//! Bounded native proxy relay sessions owned by one inbound UDP association. Failed
//! node entries remain closed, so later datagrams cannot reconnect or replay.
use super::{SessionPlan, transient_udp, udp_drop};
use std::{
    collections::HashMap,
    net::SocketAddr,
    sync::{Arc, atomic::Ordering},
    time::{Duration, Instant},
};
use swirl_dns::Resolver;
use swirl_protocol::{Socks5UdpAssociation, Target, Transport};
use swirl_subscription::{Node, Outbound};
use swirl_transport::Counters;
use tokio::{
    net::UdpSocket,
    sync::{OwnedSemaphorePermit, mpsc, watch},
    task::JoinSet,
};

const SESSION_LIMIT: usize = 16;
const QUEUE_LIMIT: usize = 4;

struct Datagram {
    target: Target,
    payload: Vec<u8>,
    // Shared with route preparation and all other UDP workers. At most four
    // client datagrams can be preparing, queued or awaiting a send in total.
    _permit: OwnedSemaphorePermit,
}

pub(super) struct Reply {
    packet: Vec<u8>,
    payload_len: usize,
    alive: watch::Receiver<()>,
    cancellation: Option<watch::Receiver<bool>>,
}

impl Reply {
    pub async fn send_to(mut self, relay: &UdpSocket, client: SocketAddr) -> Result<usize, ()> {
        // A reply queued before EOF must not be forwarded after its worker has
        // observed closure. Sender drop also wakes this branch on cancellation.
        tokio::select! {
            biased;
            _ = cancelled(&mut self.cancellation) => Err(()),
            _ = self.alive.changed() => Err(()),
            sent = relay.send_to(&self.packet, client) => sent.map(|_| self.payload_len).map_err(|_| ()),
        }
    }
}

pub(super) struct Pool {
    nodes: HashMap<(String, Option<String>, u64), mpsc::Sender<Datagram>>,
    workers: JoinSet<()>,
    replies: mpsc::Receiver<Reply>,
    reply_sender: mpsc::Sender<Reply>,
    plan: Option<Arc<SessionPlan>>,
    counters: Arc<Counters>,
    total: Arc<Counters>,
}

pub(super) struct Flow {
    pub plan: Arc<SessionPlan>,
    pub generation: u64,
    pub node_id: String,
    pub cancellation: Option<watch::Receiver<bool>>,
}

struct ConnectPlan {
    node: Node,
    resolver: Arc<Resolver>,
    transport: Option<Transport>,
    limit: Duration,
    cancellation: Option<watch::Receiver<bool>>,
}

impl Pool {
    pub fn new(plan: Arc<SessionPlan>, counters: Arc<Counters>, total: Arc<Counters>) -> Self {
        let mut pool = Self::dynamic(counters, total);
        pool.plan = Some(plan);
        pool
    }

    pub fn dynamic(counters: Arc<Counters>, total: Arc<Counters>) -> Self {
        let (reply_sender, replies) = mpsc::channel(QUEUE_LIMIT);
        Self {
            nodes: HashMap::new(),
            workers: JoinSet::new(),
            replies,
            reply_sender,
            plan: None,
            counters,
            total,
        }
    }

    pub fn send(
        &mut self,
        node_id: String,
        target: Target,
        payload: Vec<u8>,
        permit: OwnedSemaphorePermit,
    ) {
        let Some(plan) = self.plan.clone() else {
            udp_drop(&self.counters, &self.total);
            return;
        };
        self.send_with_plan(
            Flow {
                plan,
                generation: 0,
                node_id,
                cancellation: None,
            },
            target,
            payload,
            permit,
        );
    }

    pub fn send_with_plan(
        &mut self,
        flow: Flow,
        target: Target,
        payload: Vec<u8>,
        permit: OwnedSemaphorePermit,
    ) {
        let Flow {
            plan,
            generation,
            node_id,
            cancellation,
        } = flow;
        if cancellation
            .as_ref()
            .is_some_and(|cancel| *cancel.borrow() || cancel.has_changed().is_err())
        {
            udp_drop(&self.counters, &self.total);
            return;
        }
        let Some(node) = plan.config.nodes.iter().find(|node| node.id == node_id) else {
            udp_drop(&self.counters, &self.total);
            return;
        };
        // Classic VLESS UDP binds its stream to one destination. Include that
        // destination in the same bounded pool, never reuse a different target.
        let key = (
            node_id,
            matches!(node.outbound, Outbound::Vless { .. }).then(|| target.authority()),
            generation,
        );
        if !self.nodes.contains_key(&key) {
            if self.nodes.len() >= SESSION_LIMIT {
                udp_drop(&self.counters, &self.total);
                return;
            }
            let (sender, receiver) = mpsc::channel(QUEUE_LIMIT);
            let selected = ConnectPlan {
                node: node.clone(),
                resolver: plan.resolver.clone(),
                transport: plan.transports.get(&node.id).cloned(),
                limit: Duration::from_millis(plan.config.limits.handshake_timeout_ms),
                cancellation,
            };
            self.workers.spawn(run(
                selected,
                target.clone(),
                receiver,
                self.reply_sender.clone(),
                self.counters.clone(),
                self.total.clone(),
            ));
            self.nodes.insert(key.clone(), sender);
        }
        let message = Datagram {
            target,
            payload,
            _permit: permit,
        };
        if self.nodes[&key].try_send(message).is_err() {
            udp_drop(&self.counters, &self.total);
        }
    }

    pub async fn next_reply(&mut self) -> Option<Reply> {
        loop {
            tokio::select! {
                reply = self.replies.recv() => return reply,
                Some(_) = self.workers.join_next(), if !self.workers.is_empty() => {
                    // Keep the closed sender as a bounded tombstone. There is
                    // no implicit reconnect in an existing inbound association.
                }
            }
        }
    }

    pub async fn shutdown(&mut self) {
        self.plan = None;
        self.nodes.clear();
        self.workers.abort_all();
        while self.workers.join_next().await.is_some() {}
        while self.replies.try_recv().is_ok() {}
    }
}

async fn run(
    plan: ConnectPlan,
    first_target: Target,
    mut requests: mpsc::Receiver<Datagram>,
    replies: mpsc::Sender<Reply>,
    counters: Arc<Counters>,
    total: Arc<Counters>,
) {
    if !matches!(plan.node.outbound, Outbound::Socks5 { .. }) {
        run_proxy(plan, first_target, requests, replies, counters, total).await;
        return;
    }
    let ConnectPlan {
        node,
        resolver,
        transport,
        limit,
        mut cancellation,
    } = plan;
    let association = tokio::select! {
        biased;
        _ = cancelled(&mut cancellation) => { discard_pending(&mut requests, &counters, &total); return; },
        result = Socks5UdpAssociation::connect(&node.outbound, &resolver, limit) => result,
    };
    drop(node);
    drop(resolver);
    drop(transport);
    let Ok(association) = association else {
        discard_pending(&mut requests, &counters, &total);
        return;
    };
    let mut buffer = [0u8; 65535];
    let mut last_send: Option<Instant> = None;
    let (_lifetime, alive) = watch::channel(());
    loop {
        tokio::select! {
            // Observe a ready control EOF before accepting more payload. The
            // send method checks the TCP socket again immediately before UDP.
            biased;
            _ = cancelled(&mut cancellation) => break,
            _ = association.closed() => break,
            request = requests.recv() => {
                let Some(request) = request else { break; };
                let sent = tokio::select! {
                    biased;
                    _ = cancelled(&mut cancellation) => break,
                    code = association.closed() => Err(code),
                    result = association.send(&request.target, &request.payload) => result,
                };
                match sent {
                    Ok(()) => {
                        last_send = Some(Instant::now());
                        let size = request.payload.len() as u64;
                        counters.upload.fetch_add(size, Ordering::Relaxed);
                        total.upload.fetch_add(size, Ordering::Relaxed);
                    }
                    Err(code) => {
                        udp_drop(&counters, &total);
                        if matches!(code, "Socks5UdpControlClosed" | "Socks5UdpControlData") { break; }
                    }
                }
            }
            packet = association.recv(&mut buffer) => {
                let n = match packet {
                    Ok(n) => n,
                    Err(e) if transient_udp(&e) => { udp_drop(&counters, &total); continue; }
                    Err(_) => break,
                };
                if !last_send.is_some_and(|at| at.elapsed() < Duration::from_secs(30)) {
                    udp_drop(&counters, &total);
                    continue;
                }
                let Ok((_, payload)) = Socks5UdpAssociation::decode_datagram(&buffer[..n]).await else {
                    udp_drop(&counters, &total);
                    continue;
                };
                let reply = Reply { payload_len: payload.len(), packet: buffer[..n].to_vec(), alive: alive.clone(), cancellation: cancellation.clone() };
                if replies.try_send(reply).is_err() {
                    udp_drop(&counters, &total);
                }
            }
        }
    }
    discard_pending(&mut requests, &counters, &total);
}

enum ProxyAssociation {
    Hysteria2(swirl_protocol::hysteria2::UdpAssociation),
    Tuic(swirl_protocol::tuic::UdpAssociation),
    Shadowsocks2022(Box<swirl_protocol::ss2022::UdpAssociation>),
    Stream(swirl_protocol::stream_udp::UdpAssociation),
}

impl ProxyAssociation {
    async fn connect(
        outbound: &Outbound,
        resolver: &Resolver,
        transport: Option<&Transport>,
        target: &Target,
        limit: Duration,
    ) -> Result<Self, &'static str> {
        match outbound {
            Outbound::Hysteria2(config) => Ok(Self::Hysteria2(
                swirl_protocol::hysteria2::UdpAssociation::connect(config, resolver, limit).await?,
            )),
            Outbound::Tuic(config) => Ok(Self::Tuic(
                swirl_protocol::tuic::UdpAssociation::connect(config, resolver, limit).await?,
            )),
            Outbound::Shadowsocks {
                host,
                port,
                password,
                cipher,
                udp: true,
                ..
            } if cipher.starts_with("2022-") => Ok(Self::Shadowsocks2022(Box::new(
                swirl_protocol::ss2022::UdpAssociation::connect(
                    host, *port, password, cipher, resolver, limit,
                )
                .await?,
            ))),
            outbound @ (Outbound::Vless { udp: true, .. } | Outbound::Trojan { udp: true, .. }) => {
                Ok(Self::Stream(
                    swirl_protocol::stream_udp::UdpAssociation::connect(
                        outbound, target, resolver, limit, transport,
                    )
                    .await?,
                ))
            }
            _ => Err("UdpProxyUnsupportedOrRejected"),
        }
    }

    async fn send(&mut self, target: &Target, payload: &[u8]) -> Result<(), &'static str> {
        match self {
            Self::Hysteria2(value) => value.send(target, payload).await,
            Self::Tuic(value) => value.send(target, payload).await,
            Self::Shadowsocks2022(value) => value.send(target, payload).await,
            Self::Stream(value) => value.send(target, payload).await,
        }
    }

    async fn recv(&mut self) -> Result<(Target, Vec<u8>), &'static str> {
        match self {
            Self::Hysteria2(value) => value.recv().await,
            Self::Tuic(value) => value.recv().await,
            Self::Shadowsocks2022(value) => value.recv().await,
            Self::Stream(value) => value.recv().await,
        }
    }
}

async fn run_proxy(
    plan: ConnectPlan,
    first_target: Target,
    mut requests: mpsc::Receiver<Datagram>,
    replies: mpsc::Sender<Reply>,
    counters: Arc<Counters>,
    total: Arc<Counters>,
) {
    let ConnectPlan {
        node,
        resolver,
        transport,
        limit,
        mut cancellation,
    } = plan;
    let connected = tokio::select! {
        biased;
        _ = cancelled(&mut cancellation) => { discard_pending(&mut requests, &counters, &total); return; },
        result = ProxyAssociation::connect(&node.outbound, &resolver, transport.as_ref(), &first_target, limit) => result,
    };
    drop(node);
    drop(resolver);
    drop(transport);
    let Ok(mut association) = connected else {
        discard_pending(&mut requests, &counters, &total);
        return;
    };
    let (_lifetime, alive) = watch::channel(());
    let mut last_send: Option<Instant> = None;
    loop {
        tokio::select! {
            biased;
            _ = cancelled(&mut cancellation) => break,
            request = requests.recv() => {
                let Some(request) = request else { break; };
                // A stream-mode UDP send can await flow-control credit. Bound
                // that wait and retain the shared permit until it finishes.
                let sent = tokio::select! {
                    biased;
                    _ = cancelled(&mut cancellation) => break,
                    result = tokio::time::timeout(limit, association.send(&request.target, &request.payload)) => result,
                };
                if !matches!(sent, Ok(Ok(()))) {
                    udp_drop(&counters, &total);
                    break;
                }
                last_send = Some(Instant::now());
                let size = request.payload.len() as u64;
                counters.upload.fetch_add(size, Ordering::Relaxed);
                total.upload.fetch_add(size, Ordering::Relaxed);
            }
            response = association.recv() => {
                let Ok((target, payload)) = response else { break; };
                if !last_send.is_some_and(|at| at.elapsed() < Duration::from_secs(30)) {
                    udp_drop(&counters, &total);
                    continue;
                }
                let Ok(packet) = Socks5UdpAssociation::encode_datagram(&target, &payload) else {
                    udp_drop(&counters, &total);
                    continue;
                };
                if packet.len() > 65507 {
                    udp_drop(&counters, &total);
                    continue;
                }
                if replies.try_send(Reply { packet, payload_len: payload.len(), alive: alive.clone(), cancellation: cancellation.clone() }).is_err() {
                    udp_drop(&counters, &total);
                }
            }
        }
    }
    discard_pending(&mut requests, &counters, &total);
}

fn discard_pending(requests: &mut mpsc::Receiver<Datagram>, counters: &Counters, total: &Counters) {
    requests.close();
    while requests.try_recv().is_ok() {
        udp_drop(counters, total);
    }
}

async fn cancelled(cancellation: &mut Option<watch::Receiver<bool>>) {
    let Some(cancellation) = cancellation else {
        return std::future::pending().await;
    };
    loop {
        if *cancellation.borrow_and_update() {
            return;
        }
        if cancellation.changed().await.is_err() {
            return;
        }
    }
}

#[cfg(test)]
#[path = "socks5_udp_tests.rs"]
mod tests;
