//! Bounded product protocol. OS authentication is separate from this build
//! handshake: a matching role, UUID or build ID never authenticates a process.
use serde::Deserialize;
use serde_json::{Value, json};
use std::io::{self, BufRead, Read};

const FRAME_LIMIT: usize = 1024 * 1024; // Includes the trailing LF.

fn invalid(code: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, code)
}
fn frame(input: &mut impl BufRead) -> io::Result<Option<Vec<u8>>> {
    let mut bytes = Vec::new();
    let count = input
        .take((FRAME_LIMIT + 1) as u64)
        .read_until(b'\n', &mut bytes)?;
    if count == 0 {
        return Ok(None);
    }
    if count > FRAME_LIMIT || !bytes.ends_with(b"\n") {
        return Err(invalid("BrokerFrameLimit"));
    }
    Ok(Some(bytes))
}
fn decode(bytes: &[u8]) -> io::Result<Value> {
    swirl_subscription::parse_json_value(bytes).map_err(|_| invalid("BrokerJsonInvalid"))
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Hello {
    broker_schema: u32,
    op: String,
    request_id: String,
    abi_version: u32,
    build_id: String,
    source_sha: String,
    role: String,
}
fn hello(bytes: &[u8], pid: u32, gui_pid: u32) -> io::Result<Value> {
    let request: Hello =
        serde_json::from_value(decode(bytes)?).map_err(|_| invalid("BrokerHelloInvalid"))?;
    let identity = crate::build_info();
    if request.broker_schema != 1
        || request.op != "hello"
        || request.role != "swirl_gui"
        || swirl_core::v2::identity_uuid(&request.request_id).is_err()
        || request.abi_version != crate::swirl_core_abi_version()
        || identity["build_id"] != request.build_id
        || identity["source_sha"] != request.source_sha
        || request.build_id.len() != 64
        || request.source_sha.len() != 40
        || !request
            .build_id
            .bytes()
            .chain(request.source_sha.bytes())
            .all(|v| v.is_ascii_hexdigit())
    {
        return Err(invalid("BrokerBuildIdentityMismatch"));
    }
    Ok(
        json!({"ok":true,"broker_schema":1,"request_id":request.request_id,
        "role":"swirl_tun_broker","pid":pid,"gui_pid":gui_pid,"identity":identity}),
    )
}

/// Only existing Core control and the native TUN lifecycle enter the
/// privileged helper. Legacy runtimes, gateway setup and worker IPC do not.
fn command(bytes: &[u8]) -> io::Result<Value> {
    let value = decode(bytes)?;
    let object = value
        .as_object()
        .ok_or_else(|| invalid("BrokerCommandInvalid"))?;
    if object.contains_key("broker_schema")
        || object.contains_key("native_gateway_schema")
        || object.contains_key("packet_worker_schema")
    {
        return Err(invalid("BrokerCommandDenied"));
    }
    let op = value["op"]
        .as_str()
        .ok_or_else(|| invalid("BrokerCommandInvalid"))?;
    let allowed = if object.contains_key("native_tun_schema") {
        !object.contains_key("control_schema")
            && value["native_tun_schema"] == 1
            && matches!(
                op,
                "native_tun_validate"
                    | "native_tun_start"
                    | "native_tun_status"
                    | "native_tun_stop"
                    | "native_tun_recover"
            )
    } else if object.contains_key("control_schema") {
        value["control_schema"] == 2
            && matches!(
                op,
                "validate_configuration_v2"
                    | "start_v2"
                    | "prepare_configuration_v2"
                    | "activate_configuration_v2"
                    | "finish_configuration_v2"
                    | "rollback_configuration_v2"
                    | "configuration_status_v2"
                    | "lan_validate"
                    | "lan_start"
                    | "lan_stop"
                    | "lan_status"
            )
    } else {
        matches!(
            op,
            "snapshot" | "probe_start" | "probe_status" | "probe_cancel" | "stop"
        )
    };
    if !allowed {
        return Err(invalid("BrokerCommandDenied"));
    }
    Ok(value)
}

fn supervisor_recovered(value: &Value) -> bool {
    value["request_id"] == crate::native_tun_control::SUPERVISOR_RECOVERY_REQUEST_ID
        && value["native_tun_schema"] == 1
        && value["ok"] == true
        && value["state"] == "recovered"
        && value["active_owners"].as_u64() == Some(0)
}
fn safe_error_code(code: &str) -> Option<&'static str> {
    [
        "BrokerHelperDirectory",
        "BrokerHelperStdin",
        "BrokerHelperStdout",
        "BrokerHelperEof",
        "BrokerHelperExited",
        "BrokerHelperTimeout",
        "BrokerHelperNotReady",
        "BrokerHelperResponseIdentity",
        "BrokerFrameLimit",
        "BrokerJsonInvalid",
        "BrokerResponseInvalid",
        "TunHelperOutputPoisoned",
        "TunHelperOutputClosed",
        "TunHelperOutputBlocked",
        "TunHelperPermission",
        "TunNetworkConflict",
        "TunPhysicalNetworkUnavailable",
        "TunOwnedByAnotherHelper",
        "TunWindowsNetworkOperation",
        "TunJournalDirectory",
        "TunRecoveryJournalInvalid",
        "TunRecoveryJournalIdentity",
        "TunRecoveryFailed",
        "TunRecoveryConflict",
        "TunEgressStillOwned",
        "GatewayCaptureStillOwned",
        "GatewayJournalDirectory",
        "GatewayRecoveryJournalInvalid",
        "GatewayRecoveryJournalIdentity",
        "GatewayHelperPermission",
        "GatewayNetworkConflict",
        "GatewayOwnedByAnotherHelper",
        "GatewayWindowsNetworkOperation",
        "GatewayQuiesceFailed",
        "GatewayQuiesceConflict",
        "GatewayForwardingStillEnabled",
        "GatewayRecoveryFailed",
        "GatewayRecoveryConflict",
    ]
    .into_iter()
    .find(|known| *known == code)
}
fn supervisor_failure(value: &Value) -> Option<&'static str> {
    if value["native_tun_schema"] != 1
        || value["request_id"] != crate::native_tun_control::SUPERVISOR_RECOVERY_REQUEST_ID
        || value["ok"] != false
    {
        return None;
    }
    safe_error_code(value["error"].as_str()?)
        .filter(|code| code.starts_with("Tun") || code.starts_with("Gateway"))
}
fn failure_response(phase: &'static str, error: &io::Error, request: Option<&Value>) -> Value {
    // Errors may contain OS paths or configuration. Expose only this fixed
    // enum list; never turn arbitrary Display text into a protocol field.
    let code = safe_error_code(&error.to_string()).unwrap_or("BrokerOperationFailed");
    let mut response = json!({"ok":false,"broker_schema":1,"broker_phase":phase,"error":code});
    if let Some(code) = error.raw_os_error() {
        response["os_error"] = json!(code);
    }
    if let Some(id) = request.and_then(|request| request["request_id"].as_str())
        && swirl_core::v2::identity_uuid(id).is_ok()
        && id == id.to_ascii_lowercase()
    {
        response["request_id"] = json!(id);
    }
    response
}
fn normalized_driver_path(value: &str) -> Option<String> {
    let value = value.replace('/', "\\");
    let value = value.strip_prefix(r"\\?\").unwrap_or(&value);
    let bytes = value.as_bytes();
    if bytes.len() < 3
        || !bytes[0].is_ascii_alphabetic()
        || bytes[1] != b':'
        || bytes[2] != b'\\'
        || value.contains('\0')
    {
        return None;
    }
    Some(value.to_owned())
}
fn same_bundled_driver(given: &str, trusted: &str) -> bool {
    match (
        normalized_driver_path(given),
        normalized_driver_path(trusted),
    ) {
        (Some(given), Some(trusted)) => given.eq_ignore_ascii_case(&trusted),
        _ => false,
    }
}

#[cfg(windows)]
mod windows {
    use super::*;
    use crate::native_worker_output::BoundedOutput;
    use std::{
        io::{BufReader, Write},
        path::{Component, Path, Prefix},
        process::{Child, Command, Stdio},
        sync::mpsc,
        thread,
        time::{Duration, Instant},
    };
    use swirl_platform::{
        windows_tun_broker::{
            AuthenticatedPipe, LockedFile, hide_helper_window, windows_directory,
        },
        wintun_device::official_driver_sha256,
    };

    fn write_frame(output: &mut impl Write, value: &Value) -> io::Result<()> {
        let mut bytes = serde_json::to_vec(value).map_err(|_| invalid("BrokerResponseInvalid"))?;
        if bytes.len() >= FRAME_LIMIT {
            return Err(invalid("BrokerFrameLimit"));
        }
        bytes.push(b'\n');
        output.write_all(&bytes)?;
        output.flush()
    }
    fn helper_command(path: &Path) -> io::Result<Command> {
        let windows = windows_directory()?;
        let mut components = windows.components();
        let Some(Component::Prefix(prefix)) = components.next() else {
            return Err(invalid("BrokerWindowsDirectory"));
        };
        let system_drive = match (prefix.kind(), components.next()) {
            (Prefix::Disk(letter) | Prefix::VerbatimDisk(letter), Some(Component::RootDir)) => {
                format!("{}:", char::from(letter))
            }
            _ => return Err(invalid("BrokerWindowsDirectory")),
        };
        let system = windows.join("System32");
        let mut process = Command::new(path);
        // No inherited SWIRL_*, PowerShell/.NET preload, PATH or journal-root
        // overrides may enter the privileged Controller or its supervisor.
        process
            .env_clear()
            .env("SystemRoot", &windows)
            .env("WINDIR", &windows)
            // Windows Known Folder lookup expands %SystemDrive% for ProgramData.
            .env("SystemDrive", system_drive)
            .env("PATH", &system)
            .env("ComSpec", system.join("cmd.exe"))
            .current_dir(
                path.parent()
                    .ok_or_else(|| invalid("BrokerHelperDirectory"))?,
            )
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        hide_helper_window(&mut process);
        Ok(process)
    }
    fn package_file(manifest: &Value, name: &str, file: &LockedFile) -> io::Result<()> {
        let files = manifest["files"]
            .as_array()
            .ok_or_else(|| invalid("BrokerManifestInvalid"))?;
        let entries: Vec<_> = files.iter().filter(|v| v["path"] == name).collect();
        if entries.len() != 1 || entries[0]["sha256"].as_str() != Some(file.sha256()?.as_str()) {
            return Err(invalid("BrokerPackageDigestMismatch"));
        }
        Ok(())
    }
    fn verify_package(
        pipe: &AuthenticatedPipe,
    ) -> io::Result<(LockedFile, LockedFile, LockedFile)> {
        let root = &pipe.package_directory;
        let manifest_file = LockedFile::open(&root.join("package-manifest.json"))?;
        let manifest = decode(&manifest_file.read_bounded(4 * 1024 * 1024)?)?;
        let identity = crate::build_info();
        if manifest["schema"] != 1
            || manifest["source_sha"] != identity["source_sha"]
            || manifest["rust"]["build_id"] != identity["build_id"]
            || manifest["rust"]["target"] != identity["target"]
        {
            return Err(invalid("BrokerPackageIdentityMismatch"));
        }
        let helper = LockedFile::open(&root.join("swirl-tun-helper.exe"))?;
        let driver = LockedFile::open(&root.join("wintun.dll"))?;
        package_file(&manifest, "Swirl.exe", &pipe.gui_image)?;
        package_file(&manifest, "swirl-tun-broker.exe", &pipe.broker_image)?;
        package_file(&manifest, "swirl-tun-helper.exe", &helper)?;
        package_file(&manifest, "wintun.dll", &driver)?;
        // Pinned official bytes remain required even if a package manifest is
        // replaced. NativeSession independently repeats its driver verification.
        if driver.sha256()? != official_driver_sha256()? {
            return Err(invalid("BrokerDriverDigestMismatch"));
        }
        Ok((helper, driver, manifest_file))
    }
    fn receive(
        pipe: &AuthenticatedPipe,
        incoming: &mpsc::Receiver<io::Result<Vec<u8>>>,
        timeout: Duration,
    ) -> io::Result<Vec<u8>> {
        let until = Instant::now() + timeout;
        loop {
            pipe.check_alive()?;
            match incoming.recv_timeout(
                Duration::from_millis(100).min(until.saturating_duration_since(Instant::now())),
            ) {
                Ok(value) => return value,
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    return Err(invalid("BrokerHelperExited"));
                }
                Err(mpsc::RecvTimeoutError::Timeout) if Instant::now() >= until => {
                    return Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        "BrokerHelperTimeout",
                    ));
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {}
            }
        }
    }
    fn responses(
        output: impl Read + Send + 'static,
    ) -> io::Result<mpsc::Receiver<io::Result<Vec<u8>>>> {
        let (send, receive) = mpsc::sync_channel(1);
        thread::Builder::new()
            .name("swirl-broker-helper-output".into())
            .spawn(move || {
                let mut output = BufReader::new(output);
                loop {
                    let result = frame(&mut output)
                        .and_then(|value| value.ok_or_else(|| invalid("BrokerHelperEof")));
                    let failed = result.is_err();
                    if send.send(result).is_err() || failed {
                        break;
                    }
                }
            })?;
        Ok(receive)
    }
    fn verify_helper_identity(pipe: &AuthenticatedPipe, path: &Path) -> io::Result<()> {
        let mut child = helper_command(path)?.arg("--build-info").spawn()?;
        drop(child.stdin.take());
        let output = child
            .stdout
            .take()
            .ok_or_else(|| invalid("BrokerHelperStdout"))?;
        let outcome = responses(output)
            .and_then(|input| receive(pipe, &input, Duration::from_secs(10)))
            .and_then(|bytes| decode(&bytes));
        if outcome.is_err() {
            let _ = child.kill();
            let _ = child.wait();
            return outcome.map(|_| ());
        }
        let value = outcome?;
        let expected = crate::build_info();
        if value["role"] != "swirl_tun_helper"
            || ["abi_version", "build_id", "source_sha", "target"]
                .iter()
                .any(|key| value[*key] != expected[*key])
        {
            let _ = child.kill();
            let _ = child.wait();
            return Err(invalid("BrokerHelperBuildMismatch"));
        }
        let until = Instant::now() + Duration::from_secs(2);
        loop {
            if let Some(status) = child.try_wait()? {
                return if status.success() {
                    Ok(())
                } else {
                    Err(invalid("BrokerHelperBuildQueryFailed"))
                };
            }
            if Instant::now() >= until {
                let _ = child.kill();
                let _ = child.wait();
                return Err(invalid("BrokerHelperBuildQueryTimeout"));
            }
            thread::sleep(Duration::from_millis(10));
        }
    }
    struct Helper {
        child: Child,
        input: Option<BoundedOutput>,
        output: mpsc::Receiver<io::Result<Vec<u8>>>,
        closed: bool,
    }
    impl Helper {
        fn start(path: &Path, pipe: &AuthenticatedPipe) -> io::Result<Self> {
            let mut child = helper_command(path)?.arg("--serve").spawn()?;
            let mut stdin = child
                .stdin
                .take()
                .ok_or_else(|| invalid("BrokerHelperStdin"))?;
            let input = Some(BoundedOutput::new(move |value| {
                write_frame(&mut stdin, value)
            })?);
            let output = responses(
                child
                    .stdout
                    .take()
                    .ok_or_else(|| invalid("BrokerHelperStdout"))?,
            )?;
            let mut helper = Self {
                child,
                input,
                output,
                closed: false,
            };
            // This tiny local query fits the stdin pipe even while the existing
            // supervisor is recovering stale state. Wait for readiness before
            // writing a potentially large configuration frame.
            let ready = helper.call(pipe, &json!({"op":"snapshot","handle":0}))?;
            if ready["ok"] != false || ready["error"] != "UnknownHandle" {
                return Err(invalid("BrokerHelperNotReady"));
            }
            Ok(helper)
        }
        fn call(&mut self, pipe: &AuthenticatedPipe, value: &Value) -> io::Result<Value> {
            self.input
                .as_mut()
                .ok_or_else(|| invalid("BrokerHelperStdin"))?
                .write(value.clone(), Duration::from_secs(5))?;
            let response = decode(&receive(pipe, &self.output, Duration::from_secs(310))?)?;
            if let Some(code) = supervisor_failure(&response) {
                return Err(invalid(code));
            }
            let schema = if value.get("native_tun_schema").is_some() {
                Some("native_tun_schema")
            } else if value.get("control_schema").is_some() {
                Some("control_schema")
            } else {
                None
            };
            if let Some(schema) = schema {
                // Existing V2 responses carry receipt/request identity, not an
                // echoed control_schema. Native TUN replies do echo their schema.
                if response["request_id"] != value["request_id"]
                    || (schema == "native_tun_schema" && response[schema] != value[schema])
                    || (schema == "control_schema" && response.get("native_tun_schema").is_some())
                {
                    return Err(invalid("BrokerHelperResponseIdentity"));
                }
            } else if response.get("native_tun_schema").is_some()
                || response.get("control_schema").is_some()
            {
                return Err(invalid("BrokerHelperResponseIdentity"));
            }
            Ok(response)
        }
        fn close(&mut self) -> io::Result<()> {
            if self.closed {
                return Ok(());
            }
            self.closed = true;
            self.input.take();
            let until = Instant::now() + Duration::from_secs(30);
            let mut recovered = false;
            loop {
                while let Ok(Ok(bytes)) = self.output.try_recv() {
                    if let Ok(value) = decode(&bytes) {
                        recovered = supervisor_recovered(&value);
                    }
                }
                if let Some(status) = self.child.try_wait()? {
                    // The last frame can be queued just after try_wait observes
                    // process exit. Drain once more before confirming cleanup.
                    let drain_until = Instant::now() + Duration::from_secs(2);
                    while let Ok(result) = self
                        .output
                        .recv_timeout(drain_until.saturating_duration_since(Instant::now()))
                    {
                        let Ok(bytes) = result else {
                            break;
                        };
                        if let Ok(value) = decode(&bytes) {
                            recovered = supervisor_recovered(&value);
                        }
                        if Instant::now() >= drain_until {
                            break;
                        }
                    }
                    return if status.success() && recovered {
                        Ok(())
                    } else {
                        Err(invalid("BrokerRecoveryNotConfirmed"))
                    };
                }
                if Instant::now() >= until {
                    return Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        "BrokerRecoveryNotConfirmed",
                    ));
                }
                thread::sleep(Duration::from_millis(25));
            }
        }
    }
    impl Drop for Helper {
        fn drop(&mut self) {
            // EOF reaches the existing supervised worker. Never kill this
            // process tree: its supervisor must still restore owned journals.
            let _ = self.close();
        }
    }
    fn fixed_driver(value: &mut Value, driver: &LockedFile) -> io::Result<()> {
        if !matches!(
            value["op"].as_str(),
            Some("native_tun_validate" | "native_tun_start")
        ) {
            return Ok(());
        }
        let given = value["config"]["driver_path"]
            .as_str()
            .ok_or_else(|| invalid("BrokerDriverPathRequired"))?;
        // Compare only strings before any filesystem access: canonicalizing
        // an untrusted UNC/device/reparse path could itself contact that peer.
        if !same_bundled_driver(given, &driver.path().to_string_lossy()) {
            return Err(invalid("BrokerDriverPathDenied"));
        }
        // Only the already locked, verified package path enters NativeSession.
        value["config"]["driver_path"] = json!(driver.path());
        Ok(())
    }
    pub fn run(arguments: Vec<String>) -> io::Result<()> {
        // A helper is a new process and cannot inherit an installed TCP quota.
        swirl_transport::egress::check_unmetered_egress()?;
        if arguments.len() != 4 || arguments[0] != "--pipe" || arguments[2] != "--gui-pid" {
            return Err(invalid("BrokerArguments"));
        }
        let pid = arguments[3]
            .parse()
            .map_err(|_| invalid("BrokerArguments"))?;
        let pipe = AuthenticatedPipe::connect(&arguments[1], pid)?;
        let (helper_file, driver_file, _manifest_file) = verify_package(&pipe)?;
        let mut connection = BufReader::new(pipe);
        let greeting = frame(&mut connection)?.ok_or_else(|| invalid("BrokerHelloEof"))?;
        let reply = hello(&greeting, std::process::id(), pid)?;
        verify_helper_identity(connection.get_ref(), helper_file.path())?;
        write_frame(connection.get_mut(), &reply)?;
        // No recover(), driver load or network write occurs above this point.
        let mut helper = match Helper::start(helper_file.path(), connection.get_ref()) {
            Ok(helper) => helper,
            Err(error) => {
                let _ = write_frame(
                    connection.get_mut(),
                    &failure_response("helper_start", &error, None),
                );
                return Err(error);
            }
        };
        // The helper is running and its image identity was verified. No further
        // path-based resolution happens in this session (commands travel over
        // stdio, payload files stay locked, and the helper re-verifies the
        // official driver digest before loading). Release the ancestor
        // directory locks so an active TUN session no longer blocks unrelated
        // renames/deletions across the install tree.
        connection.get_mut().release_directory_locks();
        loop {
            let Some(bytes) = frame(&mut connection)? else {
                return helper.close();
            };
            let mut request = command(&bytes)?;
            fixed_driver(&mut request, &driver_file)?;
            let response = match helper.call(connection.get_ref(), &request) {
                Ok(response) => response,
                Err(error) => {
                    let _ = write_frame(
                        connection.get_mut(),
                        &failure_response("helper_command", &error, Some(&request)),
                    );
                    return Err(error);
                }
            };
            write_frame(connection.get_mut(), &response)?;
        }
    }
}
#[cfg(windows)]
pub use windows::run;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn framing_rejects_truncation_and_bounds_the_entire_line() {
        for bytes in [vec![b' '; FRAME_LIMIT + 1], vec![b' '; FRAME_LIMIT]] {
            assert!(frame(&mut bytes.as_slice()).is_err());
        }
        assert!(frame(&mut b"{}".as_slice()).is_err());
        assert_eq!(
            frame(&mut b"{}\n".as_slice()).unwrap(),
            Some(b"{}\n".to_vec())
        );
    }
    #[test]
    fn privileged_boundary_rejects_other_control_surfaces_and_duplicate_json() {
        for input in [
            r#"{"op":"start","config":{}}"#,
            r#"{"op":"configure","handle":1}"#,
            r#"{"native_gateway_schema":1,"op":"native_gateway_start"}"#,
            r#"{"native_tun_schema":1,"control_schema":2,"op":"native_tun_recover"}"#,
            r#"{"op":"snapshot","op":"stop","handle":1}"#,
        ] {
            assert!(command(input.as_bytes()).is_err());
        }
        assert!(command(br#"{"op":"snapshot","handle":1}"#).is_ok());
        assert!(command(br#"{"control_schema":2,"op":"start_v2"}"#).is_ok());
    }
    #[test]
    fn build_hello_cannot_authorize_a_different_role_or_identity() {
        let mut value = json!({"broker_schema":1,"op":"hello","request_id":"70000000-0000-4000-8000-000000000001",
            "abi_version":1,"build_id":"0".repeat(64),"source_sha":"0".repeat(40),"role":"swirl_gui"});
        assert!(hello(&serde_json::to_vec(&value).unwrap(), 1, 2).is_err());
        value["role"] = json!("administrator");
        assert!(hello(&serde_json::to_vec(&value).unwrap(), 1, 2).is_err());
    }
    #[test]
    fn failure_reports_redact_arbitrary_errors_and_do_not_invent_request_identity() {
        let private = io::Error::other(r"unreviewed failure at C:\private\configuration.json");
        assert_eq!(
            failure_response("helper_start", &private, None),
            json!({"ok":false,"broker_schema":1,"broker_phase":"helper_start","error":"BrokerOperationFailed"})
        );
        let request = json!({"request_id":"80000000-0000-4000-8000-000000000001"});
        assert_eq!(
            failure_response(
                "helper_command",
                &io::Error::from_raw_os_error(5),
                Some(&request)
            ),
            json!({"ok":false,"broker_schema":1,"broker_phase":"helper_command","error":"BrokerOperationFailed",
                "os_error":5,"request_id":"80000000-0000-4000-8000-000000000001"})
        );
        let invalid_request = json!({"request_id":"not-a-uuid"});
        assert!(
            failure_response("helper_command", &private, Some(&invalid_request))
                .get("request_id")
                .is_none()
        );
    }
    #[test]
    fn only_a_known_supervisor_failure_preserves_a_recovery_error_code() {
        let failure = json!({"native_tun_schema":1,"request_id":crate::native_tun_control::SUPERVISOR_RECOVERY_REQUEST_ID,
            "ok":false,"error":"TunWindowsNetworkOperation"});
        assert_eq!(
            supervisor_failure(&failure),
            Some("TunWindowsNetworkOperation")
        );
        for (key, value) in [
            ("request_id", json!("80000000-0000-4000-8000-000000000001")),
            ("native_tun_schema", json!(2)),
            ("ok", json!(true)),
            ("error", json!("BrokerHelperNotReady")),
            (
                "error",
                json!(r"unreviewed failure at C:\private\configuration.json"),
            ),
        ] {
            let mut unknown = failure.clone();
            unknown[key] = value;
            assert_eq!(supervisor_failure(&unknown), None);
        }
    }
    #[test]
    fn only_the_final_owner_free_recovery_receipt_confirms_cleanup() {
        let valid = json!({"native_tun_schema":1,"request_id":crate::native_tun_control::SUPERVISOR_RECOVERY_REQUEST_ID,
            "ok":true,"state":"recovered","active_owners":0});
        assert!(supervisor_recovered(&valid));
        for (key, value) in [
            ("request_id", json!("80000000-0000-4000-8000-000000000001")),
            ("active_owners", json!(1)),
            ("active_owners", json!("0")),
            ("active_owners", Value::Null),
            ("state", json!("stopped")),
            ("ok", json!(false)),
            ("native_tun_schema", json!(2)),
        ] {
            let mut receipt = valid.clone();
            receipt[key] = value;
            assert!(!supervisor_recovered(&receipt));
        }
    }
    #[test]
    fn driver_path_comparison_never_resolves_untrusted_aliases() {
        let trusted = r"\\?\C:\Swirl\wintun.dll";
        assert!(same_bundled_driver("C:/Swirl/wintun.dll", trusted));
        for given in [
            r"\\server\share\wintun.dll",
            r"\\?\UNC\server\share\wintun.dll",
            r"\\.\C:\Swirl\wintun.dll",
            r"wintun.dll",
            r"C:wintun.dll",
            r"C:\untrusted-junction\wintun.dll",
            r"C:\Swirl\..\Swirl\wintun.dll",
        ] {
            assert!(!same_bundled_driver(given, trusted));
        }
    }
}
