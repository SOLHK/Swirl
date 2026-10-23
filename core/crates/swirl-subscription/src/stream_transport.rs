//! Persisted, typed transport options. They contain configuration only; all
//! networking remains in swirl-transport and swirl-protocol.
use crate::Outbound;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GrpcMode {
    #[default]
    Tun,
    TunMulti,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GrpcConfig {
    pub authority: String,
    pub service_name: String,
    #[serde(default)]
    pub mode: GrpcMode,
    #[serde(default)]
    pub headers: Vec<(String, String)>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HttpConfig {
    pub host: String,
    pub path: String,
    #[serde(default)]
    pub headers: Vec<(String, String)>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct XHttpConfig {
    pub host: String,
    pub path: String,
    pub mode: String,
    #[serde(default)]
    pub headers: Vec<(String, String)>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum StreamTransport {
    Grpc {
        config: GrpcConfig,
    },
    #[serde(rename = "http2")]
    Http2 {
        config: HttpConfig,
    },
    #[serde(rename = "httpupgrade")]
    HttpUpgrade {
        config: HttpConfig,
    },
    #[serde(rename = "xhttp")]
    XHttp {
        config: XHttpConfig,
    },
}

impl StreamTransport {
    pub fn validate_for(&self, outbound: &Outbound) -> Result<(), &'static str> {
        let (tls, reality, websocket, flow) = match outbound {
            Outbound::Vless {
                tls,
                reality,
                websocket,
                flow,
                ..
            } => (
                tls.as_ref(),
                reality.as_ref(),
                websocket.as_ref(),
                flow.as_deref(),
            ),
            Outbound::Trojan { tls, websocket, .. } => (Some(tls), None, websocket.as_ref(), None),
            _ => return Err("TransportProtocolUnsupported"),
        };
        if websocket.is_some() {
            return Err("TransportConflict");
        }
        if flow.is_some_and(|flow| !flow.is_empty()) {
            return Err("VisionTransportUnsupported");
        }
        if reality.is_some() && !matches!(self, Self::Grpc { .. } | Self::XHttp { .. }) {
            return Err("RealityTransportUnsupported");
        }
        let (host, path, headers) = match self {
            Self::Grpc { config } => {
                if config.service_name.starts_with('/') {
                    let (service, methods) = config
                        .service_name
                        .rsplit_once('/')
                        .ok_or("GrpcServiceName")?;
                    let mut methods = methods.split('|');
                    if service.is_empty()
                        || methods.any(str::is_empty)
                        || config.service_name.matches('|').count() > 1
                    {
                        return Err("GrpcServiceName");
                    }
                }
                (&config.authority, &config.service_name, &config.headers)
            }
            Self::Http2 { config } => {
                if tls.is_none() {
                    return Err("Http2TlsRequired");
                }
                (&config.host, &config.path, &config.headers)
            }
            Self::HttpUpgrade { config } => {
                if config.path.split_once('?').is_some_and(|(_, query)| {
                    url::form_urlencoded::parse(query.as_bytes()).any(|(key, _)| key == "ed")
                }) {
                    return Err("HttpUpgradeEarlyDataUnsupported");
                }
                (&config.host, &config.path, &config.headers)
            }
            Self::XHttp { config } => {
                if config.mode != "stream-one" {
                    return Err("XHttpModeUnsupported");
                }
                if config.path.split_once('?').is_some_and(|(_, query)| {
                    !query.is_ascii() || query.bytes().any(|b| b <= b' ' || b == 127 || b == b'#')
                }) {
                    return Err("XHttpQuery");
                }
                (&config.host, &config.path, &config.headers)
            }
        };
        if host.is_empty()
            || host.len() > 1024
            || !host.is_ascii()
            || host
                .bytes()
                .any(|b| b <= b' ' || b == 127 || b"/?#@\\".contains(&b))
        {
            return Err("TransportHost");
        }
        let authority = url::Url::parse(&format!("http://{host}/")).map_err(|_| "TransportHost")?;
        if authority.host_str().is_none()
            || !authority.username().is_empty()
            || authority.password().is_some()
        {
            return Err("TransportHost");
        }
        if path.len() > 4096 || path.chars().any(char::is_control) {
            return Err("TransportPath");
        }
        if headers.len() > 64 {
            return Err("TransportHeaderLimit");
        }
        let mut size = host.len() + path.len() * 3 + 1200;
        for (name, value) in headers {
            let parsed =
                http::HeaderName::from_bytes(name.as_bytes()).map_err(|_| "TransportHeaderName")?;
            http::HeaderValue::from_str(value).map_err(|_| "TransportHeaderValue")?;
            if matches!(
                parsed.as_str(),
                "host"
                    | "connection"
                    | "upgrade"
                    | "keep-alive"
                    | "proxy-connection"
                    | "transfer-encoding"
                    | "content-length"
                    | "content-type"
                    | "referer"
                    | "te"
                    | "trailer"
                    | "accept-encoding"
                    | "grpc-encoding"
                    | "grpc-accept-encoding"
                    | "grpc-status"
            ) || parsed.as_str().starts_with("sec-websocket-")
            {
                return Err("TransportReservedHeader");
            }
            size += name.len() + value.len() + 4;
        }
        if size > 12 * 1024 {
            return Err("TransportHeaderLimit");
        }
        let required = if matches!(self, Self::HttpUpgrade { .. }) {
            "http/1.1"
        } else {
            "h2"
        };
        if tls.is_some_and(|tls| {
            !tls.alpn.is_empty()
                && (if required == "http/1.1" {
                    tls.alpn != ["http/1.1"]
                } else {
                    !tls.alpn.iter().any(|p| p == required)
                })
        }) {
            return Err("TlsAlpnUnsupported");
        }
        if reality.is_some_and(|r| !r.alpn.is_empty() && !r.alpn.iter().any(|p| p == required)) {
            return Err("RealityAlpnUnsupported");
        }
        Ok(())
    }
}

impl Outbound {
    pub fn stream_transport(&self) -> Option<&StreamTransport> {
        match self {
            Self::Vless { transport, .. } | Self::Trojan { transport, .. } => transport.as_ref(),
            _ => None,
        }
    }
}
