//! Private quotas are irreversible process state. Run each installed-guard
//! scenario in a fresh copy of this test executable, never in the shared suite.
use super::*;
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
#[ignore = "fresh-process fixture; invoked by the three parent tests"]
fn private_quota_child() {
    match std::env::var(CHILD_MODE).unwrap().as_str() {
        "guarded" => guarded_routes(),
        "late" => late_install(),
        "tls" => tls_first_flight(),
        _ => panic!("invalid private quota fixture mode"),
    }
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
