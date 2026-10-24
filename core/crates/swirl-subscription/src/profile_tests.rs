use super::*;

fn source(mut dns: Value) -> Value {
    if let Some(object) = dns.as_object_mut() {
        object.entry("enable").or_insert(true.into());
    }
    json!({"rules":["DOMAIN,fixture.invalid,DIRECT","MATCH,DIRECT"],"proxy-groups":[{"name":"Select","type":"select","proxies":["DIRECT"]}],"dns":dns})
}

#[test]
fn plain_dns_and_exact_hosts_are_projected_without_native_platform_calls() {
    let mut input = source(
        json!({"enable":true,"nameserver":["127.0.0.1","::1"],"ipv6":false,"use-hosts":true}),
    );
    input["hosts"] = json!({"Host.Invalid":"192.0.2.1"});
    let result = project(&input).unwrap();
    assert_eq!(
        result["dns"],
        json!({"mode":2,"servers":"127.0.0.1,::1","encrypted":"","hosts":[{"name":"host.invalid","value":"192.0.2.1"}],"useHosts":true,"respectRules":false,"queryFamily":"ipv4_only"})
    );
    assert_eq!(result["rules"], input["rules"]);
    assert_eq!(result["groups"], input["proxy-groups"]);
}

#[test]
fn encrypted_dns_requires_explicit_bootstrap_and_preserves_tls_authentication_name() {
    let mut input = source(json!({"nameserver":["https://dns.invalid/dns-query"]}));
    assert_eq!(
        project(&input).unwrap_err().code,
        "ProfileDnsBootstrapRequired"
    );
    input["hosts"] = json!({"dns.invalid":"192.0.2.53"});
    let result = project(&input).unwrap();
    assert_eq!(result["dns"]["encrypted"], "https://dns.invalid/dns-query");
    assert_eq!(result["dns"]["mode"], 0);
    for invalid in [
        json!({"nameserver":["127.0.0.1","tls://192.0.2.53"]}),
        json!({"nameserver":["https://192.0.2.53/dns-query?token=secret"]}),
        json!({"nameserver":["tls://192.0.2.53/path"]}),
    ] {
        assert!(project(&source(invalid)).is_err());
    }
}

#[test]
fn unsupported_security_or_routing_semantics_fail_instead_of_disappearing() {
    for (value, code) in [
        (
            json!({"enhanced-mode":"fake-ip"}),
            "ProfileDnsModeUnsupported",
        ),
        (
            json!({"respect-rules":true}),
            "ProfileDnsRuleRoutingUnsupported",
        ),
        (
            json!({"fallback":["192.0.2.1"]}),
            "ProfileDnsFieldUnsupported",
        ),
        (json!({"enable":false}), "ProfileDnsDisabledUnsupported"),
        (
            json!({"ipv6":false}),
            "DnsQueryFamilyRequiresExplicitServer",
        ),
    ] {
        assert_eq!(project(&source(value)).unwrap_err().code, code);
    }
    let mut input = source(json!({}));
    input["secret?token=PRIVATE"] = json!(true);
    let diagnostic = project(&input).unwrap_err();
    assert_eq!(
        diagnostic,
        error("ProfileGlobalFieldUnsupported", "configuration")
    );
}

#[test]
fn profile_rejects_unreachable_rules_unknown_groups_and_wrong_types_atomically() {
    let mut input = source(json!({}));
    for rules in [
        json!(["MATCH,DIRECT", "DOMAIN,later.invalid,DIRECT"]),
        json!(["DOMAIN,a.invalid,DIRECT"]),
        json!(["RULE-SET,private,DIRECT", "MATCH,DIRECT"]),
        json!(["MATCH,DIRECT", false]),
    ] {
        input["rules"] = rules;
        assert!(project(&input).is_err());
    }
    input = source(json!({}));
    input["proxy-groups"][0]["filter"] = json!(".*");
    assert_eq!(project(&input).unwrap_err().field, "proxy-groups.filter");
}

#[test]
fn client_dns_defaults_do_not_become_native_guesses() {
    let input = json!({"rules":["MATCH,DIRECT"],"dns":{"nameserver":["192.0.2.53"]}});
    assert_eq!(
        project(&input).unwrap_err().code,
        "ProfileDnsDisabledUnsupported"
    );
    let input = source(json!({"nameserver":["192.0.2.53"]}));
    assert_eq!(project(&input).unwrap()["dns"]["queryFamily"], "ipv4_only");
    let input = json!({"rules":["MATCH,DIRECT"],"hosts":{"fixture.invalid":"192.0.2.1"}});
    let mapped = project(&input).unwrap();
    assert_eq!(mapped["dns"]["queryFamily"], "dual");
    assert_eq!(
        mapped["dns"]["hosts"],
        json!([{"name":"fixture.invalid","value":"192.0.2.1"}])
    );
    let mut disabled = source(json!({"nameserver":["192.0.2.53"],"use-hosts":false}));
    disabled["hosts"] = json!({"fixture.invalid":"192.0.2.1"});
    assert_eq!(
        project(&disabled).unwrap_err().code,
        "ProfileDnsHostsDisabled"
    );
}

#[test]
fn an_explicit_loopback_restriction_is_a_typed_noop_not_permission_for_lan() {
    let baseline = json!({"rules":["MATCH,DIRECT"]});
    let mut restricted = baseline.clone();
    restricted["allow-lan"] = json!(false);
    assert_eq!(project(&restricted).unwrap(), project(&baseline).unwrap());
    for value in [
        json!(true),
        json!("false"),
        json!(0),
        Value::Null,
        json!({}),
        json!([]),
    ] {
        restricted["allow-lan"] = value;
        assert_eq!(
            project(&restricted).unwrap_err(),
            error("ProfileGlobalFieldUnsupported", "allow-lan")
        );
    }
    restricted = baseline;
    restricted["dns"] = json!({"enable":true,"nameserver":["192.0.2.53"],"allow-lan":false});
    assert_eq!(
        project(&restricted).unwrap_err().code,
        "ProfileDnsFieldUnsupported"
    );
}
