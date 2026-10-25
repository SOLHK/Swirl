use super::*;
const NODE: &str = "10000000-0000-4000-8000-000000000001";
fn id(n: u32) -> String {
    format!("20000000-0000-4000-8000-{n:012}")
}
fn nodes() -> Vec<Node> {
    vec![Node {
        id: NODE.into(),
        outbound: Outbound::Socks5 {
            host: "127.0.0.1".into(),
            port: 9,
            auth: None,
            tls: None,
            udp: false,
        },
    }]
}
fn document() -> PolicyDocument {
    PolicyDocument {
        schema: 2,
        mode: Mode::Rule,
        default_policy: DefaultPolicy {
            id: DEFAULT_POLICY_ID.into(),
            target: Target::Node { id: NODE.into() },
        },
        service_policies: vec![],
        groups: vec![],
        explicit_direct_rules: vec![],
        custom_rules: vec![],
        missing_targets: vec![],
        classification_dns: ClassificationDns::Disabled,
    }
}
#[test]
fn strict_document_rejects_process_fields_instead_of_downgrading() {
    let mut value = serde_json::to_value(document()).unwrap();
    value["processes"] = serde_json::json!(["fixture.exe"]);
    assert!(serde_json::from_value::<PolicyDocument>(value).is_err());
}
#[test]
fn default_policy_rejects_hidden_direct_branch() {
    let mut doc = document();
    doc.groups.push(Group {
        id: id(1),
        name: "Proxy".into(),
        strategy: PolicyStrategy::Manual,
        members: vec![Target::Node { id: NODE.into() }, Target::Direct {}],
        selected: Some(Target::Node { id: NODE.into() }),
        probe: None,
    });
    doc.default_policy.target = Target::Group { id: id(1) };
    assert_eq!(doc.validate(&nodes()).unwrap_err(), "DefaultProxyRequired");
}
#[test]
fn graph_validation_rejects_unselected_cycle() {
    let mut doc = document();
    doc.groups = vec![
        Group {
            id: id(1),
            name: "One".into(),
            strategy: PolicyStrategy::Manual,
            members: vec![
                Target::Node { id: NODE.into() },
                Target::Group { id: id(2) },
            ],
            selected: Some(Target::Node { id: NODE.into() }),
            probe: None,
        },
        Group {
            id: id(2),
            name: "Two".into(),
            strategy: PolicyStrategy::Manual,
            members: vec![Target::Group { id: id(1) }],
            selected: Some(Target::Group { id: id(1) }),
            probe: None,
        },
    ];
    assert_eq!(doc.validate(&nodes()).unwrap_err(), "PolicyCycle");
}
#[test]
fn unknown_references_require_explicit_safe_tombstone() {
    let mut doc = document();
    doc.default_policy.target = Target::Node { id: id(42) };
    assert_eq!(doc.validate(&nodes()).unwrap_err(), "PolicyNodeMissing");
    doc.missing_targets.push(MissingTarget {
        kind: MissingKind::Node,
        id: id(42),
        safe_label: "Deleted source node".into(),
        reason: MissingReason::MissingSource,
    });
    assert!(doc.validate(&nodes()).is_ok());
    assert_eq!(doc.validate_start(), Err("MissingTarget"));
}
#[test]
fn domain_normalization_has_idna_and_label_boundary() {
    assert_eq!(
        canonical_domain("例子.测试.").unwrap(),
        "xn--fsqu00a.xn--0zwm56d"
    );
    let domain = DomainMatch::DomainSuffix {
        value: "example.com".into(),
    };
    assert!(domain.matches("example.com"));
    assert!(domain.matches("a.example.com"));
    assert!(!domain.matches("notexample.com"));
    assert_eq!(canonical_domain("example.com/path"), Err("PolicyDomain"));
}
#[test]
fn overlapping_services_have_explicit_witness_and_priority() {
    let mut doc = document();
    for (n, value, priority) in [
        (1, "googleapis.com", 20),
        (2, "youtubei.googleapis.com", 10),
    ] {
        doc.service_policies.push(ServicePolicy {
            id: id(n),
            name: "Fixture service".into(),
            enabled: true,
            priority,
            domains: vec![DomainMatch::DomainSuffix {
                value: value.into(),
            }],
            target: Target::Node { id: NODE.into() },
            catalog_key: None,
            catalog_version: None,
        });
    }
    let conflicts = doc.validate(&nodes()).unwrap();
    assert_eq!(
        conflicts,
        vec![Conflict {
            first_id: id(1),
            second_id: id(2),
            winner_id: id(2),
            witness: "youtubei.googleapis.com".into(),
            tier: 2,
            blocking: false,
            code: "ServiceShadow",
            first_priority: 20,
            second_priority: 10
        }]
    );
    doc.service_policies[1].priority = 20;
    assert_eq!(
        doc.validate(&nodes()).unwrap_err(),
        "PolicyPriorityConflict"
    );
}
#[test]
fn strict_target_rejects_credentials_or_unused_id() {
    assert!(serde_json::from_str::<Target>(r#"{"kind":"direct","id":"fixture"}"#).is_err());
    assert!(
        serde_json::from_str::<Target>(r#"{"kind":"node","id":"fixture","password":"fixture"}"#)
            .is_err()
    );
}
#[test]
fn policy_scalar_enums_reject_object_encodings_and_aliases() {
    for input in [r#"{"direct":null}"#, r#"true"#, r#"2"#] {
        assert!(serde_json::from_str::<Mode>(input).is_err());
    }
    assert!(serde_json::from_str::<ClassificationDns>(r#"{"disabled":null}"#).is_err());
    assert!(serde_json::from_str::<MissingKind>(r#"{"node":null}"#).is_err());
    let mut group = serde_json::to_value(Group {
        id: id(1),
        name: "Fixture".into(),
        strategy: PolicyStrategy::Manual,
        members: vec![],
        selected: None,
        probe: None,
    })
    .unwrap();
    group["strategy"] = serde_json::json!({"manual":null});
    assert!(serde_json::from_value::<Group>(group).is_err());
}
#[test]
fn default_unconfigured_is_a_draft_but_not_a_startable_proxy() {
    let mut doc = document();
    doc.default_policy.target = Target::Unconfigured {};
    assert!(doc.validate(&nodes()).is_ok());
    assert_eq!(doc.validate_start(), Err("DefaultUnconfigured"));
    doc.mode = Mode::Direct;
    assert_eq!(doc.validate_start(), Ok(()));
}
