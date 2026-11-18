//! The process-local suspended lease must also cover the new Snell UDP carrier.
//! This test does not install a TUN, mutate routes/DNS, or contact an endpoint.
#[cfg(windows)]
#[tokio::test]
async fn snell_tcp_and_udp_fail_before_dial_when_physical_egress_is_suspended() {
    use std::time::Duration;
    use swirl_subscription::{Outbound, Snell};
    let lease = swirl_transport::egress::EgressLease::acquire_suspended().unwrap();
    let resolver = swirl_dns::Resolver::default();
    for host in ["192.0.2.1", "2001:db8::1"] {
        let config = Snell {
            host: host.into(),
            port: 9,
            psk: "synthetic".into(),
            version: 4,
            udp: true,
        };
        let target = swirl_protocol::Target {
            host: "127.0.0.1".into(),
            port: 80,
        };
        let tcp = swirl_protocol::connect(
            &Outbound::Snell(config.clone()),
            &target,
            &resolver,
            Duration::from_secs(1),
        )
        .await;
        assert!(matches!(tcp, Err("UpstreamNetworkUnreachable")));
        let udp = swirl_protocol::snell::UdpAssociation::connect(
            &config,
            &resolver,
            Duration::from_secs(1),
        )
        .await;
        assert!(matches!(udp, Err("UpstreamNetworkUnreachable")));
    }
    lease.release_after_routes_restored().unwrap();
}
