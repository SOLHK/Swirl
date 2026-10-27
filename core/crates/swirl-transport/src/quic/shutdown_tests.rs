//! Real QUIC delivery and STOP_SENDING checks, with no sleeps or external peers.
use super::*;
use std::future::poll_fn;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::time::timeout;
use tokio_rustls::rustls::pki_types::PrivatePkcs8KeyDer;

const LIMIT: Duration = Duration::from_secs(5);

async fn peers() -> (Arc<Session>, Connection, Endpoint) {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("../../tests/fixtures/reality_auth.json")).unwrap();
    let decode = |name: &str| {
        fixture["certificate"][name]
            .as_str()
            .unwrap()
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
            .collect::<Vec<_>>()
    };
    let certificate = decode("ordinary_self_signed_der_hex");
    let mut tls = rustls::ServerConfig::builder_with_provider(Arc::new(
        rustls::crypto::ring::default_provider(),
    ))
    .with_protocol_versions(&[&rustls::version::TLS13])
    .unwrap()
    .with_no_client_auth()
    .with_single_cert(
        vec![CertificateDer::from(certificate.clone())],
        PrivatePkcs8KeyDer::from(decode("ed25519_pkcs8_der_hex")).into(),
    )
    .unwrap();
    tls.alpn_protocols = vec![b"h3".to_vec()];
    let config = quinn::ServerConfig::with_crypto(Arc::new(
        quinn::crypto::rustls::QuicServerConfig::try_from(tls).unwrap(),
    ));
    let endpoint = Endpoint::server(config, "127.0.0.1:0".parse().unwrap()).unwrap();
    let addresses = [endpoint.local_addr().unwrap()];
    let tls = Tls {
        server_name: "reality.test".into(),
        alpn: vec!["h3".into()],
        ca_der_base64: Some(base64::engine::general_purpose::STANDARD.encode(certificate)),
    };
    let connecting = connect(
        &addresses,
        TlsOptions {
            tls: &tls,
            insecure: false,
            pin_sha256: None,
        },
        Some(b"h3"),
        "cubic",
        Instant::now() + LIMIT,
    );
    let accepting = async { endpoint.accept().await.unwrap().await.unwrap() };
    let (client, server) = timeout(LIMIT, async { tokio::join!(connecting, accepting) })
        .await
        .unwrap();
    (client.unwrap(), server, endpoint)
}

// The current-thread executor cannot drive UDP between queuing this FIN and
// its first poll. Returning Ready here would claim delivery before any ACK.
#[tokio::test]
async fn shutdown_waits_for_fin_ack_and_preserves_the_response_half() {
    let (session, server, _endpoint) = peers().await;
    let (mut send, recv) = session.connection.open_bi().await.unwrap();
    send.write_all(b"start").await.unwrap();
    let (mut response, mut request) = timeout(LIMIT, server.accept_bi()).await.unwrap().unwrap();
    let mut stream = Stream::new(session, send, recv);
    let payload = vec![0x5a; 32 * 1024];
    stream.write_all(&payload).await.unwrap();
    let pending =
        poll_fn(|cx| Poll::Ready(Pin::new(&mut stream).poll_shutdown(cx).is_pending())).await;
    assert!(pending, "queued FIN is not acknowledged delivery");
    let reading = async {
        let actual = request.read_to_end(64 * 1024).await.unwrap();
        assert_eq!(&actual[..5], b"start");
        assert_eq!(&actual[5..], payload);
        response.write_all(b"tail-after-upload-fin").await.unwrap();
        response.finish().unwrap();
    };
    let writing = async {
        stream.shutdown().await.unwrap();
        stream.shutdown().await.unwrap(); // completion is idempotent
        let mut tail = Vec::new();
        stream.read_to_end(&mut tail).await.unwrap();
        assert_eq!(tail, b"tail-after-upload-fin");
    };
    timeout(LIMIT, async { tokio::join!(reading, writing) })
        .await
        .unwrap();
}

#[tokio::test]
async fn peer_stop_is_not_reported_as_a_clean_shutdown() {
    let (session, server, _endpoint) = peers().await;
    let (mut send, recv) = session.connection.open_bi().await.unwrap();
    send.write_all(b"start").await.unwrap();
    let (_response, mut request) = timeout(LIMIT, server.accept_bi()).await.unwrap().unwrap();
    request.stop(17u32.into()).unwrap();
    assert_eq!(
        timeout(LIMIT, send.stopped()).await.unwrap().unwrap(),
        Some(17u32.into())
    );
    let mut stream = Stream::new(session, send, recv);
    assert_eq!(
        timeout(LIMIT, stream.shutdown())
            .await
            .unwrap()
            .unwrap_err()
            .kind(),
        io::ErrorKind::BrokenPipe
    );
    assert_eq!(
        stream.shutdown().await.unwrap_err().kind(),
        io::ErrorKind::BrokenPipe
    );
}

#[tokio::test]
async fn shutdown_after_complete_response_and_zero_stop_remains_an_error() {
    let (session, server, _endpoint) = peers().await;
    let (mut send, mut recv) = session.connection.open_bi().await.unwrap();
    let mut payload = (0..32 * 1024).map(|i| (i % 251) as u8).collect::<Vec<_>>();
    payload.extend_from_slice(b"final-upload-sentinel");
    send.write_all(&payload).await.unwrap();
    let (mut response, mut request) = timeout(LIMIT, server.accept_bi()).await.unwrap().unwrap();
    let mut actual = vec![0; payload.len()];
    timeout(LIMIT, request.read_exact(&mut actual))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        actual, payload,
        "the peer received every byte and the final sentinel"
    );

    const RESPONSE: &[u8] = b"complete-response-with-final-sentinel";
    response.write_all(RESPONSE).await.unwrap();
    response.finish().unwrap();
    assert_eq!(
        timeout(LIMIT, recv.read_to_end(64 * 1024))
            .await
            .unwrap()
            .unwrap(),
        RESPONSE,
        "the client received the entire response and FIN before STOP_SENDING"
    );

    // The peer's application has consumed the upload, but STOP_SENDING(0)
    // still does not acknowledge the client's as-yet unqueued FIN. Observe
    // STOP before wrapping the stream so this ordering never depends on UDP timing.
    request.stop(0u32.into()).unwrap();
    assert_eq!(
        timeout(LIMIT, send.stopped()).await.unwrap().unwrap(),
        Some(0u32.into())
    );
    let mut stream = Stream::new(session, send, recv);
    let error = timeout(LIMIT, stream.shutdown())
        .await
        .unwrap()
        .unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::BrokenPipe);
    assert_eq!(error.to_string(), "QuicShutdownPeerStoppedNoError");
    let repeated = stream.shutdown().await.unwrap_err();
    assert_eq!(repeated.kind(), io::ErrorKind::BrokenPipe);
    assert_eq!(repeated.to_string(), "QuicShutdownPeerStoppedNoError");
}

#[tokio::test]
async fn shutdown_before_response_completion_and_zero_stop_remains_an_error() {
    let (session, server, _endpoint) = peers().await;
    let (mut send, mut recv) = session.connection.open_bi().await.unwrap();
    send.write_all(b"request-with-final-sentinel")
        .await
        .unwrap();
    let (mut response, mut request) = timeout(LIMIT, server.accept_bi()).await.unwrap().unwrap();
    const PREFIX: &[u8] = b"incomplete-response-prefix";
    response.write_all(PREFIX).await.unwrap();
    let mut actual = vec![0; PREFIX.len()];
    timeout(LIMIT, recv.read_exact(&mut actual))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(actual, PREFIX);
    let mut tail = [0; 1];
    let pending = poll_fn(|cx| {
        let mut buffer = ReadBuf::new(&mut tail);
        Poll::Ready(Pin::new(&mut recv).poll_read(cx, &mut buffer).is_pending())
    })
    .await;
    assert!(pending, "the response has neither a tail byte nor FIN");

    request.stop(0u32.into()).unwrap();
    assert_eq!(
        timeout(LIMIT, send.stopped()).await.unwrap().unwrap(),
        Some(0u32.into())
    );
    let mut stream = Stream::new(session, send, recv);
    let error = timeout(LIMIT, stream.shutdown())
        .await
        .unwrap()
        .unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::BrokenPipe);
    assert_eq!(error.to_string(), "QuicShutdownPeerStoppedNoError");
}
