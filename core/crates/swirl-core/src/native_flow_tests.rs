use super::*;
use crate::v2::{Core, RuntimeConfig};
use std::collections::BTreeMap;
use swirl_subscription::{
    Dns, DnsTlsServer, Limits, PolicyStrategy, Tls,
    v2::{
        ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, Group, Mode, PolicyDocument, Probe,
        Target,
    },
};
use tokio::io::{AsyncReadExt, AsyncWriteExt};

const STORE: &str = "a0000000-0000-4000-8000-000000000001";
const START: &str = "b0000000-0000-4000-8000-000000000001";
const REQUEST: &str = "b0000000-0000-4000-8000-000000000002";

fn config() -> RuntimeConfig {
    RuntimeConfig {
        schema: 2,
        listen: "127.0.0.1:0".parse().unwrap(),
        nodes: vec![swirl_subscription::Node {
            id: "c0000000-0000-4000-8000-000000000001".into(),
            outbound: Outbound::HttpConnect {
                host: "127.0.0.1".into(),
                port: 9,
                auth: None,
                tls: None,
            },
        }],
        policy: PolicyDocument {
            schema: 2,
            mode: Mode::Direct,
            default_policy: DefaultPolicy {
                id: DEFAULT_POLICY_ID.into(),
                target: Target::Node {
                    id: "c0000000-0000-4000-8000-000000000001".into(),
                },
            },
            service_policies: vec![],
            groups: vec![],
            explicit_direct_rules: vec![],
            custom_rules: vec![],
            missing_targets: vec![],
            classification_dns: ClassificationDns::Disabled,
        },
        dns: Dns {
            tls_servers: vec![DnsTlsServer {
                // Literal destinations in these tests never query this endpoint.
                address: "192.0.2.1:853".parse().unwrap(),
                tls: Tls {
                    server_name: "dns.fixture.invalid".into(),
                    alpn: vec![],
                    ca_der_base64: None,
                },
                https_path: None,
            }],
            ..Dns::default()
        },
        inbound_auth: None,
        limits: Limits::default(),
        china_rules_directory: None,
        node_sources: BTreeMap::new(),
        transports: BTreeMap::new(),
    }
}
fn start(config: RuntimeConfig) -> Core {
    Core::start(config, STORE.into(), 1, START.into()).unwrap()
}
fn target(address: SocketAddr) -> NetworkTarget {
    NetworkTarget {
        host: address.ip().to_string(),
        port: address.port(),
    }
}
fn runtime() -> tokio::runtime::Runtime {
    tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap()
}
async fn until(mut condition: impl FnMut() -> bool) {
    timeout(Duration::from_secs(3), async {
        while !condition() {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
}

fn gateway(dispatcher: &FlowDispatcher) -> FlowDispatcher {
    dispatcher
        .with_gateway_admission(
            vec![
                "192.168.77.1".parse().unwrap(),
                "192.168.1.20".parse().unwrap(),
                "fd00::5".parse().unwrap(),
            ],
            vec![
                "192.168.77.1".parse().unwrap(),
                "192.168.1.20".parse().unwrap(),
                "fd00::5".parse().unwrap(),
            ],
        )
        .unwrap()
}

#[test]
fn gateway_address_boundary_normalizes_aliases_without_restricting_outbound_family() {
    let guard = GatewayAdmission::new(
        vec!["192.168.77.1".parse().unwrap(), "fd00::5".parse().unwrap()],
        vec!["192.168.1.20".parse().unwrap()],
    )
    .unwrap();
    let lan = "192.168.77.12:50000".parse().unwrap();
    for host in [
        "localhost",
        "x.localhost",
        "127.0.0.2",
        "::ffff:127.0.0.1",
        "::1",
        "192.168.77.1",
        "192.168.1.20",
        "fd00::5",
        "169.254.169.254",
        "fe80::1234",
        "224.0.0.1",
        "ff02::1",
        "0.0.0.0",
        "::",
        "255.255.255.255",
    ] {
        assert_eq!(
            guard.target(
                lan,
                &NetworkTarget {
                    host: host.into(),
                    port: 443
                }
            ),
            Err("GatewayHostAccessDenied"),
            "{host}"
        );
    }
    for host in [
        "target.fixture.invalid",
        "203.0.113.8",
        "192.168.77.20",
        "2001:db8::8",
    ] {
        assert!(
            guard
                .target(
                    lan,
                    &NetworkTarget {
                        host: host.into(),
                        port: 443
                    }
                )
                .is_ok(),
            "{host}"
        );
    }
    assert_eq!(
        guard.target(
            "192.0.2.5:50000".parse().unwrap(),
            &target("203.0.113.8:443".parse().unwrap())
        ),
        Err("GatewaySourceDenied")
    );
    assert!(
        guard
            .target(
                "[fd00::5]:50000".parse().unwrap(),
                &target("[::1]:443".parse().unwrap())
            )
            .is_ok()
    );
}

#[test]
fn gateway_final_route_blocks_hosts_rebinding_before_tcp_udp_or_dns_delivery() {
    let mut candidate = config();
    for (name, ip) in [
        ("loop.fixture.invalid", "127.0.0.1"),
        ("mapped.fixture.invalid", "::ffff:127.0.0.1"),
        ("wan.fixture.invalid", "192.168.1.20"),
        ("v6host.fixture.invalid", "fd00::5"),
        ("link.fixture.invalid", "169.254.169.254"),
    ] {
        candidate.dns.hosts.push(swirl_subscription::HostMapping {
            name: name.into(),
            address: ip.parse().unwrap(),
        });
    }
    let mut core = start(candidate);
    let dispatcher = gateway(&core.flow_dispatcher().unwrap());
    runtime().block_on(async {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let source = "192.168.77.12:50000".parse().unwrap();
        // These names model the domain handed to native ingress after the
        // packet adapter reverses a Fake-IP. No new DNS implementation is used.
        for host in [
            "loop.fixture.invalid",
            "mapped.fixture.invalid",
            "wan.fixture.invalid",
            "v6host.fixture.invalid",
            "link.fixture.invalid",
        ] {
            let (_client, inbound) = tokio::io::duplex(64);
            let destination = NetworkTarget {
                host: host.into(),
                port,
            };
            assert_eq!(
                dispatcher
                    .relay_tcp(inbound, source, destination.clone())
                    .await,
                Err("GatewayHostAccessDenied")
            );
            assert_eq!(
                dispatcher.open_udp(source, destination).await.err(),
                Some("GatewayHostAccessDenied")
            );
            assert_eq!(
                dispatcher.resolve_dns(host, port, source).await,
                Err("GatewayHostAccessDenied")
            );
        }
        assert!(
            timeout(Duration::from_millis(100), listener.accept())
                .await
                .is_err()
        );
        until(|| core.snapshot().unwrap()["active"] == 0).await;
    });
    let snapshot = core.snapshot().unwrap();
    assert_eq!(snapshot["upload"], 0);
    assert_eq!(snapshot["download"], 0);
    assert_eq!(snapshot["failed"], 15);
    core.stop();
}

#[test]
fn gateway_classification_rejects_protected_proxy_and_dns_before_tcp_udp_or_lookup_io() {
    for protected_proxy in [true, false] {
        let proxy = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let dns = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        proxy.set_nonblocking(true).unwrap();
        dns.set_nonblocking(true).unwrap();
        let mut candidate = config();
        candidate.policy.mode = Mode::Rule;
        candidate.policy.classification_dns = ClassificationDns::ViaDefaultPolicy;
        candidate.nodes[0].outbound = Outbound::HttpConnect {
            host: if protected_proxy {
                "127.0.0.1"
            } else {
                "unresolved-classification-proxy.fixture.invalid"
            }
            .into(),
            port: proxy.local_addr().unwrap().port(),
            auth: None,
            tls: None,
        };
        if !protected_proxy {
            candidate.dns.tls_servers[0].address = dns.local_addr().unwrap();
        }
        let mut core = start(candidate);
        let dispatcher = gateway(&core.flow_dispatcher().unwrap());
        runtime().block_on(async {
            let source = "192.168.77.12:50000".parse().unwrap();
            let destination = NetworkTarget {
                host: "gateway-classification.fixture.invalid".into(),
                port: 443,
            };
            let (_client, inbound) = tokio::io::duplex(64);
            assert_eq!(
                dispatcher
                    .relay_tcp(inbound, source, destination.clone())
                    .await,
                Err("ClassificationIngressDenied")
            );
            assert_eq!(
                dispatcher.open_udp(source, destination.clone()).await.err(),
                Some("ClassificationIngressDenied")
            );
            assert_eq!(
                dispatcher
                    .resolve_dns(&destination.host, destination.port, source)
                    .await,
                Err("ClassificationIngressDenied")
            );
            until(|| core.snapshot().unwrap()["active"] == 0).await;
        });
        assert_eq!(
            proxy.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
        assert_eq!(
            dns.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
        assert_eq!(core.snapshot().unwrap()["failed"], 3);
        core.stop();
    }
}

#[test]
fn gateway_configured_dns_guard_covers_direct_mandatory_and_proxy_bootstrap_paths() {
    for https_path in [None, Some("/dns-query".into())] {
        for path in ["direct", "mandatory", "bootstrap"] {
            let dns = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let proxy = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            dns.set_nonblocking(true).unwrap();
            proxy.set_nonblocking(true).unwrap();
            let mut candidate = config();
            candidate.dns.tls_servers[0].address = dns.local_addr().unwrap();
            candidate.dns.tls_servers[0].https_path = https_path.clone();
            let host = if path == "bootstrap" {
                "known-target.fixture.invalid"
            } else {
                "unresolved-target.fixture.invalid"
            };
            match path {
                "direct" => {}
                "mandatory" => {
                    candidate.policy.mode = Mode::Rule;
                    candidate.policy.explicit_direct_rules.push(
                        swirl_subscription::v2::PolicyRule {
                            id: "60000000-0000-4000-8000-000000000009".into(),
                            name: "gateway configured DNS fixture".into(),
                            enabled: true,
                            priority: 1,
                            matcher: swirl_subscription::Matcher::Cidr {
                                value: "198.51.100.0/24".parse().unwrap(),
                                resolve: true,
                            },
                            target: Target::Direct {},
                        },
                    );
                }
                "bootstrap" => {
                    candidate.policy.mode = Mode::Global;
                    candidate.nodes[0].outbound = Outbound::HttpConnect {
                        host: "unresolved-proxy.fixture.invalid".into(),
                        port: proxy.local_addr().unwrap().port(),
                        auth: None,
                        tls: None,
                    };
                    candidate.dns.hosts.push(swirl_subscription::HostMapping {
                        name: host.into(),
                        address: "203.0.113.8".parse().unwrap(),
                    });
                }
                _ => unreachable!(),
            }
            let mut core = start(candidate);
            let dispatcher = gateway(&core.flow_dispatcher().unwrap());
            runtime().block_on(async {
                let source = "192.168.77.12:50000".parse().unwrap();
                let destination = NetworkTarget {
                    host: host.into(),
                    port: 443,
                };
                let (_client, inbound) = tokio::io::duplex(64);
                assert_eq!(
                    dispatcher
                        .relay_tcp(inbound, source, destination.clone())
                        .await,
                    Err("DnsEndpointForbidden"),
                    "{path}"
                );
                assert_eq!(
                    dispatcher.open_udp(source, destination).await.err(),
                    Some("DnsEndpointForbidden"),
                    "{path}"
                );
                assert_eq!(
                    dispatcher.resolve_dns(host, 443, source).await,
                    Err("DnsEndpointForbidden"),
                    "{path}"
                );
                until(|| core.snapshot().unwrap()["active"] == 0).await;
            });
            assert_eq!(
                dns.accept().unwrap_err().kind(),
                std::io::ErrorKind::WouldBlock
            );
            assert_eq!(
                proxy.accept().unwrap_err().kind(),
                std::io::ErrorKind::WouldBlock
            );
            core.stop();
        }
    }
}

#[test]
fn gateway_clone_preserves_host_flows_and_does_not_mutate_original_dispatcher() {
    let mut core = start(config());
    let original = core.flow_dispatcher().unwrap();
    let restricted = gateway(&original);
    assert!(matches!(
        restricted.with_gateway_admission(
            vec!["192.168.77.1".parse().unwrap()],
            vec!["192.168.77.1".parse().unwrap()]
        ),
        Err("GatewayAdmissionAlreadySet")
    ));
    runtime().block_on(async {
        for (dispatcher, source) in [
            (
                restricted,
                "192.168.77.1:50000".parse::<SocketAddr>().unwrap(),
            ),
            (
                original,
                "192.168.77.12:50000".parse::<SocketAddr>().unwrap(),
            ),
        ] {
            let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
            let address = listener.local_addr().unwrap();
            let server = tokio::spawn(async move {
                let (mut stream, _) = listener.accept().await.unwrap();
                let mut request = [0; 4];
                stream.read_exact(&mut request).await.unwrap();
                assert_eq!(&request, b"host");
                stream.write_all(b"okay").await.unwrap();
                stream.shutdown().await.unwrap();
            });
            let (mut client, inbound) = tokio::io::duplex(64);
            let relay = tokio::spawn({
                let dispatcher = dispatcher.clone();
                async move { dispatcher.relay_tcp(inbound, source, target(address)).await }
            });
            client.write_all(b"host").await.unwrap();
            client.shutdown().await.unwrap();
            let mut response = Vec::new();
            timeout(Duration::from_secs(3), client.read_to_end(&mut response))
                .await
                .unwrap()
                .unwrap();
            assert_eq!(response, b"okay");
            relay.await.unwrap().unwrap();
            server.await.unwrap();
            let socket = UdpSocket::bind("127.0.0.1:0").await.unwrap();
            let address = socket.local_addr().unwrap();
            let server = tokio::spawn(async move {
                let mut bytes = [0; 32];
                let (n, peer) = socket.recv_from(&mut bytes).await.unwrap();
                socket.send_to(&bytes[..n], peer).await.unwrap();
            });
            let mut flow = dispatcher.open_udp(source, target(address)).await.unwrap();
            flow.send(b"host-udp").await.unwrap();
            let mut reply = [0; 32];
            let size = timeout(Duration::from_secs(3), flow.recv(&mut reply))
                .await
                .unwrap()
                .unwrap();
            assert_eq!(&reply[..size], b"host-udp");
            drop(flow);
            server.await.unwrap();
        }
        until(|| core.snapshot().unwrap()["active"] == 0).await;
    });
    core.stop();
}

#[test]
fn gateway_dns_allows_remote_ipv6_answers_but_rejects_unknown_ipv6_sources() {
    let mut candidate = config();
    candidate.dns.hosts.push(swirl_subscription::HostMapping {
        name: "remote6.fixture.invalid".into(),
        address: "2001:db8::8".parse().unwrap(),
    });
    let mut core = start(candidate);
    let dispatcher = gateway(&core.flow_dispatcher().unwrap());
    runtime().block_on(async {
        assert_eq!(
            dispatcher
                .resolve_dns(
                    "remote6.fixture.invalid",
                    443,
                    "192.168.77.12:50000".parse().unwrap()
                )
                .await
                .unwrap(),
            vec!["[2001:db8::8]:443".parse::<SocketAddr>().unwrap()]
        );
        assert_eq!(
            dispatcher
                .resolve_dns(
                    "remote6.fixture.invalid",
                    443,
                    "[fd00::12]:50000".parse().unwrap()
                )
                .await,
            Err("GatewaySourceDenied")
        );
    });
    core.stop();
}

#[test]
fn gateway_admission_requires_bounded_explicit_host_inventory() {
    assert!(matches!(
        GatewayAdmission::new(vec![], vec!["192.168.77.1".parse().unwrap()]),
        Err("GatewayAddressInventory")
    ));
    for host in ["0.0.0.0", "::", "224.0.0.1", "255.255.255.255"] {
        assert!(matches!(
            GatewayAdmission::new(
                vec![host.parse().unwrap()],
                vec!["192.168.77.1".parse().unwrap()]
            ),
            Err("GatewayAddressInventory")
        ));
    }
}

#[test]
fn native_tcp_real_loopback_dual_stack_preserves_half_close_and_accounting() {
    let mut core = start(config());
    let dispatcher = core.flow_dispatcher().unwrap();
    runtime().block_on(async {
        for bind in ["127.0.0.1:0", "[::1]:0"] {
            let listener = tokio::net::TcpListener::bind(bind).await.unwrap();
            let address = listener.local_addr().unwrap();
            let server = tokio::spawn(async move {
                let (mut stream, _) = listener.accept().await.unwrap();
                let mut received = Vec::new();
                stream.read_to_end(&mut received).await.unwrap();
                assert_eq!(received, b"native-half-close");
                stream.write_all(b"after-fin").await.unwrap();
                stream.shutdown().await.unwrap();
            });
            let (mut client, incoming) = tokio::io::duplex(4096);
            let relay = tokio::spawn({
                let dispatcher = dispatcher.clone();
                async move {
                    dispatcher
                        .relay_tcp(
                            incoming,
                            "192.0.2.2:12000".parse().unwrap(),
                            target(address),
                        )
                        .await
                }
            });
            client.write_all(b"native-half-close").await.unwrap();
            client.shutdown().await.unwrap();
            let mut reply = Vec::new();
            timeout(Duration::from_secs(3), client.read_to_end(&mut reply))
                .await
                .unwrap()
                .unwrap();
            assert_eq!(reply, b"after-fin");
            relay.await.unwrap().unwrap();
            server.await.unwrap();
        }
    });
    let snapshot = core.snapshot().unwrap();
    assert_eq!(snapshot["accepted"], 2);
    assert_eq!(snapshot["active"], 0);
    assert_eq!(snapshot["upload"], 34);
    assert_eq!(snapshot["download"], 18);
    assert_eq!(snapshot["failed"], 0);
    assert!(
        snapshot["connections"]
            .as_array()
            .unwrap()
            .iter()
            .all(|r| r["ended"] == true && r["node"] == "SWIRL_V2_DIRECT")
    );
    core.stop();
}

#[test]
fn native_udp_real_loopback_dual_stack_keeps_empty_datagrams_and_rejects_truncation() {
    let mut core = start(config());
    let dispatcher = core.flow_dispatcher().unwrap();
    runtime().block_on(async {
        for bind in ["127.0.0.1:0", "[::1]:0"] {
            let socket = UdpSocket::bind(bind).await.unwrap();
            let address = socket.local_addr().unwrap();
            let server = tokio::spawn(async move {
                let mut buffer = [0; 512];
                for _ in 0..4 {
                    let (size, peer) = socket.recv_from(&mut buffer).await.unwrap();
                    socket.send_to(&buffer[..size], peer).await.unwrap();
                }
            });
            let mut flow = dispatcher
                .open_udp("192.0.2.2:12000".parse().unwrap(), target(address))
                .await
                .unwrap();
            let mut buffer = [0; 64];
            flow.send(b"datagram").await.unwrap();
            let size = timeout(Duration::from_secs(3), flow.recv(&mut buffer))
                .await
                .unwrap()
                .unwrap();
            assert_eq!(&buffer[..size], b"datagram");
            flow.send(b"").await.unwrap();
            assert_eq!(
                timeout(Duration::from_secs(3), flow.recv(&mut []))
                    .await
                    .unwrap()
                    .unwrap(),
                0
            );
            flow.send(b"do-not-truncate").await.unwrap();
            assert_eq!(
                flow.recv(&mut [0; 2]).await,
                Err("UdpReceiveBufferTooSmall")
            );
            flow.send(b"still-open").await.unwrap();
            let size = flow.recv(&mut buffer).await.unwrap();
            assert_eq!(&buffer[..size], b"still-open");
            drop(flow);
            server.await.unwrap();
        }
        until(|| core.snapshot().unwrap()["active"] == 0).await;
    });
    core.stop();
}

struct CounterWake {
    local: Arc<Counters>,
    total: Arc<Counters>,
    upload: bool,
    observed: std::sync::Mutex<Option<(u64, u64)>>,
}
impl std::task::Wake for CounterWake {
    fn wake(self: Arc<Self>) {
        self.wake_by_ref();
    }
    fn wake_by_ref(self: &Arc<Self>) {
        let counts = if self.upload {
            (
                self.local.upload.load(Ordering::Relaxed),
                self.total.upload.load(Ordering::Relaxed),
            )
        } else {
            (
                self.local.download.load(Ordering::Relaxed),
                self.total.download.load(Ordering::Relaxed),
            )
        };
        *self.observed.lock().unwrap() = Some(counts);
    }
}
fn counter_wake(upload: bool) -> Arc<CounterWake> {
    Arc::new(CounterWake {
        local: Arc::new(Counters::default()),
        total: Arc::new(Counters::default()),
        upload,
        observed: std::sync::Mutex::new(None),
    })
}

#[tokio::test]
async fn udp_send_counters_are_visible_at_completion_wake_including_failures() {
    use std::future::Future;
    for result in [Ok(()), Err("UdpSendTimeout"), Err("SessionRevoked")] {
        let observer = counter_wake(true);
        let waker = std::task::Waker::from(observer.clone());
        let mut context = std::task::Context::from_waker(&waker);
        let (complete, mut completed) = oneshot::channel();
        assert!(
            std::pin::Pin::new(&mut completed)
                .poll(&mut context)
                .is_pending()
        );
        let request = SendRequest {
            payload: vec![0xa7; 1200],
            complete,
        };
        assert_eq!(
            request.finish(result, &observer.local, &observer.total),
            result
        );
        let expected = if result.is_ok() { 1200 } else { 0 };
        // The waker executes synchronously at publication, before the producer
        // can run any later accounting. No sleep or counter polling is involved.
        assert_eq!(
            *observer.observed.lock().unwrap(),
            Some((expected, expected))
        );
        assert_eq!(completed.await.unwrap(), result);
    }
}

#[tokio::test]
async fn udp_download_counters_are_visible_at_response_wake() {
    use std::future::Future;
    let observer = counter_wake(false);
    let waker = std::task::Waker::from(observer.clone());
    let mut context = std::task::Context::from_waker(&waker);
    let (responses, mut received) = mpsc::channel(1);
    let mut receive = Box::pin(received.recv());
    assert!(receive.as_mut().poll(&mut context).is_pending());
    assert!(queue_udp_response(
        vec![0xa7; 1200],
        &responses,
        &observer.local,
        &observer.total,
    ));
    assert_eq!(*observer.observed.lock().unwrap(), Some((1200, 1200)));
    assert_eq!(receive.await.unwrap(), vec![0xa7; 1200]);
}

#[tokio::test]
async fn udp_full_closed_and_oversized_responses_do_not_count_successful_bytes() {
    let local = Counters::default();
    let total = Counters::default();
    let (responses, mut received) = mpsc::channel(1);
    assert!(queue_udp_response(
        vec![1; 1200],
        &responses,
        &local,
        &total
    ));
    assert!(!queue_udp_response(
        vec![2; 1200],
        &responses,
        &local,
        &total
    ));
    assert_eq!(local.download.load(Ordering::Relaxed), 1200);
    assert_eq!(total.download.load(Ordering::Relaxed), 1200);
    assert_eq!(received.recv().await.unwrap(), vec![1; 1200]);
    assert!(!queue_udp_response(
        vec![3; UDP_MAX_PAYLOAD + 1],
        &responses,
        &local,
        &total
    ));
    drop(received);
    assert!(!queue_udp_response(
        vec![4; 1200],
        &responses,
        &local,
        &total
    ));
    assert_eq!(local.download.load(Ordering::Relaxed), 1200);
    assert_eq!(total.download.load(Ordering::Relaxed), 1200);
    assert_eq!(local.udp_dropped.load(Ordering::Relaxed), 3);
    assert_eq!(total.udp_dropped.load(Ordering::Relaxed), 3);
}

#[test]
fn native_and_system_proxy_share_one_connection_budget_and_drop_releases_it() {
    let mut config = config();
    config.limits.max_connections = 1;
    let mut core = start(config);
    let dispatcher = core.flow_dispatcher().unwrap();
    runtime().block_on(async {
        let peer = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let address = peer.local_addr().unwrap();
        let flow = dispatcher
            .open_udp("192.0.2.2:10000".parse().unwrap(), target(address))
            .await
            .unwrap();
        assert!(matches!(
            core.prepare_native_tun(),
            Err("TunRequiresQuiescentCore")
        ));
        assert!(matches!(
            dispatcher
                .open_udp("192.0.2.2:10001".parse().unwrap(), target(address))
                .await,
            Err("ConnectionLimit")
        ));
        let inbound = tokio::net::TcpStream::connect(core.address())
            .await
            .unwrap();
        until(|| core.snapshot().unwrap()["rejected"].as_u64().unwrap() >= 2).await;
        assert_eq!(core.snapshot().unwrap()["active"], 1);
        drop(inbound);
        drop(flow);
        until(|| core.snapshot().unwrap()["active"] == 0).await;
        // Exercise the publication boundary repeatedly: active == 0 must mean
        // the shared connection permit is already available to a new caller.
        for port in 10002..10010 {
            let next = dispatcher
                .open_udp(
                    SocketAddr::new("192.0.2.2".parse().unwrap(), port),
                    target(address),
                )
                .await
                .unwrap();
            drop(next);
            until(|| core.snapshot().unwrap()["active"] == 0).await;
        }
    });
    core.stop();
}

#[test]
fn native_reject_does_not_fall_back_to_direct() {
    let mut rejected = config();
    rejected.policy.mode = Mode::Rule;
    rejected.policy.custom_rules = vec![swirl_subscription::v2::PolicyRule {
        id: "d0000000-0000-4000-8000-000000000001".into(),
        name: "Reject fixture".into(),
        enabled: true,
        priority: 0,
        matcher: swirl_subscription::Matcher::Domain {
            value: "target.fixture.invalid".into(),
        },
        target: Target::Reject {},
    }];
    let mut core = start(rejected);
    let dispatcher = core.flow_dispatcher().unwrap();
    runtime().block_on(async {
        let destination = NetworkTarget {
            host: "target.fixture.invalid".into(),
            port: 443,
        };
        let (_client, stream) = tokio::io::duplex(64);
        assert_eq!(
            dispatcher
                .relay_tcp(
                    stream,
                    "192.0.2.2:10000".parse().unwrap(),
                    destination.clone()
                )
                .await,
            Err("Rejected")
        );
        assert!(matches!(
            dispatcher
                .open_udp("192.0.2.2:10000".parse().unwrap(), destination)
                .await,
            Err("Rejected")
        ));
    });
    let snapshot = core.snapshot().unwrap();
    assert_eq!(snapshot["failed"], 2);
    assert!(
        snapshot["connections"]
            .as_array()
            .unwrap()
            .iter()
            .all(|r| r["category"] == "reject")
    );
    core.stop();
}

#[test]
fn stopping_core_revokes_idle_udp_and_retained_dispatcher() {
    let mut core = start(config());
    let dispatcher = core.flow_dispatcher().unwrap();
    let runtime = runtime();
    let mut flow = runtime.block_on(async {
        let peer = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        dispatcher
            .open_udp(
                "192.0.2.2:10000".parse().unwrap(),
                target(peer.local_addr().unwrap()),
            )
            .await
            .unwrap()
    });
    core.stop();
    runtime.block_on(async {
        assert_eq!(flow.recv(&mut [0; 1]).await, Err("SessionRevoked"));
        assert_eq!(flow.send(b"after-stop").await, Err("SessionRevoked"));
        assert_eq!(flow.recv(&mut [0; 1]).await, Err("SessionRevoked"));
        assert!(matches!(
            dispatcher
                .open_udp(
                    "192.0.2.2:10000".parse().unwrap(),
                    target("127.0.0.1:9".parse().unwrap())
                )
                .await,
            Err("CoreStopped")
        ));
    });
    assert_eq!(core.snapshot().unwrap()["active"], 0);
}

#[test]
fn udp_terminal_state_survives_unpolled_worker_drop_and_keeps_first_error() {
    let mut core = start(config());
    let dispatcher = core.flow_dispatcher().unwrap();
    let registered = dispatcher.shared.register().unwrap();
    let (mut completed, first) = UdpCompletion::new(dispatcher.shared.clone(), &registered);
    completed.finish(Err("UdpSend"));
    drop(registered);

    let registered = dispatcher.shared.register().unwrap();
    let (completion, revoked) = UdpCompletion::new(dispatcher.shared.clone(), &registered);
    // Deliberately never poll this worker. Runtime cancellation is permitted to
    // drop a captured future without executing any line inside its async body.
    let worker = async move {
        let _guards = (registered, completion);
        std::future::pending::<()>().await;
    };
    core.stop();
    drop(worker);
    drop(completed);
    assert_eq!(*revoked.borrow(), Some("SessionRevoked"));
    assert_eq!(*first.borrow(), Some("UdpSend"));
    let snapshot = core.snapshot().unwrap();
    assert_eq!(snapshot["active"], 0);
    assert_eq!(snapshot["failed"], 2);
}

struct PendingUdpChannels {
    flow: NativeUdpFlow,
    incoming: mpsc::Receiver<SendRequest>,
    replies: mpsc::Sender<Vec<u8>>,
    finished: watch::Sender<Option<&'static str>>,
}
fn pending_udp_channels() -> PendingUdpChannels {
    let (requests, incoming) = mpsc::channel(UDP_QUEUE);
    let (replies, responses) = mpsc::channel(UDP_QUEUE);
    let (finished, closed) = watch::channel(None);
    PendingUdpChannels {
        flow: NativeUdpFlow {
            requests,
            responses,
            closed,
            _task: AbortTask(tokio::spawn(std::future::pending())),
        },
        incoming,
        replies,
        finished,
    }
}

#[tokio::test]
async fn udp_response_eof_waits_for_the_terminal_reason() {
    let PendingUdpChannels {
        mut flow,
        replies,
        finished,
        ..
    } = pending_udp_channels();
    drop(replies);
    let mut bytes = [0; 1];
    let mut receive = Box::pin(flow.recv(&mut bytes));
    assert!(
        timeout(Duration::from_millis(10), &mut receive)
            .await
            .is_err()
    );
    finished.send(Some("SessionRevoked")).unwrap();
    assert_eq!(receive.await, Err("SessionRevoked"));
}

#[tokio::test]
async fn udp_request_eof_waits_for_the_terminal_reason() {
    let PendingUdpChannels {
        flow,
        incoming,
        finished,
        ..
    } = pending_udp_channels();
    drop(incoming);
    let mut send = Box::pin(flow.send(b"queued"));
    assert!(timeout(Duration::from_millis(10), &mut send).await.is_err());
    finished.send(Some("SessionRevoked")).unwrap();
    assert_eq!(send.await, Err("SessionRevoked"));
}

#[tokio::test]
async fn udp_send_completion_eof_waits_for_the_terminal_reason() {
    let PendingUdpChannels {
        flow,
        mut incoming,
        finished,
        ..
    } = pending_udp_channels();
    let mut send = Box::pin(flow.send(b"queued"));
    let request = tokio::select! {
        biased;
        result = &mut send => panic!("send completed before its worker: {result:?}"),
        request = incoming.recv() => request.unwrap(),
    };
    assert_eq!(request.payload, b"queued");
    drop(request);
    assert!(timeout(Duration::from_millis(10), &mut send).await.is_err());
    finished.send(Some("UdpSendTimeout")).unwrap();
    assert_eq!(send.await, Err("UdpSendTimeout"));
}

#[test]
fn native_dns_requires_encrypted_upstream_before_any_network_lookup() {
    let mut config = config();
    config.dns.tls_servers.clear();
    let mut core = start(config);
    assert!(matches!(
        core.prepare_native_tun(),
        Err("DnsEncryptedUpstreamRequired")
    ));
    let dispatcher = core.flow_dispatcher().unwrap();
    runtime().block_on(async {
        assert_eq!(
            dispatcher
                .resolve_dns(
                    "private.fixture.invalid",
                    443,
                    "192.0.2.2:10000".parse().unwrap()
                )
                .await,
            Err("DnsEncryptedUpstreamRequired")
        );
        let (_client, stream) = tokio::io::duplex(64);
        assert_eq!(
            dispatcher
                .relay_tcp(
                    stream,
                    "192.0.2.2:10000".parse().unwrap(),
                    target("127.0.0.1:9".parse().unwrap())
                )
                .await,
            Err("DnsEncryptedUpstreamRequired")
        );
    });
    core.stop();
}

#[test]
fn native_lease_blocks_dns_downgrade_in_prepare_and_preexisting_activation() {
    let mut core = start(config());
    let lease = core.prepare_native_tun().unwrap();
    let mut plain = config();
    plain.dns.tls_servers.clear();
    assert_eq!(
        core.prepare(REQUEST.into(), STORE, 1, 2, 1, 1, plain.clone(), vec![])
            .unwrap_err(),
        "DnsEncryptedUpstreamRequired"
    );
    drop(lease);
    let prepared = core
        .prepare(REQUEST.into(), STORE, 1, 2, 1, 1, plain, vec![])
        .unwrap();
    let lease = core.prepare_native_tun().unwrap();
    assert_eq!(
        core.activate(
            REQUEST,
            prepared["prepared_token"].as_str().unwrap(),
            prepared["plan_digest"].as_str().unwrap(),
            1,
            2
        )
        .unwrap_err(),
        "DnsEncryptedUpstreamRequired"
    );
    assert_eq!(core.configuration().unwrap()["generation"], "1");
    drop(lease);
    core.stop();
}

#[test]
fn native_proxy_rejection_preserves_original_error_without_dns_or_direct_retry() {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    listener.set_nonblocking(true).unwrap();
    let node_id = "c0000000-0000-4000-8000-000000000001";
    let mut candidate = config();
    candidate.policy.mode = Mode::Global;
    candidate.policy.default_policy.target = Target::Node { id: node_id.into() };
    candidate.nodes = vec![swirl_subscription::Node {
        id: node_id.into(),
        outbound: Outbound::HttpConnect {
            host: address.ip().to_string(),
            port: address.port(),
            auth: None,
            tls: None,
        },
    }];
    let mut core = start(candidate);
    let dispatcher = core.flow_dispatcher().unwrap();
    runtime().block_on(async {
        let server = tokio::spawn(async move {
            let listener = tokio::net::TcpListener::from_std(listener).unwrap();
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                request.push(stream.read_u8().await.unwrap());
            }
            assert!(request.starts_with(b"CONNECT unavailable.fixture.invalid:443 HTTP/1.1\r\n"));
            stream
                .write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                .await
                .unwrap();
        });
        let (_client, incoming) = tokio::io::duplex(64);
        let result = timeout(
            Duration::from_secs(3),
            dispatcher.relay_tcp(
                incoming,
                "192.0.2.2:12000".parse().unwrap(),
                NetworkTarget {
                    host: "unavailable.fixture.invalid".into(),
                    port: 443,
                },
            ),
        )
        .await
        .unwrap();
        assert_eq!(result, Err("UpstreamRejected"));
        server.await.unwrap();
    });
    let snapshot = core.snapshot().unwrap();
    assert_eq!(snapshot["connections"][0]["node"], node_id);
    assert_eq!(snapshot["connections"][0]["error"], "UpstreamRejected");
    assert_eq!(snapshot["connections"][0]["category"], "proxy");
    core.stop();
}

#[test]
fn native_ingress_rejects_ipv4_mapped_ipv6_proxy_loop() {
    let mut core = start(config());
    let dispatcher = core.flow_dispatcher().unwrap();
    runtime().block_on(async {
        let (_client, incoming) = tokio::io::duplex(64);
        assert_eq!(
            dispatcher
                .relay_tcp(
                    incoming,
                    "192.0.2.2:12000".parse().unwrap(),
                    NetworkTarget {
                        host: "::ffff:127.0.0.1".into(),
                        port: core.address().port(),
                    }
                )
                .await,
            Err("ProxyLoop")
        );
    });
    core.stop();
}

#[test]
fn native_start_waits_for_running_probe_socket_to_be_released() {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    listener.set_nonblocking(true).unwrap();
    let mut core = start(config());
    core.probe_start(format!("http://{address}/probe"), Some(3000), Some(204))
        .unwrap();
    let runtime = runtime();
    let accepted = runtime.block_on(async {
        let listener = tokio::net::TcpListener::from_std(listener).unwrap();
        timeout(Duration::from_secs(3), listener.accept())
            .await
            .unwrap()
            .unwrap()
            .0
    });
    assert!(matches!(
        core.prepare_native_tun(),
        Err("TunRequiresQuiescentCore")
    ));
    core.probe_cancel().unwrap();
    runtime.block_on(until(|| core.probe.quiescent()));
    let lease = core.prepare_native_tun().unwrap();
    drop(accepted);
    drop(lease);
    core.stop();
}

fn automatic_health_config(proxy: SocketAddr) -> RuntimeConfig {
    let mut candidate = config();
    candidate.nodes[0].outbound = Outbound::HttpConnect {
        host: proxy.ip().to_string(),
        port: proxy.port(),
        auth: None,
        tls: None,
    };
    let group = "d0000000-0000-4000-8000-000000000001";
    candidate.policy.mode = Mode::Global;
    candidate.policy.default_policy.target = Target::Group { id: group.into() };
    candidate.policy.groups.push(Group {
        id: group.into(),
        name: "Native lease health lifetime".into(),
        strategy: PolicyStrategy::Fallback,
        members: vec![Target::Node {
            id: candidate.nodes[0].id.clone(),
        }],
        selected: None,
        probe: Some(Probe {
            url: "http://health.fixture.invalid/check".into(),
            interval_ms: 300_000,
            timeout_ms: 10_000,
            expected_status: 204,
            tolerance_ms: 0,
            tls: None,
            success_threshold: 1,
            failure_threshold: 1,
            switch_cooldown_ms: 0,
        }),
    });
    candidate
}

fn blocked_automatic_health() -> (Core, tokio::runtime::Runtime, tokio::net::TcpStream) {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    listener.set_nonblocking(true).unwrap();
    let core = start(automatic_health_config(address));
    let runtime = runtime();
    let accepted = runtime.block_on(async {
        timeout(Duration::from_secs(3), async {
            let listener = tokio::net::TcpListener::from_std(listener).unwrap();
            let (mut stream, source) = listener.accept().await.unwrap();
            assert!(source.ip().is_loopback());
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                assert!(request.len() < 8192);
                request.push(stream.read_u8().await.unwrap());
            }
            assert_eq!(
                request,
                b"CONNECT health.fixture.invalid:80 HTTP/1.1\r\nHost: health.fixture.invalid:80\r\n\r\n"
            );
            stream
        })
        .await
        .unwrap()
    });
    // The automatic policy's real connection is held in proxy negotiation.
    // Neither ordinary admissions nor the manual probe runtime owns it.
    assert_eq!(core.snapshot().unwrap()["active"], 0);
    assert!(core.probe.quiescent());
    assert!(matches!(
        core.prepare_native_tun(),
        Err("TunRequiresQuiescentCore")
    ));
    (core, runtime, accepted)
}

async fn wait_for_first_native_lease(core: &Core) -> NativeTunLease {
    timeout(Duration::from_secs(3), async {
        loop {
            match core.prepare_native_tun() {
                Ok(lease) => break lease,
                Err("TunRequiresQuiescentCore") => tokio::task::yield_now().await,
                Err(error) => panic!("unexpected lease result: {error}"),
            }
        }
    })
    .await
    .unwrap()
}

#[test]
fn native_start_waits_for_automatic_policy_health_socket_to_be_released() {
    let (mut core, runtime, mut accepted) = blocked_automatic_health();
    runtime.block_on(async {
        accepted
            .write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            .await
            .unwrap();
        drop(wait_for_first_native_lease(&core).await);
    });
    drop(accepted);
    core.stop();
}

#[test]
fn successful_automatic_health_releases_native_admission_after_response() {
    let (mut core, runtime, mut accepted) = blocked_automatic_health();
    runtime.block_on(async {
        accepted
            .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            .await
            .unwrap();
        let request = timeout(Duration::from_secs(3), async {
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                assert!(request.len() < 8192);
                request.push(accepted.read_u8().await.unwrap());
            }
            request
        })
        .await
        .unwrap();
        assert!(request.starts_with(b"GET /check HTTP/1.1\r\n"));
        assert!(matches!(
            core.prepare_native_tun(),
            Err("TunRequiresQuiescentCore")
        ));
        accepted
            .write_all(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n")
            .await
            .unwrap();
        drop(wait_for_first_native_lease(&core).await);
    });
    drop(accepted);
    core.stop();
}

#[test]
fn cancelled_automatic_health_releases_native_admission_after_task_drop() {
    let (mut core, runtime, accepted) = blocked_automatic_health();
    let policies = core.shared.live.lock().unwrap().plan.policies.clone();
    // Exercise the existing task-abort path. stop() returning alone does not
    // prove that the JoinSet's socket-owning futures have been dropped yet.
    policies.stop();
    drop(runtime.block_on(wait_for_first_native_lease(&core)));
    assert!(policies.quiescent());
    drop(accepted);
    core.stop();
}

#[test]
fn retained_tun_lease_allows_bridge_rebuild_without_reopening_dns_downgrade() {
    let mut core = start(config());
    let retained = core.prepare_native_tun().unwrap();
    let dispatcher = core.flow_dispatcher().unwrap();
    let runtime = runtime();
    let flow = runtime.block_on(async {
        let peer = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        dispatcher
            .open_udp(
                "192.0.2.2:12000".parse().unwrap(),
                target(peer.local_addr().unwrap()),
            )
            .await
            .unwrap()
    });
    assert_eq!(core.snapshot().unwrap()["active"], 1);
    let bridge_lease = core.prepare_native_tun().unwrap();
    drop(retained);
    let mut plaintext = config();
    plaintext.dns.tls_servers.clear();
    assert_eq!(
        core.prepare(REQUEST.into(), STORE, 1, 2, 1, 1, plaintext, vec![])
            .unwrap_err(),
        "DnsEncryptedUpstreamRequired"
    );
    assert_eq!(
        core.snapshot().unwrap()["active"],
        1,
        "lease changes must not revoke unrelated live sessions"
    );
    drop(bridge_lease);
    assert!(matches!(
        core.prepare_native_tun(),
        Err("TunRequiresQuiescentCore")
    ));
    drop(flow);
    runtime.block_on(until(|| core.snapshot().unwrap()["active"] == 0));
    let fresh = core.prepare_native_tun().unwrap();
    drop(fresh);
    core.stop();
}

#[test]
fn gateway_lan_flows_exchange_real_bytes_and_record_source_without_another_runtime() {
    let mut core = start(config());
    let source: SocketAddr = "192.168.77.12:50123".parse().unwrap();
    runtime().block_on(async {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let tcp_address = listener.local_addr().unwrap();
        let udp = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let udp_address = udp.local_addr().unwrap();
        let mut dispatcher = gateway(&core.flow_dispatcher().unwrap());
        // A private cfg(test) exception permits only these two ephemeral echo
        // endpoints. The production gateway rejects all loopback host services.
        Arc::get_mut(dispatcher.gateway.as_mut().unwrap())
            .unwrap()
            .fixture_endpoints
            .extend([tcp_address, udp_address]);
        let tcp_peer = tokio::spawn(async move {
            let (mut peer, _) = listener.accept().await.unwrap();
            let mut bytes = [0; 11];
            peer.read_exact(&mut bytes).await.unwrap();
            assert_eq!(&bytes, b"gateway-tcp");
            peer.write_all(b"tcp-reply").await.unwrap();
            peer.shutdown().await.unwrap();
        });
        let udp_peer = tokio::spawn(async move {
            let mut bytes = [0; 64];
            let (length, peer) = udp.recv_from(&mut bytes).await.unwrap();
            assert_eq!(&bytes[..length], b"gateway-udp");
            udp.send_to(&bytes[..length], peer).await.unwrap();
        });
        let (mut client, inbound) = tokio::io::duplex(128);
        let tcp_flow = tokio::spawn({
            let dispatcher = dispatcher.clone();
            async move {
                dispatcher
                    .relay_tcp(inbound, source, target(tcp_address))
                    .await
            }
        });
        client.write_all(b"gateway-tcp").await.unwrap();
        client.shutdown().await.unwrap();
        let mut response = Vec::new();
        timeout(Duration::from_secs(3), client.read_to_end(&mut response))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(response, b"tcp-reply");
        tcp_flow.await.unwrap().unwrap();
        tcp_peer.await.unwrap();
        let mut flow = dispatcher
            .open_udp(source, target(udp_address))
            .await
            .unwrap();
        flow.send(b"gateway-udp").await.unwrap();
        let mut bytes = [0; 64];
        let length = timeout(Duration::from_secs(3), flow.recv(&mut bytes))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(&bytes[..length], b"gateway-udp");
        drop(flow);
        udp_peer.await.unwrap();
        until(|| core.snapshot().unwrap()["active"] == 0).await;
    });
    let snapshot = core.snapshot().unwrap();
    assert_eq!(snapshot["upload"], 22);
    assert_eq!(snapshot["download"], 20);
    let records = snapshot["connections"].as_array().unwrap();
    assert_eq!(records.len(), 2);
    assert!(records.iter().all(|record| record["ingress"] == "gateway"
        && record["source_ip"] == "192.168.77.12"
        && record["ended"] == true));
    core.stop();
}

#[test]
fn gateway_upstream_host_inventory_blocks_proxy_hop_rebinding_before_handshake() {
    let mut candidate = config();
    candidate.policy.mode = Mode::Global;
    candidate.dns.hosts.push(swirl_subscription::HostMapping {
        name: "upstream.fixture.invalid".into(),
        address: "127.0.0.1".parse().unwrap(),
    });
    if let Outbound::HttpConnect { host, .. } = &mut candidate.nodes[0].outbound {
        *host = "upstream.fixture.invalid".into();
    }
    let mut core = start(candidate);
    let dispatcher = gateway(&core.flow_dispatcher().unwrap());
    runtime().block_on(async {
        let (_client, stream) = tokio::io::duplex(128);
        assert_eq!(
            dispatcher
                .relay_tcp(
                    stream,
                    "192.168.77.12:50000".parse().unwrap(),
                    NetworkTarget {
                        host: "remote.fixture.invalid".into(),
                        port: 443
                    }
                )
                .await,
            Err("GatewayHostAccessDenied")
        );
        until(|| core.snapshot().unwrap()["active"] == 0).await;
    });
    assert_eq!(core.snapshot().unwrap()["upload"], 0);
    core.stop();
}
