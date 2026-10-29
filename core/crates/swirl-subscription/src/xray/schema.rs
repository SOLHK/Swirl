//! Structural checks for the shared Xray/V2Ray envelopes. These deliberately
//! do not select endpoints, merge aliases/defaults, validate credentials, or
//! decide whether Swirl can execute a protocol. Unknown fields remain data.
use super::{Diagnostic, diagnostic, strict::key_path};
use serde_json::{Map, Value};

#[derive(Clone, Copy)]
enum Kind {
    Object,
    String,
    Bool,
    U16,
    U32,
    I32,
    StringList,
    PortRange,
}

impl Kind {
    fn accepts(self, value: &Value) -> bool {
        match self {
            Self::Object => value.is_object(),
            Self::String => value.is_string(),
            Self::Bool => value.is_boolean(),
            Self::U16 => value.as_u64().is_some_and(|v| u16::try_from(v).is_ok()),
            Self::U32 => value.as_u64().is_some_and(|v| u32::try_from(v).is_ok()),
            Self::I32 => value.as_i64().is_some_and(|v| i32::try_from(v).is_ok()),
            // Upstream StringList accepts a string or an array of strings.
            // Preserve its original form here; splitting/normalizing is B work.
            Self::StringList => value.is_string() || value.is_array(),
            Self::PortRange => value.is_string() || Self::U16.accepts(value),
        }
    }

    fn code(self) -> &'static str {
        match self {
            Self::Object => "ExpectedObject",
            Self::String => "ExpectedString",
            Self::Bool => "ExpectedBoolean",
            Self::U16 => "ExpectedUnsigned16BitInteger",
            Self::U32 => "ExpectedUnsigned32BitInteger",
            Self::I32 => "ExpectedSigned32BitInteger",
            Self::StringList => "ExpectedStringOrStringArray",
            Self::PortRange => "ExpectedPortNumberOrRangeString",
        }
    }
}

fn fields(
    object: &Map<String, Value>,
    path: &str,
    types: &[(&str, Kind)],
) -> Result<(), Diagnostic> {
    for &(key, kind) in types {
        if let Some(value) = object.get(key) {
            let path = key_path(path, key);
            if !kind.accepts(value) {
                return Err(diagnostic(kind.code(), &path, "error"));
            }
            if matches!(kind, Kind::StringList)
                && let Some(values) = value.as_array()
            {
                for (index, item) in values.iter().enumerate() {
                    if !item.is_string() {
                        return Err(diagnostic(
                            "ExpectedString",
                            &format!("{path}[{index}]"),
                            "error",
                        ));
                    }
                }
            }
        }
    }
    Ok(())
}

fn object<'a>(value: &'a Value, path: &str) -> Result<&'a Map<String, Value>, Diagnostic> {
    value
        .as_object()
        .ok_or_else(|| diagnostic("ExpectedObject", path, "error"))
}

fn object_array(
    parent: &Map<String, Value>,
    key: &str,
    path: &str,
    check: impl Fn(&Map<String, Value>, &str) -> Result<(), Diagnostic>,
) -> Result<(), Diagnostic> {
    if let Some(value) = parent.get(key) {
        let path = key_path(path, key);
        let values = value
            .as_array()
            .ok_or_else(|| diagnostic("ExpectedArray", &path, "error"))?;
        for (index, item) in values.iter().enumerate() {
            let item_path = format!("{path}[{index}]");
            check(object(item, &item_path)?, &item_path)?;
        }
    }
    Ok(())
}

fn user(value: &Map<String, Value>, path: &str) -> Result<(), Diagnostic> {
    fields(
        value,
        path,
        &[
            ("id", Kind::String),
            ("password", Kind::String),
            ("user", Kind::String),
            ("pass", Kind::String),
            ("email", Kind::String),
            ("security", Kind::String),
            ("encryption", Kind::String),
            ("flow", Kind::String),
            ("level", Kind::U32),
            ("alterId", Kind::U16),
        ],
    )
}

fn endpoint(value: &Map<String, Value>, path: &str) -> Result<(), Diagnostic> {
    fields(
        value,
        path,
        &[
            ("address", Kind::String),
            ("port", Kind::U16),
            ("method", Kind::String),
            ("password", Kind::String),
            ("email", Kind::String),
            ("level", Kind::U32),
        ],
    )?;
    user(value, path)?;
    object_array(value, "users", path, user)
}

pub(super) fn outbound(value: &Value, path: &str) -> Result<(), Diagnostic> {
    let node = object(value, path)?;
    if node.contains_key("type") && !node.contains_key("protocol") {
        return Err(diagnostic("MixedOrUnsupportedJsonDialect", path, "error"));
    }
    let protocol_path = key_path(path, "protocol");
    let protocol = node
        .get("protocol")
        .ok_or_else(|| diagnostic("MissingProtocol", &protocol_path, "error"))?
        .as_str()
        .ok_or_else(|| diagnostic("ProtocolMustBeString", &protocol_path, "error"))?;
    if protocol.trim().is_empty() {
        return Err(diagnostic("EmptyProtocol", &protocol_path, "error"));
    }
    if ["listen", "port", "sniffing", "allocate"]
        .iter()
        .any(|key| node.contains_key(*key))
        || node
            .get("settings")
            .and_then(Value::as_object)
            .is_some_and(|settings| {
                settings.contains_key("clients") || settings.contains_key("accounts")
            })
    {
        return Err(diagnostic("InboundIsNotClientOutbound", path, "error"));
    }
    fields(
        node,
        path,
        &[
            ("tag", Kind::String),
            ("sendThrough", Kind::String),
            ("targetStrategy", Kind::String),
            ("domainStrategy", Kind::String),
            ("settings", Kind::Object),
            ("streamSettings", Kind::Object),
            ("mux", Kind::Object),
            ("proxySettings", Kind::Object),
        ],
    )?;
    if let Some(settings) = node.get("settings")
        && matches!(
            protocol,
            "vless" | "vmess" | "trojan" | "shadowsocks" | "socks" | "http"
        )
    {
        let settings_path = key_path(path, "settings");
        let settings = object(settings, &settings_path)?;
        // Legacy endpoint arrays and current Xray flat forms are both retained.
        endpoint(settings, &settings_path)?;
        object_array(settings, "vnext", &settings_path, endpoint)?;
        object_array(settings, "servers", &settings_path, endpoint)?;
    }
    if let Some(settings) = node.get("streamSettings") {
        stream(settings, &key_path(path, "streamSettings"))?;
    }
    if let Some(mux) = node.get("mux") {
        let path = key_path(path, "mux");
        fields(
            object(mux, &path)?,
            &path,
            &[
                ("enabled", Kind::Bool),
                ("concurrency", Kind::I32),
                ("xudpConcurrency", Kind::I32),
                ("xudpProxyUDP443", Kind::String),
            ],
        )?;
    }
    if let Some(proxy) = node.get("proxySettings") {
        let path = key_path(path, "proxySettings");
        fields(
            object(proxy, &path)?,
            &path,
            &[("tag", Kind::String), ("transportLayer", Kind::Bool)],
        )?;
    }
    Ok(())
}

pub(super) fn stream(value: &Value, path: &str) -> Result<(), Diagnostic> {
    let value = object(value, path)?;
    fields(
        value,
        path,
        &[
            ("network", Kind::String),
            ("security", Kind::String),
            // V2Ray v5 has a transport name here; root transport is an object.
            ("transport", Kind::String),
        ],
    )?;
    for key in [
        "tcpSettings",
        "rawSettings",
        "wsSettings",
        "grpcSettings",
        "gunSettings",
        "httpSettings",
        "httpupgradeSettings",
        "xhttpSettings",
        "splithttpSettings",
        "kcpSettings",
        "quicSettings",
        "dsSettings",
        "sockopt",
        "tlsSettings",
        "realitySettings",
        "transportSettings",
        "securitySettings",
        "socketSettings",
    ] {
        if let Some(settings) = value.get(key) {
            let path = key_path(path, key);
            let settings = object(settings, &path)?;
            match key {
                "grpcSettings" | "gunSettings" => fields(
                    settings,
                    &path,
                    &[
                        ("serviceName", Kind::String),
                        ("authority", Kind::String),
                        ("multiMode", Kind::Bool),
                        ("permit_without_stream", Kind::Bool),
                        ("parseXForwardedFor", Kind::Bool),
                        ("user_agent", Kind::String),
                        ("idle_timeout", Kind::I32),
                        ("health_check_timeout", Kind::I32),
                        ("initial_windows_size", Kind::I32),
                    ],
                )?,
                "wsSettings" | "httpupgradeSettings" => {
                    fields(
                        settings,
                        &path,
                        &[
                            ("path", Kind::String),
                            ("host", Kind::String),
                            ("headers", Kind::Object),
                            ("maxEarlyData", Kind::U32),
                            ("earlyDataHeaderName", Kind::String),
                            ("acceptProxyProtocol", Kind::Bool),
                        ],
                    )?;
                    headers(settings, &path, Kind::String)?;
                }
                "httpSettings" => {
                    fields(
                        settings,
                        &path,
                        &[
                            ("path", Kind::String),
                            ("host", Kind::StringList),
                            ("headers", Kind::Object),
                        ],
                    )?;
                    headers(settings, &path, Kind::StringList)?;
                }
                "tlsSettings" => tls(settings, &path)?,
                "realitySettings" => fields(
                    settings,
                    &path,
                    &[
                        ("serverName", Kind::String),
                        ("fingerprint", Kind::String),
                        ("publicKey", Kind::String),
                        ("password", Kind::String),
                        ("shortId", Kind::String),
                        ("spiderX", Kind::String),
                        ("show", Kind::Bool),
                        ("mldsa65Verify", Kind::String),
                    ],
                )?,
                "tcpSettings" | "rawSettings" => fields(
                    settings,
                    &path,
                    &[
                        ("header", Kind::Object),
                        ("acceptProxyProtocol", Kind::Bool),
                    ],
                )?,
                // These containers are recognized, but their protocol-specific
                // schemas/semantics are intentionally deferred to conversion.
                _ => (),
            }
        }
    }
    Ok(())
}

fn headers(settings: &Map<String, Value>, path: &str, kind: Kind) -> Result<(), Diagnostic> {
    if let Some(headers) = settings.get("headers") {
        let path = key_path(path, "headers");
        let headers = object(headers, &path)?;
        for key in headers.keys() {
            // Header names are untrusted. key_path masks arbitrary credentials.
            fields(headers, &path, &[(key, kind)])?;
        }
    }
    Ok(())
}

fn tls(value: &Map<String, Value>, path: &str) -> Result<(), Diagnostic> {
    fields(
        value,
        path,
        &[
            ("serverName", Kind::String),
            ("fingerprint", Kind::String),
            ("allowInsecure", Kind::Bool),
            ("disableSystemRoot", Kind::Bool),
            ("enableSessionResumption", Kind::Bool),
            ("rejectUnknownSni", Kind::Bool),
            ("alpn", Kind::StringList),
            ("minVersion", Kind::String),
            ("maxVersion", Kind::String),
            ("cipherSuites", Kind::String),
        ],
    )?;
    object_array(value, "certificates", path, |certificate, path| {
        fields(
            certificate,
            path,
            &[
                ("certificateFile", Kind::String),
                ("keyFile", Kind::String),
                ("usage", Kind::String),
            ],
        )?;
        for key in ["certificate", "key"] {
            if let Some(value) = certificate.get(key) {
                let path = key_path(path, key);
                let lines = value
                    .as_array()
                    .ok_or_else(|| diagnostic("ExpectedArray", &path, "error"))?;
                for (index, line) in lines.iter().enumerate() {
                    if !line.is_string() {
                        return Err(diagnostic(
                            "ExpectedString",
                            &format!("{path}[{index}]"),
                            "error",
                        ));
                    }
                }
            }
        }
        Ok(())
    })
}

/// Server settings are retained in their own direction. In particular, an
/// inbound port may be a string range; it is not an outbound uint16 endpoint.
pub(super) fn inbound(value: &Value, path: &str) -> Result<(), Diagnostic> {
    let value = object(value, path)?;
    fields(
        value,
        path,
        &[
            ("protocol", Kind::String),
            ("tag", Kind::String),
            ("listen", Kind::String),
            ("port", Kind::PortRange),
            ("settings", Kind::Object),
            ("streamSettings", Kind::Object),
            ("sniffing", Kind::Object),
            ("allocate", Kind::Object),
        ],
    )?;
    if let Some(stream_settings) = value.get("streamSettings") {
        stream(stream_settings, &key_path(path, "streamSettings"))?;
    }
    if let Some(sniffing) = value.get("sniffing") {
        let path = key_path(path, "sniffing");
        fields(
            object(sniffing, &path)?,
            &path,
            &[
                ("enabled", Kind::Bool),
                ("metadataOnly", Kind::Bool),
                ("routeOnly", Kind::Bool),
                ("destOverride", Kind::StringList),
                ("domainsExcluded", Kind::StringList),
                ("ipsExcluded", Kind::StringList),
            ],
        )?;
    }
    if let Some(allocate) = value.get("allocate") {
        let path = key_path(path, "allocate");
        fields(
            object(allocate, &path)?,
            &path,
            &[
                ("strategy", Kind::String),
                ("concurrency", Kind::U32),
                ("refresh", Kind::U32),
            ],
        )?;
    }
    Ok(())
}

pub(super) fn global(key: &str, value: &Value, path: &str) -> Result<(), Diagnostic> {
    let values = object(value, path)?;
    match key {
        "transport" => stream(value, path)?,
        "log" => fields(
            values,
            path,
            &[
                ("access", Kind::String),
                ("error", Kind::String),
                ("loglevel", Kind::String),
                ("dnsLog", Kind::Bool),
            ],
        )?,
        "dns" => {
            fields(values, path, &[("hosts", Kind::Object)])?;
            if let Some(hosts) = values.get("hosts") {
                let path = key_path(path, "hosts");
                let hosts = object(hosts, &path)?;
                for key in hosts.keys() {
                    fields(hosts, &path, &[(key, Kind::StringList)])?;
                }
            }
            if let Some(servers) = values.get("servers") {
                let path = key_path(path, "servers");
                let servers = servers
                    .as_array()
                    .ok_or_else(|| diagnostic("ExpectedArray", &path, "error"))?;
                for (index, server) in servers.iter().enumerate() {
                    let path = format!("{path}[{index}]");
                    if !server.is_string() {
                        fields(
                            object(server, &path)?,
                            &path,
                            &[
                                ("address", Kind::String),
                                ("port", Kind::U16),
                                ("clientIp", Kind::String),
                                ("tag", Kind::String),
                                ("queryStrategy", Kind::String),
                                ("skipFallback", Kind::Bool),
                                ("domains", Kind::StringList),
                            ],
                        )?;
                    }
                }
            }
        }
        "routing" => {
            fields(
                values,
                path,
                &[("domainStrategy", Kind::String), ("settings", Kind::Object)],
            )?;
            object_array(values, "rules", path, |_, _| Ok(()))?;
            object_array(values, "balancers", path, |_, _| Ok(()))?;
            if let Some(settings) = values.get("settings") {
                let path = key_path(path, "settings");
                let settings = object(settings, &path)?;
                fields(settings, &path, &[("domainStrategy", Kind::String)])?;
                object_array(settings, "rules", &path, |_, _| Ok(()))?;
            }
        }
        "policy" => {
            fields(
                values,
                path,
                &[("levels", Kind::Object), ("system", Kind::Object)],
            )?;
            if let Some(levels) = values.get("levels") {
                let path = key_path(path, "levels");
                for (key, level) in object(levels, &path)? {
                    let path = key_path(&path, key);
                    fields(
                        object(level, &path)?,
                        &path,
                        &[
                            ("handshake", Kind::U32),
                            ("connIdle", Kind::U32),
                            ("uplinkOnly", Kind::U32),
                            ("downlinkOnly", Kind::U32),
                            ("bufferSize", Kind::I32),
                            ("statsUserUplink", Kind::Bool),
                            ("statsUserDownlink", Kind::Bool),
                        ],
                    )?;
                }
            }
            if let Some(system) = values.get("system") {
                let path = key_path(path, "system");
                fields(
                    object(system, &path)?,
                    &path,
                    &[
                        ("statsInboundUplink", Kind::Bool),
                        ("statsInboundDownlink", Kind::Bool),
                        ("statsOutboundUplink", Kind::Bool),
                        ("statsOutboundDownlink", Kind::Bool),
                    ],
                )?;
            }
        }
        // Other globals are recognized containers, preserved but not applied.
        _ => (),
    }
    Ok(())
}
