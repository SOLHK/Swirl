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
        let (node, routed, matched) =
            route_resolved(&config, &target, source, &answers, &choose, china).unwrap();
        assert_eq!(node.id, expected_node);
        assert_eq!(swirl_routing::rule_label(&config, matched), expected_rule);
        assert_eq!(routed.host, answers[0].ip().to_string());
        assert_eq!(routed.port, target.port);
        // Outbound resolution receives a literal IP, so no second destination
        // hostname lookup can select a different answer after route matching.
        assert_eq!(
            resolver.resolve(&routed.host, routed.port).await.unwrap(),
            vec![answers[0]]
        );
    }
}
