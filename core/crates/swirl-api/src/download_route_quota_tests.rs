//! Private quotas are irreversible process state. Run each installed-guard
//! scenario in a fresh copy of this test executable, never in the shared suite.
use super::*;
use serde_json::Value;
use std::process::Command as ProcessCommand;
use swirl_transport::egress::budget;

const CHILD_MODE: &str = "SWIRL_PRIVATE_QUOTA_FIXTURE_MODE";

fn subprocess(mode: &str) {
    let mut child = ProcessCommand::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "download_route::quota_tests::private_quota_child",
            "--ignored",
            "--nocapture",
        ])
        .env(CHILD_MODE, mode)
        .spawn()
        .unwrap();
    let deadline = std::time::Instant::now() + Duration::from_secs(15);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            assert!(status.success(), "private quota child failed: {mode}");
            return;
        }
        if std::time::Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            panic!("private quota child did not exit: {mode}");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}

#[test]
fn private_quota_process_covers_dns_and_special_routes() {
    subprocess("guarded");
}

#[test]
fn private_quota_process_rejects_install_after_raw_route_admission() {
    subprocess("late");
}

#[test]
fn private_quota_process_meters_tls_before_handshake() {
    subprocess("tls");
}

#[test]
fn private_quota_process_blocks_native_system_network() {
    subprocess("system");
}

#[test]
fn private_quota_process_rejects_install_after_native_system_admission() {
    for operation in ["native_tun_start", "gateway_prepare", "gateway_activate"] {
        subprocess(operation);
    }
}

#[test]
#[ignore = "fresh-process fixture; invoked by the parent tests"]
fn private_quota_child() {
    match std::env::var(CHILD_MODE).unwrap().as_str() {
        "guarded" => guarded_routes(),
        "late" => late_install(),
        "tls" => tls_first_flight(),
        "system" => guarded_system_network(),
        operation @ ("native_tun_start" | "gateway_prepare" | "gateway_activate") => {
            late_system_install(operation)
        }
        _ => panic!("invalid private quota fixture mode"),
    }
}

fn system_request(operation: &str) -> Value {
    let mut request = json!({"op":operation,
        "request_id":"60000000-0000-4000-8000-000000000001"});
    request[if operation.starts_with("native_tun_") {
        "native_tun_schema"
    } else {
        "native_gateway_schema"
    }] = json!(1);
    if !operation.ends_with("_validate") && !operation.ends_with("_recover") {
        request["handle"] = json!("1");
        request["engine_epoch"] = json!("1");
    }
    let tun = json!({"driver_path":"C:\\Swirl\\quota-fixture-driver.dll",
        "adapter_guid":"70000000-0000-4000-8000-000000000001",
        "adapter_name":"Swirl Quota Fixture"});
    match operation {
        "native_tun_validate" | "native_tun_start" => request["config"] = tun,
        "gateway_validate" | "gateway_prepare" => {
            request["config"] = json!({"tun":tun,"lan":{
                "lan":{"index":11,"guid":"70000000-0000-4000-8000-000000000002"},
                "subnet":"192.168.77.0/24","gateway":"192.168.77.1",
                "allowed_sources":["192.168.77.0/24"],"dedicated_lan_confirmed":true,
                "dhcp":true}});
        }
        "gateway_activate" => {
            request["preparation_id"] = json!("0".repeat(32));
            request["dhcp"] = json!({"owner_pid":1,"owner_creation":"1",
                "target_helper_pid":2,"protocol_info_base64":"Zml4dHVyZQ=="});
        }
        _ => {}
    }
    request
}

fn system_call(controller: &mut crate::Controller, operation: &str) -> Value {
    controller.dispatch(&serde_json::to_vec(&system_request(operation)).unwrap())
}

fn assert_native_state_empty(controller: &crate::Controller) {
    assert_eq!(controller.next, 0);
    assert!(controller.cores.is_empty());
    assert!(controller.cores_v2.is_empty());
    #[cfg(windows)]
    assert!(controller.native_sessions.is_empty());
}

fn available_system_control(controller: &mut crate::Controller) {
    for (prefix, unknown_handle, helper_required) in [
        ("native_tun", "UnknownHandle", "TunHelperRequired"),
        ("gateway", "UnknownV2Handle", "GatewayHelperRequired"),
    ] {
        let validation = system_call(controller, &format!("{prefix}_validate"));
        assert_eq!(validation["ok"], true, "{validation}");
        assert_eq!(validation["validated"], true);
        assert_eq!(
            system_call(controller, &format!("{prefix}_status"))["error"],
            unknown_handle
        );
        assert_eq!(
            system_call(controller, &format!("{prefix}_stop"))["error"],
            if controller.native_helper {
                unknown_handle
            } else {
                helper_required
            }
        );
        // Exercise the recovery parser/authority gate without invoking actual
        // Windows journal recovery on the developer or CI machine.
        if !controller.native_helper {
            assert_eq!(
                system_call(controller, &format!("{prefix}_recover"))["error"],
                helper_required
            );
        }
    }
    controller.stop_native_tunnels().unwrap();
    crate::native_tun_control::stop_for_core(controller, 1).unwrap();
    assert_native_state_empty(controller);
}

fn guarded_system_network() {
    let mut ordinary = crate::Controller::default();
    // Pure validation/query/cleanup must neither start unmetered admission nor
    // prevent installing the quota before a later operation.
    available_system_control(&mut ordinary);
    let guard = budget::install(4096, 2).unwrap();
    let mut helper = crate::Controller::for_native_tun_helper();
    for cancelled in [false, true] {
        if cancelled {
            guard.cancel();
        }
        for controller in [&mut ordinary, &mut helper] {
            for operation in ["native_tun_start", "gateway_prepare", "gateway_activate"] {
                let response = system_call(controller, operation);
                assert_eq!(response["ok"], false, "{response}");
                assert_eq!(
                    response["error"], "PrivateQuotaUnmeteredDenied",
                    "{response}"
                );
                assert_native_state_empty(controller);
            }
            available_system_control(controller);
        }
        // These public Windows-only library entry points must refuse before
        // pipe authentication, helper creation, token queries or handle adoption.
        #[cfg(windows)]
        {
            let error = crate::native_tun_broker::run(vec![
                "--pipe".into(),
                r"\\.\pipe\SwirlQuotaFixture".into(),
                "--gui-pid".into(),
                "1".into(),
            ])
            .unwrap_err();
            assert_eq!(error.to_string(), "PrivateQuotaUnmeteredDenied");
            let error = crate::native_packet_worker::run().unwrap_err();
            assert_eq!(error.to_string(), "PrivateQuotaUnmeteredDenied");
        }
    }
    let receipt = guard.snapshot().unwrap();
    assert_eq!(receipt.upload + receipt.download, 0);
    assert_eq!(receipt.connection_attempts, 0);
    assert!(receipt.stopped && !receipt.timed_out);
    assert_eq!(receipt.shutdown_failures, 0);
}

fn late_system_install(operation: &str) {
    let mut controller = crate::Controller::default();
    let response = system_call(&mut controller, operation);
    assert_eq!(
        response["error"],
        if operation == "native_tun_start" {
            "TunHelperRequired"
        } else {
            "GatewayHelperRequired"
        }
    );
    assert_native_state_empty(&controller);
    // Even an attempt rejected before OS execution is conservatively latched;
    // later installation cannot claim control of a prior native operation.
    assert_eq!(
        budget::install(4096, 2).err().unwrap().to_string(),
        "PrivateQuotaLateInstall"
    );
}

fn guarded_routes() {
    let guard = budget::install(4096, 2).unwrap();
    assert!(budget::install(4096, 2).is_err());
    // This exercises the same entry that a private subscription fetch uses.
    // It must fail before creating the route or resolving its destination.
    let error = execute(Command::StartOnce {
        host: "198.51.100.1".into(),
        port: 443,
    })
    .unwrap_err();
    assert_eq!(error.to_string(), "PrivateQuotaUnmeteredDenied");

    let runtime = Builder::new_current_thread().enable_all().build().unwrap();
    runtime.block_on(async {
        let tcp_peer = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let udp_peer = tokio::net::UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let mut endpoint = Endpoint {
            address: tcp_peer.local_addr().unwrap(),
            source: "127.0.0.1".parse().unwrap(),
            interface: 0,
        };
        assert_eq!(
            connect(&endpoint).await.unwrap_err().to_string(),
            "PrivateQuotaUnmeteredDenied"
        );
        endpoint.address = udp_peer.local_addr().unwrap();
        assert_eq!(
            query_dns("quota.fixture.invalid", swirl_dns::DNS_A, &endpoint)
                .await
                .unwrap_err()
                .to_string(),
            "PrivateQuotaUnmeteredDenied"
        );
        assert_eq!(
            swirl_dns::Resolver::default()
                .resolve("quota.fixture.invalid", 443)
                .await,
            Err("DnsPrivateMeteredResolverRequired")
        );
        // Numeric/explicitly mapped endpoints remain usable without starting
        // an OS DNS task. TLS still receives the original configured SNI.
        let pinned =
            swirl_dns::Resolver::default().with_hosts(&[swirl_subscription::HostMapping {
                name: "quota.fixture.invalid".into(),
                address: "127.0.0.1".parse().unwrap(),
            }]);
        assert_eq!(
            pinned.resolve("quota.fixture.invalid", 443).await.unwrap(),
            vec!["127.0.0.1:443".parse().unwrap()]
        );
        let mut data = [0; 256];
        assert!(
            timeout(Duration::from_millis(50), tcp_peer.accept())
                .await
                .is_err()
        );
        assert!(
            timeout(Duration::from_millis(50), udp_peer.recv_from(&mut data))
                .await
                .is_err()
        );
        assert!(swirl_transport::inbound::bind_udp_std("127.0.0.1:0".parse().unwrap()).is_err());
    });
    guard.cancel();
    let receipt = guard.snapshot().unwrap();
    assert_eq!(receipt.upload + receipt.download, 0);
    assert_eq!(receipt.connection_attempts, 0);
    assert!(receipt.stopped && !receipt.timed_out);
}

fn late_install() {
    let runtime = Builder::new_current_thread().enable_all().build().unwrap();
    runtime.block_on(async {
        let peer = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = Endpoint {
            address: peer.local_addr().unwrap(),
            source: "127.0.0.1".parse().unwrap(),
            interface: 0,
        };
        // The normal route is permitted before installation, but its admission
        // must irrevocably prevent a later, incomplete process-wide guard.
        let attempt = connect(&endpoint).await;
        #[cfg(not(windows))]
        assert!(attempt.is_ok());
        // Windows may reject the synthetic interface index before connect;
        // even that failed attempt must mark the unmetered path as started.
        drop(attempt);
        let error = budget::install(4096, 2).err().unwrap();
        assert_eq!(error.to_string(), "PrivateQuotaLateInstall");
    });
}

fn tls_first_flight() {
    let guard = budget::install(31, 1).unwrap();
    let runtime = Builder::new_current_thread().enable_all().build().unwrap();
    runtime.block_on(async {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let outbound = swirl_subscription::Outbound::HttpConnect {
            host: "127.0.0.1".into(),
            port: listener.local_addr().unwrap().port(),
            auth: None,
            tls: Some(swirl_subscription::Tls {
                server_name: "localhost".into(),
                alpn: vec![],
                ca_der_base64: None,
            }),
        };
        let peer = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut received = Vec::new();
            socket.read_to_end(&mut received).await.unwrap();
            received
        });
        let result = timeout(
            Duration::from_secs(3),
            swirl_protocol::connect(
                &outbound,
                &swirl_protocol::Target {
                    host: "quota.fixture.invalid".into(),
                    port: 443,
                },
                &swirl_dns::Resolver::default(),
                Duration::from_secs(2),
            ),
        )
        .await
        .unwrap();
        assert!(result.is_err());
        let received = timeout(Duration::from_secs(2), peer)
            .await
            .unwrap()
            .unwrap();
        assert_eq!(received.len(), 31);
        assert_eq!(received[0], 22, "expected a real TLS handshake record");
        assert_eq!(
            received[5], 1,
            "expected ClientHello, before authentication"
        );
    });
    let receipt = guard.snapshot().unwrap();
    assert_eq!(receipt.upload, 31);
    assert_eq!(receipt.download, 0);
    assert!(receipt.stopped);
    assert_eq!(receipt.shutdown_failures, 0);
}
