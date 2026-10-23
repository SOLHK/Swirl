use super::*;
use serde_json::json;

fn source(kind: &str) -> Value {
    let mut raw = json!({"type":kind,"tag":"synthetic","server":"localhost","server_port":443,"password":"synthetic:password","tls":{"enabled":true,"server_name":"origin.test","alpn":["h3"]}});
    if kind == "tuic" {
        raw["uuid"] = json!("00112233-4455-6677-8899-aabbccddeeff");
    }
    raw
}
fn projected(raw: &Value) -> Value {
    serde_json::to_value(outbound(raw).unwrap()).unwrap()
}

#[test]
fn singbox_tuic_options_preserve_units_network_and_credentials() {
    let mut raw = source("tuic");
    raw["heartbeat"] = json!("1s250ms");
    raw["network"] = json!("tcp");
    raw["congestion_control"] = json!("new_reno");
    raw["udp_relay_mode"] = json!("quic");
    raw["zero_rtt_handshake"] = json!(false);
    raw["udp_over_stream"] = json!(false);
    assert_eq!(
        projected(&raw),
        json!({"type":"tuic","host":"localhost","port":443,"uuid":"00112233-4455-6677-8899-aabbccddeeff","password":"synthetic:password","tls":{"server_name":"origin.test","alpn":["h3"],"ca_der_base64":null},"insecure":false,"pin_sha256":null,"udp":false,"udp_relay_mode":"quic","congestion_control":"new_reno","heartbeat_interval_ms":1250,"request_timeout_ms":10000})
    );
}
#[test]
fn singbox_hy2_obfs_bandwidth_and_inline_trust_are_preserved() {
    let mut raw = source("hysteria2");
    raw["up_mbps"] = json!(3);
    raw["down_mbps"] = json!(5);
    raw["obfs"] = json!({"type":"salamander","password":"synthetic-obfs"});
    raw["tls"]["certificate"] = json!([
        "-----BEGIN CERTIFICATE-----",
        "AQID",
        "-----END CERTIFICATE-----"
    ]);
    assert_eq!(
        projected(&raw),
        json!({"type":"hysteria2","host":"localhost","port":443,"password":"synthetic:password","tls":{"server_name":"origin.test","alpn":["h3"],"ca_der_base64":"AQID"},"insecure":false,"pin_sha256":null,"obfs":"salamander","obfs_password":"synthetic-obfs","ports":null,"up_mbps":3,"down_mbps":5,"ech":null,"udp":true})
    );
}
#[test]
fn singbox_qt_projection_and_direct_inspection_have_identical_native_semantics() {
    for kind in ["tuic", "hysteria2"] {
        let raw = source(kind);
        let expected = projected(&raw);
        let mut normalized = raw.as_object().unwrap().clone();
        let name = normalized.remove("tag").unwrap();
        let port = normalized.remove("server_port").unwrap();
        normalized.insert("name".into(), name);
        normalized.insert("port".into(), port);
        normalized.insert("_swirl-source-format".into(), json!("sing-box"));
        for document in [json!({"outbounds":[raw]}), json!({"proxies":[normalized]})] {
            let inspected = crate::inspect::inspect(&serde_json::to_vec(&document).unwrap());
            assert!(inspected.report.parsed);
            assert_eq!(
                inspected.originals[0],
                document.as_object().unwrap().values().next().unwrap()[0]
            );
            assert_eq!(
                serde_json::to_value(inspected.tcp_candidates[0].as_ref().unwrap()).unwrap(),
                expected
            );
            assert!(!inspected.report.nodes[0].real_network_verified);
            assert_eq!(inspected.report.nodes[0].transport, "quic");
            assert!(inspected.report.nodes[0].udp_declared);
            assert_eq!(inspected.report.nodes[0].unrecognized_fields, 0);
        }
    }
}
#[test]
fn singbox_quic_unknown_or_security_requirements_never_become_executable() {
    for kind in ["tuic", "hysteria2"] {
        for (key, value) in [
            ("detour", json!("other")),
            ("unknown", json!("synthetic-secret")),
            ("server_port", json!("443")),
            ("network", json!("udp")),
            ("network", json!(["udp"])),
            ("network", json!(false)),
            ("tls", json!({"enabled":false})),
            ("tls", json!({"enabled":true,"insecure":"false"})),
            ("tls", json!({"enabled":true,"disable_sni":true})),
            (
                "tls",
                json!({"enabled":true,"certificate_path":"secret.pem"}),
            ),
            ("tls", json!({"enabled":true,"alpn":[1]})),
            ("tls", json!({"enabled":true,"reality":{"enabled":true}})),
        ] {
            let mut raw = source(kind);
            raw[key] = value;
            let document = json!({"outbounds":[raw]});
            let inspected = crate::inspect::inspect(&serde_json::to_vec(&document).unwrap());
            assert!(inspected.report.parsed);
            assert!(inspected.tcp_candidates[0].is_none(), "{kind}/{key}");
            assert_eq!(inspected.originals[0], document["outbounds"][0]);
        }
    }
}
#[test]
fn singbox_tuic_unsupported_modes_and_malformed_durations_are_rejected() {
    for (key, value) in [
        ("zero_rtt_handshake", json!(true)),
        ("zero_rtt_handshake", json!("false")),
        ("udp_over_stream", json!(true)),
        ("heartbeat", json!("500us")),
        ("heartbeat", json!(1000)),
        ("heartbeat", json!("31s")),
        ("heartbeat", json!("-1s")),
        ("heartbeat", json!("1.2.3s")),
        (
            "heartbeat",
            json!("99999999999999999999999999999999999999999h"),
        ),
        ("congestion_control", json!("unknown")),
        ("udp_relay_mode", json!("unknown")),
        ("token", json!("v4")),
        ("tls", json!({"enabled":true})),
    ] {
        let mut raw = source("tuic");
        raw[key] = value;
        assert!(outbound(&raw).is_err(), "{key}");
    }
    for (text, millis) in [
        ("1.5s", 1500),
        ("0.1s", 100),
        ("0", 0),
        ("1s250ms", 1250),
        ("+1s", 1000),
        ("1000000ns", 1),
    ] {
        assert_eq!(duration_ms(text), Ok(millis));
    }
    for text in [
        "",
        "+",
        "1",
        ".s",
        "1.1.1s",
        "-0s",
        "0.1ns",
        "999999999999999999999999999999999999999999h",
    ] {
        assert!(duration_ms(text).is_err(), "{text}");
    }
}
#[test]
fn singbox_hy2_extensions_and_overflow_remain_rejected() {
    for (key, value) in [
        ("server_ports", json!(["443:8443"])),
        ("hop_interval", json!("30s")),
        ("up_mbps", json!(u64::MAX)),
        ("down_mbps", json!(1.5)),
        ("obfs", json!({"type":"gecko","password":"synthetic"})),
        (
            "obfs",
            json!({"type":"salamander","password":"synthetic","future":true}),
        ),
        ("obfs", json!("salamander")),
    ] {
        let mut raw = source("hysteria2");
        raw[key] = value;
        assert!(outbound(&raw).is_err(), "{key}");
    }
    for pem in [
        "/private/ca.pem",
        "-----BEGIN CERTIFICATE-----\nAQID\n-----END CERTIFICATE-----\n-----BEGIN CERTIFICATE-----\nAQID\n-----END CERTIFICATE-----",
    ] {
        let mut raw = source("hysteria2");
        raw["tls"]["certificate"] = json!(pem);
        assert!(outbound(&raw).is_err());
    }
}
