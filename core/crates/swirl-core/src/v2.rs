//! Revision-bound configuration transactions and a separately versioned runtime.
//! Preparation has no sockets/tasks; activation cannot admit candidate traffic
//! until the durable receipt has been reconciled by finish.
use super::{
    ChinaRules, ProbeRuntime, ProbeStatus, SessionPlan, policy::PolicyRuntime as LegacyPolicies,
    socks5_udp,
};
use crate::policy_v2::PolicyRuntime;
use ring::rand::{SecureRandom, SystemRandom};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    net::{IpAddr, SocketAddr},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
    },
    time::{Duration, Instant},
};
use swirl_dns::Resolver;
use swirl_protocol::{Inbound, Target as NetworkTarget, Transport};
use swirl_routing::v2::ResolutionPurpose;
use swirl_subscription::{
    Config, Credentials, Dns, Limits, Node, Outbound, uuid_bytes,
    v2::{
        ClassificationDns, Conflict, DIRECT_NODE_ID, Mode, PolicyDocument, REJECT_NODE_ID, Target,
    },
};
use swirl_transport::Counters;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    runtime::{Builder, Runtime},
    sync::{Notify, OwnedSemaphorePermit, Semaphore, watch},
    task::{JoinHandle, JoinSet},
    time::timeout,
};
type Result<T> = std::result::Result<T, &'static str>;

#[path = "v2_lan.rs"]
mod lan_runtime;
#[path = "native_flow.rs"]
mod native_flow;
pub use native_flow::{FlowDispatcher, NativeTunLease, NativeUdpFlow};

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeConfig {
    pub schema: u32,
    pub listen: SocketAddr,
    pub nodes: Vec<Node>,
    pub policy: PolicyDocument,
    #[serde(default)]
    pub dns: Dns,
    #[serde(default)]
    pub inbound_auth: Option<Credentials>,
    #[serde(default)]
    pub limits: Limits,
    #[serde(default)]
    pub china_rules_directory: Option<String>,
    #[serde(default)]
    pub node_sources: BTreeMap<String, String>,
    #[serde(default)]
    pub transports: BTreeMap<String, Transport>,
}
pub struct PreparedConfig {
    runtime: Arc<RuntimeConfig>,
    base: Arc<Config>,
    resolver: Arc<Resolver>,
    classification: Option<Arc<Resolver>>,
    china: (Option<Arc<ChinaRules>>, Option<Arc<ChinaRules>>),
    pub digest: String,
    pub conflicts: Vec<Conflict>,
}
impl RuntimeConfig {
    pub fn prepare(mut self) -> Result<PreparedConfig> {
        if self.schema != 2 {
            return Err("UnsupportedConfigSchema");
        }
        self.policy.normalize()?;
        self.nodes.sort_by(|a, b| a.id.cmp(&b.id));
        if self
            .nodes
            .iter()
            .any(|n| n.id == DIRECT_NODE_ID || n.id == REJECT_NODE_ID)
        {
            return Err("ReservedNodeId");
        }
        let conflicts = self.policy.validate(&self.nodes)?;
        if self.node_sources.len() > 512
            || self.node_sources.iter().any(|(node, source)| {
                !self.nodes.iter().any(|n| &n.id == node) || uuid_bytes(source).is_none()
            })
        {
            return Err("NodeSourceIdentity");
        }
        let mut nodes = self.nodes.clone();
        nodes.push(Node {
            id: DIRECT_NODE_ID.into(),
            outbound: Outbound::Direct {},
        });
        nodes.push(Node {
            id: REJECT_NODE_ID.into(),
            outbound: Outbound::Reject {},
        });
        let base = Config {
            schema: 1,
            listen: self.listen,
            selected: DIRECT_NODE_ID.into(),
            nodes,
            rules: Vec::new(),
            smart_routing: self.policy.mode == Mode::Rule,
            selectors: Vec::new(),
            dns: self.dns.clone(),
            china_rules_directory: self.china_rules_directory.clone(),
            inbound_auth: self.inbound_auth.clone(),
            limits: self.limits.clone(),
        };
        base.validate()?;
        super::validate_transports(&base, &self.transports)?;
        let resolver = Arc::new(Resolver::default().with_config(&self.dns)?);
        let classification = match self.policy.classification_dns {
            ClassificationDns::Disabled => None,
            ClassificationDns::DirectEncrypted | ClassificationDns::ViaDefaultPolicy => {
                if self.dns.tls_servers.is_empty() {
                    return Err("ClassificationEncryptedDnsRequired");
                };
                let mut dns = self.dns.clone();
                dns.servers.clear();
                dns.use_system_hosts = false;
                Some(Arc::new(Resolver::default().with_config(&dns)?))
            }
        };
        let china = super::load_china_rules(&base)?;
        let digest = format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&self).map_err(|_| "ConfigCanonicalization")?)
        );
        Ok(PreparedConfig {
            runtime: Arc::new(self),
            base: Arc::new(base),
            resolver,
            classification,
            china,
            digest,
            conflicts,
        })
    }
}
pub fn decimal(value: &str) -> Result<u64> {
    if value.is_empty()
        || (value.len() > 1 && value.starts_with('0'))
        || !value.bytes().all(|b| b.is_ascii_digit())
    {
        return Err("IdentityDecimal");
    };
    value.parse().map_err(|_| "IdentityDecimal")
}
pub fn identity_uuid(value: &str) -> Result<()> {
    if uuid_bytes(value).is_some() {
        Ok(())
    } else {
        Err("IdentityUuid")
    }
}
fn random_number() -> Result<u64> {
    let mut bytes = [0; 8];
    SystemRandom::new()
        .fill(&mut bytes)
        .map_err(|_| "IdentityRandom")?;
    Ok(u64::from_be_bytes(bytes).max(1))
}
fn random_token() -> Result<String> {
    let mut bytes = [0; 32];
    SystemRandom::new()
        .fill(&mut bytes)
        .map_err(|_| "IdentityRandom")?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

struct Plan {
    prepared: PreparedConfig,
    policies: Arc<PolicyRuntime>,
    revision: u64,
    request_id: String,
}
impl Plan {
    fn new(
        prepared: PreparedConfig,
        runtime: &Runtime,
        revision: u64,
        request_id: String,
    ) -> Result<Arc<Self>> {
        let policies = Arc::new(PolicyRuntime::dormant(
            runtime.handle().clone(),
            Arc::new(prepared.runtime.policy.clone()),
            &prepared.base.nodes,
            prepared.resolver.clone(),
            &prepared.runtime.transports,
        )?);
        Ok(Arc::new(Self {
            prepared,
            policies,
            revision,
            request_id,
        }))
    }
}
struct Live {
    plan: Arc<Plan>,
    generation: u64,
    closed: bool,
    closed_at: Option<Instant>,
}
struct SessionControl {
    cancel: watch::Sender<bool>,
    nodes: BTreeSet<String>,
    preparing: usize,
}
struct Shared {
    live: Mutex<Live>,
    notify: Notify,
    waiting: AtomicUsize,
    native_tun_leases: AtomicUsize,
    stopped: AtomicBool,
    sessions: Mutex<BTreeMap<u64, SessionControl>>,
    connection_slots: Arc<Semaphore>,
    sessions_changed: Notify,
    records: Mutex<BTreeMap<u64, Record>>,
    accepted: AtomicU64,
    active: AtomicUsize,
    failed: AtomicU64,
    rejected: AtomicU64,
    totals: Arc<Counters>,
    last_error: Mutex<&'static str>,
    address: SocketAddr,
}
struct Waiting<'a>(&'a AtomicUsize);
impl Drop for Waiting<'_> {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}
struct Record {
    peer: SocketAddr,
    ingress: &'static str,
    target: NetworkTarget,
    trace: Value,
    node: String,
    category: &'static str,
    counters: Arc<Counters>,
    started: Instant,
    ended: bool,
    error: &'static str,
}
struct RegisteredSession {
    // Rust drops fields in declaration order. Release the admission budget
    // before SessionGuard publishes the fully ended session to observers.
    _permit: OwnedSemaphorePermit,
    guard: SessionGuard,
    cancellation: watch::Receiver<bool>,
}
impl Shared {
    fn register(self: &Arc<Self>) -> Result<RegisteredSession> {
        let permit = self
            .connection_slots
            .clone()
            .try_acquire_owned()
            .map_err(|_| {
                self.rejected.fetch_add(1, Ordering::Relaxed);
                "ConnectionLimit"
            })?;
        let mut sessions = self.sessions.lock().map_err(|_| "SessionState")?;
        // Serialize against the shutdown sweep. No flow may register after the
        // sweep has already sent cancellation to every previous session.
        if self.stopped.load(Ordering::Acquire) {
            return Err("CoreStopped");
        }
        let id = self.accepted.fetch_add(1, Ordering::Relaxed) + 1;
        let (cancel, cancellation) = watch::channel(false);
        sessions.insert(
            id,
            SessionControl {
                cancel,
                nodes: BTreeSet::new(),
                preparing: 1,
            },
        );
        self.active.fetch_add(1, Ordering::Relaxed);
        Ok(RegisteredSession {
            guard: SessionGuard {
                shared: self.clone(),
                id,
            },
            _permit: permit,
            cancellation,
        })
    }

    fn failure(&self, id: u64, error: &'static str) {
        self.failed.fetch_add(1, Ordering::Relaxed);
        if let Ok(mut last) = self.last_error.lock() {
            *last = error;
        }
        if let Ok(mut records) = self.records.lock()
            && let Some(record) = records.get_mut(&id)
        {
            record.error = error;
        }
    }

    async fn admit(&self) -> Result<(Arc<Plan>, u64)> {
        let start = Instant::now();
        let mut waiting = None;
        loop {
            let notified = self.notify.notified();
            tokio::pin!(notified);
            notified.as_mut().enable();
            {
                let live = self.live.lock().map_err(|_| "ConfigState")?;
                if self.stopped.load(Ordering::Acquire) {
                    return Err("CoreStopped");
                };
                if !live.closed {
                    return Ok((live.plan.clone(), live.generation));
                }
                if live
                    .closed_at
                    .is_some_and(|at| at.elapsed() >= Duration::from_secs(2))
                {
                    return Err("Reconfiguring");
                }
            }
            if waiting.is_none() {
                loop {
                    let count = self.waiting.load(Ordering::Acquire);
                    if count >= 64 {
                        return Err("AdmissionBusy");
                    };
                    if self
                        .waiting
                        .compare_exchange_weak(
                            count,
                            count + 1,
                            Ordering::AcqRel,
                            Ordering::Acquire,
                        )
                        .is_ok()
                    {
                        break;
                    }
                }
                waiting = Some(Waiting(&self.waiting));
            }
            let remaining = Duration::from_secs(2).saturating_sub(start.elapsed()).min(
                self.live
                    .lock()
                    .map_err(|_| "ConfigState")?
                    .closed_at
                    .map_or(Duration::from_secs(2), |at| {
                        Duration::from_secs(2).saturating_sub(at.elapsed())
                    }),
            );
            if timeout(remaining, notified).await.is_err() {
                return Err("Reconfiguring");
            }
        }
    }
    fn bind(&self, id: u64, node: &str) -> Result<()> {
        let mut sessions = self.sessions.lock().map_err(|_| "SessionState")?;
        let session = sessions.get_mut(&id).ok_or("SessionRevoked")?;
        if *session.cancel.borrow() {
            return Err("SessionRevoked");
        };
        session.nodes.insert(node.into());
        session.preparing = session.preparing.saturating_sub(1);
        Ok(())
    }
    fn begin_preparation(&self, id: u64) -> Result<()> {
        let mut sessions = self.sessions.lock().map_err(|_| "SessionState")?;
        let session = sessions.get_mut(&id).ok_or("SessionRevoked")?;
        if *session.cancel.borrow() {
            return Err("SessionRevoked");
        };
        session.preparing = session
            .preparing
            .checked_add(1)
            .ok_or("SessionPreparationLimit")?;
        Ok(())
    }
    fn end_preparation(&self, id: u64) {
        if let Ok(mut sessions) = self.sessions.lock()
            && let Some(session) = sessions.get_mut(&id)
        {
            session.preparing = session.preparing.saturating_sub(1);
        }
    }
    async fn revoke(&self, nodes: &BTreeSet<String>) -> Result<()> {
        if nodes.is_empty() {
            return Ok(());
        }
        let affected = {
            let sessions = self.sessions.lock().map_err(|_| "SessionState")?;
            let mut ids = BTreeSet::new();
            for (id, session) in sessions.iter() {
                if session.preparing > 0 || !session.nodes.is_disjoint(nodes) {
                    let _ = session.cancel.send(true);
                    ids.insert(*id);
                }
            }
            ids
        };
        timeout(Duration::from_secs(2), async {
            loop {
                let changed = self.sessions_changed.notified();
                tokio::pin!(changed);
                changed.as_mut().enable();
                let done = {
                    let sessions = self.sessions.lock().map_err(|_| "SessionState")?;
                    affected.iter().all(|id| !sessions.contains_key(id))
                };
                if done {
                    return Ok(());
                }
                changed.await;
            }
        })
        .await
        .map_err(|_| "RevocationBarrierTimeout")?
    }
}
struct SessionGuard {
    shared: Arc<Shared>,
    id: u64,
}
impl Drop for SessionGuard {
    fn drop(&mut self) {
        if let Ok(mut sessions) = self.shared.sessions.lock() {
            sessions.remove(&self.id);
        }
        if let Ok(mut records) = self.shared.records.lock() {
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
        // active == 0 now implies registry/record cleanup and permit release,
        // rather than advertising free capacity before it is actually reusable.
        self.shared.active.fetch_sub(1, Ordering::Release);
        self.shared.sessions_changed.notify_waiters();
    }
}
#[derive(Clone, Copy, PartialEq, Eq)]
enum Phase {
    Prepared,
    Activated,
    RolledBack,
    RecoveryRequired,
}
impl Phase {
    fn label(self) -> &'static str {
        match self {
            Self::Prepared => "preparing",
            Self::Activated => "committing",
            Self::RolledBack => "reconciling",
            Self::RecoveryRequired => "recovery_required",
        }
    }
}
struct Pending {
    request_id: String,
    token: String,
    candidate: Arc<Plan>,
    old: Option<Arc<Plan>>,
    base_generation: u64,
    base_revision: u64,
    phase: Phase,
    created: Instant,
    committed: bool,
    revoked_nodes: BTreeSet<String>,
}
struct Transactions {
    pending: Option<Pending>,
    recent: Option<Value>,
    high_water: u64,
    recent_binding: Option<RecentBinding>,
}
struct RecentBinding {
    token: String,
    candidate_revision: u64,
    base_revision: u64,
    base_generation: u64,
    revoked_nodes: BTreeSet<String>,
    receipt: Value,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DurableReceipt {
    pub store_id: String,
    pub request_id: String,
    pub saved_revision: String,
    pub plan_digest: String,
}
pub struct Core {
    runtime: Option<Runtime>,
    shared: Arc<Shared>,
    stop: watch::Sender<bool>,
    task: Option<JoinHandle<()>>,
    probe: ProbeRuntime,
    transactions: Arc<Mutex<Transactions>>,
    expiry_notify: Arc<Notify>,
    expiry_task: Option<JoinHandle<()>>,
    store_id: String,
    epoch: u64,
    address: SocketAddr,
    lan: Option<lan_runtime::LanRuntime>,
}
impl Core {
    pub fn start(
        candidate: RuntimeConfig,
        store_id: String,
        revision: u64,
        request_id: String,
    ) -> Result<Self> {
        identity_uuid(&store_id)?;
        identity_uuid(&request_id)?;
        let epoch = random_number()?;
        let prepared = candidate.prepare()?;
        prepared.runtime.policy.validate_start()?;
        let runtime = Builder::new_multi_thread()
            .worker_threads(2)
            .max_blocking_threads(4)
            .thread_name("Swirl V2 Core")
            .enable_all()
            .build()
            .map_err(|_| "RuntimeStart")?;
        let listener = runtime
            .block_on(TcpListener::bind(prepared.runtime.listen))
            .map_err(|_| "ListenerBind")?;
        let address = listener.local_addr().map_err(|_| "ListenerAddress")?;
        let capacity = prepared.runtime.limits.max_connections;
        let plan = Plan::new(prepared, &runtime, revision, request_id)?;
        plan.policies.start()?;
        let shared = Arc::new(Shared {
            live: Mutex::new(Live {
                plan,
                generation: 1,
                closed: false,
                closed_at: None,
            }),
            notify: Notify::new(),
            waiting: AtomicUsize::new(0),
            native_tun_leases: AtomicUsize::new(0),
            stopped: AtomicBool::new(false),
            sessions: Mutex::new(BTreeMap::new()),
            connection_slots: Arc::new(Semaphore::new(capacity)),
            sessions_changed: Notify::new(),
            records: Mutex::new(BTreeMap::new()),
            accepted: AtomicU64::new(0),
            active: AtomicUsize::new(0),
            failed: AtomicU64::new(0),
            rejected: AtomicU64::new(0),
            totals: Arc::new(Counters::default()),
            last_error: Mutex::new(""),
            address,
        });
        let (stop, mut stopped) = watch::channel(false);
        let task = runtime.spawn({
            let shared = shared.clone();
            async move {
                let mut sessions = JoinSet::new();
                loop {
                    tokio::select! {
                        biased;
                        _ = stopped.changed() => break,
                        Some(_) = sessions.join_next(), if !sessions.is_empty() => {},
                        accepted = listener.accept() => {
                            let Ok((socket, peer)) = accepted else { break };
                            let registered = match shared.register() {
                                Ok(registered) => registered,
                                Err("ConnectionLimit") => continue,
                                Err(_) => break,
                            };
                            let shared = shared.clone();
                            sessions.spawn(async move {
                                let id = registered.guard.id;
                                let cancellation = registered.cancellation.clone();
                                if let Err(error) = session(socket, peer, shared.clone(), id, cancellation, None).await {
                                    shared.failure(id, error);
                                }
                                drop(registered);
                            });
                        }
                    }
                }
                if let Ok(registry) = shared.sessions.lock() {
                    for session in registry.values() {
                        let _ = session.cancel.send(true);
                    }
                }
                while sessions.join_next().await.is_some() {}
            }
        });
        let transactions = Arc::new(Mutex::new(Transactions {
            pending: None,
            recent: None,
            high_water: revision,
            recent_binding: None,
        }));
        let expiry_notify = Arc::new(Notify::new());
        let expiry_task = runtime.spawn(expire_prepared(
            transactions.clone(),
            expiry_notify.clone(),
            stop.subscribe(),
            shared.clone(),
            store_id.clone(),
            epoch,
        ));
        Ok(Self {
            probe: ProbeRuntime::new(runtime.handle().clone()),
            runtime: Some(runtime),
            shared,
            stop,
            task: Some(task),
            transactions,
            expiry_notify,
            expiry_task: Some(expiry_task),
            store_id,
            epoch,
            address,
            lan: None,
        })
    }
    pub fn lan_start(&mut self, config: crate::lan::LanConfig) -> Result<Value> {
        if self.shared.stopped.load(Ordering::Acquire) {
            return Err("CoreStopped");
        }
        if self.lan.as_ref().is_some_and(|lan| lan.running()) {
            return Err("LanAlreadyRunning");
        }
        let lan = lan_runtime::LanRuntime::start(
            self.runtime.as_ref().ok_or("CoreStopped")?,
            self.shared.clone(),
            config,
        )?;
        let status = lan.snapshot()?;
        self.lan = Some(lan);
        Ok(status)
    }
    pub fn lan_stop(&mut self) -> Result<Value> {
        if let Some(lan) = self.lan.as_mut() {
            lan.stop(self.runtime.as_ref().ok_or("CoreStopped")?)
        } else {
            self.lan_status()
        }
    }
    pub fn lan_status(&self) -> Result<Value> {
        match &self.lan {
            Some(lan) => lan.snapshot(),
            None => Ok(
                json!({"running":false,"ipv4_only":true,"ipv6_targets":true,"encrypted_transport":false,
                "listen_ip":null,"http_port":null,"socks_port":null,
                "udp_port_start":null,"udp_port_end":null,"active_connections":0,
                "accepted":0,"rejected":0,"auth_failures":0,"uploaded":0,"downloaded":0,
                "clients":[],"last_error":""}),
            ),
        }
    }
    /// A protocol-independent ingress into this runtime. Native TUN flows share
    /// listener admission, policies, DNS, accounting and node-revocation barriers.
    pub fn flow_dispatcher(&self) -> Result<FlowDispatcher> {
        Ok(FlowDispatcher::new(
            self.shared.clone(),
            self.runtime.as_ref().ok_or("CoreStopped")?.handle().clone(),
            self.probe.clone(),
        ))
    }

    pub fn prepare_native_tun(&self) -> Result<NativeTunLease> {
        self.flow_dispatcher()?.prepare_native_tun()
    }

    pub fn epoch(&self) -> u64 {
        self.epoch
    }
    pub fn store_id(&self) -> &str {
        &self.store_id
    }
    pub fn address(&self) -> SocketAddr {
        self.address
    }
    fn fields(&self, request_id: &str, state: &str) -> Result<Value> {
        let live = self.shared.live.lock().map_err(|_| "ConfigState")?;
        let state = if state == "committing"
            && live
                .closed_at
                .is_some_and(|at| at.elapsed() >= Duration::from_secs(2))
        {
            "reconciling"
        } else {
            state
        };
        Ok(
            json!({"ok":true,"request_id":request_id,"engine_epoch":self.epoch.to_string(),"generation":live.generation.to_string(),"expected_generation":live.generation.to_string(),"store_id":self.store_id,"applied_revision":live.plan.revision.to_string(),"plan_digest":live.plan.prepared.digest,"applied_mode":live.plan.prepared.runtime.policy.mode.as_str(),"transaction_state":state,"address":self.address.to_string()}),
        )
    }
    pub fn configuration(&self) -> Result<Value> {
        let transactions = self.transactions.lock().map_err(|_| "TransactionState")?;
        let mut result = self.fields(
            "",
            transactions
                .pending
                .as_ref()
                .map_or("idle", |p| p.phase.label()),
        )?;
        result["last_receipt"] = transactions.recent.clone().unwrap_or(Value::Null);
        Ok(result)
    }
    #[allow(clippy::too_many_arguments)]
    pub fn prepare(
        &self,
        request_id: String,
        store_id: &str,
        base_saved_revision: u64,
        candidate_revision: u64,
        expected_generation: u64,
        base_applied_revision: u64,
        candidate: RuntimeConfig,
        revoked_node_ids: Vec<String>,
    ) -> Result<Value> {
        identity_uuid(&request_id)?;
        if store_id != self.store_id {
            return Err("StoreIdentityMismatch");
        }
        if revoked_node_ids.len() > 2000
            || revoked_node_ids.iter().any(|id| {
                uuid_bytes(id).is_none()
                    || id.to_ascii_lowercase() != *id
                    || candidate.nodes.iter().any(|n| &n.id == id)
            })
        {
            return Err("RevocationSet");
        }
        let revoked_nodes: BTreeSet<_> = revoked_node_ids.into_iter().collect();
        let prepared = candidate.prepare()?;
        let mut transactions = self.transactions.lock().map_err(|_| "TransactionState")?;
        if let Some(pending) = &transactions.pending {
            if pending.request_id != request_id {
                return Err("Busy");
            };
            if pending.candidate.prepared.digest != prepared.digest
                || pending.candidate.revision != candidate_revision
                || pending.revoked_nodes != revoked_nodes
                || pending.base_revision != base_saved_revision
                || pending.base_revision != base_applied_revision
                || pending.base_generation != expected_generation
            {
                return Err("RequestIdentityMismatch");
            };
            let mut response = self.fields(&request_id, pending.phase.label())?;
            response["prepared_token"] = json!(pending.token);
            response["plan_digest"] = json!(pending.candidate.prepared.digest);
            response["candidate_revision"] = json!(candidate_revision.to_string());
            return Ok(response);
        }
        if let Some(recent) = &transactions.recent
            && recent["request_id"] == request_id
        {
            let binding = transactions
                .recent_binding
                .as_ref()
                .ok_or("RequestIdentityMismatch")?;
            if recent["candidate_digest"] != prepared.digest
                || binding.candidate_revision != candidate_revision
                || binding.base_revision != base_saved_revision
                || binding.base_revision != base_applied_revision
                || binding.base_generation != expected_generation
                || binding.revoked_nodes != revoked_nodes
            {
                return Err("RequestIdentityMismatch");
            };
            return Ok(recent.clone());
        }
        let live = self.shared.live.lock().map_err(|_| "ConfigState")?;
        if live.closed {
            return Err("RecoveryRequired");
        };
        if live.generation != expected_generation
            || live.plan.revision != base_applied_revision
            || base_saved_revision != base_applied_revision
        {
            return Err("RevisionConflict");
        }
        if candidate_revision <= base_saved_revision
            || candidate_revision <= transactions.high_water
        {
            return Err("RevisionConflict");
        }
        if self.shared.native_tun_leases.load(Ordering::Acquire) > 0 {
            native_flow::validate_tun_dns(&prepared.runtime)?;
        }
        let old = &live.plan.prepared.runtime;
        if prepared.runtime.listen != old.listen
            || prepared.runtime.limits.max_connections != old.limits.max_connections
            || serde_json::to_value(&prepared.runtime.inbound_auth).ok()
                != serde_json::to_value(&old.inbound_auth).ok()
        {
            return Err("RequiresRestart");
        }
        for missing in &prepared.runtime.policy.missing_targets {
            let target = match missing.kind {
                swirl_subscription::v2::MissingKind::Node => Target::Node {
                    id: missing.id.clone(),
                },
                swirl_subscription::v2::MissingKind::Group => Target::Group {
                    id: missing.id.clone(),
                },
            };
            if !old.policy.missing(&target)
                && !(missing.kind == swirl_subscription::v2::MissingKind::Group
                    && old.policy.group(&missing.id).is_some())
                && !(missing.kind == swirl_subscription::v2::MissingKind::Node
                    && revoked_nodes.contains(&missing.id))
            {
                return Err("UntrustedMissingTarget");
            }
        }
        drop(live);
        let candidate = Plan::new(
            prepared,
            self.runtime.as_ref().ok_or("CoreStopped")?,
            candidate_revision,
            request_id.clone(),
        )?;
        let token = random_token()?;
        transactions.high_water = candidate_revision;
        transactions.pending = Some(Pending {
            request_id: request_id.clone(),
            token: token.clone(),
            candidate,
            old: None,
            base_generation: expected_generation,
            base_revision: base_saved_revision,
            phase: Phase::Prepared,
            created: Instant::now(),
            committed: false,
            revoked_nodes,
        });
        self.expiry_notify.notify_one();
        let mut response = self.fields(&request_id, "preparing")?;
        response["prepared_token"] = json!(token);
        response["plan_digest"] = json!(
            transactions
                .pending
                .as_ref()
                .ok_or("TransactionState")?
                .candidate
                .prepared
                .digest
        );
        response["candidate_revision"] = json!(candidate_revision.to_string());
        response["expires_in_ms"] = json!(60000);
        Ok(response)
    }
    pub fn activate(
        &self,
        request_id: &str,
        token: &str,
        digest: &str,
        expected_generation: u64,
        candidate_revision: u64,
    ) -> Result<Value> {
        let mut transactions = self.transactions.lock().map_err(|_| "TransactionState")?;
        let pending = transactions.pending.as_mut().ok_or("PreparedMissing")?;
        if pending.request_id != request_id
            || pending.token != token
            || pending.candidate.prepared.digest != digest
            || pending.candidate.revision != candidate_revision
            || pending.base_generation != expected_generation
        {
            return Err("RequestIdentityMismatch");
        }
        if pending.phase != Phase::Prepared {
            return self.fields(request_id, pending.phase.label());
        }
        if pending.created.elapsed() > Duration::from_secs(60) {
            transactions.pending.take();
            return Err("PreparedExpired");
        }
        let mut live = self.shared.live.lock().map_err(|_| "ConfigState")?;
        if live.generation != expected_generation
            || expected_generation != pending.base_generation
            || live.plan.revision != pending.base_revision
            || live.closed
        {
            return Err("RevisionConflict");
        }
        if self.shared.native_tun_leases.load(Ordering::Acquire) > 0 {
            native_flow::validate_tun_dns(&pending.candidate.prepared.runtime)?;
        }
        let generation = live.generation.checked_add(1).ok_or("GenerationLimit")?;
        live.plan.policies.pause(true);
        live.closed = true;
        live.closed_at = Some(Instant::now());
        pending.old = Some(live.plan.clone());
        live.plan = pending.candidate.clone();
        live.generation = generation;
        pending.phase = Phase::Activated;
        self.expiry_notify.notify_one();
        drop(live);
        self.runtime
            .as_ref()
            .ok_or("CoreStopped")?
            .block_on(self.probe.invalidate_and_wait())?;
        self.fields(request_id, "committing")
    }
    pub fn rollback(
        &self,
        request_id: &str,
        token: &str,
        expected_generation: u64,
        old_revision: u64,
        old_digest: &str,
    ) -> Result<Value> {
        let mut transactions = self.transactions.lock().map_err(|_| "TransactionState")?;
        let pending = transactions.pending.as_mut().ok_or("PreparedMissing")?;
        if pending.request_id != request_id || pending.token != token {
            return Err("RequestIdentityMismatch");
        };
        if pending.committed {
            return Err("AlreadyCommitted");
        };
        if pending.phase == Phase::Prepared {
            pending.phase = Phase::RolledBack;
            self.expiry_notify.notify_one();
            return self.fields(request_id, "reconciling");
        }
        if pending.phase == Phase::RolledBack {
            return self.fields(request_id, "reconciling");
        }
        if pending.phase != Phase::Activated {
            return Err("RecoveryRequired");
        }
        let old = pending.old.as_ref().ok_or("RollbackUnavailable")?;
        if old.revision != old_revision || old.prepared.digest != old_digest {
            return Err("ReceiptMismatch");
        }
        let mut live = self.shared.live.lock().map_err(|_| "ConfigState")?;
        if live.generation != expected_generation || !live.closed {
            return Err("RevisionConflict");
        };
        live.generation = live.generation.checked_add(1).ok_or("GenerationLimit")?;
        live.plan = old.clone();
        pending.phase = Phase::RolledBack;
        drop(live);
        self.fields(request_id, "reconciling")
    }
    pub fn finish(&self, request_id: &str, token: &str, receipt: DurableReceipt) -> Result<Value> {
        let mut transactions = self.transactions.lock().map_err(|_| "TransactionState")?;
        if transactions.pending.is_none() {
            if let Some(recent) = &transactions.recent
                && recent["request_id"] == request_id
            {
                let binding = transactions
                    .recent_binding
                    .as_ref()
                    .ok_or("RequestIdentityMismatch")?;
                if binding.token != token
                    || binding.receipt
                        != serde_json::to_value(&receipt).map_err(|_| "ReceiptSerialization")?
                {
                    return Err("RequestIdentityMismatch");
                }
                return Ok(recent.clone());
            }
            return Err("PreparedMissing");
        }
        let pending = transactions.pending.as_mut().ok_or("PreparedMissing")?;
        if pending.request_id != request_id || pending.token != token {
            return Err("RequestIdentityMismatch");
        }
        if !matches!(
            pending.phase,
            Phase::Activated | Phase::RolledBack | Phase::RecoveryRequired
        ) {
            return Err("ActivationRequired");
        }
        let live_plan = self
            .shared
            .live
            .lock()
            .map_err(|_| "ConfigState")?
            .plan
            .clone();
        if receipt.store_id != self.store_id
            || decimal(&receipt.saved_revision)? != live_plan.revision
            || receipt.plan_digest != live_plan.prepared.digest
            || (receipt.request_id != request_id && receipt.request_id != live_plan.request_id)
        {
            return Err("ReceiptMismatch");
        }
        pending.committed = true;
        let runtime = self.runtime.as_ref().ok_or("CoreStopped")?;
        if pending.phase != Phase::RolledBack {
            if let Some(old) = &pending.old
                && let Err(error) = runtime.block_on(async {
                    old.policies.stop_and_wait().await?;
                    live_plan.policies.inherit_unchanged(
                        &old.policies,
                        serde_json::to_value(&old.prepared.runtime.dns).ok()
                            == serde_json::to_value(&live_plan.prepared.runtime.dns).ok(),
                    )?;
                    self.shared.revoke(&pending.revoked_nodes).await
                })
            {
                pending.phase = Phase::RecoveryRequired;
                return Err(error);
            }
            if let Err(error) = live_plan.policies.start() {
                pending.phase = Phase::RecoveryRequired;
                return Err(error);
            }
        } else {
            live_plan.policies.pause(false);
            pending.candidate.policies.stop();
        }
        let candidate_digest = pending.candidate.prepared.digest.clone();
        let outcome = if pending.phase == Phase::RolledBack {
            "rolled_back"
        } else {
            "applied"
        };
        {
            let mut live = self.shared.live.lock().map_err(|_| "ConfigState")?;
            live.closed = false;
            live.closed_at = None;
        }
        self.shared.notify.notify_waiters();
        let mut response = self.fields(request_id, "idle")?;
        response["outcome"] = json!(outcome);
        response["candidate_digest"] = json!(candidate_digest);
        response["candidate_revision"] = json!(pending.candidate.revision.to_string());
        let binding = RecentBinding {
            token: pending.token.clone(),
            candidate_revision: pending.candidate.revision,
            base_revision: pending.base_revision,
            base_generation: pending.base_generation,
            revoked_nodes: pending.revoked_nodes.clone(),
            receipt: serde_json::to_value(&receipt).map_err(|_| "ReceiptSerialization")?,
        };
        response["durable_receipt"] =
            serde_json::to_value(receipt).map_err(|_| "ReceiptSerialization")?;
        transactions.recent = Some(response.clone());
        transactions.recent_binding = Some(binding);
        transactions.pending.take();
        self.expiry_notify.notify_one();
        Ok(response)
    }
    pub fn status(&self, request_id: &str) -> Result<Value> {
        let transactions = self.transactions.lock().map_err(|_| "TransactionState")?;
        if let Some(pending) = &transactions.pending
            && pending.request_id == request_id
        {
            return self.fields(request_id, pending.phase.label());
        }
        if let Some(recent) = &transactions.recent
            && recent["request_id"] == request_id
        {
            return Ok(recent.clone());
        }
        let live = self.shared.live.lock().map_err(|_| "ConfigState")?;
        if live.plan.request_id != request_id {
            return Err("RequestUnknown");
        };
        drop(live);
        self.fields(request_id, "idle")
    }
    pub fn snapshot(&self) -> Result<Value> {
        let configuration = self.configuration()?;
        let live = self.shared.live.lock().map_err(|_| "ConfigState")?;
        let policies = live.plan.policies.report()?;
        let selected = live
            .plan
            .prepared
            .runtime
            .policy
            .default_policy
            .target
            .id()
            .unwrap_or("")
            .to_owned();
        let generation = live.generation.to_string();
        drop(live);
        let records = self.shared.records.lock().map_err(|_| "StatsState")?;
        let connections:Vec<_>=records.iter().rev().take(128).map(|(id,r)|json!({"id":id,"source_ip":r.peer.ip().to_string(),"source_port":r.peer.port(),"ingress":r.ingress,"host":r.target.host,"port":r.target.port,"node":r.node,"matched_rule":r.trace["rule_id"],"route":r.trace,"category":r.category,"transport_state":if r.ended{"closed"}else{"active"},"ended":r.ended,"error":r.error,"failure_stage":swirl_protocol::failure_stage(r.error),"upload":r.counters.upload.load(Ordering::Relaxed),"download":r.counters.download.load(Ordering::Relaxed),"elapsed_ms":r.started.elapsed().as_millis().min(u128::from(u64::MAX))as u64})).collect();
        Ok(
            json!({"schema":2,"engine":"swirl-rust","address":self.address,"generation":generation,"selected":selected,"selectors":{},"policies":policies,"configuration":configuration,"lan":self.lan_status()?,"running":self.task.as_ref().is_some_and(|t|!t.is_finished()),"active":self.shared.active.load(Ordering::Acquire),"accepted":self.shared.accepted.load(Ordering::Relaxed),"failed":self.shared.failed.load(Ordering::Relaxed),"rejected":self.shared.rejected.load(Ordering::Relaxed),"upload":self.shared.totals.upload.load(Ordering::Relaxed),"download":self.shared.totals.download.load(Ordering::Relaxed),"udp_dropped":self.shared.totals.udp_dropped.load(Ordering::Relaxed),"last_error":*self.shared.last_error.lock().map_err(|_|"StatsState")?,"connections":connections,"connection_records_total":records.len(),"connections_truncated":records.len()>128}),
        )
    }
    pub fn stop(&mut self) {
        let _ = self.lan_stop();
        self.shared.stopped.store(true, Ordering::Release);
        self.shared.notify.notify_waiters();
        let _ = self.probe.invalidate();
        if let Ok(live) = self.shared.live.lock() {
            live.plan.policies.stop();
        }
        if let Ok(mut transactions) = self.transactions.lock()
            && let Some(pending) = transactions.pending.take()
        {
            pending.candidate.policies.stop();
            if let Some(old) = pending.old {
                old.policies.stop();
            }
        }
        let _ = self.stop.send(true);
        if let Some(runtime) = self.runtime.take() {
            if let Some(task) = self.task.take() {
                runtime.block_on(async {
                    let _ = task.await;
                });
            }
            if let Some(task) = self.expiry_task.take() {
                runtime.block_on(async {
                    let _ = task.await;
                });
            }
            runtime.shutdown_timeout(Duration::from_millis(500));
        }
    }
    pub fn probe_status(&self) -> Result<ProbeStatus> {
        self.probe.status()
    }
    pub fn probe_cancel(&self) -> Result<ProbeStatus> {
        self.probe.cancel()
    }
    pub fn probe_start(
        &self,
        url: String,
        timeout_ms: Option<u64>,
        expected_status: Option<u16>,
    ) -> Result<ProbeStatus> {
        let live = self.shared.live.lock().map_err(|_| "ConfigState")?;
        if live.closed {
            return Err("Reconfiguring");
        }
        let options = swirl_subscription::HealthProbe {
            url,
            interval_ms: 300000,
            timeout_ms: timeout_ms.unwrap_or(8000),
            expected_status: expected_status.unwrap_or(204),
            tolerance_ms: 0,
            tls: None,
        };
        let target = options.target()?;
        let target = NetworkTarget {
            host: target.host,
            port: target.port,
        };
        let shared = self.shared.clone();
        self.probe.start_with(async move {
            let failed = |code| swirl_protocol::UrlTestFailure {
                stage: swirl_protocol::UrlTestStage::OutboundConnect,
                code,
                http_status: None,
                outbound_timing: None,
            };
            let (plan, generation) = shared.admit().await.map_err(failed)?;
            let route = route(
                plan,
                target,
                "127.0.0.1".parse().map_err(|_| failed("ProbeSource"))?,
                generation,
            )
            .await
            .map_err(failed)?;
            if let Some(transport) = route.transport {
                swirl_protocol::url_test_head_with_transport(
                    &route.node.outbound,
                    &options,
                    &route.resolver,
                    expected_status,
                    &transport,
                )
                .await
            } else {
                swirl_protocol::url_test_head(
                    &route.node.outbound,
                    &options,
                    &route.resolver,
                    expected_status,
                )
                .await
            }
        })
    }
}
impl Drop for Core {
    fn drop(&mut self) {
        self.stop();
    }
}

async fn expire_prepared(
    transactions: Arc<Mutex<Transactions>>,
    notify: Arc<Notify>,
    mut stopped: watch::Receiver<bool>,
    shared: Arc<Shared>,
    store_id: String,
    epoch: u64,
) {
    loop {
        let changed = notify.notified();
        tokio::pin!(changed);
        changed.as_mut().enable();
        let delay = {
            let Ok(transactions) = transactions.lock() else {
                return;
            };
            transactions
                .pending
                .as_ref()
                .filter(|pending| pending.phase == Phase::Prepared)
                .map(|pending| Duration::from_secs(60).saturating_sub(pending.created.elapsed()))
        };
        if let Some(delay) = delay {
            tokio::select! {biased;_=stopped.changed()=>return,_=changed=>continue,_=tokio::time::sleep(delay)=>{}}
            let Ok(mut transactions) = transactions.lock() else {
                return;
            };
            if transactions.pending.as_ref().is_some_and(|pending| {
                pending.phase == Phase::Prepared
                    && pending.created.elapsed() >= Duration::from_secs(60)
            }) && let Some(pending) = transactions.pending.take()
            {
                let binding = RecentBinding {
                    token: pending.token,
                    candidate_revision: pending.candidate.revision,
                    base_revision: pending.base_revision,
                    base_generation: pending.base_generation,
                    revoked_nodes: pending.revoked_nodes,
                    receipt: Value::Null,
                };
                let Ok(live) = shared.live.lock() else { return };
                transactions.recent = Some(
                    json!({"ok":false,"error":"PreparedExpired","code":"PreparedExpired","phase":"prepare","request_id":pending.request_id,"engine_epoch":epoch.to_string(),"generation":live.generation.to_string(),"store_id":store_id,"applied_revision":live.plan.revision.to_string(),"applied_mode":live.plan.prepared.runtime.policy.mode.as_str(),"transaction_state":"idle","candidate_digest":pending.candidate.prepared.digest}),
                );
                transactions.recent_binding = Some(binding);
            }
        } else {
            tokio::select! {biased;_=stopped.changed()=>return,_=changed=>{}}
        }
    }
}

struct Routed {
    node: Node,
    target: NetworkTarget,
    resolver: Arc<Resolver>,
    transport: Option<Transport>,
    trace: Value,
    generation: u64,
    limit: Duration,
}
struct PolicyDnsTransport {
    node: Node,
    transport: Option<Transport>,
    bootstrap: Arc<Resolver>,
    limit: Duration,
}
impl swirl_dns::QueryTransport for PolicyDnsTransport {
    fn connect(
        &self,
        address: SocketAddr,
    ) -> std::pin::Pin<
        Box<dyn std::future::Future<Output = Result<swirl_transport::BoxStream>> + Send + '_>,
    > {
        Box::pin(async move {
            // Ingress resolver views may restrict learned physical endpoints.
            // DNS carried through a selected proxy is still an outbound target
            // and must not become a path to a protected host service.
            if !self.bootstrap.endpoint_allowed(address) {
                return Err("DnsEndpointForbidden");
            }
            let target = NetworkTarget {
                host: address.ip().to_string(),
                port: address.port(),
            };
            if let Some(transport) = &self.transport {
                swirl_protocol::connect_with_transport(
                    &self.node.outbound,
                    &target,
                    &self.bootstrap,
                    self.limit,
                    transport,
                )
                .await
            } else {
                swirl_protocol::connect(&self.node.outbound, &target, &self.bootstrap, self.limit)
                    .await
            }
        })
    }
}
/// Pin an unresolved ingress target through the existing encrypted DNS and
/// the already selected outbound. The proxy receives a checked address, never
/// another opportunity to resolve a client-controlled name. Domain routing and
/// application TLS/HTTP Host remain based on the original request.
async fn pin_proxy_target(
    routed: &mut Routed,
    check: impl Fn(&NetworkTarget) -> Result<()>,
) -> Result<()> {
    if matches!(
        routed.node.outbound,
        Outbound::Direct {} | Outbound::Reject {}
    ) || routed.target.host.parse::<IpAddr>().is_ok()
    {
        return Ok(());
    }
    let original = routed.target.clone();
    let transport = PolicyDnsTransport {
        node: routed.node.clone(),
        transport: routed.transport.clone(),
        bootstrap: routed.resolver.clone(),
        limit: routed.limit,
    };
    let addresses = timeout(
        routed.limit,
        routed
            .resolver
            .resolve_with_transport(&original.host, original.port, &transport),
    )
    .await
    .map_err(|_| "IngressTargetDnsTimeout")??;
    if addresses.is_empty() || addresses.len() > 16 {
        return Err("IngressTargetDnsAnswers");
    }
    for address in &addresses {
        check(&NetworkTarget {
            host: address.ip().to_string(),
            port: address.port(),
        })?;
    }
    let selected = addresses[0].ip().to_string();
    routed.target.host = selected.clone();
    routed.trace["target_domain"] = json!(original.host);
    routed.trace["chosen_ip"] = json!(selected);
    routed.trace["dns_path"] = json!("configured_encrypted_via_selected_outbound");
    routed.trace["dns_profile"] = json!("target");
    Ok(())
}

async fn classify(plan: &Plan, host: &str, port: u16) -> Result<Vec<SocketAddr>> {
    let resolver = plan
        .prepared
        .classification
        .as_ref()
        .ok_or("ClassificationDnsUnavailable")?;
    if plan.prepared.runtime.policy.classification_dns == ClassificationDns::ViaDefaultPolicy {
        let selected = plan.policies.resolve(
            &plan.prepared.runtime.policy.default_policy.target,
            "policy:default",
            "classification-dns",
        )?;
        let node = plan
            .prepared
            .base
            .nodes
            .iter()
            .find(|node| node.id == selected.leaf)
            .ok_or("MissingTarget")?
            .clone();
        let transport = PolicyDnsTransport {
            transport: plan.prepared.runtime.transports.get(&node.id).cloned(),
            node,
            bootstrap: plan.prepared.resolver.clone(),
            limit: Duration::from_millis(plan.prepared.runtime.limits.handshake_timeout_ms),
        };
        resolver
            .resolve_with_transport(host, port, &transport)
            .await
    } else {
        resolver.resolve(host, port).await
    }
}
async fn route(
    plan: Arc<Plan>,
    target: NetworkTarget,
    source: IpAddr,
    generation: u64,
) -> Result<Routed> {
    let runtime = &plan.prepared.runtime;
    let policy = &runtime.policy;
    let mut known = plan
        .prepared
        .resolver
        .mapped_host(&target.host)
        .or_else(|| target.host.parse().ok());
    let mut classification_attempted = false;
    let configured_path = if !runtime.dns.tls_servers.is_empty() {
        "configured_encrypted"
    } else if !runtime.dns.servers.is_empty() {
        "configured_plaintext"
    } else {
        "system"
    };
    let mut dns_path = if target.host.parse::<IpAddr>().is_ok() {
        "literal"
    } else if known.is_some() {
        "static_hosts"
    } else {
        "remote_outbound"
    };
    let mut classification_path = None;
    let mut resolved_for_rule = false;
    let china = match (
        plan.prepared.china.0.as_deref(),
        plan.prepared.china.1.as_deref(),
    ) {
        (Some(a), Some(b)) => Some((a, b)),
        _ => None,
    };
    let mut decision = swirl_routing::v2::select(
        policy,
        &target.host,
        target.port,
        source,
        known,
        false,
        china,
    )?;
    if let Some(purpose) = decision.resolution {
        classification_attempted = purpose == ResolutionPurpose::ChinaClassification;
        if classification_attempted {
            classification_path = Some(match policy.classification_dns {
                ClassificationDns::DirectEncrypted => "direct_encrypted",
                ClassificationDns::ViaDefaultPolicy => "via_default_policy",
                ClassificationDns::Disabled => "disabled",
            });
        } else {
            resolved_for_rule = true;
        }
        let resolution = async {
            if classification_attempted {
                classify(&plan, &target.host, target.port).await
            } else {
                plan.prepared
                    .resolver
                    .resolve(&target.host, target.port)
                    .await
            }
        };
        match timeout(
            Duration::from_millis(runtime.limits.handshake_timeout_ms),
            resolution,
        )
        .await
        {
            Ok(Ok(addresses)) => {
                known = Some(addresses.first().ok_or("RouteDnsEmpty")?.ip());
                dns_path = if classification_attempted {
                    classification_path.unwrap_or("unavailable")
                } else {
                    configured_path
                };
            }
            _ if classification_attempted => {}
            _ => return Err("MandatoryRuleDnsUnavailable"),
        }
        decision = swirl_routing::v2::select(
            policy,
            &target.host,
            target.port,
            source,
            known,
            classification_attempted,
            china,
        )?;
        if decision.resolution.is_some() {
            return Err("MandatoryRuleDnsUnavailable");
        }
    }
    let service = decision
        .catalog_key
        .as_deref()
        .or(decision.service_policy_id.as_deref())
        .unwrap_or("unclassified");
    let entry = decision
        .service_policy_id
        .as_deref()
        .unwrap_or("policy:default");
    let resolved = plan.policies.resolve(&decision.target, entry, service)?;
    let node = plan
        .prepared
        .base
        .nodes
        .iter()
        .find(|n| n.id == resolved.leaf)
        .ok_or("MissingTarget")?
        .clone();
    let mut routed = target.clone();
    let mut chosen_ip = known;
    if target.host.eq_ignore_ascii_case("localhost") {
        dns_path = "fixed_local";
        routed.host = "127.0.0.1".into();
        chosen_ip = Some("127.0.0.1".parse().map_err(|_| "LocalAddress")?);
    } else if let Some(ip) = known {
        routed.host = ip.to_string();
    } else if matches!(node.outbound, Outbound::Direct {}) {
        dns_path = configured_path;
        let addresses = plan
            .prepared
            .resolver
            .resolve(&target.host, target.port)
            .await?;
        let address = addresses.first().ok_or("RouteDnsEmpty")?;
        if swirl_routing::v2::forbidden_ip(address.ip()) {
            return Err("InvalidTarget");
        };
        routed.host = address.ip().to_string();
        chosen_ip = Some(address.ip());
    }
    let trace = json!({"revision":plan.revision.to_string(),"generation":generation.to_string(),"mode":policy.mode.as_str(),"rule_id":decision.rule_id,"tier":decision.tier,"service_policy_id":decision.service_policy_id,"catalog_key":decision.catalog_key,"group_chain":resolved.chain,"leaf_node_id":node.id,"source_id":runtime.node_sources.get(&node.id),"chosen_ip":chosen_ip.map(|ip|ip.to_string()),"dns_profile":if classification_attempted{"classification"}else if resolved_for_rule{"mandatory_rules"}else{"target"},"dns_path":dns_path,"classification_dns_path":classification_path,"classification_state":decision.classification_state,"rejection_code":if matches!(node.outbound,Outbound::Reject{}){Some("Rejected")}else{None},"affinity_reason":resolved.affinity_reason});
    Ok(Routed {
        transport: runtime.transports.get(&node.id).cloned(),
        node,
        target: routed,
        resolver: plan.prepared.resolver.clone(),
        trace,
        generation,
        limit: Duration::from_millis(runtime.limits.handshake_timeout_ms),
    })
}

async fn cancelled(receiver: &mut watch::Receiver<bool>) {
    if *receiver.borrow() {
        return;
    }
    let _ = receiver.changed().await;
}
async fn route_flow(
    shared: &Arc<Shared>,
    id: u64,
    peer: SocketAddr,
    target: &NetworkTarget,
    counters: Arc<Counters>,
    native: bool,
) -> Result<Routed> {
    if target.port == 0 || !swirl_subscription::valid_host(&target.host) {
        return Err("InvalidTarget");
    }
    let (plan, generation) = shared.admit().await?;
    if native || shared.native_tun_leases.load(Ordering::Acquire) > 0 {
        native_flow::validate_tun_dns(&plan.prepared.runtime)?;
    }
    let routed = route(plan, target.clone(), peer.ip(), generation).await?;
    if routed.target.port == shared.address.port()
        && routed
            .target
            .host
            .parse::<IpAddr>()
            .ok()
            .is_some_and(|ip| swirl_routing::v2::normalize_ip(ip).is_loopback())
    {
        return Err("ProxyLoop");
    }
    shared.bind(id, &routed.node.id)?;
    shared.records.lock().map_err(|_| "StatsState")?.insert(
        id,
        Record {
            peer,
            ingress: if native { "native_tun" } else { "loopback" },
            target: target.clone(),
            trace: routed.trace.clone(),
            node: routed.node.id.clone(),
            category: if matches!(routed.node.outbound, Outbound::Direct {}) {
                "direct"
            } else if matches!(routed.node.outbound, Outbound::Reject {}) {
                "reject"
            } else {
                "proxy"
            },
            counters,
            started: Instant::now(),
            ended: false,
            error: "",
        },
    );
    if matches!(routed.node.outbound, Outbound::Reject {}) {
        return Err("Rejected");
    }
    Ok(routed)
}

async fn connect_routed_tcp(routed: &Routed) -> Result<swirl_transport::BoxStream> {
    if let Some(transport) = &routed.transport {
        swirl_protocol::connect_with_transport(
            &routed.node.outbound,
            &routed.target,
            &routed.resolver,
            routed.limit,
            transport,
        )
        .await
    } else {
        swirl_protocol::connect(
            &routed.node.outbound,
            &routed.target,
            &routed.resolver,
            routed.limit,
        )
        .await
    }
}

async fn session(
    mut inbound: TcpStream,
    peer: SocketAddr,
    shared: Arc<Shared>,
    id: u64,
    mut cancellation: watch::Receiver<bool>,
    lan: Option<lan_runtime::Ingress>,
) -> Result<()> {
    inbound.set_nodelay(true).map_err(|_| "SocketOptions")?;
    let (auth, limit) = {
        let live = shared.live.lock().map_err(|_| "ConfigState")?;
        (
            lan.as_ref()
                .map(|ingress| ingress.config.auth.clone())
                .or_else(|| live.plan.prepared.runtime.inbound_auth.clone()),
            Duration::from_millis(live.plan.prepared.runtime.limits.handshake_timeout_ms),
        )
    };
    let handshake = async {
        if let Some(ingress) = &lan {
            ingress.check_protocol(&inbound).await?;
        }
        swirl_protocol::accept(&mut inbound, &auth).await
    };
    let request = tokio::select! {biased;_=cancelled(&mut cancellation)=>return Err("SessionRevoked"),request=timeout(limit,handshake)=>request.map_err(|_|"HandshakeTimeout")??};
    drop(auth);
    if let Some(ingress) = &lan {
        ingress.authenticated();
    }
    if request.udp {
        return udp_associate(inbound, peer, request, shared, id, cancellation, lan).await;
    }
    let counters = lan.as_ref().map_or_else(
        || Arc::new(Counters::default()),
        |ingress| ingress.counters.clone(),
    );
    let mut established = false;
    let work = async {
        if let Some(ingress) = &lan {
            ingress.check_target(&request.target)?;
        }
        let mut routed =
            route_flow(&shared, id, peer, &request.target, counters.clone(), false).await?;
        if let Some(ingress) = &lan {
            ingress.check_target(&routed.target)?;
            ingress
                .prepare_outbound(&mut routed, shared.address)
                .await?;
            if let Ok(mut records) = shared.records.lock()
                && let Some(record) = records.get_mut(&id)
            {
                record.ingress = "lan";
                record.trace = routed.trace.clone();
            }
        }
        let mut upstream = connect_routed_tcp(&routed).await?;
        drop(routed);
        swirl_protocol::reply(&mut inbound, request.kind, true).await?;
        established = true;
        if matches!(request.kind, swirl_protocol::InboundKind::HttpForward) {
            return Box::pin(swirl_protocol::http_single::forward(
                &mut inbound,
                &mut upstream,
                &request.initial,
                limit,
                counters,
                shared.totals.clone(),
            ))
            .await;
        }
        if !request.initial.is_empty() {
            timeout(limit, async {
                upstream.write_all(&request.initial).await?;
                upstream.flush().await
            })
            .await
            .map_err(|_| "InitialWriteTimeout")?
            .map_err(|_| "InitialWrite")?;
            counters
                .upload
                .fetch_add(request.initial.len() as u64, Ordering::Relaxed);
            shared
                .totals
                .upload
                .fetch_add(request.initial.len() as u64, Ordering::Relaxed);
        }
        swirl_transport::relay(&mut inbound, &mut upstream, counters, shared.totals.clone())
            .await
            .map_err(|error| super::stream_failure_code(&error))
    };
    let result = tokio::select! {
        biased;
        _ = cancelled(&mut cancellation) => Err("SessionRevoked"),
        _ = lan_runtime::idle(&lan) => Err("LanIdleTimeout"),
        result = work => result,
    };
    if lan.is_some()
        && result.is_err()
        && !established
        && !matches!(result, Err("SessionRevoked" | "CoreStopped"))
    {
        let _ = timeout(
            limit,
            swirl_protocol::reply(&mut inbound, request.kind, false),
        )
        .await;
    }
    result
}

struct PreparationGuard {
    shared: Arc<Shared>,
    id: u64,
    active: bool,
}
impl Drop for PreparationGuard {
    fn drop(&mut self) {
        if self.active {
            self.shared.end_preparation(self.id);
        }
    }
}
struct UdpFlow {
    routed: Routed,
    plan: Arc<SessionPlan>,
}
fn udp_flow(routed: Routed) -> Arc<UdpFlow> {
    let base = Arc::new(Config {
        schema: 1,
        listen: "127.0.0.1:0".parse().expect("fixed loopback literal"),
        selected: routed.node.id.clone(),
        nodes: vec![routed.node.clone()],
        rules: vec![],
        smart_routing: false,
        selectors: vec![],
        dns: Dns::default(),
        china_rules_directory: None,
        inbound_auth: None,
        limits: Limits {
            max_connections: 1,
            handshake_timeout_ms: routed.limit.as_millis().min(u128::from(u64::MAX)) as u64,
        },
    });
    let transports = Arc::new(
        routed
            .transport
            .as_ref()
            .map(|t| (routed.node.id.clone(), t.clone()))
            .into_iter()
            .collect::<BTreeMap<_, _>>(),
    );
    let policies = Arc::new(LegacyPolicies::new(
        tokio::runtime::Handle::current(),
        base.clone(),
        routed.resolver.clone(),
        transports.clone(),
    ));
    let policies = Arc::new(policies.view(&base).expect("empty policy graph"));
    let plan = Arc::new(SessionPlan {
        config: base,
        transports,
        resolver: routed.resolver.clone(),
        policies,
        cn_domains: None,
        cn_ips: None,
    });
    Arc::new(UdpFlow { routed, plan })
}
enum UdpPacket {
    Datagram(SocketAddr, Vec<u8>),
    Proxy(NetworkTarget, Vec<u8>),
}
struct UdpPrepared {
    flow: Arc<UdpFlow>,
    key: String,
    packet: UdpPacket,
    permit: OwnedSemaphorePermit,
    payload_len: usize,
}
#[allow(clippy::too_many_arguments)]
async fn prepare_udp(
    shared: Arc<Shared>,
    id: u64,
    peer: IpAddr,
    target: NetworkTarget,
    payload: Vec<u8>,
    existing: Option<Arc<UdpFlow>>,
    permit: OwnedSemaphorePermit,
    lan: Option<lan_runtime::Ingress>,
) -> Result<UdpPrepared> {
    let key = target.authority();
    let flow = if let Some(flow) = existing {
        flow
    } else {
        let mut guard = PreparationGuard {
            shared: shared.clone(),
            id,
            active: true,
        };
        if let Some(ingress) = &lan {
            ingress.check_target(&target)?;
        }
        let (plan, generation) = shared.admit().await?;
        let mut routed = route(plan, target.clone(), peer, generation).await?;
        if let Some(ingress) = &lan {
            ingress.check_target(&routed.target)?;
            ingress
                .prepare_outbound(&mut routed, shared.address)
                .await?;
        }
        if routed.target.port == shared.address.port()
            && routed
                .target
                .host
                .parse::<IpAddr>()
                .ok()
                .is_some_and(|ip| swirl_routing::v2::normalize_ip(ip).is_loopback())
        {
            return Err("ProxyLoop");
        };
        shared.bind(id, &routed.node.id)?;
        guard.active = false;
        udp_flow(routed)
    };
    let payload_len = payload.len();
    let packet = match &flow.routed.node.outbound {
        Outbound::Direct {} => {
            let address = SocketAddr::new(
                flow.routed
                    .target
                    .host
                    .parse()
                    .map_err(|_| "UdpDirectAddress")?,
                flow.routed.target.port,
            );
            UdpPacket::Datagram(address, payload)
        }
        Outbound::Reject {} => return Err("Rejected"),
        Outbound::Shadowsocks {
            host,
            port,
            password,
            cipher,
            udp: true,
            ..
        } if !cipher.starts_with("2022-") => {
            let mut plain = Vec::new();
            flow.routed.target.encode(&mut plain)?;
            plain.extend(payload);
            let packet = swirl_protocol::ss_encrypt_datagram(password, cipher, &plain)
                .map_err(|_| "UdpEncode")?;
            let address = flow
                .routed
                .resolver
                .resolve(host, *port)
                .await?
                .into_iter()
                .next()
                .ok_or("DnsEmpty")?;
            UdpPacket::Datagram(address, packet)
        }
        Outbound::Socks5 { udp: true, .. }
        | Outbound::Vless { udp: true, .. }
        | Outbound::Trojan { udp: true, .. }
        | Outbound::Shadowsocks { udp: true, .. } => {
            UdpPacket::Proxy(flow.routed.target.clone(), payload)
        }
        Outbound::Hysteria2(c) if c.udp => UdpPacket::Proxy(flow.routed.target.clone(), payload),
        Outbound::Tuic(c) if c.udp => UdpPacket::Proxy(flow.routed.target.clone(), payload),
        _ => return Err("UdpProxyUnsupportedOrRejected"),
    };
    Ok(UdpPrepared {
        flow,
        key,
        packet,
        permit,
        payload_len,
    })
}
#[allow(clippy::too_many_arguments)]
async fn udp_associate(
    mut control: TcpStream,
    peer: SocketAddr,
    request: Inbound,
    shared: Arc<Shared>,
    id: u64,
    mut cancellation: watch::Receiver<bool>,
    lan: Option<lan_runtime::Ingress>,
) -> Result<()> {
    shared.end_preparation(id);
    let requested: IpAddr = request
        .target
        .host
        .parse()
        .map_err(|_| "UdpClientAddress")?;
    if !requested.is_unspecified() && requested != peer.ip() {
        return Err("UdpClientAddress");
    }
    let local_ip = control.local_addr().map_err(|_| "UdpLocalAddress")?.ip();
    let lan_relay = match lan.as_ref().map(|ingress| ingress.bind_udp()).transpose() {
        Ok(relay) => relay,
        Err(error) => {
            let _ = swirl_protocol::reply(&mut control, request.kind, false).await;
            return Err(error);
        }
    };
    let local_relay = if lan_relay.is_none() {
        // An inbound relay binds the accepted local address, never the remote
        // peer address and never an outbound physical-interface constraint.
        Some(
            swirl_transport::bind_udp_inbound(SocketAddr::new(local_ip, 0))
                .await
                .map_err(|_| "UdpBind")?,
        )
    } else {
        None
    };
    let relay = lan_relay
        .as_ref()
        .map(|lease| lease.socket())
        .or(local_relay.as_ref())
        .ok_or("UdpBind")?;
    let v4 = swirl_transport::bind_udp(SocketAddr::from(([0, 0, 0, 0], 0)))
        .await
        .map_err(|_| "UdpBind")?;
    // IPv4 ingress does not restrict IPv6 destinations. Preserve the existing
    // outbound family sockets; IPv6 listener exposure remains disabled.
    let v6 = swirl_transport::bind_udp(SocketAddr::from(([0u16; 8], 0)))
        .await
        .map_err(|_| "UdpBindV6")?;
    let address = relay.local_addr().map_err(|_| "UdpBind")?;
    let mut response = vec![5, 0, 0];
    NetworkTarget {
        host: address.ip().to_string(),
        port: address.port(),
    }
    .encode(&mut response)?;
    control.write_all(&response).await.map_err(|_| "UdpReply")?;
    let counters = lan.as_ref().map_or_else(
        || Arc::new(Counters::default()),
        |ingress| ingress.counters.clone(),
    );
    shared.records.lock().map_err(|_| "StatsState")?.insert(
        id,
        Record {
            peer,
            ingress: if lan.is_some() { "lan" } else { "loopback" },
            target: request.target.clone(),
            trace: json!({"rule_id":"per_datagram","mode":"pending"}),
            node: String::new(),
            category: "udp",
            counters: counters.clone(),
            started: Instant::now(),
            ended: false,
            error: "",
        },
    );
    let mut client =
        (request.target.port != 0).then_some(SocketAddr::new(peer.ip(), request.target.port));
    let mut flows: BTreeMap<String, (Instant, Arc<UdpFlow>)> = BTreeMap::new();
    let mut destinations: BTreeMap<SocketAddr, (Instant, Arc<UdpFlow>)> = BTreeMap::new();
    let mut pending: JoinSet<Result<UdpPrepared>> = JoinSet::new();
    let slots = Arc::new(Semaphore::new(4));
    let mut pool = socks5_udp::Pool::dynamic(counters.clone(), shared.totals.clone());
    let (mut incoming, mut from_v4, mut from_v6) =
        (vec![0u8; 65535], vec![0u8; 65535], vec![0u8; 65535]);
    let mut closed = [0u8; 1];
    let idle = lan_runtime::idle(&lan);
    tokio::pin!(idle);
    let outcome = loop {
        tokio::select! {biased;
                    _=cancelled(&mut cancellation)=>break Err("SessionRevoked"),
                    _= &mut idle=>break Err("LanIdleTimeout"),
                    _=control.read(&mut closed)=>break Ok(()),
                    Some(prepared)=pending.join_next(),if !pending.is_empty()=>{
                        let prepared = match prepared {
                            Ok(Ok(prepared)) => prepared,
                            Ok(Err(error)) => {
                                if let Some(ingress) = &lan { ingress.error(error); }
                                super::udp_drop(&counters, &shared.totals);
                                continue;
                            }
                            Err(_) => { super::udp_drop(&counters, &shared.totals); continue; }
                        };flows.retain(|_,(at,_)|at.elapsed()<Duration::from_secs(30));if flows.len()>=64&&!flows.contains_key(&prepared.key){super::udp_drop(&counters,&shared.totals);continue}
                        flows.insert(prepared.key,(Instant::now(),prepared.flow.clone()));if let Ok(mut records)=shared.records.lock()&& let Some(record)=records.get_mut(&id){record.node=prepared.flow.routed.node.id.clone();record.trace=prepared.flow.routed.trace.clone();record.target=prepared.flow.routed.target.clone();}
                        match prepared.packet{
                            UdpPacket::Proxy(target,payload)=>pool.send_with_plan(socks5_udp::Flow{plan:prepared.flow.plan.clone(),generation:prepared.flow.routed.generation,node_id:prepared.flow.routed.node.id.clone(),cancellation:Some(cancellation.clone())},target,payload,prepared.permit),
                            UdpPacket::Datagram(address,packet)=>{destinations.retain(|_,(at,_)|at.elapsed()<Duration::from_secs(30));if(destinations.len()>=64&&!destinations.contains_key(&address))||destinations.get(&address).is_some_and(|(_,old)|old.routed.node.id!=prepared.flow.routed.node.id||old.routed.generation!=prepared.flow.routed.generation){super::udp_drop(&counters,&shared.totals);continue}let socket=if address.is_ipv4(){&v4}else{&v6};let sent=tokio::select!{biased;_=cancelled(&mut cancellation)=>break Err("SessionRevoked"),sent=socket.send_to(&packet,address)=>sent};if sent.is_err(){super::udp_drop(&counters,&shared.totals);continue}destinations.insert(address,(Instant::now(),prepared.flow));counters.upload.fetch_add(prepared.payload_len as u64,Ordering::Relaxed);shared.totals.upload.fetch_add(prepared.payload_len as u64,Ordering::Relaxed);drop(prepared.permit);}
                        }
                    },
                    Some(reply)=pool.next_reply()=>{if let Some(client)=client{let sent=tokio::select!{biased;_=cancelled(&mut cancellation)=>break Err("SessionRevoked"),_=control.read(&mut closed)=>break Ok(()),sent=reply.send_to(relay,client)=>sent};match sent{Ok(size)=>{counters.download.fetch_add(size as u64,Ordering::Relaxed);shared.totals.download.fetch_add(size as u64,Ordering::Relaxed);},Err(())=>super::udp_drop(&counters,&shared.totals)}}},
                    received=relay.recv_from(&mut incoming)=>{
                        let(n,source)=match received{Ok(packet)=>packet,Err(error)if super::transient_udp(&error)=>{super::udp_drop(&counters,&shared.totals);continue},Err(_)=>break Err("UdpReceive")};if source.ip()!=peer.ip()||client.is_some_and(|client|client!=source)||n<4||incoming[..3]!=[0,0,0]{continue}let mut cursor=&incoming[3..n];let Ok(target)=swirl_protocol::read_target(&mut cursor,false).await else{continue};client=Some(source);let Ok(permit)=slots.clone().try_acquire_owned()else{super::udp_drop(&counters,&shared.totals);continue};flows.retain(|_,(at,_)|at.elapsed()<Duration::from_secs(30));let existing=flows.get(&target.authority()).map(|(_,flow)|flow.clone());if existing.is_none(){if flows.len()>=64{super::udp_drop(&counters,&shared.totals);continue}
        if shared.begin_preparation(id).is_err(){break Err("SessionRevoked")}}pending.spawn(prepare_udp(shared.clone(),id,peer.ip(),target,cursor.to_vec(),existing,permit,lan.clone()));
                    },
                    received=v4.recv_from(&mut from_v4)=>{if let Ok((n,source))=received{let response=tokio::select!{biased;_=cancelled(&mut cancellation)=>break Err("SessionRevoked"),_=control.read(&mut closed)=>break Ok(()),result=timeout(Duration::from_secs(3),udp_response(relay,client,source,&from_v4[..n],&destinations,&counters,&shared.totals))=>result.map_err(|_|"UdpSendTimeout")};match response{Ok(Ok(()))=>{},Ok(Err(code))|Err(code)=>break Err(code)}}},
                    received=v6.recv_from(&mut from_v6)=>{if let Ok((n,source))=received{let response=tokio::select!{biased;_=cancelled(&mut cancellation)=>break Err("SessionRevoked"),_=control.read(&mut closed)=>break Ok(()),result=timeout(Duration::from_secs(3),udp_response(relay,client,source,&from_v6[..n],&destinations,&counters,&shared.totals))=>result.map_err(|_|"UdpSendTimeout")};match response{Ok(Ok(()))=>{},Ok(Err(code))|Err(code)=>break Err(code)}}}
                }
    };
    pending.abort_all();
    while pending.join_next().await.is_some() {}
    pool.shutdown().await;
    drop(flows);
    drop(destinations);
    outcome
}
async fn udp_response(
    relay: &tokio::net::UdpSocket,
    client: Option<SocketAddr>,
    source: SocketAddr,
    payload: &[u8],
    destinations: &BTreeMap<SocketAddr, (Instant, Arc<UdpFlow>)>,
    counters: &Counters,
    total: &Counters,
) -> Result<()> {
    let Some(client) = client else { return Ok(()) };
    let Some((at, flow)) = destinations.get(&source) else {
        return Ok(());
    };
    if at.elapsed() >= Duration::from_secs(30) {
        return Ok(());
    }
    let decoded;
    let (target, payload) = if let Outbound::Shadowsocks {
        password, cipher, ..
    } = &flow.routed.node.outbound
    {
        decoded = match swirl_protocol::ss_decrypt_datagram(password, cipher, payload) {
            Ok(decoded) => decoded,
            Err(_) => return Ok(()),
        };
        let mut cursor = decoded.as_slice();
        let target = swirl_protocol::read_target(&mut cursor, false).await?;
        (target, cursor)
    } else {
        (
            NetworkTarget {
                host: source.ip().to_string(),
                port: source.port(),
            },
            payload,
        )
    };
    let mut packet = vec![0, 0, 0];
    target.encode(&mut packet)?;
    packet.extend_from_slice(payload);
    relay
        .send_to(&packet, client)
        .await
        .map_err(|_| "UdpSend")?;
    counters
        .download
        .fetch_add(payload.len() as u64, Ordering::Relaxed);
    total
        .download
        .fetch_add(payload.len() as u64, Ordering::Relaxed);
    Ok(())
}

#[cfg(test)]
#[path = "v2_runtime_tests.rs"]
mod runtime_tests;
#[cfg(test)]
#[path = "v2_tests.rs"]
mod tests;
