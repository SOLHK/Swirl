//! Real QUIC pool regressions. Windows-only cases change the process-local
//! egress lease; they never install a driver or alter system routes or DNS.
use base64::Engine;
use std::{sync::Arc, time::Duration};
use swirl_dns::Resolver;
use swirl_protocol::{Target, tuic};
use swirl_subscription::{Tuic, uuid_bytes};
use swirl_transport::BoxStream;
use tokio::{io::AsyncReadExt, sync::Mutex, time::timeout};
use tokio_rustls::rustls::{
    ServerConfig,
    pki_types::{CertificateDer, PrivatePkcs8KeyDer},
    version::TLS13,
};

const BUDGET: Duration = Duration::from_secs(10);
// The guard is process-global. Keep this integration binary's real socket
// cases serialized, without touching other tests' processes or OS settings.
static TEST_GUARD: Mutex<()> = Mutex::const_new(());

struct Peer {
    endpoint: quinn::Endpoint,
    config: Tuic,
}

impl Peer {
    fn new(ipv6: bool) -> Self {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../swirl-transport/tests/fixtures/reality_auth.json"
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
        let provider = Arc::new(tokio_rustls::rustls::crypto::ring::default_provider());
        let mut tls = ServerConfig::builder_with_provider(provider)
            .with_protocol_versions(&[&TLS13])
            .unwrap()
            .with_no_client_auth()
            .with_single_cert(
                vec![CertificateDer::from(certificate.clone())],
                PrivatePkcs8KeyDer::from(hex("ed25519_pkcs8_der_hex")).into(),
            )
            .unwrap();
        tls.alpn_protocols = vec![b"h3".to_vec()];
        let server = quinn::ServerConfig::with_crypto(Arc::new(
            quinn::crypto::rustls::QuicServerConfig::try_from(tls).unwrap(),
        ));
        let bind = if ipv6 { "[::1]:0" } else { "127.0.0.1:0" };
        let endpoint = quinn::Endpoint::server(server, bind.parse().unwrap()).unwrap();
        let address = endpoint.local_addr().unwrap();
        let config = serde_json::from_value(serde_json::json!({
            "host": address.ip().to_string(), "port": address.port(),
            "uuid": "00112233-4455-6677-8899-aabbccddeeff",
            "password": "public-tuic-egress-regression",
            "tls": {"server_name": "reality.test", "alpn": ["h3"],
                    "ca_der_base64": base64::engine::general_purpose::STANDARD.encode(certificate)}
        }))
        .unwrap();
        Self { endpoint, config }
    }

    async fn accept(&self) -> quinn::Connection {
        timeout(BUDGET, async {
            self.endpoint.accept().await.unwrap().await.unwrap()
        })
        .await
        .unwrap()
    }

    async fn authenticate(&self, connection: &quinn::Connection) {
        let actual = timeout(BUDGET, async {
            connection
                .accept_uni()
                .await
                .unwrap()
                .read_to_end(51)
                .await
                .unwrap()
        })
        .await
        .unwrap();
        let id = uuid_bytes(&self.config.uuid).unwrap();
        let mut token = [0; 32];
        connection
            .export_keying_material(&mut token, &id, self.config.password.as_bytes())
            .unwrap();
        let mut expected = vec![5, 0];
        expected.extend_from_slice(&id);
        expected.extend_from_slice(&token);
        assert_eq!(actual, expected);
    }
}

async fn connect(config: &Tuic) -> Result<BoxStream, &'static str> {
    tuic::connect(
        config,
        &Target {
            host: "127.0.0.1".into(),
            port: 443,
        },
        &Resolver::default(),
        BUDGET,
    )
    .await
}

async fn confirm_stream(
    connection: &quinn::Connection,
    client: &mut BoxStream,
) -> (quinn::SendStream, quinn::RecvStream) {
    timeout(BUDGET, async {
        let (mut send, mut recv) = connection.accept_bi().await.unwrap();
        let mut request = [0; 9];
        recv.read_exact(&mut request).await.unwrap();
        assert_eq!(request, [5, 1, 1, 127, 0, 0, 1, 1, 187]);
        send.write_all(b"live").await.unwrap();
        let mut response = [0; 4];
        client.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"live");
        (send, recv)
    })
    .await
    .unwrap()
}

#[tokio::test]
async fn live_tcp_requests_reuse_one_authenticated_quic_connection() {
    let _guard = TEST_GUARD.lock().await;
    for ipv6 in [false, true] {
        let peer = Peer::new(ipv6);
        let (first, connection) = tokio::join!(connect(&peer.config), peer.accept());
        let mut first = first.unwrap();
        peer.authenticate(&connection).await;
        let _first_peer = confirm_stream(&connection, &mut first).await;

        // No second server.accept() runs: a fresh QUIC connection cannot finish.
        // Success plus a second stream on this exact connection proves a cache hit.
        let mut second = connect(&peer.config).await.unwrap();
        let _second_peer = confirm_stream(&connection, &mut second).await;
        assert!(connection.close_reason().is_none());
    }
}

#[cfg(windows)]
#[tokio::test]
async fn suspended_and_released_epochs_cannot_reuse_a_live_old_client() {
    use swirl_transport::egress::{EgressLease, EgressToken};

    let _guard = TEST_GUARD.lock().await;
    let peer = Peer::new(false);
    let (first, connection) = tokio::join!(connect(&peer.config), peer.accept());
    let mut first = first.unwrap();
    peer.authenticate(&connection).await;
    let _first_peer = confirm_stream(&connection, &mut first).await;
    let local = peer.endpoint.local_addr().unwrap();
    let external = "192.0.2.1:443".parse().unwrap();
    let unbound = EgressToken::capture(&[local]).unwrap();

    let lease = EgressLease::acquire_suspended().unwrap();
    let mut external_config = peer.config.clone();
    external_config.host = "192.0.2.1".into();
    assert_eq!(
        connect(&external_config).await.err(),
        Some("TuicEgressUnavailable")
    );
    assert!(EgressToken::capture(&[external]).is_err());
    assert!(EgressToken::capture(&[local, external]).is_err());
    assert!(EgressToken::capture(&[]).is_err());
    assert!(unbound.with_current(|| ()).is_err());
    // Explicit loopback remains allowed while suspended, but its old pooled
    // connection is not. Require an actual new handshake in the current epoch.
    let (paused, paused_connection) = tokio::join!(connect(&peer.config), peer.accept());
    let mut paused = paused.unwrap();
    peer.authenticate(&paused_connection).await;
    let _paused_peer = confirm_stream(&paused_connection, &mut paused).await;
    assert_ne!(connection.stable_id(), paused_connection.stable_id());
    // The lease never installed OS routes, so this release is already safe.
    lease.release_after_routes_restored().unwrap();
    assert_ne!(unbound, EgressToken::capture(&[local]).unwrap());

    // Hold the first client and its QUIC connection alive across the transition.
    // The new request must perform a second real QUIC handshake, not reuse it.
    let (second, next_connection) = tokio::join!(connect(&peer.config), peer.accept());
    let mut second = second.unwrap();
    peer.authenticate(&next_connection).await;
    let _second_peer = confirm_stream(&next_connection, &mut second).await;
    assert_ne!(connection.stable_id(), next_connection.stable_id());
    assert_ne!(paused_connection.stable_id(), next_connection.stable_id());
    assert!(connection.close_reason().is_none());

    let mut lease = EgressLease::acquire(Some(7), Some(11)).unwrap();
    let running = EgressToken::capture(&[external]).unwrap();
    lease.suspend().unwrap();
    assert!(EgressToken::capture(&[external]).is_err());
    lease.update(Some(7), Some(11)).unwrap();
    assert!(running.with_current(|| ()).is_err());
    assert_ne!(running, EgressToken::capture(&[external]).unwrap());
    // These are guard-only identities: no socket is opened and no OS setting
    // is queried/changed using the synthetic interface indices above.
    lease.release_after_routes_restored().unwrap();
}

#[cfg(windows)]
#[tokio::test]
async fn network_change_during_real_quic_handshake_rejects_completed_client() {
    use swirl_transport::egress::EgressLease;

    let _guard = TEST_GUARD.lock().await;
    let peer = Peer::new(false);
    let config = peer.config.clone();
    let attempted = tokio::spawn(async move { connect(&config).await });
    // Receiving Initial is an actual wire boundary. Do not let the server
    // complete TLS until after the client socket's captured epoch has changed.
    let incoming = timeout(BUDGET, peer.endpoint.accept())
        .await
        .unwrap()
        .unwrap();
    let lease = EgressLease::acquire_suspended().unwrap();
    let connection = timeout(BUDGET, incoming).await.unwrap().unwrap();
    let result = timeout(BUDGET, attempted).await.unwrap().unwrap();
    assert_eq!(result.err(), Some("TuicEgressChanged"));
    lease.release_after_routes_restored().unwrap();

    // A failed completion must not publish a reusable client into the pool.
    let (fresh, fresh_connection) = tokio::join!(connect(&peer.config), peer.accept());
    let mut fresh = fresh.unwrap();
    peer.authenticate(&fresh_connection).await;
    let _fresh_peer = confirm_stream(&fresh_connection, &mut fresh).await;
    assert_ne!(connection.stable_id(), fresh_connection.stable_id());
}
