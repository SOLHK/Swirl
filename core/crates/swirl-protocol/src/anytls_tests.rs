use super::*;
use swirl_subscription::Tls;

fn configuration(port: u16) -> AnyTls {
    use base64::Engine;
    let fixture: serde_json::Value = serde_json::from_str(include_str!(
        "../../swirl-transport/tests/fixtures/reality_auth.json"
    ))
    .unwrap();
    let hex = fixture["certificate"]["ordinary_self_signed_der_hex"]
        .as_str()
        .unwrap();
    let certificate = (0..hex.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&hex[index..index + 2], 16).unwrap())
        .collect::<Vec<_>>();
    AnyTls {
        host: "127.0.0.1".into(),
        port,
        password: "swirl-fixture-password".into(),
        tls: Tls {
            server_name: "reality.test".into(),
            alpn: vec![],
            ca_der_base64: Some(base64::engine::general_purpose::STANDARD.encode(certificate)),
        },
        udp: true,
        idle_session_timeout_seconds: 5,
        session_owner: Arc::default(),
    }
}

struct Actor {
    client: Arc<Client>,
    session: Arc<Session>,
    peer: DuplexStream,
}
impl Actor {
    fn new() -> Self {
        let padding = Padding::parse(b"stop=0").unwrap();
        let client = Arc::new(Client {
            padding: Mutex::new(padding.clone()),
            sessions: Mutex::new(Vec::new()),
            next: AtomicU64::new(1),
            closed: AtomicBool::new(false),
            slots: Arc::new(Semaphore::new(MAX_SESSIONS)),
            pending: AtomicUsize::new(0),
        });
        Self::with_client(client)
    }
    fn with_client(client: Arc<Client>) -> Self {
        let padding = client.padding.lock().unwrap().clone();
        let (open, requests) = mpsc::channel(1);
        let session = Arc::new(Session {
            sequence: 1,
            busy: AtomicBool::new(true),
            closed: AtomicBool::new(false),
            open,
            task: Mutex::new(None),
            idle: Mutex::new(Instant::now()),
            egress: EgressToken::capture(&["127.0.0.1:443".parse().unwrap()]).unwrap(),
            _slot: client.slots.clone().try_acquire_owned().unwrap(),
        });
        let (stream, peer) = tokio::io::duplex(65536);
        let task = tokio::spawn(run_session(
            Box::new(stream),
            Arc::downgrade(&client),
            session.clone(),
            requests,
            Duration::from_secs(5),
            padding,
        ));
        *session.task.lock().unwrap() = Some(task.abort_handle());
        client.sessions.lock().unwrap().push(session.clone());
        Self {
            client,
            session,
            peer,
        }
    }
    async fn open(&mut self) -> (AnyStream, oneshot::Receiver<Result<()>>) {
        self.session.busy.store(true, Ordering::Release);
        let (stream, server) = tokio::io::duplex(65536);
        let (ready, ack) = oneshot::channel();
        let error = Arc::new(Mutex::new(None));
        self.session
            .open
            .send(Open {
                target: Target {
                    host: "example.test".into(),
                    port: 443,
                },
                initial_data: vec![],
                stream: server,
                ready,
                error: error.clone(),
            })
            .await
            .unwrap();
        (
            AnyStream {
                stream,
                error,
                _owner: Arc::default(),
            },
            ack,
        )
    }
    async fn read_open(&mut self, id: u32, first: bool) {
        if first {
            assert_eq!(read_frame(&mut self.peer).await.unwrap().command, 4);
        }
        let syn = read_frame(&mut self.peer).await.unwrap();
        assert_eq!((syn.command, syn.id), (1, id));
        let target = read_frame(&mut self.peer).await.unwrap();
        assert_eq!((target.command, target.id), (2, id));
    }
}
impl Drop for Actor {
    fn drop(&mut self) {
        self.client.close();
    }
}

#[tokio::test(start_paused = true)]
async fn incomplete_control_and_data_frames_have_one_bounded_deadline() {
    for wire in [vec![6], vec![2, 0, 0, 0, 1, 0, 3, b'x']] {
        let (mut peer, mut reader) = tokio::io::duplex(64);
        peer.write_all(&wire).await.unwrap();
        let started = Instant::now();
        assert_eq!(
            read_frame(&mut reader).await.err(),
            Some("AnyTlsFrameTimeout")
        );
        assert_eq!(started.elapsed(), IO_LIMIT);
    }
}

#[tokio::test(start_paused = true)]
async fn v2_missing_ack_closes_stream_and_idle_sessions_expire() {
    let mut actor = Actor::new();
    let (mut stream, ack) = actor.open().await;
    actor.read_open(1, true).await;
    ack.await.unwrap().unwrap();
    actor
        .peer
        .write_all(&frame(10, 0, b"v=2").unwrap())
        .await
        .unwrap();
    let started = Instant::now();
    assert_eq!(
        stream.read_u8().await.unwrap_err().to_string(),
        "AnyTlsSynAckTimeout"
    );
    assert_eq!(started.elapsed(), SYN_LIMIT);
    assert!(actor.session.closed.load(Ordering::Acquire));
    let mut idle = Actor::new();
    let started = Instant::now();
    assert_eq!(
        idle.peer.read_u8().await.unwrap_err().kind(),
        io::ErrorKind::UnexpectedEof
    );
    assert_eq!(started.elapsed(), Duration::from_secs(5));
    assert!(idle.session.closed.load(Ordering::Acquire));
    assert!(idle.client.closed.load(Ordering::Acquire));
}

#[tokio::test(start_paused = true)]
async fn retired_sessions_release_client_limits_across_many_resolved_identities() {
    let config = configuration(443);
    for port in 10000..10160 {
        let addresses = [std::net::SocketAddr::from(([127, 0, 0, 1], port))];
        let egress = EgressToken::capture(&addresses).unwrap();
        let reservation = client(&config, egress, &addresses).unwrap();
        let mut actor = Actor::with_client(reservation.0.clone());
        drop(reservation);
        assert!(!actor.client.closed.load(Ordering::Acquire));
        assert_eq!(
            actor.peer.read_u8().await.unwrap_err().kind(),
            io::ErrorKind::UnexpectedEof
        );
        assert!(actor.client.closed.load(Ordering::Acquire));
    }
    let pool = CLIENTS.lock().unwrap();
    assert!(
        pool.iter()
            .filter(|entry| Weak::ptr_eq(&entry.owner, &Arc::downgrade(&config.session_owner)))
            .count()
            <= 1
    );
}

#[tokio::test]
async fn reused_session_waits_for_ack_and_cancel_retires_the_socket() {
    let mut actor = Actor::new();
    let (stream, ack) = actor.open().await;
    actor.read_open(1, true).await;
    ack.await.unwrap().unwrap();
    actor
        .peer
        .write_all(&frame(10, 0, b"v=2").unwrap())
        .await
        .unwrap();
    actor
        .peer
        .write_all(&frame(7, 1, &[]).unwrap())
        .await
        .unwrap();
    drop(stream);
    assert_eq!(read_frame(&mut actor.peer).await.unwrap().command, 3);
    let (mut stream, mut ack) = actor.open().await;
    actor.read_open(2, false).await;
    assert!(matches!(
        ack.try_recv(),
        Err(oneshot::error::TryRecvError::Empty)
    ));
    actor
        .peer
        .write_all(&frame(7, 2, &[]).unwrap())
        .await
        .unwrap();
    ack.await.unwrap().unwrap();
    actor
        .peer
        .write_all(&frame(2, 1, b"stale").unwrap())
        .await
        .unwrap();
    actor
        .peer
        .write_all(&frame(2, 2, b"new").unwrap())
        .await
        .unwrap();
    let mut reply = [0; 3];
    stream.read_exact(&mut reply).await.unwrap();
    assert_eq!(&reply, b"new");
    drop(stream);
    assert_eq!(read_frame(&mut actor.peer).await.unwrap().command, 3);
    let (_stream, ack) = actor.open().await;
    actor.read_open(3, false).await;
    let opening = Opening(actor.session.clone(), true);
    drop(opening);
    assert!(timeout(Duration::from_secs(1), ack).await.unwrap().is_err());
    assert!(actor.session.closed.load(Ordering::Acquire));
    assert_eq!(
        timeout(Duration::from_secs(1), actor.peer.read_u8())
            .await
            .unwrap()
            .unwrap_err()
            .kind(),
        io::ErrorKind::UnexpectedEof
    );
}

#[tokio::test]
async fn cancelling_a_tls_handshake_closes_its_owned_socket() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let config = configuration(listener.local_addr().unwrap().port());
    let task = tokio::spawn(async move {
        connect(
            &config,
            &Target {
                host: "example.test".into(),
                port: 443,
            },
            &Resolver::default(),
            Duration::from_secs(5),
        )
        .await
    });
    let (mut socket, _) = timeout(Duration::from_secs(2), listener.accept())
        .await
        .unwrap()
        .unwrap();
    let mut bytes = [0; 4096];
    assert!(socket.read(&mut bytes).await.unwrap() > 0);
    task.abort();
    assert!(matches!(task.await,Err(error) if error.is_cancelled()));
    assert_eq!(
        timeout(Duration::from_secs(2), socket.read(&mut bytes))
            .await
            .unwrap()
            .unwrap(),
        0
    );
}

#[test]
fn pools_do_not_cross_owner_credentials_resolved_addresses_or_runtime() {
    let config = configuration(443);
    let addresses = ["127.0.0.1:443".parse().unwrap()];
    let egress = EgressToken::capture(&addresses).unwrap();
    let first_runtime = tokio::runtime::Runtime::new().unwrap();
    let first = {
        let _entered = first_runtime.enter();
        let first = client(&config, egress, &addresses).unwrap();
        assert!(Arc::ptr_eq(
            &first,
            &client(&config.clone(), egress, &addresses).unwrap()
        ));
        let independent = configuration(443);
        assert!(!Arc::ptr_eq(
            &first,
            &client(&independent, egress, &addresses).unwrap()
        ));
        let mut changed = config.clone();
        changed.password.push('x');
        assert!(!Arc::ptr_eq(
            &first,
            &client(&changed, egress, &addresses).unwrap()
        ));
        changed = config.clone();
        changed.tls.server_name = "other.test".into();
        assert!(!Arc::ptr_eq(
            &first,
            &client(&changed, egress, &addresses).unwrap()
        ));
        assert!(!Arc::ptr_eq(
            &first,
            &client(&config, egress, &["127.0.0.2:443".parse().unwrap()]).unwrap()
        ));
        first
    };
    drop(first_runtime);
    let second_runtime = tokio::runtime::Runtime::new().unwrap();
    let _entered = second_runtime.enter();
    assert!(!Arc::ptr_eq(
        &first,
        &client(&config, egress, &addresses).unwrap()
    ));
    let owner = Arc::downgrade(&config.session_owner);
    drop(config);
    assert!(owner.upgrade().is_none());
    assert!(first.closed.load(Ordering::Acquire));
}
#[test]
fn padding_is_bounded_and_keeps_exact_server_digest() {
    let padding = Padding::parse(DEFAULT_PADDING.as_bytes()).unwrap();
    assert_eq!(padding.stop, 8);
    assert_eq!(padding.auth_length().unwrap(), 30);
    for value in [
        "stop=999",
        "stop=8\n0=0-1",
        "stop=8\n2=1-65535",
        "stop=8\nstop=4",
        "stop=8\n2=x",
    ] {
        assert!(Padding::parse(value.as_bytes()).is_err());
    }
    let updated = Padding::parse(b"stop=2\n0=7-7\n1=30-30").unwrap();
    assert_eq!(updated.auth_length().unwrap(), 7);
    assert_ne!(updated.md5, padding.md5);
}
#[tokio::test]
async fn split_and_joined_frames_preserve_boundaries() {
    let (mut writer, mut reader) = tokio::io::duplex(16);
    let mut wire = frame(2, 19, b"abc").unwrap();
    wire.extend(frame(3, 19, &[]).unwrap());
    let task = tokio::spawn(async move {
        for byte in wire {
            writer.write_all(&[byte]).await.unwrap();
        }
    });
    let first = read_frame(&mut reader).await.unwrap();
    assert_eq!(
        (first.command, first.id, first.data),
        (2, 19, b"abc".to_vec())
    );
    let second = read_frame(&mut reader).await.unwrap();
    assert_eq!((second.command, second.id, second.data), (3, 19, vec![]));
    task.await.unwrap();
}
async fn stats(port: u16) -> serde_json::Value {
    let mut stream = tokio::net::TcpStream::connect((std::net::Ipv4Addr::LOCALHOST, port))
        .await
        .unwrap();
    stream
        .write_all(b"GET /stats HTTP/1.0\r\nHost: localhost\r\n\r\n")
        .await
        .unwrap();
    let mut bytes = Vec::new();
    timeout(
        Duration::from_secs(2),
        stream.take(4096).read_to_end(&mut bytes),
    )
    .await
    .unwrap()
    .unwrap();
    let at = bytes.windows(4).position(|v| v == b"\r\n\r\n").unwrap() + 4;
    serde_json::from_slice(&bytes[at..]).unwrap()
}
async fn roundtrip(stream: &mut BoxStream) {
    let payload: Vec<_> = (0..131072).map(|i| (i % 251) as u8).collect();
    let mut answer = vec![0; payload.len()];
    let (mut read, mut write) = tokio::io::split(&mut **stream);
    timeout(Duration::from_secs(5), async {
        tokio::try_join!(
            async {
                write.write_all(&payload).await?;
                write.flush().await
            },
            async { read.read_exact(&mut answer).await.map(|_| ()) }
        )
    })
    .await
    .unwrap()
    .unwrap();
    assert_eq!(payload, answer);
}
#[tokio::test]
#[ignore = "requires independently built pinned anytls-go fixture and loopback echo listeners"]
async fn official_peer_reuse_padding_tcp_udp_and_owner_retirement() {
    let port = std::env::var("SWIRL_ANYTLS_PORT")
        .unwrap()
        .parse::<u16>()
        .unwrap();
    let tcp_port = std::env::var("SWIRL_ECHO_TCP_PORT")
        .unwrap()
        .parse::<u16>()
        .unwrap();
    let udp_port = std::env::var("SWIRL_ECHO_UDP_PORT")
        .unwrap()
        .parse::<u16>()
        .unwrap();
    let stats_port = std::env::var("SWIRL_ANYTLS_STATS_PORT")
        .unwrap()
        .parse::<u16>()
        .unwrap();
    let config = configuration(port);
    let resolver = Resolver::default();
    let target = Target {
        host: "127.0.0.1".into(),
        port: tcp_port,
    };
    let limit = Duration::from_secs(5);
    let mut first = connect(&config, &target, &resolver, limit).await.unwrap();
    roundtrip(&mut first).await;
    let mut second = connect(&config, &target, &resolver, limit).await.unwrap();
    roundtrip(&mut second).await;
    assert_eq!(stats(stats_port).await["accepted"], 2);
    assert_eq!(
        stats(stats_port).await["padding"],
        serde_json::json!([30, 50])
    );
    drop(first);
    drop(second);
    let client = CLIENTS
        .lock()
        .unwrap()
        .iter()
        .find(|entry| Weak::ptr_eq(&entry.owner, &Arc::downgrade(&config.session_owner)))
        .unwrap()
        .client
        .clone();
    timeout(Duration::from_secs(2), async {
        loop {
            if client
                .sessions
                .lock()
                .unwrap()
                .iter()
                .all(|s| !s.busy.load(Ordering::Acquire))
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
    let mut third = connect(&config, &target, &resolver, limit).await.unwrap();
    roundtrip(&mut third).await;
    let newest = client
        .sessions
        .lock()
        .unwrap()
        .iter()
        .filter(|s| s.busy.load(Ordering::Acquire))
        .map(|s| s.sequence)
        .collect::<Vec<_>>();
    assert_eq!(newest, vec![2]);
    assert_eq!(stats(stats_port).await["accepted"], 2);
    drop(third);
    timeout(Duration::from_secs(2), async {
        loop {
            if client
                .sessions
                .lock()
                .unwrap()
                .iter()
                .all(|session| !session.busy.load(Ordering::Acquire))
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
    let outbound = swirl_subscription::Outbound::AnyTls(config.clone());
    let udp_target = Target {
        host: "127.0.0.1".into(),
        port: udp_port,
    };
    let mut udp =
        crate::stream_udp::UdpAssociation::connect(&outbound, &udp_target, &resolver, limit, None)
            .await
            .unwrap();
    udp.send(&udp_target, b"datagram-one").await.unwrap();
    let (sender, reply) = timeout(limit, udp.recv()).await.unwrap().unwrap();
    assert_eq!(sender.port, udp_port);
    assert_eq!(reply, b"datagram-one");
    let packet = vec![0x95; 1400];
    udp.send(&udp_target, &packet).await.unwrap();
    assert_eq!(timeout(limit, udp.recv()).await.unwrap().unwrap().1, packet);
    drop(udp);
    drop(outbound);
    let streams_before = stats(stats_port).await["streams"].as_u64().unwrap();
    let mut untrusted = config.clone();
    untrusted.tls.ca_der_base64 = None;
    assert_eq!(
        connect(&untrusted, &target, &resolver, limit).await.err(),
        Some("TlsCertificateUnknownIssuer")
    );
    let mut wrong_name = config.clone();
    wrong_name.tls.server_name = "wrong.fixture.test".into();
    assert_eq!(
        connect(&wrong_name, &target, &resolver, limit).await.err(),
        Some("TlsCertificateNameMismatch")
    );
    let mut wrong_password = config.clone();
    wrong_password.password.push('x');
    if let Ok(mut unauthenticated) = connect(&wrong_password, &target, &resolver, limit).await {
        let _ = unauthenticated.write_all(b"must-not-reach-target").await;
        let mut output = [0; 64];
        let result = timeout(Duration::from_secs(2), unauthenticated.read(&mut output))
            .await
            .unwrap();
        assert!(
            result.is_err() || result.unwrap() == 0,
            "wrong password returned target data"
        );
    }
    assert_eq!(
        stats(stats_port).await["streams"].as_u64().unwrap(),
        streams_before
    );
    drop(untrusted);
    drop(wrong_name);
    drop(wrong_password);
    let owner = Arc::downgrade(&config.session_owner);
    drop(config);
    assert!(owner.upgrade().is_none());
    assert!(client.closed.load(Ordering::Acquire));
    timeout(Duration::from_secs(2), async {
        loop {
            if stats(stats_port).await["active"] == 0 {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();

    let limited = configuration(port);
    let before = stats(stats_port).await["accepted"].as_u64().unwrap();
    let mut streams = Vec::new();
    for _ in 0..MAX_SESSIONS {
        let mut stream = connect(&limited, &target, &resolver, limit).await.unwrap();
        stream.write_all(b"limit").await.unwrap();
        let mut reply = [0; 5];
        stream.read_exact(&mut reply).await.unwrap();
        assert_eq!(&reply, b"limit");
        streams.push(stream);
    }
    assert_eq!(
        connect(&limited, &target, &resolver, limit).await.err(),
        Some("AnyTlsSessionLimit")
    );
    assert_eq!(
        stats(stats_port).await["accepted"].as_u64().unwrap(),
        before + MAX_SESSIONS as u64
    );
    drop(streams);
    drop(limited);
    timeout(Duration::from_secs(2), async {
        loop {
            if stats(stats_port).await["active"] == 0 {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();

    #[cfg(windows)]
    {
        // The lease is only a process-local socket-admission epoch. This does
        // not install an adapter or alter host routes, proxy settings or DNS.
        let config = configuration(port);
        let mut stream = connect(&config, &target, &resolver, limit).await.unwrap();
        roundtrip(&mut stream).await;
        let lease = swirl_transport::egress::EgressLease::acquire_suspended().unwrap();
        let _ = stream.write_all(b"must-not-use-the-retired-egress").await;
        let result = timeout(limit, stream.read_u8()).await.unwrap();
        assert!(
            result.is_err(),
            "a retired egress returned new application bytes"
        );
        drop(stream);
        drop(config);
        lease.release_after_routes_restored().unwrap();
        timeout(Duration::from_secs(2), async {
            loop {
                if stats(stats_port).await["active"] == 0 {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
    }
}
