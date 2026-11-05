//! Authenticated local GUI pipe for the explicitly elevated product broker.
//! This module only queries identity and performs bounded IPC/file reads.
#![allow(unsafe_code)] // Windows process/token/file/overlapped-I/O boundary.

use sha2::{Digest, Sha256};
use std::{
    ffi::OsString,
    fs::{File, OpenOptions},
    io::{self, Read, Seek, SeekFrom},
    mem::size_of,
    os::windows::{
        ffi::{OsStrExt, OsStringExt},
        fs::{MetadataExt, OpenOptionsExt},
        io::{AsRawHandle, FromRawHandle, OwnedHandle},
    },
    path::{Component, Path, PathBuf, Prefix},
    ptr::{null, null_mut},
    sync::atomic::{AtomicBool, Ordering},
    thread,
    time::Duration,
};
use windows_sys::Win32::{
    Foundation::{
        DUPLICATE_SAME_ACCESS, DuplicateHandle, ERROR_BROKEN_PIPE, ERROR_IO_INCOMPLETE,
        ERROR_IO_PENDING, ERROR_PIPE_BUSY, ERROR_PIPE_NOT_CONNECTED, FILETIME, GENERIC_READ,
        GENERIC_WRITE, HANDLE, INVALID_HANDLE_VALUE, WAIT_OBJECT_0, WAIT_TIMEOUT,
    },
    Security::{
        GetLengthSid, GetTokenInformation, TOKEN_ELEVATION, TOKEN_INFORMATION_CLASS, TOKEN_QUERY,
        TOKEN_USER, TokenElevation, TokenSessionId, TokenUser,
    },
    Storage::FileSystem::{
        BY_HANDLE_FILE_INFORMATION, CreateFileW, FILE_ATTRIBUTE_REPARSE_POINT,
        FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OVERLAPPED, GetFileInformationByHandle,
        OPEN_EXISTING, ReadFile, SECURITY_IDENTIFICATION, SECURITY_SQOS_PRESENT, SYNCHRONIZE,
        WriteFile,
    },
    System::{
        IO::{CancelIoEx, GetOverlappedResult, OVERLAPPED},
        Pipes::{GetNamedPipeServerProcessId, PeekNamedPipe, WaitNamedPipeW},
        SystemInformation::GetWindowsDirectoryW,
        Threading::{
            CreateEventW, GetCurrentProcess, GetProcessTimes, OpenProcess, OpenProcessToken,
            PROCESS_QUERY_LIMITED_INFORMATION, QueryFullProcessImageNameW, WaitForMultipleObjects,
            WaitForSingleObject,
        },
    },
};

fn failure(code: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, code)
}
fn succeeded(value: i32) -> io::Result<()> {
    if value == 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}
fn own(handle: HANDLE) -> io::Result<OwnedHandle> {
    if handle.is_null() || handle == INVALID_HANDLE_VALUE {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: callers pass a newly created, non-inheritable Windows handle.
    Ok(unsafe { OwnedHandle::from_raw_handle(handle) })
}
fn wide(value: &std::ffi::OsStr) -> Vec<u16> {
    value.encode_wide().chain(Some(0)).collect()
}

/// Hold FILE_SHARE_READ only from verification through the child lifetime.
/// File IDs, rather than a path string, identify the GUI's actual mapped image.
pub struct LockedFile {
    file: File,
    path: PathBuf,
    id: (u32, u32, u32),
}
impl LockedFile {
    pub fn open(path: &Path) -> io::Result<Self> {
        if !path.is_absolute() {
            return Err(failure("BrokerAbsolutePathRequired"));
        }
        for ancestor in path.ancestors() {
            if std::fs::symlink_metadata(ancestor)?.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT
                != 0
            {
                return Err(failure("BrokerPackageReparsePoint"));
            }
        }
        let path = std::fs::canonicalize(path)?;
        if !matches!(path.components().next(), Some(Component::Prefix(p)) if matches!(p.kind(), Prefix::Disk(_) | Prefix::VerbatimDisk(_)))
        {
            return Err(failure("BrokerLocalPackageRequired"));
        }
        let file = OpenOptions::new().read(true).share_mode(1).open(&path)?;
        let mut info = BY_HANDLE_FILE_INFORMATION::default();
        // SAFETY: file is a live disk handle and info is a correctly sized output.
        succeeded(unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) })?;
        if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0 || !file.metadata()?.is_file()
        {
            return Err(failure("BrokerPackageFileRequired"));
        }
        Ok(Self {
            file,
            path,
            id: (
                info.dwVolumeSerialNumber,
                info.nFileIndexHigh,
                info.nFileIndexLow,
            ),
        })
    }
    pub fn path(&self) -> &Path {
        &self.path
    }
    pub fn sha256(&self) -> io::Result<String> {
        if self.file.metadata()?.len() > 512 * 1024 * 1024 {
            return Err(failure("BrokerPackageFileLimit"));
        }
        let mut source = &self.file;
        source.seek(SeekFrom::Start(0))?;
        let mut hash = Sha256::new();
        let mut buffer = [0; 65536];
        loop {
            let count = source.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            hash.update(&buffer[..count]);
        }
        Ok(format!("{:x}", hash.finalize()))
    }
    pub fn read_bounded(&self, limit: u64) -> io::Result<Vec<u8>> {
        if self.file.metadata()?.len() > limit {
            return Err(failure("BrokerPackageFileLimit"));
        }
        let mut bytes = Vec::new();
        let mut source = &self.file;
        source.seek(SeekFrom::Start(0))?;
        source.take(limit + 1).read_to_end(&mut bytes)?;
        if bytes.len() as u64 > limit {
            return Err(failure("BrokerPackageFileLimit"));
        }
        Ok(bytes)
    }
}

struct TokenIdentity {
    user: Vec<u8>,
    session: u32,
    elevated: bool,
}
fn token_record(token: HANDLE, class: TOKEN_INFORMATION_CLASS) -> io::Result<Vec<usize>> {
    let mut size = 0;
    // SAFETY: first call only queries a live token record's required length.
    unsafe { GetTokenInformation(token, class, null_mut(), 0, &mut size) };
    if size == 0 || size > 65536 {
        return Err(failure("BrokerTokenRecord"));
    }
    let mut words = vec![0usize; (size as usize).div_ceil(size_of::<usize>())];
    // SAFETY: aligned owned storage is large enough for the OS-reported record.
    succeeded(unsafe {
        GetTokenInformation(token, class, words.as_mut_ptr().cast(), size, &mut size)
    })?;
    Ok(words)
}
fn token_identity(process: HANDLE) -> io::Result<TokenIdentity> {
    let mut raw = null_mut();
    // SAFETY: process remains live; only read access to its primary token is requested.
    succeeded(unsafe { OpenProcessToken(process, TOKEN_QUERY, &mut raw) })?;
    let token = own(raw)?;
    let user = token_record(token.as_raw_handle(), TokenUser)?;
    let session = token_record(token.as_raw_handle(), TokenSessionId)?;
    let elevated = token_record(token.as_raw_handle(), TokenElevation)?;
    // SAFETY: these fixed token information classes return the documented
    // structures in the aligned buffers above, including the OS-owned SID.
    unsafe {
        let sid = (*user.as_ptr().cast::<TOKEN_USER>()).User.Sid;
        let length = GetLengthSid(sid) as usize;
        if length == 0 || length > 256 {
            return Err(failure("BrokerTokenSid"));
        }
        Ok(TokenIdentity {
            user: std::slice::from_raw_parts(sid.cast::<u8>(), length).to_vec(),
            session: *session.as_ptr().cast::<u32>(),
            elevated: (*elevated.as_ptr().cast::<TOKEN_ELEVATION>()).TokenIsElevated != 0,
        })
    }
}
fn created(process: HANDLE) -> io::Result<u64> {
    let (mut start, mut end, mut kernel, mut user) = (
        FILETIME::default(),
        FILETIME::default(),
        FILETIME::default(),
        FILETIME::default(),
    );
    // SAFETY: read-only times query with four valid output structures.
    succeeded(unsafe { GetProcessTimes(process, &mut start, &mut end, &mut kernel, &mut user) })?;
    Ok((u64::from(start.dwHighDateTime) << 32) | u64::from(start.dwLowDateTime))
}
fn image_path(process: HANDLE) -> io::Result<PathBuf> {
    let mut buffer = vec![0u16; 32768];
    let mut length = buffer.len() as u32;
    // SAFETY: query-only process handle and bounded writable UTF-16 buffer.
    succeeded(unsafe { QueryFullProcessImageNameW(process, 0, buffer.as_mut_ptr(), &mut length) })?;
    Ok(PathBuf::from(OsString::from_wide(
        &buffer[..length as usize],
    )))
}

pub struct AuthenticatedPipe {
    pipe: OwnedHandle,
    gui_process: OwnedHandle,
    pub gui_pid: u32,
    pub package_directory: PathBuf,
    pub gui_image: LockedFile,
    pub broker_image: LockedFile,
    _directory_locks: Vec<File>,
    poisoned: AtomicBool,
}
impl AuthenticatedPipe {
    pub fn connect(name: &str, expected_gui_pid: u32) -> io::Result<Self> {
        let prefix = format!(r"\\.\pipe\SwirlNativeTun-{expected_gui_pid}-");
        let suffix = name
            .strip_prefix(&prefix)
            .ok_or_else(|| failure("BrokerPipeName"))?;
        if expected_gui_pid == 0
            || suffix.len() != 32
            || !suffix.bytes().all(|v| v.is_ascii_hexdigit())
        {
            return Err(failure("BrokerPipeName"));
        }
        let executable = std::env::current_exe()?;
        let directory = executable
            .parent()
            .ok_or_else(|| failure("BrokerPackageDirectory"))?;
        let mut directory_locks = Vec::new();
        for ancestor in directory.ancestors() {
            if std::fs::symlink_metadata(ancestor)?.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT
                != 0
            {
                return Err(failure("BrokerPackageReparsePoint"));
            }
            directory_locks.push(
                OpenOptions::new()
                    .read(true)
                    .share_mode(1)
                    .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
                    .open(ancestor)?,
            );
        }
        let broker_image = LockedFile::open(&directory.join("swirl-tun-broker.exe"))?;
        let actual_image = LockedFile::open(&executable)?;
        if actual_image.id != broker_image.id {
            return Err(failure("BrokerImageIdentity"));
        }
        let gui_image = LockedFile::open(&directory.join("Swirl.exe"))?;
        let pipe_name = wide(std::ffi::OsStr::new(name));
        // SQOS is mandatory: the lower-privilege server can identify this
        // elevated client but may never impersonate it to mutate the host.
        let open = || unsafe {
            CreateFileW(
                pipe_name.as_ptr(),
                GENERIC_READ | GENERIC_WRITE,
                0,
                null(),
                OPEN_EXISTING,
                FILE_FLAG_OVERLAPPED | SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION,
                null_mut(),
            )
        };
        let mut raw = open();
        if raw == INVALID_HANDLE_VALUE
            && io::Error::last_os_error().raw_os_error() == Some(ERROR_PIPE_BUSY as i32)
        {
            // SAFETY: only wait for the validated local pipe, with a fixed deadline.
            succeeded(unsafe { WaitNamedPipeW(pipe_name.as_ptr(), 10000) })?;
            raw = open();
        }
        let pipe = own(raw)?;
        let mut actual_pid = 0;
        // SAFETY: connected pipe handle and a writable PID output.
        succeeded(unsafe { GetNamedPipeServerProcessId(pipe.as_raw_handle(), &mut actual_pid) })?;
        if actual_pid != expected_gui_pid {
            return Err(failure("BrokerGuiProcessMismatch"));
        }
        // SAFETY: open the kernel-reported pipe owner with query/wait only.
        let gui_process = own(unsafe {
            OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
                0,
                actual_pid,
            )
        })?;
        // SAFETY: pseudo handle is query-only and is never closed.
        let current = unsafe { GetCurrentProcess() };
        let own_token = token_identity(current)?;
        let gui_token = token_identity(gui_process.as_raw_handle())?;
        if !own_token.elevated
            || own_token.user != gui_token.user
            || own_token.session != gui_token.session
        {
            return Err(failure("BrokerGuiTokenMismatch"));
        }
        if created(gui_process.as_raw_handle())? > created(current)? {
            return Err(failure("BrokerGuiProcessReused"));
        }
        let mapped_gui = LockedFile::open(&image_path(gui_process.as_raw_handle())?)?;
        if mapped_gui.id != gui_image.id {
            return Err(failure("BrokerGuiImageMismatch"));
        }
        let result = Self {
            pipe,
            gui_process,
            gui_pid: actual_pid,
            package_directory: broker_image.path.parent().unwrap().to_path_buf(),
            gui_image,
            broker_image,
            _directory_locks: directory_locks,
            poisoned: AtomicBool::new(false),
        };
        result.check_alive()?;
        Ok(result)
    }
    pub fn check_alive(&self) -> io::Result<()> {
        if self.poisoned.load(Ordering::Relaxed) {
            return Err(failure("BrokerPipePoisoned"));
        }
        // SAFETY: this retained process handle cannot identify a reused PID.
        if unsafe { WaitForSingleObject(self.gui_process.as_raw_handle(), 0) } != WAIT_TIMEOUT {
            return Err(failure("BrokerGuiExited"));
        }
        // Also detect a normal GUI transport close while its process remains
        // alive, including while the helper is completing a long operation.
        // SAFETY: query only; no bytes are read or removed from the pipe.
        succeeded(unsafe {
            PeekNamedPipe(
                self.pipe.as_raw_handle(),
                null_mut(),
                0,
                null_mut(),
                null_mut(),
                null_mut(),
            )
        })?;
        Ok(())
    }
    fn transfer(
        &self,
        input: Option<&[u8]>,
        length: usize,
        limit: Duration,
    ) -> io::Result<(Vec<u8>, usize)> {
        self.check_alive()?;
        let mut duplicate = null_mut();
        // SAFETY: duplicate this live pipe into the current process only; the
        // operation retains its own non-inheritable handle through completion.
        succeeded(unsafe {
            DuplicateHandle(
                GetCurrentProcess(),
                self.pipe.as_raw_handle(),
                GetCurrentProcess(),
                &mut duplicate,
                0,
                0,
                DUPLICATE_SAME_ACCESS,
            )
        })?;
        let handle = own(duplicate)?;
        // SAFETY: unnamed non-inheritable event for exactly this I/O operation.
        let event = own(unsafe { CreateEventW(null(), 1, 0, null()) })?;
        let mut operation = Box::new(PipeOperation {
            handle,
            event,
            overlapped: Box::new(OVERLAPPED::default()),
            buffer: input.map_or_else(|| vec![0; length], |bytes| bytes[..length].to_vec()),
        });
        operation.overlapped.hEvent = operation.event.as_raw_handle();
        // SAFETY: owned heap buffer/event/OVERLAPPED remain valid until the OS
        // completes. A cancelled incomplete operation transfers to a reaper.
        let result = unsafe {
            if input.is_some() {
                WriteFile(
                    operation.handle.as_raw_handle(),
                    operation.buffer.as_ptr(),
                    length as u32,
                    null_mut(),
                    &mut *operation.overlapped,
                )
            } else {
                ReadFile(
                    operation.handle.as_raw_handle(),
                    operation.buffer.as_mut_ptr(),
                    length as u32,
                    null_mut(),
                    &mut *operation.overlapped,
                )
            }
        };
        if result == 0 && io::Error::last_os_error().raw_os_error() != Some(ERROR_IO_PENDING as i32)
        {
            return Err(io::Error::last_os_error());
        }
        if result == 0 {
            let handles = [
                operation.event.as_raw_handle(),
                self.gui_process.as_raw_handle(),
            ];
            // SAFETY: both live waitable handles remain retained above.
            let waited = unsafe {
                WaitForMultipleObjects(
                    2,
                    handles.as_ptr(),
                    0,
                    limit.as_millis().min(u128::from(u32::MAX - 1)) as u32,
                )
            };
            if waited != WAIT_OBJECT_0 {
                self.poisoned.store(true, Ordering::Relaxed);
                cancel_operation(operation);
                return Err(if waited == WAIT_TIMEOUT {
                    io::Error::new(io::ErrorKind::TimedOut, "BrokerPipeTimeout")
                } else {
                    failure("BrokerGuiExited")
                });
            }
        }
        let mut transferred = 0;
        // SAFETY: event is signalled or the operation completed synchronously.
        if unsafe {
            GetOverlappedResult(
                operation.handle.as_raw_handle(),
                &*operation.overlapped,
                &mut transferred,
                0,
            )
        } == 0
        {
            let error = io::Error::last_os_error();
            if error.raw_os_error() == Some(ERROR_IO_INCOMPLETE as i32) {
                self.poisoned.store(true, Ordering::Relaxed);
                cancel_operation(operation);
            }
            return Err(error);
        }
        let PipeOperation { buffer, .. } = *operation;
        Ok((buffer, transferred as usize))
    }
}

struct PipeOperation {
    handle: OwnedHandle,
    event: OwnedHandle,
    overlapped: Box<OVERLAPPED>,
    buffer: Vec<u8>,
}
fn cancel_operation(operation: Box<PipeOperation>) {
    // SAFETY: this operation exclusively owns its live pipe/event/heap buffers.
    unsafe {
        CancelIoEx(operation.handle.as_raw_handle(), &*operation.overlapped);
    }
    let mut ignored = 0;
    // Keep the lifecycle caller bounded even if cancellation completion stalls.
    // SAFETY: only wait on the operation's retained private event.
    let waited = unsafe { WaitForSingleObject(operation.event.as_raw_handle(), 2000) };
    if waited == WAIT_OBJECT_0 {
        // SAFETY: completed event; querying never waits.
        let result = unsafe {
            GetOverlappedResult(
                operation.handle.as_raw_handle(),
                &*operation.overlapped,
                &mut ignored,
                0,
            )
        };
        if result != 0
            || io::Error::last_os_error().raw_os_error() != Some(ERROR_IO_INCOMPLETE as i32)
        {
            return;
        }
    }
    // Transfer ownership without moving the OVERLAPPED or allocation. If a
    // cleanup thread cannot be created, retain this single poisoned operation
    // until process exit rather than freeing memory the kernel may still use.
    let address = Box::into_raw(operation) as usize;
    let _ = thread::Builder::new()
        .name("swirl-broker-io-drain".into())
        .spawn(move || {
            // SAFETY: exactly this closure receives the unique leaked box address.
            let operation = unsafe { Box::from_raw(address as *mut PipeOperation) };
            let mut ignored = 0;
            // SAFETY: detached cleanup retains all memory/handles through completion;
            // this wait cannot delay TUN restoration in the lifecycle thread.
            unsafe {
                GetOverlappedResult(
                    operation.handle.as_raw_handle(),
                    &*operation.overlapped,
                    &mut ignored,
                    1,
                );
            }
        });
}
impl Read for AuthenticatedPipe {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        if bytes.is_empty() {
            return Ok(0);
        }
        match self.transfer(None, bytes.len().min(65536), Duration::from_secs(300)) {
            Err(error) if matches!(error.raw_os_error(),Some(code) if code==ERROR_BROKEN_PIPE as i32 || code==ERROR_PIPE_NOT_CONNECTED as i32) => {
                Ok(0)
            }
            Ok((buffer, count)) => {
                bytes[..count].copy_from_slice(&buffer[..count]);
                Ok(count)
            }
            Err(error) => Err(error),
        }
    }
}
impl std::io::Write for AuthenticatedPipe {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.is_empty() {
            return Ok(0);
        }
        self.transfer(Some(bytes), bytes.len().min(65536), Duration::from_secs(5))
            .map(|(_, count)| count)
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

/// Child environment roots come from the OS, never the unelevated caller.
pub fn windows_directory() -> io::Result<PathBuf> {
    let mut buffer = vec![0u16; 32768];
    // SAFETY: bounded writable UTF-16 buffer.
    let length = unsafe { GetWindowsDirectoryW(buffer.as_mut_ptr(), buffer.len() as u32) };
    if length == 0 || length as usize >= buffer.len() {
        return Err(failure("BrokerWindowsDirectory"));
    }
    Ok(PathBuf::from(OsString::from_wide(
        &buffer[..length as usize],
    )))
}

/// Keep the privileged helper headless without exposing Windows process flags
/// through a shared Core/API module.
pub fn hide_helper_window(command: &mut std::process::Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(windows_sys::Win32::System::Threading::CREATE_NO_WINDOW);
}
