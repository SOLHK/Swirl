//! Exercise an independent upstream HTTP proxy at the CONNECT wire boundary.
use super::*;
use std::time::Duration;
use tokio::{net::TcpListener, time::timeout};

fn http_proxy(port: u16) -> Outbound {
    Outbound::HttpConnect {
        host: "127.0.0.1".into(),
        port,
        auth: None,
        tls: None,
    }
}

async fn read_request(socket: &mut TcpStream) {
    let mut request = Vec::new();
    while !request.ends_with(b"\r\n\r\n") {
        assert!(request.len() < 4096);
        request.push(socket.read_u8().await.unwrap());
    }
    assert_eq!(
        request,
        b"CONNECT target.fixture.invalid:443 HTTP/1.1\r\nHost: target.fixture.invalid:443\r\n\r\n"
    );
}

#[tokio::test]
async fn every_successful_connect_status_preserves_the_opaque_stream() {
    timeout(Duration::from_secs(5), async {
        for version in ["1.0", "1.1"] {
            for status in [200, 201, 204, 299] {
                let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
                let outbound = http_proxy(listener.local_addr().unwrap().port());
                let peer = tokio::spawn(async move {
                    let (mut socket, _) = listener.accept().await.unwrap();
                    read_request(&mut socket).await;
                    // RFC 9110 9.3.6 requires the client to ignore these
                    // framing fields on a successful CONNECT. Bytes after the
                    // header are tunnel data, even for a 204 response.
                    let mut response = format!(
                        "HTTP/{version} {status} Tunnel Ready\r\nContent-Length: 999\r\nTransfer-Encoding: chunked\r\n\r\n"
                    )
                    .into_bytes();
                    response.extend_from_slice(b"\x16\x03\x03\x00\x05hello");
                    socket.write_all(&response).await.unwrap();
                    let mut payload = Vec::new();
                    socket.read_to_end(&mut payload).await.unwrap();
                    assert_eq!(payload, b"client-payload");
                    socket.write_all(b"tail-after-half-close").await.unwrap();
                    socket.shutdown().await.unwrap();
                });
                let mut stream = connect(
                    &outbound,
                    &Target {
                        host: "target.fixture.invalid".into(),
                        port: 443,
                    },
                    &Resolver::default(),
                    Duration::from_secs(2),
                )
                .await
                .unwrap_or_else(|code| panic!("HTTP/{version} CONNECT {status}: {code}"));
                let mut prefix = [0; 10];
                stream.read_exact(&mut prefix).await.unwrap();
                assert_eq!(&prefix, b"\x16\x03\x03\x00\x05hello");
                stream.write_all(b"client-payload").await.unwrap();
                stream.shutdown().await.unwrap();
                let mut tail = Vec::new();
                stream.read_to_end(&mut tail).await.unwrap();
                assert_eq!(tail, b"tail-after-half-close");
                peer.await.unwrap();
            }
        }
    })
    .await
    .expect("CONNECT status fixture exceeded its bounded deadline");
}

#[tokio::test]
async fn unsuccessful_connect_statuses_never_become_tunnels() {
    timeout(Duration::from_secs(5), async {
        for status in [101, 300, 301, 403, 407, 429, 500] {
            let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
            let outbound = http_proxy(listener.local_addr().unwrap().port());
            let peer = tokio::spawn(async move {
                let (mut socket, _) = listener.accept().await.unwrap();
                read_request(&mut socket).await;
                socket
                    .write_all(
                        format!("HTTP/1.1 {status} Not A Tunnel\r\nContent-Length: 4\r\n\r\nbody")
                            .as_bytes(),
                    )
                    .await
                    .unwrap();
            });
            let result = connect(
                &outbound,
                &Target {
                    host: "target.fixture.invalid".into(),
                    port: 443,
                },
                &Resolver::default(),
                Duration::from_secs(2),
            )
            .await;
            assert_eq!(result.err(), Some("UpstreamRejected"), "status {status}");
            peer.await.unwrap();
        }
    })
    .await
    .expect("CONNECT rejection fixture exceeded its bounded deadline");
}

#[tokio::test]
async fn informational_connect_responses_are_bounded_and_never_tunnel_data() {
    timeout(Duration::from_secs(5), async {
        for informational in [2, 8, 9] {
            let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
            let outbound = http_proxy(listener.local_addr().unwrap().port());
            let peer = tokio::spawn(async move {
                let (mut socket, _) = listener.accept().await.unwrap();
                read_request(&mut socket).await;
                let mut bytes = Vec::new();
                for index in 0..informational {
                    let status = if index == 0 { 100 } else { 103 };
                    bytes.extend_from_slice(
                        format!("HTTP/1.1 {status} Informational\r\n\r\n").as_bytes(),
                    );
                }
                bytes.extend_from_slice(
                    b"HTTP/1.1 200 Tunnel Ready\r\n\r\n\x16\x03\x03\x00\x05hello",
                );
                socket.write_all(&bytes).await.unwrap();
            });
            let result = connect(
                &outbound,
                &Target {
                    host: "target.fixture.invalid".into(),
                    port: 443,
                },
                &Resolver::default(),
                Duration::from_secs(2),
            )
            .await;
            if informational <= 8 {
                let mut stream = result.expect("interim response must not reject a valid tunnel");
                let mut payload = Vec::new();
                stream.read_to_end(&mut payload).await.unwrap();
                assert_eq!(payload, b"\x16\x03\x03\x00\x05hello");
            } else {
                assert_eq!(result.err(), Some("HttpUpstreamInformationalLimit"));
            }
            peer.await.unwrap();
        }
    })
    .await
    .expect("CONNECT informational fixture exceeded its bounded deadline");
}
