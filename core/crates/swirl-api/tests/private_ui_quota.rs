//! Fresh-process tests of the exact QA DLL ABI and actual Core egress.
//! They are not a Qt/Windows/DPAPI or provider acceptance claim.
use ring::digest;
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    process::Command,
    thread,
    time::{Duration, Instant},
};

fn quota(value: Value) -> Value {
    let input = serde_json::to_vec(&value).unwrap();
    let mut output = vec![0; swirl_api::private_ui_quota::OUTPUT_CAPACITY];
    // SAFETY: both independent vectors remain valid for the full ABI call.
    let size = unsafe {
        swirl_api::private_ui_quota::swirl_private_ui_quota_v1(
            input.as_ptr(),
            input.len(),
            output.as_mut_ptr(),
            output.len(),
        )
    };
    assert!(size > 0, "QA ABI failed: {size}");
    serde_json::from_slice(&output[..size as usize]).unwrap()
}

fn core(value: Value) -> Value {
    let input = serde_json::to_vec(&value).unwrap();
    let mut output = vec![0; swirl_api::OUTPUT_CAPACITY];
    // SAFETY: both independent vectors remain valid for the full ABI call.
    let size = unsafe {
        swirl_api::swirl_core_command(
            input.as_ptr(),
            input.len(),
            output.as_mut_ptr(),
            output.len(),
        )
    };
    assert!(size > 0, "Core ABI failed: {size}");
    serde_json::from_slice(&output[..size as usize]).unwrap()
}

fn seal(grant: &mut Value) {
    grant["plan_digest"] = json!(
        digest::digest(
            &digest::SHA256,
            &serde_json::to_vec(&grant["grant"]).unwrap()
        )
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>()
    );
}

fn grant(endpoint: u16, listener: u16, bytes: u64, timeout: u32) -> Value {
    let identity = quota(json!({"schema":1,"op":"identity"}));
    assert_eq!(identity["role"], "swirl_private_qt_ui");
    assert_eq!(identity["live"], false);
    let mut value = json!({"schema":1,"op":"grant","reservation_id":"1","nonce":"a".repeat(64),"plan_digest":"",
        "grant":{"task_id":"swirl-0.2.40-private-acceptance","ledger_id":"b".repeat(64),"sequence":1,
            "source_sha":identity["source_sha"],"build_id":identity["build_id"],"role":"synthetic_qt_ui","workload":"qt_ui_session",
            "byte_limit":bytes,"connection_limit":3,"receive_reservation":3*1024*1024,"timeout_ms":timeout,
            "endpoint":{"host":"127.0.0.1","port":endpoint},"listener":{"host":"127.0.0.1","port":listener},
            "config_fingerprint":"c".repeat(64)}});
    seal(&mut value);
    value
}

fn command(grant: &Value, op: &str) -> Value {
    json!({"schema":1,"op":op,"reservation_id":grant["reservation_id"],"nonce":grant["nonce"],"plan_digest":grant["plan_digest"]})
}

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .unwrap()
        .local_addr()
        .unwrap()
        .port()
}

fn start_core(endpoint: u16, listener: u16) -> Value {
    core(
        json!({"op":"start","config":{"schema":1,"listen":format!("127.0.0.1:{listener}"),"selected":"fixed-fixture",
        "nodes":[{"id":"fixed-fixture","outbound":{"type":"socks5","host":"127.0.0.1","port":endpoint,
            "auth":{"username":"fixture","password":"synthetic-only"}}}],
        "limits":{"max_connections":3,"handshake_timeout_ms":1500}}}),
    )
}

fn read_exact(peer: &mut TcpStream, count: usize) -> Vec<u8> {
    let mut bytes = vec![0; count];
    peer.read_exact(&mut bytes).unwrap();
    bytes
}

fn serve_request(mut peer: TcpStream) {
    peer.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    peer.set_write_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    let hello = read_exact(&mut peer, 2);
    assert_eq!(hello[0], 5);
    let methods = read_exact(&mut peer, usize::from(hello[1]));
    assert!(methods.contains(&2));
    peer.write_all(&[5, 2]).unwrap();
    let auth = read_exact(&mut peer, 2);
    assert_eq!(auth[0], 1);
    assert_eq!(read_exact(&mut peer, usize::from(auth[1])), b"fixture");
    let count = read_exact(&mut peer, 1)[0];
    assert_eq!(read_exact(&mut peer, usize::from(count)), b"synthetic-only");
    peer.write_all(&[1, 0]).unwrap();
    let header = read_exact(&mut peer, 4);
    assert_eq!(&header[..3], &[5, 1, 0]);
    match header[3] {
        1 => {
            read_exact(&mut peer, 4);
        }
        3 => {
            let count = read_exact(&mut peer, 1)[0];
            assert_eq!(
                read_exact(&mut peer, usize::from(count)),
                b"qa-origin.fixture.invalid"
            );
        }
        _ => panic!("unexpected synthetic target address kind"),
    }
    assert_eq!(read_exact(&mut peer, 2), [0, 80]);
    peer.write_all(&[5, 0, 0, 1, 127, 0, 0, 1, 0, 80]).unwrap();
    let mut request = Vec::new();
    while !request.ends_with(b"\r\n\r\n") {
        request.extend(read_exact(&mut peer, 1));
        assert!(request.len() < 8192);
    }
    assert!(request.starts_with(b"HEAD ") || request.starts_with(b"GET "));
    peer.write_all(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        .unwrap();
}

fn accept(listener: &TcpListener) -> TcpStream {
    listener.set_nonblocking(true).unwrap();
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        match listener.accept() {
            Ok((peer, _)) => return peer,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                assert!(Instant::now() < deadline, "actual Core did not connect");
                thread::sleep(Duration::from_millis(2));
            }
            Err(e) => panic!("fixture accept: {e}"),
        }
    }
}

fn probe(handle: &Value) -> Value {
    assert_eq!(
        core(
            json!({"op":"probe_start","handle":handle,"url":"http://qa-origin.fixture.invalid/probe","timeout_ms":1500,"expected_status":204})
        )["ok"],
        true
    );
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let response = core(json!({"op":"probe_status","handle":handle}));
        assert_eq!(response["ok"], true);
        if response["probe"]["state"] != "running" {
            return response;
        }
        assert!(Instant::now() < deadline, "probe did not retire");
        thread::sleep(Duration::from_millis(3));
    }
}

fn case(name: &str) {
    let fixture = TcpListener::bind("127.0.0.1:0").unwrap();
    let endpoint = fixture.local_addr().unwrap().port();
    let listener = free_port();
    if name == "no_grant" {
        assert_eq!(start_core(endpoint, listener)["ok"], false);
        return;
    }
    let bytes = if name == "quota" { 31 } else { 65536 };
    let mut plan = grant(
        endpoint,
        listener,
        bytes,
        if name == "expired_start" { 100 } else { 3000 },
    );
    if name == "identity_mismatch" {
        plan["grant"]["source_sha"] = json!("f".repeat(40));
        seal(&mut plan);
        assert_eq!(quota(plan)["ok"], false);
        assert_eq!(start_core(endpoint, listener)["ok"], false);
        return;
    }
    let ready = quota(plan.clone());
    assert_eq!(ready["op"], "ready");
    assert_eq!(ready["guard"]["connection_attempts"], 0);
    if name == "before_start" {
        assert_eq!(start_core(endpoint, listener)["ok"], false);
        assert_eq!(quota(command(&plan, "start"))["ok"], false);
        return;
    }
    if name == "expired_start" {
        thread::sleep(Duration::from_millis(140));
        assert_eq!(quota(command(&plan, "start"))["ok"], false);
        let state = quota(command(&plan, "snapshot"));
        assert_eq!(state["guard"]["timed_out"], true);
        return;
    }
    assert_eq!(quota(command(&plan, "start"))["op"], "started");
    if name == "repeated_start" {
        assert_eq!(quota(command(&plan, "start"))["ok"], false);
        assert_eq!(quota(command(&plan, "snapshot"))["guard"]["stopped"], true);
        return;
    }
    assert_eq!(quota(command(&plan, "fixture_ready"))["op"], "running");
    if name == "endpoint_denied" {
        let other = TcpListener::bind("127.0.0.1:0").unwrap();
        other.set_nonblocking(true).unwrap();
        let started = start_core(other.local_addr().unwrap().port(), listener);
        assert_eq!(started["ok"], true);
        assert_eq!(probe(&started["handle"])["probe"]["state"], "failed");
        assert_eq!(
            other.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
        assert_eq!(
            core(json!({"op":"stop","handle":started["handle"]}))["ok"],
            true
        );
        let final_state = quota(command(&plan, "finish"));
        assert_eq!(final_state["guard"]["stopped"], true);
        assert_eq!(final_state["guard"]["upload"], 0);
        return;
    }
    let server = thread::spawn(move || {
        if bytes == 31 {
            let mut peer = accept(&fixture);
            peer.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
            let hello = read_exact(&mut peer, 2);
            read_exact(&mut peer, usize::from(hello[1]));
            peer.write_all(&[5, 2]).unwrap();
            let auth = read_exact(&mut peer, 2);
            assert_eq!(auth[0], 1);
            let username = read_exact(&mut peer, usize::from(auth[1]));
            assert_eq!(username, b"fixture");
            let count = read_exact(&mut peer, 1)[0];
            let password = read_exact(&mut peer, usize::from(count));
            assert_eq!(password, b"synthetic-only");
            peer.write_all(&[1, 0]).unwrap();
            let mut received = Vec::new();
            let _ = peer.read_to_end(&mut received);
            assert!(
                received.len() + 2 + usize::from(hello[1]) + 3 + username.len() + password.len()
                    <= 31
            );
        } else {
            serve_request(accept(&fixture));
            serve_request(accept(&fixture));
        }
    });
    let started = start_core(endpoint, listener);
    assert_eq!(started["ok"], true, "{started}");
    let status = probe(&started["handle"]);
    if bytes == 31 {
        assert_eq!(status["probe"]["state"], "failed");
    } else {
        assert_eq!(status["probe"]["state"], "succeeded", "{status}");
        let mut peer = TcpStream::connect(("127.0.0.1", listener)).unwrap();
        peer.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
        peer.write_all(b"GET http://qa-origin.fixture.invalid/normal HTTP/1.1\r\nHost: qa-origin.fixture.invalid\r\nConnection: close\r\n\r\n").unwrap();
        let mut response = String::new();
        peer.read_to_string(&mut response).unwrap();
        assert!(response.starts_with("HTTP/1.1 204"));
    }
    assert_eq!(
        core(json!({"op":"stop","handle":started["handle"]}))["ok"],
        true
    );
    server.join().unwrap();
    let finished = quota(command(&plan, "finish"));
    assert_eq!(finished["op"], "finished");
    assert_eq!(finished["scope"], "synthetic-qt-ui-raw-tcp-v1");
    assert_eq!(finished["raw_tcp_quota_exercised"], true);
    assert_eq!(finished["fixture_verified"], true);
    assert_eq!(finished["guard"]["stopped"], true);
    assert_eq!(finished["guard"]["shutdown_failures"], 0);
    assert!(finished["guard"]["upload"].as_u64().unwrap() > 0);
    assert!(finished["guard"]["download"].as_u64().unwrap() > 0);
    if bytes == 31 {
        assert_eq!(finished["outcome"], "quota_stopped");
        assert_eq!(
            finished["guard"]["upload"].as_u64().unwrap()
                + finished["guard"]["download"].as_u64().unwrap(),
            31
        );
    } else {
        assert_eq!(finished["guard"]["connection_attempts"], 2);
    }
}

#[test]
#[ignore = "private fresh-process entry; parent cases invoke this explicitly"]
fn isolated_ui_quota_case() {
    case(&std::env::var("SWIRL_PRIVATE_UI_QUOTA_TEST_CASE").expect("parent case"));
}

fn run(name: &str) {
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "isolated_ui_quota_case",
            "--ignored",
            "--nocapture",
        ])
        .env("SWIRL_PRIVATE_UI_QUOTA_TEST_CASE", name)
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(8);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            assert!(status.success(), "case {name} failed");
            return;
        }
        if Instant::now() >= deadline {
            child.kill().unwrap();
            child.wait().unwrap();
            panic!("case {name} exceeded bound");
        }
        thread::sleep(Duration::from_millis(5));
    }
}

#[test]
fn no_grant_cannot_start_actual_core() {
    run("no_grant");
}
#[test]
fn installed_grant_cannot_start_core_before_start() {
    run("before_start");
}
#[test]
fn source_mismatch_cannot_install_or_start_core() {
    run("identity_mismatch");
}
#[test]
fn start_does_not_renew_expired_installation_deadline() {
    run("expired_start");
}
#[test]
fn duplicate_start_permanently_stops_the_same_guard() {
    run("repeated_start");
}
#[test]
fn core_probe_and_normal_proxy_share_actual_raw_tcp_counters() {
    run("positive");
}
#[test]
fn same_actual_core_path_stops_at_31_raw_bytes() {
    run("quota");
}
#[test]
fn another_loopback_listener_cannot_receive_core_egress() {
    run("endpoint_denied");
}
