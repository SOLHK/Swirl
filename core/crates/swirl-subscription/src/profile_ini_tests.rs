use super::*;

const SOURCE: &str = "[General]\ndns-server=192.0.2.53,192.0.2.54\nipv6=false\n[Host]\nexact.invalid=192.0.2.99\n[Proxy]\nA = ss,proxy.invalid,443,encrypt-method=aes-128-gcm,password=synthetic-pass,tfo=true\nDIRECT = direct\nREJECT = reject\n[Proxy Group]\nroute = select,A,DIRECT\nnested = select,route,REJECT\n[Rule]\nDOMAIN,exact.invalid,REJECT\nDOMAIN-SUFFIX,suffix.invalid,route\nIP-CIDR,192.0.2.0/24,nested,no-resolve\nFINAL,route\n";

fn source(text: &str) -> Value {
    json!({"document":text})
}

#[test]
fn complete_ini_dns_hosts_manual_groups_and_rules_use_existing_portable_schema() {
    let result = project(&source(SOURCE)).unwrap();
    assert_eq!(
        result,
        json!({"dns":{"mode":2,"servers":"192.0.2.53,192.0.2.54","encrypted":"","hosts":[{"name":"exact.invalid","value":"192.0.2.99"}],"useHosts":true,"respectRules":false,"queryFamily":"ipv4_only"},
        "groups":[{"name":"route","type":"select","proxies":["A","DIRECT"]},{"name":"nested","type":"select","proxies":["route","REJECT"]}],
        "rules":["DOMAIN,exact.invalid,REJECT","DOMAIN-SUFFIX,suffix.invalid,route","IP-CIDR,192.0.2.0/24,nested,no-resolve","MATCH,route"]})
    );
}

#[test]
fn ini_node_only_success_never_emits_empty_dns_rules_or_groups() {
    for document in [
        "[Proxy]\nA=socks5,proxy.invalid,1080\n",
        "[general]\nserver_check_url=https://test.invalid/204\n[server_local]\nsocks5=proxy.invalid:1080,tag=A\n",
    ] {
        let projected = project(&source(document)).unwrap();
        assert!(projected.get("dns").is_none());
        assert!(projected.get("groups").is_none());
        assert!(projected.get("rules").is_none());
        assert!(!super::super::has_profile_semantics(
            "ini",
            &source(document)
        ));
    }
}

#[test]
fn ini_dns_channels_preserve_encryption_and_reject_cross_transport_values() {
    for (key, value) in [
        ("doh-server", "192.0.2.53"),
        ("doh-server", "tls://dns.invalid"),
        ("encrypted-dns-server", "192.0.2.53"),
        ("encrypted-dns-server", "http://dns.invalid/dns-query"),
        ("encrypted-dns-server", "tcp://dns.invalid"),
        ("dns-server", "https://dns.invalid/dns-query"),
        ("dns-server", "tls://dns.invalid"),
        ("dns-server", "192.0.2.53:5300"),
    ] {
        let input = SOURCE.replace(
            "dns-server=192.0.2.53,192.0.2.54",
            &format!("{key}={value}"),
        );
        assert_eq!(
            project(&source(&input)).unwrap_err().code,
            "ProfileIniDnsTransportMismatch"
        );
    }
    for (key, value) in [
        ("doh-server", "https://dns.invalid/dns-query"),
        ("encrypted-dns-server", "https://dns.invalid/dns-query"),
        ("encrypted-dns-server", "tls://dns.invalid"),
    ] {
        let input = SOURCE
            .replace(
                "dns-server=192.0.2.53,192.0.2.54",
                &format!("{key}={value}"),
            )
            .replace("[Host]", "[Host]\ndns.invalid=192.0.2.53");
        let projected = project(&source(&input)).unwrap();
        assert_eq!(projected["dns"]["mode"], 0);
        assert_eq!(projected["dns"]["servers"], "");
        assert_eq!(projected["dns"]["encrypted"], value);
        assert_eq!(projected["dns"]["queryFamily"], "ipv4_only");
        let without_bootstrap = input.replace("dns.invalid=192.0.2.53\n", "");
        assert_eq!(
            project(&source(&without_bootstrap)).unwrap_err().code,
            "ProfileDnsBootstrapRequired"
        );
    }
}

#[test]
fn unsupported_ini_does_not_drop_host_security_network_scripts_or_remote_updates() {
    for addition in [
        "[Script]\nhttp-request ^https://secret.invalid script-path=private.js",
        "[MITM]\nca-p12=PRIVATE",
        "[Remote Proxy]\nProvider=https://private.invalid?token=PRIVATE",
        "[General]\nresource-parser=https://private.invalid?token=PRIVATE",
        "[General]\nhttp-listen=0.0.0.0:7890",
        "[General]\nbypass-tun=0.0.0.0/0",
        "[Unknown-PRIVATE]\nsecret=PRIVATE",
    ] {
        let input = SOURCE.replace(
            "[General]\ndns-server=192.0.2.53,192.0.2.54\nipv6=false\n",
            "",
        ) + addition;
        let error = project(&source(&input)).unwrap_err();
        assert!(!format!("{error:?}").contains("PRIVATE"));
        assert!(!format!("{error:?}").contains("https://"));
    }
}

#[test]
fn managed_header_and_client_metadata_are_preserved_without_changing_subscription_source() {
    let document = format!(
        "#!MANAGED-CONFIG https://private.invalid/profile?token=PRIVATE interval=900 strict=true\n{}",
        SOURCE.replace(
            "ipv6=false",
            "ipv6=false\nloglevel=notify\nproxy-test-url=https://test.invalid/204\ntest-timeout=5"
        )
    );
    let projected = project(&source(&document)).unwrap();
    assert_eq!(
        projected["rules"],
        project(&source(SOURCE)).unwrap()["rules"]
    );
    assert_eq!(
        projected["importMetadata"],
        json!({
        "managedConfig":{"embeddedUrlPreserved":true,"embeddedUrlApplied":false,"intervalSeconds":900,"strict":true},
        "preservedGeneral":["loglevel","proxy-test-url","test-timeout"],
        "restrictions":["EmbeddedUpdateUsesSwirlSubscription","ClientGeneralSettingsPreserved"]})
    );
    assert!(!projected.to_string().contains("PRIVATE"));
    assert!(!projected.to_string().contains("private.invalid"));
    for invalid in [
        document.replace("strict=true", "strict=maybe"),
        document.replace("interval=900", "interval=0"),
        document.replace(
            "https://private.invalid/profile?token=PRIVATE",
            "file:///PRIVATE",
        ),
        format!("# comment\n{document}"),
        document.replace("loglevel=notify", "loglevel=arbitrary"),
        document.replace("test-timeout=5", "test-timeout=-1"),
    ] {
        assert!(project(&source(&invalid)).is_err());
    }
}

const QX: &str = "[general]\nserver_check_url=https://test.invalid/204\nserver_check_timeout=5000\n[dns]\nno-ipv6\nno-system\nserver=192.0.2.53\naddress=/exact.invalid/192.0.2.99\n[policy]\nstatic=route,A,direct\n[server_local]\nshadowsocks=proxy.invalid:443,method=aes-128-gcm,password=synthetic-pass,tag=A\n[filter_local]\nhost,exact.invalid,A\nhost-suffix,suffix.invalid,route\nip-cidr,192.0.2.0/24,direct\nfinal,proxy\n[rewrite_local]\n[server_remote]\n";

#[test]
fn quantumult_x_local_filters_static_policies_and_declared_dns_use_real_source_names() {
    let projected = project(&source(QX)).unwrap();
    assert!(super::super::node_only_fallback_allowed("ini", &source(QX)));
    assert_eq!(
        projected["rules"],
        json!([
            "DOMAIN,exact.invalid,A",
            "DOMAIN-SUFFIX,suffix.invalid,route",
            "IP-CIDR,192.0.2.0/24,DIRECT",
            "MATCH,PROXY"
        ])
    );
    assert_eq!(
        projected["groups"],
        json!([{"name":"route","type":"select","proxies":["A","DIRECT"]},{"name":"PROXY","type":"select","proxies":["A"]}])
    );
    assert_eq!(
        projected["dns"],
        json!({"mode":2,"servers":"192.0.2.53","encrypted":"","hosts":[{"name":"exact.invalid","value":"192.0.2.99"}],"useHosts":true,"respectRules":false,"queryFamily":"ipv4_only"})
    );
    assert_eq!(
        projected["importMetadata"]["preservedGeneral"],
        json!(["server_check_timeout", "server_check_url"])
    );
}

#[test]
fn quantumult_x_encrypted_dns_never_falls_back_to_ignored_plain_servers() {
    let document = QX.replace("no-system\n", "").replace(
        "server=192.0.2.53",
        "server=192.0.2.53\ndoh-server=https://192.0.2.54/dns-query",
    );
    let projected = project(&source(&document)).unwrap();
    assert_eq!(projected["dns"]["mode"], 0);
    assert_eq!(projected["dns"]["servers"], "");
    assert_eq!(
        projected["dns"]["encrypted"],
        "https://192.0.2.54/dns-query"
    );
    assert_eq!(
        project(&source(&QX.replace("no-system\n", "")))
            .unwrap_err()
            .code,
        "ProfileQuantumultSystemDnsUnsupported"
    );
    assert_eq!(
        project(&source(
            &document.replace("https://192.0.2.54/dns-query", "192.0.2.54")
        ))
        .unwrap_err()
        .code,
        "ProfileIniDnsTransportMismatch"
    );
}

#[test]
fn quantumult_x_does_not_guess_missing_nodes_automatic_scores_dns_reject_or_scripts() {
    for (input, code) in [
        (
            QX.replace("route,A,direct", "route,missing,direct"),
            "ProfileIniUnknownPolicy",
        ),
        (
            QX.replace("static=route", "available=route"),
            "ProfileIniGroupUnsupported",
        ),
        (
            QX.replace("host,exact.invalid,A", "host,exact.invalid,reject"),
            "ProfileQuantumultDnsRejectUnsupported",
        ),
        (
            QX.replace("static=route,A,direct", "static=route,proxy,route"),
            "ProfileIniGroupCycle",
        ),
        (
            format!("{QX}[task_local]\nevent-interaction https://private.invalid/script.js"),
            "ProfileIniUnsafeSection",
        ),
        (
            format!("{QX}[mitm]\np12=PRIVATE"),
            "ProfileIniUnsafeSection",
        ),
    ] {
        let error = project(&source(&input)).unwrap_err();
        assert_eq!(error.code, code);
        assert!(!format!("{error:?}").contains("PRIVATE"));
    }
}

#[test]
fn ini_duplicates_unknown_policies_cycles_and_ambiguous_defaults_fail_atomically() {
    for input in [
        SOURCE.replace("ipv6=false", "ipv6=false\nipv6=true"),
        SOURCE.replace("ipv6=false\n", ""),
        SOURCE.replace("dns-server=192.0.2.53,192.0.2.54", "dns-server=system"),
        SOURCE.replace(
            "dns-server=192.0.2.53,192.0.2.54",
            "dns-server=192.0.2.53\ndoh-server=https://dns.invalid/dns-query",
        ),
        SOURCE.replace("route = select,A,DIRECT", "route = select,missing,DIRECT"),
        SOURCE.replace("route = select,A,DIRECT", "route = select,A,A"),
        SOURCE.replace("route = select,A,DIRECT", "route = select,nested,DIRECT"),
        SOURCE.replace("route = select,A,DIRECT", "route = url-test,A,DIRECT"),
        SOURCE.replace(
            "IP-CIDR,192.0.2.0/24,nested,no-resolve",
            "IP-CIDR,\"192.0.2.0/24,DIRECT\",nested,no-resolve",
        ),
        SOURCE.replace("FINAL,route", "FINAL,route\nDOMAIN,late.invalid,DIRECT"),
        SOURCE.replace("DIRECT = direct", "Custom = direct"),
        SOURCE.replace("exact.invalid=192.0.2.99", "*.invalid=192.0.2.99"),
        SOURCE.replace("exact.invalid=192.0.2.99", "exact.invalid=alias.invalid"),
    ] {
        assert!(project(&source(&input)).is_err());
    }
}
