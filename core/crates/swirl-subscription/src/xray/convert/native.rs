//! Native projection uses the real Swirl IR and its authoritative validator.
//! It produces one explicitly selected TCP outbound, never a network verdict.
use super::super::security::SecurityMapping;
use super::*;
use crate::{Config, Credentials, Node, Outbound};

fn blocked(sink: &Sink) -> bool {
    sink.issues
        .iter()
        .any(|d| matches!(d.severity.as_str(), "error" | "unsupported"))
}

fn reject(sink: &mut Sink, code: &str, path: &str) -> Option<Outbound> {
    sink.unsupported(code, path);
    None
}

pub(super) fn candidate_config(outbound: Outbound, listen: std::net::SocketAddr) -> Config {
    Config {
        schema: 1,
        listen,
        selected: "xray_selected".into(),
        nodes: vec![Node {
            id: "xray_selected".into(),
            outbound,
        }],
        rules: Vec::new(),
        smart_routing: false,
        selectors: Vec::new(),
        dns: crate::Dns::default(),
        china_rules_directory: None,
        inbound_auth: None,
        limits: crate::Limits::default(),
    }
}

pub(super) fn adapt(
    raw: &Value,
    protocol: Protocol,
    endpoint: Option<&Endpoint>,
    authentication: &Authentication,
    source: &NodeSource,
    mapping: &SecurityMapping,
    sink: &mut Sink,
) -> Option<Outbound> {
    if blocked(sink) {
        return None;
    }
    let endpoint = endpoint?;
    let path = &source.outbound_path;
    // Never infer a missing layer from a port, and never flatten a transport.
    if !matches!(mapping.transport, Transport::Tcp | Transport::WebSocket)
        && mapping.stream_transport.is_none()
    {
        return reject(
            sink,
            "NativeTransportUnsupported",
            &key_path(path, "streamSettings"),
        );
    }
    if !matches!(
        mapping.security,
        Security::None | Security::Tls | Security::Reality
    ) {
        return reject(
            sink,
            "NativeSecurityUnsupported",
            &key_path(path, "streamSettings"),
        );
    }
    if (mapping.security == Security::Tls && mapping.tls.is_none())
        || (mapping.security == Security::Reality && mapping.reality.is_none())
        || (mapping.transport == Transport::WebSocket && mapping.websocket.is_none())
        || (mapping.security != Security::Tls && mapping.tls.is_some())
        || (mapping.security != Security::Reality && mapping.reality.is_some())
        || (mapping.transport != Transport::WebSocket && mapping.websocket.is_some())
    {
        return reject(
            sink,
            "NativeLayerMappingIncomplete",
            &key_path(path, "streamSettings"),
        );
    }
    let host = endpoint.address.clone();
    let port = endpoint.port;
    let native = match (protocol, authentication) {
        (
            Protocol::Vless,
            Authentication::Vless {
                id: Some(uuid),
                encryption: Some(encryption),
                flow,
                ..
            },
        ) if encryption == "none" => Outbound::Vless {
            host,
            port,
            uuid: uuid.clone(),
            tls: mapping.tls.clone(),
            reality: mapping.reality.clone(),
            websocket: mapping.websocket.clone(),
            flow: flow.clone(),
            transport: mapping.stream_transport.clone(),
            udp: false,
        },
        (
            Protocol::Trojan,
            Authentication::Password {
                password: Some(password),
                ..
            },
        ) => {
            let Some(tls) = mapping.tls.clone() else {
                return reject(
                    sink,
                    "NativeTrojanRequiresTls",
                    &key_path(path, "streamSettings"),
                );
            };
            if mapping.security != Security::Tls || mapping.reality.is_some() {
                return reject(
                    sink,
                    "NativeTrojanSecurityUnsupported",
                    &key_path(path, "streamSettings"),
                );
            }
            Outbound::Trojan {
                host,
                port,
                password: password.clone(),
                tls,
                websocket: mapping.websocket.clone(),
                transport: mapping.stream_transport.clone(),
                udp: false,
            }
        }
        (
            Protocol::Shadowsocks,
            Authentication::Password {
                password: Some(password),
                method: Some(cipher),
                ..
            },
        ) => {
            if mapping.transport != Transport::Tcp || mapping.security != Security::None {
                return reject(
                    sink,
                    "NativeShadowsocksLayersUnsupported",
                    &key_path(path, "streamSettings"),
                );
            }
            Outbound::Shadowsocks {
                host,
                port,
                password: password.clone(),
                cipher: cipher.clone(),
                udp: false,
                obfs_http: None,
            }
        }
        (Protocol::Socks | Protocol::Http, auth) => {
            if mapping.transport != Transport::Tcp || mapping.security == Security::Reality {
                return reject(
                    sink,
                    "NativeProxyLayersUnsupported",
                    &key_path(path, "streamSettings"),
                );
            }
            let version = raw
                .pointer("/settings/version")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_ascii_lowercase();
            if protocol == Protocol::Socks && matches!(version.as_str(), "4" | "4a") {
                if mapping.security != Security::None {
                    return reject(
                        sink,
                        "NativeSocks4TlsUnsupported",
                        &key_path(path, "streamSettings"),
                    );
                }
                let user_id = match auth {
                    Authentication::None => String::new(),
                    Authentication::UserPassword { user, pass, .. }
                        if pass.as_ref().is_none_or(String::is_empty) =>
                    {
                        user.clone().unwrap_or_default()
                    }
                    _ => {
                        return reject(
                            sink,
                            "NativeAuthenticationUnsupported",
                            &source.server_path,
                        );
                    }
                };
                Outbound::Socks4 {
                    host,
                    port,
                    user_id,
                    remote_dns: version == "4a",
                }
            } else {
                if protocol == Protocol::Socks && !matches!(version.as_str(), "" | "5") {
                    return reject(
                        sink,
                        "NativeSocksVersionUnsupported",
                        &key_path(&key_path(path, "settings"), "version"),
                    );
                }
                let auth = match auth {
                    Authentication::None => None,
                    Authentication::UserPassword {
                        user: Some(user),
                        pass: Some(pass),
                        ..
                    } => Some(Credentials {
                        username: user.clone(),
                        password: pass.clone(),
                    }),
                    _ => {
                        return reject(
                            sink,
                            "NativeAuthenticationUnsupported",
                            &source.server_path,
                        );
                    }
                };
                if protocol == Protocol::Socks {
                    Outbound::Socks5 {
                        host,
                        port,
                        auth,
                        tls: mapping.tls.clone(),
                        udp: false,
                    }
                } else {
                    Outbound::HttpConnect {
                        host,
                        port,
                        auth,
                        tls: mapping.tls.clone(),
                    }
                }
            }
        }
        (
            Protocol::Vmess,
            Authentication::Vmess {
                id: Some(uuid),
                alter_id,
                security,
                ..
            },
        ) => {
            if mapping.reality.is_some() || mapping.security == Security::Reality {
                return reject(
                    sink,
                    "VmessRealityUnsupported",
                    &key_path(path, "streamSettings"),
                );
            }
            Outbound::Vmess {
                host,
                port,
                uuid: uuid.clone(),
                alter_id: u32::from(alter_id.unwrap_or(0)),
                security: security
                    .clone()
                    .filter(|s| !s.is_empty())
                    .unwrap_or_else(|| "auto".into()),
                tls: mapping.tls.clone(),
                websocket: mapping.websocket.clone(),
            }
        }
        _ => {
            return reject(
                sink,
                "NativeProtocolMappingUnavailable",
                &key_path(path, "protocol"),
            );
        }
    };
    // The same validation used by the Core/Qt FFI boundary is authoritative.
    // No source strings are interpolated into a diagnostic code or path.
    if let Err(code) = candidate_config(native.clone(), ([127, 0, 0, 1], 0).into()).validate() {
        return reject(sink, code, path);
    }
    Some(native)
}
