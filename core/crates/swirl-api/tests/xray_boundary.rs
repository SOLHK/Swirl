//! Qt's caller-owned UTF-8 buffers -> actual C ABI -> validated Rust Core.
//! Only synthetic configuration and loopback listeners are used. Lifecycle
//! acceptance here is not a proxy handshake, TLS, REALITY, or network test.
use serde_json::{Value, json};
use std::{
    net::{SocketAddr, TcpListener, UdpSocket},
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
const SS2022_PSK: &str = "AgICAgICAgICAgICAgICAg==";
const SECRETS: [&str; 6] = [
    USER,
    PASSWORD,
    UUID,
    PRIVATE_FIELD,
    PRIVATE_VALUE,
    SS2022_PSK,
];
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
fn persisted_http_transports_cross_actual_c_abi_and_invalid_reconfigure_is_atomic() {
    let _serial = serialized_lifecycle();
    let peer = loopback_peer();
    let endpoint = peer.local_addr().unwrap();
    for (network, key, options, expected_type) in [
        (
            "grpc",
            "grpcSettings",
            json!({"serviceName":"boundary"}),
            "grpc",
        ),
        (
            "h2",
            "httpSettings",
            json!({"host":["peer.invalid"],"path":"/h2"}),
            "http2",
        ),
        (
            "httpupgrade",
            "httpupgradeSettings",
            json!({"path":"/upgrade"}),
            "httpupgrade",
        ),
        (
            "xhttp",
            "xhttpSettings",
            json!({"path":"/split","mode":"stream-one"}),
            "xhttp",
        ),
    ] {
        let mut stream =
            json!({"network":network,"security":"tls","tlsSettings":{"serverName":"peer.invalid"}});
        stream[key] = options;
        let input = serde_json::to_vec(&json!({"outbounds":[{"protocol":"vless",
            "settings":{"vnext":[{"address":endpoint.ip().to_string(),"port":endpoint.port(),
                "users":[{"id":UUID,"encryption":"none"}]}]},"streamSettings":stream}]}))
        .unwrap();
        let imported = import_document(&input, InputSource::Clipboard).unwrap();
        let restored = ConvertedDocument::restore(&imported.save().unwrap()).unwrap();
        assert!(!restored.nodes()[0].network_verified());
        let mut native = serde_json::to_value(
            restored
                .native_config(0, "127.0.0.1:0".parse().unwrap())
                .unwrap(),
        )
        .unwrap();
        assert_eq!(
            native["nodes"][0]["outbound"]["transport"]["type"],
            expected_type
        );
        let (mut core, status) = RunningCore::start(&native);
        native["nodes"][0]["outbound"]["transport"]["config"]["headers"] =
            json!([["Content-Type", "forbidden"]]);
        let failed = command(json!({"op":"configure","handle":core.handle,"config":native}));
        assert_eq!(failed["ok"], false);
        assert_eq!(core.snapshot()["generation"], status["generation"]);
        assert_eq!(core.snapshot()["accepted"], 0);
        no_upstream_connection(&peer);
        core.stop();
    }
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

fn inspected_outbound(source: &str, expected: &str) -> Value {
    let inspection = swirl_subscription::inspect::inspect(source.as_bytes());
    assert!(inspection.report.parsed);
    assert_eq!(inspection.original, source.as_bytes());
    assert_eq!(inspection.report.nodes.len(), 1);
    assert!(inspection.report.nodes[0].native_tcp_candidate);
    assert!(!inspection.report.nodes[0].real_network_verified);
    assert_redacted(&serde_json::to_string(&inspection.report).unwrap());
    let outbound = serde_json::to_value(inspection.tcp_candidates[0].as_ref().unwrap()).unwrap();
    assert_eq!(outbound["type"], expected);
    outbound
}

#[test]
fn quic_and_ss2022_source_imports_survive_abi_configuration_and_selection() {
    let _serial = serialized_lifecycle();
    let tcp = loopback_peer();
    let tcp_endpoint = tcp.local_addr().unwrap();
    // TCP and UDP have separate port allocations and exclusions. A port reserved
    // by TCP bind(:0) is not necessarily available to UDP on Windows. Keep each
    // transport's own ephemeral socket open for the complete ABI lifecycle.
    let udp = UdpSocket::bind("127.0.0.1:0").expect("reserve the QUIC fixture's UDP port");
    udp.set_nonblocking(true).unwrap();
    let udp_endpoint = udp.local_addr().unwrap();
    let tcp_port = tcp_endpoint.port();
    let udp_port = udp_endpoint.port();
    let groups = [
        (
            "hysteria2",
            udp_endpoint,
            vec![
                format!("hy2://{PASSWORD}@{udp_endpoint}/?sni=localhost"),
                format!("hysteria2://{PASSWORD}@{udp_endpoint}/?sni=localhost"),
                format!(
                    "proxies:\n  - name: boundary\n    type: hysteria2\n    server: 127.0.0.1\n    port: {udp_port}\n    password: {PASSWORD}\n    sni: localhost\n"
                ),
            ],
        ),
        (
            "tuic",
            udp_endpoint,
            vec![
                format!("tuic://{UUID}:{PASSWORD}@{udp_endpoint}/?sni=localhost&alpn=h3"),
                format!(
                    "proxies:\n  - name: boundary\n    type: tuic\n    server: 127.0.0.1\n    port: {udp_port}\n    uuid: {UUID}\n    password: {PASSWORD}\n    sni: localhost\n    alpn: [h3]\n"
                ),
            ],
        ),
        (
            "shadowsocks",
            tcp_endpoint,
            vec![
                format!(
                    "ss://2022-blake3-aes-128-gcm:{}@{tcp_endpoint}/",
                    SS2022_PSK.replace('=', "%3D")
                ),
                format!(
                    "proxies:\n  - name: boundary\n    type: ss\n    server: 127.0.0.1\n    port: {tcp_port}\n    cipher: 2022-blake3-aes-128-gcm\n    password: {SS2022_PSK}\n"
                ),
            ],
        ),
    ];
    let mut native = json!({"schema":1,"listen":"127.0.0.1:0","selected":"node0","nodes":[]});
    for (index, (protocol, endpoint, sources)) in groups.iter().enumerate() {
        let first = inspected_outbound(&sources[0], protocol);
        assert_eq!(first["host"], endpoint.ip().to_string(), "{protocol}");
        assert_eq!(first["port"], endpoint.port(), "{protocol}");
        for source in &sources[1..] {
            // Different subscription dialects must produce identical native IR.
            assert_eq!(inspected_outbound(source, protocol), first);
        }
        native["nodes"].as_array_mut().unwrap().push(json!({
            "id":format!("node{index}"),"outbound":first
        }));
    }
    // Exercise storage serialization before crossing caller-owned ABI buffers.
    let persisted = Config::parse(&serde_json::to_vec(&native).unwrap()).unwrap();
    let native = serde_json::to_value(persisted).unwrap();
    let (mut core, before) = RunningCore::start(&native);
    for index in [1, 2, 0] {
        let id = format!("node{index}");
        assert_eq!(
            command(json!({"op":"select","handle":core.handle,"id":id})),
            json!({"ok":true})
        );
        assert_eq!(core.snapshot()["selected"], id);
    }
    assert_eq!(
        command(json!({"op":"configure","handle":core.handle,"config":native})),
        json!({"ok":true})
    );
    let after = core.snapshot();
    assert_eq!(after["address"], before["address"]);
    assert_eq!(after["accepted"], 0);
    assert_eq!(after["failed"], 0);
    no_upstream_connection(&tcp);
    let mut packet = [0; 64];
    assert_eq!(
        udp.recv_from(&mut packet).unwrap_err().kind(),
        std::io::ErrorKind::WouldBlock
    );
    core.stop();
    let address: SocketAddr = before["address"].as_str().unwrap().parse().unwrap();
    let released = TcpListener::bind(address).expect("ABI stop must release its listener");
    drop(released);
}

#[test]
fn quic_trust_and_ss2022_key_rejections_are_atomic_at_exported_abi() {
    let _serial = serialized_lifecycle();
    let peer = loopback_peer();
    let native = fixture("http", peer.local_addr().unwrap()).native;
    let (mut core, before) = RunningCore::start(&native);
    for protocol in ["hysteria2", "tuic", "shadowsocks"] {
        let mut rejected_config = native.clone();
        let mut outbound = json!({"type":protocol,"host":"127.0.0.1",
            "port":peer.local_addr().unwrap().port(),"password":PASSWORD});
        let expected = if protocol == "shadowsocks" {
            outbound["cipher"] = "2022-blake3-aes-128-gcm".into();
            "Ss2022Key"
        } else {
            outbound["tls"] = json!({"server_name":"localhost","alpn":["h3"],
                "ca_der_base64":"bm90LWEtY2VydGlmaWNhdGU="});
            if protocol == "tuic" {
                outbound["uuid"] = UUID.into();
            }
            "TlsTrustAnchor"
        };
        rejected_config["nodes"][0]["outbound"] = outbound;
        rejected(json!({"op":"start","config":rejected_config}), expected);
        rejected(
            json!({"op":"configure","handle":core.handle,"config":rejected_config}),
            expected,
        );
        for field in [
            "generation",
            "selected",
            "address",
            "running",
            "accepted",
            "failed",
        ] {
            assert_eq!(
                core.snapshot()[field],
                before[field],
                "rejected ABI update changed state"
            );
        }
    }
    no_upstream_connection(&peer);
    core.stop();
}
