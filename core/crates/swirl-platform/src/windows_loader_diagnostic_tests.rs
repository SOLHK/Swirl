use super::*;
use std::sync::atomic::{AtomicU64, Ordering};

#[test]
fn only_first_first_chance_breakpoint_is_handled() {
    let mut seen = false;
    assert_eq!(
        continuation(0xc0000142, 1, &mut seen),
        DBG_EXCEPTION_NOT_HANDLED as u32
    );
    assert!(!seen);
    assert_eq!(
        continuation(EXCEPTION_BREAKPOINT as u32, 0, &mut seen),
        DBG_EXCEPTION_NOT_HANDLED as u32
    );
    assert!(!seen);
    assert_eq!(
        continuation(EXCEPTION_BREAKPOINT as u32, 1, &mut seen),
        DBG_CONTINUE as u32
    );
    assert_eq!(
        continuation(EXCEPTION_BREAKPOINT as u32, 1, &mut seen),
        DBG_EXCEPTION_NOT_HANDLED as u32
    );
}

#[test]
fn debug_text_does_not_guess_or_replace_malformed_unicode() {
    assert_eq!(decode_string(b"loader\0", false).unwrap()["text"], "loader");
    assert_eq!(decode_string(&[0xff, 0xfe], false).unwrap()["hex"], "fffe");
    assert_eq!(decode_string(&[b'A', 0, 0, 0], true).unwrap()["text"], "A");
    assert!(decode_string(b"A", true).is_err());
    assert!(decode_string(&[0x00, 0xd8], true).is_err());
}

#[test]
fn event_ownership_never_selects_process_or_thread_handles_for_closing() {
    // Symbolic values are never passed to Windows or adopted as real owners.
    let mut event = DEBUG_EVENT {
        dwDebugEventCode: CREATE_PROCESS_DEBUG_EVENT,
        ..DEBUG_EVENT::default()
    };
    event.u.CreateProcessInfo = CREATE_PROCESS_DEBUG_INFO {
        hFile: 1usize as HANDLE,
        hProcess: 2usize as HANDLE,
        hThread: 3usize as HANDLE,
        ..CREATE_PROCESS_DEBUG_INFO::default()
    };
    assert_eq!(file_handle(&event), Some(1usize as HANDLE));
    event.dwDebugEventCode = CREATE_THREAD_DEBUG_EVENT;
    assert!(file_handle(&event).is_none());
    event.dwDebugEventCode = EXIT_PROCESS_DEBUG_EVENT;
    assert!(file_handle(&event).is_none());
    event.dwDebugEventCode = LOAD_DLL_DEBUG_EVENT;
    event.u.LoadDll = LOAD_DLL_DEBUG_INFO {
        hFile: 4usize as HANDLE,
        ..LOAD_DLL_DEBUG_INFO::default()
    };
    assert_eq!(file_handle(&event), Some(4usize as HANDLE));
}

#[test]
fn trace_limits_reject_without_appending_an_over_limit_event() {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let path = std::env::temp_dir().join(format!(
        "swirl-loader-model-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    let mut log = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&path)
        .unwrap();
    let (mut count, mut bytes) = (MAX_EVENTS - 1, 0);
    append(&mut log, &json!({"event":"model"}), &mut count, &mut bytes).unwrap();
    let before = log.metadata().unwrap().len();
    assert!(
        append(
            &mut log,
            &json!({"event":"over_limit"}),
            &mut count,
            &mut bytes
        )
        .is_err()
    );
    assert_eq!(log.metadata().unwrap().len(), before);
    count = 0;
    bytes = MAX_TRACE_BYTES;
    assert!(append(&mut log, &json!({}), &mut count, &mut bytes).is_err());
    assert_eq!(log.metadata().unwrap().len(), before);
    drop(log);
    std::fs::remove_file(path).unwrap();
}
