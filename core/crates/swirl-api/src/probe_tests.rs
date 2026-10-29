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
