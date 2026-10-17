//! Explicit encrypted DNS endpoints. An IP bootstrap address and authentication
//! name are separate: resolving an endpoint must not leak target queries.
use crate::{Dns, Tls, valid_host};
use serde::{Deserialize, Serialize};
use std::{collections::HashSet, net::SocketAddr};

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DnsTlsServer {
    pub address: SocketAddr,
    pub tls: Tls,
    /// Absent: DNS-over-TLS framing. Present: RFC 8484 HTTP/1.1 POST at this
    /// explicit path. Kept in tls_servers for backwards-compatible IR v1.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub https_path: Option<String>,
}

fn valid_https_path(path: &str) -> bool {
    if !path.starts_with('/')
        || path.starts_with("//")
        || path.len() > 1024
        || !path
            .bytes()
            .all(|b| (33..=126).contains(&b) && !b"?#\\".contains(&b))
    {
        return false;
    }
    let bytes = path.as_bytes();
    let mut at = 0;
    while at < bytes.len() {
        if bytes[at] == b'%' {
            if bytes.get(at + 1).is_none_or(|b| !b.is_ascii_hexdigit())
                || bytes.get(at + 2).is_none_or(|b| !b.is_ascii_hexdigit())
            {
                return false;
            }
            at += 3;
        } else {
            at += 1;
        }
    }
    true
}
impl Dns {
    /// Cleartext and encrypted resolvers cannot be mixed into a downgrade chain.
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
            let protocol = if let Some(path) = &server.https_path {
                if !valid_https_path(path) {
                    return Err("DnsHttpsPath");
                }
                "http/1.1"
            } else {
                "dot"
            };
            if !valid_host(&tls.server_name)
                || tls.ca_der_base64.as_ref().is_some_and(|s| s.len() > 65536)
                || !(tls.alpn.is_empty() || (tls.alpn.len() == 1 && tls.alpn[0] == protocol))
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
        assert!(decoded.dns.tls_servers[0].https_path.is_none());
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

    #[test]
    fn https_is_explicit_and_cannot_use_dot_or_h2_framing() {
        let mut server = endpoint();
        server["https_path"] = json!("/dns-query");
        assert!(config(json!({"tls_servers": [server.clone()]})).is_err());
        server["tls"]["alpn"] = json!(["http/1.1"]);
        let cfg = config(json!({"tls_servers": [server.clone()]})).unwrap();
        assert_eq!(
            cfg.dns.tls_servers[0].https_path.as_deref(),
            Some("/dns-query")
        );
        for path in [
            "",
            "dns-query",
            "//other.invalid",
            "/bad path",
            "/dns?dns=x",
            "/dns#fragment",
            "/bad\\path",
            "/bad%",
            "/x\r\nInjected: 1",
        ] {
            server["https_path"] = json!(path);
            assert!(
                config(json!({"tls_servers": [server.clone()]})).is_err(),
                "accepted {path:?}"
            );
        }
        server["https_path"] = json!("/dns-query");
        server["tls"]["alpn"] = json!(["h2"]);
        assert!(config(json!({"tls_servers": [server]})).is_err());
    }
}
