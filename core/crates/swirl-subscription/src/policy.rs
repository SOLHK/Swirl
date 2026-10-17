//! Swirl-owned policy semantics. Automatic groups require an explicit probe;
//! no implied traffic, external-core delegation, or application request replay.
use crate::{Config, Outbound, Tls, valid_host};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PolicyStrategy {
    #[default]
    Manual,
    UrlTest,
    Fallback,
    LoadBalance,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HealthProbe {
    pub url: String,
    #[serde(default = "default_interval")]
    pub interval_ms: u64,
    #[serde(default = "default_timeout")]
    pub timeout_ms: u64,
    #[serde(default = "default_status")]
    pub expected_status: u16,
    #[serde(default)]
    pub tolerance_ms: u64,
    #[serde(default)]
    pub tls: Option<Tls>,
}
fn default_interval() -> u64 {
    300000
}
fn default_timeout() -> u64 {
    5000
}
fn default_status() -> u16 {
    204
}
pub struct ProbeTarget {
    pub host: String,
    pub port: u16,
    pub authority: String,
    pub path: String,
    pub tls: Option<Tls>,
}
impl HealthProbe {
    pub fn target(&self) -> Result<ProbeTarget, &'static str> {
        if self.url.len() > 2048
            || !(1000..=3600000).contains(&self.interval_ms)
            || !(100..=30000).contains(&self.timeout_ms)
            || self.timeout_ms > self.interval_ms
            || !(200..=299).contains(&self.expected_status)
            || self.tolerance_ms > 10000
            || !self
                .url
                .bytes()
                .all(|b| (33..=126).contains(&b) && b != b'\\')
        {
            return Err("PolicyProbeParameters");
        }
        let url = url::Url::parse(&self.url).map_err(|_| "PolicyProbeUrl")?;
        if !matches!(url.scheme(), "http" | "https")
            || !url.username().is_empty()
            || url.password().is_some()
            || url.fragment().is_some()
        {
            return Err("PolicyProbeUrl");
        }
        let host = url.host_str().ok_or("PolicyProbeHost")?;
        let host = host
            .strip_prefix('[')
            .and_then(|s| s.strip_suffix(']'))
            .unwrap_or(host)
            .to_owned();
        if !valid_host(&host) {
            return Err("PolicyProbeHost");
        }
        let port = url
            .port_or_known_default()
            .filter(|p| *p != 0)
            .ok_or("PolicyProbePort")?;
        let authority = if host.contains(':') {
            format!("[{host}]:{port}")
        } else {
            format!("{host}:{port}")
        };
        let mut path = if url.path().is_empty() {
            "/".into()
        } else {
            url.path().to_owned()
        };
        if let Some(query) = url.query() {
            path.push('?');
            path.push_str(query);
        }
        let tls = if url.scheme() == "https" {
            let tls = self.tls.clone().unwrap_or(Tls {
                server_name: host.clone(),
                alpn: vec!["http/1.1".into()],
                ca_der_base64: None,
            });
            if !tls.server_name.eq_ignore_ascii_case(&host)
                || !(tls.alpn.is_empty() || tls.alpn == ["http/1.1"])
                || tls
                    .ca_der_base64
                    .as_ref()
                    .is_some_and(|ca| ca.len() > 65536)
            {
                return Err("PolicyProbeTls");
            }
            Some(tls)
        } else {
            if self.tls.is_some() {
                return Err("PolicyProbeTls");
            }
            None
        };
        Ok(ProbeTarget {
            host,
            port,
            authority,
            path,
            tls,
        })
    }
}
impl Config {
    /// Validate the entire membership graph, not only the currently selected
    /// path: a later manual switch cannot introduce an unvalidated cycle.
    pub fn validate_policies(&self) -> Result<(), &'static str> {
        let groups: HashMap<_, _> = self
            .selectors
            .iter()
            .enumerate()
            .map(|(i, s)| (s.id.as_str(), i))
            .collect();
        let nodes: HashMap<_, _> = self.nodes.iter().map(|n| (n.id.as_str(), n)).collect();
        let mut automatic = 0;
        let mut probes = 0;
        for group in &self.selectors {
            if group.strategy == PolicyStrategy::Manual {
                if group.probe.is_some() {
                    return Err("ManualPolicyProbeUnsupported");
                }
            } else {
                if !group.selected.is_empty() {
                    return Err("AutomaticPolicySelection");
                }
                automatic += 1;
                probes += group.members.len();
                if automatic > 32 || probes > 512 || group.members.len() > 64 {
                    return Err("PolicyProbeBudget");
                }
                let probe = group.probe.as_ref().ok_or("PolicyProbeRequired")?;
                probe.target()?;
                if group.strategy != PolicyStrategy::UrlTest && probe.tolerance_ms != 0 {
                    return Err("PolicyToleranceUnsupported");
                }
                for member in &group.members {
                    let node = nodes
                        .get(member.as_str())
                        .ok_or("AutomaticPolicyRequiresConcreteNodes")?;
                    if matches!(node.outbound, Outbound::Reject {}) {
                        return Err("PolicyProbeRejectMember");
                    }
                }
            }
        }
        fn depth(
            index: usize,
            config: &Config,
            groups: &HashMap<&str, usize>,
            visiting: &mut [bool],
            cache: &mut [usize],
        ) -> Result<usize, &'static str> {
            if visiting[index] {
                return Err("PolicyCycle");
            }
            if cache[index] != 0 {
                return Ok(cache[index]);
            }
            visiting[index] = true;
            let mut longest = 1;
            for member in &config.selectors[index].members {
                if let Some(next) = groups.get(member.as_str()) {
                    longest = longest.max(1 + depth(*next, config, groups, visiting, cache)?);
                    if longest > 16 {
                        return Err("PolicyDepth");
                    }
                }
            }
            visiting[index] = false;
            cache[index] = longest;
            Ok(longest)
        }
        let mut visiting = vec![false; self.selectors.len()];
        let mut cache = vec![0; self.selectors.len()];
        for index in 0..self.selectors.len() {
            depth(index, self, &groups, &mut visiting, &mut cache)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn automatic_policy_requires_explicit_bounded_safe_probe() {
        let base = json!({"schema":1,"listen":"127.0.0.1:0","selected":"g","nodes":[{"id":"a","outbound":{"type":"direct"}}],
            "selectors":[{"id":"g","members":["a"],"strategy":"fallback","probe":{"url":"http://127.0.0.1:9000/health","interval_ms":1000,"timeout_ms":500}}]});
        assert!(Config::parse(base.to_string().as_bytes()).is_ok());
        for probe in [
            json!(null),
            json!({"url":"file:///etc/hosts"}),
            json!({"url":"http://user:password@host/"}),
            json!({"url":"http://host/","interval_ms":1}),
            json!({"url":"http://host/","expected_status":302}),
            json!({"url":"https://host/","tls":{"server_name":"wrong"}}),
        ] {
            let mut bad = base.clone();
            bad["selectors"][0]["probe"] = probe;
            assert!(Config::parse(bad.to_string().as_bytes()).is_err());
        }
        let mut bad = base;
        bad["selectors"][0]["strategy"] = json!("manual");
        assert!(Config::parse(bad.to_string().as_bytes()).is_err());
    }
    #[test]
    fn nested_manual_groups_are_acyclic_and_reference_real_members() {
        let mut base = json!({"schema":1,"listen":"127.0.0.1:0","selected":"outer","nodes":[{"id":"a","outbound":{"type":"direct"}}],
            "selectors":[{"id":"outer","members":["inner"],"selected":"inner"},{"id":"inner","members":["a"],"selected":"a"}]});
        assert!(Config::parse(base.to_string().as_bytes()).is_ok());
        base["selectors"][1]["members"] = json!(["a", "outer"]);
        assert!(Config::parse(base.to_string().as_bytes()).is_err());
    }

    #[test]
    fn automatic_groups_reject_implicit_defaults_nested_members_and_ignored_options() {
        let base = serde_json::json!({"schema":1,"listen":"127.0.0.1:0","selected":"auto","nodes":[{"id":"a","outbound":{"type":"direct"}},{"id":"deny","outbound":{"type":"reject"}}],
            "selectors":[{"id":"auto","members":["a"],"strategy":"fallback","probe":{"url":"http://127.0.0.1/","interval_ms":1000,"timeout_ms":100}},
                {"id":"manual","members":["a"],"selected":"a"}]});
        assert!(Config::parse(base.to_string().as_bytes()).is_ok());
        for member in ["manual", "deny", "missing"] {
            let mut bad = base.clone();
            bad["selectors"][0]["members"] = serde_json::json!([member]);
            assert!(Config::parse(bad.to_string().as_bytes()).is_err());
        }
        let mut bad = base.clone();
        bad["selectors"][0]["selected"] = serde_json::json!("a");
        assert!(matches!(
            Config::parse(bad.to_string().as_bytes()),
            Err("AutomaticPolicySelection")
        ));
        let mut bad = base;
        bad["selectors"][0]["probe"]["tolerance_ms"] = serde_json::json!(1);
        assert!(matches!(
            Config::parse(bad.to_string().as_bytes()),
            Err("PolicyToleranceUnsupported")
        ));
    }

    #[test]
    fn policy_depth_and_total_probe_work_are_bounded() {
        let mut base = serde_json::json!({"schema":1,"listen":"127.0.0.1:0","selected":"g0","nodes":[{"id":"a","outbound":{"type":"direct"}}]});
        for length in [16, 17] {
            base["selectors"] = serde_json::json!((0..length).map(|index| {
                let next = if index + 1 < length {format!("g{}", index + 1)} else {"a".into()};
                serde_json::json!({"id":format!("g{index}"),"members":[next],"selected":next})
            }).collect::<Vec<_>>());
            assert_eq!(
                Config::parse(base.to_string().as_bytes()).is_ok(),
                length == 16
            );
        }
        base["nodes"] = serde_json::json!(
            (0..64)
                .map(|i| serde_json::json!({"id":format!("n{i}"),"outbound":{"type":"direct"}}))
                .collect::<Vec<_>>()
        );
        for groups in [8, 9] {
            base["selectors"] = serde_json::json!((0..groups).map(|index| serde_json::json!({"id":format!("g{index}"),
                "members":(0..64).map(|i|format!("n{i}")).collect::<Vec<_>>(),"strategy":"url_test","probe":{"url":"http://127.0.0.1/"}})).collect::<Vec<_>>());
            assert_eq!(
                Config::parse(base.to_string().as_bytes()).is_ok(),
                groups == 8
            );
        }
    }
}
