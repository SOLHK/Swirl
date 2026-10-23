//! The legacy Xray/V2Ray HTTP/2 transport: a streaming PUT body, not CONNECT.
//!
//! Wire reference: Xray 1.8.24, `6baad79f9881ee2cf75bdc825b3e2e92b289477a`,
//! transport/internet/http/{dialer,hub,config}.go. Modern Xray removed this
//! transport; callers must not silently replace it with XHTTP.

use crate::{BoxStream, h2_stream};
use http::{Request, Uri};
use std::time::Duration;

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub host: String,
    pub path: String,
    pub headers: Vec<(String, String)>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            host: "www.example.com".into(),
            path: "/".into(),
            headers: Vec::new(),
        }
    }
}

impl Config {
    /// Validate syntax independently of the security layer. `connect` also
    /// requires a secured stream; validation alone is not a TLS handshake.
    pub fn validate(&self) -> Result<(), &'static str> {
        request(self, true).map(|_| ())
    }
}

fn request(config: &Config, tls: bool) -> Result<Request<()>, &'static str> {
    if !tls {
        return Err("Http2TlsRequired");
    }
    let host = if config.host.is_empty() {
        "www.example.com"
    } else {
        &config.host
    };
    let path = normalized_path(&config.path);
    let uri = Uri::builder()
        .scheme("https")
        .authority(h2_stream::authority(host)?)
        .path_and_query(path)
        .build()
        .map_err(|_| "Http2Path")?;
    let mut request = Request::builder()
        .method("PUT")
        .uri(uri)
        .header("accept-encoding", "identity")
        .body(())
        .map_err(|_| "Http2Request")?;
    h2_stream::append_headers(&mut request, &config.headers, &["accept-encoding"])?;
    Ok(request)
}

// Go's URL.Path is a decoded path, so query/fragment delimiters and percent
// signs in the configured path are escaped rather than changing URI meaning.
fn normalized_path(path: &str) -> String {
    let mut result = String::new();
    if !path.starts_with('/') {
        result.push('/');
    }
    for byte in path.bytes() {
        if byte.is_ascii_alphanumeric()
            || matches!(
                byte,
                b'-' | b'_'
                    | b'.'
                    | b'~'
                    | b'/'
                    | b'$'
                    | b'&'
                    | b'+'
                    | b':'
                    | b'='
                    | b'@'
                    | b';'
                    | b','
            )
        {
            result.push(byte as char);
        } else {
            result.push('%');
            result.push(b"0123456789ABCDEF"[(byte >> 4) as usize] as char);
            result.push(b"0123456789ABCDEF"[(byte & 15) as usize] as char);
        }
    }
    result
}

pub async fn connect(
    stream: BoxStream,
    config: &Config,
    tls: bool,
) -> Result<BoxStream, &'static str> {
    let request = request(config, tls)?;
    h2_stream::connect(stream, request, h2_stream::ResponseKind::Raw).await
}

/// Like `connect`, with a deadline for deferred response headers. The caller
/// remains responsible for the overall dial/TLS/HTTP handshake budget.
pub async fn connect_with_timeout(
    stream: BoxStream,
    config: &Config,
    tls: bool,
    header_timeout: Duration,
) -> Result<BoxStream, &'static str> {
    let request = request(config, tls)?;
    h2_stream::connect_with_timeout(
        stream,
        request,
        h2_stream::ResponseKind::Raw,
        header_timeout,
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn legacy_method_host_and_decoded_path_match_upstream() {
        let config = Config {
            host: "h2.example:443".into(),
            path: "tunnel/name?not=query#not-fragment".into(),
            headers: vec![("x-route".into(), "custom".into())],
        };
        let req = request(&config, true).unwrap();
        assert_eq!(req.method(), "PUT");
        assert_eq!(req.uri().authority().unwrap().as_str(), "h2.example:443");
        assert_eq!(req.uri().path(), "/tunnel/name%3Fnot=query%23not-fragment");
        assert_eq!(req.headers()["x-route"], "custom");
        assert!(request(&Config::default(), false).is_err());
    }

    #[test]
    fn path_and_host_cannot_inject_http_fields() {
        let mut config = Config {
            host: "example.com\r\nx-header: bad".into(),
            ..Default::default()
        };
        assert!(request(&config, true).is_err());
        config.host = "user@example.com".into();
        assert!(request(&config, true).is_err());
        assert_eq!(normalized_path("/a%2Fb"), "/a%252Fb");
        assert_eq!(normalized_path(""), "/");
    }
}
