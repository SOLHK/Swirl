//! Bounded system/custom/DoT/HTTP-1.1 DoH resolver. Fake-IP is not implemented.
mod dot;
mod wire;
use std::{
    collections::HashMap,
    net::{IpAddr, SocketAddr},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use std::{future::Future, pin::Pin};
use swirl_subscription::{DnsQueryFamily, DnsTlsServer};
use swirl_transport::BoxStream;
use tokio::{net::lookup_host, sync::Semaphore, time::timeout};

/// The caller selects an already approved outbound for a fixed bootstrap IP.
/// DNS owns TLS verification and wire parsing; it does not depend on protocols.
pub trait QueryTransport: Send + Sync {
    fn connect(
        &self,
        address: SocketAddr,
    ) -> Pin<Box<dyn Future<Output = Result<BoxStream, &'static str>> + Send + '_>>;
}
struct DirectQueryTransport;
impl QueryTransport for DirectQueryTransport {
    fn connect(
        &self,
        address: SocketAddr,
    ) -> Pin<Box<dyn Future<Output = Result<BoxStream, &'static str>> + Send + '_>> {
        Box::pin(async move {
            let stream = tokio::net::TcpStream::connect(address)
                .await
                .map_err(|_| "DnsTlsConnect")?;
            Ok(Box::new(stream) as BoxStream)
        })
    }
}

type Cache = HashMap<String, (Instant, wire::Outcome)>;
type Lookup = Result<Vec<SocketAddr>, &'static str>;
type EndpointGuard = Arc<dyn Fn(SocketAddr) -> bool + Send + Sync>;
#[cfg(test)]
#[path = "query_transport_tests.rs"]
mod query_transport_tests;
const FAILURE_TTL: Duration = Duration::from_secs(1);
// Immutable views share the same cache and in-flight lookup budget. Ingress
// endpoint policies can therefore be scoped without creating another resolver.
#[derive(Clone)]
pub struct Resolver {
    query_family: DnsQueryFamily,
    cache: Arc<Mutex<Cache>>,
    pinned: Option<(String, Vec<IpAddr>)>,
    endpoint_guard: Option<EndpointGuard>,
    permits: Arc<Semaphore>,
    hosts: HashMap<String, IpAddr>,
    servers: Vec<SocketAddr>,
    tls_servers: Vec<DnsTlsServer>,
    system_hosts: HashMap<String, IpAddr>,
}
impl Default for Resolver {
    fn default() -> Self {
        Self {
            query_family: DnsQueryFamily::Dual,
            cache: Arc::new(Mutex::new(HashMap::new())),
            pinned: None,
            endpoint_guard: None,
            permits: Arc::new(Semaphore::new(8)),
            hosts: HashMap::new(),
            servers: Vec::new(),
            tls_servers: Vec::new(),
            system_hosts: HashMap::new(),
        }
    }
}
impl Resolver {
    /// Encrypted classification lookup over the explicitly selected policy.
    /// No system/UDP fallback or endpoint-name bootstrap is possible here.
    pub async fn resolve_with_transport(
        &self,
        host: &str,
        port: u16,
        transport: &dyn QueryTransport,
    ) -> Lookup {
        if port == 0 || !swirl_subscription::valid_host(host) {
            return Err("DnsInvalidTarget");
        }
        if self.tls_servers.is_empty() {
            return Err("DnsEncryptedServerRequired");
        }
        if let Ok(ip) = host.parse() {
            return Ok(vec![SocketAddr::new(ip, port)]);
        }
        if let Some(addresses) = self.pinned_addresses(host, port) {
            return Ok(addresses);
        }
        if let Some(ip) = self.mapped_host(host) {
            return Ok(vec![SocketAddr::new(ip, port)]);
        }
        let key = host.to_ascii_lowercase();
        if let Some(answer) = self.cached(&key, port)? {
            return answer;
        }
        let _permit = timeout(Duration::from_secs(3), self.permits.clone().acquire_owned())
            .await
            .map_err(|_| "DnsBusy")?
            .map_err(|_| "DnsStopped")?;
        if let Some(answer) = self.cached(&key, port)? {
            return answer;
        }
        self.check_configured_endpoints()?;
        let started = Instant::now();
        let resolution = timeout(
            Duration::from_secs(3),
            dot::resolve_with_transport(&self.tls_servers, host, self.query_family, transport),
        )
        .await
        .unwrap_or(Err("DnsTimeout"))
        .map_err(|error| self.remember_failure(key.clone(), error))?;
        let expires = started + Duration::from_secs(u64::from(resolution.ttl));
        if expires > Instant::now() {
            let mut cache = self.cache.lock().map_err(|_| "DnsState")?;
            if cache.len() >= 256 {
                cache.clear();
            }
            cache.insert(key, (expires, resolution.outcome.clone()));
        }
        resolution.outcome.for_port(port)
    }
    fn cached(&self, key: &str, port: u16) -> Result<Option<Lookup>, &'static str> {
        let mut cache = self.cache.lock().map_err(|_| "DnsState")?;
        cache.retain(|_, (expires, _)| *expires > Instant::now());
        Ok(cache.get(key).map(|(_, outcome)| outcome.for_port(port)))
    }

    fn remember_failure(&self, key: String, error: &'static str) -> &'static str {
        // Cache only completed upstream failures, after server failover. Local
        // admission/cancellation, malformed replies and unproven empty answers
        // must not become cached denials. Keep the original diagnostic code.
        if matches!(
            error,
            "DnsTimeout"
                | "DnsLookupFailed"
                | "DnsServerError"
                | "DnsAliasLoop"
                | "DnsAliasDepth"
                | "DnsConnect"
                | "DnsSend"
                | "DnsReceive"
                | "DnsTcpConnect"
                | "DnsTcpWrite"
                | "DnsTcpRead"
                | "DnsTlsConnect"
                | "DnsTlsWrite"
                | "DnsTlsRead"
                | "DnsTlsTimeout"
                | "DnsTlsVerificationOrHandshake"
                | "DnsHttpsConnect"
                | "DnsHttpsRead"
                | "DnsHttpsWrite"
                | "DnsHttpsVerificationOrHandshake"
        ) && let Ok(mut cache) = self.cache.lock()
        {
            let now = Instant::now();
            cache.retain(|_, (expires, _)| *expires > now);
            // A racing failed query must not replace a still-valid result or
            // extend a failure's lifetime on every client request.
            if !cache.contains_key(&key) {
                if cache.len() >= 256 {
                    cache.clear();
                }
                cache.insert(key, (now + FAILURE_TTL, wire::Outcome::Failure(error)));
            }
        }
        error
    }

    /// Each immutable configuration owns a separate cache and host table, while
    /// every generation shares the same cap on still-running OS lookups.
    pub fn with_hosts(&self, hosts: &[swirl_subscription::HostMapping]) -> Self {
        Self {
            query_family: DnsQueryFamily::Dual,
            cache: Arc::new(Mutex::new(HashMap::new())),
            pinned: None,
            endpoint_guard: None,
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
        dns.validate_query_family()?;
        dns.validate_tls()?;
        let mut result = self.with_hosts(&dns.hosts);
        result.query_family = dns.query_family;
        result.servers = dns.servers.clone();
        result.tls_servers = dns.tls_servers.clone();
        if (!dns.servers.is_empty() || !dns.tls_servers.is_empty()) && dns.use_system_hosts {
            result.system_hosts = system_hosts()?;
        }
        Ok(result)
    }
    /// Preserve the configured DNS policy, cache and shared lookup budget while
    /// freezing an already validated endpoint answer for one outbound flow.
    /// Protocols keep the original hostname for SNI and certificate checks.
    pub fn with_pinned_addresses(&self, host: &str, addresses: Vec<IpAddr>) -> Self {
        Self {
            query_family: self.query_family,
            cache: self.cache.clone(),
            pinned: Some((host.to_ascii_lowercase(), addresses)),
            endpoint_guard: self.endpoint_guard.clone(),
            permits: self.permits.clone(),
            hosts: self.hosts.clone(),
            servers: self.servers.clone(),
            tls_servers: self.tls_servers.clone(),
            system_hosts: self.system_hosts.clone(),
        }
    }
    /// Attach an ingress-owned endpoint policy to this immutable resolver view.
    /// Protocols that learn a second physical endpoint (SOCKS5 UDP BND.ADDR)
    /// must consult it after resolution and before sending any packet.
    pub fn with_endpoint_guard(
        mut self,
        guard: impl Fn(SocketAddr) -> bool + Send + Sync + 'static,
    ) -> Self {
        self.endpoint_guard = Some(Arc::new(guard));
        self
    }
    pub fn endpoint_allowed(&self, address: SocketAddr) -> bool {
        self.endpoint_guard
            .as_ref()
            .is_none_or(|guard| guard(address))
    }
    fn check_configured_endpoints(&self) -> Result<(), &'static str> {
        // Run after cache/hosts lookup and before any configured DNS I/O.
        // Checking every configured fallback prevents retrying a denied server.
        // The OS resolver path is unchanged; no fallback is introduced here.
        if self
            .servers
            .iter()
            .chain(self.tls_servers.iter().map(|server| &server.address))
            .any(|address| !self.endpoint_allowed(*address))
        {
            return Err("DnsEndpointForbidden");
        }
        Ok(())
    }
    fn pinned_addresses(&self, host: &str, port: u16) -> Option<Vec<SocketAddr>> {
        self.pinned
            .as_ref()
            .filter(|(name, _)| name.eq_ignore_ascii_case(host))
            .map(|(_, addresses)| {
                addresses
                    .iter()
                    .map(|ip| SocketAddr::new(*ip, port))
                    .collect()
            })
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
        if let Some(addresses) = self.pinned_addresses(host, port) {
            return Ok(addresses);
        }
        if let Some(ip) = self.mapped_host(host) {
            return Ok(vec![SocketAddr::new(ip, port)]);
        }
        if let Some(ip) = self.system_hosts.get(&host.to_ascii_lowercase()) {
            return Ok(vec![SocketAddr::new(*ip, port)]);
        }
        let key = host.to_ascii_lowercase();
        if let Some(result) = self.cached(&key, port)? {
            return result;
        }
        let permit = timeout(Duration::from_secs(3), self.permits.clone().acquire_owned())
            .await
            .map_err(|_| "DnsBusy")?
            .map_err(|_| "DnsStopped")?;
        // Another query may have finished while this one waited for capacity.
        if let Some(result) = self.cached(&key, port)? {
            return result;
        }
        if !self.servers.is_empty() || !self.tls_servers.is_empty() {
            let _permit = permit;
            self.check_configured_endpoints()?;
            let started = Instant::now();
            let resolution = async {
                if self.tls_servers.is_empty() {
                    wire::resolve(&self.servers, host, self.query_family).await
                } else {
                    dot::resolve(&self.tls_servers, host, self.query_family).await
                }
            };
            let answer = timeout(Duration::from_secs(3), resolution)
                .await
                .unwrap_or(Err("DnsTimeout"))
                .map_err(|error| self.remember_failure(key.clone(), error))?;
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
            .map_err(|_| "DnsTimeout")
            .and_then(|result| result.map_err(|_| "DnsTask"))
            .and_then(|result| result.map_err(|_| "DnsLookupFailed"))
            .map_err(|error| self.remember_failure(key.clone(), error))?;
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
    let Some(path) = swirl_platform::system_hosts_path() else {
        return Ok(HashMap::new());
    };
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
    #[tokio::test]
    async fn pinned_endpoint_preserves_policy_budget_and_cannot_rebind() {
        let root = Resolver::default();
        let dns = swirl_subscription::Dns {
            hosts: vec![swirl_subscription::HostMapping {
                name: "endpoint.fixture.invalid".into(),
                address: "127.0.0.1".parse().unwrap(),
            }],
            servers: vec!["127.0.0.1:5353".parse().unwrap()],
            use_system_hosts: false,
            ..Default::default()
        };
        let resolver = root.with_config(&dns).unwrap();
        let approved = vec![
            "203.0.113.1".parse().unwrap(),
            "2001:db8::1".parse().unwrap(),
        ];
        let pinned = resolver.with_pinned_addresses("endpoint.fixture.invalid", approved.clone());
        assert!(Arc::ptr_eq(&resolver.cache, &pinned.cache));
        assert!(Arc::ptr_eq(&resolver.permits, &pinned.permits));
        assert_eq!(resolver.servers, pinned.servers);
        assert_eq!(
            pinned
                .resolve("ENDPOINT.fixture.invalid", 443)
                .await
                .unwrap(),
            approved
                .iter()
                .map(|ip| SocketAddr::new(*ip, 443))
                .collect::<Vec<_>>()
        );
        assert_eq!(
            resolver
                .resolve("endpoint.fixture.invalid", 443)
                .await
                .unwrap(),
            vec!["127.0.0.1:443".parse().unwrap()]
        );
    }
    #[tokio::test]
    async fn scoped_configured_dns_guard_rejects_udp_dot_doh_before_network_or_failure_cache() {
        for protocol in ["udp", "dot", "doh"] {
            let udp = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
            let tcp = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            udp.set_nonblocking(true).unwrap();
            tcp.set_nonblocking(true).unwrap();
            let mut config = swirl_subscription::Dns {
                query_family: DnsQueryFamily::Ipv4Only,
                use_system_hosts: false,
                ..Default::default()
            };
            if protocol == "udp" {
                config.servers.push(udp.local_addr().unwrap());
            } else {
                config.tls_servers.push(DnsTlsServer {
                    address: tcp.local_addr().unwrap(),
                    tls: swirl_subscription::Tls {
                        server_name: "dns.fixture.invalid".into(),
                        alpn: vec![],
                        ca_der_base64: None,
                    },
                    https_path: (protocol == "doh").then(|| "/dns-query".into()),
                });
            }
            let original = Resolver::default().with_config(&config).unwrap();
            let guarded = original.clone().with_endpoint_guard(|_| false);
            assert_eq!(
                guarded.resolve("protected.fixture.invalid", 443).await,
                Err("DnsEndpointForbidden")
            );
            if protocol != "udp" {
                assert_eq!(
                    guarded
                        .resolve_with_transport(
                            "transport.fixture.invalid",
                            443,
                            &DirectQueryTransport
                        )
                        .await,
                    Err("DnsEndpointForbidden")
                );
            }
            assert!(
                original.cache.lock().unwrap().is_empty(),
                "an ingress denial must not poison the shared cache"
            );
            assert_eq!(original.permits.available_permits(), 8);
            assert_eq!(
                udp.recv_from(&mut [0; 512]).unwrap_err().kind(),
                std::io::ErrorKind::WouldBlock
            );
            assert_eq!(
                tcp.accept().unwrap_err().kind(),
                std::io::ErrorKind::WouldBlock
            );
        }
    }

    #[tokio::test]
    async fn guarded_dns_view_keeps_cache_static_answers_and_ordinary_host_policy() {
        let peer = tokio::net::UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let address = peer.local_addr().unwrap();
        let worker = tokio::spawn(async move {
            for _ in 0..2 {
                let mut query = [0; 512];
                let (length, client) = timeout(Duration::from_secs(4), peer.recv_from(&mut query))
                    .await
                    .unwrap()
                    .unwrap();
                assert_eq!(&query[length - 4..length], &[0, 1, 0, 1]);
                let mut reply = query[..length].to_vec();
                reply[2..4].copy_from_slice(&[0x81, 0x80]);
                reply[6..8].copy_from_slice(&[0, 1]);
                reply.extend([0xc0, 0x0c, 0, 1, 0, 1, 0, 0, 0, 60, 0, 4, 203, 0, 113, 8]);
                peer.send_to(&reply, client).await.unwrap();
            }
        });
        let original = Resolver::default()
            .with_config(&swirl_subscription::Dns {
                query_family: DnsQueryFamily::Ipv4Only,
                use_system_hosts: false,
                servers: vec![address],
                hosts: vec![swirl_subscription::HostMapping {
                    name: "static.fixture.invalid".into(),
                    address: "203.0.113.9".parse().unwrap(),
                }],
                ..Default::default()
            })
            .unwrap();
        let guarded = original.clone().with_endpoint_guard(|_| false);
        assert!(Arc::ptr_eq(&original.cache, &guarded.cache));
        assert!(Arc::ptr_eq(&original.permits, &guarded.permits));
        assert_eq!(
            original
                .resolve("cached.fixture.invalid", 80)
                .await
                .unwrap(),
            vec!["203.0.113.8:80".parse().unwrap()]
        );
        assert_eq!(
            guarded
                .resolve("cached.fixture.invalid", 443)
                .await
                .unwrap(),
            vec!["203.0.113.8:443".parse().unwrap()]
        );
        assert_eq!(
            guarded
                .resolve("static.fixture.invalid", 443)
                .await
                .unwrap(),
            vec!["203.0.113.9:443".parse().unwrap()]
        );
        assert_eq!(
            guarded.resolve("2001:db8::1", 443).await.unwrap(),
            vec!["[2001:db8::1]:443".parse().unwrap()]
        );
        assert_eq!(
            guarded.resolve("uncached.fixture.invalid", 443).await,
            Err("DnsEndpointForbidden")
        );
        assert!(
            original
                .cached("uncached.fixture.invalid", 443)
                .unwrap()
                .is_none()
        );
        // The restricted view has not modified the ordinary host resolver or
        // inserted a shared failure: its next real query must still succeed.
        assert_eq!(
            original
                .resolve("uncached.fixture.invalid", 443)
                .await
                .unwrap(),
            vec!["203.0.113.8:443".parse().unwrap()]
        );
        worker.await.unwrap();
    }

    #[tokio::test]
    async fn ipv4_query_policy_preserves_literal_and_static_ipv6_without_os_fallback() {
        use swirl_subscription::{Dns, HostMapping};
        let root = Resolver::default();
        let mut dns = Dns {
            query_family: DnsQueryFamily::Ipv4Only,
            ..Dns::default()
        };
        assert!(matches!(
            root.with_config(&dns),
            Err("DnsQueryFamilyRequiresExplicitServer")
        ));
        dns.servers = vec!["[::1]:5353".parse().unwrap()];
        dns.use_system_hosts = false;
        dns.hosts = vec![HostMapping {
            name: "static.invalid".into(),
            address: "::1".parse().unwrap(),
        }];
        let resolver = root.with_config(&dns).unwrap();
        assert_eq!(
            resolver.resolve("::1", 80).await.unwrap(),
            vec!["[::1]:80".parse().unwrap()]
        );
        assert_eq!(
            resolver.resolve("STATIC.INVALID", 443).await.unwrap(),
            vec!["[::1]:443".parse().unwrap()]
        );
        resolver.remember_failure("cached.invalid".into(), "DnsTimeout");
        dns.query_family = DnsQueryFamily::Dual;
        let next = resolver.with_config(&dns).unwrap();
        assert!(next.cached("cached.invalid", 443).unwrap().is_none());
        assert!(Arc::ptr_eq(&resolver.permits, &next.permits));
    }

    #[test]
    fn failure_cache_preserves_code_deadline_and_successful_answers() {
        let resolver = Resolver::default();
        assert_eq!(
            resolver.remember_failure("failed.invalid".into(), "DnsTimeout"),
            "DnsTimeout"
        );
        let deadline = resolver.cache.lock().unwrap()["failed.invalid"].0;
        resolver.remember_failure("failed.invalid".into(), "DnsServerError");
        assert_eq!(resolver.cache.lock().unwrap()["failed.invalid"].0, deadline);
        assert_eq!(
            resolver.cached("failed.invalid", 443).unwrap(),
            Some(Err("DnsTimeout"))
        );
        assert!(
            resolver
                .with_hosts(&[])
                .cached("failed.invalid", 443)
                .unwrap()
                .is_none()
        );
        resolver
            .cache
            .lock()
            .unwrap()
            .get_mut("failed.invalid")
            .unwrap()
            .0 = Instant::now();
        assert!(resolver.cached("failed.invalid", 443).unwrap().is_none());
        resolver.cache.lock().unwrap().insert(
            "good.invalid".into(),
            (
                Instant::now() + Duration::from_secs(30),
                wire::Outcome::Addresses(vec!["127.0.0.1".parse().unwrap()]),
            ),
        );
        resolver.remember_failure("good.invalid".into(), "DnsServerError");
        assert!(
            resolver
                .cached("good.invalid", 443)
                .unwrap()
                .unwrap()
                .is_ok()
        );
    }

    #[test]
    fn failure_cache_is_bounded_and_excludes_local_and_invalid_response_errors() {
        let resolver = Resolver::default();
        for error in [
            "DnsBusy",
            "DnsStopped",
            "DnsTask",
            "DnsSocket",
            "DnsInvalidTarget",
            "DnsIdentity",
            "DnsQuestion",
            "DnsSoaLength",
            "DnsEmpty",
            "DnsNameError",
            "DnsInconsistentAnswer",
            "DnsHttpsHeader",
        ] {
            assert_eq!(
                resolver.remember_failure("fixture.invalid".into(), error),
                error
            );
            assert!(resolver.cache.lock().unwrap().is_empty());
        }
        for index in 0..257 {
            resolver.remember_failure(format!("{index}.invalid"), "DnsServerError");
            assert!(resolver.cache.lock().unwrap().len() <= 256);
        }
        assert!(resolver.cached("0.invalid", 443).unwrap().is_none());
    }

    #[tokio::test]
    async fn cancelled_upstream_query_does_not_create_failure_cache() {
        for query_family in [DnsQueryFamily::Dual, DnsQueryFamily::Ipv4Only] {
            let peer = tokio::net::UdpSocket::bind("127.0.0.1:0").await.unwrap();
            let resolver = Arc::new(Resolver {
                query_family,
                servers: vec![peer.local_addr().unwrap()],
                ..Resolver::default()
            });
            let owned = resolver.clone();
            let pending =
                tokio::spawn(async move { owned.resolve("cancelled.invalid", 443).await });
            let mut packet = [0u8; 512];
            // Cancellation follows observed network work, not a scheduler delay.
            timeout(Duration::from_secs(1), peer.recv_from(&mut packet))
                .await
                .unwrap()
                .unwrap();
            pending.abort();
            assert!(pending.await.unwrap_err().is_cancelled());
            assert!(resolver.cache.lock().unwrap().is_empty());
            assert_eq!(resolver.permits.available_permits(), 8);
        }
    }

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
