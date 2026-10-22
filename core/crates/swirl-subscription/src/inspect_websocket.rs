//! Reuse the TCP protocol validator after fully validating WS-only fields.
//! Original input retention remains with Inspection; this is an isolated native
//! candidate mapping, not a claim of complete configuration or real-node tests.
use super::{NodeCapability, capability};
use crate::{Outbound, WebSocket};
use serde_json::{Value, json};

fn settings(raw: &Value) -> Result<(WebSocket, Value), &'static str> {
    let mut base = raw.clone();
    let object = base.as_object_mut().ok_or("WebSocketParameters")?;
    let ws_opts = object.remove("ws-opts");
    let transport = object.remove("transport");
    let network = object.remove("network");
    if network.as_ref().is_some_and(|v| v.as_str() != Some("ws"))
        || (ws_opts.is_some() && transport.is_some())
    {
        return Err("WebSocketConflictingTransport");
    }
    let server = raw
        .get("server")
        .and_then(Value::as_str)
        .ok_or("WebSocketHost")?;
    let default_host = if server.contains(':') && !server.starts_with('[') {
        format!("[{server}]")
    } else {
        server.to_owned()
    };
    let mut ws = WebSocket {
        host: default_host,
        path: "/".into(),
    };
    if let Some(options) = ws_opts.as_ref().or(transport.as_ref()) {
        let options = options.as_object().ok_or("WebSocketParameters")?;
        if transport.is_some() && options.get("type").and_then(Value::as_str) != Some("ws") {
            return Err("WebSocketConflictingTransport");
        }
        for key in options.keys() {
            if !matches!(key.as_str(), "path" | "headers")
                && !(transport.is_some() && key == "type")
            {
                return Err("WebSocketUnmappedOptions");
            }
        }
        if let Some(path) = options.get("path") {
            ws.path = path.as_str().ok_or("WebSocketPath")?.into();
        }
        if let Some(headers) = options.get("headers") {
            let headers = headers.as_object().ok_or("WebSocketHeaders")?;
            if headers.len() > 1 {
                return Err("WebSocketUnmappedHeaders");
            }
            for (key, value) in headers {
                if !key.eq_ignore_ascii_case("host") {
                    return Err("WebSocketUnmappedHeaders");
                }
                ws.host = value.as_str().ok_or("WebSocketHost")?.into();
            }
        }
        if object.contains_key("host") || object.contains_key("path") {
            return Err("WebSocketConflictingTransport");
        }
    } else {
        // URI transport parameters are top-level after the common URI parser.
        if !object.contains_key("raw-uri")
            && (object.contains_key("path") || object.contains_key("host"))
        {
            return Err("WebSocketUnmappedOptions");
        }
        if let Some(path) = object.remove("path") {
            ws.path = path.as_str().ok_or("WebSocketPath")?.into();
        }
        if let Some(host) = object.remove("host") {
            ws.host = host.as_str().ok_or("WebSocketHost")?.into();
        }
    }
    if raw.get("udp").is_some_and(|v| v != &json!(false)) {
        return Err("WebSocketUdpNotImplemented");
    }
    ws.validate()?;
    Ok((ws, base))
}
pub(super) fn inspect(
    raw: &Value,
    index: usize,
    family: &str,
) -> (NodeCapability, Option<Outbound>) {
    // Derive public protocol/TLS diagnostics without recursively rediscovering
    // WS. Unsupported originals are never mutated or returned in the report.
    let mut fallback = raw.clone();
    if let Some(object) = fallback.as_object_mut() {
        object.remove("network");
        object.remove("transport");
        object.remove("ws-opts");
    }
    let (mut report, _) = capability(&fallback, index, family);
    report.transport = "ws";
    report.native_tcp_candidate = false;
    report.native_udp_supported = false;
    let (ws, base) = match settings(raw) {
        Ok(value) => value,
        Err(error) => {
            report.diagnostic = error;
            return (report, None);
        }
    };
    let (base_report, candidate) = capability(&base, index, family);
    report = base_report;
    report.transport = "ws";
    report.native_tcp_candidate = false;
    report.native_udp_supported = false;
    let Some(mut candidate) = candidate else {
        return (report, None);
    };
    let error = match &mut candidate {
        Outbound::Vless { tls, websocket, .. } => {
            let result = ws.validate_tls(tls.as_ref());
            *websocket = Some(ws);
            result
        }
        Outbound::Trojan { tls, websocket, .. } => {
            let result = ws.validate_tls(Some(tls));
            *websocket = Some(ws);
            result
        }
        _ => Err("WebSocketProtocolNotImplemented"),
    };
    if let Err(error) = error {
        report.diagnostic = error;
        return (report, None);
    }
    report.native_tcp_candidate = true;
    report.diagnostic = "TcpCandidateNotYetVerified";
    (report, Some(candidate))
}

#[cfg(test)]
mod tests {
    use crate::inspect::inspect;
    use serde_json::json;
    #[test]
    fn known_websocket_formats_map_but_extensions_remain_rejected() {
        let uuid = "12345678-1234-1234-1234-123456789abc";
        let node = json!({"type":"vless","name":"fixture","server":"proxy.invalid","port":443,"uuid":uuid,"tls":true,
            "network":"ws","ws-opts":{"path":"/ws","headers":{"Host":"ws.invalid"}}});
        let data = json!({"proxies":[node.clone()]}).to_string();
        let parsed = inspect(data.as_bytes());
        assert!(parsed.report.nodes[0].native_tcp_candidate);
        assert_eq!(parsed.report.nodes[0].transport, "ws");
        assert!(!parsed.report.nodes[0].real_network_verified);
        assert_eq!(parsed.original, data.as_bytes());
        let uri = format!(
            "vless://{uuid}@proxy.invalid:443?type=ws&security=tls&path=%2Fws&host=ws.invalid"
        );
        assert!(inspect(uri.as_bytes()).report.nodes[0].native_tcp_candidate);
        let sing = json!({"outbounds":[{"type":"vless","tag":"fixture","server":"proxy.invalid","server_port":443,"uuid":uuid,
            "tls":{"enabled":true,"server_name":"proxy.invalid"},"transport":{"type":"ws","path":"/ws","headers":{"Host":"ws.invalid"}}}]}).to_string();
        assert!(inspect(sing.as_bytes()).report.nodes[0].native_tcp_candidate);
        for mutation in [
            json!({"max-early-data":2048}),
            json!({"headers":{"Cookie":"private"}}),
            json!({"path":"/bad path"}),
        ] {
            let mut bad = node.clone();
            for (key, value) in mutation.as_object().unwrap() {
                bad["ws-opts"][key] = value.clone();
            }
            let text = json!({"proxies":[bad]}).to_string();
            let parsed = inspect(text.as_bytes());
            assert!(!parsed.report.nodes[0].native_tcp_candidate);
            assert_eq!(parsed.original, text.as_bytes());
        }
        let mut bad = node;
        bad["flow"] = json!("xtls-rprx-vision");
        assert!(
            !inspect(json!({"proxies":[bad]}).to_string().as_bytes())
                .report
                .nodes[0]
                .native_tcp_candidate
        );
    }
}
