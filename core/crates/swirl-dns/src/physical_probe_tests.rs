use super::*;
use swirl_transport::egress::with_physical_probe;

#[tokio::test]
async fn a_physical_probe_never_uses_cached_or_spawned_os_dns() {
    let resolver = Resolver::default();
    // Exercise the real OS lookup and its cache before entering the physical
    // scope. TUN-off resolution must keep working with the default settings.
    let ordinary = resolver.resolve("localhost", 443).await.unwrap();
    assert!(!ordinary.is_empty());
    assert!(ordinary.iter().all(|entry| entry.ip().is_loopback()));
    let scoped = with_physical_probe(async { resolver.resolve("localhost", 443).await })
        .await
        .unwrap();
    assert_eq!(scoped, Err("DnsPhysicalResolverRequired"));
    assert_eq!(resolver.resolve("localhost", 443).await.unwrap(), ordinary);

    let mapped = resolver.with_hosts(&[swirl_subscription::HostMapping {
        name: "probe.fixture.invalid".into(),
        address: "127.0.0.1".parse().unwrap(),
    }]);
    let resolved = with_physical_probe(mapped.resolve("probe.fixture.invalid", 443))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        resolved,
        vec!["127.0.0.1:443".parse::<SocketAddr>().unwrap()]
    );
}
