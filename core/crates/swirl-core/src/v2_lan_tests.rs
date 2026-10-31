//! Real loopback peers exercise the production LAN ingress/route/relay path.
//! The test-only address admission permits loopback fixtures; public lan_start
//! still rejects loopback/wildcard/public interfaces. No host network changes.
use super::*;
use base64::{Engine, engine::general_purpose::STANDARD};
use std::{
    io::{Read, Write},
    net::{TcpListener as StdListener, TcpStream as StdStream},
    thread,
};
use swirl_subscription::v2::{DEFAULT_POLICY_ID, DefaultPolicy};

const STORE: &str = "40000000-0000-4000-8000-000000000001";
const START: &str = "50000000-0000-4000-8000-000000000001";
const REQUEST: &str = "50000000-0000-4000-8000-000000000002";
const A: &str = "10000000-0000-4000-8000-000000000001";
const B: &str = "10000000-0000-4000-8000-000000000002";

fn wait(mut predicate: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(4);
    while !predicate() {
        assert!(Instant::now() < deadline, "LAN fixture deadline");
        thread::sleep(Duration::from_millis(5));
    }
}

fn stream(address: SocketAddr) -> StdStream {
    let stream = StdStream::connect_timeout(&address, Duration::from_secs(3)).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    stream
        .set_write_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    stream
}

fn header(stream: &mut StdStream) -> std::io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    while !bytes.ends_with(b"\r\n\r\n") {
        if bytes.len() > 8192 {
            return Err(std::io::ErrorKind::InvalidData.into());
        }
        let mut byte = [0];
        stream.read_exact(&mut byte)?;
        bytes.push(byte[0]);
    }
    Ok(bytes)
}

struct Peer {
    address: SocketAddr,
    requests: Arc<AtomicUsize>,
    leaked_auth: Arc<AtomicBool>,
    stop: Arc<AtomicBool>,
    task: Option<thread::JoinHandle<()>>,
}

impl Peer {
    fn new(marker: u8) -> Self {
        let listener = StdListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let requests = Arc::new(AtomicUsize::new(0));
        let leaked_auth = Arc::new(AtomicBool::new(false));
        let stop = Arc::new(AtomicBool::new(false));
        let task = thread::spawn({
            let stop = stop.clone();
            let requests = requests.clone();
            let leaked_auth = leaked_auth.clone();
            move || {
                let mut workers = Vec::new();
                while !stop.load(Ordering::Acquire) {
                    let (mut socket, _) = match listener.accept() {
                        Ok(pair) => pair,
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            thread::sleep(Duration::from_millis(5));
                            continue;
                        }
                        Err(_) => break,
                    };
                    let requests = requests.clone();
                    let leaked_auth = leaked_auth.clone();
                    workers.push(thread::spawn(move || {
                        socket.set_nonblocking(false).unwrap();
                        socket.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
                        socket.set_write_timeout(Some(Duration::from_secs(3))).unwrap();
                        let Ok(request) = header(&mut socket) else { return };
                        if !request.starts_with(b"CONNECT ") { return; }
                        requests.fetch_add(1, Ordering::Relaxed);
                        if socket.write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n").is_err() { return; }
                        loop {
                            let mut bytes = [0;4];
                            if socket.read_exact(&mut bytes).is_err() { return; }
                            if bytes == *b"GET " {
                                let Ok(rest) = header(&mut socket) else { return };
                                if String::from_utf8_lossy(&rest).to_ascii_lowercase().contains("proxy-authorization") {
                                    leaked_auth.store(true, Ordering::Release);
                                }
                                let _ = socket.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\nokay");
                                return;
                            }
                            let response = [marker, bytes[0], bytes[1], bytes[2], bytes[3]];
                            if socket.write_all(&response).is_err() { return; }
                        }
                    }));
                }
                for worker in workers {
                    worker.join().unwrap();
                }
            }
        });
        Self {
            address,
            requests,
            leaked_auth,
            stop,
            task: Some(task),
        }
    }

    fn node(&self, id: &str) -> Node {
        Node {
            id: id.into(),
            outbound: Outbound::HttpConnect {
                host: self.address.ip().to_string(),
                port: self.address.port(),
                auth: None,
                tls: None,
            },
        }
    }
}

impl Drop for Peer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(task) = self.task.take() {
            task.join().unwrap();
        }
    }
}

fn config(nodes: Vec<Node>, selected: &str) -> RuntimeConfig {
    RuntimeConfig {
        schema: 2,
        listen: "127.0.0.1:0".parse().unwrap(),
        nodes,
        policy: PolicyDocument {
            schema: 2,
            mode: Mode::Global,
            default_policy: DefaultPolicy {
                id: DEFAULT_POLICY_ID.into(),
                target: Target::Node {
                    id: selected.into(),
                },
            },
            service_policies: vec![],
            groups: vec![],
            explicit_direct_rules: vec![],
            custom_rules: vec![],
            missing_targets: vec![],
            classification_dns: ClassificationDns::Disabled,
        },
        dns: Dns::default(),
        inbound_auth: None,
        limits: Limits::default(),
        china_rules_directory: None,
        node_sources: BTreeMap::new(),
        transports: BTreeMap::new(),
    }
}

fn fixture_ip() -> IpAddr {
    if cfg!(target_os = "macos") {
        "127.0.0.1"
    } else {
        "127.0.0.2"
    }
    .parse()
    .unwrap()
}

fn lan_config(separate: bool) -> LanConfig {
    let address = SocketAddr::new(fixture_ip(), 0);
    let http = StdListener::bind(address).unwrap();
    let socks = StdListener::bind(address).unwrap();
    let udp = StdUdpSocket::bind(address).unwrap();
    let udp_port = udp.local_addr().unwrap().port();
    LanConfig {
        listen_ip: fixture_ip(),
        http_port: http.local_addr().unwrap().port(),
        socks_port: if separate {
            socks.local_addr().unwrap().port()
        } else {
            http.local_addr().unwrap().port()
        },
        udp_port_start: udp_port,
        udp_port_end: udp_port,
        allowed_cidrs: vec!["192.168.50.0/24".into()],
        auth: Credentials {
            username: "fixture".into(),
            password: "fixture-secret-123".into(),
        },
        max_connections: 16,
        max_connections_per_client: 8,
        auth_failures_per_minute: 5,
        idle_timeout_secs: 60,
        host_addresses: vec![fixture_ip()],
    }
}

fn start_fixture(core: &mut Core, config: &LanConfig) {
    config.validate_common().unwrap();
    core.lan = Some(
        LanRuntime::start_bound(
            core.runtime.as_ref().unwrap(),
            core.shared.clone(),
            config.clone(),
            Access::LoopbackFixture,
        )
        .unwrap(),
    );
    assert_eq!(core.lan_status().unwrap()["running"], true);
}

fn http_connect(config: &LanConfig, authenticated: bool, host: &str) -> (StdStream, Vec<u8>) {
    let mut client = stream(SocketAddr::new(config.listen_ip, config.http_port));
    let authorization = if authenticated {
        format!(
            "Proxy-Authorization: Basic {}\r\n",
            STANDARD.encode(format!("{}:{}", config.auth.username, config.auth.password))
        )
    } else {
        String::new()
    };
    client
        .write_all(
            format!("CONNECT {host}:80 HTTP/1.1\r\nHost: {host}:80\r\n{authorization}\r\n")
                .as_bytes(),
        )
        .unwrap();
    let response = header(&mut client).unwrap();
    (client, response)
}

fn exchange(client: &mut StdStream, expected: u8) {
    client.write_all(b"ping").unwrap();
    let mut response = [0; 5];
    client.read_exact(&mut response).unwrap();
    assert_eq!(response, [expected, b'p', b'i', b'n', b'g']);
}

fn socks_auth(config: &LanConfig, password: &str) -> (StdStream, [u8; 2]) {
    socks_auth_stream(
        stream(SocketAddr::new(config.listen_ip, config.socks_port)),
        config,
        password,
    )
}

fn socks_auth_stream(
    mut client: StdStream,
    config: &LanConfig,
    password: &str,
) -> (StdStream, [u8; 2]) {
    client.write_all(&[5, 1, 2]).unwrap();
    let mut response = [0; 2];
    client.read_exact(&mut response).unwrap();
    assert_eq!(response, [5, 2]);
    let mut auth = vec![1, config.auth.username.len() as u8];
    auth.extend(config.auth.username.as_bytes());
    auth.push(password.len() as u8);
    auth.extend(password.as_bytes());
    client.write_all(&auth).unwrap();
    client.read_exact(&mut response).unwrap();
    (client, response)
}

#[test]
fn authenticated_http_socks_and_http_forward_use_one_native_policy() {
    let peer = Peer::new(b'A');
    let mut core =
        Core::start(config(vec![peer.node(A)], A), STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(true);
    assert_eq!(
        core.lan_start(lan.clone()).unwrap_err(),
        "LanPrivateAddressRequired"
    );
    start_fixture(&mut core, &lan);
    let (_, denied) = http_connect(&lan, false, "target.fixture.invalid");
    assert!(denied.starts_with(b"HTTP/1.1 407"));
    assert_eq!(peer.requests.load(Ordering::Relaxed), 0);
    let (mut http, response) = http_connect(&lan, true, "target.fixture.invalid");
    assert!(response.starts_with(b"HTTP/1.1 200"));
    exchange(&mut http, b'A');
    let (mut socks, response) = socks_auth(&lan, &lan.auth.password);
    assert_eq!(response, [1, 0]);
    let host = b"target.fixture.invalid";
    let mut connect = vec![5, 1, 0, 3, host.len() as u8];
    connect.extend(host);
    connect.extend([0, 80]);
    socks.write_all(&connect).unwrap();
    let mut response = [0; 10];
    socks.read_exact(&mut response).unwrap();
    assert_eq!(response[1], 0);
    exchange(&mut socks, b'A');
    let mut forward = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    let auth = STANDARD.encode(format!("{}:{}", lan.auth.username, lan.auth.password));
    forward.write_all(format!("GET http://target.fixture.invalid/path HTTP/1.1\r\nHost: target.fixture.invalid\r\nProxy-Authorization: Basic {auth}\r\n\r\n").as_bytes()).unwrap();
    assert!(header(&mut forward).unwrap().starts_with(b"HTTP/1.1 200"));
    let mut body = [0; 4];
    forward.read_exact(&mut body).unwrap();
    assert_eq!(&body, b"okay");
    assert!(!peer.leaked_auth.load(Ordering::Acquire));
    let status = core.lan_status().unwrap();
    assert!(status["uploaded"].as_u64().unwrap() >= 8);
    assert!(status["downloaded"].as_u64().unwrap() >= 10);
    assert_eq!(
        status["clients"][0]["ip"],
        http.local_addr().unwrap().ip().to_string()
    );
    assert!(!status.to_string().contains(&lan.auth.password));
    drop(http);
    drop(socks);
    drop(forward);
    core.stop();
}

#[test]
fn failed_auth_rate_limit_and_client_acl_open_no_outbound() {
    let peer = Peer::new(b'A');
    let mut core =
        Core::start(config(vec![peer.node(A)], A), STORE.into(), 1, START.into()).unwrap();
    let mut lan = lan_config(false);
    lan.auth_failures_per_minute = 2;
    start_fixture(&mut core, &lan);
    for _ in 0..2 {
        let (_, reply) = socks_auth(&lan, "incorrect-secret");
        assert_eq!(reply, [1, 1]);
        wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    }
    let mut blocked = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    let mut byte = [0];
    assert!(blocked.read(&mut byte).map_or(true, |n| n == 0));
    wait(|| core.lan_status().unwrap()["rejected"].as_u64().unwrap() >= 1);
    assert_eq!(core.lan_status().unwrap()["auth_failures"], 2);
    assert_eq!(peer.requests.load(Ordering::Relaxed), 0);
    core.lan_stop().unwrap();
    core.lan = Some(
        LanRuntime::start_bound(
            core.runtime.as_ref().unwrap(),
            core.shared.clone(),
            lan.clone(),
            Access::Private(lan.cidrs().unwrap()),
        )
        .unwrap(),
    );
    let mut denied = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    assert!(denied.read(&mut byte).map_or(true, |n| n == 0));
    wait(|| core.lan_status().unwrap()["last_error"] == "LanClientDenied");
    core.stop();
}

#[test]
fn lan_stop_preserves_loopback_and_existing_policy_sessions_survive_update() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let initial = config(vec![a.node(A), b.node(B)], A);
    let mut core = Core::start(initial, STORE.into(), 1, START.into()).unwrap();
    let mut local = stream(core.address());
    local.write_all(b"CONNECT target.fixture.invalid:80 HTTP/1.1\r\nHost: target.fixture.invalid:80\r\n\r\n").unwrap();
    assert!(header(&mut local).unwrap().starts_with(b"HTTP/1.1 200"));
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let (mut existing, reply) = http_connect(&lan, true, "target.fixture.invalid");
    assert!(reply.starts_with(b"HTTP/1.1 200"));
    let prepared = core
        .prepare(
            REQUEST.into(),
            STORE,
            1,
            2,
            1,
            1,
            config(vec![a.node(A), b.node(B)], B),
            vec![],
        )
        .unwrap();
    let token = prepared["prepared_token"].as_str().unwrap();
    let digest = prepared["plan_digest"].as_str().unwrap();
    core.activate(REQUEST, token, digest, 1, 2).unwrap();
    core.finish(
        REQUEST,
        token,
        DurableReceipt {
            store_id: STORE.into(),
            request_id: REQUEST.into(),
            saved_revision: "2".into(),
            plan_digest: digest.into(),
        },
    )
    .unwrap();
    exchange(&mut existing, b'A');
    exchange(&mut local, b'A');
    let (mut next, reply) = http_connect(&lan, true, "target.fixture.invalid");
    assert!(reply.starts_with(b"HTTP/1.1 200"));
    exchange(&mut next, b'B');
    let stopped = core.lan_stop().unwrap();
    assert_eq!(stopped["running"], false);
    assert_eq!(stopped["active_connections"], 0);
    exchange(&mut local, b'A');
    assert!(StdListener::bind(SocketAddr::new(lan.listen_ip, lan.http_port)).is_ok());
    drop(existing);
    drop(next);
    drop(local);
    core.stop();
}

#[test]
fn host_rebinding_protocol_ports_and_partial_bind_fail_closed() {
    let peer = Peer::new(b'A');
    let mut candidate = config(vec![peer.node(A)], A);
    candidate.dns.hosts.push(swirl_subscription::HostMapping {
        name: "host.fixture.invalid".into(),
        address: "127.0.0.1".parse().unwrap(),
    });
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(true);
    start_fixture(&mut core, &lan);
    for host in [
        "127.0.0.1",
        "localhost",
        "host.fixture.invalid",
        "169.254.169.254",
    ] {
        let (_, response) = http_connect(&lan, true, host);
        assert!(!response.starts_with(b"HTTP/1.1 200"));
    }
    assert_eq!(peer.requests.load(Ordering::Relaxed), 0);
    let mut wrong = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    wrong.write_all(&[5, 1, 2]).unwrap();
    let mut reply = [0; 2];
    assert!(wrong.read(&mut reply).map_or(true, |n| n == 0));
    core.lan_stop().unwrap();
    let occupied = StdListener::bind(SocketAddr::new(lan.listen_ip, lan.socks_port)).unwrap();
    assert!(
        LanRuntime::start_bound(
            core.runtime.as_ref().unwrap(),
            core.shared.clone(),
            lan.clone(),
            Access::LoopbackFixture
        )
        .is_err()
    );
    assert!(StdListener::bind(SocketAddr::new(lan.listen_ip, lan.http_port)).is_ok());
    drop(occupied);
    core.stop();
}

#[test]
fn per_client_limit_and_pending_authentication_are_bounded() {
    let peer = Peer::new(b'A');
    let mut core =
        Core::start(config(vec![peer.node(A)], A), STORE.into(), 1, START.into()).unwrap();
    let mut lan = lan_config(false);
    lan.max_connections_per_client = 1;
    start_fixture(&mut core, &lan);
    let (mut first, reply) = http_connect(&lan, true, "target.fixture.invalid");
    assert!(reply.starts_with(b"HTTP/1.1 200"));
    let mut excess = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    let mut byte = [0];
    assert!(excess.read(&mut byte).map_or(true, |n| n == 0));
    assert_eq!(core.lan_status().unwrap()["active_connections"], 1);
    exchange(&mut first, b'A');
    drop(first);
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    core.lan_stop().unwrap();
    lan.max_connections_per_client = 8;
    lan.auth_failures_per_minute = 1;
    start_fixture(&mut core, &lan);
    let mut pending = stream(SocketAddr::new(lan.listen_ip, lan.socks_port));
    pending.write_all(&[5, 1, 2]).unwrap();
    let mut greeting = [0; 2];
    pending.read_exact(&mut greeting).unwrap();
    assert_eq!(greeting, [5, 2]);
    let mut additional = stream(SocketAddr::new(lan.listen_ip, lan.socks_port));
    assert!(additional.read(&mut byte).map_or(true, |n| n == 0));
    assert_eq!(core.lan_status().unwrap()["active_connections"], 1);
    drop(pending);
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    core.stop();
}

#[test]
fn a_native_outbound_pointing_back_to_lan_is_rejected_before_recursing() {
    let peer = Peer::new(b'A');
    let mut core =
        Core::start(config(vec![peer.node(A)], A), STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let node = Node {
        id: B.into(),
        outbound: Outbound::HttpConnect {
            host: lan.listen_ip.to_string(),
            port: lan.http_port,
            auth: None,
            tls: None,
        },
    };
    let prepared = core
        .prepare(
            REQUEST.into(),
            STORE,
            1,
            2,
            1,
            1,
            config(vec![peer.node(A), node], B),
            vec![],
        )
        .unwrap();
    let token = prepared["prepared_token"].as_str().unwrap();
    let digest = prepared["plan_digest"].as_str().unwrap();
    core.activate(REQUEST, token, digest, 1, 2).unwrap();
    core.finish(
        REQUEST,
        token,
        DurableReceipt {
            store_id: STORE.into(),
            request_id: REQUEST.into(),
            saved_revision: "2".into(),
            plan_digest: digest.into(),
        },
    )
    .unwrap();
    let (_, response) = http_connect(&lan, true, "target.fixture.invalid");
    assert!(!response.starts_with(b"HTTP/1.1 200"));
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    assert_eq!(
        core.lan_status().unwrap()["last_error"],
        "LanOutboundProxyLoop"
    );
    assert_eq!(core.lan_status().unwrap()["accepted"], 1);
    assert_eq!(peer.requests.load(Ordering::Relaxed), 0);
    core.stop();
}

#[test]
fn authenticated_udp_is_bound_to_local_interface_pinned_bounded_and_released() {
    let listener = StdListener::bind("127.0.0.1:0").unwrap();
    let upstream_address = listener.local_addr().unwrap();
    let upstream_udp = StdUdpSocket::bind("127.0.0.1:0").unwrap();
    upstream_udp
        .set_read_timeout(Some(Duration::from_secs(4)))
        .unwrap();
    let packets = Arc::new(AtomicUsize::new(0));
    let server = thread::spawn({
        let packets = packets.clone();
        move || {
            let (mut control, _) = listener.accept().unwrap();
            control
                .set_read_timeout(Some(Duration::from_secs(4)))
                .unwrap();
            control
                .set_write_timeout(Some(Duration::from_secs(4)))
                .unwrap();
            let mut greeting = [0; 3];
            control.read_exact(&mut greeting).unwrap();
            assert_eq!(greeting, [5, 1, 0]);
            control.write_all(&[5, 0]).unwrap();
            let mut request = [0; 10];
            control.read_exact(&mut request).unwrap();
            assert_eq!(request, [5, 3, 0, 1, 0, 0, 0, 0, 0, 0]);
            let mut response = vec![5, 0, 0, 1, 127, 0, 0, 1];
            response.extend(upstream_udp.local_addr().unwrap().port().to_be_bytes());
            control.write_all(&response).unwrap();
            for _ in 0..2 {
                let mut buffer = [0; 4096];
                let (count, source) = upstream_udp.recv_from(&mut buffer).unwrap();
                packets.fetch_add(1, Ordering::Release);
                upstream_udp.send_to(&buffer[..count], source).unwrap();
            }
            let mut byte = [0];
            assert_eq!(control.read(&mut byte).unwrap(), 0);
        }
    });
    let node = Node {
        id: A.into(),
        outbound: Outbound::Socks5 {
            host: upstream_address.ip().to_string(),
            port: upstream_address.port(),
            auth: None,
            tls: None,
            udp: true,
        },
    };
    let mut core = Core::start(config(vec![node], A), STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let (mut control, response) = socks_auth(&lan, &lan.auth.password);
    assert_eq!(response, [1, 0]);
    let client =
        StdUdpSocket::bind(SocketAddr::new(control.local_addr().unwrap().ip(), 0)).unwrap();
    client
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let mut request = vec![5, 3, 0, 1, 0, 0, 0, 0];
    request.extend(client.local_addr().unwrap().port().to_be_bytes());
    control.write_all(&request).unwrap();
    let mut response = [0; 10];
    control.read_exact(&mut response).unwrap();
    let IpAddr::V4(local_ip) = fixture_ip() else {
        unreachable!()
    };
    assert_eq!(&response[..4], &[5, 0, 0, 1]);
    assert_eq!(&response[4..8], &local_ip.octets());
    let relay = SocketAddr::new(
        lan.listen_ip,
        u16::from_be_bytes([response[8], response[9]]),
    );
    assert_eq!(relay.port(), lan.udp_port_start);
    let mut packet = vec![0, 0, 0, 1, 203, 0, 113, 8, 1, 187];
    packet.extend(b"first\0payload");
    client.send_to(&packet, relay).unwrap();
    let mut reply = [0; 4096];
    let (count, source) = client.recv_from(&mut reply).unwrap();
    assert_eq!(source, relay);
    assert_eq!(&reply[..count], packet);
    let rogue = StdUdpSocket::bind(SocketAddr::new(client.local_addr().unwrap().ip(), 0)).unwrap();
    rogue
        .set_read_timeout(Some(Duration::from_millis(100)))
        .unwrap();
    rogue.send_to(&packet, relay).unwrap();
    assert!(rogue.recv_from(&mut reply).is_err());
    let mut fragment = packet.clone();
    fragment[2] = 1;
    client.send_to(&fragment, relay).unwrap();
    client
        .set_read_timeout(Some(Duration::from_millis(100)))
        .unwrap();
    assert!(client.recv_from(&mut reply).is_err());
    assert_eq!(packets.load(Ordering::Acquire), 1);
    let (mut excess, response) = socks_auth(&lan, &lan.auth.password);
    assert_eq!(response, [1, 0]);
    excess.write_all(&[5, 3, 0, 1, 0, 0, 0, 0, 0, 0]).unwrap();
    let mut denied = [0; 10];
    excess.read_exact(&mut denied).unwrap();
    assert_ne!(denied[1], 0);
    client
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    client.send_to(&packet, relay).unwrap();
    let (count, _) = client.recv_from(&mut reply).unwrap();
    assert_eq!(&reply[..count], packet);
    drop(excess);
    drop(control);
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    server.join().unwrap();
    assert!(StdUdpSocket::bind(relay).is_ok());
    assert_eq!(core.lan_status().unwrap()["uploaded"], 26);
    assert_eq!(core.lan_status().unwrap()["downloaded"], 26);
    core.stop();
}

#[test]
fn rejected_datagrams_do_not_keep_an_idle_udp_association_alive() {
    let peer = Peer::new(b'A');
    let mut core =
        Core::start(config(vec![peer.node(A)], A), STORE.into(), 1, START.into()).unwrap();
    let mut lan = lan_config(false);
    // Only the private fixture bypasses the product's minimum 60-second idle
    // setting; the exact timer and data-plane loop are unchanged.
    lan.idle_timeout_secs = 1;
    core.lan = Some(
        LanRuntime::start_bound(
            core.runtime.as_ref().unwrap(),
            core.shared.clone(),
            lan.clone(),
            Access::LoopbackFixture,
        )
        .unwrap(),
    );
    let (mut control, response) = socks_auth(&lan, &lan.auth.password);
    assert_eq!(response, [1, 0]);
    control.write_all(&[5, 3, 0, 1, 0, 0, 0, 0, 0, 0]).unwrap();
    let mut response = [0; 10];
    control.read_exact(&mut response).unwrap();
    assert_eq!(response[1], 0);
    let relay = SocketAddr::new(
        lan.listen_ip,
        u16::from_be_bytes([response[8], response[9]]),
    );
    let socket =
        StdUdpSocket::bind(SocketAddr::new(control.local_addr().unwrap().ip(), 0)).unwrap();
    for _ in 0..15 {
        let _ = socket.send_to(&[0, 0, 1, 1, 203, 0, 113, 8, 0, 53, 1], relay);
        thread::sleep(Duration::from_millis(100));
    }
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    assert_eq!(core.lan_status().unwrap()["last_error"], "LanIdleTimeout");
    assert_eq!(peer.requests.load(Ordering::Relaxed), 0);
    core.stop();
}

#[test]
fn direct_and_rule_modes_use_real_dual_stack_tcp_and_udp_targets() {
    for mode in [Mode::Direct, Mode::Rule] {
        for target_ip in ["127.0.0.1", "::1"] {
            let ip: IpAddr = target_ip.parse().unwrap();
            let tcp = StdListener::bind(SocketAddr::new(ip, 0)).unwrap();
            let tcp_address = tcp.local_addr().unwrap();
            let udp = StdUdpSocket::bind(SocketAddr::new(ip, 0)).unwrap();
            let udp_address = udp.local_addr().unwrap();
            udp.set_read_timeout(Some(Duration::from_secs(4))).unwrap();
            let tcp_peer = thread::spawn(move || {
                let (mut stream, _) = tcp.accept().unwrap();
                stream
                    .set_read_timeout(Some(Duration::from_secs(4)))
                    .unwrap();
                let mut bytes = [0; 4];
                stream.read_exact(&mut bytes).unwrap();
                assert_eq!(&bytes, b"ping");
                stream.write_all(b"pong").unwrap();
            });
            let udp_peer = thread::spawn(move || {
                let mut bytes = [0; 128];
                let (length, source) = udp.recv_from(&mut bytes).unwrap();
                assert_eq!(&bytes[..length], b"dual-stack-udp");
                udp.send_to(&bytes[..length], source).unwrap();
            });
            let unused_proxy = Peer::new(b'P');
            let mut candidate = config(vec![unused_proxy.node(A)], A);
            candidate.policy.mode = mode;
            candidate.dns.hosts.push(swirl_subscription::HostMapping {
                name: "direct.fixture.invalid".into(),
                address: ip,
            });
            candidate
                .policy
                .custom_rules
                .push(swirl_subscription::v2::PolicyRule {
                    id: "60000000-0000-4000-8000-000000000001".into(),
                    name: "fixture direct".into(),
                    enabled: true,
                    priority: 1,
                    matcher: swirl_subscription::Matcher::Match {},
                    target: Target::Direct {},
                });
            let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
            let lan = lan_config(false);
            start_fixture(&mut core, &lan);
            // Exact loopback destination exceptions exist only in this private
            // test fixture, never in serialized/product configuration.
            core.lan
                .as_ref()
                .unwrap()
                .state
                .fixture_targets
                .lock()
                .unwrap()
                .extend([tcp_address, udp_address]);
            let mut tcp_client = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
            let auth = STANDARD.encode(format!("{}:{}", lan.auth.username, lan.auth.password));
            tcp_client.write_all(format!("CONNECT direct.fixture.invalid:{} HTTP/1.1\r\nHost: direct.fixture.invalid:{}\r\nProxy-Authorization: Basic {auth}\r\n\r\n", tcp_address.port(), tcp_address.port()).as_bytes()).unwrap();
            assert!(
                header(&mut tcp_client)
                    .unwrap()
                    .starts_with(b"HTTP/1.1 200")
            );
            tcp_client.write_all(b"ping").unwrap();
            let mut tcp_reply = [0; 4];
            tcp_client.read_exact(&mut tcp_reply).unwrap();
            assert_eq!(&tcp_reply, b"pong");
            let (mut control, authenticated) = socks_auth(&lan, &lan.auth.password);
            assert_eq!(authenticated, [1, 0]);
            let client =
                StdUdpSocket::bind(SocketAddr::new(control.local_addr().unwrap().ip(), 0)).unwrap();
            client
                .set_read_timeout(Some(Duration::from_secs(4)))
                .unwrap();
            let mut association = vec![5, 3, 0, 1, 0, 0, 0, 0];
            association.extend(client.local_addr().unwrap().port().to_be_bytes());
            control.write_all(&association).unwrap();
            let mut accepted = [0; 10];
            control.read_exact(&mut accepted).unwrap();
            assert_eq!(accepted[1], 0);
            let relay = SocketAddr::new(
                lan.listen_ip,
                u16::from_be_bytes([accepted[8], accepted[9]]),
            );
            let mut packet = vec![0, 0, 0];
            NetworkTarget {
                host: target_ip.into(),
                port: udp_address.port(),
            }
            .encode(&mut packet)
            .unwrap();
            packet.extend(b"dual-stack-udp");
            client.send_to(&packet, relay).unwrap();
            let mut response = [0; 128];
            let (length, source) = client.recv_from(&mut response).unwrap();
            assert_eq!(source, relay);
            assert_eq!(&response[..length], packet);
            assert_eq!(unused_proxy.requests.load(Ordering::Relaxed), 0);
            tcp_peer.join().unwrap();
            udp_peer.join().unwrap();
            drop(control);
            drop(tcp_client);
            core.lan_stop().unwrap();
            assert_eq!(core.lan_status().unwrap()["active_connections"], 0);
            assert!(StdUdpSocket::bind(relay).is_ok());
            core.stop();
        }
    }
}

#[test]
fn shared_connection_budget_covers_local_and_lan_sessions() {
    let peer = Peer::new(b'A');
    let mut candidate = config(vec![peer.node(A)], A);
    candidate.limits.max_connections = 1;
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let mut local = stream(core.address());
    local.write_all(b"CONNECT target.fixture.invalid:80 HTTP/1.1\r\nHost: target.fixture.invalid:80\r\n\r\n").unwrap();
    assert!(header(&mut local).unwrap().starts_with(b"HTTP/1.1 200"));
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let mut excess = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    let mut byte = [0];
    assert!(excess.read(&mut byte).map_or(true, |count| count == 0));
    wait(|| core.lan_status().unwrap()["last_error"] == "CoreConnectionLimit");
    exchange(&mut local, b'A');
    drop(local);
    wait(|| core.shared.active.load(Ordering::Relaxed) == 0);
    let (mut admitted, response) = http_connect(&lan, true, "target.fixture.invalid");
    assert!(response.starts_with(b"HTTP/1.1 200"));
    exchange(&mut admitted, b'A');
    drop(admitted);
    core.stop();
}

struct DnsPeer {
    address: SocketAddr,
    queries: Arc<AtomicUsize>,
    stop: Arc<AtomicBool>,
    task: Option<thread::JoinHandle<()>>,
}

impl DnsPeer {
    fn new(answers: Vec<std::net::Ipv4Addr>) -> Self {
        let socket = StdUdpSocket::bind("127.0.0.1:0").unwrap();
        socket
            .set_read_timeout(Some(Duration::from_millis(50)))
            .unwrap();
        let address = socket.local_addr().unwrap();
        let queries = Arc::new(AtomicUsize::new(0));
        let stop = Arc::new(AtomicBool::new(false));
        let task = thread::spawn({
            let queries = queries.clone();
            let stop = stop.clone();
            move || {
                while !stop.load(Ordering::Acquire) {
                    let mut query = [0; 2048];
                    let (length, peer) = match socket.recv_from(&mut query) {
                        Ok(received) => received,
                        Err(error)
                            if matches!(
                                error.kind(),
                                std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                            ) =>
                        {
                            continue;
                        }
                        Err(error) => panic!("DNS fixture receive: {error}"),
                    };
                    assert!(length >= 17);
                    let mut end = 12;
                    while query[end] != 0 {
                        end += 1 + usize::from(query[end]);
                        assert!(end < length);
                    }
                    end += 5;
                    assert!(end <= length);
                    assert_eq!(&query[end - 4..end], &[0, 1, 0, 1]);
                    let index = queries.fetch_add(1, Ordering::AcqRel);
                    let answer = answers[index.min(answers.len() - 1)];
                    let mut reply = query[..end].to_vec();
                    reply[2..12].copy_from_slice(&[0x81, 0x80, 0, 1, 0, 1, 0, 0, 0, 0]);
                    // TTL=0 deliberately prevents a cache hit masking a second
                    // DNS resolution between address validation and dialing.
                    reply.extend([0xc0, 0x0c, 0, 1, 0, 1, 0, 0, 0, 0, 0, 4]);
                    reply.extend(answer.octets());
                    socket.send_to(&reply, peer).unwrap();
                }
            }
        });
        Self {
            address,
            queries,
            stop,
            task: Some(task),
        }
    }

    fn configure(&self, runtime: &mut RuntimeConfig) {
        runtime.dns.servers = vec![self.address];
        runtime.dns.tls_servers.clear();
        runtime.dns.use_system_hosts = false;
        runtime.dns.query_family = swirl_subscription::DnsQueryFamily::Ipv4Only;
    }
}

impl Drop for DnsPeer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(task) = self.task.take() {
            task.join().unwrap();
        }
    }
}

#[test]
fn real_dns_rebinding_is_rechecked_before_each_direct_connection() {
    let origin = StdListener::bind("127.0.0.1:0").unwrap();
    let destination = origin.local_addr().unwrap();
    let origin_task = thread::spawn(move || {
        let (mut client, _) = origin.accept().unwrap();
        client
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        let mut bytes = [0; 4];
        client.read_exact(&mut bytes).unwrap();
        assert_eq!(&bytes, b"ping");
        client.write_all(b"pong").unwrap();
    });
    let dns = DnsPeer::new(vec![
        "127.0.0.1".parse().unwrap(),
        "127.0.0.3".parse().unwrap(),
    ]);
    let unused = Peer::new(b'A');
    let mut candidate = config(vec![unused.node(A)], A);
    candidate.policy.mode = Mode::Direct;
    dns.configure(&mut candidate);
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    core.lan
        .as_ref()
        .unwrap()
        .state
        .fixture_targets
        .lock()
        .unwrap()
        .insert(destination);
    let auth = STANDARD.encode(format!("{}:{}", lan.auth.username, lan.auth.password));
    let request = format!(
        "CONNECT rebinding.fixture.invalid:{} HTTP/1.1\r\nHost: rebinding.fixture.invalid:{}\r\nProxy-Authorization: Basic {auth}\r\n\r\n",
        destination.port(),
        destination.port()
    );
    let mut first = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    first.write_all(request.as_bytes()).unwrap();
    assert!(header(&mut first).unwrap().starts_with(b"HTTP/1.1 200"));
    first.write_all(b"ping").unwrap();
    let mut bytes = [0; 4];
    first.read_exact(&mut bytes).unwrap();
    assert_eq!(&bytes, b"pong");
    origin_task.join().unwrap();
    drop(first);
    let mut second = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    second.write_all(request.as_bytes()).unwrap();
    assert!(!header(&mut second).unwrap().starts_with(b"HTTP/1.1 200"));
    wait(|| core.lan_status().unwrap()["last_error"] == "LanHostAccessDenied");
    assert_eq!(dns.queries.load(Ordering::Acquire), 2);
    assert_eq!(unused.requests.load(Ordering::Relaxed), 0);
    drop(second);
    core.stop();
}

#[test]
fn upstream_dns_validation_and_native_dial_use_the_same_frozen_answers() {
    let peer = Peer::new(b'A');
    let dns = DnsPeer::new(vec![
        "127.0.0.1".parse().unwrap(),
        "127.0.0.3".parse().unwrap(),
    ]);
    let mut upstream = peer.node(A);
    if let Outbound::HttpConnect { host, .. } = &mut upstream.outbound {
        *host = "upstream.fixture.invalid".into();
    }
    let mut candidate = config(vec![upstream], A);
    dns.configure(&mut candidate);
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let (mut client, response) = http_connect(&lan, true, "remote-dns-target.fixture.invalid");
    assert!(response.starts_with(b"HTTP/1.1 200"));
    exchange(&mut client, b'A');
    assert_eq!(dns.queries.load(Ordering::Acquire), 1);
    assert_eq!(peer.requests.load(Ordering::Relaxed), 1);
    drop(client);
    core.stop();
}

#[test]
fn slow_handshake_and_malformed_requests_release_admission_without_outbound() {
    let peer = Peer::new(b'A');
    let mut candidate = config(vec![peer.node(A)], A);
    candidate.limits.handshake_timeout_ms = 250;
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let mut slow = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    slow.write_all(b"CONNECT ").unwrap();
    let mut bytes = [0; 128];
    assert!(slow.read(&mut bytes).map_or(true, |count| count == 0));
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    assert_eq!(core.lan_status().unwrap()["last_error"], "HandshakeTimeout");
    let mut malformed = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    malformed.write_all(b"GET http://target.fixture.invalid/ HTTP/1.1\r\nHost: target.fixture.invalid\r\nContent-Length: 3\r\nTransfer-Encoding: chunked\r\n\r\n").unwrap();
    assert!(header(&mut malformed).unwrap().starts_with(b"HTTP/1.1 400"));
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    assert_eq!(peer.requests.load(Ordering::Relaxed), 0);
    assert_eq!(core.shared.connection_slots.available_permits(), 128);
    drop(malformed);
    drop(slow);
    core.stop();
}

fn contiguous_udp_pair(ip: IpAddr) -> (u16, u16) {
    for _ in 0..128 {
        let first = StdUdpSocket::bind(SocketAddr::new(ip, 0)).unwrap();
        let port = first.local_addr().unwrap().port();
        let Some(next) = port.checked_add(1) else {
            continue;
        };
        if let Ok(_second) = StdUdpSocket::bind(SocketAddr::new(ip, next)) {
            return (port, next);
        }
    }
    panic!("no free adjacent UDP fixture ports");
}

fn source_bound_stream(address: SocketAddr, ip: IpAddr) -> StdStream {
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let stream = runtime.block_on(async {
        let socket = tokio::net::TcpSocket::new_v4().unwrap();
        socket.bind(SocketAddr::new(ip, 0)).unwrap();
        timeout(Duration::from_secs(3), socket.connect(address))
            .await
            .unwrap()
            .unwrap()
            .into_std()
            .unwrap()
    });
    stream.set_nonblocking(false).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    stream
        .set_write_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    stream
}

#[test]
fn simultaneous_udp_clients_have_distinct_relays_and_cannot_cross_associations() {
    let origin = StdUdpSocket::bind("127.0.0.1:0").unwrap();
    let destination = origin.local_addr().unwrap();
    origin
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let received = Arc::new(AtomicUsize::new(0));
    let worker = thread::spawn({
        let received = received.clone();
        move || {
            for expected in [b"client-A", b"client-B"] {
                let mut bytes = [0; 128];
                let (length, source) = origin.recv_from(&mut bytes).unwrap();
                assert_eq!(&bytes[..length], expected);
                received.fetch_add(1, Ordering::Release);
                origin.send_to(&bytes[..length], source).unwrap();
            }
        }
    });
    let unused = Peer::new(b'A');
    let mut candidate = config(vec![unused.node(A)], A);
    candidate.policy.mode = Mode::Direct;
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let mut lan = lan_config(false);
    (lan.udp_port_start, lan.udp_port_end) = contiguous_udp_pair(lan.listen_ip);
    start_fixture(&mut core, &lan);
    core.lan
        .as_ref()
        .unwrap()
        .state
        .fixture_targets
        .lock()
        .unwrap()
        .insert(destination);
    let client_ips = if cfg!(target_os = "macos") {
        ["127.0.0.1", "127.0.0.1"]
    } else {
        ["127.0.0.3", "127.0.0.4"]
    };
    let mut associations = Vec::new();
    for (index, ip) in client_ips.iter().enumerate() {
        let ip: IpAddr = ip.parse().unwrap();
        let stream = source_bound_stream(SocketAddr::new(lan.listen_ip, lan.socks_port), ip);
        let (mut control, authenticated) = socks_auth_stream(stream, &lan, &lan.auth.password);
        assert_eq!(authenticated, [1, 0]);
        let client = StdUdpSocket::bind(SocketAddr::new(ip, 0)).unwrap();
        client
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        let mut request = vec![5, 3, 0, 1, 0, 0, 0, 0];
        request.extend(client.local_addr().unwrap().port().to_be_bytes());
        control.write_all(&request).unwrap();
        let mut response = [0; 10];
        control.read_exact(&mut response).unwrap();
        assert_eq!(response[1], 0);
        let relay = SocketAddr::new(
            lan.listen_ip,
            u16::from_be_bytes([response[8], response[9]]),
        );
        let mut packet = vec![0, 0, 0];
        NetworkTarget {
            host: destination.ip().to_string(),
            port: destination.port(),
        }
        .encode(&mut packet)
        .unwrap();
        packet.extend(if index == 0 { b"client-A" } else { b"client-B" });
        client.send_to(&packet, relay).unwrap();
        let mut reply = [0; 128];
        let (length, source) = client.recv_from(&mut reply).unwrap();
        assert_eq!(source, relay);
        assert_eq!(&reply[..length], packet);
        associations.push((control, client, relay, packet));
    }
    assert_ne!(associations[0].2, associations[1].2);
    worker.join().unwrap();
    let (_, first, _, packet) = &associations[0];
    first
        .set_read_timeout(Some(Duration::from_millis(100)))
        .unwrap();
    first.send_to(packet, associations[1].2).unwrap();
    let mut bytes = [0; 128];
    assert!(first.recv_from(&mut bytes).is_err());
    assert_eq!(received.load(Ordering::Acquire), 2);
    assert_eq!(core.lan_status().unwrap()["active_connections"], 2);
    let relays = [associations[0].2, associations[1].2];
    drop(associations);
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    assert_eq!(core.lan_status().unwrap()["uploaded"], 16);
    assert_eq!(core.lan_status().unwrap()["downloaded"], 16);
    for relay in relays {
        assert!(StdUdpSocket::bind(relay).is_ok());
    }
    core.stop();
}

#[test]
fn lan_and_native_tun_share_admission_and_stopping_lan_preserves_native_flow() {
    let peer = Peer::new(b'A');
    let mut candidate = config(vec![peer.node(A)], A);
    candidate.limits.max_connections = 1;
    candidate
        .dns
        .tls_servers
        .push(swirl_subscription::DnsTlsServer {
            address: "192.0.2.1:853".parse().unwrap(),
            tls: swirl_subscription::Tls {
                server_name: "dns.fixture.invalid".into(),
                alpn: vec![],
                ca_der_base64: None,
            },
            https_path: None,
        });
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let (mut local_client, response) = http_connect(&lan, true, "target.fixture.invalid");
    assert!(response.starts_with(b"HTTP/1.1 200"));
    exchange(&mut local_client, b'A');
    let dispatcher = core.flow_dispatcher().unwrap();
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap();
    runtime.block_on(async {
        assert_eq!(
            dispatcher
                .open_udp(
                    "192.168.77.12:50000".parse().unwrap(),
                    NetworkTarget {
                        host: "203.0.113.8".into(),
                        port: 443,
                    }
                )
                .await
                .err(),
            Some("ConnectionLimit")
        );
    });
    drop(local_client);
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    let (mut client, inbound) = tokio::io::duplex(64);
    let native = runtime.spawn(async move {
        dispatcher
            .relay_tcp(
                inbound,
                "192.168.77.12:50000".parse().unwrap(),
                NetworkTarget {
                    host: "target.fixture.invalid".into(),
                    port: 443,
                },
            )
            .await
    });
    runtime.block_on(async {
        client.write_all(b"ping").await.unwrap();
        let mut response = [0; 5];
        timeout(Duration::from_secs(3), client.read_exact(&mut response))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(&response, b"Aping");
    });
    let mut rejected = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    let mut byte = [0];
    assert!(rejected.read(&mut byte).map_or(true, |count| count == 0));
    core.lan_stop().unwrap();
    runtime.block_on(async {
        client.write_all(b"pong").await.unwrap();
        let mut response = [0; 5];
        timeout(Duration::from_secs(3), client.read_exact(&mut response))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(&response, b"Apong");
        client.shutdown().await.unwrap();
        native.await.unwrap().unwrap();
    });
    wait(|| core.shared.active.load(Ordering::Acquire) == 0);
    assert_eq!(core.shared.connection_slots.available_permits(), 1);
    core.stop();
}
