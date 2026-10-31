//! Helper-owned isolation and forwarding phases around the existing TUN.
//! The two journals stay locked together: LAN forwarding is restored before
//! capture routes, and the persistent LAN guard is removed only afterwards.
use super::native_gateway_control::{DhcpAttachment, NativeGatewayConfig};
use ring::rand::{SecureRandom, SystemRandom};
use serde_json::{Value, json};
use std::{
    io,
    net::IpAddr,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};
use swirl_platform::{
    gateway_policy::GatewayIsolationPolicy,
    network_transaction::{
        self as transaction, FileJournalStore, InterfaceIdentity, Journal, JournalStore,
        NetworkBackend, Resource, Value as NetworkValue,
    },
    windows_gateway::{self, WindowsGatewayBackend},
};
use swirl_tun::gateway::GatewayIngress;

type Result<T> = std::result::Result<T, &'static str>;
const PREPARATION_WINDOW: Duration = Duration::from_secs(30);

fn code(error: io::Error) -> &'static str {
    match error.kind() {
        io::ErrorKind::PermissionDenied => "GatewayHelperPermission",
        io::ErrorKind::AlreadyExists => "GatewayNetworkConflict",
        io::ErrorKind::WouldBlock => "GatewayOwnedByAnotherHelper",
        _ => "GatewayWindowsNetworkOperation",
    }
}

pub(crate) fn journal_path(directory: &Path, guid: &str) -> PathBuf {
    directory.join(format!("{}.gateway.json", guid.replace('-', "")))
}

fn archive(path: &Path, journal: &Journal) -> Result<()> {
    if !journal.is_restored() {
        return Err("GatewayRecoveryConflict");
    }
    let name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or("GatewayJournalPath")?;
    let restored = path.with_file_name(format!("{name}.{}.restored", journal.owner));
    if restored.exists() {
        return Err("GatewayJournalArchiveExists");
    }
    std::fs::rename(path, restored).map_err(|_| "GatewayJournalArchive")
}

/// No Drop implementation removes isolation. A failed coordinator must leave
/// the durable guard for the supervising helper, even if TUN teardown fails.
pub(crate) struct GatewayState {
    policy: GatewayIsolationPolicy,
    backend: WindowsGatewayBackend,
    store: FileJournalStore,
    journal: Journal,
    path: PathBuf,
    prepared_at: Instant,
    next_verification: Instant,
    dhcp: Option<VerifiedDhcpOwner>,
    forwarding: bool,
    isolation: bool,
    restored: bool,
}

/// A duplicated socket token is single-use. Retain no socket handle, token or
/// serialized attachment after verification; polling uses stable owner identity.
struct VerifiedDhcpOwner {
    owner_pid: u32,
    owner_creation: String,
}

impl GatewayState {
    pub fn prepare(
        config: &NativeGatewayConfig,
        tun: &InterfaceIdentity,
        directory: &Path,
    ) -> Result<Self> {
        config.validate()?;
        let path = journal_path(directory, &config.lan.lan.guid);
        if path.exists() {
            return Err("GatewayRecoveryRequired");
        }
        let mut random = [0u8; 16];
        SystemRandom::new()
            .fill(&mut random)
            .map_err(|_| "GatewayRandom")?;
        let owner = random.iter().map(|byte| format!("{byte:02x}")).collect();
        let policy = windows_gateway::preflight(&config.lan, tun, owner).map_err(code)?;
        let mut backend = WindowsGatewayBackend::for_policy(policy.clone()).map_err(code)?;
        let journal = Journal::prepare(
            &mut backend,
            policy.lan.clone(),
            policy.owner.clone(),
            windows_gateway::desired_resources(&policy).map_err(code)?,
        )
        .map_err(code)?;
        let mut store = FileJournalStore::create_new(&path).map_err(code)?;
        store.save(&journal).map_err(|_| "GatewayJournalWrite")?;
        let mut state = Self {
            policy,
            backend,
            store,
            journal,
            path,
            prepared_at: Instant::now(),
            next_verification: Instant::now(),
            dhcp: None,
            forwarding: false,
            isolation: false,
            restored: false,
        };
        if transaction::apply_prefix(&mut state.backend, &mut state.store, &mut state.journal, 1)
            .is_err()
        {
            // No TUN routes have been applied. A fully owned preparation may
            // therefore be restored immediately; conflicting state survives.
            let _ = state.finish();
            return Err("GatewayIsolationApplyFailed");
        }
        state.isolation = true;
        if windows_gateway::verify(&state.policy, false).is_err() {
            let _ = state.finish();
            return Err("GatewayPreparationChanged");
        }
        Ok(state)
    }

    pub fn ingress(&self, config: &NativeGatewayConfig) -> Result<GatewayIngress> {
        let mut hosts = self.policy.host_addresses.clone();
        // These are assigned after the topology snapshot. The adjacent .2
        // synthetic DNS address is intentionally not a host-owned address.
        hosts.extend([
            "198.18.0.1"
                .parse::<IpAddr>()
                .map_err(|_| "GatewayTunAddress")?,
            "fd53:7769:726c::1"
                .parse::<IpAddr>()
                .map_err(|_| "GatewayTunAddress")?,
        ]);
        hosts.sort();
        hosts.dedup();
        let ingress = GatewayIngress {
            lan_subnet: self.policy.subnet,
            gateway: self.policy.gateway,
            allowed_sources: self.policy.allowed_sources.clone(),
            local_sources: hosts.clone(),
            protected_hosts: hosts,
            max_tcp_per_client: config.max_tcp_per_client,
            max_udp_per_client: config.max_udp_per_client,
            max_dns_per_client: config.max_dns_per_client,
        };
        ingress
            .validate()
            .map_err(|_| "GatewayIngressConfiguration")?;
        Ok(ingress)
    }

    pub fn ready(&mut self) -> Result<()> {
        self.verify()?;
        self.prepared_at = Instant::now();
        self.next_verification = Instant::now() + Duration::from_secs(1);
        Ok(())
    }

    pub fn activate(&mut self, preparation_id: &str, dhcp: Option<DhcpAttachment>) -> Result<()> {
        if self.restored || self.forwarding || preparation_id != self.policy.owner {
            return Err("GatewayPreparationIdentity");
        }
        if self.prepared_at.elapsed() > PREPARATION_WINDOW {
            return Err("GatewayPreparationExpired");
        }
        windows_gateway::verify(&self.policy, false).map_err(|_| "GatewayPreparationChanged")?;
        match (self.policy.dhcp, dhcp.as_ref()) {
            (true, Some(attachment)) => {
                attachment.validate()?;
                windows_gateway::attest_dhcp_socket(
                    &self.policy,
                    attachment.owner_pid,
                    &attachment.owner_creation,
                    attachment.target_helper_pid,
                    &attachment.protocol_info_base64,
                )
                .map_err(|_| "GatewayDhcpAttachmentNotVerified")?;
            }
            (true, None) => return Err("GatewayDhcpAttachmentRequired"),
            (false, Some(_)) => return Err("GatewayUnexpectedDhcpAttachment"),
            (false, None) => {}
        }
        // The previous isolation stage remains owned if forwarding activation
        // fails. The enclosing Active scope quiesces it before restoring TUN.
        transaction::apply_prefix(&mut self.backend, &mut self.store, &mut self.journal, 2)
            .map_err(|_| "GatewayForwardingApplyFailed")?;
        self.forwarding = true;
        windows_gateway::verify(&self.policy, true).map_err(|_| "GatewayActivationChanged")?;
        self.dhcp = dhcp.map(|attachment| VerifiedDhcpOwner {
            owner_pid: attachment.owner_pid,
            owner_creation: attachment.owner_creation,
        });
        self.next_verification = Instant::now() + Duration::from_secs(1);
        Ok(())
    }

    pub fn failure(&mut self) -> Option<&'static str> {
        if self.restored {
            return None;
        }
        if !self.forwarding && self.prepared_at.elapsed() > PREPARATION_WINDOW {
            return Some("GatewayPreparationExpired");
        }
        if Instant::now() < self.next_verification {
            return None;
        }
        self.next_verification = Instant::now() + Duration::from_secs(1);
        self.verify().err()
    }

    pub fn verify(&self) -> Result<()> {
        if windows_gateway::verify(&self.policy, self.forwarding).is_err() {
            return Err("GatewayNetworkChanged");
        }
        if let Some(attachment) = &self.dhcp
            && windows_gateway::verify_dhcp_attachment(
                &self.policy,
                attachment.owner_pid,
                &attachment.owner_creation,
            )
            .is_err()
        {
            return Err("GatewayDhcpAttachmentLost");
        }
        Ok(())
    }

    /// Called while the TUN device, routes and physical egress lease are alive.
    /// A missing interface is safe; a foreign true forwarding bit is not ours
    /// to change and leaves the guard/journal in recovery_required.
    pub fn quiesce(&mut self) -> Result<()> {
        if self.restored {
            return Ok(());
        }
        let report =
            transaction::recover_suffix(&mut self.backend, &mut self.store, &mut self.journal, 1)
                .map_err(|_| "GatewayQuiesceFailed")?;
        if !report.conflicts.is_empty() {
            return Err("GatewayQuiesceConflict");
        }
        match self
            .backend
            .read(&self.policy.lan, &Resource::Forwarding { ipv6: false })
        {
            Ok(None | Some(NetworkValue::Forwarding { enabled: false })) => {}
            _ => return Err("GatewayForwardingStillEnabled"),
        }
        self.forwarding = false;
        self.dhcp = None;
        Ok(())
    }

    /// Only the coordinator may call this after dependent TUN resources have
    /// been restored, or during a preparation failure before TUN applied them.
    pub fn finish(&mut self) -> Result<()> {
        if self.restored {
            return Ok(());
        }
        self.quiesce()?;
        let report = transaction::recover(&mut self.backend, &mut self.store, &mut self.journal)
            .map_err(|_| "GatewayRecoveryFailed")?;
        if !report.conflicts.is_empty() || !self.journal.is_restored() {
            return Err("GatewayRecoveryConflict");
        }
        archive(&self.path, &self.journal)?;
        self.isolation = false;
        self.restored = true;
        Ok(())
    }

    pub fn status(&self) -> Value {
        json!({"ipv4_only":true,"helper_worker_pid":std::process::id(),"lan_interface":self.policy.lan,
            "tun_interface":self.policy.tun,"lan_gateway":self.policy.gateway,
            "client_subnet":self.policy.subnet,"dns_ipv4":"198.18.0.2",
            "isolation_observed":self.isolation,"forwarding_observed":self.forwarding,
            "preparation_id":if !self.forwarding && !self.restored { Some(&self.policy.owner) } else { None },
            "preparation_expires_in_ms":PREPARATION_WINDOW.saturating_sub(self.prepared_at.elapsed()).as_millis(),
            "dhcp_required":self.policy.dhcp,"dhcp_attachment_verified":self.dhcp.is_some(),
            "journal_restored":self.restored,"observation_scope":"last_successful_readback",
            "automatic_restart":false})
    }
}

/// Hold every stale gateway lock while all corresponding TUN journals recover.
/// Drop deliberately leaves guards installed if any later phase fails.
pub(crate) struct RecoveryBatch {
    states: Vec<GatewayState>,
}

impl RecoveryBatch {
    pub fn is_empty(&self) -> bool {
        self.states.is_empty()
    }

    pub fn quiesce_all(directory: &Path) -> Result<Self> {
        let mut batch = Self { states: Vec::new() };
        let mut active_owner = false;
        for entry in std::fs::read_dir(directory).map_err(|_| "GatewayJournalDirectory")? {
            let entry = entry.map_err(|_| "GatewayJournalDirectory")?;
            let name = entry.file_name();
            let Some(stem) = name
                .to_str()
                .and_then(|name| name.strip_suffix(".gateway.json"))
            else {
                continue;
            };
            if stem.len() != 32 || !stem.bytes().all(|byte| byte.is_ascii_hexdigit()) {
                continue;
            }
            let path = entry.path();
            let (store, journal) = match FileJournalStore::open_existing(&path) {
                Ok(value) => value,
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    active_owner = true;
                    continue;
                }
                Err(_) => return Err("GatewayRecoveryJournalInvalid"),
            };
            if journal.interface.guid.replace('-', "") != stem {
                return Err("GatewayRecoveryJournalIdentity");
            }
            let Some(NetworkValue::GatewayIsolation { policy }) = journal
                .changes
                .first()
                .and_then(|change| change.after.as_ref())
            else {
                return Err("GatewayRecoveryJournalInvalid");
            };
            let policy = policy.clone();
            let backend = WindowsGatewayBackend::for_policy(policy.clone()).map_err(code)?;
            let mut state = GatewayState {
                policy,
                backend,
                store,
                journal,
                path,
                prepared_at: Instant::now(),
                next_verification: Instant::now(),
                dhcp: None,
                forwarding: true,
                isolation: true,
                restored: false,
            };
            state.quiesce()?;
            batch.states.push(state);
        }
        if active_owner {
            // Do not infer which capture generation a live helper is using.
            // Already-quiesced stale guards remain durable for the next pass.
            return Err("GatewayOwnedByAnotherHelper");
        }
        Ok(batch)
    }

    pub fn finish(mut self) -> Result<usize> {
        for state in &mut self.states {
            state.finish()?;
        }
        Ok(self.states.len())
    }
}
