use crate::{Tls, valid_host};
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WebSocket {
    pub host: String,
    pub path: String,
}
impl WebSocket {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.host.is_empty() || self.host.len() > 270
            || !self.host.bytes().all(|b| b.is_ascii_alphanumeric() || b".-:[]".contains(&b))
            || !self.path.starts_with('/') || self.path.starts_with("//") || self.path.len() > 2048
            || !self.path.bytes().all(|b| (33..=126).contains(&b) && !b"#\\".contains(&b)) {
            return Err("WebSocketParameters");
        }
        let url = url::Url::parse(&format!("http://{}/", self.host)).map_err(|_| "WebSocketHost")?;
        let host = url.host_str().ok_or("WebSocketHost")?;
        let host = host.strip_prefix('[').and_then(|s| s.strip_suffix(']')).unwrap_or(host);
        if !valid_host(host) || url.port() == Some(0) { return Err("WebSocketHost"); }
        let bytes = self.path.as_bytes();
        let mut at = 0;
        while at < bytes.len() {
            if bytes[at] == b'%' {
                if bytes.get(at + 1).is_none_or(|b| !b.is_ascii_hexdigit())
                    || bytes.get(at + 2).is_none_or(|b| !b.is_ascii_hexdigit()) {
                    return Err("WebSocketPath");
                }
                at += 3;
            } else { at += 1; }
        }
        Ok(())
    }
    pub fn validate_tls(&self, tls: Option<&Tls>) -> Result<(), &'static str> {
        self.validate()?;
        if tls.is_some_and(|t| !(t.alpn.is_empty() || t.alpn == ["http/1.1"])) {
            return Err("WebSocketAlpnUnsupported");
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn websocket_rejects_header_injection_ambiguous_hosts_and_bad_escapes() {
        for host in ["", "user@host", "host/path", "x\r\nInjected: 1", "host:0", "host:65536", "bad..host"] {
            assert!(WebSocket {host: host.into(), path: "/ws".into()}.validate().is_err());
        }
        for path in ["", "ws", "//host/ws", "/bad path", "/a#fragment", "/a\\b", "/bad%", "/bad%xx"] {
            assert!(WebSocket {host: "ws.example".into(), path: path.into()}.validate().is_err());
        }
        for host in ["ws.example", "127.0.0.1:8080", "[::1]:443"] {
            assert!(WebSocket {host: host.into(), path: "/ws%20path?client=fixture".into()}.validate().is_ok());
        }
    }
}
