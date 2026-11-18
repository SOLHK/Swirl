use crate::valid_host;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Snell {
    pub host: String,
    pub port: u16,
    pub psk: String,
    pub version: u8,
    #[serde(default)]
    pub udp: bool,
}

impl Snell {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.version != 4 {
            return Err("SnellVersionUnsupported");
        }
        if !valid_host(&self.host) || self.port == 0 || self.psk.is_empty() || self.psk.len() > 1024
        {
            return Err("SnellParameters");
        }
        Ok(())
    }
    pub fn from_raw(raw: &Value) -> Result<Self, &'static str> {
        let object = raw.as_object().ok_or("SnellParameters")?;
        if object.keys().any(|key| {
            !matches!(
                key.as_str(),
                "name"
                    | "tag"
                    | "type"
                    | "server"
                    | "port"
                    | "server_port"
                    | "psk"
                    | "version"
                    | "udp"
                    | "raw-ini"
                    | "raw-uri"
                    | "network"
            )
        }) {
            return Err("SnellOptionsUnsupported");
        }
        if raw
            .get("network")
            .is_some_and(|value| value.as_str() != Some("tcp"))
        {
            return Err("SnellTransportUnsupported");
        }
        let port = raw
            .get("port")
            .or_else(|| raw.get("server_port"))
            .and_then(Value::as_u64)
            .and_then(|port| u16::try_from(port).ok())
            .ok_or("SnellPort")?;
        if raw.get("port").is_some()
            && raw.get("server_port").is_some()
            && raw["port"] != raw["server_port"]
        {
            return Err("SnellPort");
        }
        let version = match raw.get("version") {
            Some(Value::Number(number)) => number.as_u64().and_then(|v| u8::try_from(v).ok()),
            Some(Value::String(text)) if text == "4" => Some(4),
            _ => None,
        }
        .ok_or("SnellVersionRequired")?;
        let udp = match raw.get("udp") {
            None => false,
            Some(Value::Bool(value)) => *value,
            _ => return Err("SnellUdp"),
        };
        let config = Self {
            host: raw
                .get("server")
                .and_then(Value::as_str)
                .ok_or("SnellHost")?
                .to_owned(),
            port,
            psk: raw
                .get("psk")
                .and_then(Value::as_str)
                .ok_or("SnellPsk")?
                .to_owned(),
            version,
            udp,
        };
        config.validate()?;
        Ok(config)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn explicit_v4_import_keeps_native_tcp_and_udp_intent() {
        let raw = json!({"proxies":[{"name":"fixture","type":"snell","server":"fixture.invalid","port":443,"psk":"synthetic","version":4,"udp":true}]});
        let inspection = crate::inspect::inspect(&serde_json::to_vec(&raw).unwrap());
        let node = &inspection.report.nodes[0];
        assert!(node.native_tcp_candidate && node.native_udp_supported);
        assert_eq!(node.version, "4");
        assert!(!node.real_network_verified);
        assert!(matches!(
            inspection.tcp_candidates[0],
            Some(crate::Outbound::Snell(Snell {
                version: 4,
                udp: true,
                ..
            }))
        ));
    }
    #[test]
    fn undeclared_versions_and_obfuscation_are_not_silently_downgraded() {
        let base = json!({"type":"snell","server":"fixture.invalid","port":443,"psk":"synthetic","version":4});
        for version in [Value::Null, json!(1), json!(3), json!(5), json!(6)] {
            let mut raw = base.clone();
            raw["version"] = version;
            assert!(Snell::from_raw(&raw).is_err());
        }
        for key in ["obfs", "obfs-opts", "reuse", "quic"] {
            let mut raw = base.clone();
            raw[key] = json!(true);
            assert!(Snell::from_raw(&raw).is_err());
        }
    }
    #[test]
    fn surge_ini_import_preserves_version_and_udp_relay() {
        let input = b"[Proxy]\nfixture = snell, fixture.invalid, 443, psk=synthetic, version=4, udp-relay=true, tfo=true\n";
        let inspection = crate::inspect::inspect(input);
        assert_eq!(inspection.report.nodes.len(), 1);
        assert!(inspection.report.nodes[0].native_tcp_candidate);
        assert!(inspection.report.nodes[0].native_udp_supported);
        assert!(matches!(
            inspection.tcp_candidates[0],
            Some(crate::Outbound::Snell(Snell {
                version: 4,
                udp: true,
                ..
            }))
        ));
    }
}
