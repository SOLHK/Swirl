//! Xray HTTPUpgrade: an HTTP/1.1 upgrade followed by an unframed byte stream.
//!
//! Wire behavior was checked against Xray-core v26.10.21, commit
//! `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`, `transport/internet/httpupgrade`.
//! No WebSocket frame encoder, masking, or message boundaries are used here.
//! TLS (with HTTP/1.1 ALPN) is established by the caller before this handshake.

use crate::BoxStream;
use http::{HeaderName, HeaderValue};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt, BufReader};

const MAX_HEADER_BYTES: usize = 16 * 1024;
// The pinned Xray HTTPUpgrade listener caps its request reader at 12288 bytes.
const MAX_REQUEST_BYTES: usize = 12 * 1024;
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(10);

/// Transport options after endpoint/Host fallback has been resolved.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub host: String,
    /// Xray's literal path, not a complete URL. Missing leading '/' is added.
    pub path: String,
    #[serde(default)]
    pub headers: Vec<(String, String)>,
}

impl Config {
    /// Validate before opening a network connection or transmitting bytes.
    pub fn validate(&self) -> Result<(), &'static str> {
        self.request().map(|_| ())
    }

    fn request(&self) -> Result<Vec<u8>, &'static str> {
        validate_host(&self.host).map_err(|_| "HttpUpgradeHost")?;
        if self.path.len() > 4096 || self.path.chars().any(char::is_control) {
            return Err("HttpUpgradePath");
        }
        // Xray interprets ?ed= as an early-data option before constructing its
        // literal URL.Path. This implementation never silently enables it.
        if self.path.split_once('?').is_some_and(|(_, query)| {
            url::form_urlencoded::parse(query.as_bytes()).any(|(key, _)| key == "ed")
        }) {
            return Err("HttpUpgradeEarlyDataUnsupported");
        }
        if self.headers.len() > 64 {
            return Err("HttpUpgradeHeaderLimit");
        }
        let mut request = format!(
            "GET {} HTTP/1.1\r\nHost: {}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n",
            literal_path(&self.path),
            self.host
        );
        for (name, value) in &self.headers {
            let parsed =
                HeaderName::from_bytes(name.as_bytes()).map_err(|_| "HttpUpgradeHeaderName")?;
            HeaderValue::from_str(value).map_err(|_| "HttpUpgradeHeaderValue")?;
            if matches!(
                parsed.as_str(),
                "host" | "connection" | "upgrade" | "content-length" | "transfer-encoding"
            ) || parsed.as_str().starts_with("sec-websocket-")
            {
                return Err("HttpUpgradeReservedHeader");
            }
            request.push_str(name);
            request.push_str(": ");
            request.push_str(value);
            request.push_str("\r\n");
            if request.len() > MAX_REQUEST_BYTES - 2 {
                return Err("HttpUpgradeHeaderLimit");
            }
        }
        request.push_str("\r\n");
        if request.len() > MAX_REQUEST_BYTES {
            return Err("HttpUpgradeHeaderLimit");
        }
        Ok(request.into_bytes())
    }
}

// Keep only the syntax of an HTTP authority. In particular, URI user-info is
// never an HTTP Host, and a raw IPv6 literal must use brackets.
fn validate_host(host: &str) -> Result<(), ()> {
    if host.is_empty()
        || host.len() > 1024
        || !host.is_ascii()
        || host
            .bytes()
            .any(|b| b <= b' ' || b == 127 || b"/?#@\\".contains(&b))
    {
        return Err(());
    }
    let url = url::Url::parse(&format!("http://{host}/")).map_err(|_| ())?;
    if url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.path() != "/"
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err(());
    }
    Ok(())
}

// Go's URL.Path is a decoded path. Escape literal %, ?, # and UTF-8 bytes so
// the independently running Xray server observes the original configured path.
fn literal_path(path: &str) -> String {
    let mut result = String::with_capacity(path.len() + 1);
    if !path.starts_with('/') {
        result.push('/');
    }
    for byte in path.bytes() {
        if byte.is_ascii_alphanumeric() || b"/-._~!$&'()*+,;=:@".contains(&byte) {
            result.push(char::from(byte));
        } else {
            const HEX: &[u8] = b"0123456789ABCDEF";
            result.push('%');
            result.push(char::from(HEX[usize::from(byte >> 4)]));
            result.push(char::from(HEX[usize::from(byte & 15)]));
        }
    }
    result
}

fn check_response(data: &[u8]) -> Result<(), &'static str> {
    let mut headers = [httparse::EMPTY_HEADER; 64];
    let mut response = httparse::Response::new(&mut headers);
    if !response
        .parse(data)
        .map_err(|_| "HttpUpgradeResponseSyntax")?
        .is_complete()
        || response.version != Some(1)
        || response.code != Some(101)
    {
        return Err("HttpUpgradeRejected");
    }
    let mut upgrade = false;
    let mut connection = false;
    for header in response.headers.iter() {
        let value = std::str::from_utf8(header.value)
            .map_err(|_| "HttpUpgradeResponseSyntax")?
            .trim();
        match header.name.to_ascii_lowercase().as_str() {
            "upgrade" => {
                if upgrade || !value.eq_ignore_ascii_case("websocket") {
                    return Err("HttpUpgradeResponseProtocol");
                }
                upgrade = true;
            }
            "connection" => {
                connection |= value
                    .split(',')
                    .any(|token| token.trim().eq_ignore_ascii_case("upgrade"));
            }
            "transfer-encoding" | "sec-websocket-extensions" | "sec-websocket-protocol" => {
                return Err("HttpUpgradeUnexpectedFraming");
            }
            "content-length" if value != "0" => return Err("HttpUpgradeUnexpectedFraming"),
            _ => {}
        }
    }
    if !upgrade || !connection {
        return Err("HttpUpgradeResponseProtocol");
    }
    Ok(())
}

/// Upgrade an already connected TCP/TLS stream. Failed, timed-out, or cancelled
/// handshakes drop their owned stream; they cannot leak a background task.
pub async fn connect(wire: BoxStream, config: &Config) -> Result<BoxStream, &'static str> {
    connect_with_timeout(wire, config, HANDSHAKE_TIMEOUT).await
}

pub async fn connect_with_timeout(
    mut wire: BoxStream,
    config: &Config,
    timeout: Duration,
) -> Result<BoxStream, &'static str> {
    let request = config.request()?;
    tokio::time::timeout(timeout, async move {
        wire.write_all(&request)
            .await
            .map_err(|_| "HttpUpgradeRequestWrite")?;
        wire.flush().await.map_err(|_| "HttpUpgradeRequestWrite")?;
        let mut reader = BufReader::with_capacity(4096, wire);
        let mut response = Vec::with_capacity(1024);
        while !response.ends_with(b"\r\n\r\n") {
            if response.len() == MAX_HEADER_BYTES {
                return Err("HttpUpgradeResponseLimit");
            }
            response.push(
                reader
                    .read_u8()
                    .await
                    .map_err(|_| "HttpUpgradeResponseRead")?,
            );
        }
        check_response(&response)?;
        // BufReader retains any proxy bytes received in the same read as the
        // 101 response. AsyncWrite (including half-close) delegates to the wire.
        Ok(Box::new(reader) as BoxStream)
    })
    .await
    .map_err(|_| "HttpUpgradeTimeout")?
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> Config {
        Config {
            host: "transport.example:8443".into(),
            path: "/non-root/原样?value=1%2F".into(),
            headers: vec![("X-Test".into(), "allowed".into())],
        }
    }

    #[test]
    fn validates_headers_and_literal_path() {
        let request = String::from_utf8(config().request().unwrap()).unwrap();
        assert!(
            request.starts_with("GET /non-root/%E5%8E%9F%E6%A0%B7%3Fvalue=1%252F HTTP/1.1\r\n")
        );
        assert!(request.contains("Host: transport.example:8443\r\n"));
        assert!(request.contains("X-Test: allowed\r\n"));
        assert!(!request.contains("Sec-WebSocket"));
        let mut bad = config();
        for name in [
            "Host",
            "Upgrade",
            "Connection",
            "Content-Length",
            "Transfer-Encoding",
            "Sec-WebSocket-Key",
        ] {
            bad.headers = vec![(name.into(), "value".into())];
            assert_eq!(bad.validate(), Err("HttpUpgradeReservedHeader"));
        }
        bad.headers = vec![("X-Test".into(), "a\r\nInjected: yes".into())];
        assert_eq!(bad.validate(), Err("HttpUpgradeHeaderValue"));
        bad.headers = vec![("X-Test".into(), "x".repeat(MAX_REQUEST_BYTES))];
        assert_eq!(bad.validate(), Err("HttpUpgradeHeaderLimit"));
        bad = config();
        bad.path = "/transport?ed=2048".into();
        assert_eq!(bad.validate(), Err("HttpUpgradeEarlyDataUnsupported"));
        for host in ["a@b", "a/b", "a\r\nX: y", "::1", "a:invalid"] {
            bad = config();
            bad.host = host.into();
            assert_eq!(bad.validate(), Err("HttpUpgradeHost"));
        }
        bad = config();
        bad.host = "[::1]:8443".into();
        assert!(bad.validate().is_ok());
    }

    #[test]
    fn rejects_wrong_status_protocol_and_framing() {
        for response in [
            "HTTP/1.1 200 OK\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n",
            "HTTP/1.1 101 Switching Protocols\r\nConnection: close\r\nUpgrade: websocket\r\n\r\n",
            "HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: h2c\r\n\r\n",
            "HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nTransfer-Encoding: chunked\r\n\r\n",
        ] {
            assert!(check_response(response.as_bytes()).is_err());
        }
    }

    #[tokio::test]
    async fn preserves_upgrade_tail_and_raw_bidirectional_half_close() {
        let (wire, mut peer) = tokio::io::duplex(1024);
        let server = tokio::spawn(async move {
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                request.push(peer.read_u8().await.unwrap());
            }
            assert!(request.starts_with(b"GET /non-root/"));
            peer.write_all(b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\nserver-prefix")
                .await.unwrap();
            let mut upload = Vec::new();
            peer.read_to_end(&mut upload).await.unwrap();
            assert_eq!(upload, vec![0xa5; 2 * 1024 * 1024]);
            peer.write_all(b"after-half-close").await.unwrap();
            peer.shutdown().await.unwrap();
        });
        let mut stream = connect(Box::new(wire), &config()).await.unwrap();
        let mut prefix = [0; 13];
        stream.read_exact(&mut prefix).await.unwrap();
        assert_eq!(&prefix, b"server-prefix");
        stream
            .write_all(&vec![0xa5; 2 * 1024 * 1024])
            .await
            .unwrap();
        stream.shutdown().await.unwrap();
        let mut tail = Vec::new();
        stream.read_to_end(&mut tail).await.unwrap();
        assert_eq!(tail, b"after-half-close");
        server.await.unwrap();
    }

    #[tokio::test]
    async fn stalled_server_times_out_and_owned_stream_closes() {
        let (wire, mut peer) = tokio::io::duplex(1024);
        let error = connect_with_timeout(Box::new(wire), &config(), Duration::from_millis(20))
            .await
            .err()
            .unwrap();
        assert_eq!(error, "HttpUpgradeTimeout");
        let mut request = Vec::new();
        peer.read_to_end(&mut request).await.unwrap();
        assert!(request.ends_with(b"\r\n\r\n"));
    }

    #[tokio::test]
    async fn response_size_is_bounded() {
        let (wire, mut peer) = tokio::io::duplex(32768);
        peer.write_all(&vec![b'A'; MAX_HEADER_BYTES + 1])
            .await
            .unwrap();
        let error = connect(Box::new(wire), &config()).await.err().unwrap();
        assert_eq!(error, "HttpUpgradeResponseLimit");
    }
}
