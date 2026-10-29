//! Write-ahead network changes for a dedicated Swirl TUN interface.
//!
//! A backend must recheck both the interface identity and the expected value in
//! `compare_exchange`. Recovery restores a value only when it still equals the
//! value this transaction installed. It never overwrites a later administrator,
//! VPN or DHCP change. A journal is evidence of ownership, not authorization:
//! the privileged helper must keep it in an administrator-owned directory.
use ipnet::IpNet;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashSet,
    fs::{File, OpenOptions},
    io::{self, Read, Write},
    net::IpAddr,
    path::{Path, PathBuf},
};

const MAX_JOURNAL_BYTES: u64 = 1024 * 1024;
const MAX_CHANGES: usize = 32;

#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InterfaceIdentity {
    pub index: u32,
    /// Canonical, lower-case GUID; an interface index alone can be recycled.
    pub guid: String,
}

impl InterfaceIdentity {
    pub fn new(index: u32, guid: u128) -> Self {
        Self {
            index,
            guid: format!(
                "{:08x}-{:04x}-{:04x}-{:04x}-{:012x}",
                guid >> 96,
                (guid >> 80) & 0xffff,
                (guid >> 64) & 0xffff,
                (guid >> 48) & 0xffff,
                guid & 0xffff_ffff_ffff
            ),
        }
    }

    pub fn validate(&self) -> io::Result<()> {
        let guid = self.guid.as_bytes();
        if self.index == 0
            || guid.len() != 36
            || !guid.iter().enumerate().all(|(i, b)| {
                if [8, 13, 18, 23].contains(&i) {
                    *b == b'-'
                } else {
                    b.is_ascii_digit() || (b'a'..=b'f').contains(b)
                }
            })
        {
            return Err(invalid("invalid interface identity"));
        }
        Ok(())
    }
}

/// Resource keys never refer to physical interfaces: their identity is carried
/// once in the journal and independently checked by the Windows backend.
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Resource {
    Mtu {
        ipv6: bool,
    },
    Address {
        address: IpAddr,
    },
    Route {
        destination: IpNet,
        next_hop: IpAddr,
    },
    Dns,
    DnsGuard {
        name: String,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DnsProtocol {
    Tcp,
    Udp,
}

impl DnsProtocol {
    pub fn suffix(self) -> &'static str {
        match self {
            Self::Tcp => "tcp",
            Self::Udp => "udp",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Value {
    Mtu {
        mtu: u32,
    },
    Address {
        prefix_len: u8,
        skip_as_source: bool,
    },
    Route {
        metric: u32,
    },
    /// Both address families are one resource because the Windows cmdlet sets
    /// the complete server list. Order is significant (preferred resolver).
    Dns {
        servers: Vec<IpAddr>,
    },
    DnsGuard {
        protocol: DnsProtocol,
        interfaces: Vec<String>,
        owner: String,
    },
}

pub(crate) fn validate_value(resource: &Resource, value: &Option<Value>) -> io::Result<()> {
    match (resource, value) {
        (_, None) => Ok(()),
        (Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu }))
            if (if *ipv6 { 1280 } else { 576 }..=65535).contains(mtu) =>
        {
            Ok(())
        }
        (Resource::Address { address }, Some(Value::Address { prefix_len, .. }))
            if *prefix_len <= if address.is_ipv4() { 32 } else { 128 } =>
        {
            Ok(())
        }
        (
            Resource::Route {
                destination,
                next_hop,
            },
            Some(Value::Route { metric }),
        ) if destination.addr().is_ipv4() == next_hop.is_ipv4() && *metric <= 9999 => Ok(()),
        (Resource::Dns, Some(Value::Dns { servers })) if servers.len() <= 8 => Ok(()),
        (
            Resource::DnsGuard { name },
            Some(Value::DnsGuard {
                interfaces, owner, ..
            }),
        ) if name.len() <= 160
            && owner.len() == 32
            && owner.bytes().all(|c| c.is_ascii_hexdigit())
            && !interfaces.is_empty()
            && interfaces.len() <= 128
            && interfaces.iter().all(|alias| {
                !alias.is_empty()
                    && alias.encode_utf16().count() <= 256
                    && !alias.contains(['\0', '*', '?', '[', ']'])
            }) =>
        {
            Ok(())
        }
        _ => Err(invalid("resource and value mismatch")),
    }
}

pub trait NetworkBackend {
    fn read(
        &mut self,
        interface: &InterfaceIdentity,
        resource: &Resource,
    ) -> io::Result<Option<Value>>;

    /// Compare immediately before writing, then read back. Never accept only
    /// the command's exit status as proof that the desired state was installed.
    fn compare_exchange(
        &mut self,
        interface: &InterfaceIdentity,
        resource: &Resource,
        expected: &Option<Value>,
        desired: &Option<Value>,
    ) -> io::Result<()>;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChangeState {
    Pending,
    Applying,
    Applied,
    Restored,
    Conflict,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Change {
    pub resource: Resource,
    pub before: Option<Value>,
    pub after: Option<Value>,
    pub state: ChangeState,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Journal {
    pub version: u32,
    pub owner: String,
    pub interface: InterfaceIdentity,
    pub changes: Vec<Change>,
}

impl Journal {
    pub fn validate(&self) -> io::Result<()> {
        self.interface.validate()?;
        if self.version != 1
            || self.owner.len() != 32
            || !self.owner.bytes().all(|c| c.is_ascii_hexdigit())
            || self.changes.is_empty()
            || self.changes.len() > MAX_CHANGES
        {
            return Err(invalid("invalid network journal"));
        }
        let mut keys = HashSet::new();
        for change in &self.changes {
            if !keys.insert(&change.resource) {
                return Err(invalid("duplicate network journal resource"));
            }
            validate_value(&change.resource, &change.before)?;
            validate_value(&change.resource, &change.after)?;
            if let Resource::DnsGuard { name } = &change.resource {
                let Some(Value::DnsGuard {
                    protocol, owner, ..
                }) = change.after.as_ref().or(change.before.as_ref())
                else {
                    return Err(invalid("DNS guard journal has no ownership value"));
                };
                if owner != &self.owner
                    || name != &dns_guard_name(&self.interface, owner, *protocol)
                {
                    return Err(invalid("DNS guard does not belong to journal owner"));
                }
            }
        }
        Ok(())
    }

    /// Snapshot all resources before creating a durable write-ahead record.
    /// Addresses and routes must be absent: this TUN session never takes over
    /// a preexisting resource. DNS belongs to the newly created TUN interface.
    pub fn prepare(
        backend: &mut impl NetworkBackend,
        interface: InterfaceIdentity,
        owner: String,
        desired: Vec<(Resource, Option<Value>)>,
    ) -> io::Result<Self> {
        interface.validate()?;
        let mut changes = Vec::with_capacity(desired.len());
        for (resource, after) in desired {
            validate_value(&resource, &after)?;
            let before = backend.read(&interface, &resource)?;
            if before.is_some() && !matches!(resource, Resource::Dns | Resource::Mtu { .. }) {
                return Err(io::Error::new(
                    io::ErrorKind::AlreadyExists,
                    "TUN address, route or firewall rule already exists; refusing ownership takeover",
                ));
            }
            changes.push(Change {
                resource,
                before,
                after,
                state: ChangeState::Pending,
            });
        }
        let journal = Self {
            version: 1,
            owner,
            interface,
            changes,
        };
        journal.validate()?;
        Ok(journal)
    }

    pub fn is_restored(&self) -> bool {
        self.changes
            .iter()
            .all(|c| c.state == ChangeState::Restored)
    }
}

pub trait JournalStore {
    /// Must finish durable persistence before returning. A failed save must
    /// prevent the corresponding network mutation.
    fn save(&mut self, journal: &Journal) -> io::Result<()>;
}

/// A journal locked for this helper's lifetime. Another helper cannot replace
/// it while an apply/recovery is in progress. The directory must be protected by
/// the helper installation's ACL; this class does not establish that ACL.
pub struct FileJournalStore {
    path: PathBuf,
    _lock: File,
}

impl FileJournalStore {
    /// `create_new` is required for a new session. A stale journal must be
    /// recovered explicitly; it is never overwritten as part of a new start.
    pub fn create_new(path: &Path) -> io::Result<Self> {
        let store = Self::lock(path)?;
        // Do not publish an empty journal: process death between this
        // constructor and the first save would leave an unreadable recovery
        // record even though no network mutation was possible. The lock
        // reserves the name for cooperating helpers, and the first save
        // publishes a complete, synced document by atomic rename.
        match std::fs::symlink_metadata(path) {
            Ok(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::AlreadyExists,
                    "network journal already exists; recover it first",
                ));
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
        Ok(store)
    }

    pub fn open_existing(path: &Path) -> io::Result<(Self, Journal)> {
        let store = Self::lock(path)?;
        let file = File::open(path)?;
        if file.metadata()?.len() > MAX_JOURNAL_BYTES {
            return Err(invalid("network journal too large"));
        }
        let mut bytes = Vec::new();
        file.take(MAX_JOURNAL_BYTES + 1).read_to_end(&mut bytes)?;
        if bytes.len() as u64 > MAX_JOURNAL_BYTES {
            return Err(invalid("network journal too large"));
        }
        let journal: Journal = serde_json::from_slice(&bytes).map_err(invalid)?;
        journal.validate()?;
        Ok((store, journal))
    }

    fn lock(path: &Path) -> io::Result<Self> {
        if !path.is_absolute() || path.file_name().is_none() {
            return Err(invalid("journal path must be an absolute file path"));
        }
        let lock_path = path.with_extension("lock");
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(&lock_path)?;
        // OS advisory/exclusive locks are released on process death; a lockfile
        // created with create_new alone would permanently block crash recovery.
        lock.try_lock()
            .map_err(|error| io::Error::new(io::ErrorKind::WouldBlock, error))?;
        Ok(Self {
            path: path.into(),
            _lock: lock,
        })
    }
}

impl JournalStore for FileJournalStore {
    fn save(&mut self, journal: &Journal) -> io::Result<()> {
        journal.validate()?;
        let bytes = serde_json::to_vec_pretty(journal).map_err(invalid)?;
        if bytes.len() as u64 > MAX_JOURNAL_BYTES {
            return Err(invalid("network journal too large"));
        }
        let pending = self.path.with_extension("pending");
        let mut file = OpenOptions::new()
            .create(true)
            .truncate(true)
            .write(true)
            .open(&pending)?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        drop(file);
        std::fs::rename(pending, &self.path)?;
        #[cfg(unix)]
        File::open(
            self.path
                .parent()
                .ok_or_else(|| invalid("journal has no parent"))?,
        )?
        .sync_all()?;
        Ok(())
    }
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct RecoveryReport {
    pub restored: usize,
    pub already_restored: usize,
    pub conflicts: Vec<usize>,
}

#[derive(Debug)]
pub struct ApplyError {
    pub cause: io::Error,
    pub recovery: io::Result<RecoveryReport>,
}

impl std::fmt::Display for ApplyError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "network apply failed: {}; recovery: {:?}",
            self.cause, self.recovery
        )
    }
}
impl std::error::Error for ApplyError {}

/// Apply only after all snapshots have been persisted. Recovery also handles a
/// crash after an OS write but before its `Applied` marker reaches the journal.
pub fn apply(
    backend: &mut impl NetworkBackend,
    store: &mut impl JournalStore,
    journal: &mut Journal,
) -> Result<(), ApplyError> {
    let mut durable = false;
    let result = (|| -> io::Result<()> {
        journal.validate()?;
        if journal
            .changes
            .iter()
            .any(|c| c.state != ChangeState::Pending)
        {
            return Err(invalid(
                "only a fresh plan can be applied; recover existing sessions first",
            ));
        }
        store.save(journal)?;
        durable = true;
        for index in 0..journal.changes.len() {
            journal.changes[index].state = ChangeState::Applying;
            if let Err(error) = store.save(journal) {
                // This OS write was never attempted. Even if a different actor
                // installed an identical value, rollback must not adopt it.
                journal.changes[index].state = ChangeState::Pending;
                return Err(error);
            }
            let change = &journal.changes[index];
            backend.compare_exchange(
                &journal.interface,
                &change.resource,
                &change.before,
                &change.after,
            )?;
            if backend.read(&journal.interface, &change.resource)? != change.after {
                return Err(io::Error::other(
                    "network readback differs from requested state",
                ));
            }
            journal.changes[index].state = ChangeState::Applied;
            store.save(journal)?;
        }
        Ok(())
    })();
    result.map_err(|cause| ApplyError {
        cause,
        recovery: if durable {
            recover(backend, store, journal)
        } else {
            Ok(RecoveryReport::default())
        },
    })
}

pub fn recover(
    backend: &mut impl NetworkBackend,
    store: &mut impl JournalStore,
    journal: &mut Journal,
) -> io::Result<RecoveryReport> {
    journal.validate()?;
    let mut report = RecoveryReport::default();
    let mut persistence_error = None;
    // Routes were installed last. Remove captures before addresses/DNS.
    for index in (0..journal.changes.len()).rev() {
        let change = &journal.changes[index];
        if matches!(change.resource, Resource::DnsGuard { .. })
            && matches!(
                change.state,
                ChangeState::Applying | ChangeState::Applied | ChangeState::Conflict
            )
            && !report.conflicts.is_empty()
        {
            // Do not reopen a physical DNS escape path while capture recovery
            // is unresolved. Report the retained guard for explicit recovery.
            journal.changes[index].state = ChangeState::Conflict;
            report.conflicts.push(index);
            if let Err(error) = store.save(journal) {
                persistence_error.get_or_insert(error);
            }
            continue;
        }
        if matches!(change.state, ChangeState::Pending | ChangeState::Restored) {
            // Pending was durably recorded before any write was attempted.
            // Restored has relinquished ownership; never reclaim later values.
            report.already_restored += 1;
            journal.changes[index].state = ChangeState::Restored;
        } else {
            let outcome = (|| -> io::Result<bool> {
                let current = backend.read(&journal.interface, &change.resource)?;
                if current == change.before
                    || (current.is_none()
                        && matches!(change.resource, Resource::Dns | Resource::Mtu { .. }))
                {
                    return Ok(false);
                }
                if current != change.after {
                    return Err(io::Error::other("resource no longer owned"));
                }
                backend.compare_exchange(
                    &journal.interface,
                    &change.resource,
                    &current,
                    &change.before,
                )?;
                if backend.read(&journal.interface, &change.resource)? != change.before {
                    return Err(io::Error::other("restore readback mismatch"));
                }
                Ok(true)
            })();
            match outcome {
                Ok(restored) => {
                    if restored {
                        report.restored += 1;
                    } else {
                        report.already_restored += 1;
                    }
                    journal.changes[index].state = ChangeState::Restored;
                }
                Err(_) => {
                    journal.changes[index].state = ChangeState::Conflict;
                    report.conflicts.push(index);
                }
            }
        }
        // A disk failure must not prevent attempts to restore independent
        // routes. A later recovery can infer completion from OS readback.
        if let Err(error) = store.save(journal) {
            persistence_error.get_or_insert(error);
        }
    }
    match persistence_error {
        Some(error) => Err(error),
        None => Ok(report),
    }
}

/// A split default route retains the physical default routes. Core sockets must
/// already be bound to physical interfaces before applying this plan. DNS leak
/// protection against LAN routes/multi-homed DNS needs a separate WFP policy;
/// creating these routes alone does not establish that protection.
pub fn capture_resources(
    addresses: &[IpNet],
    dns_servers: &[IpAddr],
    metric: u32,
) -> io::Result<Vec<(Resource, Option<Value>)>> {
    if addresses.is_empty()
        || addresses.len() > 2
        || dns_servers.is_empty()
        || dns_servers.len() > 8
        || metric > 9999
    {
        return Err(invalid("invalid TUN capture configuration"));
    }
    let ipv4 = addresses.iter().any(|a| a.addr().is_ipv4());
    let ipv6 = addresses.iter().any(|a| a.addr().is_ipv6());
    if addresses.len() > usize::from(ipv4) + usize::from(ipv6)
        || dns_servers
            .iter()
            .any(|dns| (dns.is_ipv4() && !ipv4) || (dns.is_ipv6() && !ipv6))
    {
        return Err(invalid("each DNS/address family requires one TUN address"));
    }
    let mut resources = addresses
        .iter()
        .map(|net| {
            (
                Resource::Address {
                    address: net.addr(),
                },
                Some(Value::Address {
                    prefix_len: net.prefix_len(),
                    skip_as_source: false,
                }),
            )
        })
        .collect::<Vec<_>>();
    let mut servers = dns_servers.to_vec();
    // Windows stores per-family arrays. Keep priority within each family while
    // normalizing the cross-family order used by readback and recovery.
    servers.sort_by_key(|address| address.is_ipv6());
    resources.push((Resource::Dns, Some(Value::Dns { servers })));
    for (enabled, prefixes, gateway) in [
        (ipv4, ["0.0.0.0/1", "128.0.0.0/1"], "0.0.0.0"),
        (ipv6, ["::/1", "8000::/1"], "::"),
    ] {
        if enabled {
            for prefix in prefixes {
                resources.push((
                    Resource::Route {
                        destination: prefix.parse().map_err(invalid)?,
                        next_hop: gateway.parse().map_err(invalid)?,
                    },
                    Some(Value::Route { metric }),
                ));
            }
        }
    }
    Ok(resources)
}

fn invalid(error: impl Into<Box<dyn std::error::Error + Send + Sync>>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, error)
}

pub(crate) fn dns_guard_name(
    interface: &InterfaceIdentity,
    owner: &str,
    protocol: DnsProtocol,
) -> String {
    format!(
        "Swirl.NativeTun.DNS.{}.{}.{}",
        interface.guid,
        owner,
        protocol.suffix()
    )
}

/// Block both plaintext DNS transports on every known physical adapter,
/// including disconnected Wi-Fi/Ethernet. Place these changes before capture
/// routes so recovery removes the firewall rules last. New adapters require
/// a new guarded session; the caller must monitor adapter changes.
pub fn dns_guard_resources(
    interface: &InterfaceIdentity,
    owner: &str,
    interface_aliases: &[String],
) -> io::Result<Vec<(Resource, Option<Value>)>> {
    interface.validate()?;
    let mut interfaces = interface_aliases.to_vec();
    interfaces.sort();
    interfaces.dedup();
    [DnsProtocol::Tcp, DnsProtocol::Udp]
        .into_iter()
        .map(|protocol| {
            let key = Resource::DnsGuard {
                name: dns_guard_name(interface, owner, protocol),
            };
            let value = Some(Value::DnsGuard {
                protocol,
                interfaces: interfaces.clone(),
                owner: owner.into(),
            });
            validate_value(&key, &value)?;
            Ok((key, value))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[derive(Default)]
    struct MockNetwork {
        values: HashMap<Resource, Value>,
        writes: usize,
        fail_write: Option<usize>,
    }
    impl NetworkBackend for MockNetwork {
        fn read(&mut self, _: &InterfaceIdentity, key: &Resource) -> io::Result<Option<Value>> {
            Ok(self.values.get(key).cloned())
        }
        fn compare_exchange(
            &mut self,
            _: &InterfaceIdentity,
            key: &Resource,
            expected: &Option<Value>,
            desired: &Option<Value>,
        ) -> io::Result<()> {
            self.writes += 1;
            if self.fail_write == Some(self.writes) {
                return Err(io::Error::other("injected OS failure"));
            }
            if self.values.get(key) != expected.as_ref() {
                return Err(io::Error::other("concurrent external change"));
            }
            match desired {
                Some(value) => {
                    self.values.insert(key.clone(), value.clone());
                }
                None => {
                    self.values.remove(key);
                }
            }
            Ok(())
        }
    }
    #[derive(Default)]
    struct MemoryJournal {
        saved: Vec<Journal>,
        fail_save: Option<usize>,
    }
    impl JournalStore for MemoryJournal {
        fn save(&mut self, journal: &Journal) -> io::Result<()> {
            if self.fail_save == Some(self.saved.len() + 1) {
                return Err(io::Error::other("disk full"));
            }
            self.saved.push(journal.clone());
            Ok(())
        }
    }
    fn plan(backend: &mut MockNetwork) -> Journal {
        Journal::prepare(
            backend,
            InterfaceIdentity::new(71, 0x123456789abcdef00123456789abcdef),
            "a".repeat(32),
            capture_resources(
                &[
                    "198.18.0.1/30".parse().unwrap(),
                    "fd00:5357::1/126".parse().unwrap(),
                ],
                &[
                    "198.18.0.2".parse().unwrap(),
                    "fd00:5357::2".parse().unwrap(),
                ],
                1,
            )
            .unwrap(),
        )
        .unwrap()
    }

    #[test]
    fn dual_stack_apply_and_restore_retains_external_routes() {
        let mut backend = MockNetwork::default();
        let external = Resource::Route {
            destination: "10.0.0.0/8".parse().unwrap(),
            next_hop: "192.168.1.1".parse().unwrap(),
        };
        backend
            .values
            .insert(external.clone(), Value::Route { metric: 42 });
        let mut journal = plan(&mut backend);
        let mut store = MemoryJournal::default();
        apply(&mut backend, &mut store, &mut journal).unwrap();
        assert_eq!(backend.values.len(), 8);
        assert_eq!(store.saved[0].changes[0].state, ChangeState::Pending);
        let report = recover(&mut backend, &mut store, &mut journal).unwrap();
        assert_eq!(report.restored, 7);
        assert!(journal.is_restored());
        assert_eq!(
            backend.values,
            HashMap::from([(external, Value::Route { metric: 42 })])
        );
        assert_eq!(
            recover(&mut backend, &mut store, &mut journal)
                .unwrap()
                .restored,
            0
        );
    }

    #[test]
    fn partial_os_failure_rolls_back_only_applied_resources() {
        let mut backend = MockNetwork {
            fail_write: Some(5),
            ..Default::default()
        };
        let mut journal = plan(&mut backend);
        let error = apply(&mut backend, &mut MemoryJournal::default(), &mut journal).unwrap_err();
        assert!(error.recovery.unwrap().conflicts.is_empty());
        assert!(backend.values.is_empty());
    }

    #[test]
    fn recovery_handles_crash_between_os_write_and_journal_marker() {
        let mut backend = MockNetwork::default();
        let mut journal = plan(&mut backend);
        journal.changes[0].state = ChangeState::Applying;
        let change = journal.changes.first().unwrap();
        backend
            .values
            .insert(change.resource.clone(), change.after.clone().unwrap());
        // Durable record says Applying, as after a crash before the marker.
        let report = recover(&mut backend, &mut MemoryJournal::default(), &mut journal).unwrap();
        assert_eq!(report.restored, 1);
        assert!(backend.values.is_empty());
    }

    #[test]
    fn recovery_preserves_later_vpn_dns_changes_and_reports_conflict() {
        let mut backend = MockNetwork::default();
        let mut journal = plan(&mut backend);
        let mut store = MemoryJournal::default();
        apply(&mut backend, &mut store, &mut journal).unwrap();
        let dns = Value::Dns {
            servers: vec!["9.9.9.9".parse().unwrap()],
        };
        backend.values.insert(Resource::Dns, dns.clone());
        let report = recover(&mut backend, &mut store, &mut journal).unwrap();
        assert_eq!(report.conflicts, vec![2]);
        assert!(!journal.is_restored());
        assert_eq!(backend.values, HashMap::from([(Resource::Dns, dns)]));
    }

    #[test]
    fn no_network_write_without_a_durable_first_journal() {
        let mut backend = MockNetwork::default();
        let mut journal = plan(&mut backend);
        let mut store = MemoryJournal {
            fail_save: Some(1),
            ..Default::default()
        };
        assert!(apply(&mut backend, &mut store, &mut journal).is_err());
        assert_eq!(backend.writes, 0);
    }

    #[test]
    fn disk_failure_during_apply_does_not_block_network_rollback() {
        let mut backend = MockNetwork::default();
        let mut journal = plan(&mut backend);
        // Initial record + Applying + Applied succeed, then all saves fail.
        let mut store = MemoryJournal {
            fail_save: Some(4),
            ..Default::default()
        };
        let error = apply(&mut backend, &mut store, &mut journal).unwrap_err();
        assert!(error.recovery.is_err());
        assert!(
            backend.values.is_empty(),
            "disk-full recovery must still remove installed routes/addresses"
        );
    }

    #[test]
    fn dns_guards_and_both_mtu_values_are_owned_and_restored() {
        let mut backend = MockNetwork::default();
        let interface = InterfaceIdentity::new(7, 1);
        let owner = "b".repeat(32);
        let aliases = vec!["Wi-Fi".into(), "Ethernet".into()];
        let mut desired = dns_guard_resources(&interface, &owner, &aliases).unwrap();
        for ipv6 in [false, true] {
            backend
                .values
                .insert(Resource::Mtu { ipv6 }, Value::Mtu { mtu: 65535 });
            desired.push((Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu: 1500 })));
        }
        desired.extend(
            capture_resources(
                &["198.18.0.1/30".parse().unwrap()],
                &["198.18.0.2".parse().unwrap()],
                1,
            )
            .unwrap(),
        );
        let mut journal = Journal::prepare(&mut backend, interface, owner, desired).unwrap();
        let mut store = MemoryJournal::default();
        apply(&mut backend, &mut store, &mut journal).unwrap();
        assert_eq!(
            backend.values.get(&Resource::Mtu { ipv6: true }),
            Some(&Value::Mtu { mtu: 1500 })
        );
        assert_eq!(
            backend
                .values
                .keys()
                .filter(|key| matches!(key, Resource::DnsGuard { .. }))
                .count(),
            2
        );
        recover(&mut backend, &mut store, &mut journal).unwrap();
        assert_eq!(backend.values.len(), 2);
        assert_eq!(
            backend.values.get(&Resource::Mtu { ipv6: true }),
            Some(&Value::Mtu { mtu: 65535 })
        );
    }

    #[test]
    fn dns_guard_is_retained_when_capture_recovery_conflicts() {
        let mut backend = MockNetwork::default();
        let interface = InterfaceIdentity::new(7, 1);
        let owner = "b".repeat(32);
        let mut desired = dns_guard_resources(&interface, &owner, &["Wi-Fi".into()]).unwrap();
        desired.extend(
            capture_resources(
                &["198.18.0.1/30".parse().unwrap()],
                &["198.18.0.2".parse().unwrap()],
                1,
            )
            .unwrap(),
        );
        let mut journal = Journal::prepare(&mut backend, interface, owner, desired).unwrap();
        let mut store = MemoryJournal::default();
        apply(&mut backend, &mut store, &mut journal).unwrap();
        let route = journal.changes.last().unwrap().resource.clone();
        backend.values.insert(route, Value::Route { metric: 23 });
        let report = recover(&mut backend, &mut store, &mut journal).unwrap();
        assert_eq!(report.conflicts, vec![5, 1, 0]);
        assert_eq!(
            backend
                .values
                .keys()
                .filter(|key| matches!(key, Resource::DnsGuard { .. }))
                .count(),
            2
        );
    }

    #[test]
    fn pending_or_restored_changes_never_adopt_identical_external_values() {
        let mut backend = MockNetwork::default();
        let mut journal = plan(&mut backend);
        let key = journal.changes[0].resource.clone();
        let value = journal.changes[0].after.clone().unwrap();
        backend.values.insert(key.clone(), value.clone());
        recover(&mut backend, &mut MemoryJournal::default(), &mut journal).unwrap();
        assert_eq!(backend.values.get(&key), Some(&value));
        assert_eq!(backend.writes, 0);
        recover(&mut backend, &mut MemoryJournal::default(), &mut journal).unwrap();
        assert_eq!(backend.values.get(&key), Some(&value));
        assert_eq!(backend.writes, 0);
    }

    #[test]
    fn refuses_to_adopt_existing_route() {
        let mut backend = MockNetwork::default();
        let desired = capture_resources(
            &["198.18.0.1/30".parse().unwrap()],
            &["198.18.0.2".parse().unwrap()],
            1,
        )
        .unwrap();
        let (key, value) = desired.last().unwrap();
        backend.values.insert(key.clone(), value.clone().unwrap());
        let result = Journal::prepare(
            &mut backend,
            InterfaceIdentity::new(9, 1),
            "a".repeat(32),
            desired,
        );
        assert_eq!(result.unwrap_err().kind(), io::ErrorKind::AlreadyExists);
        assert_eq!(backend.writes, 0);
    }

    #[test]
    fn journal_roundtrip_rejects_unknown_fields_duplicate_keys_and_bad_identity() {
        let mut journal = plan(&mut MockNetwork::default());
        let bytes = serde_json::to_vec(&journal).unwrap();
        assert_eq!(serde_json::from_slice::<Journal>(&bytes).unwrap(), journal);
        let mut value = serde_json::to_value(&journal).unwrap();
        value
            .as_object_mut()
            .unwrap()
            .insert("arbitrary_command".into(), "bad".into());
        assert!(serde_json::from_value::<Journal>(value).is_err());
        journal.changes.push(journal.changes[0].clone());
        assert!(journal.validate().is_err());
        assert!(
            InterfaceIdentity {
                index: 7,
                guid: "$(evil)".into()
            }
            .validate()
            .is_err()
        );
    }

    #[test]
    fn journal_lock_survives_reopen_and_prevents_parallel_owner() {
        let directory = std::env::temp_dir().join(format!(
            "swirl-network-journal-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir(&directory).unwrap();
        let path = directory.join("session.json");
        let journal = plan(&mut MockNetwork::default());
        {
            let store = FileJournalStore::create_new(&path).unwrap();
            assert!(
                !path.exists(),
                "construction must not publish an empty journal"
            );
            assert!(FileJournalStore::create_new(&path).is_err());
            // Simulate termination before the first durable save. The lock
            // file remains, but starting again must not require recovery of
            // a journal that never contained any planned network operation.
            drop(store);
        }
        {
            let mut store = FileJournalStore::create_new(&path).unwrap();
            store.save(&journal).unwrap();
            assert!(FileJournalStore::open_existing(&path).is_err());
        }
        let (store, loaded) = FileJournalStore::open_existing(&path).unwrap();
        assert_eq!(loaded, journal);
        drop(store);
        assert!(FileJournalStore::create_new(&path).is_err());
        std::fs::remove_dir_all(directory).unwrap();
    }
}
