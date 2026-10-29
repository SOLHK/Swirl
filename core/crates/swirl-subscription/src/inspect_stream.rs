//! Clash transport options reuse the existing Xray typed-transport builder.
//! Only explicitly represented controls are removed before base validation.
//! References: https://wiki.metacubex.one/config/proxies/transport/
//!             https://xtls.github.io/en/config/transports/grpc.html
use super::{NodeCapability, capability};
use crate::{Outbound, Tls};
use serde_json::{Map, Value};

pub(super) fn declared(raw: &Value) -> bool {
    matches!(
        raw.get("network").and_then(Value::as_str),
        Some("grpc" | "h2" | "xhttp")
    ) || raw
        .pointer("/ws-opts/v2ray-http-upgrade")
        .is_some_and(|v| v != &Value::Bool(false))
}

fn options(raw: &Value) -> Result<(&'static str, Map<String, Value>, Value), &'static str> {
    let mut base = raw.clone();
    let object = base.as_object_mut().ok_or("TransportSettingsObject")?;
    let network = raw
        .get("network")
        .and_then(Value::as_str)
        .ok_or("TransportExpectedString")?;
    let (kind, source_key, destination_key) = match network {
        "grpc" => ("grpc", "grpc-opts", "grpcSettings"),
        "h2" => ("h2", "h2-opts", "httpSettings"),
        "xhttp" => ("xhttp", "xhttp-opts", "xhttpSettings"),
        "ws" => ("httpupgrade", "ws-opts", "httpupgradeSettings"),
        _ => return Err("TransportUnsupported"),
    };
    // Require the source transport block. A name alone does not establish
    // client-specific default service/host/path semantics. Normalized Qt URIs
    // emit the explicit block; old unresolved sources remain blocked.
    let value = object
        .remove(source_key)
        .ok_or("TransportSettingsRequired")?;
    let source = value.as_object().ok_or("TransportSettingsObject")?;
    let mut mapped = Map::new();
    for (key, value) in source {
        let destination = match (kind, key.as_str()) {
            ("grpc", "grpc-service-name") => Some("serviceName"),
            ("grpc", "grpc-user-agent") => Some("user_agent"),
            ("grpc", "ping-interval") if value.as_u64() == Some(0) => None,
            ("h2", "host" | "path") | ("xhttp", "host" | "path" | "mode" | "headers") => {
                Some(key.as_str())
            }
            ("httpupgrade", "path") => Some("path"),
            ("httpupgrade", "headers") => {
                let headers = value.as_object().ok_or("TransportHeaders")?;
                let mut others = Map::new();
                for (name, value) in headers {
                    if name.eq_ignore_ascii_case("host") {
                        if mapped.insert("host".into(), value.clone()).is_some() {
                            return Err("TransportConflictingHost");
                        }
                    } else {
                        others.insert(name.clone(), value.clone());
                    }
                }
                mapped.insert("headers".into(), Value::Object(others));
                None
            }
            ("httpupgrade", "v2ray-http-upgrade") if value.as_bool() == Some(true) => None,
            ("httpupgrade", "v2ray-http-upgrade-fast-open") if value.as_bool() == Some(false) => {
                None
            }
            ("httpupgrade", "max-early-data") if value.as_u64() == Some(0) => None,
            _ => return Err("TransportOptionUnsupported"),
        };
        if let Some(destination) = destination {
            mapped.insert(destination.into(), value.clone());
        }
    }
    if kind == "h2"
        && !mapped
            .get("host")
            .and_then(Value::as_array)
            .is_some_and(|hosts| {
                hosts.len() == 1 && hosts[0].as_str().is_some_and(|host| !host.is_empty())
            })
    {
        // A randomized host list cannot be replaced by its first element, and
        // an omitted Clash host must not inherit an unrelated Xray default.
        return Err("Http2ExplicitSingleHostRequired");
    }
    if kind == "httpupgrade"
        && source.get("v2ray-http-upgrade").and_then(Value::as_bool) != Some(true)
    {
        return Err("HttpUpgradeExplicitSelectionRequired");
    }
    if kind == "xhttp" && raw.get("type").and_then(Value::as_str) != Some("vless") {
        return Err("TransportProtocolUnsupported");
    }
    object.insert("network".into(), Value::String("tcp".into()));
    Ok((
        kind,
        Map::from_iter([(destination_key.into(), Value::Object(mapped))]),
        base,
    ))
}

pub(super) fn inspect(
    raw: &Value,
    index: usize,
    family: &str,
) -> (NodeCapability, Option<Outbound>) {
    // The fallback is diagnostic only. It never authorizes execution; the
    // validated base below retains every unconsumed top-level source option.
    let mut fallback = raw.clone();
    if let Some(object) = fallback.as_object_mut() {
        for key in ["network", "grpc-opts", "h2-opts", "xhttp-opts", "ws-opts"] {
            object.remove(key);
        }
    }
    let (mut report, _) = capability(&fallback, index, family);
    report.native_tcp_candidate = false;
    report.native_udp_supported = false;
    let (kind, settings, base) = match options(raw) {
        Ok(value) => value,
        Err(error) => {
            report.diagnostic = error;
            return (report, None);
        }
    };
    let (base_report, candidate) = capability(&base, index, family);
    report = base_report;
    report.transport = kind;
    report.native_tcp_candidate = false;
    report.native_udp_supported = false;
    let Some(mut outbound) = candidate else {
        return (report, None);
    };
    let (host, port, tls, reality) = match &outbound {
        Outbound::Vless {
            host,
            port,
            tls,
            reality,
            ..
        } => (host, *port, tls.as_ref(), reality.as_ref()),
        Outbound::Trojan {
            host, port, tls, ..
        } => (host, *port, Some(tls), None),
        _ => {
            report.diagnostic = "TransportProtocolUnsupported";
            return (report, None);
        }
    };
    let reality_name = reality.map(|reality| Tls {
        server_name: reality.server_name.clone(),
        alpn: reality.alpn.clone(),
        ca_der_base64: None,
    });
    let mapped = crate::xray::stream_transport::build(
        &settings,
        kind,
        tls.or(reality_name.as_ref()),
        host,
        port,
    )
    .and_then(|transport| {
        transport.validate_for(&outbound)?;
        Ok(transport)
    });
    match mapped {
        Ok(mapped) => match &mut outbound {
            Outbound::Vless { transport, .. } | Outbound::Trojan { transport, .. } => {
                *transport = Some(mapped)
            }
            _ => unreachable!("validated stream protocol"),
        },
        Err(error) => {
            report.diagnostic = error;
            return (report, None);
        }
    }
    report.native_tcp_candidate = true;
    report.native_udp_supported = matches!(
        &outbound,
        Outbound::Vless { udp: true, .. } | Outbound::Trojan { udp: true, .. }
    );
    report.diagnostic = "TcpCandidateNotYetVerified";
    (report, Some(outbound))
}
