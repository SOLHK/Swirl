//! Configuration rejection is a separate gate from protocol interoperability.
//! These real local DNS sockets detect any lookup performed before rejection.
use std::time::Duration;
use swirl_dns::Resolver;
use swirl_protocol::{Target, hysteria2, tuic};
use swirl_subscription::{Dns, Outbound};
use tokio::{net::UdpSocket, time::timeout};

#[tokio::test]
async fn invalid_quic_trust_anchor_is_rejected_before_tcp_or_udp_dns() {
    let observer = UdpSocket::bind("127.0.0.1:0").await.unwrap();
    let dns = Dns {
        servers: vec![observer.local_addr().unwrap()],
        use_system_hosts: false,
        ..Default::default()
    };
    let resolver = Resolver::default().with_config(&dns).unwrap();
    let target = Target {
        host: "127.0.0.1".into(),
        port: 80,
    };
    for protocol in ["hysteria2", "tuic"] {
        // Valid base64 containing invalid DER used to pass subscription
        // validation and reach the DNS resolver before the TLS builder failed.
        let mut value = serde_json::json!({
            "type": protocol, "host": "invalid-ca-fixture.invalid", "port": 443,
            "password": "synthetic-preflight-only",
            "tls": { "server_name": "localhost", "alpn": ["h3"],
                     "ca_der_base64": "bm90LWEtY2VydGlmaWNhdGU=" }
        });
        if protocol == "tuic" {
            value["uuid"] = "00112233-4455-6677-8899-aabbccddeeff".into();
        }
        let outbound: Outbound = serde_json::from_value(value).unwrap();
        let limit = Duration::from_millis(100);
        assert!(matches!(
            swirl_protocol::connect(&outbound, &target, &resolver, limit).await,
            Err("TlsTrustAnchor")
        ));
        match &outbound {
            Outbound::Hysteria2(config) => {
                assert_eq!(hysteria2::validate(config), Err("TlsTrustAnchor"));
                assert!(matches!(
                    hysteria2::UdpAssociation::connect(config, &resolver, limit).await,
                    Err("TlsTrustAnchor")
                ));
            }
            Outbound::Tuic(config) => {
                assert_eq!(tuic::validate(config), Err("TlsTrustAnchor"));
                assert!(matches!(
                    tuic::UdpAssociation::connect(config, &resolver, limit).await,
                    Err("TlsTrustAnchor")
                ));
            }
            _ => unreachable!(),
        }
    }
    let mut bytes = [0; 4096];
    assert!(
        timeout(Duration::from_millis(50), observer.recv_from(&mut bytes))
            .await
            .is_err(),
        "invalid QUIC certificate material caused a real DNS query"
    );
}
