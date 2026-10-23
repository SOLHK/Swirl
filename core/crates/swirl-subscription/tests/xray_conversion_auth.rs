//! B3 account expansion, wire semantics and lossless persistence. Synthetic data.
use serde_json::{Value, json};
use swirl_subscription::xray::{
    InputSource,
    convert::{
        Authentication, ConvertedDocument, Protocol, Security, Transport, ValidationStatus,
        import_document,
    },
};

fn outbound(protocol: &str) -> Value {
    json!({"protocol":protocol,"settings":{"servers":[{"address":"proxy.example.invalid","port":1080}]}})
}
fn parse(value: &Value) -> ConvertedDocument {
    import_document(&serde_json::to_vec(value).unwrap(), InputSource::Clipboard).unwrap()
}
fn roundtrip(value: &Value) -> ConvertedDocument {
    let original = parse(value);
    let restored = ConvertedDocument::restore(&original.save().unwrap()).unwrap();
    assert_eq!(restored.raw_json(), original.raw_json());
    assert_eq!(restored.configuration(), value);
    assert_eq!(restored.source(), InputSource::Clipboard);
    assert_eq!(restored.nodes().len(), original.nodes().len());
    for (before, after) in original.nodes().iter().zip(restored.nodes()) {
        assert_eq!(before.authentication(), after.authentication());
        assert_eq!(before.endpoint(), after.endpoint());
        assert_eq!(before.source(), after.source());
        assert_eq!(before.diagnostics(), after.diagnostics());
        assert_eq!(before.validation(), after.validation());
        assert!(!after.network_verified());
    }
    restored
}
fn issue(doc: &ConvertedDocument, code: &str) -> bool {
    doc.nodes()[0].diagnostics().iter().any(|d| d.code == code)
}

#[test]
fn absent_and_empty_users_are_explicit_unauthenticated_nodes() {
    for protocol in ["socks", "http"] {
        for users in [None, Some(json!([]))] {
            let mut value = outbound(protocol);
            if let Some(users) = users {
                value["settings"]["servers"][0]["users"] = users;
            }
            let doc = roundtrip(&value);
            assert_eq!(doc.nodes().len(), 1);
            assert_eq!(doc.nodes()[0].authentication(), &Authentication::None);
            assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Valid);
            assert!(doc.nodes()[0].diagnostics().is_empty());
        }
    }
}

#[test]
fn every_server_and_account_has_its_original_path_and_no_cross_product() {
    for protocol in ["socks", "http"] {
        let value = json!({"outbounds":[{"protocol":protocol,"settings":{"servers":[
            {"address":"one.example.invalid","port":1080,"users":[
                {"user":"SYNTHETIC_USER_1","pass":"SYNTHETIC_PASS_1","level":0,"email":"one@example.invalid"},
                {"user":"SYNTHETIC_USER_2","pass":"SYNTHETIC_PASS_2","level":0,"email":"two@example.invalid"}]},
            {"address":"two.example.invalid","port":3128,"users":[{"user":"SYNTHETIC_USER_3","pass":"SYNTHETIC_PASS_3"}]},
            {"address":"three.example.invalid","port":8080,"users":[]} ]}}]});
        let doc = roundtrip(&value);
        assert_eq!(doc.nodes().len(), 4);
        for (index, (s, u, port)) in [
            (0, Some(0), 1080),
            (0, Some(1), 1080),
            (1, Some(0), 3128),
            (2, None, 8080),
        ]
        .into_iter()
        .enumerate()
        {
            let node = &doc.nodes()[index];
            assert_eq!(node.source().server_index, Some(s));
            assert_eq!(node.source().user_index, u);
            assert_eq!(
                node.source().server_path,
                format!("outbounds[0].settings.servers[{s}]")
            );
            assert_eq!(node.endpoint().unwrap().port, port);
            assert_eq!(node.validation(), ValidationStatus::Valid);
            assert!(node.diagnostics().is_empty());
            if let Some(u) = u {
                assert_eq!(
                    node.source().user_path,
                    Some(format!("outbounds[0].settings.servers[{s}].users[{u}]"))
                );
                let expected = format!("SYNTHETIC_USER_{}", index + 1);
                assert!(
                    matches!(node.authentication(), Authentication::UserPassword{user:Some(user),pass:Some(_),..} if user==&expected)
                );
            }
        }
    }
}

#[test]
fn current_xray_flat_authentication_is_preserved_without_trimming() {
    for protocol in ["socks", "http"] {
        let value = json!({"protocol":protocol,"settings":{"address":"proxy.example.invalid","port":443,
            "user":" 用户 ","pass":" 密碼🦀 ","email":"metadata@example.invalid","level":0}});
        let doc = roundtrip(&value);
        assert!(
            matches!(doc.nodes()[0].authentication(), Authentication::UserPassword{user:Some(u),pass:Some(p),level:Some(0)} if u==" 用户 " && p==" 密碼🦀 ")
        );
        assert_eq!(doc.nodes()[0].source().server_index, None);
        assert_eq!(doc.nodes()[0].source().user_index, None);
        assert!(doc.nodes()[0].diagnostics().is_empty());
    }
}

#[test]
fn flat_without_credentials_is_unauthenticated_and_preserves_metadata() {
    for protocol in ["socks", "http"] {
        let value = json!({"protocol":protocol,"settings":{"address":"proxy.example.invalid","port":443,
            "email":"metadata@example.invalid","level":0}});
        let doc = roundtrip(&value);
        assert_eq!(doc.nodes()[0].authentication(), &Authentication::None);
        assert!(doc.nodes()[0].diagnostics().is_empty());
    }
}

#[test]
fn tls_and_other_stream_parameters_are_kept_outside_proxy_authentication() {
    for protocol in ["socks", "http"] {
        let mut value = outbound(protocol);
        value["settings"]["servers"][0]["users"] = json!([{"user":"user","pass":"password"}]);
        value["streamSettings"] = json!({"network":"ws","security":"tls","tlsSettings":{
            "serverName":"sni.example.invalid","alpn":["http/1.1"],"allowInsecure":false},
            "wsSettings":{"path":"/proxy","headers":{"Host":"ws.example.invalid"}}});
        let doc = roundtrip(&value);
        assert_eq!(doc.nodes()[0].security(), Security::Tls);
        assert_eq!(doc.nodes()[0].transport(), Transport::WebSocket);
        assert_eq!(doc.stream_settings(0), value.get("streamSettings"));
        assert!(matches!(
            doc.nodes()[0].authentication(),
            Authentication::UserPassword { .. }
        ));
    }
}

#[test]
fn socks4_and_4a_keep_version_userid_and_empty_password() {
    for version in ["4", "4a", "4A"] {
        for password in [None, Some("")] {
            let mut value = outbound("socks");
            value["settings"]["version"] = json!(version);
            let mut account =
                json!({"user":"synthetic-user-id","email":"metadata@example.invalid"});
            if let Some(password) = password {
                account["pass"] = json!(password);
            }
            value["settings"]["servers"][0]["users"] = json!([account]);
            let doc = roundtrip(&value);
            assert_eq!(doc.configuration()["settings"]["version"], json!(version));
            assert_eq!(doc.nodes()[0].protocol(), Protocol::Socks);
            assert!(doc.nodes()[0].diagnostics().is_empty());
        }
    }
}

#[test]
fn socks4_password_and_nul_userid_never_become_socks5_or_noauth() {
    for (account, code) in [
        (
            json!({"user":"user","pass":"password"}),
            "Socks4PasswordUnsupported",
        ),
        (
            json!({"user":"user\u{0000}suffix"}),
            "Socks4UserIdContainsNul",
        ),
    ] {
        let mut value = outbound("socks");
        value["settings"]["version"] = json!("4a");
        value["settings"]["servers"][0]["users"] = json!([account]);
        let doc = roundtrip(&value);
        assert!(issue(&doc, code));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
        assert!(matches!(
            doc.nodes()[0].authentication(),
            Authentication::UserPassword { .. }
        ));
    }
}

#[test]
fn invalid_version_and_version_types_are_diagnosed_without_defaulting() {
    for (version, code) in [
        (json!("6"), "InvalidSocksVersion"),
        (json!(5), "ExpectedString"),
        (Value::Null, "ExpectedString"),
    ] {
        let mut value = outbound("socks");
        value["settings"]["version"] = version;
        let doc = roundtrip(&value);
        assert!(issue(&doc, code));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
    }
}

#[test]
fn socks5_credentials_require_each_wire_length_in_one_to_255_bytes() {
    for account in [
        json!({}),
        json!({"user":"user"}),
        json!({"pass":"password"}),
        json!({"user":"","pass":"password"}),
        json!({"user":"user","pass":""}),
        json!({"user":"ü".repeat(128),"pass":"password"}),
        json!({"user":"user","pass":"x".repeat(256)}),
    ] {
        let mut value = outbound("socks");
        value["settings"]["servers"][0]["users"] = json!([account]);
        let doc = roundtrip(&value);
        assert!(issue(&doc, "Socks5CredentialLength"));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
        assert!(matches!(
            doc.nodes()[0].authentication(),
            Authentication::UserPassword { .. }
        ));
    }
    let mut value = outbound("socks");
    value["settings"]["servers"][0]["users"] =
        json!([{"user":"u".repeat(255),"pass":"p".repeat(255)}]);
    assert!(roundtrip(&value).nodes()[0].diagnostics().is_empty());
}

#[test]
fn http_basic_empty_or_long_credentials_remain_valid_but_native_unsupported() {
    for account in [
        json!({"user":"user","pass":""}),
        json!({"user":"","pass":"password"}),
        json!({"user":"user"}),
        json!({"user":"u".repeat(256),"pass":"password"}),
    ] {
        let mut value = outbound("http");
        value["settings"]["servers"][0]["users"] = json!([account]);
        let doc = roundtrip(&value);
        assert!(issue(&doc, "NativeProxyAuthenticationUnsupported"));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Valid);
        assert!(matches!(
            doc.nodes()[0].authentication(),
            Authentication::UserPassword { .. }
        ));
    }
}

#[test]
fn unsupported_authentication_schemes_and_basic_injection_are_never_dropped() {
    for (account, code) in [
        (
            json!({"user":"user:other","pass":"password"}),
            "HttpBasicUsernameColon",
        ),
        (
            json!({"user":"user","pass":"password\r\nX-Test: bad"}),
            "HttpBasicControlCharacter",
        ),
    ] {
        let mut value = outbound("http");
        value["settings"]["servers"][0]["users"] = json!([account]);
        let doc = roundtrip(&value);
        assert!(issue(&doc, code));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
    }
    for protocol in ["socks", "http"] {
        let mut value = outbound(protocol);
        value["settings"]["auth"] = json!("digest");
        assert!(issue(&roundtrip(&value), "OutboundAuthMethodUnsupported"));
    }
}

#[test]
fn http_headers_are_validated_preserved_and_never_claimed_applied() {
    let mut value = outbound("http");
    value["settings"]["headers"] =
        json!({"X-Synthetic":"value","Proxy-Authorization":"SYNTHETIC_TOKEN"});
    let doc = roundtrip(&value);
    assert!(issue(&doc, "HttpProxyHeadersUnsupported"));
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Valid);
    let display = format!(
        "{doc:?} {:?} {:?}",
        doc.nodes()[0],
        doc.nodes()[0].diagnostics()
    );
    assert!(!display.contains("SYNTHETIC_TOKEN"));
    value["settings"]["headers"] = json!({});
    assert!(roundtrip(&value).nodes()[0].diagnostics().is_empty());
}

#[test]
fn malformed_http_header_types_names_and_values_are_invalid() {
    for (headers, code) in [
        (json!("not-map"), "ExpectedObject"),
        (json!({"X-Test":42}), "ExpectedString"),
        (json!({"X Bad":"value"}), "InvalidHttpHeaderName"),
        (
            json!({"X-Test":"value\nInjected: yes"}),
            "InvalidHttpHeaderValue",
        ),
    ] {
        let mut value = outbound("http");
        value["settings"]["headers"] = headers;
        let doc = roundtrip(&value);
        assert!(issue(&doc, code));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Invalid);
    }
}

#[test]
fn mixed_flat_credentials_and_users_are_expanded_but_blocked_as_ambiguous() {
    for protocol in ["socks", "http"] {
        let value = json!({"protocol":protocol,"settings":{"address":"proxy.example.invalid","port":443,
            "user":"flat","pass":"flat-password","users":[{"user":"first","pass":"first-password"},
            {"user":"second","pass":"second-password"}]}});
        let doc = roundtrip(&value);
        assert_eq!(doc.nodes().len(), 2);
        assert!(
            doc.nodes()
                .iter()
                .all(|node| node.validation() == ValidationStatus::Invalid)
        );
        assert!(issue(&doc, "AmbiguousAuthenticationForms"));
        let mut empty = value.clone();
        empty["settings"]["users"] = json!([]);
        assert!(issue(&roundtrip(&empty), "AmbiguousAuthenticationForms"));
    }
}

#[test]
fn flat_users_without_direct_credentials_are_retained_as_unsupported_hybrid() {
    let value = json!({"protocol":"http","settings":{"address":"proxy.example.invalid","port":443,
        "users":[{"user":"one","pass":"password"},{"user":"two","pass":"password"}]}});
    let doc = roundtrip(&value);
    assert_eq!(doc.nodes().len(), 2);
    assert!(issue(&doc, "FlatUsersFormUnsupported"));
}

#[test]
fn unknown_account_fields_block_validation_and_preserve_all_credentials() {
    let mut value = outbound("socks");
    value["settings"]["servers"][0]["users"] = json!([{"user":"SYNTHETIC_USER","pass":"SYNTHETIC_PASSWORD",
        "SYNTHETIC_SECRET_KEY":"SYNTHETIC_VALUE"}]);
    let doc = roundtrip(&value);
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Unverified);
    assert!(issue(&doc, "UnmappedFieldPreserved"));
    let text = format!(
        "{doc:?} {:?} {:?}",
        doc.nodes()[0],
        doc.nodes()[0].authentication()
    );
    for secret in [
        "SYNTHETIC_USER",
        "SYNTHETIC_PASSWORD",
        "SYNTHETIC_SECRET_KEY",
        "SYNTHETIC_VALUE",
    ] {
        assert!(!text.contains(secret));
    }
}

#[test]
fn http_and_socks_user_levels_remain_u32_and_nonzero_policy_is_unsupported() {
    for protocol in ["socks", "http"] {
        let mut value = outbound(protocol);
        value["settings"]["servers"][0]["users"] =
            json!([{"user":"user","pass":"password","level":u32::MAX}]);
        let doc = roundtrip(&value);
        assert!(matches!(
            doc.nodes()[0].authentication(),
            Authentication::UserPassword {
                level: Some(u32::MAX),
                ..
            }
        ));
        assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Valid);
        assert!(issue(&doc, "UserLevelPolicyUnsupported"));
    }
}

#[test]
fn malformed_known_account_fields_are_rejected_by_existing_strict_parser() {
    for account in [
        json!({"user":42,"pass":"password"}),
        json!({"user":"user","pass":true}),
        json!({"user":"user","pass":"password","level":-1}),
        json!({"user":"user","pass":"password","email":null}),
    ] {
        let mut value = outbound("socks");
        value["settings"]["servers"][0]["users"] = json!([account]);
        assert!(import_document(&serde_json::to_vec(&value).unwrap(), InputSource::File).is_err());
    }
}

#[test]
fn unicode_control_is_native_unsupported_without_mislabeling_ascii_ctl() {
    let mut value = outbound("http");
    value["settings"]["servers"][0]["users"] = json!([{"user":"user","pass":"password\u{0080}"}]);
    let doc = roundtrip(&value);
    assert_eq!(doc.nodes()[0].validation(), ValidationStatus::Valid);
    assert!(issue(&doc, "NativeProxyAuthenticationUnsupported"));
    assert!(!issue(&doc, "HttpBasicControlCharacter"));
}
