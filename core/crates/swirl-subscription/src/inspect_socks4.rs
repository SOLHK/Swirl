//! SOCKS4/4a import mapping reuses the existing native handshake and IR.
//! `socks4` resolves destination names locally; `socks4a` sends the name to
//! the proxy. USERID is not a password authentication mechanism.
use super::{NodeCapability, allowed};
use crate::{Config, Outbound};
use serde_json::{Value, json};

const NODE_FIELDS: &[&str] = &[
    "type",
    "name",
    "server",
    "port",
    "username",
    "password",
    "network",
    "udp",
    "tls",
    "tfo",
    "skip-cert-verify",
    "raw-uri",
];
const SING_BOX_FIELDS: &[&str] = &[
    "type",
    "tag",
    "server",
    "server_port",
    "version",
    "username",
    "password",
    "network",
];

fn fields(raw: &Value) -> &'static [&'static str] {
    if raw.get("type").and_then(Value::as_str) == Some("socks") {
        SING_BOX_FIELDS
    } else {
        NODE_FIELDS
    }
}

fn outbound(raw: &Value, family: &str, remote_dns: bool) -> Result<Outbound, &'static str> {
    if family == "xray-v2ray-json"
        || raw
            .as_object()
            .is_none_or(|o| o.keys().any(|key| !fields(raw).contains(&key.as_str())))
    {
        return Err("Socks4UnmappedFields");
    }
    let source_type = raw.get("type").and_then(Value::as_str).unwrap_or("");
    let source_version = if remote_dns { "4a" } else { "4" };
    if source_type == "socks" && raw.get("version").and_then(Value::as_str) != Some(source_version)
    {
        return Err("Socks4Version");
    }
    if raw
        .get("network")
        .is_some_and(|value| value.as_str() != Some("tcp"))
    {
        return Err("Socks4NetworkNotImplemented");
    }
    for key in ["udp", "tls", "tfo", "skip-cert-verify"] {
        if raw.get(key).is_some_and(|value| value != &json!(false)) {
            return Err("Socks4ExtensionNotImplemented");
        }
    }
    // Never reinterpret a requested password as a SOCKS4 USERID or discard it.
    if raw
        .get("password")
        .is_some_and(|value| value.as_str() != Some(""))
    {
        return Err("Socks4PasswordUnsupported");
    }
    let user_id = match raw.get("username") {
        Some(value) => value.as_str().ok_or("Socks4UserId")?,
        None => "",
    };
    let host = raw
        .get("server")
        .and_then(Value::as_str)
        .ok_or("Socks4Server")?;
    // The field allowlist prevents aliases from overriding each other.
    let port = raw
        .get(if source_type == "socks" {
            "server_port"
        } else {
            "port"
        })
        .and_then(Value::as_u64)
        .filter(|value| (1..=65535).contains(value))
        .ok_or("Socks4Port")? as u16;
    let outbound = Outbound::Socks4 {
        host: host.into(),
        port,
        user_id: user_id.into(),
        remote_dns,
    };
    let config: Config = serde_json::from_value(json!({
        "schema": 1, "listen": "127.0.0.1:0", "selected": "isolated",
        "nodes": [{"id": "isolated", "outbound": outbound}],
    }))
    .map_err(|_| "Socks4Parameters")?;
    config.validate()?;
    Ok(outbound)
}

pub(super) fn inspect(
    raw: &Value,
    index: usize,
    family: &str,
) -> (NodeCapability, Option<Outbound>) {
    let remote_dns = raw
        .get("type")
        .and_then(Value::as_str)
        .is_some_and(|kind| kind.eq_ignore_ascii_case("socks4a"))
        || (raw.get("type").and_then(Value::as_str) == Some("socks")
            && raw.get("version").and_then(Value::as_str) == Some("4a"));
    let result = outbound(raw, family, remote_dns);
    let report = NodeCapability {
        index,
        protocol: if remote_dns { "socks4a" } else { "socks4" },
        version: if remote_dns { "4a" } else { "4" },
        transport: allowed(
            raw.get("network").and_then(Value::as_str).unwrap_or("tcp"),
            &["tcp", "ws", "grpc", "h2", "quic"],
            "unknown",
        ),
        obfuscation: "none",
        tls: if raw.get("tls").is_some_and(|v| v != &json!(false)) {
            "declared-unrecognized"
        } else {
            "not-enabled"
        },
        cipher: "not-declared-or-unrecognized",
        udp_declared: raw.get("udp").and_then(Value::as_bool) == Some(true)
            || raw.get("network").and_then(Value::as_str) == Some("udp"),
        unrecognized_fields: raw.as_object().map_or(1, |object| {
            object
                .keys()
                .filter(|key| !fields(raw).contains(&key.as_str()))
                .count()
        }),
        native_tcp_candidate: result.is_ok(),
        native_udp_supported: false,
        real_network_verified: false,
        diagnostic: result
            .as_ref()
            .err()
            .copied()
            .unwrap_or("TcpCandidateNotYetVerified"),
    };
    (report, result.ok())
}

#[cfg(test)]
mod tests {
    use crate::{Outbound, inspect::inspect};
    use base64::{Engine, engine::general_purpose::STANDARD};
    use serde_json::{Value, json};

    #[test]
    fn formats_preserve_userid_and_local_or_remote_dns() {
        for (kind, version, remote) in [("socks4", "4", false), ("socks4a", "4a", true)] {
            let sing = json!({"outbounds":[{"type":"socks", "version":version,
                "server":"proxy.fixture.invalid", "server_port":1080, "username":"user:fixture", "network":"tcp"}]}).to_string();
            let uri = format!("{kind}://user%3Afixture@proxy.fixture.invalid:1080#fixture");
            let yaml = format!(
                "proxies: [{{name: fixture, type: {kind}, server: proxy.fixture.invalid, port: 1080, username: 'user:fixture'}}]"
            );
            let json = json!({"proxies":[{"name":"fixture", "type":kind,
                "server":"proxy.fixture.invalid", "port":1080, "username":"user:fixture",
                "password":"", "udp":false, "tls":false}]})
            .to_string();
            for input in [
                &uri,
                &STANDARD.encode(&uri),
                &yaml,
                &json,
                &sing,
                &STANDARD.encode(&sing),
            ] {
                let parsed = inspect(input.as_bytes());
                assert!(parsed.report.parsed, "{:?}", parsed.report.error);
                let report = &parsed.report.nodes[0];
                assert!(report.native_tcp_candidate, "{}", report.diagnostic);
                assert_eq!(report.protocol, kind);
                assert_eq!(report.version, version);
                assert!(!report.native_udp_supported);
                assert!(!report.real_network_verified);
                assert_eq!(parsed.original, input.as_bytes());
                match parsed.tcp_candidates[0].as_ref().unwrap() {
                    Outbound::Socks4 {
                        host,
                        port,
                        user_id,
                        remote_dns,
                    } => {
                        assert_eq!(host, "proxy.fixture.invalid");
                        assert_eq!(*port, 1080);
                        assert_eq!(user_id, "user:fixture");
                        assert_eq!(*remote_dns, remote);
                    }
                    _ => panic!("wrong native protocol mapping"),
                }
                let public_report = serde_json::to_string(&parsed.report).unwrap();
                assert!(!public_report.contains("proxy.fixture.invalid"));
                assert!(!public_report.contains("user:fixture"));
            }
        }
    }

    #[test]
    fn unsafe_or_ambiguous_parameters_stay_preserved_and_unexecutable() {
        let base = json!({"name":"fixture", "type":"socks4a", "server":"proxy.fixture.invalid", "port":1080});
        for (key, value) in [
            ("password", json!("must-not-be-discarded")),
            ("password", json!(0)),
            ("username", json!(1)),
            ("username", json!("u\0id")),
            ("username", json!("é".repeat(128))),
            ("username", json!("u\u{85}id")),
            ("udp", json!(true)),
            ("udp", json!("false")),
            ("tls", json!(true)),
            ("tls", json!({"enabled":false})),
            ("tfo", json!("true")),
            ("sni", json!("name.fixture.invalid")),
            ("network", json!("udp")),
            ("network", json!("ws")),
            ("server_port", json!(1080)),
            ("port", json!("1080")),
            ("port", json!(65536)),
            ("port", json!(0)),
            ("server", json!("")),
            ("version", json!("4")),
            ("version", json!(4)),
            ("unknown-secret-field", json!("secret-value")),
            ("remote_dns", json!(false)),
        ] {
            let mut node = base.clone();
            node[key] = value;
            let document = json!({"proxies":[node]}).to_string();
            let parsed = inspect(document.as_bytes());
            assert!(parsed.report.parsed);
            assert!(!parsed.report.nodes[0].native_tcp_candidate, "{key}");
            assert_eq!(parsed.original, document.as_bytes());
            assert!(parsed.tcp_candidates[0].is_none());
        }
        for input in [
            "socks4a://user:password@proxy.fixture.invalid:1080",
            "socks4://u%00x@proxy.fixture.invalid:1080",
            "socks4a://proxy.fixture.invalid:1080?remote_dns=false",
            "socks4://proxy.fixture.invalid:1080/a-path",
        ] {
            let parsed = inspect(input.as_bytes());
            assert!(
                !parsed
                    .report
                    .nodes
                    .first()
                    .is_some_and(|node| node.native_tcp_candidate)
            );
            assert_eq!(parsed.original, input.as_bytes());
        }
        // A malformed/unsupported sing-box version must never become SOCKS5.
        for version in [json!(4), json!(null), json!("4A"), json!("6"), json!(false)] {
            let document = json!({"outbounds":[{"type":"socks", "version":version,
                "server":"proxy.fixture.invalid", "server_port":1080}]})
            .to_string();
            assert!(!inspect(document.as_bytes()).report.nodes[0].native_tcp_candidate);
        }
    }

    #[test]
    fn userid_is_not_base64_password_authentication() {
        let parsed = inspect(b"socks4://dXNlcjpwYXNz@proxy.fixture.invalid:1080");
        assert!(parsed.report.nodes[0].native_tcp_candidate);
        let Value::String(user) = serde_json::to_value(parsed.tcp_candidates[0].as_ref().unwrap())
            .unwrap()["user_id"]
            .clone()
        else {
            panic!("userid missing")
        };
        assert_eq!(user, "dXNlcjpwYXNz");
    }
}
