//! Strict external profile projection. No host APIs, requests or file access.
//! The product shell persists this result together with the imported nodes.
use crate::{Dns, DnsQueryFamily, DnsTlsServer, HostMapping, Tls, valid_host};
use serde_json::{Map, Value, json};
use std::{
    collections::HashSet,
    net::{IpAddr, SocketAddr},
};
#[path = "profile_ini.rs"]
mod ini;
#[path = "profile_scope.rs"]
mod scope;
#[path = "singbox_profile.rs"]
mod singbox;

/// Whether an external document declares non-node network semantics. This is a
/// classifier, not permission to execute source fields. Full projection and
/// data-only canonical node extraction have separate validation boundaries.
pub fn has_profile_semantics(format: &str, configuration: &Value) -> bool {
    scope::has_semantics(format, configuration)
}

/// Bound the source shape before a complete-profile failure becomes an explicit
/// DATA-ONLY nodes result. This flag never authorizes ANY source-global behavior:
/// callers must independently validate canonical nodes, keep current native
/// DNS/rules/groups and preserve all foreign settings only as inert encrypted
/// provenance. Script, file, listener and provider declarations are never run,
/// opened, fetched or implicitly promoted by this extraction path. Their full
/// execution remains rejected by the separate strict projection boundary.
pub fn node_only_fallback_allowed(format: &str, configuration: &Value) -> bool {
    scope::node_only_allowed(format, configuration)
}

pub fn project_format(format: &str, configuration: &Value) -> Result<Value, ProfileError> {
    match format {
        "ini" if configuration.get("document").is_some() => ini::project(configuration),
        "clash" | "ini" => project(configuration),
        "sing-box" => singbox::project(configuration),
        _ => Err(error("ProfileFormatUnsupported", "format")),
    }
}

#[derive(Debug, PartialEq, Eq)]
pub struct ProfileError {
    pub code: &'static str,
    pub field: String,
}

fn error(code: &'static str, field: &str) -> ProfileError {
    // Keys are untrusted too. Never expose source values, URLs or arbitrary
    // object keys through a compatibility diagnostic.
    // Even identifier-shaped unknown keys can be tokens. Only names from the
    // client schema may enter a public path; arbitrary keys become `unknown`.
    const KNOWN: &[&str] = &[
        "configuration",
        "format",
        "dns",
        "enable",
        "nameserver",
        "ipv6",
        "use-hosts",
        "respect-rules",
        "enhanced-mode",
        "hosts",
        "rules",
        "proxy-groups",
        "type",
        "filter",
        "name",
        "proxies",
        "outbounds",
        "tag",
        "default",
        "route",
        "rule_set",
        "action",
        "outbound",
        "domain",
        "domain_suffix",
        "domain_keyword",
        "source_ip_cidr",
        "port",
        "servers",
        "final",
        "strategy",
        "server",
        "server_port",
        "address",
        "fallback",
        "fallback-filter",
        "nameserver-policy",
        "default-nameserver",
        "fake-ip-range",
        "fake-ip-filter",
        "timeout",
        "interval",
        "url",
        "expected-status",
        "tolerance",
        "default-selected",
        "interrupt_exist_connections",
        "detour",
        "server_name",
        "tls",
        "log",
        "inbounds",
        "mixed-port",
        "mode",
        "allow-lan",
        "external-controller",
        "secret",
        "tun",
        "sniffer",
        "profile",
        "rule-providers",
        "proxy-providers",
    ];
    let mut parts = Vec::new();
    for part in field.split('.') {
        if KNOWN.contains(&part) {
            parts.push(part);
        } else if parts.is_empty() {
            parts.push("configuration");
            break;
        } else {
            parts.push("unknown");
            break;
        }
    }
    let field = parts.join(".");
    ProfileError { code, field }
}

fn boolean(object: &Map<String, Value>, key: &str, fallback: bool) -> Result<bool, ProfileError> {
    object.get(key).map_or(Ok(fallback), |value| {
        value
            .as_bool()
            .ok_or_else(|| error("ProfileFieldType", key))
    })
}

fn usable(address: IpAddr) -> bool {
    !address.is_unspecified() && !address.is_multicast()
}

fn dns(configuration: &Map<String, Value>) -> Result<Value, ProfileError> {
    let empty = Map::new();
    let source = configuration.get("dns").map_or(Ok(&empty), |value| {
        value
            .as_object()
            .ok_or_else(|| error("ProfileFieldType", "dns"))
    })?;
    for key in source.keys() {
        if ![
            "enable",
            "nameserver",
            "ipv6",
            "use-hosts",
            "respect-rules",
            "enhanced-mode",
        ]
        .contains(&key.as_str())
        {
            return Err(error("ProfileDnsFieldUnsupported", &format!("dns.{key}")));
        }
    }
    if configuration.contains_key("dns") && !boolean(source, "enable", false)? {
        // Disabling Clash's DNS listener does not mean discarding its resolver
        // semantics. The native core has no equivalent disabled DNS service.
        return Err(error("ProfileDnsDisabledUnsupported", "dns.enable"));
    }
    if source.contains_key("enhanced-mode") && source["enhanced-mode"].as_str() != Some("normal") {
        return Err(error("ProfileDnsModeUnsupported", "dns.enhanced-mode"));
    }
    if boolean(source, "respect-rules", false)? {
        // Native force_proxy_hosts is a different policy; do not conflate it
        // with routing the DNS upstream's own connection through proxy groups.
        return Err(error(
            "ProfileDnsRuleRoutingUnsupported",
            "dns.respect-rules",
        ));
    }
    let use_hosts = boolean(source, "use-hosts", true)?;
    // Clash defaults DNS ipv6 to false. A hosts-only root has no DNS dialect
    // whose defaults should replace the native resolver's dual-stack policy.
    let family = if boolean(source, "ipv6", !configuration.contains_key("dns"))? {
        DnsQueryFamily::Dual
    } else {
        DnsQueryFamily::Ipv4Only
    };
    let mut native = Dns {
        use_system_hosts: use_hosts,
        query_family: family,
        ..Dns::default()
    };
    let mut host_rows = Vec::new();
    if let Some(hosts) = configuration.get("hosts") {
        if !use_hosts {
            return Err(error("ProfileDnsHostsDisabled", "dns.use-hosts"));
        }
        let hosts = hosts
            .as_object()
            .ok_or_else(|| error("ProfileFieldType", "hosts"))?;
        let mut seen = HashSet::new();
        if hosts.len() > 512 {
            return Err(error("ProfileDnsHostsLimit", "hosts"));
        }
        for (name, value) in hosts {
            let normalized = name.to_ascii_lowercase();
            let address = value
                .as_str()
                .and_then(|s| s.parse::<IpAddr>().ok())
                .ok_or_else(|| error("ProfileDnsExactHostsRequired", "hosts"))?;
            if !valid_host(name)
                || name.parse::<IpAddr>().is_ok()
                || !seen.insert(normalized.clone())
            {
                return Err(error("ProfileDnsExactHostsRequired", "hosts"));
            }
            native.hosts.push(HostMapping {
                name: normalized.clone(),
                address,
            });
            host_rows.push(json!({"name":normalized,"value":address.to_string()}));
        }
    }
    let mut plain = Vec::new();
    let mut encrypted = String::new();
    if let Some(servers) = source.get("nameserver") {
        let servers = servers
            .as_array()
            .filter(|s| !s.is_empty() && s.len() <= 4)
            .ok_or_else(|| error("ProfileDnsServerList", "dns.nameserver"))?;
        let mut seen = HashSet::new();
        for value in servers {
            let text = value
                .as_str()
                .ok_or_else(|| error("ProfileFieldType", "dns.nameserver"))?;
            if !seen.insert(text) {
                return Err(error("ProfileDnsDuplicateServer", "dns.nameserver"));
            }
            if let Ok(address) = text.parse::<IpAddr>() {
                if !usable(address) {
                    return Err(error("ProfileDnsServerAddress", "dns.nameserver"));
                }
                native.servers.push(SocketAddr::new(address, 53));
                plain.push(address.to_string());
                continue;
            }
            let url = url::Url::parse(text)
                .map_err(|_| error("ProfileDnsServerUnsupported", "dns.nameserver"))?;
            let https = url.scheme() == "https";
            if (!https && url.scheme() != "tls")
                || !url.username().is_empty()
                || url.password().is_some()
                || url.query().is_some()
                || url.fragment().is_some()
                || text.contains('\\')
                || !encrypted.is_empty()
            {
                return Err(error("ProfileDnsServerUnsupported", "dns.nameserver"));
            }
            let host = url.host_str().unwrap_or("").trim_matches(['[', ']']);
            let address = host
                .parse::<IpAddr>()
                .ok()
                .or_else(|| {
                    native
                        .hosts
                        .iter()
                        .find(|h| h.name.eq_ignore_ascii_case(host))
                        .map(|h| h.address)
                })
                .filter(|address| usable(*address))
                .ok_or_else(|| error("ProfileDnsBootstrapRequired", "dns.nameserver"))?;
            let port = url.port().unwrap_or(if https { 443 } else { 853 });
            if port == 0 || (!https && url.path() != "" && url.path() != "/") {
                return Err(error("ProfileDnsServerUnsupported", "dns.nameserver"));
            }
            native.tls_servers.push(DnsTlsServer {
                address: SocketAddr::new(address, port),
                tls: Tls {
                    server_name: host.to_owned(),
                    alpn: vec![if https { "http/1.1" } else { "dot" }.to_owned()],
                    ca_der_base64: None,
                },
                https_path: https.then(|| {
                    if url.path().is_empty() {
                        "/".to_owned()
                    } else {
                        url.path().to_owned()
                    }
                }),
            });
            encrypted = text.to_owned();
        }
    }
    if !plain.is_empty() && !encrypted.is_empty() {
        return Err(error(
            "ProfileDnsMixedResolversUnsupported",
            "dns.nameserver",
        ));
    }
    if native.servers.is_empty() && native.tls_servers.is_empty() && !use_hosts {
        return Err(error("ProfileDnsSystemHostsRequired", "dns.use-hosts"));
    }
    native
        .validate_query_family()
        .map_err(|code| error(code, "dns.ipv6"))?;
    native
        .validate_tls()
        .map_err(|code| error(code, "dns.nameserver"))?;
    Ok(
        json!({"mode":if plain.is_empty() {0} else {2},"servers":plain.join(","),"encrypted":encrypted,"hosts":host_rows,"useHosts":use_hosts,"respectRules":false,"queryFamily":if family == DnsQueryFamily::Dual {"dual"} else {"ipv4_only"}}),
    )
}

/// Project a normalized Clash-shaped complete profile. Client dialects without
/// a lossless profile projection must be rejected before entering this API.
pub fn project(configuration: &Value) -> Result<Value, ProfileError> {
    let source = configuration
        .as_object()
        .ok_or_else(|| error("ProfileFieldType", "configuration"))?;
    for key in source.keys() {
        // The Rust product exposes a fixed loopback listener and refuses LAN
        // mode. An explicit false restriction is already satisfied; true and
        // mistyped values cannot request a listener through a subscription.
        if key == "allow-lan" && source[key] == Value::Bool(false) {
            continue;
        }
        if !["proxy-groups", "rules", "dns", "hosts"].contains(&key.as_str()) {
            return Err(error("ProfileGlobalFieldUnsupported", key));
        }
    }
    let rules = source
        .get("rules")
        .and_then(Value::as_array)
        .filter(|rules| !rules.is_empty() && rules.len() <= 1000)
        .ok_or_else(|| error("ProfileRulesRequired", "rules"))?;
    for (index, value) in rules.iter().enumerate() {
        let rule = value
            .as_str()
            .filter(|s| s.len() <= 2300 && !s.chars().any(char::is_control))
            .ok_or_else(|| error("ProfileRuleType", "rules"))?;
        let fields: Vec<_> = rule.split(',').map(str::trim).collect();
        let kind = fields[0];
        if kind == "MATCH" {
            if fields.len() != 2 || fields[1].is_empty() || index + 1 != rules.len() {
                return Err(error("ProfileFinalRulePosition", "rules"));
            }
        } else if ![
            "DOMAIN",
            "DOMAIN-SUFFIX",
            "DOMAIN-KEYWORD",
            "IP-CIDR",
            "IP-CIDR6",
            "SRC-IP-CIDR",
            "DST-PORT",
        ]
        .contains(&kind)
            || (fields.len() != 3
                && !(matches!(kind, "IP-CIDR" | "IP-CIDR6")
                    && fields.len() == 4
                    && fields[3] == "no-resolve"))
            || fields.iter().any(|s| s.is_empty())
        {
            return Err(error("ProfileRuleUnsupported", "rules"));
        }
    }
    if !rules.last().and_then(Value::as_str).is_some_and(|rule| {
        rule.split(',')
            .next()
            .is_some_and(|kind| kind.trim() == "MATCH")
    }) {
        return Err(error("ProfileFinalRuleRequired", "rules"));
    }
    let mut projected = Map::new();
    projected.insert("rules".into(), Value::Array(rules.clone()));
    if let Some(groups) = source.get("proxy-groups") {
        let groups_array = groups
            .as_array()
            .filter(|groups| groups.len() <= 128)
            .ok_or_else(|| error("ProfileGroupType", "proxy-groups"))?;
        for group in groups_array {
            let group = group
                .as_object()
                .ok_or_else(|| error("ProfileGroupType", "proxy-groups"))?;
            let kind = group.get("type").and_then(Value::as_str).unwrap_or("");
            let allowed: &[&str] = if kind == "select" {
                &[
                    "name",
                    "type",
                    "proxies",
                    "default-selected",
                    "url",
                    "interval",
                ]
            } else if matches!(kind, "url-test" | "fallback" | "load-balance") {
                &[
                    "name",
                    "type",
                    "proxies",
                    "url",
                    "interval",
                    "timeout",
                    "expected-status",
                    "tolerance",
                    "strategy",
                ]
            } else {
                return Err(error("ProfileGroupUnsupported", "proxy-groups.type"));
            };
            for key in group.keys() {
                if !allowed.contains(&key.as_str()) {
                    return Err(error(
                        "ProfileGroupFieldUnsupported",
                        &format!("proxy-groups.{key}"),
                    ));
                }
            }
            if group.get("name").and_then(Value::as_str).is_none()
                || group
                    .get("proxies")
                    .and_then(Value::as_array)
                    .is_none_or(|members| {
                        members.is_empty() || members.iter().any(|v| !v.is_string())
                    })
            {
                return Err(error("ProfileGroupType", "proxy-groups"));
            }
        }
        projected.insert("groups".into(), groups.clone());
    }
    if source.contains_key("dns") || source.contains_key("hosts") {
        projected.insert("dns".into(), dns(source)?);
    }
    Ok(Value::Object(projected))
}

#[cfg(test)]
#[path = "profile_tests.rs"]
mod tests;
