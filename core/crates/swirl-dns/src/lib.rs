//! Bounded system/custom/DoT/HTTP-1.1 DoH resolver. Fake-IP is not implemented.
mod dot;
mod wire;
use std::{
    collections::HashMap,
    net::{IpAddr, SocketAddr},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use swirl_subscription::DnsTlsServer;
use tokio::{net::lookup_host, sync::Semaphore, time::timeout};

type Cache = HashMap<String, (Instant, wire::Outcome)>;
pub struct Resolver {
    cache: Mutex<Cache>,
    permits: Arc<Semaphore>,
    hosts: HashMap<String, IpAddr>,
    servers: Vec<SocketAddr>,
    tls_servers: Vec<DnsTlsServer>,
    system_hosts: HashMap<String, IpAddr>,
}
impl Default for Resolver {
    fn default() -> Self {
        Self {
            cache: Mutex::new(HashMap::new()),
            permits: Arc::new(Semaphore::new(8)),
            hosts: HashMap::new(),
            servers: Vec::new(),
            tls_servers: Vec::new(),
            system_hosts: HashMap::new(),
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
            servers: Vec::new(),
            tls_servers: Vec::new(),
            system_hosts: HashMap::new(),
        }
    }
    pub fn with_config(&self, dns: &swirl_subscription::Dns) -> Result<Self, &'static str> {
        dns.validate_tls()?;
        let mut result = self.with_hosts(&dns.hosts);
        result.servers = dns.servers.clone();
        result.tls_servers = dns.tls_servers.clone();
        if (!dns.servers.is_empty() || !dns.tls_servers.is_empty()) && dns.use_system_hosts {
            result.system_hosts = system_hosts()?;
        }
        Ok(result)
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
        if let Some(ip) = self.system_hosts.get(&host.to_ascii_lowercase()) {
            return Ok(vec![SocketAddr::new(*ip, port)]);
        }
        let key = host.to_ascii_lowercase();
        {
            let mut cache = self.cache.lock().map_err(|_| "DnsState")?;
            cache.retain(|_, (expires, _)| *expires > Instant::now());
            if let Some((_, outcome)) = cache.get(&key) {
                return outcome.for_port(port);
            }
        }
        let permit = timeout(Duration::from_secs(3), self.permits.clone().acquire_owned())
            .await
            .map_err(|_| "DnsBusy")?
            .map_err(|_| "DnsStopped")?;
        if !self.servers.is_empty() || !self.tls_servers.is_empty() {
            let _permit = permit;
            let started = Instant::now();
            let resolution = async {
                if self.tls_servers.is_empty() {
                    wire::resolve(&self.servers, host).await
                } else {
                    dot::resolve(&self.tls_servers, host).await
                }
            };
            let answer = timeout(Duration::from_secs(3), resolution)
                .await
                .map_err(|_| "DnsTimeout")??;
            let expires = started + Duration::from_secs(u64::from(answer.ttl));
            if expires > Instant::now() {
                let mut cache = self.cache.lock().map_err(|_| "DnsState")?;
                if cache.len() >= 256 {
                    cache.clear();
                }
                cache.insert(key, (expires, answer.outcome.clone()));
            }
            return answer.outcome.for_port(port);
        }
        // Keep the permit until the underlying OS lookup actually finishes even
        // if the caller times out/cancels. This bounds detached blocking lookups.
        let host = host.to_owned();
        let lookup = tokio::spawn(async move {
            let _permit = permit;
            lookup_host((host, port))
                .await
                .map(|a| a.take(16).map(|address| address.ip()).collect::<Vec<_>>())
        });
        let addresses = timeout(Duration::from_secs(3), lookup)
            .await
            .map_err(|_| "DnsTimeout")?
            .map_err(|_| "DnsTask")?
            .map_err(|_| "DnsLookupFailed")?;
        if addresses.is_empty() {
            return Err("DnsEmpty");
        }
        let outcome = wire::Outcome::Addresses(addresses);
        let mut cache = self.cache.lock().map_err(|_| "DnsState")?;
        if cache.len() >= 256 {
            cache.clear();
        }
        cache.insert(
            key,
            (Instant::now() + Duration::from_secs(30), outcome.clone()),
        );
        outcome.for_port(port)
    }
}

fn system_hosts() -> Result<HashMap<String, IpAddr>, &'static str> {
    use std::io::Read;
    #[cfg(windows)]
    let path = std::path::PathBuf::from(
        std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into()),
    )
    .join("System32/drivers/etc/hosts");
    #[cfg(not(windows))]
    let path = std::path::PathBuf::from("/etc/hosts");
    let file = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(HashMap::new()),
        Err(_) => return Err("DnsSystemHostsRead"),
    };
    let mut data = Vec::new();
    file.take(1024 * 1024 + 1)
        .read_to_end(&mut data)
        .map_err(|_| "DnsSystemHostsRead")?;
    if data.len() > 1024 * 1024 {
        return Err("DnsSystemHostsLimit");
    }
    parse_hosts(&data)
}
fn parse_hosts(data: &[u8]) -> Result<HashMap<String, IpAddr>, &'static str> {
    let mut hosts = HashMap::new();
    for line in data
        .strip_prefix(&[0xef, 0xbb, 0xbf])
        .unwrap_or(data)
        .split(|b| *b == b'\n')
    {
        // Ignore comment encoding (Windows hosts often contains ANSI comments).
        let entry = line.split(|b| *b == b'#').next().unwrap_or_default();
        let mut fields = std::str::from_utf8(entry)
            .map_err(|_| "DnsSystemHostsEncoding")?
            .split_whitespace();
        let Some(ip) = fields.next().and_then(|s| s.parse::<IpAddr>().ok()) else {
            continue;
        };
        for name in fields {
            if swirl_subscription::valid_host(name) && name.parse::<IpAddr>().is_err() {
                hosts.entry(name.to_ascii_lowercase()).or_insert(ip);
                if hosts.len() > 4096 {
                    return Err("DnsSystemHostsLimit");
                }
            }
        }
    }
    Ok(hosts)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn hosts_file_aliases_comments_and_duplicate_priority() {
        let map=parse_hosts(b"\xef\xbb\xbf127.0.0.1 LocalHost alias.test # legacy comment \xff\r\n::1 ipv6.test\n127.0.0.2 localhost\nnot-an-ip ignored.test\n").unwrap();
        assert_eq!(map["localhost"], "127.0.0.1".parse::<IpAddr>().unwrap());
        assert_eq!(map["alias.test"], "127.0.0.1".parse::<IpAddr>().unwrap());
        assert_eq!(map["ipv6.test"], "::1".parse::<IpAddr>().unwrap());
        assert_eq!(map.len(), 3);
    }
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
            "cached.invalid".into(),
            (
                Instant::now(),
                wire::Outcome::Addresses(vec!["127.0.0.9".parse().unwrap()]),
            ),
        );
        assert!(next.cache.lock().unwrap().is_empty());
        assert!(root.mapped_host("fixture.invalid").is_none());
        assert_eq!(
            old.resolve("fixture.invalid", 80).await.unwrap()[0].ip(),
            "127.0.0.1".parse::<IpAddr>().unwrap()
        );
    }

    #[tokio::test]
    async fn cached_ip_sets_share_hosts_and_attach_each_requested_port() {
        let resolver = Resolver::default();
        resolver.cache.lock().unwrap().insert(
            "cached.invalid".into(),
            (
                Instant::now() + Duration::from_secs(30),
                wire::Outcome::Addresses(vec![
                    "127.0.0.9".parse().unwrap(),
                    "::1".parse().unwrap(),
                ]),
            ),
        );
        for port in [80, 443, 8443] {
            let addresses = resolver.resolve("CACHED.INVALID", port).await.unwrap();
            assert_eq!(addresses.len(), 2);
            assert!(addresses.iter().all(|address| address.port() == port));
        }
        assert_eq!(resolver.cache.lock().unwrap().len(), 1);
    }

    #[tokio::test]
    async fn negative_cache_is_shared_across_ports_but_not_configurations() {
        let resolver = Resolver::default();
        for (name, negative, expected) in [
            ("missing.invalid", wire::Negative::NameError, "DnsNameError"),
            ("empty.invalid", wire::Negative::NoData, "DnsEmpty"),
        ] {
            resolver.cache.lock().unwrap().insert(
                name.into(),
                (
                    Instant::now() + Duration::from_secs(30),
                    wire::Outcome::Negative(negative),
                ),
            );
            for port in [80, 443] {
                assert_eq!(resolver.resolve(name, port).await, Err(expected));
            }
        }
        let next = resolver.with_hosts(&[]);
        assert!(next.cache.lock().unwrap().is_empty());
        assert!(Arc::ptr_eq(&resolver.permits, &next.permits));
    }
}
