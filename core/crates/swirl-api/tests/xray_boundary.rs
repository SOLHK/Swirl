//! Qt's caller-owned UTF-8 buffers -> actual C ABI -> validated Rust Core.
//! Only synthetic configuration and loopback listeners are used. Lifecycle
//! acceptance here is not a proxy handshake, TLS, REALITY, or network test.
use serde_json::{Value, json};
use std::{
    net::{SocketAddr, TcpListener},
    sync::{Mutex, MutexGuard},
};
use swirl_api::{OUTPUT_CAPACITY, swirl_core_abi_version, swirl_core_command};
use swirl_subscription::{
    Config,
    xray::{
        InputSource,
        convert::{ConvertedDocument, NativeStatus, Protocol, import_document},
    },
};

const USER: &str = "synthetic-boundary-user";
const PASSWORD: &str = "synthetic-boundary-password";
const UUID: &str = "00112233-4455-6677-8899-aabbccddeeff";
const PRIVATE_FIELD: &str = "synthetic-private-field-name";
const PRIVATE_VALUE: &str = "synthetic-private-field-value";
const PUBLIC_KEY: &str = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE";
const SECRETS: [&str; 5] = [USER, PASSWORD, UUID, PRIVATE_FIELD, PRIVATE_VALUE];
static LIFECYCLE: Mutex<()> = Mutex::new(());

fn serialized_lifecycle() -> MutexGuard<'static, ()> {
    LIFECYCLE.lock().unwrap_or_else(|error| error.into_inner())
}

fn assert_redacted(output: &str) {
    for secret in SECRETS {
        assert!(
            !output.contains(secret),
            "control response leaked a fixture secret"
        );
    }
}

fn command_bytes(input: &[u8]) -> Value {
    let mut output = vec![0xa5; OUTPUT_CAPACITY];
    // SAFETY: both initialized allocations are live, disjoint and at least the
    // lengths passed here; output satisfies the exported ABI capacity contract.
    // Every test holds LIFECYCLE while operating on the global ABI controller.
    let written = unsafe {
        swirl_core_command(
            input.as_ptr(),
            input.len(),
            output.as_mut_ptr(),
            output.len(),
        )
    };
    assert!(written > 0, "C ABI must return an actual JSON response");
    let written = usize::try_from(written).unwrap();
    assert!(written <= output.len());
    assert!(output[written..].iter().all(|byte| *byte == 0xa5));
    let text = std::str::from_utf8(&output[..written]).unwrap();
    assert_redacted(text);
    serde_json::from_str(text).unwrap()
}

fn command(value: Value) -> Value {
    command_bytes(&serde_json::to_vec(&value).unwrap())
}

fn rejected(value: Value, expected: &str) {
    assert_eq!(command(value), json!({"ok": false, "error": expected}));
}

struct RunningCore {
    handle: u64,
    active: bool,
}
impl RunningCore {
    fn start(config: &Value) -> (Self, Value) {
        let response = command(json!({"op": "start", "config": config}));
        assert_eq!(response["ok"], true);
        let core = Self {
            handle: response["handle"].as_u64().unwrap(),
            active: true,
        };
        assert!(core.handle > 0);
        assert_eq!(response["status"]["running"], true);
        (core, response["status"].clone())
    }
    fn snapshot(&self) -> Value {
        let response = command(json!({"op": "snapshot", "handle": self.handle}));
        assert_eq!(response["ok"], true);
        response["status"].clone()
    }
    fn stop(&mut self) {
        assert_eq!(
            command(json!({"op": "stop", "handle": self.handle})),
            json!({"ok": true})
        );
        self.active = false;
    }
}
impl Drop for RunningCore {
    fn drop(&mut self) {
        if self.active {
            // Also release the listener if an assertion panics. Do not panic
            // while unwinding, and keep the caller buffers alive for the call.
            let input = format!("{{\"op\":\"stop\",\"handle\":{}}}", self.handle);
            let mut output = vec![0; OUTPUT_CAPACITY];
            // SAFETY: same independent live-buffer contract as command_bytes.
            unsafe {
                swirl_core_command(
                    input.as_ptr(),
                    input.len(),
                    output.as_mut_ptr(),
                    output.len(),
                );
            }
        }
    }
}

struct Fixture {
    source: Vec<u8>,
    archive: Vec<u8>,
    native: Value,
}
fn fixture(protocol: &str, endpoint: SocketAddr) -> Fixture {
    let source = serde_json::to_vec(&json!({
        "outbounds": [{
            "tag": "abi-fixture",
            "protocol": protocol,
            "settings": {"servers": [{
                "address": endpoint.ip().to_string(), "port": endpoint.port(),
                "users": [{"user": USER, "pass": PASSWORD}]
            }]}
        }]
    }))
    .unwrap();
    let imported = import_document(&source, InputSource::Clipboard).unwrap();
    let archive = imported.save().unwrap();
    let restored = ConvertedDocument::restore(&archive).unwrap();
    assert_eq!(restored.raw_json(), source);
    assert_eq!(restored.nodes().len(), 1);
    assert_eq!(
        restored.nodes()[0].native_status(),
        NativeStatus::Executable
    );
    assert!(restored.nodes()[0].native_outbound().is_some());
    assert!(!restored.nodes()[0].network_verified());
    let config = restored
        .native_config(0, "127.0.0.1:0".parse().unwrap())
        .unwrap();
    let native = serde_json::to_value(config).unwrap();
    // Re-enter the same strict IR serde/validator boundary before passing it
    // through the independent command deserializer and Core::start/configure.
    assert!(Config::parse(&serde_json::to_vec(&native).unwrap()).is_ok());
    assert_eq!(native["nodes"][0]["outbound"]["auth"]["username"], USER);
    assert_eq!(native["nodes"][0]["outbound"]["auth"]["password"], PASSWORD);
    Fixture {
        source,
        archive,
        native,
    }
}
fn loopback_peer() -> TcpListener {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    listener
}
fn no_upstream_connection(listener: &TcpListener) {
    assert_eq!(
        listener.accept().unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
}

#[test]
fn restored_native_config_crosses_actual_c_abi_start_configure_snapshot_stop() {
    let _serial = serialized_lifecycle();
    assert_eq!(swirl_core_abi_version(), 1);
    let peer = loopback_peer();
    let socks = fixture("socks", peer.local_addr().unwrap());
    let http = fixture("http", peer.local_addr().unwrap());
    assert_eq!(socks.native["nodes"][0]["outbound"]["type"], "socks5");
    assert_eq!(http.native["nodes"][0]["outbound"]["type"], "http_connect");

    let (mut core, initial) = RunningCore::start(&socks.native);
    let address: SocketAddr = initial["address"].as_str().unwrap().parse().unwrap();
    assert!(address.ip().is_loopback());
    assert_ne!(address.port(), 0);
    let generation = initial["generation"].as_u64().unwrap();
    assert_eq!(initial["accepted"], 0);
    assert_eq!(core.snapshot()["generation"], generation);

    // Preserve the configured :0 listener, not the runtime's assigned port.
    assert_eq!(
        command(json!({"op": "configure", "handle": core.handle, "config": http.native})),
        json!({"ok": true})
    );
    let updated = core.snapshot();
    assert_eq!(updated["running"], true);
    assert_eq!(updated["generation"], generation + 1);
    assert_eq!(updated["address"], initial["address"]);
    assert_eq!(updated["accepted"], 0);
    assert_eq!(updated["failed"], 0);
    no_upstream_connection(&peer);

    core.stop();
    rejected(
        json!({"op": "snapshot", "handle": core.handle}),
        "UnknownHandle",
    );
    rejected(
        json!({"op": "stop", "handle": core.handle}),
        "UnknownHandle",
    );
    let rebound = TcpListener::bind(address).expect("stop must release the listening socket");
    drop(rebound);
}

#[test]
fn modern_vmess_import_roundtrips_through_c_abi_without_claiming_network_verification() {
    let _serial = serialized_lifecycle();
    let peer = loopback_peer();
    let endpoint = peer.local_addr().unwrap();
    let input = serde_json::to_vec(&json!({"outbounds": [{
        "protocol": "vmess", "settings": {"vnext": [{
            "address": endpoint.ip().to_string(), "port": endpoint.port(),
            "users": [{"id": UUID, "alterId": 0, "security": "aes-128-gcm"}]
        }]}
    }]}))
    .unwrap();
    let imported = import_document(&input, InputSource::Clipboard).unwrap();
    let restored = ConvertedDocument::restore(&imported.save().unwrap()).unwrap();
    assert_eq!(
        restored.nodes()[0].native_status(),
        NativeStatus::Executable
    );
    assert!(!restored.nodes()[0].network_verified());
    let config = restored
        .native_config(0, "127.0.0.1:0".parse().unwrap())
        .unwrap();
    let native = serde_json::to_value(&config).unwrap();
    assert_eq!(native["nodes"][0]["outbound"]["type"], "vmess");
    assert_eq!(native["nodes"][0]["outbound"]["uuid"], UUID);
    let (mut core, status) = RunningCore::start(&native);
    assert_eq!(status["accepted"], 0);
    no_upstream_connection(&peer);
    core.stop();
}

#[test]
fn c_abi_refuses_xray_archives_unknown_fields_and_invalid_vmess_ir() {
    let _serial = serialized_lifecycle();
    let peer = loopback_peer();
    let http = fixture("http", peer.local_addr().unwrap());
    let source: Value = serde_json::from_slice(&http.source).unwrap();
    let archive: Value = serde_json::from_slice(&http.archive).unwrap();
    for bytes in [&http.source, &http.archive] {
        assert_eq!(
            command_bytes(bytes),
            json!({"ok": false, "error": "CommandInvalidOrUnsupported"})
        );
    }
    for external in [source, archive] {
        rejected(
            json!({"op": "start", "config": external}),
            "CommandInvalidOrUnsupported",
        );
    }

    let mut unknown_command = json!({"op": "start", "config": http.native});
    unknown_command[PRIVATE_FIELD] = json!(PRIVATE_VALUE);
    rejected(unknown_command, "CommandInvalidOrUnsupported");

    let mut unknown_config = http.native.clone();
    unknown_config[PRIVATE_FIELD] = json!(PRIVATE_VALUE);
    rejected(
        json!({"op": "start", "config": unknown_config}),
        "CommandInvalidOrUnsupported",
    );

    let mut unknown_outbound = http.native.clone();
    unknown_outbound["nodes"][0]["outbound"][PRIVATE_FIELD] = json!(PRIVATE_VALUE);
    rejected(
        json!({"op": "start", "config": unknown_outbound}),
        "CommandInvalidOrUnsupported",
    );

    let mut unknown_tls = http.native.clone();
    unknown_tls["nodes"][0]["outbound"]["tls"] = json!({
        "server_name": "tls.fixture.invalid", "alpn": ["http/1.1"],
        "allowInsecure": true, "password": PASSWORD
    });
    rejected(
        json!({"op": "start", "config": unknown_tls}),
        "CommandInvalidOrUnsupported",
    );

    let mut forged_vmess = http.native.clone();
    forged_vmess["nodes"][0]["outbound"] = json!({
        "type": "vmess", "host": "127.0.0.1", "port": peer.local_addr().unwrap().port(),
        "uuid": UUID, "alter_id": 0, "security": "auto", "unmapped_requirement": true
    });
    rejected(
        json!({"op": "start", "config": forged_vmess}),
        "CommandInvalidOrUnsupported",
    );
    no_upstream_connection(&peer);
}

#[test]
fn c_abi_revalidates_security_and_failed_configure_keeps_running_generation() {
    let _serial = serialized_lifecycle();
    let peer = loopback_peer();
    let http = fixture("http", peer.local_addr().unwrap());
    let (mut core, before) = RunningCore::start(&http.native);
    let mut conflict = http.native.clone();
    conflict["nodes"][0]["outbound"] = json!({
        "type": "vless", "host": "127.0.0.1", "port": peer.local_addr().unwrap().port(),
        "uuid": UUID,
        "tls": {"server_name": "tls.fixture.invalid", "alpn": ["http/1.1"]},
        "reality": {
            "server_name": "reality.fixture.invalid", "public_key": PUBLIC_KEY,
            "short_id": "aabb", "fingerprint": "rustls", "alpn": ["http/1.1"]
        }
    });
    // Both layers are individually representable; their simultaneous presence
    // must be rejected instead of selecting one and downgrading the other.
    assert_eq!(
        Config::parse(&serde_json::to_vec(&conflict).unwrap()).err(),
        Some("RealityTransportConflict")
    );
    rejected(
        json!({"op": "start", "config": conflict}),
        "RealityTransportConflict",
    );
    rejected(
        json!({"op": "configure", "handle": core.handle, "config": conflict}),
        "RealityTransportConflict",
    );

    let mut bad_auth = http.native.clone();
    bad_auth["nodes"][0]["outbound"]["auth"]["username"] = json!("invalid:username");
    rejected(
        json!({"op": "configure", "handle": core.handle, "config": bad_auth}),
        "NodeParameters",
    );
    let mut changed_listener = http.native.clone();
    changed_listener["listen"] = json!("127.0.0.2:0");
    rejected(
        json!({"op": "configure", "handle": core.handle, "config": changed_listener}),
        "ListenerChangeRequiresRestart",
    );
    let mut unknown = http.native.clone();
    unknown[PRIVATE_FIELD] = json!(PRIVATE_VALUE);
    rejected(
        json!({"op": "configure", "handle": core.handle, "config": unknown}),
        "CommandInvalidOrUnsupported",
    );
    let after = core.snapshot();
    for field in [
        "generation",
        "selected",
        "address",
        "running",
        "accepted",
        "failed",
    ] {
        assert_eq!(after[field], before[field], "rejected update changed state");
    }
    assert_eq!(after["running"], true);
    no_upstream_connection(&peer);
    core.stop();
}

#[test]
fn reloaded_legacy_vmess_and_conflicting_source_security_have_no_abi_export() {
    let _serial = serialized_lifecycle();
    let peer = loopback_peer();
    for protocol in ["vmess", "vless"] {
        let mut outbound = json!({
            "protocol": protocol,
            "settings": {"vnext": [{
                "address": "127.0.0.1", "port": peer.local_addr().unwrap().port(),
                "users": [{"id": UUID}]
            }]}
        });
        if protocol == "vless" {
            outbound["settings"]["vnext"][0]["users"][0]["encryption"] = json!("none");
            outbound["streamSettings"] = json!({
                "network": "tcp", "security": "tls",
                "tlsSettings": {"serverName": "tls.fixture.invalid"},
                "realitySettings": {
                    "serverName": "reality.fixture.invalid", "publicKey": PUBLIC_KEY,
                    "shortId": "aabb", "fingerprint": "chrome"
                }
            });
        } else {
            outbound["settings"]["vnext"][0]["users"][0]["alterId"] = json!(16);
        }
        let source = serde_json::to_vec(&json!({"outbounds": [outbound]})).unwrap();
        let imported = import_document(&source, InputSource::File).unwrap();
        let archive = imported.save().unwrap();
        let restored = ConvertedDocument::restore(&archive).unwrap();
        assert_eq!(restored.raw_json(), source);
        let node = &restored.nodes()[0];
        assert_eq!(
            node.protocol(),
            if protocol == "vmess" {
                Protocol::Vmess
            } else {
                Protocol::Vless
            }
        );
        assert_eq!(node.native_status(), NativeStatus::Blocked);
        assert!(node.native_outbound().is_none());
        assert!(!node.network_verified());
        let diagnostic = restored
            .native_config(0, "127.0.0.1:0".parse().unwrap())
            .err()
            .expect("blocked source must have no native config to send to Qt");
        assert_redacted(&format!("{diagnostic:?}"));
        rejected(
            json!({"op": "start", "config": serde_json::from_slice::<Value>(&archive).unwrap()}),
            "CommandInvalidOrUnsupported",
        );
    }
    no_upstream_connection(&peer);
}
