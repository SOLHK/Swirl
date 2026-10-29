//! Explicit Windows helper: private inherited stdio, no network RPC listener,
//! shell command endpoint, GUI elevation, installed service or driver download.
//! A supervisor survives a worker crash and restores owned network journals.
use std::{
    io::{self, BufRead, Write},
    process::{Command, Stdio},
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};

const MAX_COMMAND: usize = 1024 * 1024;
const OUTPUT_DRAIN: Duration = Duration::from_secs(2);
const RECOVER: &[u8] = br#"{"native_tun_schema":1,"request_id":"70000000-0000-4000-8000-000000000001","op":"native_tun_recover"}"#;

fn emit(value: &serde_json::Value) -> io::Result<()> {
    let stdout = io::stdout();
    let mut stdout = stdout.lock();
    writeln!(stdout, "{value}")?;
    stdout.flush()
}

fn recover() -> serde_json::Value {
    swirl_api::Controller::for_native_tun_helper().dispatch(RECOVER)
}

fn main() {
    let mode = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "--capabilities".into());
    if mode == "--capabilities" {
        let _ = emit(&swirl_api::native_tun_control::capabilities());
        return;
    }
    if !cfg!(windows) {
        let _ = emit(&serde_json::json!({"ok":false,"error":"TunWindowsRequired"}));
        std::process::exit(2);
    }
    let result = match mode.as_str() {
        "--recover" => {
            let result = recover();
            let ok = result["ok"].as_bool() == Some(true);
            emit(&result).and_then(|_| {
                if ok {
                    Ok(())
                } else {
                    Err(io::Error::other("TunRecoveryFailed"))
                }
            })
        }
        "--serve" => supervisor(),
        // Internal child endpoint; the normal entry point always supervises it.
        "--worker" => worker(),
        _ => Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "TunHelperArgument",
        )),
    };
    if result.is_err() {
        // A supervisor output thread can still be blocked in a client pipe.
        // Never acquire stdout again on that path: restoration has already run
        // and process exit must be able to terminate the blocked forwarder.
        if mode != "--serve" {
            let _ = emit(&serde_json::json!({"ok":false,"error":"TunHelperStopped"}));
        }
        std::process::exit(1);
    }
}

fn supervisor() -> io::Result<()> {
    let initial = recover();
    if initial["ok"].as_bool() != Some(true) {
        emit(&initial)?;
        return Err(io::Error::other("TunRecoveryRequired"));
    }
    let executable = std::env::current_exe()?;
    let mut child = Command::new(executable)
        .arg("--worker")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()?;
    let output = (|| {
        let mut child_input = child
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("TunHelperStdin"))?;
        let mut child_output = child
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("TunHelperStdout"))?;
        // EOF from the unelevated owner drops the child pipe. If the supervisor
        // itself exits, Windows closes that pipe too and the worker restores state.
        thread::Builder::new()
            .name("swirl-helper-input".into())
            .spawn(move || {
                let _ = io::copy(&mut io::stdin().lock(), &mut child_input);
            })?;
        thread::Builder::new()
            .name("swirl-helper-output".into())
            .spawn(move || io::copy(&mut child_output, &mut io::stdout().lock()))
    })();
    if output.is_err() {
        let _ = child.kill();
    }
    // Neither wait errors nor failed output forwarding may bypass recovery.
    // A failed wait is also a reason to stop the worker, but does not justify
    // returning before attempting to restore any journal whose lock is free.
    let status = child.wait().map(|status| status.success());
    if status.is_err() {
        let _ = child.kill();
    }
    finish_worker(status, output, recover, emit, OUTPUT_DRAIN)
}

fn finish_worker(
    status: io::Result<bool>,
    output: io::Result<thread::JoinHandle<io::Result<u64>>>,
    restore: impl FnOnce() -> serde_json::Value,
    report: impl FnOnce(&serde_json::Value) -> io::Result<()>,
    drain: Duration,
) -> io::Result<()> {
    // Restoring the network is independent of a client's ability to receive
    // stdout. In particular, do this before propagating wait/spawn/copy errors
    // or waiting for a forwarder which may be blocked in WriteFile.
    let recovery = restore();
    let output = output?;
    let deadline = Instant::now() + drain;
    while !output.is_finished() {
        if Instant::now() >= deadline {
            // Dropping JoinHandle detaches; main exits without writing stdout,
            // so an unresponsive consumer cannot keep the helper alive forever.
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "TunHelperOutputBlocked",
            ));
        }
        thread::sleep(Duration::from_millis(10));
    }
    output
        .join()
        .map_err(|_| io::Error::other("TunHelperOutput"))??;
    report(&recovery)?;
    if !status? || recovery["ok"].as_bool() != Some(true) {
        return Err(io::Error::other("TunWorkerOrRecoveryFailed"));
    }
    Ok(())
}

fn worker() -> io::Result<()> {
    let (commands, incoming) = mpsc::sync_channel::<io::Result<Vec<u8>>>(1);
    thread::spawn(move || {
        let stdin = io::stdin();
        let mut input = stdin.lock();
        loop {
            let mut command = Vec::new();
            loop {
                let buffer = match input.fill_buf() {
                    Ok(buffer) => buffer,
                    Err(error) => {
                        let _ = commands.send(Err(error));
                        return;
                    }
                };
                if buffer.is_empty() {
                    return;
                }
                let length = buffer
                    .iter()
                    .position(|byte| *byte == b'\n')
                    .map_or(buffer.len(), |at| at + 1);
                if command.len() + length > MAX_COMMAND {
                    let _ = commands.send(Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "TunCommandSize",
                    )));
                    return;
                }
                command.extend_from_slice(&buffer[..length]);
                input.consume(length);
                if command.ends_with(b"\n") {
                    break;
                }
            }
            if commands.send(Ok(command)).is_err() {
                return;
            }
        }
    });
    let mut controller = swirl_api::Controller::for_native_tun_helper();
    let outcome = loop {
        controller.maintain_native_tun();
        match incoming.recv_timeout(Duration::from_millis(250)) {
            Ok(Ok(command)) => {
                if let Err(error) = emit(&controller.dispatch(&command)) {
                    break Err(error);
                }
            }
            Ok(Err(error)) => break Err(error),
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => break Ok(()),
        }
    };
    // Restore before dropping Core or unloading Wintun. The supervising parent
    // retries any surviving owned journal after this worker has exited.
    controller.stop_native_tunnels().map_err(io::Error::other)?;
    outcome
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn failed_wait_restores_before_blocked_output_and_does_not_report_into_it() {
        let (release, blocked) = mpsc::channel();
        let (writer_done, writer_finished) = mpsc::channel();
        let output = thread::spawn(move || {
            blocked.recv().unwrap();
            writer_done.send(()).unwrap();
            Ok(0)
        });
        let (restored, recovery_seen) = mpsc::channel();
        let (complete, completed) = mpsc::channel();
        let finalizer = thread::spawn(move || {
            let result = finish_worker(
                Err(io::Error::other("simulated wait failure")),
                Ok(output),
                || {
                    restored.send(()).unwrap();
                    serde_json::json!({"ok":true})
                },
                |_| panic!("must not write into a blocked output pipe"),
                Duration::from_millis(30),
            );
            complete.send(result).unwrap();
        });
        let saw_recovery = recovery_seen.recv_timeout(Duration::from_secs(1));
        let result = completed.recv_timeout(Duration::from_secs(1));
        // Unblock and join even if an assertion will fail, so an ordering
        // regression reports a normal test failure instead of hanging cargo.
        release.send(()).unwrap();
        writer_finished
            .recv_timeout(Duration::from_secs(1))
            .unwrap();
        finalizer.join().unwrap();
        saw_recovery.unwrap();
        assert_eq!(result.unwrap().unwrap_err().kind(), io::ErrorKind::TimedOut);
    }

    #[test]
    fn failed_output_forwarding_cannot_bypass_recovery() {
        let output = thread::spawn(|| Err(io::Error::from(io::ErrorKind::BrokenPipe)));
        let mut restored = false;
        let result = finish_worker(
            Ok(false),
            Ok(output),
            || {
                restored = true;
                serde_json::json!({"ok":true})
            },
            |_| panic!("a broken output pipe cannot receive a report"),
            Duration::from_secs(1),
        );
        assert!(restored);
        assert_eq!(result.unwrap_err().kind(), io::ErrorKind::BrokenPipe);
    }
}
