//! Native packet ingress joined to the existing V2 runtime, without a SOCKS hop.
use std::{
    collections::HashMap,
    future::Future,
    net::{IpAddr, SocketAddr},
    pin::Pin,
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    },
    time::Duration,
};
use swirl_core::v2::{FlowDispatcher, NativeTunLease};
use swirl_dns::tun::{TunDns, TunLookup};
use swirl_protocol::Target;
use swirl_tun::{
    PacketSender, TcpFlow, TunConfig, TunControl, TunStats, UdpDatagram, UdpReplySender,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    sync::{mpsc, watch},
    task::{JoinHandle, JoinSet},
    time::{Instant, timeout},
};

type Result<T> = std::result::Result<T, &'static str>;
type UdpKey = (SocketAddr, SocketAddr);
struct UdpSlot {
    id: u64,
    sender: mpsc::Sender<Vec<u8>>,
    failed_until: Option<Instant>,
}
const DNS_IDLE: Duration = Duration::from_secs(30);
const UDP_IDLE: Duration = Duration::from_secs(60);
const UDP_QUEUE: usize = 4;
const DNS_JOBS: usize = 16;

#[derive(Default)]
pub struct BridgeStats {
    pub tcp_failures: AtomicU64,
    pub udp_failures: AtomicU64,
    pub dns_failures: AtomicU64,
    pub udp_dropped: AtomicU64,
}

pub struct PacketBridge {
    pub input: PacketSender,
    pub output: mpsc::Receiver<Vec<u8>>,
    pub stats: TunStats,
    pub bridge_stats: Arc<BridgeStats>,
    pub control: BridgeControl,
}

pub struct BridgeControl {
    stop: watch::Sender<bool>,
    task: Option<JoinHandle<Result<()>>>,
    // Kept after shutdown until the enclosing Windows transaction is restored.
    _dns_lease: NativeTunLease,
}

impl BridgeControl {
    pub async fn shutdown(&mut self) -> Result<()> {
        let _ = self.stop.send(true);
        if let Some(task) = self.task.as_mut() {
            let result = task.await.map_err(|_| "TunBridgeTask");
            self.task = None;
            result??;
        }
        Ok(())
    }

    pub fn request_stop(&self) {
        let _ = self.stop.send(true);
    }
    pub fn is_finished(&self) -> bool {
        self.task.as_ref().is_none_or(|task| task.is_finished())
    }
}

impl Drop for BridgeControl {
    fn drop(&mut self) {
        self.request_stop();
        if let Some(task) = self.task.take() {
            task.abort();
        }
    }
}

/// Creates no driver, routes or DNS settings. Caller provides either an actual
/// Wintun packet pump or a packet harness and retains control until recovery.
pub fn spawn(dispatcher: FlowDispatcher, dns: TunDns, config: TunConfig) -> Result<PacketBridge> {
    config.validate().map_err(|_| "TunLimits")?;
    let lease = dispatcher.prepare_native_tun()?;
    let runtime = dispatcher.runtime_handle();
    let _entered = runtime.enter();
    let stack = swirl_tun::spawn(config.clone()).map_err(|_| "TunStackStart")?;
    let (stop, stopped) = watch::channel(false);
    let bridge_stats = Arc::new(BridgeStats::default());
    let task = runtime.spawn(run(
        stack.tcp,
        stack.udp,
        stack.udp_reply,
        stack.control,
        dispatcher,
        dns,
        config,
        stopped,
        bridge_stats.clone(),
    ));
    Ok(PacketBridge {
        input: stack.ingress,
        output: stack.egress,
        stats: stack.stats,
        bridge_stats,
        control: BridgeControl {
            stop,
            task: Some(task),
            _dns_lease: lease,
        },
    })
}

struct Lookup {
    dispatcher: FlowDispatcher,
    source: SocketAddr,
}
impl TunLookup for Lookup {
    fn lookup<'a>(
        &'a self,
        name: &'a str,
    ) -> Pin<Box<dyn Future<Output = Result<Vec<IpAddr>>> + Send + 'a>> {
        Box::pin(async move {
            self.dispatcher
                .resolve_dns(name, 53, self.source)
                .await
                .map(|addresses| addresses.into_iter().map(|address| address.ip()).collect())
        })
    }
}

async fn tcp(flow: TcpFlow, dispatcher: FlowDispatcher, dns: TunDns) -> Result<()> {
    if flow.destination.port() != 53 {
        let host = dns.target_host(flow.destination.ip()).await?;
        return dispatcher
            .relay_tcp(
                flow.stream,
                flow.source,
                Target {
                    host,
                    port: flow.destination.port(),
                },
            )
            .await;
    }
    let lookup = Lookup {
        dispatcher,
        source: flow.source,
    };
    let mut stream = flow.stream;
    loop {
        let size = match timeout(DNS_IDLE, stream.read_u16()).await {
            Ok(Ok(size)) if (12..=4096).contains(&size) => size,
            Ok(Err(error)) if error.kind() == std::io::ErrorKind::UnexpectedEof => return Ok(()),
            _ => return Err("TunDnsTcpFrame"),
        };
        let mut request = vec![0; usize::from(size)];
        timeout(Duration::from_secs(5), stream.read_exact(&mut request))
            .await
            .map_err(|_| "TunDnsTcpTimeout")?
            .map_err(|_| "TunDnsTcpRead")?;
        let response = dns.answer(&request, &lookup).await?;
        timeout(Duration::from_secs(5), async {
            stream.write_u16(response.len() as u16).await?;
            stream.write_all(&response).await?;
            stream.flush().await
        })
        .await
        .map_err(|_| "TunDnsTcpTimeout")?
        .map_err(|_| "TunDnsTcpWrite")?;
    }
}

async fn udp(
    key: UdpKey,
    mut incoming: mpsc::Receiver<Vec<u8>>,
    replies: UdpReplySender,
    dispatcher: FlowDispatcher,
    dns: TunDns,
) -> Result<()> {
    let host = dns.target_host(key.1.ip()).await?;
    let mut flow = dispatcher
        .open_udp(
            key.0,
            Target {
                host,
                port: key.1.port(),
            },
        )
        .await?;
    let mut buffer = vec![0; 65507];
    let mut expires = Instant::now() + UDP_IDLE;
    loop {
        tokio::select! {
            input = incoming.recv() => {
                let Some(payload) = input else { return Ok(()); };
                flow.send(&payload).await?;
                expires = Instant::now() + UDP_IDLE;
            },
            reply = flow.recv(&mut buffer) => {
                let length = reply?;
                replies.send(UdpDatagram {
                    source: key.1, destination: key.0, payload: buffer[..length].to_vec(),
                }).await.map_err(|_| "TunUdpReply")?;
                expires = Instant::now() + UDP_IDLE;
            },
            _ = tokio::time::sleep_until(expires) => return Ok(()),
        }
    }
}

// Each task returns an optional UDP slot identity. A completed older worker
// cannot evict a newer flow that reused the same original five-tuple.
#[allow(clippy::too_many_arguments)]
async fn run(
    mut tcp_flows: mpsc::Receiver<TcpFlow>,
    mut udp_packets: mpsc::Receiver<UdpDatagram>,
    replies: UdpReplySender,
    mut stack: TunControl,
    dispatcher: FlowDispatcher,
    dns: TunDns,
    config: TunConfig,
    mut stop: watch::Receiver<bool>,
    stats: Arc<BridgeStats>,
) -> Result<()> {
    let mut jobs = JoinSet::new();
    let mut udp_flows: HashMap<UdpKey, UdpSlot> = HashMap::new();
    let mut next = 0u64;
    let dns_slots = Arc::new(tokio::sync::Semaphore::new(DNS_JOBS));
    let max_jobs = config.max_tcp_flows + config.max_udp_endpoints + DNS_JOBS;
    let mut cleanup = tokio::time::interval(Duration::from_secs(1));
    cleanup.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    loop {
        if *stop.borrow() {
            break;
        }
        tokio::select! {
            _ = stop.changed() => break,
            _ = cleanup.tick() => {
                let now = Instant::now();
                udp_flows.retain(|_, slot| slot.failed_until.is_none_or(|expires| expires > now));
            },
            finished = jobs.join_next(), if !jobs.is_empty() => {
                match finished {
                    Some(Ok(Some((key, id, failed)))) if udp_flows.get(&key).is_some_and(|entry| entry.id == id) => {
                        if failed {
                            // A failed/revoked QUIC tuple keeps its chosen-flow
                            // identity until idle expiry. A later packet must
                            // not silently redial against another policy/node.
                            if let Some(slot) = udp_flows.get_mut(&key) { slot.failed_until = Some(Instant::now() + UDP_IDLE); }
                        } else { udp_flows.remove(&key); }
                    },
                    Some(Err(_)) => return Err("TunFlowTask"),
                    _ => {},
                }
            },
            flow = tcp_flows.recv() => {
                let Some(flow) = flow else { break; };
                if jobs.len() >= max_jobs {
                    stats.tcp_failures.fetch_add(1, Ordering::Relaxed);
                    continue;
                }
                let dispatcher = dispatcher.clone();
                let dns = dns.clone();
                let stats = stats.clone();
                jobs.spawn(async move {
                    if tcp(flow, dispatcher, dns).await.is_err() { stats.tcp_failures.fetch_add(1, Ordering::Relaxed); }
                    None
                });
            },
            packet = udp_packets.recv() => {
                let Some(packet) = packet else { break; };
                if packet.destination.port() == 53 {
                    let Ok(permit) = dns_slots.clone().try_acquire_owned() else {
                        stats.udp_dropped.fetch_add(1, Ordering::Relaxed);
                        continue;
                    };
                    if jobs.len() >= max_jobs { stats.udp_dropped.fetch_add(1, Ordering::Relaxed); continue; }
                    let lookup = Lookup { dispatcher: dispatcher.clone(), source: packet.source };
                    let dns = dns.clone();
                    let replies = replies.clone();
                    let stats = stats.clone();
                    jobs.spawn(async move {
                        let _permit = permit;
                        let result = async {
                            let payload = dns.answer(&packet.payload, &lookup).await?;
                            replies.send(UdpDatagram { source: packet.destination, destination: packet.source, payload })
                                .await.map_err(|_| "TunDnsReply")
                        }.await;
                        if result.is_err() { stats.dns_failures.fetch_add(1, Ordering::Relaxed); }
                        None
                    });
                    continue;
                }
                let key = (packet.source, packet.destination);
                if udp_flows.get(&key).is_some_and(|slot| slot.failed_until.is_some() || slot.sender.is_closed()) {
                    stats.udp_dropped.fetch_add(1, Ordering::Relaxed);
                    continue;
                }
                if !udp_flows.contains_key(&key) {
                    if udp_flows.len() >= config.max_udp_endpoints || jobs.len() >= max_jobs {
                        stats.udp_dropped.fetch_add(1, Ordering::Relaxed);
                        continue;
                    }
                    next = next.checked_add(1).ok_or("TunFlowIdExhausted")?;
                    let id = next;
                    let (sender, receiver) = mpsc::channel(UDP_QUEUE);
                    udp_flows.insert(key, UdpSlot { id, sender, failed_until: None });
                    let dispatcher = dispatcher.clone();
                    let dns = dns.clone();
                    let replies = replies.clone();
                    let stats = stats.clone();
                    jobs.spawn(async move {
                        let failed = udp(key, receiver, replies, dispatcher, dns).await.is_err();
                        if failed { stats.udp_failures.fetch_add(1, Ordering::Relaxed); }
                        Some((key, id, failed))
                    });
                }
                if udp_flows.get(&key).is_none_or(|slot| slot.sender.try_send(packet.payload).is_err()) {
                    stats.udp_dropped.fetch_add(1, Ordering::Relaxed);
                }
            },
        }
    }
    jobs.abort_all();
    while jobs.join_next().await.is_some() {}
    stack.shutdown().await.map_err(|_| "TunStackStop")
}

#[cfg(test)]
#[path = "native_tun_tests.rs"]
mod tests;
