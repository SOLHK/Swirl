//! An additional bounded ingress into the V2 plan, never another runtime or
//! selector. This module owns only listeners, admission and LAN accounting.
use super::*;
use crate::lan::{Cidr, LanConfig};
use std::net::UdpSocket as StdUdpSocket;
use tokio::net::UdpSocket;

const CLIENT_HISTORY_LIMIT: usize = 512;
const AUTH_WINDOW: Duration = Duration::from_secs(60);

#[derive(Clone, Copy)]
enum Protocol {
    Mixed,
    Http,
    Socks,
}

enum Access {
    Private(Vec<Cidr>),
    #[cfg(test)]
    LoopbackFixture,
    // Admits a real loopback client while retaining production endpoint ACLs.
    // Individual peer sockets can be explicitly authorized by test fixtures.
    #[cfg(test)]
    StrictLoopbackFixture,
}

impl Access {
    fn allows(&self, ip: IpAddr) -> bool {
        match self {
            Self::Private(cidrs) => cidrs.iter().any(|cidr| cidr.contains(ip)),
            #[cfg(test)]
            Self::LoopbackFixture | Self::StrictLoopbackFixture => ip.is_loopback(),
        }
    }
}

struct Client {
    sessions: BTreeMap<u64, Arc<Counters>>,
    unauthenticated: BTreeSet<u64>,
    uploaded: u64,
    downloaded: u64,
    auth_window: Instant,
    failures: u32,
    last_seen: Instant,
}

struct Accounting {
    clients: BTreeMap<IpAddr, Client>,
    completed_upload: u64,
    completed_download: u64,
}

struct State {
    config: Arc<LanConfig>,
    access: Access,
    accounting: Mutex<Accounting>,
    accepted: AtomicU64,
    rejected: AtomicU64,
    auth_failures: AtomicU64,
    last_error: Mutex<&'static str>,
    #[cfg(test)]
    fixture_targets: Mutex<BTreeSet<SocketAddr>>,
}

impl State {
    fn session_ids(&self) -> Vec<u64> {
        self.accounting
            .lock()
            .map(|accounting| {
                accounting
                    .clients
                    .values()
                    .flat_map(|client| client.sessions.keys().copied())
                    .collect()
            })
            .unwrap_or_default()
    }

    fn error(&self, code: &'static str) {
        if let Ok(mut error) = self.last_error.lock() {
            *error = code;
        }
    }

    fn admit(self: &Arc<Self>, peer: IpAddr, id: u64) -> Result<ClientLease> {
        if !self.access.allows(peer) {
            return Err("LanClientDenied");
        }
        let mut accounting = self.accounting.lock().map_err(|_| "LanState")?;
        if !accounting.clients.contains_key(&peer)
            && accounting.clients.len() >= CLIENT_HISTORY_LIMIT
        {
            // Never evict an active client or an unexpired authentication
            // penalty; otherwise an attacker could rotate addresses to reset it.
            let oldest = accounting
                .clients
                .iter()
                .filter(|(_, client)| {
                    client.sessions.is_empty() && client.auth_window.elapsed() >= AUTH_WINDOW
                })
                .min_by_key(|(_, client)| client.last_seen)
                .map(|(ip, _)| *ip);
            let Some(oldest) = oldest else {
                return Err("LanClientTableFull");
            };
            accounting.clients.remove(&oldest);
        }
        let client = accounting.clients.entry(peer).or_insert_with(|| Client {
            sessions: BTreeMap::new(),
            unauthenticated: BTreeSet::new(),
            uploaded: 0,
            downloaded: 0,
            auth_window: Instant::now(),
            failures: 0,
            last_seen: Instant::now(),
        });
        if client.auth_window.elapsed() >= AUTH_WINDOW {
            client.failures = 0;
            client.auth_window = Instant::now();
        }
        if client
            .failures
            .saturating_add(client.unauthenticated.len() as u32)
            >= self.config.auth_failures_per_minute
        {
            return Err("LanAuthenticationRateLimit");
        }
        if client.sessions.len() >= self.config.max_connections_per_client {
            return Err("LanClientConnectionLimit");
        }
        let counters = Arc::new(Counters::default());
        client.sessions.insert(id, counters.clone());
        client.unauthenticated.insert(id);
        client.last_seen = Instant::now();
        self.accepted.fetch_add(1, Ordering::Relaxed);
        Ok(ClientLease {
            state: self.clone(),
            peer,
            id,
            counters,
        })
    }

    fn authenticated(&self, peer: IpAddr, id: u64) {
        if let Ok(mut accounting) = self.accounting.lock()
            && let Some(client) = accounting.clients.get_mut(&peer)
        {
            client.unauthenticated.remove(&id);
        }
    }

    fn authentication_failed(&self, peer: IpAddr) {
        self.auth_failures.fetch_add(1, Ordering::Relaxed);
        if let Ok(mut accounting) = self.accounting.lock()
            && let Some(client) = accounting.clients.get_mut(&peer)
        {
            if client.auth_window.elapsed() >= AUTH_WINDOW {
                client.failures = 0;
                client.auth_window = Instant::now();
            }
            client.failures = client.failures.saturating_add(1);
        }
    }

    fn snapshot(&self, running: bool) -> Result<Value> {
        let accounting = self.accounting.lock().map_err(|_| "LanState")?;
        let mut active = 0usize;
        let mut uploaded = accounting.completed_upload;
        let mut downloaded = accounting.completed_download;
        let clients: Vec<_> = accounting
            .clients
            .iter()
            .map(|(ip, client)| {
                let current_upload = client
                    .sessions
                    .values()
                    .map(|c| c.upload.load(Ordering::Relaxed))
                    .sum::<u64>();
                let current_download = client
                    .sessions
                    .values()
                    .map(|c| c.download.load(Ordering::Relaxed))
                    .sum::<u64>();
                active += client.sessions.len();
                uploaded = uploaded.saturating_add(current_upload);
                downloaded = downloaded.saturating_add(current_download);
                json!({"ip":ip.to_string(),"active_connections":client.sessions.len(),
                "uploaded":client.uploaded.saturating_add(current_upload),
                "downloaded":client.downloaded.saturating_add(current_download)})
            })
            .collect();
        Ok(
            json!({"running":running,"ipv4_only":true,"ipv6_targets":true,"encrypted_transport":false,
            "listen_ip":self.config.listen_ip,"http_port":self.config.http_port,
            "socks_port":self.config.socks_port,"udp_port_start":self.config.udp_port_start,
            "udp_port_end":self.config.udp_port_end,"active_connections":active,
            "accepted":self.accepted.load(Ordering::Relaxed),
            "rejected":self.rejected.load(Ordering::Relaxed),
            "auth_failures":self.auth_failures.load(Ordering::Relaxed),
            "uploaded":uploaded,"downloaded":downloaded,"clients":clients,
            "client_history_limit":CLIENT_HISTORY_LIMIT,
            "last_error":*self.last_error.lock().map_err(|_|"LanState")?}),
        )
    }
}

struct ClientLease {
    state: Arc<State>,
    peer: IpAddr,
    id: u64,
    counters: Arc<Counters>,
}

impl Drop for ClientLease {
    fn drop(&mut self) {
        if let Ok(mut accounting) = self.state.accounting.lock() {
            let up = self.counters.upload.load(Ordering::Relaxed);
            let down = self.counters.download.load(Ordering::Relaxed);
            if let Some(client) = accounting.clients.get_mut(&self.peer) {
                client.sessions.remove(&self.id);
                client.unauthenticated.remove(&self.id);
                client.uploaded = client.uploaded.saturating_add(up);
                client.downloaded = client.downloaded.saturating_add(down);
                client.last_seen = Instant::now();
            }
            accounting.completed_upload = accounting.completed_upload.saturating_add(up);
            accounting.completed_download = accounting.completed_download.saturating_add(down);
        }
    }
}

struct UdpPool {
    address: IpAddr,
    first: u16,
    last: u16,
    leased: Mutex<BTreeSet<u16>>,
}

pub(super) struct UdpLease {
    socket: Option<UdpSocket>,
    pool: Arc<UdpPool>,
    port: u16,
}

impl UdpLease {
    pub(super) fn socket(&self) -> &UdpSocket {
        self.socket
            .as_ref()
            .expect("live UDP lease owns its socket")
    }
}

impl Drop for UdpLease {
    fn drop(&mut self) {
        // Close before returning the port to the pool. No datagram queued for
        // an ended association can survive into a new association.
        drop(self.socket.take());
        if let Ok(mut leased) = self.pool.leased.lock() {
            leased.remove(&self.port);
        }
    }
}

impl UdpPool {
    fn bind(self: &Arc<Self>) -> Result<UdpLease> {
        let mut leased = self.leased.lock().map_err(|_| "LanUdpState")?;
        for port in self.first..=self.last {
            if leased.contains(&port) {
                continue;
            }
            let socket = match StdUdpSocket::bind(SocketAddr::new(self.address, port)) {
                Ok(socket) => socket,
                Err(error) if error.kind() == std::io::ErrorKind::AddrInUse => continue,
                Err(_) => return Err("LanUdpBind"),
            };
            socket.set_nonblocking(true).map_err(|_| "LanUdpSocket")?;
            let socket = UdpSocket::from_std(socket).map_err(|_| "LanUdpSocket")?;
            swirl_transport::reserve_datagram_buffers(&socket)
                .map_err(|_| "LanUdpSocketBuffers")?;
            leased.insert(port);
            return Ok(UdpLease {
                socket: Some(socket),
                pool: self.clone(),
                port,
            });
        }
        Err("LanUdpPoolExhaustedOrBusy")
    }
}

#[derive(Clone)]
pub(super) struct Ingress {
    pub(super) config: Arc<LanConfig>,
    pub(super) counters: Arc<Counters>,
    pool: Arc<UdpPool>,
    state: Arc<State>,
    peer: IpAddr,
    id: u64,
    protocol: Protocol,
}

pub(super) struct Boundary<'a> {
    ingress: &'a Ingress,
    local: SocketAddr,
}

impl IngressBoundary for Boundary<'_> {
    fn resolver(&self, resolver: &Arc<Resolver>) -> Arc<Resolver> {
        let ingress = self.ingress.clone();
        let local = self.local;
        Arc::new(
            resolver
                .as_ref()
                .clone()
                .with_endpoint_guard(move |address| {
                    ingress.check_proxy_endpoint(address, local).is_ok()
                }),
        )
    }

    fn prepare_proxy_endpoint<'a>(
        &'a self,
        node: &'a Node,
        resolver: &'a mut Arc<Resolver>,
        limit: Duration,
    ) -> GuardPreparation<'a> {
        Box::pin(
            self.ingress
                .prepare_proxy_endpoint(node, resolver, limit, self.local),
        )
    }
}

impl Ingress {
    pub(super) fn check_target(&self, target: &NetworkTarget) -> Result<()> {
        #[cfg(test)]
        if let Ok(ip) = target.host.parse::<IpAddr>()
            && self
                .state
                .fixture_targets
                .lock()
                .map_err(|_| "LanState")?
                .contains(&SocketAddr::new(ip, target.port))
        {
            return Ok(());
        }
        self.config.check_target(&target.host)
    }

    pub(super) fn boundary(&self, local: SocketAddr) -> Boundary<'_> {
        Boundary {
            ingress: self,
            local,
        }
    }

    fn check_proxy_endpoint(&self, address: SocketAddr, local: SocketAddr) -> Result<()> {
        if (address.port() == local.port()
            && (address.ip().is_loopback() || address.ip() == local.ip()))
            || ([self.config.http_port, self.config.socks_port].contains(&address.port())
                && (address.ip() == self.config.listen_ip
                    || self.config.host_addresses.contains(&address.ip())))
        {
            return Err("LanOutboundProxyLoop");
        }
        #[cfg(test)]
        if matches!(self.state.access, Access::LoopbackFixture) && address.ip().is_loopback() {
            return Ok(());
        }
        self.check_target(&NetworkTarget {
            host: address.ip().to_string(),
            port: address.port(),
        })
        .map_err(|_| "LanOutboundHostAccessDenied")
    }

    async fn prepare_proxy_endpoint(
        &self,
        node: &Node,
        resolver: &mut Arc<Resolver>,
        limit: Duration,
        local: SocketAddr,
    ) -> Result<()> {
        let (host, port) = match &node.outbound {
            Outbound::Direct {} | Outbound::Reject {} => return Ok(()),
            Outbound::Vmess { host, port, .. }
            | Outbound::Vless { host, port, .. }
            | Outbound::Shadowsocks { host, port, .. }
            | Outbound::Socks4 { host, port, .. }
            | Outbound::Socks5 { host, port, .. }
            | Outbound::HttpConnect { host, port, .. }
            | Outbound::Trojan { host, port, .. } => (host.as_str(), *port),
            Outbound::Hysteria2(config) => (config.host.as_str(), config.port),
            Outbound::Tuic(config) => (config.host.as_str(), config.port),
        };
        let host = host.to_owned();
        let known = if host.eq_ignore_ascii_case("localhost") {
            Some(IpAddr::V4(std::net::Ipv4Addr::LOCALHOST))
        } else {
            host.parse::<IpAddr>()
                .ok()
                .or_else(|| resolver.mapped_host(&host))
        };
        if let Some(ip) = known {
            self.check_proxy_endpoint(SocketAddr::new(ip, port), local)?;
        }
        // Resolve the configured endpoint through the existing DNS subsystem,
        // validate every candidate, then freeze those answers for the dial.
        // The same preparation protects an earlier classification DNS tunnel.
        let addresses = timeout(limit, resolver.resolve(&host, port))
            .await
            .map_err(|_| "LanOutboundDnsTimeout")??;
        if addresses.is_empty() || addresses.len() > 16 {
            return Err("LanOutboundDnsAnswers");
        }
        for address in &addresses {
            self.check_proxy_endpoint(*address, local)?;
        }
        let ingress = self.clone();
        *resolver = Arc::new(
            resolver
                .with_pinned_addresses(
                    &host,
                    addresses.into_iter().map(|address| address.ip()).collect(),
                )
                .with_endpoint_guard(move |address| {
                    ingress.check_proxy_endpoint(address, local).is_ok()
                }),
        );
        Ok(())
    }

    pub(super) async fn prepare_outbound(
        &self,
        routed: &mut Routed,
        local: SocketAddr,
    ) -> Result<()> {
        self.prepare_proxy_endpoint(&routed.node, &mut routed.resolver, routed.limit, local)
            .await?;
        // The target is also an address boundary. Delegating a domain to even
        // an approved proxy would let that proxy resolve it back to this host.
        // Resolve over the selected outbound's encrypted DNS path, validate
        // every answer, and send only the approved numeric target on the wire.
        pin_proxy_target(routed, |target| self.check_target(target))
            .await
            .map_err(|error| match error {
                "DnsEncryptedServerRequired" => "LanTargetDnsPolicyRequired",
                "IngressTargetDnsTimeout" => "LanTargetDnsTimeout",
                "IngressTargetDnsAnswers" => "LanTargetDnsAnswers",
                _ => error,
            })
    }

    pub(super) async fn check_protocol(&self, stream: &TcpStream) -> Result<()> {
        let mut first = [0];
        if stream.peek(&mut first).await.map_err(|_| "InboundClosed")? == 0 {
            return Err("InboundClosed");
        }
        let permitted = match self.protocol {
            Protocol::Mixed => first[0] != 4,
            Protocol::Http => first[0] != 4 && first[0] != 5,
            Protocol::Socks => first[0] == 5,
        };
        if permitted {
            Ok(())
        } else {
            Err("LanIngressProtocol")
        }
    }

    pub(super) fn authenticated(&self) {
        self.state.authenticated(self.peer, self.id);
    }

    pub(super) fn error(&self, code: &'static str) {
        self.state.error(code);
    }

    pub(super) fn bind_udp(&self) -> Result<UdpLease> {
        self.pool.bind()
    }

    pub(super) async fn idle(&self) {
        let limit = Duration::from_secs(self.config.idle_timeout_secs);
        let mut last = Instant::now();
        let mut previous = (0, 0);
        loop {
            tokio::time::sleep(Duration::from_secs(1).min(limit)).await;
            let current = (
                self.counters.upload.load(Ordering::Relaxed),
                self.counters.download.load(Ordering::Relaxed),
            );
            if current != previous {
                previous = current;
                last = Instant::now();
            }
            if last.elapsed() >= limit {
                return;
            }
        }
    }
}

pub(super) async fn idle(ingress: &Option<Ingress>) {
    if let Some(ingress) = ingress {
        ingress.idle().await;
    } else {
        std::future::pending::<()>().await;
    }
}

pub(super) struct LanRuntime {
    stop: watch::Sender<bool>,
    task: Option<JoinHandle<()>>,
    state: Arc<State>,
}

impl LanRuntime {
    pub(super) fn start(runtime: &Runtime, shared: Arc<Shared>, config: LanConfig) -> Result<Self> {
        config.validate()?;
        let access = Access::Private(config.cidrs()?);
        Self::start_bound(runtime, shared, config, access)
    }

    fn start_bound(
        runtime: &Runtime,
        shared: Arc<Shared>,
        config: LanConfig,
        access: Access,
    ) -> Result<Self> {
        let (http, socks) = runtime.block_on(async {
            let http = TcpListener::bind(SocketAddr::new(config.listen_ip, config.http_port))
                .await
                .map_err(|error| {
                    if error.kind() == std::io::ErrorKind::AddrInUse {
                        "LanHttpPortInUse"
                    } else {
                        "LanHttpBind"
                    }
                })?;
            let socks = if config.socks_port != config.http_port {
                Some(
                    TcpListener::bind(SocketAddr::new(config.listen_ip, config.socks_port))
                        .await
                        .map_err(|error| {
                            if error.kind() == std::io::ErrorKind::AddrInUse {
                                "LanSocksPortInUse"
                            } else {
                                "LanSocksBind"
                            }
                        })?,
                )
            } else {
                None
            };
            // Detect an occupied configured range before publishing running.
            // Actual association bind remains authoritative if an external
            // program takes a port after this preflight.
            let mut probe = Vec::new();
            for port in config.udp_port_start..=config.udp_port_end {
                probe.push(
                    StdUdpSocket::bind(SocketAddr::new(config.listen_ip, port))
                        .map_err(|_| "LanUdpPortInUseOrUnavailable")?,
                );
            }
            Ok::<_, &'static str>((http, socks))
        })?;
        let config = Arc::new(config);
        let state = Arc::new(State {
            config: config.clone(),
            access,
            accounting: Mutex::new(Accounting {
                clients: BTreeMap::new(),
                completed_upload: 0,
                completed_download: 0,
            }),
            accepted: AtomicU64::new(0),
            rejected: AtomicU64::new(0),
            auth_failures: AtomicU64::new(0),
            last_error: Mutex::new(""),
            #[cfg(test)]
            fixture_targets: Mutex::new(BTreeSet::new()),
        });
        let pool = Arc::new(UdpPool {
            address: config.listen_ip,
            first: config.udp_port_start,
            last: config.udp_port_end,
            leased: Mutex::new(BTreeSet::new()),
        });
        let (stop, mut stopped) = watch::channel(false);
        let task = runtime.spawn({
            let state = state.clone();
            async move {
                let permits = Arc::new(Semaphore::new(config.max_connections));
                let mut sessions = JoinSet::new();
                loop {
                    let accepted = tokio::select! {
                        biased;
                        _ = stopped.changed() => break,
                        Some(_) = sessions.join_next(), if !sessions.is_empty() => continue,
                        accepted = http.accept() => accepted.map(|pair| (pair, if socks.is_some() {Protocol::Http} else {Protocol::Mixed})),
                        accepted = async { socks.as_ref().expect("guarded SOCKS listener").accept().await }, if socks.is_some() => accepted.map(|pair| (pair, Protocol::Socks)),
                    };
                    let ((socket, peer), protocol) = match accepted {
                        Ok(value) => value,
                        Err(_) => { state.error("LanAccept"); break; }
                    };
                    let Ok(permit) = permits.clone().try_acquire_owned() else {
                        state.rejected.fetch_add(1, Ordering::Relaxed);
                        shared.rejected.fetch_add(1, Ordering::Relaxed);
                        state.error("LanConnectionLimit");
                        continue;
                    };
                    let Ok(global_permit) = shared.connection_slots.clone().try_acquire_owned() else {
                        state.rejected.fetch_add(1, Ordering::Relaxed);
                        shared.rejected.fetch_add(1, Ordering::Relaxed);
                        state.error("CoreConnectionLimit");
                        continue;
                    };
                    let id = shared.accepted.fetch_add(1, Ordering::Relaxed) + 1;
                    let lease = match state.admit(peer.ip(), id) {
                        Ok(lease) => lease,
                        Err(error) => { state.rejected.fetch_add(1, Ordering::Relaxed); shared.rejected.fetch_add(1, Ordering::Relaxed); state.error(error); continue; }
                    };
                    let (cancel, cancelled) = watch::channel(false);
                    if let Ok(mut registry) = shared.sessions.lock() {
                        registry.insert(id, SessionControl { cancel, nodes: BTreeSet::new(), preparing: 1 });
                    } else { state.error("SessionState"); break; }
                    shared.active.fetch_add(1, Ordering::Relaxed);
                    let shared = shared.clone();
                    let state = state.clone();
                    let ingress = Ingress { config: config.clone(), counters: lease.counters.clone(), pool: pool.clone(), state: state.clone(), peer: peer.ip(), id, protocol };
                    sessions.spawn(async move {
                        let _permit = permit;
                        let _global_permit = global_permit;
                        let _lease = lease;
                        let _guard = SessionGuard { shared: shared.clone(), id };
                        let result = session(socket, peer, shared.clone(), id, cancelled, Some(ingress)).await;
                        if let Err(error) = result {
                            if matches!(error, "InboundAuthentication" | "HandshakeTimeout") {
                                state.authentication_failed(peer.ip());
                            }
                            if error != "SessionRevoked" {
                                state.error(error);
                                shared.failed.fetch_add(1, Ordering::Relaxed);
                            }
                            if let Ok(mut records) = shared.records.lock() && let Some(record) = records.get_mut(&id) {
                                record.error = error;
                            }
                        }
                    });
                }
                // Revoke only LAN IDs, then let the existing UDP path join its
                // workers before stop returns. Aborting the enclosing session
                // would detach its outbound-worker cleanup.
                let ids = state.session_ids();
                if let Ok(registry) = shared.sessions.lock() {
                    for id in ids {
                        if let Some(session) = registry.get(&id) { let _ = session.cancel.send(true); }
                    }
                }
                while sessions.join_next().await.is_some() {}
            }
        });
        Ok(Self {
            stop,
            task: Some(task),
            state,
        })
    }

    pub(super) fn running(&self) -> bool {
        self.task.as_ref().is_some_and(|task| !task.is_finished())
    }

    pub(super) fn snapshot(&self) -> Result<Value> {
        self.state.snapshot(self.running())
    }

    pub(super) fn stop(&mut self, runtime: &Runtime) -> Result<Value> {
        let _ = self.stop.send(true);
        if let Some(task) = self.task.take() {
            runtime.block_on(async {
                let _ = task.await;
            });
        }
        self.state.snapshot(false)
    }
}

#[cfg(test)]
#[path = "v2_lan_tests.rs"]
mod tests;
