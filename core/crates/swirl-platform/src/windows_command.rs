//! Ownership boundary for the helper's Windows control commands.
//!
//! A command starts suspended, joins an unnamed non-inheritable kill-on-close
//! job, and only then resumes. Descendants cannot outlive the command owner and
//! perform delayed network writes after recovery. This covers CreateProcess
//! descendants, not requests already accepted by an external CIM/WMI service;
//! journal readback remains mandatory. Trusted scripts must not launch a new
//! process through a separate broker (such as WMI) to escape the job.
//!
//! Stable std::Command does not expose atomic job-list process attributes. If
//! the owner dies between spawn and assignment, a suspended orphan can remain;
//! its primary thread has not run the command. No running fallback is allowed.
use std::{
    io,
    ops::{Deref, DerefMut},
    os::windows::{
        io::{AsRawHandle, FromRawHandle, OwnedHandle},
        process::CommandExt,
    },
    process::{Child, Command, ExitStatus},
    ptr,
};
use windows_sys::Win32::{
    Foundation::{ERROR_NO_MORE_FILES, INVALID_HANDLE_VALUE},
    System::{
        Diagnostics::ToolHelp::{
            CreateToolhelp32Snapshot, TH32CS_SNAPTHREAD, THREADENTRY32, Thread32First, Thread32Next,
        },
        JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
            SetInformationJobObject, TerminateJobObject,
        },
        Threading::{
            CREATE_NO_WINDOW, CREATE_SUSPENDED, GetProcessIdOfThread, OpenThread, ResumeThread,
            THREAD_QUERY_LIMITED_INFORMATION, THREAD_SUSPEND_RESUME,
        },
    },
};

/// Owns the direct child and the sole handle to its process-tree job.
/// Deref permits taking stdio pipes; use this type's kill/wait/try_wait methods
/// so inherited pipes held by descendants are closed before reader joins.
pub(crate) struct OwnedChild {
    child: Child,
    job: Option<OwnedHandle>,
    assigned: bool,
}

/// Spawn a hidden control command; caller-supplied creation flags are replaced
/// deliberately. This is not a general GUI/process-launching abstraction.
pub(crate) fn spawn_owned(command: &mut Command) -> io::Result<OwnedChild> {
    spawn_before_assign(command, |_| Ok(()))
}

// The private observer makes the suspended, unassigned boundary testable. The
// production entry point always supplies a no-op, with no caller hook exposed.
#[allow(unsafe_code)]
fn spawn_before_assign(
    command: &mut Command,
    before_assign: impl FnOnce(&mut OwnedChild) -> io::Result<()>,
) -> io::Result<OwnedChild> {
    let job = create_job()?;
    let child = command
        .creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED)
        .spawn()?;
    // Even an assignment error or a test-observer panic kills and waits for
    // the unassigned suspended child through this guard's Drop implementation.
    let mut owned = OwnedChild {
        child,
        job: Some(job),
        assigned: false,
    };
    before_assign(&mut owned)?;
    // SAFETY: both owned handles are live; std's new child handle permits
    // PROCESS_SET_QUOTA/PROCESS_TERMINATE. No thread has been resumed yet.
    if unsafe {
        AssignProcessToJobObject(
            owned.job.as_ref().expect("new job").as_raw_handle(),
            owned.child.as_raw_handle(),
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    owned.assigned = true;
    resume_primary(&mut owned.child)?;
    Ok(owned)
}

#[allow(unsafe_code)]
fn create_job() -> io::Result<OwnedHandle> {
    // SAFETY: null security attributes create a non-inheritable handle; a null
    // name creates a private job, so a later process cannot reopen it by name.
    let raw = unsafe { CreateJobObjectW(ptr::null(), ptr::null()) };
    if raw.is_null() {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: CreateJobObjectW returned a new, valid, exclusively owned handle.
    let job = unsafe { OwnedHandle::from_raw_handle(raw) };
    let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    // SAFETY: the correctly sized repr(C) value lives through this call. No
    // BREAKAWAY_OK/SILENT_BREAKAWAY_OK flags are enabled for descendants.
    if unsafe {
        SetInformationJobObject(
            job.as_raw_handle(),
            JobObjectExtendedLimitInformation,
            ptr::from_ref(&limits).cast(),
            size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(job)
}

#[allow(unsafe_code)]
fn primary_thread(process_id: u32) -> io::Result<OwnedHandle> {
    // SAFETY: no pointer arguments; the snapshot is owned until enumeration ends.
    let raw = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) };
    if raw == INVALID_HANDLE_VALUE {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: the successful snapshot call returned an owned kernel handle.
    let snapshot = unsafe { OwnedHandle::from_raw_handle(raw) };
    let mut entry = THREADENTRY32 {
        dwSize: size_of::<THREADENTRY32>() as u32,
        ..THREADENTRY32::default()
    };
    let mut found = None;
    // SAFETY: entry is writable and its documented dwSize is initialized.
    let mut more = unsafe { Thread32First(snapshot.as_raw_handle(), &mut entry) };
    loop {
        if more == 0 {
            let error = io::Error::last_os_error();
            if error.raw_os_error() != Some(ERROR_NO_MORE_FILES as i32) {
                return Err(error);
            }
            break;
        }
        if entry.th32OwnerProcessID == process_id && found.replace(entry.th32ThreadID).is_some() {
            return Err(io::Error::other(
                "suspended command has more than one initial thread",
            ));
        }
        entry.dwSize = size_of::<THREADENTRY32>() as u32;
        // SAFETY: the snapshot remains live and entry remains correctly sized.
        more = unsafe { Thread32Next(snapshot.as_raw_handle(), &mut entry) };
    }
    let thread_id = found.ok_or_else(|| io::Error::other("suspended command thread is missing"))?;
    // SAFETY: only the just-created child's unique initial thread is opened,
    // with the two rights needed below and with inheritance disabled.
    let raw = unsafe {
        OpenThread(
            THREAD_SUSPEND_RESUME | THREAD_QUERY_LIMITED_INFORMATION,
            0,
            thread_id,
        )
    };
    if raw.is_null() {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: OpenThread returned a valid handle now owned by this guard.
    let thread = unsafe { OwnedHandle::from_raw_handle(raw) };
    // SAFETY: the live thread handle has THREAD_QUERY_LIMITED_INFORMATION.
    let owner = unsafe { GetProcessIdOfThread(thread.as_raw_handle()) };
    if owner == 0 {
        return Err(io::Error::last_os_error());
    }
    if owner != process_id {
        return Err(io::Error::other("suspended command thread owner changed"));
    }
    Ok(thread)
}

#[allow(unsafe_code)]
fn resume_primary(child: &mut Child) -> io::Result<()> {
    let thread = primary_thread(child.id())?;
    if child.try_wait()?.is_some() {
        return Err(io::Error::other("suspended command exited before resume"));
    }
    // SAFETY: assignment already succeeded, the thread belongs to the live
    // child, and this handle has THREAD_SUSPEND_RESUME. Resume exactly once.
    match unsafe { ResumeThread(thread.as_raw_handle()) } {
        1 => Ok(()),
        u32::MAX => Err(io::Error::last_os_error()),
        _ => Err(io::Error::other(
            "command did not have exactly one initial suspension",
        )),
    }
}

impl OwnedChild {
    #[allow(unsafe_code)]
    pub(crate) fn kill(&mut self) -> io::Result<()> {
        let result = if let Some(job) = self.job.take() {
            // SAFETY: this wrapper owns the only non-inheritable job handle.
            // Closing it below also enforces kill-on-close if this call fails.
            let result = if unsafe { TerminateJobObject(job.as_raw_handle(), 1) } == 0 {
                Err(io::Error::last_os_error())
            } else {
                Ok(())
            };
            drop(job);
            result
        } else {
            Ok(())
        };
        if !self.assigned {
            // Assignment failed before execution: the suspended child has not
            // joined the job, so it also needs direct termination and reaping.
            let child_result = self.child.kill();
            return result.and(child_result);
        }
        result
    }

    pub(crate) fn try_wait(&mut self) -> io::Result<Option<ExitStatus>> {
        match self.child.try_wait() {
            Ok(None) => Ok(None),
            Ok(Some(status)) => {
                self.kill()?;
                Ok(Some(status))
            }
            Err(error) => {
                let _ = self.kill();
                let _ = self.child.wait();
                Err(error)
            }
        }
    }

    pub(crate) fn wait(&mut self) -> io::Result<ExitStatus> {
        let result = self.child.wait();
        let cleanup = self.kill();
        match result {
            Ok(status) => cleanup.map(|()| status),
            Err(error) => {
                let _ = self.child.wait();
                Err(error)
            }
        }
    }
}

impl Deref for OwnedChild {
    type Target = Child;
    fn deref(&self) -> &Self::Target {
        &self.child
    }
}

impl DerefMut for OwnedChild {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.child
    }
}

impl Drop for OwnedChild {
    fn drop(&mut self) {
        let _ = self.kill();
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        io::Read,
        os::windows::ffi::OsStringExt,
        path::{Path, PathBuf},
        process::Stdio,
        sync::{
            atomic::{AtomicU64, Ordering},
            mpsc,
        },
        thread,
        time::{Duration, Instant},
    };
    use windows_sys::Win32::{
        Foundation::{WAIT_OBJECT_0, WAIT_TIMEOUT},
        System::{
            JobObjects::IsProcessInJob,
            SystemInformation::GetSystemDirectoryW,
            Threading::{OpenProcess, PROCESS_SYNCHRONIZE, SuspendThread, WaitForSingleObject},
        },
    };

    const TEST_TIMEOUT: Duration = Duration::from_secs(20);

    struct TestFiles(PathBuf);
    impl TestFiles {
        fn new() -> Self {
            static NEXT: AtomicU64 = AtomicU64::new(0);
            let path = std::env::temp_dir().join(format!(
                "swirl-owned-command-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed),
            ));
            fs::create_dir(&path).expect("unique test directory");
            Self(path)
        }
        fn path(&self, name: &str) -> PathBuf {
            self.0.join(name)
        }
    }
    impl Drop for TestFiles {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[allow(unsafe_code)]
    fn command(files: &TestFiles, script: &str) -> Command {
        let mut buffer = [0u16; 32768];
        // SAFETY: Windows receives a valid writable UTF-16 buffer. This test
        // must use the system executable, never a PATH or environment override.
        let length =
            unsafe { GetSystemDirectoryW(buffer.as_mut_ptr(), buffer.len() as u32) } as usize;
        assert!(length > 0 && length < buffer.len());
        let executable = PathBuf::from(std::ffi::OsString::from_wide(&buffer[..length]))
            .join("WindowsPowerShell/v1.0/powershell.exe");
        let mut command = Command::new(executable);
        command
            .args([
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ])
            .env("SWIRL_COMMAND_TEST_DIR", &files.0)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        command
    }

    fn wait_for_file(path: &Path) -> String {
        let start = Instant::now();
        loop {
            if let Ok(contents) = fs::read_to_string(path)
                && !contents.is_empty()
            {
                return contents;
            }
            assert!(
                start.elapsed() < TEST_TIMEOUT,
                "file was not written: {path:?}"
            );
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn wait_for_exit(child: &mut OwnedChild) -> ExitStatus {
        let start = Instant::now();
        loop {
            if let Some(status) = child.try_wait().expect("owned command status") {
                return status;
            }
            assert!(start.elapsed() < TEST_TIMEOUT, "owned command did not exit");
            thread::sleep(Duration::from_millis(10));
        }
    }

    #[allow(unsafe_code)]
    fn process_handle(pid: u32) -> OwnedHandle {
        // SAFETY: open only the known test process, for synchronization only,
        // with handle inheritance disabled. The returned handle is owned here.
        let raw = unsafe { OpenProcess(PROCESS_SYNCHRONIZE, 0, pid) };
        assert!(
            !raw.is_null(),
            "test process is missing: {}",
            io::Error::last_os_error()
        );
        unsafe { OwnedHandle::from_raw_handle(raw) }
    }

    #[allow(unsafe_code)]
    fn assert_running(process: &OwnedHandle) {
        // SAFETY: this owned handle permits synchronization and remains live.
        assert_eq!(
            unsafe { WaitForSingleObject(process.as_raw_handle(), 0) },
            WAIT_TIMEOUT
        );
    }

    #[allow(unsafe_code)]
    fn assert_terminated(process: &OwnedHandle) {
        // SAFETY: this owned handle permits synchronization and remains live.
        assert_eq!(
            unsafe { WaitForSingleObject(process.as_raw_handle(), 2_000) },
            WAIT_OBJECT_0
        );
    }

    const WAIT_THEN_WRITE: &str = r#"
$ErrorActionPreference='Stop'
$root=$env:SWIRL_COMMAND_TEST_DIR
[IO.File]::WriteAllText((Join-Path $root 'ready'),[string]$PID)
while (-not [IO.File]::Exists((Join-Path $root 'release'))) { Start-Sleep -Milliseconds 10 }
[IO.File]::WriteAllText((Join-Path $root 'late-write'),'executed')
"#;

    #[test]
    #[allow(unsafe_code)]
    fn command_is_suspended_before_assignment_and_runs_only_after_ownership() {
        let files = TestFiles::new();
        let mut command = command(&files, WAIT_THEN_WRITE);
        let mut child = spawn_before_assign(&mut command, |child| {
            let thread = primary_thread(child.id())?;
            // SAFETY: inspect the new child's unique primary-thread suspension
            // count before assignment, then restore that exact count. This is
            // deterministic and does not rely on PowerShell startup timing.
            assert_eq!(unsafe { SuspendThread(thread.as_raw_handle()) }, 1);
            assert_eq!(unsafe { ResumeThread(thread.as_raw_handle()) }, 2);
            let mut member = 1;
            // SAFETY: both process/job handles are live and member is writable.
            assert_ne!(
                unsafe {
                    IsProcessInJob(
                        child.as_raw_handle(),
                        child.job.as_ref().unwrap().as_raw_handle(),
                        &mut member,
                    )
                },
                0
            );
            assert_eq!(member, 0);
            assert!(!files.path("ready").exists());
            Ok(())
        })
        .expect("suspended command assignment");
        wait_for_file(&files.path("ready"));
        let mut member = 0;
        // SAFETY: both owned handles remain live while the child waits on release.
        assert_ne!(
            unsafe {
                IsProcessInJob(
                    child.as_raw_handle(),
                    child.job.as_ref().unwrap().as_raw_handle(),
                    &mut member,
                )
            },
            0
        );
        assert_ne!(member, 0);
        fs::write(files.path("release"), b"go").unwrap();
        assert!(wait_for_exit(&mut child).success());
        assert_eq!(
            fs::read_to_string(files.path("late-write")).unwrap(),
            "executed"
        );
    }

    #[test]
    fn closing_last_job_handle_terminates_running_child_before_late_write() {
        let files = TestFiles::new();
        let mut child = spawn_owned(&mut command(&files, WAIT_THEN_WRITE)).unwrap();
        wait_for_file(&files.path("ready"));
        let process = process_handle(child.id());
        assert_running(&process);
        // Closing the job handle models abrupt owner death. Do not call the
        // wrapper's kill()/Drop first: this specifically tests the kernel's
        // kill-on-last-close behavior and that the child did not inherit it.
        drop(child.job.take());
        assert_terminated(&process);
        drop(child);
        // The command cannot observe this release: its kernel process handle
        // is signaled, rather than merely assuming it exited after a delay.
        fs::write(files.path("release"), b"go").unwrap();
        assert!(!files.path("late-write").exists());
    }

    #[test]
    fn failure_before_assignment_reaps_the_suspended_child() {
        let files = TestFiles::new();
        let mut process = None;
        let result = spawn_before_assign(&mut command(&files, WAIT_THEN_WRITE), |child| {
            process = Some(process_handle(child.id()));
            Err(io::Error::other("injected failure before assignment"))
        });
        assert!(
            matches!(result, Err(error) if error.to_string() == "injected failure before assignment")
        );
        assert_terminated(&process.unwrap());
        assert!(!files.path("ready").exists());
        assert!(!files.path("late-write").exists());
    }

    #[test]
    fn normal_exit_terminates_descendants_and_closes_inherited_stdout() {
        let files = TestFiles::new();
        let script = r#"
$ErrorActionPreference='Stop'
$root=$env:SWIRL_COMMAND_TEST_DIR
$start=New-Object Diagnostics.ProcessStartInfo
$start.FileName=Join-Path $PSHOME 'powershell.exe'
$start.UseShellExecute=$false
$start.CreateNoWindow=$true
# .NET Framework only supplies STARTF_USESTDHANDLES when a stream is
# redirected. Redirect stdin so the child receives the existing stdout pipe;
# leave stdout itself inherited, without a forwarding pump in the parent.
$start.RedirectStandardInput=$true
$start.Arguments='-NoLogo -NoProfile -NonInteractive -Command "$root=$env:SWIRL_COMMAND_TEST_DIR; [Console]::Out.WriteLine(''descendant-ready''); [IO.File]::WriteAllText((Join-Path $root ''descendant''),[string]$PID); while (-not [IO.File]::Exists((Join-Path $root ''release''))) { Start-Sleep -Milliseconds 10 }; [IO.File]::WriteAllText((Join-Path $root ''late-write''),''executed'')"'
$descendant=[Diagnostics.Process]::Start($start)
$descendant.StandardInput.Close()
while (-not [IO.File]::Exists((Join-Path $root 'parent-exit'))) { Start-Sleep -Milliseconds 10 }
[Console]::Out.WriteLine('parent-exit')
"#;
        let mut command = command(&files, script);
        command.stdout(Stdio::piped());
        let mut child = spawn_owned(&mut command).unwrap();
        let mut stdout = child.stdout.take().unwrap();
        let (tx, rx) = mpsc::sync_channel(1);
        let reader = thread::spawn(move || {
            let mut output = String::new();
            let result = stdout.read_to_string(&mut output).map(|_| output);
            let _ = tx.send(result);
        });
        let pid: u32 = wait_for_file(&files.path("descendant")).parse().unwrap();
        let descendant = process_handle(pid);
        assert_running(&descendant);
        assert!(matches!(rx.try_recv(), Err(mpsc::TryRecvError::Empty)));
        fs::write(files.path("parent-exit"), b"go").unwrap();
        assert!(wait_for_exit(&mut child).success());
        assert_terminated(&descendant);
        let output = rx
            .recv_timeout(Duration::from_secs(2))
            .expect("descendant held stdout after normal parent exit")
            .unwrap();
        reader.join().unwrap();
        assert!(output.contains("parent-exit"), "{output:?}");
        assert!(output.contains("descendant-ready"), "{output:?}");
        fs::write(files.path("release"), b"go").unwrap();
        assert!(!files.path("late-write").exists());
    }
}
