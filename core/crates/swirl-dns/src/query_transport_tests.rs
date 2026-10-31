use super::*;
use swirl_subscription::{Dns, DnsTlsServer, Tls};
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
        fn connect(&self, _: SocketAddr) -> Pin<Box<dyn Future<Output = Result<BoxStream, &'static str>> + Send + '_>> {
            *self.0.lock().unwrap() += 1;
            Box::pin(async { Err("DnsEndpointForbidden") })
        }
    }
    for https_path in [None, Some("/dns-query".into())] {
        let first = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let second = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        first.set_nonblocking(true).unwrap();
        second.set_nonblocking(true).unwrap();
        let resolver = Resolver::default().with_config(&Dns {
            tls_servers: [first.local_addr().unwrap(), second.local_addr().unwrap()].into_iter().map(|address| DnsTlsServer {
                address,
                tls: Tls { server_name: "dns.fixture.invalid".into(), alpn: vec![], ca_der_base64: None },
                https_path: https_path.clone(),
            }).collect(),
            use_system_hosts: false,
            ..Dns::default()
        }).unwrap();
        let transport = Denied(Mutex::new(0));
        assert_eq!(resolver.resolve_with_transport("denied-policy.fixture.invalid", 443, &transport).await, Err("DnsEndpointForbidden"));
        assert_eq!(*transport.0.lock().unwrap(), 1, "a boundary denial is not retryable DNS failover");
        assert!(resolver.cache.lock().unwrap().is_empty());
        assert_eq!(first.accept().unwrap_err().kind(), std::io::ErrorKind::WouldBlock);
        assert_eq!(second.accept().unwrap_err().kind(), std::io::ErrorKind::WouldBlock);
    }
}
