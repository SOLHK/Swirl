//! Explicit DNS-over-TLS endpoints. An IP bootstrap address and authentication
//! name are separate: resolving the DoT endpoint must not leak target queries.
use crate::{Dns, Tls, valid_host};
use serde::{Deserialize, Serialize};
use std::{collections::HashSet, net::SocketAddr};

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DnsTlsServer {
    pub address: SocketAddr,
    pub tls: Tls,
}

impl Dns {
    /// Validate the additive TLS settings independently of the caller. Mixing
    /// cleartext and TLS resolvers would introduce an implicit downgrade path.
    pub fn validate_tls(&self) -> Result<(), &'static str> {
        if self.tls_servers.len() > 4 {
            return Err("DnsTlsServerLimit");
        }
        if !self.tls_servers.is_empty() && !self.servers.is_empty() {
            return Err("DnsTlsMixedResolvers");
        }
        let mut seen = HashSet::new();
        for server in &self.tls_servers {
            let address = server.address;
            if address.port() == 0
                || address.ip().is_unspecified()
                || address.ip().is_multicast()
                || matches!(address, SocketAddr::V6(a) if a.scope_id() != 0)
                || !seen.insert(address)
            {
                return Err("DnsTlsServerAddress");
            }
            let tls = &server.tls;
            if !valid_host(&tls.server_name)
                || tls.ca_der_base64.as_ref().is_some_and(|s| s.len() > 65536)
                || !(tls.alpn.is_empty() || (tls.alpn.len() == 1 && tls.alpn[0] == "dot"))
            {
                return Err("DnsTlsParameters");
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use crate::Config;
    use serde_json::{Value, json};

    fn config(dns: Value) -> Result<Config, &'static str> {
        let input = json!({
            "schema": 1,
            "listen": "127.0.0.1:0",
            "selected": "direct",
            "nodes": [{"id": "direct", "outbound": {"type": "direct"}}],
            "dns": dns
        });
        Config::parse(&serde_json::to_vec(&input).unwrap())
    }

    fn endpoint() -> Value {
        json!({"address": "127.0.0.1:853", "tls": {"server_name": "dns.fixture.invalid", "alpn": ["dot"]}})
    }

    #[test]
    fn legacy_dns_and_explicit_tls_round_trip() {
        assert!(config(json!({})).unwrap().dns.tls_servers.is_empty());
        assert!(config(json!({"servers": ["127.0.0.1:53"]})).is_ok());
        let cfg = config(json!({"tls_servers": [endpoint()], "use_system_hosts": false})).unwrap();
        let encoded = serde_json::to_vec(&cfg).unwrap();
        let decoded = Config::parse(&encoded).unwrap();
        assert_eq!(decoded.dns.tls_servers.len(), 1);
        assert_eq!(
            decoded.dns.tls_servers[0].tls.server_name,
            "dns.fixture.invalid"
        );
        assert!(!decoded.dns.use_system_hosts);
        let mut ipv6 = endpoint();
        ipv6["address"] = json!("[::1]:8853");
        ipv6["tls"]["server_name"] = json!("::1");
        ipv6["tls"]["alpn"] = json!([]);
        assert!(config(json!({"tls_servers": [ipv6]})).is_ok());
    }

    #[test]
    fn tls_cannot_downgrade_or_exceed_endpoint_budget() {
        assert!(config(json!({"tls_servers": [endpoint()], "servers": ["127.0.0.1:53"]})).is_err());
        assert!(config(json!({"tls_servers": [endpoint(), endpoint()]})).is_err());
        let servers: Vec<_> = (853..858)
            .map(|port| {
                let mut server = endpoint();
                server["address"] = json!(format!("127.0.0.1:{port}"));
                server
            })
            .collect();
        assert!(config(json!({"tls_servers": servers})).is_err());
    }

    #[test]
    fn tls_rejects_ambiguous_addresses_names_and_options() {
        for address in [
            "127.0.0.1:0",
            "0.0.0.0:853",
            "[::]:853",
            "224.0.0.1:853",
            "[fe80::1%1]:853",
            "dns.fixture.invalid:853",
        ] {
            let mut server = endpoint();
            server["address"] = json!(address);
            assert!(
                config(json!({"tls_servers": [server]})).is_err(),
                "accepted {address}"
            );
        }
        for name in ["", "bad host", "x\r\nInjected: 1", "*.example.org"] {
            let mut server = endpoint();
            server["tls"]["server_name"] = json!(name);
            assert!(config(json!({"tls_servers": [server]})).is_err());
        }
        for alpn in [json!(["h2"]), json!(["dot", "dot"]), json!("dot")] {
            let mut server = endpoint();
            server["tls"]["alpn"] = alpn;
            assert!(config(json!({"tls_servers": [server]})).is_err());
        }
        let mut server = endpoint();
        server["tls"]["skip_cert_verify"] = json!(true);
        assert!(config(json!({"tls_servers": [server]})).is_err());
    }
}
