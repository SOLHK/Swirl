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
        "#!MANAGED-CONFIG https://private.invalid?token=PRIVATE interval=3600",
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
