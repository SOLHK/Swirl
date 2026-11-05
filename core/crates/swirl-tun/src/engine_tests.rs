use std::{
    net::{IpAddr, Ipv4Addr, SocketAddr},
    sync::{
        Arc, Mutex,
        atomic::{AtomicUsize, Ordering},
    },
    time::Duration,
};

use swirl_dns::{AAAA, DNS_A, DNS_IPV4, DnsQuestion, decode_answers, encode_query};

use crate::{
    Engine,
    dispatch::{Action, ChannelPipe, ChannelUdp, Chunk, Decision, Dispatch, FlowMeta, UdpReply},
    dns_flow::TableDns,
    guard::LoopGuard,
    packet::{self, Packet},
    stack::VirtualClient,
};

type TcpEnds = (
    std::sync::mpsc::SyncSender<Chunk>,
    std::sync::mpsc::Receiver<Chunk>,
);
type UdpEnds = (
    std::sync::mpsc::SyncSender<UdpReply>,
    std::sync::mpsc::Receiver<Vec<u8>>,
);

struct Lab {
    metas: Arc<Mutex<Vec<FlowMeta>>>,
    opens: Arc<AtomicUsize>,
    tcp: Arc<Mutex<Vec<TcpEnds>>>,
    udp: Arc<Mutex<Vec<UdpEnds>>>,
    tcp_error: Option<&'static str>,
    udp_error: Option<&'static str>,
    bound: usize,
}

impl Lab {
    fn new() -> Self {
        Self {
            metas: Arc::new(Mutex::new(Vec::new())),
            opens: Arc::new(AtomicUsize::new(0)),
            tcp: Arc::new(Mutex::new(Vec::new())),
            udp: Arc::new(Mutex::new(Vec::new())),
            tcp_error: None,
            udp_error: None,
            bound: 8,
        }
    }
}

impl Dispatch for Lab {
    fn open_tcp(
        &mut self,
        meta: &FlowMeta,
    ) -> Result<(Decision, Box<dyn crate::Pipe>), &'static str> {
        self.opens.fetch_add(1, Ordering::Relaxed);
        self.metas.lock().expect("lab").push(meta.clone());
        if let Some(code) = self.tcp_error {
            return Err(code);
        }
        let (pipe, download, upload) = ChannelPipe::pair(self.bound);
        self.tcp.lock().expect("lab").push((download, upload));
        Ok((
            Decision {
                action: Action::Proxy,
                rule_id: "lab".into(),
                node_id: "node-a".into(),
            },
            Box::new(pipe),
        ))
    }

    fn open_udp(&mut self, meta: &FlowMeta) -> Result<Box<dyn crate::UdpPipe>, &'static str> {
        self.metas.lock().expect("lab").push(meta.clone());
        if let Some(code) = self.udp_error {
            return Err(code);
        }
        let decision = Decision {
            action: Action::Direct,
            rule_id: "lab-udp".into(),
            node_id: "node-u".into(),
        };
        let (pipe, download, upload) = ChannelUdp::pair(decision, self.bound);
        self.udp.lock().expect("lab").push((download, upload));
        Ok(Box::new(pipe))
    }
}

fn engine(lab: Lab, leak: bool) -> (Engine, Lab) {
    let view = Lab {
        metas: lab.metas.clone(),
        opens: lab.opens.clone(),
        tcp: lab.tcp.clone(),
        udp: lab.udp.clone(),
        tcp_error: None,
        udp_error: None,
        bound: lab.bound,
    };
    let (dns, association) = TableDns::fake(Duration::from_secs(60));
    let built = Engine::new(
        Box::new(lab),
        Box::new(dns),
        association,
        LoopGuard::new([ip("203.0.113.10")]),
        leak,
    )
    .expect("engine");
    (built, view)
}

fn ip(text: &str) -> IpAddr {
    text.parse().unwrap()
}

fn exchange(engine: &mut Engine, client: &mut VirtualClient) {
    for packet in client.poll() {
        engine.push(&packet).expect("client packet");
    }
    for packet in engine.poll() {
        client.push(&packet);
    }
    client.advance(20);
    engine.advance(20);
}

#[test]
fn tcp_reuses_one_decision_and_returns_the_proxy_bytes() {
    let lab = Lab::new();
    let opens = lab.opens.clone();
    let tcp = lab.tcp.clone();
    let metas = lab.metas.clone();
    let (mut engine, _) = engine(lab, true);
    let source: SocketAddr = "10.0.0.2:40000".parse().unwrap();
    let destination: SocketAddr = "1.2.3.4:443".parse().unwrap();
    let mut client = VirtualClient::connect(source, destination).unwrap();
    for _ in 0..40 {
        exchange(&mut engine, &mut client);
        if client.established() && engine.tcp_flows() == 1 {
            break;
        }
    }
    assert!(client.established());
    assert_eq!(engine.tcp_flows(), 1);
    assert_eq!(opens.load(Ordering::Relaxed), 1);
    assert_eq!(metas.lock().unwrap()[0].destination, destination);
    let mut payload = vec![0; 4000];
    payload[..4].copy_from_slice(b"ping");
    let mut sent = 0;
    let (download, upload) = tcp.lock().unwrap().pop().unwrap();
    let mut received = Vec::new();
    for _ in 0..80 {
        if sent < payload.len() {
            sent += client.send(&payload[sent..]);
        }
        exchange(&mut engine, &mut client);
        while let Ok(Chunk::Data(buf)) = upload.try_recv() {
            received.extend(buf);
        }
        if received.len() == payload.len() {
            break;
        }
    }
    assert_eq!(received, payload);
    download
        .send(Chunk::Data(b"pong-from-core".to_vec()))
        .unwrap();
    let mut reply = Vec::new();
    for _ in 0..40 {
        exchange(&mut engine, &mut client);
        reply.extend(client.recv());
        if reply == b"pong-from-core" {
            break;
        }
    }
    assert_eq!(reply, b"pong-from-core");
    assert_eq!(opens.load(Ordering::Relaxed), 1);
    assert_eq!(engine.ingress_len(), 0);
    engine.revoke_node("node-a");
    exchange(&mut engine, &mut client);
    exchange(&mut engine, &mut client);
    assert_eq!(engine.tcp_flows(), 0);
}

#[test]
fn rejected_tcp_is_not_retried_as_direct() {
    let mut lab = Lab::new();
    lab.tcp_error = Some("Rejected");
    let (mut engine, _) = engine(lab, true);
    let mut client = VirtualClient::connect(
        "10.0.0.2:40001".parse().unwrap(),
        "1.2.3.4:443".parse().unwrap(),
    )
    .unwrap();
    let syn = client.poll();
    assert!(!syn.is_empty());
    for packet in &syn {
        engine.push(packet).unwrap();
    }
    for _ in 0..40 {
        exchange(&mut engine, &mut client);
        if engine.stats().tcp_reject == 1 {
            break;
        }
    }
    assert_eq!(engine.stats().tcp_reject, 1);
    assert_eq!(engine.stats().tcp_open, 0);
    engine.push(&syn[0]).unwrap();
    engine.poll();
    assert!(engine.stats().tcp_suppressed >= 1);
}

#[test]
fn udp_session_echo_and_dns_leak_use_the_fake_ip_domain() {
    let lab = Lab::new();
    let udp = lab.udp.clone();
    let metas = lab.metas.clone();
    let (mut engine, _) = engine(lab, true);
    let source: SocketAddr = "10.0.0.8:53000".parse().unwrap();
    let foreign: SocketAddr = "8.8.8.8:53".parse().unwrap();
    let question = DnsQuestion {
        id: 7,
        name: "example.com".into(),
        kind: DNS_A,
        recursion_desired: true,
    };
    let query = encode_query(&question).unwrap();
    engine
        .push(&packet::udp(source, foreign, &query, 3).unwrap())
        .unwrap();
    let replies = engine.poll();
    assert_eq!(engine.stats().leak_suppressed, 1);
    assert_eq!(engine.stats().dns_answers, 1);
    assert_eq!(engine.udp_sessions(), 0);
    let Packet::Udp { payload, .. } = packet::parse(&replies[0]).unwrap() else {
        panic!("dns")
    };
    let (id, rcode, answers) = decode_answers(&payload).unwrap();
    assert_eq!((id, rcode), (7, 0));
    assert!(answers[0].to_string().starts_with("198.18."));
    let virtual_dns: SocketAddr = SocketAddr::new(IpAddr::V4(DNS_IPV4), 53);
    let aaaa = DnsQuestion {
        id: 8,
        name: "example.com".into(),
        kind: AAAA,
        recursion_desired: true,
    };
    engine
        .push(&packet::udp(source, virtual_dns, &encode_query(&aaaa).unwrap(), 4).unwrap())
        .unwrap();
    let v6 = engine.poll();
    let Packet::Udp { payload, .. } = packet::parse(&v6[0]).unwrap() else {
        panic!("aaaa")
    };
    let (_, _, v6_answers) = decode_answers(&payload).unwrap();
    assert_eq!(v6_answers[0].to_string().split(':').next().unwrap(), "fd53");

    let destination = SocketAddr::new(answers[0], 443);
    let mut client = VirtualClient::connect(source, destination).unwrap();
    for _ in 0..40 {
        exchange(&mut engine, &mut client);
        if engine.tcp_flows() == 1 {
            break;
        }
    }
    assert_eq!(engine.tcp_flows(), 1);
    assert_eq!(
        metas.lock().unwrap().last().unwrap().domain.as_deref(),
        Some("example.com")
    );

    let udp_dest: SocketAddr = "9.9.9.9:2408".parse().unwrap();
    engine
        .push(&packet::udp(source, udp_dest, b"abc", 5).unwrap())
        .unwrap();
    engine.poll();
    let (reply, upload) = udp.lock().unwrap().pop().unwrap();
    assert_eq!(upload.try_recv().unwrap(), b"abc");
    reply
        .send(UdpReply {
            source: udp_dest,
            payload: b"xyz".into(),
        })
        .unwrap();
    let back = engine.poll();
    let Packet::Udp {
        payload,
        destination: back_dest,
        ..
    } = packet::parse(&back[0]).unwrap()
    else {
        panic!("udp")
    };
    assert_eq!(payload, b"xyz");
    assert_eq!(back_dest, source);
    engine
        .push(&packet::udp(source, "203.0.113.10:443".parse().unwrap(), b"loop", 6).unwrap())
        .unwrap();
    engine
        .push(
            &packet::udp(
                source,
                SocketAddr::new(IpAddr::V4(Ipv4Addr::BROADCAST), 9),
                b"no",
                7,
            )
            .unwrap(),
        )
        .unwrap();
    engine.poll();
    assert_eq!(engine.stats().loop_bypass, 1);
    assert_eq!(engine.stats().loop_reject, 1);
    assert_eq!(engine.udp_sessions(), 1);
}

#[test]
fn ingress_is_bounded_and_stop_drops_new_packets() {
    let (mut engine, _) = engine(Lab::new(), false);
    let byte = [0x45];
    for _ in 0..64 {
        engine.push(&byte).unwrap();
    }
    assert_eq!(engine.push(&byte), Err("TunIngressFull"));
    assert_eq!(engine.ingress_len(), 64);
    engine.poll();
    assert_eq!(engine.ingress_len(), 32);
    assert_eq!(engine.stats().parse_drop, 32);
    engine.poll();
    assert_eq!(engine.ingress_len(), 0);
    assert_eq!(engine.stats().parse_drop, 64);
    engine.stop();
    assert_eq!(engine.push(&byte), Err("TunStopped"));
    assert!(engine.poll().is_empty());
}

#[test]
fn ipv6_tcp_establishes_through_the_same_engine() {
    let (mut engine, _) = engine(Lab::new(), true);
    let source: SocketAddr = "[fd00::2]:41000".parse().unwrap();
    let destination: SocketAddr = "[2001:db8::20]:443".parse().unwrap();
    let mut client = VirtualClient::connect(source, destination).unwrap();
    for _ in 0..40 {
        exchange(&mut engine, &mut client);
        if client.established() && engine.tcp_flows() == 1 {
            break;
        }
    }
    assert!(client.established(), "ipv6 handshake");
    client.send(b"v6");
    exchange(&mut engine, &mut client);
    exchange(&mut engine, &mut client);
    assert_eq!(engine.tcp_flows(), 1);
}

#[test]
fn real_ip_conflict_fails_closed() {
    let (mut dns, association) = TableDns::real(Duration::from_secs(60));
    let shared = "203.0.113.8".parse().unwrap();
    dns.insert_real("one.example", vec![shared]);
    dns.insert_real("two.example", vec![shared]);
    let engine = Engine::new(
        Box::new(Lab::new()),
        Box::new(dns),
        association,
        LoopGuard::new([]),
        true,
    )
    .unwrap();
    let mut engine = engine;
    let source: SocketAddr = "10.0.0.8:53001".parse().unwrap();
    let dns_addr: SocketAddr = "1.1.1.1:53".parse().unwrap();
    let first = DnsQuestion {
        id: 1,
        name: "one.example".into(),
        kind: DNS_A,
        recursion_desired: true,
    };
    engine
        .push(&packet::udp(source, dns_addr, &encode_query(&first).unwrap(), 1).unwrap())
        .unwrap();
    let ok = engine.poll();
    let Packet::Udp { payload, .. } = packet::parse(&ok[0]).unwrap() else {
        panic!("a")
    };
    assert_eq!(decode_answers(&payload).unwrap().1, 0);
    let second = DnsQuestion {
        id: 2,
        name: "two.example".into(),
        kind: DNS_A,
        recursion_desired: true,
    };
    engine
        .push(&packet::udp(source, dns_addr, &encode_query(&second).unwrap(), 2).unwrap())
        .unwrap();
    let bad = engine.poll();
    let Packet::Udp { payload, .. } = packet::parse(&bad[0]).unwrap() else {
        panic!("b")
    };
    assert_eq!(decode_answers(&payload).unwrap().1, 2);
}
