//! Ordered routing over immutable, validated IR. No implicit DIRECT fallback.
use swirl_subscription::{Config, Matcher, Node};

pub fn select<'a>(config: &'a Config, host: &str) -> Result<&'a Node, &'static str> {
    let host = host.to_ascii_lowercase();
    let ip = host.parse::<std::net::IpAddr>().ok();
    let id = config
        .rules
        .iter()
        .find(|r| match &r.matcher {
            Matcher::Domain { value } => host.eq_ignore_ascii_case(value),
            Matcher::DomainSuffix { value } => {
                let suffix = value.to_ascii_lowercase();
                host == suffix
                    || host
                        .strip_suffix(&suffix)
                        .is_some_and(|prefix| prefix.ends_with('.'))
            }
            Matcher::Cidr { value } => ip.is_some_and(|ip| value.contains(&ip)),
        })
        .map_or(config.selected.as_str(), |r| r.outbound.as_str());
    config
        .nodes
        .iter()
        .find(|n| n.id == id)
        .ok_or("RouteNotFound")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn suffix_is_label_bounded_and_first_match_wins() {
        let c = Config::parse(br#"{"schema":1,"listen":"127.0.0.1:0","selected":"deny","nodes":[{"id":"allow","outbound":{"type":"direct"}},{"id":"deny","outbound":{"type":"reject"}}],"rules":[{"matcher":{"type":"domain_suffix","value":"example.org"},"outbound":"allow"},{"matcher":{"type":"domain","value":"example.org"},"outbound":"deny"}]}"#).unwrap();
        assert_eq!(select(&c, "A.Example.org").unwrap().id, "allow");
        assert_eq!(select(&c, "example.org").unwrap().id, "allow");
        assert_eq!(select(&c, "notexample.org").unwrap().id, "deny");
    }
}
