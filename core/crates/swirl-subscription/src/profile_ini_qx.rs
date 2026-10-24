//! Quantumult X has a different grammar from Surge/Loon. Map its explicit local
//! policies and filters; never treat all INI dialects as the same schema.
//! Primary reference: https://github.com/crossutility/Quantumult-X/blob/master/sample.conf
use super::{ProfileError, builtin, fail, fields, group_depth, ini_section, metadata, name};
use serde_json::{Map, Value, json};
use std::collections::{HashMap, HashSet};

fn policy(text: &str) -> Result<String, ProfileError> {
    if text.eq_ignore_ascii_case("direct") {
        Ok("DIRECT".into())
    } else if text.eq_ignore_ascii_case("reject") {
        // QX also synthesizes a DNS answer for rejected domains. A plain TCP
        // reject would lose that behavior; do not silently claim equivalence.
        Err(fail("ProfileQuantumultDnsRejectUnsupported"))
    } else if text.eq_ignore_ascii_case("proxy") {
        Ok("PROXY".into())
    } else if name(text) {
        Ok(text.into())
    } else {
        Err(fail("ProfileIniUnknownPolicy"))
    }
}

pub(super) fn project(text: &str) -> Result<Value, ProfileError> {
    let mut metadata = metadata::Metadata::default();
    let mut section = String::new();
    let mut sections = HashSet::new();
    let mut nodes = Vec::new();
    let mut node_names = HashSet::new();
    let mut groups = Vec::new();
    let mut group_names = HashSet::new();
    let mut rules = Vec::new();
    let mut hosts = Map::new();
    let mut dns_plain = Vec::new();
    let mut dns_encrypted = Vec::new();
    let mut no_ipv6 = false;
    let mut no_system = false;
    let mut dns_flags = HashSet::new();
    let mut general = HashSet::new();
    let first = text.lines().map(str::trim).find(|line| !line.is_empty());
    for line in text.lines().map(str::trim) {
        if line.starts_with("#!MANAGED-CONFIG") {
            metadata.managed(line, first == Some(line))?;
            continue;
        }
        if line.is_empty() || line.starts_with(['#', ';']) || line.starts_with("//") {
            continue;
        }
        if let Some(next) = ini_section(line).map_err(|_| fail("ProfileIniSection"))? {
            if !sections.insert(next.clone()) || sections.len() > 16 {
                return Err(fail("ProfileIniDuplicateSection"));
            }
            section = next;
            continue;
        }
        if section == "filter_local" {
            let mut parts = fields(line)?;
            if parts.iter().any(|part| part.contains(',')) {
                return Err(fail("ProfileRuleType"));
            }
            let (kind, target_index) =
                match parts.first().map(|s| s.to_ascii_lowercase()).as_deref() {
                    Some("host") => ("DOMAIN", 2),
                    Some("host-suffix") => ("DOMAIN-SUFFIX", 2),
                    Some("host-keyword") => ("DOMAIN-KEYWORD", 2),
                    Some("ip-cidr") => ("IP-CIDR", 2),
                    Some("ip6-cidr") => ("IP-CIDR6", 2),
                    Some("final") => ("MATCH", 1),
                    _ => return Err(fail("ProfileQuantumultFilterUnsupported")),
                };
            if parts.len() != target_index + 1 {
                return Err(fail("ProfileQuantumultFilterUnsupported"));
            }
            parts[0] = kind.into();
            parts[target_index] = policy(&parts[target_index])?;
            rules.push(Value::String(parts.join(",")));
            if rules.len() > 1000 {
                return Err(fail("ProfileRulesRequired"));
            }
            continue;
        }
        if section == "dns" && matches!(line, "no-ipv6" | "no-system") {
            if !dns_flags.insert(line) {
                return Err(fail("ProfileIniDuplicateOption"));
            }
            no_ipv6 |= line == "no-ipv6";
            no_system |= line == "no-system";
            continue;
        }
        if matches!(
            section.as_str(),
            "script" | "mitm" | "rewrite_local" | "rewrite_remote" | "task_local" | "http_backend"
        ) {
            return Err(fail("ProfileIniUnsafeSection"));
        }
        let (raw_key, raw_value) = line
            .split_once('=')
            .ok_or_else(|| fail("ProfileIniAssignment"))?;
        let key = raw_key.trim();
        let value = raw_value.trim();
        match section.as_str() {
            "general" => {
                let key = key.to_ascii_lowercase();
                if !general.insert(key.clone()) {
                    return Err(fail("ProfileIniDuplicateOption"));
                }
                if !metadata.general(&key, value)? {
                    return Err(fail(
                        if matches!(key.as_str(), "resource_parser_url" | "geo_location_checker") {
                            "ProfileIniScriptUnsupported"
                        } else {
                            "ProfileIniGeneralUnsupported"
                        },
                    ));
                }
            }
            "server_local" => {
                let parts = fields(value)?;
                let tags: Vec<_> = parts
                    .iter()
                    .filter_map(|part| part.split_once('='))
                    .filter(|(key, _)| key.trim() == "tag")
                    .map(|(_, value)| value.trim())
                    .collect();
                if tags.len() != 1
                    || !name(tags[0])
                    || matches!(tags[0], "SWIRL" | "GLOBAL")
                    || ["direct", "reject", "proxy"]
                        .iter()
                        .any(|p| tags[0].eq_ignore_ascii_case(p))
                    || !node_names.insert(tags[0].to_owned())
                    || nodes.len() >= 512
                {
                    return Err(fail("ProfileIniNodeName"));
                }
                nodes.push(tags[0].to_owned());
            }
            "policy" => {
                // Automatic QX policies have different timing/refresh/scoring
                // semantics from the native engine. Only static is lossless.
                if !key.eq_ignore_ascii_case("static") {
                    return Err(fail("ProfileIniGroupUnsupported"));
                }
                let parts = fields(value)?;
                let group_name = parts.first().ok_or_else(|| fail("ProfileIniGroupName"))?;
                if !name(group_name)
                    || matches!(group_name.as_str(), "SWIRL" | "GLOBAL")
                    || ["direct", "reject", "proxy"]
                        .iter()
                        .any(|p| group_name.eq_ignore_ascii_case(p))
                    || !group_names.insert(group_name.clone())
                    || groups.len() >= 127
                {
                    return Err(fail("ProfileIniGroupName"));
                }
                let mut members = Vec::new();
                let mut seen = HashSet::new();
                for member in &parts[1..] {
                    if let Some((key, value)) = member.split_once('=') {
                        if key.trim() != "img-url"
                            || !metadata.general("group-icon", value.trim())?
                        {
                            return Err(fail("ProfileIniGroupUnsupported"));
                        }
                        continue;
                    }
                    let member = policy(member)?;
                    if !seen.insert(member.clone()) || members.len() >= 512 {
                        return Err(fail("ProfileIniGroupMember"));
                    }
                    members.push(member);
                }
                if members.is_empty() {
                    return Err(fail("ProfileIniGroupMember"));
                }
                groups.push(json!({"name":group_name,"type":"select","proxies":members}));
            }
            "dns" => match key {
                "server" => {
                    for server in fields(value)? {
                        // No SSID/domain conditions, nonstandard ports or
                        // implicit system resolver substitution.
                        let server = if let Ok(address) = server.parse::<std::net::IpAddr>() {
                            address.to_string()
                        } else if let Ok(address) = server.parse::<std::net::SocketAddr>() {
                            if address.port() != 53 {
                                return Err(fail("ProfileIniDnsTransportMismatch"));
                            }
                            address.ip().to_string()
                        } else {
                            return Err(fail("ProfileIniDnsTransportMismatch"));
                        };
                        dns_plain.push(server);
                    }
                }
                "doh-server" => {
                    if !dns_encrypted.is_empty() {
                        return Err(fail("ProfileIniDuplicateOption"));
                    }
                    for server in fields(value)? {
                        if !url::Url::parse(&server).is_ok_and(|u| u.scheme() == "https") {
                            return Err(fail("ProfileIniDnsTransportMismatch"));
                        }
                        dns_encrypted.push(server);
                    }
                }
                "address" => {
                    let parts: Vec<_> = value.split('/').collect();
                    if parts.len() != 3
                        || !parts[0].is_empty()
                        || !crate::valid_host(parts[1])
                        || parts[1].parse::<std::net::IpAddr>().is_ok()
                    {
                        return Err(fail("ProfileDnsExactHostsRequired"));
                    }
                    let address = parts[2]
                        .trim_matches(['[', ']'])
                        .parse::<std::net::IpAddr>()
                        .map_err(|_| fail("ProfileDnsExactHostsRequired"))?;
                    if address.is_loopback()
                        || hosts.len() >= 512
                        || hosts
                            .insert(parts[1].to_ascii_lowercase(), json!(address.to_string()))
                            .is_some()
                    {
                        return Err(fail("ProfileDnsExactHostsRequired"));
                    }
                }
                _ => return Err(fail("ProfileQuantumultDnsUnsupported")),
            },
            "script" | "mitm" | "rewrite_local" | "rewrite_remote" | "task_local"
            | "http_backend" => return Err(fail("ProfileIniUnsafeSection")),
            "server_remote" | "filter_remote" => {
                return Err(fail("ProfileIniRemoteResourceUnsupported"));
            }
            _ => return Err(fail("ProfileIniSectionUnsupported")),
        }
    }
    if !nodes.is_empty() && !super::super::has_profile_semantics("ini", &json!({"document":text})) {
        let mut projected = json!({});
        metadata.finish(&mut projected);
        return Ok(projected);
    }
    if nodes.is_empty() || !sections.contains("filter_local") {
        return Err(fail("ProfileIniCompleteRulesRequired"));
    }
    // The built-in QX proxy is a manual choice over this document's local
    // nodes, never an alias to an unrelated saved node or DIRECT.
    let uses_proxy = groups.iter().any(|g| {
        g["proxies"]
            .as_array()
            .is_some_and(|a| a.contains(&json!("PROXY")))
    }) || rules.iter().any(|r| {
        r.as_str()
            .is_some_and(|s| s.rsplit(',').next() == Some("PROXY"))
    });
    if uses_proxy {
        group_names.insert("PROXY".into());
        groups.push(json!({"name":"PROXY","type":"select","proxies":nodes}));
    }
    let mut edges = HashMap::new();
    for group in &groups {
        let group_name = group["name"].as_str().unwrap_or("");
        if node_names.contains(group_name) {
            return Err(fail("ProfileIniGroupName"));
        }
        for member in group["proxies"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
        {
            if !builtin(member) && !node_names.contains(member) && !group_names.contains(member) {
                return Err(fail("ProfileIniUnknownPolicy"));
            }
            if group_names.contains(member) {
                edges
                    .entry(group_name.to_owned())
                    .or_insert_with(Vec::new)
                    .push(member.to_owned());
            }
        }
    }
    for group_name in &group_names {
        group_depth(group_name, &edges, &mut HashSet::new(), &mut HashMap::new())?;
    }
    for rule in &rules {
        let target = rule.as_str().unwrap_or("").rsplit(',').next().unwrap_or("");
        if !builtin(target) && !node_names.contains(target) && !group_names.contains(target) {
            return Err(fail("ProfileIniUnknownPolicy"));
        }
    }
    let mut source = json!({"proxy-groups":groups,"rules":rules});
    if !hosts.is_empty() {
        source["hosts"] = Value::Object(hosts);
    }
    if sections.contains("dns") {
        let servers = if dns_encrypted.is_empty() {
            if !no_system {
                return Err(fail("ProfileQuantumultSystemDnsUnsupported"));
            }
            dns_plain
        } else {
            // QX ignores unbound plain/system servers when DoH is present.
            // They are not a plaintext fallback. The shared DNS validator
            // still requires an explicit bootstrap address for DoH names.
            dns_encrypted
        };
        if servers.is_empty() {
            return Err(fail("ProfileIniDnsServerRequired"));
        }
        source["dns"] = json!({"enable":true,"nameserver":servers,"ipv6":!no_ipv6});
    }
    let mut projected = super::super::project(&source)?;
    metadata.finish(&mut projected);
    Ok(projected)
}
