//! Native XHTTP `stream-one` over HTTP/2.
//!
//! This is a single full-duplex POST: its request and response DATA bytes are
//! the proxy byte stream. The camouflage `application/grpc` content type does
//! not introduce a protobuf or gRPC envelope. A session ID is not used.
//!
//! Reference: Xray-core v26.10.21, commit
//! `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`, `transport/internet/splithttp/`.
//! Only the default Referer padding placement is implemented. HTTP/3, upload
//! packets, separate upload/download streams, and XMUX policy are not implied.

use crate::{BoxStream, h2_stream};
use http::{HeaderName, HeaderValue, Request, Uri};
use ring::rand::{SecureRandom, SystemRandom};
use serde::{Deserialize, Serialize};
use std::time::Duration;

/// A resolved, explicitly supported XHTTP stream configuration.
///
/// Importers must reject unrepresented Xray `extra` options instead of dropping
/// them when constructing this type. In particular `auto` is not an alias for
/// `stream-one`: Xray normally selects `packet-up` with ordinary TLS.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub mode: String,
    pub host: String,
    pub path: String,
    #[serde(default)]
    pub headers: Vec<(String, String)>,
}

impl Config {
    pub fn stream_one(host: impl Into<String>, path: impl Into<String>) -> Self {
        Self {
            mode: "stream-one".into(),
            host: host.into(),
            path: path.into(),
            headers: Vec::new(),
        }
    }

    pub fn validate(&self) -> Result<(), &'static str> {
        self.request_with_padding(false, 100).map(|_| ())
    }

    fn request(&self, tls: bool) -> Result<Request<()>, &'static str> {
        self.validate()?;
        let mut random = [0; 4];
        SystemRandom::new()
            .fill(&mut random)
            .map_err(|_| "XHttpPaddingRandom")?;
        let padding_length = 100 + (u32::from_be_bytes(random) % 901) as usize;
        self.request_with_padding(tls, padding_length)
    }

    fn request_with_padding(
        &self,
        tls: bool,
        padding_length: usize,
    ) -> Result<Request<()>, &'static str> {
        if self.mode != "stream-one" {
            return Err("XHttpModeUnsupported");
        }
        validate_host(&self.host)?;
        if self.path.len() > 4096 || self.path.chars().any(char::is_control) {
            return Err("XHttpPath");
        }
        if self.headers.len() > 64 {
            return Err("XHttpHeaderLimit");
        }
        let (path, query) = self.path.split_once('?').unwrap_or((&self.path, ""));
        if !query.is_ascii() || query.bytes().any(|b| b <= b' ' || b == 127 || b == b'#') {
            return Err("XHttpQuery");
        }
        let mut normalized = literal_path(path);
        if !normalized.ends_with('/') {
            normalized.push('/');
        }
        let scheme = if tls { "https" } else { "http" };
        let base = format!("{scheme}://{}{normalized}", self.host);
        let target = if query.is_empty() {
            base.clone()
        } else {
            format!("{base}?{query}")
        };
        let uri: Uri = target.parse().map_err(|_| "XHttpPath")?;
        // Xray replaces the Referer's query, preserving the actual target's
        // query. Its default server rejects absent padding and accepts 100..1000.
        let referer = format!("{base}?x_padding={}", "X".repeat(padding_length));
        let mut request = Request::builder()
            .method(http::Method::POST)
            .version(http::Version::HTTP_2)
            .uri(uri)
            .header(http::header::CONTENT_TYPE, "application/grpc")
            .header(http::header::REFERER, referer)
            .body(())
            .map_err(|_| "XHttpRequest")?;
        // Reserve the largest supported padding before dialing as well as on
        // the actual request. A configuration near the limit must not fail
        // nondeterministically when the per-connection random padding changes.
        let mut header_size = base.len() + 1000 + 64;
        for (name, value) in &self.headers {
            let name = HeaderName::from_bytes(name.as_bytes()).map_err(|_| "XHttpHeaderName")?;
            let value = HeaderValue::from_str(value).map_err(|_| "XHttpHeaderValue")?;
            // Never allow caller headers to change framing, negotiated HTTP
            // version, authority or the mandatory padding semantics.
            if matches!(
                name.as_str(),
                "host"
                    | "connection"
                    | "upgrade"
                    | "keep-alive"
                    | "proxy-connection"
                    | "transfer-encoding"
                    | "content-length"
                    | "content-type"
                    | "referer"
                    | "te"
                    | "trailer"
                    | "accept-encoding"
            ) {
                return Err("XHttpReservedHeader");
            }
            header_size += name.as_str().len() + value.as_bytes().len() + 4;
            if header_size > 16 * 1024 {
                return Err("XHttpHeaderLimit");
            }
            request.headers_mut().append(name, value);
        }
        Ok(request)
    }
}

fn validate_host(host: &str) -> Result<(), &'static str> {
    if host.is_empty()
        || host.len() > 1024
        || !host.is_ascii()
        || host
            .bytes()
            .any(|b| b <= b' ' || b == 127 || b"/?#@\\".contains(&b))
    {
        return Err("XHttpHost");
    }
    let url = url::Url::parse(&format!("http://{host}/")).map_err(|_| "XHttpHost")?;
    if url.host_str().is_none() || !url.username().is_empty() || url.password().is_some() {
        return Err("XHttpHost");
    }
    Ok(())
}

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

/// The caller supplies a verified TLS/REALITY stream with ALPN h2, or an
/// explicit h2c stream for a server which accepts it. This function does not
/// choose or silently change the security or HTTP version.
pub async fn connect(
    wire: BoxStream,
    config: &Config,
    tls: bool,
) -> Result<BoxStream, &'static str> {
    let request = config.request(tls)?;
    h2_stream::connect(wire, request, h2_stream::ResponseKind::Raw).await
}

/// Use the caller's remaining budget for deferred HTTP/2 response headers.
/// The caller still owns the overall TCP, security and HTTP/2 handshake limit.
pub async fn connect_with_timeout(
    wire: BoxStream,
    config: &Config,
    tls: bool,
    header_timeout: Duration,
) -> Result<BoxStream, &'static str> {
    let request = config.request(tls)?;
    h2_stream::connect_with_timeout(wire, request, h2_stream::ResponseKind::Raw, header_timeout)
        .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stream_one_has_raw_body_semantics_and_default_padding_headers() {
        let mut config = Config::stream_one("xhttp.example:8443", "non-root/path?token=test");
        config.headers.push(("x-test".into(), "custom".into()));
        let request = config.request_with_padding(true, 137).unwrap();
        assert_eq!(request.method(), http::Method::POST);
        assert_eq!(request.version(), http::Version::HTTP_2);
        assert_eq!(
            request.uri().to_string(),
            "https://xhttp.example:8443/non-root/path/?token=test"
        );
        assert_eq!(request.headers()["content-type"], "application/grpc");
        assert_eq!(request.headers()["x-test"], "custom");
        assert_eq!(
            request.headers()["referer"],
            format!(
                "https://xhttp.example:8443/non-root/path/?x_padding={}",
                "X".repeat(137)
            )
        );
        assert!(!request.headers().contains_key("te"));
        assert!(!request.headers().contains_key("content-length"));
    }

    #[test]
    fn path_and_ipv6_authority_are_preserved() {
        let config = Config::stream_one("[::1]:8443", "/字%2F?");
        let request = config.request_with_padding(false, 100).unwrap();
        assert_eq!(
            request.uri().to_string(),
            "http://[::1]:8443/%E5%AD%97%252F/"
        );
        for path in ["", "/"] {
            let request = Config::stream_one("host.example", path)
                .request_with_padding(true, 100)
                .unwrap();
            assert_eq!(request.uri().path(), "/");
        }
    }

    #[test]
    fn unsupported_modes_and_ambiguous_headers_are_rejected() {
        let mut config = Config::stream_one("host.example", "/proxy");
        for mode in [
            "",
            "auto",
            "packet-up",
            "stream-up",
            "stream-one-h3",
            "unknown",
        ] {
            config.mode = mode.into();
            assert_eq!(config.validate(), Err("XHttpModeUnsupported"));
        }
        config.mode = "stream-one".into();
        for name in [
            "Host",
            "Connection",
            "Content-Length",
            "Transfer-Encoding",
            "Content-Type",
            "Referer",
            "TE",
        ] {
            config.headers = vec![(name.into(), "value".into())];
            assert_eq!(config.validate(), Err("XHttpReservedHeader"));
        }
        config.headers = vec![("x-test".into(), "a\r\nInjected: b".into())];
        assert_eq!(config.validate(), Err("XHttpHeaderValue"));
    }

    #[test]
    fn oversized_or_injected_request_fields_are_rejected() {
        let mut config = Config::stream_one("a@b", "/proxy");
        assert_eq!(config.validate(), Err("XHttpHost"));
        config.host = "host.example".into();
        config.path = "/x\r\ny".into();
        assert_eq!(config.validate(), Err("XHttpPath"));
        config.path = "/x?abc#fragment".into();
        assert_eq!(config.validate(), Err("XHttpQuery"));
        config.path = "/x".into();
        config.headers = vec![("x-big".into(), "x".repeat(16384))];
        assert_eq!(config.validate(), Err("XHttpHeaderLimit"));
    }
}
