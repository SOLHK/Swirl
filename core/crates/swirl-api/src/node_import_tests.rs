use super::*;
use crate::import_ffi::INVALID_BUFFER;
use serde_json::Value;

const ID: &str = "00112233-4455-6677-8899-aabbccddeeff";

fn node(kind: &str) -> Value {
    json!({"name":"合成节点 🌀", "type":kind,"server":"proxy.invalid","port":443})
}

fn call(input: &[u8]) -> (Value, Vec<u8>) {
    // SAFETY: the size query borrows initialized immutable input only.
    let required =
        unsafe { swirl_import_node_v1(input.as_ptr(), input.len(), std::ptr::null_mut(), 0) };
    assert!(required > 0);
    let mut output = vec![0xa5; required as usize + 8];
    // SAFETY: independent input and output buffers; output includes a canary.
    let written = unsafe {
        swirl_import_node_v1(
            input.as_ptr(),
            input.len(),
            output.as_mut_ptr(),
            required as usize,
        )
    };
    assert_eq!(written, required);
    assert_eq!(&output[required as usize..], &[0xa5; 8]);
    output.truncate(required as usize);
    (serde_json::from_slice(&output).unwrap(), output)
}

fn import(node: Value) -> Value {
    call(&serde_json::to_vec(&json!({"proxies":[node]})).unwrap()).0
}

fn native(node: Value) -> Value {
    let result = import(node);
    assert_eq!(result["ok"], true, "{}", result["error"]);
    assert_eq!(result["network_verified"], false);
    result["native_outbound"].clone()
}

fn configuration(outbound: Value) -> Config {
    Config::parse(
        &serde_json::to_vec(&json!({"schema":1,"listen":"127.0.0.1:0",
        "selected":"imported","nodes":[{"id":"imported","outbound":outbound}]}))
        .unwrap(),
    )
    .unwrap()
}

#[test]
fn product_optional_shape_and_empty_tls_name_aliases_remain_compatible() {
    let outbound = native(node("socks5"));
    assert_eq!(
        outbound,
        json!({"type":"socks5","host":"proxy.invalid","port":443,"udp":false})
    );
    let mut http = node("http");
    http["tls"] = json!(true);
    http["sni"] = json!("");
    http["servername"] = json!("");
    let outbound = native(http);
    assert!(outbound.get("auth").is_none());
    assert_eq!(
        outbound["tls"],
        json!({"server_name":"proxy.invalid","alpn":[]})
    );
    configuration(outbound);
    let mut vless = node("vless");
    vless["uuid"] = json!(ID);
    let outbound = native(vless);
    assert!(outbound.get("tls").is_none() && outbound.get("websocket").is_none());
    configuration(outbound);
}

#[test]
fn previous_http_and_socks_protocols_preserve_authentication_dns_and_udp() {
    for (kind, native_kind) in [
        ("http", "http_connect"),
        ("socks5", "socks5"),
        ("socks4", "socks4"),
        ("socks4a", "socks4"),
    ] {
        let mut raw = node(kind);
        raw["username"] = json!("synthetic-user");
        if !kind.starts_with("socks4") {
            raw["password"] = json!("synthetic-password");
        }
        if kind == "socks5" {
            raw["udp"] = json!(true);
        }
        let outbound = native(raw);
        assert_eq!(outbound["type"], native_kind);
        if kind.starts_with("socks4") {
            assert_eq!(outbound["remote_dns"], kind == "socks4a");
            assert_eq!(outbound["user_id"], "synthetic-user");
        } else {
            assert_eq!(outbound["auth"]["username"], "synthetic-user");
            assert!(outbound["auth"]["password"] == "synthetic-password");
        }
        if kind == "socks5" {
            assert_eq!(outbound["udp"], true);
        }
        configuration(outbound);
    }
}

#[test]
fn vless_and_trojan_preserve_udp_and_tls_instead_of_using_old_cpp_whitelist() {
    for kind in ["vless", "trojan"] {
        let mut raw = node(kind);
        if kind == "vless" {
            raw["uuid"] = json!(ID);
        } else {
            raw["password"] = json!("synthetic-pass");
        }
        raw["tls"] = json!(true);
        raw["sni"] = json!("tls.invalid");
        raw["alpn"] = json!(["h2", "http/1.1"]);
        raw["udp"] = json!(true);
        let outbound = native(raw);
        assert_eq!(outbound["udp"], true);
        assert_eq!(outbound["tls"]["server_name"], "tls.invalid");
        assert_eq!(outbound["tls"]["alpn"], json!(["h2", "http/1.1"]));
        configuration(outbound);
    }
}

#[test]
fn shadowsocks_aead_and_2022_key_are_not_downgraded() {
    for (cipher, password) in [
        ("aes-128-gcm", "synthetic-pass"),
        ("2022-blake3-aes-128-gcm", "AAAAAAAAAAAAAAAAAAAAAA=="),
    ] {
        let mut raw = node("ss");
        raw["cipher"] = json!(cipher);
        raw["password"] = json!(password);
        raw["udp"] = json!(true);
        let outbound = native(raw);
        assert_eq!(outbound["type"], "shadowsocks");
        assert_eq!(outbound["cipher"], cipher);
        assert!(outbound["password"] == password);
        assert_eq!(outbound["udp"], true);
        configuration(outbound);
    }
}

#[test]
fn vmess_websocket_tls_and_security_reach_existing_native_schema() {
    let mut raw = node("vmess");
    raw["uuid"] = json!(ID);
    raw["alterId"] = json!(0);
    raw["cipher"] = json!("chacha20-poly1305");
    raw["tls"] = json!(true);
    raw["servername"] = json!("tls.invalid");
    raw["alpn"] = json!(["http/1.1"]);
    raw["network"] = json!("ws");
    raw["ws-opts"] = json!({"path":"/fixture","headers":{"Host":"ws.invalid"}});
    let outbound = native(raw);
    assert_eq!(outbound["type"], "vmess");
    assert_eq!(outbound["uuid"], ID);
    assert_eq!(outbound["security"], "chacha20-poly1305");
    assert_eq!(
        outbound["websocket"],
        json!({"host":"ws.invalid","path":"/fixture"})
    );
    assert_eq!(outbound["tls"]["server_name"], "tls.invalid");
    let config = configuration(outbound);
    let mut core = swirl_core::Core::start(config).expect("native VMess listener startup");
    core.stop();
    core.stop();
}

#[test]
fn quic_protocols_preserve_authentication_bandwidth_obfs_and_udp_controls() {
    let mut hy = node("hysteria2");
    hy["password"] = json!("synthetic-user:synthetic-password");
    hy["sni"] = json!("quic.invalid");
    hy["obfs"] = json!("salamander");
    hy["obfs-password"] = json!("synthetic-obfs");
    hy["up"] = json!("20 Mbps");
    hy["down"] = json!(100);
    hy["udp"] = json!(false);
    hy["fingerprint"] = json!("ab".repeat(32));
    let outbound = native(hy);
    assert_eq!(outbound["type"], "hysteria2");
    assert_eq!(outbound["up_mbps"], 20);
    assert_eq!(outbound["down_mbps"], 100);
    assert_eq!(outbound["udp"], false);
    assert_eq!(outbound["pin_sha256"], "ab".repeat(32));
    assert!(outbound["obfs_password"] == "synthetic-obfs");
    let mut core =
        swirl_core::Core::start(configuration(outbound)).expect("native HY2 listener startup");
    core.stop();

    let mut tuic = node("tuic");
    tuic["uuid"] = json!(ID);
    tuic["password"] = json!("synthetic-password");
    tuic["sni"] = json!("quic.invalid");
    tuic["alpn"] = json!(["h3"]);
    tuic["udp-relay-mode"] = json!("quic");
    tuic["congestion-controller"] = json!("bbr");
    let outbound = native(tuic);
    assert_eq!(outbound["type"], "tuic");
    assert_eq!(outbound["uuid"], ID);
    assert_eq!(outbound["udp_relay_mode"], "quic");
    assert_eq!(outbound["congestion_control"], "bbr");
    assert_eq!(outbound["udp"], true);
    let mut core =
        swirl_core::Core::start(configuration(outbound)).expect("native TUIC listener startup");
    core.stop();
}

fn stream_node(network: &str, key: &str, settings: Value) -> Value {
    let mut raw = node("vless");
    raw["uuid"] = json!(ID);
    raw["tls"] = json!(true);
    raw["sni"] = json!("tls.invalid");
    raw["network"] = json!(network);
    raw[key] = settings;
    raw
}

#[test]
fn clash_stream_transports_reuse_native_xray_ir_and_runtime_validation() {
    let cases = [
        (
            "grpc",
            "grpc-opts",
            json!({"grpc-service-name":"fixture","grpc-user-agent":"synthetic-agent","ping-interval":0}),
            "grpc",
        ),
        (
            "h2",
            "h2-opts",
            json!({"host":["front.invalid"],"path":"/fixture"}),
            "http2",
        ),
        (
            "ws",
            "ws-opts",
            json!({"path":"/fixture","headers":{"Host":"front.invalid","X-Fixture":"yes"},"v2ray-http-upgrade":true}),
            "httpupgrade",
        ),
        (
            "xhttp",
            "xhttp-opts",
            json!({"host":"front.invalid","path":"/fixture","mode":"stream-one"}),
            "xhttp",
        ),
    ];
    for (network, key, settings, kind) in cases {
        let mut raw = stream_node(network, key, settings);
        raw["udp"] = json!(true);
        let outbound = native(raw);
        assert_eq!(outbound["transport"]["type"], kind);
        assert_eq!(outbound["udp"], true);
        if network == "grpc" {
            assert_eq!(outbound["transport"]["config"]["service_name"], "fixture");
            assert_eq!(
                outbound["transport"]["config"]["headers"],
                json!([["user-agent", "synthetic-agent"]])
            );
        } else {
            assert_eq!(outbound["transport"]["config"]["path"], "/fixture");
            assert_eq!(outbound["transport"]["config"]["host"], "front.invalid");
        }
        let mut core = swirl_core::Core::start(configuration(outbound))
            .expect("native transport listener startup");
        core.stop();
    }
}

#[test]
fn stream_controls_without_equivalent_semantics_are_never_dropped() {
    let cases = [
        stream_node(
            "h2",
            "h2-opts",
            json!({"host":["one.invalid","two.invalid"]}),
        ),
        stream_node("h2", "h2-opts", json!({})),
        stream_node(
            "grpc",
            "grpc-opts",
            json!({"grpc-service-name":"fixture","max-connections":2}),
        ),
        stream_node("grpc", "grpc-opts", json!({"ping-interval":5})),
        stream_node("xhttp", "xhttp-opts", json!({"mode":"auto"})),
        stream_node(
            "xhttp",
            "xhttp-opts",
            json!({"mode":"stream-one","extra":{"scMaxEachPostBytes":1000}}),
        ),
        stream_node(
            "ws",
            "ws-opts",
            json!({"v2ray-http-upgrade":true,"v2ray-http-upgrade-fast-open":true}),
        ),
        stream_node(
            "ws",
            "ws-opts",
            json!({"v2ray-http-upgrade":true,"headers":{"Host":"one.invalid","host":"two.invalid"}}),
        ),
    ];
    for raw in cases {
        let response = import(raw);
        assert_eq!(response["ok"], false);
        assert!(response.get("native_outbound").is_none());
    }
    let mut conflict = stream_node("grpc", "grpc-opts", json!({"grpc-service-name":"fixture"}));
    conflict["ws-opts"] = json!({"path":"/hidden"});
    assert_eq!(import(conflict)["ok"], false);
}

#[test]
fn security_aliases_unknown_fields_and_malformed_authentication_fail_closed() {
    for (kind, key, value) in [
        ("vmess", "alterId", json!(true)),
        ("vmess", "udp", json!(true)),
        ("hysteria2", "insecure", json!(true)),
        ("tuic", "insecure", json!(true)),
        ("hysteria2", "future-option", json!("PRIVATE_TOKEN")),
        ("tuic", "reduce-rtt", json!(true)),
    ] {
        let mut raw = node(kind);
        if kind == "vmess" || kind == "tuic" {
            raw["uuid"] = json!(ID);
        }
        if kind != "vmess" {
            raw["password"] = json!("PRIVATE_PASSWORD");
        }
        if kind == "tuic" {
            raw["alpn"] = json!(["h3"]);
        }
        raw[key] = value;
        let (response, bytes) = call(&serde_json::to_vec(&json!({"proxies":[raw]})).unwrap());
        assert_eq!(response["ok"], false);
        let text = String::from_utf8(bytes).unwrap();
        assert!(!text.contains("PRIVATE_TOKEN") && !text.contains("PRIVATE_PASSWORD"));
    }
}

#[test]
fn single_node_boundary_rejects_global_policy_documents_multiple_nodes_and_duplicates() {
    let cases = [
        json!({"proxies":[node("http")],"rules":["MATCH,DIRECT"]}),
        json!({"proxies":[node("http"),node("http")]}),
        json!({"proxies":[]}),
        node("http"),
    ];
    for input in cases {
        assert_eq!(call(&serde_json::to_vec(&input).unwrap()).0["ok"], false);
    }
    for input in [
        b"{\"proxies\":[],\"proxies\":[]}".as_slice(),
        b"proxies:\n- {type: http, server: one.invalid, server: two.invalid, port: 80}",
        &[0xff],
    ] {
        assert_eq!(call(input).0["ok"], false);
    }
}

#[test]
fn size_query_undersized_output_overlap_and_limits_preserve_buffer_contract() {
    let input = serde_json::to_vec(&json!({"proxies":[node("http")]})).unwrap();
    let (_, full) = call(&input);
    let mut short = vec![0xa5; full.len() - 1];
    // SAFETY: independent valid buffers; insufficient capacity must not write.
    let count = unsafe {
        swirl_import_node_v1(input.as_ptr(), input.len(), short.as_mut_ptr(), short.len())
    };
    assert_eq!(count as usize, full.len());
    assert!(short.iter().all(|b| *b == 0xa5));
    let mut overlap = input.clone();
    // SAFETY: each invalid pointer or size is rejected before pointer access.
    unsafe {
        assert_eq!(
            swirl_import_node_v1(std::ptr::null(), 1, std::ptr::null_mut(), 0),
            INVALID_BUFFER
        );
        assert_eq!(
            swirl_import_node_v1(input.as_ptr(), MAX_INPUT + 1, std::ptr::null_mut(), 0),
            INVALID_BUFFER
        );
        assert_eq!(
            swirl_import_node_v1(input.as_ptr(), input.len(), std::ptr::null_mut(), 1),
            INVALID_BUFFER
        );
        assert_eq!(
            swirl_import_node_v1(
                overlap.as_ptr(),
                overlap.len(),
                overlap.as_mut_ptr(),
                overlap.len()
            ),
            INVALID_BUFFER
        );
        assert_eq!(
            swirl_import_node_v1(usize::MAX as *const u8, 1, std::ptr::null_mut(), 0),
            INVALID_BUFFER
        );
    }
    assert!(overlap == input);
}

#[test]
fn independent_concurrent_calls_have_no_runtime_or_credential_state() {
    let jobs: Vec<_> = (0..8)
        .map(|index| {
            std::thread::spawn(move || {
                let mut raw = node("http");
                raw["username"] = json!(format!("fixture-{index}"));
                raw["password"] = json!("synthetic-password");
                let outbound = native(raw);
                assert_eq!(outbound["auth"]["username"], format!("fixture-{index}"));
            })
        })
        .collect();
    for job in jobs {
        job.join().unwrap();
    }
}
