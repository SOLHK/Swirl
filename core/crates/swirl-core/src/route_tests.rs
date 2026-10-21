use super::*;

#[tokio::test]
async fn mixed_china_dns_answers_pin_the_first_address_and_its_outbound() {
    let config = Config::parse(
        br#"{
            "schema":1,"listen":"127.0.0.1:0","selected":"proxy","smart_routing":true,
            "nodes":[
                {"id":"direct","outbound":{"type":"direct"}},
                {"id":"proxy","outbound":{"type":"socks5","host":"127.0.0.1","port":1080,"auth":null}}
            ],
            "rules":[{"matcher":{"type":"match"},"outbound":"proxy"}],
            "dns":{"servers":["127.0.0.1:5353"]}
        }"#,
    )
    .unwrap();
    let (domains, ips) = shared_bundled_rules().unwrap();
    let china = Some((domains.as_ref(), ips.as_ref()));
    let target = Target {
        host: "www.example.com".into(),
        port: 443,
    };
    let source = "127.0.0.1".parse().unwrap();
    let choose = |_: &str| -> Result<String> { Err("UnexpectedPolicy") };
    let initial = swirl_routing::select_with_trace_and_china(
        &config,
        &target.host,
        target.port,
        source,
        None,
        &choose,
        china,
    )
    .unwrap();
    assert!(matches!(initial.decision, swirl_routing::Decision::Resolve));

    let foreign: SocketAddr = "8.8.8.8:443".parse().unwrap();
    let domestic: SocketAddr = "114.114.114.114:443".parse().unwrap();
    let resolver = Resolver::default().with_config(&config.dns).unwrap();
    for (answers, expected_node, expected_rule) in [
        ([foreign, domestic], "proxy", "#1 MATCH => proxy"),
        ([domestic, foreign], "direct", "MRS:CN-IP"),
    ] {
        let (node, routed, matched, direct_addresses) = route_resolved(
            &config,
            &target,
            source,
            &answers,
            (&choose, &choose),
            china,
            true,
        )
        .unwrap();
        assert_eq!(node.id, expected_node);
        assert_eq!(swirl_routing::rule_label(&config, matched), expected_rule);
        assert_eq!(routed.host, answers[0].ip().to_string());
        assert_eq!(routed.port, target.port);
        assert_eq!(
            direct_addresses,
            if expected_node == "direct" {
                vec![answers[0]]
            } else {
                Vec::new()
            }
        );
        // Outbound resolution receives a literal IP, so no second destination
        // hostname lookup can select a different answer after route matching.
        assert_eq!(
            resolver.resolve(&routed.host, routed.port).await.unwrap(),
            vec![answers[0]]
        );
    }
}

#[tokio::test]
async fn direct_resolved_candidates_fall_back_across_families_under_same_rule() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    let config = Config::parse(
        br#"{
            "schema":1,"listen":"127.0.0.1:0","selected":"direct",
            "nodes":[
                {"id":"direct","outbound":{"type":"direct"}},
                {"id":"reject","outbound":{"type":"reject"}}
            ],
            "rules":[
                {"matcher":{"type":"cidr","value":"203.0.113.0/24","resolve":true},"outbound":"reject"},
                {"matcher":{"type":"match"},"outbound":"direct"}
            ]
        }"#,
    )
    .unwrap();
    let target = Target {
        host: "dual.example".into(),
        port,
    };
    let first = SocketAddr::new(IpAddr::V6(std::net::Ipv6Addr::LOCALHOST), port);
    let second = SocketAddr::new(IpAddr::V4(std::net::Ipv4Addr::LOCALHOST), port);
    let choose = |_: &str| -> Result<String> { Err("UnexpectedPolicy") };
    let (node, routed, rule, candidates) = route_resolved(
        &config,
        &target,
        IpAddr::V4(std::net::Ipv4Addr::LOCALHOST),
        &[first, second, second],
        (&choose, &choose),
        None,
        true,
    )
    .unwrap();
    assert_eq!(node.id, "direct");
    assert_eq!(
        swirl_routing::rule_label(&config, rule),
        "#2 MATCH => direct"
    );
    assert_eq!(routed.host, "::1");
    assert_eq!(candidates, vec![first, second]);
    let stream = swirl_protocol::connect_direct_resolved(candidates, Duration::from_secs(3))
        .await
        .unwrap();
    let (_, peer) = tokio::time::timeout(Duration::from_secs(1), listener.accept())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(peer.ip(), IpAddr::V4(std::net::Ipv4Addr::LOCALHOST));
    drop(stream);
}

#[test]
fn same_direct_node_under_different_rule_is_not_a_fallback() {
    let config = Config::parse(
        br#"{
            "schema":1,"listen":"127.0.0.1:0","selected":"direct",
            "nodes":[{"id":"direct","outbound":{"type":"direct"}}],
            "rules":[
                {"matcher":{"type":"cidr","value":"192.0.2.0/24","resolve":true},"outbound":"direct"},
                {"matcher":{"type":"match"},"outbound":"direct"}
            ]
        }"#,
    )
    .unwrap();
    let target = Target {
        host: "rule.example".into(),
        port: 443,
    };
    let first: SocketAddr = "192.0.2.1:443".parse().unwrap();
    let different_rule: SocketAddr = "198.51.100.1:443".parse().unwrap();
    let same_rule: SocketAddr = "192.0.2.2:443".parse().unwrap();
    let choose = |_: &str| -> Result<String> { Err("UnexpectedPolicy") };
    let (node, routed, rule, candidates) = route_resolved(
        &config,
        &target,
        IpAddr::V4(std::net::Ipv4Addr::LOCALHOST),
        &[first, different_rule, same_rule],
        (&choose, &choose),
        None,
        true,
    )
    .unwrap();
    assert_eq!(node.id, "direct");
    assert_eq!(
        swirl_routing::rule_label(&config, rule),
        "#1 IP-CIDR,192.0.2.0/24 => direct"
    );
    assert_eq!(routed.host, first.ip().to_string());
    assert_eq!(candidates, vec![first, same_rule]);
}

#[test]
fn rejected_first_answer_never_falls_back_to_direct() {
    let config = Config::parse(
        br#"{
            "schema":1,"listen":"127.0.0.1:0","selected":"direct",
            "nodes":[
                {"id":"direct","outbound":{"type":"direct"}},
                {"id":"reject","outbound":{"type":"reject"}}
            ],
            "rules":[
                {"matcher":{"type":"cidr","value":"192.0.2.0/24","resolve":true},"outbound":"reject"},
                {"matcher":{"type":"match"},"outbound":"direct"}
            ]
        }"#,
    )
    .unwrap();
    let target = Target {
        host: "blocked.example".into(),
        port: 443,
    };
    let first: SocketAddr = "192.0.2.1:443".parse().unwrap();
    let later: SocketAddr = "127.0.0.1:443".parse().unwrap();
    let choose = |_: &str| -> Result<String> { Err("UnexpectedPolicy") };
    let (node, routed, rule, candidates) = route_resolved(
        &config,
        &target,
        IpAddr::V4(std::net::Ipv4Addr::LOCALHOST),
        &[first, later],
        (&choose, &choose),
        None,
        true,
    )
    .unwrap();
    assert_eq!(node.id, "reject");
    assert_eq!(
        swirl_routing::rule_label(&config, rule),
        "#1 IP-CIDR,192.0.2.0/24 => reject"
    );
    assert_eq!(routed.host, first.ip().to_string());
    assert!(candidates.is_empty());
}
