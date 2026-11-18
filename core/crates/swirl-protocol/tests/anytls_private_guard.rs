//! Each subprocess gets a fresh immutable private acceptance guard. No provider
//! endpoint, TUN lease or host network setting is used by this regression.
use std::{process::Command, sync::Arc, time::Duration};
use swirl_dns::Resolver;
use swirl_protocol::{Target, anytls};
use swirl_subscription::{AnyTls, Tls};
use swirl_transport::egress::budget;

#[tokio::test]
async fn anytls_never_reuses_a_socket_across_private_guard_installation() {
    let Ok(mode) = std::env::var("SWIRL_ANYTLS_GUARD_CASE") else {
        for mode in ["guarded", "late"] {
            let status = Command::new(std::env::current_exe().unwrap())
                .args([
                    "anytls_never_reuses_a_socket_across_private_guard_installation",
                    "--exact",
                ])
                .env("SWIRL_ANYTLS_GUARD_CASE", mode)
                .status()
                .unwrap();
            assert!(status.success(), "isolated guard case failed");
        }
        return;
    };
    let config = AnyTls {
        host: "127.0.0.1".into(),
        port: 9,
        password: "public-test-password".into(),
        tls: Tls {
            server_name: "fixture.test".into(),
            alpn: vec![],
            ca_der_base64: None,
        },
        udp: true,
        idle_session_timeout_seconds: 5,
        session_owner: Arc::default(),
    };
    let target = Target {
        host: "fixture.test".into(),
        port: 443,
    };
    if mode == "guarded" {
        let guard = budget::install(1024, 1).unwrap();
        let result = anytls::connect(
            &config,
            &target,
            &Resolver::default(),
            Duration::from_secs(1),
        )
        .await;
        assert_eq!(result.err(), Some("PrivateAcceptanceAnyTlsUnsupported"));
        let snapshot = guard.snapshot().unwrap();
        assert_eq!(
            (
                snapshot.connection_attempts,
                snapshot.upload,
                snapshot.download
            ),
            (0, 0, 0)
        );
        guard.cancel();
    } else {
        assert!(
            anytls::connect(&config, &target, &Resolver::default(), Duration::ZERO)
                .await
                .is_err()
        );
        assert_eq!(
            budget::install(1024, 1).err().unwrap().to_string(),
            "PrivateQuotaLateInstall"
        );
    }
}
