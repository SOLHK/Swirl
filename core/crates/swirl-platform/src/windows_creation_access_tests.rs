//! Pure SDK-mapping/descriptor-memory checks. No host token, AccessCheck,
//! desktop/window-station creation, process launch or permission change.
use super::*;

fn mapping_tuple(mapping: GENERIC_MAPPING) -> (u32, u32, u32, u32) {
    (
        mapping.GenericRead,
        mapping.GenericWrite,
        mapping.GenericExecute,
        mapping.GenericAll,
    )
}

#[test]
fn desktop_mapping_matches_documented_sdk_rights_without_granting_them() {
    assert_eq!(
        mapping_tuple(creation_desktop_mapping()),
        (0x20041, 0x200be, 0x20100, 0xf01ff)
    );
    assert_ne!(creation_desktop_mapping().GenericAll & !0x20083, 0);
}

#[test]
fn window_station_visibility_selects_distinct_official_generic_mappings() {
    assert_eq!(
        mapping_tuple(creation_station_mapping(true)),
        (0x20303, 0x2001c, 0x20060, 0xf037f)
    );
    assert_eq!(
        mapping_tuple(creation_station_mapping(false)),
        (0x20103, 0x2001c, 0x20020, 0xf013f)
    );
}

#[test]
fn unknown_access_is_never_serialized_as_a_success_or_implicit_denial() {
    let report = CreationAccessDecision::unknown(
        GENERIC_ALL,
        CreationProbeError::new("GetUserObjectSecurity", io::Error::from_raw_os_error(5)),
    );
    assert_eq!(
        serde_json::to_value(report).unwrap(),
        serde_json::json!({
            "requested_mask":GENERIC_ALL,"mapped_mask":null,"api_success":null,
            "allowed":null,"granted_mask":null,
            "error":{"operation":"GetUserObjectSecurity","win32_error":5},
        })
    );
}

#[test]
fn probe_errors_do_not_serialize_identity_paths_or_arbitrary_error_text() {
    let private = "private-user-SID C:\\private\\worker.exe";
    let report = CreationProbeError::new("descriptor size", io::Error::other(private));
    let serialized = serde_json::to_value(report).unwrap();
    assert_eq!(
        serialized,
        serde_json::json!({"operation":"descriptor size","win32_error":null})
    );
    assert!(!serialized.to_string().contains(private));
}

#[test]
fn descriptor_and_privilege_buffers_reject_unbounded_or_empty_lengths() {
    for bytes in [0, 1024 * 1024 + 1, u32::MAX] {
        assert_eq!(
            creation_probe_buffer(bytes).unwrap_err().kind(),
            io::ErrorKind::InvalidInput
        );
    }
    for bytes in [1, 7, 8, 9, 1024] {
        let buffer = creation_probe_buffer(bytes).unwrap();
        assert!(buffer.len() * size_of::<usize>() >= bytes as usize);
        assert!(buffer.len() * size_of::<usize>() < bytes as usize + size_of::<usize>());
    }
}

#[test]
fn mandatory_label_report_reads_actual_binary_descriptor_and_distinguishes_absence() {
    let low = LocalDescriptor::new("O:BAG:BAD:P(A;;RC;;;BA)S:(ML;;NW;;;LW)").unwrap();
    let label = creation_object_label(low.0).unwrap().unwrap();
    assert_eq!(
        serde_json::to_value(label).unwrap(),
        serde_json::json!({"integrity_rid":0x1000,"mandatory_policy":1})
    );
    let absent = LocalDescriptor::new("O:BAG:BAD:P(A;;RC;;;BA)").unwrap();
    assert!(creation_object_label(absent.0).unwrap().is_none());
}
