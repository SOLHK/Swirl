//! Bounded active probes and per-session policy snapshots. Automatic decisions
//! affect only new TCP/UDP associations. A failed application connection is
//! never retried through another member. Every configuration owns its worker.
use serde::Serialize;
use std::{
    collections::{BTreeMap, HashMap},
    sync::{
        Arc, Mutex,
        atomic::{AtomicU64, Ordering},
    },
    time::{Duration, Instant},
};
use swirl_dns::Resolver;
use swirl_subscription::{Config, PolicyStrategy, Selector};
use tokio::{
    runtime::Handle,
    sync::Semaphore,
    task::{JoinHandle, JoinSet},
    time::{sleep_until, timeout_at},
};

type Result<T> = std::result::Result<T, &'static str>;
#[derive(Clone)]
struct Health {
    latency: Option<u64>,
    checked: Instant,
    error: &'static str,
}
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
struct Choice {
    members: Vec<String>,
    preferred: Option<String>,
    cursor: Arc<AtomicU64>,
    strategy: PolicyStrategy,
}
pub(super) struct PolicyView {
    groups: HashMap<String, Choice>,
    pinned: Mutex<HashMap<String, String>>,
}
impl PolicyView {
    /// Read a choice already consumed by this session. Checking alternate
    /// DNS answers must not advance an unrelated load-balance group.
    pub fn pinned_choice(&self, id: &str) -> Result<String> {
        self.pinned
            .lock()
            .map_err(|_| "PolicyState")?
            .get(id)
            .cloned()
            .ok_or("PolicyNotPinned")
    }

    pub fn choose(&self, id: &str) -> Result<String> {
        let mut pinned = self.pinned.lock().map_err(|_| "PolicyState")?;
        if let Some(node) = pinned.get(id) {
            return Ok(node.clone());
        }
        let group = self.groups.get(id).ok_or("PolicyMissing")?;
        let node = if group.strategy == PolicyStrategy::LoadBalance {
            if group.members.is_empty() {
                return Err("NoHealthyPolicyMember");
            }
            // Advance only when this policy actually routes a session, never
            // during health polling, unrelated traffic or snapshot reporting.
            let index = group.cursor.fetch_add(1, Ordering::Relaxed) % group.members.len() as u64;
            group.members[index as usize].clone()
        } else {
            group.preferred.clone().ok_or("NoHealthyPolicyMember")?
        };
        pinned.insert(id.to_owned(), node.clone());
        Ok(node)
    }
}
fn fresh(group: &Selector, health: &Health) -> bool {
    group.probe.as_ref().is_some_and(|p| {
        health.checked.elapsed()
            <= Duration::from_millis(p.interval_ms.saturating_mul(2).saturating_add(p.timeout_ms))
    }) && health.latency.is_some()
}
fn healthy_members(group: &Selector, state: &Group) -> Vec<String> {
    group
        .members
        .iter()
        .filter(|id| {
            state
                .health
                .get(id.as_str())
                .is_some_and(|h| fresh(group, h))
        })
        .cloned()
        .collect()
}
fn preferred(group: &Selector, state: &Group, healthy: &[String]) -> Option<String> {
    match group.strategy {
        PolicyStrategy::Manual => Some(group.selected.clone()),
        PolicyStrategy::Fallback => healthy.first().cloned(),
        PolicyStrategy::LoadBalance => {
            if healthy.is_empty() {
                return None;
            }
            // Reporting previews the next choice without consuming a turn.
            healthy
                .get((state.cursor.load(Ordering::Relaxed) % healthy.len() as u64) as usize)
                .cloned()
        }
        PolicyStrategy::UrlTest => {
            let best = healthy.iter().min_by_key(|id| {
                state
                    .health
                    .get(id.as_str())
                    .and_then(|h| h.latency)
                    .unwrap_or(u64::MAX)
            })?;
            let fastest = state.health.get(best.as_str())?.latency?;
            let tolerance = group.probe.as_ref()?.tolerance_ms;
            if let Some(previous) = state.selected.as_ref().filter(|id| healthy.contains(id))
                && state
                    .health
                    .get(previous.as_str())
                    .and_then(|h| h.latency)
                    .is_some_and(|age| age <= fastest.saturating_add(tolerance))
            {
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
    fn with_budget(
        runtime: Handle,
        budget: Arc<Semaphore>,
        config: Arc<Config>,
        resolver: Arc<Resolver>,
    ) -> Self {
        let registry: HashMap<_, _> = config
            .selectors
            .iter()
            .filter(|g| g.strategy != PolicyStrategy::Manual)
            .map(|g| {
                (
                    g.id.clone(),
                    Group {
                        health: HashMap::new(),
                        selected: None,
                        cursor: Arc::new(AtomicU64::new(0)),
                        checks: 0,
                    },
                )
            })
            .collect();
        let automatic = !registry.is_empty();
        let registry = Arc::new(Mutex::new(registry));
        let worker = if automatic {
            Some(runtime.spawn(run(config, resolver, registry.clone(), budget.clone())))
        } else {
            None
        };
        Self {
            registry,
            budget,
            runtime,
            worker,
        }
    }
    pub fn reconfigured(&self, config: Arc<Config>, resolver: Arc<Resolver>) -> Self {
        Self::with_budget(self.runtime.clone(), self.budget.clone(), config, resolver)
    }
    pub fn stop(&self) {
        if let Some(worker) = &self.worker {
            worker.abort();
        }
    }
    pub fn view(&self, config: &Config) -> Result<PolicyView> {
        let registry = self.registry.lock().map_err(|_| "PolicyState")?;
        let mut groups = HashMap::new();
        for group in config
            .selectors
            .iter()
            .filter(|g| g.strategy != PolicyStrategy::Manual)
        {
            let state = registry.get(&group.id).ok_or("PolicyState")?;
            let members = healthy_members(group, state);
            let chosen = preferred(group, state, &members);
            groups.insert(
                group.id.clone(),
                Choice {
                    members,
                    preferred: chosen,
                    cursor: state.cursor.clone(),
                    strategy: group.strategy,
                },
            );
        }
        Ok(PolicyView {
            groups,
            pinned: Mutex::new(HashMap::new()),
        })
    }
    pub fn report(&self, config: &Config) -> Result<BTreeMap<String, PolicyReport>> {
        let registry = self.registry.lock().map_err(|_| "PolicyState")?;
        let mut result = BTreeMap::new();
        for group in &config.selectors {
            if group.strategy == PolicyStrategy::Manual {
                result.insert(
                    group.id.clone(),
                    PolicyReport {
                        strategy: group.strategy,
                        selected: Some(group.selected.clone()),
                        checks: 0,
                        members: Vec::new(),
                    },
                );
                continue;
            }
            let state = registry.get(&group.id).ok_or("PolicyState")?;
            let healthy = healthy_members(group, state);
            let members = group
                .members
                .iter()
                .map(|id| {
                    let h = state.health.get(id);
                    let usable = h.is_some_and(|h| fresh(group, h));
                    MemberHealth {
                        node: id.clone(),
                        healthy: usable,
                        latency_ms: h.and_then(|h| h.latency),
                        checked_age_ms: h.map(|h| {
                            h.checked.elapsed().as_millis().min(u128::from(u64::MAX)) as u64
                        }),
                        error: h.map_or("PolicyNotChecked", |h| {
                            if !usable && h.error.is_empty() {
                                "PolicyHealthExpired"
                            } else {
                                h.error
                            }
                        }),
                    }
                })
                .collect();
            result.insert(
                group.id.clone(),
                PolicyReport {
                    strategy: group.strategy,
                    selected: preferred(group, state, &healthy),
                    checks: state.checks,
                    members,
                },
            );
        }
        Ok(result)
    }
}
impl Drop for PolicyRuntime {
    fn drop(&mut self) {
        self.stop();
    }
}
struct ProbeJob {
    group: usize,
    node: usize,
    next: Instant,
    active: bool,
}
fn due_job(jobs: &[ProbeJob], now: Instant) -> Option<usize> {
    jobs.iter()
        .enumerate()
        .filter(|(_, job)| !job.active && job.next <= now)
        .min_by_key(|(_, job)| job.next)
        .map(|(index, _)| index)
}
async fn run(
    config: Arc<Config>,
    resolver: Arc<Resolver>,
    registry: Arc<Mutex<HashMap<String, Group>>>,
    budget: Arc<Semaphore>,
) {
    let node_index: HashMap<_, _> = config
        .nodes
        .iter()
        .enumerate()
        .map(|(i, n)| (n.id.as_str(), i))
        .collect();
    let mut jobs = Vec::new();
    let now = Instant::now();
    // Interleave groups at equal deadlines. A large first group cannot keep a
    // later group's first member behind every member in the first group.
    for member_index in 0..64 {
        for (group_index, group) in config
            .selectors
            .iter()
            .enumerate()
            .filter(|(_, g)| g.strategy != PolicyStrategy::Manual)
        {
            let Some(member) = group.members.get(member_index) else {
                continue;
            };
            let Some(node) = node_index.get(member.as_str()) else {
                return;
            };
            jobs.push(ProbeJob {
                group: group_index,
                node: *node,
                next: now,
                active: false,
            });
        }
    }
    if jobs.is_empty() {
        return;
    }
    let mut running = JoinSet::new();
    loop {
        while running.len() < 4 {
            let Some(index) = due_job(&jobs, Instant::now()) else {
                break;
            };
            let job = &mut jobs[index];
            job.active = true;
            let group_index = job.group;
            let node_index = job.node;
            let config = config.clone();
            let resolver = resolver.clone();
            let budget = budget.clone();
            running.spawn(async move {
                let result = async {
                    let probe = config.selectors[group_index]
                        .probe
                        .as_ref()
                        .ok_or("PolicyProbeRequired")?;
                    // Admission and all protocol/DNS/TLS/request work consume
                    // one deadline, including overlap while an old generation
                    // is being cancelled. They never receive separate budgets.
                    let deadline =
                        tokio::time::Instant::now() + Duration::from_millis(probe.timeout_ms);
                    let _permit = timeout_at(deadline, budget.acquire_owned())
                        .await
                        .map_err(|_| "PolicyProbeBusy")?
                        .map_err(|_| "PolicyProbeStopped")?;
                    timeout_at(
                        deadline,
                        swirl_protocol::health_probe(
                            &config.nodes[node_index].outbound,
                            probe,
                            &resolver,
                        ),
                    )
                    .await
                    .map_err(|_| "PolicyProbeTimeout")?
                }
                .await;
                (index, result)
            });
        }
        let wake = jobs
            .iter()
            .filter(|job| !job.active)
            .map(|job| job.next)
            .min();
        let completed = tokio::select! {
            result = running.join_next(), if !running.is_empty() => result,
            _ = async {if let Some(wake) = wake {sleep_until(wake.into()).await;}}, if running.len() < 4 && wake.is_some() => continue,
            else => return,
        };
        let Some(Ok((index, result))) = completed else {
            return;
        };
        let job = &mut jobs[index];
        let group = &config.selectors[job.group];
        let Some(probe) = &group.probe else {
            return;
        };
        job.active = false;
        // Each member's interval starts after its completed check. We skip
        // missed rounds instead of building an ever-growing catch-up queue.
        job.next = Instant::now() + Duration::from_millis(probe.interval_ms);
        let Ok(mut states) = registry.lock() else {
            return;
        };
        let Some(state) = states.get_mut(&group.id) else {
            return;
        };
        let (latency, error) = match result {
            Ok(ms) => (Some(ms), ""),
            Err(error) => (None, error),
        };
        state.health.insert(
            config.nodes[job.node].id.clone(),
            Health {
                latency,
                checked: Instant::now(),
                error,
            },
        );
        state.checks = state.checks.saturating_add(1);
        state.selected = preferred(group, state, &healthy_members(group, state));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use swirl_subscription::HealthProbe;
    fn group(strategy: PolicyStrategy) -> Selector {
        Selector {
            id: "g".into(),
            members: vec!["a".into(), "b".into()],
            selected: String::new(),
            strategy,
            probe: Some(HealthProbe {
                url: "http://localhost/".into(),
                interval_ms: 1000,
                timeout_ms: 500,
                expected_status: 204,
                tolerance_ms: if strategy == PolicyStrategy::UrlTest {
                    20
                } else {
                    0
                },
                tls: None,
            }),
        }
    }
    #[test]
    fn url_test_hysteresis_and_expiration_are_explicit() {
        let config = group(PolicyStrategy::UrlTest);
        let mut state = Group {
            health: HashMap::new(),
            selected: Some("a".into()),
            cursor: Arc::new(AtomicU64::new(0)),
            checks: 0,
        };
        for (id, latency) in [("a", 100), ("b", 90)] {
            state.health.insert(
                id.into(),
                Health {
                    latency: Some(latency),
                    checked: Instant::now(),
                    error: "",
                },
            );
        }
        assert_eq!(
            preferred(&config, &state, &healthy_members(&config, &state)),
            Some("a".into())
        );
        state.health.get_mut("b").unwrap().latency = Some(50);
        assert_eq!(
            preferred(&config, &state, &healthy_members(&config, &state)),
            Some("b".into())
        );
        for health in state.health.values_mut() {
            health.checked = Instant::now() - Duration::from_secs(5);
        }
        assert!(preferred(&config, &state, &healthy_members(&config, &state)).is_none());
    }
    #[test]
    fn round_robin_advances_only_once_per_used_policy_and_session() {
        let cursor = Arc::new(AtomicU64::new(0));
        for expected in ["a", "b", "a"] {
            let view = PolicyView {
                groups: HashMap::from([(
                    "g".into(),
                    Choice {
                        members: vec!["a".into(), "b".into()],
                        preferred: None,
                        cursor: cursor.clone(),
                        strategy: PolicyStrategy::LoadBalance,
                    },
                )]),
                pinned: Mutex::new(HashMap::new()),
            };
            assert_eq!(view.choose("g").unwrap(), expected);
            assert_eq!(view.choose("g").unwrap(), expected);
        }
        assert_eq!(cursor.load(Ordering::Relaxed), 3);
    }

    #[test]
    fn alternate_address_check_reads_only_the_already_pinned_policy() {
        let used_cursor = Arc::new(AtomicU64::new(0));
        let unused_cursor = Arc::new(AtomicU64::new(0));
        let view = PolicyView {
            groups: HashMap::from([
                (
                    "used".into(),
                    Choice {
                        members: vec!["direct".into(), "other".into()],
                        preferred: None,
                        cursor: used_cursor.clone(),
                        strategy: PolicyStrategy::LoadBalance,
                    },
                ),
                (
                    "unused".into(),
                    Choice {
                        members: vec!["direct".into(), "other".into()],
                        preferred: None,
                        cursor: unused_cursor.clone(),
                        strategy: PolicyStrategy::LoadBalance,
                    },
                ),
            ]),
            pinned: Mutex::new(HashMap::new()),
        };
        assert_eq!(view.choose("used"), Ok("direct".into()));
        assert_eq!(view.pinned_choice("used"), Ok("direct".into()));
        assert_eq!(view.pinned_choice("unused"), Err("PolicyNotPinned"));
        assert_eq!(used_cursor.load(Ordering::Relaxed), 1);
        assert_eq!(unused_cursor.load(Ordering::Relaxed), 0);
    }

    #[test]
    fn fallback_keeps_member_priority_and_fails_closed_when_health_expires() {
        let config = group(PolicyStrategy::Fallback);
        let mut state = Group {
            health: HashMap::from([
                (
                    "a".into(),
                    Health {
                        latency: Some(200),
                        checked: Instant::now(),
                        error: "",
                    },
                ),
                (
                    "b".into(),
                    Health {
                        latency: Some(1),
                        checked: Instant::now(),
                        error: "",
                    },
                ),
            ]),
            selected: Some("b".into()),
            cursor: Arc::new(AtomicU64::new(0)),
            checks: 2,
        };
        assert_eq!(
            preferred(&config, &state, &healthy_members(&config, &state)),
            Some("a".into())
        );
        state.health.get_mut("a").unwrap().latency = None;
        assert_eq!(
            preferred(&config, &state, &healthy_members(&config, &state)),
            Some("b".into())
        );
        state.health.get_mut("b").unwrap().checked = Instant::now() - Duration::from_secs(5);
        assert!(preferred(&config, &state, &healthy_members(&config, &state)).is_none());
    }

    #[test]
    fn accepted_policy_views_do_not_change_when_live_health_changes() {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .build()
            .unwrap();
        let mut config = Config::parse(br#"{"schema":1,"listen":"127.0.0.1:0","selected":"a","nodes":[{"id":"a","outbound":{"type":"direct"}},{"id":"b","outbound":{"type":"direct"}}]}"#).unwrap();
        config.selectors.push(group(PolicyStrategy::Fallback));
        let registry = Arc::new(Mutex::new(HashMap::from([(
            "g".into(),
            Group {
                health: HashMap::from([
                    (
                        "a".into(),
                        Health {
                            latency: Some(20),
                            checked: Instant::now(),
                            error: "",
                        },
                    ),
                    (
                        "b".into(),
                        Health {
                            latency: Some(10),
                            checked: Instant::now(),
                            error: "",
                        },
                    ),
                ]),
                selected: Some("a".into()),
                cursor: Arc::new(AtomicU64::new(0)),
                checks: 2,
            },
        )])));
        let policies = PolicyRuntime {
            registry: registry.clone(),
            budget: Arc::new(Semaphore::new(4)),
            runtime: runtime.handle().clone(),
            worker: None,
        };
        let old = policies.view(&config).unwrap();
        {
            let mut states = registry.lock().unwrap();
            let state = states.get_mut("g").unwrap();
            state.health.get_mut("a").unwrap().latency = None;
            state.health.get_mut("a").unwrap().error = "PolicyProbeTimeout";
        }
        let next = policies.view(&config).unwrap();
        // Even first use of the old view retains the state captured at accept.
        assert_eq!(old.choose("g").unwrap(), "a");
        assert_eq!(next.choose("g").unwrap(), "b");
        let report = policies.report(&config).unwrap();
        assert_eq!(report["g"].selected.as_deref(), Some("b"));
        assert_eq!(report["g"].members[0].error, "PolicyProbeTimeout");
    }

    #[test]
    fn scheduler_skips_active_members_and_never_enqueues_catchup_rounds() {
        let now = Instant::now();
        let mut jobs = vec![
            ProbeJob {
                group: 0,
                node: 0,
                next: now,
                active: false,
            },
            ProbeJob {
                group: 1,
                node: 1,
                next: now,
                active: false,
            },
            ProbeJob {
                group: 0,
                node: 2,
                next: now,
                active: false,
            },
        ];
        assert_eq!(due_job(&jobs, now), Some(0));
        jobs[0].active = true;
        assert_eq!(due_job(&jobs, now), Some(1));
        jobs[1].next = now + Duration::from_secs(1);
        assert_eq!(due_job(&jobs, now), Some(2));
        jobs[2].active = true;
        assert_eq!(due_job(&jobs, now), None);
        jobs[0].active = false;
        jobs[0].next = now + Duration::from_secs(3);
        assert_eq!(due_job(&jobs, now + Duration::from_secs(2)), Some(1));
        assert_eq!(jobs.len(), 3);
    }
}
