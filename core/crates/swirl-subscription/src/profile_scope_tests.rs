use super::*;
use serde_json::json;

const NODE: &str =
    "[Proxy]\nA=ss,proxy.invalid,443,encrypt-method=aes-128-gcm,password=synthetic-pass\n";

fn canonical(bytes: &[u8]) -> Value {
    let inspection = crate::inspect::inspect(bytes);
    assert!(inspection.report.parsed);
    assert!(inspection.report.nodes[0].native_tcp_candidate);
    assert_eq!(inspection.original, bytes);
    let outbound = serde_json::to_value(inspection.tcp_candidates[0].as_ref().unwrap()).unwrap();
    let config:crate::Config=serde_json::from_value(json!({"schema":1,"listen":"127.0.0.1:0","selected":"A","nodes":[{"id":"A","outbound":outbound}]})).unwrap();
    config.validate().unwrap();
    serde_json::to_value(config).unwrap()
}

fn clash_document(mut source: Value) -> Vec<u8> {
    source["proxies"] = json!([{"name":"A","type":"ss","server":"proxy.invalid","port":443,"cipher":"aes-128-gcm","password":"synthetic-pass"}]);
    serde_json::to_vec(&source).unwrap()
}

#[test]
fn node_only_ini_and_cosmetic_metadata_do_not_request_network_replacement() {
    for text in [
        NODE.to_owned(),
        format!("[General]\nloglevel=notify\nproxy-test-url=https://test.invalid/204\n{NODE}"),
    ] {
        let source = json!({"document":text});
        assert!(!has_semantics("ini", &source));
        assert!(node_only_allowed("ini", &source));
    }
    for content in [
        "[General]\nipv6=false\n",
        "[Rule]\nFINAL,A\n",
        "[Unknown]\nunknown=value\n",
    ] {
        assert!(has_semantics(
            "ini",
            &json!({"document":format!("{NODE}{content}")})
        ));
    }
}

#[test]
fn foreign_ini_executable_sections_are_data_not_native_configuration() {
    let baseline = canonical(NODE.as_bytes());
    for suffix in [
        "[Script]\nx=script-path=C:\\PRIVATE\\script.js\n",
        "[Remote Script]\nx=https://private.invalid/script.js\n",
        "[MITM]\nca-p12=PRIVATE\n",
        "[URL Rewrite]\n^https://private.invalid/ url reject\n",
        "[Remote Proxy]\nx=https://private.invalid/nodes\n",
    ] {
        let document = format!("{NODE}{suffix}");
        let source = json!({"document":document});
        assert!(super::super::project_format("ini", &source).is_err());
        assert!(node_only_allowed("ini", &source));
        assert_eq!(canonical(document.as_bytes()), baseline);
    }
}

#[test]
fn unsupported_managed_headers_remain_opaque_in_data_only_extraction() {
    let baseline = canonical(NODE.as_bytes());
    for header in [
        "#!MANAGED-CONFIG file:///PRIVATE",
        "#!MANAGED-CONFIG https://user:password@private.invalid/",
        "#!MANAGED-CONFIG https://private.invalid/ interval=-1",
        "#!MANAGED-CONFIG https://private.invalid/ strict=maybe",
    ] {
        let document = format!("{header}\n{NODE}");
        let source = json!({"document":document});
        assert!(super::super::project_format("ini", &source).is_err());
        assert!(node_only_allowed("ini", &source));
        assert_eq!(canonical(document.as_bytes()), baseline);
    }
}

#[test]
fn json_code_file_and_provider_globals_cannot_change_canonical_nodes() {
    let baseline = canonical(&clash_document(json!({})));
    for global in [
        json!({"script":{"code":"PRIVATE"}}),
        json!({"proxy-providers":{"Remote":{"type":"http","url":"https://private.invalid/nodes"}}}),
        json!({"rule-providers":{"Rules":{"type":"file","path":"C:\\PRIVATE"}}}),
        json!({"dns":{"nameserver":["file:///PRIVATE"]}}),
        json!({"rules":["SCRIPT,private,DIRECT","MATCH,DIRECT"]}),
        json!({"opaque-global":{"items":[{"command":"PRIVATE","scriptPath":"private.js","future":{"path":"/PRIVATE"}}]}}),
    ] {
        assert!(super::super::project_format("clash", &global).is_err());
        assert!(node_only_allowed("clash", &global));
        assert_eq!(canonical(&clash_document(global)), baseline);
    }
}

#[test]
fn singbox_policy_and_provider_globals_remain_separate_from_remote_nodes() {
    let basic = json!({"outbounds":[{"type":"socks","tag":"A","server":"proxy.invalid","server_port":1080}]});
    let mut source = basic.clone();
    source["outbounds"].as_array_mut().unwrap().push(
        json!({"type":"selector","tag":"route","outbounds":["A"],"unknown-global-policy":true}),
    );
    source["route"] = json!({"rules":[],"final":"route","rule_set":[{"type":"remote","url":"https://private.invalid/rules"}]});
    source["unknown-global"] = json!({"command":"PRIVATE","file":"C:\\PRIVATE"});
    assert!(has_semantics("sing-box", &source));
    assert!(node_only_allowed("sing-box", &source));
    assert_eq!(
        canonical(&serde_json::to_vec(&source).unwrap()),
        canonical(&serde_json::to_vec(&basic).unwrap())
    );
    for bytes in [
        b"[Remote Proxy]\nx=https://private.invalid/nodes\n".as_slice(),
        br#"{"proxy-providers":{"x":{"type":"http","url":"https://private.invalid/nodes"}}}"#
            .as_slice(),
    ] {
        let inspection = crate::inspect::inspect(bytes);
        assert!(inspection.report.nodes.is_empty());
        assert!(inspection.tcp_candidates.is_empty());
    }
}

#[test]
fn foreign_ini_general_policy_is_data_only_after_strict_projection_rejects_it() {
    let document = format!(
        "[General]\nbypass-system=true\nskip-proxy=192.168.0.0/16,localhost\nbypass-tun=192.168.0.0/16\nhttp-listen=0.0.0.0:6152\nsocks5-listen=0.0.0.0:6153\nfuture-client-metadata=opaque\n{NODE}[Proxy Group]\nAuto=url-test,A,url=https://check.invalid/204\n[Rule]\nGEOIP,CN,DIRECT\nFINAL,Auto\n"
    );
    let source = json!({"document":document});
    assert!(has_semantics("ini", &source));
    assert_eq!(
        super::super::project_format("ini", &source)
            .unwrap_err()
            .code,
        "ProfileIniGeneralUnsupported"
    );
    assert!(node_only_allowed("ini", &source));
    assert_eq!(canonical(document.as_bytes()), canonical(NODE.as_bytes()));
}

#[test]
fn foreign_json_listener_tun_and_opaque_metadata_never_become_full_projection() {
    let source = json!({"mixed-port":7890,"allow-lan":true,"external-controller":"0.0.0.0:9090","secret":"PRIVATE","tun":{"enable":true,"auto-route":true},"dns":{"enable":true,"future-client-option":{"opaque":[true,1,"metadata"]}},"rules":["GEOIP,CN,DIRECT","MATCH,DIRECT"]});
    assert!(has_semantics("clash", &source));
    assert_eq!(
        super::super::project_format("clash", &source)
            .unwrap_err()
            .code,
        "ProfileGlobalFieldUnsupported"
    );
    assert!(node_only_allowed("clash", &source));
    assert_eq!(
        canonical(&clash_document(source)),
        canonical(&clash_document(json!({})))
    );
}

#[test]
fn late_foreign_code_file_and_resource_sections_never_promote_into_nodes() {
    let ordinary = format!("[General]\nbypass-system=true\nhttp-listen=0.0.0.0:6152\n{NODE}");
    let baseline = canonical(NODE.as_bytes());
    for suffix in [
        "[Script]\nx=script-path=C:\\PRIVATE\\script.js\n",
        "[MITM]\np12=PRIVATE\n",
        "[Plugin]\nx=https://private.invalid/plugin\n",
        "[Proxy Group]\nx=select,A,policy-path=https://private.invalid/nodes\n",
        "[Unknown Metadata]\nfuture=file:///PRIVATE\n",
        "[Unknown Metadata]\nfuture=\\\\server\\PRIVATE\n",
        "[Unknown Metadata]\nfuture=javascript:PRIVATE\n",
    ] {
        let document = format!("{ordinary}{suffix}");
        assert!(node_only_allowed("ini", &json!({"document":document})));
        assert_eq!(canonical(document.as_bytes()), baseline);
    }
}

#[test]
fn data_only_scan_has_shared_depth_item_and_text_bounds() {
    let mut nested = json!(true);
    for _ in 0..34 {
        nested = json!([nested]);
    }
    assert!(!node_only_allowed("clash", &json!({"opaque":nested})));
    assert!(!node_only_allowed(
        "clash",
        &json!({"opaque":vec![true;100001]})
    ));
    assert!(!node_only_allowed(
        "clash",
        &json!({"opaque":"x".repeat(4*1024*1024+1)})
    ));
    assert!(!node_only_allowed(
        "ini",
        &json!({"document":format!("[General]\nopaque={}\n{NODE}","x".repeat(4*1024*1024))})
    ));
    for document in [
        "[Proxy]\nA=socks5,proxy.invalid,1080\n[Proxy]\nB=socks5,proxy.invalid,1081\n",
        "[Proxy] trailing-invalid\nA=socks5,proxy.invalid,1080\n",
        "value-before-section\n[Proxy]\nA=socks5,proxy.invalid,1080\n",
    ] {
        assert!(!node_only_allowed("ini", &json!({"document":document})));
    }
}

#[test]
fn node_protocol_security_and_local_file_fields_keep_closed_native_schema() {
    let basic = json!({"name":"A","type":"ss","server":"proxy.invalid","port":443,"cipher":"aes-128-gcm","password":"synthetic-pass"});
    for (key, value) in [
        ("unknown_protocol_option", json!(true)),
        ("script", json!("PRIVATE")),
        ("command", json!("PRIVATE")),
        ("certificate-path", json!("C:\\PRIVATE")),
        ("tls", json!(false)),
    ] {
        let mut node = basic.clone();
        node[key] = value;
        let bytes = serde_json::to_vec(&json!({"proxies":[node]})).unwrap();
        let inspection = crate::inspect::inspect(&bytes);
        assert_eq!(inspection.original, bytes);
        assert!(!inspection.report.nodes[0].native_tcp_candidate);
        assert!(inspection.tcp_candidates[0].is_none());
    }
}

#[test]
fn remote_and_local_policy_resource_declarations_are_inert_source_data() {
    let document = format!(
        "[General]\nbypass-system=true\n{NODE}[Rule]\nRULE-SET,https://rules.invalid/list,A\nDOMAIN-SET,file:///PRIVATE,A\nFINAL,A\n[filter_remote]\nhttps://rules.invalid/filters,tag=ForeignPolicy\n"
    );
    assert!(node_only_allowed("ini", &json!({"document":document})));
    assert_eq!(canonical(document.as_bytes()), canonical(NODE.as_bytes()));
    for source in [
        json!({"rule-providers":{"ForeignRules":{"type":"file","path":"C:\\PRIVATE"}}}),
        json!({"rule-providers":{"ForeignRules":{"type":"http","url":"https://private.invalid/rules"}}}),
        json!({"rules":["RULE-SET,/PRIVATE/list,DIRECT"]}),
    ] {
        assert!(super::super::project_format("clash", &source).is_err());
        assert!(node_only_allowed("clash", &source));
        assert_eq!(
            canonical(&clash_document(source)),
            canonical(&clash_document(json!({})))
        );
    }
}

#[test]
fn supported_complete_profiles_keep_full_projection_and_client_metadata_scope() {
    let source =
        json!({"dns":{"enable":true,"nameserver":["192.0.2.53"]},"rules":["MATCH,DIRECT"]});
    assert_eq!(
        super::super::project_format("clash", &source).unwrap(),
        json!({"rules":["MATCH,DIRECT"],"dns":{"mode":2,"servers":"192.0.2.53","encrypted":"","hosts":[],"useHosts":true,"respectRules":false,"queryFamily":"ipv4_only"}})
    );
    let metadata = json!({"document":format!("[General]\ngroup-icon=https://display.invalid/icon.png\nallow-wifi-access=false\nipv6-vif=off\n{NODE}")});
    assert!(!has_semantics("ini", &metadata));
    assert!(node_only_allowed("ini", &metadata));
    assert_eq!(
        super::super::project_format("ini", &metadata).unwrap(),
        json!({"importMetadata":{"preservedGeneral":["allow-wifi-access","group-icon","ipv6-vif"],"restrictions":["ClientGeneralSettingsPreserved"]}})
    );
}

#[test]
fn foreign_code_and_file_aliases_have_no_execution_or_public_report_values() {
    let baseline = canonical(&clash_document(json!({})));
    for key in [
        "scriptPath",
        "SCRIPTPATH",
        "resourceParserUrl",
        "resource_parser_url",
        "execute",
        "commandLine",
        "certificatePath",
        "privateKeyPath",
    ] {
        let source = json!({"opaque-global":{key:"PRIVATE"}});
        assert!(node_only_allowed("clash", &source));
        let bytes = clash_document(source);
        assert_eq!(canonical(&bytes), baseline);
        let inspection = crate::inspect::inspect(&bytes);
        assert!(
            !serde_json::to_string(&inspection.report)
                .unwrap()
                .contains("PRIVATE")
        );
    }
}
