//! Actual loopback sockets through Rust; no external proxy executable is present.
use serde_json::json;
use std::{
    io::{Read, Write},
    net::{TcpListener, TcpStream, UdpSocket},
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
    thread,
    time::Duration,
};
use swirl_core::Core;
use swirl_subscription::Config;

fn config() -> Config {
    Config::parse(br#"{"schema":1,"listen":"127.0.0.1:0","selected":"direct","nodes":[{"id":"direct","outbound":{"type":"direct"}},{"id":"reject","outbound":{"type":"reject"}}]}"#).unwrap()
}
fn echo() -> (u16, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    (
        port,
        thread::spawn(move || {
            let (mut s, _) = listener.accept().unwrap();
            s.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
            let mut b = [0; 8192];
            loop {
                let n = s.read(&mut b).unwrap();
                if n == 0 {
                    break;
                }
                s.write_all(&b[..n]).unwrap();
            }
        }),
    )
}
fn connect(core: &Core, port: u16) -> TcpStream {
    let mut s = TcpStream::connect(core.address()).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
    write!(
        s,
        "CONNECT 127.0.0.1:{port} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n"
    )
    .unwrap();
    assert!(header(&mut s).starts_with(b"HTTP/1.1 200"));
    s
}
fn header(s: &mut TcpStream) -> Vec<u8> {
    let mut data = Vec::new();
    while !data.ends_with(b"\r\n\r\n") {
        let mut b = [0];
        s.read_exact(&mut b).unwrap();
        data.push(b[0]);
        assert!(data.len() < 16384);
    }
    data
}

#[test]
fn tcp_large_transfer_halfclose_and_exact_counters() {
    let mut core = Core::start(config()).unwrap();
    let (port, peer) = echo();
    let mut s = connect(&core, port);
    let payload = vec![0x37; 2 * 1024 * 1024];
    let mut writer = s.try_clone().unwrap();
    let expected = payload.clone();
    let sender = thread::spawn(move || {
        writer.write_all(&payload).unwrap();
        writer.shutdown(std::net::Shutdown::Write).unwrap();
    });
    let mut response = Vec::new();
    s.read_to_end(&mut response).unwrap();
    assert_eq!(response, expected);
    sender.join().unwrap();
    peer.join().unwrap();
    for _ in 0..100 {
        if core.snapshot().unwrap().active == 0 {
            break;
        }
        thread::sleep(Duration::from_millis(10));
    }
    let snapshot = core.snapshot().unwrap();
    assert_eq!(snapshot.upload, expected.len() as u64);
    assert_eq!(snapshot.download, expected.len() as u64);
    assert_eq!(snapshot.active, 0);
    let port = core.address();
    core.stop();
    assert!(TcpListener::bind(port).is_ok());
}
#[test]
fn resolving_cidr_pins_destination_and_rule_updates_preserve_stream() {
    use std::net::ToSocketAddrs;
    let address = ("localhost", 0).to_socket_addrs().unwrap().next().unwrap();
    let listener = TcpListener::bind(address).unwrap();
    let port = listener.local_addr().unwrap().port();
    let worker = thread::spawn(move || {
        let (mut socket, _) = listener.accept().unwrap();
        socket
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut data = [0; 5];
        socket.read_exact(&mut data).unwrap();
        socket.write_all(&data).unwrap();
    });
    let mut c = config();
    c.selected = "reject".into();
    c.rules = serde_json::from_value(json!([
        {"matcher":{"type":"cidr","value":"127.0.0.0/8","resolve":true},"outbound":"direct"},
        {"matcher":{"type":"cidr","value":"::1/128","resolve":true},"outbound":"direct"}
    ]))
    .unwrap();
    let core = Core::start(c.clone()).unwrap();
    let mut old = TcpStream::connect(core.address()).unwrap();
    old.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
    write!(
        old,
        "CONNECT localhost:{port} HTTP/1.1\r\nHost: localhost:{port}\r\n\r\n"
    )
    .unwrap();
    assert!(header(&mut old).starts_with(b"HTTP/1.1 200"));
    c.rules =
        serde_json::from_value(json!([{"matcher":{"type":"match"},"outbound":"reject"}])).unwrap();
    core.configure(c).unwrap();
    old.write_all(b"alive").unwrap();
    let mut data = [0; 5];
    old.read_exact(&mut data).unwrap();
    assert_eq!(&data, b"alive");
    let mut new = TcpStream::connect(core.address()).unwrap();
    new.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    write!(
        new,
        "CONNECT localhost:{port} HTTP/1.1\r\nHost: localhost:{port}\r\n\r\n"
    )
    .unwrap();
    assert!(header(&mut new).starts_with(b"HTTP/1.1 502"));
    worker.join().unwrap();
}
#[test]
fn atomic_update_preserves_existing_stream_and_rejects_new() {
    let mut core = Core::start(config()).unwrap();
    let (port, peer) = echo();
    let mut old = connect(&core, port);
    core.select_node("reject").unwrap();
    assert!(core.select_node("missing").is_err());
    assert_eq!(core.snapshot().unwrap().selected, "reject");
    old.write_all(b"alive").unwrap();
    let mut data = [0; 5];
    old.read_exact(&mut data).unwrap();
    assert_eq!(&data, b"alive");
    let mut denied = TcpStream::connect(core.address()).unwrap();
    denied
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    write!(
        denied,
        "CONNECT 127.0.0.1:{port} HTTP/1.1\r\nHost: x\r\n\r\n"
    )
    .unwrap();
    assert!(header(&mut denied).starts_with(b"HTTP/1.1 502"));
    drop(old);
    peer.join().unwrap();
    core.stop();
}
#[test]
fn socks5_fragmented_ipv6_and_bad_command() {
    let listener = TcpListener::bind("[::1]:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let peer = thread::spawn(move || {
        let (mut s, _) = listener.accept().unwrap();
        let mut x = [0; 4];
        s.read_exact(&mut x).unwrap();
        s.write_all(&x).unwrap();
    });
    let core = Core::start(config()).unwrap();
    let mut s = TcpStream::connect(core.address()).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    s.write_all(&[5]).unwrap();
    s.write_all(&[1, 0]).unwrap();
    let mut greeting = [0; 2];
    s.read_exact(&mut greeting).unwrap();
    assert_eq!(greeting, [5, 0]);
    let mut req = vec![5, 1, 0, 4];
    req.extend(std::net::Ipv6Addr::LOCALHOST.octets());
    req.extend(port.to_be_bytes());
    for b in req {
        s.write_all(&[b]).unwrap();
    }
    let mut reply = [0; 10];
    s.read_exact(&mut reply).unwrap();
    assert_eq!(reply[1], 0);
    s.write_all(b"ipv6").unwrap();
    let mut x = [0; 4];
    s.read_exact(&mut x).unwrap();
    assert_eq!(&x, b"ipv6");
    peer.join().unwrap();
}
#[test]
fn udp_associate_preserves_boundaries_and_rejects_fragments() {
    let peer = UdpSocket::bind("127.0.0.1:0").unwrap();
    peer.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    let target = peer.local_addr().unwrap();
    let mut c = config();
    c.selected = "reject".into();
    c.rules = serde_json::from_value(json!([
        {"matcher":{"type":"source_cidr","value":"192.0.2.0/24"},"outbound":"reject"},
        {"matcher":{"type":"destination_port","value":target.port()},"outbound":"direct"},
        {"matcher":{"type":"match"},"outbound":"reject"}
    ]))
    .unwrap();
    let core = Core::start(c).unwrap();
    let worker = thread::spawn(move || {
        for _ in 0..2 {
            let mut data = [0; 4096];
            let (n, from) = peer.recv_from(&mut data).unwrap();
            peer.send_to(&data[..n], from).unwrap();
        }
    });
    let mut control = TcpStream::connect(core.address()).unwrap();
    control
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    control.write_all(&[5, 1, 0]).unwrap();
    let mut x = [0; 2];
    control.read_exact(&mut x).unwrap();
    control.write_all(&[5, 3, 0, 1, 0, 0, 0, 0, 0, 0]).unwrap();
    let mut reply = [0; 10];
    control.read_exact(&mut reply).unwrap();
    assert_eq!(reply[1], 0);
    let port = u16::from_be_bytes([reply[8], reply[9]]);
    let client = UdpSocket::bind("127.0.0.1:0").unwrap();
    client
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    for payload in [b"first".as_slice(), b"second-message".as_slice()] {
        let mut packet = vec![0, 0, 0, 1, 127, 0, 0, 1];
        packet.extend(target.port().to_be_bytes());
        packet.extend(payload);
        client.send_to(&packet, ("127.0.0.1", port)).unwrap();
        let mut output = [0; 4096];
        let (n, _) = client.recv_from(&mut output).unwrap();
        assert_eq!(&output[10..n], payload);
    }
    worker.join().unwrap();
    drop(control);
}
#[test]
fn inbound_authentication_and_resource_limit() {
    let mut c = config();
    c.inbound_auth = Some(swirl_subscription::Credentials {
        username: "test".into(),
        password: "fixture".into(),
    });
    c.limits.max_connections = 1;
    c.limits.handshake_timeout_ms = 200;
    let core = Core::start(c).unwrap();
    let mut s = TcpStream::connect(core.address()).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    s.write_all(&[5, 1, 0]).unwrap();
    let mut reply = [0; 2];
    s.read_exact(&mut reply).unwrap();
    assert_eq!(reply, [5, 255]);
    drop(s);
    thread::sleep(Duration::from_millis(50));
    let _idle = TcpStream::connect(core.address()).unwrap();
    thread::sleep(Duration::from_millis(20));
    let mut extra = TcpStream::connect(core.address()).unwrap();
    extra
        .set_read_timeout(Some(Duration::from_secs(1)))
        .unwrap();
    let mut b = [0];
    assert!(matches!(extra.read(&mut b), Ok(0) | Err(_)));
    thread::sleep(Duration::from_millis(250));
    assert!(core.snapshot().unwrap().rejected >= 1);
    assert_eq!(core.snapshot().unwrap().active, 0);
}

#[test]
fn udp_reject_dns_and_icmp_do_not_kill_association_or_change_snapshot() {
    let mut c = config();
    c.rules.push(
        serde_json::from_value(
            json!({"matcher":{"type":"domain","value":"blocked.invalid"},"outbound":"reject"}),
        )
        .unwrap(),
    );
    let core = Core::start(c.clone()).unwrap();
    let peer = UdpSocket::bind("127.0.0.1:0").unwrap();
    peer.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
    let good = peer.local_addr().unwrap().port();
    let closed = UdpSocket::bind("127.0.0.1:0").unwrap();
    let bad = closed.local_addr().unwrap().port();
    drop(closed);
    let worker = thread::spawn(move || {
        for _ in 0..2 {
            let mut buf = [0; 128];
            let (n, from) = peer.recv_from(&mut buf).unwrap();
            peer.send_to(&buf[..n], from).unwrap();
        }
    });
    let mut control = TcpStream::connect(core.address()).unwrap();
    control
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    control.write_all(&[5, 1, 0]).unwrap();
    let mut greeting = [0; 2];
    control.read_exact(&mut greeting).unwrap();
    control.write_all(&[5, 3, 0, 1, 0, 0, 0, 0, 0, 0]).unwrap();
    let mut response = [0; 10];
    control.read_exact(&mut response).unwrap();
    assert_eq!(response[1], 0);
    let relay = ("127.0.0.1", u16::from_be_bytes([response[8], response[9]]));
    let client = UdpSocket::bind("127.0.0.1:0").unwrap();
    client
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    for domain in ["blocked.invalid", "swirl-nonexistent.invalid"] {
        let mut p = vec![0, 0, 0, 3, domain.len() as u8];
        p.extend(domain.as_bytes());
        p.extend([0, 53, 7]);
        client.send_to(&p, relay).unwrap();
    }
    let mut p = vec![0, 0, 0, 1, 127, 0, 0, 1];
    p.extend(bad.to_be_bytes());
    p.extend(b"unreachable");
    client.send_to(&p, relay).unwrap();
    thread::sleep(Duration::from_millis(80));
    for round in 0..2 {
        let mut p = vec![0, 0, 0, 1, 127, 0, 0, 1];
        p.extend(good.to_be_bytes());
        p.extend(b"alive");
        client.send_to(&p, relay).unwrap();
        let mut data = [0; 128];
        let (n, _) = client.recv_from(&mut data).unwrap();
        assert_eq!(&data[10..n], b"alive");
        if round == 0 {
            c.selected = "reject".into();
            core.configure(c.clone()).unwrap();
        }
    }
    assert!(core.snapshot().unwrap().udp_dropped > 0);
    worker.join().unwrap();
}
#[test]
fn failed_socks_auth_never_reaches_target_or_direct() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let seen = Arc::new(AtomicUsize::new(0));
    let counted = seen.clone();
    let reference = thread::spawn(move || {
        let (mut s, _) = listener.accept().unwrap();
        let mut g = [0; 3];
        s.read_exact(&mut g).unwrap();
        assert_eq!(g, [5, 1, 2]);
        s.write_all(&[5, 255]).unwrap();
        counted.fetch_add(1, Ordering::SeqCst);
    });
    let mut c = config();
    c.nodes[0].outbound=serde_json::from_value(json!({"type":"socks5","host":"127.0.0.1","port":port,"auth":{"username":"u","password":"bad"}})).unwrap();
    let core = Core::start(c).unwrap();
    let mut s = TcpStream::connect(core.address()).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    s.write_all(b"CONNECT unreachable.invalid:443 HTTP/1.1\r\nHost: x\r\n\r\n")
        .unwrap();
    assert!(header(&mut s).starts_with(b"HTTP/1.1 502"));
    reference.join().unwrap();
    assert_eq!(seen.load(Ordering::SeqCst), 1);
}
