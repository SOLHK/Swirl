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

fn lan_config() -> Value {
    json!({
        "listen_ip":"192.168.73.1",
        "http_port":17890,
        "socks_port":17891,
        "udp_port_start":17900,
        "udp_port_end":17915,
        "allowed_cidrs":["192.168.73.0/24"],
        "auth":{"username":"lan-test","password":"PRIVATE_LAN_TEST_PASSWORD"},
        "max_connections":64,
        "max_connections_per_client":8,
        "auth_failures_per_minute":5,
        "idle_timeout_secs":300,
        "host_addresses":["192.168.73.1"]
    })
}

#[test]
fn lan_lifecycle_requires_current_v2_identity_and_preserves_main_listener() {
    let mut controller = Controller::default();
    let started = start(&mut controller);
    for operation in ["lan_start", "lan_stop", "lan_status"] {
        let mut request = json!({"control_schema":2,"op":operation,"request_id":REQUEST,"handle":started["handle"],"engine_epoch":"0"});
        if operation == "lan_start" {
            request["config"] = lan_config();
        }
        let response = call(&mut controller, request);
        assert_eq!(response["code"], "EngineEpochMismatch", "{response}");
        assert!(!response.to_string().contains("PRIVATE_LAN_TEST_PASSWORD"));
    }
    for operation in ["lan_status", "lan_stop", "lan_status"] {
        let response = call(
            &mut controller,
            json!({"control_schema":2,"op":operation,"request_id":REQUEST,"handle":started["handle"],"engine_epoch":started["engine_epoch"]}),
        );
        assert_eq!(response["ok"], true, "{response}");
        assert_eq!(response["lan"]["running"], false, "{response}");
        assert_eq!(response["engine_epoch"], started["engine_epoch"]);
    }
    let address = started["address"].as_str().unwrap();
    let socket = std::net::TcpStream::connect(address).unwrap();
    assert!(socket.peer_addr().unwrap().ip().is_loopback());
    assert_eq!(controller.cores_v2.len(), 1);
}

#[test]
fn lan_rejects_wildcard_before_binding_and_never_echoes_credentials() {
    let mut controller = Controller::default();
    let started = start(&mut controller);
    let mut config = lan_config();
    config["listen_ip"] = json!("0.0.0.0");
    let response = call(
        &mut controller,
        json!({"control_schema":2,"op":"lan_start","request_id":REQUEST,"handle":started["handle"],"engine_epoch":started["engine_epoch"],"config":config}),
    );
    assert_eq!(response["ok"], false, "{response}");
    assert!(!response.to_string().contains("PRIVATE_LAN_TEST_PASSWORD"));
    let status = call(
        &mut controller,
        json!({"control_schema":2,"op":"lan_status","request_id":REQUEST,"handle":started["handle"],"engine_epoch":started["engine_epoch"]}),
    );
    assert_eq!(status["lan"]["running"], false);
    assert_eq!(capabilities()["optional"]["lan_proxy"], true);
    assert_eq!(capabilities()["optional"]["lan_proxy_ipv6"], false);
}

#[test]
fn lan_validation_is_pure_and_does_not_claim_network_admission() {
    let mut controller = Controller::default();
    let response = call(
        &mut controller,
        json!({"control_schema":2,"op":"lan_validate","request_id":REQUEST,"config":lan_config()}),
    );
    assert_eq!(response["ok"], true, "{response}");
    assert_eq!(response["request_id"], REQUEST);
    assert_eq!(response["lan_control_schema"], 1);
    assert_eq!(response["validation"]["valid"], true);
    assert_eq!(response["validation"]["network_preflight_required"], true);
    assert!(response.get("lan").is_none());
    assert!(!response.to_string().contains("PRIVATE_LAN_TEST_PASSWORD"));
    assert_eq!(controller.next, 0);
    assert!(controller.cores.is_empty());
    assert!(controller.cores_v2.is_empty());
    assert_eq!(capabilities()["optional"]["lan_proxy_control_schema"], 1);
    assert_eq!(capabilities()["optional"]["lan_proxy_ipv6_listener"], false);
    assert_eq!(capabilities()["optional"]["gateway"], false);
}

#[test]
fn lan_validation_rejects_unsafe_or_unbounded_configuration() {
    let mut controller = Controller::default();
    let invalid_fields = [
        ("listen_ip", json!("0.0.0.0")),
        ("listen_ip", json!("127.0.0.1")),
        ("listen_ip", json!("8.8.8.8")),
        ("listen_ip", json!("::")),
        ("http_port", json!(0)),
        ("socks_port", json!(65536)),
        ("allowed_cidrs", json!([])),
        ("allowed_cidrs", json!(["0.0.0.0/0"])),
        ("auth", json!({"username":"fixture","password":"short"})),
        ("max_connections", json!(0)),
        ("max_connections_per_client", json!(1000000)),
        ("auth_failures_per_minute", json!(0)),
        ("idle_timeout_secs", json!(0)),
        ("host_addresses", json!([])),
        ("unexpected_secret", json!("PRIVATE_LAN_TEST_PASSWORD")),
    ];
    for (field, value) in invalid_fields {
        let mut config = lan_config();
        config[field] = value;
        let response = call(
            &mut controller,
            json!({"control_schema":2,"op":"lan_validate","request_id":REQUEST,"config":config}),
        );
        assert_eq!(response["ok"], false, "accepted field {field}");
        assert!(!response.to_string().contains("PRIVATE_LAN_TEST_PASSWORD"));
        assert!(controller.cores_v2.is_empty());
    }
}

#[test]
fn lan_mutations_reject_unknown_stale_or_malformed_identity() {
    let mut controller = Controller::default();
    let started = start(&mut controller);
    let original_address = started["address"].as_str().unwrap();
    for op in ["lan_start", "lan_stop", "lan_status"] {
        for (handle, epoch) in [
            (json!("999"), started["engine_epoch"].clone()),
            (json!("01"), started["engine_epoch"].clone()),
            (started["handle"].clone(), json!("01")),
            (json!(1), started["engine_epoch"].clone()),
            (started["handle"].clone(), json!(1)),
        ] {
            let mut command = json!({"control_schema":2,"op":op,"request_id":REQUEST,"handle":handle,"engine_epoch":epoch});
            if op == "lan_start" {
                command["config"] = lan_config();
            }
            let response = call(&mut controller, command);
            assert_eq!(response["ok"], false, "{response}");
            assert!(!response.to_string().contains("PRIVATE_LAN_TEST_PASSWORD"));
        }
    }
    assert!(std::net::TcpStream::connect(original_address).is_ok());
    let handle = decimal(started["handle"].as_str().unwrap()).unwrap();
    assert_eq!(
        call(&mut controller, json!({"op":"stop","handle":handle}))["ok"],
        true
    );
    let response = call(
        &mut controller,
        json!({"control_schema":2,"op":"lan_stop","request_id":REQUEST,"handle":started["handle"],"engine_epoch":started["engine_epoch"]}),
    );
    assert_eq!(response["code"], "UnknownV2Handle");
    assert!(controller.cores_v2.is_empty());
}

#[test]
fn lan_control_c_abi_preserves_capacity_and_redacts_invalid_input() {
    let valid = serde_json::to_vec(
        &json!({"control_schema":2,"op":"lan_validate","request_id":REQUEST,"config":lan_config()}),
    )
    .unwrap();
    let invalid = br#"{"control_schema":2,"op":"lan_validate","request_id":"PRIVATE_LAN_TEST_PASSWORD","config":{}}"#.to_vec();
    for (input, expected_ok) in [(valid, true), (invalid, false)] {
        let mut output = vec![0xa5; crate::OUTPUT_CAPACITY];
        // SAFETY: live, disjoint byte vectors satisfy the exported ABI contract.
        let count = unsafe {
            crate::swirl_core_command(
                input.as_ptr(),
                input.len(),
                output.as_mut_ptr(),
                output.len(),
            )
        };
        assert!(count > 0 && (count as usize) < output.len());
        let count = count as usize;
        let response: Value = serde_json::from_slice(&output[..count]).unwrap();
        assert_eq!(response["ok"], expected_ok, "{response}");
        assert!(!response.to_string().contains("PRIVATE_LAN_TEST_PASSWORD"));
        assert!(output[count..].iter().all(|byte| *byte == 0xa5));
        // SAFETY: short capacity is deliberately rejected before any write.
        let rejected = unsafe {
            crate::swirl_core_command(input.as_ptr(), input.len(), output.as_mut_ptr(), 16)
        };
        assert_eq!(rejected, -1);
    }
}
