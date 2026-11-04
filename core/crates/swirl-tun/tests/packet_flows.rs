//! Packet-level tests: no TUN driver, host routing or system DNS is touched.
use smoltcp::{
    phy::ChecksumCapabilities,
    wire::{
        IpProtocol, Ipv4Packet, Ipv4Repr, Ipv6Packet, Ipv6Repr, TcpControl, TcpPacket, TcpRepr,
        TcpSeqNumber, UdpPacket, UdpRepr,
    },
};
use std::{
    net::{IpAddr, SocketAddr},
    time::Duration,
};
use swirl_tun::{TunConfig, TunStack, UdpDatagram, spawn};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    time::timeout,
};

const WAIT: Duration = Duration::from_secs(3);

fn gateway_config() -> TunConfig {
    TunConfig {
        gateway: Some(swirl_tun::gateway::GatewayIngress {
            lan_subnet: "192.168.77.0/24".parse().unwrap(),
            gateway: "192.168.77.1".parse().unwrap(),
            allowed_sources: vec!["192.168.77.0/25".parse().unwrap()],
            local_sources: vec![
                "192.168.77.1".parse().unwrap(),
                "198.18.0.1".parse().unwrap(),
            ],
            protected_hosts: vec!["192.168.77.1".parse().unwrap(), "10.1.2.3".parse().unwrap()],
            max_tcp_per_client: 1,
            max_udp_per_client: 8,
            max_dns_per_client: 2,
        }),
        ..TunConfig::default()
    }
}

#[tokio::test]
async fn gateway_udp_preserves_each_client_endpoint_in_both_directions() {
    let mut stack = spawn(gateway_config()).unwrap();
    let destination: SocketAddr = "203.0.113.20:443".parse().unwrap();
    for address in ["192.168.77.10:50000", "192.168.77.11:50000"] {
        let client: SocketAddr = address.parse().unwrap();
        stack
            .ingress
            .send(udp_packet(client, destination, address.as_bytes()))
            .await
            .unwrap();
        let datagram = timeout(WAIT, stack.udp.recv()).await.unwrap().unwrap();
        assert_eq!(
            (datagram.source, datagram.destination),
            (client, destination)
        );
        assert_eq!(datagram.payload, address.as_bytes());
        stack
            .udp_reply
            .send(UdpDatagram {
                source: destination,
                destination: client,
                payload: datagram.payload,
            })
            .await
            .unwrap();
        let bytes = timeout(WAIT, stack.egress.recv()).await.unwrap().unwrap();
        let (src, dst, protocol, payload) = ip_payload(&bytes);
        assert_eq!(
            (src, dst, protocol),
            (destination.ip(), client.ip(), IpProtocol::Udp)
        );
        let packet = UdpPacket::new_checked(payload).unwrap();
        assert_eq!(
            (packet.src_port(), packet.dst_port()),
            (destination.port(), client.port())
        );
        assert_eq!(packet.payload(), address.as_bytes());
    }
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn gateway_rejects_untrusted_sources_host_services_and_ipv6_before_allocation() {
    let mut stack = spawn(gateway_config()).unwrap();
    let attempts = [
        ("203.0.113.10:50000", "203.0.113.20:443"),
        ("192.168.77.200:50000", "203.0.113.20:443"),
        ("192.168.77.10:50000", "10.1.2.3:3389"),
        ("192.168.77.10:50000", "127.0.0.1:7890"),
        ("[fd00::10]:50000", "[2001:db8::20]:443"),
    ];
    for (source, destination) in attempts {
        stack
            .ingress
            .send(udp_packet(
                source.parse().unwrap(),
                destination.parse().unwrap(),
                b"denied",
            ))
            .await
            .unwrap();
    }
    wait_received(&stack, attempts.len() as u64).await;
    let stats = stack.stats.snapshot();
    assert_eq!(stats.denied_gateway_packets, attempts.len() as u64);
    assert_eq!(stats.active_udp_endpoints, 0);
    assert!(stack.udp.try_recv().is_err());
    assert!(stack.egress.try_recv().is_err());
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn gateway_tcp_limit_applies_per_client_without_disconnecting_other_devices() {
    let mut stack = spawn(gateway_config()).unwrap();
    let destination: SocketAddr = "203.0.113.20:443".parse().unwrap();
    let (first, _) = handshake(
        &mut stack,
        "192.168.77.10:50000".parse().unwrap(),
        destination,
    )
    .await;
    let rejected: SocketAddr = "192.168.77.10:50001".parse().unwrap();
    stack
        .ingress
        .send(tcp_packet(
            rejected,
            destination,
            100,
            None,
            TcpControl::Syn,
            &[],
        ))
        .await
        .unwrap();
    loop {
        let segment = next_tcp(&mut stack).await;
        if segment.destination == rejected {
            assert_eq!(segment.control, TcpControl::Rst);
            break;
        }
    }
    assert_eq!(stack.stats.snapshot().active_tcp_flows, 1);
    let (second, _) = handshake(
        &mut stack,
        "192.168.77.11:50000".parse().unwrap(),
        destination,
    )
    .await;
    assert_eq!(stack.stats.snapshot().active_tcp_flows, 2);
    assert_eq!(stack.stats.snapshot().denied_gateway_packets, 1);
    drop((first, second));
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn gateway_udp_client_limit_precedes_shared_endpoint_buffer_allocation() {
    let mut config = gateway_config();
    config.gateway.as_mut().unwrap().max_udp_per_client = 1;
    let mut stack = spawn(config).unwrap();
    let first: SocketAddr = "192.168.77.10:50000".parse().unwrap();
    let second: SocketAddr = "192.168.77.11:50000".parse().unwrap();
    let first_target: SocketAddr = "203.0.113.20:443".parse().unwrap();
    let second_target: SocketAddr = "203.0.113.21:443".parse().unwrap();
    stack
        .ingress
        .send(udp_packet(first, first_target, b"first"))
        .await
        .unwrap();
    assert_eq!(
        timeout(WAIT, stack.udp.recv())
            .await
            .unwrap()
            .unwrap()
            .source,
        first
    );
    stack
        .ingress
        .send(udp_packet(first, second_target, b"over limit"))
        .await
        .unwrap();
    wait_received(&stack, 2).await;
    assert_eq!(stack.stats.snapshot().active_udp_endpoints, 1);
    assert_eq!(stack.stats.snapshot().denied_gateway_packets, 1);
    stack
        .ingress
        .send(udp_packet(second, second_target, b"second device"))
        .await
        .unwrap();
    assert_eq!(
        timeout(WAIT, stack.udp.recv())
            .await
            .unwrap()
            .unwrap()
            .source,
        second
    );
    assert_eq!(stack.stats.snapshot().active_udp_endpoints, 2);
    stack.shutdown().await.unwrap();
}

fn ip_packet(src: IpAddr, dst: IpAddr, protocol: IpProtocol, payload: &[u8]) -> Vec<u8> {
    let mut bytes = vec![0; if src.is_ipv4() { 20 } else { 40 } + payload.len()];
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
            bytes[20..].copy_from_slice(payload);
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
            bytes[40..].copy_from_slice(payload);
        }
        _ => panic!("test address families differ"),
    }
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
        max_seg_size: if control == TcpControl::Syn {
            Some(1400)
        } else {
            None
        },
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
    if bytes[0] >> 4 == 4 {
        let p = Ipv4Packet::new_checked(bytes).unwrap();
        assert!(p.verify_checksum());
        (
            p.src_addr().into(),
            p.dst_addr().into(),
            p.next_header(),
            p.payload(),
        )
    } else {
        let p = Ipv6Packet::new_checked(bytes).unwrap();
        (
            p.src_addr().into(),
            p.dst_addr().into(),
            p.next_header(),
            p.payload(),
        )
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

async fn next_tcp(stack: &mut TunStack) -> Segment {
    timeout(WAIT, async {
        loop {
            let bytes = stack.egress.recv().await.expect("packet stream closed");
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
                ack: repr.ack_number.map(|n| n.0),
                control: repr.control,
                payload: repr.payload.to_vec(),
            };
        }
    })
    .await
    .expect("TCP output timeout")
}

async fn wait_received(stack: &TunStack, n: u64) {
    timeout(WAIT, async {
        while stack.stats.snapshot().received_packets < n {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
}

async fn handshake(
    stack: &mut TunStack,
    source: SocketAddr,
    destination: SocketAddr,
) -> (swirl_tun::TunTcpStream, i32) {
    stack
        .ingress
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
    let syn_ack = next_tcp(stack).await;
    assert_eq!((syn_ack.source, syn_ack.destination), (destination, source));
    assert_eq!(syn_ack.control, TcpControl::Syn);
    assert_eq!(syn_ack.ack, Some(101));
    let next = syn_ack.sequence.wrapping_add(1);
    let flow = timeout(WAIT, stack.tcp.recv()).await.unwrap().unwrap();
    assert_eq!((flow.source, flow.destination), (source, destination));
    stack
        .ingress
        .send(tcp_packet(
            source,
            destination,
            101,
            Some(next),
            TcpControl::None,
            &[],
        ))
        .await
        .unwrap();
    (flow.stream, next)
}

async fn tcp_payload_half_close(v6: bool) {
    let (source, destination) = if v6 {
        ("[2001:db8::10]:40000", "[2001:db8::20]:443")
    } else {
        ("192.0.2.10:40000", "203.0.113.20:443")
    };
    let source: SocketAddr = source.parse().unwrap();
    let destination: SocketAddr = destination.parse().unwrap();
    let mut stack = spawn(TunConfig::default()).unwrap();
    let (mut stream, server_next) = handshake(&mut stack, source, destination).await;
    stack
        .ingress
        .send(tcp_packet(
            source,
            destination,
            101,
            Some(server_next),
            TcpControl::Psh,
            b"request",
        ))
        .await
        .unwrap();
    stack
        .ingress
        .send(tcp_packet(
            source,
            destination,
            108,
            Some(server_next),
            TcpControl::Fin,
            &[],
        ))
        .await
        .unwrap();
    let mut request = Vec::new();
    timeout(WAIT, stream.read_to_end(&mut request))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(request, b"request");
    // EOF in one direction must preserve the entire reply and its FIN.
    stream.write_all(b"response-after-fin").await.unwrap();
    stream.shutdown().await.unwrap();
    let mut result = Vec::new();
    let mut next = server_next;
    loop {
        let segment = next_tcp(&mut stack).await;
        if !segment.payload.is_empty() {
            assert_eq!(segment.sequence, next);
            next = next.wrapping_add(segment.payload.len() as i32);
            result.extend_from_slice(&segment.payload);
        }
        let finished = segment.control == TcpControl::Fin;
        if finished {
            next = next.wrapping_add(1);
        }
        stack
            .ingress
            .send(tcp_packet(
                source,
                destination,
                109,
                Some(next),
                TcpControl::None,
                &[],
            ))
            .await
            .unwrap();
        if finished {
            break;
        }
    }
    assert_eq!(result, b"response-after-fin");
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn ipv4_tcp_handshake_payload_and_half_close() {
    tcp_payload_half_close(false).await;
}

#[tokio::test]
async fn ipv6_tcp_handshake_payload_and_half_close() {
    tcp_payload_half_close(true).await;
}

async fn cancelled_tcp_after_write_half_close(v6: bool, empty_read: bool) {
    let source: SocketAddr = if v6 {
        "[2001:db8::10]:40000"
    } else {
        "192.0.2.10:40000"
    }
    .parse()
    .unwrap();
    let destination: SocketAddr = if v6 {
        "[2001:db8::20]:443"
    } else {
        "203.0.113.20:443"
    }
    .parse()
    .unwrap();
    let mut stack = spawn(TunConfig {
        max_tcp_flows: 1,
        ..TunConfig::default()
    })
    .unwrap();
    let (mut stream, _) = handshake(&mut stack, source, destination).await;
    let cancellation = stream.abort_on_drop();
    if empty_read {
        let mut bytes = [];
        let mut buffer = tokio::io::ReadBuf::new(&mut bytes);
        std::future::poll_fn(|cx| {
            // Tokio may return Pending for an empty read on an idle duplex.
            // Exercise one poll; it is neither data consumption nor EOF.
            let _ =
                tokio::io::AsyncRead::poll_read(std::pin::Pin::new(&mut stream), cx, &mut buffer);
            std::task::Poll::Ready(())
        })
        .await;
        assert!(buffer.filled().is_empty());
    }
    stream.shutdown().await.unwrap();
    let fin = next_tcp(&mut stack).await;
    assert_eq!(fin.control, TcpControl::Fin);
    stack
        .ingress
        .send(tcp_packet(
            source,
            destination,
            101,
            Some(fin.sequence.wrapping_add(1)),
            TcpControl::None,
            &[],
        ))
        .await
        .unwrap();
    wait_received(&stack, 3).await;
    // Preserve ordinary write-only shutdown/drop draining. A dispatcher task
    // instead owns an explicit guard until the entire operation succeeds.
    let (started, ready) = tokio::sync::oneshot::channel();
    let task = tokio::spawn(async move {
        let _cancellation = cancellation;
        let _stream = stream;
        started.send(()).unwrap();
        std::future::pending::<()>().await;
    });
    timeout(WAIT, ready).await.unwrap().unwrap();
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
    let reset = next_tcp(&mut stack).await;
    assert_eq!(reset.control, TcpControl::Rst);
    timeout(WAIT, async {
        while stack.stats.snapshot().active_tcp_flows != 0 {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn ipv4_tcp_cancel_after_write_half_close_resets_remaining_upload() {
    cancelled_tcp_after_write_half_close(false, false).await;
}

#[tokio::test]
async fn ipv6_tcp_cancel_after_write_half_close_resets_remaining_upload() {
    cancelled_tcp_after_write_half_close(true, false).await;
}

#[tokio::test]
async fn empty_read_buffer_does_not_hide_cancelled_half_closed_tcp_upload() {
    cancelled_tcp_after_write_half_close(false, true).await;
}

#[tokio::test]
async fn syn_retransmission_does_not_allocate_another_flow_and_limit_rejects() {
    let mut stack = spawn(TunConfig {
        max_tcp_flows: 1,
        ..TunConfig::default()
    })
    .unwrap();
    let source = "192.0.2.10:40000".parse().unwrap();
    let destination = "203.0.113.20:443".parse().unwrap();
    let syn = tcp_packet(source, destination, 100, None, TcpControl::Syn, &[]);
    stack.ingress.send(syn.clone()).await.unwrap();
    let _ = next_tcp(&mut stack).await;
    let flow = timeout(WAIT, stack.tcp.recv()).await.unwrap().unwrap();
    for _ in 0..10 {
        stack.ingress.send(syn.clone()).await.unwrap();
    }
    wait_received(&stack, 11).await;
    assert_eq!(stack.stats.snapshot().active_tcp_flows, 1);
    assert!(stack.tcp.try_recv().is_err());
    let second = "192.0.2.11:40001".parse().unwrap();
    stack
        .ingress
        .send(tcp_packet(
            second,
            destination,
            100,
            None,
            TcpControl::Syn,
            &[],
        ))
        .await
        .unwrap();
    loop {
        let segment = next_tcp(&mut stack).await;
        if segment.destination == second {
            assert_eq!(segment.control, TcpControl::Rst);
            break;
        }
    }
    assert_eq!(stack.stats.snapshot().active_tcp_flows, 1);
    assert_eq!(stack.stats.snapshot().rejected_tcp_flows, 1);
    drop(flow);
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn equal_ports_at_different_destination_ips_cannot_cross_streams() {
    let mut stack = spawn(TunConfig::default()).unwrap();
    let source: SocketAddr = "192.0.2.10:40000".parse().unwrap();
    let d1 = "198.18.1.10:443".parse().unwrap();
    let d2 = "198.18.1.11:443".parse().unwrap();
    let (mut one, ack1) = handshake(&mut stack, source, d1).await;
    let (mut two, ack2) = handshake(&mut stack, source, d2).await;
    stack
        .ingress
        .send(tcp_packet(
            source,
            d2,
            101,
            Some(ack2),
            TcpControl::Psh,
            b"two",
        ))
        .await
        .unwrap();
    stack
        .ingress
        .send(tcp_packet(
            source,
            d1,
            101,
            Some(ack1),
            TcpControl::Psh,
            b"one",
        ))
        .await
        .unwrap();
    let mut bytes = [0; 3];
    timeout(WAIT, one.read_exact(&mut bytes))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(&bytes, b"one");
    timeout(WAIT, two.read_exact(&mut bytes))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(&bytes, b"two");
    stack.shutdown().await.unwrap();
}

async fn udp_roundtrip(v6: bool) {
    let (source, destination) = if v6 {
        ("[2001:db8::10]:40000", "[fd53:7769:726c::2]:53")
    } else {
        ("192.0.2.10:40000", "198.18.0.2:53")
    };
    let source: SocketAddr = source.parse().unwrap();
    let destination: SocketAddr = destination.parse().unwrap();
    let mut stack = spawn(TunConfig::default()).unwrap();
    // Bad input must not close the stream or poison the next datagram.
    stack.ingress.send(vec![0x60, 0, 0]).await.unwrap();
    let mut corrupted = udp_packet(source, destination, b"corrupt");
    let end = corrupted.len() - 1;
    corrupted[end] ^= 1;
    stack.ingress.send(corrupted).await.unwrap();
    for data in [&b""[..], &b"query"[..]] {
        stack
            .ingress
            .send(udp_packet(source, destination, data))
            .await
            .unwrap();
        let received = timeout(WAIT, stack.udp.recv()).await.unwrap().unwrap();
        assert_eq!(
            received,
            UdpDatagram {
                source,
                destination,
                payload: data.to_vec()
            }
        );
        stack
            .udp_reply
            .send(UdpDatagram {
                source: destination,
                destination: source,
                payload: data.to_vec(),
            })
            .await
            .unwrap();
        let bytes = timeout(WAIT, stack.egress.recv()).await.unwrap().unwrap();
        let (src, dst, protocol, payload) = ip_payload(&bytes);
        assert_eq!(
            (src, dst, protocol),
            (destination.ip(), source.ip(), IpProtocol::Udp)
        );
        let packet = UdpPacket::new_checked(payload).unwrap();
        UdpRepr::parse(
            &packet,
            &src.into(),
            &dst.into(),
            &ChecksumCapabilities::default(),
        )
        .unwrap();
        assert_eq!(packet.payload(), data);
        assert_eq!(
            (packet.src_port(), packet.dst_port()),
            (destination.port(), source.port())
        );
    }
    // Both the truncated IP packet and checksum-invalid UDP are now rejected
    // and counted at admission, before either can consume an endpoint slot.
    assert_eq!(stack.stats.snapshot().malformed_packets, 2);
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn ipv4_udp_empty_datagram_bad_packet_and_reply() {
    udp_roundtrip(false).await;
}

#[tokio::test]
async fn ipv6_udp_empty_datagram_bad_packet_and_reply() {
    udp_roundtrip(true).await;
}

#[tokio::test]
async fn mtu_validation_and_shutdown_work_with_full_egress() {
    let mut stack = spawn(TunConfig {
        queue_capacity: 1,
        ..TunConfig::default()
    })
    .unwrap();
    assert_eq!(
        stack.ingress.send(vec![0; 1501]).await.unwrap_err().kind(),
        std::io::ErrorKind::InvalidInput
    );
    let source = "192.0.2.10:40000".parse().unwrap();
    let destination = "203.0.113.20:443".parse().unwrap();
    stack
        .ingress
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
    wait_received(&stack, 1).await;
    // Keep egress and accepted-stream channels undrained while shutting down.
    timeout(WAIT, stack.control.shutdown())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(stack.stats.snapshot().active_tcp_flows, 0);
    assert!(stack.ingress.send(vec![0x40]).await.is_err());
}

#[test]
fn invalid_memory_budget_is_rejected_before_spawn() {
    let config = TunConfig {
        max_tcp_flows: 4096,
        tcp_buffer_bytes: 1024 * 1024,
        ..TunConfig::default()
    };
    assert!(config.validate().is_err());
}

#[test]
fn ipv4_udp_admission_buffer_is_included_in_memory_budget() {
    // The previous payload budget left 5,770 bytes below 1 GiB. The fixed
    // 65,535-byte raw admission buffer must reject this before allocation.
    let config = TunConfig {
        mtu: 1280,
        max_tcp_flows: 4092,
        max_udp_endpoints: 1,
        tcp_buffer_bytes: 65541,
        udp_buffer_bytes: 65536,
        queue_capacity: 1,
        ..TunConfig::default()
    };
    assert_eq!(
        config.validate().unwrap_err().to_string(),
        "TUN socket budget exceeds 1 GiB"
    );
}

async fn fragmented_udp(v6: bool) {
    let (source, destination) = if v6 {
        ("[2001:db8::10]:40000", "[2001:db8::20]:4444")
    } else {
        ("192.0.2.10:40000", "203.0.113.20:4444")
    };
    let source: SocketAddr = source.parse().unwrap();
    let destination: SocketAddr = destination.parse().unwrap();
    let mut output = spawn(TunConfig {
        queue_capacity: 2,
        ..TunConfig::default()
    })
    .unwrap();
    let mut input = spawn(TunConfig::default()).unwrap();
    let payload: Vec<u8> = (0..5000).map(|i| (i % 251) as u8).collect();
    output
        .udp_reply
        .send(UdpDatagram {
            source,
            destination,
            payload: payload.clone(),
        })
        .await
        .unwrap();
    let mut packets = Vec::new();
    let mut expected_offset = 0;
    let mut identity = None;
    loop {
        let bytes = timeout(WAIT, output.egress.recv()).await.unwrap().unwrap();
        assert!(bytes.len() <= 1500);
        let (offset, more, id, data_len) = if v6 {
            let p = Ipv6Packet::new_checked(&bytes[..]).unwrap();
            assert_eq!(p.next_header(), IpProtocol::Ipv6Frag);
            assert_eq!(bytes[40], 17);
            let bits = u16::from_be_bytes([bytes[42], bytes[43]]);
            let id = u32::from_be_bytes(bytes[44..48].try_into().unwrap());
            (
                usize::from(bits >> 3) * 8,
                bits & 1 != 0,
                id,
                bytes.len() - 48,
            )
        } else {
            let p = Ipv4Packet::new_checked(&bytes[..]).unwrap();
            assert!(p.verify_checksum());
            (
                usize::from(p.frag_offset()),
                p.more_frags(),
                u32::from(p.ident()),
                p.payload().len(),
            )
        };
        assert_eq!(offset, expected_offset);
        if more {
            assert_eq!(data_len % 8, 0);
        }
        if let Some(first_id) = identity {
            assert_eq!(id, first_id);
        } else {
            identity = Some(id);
        }
        expected_offset += data_len;
        packets.push(bytes);
        if !more {
            break;
        }
    }
    assert_eq!(expected_offset, payload.len() + 8);
    assert!(packets.len() > 1);
    // Exercise out-of-order reassembly; the transport header arrives last.
    for bytes in packets.into_iter().rev() {
        input.ingress.send(bytes).await.unwrap();
    }
    let received = timeout(WAIT, input.udp.recv()).await.unwrap().unwrap();
    assert_eq!(
        received,
        UdpDatagram {
            source,
            destination,
            payload
        }
    );
    input.shutdown().await.unwrap();
    output.shutdown().await.unwrap();
}

#[tokio::test]
async fn ipv4_udp_fragmentation_and_out_of_order_reassembly() {
    fragmented_udp(false).await;
}

#[tokio::test]
async fn ipv6_udp_fragmentation_and_out_of_order_reassembly() {
    fragmented_udp(true).await;
}

fn ipv4_fragments(bytes: &[u8], identity: u16) -> Vec<Vec<u8>> {
    let original = Ipv4Packet::new_checked(bytes).unwrap();
    original
        .payload()
        .chunks(1480)
        .enumerate()
        .map(|(index, payload)| {
            let offset = index * 1480;
            let mut bytes = ip_packet(
                original.src_addr().into(),
                original.dst_addr().into(),
                original.next_header(),
                payload,
            );
            let mut packet = Ipv4Packet::new_unchecked(&mut bytes[..]);
            packet.set_ident(identity);
            packet.set_more_frags(offset + payload.len() < original.payload().len());
            packet.set_frag_offset(offset as u16);
            packet.fill_checksum();
            bytes
        })
        .collect()
}

#[tokio::test]
async fn ipv4_udp_first_fragment_does_not_reserve_endpoint_before_reassembly() {
    let source = "192.0.2.10:40000".parse().unwrap();
    let incomplete = "203.0.113.20:4444".parse().unwrap();
    let valid = "203.0.113.21:5555".parse().unwrap();
    let mut stack = spawn(TunConfig {
        max_udp_endpoints: 1,
        ..TunConfig::default()
    })
    .unwrap();
    let fragments = ipv4_fragments(&udp_packet(source, incomplete, &vec![42; 5000]), 100);
    stack.ingress.send(fragments[0].clone()).await.unwrap();
    stack
        .ingress
        .send(udp_packet(source, valid, b"complete"))
        .await
        .unwrap();
    assert_eq!(
        timeout(WAIT, stack.udp.recv())
            .await
            .expect("an incomplete first fragment consumed endpoint capacity")
            .unwrap(),
        UdpDatagram {
            source,
            destination: valid,
            payload: b"complete".to_vec(),
        }
    );
    assert_eq!(stack.stats.snapshot().active_udp_endpoints, 1);
    assert_eq!(stack.stats.snapshot().dropped_udp_datagrams, 0);
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn ipv4_udp_bad_reassembled_checksum_does_not_consume_endpoint_capacity() {
    let source = "192.0.2.10:40000".parse().unwrap();
    let invalid = "203.0.113.20:4444".parse().unwrap();
    let valid = "203.0.113.21:5555".parse().unwrap();
    for reverse in [false, true] {
        let mut stack = spawn(TunConfig {
            max_udp_endpoints: 1,
            ..TunConfig::default()
        })
        .unwrap();
        let mut bytes = udp_packet(source, invalid, &vec![42; 5000]);
        *bytes.last_mut().unwrap() ^= 1;
        let mut fragments = ipv4_fragments(&bytes, 101);
        if reverse {
            fragments.reverse();
        }
        for fragment in fragments {
            stack.ingress.send(fragment).await.unwrap();
        }
        stack
            .ingress
            .send(udp_packet(source, valid, b"valid-after-bad-checksum"))
            .await
            .unwrap();
        assert_eq!(
            timeout(WAIT, stack.udp.recv())
                .await
                .expect("bad reassembled UDP consumed endpoint capacity")
                .unwrap(),
            UdpDatagram {
                source,
                destination: valid,
                payload: b"valid-after-bad-checksum".to_vec(),
            }
        );
        assert_eq!(stack.stats.snapshot().active_udp_endpoints, 1);
        assert_eq!(stack.stats.snapshot().malformed_packets, 1);
        assert_eq!(stack.stats.snapshot().dropped_udp_datagrams, 0);
        stack.shutdown().await.unwrap();
    }
}

#[tokio::test]
async fn ipv4_udp_reassembled_new_and_existing_endpoint_deliver_exactly_once() {
    let source = "192.0.2.10:40000".parse().unwrap();
    let destination = "203.0.113.20:4444".parse().unwrap();
    let mut stack = spawn(TunConfig {
        max_udp_endpoints: 1,
        ..TunConfig::default()
    })
    .unwrap();
    for (identity, reverse) in [(102, false), (103, true)] {
        let payload: Vec<u8> = (0..5000).map(|index| (index % 251) as u8).collect();
        let mut fragments = ipv4_fragments(&udp_packet(source, destination, &payload), identity);
        if reverse {
            fragments.reverse();
        }
        for fragment in fragments {
            stack.ingress.send(fragment).await.unwrap();
        }
        stack
            .ingress
            .send(udp_packet(source, destination, &[]))
            .await
            .unwrap();
        stack
            .ingress
            .send(udp_packet(source, destination, b"marker"))
            .await
            .unwrap();
        for payload in [payload, vec![], b"marker".to_vec()] {
            assert_eq!(
                timeout(WAIT, stack.udp.recv()).await.unwrap().unwrap(),
                UdpDatagram {
                    source,
                    destination,
                    payload,
                }
            );
        }
    }
    assert_eq!(stack.stats.snapshot().active_udp_endpoints, 1);
    assert_eq!(stack.stats.snapshot().malformed_packets, 0);
    assert_eq!(stack.stats.snapshot().dropped_udp_datagrams, 0);
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn malformed_syn_checksum_does_not_consume_flow_capacity() {
    let mut stack = spawn(TunConfig {
        max_tcp_flows: 1,
        ..TunConfig::default()
    })
    .unwrap();
    let source = "192.0.2.10:40000".parse().unwrap();
    let destination = "203.0.113.20:443".parse().unwrap();
    let mut packet = tcp_packet(source, destination, 100, None, TcpControl::Syn, &[]);
    packet[36] ^= 1;
    stack.ingress.send(packet).await.unwrap();
    wait_received(&stack, 1).await;
    assert_eq!(stack.stats.snapshot().active_tcp_flows, 0);
    assert_eq!(stack.stats.snapshot().malformed_packets, 1);
    let _flow = handshake(&mut stack, source, destination).await;
    assert_eq!(stack.stats.snapshot().active_tcp_flows, 1);
    stack.shutdown().await.unwrap();
}

async fn malformed_udp_preserves_endpoint_capacity(v6: bool) {
    let source: SocketAddr = if v6 {
        "[2001:db8::10]:40000"
    } else {
        "192.0.2.10:40000"
    }
    .parse()
    .unwrap();
    let destination: SocketAddr = if v6 {
        "[2001:db8::20]:4444"
    } else {
        "203.0.113.20:4444"
    }
    .parse()
    .unwrap();
    let valid_destination = SocketAddr::new(destination.ip(), 5555);
    for malformed in 0..4 {
        let mut stack = spawn(TunConfig {
            max_udp_endpoints: 1,
            ..TunConfig::default()
        })
        .unwrap();
        let bytes = udp_packet(source, destination, b"payload");
        let (_, _, _, payload) = ip_payload(&bytes);
        let mut payload = payload.to_vec();
        match malformed {
            0 => payload[8] ^= 1, // Incorrect nonzero checksum.
            1 => UdpPacket::new_unchecked(&mut payload[..]).set_len(7),
            2 => UdpPacket::new_unchecked(&mut payload[..]).set_len(1024),
            3 => payload.truncate(4), // Ports alone must not admit a socket.
            _ => unreachable!(),
        }
        stack
            .ingress
            .send(ip_packet(
                source.ip(),
                destination.ip(),
                IpProtocol::Udp,
                &payload,
            ))
            .await
            .unwrap();
        stack
            .ingress
            .send(udp_packet(source, valid_destination, b"valid"))
            .await
            .unwrap();
        let datagram = timeout(WAIT, stack.udp.recv())
            .await
            .expect("malformed UDP exhausted endpoint capacity")
            .unwrap();
        assert_eq!(
            datagram,
            UdpDatagram {
                source,
                destination: valid_destination,
                payload: b"valid".to_vec(),
            }
        );
        assert_eq!(stack.stats.snapshot().malformed_packets, 1);
        assert_eq!(stack.stats.snapshot().active_udp_endpoints, 1);
        stack.shutdown().await.unwrap();
    }
}

#[tokio::test]
async fn ipv4_malformed_udp_does_not_reserve_endpoint_capacity() {
    malformed_udp_preserves_endpoint_capacity(false).await;
}

#[tokio::test]
async fn ipv6_malformed_udp_does_not_reserve_endpoint_capacity() {
    malformed_udp_preserves_endpoint_capacity(true).await;
}

#[tokio::test]
async fn ipv4_udp_checksum_may_be_omitted_but_ipv6_checksum_is_required() {
    for v6 in [false, true] {
        let source: SocketAddr = if v6 {
            "[2001:db8::10]:40000"
        } else {
            "192.0.2.10:40000"
        }
        .parse()
        .unwrap();
        let destination: SocketAddr = if v6 {
            "[2001:db8::20]:4444"
        } else {
            "203.0.113.20:4444"
        }
        .parse()
        .unwrap();
        let mut stack = spawn(TunConfig::default()).unwrap();
        let mut bytes = udp_packet(source, destination, b"no-checksum");
        let offset = if v6 { 40 } else { 20 };
        UdpPacket::new_unchecked(&mut bytes[offset..]).set_checksum(0);
        stack.ingress.send(bytes).await.unwrap();
        if v6 {
            wait_received(&stack, 1).await;
            assert_eq!(stack.stats.snapshot().malformed_packets, 1);
            assert_eq!(stack.stats.snapshot().active_udp_endpoints, 0);
            assert!(stack.udp.try_recv().is_err());
        } else {
            assert_eq!(
                timeout(WAIT, stack.udp.recv()).await.unwrap().unwrap(),
                UdpDatagram {
                    source,
                    destination,
                    payload: b"no-checksum".to_vec(),
                }
            );
        }
        stack.shutdown().await.unwrap();
    }
}

#[tokio::test]
async fn simultaneous_clients_to_one_destination_are_isolated() {
    let mut stack = spawn(TunConfig::default()).unwrap();
    let s1 = "192.0.2.10:40000".parse().unwrap();
    let s2 = "192.0.2.11:40000".parse().unwrap();
    let dst = "203.0.113.20:443".parse().unwrap();
    stack
        .ingress
        .send(tcp_packet(s1, dst, 100, None, TcpControl::Syn, &[]))
        .await
        .unwrap();
    stack
        .ingress
        .send(tcp_packet(s2, dst, 100, None, TcpControl::Syn, &[]))
        .await
        .unwrap();
    for _ in 0..2 {
        let syn_ack = next_tcp(&mut stack).await;
        stack
            .ingress
            .send(tcp_packet(
                syn_ack.destination,
                dst,
                101,
                Some(syn_ack.sequence.wrapping_add(1)),
                TcpControl::Psh,
                if syn_ack.destination == s1 {
                    b"one"
                } else {
                    b"two"
                },
            ))
            .await
            .unwrap();
    }
    for _ in 0..2 {
        let mut flow = timeout(WAIT, stack.tcp.recv()).await.unwrap().unwrap();
        let mut bytes = [0; 3];
        timeout(WAIT, flow.stream.read_exact(&mut bytes))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(&bytes, if flow.source == s1 { b"one" } else { b"two" });
    }
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn dispatcher_failure_before_client_ack_sends_reset() {
    let mut stack = spawn(TunConfig::default()).unwrap();
    let source = "192.0.2.10:40000".parse().unwrap();
    let destination = "203.0.113.20:443".parse().unwrap();
    stack
        .ingress
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
    assert_eq!(next_tcp(&mut stack).await.control, TcpControl::Syn);
    let flow = timeout(WAIT, stack.tcp.recv()).await.unwrap().unwrap();
    // This is what a failed PROXY dial / REJECT does: no DIRECT fallback.
    drop(flow);
    assert_eq!(next_tcp(&mut stack).await.control, TcpControl::Rst);
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn megabyte_reply_with_small_buffers_and_queue_preserves_every_byte() {
    let mut stack = spawn(TunConfig {
        tcp_buffer_bytes: 4096,
        queue_capacity: 2,
        ..TunConfig::default()
    })
    .unwrap();
    let source = "192.0.2.10:40000".parse().unwrap();
    let destination = "203.0.113.20:443".parse().unwrap();
    let (mut stream, mut next) = handshake(&mut stack, source, destination).await;
    let expected: Vec<u8> = (0..1024 * 1024).map(|i| (i % 251) as u8).collect();
    let sent = expected.clone();
    let writer = tokio::spawn(async move {
        stream.write_all(&sent).await.unwrap();
        stream.shutdown().await.unwrap();
    });
    let mut received = Vec::new();
    loop {
        let segment = next_tcp(&mut stack).await;
        if !segment.payload.is_empty() {
            assert_eq!(segment.sequence, next);
            next = next.wrapping_add(segment.payload.len() as i32);
            received.extend_from_slice(&segment.payload);
        }
        let finished = segment.control == TcpControl::Fin;
        if finished {
            next = next.wrapping_add(1);
        }
        stack
            .ingress
            .send(tcp_packet(
                source,
                destination,
                101,
                Some(next),
                TcpControl::None,
                &[],
            ))
            .await
            .unwrap();
        if finished {
            break;
        }
    }
    assert_eq!(received, expected);
    timeout(WAIT, writer).await.unwrap().unwrap();
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn gateway_tcp_payload_and_dns_reply_return_to_original_client_tuple() {
    let mut stack = spawn(gateway_config()).unwrap();
    let source: SocketAddr = "192.168.77.10:50000".parse().unwrap();
    let target: SocketAddr = "203.0.113.20:443".parse().unwrap();
    let (mut stream, server_next) = handshake(&mut stack, source, target).await;
    stack
        .ingress
        .send(tcp_packet(
            source,
            target,
            101,
            Some(server_next),
            TcpControl::Psh,
            b"gateway-data",
        ))
        .await
        .unwrap();
    let mut data = [0; 12];
    timeout(WAIT, stream.read_exact(&mut data))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(&data, b"gateway-data");
    stream.write_all(b"return-path").await.unwrap();
    loop {
        let packet = next_tcp(&mut stack).await;
        if packet.payload.is_empty() {
            continue;
        }
        assert_eq!((packet.source, packet.destination), (target, source));
        assert_eq!(packet.payload, b"return-path");
        stack
            .ingress
            .send(tcp_packet(
                source,
                target,
                113,
                Some(packet.sequence.wrapping_add(packet.payload.len() as i32)),
                TcpControl::None,
                &[],
            ))
            .await
            .unwrap();
        break;
    }
    // The synthetic DNS endpoint is captured by TUN but is not an assigned
    // host management address. Both clients keep their own transaction tuple.
    let dns: SocketAddr = "198.18.0.2:53".parse().unwrap();
    for (source, identifier) in [("192.168.77.10:50100", 0x11), ("192.168.77.11:50100", 0x22)] {
        let source: SocketAddr = source.parse().unwrap();
        let query = [
            0, identifier, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, b'a', 0, 0, 1, 0, 1,
        ];
        stack
            .ingress
            .send(udp_packet(source, dns, &query))
            .await
            .unwrap();
        let packet = timeout(WAIT, stack.udp.recv()).await.unwrap().unwrap();
        assert_eq!((packet.source, packet.destination), (source, dns));
        assert_eq!(packet.payload, query);
        let mut answer = packet.payload;
        answer[2] = 0x81;
        answer[3] = 0x80;
        stack
            .udp_reply
            .send(UdpDatagram {
                source: dns,
                destination: source,
                payload: answer.clone(),
            })
            .await
            .unwrap();
        loop {
            let bytes = timeout(WAIT, stack.egress.recv()).await.unwrap().unwrap();
            let (src, dst, protocol, payload) = ip_payload(&bytes);
            if protocol != IpProtocol::Udp {
                continue;
            }
            let packet = UdpPacket::new_checked(payload).unwrap();
            assert_eq!(
                (src, dst, packet.src_port(), packet.dst_port()),
                (dns.ip(), source.ip(), 53, source.port())
            );
            assert_eq!(packet.payload(), answer);
            break;
        }
    }
    drop(stream);
    stack.shutdown().await.unwrap();
}

#[tokio::test]
async fn gateway_cannot_emit_unsolicited_udp_reply_to_unadmitted_client() {
    let mut stack = spawn(gateway_config()).unwrap();
    stack
        .udp_reply
        .send(UdpDatagram {
            source: "203.0.113.20:443".parse().unwrap(),
            destination: "192.168.77.10:50000".parse().unwrap(),
            payload: b"unsolicited".to_vec(),
        })
        .await
        .unwrap();
    timeout(WAIT, async {
        while stack.stats.snapshot().denied_gateway_packets == 0 {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    assert_eq!(stack.stats.snapshot().active_udp_endpoints, 0);
    assert!(stack.egress.try_recv().is_err());
    stack.shutdown().await.unwrap();
}
