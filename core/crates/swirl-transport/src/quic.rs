//! Shared native QUIC transport. Proxy authentication and framing stay in
//! swirl-protocol; Quinn only owns QUIC/TLS and reliable byte streams.
#[cfg(test)]
mod shutdown_tests;
use base64::Engine;
use quinn::{
    ClientConfig, Connection, Endpoint, RecvStream, Runtime, SendStream, TransportConfig, VarInt,
};
use ring::digest::{SHA256, digest};
use std::{
    collections::VecDeque,
    future::Future,
    io,
    net::SocketAddr,
    pin::Pin,
    sync::{Arc, Mutex, OnceLock},
    task::{Context, Poll, ready},
    time::Duration,
};
use swirl_subscription::Tls;
use tokio::{
    io::{AsyncRead, AsyncWrite, ReadBuf},
    time::{Instant, timeout_at},
};
use tokio_rustls::rustls::{
    self, CertificateError, DigitallySignedStruct, Error, RootCertStore, SignatureScheme,
    client::{
        WebPkiServerVerifier,
        danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier},
    },
    pki_types::{CertificateDer, ServerName, UnixTime},
};

pub type Result<T> = std::result::Result<T, &'static str>;

/// `insecure` is an explicit user setting. It never disables handshake
/// signature verification, and a configured certificate pin is always checked.
#[derive(Clone, Copy)]
pub struct TlsOptions<'a> {
    pub tls: &'a Tls,
    pub insecure: bool,
    pub pin_sha256: Option<&'a str>,
}

#[derive(Debug)]
struct Verifier {
    ordinary: Arc<WebPkiServerVerifier>,
    insecure: bool,
    pin: Option<[u8; 32]>,
}

impl ServerCertVerifier for Verifier {
    fn verify_server_cert(
        &self,
        end_entity: &CertificateDer<'_>,
        intermediates: &[CertificateDer<'_>],
        server_name: &ServerName<'_>,
        ocsp_response: &[u8],
        now: UnixTime,
    ) -> std::result::Result<ServerCertVerified, Error> {
        if let Some(expected) = self.pin {
            let actual = digest(&SHA256, end_entity.as_ref());
            if actual.as_ref() != expected {
                return Err(Error::InvalidCertificate(
                    CertificateError::ApplicationVerificationFailure,
                ));
            }
        }
        if self.insecure {
            Ok(ServerCertVerified::assertion())
        } else {
            self.ordinary.verify_server_cert(
                end_entity,
                intermediates,
                server_name,
                ocsp_response,
                now,
            )
        }
    }

    fn verify_tls12_signature(
        &self,
        message: &[u8],
        cert: &CertificateDer<'_>,
        dss: &DigitallySignedStruct,
    ) -> std::result::Result<HandshakeSignatureValid, Error> {
        self.ordinary.verify_tls12_signature(message, cert, dss)
    }

    fn verify_tls13_signature(
        &self,
        message: &[u8],
        cert: &CertificateDer<'_>,
        dss: &DigitallySignedStruct,
    ) -> std::result::Result<HandshakeSignatureValid, Error> {
        self.ordinary.verify_tls13_signature(message, cert, dss)
    }

    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> {
        self.ordinary.supported_verify_schemes()
    }
}

/// Parse the certificate's SHA-256 hex digest. Colon-delimited octets are
/// accepted, but arbitrary separators, truncation and non-hex data are not.
pub fn parse_pin(value: &str) -> Result<[u8; 32]> {
    let bytes = value.as_bytes();
    let mut result = [0; 32];
    let step = match bytes.len() {
        64 => 2,
        95 => 3,
        _ => return Err("QuicCertificatePin"),
    };
    for (index, byte) in result.iter_mut().enumerate() {
        let offset = index * step;
        let digit = |v: u8| match v {
            b'0'..=b'9' => Ok(v - b'0'),
            b'a'..=b'f' => Ok(v - b'a' + 10),
            b'A'..=b'F' => Ok(v - b'A' + 10),
            _ => Err("QuicCertificatePin"),
        };
        *byte = (digit(bytes[offset])? << 4) | digit(bytes[offset + 1])?;
        if step == 3 && index < 31 && bytes[offset + 2] != b':' {
            return Err("QuicCertificatePin");
        }
    }
    Ok(result)
}

/// Build once for all resolved addresses. ALPN and certificate settings are
/// validated before binding a socket. Only TLS 1.3 is offered for QUIC.
pub fn client_config(
    options: TlsOptions<'_>,
    required_alpn: Option<&[u8]>,
    congestion: &str,
) -> Result<ClientConfig> {
    build_client_config(options, required_alpn, congestion, false)
}

/// Validate complete QUIC TLS settings without DNS, socket creation or tasks.
/// The same bounded crypto cache is used by the eventual connection builder.
pub fn validate(
    options: TlsOptions<'_>,
    required_alpn: Option<&[u8]>,
    congestion: &str,
) -> Result<()> {
    client_config(options, required_alpn, congestion).map(|_| ())
}

#[derive(Clone, PartialEq, Eq)]
struct CryptoKey {
    ca: Option<String>,
    alpn: Vec<Vec<u8>>,
    insecure: bool,
    pin: Option<[u8; 32]>,
}
type Crypto = quinn::crypto::rustls::QuicClientConfig;
type CryptoCache = Mutex<VecDeque<(CryptoKey, Arc<Crypto>)>>;
static CRYPTO_CONTEXTS: OnceLock<CryptoCache> = OnceLock::new();

fn crypto_context(
    options: TlsOptions<'_>,
    alpn: Vec<Vec<u8>>,
    pin: Option<[u8; 32]>,
) -> Result<Arc<Crypto>> {
    if options
        .tls
        .ca_der_base64
        .as_ref()
        .is_some_and(|value| value.len() > 128 * 1024)
    {
        return Err("TlsTrustAnchor");
    }
    let key = CryptoKey {
        ca: options.tls.ca_der_base64.clone(),
        alpn,
        insecure: options.insecure,
        pin,
    };
    let cache = CRYPTO_CONTEXTS.get_or_init(|| Mutex::new(VecDeque::new()));
    {
        let mut entries = cache.lock().map_err(|_| "QuicContextState")?;
        if let Some(index) = entries.iter().position(|(stored, _)| stored == &key) {
            let entry = entries.remove(index).ok_or("QuicContextState")?;
            let crypto = entry.1.clone();
            entries.push_back(entry);
            return Ok(crypto);
        }
    }
    let mut roots = RootCertStore::from_iter(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
    if let Some(encoded) = &key.ca {
        let der = base64::engine::general_purpose::STANDARD
            .decode(encoded)
            .map_err(|_| "TlsTrustAnchor")?;
        roots
            .add(CertificateDer::from(der))
            .map_err(|_| "TlsTrustAnchor")?;
    }
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let ordinary = WebPkiServerVerifier::builder_with_provider(Arc::new(roots), provider.clone())
        .build()
        .map_err(|_| "TlsTrustAnchor")?;
    let verifier = Arc::new(Verifier {
        ordinary,
        insecure: key.insecure,
        pin: key.pin,
    });
    let mut tls = rustls::ClientConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&rustls::version::TLS13])
        .map_err(|_| "QuicTls13")?
        .dangerous()
        .with_custom_certificate_verifier(verifier)
        .with_no_client_auth();
    tls.alpn_protocols = key.alpn.clone();
    // Cache configuration only: retain the previous per-connection session
    // policy instead of implicitly enabling resumption through this cache.
    tls.resumption = rustls::client::Resumption::disabled();
    tls.enable_early_data = false;
    let crypto = Arc::new(Crypto::try_from(tls).map_err(|_| "QuicTls13")?);
    // No DNS, IO or certificate parsing runs under the global mutex. A race
    // may prepare twice, but only one bounded context is retained per key.
    let mut entries = cache.lock().map_err(|_| "QuicContextState")?;
    if let Some((_, existing)) = entries.iter().find(|(stored, _)| stored == &key) {
        return Ok(existing.clone());
    }
    if entries.len() == 32 {
        entries.pop_front();
    }
    entries.push_back((key, crypto.clone()));
    Ok(crypto)
}

fn build_client_config(
    options: TlsOptions<'_>,
    required_alpn: Option<&[u8]>,
    congestion: &str,
    wrapped: bool,
) -> Result<ClientConfig> {
    ServerName::try_from(options.tls.server_name.clone()).map_err(|_| "QuicServerName")?;
    let pin = options.pin_sha256.map(parse_pin).transpose()?;
    if options.tls.alpn.len() > 16
        || options
            .tls
            .alpn
            .iter()
            .any(|s| s.is_empty() || s.len() > 255)
    {
        return Err("QuicAlpn");
    }
    let mut alpn: Vec<Vec<u8>> = options
        .tls
        .alpn
        .iter()
        .map(|s| s.as_bytes().to_vec())
        .collect();
    if let Some(required) = required_alpn {
        if alpn.is_empty() {
            alpn.push(required.to_vec());
        } else if !alpn.iter().any(|value| value == required) {
            return Err("QuicAlpnUnsupported");
        }
    }
    if alpn.is_empty() {
        return Err("QuicAlpnRequired");
    }
    let crypto = crypto_context(options, alpn, pin)?;
    let mut transport = TransportConfig::default();
    transport.max_concurrent_bidi_streams(VarInt::from_u32(0));
    transport.max_concurrent_uni_streams(VarInt::from_u32(64));
    transport.stream_receive_window(VarInt::from_u32(256 * 1024));
    transport.receive_window(VarInt::from_u32(4 * 1024 * 1024));
    transport.send_window(4 * 1024 * 1024);
    transport.datagram_receive_buffer_size(Some(256 * 1024));
    transport.datagram_send_buffer_size(256 * 1024);
    transport.max_idle_timeout(Some(
        Duration::from_secs(60)
            .try_into()
            .map_err(|_| "QuicIdleTimeout")?,
    ));
    transport.keep_alive_interval(Some(Duration::from_secs(10)));
    if wrapped {
        // Obfuscation adds an outer datagram header not visible to Quinn's
        // PMTU calculation. Keep wrapped QUIC payloads at the safe minimum.
        transport.initial_mtu(1200);
        transport.mtu_discovery_config(None);
    }
    match congestion {
        "cubic" => transport
            .congestion_controller_factory(Arc::new(quinn::congestion::CubicConfig::default())),
        "new_reno" | "new-reno" | "reno" => transport
            .congestion_controller_factory(Arc::new(quinn::congestion::NewRenoConfig::default())),
        "bbr" => transport
            .congestion_controller_factory(Arc::new(quinn::congestion::BbrConfig::default())),
        _ => return Err("QuicCongestionUnsupported"),
    };
    let mut config = ClientConfig::new(crypto);
    config.transport_config(Arc::new(transport));
    Ok(config)
}

/// Keeps the UDP endpoint alive until the last stream/association is released.
/// Network migration is not exposed; reconnect creates a new validated session.
pub struct Session {
    pub connection: Connection,
    _endpoint: Endpoint,
}

pub async fn connect(
    addresses: &[SocketAddr],
    options: TlsOptions<'_>,
    required_alpn: Option<&[u8]>,
    congestion: &str,
    deadline: Instant,
) -> Result<Arc<Session>> {
    connect_inner(
        addresses,
        options,
        required_alpn,
        congestion,
        deadline,
        None,
    )
    .await
}

pub type SocketWrapper =
    dyn Fn(Arc<dyn quinn::AsyncUdpSocket>) -> Arc<dyn quinn::AsyncUdpSocket> + Send + Sync;

/// Protocol-owned wire obfuscation can wrap the actual QUIC UDP socket. The
/// wrapper is explicit, applies to both directions and cannot disable TLS.
pub async fn connect_with_socket_wrapper(
    addresses: &[SocketAddr],
    options: TlsOptions<'_>,
    required_alpn: Option<&[u8]>,
    congestion: &str,
    deadline: Instant,
    wrapper: &SocketWrapper,
) -> Result<Arc<Session>> {
    connect_inner(
        addresses,
        options,
        required_alpn,
        congestion,
        deadline,
        Some(wrapper),
    )
    .await
}

async fn connect_inner(
    addresses: &[SocketAddr],
    options: TlsOptions<'_>,
    required_alpn: Option<&[u8]>,
    congestion: &str,
    deadline: Instant,
    wrapper: Option<&SocketWrapper>,
) -> Result<Arc<Session>> {
    let config = build_client_config(options, required_alpn, congestion, wrapper.is_some())?;
    if addresses.is_empty()
        || addresses.len() > 16
        || addresses
            .iter()
            .any(|a| a.port() == 0 || a.ip().is_unspecified() || a.ip().is_multicast())
    {
        return Err("QuicServerAddress");
    }
    let mut last_error = "QuicHandshake";
    for (index, address) in addresses.iter().enumerate() {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err("QuicHandshakeTimeout");
        }
        let bind = if address.is_ipv4() {
            SocketAddr::from(([0, 0, 0, 0], 0))
        } else {
            SocketAddr::from(([0u16; 8], 0))
        };
        let socket = crate::bind_udp(bind)
            .await
            .map_err(|_| "QuicBind")?
            .into_std()
            .map_err(|_| "QuicBind")?;
        let socket = quinn::TokioRuntime
            .wrap_udp_socket(socket)
            .map_err(|_| "QuicEndpoint")?;
        let socket = if let Some(wrapper) = wrapper {
            wrapper(socket)
        } else {
            socket
        };
        let endpoint = Endpoint::new_with_abstract_socket(
            Default::default(),
            None,
            socket,
            Arc::new(quinn::TokioRuntime),
        )
        .map_err(|_| "QuicEndpoint")?;
        let connecting = endpoint
            .connect_with(config.clone(), *address, &options.tls.server_name)
            .map_err(|_| "QuicConnect")?;
        let slice = if index + 1 < addresses.len() {
            remaining.min(Duration::from_secs(3))
        } else {
            remaining
        };
        match timeout_at(Instant::now() + slice, connecting).await {
            Ok(Ok(connection)) => {
                let handshake = connection.handshake_data().ok_or("QuicHandshakeData")?;
                let handshake = handshake
                    .downcast::<quinn::crypto::rustls::HandshakeData>()
                    .map_err(|_| "QuicHandshakeData")?;
                let negotiated = handshake.protocol.as_deref().ok_or("QuicAlpnNegotiation")?;
                if required_alpn.is_some_and(|required| negotiated != required)
                    || (!options.tls.alpn.is_empty()
                        && !options
                            .tls
                            .alpn
                            .iter()
                            .any(|value| value.as_bytes() == negotiated))
                {
                    connection.close(VarInt::from_u32(1), b"ALPN mismatch");
                    return Err("QuicAlpnNegotiation");
                }
                return Ok(Arc::new(Session {
                    connection,
                    _endpoint: endpoint,
                }));
            }
            Ok(Err(_)) => last_error = "QuicTlsVerificationOrHandshake",
            Err(_) => last_error = "QuicHandshakeTimeout",
        }
    }
    Err(last_error)
}

#[derive(Clone, Copy)]
enum ShutdownFailure {
    TimedOut,
    PeerStopped,
    PeerStoppedNoError,
    ConnectionLost,
}
impl ShutdownFailure {
    fn into_io(self) -> io::Error {
        let (kind, code) = match self {
            Self::TimedOut => (io::ErrorKind::TimedOut, "QuicShutdownAckTimeout"),
            Self::PeerStopped => (io::ErrorKind::BrokenPipe, "QuicShutdownPeerStopped"),
            Self::PeerStoppedNoError => {
                (io::ErrorKind::BrokenPipe, "QuicShutdownPeerStoppedNoError")
            }
            Self::ConnectionLost => (io::ErrorKind::BrokenPipe, "QuicShutdownConnectionLost"),
        };
        io::Error::new(kind, code)
    }
}
type ShutdownResult = std::result::Result<(), ShutdownFailure>;
type ShutdownCompletion = Pin<Box<dyn Future<Output = ShutdownResult> + Send + Sync>>;

pub struct Stream {
    pub session: Arc<Session>,
    send: SendStream,
    recv: RecvStream,
    shutdown: Option<ShutdownCompletion>,
    shutdown_result: Option<ShutdownResult>,
}
impl Stream {
    pub fn new(session: Arc<Session>, send: SendStream, recv: RecvStream) -> Self {
        Self {
            session,
            send,
            recv,
            shutdown: None,
            shutdown_result: None,
        }
    }
}
impl AsyncRead for Stream {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        AsyncRead::poll_read(Pin::new(&mut self.recv), cx, buf)
    }
}
impl AsyncWrite for Stream {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        AsyncWrite::poll_write(Pin::new(&mut self.send), cx, bytes)
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        AsyncWrite::poll_flush(Pin::new(&mut self.send), cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if let Some(result) = self.shutdown_result {
            return Poll::Ready(result.map_err(ShutdownFailure::into_io));
        }
        if self.shutdown.is_none() {
            // Quinn's AsyncWrite::shutdown only queues FIN. A final owner can
            // then close the connection before queued bytes (e.g. a TLS close
            // notification) leave it. stopped() confirms acknowledged delivery
            // or reports peer rejection; neither flush nor finish does that.
            // https://docs.rs/quinn/0.11.12/quinn/struct.SendStream.html#method.stopped
            if self.send.finish().is_err() {
                self.shutdown_result = Some(Err(ShutdownFailure::ConnectionLost));
                return Poll::Ready(Err(ShutdownFailure::ConnectionLost.into_io()));
            }
            let completion = self.send.stopped();
            self.shutdown = Some(Box::pin(async move {
                match tokio::time::timeout(Duration::from_secs(5), completion).await {
                    Ok(Ok(None)) => Ok(()),
                    Ok(Ok(Some(code))) if code == VarInt::from_u32(0) => {
                        Err(ShutdownFailure::PeerStoppedNoError)
                    }
                    Ok(Ok(Some(_))) => Err(ShutdownFailure::PeerStopped),
                    Ok(Err(_)) => Err(ShutdownFailure::ConnectionLost),
                    Err(_) => Err(ShutdownFailure::TimedOut),
                }
            }));
        }
        // This future stays owned by the stream. Cancellation drops it and the
        // session normally; no detached drain task can outlive a stopped core.
        let result = ready!(
            self.shutdown
                .as_mut()
                .expect("shutdown initialized")
                .as_mut()
                .poll(cx)
        );
        self.shutdown_result = Some(result);
        self.shutdown = None;
        Poll::Ready(result.map_err(ShutdownFailure::into_io))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pins_are_exactly_sha256_hex() {
        assert_eq!(parse_pin(&"aa".repeat(32)).unwrap(), [0xaa; 32]);
        assert_eq!(parse_pin(&vec!["AB"; 32].join(":")).unwrap(), [0xab; 32]);
        for bad in [
            String::new(),
            "aa".repeat(31),
            "aa".repeat(33),
            "gg".repeat(32),
            vec!["aa"; 32].join("-"),
        ] {
            assert!(parse_pin(&bad).is_err());
        }
    }

    #[test]
    fn invalid_parameters_fail_before_socket_creation() {
        let tls = Tls {
            server_name: "test.invalid".into(),
            alpn: vec!["h3".into()],
            ca_der_base64: None,
        };
        let options = TlsOptions {
            tls: &tls,
            insecure: false,
            pin_sha256: None,
        };
        assert!(client_config(options, Some(b"h3"), "cubic").is_ok());
        assert!(client_config(options, Some(b"h2"), "cubic").is_err());
        assert!(client_config(options, Some(b"h3"), "unknown").is_err());
        assert!(
            client_config(
                TlsOptions {
                    pin_sha256: Some("bad"),
                    ..options
                },
                Some(b"h3"),
                "cubic"
            )
            .is_err()
        );
    }
}
