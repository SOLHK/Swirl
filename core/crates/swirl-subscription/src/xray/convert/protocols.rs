//! Protocol semantics only; never changes credentials or encryption methods.
use super::*;

pub(super) fn validate(
    outbound: &Value,
    protocol: Protocol,
    server: &Value,
    user: Option<&Value>,
    source: &NodeSource,
    sink: &mut Sink,
) -> Authentication {
    let path = source.user_path.as_deref().unwrap_or(&source.server_path);
    let user = user.unwrap_or(&Value::Null);
    let settings_path = key_path(&source.outbound_path, "settings");
    allow_keys(
        outbound,
        &source.outbound_path,
        &["protocol", "tag", "settings", "streamSettings", "mux"],
        sink,
    );
    match protocol {
        Protocol::Vless | Protocol::Vmess => {
            let fields: &[&str] = if protocol == Protocol::Vless {
                &["id", "encryption", "flow", "level", "email"]
            } else {
                &["id", "alterId", "security", "level", "email"]
            };
            if source.server_index.is_some() {
                allow_keys(&outbound["settings"], &settings_path, &["vnext"], sink);
                allow_keys(
                    server,
                    &source.server_path,
                    &["address", "port", "users"],
                    sink,
                );
                allow_keys(user, path, fields, sink);
            } else {
                let mut flat = fields.to_vec();
                flat.extend(["address", "port"]);
                allow_keys(server, &source.server_path, &flat, sink);
            }
            validate_id(user, path, sink);
            if level(user).is_some_and(|v| v != 0) {
                sink.unsupported("UserLevelPolicyUnsupported", &key_path(path, "level"));
            }
            if protocol == Protocol::Vless {
                match user.get("encryption").and_then(Value::as_str) {
                    Some("none") => (),
                    Some("") | None => {
                        sink.error("MissingVlessEncryption", &key_path(path, "encryption"))
                    }
                    _ => sink.unknown("VlessEncryptionUnsupported", &key_path(path, "encryption")),
                }
                Authentication::Vless {
                    id: string(user, "id"),
                    encryption: string(user, "encryption"),
                    flow: string(user, "flow"),
                    level: level(user),
                    email: string(user, "email"),
                }
            } else {
                if let Some(cipher) = user.get("security").and_then(Value::as_str)
                    && ![
                        "",
                        "auto",
                        "aes-128-gcm",
                        "chacha20-poly1305",
                        "none",
                        "zero",
                    ]
                    .contains(&cipher)
                {
                    sink.unknown("VmessCipherUnsupported", &key_path(path, "security"));
                }
                let alter_id = user
                    .get("alterId")
                    .and_then(Value::as_u64)
                    .and_then(|n| u16::try_from(n).ok());
                if alter_id.is_some_and(|n| n != 0) {
                    sink.unsupported("VmessLegacyAlterIdUnsupported", &key_path(path, "alterId"));
                }
                if matches!(
                    user.get("security").and_then(Value::as_str),
                    Some("none" | "zero")
                ) {
                    sink.unsupported("VmessSecurityUnsupported", &key_path(path, "security"));
                }
                Authentication::Vmess {
                    id: string(user, "id"),
                    alter_id,
                    security: string(user, "security"),
                    level: level(user),
                    email: string(user, "email"),
                }
            }
        }
        Protocol::Socks | Protocol::Http => super::auth::validate(
            outbound,
            protocol,
            server,
            (!user.is_null()).then_some(user),
            source,
            sink,
        ),
        Protocol::Trojan | Protocol::Shadowsocks => {
            password(outbound, protocol, server, source, sink)
        }
        _ => {
            sink.unknown(
                "ProtocolConversionUnsupported",
                &key_path(&source.outbound_path, "protocol"),
            );
            Authentication::Unknown
        }
    }
}

fn password(
    outbound: &Value,
    protocol: Protocol,
    server: &Value,
    source: &NodeSource,
    sink: &mut Sink,
) -> Authentication {
    if source.server_index.is_some() {
        allow_keys(
            &outbound["settings"],
            &key_path(&source.outbound_path, "settings"),
            &["servers"],
            sink,
        );
    }
    let fields: &[&str] = if protocol == Protocol::Trojan {
        &["address", "port", "password", "level", "email", "flow"]
    } else {
        &[
            "address", "port", "password", "level", "email", "method", "ivCheck", "ota",
        ]
    };
    allow_keys(server, &source.server_path, fields, sink);
    let password = string(server, "password");
    if password.as_ref().is_none_or(String::is_empty) {
        sink.error(
            "MissingPassword",
            &key_path(&source.server_path, "password"),
        );
    }
    // The native bound is not a reason to truncate a valid source password.
    if password.as_ref().is_some_and(|p| p.len() > 1024) {
        sink.unsupported(
            "NativePasswordLengthUnsupported",
            &key_path(&source.server_path, "password"),
        );
    }
    if let Some(level) = level(server) {
        if level > u32::from(u8::MAX) {
            sink.error(
                "UserLevelOutOfRange",
                &key_path(&source.server_path, "level"),
            );
        } else if level != 0 {
            sink.unsupported(
                "UserLevelPolicyUnsupported",
                &key_path(&source.server_path, "level"),
            );
        }
    }
    if protocol == Protocol::Trojan {
        if server
            .get("flow")
            .and_then(Value::as_str)
            .is_some_and(|v| !v.is_empty())
        {
            sink.error("TrojanFlowRemoved", &key_path(&source.server_path, "flow"));
        }
    } else {
        // V2Ray's official outbound extensions are booleans. Preserve both
        // values, but never claim the native connector applied an IV-check or
        // legacy OTA policy which is absent from Swirl's current IR.
        // In particular, explicit ivCheck=false cannot disable the native
        // connector's mandatory replay window. Do not weaken Core to import it.
        for (key, code) in [
            ("ivCheck", "ShadowsocksIvCheckUnsupported"),
            ("ota", "ShadowsocksOtaUnsupported"),
        ] {
            match server.get(key) {
                None => (),
                Some(Value::Bool(false)) if key == "ota" => (),
                Some(Value::Bool(_)) => {
                    sink.unsupported(code, &key_path(&source.server_path, key));
                }
                Some(_) => sink.error("ExpectedBoolean", &key_path(&source.server_path, key)),
            }
        }
        match server.get("method").and_then(Value::as_str) {
            None | Some("") => sink.error(
                "MissingShadowsocksMethod",
                &key_path(&source.server_path, "method"),
            ),
            Some("aes-128-gcm" | "aes-256-gcm" | "chacha20-ietf-poly1305") => (),
            Some(
                "2022-blake3-aes-128-gcm"
                | "2022-blake3-aes-256-gcm"
                | "2022-blake3-chacha20-poly1305"
                | "chacha20-poly1305"
                | "none"
                | "plain"
                | "aes-128-cfb"
                | "aes-256-cfb"
                | "chacha20"
                | "chacha20-ietf"
                | "aead_aes_128_gcm"
                | "aead_aes_256_gcm"
                | "aead_chacha20_poly1305"
                | "xchacha20-poly1305"
                | "xchacha20-ietf-poly1305"
                | "aead_xchacha20_poly1305",
            ) => {
                sink.unsupported(
                    "ShadowsocksCipherUnsupported",
                    &key_path(&source.server_path, "method"),
                );
            }
            _ => sink.unknown(
                "ShadowsocksCipherUnverified",
                &key_path(&source.server_path, "method"),
            ),
        }
    }
    Authentication::Password {
        password,
        method: string(server, "method"),
        level: level(server),
        email: string(server, "email"),
    }
}
