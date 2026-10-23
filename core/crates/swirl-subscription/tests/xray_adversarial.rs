//! Independent boundary tests for the public JSON API. Fixtures are synthetic;
//! no subscription credentials or external network access are used.
use serde_json::{Value, json};
use swirl_subscription::xray::{
    Diagnostic, MAX_JSON_DEPTH, MAX_JSON_INPUT, MAX_JSON_NODES, parse_document,
};

fn rejected(bytes: &[u8]) -> Diagnostic {
    match parse_document(bytes) {
        Ok(_) => panic!("invalid JSON input was accepted"),
        Err(error) => error,
    }
}

fn outbound() -> Value {
    json!({"protocol":"http","settings":{"servers":[{"address":"proxy.example.invalid","port":8080}]}})
}

#[test]
fn duplicate_keys_in_nonexecuted_sections_are_still_rejected() {
    // Duplicate keys cannot be hidden in server inbounds, routing or unused
    // metadata merely because only client outbounds are extracted.
    for bytes in [
        br#"{"outbounds":[{"protocol":"http"}],"inbounds":[{"settings":{"clients":[{"id":"FAKE_FIRST","\u0069d":"FAKE_SECOND"}]}}]}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http"}],"routing":{"rules":[{"password":"FAKE_FIRST","password":"FAKE_SECOND"}]}}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http"}],"FAKE_PRIVATE_TOKEN":{"secret":0,"\u0073ecret":1}}"#.as_slice(),
    ] {
        let error = rejected(bytes);
        assert_eq!(error.code, "DuplicateJsonKey");
        let diagnostic = serde_json::to_string(&error).unwrap();
        assert!(!diagnostic.contains("FAKE_"));
        assert!(!diagnostic.contains("secret"));
    }
}

#[test]
fn escaped_non_ascii_duplicate_keys_are_compared_after_decoding() {
    let bytes = "{\"outbounds\":[{\"protocol\":\"http\"}],\"🔑FAKE_SECRET\":0,\"\\ud83d\\udd11FAKE_SECRET\":1}";
    let error = rejected(bytes.as_bytes());
    assert_eq!(error.code, "DuplicateJsonKey");
    assert_eq!(error.path, "[unknown]");
    assert!(
        !serde_json::to_string(&error)
            .unwrap()
            .contains("FAKE_SECRET")
    );
}

#[test]
fn malformed_input_reports_schema_paths_without_values_or_unknown_keys() {
    for bytes in [
        br#"{"outbounds":[{"protocol":"http","settings":{"password":"FAKE_PASSWORD", "FAKE_TOKEN.with.path\n":}}]}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http","streamSettings":{"wsSettings":{"headers":{"FAKE_TOKEN":"\ud800"}}}}]}"#.as_slice(),
    ] {
        let error = rejected(bytes);
        assert_eq!(error.code, "JsonSyntax");
        let serialized = serde_json::to_string(&error).unwrap();
        assert!(!serialized.contains("FAKE_"));
        assert!(!error.path.contains('\n'));
        assert!(error.path.len() < 512);
    }
}

#[test]
fn json_extensions_cannot_pass_through_the_structural_entrypoint() {
    for bytes in [
        br#"{outbounds: [{protocol: http}]}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http"}],/*comment*/"log":{}}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http"}],"value":01}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http"}],"value":+1}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http"}],"value":Infinity}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http"}],"value":1e999}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http"}],}"#.as_slice(),
        br#"{"outbounds":[{"protocol":"http"}]}{}"#.as_slice(),
    ] {
        assert_eq!(rejected(bytes).code, "JsonSyntax");
    }
}

#[test]
fn unknown_source_values_remain_distinct_and_diagnostics_redact_their_names() {
    let source = json!({
        "outbounds":[outbound()],
        "FAKE_SECRET_METADATA":{
            "null":null,"false":false,"empty":"","array":[],"object":{},
            "integer":9007199254740993_u64,"negative":-7,"decimal":1.25
        }
    });
    let parsed = parse_document(&serde_json::to_vec(&source).unwrap()).unwrap();
    assert_eq!(parsed.configuration, source);
    let extra = &parsed.configuration["FAKE_SECRET_METADATA"];
    assert!(extra.get("missing").is_none());
    assert!(extra["null"].is_null());
    assert_eq!(extra["false"], false);
    assert_eq!(extra["empty"], "");
    assert_eq!(extra["integer"].as_u64(), Some(9007199254740993));
    let diagnostics = serde_json::to_string(&parsed.diagnostics).unwrap();
    assert!(!diagnostics.contains("FAKE_SECRET_METADATA"));
    assert!(diagnostics.contains("UnknownGlobalFieldPreserved"));
}

#[test]
fn inbound_credentials_never_become_client_outbounds() {
    let client = outbound();
    let source = json!({
        "inbounds":[{"protocol":"vless","listen":"127.0.0.1","port":1080,
            "settings":{"clients":[{"id":"00000000-0000-4000-8000-000000000001"}]}}],
        "outbounds":[client.clone()]
    });
    let parsed = parse_document(&serde_json::to_vec(&source).unwrap()).unwrap();
    assert_eq!(parsed.outbounds, vec![client]);
    assert_eq!(parsed.configuration, source);
    assert!(
        parsed
            .diagnostics
            .iter()
            .any(|d| d.code == "ServerInboundsPreservedNotImported")
    );
}

#[test]
fn invalid_global_and_outbound_section_types_do_not_normalize_to_defaults() {
    for bad in [Value::Null, json!(false), json!(""), json!([]), json!(0)] {
        for key in ["log", "dns", "routing", "policy", "transport", "stats"] {
            let mut source = json!({"outbounds":[outbound()]});
            source[key] = bad.clone();
            let error = rejected(&serde_json::to_vec(&source).unwrap());
            assert_eq!(error.code, "ExpectedObject");
            assert_eq!(error.path, key);
        }
        for key in ["settings", "streamSettings", "mux", "proxySettings"] {
            let mut source = outbound();
            source[key] = bad.clone();
            let error = rejected(&serde_json::to_vec(&source).unwrap());
            assert_eq!(error.code, "ExpectedObject");
            assert_eq!(error.path, key);
        }
    }
}

#[test]
fn depth_budget_applies_inside_unknown_metadata_before_projection() {
    let mut nested = json!("FAKE_SECRET_VALUE");
    for _ in 0..=MAX_JSON_DEPTH {
        nested = json!({"FAKE_SECRET_KEY":nested});
    }
    let source = json!({"outbounds":[outbound()],"FAKE_PRIVATE_METADATA":nested});
    let error = rejected(&serde_json::to_vec(&source).unwrap());
    assert_eq!(error.code, "JsonDepthLimit");
    assert!(!serde_json::to_string(&error).unwrap().contains("FAKE_"));
}

#[test]
fn value_budget_applies_to_large_unselected_arrays() {
    let source = json!({"outbounds":[outbound()],"unused":vec![false;100_001]});
    let bytes = serde_json::to_vec(&source).unwrap();
    assert!(bytes.len() < MAX_JSON_INPUT);
    assert_eq!(rejected(&bytes).code, "JsonValueLimit");
}

#[test]
fn outbound_count_boundary_is_enforced_for_full_and_extension_documents() {
    let nodes = vec![json!({"protocol":"http"}); MAX_JSON_NODES];
    assert!(parse_document(&serde_json::to_vec(&nodes).unwrap()).is_ok());
    let mut too_many = nodes;
    too_many.push(json!({"protocol":"http"}));
    for source in [json!(too_many), json!({"outbounds":too_many})] {
        assert_eq!(
            rejected(&serde_json::to_vec(&source).unwrap()).code,
            "NodeCountLimit"
        );
    }
}

#[test]
fn file_bom_is_accepted_but_size_and_encoding_limits_are_not_bypassed() {
    let mut file = vec![0xef, 0xbb, 0xbf];
    file.extend_from_slice(&serde_json::to_vec(&outbound()).unwrap());
    assert!(parse_document(&file).is_ok());
    file.resize(MAX_JSON_INPUT + 1, b' ');
    assert_eq!(rejected(&file).code, "JsonInputSize");
    assert_eq!(
        rejected(&[0xff, 0xfe, b'{', 0, b'}', 0]).code,
        "InvalidUtf8"
    );
}
