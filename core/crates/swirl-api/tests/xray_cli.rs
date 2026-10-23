//! Actual swirl-inspect subprocess tests. No shell, file input or network call
//! is needed; every credential is synthetic and private output stays in memory.
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
use swirl_subscription::{
    Config, Outbound,
    xray::{MAX_JSON_INPUT, convert::ConvertedDocument},
};

const HOST: &str = "synthetic-private-endpoint.example.invalid";
const FIRST_USER: &str = "synthetic-first-user";
const FIRST_PASSWORD: &str = "synthetic-first-password";
const SECOND_USER: &str = "synthetic-second-user";
const SECOND_PASSWORD: &str = "synthetic-second-password-密碼/+=-";
const TAG: &str = "synthetic-private-tag";
const UNKNOWN_KEY: &str = "synthetic-private-key";
const UNKNOWN_VALUE: &str = "synthetic-private-value";
const UUID: &str = "00112233-4455-6677-8899-aabbccddeeff";
const MAX_OUTPUT: u64 = 2 * 1024 * 1024;

struct Run {
    code: i32,
    stdout: Vec<u8>,
    value: Value,
}
fn run(args: &[&str], input: &[u8]) -> Run {
    let mut child = Command::new(env!("CARGO_BIN_EXE_swirl-inspect"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut stdin = child.stdin.take().unwrap();
    let input = input.to_vec();
    let writer = thread::spawn(move || stdin.write_all(&input));
    let stdout = child.stdout.take().unwrap();
    let reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        stdout.take(MAX_OUTPUT + 1).read_to_end(&mut bytes).unwrap();
        bytes
    });
    let stderr = child.stderr.take().unwrap();
    let error_reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        stderr.take(MAX_OUTPUT + 1).read_to_end(&mut bytes).unwrap();
        bytes
    });
    let deadline = Instant::now() + Duration::from_secs(15);
    while child.try_wait().unwrap().is_none() {
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            panic!("swirl-inspect process deadline");
        }
        thread::sleep(Duration::from_millis(5));
    }
    let status = child.wait().unwrap();
    if let Err(error) = writer.join().unwrap() {
        assert!(!status.success());
        assert_eq!(error.kind(), std::io::ErrorKind::BrokenPipe);
    }
    let stdout = reader.join().unwrap();
    let stderr = error_reader.join().unwrap();
    assert!(
        stderr.is_empty(),
        "inspector must not emit source data on stderr"
    );
    assert!(stdout.len() <= MAX_OUTPUT as usize);
    let value = serde_json::from_slice(&stdout).expect("one JSON response");
    Run {
        code: status.code().unwrap(),
        stdout,
        value,
    }
}
fn redacted(output: &[u8]) {
    let output = std::str::from_utf8(output).unwrap();
    for secret in [
        HOST,
        FIRST_USER,
        FIRST_PASSWORD,
        SECOND_USER,
        SECOND_PASSWORD,
        TAG,
        UNKNOWN_KEY,
        UNKNOWN_VALUE,
        UUID,
    ] {
        assert!(
            !output.contains(secret),
            "public CLI output contains a fixture secret"
        );
    }
}
fn socks() -> Value {
    json!({"outbounds": [{
        "tag": TAG, "protocol": "socks",
        "settings": {"servers": [{
            "address": HOST, "port": 1080,
            "users": [
                {"user": FIRST_USER, "pass": FIRST_PASSWORD},
                {"user": SECOND_USER, "pass": SECOND_PASSWORD}
            ]
        }]}
    }]})
}
fn bytes(value: &Value) -> Vec<u8> {
    serde_json::to_vec(value).unwrap()
}
fn no_private_fields(value: &Value) {
    for field in ["raw_json", "archive", "native_candidates", "native_config"] {
        assert!(value.get(field).is_none());
    }
}

#[test]
fn no_flag_and_legacy_private_pipeline_keep_their_existing_output() {
    let input = bytes(&json!({"proxies": [{
        "type": "socks5", "name": TAG, "server": HOST, "port": 1080,
        "username": FIRST_USER, "password": FIRST_PASSWORD
    }]}));
    let existing = swirl_subscription::inspect::inspect(&input);
    let report = serde_json::to_value(&existing.report).unwrap();
    let public = run(&[], &input);
    assert_eq!(public.code, 0);
    assert_eq!(public.stdout, bytes(&report));
    redacted(&public.stdout);
    let expected = json!({
        "report": existing.report, "document": existing.document,
        "nodes": existing.originals, "tcpCandidates": existing.tcp_candidates
    });
    let private = run(&["--private-json"], &input);
    assert_eq!(private.code, 0);
    assert_eq!(private.stdout, bytes(&expected));
}

#[test]
fn xray_public_mode_reports_distinct_states_and_safe_source_indices() {
    let input = bytes(&socks());
    let output = run(&["--xray-json"], &input);
    assert_eq!(output.code, 0);
    redacted(&output.stdout);
    no_private_fields(&output.value);
    assert_eq!(output.value["syntax"], "valid");
    assert_eq!(output.value["validation"], "valid");
    assert_eq!(output.value["native_executable_nodes"], 2);
    assert_eq!(output.value["source"], "file");
    assert_eq!(output.value["network_verified"], false);
    assert_eq!(
        output.value["complete_configuration_execution_supported"],
        false
    );
    let nodes = output.value["nodes"].as_array().unwrap();
    assert_eq!(nodes.len(), 2);
    for (index, node) in nodes.iter().enumerate() {
        assert_eq!(node["index"], index);
        assert_eq!(node["protocol"], "socks");
        assert_eq!(node["native_status"], "executable");
        assert_eq!(node["network_verified"], false);
        assert_eq!(node["source"]["server_index"], 0);
        assert_eq!(node["source"]["user_index"], index);
        assert_eq!(
            node["source"]["user_path"],
            format!("outbounds[0].settings.servers[0].users[{index}]")
        );
    }
    let mut unknown = socks();
    unknown["outbounds"][0][UNKNOWN_KEY] = json!(UNKNOWN_VALUE);
    let output = run(&["--xray-json"], &bytes(&unknown));
    assert_eq!(output.code, 0);
    redacted(&output.stdout);
    assert_eq!(output.value["nodes"][0]["native_status"], "blocked");
    assert!(
        output.value["nodes"][0]["diagnostics"]
            .as_array()
            .unwrap()
            .iter()
            .any(|d| d["path"].as_str().unwrap().contains("[unknown]"))
    );
}

#[test]
fn modern_vmess_cli_export_preserves_aead_and_separates_execution_from_evidence() {
    let input = bytes(&json!({"outbounds": [{
        "protocol": "vmess", "settings": {"vnext": [{
            "address": HOST, "port": 443,
            "users": [{"id": UUID, "alterId": 0, "security": "chacha20-poly1305"}]
        }]}
    }]}));
    let public = run(&["--xray-json"], &input);
    assert_eq!(public.code, 0);
    assert_eq!(public.value["native_executable_nodes"], 1);
    assert_eq!(public.value["network_verified"], false);
    redacted(&public.stdout);
    let exported = run(
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "0",
            "--listen",
            "127.0.0.1:0",
        ],
        &input,
    );
    assert_eq!(exported.code, 0);
    let outbound = &exported.value["native_config"]["nodes"][0]["outbound"];
    assert_eq!(outbound["type"], "vmess");
    assert_eq!(outbound["uuid"], UUID);
    assert_eq!(outbound["alter_id"], 0);
    assert_eq!(outbound["security"], "chacha20-poly1305");
    assert_eq!(exported.value["report"]["network_verified"], false);
}

#[test]
fn explicit_private_mode_preserves_bom_raw_archive_and_all_native_candidates() {
    let input = format!("\u{feff}  {}\r\n", socks()).into_bytes();
    let output = run(&["--private-json", "--xray-json"], &input);
    assert_eq!(output.code, 0);
    assert_eq!(output.value["raw_json"].as_str().unwrap().as_bytes(), input);
    let restored = ConvertedDocument::restore(&bytes(&output.value["archive"])).unwrap();
    assert_eq!(restored.raw_json(), input);
    assert_eq!(restored.nodes().len(), 2);
    assert_eq!(
        output.value["native_candidates"].as_array().unwrap().len(),
        2
    );
    assert_eq!(
        output.value["native_candidates"][0]["auth"]["password"],
        FIRST_PASSWORD
    );
    assert_eq!(
        output.value["native_candidates"][1]["auth"]["password"],
        SECOND_PASSWORD
    );
    assert!(output.value.get("native_config").is_none());
    assert_eq!(output.value["report"]["network_verified"], false);
    redacted(&bytes(&output.value["report"]));
}

#[test]
fn explicit_native_export_selects_second_account_without_implicit_first_selection() {
    let output = run(
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "1",
            "--listen",
            "127.0.0.1:0",
        ],
        &bytes(&socks()),
    );
    assert_eq!(output.code, 0);
    let config = Config::parse(&bytes(&output.value["native_config"])).unwrap();
    assert_eq!(config.nodes.len(), 1);
    assert_eq!(config.listen.to_string(), "127.0.0.1:0");
    let Outbound::Socks5 {
        auth: Some(auth), ..
    } = &config.nodes[0].outbound
    else {
        panic!("selected SOCKS5 protocol and authentication must be preserved");
    };
    assert_eq!(auth.username, SECOND_USER);
    assert_eq!(auth.password, SECOND_PASSWORD);
    assert_eq!(output.value["report"]["native_export"]["node_index"], 1);
    assert_eq!(
        output.value["report"]["native_export"]["source"]["user_index"],
        1
    );
    assert_eq!(output.value["report"]["network_verified"], false);
    redacted(&bytes(&output.value["report"]));

    let output = run(
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "2",
            "--listen",
            "[::1]:0",
        ],
        &bytes(&socks()),
    );
    assert_eq!(output.code, 1);
    assert_eq!(output.value["failure_stage"], "native_export");
    assert_eq!(output.value["export_diagnostic"]["code"], "NativeNodeIndex");
    no_private_fields(&output.value);
    redacted(&output.stdout);
}

#[test]
fn malformed_or_unknown_flags_never_enable_private_output() {
    let cases: &[&[&str]] = &[
        &["--xray-json", "--private-json", UNKNOWN_VALUE],
        &["--private-json", UNKNOWN_VALUE],
        &[
            "--native-node",
            "1",
            "--private-json",
            "--listen",
            "127.0.0.1:0",
        ],
        &[
            "--xray-json",
            "--native-node",
            "1",
            "--listen",
            "127.0.0.1:0",
        ],
        &["--xray-json", "--private-json", "--native-node", "1"],
        &["--xray-json", "--private-json", "--listen", "127.0.0.1:0"],
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "-1",
            "--listen",
            "127.0.0.1:0",
        ],
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "+1",
            "--listen",
            "127.0.0.1:0",
        ],
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            UNKNOWN_VALUE,
            "--listen",
            "127.0.0.1:0",
        ],
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "0",
            "--listen",
            "0.0.0.0:1080",
        ],
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "0",
            "--listen",
            "localhost:1080",
        ],
        &["--xray-json", "--xray-json", "--private-json"],
        &["--xray-json", "--private-json", "--private-json"],
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "0",
            "--native-node",
            "1",
            "--listen",
            "127.0.0.1:0",
        ],
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "0",
            "--listen",
            "127.0.0.1:0",
            "--listen",
            "[::1]:0",
        ],
        &["--xray-json", "--private-json", "--native-node"],
        &["--xray-json", "--private-json", "--listen"],
        &[
            "--xray-json",
            "--private-json",
            "--native-node=1",
            "--listen",
            "127.0.0.1:0",
        ],
    ];
    let input = bytes(&socks());
    for args in cases {
        let output = run(args, &input);
        assert_eq!(output.code, 2);
        assert_eq!(output.value["failure_stage"], "arguments");
        assert_eq!(output.value["syntax"], "not_run");
        no_private_fields(&output.value);
        redacted(&output.stdout);
    }
}

#[test]
fn strict_parser_errors_are_not_downgraded_or_echoed() {
    let duplicate = format!("{{\"{UNKNOWN_KEY}\":1,\"{UNKNOWN_KEY}\":2}}");
    let output = run(&["--xray-json", "--private-json"], duplicate.as_bytes());
    assert_eq!(output.code, 1);
    assert_eq!(output.value["syntax"], "rejected");
    assert_eq!(output.value["diagnostics"][0]["code"], "DuplicateJsonKey");
    assert_eq!(output.value["diagnostics"][0]["path"], "[unknown]");
    no_private_fields(&output.value);
    redacted(&output.stdout);

    let malformed = format!("{{\"password\":\"{FIRST_PASSWORD}\",}}");
    let output = run(&["--xray-json", "--private-json"], malformed.as_bytes());
    assert_eq!(output.code, 1);
    assert_eq!(output.value["syntax"], "invalid");
    redacted(&output.stdout);
    no_private_fields(&output.value);

    let mut wrong_type = socks();
    wrong_type["outbounds"][0]["settings"]["servers"][0]["users"][0]["pass"] = json!(7);
    let output = run(&["--xray-json", "--private-json"], &bytes(&wrong_type));
    assert_eq!(output.code, 1);
    assert_eq!(output.value["syntax"], "valid");
    assert_eq!(output.value["validation"], "invalid");
    assert_eq!(output.value["diagnostics"][0]["code"], "ExpectedString");
    redacted(&output.stdout);
    no_private_fields(&output.value);

    let mut bad_port = socks();
    bad_port["outbounds"][0]["settings"]["servers"][0]["port"] = json!(0);
    let output = run(&["--xray-json"], &bytes(&bad_port));
    assert_eq!(output.code, 0); // inspection completed; node validation failed
    assert_eq!(output.value["syntax"], "valid");
    assert_eq!(output.value["validation"], "invalid");
    assert_eq!(output.value["nodes"][0]["native_status"], "blocked");
    redacted(&output.stdout);
}

#[test]
fn input_limit_uses_strict_xray_budget() {
    let input = vec![b' '; MAX_JSON_INPUT + 1];
    let output = run(&["--xray-json", "--private-json"], &input);
    assert_eq!(output.code, 1);
    assert_eq!(output.value["diagnostics"][0]["code"], "JsonInputSize");
    assert_eq!(output.value["failure_stage"], "input_limit");
    no_private_fields(&output.value);
    redacted(&output.stdout);
}

#[test]
fn legacy_vmess_is_preserved_but_native_export_is_rejected_without_private_payload() {
    let input = bytes(&json!({"outbounds": [{
        "protocol": "vmess", "tag": TAG,
        "settings": {"vnext": [{"address": HOST, "port": 443,
            "users": [{"id": UUID, "alterId": 16, "security": "auto"}]}]}
    }]}));
    let output = run(&["--xray-json", "--private-json"], &input);
    assert_eq!(output.code, 0);
    assert_eq!(output.value["report"]["nodes"][0]["protocol"], "vmess");
    assert_eq!(
        output.value["report"]["nodes"][0]["native_status"],
        "blocked"
    );
    assert_eq!(output.value["native_candidates"][0], Value::Null);
    assert_eq!(output.value["report"]["network_verified"], false);
    assert_eq!(output.value["raw_json"].as_str().unwrap().as_bytes(), input);
    redacted(&bytes(&output.value["report"]));

    let output = run(
        &[
            "--xray-json",
            "--private-json",
            "--native-node",
            "0",
            "--listen",
            "127.0.0.1:0",
        ],
        &input,
    );
    assert_eq!(output.code, 1);
    assert_eq!(output.value["failure_stage"], "native_export");
    assert_eq!(
        output.value["export_diagnostic"]["code"],
        "NativeExecutionBlocked"
    );
    assert_eq!(output.value["nodes"][0]["protocol"], "vmess");
    no_private_fields(&output.value);
    redacted(&output.stdout);
}
