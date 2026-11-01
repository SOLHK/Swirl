//! Explicit disposable-runner restricted-token process smoke.
//! It changes only its temporary fixture files, private desktop and child job.

#[cfg(windows)]
mod windows {
    //! Explicit disposable administrator process/ACL fixture. No routes, DNS,
    //! firewall, adapter, account, UAC or installed application is changed.
    use std::{
        ffi::OsString,
        fs::{File, OpenOptions},
        io::{self, BufRead, Read, Seek, SeekFrom, Write},
        os::windows::{
            ffi::OsStrExt,
            io::{AsRawHandle, FromRawHandle, OwnedHandle},
            process::CommandExt,
        },
        path::{Path, PathBuf},
        process::{Command, Stdio},
        ptr::null_mut,
        thread,
        time::Duration,
    };
    use swirl_platform::windows_restricted_worker::{
        RestrictedChild, current_desktop_name, current_token_profile, spawn, spawn_data_plane,
    };
    use windows_sys::Win32::{
        Foundation::{
            CloseHandle, DUPLICATE_SAME_ACCESS, DuplicateHandle, GENERIC_READ, GENERIC_WRITE,
            HANDLE, LocalFree, WAIT_OBJECT_0,
        },
        Security::{
            Authorization::{
                ConvertStringSecurityDescriptorToSecurityDescriptorW, SDDL_REVISION_1,
            },
            *,
        },
        Storage::FileSystem::{CREATE_NEW, CreateFileW, FILE_ATTRIBUTE_NORMAL, FILE_SHARE_READ},
        System::StationsAndDesktops::{CloseDesktop, DESKTOP_READOBJECTS, OpenDesktopW},
        System::Threading::{
            CREATE_NO_WINDOW, GetCurrentProcess, OpenProcess, OpenProcessToken,
            PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_SYNCHRONIZE, WaitForSingleObject,
        },
    };

    const MAIN_ENTER: &str = "restricted smoke entered Rust main\n";
    const CHILD_STDERR: &str =
        "restricted smoke entered Rust main\nrestricted stderr pipe verified\n";

    fn require(value: bool, message: &str) -> io::Result<()> {
        if value {
            Ok(())
        } else {
            Err(io::Error::other(message))
        }
    }

    #[allow(unsafe_code)]
    fn admin_token_sentinel() -> io::Result<OwnedHandle> {
        let mut original = null_mut();
        // SAFETY: current-process token and writable output. Fixture is explicitly
        // elevated; the duplicated inheritable token must be absent in the worker.
        if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_ALL_ACCESS, &mut original) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let mut sentinel = null_mut();
        // SAFETY: live owned original token; output becomes a distinct owned handle.
        let copied = unsafe {
            DuplicateHandle(
                GetCurrentProcess(),
                original,
                GetCurrentProcess(),
                &mut sentinel,
                0,
                1,
                DUPLICATE_SAME_ACCESS,
            )
        };
        let error = (copied == 0).then(io::Error::last_os_error);
        // SAFETY: original token handle is no longer needed after duplication.
        unsafe { CloseHandle(original) };
        if let Some(error) = error {
            return Err(error);
        }
        // SAFETY: successful duplication created a uniquely owned new token handle.
        Ok(unsafe { OwnedHandle::from_raw_handle(sentinel) })
    }

    #[allow(unsafe_code)]
    fn inherited_admin_token(raw: usize) -> bool {
        let mut elevation = TOKEN_ELEVATION::default();
        let mut bytes = 0;
        // SAFETY: this is an intentionally untrusted numeric fixture handle.
        // GetTokenInformation validates it; no ownership is claimed or closed here.
        unsafe {
            GetTokenInformation(
                raw as HANDLE,
                TokenElevation,
                (&mut elevation as *mut TOKEN_ELEVATION).cast(),
                size_of::<TOKEN_ELEVATION>() as u32,
                &mut bytes,
            ) != 0
                && elevation.TokenIsElevated != 0
        }
    }

    #[allow(unsafe_code)]
    fn broker_file(path: &Path) -> io::Result<()> {
        let sddl = "O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;RC;;;OW)"
            .encode_utf16()
            .chain(Some(0))
            .collect::<Vec<_>>();
        let mut descriptor = null_mut();
        // SAFETY: constant SDDL and writable LocalAlloc descriptor output.
        if unsafe {
            ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl.as_ptr(),
                SDDL_REVISION_1,
                &mut descriptor,
                null_mut(),
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let attributes = SECURITY_ATTRIBUTES {
            nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: descriptor,
            bInheritHandle: 0,
        };
        let name = path
            .as_os_str()
            .encode_wide()
            .chain(Some(0))
            .collect::<Vec<_>>();
        // SAFETY: explicit fresh fixture path, no reparse or existing-file adoption;
        // descriptor is applied atomically at creation, then copied by the kernel.
        let handle = unsafe {
            CreateFileW(
                name.as_ptr(),
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ,
                &attributes,
                CREATE_NEW,
                FILE_ATTRIBUTE_NORMAL,
                null_mut(),
            )
        };
        let error = (handle == windows_sys::Win32::Foundation::INVALID_HANDLE_VALUE)
            .then(io::Error::last_os_error);
        // SAFETY: sole LocalAlloc descriptor no longer needed after CreateFile.
        unsafe { LocalFree(descriptor) };
        if let Some(error) = error {
            return Err(error);
        }
        // SAFETY: CreateFile returned a uniquely owned new file handle.
        let mut file = unsafe { File::from_raw_handle(handle) };
        file.write_all(b"broker-private-fixture\n")?;
        file.sync_all()?;
        drop(file);
        Ok(())
    }

    fn child(args: &[OsString]) -> io::Result<()> {
        require(args.len() == 4, "invalid child fixture arguments")?;
        let path = Path::new(&args[1]);
        let raw = args[2]
            .to_str()
            .ok_or_else(|| io::Error::other("invalid sentinel"))?
            .parse()
            .map_err(io::Error::other)?;
        // Read the sentinel before opening any additional token handles ourselves,
        // so handle-value reuse cannot be confused with intended inheritance.
        require(
            !inherited_admin_token(raw),
            "worker inherited an enabled administrator token",
        )?;
        let profile = current_token_profile()?;
        require(
            !profile.elevated
                && profile.restricted
                && !profile.admin_enabled
                && profile.admin_deny_only
                && profile.integrity_rid == 0x1000
                && profile.unexpected_enabled_privileges == 0,
            "child token profile violated restriction",
        )?;
        let mut stdin = io::stdin().lock();
        let mut desktop_expected = String::new();
        if args[3] == "__DESKTOP_FROM_STDIN__" {
            (&mut stdin).take(129).read_line(&mut desktop_expected)?;
        } else {
            desktop_expected = args[3].to_string_lossy().into_owned();
        }
        let desktop = current_desktop_name()?;
        require(
            desktop == desktop_expected.trim_end(),
            "worker did not attach to the explicit private desktop",
        )?;
        let denied = match OpenOptions::new().write(true).open(path) {
            Err(error) => error.raw_os_error() == Some(5),
            Ok(_) => false,
        };
        require(
            denied,
            "low worker can write broker-only file or failure was not access denied",
        )?;
        let keys = std::env::vars_os()
            .map(|(key, _)| key.to_string_lossy().to_ascii_uppercase())
            .collect::<Vec<_>>();
        require(
            keys.len() == 3
                && ["PATH", "SYSTEMROOT", "WINDIR"]
                    .iter()
                    .all(|key| keys.iter().any(|present| present == key)),
            "worker inherited ambient broker environment",
        )?;
        let delegated_io = if args[0] == "--data-plane-child" {
            delegated_io(&mut stdin)?;
            true
        } else {
            false
        };
        let mut input = String::new();
        (&mut stdin).take(65).read_line(&mut input)?;
        require(input == "ping\n", "inherited stdin pipe content mismatch")?;
        writeln!(io::stderr().lock(), "restricted stderr pipe verified")?;
        println!(
            "{}",
            serde_json::json!({"profile":profile,"private_desktop_verified":true,"admin_token_not_inherited":true,
        "broker_write_denied":true,"explicit_environment_verified":true,"stdio_reply":"pong",
        "delegated_file_and_packet_io":delegated_io})
        );
        Ok(())
    }

    #[derive(serde::Deserialize)]
    #[serde(deny_unknown_fields)]
    struct InheritedData {
        packet_input: usize,
        packet_output: usize,
        fake_ip_journal: usize,
    }

    #[allow(unsafe_code)]
    fn delegated_io(input: &mut impl BufRead) -> io::Result<()> {
        let mut line = String::new();
        input.take(1025).read_line(&mut line)?;
        require(
            line.len() <= 1024 && line.ends_with('\n'),
            "invalid resource frame",
        )?;
        let handles: InheritedData = serde_json::from_str(&line).map_err(io::Error::other)?;
        let values = [
            handles.packet_input,
            handles.packet_output,
            handles.fake_ip_journal,
        ];
        require(
            values.iter().all(|value| *value != 0)
                && values[0] != values[1]
                && values[0] != values[2]
                && values[1] != values[2],
            "invalid resource handles",
        )?;
        // SAFETY: only this explicit fixture child consumes the three distinct
        // handles just inherited through the launcher's exact handle list.
        // Their IDs arrive on its private stdin; IDs are not authentication.
        let (mut incoming, mut outgoing, mut journal) = unsafe {
            (
                File::from_raw_handle(handles.packet_input as HANDLE),
                File::from_raw_handle(handles.packet_output as HANDLE),
                File::from_raw_handle(handles.fake_ip_journal as HANDLE),
            )
        };
        journal.try_lock().map_err(io::Error::other)?;
        journal.seek(SeekFrom::Start(0))?;
        let mut original = Vec::new();
        (&mut journal).take(129).read_to_end(&mut original)?;
        require(
            original == b"initial-owned-fake-ip-fixture\n",
            "delegated journal differs",
        )?;
        journal.seek(SeekFrom::End(0))?;
        journal.write_all(b"child-owned-fake-ip-fixture\n")?;
        journal.sync_all()?;
        journal.unlock()?;
        let mut packet = [0; 128];
        incoming.read_exact(&mut packet)?;
        require(packet == [0xa7; 128], "dedicated packet input differs")?;
        outgoing.write_all(&packet)?;
        outgoing.flush()?;
        Ok(())
    }

    fn capture(mut child: RestrictedChild, input: &[u8]) -> io::Result<(u32, Vec<u8>, Vec<u8>)> {
        let mut stdout = child
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("missing stdout"))?;
        let mut stderr = child
            .stderr
            .take()
            .ok_or_else(|| io::Error::other("missing stderr"))?;
        let out = thread::spawn(move || {
            let mut bytes = Vec::new();
            (&mut stdout).take(16385).read_to_end(&mut bytes)?;
            Ok::<_, io::Error>(bytes)
        });
        let err = thread::spawn(move || {
            let mut bytes = Vec::new();
            (&mut stderr).take(16385).read_to_end(&mut bytes)?;
            Ok::<_, io::Error>(bytes)
        });
        let written = if let Some(mut stdin) = child.stdin.take() {
            stdin.write_all(input)
        } else {
            Ok(())
        };
        if written.is_err() {
            let _ = child.kill();
        }
        let status = child.wait(Duration::from_secs(10));
        // Collect every join before propagating failure; child.wait kills/reaps the
        // private job on timeout and closes any descendant-held pipe endpoints.
        let out = out.join();
        let err = err.join();
        let out = out.map_err(|_| io::Error::other("stdout reader panicked"))??;
        let err = err.map_err(|_| io::Error::other("stderr reader panicked"))??;
        written?;
        require(
            out.len() <= 16384 && err.len() <= 16384,
            "worker output exceeded fixture bound",
        )?;
        Ok((status?, out, err))
    }

    #[allow(unsafe_code)]
    fn process_handle(id: u32) -> io::Result<OwnedHandle> {
        // SAFETY: read/synchronize-only handle to an explicit fixture process ID.
        let raw = unsafe {
            OpenProcess(
                PROCESS_SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
                0,
                id,
            )
        };
        if raw.is_null() {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: new owned kernel handle from OpenProcess.
        Ok(unsafe { OwnedHandle::from_raw_handle(raw) })
    }

    #[allow(unsafe_code)]
    fn process_exited(handle: &OwnedHandle) -> bool {
        // SAFETY: borrowed read/synchronize-only process handle and finite wait.
        (unsafe { WaitForSingleObject(handle.as_raw_handle(), 5000) }) == WAIT_OBJECT_0
    }

    #[allow(unsafe_code)]
    fn require_desktop_removed(name: &str) -> io::Result<()> {
        let name = name.encode_utf16().chain(Some(0)).collect::<Vec<_>>();
        // SAFETY: read-only attempt to reopen the exact private fixture desktop
        // in this process's unchanged window station. No desktop is created.
        let handle = unsafe { OpenDesktopW(name.as_ptr(), 0, 0, DESKTOP_READOBJECTS) };
        if handle.is_null() {
            let error = io::Error::last_os_error();
            return if error.raw_os_error() == Some(2) {
                Ok(())
            } else {
                Err(error)
            };
        }
        // SAFETY: this function uniquely owns the newly opened desktop handle.
        if unsafe { CloseDesktop(handle) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Err(io::Error::other(
            "private worker desktop remained after cleanup",
        ))
    }

    fn headless_comparison(executable: &Path, directory: &Path) -> io::Result<serde_json::Value> {
        let probe = executable.with_file_name("windows-headless-worker-probe.exe");
        let worker = spawn(&probe, &["--headless-pipe-probe".into()])?;
        let desktop = worker.desktop_name().to_owned();
        let (exit, stdout, stderr) = capture(worker, b"ping\n")?;
        std::fs::write(directory.join("headless-child-stdout.log"), &stdout)?;
        std::fs::write(directory.join("headless-child-stderr.log"), &stderr)?;
        eprintln!(
            "restricted headless comparison exited: code={exit} hex=0x{exit:08x} stdout_bytes={} stderr_bytes={}",
            stdout.len(),
            stderr.len()
        );
        require_desktop_removed(&desktop)?;
        require(
            exit == 0,
            "headless comparison failed; inspect exact exit and outputs",
        )?;
        require(
            stderr == b"SWIRL_HEADLESS_WORKER_MAIN_ENTERED\n",
            "headless main marker differs",
        )?;
        let result: serde_json::Value =
            serde_json::from_slice(&stdout).map_err(io::Error::other)?;
        require(
            result["ok"] == true
                && result["stdio_reply"] == "pong"
                && result["source_sha"] == option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown")
                && result["desktop_identity_verified"] == false
                && result["product_broker_integrated"] == false
                && result["network_modified"] == false,
            "headless comparison evidence differs",
        )?;
        Ok(result)
    }

    fn run() -> io::Result<()> {
        let args = std::env::args_os().skip(1).collect::<Vec<_>>();
        match args.first().and_then(|s| s.to_str()) {
            Some("--child" | "--data-plane-child") => return child(&args),
            Some("--descendant") => {
                thread::sleep(Duration::from_secs(60));
                return Ok(());
            }
            Some("--parent") => {
                let descendant = Command::new(std::env::current_exe()?)
                    .arg("--descendant")
                    .stdin(Stdio::null())
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .creation_flags(CREATE_NO_WINDOW)
                    .spawn()?;
                println!("{}", descendant.id());
                io::stdout().flush()?;
                let mut bytes = Vec::new();
                io::stdin().take(1).read_to_end(&mut bytes)?;
                return Ok(());
            }
            _ => {}
        }
        require(
            args.len() == 3 && args[0] == "--disposable-environment" && args[1] == "--directory",
            "requires --disposable-environment --directory <fresh absolute path>; no process launched",
        )?;
        let parent = current_token_profile()?;
        require(
            parent.elevated && parent.admin_enabled,
            "requires an independently elevated disposable Windows runner",
        )?;
        let directory = PathBuf::from(&args[2]);
        require(
            directory.is_absolute(),
            "fixture directory must be absolute",
        )?;
        std::fs::create_dir(&directory)?;
        let file = directory.join("broker-only.dat");
        broker_file(&file)?;
        let sentinel = admin_token_sentinel()?;
        let executable = std::env::current_exe()?;
        let broker_desktop = current_desktop_name()?;
        // The expected desktop name is returned only after spawn; ask the child to
        // read it from an explicit pipe command instead of leaking privileged handles.
        let mut probe = spawn(
            &executable,
            &[
                "--child".into(),
                file.as_os_str().to_owned(),
                (sentinel.as_raw_handle() as usize).to_string().into(),
                "__DESKTOP_FROM_STDIN__".into(),
            ],
        )?;
        let expected_desktop = probe.desktop_name().to_owned();
        require(
            current_desktop_name()? == broker_desktop,
            "restricted spawn changed the broker thread desktop",
        )?;
        let mut stdin = probe
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("missing child stdin"))?;
        writeln!(stdin, "{expected_desktop}")?;
        stdin.write_all(b"ping\n")?;
        drop(stdin);
        let (exit, out, err) = capture(probe, b"")?;
        eprintln!(
            "restricted worker child exited: code={exit} hex=0x{exit:08x} stdout_bytes={} stderr_bytes={}",
            out.len(),
            err.len()
        );
        require(
            current_desktop_name()? == broker_desktop,
            "restricted child cleanup changed the broker thread desktop",
        )?;
        require_desktop_removed(&expected_desktop)?;
        std::fs::write(directory.join("child-stdout.log"), &out)?;
        std::fs::write(directory.join("child-stderr.log"), &err)?;
        // Collect this independent comparison before propagating A's failure.
        // It uses the same launcher/token/desktop/job/environment/three pipes.
        // B cannot substitute for A's desktop/token/handle acceptance checks.
        let headless = headless_comparison(&executable, &directory);
        if let Err(error) = &headless {
            eprintln!("headless comparison failed: {error}");
        }
        require(
            exit == 0,
            "restricted worker capability probe failed; inspect preserved stdout/stderr",
        )?;
        let headless = headless?;
        let result: serde_json::Value = serde_json::from_slice(&out).map_err(io::Error::other)?;
        require(
            result["stdio_reply"] == "pong" && err == CHILD_STDERR.as_bytes(),
            "worker output pipe mismatch",
        )?;
        require(
            std::fs::read(&file)? == b"broker-private-fixture\n",
            "worker modified broker fixture",
        )?;
        let journal_path = directory.join("delegated-fake-ip.dat");
        let mut journal = OpenOptions::new()
            .create_new(true)
            .read(true)
            .write(true)
            .open(&journal_path)?;
        journal.write_all(b"initial-owned-fake-ip-fixture\n")?;
        journal.sync_all()?;
        let mut data = spawn_data_plane(
            &executable,
            &[
                "--data-plane-child".into(),
                file.as_os_str().to_owned(),
                (sentinel.as_raw_handle() as usize).to_string().into(),
                "__DESKTOP_FROM_STDIN__".into(),
            ],
            &journal,
        )?;
        drop(journal);
        let data_desktop = data.worker.desktop_name().to_owned();
        require(
            current_desktop_name()? == broker_desktop,
            "data-plane launch changed broker desktop",
        )?;
        let resource_line = serde_json::to_string(&data.inherited).map_err(io::Error::other)?;
        let input = format!("{data_desktop}\n{resource_line}\nping\n");
        data.packet_input.write_all(&[0xa7; 128])?;
        drop(data.packet_input);
        // A failed child is killed/reaped by capture before this bounded pipe
        // reader is joined, so a failed resource test cannot leave it hanging.
        let packet_reader = thread::spawn(move || {
            let mut bytes = Vec::new();
            data.packet_output.take(129).read_to_end(&mut bytes)?;
            Ok::<_, io::Error>(bytes)
        });
        let captured = capture(data.worker, input.as_bytes());
        let packet = packet_reader
            .join()
            .map_err(|_| io::Error::other("packet reader panicked"))?;
        let (data_exit, data_out, data_err) = captured?;
        eprintln!(
            "restricted data-plane child exited: code={data_exit} hex=0x{data_exit:08x} stdout_bytes={} stderr_bytes={}",
            data_out.len(),
            data_err.len()
        );
        std::fs::write(directory.join("data-child-stdout.log"), &data_out)?;
        std::fs::write(directory.join("data-child-stderr.log"), &data_err)?;
        require(
            data_exit == 0,
            "restricted data-plane resource probe failed",
        )?;
        require(packet? == [0xa7; 128], "dedicated packet output differs")?;
        let data_result: serde_json::Value =
            serde_json::from_slice(&data_out).map_err(io::Error::other)?;
        require(
            data_result["delegated_file_and_packet_io"] == true
                && data_result["stdio_reply"] == "pong"
                && data_err == CHILD_STDERR.as_bytes(),
            "delegated child or control response differs",
        )?;
        require(
            std::fs::read(&journal_path)?
                == b"initial-owned-fake-ip-fixture\nchild-owned-fake-ip-fixture\n",
            "delegated journal change differs",
        )?;
        require(
            std::fs::read(&file)? == b"broker-private-fixture\n",
            "broker file changed",
        )?;
        require(
            current_desktop_name()? == broker_desktop,
            "data cleanup changed broker desktop",
        )?;
        require_desktop_removed(&data_desktop)?;
        let mut family = spawn(&executable, &["--parent".into()])?;
        let family_desktop = family.desktop_name().to_owned();
        require(
            current_desktop_name()? == broker_desktop,
            "descendant fixture changed the broker thread desktop",
        )?;
        let stdout = family
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("missing descendant report pipe"))?;
        let (sent, received) = std::sync::mpsc::channel();
        let reader = thread::spawn(move || {
            let mut line = String::new();
            let result = io::BufReader::new(stdout)
                .take(32)
                .read_line(&mut line)
                .map(|_| line);
            let _ = sent.send(result);
        });
        let descendant = received
            .recv_timeout(Duration::from_secs(5))
            .map_err(io::Error::other)
            .and_then(|line| line)
            .and_then(|line| line.trim().parse().map_err(io::Error::other))
            .and_then(process_handle);
        drop(family);
        reader
            .join()
            .map_err(|_| io::Error::other("descendant reporter panicked"))?;
        require(
            process_exited(&descendant?),
            "private job owner loss left descendant running",
        )?;
        require(
            current_desktop_name()? == broker_desktop,
            "descendant cleanup changed the broker thread desktop",
        )?;
        require_desktop_removed(&family_desktop)?;
        println!(
            "{}",
            serde_json::json!({"ok":true,"evidence":"restricted worker process foundation smoke",
        "source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),"child":result,
            "data_plane_child":data_result,
            "headless_comparison":headless,"headless_comparison_verified":true,
            "delegated_packet_pipes_verified":true,"delegated_file_write_verified":true,
            "job_descendants_reaped":true,"parent_desktop_unchanged":true,"private_desktops_removed":true,
            "network_modified":false,"product_broker_integrated":false,
        "network_compatibility_verified":false,"physical_windows_11_acceptance":false})
        );
        Ok(())
    }

    pub fn main() {
        // This fixed marker distinguishes a process which reached Rust main
        // from loader/CRT failure; it contains no paths, tokens or environment.
        eprint!("{MAIN_ENTER}");
        if let Err(error) = run() {
            eprintln!("restricted worker smoke failed: {error}");
            std::process::exit(1);
        }
    }
}

#[cfg(windows)]
fn main() {
    windows::main();
}

#[cfg(not(windows))]
fn main() {
    eprintln!("restricted worker smoke requires Windows; no operation attempted");
    std::process::exit(1);
}
