//! Fixed-buffer full-duplex transfer with independent half-close and live counters.
pub mod grpc;
mod h2_stream;
pub mod http2;
pub mod httpupgrade;
pub mod reality;
mod udp;
pub mod xhttp;
pub use udp::bind_udp;

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
/// explicit incompatible offer or a different negotiated protocol is rejected.
pub async fn secure_with_alpn<S: Stream + 'static>(
    stream: S,
    tls: &swirl_subscription::Tls,
    required_alpn: Option<&[u8]>,
) -> Result<BoxStream, &'static str> {
    use tokio_rustls::{
        TlsConnector,
        rustls::{ClientConfig, RootCertStore, pki_types::ServerName},
    };
    let mut roots = RootCertStore::from_iter(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
    if let Some(encoded) = &tls.ca_der_base64 {
        use base64::Engine;
        let der = base64::engine::general_purpose::STANDARD
            .decode(encoded)
            .map_err(|_| "TlsTrustAnchor")?;
        roots
            .add(tokio_rustls::rustls::pki_types::CertificateDer::from(der))
            .map_err(|_| "TlsTrustAnchor")?;
    }
    let mut config = ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    config.alpn_protocols = tls.alpn.iter().map(|s| s.as_bytes().to_vec()).collect();
    if let Some(required) = required_alpn {
        if config.alpn_protocols.is_empty() {
            config.alpn_protocols.push(required.to_vec());
        } else if !config.alpn_protocols.iter().any(|value| value == required) {
            return Err("TlsAlpnUnsupported");
        }
    }
    let name = ServerName::try_from(tls.server_name.clone()).map_err(|_| "TlsServerName")?;
    let stream = TlsConnector::from(Arc::new(config))
        .connect(name, stream)
        .await
        .map_err(|_| "TlsVerificationOrHandshake")?;
    if required_alpn.is_some_and(|required| stream.get_ref().1.alpn_protocol() != Some(required)) {
        return Err("TlsAlpnNegotiation");
    }
    Ok(Box::new(stream))
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
