use super::*;
use serde_json::json;

fn raw() -> serde_json::Value {
    json!({"name":"public fixture","type":"anytls","server":"fixture.test","port":443,
        "password":"public-test-password","sni":"tls.fixture.test","alpn":["h2"],"pcs":""})
}

#[test]
fn anytls_import_preserves_credentials_sni_and_declared_udp() {
    for udp in [false, true] {
        let mut value = raw();
        value["udp"] = json!(udp);
        let result = AnyTls::from_raw(&value).unwrap();
        assert_eq!(
            (
                result.host.as_str(),
                result.port,
                result.password.as_str(),
                result.tls.server_name.as_str(),
                result.tls.alpn.as_slice(),
                result.udp
            ),
            (
                "fixture.test",
                443,
                "public-test-password",
                "tls.fixture.test",
                ["h2".to_owned()].as_slice(),
                udp
            )
        );
        let output =
            crate::inspect::inspect(&serde_json::to_vec(&json!({"proxies":[value]})).unwrap());
        let node = &output.report.nodes[0];
        assert!(node.native_tcp_candidate);
        assert_eq!(node.native_udp_supported, udp);
        assert_eq!(
            (
                node.tls,
                node.unrecognized_fields,
                node.real_network_verified
            ),
            ("tls", 0, false)
        );
    }
}

#[test]
fn anytls_security_and_unmapped_options_fail_closed() {
    for (skip, verify, expected_insecure) in [
        (None, None, false),
        (Some(json!(false)), None, false),
        (Some(json!(true)), None, true),
        (None, Some(json!(true)), false),
        (None, Some(json!(false)), true),
        (Some(json!(true)), Some(json!(false)), true),
        (Some(json!(false)), Some(json!(true)), false),
    ] {
        let mut input = raw();
        if let Some(skip) = skip {
            input["skip-cert-verify"] = skip;
        }
        if let Some(verify) = verify {
            input["tls-verification"] = verify;
        }
        let parsed = AnyTls::from_raw(&input).unwrap();
        assert_eq!(parsed.tls.insecure, expected_insecure);
    }
    for (skip, verify) in [(true, true), (false, false)] {
        let mut conflicting = raw();
        conflicting["skip-cert-verify"] = json!(skip);
        conflicting["tls-verification"] = json!(verify);
        assert_eq!(
            AnyTls::from_raw(&conflicting).err(),
            Some("AnyTlsTlsParameters")
        );
    }
    for (key, value, code) in [
        ("skip-cert-verify", json!("false"), "AnyTlsTlsParameters"),
        ("skip-cert-verify", json!(1), "AnyTlsTlsParameters"),
        ("tls-verification", json!("false"), "AnyTlsTlsParameters"),
        (
            "pcs",
            json!("pin-request"),
            "AnyTlsCertificatePinsUnsupported",
        ),
        (
            "client-fingerprint",
            json!("chrome"),
            "AnyTlsOptionsUnsupported",
        ),
        ("network", json!("ws"), "AnyTlsTransportUnsupported"),
        ("tls", json!(false), "AnyTlsTransportUnsupported"),
        ("alpn", json!([""]), "AnyTlsTlsParameters"),
        ("alpn", json!([5]), "AnyTlsAlpn"),
        ("udp", json!("true"), "AnyTlsUdp"),
        ("server_port", json!(8443), "AnyTlsPort"),
        ("servername", json!("other.test"), "AnyTlsTlsNames"),
        ("type", json!("trojan"), "AnyTlsProtocol"),
    ] {
        let mut input = raw();
        input[key] = value;
        assert_eq!(AnyTls::from_raw(&input).err(), Some(code), "field {key}");
    }
}

#[test]
fn anytls_optional_tcp_optimization_has_an_explicit_diagnostic() {
    let mut input = raw();
    input["tfo"] = json!(true);
    let output = crate::inspect::inspect(&serde_json::to_vec(&json!({"proxies":[input]})).unwrap());
    let node = &output.report.nodes[0];
    assert!(node.native_tcp_candidate);
    assert!(node.native_udp_supported);
    assert_eq!(node.diagnostic, "TcpFastOpenFallbackToTcp");
}
