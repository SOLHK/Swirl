//! Restricted complete INI profiles. Original text belongs to the encrypted
//! catalog. This module performs no requests, file access or host operations.
//! References: https://manual.nssurge.com/profile/general.html
//! https://manual.nssurge.com/policy-groups/select.html
//! https://nsloon.app/en/docs/General/
use super::{ProfileError, error};
use crate::inspect::{clean_ini, csv, ini_section};
use serde_json::{Map, Value, json};
use std::collections::{HashMap, HashSet};
#[path = "profile_ini_metadata.rs"]
mod metadata;
#[path = "profile_ini_qx.rs"]
mod qx;

pub(super) fn client_setting_safe(key: &str, value: &str) -> bool {
    metadata::Metadata::default().general(key, value) == Ok(true)
}

fn fail(code: &'static str) -> ProfileError {
    // INI arbitrary names, keys and values may all contain credentials.
    error(code, "configuration")
}

fn fields(text: &str) -> Result<Vec<String>, ProfileError> {
    csv(text)
        .map(|items| items.into_iter().map(|(value, _)| value).collect())
        .map_err(|_| fail("ProfileIniQuotation"))
}

fn name(text: &str) -> bool {
    !text.is_empty()
        && text.len() <= 512
        && !text.contains([',', '='])
        && !text.chars().any(char::is_control)
}

fn builtin(text: &str) -> bool {
    matches!(text, "DIRECT" | "REJECT")
}

fn bool_value(text: &str) -> Result<bool, ProfileError> {
    match text.to_ascii_lowercase().as_str() {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(fail("ProfileIniBoolean")),
    }
}

fn group_depth(
    name: &str,
    edges: &HashMap<String, Vec<String>>,
    visiting: &mut HashSet<String>,
    depths: &mut HashMap<String, usize>,
) -> Result<usize, ProfileError> {
    if let Some(depth) = depths.get(name) {
        return Ok(*depth);
    }
    if !visiting.insert(name.into()) {
        return Err(fail("ProfileIniGroupCycle"));
    }
    let mut depth = 1;
    for member in edges.get(name).into_iter().flatten() {
        depth = depth.max(group_depth(member, edges, visiting, depths)? + 1);
        if depth > 16 {
            return Err(fail("ProfileIniGroupDepth"));
        }
    }
    visiting.remove(name);
    depths.insert(name.into(), depth);
    Ok(depth)
}

pub(super) fn project(configuration: &Value) -> Result<Value, ProfileError> {
    let wrapper = configuration
        .as_object()
        .ok_or_else(|| fail("ProfileFieldType"))?;
    if wrapper.len() != 1 || !wrapper.contains_key("document") {
        return Err(fail("ProfileIniDocumentRequired"));
    }
    let text = wrapper["document"]
        .as_str()
        .filter(|text| !text.is_empty() && text.len() <= 4 * 1024 * 1024)
        .ok_or_else(|| fail("ProfileIniDocumentRequired"))?;
    if text
        .chars()
        .any(|c| c.is_control() && !matches!(c, '\t' | '\r' | '\n'))
    {
        return Err(fail("ProfileIniControlCharacter"));
    }
    if text
        .lines()
        .any(|line| ini_section(line.trim()).ok().flatten().as_deref() == Some("server_local"))
    {
        return qx::project(text);
    }
    let mut metadata = metadata::Metadata::default();
    let mut seen_general = HashSet::new();
    let first_line = text.lines().map(str::trim).find(|line| !line.is_empty());
    let mut section = String::new();
    let mut sections = HashSet::new();
    let mut nodes = HashSet::new();
    let mut groups = Vec::new();
    let mut group_names = HashSet::new();
    let mut rules = Vec::new();
    let mut hosts = Map::new();
    let mut general = HashMap::new();
    for line in text.lines().map(str::trim) {
        if line.starts_with("#!MANAGED-CONFIG") {
            metadata.managed(line, first_line == Some(line))?;
            continue;
        }
        if line.is_empty() || line.starts_with(['#', ';']) || line.starts_with("//") {
            continue;
        }
        if let Some(next) = ini_section(line).map_err(|_| fail("ProfileIniSection"))? {
            if !sections.insert(next.clone()) || sections.len() > 8 {
                return Err(fail("ProfileIniDuplicateSection"));
            }
            if matches!(next.as_str(), "script" | "mitm" | "url rewrite" | "plugin") {
                return Err(fail("ProfileIniUnsafeSection"));
            }
            if !matches!(
                next.as_str(),
                "general" | "proxy" | "proxy group" | "rule" | "host"
            ) {
                return Err(fail("ProfileIniSectionUnsupported"));
            }
            section = next;
            continue;
        }
        if section == "rule" {
            let mut parts = fields(line)?;
            if parts.iter().any(|field| field.contains(',')) {
                return Err(fail("ProfileRuleType"));
            }
            let first = parts.first_mut().ok_or_else(|| fail("ProfileRuleType"))?;
            *first = first.to_ascii_uppercase();
            if first == "FINAL" {
                *first = "MATCH".into();
            }
            rules.push(Value::String(parts.join(",")));
            if rules.len() > 1000 {
                return Err(fail("ProfileRulesRequired"));
            }
            continue;
        }
        let (raw_key, raw_value) = line
            .split_once('=')
            .ok_or_else(|| fail("ProfileIniAssignment"))?;
        let key = clean_ini(raw_key);
        let value = raw_value.trim();
        match section.as_str() {
            "general" => {
                let key = key.to_ascii_lowercase();
                if !seen_general.insert(key.clone()) {
                    return Err(fail("ProfileIniDuplicateOption"));
                }
                if !matches!(
                    key.as_str(),
                    "dns-server" | "ipv6" | "doh-server" | "encrypted-dns-server"
                ) {
                    if metadata.general(&key, value)? {
                        continue;
                    }
                    if matches!(
                        key.as_str(),
                        "resource-parser" | "resource_parser_url" | "geo_location_checker"
                    ) {
                        return Err(fail("ProfileIniScriptUnsupported"));
                    }
                    if matches!(
                        key.as_str(),
                        "http-api" | "external-controller-access" | "http-listen" | "socks5-listen"
                    ) {
                        return Err(fail("ProfileIniListenerUnsupported"));
                    }
                    if matches!(
                        key.as_str(),
                        "skip-proxy"
                            | "bypass-tun"
                            | "include-tun"
                            | "tun-included-routes"
                            | "tun-excluded-routes"
                            | "interface-mode"
                    ) {
                        return Err(fail("ProfileIniSystemNetworkUnsupported"));
                    }
                    return Err(fail("ProfileIniGeneralUnsupported"));
                }
                if general.insert(key, value.to_string()).is_some() {
                    return Err(fail("ProfileIniDuplicateOption"));
                }
            }
            "proxy" => {
                if !name(&key) || !nodes.insert(key.clone()) || nodes.len() > 2000 {
                    return Err(fail("ProfileIniNodeName"));
                }
                let parts = fields(value)?;
                let kind = parts
                    .first()
                    .map(|s| s.to_ascii_lowercase())
                    .unwrap_or_default();
                if matches!(kind.as_str(), "direct" | "reject") {
                    if parts.len() != 1 || key != kind.to_ascii_uppercase() {
                        return Err(fail("ProfileIniBuiltinAliasUnsupported"));
                    }
                } else if builtin(&key)
                    || matches!(key.as_str(), "SWIRL" | "GLOBAL")
                    || parts.len() < 3
                {
                    return Err(fail("ProfileIniNodeName"));
                }
            }
            "proxy group" => {
                let parts = fields(value)?;
                if !name(&key)
                    || builtin(&key)
                    || matches!(key.as_str(), "SWIRL" | "GLOBAL")
                    || !group_names.insert(key.clone())
                    || group_names.len() > 128
                {
                    return Err(fail("ProfileIniGroupName"));
                }
                // Automatic groups differ by client in scoring, timeout,
                // refresh and default URL semantics. Do not guess equivalence.
                if parts
                    .first()
                    .is_none_or(|kind| !kind.eq_ignore_ascii_case("select"))
                    || parts.len() < 2
                {
                    return Err(fail("ProfileIniGroupUnsupported"));
                }
                let mut seen = HashSet::new();
                for member in &parts[1..] {
                    if !name(member) || !seen.insert(member.clone()) || seen.len() > 512 {
                        return Err(fail("ProfileIniGroupMember"));
                    }
                }
                groups.push(json!({"name":key,"type":"select","proxies":parts[1..]}));
            }
            "host" => {
                let address = clean_ini(value);
                if !crate::valid_host(&key)
                    || key.parse::<std::net::IpAddr>().is_ok()
                    || address.parse::<std::net::IpAddr>().is_err()
                    || hosts.len() >= 512
                    || hosts
                        .insert(key.to_ascii_lowercase(), Value::String(address))
                        .is_some()
                {
                    return Err(fail("ProfileDnsExactHostsRequired"));
                }
            }
            _ => return Err(fail("ProfileIniMissingSection")),
        }
    }
    if !nodes.is_empty() && !super::has_profile_semantics("ini", configuration) {
        let mut projected = json!({});
        metadata.finish(&mut projected);
        return Ok(projected);
    }
    if !sections.contains("proxy") || !sections.contains("rule") || nodes.is_empty() {
        return Err(fail("ProfileIniCompleteRulesRequired"));
    }
    let mut edges = HashMap::new();
    for group in &groups {
        let group_name = group["name"].as_str().unwrap_or("");
        if nodes.contains(group_name) {
            return Err(fail("ProfileIniGroupName"));
        }
        for member in group["proxies"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
        {
            if !builtin(member) && !nodes.contains(member) && !group_names.contains(member) {
                return Err(fail("ProfileIniUnknownPolicy"));
            }
            if group_names.contains(member) {
                edges
                    .entry(group_name.to_string())
                    .or_insert_with(Vec::new)
                    .push(member.to_string());
            }
        }
    }
    let mut depths = HashMap::new();
    for name in &group_names {
        group_depth(name, &edges, &mut HashSet::new(), &mut depths)?;
    }
    for rule in &rules {
        let parts: Vec<_> = rule.as_str().unwrap_or("").split(',').collect();
        let target = parts
            .get(if parts.first() == Some(&"MATCH") {
                1
            } else {
                2
            })
            .ok_or_else(|| fail("ProfileRuleType"))?;
        if !builtin(target) && !nodes.contains(*target) && !group_names.contains(*target) {
            return Err(fail("ProfileIniUnknownPolicy"));
        }
    }
    let mut source = json!({"proxy-groups":groups,"rules":rules});
    if !hosts.is_empty() {
        source["hosts"] = Value::Object(hosts);
    }
    if !general.is_empty() {
        // These INI dialects disagree on the default family, and modern Loon
        // uses ip-mode. Do not infer IPv6 from a generic format label.
        let ipv6 = general
            .get("ipv6")
            .ok_or_else(|| fail("ProfileIniDnsFamilyRequired"))
            .and_then(|value| bool_value(value))?;
        let plain = general.get("dns-server");
        let encrypted = general
            .get("doh-server")
            .or_else(|| general.get("encrypted-dns-server"));
        if general.contains_key("doh-server") && general.contains_key("encrypted-dns-server") {
            return Err(fail("ProfileIniDuplicateOption"));
        }
        if plain.is_some() && encrypted.is_some() {
            return Err(fail("ProfileIniMixedDnsUnsupported"));
        }
        let servers = plain
            .or(encrypted)
            .ok_or_else(|| fail("ProfileIniDnsServerRequired"))?;
        let servers = fields(servers)?;
        if servers
            .iter()
            .any(|value| value.eq_ignore_ascii_case("system"))
        {
            return Err(fail("ProfileIniSystemDnsUnsupported"));
        }
        // The shared Clash-shaped nameserver field accepts multiple resolver
        // transports. Preserve the stronger source-key requirement before
        // entering it: a DoH declaration must never turn into plaintext UDP.
        for server in &servers {
            let valid_transport = if plain.is_some() {
                // Custom plaintext ports are not yet represented by this
                // profile projection; do not reinterpret them as URL schemes.
                server.parse::<std::net::IpAddr>().is_ok()
            } else {
                url::Url::parse(server).is_ok_and(|url| {
                    if general.contains_key("doh-server") {
                        url.scheme() == "https"
                    } else {
                        matches!(url.scheme(), "https" | "tls")
                    }
                })
            };
            if !valid_transport {
                return Err(fail("ProfileIniDnsTransportMismatch"));
            }
        }
        source["dns"] = json!({"enable":true,"nameserver":servers,"ipv6":ipv6});
    }
    let mut projected = super::project(&source)?;
    metadata.finish(&mut projected);
    Ok(projected)
}

#[cfg(test)]
#[path = "profile_ini_tests.rs"]
mod tests;
