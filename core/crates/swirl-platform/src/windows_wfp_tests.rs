use super::*;

fn policy() -> ScopedPolicy {
    ScopedPolicy {
        schema: 1,
        owner: [7; 16],
        application: "C:\\approved\\wfp-smoke.exe".into(),
        rules: vec![ScopedRule {
            endpoint: "127.0.0.1:34567".parse().unwrap(),
            protocol: Protocol::Tcp,
            action: Action::Block,
        }],
    }
}

#[test]
fn scoped_policy_rejects_host_wide_targets_and_unowned_identity_before_ffi() {
    let valid = policy();
    valid.validate().unwrap();
    for endpoint in [
        "0.0.0.0:80",
        "1.1.1.1:443",
        "[::]:53",
        "[2001:db8::1]:53",
        "127.0.0.1:0",
        "[::1%1]:53",
    ] {
        let mut invalid = valid.clone();
        invalid.rules[0].endpoint = endpoint.parse().unwrap();
        assert!(invalid.validate().is_err(), "{endpoint}");
    }
    let mut invalid = valid.clone();
    invalid.owner = [0; 16];
    assert!(invalid.validate().is_err());
    invalid = valid.clone();
    invalid.application = "untrusted-relative.exe".into();
    assert!(invalid.validate().is_err());
    for path in [
        r"C:drive-relative.exe",
        r"\root-relative.exe",
        r"\\server\share\smoke.exe",
        r"\\?\UNC\server\share\smoke.exe",
        r"\\.\pipe\smoke.exe",
        r"\\?\GLOBALROOT\Device\smoke.exe",
    ] {
        invalid = valid.clone();
        invalid.application = path.into();
        assert!(invalid.validate().is_err(), "{path}");
    }
    invalid = valid;
    invalid.rules.clear();
    assert!(invalid.validate().is_err());
}

#[test]
fn receipt_reopen_keeps_filter_keys_and_another_owner_cannot_claim_them() {
    let original = policy();
    let reopened: ScopedPolicy = serde_json::from_slice(&original.metadata().unwrap()).unwrap();
    assert_eq!(reopened, original);
    assert!(same_guid(&original.key(0), &reopened.key(0)));
    assert!(!same_guid(&original.key(0), &original.key(1)));
    let mut another = original.clone();
    another.owner = [8; 16];
    assert!(!same_guid(&original.key(0), &another.key(0)));
    let mut unknown = serde_json::to_value(&original).unwrap();
    unknown["host_wide"] = serde_json::json!(true);
    assert!(serde_json::from_value::<ScopedPolicy>(unknown).is_err());
}

#[test]
fn scoped_filter_verifier_rejects_broadened_application_protocol_flags_or_action() {
    for endpoint in ["127.0.0.1:34567", "[::1]:34567"] {
        let mut policy = policy();
        policy.rules[0].endpoint = endpoint.parse().unwrap();
        let mut metadata = policy.metadata().unwrap();
        let mut application_bytes = b"application-id".to_vec();
        let app = blob(&mut application_bytes);
        with_filter(
            &policy,
            0,
            &policy.rules[0],
            &app,
            &mut metadata,
            |expected| {
                assert!(filter_matches(expected, expected));
                let mut changed = *expected;
                changed.flags |= FWPM_FILTER_FLAG_CLEAR_ACTION_RIGHT;
                assert!(!filter_matches(&changed, expected));
                assert_ne!(
                    filter_summary(&changed, expected)["flags"]["actual"],
                    filter_summary(&changed, expected)["flags"]["expected"]
                );
                changed = *expected;
                changed.action.r#type = FWP_ACTION_PERMIT;
                assert!(!filter_matches(&changed, expected));
                assert_eq!(
                    filter_summary(&changed, expected)["action"]["actual"],
                    FWP_ACTION_PERMIT
                );
                changed = *expected;
                changed.numFilterConditions = 3;
                assert!(!filter_matches(&changed, expected));
                assert_eq!(
                    filter_summary(&changed, expected)["condition_count"]["actual"],
                    3
                );
                // SAFETY: with_filter's condition array is live for this callback.
                let mut conditions =
                    unsafe { std::slice::from_raw_parts(expected.filterCondition, 4) }.to_vec();
                conditions[0].conditionValue = FWP_CONDITION_VALUE0::default();
                changed = *expected;
                changed.filterCondition = conditions.as_mut_ptr();
                assert!(!filter_matches(&changed, expected));
                let diagnosis = filter_summary(&changed, expected);
                assert_eq!(diagnosis["conditions"][0]["name"], "ALE_APP_ID");
                assert_eq!(diagnosis["conditions"][0]["matching_conditions"], 0);
                Ok(())
            },
        )
        .unwrap();
    }
}

#[test]
fn scoped_permit_stays_overridable_in_its_own_sublayer() {
    let mut policy = policy();
    policy.rules[0].action = Action::SoftPermit;
    let mut metadata = policy.metadata().unwrap();
    let mut bytes = vec![1, 2, 3];
    let app = blob(&mut bytes);
    with_filter(
        &policy,
        0,
        &policy.rules[0],
        &app,
        &mut metadata,
        |filter| {
            assert_eq!(filter.flags, FWPM_FILTER_FLAG_PERSISTENT);
            assert_eq!(filter.flags & FWPM_FILTER_FLAG_CLEAR_ACTION_RIGHT, 0);
            assert_eq!(filter.action.r#type, FWP_ACTION_PERMIT);
            assert!(same_guid(&filter.subLayerKey, &SUBLAYER));
            assert_eq!(filter.numFilterConditions, 4);
            Ok(())
        },
    )
    .unwrap();
}

#[test]
fn security_descriptor_is_admin_owned_protected_and_has_no_creator_user_grant() {
    let descriptor = SecurityDescriptor::new().unwrap();
    let shape = security_shape(descriptor.0).unwrap();
    assert!(shape.protected);
    assert_eq!(
        shape.owner,
        [1, 2, 0, 0, 0, 0, 0, 5, 32, 0, 0, 0, 32, 2, 0, 0]
    );
    assert_eq!(
        shape
            .grants
            .iter()
            .filter(|(mask, _)| *mask == 0x000f07ff)
            .count(),
        2
    );
    assert_eq!(
        shape
            .grants
            .iter()
            .filter(|(mask, _)| *mask == 0x00020000)
            .count(),
        1
    );
    assert_eq!(shape.grants.len(), 3);
}

#[test]
fn security_diagnostic_classifies_known_sids_and_hashes_private_values() {
    let shape = SecurityShape {
        owner: b"PRIVATE_OWNER_SID".to_vec(),
        protected: false,
        grants: vec![(0x000f07ff, b"PRIVATE_GRANTEE_SID".to_vec())],
    };
    let summary = security_summary(&shape).to_string();
    assert!(summary.contains("sha256:"));
    assert!(summary.contains("0x000f07ff"));
    assert!(!summary.contains("PRIVATE_OWNER_SID"));
    assert!(!summary.contains("PRIVATE_GRANTEE_SID"));
    let descriptor = SecurityDescriptor::new().unwrap();
    let shape = security_shape(descriptor.0).unwrap();
    let summary = security_summary(&shape).to_string();
    for known in ["BUILTIN_ADMINISTRATORS", "LOCAL_SYSTEM", "OWNER_RIGHTS"] {
        assert!(summary.contains(known));
    }
}

#[test]
fn early_security_rejections_report_acl_structure_without_private_owner_sid() {
    for (sddl, expected) in [
        (
            "O:S-1-5-21-111111-222222-333333-1001G:BAD:P(A;;GA;;;BA)(A;;GA;;;SY)",
            "ace_count=Some(2)",
        ),
        ("O:BAG:BAD:P(D;;GA;;;SY)(A;;GA;;;BA)(A;;RC;;;OW)", "type=1"),
        (
            "O:BAG:BAD:P(A;CI;GA;;;SY)(A;;GA;;;BA)(A;;RC;;;OW)",
            "flags=0x02",
        ),
    ] {
        let wide = sddl.encode_utf16().chain(Some(0)).collect::<Vec<_>>();
        let mut raw = null_mut();
        // SAFETY: pure local descriptor conversion; no OS object is created or changed.
        assert_ne!(
            unsafe {
                ConvertStringSecurityDescriptorToSecurityDescriptorW(
                    wide.as_ptr(),
                    SDDL_REVISION_1,
                    &mut raw,
                    null_mut(),
                )
            },
            0
        );
        let descriptor = SecurityDescriptor(raw);
        let error = security_shape(descriptor.0).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
        assert!(error.to_string().contains(expected), "{error}");
        assert!(!error.to_string().contains("111111"));
    }
}

#[test]
fn sdk_diagnostics_preserve_error_kind_and_include_fixed_operation_and_code() {
    let original = io::Error::from_raw_os_error(5);
    let kind = original.kind();
    let error = context("FwpmProviderAdd0", original);
    assert_eq!(error.kind(), kind);
    assert!(error.to_string().contains("FwpmProviderAdd0"));
    assert!(error.to_string().contains("0x00000005"));
}

#[test]
fn filter_diagnostics_exclude_application_path_id_and_receipt_contents() {
    let mut policy = policy();
    policy.application = r"C:\PRIVATE_PATH_SENTINEL\worker.exe".into();
    let mut metadata = policy.metadata().unwrap();
    let mut app_bytes = b"PRIVATE_APPLICATION_ID_SENTINEL".to_vec();
    let app = blob(&mut app_bytes);
    with_filter(
        &policy,
        0,
        &policy.rules[0],
        &app,
        &mut metadata,
        |expected| {
            let mut changed = *expected;
            changed.numFilterConditions = 3;
            assert!(!filter_matches(&changed, expected));
            let diagnosis = filter_summary(&changed, expected).to_string();
            assert!(diagnosis.contains("condition_count"));
            assert!(!diagnosis.contains("PRIVATE_PATH_SENTINEL"));
            assert!(!diagnosis.contains("PRIVATE_APPLICATION_ID_SENTINEL"));
            Ok(())
        },
    )
    .unwrap();
}
