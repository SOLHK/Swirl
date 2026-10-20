//! Source-preserving profile mapping tests; these do not claim network success.
use crate::{Outbound, inspect::inspect};
use base64::{
    Engine,
    engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD},
};
use serde_json::{Value, json};

fn sing_box(fingerprint: &str) -> Value {
    json!({"type":"vless","tag":"fixture","server":"proxy.invalid","server_port":443,
        "uuid":"00112233-4455-6677-8899-aabbccddeeff","flow":"xtls-rprx-vision",
        "tls":{"enabled":true,"server_name":"camouflage.invalid",
            "utls":{"enabled":true,"fingerprint":fingerprint},
            "reality":{"enabled":true,"public_key":URL_SAFE_NO_PAD.encode([9;32]),"short_id":"a1B2"}}})
}

fn document(source: &Value) -> String {
    json!({"outbounds":[source]}).to_string()
}

fn candidate(input: &str) -> Value {
    let parsed = inspect(input.as_bytes());
    assert_eq!(parsed.original, input.as_bytes());
    assert!(parsed.report.parsed);
    assert_eq!(parsed.report.nodes.len(), 1);
    assert!(
        parsed.report.nodes[0].native_tcp_candidate,
        "{}",
        parsed.report.nodes[0].diagnostic
    );
    assert!(!parsed.report.nodes[0].real_network_verified);
    let encoded = serde_json::to_vec(parsed.tcp_candidates[0].as_ref().unwrap()).unwrap();
    let restored: Outbound = serde_json::from_slice(&encoded).unwrap();
    serde_json::to_value(restored).unwrap()
}

fn rejected(source: &Value, diagnostic: &str) {
    let plain = document(source);
    for input in [plain.clone(), STANDARD.encode(plain)] {
        let parsed = inspect(input.as_bytes());
        assert!(parsed.report.parsed);
        assert_eq!(parsed.original, input.as_bytes());
        assert_eq!(parsed.originals[0], *source);
        assert!(parsed.tcp_candidates[0].is_none());
        assert!(!parsed.report.nodes[0].native_tcp_candidate);
        assert!(!parsed.report.nodes[0].real_network_verified);
        assert_eq!(parsed.report.nodes[0].diagnostic, diagnostic);
        let report = serde_json::to_string(&parsed.report).unwrap();
        for private in [
            "proxy.invalid",
            "camouflage.invalid",
            "00112233-4455-6677-8899-aabbccddeeff",
            "fixture-private",
            &URL_SAFE_NO_PAD.encode([9; 32]),
        ] {
            assert!(!report.contains(private));
        }
    }
}

#[test]
fn browser_profiles_survive_uri_yaml_singbox_xray_and_ir_without_renaming() {
    let key = URL_SAFE_NO_PAD.encode([9; 32]);
    for fingerprint in ["chrome", "chrome_133"] {
        for explicit_alpn in [false, true] {
            let mut source = sing_box(fingerprint);
            if explicit_alpn {
                source["tls"]["alpn"] = json!(["h2", "http/1.1"]);
            }
            let expected = candidate(&document(&source));
            let uri_alpn = if explicit_alpn {
                "&alpn=h2,http%2F1.1"
            } else {
                ""
            };
            let yaml_alpn = if explicit_alpn {
                "    alpn: [h2, http/1.1]\n"
            } else {
                ""
            };
            let uri = format!(
                "vless://00112233-4455-6677-8899-aabbccddeeff@proxy.invalid:443?security=reality&sni=camouflage.invalid&fp={fingerprint}&pbk={key}&sid=a1B2&type=tcp&flow=xtls-rprx-vision{uri_alpn}"
            );
            let yaml = format!(
                "proxies:\n  - type: vless\n    server: proxy.invalid\n    port: 443\n    uuid: 00112233-4455-6677-8899-aabbccddeeff\n    tls: true\n    servername: camouflage.invalid\n    client-fingerprint: {fingerprint}\n    reality-opts: {{public-key: {key}, short-id: a1B2}}\n    flow: xtls-rprx-vision\n{yaml_alpn}"
            );
            for input in [
                uri.clone(),
                STANDARD.encode(&uri),
                yaml,
                STANDARD.encode(document(&source)),
            ] {
                assert_eq!(candidate(&input), expected);
            }
            let parsed = inspect(document(&source).as_bytes());
            assert_eq!(parsed.originals[0], source);
            assert_eq!(inspect(uri.as_bytes()).originals[0]["raw-uri"], uri);
            assert_eq!(expected["reality"]["fingerprint"], fingerprint);
            assert_eq!(expected["reality"]["short_id"], "a1B2");
            assert_eq!(expected["flow"], "xtls-rprx-vision");
            assert!(expected["tls"].is_null() && expected["websocket"].is_null());
            if !explicit_alpn {
                // Xray's REALITY settings do not define an ALPN override.
                let xray = json!({"protocol":"vless","tag":"fixture",
                    "settings":{"address":"proxy.invalid","port":443,
                        "id":"00112233-4455-6677-8899-aabbccddeeff","encryption":"none","flow":"xtls-rprx-vision"},
                    "streamSettings":{"network":"raw","security":"reality",
                        "realitySettings":{"serverName":"camouflage.invalid","fingerprint":fingerprint,
                            "publicKey":key,"shortId":"a1B2"}}});
                assert_eq!(candidate(&document(&xray)), expected);
                assert_eq!(inspect(document(&xray).as_bytes()).originals[0], xray);
            }
        }
    }
}

#[test]
fn singbox_utls_requires_an_explicit_supported_browser_profile() {
    for fingerprint in [
        "rustls",
        "firefox",
        "safari",
        "random",
        "Chrome",
        "chrome_120",
        "",
    ] {
        rejected(&sing_box(fingerprint), "RealityFingerprintUnsupported");
    }
    let cases = [
        (json!({"enabled":true}), "RealityFingerprintRequired"),
        (
            json!({"enabled":true,"fingerprint":null}),
            "RealityFingerprintRequired",
        ),
        (
            json!({"enabled":false,"fingerprint":"chrome"}),
            "RealityFingerprintUnsupported",
        ),
        (
            json!({"fingerprint":"chrome"}),
            "RealityFingerprintUnsupported",
        ),
        (
            json!({"enabled":"true","fingerprint":"chrome"}),
            "RealityFingerprintUnsupported",
        ),
        (
            json!({"enabled":true,"fingerprint":"chrome","future":"fixture-private"}),
            "RealityUnmappedFields",
        ),
    ];
    for (utls, diagnostic) in cases {
        let mut source = sing_box("chrome");
        source["tls"]["utls"] = utls;
        rejected(&source, diagnostic);
    }
}

#[test]
fn source_fingerprint_and_alpn_aliases_cannot_overwrite_each_other() {
    let source = sing_box("chrome_133");
    let expected = candidate(&document(&source));
    for alias in ["fp", "client-fingerprint"] {
        let mut same = source.clone();
        same[alias] = json!("chrome_133");
        assert_eq!(candidate(&document(&same)), expected);
        for value in [json!("chrome"), json!("rustls"), Value::Null] {
            let mut conflict = same.clone();
            conflict[alias] = value;
            rejected(&conflict, "RealityConflictingFingerprint");
        }
    }
    let mut alpn = source;
    alpn["alpn"] = json!(["h2", "http/1.1"]);
    alpn["tls"]["alpn"] = json!(["h2", "http/1.1"]);
    assert_eq!(candidate(&document(&alpn))["reality"]["alpn"], alpn["alpn"]);
    alpn["tls"]["alpn"] = json!([]);
    rejected(&alpn, "ConflictingAlpn");
}

#[test]
fn browser_profile_alpn_is_fixed_while_native_rustls_keeps_custom_alpn() {
    for fingerprint in ["chrome", "chrome_133"] {
        for alpn in [
            json!(["h2"]),
            json!(["http/1.1"]),
            json!(["http/1.1", "h2"]),
            json!(["h2", "h2"]),
            json!([""]),
            json!(["custom"]),
        ] {
            let mut source = sing_box(fingerprint);
            source["tls"]["alpn"] = alpn;
            rejected(&source, "RealityFingerprintAlpnUnsupported");
        }
        let mut explicit_empty = sing_box(fingerprint);
        explicit_empty["tls"]["alpn"] = json!([]);
        assert_eq!(
            candidate(&document(&explicit_empty))["reality"]["alpn"],
            json!([])
        );
    }
    let mut native = sing_box("rustls");
    native["tls"].as_object_mut().unwrap().remove("utls");
    native["fp"] = json!("rustls");
    native["tls"]["alpn"] = json!(["custom"]);
    assert_eq!(
        candidate(&document(&native))["reality"]["alpn"],
        json!(["custom"])
    );
}
