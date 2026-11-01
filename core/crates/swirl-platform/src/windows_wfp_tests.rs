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
                changed = *expected;
                changed.action.r#type = FWP_ACTION_PERMIT;
                assert!(!filter_matches(&changed, expected));
                changed = *expected;
                changed.numFilterConditions = 3;
                assert!(!filter_matches(&changed, expected));
                // SAFETY: with_filter's condition array is live for this callback.
                let mut conditions =
                    unsafe { std::slice::from_raw_parts(expected.filterCondition, 4) }.to_vec();
                conditions[0].conditionValue = FWP_CONDITION_VALUE0::default();
                changed = *expected;
                changed.filterCondition = conditions.as_mut_ptr();
                assert!(!filter_matches(&changed, expected));
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
