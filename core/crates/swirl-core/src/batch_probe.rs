//! Concurrent per-node latency probing.
//!
//! The GUI used to start one whole engine per node, which made a large latency
//! sweep serialise engine startup, configuration and health checks. This module
//! probes the requested nodes concurrently instead, reusing one immutable plan
//! snapshot. Each probe dials only its own node through the same strict
//! protocol path: nothing is selected, no policy is re-evaluated and a failure
//! never falls back to DIRECT.
use serde::Serialize;
use std::{
    collections::BTreeMap,
    sync::{
        Arc, Mutex,
        atomic::{AtomicUsize, Ordering},
    },
};
use swirl_dns::Resolver;
use swirl_protocol::{Transport, UrlTestFailure, UrlTestMetrics, UrlTestStage};
use swirl_subscription::{HealthProbe, Outbound};
use tokio::task::{JoinHandle, JoinSet};

/// Upper bound on one sweep. The product cap for configured nodes is 512.
pub const MAX_BATCH_NODES: usize = 512;
/// Bounded simultaneous probes. Short independent connects finish a large
/// library in a few rounds of completions without exhausting sockets or CPU.
pub const MAX_CONCURRENCY: usize = 32;
const DEFAULT_CONCURRENCY: usize = 16;

/// Immutable inputs for one sweep, captured under the enclosing plan lock so a
/// sweep always probes one consistent configuration generation.
pub(super) struct BatchInputs {
    pub targets: BTreeMap<String, (Outbound, Option<Transport>)>,
    pub resolver: Arc<Resolver>,
}

/// Validate one sweep request without touching any network state.
pub(super) fn validate_request(nodes: &[String]) -> Result<(), &'static str> {
    if nodes.is_empty() || nodes.len() > MAX_BATCH_NODES {
        return Err("ProbeNodesSize");
    }
    let mut seen = std::collections::BTreeSet::new();
    for id in nodes {
        if !seen.insert(id.as_str()) {
            return Err("ProbeNodesDuplicate");
        }
    }
    Ok(())
}

/// Clamp a caller's concurrency into the supported band.
pub(super) fn effective_concurrency(value: Option<usize>) -> usize {
    value
        .unwrap_or(DEFAULT_CONCURRENCY)
        .clamp(1, MAX_CONCURRENCY)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BatchState {
    Running,
    Ok,
    Failed,
}

#[derive(Clone, Debug, Serialize)]
pub struct BatchRow {
    pub node: String,
    pub state: BatchState,
    /// Time to response headers, the value the UI shows as latency.
    pub latency_ms: Option<u64>,
    pub outbound_connect_ms: Option<u64>,
    pub http_status: Option<u16>,
    pub failure_code: Option<&'static str>,
    pub failure_stage: Option<&'static str>,
}

#[derive(Clone, Debug, Serialize)]
pub struct BatchSnapshot {
    pub request_id: u64,
    pub done: bool,
    pub url: String,
    pub concurrency: usize,
    pub rows: Vec<BatchRow>,
}

struct Slot {
    generation: u64,
    request_id: u64,
    url: String,
    concurrency: usize,
    rows: Vec<BatchRow>,
    index: BTreeMap<String, usize>,
    done: bool,
    task: Option<JoinHandle<()>>,
}

struct ActiveProbe(Arc<AtomicUsize>);
impl Drop for ActiveProbe {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

pub(super) struct BatchProbeRuntime {
    runtime: tokio::runtime::Handle,
    slot: Arc<Mutex<Slot>>,
    in_flight: Arc<AtomicUsize>,
}

impl BatchProbeRuntime {
    pub fn new(runtime: tokio::runtime::Handle) -> Self {
        Self {
            runtime,
            in_flight: Arc::new(AtomicUsize::new(0)),
            slot: Arc::new(Mutex::new(Slot {
                generation: 0,
                request_id: 0,
                url: String::new(),
                concurrency: 0,
                rows: Vec::new(),
                index: BTreeMap::new(),
                done: true,
                task: None,
            })),
        }
    }

    pub fn quiescent(&self) -> bool {
        self.in_flight.load(Ordering::Acquire) == 0
    }

    pub fn snapshot(&self) -> Result<BatchSnapshot, &'static str> {
        let slot = self.slot.lock().map_err(|_| "ProbeState")?;
        Ok(BatchSnapshot {
            request_id: slot.request_id,
            done: slot.done,
            url: slot.url.clone(),
            concurrency: slot.concurrency,
            rows: slot.rows.clone(),
        })
    }

    pub fn cancel(&self) -> Result<BatchSnapshot, &'static str> {
        {
            let mut slot = self.slot.lock().map_err(|_| "ProbeState")?;
            slot.generation = slot.generation.wrapping_add(1);
            if let Some(task) = slot.task.take() {
                task.abort();
            }
            for row in &mut slot.rows {
                if row.state == BatchState::Running {
                    row.state = BatchState::Failed;
                    row.failure_code = Some("ProbeCancelled");
                }
            }
            slot.done = true;
        }
        self.snapshot()
    }

    /// Start one sweep. Callers build the inputs under their plan lock, so this
    /// never touches admission, selection or the listener.
    pub fn start(
        &self,
        inputs: BatchInputs,
        nodes: Vec<String>,
        options: HealthProbe,
        concurrency: Option<usize>,
    ) -> Result<BatchSnapshot, &'static str> {
        validate_request(&nodes)?;
        let concurrency = effective_concurrency(concurrency);
        let mut slot = self.slot.lock().map_err(|_| "ProbeState")?;
        let generation = slot
            .generation
            .checked_add(1)
            .ok_or("ProbeGenerationLimit")?;
        if let Some(previous) = slot.task.take() {
            previous.abort();
        }
        let mut rows = Vec::with_capacity(nodes.len());
        let mut index = BTreeMap::new();
        for id in &nodes {
            index.insert(id.clone(), rows.len());
            rows.push(BatchRow {
                node: id.clone(),
                state: BatchState::Running,
                latency_ms: None,
                outbound_connect_ms: None,
                http_status: None,
                failure_code: None,
                failure_stage: None,
            });
        }
        slot.generation = generation;
        slot.request_id = generation;
        slot.url = options.url.clone();
        slot.concurrency = concurrency;
        slot.rows = rows;
        slot.index = index;
        slot.done = false;
        let shared_slot = self.slot.clone();
        let inputs = Arc::new(inputs);
        self.in_flight.fetch_add(1, Ordering::AcqRel);
        let active = ActiveProbe(self.in_flight.clone());
        slot.task = Some(self.runtime.spawn(async move {
            let _active = active;
            drive(shared_slot, generation, inputs, nodes, options, concurrency).await;
        }));
        drop(slot);
        self.snapshot()
    }
}

async fn drive(
    slot: Arc<Mutex<Slot>>,
    generation: u64,
    inputs: Arc<BatchInputs>,
    nodes: Vec<String>,
    options: HealthProbe,
    concurrency: usize,
) {
    let mut pending = nodes.into_iter();
    let mut set = JoinSet::new();
    let mut running = 0usize;
    loop {
        while running < concurrency {
            let Some(id) = pending.next() else { break };
            let inputs = inputs.clone();
            let options = options.clone();
            set.spawn(async move {
                let row = probe_one(inputs, id.clone(), options).await;
                (id, row)
            });
            running += 1;
        }
        if running == 0 {
            break;
        }
        let Some(joined) = set.join_next().await else {
            break;
        };
        running -= 1;
        if let Ok((id, row)) = joined
            && let Ok(mut guarded) = slot.lock()
        {
            if guarded.generation != generation {
                return;
            }
            if let Some(index) = guarded.index.get(&id).copied()
                && let Some(slot_row) = guarded.rows.get_mut(index)
            {
                *slot_row = row;
            }
        }
        if slot
            .lock()
            .map(|guarded| guarded.generation != generation || guarded.done)
            .unwrap_or(true)
        {
            break;
        }
    }
    // A panicked probe must never leave rows stuck in "running".
    set.abort_all();
    while set.join_next().await.is_some() {}
    if let Ok(mut guarded) = slot.lock()
        && guarded.generation == generation
    {
        for row in &mut guarded.rows {
            if row.state == BatchState::Running {
                row.state = BatchState::Failed;
                row.failure_code = Some("ProbeAborted");
            }
        }
        guarded.done = true;
        guarded.task = None;
    }
}

async fn probe_one(inputs: Arc<BatchInputs>, id: String, options: HealthProbe) -> BatchRow {
    let Some((outbound, transport)) = inputs.targets.get(&id) else {
        return finish_failure(id, "ProbeNodeUnknown", "input");
    };
    // Match probe_start's unset-expected path: a latency sweep accepts any 2xx
    // instead of pinning the policy editor's default 204. The HealthProbe value
    // stays for display only.
    let expected = None;
    let outcome: Result<UrlTestMetrics, UrlTestFailure> = match transport {
        Some(transport) => {
            swirl_protocol::url_test_head_with_transport(
                outbound,
                &options,
                &inputs.resolver,
                expected,
                transport,
            )
            .await
        }
        None => swirl_protocol::url_test_head(outbound, &options, &inputs.resolver, expected).await,
    };
    match outcome {
        Ok(metrics) => BatchRow {
            node: id,
            state: BatchState::Ok,
            latency_ms: Some(metrics.response_headers_ms),
            outbound_connect_ms: Some(metrics.outbound_connect_ms),
            http_status: Some(metrics.http_status),
            failure_code: None,
            failure_stage: None,
        },
        Err(error) => row_from_failure(id, &error),
    }
}

fn stage_name(stage: UrlTestStage) -> &'static str {
    match stage {
        UrlTestStage::Input => "input",
        UrlTestStage::Dns => "dns",
        UrlTestStage::TcpConnect => "tcp_connect",
        UrlTestStage::OutboundHandshake => "outbound_handshake",
        UrlTestStage::OutboundConnect => "outbound_connect",
        UrlTestStage::OriginTls => "origin_tls",
        UrlTestStage::RequestWrite => "request_write",
        UrlTestStage::ResponseHeaders => "response_headers",
        UrlTestStage::HttpStatus => "http_status",
    }
}

fn row_from_failure(node: String, error: &UrlTestFailure) -> BatchRow {
    BatchRow {
        node,
        state: BatchState::Failed,
        latency_ms: None,
        outbound_connect_ms: error
            .outbound_timing
            .as_ref()
            .and_then(|timing| timing.tcp_connected_attempt_us)
            .map(|micros| micros / 1000),
        http_status: error.http_status,
        failure_code: Some(error.code),
        failure_stage: Some(stage_name(error.stage)),
    }
}

fn finish_failure(node: String, code: &'static str, stage: &'static str) -> BatchRow {
    BatchRow {
        node,
        state: BatchState::Failed,
        latency_ms: None,
        outbound_connect_ms: None,
        http_status: None,
        failure_code: Some(code),
        failure_stage: Some(stage),
    }
}

#[cfg(test)]
#[path = "batch_probe_tests.rs"]
mod tests;
