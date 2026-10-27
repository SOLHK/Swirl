use super::*;
use swirl_subscription::v2::{ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, Group, Mode};
fn id(n: u32) -> String {
    format!("20000000-0000-4000-8000-{n:012}")
}
fn probe() -> Probe {
    Probe {
        url: "http://127.0.0.1:9/check".into(),
        interval_ms: 300000,
        timeout_ms: 100,
        expected_status: 204,
        tolerance_ms: 0,
        tls: None,
        success_threshold: 1,
        failure_threshold: 2,
        switch_cooldown_ms: 0,
    }
}
fn node(n: u32) -> Node {
    Node {
        id: id(n),
        outbound: swirl_subscription::Outbound::Socks5 {
            host: "127.0.0.1".into(),
            port: 9,
            auth: None,
            tls: None,
            udp: false,
        },
    }
}
fn document(groups: Vec<Group>) -> PolicyDocument {
    PolicyDocument {
        schema: 2,
        mode: Mode::Rule,
        default_policy: DefaultPolicy {
            id: DEFAULT_POLICY_ID.into(),
            target: Target::Group { id: id(100) },
        },
        service_policies: vec![],
        groups,
        explicit_direct_rules: vec![],
        custom_rules: vec![],
        missing_targets: vec![],
        classification_dns: ClassificationDns::Disabled,
    }
}
fn group(n: u32, strategy: PolicyStrategy, members: Vec<Target>) -> Group {
    Group {
        id: id(n),
        name: format!("Group {n}"),
        strategy,
        selected: (strategy == PolicyStrategy::Manual).then(|| members[0].clone()),
        probe: (strategy != PolicyStrategy::Manual).then(probe),
        members,
    }
}
fn health(runtime: &PolicyRuntime, leaf: &str, latency: u64) {
    let mut registry = runtime.registry.lock().unwrap();
    for profile in runtime.profiles.values() {
        registry.health.insert(
            (profile.clone(), leaf.into()),
            Health {
                latency: Some(latency),
                checked: Instant::now(),
                successes: 1,
                failures: 0,
                eligible: true,
                error: "",
            },
        );
    }
}
#[test]
fn all_sixteen_parent_child_strategies_keep_both_constraints() {
    let runtime = tokio::runtime::Runtime::new().unwrap();
    for parent in [
        PolicyStrategy::Manual,
        PolicyStrategy::UrlTest,
        PolicyStrategy::Fallback,
        PolicyStrategy::LoadBalance,
    ] {
        for child in [
            PolicyStrategy::Manual,
            PolicyStrategy::UrlTest,
            PolicyStrategy::Fallback,
            PolicyStrategy::LoadBalance,
        ] {
            let doc = document(vec![
                group(100, parent, vec![Target::Group { id: id(101) }]),
                group(
                    101,
                    child,
                    vec![Target::Node { id: id(1) }, Target::Node { id: id(2) }],
                ),
            ]);
            let policies = PolicyRuntime::dormant(
                runtime.handle().clone(),
                Arc::new(doc),
                &[node(1), node(2)],
                Arc::new(Resolver::default()),
                &BTreeMap::new(),
            )
            .unwrap();
            health(&policies, &id(1), 10);
            health(&policies, &id(2), 20);
            let result = policies
                .resolve(&Target::Group { id: id(100) }, "service", "catalog")
                .unwrap();
            assert_eq!(result.chain, vec![id(100), id(101)]);
            assert!([id(1), id(2)].contains(&result.leaf));
        }
    }
}
#[test]
fn parent_profile_cannot_approve_child_failed_leaf() {
    let runtime = tokio::runtime::Runtime::new().unwrap();
    let mut parent = group(
        100,
        PolicyStrategy::Fallback,
        vec![Target::Group { id: id(101) }],
    );
    parent.probe.as_mut().unwrap().url = "http://127.0.0.1:10/parent".into();
    let doc = document(vec![
        parent,
        group(
            101,
            PolicyStrategy::Fallback,
            vec![Target::Node { id: id(1) }, Target::Node { id: id(2) }],
        ),
    ]);
    let policies = PolicyRuntime::dormant(
        runtime.handle().clone(),
        Arc::new(doc),
        &[node(1), node(2)],
        Arc::new(Resolver::default()),
        &BTreeMap::new(),
    )
    .unwrap();
    health(&policies, &id(1), 10);
    health(&policies, &id(2), 20);
    let parent_profile = policies.profiles[&id(100)].clone();
    policies
        .registry
        .lock()
        .unwrap()
        .health
        .get_mut(&(parent_profile, id(1)))
        .unwrap()
        .eligible = false;
    let result = policies
        .resolve(&Target::Group { id: id(100) }, "service", "catalog")
        .unwrap();
    assert_eq!(result.leaf, id(2));
}
#[test]
fn manual_child_does_not_bypass_ancestor_health_constraint() {
    let runtime = tokio::runtime::Runtime::new().unwrap();
    let doc = document(vec![
        group(
            100,
            PolicyStrategy::Fallback,
            vec![Target::Group { id: id(101) }],
        ),
        group(
            101,
            PolicyStrategy::Manual,
            vec![Target::Node { id: id(1) }, Target::Node { id: id(2) }],
        ),
    ]);
    let policies = PolicyRuntime::dormant(
        runtime.handle().clone(),
        Arc::new(doc),
        &[node(1), node(2)],
        Arc::new(Resolver::default()),
        &BTreeMap::new(),
    )
    .unwrap();
    health(&policies, &id(2), 10);
    assert_eq!(
        policies
            .resolve(&Target::Group { id: id(100) }, "service", "catalog")
            .err(),
        Some("PolicyUnavailable")
    );
}
#[test]
fn same_service_load_balance_stays_fixed_across_hostnames() {
    let runtime = tokio::runtime::Runtime::new().unwrap();
    let doc = document(vec![group(
        100,
        PolicyStrategy::LoadBalance,
        vec![Target::Node { id: id(1) }, Target::Node { id: id(2) }],
    )]);
    let policies = PolicyRuntime::dormant(
        runtime.handle().clone(),
        Arc::new(doc),
        &[node(1), node(2)],
        Arc::new(Resolver::default()),
        &BTreeMap::new(),
    )
    .unwrap();
    health(&policies, &id(1), 10);
    health(&policies, &id(2), 20);
    let first = policies
        .resolve(&Target::Group { id: id(100) }, "policy:default", "openai")
        .unwrap()
        .leaf;
    for _ in 0..100 {
        assert_eq!(
            policies
                .resolve(&Target::Group { id: id(100) }, "policy:default", "openai")
                .unwrap()
                .leaf,
            first
        );
    }
    for h in policies.registry.lock().unwrap().health.values_mut() {
        h.eligible = false;
    }
    assert_eq!(
        policies
            .resolve(&Target::Group { id: id(100) }, "policy:default", "openai")
            .err(),
        Some("PolicyUnavailable")
    );
}
