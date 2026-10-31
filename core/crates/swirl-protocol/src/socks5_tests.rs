use super::*;
use swirl_subscription::{HostMapping, Tls};
use tokio::{net::TcpListener, time::timeout};

fn outbound(port: u16) -> Outbound {
    Outbound::Socks5 {
        host: "127.0.0.1".into(),
        port,
        auth: None,
        tls: None,
        udp: true,
    }
}

async fn accept_associate(listener: TcpListener, reply: Vec<u8>) -> TcpStream {
    let (mut control, _) = listener.accept().await.unwrap();
    let mut greeting = [0; 3];
    control.read_exact(&mut greeting).await.unwrap();
    assert_eq!(greeting, [5, 1, 0]);
    // Deliberately split the reply to exercise stream framing.
    control.write_all(&[5]).await.unwrap();
    tokio::task::yield_now().await;
    control.write_all(&[0]).await.unwrap();
    let mut command = [0; 10];
    control.read_exact(&mut command).await.unwrap();
    assert_eq!(command, [5, 3, 0, 1, 0, 0, 0, 0, 0, 0]);
    for part in reply.chunks(2) {
        control.write_all(part).await.unwrap();
        tokio::task::yield_now().await;
    }
    control
}

#[tokio::test]
async fn datagram_boundaries_addresses_and_fragments() {
    for host in ["127.0.0.1", "2001:db8::7", "udp.fixture.test"] {
        let target = Target {
            host: host.into(),
            port: 5353,
        };
        for payload in [b"".as_slice(), b"first\0second", &[0xff; 1024]] {
            let wire = UdpAssociation::encode_datagram(&target, payload).unwrap();
            let (decoded, actual) = UdpAssociation::decode_datagram(&wire).await.unwrap();
            assert_eq!(decoded.host, host);
            assert_eq!(decoded.port, 5353);
            assert_eq!(actual, payload);
            for byte in [1, 127, 128, 255] {
                let mut fragmented = wire.clone();
                fragmented[2] = byte;
                assert!(matches!(
                    UdpAssociation::decode_datagram(&fragmented).await,
                    Err("Socks5UdpFragmentUnsupported")
                ));
            }
            let header_len = wire.len() - payload.len();
            for end in 0..header_len {
                assert!(UdpAssociation::decode_datagram(&wire[..end]).await.is_err());
            }
            let mut reserved = wire.clone();
            reserved[1] = 1;
            assert!(UdpAssociation::decode_datagram(&reserved).await.is_err());
            let mut zero_port = wire[..header_len].to_vec();
            zero_port[header_len - 2..].fill(0);
            assert!(UdpAssociation::decode_datagram(&zero_port).await.is_err());
        }
        let header = UdpAssociation::encode_datagram(&target, &[]).unwrap().len();
        let limit = vec![7; DATAGRAM_LIMIT - header];
        let packet = UdpAssociation::encode_datagram(&target, &limit).unwrap();
        assert_eq!(packet.len(), DATAGRAM_LIMIT);
        assert_eq!(
            UdpAssociation::decode_datagram(&packet).await.unwrap().1,
            limit
        );
        assert!(UdpAssociation::encode_datagram(&target, &vec![7; limit.len() + 1]).is_err());
    }
    for packet in [
        &[0, 0, 0, 2, 0, 1][..],
        &[0, 0, 0, 3, 0, 0, 1],
        &[0, 0, 0, 3, 2, b'a', b' ', 0, 1],
    ] {
        assert!(UdpAssociation::decode_datagram(packet).await.is_err());
    }
    assert!(
        UdpAssociation::decode_datagram(&vec![0; DATAGRAM_LIMIT + 1])
            .await
            .is_err()
    );
}

#[tokio::test]
async fn relay_uses_bound_address_configured_dns_and_control_lifetime() {
    for bound_host in ["0.0.0.0", "127.0.0.1", "relay.fixture.test"] {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let outbound = outbound(listener.local_addr().unwrap().port());
        let relay = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let mut reply = vec![5, 0, 0];
        Target {
            host: bound_host.into(),
            port: relay.local_addr().unwrap().port(),
        }
        .encode(&mut reply)
        .unwrap();
        let server = tokio::spawn(accept_associate(listener, reply));
        let resolver = Resolver::default().with_hosts(&[HostMapping {
            name: "relay.fixture.test".into(),
            address: "127.0.0.1".parse().unwrap(),
        }]);
        let association = UdpAssociation::connect(&outbound, &resolver, Duration::from_secs(2))
            .await
            .unwrap();
        let control = server.await.unwrap();
        let target = Target {
            host: "remote.fixture.test".into(),
            port: 4242,
        };
        association.send(&target, b"first\0packet").await.unwrap();
        let mut buffer = [0; 1024];
        let (n, client) = timeout(Duration::from_secs(1), relay.recv_from(&mut buffer))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            &buffer[..n],
            b"\0\0\0\x03\x13remote.fixture.test\x10\x92first\0packet"
        );
        let attacker = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        attacker.send_to(&buffer[..n], client).await.unwrap();
        let mut response = [0; 1024];
        assert!(
            timeout(Duration::from_millis(50), association.recv(&mut response))
                .await
                .is_err()
        );
        relay.send_to(&buffer[..n], client).await.unwrap();
        let actual = timeout(Duration::from_secs(1), association.recv(&mut response))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(&response[..actual], &buffer[..n]);
        drop(control);
        assert_eq!(
            timeout(Duration::from_secs(1), association.closed())
                .await
                .unwrap(),
            "Socks5UdpControlClosed"
        );
        assert!(matches!(
            association.send(&target, b"must-not-send").await,
            Err("Socks5UdpControlClosed")
        ));
        assert!(
            timeout(Duration::from_millis(50), relay.recv_from(&mut buffer))
                .await
                .is_err()
        );
    }
}

#[tokio::test]
async fn malformed_associate_replies_are_rejected() {
    for reply in [
        vec![4, 0, 0, 1, 127, 0, 0, 1, 0, 53],
        vec![5, 7, 0, 1, 127, 0, 0, 1, 0, 53],
        vec![5, 0, 1, 1, 127, 0, 0, 1, 0, 53],
        vec![5, 0, 0, 1, 127, 0, 0, 1, 0, 0],
        vec![5, 0, 0, 1, 224, 0, 0, 1, 0, 53],
        vec![5, 0, 0, 1, 255, 255, 255, 255, 0, 53],
        vec![5, 0, 0, 2],
        vec![5, 0, 0, 3, 0, 0, 53],
    ] {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let outbound = outbound(listener.local_addr().unwrap().port());
        // One write avoids requiring a peer to accept bytes after early rejection.
        let server = tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut greeting = [0; 3];
            stream.read_exact(&mut greeting).await.unwrap();
            assert_eq!(greeting, [5, 1, 0]);
            stream.write_all(&[5, 0]).await.unwrap();
            let mut command = [0; 10];
            stream.read_exact(&mut command).await.unwrap();
            assert_eq!(command, [5, 3, 0, 1, 0, 0, 0, 0, 0, 0]);
            stream.write_all(&reply).await.unwrap();
        });
        assert!(
            UdpAssociation::connect(&outbound, &Resolver::default(), Duration::from_secs(1))
                .await
                .is_err()
        );
        server.await.unwrap();
    }
}

#[tokio::test]
async fn authentication_is_shared_strict_and_does_not_downgrade() {
    for (method_reply, auth_reply, expected) in [
        ([5, 2], Some([1, 0]), Ok(())),
        ([5, 0], None, Err("UpstreamAuthentication")),
        ([5, 255], None, Err("UpstreamAuthentication")),
        ([4, 2], None, Err("UpstreamAuthentication")),
        ([5, 2], Some([1, 1]), Err("UpstreamAuthentication")),
        ([5, 2], Some([2, 0]), Err("UpstreamAuthentication")),
    ] {
        let (mut client, mut server) = tokio::io::duplex(1024);
        let peer = tokio::spawn(async move {
            let mut greeting = [0; 3];
            server.read_exact(&mut greeting).await.unwrap();
            assert_eq!(greeting, [5, 1, 2]);
            server.write_all(&method_reply).await.unwrap();
            if let Some(reply) = auth_reply {
                let mut request = [0; 13];
                server.read_exact(&mut request).await.unwrap();
                assert_eq!(&request, b"\x01\x04user\x06secret");
                server.write_all(&reply).await.unwrap();
            }
            let mut extra = [0];
            assert_eq!(server.read(&mut extra).await.unwrap(), 0);
        });
        let auth = Credentials {
            username: "user".into(),
            password: "secret".into(),
        };
        assert_eq!(authenticate(&mut client, Some(&auth)).await, expected);
        drop(client);
        peer.await.unwrap();
    }
}

#[tokio::test]
async fn disabled_tls_and_handshake_timeout_fail_closed() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let mut node = outbound(listener.local_addr().unwrap().port());
    if let Outbound::Socks5 { udp, .. } = &mut node {
        *udp = false;
    }
    assert!(matches!(
        UdpAssociation::connect(&node, &Resolver::default(), Duration::from_secs(1)).await,
        Err("Socks5UdpDisabled")
    ));
    if let Outbound::Socks5 { udp, tls, .. } = &mut node {
        *udp = true;
        *tls = Some(Tls {
            server_name: "proxy.fixture.test".into(),
            alpn: Vec::new(),
            ca_der_base64: None,
        });
    }
    assert!(matches!(
        UdpAssociation::connect(&node, &Resolver::default(), Duration::from_secs(1)).await,
        Err("Socks5UdpTlsUnsupported")
    ));
    assert!(
        timeout(Duration::from_millis(50), listener.accept())
            .await
            .is_err()
    );
    if let Outbound::Socks5 { tls, .. } = &mut node {
        *tls = None;
    }
    let peer = tokio::spawn(async move {
        let (mut stream, _) = listener.accept().await.unwrap();
        let mut greeting = [0; 3];
        stream.read_exact(&mut greeting).await.unwrap();
        assert_eq!(greeting, [5, 1, 0]);
        let mut extra = [0];
        assert_eq!(stream.read(&mut extra).await.unwrap(), 0);
    });
    let started = Instant::now();
    assert!(matches!(
        UdpAssociation::connect(&node, &Resolver::default(), Duration::from_millis(120)).await,
        Err("UpstreamProtocolTimeout")
    ));
    assert!(started.elapsed() < Duration::from_secs(1));
    peer.await.unwrap();
}

#[tokio::test]
async fn advertised_udp_relay_cannot_bypass_ingress_endpoint_guard() {
    for host in ["127.0.0.1", "relay.fixture.test"] {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let outbound = outbound(listener.local_addr().unwrap().port());
        let relay = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let forbidden = relay.local_addr().unwrap();
        let mut reply = vec![5, 0, 0];
        Target { host: host.into(), port: forbidden.port() }.encode(&mut reply).unwrap();
        let server = tokio::spawn(accept_associate(listener, reply));
        let resolver = Resolver::default().with_hosts(&[HostMapping {
            name: "relay.fixture.test".into(), address: forbidden.ip(),
        }]).with_endpoint_guard(move |address| address != forbidden);
        assert!(matches!(
            UdpAssociation::connect(&outbound, &resolver, Duration::from_secs(2)).await,
            Err("Socks5UdpRelayForbidden")
        ));
        let mut control = server.await.unwrap();
        let mut byte = [0];
        assert_eq!(timeout(Duration::from_secs(1), control.read(&mut byte)).await.unwrap().unwrap(), 0);
        let mut packet = [0; 128];
        assert!(timeout(Duration::from_millis(50), relay.recv_from(&mut packet)).await.is_err());
    }
}
