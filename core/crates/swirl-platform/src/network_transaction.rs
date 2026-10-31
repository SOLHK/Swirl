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

/// The identity is carried once in the journal and independently checked by
/// its backend. The TUN backend still refuses physical interfaces; the gateway
/// backend permits only dedicated-LAN forwarding and its owned isolation guard.
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Resource {
    Forwarding {
        ipv6: bool,
    },
    GatewayIsolation {
        name: String,
    },
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
    Forwarding {
        enabled: bool,
    },
    GatewayIsolation {
        policy: crate::gateway_policy::GatewayIsolationPolicy,
    },
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

/// Validate an OS state, including a snapshot that must be restored exactly.
/// Windows NlMtuBytes has a u32 range; the adapter's existing value is not a
/// request to send a packet of that size. Keep the smaller installation limit
/// separate so journal recovery never clamps or rejects a legal prior state.
/// See Microsoft Set-NetIPInterface, -NlMtuBytes.
pub(crate) fn validate_value(resource: &Resource, value: &Option<Value>) -> io::Result<()> {
    match (resource, value) {
        (_, None) => Ok(()),
        (Resource::Forwarding { .. }, Some(Value::Forwarding { .. })) => Ok(()),
        (Resource::GatewayIsolation { name }, Some(Value::GatewayIsolation { policy })) => {
            policy.validate()?;
            if name != &policy.name() {
                return Err(invalid("gateway isolation ownership name mismatch"));
            }
            Ok(())
        }
        (Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu })) => {
            let minimum = if *ipv6 { 1280 } else { 576 };
            if *mtu < minimum {
                return Err(invalid(format!(
                    "invalid IPv{} OS MTU {mtu}; resource={resource:?}, value={value:?}, field=mtu; expected {minimum}..={}",
                    if *ipv6 { 6 } else { 4 },
                    u32::MAX
                )));
            }
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
        _ => Err(invalid(format!(
            "resource and value mismatch: resource={resource:?}, value={value:?}"
        ))),
    }
}

/// Values Swirl installs retain the packet-size limit, independently of the
/// full Windows state range needed for exact restoration of `before` values.
fn validate_install_value(resource: &Resource, value: &Option<Value>) -> io::Result<()> {
    validate_value(resource, value)?;
    if let (Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu })) = (resource, value)
        && *mtu > 65535
    {
        let minimum = if *ipv6 { 1280 } else { 576 };
        return Err(invalid(format!(
            "invalid IPv{} installed MTU {mtu}; resource={resource:?}, value={value:?}, field=mtu; expected {minimum}..=65535",
            if *ipv6 { 6 } else { 4 }
        )));
    }
    Ok(())
}

pub trait NetworkBackend {
    fn read(
        &mut self,
        interface: &InterfaceIdentity,
        resource: &Resource,
    ) -> io::Result<Option<Value>>;

    /// Compare immediately before writing, then read back. Never accept only
    /// the command's exit status as proof that the desired state was installed.
    /// Return AlreadyExists only for an ownership/CAS conflict proven to occur
    /// before any write. The journal must never adopt that actor's state.
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
    /// A compare rejected a foreign value before writing, or recovery observed
    /// ownership loss. Even a later value equal to `after` is not ours to undo.
    NotOwned,
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
            validate_value(&change.resource, &change.before).map_err(|error| {
                io::Error::new(error.kind(), format!("journal before validation: {error}"))
            })?;
            validate_install_value(&change.resource, &change.after).map_err(|error| {
                io::Error::new(error.kind(), format!("journal after validation: {error}"))
            })?;
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
            if let Resource::GatewayIsolation { .. } = &change.resource {
                let Some(Value::GatewayIsolation { policy }) = change.after.as_ref().or(change.before.as_ref()) else {
                    return Err(invalid("gateway guard has no ownership value"));
                };
                if policy.owner != self.owner || policy.lan != self.interface || change.before.is_some() {
                    return Err(invalid("gateway guard does not belong to journal owner"));
                }
            }
        }
        if self.changes.iter().any(|change| matches!(change.resource, Resource::GatewayIsolation { .. }))
            && (self.changes.len() != 2
                || !matches!(self.changes[0].resource, Resource::GatewayIsolation { .. })
                || !matches!(self.changes[1].resource, Resource::Forwarding { ipv6: false })
                || self.changes[1].after != Some(Value::Forwarding { enabled: true })
                || self.changes[1].before != Some(Value::Forwarding { enabled: false }))
        {
            return Err(invalid("gateway isolation must precede the dedicated IPv4 forwarding change"));
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
            validate_install_value(&resource, &after).map_err(|error| {
                io::Error::new(error.kind(), format!("requested state validation: {error}"))
            })?;
            let before = backend.read(&interface, &resource).map_err(|error| {
                io::Error::new(
                    error.kind(),
                    format!(
                        "snapshot read: interface={interface:?}, resource={resource:?}: {error}"
                    ),
                )
            })?;
            validate_value(&resource, &before).map_err(|error| {
                io::Error::new(error.kind(), format!("captured state validation: {error}"))
            })?;
            if before.is_some() && !matches!(resource, Resource::Dns | Resource::Mtu { .. } | Resource::Forwarding { .. }) {
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
    if journal.changes.iter().any(|change| change.state != ChangeState::Pending) {
        return Err(ApplyError {
            cause: invalid("only a fresh plan can be applied; recover existing sessions first"),
            recovery: Ok(RecoveryReport::default()),
        });
    }
    let through = journal.changes.len();
    apply_prefix(backend, store, journal, through)
}

/// Apply a contiguous, verified prefix of a durable plan. This permits the
/// gateway coordinator to install isolation, establish the TUN/DHCP data path,
/// and only then enable LAN forwarding. Resumption never adopts outside writes:
/// every already-Applied resource is read back before another write is allowed.
/// A failure rolls back only changes attempted by this stage. An earlier stage
/// stays owned until its coordinator has torn down dependent resources. This
/// keeps gateway isolation alive while TUN/DHCP activation is rolled back.
pub fn apply_prefix(
    backend: &mut impl NetworkBackend,
    store: &mut impl JournalStore,
    journal: &mut Journal,
    through: usize,
) -> Result<(), ApplyError> {
    let mut durable = false;
    let mut rollback_from = 0;
    let result = (|| -> io::Result<()> {
        journal.validate()?;
        if through == 0 || through > journal.changes.len() {
            return Err(invalid("invalid transaction prefix"));
        }
        let first_pending = journal.changes.iter()
            .position(|change| change.state != ChangeState::Applied)
            .unwrap_or(journal.changes.len());
        if first_pending > through || journal.changes[first_pending..].iter()
            .any(|change| change.state != ChangeState::Pending) {
            return Err(invalid("only an Applied prefix and Pending suffix may be resumed"));
        }
        rollback_from = first_pending;
        durable = first_pending > 0;
        store.save(journal)?;
        durable = true;
        for change in &journal.changes[..first_pending] {
            if backend.read(&journal.interface, &change.resource)? != change.after {
                return Err(io::Error::new(io::ErrorKind::AlreadyExists,
                    "applied transaction prefix changed before resumption"));
            }
        }
        for index in first_pending..through {
            journal.changes[index].state = ChangeState::Applying;
            if let Err(error) = store.save(journal) {
                // This OS write was never attempted. Even if a different actor
                // installed an identical value, rollback must not adopt it.
                journal.changes[index].state = ChangeState::Pending;
                return Err(error);
            }
            let change = &journal.changes[index];
            if let Err(error) = backend.compare_exchange(
                &journal.interface,
                &change.resource,
                &change.before,
                &change.after,
            ) {
                if error.kind() == io::ErrorKind::AlreadyExists {
                    journal.changes[index].state = ChangeState::NotOwned;
                    // Preserve the in-memory loss even if persistence fails;
                    // this recovery attempt must never perform the write.
                    store.save(journal)?;
                }
                return Err(error);
            }
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
        recovery: if durable && rollback_from < journal.changes.len() {
            recover_suffix(backend, store, journal, rollback_from)
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
    recover_suffix(backend, store, journal, 0)
}

/// Restore only a suffix, in reverse order. Gateway shutdown first restores
/// LAN forwarding (suffix 1), then tears down TUN, and finally restores suffix 0
/// to relinquish isolation. The journal remains locked throughout these steps.
pub fn recover_suffix(
    backend: &mut impl NetworkBackend,
    store: &mut impl JournalStore,
    journal: &mut Journal,
    from: usize,
) -> io::Result<RecoveryReport> {
    journal.validate()?;
    if from >= journal.changes.len() {
        return Err(invalid("invalid recovery suffix"));
    }
    let mut report = RecoveryReport::default();
    let mut persistence_error = None;
    // Routes were installed last. Remove captures before addresses/DNS.
    for index in (from..journal.changes.len()).rev() {
        let change = &journal.changes[index];
        let owns_guard = matches!(change.state,
            ChangeState::Applying | ChangeState::Applied | ChangeState::Conflict | ChangeState::NotOwned);
        let gateway_forwarding_unresolved = matches!(change.resource, Resource::GatewayIsolation { .. })
            && owns_guard
            && report.conflicts.is_empty()
            && !matches!(backend.read(&journal.interface, &Resource::Forwarding { ipv6: false }),
                Ok(None) | Ok(Some(Value::Forwarding { enabled: false })));
        if matches!(change.resource, Resource::DnsGuard { .. } | Resource::GatewayIsolation { .. })
            && owns_guard
            && (!report.conflicts.is_empty() || gateway_forwarding_unresolved)
        {
            // Do not reopen a physical DNS escape path while capture recovery
            // is unresolved. Gateway Forwarding can also change while Pending
            // or after our restore; reread it before removing our guard. Never
            // disable that external value to make cleanup appear successful.
            if change.state != ChangeState::NotOwned {
                journal.changes[index].state = ChangeState::Conflict;
            }
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
            let ownership_lost = change.state == ChangeState::NotOwned;
            let outcome = (|| -> io::Result<bool> {
                let current = backend.read(&journal.interface, &change.resource)?;
                if current == change.before
                    || (current.is_none()
                        && matches!(change.resource, Resource::Dns | Resource::Mtu { .. } | Resource::Forwarding { .. }))
                {
                    return Ok(false);
                }
                // Forwarding is a shared boolean with no OS owner token. If a
                // process dies (or loses its disk) at Applying, a successful
                // write and a rejected compare against an identical external
                // value are indistinguishable. Keep isolation and evidence;
                // never guess ownership merely because the bit is true.
                if change.state == ChangeState::NotOwned
                    || (change.state == ChangeState::Applying
                        && matches!(change.resource, Resource::Forwarding { .. }))
                    || current != change.after
                {
                    return Err(io::Error::new(io::ErrorKind::AlreadyExists, "resource no longer owned"));
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
                Err(error) => {
                    journal.changes[index].state = if ownership_lost || error.kind() == io::ErrorKind::AlreadyExists {
                        ChangeState::NotOwned
                    } else {
                        ChangeState::Conflict
                    };
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
            // Match the Windows backend's bidirectional state validation:
            // desired may be the captured OS value during journal recovery.
            validate_value(key, expected)?;
            validate_value(key, desired)?;
            self.writes += 1;
            if self.fail_write == Some(self.writes) {
                return Err(io::Error::other("injected OS failure"));
            }
            if self.values.get(key) != expected.as_ref() {
                return Err(io::Error::new(io::ErrorKind::AlreadyExists, "concurrent external change"));
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
    fn large_os_mtu_snapshots_survive_disk_reopen_and_exact_dual_stack_restore() {
        let directory = std::env::temp_dir().join(format!(
            "swirl-network-mtu-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir(&directory).unwrap();
        for original in [65536, u32::MAX] {
            let initial = HashMap::from([
                (Resource::Mtu { ipv6: false }, Value::Mtu { mtu: original }),
                (Resource::Mtu { ipv6: true }, Value::Mtu { mtu: original }),
            ]);
            let mut backend = MockNetwork {
                values: initial.clone(),
                ..Default::default()
            };
            let mut journal = Journal::prepare(
                &mut backend,
                InterfaceIdentity::new(71, 1),
                "a".repeat(32),
                [false, true]
                    .into_iter()
                    .map(|ipv6| (Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu: 1500 })))
                    .collect(),
            )
            .unwrap();
            assert!(
                journal
                    .changes
                    .iter()
                    .all(|change| change.before == Some(Value::Mtu { mtu: original }))
            );
            let path = directory.join(format!("{original}.json"));
            let mut store = FileJournalStore::create_new(&path).unwrap();
            apply(&mut backend, &mut store, &mut journal).unwrap();
            assert!(
                backend
                    .values
                    .values()
                    .all(|value| value == &Value::Mtu { mtu: 1500 })
            );
            drop(store);
            let (mut store, mut restored) = FileJournalStore::open_existing(&path).unwrap();
            assert_eq!(restored, journal);
            let report = recover(&mut backend, &mut store, &mut restored).unwrap();
            assert_eq!(report.restored, 2);
            assert!(report.conflicts.is_empty());
            assert!(restored.is_restored());
            assert_eq!(backend.values, initial);
            assert_eq!(backend.writes, 4);
            drop(store);
        }
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn oversized_installed_mtu_is_rejected_before_writes_and_in_loaded_journals() {
        for ipv6 in [false, true] {
            for mtu in [65536, u32::MAX] {
                let mut backend = MockNetwork::default();
                let desired = vec![(Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu }))];
                let error = Journal::prepare(
                    &mut backend,
                    InterfaceIdentity::new(71, 1),
                    "a".repeat(32),
                    desired,
                )
                .unwrap_err();
                assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
                assert!(error.to_string().contains(&mtu.to_string()));
                assert!(error.to_string().contains("..=65535"));
                assert_eq!(backend.writes, 0);
                let journal = Journal {
                    version: 1,
                    owner: "a".repeat(32),
                    interface: InterfaceIdentity::new(71, 1),
                    changes: vec![Change {
                        resource: Resource::Mtu { ipv6 },
                        before: Some(Value::Mtu { mtu: u32::MAX }),
                        after: Some(Value::Mtu { mtu }),
                        state: ChangeState::Applying,
                    }],
                };
                let loaded: Journal =
                    serde_json::from_slice(&serde_json::to_vec(&journal).unwrap()).unwrap();
                assert!(loaded.validate().is_err());
            }
        }
    }

    #[test]
    fn os_mtu_snapshots_below_family_minimum_remain_invalid() {
        for (ipv6, minimum) in [(false, 576), (true, 1280)] {
            for mtu in [0, minimum - 1] {
                let mut backend = MockNetwork {
                    values: HashMap::from([(Resource::Mtu { ipv6 }, Value::Mtu { mtu })]),
                    ..Default::default()
                };
                let error = Journal::prepare(
                    &mut backend,
                    InterfaceIdentity::new(71, 1),
                    "a".repeat(32),
                    vec![(Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu: 1500 }))],
                )
                .unwrap_err();
                assert!(error.to_string().contains(&mtu.to_string()));
                assert!(
                    error
                        .to_string()
                        .contains(&format!("{minimum}..={}", u32::MAX))
                );
                assert_eq!(backend.writes, 0);
            }
        }
    }

    #[test]
    fn installed_mtu_family_boundaries_apply_and_restore_exact_originals() {
        for (ipv6, minimum) in [(false, 576), (true, 1280)] {
            for mtu in [minimum, 1500, 65535] {
                let resource = Resource::Mtu { ipv6 };
                let initial = HashMap::from([(resource.clone(), Value::Mtu { mtu: u32::MAX })]);
                let mut backend = MockNetwork {
                    values: initial.clone(),
                    ..Default::default()
                };
                let mut journal = Journal::prepare(
                    &mut backend,
                    InterfaceIdentity::new(71, 1),
                    "a".repeat(32),
                    vec![(resource.clone(), Some(Value::Mtu { mtu }))],
                )
                .unwrap();
                let mut store = MemoryJournal::default();
                apply(&mut backend, &mut store, &mut journal).unwrap();
                assert_eq!(backend.values.get(&resource), Some(&Value::Mtu { mtu }));
                let report = recover(&mut backend, &mut store, &mut journal).unwrap();
                assert_eq!(report.restored, 1);
                assert!(report.conflicts.is_empty());
                assert_eq!(backend.values, initial);
                assert!(journal.is_restored());
            }
            for mtu in [0, minimum - 1] {
                let mut backend = MockNetwork::default();
                let error = Journal::prepare(
                    &mut backend,
                    InterfaceIdentity::new(71, 1),
                    "a".repeat(32),
                    vec![(Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu }))],
                )
                .unwrap_err();
                assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
                assert!(error.to_string().contains("requested state validation"));
                assert_eq!(backend.writes, 0);
            }
        }
    }

    #[test]
    fn partial_apply_failure_restores_large_mtu_without_clamping() {
        for first_ipv6 in [false, true] {
            for original in [65536, u32::MAX] {
                let initial = HashMap::from([
                    (Resource::Mtu { ipv6: false }, Value::Mtu { mtu: original }),
                    (Resource::Mtu { ipv6: true }, Value::Mtu { mtu: original }),
                ]);
                let mut backend = MockNetwork {
                    values: initial.clone(),
                    fail_write: Some(2),
                    ..Default::default()
                };
                let mut journal = Journal::prepare(
                    &mut backend,
                    InterfaceIdentity::new(71, 1),
                    "a".repeat(32),
                    [first_ipv6, !first_ipv6]
                        .into_iter()
                        .map(|ipv6| (Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu: 1500 })))
                        .collect(),
                )
                .unwrap();
                let error =
                    apply(&mut backend, &mut MemoryJournal::default(), &mut journal).unwrap_err();
                assert_eq!(error.cause.to_string(), "injected OS failure");
                let report = error.recovery.unwrap();
                assert_eq!(report.restored, 1);
                assert_eq!(report.already_restored, 1);
                assert!(report.conflicts.is_empty());
                assert_eq!(backend.values, initial);
                assert_eq!(backend.writes, 3);
                assert!(journal.is_restored());
            }
        }
    }

    #[test]
    fn large_mtu_recovery_preserves_later_external_change_and_reports_conflict() {
        for changed_ipv6 in [false, true] {
            let initial = HashMap::from([
                (Resource::Mtu { ipv6: false }, Value::Mtu { mtu: 65536 }),
                (Resource::Mtu { ipv6: true }, Value::Mtu { mtu: u32::MAX }),
            ]);
            for external_mtu in [1400, 262144] {
                let mut backend = MockNetwork {
                    values: initial.clone(),
                    ..Default::default()
                };
                let mut journal = Journal::prepare(
                    &mut backend,
                    InterfaceIdentity::new(71, 1),
                    "a".repeat(32),
                    [false, true]
                        .into_iter()
                        .map(|ipv6| (Resource::Mtu { ipv6 }, Some(Value::Mtu { mtu: 1500 })))
                        .collect(),
                )
                .unwrap();
                let mut store = MemoryJournal::default();
                apply(&mut backend, &mut store, &mut journal).unwrap();
                let changed = Resource::Mtu { ipv6: changed_ipv6 };
                backend
                    .values
                    .insert(changed.clone(), Value::Mtu { mtu: external_mtu });
                let report = recover(&mut backend, &mut store, &mut journal).unwrap();
                assert_eq!(report.restored, 1);
                assert_eq!(report.conflicts, vec![usize::from(changed_ipv6)]);
                assert!(!journal.is_restored());
                let mut expected = initial.clone();
                expected.insert(changed, Value::Mtu { mtu: external_mtu });
                assert_eq!(backend.values, expected);
                assert_eq!(backend.writes, 3);
                let again = recover(&mut backend, &mut store, &mut journal).unwrap();
                assert_eq!(again.restored, 0);
                assert_eq!(again.conflicts, report.conflicts);
                assert_eq!(backend.values, expected);
                assert_eq!(backend.writes, 3);
            }
        }
    }

    #[test]
    fn snapshot_validation_errors_identify_stage_resource_field_and_value() {
        let resource = Resource::Mtu { ipv6: true };
        let mut backend = MockNetwork {
            values: HashMap::from([(resource.clone(), Value::Mtu { mtu: 1279 })]),
            ..Default::default()
        };
        let error = Journal::prepare(
            &mut backend,
            InterfaceIdentity::new(71, 1),
            "a".repeat(32),
            vec![(resource.clone(), Some(Value::Mtu { mtu: 1500 }))],
        )
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
        let message = error.to_string();
        for expected in [
            "captured state validation",
            "resource=Mtu { ipv6: true }",
            "value=Some(Mtu { mtu: 1279 })",
            "field=mtu",
        ] {
            assert!(message.contains(expected), "{message}");
        }
        let mut journal = Journal {
            version: 1,
            owner: "a".repeat(32),
            interface: InterfaceIdentity::new(71, 1),
            changes: vec![Change {
                resource,
                before: Some(Value::Mtu { mtu: 1279 }),
                after: Some(Value::Mtu { mtu: 1500 }),
                state: ChangeState::Pending,
            }],
        };
        assert!(
            journal
                .validate()
                .unwrap_err()
                .to_string()
                .contains("journal before validation")
        );
        journal.changes[0].before = Some(Value::Mtu { mtu: u32::MAX });
        journal.changes[0].after = Some(Value::Mtu { mtu: 65536 });
        let message = journal.validate().unwrap_err().to_string();
        assert!(message.contains("journal after validation"));
        assert!(message.contains("65536"));
        assert_eq!(backend.writes, 0);
    }

    #[test]
    fn snapshot_type_mismatch_identifies_the_returned_resource_and_value() {
        let resource = Resource::Mtu { ipv6: false };
        let mut backend = MockNetwork {
            values: HashMap::from([(resource.clone(), Value::Route { metric: 5 })]),
            ..Default::default()
        };
        let error = Journal::prepare(
            &mut backend,
            InterfaceIdentity::new(71, 1),
            "a".repeat(32),
            vec![(resource, Some(Value::Mtu { mtu: 1500 }))],
        )
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
        let message = error.to_string();
        assert!(message.contains("captured state validation"));
        assert!(message.contains("resource=Mtu { ipv6: false }"));
        assert!(message.contains("value=Some(Route { metric: 5 })"));
        assert_eq!(backend.writes, 0);
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

    fn gateway_plan(backend: &mut MockNetwork) -> Journal {
        let policy = crate::gateway_policy::fixture();
        let forwarding = Resource::Forwarding { ipv6: false };
        backend.values.insert(forwarding.clone(), Value::Forwarding { enabled: false });
        Journal::prepare(backend, policy.lan.clone(), policy.owner.clone(), vec![
            (Resource::GatewayIsolation { name: policy.name() }, Some(Value::GatewayIsolation { policy })),
            (forwarding, Some(Value::Forwarding { enabled: true })),
        ]).unwrap()
    }

    #[test]
    fn gateway_recovery_retains_isolation_until_lan_forwarding_is_restored() {
        let mut backend = MockNetwork::default();
        let mut journal = gateway_plan(&mut backend);
        let mut store = MemoryJournal::default();
        apply(&mut backend, &mut store, &mut journal).unwrap();
        backend.fail_write = Some(3);
        let report = recover(&mut backend, &mut store, &mut journal).unwrap();
        assert_eq!(report.conflicts, vec![1, 0]);
        assert!(backend.values.contains_key(&journal.changes[0].resource));
        assert_eq!(backend.values[&journal.changes[1].resource], Value::Forwarding { enabled: true });
        backend.fail_write = None;
        assert!(recover(&mut backend, &mut store, &mut journal).unwrap().conflicts.is_empty());
        assert!(journal.is_restored());
        assert!(!backend.values.contains_key(&journal.changes[0].resource));
        assert_eq!(backend.values[&journal.changes[1].resource], Value::Forwarding { enabled: false });
    }

    #[test]
    fn gateway_preparation_activation_and_quiesce_hold_isolation_between_phases() {
        let mut backend = MockNetwork::default();
        let mut journal = gateway_plan(&mut backend);
        let mut store = MemoryJournal::default();
        let guard = journal.changes[0].resource.clone();
        let forwarding = journal.changes[1].resource.clone();
        apply_prefix(&mut backend, &mut store, &mut journal, 1).unwrap();
        assert!(backend.values.contains_key(&guard));
        assert_eq!(backend.values[&forwarding], Value::Forwarding { enabled: false });
        assert_eq!(journal.changes[1].state, ChangeState::Pending);
        assert_eq!(backend.writes, 1);
        apply_prefix(&mut backend, &mut store, &mut journal, 2).unwrap();
        assert_eq!(backend.values[&forwarding], Value::Forwarding { enabled: true });
        assert_eq!(backend.writes, 2);
        let report = recover_suffix(&mut backend, &mut store, &mut journal, 1).unwrap();
        assert!(report.conflicts.is_empty());
        assert_eq!(backend.values[&forwarding], Value::Forwarding { enabled: false });
        assert!(backend.values.contains_key(&guard), "TUN teardown still depends on isolation");
        assert!(!journal.is_restored());
        recover(&mut backend, &mut store, &mut journal).unwrap();
        assert!(journal.is_restored());
        assert!(!backend.values.contains_key(&guard));
    }

    #[test]
    fn failed_activation_rolls_back_only_its_stage_until_tun_teardown() {
        let mut backend = MockNetwork::default();
        let mut journal = gateway_plan(&mut backend);
        let mut store = MemoryJournal::default();
        apply_prefix(&mut backend, &mut store, &mut journal, 1).unwrap();
        backend.fail_write = Some(2);
        let failure = apply_prefix(&mut backend, &mut store, &mut journal, 2).unwrap_err();
        assert!(failure.recovery.unwrap().conflicts.is_empty());
        assert_eq!(journal.changes[0].state, ChangeState::Applied);
        assert!(backend.values.contains_key(&journal.changes[0].resource));
        assert_eq!(backend.values[&journal.changes[1].resource], Value::Forwarding { enabled: false });
        backend.fail_write = None;
        recover(&mut backend, &mut store, &mut journal).unwrap();
        assert!(journal.is_restored());
    }

    #[test]
    fn staged_resume_rechecks_isolation_and_cannot_enable_forwarding_after_removal() {
        let mut backend = MockNetwork::default();
        let mut journal = gateway_plan(&mut backend);
        let mut store = MemoryJournal::default();
        apply_prefix(&mut backend, &mut store, &mut journal, 1).unwrap();
        backend.values.remove(&journal.changes[0].resource);
        let writes = backend.writes;
        assert!(apply_prefix(&mut backend, &mut store, &mut journal, 2).is_err());
        assert_eq!(backend.writes, writes);
        assert_eq!(backend.values[&journal.changes[1].resource], Value::Forwarding { enabled: false });
        assert!(!journal.is_restored(), "caller still owns preparation teardown");
    }

    #[test]
    fn quiesce_does_not_adopt_external_forwarding_from_a_prepared_session() {
        let mut backend = MockNetwork::default();
        let mut journal = gateway_plan(&mut backend);
        let mut store = MemoryJournal::default();
        apply_prefix(&mut backend, &mut store, &mut journal, 1).unwrap();
        let forwarding = journal.changes[1].resource.clone();
        backend.values.insert(forwarding.clone(), Value::Forwarding { enabled: true });
        let writes = backend.writes;
        // Pending is not ownership. The coordinator's explicit forwarding
        // readback rejects this state; whole-plan recovery retains the guard.
        recover_suffix(&mut backend, &mut store, &mut journal, 1).unwrap();
        let report = recover(&mut backend, &mut store, &mut journal).unwrap();
        assert_eq!(report.conflicts, vec![0]);
        assert_eq!(backend.writes, writes);
        assert_eq!(backend.values[&forwarding], Value::Forwarding { enabled: true });
        assert!(backend.values.contains_key(&journal.changes[0].resource));
    }

    #[test]
    fn gateway_plan_rejects_unsafe_recovery_order_and_wrong_owner() {
        let mut journal = gateway_plan(&mut MockNetwork::default());
        journal.changes.swap(0, 1);
        assert!(journal.validate().is_err());
        journal.changes.swap(0, 1);
        journal.owner = "b".repeat(32);
        assert!(journal.validate().is_err());
    }

    #[test]
    fn rejected_gateway_cas_never_adopts_an_identical_external_forwarding_value() {
        let mut backend = MockNetwork::default();
        let mut journal = gateway_plan(&mut backend);
        let forwarding = journal.changes[1].resource.clone();
        // Another actor enables Forwarding after our snapshot. It happens to
        // match the desired value, but our compare must reject without writing.
        backend.values.insert(forwarding.clone(), Value::Forwarding { enabled: true });
        let mut store = MemoryJournal::default();
        let failure = apply(&mut backend, &mut store, &mut journal).unwrap_err();
        assert_eq!(failure.cause.kind(), io::ErrorKind::AlreadyExists);
        assert_eq!(failure.recovery.unwrap().conflicts, vec![1, 0]);
        assert_eq!(journal.changes[1].state, ChangeState::NotOwned);
        let writes = backend.writes;
        let report = recover(&mut backend, &mut store, &mut journal).unwrap();
        assert_eq!(report.conflicts, vec![1, 0]);
        assert_eq!(backend.writes, writes);
        assert_eq!(backend.values[&forwarding], Value::Forwarding { enabled: true });
        // The administrator explicitly restores the original value. Recovery
        // now relinquishes our guard without modifying that interface setting.
        backend.values.insert(forwarding.clone(), Value::Forwarding { enabled: false });
        assert!(recover(&mut backend, &mut store, &mut journal).unwrap().conflicts.is_empty());
        assert!(journal.is_restored());
        assert_eq!(backend.values.len(), 1);
    }

    #[test]
    fn failed_not_owned_persistence_cannot_adopt_foreign_forwarding_after_restart() {
        let mut backend = MockNetwork::default();
        let mut journal = gateway_plan(&mut backend);
        let forwarding = journal.changes[1].resource.clone();
        backend.values.insert(forwarding.clone(), Value::Forwarding { enabled: true });
        // Pending, guard Applying/Applied and forwarding Applying persist.
        // NotOwned and every subsequent save fail, then the process dies.
        let mut store = MemoryJournal { fail_save: Some(5), ..Default::default() };
        assert!(apply(&mut backend, &mut store, &mut journal).is_err());
        let mut persisted = store.saved.last().unwrap().clone();
        assert_eq!(persisted.changes[1].state, ChangeState::Applying);
        let writes = backend.writes;
        let report = recover(&mut backend, &mut MemoryJournal::default(), &mut persisted).unwrap();
        assert_eq!(report.conflicts, vec![1, 0]);
        assert_eq!(backend.writes, writes);
        assert_eq!(backend.values[&forwarding], Value::Forwarding { enabled: true });
        assert!(backend.values.contains_key(&persisted.changes[0].resource));
    }

    #[test]
    fn gateway_guard_is_retained_when_unowned_forwarding_is_enabled() {
        for state in [ChangeState::Pending, ChangeState::Restored] {
            let mut backend = MockNetwork::default();
            let mut journal = gateway_plan(&mut backend);
            let guard = journal.changes[0].resource.clone();
            backend.values.insert(guard.clone(), journal.changes[0].after.clone().unwrap());
            journal.changes[0].state = ChangeState::Applied;
            journal.changes[1].state = state;
            let forwarding = journal.changes[1].resource.clone();
            // Foreign change before our write, or after our restore. Neither
            // case grants ownership over this shared Windows boolean.
            backend.values.insert(forwarding.clone(), Value::Forwarding { enabled: true });
            let mut store = MemoryJournal::default();
            let report = recover(&mut backend, &mut store, &mut journal).unwrap();
            assert_eq!(report.conflicts, vec![0]);
            assert_eq!(backend.writes, 0);
            assert!(backend.values.contains_key(&guard));
            backend.values.insert(forwarding, Value::Forwarding { enabled: false });
            assert!(recover(&mut backend, &mut store, &mut journal).unwrap().conflicts.is_empty());
            assert!(journal.is_restored());
            assert_eq!(backend.writes, 1);
        }
    }
}
