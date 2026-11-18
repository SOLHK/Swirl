use super::*;
use swirl_subscription::{Dns, DnsTlsServer, Tls};

struct HeldTransport {
    calls: std::sync::atomic::AtomicUsize,
    entered: tokio::sync::Notify,
    release: Semaphore,
}
impl QueryTransport for HeldTransport {
    fn connect(
        &self,
        _: SocketAddr,
    ) -> Pin<Box<dyn Future<Output = Result<BoxStream, &'static str>> + Send + '_>> {
        Box::pin(async {
            self.calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            self.entered.notify_one();
            self.release.acquire().await.unwrap().forget();
            Err("DnsTlsConnect")
        })
    }
}
fn held_resolver() -> Resolver {
    Resolver::default()
        .with_config(&Dns {
            query_family: DnsQueryFamily::Ipv4Only,
            use_system_hosts: false,
            tls_servers: vec![DnsTlsServer {
                address: "127.0.0.1:9".parse().unwrap(),
                tls: Tls {
                    server_name: "dns.fixture.invalid".into(),
                    alpn: vec![],
                    ca_der_base64: None,
                },
                https_path: None,
            }],
            ..Dns::default()
        })
        .unwrap()
}
#[tokio::test]
async fn concurrent_shared_hostname_uses_one_query_and_keeps_failure_cache_bounded() {
    let resolver = held_resolver();
    let transport = Arc::new(HeldTransport {
        calls: 0.into(),
        entered: tokio::sync::Notify::new(),
        release: Semaphore::new(0),
    });
    let (arrived, mut arrivals) = tokio::sync::mpsc::unbounded_channel();
    let mut workers = tokio::task::JoinSet::new();
    for port in 1000..1064 {
        let resolver = resolver.clone();
        let transport = transport.clone();
        let arrived = arrived.clone();
        workers.spawn(async move {
            arrived.send(()).unwrap();
            resolver
                .resolve_with_transport("SHARED.fixture.invalid", port, transport.as_ref())
                .await
        });
    }
    for _ in 0..64 {
        arrivals.recv().await.unwrap();
    }
    transport.entered.notified().await;
    assert_eq!(transport.calls.load(std::sync::atomic::Ordering::SeqCst), 1);
    transport.release.add_permits(1);
    while let Some(result) = timeout(Duration::from_secs(2), workers.join_next())
        .await
        .unwrap()
    {
        assert_eq!(result.unwrap(), Err("DnsTlsConnect"));
    }
    assert_eq!(transport.calls.load(std::sync::atomic::Ordering::SeqCst), 1);
    assert_eq!(resolver.cache.lock().unwrap().len(), 1);
}
#[tokio::test]
async fn cancelled_lookup_leader_releases_shared_hostname_for_next_caller() {
    let resolver = held_resolver();
    let transport = Arc::new(HeldTransport {
        calls: 0.into(),
        entered: tokio::sync::Notify::new(),
        release: Semaphore::new(0),
    });
    let worker = {
        let resolver = resolver.clone();
        let transport = transport.clone();
        tokio::spawn(async move {
            resolver
                .resolve_with_transport("shared.fixture.invalid", 443, transport.as_ref())
                .await
        })
    };
    transport.entered.notified().await;
    worker.abort();
    assert!(worker.await.unwrap_err().is_cancelled());
    assert!(resolver.cache.lock().unwrap().is_empty());
    transport.release.add_permits(1);
    assert_eq!(
        timeout(
            Duration::from_secs(2),
            resolver.resolve_with_transport("shared.fixture.invalid", 80, transport.as_ref())
        )
        .await
        .unwrap(),
        Err("DnsTlsConnect")
    );
    assert_eq!(transport.calls.load(std::sync::atomic::Ordering::SeqCst), 2);
    assert_eq!(resolver.permits.available_permits(), 8);
}

#[tokio::test]
async fn zero_ttl_answer_is_shared_only_with_already_registered_waiters() {
    let resolver = Resolver::default();
    let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let release = Arc::new(Semaphore::new(0));
    let (arrived, mut arrivals) = tokio::sync::mpsc::unbounded_channel();
    let mut tasks = tokio::task::JoinSet::new();
    for port in 1000..1064 {
        let resolver = resolver.clone();
        let calls = calls.clone();
        let release = release.clone();
        let arrived = arrived.clone();
        tasks.spawn(async move {
            arrived.send(()).unwrap();
            let answer = resolver
                .share_query("zero-ttl.invalid", port, async {
                    calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                    release.acquire().await.unwrap().forget();
                    Ok(vec![SocketAddr::new("203.0.113.7".parse().unwrap(), port)])
                })
                .await
                .unwrap();
            assert_eq!(
                answer,
                vec![SocketAddr::new("203.0.113.7".parse().unwrap(), port)]
            );
        });
    }
    for _ in 0..64 {
        arrivals.recv().await.unwrap();
    }
    assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 1);
    release.add_permits(1);
    while let Some(result) = timeout(Duration::from_secs(2), tasks.join_next())
        .await
        .unwrap()
    {
        result.unwrap();
    }
    assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 1);
    assert!(resolver.cache.lock().unwrap().is_empty());
    let fresh = resolver
        .share_query("zero-ttl.invalid", 443, async {
            Ok(vec!["203.0.113.8:443".parse().unwrap()])
        })
        .await
        .unwrap();
    assert_eq!(
        fresh,
        vec!["203.0.113.8:443".parse::<SocketAddr>().unwrap()]
    );
}

struct Bootstrapping {
    resolver: Resolver,
    completed: std::sync::atomic::AtomicBool,
}
impl QueryTransport for Bootstrapping {
    fn connect(
        &self,
        _: SocketAddr,
    ) -> Pin<Box<dyn Future<Output = Result<BoxStream, &'static str>> + Send + '_>> {
        Box::pin(async {
            let answer = self.resolver.resolve("shared.fixture.invalid", 443).await;
            assert!(answer.is_err());
            assert_ne!(answer, Err("DnsBusy"));
            assert_ne!(answer, Err("DnsTimeout"));
            self.completed
                .store(true, std::sync::atomic::Ordering::SeqCst);
            Err("FixtureBootstrapCompleted")
        })
    }
}
#[tokio::test]
async fn routed_query_can_bootstrap_the_same_proxy_hostname_without_self_waiting() {
    let peer = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let mut resolver = held_resolver();
    resolver.tls_servers[0].address = peer.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let (socket, _) = peer.accept().await.unwrap();
        drop(socket);
    });
    let transport = Bootstrapping {
        resolver: resolver.clone(),
        completed: false.into(),
    };
    let answer = timeout(
        Duration::from_secs(2),
        resolver.resolve_with_transport("shared.fixture.invalid", 80, &transport),
    )
    .await
    .expect("routed DNS waited on its own bootstrap flight");
    assert_eq!(answer, Err("DnsTlsConnect"));
    assert!(
        transport
            .completed
            .load(std::sync::atomic::Ordering::SeqCst)
    );
    server.await.unwrap();
}

struct Refusing {
    seen: Mutex<Vec<SocketAddr>>,
}
impl QueryTransport for Refusing {
    fn connect(
        &self,
        address: SocketAddr,
    ) -> Pin<Box<dyn Future<Output = Result<BoxStream, &'static str>> + Send + '_>> {
        self.seen.lock().unwrap().push(address);
        Box::pin(async { Err("FixturePolicyUnavailable") })
    }
}
#[tokio::test]
async fn encrypted_policy_transport_failure_never_tries_direct_endpoint_or_system_fallback() {
    for https_path in [None, Some("/dns-query".into())] {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let tls = DnsTlsServer {
            address,
            tls: Tls {
                server_name: "dns.fixture.invalid".into(),
                alpn: vec![],
                ca_der_base64: None,
            },
            https_path,
        };
        let resolver = Resolver::default()
            .with_config(&Dns {
                tls_servers: vec![tls],
                use_system_hosts: false,
                ..Dns::default()
            })
            .unwrap();
        let transport = Refusing {
            seen: Mutex::new(vec![]),
        };
        assert!(
            resolver
                .resolve_with_transport("unknown.fixture.invalid", 443, &transport)
                .await
                .is_err()
        );
        assert_eq!(*transport.seen.lock().unwrap(), vec![address]);
        assert_eq!(
            listener.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
    }
}
#[tokio::test]
async fn policy_transport_does_not_accept_plaintext_only_configuration() {
    let resolver = Resolver::default()
        .with_config(&Dns {
            servers: vec!["127.0.0.1:53".parse().unwrap()],
            use_system_hosts: false,
            ..Dns::default()
        })
        .unwrap();
    let transport = Refusing {
        seen: Mutex::new(vec![]),
    };
    assert_eq!(
        resolver
            .resolve_with_transport("fixture.invalid", 443, &transport)
            .await,
        Err("DnsEncryptedServerRequired")
    );
    assert!(transport.seen.lock().unwrap().is_empty());
}
#[tokio::test]
async fn invalid_policy_dns_target_is_rejected_before_transport() {
    let resolver = Resolver::default();
    let transport = Refusing {
        seen: Mutex::new(vec![]),
    };
    assert_eq!(
        resolver
            .resolve_with_transport("bad/host", 443, &transport)
            .await,
        Err("DnsInvalidTarget")
    );
    assert!(transport.seen.lock().unwrap().is_empty());
}

#[tokio::test]
async fn policy_endpoint_denial_survives_dot_doh_without_failover_or_shared_failure_cache() {
    struct Denied(Mutex<usize>);
    impl QueryTransport for Denied {
        fn connect(
            &self,
            _: SocketAddr,
        ) -> Pin<Box<dyn Future<Output = Result<BoxStream, &'static str>> + Send + '_>> {
            *self.0.lock().unwrap() += 1;
            Box::pin(async { Err("DnsEndpointForbidden") })
        }
    }
    for https_path in [None, Some("/dns-query".into())] {
        let first = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let second = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        first.set_nonblocking(true).unwrap();
        second.set_nonblocking(true).unwrap();
        let resolver = Resolver::default()
            .with_config(&Dns {
                tls_servers: [first.local_addr().unwrap(), second.local_addr().unwrap()]
                    .into_iter()
                    .map(|address| DnsTlsServer {
                        address,
                        tls: Tls {
                            server_name: "dns.fixture.invalid".into(),
                            alpn: vec![],
                            ca_der_base64: None,
                        },
                        https_path: https_path.clone(),
                    })
                    .collect(),
                use_system_hosts: false,
                ..Dns::default()
            })
            .unwrap();
        let transport = Denied(Mutex::new(0));
        assert_eq!(
            resolver
                .resolve_with_transport("denied-policy.fixture.invalid", 443, &transport)
                .await,
            Err("DnsEndpointForbidden")
        );
        assert_eq!(
            *transport.0.lock().unwrap(),
            1,
            "a boundary denial is not retryable DNS failover"
        );
        assert!(resolver.cache.lock().unwrap().is_empty());
        assert_eq!(
            first.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
        assert_eq!(
            second.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
    }
}
