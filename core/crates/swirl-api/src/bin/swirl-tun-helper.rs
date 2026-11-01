//! Explicit Windows helper: private inherited stdio, no network RPC listener,
//! shell command endpoint, GUI elevation, installed service or driver download.
//! A supervisor survives a worker crash and restores owned network journals.
use std::{
    io::{self, BufRead, Read, Write},
    process::{Child, Command, Stdio},
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};

const MAX_COMMAND: usize = 1024 * 1024;
const OUTPUT_DRAIN: Duration = Duration::from_secs(2);
const WORKER_HEARTBEAT_INTERVAL: Duration = Duration::from_secs(1);
// Includes bounded Windows configuration/recovery operations on the worker's
// control thread. This replaces an infinite wait; it does not extend any
// command, socket or test timeout. Heartbeats must come from that control loop,
// not a separate thread which could remain alive while the loop is deadlocked.
const WORKER_STALL: Duration = Duration::from_secs(300);
const HEARTBEAT_FRAME: &[u8] = b"{\"native_tun_worker_heartbeat\":1}\n";
const RECOVER: &[u8] = br#"{"native_tun_schema":1,"request_id":"70000000-0000-4000-8000-000000000001","op":"native_tun_recover"}"#;

fn emit(value: &serde_json::Value) -> io::Result<()> {
    let stdout = io::stdout();
    let mut stdout = stdout.lock();
    writeln!(stdout, "{value}")?;
    stdout.flush()
}

/// Keep a stalled parent pipe from blocking the lifecycle thread indefinitely.
/// There is one writer and at most one queued response; timeout poisons this
/// connection and the worker restores its network state before process exit.
struct BoundedOutput {
    pending: mpsc::SyncSender<serde_json::Value>,
    completed: mpsc::Receiver<io::Result<()>>,
    poisoned: bool,
}

impl BoundedOutput {
    fn new(
        mut write: impl FnMut(&serde_json::Value) -> io::Result<()> + Send + 'static,
    ) -> io::Result<Self> {
        let (pending, input) = mpsc::sync_channel(1);
        let (finished, completed) = mpsc::sync_channel(1);
        thread::Builder::new()
            .name("swirl-helper-response".into())
            .spawn(move || {
                while let Ok(value) = input.recv() {
                    let result = write(&value);
                    let failed = result.is_err();
                    if finished.send(result).is_err() || failed {
                        break;
                    }
                }
            })?;
        Ok(Self {
            pending,
            completed,
            poisoned: false,
        })
    }

    fn write(&mut self, value: serde_json::Value, deadline: Duration) -> io::Result<()> {
        if self.poisoned {
            return Err(io::Error::other("TunHelperOutputPoisoned"));
        }
        let result = (|| {
            self.pending
                .try_send(value)
                .map_err(|_| io::Error::other("TunHelperOutputClosed"))?;
            self.completed
                .recv_timeout(deadline)
                .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "TunHelperOutputBlocked"))?
        })();
        self.poisoned = result.is_err();
        result
    }
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
        "--worker" => worker(false),
        "--supervised-worker" => worker(true),
        _ => Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "TunHelperArgument",
        )),
    };
    if result.is_err() {
        // A supervisor output thread can still be blocked in a client pipe.
        // Never acquire stdout again on that path: restoration has already run
        // and process exit must be able to terminate the blocked forwarder.
        if mode != "--serve" && mode != "--worker" && mode != "--supervised-worker" {
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
        .arg("--supervised-worker")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()?;
    let heartbeat = Arc::new(AtomicU64::new(0));
    let worker_heartbeat = heartbeat.clone();
    let output = (|| {
        let mut child_input = child
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("TunHelperStdin"))?;
        let child_output = child
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
            .spawn(move || {
                forward_worker_output(
                    io::BufReader::new(child_output),
                    io::stdout().lock(),
                    &worker_heartbeat,
                )
            })
    })();
    if output.is_err() {
        let _ = child.kill();
    }
    // Neither wait errors nor failed output forwarding may bypass recovery.
    // A failed wait is also a reason to stop the worker, but does not justify
    // returning before attempting to restore any journal whose lock is free.
    let status = wait_for_worker(&mut child, &heartbeat, WORKER_STALL);
    if status.is_err() {
        let _ = child.kill();
        let _ = child.wait();
    }
    finish_worker(status, output, recover, emit, OUTPUT_DRAIN)
}

fn wait_for_worker(child: &mut Child, heartbeat: &AtomicU64, stall: Duration) -> io::Result<bool> {
    let mut observed = heartbeat.load(Ordering::Acquire);
    let mut progressed = Instant::now();
    loop {
        if let Some(status) = child.try_wait()? {
            return Ok(status.success());
        }
        let current = heartbeat.load(Ordering::Acquire);
        if current != observed {
            observed = current;
            progressed = Instant::now();
        }
        if progressed.elapsed() >= stall {
            child.kill()?;
            child.wait()?;
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "TunWorkerUnresponsive",
            ));
        }
        thread::sleep(Duration::from_millis(100).min(stall.saturating_sub(progressed.elapsed())));
    }
}

/// Heartbeats belong only to the private child stream. Preserve complete normal
/// responses byte-for-byte, without exposing internal frames to the GUI. Bound
/// allocation even if a broken worker never writes a newline.
fn forward_worker_output(
    mut input: impl BufRead,
    mut output: impl Write,
    heartbeat: &AtomicU64,
) -> io::Result<u64> {
    let mut forwarded = 0;
    loop {
        let mut frame = Vec::new();
        let length = (&mut input)
            .take((swirl_api::OUTPUT_CAPACITY + 2) as u64)
            .read_until(b'\n', &mut frame)?;
        if length == 0 {
            return Ok(forwarded);
        }
        if length > swirl_api::OUTPUT_CAPACITY + 1 || !frame.ends_with(b"\n") {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "TunWorkerResponseFrame",
            ));
        }
        if frame == HEARTBEAT_FRAME {
            heartbeat.fetch_add(1, Ordering::Release);
        } else {
            output.write_all(&frame)?;
            output.flush()?;
            forwarded += length as u64;
        }
    }
}

fn finish_worker(
    status: io::Result<bool>,
    output: io::Result<thread::JoinHandle<io::Result<u64>>>,
    restore: impl FnOnce() -> serde_json::Value,
    report: impl FnOnce(&serde_json::Value) -> io::Result<()> + Send + 'static,
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
    // Even after forwarding finishes, the client's pipe may still be full.
    // Bound the final recovery report as well; it must not hold the process up.
    let (reported, report_done) = mpsc::sync_channel(1);
    let mut final_state = recovery.clone();
    let worker_error = match &status {
        Err(error) if error.kind() == io::ErrorKind::TimedOut => Some("TunWorkerUnresponsive"),
        Err(_) => Some("TunWorkerWaitFailed"),
        Ok(false) => Some("TunWorkerFailed"),
        Ok(true) => None,
    };
    if let Some(error) = worker_error {
        final_state["worker_error"] = serde_json::json!(error);
    }
    thread::Builder::new()
        .name("swirl-helper-final-report".into())
        .spawn(move || {
            let _ = reported.send(report(&final_state));
        })?;
    report_done
        .recv_timeout(drain)
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "TunHelperOutputBlocked"))??;
    if !status? || recovery["ok"].as_bool() != Some(true) {
        return Err(io::Error::other("TunWorkerOrRecoveryFailed"));
    }
    Ok(())
}

fn worker(supervised: bool) -> io::Result<()> {
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
    let mut output = BoundedOutput::new(emit)?;
    let mut controller = swirl_api::Controller::for_native_tun_helper();
    let mut heartbeat_at = Instant::now();
    let outcome = loop {
        controller.maintain_native_tun();
        if supervised && Instant::now() >= heartbeat_at {
            if let Err(error) = output.write(
                serde_json::json!({"native_tun_worker_heartbeat":1}),
                OUTPUT_DRAIN,
            ) {
                break Err(error);
            }
            heartbeat_at = Instant::now() + WORKER_HEARTBEAT_INTERVAL;
        }
        match incoming.recv_timeout(Duration::from_millis(250)) {
            Ok(Ok(command)) => {
                if let Err(error) = output.write(controller.dispatch(&command), OUTPUT_DRAIN) {
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
#[path = "../native_tun_helper_tests.rs"]
mod watchdog_tests;

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

    #[test]
    fn blocked_worker_response_times_out_and_cannot_reuse_a_stale_ack() {
        let (release, blocked) = mpsc::channel();
        let (done, finished) = mpsc::channel();
        let mut output = BoundedOutput::new(move |_| {
            blocked.recv().unwrap();
            done.send(()).unwrap();
            Ok(())
        })
        .unwrap();
        let result = output.write(serde_json::json!({"ok":true}), Duration::from_millis(30));
        release.send(()).unwrap();
        finished.recv_timeout(Duration::from_secs(1)).unwrap();
        assert_eq!(result.unwrap_err().kind(), io::ErrorKind::TimedOut);
        assert_eq!(
            output
                .write(serde_json::json!({"next":true}), Duration::from_secs(1))
                .unwrap_err()
                .to_string(),
            "TunHelperOutputPoisoned"
        );
    }

    #[test]
    fn blocked_final_report_cannot_delay_a_completed_network_recovery() {
        let (release, blocked) = mpsc::channel();
        let (done, reported) = mpsc::channel();
        let mut restored = false;
        let result = finish_worker(
            Ok(true),
            Ok(thread::spawn(|| Ok(0))),
            || {
                restored = true;
                serde_json::json!({"ok":true})
            },
            move |_| {
                blocked.recv().unwrap();
                done.send(()).unwrap();
                Ok(())
            },
            Duration::from_millis(30),
        );
        release.send(()).unwrap();
        reported.recv_timeout(Duration::from_secs(1)).unwrap();
        assert!(restored);
        assert_eq!(result.unwrap_err().kind(), io::ErrorKind::TimedOut);
    }
}
