use super::*;

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
