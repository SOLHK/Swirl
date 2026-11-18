use super::*;
use std::io::Cursor;

const ID: &str = "70000000-0000-4000-8000-000000000001";

#[test]
fn launch_epoch_and_duplicate_fields_cannot_be_reinterpreted() {
    let valid = format!(
        r#"{{"packet_worker_schema":1,"request_id":"{ID}","epoch":7,"command":{{"op":"status"}}}}"#
    );
    assert!(request(valid.as_bytes(), Some(7)).is_ok());
    assert!(request(valid.as_bytes(), Some(8)).is_err());
    assert!(request(valid.replace("\"epoch\":7", "\"epoch\":0").as_bytes(), None).is_err());
    assert!(
        request(
            valid
                .replace("\"epoch\":7", "\"epoch\":7,\"epoch\":8")
                .as_bytes(),
            None
        )
        .is_err()
    );
    assert!(
        request(
            valid
                .replace("\"op\":\"status\"", "\"op\":\"stop\",\"unknown\":true")
                .as_bytes(),
            None
        )
        .is_err()
    );
}

#[test]
fn core_boundary_preserves_duplicate_rejection_and_rejects_privileged_or_exposed_listeners() {
    let command = |op: &str, listen: &str| {
        format!(
            r#"{{"control_schema":2,"request_id":"{ID}","op":"{op}","candidate":{{"listen":"{listen}"}}}}"#
        )
    };
    assert!(core_command(&command("start_v2", "127.0.0.1:0"), ID, 0).is_ok());
    assert!(core_command(&command("start_v2", "[::1]:0"), ID, 0).is_ok());
    for listen in ["0.0.0.0:0", "[::]:0", "192.0.2.1:0", "127.0.0.1:1080"] {
        assert!(core_command(&command("start_v2", listen), ID, 0).is_err());
    }
    assert!(core_command(&command("start_v2", "127.0.0.1:0"), ID, 1).is_err());
    for op in [
        "start",
        "native_tun_start",
        "native_tun_recover",
        "probe_start",
    ] {
        assert!(core_command(&command(op, "127.0.0.1:0"), ID, 0).is_err());
    }
    let raw = command("start_v2", "127.0.0.1:0");
    assert!(
        core_command(
            &raw.replace(
                "\"control_schema\":2",
                "\"control_schema\":2,\"control_schema\":2"
            ),
            ID,
            0
        )
        .is_err()
    );
    assert!(core_command(&raw, "70000000-0000-4000-8000-000000000002", 0).is_err());
}

#[test]
fn control_frames_require_newline_and_bound_fragmented_input() {
    let mut input = Cursor::new(b"{\"one\":1}\n{\"two\":2}\n");
    assert_eq!(read_frame(&mut input).unwrap().unwrap(), b"{\"one\":1}\n");
    assert_eq!(read_frame(&mut input).unwrap().unwrap(), b"{\"two\":2}\n");
    assert!(read_frame(&mut input).unwrap().is_none());
    assert!(read_frame(&mut Cursor::new(b"unfinished")).is_err());
    let mut too_long = vec![b'a'; MAX_FRAME];
    too_long.push(b'\n');
    assert!(read_frame(&mut Cursor::new(too_long)).is_err());
}

#[test]
fn escaped_responses_cannot_exceed_the_independent_output_frame_limit() {
    // The JSON string's quotes and final newline are part of the wire limit.
    let exact = Value::String("a".repeat(MAX_FRAME - 3));
    assert_eq!(response_bytes(&exact).unwrap().len() + 1, MAX_FRAME);
    let one_over = Value::String("a".repeat(MAX_FRAME - 2));
    assert!(response_bytes(&one_over).is_err());
    // Escaping grows the serialized frame beyond its in-memory character count.
    let escaped = Value::String("\n".repeat(MAX_FRAME / 2));
    assert!(response_bytes(&escaped).is_err());
}

fn low_token() -> TokenProfile {
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
fn restricted_shape_is_required_without_claiming_broker_authentication() {
    assert!(token_gate(&low_token()).is_ok());
    let cases = [
        TokenProfile {
            elevated: true,
            ..low_token()
        },
        TokenProfile {
            restricted: false,
            ..low_token()
        },
        TokenProfile {
            admin_enabled: true,
            ..low_token()
        },
        TokenProfile {
            admin_deny_only: false,
            ..low_token()
        },
        TokenProfile {
            integrity_rid: 0x2000,
            ..low_token()
        },
        TokenProfile {
            unexpected_enabled_privileges: 1,
            ..low_token()
        },
        TokenProfile {
            enabled_privileges: 2,
            ..low_token()
        },
    ];
    for token in cases {
        assert_eq!(
            token_gate(&token).unwrap_err().kind(),
            io::ErrorKind::PermissionDenied
        );
    }
    let output = status(&None, &low_token(), true);
    assert_eq!(output["state"], "stopped");
    for key in [
        "broker_authenticated",
        "service_principal_authenticated",
        "kernel_identity_enforced",
        "product_broker_integrated",
        "system_kill_switch",
        "network_resources_owned",
        "routes_restored",
    ] {
        assert_eq!(output[key], false, "{key}");
    }
}

#[test]
fn stop_is_idempotent_with_no_core_or_bridge_and_does_not_create_os_resources() {
    let mut controller = Controller::default();
    let mut session = None;
    stop(&mut session, &mut controller).unwrap();
    stop(&mut session, &mut controller).unwrap();
    assert!(controller.cores_v2.is_empty());
}
