//! JSON-specific visitor: no YAML coercion, duplicate-key last-wins behavior,
//! input excerpts, unbounded recursion, or attacker-controlled diagnostic keys.
use super::{Diagnostic, MAX_JSON_DEPTH, MAX_JSON_INPUT, MAX_JSON_VALUES, diagnostic};
use serde::de::{self, DeserializeSeed, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Number, Value};
use std::fmt;

pub(super) fn key_path(parent: &str, key: &str) -> String {
    // A JSON object may use a password/token/UUID as its *key*. Only these
    // schema names may be reflected. Headers and future extensions use a mask.
    const NAMES: &[&str] = &[
        "outbounds",
        "inbounds",
        "outbound",
        "inbound",
        "outboundDetour",
        "inboundDetour",
        "log",
        "dns",
        "hosts",
        "clientIp",
        "queryStrategy",
        "skipFallback",
        "domains",
        "routing",
        "rules",
        "balancers",
        "policy",
        "levels",
        "system",
        "handshake",
        "connIdle",
        "uplinkOnly",
        "downlinkOnly",
        "bufferSize",
        "statsUserUplink",
        "statsUserDownlink",
        "statsInboundUplink",
        "statsInboundDownlink",
        "statsOutboundUplink",
        "statsOutboundDownlink",
        "access",
        "error",
        "loglevel",
        "dnsLog",
        "transport",
        "stats",
        "api",
        "reverse",
        "fakedns",
        "metrics",
        "observatory",
        "burstObservatory",
        "router",
        "services",
        "extension",
        "protocol",
        "tag",
        "settings",
        "streamSettings",
        "mux",
        "sendThrough",
        "proxySettings",
        "transportLayer",
        "domainStrategy",
        "targetStrategy",
        "vnext",
        "servers",
        "users",
        "address",
        "server",
        "port",
        "id",
        "encryption",
        "flow",
        "alterId",
        "security",
        "method",
        "password",
        "user",
        "pass",
        "username",
        "level",
        "email",
        "network",
        "tcpSettings",
        "rawSettings",
        "wsSettings",
        "grpcSettings",
        "gunSettings",
        "httpSettings",
        "httpupgradeSettings",
        "xhttpSettings",
        "splithttpSettings",
        "kcpSettings",
        "quicSettings",
        "dsSettings",
        "sockopt",
        "tlsSettings",
        "realitySettings",
        "transportSettings",
        "securitySettings",
        "socketSettings",
        "serverName",
        "fingerprint",
        "publicKey",
        "shortId",
        "spiderX",
        "alpn",
        "allowInsecure",
        "certificates",
        "certificate",
        "key",
        "certificateFile",
        "keyFile",
        "usage",
        "disableSystemRoot",
        "minVersion",
        "maxVersion",
        "cipherSuites",
        "pinnedPeerCertificateChainSha256",
        "verifyPeerCertInNames",
        "rejectUnknownSni",
        "enableSessionResumption",
        "echConfigList",
        "echServerKeys",
        "echForceQuery",
        "show",
        "mldsa65Verify",
        "privateKey",
        "serverNames",
        "shortIds",
        "dest",
        "target",
        "xver",
        "maxTimeDiff",
        "path",
        "host",
        "headers",
        "Host",
        "serviceName",
        "authority",
        "multiMode",
        "idle_timeout",
        "health_check_timeout",
        "permit_without_stream",
        "initial_windows_size",
        "parseXForwardedFor",
        "user_agent",
        "maxEarlyData",
        "earlyDataHeaderName",
        "acceptProxyProtocol",
        "heartbeatPeriod",
        "mode",
        "extra",
        "downloadSettings",
        "header",
        "type",
        "request",
        "response",
        "enabled",
        "concurrency",
        "xudpConcurrency",
        "xudpProxyUDP443",
        "plugin",
        "plugin_opts",
        "pluginOptions",
        "plugin-opts",
        "uot",
        "udpOverTcp",
        "packetEncoding",
        "version",
        "listen",
        "clients",
        "accounts",
        "sniffing",
        "metadataOnly",
        "routeOnly",
        "destOverride",
        "domainsExcluded",
        "ipsExcluded",
        "allocate",
        "strategy",
        "refresh",
        "schema",
        "outbound",
        "global_transport",
        "server_index",
        "user_index",
        "source",
        "network_verified",
    ];
    let key = if NAMES.contains(&key) {
        key
    } else {
        "[unknown]"
    };
    if parent.is_empty() {
        key.into()
    } else {
        format!("{parent}.{key}")
    }
}

#[derive(Default)]
struct Budget {
    values: usize,
    error: Option<Diagnostic>,
    path: String,
}
impl Budget {
    fn fail<E: de::Error>(&mut self, code: &str, path: &str) -> E {
        self.error = Some(diagnostic(code, path, "error"));
        E::custom("Invalid JSON document")
    }
}
struct Seed<'a> {
    budget: &'a mut Budget,
    depth: usize,
    path: String,
}
impl<'de> DeserializeSeed<'de> for Seed<'_> {
    type Value = Value;
    fn deserialize<D: de::Deserializer<'de>>(self, deserializer: D) -> Result<Value, D::Error> {
        self.budget.values += 1;
        self.budget.path.clone_from(&self.path);
        if self.budget.values > MAX_JSON_VALUES {
            return Err(self.budget.fail("JsonValueLimit", &self.path));
        }
        if self.depth > MAX_JSON_DEPTH {
            return Err(self.budget.fail("JsonDepthLimit", &self.path));
        }
        deserializer.deserialize_any(self)
    }
}
impl<'de> Visitor<'de> for Seed<'_> {
    type Value = Value;
    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("a bounded JSON value")
    }
    fn visit_bool<E: de::Error>(self, value: bool) -> Result<Value, E> {
        Ok(Value::Bool(value))
    }
    fn visit_i64<E: de::Error>(self, value: i64) -> Result<Value, E> {
        Ok(Value::Number(value.into()))
    }
    fn visit_u64<E: de::Error>(self, value: u64) -> Result<Value, E> {
        Ok(Value::Number(value.into()))
    }
    fn visit_f64<E: de::Error>(self, value: f64) -> Result<Value, E> {
        Number::from_f64(value)
            .map(Value::Number)
            .ok_or_else(|| self.budget.fail("JsonNumber", &self.path))
    }
    fn visit_str<E: de::Error>(self, value: &str) -> Result<Value, E> {
        Ok(Value::String(value.into()))
    }
    fn visit_string<E: de::Error>(self, value: String) -> Result<Value, E> {
        Ok(Value::String(value))
    }
    fn visit_unit<E: de::Error>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }
    fn visit_none<E: de::Error>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Value, A::Error> {
        let mut values = Vec::new();
        while let Some(value) = seq.next_element_seed(Seed {
            budget: self.budget,
            depth: self.depth + 1,
            path: format!("{}[{}]", self.path, values.len()),
        })? {
            values.push(value);
        }
        Ok(Value::Array(values))
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Value, A::Error> {
        let mut values = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            let path = key_path(&self.path, &key);
            // Decoded keys are compared, so `id` and `\u0069d` conflict too.
            if values.contains_key(&key) {
                return Err(self.budget.fail("DuplicateJsonKey", &path));
            }
            let value = map.next_value_seed(Seed {
                budget: self.budget,
                depth: self.depth + 1,
                path,
            })?;
            values.insert(key, value);
        }
        Ok(Value::Object(values))
    }
}

pub(super) fn parse(bytes: &[u8]) -> Result<Value, Diagnostic> {
    if bytes.len() > MAX_JSON_INPUT {
        return Err(diagnostic("JsonInputSize", "", "error"));
    }
    // UTF-8 BOM is an explicit file-import accommodation; no other encoding or
    // YAML syntax is accepted. The public API retains the original bytes.
    let bytes = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(bytes);
    let text = std::str::from_utf8(bytes).map_err(|_| diagnostic("InvalidUtf8", "", "error"))?;
    if text
        .bytes()
        .all(|byte| matches!(byte, b' ' | b'\r' | b'\n' | b'\t'))
    {
        return Err(diagnostic("EmptyJsonInput", "", "error"));
    }
    let mut budget = Budget::default();
    let mut deserializer = serde_json::Deserializer::from_str(text);
    let result = Seed {
        budget: &mut budget,
        depth: 0,
        path: String::new(),
    }
    .deserialize(&mut deserializer)
    .and_then(|value| {
        deserializer.end()?;
        Ok(value)
    });
    result.map_err(|error| {
        let mut diagnostic = budget
            .error
            .unwrap_or_else(|| diagnostic("JsonSyntax", &budget.path, "error"));
        // The parser's Display message can include untrusted excerpts/keys.
        // Copy numeric location only, including for duplicate/depth failures.
        diagnostic.line = Some(error.line());
        diagnostic.column = Some(error.column());
        diagnostic
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn json_preserves_missing_null_false_empty_and_numbers() {
        let value = parse(br#"{"a":null,"b":false,"c":"","d":18446744073709551615}"#).unwrap();
        assert!(value.get("absent").is_none());
        assert_eq!(value["a"], Value::Null);
        assert_eq!(value["b"], false);
        assert_eq!(value["c"], "");
        assert_eq!(value["d"].as_u64(), Some(u64::MAX));
    }
    #[test]
    fn duplicate_keys_are_checked_before_normalization_at_every_depth() {
        for bytes in [
            br#"{"outbounds":[{"settings":{"password":"SECRET","password":"second"}}]}"#.as_slice(),
            br#"{"outbounds":[{"settings":{"id":"SECRET","\u0069d":"second"}}]}"#.as_slice(),
        ] {
            let e = parse(bytes).unwrap_err();
            assert_eq!(e.code, "DuplicateJsonKey");
            assert!(e.path.starts_with("outbounds[0].settings."));
            assert!(!serde_json::to_string(&e).unwrap().contains("SECRET"));
        }
        let e = parse(br#"{"SECRET_TOKEN":0,"SECRET_TOKEN":1}"#).unwrap_err();
        assert_eq!(e.path, "[unknown]");
    }
    #[test]
    fn rejects_yaml_comments_trailing_content_bad_unicode_and_numbers() {
        for bytes in [
            "{outbounds: []}",
            "{'outbounds':[]}",
            "{\"a\":1,}",
            "[1] [2]",
            "// comment\n{}",
            "{\"a\":NaN}",
            "{\"a\":Infinity}",
            "{\"a\":01}",
            "{\"a\":1e999}",
            "\"\\ud800\"",
        ] {
            assert!(
                parse(bytes.as_bytes()).is_err(),
                "accepted invalid JSON grammar"
            );
        }
        assert!(parse(&[b'"', 0xff, b'"']).is_err());
        assert_eq!(parse(b"\xef\xbb\xbf{\"a\":1}\r\n").unwrap(), json!({"a":1}));
    }
    #[test]
    fn bounds_input_depth_and_total_values_before_expansion() {
        let too_big = vec![b' '; MAX_JSON_INPUT + 1];
        assert_eq!(parse(&too_big).unwrap_err().code, "JsonInputSize");
        let nested = format!(
            "{}0{}",
            "[".repeat(MAX_JSON_DEPTH + 1),
            "]".repeat(MAX_JSON_DEPTH + 1)
        );
        assert_eq!(parse(nested.as_bytes()).unwrap_err().code, "JsonDepthLimit");
        let flat = format!("[{}0]", "0,".repeat(MAX_JSON_VALUES));
        assert_eq!(parse(flat.as_bytes()).unwrap_err().code, "JsonValueLimit");
    }
}
