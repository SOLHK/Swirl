//! Strict VMess TCP/WS normalization for Clash and v2rayN URI JSON.
//! Unknown or unsupported execution requirements fail closed and are retained
//! by the caller in the original source document.
use crate::{Outbound, Tls, WebSocket, uuid_bytes, valid_host};
use serde_json::{Map, Value};

pub fn validate(uuid: &str, alter_id: u32, security: &str) -> Result<(), &'static str> {
    if uuid_bytes(uuid).is_none() {
        return Err("VmessUuid");
    }
    if alter_id != 0 {
        return Err("VmessLegacyAlterIdUnsupported");
    }
    if !["auto", "aes-128-gcm", "chacha20-poly1305"].contains(&security) {
        return Err("VmessCipherUnsupported");
    }
    Ok(())
}

fn object(value: &Value) -> Result<&Map<String, Value>, &'static str> {
    value.as_object().ok_or("VmessParameters")
}

fn allowed(value: &Map<String, Value>, fields: &[&str]) -> Result<(), &'static str> {
    if value.keys().any(|key| !fields.contains(&key.as_str())) {
        return Err("VmessUnsupportedField");
    }
    Ok(())
}

fn text<'a>(
    value: &'a Map<String, Value>,
    key: &str,
    default: &'a str,
) -> Result<&'a str, &'static str> {
    match value.get(key) {
        None => Ok(default),
        Some(Value::String(value)) => Ok(value),
        _ => Err("VmessFieldType"),
    }
}

fn unsigned(value: Option<&Value>, default: u32) -> Result<u32, &'static str> {
    match value {
        None => Ok(default),
        Some(Value::Number(n)) => n
            .as_u64()
            .and_then(|n| n.try_into().ok())
            .ok_or("VmessInteger"),
        Some(Value::String(s)) if !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()) => {
            s.parse().map_err(|_| "VmessInteger")
        }
        _ => Err("VmessInteger"),
    }
}

fn disabled(
    value: &Map<String, Value>,
    key: &str,
    error: &'static str,
) -> Result<(), &'static str> {
    match value.get(key) {
        None | Some(Value::Bool(false)) => Ok(()),
        Some(Value::Bool(true)) => Err(error),
        _ => Err("VmessFieldType"),
    }
}

fn alpn(value: Option<&Value>, uri: bool) -> Result<Vec<String>, &'static str> {
    let result = match value {
        None => Vec::new(),
        Some(Value::String(s)) if uri && s.is_empty() => Vec::new(),
        Some(Value::String(s)) if uri => s.split(',').map(str::to_owned).collect(),
        Some(Value::Array(items)) if !uri => items
            .iter()
            .map(|item| item.as_str().map(str::to_owned).ok_or("VmessAlpn"))
            .collect::<Result<Vec<_>, _>>()?,
        _ => return Err("VmessAlpn"),
    };
    if result.len() > 16
        || result.iter().any(|item| {
            item.is_empty() || item.len() > 255 || !item.bytes().all(|b| (33..=126).contains(&b))
        })
    {
        return Err("VmessAlpn");
    }
    Ok(result)
}

fn tls(
    enabled: bool,
    server: &str,
    sni: &str,
    alpn: Vec<String>,
    fingerprint: &str,
) -> Result<Option<Tls>, &'static str> {
    if !matches!(fingerprint, "" | "rustls") {
        return Err("VmessFingerprintUnsupported");
    }
    if !enabled {
        if !sni.is_empty() || !alpn.is_empty() || !fingerprint.is_empty() {
            return Err("VmessTlsParametersWithoutTls");
        }
        return Ok(None);
    }
    let server_name = if sni.is_empty() { server } else { sni };
    if !valid_host(server_name) {
        return Err("VmessServerName");
    }
    Ok(Some(Tls {
        server_name: server_name.into(),
        alpn,
        ca_der_base64: None,
    }))
}

fn finish(
    host: &str,
    port: u32,
    uuid: &str,
    alter_id: u32,
    security: &str,
    tls: Option<Tls>,
    websocket: Option<WebSocket>,
) -> Result<Outbound, &'static str> {
    if !valid_host(host) || !(1..=u16::MAX as u32).contains(&port) {
        return Err("VmessEndpoint");
    }
    validate(uuid, alter_id, security)?;
    if let Some(ws) = &websocket {
        ws.validate_tls(tls.as_ref())?;
    }
    Ok(Outbound::Vmess {
        host: host.into(),
        port: port as u16,
        uuid: uuid.into(),
        alter_id,
        security: security.into(),
        tls,
        websocket,
    })
}

/// Accepts an inspected raw Clash node or the inspector's `raw-vmess` URI
/// envelope. Native Swirl IR uses normal serde deserialization and validate().
pub fn from_raw(value: &Value) -> Result<Outbound, &'static str> {
    let value = object(value)?;
    if let Some(raw) = value.get("raw-vmess") {
        allowed(
            value,
            &["type", "server", "port", "network", "tls", "raw-vmess"],
        )?;
        if text(value, "type", "")? != "vmess" {
            return Err("VmessProtocol");
        }
        let raw = object(raw)?;
        for (outer, inner) in [
            ("server", "add"),
            ("port", "port"),
            ("network", "net"),
            ("tls", "tls"),
        ] {
            if value.get(outer).unwrap_or(&Value::Null) != raw.get(inner).unwrap_or(&Value::Null) {
                return Err("VmessSourceConflict");
            }
        }
        return from_uri_json(raw);
    }
    allowed(
        value,
        &[
            "name",
            "type",
            "server",
            "port",
            "uuid",
            "alterId",
            "cipher",
            "tls",
            "servername",
            "alpn",
            "client-fingerprint",
            "skip-cert-verify",
            "network",
            "ws-opts",
            "udp",
            "global-padding",
            "authenticated-length",
        ],
    )?;
    if text(value, "type", "")? != "vmess" {
        return Err("VmessProtocol");
    }
    disabled(value, "udp", "VmessUdpUnsupported")?;
    disabled(value, "global-padding", "VmessGlobalPaddingUnsupported")?;
    disabled(
        value,
        "authenticated-length",
        "VmessAuthenticatedLengthUnsupported",
    )?;
    disabled(value, "skip-cert-verify", "VmessInsecureUnsupported")?;
    let host = text(value, "server", "")?;
    let tls_enabled = match value.get("tls") {
        None | Some(Value::Bool(false)) => false,
        Some(Value::Bool(true)) => true,
        _ => return Err("VmessTlsParameters"),
    };
    let tls = tls(
        tls_enabled,
        host,
        text(value, "servername", "")?,
        alpn(value.get("alpn"), false)?,
        text(value, "client-fingerprint", "")?,
    )?;
    let websocket = match text(value, "network", "tcp")? {
        "tcp" => {
            if value.contains_key("ws-opts") {
                return Err("VmessTransportConflict");
            }
            None
        }
        "ws" => {
            let empty = Map::new();
            let options = value
                .get("ws-opts")
                .map(object)
                .transpose()?
                .unwrap_or(&empty);
            allowed(
                options,
                &[
                    "path",
                    "headers",
                    "max-early-data",
                    "early-data-header-name",
                ],
            )?;
            if unsigned(options.get("max-early-data"), 0)? != 0
                || !text(options, "early-data-header-name", "")?.is_empty()
            {
                return Err("VmessEarlyDataUnsupported");
            }
            let mut ws_host = host;
            if let Some(headers) = options.get("headers") {
                let headers = object(headers)?;
                if headers.len() > 1 || headers.keys().any(|key| !key.eq_ignore_ascii_case("host"))
                {
                    return Err("VmessWebSocketHeadersUnsupported");
                }
                if let Some(value) = headers.values().next() {
                    ws_host = value.as_str().ok_or("VmessFieldType")?;
                }
            }
            Some(WebSocket {
                host: authority(ws_host),
                path: text(options, "path", "/")?.into(),
            })
        }
        _ => return Err("VmessTransportUnsupported"),
    };
    finish(
        host,
        unsigned(value.get("port"), 0)?,
        text(value, "uuid", "")?,
        unsigned(value.get("alterId"), 0)?,
        text(value, "cipher", "auto")?,
        tls,
        websocket,
    )
}

fn authority(host: &str) -> String {
    if host.parse::<std::net::Ipv6Addr>().is_ok() {
        format!("[{host}]")
    } else {
        host.into()
    }
}

fn from_uri_json(value: &Map<String, Value>) -> Result<Outbound, &'static str> {
    allowed(
        value,
        &[
            "v",
            "ps",
            "add",
            "port",
            "id",
            "aid",
            "scy",
            "net",
            "type",
            "host",
            "path",
            "tls",
            "sni",
            "alpn",
            "fp",
            "insecure",
            "allowInsecure",
        ],
    )?;
    if unsigned(value.get("v"), 2)? != 2 {
        return Err("VmessUriVersionUnsupported");
    }
    for key in ["insecure", "allowInsecure"] {
        match value.get(key) {
            None | Some(Value::Bool(false)) => (),
            Some(Value::String(s)) if s == "0" || s == "false" => (),
            Some(Value::Number(n)) if n.as_u64() == Some(0) => (),
            _ => return Err("VmessInsecureUnsupported"),
        }
    }
    if !matches!(text(value, "type", "none")?, "" | "none") {
        return Err("VmessHeaderUnsupported");
    }
    let host = text(value, "add", "")?;
    let tls_enabled = match text(value, "tls", "")? {
        "tls" => true,
        "" | "none" => false,
        _ => return Err("VmessTlsParameters"),
    };
    let tls = tls(
        tls_enabled,
        host,
        text(value, "sni", "")?,
        alpn(value.get("alpn"), true)?,
        text(value, "fp", "")?,
    )?;
    let websocket = match text(value, "net", "tcp")? {
        "tcp" => {
            if !text(value, "host", "")?.is_empty() || !matches!(text(value, "path", "")?, "" | "/")
            {
                return Err("VmessTcpHeaderUnsupported");
            }
            None
        }
        "ws" => {
            let ws_host = text(value, "host", "")?;
            let path = text(value, "path", "/")?;
            Some(WebSocket {
                host: authority(if ws_host.is_empty() { host } else { ws_host }),
                path: if path.is_empty() { "/" } else { path }.into(),
            })
        }
        _ => return Err("VmessTransportUnsupported"),
    };
    finish(
        host,
        unsigned(value.get("port"), 0)?,
        text(value, "id", "")?,
        unsigned(value.get("aid"), 0)?,
        text(value, "scy", "auto")?,
        tls,
        websocket,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn clash() -> Value {
        json!({"type":"vmess","server":"proxy.example","port":443,
            "uuid":"00112233-4455-6677-8899-aabbccddeeff","alterId":0,"cipher":"auto"})
    }
    fn envelope(raw: Value) -> Value {
        json!({"type":"vmess","server":raw["add"],"port":raw["port"],
            "network":raw["net"],"tls":raw["tls"],"raw-vmess":raw})
    }

    #[test]
    fn clash_and_uri_produce_identical_native_parameters() {
        let a = from_raw(&clash()).unwrap();
        let b = from_raw(&envelope(
            json!({"v":"2","add":"proxy.example","port":"443",
            "id":"00112233-4455-6677-8899-aabbccddeeff","aid":"0","scy":"auto","net":"tcp"}),
        ))
        .unwrap();
        assert_eq!(
            serde_json::to_value(a).unwrap(),
            serde_json::to_value(b).unwrap()
        );
    }

    #[test]
    fn websocket_tls_maps_sni_host_path_and_alpn_without_changing_identity() {
        let mut value = clash();
        value["network"] = json!("ws");
        value["tls"] = json!(true);
        value["servername"] = json!("cert.example");
        value["alpn"] = json!(["http/1.1"]);
        value["ws-opts"] = json!({"path":"/vmess%2Ftest","headers":{"Host":"cdn.example"}});
        let native = from_raw(&value).unwrap();
        let Outbound::Vmess {
            uuid,
            tls,
            websocket,
            ..
        } = native
        else {
            panic!("protocol changed")
        };
        assert_eq!(uuid, "00112233-4455-6677-8899-aabbccddeeff");
        let tls = tls.unwrap();
        assert_eq!(tls.server_name, "cert.example");
        assert_eq!(tls.alpn, ["http/1.1"]);
        let ws = websocket.unwrap();
        assert_eq!(
            (ws.host.as_str(), ws.path.as_str()),
            ("cdn.example", "/vmess%2Ftest")
        );
    }

    #[test]
    fn critical_fields_never_disappear_before_dialing() {
        for (key, val) in [
            ("udp", json!(true)),
            ("alterId", json!(1)),
            ("cipher", json!("none")),
            ("skip-cert-verify", json!(true)),
            ("global-padding", json!(true)),
            ("authenticated-length", json!(true)),
            ("client-fingerprint", json!("chrome")),
            ("fingerprint", json!("abc")),
            ("packet-encoding", json!("xudp")),
            ("network", json!("typo")),
            ("reality-opts", json!({})),
            ("unknown", json!(false)),
        ] {
            let mut value = clash();
            value[key] = val;
            assert!(from_raw(&value).is_err(), "accepted {key}");
        }
    }

    #[test]
    fn uri_envelope_conflicts_and_critical_unknown_fields_are_rejected() {
        let raw = json!({"add":"proxy.example","port":"443",
            "id":"00112233-4455-6677-8899-aabbccddeeff","aid":"0"});
        let mut value = envelope(raw.clone());
        value["server"] = json!("different.example");
        assert!(matches!(from_raw(&value), Err("VmessSourceConflict")));
        for key in ["pcs", "vcn", "eh", "ed", "pbk"] {
            let mut raw = raw.clone();
            raw[key] = json!("nonempty");
            assert!(from_raw(&envelope(raw)).is_err());
        }
    }

    #[test]
    fn unsupported_ws_headers_early_data_and_non_http1_alpn_are_rejected() {
        for options in [
            json!({"headers":{"Host":"a.example","X-Required":"keep"}}),
            json!({"max-early-data":1024}),
            json!({"early-data-header-name":"Sec-WebSocket-Protocol"}),
        ] {
            let mut value = clash();
            value["network"] = json!("ws");
            value["ws-opts"] = options;
            assert!(from_raw(&value).is_err());
        }
        let mut value = clash();
        value["network"] = json!("ws");
        value["tls"] = json!(true);
        value["alpn"] = json!(["h2"]);
        assert!(matches!(from_raw(&value), Err("WebSocketAlpnUnsupported")));
    }
}
