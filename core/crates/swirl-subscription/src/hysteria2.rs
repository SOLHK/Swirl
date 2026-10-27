//! Hysteria 2 configuration. Importability and native execution are separate:
//! security or transport options without an implementation fail closed.
//! Protocol reference: https://v2.hysteria.network/docs/developers/Protocol/
use crate::{Tls, valid_host};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Hysteria2 {
    pub host: String,
    pub port: u16,
    pub password: String,
    pub tls: Tls,
    #[serde(default)]
    pub insecure: bool,
    #[serde(default)]
    pub pin_sha256: Option<String>,
    #[serde(default)]
    pub obfs: Option<String>,
    #[serde(default)]
    pub obfs_password: Option<String>,
    #[serde(default)]
    pub ports: Option<String>,
    #[serde(default)]
    pub up_mbps: Option<u64>,
    #[serde(default)]
    pub down_mbps: Option<u64>,
    #[serde(default)]
    pub ech: Option<String>,
    #[serde(default = "udp_default")]
    pub udp: bool,
}

fn udp_default() -> bool {
    true
}

impl Hysteria2 {
    pub fn validate(&self) -> Result<(), &'static str> {
        if !valid_host(&self.host) || self.port == 0 {
            return Err("Hysteria2Endpoint");
        }
        // Credentials are an HTTP field value, never a URL or a log message.
        if self.password.is_empty()
            || self.password.len() > 4096
            || !self
                .password
                .bytes()
                .all(|b| (0x20..=0x7e).contains(&b) || b >= 0x80)
        {
            return Err("Hysteria2AuthenticationParameters");
        }
        if !valid_host(&self.tls.server_name) {
            return Err("Hysteria2Sni");
        }
        if !self.tls.alpn.is_empty() && self.tls.alpn != ["h3"] {
            return Err("Hysteria2Alpn");
        }
        if self.pin_sha256.as_ref().is_some_and(|pin| match pin.len() {
            64 => !pin.bytes().all(|byte| byte.is_ascii_hexdigit()),
            95 => !pin.bytes().enumerate().all(|(index, byte)| {
                if index % 3 == 2 {
                    byte == b':'
                } else {
                    byte.is_ascii_hexdigit()
                }
            }),
            _ => true,
        }) {
            return Err("Hysteria2CertificatePin");
        }
        if let Some(certificate) = &self.tls.ca_der_base64 {
            use base64::Engine;
            if certificate.len() > 65536
                || base64::engine::general_purpose::STANDARD
                    .decode(certificate)
                    .is_err()
            {
                return Err("Hysteria2TrustAnchor");
            }
        }
        match (self.obfs.as_deref(), self.obfs_password.as_deref()) {
            (None | Some(""), None) => {}
            (Some("salamander"), Some(password)) if (4..=1024).contains(&password.len()) => {}
            (Some("salamander"), _) => return Err("Hysteria2ObfsParameters"),
            _ => return Err("Hysteria2ObfsUnsupported"),
        }
        if self.ports.is_some() {
            return Err("Hysteria2PortHoppingUnsupported");
        }
        self.bandwidth_bytes()?;
        if self.ech.is_some() {
            return Err("Hysteria2EchUnsupported");
        }
        Ok(())
    }

    /// Subscription bandwidth values are decimal megabits per second; the
    /// Hysteria protocol authenticates with bytes per second. Zero means auto.
    pub fn bandwidth_bytes(&self) -> Result<(u64, u64), &'static str> {
        let convert = |value: Option<u64>| {
            value
                .unwrap_or(0)
                .checked_mul(125_000)
                .ok_or("Hysteria2BandwidthParameters")
        };
        Ok((convert(self.up_mbps)?, convert(self.down_mbps)?))
    }
}

fn optional_string(raw: &Value, keys: &[&str]) -> Result<Option<String>, &'static str> {
    let mut result: Option<String> = None;
    for key in keys {
        if let Some(value) = raw.get(*key) {
            let value = value.as_str().ok_or("Hysteria2ParameterType")?;
            if result.as_ref().is_some_and(|previous| previous != value) {
                return Err("Hysteria2ConflictingParameters");
            }
            result = Some(value.into());
        }
    }
    Ok(result)
}

fn optional_bool(raw: &Value, keys: &[&str]) -> Result<Option<bool>, &'static str> {
    let mut result = None;
    for key in keys {
        if let Some(value) = raw.get(*key) {
            let value = value.as_bool().ok_or("Hysteria2ParameterType")?;
            if result.is_some_and(|previous| previous != value) {
                return Err("Hysteria2ConflictingParameters");
            }
            result = Some(value);
        }
    }
    Ok(result)
}

fn bandwidth(raw: &Value, key: &str) -> Result<Option<u64>, &'static str> {
    match raw.get(key) {
        None => Ok(None),
        Some(value) => value
            .as_u64()
            .or_else(|| {
                value
                    .as_str()
                    .and_then(|value| value.strip_suffix(" Mbps").unwrap_or(value).parse().ok())
            })
            .map(Some)
            .ok_or("Hysteria2BandwidthParameters"),
    }
}

/// Convert the common Clash/URI representation; source documents remain intact.
pub fn from_raw(raw: &Value) -> Result<Hysteria2, &'static str> {
    const FIELDS: &[&str] = &[
        "type",
        "name",
        "server",
        "port",
        "password",
        "sni",
        "servername",
        "alpn",
        "skip-cert-verify",
        "insecure",
        "pinSHA256",
        "fingerprint",
        "obfs",
        "obfs-password",
        "ports",
        "mport",
        "up",
        "down",
        "udp",
        "ech",
        "raw-uri",
        "ca-der-base64",
    ];
    let object = raw.as_object().ok_or("Hysteria2Parameters")?;
    if object.keys().any(|key| !FIELDS.contains(&key.as_str())) {
        return Err("Hysteria2UnmappedFields");
    }
    if !matches!(
        raw.get("type").and_then(Value::as_str),
        Some("hysteria2" | "hy2")
    ) {
        return Err("Hysteria2ProtocolVersion");
    }
    let host = optional_string(raw, &["server"])?.ok_or("Hysteria2Endpoint")?;
    let port = raw.get("port").and_then(Value::as_u64).unwrap_or(443);
    // An explicitly malformed port cannot inherit the URI default.
    if raw
        .get("port")
        .is_some_and(|value| value.as_u64().is_none())
        || !(1..=65535).contains(&port)
    {
        return Err("Hysteria2Endpoint");
    }
    let config = Hysteria2 {
        tls: Tls {
            server_name: optional_string(raw, &["sni", "servername"])?
                .unwrap_or_else(|| host.clone()),
            alpn: match raw.get("alpn") {
                None => vec!["h3".into()],
                Some(value) => {
                    serde_json::from_value(value.clone()).map_err(|_| "Hysteria2Alpn")?
                }
            },
            ca_der_base64: optional_string(raw, &["ca-der-base64"])?,
        },
        host,
        port: port as u16,
        password: optional_string(raw, &["password"])?
            .ok_or("Hysteria2AuthenticationParameters")?,
        insecure: optional_bool(raw, &["insecure", "skip-cert-verify"])?.unwrap_or(false),
        // Mihomo's `fingerprint` for this protocol is the certificate digest;
        // `client-fingerprint` is deliberately outside the allowed field set.
        pin_sha256: optional_string(raw, &["pinSHA256", "fingerprint"])?,
        obfs: optional_string(raw, &["obfs"])?,
        obfs_password: optional_string(raw, &["obfs-password"])?,
        ports: optional_string(raw, &["ports", "mport"])?,
        up_mbps: bandwidth(raw, "up")?,
        down_mbps: bandwidth(raw, "down")?,
        ech: optional_string(raw, &["ech"])?,
        udp: optional_bool(raw, &["udp"])?.unwrap_or(true),
    };
    config.validate()?;
    Ok(config)
}

fn decode(value: &str) -> Result<String, &'static str> {
    let bytes = value.as_bytes();
    let mut position = 0;
    while position < bytes.len() {
        if bytes[position] == b'%' {
            if position + 2 >= bytes.len()
                || !bytes[position + 1].is_ascii_hexdigit()
                || !bytes[position + 2].is_ascii_hexdigit()
            {
                return Err("Hysteria2UriEscape");
            }
            position += 2;
        }
        position += 1;
    }
    percent_encoding::percent_decode_str(value)
        .decode_utf8()
        .map(|text| text.into_owned())
        .map_err(|_| "Hysteria2UriEncoding")
}

/// Parse the official hy2/hysteria2 URI, including a preserved multi-port field.
/// Unsupported execution options survive parsing and are rejected by validate.
pub fn parse_uri(input: &str) -> Result<Value, &'static str> {
    let (scheme, tail) = input.split_once("://").ok_or("Hysteria2Uri")?;
    if !matches!(scheme, "hysteria2" | "hy2") || input.len() > 16384 {
        return Err("Hysteria2Uri");
    }
    let end = tail.find(['/', '?', '#']).unwrap_or(tail.len());
    let authority = &tail[..end];
    let (_, endpoint) = authority
        .rsplit_once('@')
        .ok_or("Hysteria2UriAuthentication")?;
    let port_start = if endpoint.starts_with('[') {
        endpoint
            .find(']')
            .and_then(|close| endpoint[close + 1..].strip_prefix(':').map(|_| close + 2))
    } else {
        endpoint.rfind(':').map(|colon| colon + 1)
    };
    let multi = port_start
        .map(|position| &endpoint[position..])
        .filter(|port| port.contains([',', '-']));
    let rewritten;
    let url_text = if let Some(ports) = multi {
        if ports.len() > 1024
            || !ports
                .bytes()
                .all(|byte| byte.is_ascii_digit() || b",-".contains(&byte))
        {
            return Err("Hysteria2PortHoppingParameters");
        }
        let start = input.len() - tail.len() + authority.len() - ports.len();
        rewritten = format!("{}443{}", &input[..start], &tail[end..]);
        rewritten.as_str()
    } else {
        input
    };
    let url = url::Url::parse(url_text).map_err(|_| "Hysteria2Uri")?;
    if !matches!(url.path(), "" | "/") {
        return Err("Hysteria2UriPath");
    }
    let mut password = decode(url.username())?;
    if let Some(part) = url.password() {
        password.push(':');
        password.push_str(&decode(part)?);
    }
    let host = url
        .host_str()
        .ok_or("Hysteria2Endpoint")?
        .trim_start_matches('[')
        .trim_end_matches(']');
    let mut output = Map::new();
    output.insert("type".into(), json!("hysteria2"));
    output.insert("server".into(), json!(host));
    output.insert("port".into(), json!(url.port().unwrap_or(443)));
    output.insert("password".into(), json!(password));
    output.insert("raw-uri".into(), json!(input));
    if let Some(name) = url.fragment() {
        output.insert("name".into(), json!(decode(name)?));
    }
    if let Some(ports) = multi {
        output.insert("ports".into(), json!(ports));
    }
    if let Some(query) = url.query() {
        for pair in query.split('&').filter(|part| !part.is_empty()) {
            let (key, value) = pair.split_once('=').ok_or("Hysteria2UriParameter")?;
            let key = decode(key)?;
            let value = decode(value)?;
            if output.contains_key(&key) {
                return Err("Hysteria2DuplicateParameter");
            }
            let value = match key.as_str() {
                "insecure" | "udp" => match value.as_str() {
                    "0" => json!(false),
                    "1" => json!(true),
                    _ => return Err("Hysteria2UriBoolean"),
                },
                "alpn" => json!(value.split(',').collect::<Vec<_>>()),
                _ => json!(value),
            };
            output.insert(key, value);
        }
    }
    Ok(Value::Object(output))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn official_uri_defaults_and_userpass_are_not_lost() {
        let raw = parse_uri("hy2://user:p%40ss@proxy.example/?sni=origin.example#demo").unwrap();
        let node = from_raw(&raw).unwrap();
        assert_eq!(node.port, 443);
        assert_eq!(node.password, "user:p@ss");
        assert_eq!(node.tls.server_name, "origin.example");
        assert!(node.udp);
        assert!(!node.insecure);
    }

    #[test]
    fn unsupported_security_and_transport_parameters_are_preserved_then_blocked() {
        for (uri, error) in [
            (
                "hy2://pass@proxy.example:443,8443/",
                "Hysteria2PortHoppingUnsupported",
            ),
            (
                "hy2://pass@proxy.example/?obfs=gecko&obfs-password=secret",
                "Hysteria2ObfsUnsupported",
            ),
            (
                "hy2://pass@proxy.example/?ech=AAAA",
                "Hysteria2EchUnsupported",
            ),
            (
                "hy2://pass@proxy.example/?client-fingerprint=chrome",
                "Hysteria2UnmappedFields",
            ),
        ] {
            let raw = parse_uri(uri).unwrap();
            assert_eq!(raw["raw-uri"], uri);
            assert_eq!(from_raw(&raw).err(), Some(error));
        }
    }

    #[test]
    fn strict_pin_and_ipv6_uri() {
        let pin = "ab".repeat(32);
        let raw = parse_uri(&format!(
            "hysteria2://p%3Aa@[::1]:8443/?insecure=1&pinSHA256={pin}"
        ))
        .unwrap();
        let node = from_raw(&raw).unwrap();
        assert_eq!(node.host, "::1");
        assert_eq!(node.password, "p:a");
        assert_eq!(node.pin_sha256.as_deref(), Some(pin.as_str()));
        assert!(node.insecure);
        assert!(
            from_raw(
                &json!({"type":"hysteria2","server":"host.test","password":"x","pinSHA256":"no"})
            )
            .is_err()
        );
    }

    #[test]
    fn malformed_or_conflicting_configuration_is_rejected() {
        for uri in [
            "hy2://x@host.test/?insecure=true",
            "hy2://x@host.test/?sni=a&sni=b",
            "hy2://%ZZ@host.test/",
            "hy2://x@host.test/path",
        ] {
            assert!(parse_uri(uri).is_err());
        }
        for extra in [
            json!({"insecure":"false"}),
            json!({"port":"443"}),
            json!({"sni":"a.test","servername":"b.test"}),
            json!({"alpn":["h2"]}),
            json!({"password":"a\r\nb"}),
            json!({"up":u64::MAX}),
        ] {
            let mut raw = json!({"type":"hysteria2","server":"host.test","password":"pass"});
            raw.as_object_mut()
                .unwrap()
                .extend(extra.as_object().unwrap().clone());
            assert!(from_raw(&raw).is_err());
        }
    }

    #[test]
    fn salamander_and_bandwidth_parameters_survive_both_import_paths() {
        let uri = "hy2://pass@host.test/?obfs=salamander&obfs-password=long-secret&up=3&down=5";
        let node = from_raw(&parse_uri(uri).unwrap()).unwrap();
        assert_eq!(node.obfs.as_deref(), Some("salamander"));
        assert_eq!(node.obfs_password.as_deref(), Some("long-secret"));
        assert_eq!(node.bandwidth_bytes().unwrap(), (375000, 625000));
        let node = from_raw(
            &json!({"type":"hysteria2","server":"host.test","password":"pass",
            "up":"3 Mbps","down":5}),
        )
        .unwrap();
        assert_eq!(node.bandwidth_bytes().unwrap(), (375000, 625000));
    }
}
