//! Explicit, scoped Wintun smoke for a disposable Windows runner.
//! `cargo test --all-targets` compiles this example without running `main`.
//! No networking or driver operation is reachable without that explicit flag.

use std::{io, path::PathBuf, process::ExitCode};

fn arguments() -> io::Result<Option<PathBuf>> {
    let mut arguments = std::env::args_os().skip(1);
    let mut disposable = false;
    let mut driver = None;
    while let Some(argument) = arguments.next() {
        if argument == "--help" {
            println!(
                "windows-tun-smoke --disposable-network --wintun <absolute official wintun.dll>\n\
                 Only use an explicitly authorized disposable Windows environment.\n\
                 Configures one temporary adapter and two exact test destination routes."
            );
            return Ok(None);
        } else if argument == "--disposable-network" && !disposable {
            disposable = true;
        } else if argument == "--wintun" && driver.is_none() {
            driver = Some(PathBuf::from(arguments.next().ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidInput, "--wintun requires a path")
            })?));
        } else {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!(
                    "unsupported or duplicate argument: {}",
                    argument.to_string_lossy()
                ),
            ));
        }
    }
    if !disposable {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "explicit --disposable-network acknowledgement is required",
        ));
    }
    driver.map(Some).ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "--wintun requires an absolute DLL path",
        )
    })
}

fn main() -> ExitCode {
    let result = arguments().and_then(|driver| match driver {
        None => Ok(()),
        Some(driver) => execute(driver),
    });
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("windows-tun-smoke failed: {error}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(not(windows))]
fn execute(_: PathBuf) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "this smoke requires Windows; no network operation was attempted",
    ))
}

#[cfg(windows)]
fn execute(driver: PathBuf) -> io::Result<()> {
    windows::run(driver)
}

#[cfg(windows)]
mod windows {
    use super::*;
    use ring::rand::{SecureRandom, SystemRandom};
    use serde_json::json;
    use std::{
        collections::BTreeMap,
        future::Future,
        io::{Read, Write},
        net::{IpAddr, Ipv4Addr, Ipv6Addr, Shutdown, SocketAddr},
        path::Path,
        pin::Pin,
        sync::{
            Arc,
            atomic::{AtomicBool, AtomicU64, Ordering},
        },
        thread,
        time::{Duration, Instant},
    };
    use swirl_api::native_tun::{self, BridgeControl, PacketBridge};
    use swirl_core::v2::{Core, FlowDispatcher, RuntimeConfig};
    use swirl_dns::tun::{DNS_IPV4, DNS_IPV6, FakeIpStore, TunDns, TunLookup};
    use swirl_platform::{
        network_transaction::{
            self as transaction, FileJournalStore, InterfaceIdentity, Journal, Resource, Value,
        },
        windows_network::{self, SystemRoute, WindowsNetworkBackend},
        wintun_device::{WintunConfig, WintunDevice, official_driver_sha256},
    };
    use swirl_subscription::{
        Dns, DnsTlsServer, HostMapping, Limits, Node, Outbound, Tls,
        v2::{ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, Mode, PolicyDocument, Target},
    };
    use swirl_transport::egress::EgressLease;
    use swirl_tun::{TunConfig, TunStats};
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        runtime::Handle,
        task::JoinHandle,
        time::timeout,
    };

    const IO_WAIT: Duration = Duration::from_secs(15);
    const MTU: u32 = 1500;
    const TCP_BYTES: usize = 256 * 1024;
    const UDP_BYTES: usize = 1200;
    const HOST_V4: &str = "ipv4.wintun.smoke.invalid";
    const HOST_V6: &str = "ipv6.wintun.smoke.invalid";
    const OWN_V4: Ipv4Addr = Ipv4Addr::new(198, 18, 0, 1);
    const OWN_V6: Ipv6Addr = Ipv6Addr::new(0xfd53, 0x7769, 0x726c, 0, 0, 0, 0, 1);

    fn require(condition: bool, reason: &'static str) -> io::Result<()> {
        if condition {
            Ok(())
        } else {
            Err(io::Error::other(reason))
        }
    }

    fn nonce() -> io::Result<(String, u128)> {
        let mut bytes = [0u8; 16];
        SystemRandom::new()
            .fill(&mut bytes)
            .map_err(|_| io::Error::other("secure random unavailable"))?;
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        Ok((
            bytes.iter().map(|byte| format!("{byte:02x}")).collect(),
            u128::from_be_bytes(bytes),
        ))
    }

    fn runtime_config() -> io::Result<RuntimeConfig> {
        Ok(RuntimeConfig {
            schema: 2,
            listen: "127.0.0.1:0".parse().map_err(io::Error::other)?,
            nodes: vec![Node {
                id: "c1000000-0000-4000-8000-000000000001".into(),
                // Direct mode must never dial this unused proxy fixture.
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
                        id: "c1000000-0000-4000-8000-000000000001".into(),
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
                // Explicit encrypted DNS is required by the real Core lease.
                // Exact hosts below satisfy every query. The suspended egress
                // lease forbids any accidental non-loopback bootstrap dial.
                tls_servers: vec![DnsTlsServer {
                    address: "192.0.2.1:853".parse().map_err(io::Error::other)?,
                    tls: Tls {
                        server_name: "dns.wintun.smoke.invalid".into(),
                        alpn: vec![],
                        ca_der_base64: None,
                    },
                    https_path: None,
                }],
                hosts: vec![
                    HostMapping {
                        name: HOST_V4.into(),
                        address: Ipv4Addr::LOCALHOST.into(),
                    },
                    HostMapping {
                        name: HOST_V6.into(),
                        address: Ipv6Addr::LOCALHOST.into(),
                    },
                ],
                ..Dns::default()
            },
            inbound_auth: None,
            limits: Limits::default(),
            china_rules_directory: None,
            node_sources: BTreeMap::new(),
            transports: BTreeMap::new(),
        })
    }

    struct Lookup(FlowDispatcher);
    impl TunLookup for Lookup {
        fn lookup<'a>(
            &'a self,
            name: &'a str,
        ) -> Pin<Box<dyn Future<Output = Result<Vec<IpAddr>, &'static str>> + Send + 'a>> {
            Box::pin(async move {
                self.0
                    .resolve_dns(name, 53, SocketAddr::new(OWN_V4.into(), 41053))
                    .await
                    .map(|addresses| addresses.into_iter().map(|address| address.ip()).collect())
            })
        }
    }

    fn query(name: &str, ipv6: bool) -> Vec<u8> {
        let mut result = vec![0xca, 0xfe, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0];
        for label in name.split('.') {
            result.push(label.len() as u8);
            result.extend_from_slice(label.as_bytes());
        }
        result.push(0);
        result.extend_from_slice(if ipv6 { &[0, 28, 0, 1] } else { &[0, 1, 0, 1] });
        result
    }

    // This only validates the fixed single-answer fixture emitted by TunDns.
    // It is not a second DNS resolver or a general-purpose DNS parser.
    fn answer_ip(request: &[u8], response: &[u8], ipv6: bool) -> io::Result<IpAddr> {
        let length = if ipv6 { 16 } else { 4 };
        require(
            response.len() == request.len() + 12 + length,
            "DNS response length",
        )?;
        require(response[..2] == request[..2], "DNS transaction identity")?;
        require(
            response[2] & 0x80 != 0 && response[3] & 15 == 0,
            "DNS response must succeed",
        )?;
        require(
            response[4..8] == [0, 1, 0, 1],
            "one DNS question and one answer required",
        )?;
        require(
            response[8..12] == [0; 4],
            "unexpected DNS authority/additional records",
        )?;
        require(
            response[12..request.len()] == request[12..],
            "DNS question changed",
        )?;
        let answer = &response[request.len()..];
        require(answer[..2] == [0xc0, 0x0c], "DNS answer name identity")?;
        require(
            answer[2..6] == request[request.len() - 4..],
            "DNS answer type/class",
        )?;
        require(
            u16::from_be_bytes([answer[10], answer[11]]) as usize == length,
            "DNS address length",
        )?;
        if ipv6 {
            Ok(
                Ipv6Addr::from(<[u8; 16]>::try_from(&answer[12..]).map_err(io::Error::other)?)
                    .into(),
            )
        } else {
            Ok(
                Ipv4Addr::from(<[u8; 4]>::try_from(&answer[12..]).map_err(io::Error::other)?)
                    .into(),
            )
        }
    }

    struct DeviceRun {
        device: Option<Arc<WintunDevice>>,
        runtime: Handle,
        bridge: BridgeControl,
        stats: TunStats,
        reader: Option<thread::JoinHandle<()>>,
        writer: Option<JoinHandle<()>>,
        closing: Arc<AtomicBool>,
        failed: Arc<AtomicBool>,
        read_packets: Arc<AtomicU64>,
        written_packets: Arc<AtomicU64>,
        backend: WindowsNetworkBackend,
        journal: Journal,
        store: FileJournalStore,
        journal_path: PathBuf,
        binding: Option<EgressLease>,
        restored: bool,
    }

    impl DeviceRun {
        fn start(
            driver: PathBuf,
            directory: &Path,
            identity_seed: (String, u128),
            packet: PacketBridge,
            runtime: Handle,
            fake: [IpAddr; 2],
            binding: EgressLease,
        ) -> io::Result<Self> {
            let (owner, guid) = identity_seed;
            let device = Arc::new(WintunDevice::create(&WintunConfig {
                driver_path: driver,
                expected_sha256: official_driver_sha256()?.into(),
                adapter_name: format!("Swirl TUN Smoke {}", &owner[..8]),
                adapter_guid: guid,
                ring_capacity: 4 * 1024 * 1024,
            })?);
            let identity = InterfaceIdentity::new(device.interface_index()?, device.adapter_guid());
            let mut backend = WindowsNetworkBackend::for_owned_interface(identity.clone())?;
            let mut desired = vec![
                (Resource::Mtu { ipv6: false }, Some(Value::Mtu { mtu: MTU })),
                (Resource::Mtu { ipv6: true }, Some(Value::Mtu { mtu: MTU })),
                (
                    Resource::Address {
                        address: OWN_V4.into(),
                    },
                    Some(Value::Address {
                        prefix_len: 30,
                        skip_as_source: false,
                    }),
                ),
                (
                    Resource::Address {
                        address: OWN_V6.into(),
                    },
                    Some(Value::Address {
                        prefix_len: 126,
                        skip_as_source: false,
                    }),
                ),
            ];
            for address in fake {
                desired.push((
                    Resource::Route {
                        destination: ipnet::IpNet::new(
                            address,
                            if address.is_ipv6() { 128 } else { 32 },
                        )
                        .map_err(io::Error::other)?,
                        next_hop: if address.is_ipv6() {
                            Ipv6Addr::UNSPECIFIED.into()
                        } else {
                            Ipv4Addr::UNSPECIFIED.into()
                        },
                    },
                    Some(Value::Route { metric: 5 }),
                ));
            }
            // No DNS, firewall, default route, split default, or physical
            // interface mutation is expressible by this desired plan.
            let journal = Journal::prepare(&mut backend, identity.clone(), owner, desired)
                .map_err(|error| {
                    io::Error::other(format!("snapshot owned test resources: {error}"))
                })?;
            let journal_path =
                directory.join(format!("{}.network.json", identity.guid.replace('-', "")));
            let store = FileJournalStore::create_new(&journal_path)?;
            let mut run = Self {
                device: Some(device),
                runtime,
                bridge: packet.control,
                stats: packet.stats,
                reader: None,
                writer: None,
                closing: Arc::new(AtomicBool::new(false)),
                failed: Arc::new(AtomicBool::new(false)),
                read_packets: Arc::new(AtomicU64::new(0)),
                written_packets: Arc::new(AtomicU64::new(0)),
                backend,
                journal,
                store,
                journal_path,
                binding: Some(binding),
                restored: false,
            };
            let reader_device = run
                .device
                .as_ref()
                .ok_or_else(|| io::Error::other("missing device"))?
                .clone();
            let closing = run.closing.clone();
            let failed = run.failed.clone();
            let count = run.read_packets.clone();
            run.reader = Some(
                thread::Builder::new()
                    .name("swirl-smoke-wintun-read".into())
                    .spawn(move || {
                        while !closing.load(Ordering::Acquire) {
                            let mut bytes = Vec::with_capacity(MTU as usize);
                            match reader_device.receive_blocking(&mut bytes) {
                                Ok(()) if bytes.len() <= MTU as usize => {
                                    count.fetch_add(1, Ordering::Relaxed);
                                    if packet.input.blocking_send(bytes).is_err() {
                                        if !closing.load(Ordering::Acquire) {
                                            failed.store(true, Ordering::Release);
                                        }
                                        break;
                                    }
                                }
                                Err(_) if closing.load(Ordering::Acquire) => break,
                                _ => {
                                    failed.store(true, Ordering::Release);
                                    break;
                                }
                            }
                        }
                    })?,
            );
            let writer_device = run
                .device
                .as_ref()
                .ok_or_else(|| io::Error::other("missing device"))?
                .clone();
            let mut output = packet.output;
            let closing = run.closing.clone();
            let failed = run.failed.clone();
            let count = run.written_packets.clone();
            run.writer = Some(run.runtime.spawn(async move {
                while let Some(bytes) = output.recv().await {
                    let mut delivered = false;
                    for _ in 0..64 {
                        match writer_device.send(&bytes) {
                            Ok(()) => {
                                count.fetch_add(1, Ordering::Relaxed);
                                delivered = true;
                                break;
                            }
                            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                                tokio::time::sleep(Duration::from_millis(1)).await;
                            }
                            Err(_) if closing.load(Ordering::Acquire) => return,
                            Err(_) => {
                                failed.store(true, Ordering::Release);
                                return;
                            }
                        }
                    }
                    if !delivered {
                        failed.store(true, Ordering::Release);
                        return;
                    }
                }
            }));
            transaction::apply(&mut run.backend, &mut run.store, &mut run.journal).map_err(
                |error| io::Error::other(format!("apply owned test resources: {error}")),
            )?;
            Ok(run)
        }

        fn stop(&mut self) -> io::Result<()> {
            if self.restored {
                return Ok(());
            }
            let mut errors = Vec::new();
            match transaction::recover(&mut self.backend, &mut self.store, &mut self.journal) {
                Ok(report) if report.conflicts.is_empty() && self.journal.is_restored() => {}
                Ok(report) => errors.push(format!(
                    "network recovery conflicts: {:?}",
                    report.conflicts
                )),
                Err(error) => errors.push(format!("network recovery: {error}")),
            }
            // Always shut down packet tasks after attempting compare-restore,
            // even when an OS failure must leave a journal for later recovery.
            self.closing.store(true, Ordering::Release);
            if let Some(device) = &self.device
                && let Err(error) = device.shutdown()
            {
                errors.push(format!("device shutdown: {error}"));
            }
            if let Err(error) = self.runtime.block_on(self.bridge.shutdown()) {
                errors.push(format!("bridge shutdown: {error}"));
            }
            if let Some(writer) = self.writer.take() {
                writer.abort();
                let _ = self.runtime.block_on(writer);
            }
            if let Some(reader) = self.reader.take()
                && reader.join().is_err()
            {
                errors.push("packet reader panicked".into());
            }
            self.device.take();
            if errors.is_empty() {
                let archive = self.journal_path.with_extension("smoke-restored");
                if archive.exists() {
                    errors.push("restored journal archive already exists".into());
                } else if let Err(error) = std::fs::rename(&self.journal_path, archive) {
                    errors.push(format!("journal archive: {error}"));
                }
            }
            if errors.is_empty() {
                if let Some(binding) = self.binding.take() {
                    binding.release_after_routes_restored()?;
                }
                self.restored = true;
                Ok(())
            } else {
                Err(io::Error::other(errors.join("; ")))
            }
        }
    }

    impl Drop for DeviceRun {
        fn drop(&mut self) {
            if let Err(error) = self.stop() {
                eprintln!(
                    "smoke recovery remains incomplete; preserve {}: {error}",
                    self.journal_path.display()
                );
            }
        }
    }

    struct Peer(JoinHandle<io::Result<()>>);
    impl Peer {
        fn finish(mut self, runtime: &Handle) -> io::Result<()> {
            runtime.block_on(async {
                timeout(IO_WAIT, &mut self.0)
                    .await
                    .map_err(io::Error::other)?
                    .map_err(io::Error::other)?
            })
        }
    }
    impl Drop for Peer {
        fn drop(&mut self) {
            self.0.abort();
        }
    }

    fn payload(size: usize) -> Vec<u8> {
        (0..size).map(|index| (index % 251) as u8).collect()
    }

    fn own(ipv6: bool) -> IpAddr {
        if ipv6 { OWN_V6.into() } else { OWN_V4.into() }
    }
    fn dns_address(ipv6: bool) -> SocketAddr {
        SocketAddr::new(
            if ipv6 {
                DNS_IPV6.into()
            } else {
                DNS_IPV4.into()
            },
            53,
        )
    }

    fn local_udp(ipv6: bool) -> io::Result<std::net::UdpSocket> {
        let deadline = Instant::now() + IO_WAIT;
        loop {
            match std::net::UdpSocket::bind(SocketAddr::new(own(ipv6), 0)) {
                Ok(socket) => {
                    socket.set_read_timeout(Some(IO_WAIT))?;
                    socket.set_write_timeout(Some(IO_WAIT))?;
                    return Ok(socket);
                }
                Err(error) if Instant::now() >= deadline => return Err(error),
                Err(_) => thread::sleep(Duration::from_millis(50)),
            }
        }
    }

    fn dns_roundtrip(fake: IpAddr, request: &[u8]) -> io::Result<()> {
        let ipv6 = fake.is_ipv6();
        let socket = local_udp(ipv6)?;
        let remote = dns_address(ipv6);
        require(
            socket.send_to(request, remote)? == request.len(),
            "short DNS send",
        )?;
        let mut response = [0u8; 4096];
        let (length, sender) = socket.recv_from(&mut response)?;
        require(sender == remote, "DNS response endpoint changed")?;
        require(
            answer_ip(request, &response[..length], ipv6)? == fake,
            "Windows DNS path returned another fake identity",
        )
    }

    fn tcp_roundtrip(runtime: &Handle, fake: IpAddr) -> io::Result<()> {
        let ipv6 = fake.is_ipv6();
        let real = SocketAddr::new(
            if ipv6 {
                Ipv6Addr::LOCALHOST.into()
            } else {
                Ipv4Addr::LOCALHOST.into()
            },
            0,
        );
        let listener = runtime.block_on(tokio::net::TcpListener::bind(real))?;
        let destination = SocketAddr::new(fake, listener.local_addr()?.port());
        let peer = Peer(runtime.spawn(async move {
            timeout(IO_WAIT, async {
                let (mut stream, source) = listener.accept().await?;
                require(
                    source.ip().is_loopback(),
                    "Core TCP egress did not use loopback",
                )?;
                let mut received = Vec::new();
                (&mut stream)
                    .take((TCP_BYTES + 1) as u64)
                    .read_to_end(&mut received)
                    .await?;
                require(
                    received == payload(TCP_BYTES),
                    "TCP request bytes or client FIN lost",
                )?;
                stream.write_all(&received).await?;
                stream.write_all(b"reply-after-client-fin").await?;
                stream.shutdown().await
            })
            .await
            .map_err(io::Error::other)?
        }));
        let mut client = std::net::TcpStream::connect_timeout(&destination, IO_WAIT)?;
        client.set_read_timeout(Some(IO_WAIT))?;
        client.set_write_timeout(Some(IO_WAIT))?;
        require(
            client.local_addr()?.ip() == own(ipv6),
            "Windows TCP did not select the owned TUN address",
        )?;
        client.write_all(&payload(TCP_BYTES))?;
        client.shutdown(Shutdown::Write)?;
        let mut response = Vec::new();
        (&mut client)
            .take((TCP_BYTES + 64) as u64)
            .read_to_end(&mut response)?;
        let mut expected = payload(TCP_BYTES);
        expected.extend_from_slice(b"reply-after-client-fin");
        require(
            response == expected,
            "TCP response bytes or half-close semantics lost",
        )?;
        peer.finish(runtime)
    }

    fn udp_roundtrip(runtime: &Handle, fake: IpAddr) -> io::Result<()> {
        let ipv6 = fake.is_ipv6();
        let real = SocketAddr::new(
            if ipv6 {
                Ipv6Addr::LOCALHOST.into()
            } else {
                Ipv4Addr::LOCALHOST.into()
            },
            0,
        );
        let server = runtime.block_on(tokio::net::UdpSocket::bind(real))?;
        let destination = SocketAddr::new(fake, server.local_addr()?.port());
        let peer = Peer(runtime.spawn(async move {
            timeout(IO_WAIT, async {
                let mut buffer = [0u8; UDP_BYTES + 1];
                for size in [0, UDP_BYTES] {
                    let (length, source) = server.recv_from(&mut buffer).await?;
                    require(
                        source.ip().is_loopback(),
                        "Core UDP egress did not use loopback",
                    )?;
                    require(
                        buffer[..length] == payload(size),
                        "UDP request boundary or contents changed",
                    )?;
                    require(
                        server.send_to(&buffer[..length], source).await? == length,
                        "short UDP echo",
                    )?;
                }
                Ok(())
            })
            .await
            .map_err(io::Error::other)?
        }));
        let client = local_udp(ipv6)?;
        for size in [0, UDP_BYTES] {
            let message = payload(size);
            require(
                client.send_to(&message, destination)? == size,
                "short UDP client send",
            )?;
            let mut buffer = [0u8; UDP_BYTES + 1];
            let (length, source) = client.recv_from(&mut buffer)?;
            require(
                source == destination,
                "UDP reply did not preserve its fake source endpoint",
            )?;
            require(
                buffer[..length] == message,
                "UDP response boundary or contents changed",
            )?;
        }
        peer.finish(runtime)
    }

    fn sorted_routes(mut routes: Vec<SystemRoute>) -> Vec<SystemRoute> {
        routes.sort_by_key(|route| {
            (
                route.interface_index,
                route.destination.to_string(),
                route.next_hop.to_string(),
                route.metric,
            )
        });
        routes
    }

    pub fn run(driver: PathBuf) -> io::Result<()> {
        require(driver.is_absolute(), "driver path must be absolute")?;
        let directory = windows_network::secure_state_directory()?;
        let before = windows_network::snapshot()?;
        let (owner, guid) = nonce()?;
        let dns = TunDns::new(
            FakeIpStore::open(&directory.join(format!("smoke-{owner}.fake-ip.jsonl")), 8)
                .map_err(io::Error::other)?,
        );
        let mut core = Core::start(
            runtime_config()?,
            "a1000000-0000-4000-8000-000000000001".into(),
            1,
            "b1000000-0000-4000-8000-000000000001".into(),
        )
        .map_err(io::Error::other)?;
        let dispatcher = core.flow_dispatcher().map_err(io::Error::other)?;
        let runtime = dispatcher.runtime_handle();
        // This guard permits only explicit loopback Core outbounds. It proves
        // the fixture never needs an external bootstrap but does not exercise
        // physical-interface pinning or a full-tunnel routing configuration.
        let binding = EgressLease::acquire_suspended()?;
        let packet = native_tun::spawn(
            dispatcher.clone(),
            dns.clone(),
            TunConfig {
                mtu: MTU as usize,
                max_tcp_flows: 8,
                max_udp_endpoints: 8,
                ..TunConfig::default()
            },
        )
        .map_err(io::Error::other)?;
        let requests = [query(HOST_V4, false), query(HOST_V6, true)];
        let lookup = Lookup(dispatcher);
        let mut fake = [
            IpAddr::V4(Ipv4Addr::UNSPECIFIED),
            IpAddr::V6(Ipv6Addr::UNSPECIFIED),
        ];
        for index in 0..2 {
            let response = runtime
                .block_on(dns.answer(&requests[index], &lookup))
                .map_err(io::Error::other)?;
            fake[index] = answer_ip(&requests[index], &response, index == 1)?;
            require(
                runtime
                    .block_on(dns.target_host(fake[index]))
                    .map_err(io::Error::other)?
                    == [HOST_V4, HOST_V6][index],
                "fake identity did not retain the host",
            )?;
        }
        eprintln!("Wintun smoke: creating an owned adapter and applying exact test routes");
        let mut run = DeviceRun::start(
            driver,
            &directory,
            (owner, guid),
            packet,
            runtime.clone(),
            fake,
            binding,
        )?;
        let tests = (|| {
            for index in 0..2 {
                let family = if index == 0 { 4 } else { 6 };
                eprintln!("Wintun smoke: IPv{family} DNS identity");
                dns_roundtrip(fake[index], &requests[index])?;
                eprintln!("Wintun smoke: IPv{family} TCP payload and half-close");
                tcp_roundtrip(&runtime, fake[index])?;
                eprintln!("Wintun smoke: IPv{family} empty and full UDP datagrams");
                udp_roundtrip(&runtime, fake[index])?;
            }
            require(
                !run.failed.load(Ordering::Acquire),
                "Wintun packet pump failed",
            )?;
            require(
                run.read_packets.load(Ordering::Relaxed) > 0
                    && run.written_packets.load(Ordering::Relaxed) > 0,
                "driver did not transfer real packets",
            )
        })();
        eprintln!("Wintun smoke: restoring owned network state");
        let restored = run.stop();
        if let Err(error) = restored {
            return Err(io::Error::other(format!(
                "test result: {tests:?}; recovery failed: {error}"
            )));
        }
        tests?;
        let stats = run.stats.snapshot();
        require(
            stats.active_tcp_flows == 0 && stats.active_udp_endpoints == 0,
            "packet resources survived shutdown",
        )?;
        let after = windows_network::snapshot()?;
        require(
            sorted_routes(before.routes) == sorted_routes(after.routes),
            "unrelated default/split-default routes changed",
        )?;
        require(
            !after
                .adapters
                .iter()
                .any(|adapter| adapter.identity.guid == run.journal.interface.guid),
            "owned Wintun adapter survived shutdown",
        )?;
        core.stop();
        println!(
            "{}",
            json!({
                "ok":true,"evidence":"Windows Wintun scoped loopback smoke",
                "source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),
                "driver_version":"0.14.1","driver_sha256":official_driver_sha256()?,
                "interface_index":run.journal.interface.index,
                "dns_a":true,"dns_aaaa":true,"tcp_ipv4":true,"tcp_ipv6":true,
                "tcp_payload_bytes_each_family":TCP_BYTES,"tcp_reply_after_client_fin":true,
                "udp_ipv4":true,"udp_ipv6":true,"udp_payload_lengths":[0,UDP_BYTES],
                "wintun_received_packets":run.read_packets.load(Ordering::Relaxed),
                "wintun_sent_packets":run.written_packets.load(Ordering::Relaxed),
                "owned_network_state_restored":true,"adapter_removed":true,
                "default_routes_unchanged":true,"physical_dns_modified":false,
                "firewall_modified":false,"windows_11_application_acceptance":false
            })
        );
        Ok(())
    }
}
