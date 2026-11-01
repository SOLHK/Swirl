//! Explicit disposable SCM identity proof. No driver, routing, DNS or WFP writes.
//! Kernel WFP enforcement is a separate, still-required acceptance stage.
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
        ptr::{null, null_mut},
        sync::{
            OnceLock,
            atomic::{AtomicBool, AtomicPtr, Ordering},
        },
        thread,
        time::{Duration, Instant},
    };
    use swirl_platform::windows_restricted_worker::current_token_profile;
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
        fn cleanup(&mut self) -> io::Result<()> {
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

    fn token(process: HANDLE) -> io::Result<OwnedHandle> {
        let mut raw = null_mut();
        sdk(
            unsafe { OpenProcessToken(process, TOKEN_QUERY | TOKEN_DUPLICATE, &mut raw) },
            "OpenProcessToken",
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
            serde_json::json!({"normal_principal_matches":normal,"restricted_principal_matches":restricted_match,"only_change_notify_privilege":only_notify,"session_zero":*session.value::<u32>()? == 0,"condition_access_matches":access_matches(token, &sid_string(expected)?)?}),
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
        let token = token(unsafe { GetCurrentProcess() })?;
        let identity = principal_report(token.as_raw_handle(), expected.0)?;
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
        check(
            arguments.len() == 3
                && arguments[0] == "--disposable-services"
                && matches!(arguments[1].as_str(), "--directory" | "--recover"),
            "requires --disposable-services --directory <fresh absolute path> or --recover <owned directory>; no service mutation attempted",
        )?;
        assert_admin()?;
        let directory = PathBuf::from(&arguments[2]);
        local_path(&directory)?;
        if arguments[1] == "--recover" {
            let receipt: Receipt = read_json(&directory.join("service-receipt.json"))?;
            check(
                receipt.directory == directory,
                "recovery directory differs from owned receipt",
            )?;
            match OwnedService::open(receipt, false) {
                Ok(mut service) => service.cleanup()?,
                Err(error) if error.raw_os_error() == Some(ERROR_SERVICE_DOES_NOT_EXIST as i32) => {
                }
                Err(error) => return Err(error),
            }
            println!(
                "{}",
                serde_json::json!({"ok":true,"owned_service_removed":true,"evidence":"explicit owned SCM fixture recovery"})
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
            let original = token(unsafe { GetCurrentProcess() })?;
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
            let observed = token(process.as_raw_handle())?;
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
                serde_json::json!({"ok":true,"evidence":"SCM virtual service identity and OS AccessCheck foundation smoke","source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),"service":report,"owned_config_and_acl_verified":true,"scm_live_process_image_verified":true,"normal_token_access_refused":true,"standard_token_access_refused":true,"forged_restricting_sid_access_refused":true,"wfp_enforcement_verified":false,"low_integrity_core_child_verified":false,"product_broker_integrated":false,"network_configuration_modified":false,"service_deadline_seconds":WAIT.as_secs()}),
            )
        })();
        let cleanup = service.cleanup();
        let mut report = combine(result, cleanup)?;
        report["owned_service_removed"] = serde_json::json!(true);
        println!("{report}");
        Ok(())
    }

    #[cfg(test)]
    mod tests {
        use super::*;
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
    }
}
