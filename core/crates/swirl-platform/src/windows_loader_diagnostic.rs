//! Explicit diagnostic only: same restricted launch, plus its own debug port.
//! Debugging changes scheduling; collection success is not startup acceptance.
use super::*;
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    thread,
    time::Instant,
};
use windows_sys::Win32::{
    Foundation::{
        CloseHandle, DBG_CONTINUE, DBG_EXCEPTION_NOT_HANDLED, ERROR_SEM_TIMEOUT,
        EXCEPTION_BREAKPOINT,
    },
    Storage::FileSystem::GetFinalPathNameByHandleW,
    System::Diagnostics::Debug::*,
};

const MAX_EVENTS: usize = 256;
const MAX_TRACE_BYTES: usize = 512 * 1024;
const MAX_STRING_BYTES: usize = 4096;
const TRACE_DEADLINE: Duration = Duration::from_secs(10);

fn sdk(operation: &'static str) -> io::Error {
    let error = io::Error::last_os_error();
    io::Error::new(
        error.kind(),
        format!("{operation}: code {}", error.raw_os_error().unwrap_or(0)),
    )
}

fn creator_thread(creator: u32) -> io::Result<()> {
    // SAFETY: read-only identity of the current thread, no object ownership.
    if creator != unsafe { GetCurrentThreadId() } {
        return Err(invalid(
            "loader diagnostic must stay on its creating thread",
        ));
    }
    Ok(())
}

fn wait_event(milliseconds: u32) -> io::Result<Option<DEBUG_EVENT>> {
    let mut event = DEBUG_EVENT::default();
    // SAFETY: initialized writable structure; finite timeout, same creator thread.
    if unsafe { WaitForDebugEventEx(&mut event, milliseconds) } != 0 {
        Ok(Some(event))
    } else if io::Error::last_os_error().raw_os_error() == Some(ERROR_SEM_TIMEOUT as i32) {
        Ok(None)
    } else {
        Err(sdk("WaitForDebugEventEx"))
    }
}

fn file_handle(event: &DEBUG_EVENT) -> Option<HANDLE> {
    // SAFETY: the SDK's event code discriminates the union. Only these hFile
    // values belong to us. hProcess/hThread are debug-port/system-owned and
    // intentionally never converted to OwnedHandle or manually closed.
    let handle = unsafe {
        match event.dwDebugEventCode {
            CREATE_PROCESS_DEBUG_EVENT => event.u.CreateProcessInfo.hFile,
            LOAD_DLL_DEBUG_EVENT => event.u.LoadDll.hFile,
            _ => return None,
        }
    };
    (!handle.is_null()).then_some(handle)
}

fn close_file(event: &DEBUG_EVENT) -> io::Result<()> {
    if let Some(file) = file_handle(event) {
        // SAFETY: exact SDK-owned image-file handle from this single event.
        if unsafe { CloseHandle(file) } == 0 {
            return Err(sdk("CloseDebugEventImageFile"));
        }
    }
    Ok(())
}

fn continue_event(event: &DEBUG_EVENT, status: u32) -> io::Result<()> {
    // SAFETY: exact ids from the uncontinued event on its creating thread.
    if unsafe { ContinueDebugEvent(event.dwProcessId, event.dwThreadId, status as i32) } == 0 {
        return Err(sdk("ContinueDebugEvent"));
    }
    Ok(())
}

fn continuation(code: u32, first_chance: u32, breakpoint_seen: &mut bool) -> u32 {
    if code == EXCEPTION_BREAKPOINT as u32 && first_chance != 0 && !*breakpoint_seen {
        *breakpoint_seen = true;
        DBG_CONTINUE as u32
    } else {
        DBG_EXCEPTION_NOT_HANDLED as u32
    }
}

fn module_name(file: HANDLE) -> io::Result<String> {
    let mut name = vec![0u16; 4096];
    // SAFETY: live event image file; bounded writable UTF-16 output.
    let length = unsafe { GetFinalPathNameByHandleW(file, name.as_mut_ptr(), name.len() as u32, 0) }
        as usize;
    if length == 0 {
        return Err(sdk("GetFinalPathNameByHandleW"));
    }
    if length >= name.len() {
        return Err(invalid("debug image path exceeds bounded buffer"));
    }
    let path = String::from_utf16(&name[..length])
        .map_err(|_| invalid("malformed debug image Unicode"))?;
    Path::new(&path)
        .file_name()
        .and_then(OsStr::to_str)
        .map(str::to_owned)
        .ok_or_else(|| invalid("debug image has no module basename"))
}

fn decode_string(bytes: &[u8], unicode: bool) -> io::Result<Value> {
    if unicode {
        if !bytes.len().is_multiple_of(2) {
            return Err(invalid("odd debug Unicode byte length"));
        }
        let units = bytes
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect::<Vec<_>>();
        let text =
            String::from_utf16(&units).map_err(|_| invalid("malformed debug string Unicode"))?;
        Ok(json!({"encoding":"utf16le","text":text.trim_end_matches('\0')}))
    } else if let Ok(text) = std::str::from_utf8(bytes) {
        // ASCII loader messages are UTF-8. Non-UTF-8 ANSI bytes are retained as
        // hex, rather than claiming a guessed code-page decoding is lossless.
        Ok(json!({"encoding":"ansi_utf8_compatible","text":text.trim_end_matches('\0')}))
    } else {
        let hex = bytes
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        Ok(json!({"encoding":"ansi_bytes","hex":hex}))
    }
}

fn debug_string(process: HANDLE, info: OUTPUT_DEBUG_STRING_INFO) -> io::Result<Value> {
    let unicode = info.fUnicode != 0;
    let advertised = usize::from(info.nDebugStringLength) * if unicode { 2 } else { 1 };
    let size = advertised.min(MAX_STRING_BYTES);
    if size == 0 {
        return Ok(json!({"empty":true,"advertised_bytes":0}));
    }
    if info.lpDebugStringData.is_null() {
        return Err(invalid("null nonempty debug string"));
    }
    let mut bytes = vec![0u8; size];
    let mut transferred = 0;
    // SAFETY: kernel-validated copy from this stopped debuggee's address space
    // into a bounded initialized buffer. Never dereference the remote pointer.
    if unsafe {
        ReadProcessMemory(
            process,
            info.lpDebugStringData.cast(),
            bytes.as_mut_ptr().cast(),
            size,
            &mut transferred,
        )
    } == 0
    {
        return Err(sdk("ReadDebugString"));
    }
    if transferred != size {
        return Err(invalid("partial debug string read"));
    }
    let mut value = decode_string(&bytes, unicode)?;
    value["advertised_bytes"] = json!(advertised);
    value["truncated"] = json!(advertised != size);
    Ok(value)
}

fn describe(
    event: &DEBUG_EVENT,
    process: HANDLE,
    breakpoint_seen: &mut bool,
) -> io::Result<(Value, u32, Option<u32>)> {
    let mut value = json!({"event_code":event.dwDebugEventCode,"process_id":event.dwProcessId,"thread_id":event.dwThreadId});
    let mut status = DBG_CONTINUE as u32;
    let mut exit = None;
    // SAFETY: every union access is guarded by its Windows event discriminant.
    unsafe {
        match event.dwDebugEventCode {
            CREATE_PROCESS_DEBUG_EVENT | LOAD_DLL_DEBUG_EVENT => {
                value["event"] = json!(if event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT {
                    "create_process"
                } else {
                    "load_dll"
                });
                value["module"] = file_handle(event).map(module_name).transpose()?.into();
            }
            CREATE_THREAD_DEBUG_EVENT => value["event"] = json!("create_thread"),
            EXIT_THREAD_DEBUG_EVENT => {
                value["event"] = json!("exit_thread");
                value["exit_code"] = json!(event.u.ExitThread.dwExitCode);
            }
            EXCEPTION_DEBUG_EVENT => {
                let exception = event.u.Exception;
                let code = exception.ExceptionRecord.ExceptionCode as u32;
                status = continuation(code, exception.dwFirstChance, breakpoint_seen);
                value["event"] = json!("exception");
                value["exception_code"] = json!(code);
                value["exception_hex"] = json!(format!("0x{code:08x}"));
                value["first_chance"] = json!(exception.dwFirstChance != 0);
            }
            OUTPUT_DEBUG_STRING_EVENT => {
                value["event"] = json!("debug_string");
                value["message"] = debug_string(process, event.u.DebugString)?;
            }
            UNLOAD_DLL_DEBUG_EVENT => value["event"] = json!("unload_dll"),
            EXIT_PROCESS_DEBUG_EVENT => {
                let code = event.u.ExitProcess.dwExitCode;
                exit = Some(code);
                value["event"] = json!("exit_process");
                value["exit_code"] = json!(code);
                value["exit_hex"] = json!(format!("0x{code:08x}"));
            }
            RIP_EVENT => {
                value["event"] = json!("rip");
                value["error"] = json!(event.u.RipInfo.dwError);
                value["type"] = json!(event.u.RipInfo.dwType);
            }
            _ => return Err(invalid("unknown debug event")),
        }
    };
    value["continue_status"] = json!(status);
    Ok((value, status, exit))
}

fn append(log: &mut File, value: &Value, events: &mut usize, bytes: &mut usize) -> io::Result<()> {
    let mut encoded = serde_json::to_vec(value)?;
    encoded.push(b'\n');
    if *events >= MAX_EVENTS || encoded.len() > MAX_TRACE_BYTES.saturating_sub(*bytes) {
        return Err(invalid("loader trace bound exceeded"));
    }
    log.write_all(&encoded)?;
    log.flush()?;
    *events += 1;
    *bytes += encoded.len();
    Ok(())
}

fn collect(child: &RestrictedChild, log: &mut File) -> io::Result<u32> {
    let creator = child
        .debug_thread
        .ok_or_else(|| invalid("child has no diagnostic debug port"))?;
    creator_thread(creator)?;
    let deadline = Instant::now() + TRACE_DEADLINE;
    let (mut events, mut bytes, mut breakpoint_seen) = (0, 0, false);
    loop {
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "loader trace deadline",
            ));
        }
        let Some(event) = wait_event(50)? else {
            continue;
        };
        let decoded = if event.dwProcessId == child.id {
            describe(&event, child.process.as_raw_handle(), &mut breakpoint_seen)
        } else {
            Err(invalid("debug event belongs to a different process"))
        };
        let status = decoded
            .as_ref()
            .map_or(DBG_EXCEPTION_NOT_HANDLED as u32, |(_, status, _)| *status);
        let recorded = match &decoded {
            Ok((value, _, _)) => append(log, value, &mut events, &mut bytes),
            Err(error) => append(
                log,
                &json!({"event_code":event.dwDebugEventCode,"decode_error":error.to_string()}),
                &mut events,
                &mut bytes,
            ),
        };
        // Even decoding/logging failure must release the stopped process. Close
        // hFile exactly once before continuing; all other event handles are SDK-owned.
        let closed = close_file(&event);
        let continued = continue_event(&event, status);
        let cleanup = checked_cleanup(closed, continued);
        checked_cleanup(recorded, cleanup)?;
        let (_, _, exit) = decoded?;
        if let Some(exit) = exit {
            log.sync_all()?;
            return Ok(exit);
        }
    }
}

pub(super) fn drain_terminated(creator: u32, id: u32, process: HANDLE) -> io::Result<()> {
    creator_thread(creator)?;
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        // SAFETY: original independently owned CreateProcess handle, not an
        // auto-closed debug-event process handle.
        if unsafe { WaitForSingleObject(process, 0) } == WAIT_OBJECT_0 {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "debug termination drain deadline",
            ));
        }
        let Some(event) = wait_event(50)? else {
            continue;
        };
        let close = close_file(&event);
        let status = if event.dwDebugEventCode == EXCEPTION_DEBUG_EVENT {
            DBG_EXCEPTION_NOT_HANDLED as u32
        } else {
            DBG_CONTINUE as u32
        };
        let continued = continue_event(&event, status);
        checked_cleanup(close, continued)?;
        if event.dwProcessId != id {
            return Err(invalid("termination event belongs to another process"));
        }
    }
}

fn reader(
    mut file: File,
    mut capture: File,
) -> io::Result<thread::JoinHandle<io::Result<Vec<u8>>>> {
    thread::Builder::new()
        .name("swirl-loader-output".into())
        .spawn(move || {
            let mut bytes = Vec::new();
            let read = (&mut file)
                .take((MAX_TRACE_BYTES + 1) as u64)
                .read_to_end(&mut bytes);
            let overflow = bytes.len() > MAX_TRACE_BYTES;
            bytes.truncate(MAX_TRACE_BYTES);
            // Preserve each stream's bounded prefix independently, including
            // partial-read/overflow failures. The other reader cannot discard it.
            capture.write_all(&bytes)?;
            capture.sync_all()?;
            read?;
            if overflow {
                return Err(invalid("diagnostic child output bound exceeded"));
            }
            Ok(bytes)
        })
}

fn finish_reader(reader: thread::JoinHandle<io::Result<Vec<u8>>>) -> io::Result<Vec<u8>> {
    let deadline = Instant::now() + Duration::from_secs(1);
    while !reader.is_finished() {
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "diagnostic output reader did not finish",
            ));
        }
        thread::sleep(Duration::from_millis(5));
    }
    reader
        .join()
        .map_err(|_| invalid("diagnostic output reader panicked"))?
}

/// Disposable-only startup diagnosis of the preapproved tiny headless probe.
/// Caller supplies a fresh fixture directory and approved copied image. There
/// are no extra privileges, inherited handles, or relaxed policy paths.
pub fn trace_headless_startup(
    executable: &Path,
    fake_ip_journal: &File,
    directory: &Path,
) -> io::Result<Value> {
    let mut log = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(directory.join("loader-events.jsonl"))?;
    let stdout_log = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(directory.join("child-stdout.log"))?;
    let stderr_log = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(directory.join("child-stderr.log"))?;
    // DEBUG_ONLY_THIS_PROCESS is the sole creation-flag difference. Creation,
    // waiting, continuing and diagnostic cleanup all stay on this caller thread.
    let mut child = spawn_data_plane_inner(
        executable,
        &[OsString::from("--headless-pipe-probe")],
        fake_ip_journal,
        true,
    )?;
    let out = reader(
        child
            .worker
            .stdout
            .take()
            .ok_or_else(|| invalid("missing diagnostic stdout"))?,
        stdout_log,
    )?;
    let err = reader(
        child
            .worker
            .stderr
            .take()
            .ok_or_else(|| invalid("missing diagnostic stderr"))?,
        stderr_log,
    )?;
    let sent = child
        .worker
        .stdin
        .take()
        .ok_or_else(|| invalid("missing diagnostic stdin"))?
        .write_all(b"ping\n");
    let trace = sent.and_then(|()| collect(&child.worker, &mut log));
    let synced = log.sync_all();
    let cleanup = child.worker.kill();
    // Job termination closes child pipe ends before joining these bounded
    // drains. No descendant may escape this private kill-on-close Job.
    let stdout = finish_reader(out);
    let stderr = finish_reader(err);
    let mut result = json!({"schema":1,"diagnostic_only":true,"original_required_smoke_replaced":false,
        "source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unrecorded"),
        "trace_complete":trace.is_ok() && synced.is_ok(),"cleanup_complete":cleanup.is_ok(),"startup_verified":false,
        "max_events":MAX_EVENTS,"max_trace_bytes":MAX_TRACE_BYTES,"max_debug_string_bytes":MAX_STRING_BYTES,
        "deadline_ms":TRACE_DEADLINE.as_millis(),"inherited_handle_count":6,
        "debug_only_this_process":true,"security_policy_relaxed":false});
    if let Ok(exit) = trace.as_ref() {
        result["child_exit_code"] = json!(exit);
        result["child_exit_hex"] = json!(format!("0x{exit:08x}"));
    }
    if let Err(error) = &trace {
        result["trace_error"] = json!(error.to_string());
    }
    if let Err(error) = &synced {
        result["trace_sync_error"] = json!(error.to_string());
    }
    if let Err(error) = &cleanup {
        result["cleanup_error"] = json!(error.to_string());
    }
    let output = checked_cleanup(
        stdout,
        stderr
            .as_ref()
            .map(|_| ())
            .map_err(|error| io::Error::new(error.kind(), error.to_string())),
    );
    if let Ok(stderr) = &stderr {
        result["startup_verified"] = json!(
            trace.as_ref().ok() == Some(&0)
                && stderr
                    .windows(b"SWIRL_HEADLESS_WORKER_MAIN_ENTERED".len())
                    .any(|window| window == b"SWIRL_HEADLESS_WORKER_MAIN_ENTERED")
        );
    }
    if let Err(error) = &output {
        result["output_error"] = json!(error.to_string());
    }
    std::fs::write(
        directory.join("loader-result.json"),
        serde_json::to_vec_pretty(&result)?,
    )?;
    checked_cleanup(trace.map(|_| ()), cleanup)?;
    synced?;
    output?;
    Ok(result)
}

#[cfg(test)]
#[path = "windows_loader_diagnostic_tests.rs"]
mod tests;
