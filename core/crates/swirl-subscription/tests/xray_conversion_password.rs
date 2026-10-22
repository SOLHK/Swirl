//! Synthetic public protocol conversion regressions; no network or real credentials.
use serde_json::{Value, json};
use swirl_subscription::xray::InputSource;
use swirl_subscription::xray::convert::{
    Authentication, ConvertedDocument, Protocol, ValidationStatus, import_document,
};

fn source(protocol: &str) -> Value {
    let mut server = json!({"address":"proxy.example.invalid","port":443,"password":"  SYNTHETIC_密碼\u{0000}  ","level":0,"email":"fixture@example.invalid"});
    if protocol == "shadowsocks" {
        server["method"] = json!("aes-256-gcm");
    }
    json!({"protocol":protocol,"settings":{"servers":[server]},"streamSettings":{"network":"ws","security":"tls",
        "tlsSettings":{"serverName":"sni.example.invalid","alpn":["http/1.1"]},"wsSettings":{"path":"/private","headers":{"Host":"ws.example.invalid"}}}})
}
fn roundtrip(value: &Value) -> ConvertedDocument {
    let a = import_document(&serde_json::to_vec(value).unwrap(), InputSource::File).unwrap();
    let b = ConvertedDocument::restore(&a.save().unwrap()).unwrap();
    assert_eq!(a.raw_json(), b.raw_json());
    assert_eq!(a.nodes().len(), b.nodes().len());
    for (x, y) in a.nodes().iter().zip(b.nodes()) {
        assert_eq!(x.protocol(), y.protocol());
        assert!(x.authentication() == y.authentication());
        assert!(x.endpoint() == y.endpoint());
        assert_eq!(x.source(), y.source());
        assert_eq!(x.diagnostics(), y.diagnostics());
    }
    b
}
#[test]
fn trojan_and_ss_password_algorithm_level_email_and_transport_roundtrip() {
    for p in ["trojan", "shadowsocks"] {
        let s = source(p);
        let d = roundtrip(&s);
        let n = &d.nodes()[0];
        assert_eq!(
            n.protocol(),
            if p == "trojan" {
                Protocol::Trojan
            } else {
                Protocol::Shadowsocks
            }
        );
        assert!(
            matches!(n.authentication(),Authentication::Password {password:Some(p),level:Some(0),email:Some(e),..}
            if p=="  SYNTHETIC_密碼\u{0000}  " && e=="fixture@example.invalid")
        );
        assert_eq!(d.stream_settings(0), s.get("streamSettings"));
        assert!(!format!("{n:?} {:?}", n.authentication()).contains("SYNTHETIC"));
    }
}
#[test]
fn ss_aead_and_unsupported_ciphers_are_retained_not_replaced() {
    for method in [
        "aes-128-gcm",
        "aes-256-gcm",
        "chacha20-ietf-poly1305",
        "2022-blake3-aes-128-gcm",
        "aes-128-cfb",
        "future-cipher",
    ] {
        let mut s = source("shadowsocks");
        s["settings"]["servers"][0]["method"] = json!(method);
        let d = roundtrip(&s);
        assert!(
            matches!(d.nodes()[0].authentication(),Authentication::Password {method:Some(m),..} if m==method)
        );
        if !["aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305"].contains(&method) {
            assert!(
                d.nodes()[0]
                    .diagnostics()
                    .iter()
                    .any(|x| x.code.starts_with("ShadowsocksCipher"))
            );
        }
    }
}
#[test]
fn multiple_password_servers_and_flat_form_preserve_source_identity() {
    for p in ["trojan", "shadowsocks"] {
        let mut s = source(p);
        let mut second = s["settings"]["servers"][0].clone();
        second["password"] = json!("SECOND_SYNTHETIC");
        second["port"] = json!(8443);
        s["settings"]["servers"]
            .as_array_mut()
            .unwrap()
            .push(second);
        let d = roundtrip(&s);
        assert_eq!(d.nodes().len(), 2);
        assert_eq!(d.nodes()[1].source().server_index, Some(1));
        assert_eq!(d.nodes()[1].source().user_index, None);
        assert!(
            matches!(d.nodes()[1].authentication(),Authentication::Password {password:Some(p),..} if p=="SECOND_SYNTHETIC")
        );
        s["settings"] = s["settings"]["servers"][0].clone();
        let d = roundtrip(&s);
        assert_eq!(d.nodes().len(), 1);
        assert_eq!(d.nodes()[0].source().server_index, None);
    }
}
#[test]
fn empty_missing_password_and_method_are_invalid_wrong_type_is_rejected_by_a() {
    for p in ["trojan", "shadowsocks"] {
        for missing in [false, true] {
            let mut s = source(p);
            if missing {
                s["settings"]["servers"][0]
                    .as_object_mut()
                    .unwrap()
                    .remove("password");
            } else {
                s["settings"]["servers"][0]["password"] = json!("");
            }
            assert_eq!(
                roundtrip(&s).nodes()[0].validation(),
                ValidationStatus::Invalid
            );
        }
        let mut s = source(p);
        s["settings"]["servers"][0]["password"] = json!(42);
        assert!(import_document(&serde_json::to_vec(&s).unwrap(), InputSource::File).is_err());
    }
    let mut s = source("shadowsocks");
    s["settings"]["servers"][0]["method"] = json!("");
    assert!(
        roundtrip(&s).nodes()[0]
            .diagnostics()
            .iter()
            .any(|d| d.code == "MissingShadowsocksMethod")
    );
}
#[test]
fn long_passwords_are_kept_in_full_and_not_claimed_native() {
    let password = "x".repeat(2049);
    let mut s = source("trojan");
    s["settings"]["servers"][0]["password"] = json!(password);
    let d = roundtrip(&s);
    assert!(
        matches!(d.nodes()[0].authentication(),Authentication::Password {password:Some(p),..} if p.len()==2049)
    );
    assert!(
        d.nodes()[0]
            .diagnostics()
            .iter()
            .any(|d| d.code == "NativePasswordLengthUnsupported")
    );
}
#[test]
fn removed_trojan_flow_and_out_of_range_byte_level_are_explicit() {
    let mut s = source("trojan");
    s["settings"]["servers"][0]["flow"] = json!("xtls-rprx-vision");
    assert!(
        roundtrip(&s).nodes()[0]
            .diagnostics()
            .iter()
            .any(|d| d.code == "TrojanFlowRemoved")
    );
    for p in ["trojan", "shadowsocks"] {
        let mut s = source(p);
        s["settings"]["servers"][0]["level"] = json!(256);
        assert_eq!(
            roundtrip(&s).nodes()[0].validation(),
            ValidationStatus::Invalid
        );
    }
}
#[test]
fn ss_plugins_uot_and_unknown_secret_keys_survive_with_blocking_diagnostics() {
    let mut s = source("shadowsocks");
    s["settings"]["servers"][0]["uot"] = json!(true);
    s["settings"]["servers"][0]["SYNTHETIC_PRIVATE_KEY"] = json!({"plugin":"not-a-command"});
    let d = roundtrip(&s);
    assert_eq!(d.configuration(), &s);
    assert_eq!(d.nodes()[0].validation(), ValidationStatus::Unverified);
    assert!(
        !serde_json::to_string(d.nodes()[0].diagnostics())
            .unwrap()
            .contains("SYNTHETIC_PRIVATE_KEY")
    );
}

#[test]
fn official_ss_boolean_extensions_preserve_intent_and_reject_wrong_types() {
    for (key, code) in [
        ("ivCheck", "ShadowsocksIvCheckUnsupported"),
        ("ota", "ShadowsocksOtaUnsupported"),
    ] {
        for enabled in [false, true] {
            let mut s = source("shadowsocks");
            s["settings"]["servers"][0][key] = json!(enabled);
            let d = roundtrip(&s);
            assert_eq!(d.configuration(), &s);
            assert_eq!(d.nodes()[0].validation(), ValidationStatus::Valid);
            assert_eq!(
                d.nodes()[0].diagnostics().iter().any(|d| d.code == code),
                enabled || key == "ivCheck"
            );
        }
        for wrong in [json!(null), json!(0), json!("false"), json!({})] {
            let mut s = source("shadowsocks");
            s["settings"]["servers"][0][key] = wrong;
            let d = roundtrip(&s);
            assert_eq!(d.configuration(), &s);
            assert_eq!(d.nodes()[0].validation(), ValidationStatus::Invalid);
            assert!(
                d.nodes()[0]
                    .diagnostics()
                    .iter()
                    .any(|d| d.code == "ExpectedBoolean")
            );
        }
    }
}

#[test]
fn official_ss_cipher_aliases_and_xchacha_are_not_rewritten_to_a_native_method() {
    for method in [
        "aead_aes_128_gcm",
        "aead_aes_256_gcm",
        "aead_chacha20_poly1305",
        "xchacha20-poly1305",
        "xchacha20-ietf-poly1305",
        "aead_xchacha20_poly1305",
    ] {
        let mut s = source("shadowsocks");
        s["settings"]["servers"][0]["method"] = json!(method);
        let d = roundtrip(&s);
        assert!(
            matches!(d.nodes()[0].authentication(), Authentication::Password { method: Some(m), .. } if m == method)
        );
        assert!(
            d.nodes()[0]
                .diagnostics()
                .iter()
                .any(|d| d.code == "ShadowsocksCipherUnsupported")
        );
        assert!(!d.nodes()[0].network_verified());
    }
}

#[test]
fn trojan_tls_ws_and_mux_are_retained_independently_of_password_projection() {
    let mut s = source("trojan");
    s["mux"] = json!({"enabled": true, "concurrency": 8});
    s["streamSettings"]["wsSettings"]["headers"]["Authorization"] = json!("SYNTHETIC_HEADER");
    let d = roundtrip(&s);
    assert_eq!(d.stream_settings(0), s.get("streamSettings"));
    assert_eq!(d.mux(0), s.get("mux"));
    assert!(!format!("{:?}", d.nodes()[0]).contains("SYNTHETIC_HEADER"));
}
