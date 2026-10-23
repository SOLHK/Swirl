//! One bounded user-requested URL test per core. Network work runs on Tokio,
//! while control calls only update a small redacted state under a short lock.
use serde::Serialize;
use std::{
    future::Future,
    sync::{Arc, Mutex},
};
use swirl_protocol::{ConnectTimings, UrlTestFailure, UrlTestMetrics, UrlTestStage};
use tokio::{runtime::Handle, task::JoinHandle};

type Result<T> = std::result::Result<T, &'static str>;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ProbePhase {
    Idle,
    Running,
    Succeeded,
    Failed,
    Cancelled,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ProbeMetrics {
    pub outbound_connect_ms: u64,
    pub origin_tls_ms: Option<u64>,
    pub response_headers_ms: u64,
    pub http_status: u16,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub outbound_timing: Option<ConnectTimings>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ProbeFailure {
    pub stage: &'static str,
    pub code: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub http_status: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub outbound_timing: Option<ConnectTimings>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ProbeStatus {
    pub request_id: u64,
    pub state: ProbePhase,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metrics: Option<ProbeMetrics>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure: Option<ProbeFailure>,
}

impl Default for ProbeStatus {
    fn default() -> Self {
        Self {
            request_id: 0,
            state: ProbePhase::Idle,
            metrics: None,
            failure: None,
        }
    }
}

struct Slot {
    generation: u64,
    status: ProbeStatus,
    task: Option<JoinHandle<()>>,
}

pub(super) struct ProbeRuntime {
    runtime: Handle,
    slot: Arc<Mutex<Slot>>,
}

impl ProbeRuntime {
    pub fn new(runtime: Handle) -> Self {
        Self {
            runtime,
            slot: Arc::new(Mutex::new(Slot {
                generation: 0,
                status: ProbeStatus::default(),
                task: None,
            })),
        }
    }

    pub fn status(&self) -> Result<ProbeStatus> {
        Ok(self.slot.lock().map_err(|_| "ProbeState")?.status.clone())
    }

    /// `future` owns all network inputs. Spawning it never waits for a socket,
    /// TLS handshake, or response while the control ABI holds its mutex.
    pub fn start_with<F>(&self, future: F) -> Result<ProbeStatus>
    where
        F: Future<Output = std::result::Result<UrlTestMetrics, UrlTestFailure>> + Send + 'static,
    {
        let mut slot = self.slot.lock().map_err(|_| "ProbeState")?;
        let generation = slot
            .generation
            .checked_add(1)
            .ok_or("ProbeGenerationLimit")?;
        if let Some(previous) = slot.task.take() {
            previous.abort();
        }
        slot.generation = generation;
        slot.status = ProbeStatus {
            request_id: generation,
            state: ProbePhase::Running,
            metrics: None,
            failure: None,
        };
        let shared = self.slot.clone();
        slot.task = Some(self.runtime.spawn(async move {
            let result = future.await;
            Self::finish(&shared, generation, result);
        }));
        Ok(slot.status.clone())
    }

    fn finish(
        shared: &Mutex<Slot>,
        generation: u64,
        result: std::result::Result<UrlTestMetrics, UrlTestFailure>,
    ) {
        let Ok(mut slot) = shared.lock() else {
            return;
        };
        if slot.generation != generation || slot.status.state != ProbePhase::Running {
            return;
        }
        slot.task = None;
        slot.status = match result {
            Ok(metrics) => ProbeStatus {
                request_id: generation,
                state: ProbePhase::Succeeded,
                metrics: Some(ProbeMetrics {
                    outbound_connect_ms: metrics.outbound_connect_ms,
                    origin_tls_ms: metrics.origin_tls_ms,
                    response_headers_ms: metrics.response_headers_ms,
                    http_status: metrics.http_status,
                    outbound_timing: metrics.outbound_timing,
                }),
                failure: None,
            },
            Err(error) => ProbeStatus {
                request_id: generation,
                state: ProbePhase::Failed,
                metrics: None,
                failure: Some(ProbeFailure {
                    stage: match error.stage {
                        UrlTestStage::Input => "input",
                        UrlTestStage::Dns => "dns",
                        UrlTestStage::TcpConnect => "tcp_connect",
                        UrlTestStage::OutboundHandshake => "outbound_handshake",
                        UrlTestStage::OutboundConnect => "outbound_connect",
                        UrlTestStage::OriginTls => "origin_tls",
                        UrlTestStage::RequestWrite => "request_write",
                        UrlTestStage::ResponseHeaders => "response_headers",
                        UrlTestStage::HttpStatus => "http_status",
                    },
                    code: error.code,
                    http_status: error.http_status,
                    outbound_timing: error.outbound_timing.map(|timing| *timing),
                }),
            },
        };
    }

    fn transition(&self, state: ProbePhase) -> Result<ProbeStatus> {
        let mut slot = self.slot.lock().map_err(|_| "ProbeState")?;
        slot.generation = slot
            .generation
            .checked_add(1)
            .ok_or("ProbeGenerationLimit")?;
        if let Some(task) = slot.task.take() {
            task.abort();
        }
        slot.status = ProbeStatus {
            request_id: slot.generation,
            state,
            metrics: None,
            failure: None,
        };
        Ok(slot.status.clone())
    }

    pub fn cancel(&self) -> Result<ProbeStatus> {
        self.transition(ProbePhase::Cancelled)
    }

    pub fn invalidate(&self) -> Result<()> {
        self.transition(ProbePhase::Idle).map(|_| ())
    }
}

#[cfg(test)]
#[path = "probe_tests.rs"]
mod tests;
