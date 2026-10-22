use std::{
    collections::VecDeque,
    io::{self, Cursor, Write},
    pin::Pin,
    sync::{
        Arc, Mutex,
        atomic::{AtomicUsize, Ordering},
    },
    task::{Context, Poll},
    time::Duration,
};
use swirl_protocol::vision::{
    Command, Encoder,
    record::{PlaintextChunks, TlsRecordIo},
    stream::{ReadMode, Role, Stream},
};
use swirl_transport::BoxStream;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, ReadBuf};
use tokio_rustls::{
    TlsConnector,
    rustls::{
        ClientConfig, RootCertStore, ServerConfig, ServerConnection,
        pki_types::{CertificateDer, PrivatePkcs8KeyDer, ServerName},
        version::TLS13,
    },
};

const UUID: [u8; 16] = [0x63; 16];

fn hex(value: &serde_json::Value) -> Vec<u8> {
    value
        .as_str()
        .unwrap()
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

// Reuse an existing public synthetic self-signed certificate as an explicit
// trust anchor. Ordinary rustls certificate/name, CertificateVerify and both
// Finished checks remain enabled. Every session has fresh traffic secrets;
// this in-memory regression is separate from the mature Xray peer suite.
fn configs() -> (Arc<ClientConfig>, Arc<ServerConfig>) {
    let fixture: serde_json::Value = serde_json::from_str(include_str!(
        "../../swirl-transport/tests/fixtures/reality_auth.json"
    ))
    .unwrap();
    let certificate = &fixture["certificate"];
    let der = CertificateDer::from(hex(&certificate["ordinary_self_signed_der_hex"]));
    let mut roots = RootCertStore::empty();
    roots.add(der.clone()).unwrap();
    let provider = Arc::new(tokio_rustls::rustls::crypto::ring::default_provider());
    let client = ClientConfig::builder_with_provider(provider.clone())
        .with_protocol_versions(&[&TLS13])
        .unwrap()
        .with_root_certificates(roots)
        .with_no_client_auth();
    let mut server = ServerConfig::builder_with_provider(provider)
        .with_protocol_versions(&[&TLS13])
        .unwrap()
        .with_no_client_auth()
        .with_single_cert(
            vec![der],
            PrivatePkcs8KeyDer::from(hex(&certificate["ed25519_pkcs8_der_hex"])).into(),
        )
        .unwrap();
    server.send_tls13_tickets = 0;
    (Arc::new(client), Arc::new(server))
}

struct State {
    server: ServerConnection,
    pending: VecDeque<u8>,
    eof: bool,
    read_bytes: usize,
    alert: Option<String>,
}

impl State {
    fn drain_server(&mut self) -> Vec<u8> {
        let mut wire = Vec::new();
        while self.server.wants_write() {
            self.server.write_tls(&mut wire).unwrap();
        }
        wire
    }

    fn seal(&mut self, plaintext: &[u8]) -> Vec<u8> {
        assert!(!self.server.is_handshaking());
        self.server.writer().write_all(plaintext).unwrap();
        self.drain_server()
    }
}

// A synchronous in-memory real TLS peer makes coalescing deterministic. Every
// queued ciphertext byte is available in one read, subject only to the caller's
// requested capacity. It records exactly which bytes reach the outer engine.
struct PeerIo {
    state: Arc<Mutex<State>>,
    drops: Arc<AtomicUsize>,
}

impl Drop for PeerIo {
    fn drop(&mut self) {
        self.drops.fetch_add(1, Ordering::SeqCst);
    }
}

impl AsyncRead for PeerIo {
    fn poll_read(
        self: Pin<&mut Self>,
        _cx: &mut Context<'_>,
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let mut state = self.state.lock().unwrap();
        if out.remaining() == 0 || (state.pending.is_empty() && state.eof) {
            return Poll::Ready(Ok(()));
        }
        if state.pending.is_empty() {
            return Poll::Pending;
        }
        let count = out.remaining().min(state.pending.len());
        for byte in state.pending.drain(..count) {
            out.put_slice(&[byte]);
        }
        state.read_bytes += count;
        Poll::Ready(Ok(()))
    }
}

impl AsyncWrite for PeerIo {
    fn poll_write(
        self: Pin<&mut Self>,
        _cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        let mut state = self.state.lock().unwrap();
        let count = state.server.read_tls(&mut Cursor::new(bytes))?;
        if let Err(error) = state.server.process_new_packets() {
            state.alert = Some(format!("{error:?}"));
        }
        let wire = state.drain_server();
        state.pending.extend(wire);
        Poll::Ready(Ok(count))
    }

    fn poll_flush(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Poll::Ready(Ok(()))
    }

    fn poll_shutdown(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Poll::Ready(Ok(()))
    }
}

async fn peer(
    ciphertext_boundary: bool,
    plaintext_boundary: bool,
) -> (BoxStream, Arc<Mutex<State>>, Arc<AtomicUsize>) {
    let (client_config, server_config) = configs();
    let state = Arc::new(Mutex::new(State {
        server: ServerConnection::new(server_config).unwrap(),
        pending: VecDeque::new(),
        eof: false,
        read_bytes: 0,
        alert: None,
    }));
    let drops = Arc::new(AtomicUsize::new(0));
    let io = PeerIo {
        state: state.clone(),
        drops: drops.clone(),
    };
    let io: BoxStream = if ciphertext_boundary {
        Box::new(TlsRecordIo::new(io))
    } else {
        Box::new(io)
    };
    let tls = tokio::time::timeout(
        Duration::from_secs(2),
        TlsConnector::from(client_config)
            .connect(ServerName::try_from("reality.test").unwrap(), io),
    )
    .await
    .unwrap()
    .unwrap();
    assert!(!tls.get_ref().1.is_handshaking());
    assert!(!state.lock().unwrap().server.is_handshaking());
    assert!(state.lock().unwrap().pending.is_empty());
    let tls: BoxStream = if plaintext_boundary {
        Box::new(PlaintextChunks::new(tls))
    } else {
        Box::new(tls)
    };
    (tls, state, drops)
}

async fn foreign_record() -> Vec<u8> {
    let (_tls, state, _) = peer(true, true).await;
    state.lock().unwrap().seal(b"raw inner ciphertext")
}

#[tokio::test]
async fn both_boundaries_deliver_authenticated_direct_request_before_coalesced_raw_tls() {
    let raw = foreign_record().await;
    for (ciphertext_boundary, plaintext_boundary) in
        [(false, false), (false, true), (true, false), (true, true)]
    {
        let (tls, state, drops) = peer(ciphertext_boundary, plaintext_boundary).await;
        let frame = Encoder::new(UUID)
            .frame(Command::DirectRequested, b"must not escape", &[0x72; 103])
            .unwrap();
        let (before, authenticated_length) = {
            let mut state = state.lock().unwrap();
            let authenticated = state.seal(&frame);
            let length = authenticated.len();
            assert!(length + raw.len() < 4096);
            state.pending.extend(authenticated);
            state.pending.extend(raw.iter().copied());
            (state.read_bytes, length)
        };
        let mut vision = Stream::new(tls, UUID, Role::Client);
        let mut output = [0xd3; 2048];
        let error = vision.read(&mut output).await.unwrap_err();
        assert_eq!(output, [0xd3; 2048]);
        assert_eq!(drops.load(Ordering::SeqCst), 1);
        let state = state.lock().unwrap();
        if ciphertext_boundary {
            assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
            assert_eq!(vision.read_mode(), ReadMode::DirectRequested);
        } else {
            // Exact reproduction of the original macOS/Windows failure: the
            // valid outer frame is hidden by a later wrong-key record's MAC.
            assert_eq!(error.kind(), io::ErrorKind::InvalidData);
            assert_ne!(vision.read_mode(), ReadMode::DirectRequested);
        }
        if ciphertext_boundary && plaintext_boundary {
            assert_eq!(state.read_bytes - before, authenticated_length);
            assert_eq!(state.pending.iter().copied().collect::<Vec<_>>(), raw);
            assert!(state.alert.is_none());
        } else {
            assert_eq!(state.read_bytes - before, authenticated_length + raw.len());
            assert!(state.alert.as_deref().unwrap().contains("BadRecordMac"));
        }
    }
}

#[tokio::test]
async fn tampered_outer_direct_record_remains_an_authentication_failure() {
    let (tls, state, drops) = peer(true, true).await;
    let frame = Encoder::new(UUID)
        .frame(Command::DirectRequested, b"not authenticated", &[])
        .unwrap();
    let mut wire = state.lock().unwrap().seal(&frame);
    *wire.last_mut().unwrap() ^= 1;
    state.lock().unwrap().pending.extend(wire);
    let mut vision = Stream::new(tls, UUID, Role::Client);
    let mut output = [0xa4; 128];
    assert_eq!(
        vision.read(&mut output).await.unwrap_err().kind(),
        io::ErrorKind::InvalidData
    );
    assert_ne!(vision.read_mode(), ReadMode::DirectRequested);
    assert_eq!(output, [0xa4; 128]);
    assert_eq!(drops.load(Ordering::SeqCst), 1);
}

#[tokio::test]
async fn real_tls_close_notify_is_required_even_at_record_boundaries() {
    for close in ["notify", "tcp_eof", "partial_header", "partial_body"] {
        let (tls, state, drops) = peer(true, true).await;
        let frame = Encoder::new(UUID)
            .frame(Command::EndPadding, b"authenticated payload", &[])
            .unwrap();
        {
            let mut state = state.lock().unwrap();
            let mut wire = state.seal(&frame);
            state.server.send_close_notify();
            let notify = state.drain_server();
            match close {
                "notify" => wire.extend_from_slice(&notify),
                "tcp_eof" => (),
                "partial_header" => wire.extend_from_slice(&notify[..3]),
                "partial_body" => wire.extend_from_slice(&notify[..notify.len() - 1]),
                _ => unreachable!(),
            }
            state.pending.extend(wire);
            state.eof = true;
        }
        let mut vision = Stream::new(tls, UUID, Role::Client);
        let mut output = Vec::new();
        let result = vision.read_to_end(&mut output).await;
        assert_eq!(output, b"authenticated payload");
        if close == "notify" {
            result.unwrap();
            assert_eq!(vision.read_mode(), ReadMode::Closed);
        } else {
            assert_eq!(result.unwrap_err().kind(), io::ErrorKind::UnexpectedEof);
        }
        drop(vision);
        assert_eq!(drops.load(Ordering::SeqCst), 1);
    }
}

#[tokio::test(start_paused = true)]
async fn partial_header_survives_cancelled_read_and_write_half_close() {
    let (socket, mut peer) = tokio::io::duplex(64);
    let mut boundary = TlsRecordIo::new(socket);
    peer.write_all(&[23, 3]).await.unwrap();
    let mut header = [0; 5];
    boundary.read_exact(&mut header[..2]).await.unwrap();
    assert_eq!(header[..2], [23, 3]);
    let mut byte = [0];
    assert!(
        tokio::time::timeout(Duration::from_millis(10), boundary.read(&mut byte))
            .await
            .is_err()
    );
    boundary.write_all(b"upload").await.unwrap();
    boundary.shutdown().await.unwrap();
    let mut upload = Vec::new();
    peer.read_to_end(&mut upload).await.unwrap();
    assert_eq!(upload, b"upload");
    peer.write_all(&[3, 0, 3, 0x41, 0x42, 0x43]).await.unwrap();
    peer.shutdown().await.unwrap();
    let mut tail = Vec::new();
    boundary.read_to_end(&mut tail).await.unwrap();
    assert_eq!(tail, [3, 0, 3, 0x41, 0x42, 0x43]);
}

#[tokio::test]
async fn oversized_record_is_rejected_without_reading_its_body() {
    let (tls, state, drops) = peer(true, true).await;
    let body = [0xb7; 17];
    let mut wire = vec![23, 3, 3, 0xff, 0xff];
    wire.extend_from_slice(&body);
    let before = {
        let mut state = state.lock().unwrap();
        state.pending.extend(wire);
        state.read_bytes
    };
    let mut vision = Stream::new(tls, UUID, Role::Client);
    let mut output = Vec::new();
    assert_eq!(
        vision.read_to_end(&mut output).await.unwrap_err().kind(),
        io::ErrorKind::InvalidData
    );
    assert!(output.is_empty());
    assert_eq!(
        vision.read(&mut [0; 1]).await.unwrap_err().kind(),
        io::ErrorKind::InvalidData
    );
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    let state = state.lock().unwrap();
    assert_eq!(state.read_bytes - before, 5);
    assert_eq!(state.pending.iter().copied().collect::<Vec<_>>(), body);
}
