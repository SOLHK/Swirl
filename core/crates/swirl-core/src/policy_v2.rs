//! Profile-scoped leaf probes and context-aware nested policy selection.
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicUsize, Ordering},
    },
    time::{Duration, Instant},
};
use swirl_dns::Resolver;
use swirl_protocol::Transport;
use swirl_subscription::{
    Node, PolicyStrategy,
    v2::{DIRECT_NODE_ID, PolicyDocument, Probe, REJECT_NODE_ID, Target},
};
use tokio::{
    runtime::Handle,
    sync::{Notify, Semaphore, watch},
    task::{JoinHandle, JoinSet},
    time::{sleep_until, timeout},
};
type Result<T> = std::result::Result<T, &'static str>;

#[derive(Clone)]
struct Health {
    latency: Option<u64>,
    checked: Instant,
    successes: u8,
    failures: u8,
    eligible: bool,
    error: &'static str,
}
#[derive(Clone)]
struct Pin {
    branch: Target,
    leaf: String,
    touched: Instant,
    switched: Instant,
}
#[derive(Default)]
struct Registry {
    health: BTreeMap<(String, String), Health>,
    pins: BTreeMap<String, Pin>,
    epoch: u64,
}
#[derive(Clone, Debug)]
pub(super) struct Resolution {
    pub leaf: String,
    pub chain: Vec<String>,
    pub eligible: BTreeSet<String>,
    pub affinity_reason: &'static str,
}
struct Job {
    leaf: Node,
    transport: Option<Transport>,
    probe: Probe,
    profile: String,
    next: tokio::time::Instant,
    active: bool,
}

struct ActiveHealthProbe(Arc<AtomicUsize>);

impl ActiveHealthProbe {
    fn new(in_flight: &Arc<AtomicUsize>) -> Self {
        in_flight.fetch_add(1, Ordering::AcqRel);
        Self(in_flight.clone())
    }
}

impl Drop for ActiveHealthProbe {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

pub(super) struct PolicyRuntime {
    document: Arc<PolicyDocument>,
    profiles: BTreeMap<String, String>,
    registry: Arc<Mutex<Registry>>,
    worker: Mutex<Option<JoinHandle<()>>>,
    in_flight: Arc<AtomicUsize>,
    jobs: Mutex<Option<Vec<Job>>>,
    resolver: Arc<Resolver>,
    runtime: Handle,
    paused: Arc<AtomicBool>,
    resumed: Arc<Notify>,
    stop: watch::Sender<bool>,
    node_digests: BTreeMap<String, String>,
}
fn profile(probe: &Probe) -> Result<String> {
    let bytes = serde_json::to_vec(probe).map_err(|_| "PolicyProbeProfile")?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}
impl PolicyRuntime {
    /// Creates no tasks and performs no DNS, sockets or probes.
    pub fn dormant(
        runtime: Handle,
        document: Arc<PolicyDocument>,
        nodes: &[Node],
        resolver: Arc<Resolver>,
        transports: &BTreeMap<String, Transport>,
    ) -> Result<Self> {
        let mut profiles = BTreeMap::new();
        let mut jobs = BTreeMap::new();
        for group in document
            .groups
            .iter()
            .filter(|g| g.strategy != PolicyStrategy::Manual)
        {
            let probe = group.probe.as_ref().ok_or("PolicyProbeRequired")?;
            let digest = profile(probe)?;
            profiles.insert(group.id.clone(), digest.clone());
            for id in document.reachable_nodes(&Target::Group {
                id: group.id.clone(),
            })? {
                let Some(node) = nodes.iter().find(|n| n.id == id) else {
                    continue;
                };
                jobs.entry((digest.clone(), id)).or_insert_with(|| Job {
                    leaf: node.clone(),
                    transport: transports.get(&node.id).cloned(),
                    probe: probe.clone(),
                    profile: digest.clone(),
                    next: tokio::time::Instant::now(),
                    active: false,
                });
            }
        }
        if jobs.len() > 512 {
            return Err("PolicyProbeBudget");
        }
        let node_digests = nodes
            .iter()
            .map(|node| {
                let bytes = serde_json::to_vec(&(node, transports.get(&node.id)))
                    .map_err(|_| "PolicyNodeDigest")?;
                Ok((node.id.clone(), format!("{:x}", Sha256::digest(bytes))))
            })
            .collect::<Result<_>>()?;
        Ok(Self {
            document,
            profiles,
            registry: Arc::new(Mutex::new(Registry::default())),
            worker: Mutex::new(None),
            in_flight: Arc::new(AtomicUsize::new(0)),
            jobs: Mutex::new(Some(jobs.into_values().collect())),
            resolver,
            runtime,
            paused: Arc::new(AtomicBool::new(false)),
            resumed: Arc::new(Notify::new()),
            stop: watch::channel(false).0,
            node_digests,
        })
    }
    pub fn inherit_unchanged(&self, old: &Self, same_dns: bool) -> Result<()> {
        if !same_dns {
            return Ok(());
        }
        let mut jobs = self.jobs.lock().map_err(|_| "PolicyState")?;
        let Some(jobs) = jobs.as_mut() else {
            return Err("PolicyAlreadyStarted");
        };
        let keys: BTreeSet<_> = jobs
            .iter()
            .map(|job| (job.profile.clone(), job.leaf.id.clone()))
            .collect();
        let old_state = old.registry.lock().map_err(|_| "PolicyState")?;
        let mut state = self.registry.lock().map_err(|_| "PolicyState")?;
        for (key, health) in &old_state.health {
            if keys.contains(key) && self.node_digests.get(&key.1) == old.node_digests.get(&key.1) {
                state.health.insert(key.clone(), health.clone());
            }
        }
        for job in jobs {
            if let Some(health) = state
                .health
                .get(&(job.profile.clone(), job.leaf.id.clone()))
            {
                job.next = tokio::time::Instant::now()
                    + Duration::from_millis(job.probe.interval_ms)
                        .saturating_sub(health.checked.elapsed());
            }
        }
        state.epoch = old_state.epoch;
        state.pins = old_state
            .pins
            .iter()
            .filter(|(key, _)| {
                key.split('/')
                    .nth(2)
                    .is_some_and(|id| self.document.group(id).is_some())
            })
            .map(|(key, pin)| (key.clone(), pin.clone()))
            .collect();
        Ok(())
    }
    pub fn start(&self) -> Result<()> {
        let mut worker = self.worker.lock().map_err(|_| "PolicyState")?;
        if worker.is_some() {
            return Ok(());
        }
        let jobs = self
            .jobs
            .lock()
            .map_err(|_| "PolicyState")?
            .take()
            .unwrap_or_default();
        if !jobs.is_empty() {
            *worker = Some(self.runtime.spawn(run(
                jobs,
                self.resolver.clone(),
                self.registry.clone(),
                self.paused.clone(),
                self.resumed.clone(),
                self.stop.subscribe(),
                self.in_flight.clone(),
            )))
        }
        Ok(())
    }
    /// Native TUN acquisition must exclude sockets from automatic health jobs,
    /// which are separate from ordinary admissions and the manual probe task.
    pub fn quiescent(&self) -> bool {
        self.in_flight.load(Ordering::Acquire) == 0
    }
    pub fn pause(&self, paused: bool) {
        self.paused.store(paused, Ordering::Release);
        if !paused {
            self.resumed.notify_one();
        }
    }
    pub fn stop(&self) {
        let _ = self.stop.send(true);
        if let Ok(mut worker) = self.worker.lock()
            && let Some(task) = worker.take()
        {
            task.abort();
        }
        if let Ok(mut jobs) = self.jobs.lock() {
            jobs.take();
        }
    }
    pub async fn stop_and_wait(&self) -> Result<()> {
        let _ = self.stop.send(true);
        let task = self.worker.lock().map_err(|_| "PolicyState")?.take();
        if let Some(mut task) = task
            && timeout(Duration::from_secs(2), &mut task).await.is_err()
        {
            task.abort();
            let _ = task.await;
            return Err("PolicyShutdownTimeout");
        }
        self.jobs.lock().map_err(|_| "PolicyState")?.take();
        Ok(())
    }
    pub fn resolve(&self, target: &Target, entry: &str, service: &str) -> Result<Resolution> {
        let mut state = self.registry.lock().map_err(|_| "PolicyState")?;
        let now = Instant::now();
        state
            .pins
            .retain(|_, pin| now.duration_since(pin.touched) < Duration::from_secs(1800));
        let mut budget = 16384;
        let mut memo = BTreeMap::new();
        self.resolve_inner(
            target,
            entry,
            service,
            None,
            &mut state,
            &mut budget,
            &mut memo,
            0,
        )
    }
    #[allow(clippy::too_many_arguments)]
    fn resolve_inner(
        &self,
        target: &Target,
        entry: &str,
        service: &str,
        allowed: Option<&BTreeSet<String>>,
        state: &mut Registry,
        budget: &mut usize,
        memo: &mut BTreeMap<String, Resolution>,
        depth: usize,
    ) -> Result<Resolution> {
        *budget = budget.checked_sub(1).ok_or("PolicyResolutionBudget")?;
        if depth > 16 {
            return Err("PolicyDepth");
        }
        if self.document.missing(target) {
            return Err("MissingTarget");
        }
        let leaf = match target {
            Target::Node { id } => Some(id.clone()),
            Target::Direct {} => Some(DIRECT_NODE_ID.into()),
            Target::Reject {} => Some(REJECT_NODE_ID.into()),
            Target::Unconfigured {} => return Err("DefaultUnconfigured"),
            Target::Group { .. } => None,
        };
        if let Some(leaf) = leaf {
            if allowed.is_some_and(|set| !set.contains(&leaf)) {
                return Err("PolicyUnavailable");
            };
            return Ok(Resolution {
                eligible: BTreeSet::from([leaf.clone()]),
                leaf,
                chain: Vec::new(),
                affinity_reason: "fixed",
            });
        }
        let Target::Group { id } = target else {
            return Err("PolicyTarget");
        };
        let group = self.document.group(id).ok_or("MissingTarget")?;
        let allowed_digest = allowed
            .map(|set| {
                let mut h = Sha256::new();
                for id in set {
                    h.update(id.as_bytes());
                    h.update([0]);
                }
                format!("{:x}", h.finalize())
            })
            .unwrap_or_default();
        let key = format!("{entry}/{service}/{id}/{allowed_digest}");
        if let Some(value) = memo.get(&key) {
            return Ok(value.clone());
        }
        if group.strategy == PolicyStrategy::Manual {
            let selected = group.selected.as_ref().ok_or("PolicyUnavailable")?;
            let mut result = self.resolve_inner(
                selected,
                entry,
                service,
                allowed,
                state,
                budget,
                memo,
                depth + 1,
            )?;
            result.chain.insert(0, id.clone());
            memo.insert(key, result.clone());
            return Ok(result);
        }
        let probe = group.probe.as_ref().ok_or("PolicyProbeRequired")?;
        let profile = self.profiles.get(id).ok_or("PolicyState")?;
        let healthy: BTreeSet<_> = state
            .health
            .iter()
            .filter(|((p, leaf), h)| {
                p == profile
                    && h.eligible
                    && h.checked.elapsed()
                        <= Duration::from_millis(
                            probe
                                .interval_ms
                                .saturating_mul(2)
                                .saturating_add(probe.timeout_ms),
                        )
                    && allowed.is_none_or(|set| set.contains(leaf))
            })
            .map(|((_, leaf), _)| leaf.clone())
            .collect();
        let mut candidates = Vec::new();
        let mut eligible = BTreeSet::new();
        for member in &group.members {
            match self.resolve_inner(
                member,
                entry,
                service,
                Some(&healthy),
                state,
                budget,
                memo,
                depth + 1,
            ) {
                Ok(result) => {
                    eligible.extend(result.eligible.iter().cloned());
                    let latency = result
                        .eligible
                        .iter()
                        .filter_map(|leaf| {
                            state
                                .health
                                .get(&(profile.clone(), leaf.clone()))
                                .and_then(|h| h.latency)
                        })
                        .max()
                        .ok_or("PolicyUnavailable")?;
                    candidates.push((member.clone(), result, latency));
                }
                Err("PolicyUnavailable" | "MissingTarget" | "DefaultUnconfigured") => {}
                Err(error) => return Err(error),
            }
        }
        if candidates.is_empty() {
            return Err("PolicyUnavailable");
        }
        let previous = state.pins.get(&key).cloned();
        let index = match group.strategy {
            PolicyStrategy::Fallback => 0,
            PolicyStrategy::UrlTest => candidates
                .iter()
                .enumerate()
                .min_by_key(|(_, (_, _, latency))| *latency)
                .map_or(0, |(index, _)| index),
            PolicyStrategy::LoadBalance => candidates
                .iter()
                .enumerate()
                .max_by_key(|(_, (member, _, _))| {
                    let mut h = Sha256::new();
                    h.update(entry);
                    h.update([0]);
                    h.update(service);
                    h.update([0]);
                    h.update(id);
                    h.update([0]);
                    h.update(serde_json::to_vec(member).unwrap_or_default());
                    <[u8; 32]>::from(h.finalize())
                })
                .map_or(0, |(index, _)| index),
            PolicyStrategy::Manual => return Err("PolicyState"),
        };
        let mut index = index;
        let mut reason = "rendezvous";
        if let Some(old) = &previous {
            if let Some(current) = candidates.iter().position(|(branch, result, _)| {
                branch == &old.branch
                    && result.eligible.contains(&old.leaf)
                    && result.leaf == old.leaf
            }) {
                if group.strategy == PolicyStrategy::LoadBalance
                    || old.switched.elapsed() < Duration::from_millis(probe.switch_cooldown_ms)
                    || (group.strategy == PolicyStrategy::UrlTest
                        && candidates[current].2
                            <= candidates[index].2.saturating_add(probe.tolerance_ms))
                {
                    index = current;
                    reason = "healthy_pin";
                } else {
                    reason = "policy_switch";
                }
            } else {
                reason = "invalidated_pin";
            }
        }
        let (branch, mut result, _) = candidates.swap_remove(index);
        let switched = previous
            .as_ref()
            .filter(|old| old.branch == branch && old.leaf == result.leaf)
            .map_or_else(Instant::now, |old| old.switched);
        if state.pins.len() >= 8192
            && !state.pins.contains_key(&key)
            && let Some(oldest) = state
                .pins
                .iter()
                .min_by_key(|(_, pin)| pin.touched)
                .map(|(k, _)| k.clone())
        {
            state.pins.remove(&oldest);
        }
        state.pins.insert(
            key.clone(),
            Pin {
                branch,
                leaf: result.leaf.clone(),
                touched: Instant::now(),
                switched,
            },
        );
        result.chain.insert(0, id.clone());
        result.eligible = eligible;
        result.affinity_reason = reason;
        memo.insert(key, result.clone());
        Ok(result)
    }
    pub fn report(&self) -> Result<BTreeMap<String, serde_json::Value>> {
        let state = self.registry.lock().map_err(|_| "PolicyState")?;
        let mut result = BTreeMap::new();
        let mut detail_budget = 512usize;
        for group in &self.document.groups {
            let profile = self.profiles.get(&group.id);
            let mut members = Vec::new();
            if let Some(profile) = profile {
                for leaf in self.document.reachable_nodes(&Target::Group {
                    id: group.id.clone(),
                })? {
                    if detail_budget == 0 {
                        break;
                    }
                    detail_budget -= 1;
                    let h = state.health.get(&(profile.clone(), leaf.clone()));
                    let expiry = group.probe.as_ref().map_or(0, |p| {
                        p.interval_ms.saturating_mul(2).saturating_add(p.timeout_ms)
                    });
                    members.push(serde_json::json!({"node":leaf,"healthy":h.is_some_and(|h|h.eligible&&h.checked.elapsed()<=Duration::from_millis(expiry)),"latency_ms":h.and_then(|h|h.latency),"checked_age_ms":h.map(|h|h.checked.elapsed().as_millis().min(u128::from(u64::MAX))as u64),"error":h.map_or("PolicyNotChecked",|h|h.error)}));
                }
            }
            let total = if profile.is_some() {
                self.document
                    .reachable_nodes(&Target::Group {
                        id: group.id.clone(),
                    })?
                    .len()
            } else {
                0
            };
            result.insert(group.id.clone(),serde_json::json!({"strategy":group.strategy,"selected":group.selected.as_ref().and_then(Target::id),"context_dependent":group.strategy!=PolicyStrategy::Manual,"health_epoch":state.epoch.to_string(),"members_total":total,"members_truncated":members.len()<total,"members":members}));
        }
        Ok(result)
    }
}
impl Drop for PolicyRuntime {
    fn drop(&mut self) {
        self.stop();
    }
}

async fn run(
    mut jobs: Vec<Job>,
    resolver: Arc<Resolver>,
    registry: Arc<Mutex<Registry>>,
    paused: Arc<AtomicBool>,
    resumed: Arc<Notify>,
    mut stopped: watch::Receiver<bool>,
    in_flight: Arc<AtomicUsize>,
) {
    let permits = Arc::new(Semaphore::new(4));
    let mut active = JoinSet::new();
    loop {
        if paused.load(Ordering::Acquire) {
            tokio::select! {biased;_=stopped.changed()=>break,_=resumed.notified()=>{}}
            continue;
        }
        let now = tokio::time::Instant::now();
        for (index, job) in jobs.iter_mut().enumerate() {
            if !job.active && job.next <= now {
                let Ok(permit) = permits.clone().try_acquire_owned() else {
                    break;
                };
                job.active = true;
                let node = job.leaf.clone();
                let options = job.probe.legacy();
                let transport = job.transport.clone();
                let resolver = resolver.clone();
                // Register before spawn, hence before any DNS/socket IO. The
                // guard is also dropped if cancellation precedes the first poll.
                let probe = ActiveHealthProbe::new(&in_flight);
                active.spawn(async move {
                    let _probe = probe;
                    let _permit = permit;
                    let result = if let Some(transport) = transport {
                        swirl_protocol::health_probe_with_transport(
                            &node.outbound,
                            &options,
                            &resolver,
                            &transport,
                        )
                        .await
                    } else {
                        swirl_protocol::health_probe(&node.outbound, &options, &resolver).await
                    };
                    (index, result)
                });
            }
        }
        let next = jobs
            .iter()
            .filter(|j| !j.active)
            .map(|j| j.next)
            .min()
            .unwrap_or_else(|| now + Duration::from_secs(3600));
        tokio::select! {
            biased;
            _=stopped.changed()=>break,
            Some(result)=active.join_next(),if !active.is_empty()=>{
                let Ok((index,result))=result else{continue};let job=&mut jobs[index];job.active=false;job.next=tokio::time::Instant::now()+Duration::from_millis(job.probe.interval_ms);
                if let Ok(mut state)=registry.lock(){let h=state.health.entry((job.profile.clone(),job.leaf.id.clone())).or_insert_with(||Health{latency:None,checked:Instant::now(),successes:0,failures:0,eligible:false,error:"PolicyNotChecked"});h.checked=Instant::now();match result{Ok(latency)=>{h.successes=h.successes.saturating_add(1);h.failures=0;h.latency=Some(latency);h.error="";if h.successes>=job.probe.success_threshold{h.eligible=true;}},Err(code)=>{h.failures=h.failures.saturating_add(1);h.successes=0;h.error=code;if h.failures>=job.probe.failure_threshold{h.eligible=false;}}}state.epoch=state.epoch.saturating_add(1);}
            },
            _=sleep_until(next),if active.len()<4&&jobs.iter().any(|j|!j.active)=>{}
        }
    }
    active.abort_all();
    while active.join_next().await.is_some() {}
}

#[cfg(test)]
#[path = "policy_v2_tests.rs"]
mod tests;
