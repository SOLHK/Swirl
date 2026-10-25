use super::*;
#[test]
fn decimal_identities_reject_lossy_or_noncanonical_numbers() {
    for value in ["", "01", "-1", "1.0", "1e3", "18446744073709551616", " 1"] {
        assert_eq!(decimal(value), Err("IdentityDecimal"));
    }
    assert_eq!(decimal("18446744073709551615"), Ok(u64::MAX));
}
#[test]
fn runtime_schema_rejects_legacy_fields_instead_of_falling_back() {
    let value = json!({"schema":2,"listen":"127.0.0.1:0","nodes":[],"selected":"fixture","policy":{"schema":2,"mode":"direct","default_policy":{"id":"policy:default","target":{"kind":"unconfigured"}}}});
    assert!(serde_json::from_value::<RuntimeConfig>(value).is_err());
}
