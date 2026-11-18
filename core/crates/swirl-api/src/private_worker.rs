//! A single-use synthetic QA worker, never a live-provider admission API.
//! The parent owns its private pipes, durable reservation, process identity,
//! absolute deadline and OS exit proof. A child receipt is not that proof.
use ring::{
    digest, hmac,
    rand::{SecureRandom, SystemRandom},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, IsTerminal, Read, Write},
    net::{Ipv4Addr, SocketAddr},
    sync::{
        Arc, Mutex,
        atomic::{AtomicU8, Ordering},
    },
    thread,
    time::Duration,
};
use swirl_transport::egress::budget::{self, TcpQuota};
use tokio::io::{AsyncReadExt, AsyncWriteExt};

mod billing;

const MAX_FRAME: usize = 16 * 1024;
const TASK: &str = "swirl-0.2.40-private-acceptance";
const CANCELLED: u8 = 1;
const PROTOCOL_ERROR: u8 = 2;
const PIPE_ERROR: u8 = 3;
type Result<T> = std::result::Result<T, &'static str>;
type Output = Arc<Mutex<std::io::Stdout>>;

/// Fixed, non-secret compiled identity. The parent separately hashes the EXE.
pub fn identity() -> Value {
    let build = crate::build_info();
    json!({"private_worker_schema":1,"role":"swirl_private_worker",
        "guard_mode":"mandatory_before_grant","live":false,
        "abi_version":build["abi_version"],"source_sha":build["source_sha"],
        "build_id":build["build_id"],"target":build["target"],
        "package_version":build["package_version"]})
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Endpoint {
    host: String,
    port: u16,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct FixtureTls {
    server_name: String,
    ca_der_base64: String,
}

#[derive(Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Workload {
    UploadUntilStop,
    DownloadUntilStop,
    StallRuntimeAfterConnect,
    CoreProbe,
    BillingSnapshot,
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
    byte_limit: u64,
    connection_limit: u32,
    receive_reservation: u64,
    timeout_ms: u32,
    endpoint: Endpoint,
    challenge: String,
    workload: Workload,
    config_fingerprint: String,
    tls: Option<FixtureTls>,
    billing: Option<billing::BillingGrant>,
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
enum Message {
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
}

#[derive(Clone)]
struct Binding {
    reservation_id: String,
    nonce: String,
    plan_digest: String,
}

impl Message {
    fn binding(&self) -> (u32, &str, &str, &str) {
        match self {
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
            } => (*schema, reservation_id, nonce, plan_digest),
        }
    }
}

impl Binding {
    fn accepts(&self, message: &Message) -> bool {
        message.binding() == (1, &self.reservation_id, &self.nonce, &self.plan_digest)
    }

    fn response(&self, operation: &str, guard: &TcpQuota) -> Result<Value> {
        let build = identity();
        Ok(json!({"schema":1,"op":operation,"ok":true,
            "reservation_id":self.reservation_id,"nonce":self.nonce,
            "plan_digest":self.plan_digest,"identity":build,
            "source_sha":build["source_sha"],"build_id":build["build_id"],
            "guard_mode":"mandatory_before_grant",
            "guard":guard.snapshot().map_err(|_| "PrivateWorkerQuotaState")?}))
    }
}

fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        result.push(char::from(DIGITS[usize::from(byte >> 4)]));
        result.push(char::from(DIGITS[usize::from(byte & 15)]));
    }
    result
}

fn key(value: &str) -> Option<[u8; 32]> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return None;
    }
    let mut result = [0; 32];
    for (index, byte) in result.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&value[index * 2..index * 2 + 2], 16).ok()?;
    }
    Some(result)
}

fn read_message(input: &mut impl BufRead) -> Result<Option<(Message, Value)>> {
    let mut bytes = Vec::new();
    let count = input
        .take((MAX_FRAME + 1) as u64)
        .read_until(b'\n', &mut bytes)
        .map_err(|_| "PrivateWorkerPipeRead")?;
    if count == 0 {
        return Ok(None);
    }
    if count > MAX_FRAME || !bytes.ends_with(b"\n") {
        return Err("PrivateWorkerFrame");
    }
    let value = swirl_subscription::parse_json_value(&bytes).map_err(|_| "PrivateWorkerJson")?;
    let message = serde_json::from_value(value.clone()).map_err(|_| "PrivateWorkerCommand")?;
    Ok(Some((message, value)))
}

fn emit(output: &Output, value: Value) -> Result<()> {
    let mut bytes = serde_json::to_vec(&value).map_err(|_| "PrivateWorkerResponse")?;
    if bytes.len() + 1 > MAX_FRAME {
        return Err("PrivateWorkerResponse");
    }
    bytes.push(b'\n');
    let mut output = output.lock().map_err(|_| "PrivateWorkerPipeState")?;
    output
        .write_all(&bytes)
        .and_then(|()| output.flush())
        .map_err(|_| "PrivateWorkerPipeWrite")
}

impl Grant {
    fn endpoint(&self) -> SocketAddr {
        SocketAddr::from((Ipv4Addr::LOCALHOST, self.endpoint.port))
    }

    fn validate(&self, binding: &Binding, value: &Value) -> Result<()> {
        let build = identity();
        let canonical = serde_json::to_vec(&value["grant"]).map_err(|_| "PrivateWorkerGrant")?;
        if self.task_id != TASK
            || self.role != "synthetic_loopback"
            || self.sequence == 0
            || binding.reservation_id != self.sequence.to_string()
            || key(&binding.nonce).is_none()
            || key(&binding.plan_digest).is_none()
            || key(&self.ledger_id).is_none()
            || key(&self.config_fingerprint).is_none()
            || key(&self.challenge).is_none()
            || binding.plan_digest != hex(digest::digest(&digest::SHA256, &canonical).as_ref())
            || build["source_sha"].as_str() != Some(self.source_sha.as_str())
            || build["build_id"].as_str() != Some(self.build_id.as_str())
            || self.endpoint.host != "127.0.0.1"
            || self.endpoint.port == 0
            || !(1..=budget::MAX_BYTES).contains(&self.byte_limit)
            || !(1..=budget::MAX_CONNECTIONS).contains(&self.connection_limit)
            || !(1..=budget::MAX_TIMEOUT_MS).contains(&self.timeout_ms)
            || self.receive_reservation
                != u64::from(self.connection_limit) * budget::RECEIVE_RESERVATION
            || matches!(
                self.workload,
                Workload::CoreProbe | Workload::BillingSnapshot
            ) != self.tls.is_some()
            || (self.tls.is_some() && self.timeout_ms < 100)
            || (self.workload == Workload::BillingSnapshot) != self.billing.is_some()
        {
            return Err("PrivateWorkerGrant");
        }
        if let Some(billing) = &self.billing {
            if self.byte_limit != billing::BYTE_LIMIT || self.connection_limit != 2 {
                return Err("PrivateWorkerGrant");
            }
            billing.validate(&binding.nonce)?;
        }
        if let Some(tls) = &self.tls {
            if !swirl_subscription::valid_host(&tls.server_name)
                || tls.ca_der_base64.is_empty()
                || tls.ca_der_base64.len() > 8192
                || !tls.ca_der_base64.is_ascii()
            {
                return Err("PrivateWorkerTls");
            }
            if self.workload == Workload::BillingSnapshot {
                billing::tls_config(tls)?;
            } else {
                swirl_transport::validate_tls(&self.tls_options(tls), None)
                    .map_err(|_| "PrivateWorkerTls")?;
            }
        }
        Ok(())
    }

    fn tls_options(&self, tls: &FixtureTls) -> swirl_subscription::Tls {
        swirl_subscription::Tls {
            server_name: tls.server_name.clone(),
            alpn: vec!["http/1.1".into()],
            ca_der_base64: Some(tls.ca_der_base64.clone()),
        }
    }
}

struct CancelOnDrop(Arc<TcpQuota>);
impl Drop for CancelOnDrop {
    fn drop(&mut self) {
        self.0.cancel();
    }
}

fn finish(
    output: &Output,
    binding: &Binding,
    guard: &TcpQuota,
    fixture_verified: bool,
    outcome: &'static str,
    metrics: Option<Value>,
    billing: Option<Value>,
) -> Result<()> {
    guard.cancel();
    let mut response = binding.response("finished", guard)?;
    response["fixture_verified"] = json!(fixture_verified);
    response["outcome"] = json!(outcome);
    if let Some(metrics) = metrics {
        response["metrics"] = metrics;
    }
    if outcome == "billing_snapshot_succeeded"
        && let Some(billing) = billing
    {
        response["billing"] = billing;
    }
    emit(output, response)
}

fn control_reader(
    mut input: BufReader<std::io::Stdin>,
    output: Output,
    binding: Binding,
    guard: Arc<TcpQuota>,
    stopped: Arc<AtomicU8>,
) {
    for _ in 0..32 {
        let message = match read_message(&mut input) {
            Ok(Some((message, _))) if binding.accepts(&message) => message,
            Ok(None) => {
                stopped.store(CANCELLED, Ordering::Release);
                guard.cancel();
                return;
            }
            _ => {
                stopped.store(PROTOCOL_ERROR, Ordering::Release);
                guard.cancel();
                return;
            }
        };
        match message {
            Message::Snapshot { .. } => {
                if binding
                    .response("snapshot", &guard)
                    .and_then(|value| emit(&output, value))
                    .is_err()
                {
                    stopped.store(PIPE_ERROR, Ordering::Release);
                    guard.cancel();
                    return;
                }
            }
            Message::Cancel { .. } => {
                stopped.store(CANCELLED, Ordering::Release);
                guard.cancel();
                return;
            }
            _ => {
                stopped.store(PROTOCOL_ERROR, Ordering::Release);
                guard.cancel();
                return;
            }
        }
    }
    stopped.store(PROTOCOL_ERROR, Ordering::Release);
    guard.cancel();
}

async fn authenticate_fixture(grant: &Grant) -> Result<swirl_transport::TcpConnection> {
    let mut socket = swirl_transport::connect_tcp(grant.endpoint())
        .await
        .map_err(|_| "worker_io_error")?;
    let mut challenge = [0; 32];
    SystemRandom::new()
        .fill(&mut challenge)
        .map_err(|_| "worker_io_error")?;
    let request = format!("SWIRL-SYNTHETIC-V1 {}\n", hex(&challenge));
    socket
        .write_all(request.as_bytes())
        .await
        .map_err(|_| "worker_io_error")?;
    let mut reply = Vec::new();
    while reply.len() < 128 {
        let byte = socket.read_u8().await.map_err(|_| "fixture_closed")?;
        reply.push(byte);
        if byte == b'\n' {
            break;
        }
    }
    let reply = std::str::from_utf8(&reply).map_err(|_| "fixture_rejected")?;
    let signature = reply
        .strip_prefix("SWIRL-SYNTHETIC-ACK ")
        .and_then(|reply| reply.strip_suffix('\n'))
        .and_then(key)
        .ok_or("fixture_rejected")?;
    let secret = key(&grant.challenge).ok_or("fixture_rejected")?;
    hmac::verify(
        &hmac::Key::new(hmac::HMAC_SHA256, &secret),
        request.as_bytes(),
        &signature,
    )
    .map_err(|_| "fixture_rejected")?;
    Ok(socket)
}

fn core_probe(grant: &Grant, binding: &Binding, guard: &TcpQuota) -> (&'static str, Option<Value>) {
    let Some(tls) = &grant.tls else {
        return ("core_probe_failed", None);
    };
    let mut controller = crate::Controller::default();
    let call = |controller: &mut crate::Controller, value: Value| {
        controller.dispatch(&serde_json::to_vec(&value).unwrap_or_default())
    };
    let started = call(
        &mut controller,
        json!({"op":"start","config":{
            "schema":1,"listen":"127.0.0.1:0","selected":"synthetic-fixture",
            "nodes":[{"id":"synthetic-fixture","outbound":{"type":"http_connect",
                "host":"127.0.0.1","port":grant.endpoint.port,
                "auth":{"username":"swirl-private-qa","password":grant.challenge},
                "tls":grant.tls_options(tls)}}],
            "inbound_auth":{"username":"swirl-private-qa","password":binding.nonce},
            "limits":{"max_connections":1,"handshake_timeout_ms":grant.timeout_ms}
        }}),
    );
    let Some(handle) = started["handle"].as_u64().filter(|_| started["ok"] == true) else {
        return ("core_probe_failed", None);
    };
    let probe = call(
        &mut controller,
        json!({"op":"probe_start","handle":handle,
        "url":format!("http://qa-origin.fixture.invalid/swirl-private-fixture/{}",binding.nonce),
        "timeout_ms":grant.timeout_ms,"expected_status":204}),
    );
    let result = if probe["ok"] != true {
        ("core_probe_failed", None)
    } else {
        loop {
            let status = call(
                &mut controller,
                json!({"op":"probe_status","handle":handle}),
            );
            if status["ok"] != true {
                break ("core_probe_failed", None);
            }
            if status["probe"]["state"] == "succeeded" {
                let metrics = &status["probe"]["metrics"];
                break (
                    "core_probe_succeeded",
                    Some(json!({
                        "http_status":metrics["http_status"],
                        "outbound_connect_ms":metrics["outbound_connect_ms"],
                        "response_headers_ms":metrics["response_headers_ms"]
                    })),
                );
            }
            if status["probe"]["state"] != "running"
                || guard.snapshot().map_or(true, |receipt| receipt.stopped)
            {
                break ("core_probe_failed", None);
            }
            thread::sleep(Duration::from_millis(5));
        }
    };
    let stopped = call(&mut controller, json!({"op":"stop","handle":handle}));
    if stopped["ok"] != true {
        return ("core_probe_failed", None);
    }
    result
}

/// Read the one grant from private stdio only. There is no CLI/environment
/// grant, arbitrary Core command forwarding, live role or quota reset.
pub fn run() -> Result<()> {
    if std::io::stdin().is_terminal() || std::io::stdout().is_terminal() {
        return Err("PrivateWorkerPrivatePipesRequired");
    }
    let output = Arc::new(Mutex::new(std::io::stdout()));
    let mut input = BufReader::new(std::io::stdin());
    let (message, value) = read_message(&mut input)?.ok_or("PrivateWorkerGrantRequired")?;
    let Message::Grant {
        schema: 1,
        reservation_id,
        nonce,
        plan_digest,
        grant,
    } = message
    else {
        return Err("PrivateWorkerGrantRequired");
    };
    let binding = Binding {
        reservation_id,
        nonce,
        plan_digest,
    };
    grant.validate(&binding, &value)?;
    let guard = budget::install_worker(
        grant.byte_limit,
        grant.connection_limit,
        grant.timeout_ms,
        grant.endpoint(),
    )
    .map_err(|_| "PrivateWorkerQuotaInstall")?;
    let _cancel = CancelOnDrop(Arc::clone(&guard));
    emit(&output, binding.response("ready", &guard)?)?;
    // The installation deadline already runs here. A delayed START never
    // creates a new quota clock; the parent also enforces its earlier deadline.
    loop {
        let (message, _) = read_message(&mut input)?.ok_or("PrivateWorkerStartRequired")?;
        if !binding.accepts(&message) {
            return Err("PrivateWorkerBinding");
        }
        if guard
            .snapshot()
            .map_err(|_| "PrivateWorkerQuotaState")?
            .stopped
        {
            return finish(
                &output,
                &binding,
                &guard,
                false,
                "deadline_expired",
                None,
                None,
            );
        }
        match message {
            Message::Start { .. } => break,
            Message::Snapshot { .. } => emit(&output, binding.response("snapshot", &guard)?)?,
            Message::Cancel { .. } => {
                return finish(&output, &binding, &guard, false, "cancelled", None, None);
            }
            Message::Grant { .. } => return Err("PrivateWorkerDuplicateGrant"),
        }
    }
    let stopped = Arc::new(AtomicU8::new(0));
    let reader_guard = Arc::clone(&guard);
    let reader_stopped = Arc::clone(&stopped);
    let reader_output = Arc::clone(&output);
    let reader_binding = binding.clone();
    thread::Builder::new()
        .name("swirl-private-control".into())
        .spawn(move || {
            control_reader(
                input,
                reader_output,
                reader_binding,
                reader_guard,
                reader_stopped,
            );
        })
        .map_err(|_| "PrivateWorkerControlThread")?;
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .map_err(|_| "PrivateWorkerRuntime")?;
    let mut verified = false;
    let mut billing_snapshot = None;
    let result: Result<()> = runtime.block_on(async {
        let mut socket = authenticate_fixture(&grant).await?;
        verified = true;
        let mut running = binding.response("running", &guard)?;
        running["fixture_verified"] = json!(true);
        emit(&output, running)?;
        match grant.workload {
            Workload::UploadUntilStop => loop {
                socket
                    .write_all(&[0x53; 4096])
                    .await
                    .map_err(|_| "worker_io_error")?;
            },
            Workload::DownloadUntilStop => loop {
                let mut bytes = [0; 4096];
                if socket
                    .read(&mut bytes)
                    .await
                    .map_err(|_| "worker_io_error")?
                    == 0
                {
                    return Err("fixture_closed");
                }
            },
            Workload::StallRuntimeAfterConnect => {
                // Intentional synthetic failure: no Tokio polling or control
                // dispatch can reap this runtime. The independent quota thread
                // may shut down its registered socket; the parent must kill and
                // actually wait for this process. Never emit a success receipt.
                let _socket = socket;
                loop {
                    thread::park();
                }
            }
            Workload::CoreProbe => {
                let _ = socket.shutdown().await;
                Ok(())
            }
            Workload::BillingSnapshot => {
                socket
                    .shutdown()
                    .await
                    .map_err(|_| "billing_snapshot_failed")?;
                drop(socket);
                billing_snapshot = Some(billing::snapshot(&grant).await?);
                Ok(())
            }
        }
    });
    drop(runtime);
    let (mut outcome, metrics) = if grant.workload == Workload::BillingSnapshot {
        (
            if result.is_ok() && billing_snapshot.is_some() {
                "billing_snapshot_succeeded"
            } else {
                "billing_snapshot_failed"
            },
            None,
        )
    } else if result.is_ok() && grant.workload == Workload::CoreProbe {
        core_probe(&grant, &binding, &guard)
    } else {
        let code = match result {
            Err("fixture_rejected") => "fixture_rejected",
            Err("fixture_closed") => "fixture_closed",
            _ => "worker_io_error",
        };
        (code, None)
    };
    let receipt = guard.snapshot().map_err(|_| "PrivateWorkerQuotaState")?;
    outcome = match stopped.load(Ordering::Acquire) {
        CANCELLED => "cancelled",
        PROTOCOL_ERROR => "worker_protocol_error",
        PIPE_ERROR => "worker_io_error",
        _ if receipt.timed_out => "deadline_expired",
        _ if receipt.stopped => "quota_stopped",
        _ => outcome,
    };
    finish(
        &output,
        &binding,
        &guard,
        verified,
        outcome,
        metrics,
        billing_snapshot,
    )
}
