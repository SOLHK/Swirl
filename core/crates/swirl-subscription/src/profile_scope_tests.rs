use super::*;
use serde_json::json;

const NODE: &str =
    "[Proxy]\nA=ss,proxy.invalid,443,encrypt-method=aes-128-gcm,password=synthetic-pass\n";

#[test]
fn node_only_ini_and_cosmetic_metadata_do_not_request_network_replacement() {
    for text in [
        NODE.to_owned(),
        format!("[General]\nloglevel=notify\nproxy-test-url=https://test.invalid/204\n{NODE}"),
    ] {
        let input = json!({"document":text});
        assert!(!has_semantics("ini", &input));
        assert!(node_only_allowed("ini", &input));
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
fn recoverable_unsupported_rules_never_hide_later_host_capabilities() {
    let unsupported = format!(
        "{NODE}[General]\ndns_exclusion_list=*.example.invalid\n[Rule]\nGEOIP,CN,DIRECT\nFINAL,A\n"
    );
    assert!(node_only_allowed("ini", &json!({"document":unsupported})));
    for suffix in [
        "[Script]\nx=script-path=private.js",
        "[MITM]\np12=PRIVATE",
        "[General]\nhttp-listen=0.0.0.0:7890",
        "[General]\nresource_parser_url=https://private.invalid/script.js",
        "[General]\nunknown_capability=PRIVATE",
        "[Remote Proxy]\nx=https://private.invalid/",
        "[Proxy Group]\na=select,A,policy-path=C:\\PRIVATE",
        "[Rule]\nSCRIPT,private-script,A",
        "[Rule]\nRULE-SET,file:///PRIVATE,A",
        "[Rule]\nRULE-SET,C:\\PRIVATE,A",
        "[Rule]\nRULE-SET,\\\\server\\PRIVATE,A",
        "[Proxy Group]\na=url-test,A,url=file:///PRIVATE",
        "[Proxy Group]\na=url-test,A,url=javascript:PRIVATE",
    ] {
        let input = json!({"document":format!("{unsupported}{suffix}")});
        assert!(
            !node_only_allowed("ini", &input),
            "unsafe suffix was allowed"
        );
    }
}

#[test]
fn malformed_or_local_managed_headers_cannot_be_reclassified_as_comments() {
    for header in [
        "#!MANAGED-CONFIG file:///private/config",
        "#!MANAGED-CONFIG https://user:password@private.invalid/",
        "#!MANAGED-CONFIG https://private.invalid/ interval=-1",
        "#!MANAGED-CONFIG https://private.invalid/ strict=maybe",
    ] {
        assert!(!node_only_allowed(
            "ini",
            &json!({"document":format!("{header}\n{NODE}")})
        ));
    }
    assert!(node_only_allowed(
        "ini",
        &json!({"document":format!("#!MANAGED-CONFIG https://private.invalid/?token=PRIVATE interval=900 strict=false\n{NODE}")})
    ));
    assert!(!node_only_allowed(
        "ini",
        &json!({"document":format!("[General]\nserver_check_url=file:///PRIVATE\n{NODE}")})
    ));
}

#[test]
fn json_fallback_is_closed_to_host_operations_and_unknown_capabilities() {
    let safe = json!({"rules":["GEOIP,CN,DIRECT","MATCH,DIRECT"],"dns":{"enable":true,"fallback":["https://dns.invalid/query"]}});
    assert!(node_only_allowed("clash", &safe));
    for extra in [
        json!({"script":{"code":"PRIVATE"}}),
        json!({"tun":{"enable":true}}),
        json!({"mixed-port":7890}),
        json!({"dns":{"unknown_capability":true}}),
        json!({"proxy-groups":[{"name":"a","type":"select","proxies":["A"],"policy-path":"C:\\PRIVATE"}]}),
        json!({"dns":{"nameserver":["file:///PRIVATE"]}}),
        json!({"rules":["RULE-SET,file:///PRIVATE,DIRECT","MATCH,DIRECT"]}),
        json!({"rules":["RULE-SET,C:\\PRIVATE,DIRECT","MATCH,DIRECT"]}),
        json!({"rules":["SCRIPT,private,DIRECT","MATCH,DIRECT"]}),
        json!({"proxy-groups":[{"name":"a","type":"script","proxies":["A"]}]}),
        json!({"proxy-groups":[{"name":"a","type":"url-test","proxies":["A"],"url":"file:///PRIVATE"}]}),
    ] {
        let mut input = safe.clone();
        input
            .as_object_mut()
            .unwrap()
            .extend(extra.as_object().unwrap().clone());
        assert!(!node_only_allowed("clash", &input));
    }
}

#[test]
fn singbox_selectors_are_audited_even_when_valid_nodes_have_already_been_parsed() {
    let safe = json!({"outbounds":[{"type":"socks","tag":"A","server":"proxy.invalid","server_port":1080,"password":"/literal/password"},
        {"type":"selector","tag":"route","outbounds":["A"],"default":"A"}],"route":{"rules":[],"final":"route"}});
    assert!(node_only_allowed("sing-box", &safe));
    assert!(has_semantics(
        "sing-box",
        &json!({"outbounds":safe["outbounds"]})
    ));
    assert!(!has_semantics(
        "sing-box",
        &json!({"outbounds":[safe["outbounds"][0]]})
    ));
    for (key, value) in [
        ("script", json!("PRIVATE")),
        ("command", json!("PRIVATE")),
        ("policy-path", json!("C:\\PRIVATE")),
        ("unknown_capability", json!(true)),
    ] {
        let mut input = safe.clone();
        input["outbounds"][1][key] = value;
        assert!(!node_only_allowed("sing-box", &input));
    }
    let mut input = safe.clone();
    input["outbounds"][1] =
        json!({"type":"urltest","tag":"route","outbounds":["A"],"url":"file:///PRIVATE"});
    assert!(!node_only_allowed("sing-box", &input));
    let mut input = safe;
    input["outbounds"][0]["tls"] = json!({"certificate_path":"C:\\PRIVATE"});
    assert!(!node_only_allowed("sing-box", &input));
}
