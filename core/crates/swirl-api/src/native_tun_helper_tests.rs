use super::*;

fn spawn_worker(_windows_script: &str, _unix_script: &str) -> Child {
    #[cfg(windows)]
    let mut command = {
        let windows = std::env::var_os("SystemRoot").unwrap();
        let mut command = Command::new(
            std::path::PathBuf::from(windows)
                .join("System32/WindowsPowerShell/v1.0/powershell.exe"),
        );
        command.args([
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _windows_script,
        ]);
        command
    };
    #[cfg(not(windows))]
    let mut command = {
        let mut command = Command::new("/bin/sh");
        command.args(["-c", _unix_script]);
        command
    };
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap()
}

fn ready_reader(child: &mut Child) -> io::BufReader<std::process::ChildStdout> {
    // Synchronize on the actual child instead of including shell startup in
    // the watchdog deadline. The finite child workload also bounds a broken
    // old wait(), so the regression cannot strand a test process.
    let mut ready = String::new();
    let mut output = io::BufReader::new(child.stdout.take().unwrap());
    output.read_line(&mut ready).unwrap();
    assert_eq!(ready.trim_end(), "ready");
    output
}

#[test]
fn stalled_worker_is_terminated_and_reaped_before_recovery_can_run() {
    let mut child = spawn_worker(
        "[Console]::Out.WriteLine('ready'); [Console]::Out.Flush(); [Threading.Thread]::Sleep(2000)",
        "printf 'ready\\n'; sleep 2",
    );
    drop(ready_reader(&mut child));
    let result = wait_for_worker(&mut child, &AtomicU64::new(0), Duration::from_millis(30));
    assert_eq!(result.as_ref().unwrap_err().kind(), io::ErrorKind::TimedOut);
    let (reported, report) = mpsc::channel();
    let mut restored = 0;
    let completed = finish_worker(
        result,
        Ok(thread::spawn(|| Ok(0))),
        || {
            assert!(child.try_wait().unwrap().is_some());
            restored += 1;
            serde_json::json!({"ok":true,"state":"recovered"})
        },
        move |value| {
            reported.send(value.clone()).unwrap();
            Ok(())
        },
        Duration::from_secs(1),
    );
    assert_eq!(completed.unwrap_err().kind(), io::ErrorKind::TimedOut);
    assert_eq!(restored, 1);
    assert_eq!(
        report.recv_timeout(Duration::from_secs(1)).unwrap(),
        serde_json::json!({"ok":true,"state":"recovered","worker_error":"TunWorkerUnresponsive"})
    );
}

#[test]
fn live_control_heartbeats_extend_the_worker_deadline_without_reaching_the_client() {
    let mut child = spawn_worker(
        r#"[Console]::Out.WriteLine('ready'); [Console]::Out.Flush(); 1..10 | ForEach-Object { [Console]::Out.Write('{"native_tun_worker_heartbeat":1}' + [char]10); [Console]::Out.Flush(); [Threading.Thread]::Sleep(100) }; [Console]::Out.WriteLine('{"ok":true}')"#,
        r#"printf 'ready\n'; for i in 1 2 3 4 5 6 7 8 9 10; do printf '{"native_tun_worker_heartbeat":1}\n'; sleep .1; done; printf '{"ok":true}\n'"#,
    );
    let input = ready_reader(&mut child);
    let heartbeat = Arc::new(AtomicU64::new(0));
    let observed = heartbeat.clone();
    let output = thread::spawn(move || {
        let mut response = Vec::new();
        let forwarded = forward_worker_output(input, &mut response, &observed)?;
        Ok::<_, io::Error>((forwarded, response))
    });
    let result = wait_for_worker(&mut child, &heartbeat, Duration::from_millis(600));
    let output = output.join().unwrap().unwrap();
    assert!(result.unwrap());
    let expected = if cfg!(windows) {
        b"{\"ok\":true}\r\n".as_slice()
    } else {
        b"{\"ok\":true}\n".as_slice()
    };
    assert_eq!(
        (heartbeat.load(Ordering::Acquire), output),
        (10, (expected.len() as u64, expected.to_vec()))
    );
}

#[test]
fn private_heartbeat_frame_is_exact_and_normal_response_bytes_are_preserved() {
    let normal =
        b"{\"native_tun_worker_heartbeat\":1,\"ok\":true}\n{\"ok\":false,\"request_id\":\"abc\"}\n";
    let input = [HEARTBEAT_FRAME, normal, HEARTBEAT_FRAME].concat();
    let heartbeat = AtomicU64::new(0);
    let mut output = Vec::new();
    let forwarded = forward_worker_output(io::Cursor::new(input), &mut output, &heartbeat).unwrap();
    assert_eq!(
        (forwarded, heartbeat.load(Ordering::Acquire), output),
        (normal.len() as u64, 2, normal.to_vec())
    );
}

#[test]
fn incomplete_or_oversized_worker_frame_cannot_allocate_indefinitely_or_renew_liveness() {
    for input in [
        b"{\"ok\":true}".to_vec(),
        vec![b'x'; swirl_api::OUTPUT_CAPACITY + 2],
        [vec![b'x'; swirl_api::OUTPUT_CAPACITY + 1], vec![b'\n']].concat(),
    ] {
        let heartbeat = AtomicU64::new(0);
        let mut output = Vec::new();
        let error =
            forward_worker_output(io::Cursor::new(input), &mut output, &heartbeat).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert_eq!((heartbeat.load(Ordering::Acquire), output), (0, Vec::new()));
    }
}
