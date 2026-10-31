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
#[path = "support/nonblocking_fixture_socket.rs"]
mod nonblocking_fixture_socket;

#[cfg(windows)]
mod windows {
    use super::nonblocking_fixture_socket::{clone_listener_for_tokio, clone_udp_for_tokio};
    use super::*;
    use base64::Engine;
    use ring::rand::{SecureRandom, SystemRandom};
    use serde_json::json;
    use smoltcp::wire::{IpProtocol, Ipv4Packet, Ipv6Packet, TcpPacket};
    use std::{
        collections::BTreeMap,
        future::Future,
        io::{Read, Write},
        net::{IpAddr, Ipv4Addr, Ipv6Addr, Shutdown, SocketAddr},
        path::Path,
        pin::Pin,
        sync::{
            Arc, Mutex,
            atomic::{AtomicBool, AtomicU64, Ordering},
        },
        thread,
        time::{Duration, Instant},
    };
    use swirl_api::native_tun::{self, BridgeControl, PacketBridge};
    use swirl_core::v2::{Core, DurableReceipt, FlowDispatcher, RuntimeConfig};
    use swirl_dns::tun::{ANSWER_TTL, DNS_IPV4, DNS_IPV6, FakeIpStore, TunDns, TunLookup};
    use swirl_platform::{
        network_transaction::{
            self as transaction, FileJournalStore, InterfaceIdentity, Journal, NetworkBackend,
            Resource, Value,
        },
        windows_network::{self, SystemRoute, WindowsNetworkBackend},
        wintun_device::{WintunConfig, WintunDevice, official_driver_sha256},
    };
    use swirl_subscription::{
        Dns, DnsTlsServer, HostMapping, Limits, Matcher, Node, Outbound, Tls,
        v2::{
            ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, Mode, PolicyDocument, PolicyRule,
            Target,
        },
    };
    use swirl_transport::egress::EgressLease;
    use swirl_tun::{TunConfig, TunStats};
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        runtime::Handle,
        task::JoinHandle,
        time::timeout,
    };
    use tokio_rustls::{
        TlsAcceptor,
        rustls::{
            ServerConfig,
            pki_types::{CertificateDer, PrivatePkcs8KeyDer},
        },
    };

    const IO_WAIT: Duration = Duration::from_secs(15);
    const MTU: u32 = 1500;
    const TCP_BYTES: usize = 256 * 1024;
    const UDP_BYTES: usize = 1200;
    const REUSE_ROUNDS: usize = 64;
    const REUSE_BYTES: usize = 4096;
    const STORE_ID: &str = "a1000000-0000-4000-8000-000000000001";
    const NODE_ID: &str = "c1000000-0000-4000-8000-000000000001";
    const HOST_V4: &str = "ipv4.wintun.smoke.invalid";
    const HOST_V6: &str = "ipv6.wintun.smoke.invalid";
    const OWN_V4: Ipv4Addr = Ipv4Addr::new(198, 18, 0, 1);
    const OWN_V6: Ipv6Addr = Ipv6Addr::new(0xfd53, 0x7769, 0x726c, 0, 0, 0, 0, 1);
    type TcpTuple = (SocketAddr, SocketAddr);

    fn reset_tuple(bytes: &[u8]) -> Option<TcpTuple> {
        let (source, destination, protocol, payload) = match bytes.first()? >> 4 {
            4 => {
                let packet = Ipv4Packet::new_checked(bytes).ok()?;
                (
                    IpAddr::V4(packet.src_addr()),
                    IpAddr::V4(packet.dst_addr()),
                    packet.next_header(),
                    packet.payload(),
                )
            }
            6 => {
                let packet = Ipv6Packet::new_checked(bytes).ok()?;
                (
                    IpAddr::V6(packet.src_addr()),
                    IpAddr::V6(packet.dst_addr()),
                    packet.next_header(),
                    packet.payload(),
                )
            }
            _ => return None,
        };
        if protocol != IpProtocol::Tcp {
            return None;
        }
        let tcp = TcpPacket::new_checked(payload).ok()?;
        tcp.rst().then(|| {
            (
                SocketAddr::new(source, tcp.src_port()),
                SocketAddr::new(destination, tcp.dst_port()),
            )
        })
    }

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
                id: NODE_ID.into(),
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
                    target: Target::Node { id: NODE_ID.into() },
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
            u32::from_be_bytes(answer[6..10].try_into().map_err(io::Error::other)?) == ANSWER_TTL,
            "DNS answer TTL changed",
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
        bridge_stats: Arc<native_tun::BridgeStats>,
        reader: Option<thread::JoinHandle<()>>,
        writer: Option<JoinHandle<()>>,
        closing: Arc<AtomicBool>,
        failed: Arc<AtomicBool>,
        read_packets: Arc<AtomicU64>,
        written_packets: Arc<AtomicU64>,
        reset_packets: Arc<Mutex<Vec<TcpTuple>>>,
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
            // Capture the actual Windows values before Journal::prepare can
            // reject them. These reads are limited to this temporary adapter;
            // they do not dump physical-network or user configuration.
            for (resource, requested) in &desired {
                let observed = backend.read(&identity, resource)?;
                eprintln!(
                    "Wintun smoke: pre-validation snapshot {}",
                    json!({"resource": resource, "observed": observed, "requested": requested})
                );
            }
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
                bridge_stats: packet.bridge_stats,
                reader: None,
                writer: None,
                closing: Arc::new(AtomicBool::new(false)),
                failed: Arc::new(AtomicBool::new(false)),
                read_packets: Arc::new(AtomicU64::new(0)),
                written_packets: Arc::new(AtomicU64::new(0)),
                reset_packets: Arc::new(Mutex::new(Vec::new())),
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
            let resets = run.reset_packets.clone();
            run.reader = Some(
                thread::Builder::new()
                    .name("swirl-smoke-wintun-read".into())
                    .spawn(move || {
                        while !closing.load(Ordering::Acquire) {
                            let mut bytes = Vec::with_capacity(MTU as usize);
                            match reader_device.receive_blocking(&mut bytes) {
                                Ok(()) if bytes.len() <= MTU as usize => {
                                    count.fetch_add(1, Ordering::Relaxed);
                                    if let Some(tuple) = reset_tuple(&bytes) {
                                        match resets.lock() {
                                            Ok(mut observed) if observed.len() < 64 => {
                                                observed.push(tuple)
                                            }
                                            _ => {
                                                failed.store(true, Ordering::Release);
                                                break;
                                            }
                                        }
                                    }
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
                Ok(report) if report.conflicts.is_empty() && self.journal.is_restored() => {
                    eprintln!("Wintun smoke: recovery report {}", json!(report));
                }
                Ok(report) => errors.push(format!(
                    "network recovery conflicts: {:?}",
                    report.conflicts
                )),
                Err(error) => errors.push(format!("network recovery: {error}")),
            }
            // Read back before closing the adapter: deleting the interface is
            // not proof that its MTU or any other before value was restored.
            // These are only this smoke's six owned resources, never a dump of
            // the runner's physical network configuration.
            for change in &self.journal.changes {
                match self.backend.read(&self.journal.interface, &change.resource) {
                    Ok(observed) => {
                        let exact = observed == change.before;
                        eprintln!(
                            "Wintun smoke: restored raw state {}",
                            json!({"resource":change.resource,"before":change.before,
                                "observed":observed,"exact":exact,"state":change.state})
                        );
                        if !exact {
                            errors.push(format!(
                                "restored value differs from original {:?}",
                                change.resource
                            ));
                        }
                    }
                    Err(error) => {
                        errors.push(format!("recovery readback {:?}: {error}", change.resource))
                    }
                }
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
        fn spawn<F>(runtime: &Handle, label: impl Into<String>, work: F) -> Self
        where
            F: Future<Output = io::Result<()>> + Send + 'static,
        {
            let label = label.into();
            Self(runtime.spawn(async move {
                let result = work.await;
                if let Err(error) = &result {
                    // A client can observe the resulting reset and return
                    // before finish(). Preserve the originating fixture error.
                    eprintln!("Wintun smoke: peer failure [{label}]: {error}");
                }
                result
            }))
        }

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

    fn apply_policy(core: &Core, directory: &Path, candidate: RuntimeConfig) -> io::Result<()> {
        let current = core.configuration().map_err(io::Error::other)?;
        let revision = current["applied_revision"]
            .as_str()
            .ok_or_else(|| io::Error::other("missing applied revision"))?
            .parse::<u64>()
            .map_err(io::Error::other)?;
        let generation = current["generation"]
            .as_str()
            .ok_or_else(|| io::Error::other("missing generation"))?
            .parse::<u64>()
            .map_err(io::Error::other)?;
        let next = revision + 1;
        let request = format!("d1000000-0000-4000-8000-{next:012x}");
        let prepared = core
            .prepare(
                request.clone(),
                STORE_ID,
                revision,
                next,
                generation,
                revision,
                candidate.clone(),
                vec![],
            )
            .map_err(io::Error::other)?;
        let token = prepared["prepared_token"]
            .as_str()
            .ok_or_else(|| io::Error::other("missing prepared token"))?;
        let digest = prepared["plan_digest"]
            .as_str()
            .ok_or_else(|| io::Error::other("missing plan digest"))?;
        core.activate(&request, token, digest, generation, next)
            .map_err(io::Error::other)?;
        let receipt = DurableReceipt {
            store_id: STORE_ID.into(),
            request_id: request.clone(),
            saved_revision: next.to_string(),
            plan_digest: digest.into(),
        };
        // Use the actual V2 admission transaction, including a synced fixture
        // receipt, rather than replacing a dispatcher or bypassing finish().
        let (id, _) = nonce()?;
        let mut saved = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(directory.join(format!("smoke-policy-{id}.json")))?;
        saved.write_all(
            &serde_json::to_vec(&json!({"runtime":candidate,"receipt":receipt}))
                .map_err(io::Error::other)?,
        )?;
        saved.sync_all()?;
        drop(saved);
        let finished = core
            .finish(&request, token, receipt)
            .map_err(io::Error::other)?;
        require(
            finished["outcome"] == "applied",
            "policy transaction not applied",
        )
    }

    fn loopback(ipv6: bool) -> IpAddr {
        if ipv6 {
            Ipv6Addr::LOCALHOST.into()
        } else {
            Ipv4Addr::LOCALHOST.into()
        }
    }

    /// A real encrypted resolver for the policy controls below. Unlike static
    /// hosts, a resolved answer does not preselect the built-in LAN/direct rule.
    /// Thus both PROXY/REJECT and a reachable DIRECT control can target exactly
    /// the same hostname, port and listening socket.
    fn dns_fixture(runtime: &Handle) -> io::Result<(Dns, Peer, Arc<AtomicU64>)> {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../swirl-transport/tests/fixtures/reality_auth.json"
        ))
        .map_err(io::Error::other)?;
        let decode = |field: &str| -> io::Result<Vec<u8>> {
            let encoded = fixture["certificate"][field]
                .as_str()
                .ok_or_else(|| io::Error::other("missing fixture certificate field"))?;
            require(encoded.len() % 2 == 0, "odd fixture certificate hex")?;
            encoded
                .as_bytes()
                .as_chunks::<2>()
                .0
                .iter()
                .map(|pair| {
                    u8::from_str_radix(std::str::from_utf8(pair).map_err(io::Error::other)?, 16)
                        .map_err(io::Error::other)
                })
                .collect()
        };
        let certificate = decode("ordinary_self_signed_der_hex")?;
        let server = ServerConfig::builder()
            .with_no_client_auth()
            .with_single_cert(
                vec![CertificateDer::from(certificate.clone())],
                PrivatePkcs8KeyDer::from(decode("ed25519_pkcs8_der_hex")?).into(),
            )
            .map_err(io::Error::other)?;
        let acceptor = TlsAcceptor::from(Arc::new(server));
        let listener = runtime.block_on(tokio::net::TcpListener::bind("127.0.0.1:0"))?;
        let address = listener.local_addr()?;
        let queries = Arc::new(AtomicU64::new(0));
        let observed = queries.clone();
        let peer = Peer::spawn(runtime, "DoT A/AAAA resolver", async move {
            loop {
                let (stream, source) = listener.accept().await?;
                require(
                    source.ip().is_loopback(),
                    "DoT fixture received non-loopback client",
                )?;
                timeout(IO_WAIT, async {
                    let mut stream = acceptor.accept(stream).await?;
                    // The production DoT resolver sends A then AAAA on this
                    // same verified TLS connection, not separate sockets.
                    for expected_v6 in [false, true] {
                        let length = usize::from(stream.read_u16().await?);
                        require((12..=4096).contains(&length), "DoT fixture query length")?;
                        let mut request = vec![0; length];
                        stream.read_exact(&mut request).await?;
                        let mut selected = None;
                        for (host, ipv6) in [(HOST_V4, false), (HOST_V6, true)] {
                            for q6 in [false, true] {
                                let expected = query(host, q6);
                                if request[4..] == expected[4..] {
                                    selected = Some((ipv6, q6));
                                }
                            }
                        }
                        let (host_v6, query_v6) = selected
                            .ok_or_else(|| io::Error::other("unexpected DoT fixture question"))?;
                        require(query_v6 == expected_v6, "DoT family order changed")?;
                        let mut reply = request;
                        reply[2..4].copy_from_slice(&[0x81, 0x80]);
                        if host_v6 == query_v6 {
                            reply[6..8].copy_from_slice(&[0, 1]);
                            reply.extend_from_slice(&[0xc0, 0x0c]);
                            reply.extend_from_slice(if query_v6 {
                                &[0, 28, 0, 1]
                            } else {
                                &[0, 1, 0, 1]
                            });
                            reply.extend_from_slice(&ANSWER_TTL.to_be_bytes());
                            if query_v6 {
                                reply.extend_from_slice(&[0, 16]);
                                reply.extend_from_slice(&Ipv6Addr::LOCALHOST.octets());
                            } else {
                                reply.extend_from_slice(&[0, 4]);
                                reply.extend_from_slice(&Ipv4Addr::LOCALHOST.octets());
                            }
                        }
                        observed.fetch_add(1, Ordering::AcqRel);
                        stream.write_u16(reply.len() as u16).await?;
                        stream.write_all(&reply).await?;
                        stream.flush().await?;
                    }
                    stream.shutdown().await
                })
                .await
                .map_err(io::Error::other)??;
            }
        });
        Ok((
            Dns {
                tls_servers: vec![DnsTlsServer {
                    address,
                    tls: Tls {
                        server_name: "reality.test".into(),
                        alpn: vec![],
                        ca_der_base64: Some(
                            base64::engine::general_purpose::STANDARD.encode(certificate),
                        ),
                    },
                    https_path: None,
                }],
                hosts: vec![],
                use_system_hosts: false,
                ..Dns::default()
            },
            peer,
            queries,
        ))
    }

    fn no_tcp_accept(listener: &std::net::TcpListener) -> io::Result<()> {
        match listener.accept() {
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => Ok(()),
            Err(error) => Err(error),
            Ok(_) => Err(io::Error::other(
                "forbidden DIRECT/unused proxy listener accepted traffic",
            )),
        }
    }

    fn flow_ended(
        core: &Core,
        baseline: u64,
        host: &str,
        port: u16,
        category: &str,
        error: &str,
    ) -> io::Result<()> {
        let deadline = Instant::now() + IO_WAIT;
        loop {
            let snapshot = core.snapshot().map_err(io::Error::other)?;
            let records = snapshot["connections"]
                .as_array()
                .ok_or_else(|| io::Error::other("missing Core flow records"))?;
            let matches = records
                .iter()
                .filter(|row| {
                    row["id"].as_u64().is_some_and(|id| id > baseline)
                        && row["host"] == host
                        && row["port"] == port
                })
                .collect::<Vec<_>>();
            let diagnose = || {
                let observed = matches
                    .iter()
                    .map(|row| {
                        json!({"id":row["id"],"category":row["category"],
                            "error":row["error"],"node":row["node"],"ended":row["ended"]})
                    })
                    .collect::<Vec<_>>();
                eprintln!(
                    "Wintun smoke: Core flow assertion {}",
                    json!({"host":host,"port":port,"baseline":baseline,
                        "expected":{"category":category,"error":error,
                            "node":(category == "proxy").then_some(NODE_ID)},
                        "observed":observed})
                );
            };
            if matches.len() > 1 {
                diagnose();
                return Err(io::Error::other(
                    "one native flow produced multiple Core admissions",
                ));
            }
            if let Some(row) = matches.first()
                && row["ended"] == true
            {
                if row["category"] != category
                    || row["error"] != error
                    || (category == "proxy" && row["node"] != NODE_ID)
                {
                    diagnose();
                }
                require(
                    row["category"] == category,
                    "Core selected an unexpected route category",
                )?;
                require(
                    row["error"] == error,
                    "Core did not preserve the exact flow result",
                )?;
                if category == "proxy" {
                    require(
                        row["node"] == NODE_ID,
                        "Core switched away from selected proxy",
                    )?;
                }
                return Ok(());
            }
            if Instant::now() >= deadline {
                diagnose();
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Core flow did not reach its expected terminal record",
                ));
            }
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn accepted_count(core: &Core) -> io::Result<u64> {
        core.snapshot().map_err(io::Error::other)?["accepted"]
            .as_u64()
            .ok_or_else(|| io::Error::other("missing Core admission count"))
    }

    fn direct_trap_control(
        core: &Core,
        directory: &Path,
        runtime: &Handle,
        mut config: RuntimeConfig,
        fake: IpAddr,
        listener: std::net::TcpListener,
    ) -> io::Result<()> {
        config.policy.mode = Mode::Direct;
        apply_policy(core, directory, config)?;
        let port = listener.local_addr()?.port();
        let baseline = accepted_count(core)?;
        let label = format!(
            "IPv{} DIRECT trap control",
            if fake.is_ipv6() { 6 } else { 4 }
        );
        let peer = Peer::spawn(runtime, label, async move {
            timeout(IO_WAIT, async {
                let listener = tokio::net::TcpListener::from_std(listener)?;
                let (mut stream, source) = listener.accept().await?;
                require(
                    source.ip().is_loopback(),
                    "DIRECT control did not resolve to loopback",
                )?;
                let mut message = [0; 4];
                stream.read_exact(&mut message).await?;
                require(&message == b"trap", "DIRECT control payload changed")?;
                stream.write_all(b"live").await?;
                stream.shutdown().await
            })
            .await
            .map_err(io::Error::other)?
        });
        let mut client =
            std::net::TcpStream::connect_timeout(&SocketAddr::new(fake, port), IO_WAIT)?;
        client.set_read_timeout(Some(IO_WAIT))?;
        client.set_write_timeout(Some(IO_WAIT))?;
        require(
            client.local_addr()?.ip() == own(fake.is_ipv6()),
            "DIRECT control bypassed owned TUN source",
        )?;
        client.write_all(b"trap")?;
        client.shutdown(Shutdown::Write)?;
        let mut message = Vec::new();
        (&mut client).take(5).read_to_end(&mut message)?;
        require(
            message == b"live",
            "DIRECT control was not reachable through Wintun",
        )?;
        peer.finish(runtime)?;
        flow_ended(
            core,
            baseline,
            if fake.is_ipv6() { HOST_V6 } else { HOST_V4 },
            port,
            "direct",
            "",
        )
    }

    fn proxy_peer(
        runtime: &Handle,
        listener: std::net::TcpListener,
        host: &'static str,
        port: u16,
        reject: bool,
    ) -> Peer {
        let label = format!("HTTP CONNECT host={host} port={port} reject={reject}");
        Peer::spawn(runtime, label, async move {
            timeout(IO_WAIT, async {
                let listener = tokio::net::TcpListener::from_std(listener)?;
                let (mut stream, source) = listener.accept().await?;
                require(
                    source.ip().is_loopback(),
                    "proxy fixture received non-loopback egress",
                )?;
                let mut header = Vec::new();
                while !header.ends_with(b"\r\n\r\n") {
                    require(header.len() < 8192, "oversized fixture CONNECT header")?;
                    header.push(stream.read_u8().await?);
                }
                require(
                    header
                        == format!("CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n")
                            .as_bytes(),
                    "native HTTP CONNECT changed target identity",
                )?;
                if reject {
                    stream
                        .write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                        .await?;
                    return stream.shutdown().await;
                }
                stream
                    .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    .await?;
                let mut received = Vec::new();
                (&mut stream)
                    .take((TCP_BYTES + 1) as u64)
                    .read_to_end(&mut received)
                    .await?;
                require(
                    received == payload(TCP_BYTES),
                    "native proxy payload or client FIN lost",
                )?;
                stream.write_all(&received).await?;
                stream.write_all(b"reply-after-client-fin").await?;
                stream.shutdown().await
            })
            .await
            .map_err(io::Error::other)?
        })
    }

    fn tcp_must_reset(destination: SocketAddr) -> io::Result<()> {
        let reset = |error: io::Error| -> io::Result<()> {
            if matches!(
                error.kind(),
                io::ErrorKind::ConnectionReset
                    | io::ErrorKind::ConnectionAborted
                    | io::ErrorKind::ConnectionRefused
                    | io::ErrorKind::BrokenPipe
            ) {
                Ok(())
            } else {
                Err(io::Error::other(format!(
                    "expected rejected TCP flow/reset, observed {error}"
                )))
            }
        };
        let mut client = match std::net::TcpStream::connect_timeout(&destination, IO_WAIT) {
            Ok(client) => client,
            Err(error) => return reset(error),
        };
        client.set_read_timeout(Some(IO_WAIT))?;
        client.set_write_timeout(Some(IO_WAIT))?;
        require(
            client.local_addr()?.ip() == own(destination.is_ipv6()),
            "rejection probe bypassed Wintun",
        )?;
        if let Err(error) = client.write_all(b"must-not-forward") {
            return reset(error);
        }
        let mut response = [0; 1];
        match client.read(&mut response) {
            Err(error) => reset(error),
            Ok(size) => Err(io::Error::other(format!(
                "rejected flow returned {size} bytes or graceful EOF instead of reset"
            ))),
        }
    }

    fn policy_roundtrips(
        core: &Core,
        directory: &Path,
        runtime: &Handle,
        fake: [IpAddr; 2],
    ) -> io::Result<()> {
        let (encrypted_dns, _dns_peer, dns_queries) = dns_fixture(runtime)?;
        // First prove the real DoT fixture can resolve both families with TLS
        // verification. The Core subsequently builds its own uncached resolver.
        let resolver = swirl_dns::Resolver::default()
            .with_config(&encrypted_dns)
            .map_err(io::Error::other)?;
        for (index, host) in [HOST_V4, HOST_V6].iter().enumerate() {
            let addresses = runtime
                .block_on(resolver.resolve(host, 443))
                .map_err(io::Error::other)?;
            require(
                addresses == vec![SocketAddr::new(loopback(index == 1), 443)],
                "DoT fixture did not return the exact reachable target family",
            )?;
        }
        eprintln!("Wintun smoke: PASS verified DoT A/AAAA resolver fixture");
        for (index, host) in [HOST_V4, HOST_V6].into_iter().enumerate() {
            let ipv6 = index == 1;
            let family = if ipv6 { 6 } else { 4 };
            for case in ["proxy", "reject", "proxy_rejected", "proxy_unavailable"] {
                eprintln!("Wintun smoke: IPv{family} {case} with reachable DIRECT controls");
                let trap = std::net::TcpListener::bind(SocketAddr::new(loopback(ipv6), 0))?;
                trap.set_nonblocking(true)?;
                let port = trap.local_addr()?.port();
                let proxy = std::net::TcpListener::bind(SocketAddr::new(loopback(ipv6), 0))?;
                proxy.set_nonblocking(true)?;
                // Keep the unused port bound for the entire case without
                // listening. No race with another process reusing a dropped
                // listener is permitted in the connection-refused fixture.
                let unavailable = if case == "proxy_unavailable" {
                    let socket = if ipv6 {
                        tokio::net::TcpSocket::new_v6()?
                    } else {
                        tokio::net::TcpSocket::new_v4()?
                    };
                    socket.bind(SocketAddr::new(loopback(ipv6), 0))?;
                    Some(socket)
                } else {
                    None
                };
                let proxy_address = match &unavailable {
                    Some(socket) => socket.local_addr()?,
                    None => proxy.local_addr()?,
                };
                if unavailable.is_some() {
                    match std::net::TcpStream::connect_timeout(&proxy_address, IO_WAIT) {
                        Err(error) if error.kind() == io::ErrorKind::ConnectionRefused => {}
                        Err(error) => {
                            return Err(io::Error::other(format!(
                                "unavailable proxy fixture did not refuse: {error}"
                            )));
                        }
                        Ok(_) => {
                            return Err(io::Error::other(
                                "unavailable proxy fixture unexpectedly accepted TCP",
                            ));
                        }
                    }
                }
                let mut config = runtime_config()?;
                config.dns = encrypted_dns.clone();
                config.nodes[0].outbound = Outbound::HttpConnect {
                    host: proxy_address.ip().to_string(),
                    port: proxy_address.port(),
                    auth: None,
                    tls: None,
                };
                direct_trap_control(
                    core,
                    directory,
                    runtime,
                    config.clone(),
                    fake[index],
                    clone_listener_for_tokio(&trap)?,
                )?;
                no_tcp_accept(&trap)?;
                config.policy.mode = if case == "reject" {
                    Mode::Rule
                } else {
                    Mode::Global
                };
                if case == "reject" {
                    // Release executables do not use the development fallback
                    // for bundled rules. Use the repository's existing pinned
                    // MRS assets explicitly; no special rule set is invented.
                    config.china_rules_directory = Some(
                        Path::new(env!("CARGO_MANIFEST_DIR"))
                            .join("../../../src/Swirl.Quick/packaging/rules")
                            .canonicalize()?
                            .to_str()
                            .ok_or_else(|| io::Error::other("MRS fixture path is not UTF-8"))?
                            .into(),
                    );
                    config.policy.custom_rules.push(PolicyRule {
                        id: "e1000000-0000-4000-8000-000000000001".into(),
                        name: "Reject owned Wintun smoke targets".into(),
                        enabled: true,
                        priority: 0,
                        matcher: Matcher::DomainSuffix {
                            value: "wintun.smoke.invalid".into(),
                        },
                        target: Target::Reject {},
                    });
                }
                apply_policy(core, directory, config.clone())?;
                let baseline = accepted_count(core)?;
                let queries_before = dns_queries.load(Ordering::Acquire);
                let peer = if matches!(case, "reject" | "proxy_unavailable") {
                    None
                } else {
                    Some(proxy_peer(
                        runtime,
                        clone_listener_for_tokio(&proxy)?,
                        host,
                        port,
                        case == "proxy_rejected",
                    ))
                };
                let destination = SocketAddr::new(fake[index], port);
                if case == "proxy" {
                    tcp_client_roundtrip(destination)?;
                } else {
                    tcp_must_reset(destination)?;
                }
                if let Some(peer) = peer {
                    peer.finish(runtime)?;
                }
                let (category, error) = match case {
                    "proxy" => ("proxy", ""),
                    "reject" => ("reject", "Rejected"),
                    "proxy_rejected" => ("proxy", "UpstreamRejected"),
                    _ => ("proxy", "UpstreamConnectionRefused"),
                };
                flow_ended(core, baseline, host, port, category, error)?;
                require(
                    dns_queries.load(Ordering::Acquire) == queries_before,
                    "proxy/reject path unexpectedly attempted direct DNS resolution",
                )?;
                no_tcp_accept(&trap)?;
                no_tcp_accept(&proxy)?;
                // Same name, port, DNS and still-open listener; only the policy
                // changes. This proves absence of an accept above was not an
                // unreachable or broken DIRECT trap.
                direct_trap_control(core, directory, runtime, config, fake[index], trap)?;
                eprintln!(
                    "Wintun smoke: PASS IPv{family} {case}, exact Core outcome and reachable DIRECT trap controls"
                );
            }
        }
        Ok(())
    }

    #[derive(Clone, Copy)]
    struct UdpOutcome {
        ended: bool,
        error: &'static str,
        bytes: u64,
    }

    fn udp_record(
        core: &Core,
        baseline: u64,
        source: SocketAddr,
        host: &str,
        port: u16,
        category: &str,
        expected: UdpOutcome,
    ) -> io::Result<serde_json::Value> {
        let deadline = Instant::now() + IO_WAIT;
        let node = match category {
            "direct" => "SWIRL_V2_DIRECT",
            "reject" => "SWIRL_V2_REJECT",
            "proxy" => NODE_ID,
            _ => return Err(io::Error::other("unexpected UDP evidence category")),
        };
        loop {
            let snapshot = core.snapshot().map_err(io::Error::other)?;
            let matches = snapshot["connections"]
                .as_array()
                .ok_or_else(|| io::Error::other("missing Core UDP records"))?
                .iter()
                .filter(|row| {
                    row["id"].as_u64().is_some_and(|id| id > baseline)
                        && row["host"] == host
                        && row["port"] == port
                })
                .collect::<Vec<_>>();
            let diagnose = || {
                eprintln!(
                    "Wintun smoke: UDP Core assertion {}",
                    json!({"host":host,"port":port,"source":source,"baseline":baseline,
                        "expected":{"category":category,"node":node,"ended":expected.ended,
                            "error":expected.error,"upload":expected.bytes,"download":expected.bytes},
                        "observed":matches})
                );
            };
            if matches.len() > 1 {
                diagnose();
                return Err(io::Error::other(
                    "one UDP tuple produced multiple Core admissions",
                ));
            }
            if let Some(row) = matches.first() {
                if row["source_ip"] != source.ip().to_string()
                    || row["source_port"] != source.port()
                    || row["category"] != category
                    || row["node"] != node
                {
                    diagnose();
                    return Err(io::Error::other(
                        "UDP Core source or selected route changed",
                    ));
                }
                if row["ended"] == true
                    || (!expected.ended
                        && row["upload"] == expected.bytes
                        && row["download"] == expected.bytes)
                {
                    if row["ended"] != expected.ended
                        || row["error"] != expected.error
                        || row["upload"] != expected.bytes
                        || row["download"] != expected.bytes
                    {
                        diagnose();
                        return Err(io::Error::other(
                            "UDP Core terminal state or counters changed",
                        ));
                    }
                    return Ok((*row).clone());
                }
            }
            if Instant::now() >= deadline {
                diagnose();
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "UDP Core evidence deadline",
                ));
            }
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn no_udp_receive(socket: &std::net::UdpSocket) -> io::Result<()> {
        socket.set_nonblocking(true)?;
        match socket.recv_from(&mut [0; UDP_BYTES + 1]) {
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => Ok(()),
            Err(error) => Err(error),
            Ok((length, _)) => Err(io::Error::other(format!(
                "forbidden UDP endpoint received {length} bytes, including empty datagrams"
            ))),
        }
    }

    fn udp_stage_error(
        core: &Core,
        run: &DeviceRun,
        context: &serde_json::Value,
        phase: &str,
        error: io::Error,
    ) -> io::Error {
        // Read evidence before teardown cancels the association. Only this
        // bounded fixture tuple is included, never the complete traffic log.
        let snapshot = core
            .snapshot()
            .unwrap_or_else(|error| json!({"snapshot_error":error}));
        let baseline = context["baseline"].as_u64().unwrap_or(u64::MAX);
        let rows = snapshot["connections"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|row| {
                row["id"].as_u64().is_some_and(|id| id > baseline)
                    && row["host"] == context["host"]
                    && row["port"] == context["port"]
            })
            .take(8)
            .collect::<Vec<_>>();
        let stats = run.stats.snapshot();
        eprintln!(
            "Wintun smoke: UDP stage failure {}",
            json!({"phase":phase,"context":context,"error":error.to_string(),
                "os_error":error.raw_os_error(),"kind":format!("{:?}",error.kind()),
                "core":{"active":snapshot["active"],"accepted":snapshot["accepted"],
                    "failed":snapshot["failed"],"rejected":snapshot["rejected"],
                    "last_error":snapshot["last_error"],"udp_dropped":snapshot["udp_dropped"],
                    "configuration":snapshot["configuration"],"connections":rows},
                "tun":{"received_packets":stats.received_packets,
                    "malformed_packets":stats.malformed_packets,
                    "dropped_udp_datagrams":stats.dropped_udp_datagrams,
                    "active_tcp_flows":stats.active_tcp_flows,
                    "active_udp_endpoints":stats.active_udp_endpoints},
                "bridge":{"udp_failures":run.bridge_stats.udp_failures.load(Ordering::Acquire),
                    "udp_dropped":run.bridge_stats.udp_dropped.load(Ordering::Acquire),
                    "tcp_failures":run.bridge_stats.tcp_failures.load(Ordering::Acquire),
                    "dns_failures":run.bridge_stats.dns_failures.load(Ordering::Acquire)},
                "wintun":{"received_packets":run.read_packets.load(Ordering::Acquire),
                    "sent_packets":run.written_packets.load(Ordering::Acquire),
                    "failed":run.failed.load(Ordering::Acquire)}})
        );
        io::Error::new(error.kind(), format!("{phase}: {error}"))
    }

    fn udp_direct_control(
        core: &Core,
        directory: &Path,
        runtime: &Handle,
        mut config: RuntimeConfig,
        fake: IpAddr,
        trap: &std::net::UdpSocket,
    ) -> io::Result<std::net::UdpSocket> {
        config.policy.mode = Mode::Direct;
        apply_policy(core, directory, config)?;
        let port = trap.local_addr()?.port();
        let baseline = accepted_count(core)?;
        let server = trap.try_clone()?;
        let peer = Peer::spawn(runtime, "UDP DIRECT trap control", async move {
            timeout(IO_WAIT, async {
                let server = tokio::net::UdpSocket::from_std(server)?;
                let mut buffer = [0; UDP_BYTES + 1];
                let (length, source) = server.recv_from(&mut buffer).await?;
                require(
                    source.ip().is_loopback(),
                    "UDP DIRECT control escaped loopback",
                )?;
                require(
                    &buffer[..length] == b"trap",
                    "UDP DIRECT trap received unexpected payload",
                )?;
                require(
                    server.send_to(b"live", source).await? == 4,
                    "short UDP DIRECT control reply",
                )
            })
            .await
            .map_err(io::Error::other)?
        });
        let client = local_udp(fake.is_ipv6())?;
        let destination = SocketAddr::new(fake, port);
        require(
            client.send_to(b"trap", destination)? == 4,
            "short UDP DIRECT control send",
        )?;
        let mut response = [0; UDP_BYTES + 1];
        let (length, sender) = client.recv_from(&mut response)?;
        require(
            sender == destination && &response[..length] == b"live",
            "UDP DIRECT control did not return through Wintun",
        )?;
        peer.finish(runtime)?;
        udp_record(
            core,
            baseline,
            client.local_addr()?,
            if fake.is_ipv6() { HOST_V6 } else { HOST_V4 },
            port,
            "direct",
            UdpOutcome {
                ended: false,
                error: "",
                bytes: 4,
            },
        )?;
        // Keep this Windows source port occupied: UDP has no FIN, and reusing
        // its five-tuple would intentionally retain the previous Core policy.
        Ok(client)
    }

    fn socks5_udp_peer(
        runtime: &Handle,
        listener: std::net::TcpListener,
        relay: std::net::UdpSocket,
        host: &'static str,
        port: u16,
        reject: bool,
    ) -> (Peer, tokio::sync::oneshot::Sender<()>) {
        let (close, closed) = tokio::sync::oneshot::channel();
        let peer = Peer::spawn(
            runtime,
            format!("SOCKS5 UDP host={host} reject={reject}"),
            async move {
                let started = Instant::now();
                let note_stage = |phase: &'static str| {
                    eprintln!(
                        "Wintun smoke: SOCKS5 UDP pending {}",
                        json!({"host":host,"port":port,"stage":phase})
                    );
                    phase
                };
                let mut stage = note_stage("register control listener and relay");
                let result = timeout(IO_WAIT, async {
                    let listener = tokio::net::TcpListener::from_std(listener)?;
                    let relay = tokio::net::UdpSocket::from_std(relay)?;
                    let address = relay.local_addr()?;
                    stage = note_stage("accept TCP control");
                    let (mut control, source) = listener.accept().await?;
                    eprintln!(
                        "Wintun smoke: SOCKS5 UDP stage {}",
                        json!({"host":host,"port":port,"stage":"control_accepted",
                            "source":source,"control_local":control.local_addr()?,"relay":address})
                    );
                    require(source.ip().is_loopback(), "SOCKS5 control escaped loopback")?;
                    let mut greeting = [0; 3];
                    stage = note_stage("read TCP greeting");
                    control.read_exact(&mut greeting).await?;
                    require(greeting == [5, 1, 0], "unexpected SOCKS5 UDP greeting")?;
                    stage = note_stage("write TCP greeting selection");
                    control.write_all(&[5, 0]).await?;
                    let mut command = [0; 4];
                    stage = note_stage("read TCP ASSOCIATE header");
                    control.read_exact(&mut command).await?;
                    require(
                        command == [5, 3, 0, if source.is_ipv6() { 4 } else { 1 }],
                        "SOCKS5 UDP ASSOCIATE command changed",
                    )?;
                    let mut unspecified = vec![0; if source.is_ipv6() { 18 } else { 6 }];
                    stage = note_stage("read TCP ASSOCIATE address and port");
                    control.read_exact(&mut unspecified).await?;
                    require(
                        unspecified.iter().all(|byte| *byte == 0),
                        "SOCKS5 association source request changed",
                    )?;
                    eprintln!(
                        "Wintun smoke: SOCKS5 UDP stage {}",
                        json!({"host":host,"port":port,"stage":"associate_request_validated",
                            "command":command,"address_bytes":unspecified.len()})
                    );
                    let mut reply = vec![5, if reject { 2 } else { 0 }, 0];
                    match address.ip() {
                        IpAddr::V4(ip) => {
                            reply.push(1);
                            reply.extend_from_slice(&ip.octets());
                        }
                        IpAddr::V6(ip) => {
                            reply.push(4);
                            reply.extend_from_slice(&ip.octets());
                        }
                    }
                    reply.extend_from_slice(&address.port().to_be_bytes());
                    stage = note_stage("write TCP ASSOCIATE reply");
                    control.write_all(&reply).await?;
                    eprintln!(
                        "Wintun smoke: SOCKS5 UDP stage {}",
                        json!({"host":host,"port":port,"stage":"associate_reply_written",
                            "reply_code":if reject { 2 } else { 0 },"relay":address})
                    );
                    if reject {
                        // A client may abort as soon as it reads the nonzero REP.
                        // The full denial is written; no UDP relay was admitted.
                        return Ok(());
                    }
                    let mut header = vec![0, 0, 0, 3, host.len() as u8];
                    header.extend_from_slice(host.as_bytes());
                    header.extend_from_slice(&port.to_be_bytes());
                    let mut original_source = None;
                    let mut buffer = vec![0; header.len() + UDP_BYTES + 1];
                    for size in [0, UDP_BYTES] {
                        stage = note_stage(if size == 0 {
                            "receive empty UDP relay datagram"
                        } else {
                            "receive full UDP relay datagram"
                        });
                        let (length, source) = relay.recv_from(&mut buffer).await?;
                        eprintln!(
                            "Wintun smoke: SOCKS5 UDP stage {}",
                            json!({"host":host,"port":port,"stage":"relay_received",
                                "source":source,"relay":address,"wire_bytes":length,
                                "expected_payload_bytes":size})
                        );
                        require(
                            source.ip().is_loopback() && source.is_ipv6() == address.is_ipv6(),
                            "SOCKS5 UDP relay source changed family or escaped loopback",
                        )?;
                        require(
                            original_source.is_none_or(|original| original == source),
                            "SOCKS5 UDP source changed during one association",
                        )?;
                        original_source = Some(source);
                        let expected = [header.as_slice(), &payload(size)].concat();
                        require(
                            buffer[..length] == expected,
                            "SOCKS5 UDP target, empty boundary or payload changed",
                        )?;
                        stage = note_stage(if size == 0 {
                            "send empty UDP relay reply"
                        } else {
                            "send full UDP relay reply"
                        });
                        require(
                            relay.send_to(&buffer[..length], source).await? == length,
                            "short SOCKS5 UDP reply",
                        )?;
                        eprintln!(
                            "Wintun smoke: SOCKS5 UDP stage {}",
                            json!({"host":host,"port":port,"stage":"relay_reply_sent",
                                "source":source,"wire_bytes":length,"payload_bytes":size})
                        );
                    }
                    // Close only after Windows received both replies. Otherwise an
                    // intentional control failure could overtake the final packet.
                    stage = note_stage("wait for Windows to receive both UDP replies");
                    closed.await.map_err(io::Error::other)?;
                    stage = note_stage("shutdown TCP control");
                    control.shutdown().await
                })
                .await
                .map_err(io::Error::other)
                .and_then(|result| result);
                result.map_err(|error| {
                    io::Error::new(
                        error.kind(),
                        format!("{stage} after {}ms: {error}", started.elapsed().as_millis()),
                    )
                })
            },
        );
        (peer, close)
    }

    fn udp_policy_roundtrips(
        core: &Core,
        directory: &Path,
        runtime: &Handle,
        fake: [IpAddr; 2],
        run: &DeviceRun,
    ) -> io::Result<Vec<serde_json::Value>> {
        let (encrypted_dns, _dns_peer, dns_queries) = dns_fixture(runtime)?;
        let mut retained_clients = Vec::new();
        let mut evidence = Vec::new();
        for (index, host) in [HOST_V4, HOST_V6].into_iter().enumerate() {
            let ipv6 = index == 1;
            let family = if ipv6 { 6 } else { 4 };
            for case in ["proxy", "reject", "proxy_rejected", "proxy_unavailable"] {
                eprintln!("Wintun smoke: IPv{family} UDP {case} with reachable DIRECT controls");
                let trap = std::net::UdpSocket::bind(SocketAddr::new(loopback(ipv6), 0))?;
                trap.set_nonblocking(true)?;
                let port = trap.local_addr()?.port();
                let relay = std::net::UdpSocket::bind(SocketAddr::new(loopback(ipv6), 0))?;
                relay.set_nonblocking(true)?;
                let proxy = std::net::TcpListener::bind(SocketAddr::new(loopback(ipv6), 0))?;
                proxy.set_nonblocking(true)?;
                let unavailable = if case == "proxy_unavailable" {
                    let socket = if ipv6 {
                        tokio::net::TcpSocket::new_v6()?
                    } else {
                        tokio::net::TcpSocket::new_v4()?
                    };
                    socket.bind(SocketAddr::new(loopback(ipv6), 0))?;
                    Some(socket)
                } else {
                    None
                };
                let proxy_address = match &unavailable {
                    Some(socket) => socket.local_addr()?,
                    None => proxy.local_addr()?,
                };
                if unavailable.is_some() {
                    match std::net::TcpStream::connect_timeout(&proxy_address, IO_WAIT) {
                        Err(error) if error.kind() == io::ErrorKind::ConnectionRefused => {}
                        Err(error) => {
                            return Err(io::Error::other(format!(
                                "UDP unavailable proxy control did not refuse: {error}"
                            )));
                        }
                        Ok(_) => {
                            return Err(io::Error::other(
                                "UDP unavailable proxy control unexpectedly connected",
                            ));
                        }
                    }
                }
                let mut config = runtime_config()?;
                config.dns = encrypted_dns.clone();
                config.nodes[0].outbound = Outbound::Socks5 {
                    host: proxy_address.ip().to_string(),
                    port: proxy_address.port(),
                    auth: None,
                    tls: None,
                    udp: true,
                };
                retained_clients.push(udp_direct_control(
                    core,
                    directory,
                    runtime,
                    config.clone(),
                    fake[index],
                    &trap,
                )?);
                eprintln!(
                    "Wintun smoke: UDP client stage {}",
                    json!({"family":family,"case":case,"host":host,"port":port,
                        "stage":"direct_before_received"})
                );
                no_udp_receive(&trap)?;
                config.policy.mode = if case == "reject" {
                    Mode::Rule
                } else {
                    Mode::Global
                };
                if case == "reject" {
                    config.china_rules_directory = Some(
                        Path::new(env!("CARGO_MANIFEST_DIR"))
                            .join("../../../src/Swirl.Quick/packaging/rules")
                            .canonicalize()?
                            .to_str()
                            .ok_or_else(|| io::Error::other("MRS fixture path is not UTF-8"))?
                            .into(),
                    );
                    config.policy.custom_rules.push(PolicyRule {
                        id: "e1000000-0000-4000-8000-000000000001".into(),
                        name: "Reject owned Wintun UDP targets".into(),
                        enabled: true,
                        priority: 0,
                        matcher: Matcher::DomainSuffix {
                            value: "wintun.smoke.invalid".into(),
                        },
                        target: Target::Reject {},
                    });
                }
                apply_policy(core, directory, config.clone())?;
                let baseline = accepted_count(core)?;
                let queries_before = dns_queries.load(Ordering::Acquire);
                let peer = if matches!(case, "reject" | "proxy_unavailable") {
                    None
                } else {
                    Some(socks5_udp_peer(
                        runtime,
                        clone_listener_for_tokio(&proxy)?,
                        clone_udp_for_tokio(&relay)?,
                        host,
                        port,
                        case == "proxy_rejected",
                    ))
                };
                let client = local_udp(ipv6)?;
                let source = client.local_addr()?;
                let destination = SocketAddr::new(fake[index], port);
                let context = json!({"family":family,"case":case,"host":host,"port":port,
                    "source":source,"destination":destination,"baseline":baseline,
                    "proxy_control":proxy_address,"proxy_relay":relay.local_addr()?,
                    "configuration":core.configuration().map_err(io::Error::other)?});
                require(
                    client.send_to(&[], destination).map_err(|error| {
                        udp_stage_error(core, run, &context, "send initial empty UDP", error)
                    })? == 0,
                    "empty UDP send changed length",
                )?;
                eprintln!(
                    "Wintun smoke: UDP client stage {}",
                    json!({"stage":"initial_empty_sent","context":context})
                );
                if case == "proxy" {
                    let mut response = [0; UDP_BYTES + 1];
                    let (length, sender) = client.recv_from(&mut response).map_err(|error| {
                        udp_stage_error(core, run, &context, "receive initial empty UDP", error)
                    })?;
                    require(
                        length == 0 && sender == destination,
                        "SOCKS5 empty UDP reply identity changed",
                    )?;
                    eprintln!(
                        "Wintun smoke: UDP client stage {}",
                        json!({"family":family,"case":case,"source":source,
                            "stage":"empty_reply_received","sender":sender,"bytes":length})
                    );
                    let message = payload(UDP_BYTES);
                    require(
                        client.send_to(&message, destination).map_err(|error| {
                            udp_stage_error(core, run, &context, "send full UDP", error)
                        })? == UDP_BYTES,
                        "short SOCKS5 UDP payload send",
                    )?;
                    let (length, sender) = client.recv_from(&mut response).map_err(|error| {
                        udp_stage_error(core, run, &context, "receive full UDP", error)
                    })?;
                    require(
                        sender == destination && response[..length] == message,
                        "SOCKS5 UDP payload or fake source identity changed",
                    )?;
                    eprintln!(
                        "Wintun smoke: UDP client stage {}",
                        json!({"family":family,"case":case,"source":source,
                            "stage":"full_reply_received","sender":sender,"bytes":length})
                    );
                    udp_record(
                        core,
                        baseline,
                        source,
                        host,
                        port,
                        "proxy",
                        UdpOutcome {
                            ended: false,
                            error: "",
                            bytes: UDP_BYTES as u64,
                        },
                    )
                    .map_err(|error| {
                        udp_stage_error(core, run, &context, "verify active UDP Core record", error)
                    })?;
                }
                if let Some((peer, close)) = peer {
                    if case == "proxy" {
                        close.send(()).map_err(|_| {
                            io::Error::other("SOCKS5 control peer ended before close request")
                        })?;
                    }
                    peer.finish(runtime).map_err(|error| {
                        udp_stage_error(core, run, &context, "finish SOCKS5 UDP peer", error)
                    })?;
                }
                let (category, error, bytes) = match case {
                    "proxy" => ("proxy", "Socks5UdpControlClosed", UDP_BYTES as u64),
                    "reject" => ("reject", "Rejected", 0),
                    "proxy_rejected" => ("proxy", "UpstreamRejected", 0),
                    _ => ("proxy", "UpstreamConnectionRefused", 0),
                };
                let record = udp_record(
                    core,
                    baseline,
                    source,
                    host,
                    port,
                    category,
                    UdpOutcome {
                        ended: true,
                        error,
                        bytes,
                    },
                )?;
                require(
                    dns_queries.load(Ordering::Acquire) == queries_before,
                    "UDP proxy/reject attempted direct target DNS",
                )?;
                no_udp_receive(&trap)?;
                no_udp_receive(&relay)?;
                no_udp_receive(&client)?;
                no_tcp_accept(&proxy)?;

                // A policy switch is not permission to replay a failed UDP
                // association. Verify that this very source tuple is consumed
                // and dropped, without another Core admission or DIRECT send.
                config.policy.mode = Mode::Direct;
                apply_policy(core, directory, config.clone())?;
                let admissions = accepted_count(core)?;
                require(
                    admissions == baseline + 1,
                    "UDP fixture performed unexpected Core admissions",
                )?;
                let dropped = run.bridge_stats.udp_dropped.load(Ordering::Acquire);
                let retry = payload(UDP_BYTES);
                require(
                    client.send_to(&retry, destination)? == retry.len(),
                    "short failed-tuple UDP retry",
                )?;
                let deadline = Instant::now() + IO_WAIT;
                loop {
                    if run.bridge_stats.udp_dropped.load(Ordering::Acquire) == dropped + 1 {
                        break;
                    }
                    if Instant::now() >= deadline {
                        return Err(io::Error::new(
                            io::ErrorKind::TimedOut,
                            "failed UDP tuple was not observed and dropped by the packet bridge",
                        ));
                    }
                    thread::sleep(Duration::from_millis(10));
                }
                require(
                    accepted_count(core)? == admissions,
                    "failed UDP tuple redialled after switching to DIRECT",
                )?;
                no_udp_receive(&trap)?;
                no_udp_receive(&relay)?;
                no_udp_receive(&client)?;
                no_tcp_accept(&proxy)?;
                retained_clients.push(client);
                retained_clients.push(udp_direct_control(
                    core,
                    directory,
                    runtime,
                    config,
                    fake[index],
                    &trap,
                )?);
                no_udp_receive(&trap)?;
                let result = json!({"family":family,"case":case,"source":source,
                    "host":host,"port":port,"core_record_id":record["id"],
                    "category":record["category"],"node":record["node"],"error":record["error"],
                    "upload":record["upload"],"download":record["download"],"ended":record["ended"],
                    "proxy_payload_lengths":if case == "proxy" { vec![0,UDP_BYTES] } else { vec![] },
                    "initial_empty_datagram":true,"blocked_retry_payload_bytes":UDP_BYTES,
                    "same_tuple_retry_after_direct_switch_dropped":true,
                    "core_admissions_during_retry":0,"direct_trap_controls":2,"unexpected_trap_datagrams":0});
                eprintln!("Wintun smoke: PASS UDP policy {}", result);
                evidence.push(result);
            }
        }
        Ok(evidence)
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

    fn dns_tcp_roundtrip(fake: IpAddr, request: &[u8]) -> io::Result<()> {
        let ipv6 = fake.is_ipv6();
        let mut client = std::net::TcpStream::connect_timeout(&dns_address(ipv6), IO_WAIT)?;
        client.set_read_timeout(Some(IO_WAIT))?;
        client.set_write_timeout(Some(IO_WAIT))?;
        require(
            client.local_addr()?.ip() == own(ipv6),
            "Windows TCP DNS did not select the owned TUN address",
        )?;
        // Two framed messages on one connection exercise frame boundaries and
        // reuse of the real bridge's TCP DNS handler.
        for _ in 0..2 {
            client.write_all(&(request.len() as u16).to_be_bytes())?;
            client.write_all(request)?;
            let mut length = [0; 2];
            client.read_exact(&mut length)?;
            let length = usize::from(u16::from_be_bytes(length));
            require(
                (12..=4096).contains(&length),
                "invalid TCP DNS frame length",
            )?;
            let mut response = vec![0; length];
            client.read_exact(&mut response)?;
            require(
                answer_ip(request, &response, ipv6)? == fake,
                "Windows TCP DNS returned another fake identity",
            )?;
        }
        client.shutdown(Shutdown::Write)?;
        let mut byte = [0];
        require(
            client.read(&mut byte)? == 0,
            "TCP DNS did not finish after client FIN",
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
        let label = format!("IPv{} TCP payload and half-close", if ipv6 { 6 } else { 4 });
        let peer = Peer::spawn(runtime, label, async move {
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
        });
        tcp_client_roundtrip(destination)?;
        peer.finish(runtime)
    }

    fn tcp_client_roundtrip(destination: SocketAddr) -> io::Result<()> {
        let mut client = std::net::TcpStream::connect_timeout(&destination, IO_WAIT)?;
        client.set_read_timeout(Some(IO_WAIT))?;
        client.set_write_timeout(Some(IO_WAIT))?;
        require(
            client.local_addr()?.ip() == own(destination.is_ipv6()),
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
        )
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
        let label = format!("IPv{} empty/full UDP", if ipv6 { 6 } else { 4 });
        let peer = Peer::spawn(runtime, label, async move {
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
        });
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

    fn reused_frame(round: usize) -> Vec<u8> {
        let mut frame = payload(REUSE_BYTES);
        frame[..4].copy_from_slice(&(round as u32).to_be_bytes());
        frame
    }

    fn tcp_reuse_and_reset(runtime: &Handle, fake: IpAddr, run: &DeviceRun) -> io::Result<()> {
        let ipv6 = fake.is_ipv6();
        let listener = runtime.block_on(tokio::net::TcpListener::bind(SocketAddr::new(
            loopback(ipv6),
            0,
        )))?;
        let destination = SocketAddr::new(fake, listener.local_addr()?.port());
        let label = format!("IPv{} persistent TCP", if ipv6 { 6 } else { 4 });
        let peer = Peer::spawn(runtime, label, async move {
            timeout(IO_WAIT, async {
                let (mut stream, source) = listener.accept().await?;
                require(
                    source.ip().is_loopback(),
                    "reused TCP Core egress escaped loopback",
                )?;
                let mut frame = vec![0; REUSE_BYTES];
                for round in 0..REUSE_ROUNDS {
                    stream.read_exact(&mut frame).await?;
                    require(
                        frame == reused_frame(round),
                        "reused TCP request order or bytes changed",
                    )?;
                    frame[0] ^= 0xa5;
                    stream.write_all(&frame).await?;
                }
                let mut byte = [0];
                require(
                    stream.read(&mut byte).await? == 0,
                    "reused TCP client FIN missing",
                )?;
                stream.write_all(b"reuse-finished").await?;
                stream.shutdown().await
            })
            .await
            .map_err(io::Error::other)?
        });
        let mut client = std::net::TcpStream::connect_timeout(&destination, IO_WAIT)?;
        client.set_read_timeout(Some(IO_WAIT))?;
        client.set_write_timeout(Some(IO_WAIT))?;
        let original_source = client.local_addr()?;
        require(
            original_source.ip() == own(ipv6),
            "reused TCP did not enter owned TUN",
        )?;
        for round in 0..REUSE_ROUNDS {
            if round == REUSE_ROUNDS / 2 {
                let reset_listener = runtime.block_on(tokio::net::TcpListener::bind(
                    SocketAddr::new(loopback(ipv6), 0),
                ))?;
                let reset_destination = SocketAddr::new(fake, reset_listener.local_addr()?.port());
                let label = format!("IPv{} abortive TCP reset", if ipv6 { 6 } else { 4 });
                let reset_peer = Peer::spawn(runtime, label, async move {
                    timeout(IO_WAIT, async {
                        let (mut stream, source) = reset_listener.accept().await?;
                        require(
                            source.ip().is_loopback(),
                            "RST Core egress escaped loopback",
                        )?;
                        let mut ready = [0; 11];
                        stream.read_exact(&mut ready).await?;
                        require(&ready == b"reset-ready", "RST setup request changed")?;
                        stream.write_all(b"reset-armed").await?;
                        let mut byte = [0];
                        match stream.read(&mut byte).await {
                            Ok(0) => Ok(()),
                            Err(error)
                                if matches!(
                                    error.kind(),
                                    io::ErrorKind::ConnectionReset
                                        | io::ErrorKind::ConnectionAborted
                                ) =>
                            {
                                Ok(())
                            }
                            Err(error) => Err(error),
                            Ok(_) => {
                                Err(io::Error::other("aborted flow delivered unexpected bytes"))
                            }
                        }
                    })
                    .await
                    .map_err(io::Error::other)?
                });
                let reset_source = runtime.block_on(async {
                    let socket = if ipv6 {
                        tokio::net::TcpSocket::new_v6()?
                    } else {
                        tokio::net::TcpSocket::new_v4()?
                    };
                    socket.bind(SocketAddr::new(own(ipv6), 0))?;
                    socket.set_zero_linger()?;
                    require(
                        socket.linger()? == Some(Duration::ZERO),
                        "SO_LINGER=0 was not applied",
                    )?;
                    let mut reset = timeout(IO_WAIT, socket.connect(reset_destination))
                        .await
                        .map_err(io::Error::other)??;
                    let source = reset.local_addr()?;
                    timeout(IO_WAIT, async {
                        reset.write_all(b"reset-ready").await?;
                        let mut ready = [0; 11];
                        reset.read_exact(&mut ready).await?;
                        require(&ready == b"reset-armed", "RST setup response changed")
                    })
                    .await
                    .map_err(io::Error::other)??;
                    // No shutdown(): dropping this real Windows socket must
                    // produce the abortive RST observed by the Wintun reader.
                    drop(reset);
                    Ok::<_, io::Error>(source)
                })?;
                reset_peer.finish(runtime)?;
                let deadline = Instant::now() + IO_WAIT;
                loop {
                    let observed = run
                        .reset_packets
                        .lock()
                        .map_err(|_| io::Error::other("RST observation lock poisoned"))?
                        .contains(&(reset_source, reset_destination));
                    if observed && run.stats.snapshot().active_tcp_flows == 1 {
                        break;
                    }
                    if Instant::now() >= deadline {
                        return Err(io::Error::new(
                            io::ErrorKind::TimedOut,
                            "exact Windows RST packet or aborted-flow cleanup was not observed",
                        ));
                    }
                    thread::sleep(Duration::from_millis(10));
                }
                eprintln!(
                    "Wintun smoke: PASS IPv{} exact Windows SO_LINGER=0 RST tuple and independent flow cleanup",
                    if ipv6 { 6 } else { 4 }
                );
            }
            let mut frame = reused_frame(round);
            client.write_all(&frame)?;
            frame[0] ^= 0xa5;
            let mut reply = vec![0; REUSE_BYTES];
            client.read_exact(&mut reply)?;
            require(reply == frame, "reused TCP response order or bytes changed")?;
            require(
                client.local_addr()? == original_source,
                "persistent TCP connection changed",
            )?;
        }
        client.shutdown(Shutdown::Write)?;
        let mut final_reply = Vec::new();
        (&mut client).take(32).read_to_end(&mut final_reply)?;
        require(
            final_reply == b"reuse-finished",
            "persistent TCP final half-close reply changed",
        )?;
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
        let configuration_before = windows_network::snapshot_network_configuration()?;
        let (owner, guid) = nonce()?;
        let fake_path = directory.join(format!("smoke-{owner}.fake-ip.jsonl"));
        let dns = TunDns::new(FakeIpStore::open(&fake_path, 8).map_err(io::Error::other)?);
        let mut core = Core::start(
            runtime_config()?,
            STORE_ID.into(),
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
        let requests = [query(HOST_V4, false), query(HOST_V6, true)];
        let lookup = Lookup(dispatcher.clone());
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
        // Close the actual file owner and reconstruct from durable bytes. The
        // Wintun path below uses this reopened store, not the original memory.
        drop(dns);
        let dns = TunDns::new(FakeIpStore::open(&fake_path, 8).map_err(io::Error::other)?);
        for index in 0..2 {
            require(
                runtime
                    .block_on(dns.target_host(fake[index]))
                    .map_err(io::Error::other)?
                    == [HOST_V4, HOST_V6][index],
                "persisted fake identity changed after reopening",
            )?;
            let response = runtime
                .block_on(dns.answer(&requests[index], &lookup))
                .map_err(io::Error::other)?;
            require(
                answer_ip(&requests[index], &response, index == 1)? == fake[index],
                "persisted fake address changed after reopening",
            )?;
        }
        eprintln!("Wintun smoke: PASS durable dual-stack Fake-IP close/reopen identity");
        let packet = native_tun::spawn(
            dispatcher.clone(),
            dns,
            TunConfig {
                mtu: MTU as usize,
                max_tcp_flows: 8,
                // Two existing DIRECT tuples plus 2 families * 4 policy cases
                // * 3 retained source tuples (before/case/after) require 26.
                // Keep capacity bounded without evicting negative tombstones.
                max_udp_endpoints: 32,
                ..TunConfig::default()
            },
        )
        .map_err(io::Error::other)?;
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
        let mut udp_policy_evidence = Vec::new();
        let tests = (|| {
            for index in 0..2 {
                let family = if index == 0 { 4 } else { 6 };
                eprintln!("Wintun smoke: IPv{family} DNS identity");
                dns_roundtrip(fake[index], &requests[index])?;
                eprintln!("Wintun smoke: PASS IPv{family} UDP DNS identity and TTL");
                dns_tcp_roundtrip(fake[index], &requests[index])?;
                eprintln!("Wintun smoke: PASS IPv{family} TCP DNS framing, identity and TTL");
                eprintln!("Wintun smoke: IPv{family} TCP payload and half-close");
                tcp_roundtrip(&runtime, fake[index])?;
                eprintln!("Wintun smoke: PASS IPv{family} TCP payload and half-close");
                tcp_reuse_and_reset(&runtime, fake[index], &run)?;
                eprintln!(
                    "Wintun smoke: PASS IPv{family} {REUSE_ROUNDS} rounds on one TCP connection across a second connection reset"
                );
                eprintln!("Wintun smoke: IPv{family} empty and full UDP datagrams");
                udp_roundtrip(&runtime, fake[index])?;
                eprintln!("Wintun smoke: PASS IPv{family} empty and full UDP datagrams");
            }
            policy_roundtrips(&core, &directory, &runtime, fake)?;
            udp_policy_evidence = udp_policy_roundtrips(&core, &directory, &runtime, fake, &run)?;
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
        let mut errors = Vec::new();
        if let Err(error) = tests {
            errors.push(format!("data tests: {error}"));
        }
        if let Err(error) = run.stop() {
            errors.push(format!("network recovery: {error}"));
        }
        // A failed data test must still execute every shutdown assertion. A
        // successful stop alone is not evidence that the adapter disappeared
        // or that the runner's original capture/default routes are unchanged.
        let stats = run.stats.snapshot();
        if stats.active_tcp_flows != 0 || stats.active_udp_endpoints != 0 {
            errors.push("packet resources survived shutdown".into());
        } else {
            eprintln!("Wintun smoke: PASS packet resources released");
        }
        match windows_network::snapshot() {
            Ok(after) => {
                if sorted_routes(before.routes) != sorted_routes(after.routes) {
                    errors.push("unrelated default/split-default routes changed".into());
                } else {
                    eprintln!("Wintun smoke: PASS default/split-default routes unchanged");
                }
                if after
                    .adapters
                    .iter()
                    .any(|adapter| adapter.identity.guid == run.journal.interface.guid)
                {
                    errors.push("owned Wintun adapter survived shutdown".into());
                } else {
                    eprintln!("Wintun smoke: PASS owned Wintun adapter removed");
                }
            }
            Err(error) => errors.push(format!("post-cleanup system snapshot: {error}")),
        }
        match windows_network::snapshot_network_configuration() {
            Ok(after) => {
                let adapters_equal = after.adapters == configuration_before.adapters;
                let routes_equal = after.routes == configuration_before.routes;
                eprintln!(
                    "Wintun smoke: exact network configuration verification {}",
                    json!({"adapters_equal":adapters_equal,"all_routes_equal":routes_equal,
                        "adapters_before":configuration_before.adapters.len(),"adapters_after":after.adapters.len(),
                        "routes_before":configuration_before.routes.len(),"routes_after":after.routes.len()})
                );
                if !adapters_equal {
                    errors.push("original adapter addresses/DNS/MTU/DHCP/metrics changed".into());
                }
                if !routes_equal {
                    errors.push("original complete ActiveStore route configuration changed".into());
                }
            }
            Err(error) => errors.push(format!("post-cleanup full network configuration: {error}")),
        }
        core.stop();
        if !errors.is_empty() {
            return Err(io::Error::other(errors.join("; ")));
        }
        let additional_cases = json!({
            "dns_tcp_ipv4":true,"dns_tcp_ipv6":true,"dns_ttl":ANSWER_TTL,
            "fake_ip_persisted_reopen":true,
            "native_http_connect_ipv4":true,"native_http_connect_ipv6":true,
            "reject_tcp_ipv4":true,"reject_tcp_ipv6":true,
            "proxy_failure_no_direct_ipv4":true,"proxy_failure_no_direct_ipv6":true,
            "proxy_failure_cases":["http_403_rejected","connection_refused"],
            "direct_trap_controls_before_and_after":true,"verified_dot_fixture":true,
            "tcp_policy":{"transport":"native_http_connect","families":[4,6],
                "direct":true,"proxy":true,"reject":true,
                "proxy_failure_no_direct":["UpstreamRejected","UpstreamConnectionRefused"]},
            "udp_policy":{"transport":"native_socks5_udp","families":[4,6],
                "proxy_payload_lengths":[0,UDP_BYTES],"direct":true,"proxy":true,"reject":true,
                "proxy_failure_no_direct":["UpstreamRejected","UpstreamConnectionRefused","Socks5UdpControlClosed"],
                "failed_source_tuple_no_redial_after_direct_switch":true,
                "results":udp_policy_evidence},
            "windows_tcp_rst_ipv4":true,"windows_tcp_rst_ipv6":true,
            "tcp_reuse_rounds_each_family":REUSE_ROUNDS,
            "tcp_reuse_payload_bytes_each_round":REUSE_BYTES,
            "long_duration_soak_acceptance":false,
            "original_network_configuration_exact":true
        });
        println!(
            "{}",
            json!({
                "ok":true,"evidence":"Windows Wintun scoped loopback smoke",
                "source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),
                "driver_version":"0.14.1","driver_sha256":official_driver_sha256()?,
                "interface_index":run.journal.interface.index,
                "dns_a":true,"dns_aaaa":true,"tcp_ipv4":true,"tcp_ipv6":true,
                "tcp_payload_bytes_each_family":TCP_BYTES,"tcp_reply_after_client_fin":true,
                "additional_cases":additional_cases,
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
