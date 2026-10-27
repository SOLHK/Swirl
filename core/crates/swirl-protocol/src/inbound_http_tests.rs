//! Real loopback sockets guard compatibility at the inbound wire boundary.
//! HTTP/1.0 CONNECT is a tunnel handshake, not permission to relax HTTP
//! forwarding, authority validation, authentication or request framing.
use super::*;
use std::time::Duration;
use tokio::net::TcpListener;

async fn accept_wire(request: &[u8], auth: Option<Credentials>) -> Result<Inbound> {
    tokio::time::timeout(Duration::from_secs(3), async {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let client = async {
            let mut socket = TcpStream::connect(address).await.unwrap();
            socket.write_all(request).await.unwrap();
            socket.shutdown().await.unwrap();
            // Keep the read half alive so rejected/authenticated handshakes
            // can write their response without racing a client-side reset.
            let mut response = Vec::new();
            socket.read_to_end(&mut response).await.unwrap();
        };
        let server = async {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut result = accept(&mut socket, &auth).await;
            if let Ok(inbound) = &mut result {
                // TCP may split the first tunnel payload at any byte. Its
                // buffered prefix plus unread bytes must remain unchanged.
                socket.read_to_end(&mut inbound.initial).await.unwrap();
            }
            result
        };
        let (_, result) = tokio::join!(client, server);
        result
    })
    .await
    .expect("inbound fixture exceeded its bounded deadline")
}

#[tokio::test]
async fn http10_connect_accepts_authority_without_host_and_preserves_tunnel_bytes() {
    let inbound = accept_wire(
        b"CONNECT desktop.example:443 HTTP/1.0\r\n\r\n\x16\x03\x01\x00\x05hello",
        None,
    )
    .await
    .expect("HTTP/1.0 CONNECT must establish an ordinary tunnel");
    assert!(matches!(inbound.kind, InboundKind::HttpConnect));
    assert_eq!(
        (
            inbound.target.host.as_str(),
            inbound.target.port,
            inbound.udp,
            inbound.initial.as_slice()
        ),
        (
            "desktop.example",
            443,
            false,
            b"\x16\x03\x01\x00\x05hello".as_slice()
        )
    );
}

#[tokio::test]
async fn http10_connect_preserves_ipv6_authority_and_proxy_authentication() {
    let auth = Credentials {
        username: "fixture".into(),
        password: "secret".into(),
    };
    let unauthenticated =
        accept_wire(b"CONNECT [::1]:8443 HTTP/1.0\r\n\r\n", Some(auth.clone())).await;
    assert_eq!(unauthenticated.err(), Some("InboundAuthentication"));
    let inbound = accept_wire(
        b"CONNECT [::1]:8443 HTTP/1.0\r\nHost: [::1]:8443\r\nProxy-Authorization: Basic Zml4dHVyZTpzZWNyZXQ=\r\n\r\n",
        Some(auth),
    ).await.expect("authenticated IPv6 CONNECT must retain its authority");
    assert!(matches!(inbound.kind, InboundKind::HttpConnect));
    assert_eq!(
        (
            inbound.target.host.as_str(),
            inbound.target.port,
            inbound.udp,
            inbound.initial
        ),
        ("::1", 8443, false, Vec::new())
    );
}

#[tokio::test]
async fn http10_connect_rejects_bodies_ambiguous_framing_and_invalid_authorities() {
    for request in [
        "CONNECT desktop.example:443 HTTP/1.0\r\nContent-Length: 1\r\n\r\nx",
        "CONNECT desktop.example:443 HTTP/1.0\r\nContent-Length: 0\r\n\r\n",
        "CONNECT desktop.example:443 HTTP/1.0\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
        "CONNECT desktop.example:443 HTTP/1.0\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\nx",
        "CONNECT desktop.example:443 HTTP/1.0\r\nHost: one.example\r\nHost: two.example\r\n\r\n",
        "CONNECT desktop.example:443 HTTP/1.0\r\nX-Test: a\x00b\r\n\r\n",
        "CONNECT desktop.example HTTP/1.0\r\n\r\n",
        "CONNECT desktop.example:0 HTTP/1.0\r\n\r\n",
        "CONNECT desktop.example:65536 HTTP/1.0\r\n\r\n",
        "CONNECT http://desktop.example:443/ HTTP/1.0\r\n\r\n",
        "CONNECT user@desktop.example:443 HTTP/1.0\r\n\r\n",
        "CONNECT ::1:443 HTTP/1.0\r\n\r\n",
    ] {
        assert!(
            accept_wire(request.as_bytes(), None).await.is_err(),
            "unsafe request was accepted: {request:?}"
        );
    }
}

#[tokio::test]
async fn http10_connect_compatibility_does_not_accept_unknown_versions_or_forwarding() {
    for request in [
        "CONNECT desktop.example:443 HTTP/1.2\r\n\r\n",
        "CONNECT desktop.example:443 HTTP/2.0\r\n\r\n",
        "CONNECT desktop.example:443\r\n\r\n",
        "GET http://desktop.example/ HTTP/1.0\r\nHost: desktop.example\r\n\r\n",
    ] {
        assert!(
            accept_wire(request.as_bytes(), None).await.is_err(),
            "version boundary was relaxed: {request:?}"
        );
    }
    let normal = accept_wire(
        b"GET http://desktop.example/path HTTP/1.1\r\nHost: desktop.example\r\n\r\n",
        None,
    )
    .await
    .unwrap();
    assert!(matches!(normal.kind, InboundKind::HttpForward));
    assert_eq!(
        (normal.target.host.as_str(), normal.target.port),
        ("desktop.example", 80)
    );
    assert!(
        accept_wire(
            b"GET http://desktop.example/path HTTP/1.1\r\nHost: another.example\r\n\r\n",
            None
        )
        .await
        .is_err()
    );
}
