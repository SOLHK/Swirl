//! Independently implemented Xray/V2Ray stream semantics. This module only
//! projects the supported subset; the caller retains every source field and
//! refuses execution on any error/unsupported diagnostic.
use super::{
    convert::{Authentication, Endpoint, NodeSource, Protocol, Security, Sink, Transport},
    strict::key_path,
};
use crate::{Reality, Tls, WebSocket};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use serde_json::{Map, Value};

/// Candidate parameters only. Any blocking diagnostic prevents native execution.
/// Raw stream settings remain owned once by ConvertedDocument for exact recovery.
pub(super) struct SecurityMapping {
    pub transport: Transport,
    pub security: Security,
    pub tls: Option<Tls>,
    pub reality: Option<Reality>,
    pub websocket: Option<WebSocket>,
}

fn push(sink: &mut Sink, code: &str, path: &str, severity: &str) {
    // Unimplemented transports and extension schemas have not established
    // semantic validity. Known, fully checked features can remain valid yet
    // unsupported by the current runtime (for example allowInsecure=true).
    if severity == "unsupported"
        && matches!(
            code,
            "TransportUnsupported"
                | "SecurityUnsupported"
                | "StreamOptionUnsupported"
                | "RealityOptionUnsupported"
                | "TcpHeaderOptionUnsupported"
                | "UnappliedStreamSettingsPreserved"
        )
    {
        sink.unknown(code, path);
    } else {
        sink.issue(code, path, severity);
    }
}

fn transport(value: &str) -> Transport {
    match value {
        "tcp" => Transport::Tcp,
        "ws" => Transport::WebSocket,
        "grpc" => Transport::Grpc,
        "h2" => Transport::Http2,
        "httpupgrade" => Transport::HttpUpgrade,
        "xhttp" => Transport::Xhttp,
        _ => Transport::Unknown,
    }
}

fn security(value: &str) -> Security {
    match value {
        "none" => Security::None,
        "tls" => Security::Tls,
        "reality" => Security::Reality,
        _ => Security::Unknown,
    }
}

pub(super) fn map(
    outbound: &Value,
    endpoint: Option<&Endpoint>,
    authentication: &Authentication,
    source: &NodeSource,
    protocol: Protocol,
    sink: &mut Sink,
) -> SecurityMapping {
    let (address, port) = endpoint.map_or(("", 0), |endpoint| {
        (endpoint.address.as_str(), endpoint.port)
    });
    let flow = match authentication {
        Authentication::Vless { flow, .. } => flow.as_deref(),
        _ => None,
    };
    let protocol = match protocol {
        Protocol::Vless => "vless",
        Protocol::Vmess => "vmess",
        Protocol::Trojan => "trojan",
        Protocol::Shadowsocks => "shadowsocks",
        Protocol::Socks => "socks",
        Protocol::Http => "http",
        Protocol::Unknown => "unknown",
    };
    mux(
        outbound.get("mux"),
        &key_path(&source.outbound_path, "mux"),
        sink,
    );
    let mapped = map_stream(
        outbound.get("streamSettings").unwrap_or(&Value::Null),
        protocol,
        address,
        port,
        flow,
        &key_path(&source.outbound_path, "streamSettings"),
        sink,
    );
    SecurityMapping {
        transport: transport(&mapped.network),
        security: security(&mapped.security),
        tls: mapped.tls,
        reality: mapped.reality,
        websocket: mapped.websocket,
    }
}

fn mux(value: Option<&Value>, path: &str, sink: &mut Sink) {
    let Some(value) = value else {
        return;
    };
    let Some(settings) = object(value, path, sink) else {
        return;
    };
    for (key, value) in settings {
        let field = key_path(path, key);
        match key.as_str() {
            "enabled" => disabled_bool(value, &field, "MuxUnsupported", sink),
            "concurrency" | "xudpConcurrency" => {
                if !value.as_i64().is_some_and(|n| i16::try_from(n).is_ok()) {
                    sink.error("MuxConcurrencyRange", &field);
                } else if key == "xudpConcurrency" && value.as_i64() != Some(0) {
                    sink.unsupported("MuxXudpUnsupported", &field);
                }
            }
            "xudpProxyUDP443" => match value.as_str() {
                Some("" | "reject") => (),
                Some("allow" | "skip") => sink.unsupported("MuxXudpUnsupported", &field),
                Some(_) => sink.error("MuxXudpPolicy", &field),
                None => sink.error("ExpectedString", &field),
            },
            _ => sink.unknown("MuxOptionUnsupported", &field),
        }
    }
}

struct StreamMapping {
    network: String,
    security: String,
    pub tls: Option<Tls>,
    pub reality: Option<Reality>,
    pub websocket: Option<WebSocket>,
}

fn string<'a>(
    object: &'a Map<String, Value>,
    key: &str,
    path: &str,
    diagnostics: &mut Sink,
) -> Option<&'a str> {
    match object.get(key) {
        None => None,
        Some(Value::String(value)) => Some(value),
        Some(_) => {
            push(diagnostics, "ExpectedString", &key_path(path, key), "error");
            None
        }
    }
}

fn object<'a>(
    value: &'a Value,
    path: &str,
    diagnostics: &mut Sink,
) -> Option<&'a Map<String, Value>> {
    match value.as_object() {
        Some(object) => Some(object),
        None => {
            push(diagnostics, "ExpectedObject", path, "error");
            None
        }
    }
}

fn disabled_bool(value: &Value, path: &str, code: &str, diagnostics: &mut Sink) {
    match value.as_bool() {
        Some(false) => (),
        Some(true) => push(diagnostics, code, path, "unsupported"),
        None => push(diagnostics, "ExpectedBoolean", path, "error"),
    }
}

fn empty_string(value: &Value, path: &str, code: &str, diagnostics: &mut Sink) {
    match value.as_str() {
        Some("") => (),
        Some(_) => push(diagnostics, code, path, "unsupported"),
        None => push(diagnostics, "ExpectedString", path, "error"),
    }
}

fn network_name(value: &str) -> String {
    match value.to_ascii_lowercase().as_str() {
        "raw" | "tcp" => "tcp".into(),
        "ws" | "websocket" => "ws".into(),
        "http" | "h2" => "h2".into(),
        "gun" | "grpc" => "grpc".into(),
        "splithttp" | "xhttp" => "xhttp".into(),
        _ => value.to_ascii_lowercase(),
    }
}

fn alpn(value: Option<&Value>, websocket: bool, path: &str, diagnostics: &mut Sink) -> Vec<String> {
    // These are bounds of the native TLS projection, not of retained source.
    // Check before cloning/splitting so one large value cannot amplify across
    // thousands of expanded users.
    if value.is_some_and(|value| match value {
        Value::String(value) => value.len() > 4095,
        Value::Array(values) => {
            values.len() > 16
                || values
                    .iter()
                    .any(|value| value.as_str().is_some_and(|v| v.len() > 255))
        }
        _ => false,
    }) {
        push(diagnostics, "TlsAlpnParameters", path, "error");
        return Vec::new();
    }
    let values = match value {
        None => Vec::new(),
        Some(Value::String(value)) => value.split(',').map(str::to_owned).collect(),
        Some(Value::Array(values)) => {
            let mut protocols = Vec::new();
            for (index, value) in values.iter().enumerate() {
                if let Some(value) = value.as_str() {
                    protocols.push(value.to_owned());
                } else {
                    push(
                        diagnostics,
                        "ExpectedString",
                        &format!("{path}[{index}]"),
                        "error",
                    );
                }
            }
            protocols
        }
        Some(_) => {
            push(diagnostics, "ExpectedStringOrStringArray", path, "error");
            Vec::new()
        }
    };
    if values.is_empty() {
        // Both official TLS implementations use this default; their WS
        // dialers provide the HTTP/1.1-specific default before TLS negotiation.
        if websocket {
            vec!["http/1.1".into()]
        } else {
            vec!["h2".into(), "http/1.1".into()]
        }
    } else {
        if values.len() > 16
            || values.iter().any(|value| {
                value.is_empty()
                    || value.len() > 255
                    || !value.is_ascii()
                    || value.bytes().any(|b| b.is_ascii_control())
            })
        {
            push(diagnostics, "TlsAlpnParameters", path, "error");
        }
        if values
            .iter()
            .any(|value| value.eq_ignore_ascii_case("frommitm"))
        {
            push(
                diagnostics,
                "TlsDynamicAlpnUnsupported",
                path,
                "unsupported",
            );
        }
        values
    }
}

fn tls(
    settings: &Value,
    network: &str,
    protocol: &str,
    address: &str,
    path: &str,
    diagnostics: &mut Sink,
) -> Option<Tls> {
    let settings = object(settings, path, diagnostics)?;
    for (key, value) in settings {
        let path = key_path(path, key);
        match key.as_str() {
            "serverName" | "alpn" => (),
            "fingerprint" => {
                if value.is_string() {
                    push(
                        diagnostics,
                        "TlsFingerprintUnsupported",
                        &path,
                        "unsupported",
                    );
                } else {
                    push(diagnostics, "ExpectedString", &path, "error");
                }
            }
            "allowInsecure" => disabled_bool(value, &path, "TlsInsecureUnsupported", diagnostics),
            "disableSystemRoot" => {
                disabled_bool(value, &path, "TlsDisableSystemRootUnsupported", diagnostics)
            }
            "enableSessionResumption" => {
                disabled_bool(value, &path, "TlsSessionResumptionUnsupported", diagnostics)
            }
            "rejectUnknownSni" | "verifyClientCertificate" => {
                disabled_bool(value, &path, "TlsInboundOptionUnsupported", diagnostics)
            }
            "certificates" => match value.as_array() {
                Some(certificates) if certificates.is_empty() => (),
                Some(_) => push(
                    diagnostics,
                    "TlsCertificatesUnsupported",
                    &path,
                    "unsupported",
                ),
                None => push(diagnostics, "ExpectedArray", &path, "error"),
            },
            "minVersion" | "maxVersion" | "cipherSuites" | "masterKeyLog" => {
                empty_string(value, &path, "TlsOptionUnsupported", diagnostics);
            }
            // Pins, custom trust, ECH, curves and unknown future options must
            // never disappear at the native boundary, even if a value is empty.
            _ => diagnostics.unknown("TlsOptionUnsupported", &path),
        }
    }
    let declared_name = string(settings, "serverName", path, diagnostics).unwrap_or("");
    let server_name = if declared_name.is_empty() {
        address
    } else {
        declared_name
    };
    if !crate::valid_host(server_name) {
        push(
            diagnostics,
            "TlsServerNameUnsupported",
            &key_path(path, "serverName"),
            "unsupported",
        );
        return None;
    }
    if server_name.eq_ignore_ascii_case("frommitm") || server_name.starts_with("experiment:") {
        push(
            diagnostics,
            "TlsDynamicServerNameUnsupported",
            &key_path(path, "serverName"),
            "unsupported",
        );
    }
    let alpn = alpn(
        settings.get("alpn"),
        network == "ws",
        &key_path(path, "alpn"),
        diagnostics,
    );
    if protocol == "http" && alpn.iter().any(|value| value != "http/1.1") {
        push(
            diagnostics,
            "HttpConnectAlpnUnsupported",
            &key_path(path, "alpn"),
            "unsupported",
        );
    }
    Some(Tls {
        server_name: server_name.to_owned(),
        alpn,
        ca_der_base64: None,
    })
}

fn reality(settings: &Value, address: &str, path: &str, diagnostics: &mut Sink) -> Option<Reality> {
    let settings = object(settings, path, diagnostics)?;
    for (key, value) in settings {
        let path = key_path(path, key);
        match key.as_str() {
            "serverName" | "fingerprint" | "publicKey" | "password" | "shortId" => (),
            "show" => disabled_bool(value, &path, "RealityDebugOutputUnsupported", diagnostics),
            "spiderX" => {
                if value.is_string() {
                    push(
                        diagnostics,
                        "RealitySpiderUnsupported",
                        &path,
                        "unsupported",
                    );
                } else {
                    push(diagnostics, "ExpectedString", &path, "error");
                }
            }
            "mldsa65Verify" => empty_string(value, &path, "RealityMldsa65Unsupported", diagnostics),
            "masterKeyLog" => empty_string(value, &path, "RealityKeyLogUnsupported", diagnostics),
            _ => push(
                diagnostics,
                "RealityOptionUnsupported",
                &path,
                "unsupported",
            ),
        }
    }
    let key = string(settings, "publicKey", path, diagnostics).unwrap_or("");
    let password = string(settings, "password", path, diagnostics).unwrap_or("");
    if !key.is_empty() && !password.is_empty() && key != password {
        push(
            diagnostics,
            "RealityPublicKeyAliasConflict",
            &key_path(path, "password"),
            "error",
        );
    }
    let public_key = if password.is_empty() { key } else { password };
    let name = string(settings, "serverName", path, diagnostics).unwrap_or("");
    let fingerprint = string(settings, "fingerprint", path, diagnostics).unwrap_or("");
    if fingerprint.is_empty() {
        push(
            diagnostics,
            "RealityFingerprintMustBeExplicit",
            &key_path(path, "fingerprint"),
            "unsupported",
        );
    }
    let short_id = string(settings, "shortId", path, diagnostics).unwrap_or("");
    let server_name = if name.is_empty() { address } else { name };
    if public_key.len() > 44
        || short_id.len() > 16
        || server_name.len() > 253
        || fingerprint.len() > 64
    {
        push(diagnostics, "RealityParametersBounds", path, "error");
        return None;
    }
    let source_fingerprint = fingerprint.to_ascii_lowercase();
    // Only explicitly modeled official names may cross the native boundary.
    // In particular, Swirl-only names such as rustls/chrome_133 are not source
    // aliases. A future native profile must not implicitly widen this set.
    let supported_source_profile =
        matches!(source_fingerprint.as_str(), "chrome" | "hellochrome_133");
    if !supported_source_profile && !source_fingerprint.is_empty() {
        diagnostics.unknown(
            "RealitySourceFingerprintUnsupported",
            &key_path(path, "fingerprint"),
        );
    }
    let fingerprint = match source_fingerprint.as_str() {
        // Xray's pinned uTLS dependency aa6edf4b11af maps Chrome_Auto to
        // Chrome_133. The explicit official name selects that same fixed
        // profile; only the execution projection uses Swirl's internal alias.
        "hellochrome_133" => "chrome_133".to_owned(),
        _ => source_fingerprint,
    };
    let reality = Reality {
        server_name: server_name.to_owned(),
        public_key: public_key.to_owned(),
        short_id: short_id.to_owned(),
        fingerprint,
        alpn: Vec::new(),
    };
    if URL_SAFE_NO_PAD.decode(public_key).is_err() {
        push(
            diagnostics,
            "RealityPublicKey",
            &key_path(path, "publicKey"),
            "error",
        );
    }
    if let Err(code) = reality.key_material() {
        let field = if code == "RealityShortId" {
            "shortId"
        } else {
            "publicKey"
        };
        push(diagnostics, code, &key_path(path, field), "error");
    }
    match reality.validate() {
        Err(code) => {
            // key_material errors above are input errors; remaining failures are
            // actual limitations of the current native REALITY implementation.
            if !matches!(code, "RealityPublicKey" | "RealityShortId") {
                push(diagnostics, code, path, "unsupported");
            }
        }
        Ok(()) if supported_source_profile && !settings.contains_key("spiderX") => {
            // Xray defaults spiderX to "/" and may crawl a decoy site after
            // authentication fails. Native Swirl authenticates or closes; its
            // executable proxy path does not include that fallback behavior.
            // Explicit crawler options remain unsupported above. This scoped
            // difference must be visible even when no source field supplied it.
            push(diagnostics, "RealityNativeAuthenticationOnly", path, "info");
        }
        Ok(()) => (),
    }
    Some(reality)
}

fn tcp(settings: &Value, path: &str, diagnostics: &mut Sink) {
    let Some(settings) = object(settings, path, diagnostics) else {
        return;
    };
    for (key, value) in settings {
        let path = key_path(path, key);
        match key.as_str() {
            "acceptProxyProtocol" => disabled_bool(
                value,
                &path,
                "InboundProxyProtocolOptionUnsupported",
                diagnostics,
            ),
            "header" => {
                let Some(header) = object(value, &path, diagnostics) else {
                    continue;
                };
                if let Some(kind) = string(header, "type", &path, diagnostics) {
                    if kind != "none" {
                        push(
                            diagnostics,
                            "TcpHeaderUnsupported",
                            &key_path(&path, "type"),
                            "unsupported",
                        );
                    }
                } else {
                    push(
                        diagnostics,
                        "MissingTcpHeaderType",
                        &key_path(&path, "type"),
                        "error",
                    );
                }
                for key in header.keys().filter(|key| key.as_str() != "type") {
                    push(
                        diagnostics,
                        "TcpHeaderOptionUnsupported",
                        &key_path(&path, key),
                        "unsupported",
                    );
                }
            }
            _ => diagnostics.unknown("TcpOptionUnsupported", &path),
        }
    }
}

fn websocket(
    settings: &Value,
    tls: Option<&Tls>,
    address: &str,
    port: u16,
    path: &str,
    diagnostics: &mut Sink,
) -> Option<WebSocket> {
    let settings = object(settings, path, diagnostics)?;
    for (key, value) in settings {
        let path = key_path(path, key);
        match key.as_str() {
            "host" | "path" | "headers" => (),
            "acceptProxyProtocol" => disabled_bool(
                value,
                &path,
                "InboundProxyProtocolOptionUnsupported",
                diagnostics,
            ),
            "useBrowserForwarding" | "parseXForwardedFor" => {
                disabled_bool(value, &path, "WebSocketOptionUnsupported", diagnostics)
            }
            "maxEarlyData" | "heartbeatPeriod" => match value.as_u64() {
                Some(0) => (),
                Some(value)
                    if value
                        <= if key == "maxEarlyData" {
                            i32::MAX as u64
                        } else {
                            u32::MAX as u64
                        } =>
                {
                    push(
                        diagnostics,
                        "WebSocketOptionUnsupported",
                        &path,
                        "unsupported",
                    )
                }
                _ => push(diagnostics, "WebSocketOptionRange", &path, "error"),
            },
            "earlyDataHeaderName" => {
                empty_string(value, &path, "WebSocketEarlyDataUnsupported", diagnostics)
            }
            _ => diagnostics.unknown("WebSocketOptionUnsupported", &path),
        }
    }
    let explicit_host = string(settings, "host", path, diagnostics).unwrap_or("");
    let mut header_host = None;
    if let Some(headers) = settings.get("headers")
        && let Some(headers) = object(headers, &key_path(path, "headers"), diagnostics)
    {
        for (key, value) in headers {
            let header_path = key_path(&key_path(path, "headers"), key);
            let Some(value) = value.as_str() else {
                push(diagnostics, "ExpectedString", &header_path, "error");
                continue;
            };
            if value.chars().any(|c| matches!(c, '\r' | '\n' | '\0')) {
                push(diagnostics, "WebSocketHeaderValue", &header_path, "error");
            }
            if key.eq_ignore_ascii_case("host") {
                if header_host.replace(value).is_some() {
                    push(diagnostics, "WebSocketHostDuplicate", &header_path, "error");
                }
            } else {
                push(
                    diagnostics,
                    "WebSocketHeaderUnsupported",
                    &header_path,
                    "unsupported",
                );
            }
        }
    }
    if !explicit_host.is_empty() && header_host.is_some_and(|host| host != explicit_host) {
        push(
            diagnostics,
            "WebSocketHostAliasConflict",
            &key_path(path, "host"),
            "error",
        );
    }
    let declared_host = if explicit_host.is_empty() {
        header_host.unwrap_or("")
    } else {
        explicit_host
    };
    let declared_path = string(settings, "path", path, diagnostics).unwrap_or("");
    if declared_host.len() > 270 || address.len() > 253 || declared_path.len() > 2048 {
        push(diagnostics, "WebSocketParameters", path, "unsupported");
        return None;
    }
    let host = if declared_host.is_empty() {
        // Xray uses SNI then address without port; V2Ray uses address and the
        // nondefault port. Shared JSON cannot safely choose between them.
        let default_port = if tls.is_some() { 443 } else { 80 };
        if port != default_port || tls.is_some_and(|tls| tls.server_name != address) {
            push(
                diagnostics,
                "WebSocketHostDefaultAmbiguous",
                &key_path(path, "host"),
                "unsupported",
            );
        }
        if address.contains(':') {
            format!("[{address}]")
        } else {
            address.to_owned()
        }
    } else {
        declared_host.to_owned()
    };
    let ws_path = if declared_path.starts_with('/') {
        declared_path.to_owned()
    } else {
        format!("/{declared_path}")
    };
    if ws_path.split_once('?').is_some_and(|(_, query)| {
        url::form_urlencoded::parse(query.as_bytes())
            .any(|(key, value)| key == "ed" && !value.is_empty())
    }) {
        push(
            diagnostics,
            "WebSocketEarlyDataUnsupported",
            &key_path(path, "path"),
            "unsupported",
        );
    }
    let websocket = WebSocket {
        host,
        path: ws_path,
    };
    if let Err(code) = websocket.validate_tls(tls) {
        push(diagnostics, code, path, "unsupported");
    }
    Some(websocket)
}

fn map_stream(
    stream: &Value,
    protocol: &str,
    address: &str,
    port: u16,
    flow: Option<&str>,
    path: &str,
    diagnostics: &mut Sink,
) -> StreamMapping {
    let empty = Map::new();
    let stream = if stream.is_null() {
        &empty
    } else {
        object(stream, path, diagnostics).unwrap_or(&empty)
    };
    let declared_network = string(stream, "network", path, diagnostics).unwrap_or("tcp");
    let declared_method = string(stream, "method", path, diagnostics);
    // Reject oversized selectors before case folding or alias comparison.
    fn bounded(value: &str) -> &str {
        if value.len() <= 64 {
            value
        } else {
            "unsupported"
        }
    }
    if declared_network.len() > 64 || declared_method.is_some_and(|method| method.len() > 64) {
        push(diagnostics, "StreamNameSizeLimit", path, "error");
    }
    let network = bounded(declared_network);
    let method = declared_method.map(bounded);
    if let Some(method) = method
        && stream.contains_key("network")
        && network_name(method) != network_name(network)
    {
        push(
            diagnostics,
            "TransportAliasConflict",
            &key_path(path, "method"),
            "error",
        );
    }
    let network = network_name(method.unwrap_or(network));
    let security = string(stream, "security", path, diagnostics).unwrap_or("none");
    let security = if security.len() <= 64 {
        security.to_ascii_lowercase()
    } else {
        push(
            diagnostics,
            "StreamNameSizeLimit",
            &key_path(path, "security"),
            "error",
        );
        "unsupported".into()
    };
    let security = if security.is_empty() {
        "none".into()
    } else {
        security
    };
    let mut mapping = StreamMapping {
        network,
        security,
        tls: None,
        reality: None,
        websocket: None,
    };
    if !matches!(mapping.network.as_str(), "tcp" | "ws") {
        push(
            diagnostics,
            "TransportUnsupported",
            &key_path(path, "network"),
            "unsupported",
        );
    }
    if stream.contains_key("tlsSettings") && stream.contains_key("realitySettings") {
        push(diagnostics, "TlsRealityConflict", path, "error");
    }
    for (key, value) in stream {
        let field_path = key_path(path, key);
        match key.as_str() {
            "network" | "method" | "security" => (),
            "tlsSettings" if mapping.security == "tls" => (),
            "realitySettings" if mapping.security == "reality" => (),
            "tcpSettings" | "rawSettings" if mapping.network == "tcp" => (),
            "wsSettings" if mapping.network == "ws" => (),
            "sockopt" if value.as_object().is_some_and(Map::is_empty) => (),
            "tlsSettings"
            | "realitySettings"
            | "tcpSettings"
            | "rawSettings"
            | "wsSettings"
            | "grpcSettings"
            | "gunSettings"
            | "httpSettings"
            | "httpupgradeSettings"
            | "xhttpSettings"
            | "splithttpSettings"
            | "kcpSettings"
            | "quicSettings"
            | "dsSettings" => {
                push(
                    diagnostics,
                    "UnappliedStreamSettingsPreserved",
                    &field_path,
                    if value.as_object().is_some_and(Map::is_empty) {
                        "info"
                    } else {
                        "unsupported"
                    },
                );
            }
            _ => push(
                diagnostics,
                "StreamOptionUnsupported",
                &field_path,
                "unsupported",
            ),
        }
    }
    let empty_value = Value::Object(Map::new());
    match mapping.security.as_str() {
        "none" => (),
        "tls" => {
            mapping.tls = tls(
                stream.get("tlsSettings").unwrap_or(&empty_value),
                &mapping.network,
                protocol,
                address,
                &key_path(path, "tlsSettings"),
                diagnostics,
            )
        }
        "reality" => {
            if !matches!(mapping.network.as_str(), "tcp" | "grpc" | "xhttp") {
                push(
                    diagnostics,
                    "RealityTransportConflict",
                    &key_path(path, "network"),
                    "error",
                );
            } else if mapping.network != "tcp" {
                push(
                    diagnostics,
                    "RealityTransportUnsupported",
                    &key_path(path, "network"),
                    "unsupported",
                );
            }
            if protocol != "vless" {
                push(
                    diagnostics,
                    "RealityProtocolUnsupported",
                    path,
                    "unsupported",
                );
            }
            if let Some(settings) = stream.get("realitySettings") {
                mapping.reality = reality(
                    settings,
                    address,
                    &key_path(path, "realitySettings"),
                    diagnostics,
                );
            } else {
                push(
                    diagnostics,
                    "MissingRealitySettings",
                    &key_path(path, "realitySettings"),
                    "error",
                );
            }
        }
        _ => push(
            diagnostics,
            "SecurityUnsupported",
            &key_path(path, "security"),
            "unsupported",
        ),
    }
    if mapping.network == "tcp" {
        if let (Some(raw), Some(tcp)) = (stream.get("rawSettings"), stream.get("tcpSettings"))
            && raw != tcp
        {
            push(diagnostics, "TcpRawAliasConflict", path, "error");
        }
        for key in ["rawSettings", "tcpSettings"] {
            if let Some(settings) = stream.get(key) {
                tcp(settings, &key_path(path, key), diagnostics);
            }
        }
    } else if mapping.network == "ws" {
        if !matches!(protocol, "vless" | "vmess" | "trojan") {
            push(
                diagnostics,
                "ProtocolWebSocketUnsupported",
                path,
                "unsupported",
            );
        }
        mapping.websocket = websocket(
            stream.get("wsSettings").unwrap_or(&empty_value),
            mapping.tls.as_ref(),
            address,
            port,
            &key_path(path, "wsSettings"),
            diagnostics,
        );
    }
    if let Some(flow) = flow.filter(|flow| !flow.is_empty()) {
        if protocol != "vless" || !matches!(flow, "xtls-rprx-vision" | "xtls-rprx-vision-udp443") {
            push(diagnostics, "VisionFlowUnsupported", path, "unsupported");
        }
        if mapping.security == "none" || mapping.network != "tcp" {
            push(
                diagnostics,
                "VisionSecurityTransportUnsupported",
                path,
                "unsupported",
            );
        } else if mapping.security != "reality" || flow != "xtls-rprx-vision" {
            push(
                diagnostics,
                "VisionCombinationUnsupported",
                path,
                "unsupported",
            );
        }
    }
    mapping
}
