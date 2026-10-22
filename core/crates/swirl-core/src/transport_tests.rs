use super::*;
use swirl_protocol::{UrlTestFailure, UrlTestMetrics};

fn configuration() -> Config {
    Config::parse(
        br#"{"schema":1,"listen":"127.0.0.1:0","selected":"a","nodes":[
            {"id":"a","outbound":{"type":"vless","host":"127.0.0.1","port":9,"uuid":"00112233-4455-6677-8899-aabbccddeeff"}},
            {"id":"b","outbound":{"type":"direct"}}
        ],"selectors":[{"id":"manual","members":["a","b"],"selected":"a"}]}"#,
    )
    .unwrap()
}

fn websocket(path: &str) -> Transport {
    Transport::WebSocket {
        settings: swirl_subscription::WebSocket {
            host: "transport.fixture.invalid".into(),
            path: path.into(),
        },
        headers: vec![("X-Transport-Test".into(), "runtime".into())],
    }
}

fn transports() -> BTreeMap<String, Transport> {
    BTreeMap::from([("a".into(), websocket("/original"))])
}

fn path(map: &BTreeMap<String, Transport>) -> &str {
    match &map["a"] {
        Transport::WebSocket { settings, .. } => &settings.path,
        _ => panic!("expected explicit WebSocket transport"),
    }
}

#[test]
fn invalid_transport_configuration_is_rejected_before_listener_start() {
    let occupied = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let mut config = configuration();
    config.listen = occupied.local_addr().unwrap();
    for (selected, expected) in [
        (
            BTreeMap::from([("missing".into(), websocket("/"))]),
            "TransportNodeMissing",
        ),
        (
            BTreeMap::from([("manual".into(), websocket("/"))]),
            "TransportNodeMissing",
        ),
        (
            BTreeMap::from([("b".into(), websocket("/"))]),
            "TransportProtocolUnsupported",
        ),
    ] {
        assert_eq!(
            Core::start_with_transports(config.clone(), selected).err(),
            Some(expected)
        );
    }
    for path in ["/ws?ed=256", "/ws?token=fixture&%65%64=1"] {
        assert_eq!(
            Core::start_with_transports(
                config.clone(),
                BTreeMap::from([("a".into(), websocket(path))]),
            )
            .err(),
            Some("WebSocketEarlyDataUnsupported")
        );
    }
    let Outbound::Vless {
        websocket: legacy, ..
    } = &mut config.nodes[0].outbound
    else {
        unreachable!()
    };
    *legacy = Some(swirl_subscription::WebSocket {
        host: "legacy.fixture.invalid".into(),
        path: "/legacy".into(),
    });
    assert_eq!(
        Core::start_with_transports(config, transports()).err(),
        Some("TransportConflict")
    );
}

#[test]
fn selecting_and_legacy_configuring_preserve_the_explicit_transport() {
    let config = configuration();
    let mut core = Core::start_with_transports(config.clone(), transports()).unwrap();
    let map = core.plan.read().unwrap().transports.clone();
    core.select_node("b").unwrap();
    core.select_group("manual", "b").unwrap();
    core.configure(config).unwrap();
    let plan = core.plan.read().unwrap().clone();
    assert!(Arc::ptr_eq(&map, &plan.transports));
    assert_eq!(path(&plan.transports), "/original");
    assert_eq!(plan.config.selected, "a");
    core.stop();
}

#[test]
fn rejected_reconfiguration_preserves_generation_probes_and_transport() {
    let config = configuration();
    let mut core = Core::start_with_transports(config.clone(), transports()).unwrap();
    let original = core.plan.read().unwrap().clone();
    let generation = core.snapshot().unwrap().generation;
    let probe = core
        .probe
        .start_with(std::future::pending::<
            std::result::Result<UrlTestMetrics, UrlTestFailure>,
        >())
        .unwrap();

    let mut removed = config.clone();
    removed.selected = "b".into();
    removed.nodes.remove(0);
    removed.selectors.clear();
    assert_eq!(core.configure(removed), Err("TransportNodeMissing"));
    let mut incompatible = config.clone();
    incompatible.nodes[0].outbound = Outbound::Direct {};
    assert_eq!(
        core.configure(incompatible),
        Err("TransportProtocolUnsupported")
    );
    assert_eq!(
        core.configure_with_transports(
            config,
            BTreeMap::from([("absent".into(), websocket("/"))]),
        ),
        Err("TransportNodeMissing")
    );
    assert!(Arc::ptr_eq(&original, &core.plan.read().unwrap()));
    assert_eq!(core.snapshot().unwrap().generation, generation);
    assert_eq!(core.probe_status().unwrap(), probe);
    core.stop();
}

#[test]
fn explicit_replacement_keeps_accepted_session_transport_immutable() {
    let config = configuration();
    let mut core = Core::start_with_transports(config.clone(), transports()).unwrap();
    let old = core.plan.read().unwrap().session().unwrap();
    core.configure_with_transports(
        config.clone(),
        BTreeMap::from([("a".into(), websocket("/replacement"))]),
    )
    .unwrap();
    let current = core.plan.read().unwrap().session().unwrap();
    assert_eq!(path(&old.transports), "/original");
    assert_eq!(path(&current.transports), "/replacement");
    assert!(!Arc::ptr_eq(&old.transports, &current.transports));
    core.configure_with_transports(config, BTreeMap::new())
        .unwrap();
    assert!(core.plan.read().unwrap().transports.is_empty());
    assert_eq!(path(&old.transports), "/original");
    assert_eq!(path(&current.transports), "/replacement");
    core.stop();
}
