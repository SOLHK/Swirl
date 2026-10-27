use super::*;

fn raw(kind: &str) -> Value {
    let mut value = json!({"name":"fixture", "type":kind,"server":"proxy.invalid","port":443});
    match kind {
        "ss" => {
            value["password"] = json!("synthetic-pass");
            value["cipher"] = json!("aes-128-gcm");
        }
        "trojan" => value["password"] = json!("synthetic-pass"),
        "vless" | "vmess" => value["uuid"] = json!("00112233-4455-6677-8899-aabbccddeeff"),
        _ => {}
    }
    value
}

fn project(node: &Value) -> Inspection {
    inspect(&serde_json::to_vec(&json!({"proxies":[node]})).unwrap())
}

#[test]
fn optional_tfo_uses_identical_tcp_outbound_and_retains_source() {
    for kind in [
        "ss", "trojan", "vless", "vmess", "http", "socks5", "socks4", "socks4a",
    ] {
        let mut node = raw(kind);
        let baseline = project(&node);
        assert!(baseline.tcp_candidates[0].is_some(), "{kind}");
        for enabled in [false, true] {
            node["tfo"] = json!(enabled);
            let result = project(&node);
            assert_eq!(
                serde_json::to_value(&result.tcp_candidates[0]).unwrap(),
                serde_json::to_value(&baseline.tcp_candidates[0]).unwrap(),
                "{kind} tfo={enabled} must change no authentication, TLS, UDP or transport setting"
            );
            assert_eq!(result.originals[0]["tfo"], enabled);
            assert!(!result.report.nodes[0].real_network_verified);
            assert_eq!(
                result.report.nodes[0].diagnostic,
                if enabled {
                    "TcpFastOpenFallbackToTcp"
                } else {
                    "TcpCandidateNotYetVerified"
                }
            );
        }
    }
}

#[test]
fn fallback_preserves_websocket_and_does_not_override_security_or_unknown_fields() {
    let mut node = raw("trojan");
    node["network"] = json!("ws");
    node["ws-opts"] = json!({"path":"/fixture","headers":{"Host":"ws.invalid"}});
    let baseline = project(&node);
    node["tfo"] = json!(true);
    let fallback = project(&node);
    assert_eq!(
        serde_json::to_value(&fallback.tcp_candidates[0]).unwrap(),
        serde_json::to_value(&baseline.tcp_candidates[0]).unwrap()
    );
    assert!(fallback.tcp_candidates[0].is_some());
    for (key, value) in [
        ("skip-cert-verify", json!(true)),
        ("future-field", json!(1)),
    ] {
        let mut rejected = node.clone();
        rejected[key] = value;
        let result = project(&rejected);
        assert!(result.tcp_candidates[0].is_none());
        assert_ne!(
            result.report.nodes[0].diagnostic,
            "TcpFastOpenFallbackToTcp"
        );
    }
    for invalid in [
        Value::Null,
        json!(0),
        json!(1),
        json!("true"),
        json!([]),
        json!({}),
    ] {
        node["tfo"] = invalid;
        assert!(project(&node).tcp_candidates[0].is_none());
    }
}

#[test]
fn surge_surfboard_loon_and_clash_tfo_produce_the_same_shadowsocks_outbound() {
    let sources = [
        "[Proxy]\nfixture = ss,proxy.invalid,443,encrypt-method=aes-128-gcm,password=synthetic-pass,tfo=true",
        "[Proxy]\nfixture = Shadowsocks,proxy.invalid,443,aes-128-gcm,synthetic-pass,fast-open=true",
        "proxies: [{name: fixture, type: ss, server: proxy.invalid, port: 443, cipher: aes-128-gcm, password: synthetic-pass, tfo: true}]",
    ];
    let baseline = serde_json::to_value(&project(&raw("ss")).tcp_candidates[0]).unwrap();
    for source in sources {
        let result = inspect(source.as_bytes());
        assert_eq!(result.report.error, None);
        assert_eq!(
            result.report.nodes[0].diagnostic,
            "TcpFastOpenFallbackToTcp"
        );
        assert_eq!(
            serde_json::to_value(&result.tcp_candidates[0]).unwrap(),
            baseline
        );
        assert_eq!(result.original, source.as_bytes());
    }
}
