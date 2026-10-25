use super::*;
const STORE: &str = "40000000-0000-4000-8000-000000000001";
const START: &str = "50000000-0000-4000-8000-000000000001";
const REQUEST: &str = "50000000-0000-4000-8000-000000000002";
const NODE: &str = "10000000-0000-4000-8000-000000000001";
fn candidate() -> Value {
    json!({"schema":2,"listen":"127.0.0.1:0","nodes":[{"id":NODE,"outbound":{"type":"socks5","host":"127.0.0.1","port":9,"auth":null}}],"policy":{"schema":2,"mode":"global","default_policy":{"id":"policy:default","target":{"kind":"node","id":NODE}}}})
}
fn call(controller: &mut Controller, value: Value) -> Value {
    controller.dispatch(&serde_json::to_vec(&value).unwrap())
}
fn start(controller: &mut Controller) -> Value {
    let result = call(
        controller,
        json!({"control_schema":2,"op":"start_v2","request_id":START,"store_id":STORE,"saved_revision":"1","candidate":candidate()}),
    );
    assert_eq!(result["ok"], true, "{result}");
    result
}
fn prepare(controller: &mut Controller, start: &Value) -> Value {
    let result = call(
        controller,
        json!({"control_schema":2,"op":"prepare_configuration_v2","request_id":REQUEST,"handle":start["handle"],"engine_epoch":start["engine_epoch"],"store_id":STORE,"base_saved_revision":"1","candidate_revision":"2","expected_generation":"1","base_applied_revision":"1","candidate":candidate()}),
    );
    assert_eq!(result["ok"], true, "{result}");
    result
}
#[test]
fn offline_validation_is_pure_and_draft_default_is_not_a_listener() {
    let mut controller = Controller::default();
    let mut config = candidate();
    config["policy"]["default_policy"]["target"] = json!({"kind":"unconfigured"});
    let result = call(
        &mut controller,
        json!({"control_schema":2,"op":"validate_configuration_v2","request_id":REQUEST,"candidate":config}),
    );
    assert_eq!(result["ok"], true, "{result}");
    assert_eq!(result["plan_digest"].as_str().unwrap().len(), 64);
    assert_eq!(
        (
            controller.next,
            controller.cores.len(),
            controller.cores_v2.len()
        ),
        (0, 0, 0)
    );
}
#[test]
fn activation_requires_durable_finish_and_returns_actual_revision() {
    let mut controller = Controller::default();
    let started = start(&mut controller);
    let prepared = prepare(&mut controller, &started);
    let activated = call(
        &mut controller,
        json!({"control_schema":2,"op":"activate_configuration_v2","request_id":REQUEST,"handle":started["handle"],"engine_epoch":started["engine_epoch"],"prepared_token":prepared["prepared_token"],"plan_digest":prepared["plan_digest"],"candidate_revision":"2","expected_generation":"1"}),
    );
    assert_eq!(
        (
            activated["ok"].clone(),
            activated["applied_revision"].clone(),
            activated["generation"].clone(),
            activated["transaction_state"].clone()
        ),
        (json!(true), json!("2"), json!("2"), json!("committing"))
    );
    let finished = call(
        &mut controller,
        json!({"control_schema":2,"op":"finish_configuration_v2","request_id":REQUEST,"handle":started["handle"],"engine_epoch":started["engine_epoch"],"prepared_token":prepared["prepared_token"],"durable_receipt":{"store_id":STORE,"request_id":REQUEST,"saved_revision":"2","plan_digest":prepared["plan_digest"]}}),
    );
    assert_eq!(
        (
            finished["ok"].clone(),
            finished["outcome"].clone(),
            finished["applied_mode"].clone()
        ),
        (json!(true), json!("applied"), json!("global"))
    );
}
#[test]
fn prepared_failure_discards_only_after_old_receipt_reconciles() {
    let mut controller = Controller::default();
    let started = start(&mut controller);
    let prepared = prepare(&mut controller, &started);
    let old = json!({"store_id":STORE,"request_id":START,"saved_revision":"1","plan_digest":started["plan_digest"]});
    let rollback = call(
        &mut controller,
        json!({"control_schema":2,"op":"rollback_configuration_v2","request_id":REQUEST,"handle":started["handle"],"engine_epoch":started["engine_epoch"],"prepared_token":prepared["prepared_token"],"expected_generation":"1","old_committed":old}),
    );
    assert_eq!(
        (
            rollback["ok"].clone(),
            rollback["applied_revision"].clone(),
            rollback["generation"].clone()
        ),
        (json!(true), json!("1"), json!("1"))
    );
    let finish = call(
        &mut controller,
        json!({"control_schema":2,"op":"finish_configuration_v2","request_id":REQUEST,"handle":started["handle"],"engine_epoch":started["engine_epoch"],"prepared_token":prepared["prepared_token"],"durable_receipt":old}),
    );
    assert_eq!(finish["outcome"], "rolled_back");
}
#[test]
fn legacy_mutations_cannot_bypass_v2_but_read_only_and_stop_work() {
    let mut controller = Controller::default();
    let started = start(&mut controller);
    let handle = decimal(started["handle"].as_str().unwrap()).unwrap();
    let failed = call(
        &mut controller,
        json!({"op":"select","handle":handle,"id":NODE}),
    );
    assert_eq!(failed["error"], "V2MutationRequiresTransaction");
    assert_eq!(
        call(&mut controller, json!({"op":"snapshot","handle":handle}))["status"]["configuration"]
            ["applied_revision"],
        "1"
    );
    assert_eq!(
        call(&mut controller, json!({"op":"stop","handle":handle}))["ok"],
        true
    );
    assert!(controller.cores_v2.is_empty());
}
#[test]
fn stale_epoch_and_noncanonical_revision_do_not_prepare() {
    let mut controller = Controller::default();
    let started = start(&mut controller);
    let result = call(
        &mut controller,
        json!({"control_schema":2,"op":"configuration_status_v2","request_id":START,"handle":started["handle"],"engine_epoch":"0"}),
    );
    assert_eq!(result["code"], "EngineEpochMismatch");
    let mut request = json!({"control_schema":2,"op":"prepare_configuration_v2","request_id":REQUEST,"handle":started["handle"],"engine_epoch":started["engine_epoch"],"store_id":STORE,"base_saved_revision":"1","candidate_revision":"02","expected_generation":"1","base_applied_revision":"1","candidate":candidate()});
    assert_eq!(
        call(&mut controller, request.clone())["code"],
        "IdentityDecimal"
    );
    request["candidate_revision"] = json!(2);
    assert_eq!(
        call(&mut controller, request)["code"],
        "CommandInvalidOrUnsupported"
    );
}
#[test]
fn duplicate_nested_keys_and_unknown_secrets_never_fall_back_or_echo() {
    let mut controller = Controller::default();
    let invalid=br#"{"control_schema":2,"op":"validate_configuration_v2","request_id":"50000000-0000-4000-8000-000000000002","candidate":{"schema":2,"schema":1,"password":"PRIVATE_FIXTURE"}}"#;
    let result = controller.dispatch(invalid);
    assert_eq!(result["ok"], false);
    assert!(!result.to_string().contains("PRIVATE_FIXTURE"));
    assert!(controller.cores_v2.is_empty());
}
