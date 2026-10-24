//! Closed, offline scope/safety audit for automatic import. A recognized but
//! unsupported routing/DNS feature can preserve the user's current policy while
//! keeping valid nodes. Scripts, host operations and unknown capabilities cannot.
use crate::inspect::{csv, ini_section};
use serde_json::Value;

fn host_reference(text: &str, dns_expression: bool) -> bool {
    // Values can carry capabilities after a rule comma or key assignment, not
    // only at the beginning of a string. Node credentials are audited by the
    // separate strict node boundary and never enter this metadata/rule scan.
    text.split([',', '=', ' ', '\t']).any(|part| {
        let part = part.trim_matches(['\'', '"']);
        let lower = part.to_ascii_lowercase();
        ["file:", "script:", "exec:", "javascript:"]
            .iter()
            .any(|prefix| lower.contains(prefix))
            || lower.starts_with('\\')
            || (!dns_expression && lower.starts_with('/'))
            || (lower.as_bytes().get(1) == Some(&b':')
                && lower
                    .as_bytes()
                    .get(2)
                    .is_some_and(|c| matches!(c, b'\\' | b'/')))
    })
}

fn text(configuration: &Value) -> Option<&str> {
    let object = configuration.as_object()?;
    (object.len() == 1)
        .then(|| object.get("document")?.as_str())
        .flatten()
}

fn benign_general(key: &str) -> bool {
    matches!(
        key,
        "loglevel"
            | "proxy-test-url"
            | "internet-test-url"
            | "test-timeout"
            | "network_check_url"
            | "server_check_url"
            | "server_check_timeout"
            | "server_check_user_agent"
            | "doh_user_agent"
            | "profile_img_url"
    )
}

pub(super) fn has_semantics(format: &str, configuration: &Value) -> bool {
    if format == "ini"
        && let Some(text) = text(configuration)
    {
        let mut section = String::new();
        for line in text.lines().map(str::trim) {
            if line.is_empty() || line.starts_with(['#', ';']) || line.starts_with("//") {
                continue;
            }
            match ini_section(line) {
                Ok(Some(next)) => {
                    section = next;
                    continue;
                }
                Err(_) => return true,
                _ => {}
            }
            if matches!(section.as_str(), "proxy" | "server_local") {
                continue;
            }
            if section == "general"
                && line
                    .split_once('=')
                    .is_some_and(|(key, _)| benign_general(&key.trim().to_ascii_lowercase()))
            {
                continue;
            }
            return true;
        }
        return false;
    }
    configuration.as_object().is_none_or(|o| {
        if format == "sing-box"
            && o.get("outbounds")
                .and_then(Value::as_array)
                .is_some_and(|outbounds| {
                    outbounds.iter().any(|outbound| {
                        outbound
                            .get("type")
                            .and_then(Value::as_str)
                            .is_some_and(|kind| matches!(kind, "selector" | "urltest" | "dns"))
                    })
                })
        {
            return true;
        }
        o.keys()
            .any(|key| !matches!(key.as_str(), "proxies" | "outbounds" | "log-level"))
    })
}

fn safe_ini(text: &str) -> bool {
    if text.is_empty()
        || text.len() > 4 * 1024 * 1024
        || text
            .chars()
            .any(|c| c.is_control() && !matches!(c, '\t' | '\r' | '\n'))
        || !super::ini::managed_headers_safe(text)
    {
        return false;
    }
    let mut section = String::new();
    let mut sections = std::collections::HashSet::new();
    for line in text.lines().map(str::trim) {
        if line.is_empty() || line.starts_with(['#', ';']) || line.starts_with("//") {
            continue;
        }
        match ini_section(line) {
            Ok(Some(next)) => {
                if !sections.insert(next.clone()) || sections.len() > 256 {
                    return false;
                }
                section = next;
                continue;
            }
            Err(_) => return false,
            _ => {}
        }
        if matches!(section.as_str(), "proxy" | "server_local") {
            continue;
        }
        let directive_value = line.split_once('=').map_or(line, |(_, value)| value);
        if host_reference(directive_value, section == "dns") {
            return false;
        }
        match section.as_str() {
            "general" => {
                let Some((key, value)) = line.split_once('=') else {
                    return false;
                };
                let key = key.trim().to_ascii_lowercase();
                if benign_general(&key) {
                    if !super::ini::client_setting_safe(&key, value.trim()) {
                        return false;
                    }
                    continue;
                }
                if matches!(key.as_str(), "allow-wifi-access" | "allow-lan") {
                    if !value.trim().eq_ignore_ascii_case("false") {
                        return false;
                    }
                    continue;
                }
                if key == "ipv6-vif" {
                    if !matches!(
                        value.trim().to_ascii_lowercase().as_str(),
                        "off" | "disabled"
                    ) {
                        return false;
                    }
                    continue;
                }
                if !matches!(
                    key.as_str(),
                    "dns-server"
                        | "ipv6"
                        | "doh-server"
                        | "encrypted-dns-server"
                        | "ip-mode"
                        | "dns_exclusion_list"
                        | "dns_reject_domain_behavior"
                ) {
                    return false;
                }
            }
            "rule" | "filter_local" => {
                let Ok(parts) = csv(line) else {
                    return false;
                };
                let Some((kind, _)) = parts.first() else {
                    return false;
                };
                if !matches!(
                    kind.to_ascii_lowercase().as_str(),
                    "domain"
                        | "domain-suffix"
                        | "domain-keyword"
                        | "ip-cidr"
                        | "ip-cidr6"
                        | "src-ip-cidr"
                        | "dst-port"
                        | "final"
                        | "match"
                        | "host"
                        | "host-suffix"
                        | "host-keyword"
                        | "host-wildcard"
                        | "ip6-cidr"
                        | "geoip"
                        | "ip-asn"
                        | "process-name"
                        | "domain-set"
                        | "rule-set"
                        | "user-agent"
                        | "url-regex"
                ) {
                    return false;
                }
            }
            "proxy group" | "policy" => {
                let Some((key, body)) = line.split_once('=') else {
                    return false;
                };
                let Ok(parts) = csv(body) else {
                    return false;
                };
                let kind = if section == "policy" {
                    key.trim()
                } else {
                    let Some((first, _)) = parts.first() else {
                        return false;
                    };
                    first
                };
                if !matches!(
                    kind.to_ascii_lowercase().as_str(),
                    "select"
                        | "url-test"
                        | "fallback"
                        | "load-balance"
                        | "static"
                        | "available"
                        | "round-robin"
                        | "dest-hash"
                        | "url-latency-benchmark"
                        | "ssid"
                ) {
                    return false;
                }
                for (part, _) in parts {
                    if let Some((key, _)) = part.split_once('=')
                        && !matches!(
                            key.trim().to_ascii_lowercase().as_str(),
                            "url"
                                | "interval"
                                | "tolerance"
                                | "timeout"
                                | "lazy"
                                | "expected-status"
                                | "policy-regex-filter"
                                | "include-all-proxies"
                                | "include-other-group"
                                | "icon-url"
                                | "img-url"
                                | "persistent"
                                | "evaluate-before-use"
                                | "no-alert"
                                | "check-interval"
                                | "alive-checking"
                                | "server-tag-regex"
                                | "resource-tag-regex"
                        )
                    {
                        return false;
                    }
                }
            }
            "host" => {
                if !line.contains('=') {
                    return false;
                }
            }
            "dns" => {
                let key = line.split_once('=').map_or(line, |(key, _)| key.trim());
                if !matches!(
                    key,
                    "no-system"
                        | "no-ipv6"
                        | "server"
                        | "doh-server"
                        | "doq-server"
                        | "doh3-server"
                        | "address"
                        | "alias"
                        | "prefer-doh3"
                        | "circumvent-ipv4-answer"
                        | "circumvent-ipv6-answer"
                ) {
                    return false;
                }
            }
            _ => return false,
        }
    }
    true
}

fn no_host_capabilities(value: &Value, depth: usize, budget: &mut usize) -> bool {
    if depth > 32 || *budget == 0 {
        return false;
    }
    *budget -= 1;
    match value {
        Value::Array(array) => array
            .iter()
            .all(|v| no_host_capabilities(v, depth + 1, budget)),
        Value::Object(object) => object.iter().all(|(key, value)| {
            let key = key.to_ascii_lowercase();
            if key == "type"
                && value.as_str().is_some_and(|kind| {
                    matches!(
                        kind.to_ascii_lowercase().as_str(),
                        "script" | "exec" | "command"
                    )
                })
            {
                return false;
            }
            matches!(
                key.as_str(),
                "enable"
                    | "nameserver"
                    | "ipv6"
                    | "use-hosts"
                    | "respect-rules"
                    | "enhanced-mode"
                    | "default-nameserver"
                    | "fallback"
                    | "fallback-filter"
                    | "nameserver-policy"
                    | "fake-ip-range"
                    | "fake-ip-filter"
                    | "geoip"
                    | "geoip-code"
                    | "ipcidr"
                    | "domain"
                    | "name"
                    | "type"
                    | "proxies"
                    | "default-selected"
                    | "url"
                    | "interval"
                    | "timeout"
                    | "expected-status"
                    | "tolerance"
                    | "strategy"
                    | "filter"
                    | "lazy"
                    | "include-all"
                    | "rules"
                    | "final"
                    | "rule_set"
                    | "action"
                    | "outbound"
                    | "domain_suffix"
                    | "domain_keyword"
                    | "source_ip_cidr"
                    | "port"
                    | "servers"
                    | "server"
                    | "server_port"
                    | "address"
                    | "tag"
                    | "detour"
                    | "default"
                    | "tls"
                    | "enabled"
                    | "server_name"
                    | "rule-set"
                    | "network"
                    | "protocol"
                    | "dns_mode"
                    | "dns-fallback"
            ) && no_host_capabilities(value, depth + 1, budget)
        }),
        Value::String(text) => {
            !host_reference(text, false)
                && !text
                    .split(',')
                    .next()
                    .is_some_and(|kind| kind.trim().eq_ignore_ascii_case("SCRIPT"))
        }
        _ => true,
    }
}

fn safe_singbox_outbounds(value: &Value) -> bool {
    let Some(outbounds) = value.as_array().filter(|array| array.len() <= 2000) else {
        return false;
    };
    outbounds.iter().all(|outbound| {
        let Some(object) = outbound.as_object() else {
            return false;
        };
        let Some(kind) = object.get("type").and_then(Value::as_str) else {
            return false;
        };
        if matches!(kind, "selector" | "urltest") {
            // These entries are policy configuration, not prevalidated nodes.
            // Their entire shape must be audited before reduced-scope import.
            let allowed: &[&str] = if kind == "selector" {
                &[
                    "type",
                    "tag",
                    "outbounds",
                    "default",
                    "interrupt_exist_connections",
                ]
            } else {
                &[
                    "type",
                    "tag",
                    "outbounds",
                    "url",
                    "interval",
                    "tolerance",
                    "idle_timeout",
                    "interrupt_exist_connections",
                ]
            };
            return object.iter().all(|(key, value)| {
                allowed.contains(&key.as_str()) && no_host_capabilities(value, 0, &mut 100000)
            });
        }
        if !matches!(
            kind,
            "shadowsocks"
                | "trojan"
                | "vmess"
                | "vless"
                | "socks"
                | "http"
                | "hysteria2"
                | "tuic"
                | "direct"
                | "block"
                | "dns"
        ) {
            return false;
        }
        safe_endpoint_object(outbound, 0, &mut 100000)
    })
}

fn safe_endpoint_object(value: &Value, depth: usize, budget: &mut usize) -> bool {
    if depth > 32 || *budget == 0 {
        return false;
    }
    *budget -= 1;
    match value {
        Value::Array(array) => array
            .iter()
            .all(|value| safe_endpoint_object(value, depth + 1, budget)),
        Value::Object(object) => object.iter().all(|(key, value)| {
            if matches!(key.as_str(), "password" | "username" | "uuid") {
                return value.is_string();
            }
            // `path` is a transport URI, never a local file name. Other file or
            // executable options have no entry in this closed source schema.
            if key == "path" {
                return value.is_string();
            }
            if key == "headers" {
                return value.as_object().is_some();
            }
            matches!(
                key.as_str(),
                "type"
                    | "tag"
                    | "server"
                    | "server_port"
                    | "tls"
                    | "transport"
                    | "method"
                    | "alter_id"
                    | "security"
                    | "flow"
                    | "detour"
                    | "up_mbps"
                    | "down_mbps"
                    | "enabled"
                    | "server_name"
                    | "alpn"
                    | "insecure"
                    | "utls"
                    | "fingerprint"
                    | "reality"
                    | "public_key"
                    | "short_id"
                    | "host"
                    | "service_name"
                    | "max_early_data"
                    | "early_data_header_name"
            ) && safe_endpoint_object(value, depth + 1, budget)
        }),
        Value::String(text) => !host_reference(text, false),
        _ => true,
    }
}

pub(super) fn node_only_allowed(format: &str, configuration: &Value) -> bool {
    if format == "ini" && configuration.get("document").is_some() {
        return text(configuration).is_some_and(safe_ini);
    }
    let Some(object) = configuration.as_object() else {
        return false;
    };
    let allowed: &[&str] = match format {
        "clash" | "ini" => &[
            "rules",
            "proxy-groups",
            "dns",
            "hosts",
            "mode",
            "log-level",
            "allow-lan",
        ],
        "sing-box" => &["outbounds", "route", "dns"],
        _ => return false,
    };
    if object.keys().any(|key| !allowed.contains(&key.as_str()))
        || object
            .get("allow-lan")
            .is_some_and(|v| v != &Value::Bool(false))
    {
        return false;
    }
    object.iter().all(|(key, value)| {
        if format == "sing-box" && key == "outbounds" {
            safe_singbox_outbounds(value)
        } else {
            no_host_capabilities(value, 0, &mut 100000)
        }
    })
}

#[cfg(test)]
#[path = "profile_scope_tests.rs"]
mod tests;
