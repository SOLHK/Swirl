//! Bounded active probes and per-session policy snapshots. Automatic decisions
//! affect only new TCP/UDP associations. A failed application connection is
//! never retried through another member. Every configuration owns its worker.
use serde::Serialize;
use std::{collections::{BTreeMap, HashMap, VecDeque}, sync::{Arc, Mutex, atomic::{AtomicU64, Ordering}}, time::{Duration, Instant}};
use swirl_dns::Resolver;
use swirl_subscription::{Config, PolicyStrategy, Selector};
use tokio::{runtime::Handle, sync::Semaphore, task::{JoinHandle, JoinSet}, time::{sleep_until, timeout}};

type Result<T> = std::result::Result<T, &'static str>;
#[derive(Clone)]
struct Health { latency: Option<u64>, checked: Instant, error: &'static str }
struct Group {
    health: HashMap<String, Health>,
    selected: Option<String>,
    cursor: Arc<AtomicU64>,
    checks: u64,
}
#[derive(Serialize)]
pub struct MemberHealth {
    pub node: String,
    pub healthy: bool,
    pub latency_ms: Option<u64>,
    pub checked_age_ms: Option<u64>,
    pub error: &'static str,
}
#[derive(Serialize)]
pub struct PolicyReport {
    pub strategy: PolicyStrategy,
    pub selected: Option<String>,
    pub checks: u64,
    pub members: Vec<MemberHealth>,
}
struct Choice {members: Vec<String>, preferred: Option<String>, cursor: Arc<AtomicU64>, strategy: PolicyStrategy}
pub(super) struct PolicyView {
    groups: HashMap<String, Choice>,
    pinned: Mutex<HashMap<String, String>>,
}
impl PolicyView {
    pub fn choose(&self, id: &str) -> Result<String> {
        let mut pinned = self.pinned.lock().map_err(|_| "PolicyState")?;
        if let Some(node) = pinned.get(id) {return Ok(node.clone());}
        let group = self.groups.get(id).ok_or("PolicyMissing")?;
        let node = if group.strategy == PolicyStrategy::LoadBalance {
            if group.members.is_empty() {return Err("NoHealthyPolicyMember");}
            // Advance only when this policy actually routes a session, never
            // during health polling, unrelated traffic or snapshot reporting.
            let index = group.cursor.fetch_add(1, Ordering::Relaxed) % group.members.len() as u64;
            group.members[index as usize].clone()
        } else {group.preferred.clone().ok_or("NoHealthyPolicyMember")?};
        pinned.insert(id.to_owned(), node.clone());
        Ok(node)
    }
}
fn fresh(group: &Selector, health: &Health) -> bool {
    group.probe.as_ref().is_some_and(|p| health.checked.elapsed()
        <= Duration::from_millis(p.interval_ms.saturating_mul(2).saturating_add(p.timeout_ms)))
        && health.latency.is_some()
}
fn healthy_members(group: &Selector, state: &Group) -> Vec<String> {
    group.members.iter().filter(|id| state.health.get(id.as_str()).is_some_and(|h| fresh(group,h))).cloned().collect()
}
fn preferred(group: &Selector, state: &Group, healthy: &[String]) -> Option<String> {
    match group.strategy {
        PolicyStrategy::Manual => Some(group.selected.clone()),
        PolicyStrategy::Fallback => healthy.first().cloned(),
        PolicyStrategy::LoadBalance => state.selected.as_ref().filter(|id| healthy.contains(id)).cloned().or_else(|| healthy.first().cloned()),
        PolicyStrategy::UrlTest => {
            let best = healthy.iter().min_by_key(|id| state.health.get(id.as_str()).and_then(|h| h.latency).unwrap_or(u64::MAX))?;
            let fastest = state.health.get(best.as_str())?.latency?;
            let tolerance = group.probe.as_ref()?.tolerance_ms;
            if let Some(previous) = state.selected.as_ref().filter(|id| healthy.contains(id))
                && state.health.get(previous.as_str()).and_then(|h| h.latency).is_some_and(|age| age <= fastest.saturating_add(tolerance)) {
                return Some(previous.clone());
            }
            Some(best.clone())
        }
    }
}
pub(super) struct PolicyRuntime {
    registry: Arc<Mutex<HashMap<String, Group>>>,
    budget: Arc<Semaphore>,
    runtime: Handle,
    worker: Option<JoinHandle<()>>,
}
impl PolicyRuntime {
    pub fn new(runtime: Handle, config: Arc<Config>, resolver: Arc<Resolver>) -> Self {
        Self::with_budget(runtime, Arc::new(Semaphore::new(4)), config, resolver)
    }
    fn with_budget(runtime: Handle, budget: Arc<Semaphore>, config: Arc<Config>, resolver: Arc<Resolver>) -> Self {
        let registry: HashMap<_,_> = config.selectors.iter().filter(|g| g.strategy != PolicyStrategy::Manual)
            .map(|g|(g.id.clone(), Group {health: HashMap::new(), selected: None, cursor: Arc::new(AtomicU64::new(0)), checks: 0})).collect();
        let automatic = !registry.is_empty();
        let registry = Arc::new(Mutex::new(registry));
        let worker = if automatic {
            Some(runtime.spawn(run(config, resolver, registry.clone(), budget.clone())))
        } else {None};
        Self {registry, budget, runtime, worker}
    }
    pub fn reconfigured(&self, config: Arc<Config>, resolver: Arc<Resolver>) -> Self {
        Self::with_budget(self.runtime.clone(), self.budget.clone(), config, resolver)
    }
    pub fn stop(&self) {if let Some(worker) = &self.worker {worker.abort();}}
    pub fn view(&self, config: &Config) -> Result<PolicyView> {
        let registry = self.registry.lock().map_err(|_| "PolicyState")?;
        let mut groups = HashMap::new();
        for group in config.selectors.iter().filter(|g| g.strategy != PolicyStrategy::Manual) {
            let state = registry.get(&group.id).ok_or("PolicyState")?;
            let members = healthy_members(group, state);
            let chosen = preferred(group, state, &members);
            groups.insert(group.id.clone(), Choice {members, preferred: chosen, cursor: state.cursor.clone(), strategy: group.strategy});
        }
        Ok(PolicyView {groups, pinned: Mutex::new(HashMap::new())})
    }
    pub fn report(&self, config: &Config) -> Result<BTreeMap<String, PolicyReport>> {
        let registry = self.registry.lock().map_err(|_| "PolicyState")?;
        let mut result = BTreeMap::new();
        for group in &config.selectors {
            if group.strategy == PolicyStrategy::Manual {
                result.insert(group.id.clone(), PolicyReport {strategy: group.strategy, selected: Some(group.selected.clone()), checks: 0, members: Vec::new()});
                continue;
            }
            let state = registry.get(&group.id).ok_or("PolicyState")?;
            let healthy = healthy_members(group,state);
            let members = group.members.iter().map(|id| {
                let h = state.health.get(id);
                let usable = h.is_some_and(|h| fresh(group,h));
                MemberHealth {node: id.clone(), healthy: usable, latency_ms: h.and_then(|h| h.latency),
                    checked_age_ms: h.map(|h| h.checked.elapsed().as_millis().min(u128::from(u64::MAX)) as u64),
                    error: h.map_or("PolicyNotChecked", |h| if !usable && h.error.is_empty() {"PolicyHealthExpired"} else {h.error})}
            }).collect();
            result.insert(group.id.clone(), PolicyReport {strategy: group.strategy, selected: preferred(group,state,&healthy), checks: state.checks, members});
        }
        Ok(result)
    }
}
impl Drop for PolicyRuntime {fn drop(&mut self) {self.stop();}}
async fn run(config: Arc<Config>, resolver: Arc<Resolver>, registry: Arc<Mutex<HashMap<String,Group>>>, budget: Arc<Semaphore>) {
    let node_index: HashMap<_,_> = config.nodes.iter().enumerate().map(|(i,n)|(n.id.clone(),i)).collect();
    let mut next: Vec<_> = config.selectors.iter().map(|_| Instant::now()).collect();
    loop {
        let now = Instant::now();
        let mut jobs = VecDeque::new();
        for (index,group) in config.selectors.iter().enumerate().filter(|(_,g)|g.strategy != PolicyStrategy::Manual) {
            if next[index] > now {continue;}
            let Some(probe) = &group.probe else {return;};
            next[index] = now + Duration::from_millis(probe.interval_ms);
            for member in &group.members {
                let Some(node) = node_index.get(member) else {return;};
                jobs.push_back((index,*node));
            }
        }
        let mut running = JoinSet::new();
        while !jobs.is_empty() || !running.is_empty() {
            while running.len() < 4 {
                let Some((group_index,node_index)) = jobs.pop_front() else {break;};
                let config = config.clone();let resolver = resolver.clone();let budget = budget.clone();
                running.spawn(async move {
                    let group = &config.selectors[group_index];
                    let result = async {
                        let probe = group.probe.as_ref().ok_or("PolicyProbeRequired")?;
                        let _permit = timeout(Duration::from_millis(probe.timeout_ms), budget.acquire_owned()).await
                            .map_err(|_| "PolicyProbeBusy")?.map_err(|_| "PolicyProbeStopped")?;
                        swirl_protocol::health_probe(&config.nodes[node_index].outbound,probe,&resolver).await
                    }.await;
                    (group_index,node_index,result)
                });
            }
            let Some(Ok((group_index,node_index,result))) = running.join_next().await else {return;};
            let group = &config.selectors[group_index];
            let Ok(mut states) = registry.lock() else {return;};
            let Some(state) = states.get_mut(&group.id) else {return;};
            let (latency,error) = match result {Ok(ms)=>(Some(ms),""),Err(error)=>(None,error)};
            state.health.insert(config.nodes[node_index].id.clone(),Health {latency,checked:Instant::now(),error});
            state.checks = state.checks.saturating_add(1);
            state.selected = preferred(group,state,&healthy_members(group,state));
        }
        let wake = config.selectors.iter().enumerate().filter(|(_,g)|g.strategy != PolicyStrategy::Manual)
            .map(|(i,_)|next[i]).min().unwrap_or_else(Instant::now);
        sleep_until(wake.into()).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use swirl_subscription::HealthProbe;
    fn group(strategy: PolicyStrategy) -> Selector {
        Selector {id:"g".into(),members:vec!["a".into(),"b".into()],selected:String::new(),strategy,
            probe:Some(HealthProbe {url:"http://localhost/".into(),interval_ms:1000,timeout_ms:500,expected_status:204,tolerance_ms:20,tls:None})}
    }
    #[test]
    fn url_test_hysteresis_and_expiration_are_explicit() {
        let config = group(PolicyStrategy::UrlTest);
        let mut state = Group {health:HashMap::new(),selected:Some("a".into()),cursor:Arc::new(AtomicU64::new(0)),checks:0};
        for (id,latency) in [("a",100),("b",90)] {state.health.insert(id.into(),Health {latency:Some(latency),checked:Instant::now(),error:""});}
        assert_eq!(preferred(&config,&state,&healthy_members(&config,&state)),Some("a".into()));
        state.health.get_mut("b").unwrap().latency = Some(50);
        assert_eq!(preferred(&config,&state,&healthy_members(&config,&state)),Some("b".into()));
        for health in state.health.values_mut() {health.checked = Instant::now()-Duration::from_secs(5);}
        assert!(preferred(&config,&state,&healthy_members(&config,&state)).is_none());
    }
    #[test]
    fn round_robin_advances_only_once_per_used_policy_and_session() {
        let cursor = Arc::new(AtomicU64::new(0));
        for expected in ["a","b","a"] {
            let view = PolicyView {groups:HashMap::from([("g".into(),Choice {members:vec!["a".into(),"b".into()],preferred:None,cursor:cursor.clone(),strategy:PolicyStrategy::LoadBalance})]),pinned:Mutex::new(HashMap::new())};
            assert_eq!(view.choose("g").unwrap(),expected);
            assert_eq!(view.choose("g").unwrap(),expected);
        }
        assert_eq!(cursor.load(Ordering::Relaxed),3);
    }
}
