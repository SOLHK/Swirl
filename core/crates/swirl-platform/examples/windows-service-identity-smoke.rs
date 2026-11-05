//! Explicit disposable SCM identity proof. No driver, routing or DNS writes.
//! Optional `--scoped-wfp` verifies only this copied image and one loopback
//! endpoint. It is neither a product kill switch nor a low-integrity Core proof.
#[cfg(not(windows))]
fn main() {
    eprintln!("WindowsRequired");
    std::process::exit(2);
}

#[cfg(windows)]
fn main() {
    if let Err(error) = windows::run() {
        eprintln!("service identity smoke failed: {error}");
        std::process::exit(1);
    }
}

#[cfg(windows)]
#[allow(unsafe_code)] // Private, explicitly acknowledged disposable SCM fixture.
mod windows {
    use serde::{Deserialize, Serialize};
    use sha2::{Digest, Sha256};
    use std::{
        ffi::c_void,
        fs::{File, OpenOptions},
        io::{self, Read, Write},
        mem::{offset_of, size_of},
        net::{SocketAddr, TcpListener, TcpStream},
        os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle},
        path::{Path, PathBuf},
        process::{Child, Command, Stdio},
        ptr::{null, null_mut},
        sync::{
            OnceLock,
            atomic::{AtomicBool, AtomicPtr, Ordering},
        },
        thread,
        time::{Duration, Instant},
    };
    use swirl_platform::windows_restricted_worker::current_token_profile;
    use swirl_platform::windows_wfp::{Action, Engine, Protocol, ScopedPolicy, ScopedRule};
    use windows_sys::{
        Win32::{
            Foundation::*,
            Security::{Authorization::*, *},
            System::{Rpc::UuidCreate, Services::*, Threading::*},
        },
        core::GUID,
    };

    const WAIT: Duration = Duration::from_secs(20);
    // winsvc.h / SERVICE_SID_INFO: omitted from windows-sys 0.61 metadata.
    const SERVICE_SID_TYPE_RESTRICTED: u32 = 0x0000_0003;
    const MAX_FILE: u64 = 64 * 1024;
    const SERVICE_SDDL: &str =
        "O:BAG:BAD:P(A;;0x000f01ff;;;SY)(A;;0x000f01ff;;;BA)(A;;0x00020005;;;BU)(A;;RC;;;OW)";
    static SETTINGS: OnceLock<Receipt> = OnceLock::new();
    static STOP: AtomicBool = AtomicBool::new(false);
    static STATUS: AtomicPtr<c_void> = AtomicPtr::new(null_mut());

    fn check(value: bool, message: &str) -> io::Result<()> {
        if value {
            Ok(())
        } else {
            Err(io::Error::other(message))
        }
    }
    fn sdk(value: i32, operation: &str) -> io::Result<()> {
        if value != 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        Err(io::Error::new(
            error.kind(),
            format!("{operation}: sdk_code={:?}; {error}", error.raw_os_error()),
        ))
    }
    fn wide(text: &str) -> Vec<u16> {
        text.encode_utf16().chain(Some(0)).collect()
    }
    fn local_path(path: &Path) -> io::Result<String> {
        let value = path
            .to_str()
            .ok_or_else(|| io::Error::other("fixture path is not UTF-8"))?;
        check(
            path.is_absolute() && !value.contains(['\0', '"']) && !value.starts_with("\\\\"),
            "requires a local absolute fixture path",
        )?;
        Ok(value.into())
    }
    fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> io::Result<T> {
        let mut bytes = Vec::new();
        File::open(path)?
            .take(MAX_FILE + 1)
            .read_to_end(&mut bytes)?;
        check(bytes.len() as u64 <= MAX_FILE, "fixture JSON exceeds bound")?;
        serde_json::from_slice(&bytes).map_err(io::Error::other)
    }
    fn write_json(path: &Path, value: &impl Serialize, fresh: bool) -> io::Result<()> {
        let bytes = serde_json::to_vec_pretty(value).map_err(io::Error::other)?;
        check(bytes.len() as u64 <= MAX_FILE, "fixture JSON exceeds bound")?;
        let mut options = OpenOptions::new();
        options.write(true);
        if fresh {
            options.create_new(true);
        } else {
            options.truncate(true);
        }
        let mut file = options.open(path)?;
        file.write_all(&bytes)?;
        file.sync_all()
    }
    fn hash(path: &Path) -> io::Result<String> {
        let mut file = File::open(path)?;
        let mut hash = Sha256::new();
        let mut buffer = [0; 16 * 1024];
        loop {
            let count = file.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            hash.update(&buffer[..count]);
        }
        Ok(format!("{:x}", hash.finalize()))
    }
    struct Local(*mut c_void);
    impl Drop for Local {
        fn drop(&mut self) {
            unsafe {
                LocalFree(self.0);
            }
        }
    }
    fn descriptor(sddl: &str) -> io::Result<Local> {
        let mut raw = null_mut();
        sdk(
            unsafe {
                ConvertStringSecurityDescriptorToSecurityDescriptorW(
                    wide(sddl).as_ptr(),
                    SDDL_REVISION_1,
                    &mut raw,
                    null_mut(),
                )
            },
            "ConvertStringSecurityDescriptor",
        )?;
        Ok(Local(raw))
    }
    fn protect_file(
        path: &Path,
        service: Option<&str>,
        write: bool,
        directory: bool,
    ) -> io::Result<()> {
        let inheritance = if directory { "OICI" } else { "" };
        let extra = service
            .map(|sid| {
                format!(
                    "(A;{inheritance};{};;;{sid})",
                    if write { "GRGW" } else { "GRGX" }
                )
            })
            .unwrap_or_default();
        let sd = descriptor(&format!(
            "O:BAG:BAD:P(A;{inheritance};FA;;;SY)(A;{inheritance};FA;;;BA)(A;{inheritance};GRGX;;;BU){extra}(A;;RC;;;OW)"
        ))?;
        let mut owner = null_mut();
        let mut dacl = null_mut();
        let (mut defaulted, mut present) = (0, 0);
        sdk(
            unsafe { GetSecurityDescriptorOwner(sd.0, &mut owner, &mut defaulted) },
            "GetSecurityDescriptorOwner",
        )?;
        sdk(
            unsafe { GetSecurityDescriptorDacl(sd.0, &mut present, &mut dacl, &mut defaulted) },
            "GetSecurityDescriptorDacl",
        )?;
        let code = unsafe {
            SetNamedSecurityInfoW(
                wide(&local_path(path)?).as_ptr(),
                SE_FILE_OBJECT,
                OWNER_SECURITY_INFORMATION
                    | DACL_SECURITY_INFORMATION
                    | PROTECTED_DACL_SECURITY_INFORMATION,
                owner,
                null_mut(),
                dacl,
                null(),
            )
        };
        if code != 0 {
            return Err(io::Error::from_raw_os_error(code as i32));
        }
        Ok(())
    }
    fn canonical_sd(raw: *mut c_void) -> io::Result<String> {
        let mut text = null_mut();
        sdk(
            unsafe {
                ConvertSecurityDescriptorToStringSecurityDescriptorW(
                    raw,
                    SDDL_REVISION_1,
                    OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                    &mut text,
                    null_mut(),
                )
            },
            "ConvertSecurityDescriptorToString",
        )?;
        let allocation = Local(text.cast());
        let mut length = 0;
        while unsafe { *text.add(length) } != 0 {
            length += 1;
            check(length <= 8192, "security descriptor string exceeds bound")?;
        }
        let value = String::from_utf16(unsafe { std::slice::from_raw_parts(text, length) })
            .map_err(io::Error::other);
        drop(allocation);
        value
    }

    #[derive(Clone, Serialize, Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Receipt {
        schema: u32,
        nonce: String,
        name: String,
        directory: PathBuf,
        image: PathBuf,
        image_sha256: String,
        endpoint: SocketAddr,
    }
    impl Receipt {
        fn command(&self) -> io::Result<String> {
            Ok(format!(
                "\"{}\" --service {} \"{}\" {}",
                local_path(&self.image)?,
                self.name,
                local_path(&self.directory)?,
                self.nonce
            ))
        }
        fn validate(&self) -> io::Result<()> {
            check(
                self.schema == 1
                    && self.nonce.len() == 32
                    && self.nonce.bytes().all(|b| b.is_ascii_hexdigit())
                    && self.name == format!("SwirlIdentitySmoke-{}", self.nonce),
                "invalid owned service identity",
            )?;
            check(
                self.image == self.directory.join("identity-worker.exe")
                    && self.endpoint.ip().is_loopback()
                    && self.endpoint.port() != 0,
                "invalid owned service scope",
            )?;
            self.command()?;
            check(
                hash(&self.image)? == self.image_sha256,
                "owned service image changed",
            )
        }
        fn account(&self) -> String {
            format!("NT SERVICE\\{}", self.name)
        }
    }

    // Keep the scoped WFP receipt separate from SCM recovery. Both retain
    // exact ownership; deleting a service must not orphan persistent filters.
    fn scoped_policy(receipt: &Receipt, principal: &str) -> io::Result<ScopedPolicy> {
        let mut owner = [0; 16];
        check(receipt.nonce.len() == 32, "invalid scoped WFP owner nonce")?;
        for (byte, pair) in owner
            .iter_mut()
            .zip(receipt.nonce.as_bytes().as_chunks::<2>().0)
        {
            *byte = u8::from_str_radix(std::str::from_utf8(pair).map_err(io::Error::other)?, 16)
                .map_err(io::Error::other)?;
        }
        let policy = ScopedPolicy {
            schema: 2,
            owner,
            application: receipt.image.clone(),
            sublayer_weight: 0,
            rules: vec![
                ScopedRule {
                    endpoint: receipt.endpoint,
                    protocol: Protocol::Tcp,
                    action: Action::Block,
                    service_sid: None,
                },
                ScopedRule {
                    endpoint: receipt.endpoint,
                    protocol: Protocol::Tcp,
                    action: Action::SoftPermit,
                    service_sid: Some(principal.into()),
                },
            ],
        };
        policy.validate()?;
        Ok(policy)
    }
    fn verify_policy_binding(
        receipt: &Receipt,
        policy: &ScopedPolicy,
        principal: &str,
    ) -> io::Result<()> {
        let mut expected = scoped_policy(receipt, principal)?;
        expected.sublayer_weight = policy.sublayer_weight;
        check(
            serde_json::to_value(&expected).map_err(io::Error::other)?
                == serde_json::to_value(policy).map_err(io::Error::other)?,
            "scoped WFP receipt differs from owned image/endpoint/identity",
        )
    }
    fn owned_policy(receipt: &Receipt) -> io::Result<ScopedPolicy> {
        let policy: ScopedPolicy = read_json(&receipt.directory.join("wfp-receipt.json"))?;
        // The journal is a claim to verify, never the authority for its own
        // principal. Resolve the account from the exact owned SCM service name.
        let expected = service_sid(&receipt.name)?;
        verify_policy_binding(receipt, &policy, &sid_string(expected.0)?)?;
        Ok(policy)
    }
    struct OwnedWfp {
        engine: Option<Engine>,
        policy: ScopedPolicy,
    }
    impl OwnedWfp {
        fn install(&mut self, receipt: &Receipt) -> io::Result<()> {
            let engine = self
                .engine
                .as_mut()
                .ok_or_else(|| io::Error::other("WFP engine closed"))?;
            let mut transaction = engine.begin()?;
            transaction.prepare_policy_weight(&mut self.policy)?;
            // Durable write-ahead ownership precedes the first BFE write.
            write_json(
                &receipt.directory.join("wfp-receipt.json"),
                &self.policy,
                false,
            )?;
            transaction.install(&self.policy)?;
            transaction.commit()?;
            engine.verify(&self.policy)
        }
        fn cleanup(&mut self) -> io::Result<()> {
            if let Some(engine) = self.engine.as_mut()
                && !engine.absent(&self.policy)?
            {
                let mut transaction = engine.begin()?;
                transaction.remove(&self.policy)?;
                transaction.commit()?;
                check(
                    engine.absent(&self.policy)?,
                    "owned scoped WFP removal is incomplete",
                )?;
            }
            if let Some(engine) = self.engine.take() {
                engine.close()?;
            }
            Ok(())
        }
    }
    impl Drop for OwnedWfp {
        fn drop(&mut self) {
            if let Err(error) = self.cleanup() {
                eprintln!("owned scoped WFP cleanup failed; use --recover: {error}");
            }
        }
    }

    struct Impersonation;
    impl Impersonation {
        fn enter(token: HANDLE) -> io::Result<Self> {
            let mut raw = null_mut();
            sdk(
                unsafe { DuplicateToken(token, SecurityImpersonation, &mut raw) },
                "DuplicateToken socket negative control",
            )?;
            let token = unsafe { OwnedHandle::from_raw_handle(raw) };
            sdk(
                unsafe { SetThreadToken(null(), token.as_raw_handle()) },
                "SetThreadToken socket negative control",
            )?;
            Ok(Self)
        }
        fn revert(self) -> io::Result<()> {
            let result = sdk(
                unsafe { RevertToSelf() },
                "RevertToSelf socket negative control",
            );
            // A failed explicit revert must be retried by Drop, never ignored.
            if result.is_ok() {
                std::mem::forget(self);
            }
            result
        }
    }
    impl Drop for Impersonation {
        fn drop(&mut self) {
            if unsafe { RevertToSelf() } == 0 {
                // Continuing as the wrong principal is not a recovery strategy.
                eprintln!(
                    "RevertToSelf socket control failed: {}",
                    io::Error::last_os_error()
                );
                std::process::abort();
            }
        }
    }
    fn effective_socket_identity(
        expected: PSID,
        impersonated: bool,
    ) -> io::Result<serde_json::Value> {
        let token = if impersonated {
            let mut raw = null_mut();
            sdk(
                unsafe { OpenThreadToken(GetCurrentThread(), TOKEN_QUERY, 1, &mut raw) },
                "OpenThreadToken socket negative control",
            )?;
            unsafe { OwnedHandle::from_raw_handle(raw) }
        } else {
            token(
                unsafe { GetCurrentProcess() },
                TOKEN_QUERY,
                "OpenProcessToken socket control",
            )?
        };
        let mut identity = principal_report(token.as_raw_handle(), expected)?;
        let elevation = Buffer::query(|data, bytes, needed| unsafe {
            GetTokenInformation(
                token.as_raw_handle(),
                TokenElevation,
                data.cast(),
                bytes,
                needed,
            )
        })?;
        identity["elevated"] =
            serde_json::json!(elevation.value::<TOKEN_ELEVATION>()?.TokenIsElevated != 0);
        identity["thread_impersonated"] = serde_json::json!(impersonated);
        Ok(identity)
    }
    fn socket_observation(endpoint: SocketAddr, request: &[u8]) -> serde_json::Value {
        let result = (|| {
            let mut stream = TcpStream::connect_timeout(&endpoint, Duration::from_secs(3))?;
            stream.set_read_timeout(Some(Duration::from_secs(3)))?;
            stream.set_write_timeout(Some(Duration::from_secs(3)))?;
            let local = stream.local_addr()?;
            stream.write_all(request)?;
            let mut reply = [0; 3];
            stream.read_exact(&mut reply)?;
            check(&reply == b"ok\n", "negative socket control reply differs")?;
            Ok::<_, io::Error>(local)
        })();
        match result {
            Ok(local) => {
                serde_json::json!({"echo_succeeded":true,"local":local,"socket_error":null})
            }
            Err(error) => {
                serde_json::json!({"echo_succeeded":false,"socket_error":error.raw_os_error(),"error":error.to_string()})
            }
        }
    }
    fn negative_probe(receipt: &Receipt, phase: &str) -> io::Result<()> {
        check(
            matches!(phase, "before" | "blocked" | "after"),
            "invalid negative probe phase",
        )?;
        let policy = owned_policy(receipt)?;
        let expected = sid(policy.rules[1].service_sid.as_deref().unwrap())?;
        let original = token(
            unsafe { GetCurrentProcess() },
            TOKEN_QUERY | TOKEN_DUPLICATE,
            "OpenProcessToken copied-image negative source",
        )?;
        let standard = negative_token(original.as_raw_handle(), None)?;
        let forged = negative_token(original.as_raw_handle(), Some(expected.0))?;
        let mut observations = Vec::new();
        for (kind, token) in [
            ("administrator", None),
            ("standard_effective_token", Some(&standard)),
            ("forged_restricting_sid", Some(&forged)),
        ] {
            let impersonation = token
                .map(|value| Impersonation::enter(value.as_raw_handle()))
                .transpose()?;
            let identity = effective_socket_identity(expected.0, impersonation.is_some())?;
            let observation =
                socket_observation(receipt.endpoint, format!("{phase}:{kind}\n").as_bytes());
            if let Some(impersonation) = impersonation {
                impersonation.revert()?;
            }
            observations
                .push(serde_json::json!({"kind":kind,"identity":identity,"socket":observation}));
        }
        // Persist observations before the parent validates them. A failed socket
        // assertion must preserve the actual error rather than a success marker.
        write_json(
            &receipt.directory.join(format!("wfp-negative-{phase}.json")),
            &serde_json::json!({"nonce":receipt.nonce,"phase":phase,"image_sha256":receipt.image_sha256,"observations":observations}),
            true,
        )
    }
    struct ProbeChild(Child);
    impl Drop for ProbeChild {
        fn drop(&mut self) {
            if !matches!(self.0.try_wait(), Ok(Some(_))) {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }
    }
    fn validate_probe(
        report: &serde_json::Value,
        receipt: &Receipt,
        phase: &str,
        accepted: &[String],
    ) -> io::Result<()> {
        check(
            report["nonce"] == receipt.nonce
                && report["phase"] == phase
                && report["image_sha256"] == receipt.image_sha256,
            "copied-image socket probe identity differs",
        )?;
        let observations = report["observations"]
            .as_array()
            .ok_or_else(|| io::Error::other("socket observations absent"))?;
        let kinds = [
            "administrator",
            "standard_effective_token",
            "forged_restricting_sid",
        ];
        check(
            observations.len() == kinds.len(),
            "socket observation count differs",
        )?;
        for (index, kind) in kinds.iter().enumerate() {
            let value = &observations[index];
            check(
                value["kind"] == *kind
                    && value["identity"]["normal_principal_matches"] == false
                    && value["identity"]["restricted_principal_matches"] == (index == 2)
                    && value["identity"]["thread_impersonated"] == (index != 0)
                    && value["identity"]["elevated"] == (index == 0),
                "socket control effective identity differs",
            )?;
            let socket = &value["socket"];
            check(
                if phase == "blocked" {
                    socket["echo_succeeded"] == false && socket["socket_error"] == 10013
                } else {
                    socket["echo_succeeded"] == true && socket["socket_error"].is_null()
                },
                &format!("{phase}/{kind} actual socket observation differs: {socket}"),
            )?;
        }
        let mut expected = if phase == "blocked" {
            Vec::new()
        } else {
            kinds
                .iter()
                .map(|kind| format!("{phase}:{kind}\n"))
                .collect::<Vec<_>>()
        };
        expected.sort();
        let mut actual = accepted.to_vec();
        actual.sort();
        check(
            actual == expected,
            "origin accepted unexpected socket control traffic",
        )
    }
    fn run_negative_probe(
        receipt: &Receipt,
        phase: &str,
        listener: &TcpListener,
    ) -> io::Result<serde_json::Value> {
        let child = Command::new(&receipt.image)
            .arg("--wfp-negative")
            .arg(&receipt.directory)
            .arg(&receipt.nonce)
            .arg(phase)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::inherit())
            .spawn()?;
        let mut child = ProbeChild(child);
        let deadline = Instant::now() + WAIT;
        let mut accepted = Vec::new();
        let mut peers = Vec::new();
        let result = (|| {
            loop {
                while let Some((mut stream, peer)) = match listener.accept() {
                    Ok(value) => Some(value),
                    Err(error) if error.kind() == io::ErrorKind::WouldBlock => None,
                    Err(error) => return Err(error),
                } {
                    check(
                        accepted.len() < 4 && peer.ip().is_loopback(),
                        "negative control origin scope/count differs",
                    )?;
                    stream.set_read_timeout(Some(Duration::from_secs(3)))?;
                    stream.set_write_timeout(Some(Duration::from_secs(3)))?;
                    let mut request = Vec::new();
                    loop {
                        let mut byte = [0];
                        stream.read_exact(&mut byte)?;
                        request.push(byte[0]);
                        check(request.len() <= 96, "socket control request exceeds bound")?;
                        if byte[0] == b'\n' {
                            break;
                        }
                    }
                    accepted.push(String::from_utf8(request).map_err(io::Error::other)?);
                    peers.push(peer);
                    stream.write_all(b"ok\n")?;
                }
                if let Some(status) = child.0.try_wait()? {
                    check(
                        status.success(),
                        &format!("copied-image socket probe exited: {status}"),
                    )?;
                    break;
                }
                check(
                    Instant::now() < deadline,
                    "copied-image socket probe exceeded bounded deadline",
                )?;
                thread::sleep(Duration::from_millis(10));
            }
            read_json::<serde_json::Value>(
                &receipt.directory.join(format!("wfp-negative-{phase}.json")),
            )
        })();
        // Record origin observations even if the child did not write a report.
        let diagnostics = write_json(
            &receipt.directory.join(format!("wfp-origin-{phase}.json")),
            &serde_json::json!({"phase":phase,"accepted":accepted,"peers":peers}),
            true,
        );
        let report = combine(result, diagnostics)?;
        validate_probe(&report, receipt, phase, &accepted)?;
        Ok(report)
    }
    struct ServiceHandle(SC_HANDLE);
    impl Drop for ServiceHandle {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe {
                    CloseServiceHandle(self.0);
                }
            }
        }
    }
    fn scm(create: bool) -> io::Result<ServiceHandle> {
        let raw = unsafe {
            OpenSCManagerW(
                null(),
                null(),
                SC_MANAGER_CONNECT | if create { SC_MANAGER_CREATE_SERVICE } else { 0 },
            )
        };
        if raw.is_null() {
            return Err(io::Error::last_os_error());
        }
        Ok(ServiceHandle(raw))
    }
    struct Buffer {
        words: Vec<usize>,
        bytes: usize,
    }
    impl Buffer {
        fn query(mut query: impl FnMut(*mut u8, u32, *mut u32) -> i32) -> io::Result<Self> {
            let mut bytes = 0;
            let result = query(null_mut(), 0, &mut bytes);
            let error = io::Error::last_os_error();
            check(
                result == 0
                    && matches!(error.raw_os_error(), Some(24 | 122))
                    && bytes != 0
                    && u64::from(bytes) <= MAX_FILE,
                "SDK query size failed",
            )?;
            let mut result = Self {
                words: vec![0; (bytes as usize).div_ceil(size_of::<usize>())],
                bytes: bytes as usize,
            };
            sdk(
                query(result.words.as_mut_ptr().cast(), bytes, &mut bytes),
                "SDK query",
            )?;
            check(
                bytes as usize <= result.bytes,
                "SDK query exceeded allocation",
            )?;
            result.bytes = bytes as usize;
            Ok(result)
        }
        fn value<T>(&self) -> io::Result<&T> {
            check(self.bytes >= size_of::<T>(), "SDK record truncated")?;
            Ok(unsafe { &*self.words.as_ptr().cast::<T>() })
        }
        fn string(&self, pointer: *const u16) -> io::Result<String> {
            let start = pointer as usize;
            let base = self.words.as_ptr() as usize;
            check(
                start >= base && start < base + self.bytes && start.is_multiple_of(2),
                "SDK string outside allocation",
            )?;
            let units =
                unsafe { std::slice::from_raw_parts(pointer, (base + self.bytes - start) / 2) };
            let end = units
                .iter()
                .position(|value| *value == 0)
                .ok_or_else(|| io::Error::other("SDK string not terminated"))?;
            String::from_utf16(&units[..end]).map_err(io::Error::other)
        }
    }
    struct OwnedService {
        manager: ServiceHandle,
        service: Option<ServiceHandle>,
        receipt: Receipt,
        deleted: bool,
        configured: bool,
    }
    impl OwnedService {
        fn open(receipt: Receipt, create: bool) -> io::Result<Self> {
            receipt.validate()?;
            let manager = scm(create)?;
            let name = wide(&receipt.name);
            let raw = if create {
                unsafe {
                    CreateServiceW(
                        manager.0,
                        name.as_ptr(),
                        name.as_ptr(),
                        SERVICE_ALL_ACCESS,
                        SERVICE_WIN32_OWN_PROCESS,
                        SERVICE_DEMAND_START,
                        SERVICE_ERROR_NORMAL,
                        wide(&receipt.command()?).as_ptr(),
                        null(),
                        null_mut(),
                        null(),
                        wide(&receipt.account()).as_ptr(),
                        null(),
                    )
                }
            } else {
                unsafe { OpenServiceW(manager.0, name.as_ptr(), SERVICE_ALL_ACCESS) }
            };
            if raw.is_null() {
                return Err(io::Error::last_os_error());
            }
            Ok(Self {
                manager,
                service: Some(ServiceHandle(raw)),
                receipt,
                deleted: false,
                configured: !create,
            })
        }
        fn handle(&self) -> SC_HANDLE {
            self.service.as_ref().expect("live owned service").0
        }
        fn verify_config(&self) -> io::Result<()> {
            let buffer = Buffer::query(|data, bytes, needed| unsafe {
                QueryServiceConfigW(self.handle(), data.cast(), bytes, needed)
            })?;
            let config = buffer.value::<QUERY_SERVICE_CONFIGW>()?;
            check(
                config.dwServiceType == SERVICE_WIN32_OWN_PROCESS
                    && config.dwStartType == SERVICE_DEMAND_START
                    && config.dwErrorControl == SERVICE_ERROR_NORMAL
                    && buffer.string(config.lpBinaryPathName)? == self.receipt.command()?
                    && buffer
                        .string(config.lpServiceStartName)?
                        .eq_ignore_ascii_case(&self.receipt.account()),
                "owned service configuration differs",
            )
        }
        fn configure(&mut self) -> io::Result<()> {
            self.verify_config()?;
            let sid = SERVICE_SID_INFO {
                dwServiceSidType: SERVICE_SID_TYPE_RESTRICTED,
            };
            sdk(
                unsafe {
                    ChangeServiceConfig2W(
                        self.handle(),
                        SERVICE_CONFIG_SERVICE_SID_INFO,
                        (&sid as *const SERVICE_SID_INFO).cast(),
                    )
                },
                "ChangeServiceConfig2 SID",
            )?;
            let mut privileges = wide("SeChangeNotifyPrivilege");
            privileges.push(0);
            let required = SERVICE_REQUIRED_PRIVILEGES_INFOW {
                pmszRequiredPrivileges: privileges.as_mut_ptr(),
            };
            sdk(
                unsafe {
                    ChangeServiceConfig2W(
                        self.handle(),
                        SERVICE_CONFIG_REQUIRED_PRIVILEGES_INFO,
                        (&required as *const SERVICE_REQUIRED_PRIVILEGES_INFOW).cast(),
                    )
                },
                "ChangeServiceConfig2 privileges",
            )?;
            let sd = descriptor(SERVICE_SDDL)?;
            sdk(
                unsafe {
                    SetServiceObjectSecurity(
                        self.handle(),
                        OWNER_SECURITY_INFORMATION
                            | DACL_SECURITY_INFORMATION
                            | PROTECTED_DACL_SECURITY_INFORMATION,
                        sd.0,
                    )
                },
                "SetServiceObjectSecurity",
            )?;
            self.verify_security()?;
            self.configured = true;
            Ok(())
        }
        fn verify_security(&self) -> io::Result<()> {
            self.verify_config()?;
            let sid = Buffer::query(|data, bytes, needed| unsafe {
                QueryServiceConfig2W(
                    self.handle(),
                    SERVICE_CONFIG_SERVICE_SID_INFO,
                    data,
                    bytes,
                    needed,
                )
            })?;
            check(
                sid.value::<SERVICE_SID_INFO>()?.dwServiceSidType == SERVICE_SID_TYPE_RESTRICTED,
                "service restricted-SID configuration differs",
            )?;
            let privileges = Buffer::query(|data, bytes, needed| unsafe {
                QueryServiceConfig2W(
                    self.handle(),
                    SERVICE_CONFIG_REQUIRED_PRIVILEGES_INFO,
                    data,
                    bytes,
                    needed,
                )
            })?;
            let list = privileges
                .value::<SERVICE_REQUIRED_PRIVILEGES_INFOW>()?
                .pmszRequiredPrivileges;
            check(
                privileges.string(list)? == "SeChangeNotifyPrivilege",
                "required service privilege differs",
            )?;
            let end = unsafe { list.add("SeChangeNotifyPrivilege".len() + 1) };
            check(
                privileges.string(end)?.is_empty(),
                "additional service privileges configured",
            )?;
            let security = Buffer::query(|data, bytes, needed| unsafe {
                QueryServiceObjectSecurity(
                    self.handle(),
                    OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                    data.cast(),
                    bytes,
                    needed,
                )
            })?;
            check(
                canonical_sd(security.words.as_ptr().cast_mut().cast())?
                    == canonical_sd(descriptor(SERVICE_SDDL)?.0)?,
                "service owner/protected DACL differs",
            )
        }
        fn status(&self) -> io::Result<SERVICE_STATUS_PROCESS> {
            let mut result = SERVICE_STATUS_PROCESS::default();
            let mut bytes = 0;
            sdk(
                unsafe {
                    QueryServiceStatusEx(
                        self.handle(),
                        SC_STATUS_PROCESS_INFO,
                        (&mut result as *mut SERVICE_STATUS_PROCESS).cast(),
                        size_of::<SERVICE_STATUS_PROCESS>() as u32,
                        &mut bytes,
                    )
                },
                "QueryServiceStatusEx",
            )?;
            check(
                bytes as usize == size_of::<SERVICE_STATUS_PROCESS>(),
                "service status size differs",
            )?;
            Ok(result)
        }
        fn wait(&self, desired: u32) -> io::Result<SERVICE_STATUS_PROCESS> {
            let deadline = Instant::now() + WAIT;
            loop {
                let status = self.status()?;
                if status.dwCurrentState == desired {
                    return Ok(status);
                }
                check(
                    desired != SERVICE_RUNNING || status.dwCurrentState != SERVICE_STOPPED,
                    &format!(
                        "service exited before running: win32={} specific={}",
                        status.dwWin32ExitCode, status.dwServiceSpecificExitCode
                    ),
                )?;
                check(
                    Instant::now() < deadline,
                    "service status deadline exceeded",
                )?;
                thread::sleep(Duration::from_millis(25));
            }
        }
        fn stop(&self) -> io::Result<()> {
            if self.deleted {
                return Ok(());
            }
            if self.service.is_some() {
                if self.configured {
                    self.verify_security()?;
                } else {
                    self.verify_config()?;
                }
                if self.status()?.dwCurrentState != SERVICE_STOPPED {
                    let mut status = SERVICE_STATUS::default();
                    let stopped =
                        unsafe { ControlService(self.handle(), SERVICE_CONTROL_STOP, &mut status) };
                    if stopped == 0
                        && io::Error::last_os_error().raw_os_error()
                            != Some(ERROR_SERVICE_NOT_ACTIVE as i32)
                    {
                        return Err(io::Error::last_os_error());
                    }
                    self.wait(SERVICE_STOPPED)?;
                }
            }
            Ok(())
        }
        fn cleanup(&mut self) -> io::Result<()> {
            if self.deleted {
                return Ok(());
            }
            self.stop()?;
            if self.service.is_some() {
                sdk(
                    unsafe { DeleteService(self.handle()) },
                    "DeleteService exact owned service",
                )?;
                drop(self.service.take());
            }
            let deadline = Instant::now() + WAIT;
            loop {
                let raw = unsafe {
                    OpenServiceW(
                        self.manager.0,
                        wide(&self.receipt.name).as_ptr(),
                        SERVICE_QUERY_STATUS,
                    )
                };
                if raw.is_null() {
                    let error = io::Error::last_os_error();
                    if error.raw_os_error() == Some(ERROR_SERVICE_DOES_NOT_EXIST as i32) {
                        self.deleted = true;
                        return Ok(());
                    }
                    if error.raw_os_error() != Some(ERROR_SERVICE_MARKED_FOR_DELETE as i32) {
                        return Err(error);
                    }
                } else {
                    drop(ServiceHandle(raw));
                }
                check(
                    Instant::now() < deadline,
                    "owned service remained after DeleteService",
                )?;
                thread::sleep(Duration::from_millis(25));
            }
        }
    }
    impl Drop for OwnedService {
        fn drop(&mut self) {
            if let Err(error) = self.cleanup() {
                eprintln!(
                    "owned SCM cleanup incomplete; preserve {}: {error}",
                    self.receipt.directory.display()
                );
            }
        }
    }

    fn token(process: HANDLE, access: u32, operation: &str) -> io::Result<OwnedHandle> {
        let mut raw = null_mut();
        sdk(
            unsafe { OpenProcessToken(process, access, &mut raw) },
            operation,
        )?;
        Ok(unsafe { OwnedHandle::from_raw_handle(raw) })
    }
    fn sid(text: &str) -> io::Result<Local> {
        let mut raw = null_mut();
        sdk(
            unsafe { ConvertStringSidToSidW(wide(text).as_ptr(), &mut raw) },
            "ConvertStringSidToSid",
        )?;
        Ok(Local(raw))
    }
    fn service_sid(name: &str) -> io::Result<Local> {
        let account = wide(&format!("NT SERVICE\\{name}"));
        let (mut bytes, mut domain, mut kind) = (0, 0, 0);
        unsafe {
            LookupAccountNameW(
                null(),
                account.as_ptr(),
                null_mut(),
                &mut bytes,
                null_mut(),
                &mut domain,
                &mut kind,
            );
        }
        check(
            bytes > 0 && bytes <= 128 && domain <= 1024,
            "service SID lookup size invalid",
        )?;
        let mut storage = vec![0usize; (bytes as usize).div_ceil(size_of::<usize>())];
        let raw = storage.as_mut_ptr().cast();
        let mut domain_text = vec![0; domain as usize];
        sdk(
            unsafe {
                LookupAccountNameW(
                    null(),
                    account.as_ptr(),
                    raw,
                    &mut bytes,
                    domain_text.as_mut_ptr(),
                    &mut domain,
                    &mut kind,
                )
            },
            "LookupAccountName service",
        )?;
        sid(&sid_string(raw)?)
    }
    fn sid_string(raw: PSID) -> io::Result<String> {
        let mut text = null_mut();
        sdk(
            unsafe { ConvertSidToStringSidW(raw, &mut text) },
            "ConvertSidToStringSid",
        )?;
        let allocation = Local(text.cast());
        let mut count = 0;
        while unsafe { *text.add(count) } != 0 {
            count += 1;
            check(count <= 256, "SID string exceeds bound")?;
        }
        let value = String::from_utf16(unsafe { std::slice::from_raw_parts(text, count) })
            .map_err(io::Error::other);
        drop(allocation);
        value
    }
    fn access_matches(token: HANDLE, principal: &str) -> io::Result<bool> {
        let sd = descriptor(&format!("O:SYG:SYD:P(A;;0x1;;;{principal})"))?;
        let mut impersonation = null_mut();
        sdk(
            unsafe { DuplicateToken(token, SecurityImpersonation, &mut impersonation) },
            "DuplicateToken impersonation",
        )?;
        let impersonation = unsafe { OwnedHandle::from_raw_handle(impersonation) };
        let mapping = GENERIC_MAPPING {
            GenericRead: 1,
            GenericWrite: 1,
            GenericExecute: 1,
            GenericAll: 1,
        };
        let mut privileges = vec![0usize; 1024];
        let mut bytes = size_of_val(privileges.as_slice()) as u32;
        let (mut granted, mut allowed) = (0, 0);
        sdk(
            unsafe {
                AccessCheck(
                    sd.0,
                    impersonation.as_raw_handle(),
                    1,
                    &mapping,
                    privileges.as_mut_ptr().cast(),
                    &mut bytes,
                    &mut granted,
                    &mut allowed,
                )
            },
            "AccessCheck MATCH_FILTER",
        )?;
        Ok(allowed != 0 && granted & 1 != 0)
    }
    fn principal_report(token: HANDLE, expected: PSID) -> io::Result<serde_json::Value> {
        let user = Buffer::query(|data, bytes, needed| unsafe {
            GetTokenInformation(token, TokenUser, data.cast(), bytes, needed)
        })?;
        let restricted = Buffer::query(|data, bytes, needed| unsafe {
            GetTokenInformation(token, TokenRestrictedSids, data.cast(), bytes, needed)
        })?;
        let count = *restricted.value::<u32>()? as usize;
        check(
            count
                .checked_mul(size_of::<SID_AND_ATTRIBUTES>())
                .and_then(|n| n.checked_add(offset_of!(TOKEN_GROUPS, Groups)))
                .is_some_and(|end| end <= restricted.bytes),
            "restricted SID array exceeds allocation",
        )?;
        let groups = unsafe {
            std::slice::from_raw_parts(
                restricted
                    .words
                    .as_ptr()
                    .cast::<u8>()
                    .add(offset_of!(TOKEN_GROUPS, Groups))
                    .cast::<SID_AND_ATTRIBUTES>(),
                count,
            )
        };
        let normal = unsafe { EqualSid(user.value::<TOKEN_USER>()?.User.Sid, expected) } != 0;
        let restricted_match = groups
            .iter()
            .any(|group| unsafe { EqualSid(group.Sid, expected) } != 0);
        let privileges = Buffer::query(|data, bytes, needed| unsafe {
            GetTokenInformation(token, TokenPrivileges, data.cast(), bytes, needed)
        })?;
        let count = *privileges.value::<u32>()? as usize;
        check(
            count
                .checked_mul(size_of::<LUID_AND_ATTRIBUTES>())
                .and_then(|n| n.checked_add(offset_of!(TOKEN_PRIVILEGES, Privileges)))
                .is_some_and(|end| end <= privileges.bytes),
            "privilege array exceeds allocation",
        )?;
        let values = unsafe {
            std::slice::from_raw_parts(
                privileges
                    .words
                    .as_ptr()
                    .cast::<u8>()
                    .add(offset_of!(TOKEN_PRIVILEGES, Privileges))
                    .cast::<LUID_AND_ATTRIBUTES>(),
                count,
            )
        };
        let mut notify = LUID::default();
        sdk(
            unsafe {
                LookupPrivilegeValueW(
                    null(),
                    wide("SeChangeNotifyPrivilege").as_ptr(),
                    &mut notify,
                )
            },
            "LookupPrivilegeValue notify",
        )?;
        let only_notify = values.iter().all(|value| {
            value.Luid.LowPart == notify.LowPart && value.Luid.HighPart == notify.HighPart
        });
        let session = Buffer::query(|data, bytes, needed| unsafe {
            GetTokenInformation(token, TokenSessionId, data.cast(), bytes, needed)
        })?;
        Ok(
            serde_json::json!({"normal_principal_matches":normal,"restricted_principal_matches":restricted_match,"only_change_notify_privilege":only_notify,"session_zero":*session.value::<u32>()? == 0}),
        )
    }
    fn negative_token(source: HANDLE, principal: Option<PSID>) -> io::Result<OwnedHandle> {
        let admins = sid("S-1-5-32-544")?;
        let world = sid("S-1-1-0")?;
        let disabled = SID_AND_ATTRIBUTES {
            Sid: admins.0,
            Attributes: 0,
        };
        let mut restricted = vec![SID_AND_ATTRIBUTES {
            Sid: world.0,
            Attributes: 0,
        }];
        if let Some(principal) = principal {
            restricted.push(SID_AND_ATTRIBUTES {
                Sid: principal,
                Attributes: 0,
            });
        }
        let mut raw = null_mut();
        sdk(
            unsafe {
                CreateRestrictedToken(
                    source,
                    DISABLE_MAX_PRIVILEGE | LUA_TOKEN,
                    1,
                    &disabled,
                    0,
                    null(),
                    restricted.len() as u32,
                    restricted.as_ptr(),
                    &mut raw,
                )
            },
            "CreateRestrictedToken forged restricting SID fixture",
        )?;
        let token = unsafe { OwnedHandle::from_raw_handle(raw) };
        let elevation = Buffer::query(|data, bytes, needed| unsafe {
            GetTokenInformation(
                token.as_raw_handle(),
                TokenElevation,
                data.cast(),
                bytes,
                needed,
            )
        })?;
        check(
            elevation.value::<TOKEN_ELEVATION>()?.TokenIsElevated == 0,
            "negative standard token remained elevated",
        )?;
        Ok(token)
    }

    fn publish(state: u32, error: u32) -> io::Result<()> {
        let status = SERVICE_STATUS {
            dwServiceType: SERVICE_WIN32_OWN_PROCESS,
            dwCurrentState: state,
            dwControlsAccepted: if state == SERVICE_RUNNING {
                SERVICE_ACCEPT_STOP
            } else {
                0
            },
            dwWin32ExitCode: if error == 0 {
                0
            } else {
                ERROR_SERVICE_SPECIFIC_ERROR
            },
            dwServiceSpecificExitCode: error,
            dwCheckPoint: 0,
            dwWaitHint: 0,
        };
        sdk(
            unsafe { SetServiceStatus(STATUS.load(Ordering::Acquire), &status) },
            "SetServiceStatus",
        )
    }
    unsafe extern "system" fn control(code: u32, _: u32, _: *mut c_void, _: *mut c_void) -> u32 {
        if code == SERVICE_CONTROL_STOP {
            STOP.store(true, Ordering::Release);
        }
        0
    }
    fn service_work(settings: &Receipt) -> io::Result<serde_json::Value> {
        let expected = service_sid(&settings.name)?;
        let token = token(
            unsafe { GetCurrentProcess() },
            TOKEN_QUERY | TOKEN_DUPLICATE,
            "OpenProcessToken service self AccessCheck",
        )?;
        let mut identity = principal_report(token.as_raw_handle(), expected.0)?;
        identity["condition_access_matches"] = serde_json::json!(access_matches(
            token.as_raw_handle(),
            &sid_string(expected.0)?
        )?);
        check(
            identity["normal_principal_matches"] == true
                && identity["restricted_principal_matches"] == true
                && identity["condition_access_matches"] == true
                && identity["only_change_notify_privilege"] == true
                && identity["session_zero"] == true,
            "SCM service token identity differs",
        )?;
        let profile = current_token_profile()?;
        check(
            !profile.admin_enabled && profile.unexpected_enabled_privileges == 0,
            "virtual worker retained administrator or unexpected privileges",
        )?;
        let mut stream = TcpStream::connect_timeout(&settings.endpoint, Duration::from_secs(3))?;
        stream.set_read_timeout(Some(Duration::from_secs(3)))?;
        stream.set_write_timeout(Some(Duration::from_secs(3)))?;
        stream.write_all(b"service-identity\n")?;
        let mut answer = [0; 3];
        stream.read_exact(&mut answer)?;
        check(&answer == b"ok\n", "service loopback reply differs")?;
        Ok(
            serde_json::json!({"ok":true,"nonce":settings.nonce,"source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),"identity":identity,"profile":profile,"loopback_tcp_baseline":true}),
        )
    }
    unsafe extern "system" fn service_main(_: u32, _: *mut *mut u16) {
        let Some(settings) = SETTINGS.get() else {
            return;
        };
        let handle = unsafe {
            RegisterServiceCtrlHandlerExW(wide(&settings.name).as_ptr(), Some(control), null())
        };
        if handle.is_null() {
            return;
        }
        STATUS.store(handle, Ordering::Release);
        let result = (|| {
            publish(SERVICE_START_PENDING, 0)?;
            publish(SERVICE_RUNNING, 0)?;
            let report = service_work(settings);
            let failed = report.is_err();
            let report = report.unwrap_or_else(|error| serde_json::json!({"ok":false,"nonce":settings.nonce,"error":error.to_string(),"sdk_code":error.raw_os_error()}));
            write_json(
                &settings.directory.join("service-result.json"),
                &report,
                false,
            )?;
            let mut completed = OpenOptions::new()
                .write(true)
                .open(settings.directory.join("service-complete.dat"))?;
            completed.write_all(b"1\n")?;
            completed.sync_all()?;
            check(!failed, "service capability proof failed")?;
            let deadline = Instant::now() + WAIT;
            while !STOP.load(Ordering::Acquire) && Instant::now() < deadline {
                thread::sleep(Duration::from_millis(25));
            }
            check(
                STOP.load(Ordering::Acquire),
                "service owner did not stop fixture before deadline",
            )
        })();
        let _ = publish(SERVICE_STOPPED, u32::from(result.is_err()));
    }

    fn combine(
        primary: io::Result<serde_json::Value>,
        cleanup: io::Result<()>,
    ) -> io::Result<serde_json::Value> {
        match (primary, cleanup) {
            (Ok(value), Ok(())) => Ok(value),
            (Err(error), Ok(())) | (Ok(_), Err(error)) => Err(error),
            (Err(primary), Err(cleanup)) => Err(io::Error::new(
                primary.kind(),
                format!("{primary}; owned cleanup failed: {cleanup}"),
            )),
        }
    }
    fn assert_admin() -> io::Result<()> {
        let profile = current_token_profile()?;
        check(
            profile.elevated && profile.admin_enabled,
            "requires an independently elevated disposable Windows runner",
        )
    }
    pub fn run() -> io::Result<()> {
        let arguments = std::env::args().skip(1).collect::<Vec<_>>();
        if arguments.first().map(String::as_str) == Some("--wfp-negative") {
            check(
                arguments.len() == 4,
                "invalid internal socket probe arguments",
            )?;
            assert_admin()?;
            let receipt: Receipt =
                read_json(&Path::new(&arguments[1]).join("service-receipt.json"))?;
            receipt.validate()?;
            check(
                receipt.nonce == arguments[2] && receipt.image == std::env::current_exe()?,
                "copied-image socket probe launch identity differs",
            )?;
            return negative_probe(&receipt, &arguments[3]);
        }
        if arguments.first().map(String::as_str) == Some("--service") {
            check(arguments.len() == 4, "invalid internal service arguments")?;
            let receipt: Receipt =
                read_json(&Path::new(&arguments[2]).join("service-receipt.json"))?;
            receipt.validate()?;
            check(
                receipt.name == arguments[1]
                    && receipt.nonce == arguments[3]
                    && receipt.image == std::env::current_exe()?,
                "service launch identity differs",
            )?;
            SETTINGS
                .set(receipt.clone())
                .map_err(|_| io::Error::other("service context already initialized"))?;
            // Keep the name allocation live through the dispatcher lifetime.
            let mut name = wide(&receipt.name);
            let table = [
                SERVICE_TABLE_ENTRYW {
                    lpServiceName: name.as_mut_ptr(),
                    lpServiceProc: Some(service_main),
                },
                SERVICE_TABLE_ENTRYW::default(),
            ];
            return sdk(
                unsafe { StartServiceCtrlDispatcherW(table.as_ptr()) },
                "StartServiceCtrlDispatcherW",
            );
        }
        let scoped_wfp = arguments.len() == 4 && arguments[3] == "--scoped-wfp";
        check(
            (arguments.len() == 3 || scoped_wfp)
                && arguments[0] == "--disposable-services"
                && matches!(arguments[1].as_str(), "--directory" | "--recover"),
            "requires --disposable-services --directory <fresh absolute path> [--scoped-wfp] or --recover <owned directory>; no service mutation attempted",
        )?;
        assert_admin()?;
        let directory = PathBuf::from(&arguments[2]);
        local_path(&directory)?;
        if arguments[1] == "--recover" {
            let receipt: Receipt = read_json(&directory.join("service-receipt.json"))?;
            receipt.validate()?;
            check(
                receipt.directory == directory,
                "recovery directory differs from owned receipt",
            )?;
            let wfp_policy = match std::fs::metadata(directory.join("wfp-receipt.json")) {
                Ok(_) => owned_policy(&receipt).map(Some),
                Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
                Err(error) => Err(error),
            };
            let service_cleanup = match OwnedService::open(receipt.clone(), false) {
                Ok(mut service) => service.cleanup(),
                Err(error) if error.raw_os_error() == Some(ERROR_SERVICE_DOES_NOT_EXIST as i32) => {
                    Ok(())
                }
                Err(error) => Err(error),
            };
            let wfp_cleanup = (|| match wfp_policy? {
                Some(policy) => {
                    let mut wfp = OwnedWfp {
                        engine: Some(Engine::open()?),
                        policy,
                    };
                    wfp.cleanup()
                }
                None => Ok(()),
            })();
            combine(
                service_cleanup.map(|()| serde_json::Value::Null),
                wfp_cleanup,
            )?;
            println!(
                "{}",
                serde_json::json!({"ok":true,"owned_service_removed":true,"owned_wfp_policy_absent":true,"evidence":"explicit exact-owned SCM/scoped WFP fixture recovery"})
            );
            return Ok(());
        }
        std::fs::create_dir(&directory)?;
        protect_file(&directory, None, false, true)?;
        let image = directory.join("identity-worker.exe");
        std::fs::copy(std::env::current_exe()?, &image)?;
        protect_file(&image, None, false, false)?;
        let listener = TcpListener::bind("127.0.0.1:0")?;
        listener.set_nonblocking(true)?;
        let mut id = GUID::from_u128(0);
        let code = unsafe { UuidCreate(&mut id) };
        check(code == 0, "UuidCreate failed")?;
        let nonce = format!(
            "{:08x}{:04x}{:04x}{:016x}",
            id.data1,
            id.data2,
            id.data3,
            u64::from_be_bytes(id.data4)
        );
        let receipt = Receipt {
            schema: 1,
            name: format!("SwirlIdentitySmoke-{nonce}"),
            nonce,
            directory: directory.clone(),
            image: image.clone(),
            image_sha256: hash(&image)?,
            endpoint: listener.local_addr()?,
        };
        write_json(&directory.join("service-receipt.json"), &receipt, true)?;
        let mut service = OwnedService::open(receipt.clone(), true)?;
        let mut wfp = None;
        let result = (|| {
            service.configure()?;
            let expected = service_sid(&receipt.name)?;
            let expected_text = sid_string(expected.0)?;
            protect_file(&directory, Some(&expected_text), false, true)?;
            protect_file(&image, Some(&expected_text), false, false)?;
            protect_file(
                &directory.join("service-receipt.json"),
                Some(&expected_text),
                false,
                false,
            )?;
            let result_path = directory.join("service-result.json");
            write_json(
                &result_path,
                &serde_json::json!({"ok":false,"pending":true}),
                true,
            )?;
            protect_file(&result_path, Some(&expected_text), true, false)?;
            let complete_path = directory.join("service-complete.dat");
            OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(&complete_path)?
                .sync_all()?;
            protect_file(&complete_path, Some(&expected_text), true, false)?;
            let original = token(
                unsafe { GetCurrentProcess() },
                TOKEN_QUERY | TOKEN_DUPLICATE,
                "OpenProcessToken negative fixture source",
            )?;
            check(
                !access_matches(original.as_raw_handle(), &expected_text)?,
                "ordinary administrator token unexpectedly matches service identity",
            )?;
            let standard = negative_token(original.as_raw_handle(), None)?;
            check(
                !access_matches(standard.as_raw_handle(), &expected_text)?,
                "standard token unexpectedly matched service identity",
            )?;
            let forged = negative_token(original.as_raw_handle(), Some(expected.0))?;
            check(
                !access_matches(forged.as_raw_handle(), &expected_text)?,
                "forged restricting SID matched normal service principal",
            )?;
            let socket_before = if scoped_wfp {
                let policy = scoped_policy(&receipt, &expected_text)?;
                write_json(&directory.join("wfp-receipt.json"), &policy, true)?;
                protect_file(&directory.join("wfp-receipt.json"), None, false, false)?;
                let before = run_negative_probe(&receipt, "before", &listener)?;
                wfp = Some(OwnedWfp {
                    engine: Some(Engine::open()?),
                    policy,
                });
                wfp.as_mut().unwrap().install(&receipt)?;
                Some(before)
            } else {
                None
            };
            let socket_blocked = if scoped_wfp {
                Some(run_negative_probe(&receipt, "blocked", &listener)?)
            } else {
                None
            };
            sdk(
                unsafe { StartServiceW(service.handle(), 0, null()) },
                "StartService virtual account",
            )?;
            let running = service.wait(SERVICE_RUNNING)?;
            check(running.dwProcessId != 0, "SCM returned no live service PID")?;
            let raw = unsafe {
                OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SYNCHRONIZE,
                    0,
                    running.dwProcessId,
                )
            };
            if raw.is_null() {
                return Err(io::Error::last_os_error());
            }
            let process = unsafe { OwnedHandle::from_raw_handle(raw) };
            check(
                unsafe { GetProcessId(process.as_raw_handle()) } == running.dwProcessId,
                "SCM process handle identity differs",
            )?;
            let mut image_name = vec![0u16; 32768];
            let mut image_units = image_name.len() as u32;
            sdk(
                unsafe {
                    QueryFullProcessImageNameW(
                        process.as_raw_handle(),
                        0,
                        image_name.as_mut_ptr(),
                        &mut image_units,
                    )
                },
                "QueryFullProcessImageName service",
            )?;
            let actual_image = String::from_utf16(&image_name[..image_units as usize])
                .map_err(io::Error::other)?;
            check(
                actual_image.eq_ignore_ascii_case(&local_path(&image)?),
                "live SCM service executable differs",
            )?;
            let (mut created, mut exited, mut kernel, mut user) = (
                FILETIME::default(),
                FILETIME::default(),
                FILETIME::default(),
                FILETIME::default(),
            );
            sdk(
                unsafe {
                    GetProcessTimes(
                        process.as_raw_handle(),
                        &mut created,
                        &mut exited,
                        &mut kernel,
                        &mut user,
                    )
                },
                "GetProcessTimes service",
            )?;
            check(
                created.dwLowDateTime != 0 || created.dwHighDateTime != 0,
                "service creation time is absent",
            )?;
            check(
                unsafe { WaitForSingleObject(process.as_raw_handle(), 0) } == WAIT_TIMEOUT,
                "service process already exited",
            )?;
            // This is read-only observation of another account's live SCM
            // token. AccessCheck is performed by the service on its own token;
            // the parent must not require TOKEN_DUPLICATE for these queries.
            let observed = token(
                process.as_raw_handle(),
                TOKEN_QUERY,
                "OpenProcessToken live SCM read-only",
            )?;
            let identity = principal_report(observed.as_raw_handle(), expected.0)?;
            check(
                identity["normal_principal_matches"] == true
                    && identity["restricted_principal_matches"] == true
                    && identity["only_change_notify_privilege"] == true
                    && identity["session_zero"] == true,
                "live SCM PID/token does not match virtual identity",
            )?;
            let deadline = Instant::now() + WAIT;
            let (mut stream, address) = loop {
                match listener.accept() {
                    Ok(value) => break value,
                    Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
                    Err(error) => return Err(error),
                }
                check(
                    Instant::now() < deadline,
                    "service loopback baseline deadline exceeded",
                )?;
                thread::sleep(Duration::from_millis(10));
            };
            check(address.ip().is_loopback(), "service peer escaped loopback")?;
            stream.set_read_timeout(Some(Duration::from_secs(3)))?;
            stream.set_write_timeout(Some(Duration::from_secs(3)))?;
            let mut request = [0; 17];
            stream.read_exact(&mut request)?;
            check(
                &request == b"service-identity\n",
                "service loopback request differs",
            )?;
            stream.write_all(b"ok\n")?;
            let report: serde_json::Value = loop {
                let completed = std::fs::metadata(&complete_path)?.len();
                check(completed <= 2, "service completion marker exceeds bound")?;
                if completed == 2 {
                    check(
                        std::fs::read(&complete_path)? == b"1\n",
                        "service completion marker differs",
                    )?;
                    break read_json::<serde_json::Value>(&result_path)?;
                }
                check(
                    Instant::now() < deadline,
                    "service token report deadline exceeded",
                )?;
                thread::sleep(Duration::from_millis(10));
            };
            check(
                report["ok"] == true
                    && report["nonce"] == receipt.nonce
                    && report["source_sha"] == option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),
                "service capability report failed; inspect preserved service-result.json",
            )?;
            service.verify_security()?;
            check(
                unsafe { WaitForSingleObject(process.as_raw_handle(), 0) } == WAIT_TIMEOUT,
                "service incarnation exited before final verification",
            )?;
            Ok(
                serde_json::json!({"ok":true,"evidence":"SCM virtual service identity and OS AccessCheck foundation smoke","source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),"service":report,"owned_config_and_acl_verified":true,"scm_live_process_image_verified":true,"normal_token_access_refused":true,"standard_token_access_refused":true,"forged_restricting_sid_access_refused":true,"wfp_enforcement_verified":scoped_wfp,"socket_controls_before":socket_before,"socket_controls_blocked":socket_blocked,"socket_control_scope":"same copied AppId, queried effective token held through all socket IO; not primary-token restricted children","low_integrity_core_child_verified":false,"product_broker_integrated":false,"system_kill_switch_acceptance":false,"network_configuration_modified":scoped_wfp,"routing_or_dns_modified":false,"service_deadline_seconds":WAIT.as_secs()}),
            )
        })();
        // Stop promptly, retaining the installed account until copied probes
        // independently resolve its exact expected service principal.
        let result = combine(result, service.stop());
        let had_wfp = wfp.is_some();
        let cleanup = wfp.as_mut().map_or(Ok(()), OwnedWfp::cleanup);
        // Restore verification remains useful after a failed installed-policy
        // assertion. Preserve the first failure and retain both phase artifacts.
        let after = if had_wfp && cleanup.is_ok() {
            Some(run_negative_probe(&receipt, "after", &listener))
        } else {
            None
        };
        let result = combine(result, cleanup);
        let result = match &after {
            Some(Err(error)) => {
                combine(result, Err(io::Error::new(error.kind(), error.to_string())))
            }
            _ => result,
        };
        let mut report = combine(result, service.cleanup())?;
        if let Some(Ok(after)) = after {
            report["socket_controls_after"] = after;
            report["owned_wfp_policy_removed"] = serde_json::json!(true);
        }
        report["owned_service_removed"] = serde_json::json!(true);
        println!("{report}");
        Ok(())
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        #[test]
        fn live_principal_report_needs_only_query_access() -> io::Result<()> {
            let mut raw = null_mut();
            sdk(
                unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut raw) },
                "OpenProcessToken read-only regression",
            )?;
            let token = unsafe { OwnedHandle::from_raw_handle(raw) };
            let expected = sid("S-1-5-80-1-2-3-4-5")?;
            let report = principal_report(token.as_raw_handle(), expected.0)?;
            assert_eq!(report["normal_principal_matches"], false);
            assert!(
                report.get("condition_access_matches").is_none(),
                "live reporting must not duplicate another account's token for AccessCheck"
            );
            Ok(())
        }
        #[test]
        fn cleanup_failure_prevents_a_success_receipt_and_preserves_both_errors() {
            assert!(
                combine(
                    Ok(serde_json::json!({"ok":true})),
                    Err(io::Error::other("DeleteService failed"))
                )
                .is_err()
            );
            let error = combine(
                Err(io::Error::new(io::ErrorKind::InvalidData, "token mismatch")),
                Err(io::Error::other("DeleteService failed")),
            )
            .unwrap_err();
            assert_eq!(error.kind(), io::ErrorKind::InvalidData);
            assert!(error.to_string().contains("token mismatch"));
            assert!(error.to_string().contains("DeleteService failed"));
        }
        #[test]
        fn scope_rejects_relative_or_remote_or_command_delimited_paths_without_os_writes() {
            for path in [r"relative", r"\\server\share\fixture", "C:\\unsafe\"path"] {
                assert!(local_path(Path::new(path)).is_err());
            }
        }
        fn fixture_receipt() -> Receipt {
            let directory = PathBuf::from(r"C:\SwirlOwnedIdentityFixture");
            Receipt {
                schema: 1,
                nonce: "00112233445566778899aabbccddeeff".into(),
                name: "SwirlIdentitySmoke-00112233445566778899aabbccddeeff".into(),
                image: directory.join("identity-worker.exe"),
                directory,
                image_sha256: "fixture-only-no-file-read".into(),
                endpoint: "127.0.0.1:43210".parse().unwrap(),
            }
        }
        #[test]
        fn scoped_policy_has_exact_image_tuple_and_service_only_soft_permit() {
            let receipt = fixture_receipt();
            let policy = scoped_policy(&receipt, "S-1-5-80-1-2-3-4-5").unwrap();
            assert_eq!(
                serde_json::to_value(policy).unwrap(),
                serde_json::json!({
                    "schema":2,
                    "owner":[0,17,34,51,68,85,102,119,136,153,170,187,204,221,238,255],
                    "application":receipt.image,
                    "sublayer_weight":0,
                    "rules":[
                    {"endpoint":receipt.endpoint,"protocol":"Tcp","action":"Block"},
                    {"endpoint":receipt.endpoint,"protocol":"Tcp","action":"SoftPermit","service_sid":"S-1-5-80-1-2-3-4-5"}
                    ]
                })
            );
            for principal in ["S-1-1-0", "S-1-5-32-544", "S-1-5-80-1-2-3-4"] {
                assert!(scoped_policy(&receipt, principal).is_err());
            }
            let mut remote = receipt;
            remote.endpoint = "192.0.2.1:43210".parse().unwrap();
            assert!(scoped_policy(&remote, "S-1-5-80-1-2-3-4-5").is_err());
        }
        #[test]
        fn policy_receipt_cannot_authorize_its_own_principal_or_wider_scope() {
            let receipt = fixture_receipt();
            let principal = "S-1-5-80-1-2-3-4-5";
            let policy = scoped_policy(&receipt, principal).unwrap();
            verify_policy_binding(&receipt, &policy, principal).unwrap();
            let mut forged = policy.clone();
            forged.rules[1].service_sid = Some("S-1-5-80-6-7-8-9-10".into());
            assert!(verify_policy_binding(&receipt, &forged, principal).is_err());
            let mut changed = policy.clone();
            changed.rules[0].endpoint = "127.0.0.1:43211".parse().unwrap();
            assert!(verify_policy_binding(&receipt, &changed, principal).is_err());
            let mut reordered = policy;
            reordered.rules.reverse();
            assert!(verify_policy_binding(&receipt, &reordered, principal).is_err());
        }
        fn blocked_report(receipt: &Receipt) -> serde_json::Value {
            let observations = ["administrator", "standard_effective_token", "forged_restricting_sid"]
                .iter().enumerate().map(|(index, kind)| serde_json::json!({
                    "kind":kind,
                    "identity":{"normal_principal_matches":false,"restricted_principal_matches":index == 2,
                        "thread_impersonated":index != 0,"elevated":index == 0},
                    "socket":{"echo_succeeded":false,"socket_error":10013}
                })).collect::<Vec<_>>();
            serde_json::json!({"nonce":receipt.nonce,"phase":"blocked","image_sha256":receipt.image_sha256,"observations":observations})
        }
        #[test]
        fn kernel_refusal_evidence_rejects_timeout_missing_identity_and_origin_traffic() {
            let receipt = fixture_receipt();
            let report = blocked_report(&receipt);
            validate_probe(&report, &receipt, "blocked", &[]).unwrap();
            for error in [
                serde_json::Value::Null,
                serde_json::json!(10060),
                serde_json::json!(10061),
            ] {
                let mut altered = report.clone();
                altered["observations"][1]["socket"]["socket_error"] = error;
                assert!(validate_probe(&altered, &receipt, "blocked", &[]).is_err());
            }
            for (index, field) in [
                (0, "elevated"),
                (1, "thread_impersonated"),
                (2, "restricted_principal_matches"),
            ] {
                let mut altered = report.clone();
                altered["observations"][index]["identity"][field] = serde_json::json!(false);
                assert!(validate_probe(&altered, &receipt, "blocked", &[]).is_err());
            }
            assert!(
                validate_probe(
                    &report,
                    &receipt,
                    "blocked",
                    &["blocked:administrator\n".into()]
                )
                .is_err()
            );
            let mut incomplete = report;
            incomplete["observations"].as_array_mut().unwrap().pop();
            assert!(validate_probe(&incomplete, &receipt, "blocked", &[]).is_err());
        }
        #[test]
        fn restored_connectivity_requires_all_three_exact_echoes_and_owned_probe() {
            let receipt = fixture_receipt();
            let mut report = blocked_report(&receipt);
            report["phase"] = serde_json::json!("after");
            let mut accepted = Vec::new();
            for value in report["observations"].as_array_mut().unwrap() {
                value["socket"] = serde_json::json!({"echo_succeeded":true,"socket_error":null});
                accepted.push(format!("after:{}\n", value["kind"].as_str().unwrap()));
            }
            accepted.reverse(); // Arrival order does not establish principal identity.
            validate_probe(&report, &receipt, "after", &accepted).unwrap();
            assert!(validate_probe(&report, &receipt, "after", &accepted[..2]).is_err());
            report["image_sha256"] = serde_json::json!("other-image");
            assert!(validate_probe(&report, &receipt, "after", &accepted).is_err());
        }
    }
}
