//! Strict, stable-identity policy documents. Legacy Config parsing is unchanged.
use crate::{Config, HealthProbe, Matcher, Node, Outbound, PolicyStrategy, uuid_bytes};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const DEFAULT_POLICY_ID: &str = "policy:default";
pub const DIRECT_NODE_ID: &str = "SWIRL_V2_DIRECT";
pub const REJECT_NODE_ID: &str = "SWIRL_V2_REJECT";

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Target {
    Node { id: String },
    Group { id: String },
    Direct {},
    Reject {},
    Unconfigured {},
}
impl Target {
    pub fn id(&self) -> Option<&str> {
        match self {
            Self::Node { id } | Self::Group { id } => Some(id),
            _ => None,
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", try_from = "String")]
pub enum Mode {
    #[default]
    Rule,
    Global,
    Direct,
}
impl TryFrom<String> for Mode {
    type Error = &'static str;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        match value.as_str() {
            "rule" => Ok(Self::Rule),
            "global" => Ok(Self::Global),
            "direct" => Ok(Self::Direct),
            _ => Err("UnsupportedMode"),
        }
    }
}
impl Mode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Rule => "rule",
            Self::Global => "global",
            Self::Direct => "direct",
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", try_from = "String")]
pub enum ClassificationDns {
    #[default]
    Disabled,
    DirectEncrypted,
    ViaDefaultPolicy,
}
impl TryFrom<String> for ClassificationDns {
    type Error = &'static str;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        match value.as_str() {
            "disabled" => Ok(Self::Disabled),
            "direct_encrypted" => Ok(Self::DirectEncrypted),
            "via_default_policy" => Ok(Self::ViaDefaultPolicy),
            _ => Err("ClassificationDnsPath"),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DefaultPolicy {
    pub id: String,
    pub target: Target,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum DomainMatch {
    Domain { value: String },
    DomainSuffix { value: String },
}
impl DomainMatch {
    pub fn value(&self) -> &str {
        match self {
            Self::Domain { value } | Self::DomainSuffix { value } => value,
        }
    }
    pub fn matches(&self, host: &str) -> bool {
        host == self.value()
            || matches!(self, Self::DomainSuffix { .. })
                && host
                    .strip_suffix(self.value())
                    .is_some_and(|p| p.ends_with('.'))
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ServicePolicy {
    pub id: String,
    pub name: String,
    pub enabled: bool,
    pub priority: u32,
    pub domains: Vec<DomainMatch>,
    pub target: Target,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub catalog_key: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub catalog_version: Option<String>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PolicyRule {
    pub id: String,
    pub name: String,
    pub enabled: bool,
    pub priority: u32,
    pub matcher: Matcher,
    pub target: Target,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Probe {
    pub url: String,
    pub interval_ms: u64,
    pub timeout_ms: u64,
    pub expected_status: u16,
    pub tolerance_ms: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tls: Option<crate::Tls>,
    pub success_threshold: u8,
    pub failure_threshold: u8,
    pub switch_cooldown_ms: u64,
}
impl Probe {
    pub fn legacy(&self) -> HealthProbe {
        HealthProbe {
            url: self.url.clone(),
            interval_ms: self.interval_ms,
            timeout_ms: self.timeout_ms,
            expected_status: self.expected_status,
            tolerance_ms: self.tolerance_ms,
            tls: self.tls.clone(),
        }
    }
    pub fn validate(&self) -> Result<(), &'static str> {
        self.legacy().target()?;
        if !(1..=10).contains(&self.success_threshold)
            || !(1..=10).contains(&self.failure_threshold)
            || self.switch_cooldown_ms > 3_600_000
        {
            return Err("PolicyHealthThreshold");
        }
        Ok(())
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Group {
    pub id: String,
    pub name: String,
    #[serde(deserialize_with = "strict_strategy")]
    pub strategy: PolicyStrategy,
    pub members: Vec<Target>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub selected: Option<Target>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub probe: Option<Probe>,
}
fn strict_strategy<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> Result<PolicyStrategy, D::Error> {
    let value = String::deserialize(deserializer)?;
    match value.as_str() {
        "manual" => Ok(PolicyStrategy::Manual),
        "url_test" => Ok(PolicyStrategy::UrlTest),
        "fallback" => Ok(PolicyStrategy::Fallback),
        "load_balance" => Ok(PolicyStrategy::LoadBalance),
        _ => Err(serde::de::Error::custom("PolicyStrategy")),
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MissingTarget {
    pub kind: MissingKind,
    pub id: String,
    pub safe_label: String,
    pub reason: MissingReason,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", try_from = "String")]
pub enum MissingKind {
    Node,
    Group,
}
impl TryFrom<String> for MissingKind {
    type Error = &'static str;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        match value.as_str() {
            "node" => Ok(Self::Node),
            "group" => Ok(Self::Group),
            _ => Err("MissingTargetKind"),
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", try_from = "String")]
pub enum MissingReason {
    MissingSource,
    DeletedTarget,
}
impl TryFrom<String> for MissingReason {
    type Error = &'static str;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        match value.as_str() {
            "missing_source" => Ok(Self::MissingSource),
            "deleted_target" => Ok(Self::DeletedTarget),
            _ => Err("MissingTargetReason"),
        }
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PolicyDocument {
    pub schema: u32,
    pub mode: Mode,
    pub default_policy: DefaultPolicy,
    #[serde(default)]
    pub service_policies: Vec<ServicePolicy>,
    #[serde(default)]
    pub groups: Vec<Group>,
    #[serde(default)]
    pub explicit_direct_rules: Vec<PolicyRule>,
    #[serde(default)]
    pub custom_rules: Vec<PolicyRule>,
    #[serde(default)]
    pub missing_targets: Vec<MissingTarget>,
    #[serde(default)]
    pub classification_dns: ClassificationDns,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Conflict {
    pub first_id: String,
    pub second_id: String,
    pub winner_id: String,
    pub witness: String,
    pub tier: u8,
    pub blocking: bool,
    pub code: &'static str,
    pub first_priority: u32,
    pub second_priority: u32,
}

pub fn canonical_domain(value: &str) -> Result<String, &'static str> {
    if value.is_empty() || value != value.trim() || value.chars().any(char::is_control) {
        return Err("PolicyDomain");
    }
    let value = value.strip_suffix('.').unwrap_or(value);
    match url::Host::parse(value).map_err(|_| "PolicyDomain")? {
        url::Host::Domain(host) if crate::valid_host(&host) && !host.is_empty() => {
            Ok(host.to_ascii_lowercase())
        }
        _ => Err("PolicyDomain"),
    }
}
fn valid_id(id: &str) -> bool {
    uuid_bytes(id).is_some() && id.bytes().all(|b| !b.is_ascii_uppercase())
}
fn valid_name(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 256 && !value.chars().any(char::is_control)
}

impl PolicyDocument {
    pub fn normalize(&mut self) -> Result<(), &'static str> {
        for service in &mut self.service_policies {
            for domain in &mut service.domains {
                let (DomainMatch::Domain { value } | DomainMatch::DomainSuffix { value }) = domain;
                *value = canonical_domain(value)?;
            }
        }
        for rule in self
            .explicit_direct_rules
            .iter_mut()
            .chain(&mut self.custom_rules)
        {
            if let Matcher::Domain { value } | Matcher::DomainSuffix { value } = &mut rule.matcher {
                *value = canonical_domain(value)?;
            }
        }
        self.groups.sort_by(|a, b| a.id.cmp(&b.id));
        self.service_policies
            .sort_by(|a, b| (a.priority, &a.id).cmp(&(b.priority, &b.id)));
        self.explicit_direct_rules
            .sort_by(|a, b| (a.priority, &a.id).cmp(&(b.priority, &b.id)));
        self.custom_rules
            .sort_by(|a, b| (a.priority, &a.id).cmp(&(b.priority, &b.id)));
        self.missing_targets
            .sort_by(|a, b| (a.kind as u8, &a.id).cmp(&(b.kind as u8, &b.id)));
        Ok(())
    }
    pub fn missing(&self, target: &Target) -> bool {
        self.missing_targets.iter().any(|missing| match target {
            Target::Node { id } => missing.kind == MissingKind::Node && &missing.id == id,
            Target::Group { id } => missing.kind == MissingKind::Group && &missing.id == id,
            _ => false,
        })
    }
    pub fn group(&self, id: &str) -> Option<&Group> {
        self.groups.iter().find(|g| g.id == id)
    }
    pub fn reachable_nodes(&self, target: &Target) -> Result<BTreeSet<String>, &'static str> {
        fn visit(
            doc: &PolicyDocument,
            target: &Target,
            depth: usize,
            remaining: &mut usize,
            visited: &mut BTreeSet<String>,
            result: &mut BTreeSet<String>,
        ) -> Result<(), &'static str> {
            *remaining = remaining.checked_sub(1).ok_or("PolicyResolutionBudget")?;
            if depth > 16 {
                return Err("PolicyDepth");
            }
            match target {
                Target::Node { id } => {
                    if !doc.missing(target) {
                        result.insert(id.clone());
                    }
                }
                Target::Group { id } => {
                    if visited.insert(id.clone())
                        && let Some(group) = doc.group(id)
                    {
                        for member in &group.members {
                            visit(doc, member, depth + 1, remaining, visited, result)?;
                        }
                    }
                }
                Target::Direct {} => {
                    result.insert(DIRECT_NODE_ID.to_owned());
                }
                _ => {}
            }
            Ok(())
        }
        // Validated graphs contain at most 4096 edges. Memoize group closures
        // below in validation; this bounded traversal also protects callers.
        let mut result = BTreeSet::new();
        visit(
            self,
            target,
            0,
            &mut 8192,
            &mut BTreeSet::new(),
            &mut result,
        )?;
        Ok(result)
    }
    pub fn validate(&self, nodes: &[Node]) -> Result<Vec<Conflict>, &'static str> {
        if self.schema != 2
            || self.default_policy.id != DEFAULT_POLICY_ID
            || self.groups.len() > 128
            || self.service_policies.len() > 1000
            || self.explicit_direct_rules.len()
                + self.custom_rules.len()
                + self
                    .service_policies
                    .iter()
                    .map(|s| s.domains.len())
                    .sum::<usize>()
                > 4096
            || self.missing_targets.len() > 2512
        {
            return Err("PolicyBounds");
        }
        if !matches!(
            self.default_policy.target,
            Target::Node { .. } | Target::Group { .. } | Target::Unconfigured {}
        ) {
            return Err("DefaultProxyRequired");
        }
        let node_ids: BTreeSet<_> = nodes.iter().map(|n| n.id.as_str()).collect();
        let mut group_ids = BTreeSet::new();
        for group in &self.groups {
            if !valid_id(&group.id)
                || !valid_name(&group.name)
                || !group_ids.insert(group.id.as_str())
                || node_ids.contains(group.id.as_str())
            {
                return Err("PolicyGroupId");
            }
        }
        let mut missing_ids = BTreeSet::new();
        for missing in &self.missing_targets {
            if !valid_id(&missing.id)
                || !valid_name(&missing.safe_label)
                || !missing_ids.insert((missing.kind as u8, missing.id.as_str()))
                || (missing.kind == MissingKind::Node && node_ids.contains(missing.id.as_str()))
                || (missing.kind == MissingKind::Group && group_ids.contains(missing.id.as_str()))
            {
                return Err("MissingTargetDeclaration");
            }
        }
        let check_target = |target: &Target| -> Result<(), &'static str> {
            if self.missing(target) {
                return Ok(());
            }
            match target {
                Target::Node { id } if !node_ids.contains(id.as_str()) => Err("PolicyNodeMissing"),
                Target::Group { id } if !group_ids.contains(id.as_str()) => {
                    Err("PolicyGroupMissing")
                }
                Target::Node { id }
                    if nodes.iter().any(|n| {
                        &n.id == id
                            && matches!(n.outbound, Outbound::Direct {} | Outbound::Reject {})
                    }) =>
                {
                    Err("PolicyNodeMustProxy")
                }
                Target::Unconfigured {} => Err("PolicyTargetUnconfigured"),
                _ => Ok(()),
            }
        };
        if !matches!(self.default_policy.target, Target::Unconfigured {}) {
            check_target(&self.default_policy.target)?;
        }
        let mut edges = 0;
        let mut automatic = 0;
        for group in &self.groups {
            edges += group.members.len();
            if edges > 4096
                || group.members.len()
                    > if group.strategy == PolicyStrategy::Manual {
                        512
                    } else {
                        64
                    }
            {
                return Err("PolicyMemberBudget");
            }
            let mut members = BTreeSet::new();
            for member in &group.members {
                check_target(member)?;
                if !members.insert(member) {
                    return Err("PolicyDuplicateMember");
                }
            }
            if group.strategy == PolicyStrategy::Manual {
                if group.probe.is_some() {
                    return Err("ManualPolicyProbeUnsupported");
                }
                if group
                    .selected
                    .as_ref()
                    .is_some_and(|s| !group.members.contains(s))
                {
                    return Err("PolicySelectionNotMember");
                }
            } else {
                automatic += 1;
                if automatic > 32 {
                    return Err("PolicyProbeBudget");
                }
                if group.selected.is_some() {
                    return Err("AutomaticPolicySelection");
                }
                let probe = group.probe.as_ref().ok_or("PolicyProbeRequired")?;
                probe.validate()?;
                if group.strategy != PolicyStrategy::UrlTest && probe.tolerance_ms != 0 {
                    return Err("PolicyToleranceUnsupported");
                }
            }
        }
        fn graph(
            doc: &PolicyDocument,
            id: &str,
            active: &mut BTreeSet<String>,
            cache: &mut BTreeMap<String, usize>,
        ) -> Result<usize, &'static str> {
            if active.contains(id) {
                return Err("PolicyCycle");
            }
            if let Some(depth) = cache.get(id) {
                return Ok(*depth);
            }
            let Some(group) = doc.group(id) else {
                return Ok(0);
            };
            active.insert(id.to_owned());
            let mut depth = 1;
            for member in &group.members {
                if let Target::Group { id } = member {
                    depth = depth.max(1 + graph(doc, id, active, cache)?);
                }
            }
            active.remove(id);
            if depth > 16 {
                return Err("PolicyDepth");
            }
            cache.insert(id.to_owned(), depth);
            Ok(depth)
        }
        let mut depths = BTreeMap::new();
        for group in &self.groups {
            graph(self, &group.id, &mut BTreeSet::new(), &mut depths)?;
        }
        fn proxy_only(
            doc: &PolicyDocument,
            target: &Target,
            seen: &mut BTreeSet<String>,
        ) -> Result<(), &'static str> {
            match target {
                Target::Node { .. } | Target::Unconfigured {} => Ok(()),
                Target::Group { id } => {
                    if !seen.insert(id.clone()) {
                        return Ok(());
                    }
                    if let Some(group) = doc.group(id) {
                        for member in &group.members {
                            proxy_only(doc, member, seen)?;
                        }
                    }
                    Ok(())
                }
                _ => Err("DefaultProxyRequired"),
            }
        }
        proxy_only(self, &self.default_policy.target, &mut BTreeSet::new())?;
        let mut jobs = BTreeSet::new();
        for group in self
            .groups
            .iter()
            .filter(|g| g.strategy != PolicyStrategy::Manual)
        {
            let profile = serde_json::to_string(group.probe.as_ref().ok_or("PolicyProbeRequired")?)
                .map_err(|_| "PolicyProbeProfile")?;
            for leaf in self.reachable_nodes(&Target::Group {
                id: group.id.clone(),
            })? {
                jobs.insert((leaf, profile.clone()));
            }
        }
        if jobs.len() > 512 {
            return Err("PolicyProbeBudget");
        }
        let mut entity_ids = BTreeSet::new();
        let mut exact_domains = BTreeMap::new();
        let mut priorities = BTreeSet::new();
        for service in &self.service_policies {
            if !valid_id(&service.id)
                || !valid_name(&service.name)
                || !entity_ids.insert(service.id.as_str())
                || service.domains.is_empty()
                || service.domains.len() > 128
            {
                return Err("ServicePolicyBounds");
            }
            if service.enabled && !priorities.insert(service.priority) {
                return Err("PolicyPriorityConflict");
            }
            if service.catalog_key.as_ref().is_some_and(|s| {
                s.len() > 64
                    || !s
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b))
            }) || service
                .catalog_version
                .as_ref()
                .is_some_and(|s| s.len() > 64 || s.chars().any(char::is_control))
            {
                return Err("ServiceCatalogIdentity");
            }
            check_target(&service.target)?;
            let mut domains = BTreeSet::new();
            for domain in &service.domains {
                let key = (
                    matches!(domain, DomainMatch::DomainSuffix { .. }),
                    domain.value(),
                );
                if canonical_domain(domain.value())? != domain.value() || !domains.insert(key) {
                    return Err("PolicyDomain");
                }
                if service.enabled
                    && exact_domains
                        .insert(key, &service.target)
                        .is_some_and(|previous| previous != &service.target)
                {
                    return Err("PolicyRuleConflict");
                }
            }
        }
        for (direct, rules) in [
            (true, &self.explicit_direct_rules),
            (false, &self.custom_rules),
        ] {
            let mut priorities = BTreeSet::new();
            let mut exact_matchers = BTreeMap::new();
            for rule in rules {
                if !valid_id(&rule.id)
                    || !valid_name(&rule.name)
                    || !entity_ids.insert(rule.id.as_str())
                {
                    return Err("PolicyRuleId");
                }
                if rule.enabled && !priorities.insert(rule.priority) {
                    return Err("PolicyPriorityConflict");
                }
                if direct && !matches!(rule.target, Target::Direct {}) {
                    return Err("ExplicitDirectTarget");
                }
                check_target(&rule.target)?;
                if rule.enabled
                    && exact_matchers
                        .insert(
                            serde_json::to_string(&rule.matcher).map_err(|_| "RuleMatcher")?,
                            &rule.target,
                        )
                        .is_some_and(|previous| previous != &rule.target)
                {
                    return Err("PolicyRuleConflict");
                }
                match &rule.matcher {
                    Matcher::Domain { value } | Matcher::DomainSuffix { value }
                        if canonical_domain(value)? != *value =>
                    {
                        return Err("PolicyDomain");
                    }
                    Matcher::DomainKeyword { value }
                        if value.is_empty()
                            || value.len() > 253
                            || !value.is_ascii()
                            || value.chars().any(char::is_control) =>
                    {
                        return Err("RuleKeyword");
                    }
                    Matcher::DestinationPort { value: 0 } => return Err("RulePort"),
                    _ => {}
                }
            }
        }
        let conflicts = self.conflicts();
        if conflicts.iter().any(|c| c.blocking) {
            return Err("PolicyRuleConflict");
        }
        Ok(conflicts)
    }
    pub fn conflicts(&self) -> Vec<Conflict> {
        let enabled: Vec<_> = self.service_policies.iter().filter(|s| s.enabled).collect();
        let mut result = Vec::new();
        fn push(result: &mut Vec<Conflict>, value: Conflict) {
            if result.len() < 512 {
                result.push(value)
            } else if value.blocking
                && let Some(index) = result.iter().rposition(|value| !value.blocking)
            {
                result[index] = value;
            }
        }
        for (index, first) in enabled.iter().enumerate() {
            for second in enabled.iter().skip(index + 1) {
                if first.priority == second.priority {
                    push(
                        &mut result,
                        Conflict {
                            first_id: first.id.clone(),
                            second_id: second.id.clone(),
                            winner_id: String::new(),
                            witness: first.domains.first().map_or("", DomainMatch::value).into(),
                            tier: 2,
                            blocking: true,
                            code: "PolicyPriorityConflict",
                            first_priority: first.priority,
                            second_priority: second.priority,
                        },
                    );
                }
                for a in &first.domains {
                    for b in &second.domains {
                        let witness = if a.matches(b.value()) {
                            Some(b.value())
                        } else if b.matches(a.value()) {
                            Some(a.value())
                        } else {
                            None
                        };
                        if let Some(witness) = witness {
                            let exact_duplicate = a == b && first.target != second.target;
                            push(
                                &mut result,
                                Conflict {
                                    first_id: first.id.clone(),
                                    second_id: second.id.clone(),
                                    winner_id: if first.priority < second.priority {
                                        first.id.clone()
                                    } else {
                                        second.id.clone()
                                    },
                                    witness: witness.to_owned(),
                                    tier: 2,
                                    blocking: exact_duplicate,
                                    code: if exact_duplicate {
                                        "DuplicateServiceTarget"
                                    } else {
                                        "ServiceShadow"
                                    },
                                    first_priority: first.priority,
                                    second_priority: second.priority,
                                },
                            );
                        }
                    }
                }
            }
        }
        for (tier, rules) in [(1, &self.explicit_direct_rules), (4, &self.custom_rules)] {
            let enabled: Vec<_> = rules.iter().filter(|rule| rule.enabled).collect();
            for (index, first) in enabled.iter().enumerate() {
                for second in enabled.iter().skip(index + 1) {
                    let witness = matcher_witness(&first.matcher, &second.matcher);
                    let duplicate =
                        first.matcher == second.matcher && first.target != second.target;
                    let priority = first.priority == second.priority;
                    if witness.is_some() || priority {
                        push(
                            &mut result,
                            Conflict {
                                first_id: first.id.clone(),
                                second_id: second.id.clone(),
                                winner_id: if priority {
                                    String::new()
                                } else if first.priority < second.priority {
                                    first.id.clone()
                                } else {
                                    second.id.clone()
                                },
                                witness: witness.unwrap_or_default(),
                                tier,
                                blocking: duplicate || priority,
                                code: if priority {
                                    "PolicyPriorityConflict"
                                } else if duplicate {
                                    "DuplicateRuleTarget"
                                } else {
                                    "RuleShadow"
                                },
                                first_priority: first.priority,
                                second_priority: second.priority,
                            },
                        );
                    }
                }
            }
        }
        for service in self
            .service_policies
            .iter()
            .filter(|service| service.enabled)
        {
            for domain in &service.domains {
                let matcher = match domain {
                    DomainMatch::Domain { value } => Matcher::Domain {
                        value: value.clone(),
                    },
                    DomainMatch::DomainSuffix { value } => Matcher::DomainSuffix {
                        value: value.clone(),
                    },
                };
                for (tier, rules) in [(1, &self.explicit_direct_rules), (4, &self.custom_rules)] {
                    for rule in rules.iter().filter(|r| r.enabled) {
                        if let Some(witness) = matcher_witness(&matcher, &rule.matcher) {
                            push(
                                &mut result,
                                Conflict {
                                    first_id: service.id.clone(),
                                    second_id: rule.id.clone(),
                                    winner_id: if tier == 1 {
                                        rule.id.clone()
                                    } else {
                                        service.id.clone()
                                    },
                                    witness,
                                    tier: tier.min(2),
                                    blocking: false,
                                    code: "FixedTierShadow",
                                    first_priority: service.priority,
                                    second_priority: rule.priority,
                                },
                            );
                        }
                    }
                }
            }
        }
        for first in self
            .explicit_direct_rules
            .iter()
            .filter(|rule| rule.enabled)
        {
            for second in self.custom_rules.iter().filter(|rule| rule.enabled) {
                if let Some(witness) = matcher_witness(&first.matcher, &second.matcher) {
                    push(
                        &mut result,
                        Conflict {
                            first_id: first.id.clone(),
                            second_id: second.id.clone(),
                            winner_id: first.id.clone(),
                            witness,
                            tier: 1,
                            blocking: false,
                            code: "FixedTierShadow",
                            first_priority: first.priority,
                            second_priority: second.priority,
                        },
                    );
                }
            }
        }
        result
    }
    pub fn validate_start(&self) -> Result<(), &'static str> {
        if self.mode == Mode::Direct {
            return Ok(());
        }
        if matches!(self.default_policy.target, Target::Unconfigured {}) {
            return Err("DefaultUnconfigured");
        }
        if self.missing(&self.default_policy.target) {
            return Err("MissingTarget");
        }
        fn available(
            doc: &PolicyDocument,
            target: &Target,
            depth: usize,
            visited: &mut BTreeSet<String>,
        ) -> Result<(), &'static str> {
            if depth > 16 {
                return Err("PolicyDepth");
            };
            if doc.missing(target) {
                return Err("MissingTarget");
            }
            match target {
                Target::Node { .. } => Ok(()),
                Target::Group { id } => {
                    if !visited.insert(id.clone()) {
                        return Err("PolicyUnavailable");
                    }
                    let group = doc.group(id).ok_or("MissingTarget")?;
                    if group.strategy == PolicyStrategy::Manual {
                        available(
                            doc,
                            group.selected.as_ref().ok_or("PolicyUnavailable")?,
                            depth + 1,
                            visited,
                        )
                    } else {
                        if group
                            .members
                            .iter()
                            .any(|member| available(doc, member, depth + 1, visited).is_ok())
                        {
                            Ok(())
                        } else {
                            Err("PolicyUnavailable")
                        }
                    }
                }
                Target::Unconfigured {} => Err("DefaultUnconfigured"),
                _ => Err("DefaultProxyRequired"),
            }
        }
        available(self, &self.default_policy.target, 0, &mut BTreeSet::new())
    }
}

fn matcher_witness(a: &Matcher, b: &Matcher) -> Option<String> {
    let domains = |matcher: &Matcher| match matcher {
        Matcher::Domain { value } => Some(DomainMatch::Domain {
            value: value.clone(),
        }),
        Matcher::DomainSuffix { value } => Some(DomainMatch::DomainSuffix {
            value: value.clone(),
        }),
        _ => None,
    };
    if let (Some(a), Some(b)) = (domains(a), domains(b)) {
        return if a.matches(b.value()) {
            Some(b.value().into())
        } else if b.matches(a.value()) {
            Some(a.value().into())
        } else {
            None
        };
    }
    match (a, b) {
        (Matcher::Cidr { value: a, .. }, Matcher::Cidr { value: b, .. })
        | (Matcher::SourceCidr { value: a }, Matcher::SourceCidr { value: b }) => {
            if a.contains(&b.addr()) {
                Some(b.addr().to_string())
            } else if b.contains(&a.addr()) {
                Some(a.addr().to_string())
            } else {
                None
            }
        }
        (Matcher::DestinationPort { value: a }, Matcher::DestinationPort { value: b })
            if a == b =>
        {
            Some(format!("target-port:{a}"))
        }
        (Matcher::DomainKeyword { value: a }, Matcher::DomainKeyword { value: b }) => {
            Some(format!("{a}.{b}.invalid"))
        }
        (Matcher::Match {}, Matcher::Domain { value } | Matcher::DomainSuffix { value })
        | (Matcher::Domain { value } | Matcher::DomainSuffix { value }, Matcher::Match {}) => {
            Some(value.clone())
        }
        (Matcher::Match {}, Matcher::Match {}) => Some("unclassified.invalid".into()),
        _ => None,
    }
}

/// Shared strict protocol/listener/DNS validator without translating policy
/// groups to legacy selectors (which would silently discard nested semantics).
pub fn validate_runtime_base(config: &Config) -> Result<(), &'static str> {
    config.validate()
}

#[cfg(test)]
#[path = "v2_tests.rs"]
mod tests;
