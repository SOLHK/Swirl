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
        dns: Dns {
            // Most fixtures exercise ingress, routing and session lifetime.
            // Give their synthetic target an explicit policy-owned address;
            // unresolved proxy domains have dedicated encrypted-DNS tests.
            hosts: vec![swirl_subscription::HostMapping {
                name: "target.fixture.invalid".into(),
                address: "203.0.113.80".parse().unwrap(),
            }],
            ..Dns::default()
        },
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

fn start_strict_fixture(core: &mut Core, config: &LanConfig, endpoints: &[SocketAddr]) {
    config.validate_common().unwrap();
    core.lan = Some(
        LanRuntime::start_bound(
            core.runtime.as_ref().unwrap(),
            core.shared.clone(),
            config.clone(),
            Access::StrictLoopbackFixture,
        )
        .unwrap(),
    );
    core.lan
        .as_ref()
        .unwrap()
        .state
        .fixture_targets
        .lock()
        .unwrap()
        .extend(endpoints.iter().copied());
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
        Self::with_ttl(answers, 0)
    }

    fn with_ttl(answers: Vec<std::net::Ipv4Addr>, ttl: u32) -> Self {
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
                    // Default TTL=0 exposes validation/dial re-resolution;
                    // cache-preservation cases explicitly opt into a lifetime.
                    reply.extend([0xc0, 0x0c, 0, 1, 0, 1]);
                    reply.extend(ttl.to_be_bytes());
                    reply.extend([0, 4]);
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

/// A real HTTP proxy carries a verified DoT exchange inside its first CONNECT.
/// The declared DNS address is also watched by a separate listening socket:
/// neither target queries nor TLS are allowed to bypass the selected proxy.
struct EncryptedDnsProxy {
    address: SocketAddr,
    direct_dns: StdListener,
    trust: String,
    accepted: Arc<AtomicUsize>,
    queries: Arc<AtomicUsize>,
    targets: Arc<Mutex<Vec<String>>>,
    application_headers: Arc<Mutex<Vec<String>>>,
    stop: Arc<AtomicBool>,
    task: Option<thread::JoinHandle<()>>,
}

impl EncryptedDnsProxy {
    fn new(answers: Vec<std::net::Ipv4Addr>, malformed: bool) -> Self {
        Self::with_ttl(answers, malformed, 0)
    }

    fn with_ttl(answers: Vec<std::net::Ipv4Addr>, malformed: bool, ttl: u32) -> Self {
        use tokio_rustls::rustls::{
            ServerConfig,
            pki_types::{CertificateDer, PrivatePkcs8KeyDer},
        };
        let fixture: Value = serde_json::from_str(include_str!(
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
        let server = Arc::new(
            ServerConfig::builder()
                .with_no_client_auth()
                .with_single_cert(
                    vec![CertificateDer::from(der.clone())],
                    PrivatePkcs8KeyDer::from(hex("ed25519_pkcs8_der_hex")).into(),
                )
                .unwrap(),
        );
        let listener = StdListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let direct_dns = StdListener::bind("127.0.0.1:0").unwrap();
        direct_dns.set_nonblocking(true).unwrap();
        let dns_target = direct_dns.local_addr().unwrap().to_string();
        let accepted = Arc::new(AtomicUsize::new(0));
        let queries = Arc::new(AtomicUsize::new(0));
        let targets = Arc::new(Mutex::new(Vec::new()));
        let application_headers = Arc::new(Mutex::new(Vec::new()));
        let stop = Arc::new(AtomicBool::new(false));
        let task = thread::spawn({
            let accepted = accepted.clone();
            let queries = queries.clone();
            let targets = targets.clone();
            let application_headers = application_headers.clone();
            let stop = stop.clone();
            move || {
                let mut workers = Vec::new();
                while !stop.load(Ordering::Acquire) {
                    let (mut socket, _) = match listener.accept() {
                        Ok(value) => value,
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            thread::sleep(Duration::from_millis(5));
                            continue;
                        }
                        Err(error) => panic!("encrypted proxy accept: {error}"),
                    };
                    accepted.fetch_add(1, Ordering::AcqRel);
                    let server = server.clone();
                    let dns_target = dns_target.clone();
                    let answers = answers.clone();
                    let queries = queries.clone();
                    let targets = targets.clone();
                    let application_headers = application_headers.clone();
                    workers.push(thread::spawn(move || {
                        use tokio_rustls::rustls::{ServerConnection, StreamOwned};
                        socket.set_nonblocking(false).unwrap();
                        socket.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
                        socket.set_write_timeout(Some(Duration::from_secs(3))).unwrap();
                        let Ok(request) = header(&mut socket) else { return; };
                        let request = String::from_utf8(request).unwrap();
                        let mut words = request.split_ascii_whitespace();
                        assert_eq!(words.next(), Some("CONNECT"));
                        let target = words.next().unwrap().to_owned();
                        socket.write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n").unwrap();
                        if target == dns_target {
                            let mut tls = StreamOwned::new(ServerConnection::new(server).unwrap(), socket);
                            let mut length = [0; 2];
                            let Ok(()) = tls.read_exact(&mut length) else { return; };
                            let mut query = vec![0; usize::from(u16::from_be_bytes(length))];
                            assert!((17..=4096).contains(&query.len()));
                            tls.read_exact(&mut query).unwrap();
                            assert_eq!(&query[query.len() - 4..], &[0, 1, 0, 1]);
                            queries.fetch_add(1, Ordering::AcqRel);
                            let mut reply = query;
                            reply[2..4].copy_from_slice(&[0x81, 0x80]);
                            reply[6..8].copy_from_slice(&(answers.len() as u16).to_be_bytes());
                            for answer in answers {
                                // Default zero TTL exposes a second lookup;
                                // the classification cache test opts into 60s.
                                reply.extend([0xc0, 0x0c, 0, 1, 0, 1]);
                                reply.extend(ttl.to_be_bytes());
                                reply.extend([0, 4]);
                                reply.extend(answer.octets());
                            }
                            if malformed { reply[0] ^= 1; }
                            tls.write_all(&(reply.len() as u16).to_be_bytes()).unwrap();
                            tls.write_all(&reply).unwrap();
                            tls.flush().unwrap();
                            tls.conn.send_close_notify();
                            let _ = tls.flush();
                            return;
                        }
                        targets.lock().unwrap().push(target);
                        let mut first = [0; 4];
                        if socket.read_exact(&mut first).is_err() { return; }
                        if first == *b"GET " {
                            let Ok(rest) = header(&mut socket) else { return; };
                            application_headers.lock().unwrap().push(String::from_utf8(rest).unwrap());
                            let _ = socket.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\nokay");
                        } else {
                            assert_eq!(&first, b"ping");
                            let _ = socket.write_all(b"Pping");
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
            direct_dns,
            trust: STANDARD.encode(der),
            accepted,
            queries,
            targets,
            application_headers,
            stop,
            task: Some(task),
        }
    }

    fn config(&self) -> RuntimeConfig {
        let mut runtime = config(
            vec![Node {
                id: A.into(),
                outbound: Outbound::HttpConnect {
                    host: self.address.ip().to_string(),
                    port: self.address.port(),
                    auth: None,
                    tls: None,
                },
            }],
            A,
        );
        runtime.dns.servers.clear();
        runtime.dns.query_family = swirl_subscription::DnsQueryFamily::Ipv4Only;
        runtime.dns.use_system_hosts = false;
        runtime.dns.tls_servers = vec![swirl_subscription::DnsTlsServer {
            address: self.direct_dns.local_addr().unwrap(),
            tls: swirl_subscription::Tls {
                server_name: "reality.test".into(),
                alpn: vec![],
                ca_der_base64: Some(self.trust.clone()),
            },
            https_path: None,
        }];
        runtime
    }

    fn assert_no_direct_dns(&self) {
        assert_eq!(
            self.direct_dns.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
    }
}

impl Drop for EncryptedDnsProxy {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(task) = self.task.take() {
            task.join().unwrap();
        }
    }
}

#[test]
fn proxy_domain_without_authorized_dns_never_reaches_proxy_or_plaintext_dns() {
    let peer = Peer::new(b'A');
    let dns = DnsPeer::new(vec!["127.0.0.1".parse().unwrap()]);
    let mut candidate = config(vec![peer.node(A)], A);
    dns.configure(&mut candidate);
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let (client, response) = http_connect(&lan, true, "unresolved-protected.fixture.invalid");
    assert!(!response.starts_with(b"HTTP/1.1 200"));
    wait(|| core.lan_status().unwrap()["last_error"] == "LanTargetDnsPolicyRequired");
    assert_eq!(peer.requests.load(Ordering::Acquire), 0);
    assert_eq!(dns.queries.load(Ordering::Acquire), 0);
    drop(client);
    core.stop();
}

#[test]
fn udp_proxy_domain_without_authorized_dns_cannot_open_an_upstream_association() {
    let upstream = StdListener::bind("127.0.0.1:0").unwrap();
    upstream.set_nonblocking(true).unwrap();
    let address = upstream.local_addr().unwrap();
    let dns = DnsPeer::new(vec!["127.0.0.1".parse().unwrap()]);
    let mut candidate = config(
        vec![Node {
            id: A.into(),
            outbound: Outbound::Socks5 {
                host: address.ip().to_string(),
                port: address.port(),
                auth: None,
                tls: None,
                udp: true,
            },
        }],
        A,
    );
    dns.configure(&mut candidate);
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let (mut control, authenticated) = socks_auth(&lan, &lan.auth.password);
    assert_eq!(authenticated, [1, 0]);
    let client =
        StdUdpSocket::bind(SocketAddr::new(control.local_addr().unwrap().ip(), 0)).unwrap();
    client
        .set_read_timeout(Some(Duration::from_millis(150)))
        .unwrap();
    let mut request = vec![5, 3, 0, 1, 0, 0, 0, 0];
    request.extend(client.local_addr().unwrap().port().to_be_bytes());
    control.write_all(&request).unwrap();
    let mut response = [0; 10];
    control.read_exact(&mut response).unwrap();
    assert_eq!(&response[..4], &[5, 0, 0, 1]);
    let relay = SocketAddr::new(
        lan.listen_ip,
        u16::from_be_bytes([response[8], response[9]]),
    );
    let host = b"udp-protected.fixture.invalid";
    let mut datagram = vec![0, 0, 0, 3, host.len() as u8];
    datagram.extend(host);
    datagram.extend(443u16.to_be_bytes());
    datagram.extend(b"private-udp");
    client.send_to(&datagram, relay).unwrap();
    wait(|| core.shared.totals.udp_dropped.load(Ordering::Relaxed) > 0);
    assert_eq!(
        core.lan_status().unwrap()["last_error"],
        "LanTargetDnsPolicyRequired"
    );
    assert!(client.recv_from(&mut [0; 512]).is_err());
    assert_eq!(
        upstream.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
    assert_eq!(dns.queries.load(Ordering::Acquire), 0);
    drop(control);
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    core.stop();
}

#[test]
fn proxy_target_uses_verified_dns_over_selected_node_then_only_the_pinned_ip() {
    let proxy = EncryptedDnsProxy::new(vec!["203.0.113.80".parse().unwrap()], false);
    let mut core = Core::start(proxy.config(), STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_fixture(&mut core, &lan);
    let (mut client, response) = http_connect(&lan, true, "encrypted-target.fixture.invalid");
    assert!(response.starts_with(b"HTTP/1.1 200"), "{response:?}");
    exchange(&mut client, b'P');
    drop(client);
    let mut forward = stream(SocketAddr::new(lan.listen_ip, lan.http_port));
    let auth = STANDARD.encode(format!("{}:{}", lan.auth.username, lan.auth.password));
    forward.write_all(format!("GET http://encrypted-target.fixture.invalid/original HTTP/1.1\r\nHost: encrypted-target.fixture.invalid\r\nProxy-Authorization: Basic {auth}\r\n\r\n").as_bytes()).unwrap();
    assert!(header(&mut forward).unwrap().starts_with(b"HTTP/1.1 200"));
    let mut body = [0; 4];
    forward.read_exact(&mut body).unwrap();
    assert_eq!(&body, b"okay");
    assert_eq!(
        *proxy.targets.lock().unwrap(),
        vec!["203.0.113.80:80", "203.0.113.80:80"]
    );
    assert_eq!(
        proxy.queries.load(Ordering::Acquire),
        2,
        "TTL zero must not hide target re-resolution"
    );
    let headers = proxy.application_headers.lock().unwrap();
    assert_eq!(headers.len(), 1);
    assert!(headers[0].contains("Host: encrypted-target.fixture.invalid\r\n"));
    assert!(
        !headers[0]
            .to_ascii_lowercase()
            .contains("proxy-authorization")
    );
    drop(headers);
    let records = core.shared.records.lock().unwrap();
    assert!(records.values().any(|record| record.ingress == "lan"
        && record.target.host == "encrypted-target.fixture.invalid"
        && record.trace["chosen_ip"] == "203.0.113.80"
        && record.trace["dns_path"] == "configured_encrypted_via_selected_outbound"));
    drop(records);
    proxy.assert_no_direct_dns();
    drop(forward);
    core.stop();
}

#[test]
fn proxy_domain_rebinding_and_malformed_encrypted_dns_cannot_delegate_a_target() {
    let protected: std::net::Ipv4Addr = "203.0.113.42".parse().unwrap();
    for (answers, malformed) in [
        (vec![protected], false),
        (vec!["203.0.113.80".parse().unwrap(), protected], false),
        (vec!["203.0.113.80".parse().unwrap()], true),
    ] {
        let proxy = EncryptedDnsProxy::new(answers, malformed);
        let mut core = Core::start(proxy.config(), STORE.into(), 1, START.into()).unwrap();
        let mut lan = lan_config(false);
        // A multihomed host may own a public address. Private-hop blocking
        // alone cannot protect this management endpoint from a remote proxy.
        lan.host_addresses.push(protected.into());
        start_fixture(&mut core, &lan);
        let (client, response) = http_connect(&lan, true, "attacker-rebinding.fixture.invalid");
        assert!(!response.starts_with(b"HTTP/1.1 200"));
        wait(|| core.lan_status().unwrap()["active_connections"] == 0);
        if !malformed {
            assert_eq!(
                core.lan_status().unwrap()["last_error"],
                "LanHostAccessDenied"
            );
        }
        assert_eq!(proxy.queries.load(Ordering::Acquire), 1);
        assert!(
            proxy.targets.lock().unwrap().is_empty(),
            "proxy must never receive a forbidden target"
        );
        assert_eq!(
            proxy.accepted.load(Ordering::Acquire),
            1,
            "only the approved encrypted DNS stream may open"
        );
        proxy.assert_no_direct_dns();
        drop(client);
        core.stop();
    }
}

fn require_rule_dns(candidate: &mut RuntimeConfig) {
    candidate.policy.mode = Mode::Rule;
    candidate
        .policy
        .explicit_direct_rules
        .push(swirl_subscription::v2::PolicyRule {
            id: "60000000-0000-4000-8000-000000000009".into(),
            name: "configured DNS boundary fixture".into(),
            enabled: true,
            priority: 1,
            matcher: swirl_subscription::Matcher::Cidr {
                value: "198.51.100.0/24".parse().unwrap(),
                resolve: true,
            },
            target: Target::Direct {},
        });
}

#[test]
fn configured_dns_guard_precedes_direct_mandatory_rule_and_proxy_bootstrap_io() {
    for protocol in ["udp", "dot", "doh"] {
        for path in ["direct", "mandatory", "bootstrap"] {
            let proxy = EncryptedDnsProxy::new(vec!["203.0.113.80".parse().unwrap()], false);
            let dns = DnsPeer::new(vec!["203.0.113.80".parse().unwrap()]);
            let mut candidate = proxy.config();
            match protocol {
                "udp" => dns.configure(&mut candidate),
                "doh" => candidate.dns.tls_servers[0].https_path = Some("/dns-query".into()),
                _ => {}
            }
            match path {
                "direct" => candidate.policy.mode = Mode::Direct,
                "mandatory" => require_rule_dns(&mut candidate),
                "bootstrap" => {
                    let Outbound::HttpConnect { host, .. } = &mut candidate.nodes[0].outbound
                    else {
                        unreachable!();
                    };
                    *host = "guarded-bootstrap.fixture.invalid".into();
                }
                _ => unreachable!(),
            }
            let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
            let lan = lan_config(false);
            start_strict_fixture(&mut core, &lan, &[proxy.address]);
            let host = if path == "bootstrap" {
                "target.fixture.invalid"
            } else {
                "configured-dns.fixture.invalid"
            };
            let (client, response) = http_connect(&lan, true, host);
            assert!(!response.starts_with(b"HTTP/1.1 200"), "{protocol}/{path}");
            wait(|| core.lan_status().unwrap()["active_connections"] == 0);
            assert_eq!(
                core.lan_status().unwrap()["last_error"],
                "DnsEndpointForbidden",
                "{protocol}/{path}"
            );
            assert_eq!(dns.queries.load(Ordering::Acquire), 0);
            assert_eq!(proxy.accepted.load(Ordering::Acquire), 0);
            assert_eq!(proxy.queries.load(Ordering::Acquire), 0);
            proxy.assert_no_direct_dns();
            drop(client);
            core.stop();
        }
    }
}

#[test]
fn permitted_configured_dns_keeps_mandatory_routing_bootstrap_and_shared_cache() {
    for bootstrap in [false, true] {
        let peer = Peer::new(b'A');
        let address = if bootstrap {
            "127.0.0.1"
        } else {
            "203.0.113.80"
        };
        let dns = DnsPeer::with_ttl(vec![address.parse().unwrap()], 60);
        let mut candidate = config(vec![peer.node(A)], A);
        dns.configure(&mut candidate);
        if bootstrap {
            let Outbound::HttpConnect { host, .. } = &mut candidate.nodes[0].outbound else {
                unreachable!();
            };
            *host = "permitted-bootstrap.fixture.invalid".into();
        } else {
            require_rule_dns(&mut candidate);
        }
        let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
        let lan = lan_config(false);
        start_strict_fixture(&mut core, &lan, &[peer.address, dns.address]);
        let host = if bootstrap {
            "target.fixture.invalid"
        } else {
            "permitted-rule.fixture.invalid"
        };
        for _ in 0..2 {
            let (mut client, response) = http_connect(&lan, true, host);
            assert!(response.starts_with(b"HTTP/1.1 200"), "{response:?}");
            exchange(&mut client, b'A');
        }
        wait(|| core.lan_status().unwrap()["active_connections"] == 0);
        assert_eq!(
            dns.queries.load(Ordering::Acquire),
            1,
            "the guarded view retains the original cache"
        );
        assert_eq!(peer.requests.load(Ordering::Acquire), 2);
        let records = core.shared.records.lock().unwrap();
        assert_eq!(records.len(), 2);
        assert!(
            records
                .values()
                .all(|record| record.node == A && record.trace["chosen_ip"] == "203.0.113.80")
        );
        drop(records);
        core.stop();
    }
}

#[test]
fn classification_cannot_dial_a_protected_default_proxy_before_lan_outbound_preparation() {
    for mapped_hostname in [false, true] {
        let proxy = EncryptedDnsProxy::new(vec!["203.0.113.80".parse().unwrap()], false);
        let mut candidate = proxy.config();
        candidate.policy.mode = Mode::Rule;
        candidate.policy.classification_dns = ClassificationDns::ViaDefaultPolicy;
        // An allowed DNS address isolates the selected physical proxy check.
        // Neither address is dialled because the protected proxy is denied.
        candidate.dns.tls_servers[0].address = "203.0.113.53:853".parse().unwrap();
        if mapped_hostname {
            let Outbound::HttpConnect { host, .. } = &mut candidate.nodes[0].outbound else {
                unreachable!();
            };
            *host = "protected-proxy.fixture.invalid".into();
            candidate.dns.hosts.push(swirl_subscription::HostMapping {
                name: host.clone(),
                address: proxy.address.ip(),
            });
        }
        let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
        let lan = lan_config(false);
        start_strict_fixture(&mut core, &lan, &[]);
        let (client, response) = http_connect(&lan, true, "classified-protected.fixture.invalid");
        assert!(!response.starts_with(b"HTTP/1.1 200"));
        wait(|| core.lan_status().unwrap()["active_connections"] == 0);
        assert_eq!(
            core.lan_status().unwrap()["last_error"],
            "ClassificationIngressDenied"
        );
        assert_eq!(proxy.accepted.load(Ordering::Acquire), 0);
        assert_eq!(proxy.queries.load(Ordering::Acquire), 0);
        proxy.assert_no_direct_dns();
        drop(client);
        core.stop();
    }
}

#[test]
fn classification_checks_dot_and_doh_endpoints_before_proxy_hostname_bootstrap() {
    for https_path in [None, Some("/dns-query".into())] {
        let proxy = EncryptedDnsProxy::new(vec!["203.0.113.80".parse().unwrap()], false);
        let mut candidate = proxy.config();
        candidate.policy.mode = Mode::Rule;
        candidate.policy.classification_dns = ClassificationDns::ViaDefaultPolicy;
        candidate.dns.tls_servers[0].https_path = https_path;
        let Outbound::HttpConnect { host, .. } = &mut candidate.nodes[0].outbound else {
            unreachable!();
        };
        *host = "unresolved-proxy.fixture.invalid".into();
        let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
        let lan = lan_config(false);
        // The selected proxy fixture would be allowed, but its hostname must
        // not bootstrap through the unapproved host-owned encrypted DNS socket.
        start_strict_fixture(&mut core, &lan, &[proxy.address]);
        let (client, response) = http_connect(&lan, true, "classified-dns-pivot.fixture.invalid");
        assert!(!response.starts_with(b"HTTP/1.1 200"));
        wait(|| core.lan_status().unwrap()["active_connections"] == 0);
        assert_eq!(
            core.lan_status().unwrap()["last_error"],
            "ClassificationIngressDenied"
        );
        assert_eq!(proxy.accepted.load(Ordering::Acquire), 0);
        assert_eq!(proxy.queries.load(Ordering::Acquire), 0);
        proxy.assert_no_direct_dns();
        drop(client);
        core.stop();
    }
}

#[test]
fn udp_classification_cannot_open_a_protected_default_proxy_after_authentication() {
    let proxy = EncryptedDnsProxy::new(vec!["203.0.113.80".parse().unwrap()], false);
    let mut candidate = proxy.config();
    candidate.policy.mode = Mode::Rule;
    candidate.policy.classification_dns = ClassificationDns::ViaDefaultPolicy;
    candidate.dns.tls_servers[0].address = "203.0.113.53:853".parse().unwrap();
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    start_strict_fixture(&mut core, &lan, &[]);
    let (mut control, authenticated) = socks_auth(&lan, &lan.auth.password);
    assert_eq!(authenticated, [1, 0]);
    let client =
        StdUdpSocket::bind(SocketAddr::new(control.local_addr().unwrap().ip(), 0)).unwrap();
    client
        .set_read_timeout(Some(Duration::from_millis(150)))
        .unwrap();
    let mut request = vec![5, 3, 0, 1, 0, 0, 0, 0];
    request.extend(client.local_addr().unwrap().port().to_be_bytes());
    control.write_all(&request).unwrap();
    let mut response = [0; 10];
    control.read_exact(&mut response).unwrap();
    assert_eq!(&response[..4], &[5, 0, 0, 1]);
    let relay = SocketAddr::new(
        lan.listen_ip,
        u16::from_be_bytes([response[8], response[9]]),
    );
    let host = b"udp-classification.fixture.invalid";
    let mut datagram = vec![0, 0, 0, 3, host.len() as u8];
    datagram.extend(host);
    datagram.extend(443u16.to_be_bytes());
    datagram.extend(b"blocked-classification");
    client.send_to(&datagram, relay).unwrap();
    wait(|| core.lan_status().unwrap()["last_error"] == "ClassificationIngressDenied");
    assert!(client.recv_from(&mut [0; 512]).is_err());
    assert_eq!(proxy.accepted.load(Ordering::Acquire), 0);
    assert_eq!(proxy.queries.load(Ordering::Acquire), 0);
    proxy.assert_no_direct_dns();
    drop(control);
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    core.stop();
}

#[test]
fn classification_keeps_selected_proxy_dns_cache_and_unused_nodes_for_authenticated_lan() {
    let proxy = EncryptedDnsProxy::with_ttl(vec!["203.0.113.80".parse().unwrap()], false, 60);
    let unused = Peer::new(b'B');
    let mut candidate = proxy.config();
    candidate.nodes.push(unused.node(B));
    candidate.policy.mode = Mode::Rule;
    candidate.policy.classification_dns = ClassificationDns::ViaDefaultPolicy;
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let lan = lan_config(false);
    // Only the actual selected node and its declared DNS socket are authorized
    // fixtures. An unrelated, unused loopback node must not invalidate routing.
    start_strict_fixture(
        &mut core,
        &lan,
        &[proxy.address, proxy.direct_dns.local_addr().unwrap()],
    );
    for _ in 0..2 {
        let (mut client, response) =
            http_connect(&lan, true, "classification-cache.fixture.invalid");
        assert!(response.starts_with(b"HTTP/1.1 200"), "{response:?}");
        exchange(&mut client, b'P');
    }
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    assert_eq!(
        proxy.queries.load(Ordering::Acquire),
        1,
        "classification keeps its existing cache"
    );
    assert_eq!(proxy.accepted.load(Ordering::Acquire), 3);
    assert_eq!(
        *proxy.targets.lock().unwrap(),
        vec!["203.0.113.80:80", "203.0.113.80:80"]
    );
    assert_eq!(unused.requests.load(Ordering::Acquire), 0);
    let records = core.shared.records.lock().unwrap();
    assert!(records.values().any(|record| record.ingress == "lan"
        && record.target.host == "classification-cache.fixture.invalid"
        && record.trace["leaf_node_id"] == A
        && record.trace["chosen_ip"] == "203.0.113.80"
        && record.trace["dns_profile"] == "classification"
        && record.trace["classification_dns_path"] == "via_default_policy"));
    drop(records);
    proxy.assert_no_direct_dns();
    core.stop();
}

#[test]
fn protected_dns_endpoint_is_rejected_before_opening_its_proxy_tunnel() {
    let proxy = EncryptedDnsProxy::new(vec!["203.0.113.80".parse().unwrap()], false);
    let protected: IpAddr = "203.0.113.42".parse().unwrap();
    let mut candidate = proxy.config();
    candidate.dns.tls_servers[0].address = SocketAddr::new(protected, 853);
    let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
    let mut lan = lan_config(false);
    lan.host_addresses.push(protected);
    start_fixture(&mut core, &lan);
    let (client, response) = http_connect(&lan, true, "dns-pivot.fixture.invalid");
    assert!(!response.starts_with(b"HTTP/1.1 200"));
    wait(|| core.lan_status().unwrap()["active_connections"] == 0);
    assert_eq!(proxy.accepted.load(Ordering::Acquire), 0);
    assert_eq!(proxy.queries.load(Ordering::Acquire), 0);
    assert!(proxy.targets.lock().unwrap().is_empty());
    proxy.assert_no_direct_dns();
    drop(client);
    core.stop();
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
    let (mut client, response) = http_connect(&lan, true, "target.fixture.invalid");
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
