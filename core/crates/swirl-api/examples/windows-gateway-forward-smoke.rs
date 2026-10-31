//! Disposable Windows forwarding mechanism test with two newly owned Wintun
//! adapters. This is not physical LAN, WFP topology, DHCP, or Windows 11 product
//! acceptance. No network operation is reachable without the explicit flag.
//!
//! Client packets enter Windows through adapter A, must be routed by Windows
//! into adapter B, and only then reach the existing native_tun/FlowDispatcher.
//! Replies enter Windows through B and must return through A. The fixture
//! never sends a client packet directly to PacketBridge.input.
//! Mechanism references: https://git.zx2c4.com/wintun/tree/api/wintun.h and
//! https://learn.microsoft.com/powershell/module/nettcpip/set-netipinterface
//! (`Forwarding` governs packets arriving on the selected interface).
use std::{io, path::PathBuf, process::ExitCode};

fn arguments() -> io::Result<Option<PathBuf>> {
    let mut arguments = std::env::args_os().skip(1);
    let mut disposable = false;
    let mut driver = None;
    while let Some(argument) = arguments.next() {
        if argument == "--help" {
            println!(
                "windows-gateway-forward-smoke --disposable-network --wintun <absolute official wintun.dll>\n\
                 Only use an explicitly authorized disposable Windows environment.\n\
                 Enables IPv4 forwarding only on two newly created owned adapters.\n\
                 Adds exact /32 test routes; does not alter physical forwarding, DNS, firewall or defaults."
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
                format!("unsupported or duplicate argument: {}", argument.to_string_lossy()),
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
        io::Error::new(io::ErrorKind::InvalidInput, "--wintun requires an absolute DLL path")
    })
}

fn main() -> ExitCode {
    let result = arguments().and_then(|driver| match driver {
        Some(driver) => execute(driver),
        None => Ok(()),
    });
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("windows-gateway-forward-smoke failed: {error}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(not(windows))]
fn execute(_: PathBuf) -> io::Result<()> {
    Err(io::Error::new(io::ErrorKind::Unsupported, "this smoke requires disposable Windows"))
}

#[cfg(windows)]
fn execute(driver: PathBuf) -> io::Result<()> {
    windows::run(driver)
}

#[cfg(windows)]
#[path = "support/gateway_packet_fixture.rs"]
mod packet;

#[cfg(windows)]
mod windows {
    use super::{packet, *};
    use ring::rand::{SecureRandom, SystemRandom};
    use serde_json::json;
    use smoltcp::wire::{IpProtocol, TcpControl};
    use std::{
        collections::{BTreeMap, HashMap},
        future::Future,
        net::{IpAddr, Ipv4Addr, SocketAddr, SocketAddrV4, TcpListener, TcpStream, UdpSocket},
        path::Path,
        pin::Pin,
        sync::{Arc, Mutex, atomic::{AtomicBool, AtomicU64, Ordering}, mpsc},
        thread,
        time::{Duration, Instant},
    };
    use swirl_api::native_tun::{self, BridgeControl, PacketBridge};
    use swirl_core::v2::{Core, FlowDispatcher, RuntimeConfig};
    use swirl_dns::tun::{ANSWER_TTL, DNS_IPV4, FakeIpStore, TunDns, TunLookup};
    use swirl_platform::{
        network_transaction::{
            self as transaction, FileJournalStore, InterfaceIdentity, Journal,
            NetworkBackend, Resource, Value,
        },
        windows_network::{self, NetworkConfigurationSnapshot, WindowsNetworkBackend},
        wintun_device::{WintunConfig, WintunDevice, official_driver_sha256},
    };
    use swirl_subscription::{
        Dns, DnsTlsServer, HostMapping, Limits, Node, Outbound, Tls,
        v2::{ClassificationDns, DEFAULT_POLICY_ID, DefaultPolicy, Mode, PolicyDocument, Target},
    };
    use swirl_transport::egress::EgressLease;
    use swirl_tun::{TunConfig, TunStats, gateway::GatewayIngress};
    use tokio::{runtime::Handle, task::JoinHandle};

    const WAIT: Duration = Duration::from_secs(15);
    const QUIET: Duration = Duration::from_millis(500);
    const MTU: u32 = 1500;
    const MAX_PACKETS: usize = 512;
    const LAN_HOST: Ipv4Addr = Ipv4Addr::new(192, 168, 249, 1);
    // Deliberately never assigned to any Windows adapter: replies must be
    // forwarded to A, not delivered into a local host socket.
    const CLIENT: Ipv4Addr = Ipv4Addr::new(192, 168, 249, 2);
    const CORE_HOST: Ipv4Addr = Ipv4Addr::new(198, 18, 0, 1);
    const GOOD_HOST: &str = "public.gateway-forward.smoke.invalid";
    const BLOCKED_HOST: &str = "protected.gateway-forward.smoke.invalid";
    const STORE_ID: &str = "a2000000-0000-4000-8000-000000000001";
    const NODE_ID: &str = "c2000000-0000-4000-8000-000000000001";

    fn require(condition: bool, reason: impl ToString) -> io::Result<()> {
        if condition { Ok(()) } else { Err(io::Error::other(reason.to_string())) }
    }

    fn nonce() -> io::Result<(String, u128)> {
        let mut bytes = [0u8; 16];
        SystemRandom::new().fill(&mut bytes).map_err(|_| io::Error::other("secure random unavailable"))?;
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        Ok((bytes.iter().map(|byte| format!("{byte:02x}")).collect(), u128::from_be_bytes(bytes)))
    }

    fn runtime_config() -> io::Result<RuntimeConfig> {
        Ok(RuntimeConfig {
            schema: 2,
            listen: "127.0.0.1:0".parse().map_err(io::Error::other)?,
            nodes: vec![Node {
                id: NODE_ID.into(),
                // Direct mode never uses this placeholder. Gateway admission
                // has no loopback exception for it or for the protected trap.
                outbound: Outbound::HttpConnect { host: "127.0.0.1".into(), port: 9, auth: None, tls: None },
            }],
            policy: PolicyDocument {
                schema: 2, mode: Mode::Direct,
                default_policy: DefaultPolicy { id: DEFAULT_POLICY_ID.into(), target: Target::Node { id: NODE_ID.into() } },
                service_policies: vec![], groups: vec![], explicit_direct_rules: vec![],
                custom_rules: vec![], missing_targets: vec![], classification_dns: ClassificationDns::Disabled,
            },
            dns: Dns {
                tls_servers: vec![DnsTlsServer {
                    address: "192.0.2.1:853".parse().map_err(io::Error::other)?,
                    tls: Tls { server_name: "dns.gateway-forward.smoke.invalid".into(), alpn: vec![], ca_der_base64: None },
                    https_path: None,
                }],
                hosts: vec![
                    HostMapping { name: GOOD_HOST.into(), address: Ipv4Addr::new(203, 0, 113, 7).into() },
                    HostMapping { name: BLOCKED_HOST.into(), address: Ipv4Addr::LOCALHOST.into() },
                ],
                use_system_hosts: false,
                ..Dns::default()
            },
            inbound_auth: None, limits: Limits::default(), china_rules_directory: None,
            node_sources: BTreeMap::new(), transports: BTreeMap::new(),
        })
    }

    struct Lookup(FlowDispatcher);
    impl TunLookup for Lookup {
        fn lookup<'a>(&'a self, name: &'a str) -> Pin<Box<dyn Future<Output = Result<Vec<IpAddr>, &'static str>> + Send + 'a>> {
            Box::pin(async move {
                self.0.resolve_dns(name, 53, SocketAddr::new(CORE_HOST.into(), 41053)).await
                    .map(|addresses| addresses.into_iter().map(|address| address.ip()).collect())
            })
        }
    }

    fn query(name: &str, ipv6: bool, id: u16) -> Vec<u8> {
        let mut bytes = vec![0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0];
        bytes[..2].copy_from_slice(&id.to_be_bytes());
        for label in name.split('.') {
            bytes.push(label.len() as u8);
            bytes.extend_from_slice(label.as_bytes());
        }
        bytes.push(0);
        bytes.extend_from_slice(if ipv6 { &[0, 28, 0, 1] } else { &[0, 1, 0, 1] });
        bytes
    }

    fn dns_answer(request: &[u8], response: &[u8]) -> io::Result<Ipv4Addr> {
        require(response.len() == request.len() + 16, "DNS A response length")?;
        require(response[..2] == request[..2] && response[2] & 0x80 != 0 && response[3] & 15 == 0, "DNS response identity or status")?;
        require(response[4..12] == [0, 1, 0, 1, 0, 0, 0, 0], "DNS answer counts")?;
        require(response[12..request.len()] == request[12..], "DNS question changed")?;
        let answer = &response[request.len()..];
        require(answer[..6] == [0xc0, 0x0c, 0, 1, 0, 1], "DNS answer type")?;
        require(u32::from_be_bytes(answer[6..10].try_into().map_err(io::Error::other)?) == ANSWER_TTL, "DNS answer TTL")?;
        require(answer[10..12] == [0, 4], "DNS address size")?;
        Ok(Ipv4Addr::from(<[u8; 4]>::try_from(&answer[12..]).map_err(io::Error::other)?))
    }

    fn host_inventory(snapshot: &NetworkConfigurationSnapshot) -> io::Result<Vec<IpAddr>> {
        let mut addresses = vec![IpAddr::V4(LAN_HOST), IpAddr::V4(CORE_HOST), IpAddr::V4(Ipv4Addr::LOCALHOST)];
        for adapter in &snapshot.adapters {
            for address in &adapter.addresses {
                let literal = address.address.split('%').next().ok_or_else(|| io::Error::other("empty host address"))?;
                let ip: IpAddr = literal.parse().map_err(io::Error::other)?;
                if !ip.is_unspecified() && !ip.is_multicast() {
                    addresses.push(ip);
                }
            }
        }
        addresses.sort();
        addresses.dedup();
        require(!addresses.contains(&CLIENT.into()), "synthetic client must not be a host address")?;
        Ok(addresses)
    }

    fn unused_scope(snapshot: &NetworkConfigurationSnapshot, targets: &[Ipv4Addr]) -> io::Result<()> {
        for adapter in &snapshot.adapters {
            for address in &adapter.addresses {
                if let Ok(ip) = address.address.parse::<Ipv4Addr>() {
                    require(!targets.contains(&ip), "fixture address already belongs to a host adapter")?;
                }
            }
        }
        for route in &snapshot.routes {
            let prefix: ipnet::IpNet = route.destination.parse().map_err(io::Error::other)?;
            // Existing defaults are observed, never changed. Any more-specific
            // route into this scope makes the disposable fixture unsuitable.
            require(prefix.prefix_len() < 2 || !targets.iter().any(|ip| prefix.contains(&IpAddr::V4(*ip))), "existing route overlaps a fixture destination")?;
        }
        Ok(())
    }

    struct OwnedAdapter {
        device: Option<Arc<WintunDevice>>,
        backend: WindowsNetworkBackend,
        journal: Journal,
        store: FileJournalStore,
        journal_path: PathBuf,
        restored: bool,
    }

    impl OwnedAdapter {
        fn prepare(driver: &Path, directory: &Path, lan: bool, destinations: &[Ipv4Addr]) -> io::Result<Self> {
            let (owner, guid) = nonce()?;
            let device = Arc::new(WintunDevice::create(&WintunConfig {
                driver_path: driver.to_owned(), expected_sha256: official_driver_sha256()?.into(),
                adapter_name: format!("Swirl Gateway Smoke {} {}", if lan { "A" } else { "B" }, &owner[..8]),
                adapter_guid: guid, ring_capacity: 4 * 1024 * 1024,
            })?);
            let identity = InterfaceIdentity::new(device.interface_index()?, device.adapter_guid());
            let mut backend = WindowsNetworkBackend::for_owned_interface(identity.clone())?;
            require(backend.read(&identity, &Resource::Forwarding { ipv6: false })?
                == Some(Value::Forwarding { enabled: false }), "new disposable adapter unexpectedly forwards already")?;
            let mut desired = vec![
                (Resource::Mtu { ipv6: false }, Some(Value::Mtu { mtu: MTU })),
                (Resource::Address { address: if lan { LAN_HOST } else { CORE_HOST }.into() },
                    Some(Value::Address { prefix_len: 32, skip_as_source: false })),
            ];
            // A: return route before forwarding; forwarding is applied last.
            // B: forwarding before /32 capture routes; recovery removes those
            // routes before disabling the return path. All targets are fixtures.
            if !lan {
                desired.push((Resource::Forwarding { ipv6: false }, Some(Value::Forwarding { enabled: true })));
            }
            for destination in destinations {
                desired.push((Resource::Route {
                    destination: ipnet::IpNet::new((*destination).into(), 32).map_err(io::Error::other)?,
                    next_hop: Ipv4Addr::UNSPECIFIED.into(),
                }, Some(Value::Route { metric: 5 })));
            }
            if lan {
                desired.push((Resource::Forwarding { ipv6: false }, Some(Value::Forwarding { enabled: true })));
            }
            let journal = Journal::prepare(&mut backend, identity.clone(), owner, desired)?;
            let journal_path = directory.join(format!("{}.network.json", identity.guid.replace('-', "")));
            let store = FileJournalStore::create_new(&journal_path)?;
            Ok(Self { device: Some(device), backend, journal, store, journal_path, restored: false })
        }

        fn device(&self) -> io::Result<Arc<WintunDevice>> {
            self.device.clone().ok_or_else(|| io::Error::other("owned device has stopped"))
        }

        fn apply_through(&mut self, through: usize) -> io::Result<()> {
            transaction::apply_prefix(&mut self.backend, &mut self.store, &mut self.journal, through)
                .map_err(|error| io::Error::other(format!("owned forwarding fixture apply: {error}")))
        }

        fn quiesce(&mut self) -> io::Result<()> {
            let last = self.journal.changes.len() - 1;
            require(self.journal.changes[last].resource == Resource::Forwarding { ipv6: false }, "entry forwarding must be last in its journal")?;
            let report = transaction::recover_suffix(&mut self.backend, &mut self.store, &mut self.journal, last)?;
            require(report.conflicts.is_empty(), format!("entry forwarding restore conflicts: {:?}", report.conflicts))?;
            require(self.backend.read(&self.journal.interface, &Resource::Forwarding { ipv6: false })?
                == Some(Value::Forwarding { enabled: false }), "entry forwarding remains enabled")
        }

        fn restore(&mut self) -> io::Result<()> {
            if self.restored { return Ok(()); }
            let report = transaction::recover(&mut self.backend, &mut self.store, &mut self.journal)?;
            require(report.conflicts.is_empty() && self.journal.is_restored(), format!("owned adapter recovery conflicts: {:?}", report.conflicts))?;
            for change in &self.journal.changes {
                let observed = self.backend.read(&self.journal.interface, &change.resource)?;
                let exact = observed == change.before;
                eprintln!("Gateway forwarding smoke restored {}", json!({
                    "interface":self.journal.interface,"resource":change.resource,
                    "before":change.before,"observed":observed,"exact":exact
                }));
                require(exact, "owned forwarding fixture before-value readback differs")?;
            }
            let archive = self.journal_path.with_extension("gateway-smoke-restored");
            require(!archive.exists(), "restored journal archive already exists")?;
            std::fs::rename(&self.journal_path, archive)?;
            self.restored = true;
            Ok(())
        }
    }

    impl Drop for OwnedAdapter {
        fn drop(&mut self) {
            if self.device.is_some() {
                if let Err(error) = self.restore() {
                    eprintln!("Gateway smoke recovery incomplete; preserve {}: {error}", self.journal_path.display());
                }
                if let Some(device) = self.device.take() { let _ = device.shutdown(); }
            }
        }
    }

    #[derive(Default)]
    struct PacketEvidence {
        injected: HashMap<Vec<u8>, u8>,
        replies: HashMap<Vec<u8>, u8>,
        forwarded_into_core: u64,
        forwarded_to_client: u64,
        errors: Vec<String>,
    }

    impl PacketEvidence {
        fn fail(&mut self, reason: impl ToString) {
            if self.errors.len() < 16 { self.errors.push(reason.to_string()); }
        }

        fn record(map: &mut HashMap<Vec<u8>, u8>, bytes: &[u8]) -> io::Result<()> {
            let (identity, ttl) = packet::forwarding_identity(bytes)?;
            require(map.len() < MAX_PACKETS || map.contains_key(&identity), "packet evidence bound reached")?;
            require(ttl > 1, "fixture packet cannot survive a forwarding hop")?;
            map.insert(identity, ttl);
            Ok(())
        }

        fn verify(map: &HashMap<Vec<u8>, u8>, bytes: &[u8]) -> io::Result<()> {
            let (identity, ttl) = packet::forwarding_identity(bytes)?;
            let previous = map.get(&identity).ok_or_else(|| io::Error::other("driver packet did not originate from the recorded fixture path"))?;
            require(ttl.checked_add(1) == Some(*previous), format!("Windows forwarding TTL differs: observed={ttl}, original={previous}"))
        }
    }

    fn with_evidence<T>(evidence: &Mutex<PacketEvidence>, work: impl FnOnce(&mut PacketEvidence) -> io::Result<T>) -> io::Result<T> {
        let mut locked = evidence.lock().map_err(|_| io::Error::other("packet evidence lock poisoned"))?;
        work(&mut locked)
    }

    fn send_packet(device: &WintunDevice, bytes: &[u8]) -> io::Result<()> {
        for _ in 0..64 {
            match device.send(bytes) {
                Ok(()) => return Ok(()),
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => thread::sleep(Duration::from_millis(1)),
                Err(error) => return Err(error),
            }
        }
        Err(io::Error::new(io::ErrorKind::TimedOut, "Wintun send ring remained full"))
    }

    struct ForwardRun {
        lan: OwnedAdapter,
        capture: OwnedAdapter,
        runtime: Handle,
        control: BridgeControl,
        stats: TunStats,
        bridge_stats: Arc<native_tun::BridgeStats>,
        client_packets: mpsc::Receiver<Vec<u8>>,
        readers: Vec<thread::JoinHandle<()>>,
        writer: Option<JoinHandle<()>>,
        closing: Arc<AtomicBool>,
        evidence: Arc<Mutex<PacketEvidence>>,
        injected_packets: u64,
        returned_packets: Arc<AtomicU64>,
        destinations: Vec<Ipv4Addr>,
        binding: Option<EgressLease>,
        stopped: bool,
    }

    impl ForwardRun {
        fn start(driver: &Path, directory: &Path, packet: PacketBridge, runtime: Handle, destinations: Vec<Ipv4Addr>, binding: EgressLease) -> io::Result<Self> {
            let lan = OwnedAdapter::prepare(driver, directory, true, &[CLIENT])?;
            let capture = OwnedAdapter::prepare(driver, directory, false, &destinations)?;
            let (sender, receiver) = mpsc::sync_channel(MAX_PACKETS);
            let mut run = Self {
                lan, capture, runtime, control: packet.control, stats: packet.stats, bridge_stats: packet.bridge_stats,
                client_packets: receiver, readers: Vec::new(), writer: None,
                closing: Arc::new(AtomicBool::new(false)), evidence: Arc::new(Mutex::new(PacketEvidence::default())),
                injected_packets: 0, returned_packets: Arc::new(AtomicU64::new(0)),
                destinations: destinations.clone(),
                binding: Some(binding), stopped: false,
            };
            // The entry remains non-forwarding until the capture and reader
            // tasks are ready. Both durable plans only target newly owned NICs.
            run.lan.apply_through(run.lan.journal.changes.len() - 1)?;
            run.capture.apply_through(run.capture.journal.changes.len())?;
            let core_device = run.capture.device()?;
            let closing = run.closing.clone();
            let evidence = run.evidence.clone();
            let capture_destinations = destinations.clone();
            run.readers.push(thread::Builder::new().name("swirl-gateway-smoke-core".into()).spawn(move || {
                while !closing.load(Ordering::Acquire) {
                    let result = (|| -> io::Result<()> {
                        let mut bytes = Vec::with_capacity(MTU as usize);
                        core_device.receive_blocking(&mut bytes)?;
                        if bytes.first().is_none_or(|byte| byte >> 4 != 4) { return Ok(()); }
                        let ip = packet::envelope(&bytes)?;
                        if ip.source != CLIENT || !capture_destinations.contains(&ip.destination) { return Ok(()); }
                        with_evidence(&evidence, |observed| {
                            PacketEvidence::verify(&observed.injected, &bytes)?;
                            observed.forwarded_into_core += 1;
                            Ok(())
                        })?;
                        // Sole client ingress: bytes read from the B driver.
                        packet.input.blocking_send(bytes).map_err(io::Error::other)
                    })();
                    if let Err(error) = result {
                        if !closing.load(Ordering::Acquire) {
                            let _ = with_evidence(&evidence, |observed| { observed.fail(format!("B reader: {error}")); Ok(()) });
                        }
                        break;
                    }
                }
            })?);
            let client_device = run.lan.device()?;
            let closing = run.closing.clone();
            let evidence = run.evidence.clone();
            let reply_sources = destinations;
            run.readers.push(thread::Builder::new().name("swirl-gateway-smoke-client".into()).spawn(move || {
                while !closing.load(Ordering::Acquire) {
                    let result = (|| -> io::Result<()> {
                        let mut bytes = Vec::with_capacity(MTU as usize);
                        client_device.receive_blocking(&mut bytes)?;
                        if bytes.first().is_none_or(|byte| byte >> 4 != 4) { return Ok(()); }
                        let ip = packet::envelope(&bytes)?;
                        if ip.destination != CLIENT || !reply_sources.contains(&ip.source) { return Ok(()); }
                        with_evidence(&evidence, |observed| {
                            PacketEvidence::verify(&observed.replies, &bytes)?;
                            observed.forwarded_to_client += 1;
                            Ok(())
                        })?;
                        sender.try_send(bytes).map_err(io::Error::other)
                    })();
                    if let Err(error) = result {
                        if !closing.load(Ordering::Acquire) {
                            let _ = with_evidence(&evidence, |observed| { observed.fail(format!("A reader: {error}")); Ok(()) });
                        }
                        break;
                    }
                }
            })?);
            let core_device = run.capture.device()?;
            let closing = run.closing.clone();
            let evidence = run.evidence.clone();
            let count = run.returned_packets.clone();
            let reply_sources = run.destinations.clone();
            let mut output = packet.output;
            run.writer = Some(run.runtime.spawn(async move {
                while let Some(bytes) = output.recv().await {
                    let recorded = (|| -> io::Result<()> {
                        let ip = packet::envelope(&bytes)?;
                        require(bytes.len() <= MTU as usize && ip.destination == CLIENT
                            && reply_sources.contains(&ip.source)
                            && matches!(ip.protocol, IpProtocol::Tcp | IpProtocol::Udp),
                            "Core reply escaped the fixture tuple scope")?;
                        with_evidence(&evidence, |observed| PacketEvidence::record(&mut observed.replies, &bytes))
                    })();
                    if let Err(error) = recorded {
                        let _ = with_evidence(&evidence, |observed| { observed.fail(format!("B writer identity: {error}")); Ok(()) });
                        break;
                    }
                    let mut delivered = false;
                    for _ in 0..64 {
                        match core_device.send(&bytes) {
                            Ok(()) => { count.fetch_add(1, Ordering::Relaxed); delivered = true; break; }
                            Err(error) if error.kind() == io::ErrorKind::WouldBlock => tokio::time::sleep(Duration::from_millis(1)).await,
                            Err(_) if closing.load(Ordering::Acquire) => return,
                            Err(error) => {
                                let _ = with_evidence(&evidence, |observed| { observed.fail(format!("B writer: {error}")); Ok(()) });
                                return;
                            }
                        }
                    }
                    if !delivered {
                        let _ = with_evidence(&evidence, |observed| { observed.fail("B output ring exhausted"); Ok(()) });
                        break;
                    }
                }
            }));
            Ok(run)
        }

        fn send(&mut self, bytes: &[u8]) -> io::Result<()> {
            let ip = packet::envelope(bytes)?;
            require(bytes.len() <= MTU as usize && ip.source == CLIENT
                && self.destinations.contains(&ip.destination)
                && matches!(ip.protocol, IpProtocol::Tcp | IpProtocol::Udp),
                "client injection escaped the fixture tuple scope")?;
            with_evidence(&self.evidence, |observed| PacketEvidence::record(&mut observed.injected, bytes))?;
            // Never call PacketBridge.input here. This is an NDIS receive into
            // Windows on A; the B driver's reader must independently see it.
            send_packet(&self.lan.device()?, bytes)?;
            self.injected_packets += 1;
            self.check_pumps()
        }

        fn check_pumps(&self) -> io::Result<()> {
            with_evidence(&self.evidence, |observed| require(observed.errors.is_empty(), observed.errors.join("; ")))
        }

        fn receive(&self, deadline: Instant) -> io::Result<Vec<u8>> {
            loop {
                self.check_pumps()?;
                let remaining = deadline.saturating_duration_since(Instant::now());
                require(!remaining.is_zero(), "Windows forwarding response timed out")?;
                match self.client_packets.recv_timeout(remaining.min(Duration::from_millis(100))) {
                    Ok(bytes) => return Ok(bytes),
                    Err(mpsc::RecvTimeoutError::Timeout) => continue,
                    Err(error) => return Err(io::Error::other(error)),
                }
            }
        }

        fn stop(&mut self) -> io::Result<()> {
            if self.stopped { return Ok(()); }
            let mut errors = Vec::new();
            // Entry forwarding is quiesced before any B capture route or
            // return forwarding is restored. Physical interfaces are untouched.
            if let Err(error) = self.lan.quiesce() {
                errors.push(format!("entry quiesce: {error}"));
                // This exclusively owned driver ingress cannot be left alive
                // while its forwarding ownership is uncertain.
                if let Some(device) = &self.lan.device { let _ = device.shutdown(); }
            }
            if let Err(error) = self.capture.restore() { errors.push(format!("B restore: {error}")); }
            if let Err(error) = self.lan.restore() { errors.push(format!("A restore: {error}")); }
            self.closing.store(true, Ordering::Release);
            for adapter in [&self.lan, &self.capture] {
                if let Some(device) = &adapter.device && let Err(error) = device.shutdown() {
                    errors.push(format!("driver shutdown: {error}"));
                }
            }
            if let Err(error) = self.runtime.block_on(self.control.shutdown()) { errors.push(format!("Core bridge shutdown: {error}")); }
            if let Some(writer) = self.writer.take() {
                writer.abort();
                let _ = self.runtime.block_on(writer);
            }
            for reader in self.readers.drain(..) {
                if reader.join().is_err() { errors.push("driver reader panicked".into()); }
            }
            self.lan.device.take();
            self.capture.device.take();
            self.stopped = true;
            if errors.is_empty() && let Some(binding) = self.binding.take() {
                binding.release_after_routes_restored()?;
            }
            require(errors.is_empty(), errors.join("; "))
        }
    }

    impl Drop for ForwardRun {
        fn drop(&mut self) {
            if let Err(error) = self.stop() { eprintln!("Gateway forwarding smoke cleanup incomplete: {error}"); }
        }
    }

    fn counter(core: &Core, name: &str) -> io::Result<u64> {
        core.snapshot().map_err(io::Error::other)?[name].as_u64()
            .ok_or_else(|| io::Error::other(format!("Core counter missing: {name}")))
    }

    fn forwarding_disabled_control(run: &mut ForwardRun, core: &Core, port: u16) -> io::Result<()> {
        let received = with_evidence(&run.evidence, |evidence| Ok(evidence.forwarded_into_core))?;
        let accepted = counter(core, "accepted")?;
        run.send(&packet::udp_packet(SocketAddrV4::new(CLIENT, port), SocketAddrV4::new(DNS_IPV4, 53), &query(GOOD_HOST, false, port)))?;
        let until = Instant::now() + QUIET;
        while Instant::now() < until {
            run.check_pumps()?;
            require(with_evidence(&run.evidence, |evidence| Ok(evidence.forwarded_into_core))? == received,
                "entry Forwarding=Disabled still delivered a packet to B")?;
            thread::sleep(Duration::from_millis(10));
        }
        require(counter(core, "accepted")? == accepted, "disabled entry still admitted a Core flow")
    }

    fn udp_dns(run: &mut ForwardRun, request: &[u8], port: u16) -> io::Result<Vec<u8>> {
        let source = SocketAddrV4::new(CLIENT, port);
        let destination = SocketAddrV4::new(DNS_IPV4, 53);
        run.send(&packet::udp_packet(source, destination, request))?;
        let deadline = Instant::now() + WAIT;
        loop {
            let bytes = run.receive(deadline)?;
            if let Some((from, to, payload)) = packet::udp_datagram(&bytes)?
                && (from, to) == (destination, source) {
                return Ok(payload);
            }
        }
    }

    fn next_tcp(run: &ForwardRun, source: SocketAddrV4, destination: SocketAddrV4, deadline: Instant) -> io::Result<packet::Segment> {
        loop {
            let bytes = run.receive(deadline)?;
            if let Some(segment) = packet::tcp_segment(&bytes)?
                && (segment.source, segment.destination) == (destination, source) {
                return Ok(segment);
            }
        }
    }

    fn handshake(run: &mut ForwardRun, source: SocketAddrV4, destination: SocketAddrV4) -> io::Result<i32> {
        run.send(&packet::tcp_packet(source, destination, 100, None, TcpControl::Syn, &[]))?;
        let syn_ack = next_tcp(run, source, destination, Instant::now() + WAIT)?;
        require(syn_ack.control == TcpControl::Syn && syn_ack.acknowledgement == Some(101), "forwarded TCP SYN/ACK mismatch")?;
        let next = syn_ack.sequence.wrapping_add(1);
        run.send(&packet::tcp_packet(source, destination, 101, Some(next), TcpControl::None, &[]))?;
        Ok(next)
    }

    fn tcp_dns(run: &mut ForwardRun, request: &[u8]) -> io::Result<Vec<u8>> {
        let source = SocketAddrV4::new(CLIENT, 42053);
        let destination = SocketAddrV4::new(DNS_IPV4, 53);
        let mut server_next = handshake(run, source, destination)?;
        let mut framed = (request.len() as u16).to_be_bytes().to_vec();
        framed.extend_from_slice(request);
        run.send(&packet::tcp_packet(source, destination, 101, Some(server_next), TcpControl::Psh, &framed))?;
        let client_fin = 101 + framed.len() as i32;
        run.send(&packet::tcp_packet(source, destination, client_fin, Some(server_next), TcpControl::Fin, &[]))?;
        let deadline = Instant::now() + WAIT;
        let mut response = Vec::new();
        loop {
            let segment = next_tcp(run, source, destination, deadline)?;
            require(segment.control != TcpControl::Rst, "forwarded DNS TCP reset")?;
            if !segment.payload.is_empty() {
                require(segment.sequence == server_next, "forwarded DNS TCP data sequence")?;
                server_next = server_next.wrapping_add(segment.payload.len() as i32);
                response.extend_from_slice(&segment.payload);
                require(response.len() <= 4096, "forwarded DNS TCP response exceeded limit")?;
            }
            let finished = segment.control == TcpControl::Fin;
            if finished { server_next = server_next.wrapping_add(1); }
            run.send(&packet::tcp_packet(source, destination, client_fin + 1, Some(server_next), TcpControl::None, &[]))?;
            if finished { break; }
        }
        require(response.len() >= 2, "missing DNS TCP length")?;
        let length = usize::from(u16::from_be_bytes([response[0], response[1]]));
        require(length == response.len() - 2, "DNS TCP length mismatch")?;
        Ok(response[2..].to_vec())
    }

    struct HostTraps {
        tcp: TcpListener,
        udp: UdpSocket,
    }

    impl HostTraps {
        fn new() -> io::Result<Self> {
            let tcp = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
            tcp.set_nonblocking(true)?;
            let udp = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0))?;
            udp.set_read_timeout(Some(QUIET))?;
            Ok(Self { tcp, udp })
        }

        fn control(&self) -> io::Result<()> {
            let client = TcpStream::connect_timeout(&self.tcp.local_addr()?, WAIT)?;
            let deadline = Instant::now() + WAIT;
            loop {
                match self.tcp.accept() {
                    Ok((accepted, peer)) => {
                        require(peer == client.local_addr()?, "TCP trap control source mismatch")?;
                        drop(accepted);
                        break;
                    }
                    Err(error) if error.kind() == io::ErrorKind::WouldBlock && Instant::now() < deadline => thread::sleep(Duration::from_millis(1)),
                    Err(error) => return Err(error),
                }
            }
            drop(client);
            let udp = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0))?;
            let challenge = b"Swirl gateway protected-target control";
            udp.send_to(challenge, self.udp.local_addr()?)?;
            let mut buffer = [0u8; 128];
            let (length, peer) = self.udp.recv_from(&mut buffer)?;
            require(peer == udp.local_addr()? && &buffer[..length] == challenge, "UDP trap control payload or source mismatch")
        }

        fn undelivered(&self) -> io::Result<()> {
            match self.tcp.accept() {
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
                Ok(_) => return Err(io::Error::other("protected TCP trap received a gateway connection")),
                Err(error) => return Err(error),
            }
            let mut buffer = [0u8; 256];
            match self.udp.recv_from(&mut buffer) {
                Err(error) if matches!(error.kind(), io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut) => Ok(()),
                Ok(_) => Err(io::Error::other("protected UDP trap received a gateway datagram")),
                Err(error) => Err(error),
            }
        }
    }

    fn wait_gateway_failure(core: &Core, run: &ForwardRun, accepted: u64, failed: u64, tcp: bool, bridge_failures: u64) -> io::Result<()> {
        let deadline = Instant::now() + WAIT;
        loop {
            run.check_pumps()?;
            let snapshot = core.snapshot().map_err(io::Error::other)?;
            let observed = if tcp { &run.bridge_stats.tcp_failures } else { &run.bridge_stats.udp_failures };
            if snapshot["failed"].as_u64().is_some_and(|count| count > failed)
                && observed.load(Ordering::Relaxed) > bridge_failures {
                require(snapshot["failed"] == failed + 1 && snapshot["accepted"] == accepted + 1,
                    "protected target did not produce exactly one Core admission/failure")?;
                return require(snapshot["last_error"] == "GatewayHostAccessDenied", format!("protected target failed for an unrelated reason: {}", snapshot["last_error"]));
            }
            require(Instant::now() < deadline, format!("protected target Core rejection timed out: accepted={} failed={} last_error={}", snapshot["accepted"], snapshot["failed"], snapshot["last_error"]))?;
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn protected_targets(run: &mut ForwardRun, core: &Core, fake: Ipv4Addr) -> io::Result<()> {
        let traps = HostTraps::new()?;
        traps.control()?;
        let accepted = counter(core, "accepted")?;
        let failed = counter(core, "failed")?;
        let bridge_failures = run.bridge_stats.tcp_failures.load(Ordering::Relaxed);
        let source = SocketAddrV4::new(CLIENT, 42180);
        let destination = SocketAddrV4::new(fake, traps.tcp.local_addr()?.port());
        let next = handshake(run, source, destination)?;
        run.send(&packet::tcp_packet(source, destination, 101, Some(next), TcpControl::Psh, b"must never reach host TCP"))?;
        wait_gateway_failure(core, run, accepted, failed, true, bridge_failures)?;
        let accepted = counter(core, "accepted")?;
        let failed = counter(core, "failed")?;
        let bridge_failures = run.bridge_stats.udp_failures.load(Ordering::Relaxed);
        run.send(&packet::udp_packet(SocketAddrV4::new(CLIENT, 42181), SocketAddrV4::new(fake, traps.udp.local_addr()?.port()), b"must never reach host UDP"))?;
        wait_gateway_failure(core, run, accepted, failed, false, bridge_failures)?;
        traps.undelivered()?;
        traps.control()?;
        traps.undelivered()?;
        Ok(())
    }

    fn exercise(run: &mut ForwardRun, core: &Core, dns: &TunDns, fake: [Ipv4Addr; 2]) -> io::Result<serde_json::Value> {
        // A negative control is necessary: mere Forwarding readback would not
        // establish that the observed packets actually used Windows routing.
        forwarding_disabled_control(run, core, 41990)?;
        run.lan.apply_through(run.lan.journal.changes.len())?;
        require(!windows_network::snapshot_network_configuration()?.adapters.iter()
            .flat_map(|adapter| &adapter.addresses).any(|address| address.address == CLIENT.to_string()),
            "synthetic client became a local Windows address")?;
        let accepted_before = counter(core, "accepted")?;
        let request = query(GOOD_HOST, false, 0x6001);
        let response = udp_dns(run, &request, 41053)?;
        require(dns_answer(&request, &response)? == fake[0], "forwarded UDP DNS Fake-IP changed")?;
        let request = query(GOOD_HOST, false, 0x6002);
        let response = tcp_dns(run, &request)?;
        require(dns_answer(&request, &response)? == fake[0], "forwarded TCP DNS Fake-IP changed")?;
        require(run.runtime.block_on(dns.target_host(fake[0].into())).map_err(io::Error::other)? == GOOD_HOST,
            "forwarded DNS result lost shared Fake-IP reverse identity")?;
        require(counter(core, "accepted")? == accepted_before + 2, "forwarded UDP/TCP DNS did not use the existing Core resolver")?;
        let request = query(GOOD_HOST, true, 0x6003);
        let response = udp_dns(run, &request, 41054)?;
        require(response.len() == request.len() && response[..2] == request[..2]
            && response[2] & 0x80 != 0 && response[3] & 15 == 0
            && response[4..12] == [0, 1, 0, 0, 0, 0, 0, 0] && response[12..] == request[12..],
            "IPv4-only gateway AAAA must return NODATA")?;
        require(counter(core, "accepted")? == accepted_before + 2, "LAN AAAA NODATA unexpectedly performed a Core DNS lookup")?;
        eprintln!("Gateway forwarding smoke: PASS Windows A -> B -> Core DNS UDP/TCP -> B -> A, TTL and exact payload identity");
        protected_targets(run, core, fake[1])?;
        require(run.stats.snapshot().malformed_packets == 0, "fixture emitted malformed stack packets")?;
        require(run.bridge_stats.dns_failures.load(Ordering::Relaxed) == 0, "forwarded DNS bridge failed")?;
        run.lan.quiesce()?;
        forwarding_disabled_control(run, core, 41991)?;
        run.check_pumps()?;
        let (ingress, replies) = with_evidence(&run.evidence, |evidence| Ok((evidence.forwarded_into_core, evidence.forwarded_to_client)))?;
        require(ingress > 0 && replies > 0 && run.returned_packets.load(Ordering::Relaxed) > 0,
            "both Windows forwarding hops require actual driver packets")?;
        Ok(json!({
            "client_ipv4":CLIENT.to_string(),"client_address_assigned_to_windows":false,
            "core_dns_admissions":2,"gateway_aaaa_nodata":true,
            "protected_tcp_rejection":"GatewayHostAccessDenied","protected_udp_rejection":"GatewayHostAccessDenied",
            "protected_traps_undelivered":true,"trap_controls_before_and_after":true,
            "entry_disabled_before_and_after_blocks_core_ingress":true,
            "client_injected_packets":run.injected_packets,"windows_forwarded_into_core":ingress,
            "core_injected_replies":run.returned_packets.load(Ordering::Relaxed),"windows_forwarded_back_to_client":replies,
            "both_hops_exact_payload_and_ttl_decrement":true,
            "dns_a_udp":true,"dns_a_tcp":true,"dns_shared_fake_ip":true
        }))
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        // This non-privileged test runs without opening a Wintun adapter. It
        // proves that the evidence check rejects a bypassed forwarding hop or
        // changed payload, rather than merely matching client/server tuples.
        #[test]
        fn packet_evidence_requires_one_router_hop_and_identical_payload() {
            let source = SocketAddrV4::new(CLIENT, 41053);
            let destination = SocketAddrV4::new(DNS_IPV4, 53);
            let original = packet::udp_packet(source, destination, b"fixture");
            let (from, to, payload) = packet::udp_datagram(&original).unwrap().unwrap();
            assert_eq!((from, to, payload), (source, destination, b"fixture".to_vec()));
            let mut evidence = PacketEvidence::default();
            PacketEvidence::record(&mut evidence.injected, &original).unwrap();
            assert!(PacketEvidence::verify(&evidence.injected, &original).is_err());
            let mut forwarded = original.clone();
            forwarded[8] -= 1;
            forwarded[10..12].fill(0);
            let sum: u32 = forwarded[..20].chunks_exact(2)
                .map(|pair| u32::from(u16::from_be_bytes([pair[0], pair[1]]))).sum();
            let sum = (sum & 0xffff) + (sum >> 16);
            let checksum = !(((sum & 0xffff) + (sum >> 16)) as u16);
            forwarded[10..12].copy_from_slice(&checksum.to_be_bytes());
            PacketEvidence::verify(&evidence.injected, &forwarded).unwrap();
            *forwarded.last_mut().unwrap() ^= 1;
            assert!(PacketEvidence::verify(&evidence.injected, &forwarded).is_err());
            assert!(packet::udp_datagram(&forwarded).is_err());

            let tcp = packet::tcp_packet(source, destination, 100, None, TcpControl::Syn, &[]);
            let segment = packet::tcp_segment(&tcp).unwrap().unwrap();
            assert_eq!((segment.source, segment.destination), (source, destination));
            assert_eq!((segment.sequence, segment.acknowledgement, segment.control), (100, None, TcpControl::Syn));
            assert!(segment.payload.is_empty());
        }
    }

    pub fn run(driver: PathBuf) -> io::Result<()> {
        require(driver.is_absolute(), "driver path must be absolute")?;
        let directory = windows_network::secure_state_directory()?;
        let configuration_before = windows_network::snapshot_network_configuration()?;
        let (owner, _) = nonce()?;
        let fake_path = directory.join(format!("gateway-smoke-{owner}.fake-ip.jsonl"));
        let mut core = Core::start(runtime_config()?, STORE_ID.into(), 1,
            "b2000000-0000-4000-8000-000000000001".into()).map_err(io::Error::other)?;
        let dispatcher = core.flow_dispatcher().map_err(io::Error::other)?;
        let runtime = dispatcher.runtime_handle();
        let result = (|| -> io::Result<serde_json::Value> {
            let binding = EgressLease::acquire_suspended()?;
            let dns = TunDns::new(FakeIpStore::open(&fake_path, 8).map_err(io::Error::other)?);
            let lookup = Lookup(dispatcher.clone());
            let mut fake = [Ipv4Addr::UNSPECIFIED; 2];
            // Seed through the same Core before acquiring gateway admission.
            // This models a retained Fake-IP identity from an earlier host
            // session. The later LAN flow must recheck its protected target.
            for (index, name) in [GOOD_HOST, BLOCKED_HOST].into_iter().enumerate() {
                let request = query(name, false, 0x5000 + index as u16);
                let response = runtime.block_on(dns.answer(&request, &lookup)).map_err(io::Error::other)?;
                fake[index] = dns_answer(&request, &response)?;
            }
            drop(dns);
            let dns = TunDns::new(FakeIpStore::open(&fake_path, 8).map_err(io::Error::other)?);
            for (address, host) in fake.into_iter().zip([GOOD_HOST, BLOCKED_HOST]) {
                require(runtime.block_on(dns.target_host(address.into())).map_err(io::Error::other)? == host,
                    "durable Fake-IP reverse identity changed")?;
            }
            unused_scope(&configuration_before, &[LAN_HOST, CLIENT, CORE_HOST, DNS_IPV4, fake[0], fake[1]])?;
            let local = host_inventory(&configuration_before)?;
            let gateway = GatewayIngress {
                lan_subnet: "192.168.249.0/30".parse().map_err(io::Error::other)?,
                gateway: LAN_HOST,
                allowed_sources: vec!["192.168.249.2/32".parse().map_err(io::Error::other)?],
                local_sources: local.clone(), protected_hosts: local,
                max_tcp_per_client: 8, max_udp_per_client: 8, max_dns_per_client: 4,
            };
            gateway.validate()?;
            let packet = native_tun::spawn(dispatcher.clone(), dns.clone(), TunConfig {
                mtu: MTU as usize, max_tcp_flows: 8, max_udp_endpoints: 8,
                gateway: Some(gateway), ..TunConfig::default()
            }).map_err(io::Error::other)?;
            let mut run = ForwardRun::start(&driver, &directory, packet, runtime.clone(), vec![DNS_IPV4, fake[0], fake[1]], binding)?;
            let tests = exercise(&mut run, &core, &dns, fake);
            if tests.is_err() {
                let diagnostic = with_evidence(&run.evidence, |evidence| Ok(json!({
                    "lan_interface":run.lan.journal.interface,"core_interface":run.capture.journal.interface,
                    "client_injected":run.injected_packets,"forwarded_into_core":evidence.forwarded_into_core,
                    "core_replies_injected":run.returned_packets.load(Ordering::Relaxed),
                    "forwarded_back_to_client":evidence.forwarded_to_client,"pump_errors":evidence.errors,
                    "stack_received":run.stats.snapshot().received_packets,
                    "core_accepted":counter(&core,"accepted").ok(),"core_failed":counter(&core,"failed").ok()
                })));
                eprintln!("Gateway forwarding smoke failure evidence {diagnostic:?}");
            }
            let cleanup = run.stop();
            let stats = run.stats.snapshot();
            let mut errors = Vec::new();
            if let Err(error) = &tests { errors.push(format!("forwarded packet tests: {error}")); }
            if let Err(error) = cleanup { errors.push(format!("owned network recovery: {error}")); }
            if stats.active_tcp_flows != 0 || stats.active_udp_endpoints != 0 { errors.push("packet resources survived shutdown".into()); }
            require(errors.is_empty(), errors.join("; "))?;
            tests
        })();
        core.stop();
        let mut errors = Vec::new();
        if let Err(error) = &result { errors.push(error.to_string()); }
        // Execute the final comparison after setup or packet failures too;
        // removing adapters alone is not evidence of compare-restoration.
        match windows_network::snapshot_network_configuration() {
            Ok(after) => {
                let adapters_equal = configuration_before.adapters == after.adapters;
                let routes_equal = configuration_before.routes == after.routes;
                eprintln!("Gateway forwarding smoke full configuration {}", json!({
                    "adapters_equal":adapters_equal,"all_routes_equal":routes_equal,
                    "adapters_before":configuration_before.adapters.len(),"adapters_after":after.adapters.len(),
                    "routes_before":configuration_before.routes.len(),"routes_after":after.routes.len()
                }));
                if !adapters_equal { errors.push("original adapter/DNS/MTU/DHCP/metric snapshot changed".into()); }
                if !routes_equal { errors.push("original complete ActiveStore routes changed".into()); }
            }
            Err(error) => errors.push(format!("final full network inventory: {error}")),
        }
        require(errors.is_empty(), errors.join("; "))?;
        println!("{}", json!({
            "ok":true,"evidence":"disposable dual-Wintun Windows IPv4 forwarding mechanism",
            "source_sha":option_env!("SWIRL_SOURCE_SHA").unwrap_or("unknown"),
            "driver_version":"0.14.1","driver_sha256":official_driver_sha256()?,
            "results":result?,"owned_network_state_restored":true,"both_adapters_removed":true,
            "original_network_configuration_exact":true,"physical_forwarding_modified":false,
            "default_routes_modified":false,"physical_dns_modified":false,"firewall_modified":false,"dhcp_started":false,
            "physical_lan_ingress_acceptance":false,"production_wfp_packet_metadata_acceptance":false,
            "positive_external_tcp_udp_acceptance":false,"windows_11_application_acceptance":false
        }));
        Ok(())
    }
}
