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
