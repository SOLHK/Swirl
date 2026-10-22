//! Strict Xray JSON adaptation, independently implemented from the locked
//! upstream field definitions. This is node mapping, not Xray global-policy
//! execution. Unknown source fields are rejected before any normalization.
//!
//! https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/infra/conf/vless.go
//! https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/infra/conf/transport_security.go
//! https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/transport/internet/reality/reality.go
use super::{aliases, object_keys, string};
use serde_json::{Value, json};

pub(super) const FIELDS: &[&str] = &["protocol", "tag", "settings", "streamSettings", "mux"];

fn only<'a>(value: Option<&'a Value>, error: &'static str) -> Result<&'a Value, &'static str> {
    let values = value.and_then(Value::as_array).ok_or(error)?;
    if values.len() != 1 {
        return Err(error);
    }
    Ok(&values[0])
}

pub(super) fn normalized(raw: &Value) -> Result<Value, &'static str> {
    object_keys(raw, FIELDS)?;
    if raw.get("protocol").and_then(Value::as_str) != Some("vless")
        || raw.get("tag").is_some_and(|value| !value.is_string())
    {
        return Err("VlessParameters");
    }
    if let Some(mux) = raw.get("mux") {
        object_keys(mux, &["enabled"])?;
        if mux.get("enabled").and_then(Value::as_bool) != Some(false) {
            return Err("VlessMultiplexUnsupported");
        }
    }
    let settings = raw.get("settings").ok_or("VlessParameters")?;
    let (endpoint, user) = if settings.get("vnext").is_some() {
        // No flattening of multiple endpoints/users and no precedence between
        // legacy vnext and the newer simplified outbound syntax.
        object_keys(settings, &["vnext"])?;
        let endpoint = only(settings.get("vnext"), "VlessEndpointCount")?;
        object_keys(endpoint, &["address", "port", "users"])?;
        let user = only(endpoint.get("users"), "VlessUserCount")?;
        object_keys(user, &["id", "encryption", "flow"])?;
        (endpoint, user)
    } else {
        object_keys(settings, &["address", "port", "id", "encryption", "flow"])?;
        (settings, settings)
    };
    if user.get("encryption").and_then(Value::as_str) != Some("none") {
        return Err("VlessEncryptionUnsupported");
    }
    let port = endpoint
        .get("port")
        .and_then(Value::as_u64)
        .and_then(|value| u16::try_from(value).ok())
        .filter(|value| *value != 0)
        .ok_or("VlessParameters")?;
    let stream = raw.get("streamSettings").ok_or("RealitySecurityRequired")?;
    object_keys(
        stream,
        &[
            "network",
            "security",
            "realitySettings",
            "tcpSettings",
            "rawSettings",
        ],
    )?;
    if !matches!(
        stream.get("network").and_then(Value::as_str),
        Some("tcp" | "raw")
    ) {
        return Err("RealityTransportUnsupported");
    }
    if stream.get("security").and_then(Value::as_str) != Some("reality") {
        return Err("RealitySecurityConflict");
    }
    if let Some(tcp) = aliases(
        &[stream.get("tcpSettings"), stream.get("rawSettings")],
        "RealityConflictingTransport",
    )? {
        object_keys(tcp, &["header"])?;
        if let Some(header) = tcp.get("header") {
            object_keys(header, &["type"])?;
            if header.get("type").and_then(Value::as_str) != Some("none") {
                return Err("RealityTransportUnsupported");
            }
        }
    }
    let reality = stream
        .get("realitySettings")
        .ok_or("RealitySecurityRequired")?;
    object_keys(
        reality,
        &[
            "serverName",
            "fingerprint",
            "publicKey",
            "password",
            "shortId",
            "spiderX",
            "show",
        ],
    )?;
    if reality.get("spiderX").is_some() {
        // Upstream uses this path for camouflage HTTP crawling after REALITY
        // authentication failed. Swirl fails closed and does not implement the
        // requested crawler, including an explicitly declared empty/default path.
        return Err("RealitySpiderUnsupported");
    }
    if reality
        .get("show")
        .is_some_and(|value| value.as_bool() != Some(false))
    {
        return Err("RealityDiagnosticUnsupported");
    }
    let key = aliases(
        &[reality.get("publicKey"), reality.get("password")],
        "RealityConflictingPublicKey",
    )?;
    let mut mapped = json!({
        "type":"vless",
        "server":string(endpoint.get("address"), "VlessParameters")?,
        "port":port,
        "uuid":string(user.get("id"), "VlessParameters")?,
        "encryption":"none",
        "security":"reality",
        "network":"tcp",
        "sni":string(reality.get("serverName"), "RealityServerName")?,
        "fp":string(reality.get("fingerprint"), "RealityFingerprintRequired")?,
        "pbk":string(key, "RealityPublicKey")?,
        "sid":string(reality.get("shortId"), "RealityShortId")?,
    });
    if let Some(flow) = user.get("flow") {
        mapped["flow"] = flow.clone();
    }
    // ALPN is not a realitySettings field in the locked Xray version; a source
    // that supplies it is rejected above, never silently discarded or invented.
    Ok(mapped)
}

#[cfg(test)]
mod tests {
    use crate::inspect::{Inspection, inspect};
    use base64::{
        Engine,
        engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD},
    };
    use serde_json::{Value, json};

    fn source() -> Value {
        // "rustls" is an explicit Swirl native profile used to exercise this
        // mapper, not a claim that upstream Xray implements that fingerprint.
        json!({
            "protocol":"vless", "tag":"fixture",
            "settings":{"vnext":[{"address":"proxy.invalid","port":443,
                "users":[{"id":"00112233-4455-6677-8899-aabbccddeeff",
                    "encryption":"none","flow":"xtls-rprx-vision"}]}]},
            "streamSettings":{"network":"raw","security":"reality",
                "realitySettings":{"serverName":"camouflage.invalid",
                    "fingerprint":"rustls","publicKey":URL_SAFE_NO_PAD.encode([9;32]),
                    "shortId":"a1B2"}}
        })
    }

    fn document(node: &Value) -> String {
        json!({"outbounds":[node]}).to_string()
    }

    fn candidate(input: &str) -> Value {
        let parsed = inspect(input.as_bytes());
        assert!(parsed.report.parsed);
        assert_eq!(parsed.original, input.as_bytes());
        assert_eq!(parsed.report.nodes.len(), 1);
        assert!(!parsed.report.nodes[0].real_network_verified);
        assert!(!parsed.report.nodes[0].native_udp_supported);
        assert_eq!(parsed.report.nodes[0].transport, "tcp");
        serde_json::to_value(
            parsed.tcp_candidates[0]
                .as_ref()
                .unwrap_or_else(|| panic!("{}", parsed.report.nodes[0].diagnostic)),
        )
        .unwrap()
    }

    fn rejected(node: &Value) -> Inspection {
        let input = document(node);
        let parsed = inspect(input.as_bytes());
        assert!(parsed.report.parsed);
        assert_eq!(parsed.original, input.as_bytes());
        assert_eq!(parsed.originals[0], *node);
        assert!(parsed.tcp_candidates[0].is_none());
        assert!(!parsed.report.nodes[0].native_tcp_candidate);
        assert!(!parsed.report.nodes[0].real_network_verified);
        let report = serde_json::to_string(&parsed.report).unwrap();
        for private in [
            "proxy.invalid",
            "camouflage.invalid",
            "fixture-private-extension",
            "00112233-4455-6677-8899-aabbccddeeff",
        ] {
            assert!(!report.contains(private));
        }
        assert!(!report.contains(&URL_SAFE_NO_PAD.encode([9; 32])));
        parsed
    }

    #[test]
    fn explicit_native_profile_xray_uri_yaml_and_wrapped_json_preserve_same_parameters() {
        let legacy = source();
        let expected = candidate(&document(&legacy));
        let key = URL_SAFE_NO_PAD.encode([9; 32]);
        let uri = format!(
            "vless://00112233-4455-6677-8899-aabbccddeeff@proxy.invalid:443?security=reality&sni=camouflage.invalid&fp=rustls&pbk={key}&sid=a1B2&type=tcp&encryption=none&flow=xtls-rprx-vision"
        );
        let yaml = format!(
            "proxies:\n  - type: vless\n    server: proxy.invalid\n    port: 443\n    uuid: 00112233-4455-6677-8899-aabbccddeeff\n    tls: true\n    servername: camouflage.invalid\n    client-fingerprint: rustls\n    reality-opts: {{public-key: {key}, short-id: a1B2}}\n    flow: xtls-rprx-vision\n"
        );
        let mut tcp = legacy.clone();
        tcp["streamSettings"]["network"] = json!("tcp");
        tcp["streamSettings"]["tcpSettings"] = json!({"header":{"type":"none"}});
        tcp["streamSettings"]["rawSettings"] = tcp["streamSettings"]["tcpSettings"].clone();
        tcp["mux"] = json!({"enabled":false});
        let mut simplified = legacy.clone();
        simplified["settings"] = json!({"address":"proxy.invalid","port":443,
            "id":"00112233-4455-6677-8899-aabbccddeeff","encryption":"none","flow":"xtls-rprx-vision"});
        let mut renamed_key = simplified.clone();
        let options = renamed_key["streamSettings"]["realitySettings"]
            .as_object_mut()
            .unwrap();
        let key = options.remove("publicKey").unwrap();
        options.insert("password".into(), key);
        let mut equal_aliases = renamed_key.clone();
        equal_aliases["streamSettings"]["realitySettings"]["publicKey"] =
            equal_aliases["streamSettings"]["realitySettings"]["password"].clone();
        equal_aliases["streamSettings"]["realitySettings"]["show"] = json!(false);
        for input in [
            uri.clone(),
            STANDARD.encode(uri),
            yaml,
            document(&tcp),
            document(&simplified),
            document(&renamed_key),
            document(&equal_aliases),
            STANDARD.encode(document(&legacy)),
        ] {
            assert_eq!(candidate(&input), expected);
        }
        let parsed = inspect(document(&legacy).as_bytes());
        assert_eq!(parsed.originals[0], legacy);
        assert_eq!(expected["reality"]["fingerprint"], "rustls");
        assert_eq!(expected["reality"]["short_id"], "a1B2");
        assert_eq!(expected["flow"], "xtls-rprx-vision");
        assert!(expected["tls"].is_null() && expected["websocket"].is_null());
    }

    #[test]
    fn mapping_one_xray_node_does_not_claim_full_document_execution() {
        let node = source();
        let input = json!({"outbounds":[node.clone()],
            "dns":{"servers":["fixture-private-extension"]},
            "routing":{"domainStrategy":"IPIfNonMatch","rules":[]}})
        .to_string();
        let parsed = inspect(input.as_bytes());
        assert_eq!(parsed.original, input.as_bytes());
        assert_eq!(parsed.originals[0], node);
        assert_eq!(
            parsed.document["dns"]["servers"][0],
            "fixture-private-extension"
        );
        assert!(parsed.tcp_candidates[0].is_some());
        assert_eq!(parsed.report.full_configuration_sections_preserved, 2);
        assert_eq!(parsed.report.configuration_sections_unvalidated, 2);
        assert!(!parsed.report.complete_configuration_execution_supported);
        assert!(!parsed.report.nodes[0].real_network_verified);
    }

    #[test]
    fn xray_non_vision_and_explicit_empty_short_id_are_preserved() {
        let mut node = source();
        node["settings"]["vnext"][0]["users"][0]
            .as_object_mut()
            .unwrap()
            .remove("flow");
        node["streamSettings"]["realitySettings"]["shortId"] = json!("");
        let mapped = candidate(&document(&node));
        assert!(mapped.get("flow").is_none());
        assert_eq!(mapped["reality"]["short_id"], "");
        node["settings"]["vnext"][0]["users"][0]["flow"] = json!("");
        assert_eq!(candidate(&document(&node))["flow"], "");
    }

    #[test]
    fn unknown_fields_at_every_xray_boundary_are_rejected_before_normalization() {
        for path in [
            "",
            "/settings",
            "/settings/vnext/0",
            "/settings/vnext/0/users/0",
            "/streamSettings",
            "/streamSettings/realitySettings",
        ] {
            let mut node = source();
            node.pointer_mut(path)
                .unwrap()
                .as_object_mut()
                .unwrap()
                .insert(
                    "fixture-private-extension".into(),
                    json!("fixture-private-extension"),
                );
            let parsed = rejected(&node);
            assert_eq!(parsed.report.nodes[0].diagnostic, "RealityUnmappedFields");
        }
        for options in [
            json!({"header":{"type":"none","request":{}}}),
            json!({"acceptProxyProtocol":true}),
            json!({"header":null}),
        ] {
            let mut node = source();
            node["streamSettings"]["rawSettings"] = options;
            rejected(&node);
        }
        for (path, key, value) in [
            ("", "sendThrough", json!("192.0.2.10")),
            ("", "proxySettings", json!({"tag":"private"})),
            (
                "/streamSettings",
                "sockopt",
                json!({"dialerProxy":"private"}),
            ),
            (
                "/streamSettings",
                "tlsSettings",
                json!({"allowInsecure":false}),
            ),
            ("/settings/vnext/0/users/0", "packetEncoding", json!("xudp")),
            ("/settings/vnext/0/users/0", "level", json!(1)),
            (
                "/streamSettings/realitySettings",
                "mldsa65Verify",
                json!("fixture-private-extension"),
            ),
            ("/streamSettings/realitySettings", "alpn", json!(["h2"])),
        ] {
            let mut node = source();
            node.pointer_mut(path)
                .unwrap()
                .as_object_mut()
                .unwrap()
                .insert(key.into(), value);
            rejected(&node);
        }
    }

    #[test]
    fn missing_and_mistyped_xray_security_parameters_never_become_candidates() {
        let paths = [
            "/settings/vnext/0/address",
            "/settings/vnext/0/port",
            "/settings/vnext/0/users/0/id",
            "/settings/vnext/0/users/0/encryption",
            "/streamSettings/network",
            "/streamSettings/security",
            "/streamSettings/realitySettings/serverName",
            "/streamSettings/realitySettings/fingerprint",
            "/streamSettings/realitySettings/publicKey",
            "/streamSettings/realitySettings/shortId",
        ];
        for path in paths {
            let mut missing = source();
            let (parent, key) = path.rsplit_once('/').unwrap();
            missing
                .pointer_mut(parent)
                .unwrap()
                .as_object_mut()
                .unwrap()
                .remove(key);
            rejected(&missing);
            for wrong in [Value::Null, json!(false), json!([]), json!({})] {
                let mut node = source();
                *node.pointer_mut(path).unwrap() = wrong;
                rejected(&node);
            }
        }
        for port in [
            json!("443"),
            json!(0),
            json!(65536),
            json!(-1),
            json!(443.5),
        ] {
            let mut node = source();
            node["settings"]["vnext"][0]["port"] = port;
            rejected(&node);
        }
    }

    #[test]
    fn conflicting_or_unimplemented_xray_features_fail_with_original_retained() {
        let mut node = source();
        node["streamSettings"]["realitySettings"]["password"] =
            json!(URL_SAFE_NO_PAD.encode([8; 32]));
        assert_eq!(
            rejected(&node).report.nodes[0].diagnostic,
            "RealityConflictingPublicKey"
        );
        for key in [Value::Null, json!("")] {
            node["streamSettings"]["realitySettings"]["password"] = key;
            assert_eq!(
                rejected(&node).report.nodes[0].diagnostic,
                "RealityConflictingPublicKey"
            );
        }
        for (path, value, reason) in [
            (
                "/streamSettings/network",
                json!("grpc"),
                "RealityTransportUnsupported",
            ),
            (
                "/streamSettings/security",
                json!("tls"),
                "RealitySecurityConflict",
            ),
            (
                "/settings/vnext/0/users/0/encryption",
                json!("auto"),
                "VlessEncryptionUnsupported",
            ),
            (
                "/settings/vnext/0/users/0/flow",
                json!("xtls-rprx-vision-udp443"),
                "VlessFlowUnsupported",
            ),
            (
                "/streamSettings/realitySettings/fingerprint",
                json!("firefox"),
                "RealityFingerprintUnsupported",
            ),
        ] {
            let mut node = source();
            *node.pointer_mut(path).unwrap() = value;
            assert_eq!(rejected(&node).report.nodes[0].diagnostic, reason);
        }
        for spider in [
            json!("/"),
            json!(""),
            json!("/fixture-private-extension"),
            Value::Null,
        ] {
            let mut node = source();
            node["streamSettings"]["realitySettings"]["spiderX"] = spider;
            assert_eq!(
                rejected(&node).report.nodes[0].diagnostic,
                "RealitySpiderUnsupported"
            );
        }
        for enabled in [json!(true), json!("false"), Value::Null] {
            let mut node = source();
            node["mux"] = json!({"enabled":enabled});
            assert_eq!(
                rejected(&node).report.nodes[0].diagnostic,
                "VlessMultiplexUnsupported"
            );
        }
        let mut node = source();
        node["streamSettings"]["tcpSettings"] = json!({"header":{"type":"none"}});
        node["streamSettings"]["rawSettings"] = json!({"header":{"type":"http"}});
        assert_eq!(
            rejected(&node).report.nodes[0].diagnostic,
            "RealityConflictingTransport"
        );
        node = source();
        node["settings"]["address"] = json!("different.invalid");
        assert_eq!(
            rejected(&node).report.nodes[0].diagnostic,
            "RealityUnmappedFields"
        );
        for (path, expected) in [
            ("/settings/vnext", "VlessEndpointCount"),
            ("/settings/vnext/0/users", "VlessUserCount"),
        ] {
            for count in [0, 2] {
                let mut node = source();
                let values = node.pointer_mut(path).unwrap().as_array_mut().unwrap();
                if count == 0 {
                    values.clear();
                } else {
                    values.push(values[0].clone());
                }
                assert_eq!(rejected(&node).report.nodes[0].diagnostic, expected);
            }
        }
    }
}
