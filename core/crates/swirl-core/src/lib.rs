//! Rust-owned runtime, sockets, scheduling, statistics and immutable session plans.
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
use swirl_protocol::{Inbound, Result, Target};
use swirl_subscription::{Config, Outbound};
use swirl_transport::Counters;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream, UdpSocket},
    runtime::{Builder, Runtime},
    sync::{Semaphore, watch},
    task::{JoinHandle, JoinSet},
    time::timeout,
};

struct Record {
    peer: SocketAddr,
    category: &'static str,
    target: Target,
    node: String,
    started: Instant,
    ended: bool,
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
    pub ended: bool,
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
    pub running: bool,
    pub active: usize,
    pub accepted: u64,
    pub failed: u64,
    pub rejected: u64,
    pub upload: u64,
    pub download: u64,
    pub udp_dropped: u64,
    pub last_error: &'static str,
    pub connections: Vec<Connection>,
}
pub struct Core {
    runtime: Option<Runtime>,
    stop: watch::Sender<bool>,
    task: Option<JoinHandle<()>>,
    plan: Arc<RwLock<Arc<Config>>>,
    state: Arc<State>,
    address: SocketAddr,
}

impl Core {
    pub fn start(config: Config) -> Result<Self> {
        config.validate()?;
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
        let plan = Arc::new(RwLock::new(Arc::new(config)));
        let state = Arc::new(State::default());
        state.generation.store(1, Ordering::Relaxed);
        let resolver = Arc::new(Resolver::default());
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
                        let Ok(config)=plan.read().map(|c|c.clone()) else {break;};
                        let state=state.clone();let resolver=resolver.clone();
                        let id=state.accepted.fetch_add(1,Ordering::Relaxed)+1;
                        state.active.fetch_add(1,Ordering::Relaxed);
                        let guard=SessionGuard {state:state.clone(),id};
                        sessions.spawn(async move {
                            let _permit=permit;let _guard=guard;
                            if let Err(code)=session(socket,peer,config,resolver,state.clone(),id).await {
                                state.failed.fetch_add(1,Ordering::Relaxed);
                                if let Ok(mut error)=state.last_error.lock(){*error=code;}
                            }
                        });
                    }
                }
            }
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
        config.validate()?;
        let mut plan = self.plan.write().map_err(|_| "ConfigState")?;
        if config.listen != plan.listen
            || config.limits.max_connections != plan.limits.max_connections
        {
            return Err("ListenerChangeRequiresRestart");
        }
        *plan = Arc::new(config);
        self.state.generation.fetch_add(1, Ordering::Relaxed);
        Ok(())
    }
    pub fn select_node(&self, id: &str) -> Result<()> {
        let config = {
            let plan = self.plan.read().map_err(|_| "ConfigState")?;
            let mut next = (**plan).clone();
            next.selected = id.to_owned();
            next
        };
        self.configure(config)
    }
    pub fn address(&self) -> SocketAddr {
        self.address
    }
    pub fn snapshot(&self) -> Result<Snapshot> {
        let plan = self.plan.read().map_err(|_| "ConfigState")?;
        let records = self.state.records.lock().map_err(|_| "StatsState")?;
        Ok(Snapshot {
            schema: 1,
            engine: "swirl-rust",
            address: self.address,
            generation: self.state.generation.load(Ordering::Relaxed),
            selected: plan.selected.clone(),
            running: self.task.as_ref().is_some_and(|t| !t.is_finished()),
            active: self.state.active.load(Ordering::Relaxed),
            accepted: self.state.accepted.load(Ordering::Relaxed),
            failed: self.state.failed.load(Ordering::Relaxed),
            rejected: self.state.rejected.load(Ordering::Relaxed),
            upload: self.state.totals.upload.load(Ordering::Relaxed),
            download: self.state.totals.download.load(Ordering::Relaxed),
            udp_dropped: self.state.totals.udp_dropped.load(Ordering::Relaxed),
            last_error: *self.state.last_error.lock().map_err(|_| "StatsState")?,
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
                    ended: r.ended,
                    upload: r.counters.upload.load(Ordering::Relaxed),
                    download: r.counters.download.load(Ordering::Relaxed),
                    udp_dropped: r.counters.udp_dropped.load(Ordering::Relaxed),
                    elapsed_ms: r.started.elapsed().as_millis() as u64,
                })
                .collect(),
        })
    }
    pub fn stop(&mut self) {
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
    config: Arc<Config>,
    resolver: Arc<Resolver>,
    state: Arc<State>,
    id: u64,
) -> Result<()> {
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
                category: "direct",
                target: request.target.clone(),
                node: "udp-routed".into(),
                started: Instant::now(),
                ended: false,
                counters: counters.clone(),
            },
        );
        return udp_associate(
            inbound,
            peer,
            request,
            config,
            resolver,
            counters,
            state.totals.clone(),
        )
        .await;
    }
    let (node, routed_target) = match route(&config, &request.target, peer.ip(), &resolver).await {
        Ok(route) => route,
        Err(error) => {
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
            started: Instant::now(),
            ended: false,
            counters: counters.clone(),
        },
    );
    let connected = timeout(
        limit,
        swirl_protocol::connect(&node.outbound, &routed_target, &resolver, limit),
    )
    .await
    .map_err(|_| "UpstreamTimeout")
    .and_then(|r| r);
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
    config: &'a Config,
    target: &Target,
    source: std::net::IpAddr,
    resolver: &Resolver,
) -> Result<(&'a swirl_subscription::Node, Target)> {
    use swirl_routing::Decision;
    match swirl_routing::select(config, &target.host, target.port, source, None)? {
        Decision::Node(node) => Ok((node, target.clone())),
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
            match swirl_routing::select(
                config,
                &target.host,
                target.port,
                source,
                Some(&addresses),
            )? {
                Decision::Node(node) => Ok((
                    node,
                    Target {
                        host: address.ip().to_string(),
                        port: target.port,
                    },
                )),
                Decision::Resolve => Err("RouteDnsUnresolved"),
            }
        }
    }
}

struct UdpDispatch {
    address: SocketAddr,
    packet: Vec<u8>,
    payload_len: usize,
    node_id: String,
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
    config: Arc<Config>,
    resolver: Arc<Resolver>,
    target: Target,
    payload: Vec<u8>,
    source: std::net::IpAddr,
) -> Result<UdpDispatch> {
    let (node, target) = route(&config, &target, source, &resolver).await?;
    let (host, port, packet) = match &node.outbound {
        Outbound::Direct {} => (target.host.clone(), target.port, payload.clone()),
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
    let address = resolver
        .resolve(&host, port)
        .await?
        .into_iter()
        .next()
        .ok_or("DnsEmpty")?;
    Ok(UdpDispatch {
        address,
        packet,
        payload_len: payload.len(),
        node_id: node.id.clone(),
    })
}
async fn udp_associate(
    mut control: TcpStream,
    peer: SocketAddr,
    request: Inbound,
    config: Arc<Config>,
    resolver: Arc<Resolver>,
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
    let relay = UdpSocket::bind(SocketAddr::new(peer.ip(), 0))
        .await
        .map_err(|_| "UdpBind")?;
    let local = relay.local_addr().map_err(|_| "UdpBind")?;
    let mut response = vec![5, 0, 0];
    Target {
        host: local.ip().to_string(),
        port: local.port(),
    }
    .encode(&mut response)?;
    control.write_all(&response).await.map_err(|_| "UdpReply")?;
    let v4 = UdpSocket::bind("0.0.0.0:0").await.map_err(|_| "UdpBind")?;
    let v6 = UdpSocket::bind("[::]:0").await.map_err(|_| "UdpBindV6")?;
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
    loop {
        tokio::select! {
            _=control.read(&mut closed)=>return Ok(()),
            Some(prepared)=pending.join_next(), if !pending.is_empty()=>{
                let dispatch=match prepared {Ok(Ok(d))=>d,_=>{udp_drop(&counters,&total);continue;}};
                destinations.retain(|_,(at,_)|at.elapsed()<Duration::from_secs(30));
                if (destinations.len()>=64 && !destinations.contains_key(&dispatch.address)) || destinations.get(&dispatch.address).is_some_and(|(_,id)|id!=&dispatch.node_id){udp_drop(&counters,&total);continue;}
                let socket=if dispatch.address.is_ipv4(){&v4}else{&v6};
                if socket.send_to(&dispatch.packet,dispatch.address).await.is_err(){udp_drop(&counters,&total);continue;}
                destinations.insert(dispatch.address,(Instant::now(),dispatch.node_id));
                counters.upload.fetch_add(dispatch.payload_len as u64,Ordering::Relaxed);total.upload.fetch_add(dispatch.payload_len as u64,Ordering::Relaxed);
            }
            packet=relay.recv_from(&mut from_client)=>{
                let (n,source)=match packet {Ok(v)=>v,Err(e) if transient_udp(&e)=>{udp_drop(&counters,&total);continue;},Err(_)=>return Err("UdpReceive")};
                if source.ip()!=peer.ip() || client.is_some_and(|p|p!=source) || n<4 || from_client[..3]!=[0,0,0]{continue;}
                let mut cursor=&from_client[3..n];
                let Ok(target)=swirl_protocol::read_target(&mut cursor,false).await else {continue;};
                client=Some(source);
                if cursor.len()>65507 {continue;}
                if pending.len()>=4{udp_drop(&counters,&total);continue;}
                pending.spawn(prepare_udp(config.clone(),resolver.clone(),target,cursor.to_vec(),source.ip()));
            }
            packet=v4.recv_from(&mut from_v4)=>{
                let (n,source)=match packet {Ok(v)=>v,Err(e) if transient_udp(&e)=>{udp_drop(&counters,&total);continue;},Err(_)=>return Err("UdpReceive")};
                udp_response(&relay,client,source,&from_v4[..n],&destinations,&config,(&counters,&total)).await?;
            }
            packet=v6.recv_from(&mut from_v6)=>{
                let (n,source)=match packet {Ok(v)=>v,Err(e) if transient_udp(&e)=>{udp_drop(&counters,&total);continue;},Err(_)=>return Err("UdpReceive")};
                udp_response(&relay,client,source,&from_v6[..n],&destinations,&config,(&counters,&total)).await?;
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
