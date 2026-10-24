//! Lossless, deliberately closed sing-box profile subset. Unknown semantics
//! fail as a whole before any node or network setting can be committed.
use super::{ProfileError, error};
use serde_json::{Map, Value, json};
use std::collections::{BTreeMap, HashSet};

fn object<'a>(value: &'a Value, field: &str) -> Result<&'a Map<String, Value>, ProfileError> {
    value
        .as_object()
        .ok_or_else(|| error("ProfileFieldType", field))
}

pub(super) fn project(source: &Value) -> Result<Value, ProfileError> {
    let source = object(source, "configuration")?;
    for key in source.keys() {
        if !["outbounds", "route", "dns"].contains(&key.as_str()) {
            return Err(error("ProfileGlobalFieldUnsupported", key));
        }
    }
    let outbounds = source
        .get("outbounds")
        .and_then(Value::as_array)
        .ok_or_else(|| error("ProfileFieldType", "outbounds"))?;
    let mut tags = HashSet::new();
    let mut aliases = BTreeMap::new();
    for raw in outbounds {
        let outbound = object(raw, "outbounds")?;
        let tag = outbound
            .get("tag")
            .and_then(Value::as_str)
            .filter(|tag| !tag.is_empty() && !tag.contains(','))
            .ok_or_else(|| error("ProfileOutboundTagRequired", "outbounds.tag"))?;
        if !tags.insert(tag.to_owned()) {
            return Err(error("ProfileOutboundTagDuplicate", "outbounds.tag"));
        }
        match outbound.get("type").and_then(Value::as_str) {
            Some("direct" | "block") => {
                if outbound
                    .keys()
                    .any(|key| !["type", "tag"].contains(&key.as_str()))
                {
                    return Err(error("ProfileBuiltinOptionsUnsupported", "outbounds"));
                }
                aliases.insert(
                    tag.to_owned(),
                    if outbound["type"] == "direct" {
                        "DIRECT"
                    } else {
                        "REJECT"
                    }
                    .to_owned(),
                );
            }
            Some("dns") => return Err(error("ProfileDnsOutboundUnsupported", "outbounds.type")),
            Some(_) => {
                aliases.insert(tag.to_owned(), tag.to_owned());
            }
            None => return Err(error("ProfileFieldType", "outbounds.type")),
        }
    }
    let resolve = |value: &Value| -> Result<String, ProfileError> {
        value
            .as_str()
            .and_then(|tag| aliases.get(tag))
            .cloned()
            .ok_or_else(|| error("ProfileOutboundReference", "route"))
    };
    let mut groups = Vec::new();
    for raw in outbounds {
        let outbound = object(raw, "outbounds")?;
        if outbound["type"] != "selector" {
            if outbound["type"] == "urltest" {
                return Err(error("ProfileGroupUnsupported", "outbounds.type"));
            }
            continue;
        }
        for key in outbound.keys() {
            if !["type", "tag", "outbounds", "default"].contains(&key.as_str()) {
                return Err(error(
                    "ProfileGroupFieldUnsupported",
                    &format!("outbounds.{key}"),
                ));
            }
        }
        let members = outbound
            .get("outbounds")
            .and_then(Value::as_array)
            .filter(|members| !members.is_empty())
            .ok_or_else(|| error("ProfileGroupType", "outbounds.outbounds"))?;
        let members = members
            .iter()
            .map(&resolve)
            .collect::<Result<Vec<_>, _>>()?;
        let mut group = json!({"name":outbound["tag"],"type":"select","proxies":members});
        if let Some(selected) = outbound.get("default") {
            group["default-selected"] = resolve(selected)?.into();
        }
        groups.push(group);
    }
    let route = source
        .get("route")
        .ok_or_else(|| error("ProfileRulesRequired", "route"))?;
    let route = object(route, "route")?;
    for key in route.keys() {
        if !["rules", "final"].contains(&key.as_str()) {
            return Err(error(
                "ProfileRouteFieldUnsupported",
                &format!("route.{key}"),
            ));
        }
    }
    let mut rules = Vec::new();
    if let Some(entries) = route.get("rules") {
        let entries = entries
            .as_array()
            .ok_or_else(|| error("ProfileFieldType", "route.rules"))?;
        for entry in entries {
            let rule = object(entry, "route.rules")?;
            if rule
                .get("type")
                .is_some_and(|kind| kind.as_str() != Some("default"))
                || rule
                    .get("action")
                    .is_some_and(|action| action.as_str() != Some("route"))
            {
                return Err(error("ProfileRuleUnsupported", "route.rules.action"));
            }
            let target = resolve(rule.get("outbound").unwrap_or(&Value::Null))?;
            let mut predicate = None;
            for key in rule
                .keys()
                .filter(|key| !["type", "action", "outbound"].contains(&key.as_str()))
            {
                if ![
                    "domain",
                    "domain_suffix",
                    "domain_keyword",
                    "source_ip_cidr",
                    "port",
                ]
                .contains(&key.as_str())
                    || predicate.is_some()
                {
                    return Err(error(
                        "ProfileRuleCompoundOrUnsupported",
                        &format!("route.rules.{key}"),
                    ));
                }
                predicate = Some(key.as_str());
            }
            let key =
                predicate.ok_or_else(|| error("ProfileRulePredicateRequired", "route.rules"))?;
            let values = rule[key]
                .as_array()
                .filter(|values| !values.is_empty())
                .ok_or_else(|| error("ProfileFieldType", "route.rules"))?;
            for value in values {
                let text = if key == "port" {
                    value
                        .as_u64()
                        .filter(|port| *port > 0 && *port <= 65535)
                        .map(|port| port.to_string())
                } else {
                    value
                        .as_str()
                        .filter(|value| !value.contains(',') && !value.starts_with('.'))
                        .map(str::to_owned)
                }
                .ok_or_else(|| error("ProfileRuleValueUnsupported", "route.rules"))?;
                let kind = match key {
                    "domain" => "DOMAIN",
                    "domain_suffix" => "DOMAIN-SUFFIX",
                    "domain_keyword" => "DOMAIN-KEYWORD",
                    "source_ip_cidr" => "SRC-IP-CIDR",
                    _ => "DST-PORT",
                };
                rules.push(Value::String(format!("{kind},{text},{target}")));
            }
        }
    }
    let final_target = resolve(route.get("final").unwrap_or(&Value::Null))?;
    rules.push(Value::String(format!("MATCH,{final_target}")));
    let mut normalized = json!({"rules":rules,"proxy-groups":groups});
    if let Some(dns) = source.get("dns") {
        let dns = object(dns, "dns")?;
        for key in dns.keys() {
            if !["servers", "final", "strategy"].contains(&key.as_str()) {
                return Err(error("ProfileDnsFieldUnsupported", &format!("dns.{key}")));
            }
        }
        let servers = dns
            .get("servers")
            .and_then(Value::as_array)
            .filter(|servers| servers.len() == 1)
            .ok_or_else(|| error("ProfileDnsSingleServerRequired", "dns.servers"))?;
        let server = object(&servers[0], "dns.servers")?;
        let kind = server.get("type").and_then(Value::as_str);
        let allowed: &[&str] = match kind {
            None => &["tag", "address"],
            Some("local") => &["type", "tag"],
            Some("udp") => &["type", "tag", "server", "server_port"],
            _ => return Err(error("ProfileDnsServerUnsupported", "dns.servers.type")),
        };
        for key in server.keys() {
            if !allowed.contains(&key.as_str()) {
                return Err(error(
                    "ProfileDnsFieldUnsupported",
                    &format!("dns.servers.{key}"),
                ));
            }
        }
        if let Some(final_tag) = dns.get("final")
            && (final_tag.as_str().is_none() || server.get("tag") != Some(final_tag))
        {
            return Err(error("ProfileDnsServerReference", "dns.final"));
        }
        let mut mapped = Map::new();
        // This is a sing-box resolver, not a disabled-by-default Clash DNS
        // section. Carry the dialect's dual-stack default explicitly.
        mapped.insert("enable".into(), true.into());
        mapped.insert("ipv6".into(), true.into());
        let address = if kind == Some("local") {
            "local"
        } else {
            server
                .get(if kind.is_some() { "server" } else { "address" })
                .and_then(Value::as_str)
                .ok_or_else(|| error("ProfileFieldType", "dns.servers"))?
        };
        if kind == Some("udp") && address.parse::<std::net::IpAddr>().is_err() {
            return Err(error("ProfileDnsServerAddress", "dns.servers.server"));
        }
        if server
            .get("server_port")
            .is_some_and(|port| port.as_u64() != Some(53))
        {
            return Err(error(
                "ProfileDnsServerPortUnsupported",
                "dns.servers.server_port",
            ));
        }
        if address != "local" {
            mapped.insert("nameserver".into(), json!([address]));
        }
        if let Some(strategy) = dns.get("strategy") {
            if strategy.as_str() != Some("ipv4_only") {
                return Err(error("ProfileDnsStrategyUnsupported", "dns.strategy"));
            }
            mapped.insert("ipv6".into(), false.into());
        }
        normalized["dns"] = Value::Object(mapped);
    }
    super::project(&normalized)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn profile() -> Value {
        json!({"outbounds":[{"tag":"node","type":"socks","server":"192.0.2.1","server_port":1080},{"tag":"bypass","type":"direct"},{"tag":"choice","type":"selector","outbounds":["node","bypass"],"default":"node"}],"route":{"rules":[{"domain":["example.org","example.net"],"outbound":"bypass"}],"final":"choice"},"dns":{"servers":[{"tag":"resolver","type":"udp","server":"192.0.2.53"}],"final":"resolver","strategy":"ipv4_only"}})
    }
    #[test]
    fn selectors_route_arrays_final_and_explicit_dns_survive_projection() {
        let mapped = project(&profile()).unwrap();
        assert_eq!(
            mapped["groups"],
            json!([{"name":"choice","type":"select","proxies":["node","DIRECT"],"default-selected":"node"}])
        );
        assert_eq!(
            mapped["rules"],
            json!([
                "DOMAIN,example.org,DIRECT",
                "DOMAIN,example.net,DIRECT",
                "MATCH,choice"
            ])
        );
        assert_eq!(mapped["dns"]["servers"], "192.0.2.53");
        assert_eq!(mapped["dns"]["queryFamily"], "ipv4_only");
    }
    #[test]
    fn compound_rules_remote_rules_and_dns_fallback_cannot_silently_change_meaning() {
        let mut input = profile();
        input["route"]["rules"][0]["port"] = json!([443]);
        assert_eq!(
            project(&input).unwrap_err().code,
            "ProfileRuleCompoundOrUnsupported"
        );
        input = profile();
        input["route"]["rule_set"] = json!([]);
        assert_eq!(project(&input).unwrap_err().field, "route.rule_set");
        input = profile();
        input["dns"]["rules"] = json!([]);
        assert_eq!(project(&input).unwrap_err().field, "dns.rules");
        input = profile();
        input["route"]["final"] = json!("missing");
        assert_eq!(
            project(&input).unwrap_err().code,
            "ProfileOutboundReference"
        );
    }
}
