use ring::digest::{SHA256, digest};
use serde_json::{Value, json};
use smoltcp::{
    phy::ChecksumCapabilities,
    wire::{
        IpProtocol, Ipv4Packet, Ipv4Repr, Ipv6Packet, Ipv6Repr, TcpControl, TcpPacket, TcpRepr,
        TcpSeqNumber, UdpPacket, UdpRepr,
    },
};
use std::{
    fs::{self, File, OpenOptions},
    io::{self, BufRead, BufReader, Read, Write},
    net::{IpAddr, Shutdown, SocketAddr, TcpListener, UdpSocket},
    path::{Component, PathBuf, Prefix},
    sync::mpsc::{self, Receiver, SyncSender},
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};
use swirl_core::native_tun_ipc::{PacketReader, PacketWriter};
use swirl_core::v2::RuntimeConfig;
use swirl_dns::tun::{DNS_IPV4, DNS_IPV6, FakeIpStore};
use swirl_platform::windows_restricted_worker::{DataPlaneChild, spawn_data_plane};
use swirl_subscription::{
    Dns, DnsTlsServer, HostMapping, Limits, Node, Outbound, Tls,
    v2::{ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, Mode, PolicyDocument, Target},
};

const WAIT: Duration = Duration::from_secs(15);
const MAX_LINE: usize = 1024 * 1024;
const MAX_LOG: usize = 4 * MAX_LINE;
const EPOCH: u64 = 1;
const STORE: &str = "a1000000-0000-4000-8000-000000000001";
const NODE: &str = "c1000000-0000-4000-8000-000000000001";
const REQUEST: &str = "b1000000-0000-4000-8000-000000000001";
const TCP_REPLY_BYTES: usize = 128 * 1024;

fn check(value: bool, message: &str) -> io::Result<()> {
    if value {
        Ok(())
    } else {
        Err(io::Error::other(message))
    }
}
fn hash(bytes: &[u8]) -> String {
    digest(&SHA256, bytes)
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}
fn receive<T>(receiver: &Receiver<io::Result<T>>, operation: &str) -> io::Result<T> {
    receiver
        .recv_timeout(WAIT)
        .map_err(|e| io::Error::new(io::ErrorKind::TimedOut, format!("{operation}: {e}")))?
}
fn join<T>(thread: JoinHandle<io::Result<T>>) -> io::Result<T> {
    let deadline = Instant::now() + WAIT;
    while !thread.is_finished() {
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "fixture IO thread did not finish after child cleanup",
            ));
        }
        thread::sleep(Duration::from_millis(5));
    }
    thread
        .join()
        .map_err(|_| io::Error::other("fixture IO thread panicked"))?
}

// Bound allocation before parsing. This reads a dedicated control pipe only;
// packet bytes always use the existing Core frame reader on a different pipe.
fn line(input: &mut impl BufRead) -> io::Result<Option<Vec<u8>>> {
    let mut bytes = Vec::new();
    let count = input
        .take((MAX_LINE + 1) as u64)
        .read_until(b'\n', &mut bytes)?;
    if count == 0 {
        return Ok(None);
    }
    check(
        count <= MAX_LINE && bytes.last() == Some(&b'\n'),
        "unbounded/truncated worker control line",
    )?;
    Ok(Some(bytes))
}

fn control_reader(
    file: File,
    path: PathBuf,
    sender: SyncSender<io::Result<Value>>,
) -> io::Result<()> {
    let mut input = BufReader::new(file);
    let mut log = OpenOptions::new().create_new(true).write(true).open(path)?;
    let mut total = 0;
    let result: io::Result<()> = (|| {
        while let Some(bytes) = line(&mut input)? {
            check(
                bytes.len() <= MAX_LOG - total,
                "worker stdout exceeded fixture total log bound",
            )?;
            total += bytes.len();
            log.write_all(&bytes)?;
            let value: Value = serde_json::from_slice(&bytes)?;
            if value.get("event").is_some() {
                check(
                    value["event"] == "heartbeat"
                        && value["packet_worker_schema"] == 1
                        && value["epoch"] == EPOCH,
                    "invalid worker heartbeat",
                )?;
                continue;
            }
            sender
                .try_send(Ok(value))
                .map_err(|_| io::Error::other("unexpected/excess worker replies"))?;
        }
        Ok(())
    })();
    if let Err(ref e) = result {
        let _ = sender.try_send(Err(io::Error::new(e.kind(), e.to_string())));
    }
    log.sync_all()?;
    result
}

fn writer(file: File, framed: bool, receiver: Receiver<Vec<u8>>) -> io::Result<()> {
    if framed {
        let mut output = PacketWriter::new(file, EPOCH, 1500)?;
        for packet in receiver {
            output.write_packet(&packet)?;
        }
    } else {
        let mut output = file;
        for bytes in receiver {
            output.write_all(&bytes)?;
            output.flush()?;
        }
    }
    Ok(())
}

struct Client {
    control: SyncSender<Vec<u8>>,
    replies: Receiver<io::Result<Value>>,
    packets: SyncSender<Vec<u8>>,
    received: Receiver<io::Result<Vec<u8>>>,
}
impl Client {
    fn send_packet(&self, mut bytes: Vec<u8>) -> io::Result<()> {
        let deadline = Instant::now() + WAIT;
        loop {
            match self.packets.try_send(bytes) {
                Ok(()) => return Ok(()),
                Err(mpsc::TrySendError::Disconnected(_)) => {
                    return Err(io::Error::other("worker packet queue disconnected"));
                }
                Err(mpsc::TrySendError::Full(unsent)) => {
                    if Instant::now() >= deadline {
                        return Err(io::Error::new(
                            io::ErrorKind::TimedOut,
                            "worker packet queue backpressure exceeded deadline",
                        ));
                    }
                    bytes = unsent;
                    thread::sleep(Duration::from_millis(1));
                }
            }
        }
    }
    fn rpc(&self, command: Value) -> io::Result<Value> {
        let mut bytes = serde_json::to_vec(
            &json!({"packet_worker_schema":1,"request_id":REQUEST,"epoch":EPOCH,"command":command}),
        )?;
        bytes.push(b'\n');
        check(bytes.len() <= MAX_LINE, "fixture command exceeded bound")?;
        self.control
            .try_send(bytes)
            .map_err(|_| io::Error::other("worker control queue unavailable"))?;
        let reply = receive(&self.replies, "worker control response")?;
        check(
            reply["packet_worker_schema"] == 1
                && reply["request_id"] == REQUEST
                && reply["epoch"] == EPOCH
                && reply["ok"] == true,
            &format!("worker rejected command: {reply}"),
        )?;
        Ok(reply["result"].clone())
    }
    fn udp(
        &self,
        source: SocketAddr,
        destination: SocketAddr,
        payload: &[u8],
    ) -> io::Result<Vec<u8>> {
        self.send_packet(udp_packet(source, destination, payload)?)?;
        let reply = receive(&self.received, "worker UDP response")?;
        let (from, to, bytes) = udp_payload(&reply)?;
        check(
            (from, to) == (destination, source),
            "worker UDP response tuple differs",
        )?;
        Ok(bytes.to_vec())
    }
}

fn ip_packet(
    src: IpAddr,
    dst: IpAddr,
    protocol: IpProtocol,
    payload: &[u8],
) -> io::Result<Vec<u8>> {
    let header = if src.is_ipv4() { 20 } else { 40 };
    let mut bytes = vec![0; header + payload.len()];
    match (src, dst) {
        (IpAddr::V4(src_addr), IpAddr::V4(dst_addr)) => Ipv4Repr {
            src_addr,
            dst_addr,
            next_header: protocol,
            payload_len: payload.len(),
            hop_limit: 64,
        }
        .emit(
            &mut Ipv4Packet::new_unchecked(&mut bytes[..]),
            &ChecksumCapabilities::default(),
        ),
        (IpAddr::V6(src_addr), IpAddr::V6(dst_addr)) => Ipv6Repr {
            src_addr,
            dst_addr,
            next_header: protocol,
            payload_len: payload.len(),
            hop_limit: 64,
        }
        .emit(&mut Ipv6Packet::new_unchecked(&mut bytes[..])),
        _ => return Err(io::Error::other("fixture IP families differ")),
    }
    bytes[header..].copy_from_slice(payload);
    Ok(bytes)
}
fn udp_packet(src: SocketAddr, dst: SocketAddr, payload: &[u8]) -> io::Result<Vec<u8>> {
    let mut udp = vec![0; 8 + payload.len()];
    UdpRepr {
        src_port: src.port(),
        dst_port: dst.port(),
    }
    .emit(
        &mut UdpPacket::new_unchecked(&mut udp[..]),
        &src.ip().into(),
        &dst.ip().into(),
        payload.len(),
        |out| out.copy_from_slice(payload),
        &ChecksumCapabilities::default(),
    );
    ip_packet(src.ip(), dst.ip(), IpProtocol::Udp, &udp)
}
fn ip_payload(bytes: &[u8]) -> io::Result<(IpAddr, IpAddr, IpProtocol, &[u8])> {
    let (src, dst, protocol, payload) = match bytes.first().map(|b| b >> 4) {
        Some(4) => {
            let packet = Ipv4Packet::new_checked(bytes).map_err(io::Error::other)?;
            check(
                packet.verify_checksum() && packet.total_len() as usize == bytes.len(),
                "invalid returned IPv4 checksum/length",
            )?;
            (
                IpAddr::V4(packet.src_addr()),
                IpAddr::V4(packet.dst_addr()),
                packet.next_header(),
                packet.payload(),
            )
        }
        Some(6) => {
            let packet = Ipv6Packet::new_checked(bytes).map_err(io::Error::other)?;
            check(
                packet.payload_len() as usize + 40 == bytes.len(),
                "invalid returned IPv6 length",
            )?;
            (
                IpAddr::V6(packet.src_addr()),
                IpAddr::V6(packet.dst_addr()),
                packet.next_header(),
                packet.payload(),
            )
        }
        _ => return Err(io::Error::other("invalid returned IP packet")),
    };
    Ok((src, dst, protocol, payload))
}
fn udp_payload(bytes: &[u8]) -> io::Result<(SocketAddr, SocketAddr, &[u8])> {
    let (src, dst, protocol, payload) = ip_payload(bytes)?;
    check(
        protocol == IpProtocol::Udp,
        "unexpected non-UDP fixture packet",
    )?;
    let udp = UdpPacket::new_checked(payload).map_err(io::Error::other)?;
    let repr = UdpRepr::parse(
        &udp,
        &src.into(),
        &dst.into(),
        &ChecksumCapabilities::default(),
    )
    .map_err(io::Error::other)?;
    Ok((
        SocketAddr::new(src, repr.src_port),
        SocketAddr::new(dst, repr.dst_port),
        udp.payload(),
    ))
}

fn tcp_packet(
    src: SocketAddr,
    dst: SocketAddr,
    sequence: i32,
    ack: Option<i32>,
    control: TcpControl,
    payload: &[u8],
) -> io::Result<Vec<u8>> {
    let repr = TcpRepr {
        src_port: src.port(),
        dst_port: dst.port(),
        control,
        seq_number: TcpSeqNumber(sequence),
        ack_number: ack.map(TcpSeqNumber),
        window_len: 65535,
        window_scale: None,
        max_seg_size: (control == TcpControl::Syn).then_some(1400),
        sack_permitted: false,
        sack_ranges: [None; 3],
        timestamp: None,
        payload,
    };
    let mut bytes = vec![0; repr.buffer_len()];
    repr.emit(
        &mut TcpPacket::new_unchecked(&mut bytes[..]),
        &src.ip().into(),
        &dst.ip().into(),
        &ChecksumCapabilities::default(),
    );
    ip_packet(src.ip(), dst.ip(), IpProtocol::Tcp, &bytes)
}

fn tcp_roundtrip(client: &Client, v6: bool, fake: IpAddr) -> io::Result<()> {
    let listener = TcpListener::bind(if v6 { "[::1]:0" } else { "127.0.0.1:0" })?;
    listener.set_nonblocking(true)?;
    let endpoint = listener.local_addr()?;
    let peer = thread::spawn(move || {
        let deadline = Instant::now() + WAIT;
        let mut stream = loop {
            match listener.accept() {
                Ok((stream, _)) => break stream,
                Err(e) if e.kind() == io::ErrorKind::WouldBlock && Instant::now() < deadline => {
                    thread::sleep(Duration::from_millis(1))
                }
                Err(e) => return Err(e),
            }
        };
        stream.set_read_timeout(Some(WAIT))?;
        stream.set_write_timeout(Some(WAIT))?;
        let mut request = Vec::new();
        Read::by_ref(&mut stream)
            .take(1025)
            .read_to_end(&mut request)?;
        check(
            request == [0x6c; 1024],
            "real TCP peer did not receive request followed by FIN",
        )?;
        stream.write_all(&vec![0x91; TCP_REPLY_BYTES])?;
        stream.shutdown(Shutdown::Write)?;
        Ok(())
    });
    let transfer = (|| {
        let origin = source(v6, 44000);
        let destination = SocketAddr::new(fake, endpoint.port());
        client.send_packet(tcp_packet(
            origin,
            destination,
            100,
            None,
            TcpControl::Syn,
            &[],
        )?)?;
        let mut next = None;
        let mut response = Vec::new();
        let deadline = Instant::now() + WAIT;
        loop {
            check(
                Instant::now() < deadline,
                "TCP fixture exceeded predeclared deadline",
            )?;
            let bytes = receive(&client.received, "worker TCP response")?;
            let (src, dst, protocol, payload) = ip_payload(&bytes)?;
            check(
                protocol == IpProtocol::Tcp,
                "unexpected non-TCP fixture packet",
            )?;
            let packet = TcpPacket::new_checked(payload).map_err(io::Error::other)?;
            let segment = TcpRepr::parse(
                &packet,
                &src.into(),
                &dst.into(),
                &ChecksumCapabilities::default(),
            )
            .map_err(io::Error::other)?;
            check(
                (
                    SocketAddr::new(src, segment.src_port),
                    SocketAddr::new(dst, segment.dst_port),
                ) == (destination, origin),
                "TCP fixture tuple differs",
            )?;
            check(
                segment.control != TcpControl::Rst,
                "restricted Core reset TCP transfer",
            )?;
            if next.is_none() {
                check(
                    segment.control == TcpControl::Syn
                        && segment.ack_number == Some(TcpSeqNumber(101)),
                    "worker TCP SYN acknowledgement differs",
                )?;
                let server = segment.seq_number.0.wrapping_add(1);
                next = Some(server);
                client.send_packet(tcp_packet(
                    origin,
                    destination,
                    101,
                    Some(server),
                    TcpControl::None,
                    &[],
                )?)?;
                client.send_packet(tcp_packet(
                    origin,
                    destination,
                    101,
                    Some(server),
                    TcpControl::Psh,
                    &[0x6c; 1024],
                )?)?;
                client.send_packet(tcp_packet(
                    origin,
                    destination,
                    1125,
                    Some(server),
                    TcpControl::Fin,
                    &[],
                )?)?;
                continue;
            }
            let mut server = next.unwrap();
            if !segment.payload.is_empty() {
                check(
                    segment.seq_number.0 == server,
                    "worker TCP reply sequence differs",
                )?;
                check(
                    response.len() + segment.payload.len() <= TCP_REPLY_BYTES,
                    "worker TCP reply exceeded planned size",
                )?;
                response.extend_from_slice(segment.payload);
                server = server.wrapping_add(segment.payload.len() as i32);
            }
            let finished = segment.control == TcpControl::Fin;
            if finished {
                server = server.wrapping_add(1);
            }
            client.send_packet(tcp_packet(
                origin,
                destination,
                1126,
                Some(server),
                TcpControl::None,
                &[],
            )?)?;
            next = Some(server);
            if finished {
                break;
            }
        }
        check(
            response == vec![0x91; TCP_REPLY_BYTES],
            "worker TCP half-close reply differs",
        )
    })();
    let peer_result = join(peer);
    transfer?;
    peer_result
}

fn config() -> RuntimeConfig {
    RuntimeConfig {
        schema: 2,
        listen: "127.0.0.1:0".parse().unwrap(),
        nodes: vec![Node {
            id: NODE.into(),
            outbound: Outbound::HttpConnect {
                host: "127.0.0.1".into(),
                port: 9,
                auth: None,
                tls: None,
            },
        }],
        policy: PolicyDocument {
            schema: 2,
            mode: Mode::Direct,
            default_policy: DefaultPolicy {
                id: DEFAULT_POLICY_ID.into(),
                target: Target::Node { id: NODE.into() },
            },
            service_policies: vec![],
            groups: vec![],
            explicit_direct_rules: vec![],
            custom_rules: vec![],
            missing_targets: vec![],
            classification_dns: ClassificationDns::Disabled,
        },
        dns: Dns {
            hosts: vec![
                HostMapping {
                    name: "ipv4.worker.fixture.invalid".into(),
                    address: "127.0.0.1".parse().unwrap(),
                },
                HostMapping {
                    name: "ipv6.worker.fixture.invalid".into(),
                    address: "::1".parse().unwrap(),
                },
            ],
            use_system_hosts: false,
            tls_servers: vec![DnsTlsServer {
                address: "192.0.2.1:853".parse().unwrap(),
                tls: Tls {
                    server_name: "dns.fixture.invalid".into(),
                    alpn: vec![],
                    ca_der_base64: None,
                },
                https_path: None,
            }],
            ..Dns::default()
        },
        inbound_auth: None,
        limits: Limits::default(),
        china_rules_directory: None,
        node_sources: Default::default(),
        transports: Default::default(),
    }
}
fn source(v6: bool, port: u16) -> SocketAddr {
    SocketAddr::new(
        if v6 { "2001:db8::10" } else { "192.0.2.10" }
            .parse()
            .unwrap(),
        port,
    )
}
fn query(v6: bool) -> Vec<u8> {
    let mut bytes = vec![0x12, 0x34, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0];
    for label in [
        if v6 { "ipv6" } else { "ipv4" },
        "worker",
        "fixture",
        "invalid",
    ] {
        bytes.push(label.len() as u8);
        bytes.extend_from_slice(label.as_bytes());
    }
    bytes.extend_from_slice(&[0, 0, if v6 { 28 } else { 1 }, 0, 1]);
    bytes
}
fn exercise(client: &Client) -> io::Result<Vec<IpAddr>> {
    let mut fake = Vec::new();
    for v6 in [false, true] {
        let socket = UdpSocket::bind(if v6 { "[::1]:0" } else { "127.0.0.1:0" })?;
        socket.set_read_timeout(Some(WAIT))?;
        socket.set_write_timeout(Some(WAIT))?;
        let endpoint = socket.local_addr()?;
        let peer = thread::spawn(move || {
            let mut bytes = [0; 1500];
            for _ in 0..2 {
                let (size, from) = socket.recv_from(&mut bytes)?;
                socket.send_to(&bytes[..size], from)?;
            }
            Ok(())
        });
        let transfer: io::Result<()> = (|| {
            for payload in [&b""[..], &[0xa7; 1200][..]] {
                check(
                    client.udp(source(v6, 42000), endpoint, payload)? == payload,
                    "restricted Core UDP echo differs",
                )?;
            }
            Ok(())
        })();
        let peer_result = join(peer);
        transfer?;
        peer_result?;
        let dns = SocketAddr::new(if v6 { DNS_IPV6.into() } else { DNS_IPV4.into() }, 53);
        let query = query(v6);
        let response = client.udp(source(v6, 43000), dns, &query)?;
        let length = if v6 { 16 } else { 4 };
        check(
            response.len() == query.len() + 12 + length
                && response[..2] == query[..2]
                && response[2] & 0x80 != 0
                && response[3] & 15 == 0
                && response[6..8] == [0, 1]
                && response[12..query.len()] == query[12..],
            "restricted Core DNS response differs",
        )?;
        let address = &response[response.len() - length..];
        let address = if v6 {
            IpAddr::V6(
                <[u8; 16]>::try_from(address)
                    .map_err(io::Error::other)?
                    .into(),
            )
        } else {
            IpAddr::V4(
                <[u8; 4]>::try_from(address)
                    .map_err(io::Error::other)?
                    .into(),
            )
        };
        tcp_roundtrip(client, v6, address)?;
        fake.push(address);
    }
    Ok(fake)
}

pub fn run(worker: PathBuf, directory: PathBuf) -> io::Result<()> {
    for path in [&worker, &directory] {
        check(
            matches!(path.components().next(),Some(Component::Prefix(p)) if matches!(p.kind(),Prefix::Disk(_)|Prefix::VerbatimDisk(_))),
            "fixture requires local drive paths",
        )?;
    }
    let source_sha = std::env::var("SWIRL_SOURCE_SHA").map_err(io::Error::other)?;
    check(
        source_sha.len() == 40 && source_sha.bytes().all(|b| b.is_ascii_hexdigit()),
        "missing exact source SHA",
    )?;
    let image = fs::read(&worker)?;
    fs::create_dir(&directory)?;
    let copied = directory.join("swirl-tun-packet-worker.exe");
    fs::write(&copied, &image)?;
    let journal_path = directory.join("fake-ip.jsonl");
    let journal = OpenOptions::new()
        .create_new(true)
        .read(true)
        .write(true)
        .open(&journal_path)?;
    // Persist scope/criteria before creating a token, desktop, job or child.
    let mut plan = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(directory.join("plan.json"))?;
    serde_json::to_writer_pretty(
        &mut plan,
        &json!({"schema":1,"source_sha":source_sha,"worker_sha256":hash(&image),"epoch":EPOCH,"mtu":1500,"io_deadline_seconds":WAIT.as_secs(),"stdout_log_limit":MAX_LOG,"stderr_log_limit":MAX_LINE,"udp_families":2,"datagrams_per_family":2,"payload_sizes":[0,1200],"dns_queries":["A","AAAA"],"tcp_families":2,"tcp_request_bytes":1024,"tcp_reply_after_fin_bytes":TCP_REPLY_BYTES,"normal_stop_seconds":WAIT.as_secs(),"network_configuration_changed":false}),
    )?;
    plan.sync_all()?;
    let DataPlaneChild {
        mut worker,
        packet_input,
        packet_output,
        inherited,
    } = spawn_data_plane(&copied, &["--internal-packet-worker".into()], &journal)?;
    let (control, control_rx) = mpsc::sync_channel(4);
    let (packets, packets_rx) = mpsc::sync_channel(4);
    let (reply_tx, replies) = mpsc::sync_channel(4);
    let (packet_tx, received) = mpsc::sync_channel(4);
    let stdin = worker
        .stdin
        .take()
        .ok_or_else(|| io::Error::other("missing child stdin"))?;
    let stdout = worker
        .stdout
        .take()
        .ok_or_else(|| io::Error::other("missing child stdout"))?;
    let stderr = worker
        .stderr
        .take()
        .ok_or_else(|| io::Error::other("missing child stderr"))?;
    let ctrl_out = thread::spawn(move || writer(stdin, false, control_rx));
    let packet_out = thread::spawn(move || writer(packet_input, true, packets_rx));
    let stdout_path = directory.join("child-stdout.log");
    let ctrl_in = thread::spawn(move || control_reader(stdout, stdout_path, reply_tx));
    let stderr_path = directory.join("child-stderr.log");
    let stderr_in = thread::spawn(move || {
        let mut out = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(stderr_path)?;
        let mut bounded = stderr.take((MAX_LINE + 1) as u64);
        let size = io::copy(&mut bounded, &mut out)?;
        out.sync_all()?;
        check(size <= MAX_LINE as u64, "worker stderr exceeded bound")
    });
    let packet_in = thread::spawn(move || {
        let mut reader = PacketReader::new(packet_output, EPOCH, 1500)?;
        loop {
            match reader.read_packet() {
                Ok(Some(packet)) => {
                    if packet_tx.send(Ok(packet)).is_err() {
                        return Ok(());
                    }
                }
                Ok(None) => return Ok(()),
                Err(error) => {
                    let _ = packet_tx.send(Err(error));
                    return Ok(());
                }
            }
        }
    });
    let client = Client {
        control,
        replies,
        packets,
        received,
    };
    let result: io::Result<Vec<IpAddr>> = (|| {
        let initialized=client.rpc(json!({"op":"init","mtu":1500,"max_tcp_flows":256,"max_udp_flows":128,"resources":inherited}))?;
        let profile = &initialized["token_profile"];
        check(
            initialized["token_validated"] == true
                && initialized["source_sha"] == source_sha
                && profile["elevated"] == false
                && profile["restricted"] == true
                && profile["admin_enabled"] == false
                && profile["admin_deny_only"] == true
                && profile["integrity_rid"] == 4096
                && profile["unexpected_enabled_privileges"] == 0
                && profile["enabled_privileges"]
                    .as_u64()
                    .is_some_and(|n| n <= 1),
            "worker did not report its actual required restricted Low token/source",
        )?;
        for field in [
            "broker_authenticated",
            "service_principal_authenticated",
            "kernel_identity_enforced",
            "product_broker_integrated",
            "system_kill_switch",
            "network_resources_owned",
            "routes_restored",
        ] {
            check(
                initialized[field] == false,
                "experimental worker overstated an unverified production capability",
            )?;
        }
        check(
            initialized["physical_egress_suspended"] == true,
            "packet worker did not retain suspended physical egress",
        )?;
        let request = json!({"control_schema":2,"op":"start_v2","request_id":REQUEST,"store_id":STORE,"saved_revision":"1","candidate":config()});
        let core = client.rpc(json!({"op":"core","json":serde_json::to_string(&request)?}))?;
        check(core["ok"] == true, "worker original V2 start failed")?;
        client.rpc(json!({"op":"bridge_start","handle":core["handle"],"engine_epoch":core["engine_epoch"]}))?;
        let fake = exercise(&client)?;
        let status = client.rpc(json!({"op":"status"}))?;
        check(
            status["state"] == "running"
                && status["bridge"]["packet_input_accepted"]
                    .as_u64()
                    .is_some_and(|n| n >= 10)
                && status["bridge"]["packet_output_written"]
                    .as_u64()
                    .is_some_and(|n| n >= 10),
            "worker did not observe actual bidirectional packet traffic",
        )?;
        for counter in [
            "malformed_packets",
            "tcp_failures",
            "udp_failures",
            "dns_failures",
            "packet_queue_dropped",
        ] {
            check(
                status["bridge"][counter] == 0,
                "worker packet/Core error counter is not zero",
            )?;
        }
        check(
            client.rpc(json!({"op":"stop"}))?["state"] == "stopped",
            "worker did not acknowledge stopped state",
        )?;
        Ok(fake)
    })();
    drop(client);
    // Close/reap the whole owned job before joining any possibly blocked pipe
    // pumps. Capture every cleanup result even when the first scenario failed.
    let exit = if result.is_ok() {
        worker.wait(WAIT)
    } else {
        worker.kill().map(|()| 1)
    };
    let joins = [
        join(ctrl_out),
        join(packet_out),
        join(ctrl_in),
        join(stderr_in),
        join(packet_in),
    ];
    if let Err(ref error) = exit {
        eprintln!("packet worker cleanup failed: {error}");
    }
    for joined in &joins {
        if let Err(error) = joined {
            eprintln!("packet worker IO cleanup failed: {error}");
        }
    }
    let fake = result?;
    check(exit? == 0, "restricted packet worker exited unsuccessfully")?;
    for joined in joins {
        joined?;
    }
    drop(journal);
    let store = FakeIpStore::open(&journal_path, 16).map_err(io::Error::other)?;
    for address in fake {
        let expected = if address.is_ipv6() {
            "ipv6.worker.fixture.invalid"
        } else {
            "ipv4.worker.fixture.invalid"
        };
        check(
            store.domain(address).map_err(io::Error::other)?.as_deref() == Some(expected),
            "worker Fake-IP journal did not persist exact mapping",
        )?;
    }
    println!(
        "{}",
        json!({"ok":true,"source_sha":source_sha,"worker_sha256":hash(&image),"restricted_core_udp_ipv4_ipv6":true,"empty_and_1200_byte_datagrams":true,"udp_dns_a_aaaa":true,"fake_ip_reopened":true,"normal_child_exit_and_pipe_join":true,"network_configuration_changed":false,"restricted_core_tcp_ipv4_ipv6_half_close":true,"wintun_acceptance":false,"kernel_service_identity_acceptance":false,"product_broker_integrated":false,"physical_windows_11_acceptance":false})
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn packet_scenario_reaches_real_shared_core_and_loopback_peers_before_process_acceptance()
    -> io::Result<()> {
        // This checks the fixture against real Core sockets without creating
        // restricted tokens, desktops, child processes or host configuration.
        let _egress =
            swirl_transport::egress::EgressLease::acquire_suspended().map_err(io::Error::other)?;
        let mut core = swirl_core::v2::Core::start(config(), STORE.into(), 1, REQUEST.into())
            .map_err(io::Error::other)?;
        let dispatcher = core.flow_dispatcher().map_err(io::Error::other)?;
        let runtime = dispatcher.runtime_handle();
        let bridge = runtime
            .block_on(async {
                swirl_core::native_tun::spawn(
                    dispatcher,
                    swirl_dns::tun::TunDns::new(FakeIpStore::memory(16)?),
                    swirl_tun::TunConfig::default(),
                )
            })
            .map_err(io::Error::other)?;
        let mut control = bridge.control;
        let input = bridge.input;
        let mut output = bridge.output;
        let (packets, packet_rx) = mpsc::sync_channel(4);
        let (packet_tx, received) = mpsc::sync_channel(4);
        let pump_runtime = runtime.clone();
        let incoming = thread::spawn(move || {
            for bytes in packet_rx {
                pump_runtime
                    .block_on(input.send(bytes))
                    .map_err(io::Error::other)?;
            }
            Ok(())
        });
        let outgoing = thread::spawn(move || {
            while let Some(bytes) = output.blocking_recv() {
                if packet_tx.send(Ok(bytes)).is_err() {
                    break;
                }
            }
            Ok(())
        });
        let (control_tx, _control_rx) = mpsc::sync_channel(4);
        let (_reply_tx, replies) = mpsc::sync_channel(4);
        let client = Client {
            control: control_tx,
            replies,
            packets,
            received,
        };
        let result = exercise(&client);
        drop(client);
        let shutdown = runtime
            .block_on(control.shutdown())
            .map_err(io::Error::other);
        let input_done = join(incoming);
        let output_done = join(outgoing);
        core.stop();
        check(
            result?.len() == 2,
            "fixture did not produce both Fake-IP families",
        )?;
        shutdown?;
        input_done?;
        output_done?;
        Ok(())
    }
    #[test]
    fn control_eof_and_exact_limit_do_not_accept_unterminated_or_oversized_records() {
        assert!(line(&mut &b""[..]).unwrap().is_none());
        assert!(line(&mut &b"{}"[..]).is_err());
        assert!(line(&mut &vec![b'x'; MAX_LINE + 1][..]).is_err());
        let mut exact = vec![b' '; MAX_LINE];
        exact[MAX_LINE - 1] = b'\n';
        assert_eq!(
            line(&mut exact.as_slice()).unwrap().unwrap().len(),
            MAX_LINE
        );
    }
    #[test]
    fn bad_returned_packet_cannot_count_as_a_worker_echo() -> io::Result<()> {
        for v6 in [false, true] {
            let from = source(v6, 1);
            let to = source(v6, 2);
            let mut bytes = udp_packet(from, to, b"exact")?;
            assert_eq!(udp_payload(&bytes)?, (from, to, &b"exact"[..]));
            let last = bytes.len() - 1;
            bytes[last] ^= 1;
            assert!(udp_payload(&bytes).is_err());
        }
        Ok(())
    }
}
