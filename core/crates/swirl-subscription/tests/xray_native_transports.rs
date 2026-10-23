//! Offline import and archive invariants. Official data-plane receipts live in
//! docs/evidence/x14-a5-imported-transports; these tests make no network claim.
use serde_json::{Value, json};
use swirl_subscription::{
    Config,
    xray::{
        InputSource,
        convert::{ConvertedDocument, NativeStatus, import_document},
    },
};

fn source(protocol: &str, network: &str, settings: Value) -> Value {
    let mut stream = json!({"network":network,"security":"tls",
        "tlsSettings":{"serverName":"peer.invalid","alpn":[if network == "httpupgrade" {"http/1.1"} else {"h2"}]}});
    stream[match network {
        "grpc" => "grpcSettings",
        "h2" => "httpSettings",
        "httpupgrade" => "httpupgradeSettings",
        "xhttp" => "xhttpSettings",
        _ => unreachable!(),
    }] = settings;
    let settings = if protocol == "trojan" {
        json!({"servers":[{"address":"127.0.0.1","port":443,"password":"fixture"}]})
    } else {
        json!({"vnext":[{"address":"127.0.0.1","port":443,
            "users":[{"id":"00112233-4455-6677-8899-aabbccddeeff","encryption":"none"}]}]})
    };
    json!({"outbounds":[{"protocol":protocol,"settings":settings,"streamSettings":stream}]})
}

#[test]
fn persisted_transport_options_survive_exact_source_archive_and_native_roundtrip() {
    for (protocol, network, settings, expected) in [
        (
            "vless",
            "grpc",
            json!({"authority":"front.invalid","serviceName":"svc","multiMode":false,"user_agent":"fixture-agent"}),
            json!({"type":"grpc","config":{"authority":"front.invalid","service_name":"svc","mode":"tun","headers":[["user-agent","fixture-agent"]]}}),
        ),
        (
            "trojan",
            "grpc",
            json!({"serviceName":"svc","multiMode":true}),
            json!({"type":"grpc","config":{"authority":"peer.invalid","service_name":"svc","mode":"tun_multi","headers":[]}}),
        ),
        (
            "vless",
            "h2",
            json!({"host":["front.invalid"],"path":"/h2","headers":{"X-Fixture":["one","two"]}}),
            json!({"type":"http2","config":{"host":"front.invalid","path":"/h2","headers":[["X-Fixture","one"],["X-Fixture","two"]]}}),
        ),
        (
            "vless",
            "httpupgrade",
            json!({"host":"front.invalid","path":"/upgrade","headers":{"X-Fixture":"one"}}),
            json!({"type":"httpupgrade","config":{"host":"front.invalid","path":"/upgrade","headers":[["X-Fixture","one"]]}}),
        ),
        (
            "vless",
            "xhttp",
            json!({"host":"front.invalid","path":"/split","mode":"stream-one"}),
            json!({"type":"xhttp","config":{"host":"front.invalid","path":"/split","mode":"stream-one","headers":[]}}),
        ),
    ] {
        let raw = serde_json::to_vec_pretty(&source(protocol, network, settings)).unwrap();
        let imported = import_document(&raw, InputSource::Clipboard).unwrap();
        let restored = ConvertedDocument::restore(&imported.save().unwrap()).unwrap();
        assert_eq!(restored.raw_json(), raw);
        assert_eq!(
            restored.nodes()[0].native_status(),
            NativeStatus::Executable,
            "{:?}",
            restored.nodes()[0].diagnostics()
        );
        assert!(!restored.nodes()[0].network_verified());
        let native = restored
            .native_config(0, "127.0.0.1:0".parse().unwrap())
            .unwrap();
        let value = serde_json::to_value(&native).unwrap();
        assert_eq!(value["nodes"][0]["outbound"]["transport"], expected);
        let reparsed = Config::parse(&serde_json::to_vec(&value).unwrap()).unwrap();
        assert_eq!(serde_json::to_value(reparsed).unwrap(), value);
    }
}

#[test]
fn unimplemented_transport_controls_and_conflicting_security_never_export() {
    for (network, settings) in [
        ("grpc", json!({"serviceName":"s","idle_timeout":1})),
        (
            "grpc",
            json!({"serviceName":"s","permit_without_stream":true}),
        ),
        ("h2", json!({"host":["one.invalid","two.invalid"]})),
        ("httpupgrade", json!({"path":"/upgrade?%65%64=2048"})),
        ("httpupgrade", json!({"acceptProxyProtocol":true})),
        ("xhttp", json!({"mode":"auto"})),
        ("xhttp", json!({"mode":"stream-up"})),
        ("xhttp", json!({"mode":"packet-up"})),
        ("xhttp", json!({"mode":"stream-one","extra":{"xmux":{}}})),
        (
            "xhttp",
            json!({"mode":"stream-one","headers":{"Content-Type":"fixture"}}),
        ),
    ] {
        let raw = serde_json::to_vec(&source("vless", network, settings)).unwrap();
        let imported = import_document(&raw, InputSource::File).unwrap();
        assert!(
            imported
                .native_config(0, "127.0.0.1:0".parse().unwrap())
                .is_err(),
            "{network}"
        );
        assert_eq!(imported.raw_json(), raw);
    }
    let mistyped = serde_json::to_vec(&source(
        "vless",
        "grpc",
        json!({"serviceName":"s","multiMode":"false"}),
    ))
    .unwrap();
    assert!(import_document(&mistyped, InputSource::File).is_err());
    let mut value = source("vless", "grpc", json!({"serviceName":"s"}));
    value["outbounds"][0]["settings"]["vnext"][0]["users"][0]["flow"] = json!("xtls-rprx-vision");
    let imported =
        import_document(&serde_json::to_vec(&value).unwrap(), InputSource::File).unwrap();
    assert!(
        imported
            .native_config(0, "127.0.0.1:0".parse().unwrap())
            .is_err()
    );
}
