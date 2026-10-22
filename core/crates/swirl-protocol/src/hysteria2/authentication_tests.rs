//! Real QUIC/H3 regressions for a peer that replies before request completion.
//!
//! This controlled peer complements the pinned official-server suite. Awaiting
//! an actually received STOP_SENDING frame makes finish() deterministic without
//! a fixed sleep, production hooks, or any fabricated transport error.

use super::{Session, Task, authentication_finish};
use base64::Engine;
use bytes::Bytes;
use h3::error::{Code, StreamError};
use std::{future::poll_fn, sync::Arc, time::Duration};
use swirl_dns::Resolver;
use swirl_subscription::Hysteria2;
use tokio::time::{Instant, timeout};
use tokio_rustls::rustls::{
    ClientConfig, RootCertStore, ServerConfig,
    pki_types::{CertificateDer, PrivatePkcs8KeyDer},
    version::TLS13,
};

const PASSWORD: &str = "public-authentication-regression-password";
const SERVER_NAME: &str = "reality.test";
const BUDGET: Duration = Duration::from_secs(10);

struct Peer {
    server: quinn::Endpoint,
    client: quinn::Endpoint,
    certificate: Vec<u8>,
}

impl Peer {
    fn new() -> Self {
        // Reuse an explicitly trusted public synthetic fixture. Certificate,
        // server-name, CertificateVerify, and Finished checks remain enabled.
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../swirl-transport/tests/fixtures/reality_auth.json"
        ))
        .unwrap();
        let hex = |key: &str| {
            fixture["certificate"][key]
                .as_str()
                .unwrap()
                .as_bytes()
                .as_chunks::<2>()
                .0
                .iter()
                .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
                .collect::<Vec<_>>()
        };
        let certificate = hex("ordinary_self_signed_der_hex");
        let der = CertificateDer::from(certificate.clone());
        let provider = Arc::new(tokio_rustls::rustls::crypto::ring::default_provider());
        let mut roots = RootCertStore::empty();
        roots.add(der.clone()).unwrap();
        let mut client_tls = ClientConfig::builder_with_provider(provider.clone())
            .with_protocol_versions(&[&TLS13])
            .unwrap()
            .with_root_certificates(roots)
            .with_no_client_auth();
        client_tls.alpn_protocols = vec![b"h3".to_vec()];
        let mut server_tls = ServerConfig::builder_with_provider(provider)
            .with_protocol_versions(&[&TLS13])
            .unwrap()
            .with_no_client_auth()
            .with_single_cert(
                vec![der],
                PrivatePkcs8KeyDer::from(hex("ed25519_pkcs8_der_hex")).into(),
            )
            .unwrap();
        server_tls.alpn_protocols = vec![b"h3".to_vec()];
        let server_config = quinn::ServerConfig::with_crypto(Arc::new(
            quinn::crypto::rustls::QuicServerConfig::try_from(server_tls).unwrap(),
        ));
        let server =
            quinn::Endpoint::server(server_config, "127.0.0.1:0".parse().unwrap()).unwrap();
        let mut client = quinn::Endpoint::client("127.0.0.1:0".parse().unwrap()).unwrap();
        client.set_default_client_config(quinn::ClientConfig::new(Arc::new(
            quinn::crypto::rustls::QuicClientConfig::try_from(client_tls).unwrap(),
        )));
        Self {
            server,
            client,
            certificate,
        }
    }

    async fn serve_authentication(&self, stop_code: Code) {
        let connection = self.server.accept().await.unwrap().await.unwrap();
        let mut driver =
            h3::server::Connection::<_, Bytes>::new(h3_quinn::Connection::new(connection.clone()))
                .await
                .unwrap();
        let (request, mut stream) = driver
            .accept()
            .await
            .unwrap()
            .unwrap()
            .resolve_request()
            .await
            .unwrap();
        assert_eq!(request.method(), http::Method::POST);
        assert_eq!(request.uri().path(), "/auth");
        let accepted = request.headers().get("hysteria-auth").unwrap() == PASSWORD;
        let mut response = http::Response::builder().status(if accepted { 233 } else { 404 });
        if accepted {
            response = response
                .header("hysteria-udp", "true")
                .header("hysteria-cc-rx", "auto");
        }
        stream
            .send_response(response.body(()).unwrap())
            .await
            .unwrap();
        // Like the reference peer, decide from headers and stop reading the
        // request without requiring any request body.
        stream.stop_sending(stop_code);
        stream.finish().await.unwrap();
        // Keep both H3 owners alive until the client has checked its result.
        let _ = connection.closed().await;
        drop(stream);
        drop(driver);
    }

    async fn close(&self) {
        self.client
            .close(Code::H3_NO_ERROR.value().try_into().unwrap(), b"");
        self.server
            .close(Code::H3_NO_ERROR.value().try_into().unwrap(), b"");
        tokio::join!(self.client.wait_idle(), self.server.wait_idle());
    }
}

async fn finish_case(
    stop_code: Code,
    password: &str,
    expected_status: u16,
    expected_finish: super::Result<()>,
) {
    let peer = Peer::new();
    let client = async {
        let connection = peer
            .client
            .connect(peer.server.local_addr().unwrap(), SERVER_NAME)
            .unwrap()
            .await
            .unwrap();
        let (mut connection_driver, mut requester) = h3::client::builder()
            .send_grease(true)
            .build::<_, _, Bytes>(h3_quinn::Connection::new(connection.clone()))
            .await
            .unwrap();
        let mut driver = Task(tokio::spawn(async move {
            let _ = poll_fn(|context| connection_driver.poll_close(context)).await;
        }));
        let request = http::Request::builder()
            .method(http::Method::POST)
            .uri("https://hysteria/auth")
            .header("hysteria-auth", password)
            .body(())
            .unwrap();
        let mut stream = requester.send_request(request).await.unwrap();

        // Wait for Quinn to receive the real STOP_SENDING frame. Each yield
        // lets the connection driver run; the enclosing 10-second timeout also
        // bounds this barrier. Keep the auth request header-only so finish()
        // itself performs the first write after the peer stops the direction.
        while connection.stats().frame_rx.stop_sending == 0 {
            assert!(connection.close_reason().is_none());
            tokio::task::yield_now().await;
        }
        let finish = stream.finish().await;
        assert!(
            matches!(
                &finish,
                Err(StreamError::RemoteTerminate { code, .. }) if *code == stop_code
            ),
            "unexpected finish result: {finish:?}"
        );
        assert_eq!(authentication_finish(finish), expected_finish);

        // Even the negative-code cases leave a real response readable. Only
        // NO_ERROR may let production advance to these independent checks.
        let response = stream.recv_response().await.unwrap();
        assert_eq!(response.status().as_u16(), expected_status);
        if expected_status == 233 {
            assert_eq!(response.headers()["hysteria-udp"], "true");
            assert_eq!(response.headers()["hysteria-cc-rx"], "auto");
        }
        assert!(stream.recv_data().await.unwrap().is_none());
        connection.close(Code::H3_NO_ERROR.value().try_into().unwrap(), b"");
        drop(stream);
        drop(requester);
        driver.0.abort();
        let _ = (&mut driver.0).await;
    };
    tokio::join!(peer.serve_authentication(stop_code), client);
    peer.close().await;
}

#[tokio::test]
async fn normal_request_stop_preserves_successful_auth_response() {
    timeout(
        BUDGET,
        finish_case(Code::H3_NO_ERROR, PASSWORD, 233, Ok(())),
    )
    .await
    .expect("QUIC/H3 early-success regression exceeded its 10-second budget");
}

#[tokio::test]
async fn normal_request_stop_preserves_rejected_auth_response() {
    timeout(
        BUDGET,
        finish_case(Code::H3_NO_ERROR, "incorrect-password", 404, Ok(())),
    )
    .await
    .expect("QUIC/H3 early-rejection regression exceeded its 10-second budget");
}

#[tokio::test]
async fn abnormal_request_stop_remains_authentication_write_failure() {
    timeout(BUDGET, async {
        for code in [
            Code::H3_REQUEST_CANCELLED,
            Code::H3_REQUEST_REJECTED,
            Code::H3_INTERNAL_ERROR,
        ] {
            finish_case(code, PASSWORD, 233, Err("Hysteria2AuthenticationWrite")).await;
        }
    })
    .await
    .expect("QUIC/H3 abnormal-stop regression exceeded its 10-second budget");
}

#[tokio::test]
async fn session_rejects_404_after_peer_stops_request_normally() {
    timeout(BUDGET, async {
        let peer = Peer::new();
        let config: Hysteria2 = serde_json::from_value(serde_json::json!({
            "host": "127.0.0.1",
            "port": peer.server.local_addr().unwrap().port(),
            "password": "incorrect-password",
            "tls": {
                "server_name": SERVER_NAME,
                "alpn": ["h3"],
                "ca_der_base64": base64::engine::general_purpose::STANDARD.encode(&peer.certificate)
            }
        }))
        .unwrap();
        let client = async {
            let result =
                Session::connect(&config, &Resolver::default(), Instant::now() + BUDGET).await;
            assert_eq!(result.err(), Some("Hysteria2AuthenticationRejected"));
        };
        tokio::join!(peer.serve_authentication(Code::H3_NO_ERROR), client);
        peer.close().await;
    })
    .await
    .expect("native-session rejection regression exceeded its 10-second budget");
}
