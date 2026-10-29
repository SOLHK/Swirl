use super::*;
use ring::{aead, hkdf, hmac};
use std::{collections::BTreeMap, sync::Arc, time::Duration};
use tokio::io::{AsyncReadExt, AsyncWriteExt, DuplexStream};
use tokio_rustls::{
    TlsAcceptor,
    rustls::{
        ServerConfig,
        pki_types::{CertificateDer, PrivatePkcs8KeyDer},
    },
};
use x25519_dalek::{PublicKey, StaticSecret};

const TEST_TIME: u32 = 1_792_353_600;

fn parameters() -> ClientParameters {
    ClientParameters::new(
        "reality.test",
        *PublicKey::from(&StaticSecret::from([0x42; 32])).as_bytes(),
        &[0xab, 0xcd],
        [26, 10, 19],
    )
    .unwrap()
}

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

fn word(bytes: &[u8]) -> usize {
    usize::from(u16::from_be_bytes(bytes[..2].try_into().unwrap()))
}

// This regression peer derives and verifies authentication from the actual
// wire ClientHello, independently of the client's private keys/verifier. It is
// a real rustls TLS peer, separate from the mandatory official Xray integration.
fn server_config(hello: &[u8], corrupt_certificate: bool) -> Arc<ServerConfig> {
    let mut at = 71;
    at += 2 + word(&hello[at..]);
    at += 1 + usize::from(hello[at]);
    let end = at + 2 + word(&hello[at..]);
    at += 2;
    let mut extensions = BTreeMap::new();
    while at < end {
        let kind = word(&hello[at..]);
        let count = word(&hello[at + 2..]);
        extensions.insert(kind, &hello[at + 4..at + 4 + count]);
        at += 4 + count;
    }
    let shares = extensions[&51];
    assert_eq!(word(&shares[2..]), 0x11ec);
    let client_key: [u8; 32] = shares[6 + 1184..6 + 1216].try_into().unwrap();
    let shared = StaticSecret::from([0x42; 32]).diffie_hellman(&PublicKey::from(client_key));
    let prk = hkdf::Salt::new(hkdf::HKDF_SHA256, &hello[6..26]).extract(shared.as_bytes());
    let mut key = [0; 32];
    prk.expand(&[b"REALITY"], hkdf::HKDF_SHA256)
        .unwrap()
        .fill(&mut key)
        .unwrap();
    let mut aad = hello.to_vec();
    aad[39..71].fill(0);
    let mut sid = hello[39..71].to_vec();
    let cipher = aead::LessSafeKey::new(aead::UnboundKey::new(&aead::AES_256_GCM, &key).unwrap());
    let plain = cipher
        .open_in_place(
            aead::Nonce::assume_unique_for_key(hello[26..38].try_into().unwrap()),
            aead::Aad::from(&aad),
            &mut sid,
        )
        .unwrap();
    assert_eq!(&plain[..4], &[26, 10, 19, 0]);
    assert_eq!(&plain[4..8], TEST_TIME.to_be_bytes());
    assert_eq!(&plain[8..], &[0xab, 0xcd, 0, 0, 0, 0, 0, 0]);
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("../../tests/fixtures/reality_auth.json")).unwrap();
    let certificate = &fixture["certificate"];
    let mut der = hex(&certificate["der_hex"]);
    let mac = hmac::sign(
        &hmac::Key::new(hmac::HMAC_SHA512, &key),
        &hex(&certificate["ed25519_public_key_hex"]),
    );
    let end = der.len();
    der[end - 64..].copy_from_slice(mac.as_ref());
    if corrupt_certificate {
        der[end - 1] ^= 1;
    }
    let mut provider = tokio_rustls::rustls::crypto::ring::default_provider();
    provider.kx_groups = vec![tokio_rustls::rustls::crypto::ring::kx_group::X25519];
    let mut config = ServerConfig::builder_with_provider(Arc::new(provider))
        .with_protocol_versions(&[&tokio_rustls::rustls::version::TLS13])
        .unwrap()
        .with_no_client_auth()
        .with_single_cert(
            vec![CertificateDer::from(der)],
            PrivatePkcs8KeyDer::from(hex(&certificate["ed25519_pkcs8_der_hex"])).into(),
        )
        .unwrap();
    config.send_tls13_tickets = 0;
    Arc::new(config)
}

struct Chunks<S> {
    io: S,
    limit: usize,
    prefix: std::io::Cursor<Vec<u8>>,
}

impl<S: AsyncRead + Unpin> AsyncRead for Chunks<S> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        let count = out.remaining().min(this.limit);
        let mut part = ReadBuf::new(out.initialize_unfilled_to(count));
        let prefix = this.prefix.get_ref().len() - this.prefix.position() as usize;
        if prefix != 0 {
            let at = this.prefix.position() as usize;
            let count = count.min(prefix);
            part.put_slice(&this.prefix.get_ref()[at..at + count]);
            this.prefix.set_position((at + count) as u64);
        } else {
            ready!(Pin::new(&mut this.io).poll_read(cx, &mut part))?;
        }
        let count = part.filled().len();
        out.advance(count);
        Poll::Ready(Ok(()))
    }
}

impl<S: AsyncWrite + Unpin> AsyncWrite for Chunks<S> {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        let count = bytes.len().min(self.limit);
        Pin::new(&mut self.io).poll_write(cx, &bytes[..count])
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.io).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.io).poll_shutdown(cx)
    }
}

async fn peer(
    mut io: DuplexStream,
    limit: usize,
    corrupt: bool,
) -> io::Result<tokio_rustls::server::TlsStream<Chunks<DuplexStream>>> {
    let mut header = [0; 5];
    io.read_exact(&mut header).await?;
    let mut body = vec![0; word(&header[3..])];
    io.read_exact(&mut body).await?;
    let config = server_config(&body, corrupt);
    TlsAcceptor::from(config)
        .accept(Chunks {
            io,
            limit,
            prefix: std::io::Cursor::new([header.as_slice(), &body].concat()),
        })
        .await
}

#[tokio::test]
async fn tiny_partial_io_and_backpressure_preserve_data_and_authenticated_half_close() {
    for limit in [1, 127, 4096] {
        // The one-byte case performs over 500,000 partial-I/O operations. Allow
        // loaded CI scheduling without changing the payload, I/O caps or runtime
        // deadlines; this watchdog still bounds a stalled test.
        tokio::time::timeout(Duration::from_secs(30), async move {
            let (client_io, peer_io) = tokio::io::duplex(128);
            let payload: Vec<u8> = (0..256 * 1024).map(|i| (i % 251) as u8).collect();
            let expected = payload.clone();
            let worker = tokio::spawn(async move {
                let mut peer = peer(peer_io, limit, false).await.unwrap();
                let mut request = Vec::new();
                peer.read_to_end(&mut request).await.unwrap();
                assert_eq!(request, expected);
                peer.write_all(&request).await.unwrap();
                peer.write_all(b"after upload half-close").await.unwrap();
                peer.shutdown().await.unwrap();
            });
            let mut client = connect(
                Chunks {
                    io: client_io,
                    limit,
                    prefix: std::io::Cursor::new(Vec::new()),
                },
                &parameters(),
                TEST_TIME,
                &[],
            )
            .await
            .unwrap();
            assert!(client.is_authenticated());
            assert!(!client.raw_read_enabled() && !client.raw_write_enabled());
            client.write_all(&payload).await.unwrap();
            client.shutdown().await.unwrap();
            let mut response = Vec::new();
            client.read_to_end(&mut response).await.unwrap();
            assert_eq!(
                response,
                [payload.as_slice(), b"after upload half-close"].concat()
            );
            assert!(client.tls().peer_has_closed());
            assert_eq!(
                client.write(b"late").await.unwrap_err().kind(),
                io::ErrorKind::BrokenPipe
            );
            worker.await.unwrap();
        })
        .await
        .unwrap();
    }
}

#[tokio::test]
async fn failed_authentication_releases_transport_and_returns_no_stream() {
    let (client_io, peer_io) = tokio::io::duplex(128);
    let worker = tokio::spawn(async move {
        assert!(peer(peer_io, 31, true).await.is_err());
    });
    let error = connect(client_io, &parameters(), TEST_TIME, &[])
        .await
        .unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    tokio::time::timeout(Duration::from_secs(1), worker)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn cancellation_releases_pending_handshake_without_detached_tasks() {
    let (client_io, mut peer_io) = tokio::io::duplex(32);
    let (hello_seen, hello_ready) = tokio::sync::oneshot::channel();
    let worker = tokio::spawn(async move {
        let mut header = [0; 5];
        peer_io.read_exact(&mut header).await.unwrap();
        let mut hello = vec![0; word(&header[3..])];
        peer_io.read_exact(&mut hello).await.unwrap();
        hello_seen.send(()).unwrap();
        let mut observed = Vec::new();
        peer_io.read_to_end(&mut observed).await.unwrap();
        assert!(observed.is_empty());
    });
    let parameters = parameters();
    let mut handshake = Box::pin(connect(client_io, &parameters, TEST_TIME, &[]));
    tokio::select! {
        result = &mut handshake => panic!("stalled peer unexpectedly completed: {result:?}"),
        result = hello_ready => result.unwrap(),
    }
    assert!(
        tokio::time::timeout(Duration::from_millis(20), handshake)
            .await
            .is_err()
    );
    tokio::time::timeout(Duration::from_secs(1), worker)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn raw_handoff_preserves_tls_tail_and_raw_suffix_without_outer_close_alert() {
    let (client_io, peer_io) = tokio::io::duplex(128);
    let worker = tokio::spawn(async move {
        let mut tls = peer(peer_io, 7, false).await.unwrap();
        tls.write_all(b"Dauthenticated tail").await.unwrap();
        tls.flush().await.unwrap();
        let (mut raw, mut tls) = tls.into_inner();
        // The peer must also stop exactly at its framed-to-raw boundary. A
        // stock tokio-rustls read may prefetch the subsequent raw upload into
        // its TLS deframer, so consume precisely this final encrypted record.
        let mut record = vec![0; 5];
        raw.read_exact(&mut record).await.unwrap();
        let length = word(&record[3..]);
        record.resize(5 + length, 0);
        raw.read_exact(&mut record[5..]).await.unwrap();
        tls.read_tls(&mut std::io::Cursor::new(record)).unwrap();
        tls.process_new_packets().unwrap();
        let mut framed_upload = [0; 1];
        std::io::Read::read_exact(&mut tls.reader(), &mut framed_upload).unwrap();
        assert_eq!(framed_upload, [b'U']);
        raw.write_all(b"raw suffix").await.unwrap();
        raw.shutdown().await.unwrap();
        let mut received = Vec::new();
        raw.read_to_end(&mut received).await.unwrap();
        // Any leaked outer close_notify or reordered framed ciphertext fails.
        assert_eq!(received, b"direct upload");
    });
    let mut client = connect(client_io, &parameters(), TEST_TIME, &[])
        .await
        .unwrap();
    let mut command = [0; 1];
    client.read_exact(&mut command).await.unwrap();
    assert_eq!(command, [b'D']);
    let remaining = client.enable_raw_read().unwrap();
    assert_eq!(remaining, b"authenticated tail");
    // Leave this TLS record queued: switching must flush it before raw upload.
    client.write_all(b"U").await.unwrap();
    poll_fn(|cx| client.poll_enable_raw_write(cx))
        .await
        .unwrap();
    client.write_all(b"direct upload").await.unwrap();
    client.shutdown().await.unwrap();
    let mut received = Vec::new();
    client.read_to_end(&mut received).await.unwrap();
    assert_eq!(received, b"raw suffix");
    assert!(client.raw_read_enabled() && client.raw_write_enabled());
    worker.await.unwrap();
}

#[tokio::test]
async fn downlink_raw_transition_remains_available_after_upload_half_close() {
    let (client_io, peer_io) = tokio::io::duplex(128);
    let worker = tokio::spawn(async move {
        let mut tls = peer(peer_io, 7, false).await.unwrap();
        let mut request = Vec::new();
        tls.read_to_end(&mut request).await.unwrap();
        assert_eq!(request, b"upload");
        tls.write_all(b"Dauthenticated response tail")
            .await
            .unwrap();
        tls.flush().await.unwrap();
        let (mut raw, _tls) = tls.into_inner();
        raw.write_all(b"raw response after upload EOF")
            .await
            .unwrap();
        raw.shutdown().await.unwrap();
    });
    let mut client = connect(client_io, &parameters(), TEST_TIME, &[])
        .await
        .unwrap();
    client.write_all(b"upload").await.unwrap();
    client.shutdown().await.unwrap();
    let mut command = [0; 1];
    client.read_exact(&mut command).await.unwrap();
    assert_eq!(command, [b'D']);
    assert_eq!(
        client.enable_raw_read().unwrap(),
        b"authenticated response tail"
    );
    let mut response = Vec::new();
    client.read_to_end(&mut response).await.unwrap();
    assert_eq!(response, b"raw response after upload EOF");
    worker.await.unwrap();
}

#[tokio::test]
async fn cancelled_partial_record_cannot_be_reinterpreted_as_raw() {
    let (client_io, peer_io) = tokio::io::duplex(128);
    let (fragment_sent, fragment_ready) = tokio::sync::oneshot::channel();
    let worker = tokio::spawn(async move {
        let tls = peer(peer_io, 71, false).await.unwrap();
        let (mut raw, _tls) = tls.into_inner();
        raw.write_all(&[23, 3, 3, 0, 10, 1, 2, 3, 4]).await.unwrap();
        fragment_sent.send(()).unwrap();
        let mut pending = Vec::new();
        raw.read_to_end(&mut pending).await.unwrap();
    });
    let mut client = connect(client_io, &parameters(), TEST_TIME, &[])
        .await
        .unwrap();
    fragment_ready.await.unwrap();
    let mut out = [0; 1];
    assert!(
        tokio::time::timeout(Duration::from_millis(20), client.read(&mut out))
            .await
            .is_err()
    );
    assert_eq!(
        client.enable_raw_read().unwrap_err().to_string(),
        "RealityRawReadBoundary"
    );
    assert!(!client.raw_read_enabled());
    assert!(client.write(b"must not escape").await.is_err());
    drop(client);
    tokio::time::timeout(Duration::from_secs(1), worker)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn bare_outer_eof_is_not_a_tls_close() {
    let (client_io, peer_io) = tokio::io::duplex(128);
    let worker = tokio::spawn(async move {
        let mut peer = peer(peer_io, 71, false).await.unwrap();
        peer.write_all(b"complete data").await.unwrap();
        peer.flush().await.unwrap();
        // Deliberately drop the outer socket without its authenticated alert.
    });
    let mut client = connect(client_io, &parameters(), TEST_TIME, &[])
        .await
        .unwrap();
    let mut received = Vec::new();
    let error = client.read_to_end(&mut received).await.unwrap_err();
    assert_eq!(received, b"complete data");
    assert_eq!(error.kind(), io::ErrorKind::UnexpectedEof);
    assert!(!client.tls().peer_has_closed());
    assert!(client.write(b"must not escape").await.is_err());
    worker.await.unwrap();
}
