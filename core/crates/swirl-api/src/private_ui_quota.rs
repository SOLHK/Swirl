//! A QA-only quota bridge for the actual, separately owned Qt process.
//!
//! No provider or filesystem input is accepted. The parent owns the original
//! durable reservation, pipes, independent deadline and actual process exit.
//! The ordinary product DLL does not export this ABI. A receipt is never an
//! ExitProof, account identity, official billing observation or live permission.
use ring::digest;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    net::SocketAddr,
    sync::{Arc, Mutex, OnceLock},
};
use swirl_transport::egress::budget::{self, TcpQuota};

pub const OUTPUT_CAPACITY: usize = 16 * 1024;
const TASK: &str = "swirl-0.2.40-private-acceptance";
type Result<T> = std::result::Result<T, &'static str>;
static SESSION: OnceLock<Mutex<Option<Session>>> = OnceLock::new();

pub fn identity() -> Value {
    let build = crate::build_info();
    json!({"private_worker_schema":1,"role":"swirl_private_qt_ui",
        "guard_mode":"mandatory_before_grant","live":false,
        "abi_version":build["abi_version"],"source_sha":build["source_sha"],
        "build_id":build["build_id"],"target":build["target"],
        "package_version":build["package_version"]})
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Endpoint {
    host: String,
    port: u16,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Grant {
    task_id: String,
    ledger_id: String,
    sequence: u64,
    source_sha: String,
    build_id: String,
    role: String,
    workload: String,
    byte_limit: u64,
    connection_limit: u32,
    receive_reservation: u64,
    timeout_ms: u32,
    endpoint: Endpoint,
    listener: Endpoint,
    config_fingerprint: String,
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Message {
    Identity {
        schema: u32,
    },
    Grant {
        schema: u32,
        reservation_id: String,
        nonce: String,
        plan_digest: String,
        grant: Box<Grant>,
    },
    Start {
        schema: u32,
        reservation_id: String,
        nonce: String,
        plan_digest: String,
    },
    FixtureReady {
        schema: u32,
        reservation_id: String,
        nonce: String,
        plan_digest: String,
    },
    Snapshot {
        schema: u32,
        reservation_id: String,
        nonce: String,
        plan_digest: String,
    },
    Cancel {
        schema: u32,
        reservation_id: String,
        nonce: String,
        plan_digest: String,
    },
    Finish {
        schema: u32,
        reservation_id: String,
        nonce: String,
        plan_digest: String,
    },
}

#[derive(Clone)]
struct Binding {
    reservation_id: String,
    nonce: String,
    plan_digest: String,
}

impl Message {
    fn binding(&self) -> Option<(u32, &str, &str, &str)> {
        match self {
            Self::Identity { .. } => None,
            Self::Grant {
                schema,
                reservation_id,
                nonce,
                plan_digest,
                ..
            }
            | Self::Start {
                schema,
                reservation_id,
                nonce,
                plan_digest,
            }
            | Self::FixtureReady {
                schema,
                reservation_id,
                nonce,
                plan_digest,
            }
            | Self::Snapshot {
                schema,
                reservation_id,
                nonce,
                plan_digest,
            }
            | Self::Cancel {
                schema,
                reservation_id,
                nonce,
                plan_digest,
            }
            | Self::Finish {
                schema,
                reservation_id,
                nonce,
                plan_digest,
            } => Some((*schema, reservation_id, nonce, plan_digest)),
        }
    }
}

struct Session {
    binding: Binding,
    quota: Arc<TcpQuota>,
    started: bool,
    fixture_verified: bool,
    finished: bool,
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn digest_text(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

impl Grant {
    fn validate(&self, binding: &Binding, raw: &Value) -> Result<(SocketAddr, SocketAddr)> {
        let canonical = serde_json::to_vec(raw).map_err(|_| "PrivateUiGrant")?;
        let build = crate::build_info();
        if self.task_id != TASK
            || !digest_text(&self.ledger_id)
            || self.sequence == 0
            || self.sequence.to_string() != binding.reservation_id
            || !digest_text(&binding.nonce)
            || !digest_text(&binding.plan_digest)
            || binding.plan_digest != hex(digest::digest(&digest::SHA256, &canonical).as_ref())
            || self.role != "synthetic_qt_ui"
            || self.workload != "qt_ui_session"
            || !digest_text(&self.config_fingerprint)
            || build["source_sha"].as_str() != Some(self.source_sha.as_str())
            || build["build_id"].as_str() != Some(self.build_id.as_str())
            || self.endpoint.host != "127.0.0.1"
            || self.endpoint.port == 0
            || self.listener.host != "127.0.0.1"
            || self.listener.port == 0
            || self.endpoint.port == self.listener.port
            || !(1..=budget::MAX_BYTES).contains(&self.byte_limit)
            || !(1..=12).contains(&self.connection_limit)
            || !(100..=budget::MAX_TIMEOUT_MS).contains(&self.timeout_ms)
            || self.receive_reservation
                != u64::from(self.connection_limit) * budget::RECEIVE_RESERVATION
        {
            return Err("PrivateUiGrant");
        }
        Ok((
            SocketAddr::from(([127, 0, 0, 1], self.endpoint.port)),
            SocketAddr::from(([127, 0, 0, 1], self.listener.port)),
        ))
    }
}

impl Session {
    fn accepts(&self, message: &Message) -> bool {
        message.binding()
            == Some((
                1,
                &self.binding.reservation_id,
                &self.binding.nonce,
                &self.binding.plan_digest,
            ))
    }

    fn response(&self, operation: &str) -> Result<Value> {
        let identity = identity();
        let mut value = json!({"schema":1,"op":operation,"ok":true,
            "reservation_id":self.binding.reservation_id,"nonce":self.binding.nonce,
            "plan_digest":self.binding.plan_digest,"identity":identity,
            "source_sha":identity["source_sha"],"build_id":identity["build_id"],
            "guard_mode":"mandatory_before_grant",
            "guard":self.quota.snapshot().map_err(|_| "PrivateUiQuotaState")?});
        if operation == "running" || operation == "finished" {
            value["fixture_verified"] = json!(self.fixture_verified);
        }
        if operation == "finished" {
            let snapshot = self.quota.snapshot().map_err(|_| "PrivateUiQuotaState")?;
            // Only child transport facts: the child cannot attest the parent's
            // durable ledger, native exit proof, account or settlement.
            value["scope"] = json!("synthetic-qt-ui-raw-tcp-v1");
            value["raw_tcp_quota_exercised"] =
                json!(snapshot.connection_attempts > 0 && snapshot.upload + snapshot.download > 0);
            value["outcome"] = json!(
                if snapshot.upload + snapshot.download == snapshot.byte_limit {
                    "quota_stopped"
                } else if snapshot.timed_out {
                    "deadline_expired"
                } else {
                    "qt_ui_finished"
                }
            );
        }
        Ok(value)
    }
}

fn execute(session: &mut Option<Session>, input: &[u8]) -> Result<Value> {
    if input.is_empty() || input.len() > OUTPUT_CAPACITY {
        return Err("PrivateUiFrame");
    }
    // This parser rejects duplicate JSON keys before serde builds a typed
    // message; Qt must forward the raw line rather than normalize it first.
    let raw = swirl_subscription::parse_json_value(input).map_err(|_| "PrivateUiJson")?;
    let message: Message = serde_json::from_value(raw.clone()).map_err(|_| "PrivateUiCommand")?;
    if let Message::Identity { schema: 1 } = message {
        if session.is_some() {
            return Err("PrivateUiAlreadyInstalled");
        }
        return Ok(identity());
    }
    if let Message::Grant {
        schema,
        reservation_id,
        nonce,
        plan_digest,
        grant,
    } = message
    {
        if schema != 1 || session.is_some() {
            return Err("PrivateUiAlreadyInstalled");
        }
        let binding = Binding {
            reservation_id,
            nonce,
            plan_digest,
        };
        let (endpoint, listener) = grant.validate(&binding, &raw["grant"])?;
        let quota = budget::install_ui(
            grant.byte_limit,
            grant.connection_limit,
            grant.timeout_ms,
            endpoint,
            listener,
        )
        .map_err(|_| "PrivateUiQuotaInstall")?;
        *session = Some(Session {
            binding,
            quota,
            started: false,
            fixture_verified: false,
            finished: false,
        });
        return session
            .as_ref()
            .ok_or("PrivateUiQuotaState")?
            .response("ready");
    }
    let active = session.as_mut().ok_or("PrivateUiGrantRequired")?;
    if !active.accepts(&message) || active.finished {
        return Err("PrivateUiBinding");
    }
    match message {
        Message::Start { .. } if !active.started => {
            active.quota.start_ui().map_err(|_| "PrivateUiStart")?;
            active.started = true;
            active.response("started")
        }
        Message::FixtureReady { .. } if active.started && !active.fixture_verified => {
            // The trusted QA Qt bridge calls this only after the unchanged
            // owned-fixture proof/EOF/manifest/DPAPI gates have completed.
            active.fixture_verified = true;
            active.response("running")
        }
        Message::Snapshot { .. } => active.response("snapshot"),
        Message::Cancel { .. } => {
            active.quota.cancel();
            active.response("snapshot")
        }
        Message::Finish { .. } if active.started => {
            active.quota.cancel();
            active.finished = true;
            active.response("finished")
        }
        _ => Err("PrivateUiPhase"),
    }
}

/// Strict JSON dispatcher used by the QA C ABI and fresh-process tests.
pub fn dispatch(input: &[u8]) -> Value {
    let Ok(mut session) = SESSION.get_or_init(|| Mutex::new(None)).lock() else {
        return json!({"ok":false,"error":"PrivateUiQuotaState"});
    };
    match execute(&mut session, input) {
        Ok(value) => value,
        Err(code) => {
            if let Some(active) = session.as_ref() {
                active.quota.cancel();
            }
            json!({"ok":false,"error":code})
        }
    }
}

/// Execute one bounded QA control frame without unwinding into Qt.
///
/// # Safety
/// Input and output must be valid, initialized, nonoverlapping buffers for the
/// declared lengths. Output must provide at least OUTPUT_CAPACITY writable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swirl_private_ui_quota_v1(
    input: *const u8,
    input_len: usize,
    output: *mut u8,
    output_capacity: usize,
) -> isize {
    if input.is_null()
        || output.is_null()
        || input_len == 0
        || input_len > OUTPUT_CAPACITY
        || output_capacity < OUTPUT_CAPACITY
    {
        return -1;
    }
    std::panic::catch_unwind(|| {
        // SAFETY: the caller owns the buffers under the documented ABI contract.
        let input = unsafe { std::slice::from_raw_parts(input, input_len) };
        let Ok(bytes) = serde_json::to_vec(&dispatch(input)) else {
            return -3;
        };
        if bytes.len() > output_capacity {
            return -1;
        }
        // SAFETY: the caller provides sufficient nonoverlapping writable output.
        unsafe {
            std::ptr::copy_nonoverlapping(bytes.as_ptr(), output, bytes.len());
        }
        bytes.len() as isize
    })
    .unwrap_or(-2)
}
