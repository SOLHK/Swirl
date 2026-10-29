//! Explicit helper-owned Windows network lifecycle. No GUI/UAC code lives here.
use super::{
    native_tun::{self, BridgeControl, BridgeStats},
    native_tun_control::NativeTunConfig,
};
use ring::rand::{SecureRandom, SystemRandom};
use serde_json::{Value, json};
use std::{
    io,
    path::{Path, PathBuf},
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU64, Ordering},
    },
    thread,
    time::{Duration, Instant},
};
use swirl_core::v2::{FlowDispatcher, NativeTunLease};
use swirl_dns::tun::{DNS_IPV4, DNS_IPV6, FakeIpStore, TunDns};
use swirl_platform::{
    network_transaction::{
        self as transaction, FileJournalStore, InterfaceIdentity, Journal, Resource,
        Value as NetworkValue,
    },
    windows_network::{self, NetworkChangeWatcher, NetworkSnapshot, WindowsNetworkBackend},
    wintun_device::{WintunConfig, WintunDevice, official_driver_sha256},
};
use swirl_transport::egress::EgressLease;
use swirl_tun::TunStats;
use tokio::{runtime::Handle, task::JoinHandle};

type Result<T> = std::result::Result<T, &'static str>;

fn code(error: io::Error) -> &'static str {
    match error.kind() {
        io::ErrorKind::PermissionDenied => "TunHelperPermission",
        io::ErrorKind::AlreadyExists => "TunNetworkConflict",
        io::ErrorKind::NotFound | io::ErrorKind::NetworkUnreachable => {
            "TunPhysicalNetworkUnavailable"
        }
        io::ErrorKind::WouldBlock => "TunOwnedByAnotherHelper",
        _ => "TunWindowsNetworkOperation",
    }
}

fn egress(snapshot: &NetworkSnapshot, ipv6: bool) -> Result<Option<InterfaceIdentity>> {
    match snapshot.physical_egress(ipv6) {
        Ok(identity) => Ok(Some(identity)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(code(error)),
    }
}

fn owner() -> Result<String> {
    let mut bytes = [0u8; 16];
    SystemRandom::new()
        .fill(&mut bytes)
        .map_err(|_| "TunRandom")?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn journal_path(directory: &Path, guid: &str) -> PathBuf {
    directory.join(format!("{}.network.json", guid.replace('-', "")))
}

fn archive(path: &Path, journal: &Journal) -> Result<()> {
    if !journal.is_restored() {
        return Err("TunRecoveryConflict");
    }
    let stem = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or("TunJournalPath")?;
    let restored = path.with_file_name(format!("{stem}.{}.restored", journal.owner));
    if restored.exists() {
        return Err("TunJournalArchiveExists");
    }
    std::fs::rename(path, restored).map_err(|_| "TunJournalArchive")
}

/// This is the only scope which owns both a live adapter and applied routes.
struct Active {
    runtime: Handle,
    device: Arc<WintunDevice>,
    reader: Option<thread::JoinHandle<()>>,
    writer: Option<JoinHandle<()>>,
    closing: Arc<AtomicBool>,
    io_failed: Arc<AtomicBool>,
    packet_drops: Arc<AtomicU64>,
    bridge: BridgeControl,
    stats: TunStats,
    bridge_stats: Arc<BridgeStats>,
    backend: WindowsNetworkBackend,
    store: FileJournalStore,
    journal: Journal,
    path: PathBuf,
    watcher: Option<NetworkChangeWatcher>,
    restored: bool,
}

impl Active {
    fn start(
        dispatcher: &FlowDispatcher,
        dns: &TunDns,
        config: &NativeTunConfig,
        directory: &Path,
        binding: &mut EgressLease,
    ) -> Result<Self> {
        let path = journal_path(directory, &config.adapter_guid);
        if path.exists() {
            return Err("TunRecoveryRequired");
        }
        let snapshot = windows_network::snapshot().map_err(code)?;
        let v4 = egress(&snapshot, false)?;
        let v6 = egress(&snapshot, true)?;
        if v4.is_none() && v6.is_none() {
            return Err("TunPhysicalNetworkUnavailable");
        }
        // The session reserves binding BEFORE acquiring its first Core lease
        // and never releases it between adapters. New Core sockets therefore
        // cannot enter a later capture generation without physical binding.
        binding
            .update(v4.as_ref().map(|v| v.index), v6.as_ref().map(|v| v.index))
            .map_err(|_| "TunEgressUnavailable")?;
        let setup = (|| {
            let packet = native_tun::spawn(dispatcher.clone(), dns.clone(), config.stack_config())?;
            let device = Arc::new(
                WintunDevice::create(&WintunConfig {
                    driver_path: config.driver_path.clone(),
                    expected_sha256: official_driver_sha256().map_err(code)?.into(),
                    adapter_name: config.adapter_name.clone(),
                    adapter_guid: config.guid()?,
                    ring_capacity: 4 * 1024 * 1024,
                })
                .map_err(code)?,
            );
            let identity = InterfaceIdentity::new(
                device.interface_index().map_err(code)?,
                device.adapter_guid(),
            );
            // Watch before the final physical snapshot. Otherwise an interface
            // change during the comparatively slow transaction preparation can
            // be lost before notification registration and leave stale egress.
            let watcher = NetworkChangeWatcher::new(identity.index).map_err(code)?;
            let snapshot = windows_network::snapshot().map_err(code)?;
            let v4 = egress(&snapshot, false)?;
            let v6 = egress(&snapshot, true)?;
            if v4.is_none() && v6.is_none() {
                return Err("TunPhysicalNetworkUnavailable");
            }
            binding
                .update(v4.as_ref().map(|v| v.index), v6.as_ref().map(|v| v.index))
                .map_err(|_| "TunEgressUnavailable")?;
            if [v4.as_ref(), v6.as_ref()]
                .into_iter()
                .flatten()
                .any(|i| i.index == identity.index)
            {
                return Err("TunEgressIsTunnel");
            }
            let mut backend =
                WindowsNetworkBackend::for_owned_interface(identity.clone()).map_err(code)?;
            let nonce = owner()?;
            let aliases = snapshot
                .adapters
                .iter()
                .filter(|adapter| adapter.hardware)
                .map(|adapter| adapter.name.clone())
                .collect::<Vec<_>>();
            let mut desired =
                transaction::dns_guard_resources(&identity, &nonce, &aliases).map_err(code)?;
            for ipv6 in [false, true] {
                desired.push((
                    Resource::Mtu { ipv6 },
                    Some(NetworkValue::Mtu {
                        mtu: u32::from(config.mtu),
                    }),
                ));
            }
            desired.extend(
                transaction::capture_resources(
                    &[
                        "198.18.0.1/30".parse().map_err(|_| "TunAddress")?,
                        "fd53:7769:726c::1/126".parse().map_err(|_| "TunAddress")?,
                    ],
                    &[DNS_IPV4.into(), DNS_IPV6.into()],
                    5,
                )
                .map_err(code)?,
            );
            let journal =
                Journal::prepare(&mut backend, identity.clone(), nonce, desired).map_err(code)?;
            let mut store = FileJournalStore::create_new(&path).map_err(code)?;
            if transaction::JournalStore::save(&mut store, &journal).is_err() {
                // This file was created by this call and no OS write has run.
                let _ = std::fs::remove_file(&path);
                return Err("TunJournalWrite");
            }
            Ok((packet, device, watcher, backend, journal, store))
        })();
        let (packet, device, watcher, backend, journal, store) = match setup {
            Ok(value) => value,
            Err(error) => {
                let _ = binding.suspend();
                return Err(error);
            }
        };
        let runtime = dispatcher.runtime_handle();
        let closing = Arc::new(AtomicBool::new(false));
        let io_failed = Arc::new(AtomicBool::new(false));
        let packet_drops = Arc::new(AtomicU64::new(0));
        let incoming = packet.input;
        let reader_device = device.clone();
        let reader_closing = closing.clone();
        let reader_failed = io_failed.clone();
        let reader_drops = packet_drops.clone();
        let mtu = usize::from(config.mtu);
        let reader = thread::Builder::new()
            .name("swirl-wintun-read".into())
            .spawn(move || {
                while !reader_closing.load(Ordering::Acquire) {
                    let mut bytes = Vec::with_capacity(mtu);
                    match reader_device.receive_blocking(&mut bytes) {
                        Ok(()) => {
                            if bytes.len() > mtu {
                                reader_drops.fetch_add(1, Ordering::Relaxed);
                                continue;
                            }
                            if incoming.blocking_send(bytes).is_err() {
                                break;
                            }
                        }
                        Err(_) if reader_closing.load(Ordering::Acquire) => break,
                        Err(_) => {
                            reader_failed.store(true, Ordering::Release);
                            break;
                        }
                    }
                }
            })
            .map_err(|_| "TunReaderThread");
        let reader = match reader {
            Ok(reader) => reader,
            Err(error) => {
                // Only our complete Pending journal exists: no OS writes ran.
                // Remove it so a recoverable thread allocation failure does not
                // permanently poison this adapter's next startup attempt.
                let _ = std::fs::remove_file(&path);
                let _ = binding.suspend();
                return Err(error);
            }
        };
        let mut output = packet.output;
        let writer_device = device.clone();
        let writer_failed = io_failed.clone();
        let writer_drops = packet_drops.clone();
        let writer_closing = closing.clone();
        let writer = runtime.spawn(async move {
            while let Some(bytes) = output.recv().await {
                let mut delivered = false;
                for _ in 0..16 {
                    match writer_device.send(&bytes) {
                        Ok(()) => {
                            delivered = true;
                            break;
                        }
                        Err(error)
                            if error.raw_os_error() == Some(111)
                                || error.kind() == io::ErrorKind::WouldBlock =>
                        {
                            tokio::time::sleep(Duration::from_millis(1)).await;
                        }
                        Err(_) if writer_closing.load(Ordering::Acquire) => return,
                        Err(_) => {
                            writer_failed.store(true, Ordering::Release);
                            return;
                        }
                    }
                }
                if !delivered {
                    writer_drops.fetch_add(1, Ordering::Relaxed);
                }
            }
        });
        let mut active = Self {
            runtime,
            device,
            reader: Some(reader),
            writer: Some(writer),
            closing,
            io_failed,
            packet_drops,
            bridge: packet.control,
            stats: packet.stats,
            bridge_stats: packet.bridge_stats,
            backend,
            store,
            journal,
            path,
            watcher: Some(watcher),
            restored: false,
        };
        if transaction::apply(&mut active.backend, &mut active.store, &mut active.journal).is_err()
        {
            // apply has already attempted a compare-and-restore rollback.
            // Drop retries recovery; the durable journal remains for supervisor.
            return Err("TunNetworkApplyFailed");
        }
        Ok(active)
    }

    fn stop(&mut self) -> Result<()> {
        if self.restored {
            return Ok(());
        }
        if let Some(mut watcher) = self.watcher.take() {
            // Network restoration must still run if an observer cannot close;
            // the platform wrapper retains callback storage safely on failure.
            let _ = watcher.close();
        }
        let recovered = transaction::recover(&mut self.backend, &mut self.store, &mut self.journal)
            .map_err(|_| "TunRecoveryFailed")?;
        if !recovered.conflicts.is_empty() || !self.journal.is_restored() {
            return Err("TunRecoveryConflict");
        }
        self.closing.store(true, Ordering::Release);
        self.device.shutdown().map_err(code)?;
        self.runtime.block_on(self.bridge.shutdown())?;
        if let Some(writer) = self.writer.take() {
            writer.abort();
            let _ = self.runtime.block_on(writer);
        }
        if let Some(reader) = self.reader.take() {
            reader.join().map_err(|_| "TunReaderPanic")?;
        }
        archive(&self.path, &self.journal)?;
        self.restored = true;
        Ok(())
    }

    fn failure_or_change(&self) -> Option<&'static str> {
        if self.io_failed.load(Ordering::Acquire) || self.bridge.is_finished() {
            Some("TunPacketPumpStopped")
        } else if self
            .watcher
            .as_ref()
            .is_some_and(|watcher| watcher.take_changed())
        {
            Some("TunNetworkChanged")
        } else {
            None
        }
    }

    fn status(&self) -> Value {
        let stats = self.stats.snapshot();
        json!({
            "interface_index":self.journal.interface.index,
            "packets":stats.received_packets,"malformed_packets":stats.malformed_packets,
            "active_tcp_flows":stats.active_tcp_flows,"active_udp_endpoints":stats.active_udp_endpoints,
            "rejected_tcp_flows":stats.rejected_tcp_flows,
            "udp_dropped":stats.dropped_udp_datagrams + self.bridge_stats.udp_dropped.load(Ordering::Relaxed),
            "packet_io_dropped":self.packet_drops.load(Ordering::Relaxed),
            "tcp_failures":self.bridge_stats.tcp_failures.load(Ordering::Relaxed),
            "udp_failures":self.bridge_stats.udp_failures.load(Ordering::Relaxed),
            "dns_failures":self.bridge_stats.dns_failures.load(Ordering::Relaxed)
        })
    }
}

impl Drop for Active {
    fn drop(&mut self) {
        if self.stop().is_err() {
            // The supervisor handles a surviving journal after process exit.
            // Do not clear the egress lease while owned capture may still exist.
            self.closing.store(true, Ordering::Release);
            let _ = self.device.shutdown();
            self.bridge.request_stop();
            if let Some(writer) = self.writer.take() {
                writer.abort();
            }
        }
    }
}

pub(crate) struct NativeSession {
    dispatcher: FlowDispatcher,
    config: NativeTunConfig,
    directory: PathBuf,
    dns: TunDns,
    active: Option<Active>,
    // A single owner spans running, paused and rebuilding states. Releasing it
    // during a pause would admit unbound Core sockets into the next capture.
    binding: Option<EgressLease>,
    // Retains strict DNS admission during network loss/restart as well.
    _epoch_lease: NativeTunLease,
    desired: bool,
    state: &'static str,
    last_error: Option<&'static str>,
    next_retry: Instant,
}

impl NativeSession {
    pub fn start(dispatcher: FlowDispatcher, config: NativeTunConfig) -> Result<Self> {
        config.validate()?;
        let directory = windows_network::secure_state_directory().map_err(code)?;
        let dns = TunDns::new(FakeIpStore::open(
            &directory.join("fake-ip-v1.jsonl"),
            16384,
        )?);
        let binding = EgressLease::acquire_suspended().map_err(|_| "TunEgressUnavailable")?;
        let epoch_lease = match dispatcher.prepare_native_tun() {
            Ok(lease) => lease,
            Err(error) => {
                let _ = binding.release_after_routes_restored();
                return Err(error);
            }
        };
        let mut session = Self {
            dispatcher,
            config,
            directory,
            dns,
            active: None,
            binding: Some(binding),
            _epoch_lease: epoch_lease,
            desired: true,
            state: "starting",
            last_error: None,
            next_retry: Instant::now(),
        };
        session.active = Some(Active::start(
            &session.dispatcher,
            &session.dns,
            &session.config,
            &session.directory,
            session.binding.as_mut().ok_or("TunEgressUnavailable")?,
        )?);
        session.state = "running";
        Ok(session)
    }

    pub fn maintain(&mut self) {
        if !self.desired || self.state == "recovery_required" {
            return;
        }
        if let Some(reason) = self.active.as_ref().and_then(Active::failure_or_change) {
            self.last_error = Some(reason);
            if self
                .binding
                .as_mut()
                .is_none_or(|binding| binding.suspend().is_err())
            {
                self.state = "recovery_required";
                self.last_error = Some("TunEgressUnavailable");
                return;
            }
            if self
                .active
                .as_mut()
                .is_some_and(|active| active.stop().is_err())
            {
                self.state = "recovery_required";
                return;
            }
            self.active = None;
            self.state = "waiting_for_network";
            self.next_retry = Instant::now() + Duration::from_secs(1);
        }
        if self.active.is_none() && Instant::now() >= self.next_retry {
            let Some(binding) = self.binding.as_mut() else {
                self.state = "recovery_required";
                self.last_error = Some("TunEgressUnavailable");
                return;
            };
            match Active::start(
                &self.dispatcher,
                &self.dns,
                &self.config,
                &self.directory,
                binding,
            ) {
                Ok(active) => {
                    self.active = Some(active);
                    self.state = "running";
                    self.last_error = None;
                }
                Err(error) => {
                    let _ = binding.suspend();
                    self.last_error = Some(error);
                    if journal_path(&self.directory, &self.config.adapter_guid).exists() {
                        self.state = "recovery_required";
                    }
                    self.next_retry = Instant::now() + Duration::from_secs(5);
                }
            }
        }
    }

    pub fn stop(&mut self) -> Result<()> {
        self.desired = false;
        let result = self.stop_inner();
        if let Err(error) = result {
            self.state = "recovery_required";
            self.last_error = Some(error);
        }
        result
    }

    fn stop_inner(&mut self) -> Result<()> {
        if let Some(binding) = self.binding.as_mut() {
            binding.suspend().map_err(|_| "TunEgressUnavailable")?;
        }
        if let Some(active) = &mut self.active {
            active.stop()?;
        }
        self.active = None;
        if journal_path(&self.directory, &self.config.adapter_guid).exists() {
            return Err("TunRecoveryRequired");
        }
        if let Some(binding) = self.binding.take() {
            binding
                .release_after_routes_restored()
                .map_err(|_| "TunEgressRelease")?;
        }
        self.state = "stopped";
        Ok(())
    }

    pub fn status(&self) -> Value {
        let capture_active = match self.state {
            "running" => Some(true),
            "stopped" | "waiting_for_network" => Some(false),
            _ => None,
        };
        json!({"state":self.state,"desired_enabled":self.desired,"last_error":self.last_error,
            "capture_active":capture_active,
            "dns_guard_active":capture_active,
            "core_egress_guard_owned":self.binding.is_some(),
            "statistics":self.active.as_ref().map(Active::status),
            "capabilities":super::native_tun_control::capabilities()})
    }
}

impl Drop for NativeSession {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

/// Used by the supervising helper after its worker exits, and before accepting
/// a new session. Only fixed-name journals in the protected state directory are
/// read. A live owner's lock and every third-party network change are respected.
pub(crate) fn recover_stale() -> Result<Value> {
    let directory = windows_network::secure_state_directory().map_err(code)?;
    let mut restored = 0;
    let mut active = 0;
    let mut conflicts = 0;
    let entries = std::fs::read_dir(&directory).map_err(|_| "TunJournalDirectory")?;
    for entry in entries {
        let entry = entry.map_err(|_| "TunJournalDirectory")?;
        let name = entry.file_name();
        let Some(stem) = name
            .to_str()
            .and_then(|name| name.strip_suffix(".network.json"))
        else {
            continue;
        };
        if stem.len() != 32 || !stem.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            continue;
        }
        let path = entry.path();
        let (mut store, mut journal) = match FileJournalStore::open_existing(&path) {
            Ok(value) => value,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                active += 1;
                continue;
            }
            Err(_) => return Err("TunRecoveryJournalInvalid"),
        };
        if journal.interface.guid.replace('-', "") != stem {
            return Err("TunRecoveryJournalIdentity");
        }
        let mut backend =
            WindowsNetworkBackend::for_owned_interface(journal.interface.clone()).map_err(code)?;
        let report = transaction::recover(&mut backend, &mut store, &mut journal)
            .map_err(|_| "TunRecoveryFailed")?;
        if report.conflicts.is_empty() && journal.is_restored() {
            archive(&path, &journal)?;
            restored += 1;
        } else {
            conflicts += 1;
        }
    }
    if conflicts != 0 {
        return Err("TunRecoveryConflict");
    }
    if active == 0 {
        swirl_transport::egress::release_orphan_after_routes_restored()
            .map_err(|_| "TunEgressStillOwned")?;
    }
    Ok(json!({"state":"recovered","journals_restored":restored,"active_owners":active}))
}
