//! L3 packet bridge acceptance against real, independently owned loopback peers.
//! These tests do not install a driver or modify host routes, DNS or adapters.
use crate::native_tun::{PacketBridge, spawn};
use smoltcp::{
    phy::ChecksumCapabilities,
    wire::{
        IpProtocol, Ipv4Packet, Ipv4Repr, Ipv6Packet, Ipv6Repr, TcpControl, TcpPacket, TcpRepr,
        TcpSeqNumber, UdpPacket, UdpRepr,
    },
};
use std::{
    collections::BTreeMap,
    net::{IpAddr, SocketAddr},
    time::Duration,
};
use swirl_core::v2::{Core, RuntimeConfig};
use swirl_dns::tun::{DNS_IPV4, DNS_IPV6, FakeIpStore, TunDns};
use swirl_subscription::{
    Dns, DnsTlsServer, HostMapping, Limits, Matcher, Node, Outbound, Tls,
    v2::{
        ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, Mode, PolicyDocument, PolicyRule,
        Target,
    },
};
use swirl_tun::TunConfig;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    time::timeout,
};

const WAIT: Duration = Duration::from_secs(4);
const STORE: &str = "a1000000-0000-4000-8000-000000000001";
const START: &str = "b1000000-0000-4000-8000-000000000001";
const NODE: &str = "c1000000-0000-4000-8000-000000000001";

fn runtime_config() -> RuntimeConfig {
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
            tls_servers: vec![DnsTlsServer {
                // Literal and configured host-table destinations never query
                // this endpoint. Missing DNS security still fails preflight.
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
        node_sources: BTreeMap::new(),
        transports: BTreeMap::new(),
    }
}

fn start(config: RuntimeConfig) -> Core {
    Core::start(config, STORE.into(), 1, START.into()).unwrap()
}

fn source(v6: bool, port: u16) -> SocketAddr {
    SocketAddr::new(
        if v6 { "2001:db8::10" } else { "192.0.2.10" }
            .parse()
            .unwrap(),
        port,
    )
}

fn ip_packet(src: IpAddr, dst: IpAddr, protocol: IpProtocol, payload: &[u8]) -> Vec<u8> {
    let header = if src.is_ipv4() { 20 } else { 40 };
    let mut bytes = vec![0; header + payload.len()];
    match (src, dst) {
        (IpAddr::V4(src_addr), IpAddr::V4(dst_addr)) => {
            Ipv4Repr {
                src_addr,
                dst_addr,
                next_header: protocol,
                payload_len: payload.len(),
                hop_limit: 64,
            }
            .emit(
                &mut Ipv4Packet::new_unchecked(&mut bytes[..]),
                &ChecksumCapabilities::default(),
            );
        }
        (IpAddr::V6(src_addr), IpAddr::V6(dst_addr)) => {
            Ipv6Repr {
                src_addr,
                dst_addr,
                next_header: protocol,
                payload_len: payload.len(),
                hop_limit: 64,
            }
            .emit(&mut Ipv6Packet::new_unchecked(&mut bytes[..]));
        }
        _ => panic!("test endpoint families differ"),
    }
    bytes[header..].copy_from_slice(payload);
    bytes
}

fn tcp_packet(
    src: SocketAddr,
    dst: SocketAddr,
    seq: i32,
    ack: Option<i32>,
    control: TcpControl,
    data: &[u8],
) -> Vec<u8> {
    let repr = TcpRepr {
        src_port: src.port(),
        dst_port: dst.port(),
        control,
        seq_number: TcpSeqNumber(seq),
        ack_number: ack.map(TcpSeqNumber),
        window_len: 65535,
        window_scale: None,
        max_seg_size: (control == TcpControl::Syn).then_some(1400),
        sack_permitted: false,
        sack_ranges: [None; 3],
        timestamp: None,
        payload: data,
    };
    let mut tcp = vec![0; repr.buffer_len()];
    repr.emit(
        &mut TcpPacket::new_unchecked(&mut tcp[..]),
        &src.ip().into(),
        &dst.ip().into(),
        &ChecksumCapabilities::default(),
    );
    ip_packet(src.ip(), dst.ip(), IpProtocol::Tcp, &tcp)
}

fn udp_packet(src: SocketAddr, dst: SocketAddr, data: &[u8]) -> Vec<u8> {
    let mut udp = vec![0; 8 + data.len()];
    UdpRepr {
        src_port: src.port(),
        dst_port: dst.port(),
    }
    .emit(
        &mut UdpPacket::new_unchecked(&mut udp[..]),
        &src.ip().into(),
        &dst.ip().into(),
        data.len(),
        |bytes| bytes.copy_from_slice(data),
        &ChecksumCapabilities::default(),
    );
    ip_packet(src.ip(), dst.ip(), IpProtocol::Udp, &udp)
}

fn ip_payload(bytes: &[u8]) -> (IpAddr, IpAddr, IpProtocol, &[u8]) {
    match bytes[0] >> 4 {
        4 => {
            let packet = Ipv4Packet::new_checked(bytes).unwrap();
            assert!(packet.verify_checksum());
            assert_eq!(usize::from(packet.total_len()), bytes.len());
            (
                packet.src_addr().into(),
                packet.dst_addr().into(),
                packet.next_header(),
                packet.payload(),
            )
        }
        6 => {
            let packet = Ipv6Packet::new_checked(bytes).unwrap();
            assert_eq!(usize::from(packet.payload_len()) + 40, bytes.len());
            (
                packet.src_addr().into(),
                packet.dst_addr().into(),
                packet.next_header(),
                packet.payload(),
            )
        }
        _ => panic!("invalid outbound IP version"),
    }
}

struct Segment {
    source: SocketAddr,
    destination: SocketAddr,
    sequence: i32,
    ack: Option<i32>,
    control: TcpControl,
    payload: Vec<u8>,
}

async fn next_tcp(bridge: &mut PacketBridge) -> Segment {
    timeout(WAIT, async {
        loop {
            let bytes = bridge
                .output
                .recv()
                .await
                .expect("bridge packet stream closed");
            let (src, dst, protocol, payload) = ip_payload(&bytes);
            if protocol != IpProtocol::Tcp {
                continue;
            }
            let packet = TcpPacket::new_checked(payload).unwrap();
            let repr = TcpRepr::parse(
                &packet,
                &src.into(),
                &dst.into(),
                &ChecksumCapabilities::default(),
            )
            .unwrap();
            return Segment {
                source: SocketAddr::new(src, repr.src_port),
                destination: SocketAddr::new(dst, repr.dst_port),
                sequence: repr.seq_number.0,
                ack: repr.ack_number.map(|ack| ack.0),
                control: repr.control,
                payload: repr.payload.to_vec(),
            };
        }
    })
    .await
    .expect("bridge TCP response timeout")
}

async fn next_udp(bridge: &mut PacketBridge) -> (SocketAddr, SocketAddr, Vec<u8>) {
    timeout(WAIT, async {
        loop {
            let bytes = bridge
                .output
                .recv()
                .await
                .expect("bridge packet stream closed");
            let (src, dst, protocol, payload) = ip_payload(&bytes);
            if protocol != IpProtocol::Udp {
                continue;
            }
            let packet = UdpPacket::new_checked(payload).unwrap();
            let repr = UdpRepr::parse(
                &packet,
                &src.into(),
                &dst.into(),
                &ChecksumCapabilities::default(),
            )
            .unwrap();
            return (
                SocketAddr::new(src, repr.src_port),
                SocketAddr::new(dst, repr.dst_port),
                packet.payload().to_vec(),
            );
        }
    })
    .await
    .expect("bridge UDP response timeout")
}

async fn handshake(bridge: &mut PacketBridge, source: SocketAddr, destination: SocketAddr) -> i32 {
    bridge
        .input
        .send(tcp_packet(
            source,
            destination,
            100,
            None,
            TcpControl::Syn,
            &[],
        ))
        .await
        .unwrap();
    let syn_ack = next_tcp(bridge).await;
    assert_eq!((syn_ack.source, syn_ack.destination), (destination, source));
    assert_eq!(syn_ack.control, TcpControl::Syn);
    assert_eq!(syn_ack.ack, Some(101));
    let server_next = syn_ack.sequence.wrapping_add(1);
    bridge
        .input
        .send(tcp_packet(
            source,
            destination,
            101,
            Some(server_next),
            TcpControl::None,
            &[],
        ))
        .await
        .unwrap();
    server_next
}

async fn until(mut condition: impl FnMut() -> bool) {
    timeout(WAIT, async {
        while !condition() {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("bridge state deadline");
}

fn dns_query(name: &str, v6: bool) -> Vec<u8> {
    let mut query = vec![0xca, 0xfe, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0];
    for label in name.split('.') {
        query.push(label.len() as u8);
        query.extend_from_slice(label.as_bytes());
    }
    query.push(0);
    query.extend_from_slice(if v6 { &[0, 28, 0, 1] } else { &[0, 1, 0, 1] });
    query
}

async fn fake_address(bridge: &mut PacketBridge, name: &str, v6: bool) -> IpAddr {
    let origin = source(v6, 41053);
    let destination = SocketAddr::new(if v6 { DNS_IPV6.into() } else { DNS_IPV4.into() }, 53);
    let query = dns_query(name, v6);
    bridge
        .input
        .send(udp_packet(origin, destination, &query))
        .await
        .unwrap();
    let (from, to, answer) = next_udp(bridge).await;
    assert_eq!((from, to), (destination, origin));
    assert_eq!(&answer[..2], &[0xca, 0xfe]);
    assert_eq!(answer[3] & 15, 0, "DNS must succeed");
    assert_eq!(&answer[4..8], &[0, 1, 0, 1]);
    assert_eq!(&answer[12..query.len()], &query[12..]);
    assert_eq!(&answer[query.len()..query.len() + 2], &[0xc0, 0x0c]);
    let bytes = &answer[query.len() + 12..];
    if v6 {
        IpAddr::V6(std::net::Ipv6Addr::from(
            <[u8; 16]>::try_from(bytes).unwrap(),
        ))
    } else {
        IpAddr::V4(std::net::Ipv4Addr::from(
            <[u8; 4]>::try_from(bytes).unwrap(),
        ))
    }
}

fn tcp_roundtrip(v6: bool) {
    let listener = std::net::TcpListener::bind(if v6 { "[::1]:0" } else { "127.0.0.1:0" }).unwrap();
    let real = listener.local_addr().unwrap();
    listener.set_nonblocking(true).unwrap();
    let name = if v6 {
        "ipv6.packet.fixture.invalid"
    } else {
        "ipv4.packet.fixture.invalid"
    };
    let mut config = runtime_config();
    config.dns.hosts.push(HostMapping {
        name: name.into(),
        address: real.ip(),
    });
    let mut core = start(config);
    let dispatcher = core.flow_dispatcher().unwrap();
    let runtime = dispatcher.runtime_handle();
    runtime.block_on(async {
        const REQUEST: &[u8] = b"request-through-l3";
        const RESPONSE: &[u8] = b"complete-server-response-after-client-fin";
        let server = tokio::spawn(async move {
            let listener = tokio::net::TcpListener::from_std(listener).unwrap();
            let (mut stream, _) = timeout(WAIT, listener.accept()).await.unwrap().unwrap();
            let mut request = Vec::new();
            timeout(WAIT, stream.read_to_end(&mut request))
                .await
                .unwrap()
                .unwrap();
            assert_eq!(request, REQUEST);
            stream.write_all(RESPONSE).await.unwrap();
            stream.shutdown().await.unwrap();
        });
        let dns = TunDns::new(FakeIpStore::memory(8).unwrap());
        let mut bridge = spawn(dispatcher, dns.clone(), TunConfig::default()).unwrap();
        let fake = fake_address(&mut bridge, name, v6).await;
        assert_ne!(fake, real.ip());
        assert_eq!(dns.target_host(fake).await.unwrap(), name);
        let origin = source(v6, 41000);
        let destination = SocketAddr::new(fake, real.port());
        let mut server_next = handshake(&mut bridge, origin, destination).await;
        bridge
            .input
            .send(tcp_packet(
                origin,
                destination,
                101,
                Some(server_next),
                TcpControl::Psh,
                REQUEST,
            ))
            .await
            .unwrap();
        let client_fin = 101 + REQUEST.len() as i32;
        bridge
            .input
            .send(tcp_packet(
                origin,
                destination,
                client_fin,
                Some(server_next),
                TcpControl::Fin,
                &[],
            ))
            .await
            .unwrap();
        let mut response = Vec::new();
        loop {
            let segment = next_tcp(&mut bridge).await;
            assert_eq!((segment.source, segment.destination), (destination, origin));
            assert_ne!(segment.control, TcpControl::Rst);
            if !segment.payload.is_empty() {
                assert_eq!(segment.sequence, server_next);
                server_next = server_next.wrapping_add(segment.payload.len() as i32);
                response.extend_from_slice(&segment.payload);
            }
            let finished = segment.control == TcpControl::Fin;
            if finished {
                server_next = server_next.wrapping_add(1);
            }
            bridge
                .input
                .send(tcp_packet(
                    origin,
                    destination,
                    client_fin + 1,
                    Some(server_next),
                    TcpControl::None,
                    &[],
                ))
                .await
                .unwrap();
            if finished {
                break;
            }
        }
        assert_eq!(response, RESPONSE);
        server.await.unwrap();
        until(|| core.snapshot().unwrap()["active"] == 0).await;
        let snapshot = core.snapshot().unwrap();
        assert_eq!(snapshot["upload"], REQUEST.len() as u64);
        assert_eq!(snapshot["download"], RESPONSE.len() as u64);
        assert_eq!(snapshot["failed"], 0);
        assert!(
            snapshot["connections"]
                .as_array()
                .unwrap()
                .iter()
                .any(|row| row["host"] == name && row["node"] == "SWIRL_V2_DIRECT")
        );
        assert_eq!(bridge.stats.snapshot().malformed_packets, 0);
        assert_eq!(
            bridge
                .bridge_stats
                .tcp_failures
                .load(std::sync::atomic::Ordering::Relaxed),
            0
        );
        assert_eq!(
            bridge
                .bridge_stats
                .dns_failures
                .load(std::sync::atomic::Ordering::Relaxed),
            0
        );
        bridge.control.shutdown().await.unwrap();
        assert!(bridge.control.is_finished());
        assert_eq!(bridge.stats.snapshot().active_tcp_flows, 0);
    });
    core.stop();
}

#[test]
fn packet_bridge_ipv4_dns_fake_ip_tcp_half_close_reaches_real_core_socket() {
    tcp_roundtrip(false);
}

#[test]
fn packet_bridge_ipv6_dns_fake_ip_tcp_half_close_reaches_real_core_socket() {
    tcp_roundtrip(true);
}

fn udp_roundtrip(v6: bool) {
    let socket = std::net::UdpSocket::bind(if v6 { "[::1]:0" } else { "127.0.0.1:0" }).unwrap();
    let destination = socket.local_addr().unwrap();
    socket.set_nonblocking(true).unwrap();
    let mut core = start(runtime_config());
    let dispatcher = core.flow_dispatcher().unwrap();
    let runtime = dispatcher.runtime_handle();
    runtime.block_on(async {
        let server = tokio::spawn(async move {
            let socket = tokio::net::UdpSocket::from_std(socket).unwrap();
            let mut buffer = [0; 1500];
            for _ in 0..2 {
                let (size, source) = timeout(WAIT, socket.recv_from(&mut buffer))
                    .await
                    .unwrap()
                    .unwrap();
                socket.send_to(&buffer[..size], source).await.unwrap();
            }
        });
        let mut bridge = spawn(
            dispatcher,
            TunDns::new(FakeIpStore::memory(8).unwrap()),
            TunConfig::default(),
        )
        .unwrap();
        let origin = source(v6, 42000);
        let full = vec![0xa7; 1200];
        for payload in [&b""[..], full.as_slice()] {
            bridge
                .input
                .send(udp_packet(origin, destination, payload))
                .await
                .unwrap();
            let (from, to, response) = next_udp(&mut bridge).await;
            assert_eq!((from, to), (destination, origin));
            assert_eq!(response, payload);
        }
        server.await.unwrap();
        let snapshot = core.snapshot().unwrap();
        assert_eq!(snapshot["upload"], 1200);
        assert_eq!(snapshot["download"], 1200);
        assert_eq!(snapshot["failed"], 0);
        assert_eq!(
            bridge
                .bridge_stats
                .udp_failures
                .load(std::sync::atomic::Ordering::Relaxed),
            0
        );
        bridge.control.shutdown().await.unwrap();
        assert!(bridge.control.is_finished());
        until(|| core.snapshot().unwrap()["active"] == 0).await;
    });
    core.stop();
}

#[test]
fn packet_bridge_ipv4_udp_preserves_empty_datagram_and_packet_boundaries() {
    udp_roundtrip(false);
}

#[test]
fn packet_bridge_ipv6_udp_preserves_empty_datagram_and_packet_boundaries() {
    udp_roundtrip(true);
}

#[test]
fn packet_bridge_reject_records_core_decision_and_never_dials_proxy_or_replies_with_data() {
    let proxy = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let proxy_address = proxy.local_addr().unwrap();
    proxy.set_nonblocking(true).unwrap();
    let mut config = runtime_config();
    config.policy.mode = Mode::Rule;
    config.nodes[0].outbound = Outbound::HttpConnect {
        host: proxy_address.ip().to_string(),
        port: proxy_address.port(),
        auth: None,
        tls: None,
    };
    config.policy.custom_rules.push(PolicyRule {
        id: "d1000000-0000-4000-8000-000000000001".into(),
        name: "Reject packet fixture".into(),
        enabled: true,
        priority: 0,
        matcher: Matcher::Cidr {
            value: "203.0.113.40/32".parse().unwrap(),
            resolve: false,
        },
        target: Target::Reject {},
    });
    let mut core = start(config);
    let dispatcher = core.flow_dispatcher().unwrap();
    let runtime = dispatcher.runtime_handle();
    runtime.block_on(async {
        let mut bridge = spawn(
            dispatcher,
            TunDns::new(FakeIpStore::memory(8).unwrap()),
            TunConfig::default(),
        )
        .unwrap();
        let origin = source(false, 43000);
        let destination = "203.0.113.40:443".parse().unwrap();
        let server_next = handshake(&mut bridge, origin, destination).await;
        bridge
            .input
            .send(tcp_packet(
                origin,
                destination,
                101,
                Some(server_next),
                TcpControl::Psh,
                b"must-not-forward",
            ))
            .await
            .unwrap();
        until(|| core.snapshot().unwrap()["failed"] == 1).await;
        loop {
            let segment = next_tcp(&mut bridge).await;
            assert!(segment.payload.is_empty());
            if matches!(segment.control, TcpControl::Fin | TcpControl::Rst) {
                assert_eq!(
                    segment.control,
                    TcpControl::Rst,
                    "REJECT must reset an unforwarded TCP flow"
                );
                break;
            }
        }
        let destination = "203.0.113.40:44000".parse().unwrap();
        bridge
            .input
            .send(udp_packet(
                source(false, 43001),
                destination,
                b"must-not-forward",
            ))
            .await
            .unwrap();
        until(|| core.snapshot().unwrap()["failed"] == 2).await;
        until(|| {
            bridge
                .bridge_stats
                .udp_failures
                .load(std::sync::atomic::Ordering::Relaxed)
                == 1
        })
        .await;
        let dropped = bridge
            .bridge_stats
            .udp_dropped
            .load(std::sync::atomic::Ordering::Relaxed);
        // A failed QUIC/UDP tuple must remain closed. A later datagram is not
        // permission to reroute/reconnect that same association to another exit.
        bridge
            .input
            .send(udp_packet(
                source(false, 43001),
                destination,
                b"must-not-retry",
            ))
            .await
            .unwrap();
        until(|| {
            bridge
                .bridge_stats
                .udp_dropped
                .load(std::sync::atomic::Ordering::Relaxed)
                == dropped + 1
        })
        .await;
        assert_eq!(
            bridge
                .bridge_stats
                .udp_failures
                .load(std::sync::atomic::Ordering::Relaxed),
            1
        );
        assert_eq!(
            core.snapshot().unwrap()["failed"],
            2,
            "the repeated tuple must not perform a second Core route/open"
        );
        assert!(
            timeout(Duration::from_millis(100), next_udp(&mut bridge))
                .await
                .is_err()
        );
        let snapshot = core.snapshot().unwrap();
        assert_eq!(snapshot["upload"], 0);
        assert_eq!(snapshot["download"], 0);
        assert!(
            snapshot["connections"]
                .as_array()
                .unwrap()
                .iter()
                .all(|row| row["category"] == "reject" && row["error"] == "Rejected")
        );
        assert_eq!(
            proxy.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
        bridge.control.shutdown().await.unwrap();
    });
    core.stop();
}
