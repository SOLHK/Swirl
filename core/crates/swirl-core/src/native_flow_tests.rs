use super::*;
use crate::v2::{Core, RuntimeConfig};
use std::collections::BTreeMap;
use swirl_subscription::{
    Dns, DnsTlsServer, Limits, Tls,
    v2::{ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, Mode, PolicyDocument, Target},
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
