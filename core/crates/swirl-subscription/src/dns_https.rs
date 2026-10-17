//! Explicit IP bootstrap with a separately verified HTTPS identity.
use crate::{Dns, Tls, valid_host};
use serde::{Deserialize, Serialize};
use std::{collections::HashSet, net::SocketAddr};
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DnsHttpsServer {
    pub address: SocketAddr,
    pub path: String,
    pub tls: Tls,
}
impl Dns {
    pub fn validate_https(&self) -> Result<(), &'static str> {
        if self.https_servers.len() > 4 {
            return Err("DnsHttpsLimit");
        }
        if !self.https_servers.is_empty()
            && (!self.servers.is_empty() || !self.tls_servers.is_empty())
        {
            return Err("DnsHttpsMixedResolvers");
        }
        let mut seen = HashSet::new();
        for server in &self.https_servers {
            let address = server.address;
            let tls = &server.tls;
            if address.port() == 0
                || address.ip().is_unspecified()
                || address.ip().is_multicast()
                || matches!(address,SocketAddr::V6(a) if a.scope_id()!=0)
                || !seen.insert((address, &server.path, &tls.server_name))
            {
                return Err("DnsHttpsAddress");
            }
            if !valid_host(&tls.server_name)
                || tls.ca_der_base64.as_ref().is_some_and(|s| s.len() > 65536)
                || !(tls.alpn.is_empty() || (tls.alpn.len() == 1 && tls.alpn[0] == "http/1.1"))
            {
                return Err("DnsHttpsTls");
            }
            let path = &server.path;
            if !path.starts_with('/')
                || path.starts_with("//")
                || path.len() > 2048
                || !path
                    .bytes()
                    .all(|b| b.is_ascii_graphic() && !b"#\\{}".contains(&b))
            {
                return Err("DnsHttpsPath");
            }
            let bytes = path.as_bytes();
            for (i, b) in bytes.iter().enumerate() {
                if *b == b'%'
                    && (i + 2 >= bytes.len()
                        || !bytes[i + 1].is_ascii_hexdigit()
                        || !bytes[i + 2].is_ascii_hexdigit())
                {
                    return Err("DnsHttpsPath");
                }
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
        Config::parse(&serde_json::to_vec(&json!({"schema":1,"listen":"127.0.0.1:0","selected":"d","nodes":[{"id":"d","outbound":{"type":"direct"}}],"dns":dns})).unwrap())
    }
    fn endpoint() -> Value {
        json!({"address":"127.0.0.1:443","path":"/dns-query","tls":{"server_name":"dns.test","alpn":["http/1.1"]}})
    }
    #[test]
    fn https_roundtrip_and_no_downgrade() {
        let c = config(json!({"https_servers":[endpoint()],"use_system_hosts":false})).unwrap();
        assert_eq!(
            Config::parse(&serde_json::to_vec(&c).unwrap())
                .unwrap()
                .dns
                .https_servers
                .len(),
            1
        );
        assert!(config(json!({"https_servers":[endpoint()],"servers":["127.0.0.1:53"]})).is_err());
        assert!(config(json!({"https_servers":[endpoint()],"tls_servers":[{"address":"127.0.0.1:853","tls":{"server_name":"dns.test"}}]})).is_err());
        assert!(config(json!({"https_servers":[endpoint(),endpoint()]})).is_err());
    }
    #[test]
    fn rejects_unsafe_path_identity_and_options() {
        for path in [
            "",
            "//other.test/x",
            "/bad\r\nHeader: x",
            "/fragment#x",
            "/x%",
            "/x%xx",
            "/{?dns}",
            "/a\\b",
        ] {
            let mut e = endpoint();
            e["path"] = json!(path);
            assert!(config(json!({"https_servers":[e]})).is_err(), "{path}");
        }
        for address in ["dns.test:443", "0.0.0.0:443", "[::]:443", "127.0.0.1:0"] {
            let mut e = endpoint();
            e["address"] = json!(address);
            assert!(config(json!({"https_servers":[e]})).is_err());
        }
        let mut e = endpoint();
        e["tls"]["alpn"] = json!(["h2"]);
        assert!(config(json!({"https_servers":[e]})).is_err());
        let mut e = endpoint();
        e["tls"]["skip_cert_verify"] = json!(true);
        assert!(config(json!({"https_servers":[e]})).is_err());
    }
}
