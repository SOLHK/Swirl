use super::{MAX_PENDING_PACKETS, REASSEMBLY_TTL, UdpAssociation};
use base64::{Engine, engine::general_purpose::STANDARD};
use bytes::Bytes;
use std::{sync::Arc, time::Duration};
use swirl_dns::Resolver;
use swirl_subscription::{Tls, Tuic};
use tokio::time::{advance, pause, resume, timeout};
use tokio_rustls::rustls::{
    ServerConfig,
    pki_types::{CertificateDer, PrivatePkcs8KeyDer},
    version::TLS13,
};

const BUDGET: Duration = Duration::from_secs(10);

fn loopback_peer() -> (quinn::Endpoint, Tuic) {
    let fixture: serde_json::Value = serde_json::from_str(include_str!(
        "../../swirl-transport/tests/fixtures/reality_auth.json"
    ))
    .unwrap();
    let certificate = &fixture["certificate"];
    let hex = |name: &str| {
        certificate[name]
            .as_str()
            .unwrap()
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
            .collect::<Vec<_>>()
    };
    let der = hex("ordinary_self_signed_der_hex");
    let mut tls = ServerConfig::builder_with_provider(Arc::new(
        tokio_rustls::rustls::crypto::ring::default_provider(),
    ))
    .with_protocol_versions(&[&TLS13])
    .unwrap()
    .with_no_client_auth()
    .with_single_cert(
        vec![CertificateDer::from(der.clone())],
        PrivatePkcs8KeyDer::from(hex("ed25519_pkcs8_der_hex")).into(),
    )
    .unwrap();
    tls.alpn_protocols = vec![b"h3".to_vec()];
    let server = quinn::ServerConfig::with_crypto(Arc::new(
        quinn::crypto::rustls::QuicServerConfig::try_from(tls).unwrap(),
    ));
    let endpoint = quinn::Endpoint::server(server, "127.0.0.1:0".parse().unwrap()).unwrap();
    let config = Tuic {
        host: "127.0.0.1".into(),
        port: endpoint.local_addr().unwrap().port(),
        uuid: "00000000-0000-0000-0000-000000000001".into(),
        password: "public-tuic-native-udp-regression".into(),
        tls: Tls {
            server_name: "reality.test".into(),
            alpn: vec!["h3".into()],
            ca_der_base64: Some(STANDARD.encode(der)),
        },
        insecure: false,
        pin_sha256: None,
        udp: true,
        udp_relay_mode: "native".into(),
        congestion_control: "cubic".into(),
        heartbeat_interval_ms: 10_000,
        request_timeout_ms: 10_000,
    };
    (endpoint, config)
}

fn reply(association: u16, packet: u16, total: u8, index: u8, payload: &[u8]) -> Bytes {
    let mut wire = vec![5, 2];
    wire.extend_from_slice(&association.to_be_bytes());
    wire.extend_from_slice(&packet.to_be_bytes());
    wire.extend_from_slice(&[total, index]);
    wire.extend_from_slice(&u16::try_from(payload.len()).unwrap().to_be_bytes());
    if index == 0 {
        wire.extend_from_slice(&[1, 127, 0, 0, 1, 0, 53]);
    } else {
        wire.push(255);
    }
    wire.extend_from_slice(payload);
    wire.into()
}

async fn send_in_order(peer: &quinn::Connection, receiver: &quinn::Connection, packet: Bytes) {
    let before = receiver.stats().frame_rx.datagram;
    peer.send_datagram_wait(packet).await.unwrap();
    // Wait for the real QUIC driver to receive this datagram before injecting
    // the next one. The test controls order without relying on UDP delivery order.
    while receiver.stats().frame_rx.datagram == before {
        tokio::task::yield_now().await;
    }
}

#[tokio::test]
async fn native_udp_survives_discarded_fragments_and_expiry() {
    let (endpoint, config) = loopback_peer();
    let resolver = Resolver::default();
    let (association, peer) = timeout(BUDGET, async {
        tokio::join!(UdpAssociation::connect(&config, &resolver, BUDGET), async {
            endpoint.accept().await.unwrap().await.unwrap()
        },)
    })
    .await
    .expect("loopback TUIC connection must establish");
    let mut association = association.unwrap();
    let receiver = association.client.session.connection.clone();
    let id = association.association;
    let overflow_id = u16::try_from(MAX_PENDING_PACKETS).unwrap();
    let good_id = overflow_id + 1;

    timeout(BUDGET, async {
        for packet in 0..overflow_id {
            send_in_order(&peer, &receiver, reply(id, packet, 2, 0, b"lost-tail")).await;
        }
        send_in_order(
            &peer,
            &receiver,
            reply(id, overflow_id, 2, 0, b"over-limit"),
        )
        .await;
        send_in_order(&peer, &receiver, reply(id, good_id, 2, 2, b"bad-index")).await;
        send_in_order(
            &peer,
            &receiver,
            reply(id.wrapping_add(1), good_id, 1, 0, b"wrong-association"),
        )
        .await;
        send_in_order(&peer, &receiver, reply(id, good_id, 1, 0, b"whole")).await;
    })
    .await
    .expect("first burst must arrive at the real QUIC receiver");
    let (source, payload) = timeout(BUDGET, association.recv())
        .await
        .expect("valid datagram behind the dropped packets must be delivered")
        .expect("packet-local native UDP errors must preserve the association");
    assert_eq!((source.host.as_str(), source.port), ("127.0.0.1", 53));
    assert_eq!(payload, b"whole");
    assert_eq!(association.assembly.packets.len(), MAX_PENDING_PACKETS);

    // Advance the application's TTL in this current-thread test runtime.
    // The real QUIC endpoints stay connected and the next wire fragments use
    // the same association, including a packet ID previously held by the map.
    pause();
    advance(REASSEMBLY_TTL).await;
    resume();
    timeout(BUDGET, async {
        send_in_order(&peer, &receiver, reply(id, 0, 2, 1, b"-again")).await;
        send_in_order(&peer, &receiver, reply(id, 0, 2, 0, b"whole")).await;
    })
    .await
    .expect("both new fragments must arrive at the real QUIC receiver");
    let (source, payload) = timeout(BUDGET, association.recv())
        .await
        .expect("the incomplete packet must expire and free its ID")
        .unwrap();
    assert_eq!((source.host.as_str(), source.port), ("127.0.0.1", 53));
    assert_eq!(payload, b"whole-again");
    assert!(association.assembly.packets.is_empty());
    assert_eq!(association.assembly.bytes, 0);

    let mut dissociate = vec![5, 3];
    dissociate.extend_from_slice(&id.to_be_bytes());
    send_in_order(&peer, &receiver, dissociate.into()).await;
    assert_eq!(
        timeout(BUDGET, association.recv()).await.unwrap().err(),
        Some("TuicPacketCommand"),
    );

    peer.close(0u32.into(), b"");
    assert_eq!(
        timeout(BUDGET, association.recv())
            .await
            .expect("peer close must wake the receiver")
            .err(),
        Some("TuicUdpReceive"),
    );
}
