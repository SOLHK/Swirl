//! Five explicit routing tiers. This does not modify schema-1 ordered routing.
use crate::ChinaRules;
use serde::Serialize;
use std::net::{IpAddr, Ipv4Addr};
use swirl_subscription::{
    Matcher,
    v2::{ClassificationDns, Mode, PolicyDocument, PolicyRule, Target, canonical_domain},
};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ResolutionPurpose {
    ChinaClassification,
    MandatoryRule,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct RouteDecision {
    pub target: Target,
    pub rule_id: String,
    pub tier: u8,
    pub service_policy_id: Option<String>,
    pub catalog_key: Option<String>,
    pub classification_state: &'static str,
    pub resolution: Option<ResolutionPurpose>,
}
impl RouteDecision {
    fn selected(
        target: Target,
        rule_id: impl Into<String>,
        tier: u8,
        classification_state: &'static str,
    ) -> Self {
        Self {
            target,
            rule_id: rule_id.into(),
            tier,
            service_policy_id: None,
            catalog_key: None,
            classification_state,
            resolution: None,
        }
    }
    fn resolve(rule_id: impl Into<String>, tier: u8, purpose: ResolutionPurpose) -> Self {
        Self {
            resolution: Some(purpose),
            ..Self::selected(Target::Unconfigured {}, rule_id, tier, "pending")
        }
    }
}

pub fn normalize_ip(ip: IpAddr) -> IpAddr {
    match ip {
        IpAddr::V6(ip) => ip.to_ipv4_mapped().map_or(IpAddr::V6(ip), IpAddr::V4),
        ip => ip,
    }
}
pub fn local_ip(ip: IpAddr) -> bool {
    match normalize_ip(ip) {
        IpAddr::V4(ip) => {
            ip.is_loopback()
                || ip.is_private()
                || ip.is_link_local()
                || (u32::from(ip) & 0xffc0_0000 == u32::from(Ipv4Addr::new(100, 64, 0, 0)))
        }
        IpAddr::V6(ip) => {
            ip.is_loopback()
                || (ip.segments()[0] & 0xfe00 == 0xfc00)
                || (ip.segments()[0] & 0xffc0 == 0xfe80)
        }
    }
}
pub fn forbidden_ip(ip: IpAddr) -> bool {
    let ip = normalize_ip(ip);
    ip.is_unspecified() || ip.is_multicast() || ip == IpAddr::V4(Ipv4Addr::BROADCAST)
}

fn matcher(
    rule: &PolicyRule,
    host: &str,
    ip: Option<IpAddr>,
    source: IpAddr,
    port: u16,
) -> Result<bool, ResolutionPurpose> {
    Ok(match &rule.matcher {
        Matcher::Domain { value } => host == value,
        Matcher::DomainSuffix { value } => {
            host == value || host.strip_suffix(value).is_some_and(|p| p.ends_with('.'))
        }
        Matcher::DomainKeyword { value } => host.contains(&value.to_ascii_lowercase()),
        Matcher::Cidr { value, resolve } => match ip {
            Some(ip) => value.contains(&normalize_ip(ip)),
            None if *resolve => return Err(ResolutionPurpose::MandatoryRule),
            None => false,
        },
        Matcher::SourceCidr { value } => value.contains(&normalize_ip(source)),
        Matcher::DestinationPort { value } => port == *value,
        Matcher::Match {} => true,
    })
}

pub fn select(
    policy: &PolicyDocument,
    host: &str,
    port: u16,
    source: IpAddr,
    known_ip: Option<IpAddr>,
    classification_attempted: bool,
    china: Option<(&ChinaRules, &ChinaRules)>,
) -> Result<RouteDecision, &'static str> {
    let literal = host.parse::<IpAddr>().ok().map(normalize_ip);
    let host = if literal.is_some() {
        host.to_ascii_lowercase()
    } else {
        canonical_domain(host)?
    };
    let ip = known_ip
        .map(normalize_ip)
        .or(literal)
        .or_else(|| (host == "localhost").then_some(IpAddr::V4(Ipv4Addr::LOCALHOST)));
    if port == 0 || ip.is_some_and(forbidden_ip) {
        return Err("InvalidTarget");
    }
    if policy.mode == Mode::Direct {
        return Ok(RouteDecision::selected(
            Target::Direct {},
            "mode:direct",
            0,
            "not_required",
        ));
    }
    if ip.is_some_and(local_ip) {
        return Ok(RouteDecision::selected(
            Target::Direct {},
            "builtin:local-v1",
            1,
            "local",
        ));
    }
    if policy.mode == Mode::Global {
        return Ok(RouteDecision::selected(
            policy.default_policy.target.clone(),
            "policy:default",
            5,
            "not_required",
        ));
    }
    let mut explicit: Vec<_> = policy
        .explicit_direct_rules
        .iter()
        .filter(|r| r.enabled)
        .collect();
    explicit.sort_by_key(|r| r.priority);
    for rule in explicit {
        match matcher(rule, &host, ip, source, port) {
            Ok(true) => {
                return Ok(RouteDecision::selected(
                    Target::Direct {},
                    &rule.id,
                    1,
                    "explicit",
                ));
            }
            Err(purpose) => return Ok(RouteDecision::resolve(&rule.id, 1, purpose)),
            _ => {}
        }
    }
    let mut services: Vec<_> = policy
        .service_policies
        .iter()
        .filter(|s| s.enabled)
        .collect();
    services.sort_by_key(|s| s.priority);
    for service in services {
        if service.domains.iter().any(|domain| domain.matches(&host)) {
            return Ok(RouteDecision {
                service_policy_id: Some(service.id.clone()),
                catalog_key: service.catalog_key.clone(),
                ..RouteDecision::selected(service.target.clone(), &service.id, 2, "service")
            });
        }
    }
    let (domains, ips) = china.ok_or("ChinaRuleSetIncomplete")?;
    if domains.matches_domain(&host) {
        return Ok(RouteDecision::selected(
            Target::Direct {},
            "builtin:cn-domain",
            3,
            "china_domain",
        ));
    }
    if ip.is_some_and(|ip| ips.matches_ip(ip)) {
        return Ok(RouteDecision::selected(
            Target::Direct {},
            "builtin:cn-ip",
            3,
            "china_ip",
        ));
    }
    if ip.is_none()
        && !classification_attempted
        && policy.classification_dns != ClassificationDns::Disabled
    {
        return Ok(RouteDecision::resolve(
            "builtin:cn-ip",
            3,
            ResolutionPurpose::ChinaClassification,
        ));
    }
    let classification = if ip.is_some() {
        "non_china_ip"
    } else if classification_attempted {
        "unavailable"
    } else {
        "disabled"
    };
    let mut custom: Vec<_> = policy.custom_rules.iter().filter(|r| r.enabled).collect();
    custom.sort_by_key(|r| r.priority);
    for rule in custom {
        match matcher(rule, &host, ip, source, port) {
            Ok(true) => {
                return Ok(RouteDecision::selected(
                    rule.target.clone(),
                    &rule.id,
                    4,
                    classification,
                ));
            }
            Err(purpose) => return Ok(RouteDecision::resolve(&rule.id, 4, purpose)),
            _ => {}
        }
    }
    Ok(RouteDecision::selected(
        policy.default_policy.target.clone(),
        "policy:default",
        5,
        classification,
    ))
}

#[cfg(test)]
#[path = "v2_tests.rs"]
mod tests;
