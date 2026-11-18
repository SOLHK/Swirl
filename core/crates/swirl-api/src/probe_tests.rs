use super::*;
use std::{
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    thread,
    time::{Duration, Instant},
};

fn ffi(command: Value) -> Value {
    let input = serde_json::to_vec(&command).unwrap();
    let mut output = vec![0; OUTPUT_CAPACITY];
    // SAFETY: these separate Vec buffers remain valid for the entire call.
    let count = unsafe {
        swirl_core_command(
            input.as_ptr(),
            input.len(),
            output.as_mut_ptr(),
            output.len(),
        )
    };
    assert!(count > 0, "ABI returned {count}");
    serde_json::from_slice(&output[..count as usize]).unwrap()
}

fn accept_bounded(listener: &TcpListener) -> TcpStream {
    listener.set_nonblocking(true).unwrap();
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        match listener.accept() {
            Ok((peer, _)) => return peer,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                assert!(
                    Instant::now() < deadline,
                    "URL test did not reach loopback peer"
                );
                thread::sleep(Duration::from_millis(5));
            }
            Err(error) => panic!("loopback accept failed: {error}"),
        }
    }
}

fn command(controller: &mut Controller, command: Value) -> Value {
    controller.dispatch(&serde_json::to_vec(&command).unwrap())
}

fn wait_probe(controller: &mut Controller, handle: u64) -> Value {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let status = command(controller, json!({"op":"probe_status","handle":handle}));
        assert_eq!(status["ok"], true);
        if status["probe"]["state"] != "running" {
            return status;
        }
        assert!(Instant::now() < deadline, "physical probe never completed");
        thread::sleep(Duration::from_millis(5));
    }
}

#[test]
fn a_physical_probe_cannot_override_a_routed_core() {
    let mut controller = Controller::default();
    let started = command(
        &mut controller,
        json!({"op":"start","config":{
            "schema":1,"listen":"127.0.0.1:0","selected":"direct",
            "nodes":[{"id":"direct","outbound":{"type":"direct"}}],
            "rules":[{"matcher":{"type":"match"},"outbound":"direct"}]
        }}),
    );
    assert_eq!(started["ok"], true);
    let handle = started["handle"].as_u64().unwrap();
    let result = command(
        &mut controller,
        json!({"op":"probe_start","handle":handle,
        "url":"http://127.0.0.1:9/","physical_egress":true}),
    );
    assert_eq!(result["ok"], false);
    assert_eq!(result["error"], "ProbePhysicalWorkerRequired");
    assert_eq!(
        command(&mut controller, json!({"op":"stop","handle":handle}))["ok"],
        true
    );
}

#[cfg(not(windows))]
#[test]
fn unsupported_physical_probe_never_falls_back_to_an_unbound_request() {
    let mut controller = Controller::default();
    let started = command(
        &mut controller,
        json!({"op":"start","config":{
            "schema":1,"listen":"127.0.0.1:0","selected":"direct",
            "nodes":[{"id":"direct","outbound":{"type":"direct"}}]
        }}),
    );
    assert_eq!(started["ok"], true);
    let handle = started["handle"].as_u64().unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let launched = command(
        &mut controller,
        json!({"op":"probe_start","handle":handle,
        "url":format!("http://{}/",listener.local_addr().unwrap()),"physical_egress":true}),
    );
    assert_eq!(launched["ok"], true);
    let result = wait_probe(&mut controller, handle);
    assert_eq!(result["probe"]["state"], "failed");
    assert_eq!(result["probe"]["failure"]["code"], "ProbeEgressUnsupported");
    assert_eq!(
        listener.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
    assert_eq!(
        command(&mut controller, json!({"op":"stop","handle":handle}))["ok"],
        true
    );
}

#[cfg(windows)]
#[test]
fn windows_physical_probe_completes_configured_dns_and_http_over_bound_sockets() {
    use std::net::{IpAddr, SocketAddr, UdpSocket};
    let physical = swirl_platform::physical_network::physical_probe_interfaces().unwrap();
    let source = physical
        .iter()
        .find(|entry| entry.source.is_ipv4())
        .unwrap()
        .source;
    let origin = TcpListener::bind(SocketAddr::new(source, 0)).unwrap();
    let port = origin.local_addr().unwrap().port();
    let dns = UdpSocket::bind(SocketAddr::new(source, 0)).unwrap();
    dns.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
    let dns_address = dns.local_addr().unwrap();
    let dns_peer = thread::spawn(move || {
        let mut bytes = [0; 2048];
        let (length, remote) = dns.recv_from(&mut bytes).unwrap();
        assert_eq!(remote.ip(), source);
        let question = swirl_dns::decode_query(&bytes[..length]).unwrap();
        assert_eq!(question.name, "physical-probe.fixture.invalid");
        assert_eq!(question.kind, swirl_dns::DNS_A);
        let response = swirl_dns::encode_response(&question, &[source], 30, 0).unwrap();
        dns.send_to(&response, remote).unwrap();
    });
    let http_peer = thread::spawn(move || {
        let mut stream = accept_bounded(&origin);
        assert_eq!(stream.peer_addr().unwrap().ip(), source);
        stream.set_nonblocking(false).unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        let mut request = Vec::new();
        while !request.ends_with(b"\r\n\r\n") {
            let mut byte = [0];
            stream.read_exact(&mut byte).unwrap();
            request.push(byte[0]);
            assert!(request.len() < 8192);
        }
        assert!(request.starts_with(b"HEAD /complete HTTP/1.1\r\n"));
        stream
            .write_all(b"HTTP/1.1 204 No Content\r\n\r\n")
            .unwrap();
    });
    let mut controller = Controller::default();
    let started = command(
        &mut controller,
        json!({"op":"start","config":{
            "schema":1,"listen":"127.0.0.1:0","selected":"direct",
            "nodes":[{"id":"direct","outbound":{"type":"direct"}}],
            "dns":{"servers":[dns_address.to_string()],"query_family":"ipv4_only","use_system_hosts":false}
        }}),
    );
    assert_eq!(started["ok"], true);
    let handle = started["handle"].as_u64().unwrap();
    let launched = command(
        &mut controller,
        json!({"op":"probe_start","handle":handle,
        "url":format!("http://physical-probe.fixture.invalid:{port}/complete"),"physical_egress":true}),
    );
    assert_eq!(launched["ok"], true);
    let result = wait_probe(&mut controller, handle);
    assert_eq!(result["probe"]["state"], "succeeded", "{result}");
    assert_eq!(result["probe"]["metrics"]["http_status"], 204);
    assert!(!result.to_string().contains(&IpAddr::to_string(&source)));
    assert_eq!(
        command(&mut controller, json!({"op":"stop","handle":handle}))["ok"],
        true
    );
    dns_peer.join().unwrap();
    http_peer.join().unwrap();
}

#[test]
fn ffi_probe_starts_without_waiting_for_headers_and_returns_redacted_status() {
    let started = ffi(json!({
        "op":"start",
        "config":{
            "schema":1,"listen":"127.0.0.1:0","selected":"direct",
            "nodes":[{"id":"direct","outbound":{"type":"direct"}}]
        }
    }));
    assert_eq!(started["ok"], true);
    let handle = started["handle"].as_u64().unwrap();
    let invalid = ffi(json!({
        "op":"probe_start","handle":handle,
        "url":"http://user:PRIVATE_FIXTURE@127.0.0.1/"
    }));
    assert_eq!(invalid["ok"], false);
    assert!(!invalid.to_string().contains("PRIVATE_FIXTURE"));

    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!(
        "http://127.0.0.1:{}/check",
        listener.local_addr().unwrap().port()
    );
    let clock = Instant::now();
    let launched = ffi(json!({
        "op":"probe_start","handle":handle,"url":url,"timeout_ms":5000
    }));
    let launch_time = clock.elapsed();
    let while_waiting = ffi(json!({"op":"probe_status","handle":handle}));
    let mut peer = accept_bounded(&listener);
    peer.set_nonblocking(false).unwrap();
    peer.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    let mut request = Vec::new();
    while !request.ends_with(b"\r\n\r\n") {
        let mut byte = [0];
        peer.read_exact(&mut byte).unwrap();
        request.push(byte[0]);
        assert!(request.len() <= 8192);
    }
    peer.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(3);
    let completed = loop {
        let status = ffi(json!({"op":"probe_status","handle":handle}));
        if status["probe"]["state"] != "running" {
            break status;
        }
        assert!(Instant::now() < deadline, "URL test never completed");
        thread::sleep(Duration::from_millis(5));
    };

    let stall = TcpListener::bind("127.0.0.1:0").unwrap();
    let stalled_url = format!(
        "http://127.0.0.1:{}/wait",
        stall.local_addr().unwrap().port()
    );
    let second = ffi(json!({"op":"probe_start","handle":handle,"url":stalled_url}));
    let cancelled = ffi(json!({"op":"probe_cancel","handle":handle}));
    let after_cancel = ffi(json!({"op":"probe_status","handle":handle}));
    let stopped = ffi(json!({"op":"stop","handle":handle}));

    assert!(launch_time < Duration::from_secs(2));
    assert_eq!(launched["ok"], true);
    assert_eq!(launched["probe"]["state"], "running");
    assert_eq!(while_waiting["probe"]["state"], "running");
    assert!(request.starts_with(b"HEAD /check HTTP/1.1\r\n"));
    assert_eq!(completed["probe"]["state"], "succeeded");
    assert_eq!(completed["probe"]["metrics"]["http_status"], 200);
    let timing = &completed["probe"]["metrics"]["outbound_timing"];
    assert!(timing["resolution_us"].is_u64());
    assert!(timing["tcp_dial_us"].is_u64());
    assert!(timing["tcp_connected_attempt_us"].is_u64());
    assert_eq!(timing["tcp_attempts"], 1);
    assert!(timing["proxy_tls_handshake_us"].is_null());
    assert!(timing["quic_handshake_including_tls_us"].is_null());
    assert_eq!(timing["authentication_response_accepted"], false);
    assert_eq!(second["probe"]["state"], "running");
    assert_eq!(cancelled["probe"]["state"], "cancelled");
    assert_eq!(after_cancel["probe"], cancelled["probe"]);
    // Additive, fixed-size timing fields remain bounded and endpoint-free.
    assert!(completed["probe"].to_string().len() < 2048);
    assert!(!completed["probe"].to_string().contains("127.0.0.1"));
    assert_eq!(stopped["ok"], true);
}
