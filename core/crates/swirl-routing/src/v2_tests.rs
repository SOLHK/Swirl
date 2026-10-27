use super::*;
use swirl_subscription::v2::{DEFAULT_POLICY_ID, DefaultPolicy, DomainMatch, ServicePolicy};
fn id(n: u32) -> String {
    format!("30000000-0000-4000-8000-{n:012}")
}
fn policy() -> PolicyDocument {
    PolicyDocument {
        schema: 2,
        mode: Mode::Rule,
        default_policy: DefaultPolicy {
            id: DEFAULT_POLICY_ID.into(),
            target: Target::Node { id: id(1) },
        },
        service_policies: vec![],
        groups: vec![],
        explicit_direct_rules: vec![],
        custom_rules: vec![],
        missing_targets: vec![],
        classification_dns: ClassificationDns::Disabled,
    }
}
fn decide(doc: &PolicyDocument, host: &str) -> RouteDecision {
    let (domains, ips) = crate::shared_bundled_rules().unwrap();
    select(
        doc,
        host,
        443,
        "127.0.0.1".parse().unwrap(),
        None,
        false,
        Some((&domains, &ips)),
    )
    .unwrap()
}
#[test]
fn custom_proxy_rule_cannot_override_china_tier() {
    let mut doc = policy();
    doc.custom_rules.push(PolicyRule {
        id: id(2),
        name: "Baidu proxy attempt".into(),
        enabled: true,
        priority: 0,
        matcher: Matcher::DomainSuffix {
            value: "baidu.com".into(),
        },
        target: Target::Node { id: id(3) },
    });
    let result = decide(&doc, "www.baidu.com");
    assert_eq!(
        (result.target, result.tier, result.rule_id),
        (Target::Direct {}, 3, "builtin:cn-domain".into())
    );
}
#[test]
fn service_and_china_defaults_coexist() {
    let mut doc = policy();
    doc.service_policies.push(ServicePolicy {
        id: id(2),
        name: "OpenAI".into(),
        enabled: true,
        priority: 0,
        domains: vec![DomainMatch::DomainSuffix {
            value: "openai.com".into(),
        }],
        target: Target::Node { id: id(3) },
        catalog_key: Some("openai".into()),
        catalog_version: None,
    });
    let result = decide(&doc, "api.openai.com");
    assert_eq!(
        (result.target, result.tier, result.service_policy_id),
        (Target::Node { id: id(3) }, 2, Some(id(2)))
    );
    assert_eq!(decide(&doc, "baidu.com").target, Target::Direct {});
    assert_eq!(
        decide(&doc, "unknown.fixture.invalid").target,
        doc.default_policy.target
    );
}
#[test]
fn global_keeps_only_fixed_local_exceptions() {
    let mut doc = policy();
    doc.mode = Mode::Global;
    doc.explicit_direct_rules.push(PolicyRule {
        id: id(2),
        name: "Explicit public direct".into(),
        enabled: true,
        priority: 0,
        matcher: Matcher::DomainSuffix {
            value: "fixture.invalid".into(),
        },
        target: Target::Direct {},
    });
    assert_eq!(
        decide(&doc, "public.fixture.invalid").target,
        doc.default_policy.target
    );
    assert_eq!(decide(&doc, "baidu.com").target, doc.default_policy.target);
    for host in [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.0.1",
        "100.64.0.1",
        "fc00::1",
        "fe80::1",
        "::ffff:192.168.1.1",
        "localhost",
    ] {
        assert_eq!(decide(&doc, host).target, Target::Direct {});
    }
}
#[test]
fn unavailable_china_classification_defaults_but_mandatory_rule_cannot_skip() {
    let mut doc = policy();
    doc.classification_dns = ClassificationDns::DirectEncrypted;
    let (domains, ips) = crate::shared_bundled_rules().unwrap();
    let china = Some((domains.as_ref(), ips.as_ref()));
    assert_eq!(
        select(
            &doc,
            "unclassified.invalid",
            443,
            "127.0.0.1".parse().unwrap(),
            None,
            false,
            china
        )
        .unwrap()
        .resolution,
        Some(ResolutionPurpose::ChinaClassification)
    );
    let result = select(
        &doc,
        "unclassified.invalid",
        443,
        "127.0.0.1".parse().unwrap(),
        None,
        true,
        china,
    )
    .unwrap();
    assert_eq!(
        (result.target, result.classification_state),
        (doc.default_policy.target.clone(), "unavailable")
    );
    doc.custom_rules.push(PolicyRule {
        id: id(2),
        name: "Block CIDR".into(),
        enabled: true,
        priority: 0,
        matcher: Matcher::Cidr {
            value: "203.0.113.0/24".parse().unwrap(),
            resolve: true,
        },
        target: Target::Reject {},
    });
    assert_eq!(
        select(
            &doc,
            "unclassified.invalid",
            443,
            "127.0.0.1".parse().unwrap(),
            None,
            true,
            china
        )
        .unwrap()
        .resolution,
        Some(ResolutionPurpose::MandatoryRule)
    );
}
#[test]
fn selected_address_controls_china_classification_not_any_answer() {
    let doc = policy();
    let (domains, ips) = crate::shared_bundled_rules().unwrap();
    assert!(ips.matches_ip("114.114.114.114".parse().unwrap()));
    let china = Some((domains.as_ref(), ips.as_ref()));
    let proxy = select(
        &doc,
        "unclassified.invalid",
        443,
        "127.0.0.1".parse().unwrap(),
        Some("203.0.113.1".parse().unwrap()),
        true,
        china,
    )
    .unwrap();
    let direct = select(
        &doc,
        "unclassified.invalid",
        443,
        "127.0.0.1".parse().unwrap(),
        Some("114.114.114.114".parse().unwrap()),
        true,
        china,
    )
    .unwrap();
    assert_eq!(proxy.target, doc.default_policy.target);
    assert_eq!(
        (direct.target, direct.classification_state),
        (Target::Direct {}, "china_ip")
    );
}
#[test]
fn invalid_network_destinations_are_never_proxy_fallbacks() {
    let doc = policy();
    for host in ["0.0.0.0", "::", "224.0.0.1", "ff02::1", "255.255.255.255"] {
        let (domains, ips) = crate::shared_bundled_rules().unwrap();
        assert_eq!(
            select(
                &doc,
                host,
                443,
                "127.0.0.1".parse().unwrap(),
                None,
                false,
                Some((&domains, &ips))
            ),
            Err("InvalidTarget")
        );
    }
}
#[test]
fn local_looking_domain_needs_actual_local_mapping() {
    let doc = policy();
    assert_eq!(
        decide(&doc, "public.local").target,
        doc.default_policy.target
    );
    let (domains, ips) = crate::shared_bundled_rules().unwrap();
    assert_eq!(
        select(
            &doc,
            "public.local",
            443,
            "127.0.0.1".parse().unwrap(),
            Some("10.0.0.2".parse().unwrap()),
            false,
            Some((&domains, &ips))
        )
        .unwrap()
        .target,
        Target::Direct {}
    );
}
