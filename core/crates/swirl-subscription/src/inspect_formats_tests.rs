use super::*;
use crate::WebSocket;

#[test]
fn loon_vmess_positional_cipher_and_uuid_preserve_typed_outbound() {
    for (options, tls, websocket) in [
        ("transport=tcp,over-tls=false", None, None),
        (
            "transport=ws,path=/authored,host=cdn.fixture.invalid,over-tls=true,tls-name=secure.fixture.invalid,alterId=0,fast-open=false",
            Some(Tls {
                server_name: "secure.fixture.invalid".into(),
                alpn: vec![],
                ca_der_base64: None,
            }),
            Some(WebSocket {
                host: "cdn.fixture.invalid".into(),
                path: "/authored".into(),
            }),
        ),
    ] {
        let input = format!(
            "[Proxy]\nAuthored = vmess,edge.fixture.invalid,8443,aes-128-gcm,\"00112233-4455-4677-8899-aabbccddeeff\",{options}"
        );
        let expected = Outbound::Vmess {
            host: "edge.fixture.invalid".into(),
            port: 8443,
            uuid: "00112233-4455-4677-8899-aabbccddeeff".into(),
            alter_id: 0,
            security: "aes-128-gcm".into(),
            tls,
            websocket,
        };
        for body in [
            input.as_bytes().to_vec(),
            STANDARD.encode(&input).into_bytes(),
        ] {
            let result = inspect(&body);
            assert!(result.report.parsed);
            assert_eq!(result.report.nodes.len(), 1);
            assert!(
                result.report.nodes[0].native_tcp_candidate,
                "{}",
                result.report.nodes[0].diagnostic
            );
            assert_eq!(
                serde_json::to_value(result.tcp_candidates[0].as_ref().unwrap()).unwrap(),
                serde_json::to_value(&expected).unwrap()
            );
            assert_eq!(result.original, body);
            assert_eq!(
                result.originals[0]["raw-ini"],
                input.lines().nth(1).unwrap()
            );
        }
    }
}

#[test]
fn loon_http_positional_authentication_retains_quoted_delimiters_and_tls() {
    for (protocol, tls) in [
        ("http", None),
        (
            "https",
            Some(Tls {
                server_name: "edge.fixture.invalid".into(),
                alpn: vec![],
                ca_der_base64: None,
            }),
        ),
    ] {
        let input = format!(
            "[Proxy]\nAuthored = {protocol},edge.fixture.invalid,8443,\"user,with+percent%25\",\"secret=with:+percent%25\""
        );
        let result = inspect(input.as_bytes());
        assert!(result.report.parsed);
        assert!(
            result.report.nodes[0].native_tcp_candidate,
            "{}",
            result.report.nodes[0].diagnostic
        );
        let expected = Outbound::HttpConnect {
            host: "edge.fixture.invalid".into(),
            port: 8443,
            auth: Some(Credentials {
                username: "user,with+percent%25".into(),
                password: "secret=with:+percent%25".into(),
            }),
            tls,
        };
        assert_eq!(
            serde_json::to_value(result.tcp_candidates[0].as_ref().unwrap()).unwrap(),
            serde_json::to_value(expected).unwrap()
        );
        assert_eq!(result.original, input.as_bytes());
    }
}

#[test]
fn loon_positional_alias_conflicts_and_unsupported_requirements_never_become_candidates() {
    let vmess = "[Proxy]\nAuthored = vmess,edge.fixture.invalid,8443,aes-128-gcm,\"00112233-4455-4677-8899-aabbccddeeff\"";
    for suffix in [
        ",uuid=ffeeddcc-bbaa-4988-8766-554433221100",
        ",alterId=broken",
        ",alterId=1",
        ",udp=true",
        ",fast-open=invalid",
        ",transport=grpc",
        ",future-option=retained",
    ] {
        let input = format!("{vmess}{suffix}");
        let result = inspect(input.as_bytes());
        assert!(result.tcp_candidates.iter().all(Option::is_none));
        assert_eq!(result.original, input.as_bytes());
    }
    for suffix in [",username=other", ",password=other"] {
        let input =
            format!("[Proxy]\nAuthored = http,edge.fixture.invalid,8443,user,secret{suffix}");
        let result = inspect(input.as_bytes());
        assert!(!result.report.parsed);
        assert_eq!(result.report.error, Some("DuplicateIniParameter"));
        assert_eq!(result.original, input.as_bytes());
    }
    let input = b"[Proxy]\nAuthored = http,edge.fixture.invalid,8443,\"user:ambiguous\",secret";
    let result = inspect(input);
    assert!(result.report.parsed);
    assert!(result.tcp_candidates[0].is_none());
    assert_eq!(result.original, input);
}

#[test]
fn content_detection_does_not_treat_every_client_as_clash() {
    let cases: &[(&[u8],&str)] = &[
        (b"proxies:\n - {name: fixture, type: ss, server: example.org, port: 443, cipher: aes-128-gcm, password: synthetic}","clash-yaml"),
        (b"[Proxy]\nfixture = Shadowsocks, example.org, 443, aes-128-gcm, synthetic","ini"),
        (b"[Proxy]\nfixture = ss, example.org, 443, encrypt-method=aes-128-gcm, password=synthetic","ini"),
        (b"[server_local]\nshadowsocks = example.org:443, method=aes-128-gcm, password=synthetic, tag=Quantumult fixture","ini"),
        (b"STATUS=1\nss://YWVzLTEyOC1nY206c3ludGhldGlj@example.org:443#fixture","shadowrocket"),
        (b"# exported links\nss://YWVzLTEyOC1nY206c3ludGhldGlj@example.org:443#fixture\n// footer","uri-list"),
        (br#"{"outbounds":[{"tag":"fixture","type":"hysteria2","server":"example.org","server_port":443,"password":"synthetic","tls":{"enabled":true,"server_name":"example.org"}}]}"#,"sing-box-json"),
    ];
    for (input, format) in cases {
        let inspected = inspect(input);
        assert!(
            inspected.report.parsed,
            "{format}: {:?}",
            inspected.report.error
        );
        assert_eq!(inspected.report.format, *format);
        assert_eq!(inspected.report.nodes.len(), 1);
        assert!(
            inspected.report.nodes[0].native_tcp_candidate,
            "{format}: {}",
            inspected.report.nodes[0].diagnostic
        );
        assert_eq!(inspected.original, *input);
    }
    let qx = inspect(cases[3].0);
    assert_eq!(qx.originals[0]["name"], "Quantumult fixture");
}

#[test]
fn base64_envelope_retains_singbox_quic_dialect_and_security() {
    let input = br#"{"outbounds":[{"tag":"fixture","type":"hysteria2","server":"example.org","server_port":443,"password":"synthetic","tls":{"enabled":true,"server_name":"authenticated.invalid"}}]}"#;
    let raw = inspect(input);
    let wrapped = inspect(STANDARD.encode(input).as_bytes());
    assert_eq!(wrapped.report.format, "base64");
    assert!(
        wrapped.report.nodes[0].native_tcp_candidate,
        "{}",
        wrapped.report.nodes[0].diagnostic
    );
    assert_eq!(
        serde_json::to_value(&wrapped.tcp_candidates[0]).unwrap(),
        serde_json::to_value(&raw.tcp_candidates[0]).unwrap()
    );
    let output = serde_json::to_value(&wrapped.tcp_candidates[0]).unwrap();
    assert_eq!(output["tls"]["server_name"], "authenticated.invalid");
}

#[test]
fn error_pages_and_partial_client_documents_never_become_successful_imports() {
    for (input, error) in [
        (
            b"<html>login?token=PRIVATE</html>".as_slice(),
            "SubscriptionResponseIsHtml",
        ),
        (b"STATUS=1".as_slice(), "ShadowrocketStatusHeader"),
        (
            b"\xef\xbb\xbf\xef\xbb\xbfss://user@example.org:443".as_slice(),
            "DocumentControlCharacter",
        ),
    ] {
        let result = inspect(input);
        assert!(!result.report.parsed);
        assert_eq!(result.report.error, Some(error));
        assert!(result.tcp_candidates.is_empty());
        assert!(
            !serde_json::to_string(&result.report)
                .unwrap()
                .contains("PRIVATE")
        );
    }
    let duplicate = inspect(b"[server_local]\nshadowsocks = example.org:443, method=aes-128-gcm, password=synthetic, tag=one, tag=two");
    assert_eq!(duplicate.report.error, Some("DuplicateIniParameter"));
}
