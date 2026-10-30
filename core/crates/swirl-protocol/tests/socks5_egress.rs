//! Real SOCKS5 UDP egress regression. The process-local Windows lease never
//! changes host routes or DNS and cannot affect another integration binary.
use std::{net::SocketAddr, time::Duration};
use swirl_dns::Resolver;
use swirl_protocol::{Socks5UdpAssociation, Target};
use swirl_subscription::Outbound;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream, UdpSocket},
    sync::Mutex,
    time::timeout,
};

const WAIT: Duration = Duration::from_secs(5);
static TEST_GUARD: Mutex<()> = Mutex::const_new(());

fn outbound(address: SocketAddr) -> Outbound {
    Outbound::Socks5 {
        host: address.ip().to_string(),
        port: address.port(),
        auth: None,
        tls: None,
        udp: true,
    }
}

async fn associate(listener: &TcpListener, relay: SocketAddr) -> TcpStream {
    timeout(WAIT, async {
        let (mut control, source) = listener.accept().await.unwrap();
        assert!(source.ip().is_loopback());
        let mut greeting = [0; 3];
        control.read_exact(&mut greeting).await.unwrap();
        assert_eq!(greeting, [5, 1, 0]);
        control.write_all(&[5, 0]).await.unwrap();
        let mut command = [0; 4];
        control.read_exact(&mut command).await.unwrap();
        assert_eq!(command, [5, 3, 0, if source.is_ipv6() { 4 } else { 1 }]);
        let mut unspecified = vec![0; if source.is_ipv6() { 18 } else { 6 }];
        control.read_exact(&mut unspecified).await.unwrap();
        assert!(unspecified.iter().all(|byte| *byte == 0));
        let mut reply = vec![5, 0, 0];
        match relay.ip() {
            std::net::IpAddr::V4(ip) => {
                reply.push(1);
                reply.extend_from_slice(&ip.octets());
            }
            std::net::IpAddr::V6(ip) => {
                reply.push(4);
                reply.extend_from_slice(&ip.octets());
            }
        }
        reply.extend_from_slice(&relay.port().to_be_bytes());
        control.write_all(&reply).await.unwrap();
        control
    })
    .await
    .unwrap()
}

async fn loopback_roundtrips() {
    for bind in ["127.0.0.1:0", "[::1]:0"] {
        let listener = TcpListener::bind(bind).await.unwrap();
        let relay = UdpSocket::bind(bind).await.unwrap();
        let node = outbound(listener.local_addr().unwrap());
        let resolver = Resolver::default();
        let (client, _control) = tokio::join!(
            Socks5UdpAssociation::connect(&node, &resolver, WAIT),
            associate(&listener, relay.local_addr().unwrap()),
        );
        let client = client.unwrap();
        let target = Target {
            host: "udp.fixture.invalid".into(),
            port: 5353,
        };
        let mut header = vec![0, 0, 0, 3, target.host.len() as u8];
        header.extend_from_slice(target.host.as_bytes());
        header.extend_from_slice(&target.port.to_be_bytes());
        for payload in [vec![], vec![0x6b; 1200]] {
            client.send(&target, &payload).await.unwrap();
            let mut buffer = [0; 2048];
            let (size, source) = timeout(WAIT, relay.recv_from(&mut buffer))
                .await
                .unwrap()
                .unwrap();
            assert!(source.ip().is_loopback());
            assert_eq!(source.is_ipv6(), relay.local_addr().unwrap().is_ipv6());
            assert_eq!(&buffer[..size], &[header.as_slice(), &payload].concat());
            let response = [header.as_slice(), b"peer:", &payload].concat();
            assert_eq!(
                relay.send_to(&response, source).await.unwrap(),
                response.len()
            );
            let size = timeout(WAIT, client.recv(&mut buffer))
                .await
                .unwrap()
                .unwrap();
            assert_eq!(&buffer[..size], &response);
        }
    }
}

#[tokio::test]
async fn socks5_udp_keeps_empty_and_full_ipv4_ipv6_datagrams() {
    let _guard = TEST_GUARD.lock().await;
    loopback_roundtrips().await;
}

#[cfg(windows)]
#[tokio::test]
async fn suspended_socks5_keeps_loopback_but_rejects_advertised_external_relays() {
    use swirl_transport::egress::EgressLease;

    let _guard = TEST_GUARD.lock().await;
    let lease = EgressLease::acquire_suspended().unwrap();
    for (bind, advertised) in [
        ("127.0.0.1:0", "192.0.2.1:5353"),
        ("[::1]:0", "[2001:db8::1]:5353"),
    ] {
        let listener = TcpListener::bind(bind).await.unwrap();
        let node = outbound(listener.local_addr().unwrap());
        let resolver = Resolver::default();
        let (result, _control) = tokio::join!(
            Socks5UdpAssociation::connect(&node, &resolver, WAIT),
            associate(&listener, advertised.parse().unwrap()),
        );
        assert!(
            matches!(result, Err("Socks5UdpBind")),
            "loopback TCP control cannot exempt an external UDP relay"
        );
    }
    loopback_roundtrips().await;
    lease.release_after_routes_restored().unwrap();
}
