//! Bounded native proxy relay sessions owned by one inbound UDP association. Failed
//! node entries remain closed, so later datagrams cannot reconnect or replay.
use super::{SessionPlan, transient_udp, udp_drop};
use std::{
    collections::HashMap,
    net::SocketAddr,
    sync::{Arc, atomic::Ordering},
    time::{Duration, Instant},
};
use swirl_protocol::{Socks5UdpAssociation, Target};
use swirl_subscription::Outbound;
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
}

impl Reply {
    pub async fn send_to(mut self, relay: &UdpSocket, client: SocketAddr) -> Result<usize, ()> {
        // A reply queued before EOF must not be forwarded after its worker has
        // observed closure. Sender drop also wakes this branch on cancellation.
        tokio::select! {
            biased;
            _ = self.alive.changed() => Err(()),
            sent = relay.send_to(&self.packet, client) => sent.map(|_| self.payload_len).map_err(|_| ()),
        }
    }
}

pub(super) struct Pool {
    nodes: HashMap<String, mpsc::Sender<Datagram>>,
    workers: JoinSet<()>,
    replies: mpsc::Receiver<Reply>,
    reply_sender: mpsc::Sender<Reply>,
    plan: Arc<SessionPlan>,
    counters: Arc<Counters>,
    total: Arc<Counters>,
}

impl Pool {
    pub fn new(plan: Arc<SessionPlan>, counters: Arc<Counters>, total: Arc<Counters>) -> Self {
        let (reply_sender, replies) = mpsc::channel(QUEUE_LIMIT);
        Self {
            nodes: HashMap::new(),
            workers: JoinSet::new(),
            replies,
            reply_sender,
            plan,
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
        if !self.nodes.contains_key(&node_id) {
            if self.nodes.len() >= SESSION_LIMIT {
                udp_drop(&self.counters, &self.total);
                return;
            }
            let Some(index) = self.plan.config.nodes.iter().position(|n| n.id == node_id) else {
                udp_drop(&self.counters, &self.total);
                return;
            };
            let (sender, receiver) = mpsc::channel(QUEUE_LIMIT);
            self.workers.spawn(run(
                self.plan.clone(),
                index,
                receiver,
                self.reply_sender.clone(),
                self.counters.clone(),
                self.total.clone(),
            ));
            self.nodes.insert(node_id.clone(), sender);
        }
        let message = Datagram {
            target,
            payload,
            _permit: permit,
        };
        if self.nodes[&node_id].try_send(message).is_err() {
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
}

async fn run(
    plan: Arc<SessionPlan>,
    index: usize,
    mut requests: mpsc::Receiver<Datagram>,
    replies: mpsc::Sender<Reply>,
    counters: Arc<Counters>,
    total: Arc<Counters>,
) {
    if matches!(
        plan.config.nodes[index].outbound,
        Outbound::Hysteria2(_) | Outbound::Tuic(_)
    ) {
        run_quic(plan, index, requests, replies, counters, total).await;
        return;
    }
    let association = Socks5UdpAssociation::connect(
        &plan.config.nodes[index].outbound,
        &plan.resolver,
        Duration::from_millis(plan.config.limits.handshake_timeout_ms),
    )
    .await;
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
            _ = association.closed() => break,
            request = requests.recv() => {
                let Some(request) = request else { break; };
                let sent = tokio::select! {
                    biased;
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
                let reply = Reply { payload_len: payload.len(), packet: buffer[..n].to_vec(), alive: alive.clone() };
                if replies.try_send(reply).is_err() {
                    udp_drop(&counters, &total);
                }
            }
        }
    }
    discard_pending(&mut requests, &counters, &total);
}

enum QuicAssociation {
    Hysteria2(swirl_protocol::hysteria2::UdpAssociation),
    Tuic(swirl_protocol::tuic::UdpAssociation),
}

impl QuicAssociation {
    async fn connect(plan: &SessionPlan, index: usize) -> Result<Self, &'static str> {
        let limit = Duration::from_millis(plan.config.limits.handshake_timeout_ms);
        match &plan.config.nodes[index].outbound {
            Outbound::Hysteria2(config) => Ok(Self::Hysteria2(
                swirl_protocol::hysteria2::UdpAssociation::connect(config, &plan.resolver, limit)
                    .await?,
            )),
            Outbound::Tuic(config) => Ok(Self::Tuic(
                swirl_protocol::tuic::UdpAssociation::connect(config, &plan.resolver, limit)
                    .await?,
            )),
            _ => Err("UdpProxyUnsupportedOrRejected"),
        }
    }

    async fn send(&self, target: &Target, payload: &[u8]) -> Result<(), &'static str> {
        match self {
            Self::Hysteria2(value) => value.send(target, payload).await,
            Self::Tuic(value) => value.send(target, payload).await,
        }
    }

    async fn recv(&mut self) -> Result<(Target, Vec<u8>), &'static str> {
        match self {
            Self::Hysteria2(value) => value.recv().await,
            Self::Tuic(value) => value.recv().await,
        }
    }
}

async fn run_quic(
    plan: Arc<SessionPlan>,
    index: usize,
    mut requests: mpsc::Receiver<Datagram>,
    replies: mpsc::Sender<Reply>,
    counters: Arc<Counters>,
    total: Arc<Counters>,
) {
    let Ok(mut association) = QuicAssociation::connect(&plan, index).await else {
        discard_pending(&mut requests, &counters, &total);
        return;
    };
    let (_lifetime, alive) = watch::channel(());
    let mut last_send: Option<Instant> = None;
    loop {
        tokio::select! {
            request = requests.recv() => {
                let Some(request) = request else { break; };
                // A stream-mode UDP send can await flow-control credit. Bound
                // that wait and retain the shared permit until it finishes.
                let sent = tokio::time::timeout(
                    Duration::from_millis(plan.config.limits.handshake_timeout_ms),
                    association.send(&request.target, &request.payload),
                ).await;
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
                if replies.try_send(Reply { packet, payload_len: payload.len(), alive: alive.clone() }).is_err() {
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

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn queued_reply_cannot_outlive_its_control_worker() {
        let relay = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let client = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let (lifetime, alive) = watch::channel(());
        let reply = Reply {
            packet: b"must-not-forward".to_vec(),
            payload_len: 16,
            alive,
        };
        drop(lifetime);
        assert!(
            reply
                .send_to(&relay, client.local_addr().unwrap())
                .await
                .is_err()
        );
        let mut bytes = [0; 32];
        assert!(
            tokio::time::timeout(Duration::from_millis(50), client.recv_from(&mut bytes))
                .await
                .is_err()
        );
    }
}
