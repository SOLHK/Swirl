//! One fixed network script per owned interface, retaining loaded CIM modules.
//! Each request still performs fresh ownership/CAS/readback checks. A failed
//! request ends the whole process tree; writes are never automatically retried.
use crate::{
    windows_command::OwnedChild,
    windows_network::{decode_json, system_powershell},
};
use serde::{Deserialize, de::DeserializeOwned};
use std::{
    io::{self, BufRead, BufReader, Read, Write},
    process::{Command, Stdio},
    sync::mpsc::{self, Receiver, SyncSender},
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

const MAX_REQUEST: usize = 64 * 1024;
const MAX_RESPONSE: u64 = 1024 * 1024;

pub(crate) struct NetworkSession {
    child: OwnedChild,
    requests: Option<SyncSender<Vec<u8>>>,
    responses: Option<Receiver<io::Result<Vec<u8>>>>,
    writer: Option<JoinHandle<()>>,
    reader: Option<JoinHandle<()>>,
    stderr: Option<JoinHandle<io::Result<Vec<u8>>>>,
    request_id: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Response<T> {
    request_id: u64,
    result: T,
}

impl NetworkSession {
    pub(crate) fn start(script: &str) -> io::Result<Self> {
        let powershell = system_powershell()?;
        let modules = powershell
            .parent()
            .ok_or_else(|| io::Error::other("missing system PowerShell directory"))?
            .join("Modules");
        let mut command = Command::new(powershell);
        command
            .args([
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ])
            .env("PSModulePath", modules)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let mut child = crate::windows_command::spawn_owned(&mut command)?;
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("missing network stdin"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("missing network stdout"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| io::Error::other("missing network stderr"))?;
        let (requests, input) = mpsc::sync_channel::<Vec<u8>>(1);
        let writer = thread::spawn(move || {
            while let Ok(bytes) = input.recv() {
                if stdin
                    .write_all(&bytes)
                    .and_then(|()| stdin.flush())
                    .is_err()
                {
                    break;
                }
            }
        });
        let (output, responses) = mpsc::sync_channel(1);
        let reader = thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                let mut line = Vec::new();
                let result = reader
                    .by_ref()
                    .take(MAX_RESPONSE + 1)
                    .read_until(b'\n', &mut line)
                    .and_then(|length| {
                        if length == 0 {
                            Err(io::Error::new(
                                io::ErrorKind::UnexpectedEof,
                                "network session closed",
                            ))
                        } else if line.len() as u64 > MAX_RESPONSE || !line.ends_with(b"\n") {
                            Err(io::Error::new(
                                io::ErrorKind::InvalidData,
                                "network response exceeds limit or is truncated",
                            ))
                        } else {
                            Ok(line)
                        }
                    });
                let failed = result.is_err();
                if output.send(result).is_err() || failed {
                    break;
                }
            }
        });
        let stderr = thread::spawn(move || {
            let mut bytes = Vec::new();
            stderr.take(MAX_RESPONSE + 1).read_to_end(&mut bytes)?;
            if bytes.len() as u64 > MAX_RESPONSE {
                return Err(io::Error::other("network error output exceeds limit"));
            }
            Ok(bytes)
        });
        Ok(Self {
            child,
            requests: Some(requests),
            responses: Some(responses),
            writer: Some(writer),
            reader: Some(reader),
            stderr: Some(stderr),
            request_id: 0,
        })
    }

    pub(crate) fn request<T: DeserializeOwned>(
        &mut self,
        input: &serde_json::Value,
        timeout: Duration,
    ) -> io::Result<T> {
        let result = (|| {
            let deadline = Instant::now() + timeout;
            self.request_id += 1;
            let mut bytes = serde_json::to_vec(&serde_json::json!({
                "request_id": self.request_id, "request": input,
            }))
            .map_err(io::Error::other)?;
            if bytes.len() > MAX_REQUEST {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "helper request too large",
                ));
            }
            bytes.push(b'\n');
            self.requests
                .as_ref()
                .ok_or_else(|| io::Error::other("network session ended"))?
                .try_send(bytes)
                .map_err(|_| io::Error::other("network request writer unavailable"))?;
            let line = self
                .responses
                .as_ref()
                .ok_or_else(|| io::Error::other("network session ended"))?
                .recv_timeout(deadline.saturating_duration_since(Instant::now()))
                .map_err(|error| match error {
                    mpsc::RecvTimeoutError::Timeout => io::Error::new(
                        io::ErrorKind::TimedOut,
                        "Windows network operation timed out; recover its journal",
                    ),
                    mpsc::RecvTimeoutError::Disconnected => io::Error::new(
                        io::ErrorKind::UnexpectedEof,
                        "network response reader closed",
                    ),
                })??;
            if Instant::now() >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Windows network operation timed out; recover its journal",
                ));
            }
            let response: Response<T> = decode_json(&line)?;
            if response.request_id != self.request_id {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "network response request identity mismatch",
                ));
            }
            Ok(response.result)
        })();
        result.map_err(|error| {
            let details = self.stop();
            match details {
                Ok(stderr) if !stderr.is_empty() => io::Error::new(
                    error.kind(),
                    format!(
                        "Windows network operation failed: {}; {error}",
                        String::from_utf8_lossy(&stderr).trim()
                    ),
                ),
                Err(cleanup) => io::Error::new(
                    error.kind(),
                    format!("{error}; network session cleanup: {cleanup}"),
                ),
                _ => error,
            }
        })
    }

    fn stop(&mut self) -> io::Result<Vec<u8>> {
        // Close the job before joining any pipe owner, including descendants
        // that inherited stdout. Drop channels to unblock waiting workers.
        let killed = self.child.kill();
        let waited = self.child.wait();
        self.requests.take();
        self.responses.take();
        let writer = self.writer.take().map(|t| t.join());
        let reader = self.reader.take().map(|t| t.join());
        let stderr = self.stderr.take().map(|t| t.join());
        killed?;
        waited?;
        if writer.is_some_and(|r| r.is_err()) || reader.is_some_and(|r| r.is_err()) {
            return Err(io::Error::other("network pipe owner panicked"));
        }
        stderr.map_or(Ok(Vec::new()), |r| {
            r.map_err(|_| io::Error::other("network error reader panicked"))?
        })
    }
}

impl Drop for NetworkSession {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}
