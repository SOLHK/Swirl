use super::*;
use base64::{Engine, engine::general_purpose::STANDARD};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    time::timeout,
};

const WAIT: Duration = Duration::from_secs(3);

async fn setup(host: &str) -> (SocketAddr, TcpListener, JoinHandle<io::Result<()>>) {
    setup_mode(host, false).await
}

async fn setup_mode(
    host: &str,
    once: bool,
) -> (SocketAddr, TcpListener, JoinHandle<io::Result<()>>) {
    let origin = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let route = Arc::new(Route {
        host: host.into(),
        port: 443,
        credentials: Credentials {
            username: "fixture-user".into(),
            password: "fixture-secret".into(),
        },
        endpoints: vec![Endpoint {
            address: origin.local_addr().unwrap(),
            source: "127.0.0.1".parse().unwrap(),
            interface: 1,
        }],
        resolved: tokio::sync::OnceCell::new(),
        once,
        upstream_used: AtomicBool::new(false),
    });
    (address, origin, tokio::spawn(serve(listener, route, WAIT)))
}

async fn request(address: SocketAddr, target: &str, credentials: &str) -> (TcpStream, String) {
    let mut client = TcpStream::connect(address).await.unwrap();
    client.write_all(format!("CONNECT {target} HTTP/1.1\r\nHost: {target}\r\nProxy-Authorization: Basic {}\r\n\r\n",STANDARD.encode(credentials)).as_bytes()).await.unwrap();
    let mut header = Vec::new();
    while !header.ends_with(b"\r\n\r\n") {
        header.push(timeout(WAIT, client.read_u8()).await.unwrap().unwrap());
        assert!(header.len() < 4096);
    }
    (client, String::from_utf8(header).unwrap())
}

#[tokio::test]
async fn authenticated_fixed_target_tunnels_both_directions_and_half_close() {
    let (address, origin, task) = setup("fixture.invalid").await;
    let echo = tokio::spawn(async move {
        let (mut peer, source) = origin.accept().await.unwrap();
        assert_eq!(source.ip(), "127.0.0.1".parse::<IpAddr>().unwrap());
        let mut request = Vec::new();
        peer.read_to_end(&mut request).await.unwrap();
        assert_eq!(request, b"opaque-tls-fixture-bytes");
        peer.write_all(&vec![0x91; 128 * 1024]).await.unwrap();
        peer.shutdown().await.unwrap();
    });
    let (mut client, header) = request(
        address,
        "fixture.invalid:443",
        "fixture-user:fixture-secret",
    )
    .await;
    assert!(header.starts_with("HTTP/1.1 200 "));
    client.write_all(b"opaque-tls-fixture-bytes").await.unwrap();
    client.shutdown().await.unwrap();
    let mut reply = Vec::new();
    timeout(WAIT, client.read_to_end(&mut reply))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(reply, vec![0x91; 128 * 1024]);
    timeout(WAIT, echo).await.unwrap().unwrap();
    task.abort();
}

#[tokio::test]
async fn wrong_credentials_and_other_target_never_open_origin() {
    let (address, origin, task) = setup("fixture.invalid").await;
    let (_, denied) = request(address, "fixture.invalid:443", "fixture-user:wrong").await;
    assert!(denied.starts_with("HTTP/1.1 407 "));
    let (_, denied) = request(
        address,
        "another.invalid:443",
        "fixture-user:fixture-secret",
    )
    .await;
    assert!(denied.starts_with("HTTP/1.1 403 "));
    assert!(
        timeout(Duration::from_millis(40), origin.accept())
            .await
            .is_err()
    );
    task.abort();
}

#[tokio::test]
async fn cancellation_closes_listener_and_an_established_tunnel() {
    let (address, origin, task) = setup("fixture.invalid").await;
    let (mut client, header) = request(
        address,
        "fixture.invalid:443",
        "fixture-user:fixture-secret",
    )
    .await;
    assert!(header.starts_with("HTTP/1.1 200 "));
    let (mut peer, _) = timeout(WAIT, origin.accept()).await.unwrap().unwrap();
    task.abort();
    let _ = task.await;
    let mut byte = [0];
    assert_eq!(
        timeout(WAIT, client.read(&mut byte))
            .await
            .unwrap()
            .unwrap(),
        0
    );
    assert_eq!(
        timeout(WAIT, peer.read(&mut byte)).await.unwrap().unwrap(),
        0
    );
    assert!(TcpStream::connect(address).await.is_err());
}

#[tokio::test]
async fn native_deadline_closes_an_idle_authenticated_tunnel_and_listener() {
    let (address, origin, task) = setup("fixture.invalid").await;
    let (mut client, header) = request(
        address,
        "fixture.invalid:443",
        "fixture-user:fixture-secret",
    )
    .await;
    assert!(header.starts_with("HTTP/1.1 200 "));
    let (mut peer, _) = origin.accept().await.unwrap();
    timeout(WAIT * 2, task).await.unwrap().unwrap().unwrap();
    let mut byte = [0];
    assert_eq!(
        timeout(WAIT, client.read(&mut byte))
            .await
            .unwrap()
            .unwrap(),
        0
    );
    assert_eq!(
        timeout(WAIT, peer.read(&mut byte)).await.unwrap().unwrap(),
        0
    );
    assert!(TcpStream::connect(address).await.is_err());
}

#[tokio::test]
async fn simultaneous_authenticated_tunnels_wait_for_a_slot_before_opening_origin() {
    let (address, origin, task) = setup("fixture.invalid").await;
    let mut clients = Vec::new();
    let mut peers = Vec::new();
    for _ in 0..4 {
        let (client, header) = request(
            address,
            "fixture.invalid:443",
            "fixture-user:fixture-secret",
        )
        .await;
        assert!(header.starts_with("HTTP/1.1 200 "));
        clients.push(client);
        peers.push(origin.accept().await.unwrap().0);
    }
    let (sent, received) = tokio::sync::oneshot::channel();
    let fifth = tokio::spawn(async move {
        let mut client = TcpStream::connect(address).await.unwrap();
        let auth = STANDARD.encode("fixture-user:fixture-secret");
        client.write_all(format!("CONNECT fixture.invalid:443 HTTP/1.1\r\nHost: fixture.invalid:443\r\nProxy-Authorization: Basic {auth}\r\n\r\n").as_bytes()).await.unwrap();
        sent.send(()).unwrap();
        let mut header = Vec::new();
        while !header.ends_with(b"\r\n\r\n") {
            header.push(client.read_u8().await.unwrap());
            assert!(header.len() < 4096);
        }
        assert!(header.starts_with(b"HTTP/1.1 200 "));
        client
    });
    timeout(WAIT, received).await.unwrap().unwrap();
    assert!(
        timeout(Duration::from_millis(40), origin.accept())
            .await
            .is_err()
    );
    assert!(!fifth.is_finished());
    drop(clients.remove(0));
    drop(peers.remove(0));
    let client = timeout(WAIT, fifth).await.unwrap().unwrap();
    let (peer, _) = timeout(WAIT, origin.accept()).await.unwrap().unwrap();
    drop(client);
    drop(peer);
    task.abort();
}

#[tokio::test]
async fn physical_dns_uses_pinned_source_and_rejects_replayed_transaction() {
    for replay in [false, true] {
        let server = tokio::net::UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let endpoint = Endpoint {
            address: server.local_addr().unwrap(),
            source: "127.0.0.1".parse().unwrap(),
            interface: 1,
        };
        let peer = tokio::spawn(async move {
            let mut bytes = [0; 2048];
            let (length, source) = server.recv_from(&mut bytes).await.unwrap();
            assert_eq!(source.ip(), "127.0.0.1".parse::<IpAddr>().unwrap());
            let mut question = swirl_dns::decode_query(&bytes[..length]).unwrap();
            assert_eq!(question.name, "fixture.invalid");
            assert_eq!(question.kind, swirl_dns::DNS_A);
            if replay {
                question.id = question.id.wrapping_add(1);
            }
            let response =
                swirl_dns::encode_response(&question, &["203.0.113.9".parse().unwrap()], 60, 0)
                    .unwrap();
            server.send_to(&response, source).await.unwrap();
        });
        let result = timeout(
            WAIT,
            query_dns("fixture.invalid", swirl_dns::DNS_A, &endpoint),
        )
        .await
        .unwrap();
        if replay {
            assert!(result.is_err());
        } else {
            assert_eq!(
                result.unwrap(),
                vec!["203.0.113.9".parse::<IpAddr>().unwrap()]
            );
        }
        peer.await.unwrap();
    }
}

#[tokio::test]
async fn truncated_physical_dns_udp_uses_the_same_pinned_tcp_server() {
    // Reserve the protocol pair together. Windows may exclude a port for only
    // one transport. Hold failed TCP candidates so port zero cannot select the
    // same unavailable UDP port again before starting either peer.
    let mut pair = None;
    let mut reserved = Vec::new();
    let mut failures = Vec::new();
    for _ in 0..16 {
        let tcp = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = tcp.local_addr().unwrap();
        match tokio::net::UdpSocket::bind(address).await {
            Ok(udp) => {
                pair = Some((tcp, udp));
                break;
            }
            Err(error) => {
                failures.push((address.port(), error.kind(), error.raw_os_error()));
                reserved.push(tcp);
            }
        }
    }
    let (tcp, udp) = pair.unwrap_or_else(|| {
        panic!("no available TCP/UDP fixture port pair; failed candidates={failures:?}")
    });
    drop(reserved);
    let endpoint = Endpoint {
        address: tcp.local_addr().unwrap(),
        source: "127.0.0.1".parse().unwrap(),
        interface: 1,
    };
    let peer = tokio::spawn(async move {
        let mut bytes = [0; 2048];
        let (length, source) = udp.recv_from(&mut bytes).await.unwrap();
        let query = bytes[..length].to_vec();
        let question = swirl_dns::decode_query(&query).unwrap();
        let mut truncated = swirl_dns::encode_response(&question, &[], 0, 0).unwrap();
        truncated[2] |= 0x02;
        udp.send_to(&truncated, source).await.unwrap();
        let (mut stream, source) = tcp.accept().await.unwrap();
        assert_eq!(source.ip(), "127.0.0.1".parse::<IpAddr>().unwrap());
        let length = stream.read_u16().await.unwrap() as usize;
        let mut actual = vec![0; length];
        stream.read_exact(&mut actual).await.unwrap();
        assert_eq!(actual, query);
        let response =
            swirl_dns::encode_response(&question, &["203.0.113.9".parse().unwrap()], 60, 0)
                .unwrap();
        stream
            .write_all(&swirl_dns::wrap_tcp(&response).unwrap())
            .await
            .unwrap();
    });
    assert_eq!(
        timeout(
            WAIT,
            query_dns("fixture.invalid", swirl_dns::DNS_A, &endpoint)
        )
        .await
        .unwrap()
        .unwrap(),
        vec!["203.0.113.9".parse::<IpAddr>().unwrap()]
    );
    timeout(WAIT, peer).await.unwrap().unwrap();
}

#[tokio::test]
async fn physical_dns_tcp_rejects_invalid_lengths_and_incomplete_frames() {
    for (length, payload) in [(0, vec![]), (11, vec![]), (4097, vec![]), (12, vec![0; 5])] {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = Endpoint {
            address: listener.local_addr().unwrap(),
            source: "127.0.0.1".parse().unwrap(),
            interface: 1,
        };
        let peer = tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let request_length = stream.read_u16().await.unwrap() as usize;
            let mut request = vec![0; request_length];
            stream.read_exact(&mut request).await.unwrap();
            stream.write_u16(length).await.unwrap();
            stream.write_all(&payload).await.unwrap();
            stream.shutdown().await.unwrap();
        });
        assert!(
            timeout(WAIT, query_dns_tcp(b"fixture-query", &endpoint))
                .await
                .unwrap()
                .is_err()
        );
        timeout(WAIT, peer).await.unwrap().unwrap();
    }
}

#[test]
fn physical_destinations_exclude_local_shared_and_fake_addresses() {
    for address in [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.1.1",
        "100.64.1.1",
        "198.18.0.1",
        "0.0.0.0",
        "255.255.255.255",
        "224.0.0.1",
        "::1",
        "::",
        "fe80::1",
        "fec0::1",
        "fc00::1",
        "ff02::1",
        "::ffff:127.0.0.1",
    ] {
        assert!(!public_destination(address.parse().unwrap()), "{address}");
    }
    for address in ["1.1.1.1", "8.8.8.8", "2606:4700:4700::1111"] {
        assert!(public_destination(address.parse().unwrap()));
    }
}

#[test]
fn fixed_capacity_abi_rejects_size_queries_and_invalid_targets_without_routes() {
    let input = br#"{"op":"start","host":"fixture.invalid","port":443}"#;
    assert_eq!(response(input, 0).unwrap_err(), -1);
    assert_eq!(response(input, 4095).unwrap_err(), -1);
    for (host, port) in [
        ("localhost", 443),
        ("sub.localhost", 443),
        ("https://fixture.invalid/private", 443),
        ("fixture.invalid", 0),
    ] {
        let input = serde_json::to_vec(&json!({"op":"start","host":host,"port":port})).unwrap();
        let (_, bytes) = response(&input, 4096).unwrap();
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&bytes.unwrap()).unwrap(),
            json!({"ok":false,"error":"PhysicalRouteTargetInvalid"})
        );
    }
    assert_eq!(
        execute(Command::Stop { handle: u64::MAX }).unwrap(),
        json!({"ok":true})
    );
}

#[tokio::test]
async fn ipv6_connect_authority_matches_the_fixed_address_not_its_text_spelling() {
    let (address, origin, task) = setup("2606:4700:4700:0:0:0:0:1111").await;
    let (mut client, header) = request(
        address,
        "[2606:4700:4700::1111]:443",
        "fixture-user:fixture-secret",
    )
    .await;
    assert!(header.starts_with("HTTP/1.1 200 "));
    let (mut peer, _) = origin.accept().await.unwrap();
    client.write_all(b"fixed-ipv6-target").await.unwrap();
    let mut actual = [0; 17];
    timeout(WAIT, peer.read_exact(&mut actual))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(&actual, b"fixed-ipv6-target");
    task.abort();
}

#[cfg(windows)]
#[test]
fn bridge_abi_start_authentication_and_idempotent_stop_need_no_system_resolution() {
    let result = execute(Command::Start {
        host: "not-resolved.fixture.invalid".into(),
        port: 443,
    })
    .unwrap();
    let handle = result["handle"].as_u64().unwrap();
    let address = SocketAddr::from(([127, 0, 0, 1], result["port"].as_u64().unwrap() as u16));
    let (_, header) = runtime().unwrap().block_on(request(
        address,
        "not-resolved.fixture.invalid:443",
        "wrong:credentials",
    ));
    assert!(header.starts_with("HTTP/1.1 407 "));
    assert_eq!(
        execute(Command::Stop { handle }).unwrap(),
        json!({"ok":true})
    );
    assert_eq!(
        execute(Command::Stop { handle }).unwrap(),
        json!({"ok":true})
    );
    assert!(std::net::TcpStream::connect_timeout(&address, WAIT).is_err());
}

#[cfg(windows)]
#[test]
fn bridge_abi_start_once_creates_a_cancellable_authenticated_route() {
    let input = br#"{"op":"start_once","host":"not-resolved.fixture.invalid","port":443}"#;
    assert_eq!(response(input, 4095).unwrap_err(), -1);
    let (_, bytes) = response(input, 4096).unwrap();
    let value: serde_json::Value = serde_json::from_slice(&bytes.unwrap()).unwrap();
    assert_eq!(value["ok"], true);
    let handle = value["handle"].as_u64().unwrap();
    let address = SocketAddr::from(([127, 0, 0, 1], value["port"].as_u64().unwrap() as u16));
    let (_, header) = runtime().unwrap().block_on(request(
        address,
        "not-resolved.fixture.invalid:443",
        "wrong:credentials",
    ));
    assert!(header.starts_with("HTTP/1.1 407 "));
    assert_eq!(
        execute(Command::Stop { handle }).unwrap(),
        json!({"ok":true})
    );
    assert!(std::net::TcpStream::connect_timeout(&address, WAIT).is_err());
}

#[tokio::test]
async fn once_bad_auth_and_target_do_not_consume_the_single_upstream_budget() {
    let (address, origin, task) = setup_mode("fixture.invalid", true).await;
    let (_, header) = request(address, "fixture.invalid:443", "fixture-user:wrong").await;
    assert!(header.starts_with("HTTP/1.1 407 "));
    let (_, header) = request(
        address,
        "another.invalid:443",
        "fixture-user:fixture-secret",
    )
    .await;
    assert!(header.starts_with("HTTP/1.1 403 "));
    assert!(
        timeout(Duration::from_millis(40), origin.accept())
            .await
            .is_err()
    );
    let (mut client, header) = request(
        address,
        "fixture.invalid:443",
        "fixture-user:fixture-secret",
    )
    .await;
    assert!(header.starts_with("HTTP/1.1 200 "));
    let (mut peer, _) = timeout(WAIT, origin.accept()).await.unwrap().unwrap();
    let (_, header) = request(
        address,
        "fixture.invalid:443",
        "fixture-user:fixture-secret",
    )
    .await;
    assert!(
        header.starts_with("HTTP/1.1 403 "),
        "a second authenticated CONNECT must be refused"
    );
    assert!(
        timeout(Duration::from_millis(40), origin.accept())
            .await
            .is_err()
    );
    client.write_all(b"only-request").await.unwrap();
    client.shutdown().await.unwrap();
    let mut received = Vec::new();
    timeout(WAIT, peer.read_to_end(&mut received))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(received, b"only-request");
    peer.write_all(b"only-reply").await.unwrap();
    peer.shutdown().await.unwrap();
    let mut reply = Vec::new();
    timeout(WAIT, client.read_to_end(&mut reply))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(reply, b"only-reply");
    task.abort();
}

#[tokio::test]
async fn once_four_authenticated_clients_open_exactly_one_upstream() {
    let (address, origin, task) = setup_mode("fixture.invalid", true).await;
    let mut attempts = Vec::new();
    for _ in 0..4 {
        attempts.push(tokio::spawn(request(
            address,
            "fixture.invalid:443",
            "fixture-user:fixture-secret",
        )));
    }
    let mut clients = Vec::new();
    let mut accepted = 0;
    let mut refused = 0;
    for attempt in attempts {
        let (client, header) = timeout(WAIT, attempt).await.unwrap().unwrap();
        accepted += usize::from(header.starts_with("HTTP/1.1 200 "));
        refused += usize::from(header.starts_with("HTTP/1.1 403 "));
        clients.push(client);
    }
    assert_eq!((accepted, refused), (1, 3));
    let (peer, _) = timeout(WAIT, origin.accept()).await.unwrap().unwrap();
    assert!(
        timeout(Duration::from_millis(40), origin.accept())
            .await
            .is_err()
    );
    drop(peer);
    drop(clients);
    task.abort();
}
