use super::*;

#[test]
fn delegated_journal_supports_allocator_io_without_attribute_or_delete_access() {
    use std::{
        fs::OpenOptions,
        io::{Read, Seek, SeekFrom, Write},
        sync::atomic::{AtomicU64, Ordering},
        time::{SystemTime, UNIX_EPOCH},
    };
    use windows_sys::Win32::{
        Foundation::{FILETIME, GetHandleInformation, HANDLE_FLAG_INHERIT},
        Storage::FileSystem::{
            FILE_DISPOSITION_INFO, FileDispositionInfo, SetFileInformationByHandle, SetFileTime,
        },
    };
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let path = std::env::temp_dir().join(format!(
        "swirl-delegated-journal-{}-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        NEXT.fetch_add(1, Ordering::Relaxed),
    ));
    struct Remove(std::path::PathBuf);
    impl Drop for Remove {
        fn drop(&mut self) {
            let _ = std::fs::remove_file(&self.0);
        }
    }
    let _remove = Remove(path.clone());
    let mut source = OpenOptions::new()
        .create_new(true)
        .read(true)
        .write(true)
        .open(&path)
        .unwrap();
    source.write_all(b"prefix").unwrap();
    let duplicate = inherited_fake_ip_journal(&source).unwrap();
    let mut flags = 0;
    // SAFETY: read-only query on the newly delegated temporary-file handle.
    assert_ne!(
        unsafe { GetHandleInformation(duplicate.as_raw_handle(), &mut flags) },
        0
    );
    assert_ne!(flags & HANDLE_FLAG_INHERIT, 0);
    let mut file = File::from(duplicate);
    file.try_lock().unwrap();
    file.seek(SeekFrom::Start(0)).unwrap();
    let mut prefix = [0; 6];
    file.read_exact(&mut prefix).unwrap();
    assert_eq!(&prefix, b"prefix");
    file.write_all(b"-record\n-torn").unwrap();
    file.set_len(14).unwrap();
    file.seek(SeekFrom::End(0)).unwrap();
    file.write_all(b"next\n").unwrap();
    file.sync_all().unwrap();
    assert_eq!(file.metadata().unwrap().len(), 19);
    file.unlock().unwrap();
    let time = FILETIME {
        dwLowDateTime: 1,
        dwHighDateTime: 0,
    };
    // SAFETY: only this synthetic temporary file can be affected. The exact
    // delegated rights must refuse FILE_WRITE_ATTRIBUTES before changing it.
    assert_eq!(
        unsafe { SetFileTime(file.as_raw_handle(), null(), null(), &time) },
        0
    );
    assert_eq!(io::Error::last_os_error().raw_os_error(), Some(5));
    let disposition = FILE_DISPOSITION_INFO { DeleteFile: true };
    // SAFETY: only this synthetic temporary file; DELETE must not be delegated.
    assert_eq!(
        unsafe {
            SetFileInformationByHandle(
                file.as_raw_handle(),
                FileDispositionInfo,
                (&disposition as *const FILE_DISPOSITION_INFO).cast(),
                size_of::<FILE_DISPOSITION_INFO>() as u32,
            )
        },
        0
    );
    assert_eq!(io::Error::last_os_error().raw_os_error(), Some(5));
    assert_eq!(std::fs::read(path).unwrap(), b"prefix-record\nnext\n");
}

#[test]
fn delegated_journal_refuses_anonymous_pipe_before_any_file_io() {
    let (read, _write) = pipe().unwrap();
    let error = inherited_fake_ip_journal(&File::from(read)).unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
    assert!(error.to_string().contains("regular disk file"));
}

#[test]
fn desktop_restoration_is_conditional_and_checks_the_resulting_binding() {
    use std::cell::{Cell, RefCell};
    let original = 1usize as HDESK;
    let private = 2usize as HDESK;
    for starts_private in [false, true] {
        let binding = Cell::new(if starts_private { private } else { original });
        let operations = RefCell::new(Vec::new());
        restore_desktop_binding(
            original,
            || {
                operations.borrow_mut().push("get");
                Ok(binding.get())
            },
            |handle| {
                operations.borrow_mut().push("restore");
                assert_eq!(handle, original);
                binding.set(handle);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(binding.get(), original);
        assert_eq!(
            operations.into_inner(),
            if starts_private {
                vec!["get", "restore", "get"]
            } else {
                vec!["get"]
            }
        );
    }
    let error = restore_desktop_binding(original, || Ok(private), |_| Ok(())).unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
    assert!(error.to_string().contains("did not take effect"));
}

#[test]
fn desktop_restoration_preserves_query_and_set_failures() {
    let original = 1usize as HDESK;
    let private = 2usize as HDESK;
    let query = restore_desktop_binding(
        original,
        || Err(io::Error::from_raw_os_error(6)),
        |_| panic!("query failure must not attempt restoration"),
    )
    .unwrap_err();
    assert_eq!(query.raw_os_error(), Some(6));
    let set = restore_desktop_binding(
        original,
        || Ok(private),
        |_| Err(io::Error::from_raw_os_error(5)),
    )
    .unwrap_err();
    assert_eq!(set.raw_os_error(), Some(5));
}

#[test]
fn cleanup_failure_prevents_success_and_preserves_an_existing_failure() {
    let cleanup = || io::Error::new(io::ErrorKind::PermissionDenied, "CloseDesktop denied");
    let failed_close = checked_cleanup(Ok(42), Err(cleanup())).unwrap_err();
    assert_eq!(failed_close.kind(), io::ErrorKind::PermissionDenied);
    assert_eq!(failed_close.to_string(), "CloseDesktop denied");
    let primary = io::Error::new(io::ErrorKind::InvalidData, "desktop identity changed");
    let both = checked_cleanup::<()>(Err(primary), Err(cleanup())).unwrap_err();
    assert_eq!(both.kind(), io::ErrorKind::InvalidData);
    assert!(both.to_string().contains("desktop identity changed"));
    assert!(both.to_string().contains("CloseDesktop denied"));
    assert_eq!(checked_cleanup(Ok(42), Ok(())).unwrap(), 42);
}

#[test]
fn current_desktop_identity_query_is_read_only_and_stable() {
    let before = current_thread_desktop().unwrap();
    let name = current_desktop_name().unwrap();
    assert!(!name.is_empty());
    assert_eq!(current_thread_desktop().unwrap(), before);
    assert_eq!(object_name(before).unwrap(), name);
}

#[test]
fn environment_is_explicit_sorted_and_excludes_parent_secrets() {
    let encoded = environment(Path::new(r"C:\Windows"));
    assert!(encoded.ends_with(&[0, 0]));
    let entries = encoded
        .split(|unit| *unit == 0)
        .filter(|entry| !entry.is_empty())
        .map(|entry| String::from_utf16(entry).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(
        entries,
        vec![
            r"PATH=C:\Windows\System32",
            r"SystemRoot=C:\Windows",
            r"WINDIR=C:\Windows"
        ]
    );
}

#[test]
fn command_line_preserves_empty_quotes_and_trailing_backslashes() {
    for (argument, expected) in [
        ("", "\"\""),
        ("hello world", "\"hello world\""),
        ("quote\"test", "\"quote\\\"test\""),
        ("C:\\path\\", "\"C:\\path\\\\\""),
    ] {
        assert_eq!(
            String::from_utf16(&quote_argument(OsStr::new(argument)).unwrap()).unwrap(),
            expected
        );
    }
    let line = command_line(
        Path::new(r"C:\Program Files\worker.exe"),
        &[OsString::from("--child"), OsString::from("")],
    )
    .unwrap();
    assert_eq!(line.last(), Some(&0));
    assert_eq!(
        String::from_utf16(&line[..line.len() - 1]).unwrap(),
        "\"C:\\Program Files\\worker.exe\" \"--child\" \"\""
    );
}

#[test]
fn command_line_rejects_nul_and_oversize_before_process_creation() {
    assert!(quote_argument(&OsString::from_wide(&[65, 0, 66])).is_err());
    assert!(
        command_line(
            Path::new(r"C:\worker.exe"),
            &[OsString::from("x".repeat(32768))]
        )
        .is_err()
    );
}

fn valid_profile() -> TokenProfile {
    TokenProfile {
        elevated: false,
        restricted: true,
        admin_enabled: false,
        admin_deny_only: true,
        integrity_rid: 0x1000,
        enabled_privileges: 1,
        unexpected_enabled_privileges: 0,
    }
}

#[test]
fn restricted_gate_rejects_elevation_admin_privileges_or_wrong_integrity() {
    verify_restricted(&valid_profile()).unwrap();
    for change in 0..6 {
        let mut profile = valid_profile();
        match change {
            0 => profile.elevated = true,
            1 => profile.restricted = false,
            2 => profile.admin_enabled = true,
            3 => profile.admin_deny_only = false,
            4 => profile.integrity_rid = 0x2000,
            5 => profile.unexpected_enabled_privileges = 1,
            _ => unreachable!(),
        }
        assert_eq!(
            verify_restricted(&profile).unwrap_err().kind(),
            io::ErrorKind::PermissionDenied
        );
    }
}

#[test]
fn token_query_is_read_only_and_profile_contains_no_user_identity() {
    let observed = current_token_profile().unwrap();
    let serialized = serde_json::to_value(&observed).unwrap();
    assert_eq!(serialized.as_object().unwrap().len(), 7);
    assert!(serialized.get("user_sid").is_none());
    assert!(observed.integrity_rid >= 0x1000);
}

#[test]
fn token_variable_arrays_accept_zero_entries_at_the_header_offset() {
    let groups = TokenBuffer {
        words: vec![0; 2],
        bytes: offset_of!(TOKEN_GROUPS, Groups),
    };
    assert_eq!(*groups.value::<u32>().unwrap(), 0);
    assert!(
        groups
            .array::<SID_AND_ATTRIBUTES>(offset_of!(TOKEN_GROUPS, Groups), 0)
            .unwrap()
            .is_empty()
    );
    assert!(
        groups
            .array::<SID_AND_ATTRIBUTES>(offset_of!(TOKEN_GROUPS, Groups), 1)
            .is_err()
    );
    let privileges = TokenBuffer {
        words: vec![0; 2],
        bytes: offset_of!(TOKEN_PRIVILEGES, Privileges),
    };
    assert_eq!(*privileges.value::<u32>().unwrap(), 0);
    assert!(
        privileges
            .array::<LUID_AND_ATTRIBUTES>(offset_of!(TOKEN_PRIVILEGES, Privileges), 0)
            .unwrap()
            .is_empty()
    );
    assert!(
        privileges
            .array::<LUID_AND_ATTRIBUTES>(offset_of!(TOKEN_PRIVILEGES, Privileges), 1)
            .is_err()
    );
}
