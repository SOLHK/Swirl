//! Swirl IR v1. External documents remain available even if execution is rejected.
//! No Mihomo configuration or proxy engine is an internal execution dependency.
use serde::{Deserialize, Serialize};
pub mod inspect;
use std::{collections::HashSet, net::SocketAddr};

pub const MAX_DOCUMENT: usize = 1024 * 1024;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Credentials {
    pub username: String,
    pub password: String,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Tls {
    pub server_name: String,
    #[serde(default)]
    pub alpn: Vec<String>,
    /// Explicit extra trust anchor in DER/base64; never a filesystem path.
    #[serde(default)]
    pub ca_der_base64: Option<String>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Outbound {
    Direct,
    Reject,
    Socks5 {
        host: String,
        port: u16,
        auth: Option<Credentials>,
        #[serde(default)]
        tls: Option<Tls>,
    },
    HttpConnect {
        host: String,
        port: u16,
        auth: Option<Credentials>,
        #[serde(default)]
        tls: Option<Tls>,
    },
    Trojan {
        host: String,
        port: u16,
        password: String,
        tls: Tls,
    },
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Node {
    pub id: String,
    pub outbound: Outbound,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Matcher {
    Domain { value: String },
    DomainSuffix { value: String },
    Cidr { value: ipnet::IpNet },
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Rule {
    pub matcher: Matcher,
    pub outbound: String,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Limits {
    pub max_connections: usize,
    pub handshake_timeout_ms: u64,
}
impl Default for Limits {
    fn default() -> Self {
        Self {
            max_connections: 128,
            handshake_timeout_ms: 10000,
        }
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub schema: u32,
    pub listen: SocketAddr,
    pub selected: String,
    pub nodes: Vec<Node>,
    #[serde(default)]
    pub rules: Vec<Rule>,
    #[serde(default)]
    pub inbound_auth: Option<Credentials>,
    #[serde(default)]
    pub limits: Limits,
}

pub fn valid_host(host: &str) -> bool {
    !host.is_empty()
        && host.len() <= 253
        && (host.parse::<std::net::IpAddr>().is_ok()
            || host.split('.').all(|label| {
                !label.is_empty()
                    && label.len() <= 63
                    && !label.starts_with('-')
                    && !label.ends_with('-')
                    && label
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b == b'-')
            }))
}
fn valid_auth(auth: &Option<Credentials>) -> bool {
    auth.as_ref().is_none_or(|a| {
        !a.username.is_empty()
            && !a.password.is_empty()
            && a.username.len() <= 255
            && a.password.len() <= 255
            && !a.username.contains(':')
            && !a
                .username
                .chars()
                .chain(a.password.chars())
                .any(char::is_control)
    })
}
impl Config {
    pub fn parse(bytes: &[u8]) -> Result<Self, &'static str> {
        if bytes.is_empty() || bytes.len() > MAX_DOCUMENT {
            return Err("ConfigSize");
        }
        // Direct typed deserialization rejects duplicate known fields and unknown options.
        let config: Self =
            serde_json::from_slice(bytes).map_err(|_| "ConfigSyntaxOrUnsupportedField")?;
        config.validate()?;
        Ok(config)
    }
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.schema != 1
            || !self.listen.ip().is_loopback()
            || self.nodes.is_empty()
            || self.nodes.len() > 512
            || self.rules.len() > 4096
            || !(1..=256).contains(&self.limits.max_connections)
            || !(100..=30000).contains(&self.limits.handshake_timeout_ms)
            || !valid_auth(&self.inbound_auth)
        {
            return Err("ConfigBounds");
        }
        let mut ids = HashSet::new();
        for node in &self.nodes {
            if node.id.is_empty()
                || node.id.len() > 64
                || !node
                    .id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b))
                || !ids.insert(node.id.as_str())
            {
                return Err("NodeId");
            }
            match &node.outbound {
                Outbound::Socks5 {
                    host, port, auth, ..
                }
                | Outbound::HttpConnect {
                    host, port, auth, ..
                } if !valid_host(host) || *port == 0 || !valid_auth(auth) => {
                    return Err("NodeParameters");
                }
                Outbound::Trojan {
                    host,
                    port,
                    password,
                    ..
                } if !valid_host(host)
                    || *port == 0
                    || password.is_empty()
                    || password.len() > 1024 =>
                {
                    return Err("NodeParameters");
                }
                _ => {}
            }
            let tls = match &node.outbound {
                Outbound::Socks5 { tls, .. } | Outbound::HttpConnect { tls, .. } => tls.as_ref(),
                Outbound::Trojan { tls, .. } => Some(tls),
                _ => None,
            };
            if let Some(tls) = tls
                && (!valid_host(&tls.server_name)
                    || tls.ca_der_base64.as_ref().is_some_and(|s| s.len() > 65536)
                    || tls.alpn.len() > 16
                    || tls
                        .alpn
                        .iter()
                        .any(|s| s.is_empty() || s.len() > 255 || !s.is_ascii()))
            {
                return Err("TlsParameters");
            }
        }
        if !ids.contains(self.selected.as_str()) {
            return Err("SelectedNodeMissing");
        }
        for rule in &self.rules {
            if !ids.contains(rule.outbound.as_str()) {
                return Err("RuleNodeMissing");
            }
            match &rule.matcher {
                Matcher::Domain { value } | Matcher::DomainSuffix { value }
                    if !valid_host(value) =>
                {
                    return Err("RuleDomain");
                }
                _ => {}
            }
        }
        Ok(())
    }
}

/// Raw input retention is independent of executable IR success. Never logs input.
pub struct ImportedDocument {
    pub original: Vec<u8>,
    pub executable: Result<Config, &'static str>,
}
impl ImportedDocument {
    pub fn from_ir(bytes: &[u8]) -> Result<Self, &'static str> {
        if bytes.len() > MAX_DOCUMENT {
            return Err("ConfigSize");
        }
        Ok(Self {
            original: bytes.to_vec(),
            executable: Config::parse(bytes),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unknown_fields_preserved_but_not_executed() {
        let data = br#"{"schema":1,"unknown_tls_secret":"fixture"}"#;
        let imported = ImportedDocument::from_ir(data).unwrap();
        assert_eq!(imported.original, data);
        assert!(imported.executable.is_err());
    }
    #[test]
    fn host_validation_rejects_injection() {
        for host in [
            "x\r\nAuthorization: bad",
            "",
            "bad host",
            "-bad.test",
            "a..b",
        ] {
            assert!(!valid_host(host));
        }
        for host in ["example.org", "127.0.0.1", "::1"] {
            assert!(valid_host(host));
        }
    }
    #[test]
    fn duplicate_schema_rejected() {
        assert!(Config::parse(br#"{"schema":1,"schema":1,"listen":"127.0.0.1:0","selected":"d","nodes":[{"id":"d","outbound":{"type":"direct"}}]}"#).is_err());
    }
}
