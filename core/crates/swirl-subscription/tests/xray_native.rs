//! Native execution eligibility is a separate gate from lossless JSON import.
//! All identifiers, keys, hosts and credentials below are synthetic.
use serde_json::{Value, json};
use swirl_subscription::{
    Config, Outbound,
    xray::{
        InputSource,
        convert::{ConvertedDocument, NativeStatus, Protocol, ValidationStatus, import_document},
    },
};

const ID: &str = "00112233-4455-6677-8899-aabbccddeeff";
const KEY: &str = "ERERERERERERERERERERERERERERERERERERERERERE";

fn source(protocol: &str) -> Value {
    let mut value =
        json!({"protocol":protocol,"settings":{"address":"proxy.example.invalid","port":443}});
    match protocol {
        "vless" => {
            value["settings"]["id"] = json!(ID);
            value["settings"]["encryption"] = json!("none");
        }
        "vmess" => {
            value["settings"]["id"] = json!(ID);
            value["settings"]["alterId"] = json!(0);
            value["settings"]["security"] = json!("auto");
        }
        "trojan" | "shadowsocks" => {
            value["settings"]["password"] = json!(" SYNTHETIC:密碼/#% ");
            if protocol == "shadowsocks" {
                value["settings"]["method"] = json!("aes-128-gcm");
            }
        }
        _ => {}
    }
    value
}
fn tls() -> Value {
    json!({"network":"tcp","security":"tls","tlsSettings":{"serverName":"cover.example.invalid","alpn":["http/1.1"]}})
}
fn ws_tls() -> Value {
    let mut value = tls();
    value["network"] = json!("ws");
    value["wsSettings"] =
        json!({"path":"/fixture?token=synthetic","headers":{"Host":"front.example.invalid"}});
    value
}
fn reality() -> Value {
    json!({"network":"raw","security":"reality","realitySettings":{
        "publicKey":KEY,"shortId":"aabb","serverName":"cover.example.invalid","fingerprint":"chrome"}})
}
fn roundtrip(value: &Value) -> ConvertedDocument {
    let raw = serde_json::to_vec(value).unwrap();
    let original = import_document(&raw, InputSource::File).unwrap();
    let restored = ConvertedDocument::restore(&original.save().unwrap()).unwrap();
    assert_eq!(restored.raw_json(), raw);
    assert_eq!(restored.configuration(), value);
    assert_eq!(restored.nodes().len(), original.nodes().len());
    for (before, after) in original.nodes().iter().zip(restored.nodes()) {
        assert_eq!(before.native_status(), after.native_status());
        assert_eq!(before.validation(), after.validation());
        assert_eq!(before.source(), after.source());
        assert_eq!(before.diagnostics(), after.diagnostics());
        assert_eq!(
            before
                .native_outbound()
                .map(|o| serde_json::to_value(o).unwrap()),
            after
                .native_outbound()
                .map(|o| serde_json::to_value(o).unwrap())
        );
        assert!(!before.network_verified() && !after.network_verified());
    }
    restored
}
fn executable(value: &Value) -> Config {
    let doc = roundtrip(value);
    let node = &doc.nodes()[0];
    assert_eq!(node.validation(), ValidationStatus::Valid, "{node:?}");
    assert_eq!(node.native_status(), NativeStatus::Executable, "{node:?}");
    let config = doc
        .native_config(0, "127.0.0.1:0".parse().unwrap())
        .unwrap();
    assert!(config.validate().is_ok());
    let serialized = serde_json::to_vec(&config).unwrap();
    let reparsed = Config::parse(&serialized).unwrap();
    assert_eq!(
        serde_json::to_value(&reparsed).unwrap(),
        serde_json::to_value(config).unwrap()
    );
    reparsed
}
fn blocked(value: &Value) {
    let doc = roundtrip(value);
    for (i, node) in doc.nodes().iter().enumerate() {
        assert_eq!(node.native_status(), NativeStatus::Blocked, "{node:?}");
        assert!(node.native_outbound().is_none());
        assert_eq!(
            doc.native_config(i, "127.0.0.1:0".parse().unwrap())
                .err()
                .unwrap()
                .code,
            "NativeExecutionBlocked"
        );
        assert!(
            node.diagnostics()
                .iter()
                .any(|d| matches!(d.severity.as_str(), "error" | "unsupported"))
        );
    }
}

#[test]
fn vless_tcp_keeps_uuid_protocol_and_explicit_encryption_requirement() {
    let original = source("vless");
    let config = executable(&original);
    assert!(
        matches!(&config.nodes[0].outbound, Outbound::Vless { uuid, tls: None, reality: None, websocket: None, flow: None, .. } if uuid == ID)
    );
    let mut missing = original.clone();
    missing["settings"]
        .as_object_mut()
        .unwrap()
        .remove("encryption");
    blocked(&missing);
    for encryption in ["", "auto", "mlkem768x25519plus.native.600s.synthetic"] {
        missing["settings"]["encryption"] = json!(encryption);
        blocked(&missing);
    }
}

#[test]
fn vless_tls_keeps_sni_and_alpn_without_a_plaintext_candidate() {
    let mut value = source("vless");
    value["streamSettings"] = tls();
    let config = executable(&value);
    assert!(
        matches!(&config.nodes[0].outbound, Outbound::Vless { tls: Some(tls), reality: None, .. }
        if tls.server_name == "cover.example.invalid" && tls.alpn == ["http/1.1"])
    );
}

#[test]
fn vless_reality_and_vision_never_become_tls_or_lose_flow() {
    for flow in [None, Some("xtls-rprx-vision")] {
        let mut value = source("vless");
        value["streamSettings"] = reality();
        if let Some(flow) = flow {
            value["settings"]["flow"] = json!(flow);
        }
        let config = executable(&value);
        assert!(
            matches!(&config.nodes[0].outbound, Outbound::Vless { tls: None, reality: Some(r), flow: f, websocket: None, .. }
            if r.public_key == KEY && r.short_id == "aabb" && r.fingerprint == "chrome" && f.as_deref() == flow)
        );
    }
}

#[test]
fn vless_and_trojan_websocket_tls_keep_both_layers_host_and_path() {
    for protocol in ["vless", "trojan"] {
        let mut value = source(protocol);
        value["streamSettings"] = ws_tls();
        let config = executable(&value);
        let (tls, websocket) = match &config.nodes[0].outbound {
            Outbound::Vless {
                tls: Some(tls),
                websocket: Some(ws),
                ..
            }
            | Outbound::Trojan {
                tls,
                websocket: Some(ws),
                ..
            } => (tls, ws),
            _ => panic!("both TLS and WebSocket are required"),
        };
        assert_eq!(tls.server_name, "cover.example.invalid");
        assert_eq!(tls.alpn, ["http/1.1"]);
        assert_eq!(websocket.host, "front.example.invalid");
        assert_eq!(websocket.path, "/fixture?token=synthetic");
    }
}

#[test]
fn vmess_tcp_and_ws_tls_preserve_supported_aead_and_reject_legacy_modes() {
    for stream in [json!({"network":"tcp"}), ws_tls()] {
        for alter_id in [0, 64, 65535] {
            for cipher in ["auto", "aes-128-gcm", "chacha20-poly1305", "none", "zero"] {
                let mut value = source("vmess");
                value["settings"]["alterId"] = json!(alter_id);
                value["settings"]["security"] = json!(cipher);
                value["streamSettings"] = stream.clone();
                if alter_id == 0 && ["auto", "aes-128-gcm", "chacha20-poly1305"].contains(&cipher) {
                    let config = executable(&value);
                    assert!(
                        matches!(&config.nodes[0].outbound, Outbound::Vmess { uuid, alter_id: 0, security, .. } if uuid == ID && security == cipher)
                    );
                } else {
                    blocked(&value);
                }
                assert_eq!(roundtrip(&value).nodes()[0].protocol(), Protocol::Vmess);
            }
        }
    }
}

#[test]
fn trojan_requires_real_tls_and_preserves_the_exact_password() {
    let mut value = source("trojan");
    blocked(&value);
    value["streamSettings"] = tls();
    let config = executable(&value);
    assert!(
        matches!(&config.nodes[0].outbound, Outbound::Trojan { password, .. } if password == " SYNTHETIC:密碼/#% ")
    );
    value["streamSettings"] = reality();
    blocked(&value);
}

#[test]
fn shadowsocks_exact_aead_cipher_password_and_tcp_scope_are_preserved() {
    for cipher in ["aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305"] {
        let mut value = source("shadowsocks");
        value["settings"]["method"] = json!(cipher);
        let config = executable(&value);
        assert!(
            matches!(&config.nodes[0].outbound, Outbound::Shadowsocks { cipher: c, password, udp: false, obfs_http: None, .. }
            if c == cipher && password == " SYNTHETIC:密碼/#% ")
        );
    }
}

#[test]
fn unsupported_shadowsocks_methods_layers_and_replay_options_have_no_fallback() {
    for cipher in [
        "2022-blake3-aes-128-gcm",
        "aes-128-cfb",
        "none",
        "chacha20-poly1305",
        "aead_aes_128_gcm",
        "synthetic-unknown",
    ] {
        let mut value = source("shadowsocks");
        value["settings"]["method"] = json!(cipher);
        blocked(&value);
    }
    for stream in [tls(), ws_tls(), json!({"network":"grpc"})] {
        let mut value = source("shadowsocks");
        value["streamSettings"] = stream;
        blocked(&value);
    }
    for iv_check in [false, true] {
        let mut value = source("shadowsocks");
        value["settings"]["ivCheck"] = json!(iv_check);
        blocked(&value);
    }
}

#[test]
fn socks_and_http_authentication_is_exact_and_not_changed_to_no_auth() {
    for protocol in ["socks", "http"] {
        let mut value = source(protocol);
        value["settings"]["user"] = json!("SYNTHETIC_USER");
        value["settings"]["pass"] = json!(" password:with:colon ");
        let config = executable(&value);
        let auth = match &config.nodes[0].outbound {
            Outbound::Socks5 {
                auth: Some(auth), ..
            }
            | Outbound::HttpConnect {
                auth: Some(auth), ..
            } => auth,
            _ => panic!("credential pair required"),
        };
        assert_eq!(auth.username, "SYNTHETIC_USER");
        assert_eq!(auth.password, " password:with:colon ");
        value["settings"]["pass"] = json!("");
        blocked(&value);
    }
}

#[test]
fn proxy_no_auth_and_tls_are_distinct_valid_native_variants() {
    for protocol in ["socks", "http"] {
        let config = executable(&source(protocol));
        assert!(matches!(
            &config.nodes[0].outbound,
            Outbound::Socks5 {
                auth: None,
                tls: None,
                ..
            } | Outbound::HttpConnect {
                auth: None,
                tls: None,
                ..
            }
        ));
        let mut value = source(protocol);
        value["streamSettings"] = tls();
        let config = executable(&value);
        assert!(matches!(
            &config.nodes[0].outbound,
            Outbound::Socks5 {
                auth: None,
                tls: Some(_),
                ..
            } | Outbound::HttpConnect {
                auth: None,
                tls: Some(_),
                ..
            }
        ));
        value["streamSettings"] = ws_tls();
        blocked(&value);
    }
}

#[test]
fn socks4_explicit_empty_userid_and_uppercase_4a_keep_version_semantics() {
    for (version, remote_dns) in [("4", false), ("4a", true), ("4A", true)] {
        let value = json!({"protocol":"socks","settings":{"version":version,"servers":[
            {"address":"proxy.example.invalid","port":1080,"users":[{}]}
        ]}});
        let config = executable(&value);
        assert!(
            matches!(&config.nodes[0].outbound, Outbound::Socks4 { user_id, remote_dns: dns, .. }
            if user_id.is_empty() && *dns == remote_dns)
        );
    }
}

#[test]
fn all_servers_and_accounts_remain_selectable_by_original_index() {
    for protocol in ["socks", "http"] {
        let value = json!({"protocol":protocol,"settings":{"servers":[
            {"address":"one.example.invalid","port":1001,"users":[{"user":"first","pass":"one"}]},
            {"address":"two.example.invalid","port":1002,"users":[{"user":"second","pass":"two"},{"user":"third","pass":"three"}]}
        ]}});
        let doc = roundtrip(&value);
        assert_eq!(doc.nodes().len(), 3);
        for (index, (server, user, username, password)) in [
            (0, 0, "first", "one"),
            (1, 0, "second", "two"),
            (1, 1, "third", "three"),
        ]
        .into_iter()
        .enumerate()
        {
            let node = &doc.nodes()[index];
            assert_eq!(node.source().server_index, Some(server));
            assert_eq!(node.source().user_index, Some(user));
            let config = doc
                .native_config(index, "127.0.0.1:0".parse().unwrap())
                .unwrap();
            let auth = match &config.nodes[0].outbound {
                Outbound::Socks5 {
                    auth: Some(auth), ..
                }
                | Outbound::HttpConnect {
                    auth: Some(auth), ..
                } => auth,
                _ => panic!("account was dropped"),
            };
            assert_eq!(
                (auth.username.as_str(), auth.password.as_str()),
                (username, password)
            );
            assert_eq!(config.nodes.len(), 1);
        }
        assert_eq!(
            doc.native_config(3, "127.0.0.1:0".parse().unwrap())
                .err()
                .unwrap()
                .code,
            "NativeNodeIndex"
        );
    }
}

#[test]
fn every_invalid_port_uuid_and_wrong_type_remains_unexecutable() {
    for port in [json!(0), json!(65536), json!(-1), json!("443"), json!(null)] {
        let mut value = source("vless");
        value["settings"]["port"] = port;
        let bytes = serde_json::to_vec(&value).unwrap();
        match import_document(&bytes, InputSource::File) {
            Err(d) => assert_eq!(d.severity, "error"),
            Ok(_) => blocked(&value),
        }
    }
    for id in [
        "",
        "not-a-canonical-uuid-with-more-than-thirty-bytes",
        "00112233-4455-6677-8899-aabbccddeefg",
    ] {
        let mut value = source("vless");
        value["settings"]["id"] = json!(id);
        blocked(&value);
    }
}

#[test]
fn short_custom_id_uses_the_fixed_upstream_utf8_byte_boundary() {
    for (id, expected) in [
        ("a".repeat(29), ValidationStatus::Unverified),
        ("b".repeat(30), ValidationStatus::Unverified),
        ("c".repeat(31), ValidationStatus::Invalid),
        ("字".repeat(10), ValidationStatus::Unverified),
        ("字".repeat(11), ValidationStatus::Invalid),
    ] {
        let mut value = source("vless");
        value["settings"]["id"] = json!(id);
        blocked(&value);
        let doc = roundtrip(&value);
        assert_eq!(doc.nodes()[0].validation(), expected);
        let code = if expected == ValidationStatus::Unverified {
            "CustomIdMappingUnsupported"
        } else {
            "InvalidUuid"
        };
        assert!(doc.nodes()[0].diagnostics().iter().any(|d| d.code == code));
    }
}

#[test]
fn unsupported_transports_tls_reality_conflict_and_vision_conflicts_stay_blocked() {
    for network in [
        "grpc",
        "h2",
        "http",
        "httpupgrade",
        "xhttp",
        "synthetic-future",
    ] {
        let mut value = source("vless");
        value["streamSettings"] = json!({"network":network});
        blocked(&value);
    }
    let mut value = source("vless");
    value["streamSettings"] = reality();
    value["streamSettings"]["tlsSettings"] = json!({"serverName":"cover.example.invalid"});
    blocked(&value);
    for stream in [json!({}), tls(), ws_tls()] {
        value["streamSettings"] = stream;
        value["settings"]["flow"] = json!("xtls-rprx-vision");
        blocked(&value);
    }
    value["streamSettings"] = reality();
    value["settings"]["flow"] = json!("xtls-rprx-vision-udp443");
    blocked(&value);
}

#[test]
fn explicit_tls_and_websocket_extensions_never_disappear_to_make_a_candidate() {
    for extra in [
        json!({"fingerprint":"chrome"}),
        json!({"allowInsecure":true}),
        json!({"disableSystemRoot":true}),
        json!({"certificates":[{"certificateFile":"SYNTHETIC_FILE.pem"}]}),
    ] {
        let mut value = source("vless");
        value["streamSettings"] = tls();
        value["streamSettings"]["tlsSettings"]
            .as_object_mut()
            .unwrap()
            .extend(extra.as_object().unwrap().clone());
        blocked(&value);
    }
    for ws in [
        json!({"host":"front.example.invalid","path":"/","headers":{"X-Synthetic":"private"}}),
        json!({"host":"front.example.invalid","path":"/","maxEarlyData":2048}),
        json!({"host":"front.example.invalid","path":"/","earlyDataHeaderName":"Sec-WebSocket-Protocol"}),
    ] {
        let mut value = source("trojan");
        value["streamSettings"] = ws_tls();
        value["streamSettings"]["wsSettings"] = ws;
        blocked(&value);
    }
}

#[test]
fn late_global_transport_diagnostics_revoke_cached_native_candidates() {
    let value = json!({"outbounds":[source("vless")],"transport":{"tcpSettings":{"header":{"type":"http"}}}});
    let doc = roundtrip(&value);
    assert!(
        doc.nodes()[0]
            .diagnostics()
            .iter()
            .any(|d| d.code == "GlobalTransportDefaultsUnsupported")
    );
    blocked(&value);
}

#[test]
fn source_global_sections_are_kept_but_node_export_is_explicitly_single_node() {
    let value = json!({
        "outbounds":[source("vless")],
        "dns":{"servers":["dns.example.invalid"]},
        "routing":{"domainStrategy":"IPIfNonMatch","rules":[]},
        "policy":{"levels":{"0":{"handshake":4}}}
    });
    let doc = roundtrip(&value);
    let config = doc
        .native_config(0, "127.0.0.1:0".parse().unwrap())
        .unwrap();
    assert_eq!(doc.configuration(), &value);
    assert_eq!(config.nodes.len(), 1);
    assert!(config.rules.is_empty() && config.selectors.is_empty() && !config.smart_routing);
    assert!(config.validate().is_ok());
}

#[test]
fn unknown_fields_mux_and_policy_levels_cannot_authorize_native_execution() {
    for value in [
        {
            let mut v = source("vless");
            v["settings"]["SYNTHETIC_PRIVATE_KEY"] = json!("private value");
            v
        },
        {
            let mut v = source("trojan");
            v["streamSettings"] = tls();
            v["mux"] = json!({"enabled":true});
            v
        },
        {
            let mut v = source("http");
            v["settings"]["level"] = json!(1);
            v
        },
    ] {
        blocked(&value);
    }
}

#[test]
fn listen_address_and_mutated_native_config_are_revalidated_at_the_real_ir_boundary() {
    let doc = roundtrip(&source("vless"));
    assert!(
        doc.native_config(0, "0.0.0.0:8080".parse().unwrap())
            .is_err()
    );
    assert!(doc.native_config(0, "[::]:8080".parse().unwrap()).is_err());
    assert!(doc.native_config(0, "[::1]:0".parse().unwrap()).is_ok());
    let config = doc
        .native_config(0, "127.0.0.1:0".parse().unwrap())
        .unwrap();
    let mut wire = serde_json::to_value(config).unwrap();
    wire["nodes"][0]["outbound"]["type"] = json!("vmess");
    wire["nodes"][0]["outbound"]["alter_id"] = json!(16);
    assert!(Config::parse(&serde_json::to_vec(&wire).unwrap()).is_err());
    wire["nodes"][0]["outbound"]
        .as_object_mut()
        .unwrap()
        .remove("alter_id");
    wire["nodes"][0]["outbound"]["type"] = json!("vless");
    wire["nodes"][0]["outbound"]["flow"] = json!("xtls-rprx-vision");
    assert!(Config::parse(&serde_json::to_vec(&wire).unwrap()).is_err());
}

#[test]
fn archive_and_diagnostics_cannot_forge_or_leak_execution_authority() {
    let mut value = source("trojan");
    value["settings"]["password"] = json!("SYNTHETIC_PASSWORD_NEVER_LOGGED");
    value["streamSettings"] = ws_tls();
    value["streamSettings"]["wsSettings"]["headers"]["SYNTHETIC_PRIVATE_HEADER"] =
        json!("SYNTHETIC_HEADER_VALUE");
    let doc = roundtrip(&value);
    blocked(&value);
    let public = format!("{doc:?} {:?}", doc.nodes()[0]);
    for secret in [
        "SYNTHETIC_PASSWORD_NEVER_LOGGED",
        "SYNTHETIC_PRIVATE_HEADER",
        "SYNTHETIC_HEADER_VALUE",
        "proxy.example.invalid",
    ] {
        assert!(!public.contains(secret));
    }
    let mut archive: Value = serde_json::from_slice(&doc.save().unwrap()).unwrap();
    archive["native_status"] = json!("executable");
    assert!(ConvertedDocument::restore(&serde_json::to_vec(&archive).unwrap()).is_err());
    archive.as_object_mut().unwrap().remove("native_status");
    archive["raw_json"] = json!(serde_json::to_string(&source("vmess")).unwrap());
    let changed = ConvertedDocument::restore(&serde_json::to_vec(&archive).unwrap()).unwrap();
    assert_eq!(changed.nodes()[0].protocol(), Protocol::Vmess);
    assert_eq!(changed.nodes()[0].native_status(), NativeStatus::Executable);
    assert!(matches!(
        changed.nodes()[0].native_outbound(),
        Some(Outbound::Vmess { alter_id: 0, .. })
    ));
    assert!(!changed.nodes()[0].network_verified());
}

#[test]
fn compact_and_partially_separated_uuid_syntax_is_retained_without_native_normalization() {
    for id in [
        "00112233445566778899aabbccddeeff",
        "00112233-445566778899aabbccddeeff",
        "-00112233445566778899aabbccddeeff",
        "001122334455-6677-8899-aabbccddeeff",
    ] {
        let mut value = source("vless");
        value["settings"]["id"] = json!(id);
        blocked(&value);
        let doc = roundtrip(&value);
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Unverified);
        assert!(
            doc.nodes()[0]
                .diagnostics()
                .iter()
                .any(|d| d.code == "NonCanonicalUuidMappingUnsupported")
        );
        assert_eq!(doc.configuration()["settings"]["id"], id);
    }
    for id in [
        "00112233445566778899aabbccddeefg",
        "00112233445566778899aabbccddeeff-",
        "00112233445566778899aabbccddeeffXYZ",
        "00112233--445566778899aabbccddeeff",
    ] {
        let mut value = source("vless");
        value["settings"]["id"] = json!(id);
        let doc = roundtrip(&value);
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
        blocked(&value);
    }
}
