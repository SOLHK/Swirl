//! Receipts are checked against bytes delivered through independent A/B peers.
use super::*;
use std::{
    io::{Read, Write},
    net::{TcpListener as StdListener, TcpStream as StdStream},
    thread,
};
use swirl_subscription::v2::{DEFAULT_POLICY_ID, DefaultPolicy, Group, Probe};
const STORE: &str = "40000000-0000-4000-8000-000000000001";
const START: &str = "50000000-0000-4000-8000-000000000001";
const REQUEST: &str = "50000000-0000-4000-8000-000000000002";
const REQUEST3: &str = "50000000-0000-4000-8000-000000000003";
const A: &str = "10000000-0000-4000-8000-000000000001";
const B: &str = "10000000-0000-4000-8000-000000000002";
const GROUP: &str = "20000000-0000-4000-8000-000000000001";
struct Peer {
    address: SocketAddr,
    connections: Arc<AtomicUsize>,
    requests: Arc<AtomicUsize>,
    stop: Arc<AtomicBool>,
    task: Option<thread::JoinHandle<()>>,
}
fn header(stream: &mut StdStream) -> std::io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    while !bytes.ends_with(b"\r\n\r\n") {
        if bytes.len() >= 8192 {
            return Err(std::io::ErrorKind::InvalidData.into());
        }
        let mut byte = [0];
        stream.read_exact(&mut byte)?;
        bytes.push(byte[0]);
    }
    Ok(bytes)
}
impl Peer {
    fn new(marker: u8) -> Self {
        let listener = StdListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let connections = Arc::new(AtomicUsize::new(0));
        let requests = Arc::new(AtomicUsize::new(0));
        let stop = Arc::new(AtomicBool::new(false));
        let task = thread::spawn({
            let connections = connections.clone();
            let requests = requests.clone();
            let stop = stop.clone();
            move || {
                let mut workers = Vec::new();
                for accepted in listener.incoming() {
                    let Ok(mut stream) = accepted else { break };
                    if stop.load(Ordering::Acquire) {
                        break;
                    }
                    connections.fetch_add(1, Ordering::AcqRel);
                    let requests = requests.clone();
                    workers.push(thread::spawn(move || {
                        stream
                            .set_read_timeout(Some(Duration::from_secs(4)))
                            .unwrap();
                        stream
                            .set_write_timeout(Some(Duration::from_secs(4)))
                            .unwrap();
                        let Ok(request) = header(&mut stream) else {
                            return;
                        };
                        if !request.starts_with(b"CONNECT ") {
                            return;
                        }
                        if stream
                            .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                            .is_err()
                        {
                            return;
                        }
                        loop {
                            let mut bytes = [0u8; 4];
                            if stream.read_exact(&mut bytes).is_err() {
                                return;
                            }
                            requests.fetch_add(1, Ordering::AcqRel);
                            let mut response = vec![marker, b':'];
                            response.extend(bytes);
                            if stream.write_all(&response).is_err() {
                                return;
                            }
                        }
                    }));
                }
                for worker in workers {
                    let _ = worker.join();
                }
            }
        });
        Self {
            address,
            connections,
            requests,
            stop,
            task: Some(task),
        }
    }
}
impl Drop for Peer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        let _ = StdStream::connect(self.address);
        if let Some(task) = self.task.take() {
            let _ = task.join();
        }
    }
}
fn node(id: &str, peer: &Peer) -> Node {
    Node {
        id: id.into(),
        outbound: Outbound::HttpConnect {
            host: peer.address.ip().to_string(),
            port: peer.address.port(),
            auth: None,
            tls: None,
        },
    }
}
fn config(a: &Peer, b: &Peer, selected: &str, include_a: bool) -> RuntimeConfig {
    RuntimeConfig {
        schema: 2,
        listen: "127.0.0.1:0".parse().unwrap(),
        nodes: if include_a {
            vec![node(A, a), node(B, b)]
        } else {
            vec![node(B, b)]
        },
        policy: PolicyDocument {
            schema: 2,
            mode: Mode::Global,
            default_policy: DefaultPolicy {
                id: DEFAULT_POLICY_ID.into(),
                target: Target::Node {
                    id: selected.into(),
                },
            },
            service_policies: vec![],
            groups: vec![],
            explicit_direct_rules: vec![],
            custom_rules: vec![],
            missing_targets: vec![],
            classification_dns: ClassificationDns::Disabled,
        },
        dns: Dns::default(),
        inbound_auth: None,
        limits: Limits::default(),
        china_rules_directory: None,
        node_sources: BTreeMap::new(),
        transports: BTreeMap::new(),
    }
}
fn connect(address: SocketAddr) -> StdStream {
    let mut client = StdStream::connect(address).unwrap();
    client
        .set_read_timeout(Some(Duration::from_secs(4)))
        .unwrap();
    client
        .set_write_timeout(Some(Duration::from_secs(4)))
        .unwrap();
    client.write_all(b"CONNECT target.fixture.invalid:80 HTTP/1.1\r\nHost: target.fixture.invalid:80\r\n\r\n").unwrap();
    assert!(header(&mut client).unwrap().starts_with(b"HTTP/1.1 200"));
    client
}
fn exchange(client: &mut StdStream, bytes: &[u8; 4]) -> Vec<u8> {
    client.write_all(bytes).unwrap();
    let mut response = vec![0; 6];
    client.read_exact(&mut response).unwrap();
    response
}
fn wait(mut predicate: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(3);
    while !predicate() {
        assert!(Instant::now() < deadline, "condition deadline");
        thread::yield_now();
    }
}
fn prepared(
    core: &Core,
    candidate: RuntimeConfig,
    request: &str,
    base: u64,
    next: u64,
    generation: u64,
    revoked: Vec<String>,
) -> Value {
    core.prepare(
        request.into(),
        STORE,
        base,
        next,
        generation,
        base,
        candidate,
        revoked,
    )
    .unwrap()
}
fn activated(
    core: &Core,
    prepared: &Value,
    request: &str,
    generation: u64,
    revision: u64,
) -> Value {
    core.activate(
        request,
        prepared["prepared_token"].as_str().unwrap(),
        prepared["plan_digest"].as_str().unwrap(),
        generation,
        revision,
    )
    .unwrap()
}
fn finished(core: &Core, prepared: &Value, request: &str, revision: u64) -> Value {
    core.finish(
        request,
        prepared["prepared_token"].as_str().unwrap(),
        DurableReceipt {
            store_id: STORE.into(),
            request_id: request.into(),
            saved_revision: revision.to_string(),
            plan_digest: prepared["plan_digest"].as_str().unwrap().into(),
        },
    )
    .unwrap()
}
#[test]
fn candidate_gate_delivers_no_new_bytes_until_matching_durable_receipt() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let mut core = Core::start(config(&a, &b, A, true), STORE.into(), 1, START.into()).unwrap();
    let address = core.address();
    let plan = prepared(&core, config(&a, &b, B, false), REQUEST, 1, 2, 1, vec![]);
    activated(&core, &plan, REQUEST, 1, 2);
    let client = thread::spawn(move || {
        let mut stream = connect(address);
        exchange(&mut stream, b"ping")
    });
    wait(|| core.shared.waiting.load(Ordering::Acquire) == 1);
    assert_eq!(
        (
            a.requests.load(Ordering::Acquire),
            b.requests.load(Ordering::Acquire)
        ),
        (0, 0)
    );
    assert_eq!(
        core.configuration().unwrap()["transaction_state"],
        "committing"
    );
    assert_eq!(finished(&core, &plan, REQUEST, 2)["outcome"], "applied");
    assert_eq!(client.join().unwrap(), b"B:ping");
    assert_eq!(
        (
            a.requests.load(Ordering::Acquire),
            b.requests.load(Ordering::Acquire)
        ),
        (0, 1)
    );
    core.stop();
    assert!(StdListener::bind(address).is_ok());
}
#[test]
fn rollback_keeps_gate_closed_until_old_disk_receipt_is_reconciled() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let mut core = Core::start(config(&a, &b, A, true), STORE.into(), 1, START.into()).unwrap();
    let old_digest = core.configuration().unwrap()["plan_digest"]
        .as_str()
        .unwrap()
        .to_owned();
    let address = core.address();
    let plan = prepared(&core, config(&a, &b, B, false), REQUEST, 1, 2, 1, vec![]);
    activated(&core, &plan, REQUEST, 1, 2);
    let client = thread::spawn(move || {
        let mut stream = connect(address);
        exchange(&mut stream, b"ping")
    });
    wait(|| core.shared.waiting.load(Ordering::Acquire) == 1);
    let response = core
        .rollback(
            REQUEST,
            plan["prepared_token"].as_str().unwrap(),
            2,
            1,
            &old_digest,
        )
        .unwrap();
    assert_eq!(
        (
            response["generation"].clone(),
            response["applied_revision"].clone()
        ),
        (json!("3"), json!("1"))
    );
    assert!(core.shared.live.lock().unwrap().closed);
    assert_eq!(
        (
            a.requests.load(Ordering::Acquire),
            b.requests.load(Ordering::Acquire)
        ),
        (0, 0)
    );
    let response = core
        .finish(
            REQUEST,
            plan["prepared_token"].as_str().unwrap(),
            DurableReceipt {
                store_id: STORE.into(),
                request_id: START.into(),
                saved_revision: "1".into(),
                plan_digest: old_digest,
            },
        )
        .unwrap();
    assert_eq!(response["outcome"], "rolled_back");
    assert_eq!(client.join().unwrap(), b"A:ping");
    assert_eq!(b.requests.load(Ordering::Acquire), 0);
    core.stop();
}
#[test]
fn ordinary_closure_change_preserves_old_tunnel_but_explicit_catalogue_revoke_closes_it() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let mut core = Core::start(config(&a, &b, A, true), STORE.into(), 1, START.into()).unwrap();
    let mut old = connect(core.address());
    assert_eq!(exchange(&mut old, b"ping"), b"A:ping");
    let old_config = Arc::downgrade(&core.shared.live.lock().unwrap().plan.prepared.runtime);
    let plan = prepared(&core, config(&a, &b, B, false), REQUEST, 1, 2, 1, vec![]);
    activated(&core, &plan, REQUEST, 1, 2);
    finished(&core, &plan, REQUEST, 2);
    assert!(
        old_config.upgrade().is_none(),
        "established tunnel must release unselected configuration credentials"
    );
    assert_eq!(exchange(&mut old, b"stay"), b"A:stay");
    let mut unaffected = connect(core.address());
    assert_eq!(exchange(&mut unaffected, b"ping"), b"B:ping");
    let revoke = prepared(
        &core,
        config(&a, &b, B, false),
        REQUEST3,
        2,
        3,
        2,
        vec![A.into()],
    );
    activated(&core, &revoke, REQUEST3, 2, 3);
    finished(&core, &revoke, REQUEST3, 3);
    let mut byte = [0];
    match old.read(&mut byte) {
        Ok(0) => {}
        Err(error)
            if matches!(
                error.kind(),
                std::io::ErrorKind::ConnectionReset | std::io::ErrorKind::ConnectionAborted
            ) => {}
        result => panic!("revoked tunnel remained usable: {result:?}"),
    };
    assert_eq!(exchange(&mut unaffected, b"stay"), b"B:stay");
    drop(old);
    drop(unaffected);
    core.stop();
}
#[test]
fn preparation_and_activation_cannot_start_candidate_health_probes() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let mut core = Core::start(config(&a, &b, A, true), STORE.into(), 1, START.into()).unwrap();
    let mut candidate = config(&a, &b, B, false);
    candidate.policy.default_policy.target = Target::Group { id: GROUP.into() };
    candidate.policy.groups.push(Group {
        id: GROUP.into(),
        name: "Health fence".into(),
        strategy: swirl_subscription::PolicyStrategy::Fallback,
        members: vec![Target::Node { id: B.into() }],
        selected: None,
        probe: Some(Probe {
            url: "http://health.fixture.invalid/check".into(),
            interval_ms: 1000,
            timeout_ms: 100,
            expected_status: 204,
            tolerance_ms: 0,
            tls: None,
            success_threshold: 1,
            failure_threshold: 1,
            switch_cooldown_ms: 0,
        }),
    });
    let plan = prepared(&core, candidate, REQUEST, 1, 2, 1, vec![]);
    assert_eq!(b.connections.load(Ordering::Acquire), 0);
    activated(&core, &plan, REQUEST, 1, 2);
    assert_eq!(b.connections.load(Ordering::Acquire), 0);
    finished(&core, &plan, REQUEST, 2);
    wait(|| b.connections.load(Ordering::Acquire) > 0);
    core.stop();
}
#[test]
fn cancelled_admission_waiters_release_capacity_and_limit_is_exact() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let mut core = Core::start(config(&a, &b, A, true), STORE.into(), 1, START.into()).unwrap();
    let plan = prepared(&core, config(&a, &b, B, false), REQUEST, 1, 2, 1, vec![]);
    activated(&core, &plan, REQUEST, 1, 2);
    let shared = core.shared.clone();
    core.runtime.as_ref().unwrap().block_on(async {
        let mut tasks = JoinSet::new();
        for _ in 0..64 {
            let shared = shared.clone();
            tasks.spawn(async move { shared.admit().await.map(|_| ()) });
        }
        timeout(Duration::from_secs(1), async {
            while shared.waiting.load(Ordering::Acquire) != 64 {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        assert_eq!(shared.admit().await.err(), Some("AdmissionBusy"));
        tasks.abort_all();
        while tasks.join_next().await.is_some() {}
        assert_eq!(shared.waiting.load(Ordering::Acquire), 0);
    });
    core.stop();
}
#[test]
fn expired_prepared_plan_is_released_without_traffic_or_revision_reuse() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let mut core = Core::start(config(&a, &b, A, true), STORE.into(), 1, START.into()).unwrap();
    prepared(&core, config(&a, &b, B, false), REQUEST, 1, 2, 1, vec![]);
    let weak = {
        let mut transactions = core.transactions.lock().unwrap();
        let pending = transactions.pending.as_mut().unwrap();
        pending.created = Instant::now() - Duration::from_secs(61);
        Arc::downgrade(&pending.candidate.prepared.runtime)
    };
    core.expiry_notify.notify_one();
    wait(|| core.transactions.lock().unwrap().pending.is_none());
    assert!(weak.upgrade().is_none());
    assert_eq!(core.status(REQUEST).unwrap()["code"], "PreparedExpired");
    assert_eq!(
        core.prepare(
            REQUEST3.into(),
            STORE,
            1,
            2,
            1,
            1,
            config(&a, &b, B, false),
            vec![]
        )
        .unwrap_err(),
        "RevisionConflict"
    );
    assert_eq!(core.configuration().unwrap()["applied_revision"], "1");
    assert_eq!(b.connections.load(Ordering::Acquire), 0);
    core.stop();
}
#[test]
fn idempotent_finish_and_prepare_reject_changed_token_receipt_or_revocation_set() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let mut core = Core::start(config(&a, &b, A, true), STORE.into(), 1, START.into()).unwrap();
    let plan = prepared(&core, config(&a, &b, B, false), REQUEST, 1, 2, 1, vec![]);
    assert_eq!(
        core.prepare(
            REQUEST.into(),
            STORE,
            1,
            2,
            1,
            1,
            config(&a, &b, B, false),
            vec![A.into()]
        )
        .unwrap_err(),
        "RequestIdentityMismatch"
    );
    activated(&core, &plan, REQUEST, 1, 2);
    let result = finished(&core, &plan, REQUEST, 2);
    let receipt = DurableReceipt {
        store_id: STORE.into(),
        request_id: REQUEST.into(),
        saved_revision: "2".into(),
        plan_digest: plan["plan_digest"].as_str().unwrap().into(),
    };
    assert_eq!(
        core.finish(REQUEST, "wrong-token", receipt.clone())
            .unwrap_err(),
        "RequestIdentityMismatch"
    );
    assert_eq!(
        core.finish(REQUEST, plan["prepared_token"].as_str().unwrap(), receipt)
            .unwrap(),
        result
    );
    core.stop();
}
#[test]
fn generation_overflow_fails_before_closing_gate_or_changing_plan() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let mut core = Core::start(config(&a, &b, A, true), STORE.into(), 1, START.into()).unwrap();
    core.shared.live.lock().unwrap().generation = u64::MAX;
    let plan = prepared(
        &core,
        config(&a, &b, B, false),
        REQUEST,
        1,
        2,
        u64::MAX,
        vec![],
    );
    assert_eq!(
        core.activate(
            REQUEST,
            plan["prepared_token"].as_str().unwrap(),
            plan["plan_digest"].as_str().unwrap(),
            u64::MAX,
            2
        )
        .unwrap_err(),
        "GenerationLimit"
    );
    assert!(!core.shared.live.lock().unwrap().closed);
    assert_eq!(core.configuration().unwrap()["applied_revision"], "1");
    core.stop();
}

#[test]
fn ordinary_http_preserves_framed_bodies_and_cannot_pipeline_a_second_request() {
    for (method, framing, body, response) in [
        (
            "POST",
            "Content-Length: 27\r\n",
            "body\r\nUpgrade: websocket\r\n!",
            "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: keep-alive\r\n\r\nOK",
        ),
        (
            "POST",
            "Transfer-Encoding: chunked\r\n",
            "4;fixture=yes\r\nbody\r\n0\r\nX-Fixture: tail\r\n\r\n",
            "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nOK\r\n0\r\n\r\n",
        ),
        (
            "HEAD",
            "",
            "",
            "HTTP/1.1 200 OK\r\nContent-Length: 999\r\nConnection: keep-alive\r\n\r\n",
        ),
    ] {
        let listener = StdListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let origin = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(4)))
                .unwrap();
            assert!(
                header(&mut stream)
                    .unwrap()
                    .starts_with(b"CONNECT target.fixture.invalid:80 ")
            );
            stream
                .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                .unwrap();
            let first = header(&mut stream).unwrap();
            let mut actual_body = vec![0; body.len()];
            stream.read_exact(&mut actual_body).unwrap();
            assert_eq!(actual_body, body.as_bytes());
            assert!(
                first
                    .windows(b"Connection: close".len())
                    .any(|part| part == b"Connection: close")
            );
            stream.write_all(response.as_bytes()).unwrap();
            // The origin deliberately ignores Connection: close. Swirl must
            // finish at the response frame rather than wait for origin EOF.
            let mut extra = Vec::new();
            stream.read_to_end(&mut extra).unwrap();
            assert!(
                extra.is_empty(),
                "a second logical request escaped the first snapshot"
            );
        });
        let a = Peer::new(b'A');
        let b = Peer::new(b'B');
        let mut candidate = config(&a, &b, A, true);
        candidate.nodes[0].outbound = Outbound::HttpConnect {
            host: address.ip().to_string(),
            port: address.port(),
            auth: None,
            tls: None,
        };
        let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
        let mut client = StdStream::connect(core.address()).unwrap();
        client
            .set_read_timeout(Some(Duration::from_secs(4)))
            .unwrap();
        let first = format!(
            "{method} http://target.fixture.invalid/first HTTP/1.1\r\nHost: target.fixture.invalid\r\n{framing}Connection: keep-alive\r\n\r\n{body}"
        );
        let second = "GET http://target.fixture.invalid/forbidden HTTP/1.1\r\nHost: target.fixture.invalid\r\n\r\n";
        client
            .write_all(format!("{first}{second}").as_bytes())
            .unwrap();
        let mut reply = Vec::new();
        client.read_to_end(&mut reply).unwrap();
        assert!(reply.starts_with(b"HTTP/1.1 200"));
        assert!(
            reply
                .windows(b"Connection: close".len())
                .any(|part| part == b"Connection: close")
        );
        if method != "HEAD" {
            assert!(reply.windows(2).any(|part| part == b"OK"));
        }
        origin.join().unwrap();
        core.stop();
    }
}

struct DatagramPeer {
    address: SocketAddr,
    packets: Arc<AtomicUsize>,
    stop: Arc<AtomicBool>,
    task: Option<thread::JoinHandle<()>>,
}
#[test]
fn websocket_requires_actual_authenticated_upgrade_before_opaque_tunnel() {
    for upgraded in [false, true] {
        let listener = StdListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let origin = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            assert!(header(&mut socket).unwrap().starts_with(b"CONNECT "));
            socket
                .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                .unwrap();
            let request = header(&mut socket).unwrap();
            assert!(request.starts_with(b"GET /upgrade HTTP/1.1"));
            if upgraded {
                socket.write_all(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n").unwrap();
                let mut frame = [0; 8];
                socket.read_exact(&mut frame).unwrap();
                assert_eq!(&frame, b"\x82\x82MASKok");
                socket.write_all(b"\x82\x02OK").unwrap();
            } else {
                socket
                    .write_all(
                        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: keep-alive\r\n\r\nOK",
                    )
                    .unwrap();
                let mut extra = Vec::new();
                socket.read_to_end(&mut extra).unwrap();
                assert!(
                    extra.is_empty(),
                    "declined upgrade forwarded a later ordinary request"
                );
            }
        });
        let a = Peer::new(b'A');
        let b = Peer::new(b'B');
        let mut candidate = config(&a, &b, A, true);
        candidate.nodes[0].outbound = Outbound::HttpConnect {
            host: address.ip().to_string(),
            port: address.port(),
            auth: None,
            tls: None,
        };
        let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
        let mut client = StdStream::connect(core.address()).unwrap();
        client
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        let request=b"GET http://target.fixture.invalid/upgrade HTTP/1.1\r\nHost: target.fixture.invalid\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n";
        let tail = if upgraded {
            b"\x82\x82MASKok".as_slice()
        } else {
            b"GET /second HTTP/1.1\r\nHost: target.fixture.invalid\r\n\r\n".as_slice()
        };
        client
            .write_all(&[request.as_slice(), tail].concat())
            .unwrap();
        let mut reply = Vec::new();
        client.read_to_end(&mut reply).unwrap();
        if upgraded {
            assert!(reply.starts_with(b"HTTP/1.1 101"));
            assert!(reply.ends_with(b"\x82\x02OK"));
        } else {
            assert!(reply.starts_with(b"HTTP/1.1 200"));
            assert!(reply.ends_with(b"OK"));
        }
        origin.join().unwrap();
        core.stop();
    }
}
// Separate endpoint cipher, deliberately independent of the production
// process-wide replay window. Reusing its encrypt/decrypt helpers in a local
// peer would correctly reject its own process's just-issued salt as a replay.
fn datagram_peer_key(salt: &[u8]) -> ring::aead::LessSafeKey {
    use ring::{aead, hkdf};
    struct Size;
    impl hkdf::KeyType for Size {
        fn len(&self) -> usize {
            32
        }
    }
    let master = [
        0x88, 0xb9, 0xdd, 0x75, 0x12, 0xbb, 0x85, 0xac, 0x9d, 0x13, 0x99, 0x4c, 0x69, 0xd1, 0x58,
        0xc1, 0x4f, 0xf1, 0xfc, 0x74, 0xe3, 0xf1, 0x01, 0x78, 0x3a, 0x06, 0xef, 0x57, 0xf9, 0x12,
        0x76, 0x06,
    ];
    let extracted = hkdf::Salt::new(hkdf::HKDF_SHA1_FOR_LEGACY_USE_ONLY, salt).extract(&master);
    let mut key = [0; 32];
    extracted
        .expand(&[b"ss-subkey"], Size)
        .unwrap()
        .fill(&mut key)
        .unwrap();
    aead::LessSafeKey::new(aead::UnboundKey::new(&aead::AES_256_GCM, &key).unwrap())
}
impl DatagramPeer {
    fn new(marker: u8) -> Self {
        let socket = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
        let address = socket.local_addr().unwrap();
        let packets = Arc::new(AtomicUsize::new(0));
        let stop = Arc::new(AtomicBool::new(false));
        let task = thread::spawn({
            let packets = packets.clone();
            let stop = stop.clone();
            move || {
                let mut wire = [0; 65535];
                loop {
                    let (size, client) = socket.recv_from(&mut wire).unwrap();
                    if stop.load(Ordering::Acquire) {
                        return;
                    }
                    let mut plain = wire[32..size].to_vec();
                    let decoded = datagram_peer_key(&wire[..32])
                        .open_in_place(
                            ring::aead::Nonce::assume_unique_for_key([0; 12]),
                            ring::aead::Aad::empty(),
                            &mut plain,
                        )
                        .unwrap()
                        .len();
                    plain.truncate(decoded);
                    assert_eq!(plain[0], 3, "fixture expects remote domain routing");
                    let boundary = 2 + usize::from(plain[1]) + 2;
                    let mut response = plain[..boundary].to_vec();
                    response.push(marker);
                    response.push(b':');
                    response.extend_from_slice(&plain[boundary..]);
                    packets.fetch_add(1, Ordering::AcqRel);
                    use ring::rand::SecureRandom;
                    let mut salt = [0; 32];
                    ring::rand::SystemRandom::new().fill(&mut salt).unwrap();
                    datagram_peer_key(&salt)
                        .seal_in_place_append_tag(
                            ring::aead::Nonce::assume_unique_for_key([0; 12]),
                            ring::aead::Aad::empty(),
                            &mut response,
                        )
                        .unwrap();
                    let mut encrypted = salt.to_vec();
                    encrypted.extend(response);
                    socket.send_to(&encrypted, client).unwrap();
                }
            }
        });
        Self {
            address,
            packets,
            stop,
            task: Some(task),
        }
    }
    fn node(&self, id: &str) -> Node {
        Node {
            id: id.into(),
            outbound: Outbound::Shadowsocks {
                host: self.address.ip().to_string(),
                port: self.address.port(),
                password: "synthetic-udp-password".into(),
                cipher: "aes-256-gcm".into(),
                udp: true,
                obfs_http: None,
            },
        }
    }
}
impl Drop for DatagramPeer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        let wake = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
        let _ = wake.send_to(&[], self.address);
        if let Some(task) = self.task.take() {
            let joined = task.join();
            if !thread::panicking() {
                joined.unwrap();
            }
        }
    }
}
fn udp_association(address: SocketAddr) -> (StdStream, std::net::UdpSocket, SocketAddr) {
    let mut control = StdStream::connect(address).unwrap();
    control
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    control.write_all(&[5, 1, 0]).unwrap();
    let mut greeting = [0; 2];
    control.read_exact(&mut greeting).unwrap();
    assert_eq!(greeting, [5, 0]);
    control.write_all(&[5, 3, 0, 1, 0, 0, 0, 0, 0, 0]).unwrap();
    let mut reply = [0; 10];
    control.read_exact(&mut reply).unwrap();
    assert_eq!(&reply[..4], &[5, 0, 0, 1]);
    let relay = SocketAddr::from((
        [reply[4], reply[5], reply[6], reply[7]],
        u16::from_be_bytes([reply[8], reply[9]]),
    ));
    let datagrams = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
    datagrams
        .set_read_timeout(Some(Duration::from_secs(3)))
        .unwrap();
    (control, datagrams, relay)
}
fn udp_send(socket: &std::net::UdpSocket, relay: SocketAddr, destination: &str, payload: &[u8]) {
    let mut wire = vec![0, 0, 0, 3, destination.len() as u8];
    wire.extend(destination.as_bytes());
    wire.extend(80u16.to_be_bytes());
    wire.extend(payload);
    socket.send_to(&wire, relay).unwrap();
}
fn udp_receive(socket: &std::net::UdpSocket) -> Vec<u8> {
    let mut wire = [0; 1024];
    let (size, _) = socket.recv_from(&mut wire).unwrap();
    assert_eq!(&wire[..4], &[0, 0, 0, 3]);
    let boundary = 5 + usize::from(wire[4]) + 2;
    wire[boundary..size].to_vec()
}
#[test]
fn udp_new_destination_waits_for_receipt_old_destination_stays_pinned_and_catalogue_revoke_closes_flow()
 {
    let a = DatagramPeer::new(b'A');
    let b = DatagramPeer::new(b'B');
    let dummy_a = Peer::new(b'A');
    let dummy_b = Peer::new(b'B');
    let mut initial = config(&dummy_a, &dummy_b, A, true);
    initial.nodes = vec![a.node(A), b.node(B)];
    let mut candidate = initial.clone();
    candidate.nodes = vec![b.node(B)];
    candidate.policy.default_policy.target = Target::Node { id: B.into() };
    let mut core = Core::start(initial, STORE.into(), 1, START.into()).unwrap();
    let (mut control, socket, relay) = udp_association(core.address());
    udp_send(&socket, relay, "first.fixture.invalid", b"old1");
    assert_eq!(udp_receive(&socket), b"A:old1");
    let plan = prepared(&core, candidate.clone(), REQUEST, 1, 2, 1, vec![]);
    activated(&core, &plan, REQUEST, 1, 2);
    udp_send(&socket, relay, "second.fixture.invalid", b"new2");
    wait(|| core.shared.waiting.load(Ordering::Acquire) == 1);
    assert_eq!(b.packets.load(Ordering::Acquire), 0);
    udp_send(&socket, relay, "first.fixture.invalid", b"old2");
    assert_eq!(udp_receive(&socket), b"A:old2");
    finished(&core, &plan, REQUEST, 2);
    assert_eq!(udp_receive(&socket), b"B:new2");
    udp_send(&socket, relay, "first.fixture.invalid", b"old3");
    assert_eq!(udp_receive(&socket), b"A:old3");
    assert_eq!(
        (
            a.packets.load(Ordering::Acquire),
            b.packets.load(Ordering::Acquire)
        ),
        (3, 1)
    );
    let revoke = prepared(&core, candidate, REQUEST3, 2, 3, 2, vec![A.into()]);
    activated(&core, &revoke, REQUEST3, 2, 3);
    finished(&core, &revoke, REQUEST3, 3);
    let mut byte = [0];
    assert_eq!(
        control.read(&mut byte).unwrap(),
        0,
        "revocation receipt must acknowledge UDP association teardown"
    );
    udp_send(&socket, relay, "first.fixture.invalid", b"dead");
    socket
        .set_read_timeout(Some(Duration::from_millis(100)))
        .unwrap();
    assert!(socket.recv_from(&mut [0; 1024]).is_err());
    assert_eq!(
        (
            a.packets.load(Ordering::Acquire),
            b.packets.load(Ordering::Acquire)
        ),
        (3, 1)
    );
    core.stop();
}

#[test]
fn classification_dns_uses_default_proxy_then_verified_tls_without_direct_or_plaintext_fallback() {
    dns_transport_roundtrip(false);
}

#[test]
fn native_dns_uses_selected_proxy_verified_tls_without_direct_or_plaintext_fallback() {
    dns_transport_roundtrip(true);
}

fn dns_transport_roundtrip(native_ingress: bool) {
    use base64::Engine;
    use swirl_subscription::{DnsQueryFamily, DnsTlsServer, Tls};
    use tokio_rustls::{
        TlsAcceptor,
        rustls::{
            ServerConfig,
            pki_types::{CertificateDer, PrivatePkcs8KeyDer},
        },
    };
    let fixture: Value = serde_json::from_str(include_str!(
        "../../swirl-transport/tests/fixtures/reality_auth.json"
    ))
    .unwrap();
    let certificate = &fixture["certificate"];
    let hex = |key: &str| {
        certificate[key]
            .as_str()
            .unwrap()
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
            .collect::<Vec<_>>()
    };
    let der = hex("ordinary_self_signed_der_hex");
    let key = hex("ed25519_pkcs8_der_hex");
    let server = ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(
            vec![CertificateDer::from(der.clone())],
            PrivatePkcs8KeyDer::from(key).into(),
        )
        .unwrap();
    for trusted_name in [true, false] {
        let proxy = StdListener::bind("127.0.0.1:0").unwrap();
        let proxy_address = proxy.local_addr().unwrap();
        proxy.set_nonblocking(true).unwrap();
        let direct = StdListener::bind("127.0.0.1:0").unwrap();
        let direct_address = direct.local_addr().unwrap();
        direct.set_nonblocking(true).unwrap();
        let plaintext = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
        plaintext.set_nonblocking(true).unwrap();
        let observed = Arc::new(AtomicUsize::new(0));
        let dns_queries = observed.clone();
        let acceptor = TlsAcceptor::from(Arc::new(server.clone()));
        let peer = thread::spawn(move || {
            let runtime = Builder::new_current_thread().enable_all().build().unwrap();
            runtime.block_on(async move {
                let listener = TcpListener::from_std(proxy).unwrap();
                let (mut socket, _) = timeout(Duration::from_secs(4), listener.accept())
                    .await
                    .unwrap()
                    .unwrap();
                let mut request = Vec::new();
                while !request.ends_with(b"\r\n\r\n") {
                    request.push(socket.read_u8().await.unwrap());
                }
                assert!(
                    request
                        .starts_with(format!("CONNECT {direct_address} HTTP/1.1\r\n").as_bytes())
                );
                socket
                    .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    .await
                    .unwrap();
                let accepted = acceptor.accept(socket).await;
                if !trusted_name {
                    assert!(accepted.is_err());
                    return;
                }
                let mut tls = accepted.unwrap();
                let size = tls.read_u16().await.unwrap();
                let mut query = vec![0; usize::from(size)];
                tls.read_exact(&mut query).await.unwrap();
                assert_eq!(&query[query.len() - 4..], &[0, 1, 0, 1]);
                let mut reply = query.clone();
                reply[2..4].copy_from_slice(&[0x81, 0x80]);
                reply[6..8].copy_from_slice(&[0, 1]);
                reply.extend_from_slice(&[
                    0xc0, 0x0c, 0, 1, 0, 1, 0, 0, 0, 60, 0, 4, 203, 0, 113, 9,
                ]);
                dns_queries.fetch_add(1, Ordering::AcqRel);
                tls.write_u16(reply.len() as u16).await.unwrap();
                tls.write_all(&reply).await.unwrap();
                tls.flush().await.unwrap();
                let _ = tls.shutdown().await;
            });
        });
        let a = Peer::new(b'A');
        let b = Peer::new(b'B');
        let mut candidate = config(&a, &b, A, true);
        candidate.nodes[0].outbound = Outbound::HttpConnect {
            host: proxy_address.ip().to_string(),
            port: proxy_address.port(),
            auth: None,
            tls: None,
        };
        candidate.policy.classification_dns = ClassificationDns::ViaDefaultPolicy;
        candidate.dns = Dns {
            query_family: DnsQueryFamily::Ipv4Only,
            hosts: vec![],
            force_proxy_hosts: false,
            use_system_hosts: false,
            servers: vec![],
            tls_servers: vec![DnsTlsServer {
                address: direct_address,
                tls: Tls {
                    server_name: if trusted_name {
                        "reality.test"
                    } else {
                        "wrong.fixture.invalid"
                    }
                    .into(),
                    alpn: vec![],
                    ca_der_base64: Some(base64::engine::general_purpose::STANDARD.encode(&der)),
                },
                https_path: None,
            }],
        };
        let mut core = Core::start(candidate, STORE.into(), 1, START.into()).unwrap();
        let resolved = if native_ingress {
            let dispatcher = core.flow_dispatcher().unwrap();
            core.runtime
                .as_ref()
                .unwrap()
                .block_on(dispatcher.resolve_dns(
                    "classified.fixture.invalid",
                    443,
                    "192.0.2.2:12000".parse().unwrap(),
                ))
        } else {
            let plan = core.shared.live.lock().unwrap().plan.clone();
            core.runtime.as_ref().unwrap().block_on(classify(
                &plan,
                "classified.fixture.invalid",
                443,
            ))
        };
        if trusted_name {
            assert_eq!(resolved.unwrap(), vec!["203.0.113.9:443".parse().unwrap()]);
            assert_eq!(observed.load(Ordering::Acquire), 1);
        } else {
            assert!(resolved.is_err());
            assert_eq!(observed.load(Ordering::Acquire), 0);
        }
        assert_eq!(
            direct.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
        assert_eq!(
            plaintext.recv_from(&mut [0; 512]).unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
        peer.join().unwrap();
        core.stop();
    }
}

fn native_dns_fixture(mut candidate: RuntimeConfig) -> RuntimeConfig {
    candidate.dns.tls_servers = vec![swirl_subscription::DnsTlsServer {
        address: "192.0.2.1:853".parse().unwrap(),
        tls: swirl_subscription::Tls {
            server_name: "dns.fixture.invalid".into(),
            alpn: vec![],
            ca_der_base64: None,
        },
        https_path: None,
    }];
    candidate
}

#[test]
fn native_tcp_reuses_proxy_policy_admission_pinning_and_catalogue_revocation() {
    let a = Peer::new(b'A');
    let b = Peer::new(b'B');
    let initial = native_dns_fixture(config(&a, &b, A, true));
    let candidate = native_dns_fixture(config(&a, &b, B, false));
    let mut core = Core::start(initial, STORE.into(), 1, START.into()).unwrap();
    let dispatcher = core.flow_dispatcher().unwrap();
    let runtime = Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap();
    let open = |dispatcher: FlowDispatcher| async move {
        let (mut client, incoming) = tokio::io::duplex(1024);
        let relay = tokio::spawn(async move {
            dispatcher
                .relay_tcp(
                    incoming,
                    "192.0.2.2:12000".parse().unwrap(),
                    NetworkTarget {
                        host: "target.fixture.invalid".into(),
                        port: 80,
                    },
                )
                .await
        });
        client.write_all(b"ping").await.unwrap();
        (client, relay)
    };
    let (mut old_client, old_relay) = runtime.block_on(open(dispatcher.clone()));
    runtime.block_on(async {
        let mut response = [0; 6];
        old_client.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"A:ping");
    });
    let plan = prepared(&core, candidate.clone(), REQUEST, 1, 2, 1, vec![]);
    activated(&core, &plan, REQUEST, 1, 2);
    let (mut new_client, new_relay) = runtime.block_on(open(dispatcher));
    wait(|| core.shared.waiting.load(Ordering::Acquire) == 1);
    assert_eq!(b.requests.load(Ordering::Acquire), 0);
    finished(&core, &plan, REQUEST, 2);
    runtime.block_on(async {
        let mut response = [0; 6];
        new_client.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"B:ping");
        old_client.write_all(b"old1").await.unwrap();
        old_client.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"A:old1");
    });
    let revoke = prepared(&core, candidate, REQUEST3, 2, 3, 2, vec![A.into()]);
    activated(&core, &revoke, REQUEST3, 2, 3);
    finished(&core, &revoke, REQUEST3, 3);
    runtime.block_on(async {
        assert_eq!(old_client.read(&mut [0; 1]).await.unwrap(), 0);
        assert_eq!(old_relay.await.unwrap(), Err("SessionRevoked"));
        let mut response = [0; 6];
        new_client.write_all(b"new2").await.unwrap();
        new_client.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"B:new2");
        drop(new_client);
        new_relay.await.unwrap().unwrap();
    });
    assert_eq!(a.requests.load(Ordering::Acquire), 2);
    assert_eq!(b.requests.load(Ordering::Acquire), 2);
    core.stop();
}

#[test]
fn native_udp_reuses_shadowsocks_outbound_and_revokes_an_idle_session() {
    let a = DatagramPeer::new(b'A');
    let b = DatagramPeer::new(b'B');
    let dummy_a = Peer::new(b'A');
    let dummy_b = Peer::new(b'B');
    let mut initial = native_dns_fixture(config(&dummy_a, &dummy_b, A, true));
    initial.nodes = vec![a.node(A), b.node(B)];
    let mut candidate = initial.clone();
    candidate.nodes = vec![b.node(B)];
    candidate.policy.default_policy.target = Target::Node { id: B.into() };
    let mut core = Core::start(initial, STORE.into(), 1, START.into()).unwrap();
    let dispatcher = core.flow_dispatcher().unwrap();
    let runtime = Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .unwrap();
    let mut flow = runtime.block_on(async {
        let mut flow = dispatcher
            .open_udp(
                "192.0.2.2:12000".parse().unwrap(),
                NetworkTarget {
                    host: "target.fixture.invalid".into(),
                    port: 80,
                },
            )
            .await
            .unwrap();
        flow.send(b"udp1").await.unwrap();
        let mut response = [0; 64];
        let size = timeout(Duration::from_secs(3), flow.recv(&mut response))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(&response[..size], b"A:udp1");
        flow
    });
    let plan = prepared(&core, candidate, REQUEST, 1, 2, 1, vec![A.into()]);
    activated(&core, &plan, REQUEST, 1, 2);
    // No send/recv future is polled by the caller here: the owned worker must
    // observe cancellation itself and release the real revocation barrier.
    finished(&core, &plan, REQUEST, 2);
    assert_eq!(core.snapshot().unwrap()["active"], 0);
    runtime.block_on(async {
        assert_eq!(flow.recv(&mut [0; 64]).await, Err("SessionRevoked"));
        assert_eq!(flow.send(b"must-not-replay").await, Err("SessionRevoked"));
    });
    assert_eq!(a.packets.load(Ordering::Acquire), 1);
    assert_eq!(b.packets.load(Ordering::Acquire), 0);
    core.stop();
}
