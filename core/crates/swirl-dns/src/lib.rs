//! Bounded system resolver and cache. DoH/DoT/Fake-IP are not claimed here.
use std::{
    collections::HashMap,
    net::{IpAddr, SocketAddr},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tokio::{net::lookup_host, sync::Semaphore, time::timeout};

type Cache = HashMap<(String, u16), (Instant, Vec<SocketAddr>)>;
pub struct Resolver {
    cache: Mutex<Cache>,
    permits: Arc<Semaphore>,
    hosts: HashMap<String, IpAddr>,
}
impl Default for Resolver {
    fn default() -> Self {
        Self {
            cache: Mutex::new(HashMap::new()),
            permits: Arc::new(Semaphore::new(8)),
            hosts: HashMap::new(),
        }
    }
}
impl Resolver {
    /// Each immutable configuration owns a separate cache and host table, while
    /// every generation shares the same cap on still-running OS lookups.
    pub fn with_hosts(&self, hosts: &[swirl_subscription::HostMapping]) -> Self {
        Self {
            cache: Mutex::new(HashMap::new()),
            permits: self.permits.clone(),
            hosts: hosts
                .iter()
                .map(|h| (h.name.to_ascii_lowercase(), h.address))
                .collect(),
        }
    }
    pub fn mapped_host(&self, host: &str) -> Option<IpAddr> {
        self.hosts.get(&host.to_ascii_lowercase()).copied()
    }
    pub async fn resolve(&self, host: &str, port: u16) -> Result<Vec<SocketAddr>, &'static str> {
        if port == 0 || !swirl_subscription::valid_host(host) {
            return Err("DnsInvalidTarget");
        }
        if let Ok(ip) = host.parse() {
            return Ok(vec![SocketAddr::new(ip, port)]);
        }
        if let Some(ip) = self.mapped_host(host) {
            return Ok(vec![SocketAddr::new(ip, port)]);
        }
        let key = (host.to_ascii_lowercase(), port);
        {
            let mut cache = self.cache.lock().map_err(|_| "DnsState")?;
            cache.retain(|_, (at, _)| at.elapsed() < Duration::from_secs(30));
            if let Some((_, addresses)) = cache.get(&key) {
                return Ok(addresses.clone());
            }
        }
        let permit = timeout(Duration::from_secs(3), self.permits.clone().acquire_owned())
            .await
            .map_err(|_| "DnsBusy")?
            .map_err(|_| "DnsStopped")?;
        // Keep the permit until the underlying OS lookup actually finishes even
        // if the caller times out/cancels. This bounds detached blocking lookups.
        let host = host.to_owned();
        let lookup = tokio::spawn(async move {
            let _permit = permit;
            lookup_host((host, port))
                .await
                .map(|a| a.take(16).collect::<Vec<_>>())
        });
        let addresses = timeout(Duration::from_secs(3), lookup)
            .await
            .map_err(|_| "DnsTimeout")?
            .map_err(|_| "DnsTask")?
            .map_err(|_| "DnsLookupFailed")?;
        if addresses.is_empty() {
            return Err("DnsEmpty");
        }
        let mut cache = self.cache.lock().map_err(|_| "DnsState")?;
        if cache.len() >= 256 {
            cache.clear();
        }
        cache.insert(key, (Instant::now(), addresses.clone()));
        Ok(addresses)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn ipv4_ipv6_and_system_localhost() {
        let r = Resolver::default();
        assert_eq!(r.resolve("127.0.0.1", 80).await.unwrap()[0].port(), 80);
        assert!(r.resolve("::1", 80).await.unwrap()[0].is_ipv6());
        assert!(!r.resolve("localhost", 80).await.unwrap().is_empty());
        assert!(r.resolve("bad\nhost", 80).await.is_err());
    }
    #[tokio::test]
    async fn host_maps_are_case_insensitive_and_generations_share_only_budget() {
        use swirl_subscription::HostMapping;
        let root = Resolver::default();
        let old = root.with_hosts(&[HostMapping {
            name: "Fixture.Invalid".into(),
            address: "127.0.0.1".parse().unwrap(),
        }]);
        let next = old.with_hosts(&[HostMapping {
            name: "fixture.invalid".into(),
            address: "::1".parse().unwrap(),
        }]);
        assert!(Arc::ptr_eq(&old.permits, &next.permits));
        assert_eq!(
            old.resolve("FIXTURE.INVALID", 80).await.unwrap(),
            vec!["127.0.0.1:80".parse().unwrap()]
        );
        assert_eq!(
            next.resolve("fixture.invalid", 443).await.unwrap(),
            vec!["[::1]:443".parse().unwrap()]
        );
        assert!(next.resolve("fixture.invalid", 0).await.is_err());
        old.cache.lock().unwrap().insert(
            ("cached.invalid".into(), 80),
            (Instant::now(), vec!["127.0.0.9:80".parse().unwrap()]),
        );
        assert!(next.cache.lock().unwrap().is_empty());
        assert!(root.mapped_host("fixture.invalid").is_none());
        assert_eq!(
            old.resolve("fixture.invalid", 80).await.unwrap()[0].ip(),
            "127.0.0.1".parse::<IpAddr>().unwrap()
        );
    }
}
