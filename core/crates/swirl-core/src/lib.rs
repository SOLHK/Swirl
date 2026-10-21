//! Rust-owned runtime, sockets, scheduling, statistics and immutable session plans.
mod policy;
mod socks5_udp;
pub use policy::{MemberHealth, PolicyReport};
use policy::{PolicyRuntime, PolicyView};
use serde::Serialize;
use std::{
    collections::{BTreeMap, HashMap},
    net::{IpAddr, SocketAddr},
    sync::{
        Arc, Mutex, RwLock,
        atomic::{AtomicU64, AtomicUsize, Ordering},
    },
    time::{Duration, Instant},
};
use swirl_dns::Resolver;
use swirl_routing::{ChinaRules, MrsBehavior};
use swirl_protocol::{Inbound, Result, Target};
use swirl_subscription::{Config, Outbound, PolicyStrategy};
use swirl_transport::{Counters, bind_udp};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream, UdpSocket},
    runtime::{Builder, Runtime},
    sync::{OwnedSemaphorePermit, Semaphore, watch},
    task::{JoinHandle, JoinSet},
    time::timeout,
};

fn load_china_rules(config: &Config) -> Result<(Option<Arc<ChinaRules>>, Option<Arc<ChinaRules>>)> {
    if !config.smart_routing { return Ok((None, None)); }
    let directory = config.china_rules_directory.as_ref().ok_or("ChinaRulesDirectoryMissing")?;
    let directory = std::path::Path::new(directory);
    let domain_path = directory.join("cn-domain.mrs");
    let ip_path = directory.join("cn-ip.mrs");
    let domain_bytes = std::fs::read(domain_path).map_err(|_| "ChinaDomainRulesRead")?;
    let ip_bytes = std::fs::read(ip_path).map_err(|_| "ChinaIpRulesRead")?;
    let domains = ChinaRules::parse(&domain_bytes, MrsBehavior::Domain, "e92bda4f0b9f05623663a882331a320ab4e266cada2046d3828a94572cdded46")
        .map_err(|_| "ChinaDomainRulesInvalid")?;
    let ips = ChinaRules::parse(&ip_bytes, MrsBehavior::IpCidr, "d95b3d125f6c74ce3c15e19ef794f142de91e21c3b8fb7767e76aebfabff5149")
        .map_err(|_| "ChinaIpRulesInvalid")?;
    Ok((Some(Arc::new(domains)), Some(Arc::new(ips))))
}

struct Record {
    peer: SocketAddr,
    category: &'static str,
    target: Target,
    node: String,
    matched_rule: String,
    started: Instant,
    ended: bool,
    error: &'static str,
    counters: Arc<Counters>,
}
#[derive(Default)]
struct State {
    totals: Arc<Counters>,
    active: AtomicUsize,
    accepted: AtomicU64,
    failed: AtomicU64,
    rejected: AtomicU64,
    generation: AtomicU64,
    records: Mutex<BTreeMap<u64, Record>>,
    last_error: Mutex<&'static str>,
}
#[derive(Serialize)]
pub struct Connection {
    pub source_ip: String,
    pub source_port: u16,
    pub category: &'static str,
    pub id: u64,
    pub host: String,
    pub port: u16,
    pub node: String,
    pub matched_rule: String,
    pub transport_state: &'static str,
    pub ended: bool,
    pub error: &'static str,
    pub failure_stage: &'static str,
    pub upload: u64,
    pub download: u64,
    pub udp_dropped: u64,
    pub elapsed_ms: u64,
}
#[derive(Serialize)]
pub struct Snapshot {
    pub schema: u32,
    pub engine: &'static str,
    pub address: SocketAddr,
    pub generation: u64,
    pub selected: String,
    pub selectors: BTreeMap<String, String>,
    pub policies: BTreeMap<String, PolicyReport>,
    pub running: bool,
    pub active: usize,
    pub accepted: u64,
    pub failed: u64,
    pub rejected: u64,
    pub upload: u64,
    pub download: u64,
    pub udp_dropped: u64,
    pub last_error: &'static str,
    pub last_error_stage: &'static str,
    pub connections: Vec<Connection>,
}
struct Plan {
    config: Arc<Config>,
    resolver: Arc<Resolver>,
    policies: Arc<PolicyRuntime>,
    cn_domains: Option<Arc<ChinaRules>>,
    cn_ips: Option<Arc<ChinaRules>>,
}
struct SessionPlan {
    config: Arc<Config>,
    resolver: Arc<Resolver>,
    policies: Arc<PolicyView>,
    cn_domains: Option<Arc<ChinaRules>>,
    cn_ips: Option<Arc<ChinaRules>>,
}
impl Plan {
    fn session(&self) -> Result<Arc<SessionPlan>> {
        Ok(Arc::new(SessionPlan {
            config: self.config.clone(),
            resolver: self.resolver.clone(),
            policies: Arc::new(self.policies.view(&self.config)?),
            cn_domains: self.cn_domains.clone(),
            cn_ips: self.cn_ips.clone(),
        }))
    }
}
pub struct Core {
    runtime: Option<Runtime>,
    stop: watch::Sender<bool>,
    task: Option<JoinHandle<()>>,
    plan: Arc<RwLock<Arc<Plan>>>,
    state: Arc<State>,
    address: SocketAddr,
}

impl Core {
    pub fn start(config: Config) -> Result<Self> {
        config.validate()?;
        swirl_routing::validate_smart_routing(&config)?;
        let runtime = Builder::new_multi_thread()
            .worker_threads(2)
            .max_blocking_threads(4)
            .thread_name("Swirl Rust Core")
            .enable_all()
            .build()
            .map_err(|_| "RuntimeStart")?;
        let listener = runtime
            .block_on(TcpListener::bind(config.listen))
            .map_err(|_| "ListenerBind")?;
        let address = listener.local_addr().map_err(|_| "ListenerAddress")?;
        let capacity = config.limits.max_connections;
        let resolver = Arc::new(Resolver::default().with_config(&config.dns)?);
        let (cn_domains, cn_ips) = load_china_rules(&config)?;
        let config = Arc::new(config);
        let policies = Arc::new(PolicyRuntime::new(
            runtime.handle().clone(),
            config.clone(),
            resolver.clone(),
        ));
        let plan = Arc::new(RwLock::new(Arc::new(Plan {
            config,
            resolver,
            policies,
            cn_domains,
            cn_ips,
        })));
        let state = Arc::new(State::default());
        state.generation.store(1, Ordering::Relaxed);
        let (stop, mut stopped) = watch::channel(false);
        let task=runtime.spawn({let plan=plan.clone();let state=state.clone();async move {
            let permits=Arc::new(Semaphore::new(capacity));
            let mut sessions=JoinSet::new();
            loop {
                tokio::select! {
                    biased;
                    _=stopped.changed()=>break,
                    Some(_)=sessions.join_next(), if !sessions.is_empty()=>{},
                    accepted=listener.accept()=>{
                        let Ok((socket,peer))=accepted else {break;};
                        let Ok(permit)=permits.clone().try_acquire_owned() else {state.rejected.fetch_add(1,Ordering::Relaxed);continue;};
                        let Ok(current)=plan.read().map(|c|c.clone()) else {break;};
                        let Ok(session_plan)=current.session() else {break;};
                        let state=state.clone();
                        let id=state.accepted.fetch_add(1,Ordering::Relaxed)+1;
                        state.active.fetch_add(1,Ordering::Relaxed);
                        let guard=SessionGuard {state:state.clone(),id};
                        sessions.spawn(async move {
                            let _permit=permit;let _guard=guard;
                            if let Err(code)=session(socket,peer,session_plan,state.clone(),id).await {
                                state.failed.fetch_add(1,Ordering::Relaxed);
                                if let Ok(mut error)=state.last_error.lock(){*error=code;}
                                if let Ok(mut records)=state.records.lock()
                                    && let Some(record)=records.get_mut(&id) {
                                    record.error=code;
                                }
                            }
                        });
                    }
                }
            }
            if let Ok(current)=plan.read() {current.policies.stop();}
            sessions.abort_all();while sessions.join_next().await.is_some() {}
        }});
        Ok(Self {
            runtime: Some(runtime),
            stop,
            task: Some(task),
            plan,
            state,
            address,
        })
    }
    pub fn configure(&self, config: Config) -> Result<()> {
        if self.runtime.is_none() {
            return Err("CoreStopped");
        }
        config.validate()?;
        let mut plan = self.plan.write().map_err(|_| "ConfigState")?;
        if config.listen != plan.config.listen
            || config.limits.max_connections != plan.config.limits.max_connections
        {
            return Err("ListenerChangeRequiresRestart");
        }
        let resolver = Arc::new(plan.resolver.with_config(&config.dns)?);
        let (cn_domains, cn_ips) = load_china_rules(&config)?;
        let config = Arc::new(config);
        let policies = Arc::new(plan.policies.reconfigured(config.clone(), resolver.clone()));
        // All fallible validation has completed. Stop the replaced worker even
        // if an old session still owns its immutable configuration and choices.
        plan.policies.stop();
        *plan = Arc::new(Plan {
            config,
            resolver,
            policies,
            cn_domains,
            cn_ips,
        });
        self.state.generation.fetch_add(1, Ordering::Relaxed);
        Ok(())
    }
    pub fn select_node(&self, id: &str) -> Result<()> {
        if self.runtime.is_none() {
            return Err("CoreStopped");
        }
        let mut plan = self.plan.write().map_err(|_| "ConfigState")?;
        let mut next = (*plan.config).clone();
        next.selected = id.to_owned();
        next.validate()?;
        *plan = Arc::new(Plan {
            config: Arc::new(next),
            resolver: plan.resolver.clone(),
            policies: plan.policies.clone(),
            cn_domains: plan.cn_domains.clone(),
            cn_ips: plan.cn_ips.clone(),
        });
        self.state.generation.fetch_add(1, Ordering::Relaxed);
        Ok(())
    }
    pub fn select_group(&self, id: &str, member: &str) -> Result<()> {
        if self.runtime.is_none() {
            return Err("CoreStopped");
        }
        let mut plan = self.plan.write().map_err(|_| "ConfigState")?;
        let mut next = (*plan.config).clone();
        let selector = next
            .selectors
            .iter_mut()
            .find(|s| s.id == id)
            .ok_or("SelectorMissing")?;
        if selector.strategy != PolicyStrategy::Manual {
            return Err("AutomaticPolicySelection");
        }
        if !selector.members.iter().any(|id| id == member) {
            return Err("SelectorMemberMissing");
        }
        selector.selected = member.to_owned();
        next.validate()?;
        *plan = Arc::new(Plan {
            config: Arc::new(next),
            resolver: plan.resolver.clone(),
            policies: plan.policies.clone(),
            cn_domains: plan.cn_domains.clone(),
            cn_ips: plan.cn_ips.clone(),
        });
        self.state.generation.fetch_add(1, Ordering::Relaxed);
        Ok(())
    }
    pub fn address(&self) -> SocketAddr {
        self.address
    }
    pub fn snapshot(&self) -> Result<Snapshot> {
        let plan = self.plan.read().map_err(|_| "ConfigState")?;
        let policies = plan.policies.report(&plan.config)?;
        let records = self.state.records.lock().map_err(|_| "StatsState")?;
        let last_error = *self.state.last_error.lock().map_err(|_| "StatsState")?;
        Ok(Snapshot {
            schema: 1,
            engine: "swirl-rust",
            address: self.address,
            generation: self.state.generation.load(Ordering::Relaxed),
            selected: plan.config.selected.clone(),
            selectors: policies
                .iter()
                .map(|(id, policy)| (id.clone(), policy.selected.clone().unwrap_or_default()))
                .collect(),
            policies,
            running: self.task.as_ref().is_some_and(|t| !t.is_finished()),
            active: self.state.active.load(Ordering::Relaxed),
            accepted: self.state.accepted.load(Ordering::Relaxed),
            failed: self.state.failed.load(Ordering::Relaxed),
            rejected: self.state.rejected.load(Ordering::Relaxed),
            upload: self.state.totals.upload.load(Ordering::Relaxed),
            download: self.state.totals.download.load(Ordering::Relaxed),
            udp_dropped: self.state.totals.udp_dropped.load(Ordering::Relaxed),
            last_error,
            last_error_stage: swirl_protocol::failure_stage(last_error),
            connections: records
                .iter()
                .map(|(id, r)| Connection {
                    source_ip: r.peer.ip().to_string(),
                    source_port: r.peer.port(),
                    category: r.category,
                    id: *id,
                    host: r.target.host.clone(),
                    port: r.target.port,
                    node: r.node.clone(),
                    matched_rule: r.matched_rule.clone(),
                    transport_state: if r.error.is_empty() {
                        if r.ended { "closed" } else { "active" }
                    } else {
                        "failed"
                    },
                    ended: r.ended,
                    error: r.error,
                    failure_stage: swirl_protocol::failure_stage(r.error),
                    upload: r.counters.upload.load(Ordering::Relaxed),
                    download: r.counters.download.load(Ordering::Relaxed),
                    udp_dropped: r.counters.udp_dropped.load(Ordering::Relaxed),
                    elapsed_ms: r.started.elapsed().as_millis() as u64,
                })
                .collect(),
        })
    }
    pub fn stop(&mut self) {
        if let Ok(plan) = self.plan.read() {
            plan.policies.stop();
        }
        let _ = self.stop.send(true);
        if let Some(runtime) = self.runtime.take() {
            if let Some(task) = self.task.take() {
                runtime.block_on(async {
                    let _ = task.await;
                });
            }
            // OS resolver calls can outlive cancellation; never block UI shutdown on them.
            runtime.shutdown_timeout(Duration::from_millis(500));
        }
    }
}
impl Drop for Core {
    fn drop(&mut self) {
        self.stop();
    }
}
struct SessionGuard {
    state: Arc<State>,
    id: u64,
}
impl Drop for SessionGuard {
    fn drop(&mut self) {
        self.state.active.fetch_sub(1, Ordering::Relaxed);
        if let Ok(mut records) = self.state.records.lock() {
            if let Some(record) = records.get_mut(&self.id) {
                record.ended = true;
            }
            let expired: Vec<_> = records
                .iter()
                .filter(|(_, r)| r.ended)
                .map(|(id, _)| *id)
                .collect();
            for id in expired.iter().take(expired.len().saturating_sub(128)) {
                records.remove(id);
            }
        }
    }
}

async fn session(
    mut inbound: TcpStream,
    peer: SocketAddr,
    plan: Arc<SessionPlan>,
    state: Arc<State>,
    id: u64,
) -> Result<()> {
    let config = &plan.config;
    let resolver = &plan.resolver;
    inbound.set_nodelay(true).map_err(|_| "SocketOptions")?;
    let limit = Duration::from_millis(config.limits.handshake_timeout_ms);
    let request = timeout(
        limit,
        swirl_protocol::accept(&mut inbound, &config.inbound_auth),
    )
    .await
    .map_err(|_| "HandshakeTimeout")??;
    let counters = Arc::new(Counters::default());
    if request.udp {
        state.records.lock().map_err(|_| "StatsState")?.insert(
            id,
            Record {
                peer,
                category: "udp",
                target: request.target.clone(),
                node: "udp-routed".into(),
                matched_rule: "PER_DATAGRAM".into(),
                started: Instant::now(),
                ended: false,
                error: "",
                counters: counters.clone(),
            },
        );
        return udp_associate(inbound, peer, request, plan, counters, state.totals.clone()).await;
    }
    let (node, routed_target, rule_index) = match route(&plan, &request.target, peer.ip()).await {
        Ok(route) => route,
        Err(error) => {
            state.records.lock().map_err(|_| "StatsState")?.insert(
                id,
                Record {
                    peer,
                    category: "route-error",
                    target: request.target.clone(),
                    node: String::new(),
                    matched_rule: "ROUTE_ERROR".into(),
                    started: Instant::now(),
                    ended: false,
                    error,
                    counters: counters.clone(),
                },
            );
            let _ = swirl_protocol::reply(&mut inbound, request.kind, false).await;
            return Err(error);
        }
    };
    state.records.lock().map_err(|_| "StatsState")?.insert(
        id,
        Record {
            peer,
            category: if matches!(node.outbound, Outbound::Direct {}) {
                "direct"
            } else if matches!(node.outbound, Outbound::Reject {}) {
                "reject"
            } else {
                "proxy"
            },
            target: request.target.clone(),
            node: node.id.clone(),
            matched_rule: swirl_routing::rule_label(config, rule_index),
            started: Instant::now(),
            ended: false,
            error: "",
            counters: counters.clone(),
        },
    );
    let connected = swirl_protocol::connect(&node.outbound, &routed_target, resolver, limit).await;
    let mut upstream = match connected {
        Ok(s) => s,
        Err(e) => {
            let _ = swirl_protocol::reply(&mut inbound, request.kind, false).await;
            return Err(e);
        }
    };
    swirl_protocol::reply(&mut inbound, request.kind, true).await?;
    if !request.initial.is_empty() {
        timeout(limit, upstream.write_all(&request.initial))
            .await
            .map_err(|_| "InitialWriteTimeout")?
            .map_err(|_| "InitialWrite")?;
        // Flush framed output before waiting for more client data, otherwise
        // the initial HTTP request can remain buffered indefinitely.
        timeout(limit, upstream.flush())
            .await
            .map_err(|_| "InitialWriteTimeout")?
            .map_err(|_| "InitialWrite")?;
        counters
            .upload
            .fetch_add(request.initial.len() as u64, Ordering::Relaxed);
        state
            .totals
            .upload
            .fetch_add(request.initial.len() as u64, Ordering::Relaxed);
    }
    swirl_transport::relay(&mut inbound, &mut upstream, counters, state.totals.clone())
        .await
        .map_err(|_| "StreamIo")
}

async fn route<'a>(
    plan: &'a SessionPlan,
    target: &Target,
    source: std::net::IpAddr,
) -> Result<(&'a swirl_subscription::Node, Target, Option<usize>)> {
    let config = &plan.config;
    let resolver = &plan.resolver;
    use swirl_routing::Decision;
    let choose = |id: &str| plan.policies.choose(id);
    let selected =
        swirl_routing::select_with_trace_and_china(config, &target.host, target.port, source, None, &choose, plan.cn_domains.as_deref(), plan.cn_ips.as_deref())?;
    match selected.decision {
        Decision::Node(node) => {
            let mut routed = target.clone();
            if config.dns.force_proxy_hosts
                && !matches!(node.outbound, Outbound::Reject {})
                && let Some(ip) = resolver.mapped_host(&target.host)
            {
                routed.host = ip.to_string();
            }
            Ok((node, routed, selected.matched_rule))
        }
        Decision::Resolve => {
            let addresses = timeout(
                Duration::from_millis(config.limits.handshake_timeout_ms),
                resolver.resolve(&target.host, target.port),
            )
            .await
            .map_err(|_| "RouteDnsTimeout")??;
            // Match and dial the same address. Do not retry another DNS answer
            // under the first address's policy or let an upstream resolve again.
            let address = addresses.first().ok_or("RouteDnsEmpty")?;
            let selected = swirl_routing::select_with_trace(
                config,
                &target.host,
                target.port,
                source,
                Some(&addresses),
                &choose,
                plan.cn_domains.as_deref(),
                plan.cn_ips.as_deref(),
            )?;
            match selected.decision {
                Decision::Node(node) => Ok((
                    node,
                    Target {
                        host: address.ip().to_string(),
                        port: target.port,
                    },
                    selected.matched_rule,
                )),
                Decision::Resolve => Err("RouteDnsUnresolved"),
            }
        }
    }
}

struct UdpDispatch {
    transport: UdpTransport,
    payload_len: usize,
    node_id: String,
    permit: OwnedSemaphorePermit,
}
enum UdpTransport {
    Datagram {
        address: SocketAddr,
        packet: Vec<u8>,
    },
    Socks5 {
        target: Target,
        payload: Vec<u8>,
    },
}
fn udp_drop(local: &Counters, total: &Counters) {
    local.udp_dropped.fetch_add(1, Ordering::Relaxed);
    total.udp_dropped.fetch_add(1, Ordering::Relaxed);
}
fn transient_udp(error: &std::io::Error) -> bool {
    matches!(
        error.kind(),
        std::io::ErrorKind::ConnectionReset
            | std::io::ErrorKind::ConnectionRefused
            | std::io::ErrorKind::HostUnreachable
            | std::io::ErrorKind::NetworkUnreachable
            | std::io::ErrorKind::Interrupted
    )
}
async fn prepare_udp(
    plan: Arc<SessionPlan>,
    target: Target,
    payload: Vec<u8>,
    source: std::net::IpAddr,
    permit: OwnedSemaphorePermit,
) -> Result<UdpDispatch> {
    let (node, target, _) = route(&plan, &target, source).await?;
    let payload_len = payload.len();
    let (host, port, packet) = match &node.outbound {
        Outbound::Direct {} => (target.host.clone(), target.port, payload),
        Outbound::Socks5 {
            udp: true,
            tls: None,
            ..
        } => {
            return Ok(UdpDispatch {
                transport: UdpTransport::Socks5 { target, payload },
                payload_len,
                node_id: node.id.clone(),
                permit,
            });
        }
        Outbound::Shadowsocks {
            host,
            port,
            password,
            cipher,
            udp: true,
            ..
        } => {
            let mut plain = Vec::new();
            target.encode(&mut plain)?;
            plain.extend(&payload);
            let wire = swirl_protocol::ss_encrypt_datagram(password, cipher, &plain)
                .map_err(|_| "UdpEncode")?;
            (host.clone(), *port, wire)
        }
        _ => return Err("UdpProxyUnsupportedOrRejected"),
    };
    let address = plan
        .resolver
        .resolve(&host, port)
        .await?
        .into_iter()
        .next()
        .ok_or("DnsEmpty")?;
    Ok(UdpDispatch {
        transport: UdpTransport::Datagram { address, packet },
        payload_len,
        node_id: node.id.clone(),
        permit,
    })
}
async fn udp_associate(
    mut control: TcpStream,
    peer: SocketAddr,
    request: Inbound,
    plan: Arc<SessionPlan>,
    counters: Arc<Counters>,
    total: Arc<Counters>,
) -> Result<()> {
    // Unsupported proxy UDP is an error, never silently converted to DIRECT.
    let requested_ip: IpAddr = request
        .target
        .host
        .parse()
        .map_err(|_| "UdpClientAddress")?;
    if !requested_ip.is_unspecified() && requested_ip != peer.ip() {
        return Err("UdpClientAddress");
    }
    let relay = bind_udp(SocketAddr::new(peer.ip(), 0))
        .await
        .map_err(|_| "UdpBind")?;
    let v4 = bind_udp(SocketAddr::from(([0, 0, 0, 0], 0)))
        .await
        .map_err(|_| "UdpBind")?;
    let v6 = bind_udp(SocketAddr::from(([0u16; 8], 0)))
        .await
        .map_err(|_| "UdpBindV6")?;
    let local = relay.local_addr().map_err(|_| "UdpBind")?;
    let mut response = vec![5, 0, 0];
    Target {
        host: local.ip().to_string(),
        port: local.port(),
    }
    .encode(&mut response)?;
    control.write_all(&response).await.map_err(|_| "UdpReply")?;
    let mut client = if request.target.port == 0 {
        None
    } else {
        Some(SocketAddr::new(peer.ip(), request.target.port))
    };
    let mut destinations: HashMap<SocketAddr, (Instant, String)> = HashMap::new();
    let (mut from_client, mut from_v4, mut from_v6) = ([0u8; 65535], [0u8; 65535], [0u8; 65535]);
    let mut closed = [0; 1];
    // A bounded per-association preparation queue lets DNS wait independently
    // from received replies. Dropping the JoinSet cancels all queued work.
    let mut pending: JoinSet<Result<UdpDispatch>> = JoinSet::new();
    let slots = Arc::new(Semaphore::new(4));
    let mut socks = socks5_udp::Pool::new(plan.clone(), counters.clone(), total.clone());
    loop {
        tokio::select! {
            _=control.read(&mut closed)=>return Ok(()),
            Some(prepared)=pending.join_next(), if !pending.is_empty()=>{
                let UdpDispatch {transport,payload_len,node_id,permit}=match prepared {Ok(Ok(d))=>d,_=>{udp_drop(&counters,&total);continue;}};
                let (address,packet)=match transport {
                    UdpTransport::Datagram {address,packet}=>(address,packet),
                    UdpTransport::Socks5 {target,payload}=>{socks.send(node_id,target,payload,permit);continue;}
                };
                destinations.retain(|_,(at,_)|at.elapsed()<Duration::from_secs(30));
                if (destinations.len()>=64 && !destinations.contains_key(&address)) || destinations.get(&address).is_some_and(|(_,id)|id!=&node_id){udp_drop(&counters,&total);continue;}
                let socket=if address.is_ipv4(){&v4}else{&v6};
                if socket.send_to(&packet,address).await.is_err(){udp_drop(&counters,&total);continue;}
                destinations.insert(address,(Instant::now(),node_id));
                counters.upload.fetch_add(payload_len as u64,Ordering::Relaxed);total.upload.fetch_add(payload_len as u64,Ordering::Relaxed);
                drop(permit);
            }
            Some(response)=socks.next_reply()=>{
                let Some(client)=client else {continue;};
                let forwarded=tokio::select! {
                    biased;
                    _=control.read(&mut closed)=>return Ok(()),
                    sent=response.send_to(&relay,client)=>sent,
                };
                let Ok(payload_len)=forwarded else {udp_drop(&counters,&total);continue;};
                counters.download.fetch_add(payload_len as u64,Ordering::Relaxed);total.download.fetch_add(payload_len as u64,Ordering::Relaxed);
            }
            packet=relay.recv_from(&mut from_client)=>{
                let (n,source)=match packet {Ok(v)=>v,Err(e) if transient_udp(&e)=>{udp_drop(&counters,&total);continue;},Err(_)=>return Err("UdpReceive")};
                if source.ip()!=peer.ip() || client.is_some_and(|p|p!=source) || n<4 || from_client[..3]!=[0,0,0]{continue;}
                let mut cursor=&from_client[3..n];
                let Ok(target)=swirl_protocol::read_target(&mut cursor,false).await else {continue;};
                client=Some(source);
                if cursor.len()>65507 {continue;}
                let Ok(permit)=slots.clone().try_acquire_owned() else {udp_drop(&counters,&total);continue;};
                pending.spawn(prepare_udp(plan.clone(),target,cursor.to_vec(),source.ip(),permit));
            }
            packet=v4.recv_from(&mut from_v4)=>{
                let (n,source)=match packet {Ok(v)=>v,Err(e) if transient_udp(&e)=>{udp_drop(&counters,&total);continue;},Err(_)=>return Err("UdpReceive")};
                udp_response(&relay,client,source,&from_v4[..n],&destinations,&plan.config,(&counters,&total)).await?;
            }
            packet=v6.recv_from(&mut from_v6)=>{
                let (n,source)=match packet {Ok(v)=>v,Err(e) if transient_udp(&e)=>{udp_drop(&counters,&total);continue;},Err(_)=>return Err("UdpReceive")};
                udp_response(&relay,client,source,&from_v6[..n],&destinations,&plan.config,(&counters,&total)).await?;
            }
        }
    }
}
async fn udp_response(
    relay: &UdpSocket,
    client: Option<SocketAddr>,
    source: SocketAddr,
    payload: &[u8],
    destinations: &HashMap<SocketAddr, (Instant, String)>,
    config: &Config,
    counts: (&Counters, &Counters),
) -> Result<()> {
    let (counters, total) = counts;
    let Some(client) = client else {
        return Ok(());
    };
    let Some((at, id)) = destinations.get(&source) else {
        return Ok(());
    };
    if at.elapsed() >= Duration::from_secs(30) {
        return Ok(());
    }
    let node = config
        .nodes
        .iter()
        .find(|n| &n.id == id)
        .ok_or("UdpRouteMissing")?;
    let decoded;
    let (target, payload) = if let Outbound::Shadowsocks {
        password, cipher, ..
    } = &node.outbound
    {
        let Ok(plain) = swirl_protocol::ss_decrypt_datagram(password, cipher, payload) else {
            return Ok(());
        };
        decoded = plain;
        let mut cursor = decoded.as_slice();
        let Ok(target) = swirl_protocol::read_target(&mut cursor, false).await else {
            return Ok(());
        };
        (target, cursor)
    } else {
        (
            Target {
                host: source.ip().to_string(),
                port: source.port(),
            },
            payload,
        )
    };
    let mut data = vec![0, 0, 0];
    target.encode(&mut data)?;
    data.extend(payload);
    if data.len() > 65507 {
        return Ok(());
    }
    if relay.send_to(&data, client).await.is_err() {
        udp_drop(counters, total);
        return Ok(());
    }
    counters
        .download
        .fetch_add(payload.len() as u64, Ordering::Relaxed);
    total
        .download
        .fetch_add(payload.len() as u64, Ordering::Relaxed);
    Ok(())
}
