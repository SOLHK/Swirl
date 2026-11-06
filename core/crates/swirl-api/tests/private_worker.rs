//! Real executable/loopback tests. Windows Job ownership is exercised by the
//! separate parent coordinator suite, not claimed by this portable test owner.
use base64::Engine;
use ring::{
    digest, hmac,
    signature::{Ed25519KeyPair, KeyPair},
};
use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Read, Write},
    net::{TcpListener, TcpStream},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{Arc, Mutex, mpsc},
    thread,
    time::{Duration, Instant},
};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio_rustls::{
    TlsAcceptor,
    rustls::{
        ServerConfig,
        pki_types::{CertificateDer, PrivatePkcs8KeyDer},
    },
};

const SECRET: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const NONCE: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const WAIT: Duration = Duration::from_secs(5);

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}
fn unhex(text: &str) -> Vec<u8> {
    text.as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}
fn identity() -> Value {
    let output = Command::new(env!("CARGO_BIN_EXE_swirl-private-worker"))
        .arg("--build-info")
        .output()
        .unwrap();
    assert!(output.status.success());
    serde_json::from_slice(&output.stdout).unwrap()
}
fn seal(plan: &mut Value) {
    plan["plan_digest"] = json!(hex(digest::digest(
        &digest::SHA256,
        &serde_json::to_vec(&plan["grant"]).unwrap()
    )
    .as_ref()));
}
fn plan(listener: &TcpListener, workload: &str, timeout_ms: u32) -> Value {
    let build = identity();
    let connections = if workload == "core_probe" { 2 } else { 1 };
    let mut plan = json!({"schema":1,"op":"grant","reservation_id":"1",
    "nonce":NONCE,"plan_digest":"","grant":{
        "task_id":"swirl-0.2.40-private-acceptance","ledger_id":"c".repeat(64),
        "sequence":1,"source_sha":build["source_sha"],"build_id":build["build_id"],
        "role":"synthetic_loopback","byte_limit":4096,"connection_limit":connections,
        "receive_reservation":connections*1024*1024,"timeout_ms":timeout_ms,
        "endpoint":{"host":"127.0.0.1","port":listener.local_addr().unwrap().port()},
        "challenge":SECRET,"workload":workload,"config_fingerprint":"d".repeat(64),
        "tls":null
    }});
    seal(&mut plan);
    plan
}
fn control(plan: &Value, operation: &str) -> Value {
    json!({"schema":1,"op":operation,"reservation_id":plan["reservation_id"],
        "nonce":plan["nonce"],"plan_digest":plan["plan_digest"]})
}

struct Worker {
    child: Child,
    input: Option<ChildStdin>,
    replies: mpsc::Receiver<Value>,
    errors: Arc<Mutex<String>>,
}
impl Worker {
    fn spawn() -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_swirl-private-worker"))
            .arg("--internal-private-acceptance-worker")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let input = child.stdin.take();
        let output = child.stdout.take().unwrap();
        let error = child.stderr.take().unwrap();
        let (send, replies) = mpsc::channel();
        thread::spawn(move || {
            for line in BufReader::new(output).lines() {
                let Ok(line) = line else {
                    break;
                };
                let value = serde_json::from_str(&line).expect("worker JSON response");
                if send.send(value).is_err() {
                    break;
                }
            }
        });
        let errors = Arc::new(Mutex::new(String::new()));
        let received_errors = Arc::clone(&errors);
        thread::spawn(move || {
            let mut contents = String::new();
            let _ = error.take(16384).read_to_string(&mut contents);
            *received_errors.lock().unwrap() = contents;
        });
        Self {
            child,
            input,
            replies,
            errors,
        }
    }
    fn send(&mut self, value: &Value) {
        let input = self.input.as_mut().unwrap();
        serde_json::to_writer(&mut *input, value).unwrap();
        input.write_all(b"\n").unwrap();
        input.flush().unwrap();
    }
    fn response(&self, operation: &str) -> Value {
        let value = self.replies.recv_timeout(WAIT).unwrap_or_else(|error| {
            panic!(
                "worker response {operation}: {error}; {}",
                self.errors.lock().unwrap()
            )
        });
        assert_eq!(value["op"], operation, "{value}");
        assert!(!value.to_string().contains(SECRET), "fixture secret leaked");
        assert_eq!(value["identity"], identity());
        value
    }
    fn grant(&mut self, plan: &Value) {
        self.send(plan);
        let ready = self.response("ready");
        assert_eq!(ready["plan_digest"], plan["plan_digest"]);
        assert_eq!(ready["guard"]["upload"], 0);
        assert_eq!(ready["guard"]["download"], 0);
        assert_eq!(ready["guard"]["connection_attempts"], 0);
        assert_eq!(ready["guard"]["stopped"], false);
    }
    fn wait(&mut self, success: bool) {
        let deadline = Instant::now() + WAIT;
        loop {
            if let Some(status) = self.child.try_wait().unwrap() {
                assert_eq!(
                    status.success(),
                    success,
                    "{status}: {}",
                    self.errors.lock().unwrap()
                );
                assert!(!self.errors.lock().unwrap().contains(SECRET));
                return;
            }
            assert!(Instant::now() < deadline, "worker did not exit");
            thread::sleep(Duration::from_millis(5));
        }
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn listener() -> TcpListener {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    listener
}
fn accept(listener: &TcpListener) -> TcpStream {
    let deadline = Instant::now() + WAIT;
    loop {
        match listener.accept() {
            Ok((socket, _)) => {
                socket.set_nonblocking(false).unwrap();
                socket.set_read_timeout(Some(WAIT)).unwrap();
                socket.set_write_timeout(Some(WAIT)).unwrap();
                return socket;
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                assert!(Instant::now() < deadline, "fixture never contacted");
                thread::sleep(Duration::from_millis(5));
            }
            Err(error) => panic!("fixture accept: {error}"),
        }
    }
}
fn authenticate(socket: &mut TcpStream, valid: bool) -> usize {
    let mut request = Vec::new();
    loop {
        let mut byte = [0];
        socket.read_exact(&mut byte).unwrap();
        request.push(byte[0]);
        assert!(request.len() < 128);
        if byte[0] == b'\n' {
            break;
        }
    }
    assert!(request.starts_with(b"SWIRL-SYNTHETIC-V1 "));
    assert!(!std::str::from_utf8(&request).unwrap().contains(SECRET));
    let signature = hmac::sign(&hmac::Key::new(hmac::HMAC_SHA256, &unhex(SECRET)), &request);
    let signature = if valid {
        hex(signature.as_ref())
    } else {
        "0".repeat(64)
    };
    socket
        .write_all(format!("SWIRL-SYNTHETIC-ACK {signature}\n").as_bytes())
        .unwrap();
    request.len()
}

#[test]
fn mandatory_build_identity_and_pregrant_transport_are_fail_closed() {
    let build = identity();
    assert_eq!(build["private_worker_schema"], 1);
    assert_eq!(build["guard_mode"], "mandatory_before_grant");
    assert_eq!(build["live"], false);
    policy_child("preguard");
    policy_child("endpoint");
}

fn policy_child(mode: &str) {
    let status = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "policy_fixture_child",
            "--ignored",
            "--nocapture",
        ])
        .env("SWIRL_PRIVATE_POLICY_CASE", mode)
        .status()
        .unwrap();
    assert!(status.success());
}

#[test]
#[ignore = "fresh-process guard state; invoked by the policy parent"]
fn policy_fixture_child() {
    use swirl_transport::egress::budget;
    let allowed = listener();
    let denied = listener();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    match std::env::var("SWIRL_PRIVATE_POLICY_CASE").unwrap().as_str() {
        "preguard" => {
            runtime.block_on(async {
                assert_eq!(
                    swirl_transport::connect_tcp(allowed.local_addr().unwrap())
                        .await
                        .err()
                        .unwrap()
                        .to_string(),
                    "PrivateQuotaWorkerGrantRequired"
                );
                assert!(
                    swirl_transport::bind_udp("127.0.0.1:0".parse().unwrap())
                        .await
                        .is_err()
                );
                assert!(
                    swirl_transport::inbound::bind_tcp("127.0.0.1:0".parse().unwrap()).is_err()
                );
                assert_eq!(
                    swirl_dns::Resolver::default()
                        .resolve("private-qa.fixture.invalid", 80)
                        .await,
                    Err("DnsPrivateMeteredResolverRequired")
                );
            });
            let mut controller = swirl_api::Controller::for_native_tun_helper();
            let command = json!({"native_tun_schema":1,"op":"native_tun_start",
                "request_id":"60000000-0000-4000-8000-000000000001","handle":"1","engine_epoch":"1",
                "config":{"driver_path":"C:\\Swirl\\fixture.dll","adapter_guid":"70000000-0000-4000-8000-000000000001","adapter_name":"Fixture"}});
            assert_eq!(
                controller.dispatch(&serde_json::to_vec(&command).unwrap())["error"],
                "PrivateQuotaUnmeteredDenied"
            );
            let command = json!({"op":"start","config":{"schema":1,"listen":"127.0.0.1:0","selected":"fixture",
                "nodes":[{"id":"fixture","outbound":{"type":"socks5","host":"127.0.0.1","port":9,"auth":null}}]}});
            assert_eq!(
                controller.dispatch(&serde_json::to_vec(&command).unwrap())["error"],
                "PrivateQuotaListenerDenied"
            );
            let node = "10000000-0000-4000-8000-000000000001";
            let command = json!({"control_schema":2,"op":"start_v2",
                "request_id":"50000000-0000-4000-8000-000000000001",
                "store_id":"40000000-0000-4000-8000-000000000001","saved_revision":"1",
                "candidate":{"schema":2,"listen":"127.0.0.1:0",
                    "nodes":[{"id":node,"outbound":{"type":"socks5","host":"127.0.0.1","port":9,"auth":null}}],
                    "policy":{"schema":2,"mode":"global","default_policy":{"id":"policy:default","target":{"kind":"node","id":node}}}}});
            assert_eq!(
                controller.dispatch(&serde_json::to_vec(&command).unwrap())["error"],
                "PrivateQuotaListenerDenied"
            );
            #[cfg(windows)]
            {
                assert_eq!(
                    swirl_api::native_tun_broker::run(Vec::new())
                        .unwrap_err()
                        .to_string(),
                    "PrivateQuotaUnmeteredDenied"
                );
                assert_eq!(
                    swirl_api::native_packet_worker::run()
                        .unwrap_err()
                        .to_string(),
                    "PrivateQuotaUnmeteredDenied"
                );
            }
            assert_eq!(
                budget::install(4096, 1).err().unwrap().to_string(),
                "PrivateQuotaWorkerGrantRequired"
            );
            assert_eq!(
                budget::install_worker(4096, 1, 1000, allowed.local_addr().unwrap())
                    .err()
                    .unwrap()
                    .to_string(),
                "PrivateQuotaLateInstall"
            );
        }
        "endpoint" => {
            let guard =
                budget::install_worker(4096, 1, 1000, allowed.local_addr().unwrap()).unwrap();
            runtime.block_on(async {
                assert_eq!(
                    swirl_transport::connect_tcp(denied.local_addr().unwrap())
                        .await
                        .err()
                        .unwrap()
                        .to_string(),
                    "PrivateQuotaEndpointDenied"
                );
            });
            let receipt = guard.snapshot().unwrap();
            assert_eq!(receipt.upload + receipt.download, 0);
            assert_eq!(receipt.connection_attempts, 1);
            assert!(receipt.stopped);
        }
        _ => panic!("policy fixture mode"),
    }
    assert_eq!(
        allowed.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
    assert_eq!(
        denied.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
}

#[test]
fn grant_is_required_and_cannot_admit_live_or_unowned_addresses() {
    for violation in [
        "no-grant", "role", "endpoint", "digest", "receive", "unknown",
    ] {
        let listener = listener();
        let mut plan = plan(&listener, "upload_until_stop", 2000);
        match violation {
            "no-grant" => plan = control(&plan, "start"),
            "role" => plan["grant"]["role"] = json!("live"),
            "endpoint" => plan["grant"]["endpoint"]["host"] = json!("198.51.100.1"),
            "digest" => plan["grant"]["byte_limit"] = json!(8192),
            "receive" => plan["grant"]["receive_reservation"] = json!(0),
            "unknown" => plan["grant"]["allow_live"] = json!(true),
            _ => unreachable!(),
        }
        if !matches!(violation, "no-grant" | "digest") {
            seal(&mut plan);
        }
        let mut worker = Worker::spawn();
        worker.send(&plan);
        worker.wait(false);
        assert_eq!(
            listener.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
    }
}

#[test]
fn ready_opens_no_socket_and_binding_or_duplicate_grant_never_starts() {
    for violation in ["binding", "grant", "expand"] {
        let listener = listener();
        let plan = plan(&listener, "upload_until_stop", 2000);
        let mut worker = Worker::spawn();
        worker.grant(&plan);
        assert_eq!(
            listener.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
        let mut next = control(&plan, "start");
        match violation {
            "binding" => next["nonce"] = json!("f".repeat(64)),
            "grant" => next = plan.clone(),
            "expand" => next["byte_limit"] = json!(8192),
            _ => unreachable!(),
        }
        worker.send(&next);
        worker.wait(false);
        assert_eq!(
            listener.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
    }
}

#[test]
fn late_start_cannot_reset_the_installation_deadline() {
    let listener = listener();
    let plan = plan(&listener, "upload_until_stop", 50);
    let mut worker = Worker::spawn();
    worker.grant(&plan);
    thread::sleep(Duration::from_millis(90));
    worker.send(&control(&plan, "start"));
    let receipt = worker.response("finished");
    assert_eq!(receipt["outcome"], "deadline_expired");
    assert_eq!(receipt["guard"]["connection_attempts"], 0);
    assert_eq!(receipt["guard"]["timed_out"], true);
    worker.wait(true);
    assert_eq!(
        listener.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
}

#[test]
fn real_upload_and_download_share_the_pre_handshake_byte_limit() {
    for workload in ["upload_until_stop", "download_until_stop"] {
        let listener = listener();
        let plan = plan(&listener, workload, 2000);
        let download = workload == "download_until_stop";
        let peer = thread::spawn(move || {
            let mut socket = accept(&listener);
            let handshake = authenticate(&mut socket, true);
            if download {
                // Writes may enter unread kernel buffers; these are deliberately
                // not relabeled as application-delivered bytes in the receipt.
                let _ = socket.write_all(&[0x52; 65536]);
            }
            let mut received = Vec::new();
            let _ = socket.read_to_end(&mut received);
            handshake + received.len()
        });
        let mut worker = Worker::spawn();
        worker.grant(&plan);
        worker.send(&control(&plan, "start"));
        assert_eq!(worker.response("running")["fixture_verified"], true);
        let receipt = worker.response("finished");
        assert_eq!(receipt["outcome"], "quota_stopped", "{receipt}");
        assert_eq!(
            receipt["guard"]["upload"].as_u64().unwrap()
                + receipt["guard"]["download"].as_u64().unwrap(),
            4096
        );
        assert_eq!(receipt["guard"]["connection_attempts"], 1);
        assert_eq!(receipt["guard"]["receive_reservation"], 1024 * 1024);
        assert_eq!(receipt["guard"]["shutdown_failures"], 0);
        worker.wait(true);
        let received = peer.join().unwrap();
        assert!(received > 0);
        assert!(received as u64 <= receipt["guard"]["upload"].as_u64().unwrap());
    }
}

#[test]
fn wrong_fixture_mac_stops_before_any_workload_bytes() {
    let listener = listener();
    let plan = plan(&listener, "upload_until_stop", 2000);
    let peer = thread::spawn(move || {
        let mut socket = accept(&listener);
        authenticate(&mut socket, false);
        let mut bytes = Vec::new();
        let _ = socket.read_to_end(&mut bytes);
        bytes
    });
    let mut worker = Worker::spawn();
    worker.grant(&plan);
    worker.send(&control(&plan, "start"));
    let receipt = worker.response("finished");
    assert_eq!(receipt["outcome"], "fixture_rejected");
    assert_eq!(receipt["fixture_verified"], false);
    worker.wait(true);
    assert!(peer.join().unwrap().is_empty());
}

#[test]
fn duplicate_start_and_parent_eof_irreversibly_cancel_an_active_socket() {
    for operation in ["start", "grant", "eof"] {
        let listener = listener();
        let plan = plan(&listener, "download_until_stop", 2000);
        let peer = thread::spawn(move || {
            let mut socket = accept(&listener);
            authenticate(&mut socket, true);
            let mut byte = [0];
            match socket.read(&mut byte) {
                Ok(0) => true,
                Err(error) => matches!(
                    error.kind(),
                    std::io::ErrorKind::ConnectionReset | std::io::ErrorKind::ConnectionAborted
                ),
                _ => false,
            }
        });
        let mut worker = Worker::spawn();
        worker.grant(&plan);
        worker.send(&control(&plan, "start"));
        worker.response("running");
        match operation {
            "start" => worker.send(&control(&plan, "start")),
            "grant" => worker.send(&plan),
            "eof" => drop(worker.input.take()),
            _ => unreachable!(),
        }
        let receipt = worker.response("finished");
        assert_eq!(
            receipt["outcome"],
            if operation == "eof" {
                "cancelled"
            } else {
                "worker_protocol_error"
            }
        );
        assert_eq!(receipt["guard"]["stopped"], true);
        worker.wait(true);
        assert!(peer.join().unwrap());
    }
}

#[test]
fn blocked_runtime_loses_its_socket_but_requires_os_process_termination() {
    let listener = listener();
    let plan = plan(&listener, "stall_runtime_after_connect", 300);
    let (closed, observed) = mpsc::channel();
    let peer = thread::spawn(move || {
        let mut socket = accept(&listener);
        authenticate(&mut socket, true);
        let mut byte = [0];
        let closed_socket = match socket.read(&mut byte) {
            Ok(0) => true,
            Err(error) => matches!(
                error.kind(),
                std::io::ErrorKind::ConnectionReset | std::io::ErrorKind::ConnectionAborted
            ),
            _ => false,
        };
        closed.send(closed_socket).unwrap();
    });
    let mut worker = Worker::spawn();
    worker.grant(&plan);
    worker.send(&control(&plan, "start"));
    worker.response("running");
    assert!(
        observed.recv_timeout(Duration::from_secs(2)).unwrap(),
        "independent watchdog did not close the registered socket"
    );
    assert!(
        worker.child.try_wait().unwrap().is_none(),
        "runtime stall unexpectedly exited"
    );
    assert!(
        worker.replies.try_recv().is_err(),
        "stalled runtime must not claim completion"
    );
    worker.child.kill().unwrap();
    assert!(!worker.child.wait().unwrap().success());
    peer.join().unwrap();
}

fn tls_material() -> (Vec<u8>, Vec<u8>, TlsAcceptor) {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../swirl-transport/tests/fixtures/reality_auth.json"
    ))
    .unwrap();
    let certificate = &fixture["certificate"];
    let der = unhex(
        certificate["ordinary_self_signed_der_hex"]
            .as_str()
            .unwrap(),
    );
    let private = unhex(certificate["ed25519_pkcs8_der_hex"].as_str().unwrap());
    let config = ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(
            vec![CertificateDer::from(der.clone())],
            PrivatePkcs8KeyDer::from(private).into(),
        )
        .unwrap();
    // A different, correctly self-signed root with the same subject supplies a
    // valid-but-untrusted CA negative control, not a malformed-DER shortcut.
    let mut wrong = der.clone();
    // This fixture also contains a different minimal REALITY TBS. Extract the
    // ordinary certificate's own DER sequence before signing the alternate CA.
    let sequence = |bytes: &[u8]| {
        assert_eq!(bytes[0], 0x30);
        let (header, length) = if bytes[1] < 128 {
            (2, usize::from(bytes[1]))
        } else {
            let size = usize::from(bytes[1] & 0x7f);
            assert!((1..=2).contains(&size));
            let length = bytes[2..2 + size]
                .iter()
                .fold(0usize, |length, byte| (length << 8) | usize::from(*byte));
            (2 + size, length)
        };
        (header, header + length)
    };
    let (certificate_header, _) = sequence(&der);
    let (_, tbs_length) = sequence(&der[certificate_header..]);
    let tbs_end = certificate_header + tbs_length;
    let mut tbs = der[certificate_header..tbs_end].to_vec();
    let old_public = unhex(certificate["ed25519_public_key_hex"].as_str().unwrap());
    let replacement = Ed25519KeyPair::from_seed_unchecked(&[0x42; 32]).unwrap();
    let at = tbs
        .windows(old_public.len())
        .position(|part| part == old_public)
        .unwrap();
    tbs[at..at + 32].copy_from_slice(replacement.public_key().as_ref());
    wrong[certificate_header..tbs_end].copy_from_slice(&tbs);
    let signature = replacement.sign(&tbs);
    let signature_at = wrong.len() - 64;
    wrong[signature_at..].copy_from_slice(signature.as_ref());
    (der, wrong, TlsAcceptor::from(Arc::new(config)))
}

async fn headers(stream: &mut (impl tokio::io::AsyncRead + Unpin)) -> std::io::Result<String> {
    let mut bytes = Vec::new();
    while bytes.len() < 8192 && !bytes.ends_with(b"\r\n\r\n") {
        bytes.push(stream.read_u8().await?);
    }
    String::from_utf8(bytes).map_err(std::io::Error::other)
}

#[test]
fn core_probe_uses_authenticated_tls_and_rejects_wrong_ca_or_hostname() {
    for negative in ["none", "ca", "hostname"] {
        let listener = listener();
        let (certificate, wrong_ca, acceptor) = tls_material();
        let mut plan = plan(&listener, "core_probe", 8000);
        plan["grant"]["byte_limit"] = json!(65536);
        plan["grant"]["tls"] = json!({
            "server_name":if negative == "hostname" { "wrong.fixture.invalid" } else { "reality.test" },
            "ca_der_base64":base64::engine::general_purpose::STANDARD.encode(if negative == "ca" { wrong_ca } else { certificate })
        });
        seal(&mut plan);
        let peer = thread::spawn(move || {
            let mut first = accept(&listener);
            authenticate(&mut first, true);
            drop(first);
            let socket = accept(&listener);
            socket.set_nonblocking(true).unwrap();
            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap();
            runtime.block_on(async move {
                let io = tokio::net::TcpStream::from_std(socket).unwrap();
                let Ok(Ok(mut tls)) = tokio::time::timeout(WAIT, acceptor.accept(io)).await else {
                    return false;
                };
                let Ok(Ok(connect)) = tokio::time::timeout(WAIT, headers(&mut tls)).await else {
                    return false;
                };
                let authorization = base64::engine::general_purpose::STANDARD
                    .encode(format!("swirl-private-qa:{SECRET}"));
                assert!(connect.starts_with("CONNECT qa-origin.fixture.invalid:80 HTTP/1.1\r\n"));
                assert!(
                    connect.contains(&format!("Proxy-Authorization: Basic {authorization}\r\n"))
                );
                tls.write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    .await
                    .unwrap();
                let request = tokio::time::timeout(WAIT, headers(&mut tls))
                    .await
                    .unwrap()
                    .unwrap();
                assert!(
                    request
                        .starts_with(&format!("HEAD /swirl-private-fixture/{NONCE} HTTP/1.1\r\n"))
                );
                tls.write_all(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n")
                    .await
                    .unwrap();
                tls.flush().await.unwrap();
                true
            })
        });
        let mut worker = Worker::spawn();
        worker.grant(&plan);
        worker.send(&control(&plan, "start"));
        worker.response("running");
        let receipt = worker.response("finished");
        assert_eq!(receipt["fixture_verified"], true);
        assert_eq!(receipt["guard"]["connection_attempts"], 2);
        assert_eq!(
            receipt["outcome"],
            if negative == "none" {
                "core_probe_succeeded"
            } else {
                "core_probe_failed"
            },
            "{receipt}"
        );
        if negative == "none" {
            assert_eq!(receipt["metrics"]["http_status"], 204);
        }
        worker.wait(true);
        assert_eq!(peer.join().unwrap(), negative == "none");
    }
}
