//! Public conversion tests. All endpoints and credentials are synthetic.
use serde_json::{Value, json};
use swirl_subscription::xray::convert::{
    Authentication, ConvertedDocument, MAX_EXPANDED_NODES, Protocol, Security, Transport,
    ValidationStatus, convert_document, import_document,
};
use swirl_subscription::xray::{InputSource, parse_document};

const ID1: &str = "00000000-0000-4000-8000-000000000001";
const ID2: &str = "00000000-0000-4000-8000-000000000002";
fn vless() -> Value {
    json!({"protocol":"vless","settings":{"address":"proxy.example.invalid","port":443,
        "id":ID1,"encryption":"none"}})
}
fn import(value: &Value) -> ConvertedDocument {
    import_document(&serde_json::to_vec(value).unwrap(), InputSource::File).unwrap()
}
fn roundtrip(value: &Value) -> ConvertedDocument {
    let first = import(value);
    let restored = ConvertedDocument::restore(&first.save().unwrap()).unwrap();
    assert_eq!(first.raw_json(), restored.raw_json());
    assert_eq!(first.source(), restored.source());
    assert_eq!(first.nodes().len(), restored.nodes().len());
    for (a, b) in first.nodes().iter().zip(restored.nodes()) {
        assert_eq!(a.protocol(), b.protocol());
        assert!(a.endpoint() == b.endpoint());
        assert!(a.authentication() == b.authentication());
        assert_eq!(a.source(), b.source());
        assert_eq!(a.transport(), b.transport());
        assert_eq!(a.security(), b.security());
        assert_eq!(a.validation(), b.validation());
        assert_eq!(a.diagnostics(), b.diagnostics());
        assert!(!b.network_verified());
    }
    restored
}
#[test]
fn vless_flat_roundtrip_preserves_required_fields_and_missing_optional_fields() {
    let source = vless();
    let doc = roundtrip(&source);
    let n = &doc.nodes()[0];
    assert_eq!(n.protocol(), Protocol::Vless);
    assert_eq!(n.validation(), ValidationStatus::Valid);
    assert!(
        matches!(n.authentication(), Authentication::Vless { id: Some(id), encryption: Some(e), flow: None, level: None, email: None } if id == ID1 && e == "none")
    );
    assert_eq!(n.transport(), Transport::Tcp);
    assert_eq!(n.security(), Security::None);
    assert!(doc.stream_settings(0).is_none());
    assert_eq!(doc.configuration(), &source);
}
#[test]
fn multiple_servers_expand_only_their_own_users_in_original_order() {
    let source = json!({"outbounds":[{"protocol":"vless","settings":{"vnext":[
        {"address":"one.example.invalid","port":443,"users":[{"id":ID1,"encryption":"none"},{"id":ID2,"encryption":"none"}]},
        {"address":"two.example.invalid","port":8443,"users":[{"id":ID2,"encryption":"none"}]}]}}]});
    let doc = roundtrip(&source);
    assert_eq!(doc.nodes().len(), 3);
    for (n, (s, u, host, port)) in doc.nodes().iter().zip([
        (0, 0, "one.example.invalid", 443),
        (0, 1, "one.example.invalid", 443),
        (1, 0, "two.example.invalid", 8443),
    ]) {
        assert_eq!(n.source().server_index, Some(s));
        assert_eq!(n.source().user_index, Some(u));
        assert_eq!(n.source().outbound_path, "outbounds[0]");
        assert_eq!(
            n.source().user_path.as_deref(),
            Some(format!("outbounds[0].settings.vnext[{s}].users[{u}]").as_str())
        );
        assert!(
            n.endpoint()
                .is_some_and(|e| e.address == host && e.port == port)
        );
    }
}
#[test]
fn vmess_legacy_alter_id_cipher_and_protocol_never_change() {
    let source = json!({"protocol":"vmess","settings":{"vnext":[{"address":"vm.example.invalid","port":80,
        "users":[{"id":ID1,"alterId":64,"security":"none","level":0}]}]}});
    let doc = roundtrip(&source);
    let n = &doc.nodes()[0];
    assert_eq!(n.protocol(), Protocol::Vmess);
    assert!(
        matches!(n.authentication(), Authentication::Vmess { alter_id: Some(64), security: Some(s), .. } if s == "none")
    );
    assert!(
        n.diagnostics()
            .iter()
            .any(|d| d.code == "VmessLegacyAlterIdUnsupported")
    );
    assert!(
        n.diagnostics()
            .iter()
            .any(|d| d.code == "VmessNativeOutboundUnavailable")
    );
}
#[test]
fn vmess_known_and_unknown_ciphers_are_preserved_without_fallback() {
    for cipher in [
        "auto",
        "aes-128-gcm",
        "chacha20-poly1305",
        "none",
        "zero",
        "aes-128-cfb",
        "future-cipher",
    ] {
        let source = json!({"protocol":"vmess","settings":{"address":"vm.example.invalid","port":443,
            "id":ID1,"alterId":0,"security":cipher}});
        let doc = roundtrip(&source);
        assert!(
            matches!(doc.nodes()[0].authentication(), Authentication::Vmess { alter_id: Some(0), security: Some(s), .. } if s == cipher)
        );
        assert_eq!(doc.nodes()[0].protocol(), Protocol::Vmess);
    }
}
#[test]
fn security_transport_mux_and_unknown_parameters_survive_archive() {
    let mut source = vless();
    source["settings"]["flow"] = json!("xtls-rprx-vision");
    source["streamSettings"] = json!({"network":"raw","security":"reality","realitySettings":{
        "publicKey":"SYNTHETIC_PUBLIC_KEY","shortId":"aabb","serverName":"sni.example.invalid",
        "fingerprint":"chrome","spiderX":"/private-path","show":false,"futureOption":{"token":"SYNTHETIC_TOKEN"}}});
    source["mux"] = json!({"enabled":true,"concurrency":8});
    let doc = roundtrip(&source);
    assert_eq!(doc.stream_settings(0), source.get("streamSettings"));
    assert_eq!(doc.mux(0), source.get("mux"));
    assert_eq!(doc.nodes()[0].security(), Security::Reality);
    assert!(
        matches!(doc.nodes()[0].authentication(), Authentication::Vless { flow: Some(s), .. } if s == "xtls-rprx-vision")
    );
}
#[test]
fn websocket_tls_host_path_headers_and_early_data_are_not_lost() {
    for protocol in ["vless", "vmess"] {
        let mut source = vless();
        source["protocol"] = json!(protocol);
        if protocol == "vmess" {
            source["settings"]
                .as_object_mut()
                .unwrap()
                .remove("encryption");
            source["settings"]["alterId"] = json!(0);
        }
        source["streamSettings"] = json!({"network":"ws","security":"tls",
            "tlsSettings":{"serverName":"tls.example.invalid","allowInsecure":false,"alpn":["http/1.1"]},
            "wsSettings":{"path":"/ws?ed=2048","headers":{"Host":"ws.example.invalid","Authorization":"SYNTHETIC_TOKEN"},
                "maxEarlyData":2048,"earlyDataHeaderName":"Sec-WebSocket-Protocol","acceptProxyProtocol":false}});
        let doc = roundtrip(&source);
        assert_eq!(doc.nodes()[0].transport(), Transport::WebSocket);
        assert_eq!(doc.stream_settings(0), source.get("streamSettings"));
    }
}
#[test]
fn raw_byte_roundtrip_keeps_bom_numbers_key_order_and_unknowns() {
    let bytes = b"\xef\xbb\xbf{\n\"protocol\":\"vless\",\"settings\":{\"address\":\"example.invalid\",\"port\":443,\"id\":\"00000000-0000-4000-8000-000000000001\",\"encryption\":\"none\"},\"opaque\":[18446744073709551617,0.12345678901234567890123456789,-0.0,1e+03]}\r\n";
    let doc = import_document(bytes, InputSource::Subscription).unwrap();
    let restored = ConvertedDocument::restore(&doc.save().unwrap()).unwrap();
    assert_eq!(restored.raw_json(), bytes);
    assert_eq!(restored.source(), InputSource::Subscription);
}
#[test]
fn mutable_parser_views_cannot_forge_conversion_results_or_source_paths() {
    let bytes = serde_json::to_vec(&vless()).unwrap();
    let mut parsed = parse_document(&bytes).unwrap();
    parsed.outbounds[0]["protocol"] = json!("vmess");
    parsed.outbound_paths[0] = "SYNTHETIC_SECRET_PATH".into();
    parsed.configuration = Value::Null;
    let doc = convert_document(&parsed).unwrap();
    assert_eq!(doc.nodes()[0].protocol(), Protocol::Vless);
    assert_eq!(doc.nodes()[0].source().outbound_path, "");
    assert!(!format!("{doc:?}").contains("SYNTHETIC_SECRET_PATH"));
}
#[test]
fn archives_reject_forged_execution_flags_versions_unknowns_and_duplicates() {
    let doc = import(&vless());
    let saved = doc.save().unwrap();
    let mut value: Value = serde_json::from_slice(&saved).unwrap();
    value["executable"] = json!(true);
    assert!(ConvertedDocument::restore(&serde_json::to_vec(&value).unwrap()).is_err());
    value.as_object_mut().unwrap().remove("executable");
    value["schema"] = json!(2);
    assert_eq!(
        ConvertedDocument::restore(&serde_json::to_vec(&value).unwrap())
            .unwrap_err()
            .code,
        "ArchiveVersion"
    );
    let text =
        String::from_utf8(saved)
            .unwrap()
            .replacen("\"schema\":1", "\"schema\":1,\"schema\":1", 1);
    assert_eq!(
        ConvertedDocument::restore(text.as_bytes())
            .unwrap_err()
            .code,
        "ArchiveSyntax"
    );
}
#[test]
fn archive_reload_rechecks_duplicate_keys_inside_the_raw_document() {
    let archive = json!({"schema":1,"source":"file","raw_json":"{\"protocol\":\"http\",\"protocol\":\"socks\"}"});
    assert_eq!(
        ConvertedDocument::restore(&serde_json::to_vec(&archive).unwrap())
            .unwrap_err()
            .code,
        "DuplicateJsonKey"
    );
}
#[test]
fn invalid_uuid_empty_host_zero_port_and_missing_auth_are_diagnosed() {
    for (field, value, code) in [
        (
            "id",
            json!("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"),
            "InvalidUuid",
        ),
        ("address", json!(""), "InvalidServerAddress"),
        ("port", json!(0), "InvalidServerPort"),
        ("encryption", json!(""), "MissingVlessEncryption"),
    ] {
        let mut source = vless();
        source["settings"][field] = value;
        let doc = roundtrip(&source);
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
        assert!(doc.nodes()[0].diagnostics().iter().any(|d| d.code == code));
    }
    let mut source = vless();
    source["settings"].as_object_mut().unwrap().remove("id");
    assert_eq!(
        import(&source).nodes()[0].validation(),
        ValidationStatus::Invalid
    );
}
#[test]
fn malformed_types_and_out_of_range_ports_still_use_the_strict_parser() {
    for value in [
        json!(65536),
        json!(-1),
        json!("443"),
        json!(443.0),
        json!(false),
    ] {
        let mut source = vless();
        source["settings"]["port"] = value;
        assert!(import_document(&serde_json::to_vec(&source).unwrap(), InputSource::File).is_err());
    }
    let mut source = vless();
    source["settings"]["id"] = json!(42);
    assert!(import_document(&serde_json::to_vec(&source).unwrap(), InputSource::File).is_err());
}
#[test]
fn flat_and_array_forms_are_never_silently_prioritized() {
    let mut source = vless();
    source["settings"]["vnext"] = json!([{"address":"other.example.invalid","port":80,"users":[{"id":ID2,"encryption":"none"}]}]);
    let doc = roundtrip(&source);
    assert!(
        doc.nodes()[0]
            .diagnostics()
            .iter()
            .any(|d| d.code == "AmbiguousEndpointForms")
    );
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
}
#[test]
fn expansion_budget_applies_to_accounts_not_only_outbound_count() {
    let user = json!({"id":ID1,"encryption":"none"});
    let mut source = json!({"protocol":"vless","settings":{"vnext":[{"address":"example.invalid","port":443,
        "users":vec![user.clone();MAX_EXPANDED_NODES]}]}});
    assert_eq!(import(&source).nodes().len(), MAX_EXPANDED_NODES);
    source["settings"]["vnext"][0]["users"]
        .as_array_mut()
        .unwrap()
        .push(user);
    assert_eq!(
        import_document(&serde_json::to_vec(&source).unwrap(), InputSource::File)
            .unwrap_err()
            .code,
        "ExpandedNodeLimit"
    );
}
#[test]
fn conversion_diagnostics_are_bounded_and_unknown_keys_are_masked() {
    let mut source = vless();
    for index in 0..65 {
        source["settings"][format!("SYNTHETIC_SECRET_{index}")] = json!(true);
    }
    let err =
        import_document(&serde_json::to_vec(&source).unwrap(), InputSource::File).unwrap_err();
    assert_eq!(err.code, "DiagnosticLimit");
    assert!(!format!("{err:?}").contains("SYNTHETIC_SECRET"));
}
#[test]
fn all_public_debug_views_redact_credentials_and_unknown_names() {
    let mut source = vless();
    source["settings"]["SYNTHETIC_TOKEN"] = json!("SYNTHETIC_PASSWORD");
    let doc = import(&source);
    let node = &doc.nodes()[0];
    let text = format!(
        "{doc:?} {node:?} {:?} {:?} {}",
        node.authentication(),
        node.endpoint(),
        serde_json::to_string(node.diagnostics()).unwrap()
    );
    for secret in [ID1, "SYNTHETIC_TOKEN", "SYNTHETIC_PASSWORD"] {
        assert!(!text.contains(secret));
    }
}
#[test]
fn legacy_envelope_paths_survive_save_reload() {
    let source = json!({"outbound":vless(),"outboundDetour":[vless()],"outbounds":[vless()]});
    let doc = roundtrip(&source);
    assert_eq!(
        doc.nodes()
            .iter()
            .map(|n| n.source().outbound_path.as_str())
            .collect::<Vec<_>>(),
        ["outbound", "outboundDetour[0]", "outbounds[0]"]
    );
}
#[test]
fn short_xray_custom_ids_are_preserved_but_never_pretend_to_be_native_uuids() {
    let mut source = vless();
    source["settings"]["id"] = json!("custom-id");
    let doc = roundtrip(&source);
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Unverified);
    assert!(
        doc.nodes()[0]
            .diagnostics()
            .iter()
            .any(|d| d.code == "CustomIdMappingUnsupported")
    );
    assert!(
        matches!(doc.nodes()[0].authentication(),Authentication::Vless { id: Some(id), .. } if id == "custom-id")
    );
}
