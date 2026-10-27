//! Offline, single-node projection of the existing subscription inspector.
//! Qt sends every normalized option; there is no second protocol converter.
use crate::import_ffi::encoded_response;
use serde_json::{Value, json};
use swirl_subscription::{Config, Limits, Node, Outbound, inspect};

const MAX_INPUT: usize = 1024 * 1024;

fn omit_absent_options(value: &mut Value) {
    // This projection is applied only after serialization of a validated typed
    // Outbound. Its null object values are absent Option<T>s, never unvalidated
    // source fields. Preserve the product's established optional-field shape.
    match value {
        Value::Object(object) => {
            object.retain(|_, value| !value.is_null());
            for value in object.values_mut() {
                omit_absent_options(value);
            }
        }
        Value::Array(array) => {
            for value in array {
                omit_absent_options(value);
            }
        }
        _ => {}
    }
}

fn response(input: &[u8], capacity: usize) -> Result<(usize, Option<Vec<u8>>), isize> {
    let inspected = inspect::inspect(input);
    let result = (|| {
        if let Some(error) = inspected.report.error {
            return Err(error);
        }
        // This entry point accepts exactly one complete normalized node, never
        // a full document whose DNS/rules/scripts could otherwise be ignored.
        if !inspected.report.parsed
            || !matches!(inspected.report.format, "clash-json" | "clash-yaml")
            || !inspected
                .document
                .as_object()
                .is_some_and(|object| object.len() == 1 && object.contains_key("proxies"))
            || inspected.report.nodes.len() != 1
            || inspected.tcp_candidates.len() != 1
        {
            return Err("SingleNormalizedNodeRequired");
        }
        let outbound = inspected.tcp_candidates[0]
            .as_ref()
            .ok_or(inspected.report.nodes[0].diagnostic)?;
        // Product imports have always required certificate verification. The
        // QUIC parsers understand the insecure alias, but it must not bypass
        // that policy by using a spelling other than skip-cert-verify.
        if matches!(outbound, Outbound::Hysteria2(config) if config.insecure)
            || matches!(outbound, Outbound::Tuic(config) if config.insecure)
        {
            return Err("CertificateVerificationDisabledUnsupported");
        }
        let config = Config {
            schema: 1,
            listen: "127.0.0.1:0".parse().expect("constant loopback"),
            selected: "node".into(),
            nodes: vec![Node {
                id: "node".into(),
                outbound: outbound.clone(),
            }],
            rules: Vec::new(),
            selectors: Vec::new(),
            smart_routing: false,
            china_rules_directory: None,
            dns: Default::default(),
            inbound_auth: None,
            limits: Limits::default(),
        };
        config.validate()?;
        let mut projection =
            serde_json::to_value(outbound).map_err(|_| "NativeProjectionInvalid")?;
        omit_absent_options(&mut projection);
        Ok(projection)
    })();
    match result {
        Ok(outbound) => encoded_response(
            &json!({
                "schema": 1, "ok": true, "native_outbound": outbound,
                "warnings": if inspected.report.nodes[0].diagnostic == "TcpFastOpenFallbackToTcp" {
                    vec!["TcpFastOpenFallbackToTcp"]
                } else { Vec::<&str>::new() },
                "network_verified": false
            }),
            capacity,
        ),
        Err(code) => encoded_response(
            &json!({
                "schema": 1, "ok": false, "error": code,
                "network_verified": false
            }),
            capacity,
        ),
    }
}

/// Convert one normalized Clash-shaped node, preserving all options. This
/// performs no file, DNS, network, process or runtime operation. Success data
/// contains credentials and must never be sent to logs or QML.
///
/// # Safety
/// Follows the same nonoverlapping caller-owned buffer contract as
/// `swirl_import_xray_v1`; input is bounded to 1 MiB. Null output and zero
/// capacity query the exact response size. An undersized buffer is untouched.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swirl_import_node_v1(
    input: *const u8,
    input_len: usize,
    output: *mut u8,
    output_capacity: usize,
) -> isize {
    // SAFETY: the documented public contract is checked by the shared helper.
    unsafe {
        crate::import_ffi::call(
            input,
            input_len,
            output,
            output_capacity,
            MAX_INPUT,
            response,
        )
    }
}

#[cfg(test)]
#[path = "node_import_tests.rs"]
mod tests;
