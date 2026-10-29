//! TUN flows enter the same `route` and `connect` path as SOCKS. There is no
//! second local proxy hop and no DIRECT fallback after a proxy or reject.
use std::{net::IpAddr, sync::Arc, time::Duration};

use swirl_protocol::Target as NetworkTarget;
use swirl_subscription::Outbound;
use swirl_tun::{Action, Chunk, Decision, Dispatch, FlowMeta, Pipe, Pull, Push, UdpPipe, UdpReply};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    sync::mpsc,
};

use super::{Core, Shared, route};

pub(super) fn engine(
    core: &Core,
    proxies: Vec<IpAddr>,
    leak_protection: bool,
) -> super::Result<swirl_tun::Engine> {
    let runtime = core.runtime.as_ref().ok_or("CoreStopped")?;
    let (dns, association) = swirl_tun::TableDns::fake(Duration::from_secs(60));
    let dispatch = TunDispatch {
        handle: runtime.handle().clone(),
        shared: core.shared.clone(),
    };
    swirl_tun::Engine::new(
        Box::new(dispatch),
        Box::new(dns),
        association,
        swirl_tun::LoopGuard::new(proxies),
        leak_protection,
    )
}

struct TunDispatch {
    handle: tokio::runtime::Handle,
    shared: Arc<Shared>,
}

impl Dispatch for TunDispatch {
    fn open_tcp(
        &mut self,
        meta: &FlowMeta,
    ) -> std::result::Result<(Decision, Box<dyn Pipe>), &'static str> {
        let shared = self.shared.clone();
        let meta = meta.clone();
        let (decision, mut upstream) = self
            .handle
            .block_on(async move { connect_tcp(&shared, &meta).await })?;
        let (upload, mut upload_rx) = mpsc::channel(8);
        let (download_tx, download_rx) = mpsc::channel(8);
        self.handle.spawn(async move {
            let mut buffer = [0; 2048];
            loop {
                tokio::select! {
                    incoming = upload_rx.recv() => match incoming {
                        Some(Chunk::Data(bytes)) => {
                            if upstream.write_all(&bytes).await.is_err() {
                                break;
                            }
                        }
                        Some(Chunk::Shutdown) | None => {
                            let _ = upstream.shutdown().await;
                            break;
                        }
                    },
                    read = upstream.read(&mut buffer) => match read {
                        Ok(0) => {
                            let _ = download_tx.send(Chunk::Shutdown).await;
                            break;
                        }
                        Ok(size) => {
                            if download_tx.send(Chunk::Data(buffer[..size].to_vec())).await.is_err() {
                                break;
                            }
                        }
                        Err(_) => break,
                    },
                }
            }
        });
        Ok((
            decision,
            Box::new(TokioPipe {
                upload,
                download: std::sync::Mutex::new(download_rx),
            }),
        ))
    }

    fn open_udp(&mut self, meta: &FlowMeta) -> std::result::Result<Box<dyn UdpPipe>, &'static str> {
        let shared = self.shared.clone();
        let destination = meta.destination;
        let meta = meta.clone();
        let decision = self
            .handle
            .block_on(async move { route_udp(&shared, &meta).await })?;
        let bind = if destination.is_ipv4() {
            "0.0.0.0:0"
        } else {
            "[::]:0"
        };
        let socket = self
            .handle
            .block_on(tokio::net::UdpSocket::bind(bind))
            .map_err(|_| "UdpBind")?;
        let (upload, mut upload_rx) = mpsc::channel::<Vec<u8>>(8);
        let (replies, download) = mpsc::channel(8);
        self.handle.spawn(async move {
            let mut buffer = [0u8; 2048];
            loop {
                tokio::select! {
                    incoming = upload_rx.recv() => {
                        let Some(bytes) = incoming else { break };
                        if socket.send_to(&bytes, destination).await.is_err() {
                            break;
                        }
                    }
                    incoming = socket.recv_from(&mut buffer) => {
                        let Ok((size, source)) = incoming else { break };
                        if replies
                            .send(UdpReply {
                                source,
                                payload: buffer[..size].to_vec(),
                            })
                            .await
                            .is_err()
                        {
                            break;
                        }
                    }
                }
            }
        });
        Ok(Box::new(TokioUdp {
            decision,
            upload,
            download: std::sync::Mutex::new(download),
        }))
    }
}

async fn connect_tcp(
    shared: &Shared,
    meta: &FlowMeta,
) -> super::Result<(Decision, swirl_transport::BoxStream)> {
    let routed = routed(shared, meta).await?;
    if matches!(routed.node.outbound, Outbound::Reject {}) {
        return Err("Rejected");
    }
    if routed.target.port == shared.address.port()
        && routed
            .target
            .host
            .parse::<IpAddr>()
            .ok()
            .is_some_and(|ip| ip.is_loopback())
    {
        return Err("ProxyLoop");
    }
    let decision = decision_of(&routed);
    let upstream = if let Some(transport) = &routed.transport {
        swirl_protocol::connect_with_transport(
            &routed.node.outbound,
            &routed.target,
            &routed.resolver,
            routed.limit,
            transport,
        )
        .await?
    } else {
        swirl_protocol::connect(
            &routed.node.outbound,
            &routed.target,
            &routed.resolver,
            routed.limit,
        )
        .await?
    };
    Ok((decision, upstream))
}

async fn route_udp(shared: &Shared, meta: &FlowMeta) -> super::Result<Decision> {
    let routed = routed(shared, meta).await?;
    if matches!(routed.node.outbound, Outbound::Reject {}) {
        return Err("Rejected");
    }
    if !matches!(routed.node.outbound, Outbound::Direct {}) {
        return Err("UdpProxyUnsupportedOrRejected");
    }
    Ok(decision_of(&routed))
}

async fn routed(shared: &Shared, meta: &FlowMeta) -> super::Result<super::Routed> {
    let (plan, generation) = shared.admit().await?;
    let host = meta
        .domain
        .clone()
        .unwrap_or_else(|| meta.destination.ip().to_string());
    route(
        plan,
        NetworkTarget {
            host,
            port: meta.destination.port(),
        },
        meta.source.ip(),
        generation,
    )
    .await
}

fn decision_of(routed: &super::Routed) -> Decision {
    let action = if matches!(routed.node.outbound, Outbound::Direct {}) {
        Action::Direct
    } else {
        Action::Proxy
    };
    Decision {
        action,
        rule_id: routed
            .trace
            .get("rule_id")
            .and_then(|value| value.as_str())
            .unwrap_or("tun")
            .to_owned(),
        node_id: routed.node.id.clone(),
    }
}

struct TokioUdp {
    decision: Decision,
    upload: mpsc::Sender<Vec<u8>>,
    download: std::sync::Mutex<mpsc::Receiver<UdpReply>>,
}

impl UdpPipe for TokioUdp {
    fn push(&mut self, payload: &[u8]) -> bool {
        self.upload.try_send(payload.to_vec()).is_ok()
    }

    fn pull(&mut self) -> Option<UdpReply> {
        self.download
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .try_recv()
            .ok()
    }

    fn decision(&self) -> &Decision {
        &self.decision
    }
}

struct TokioPipe {
    upload: mpsc::Sender<Chunk>,
    download: std::sync::Mutex<mpsc::Receiver<Chunk>>,
}

impl Pipe for TokioPipe {
    fn push_upstream(&mut self, chunk: Chunk) -> Push {
        match self.upload.try_send(chunk) {
            Ok(()) => Push::Queued,
            Err(mpsc::error::TrySendError::Full(chunk)) => Push::Full(chunk),
            Err(mpsc::error::TrySendError::Closed(_)) => Push::Closed,
        }
    }

    fn pull_downstream(&mut self) -> Pull {
        match self
            .download
            .get_mut()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .try_recv()
        {
            Ok(chunk) => Pull::Chunk(chunk),
            Err(mpsc::error::TryRecvError::Empty) => Pull::Empty,
            Err(mpsc::error::TryRecvError::Disconnected) => Pull::Closed,
        }
    }
}

#[cfg(test)]
mod tests {
    use std::{
        io::{Read, Write},
        net::{TcpListener, TcpStream, UdpSocket},
        sync::{
            Arc,
            atomic::{AtomicUsize, Ordering},
        },
        thread,
        time::{Duration, Instant},
    };

    use swirl_subscription::{
        Dns, Limits, Matcher, Node, Outbound,
        v2::{
            ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, Mode, PolicyDocument, PolicyRule,
            Target,
        },
    };
    use swirl_tun::{
        VirtualClient,
        packet::{self, Packet},
    };

    use super::super::{Core, RuntimeConfig};

    const STORE: &str = "40000000-0000-4000-8000-0000000000a1";
    const START: &str = "50000000-0000-4000-8000-0000000000a1";
    const NODE: &str = "10000000-0000-4000-8000-0000000000a1";

    fn policy(mode: Mode, target: Target) -> PolicyDocument {
        PolicyDocument {
            schema: 2,
            mode,
            default_policy: DefaultPolicy {
                id: DEFAULT_POLICY_ID.into(),
                target,
            },
            service_policies: Vec::new(),
            groups: Vec::new(),
            explicit_direct_rules: Vec::new(),
            custom_rules: Vec::new(),
            missing_targets: Vec::new(),
            classification_dns: ClassificationDns::Disabled,
        }
    }

    fn runtime(nodes: Vec<Node>, mode: Mode, target: Target) -> RuntimeConfig {
        RuntimeConfig {
            schema: 2,
            listen: "127.0.0.1:0".parse().unwrap(),
            nodes,
            policy: policy(mode, target),
            dns: Dns::default(),
            inbound_auth: None,
            limits: Limits {
                handshake_timeout_ms: 800,
                ..Limits::default()
            },
            china_rules_directory: None,
            node_sources: std::collections::BTreeMap::new(),
            transports: std::collections::BTreeMap::new(),
        }
    }

    fn exchange(engine: &mut swirl_tun::Engine, client: &mut VirtualClient) {
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
    fn direct_tcp_and_udp_use_core_and_reject_does_not_dial() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let echo = listener.local_addr().unwrap();
        let stop = Arc::new(AtomicUsize::new(0));
        let flag = stop.clone();
        let echo_task = thread::spawn(move || {
            listener.set_nonblocking(true).unwrap();
            let deadline = Instant::now() + Duration::from_secs(3);
            while Instant::now() < deadline && flag.load(Ordering::Relaxed) == 0 {
                let Ok((mut stream, _)) = listener.accept() else {
                    thread::sleep(Duration::from_millis(5));
                    continue;
                };
                stream.set_nonblocking(false).unwrap();
                stream
                    .set_read_timeout(Some(Duration::from_secs(2)))
                    .unwrap();
                let mut buffer = [0; 64];
                if let Ok(size) = stream.read(&mut buffer)
                    && size > 0
                {
                    let _ = stream.write_all(&buffer[..size]);
                }
            }
        });
        let udp = UdpSocket::bind("127.0.0.1:0").unwrap();
        let udp_address = udp.local_addr().unwrap();
        thread::spawn(move || {
            udp.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
            let mut buffer = [0; 64];
            if let Ok((size, from)) = udp.recv_from(&mut buffer) {
                let _ = udp.send_to(&buffer[..size], from);
            }
        });
        let core = Core::start(
            runtime(Vec::new(), Mode::Direct, Target::Unconfigured {}),
            STORE.into(),
            1,
            START.into(),
        )
        .unwrap();
        let mut engine = core.open_tun_engine(Vec::new(), true).unwrap();
        let source = "10.0.0.2:41000".parse().unwrap();
        let mut client = VirtualClient::connect(source, echo).unwrap();
        for _ in 0..50 {
            exchange(&mut engine, &mut client);
            if client.established() && engine.tcp_flows() == 1 {
                break;
            }
        }
        assert!(client.established());
        assert_eq!(engine.tcp_flows(), 1);
        client.send(b"tun-core");
        let mut reply = Vec::new();
        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline && reply != b"tun-core" {
            exchange(&mut engine, &mut client);
            reply.extend(client.recv());
            thread::sleep(Duration::from_millis(5));
        }
        assert_eq!(reply, b"tun-core");

        engine
            .push(&packet::udp(source, udp_address, b"udp", 9).unwrap())
            .unwrap();
        let mut udp_reply = Vec::new();
        for _ in 0..40 {
            for packet in engine.poll() {
                if let Ok(Packet::Udp { payload, .. }) = packet::parse(&packet) {
                    udp_reply = payload;
                }
            }
            if udp_reply == b"udp" {
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        assert_eq!(udp_reply, b"udp");
        assert_eq!(engine.stats().udp_open, 1);

        drop(engine);
        drop(core);
        let mut rejected_runtime = runtime(
            vec![Node {
                id: NODE.into(),
                outbound: Outbound::HttpConnect {
                    host: "127.0.0.1".into(),
                    port: 1,
                    auth: None,
                    tls: None,
                },
            }],
            Mode::Rule,
            Target::Node { id: NODE.into() },
        );
        rejected_runtime.policy.custom_rules.push(PolicyRule {
            id: "60000000-0000-4000-8000-0000000000a2".into(),
            name: "Reject documentation range".into(),
            enabled: true,
            priority: 0,
            matcher: Matcher::Cidr {
                value: "203.0.113.0/24".parse().unwrap(),
                resolve: false,
            },
            target: Target::Reject {},
        });
        let rejected_core = Core::start(
            rejected_runtime,
            "40000000-0000-4000-8000-0000000000a2".into(),
            1,
            "50000000-0000-4000-8000-0000000000a2".into(),
        )
        .unwrap();
        let mut rejected = rejected_core.open_tun_engine(Vec::new(), true).unwrap();
        let mut client = VirtualClient::connect(
            "10.0.0.3:41001".parse().unwrap(),
            "203.0.113.50:443".parse().unwrap(),
        )
        .unwrap();
        for _ in 0..40 {
            exchange(&mut rejected, &mut client);
            if rejected.stats().tcp_reject == 1 {
                break;
            }
        }
        assert_eq!(rejected.stats().tcp_reject, 1);
        assert_eq!(rejected.stats().tcp_open, 0);
        stop.store(1, Ordering::Relaxed);
        let _ = TcpStream::connect(echo);
        let _ = echo_task.join();
    }

    #[test]
    fn proxy_failure_is_not_a_direct_dial() {
        let core = Core::start(
            runtime(
                vec![Node {
                    id: NODE.into(),
                    outbound: Outbound::HttpConnect {
                        host: "127.0.0.1".into(),
                        port: 1,
                        auth: None,
                        tls: None,
                    },
                }],
                Mode::Global,
                Target::Node { id: NODE.into() },
            ),
            "40000000-0000-4000-8000-0000000000a3".into(),
            1,
            "50000000-0000-4000-8000-0000000000a3".into(),
        )
        .unwrap();
        let mut engine = core.open_tun_engine(Vec::new(), true).unwrap();
        let mut client = VirtualClient::connect(
            "10.0.0.4:41002".parse().unwrap(),
            "203.0.113.60:443".parse().unwrap(),
        )
        .unwrap();
        for _ in 0..40 {
            exchange(&mut engine, &mut client);
            if engine.stats().tcp_fail == 1 {
                break;
            }
        }
        assert_eq!(engine.stats().tcp_fail, 1);
        assert_eq!(engine.stats().tcp_open, 0);
        engine
            .push(
                &packet::udp(
                    "10.0.0.4:41003".parse().unwrap(),
                    "203.0.113.70:53".parse().unwrap(),
                    b"no",
                    1,
                )
                .unwrap(),
            )
            .unwrap();
        // Port 53 is captured by leak protection before UDP dispatch.
        engine.poll();
        assert_eq!(engine.stats().udp_open, 0);
        engine
            .push(
                &packet::udp(
                    "10.0.0.4:41004".parse().unwrap(),
                    "203.0.113.70:2408".parse().unwrap(),
                    b"no",
                    2,
                )
                .unwrap(),
            )
            .unwrap();
        engine.poll();
        assert_eq!(engine.stats().udp_drop, 1);
    }
}
