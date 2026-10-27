//! TUIC v5 executable configuration. Legacy token authentication is TUIC v4,
//! not an alternative spelling of the v5 UUID/password exporter authentication.
use crate::{Tls, uuid_bytes, valid_host};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Tuic {
    pub host: String,
    pub port: u16,
    pub uuid: String,
    pub password: String,
    pub tls: Tls,
    #[serde(default)]
    pub insecure: bool,
    #[serde(default)]
    pub pin_sha256: Option<String>,
    #[serde(default = "enabled")]
    pub udp: bool,
    #[serde(default = "native")]
    pub udp_relay_mode: String,
    #[serde(default = "cubic")]
    pub congestion_control: String,
    #[serde(default = "heartbeat")]
    pub heartbeat_interval_ms: u64,
    #[serde(default = "request_timeout")]
    pub request_timeout_ms: u64,
}
fn enabled() -> bool {
    true
}
fn native() -> String {
    "native".into()
}
fn cubic() -> String {
    "cubic".into()
}
fn heartbeat() -> u64 {
    10_000
}
fn request_timeout() -> u64 {
    10_000
}

impl Tuic {
    pub fn validate(&self) -> Result<(), &'static str> {
        if !valid_host(&self.host)
            || self.port == 0
            || uuid_bytes(&self.uuid).is_none()
            || self.password.is_empty()
            || self.password.len() > 1024
        {
            return Err("TuicParameters");
        }
        if !valid_host(&self.tls.server_name)
            || self.tls.alpn.is_empty()
            || self.tls.alpn.len() > 16
            || self
                .tls
                .alpn
                .iter()
                .any(|v| v.is_empty() || v.len() > 255 || !v.is_ascii())
            || self
                .tls
                .ca_der_base64
                .as_ref()
                .is_some_and(|v| v.len() > 65_536)
        {
            return Err("TuicTlsParameters");
        }
        if let Some(pin) = &self.pin_sha256 {
            let bytes = pin.as_bytes();
            let valid = match bytes.len() {
                64 => bytes.iter().all(u8::is_ascii_hexdigit),
                95 => bytes.iter().enumerate().all(|(i, b)| {
                    if i % 3 == 2 {
                        *b == b':'
                    } else {
                        b.is_ascii_hexdigit()
                    }
                }),
                _ => false,
            };
            if !valid {
                return Err("TuicCertificatePin");
            }
        }
        if !["native", "quic"].contains(&self.udp_relay_mode.as_str()) {
            return Err("TuicUdpRelayMode");
        }
        if !["cubic", "bbr", "new_reno"].contains(&self.congestion_control.as_str()) {
            return Err("TuicCongestionUnsupported");
        }
        if !(100..=30_000).contains(&self.heartbeat_interval_ms) {
            return Err("TuicHeartbeatInterval");
        }
        if !(100..=120_000).contains(&self.request_timeout_ms) {
            return Err("TuicRequestTimeout");
        }
        Ok(())
    }

    /// Strict adapter for Clash/Mihomo and retained TUIC URI objects. Source
    /// values are never logged. Unsupported requirements reject the candidate.
    pub fn from_raw(raw: &Value) -> Result<Self, &'static str> {
        let object = raw.as_object().ok_or("TuicParameters")?;
        for key in ["type", "protocol"] {
            if object
                .get(key)
                .is_some_and(|value| value.as_str() != Some("tuic"))
            {
                return Err("TuicProtocol");
            }
        }
        if object.contains_key("token") {
            return Err("TuicV4Unsupported");
        }
        let allowed = [
            "type",
            "protocol",
            "name",
            "tag",
            "server",
            "port",
            "server_port",
            "uuid",
            "password",
            "tls",
            "sni",
            "servername",
            "alpn",
            "skip-cert-verify",
            "insecure",
            "pinSHA256",
            "pin-sha256",
            "fingerprint",
            "udp",
            "udp-relay-mode",
            "udp_relay_mode",
            "congestion-controller",
            "congestion_control",
            "heartbeat-interval",
            "request-timeout",
            "reduce-rtt",
            "disable-sni",
            "fast-open",
            "udp-over-stream",
            "version",
            "raw-uri",
        ];
        if object.keys().any(|key| !allowed.contains(&key.as_str())) {
            return Err("TuicUnmappedFields");
        }
        let uri_source = object
            .get("raw-uri")
            .map(|v| v.as_str().ok_or("TuicUri"))
            .transpose()?;
        let uri = uri_source
            .map(url::Url::parse)
            .transpose()
            .map_err(|_| "TuicUri")?;
        if let Some(uri) = &uri {
            if uri.scheme() != "tuic" {
                return Err("TuicUri");
            }
            let raw = uri_source.ok_or("TuicUri")?;
            let suffix = raw
                .split_once("://")
                .ok_or("TuicUri")?
                .1
                .split(['?', '#'])
                .next()
                .ok_or("TuicUri")?;
            if suffix
                .find('/')
                .is_some_and(|at| !matches!(&suffix[at..], "" | "/"))
            {
                return Err("TuicUriPath");
            }
        }
        let string = |keys: &[&str]| -> Result<Option<String>, &'static str> {
            let mut result: Option<String> = None;
            for key in keys {
                if let Some(value) = object.get(*key) {
                    let text = value.as_str().ok_or("TuicParameterType")?;
                    if result.as_ref().is_some_and(|other| other != text) {
                        return Err("TuicConflictingParameters");
                    }
                    result = Some(text.to_owned());
                }
            }
            Ok(result)
        };
        let boolean = |keys: &[&str], default: bool| -> Result<bool, &'static str> {
            let mut result = None;
            for key in keys {
                if let Some(value) = object.get(*key) {
                    let parsed = bool_value(value, uri.is_some())?;
                    if result.is_some_and(|old| old != parsed) {
                        return Err("TuicConflictingParameters");
                    }
                    result = Some(parsed);
                }
            }
            Ok(result.unwrap_or(default))
        };
        for key in ["reduce-rtt", "disable-sni", "fast-open", "udp-over-stream"] {
            if boolean(&[key], false)? {
                return Err("TuicOptionUnsupported");
            }
        }
        if let Some(version) = object.get("version")
            && number(version)? != 5
        {
            return Err("TuicVersionUnsupported");
        }
        let host = string(&["server"])?.ok_or("TuicParameters")?;
        let mut port = None;
        for key in ["port", "server_port"] {
            if let Some(value) = object.get(key) {
                let parsed = u16::try_from(number(value)?).map_err(|_| "TuicParameters")?;
                if port.is_some_and(|old| old != parsed) {
                    return Err("TuicConflictingParameters");
                }
                port = Some(parsed);
            }
        }
        let port = port.ok_or("TuicParameters")?;
        let uuid = string(&["uuid"])?.ok_or("TuicParameters")?;
        let mut password = string(&["password"])?;
        if let Some(uri) = &uri {
            let percent = |value: &str| -> Result<String, &'static str> {
                let bytes = value.as_bytes();
                for (at, byte) in bytes.iter().enumerate() {
                    if *byte == b'%'
                        && (at + 2 >= bytes.len()
                            || !bytes[at + 1].is_ascii_hexdigit()
                            || !bytes[at + 2].is_ascii_hexdigit())
                    {
                        return Err("TuicUriEncoding");
                    }
                }
                percent_encoding::percent_decode_str(value)
                    .decode_utf8()
                    .map(|v| v.into_owned())
                    .map_err(|_| "TuicUriEncoding")
            };
            let original_uuid = percent(uri.username())?;
            let original_password = percent(uri.password().ok_or("TuicPassword")?)?;
            if uuid_bytes(&original_uuid) != uuid_bytes(&uuid)
                || uri.port() != Some(port)
                || uri
                    .host_str()
                    .map(|v| v.trim_matches(['[', ']']))
                    .is_none_or(|v| v != host)
            {
                return Err("TuicConflictingParameters");
            }
            if password
                .as_ref()
                .is_some_and(|value| value != &original_password)
            {
                return Err("TuicConflictingParameters");
            }
            password = Some(original_password);
        }
        let tls_map = match object.get("tls") {
            None | Some(Value::Bool(true)) => None,
            Some(Value::Object(value)) => Some(value),
            _ => return Err("TuicTlsRequired"),
        };
        if tls_map.is_some_and(|map| {
            map.keys().any(|k| {
                ![
                    "enabled",
                    "server_name",
                    "alpn",
                    "insecure",
                    "ca_der_base64",
                ]
                .contains(&k.as_str())
            })
        }) {
            return Err("TuicTlsUnmappedFields");
        }
        if let Some(enabled) = tls_map.and_then(|map| map.get("enabled"))
            && !bool_value(enabled, false)?
        {
            return Err("TuicTlsRequired");
        }
        let nested_name = field_string(tls_map, "server_name")?;
        let outer_name = string(&["sni", "servername"])?;
        if nested_name
            .as_ref()
            .zip(outer_name.as_ref())
            .is_some_and(|(a, b)| a != b)
        {
            return Err("TuicConflictingParameters");
        }
        let server_name = outer_name.or(nested_name).unwrap_or_else(|| host.clone());
        let mut alpn = None;
        for value in [object.get("alpn"), tls_map.and_then(|map| map.get("alpn"))]
            .into_iter()
            .flatten()
        {
            let parsed = match value {
                Value::Array(values) => values
                    .iter()
                    .map(|v| v.as_str().map(str::to_owned).ok_or("TuicAlpn"))
                    .collect::<Result<Vec<_>, _>>()?,
                Value::String(value) if uri.is_some() => {
                    value.split(',').map(str::to_owned).collect()
                }
                _ => return Err("TuicAlpn"),
            };
            if alpn.as_ref().is_some_and(|old| old != &parsed) {
                return Err("TuicConflictingParameters");
            }
            alpn = Some(parsed);
        }
        let mut insecure = boolean(&["skip-cert-verify", "insecure"], false)?;
        if let Some(value) = tls_map.and_then(|map| map.get("insecure")) {
            let nested = bool_value(value, false)?;
            if (object.contains_key("skip-cert-verify") || object.contains_key("insecure"))
                && nested != insecure
            {
                return Err("TuicConflictingParameters");
            }
            insecure = nested;
        }
        // In Mihomo's generic TLS config fingerprint is a certificate digest,
        // while client-fingerprint is a ClientHello profile. The latter is not
        // in the allowlist and cannot be silently mapped to rustls.
        let pin_sha256 = string(&["pinSHA256", "pin-sha256", "fingerprint"])?;
        let result = Self {
            host,
            port,
            uuid,
            password: password.ok_or("TuicPassword")?,
            tls: Tls {
                server_name,
                alpn: alpn.unwrap_or_else(|| vec!["h3".into()]),
                ca_der_base64: field_string(tls_map, "ca_der_base64")?,
            },
            insecure,
            pin_sha256,
            udp: boolean(&["udp"], true)?,
            udp_relay_mode: string(&["udp-relay-mode", "udp_relay_mode"])?.unwrap_or_else(native),
            congestion_control: string(&["congestion-controller", "congestion_control"])?
                .unwrap_or_else(cubic),
            heartbeat_interval_ms: object
                .get("heartbeat-interval")
                .map(number)
                .transpose()?
                .unwrap_or_else(heartbeat),
            request_timeout_ms: object
                .get("request-timeout")
                .map(number)
                .transpose()?
                .unwrap_or_else(request_timeout),
        };
        result.validate()?;
        Ok(result)
    }
}

fn field_string(
    map: Option<&Map<String, Value>>,
    key: &str,
) -> Result<Option<String>, &'static str> {
    map.and_then(|map| map.get(key))
        .map(|value| value.as_str().map(str::to_owned).ok_or("TuicParameterType"))
        .transpose()
}
fn number(value: &Value) -> Result<u64, &'static str> {
    value
        .as_u64()
        .or_else(|| {
            value.as_str().and_then(|s| {
                if !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()) {
                    s.parse().ok()
                } else {
                    None
                }
            })
        })
        .ok_or("TuicParameterType")
}
fn bool_value(value: &Value, uri: bool) -> Result<bool, &'static str> {
    match value {
        Value::Bool(value) => Ok(*value),
        Value::String(value) if uri => match value.as_str() {
            "true" | "1" => Ok(true),
            "false" | "0" => Ok(false),
            _ => Err("TuicParameterType"),
        },
        _ => Err("TuicParameterType"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn raw() -> Value {
        json!({"type":"tuic","server":"localhost","port":443,"uuid":"00000000-0000-0000-0000-000000000001","password":"local-fixture"})
    }
    #[test]
    fn clash_v5_and_modes_are_mapped_without_credentials_loss() {
        let mut value = raw();
        value["udp-relay-mode"] = "quic".into();
        value["congestion-controller"] = "bbr".into();
        value["heartbeat-interval"] = 5000.into();
        let mapped = Tuic::from_raw(&value).unwrap();
        assert_eq!(mapped.password, "local-fixture");
        assert_eq!(mapped.udp_relay_mode, "quic");
        assert_eq!(mapped.congestion_control, "bbr");
        assert_eq!(mapped.heartbeat_interval_ms, 5000);
        assert!(!mapped.insecure);
    }
    #[test]
    fn retained_uri_recovers_the_password_and_checks_conflicts() {
        let mut value = raw();
        value.as_object_mut().unwrap().remove("password");
        value["raw-uri"] =
            "tuic://00000000-0000-0000-0000-000000000001:local%3Afixture@localhost:443".into();
        assert_eq!(Tuic::from_raw(&value).unwrap().password, "local:fixture");
        value["password"] = "different".into();
        assert!(Tuic::from_raw(&value).is_err());
    }
    #[test]
    fn legacy_security_conflicts_and_unimplemented_requirements_are_blocked() {
        for (key, val) in [
            ("token", json!("v4")),
            ("reduce-rtt", json!(true)),
            ("disable-sni", json!(true)),
            ("client-fingerprint", json!("chrome")),
            ("unknown", json!(1)),
            ("udp-relay-mode", json!("other")),
            ("pinSHA256", json!("invalid")),
            ("skip-cert-verify", json!("true")),
            ("tls", json!(false)),
        ] {
            let mut value = raw();
            value[key] = val;
            assert!(Tuic::from_raw(&value).is_err(), "{key}");
        }
        let mut value = raw();
        value["sni"] = "a.invalid".into();
        value["servername"] = "b.invalid".into();
        assert!(Tuic::from_raw(&value).is_err());
    }
}
