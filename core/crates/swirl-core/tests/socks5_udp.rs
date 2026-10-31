//! Loopback end-to-end checks through Core's public API and raw RFC 1928 bytes.
use serde_json::json;
use std::{
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream, UdpSocket},
    sync::mpsc,
    thread,
    time::Duration,
};
use swirl_core::Core;
use swirl_subscription::Config;

fn config(port: u16) -> Config {
    Config::parse(&serde_json::to_vec(&json!({
        "schema":1,"listen":"127.0.0.1:0","selected":"proxy",
        "nodes":[
            {"id":"proxy","outbound":{"type":"socks5","host":"127.0.0.1","port":port,"udp":true}},
            {"id":"direct","outbound":{"type":"direct"}},
            {"id":"reject","outbound":{"type":"reject"}}
        ],
        "limits":{"max_connections":16,"handshake_timeout_ms":1000}
    })).unwrap()).unwrap()
}

fn accept_upstream(listener: &TcpListener, relay: &UdpSocket) -> TcpStream {
    let (mut stream, _) = listener.accept().unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let mut greeting = [0; 3];
    stream.read_exact(&mut greeting).unwrap();
    assert_eq!(greeting, [5, 1, 0]);
    stream.write_all(&[5, 0]).unwrap();
    let mut command = [0; 10];
    stream.read_exact(&mut command).unwrap();
    assert_eq!(command, [5, 3, 0, 1, 0, 0, 0, 0, 0, 0]);
    let mut reply = vec![5, 0, 0, 1, 0, 0, 0, 0];
    reply.extend(relay.local_addr().unwrap().port().to_be_bytes());
    stream.write_all(&reply).unwrap();
    stream
}

fn inbound(core: &Core) -> (TcpStream, UdpSocket, SocketAddr) {
    let mut control = TcpStream::connect(core.address()).unwrap();
    control
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    control.write_all(&[5, 1, 0]).unwrap();
    let mut greeting = [0; 2];
    control.read_exact(&mut greeting).unwrap();
    assert_eq!(greeting, [5, 0]);
    control.write_all(&[5, 3, 0, 1, 0, 0, 0, 0, 0, 0]).unwrap();
    let mut reply = [0; 10];
    control.read_exact(&mut reply).unwrap();
    assert_eq!(&reply[..8], &[5, 0, 0, 1, 127, 0, 0, 1]);
    let relay = SocketAddr::from(([127, 0, 0, 1], u16::from_be_bytes([reply[8], reply[9]])));
    let client = UdpSocket::bind("127.0.0.1:0").unwrap();
    client
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    (control, client, relay)
}

fn packet(host: &str, port: u16, payload: &[u8]) -> Vec<u8> {
    let mut packet = vec![0, 0, 0];
    if let Ok(ip) = host.parse::<std::net::Ipv4Addr>() {
        packet.push(1);
        packet.extend(ip.octets());
    } else {
        packet.extend([3, host.len() as u8]);
        packet.extend(host.as_bytes());
    }
    packet.extend(port.to_be_bytes());
    packet.extend(payload);
    packet
}

fn exchange(client: &UdpSocket, relay: SocketAddr, packet: &[u8]) {
    client.send_to(packet, relay).unwrap();
    let mut reply = [0; 4096];
    let (n, source) = client.recv_from(&mut reply).unwrap();
    assert_eq!(source, relay);
    assert_eq!(&reply[..n], packet);
}

#[test]
fn association_reuses_control_keeps_old_route_and_closes_with_inbound() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let relay = UdpSocket::bind("127.0.0.1:0").unwrap();
    relay
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let packets = [
        packet("unresolved.fixture.invalid", 4242, b"first\0packet"),
        packet("127.0.0.1", 4141, b"second"),
        packet("unresolved.fixture.invalid", 4343, b""),
    ];
    let expected = packets.clone();
    let server = thread::spawn(move || {
        let mut control = accept_upstream(&listener, &relay);
        let mut client = None;
        for expected in expected {
            let mut buffer = [0; 4096];
            let (n, source) = relay.recv_from(&mut buffer).unwrap();
            assert_eq!(&buffer[..n], expected);
            assert!(client.is_none_or(|previous| previous == source));
            client = Some(source);
            relay.send_to(&buffer[..n], source).unwrap();
        }
        let mut extra = [0];
        assert_eq!(control.read(&mut extra).unwrap(), 0);
        listener.set_nonblocking(true).unwrap();
        assert!(matches!(listener.accept(), Err(e) if e.kind() == std::io::ErrorKind::WouldBlock));
    });
    let mut config = config(port);
    let core = Core::start(config.clone()).unwrap();
    let (control, client, relay) = inbound(&core);
    exchange(&client, relay, &packets[0]);
    config.selected = "reject".into();
    core.configure(config).unwrap();
    exchange(&client, relay, &packets[1]);
    exchange(&client, relay, &packets[2]);
    let (new_control, new_client, new_relay) = inbound(&core);
    new_client
        .set_read_timeout(Some(Duration::from_millis(100)))
        .unwrap();
    new_client.send_to(&packets[0], new_relay).unwrap();
    let mut reply = [0; 4096];
    assert!(new_client.recv_from(&mut reply).is_err());
    drop(new_control);
    drop(control);
    server.join().unwrap();
    let snapshot = core.snapshot().unwrap();
    assert_eq!(snapshot.selected, "reject");
    assert_eq!(snapshot.upload, 18);
    assert_eq!(snapshot.download, 18);
    assert!(snapshot.udp_dropped >= 1);
}

#[test]
fn closed_proxy_never_reconnects_or_sends_direct_and_other_routes_survive() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let relay = UdpSocket::bind("127.0.0.1:0").unwrap();
    relay
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let bypass = UdpSocket::bind("127.0.0.1:0").unwrap();
    bypass
        .set_read_timeout(Some(Duration::from_millis(100)))
        .unwrap();
    let proxy_packet = packet("127.0.0.1", bypass.local_addr().unwrap().port(), b"one");
    let expected = proxy_packet.clone();
    let (close_tx, close_rx) = mpsc::channel();
    let (closed_tx, closed_rx) = mpsc::channel();
    let server = thread::spawn(move || {
        let control = accept_upstream(&listener, &relay);
        let mut buffer = [0; 4096];
        let (n, source) = relay.recv_from(&mut buffer).unwrap();
        assert_eq!(&buffer[..n], expected);
        relay.send_to(&buffer[..n], source).unwrap();
        // Let the client acknowledge its received packet before sending EOF.
        close_rx.recv_timeout(Duration::from_secs(3)).unwrap();
        drop(control);
        closed_tx.send(()).unwrap();
        relay
            .set_read_timeout(Some(Duration::from_millis(400)))
            .unwrap();
        assert!(relay.recv_from(&mut buffer).is_err());
        listener.set_nonblocking(true).unwrap();
        assert!(matches!(listener.accept(), Err(e) if e.kind() == std::io::ErrorKind::WouldBlock));
    });
    let direct = UdpSocket::bind("127.0.0.1:0").unwrap();
    let direct_port = direct.local_addr().unwrap().port();
    direct
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let direct_server = thread::spawn(move || {
        let mut buffer = [0; 32];
        let (n, source) = direct.recv_from(&mut buffer).unwrap();
        assert_eq!(&buffer[..n], b"direct");
        direct.send_to(&buffer[..n], source).unwrap();
    });
    let mut config = config(port);
    config.rules = serde_json::from_value(json!([
        {"matcher":{"type":"destination_port","value":direct_port},"outbound":"direct"}
    ]))
    .unwrap();
    let core = Core::start(config).unwrap();
    let (control, client, relay) = inbound(&core);
    exchange(&client, relay, &proxy_packet);
    close_tx.send(()).unwrap();
    closed_rx.recv_timeout(Duration::from_secs(1)).unwrap();
    thread::sleep(Duration::from_millis(100));
    client.send_to(&proxy_packet, relay).unwrap();
    exchange(&client, relay, &packet("127.0.0.1", direct_port, b"direct"));
    let mut none = [0; 32];
    assert!(bypass.recv_from(&mut none).is_err());
    server.join().unwrap();
    direct_server.join().unwrap();
    let snapshot = core.snapshot().unwrap();
    assert_eq!(snapshot.upload, 9);
    assert_eq!(snapshot.download, 9);
    assert!(snapshot.udp_dropped >= 1);
    drop(control);
}

// Linux and Windows route the full 127/8 range as loopback; no interface or
// host network mutation is needed to give the client a distinct local address.
#[cfg(any(target_os = "linux", target_os = "windows"))]
#[test]
fn relay_advertises_accepted_local_address_not_control_peer_address() {
    let mut candidate = config(9);
    candidate.selected = "direct".into();
    let core = Core::start(candidate).unwrap();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let mut control = runtime.block_on(async {
        let socket = tokio::net::TcpSocket::new_v4().unwrap();
        socket.bind("127.0.0.2:0".parse().unwrap()).unwrap();
        socket
            .connect(core.address())
            .await
            .unwrap()
            .into_std()
            .unwrap()
    });
    control.set_nonblocking(false).unwrap();
    control
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    assert_eq!(control.local_addr().unwrap().ip().to_string(), "127.0.0.2");
    control.write_all(&[5, 1, 0]).unwrap();
    let mut greeting = [0; 2];
    control.read_exact(&mut greeting).unwrap();
    assert_eq!(greeting, [5, 0]);
    control.write_all(&[5, 3, 0, 1, 0, 0, 0, 0, 0, 0]).unwrap();
    let mut response = [0; 10];
    control.read_exact(&mut response).unwrap();
    assert_eq!(&response[..8], &[5, 0, 0, 1, 127, 0, 0, 1]);
    let relay = SocketAddr::from((
        [127, 0, 0, 1],
        u16::from_be_bytes([response[8], response[9]]),
    ));
    let origin = UdpSocket::bind("127.0.0.1:0").unwrap();
    origin
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let destination = origin.local_addr().unwrap();
    let client = UdpSocket::bind("127.0.0.2:0").unwrap();
    client
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let expected = packet("127.0.0.1", destination.port(), b"distinct-client");
    client.send_to(&expected, relay).unwrap();
    let mut bytes = [0; 128];
    let (size, peer) = origin.recv_from(&mut bytes).unwrap();
    assert_eq!(&bytes[..size], b"distinct-client");
    origin.send_to(&bytes[..size], peer).unwrap();
    let (size, source) = client.recv_from(&mut bytes).unwrap();
    assert_eq!(source, relay);
    assert_eq!(&bytes[..size], expected);
    drop(control);
    drop(core);
}
