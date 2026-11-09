//! Owned-loopback Snell v4 interoperability client. The independent server is
//! test infrastructure only; all client framing and sockets are native Swirl.
use serde_json::json;
use std::{net::Ipv4Addr, time::Duration};
use swirl_protocol::Target;
use swirl_subscription::{Outbound, Snell};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, UdpSocket},
};

const PSK: &str = "swirl-synthetic-peer-psk-2026";

async fn verify(port: u16) -> serde_json::Value {
    let resolver = swirl_dns::Resolver::default();
    let config = Snell {
        host: Ipv4Addr::LOCALHOST.to_string(),
        port,
        psk: PSK.into(),
        version: 4,
        udp: true,
    };
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).await.unwrap();
    let address = listener.local_addr().unwrap();
    let bytes: Vec<u8> = (0..37000).map(|i| (i * 31 + 7) as u8).collect();
    let expected = bytes.clone();
    let origin = tokio::spawn(async move {
        let (mut stream, _) = listener.accept().await.unwrap();
        let mut received = vec![0; expected.len()];
        stream.read_exact(&mut received).await.unwrap();
        assert_eq!(received, expected);
        for block in received.chunks(53) {
            stream.write_all(block).await.unwrap();
        }
        stream.shutdown().await.unwrap();
    });
    let target = Target {
        host: address.ip().to_string(),
        port: address.port(),
    };
    // Exercise the same validated native outbound entry point as the runtime.
    let mut stream = swirl_protocol::connect(
        &Outbound::Snell(config.clone()),
        &target,
        &resolver,
        Duration::from_secs(3),
    )
    .await
    .unwrap();
    stream.write_all(&bytes).await.unwrap();
    stream.flush().await.unwrap();
    let mut received = vec![0; bytes.len()];
    stream.read_exact(&mut received).await.unwrap();
    assert_eq!(received, bytes);
    stream.shutdown().await.unwrap();
    assert_eq!(stream.read(&mut [0]).await.unwrap(), 0);
    origin.await.unwrap();

    let forbidden = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).await.unwrap();
    let target = Target {
        host: Ipv4Addr::LOCALHOST.to_string(),
        port: forbidden.local_addr().unwrap().port(),
    };
    let mut wrong = config.clone();
    wrong.psk = "wrong-synthetic-key".into();
    let mut bad = swirl_protocol::connect(
        &Outbound::Snell(wrong),
        &target,
        &resolver,
        Duration::from_secs(3),
    )
    .await
    .unwrap();
    // The encrypted CONNECT already names the forbidden origin. Do not add
    // a raced write after a correctly rejected authentication handshake.
    let mut byte = [0];
    let (rejection, connection) = tokio::join!(
        tokio::time::timeout(Duration::from_secs(2), bad.read(&mut byte)),
        tokio::time::timeout(Duration::from_secs(2), forbidden.accept())
    );
    assert!(
        connection.is_err(),
        "wrong PSK reached the application origin"
    );
    let rejection = match rejection {
        Ok(Ok(0)) => "peer_closed",
        Ok(Err(_)) => "peer_rejected",
        Err(_) => "no_plaintext_before_deadline",
        Ok(Ok(_)) => panic!("wrong PSK exposed application bytes"),
    };
    drop(bad);

    let origin = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).await.unwrap();
    let address = origin.local_addr().unwrap();
    let echo = tokio::spawn(async move {
        for _ in 0..3 {
            let mut data = vec![0; 65535];
            let (count, peer) = origin.recv_from(&mut data).await.unwrap();
            origin.send_to(&data[..count], peer).await.unwrap();
        }
    });
    let mut udp =
        swirl_protocol::snell::UdpAssociation::connect(&config, &resolver, Duration::from_secs(3))
            .await
            .unwrap();
    let target = Target {
        host: address.ip().to_string(),
        port: address.port(),
    };
    for length in [0, 1200, 16000] {
        let data = vec![61; length];
        udp.send(&target, &data).await.unwrap();
        let (reply, received) = udp.recv().await.unwrap();
        assert_eq!(reply.host, target.host);
        assert_eq!(reply.port, target.port);
        assert_eq!(data, received);
    }
    echo.await.unwrap();
    assert_eq!(
        udp.send(&target, &vec![0; 16383]).await.unwrap_err(),
        "SnellUdpPayloadTooLarge"
    );
    json!({"success": true, "native_tcp_entry": true, "tcp_bytes_each_direction": 37000, "clean_tcp_eof": true,
        "udp_datagrams": [0, 1200, 16000], "oversized_udp_rejected": true,
        "wrong_psk_origin_connections": 0, "wrong_psk_outcome": rejection,
        "public_network_tested": false, "qt_product_acceptance": false})
}

#[tokio::main]
async fn main() {
    let port: u16 = std::env::args()
        .nth(1)
        .expect("loopback server port")
        .parse()
        .unwrap();
    assert_ne!(port, 0);
    let result = tokio::time::timeout(Duration::from_secs(15), verify(port))
        .await
        .unwrap();
    println!("{result}");
}
