//! Ordered routing over immutable, validated IR. No implicit DIRECT fallback.
use std::net::{IpAddr, SocketAddr};
use swirl_subscription::{Config, Matcher, Node};

pub enum Decision<'a> {
    Node(&'a Node),
    Resolve,
}

/// Ask for DNS only when an unresolved destination reaches a resolving CIDR.
/// The caller retries with bounded resolver results. Earlier rules still win.
pub fn select<'a>(
    config: &'a Config,
    host: &str,
    port: u16,
    source: IpAddr,
    resolved: Option<&[SocketAddr]>,
) -> Result<Decision<'a>, &'static str> {
    let host = host.to_ascii_lowercase();
    let ip = host.parse::<std::net::IpAddr>().ok();
    // Do not expose results to earlier no-resolve rules on the second pass:
    // those rules were already skipped before resolution was requested.
    let mut dns_reached = false;
    let mut id = config.selected.as_str();
    for rule in &config.rules {
        let matched = match &rule.matcher {
            Matcher::Domain { value } => host.eq_ignore_ascii_case(value),
            Matcher::DomainSuffix { value } => {
                let suffix = value.to_ascii_lowercase();
                host == suffix
                    || host
                        .strip_suffix(&suffix)
                        .is_some_and(|prefix| prefix.ends_with('.'))
            }
            Matcher::DomainKeyword { value } => host.contains(&value.to_ascii_lowercase()),
            Matcher::Cidr { value, resolve } => {
                if let Some(ip) = ip {
                    value.contains(&ip)
                } else {
                    if *resolve {
                        dns_reached = true;
                        if resolved.is_none() {
                            return Ok(Decision::Resolve);
                        }
                    }
                    dns_reached
                        && resolved
                            .and_then(|a| a.first())
                            .is_some_and(|a| value.contains(&a.ip()))
                }
            }
            Matcher::SourceCidr { value } => value.contains(&source),
            Matcher::DestinationPort { value } => port == *value,
            Matcher::Match {} => true,
        };
        if matched {
            id = &rule.outbound;
            break;
        }
    }
    if let Some(selector) = config.selectors.iter().find(|s| s.id == id) {
        id = &selector.selected;
    }
    config
        .nodes
        .iter()
        .find(|n| n.id == id)
        .map(Decision::Node)
        .ok_or("RouteNotFound")
}

#[cfg(test)]
mod tests {
    use super::*;
    fn config(rules: &str) -> Config {
        Config::parse(format!(r#"{{"schema":1,"listen":"127.0.0.1:0","selected":"deny","nodes":[{{"id":"allow","outbound":{{"type":"direct"}}}},{{"id":"deny","outbound":{{"type":"reject"}}}}],"rules":{rules}}}"#).as_bytes()).unwrap()
    }
    fn route<'a>(c: &'a Config, host: &str, port: u16, resolved: Option<&[SocketAddr]>) -> &'a str {
        match select(c, host, port, "127.0.0.1".parse().unwrap(), resolved).unwrap() {
            Decision::Node(n) => &n.id,
            Decision::Resolve => "resolve",
        }
    }
    #[test]
    fn suffix_is_label_bounded_and_first_match_wins() {
        let c = Config::parse(br#"{"schema":1,"listen":"127.0.0.1:0","selected":"deny","nodes":[{"id":"allow","outbound":{"type":"direct"}},{"id":"deny","outbound":{"type":"reject"}}],"rules":[{"matcher":{"type":"domain_suffix","value":"example.org"},"outbound":"allow"},{"matcher":{"type":"domain","value":"example.org"},"outbound":"deny"}]}"#).unwrap();
        assert_eq!(route(&c, "A.Example.org", 80, None), "allow");
        assert_eq!(route(&c, "example.org", 80, None), "allow");
        assert_eq!(route(&c, "notexample.org", 80, None), "deny");
    }
    #[test]
    fn dns_is_lazy_and_no_resolve_does_not_reorder_rules() {
        let c = config(
            r#"[{"matcher":{"type":"domain","value":"local.test"},"outbound":"deny"},{"matcher":{"type":"cidr","value":"127.0.0.0/8"},"outbound":"deny"},{"matcher":{"type":"cidr","value":"::1/128","resolve":true},"outbound":"allow"},{"matcher":{"type":"cidr","value":"127.0.0.0/8"},"outbound":"allow"}]"#,
        );
        let addresses = ["127.0.0.1:80".parse().unwrap()];
        assert_eq!(route(&c, "local.test", 80, None), "deny");
        assert_eq!(route(&c, "localhost", 80, None), "resolve");
        assert_eq!(route(&c, "localhost", 80, Some(&addresses)), "allow");
        assert_eq!(route(&c, "127.0.0.1", 80, None), "deny");
        assert_eq!(route(&c, "::1", 80, None), "allow");
        assert_eq!(route(&c, "localhost", 80, Some(&[])), "deny");
        let mixed = [
            "192.0.2.1:80".parse().unwrap(),
            "127.0.0.1:80".parse().unwrap(),
        ];
        assert_eq!(route(&c, "localhost", 80, Some(&mixed)), "deny");
    }
    #[test]
    fn keyword_port_source_and_final_are_ordered() {
        let c = config(
            r#"[{"matcher":{"type":"domain_keyword","value":"BLOCK"},"outbound":"deny"},{"matcher":{"type":"destination_port","value":443},"outbound":"allow"},{"matcher":{"type":"source_cidr","value":"127.0.0.0/8"},"outbound":"allow"},{"matcher":{"type":"match"},"outbound":"deny"},{"matcher":{"type":"match"},"outbound":"allow"}]"#,
        );
        assert_eq!(route(&c, "blocked.test", 443, None), "deny");
        assert_eq!(route(&c, "ordinary.test", 443, None), "allow");
        assert_eq!(route(&c, "ordinary.test", 80, None), "allow");
        let Decision::Node(n) =
            select(&c, "ordinary.test", 80, "192.0.2.1".parse().unwrap(), None).unwrap()
        else {
            panic!()
        };
        assert_eq!(n.id, "deny");
    }
}
