//! Public structural contract tests. All addresses and credentials below are
//! synthetic fixtures; these tests perform no file or network operations.
use serde_json::{Value, json};
use swirl_subscription::xray::{
    Diagnostic, InputSource, MAX_JSON_DEPTH, MAX_JSON_DIAGNOSTICS, MAX_JSON_INPUT, MAX_JSON_NODES,
    MAX_JSON_VALUES, ParsedDocument, parse_document, parse_document_with_source,
};

fn parse(value: &Value) -> Result<ParsedDocument, Diagnostic> {
    parse_document(&serde_json::to_vec(value).unwrap())
}

fn rejected(value: &Value, code: &str, path: &str) {
    let error = parse(value).unwrap_err();
    assert_eq!(error.code, code);
    assert_eq!(error.path, path);
}

fn client() -> Value {
    json!({
        "tag":"synthetic-client", "protocol":"vless",
        "settings":{"vnext":[{"address":"proxy.example.invalid","port":443,
            "users":[{"id":"00000000-0000-4000-8000-000000000001","encryption":"none"}]}]},
        "streamSettings":{"network":"tcp","security":"tls",
            "tlsSettings":{"serverName":"proxy.example.invalid","allowInsecure":false,
                "alpn":["h2","http/1.1"]}}
    })
}

#[test]
fn official_style_xray_full_configuration_preserves_every_section() {
    let proxy = client();
    let source = json!({
        "log":{"loglevel":"warning"},
        "dns":{"servers":["localhost"]},
        "inbounds":[{"tag":"local","listen":"127.0.0.1","port":1080,
            "protocol":"socks","settings":{"auth":"noauth","udp":true}}],
        "outbounds":[proxy.clone(),{"tag":"direct","protocol":"freedom","settings":{}}],
        "routing":{"domainStrategy":"AsIs","rules":[{"type":"field",
            "domain":["domain:example.invalid"],"outboundTag":"direct"}]},
        "policy":{"levels":{"0":{"handshake":4}}},
        "transport":{},
        "stats":{}
    });
    let bytes = serde_json::to_vec_pretty(&source).unwrap();
    let result = parse_document(&bytes).unwrap();
    assert_eq!(result.input_kind, "configuration");
    assert_eq!(result.configuration, source);
    assert_eq!(result.raw_json(), bytes);
    assert_eq!(result.outbounds.len(), 2);
    assert_eq!(result.outbounds[0], proxy);
    for section in [
        "log",
        "dns",
        "inbounds",
        "outbounds",
        "routing",
        "policy",
        "transport",
        "stats",
    ] {
        assert!(result.global_sections.contains(&section));
    }
    for section in ["log", "dns", "routing", "policy", "transport", "stats"] {
        assert!(
            result
                .diagnostics
                .iter()
                .any(|d| d.path == section && d.severity == "unsupported")
        );
    }
}

#[test]
fn official_style_v2ray_configuration_keeps_global_transport_and_all_users() {
    let source = json!({
        "log":{"loglevel":"error"}, "dns":{"servers":["localhost"]},
        "inbounds":[{"protocol":"socks","port":"1080-1081","settings":{"auth":"noauth"}}],
        "outbounds":[{"protocol":"vmess","settings":{"vnext":[{
            "address":"vmess.example.invalid","port":443,"users":[
                {"id":"00000000-0000-4000-8000-000000000001","alterId":0,"security":"auto"},
                {"id":"00000000-0000-4000-8000-000000000002","alterId":0,"level":1}]}]},
            "streamSettings":{"network":"grpc","security":"tls",
                "grpcSettings":{"serviceName":"synthetic","idle_timeout":-1,
                    "health_check_timeout":-1,"initial_windows_size":-1,"permit_without_stream":false},
                "tlsSettings":{"serverName":"vmess.example.invalid","alpn":"h2"}}}],
        "routing":{"domainStrategy":"IPIfNonMatch","rules":[]},
        "policy":{"system":{"statsOutboundUplink":true}},
        "transport":{"wsSettings":{"path":"/global","headers":{"Host":"global.example.invalid"}}},
        "stats":{}
    });
    let result = parse(&source).unwrap();
    assert_eq!(result.configuration, source);
    assert_eq!(
        result.outbounds[0]["settings"]["vnext"][0]["users"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
    assert_eq!(result.global_transport.as_ref(), source.get("transport"));
    assert_eq!(result.configuration["inbounds"][0]["port"], "1080-1081");
}

#[test]
fn single_multi_and_extension_envelopes_preserve_order() {
    let first = client();
    let second = json!({"protocol":"trojan","settings":{
        "address":"trojan.example.invalid","port":443,"password":"SYNTHETIC_PASSWORD"}});
    assert_eq!(parse(&first).unwrap().input_kind, "outbound");
    let nodes = vec![first, second];
    let full = parse(&json!({"outbounds":nodes})).unwrap();
    assert_eq!(full.input_kind, "configuration");
    assert_eq!(full.outbounds, nodes);
    let extension = parse(&json!(nodes)).unwrap();
    assert_eq!(extension.input_kind, "swirl-outbound-array");
    assert_eq!(extension.outbounds, nodes);
    assert!(
        extension
            .diagnostics
            .iter()
            .any(|d| d.code == "SwirlOutboundArrayExtension")
    );
}

#[test]
fn empty_or_absent_outbounds_never_fall_back_to_server_inbounds() {
    for source in [
        json!([]),
        json!({"outbounds":[]}),
        json!({"inbounds":[client()],"outbounds":[]}),
    ] {
        assert_eq!(parse(&source).unwrap_err().code, "EmptyOutbounds");
    }
    for source in [
        json!({}),
        json!({"inbounds":[client()]}),
        json!({"inbound":client()}),
    ] {
        rejected(&source, "MissingClientOutbounds", "outbounds");
    }
    rejected(&json!({"outbounds":null}), "ExpectedArray", "outbounds");
    rejected(&json!({"outbounds":false}), "ExpectedArray", "outbounds");
    rejected(&json!({"outbounds":""}), "ExpectedArray", "outbounds");
}

#[test]
fn server_markers_are_rejected_in_every_client_envelope() {
    for marker in [
        json!({"listen":"0.0.0.0"}),
        json!({"port":443}),
        json!({"sniffing":{}}),
        json!({"allocate":{}}),
        json!({"settings":{"clients":[]}}),
    ] {
        let mut node = json!({"protocol":"vless"});
        node.as_object_mut()
            .unwrap()
            .extend(marker.as_object().unwrap().clone());
        for (source, path) in [
            (node.clone(), ""),
            (json!([node.clone()]), "[0]"),
            (json!({"outbounds":[node]}), "outbounds[0]"),
        ] {
            rejected(&source, "InboundIsNotClientOutbound", path);
        }
    }
    let source = json!({"inbounds":[{"protocol":"vless","port":443,
        "settings":{"clients":[{"id":"SYNTHETIC_SERVER_ID"}]}}],"outbounds":[client()]});
    assert_eq!(parse(&source).unwrap().outbounds, vec![client()]);
}

#[test]
fn nested_structural_errors_have_exact_outbound_and_user_paths() {
    let source = json!({"outbounds":[client(),client(),{"protocol":"vmess",
        "settings":{"vnext":[{"users":[false]}]}}]});
    rejected(
        &source,
        "ExpectedObject",
        "outbounds[2].settings.vnext[0].users[0]",
    );
    let source = json!({"outbounds":[client(),{"protocol":"vless",
        "streamSettings":{"grpcSettings":false}}]});
    rejected(
        &source,
        "ExpectedObject",
        "outbounds[1].streamSettings.grpcSettings",
    );
    for (settings, path, code) in [
        (json!({"vnext":false}), "settings.vnext", "ExpectedArray"),
        (
            json!({"vnext":[null]}),
            "settings.vnext[0]",
            "ExpectedObject",
        ),
        (
            json!({"vnext":[{"users":{}}]}),
            "settings.vnext[0].users",
            "ExpectedArray",
        ),
        (
            json!({"servers":[{"users":[[]]}]}),
            "settings.servers[0].users[0]",
            "ExpectedObject",
        ),
    ] {
        rejected(&json!({"protocol":"vless","settings":settings}), code, path);
    }
}

#[test]
fn required_protocol_distinguishes_missing_wrong_type_and_empty() {
    rejected(&json!([{}]), "MissingProtocol", "[0].protocol");
    for value in [Value::Null, json!(false), json!(0), json!([]), json!({})] {
        rejected(
            &json!({"protocol":value}),
            "ProtocolMustBeString",
            "protocol",
        );
    }
    for value in ["", " \r\n\t"] {
        rejected(&json!({"protocol":value}), "EmptyProtocol", "protocol");
    }
}

#[test]
fn optional_values_remain_distinct_without_invented_defaults() {
    let source = json!({"protocol":"vless","tag":"","mux":{"enabled":false},
        "settings":{"id":"","port":0},"extra":{"null":null,"false":false,"empty":""}});
    let result = parse(&source).unwrap();
    assert_eq!(result.configuration, source);
    assert!(result.configuration.get("streamSettings").is_none());
    assert!(result.configuration["extra"]["null"].is_null());
    assert_eq!(result.configuration["extra"]["false"], false);
    assert_eq!(result.configuration["extra"]["empty"], "");
    assert!(parse(&json!({"protocol":"vless"})).is_ok());
    for invalid in [Value::Null, json!(false), json!("")] {
        rejected(
            &json!({"protocol":"vless","settings":invalid}),
            "ExpectedObject",
            "settings",
        );
    }
}

#[test]
fn scalar_roots_and_nonobject_array_members_are_rejected() {
    for source in [
        Value::Null,
        json!(false),
        json!(true),
        json!(0),
        json!(1.5),
        json!(""),
    ] {
        rejected(&source, "ExpectedConfigurationObjectOrArray", "");
    }
    for member in [
        Value::Null,
        json!(false),
        json!(4),
        json!("node"),
        json!([]),
    ] {
        rejected(&json!([client(), member.clone()]), "ExpectedObject", "[1]");
        rejected(
            &json!({"outbounds":[client(),member]}),
            "ExpectedObject",
            "outbounds[1]",
        );
    }
    rejected(
        &json!({"inbounds":[false],"outbounds":[client()]}),
        "ExpectedObject",
        "inbounds[0]",
    );
}

#[test]
fn malformed_json_is_not_repaired_or_treated_as_yaml() {
    for input in [
        "{protocol: http}",
        "{'protocol':'http'}",
        "{\"protocol\":\"http\",}",
        "//comment\n{\"protocol\":\"http\"}",
        "{\"protocol\":\"http\"}{}",
        "{\"protocol\":\"http\",\"x\":NaN}",
        "{\"protocol\":\"http\",\"x\":01}",
        "{\"protocol\":\"http\",\"x\":\"\\ud800\"}",
    ] {
        assert_eq!(
            parse_document(input.as_bytes()).unwrap_err().code,
            "JsonSyntax"
        );
    }
    let error = parse_document(b"{\n\"outbounds\": [{\"protocol\": }]\n}").unwrap_err();
    assert_eq!(error.path, "outbounds[0].protocol");
    assert_eq!(error.line, Some(2));
    assert!(error.column.is_some_and(|column| column > 0));
}

#[test]
fn duplicate_keys_are_detected_after_escape_decoding_at_all_depths() {
    for (bytes, path) in [
        (br#"{"protocol":"http","pro\u0074ocol":"socks"}"#.as_slice(), "protocol"),
        (br#"{"outbounds":[{"protocol":"vless","settings":{"vnext":[{"users":[{"id":"SYNTHETIC_ONE","\u0069d":"SYNTHETIC_TWO"}]}]}}]}"#.as_slice(),
            "outbounds[0].settings.vnext[0].users[0].id"),
        (br#"{"protocol":"http","extra":{"a":1,"\u0061":2}}"#.as_slice(), "extra.[unknown]"),
    ] {
        let error = parse_document(bytes).unwrap_err();
        assert_eq!(error.code, "DuplicateJsonKey");
        assert_eq!(error.path, path);
        assert!(error.line.is_some());
        assert!(!format!("{error:?}").contains("SYNTHETIC_"));
    }
}

#[test]
fn empty_files_and_invalid_encodings_have_explicit_errors() {
    for input in [
        b"".as_slice(),
        b" \r\n\t",
        b"\xef\xbb\xbf",
        b"\xef\xbb\xbf\r\n ",
    ] {
        assert_eq!(parse_document(input).unwrap_err().code, "EmptyJsonInput");
    }
    for input in [
        b"\xff".as_slice(),
        b"\xff\xfe{\0}\0",
        b"{\"protocol\":\"http\",\"x\":\"\xc0\xaf\"}",
        b"{\"protocol\":\"http\",\"x\":\"\xed\xa0\x80\"}",
        b"\xf0\x9f\x92",
    ] {
        assert_eq!(parse_document(input).unwrap_err().code, "InvalidUtf8");
    }
    assert_eq!(
        parse_document(b"\xef\xbb\xbf\xef\xbb\xbf{}")
            .unwrap_err()
            .code,
        "JsonSyntax"
    );
}

#[test]
fn original_bytes_keep_numeric_lexemes_order_whitespace_and_bom() {
    let source = b"\xef\xbb\xbf{\n  \"protocol\": \"http\",\n  \"opaque\": [18446744073709551617, -9223372036854775809, 0.123456789012345678901234567890, -0.0, 1e+03]\n}\r\n";
    let result = parse_document(source).unwrap();
    assert_eq!(result.raw_json(), source);
    assert!(result.configuration["opaque"].is_array());
    // The parsed numeric view is not the source of truth for a later lossless
    // serializer: byte preservation is the guarantee this assertion exercises.
}

#[test]
fn caller_provenance_is_preserved_without_urls_or_paths() {
    let input = br#"{"protocol":"http"}"#;
    assert_eq!(parse_document(input).unwrap().source, InputSource::Unknown);
    for source in [
        InputSource::File,
        InputSource::Clipboard,
        InputSource::Subscription,
    ] {
        let result = parse_document_with_source(input, source).unwrap();
        assert_eq!(result.source, source);
        assert_eq!(result.raw_json(), input);
    }
}

#[test]
fn string_list_fields_accept_both_upstream_forms_without_normalizing() {
    for list in [json!("h2,http/1.1"), json!(["h2", "http/1.1"]), json!([])] {
        let source = json!({"protocol":"vmess","streamSettings":{
            "tlsSettings":{"alpn":list}, "httpSettings":{"host":list,"headers":{"X-Synthetic":list}}}});
        assert_eq!(parse(&source).unwrap().configuration, source);
    }
    rejected(
        &json!({"protocol":"vmess","streamSettings":{"tlsSettings":{"alpn":["h2",false]}}}),
        "ExpectedString",
        "streamSettings.tlsSettings.alpn[1]",
    );
    rejected(
        &json!({"protocol":"vmess","streamSettings":{"httpSettings":{"host":false}}}),
        "ExpectedStringOrStringArray",
        "streamSettings.httpSettings.host",
    );
}

#[test]
fn grpc_signed_integer_types_remain_distinct_from_unsigned_ports() {
    for timeout in [i32::MIN, -1, 0, i32::MAX] {
        let source = json!({"protocol":"vless","streamSettings":{"grpcSettings":{
            "idle_timeout":timeout,"health_check_timeout":timeout,"initial_windows_size":timeout}}});
        assert_eq!(parse(&source).unwrap().configuration, source);
    }
    for value in [
        json!(i64::from(i32::MAX) + 1),
        json!(i64::from(i32::MIN) - 1),
        json!(1.5),
        json!("1"),
        Value::Null,
    ] {
        rejected(
            &json!({"protocol":"vless","streamSettings":{"grpcSettings":{"idle_timeout":value}}}),
            "ExpectedSigned32BitInteger",
            "streamSettings.grpcSettings.idle_timeout",
        );
    }
}

#[test]
fn outbound_port_types_follow_uint16_and_preserve_flat_settings() {
    for protocol in ["vmess", "vless", "trojan", "http", "socks", "shadowsocks"] {
        for port in [0, 443, 65535] {
            let source = json!({"protocol":protocol,"settings":{"address":"proxy.example.invalid","port":port}});
            assert_eq!(parse(&source).unwrap().configuration, source);
        }
        for port in [
            json!(-1),
            json!(65536),
            json!(443.0),
            json!("443"),
            json!(false),
            Value::Null,
        ] {
            rejected(
                &json!({"protocol":protocol,"settings":{"port":port}}),
                "ExpectedUnsigned16BitInteger",
                "settings.port",
            );
        }
    }
    rejected(
        &json!({"protocol":"vless","settings":{"vnext":[{"port":"443"}]}}),
        "ExpectedUnsigned16BitInteger",
        "settings.vnext[0].port",
    );
    rejected(
        &json!({"protocol":"trojan","settings":{"servers":[{"port":65536}]}}),
        "ExpectedUnsigned16BitInteger",
        "settings.servers[0].port",
    );
}

#[test]
fn byte_budget_accepts_exact_limit_and_rejects_one_more_before_decode() {
    let prefix = br#"{"protocol":"http","opaque":""#;
    let suffix = br#""}"#;
    let mut source = Vec::with_capacity(MAX_JSON_INPUT + 1);
    source.extend_from_slice(prefix);
    source.resize(MAX_JSON_INPUT - suffix.len(), b'x');
    source.extend_from_slice(suffix);
    assert_eq!(source.len(), MAX_JSON_INPUT);
    assert_eq!(parse_document(&source).unwrap().raw_json(), source);
    source.push(0xff);
    assert_eq!(parse_document(&source).unwrap_err().code, "JsonInputSize");
}

#[test]
fn depth_budget_counts_root_as_zero_and_checks_unknown_values() {
    fn document(array_count: usize) -> String {
        format!(
            "{{\"protocol\":\"http\",\"opaque\":{}0{}}}",
            "[".repeat(array_count),
            "]".repeat(array_count)
        )
    }
    assert!(parse_document(document(MAX_JSON_DEPTH - 1).as_bytes()).is_ok());
    let error = parse_document(document(MAX_JSON_DEPTH).as_bytes()).unwrap_err();
    assert_eq!(error.code, "JsonDepthLimit");
    assert!(error.path.starts_with("[unknown][0]"));
}

#[test]
fn value_budget_accepts_exact_limit_and_rejects_one_more() {
    // Root object + protocol string + opaque array account for three values.
    let source = json!({"protocol":"http","opaque":vec![false; MAX_JSON_VALUES - 3]});
    assert!(parse(&source).is_ok());
    let source = json!({"protocol":"http","opaque":vec![false; MAX_JSON_VALUES - 2]});
    assert_eq!(parse(&source).unwrap_err().code, "JsonValueLimit");
}

#[test]
fn diagnostic_budget_bounds_unrecognized_global_fields() {
    let mut source = json!({"outbounds":[client()]});
    for index in 0..MAX_JSON_DIAGNOSTICS {
        source[format!("synthetic-extra-{index}")] = Value::Null;
    }
    let result = parse(&source).unwrap();
    assert_eq!(result.diagnostics.len(), MAX_JSON_DIAGNOSTICS);
    source["one-more"] = Value::Null;
    assert_eq!(parse(&source).unwrap_err().code, "DiagnosticLimit");
}

#[test]
fn diagnostics_never_echo_credentials_header_values_or_private_urls() {
    const SECRETS: &[&str] = &[
        "00000000-0000-4000-8000-000000000099",
        "SYNTHETIC_PASSWORD",
        "SYNTHETIC_SUBSCRIPTION_TOKEN",
        "Bearer SYNTHETIC_AUTHORIZATION",
        "https://synthetic-user:synthetic-pass@subscription.example.invalid/private?token=SYNTHETIC_URL_TOKEN",
    ];
    for secret in SECRETS {
        let source = json!({"protocol":"vless","settings":{"id":SECRETS[0],"password":SECRETS[1]},
            "streamSettings":{"wsSettings":{"headers":{"Authorization":{*secret:secret}}}}});
        let error = parse(&source).unwrap_err();
        let printable = format!(
            "{error} {error:?} {}",
            serde_json::to_string(&error).unwrap()
        );
        assert_eq!(error.path, "streamSettings.wsSettings.headers.[unknown]");
        for secret in SECRETS {
            assert!(!printable.contains(secret));
        }
        let quoted = serde_json::to_string(secret).unwrap();
        let duplicate = format!("{{\"protocol\":\"http\",{quoted}:0,{quoted}:1}}");
        let error = parse_document(duplicate.as_bytes()).unwrap_err();
        assert_eq!(error.code, "DuplicateJsonKey");
        assert_eq!(error.path, "[unknown]");
        assert!(!format!("{error} {error:?}").contains(secret));
    }
    let source = json!({"outbounds":[{"protocol":"http","settings":{"password":SECRETS[1]}}],
        SECRETS[4]:{"Authorization":SECRETS[3]}});
    let result = parse(&source).unwrap();
    let printable = format!("{result:?}");
    for secret in SECRETS {
        assert!(!printable.contains(secret));
    }
}

#[test]
fn v2ray_v5_envelopes_are_retained_without_claiming_conversion() {
    let source = json!({"log":{},"dns":{},"router":{},"services":{},"extension":[],"inbounds":[],
        "outbounds":[{"protocol":"vmess","settings":{},"streamSettings":{
            "transport":"grpc","transportSettings":{"serviceName":"synthetic"},
            "security":"tls","securitySettings":{"serverName":"example.invalid"},"socketSettings":{}}}]});
    let result = parse(&source).unwrap();
    assert_eq!(result.configuration, source);
    for section in ["router", "services", "extension"] {
        assert!(result.global_sections.contains(&section));
    }
}

#[test]
fn legacy_v2ray_envelopes_preserve_source_paths_and_upstream_order() {
    let first = json!({"protocol":"http","tag":"first"});
    let second = json!({"protocol":"socks","tag":"second"});
    let third = json!({"protocol":"vless","tag":"third"});
    let legacy = json!({"outbound":first,"outboundDetour":[second]});
    let result = parse(&legacy).unwrap();
    assert_eq!(result.outbounds, vec![first.clone(), second.clone()]);
    assert_eq!(result.outbound_paths, vec!["outbound", "outboundDetour[0]"]);
    assert_eq!(result.configuration, legacy);
    let mixed = json!({"outbounds":[third],"outboundDetour":[second],"outbound":first,
        "inbound":{"protocol":"vless","port":443,"settings":{"clients":[]}}});
    let result = parse(&mixed).unwrap();
    assert_eq!(result.outbounds, vec![first, second, third]);
    assert_eq!(
        result.outbound_paths,
        vec!["outbound", "outboundDetour[0]", "outbounds[0]"]
    );
    assert_eq!(result.configuration, mixed);
    rejected(
        &json!({"outboundDetour":[{"protocol":"vmess","settings":{"vnext":[{"users":[false]}]}}]}),
        "ExpectedObject",
        "outboundDetour[0].settings.vnext[0].users[0]",
    );
    let at_limit = json!({"outbound":{"protocol":"http"},
        "outboundDetour":vec![json!({"protocol":"http"});MAX_JSON_NODES-1]});
    assert_eq!(parse(&at_limit).unwrap().outbounds.len(), MAX_JSON_NODES);
    let mut over_limit = at_limit;
    over_limit["outbounds"] = json!([{"protocol":"http"}]);
    assert_eq!(parse(&over_limit).unwrap_err().code, "NodeCountLimit");
}

#[test]
fn recognized_global_and_inbound_children_are_typed_without_execution() {
    for (section, value, code, path) in [
        (
            "log",
            json!({"loglevel":false}),
            "ExpectedString",
            "log.loglevel",
        ),
        (
            "dns",
            json!({"servers":[false]}),
            "ExpectedObject",
            "dns.servers[0]",
        ),
        (
            "dns",
            json!({"hosts":{"private.example.invalid":false}}),
            "ExpectedStringOrStringArray",
            "dns.hosts.[unknown]",
        ),
        (
            "routing",
            json!({"rules":[null]}),
            "ExpectedObject",
            "routing.rules[0]",
        ),
        (
            "policy",
            json!({"levels":{"private-level":null}}),
            "ExpectedObject",
            "policy.levels.[unknown]",
        ),
    ] {
        let mut source = json!({"outbounds":[client()]});
        source[section] = value;
        rejected(&source, code, path);
    }
    rejected(
        &json!({"inbounds":[{"protocol":"vless","settings":false}],"outbounds":[client()]}),
        "ExpectedObject",
        "inbounds[0].settings",
    );
    rejected(
        &json!({"inbounds":[{"protocol":"http","sniffing":{"enabled":"false"}}],"outbounds":[client()]}),
        "ExpectedBoolean",
        "inbounds[0].sniffing.enabled",
    );
}

#[test]
fn unknown_protocol_fields_are_preserved_for_later_conversion() {
    let source = json!({"protocol":"future-synthetic-protocol","settings":{
        "vnext":false,"private":{"password":"SYNTHETIC_PASSWORD"}},
        "streamSettings":{"network":"future-transport","futureSettings":{"opaque":[null,false,""]}}});
    assert_eq!(parse(&source).unwrap().configuration, source);
}

#[test]
fn truncations_and_small_hostile_byte_corpus_do_not_panic() {
    let bytes = serde_json::to_vec(&client()).unwrap();
    for end in 0..bytes.len() {
        assert!(parse_document(&bytes[..end]).is_err());
    }
    for byte in 0..=u8::MAX {
        let _ = parse_document(&[byte]);
    }
    for index in 0..bytes.len() {
        let mut altered = bytes.clone();
        altered[index] ^= 0x80;
        let _ = parse_document(&altered);
    }
}
