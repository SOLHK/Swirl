//! Bounded, redacted DNS/TCP diagnostics for an encrypted-cache stdin pipeline.
//! No private-json output, command-line endpoint, proxy settings or application
//! payload. A successful report establishes only TCP reachability.
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    net::{IpAddr, Ipv6Addr},
    time::Duration,
};
use swirl_dns::Resolver;
use swirl_protocol::{Target, diagnose_tcp};
use swirl_subscription::{Config, Dns, Limits, Node, Outbound, valid_host};

const MAX_INPUT: usize = 64 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    host: String,
    port: u16,
    #[serde(default)]
    dns: Dns,
    #[serde(default = "total_budget")]
    total_budget_ms: u64,
    #[serde(default = "dns_budget")]
    dns_budget_ms: u64,
}

fn total_budget() -> u64 {
    10_000
}

fn dns_budget() -> u64 {
    3_000
}

fn parse_request(input: &[u8]) -> Result<Request, &'static str> {
    if input.is_empty() || input.len() > MAX_INPUT {
        return Err("DiagnosticInput");
    }
    let mut request: Request = serde_json::from_slice(input).map_err(|_| "DiagnosticInput")?;
    if let Some(ipv6) = request
        .host
        .strip_prefix('[')
        .and_then(|v| v.strip_suffix(']'))
    {
        request.host = ipv6
            .parse::<Ipv6Addr>()
            .map_err(|_| "DiagnosticInput")?
            .to_string();
    } else if let Ok(ip) = request.host.parse::<IpAddr>() {
        request.host = ip.to_string();
    }
    if !valid_host(&request.host) || request.port == 0 {
        return Err("DiagnosticInput");
    }
    if !(1..=10_000).contains(&request.total_budget_ms)
        || !(1..=3_000).contains(&request.dns_budget_ms)
    {
        return Err("DiagnosticBudget");
    }
    Ok(request)
}

fn resolver(dns: Dns) -> Result<Resolver, &'static str> {
    // Reuse the product's entire DNS validation, including duplicate mappings,
    // endpoint bounds, conflicting resolver modes and strict TLS settings. This
    // value is validated only: no listener or product core is started.
    let config = Config {
        schema: 1,
        listen: ([127, 0, 0, 1], 0).into(),
        selected: "diagnostic".into(),
        nodes: vec![Node {
            id: "diagnostic".into(),
            outbound: Outbound::Direct {},
        }],
        rules: Vec::new(),
        selectors: Vec::new(),
        dns,
        inbound_auth: None,
        limits: Limits::default(),
    };
    config.validate().map_err(|_| "DiagnosticDnsConfig")?;
    Resolver::default()
        .with_config(&config.dns)
        .map_err(|_| "DiagnosticDnsConfig")
}

fn error_report(code: &'static str) -> Value {
    json!({
        "schema": 1,
        "engine": "swirl-rust",
        "scope": "dns_tcp_only",
        "ok": false,
        "error_code": code,
        "failure_stage": "input",
        "total_budget_ms": 10_000,
        "dns_budget_ms": 3_000,
        "dns_elapsed_ms": 0,
        "tcp_elapsed_ms": 0,
        "total_elapsed_ms": 0,
        "address_count": 0,
        "ipv4_count": 0,
        "ipv6_count": 0,
        "attempted_count": 0,
        "remaining_count": 0,
        "peak_pending": 0,
        "attempts": [],
    })
}

fn execute() -> Result<Value, &'static str> {
    if std::env::args_os().len() != 1 {
        return Err("DiagnosticInput");
    }
    let mut input = Vec::new();
    std::io::stdin()
        .take((MAX_INPUT + 1) as u64)
        .read_to_end(&mut input)
        .map_err(|_| "DiagnosticInput")?;
    let request = parse_request(&input)?;
    let resolver = resolver(request.dns)?;
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(1)
        .enable_all()
        .build()
        .map_err(|_| "DiagnosticRuntime")?;
    let report = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        runtime.block_on(diagnose_tcp(
            &resolver,
            &Target {
                host: request.host,
                port: request.port,
            },
            Duration::from_millis(request.total_budget_ms),
            Duration::from_millis(request.dns_budget_ms),
        ))
    }));
    // Tokio's system resolver may have a non-cancellable blocking OS lookup.
    // Do not let runtime destruction extend a completed diagnostic by waiting
    // for it. This one-shot process terminates after printing its safe report.
    runtime.shutdown_timeout(Duration::ZERO);
    let report = report.map_err(|_| "DiagnosticInternal")?;
    serde_json::to_value(report).map_err(|_| "DiagnosticInternal")
}

fn main() {
    // Panic messages can include dependency arguments. This standalone private
    // diagnostic emits only our closed error vocabulary, also on unexpected
    // failures; it does not change the application's panic behavior.
    std::panic::set_hook(Box::new(|_| {}));
    let output = match std::panic::catch_unwind(execute) {
        Ok(Ok(report)) => report,
        Ok(Err(code)) => error_report(code),
        Err(_) => error_report("DiagnosticInternal"),
    };
    if let Ok(bytes) = serde_json::to_vec(&output) {
        let _ = std::io::stdout().write_all(&bytes);
        let _ = std::io::stdout().write_all(b"\n");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stdin_rejects_ambiguous_input_and_never_echoes_private_values() {
        for input in [
            r#"{"host":"secret.invalid","port":443,"password":"private-marker"}"#,
            r#"{"host":"secret.invalid","host":"other.invalid","port":443}"#,
            r#"{"host":"secret.invalid","port":0}"#,
            r#"{"host":"private-marker\nsecret.invalid","port":443}"#,
            r#"{"host":"secret.invalid","port":443,"total_budget_ms":10001}"#,
            r#"{"host":"secret.invalid","port":443,"dns_budget_ms":3001}"#,
            r#"{"host":"secret.invalid","port":443,"total_budget_ms":0}"#,
            r#"{"host":"secret.invalid","port":443,"dns_budget_ms":0}"#,
            "private-marker-invalid-json",
        ] {
            let error = parse_request(input.as_bytes()).err().expect("must reject");
            let output = error_report(error).to_string();
            for sensitive in ["secret.invalid", "other.invalid", "private-marker", "443"] {
                assert!(!output.contains(sensitive));
            }
        }
        assert!(parse_request(&vec![b'x'; MAX_INPUT + 1]).is_err());
    }

    #[test]
    fn stdin_preserves_small_budgets_and_normalizes_ipv6() {
        let request =
            parse_request(br#"{"host":"[0:0:0:0:0:0:0:1]","port":443,"total_budget_ms":4750}"#)
                .unwrap();
        assert_eq!(request.host, "::1");
        assert_eq!(request.total_budget_ms, 4750);
        assert_eq!(request.dns_budget_ms, 3000);
    }

    #[test]
    fn diagnostic_uses_product_dns_validation() {
        for dns in [
            r#"{"hosts":[{"name":"a.invalid","address":"127.0.0.1"},{"name":"A.invalid","address":"::1"}]}"#,
            r#"{"servers":["127.0.0.1:0"]}"#,
            r#"{"servers":["127.0.0.1:53","127.0.0.1:53"]}"#,
            r#"{"use_system_hosts":false}"#,
        ] {
            let dns: Dns = serde_json::from_str(dns).unwrap();
            assert_eq!(resolver(dns).err(), Some("DiagnosticDnsConfig"));
        }
        assert!(resolver(Dns::default()).is_ok());
    }
}
