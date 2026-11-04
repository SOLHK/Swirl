//! Fixed-buffer full-duplex transfer with independent half-close and live counters.
pub mod egress;
pub mod grpc;
mod h2_stream;
pub mod http2;
pub mod httpupgrade;
pub mod inbound;
pub mod quic;
pub mod reality;
mod udp;
pub mod xhttp;
pub use egress::connect_tcp;
pub use udp::{bind_udp, bind_udp_inbound, reserve_datagram_buffers};

use std::{
    io,
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    },
};
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};

#[derive(Default)]
pub struct Counters {
    pub upload: AtomicU64,
    pub download: AtomicU64,
    pub udp_dropped: AtomicU64,
}
pub trait Stream: AsyncRead + AsyncWrite + Unpin + Send {}
impl<T: AsyncRead + AsyncWrite + Unpin + Send> Stream for T {}
pub type BoxStream = Box<dyn Stream>;

/// Authenticate TLS over a native byte stream, including an already negotiated
/// proxy tunnel. The same verification path applies to direct and nested TLS.
pub async fn secure<S: Stream + 'static>(
    stream: S,
    tls: &swirl_subscription::Tls,
) -> Result<BoxStream, &'static str> {
    secure_with_alpn(stream, tls, None).await
}

/// Authenticate TLS and require the selected application protocol where the
/// transport needs it. An empty offer gets that transport's protocol; an
/// explicit incompatible offer or a different negotiated offer is rejected.
pub async fn secure_with_alpn<S: Stream + 'static>(
    stream: S,
    tls: &swirl_subscription::Tls,
    required_alpn: Option<&[u8]>,
) -> Result<BoxStream, &'static str> {
    use tokio_rustls::TlsConnector;
    let (config, name) = tls_context(tls, required_alpn)?;
    let stream = TlsConnector::from(config)
        .connect(name, stream)
        .await
        .map_err(|error| tls_failure_code(&error))?;
    if required_alpn.is_some_and(|required| stream.get_ref().1.alpn_protocol() != Some(required)) {
        return Err("TlsAlpnNegotiation");
    }
    Ok(Box::new(stream))
}

// Preserve only typed, fixed categories. Rustls context can contain private
// expected/presented names; neither its Display nor Debug text is exported.
fn tls_failure_code(error: &io::Error) -> &'static str {
    use tokio_rustls::rustls::{CertificateError, Error};
    if let Some(tls_error) = error
        .get_ref()
        .and_then(|inner| inner.downcast_ref::<Error>())
    {
        return match tls_error {
            Error::InvalidCertificate(certificate) => match certificate {
                CertificateError::Expired | CertificateError::ExpiredContext { .. } => {
                    "TlsCertificateExpired"
                }
                CertificateError::NotValidYet | CertificateError::NotValidYetContext { .. } => {
                    "TlsCertificateNotValidYet"
                }
                CertificateError::NotValidForName
                | CertificateError::NotValidForNameContext { .. } => "TlsCertificateNameMismatch",
                CertificateError::UnknownIssuer => "TlsCertificateUnknownIssuer",
                CertificateError::Revoked => "TlsCertificateRevoked",
                _ => "TlsCertificateInvalid",
            },
            Error::NoCertificatesPresented => "TlsCertificateMissing",
            _ => "TlsVerificationOrHandshake",
        };
    }
    match error.kind() {
        io::ErrorKind::UnexpectedEof => "TlsHandshakeEof",
        io::ErrorKind::ConnectionReset => "TlsConnectionReset",
        io::ErrorKind::ConnectionAborted => "TlsConnectionAborted",
        io::ErrorKind::ConnectionRefused => "TlsConnectionRefused",
        io::ErrorKind::TimedOut => "TlsHandshakeIoTimeout",
        io::ErrorKind::BrokenPipe => "TlsHandshakeBrokenPipe",
        _ => "TlsVerificationOrHandshake",
    }
}

#[cfg(test)]
#[path = "tls_failure_tests.rs"]
mod tls_failure_tests;

/// Validate certificate material, SNI and ALPN without opening a socket. The
/// bounded cache also avoids rebuilding the root store on each TLS connection.
pub fn validate_tls(
    tls: &swirl_subscription::Tls,
    required_alpn: Option<&[u8]>,
) -> Result<(), &'static str> {
    tls_context(tls, required_alpn).map(|_| ())
}

type PreparedTls = (
    Arc<tokio_rustls::rustls::ClientConfig>,
    tokio_rustls::rustls::pki_types::ServerName<'static>,
);

fn tls_context(
    tls: &swirl_subscription::Tls,
    required_alpn: Option<&[u8]>,
) -> Result<PreparedTls, &'static str> {
    use std::{
        collections::VecDeque,
        sync::{Mutex, OnceLock},
    };
    use tokio_rustls::rustls::{
        ClientConfig, RootCertStore,
        pki_types::{CertificateDer, ServerName},
    };
    #[derive(Clone, PartialEq, Eq)]
    struct Key {
        ca: Option<String>,
        alpn: Vec<Vec<u8>>,
    }
    type Entry = (Key, Arc<ClientConfig>);
    static CONTEXTS: OnceLock<Mutex<VecDeque<Entry>>> = OnceLock::new();
    let name = ServerName::try_from(tls.server_name.clone()).map_err(|_| "TlsServerName")?;
    if tls.ca_der_base64.as_ref().is_some_and(|s| s.len() > 65536)
        || tls.alpn.len() > 16
        || tls.alpn.iter().any(|s| {
            s.is_empty()
                || s.len() > 255
                || !s.is_ascii()
                || s.bytes().any(|b| b.is_ascii_control())
        })
    {
        return Err("TlsParameters");
    }
    let mut alpn: Vec<Vec<u8>> = tls.alpn.iter().map(|s| s.as_bytes().to_vec()).collect();
    if let Some(required) = required_alpn {
        if alpn.is_empty() {
            alpn.push(required.to_vec());
        } else if !alpn.iter().any(|value| value == required) {
            return Err("TlsAlpnUnsupported");
        }
    }
    let key = Key {
        ca: tls.ca_der_base64.clone(),
        alpn,
    };
    let cache = CONTEXTS.get_or_init(|| Mutex::new(VecDeque::new()));
    {
        let mut cache = cache.lock().map_err(|_| "TlsContextLock")?;
        if let Some(index) = cache.iter().position(|(stored, _)| *stored == key) {
            let entry = cache.remove(index).ok_or("TlsContextCache")?;
            let config = entry.1.clone();
            cache.push_back(entry);
            return Ok((config, name));
        }
    }
    let mut roots = RootCertStore::from_iter(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
    if let Some(encoded) = &key.ca {
        use base64::Engine;
        let der = base64::engine::general_purpose::STANDARD
            .decode(encoded)
            .map_err(|_| "TlsTrustAnchor")?;
        roots
            .add(CertificateDer::from(der))
            .map_err(|_| "TlsTrustAnchor")?;
    }
    let mut config = ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    config.alpn_protocols = key.alpn.clone();
    // The current native schema does not expose session-resumption/0-RTT
    // policy. In particular, imported enableSessionResumption=false is honored.
    config.resumption = tokio_rustls::rustls::client::Resumption::disabled();
    config.enable_early_data = false;
    let config = Arc::new(config);
    let mut cache = cache.lock().map_err(|_| "TlsContextLock")?;
    if let Some((_, existing)) = cache.iter().find(|(stored, _)| *stored == key) {
        return Ok((existing.clone(), name));
    }
    if cache.len() == 32 {
        cache.pop_front();
    }
    cache.push_back((key, config.clone()));
    Ok((config, name))
}

async fn pump<R: AsyncRead + Unpin, W: AsyncWrite + Unpin>(
    mut reader: R,
    mut writer: W,
    local: &AtomicU64,
    total: &AtomicU64,
) -> io::Result<()> {
    let mut buffer = [0u8; 16 * 1024];
    loop {
        let n = reader.read(&mut buffer).await?;
        if n == 0 {
            return writer.shutdown().await;
        }
        let mut offset = 0;
        while offset < n {
            let written = writer.write(&buffer[offset..n]).await?;
            if written == 0 {
                return Err(io::ErrorKind::WriteZero.into());
            }
            offset += written;
            local.fetch_add(written as u64, Ordering::Relaxed);
            total.fetch_add(written as u64, Ordering::Relaxed);
        }
        writer.flush().await?;
    }
}
pub async fn relay<A: Stream, B: Stream>(
    a: &mut A,
    b: &mut B,
    local: Arc<Counters>,
    total: Arc<Counters>,
) -> io::Result<()> {
    let (ar, aw) = tokio::io::split(a);
    let (br, bw) = tokio::io::split(b);
    tokio::try_join!(
        pump(ar, bw, &local.upload, &total.upload),
        pump(br, aw, &local.download, &total.download)
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tls_context_reuses_trust_policy_and_rejects_invalid_material_before_io() {
        let mut tls = swirl_subscription::Tls {
            server_name: "one.invalid".into(),
            alpn: vec!["h2".into()],
            ca_der_base64: None,
        };
        let first = tls_context(&tls, Some(b"h2")).unwrap().0;
        tls.server_name = "two.invalid".into();
        let second = tls_context(&tls, Some(b"h2")).unwrap().0;
        assert!(Arc::ptr_eq(&first, &second));
        tls.alpn = vec!["http/1.1".into()];
        assert!(matches!(
            tls_context(&tls, Some(b"h2")),
            Err("TlsAlpnUnsupported")
        ));
        let http1 = tls_context(&tls, Some(b"http/1.1")).unwrap().0;
        assert!(!Arc::ptr_eq(&first, &http1));
        tls.ca_der_base64 = Some("AA==".into());
        assert!(matches!(tls_context(&tls, None), Err("TlsTrustAnchor")));
        tls.ca_der_base64 = Some("not-base64".into());
        assert!(matches!(tls_context(&tls, None), Err("TlsTrustAnchor")));
        tls.ca_der_base64 = None;
        tls.server_name = "bad/server".into();
        assert!(matches!(tls_context(&tls, None), Err("TlsServerName")));
        tls.server_name = "one.invalid".into();
        tls.alpn = vec!["h2\r\n".into()];
        assert!(matches!(tls_context(&tls, None), Err("TlsParameters")));
    }
    #[tokio::test]
    async fn eof_keeps_reverse_direction_alive() {
        let (mut a, mut x) = tokio::io::duplex(32);
        let (mut y, mut b) = tokio::io::duplex(32);
        let total = Arc::new(Counters::default());
        let result = tokio::spawn({
            let total = total.clone();
            async move { relay(&mut x, &mut y, Arc::new(Counters::default()), total).await }
        });
        a.write_all(b"request").await.unwrap();
        a.shutdown().await.unwrap();
        let mut request = Vec::new();
        b.read_to_end(&mut request).await.unwrap();
        assert_eq!(request, b"request");
        b.write_all(b"tail-after-half-close").await.unwrap();
        b.shutdown().await.unwrap();
        let mut tail = Vec::new();
        a.read_to_end(&mut tail).await.unwrap();
        assert_eq!(tail, b"tail-after-half-close");
        result.await.unwrap().unwrap();
        assert_eq!(total.upload.load(Ordering::Relaxed), 7);
    }
}
