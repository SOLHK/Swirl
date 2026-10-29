//! SOCKS and HTTP CONNECT account semantics. The source remains authoritative;
//! this projection neither selects the first account nor creates a runtime.
use super::*;

pub(super) fn validate(
    outbound: &Value,
    protocol: Protocol,
    server: &Value,
    user: Option<&Value>,
    source: &NodeSource,
    sink: &mut Sink,
) -> Authentication {
    let settings = &outbound["settings"];
    let settings_path = key_path(&source.outbound_path, "settings");
    let mut settings_fields = vec!["servers", "auth"];
    if protocol == Protocol::Socks {
        settings_fields.push("version");
    } else {
        settings_fields.push("headers");
        headers(settings, &settings_path, sink);
    }
    if source.server_index.is_none() {
        settings_fields.extend(["address", "port", "user", "pass", "level", "email", "users"]);
    } else {
        allow_keys(
            server,
            &source.server_path,
            &["address", "port", "users"],
            sink,
        );
    }
    allow_keys(settings, &settings_path, &settings_fields, sink);
    if let Some(value) = settings.get("auth") {
        // `auth` is an inbound selector. Outbound authentication comes from
        // the account itself; accepting this field could silently select noauth.
        if value.is_string() {
            sink.unsupported(
                "OutboundAuthMethodUnsupported",
                &key_path(&settings_path, "auth"),
            );
        } else {
            sink.error("ExpectedString", &key_path(&settings_path, "auth"));
        }
    }
    let version = if protocol == Protocol::Socks {
        socks_version(settings, &settings_path, sink)
    } else {
        "".into()
    };
    if source.server_index.is_none() && server.get("users").is_some() {
        if ["user", "pass"].iter().any(|key| server.get(key).is_some()) {
            sink.error("AmbiguousAuthenticationForms", &source.server_path);
        } else if server["users"]
            .as_array()
            .is_some_and(|users| !users.is_empty())
        {
            // Xray's direct form takes user/pass and would ignore this array.
            // Keep every member as a node but require explicit disambiguation.
            sink.unknown(
                "FlatUsersFormUnsupported",
                &key_path(&source.server_path, "users"),
            );
        }
    }
    let path = source.user_path.as_deref().unwrap_or(&source.server_path);
    let metadata = user.unwrap_or(server);
    if level(metadata).is_some_and(|value| value != 0) {
        sink.unsupported("UserLevelPolicyUnsupported", &key_path(path, "level"));
    }
    let Some(user) = user else {
        return Authentication::None;
    };
    if source.user_path.is_some() {
        allow_keys(user, path, &["user", "pass", "level", "email"], sink);
    }
    let username = string(user, "user");
    let password = string(user, "pass");
    if protocol == Protocol::Socks && matches!(version.as_str(), "4" | "4a") {
        if password.as_ref().is_some_and(|value| !value.is_empty()) {
            sink.error("Socks4PasswordUnsupported", &key_path(path, "pass"));
        }
        if username.as_ref().is_some_and(|value| value.contains('\0')) {
            sink.error("Socks4UserIdContainsNul", &key_path(path, "user"));
        }
        if username
            .as_ref()
            .is_some_and(|value| value.len() > 255 || value.chars().any(char::is_control))
        {
            sink.unsupported("NativeSocks4UserIdUnsupported", &key_path(path, "user"));
        }
    } else {
        if protocol == Protocol::Socks {
            // RFC 1929 encodes byte lengths, not character counts. Absence has
            // the upstream empty-string default, which cannot be sent as valid
            // username/password authentication (both lengths must be 1..255).
            for (key, value) in [("user", &username), ("pass", &password)] {
                if value
                    .as_ref()
                    .is_none_or(|value| value.is_empty() || value.len() > 255)
                {
                    sink.error("Socks5CredentialLength", &key_path(path, key));
                }
            }
        } else {
            if username.as_ref().is_some_and(|value| value.contains(':')) {
                sink.error("HttpBasicUsernameColon", &key_path(path, "user"));
            }
            for (key, value) in [("user", &username), ("pass", &password)] {
                if value
                    .as_ref()
                    .is_some_and(|value| value.bytes().any(|byte| byte < 0x20 || byte == 0x7f))
                {
                    sink.error("HttpBasicControlCharacter", &key_path(path, key));
                }
            }
        }
        // Empty HTTP Basic components and a colon in SOCKS credentials have
        // upstream/wire semantics, but Swirl's shared Credentials gate cannot
        // represent them. Preserve them instead of dropping authentication.
        if username.as_ref().is_none_or(|value| {
            value.is_empty()
                || value.len() > 255
                || value.contains(':')
                || value.chars().any(char::is_control)
        }) || password.as_ref().is_none_or(|value| {
            value.is_empty() || value.len() > 255 || value.chars().any(char::is_control)
        }) {
            sink.unsupported("NativeProxyAuthenticationUnsupported", path);
        }
    }
    Authentication::UserPassword {
        user: username,
        pass: password,
        level: level(user),
    }
}

fn socks_version(settings: &Value, path: &str, sink: &mut Sink) -> String {
    match settings.get("version") {
        None => "5".into(),
        Some(Value::String(version)) => match version.to_ascii_lowercase().as_str() {
            "" | "5" => "5".into(),
            "4" => "4".into(),
            "4a" => "4a".into(),
            _ => {
                sink.error("InvalidSocksVersion", &key_path(path, "version"));
                String::new()
            }
        },
        Some(_) => {
            sink.error("ExpectedString", &key_path(path, "version"));
            String::new()
        }
    }
}

fn headers(settings: &Value, path: &str, sink: &mut Sink) {
    let Some(value) = settings.get("headers") else {
        return;
    };
    let path = key_path(path, "headers");
    let Some(headers) = value.as_object() else {
        sink.error("ExpectedObject", &path);
        return;
    };
    if !headers.is_empty() {
        sink.unsupported("HttpProxyHeadersUnsupported", &path);
    }
    for (name, value) in headers {
        let field_path = key_path(&path, name);
        if name.is_empty()
            || !name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b))
        {
            sink.error("InvalidHttpHeaderName", &field_path);
        }
        match value.as_str() {
            Some(value) if value.bytes().any(|b| (b < 0x20 && b != b'\t') || b == 0x7f) => {
                sink.error("InvalidHttpHeaderValue", &field_path);
            }
            Some(_) => (),
            None => sink.error("ExpectedString", &field_path),
        }
        if sink.overflow {
            break;
        }
    }
}
