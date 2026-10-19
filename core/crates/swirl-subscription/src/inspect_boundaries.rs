//! Regressions for raw subscription -> typed outbound -> serialized Config.
//! These test the Rust boundary; Qt persistence and real peers run separately.
use super::{Inspection, inspect};
use crate::Config;
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};

fn node(kind: &str) -> Value {
    let mut node = json!({"type": kind, "server": "proxy.fixture.invalid", "port": 443});
    match kind {
        "vless" => node["uuid"] = json!("00112233-4455-6677-8899-aabbccddeeff"),
        "ss" => {
            node["cipher"] = json!("aes-128-gcm");
            node["password"] = json!("synthetic");
        }
        _ => node["password"] = json!("synthetic"),
    }
    if matches!(kind, "http" | "https" | "socks5" | "socks5-tls") {
        node["username"] = json!("synthetic-user");
    }
    node
}

fn documents(node: &Value) -> Vec<Vec<u8>> {
    ["proxies", "outbounds"]
        .into_iter()
        .flat_map(|key| {
            let document = json!({key: [node]}).to_string();
            [
                document.as_bytes().to_vec(),
                STANDARD.encode(&document).into_bytes(),
            ]
        })
        .collect()
}

fn restored_outbound(result: &Inspection) -> Value {
    assert!(
        result.report.nodes[0].native_tcp_candidate,
        "{}",
        result.report.nodes[0].diagnostic
    );
    let outbound = result.tcp_candidates[0].as_ref().unwrap();
    let config: Config = serde_json::from_value(json!({
        "schema": 1, "listen": "127.0.0.1:0", "selected": "subscription-node",
        "nodes": [{"id": "subscription-node", "outbound": outbound}],
    }))
    .unwrap();
    config.validate().unwrap();
    let bytes = serde_json::to_vec(&config).unwrap();
    let restored: Config = serde_json::from_slice(&bytes).unwrap();
    restored.validate().unwrap();
    assert_eq!(restored.selected, "subscription-node");
    assert_eq!(
        serde_json::to_value(&restored).unwrap(),
        serde_json::to_value(&config).unwrap()
    );
    // The retained source is independent of normalized defaults in Config.
    let preserved: Value =
        serde_json::from_slice(&serde_json::to_vec(&result.originals).unwrap()).unwrap();
    assert_eq!(preserved[0], result.originals[0]);
    assert!(!result.report.nodes[0].real_network_verified);
    serde_json::to_value(&restored.nodes[0].outbound).unwrap()
}

#[test]
fn explicit_invalid_network_never_becomes_default_tcp() {
    for kind in ["http", "socks5", "trojan", "vless", "ss"] {
        let base = node(kind);
        for input in documents(&base) {
            restored_outbound(&inspect(&input));
        }
        for network in [
            json!(null),
            json!(false),
            json!(true),
            json!(0),
            json!([]),
            json!({}),
            json!(""),
            json!("future"),
        ] {
            let mut raw = base.clone();
            raw["network"] = network;
            for input in documents(&raw) {
                let result = inspect(&input);
                assert!(result.report.parsed);
                assert!(
                    !result.report.nodes[0].native_tcp_candidate,
                    "{kind}: {raw}"
                );
                assert_eq!(result.report.nodes[0].diagnostic, "TransportNotImplemented");
                assert_eq!(result.originals[0], raw);
                assert_eq!(result.original, input);
            }
        }
    }
}

#[test]
fn endpoint_aliases_validate_both_values_and_never_select_a_conflict() {
    for kind in ["http", "socks5", "trojan", "vless", "ss"] {
        let base = node(kind);
        for (port, server_port, expected) in [
            (json!(443), json!(8443), "ConflictingServerPort"),
            (json!(443), json!(null), "NodeParameters"),
            (json!(443), json!(false), "NodeParameters"),
            (json!(443), json!(65536), "NodeParameters"),
            (json!(null), json!(443), "NodeParameters"),
        ] {
            let mut raw = base.clone();
            raw["port"] = port;
            raw["server_port"] = server_port;
            for input in documents(&raw) {
                let result = inspect(&input);
                assert!(
                    !result.report.nodes[0].native_tcp_candidate,
                    "{kind}: {raw}"
                );
                assert_eq!(result.report.nodes[0].diagnostic, expected);
                assert_eq!(result.originals[0], raw);
                assert_eq!(result.original, input);
            }
        }
        let mut same = base;
        same["server_port"] = json!("443");
        for input in documents(&same) {
            let result = inspect(&input);
            assert_eq!(restored_outbound(&result)["port"], 443);
            assert_eq!(result.originals[0], same);
        }
    }
}

#[test]
fn alpn_aliases_cannot_hide_conflicts_invalid_types_or_order() {
    for kind in ["http", "socks5", "trojan", "vless"] {
        let mut base = node(kind);
        base["tls"] =
            json!({"enabled":true, "server_name":"tls.fixture.invalid", "alpn":["h2", "http/1.1"]});
        base["alpn"] = json!(["h2", "http/1.1"]);
        base["sni"] = json!("tls.fixture.invalid");
        for input in documents(&base) {
            let result = inspect(&input);
            let outbound = restored_outbound(&result);
            assert_eq!(outbound["tls"]["alpn"], json!(["h2", "http/1.1"]));
            assert_eq!(outbound["tls"]["server_name"], "tls.fixture.invalid");
            assert_eq!(result.originals[0], base);
        }
        for hidden in [
            json!(null),
            json!(false),
            json!("h2"),
            json!([1]),
            json!([]),
            json!(["http/1.1", "h2"]),
        ] {
            let mut raw = base.clone();
            raw["tls"]["alpn"] = hidden;
            for input in documents(&raw) {
                let result = inspect(&input);
                assert!(
                    !result.report.nodes[0].native_tcp_candidate,
                    "{kind}: {raw}"
                );
                assert_eq!(result.report.nodes[0].diagnostic, "ConflictingAlpn");
                assert_eq!(result.originals[0], raw);
            }
        }
    }
}

#[test]
fn document_protocols_with_implicit_tls_never_lose_or_override_it() {
    for kind in ["https", "socks5-tls", "trojan"] {
        let raw = node(kind);
        for input in documents(&raw) {
            let result = inspect(&input);
            let outbound = restored_outbound(&result);
            assert!(outbound["tls"].is_object(), "{kind}: {outbound}");
            assert_eq!(outbound["tls"]["server_name"], "proxy.fixture.invalid");
        }
        for extra in [
            json!({"tls":false}),
            json!({"tls":{"enabled":false}}),
            json!({"security":"none"}),
        ] {
            let mut bad = raw.clone();
            bad.as_object_mut()
                .unwrap()
                .extend(extra.as_object().unwrap().clone());
            for input in documents(&bad) {
                let result = inspect(&input);
                assert!(
                    !result.report.nodes[0].native_tcp_candidate,
                    "{kind}: {bad}"
                );
                assert_eq!(result.originals[0], bad);
            }
        }
    }
}

#[test]
fn uri_alpn_maps_ordered_values_and_round_trips_without_losing_raw_input() {
    for protocol in [
        "vless://00112233-4455-6677-8899-aabbccddeeff",
        "trojan://synthetic",
    ] {
        for (query, expected) in [
            ("h2", json!(["h2"])),
            ("h2%2Chttp%2F1.1", json!(["h2", "http/1.1"])),
        ] {
            let uri = format!(
                "{protocol}@proxy.fixture.invalid:443?security=tls&alpn={query}&sni=tls.fixture.invalid"
            );
            for input in [uri.as_bytes().to_vec(), STANDARD.encode(&uri).into_bytes()] {
                let result = inspect(&input);
                let outbound = restored_outbound(&result);
                assert_eq!(outbound["tls"]["alpn"], expected);
                assert_eq!(result.originals[0]["alpn"], expected);
                assert_eq!(result.originals[0]["raw-uri"], uri);
                assert_eq!(result.original, input);
            }
        }
        for alpn in ["", "%2Ch2", "h2%2C", "h2%2C%20http%2F1.1", "h2%00"] {
            let uri = format!("{protocol}@proxy.fixture.invalid:443?security=tls&alpn={alpn}");
            let result = inspect(uri.as_bytes());
            assert!(!result.report.parsed, "{uri}");
            assert_eq!(result.report.error, Some("InvalidUriAlpn"));
            assert_eq!(result.original, uri.as_bytes());
        }
    }
}

#[test]
fn trojan_username_is_not_silently_discarded_by_tcp_or_websocket_mapping() {
    for network in ["tcp", "ws"] {
        let mut base = node("trojan");
        base["network"] = json!(network);
        let expected = restored_outbound(&inspect(&documents(&base)[0]));
        for username in [None, Some(json!(""))] {
            let mut raw = base.clone();
            if let Some(value) = username {
                raw["username"] = value;
            }
            for input in documents(&raw) {
                let result = inspect(&input);
                assert_eq!(restored_outbound(&result), expected);
                assert_eq!(result.originals[0], raw);
            }
        }
        for username in [
            json!("unsupported-user"),
            json!(" "),
            json!(null),
            json!(false),
            json!(0),
            json!([]),
            json!({}),
        ] {
            let mut raw = base.clone();
            raw["username"] = username;
            for input in documents(&raw) {
                let result = inspect(&input);
                assert!(result.report.parsed);
                assert!(!result.report.nodes[0].native_tcp_candidate);
                assert!(result.tcp_candidates[0].is_none());
                assert_eq!(
                    result.report.nodes[0].diagnostic,
                    "TrojanUsernameUnsupported"
                );
                assert_eq!(result.originals[0], raw);
                assert_eq!(result.original, input);
            }
        }
    }
}
