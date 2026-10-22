use super::*;
use serde_json::{Value, json};

const ID: &str = "00112233-4455-6677-8899-aabbccddeeff";

fn vless() -> Value {
    json!({"protocol":"vless", "tag":"东京 · 节点 🌀",
        "settings":{"address":"proxy.invalid","port":443,"id":ID,"encryption":"none"}})
}

fn call(input: &[u8]) -> (Value, Vec<u8>) {
    // SAFETY: input remains immutable and the first call requests no output.
    let needed =
        unsafe { swirl_import_xray_v1(input.as_ptr(), input.len(), std::ptr::null_mut(), 0) };
    assert!(needed > 0);
    let mut output = vec![0xa5; needed as usize + 8];
    // SAFETY: independent initialized input and output buffers have exact lengths.
    let written = unsafe {
        swirl_import_xray_v1(
            input.as_ptr(),
            input.len(),
            output.as_mut_ptr(),
            needed as usize,
        )
    };
    assert_eq!(written, needed);
    assert_eq!(&output[needed as usize..], &[0xa5; 8]);
    output.truncate(needed as usize);
    (serde_json::from_slice(&output).unwrap(), output)
}

fn call_value(input: &Value) -> Value {
    call(&serde_json::to_vec(input).unwrap()).0
}

#[test]
fn abi_projection_preserves_unicode_authentication_and_separates_four_states() {
    let mut original = vless();
    original["settings"]["flow"] = json!("xtls-rprx-vision");
    original["streamSettings"] = json!({"network":"ws","security":"tls",
        "wsSettings":{"path":"/private-path","headers":{"Host":"web.invalid"}},
        "tlsSettings":{"serverName":"web.invalid","alpn":["http/1.1"]}});
    let response = call_value(&original);
    assert_eq!(response["schema"], 1);
    assert_eq!(response["ok"], true);
    assert_eq!(response["format"], "xray-v2ray-json");
    assert_eq!(response["outbounds"], json!([original]));
    let node = &response["nodes"][0];
    assert_eq!(node["index"], 0);
    assert_eq!(node["source"]["outbound_index"], 0);
    assert_eq!(node["name"], "东京 · 节点 🌀");
    assert_eq!(node["host"], "proxy.invalid");
    assert_eq!(node["port"], 443);
    assert_eq!(node["authentication"]["kind"], "vless");
    assert_eq!(node["authentication"]["id"], ID);
    assert_eq!(node["authentication"]["flow"], "xtls-rprx-vision");
    assert_eq!(node["transport"], "web_socket");
    assert_eq!(node["security"], "tls");
    assert_eq!(node["validation"], "valid");
    assert_eq!(node["executable"], false);
    assert_eq!(node["network_verified"], false);
    assert!(node["native_outbound"].is_null());
}

#[test]
fn insufficient_buffer_is_untouched_and_reports_exact_size() {
    let input = serde_json::to_vec(&vless()).unwrap();
    let (_, complete) = call(&input);
    let mut short = vec![0xa5; complete.len() - 1];
    // SAFETY: valid nonoverlapping buffers; the declared capacity is insufficient.
    let needed = unsafe {
        swirl_import_xray_v1(input.as_ptr(), input.len(), short.as_mut_ptr(), short.len())
    };
    assert_eq!(needed as usize, complete.len());
    assert!(short.iter().all(|byte| *byte == 0xa5));
}

#[test]
fn duplicate_keys_and_error_responses_never_echo_input_secrets() {
    let (response, encoded) = call(
        br#"{"protocol":"vless","settings":{"PRIVATE_TOKEN":"PRIVATE_PASSWORD","PRIVATE_TOKEN":"PRIVATE_PASSWORD"}}"#,
    );
    assert_eq!(response["schema"], 1);
    assert_eq!(response["ok"], false);
    assert_eq!(response["error"], "DuplicateJsonKey");
    let text = String::from_utf8(encoded).unwrap();
    assert!(!text.contains("PRIVATE_TOKEN"));
    assert!(!text.contains("PRIVATE_PASSWORD"));
    assert!(response.get("nodes").is_none());
    assert!(response.get("outbounds").is_none());
}

#[test]
fn structural_errors_budgets_and_invalid_utf8_use_the_strict_parser() {
    for bytes in [
        Vec::new(),
        vec![0xff, 0xfe],
        b"{\"protocol\":\"vless\",}".to_vec(),
        b"{/*comment*/\"protocol\":\"vless\"}".to_vec(),
        b"{\"protocol\":\"vless\",\"settings\":{\"port\":65536}}".to_vec(),
        b"{\"protocol\":\"vless\",\"settings\":{\"port\":\"443\"}}".to_vec(),
        format!("{}0{}", "[".repeat(34), "]".repeat(34)).into_bytes(),
        serde_json::to_vec(&vec![vless(); 2001]).unwrap(),
    ] {
        let (response, _) = call(&bytes);
        assert_eq!(response["schema"], 1);
        assert_eq!(response["ok"], false);
        assert!(response["error"].is_string());
    }
}

#[test]
fn maximum_input_is_bounded_before_pointer_access() {
    let mut input = serde_json::to_vec(&vless()).unwrap();
    input.resize(MAX_JSON_INPUT, b' ');
    assert_eq!(call(&input).0["ok"], true);
    // SAFETY: rejected by the size check before reading the supplied pointer.
    let result = unsafe {
        swirl_import_xray_v1(input.as_ptr(), MAX_JSON_INPUT + 1, std::ptr::null_mut(), 0)
    };
    assert_eq!(result, INVALID_BUFFER);
}

#[test]
fn abi_rejects_null_overlap_and_pointer_range_overflow_without_writes() {
    let mut input = serde_json::to_vec(&vless()).unwrap();
    // SAFETY: each invalid case is rejected before any pointer is dereferenced.
    unsafe {
        assert_eq!(
            swirl_import_xray_v1(std::ptr::null(), 1, std::ptr::null_mut(), 0),
            INVALID_BUFFER
        );
        assert_eq!(
            swirl_import_xray_v1(input.as_ptr(), input.len(), std::ptr::null_mut(), 1),
            INVALID_BUFFER
        );
        assert_eq!(
            swirl_import_xray_v1(input.as_ptr(), input.len(), input.as_mut_ptr(), input.len()),
            INVALID_BUFFER
        );
        assert_eq!(
            swirl_import_xray_v1(
                input.as_ptr(),
                input.len(),
                input.as_mut_ptr(),
                MAX_OUTPUT + 1
            ),
            INVALID_BUFFER
        );
        assert_eq!(
            swirl_import_xray_v1(usize::MAX as *const u8, 1, std::ptr::null_mut(), 0),
            INVALID_BUFFER
        );
    }
    assert!(serde_json::from_slice::<Value>(&input).is_ok());
    // SAFETY: zero-length null input is explicitly permitted by this ABI.
    assert!(unsafe { swirl_import_xray_v1(std::ptr::null(), 0, std::ptr::null_mut(), 0) } > 0);
}

#[test]
fn multiple_accounts_do_not_duplicate_the_raw_outbound() {
    let users = vec![json!({"id":ID,"encryption":"none"}); 2000];
    let original = json!({"protocol":"vless","settings":{"vnext":[{
        "address":"proxy.invalid","port":443,"users":users}]}});
    let (response, bytes) = call(&serde_json::to_vec(&original).unwrap());
    assert_eq!(response["ok"], true);
    assert_eq!(response["outbounds"], json!([original]));
    assert_eq!(response["nodes"].as_array().unwrap().len(), 2000);
    for (index, node) in response["nodes"].as_array().unwrap().iter().enumerate() {
        assert_eq!(node["index"], index);
        assert_eq!(node["source"]["outbound_index"], 0);
        assert_eq!(node["source"]["user_index"], index);
        assert!(node.get("raw_outbound").is_none());
    }
    assert!(bytes.len() < 4 * 1024 * 1024);
}

#[test]
fn six_protocol_names_and_local_actions_are_not_renamed() {
    let original = json!({"outbounds":[
        vless(),
        {"protocol":"vmess","settings":{"address":"vmess.invalid","port":443,"id":ID,"alterId":0}},
        {"protocol":"trojan","settings":{"servers":[{"address":"trojan.invalid","port":443,"password":"fixture"}]}},
        {"protocol":"shadowsocks","settings":{"servers":[{"address":"ss.invalid","port":443,"password":"fixture","method":"aes-128-gcm"}]}},
        {"protocol":"socks","settings":{"servers":[{"address":"socks.invalid","port":1080}]}},
        {"protocol":"http","settings":{"servers":[{"address":"http.invalid","port":8080}]}},
        {"protocol":"freedom"},{"protocol":"blackhole"},{"protocol":"dns"},{"protocol":"loopback"}
    ]});
    let response = call_value(&original);
    assert_eq!(response["ok"], true);
    let nodes = response["nodes"].as_array().unwrap();
    for (index, protocol) in ["vless", "vmess", "trojan", "shadowsocks", "socks", "http"]
        .iter()
        .enumerate()
    {
        assert_eq!(nodes[index]["protocol"], *protocol);
        assert_eq!(nodes[index]["is_remote_node"], true);
        assert_eq!(nodes[index]["network_verified"], false);
    }
    for node in &nodes[6..] {
        assert_eq!(node["is_remote_node"], false);
        assert_eq!(node["executable"], false);
    }
    assert_eq!(nodes[1]["authentication"]["kind"], "vmess");
    assert_eq!(nodes[1]["authentication"]["alter_id"], 0);
    assert_eq!(nodes[1]["executable"], false);
}

#[test]
fn password_getters_preserve_unicode_nul_and_exact_cipher_without_claiming_native_support() {
    let password = "  SYNTHETIC_密碼\u{0000} 🌪  ";
    let cases = [
        ("trojan", None),
        ("shadowsocks", Some("aes-128-gcm")),
        ("shadowsocks", Some("aes-256-gcm")),
        ("shadowsocks", Some("chacha20-ietf-poly1305")),
    ];
    let outbounds: Vec<Value> = cases
        .iter()
        .map(|(protocol, method)| {
            let mut server = json!({"address":"proxy.invalid","port":443,
                "password":password,"level":0,"email":"SYNTHETIC_EMAIL@example.invalid"});
            if let Some(method) = method {
                server["method"] = json!(method);
            }
            json!({"protocol":protocol,"tag":"密码节点 🌪","settings":{"servers":[server]}})
        })
        .collect();
    let original = json!({"outbounds":outbounds});
    let response = call_value(&original);
    assert_eq!(response["schema"], 1);
    assert_eq!(response["ok"], true);
    // Keep credential-bearing values out of assertion diagnostics.
    assert!(response["outbounds"] == original["outbounds"]);
    assert_eq!(response["nodes"].as_array().unwrap().len(), cases.len());
    for (index, (protocol, method)) in cases.iter().enumerate() {
        let node = &response["nodes"][index];
        assert_eq!(node["index"], index);
        assert_eq!(node["source"]["outbound_index"], index);
        assert_eq!(node["source"]["server_index"], 0);
        assert_eq!(node["protocol"], *protocol);
        assert_eq!(node["authentication"]["kind"], "password");
        assert!(node["authentication"]["password"].as_str() == Some(password));
        assert_eq!(node["authentication"]["method"].as_str(), *method);
        assert_eq!(node["authentication"]["level"], 0);
        assert!(node["authentication"]["email"] == "SYNTHETIC_EMAIL@example.invalid");
        assert_eq!(node["validation"], "valid");
        assert_eq!(node["executable"], false);
        assert!(node["native_outbound"].is_null());
        assert_eq!(node["execution_issues"], json!(["NativeConversionPending"]));
        assert_eq!(node["network_verified"], false);
        assert!(node["diagnostics"].as_array().unwrap().is_empty());
    }
}

#[test]
fn inbounds_never_become_remote_nodes_or_configure_listeners() {
    let original = json!({"inbounds":[{"protocol":"socks","port":23456,"listen":"0.0.0.0","settings":{}}],
        "outbounds":[vless()]});
    let response = call_value(&original);
    assert_eq!(response["ok"], true);
    assert_eq!(response["nodes"].as_array().unwrap().len(), 1);
    assert_eq!(response["outbounds"].as_array().unwrap().len(), 1);
    assert!(response.get("listen").is_none());
    assert_eq!(
        call_value(&json!({"inbounds":original["inbounds"]}))["ok"],
        false
    );
    assert_eq!(
        call_value(&json!({"protocol":"socks","listen":"0.0.0.0","port":23456}))["ok"],
        false
    );
}

fn reality() -> Value {
    let mut original = vless();
    original["settings"]["flow"] = json!("xtls-rprx-vision");
    original["streamSettings"] = json!({"network":"tcp","security":"reality",
        "realitySettings":{"serverName":"camouflage.invalid","fingerprint":"rustls",
            "publicKey":"CQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQk","shortId":"a1B2"}});
    original
}

#[test]
fn native_capability_reuses_existing_rust_mapper_and_preserves_reality_vision() {
    let original = reality();
    let response = call_value(&original);
    let node = &response["nodes"][0];
    assert_eq!(node["security"], "reality");
    assert_eq!(node["executable"], true);
    assert_eq!(node["native_outbound"]["type"], "vless");
    assert_eq!(node["native_outbound"]["flow"], "xtls-rprx-vision");
    assert_eq!(node["native_outbound"]["reality"]["short_id"], "a1B2");
    assert_eq!(node["network_verified"], false);

    let global = json!({"transport":{"wsSettings":{"path":"/global"}},"outbounds":[original]});
    let node = &call_value(&global)["nodes"][0];
    assert_eq!(node["executable"], false);
    assert!(node["native_outbound"].is_null());
    assert_eq!(node["execution_issues"][0], "GlobalTransportNotApplied");

    for (key, value) in [
        ("spiderX", json!("/preserved")),
        ("unrecognized", json!(true)),
    ] {
        let mut source = reality();
        source["streamSettings"]["realitySettings"][key] = value;
        let response = call_value(&source);
        assert_eq!(response["nodes"][0]["executable"], false);
        assert_eq!(response["outbounds"][0], source);
    }
}

#[test]
fn invalid_uuid_and_zero_port_are_parameter_failures_not_json_successful_execution() {
    for (key, value) in [
        ("id", json!("not-a-uuid-that-is-at-least-thirty-characters")),
        ("port", json!(0)),
    ] {
        let mut source = vless();
        source["settings"][key] = value;
        let response = call_value(&source);
        assert_eq!(response["ok"], true);
        assert_eq!(response["nodes"][0]["validation"], "invalid");
        assert_eq!(response["nodes"][0]["executable"], false);
        assert_eq!(response["nodes"][0]["network_verified"], false);
    }
}

#[test]
fn output_serialization_limit_is_enforced_before_allocation_or_writing() {
    let result = serialize(
        &json!({"private":"not reflected in errors"}),
        Counter::default(),
        8,
    );
    assert!(matches!(result, Err(OUTPUT_LIMIT)));
    let input = vec![b'a'; MAX_OUTPUT + 1];
    let result = serialize(&input, Counter::default(), MAX_OUTPUT);
    assert!(matches!(result, Err(OUTPUT_LIMIT)));
}

#[test]
fn imports_are_independent_across_threads() {
    let handles = (0..8)
        .map(|index| {
            std::thread::spawn(move || {
                let mut source = vless();
                source["tag"] = json!(format!("thread {index}"));
                for _ in 0..8 {
                    let response = call_value(&source);
                    assert_eq!(response["nodes"][0]["name"], format!("thread {index}"));
                    assert_eq!(response["nodes"][0]["network_verified"], false);
                }
            })
        })
        .collect::<Vec<_>>();
    for handle in handles {
        handle.join().unwrap();
    }
}
