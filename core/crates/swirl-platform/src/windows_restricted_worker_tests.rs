use super::*;

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
