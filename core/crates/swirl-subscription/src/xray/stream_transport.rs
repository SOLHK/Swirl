//! Strict source-to-native mappings for transports already implemented in the
//! Rust runtime. Unrepresented controls remain blocking diagnostics.
use super::{convert::Sink, strict::key_path};
use crate::{
    StreamTransport, Tls,
    stream_transport::{GrpcConfig, GrpcMode, HttpConfig, XHttpConfig},
};
use serde_json::{Map, Value};

fn text<'a>(
    object: &'a Map<String, Value>,
    key: &str,
    fallback: &'a str,
) -> Result<&'a str, &'static str> {
    object.get(key).map_or(Ok(fallback), |v| {
        v.as_str().ok_or("TransportExpectedString")
    })
}

fn headers(value: Option<&Value>, arrays: bool) -> Result<Vec<(String, String)>, &'static str> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let map = value.as_object().ok_or("TransportHeaders")?;
    if map.len() > 64 {
        return Err("TransportHeaderLimit");
    }
    let mut output = Vec::new();
    for (name, value) in map {
        let values = match value {
            Value::String(value) => vec![value.as_str()],
            Value::Array(values) if arrays => values
                .iter()
                .map(|v| v.as_str().ok_or("TransportHeaders"))
                .collect::<Result<Vec<_>, _>>()?,
            _ => return Err("TransportHeaders"),
        };
        for value in values {
            if output.len() >= 64 || name.len() + value.len() > 12 * 1024 {
                return Err("TransportHeaderLimit");
            }
            output.push((name.clone(), value.into()));
        }
    }
    Ok(output)
}

fn build(
    stream: &Map<String, Value>,
    network: &str,
    tls: Option<&Tls>,
    address: &str,
    port: u16,
) -> Result<StreamTransport, &'static str> {
    let keys: &[&str] = match network {
        "grpc" => &["grpcSettings", "gunSettings"],
        "h2" => &["httpSettings"],
        "httpupgrade" => &["httpupgradeSettings"],
        "xhttp" => &["xhttpSettings", "splithttpSettings"],
        _ => return Err("TransportUnsupported"),
    };
    if keys.len() == 2
        && stream.contains_key(keys[0])
        && stream.contains_key(keys[1])
        && stream[keys[0]] != stream[keys[1]]
    {
        return Err("TransportSettingsAliasConflict");
    }
    let empty = Map::new();
    let options = keys
        .iter()
        .find_map(|key| stream.get(*key))
        .map_or(Ok(&empty), |v| {
            v.as_object().ok_or("TransportSettingsObject")
        })?;
    let endpoint = if address.contains(':') {
        format!("[{address}]:{port}")
    } else {
        format!("{address}:{port}")
    };
    let name = tls.map(|tls| tls.server_name.as_str()).unwrap_or(address);
    let name = if name.contains(':') {
        format!("[{name}]")
    } else {
        name.to_owned()
    };
    for (key, value) in options {
        let supported = match network {
            "grpc" => {
                matches!(
                    key.as_str(),
                    "authority" | "serviceName" | "multiMode" | "user_agent"
                ) || (matches!(
                    key.as_str(),
                    "idle_timeout" | "health_check_timeout" | "initial_windows_size"
                ) && value.as_i64() == Some(0))
                    || (key == "permit_without_stream" && value.as_bool() == Some(false))
            }
            "h2" => {
                matches!(key.as_str(), "host" | "path" | "headers")
                    || (matches!(key.as_str(), "read_idle_timeout" | "health_check_timeout")
                        && value.as_i64() == Some(0))
            }
            "httpupgrade" => {
                matches!(key.as_str(), "host" | "path" | "headers")
                    || (key == "acceptProxyProtocol" && value.as_bool() == Some(false))
            }
            "xhttp" => matches!(key.as_str(), "host" | "path" | "mode" | "headers"),
            _ => false,
        };
        if !supported {
            return Err("TransportOptionUnsupported");
        }
    }
    let result = match network {
        "grpc" => {
            let authority = text(options, "authority", "")?;
            let fallback = if tls.is_some() || address.parse::<std::net::IpAddr>().is_err() {
                &name
            } else {
                &endpoint
            };
            let mut headers = Vec::new();
            if let Some(value) = options.get("user_agent") {
                let value = value.as_str().ok_or("TransportExpectedString")?;
                if !value.is_empty() {
                    headers.push(("user-agent".into(), value.into()));
                }
            }
            let multi = options
                .get("multiMode")
                .map_or(Ok(false), |v| v.as_bool().ok_or("TransportExpectedBoolean"))?;
            StreamTransport::Grpc {
                config: GrpcConfig {
                    authority: if authority.is_empty() {
                        fallback.to_owned()
                    } else {
                        authority.into()
                    },
                    service_name: text(options, "serviceName", "")?.into(),
                    mode: if multi {
                        GrpcMode::TunMulti
                    } else {
                        GrpcMode::Tun
                    },
                    headers,
                },
            }
        }
        "h2" => {
            let host = match options.get("host") {
                None => "www.example.com",
                Some(Value::Array(values)) if values.is_empty() => "www.example.com",
                Some(Value::Array(values)) if values.len() == 1 => {
                    values[0].as_str().ok_or("Http2Host")?
                }
                Some(Value::Array(_)) => return Err("Http2MultipleHostsUnsupported"),
                // The pinned legacy Xray schema is a string-list, not an URI.
                _ => return Err("Http2Host"),
            };
            StreamTransport::Http2 {
                config: HttpConfig {
                    host: host.into(),
                    path: text(options, "path", "/")?.into(),
                    headers: headers(options.get("headers"), true)?,
                },
            }
        }
        "httpupgrade" => {
            let host = text(options, "host", "")?;
            StreamTransport::HttpUpgrade {
                config: HttpConfig {
                    host: if host.is_empty() {
                        name.clone()
                    } else {
                        host.into()
                    },
                    path: text(options, "path", "/")?.into(),
                    headers: headers(options.get("headers"), false)?,
                },
            }
        }
        "xhttp" => {
            let mode = text(options, "mode", "auto")?;
            if mode != "stream-one" {
                return Err("XHttpModeUnsupported");
            }
            let host = text(options, "host", "")?;
            StreamTransport::XHttp {
                config: XHttpConfig {
                    host: if host.is_empty() {
                        name.clone()
                    } else {
                        host.into()
                    },
                    path: text(options, "path", "/")?.into(),
                    headers: headers(options.get("headers"), false)?,
                    mode: mode.into(),
                },
            }
        }
        _ => return Err("TransportUnsupported"),
    };
    Ok(result)
}

pub(super) fn map(
    stream: &Map<String, Value>,
    network: &str,
    tls: Option<&Tls>,
    address: &str,
    port: u16,
    path: &str,
    sink: &mut Sink,
) -> Option<StreamTransport> {
    match build(stream, network, tls, address, port) {
        Ok(result) => Some(result),
        Err(code) => {
            sink.unsupported(
                code,
                &key_path(
                    path,
                    match network {
                        "grpc" => "grpcSettings",
                        "h2" => "httpSettings",
                        "httpupgrade" => "httpupgradeSettings",
                        _ => "xhttpSettings",
                    },
                ),
            );
            None
        }
    }
}
