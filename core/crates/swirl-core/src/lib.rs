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
    let node = swirl_routing::select(&config, &request.target.host)?;
    state.records.lock().map_err(|_| "StatsState")?.insert(
        id,
        Record {
            peer,
            category: if matches!(node.outbound, Outbound::Direct) {
                "direct"
            } else if matches!(node.outbound, Outbound::Reject) {
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
        swirl_protocol::connect(&node.outbound, &request.target, &resolver),
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

async fn udp_associate(
    mut control: TcpStream,
    peer: SocketAddr,
    request: Inbound,
    config: Arc<Config>,
    resolver: Arc<Resolver>,
    counters: Arc<Counters>,
    total: Arc<Counters>,
) -> Result<()> {
    // First phase: UDP ASSOCIATE executes explicit DIRECT/REJECT routes only.
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
    let mut destinations: HashMap<SocketAddr, Instant> = HashMap::new();
    let (mut from_client, mut from_v4, mut from_v6) = ([0u8; 65535], [0u8; 65535], [0u8; 65535]);
    let mut closed = [0; 1];
    loop {
        tokio::select! {
            _=control.read(&mut closed)=>return Ok(()),
            packet=relay.recv_from(&mut from_client)=>{
                let (n,source)=packet.map_err(|_|"UdpReceive")?;
                if source.ip()!=peer.ip() || client.is_some_and(|p|p!=source) || n<4 || from_client[..3]!=[0,0,0]{continue;}
                let mut cursor=&from_client[3..n];
                let Ok(target)=swirl_protocol::read_target(&mut cursor,false).await else {continue;};
                client=Some(source);
                if cursor.len()>65507 {continue;}
                let node=swirl_routing::select(&config,&target.host)?;
                if !matches!(node.outbound,Outbound::Direct){return Err("UdpProxyUnsupportedOrRejected");}
                let address=resolver.resolve(&target.host,target.port).await?.into_iter().next().ok_or("DnsEmpty")?;
                destinations.retain(|_,at|at.elapsed()<Duration::from_secs(30));
                if destinations.len()>=64 && !destinations.contains_key(&address){continue;}
                let socket=if address.is_ipv4(){&v4}else{&v6};
                let count=socket.send_to(cursor,address).await.map_err(|_|"UdpSend")?;
                destinations.insert(address,Instant::now());
                counters.upload.fetch_add(count as u64,Ordering::Relaxed);total.upload.fetch_add(count as u64,Ordering::Relaxed);
            }
            packet=v4.recv_from(&mut from_v4)=>{
                let (n,source)=packet.map_err(|_|"UdpReceive")?;
                udp_response(&relay,client,source,&from_v4[..n],&destinations,&counters,&total).await?;
            }
            packet=v6.recv_from(&mut from_v6)=>{
                let (n,source)=packet.map_err(|_|"UdpReceive")?;
                udp_response(&relay,client,source,&from_v6[..n],&destinations,&counters,&total).await?;
            }
        }
    }
}
async fn udp_response(
    relay: &UdpSocket,
    client: Option<SocketAddr>,
    source: SocketAddr,
    payload: &[u8],
    destinations: &HashMap<SocketAddr, Instant>,
    counters: &Counters,
    total: &Counters,
) -> Result<()> {
    let Some(client) = client else {
        return Ok(());
    };
    if destinations
        .get(&source)
        .is_none_or(|at| at.elapsed() >= Duration::from_secs(30))
    {
        return Ok(());
    }
    let mut data = vec![0, 0, 0];
    Target {
        host: source.ip().to_string(),
        port: source.port(),
    }
    .encode(&mut data)?;
    data.extend(payload);
    if data.len() > 65507 {
        return Ok(());
    }
    relay.send_to(&data, client).await.map_err(|_| "UdpSend")?;
    counters
        .download
        .fetch_add(payload.len() as u64, Ordering::Relaxed);
    total
        .download
        .fetch_add(payload.len() as u64, Ordering::Relaxed);
    Ok(())
}
