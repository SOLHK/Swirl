//! Native ingress for packet-stack adapters. Protocol implementations, policy
//! transactions and accounting remain owned by the existing V2 runtime.
use super::{
    NetworkTarget, Outbound, PolicyDnsTransport, RegisteredSession, Result, Routed, Shared,
    cancelled, connect_tcp_flow, route, route_flow,
};
use crate::socks5_udp::ProxyAssociation;
use std::{
    net::SocketAddr,
    sync::{Arc, atomic::Ordering},
    time::Duration,
};
use swirl_protocol::Socks5UdpAssociation;
use swirl_transport::{Counters, Stream, bind_udp};
use tokio::{
    net::UdpSocket,
    runtime::Handle,
    sync::{mpsc, oneshot, watch},
    task::JoinHandle,
    time::{Instant, timeout},
};

const UDP_QUEUE: usize = 4;
const UDP_MAX_PAYLOAD: usize = 65_507;
const UDP_IDLE: Duration = Duration::from_secs(60);

/// Cloneable ingress handle, without another listener or proxy hop. Every worker
/// runs on the core's existing runtime and shares its connection budget.
#[derive(Clone)]
pub struct FlowDispatcher {
    shared: Arc<Shared>,
    runtime: Handle,
    probe: crate::ProbeRuntime,
}

impl FlowDispatcher {
    pub(super) fn new(shared: Arc<Shared>, runtime: Handle, probe: crate::ProbeRuntime) -> Self {
        Self {
            shared,
            runtime,
            probe,
        }
    }

    /// Schedule a packet-stack adapter on the core's existing Tokio runtime.
    /// This handle does not create a second executor or extend its lifetime.
    pub fn runtime_handle(&self) -> Handle {
        self.runtime.clone()
    }

    /// Relay one established TCP stream from an L3 stack. The caller must retain
    /// this future for the session lifetime. Dropping it aborts and unregisters
    /// the flow; runtime shutdown and node revocation do the same.
    pub async fn relay_tcp<S: Stream + 'static>(
        &self,
        mut inbound: S,
        source: SocketAddr,
        target: NetworkTarget,
    ) -> Result<()> {
        let registered = self.shared.register()?;
        let shared = self.shared.clone();
        let mut task = AbortTask(self.runtime.spawn(async move {
            let id = registered.guard.id;
            let mut cancellation = registered.cancellation.clone();
            let counters = Arc::new(Counters::default());
            let work = async {
                let mut upstream =
                    connect_tcp_flow(&shared, id, source, &target, counters.clone(), true).await?;
                swirl_transport::relay(&mut inbound, &mut upstream, counters, shared.totals.clone())
                    .await
                    .map_err(|error| crate::stream_failure_code(&error))
            };
            let result = tokio::select! {
                biased;
                _ = cancelled(&mut cancellation) => Err("SessionRevoked"),
                result = work => result,
            };
            if let Err(error) = result {
                shared.failure(id, error);
            }
            drop(registered);
            result
        }));
        (&mut task.0).await.map_err(|_| "NativeFlowTask")?
    }

    /// Open a fixed-destination UDP flow. Routing happens once, then each packet
    /// reuses that immutable node/transport. Failures close the flow; there is no
    /// implicit reconnect, replay or DIRECT fallback.
    pub async fn open_udp(
        &self,
        source: SocketAddr,
        target: NetworkTarget,
    ) -> Result<NativeUdpFlow> {
        let registered = self.shared.register()?;
        let (requests, incoming) = mpsc::channel(UDP_QUEUE);
        let (replies, responses) = mpsc::channel(UDP_QUEUE);
        let (ready, started) = oneshot::channel();
        let shared = self.shared.clone();
        // Construct before spawn: shutdown can drop a task before its first
        // poll, and that path still has to publish an authoritative close cause.
        let (mut completion, mut closed) = UdpCompletion::new(shared.clone(), &registered);
        let task = AbortTask(self.runtime.spawn(async move {
            let result = run_udp(
                shared,
                &registered,
                source,
                target,
                incoming,
                replies,
                ready,
            )
            .await;
            completion.finish(result);
            drop(registered);
        }));
        match started.await {
            Ok(result) => result?,
            Err(_) => return Err(udp_closed(&mut closed).await),
        }
        Ok(NativeUdpFlow {
            requests,
            responses,
            closed,
            _task: task,
        })
    }

    /// Resolve a DNS interception query over the same selected V2 outbound. The
    /// encrypted resolver uses fixed bootstrap addresses and has no system or
    /// plaintext fallback. A/AAAA parsing, cache and TLS remain in swirl-dns.
    pub async fn resolve_dns(
        &self,
        host: &str,
        port: u16,
        source: SocketAddr,
    ) -> Result<Vec<SocketAddr>> {
        let registered = self.shared.register()?;
        let shared = self.shared.clone();
        let host = host.to_owned();
        let mut task = AbortTask(self.runtime.spawn(async move {
            let id = registered.guard.id;
            let mut cancellation = registered.cancellation.clone();
            let work = async {
                let (plan, generation) = shared.admit().await?;
                validate_tun_dns(&plan.prepared.runtime)?;
                let routed = route(
                    plan.clone(),
                    NetworkTarget {
                        host: host.clone(),
                        port,
                    },
                    source.ip(),
                    generation,
                )
                .await?;
                shared.bind(id, &routed.node.id)?;
                if matches!(routed.node.outbound, Outbound::Reject {}) {
                    return Err("Rejected");
                }
                let transport = PolicyDnsTransport {
                    node: routed.node,
                    transport: routed.transport,
                    bootstrap: routed.resolver.clone(),
                    limit: routed.limit,
                };
                routed
                    .resolver
                    .resolve_with_transport(&host, port, &transport)
                    .await
            };
            let result = tokio::select! {
                biased;
                _ = cancelled(&mut cancellation) => Err("SessionRevoked"),
                result = work => result,
            };
            if let Err(error) = result {
                shared.failure(id, error);
            }
            drop(registered);
            result
        }));
        (&mut task.0).await.map_err(|_| "NativeFlowTask")?
    }

    /// Validate before acquiring OS routes. Keep the lease until those routes
    /// have been restored; policy transactions cannot downgrade DNS meanwhile.
    pub fn prepare_native_tun(&self) -> Result<NativeTunLease> {
        let live = self.shared.live.lock().map_err(|_| "ConfigState")?;
        if self.shared.stopped.load(Ordering::Acquire) {
            return Err("CoreStopped");
        }
        if live.closed {
            return Err("Reconfiguring");
        }
        validate_tun_dns(&live.plan.prepared.runtime)?;
        let sessions = self.shared.sessions.lock().map_err(|_| "SessionState")?;
        // Only the first lease must exclude old resolver generations. An
        // existing lease already prevents every configuration transaction from
        // installing plaintext/system DNS. A lifecycle controller may retain
        // that constraint while rebuilding a paused packet bridge.
        if self.shared.native_tun_leases.load(Ordering::Acquire) == 0
            && (!sessions.is_empty() || !self.probe.quiescent() || !live.plan.policies.quiescent())
        {
            return Err("TunRequiresQuiescentCore");
        }
        // live + sessions remain locked across this increment. Even if the
        // previous owner concurrently drops the last old lease, no downgrade,
        // new session or manual probe can enter that brief interval. Automatic
        // health jobs register before IO; the Windows controller has already
        // suspended egress, so later jobs cannot create old unbound sockets.
        self.shared.native_tun_leases.fetch_add(1, Ordering::AcqRel);
        Ok(NativeTunLease {
            shared: self.shared.clone(),
        })
    }
}

pub(super) fn validate_tun_dns(config: &super::RuntimeConfig) -> Result<()> {
    if config.dns.tls_servers.is_empty() {
        return Err("DnsEncryptedUpstreamRequired");
    }
    config.dns.validate_tls()
}

/// DNS safety constraint held by a native TUN lifecycle controller. It performs
/// no network/OS mutation; dropping it only releases the configuration constraint.
pub struct NativeTunLease {
    shared: Arc<Shared>,
}
impl Drop for NativeTunLease {
    fn drop(&mut self) {
        self.shared.native_tun_leases.fetch_sub(1, Ordering::AcqRel);
    }
}

struct AbortTask<T>(JoinHandle<T>);
impl<T> Drop for AbortTask<T> {
    fn drop(&mut self) {
        self.0.abort();
    }
}

struct SendRequest {
    payload: Vec<u8>,
    complete: oneshot::Sender<Result<()>>,
}
impl SendRequest {
    fn finish(self, result: Result<()>, counters: &Counters, total: &Counters) -> Result<()> {
        if result.is_ok() {
            let size = self.payload.len() as u64;
            counters.upload.fetch_add(size, Ordering::Relaxed);
            total.upload.fetch_add(size, Ordering::Relaxed);
        }
        // Completion is a publication boundary: an awakened caller must already
        // observe the successful send in both session and aggregate counters.
        let _ = self.complete.send(result);
        result
    }
}

fn queue_udp_response(
    payload: Vec<u8>,
    responses: &mpsc::Sender<Vec<u8>>,
    counters: &Counters,
    total: &Counters,
) -> bool {
    if payload.len() > UDP_MAX_PAYLOAD {
        crate::udp_drop(counters, total);
        return false;
    }
    let Ok(permit) = responses.try_reserve() else {
        // Full and closed queues did not accept the response, so neither may
        // contribute successful download bytes.
        crate::udp_drop(counters, total);
        return false;
    };
    let size = payload.len() as u64;
    counters.download.fetch_add(size, Ordering::Relaxed);
    total.download.fetch_add(size, Ordering::Relaxed);
    // Reserve first, account second, publish last. Once recv observes payload,
    // the channel's synchronization also makes these earlier counts visible.
    permit.send(payload);
    true
}

/// Exactly one terminal state survives data-channel closure, task cancellation
/// and runtime shutdown. Data channels can close before run_udp returns; their
/// EOF is only a signal to wait for this state, not a separate failure cause.
struct UdpCompletion {
    shared: Arc<Shared>,
    id: u64,
    cancellation: watch::Receiver<bool>,
    finished: watch::Sender<Option<&'static str>>,
    published: bool,
}
impl UdpCompletion {
    fn new(
        shared: Arc<Shared>,
        registered: &RegisteredSession,
    ) -> (Self, watch::Receiver<Option<&'static str>>) {
        let (finished, closed) = watch::channel(None);
        (
            Self {
                shared,
                id: registered.guard.id,
                cancellation: registered.cancellation.clone(),
                finished,
                published: false,
            },
            closed,
        )
    }

    fn finish(&mut self, result: Result<()>) {
        if let Err(error) = result {
            self.shared.failure(self.id, error);
        }
        self.finished
            .send_replace(Some(result.err().unwrap_or("UdpFlowClosed")));
        self.published = true;
    }
}
impl Drop for UdpCompletion {
    fn drop(&mut self) {
        if !self.published {
            // Core shutdown may cancel this worker before it can observe the
            // registry's watch notification. Preserve revocation even then.
            let revoked =
                self.shared.stopped.load(Ordering::Acquire) || *self.cancellation.borrow();
            self.finish(if revoked {
                Err("SessionRevoked")
            } else {
                Ok(())
            });
        }
    }
}

/// One connected UDP session. Empty datagrams are valid, responses preserve
/// boundaries, and a small receive buffer is an explicit error, never truncation.
pub struct NativeUdpFlow {
    requests: mpsc::Sender<SendRequest>,
    responses: mpsc::Receiver<Vec<u8>>,
    closed: watch::Receiver<Option<&'static str>>,
    _task: AbortTask<()>,
}
impl NativeUdpFlow {
    pub async fn send(&self, payload: &[u8]) -> Result<()> {
        if payload.len() > UDP_MAX_PAYLOAD {
            return Err("UdpPayloadTooLarge");
        }
        let mut closed = self.closed.clone();
        // Reserve before allocating: competing callers cannot create an
        // unbounded collection of owned queued datagrams.
        let slot = tokio::select! {
            biased;
            error = udp_closed(&mut closed) => return Err(error),
            slot = self.requests.reserve() => match slot {
                Ok(slot) => slot,
                Err(_) => return Err(udp_closed(&mut closed).await),
            },
        };
        let (complete, completion) = oneshot::channel();
        slot.send(SendRequest {
            payload: payload.to_vec(),
            complete,
        });
        tokio::select! {
            biased;
            error = udp_closed(&mut closed) => Err(error),
            result = completion => match result {
                Ok(result) => result,
                Err(_) => Err(udp_closed(&mut closed).await),
            },
        }
    }

    pub async fn recv(&mut self, buffer: &mut [u8]) -> Result<usize> {
        let payload = tokio::select! {
            biased;
            error = udp_closed(&mut self.closed) => return Err(error),
            payload = self.responses.recv() => match payload {
                Some(payload) => payload,
                None => return Err(udp_closed(&mut self.closed).await),
            },
        };
        if payload.len() > buffer.len() {
            return Err("UdpReceiveBufferTooSmall");
        }
        buffer[..payload.len()].copy_from_slice(&payload);
        Ok(payload.len())
    }
}

async fn udp_closed(receiver: &mut watch::Receiver<Option<&'static str>>) -> &'static str {
    loop {
        if let Some(error) = *receiver.borrow_and_update() {
            return error;
        }
        if receiver.changed().await.is_err() {
            return receiver.borrow().unwrap_or("UdpFlowClosed");
        }
    }
}

enum NativeAssociation {
    Direct(UdpSocket),
    Shadowsocks {
        socket: UdpSocket,
        password: String,
        cipher: String,
    },
    Socks5(Socks5UdpAssociation),
    Proxy(Box<ProxyAssociation>),
}
impl NativeAssociation {
    async fn connect(flow: &Routed) -> Result<Self> {
        match &flow.node.outbound {
            Outbound::Direct {} => {
                let address = SocketAddr::new(
                    flow.target.host.parse().map_err(|_| "UdpDirectAddress")?,
                    flow.target.port,
                );
                Ok(Self::Direct(connected_udp(address).await?))
            }
            Outbound::Reject {} => Err("Rejected"),
            outbound @ Outbound::Socks5 { udp: true, .. } => Ok(Self::Socks5(
                Socks5UdpAssociation::connect(outbound, &flow.resolver, flow.limit).await?,
            )),
            Outbound::Shadowsocks {
                host,
                port,
                password,
                cipher,
                udp: true,
                ..
            } if !cipher.starts_with("2022-") => {
                let address = flow
                    .resolver
                    .resolve(host, *port)
                    .await?
                    .into_iter()
                    .next()
                    .ok_or("DnsEmpty")?;
                Ok(Self::Shadowsocks {
                    socket: connected_udp(address).await?,
                    password: password.clone(),
                    cipher: cipher.clone(),
                })
            }
            Outbound::Hysteria2(config) if !config.udp => Err("UdpProxyUnsupportedOrRejected"),
            Outbound::Tuic(config) if !config.udp => Err("UdpProxyUnsupportedOrRejected"),
            _ => Ok(Self::Proxy(Box::new(
                ProxyAssociation::connect(
                    &flow.node.outbound,
                    &flow.resolver,
                    flow.transport.as_ref(),
                    &flow.target,
                    flow.limit,
                )
                .await?,
            ))),
        }
    }

    async fn send(&mut self, target: &NetworkTarget, payload: &[u8]) -> Result<()> {
        match self {
            Self::Direct(socket) => send_datagram(socket, payload).await,
            Self::Shadowsocks {
                socket,
                password,
                cipher,
            } => {
                let mut plaintext = Vec::with_capacity(payload.len() + 260);
                target.encode(&mut plaintext)?;
                plaintext.extend_from_slice(payload);
                let packet = swirl_protocol::ss_encrypt_datagram(password, cipher, &plaintext)
                    .map_err(|_| "UdpEncode")?;
                send_datagram(socket, &packet).await
            }
            Self::Socks5(association) => association.send(target, payload).await,
            Self::Proxy(association) => association.send(target, payload).await,
        }
    }

    async fn recv(&mut self, target: &NetworkTarget, buffer: &mut [u8]) -> Result<Vec<u8>> {
        let (remote, payload) = match self {
            Self::Direct(socket) => {
                let size = socket.recv(buffer).await.map_err(|error| {
                    if crate::transient_udp(&error) {
                        "UdpTransient"
                    } else {
                        "UdpReceive"
                    }
                })?;
                return Ok(buffer[..size].to_vec());
            }
            Self::Shadowsocks {
                socket,
                password,
                cipher,
            } => {
                let size = socket.recv(buffer).await.map_err(|error| {
                    if crate::transient_udp(&error) {
                        "UdpTransient"
                    } else {
                        "UdpReceive"
                    }
                })?;
                let plain = swirl_protocol::ss_decrypt_datagram(password, cipher, &buffer[..size])
                    .map_err(|_| "UdpDecode")?;
                let mut bytes = plain.as_slice();
                let remote = swirl_protocol::read_target(&mut bytes, false).await?;
                (remote, bytes.to_vec())
            }
            Self::Socks5(association) => {
                let size = tokio::select! {
                    biased;
                    code = association.closed() => return Err(code),
                    result = association.recv(buffer) => result.map_err(|error| if crate::transient_udp(&error) { "UdpTransient" } else { "Socks5UdpReceive" })?,
                };
                let (remote, payload) =
                    Socks5UdpAssociation::decode_datagram(&buffer[..size]).await?;
                (remote, payload.to_vec())
            }
            Self::Proxy(association) => association.recv().await?,
        };
        if !response_matches(target, &remote) {
            return Err("UdpResponseTargetMismatch");
        }
        Ok(payload)
    }
}

fn response_matches(request: &NetworkTarget, response: &NetworkTarget) -> bool {
    if request.port != response.port {
        return false;
    }
    match request.host.parse::<std::net::IpAddr>() {
        Ok(expected) => response
            .host
            .parse::<std::net::IpAddr>()
            .ok()
            .is_some_and(|actual| {
                swirl_routing::v2::normalize_ip(expected) == swirl_routing::v2::normalize_ip(actual)
            }),
        // Each association carries exactly one target. A proxy that resolved a
        // domain may return its resulting IP, without a local DNS leakage query.
        Err(_) => {
            request.host.eq_ignore_ascii_case(&response.host)
                || response.host.parse::<std::net::IpAddr>().is_ok()
        }
    }
}

async fn connected_udp(address: SocketAddr) -> Result<UdpSocket> {
    // This association has one known peer. Bind local peers to localhost before
    // pin_udp checks the physical egress guard, as the TCP path already does.
    // Non-loopback destinations must keep wildcard binding and guard checks.
    let local = match (address.is_ipv4(), address.ip().is_loopback()) {
        (true, true) => "127.0.0.1:0",
        (false, true) => "[::1]:0",
        (true, false) => "0.0.0.0:0",
        (false, false) => "[::]:0",
    };
    let socket = bind_udp(local.parse().map_err(|_| "UdpBind")?)
        .await
        .map_err(|_| "UdpBind")?;
    socket.connect(address).await.map_err(|_| "UdpConnect")?;
    Ok(socket)
}
async fn send_datagram(socket: &UdpSocket, payload: &[u8]) -> Result<()> {
    let sent = socket.send(payload).await.map_err(|_| "UdpSend")?;
    if sent != payload.len() {
        return Err("UdpSend");
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
async fn run_udp(
    shared: Arc<Shared>,
    registered: &RegisteredSession,
    source: SocketAddr,
    target: NetworkTarget,
    mut requests: mpsc::Receiver<SendRequest>,
    responses: mpsc::Sender<Vec<u8>>,
    ready: oneshot::Sender<Result<()>>,
) -> Result<()> {
    let id = registered.guard.id;
    let mut cancellation = registered.cancellation.clone();
    let counters = Arc::new(Counters::default());
    let setup = async {
        let routed = route_flow(&shared, id, source, &target, counters.clone(), true).await?;
        let association = timeout(routed.limit, NativeAssociation::connect(&routed))
            .await
            .map_err(|_| "UdpConnectTimeout")??;
        Ok::<_, &'static str>((routed, association))
    };
    let setup = tokio::select! {
        biased;
        _ = cancelled(&mut cancellation) => Err("SessionRevoked"),
        result = setup => result,
    };
    let (routed, mut association) = match setup {
        Ok(ready_flow) => {
            let _ = ready.send(Ok(()));
            ready_flow
        }
        Err(error) => {
            let _ = ready.send(Err(error));
            return Err(error);
        }
    };
    let mut buffer = vec![0; 65_535];
    let mut last_activity = Instant::now();
    loop {
        tokio::select! {
            biased;
            _ = cancelled(&mut cancellation) => return Err("SessionRevoked"),
            _ = tokio::time::sleep_until(last_activity + UDP_IDLE) => return Err("UdpIdleTimeout"),
            request = requests.recv() => {
                let Some(request) = request else { return Ok(()) };
                let sent = tokio::select! {
                    biased;
                    _ = cancelled(&mut cancellation) => Err("SessionRevoked"),
                    result = timeout(routed.limit, association.send(&routed.target, &request.payload)) => result.map_err(|_| "UdpSendTimeout").and_then(|r| r),
                };
                if sent.is_ok() {
                    last_activity = Instant::now();
                }
                request.finish(sent, &counters, &shared.totals)?;
            }
            response = association.recv(&routed.target, &mut buffer) => {
                let payload = match response {
                    Ok(payload) => payload,
                    Err("UdpTransient" | "UdpDecode" | "UdpResponseTargetMismatch" | "Socks5UdpDatagram" | "Socks5UdpFragmentUnsupported") => {
                        crate::udp_drop(&counters, &shared.totals);
                        continue;
                    }
                    Err(error) => return Err(error),
                };
                if queue_udp_response(payload, &responses, &counters, &shared.totals) {
                    last_activity = Instant::now();
                }
            }
        }
    }
}

#[cfg(test)]
#[path = "native_flow_tests.rs"]
mod tests;
