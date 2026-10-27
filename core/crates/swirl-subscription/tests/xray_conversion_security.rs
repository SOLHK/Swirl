//! B4 stream semantics. All material is synthetic and no file/network is opened.
use serde_json::{Value, json};
use swirl_subscription::xray::{
    InputSource,
    convert::{
        Authentication, ConvertedDocument, Security, Transport, ValidationStatus, import_document,
    },
};

const ID: &str = "00000000-0000-4000-8000-000000000001";
const KEY: &str = "ERERERERERERERERERERERERERERERERERERERERERE";
fn vless(stream: Value) -> Value {
    json!({"protocol":"vless","settings":{"address":"proxy.example.invalid","port":443,
        "id":ID,"encryption":"none"},"streamSettings":stream})
}
fn reality() -> Value {
    json!({"network":"raw","security":"reality","realitySettings":{
        "serverName":"cover.example.invalid","publicKey":KEY,"shortId":"aabb","fingerprint":"chrome"}})
}
fn import(value: &Value) -> ConvertedDocument {
    import_document(&serde_json::to_vec(value).unwrap(), InputSource::File).unwrap()
}
fn roundtrip(value: &Value) -> ConvertedDocument {
    let doc = import(value);
    let restored = ConvertedDocument::restore(&doc.save().unwrap()).unwrap();
    assert_eq!(restored.configuration(), value);
    assert_eq!(doc.raw_json(), restored.raw_json());
    for (first, restored) in doc.nodes().iter().zip(restored.nodes()) {
        assert_eq!(first.transport(), restored.transport());
        assert_eq!(first.security(), restored.security());
        assert_eq!(first.validation(), restored.validation());
        assert_eq!(first.diagnostics(), restored.diagnostics());
        assert_eq!(first.source(), restored.source());
        assert!(!restored.network_verified());
        for (a, b) in [
            (
                first.projected_tls().map(serde_json::to_value),
                restored.projected_tls().map(serde_json::to_value),
            ),
            (
                first.projected_reality().map(serde_json::to_value),
                restored.projected_reality().map(serde_json::to_value),
            ),
            (
                first.projected_websocket().map(serde_json::to_value),
                restored.projected_websocket().map(serde_json::to_value),
            ),
        ] {
            assert_eq!(a.map(Result::unwrap), b.map(Result::unwrap));
        }
    }
    restored
}
fn has(doc: &ConvertedDocument, code: &str) -> bool {
    doc.nodes()[0].diagnostics().iter().any(|d| d.code == code)
}
fn blocked(doc: &ConvertedDocument) -> bool {
    doc.nodes()[0]
        .diagnostics()
        .iter()
        .any(|d| matches!(d.severity.as_str(), "error" | "unsupported"))
}

#[test]
fn tcp_tls_defaults_are_projected_without_changing_absent_source_fields() {
    let original = vless(json!({"network":"raw","security":"tls"}));
    let doc = roundtrip(&original);
    let node = &doc.nodes()[0];
    assert_eq!(node.transport(), Transport::Tcp);
    assert_eq!(node.security(), Security::Tls);
    let tls = node.projected_tls().unwrap();
    assert_eq!(tls.server_name, "proxy.example.invalid");
    assert_eq!(tls.alpn, ["h2", "http/1.1"]);
    assert!(tls.ca_der_base64.is_none());
    assert!(doc.stream_settings(0).unwrap().get("tlsSettings").is_none());
    assert!(!blocked(&doc));
}

#[test]
fn tls_sni_and_string_or_array_alpn_are_lossless() {
    for alpn in [json!("h2,http/1.1"), json!(["h2", "http/1.1"])] {
        let original = vless(json!({"security":"tls","tlsSettings":{
            "serverName":"sni.example.invalid","alpn":alpn,"allowInsecure":false,
            "disableSystemRoot":false,"certificates":[]}}));
        let doc = roundtrip(&original);
        assert_eq!(
            doc.nodes()[0].projected_tls().unwrap().alpn,
            ["h2", "http/1.1"]
        );
        assert_eq!(doc.stream_settings(0), original.get("streamSettings"));
        assert!(!blocked(&doc));
    }
}

#[test]
fn explicit_certificate_fingerprint_verification_and_ech_options_never_disappear() {
    for extra in [
        json!({"allowInsecure":true}),
        json!({"disableSystemRoot":true}),
        json!({"fingerprint":"chrome"}),
        json!({"fingerprint":""}),
        json!({"certificates":[{"certificateFile":"SYNTHETIC_PRIVATE_FILE.pem","key":["SYNTHETIC_KEY"]}]}),
        json!({"pinnedPeerCertificateChainSha256":["SYNTHETIC_PIN"]}),
        json!({"pinnedPeerCertSha256":"SYNTHETIC_PIN"}),
        json!({"minVersion":"1.3"}),
        json!({"enableSessionResumption":true}),
        json!({"echConfigList":"SYNTHETIC_ECH"}),
        json!({"useSystemCA":true}),
    ] {
        let doc = roundtrip(&vless(json!({"security":"tls","tlsSettings":extra})));
        assert!(blocked(&doc));
        let text = format!("{doc:?} {:?}", doc.nodes()[0]);
        assert!(!text.contains("SYNTHETIC_"));
    }
}

#[test]
fn reality_and_vision_keep_the_real_security_and_flow() {
    let mut original = vless(reality());
    original["settings"]["flow"] = json!("xtls-rprx-vision");
    let doc = roundtrip(&original);
    let node = &doc.nodes()[0];
    assert_eq!(node.security(), Security::Reality);
    assert!(node.projected_tls().is_none());
    assert!(
        matches!(node.authentication(), Authentication::Vless { flow: Some(flow), .. } if flow == "xtls-rprx-vision")
    );
    let params = node.projected_reality().unwrap();
    assert_eq!(params.public_key, KEY);
    assert_eq!(params.short_id, "aabb");
    assert_eq!(params.fingerprint, "chrome");
    assert!(!blocked(&doc));
}

#[test]
fn reality_password_alias_maps_only_when_unambiguous() {
    let mut stream = reality();
    stream["realitySettings"]["password"] = json!(KEY);
    let doc = roundtrip(&vless(stream.clone()));
    assert!(!blocked(&doc));
    assert_eq!(doc.nodes()[0].projected_reality().unwrap().public_key, KEY);
    stream["realitySettings"]["password"] = json!("IiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiI");
    let doc = roundtrip(&vless(stream));
    assert!(has(&doc, "RealityPublicKeyAliasConflict"));
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
}

#[test]
fn reality_missing_and_unsupported_fingerprints_never_become_plain_tls() {
    for fingerprint in [None, Some(""), Some("firefox")] {
        let mut stream = reality();
        if let Some(fingerprint) = fingerprint {
            stream["realitySettings"]["fingerprint"] = json!(fingerprint);
        } else {
            stream["realitySettings"]
                .as_object_mut()
                .unwrap()
                .remove("fingerprint");
        }
        let doc = roundtrip(&vless(stream));
        assert!(blocked(&doc));
        assert_eq!(doc.nodes()[0].security(), Security::Reality);
        assert!(doc.nodes()[0].projected_tls().is_none());
    }
}

#[test]
fn official_chrome_133_spelling_uses_the_fixed_native_profile_but_source_is_exact() {
    let mut stream = reality();
    stream["realitySettings"]["fingerprint"] = json!("hellochrome_133");
    let doc = roundtrip(&vless(stream.clone()));
    assert!(!blocked(&doc));
    assert_eq!(
        doc.nodes()[0].projected_reality().unwrap().fingerprint,
        "chrome_133"
    );
    assert_eq!(doc.stream_settings(0), Some(&stream));
}

#[test]
fn native_only_fingerprint_names_cannot_bypass_the_source_schema() {
    for fingerprint in [
        "rustls",
        "Rustls",
        "chrome_133",
        "CHROME_133",
        "future-native",
    ] {
        let mut stream = reality();
        stream["realitySettings"]["fingerprint"] = json!(fingerprint);
        let doc = roundtrip(&vless(stream.clone()));
        assert!(has(&doc, "RealitySourceFingerprintUnsupported"));
        assert!(blocked(&doc));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Unverified);
        assert_eq!(doc.stream_settings(0), Some(&stream));
        assert!(doc.nodes()[0].projected_tls().is_none());
    }
}

#[test]
fn reality_implicit_crawler_difference_is_visible_without_inventing_source_fields() {
    for fingerprint in ["chrome", "CHROME", "hellochrome_133"] {
        let mut stream = reality();
        stream["realitySettings"]["fingerprint"] = json!(fingerprint);
        let doc = roundtrip(&vless(stream.clone()));
        assert!(!blocked(&doc));
        assert!(doc.nodes()[0].diagnostics().iter().any(|diagnostic| {
            diagnostic.code == "RealityNativeAuthenticationOnly" && diagnostic.severity == "info"
        }));
        let projection = doc.nodes()[0].projected_reality().unwrap();
        // The pinned Chrome profile's native empty ALPN explicitly means the
        // h2,http/1.1 offer. It cannot select the rustls profile by default.
        assert!(matches!(
            projection.fingerprint.as_str(),
            "chrome" | "chrome_133"
        ));
        assert!(projection.alpn.is_empty());
        assert!(stream["realitySettings"].get("spiderX").is_none());
        assert_eq!(doc.stream_settings(0), Some(&stream));
    }
    for explicit in ["", "/"] {
        let mut stream = reality();
        stream["realitySettings"]["spiderX"] = json!(explicit);
        let doc = roundtrip(&vless(stream));
        assert!(has(&doc, "RealitySpiderUnsupported"));
        assert!(!has(&doc, "RealityNativeAuthenticationOnly"));
        assert!(blocked(&doc));
    }
}

#[test]
fn reality_debug_spider_and_additional_verification_options_remain_blocking() {
    for (field, value) in [
        ("show", json!(true)),
        ("spiderX", json!("/SYNTHETIC_SPIDER")),
        ("mldsa65Verify", json!("SYNTHETIC_MLDSA")),
        ("masterKeyLog", json!("SYNTHETIC_PATH")),
        ("dest", json!("server-only.invalid:443")),
        ("futureSYNTHETIC_SECRET", json!(true)),
    ] {
        let mut stream = reality();
        stream["realitySettings"][field] = value;
        let doc = roundtrip(&vless(stream));
        assert!(blocked(&doc));
        assert!(
            !serde_json::to_string(doc.nodes()[0].diagnostics())
                .unwrap()
                .contains("SYNTHETIC")
        );
    }
}

#[test]
fn reality_key_and_short_id_format_errors_are_semantic_errors() {
    for (field, value) in [
        ("shortId", "abc"),
        ("shortId", "gg"),
        ("shortId", "001122334455667788"),
        ("publicKey", "bad-key"),
        ("publicKey", "ERERERERERERERERERERERERERERERERERERERERERE="),
    ] {
        let mut stream = reality();
        stream["realitySettings"][field] = json!(value);
        let doc = roundtrip(&vless(stream));
        assert!(blocked(&doc));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
    }
}

#[test]
fn vision_unsupported_combinations_keep_exact_flow_and_source() {
    for (flow, stream) in [
        ("xtls-rprx-vision", json!({"security":"tls"})),
        (
            "xtls-rprx-vision",
            json!({"network":"ws","wsSettings":{"host":"proxy.example.invalid"}}),
        ),
        ("xtls-rprx-vision-udp443", reality()),
        ("future-flow", reality()),
    ] {
        let mut original = vless(stream);
        original["settings"]["flow"] = json!(flow);
        let doc = roundtrip(&original);
        assert!(blocked(&doc));
        assert!(
            matches!(doc.nodes()[0].authentication(),Authentication::Vless { flow: Some(value), .. } if value == flow)
        );
    }
}

#[test]
fn websocket_tls_host_path_and_defaults_are_not_erased() {
    let stream = json!({"network":"websocket","security":"tls", "tlsSettings":{"serverName":"sni.example.invalid"},
        "wsSettings":{"headers":{"Host":"front.example.invalid:8443"},"path":"relative?token=SYNTHETIC", "maxEarlyData":0}});
    let doc = roundtrip(&vless(stream.clone()));
    assert!(!blocked(&doc));
    assert_eq!(doc.nodes()[0].transport(), Transport::WebSocket);
    let ws = doc.nodes()[0].projected_websocket().unwrap();
    assert_eq!(ws.host, "front.example.invalid:8443");
    assert_eq!(ws.path, "/relative?token=SYNTHETIC");
    assert_eq!(doc.nodes()[0].projected_tls().unwrap().alpn, ["http/1.1"]);
    assert_eq!(doc.stream_settings(0), Some(&stream));
}

#[test]
fn websocket_custom_headers_early_data_and_heartbeat_are_retained_and_blocked() {
    for settings in [
        json!({"path":"/ws?ed=2048"}),
        json!({"path":"/ws?ed=0"}),
        json!({"path":"/ws?ed=not-an-integer"}),
        json!({"maxEarlyData":2048}),
        json!({"earlyDataHeaderName":"Sec-WebSocket-Protocol"}),
        json!({"headers":{"Authorization":"SYNTHETIC_TOKEN"}}),
        json!({"headers":{"X-SYNTHETIC_SECRET":"SYNTHETIC_VALUE"}}),
        json!({"heartbeatPeriod":30}),
        json!({"useBrowserForwarding":true}),
        json!({"acceptProxyProtocol":true}),
        json!({"parseXForwardedFor":true}),
    ] {
        let doc = roundtrip(&vless(json!({"network":"ws","wsSettings":settings})));
        assert!(blocked(&doc));
        assert_eq!(doc.nodes()[0].transport(), Transport::WebSocket);
        assert!(
            !serde_json::to_string(doc.nodes()[0].diagnostics())
                .unwrap()
                .contains("SYNTHETIC")
        );
    }
}

#[test]
fn websocket_conflicting_or_repeated_host_headers_are_invalid() {
    for settings in [
        json!({"host":"one.example.invalid","headers":{"Host":"two.example.invalid"}}),
        json!({"headers":{"Host":"one.example.invalid","host":"one.example.invalid"}}),
        json!({"headers":{"Host":"a\r\nInjected: value"}}),
    ] {
        let doc = roundtrip(&vless(json!({"network":"ws","wsSettings":settings})));
        assert!(blocked(&doc));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
    }
}

#[test]
fn websocket_dialect_dependent_host_defaults_are_never_guessed() {
    for (port, sni) in [
        (8443, "proxy.example.invalid"),
        (443, "sni.example.invalid"),
    ] {
        let mut original =
            vless(json!({"network":"ws","security":"tls","tlsSettings":{"serverName":sni}}));
        original["settings"]["port"] = json!(port);
        let doc = roundtrip(&original);
        assert!(has(&doc, "WebSocketHostDefaultAmbiguous"));
    }
}

#[test]
fn websocket_integer_range_matches_v2ray_signed_early_data_bound() {
    let doc = roundtrip(&vless(
        json!({"network":"ws","wsSettings":{"maxEarlyData":2147483648u64}}),
    ));
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
}

#[test]
fn incompatible_transport_settings_are_preserved_and_never_fall_back_to_tcp() {
    for (name, kind) in [
        ("grpc", Transport::Grpc),
        ("http", Transport::Http2),
        ("h2", Transport::Http2),
        ("httpupgrade", Transport::HttpUpgrade),
        ("xhttp", Transport::Xhttp),
        ("splithttp", Transport::Xhttp),
        ("future-transport", Transport::Unknown),
    ] {
        let stream = json!({"network":name,"grpcSettings":{"serviceName":"SYNTHETIC_SERVICE"},
            "httpSettings":{"host":["h2.example.invalid"],"path":"/h2"},
            "httpupgradeSettings":{"path":"/upgrade"},"xhttpSettings":{"mode":"stream-up"}});
        let doc = roundtrip(&vless(stream.clone()));
        assert_eq!(doc.nodes()[0].transport(), kind);
        assert!(blocked(&doc));
        assert!(has(&doc, "UnappliedStreamSettingsPreserved"));
        assert_eq!(doc.stream_settings(0), Some(&stream));
    }
}

#[test]
fn tls_reality_and_network_alias_conflicts_are_invalid() {
    for stream in [
        json!({"security":"tls","tlsSettings":{},"realitySettings":{}}),
        json!({"network":"ws","security":"reality","realitySettings":{}}),
        json!({"network":"tcp","method":"ws"}),
        json!({"rawSettings":{"header":{"type":"none"}},"tcpSettings":{"header":{"type":"http"}}}),
    ] {
        let doc = roundtrip(&vless(stream));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
        assert!(blocked(&doc));
    }
}

#[test]
fn explicit_noop_raw_settings_and_aliases_are_supported_without_losing_source() {
    let stream = json!({"network":"RAW","method":"tcp","rawSettings":{"header":{"type":"none"},"acceptProxyProtocol":false},
        "tcpSettings":{"header":{"type":"none"},"acceptProxyProtocol":false}});
    let doc = roundtrip(&vless(stream));
    assert_eq!(doc.nodes()[0].transport(), Transport::Tcp);
    assert!(!blocked(&doc));
}

#[test]
fn inactive_nonempty_settings_and_unknown_stream_fields_block_execution() {
    for stream in [
        json!({"tlsSettings":{"serverName":"unused.example.invalid"}}),
        json!({"network":"tcp","wsSettings":{"path":"/unused"}}),
        json!({"network":"tcp","SYNTHETIC_SECRET_KEY":"SYNTHETIC_VALUE"}),
        json!({"security":"future-security"}),
    ] {
        let doc = roundtrip(&vless(stream));
        assert!(blocked(&doc));
        assert!(
            !serde_json::to_string(doc.nodes()[0].diagnostics())
                .unwrap()
                .contains("SYNTHETIC")
        );
    }
}

#[test]
fn enabled_mux_and_xudp_extensions_do_not_become_plain_connections() {
    for mux in [
        json!({"enabled":true,"concurrency":8}),
        json!({"enabled":false,"xudpConcurrency":16}),
        json!({"enabled":false,"xudpProxyUDP443":"allow"}),
        json!({"futureMux":false}),
    ] {
        let mut original = vless(json!({}));
        original["mux"] = mux.clone();
        let doc = roundtrip(&original);
        assert!(blocked(&doc));
        assert_eq!(doc.mux(0), Some(&mux));
    }
    let mut original = vless(json!({}));
    original["mux"] = json!({"enabled":false,"concurrency":8});
    assert!(!blocked(&roundtrip(&original)));
}

#[test]
fn mux_field_types_and_out_of_range_values_are_never_defaulted() {
    for mux in [json!({"enabled":"true"}), json!({"concurrency":"8"})] {
        let mut original = vless(json!({}));
        original["mux"] = mux;
        assert!(
            import_document(&serde_json::to_vec(&original).unwrap(), InputSource::File).is_err()
        );
    }
    let mut original = vless(json!({}));
    original["mux"] = json!({"concurrency":65536});
    let doc = roundtrip(&original);
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
}

#[test]
fn global_transport_inheritance_remains_blocked_after_archive_reload() {
    let original = json!({"outbounds":[vless(json!({})),vless(json!({"security":"tls"}))],
        "transport":{"wsSettings":{"path":"/inherited"}}});
    let doc = roundtrip(&original);
    for node in doc.nodes() {
        assert!(
            node.diagnostics()
                .iter()
                .any(|d| d.code == "GlobalTransportDefaultsUnsupported")
        );
    }
}

#[test]
fn malformed_security_types_still_use_the_existing_strict_parser() {
    for stream in [
        json!({"network":7}),
        json!({"security":false}),
        json!({"tlsSettings":{"allowInsecure":"false"}}),
        json!({"tlsSettings":{"alpn":["h2",null]}}),
        json!({"realitySettings":{"show":1}}),
        json!({"wsSettings":{"headers":{"Authorization":[]}}}),
    ] {
        assert!(
            import_document(
                &serde_json::to_vec(&vless(stream)).unwrap(),
                InputSource::File
            )
            .is_err()
        );
    }
    let doc = roundtrip(&vless(json!({"method":false})));
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
}

#[test]
fn security_projections_are_bounded_and_diagnostics_redact_unknown_names() {
    for stream in [
        json!({"security":"tls","tlsSettings":{"serverName":"x".repeat(4096)}}),
        json!({"security":"tls","tlsSettings":{"alpn":"x".repeat(4096)}}),
        json!({"network":"ws","wsSettings":{"path":"x".repeat(4096)}}),
    ] {
        let doc = roundtrip(&vless(stream));
        assert!(blocked(&doc));
    }
    let mut stream = json!({"security":"tls","tlsSettings":{}});
    for i in 0..65 {
        stream["tlsSettings"][format!("SYNTHETIC_SECRET_{i}")] = json!(true);
    }
    let error = import_document(
        &serde_json::to_vec(&vless(stream)).unwrap(),
        InputSource::File,
    )
    .unwrap_err();
    assert_eq!(error.code, "DiagnosticLimit");
    assert!(!format!("{error:?}").contains("SYNTHETIC"));
}

#[test]
fn unimplemented_or_unknown_stream_semantics_are_unverified_not_validated() {
    for stream in [
        json!({"network":"future-grpc-version"}),
        json!({"security":"future-security"}),
        json!({"futureStream":{"secret":"SYNTHETIC"}}),
        json!({"network":"ws","wsSettings":{"host":"proxy.example.invalid","futureWS":true}}),
    ] {
        let doc = roundtrip(&vless(stream));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Unverified);
        assert!(blocked(&doc));
    }
    let doc = roundtrip(&vless(
        json!({"security":"tls","tlsSettings":{"allowInsecure":true}}),
    ));
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Valid);
    assert!(blocked(&doc));
}
