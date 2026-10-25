//! Swirl IR v1. External documents remain available even if execution is rejected.
//! No Mihomo configuration or proxy engine is an internal execution dependency.
use serde::{Deserialize, Serialize};
mod dns_tls;
pub mod hysteria2;
pub mod ss2022;
pub mod tuic;
pub mod vmess;
pub use hysteria2::Hysteria2;
pub use tuic::Tuic;
mod policy;
mod reality;
mod singbox_quic;
pub mod stream_transport;
pub mod v2;
mod websocket;
pub use policy::{HealthProbe, PolicyStrategy, ProbeTarget};
pub use reality::Reality;
pub use stream_transport::StreamTransport;
pub use websocket::WebSocket;
pub mod inspect;
pub mod profile;
pub mod xray;
pub use dns_tls::DnsTlsServer;
use std::{collections::HashSet, net::SocketAddr};

pub const MAX_DOCUMENT: usize = 1024 * 1024;

/// Bounded JSON parsing shared by offline import boundaries. Duplicate keys
/// fail at every depth before a client-specific projection can discard them.
pub fn parse_json_value(bytes: &[u8]) -> Result<serde_json::Value, xray::Diagnostic> {
    xray::parse_json_value(bytes)
}

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
#[serde(deny_unknown_fields)]
pub struct ObfsHttp {
    pub host: String,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Outbound {
    Direct {},
    Reject {},
    Vmess {
        host: String,
        port: u16,
        uuid: String,
        #[serde(default)]
        alter_id: u32,
        #[serde(default = "vmess_default_security")]
        security: String,
        #[serde(default)]
        tls: Option<Tls>,
        #[serde(default)]
        websocket: Option<WebSocket>,
    },
    Hysteria2(Hysteria2),
    Tuic(Tuic),
    Vless {
        host: String,
        port: u16,
        uuid: String,
        #[serde(default)]
        tls: Option<Tls>,
        #[serde(default)]
        websocket: Option<WebSocket>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        reality: Option<Reality>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        flow: Option<String>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        transport: Option<StreamTransport>,
        #[serde(default)]
        udp: bool,
    },
    Shadowsocks {
        host: String,
        port: u16,
        password: String,
        cipher: String,
        #[serde(default)]
        udp: bool,
        #[serde(default)]
        obfs_http: Option<ObfsHttp>,
    },
    Socks4 {
        host: String,
        port: u16,
        #[serde(default)]
        user_id: String,
        #[serde(default = "default_true")]
        remote_dns: bool,
    },
    Socks5 {
        host: String,
        port: u16,
        auth: Option<Credentials>,
        #[serde(default)]
        tls: Option<Tls>,
        #[serde(default)]
        udp: bool,
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
        #[serde(default)]
        websocket: Option<WebSocket>,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        transport: Option<StreamTransport>,
        #[serde(default)]
        udp: bool,
    },
}

fn vmess_default_security() -> String {
    "auto".into()
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Node {
    pub id: String,
    pub outbound: Outbound,
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Matcher {
    Domain {
        value: String,
    },
    DomainSuffix {
        value: String,
    },
    DomainKeyword {
        value: String,
    },
    Cidr {
        value: ipnet::IpNet,
        // Existing schema-1 CIDR rules remain literal-IP-only by default.
        #[serde(default)]
        resolve: bool,
    },
    SourceCidr {
        value: ipnet::IpNet,
    },
    DestinationPort {
        value: u16,
    },
    Match {},
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Rule {
    pub matcher: Matcher,
    pub outbound: String,
}

/// Explicit policy group. Manual groups can contain validated groups; automatic
/// groups probe concrete nodes and never replay application requests.
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Selector {
    pub id: String,
    pub members: Vec<String>,
    #[serde(default)]
    pub selected: String,
    #[serde(default)]
    pub strategy: PolicyStrategy,
    #[serde(default)]
    pub probe: Option<HealthProbe>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HostMapping {
    pub name: String,
    pub address: std::net::IpAddr,
}

/// Which wire record families explicit DNS upstreams may query. This does not
/// disable IPv6 literal destinations or exact static host mappings.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", try_from = "String")]
pub enum DnsQueryFamily {
    #[default]
    Dual,
    Ipv4Only,
}
impl TryFrom<String> for DnsQueryFamily {
    type Error = &'static str;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        match value.as_str() {
            "dual" => Ok(Self::Dual),
            "ipv4_only" => Ok(Self::Ipv4Only),
            _ => Err("DnsQueryFamilyValue"),
        }
    }
}
impl DnsQueryFamily {
    fn is_default(&self) -> bool {
        *self == Self::Dual
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Dns {
    #[serde(default, skip_serializing_if = "DnsQueryFamily::is_default")]
    pub query_family: DnsQueryFamily,
    #[serde(default)]
    pub hosts: Vec<HostMapping>,
    #[serde(default)]
    pub force_proxy_hosts: bool,
    #[serde(default)]
    pub servers: Vec<SocketAddr>,
    /// Strict DoT endpoints; mutually exclusive with plaintext servers.
    #[serde(default)]
    pub tls_servers: Vec<DnsTlsServer>,
    #[serde(default = "default_true")]
    pub use_system_hosts: bool,
}
fn default_true() -> bool {
    true
}
impl Dns {
    pub fn validate_query_family(&self) -> Result<(), &'static str> {
        // Filtering OS lookup results would not prevent unrequested wire queries.
        if self.query_family != DnsQueryFamily::Dual
            && self.servers.is_empty()
            && self.tls_servers.is_empty()
        {
            return Err("DnsQueryFamilyRequiresExplicitServer");
        }
        Ok(())
    }
}
impl Default for Dns {
    fn default() -> Self {
        Self {
            query_family: DnsQueryFamily::Dual,
            hosts: Vec::new(),
            force_proxy_hosts: false,
            servers: Vec::new(),
            tls_servers: Vec::new(),
            use_system_hosts: true,
        }
    }
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
    /// Enable bundled, checksum-pinned China MRS fallback before MATCH.
    #[serde(default)]
    pub smart_routing: bool,
    #[serde(default)]
    pub selectors: Vec<Selector>,
    #[serde(default)]
    pub dns: Dns,
    /// Directory containing the two bundled, checksum-pinned MRS rule providers.
    #[serde(default)]
    pub china_rules_directory: Option<String>,
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
pub fn uuid_bytes(value: &str) -> Option<[u8; 16]> {
    if value.len() != 36 || !value.is_ascii() {
        return None;
    }
    let mut compact = String::with_capacity(32);
    for (i, c) in value.chars().enumerate() {
        if [8, 13, 18, 23].contains(&i) {
            if c != '-' {
                return None;
            }
        } else if c.is_ascii_hexdigit() {
            compact.push(c);
        } else {
            return None;
        }
    }
    let mut bytes = [0; 16];
    for (i, b) in bytes.iter_mut().enumerate() {
        *b = u8::from_str_radix(&compact[i * 2..i * 2 + 2], 16).ok()?;
    }
    Some(bytes)
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
            || self.selectors.len() > 128
            || self.dns.hosts.len() > 512
            || self.dns.servers.len() > 4
            || self
                .dns
                .servers
                .iter()
                .any(|s| s.port() == 0 || s.ip().is_unspecified() || s.ip().is_multicast())
            || (self.dns.servers.is_empty()
                && self.dns.tls_servers.is_empty()
                && !self.dns.use_system_hosts)
            || !(1..=256).contains(&self.limits.max_connections)
            || !(100..=30000).contains(&self.limits.handshake_timeout_ms)
            || !valid_auth(&self.inbound_auth)
        {
            return Err("ConfigBounds");
        }
        if self
            .china_rules_directory
            .as_ref()
            .is_some_and(|p| p.is_empty() || p.len() > 4096 || p.chars().any(char::is_control))
        {
            return Err("ChinaRulesDirectory");
        }
        self.dns.validate_query_family()?;
        self.dns.validate_tls()?;
        let mut host_names = HashSet::new();
        let mut servers = HashSet::new();
        for server in &self.dns.servers {
            if !servers.insert(*server)
                || matches!(server,SocketAddr::V6(address) if address.scope_id()!=0)
            {
                return Err("DnsServerAddress");
            }
        }
        for host in &self.dns.hosts {
            if !valid_host(&host.name)
                || host.name.parse::<std::net::IpAddr>().is_ok()
                || !host_names.insert(host.name.to_ascii_lowercase())
            {
                return Err("DnsHostMapping");
            }
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
                Outbound::Vmess {
                    host,
                    port,
                    uuid,
                    alter_id,
                    security,
                    ..
                } => {
                    if !valid_host(host) || *port == 0 {
                        return Err("VmessParameters");
                    }
                    vmess::validate(uuid, *alter_id, security)?;
                }
                Outbound::Hysteria2(config) => config.validate()?,
                Outbound::Tuic(config) => config.validate()?,
                Outbound::Socks4 {
                    host,
                    port,
                    user_id,
                    ..
                } if !valid_host(host)
                    || *port == 0
                    || user_id.len() > 255
                    || user_id.chars().any(char::is_control) =>
                {
                    return Err("Socks4Parameters");
                }
                Outbound::Vless {
                    host, port, uuid, ..
                } if !valid_host(host) || *port == 0 || uuid_bytes(uuid).is_none() => {
                    return Err("VlessParameters");
                }
                Outbound::Shadowsocks {
                    host,
                    port,
                    password,
                    cipher,
                    obfs_http,
                    ..
                } => {
                    if !valid_host(host)
                        || *port == 0
                        || password.is_empty()
                        || password.len() > 1024
                        || ![
                            "aes-128-gcm",
                            "aes-256-gcm",
                            "chacha20-ietf-poly1305",
                            "2022-blake3-aes-128-gcm",
                            "2022-blake3-aes-256-gcm",
                        ]
                        .contains(&cipher.as_str())
                        || obfs_http.as_ref().is_some_and(|o| !valid_host(&o.host))
                    {
                        return Err("ShadowsocksParameters");
                    }
                    if cipher.starts_with("2022-") {
                        ss2022::validate(password, cipher)?;
                        if obfs_http.is_some() {
                            return Err("Shadowsocks2022ObfsUnsupported");
                        }
                    }
                }
                Outbound::Socks5 {
                    host, port, auth, ..
                }
                | Outbound::HttpConnect {
                    host, port, auth, ..
                } if !valid_host(host) || *port == 0 || !valid_auth(auth) => {
                    return Err("NodeParameters");
                }
                Outbound::Socks5 {
                    udp: true,
                    tls: Some(_),
                    ..
                } => return Err("Socks5UdpTlsUnsupported"),
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
            if let Some(transport) = node.outbound.stream_transport() {
                transport.validate_for(&node.outbound)?;
            }
            if matches!(&node.outbound, Outbound::Vless { udp: true, flow: Some(flow), .. } if !flow.is_empty())
            {
                return Err("VisionUdpUnsupported");
            }
            match &node.outbound {
                Outbound::Vmess {
                    websocket: Some(ws),
                    tls,
                    ..
                } => ws.validate_tls(tls.as_ref())?,
                Outbound::Vless {
                    reality,
                    flow,
                    tls,
                    websocket,
                    ..
                } => {
                    if flow.as_deref().is_some_and(|value| {
                        !value.is_empty() && (reality.is_none() || value != "xtls-rprx-vision")
                    }) {
                        return Err("VlessFlowUnsupported");
                    }
                    if let Some(reality) = reality {
                        if tls.is_some() || websocket.is_some() {
                            return Err("RealityTransportConflict");
                        }
                        reality.validate()?;
                    }
                    if let Some(ws) = websocket {
                        ws.validate_tls(tls.as_ref())?;
                    }
                }
                Outbound::Trojan {
                    websocket: Some(ws),
                    tls,
                    ..
                } => ws.validate_tls(Some(tls))?,
                _ => {}
            }
            let tls = match &node.outbound {
                Outbound::Socks5 { tls, .. }
                | Outbound::HttpConnect { tls, .. }
                | Outbound::Vmess { tls, .. }
                | Outbound::Vless { tls, .. } => tls.as_ref(),
                Outbound::Trojan { tls, .. } => Some(tls),
                Outbound::Hysteria2(config) => Some(&config.tls),
                Outbound::Tuic(config) => Some(&config.tls),
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
        let mut selector_ids = HashSet::new();
        for selector in &self.selectors {
            if selector.id.is_empty()
                || selector.id.len() > 64
                || !selector
                    .id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b))
                || ids.contains(selector.id.as_str())
                || !selector_ids.insert(selector.id.as_str())
            {
                return Err("SelectorId");
            }
        }
        if !ids.contains(self.selected.as_str()) && !selector_ids.contains(self.selected.as_str()) {
            return Err("SelectedNodeMissing");
        }
        for selector in &self.selectors {
            let mut members = HashSet::new();
            if selector.members.is_empty()
                || selector.members.len() > 512
                || selector.members.iter().any(|id| {
                    (!ids.contains(id.as_str()) && !selector_ids.contains(id.as_str()))
                        || !members.insert(id.as_str())
                })
                || (selector.strategy == PolicyStrategy::Manual
                    && !members.contains(selector.selected.as_str()))
            {
                return Err("SelectorMembers");
            }
        }
        self.validate_policies()?;
        for rule in &self.rules {
            if !ids.contains(rule.outbound.as_str())
                && !selector_ids.contains(rule.outbound.as_str())
            {
                return Err("RuleNodeMissing");
            }
            match &rule.matcher {
                Matcher::Domain { value } | Matcher::DomainSuffix { value }
                    if !valid_host(value) =>
                {
                    return Err("RuleDomain");
                }
                Matcher::DomainKeyword { value }
                    if value.is_empty()
                        || value.len() > 253
                        || !value
                            .bytes()
                            .all(|b| b.is_ascii_alphanumeric() || b".-_".contains(&b)) =>
                {
                    return Err("RuleKeyword");
                }
                Matcher::DestinationPort { value: 0 } => return Err("RulePort"),
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
    fn socks5_udp_is_explicit_and_never_weakens_tls() {
        for (extra, udp) in [
            ("", false),
            (",\"udp\":false", false),
            (",\"udp\":true", true),
        ] {
            let document = format!(
                r#"{{"schema":1,"listen":"127.0.0.1:0","selected":"s","nodes":[{{"id":"s","outbound":{{"type":"socks5","host":"proxy.fixture.test","port":1080{extra}}}}}]}}"#
            );
            let config = Config::parse(document.as_bytes()).unwrap();
            assert!(
                matches!(&config.nodes[0].outbound, Outbound::Socks5 { udp: actual, .. } if *actual == udp)
            );
            let tls =
                document.replace("1080", r#"1080,"tls":{"server_name":"proxy.fixture.test"}"#);
            if udp {
                assert!(matches!(
                    Config::parse(tls.as_bytes()),
                    Err("Socks5UdpTlsUnsupported")
                ));
            } else {
                assert!(Config::parse(tls.as_bytes()).is_ok());
            }
        }
    }
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
    #[test]
    fn selectors_reject_missing_duplicate_nested_and_unknown_members() {
        for selector in [
            r#"{"id":"d","members":["d"],"selected":"d"}"#,
            r#"{"id":"g","members":[],"selected":"d"}"#,
            r#"{"id":"g","members":["d","d"],"selected":"d"}"#,
            r#"{"id":"g","members":["d"],"selected":"missing"}"#,
            r#"{"id":"g","members":["g"],"selected":"g"}"#,
            r#"{"id":"g","members":["d"],"selected":"d","type":"fallback"}"#,
        ] {
            let data = format!(
                r#"{{"schema":1,"listen":"127.0.0.1:0","selected":"d","nodes":[{{"id":"d","outbound":{{"type":"direct"}}}}],"selectors":[{selector}]}}"#
            );
            assert!(
                Config::parse(data.as_bytes()).is_err(),
                "accepted {selector}"
            );
        }
    }
    #[test]
    fn dns_rejects_ambiguous_mapping_and_unknown_settings() {
        for dns in [
            r#"{"hosts":[{"name":"a.test","address":"127.0.0.1"},{"name":"A.test","address":"::1"}]}"#,
            r#"{"hosts":[{"name":"*.test","address":"127.0.0.1"}]}"#,
            r#"{"hosts":[{"name":"127.0.0.1","address":"::1"}]}"#,
            r#"{"hosts":[{"name":"a.test","address":"not-ip"}]}"#,
            r#"{"hosts":[{"name":"a.test","address":"127.0.0.1","server":"other"}]}"#,
            r#"{"force_proxy_hosts":"true"}"#,
            r#"{"nameserver":"unknown"}"#,
            r#"{"servers":["127.0.0.1:0"]}"#,
            r#"{"servers":["0.0.0.0:53"]}"#,
            r#"{"servers":["224.0.0.1:53"]}"#,
            r#"{"servers":["127.0.0.1:53","127.0.0.1:53"]}"#,
            r#"{"use_system_hosts":false}"#,
        ] {
            let data = format!(
                r#"{{"schema":1,"listen":"127.0.0.1:0","selected":"d","nodes":[{{"id":"d","outbound":{{"type":"direct"}}}}],"dns":{dns}}}"#
            );
            assert!(Config::parse(data.as_bytes()).is_err(), "accepted {dns}");
        }
    }
    #[test]
    fn invalid_routing_fields_fail_before_activation() {
        for kind in ["direct", "reject"] {
            let data = format!(
                r#"{{"schema":1,"listen":"127.0.0.1:0","selected":"d","nodes":[{{"id":"d","outbound":{{"type":"{kind}","unmapped":"value"}}}}]}}"#
            );
            assert!(
                Config::parse(data.as_bytes()).is_err(),
                "unknown {kind} field accepted"
            );
        }
        for matcher in [
            r#"{"type":"destination_port","value":0}"#,
            r#"{"type":"destination_port","value":65536}"#,
            r#"{"type":"domain_keyword","value":""}"#,
            r#"{"type":"domain_keyword","value":"bad\\nkeyword"}"#,
            r#"{"type":"source_cidr","value":"127.0.0.1/33"}"#,
            r#"{"type":"cidr","value":"127.0.0.0/8","resolve":"false"}"#,
            r#"{"type":"match","ignored":"field"}"#,
        ] {
            let data = format!(
                r#"{{"schema":1,"listen":"127.0.0.1:0","selected":"d","nodes":[{{"id":"d","outbound":{{"type":"direct"}}}}],"rules":[{{"matcher":{matcher},"outbound":"d"}}]}}"#
            );
            assert!(
                Config::parse(data.as_bytes()).is_err(),
                "accepted {matcher}"
            );
        }
    }
}
