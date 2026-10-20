//! Strict VLESS/REALITY mapping for sharing URIs, Clash YAML/JSON and sing-box
//! JSON. Original documents stay with Inspection; diagnostics contain no values.
use super::{Config, Limits, Node, NodeCapability, Outbound, Value, endpoint_port};
use crate::Reality;

const FIELDS: &[&str] = &[
    "type",
    "name",
    "tag",
    "server",
    "port",
    "server_port",
    "uuid",
    "raw-uri",
    "network",
    "security",
    "tls",
    "sni",
    "servername",
    "alpn",
    "flow",
    "encryption",
    "reality-opts",
    "pbk",
    "sid",
    "fp",
    "client-fingerprint",
    "udp",
    "tfo",
    "skip-cert-verify",
    "tls-verification",
];

pub(super) fn declared(raw: &Value) -> bool {
    raw.get("reality-opts").is_some()
        || raw.pointer("/tls/reality").is_some()
        || raw.get("security").and_then(Value::as_str) == Some("reality")
        || raw
            .pointer("/streamSettings/security")
            .and_then(Value::as_str)
            == Some("reality")
}

fn aliases<'a>(
    values: &[Option<&'a Value>],
    error: &'static str,
) -> Result<Option<&'a Value>, &'static str> {
    let first = values.iter().flatten().next().copied();
    if values.iter().flatten().any(|value| Some(*value) != first) {
        Err(error)
    } else {
        Ok(first)
    }
}

fn string(value: Option<&Value>, error: &'static str) -> Result<String, &'static str> {
    value
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or(error)
}

fn object_keys(value: &Value, allowed: &[&str]) -> Result<(), &'static str> {
    let object = value.as_object().ok_or("RealityParameterType")?;
    if object.keys().any(|key| !allowed.contains(&key.as_str())) {
        Err("RealityUnmappedFields")
    } else {
        Ok(())
    }
}

fn outbound(raw: &Value, family: &str) -> Result<Outbound, &'static str> {
    if family == "xray-v2ray-json" {
        return Err("RealityFormatUnsupported");
    }
    object_keys(raw, FIELDS)?;
    if raw
        .get("network")
        .is_some_and(|value| value.as_str() != Some("tcp"))
    {
        return Err("RealityTransportUnsupported");
    }
    if raw
        .get("security")
        .is_some_and(|value| value.as_str() != Some("reality"))
    {
        return Err("RealitySecurityConflict");
    }
    for key in ["udp", "tfo", "skip-cert-verify"] {
        if raw
            .get(key)
            .is_some_and(|value| value.as_bool() != Some(false))
        {
            return Err(match key {
                "udp" => "VlessUdpUnsupported",
                "tfo" => "TcpFastOpenNotImplemented",
                _ => "CertificateVerificationDisabledUnsupported",
            });
        }
    }
    if raw
        .get("tls-verification")
        .is_some_and(|value| value.as_bool() != Some(true))
    {
        return Err("CertificateVerificationDisabledUnsupported");
    }
    if let Some(tls) = raw.get("tls") {
        if tls.is_object() {
            object_keys(
                tls,
                &[
                    "enabled",
                    "server_name",
                    "alpn",
                    "insecure",
                    "reality",
                    "utls",
                ],
            )?;
            if tls.get("enabled").and_then(Value::as_bool) != Some(true) {
                return Err("RealitySecurityConflict");
            }
            if tls
                .get("insecure")
                .is_some_and(|value| value.as_bool() != Some(false))
            {
                return Err("CertificateVerificationDisabledUnsupported");
            }
        } else if tls.as_bool() != Some(true) {
            return Err("RealitySecurityConflict");
        }
    } else if raw.get("security").and_then(Value::as_str) != Some("reality") {
        return Err("RealitySecurityRequired");
    }
    if let Some(options) = raw.get("reality-opts") {
        object_keys(options, &["public-key", "short-id"])?;
    }
    if let Some(options) = raw.pointer("/tls/reality") {
        object_keys(options, &["enabled", "public_key", "short_id"])?;
        if options.get("enabled").and_then(Value::as_bool) != Some(true) {
            return Err("RealitySecurityConflict");
        }
    }
    if let Some(utls) = raw.pointer("/tls/utls") {
        object_keys(utls, &["enabled", "fingerprint"])?;
        // This path denotes a uTLS browser profile. Claiming native rustls is
        // uTLS would change an explicit source requirement.
        if utls.get("enabled").and_then(Value::as_bool) != Some(false)
            || utls.get("fingerprint").is_some()
        {
            return Err("RealityFingerprintUnsupported");
        }
    }
    let public_key = string(
        aliases(
            &[
                raw.get("pbk"),
                raw.pointer("/reality-opts/public-key"),
                raw.pointer("/tls/reality/public_key"),
            ],
            "RealityConflictingPublicKey",
        )?,
        "RealityPublicKey",
    )?;
    let short_id = string(
        aliases(
            &[
                raw.get("sid"),
                raw.pointer("/reality-opts/short-id"),
                raw.pointer("/tls/reality/short_id"),
            ],
            "RealityConflictingShortId",
        )?,
        "RealityShortId",
    )?;
    let fingerprint = string(
        aliases(
            &[raw.get("fp"), raw.get("client-fingerprint")],
            "RealityConflictingFingerprint",
        )?,
        "RealityFingerprintRequired",
    )?;
    let server_name = string(
        aliases(
            &[
                raw.get("sni"),
                raw.get("servername"),
                raw.pointer("/tls/server_name"),
            ],
            "RealityConflictingServerName",
        )?,
        "RealityServerName",
    )?;
    let alpn = aliases(
        &[raw.get("alpn"), raw.pointer("/tls/alpn")],
        "ConflictingAlpn",
    )?
    .map_or(Ok(Vec::new()), |value| {
        serde_json::from_value::<Vec<String>>(value.clone()).map_err(|_| "RealityAlpn")
    })?;
    if raw
        .get("encryption")
        .is_some_and(|value| value.as_str() != Some("none"))
    {
        return Err("VlessEncryptionUnsupported");
    }
    let flow = raw
        .get("flow")
        .map(|value| string(Some(value), "VlessFlowUnsupported"))
        .transpose()?;
    let result = Outbound::Vless {
        host: string(raw.get("server"), "VlessParameters")?,
        port: endpoint_port(raw)?,
        uuid: string(raw.get("uuid"), "VlessParameters")?,
        tls: None,
        websocket: None,
        reality: Some(Reality {
            server_name,
            public_key,
            short_id,
            fingerprint,
            alpn,
        }),
        flow,
    };
    Config {
        schema: 1,
        listen: "127.0.0.1:0".parse().expect("constant"),
        selected: "isolated".into(),
        nodes: vec![Node {
            id: "isolated".into(),
            outbound: result.clone(),
        }],
        rules: vec![],
        selectors: vec![],
        dns: Default::default(),
        inbound_auth: None,
        limits: Limits::default(),
    }
    .validate()?;
    Ok(result)
}

pub(super) fn inspect(
    raw: &Value,
    index: usize,
    family: &str,
) -> (NodeCapability, Option<Outbound>) {
    let (candidate, diagnostic) = match outbound(raw, family) {
        Ok(value) => (Some(value), "TcpCandidateNotYetVerified"),
        Err(error) => (None, error),
    };
    let transport = match raw.get("network") {
        None => "tcp",
        Some(value) if value.as_str() == Some("tcp") => "tcp",
        _ => "unsupported",
    };
    (
        NodeCapability {
            index,
            protocol: "vless",
            version: "0",
            transport,
            obfuscation: "none",
            tls: "reality",
            cipher: "none",
            udp_declared: raw.get("udp").and_then(Value::as_bool) == Some(true),
            unrecognized_fields: raw.as_object().map_or(1, |object| {
                object
                    .keys()
                    .filter(|key| !FIELDS.contains(&key.as_str()))
                    .count()
            }),
            native_tcp_candidate: candidate.is_some(),
            native_udp_supported: false,
            real_network_verified: false,
            diagnostic,
        },
        candidate,
    )
}

#[cfg(test)]
mod tests {
    use crate::{Outbound, inspect::inspect};
    use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
    use serde_json::{Value, json};

    fn node() -> Value {
        json!({"type":"vless","name":"native","server":"proxy.invalid","port":443,
            "uuid":"00112233-4455-6677-8899-aabbccddeeff","tls":true,"servername":"camouflage.invalid",
            "client-fingerprint":"rustls","reality-opts":{"public-key":URL_SAFE_NO_PAD.encode([9;32]),"short-id":"a1B2"},
            "network":"tcp","encryption":"none","alpn":["h2","http/1.1"]})
    }

    #[test]
    fn explicit_native_reality_survives_uri_json_yaml_and_ir_roundtrip() {
        let base = node();
        let key = base["reality-opts"]["public-key"].as_str().unwrap();
        let uri = format!(
            "vless://00112233-4455-6677-8899-aabbccddeeff@proxy.invalid:443?security=reality&sni=camouflage.invalid&fp=rustls&pbk={key}&sid=a1B2&type=tcp&encryption=none&alpn=h2,http%2F1.1"
        );
        let documents = [
            json!({"proxies":[base]}).to_string(),
            uri.clone(),
            format!(
                "proxies:\n  - type: vless\n    server: proxy.invalid\n    port: 443\n    uuid: 00112233-4455-6677-8899-aabbccddeeff\n    tls: true\n    servername: camouflage.invalid\n    client-fingerprint: rustls\n    reality-opts: {{public-key: {key}, short-id: a1B2}}\n    alpn: [h2, http/1.1]\n"
            ),
        ];
        for document in documents {
            let parsed = inspect(document.as_bytes());
            assert_eq!(parsed.original, document.as_bytes());
            assert!(
                parsed.report.nodes[0].native_tcp_candidate,
                "{}",
                parsed.report.nodes[0].diagnostic
            );
            assert!(!parsed.report.nodes[0].real_network_verified);
            let outbound = parsed.tcp_candidates[0].as_ref().unwrap();
            let bytes = serde_json::to_vec(outbound).unwrap();
            let restored: Outbound = serde_json::from_slice(&bytes).unwrap();
            let Outbound::Vless {
                reality: Some(reality),
                tls,
                websocket,
                ..
            } = restored
            else {
                panic!("wrong outbound")
            };
            assert!(tls.is_none() && websocket.is_none());
            assert_eq!(reality.server_name, "camouflage.invalid");
            assert_eq!(reality.public_key, key);
            assert_eq!(reality.short_id, "a1B2");
            assert_eq!(reality.fingerprint, "rustls");
            assert_eq!(reality.alpn, ["h2", "http/1.1"]);
        }
        assert_eq!(inspect(uri.as_bytes()).originals[0]["raw-uri"], uri);
    }

    #[test]
    fn unsupported_profiles_conflicts_and_unknown_fields_never_downgrade() {
        let cases = [
            json!({"client-fingerprint":"chrome"}),
            json!({"client-fingerprint":null}),
            json!({"flow":"xtls-rprx-vision"}),
            json!({"flow":false}),
            json!({"network":"ws"}),
            json!({"security":"tls"}),
            json!({"tls":false}),
            json!({"sni":"other.invalid"}),
            json!({"fp":"chrome"}),
            json!({"sid":""}),
            json!({"pbk":URL_SAFE_NO_PAD.encode([8;32])}),
            json!({"udp":true}),
            json!({"reality-opts":{"public-key":URL_SAFE_NO_PAD.encode([9;32]),"short-id":"abc"}}),
            json!({"reality-opts":{"public-key":URL_SAFE_NO_PAD.encode([9;32]),"short-id":"aa","spider-x":"private"}}),
            json!({"spx":"private"}),
            json!({"alpn":["h2","h2"]}),
            json!({"alpn":["a".repeat(255),"b".repeat(255),"c".repeat(255),"d".repeat(255),"e".repeat(5)]}),
            json!({"alpn":["h2",false]}),
            json!({"skip-cert-verify":true}),
        ];
        for change in cases {
            let mut source = node();
            for (key, value) in change.as_object().unwrap() {
                source[key] = value.clone();
            }
            let document = json!({"proxies":[source]}).to_string();
            let parsed = inspect(document.as_bytes());
            assert!(parsed.report.parsed);
            assert!(parsed.tcp_candidates[0].is_none(), "accepted {change}");
            assert_eq!(parsed.original, document.as_bytes());
            assert!(
                !serde_json::to_string(&parsed.report)
                    .unwrap()
                    .contains("private")
            );
        }
    }

    #[test]
    fn missing_required_parameters_are_not_guessed() {
        for key in ["client-fingerprint", "servername", "uuid"] {
            let mut source = node();
            source.as_object_mut().unwrap().remove(key);
            let parsed = inspect(json!({"proxies":[source]}).to_string().as_bytes());
            assert!(parsed.tcp_candidates[0].is_none());
        }
    }
}
