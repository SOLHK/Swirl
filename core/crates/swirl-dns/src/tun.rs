//! DNS interception and durable fake-IP identity for native TUN flows.
//!
//! Names are resolved by the caller's existing policy-aware Resolver. This is
//! an inbound DNS adapter, not another resolver. Addresses are never reassigned
//! to another name, including after restart; exhausted address space fails
//! closed. The small append-only identity journal is committed before a reply.
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    fs::{File, OpenOptions},
    future::Future,
    io::{Read, Seek, SeekFrom, Write},
    net::{IpAddr, Ipv4Addr, Ipv6Addr},
    path::Path,
    pin::Pin,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};
use tokio::sync::Semaphore;

pub const DNS_IPV4: Ipv4Addr = Ipv4Addr::new(198, 18, 0, 2);
pub const DNS_IPV6: Ipv6Addr = Ipv6Addr::new(0xfd53, 0x7769, 0x726c, 0, 0, 0, 0, 2);
pub const ANSWER_TTL: u32 = 30;
const RETENTION: u64 = 300;
const V4_BASE: u32 = 0xc612_0000;
const FIRST_ID: u32 = 256;
const LAST_ID: u32 = 0x1fffe;
const JOURNAL_LIMIT: u64 = 64 * 1024 * 1024;
const MAX_QUERY: usize = 4096;
type Result<T> = std::result::Result<T, &'static str>;

/// Implemented by the V2 FlowDispatcher adapter; no system DNS fallback here.
pub trait TunLookup: Send + Sync {
    fn lookup<'a>(
        &'a self,
        name: &'a str,
    ) -> Pin<Box<dyn Future<Output = Result<Vec<IpAddr>>> + Send + 'a>>;
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    name: String,
    id: u32,
    expires: u64,
}

/// Bounded active names. The durable sequence prevents late packets from being
/// mistaken for a newly allocated domain after TTL expiry or a helper restart.
pub struct FakeIpStore {
    capacity: usize,
    names: HashMap<String, Record>,
    reverse: HashMap<u32, String>,
    next: u32,
    journal: Option<File>,
    journal_bytes: u64,
    poisoned: bool,
}

fn now() -> Result<u64> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|time| time.as_secs())
        .map_err(|_| "DnsClock")
}

impl FakeIpStore {
    /// In-memory packet harness only. Production startup must use `open` so OS
    /// DNS caches cannot alias a previous process's fake addresses.
    pub fn memory(capacity: usize) -> Result<Self> {
        if !(1..=65_536).contains(&capacity) {
            return Err("FakeIpCapacity");
        }
        Ok(Self {
            capacity,
            names: HashMap::new(),
            reverse: HashMap::new(),
            next: FIRST_ID,
            journal: None,
            journal_bytes: 0,
            poisoned: false,
        })
    }

    pub fn open(path: &Path, capacity: usize) -> Result<Self> {
        let mut result = Self::memory(capacity)?;
        if !path.is_absolute() {
            return Err("FakeIpJournalPath");
        }
        if std::fs::symlink_metadata(path).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
            return Err("FakeIpJournalSymlink");
        }
        let mut options = OpenOptions::new();
        // Windows append-only handles cannot truncate a torn final record.
        // The exclusive lock below owns this read/write handle until drop.
        options.read(true).write(true).create(true).truncate(false);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut journal = options.open(path).map_err(|_| "FakeIpJournalOpen")?;
        journal.try_lock().map_err(|_| "FakeIpJournalOwned")?;
        let size = journal.metadata().map_err(|_| "FakeIpJournalRead")?.len();
        if size > JOURNAL_LIMIT {
            return Err("FakeIpJournalLimit");
        }
        let mut bytes = Vec::with_capacity(size as usize);
        (&mut journal)
            .take(JOURNAL_LIMIT + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "FakeIpJournalRead")?;
        if bytes.len() as u64 > JOURNAL_LIMIT {
            return Err("FakeIpJournalLimit");
        }
        // No reply can have exposed an incomplete record: append + sync_all
        // must succeed first. Ignore only a torn final append, never bad lines.
        let complete = bytes
            .iter()
            .rposition(|byte| *byte == b'\n')
            .map_or(0, |i| i + 1);
        let current = now()?;
        let mut identities = HashMap::new();
        for line in bytes[..complete]
            .split(|byte| *byte == b'\n')
            .filter(|line| !line.is_empty())
        {
            if line.len() > 1024 {
                return Err("FakeIpJournalInvalid");
            }
            let record: Record =
                serde_json::from_slice(line).map_err(|_| "FakeIpJournalInvalid")?;
            if canonical(&record.name)? != record.name || !(FIRST_ID..=LAST_ID).contains(&record.id)
            {
                return Err("FakeIpJournalInvalid");
            }
            if record.id == result.next {
                identities.insert(record.id, record.name.clone());
                result.next += 1;
            } else if identities.get(&record.id) != Some(&record.name) {
                return Err("FakeIpJournalSequence");
            }
            // A renewal may only extend the same identity, never steal an ID.
            if let Some(existing) = result.reverse.get(&record.id)
                && existing != &record.name
            {
                return Err("FakeIpJournalConflict");
            }
            if record.expires > current {
                if result
                    .names
                    .get(&record.name)
                    .is_some_and(|old| old.id != record.id)
                {
                    return Err("FakeIpJournalConflict");
                }
                result.reverse.insert(record.id, record.name.clone());
                result.names.insert(record.name.clone(), record);
            }
        }
        if result.names.len() > capacity {
            return Err("FakeIpCapacity");
        }
        journal
            .set_len(complete as u64)
            .map_err(|_| "FakeIpJournalRepair")?;
        // set_len does not reposition the cursor after reading a torn tail.
        // Keep subsequent, serialized writes at the repaired journal's end.
        journal
            .seek(SeekFrom::End(0))
            .map_err(|_| "FakeIpJournalRepair")?;
        journal.sync_all().map_err(|_| "FakeIpJournalSync")?;
        result.journal_bytes = complete as u64;
        result.journal = Some(journal);
        Ok(result)
    }

    fn allocate(&mut self, name: &str, at: u64) -> Result<u32> {
        if self.poisoned {
            return Err("FakeIpJournalSync");
        }
        let name = canonical(name)?;
        if let Some(record) = self.names.get(&name)
            && record.expires >= at.saturating_add(2 * u64::from(ANSWER_TTL))
        {
            return Ok(record.id);
        }
        let existing = self
            .names
            .get(&name)
            .filter(|entry| entry.expires > at)
            .map(|entry| entry.id);
        if existing.is_none() {
            self.expire(at);
            if self.names.len() >= self.capacity {
                return Err("FakeIpCapacity");
            }
            if self.next > LAST_ID {
                return Err("FakeIpAddressSpaceExhausted");
            }
        }
        let record = Record {
            name: name.clone(),
            id: existing.unwrap_or(self.next),
            expires: at.checked_add(RETENTION).ok_or("DnsClock")?,
        };
        if let Some(journal) = &mut self.journal {
            let mut bytes = serde_json::to_vec(&record).map_err(|_| "FakeIpJournalEncode")?;
            bytes.push(b'\n');
            if self.journal_bytes + bytes.len() as u64 > JOURNAL_LIMIT {
                return Err("FakeIpJournalLimit");
            }
            // A partial write poisons this process's allocator. Reopening from
            // the journal is required, avoiding appending after a torn record.
            if journal
                .write_all(&bytes)
                .and_then(|_| journal.sync_all())
                .is_err()
            {
                self.poisoned = true;
                return Err("FakeIpJournalSync");
            }
            self.journal_bytes += bytes.len() as u64;
        }
        if existing.is_none() {
            self.next += 1;
        }
        self.reverse.insert(record.id, name.clone());
        self.names.insert(name, record.clone());
        Ok(record.id)
    }

    fn expire(&mut self, at: u64) {
        let reverse = &mut self.reverse;
        self.names.retain(|_, record| {
            if record.expires <= at {
                reverse.remove(&record.id);
                false
            } else {
                true
            }
        });
    }

    /// None means a real IP. An unknown/expired address from either reserved
    /// range is an error, never a real-IP DIRECT/proxy destination.
    pub fn domain(&self, address: IpAddr) -> Result<Option<String>> {
        self.domain_at(address, now()?)
    }

    fn domain_at(&self, address: IpAddr, at: u64) -> Result<Option<String>> {
        let Some(id) = fake_id(address) else {
            return Ok(None);
        };
        let name = self.reverse.get(&id).ok_or("FakeIpUnknown")?;
        let record = self.names.get(name).ok_or("FakeIpUnknown")?;
        if record.expires <= at {
            return Err("FakeIpExpired");
        }
        Ok(Some(name.clone()))
    }

    pub fn active_names(&self) -> usize {
        self.names.len()
    }
}

fn canonical(name: &str) -> Result<String> {
    let name = name.trim_end_matches('.').to_ascii_lowercase();
    if name.parse::<IpAddr>().is_ok() || !swirl_subscription::valid_host(&name) {
        return Err("DnsQueryName");
    }
    Ok(name)
}

fn fake_id(address: IpAddr) -> Option<u32> {
    match address {
        IpAddr::V4(ip) => {
            let bits = u32::from(ip);
            (bits & 0xfffe_0000 == V4_BASE).then_some(bits.wrapping_sub(V4_BASE))
        }
        IpAddr::V6(ip) => {
            let segments = ip.segments();
            if segments[..4] != [0xfd53, 0x7769, 0x726c, 0] {
                return None;
            }
            if segments[4] != 0 || segments[5] != 0 {
                return Some(u32::MAX);
            }
            Some((u32::from(segments[6]) << 16) | u32::from(segments[7]))
        }
    }
}

fn fake_address(id: u32, ipv6: bool) -> IpAddr {
    if ipv6 {
        Ipv6Addr::new(
            0xfd53,
            0x7769,
            0x726c,
            0,
            0,
            0,
            (id >> 16) as u16,
            id as u16,
        )
        .into()
    } else {
        Ipv4Addr::from(V4_BASE + id).into()
    }
}

struct Question {
    id: u16,
    flags: u16,
    name: String,
    kind: u16,
    wire: Vec<u8>,
}

fn question(data: &[u8]) -> Result<Question> {
    use crate::wire::{name_labels, word};
    if !(12..=MAX_QUERY).contains(&data.len()) {
        return Err("DnsQuerySize");
    }
    let flags = word(data, 2)?;
    if flags & 0xf840 != 0
        || word(data, 4)? != 1
        || word(data, 6)? != 0
        || word(data, 8)? != 0
        || word(data, 10)? > 1
    {
        return Err("DnsQueryHeader");
    }
    let mut cursor = 12;
    let labels = name_labels(data, &mut cursor)?;
    let mut name = Vec::new();
    let mut wire = Vec::new();
    for label in labels {
        if !name.is_empty() {
            name.push(b'.');
        }
        name.extend_from_slice(label);
        wire.push(label.len() as u8);
        wire.extend_from_slice(label);
    }
    wire.push(0);
    let kind = word(data, cursor)?;
    if word(data, cursor + 2)? != 1 {
        return Err("DnsQueryClass");
    }
    wire.extend_from_slice(&data[cursor..cursor + 4]);
    cursor += 4;
    if word(data, 10)? == 1 {
        // Validate one EDNS0 OPT record. No client-controlled hints/extra
        // answers are copied into the synthetic DNS response.
        if *data.get(cursor).ok_or("DnsTruncated")? != 0
            || word(data, cursor + 1)? != 41
            || *data.get(cursor + 6).ok_or("DnsTruncated")? != 0
        {
            return Err("DnsQueryEdns");
        }
        let size = usize::from(word(data, cursor + 9)?);
        cursor = cursor.checked_add(11 + size).ok_or("DnsTruncated")?;
    }
    if cursor != data.len() {
        return Err("DnsQueryTrailing");
    }
    let name = canonical(std::str::from_utf8(&name).map_err(|_| "DnsQueryName")?)?;
    Ok(Question {
        id: word(data, 0)?,
        flags,
        name,
        kind,
        wire,
    })
}

fn response(question: &Question, rcode: u16, address: Option<IpAddr>) -> Vec<u8> {
    let mut data = Vec::with_capacity(question.wire.len() + 40);
    data.extend(question.id.to_be_bytes());
    // DNSSEC AD is deliberately clear: fake-IP records are locally synthesized.
    data.extend((0x8080 | (question.flags & 0x0110) | rcode).to_be_bytes());
    data.extend(1u16.to_be_bytes());
    data.extend(u16::from(address.is_some()).to_be_bytes());
    data.extend([0, 0, 0, 0]);
    data.extend_from_slice(&question.wire);
    if let Some(address) = address {
        data.extend([0xc0, 0x0c]);
        data.extend(question.kind.to_be_bytes());
        data.extend([0, 1]);
        data.extend(ANSWER_TTL.to_be_bytes());
        match address {
            IpAddr::V4(ip) => {
                data.extend(4u16.to_be_bytes());
                data.extend(ip.octets());
            }
            IpAddr::V6(ip) => {
                data.extend(16u16.to_be_bytes());
                data.extend(ip.octets());
            }
        }
    }
    data
}

#[derive(Clone)]
pub struct TunDns {
    store: Arc<Mutex<FakeIpStore>>,
    queries: Arc<Semaphore>,
}

impl TunDns {
    pub fn new(store: FakeIpStore) -> Self {
        Self {
            store: Arc::new(Mutex::new(store)),
            queries: Arc::new(Semaphore::new(16)),
        }
    }

    pub async fn target_host(&self, address: IpAddr) -> Result<String> {
        if fake_id(address).is_none() {
            return Ok(address.to_string());
        }
        let permit = self
            .queries
            .clone()
            .acquire_owned()
            .await
            .map_err(|_| "FakeIpStopped")?;
        let store = self.store.clone();
        tokio::task::spawn_blocking(move || {
            let _permit = permit;
            store
                .lock()
                .map_err(|_| "FakeIpState")?
                .domain(address)
                .map(|domain| domain.unwrap_or_else(|| address.to_string()))
        })
        .await
        .map_err(|_| "FakeIpTask")?
    }

    pub async fn answer(&self, request: &[u8], resolver: &dyn TunLookup) -> Result<Vec<u8>> {
        let query = question(request)?;
        let Ok(permit) = self.queries.clone().try_acquire_owned() else {
            return Ok(response(&query, 2, None));
        };
        // HTTPS/SVCB IP hints could bypass the one-name identity. NODATA makes
        // clients use ordinary A/AAAA; other RR types are explicitly unsupported.
        if matches!(query.kind, 64 | 65) {
            return Ok(response(&query, 0, None));
        }
        if !matches!(query.kind, 1 | 28) {
            return Ok(response(&query, 4, None));
        }
        let addresses = match resolver.lookup(&query.name).await {
            Ok(addresses) => addresses,
            Err("DnsNameError") => return Ok(response(&query, 3, None)),
            Err("DnsEmpty") => return Ok(response(&query, 0, None)),
            Err(_) => return Ok(response(&query, 2, None)),
        };
        let ipv6 = query.kind == 28;
        if !addresses.iter().any(|address| address.is_ipv6() == ipv6) {
            return Ok(response(&query, 0, None));
        }
        let store = self.store.clone();
        let name = query.name.clone();
        // Durable allocation may sync a disk journal. Keep it off Tokio workers;
        // the shared semaphore bounds these jobs even under a DNS flood.
        let allocated = tokio::task::spawn_blocking(move || {
            let _permit = permit;
            store
                .lock()
                .map_err(|_| "FakeIpState")?
                .allocate(&name, now()?)
        })
        .await
        .map_err(|_| "FakeIpTask")?;
        match allocated {
            Ok(id) => Ok(response(&query, 0, Some(fake_address(id, ipv6)))),
            Err(_) => Ok(response(&query, 2, None)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Lookup(Result<Vec<IpAddr>>);
    impl TunLookup for Lookup {
        fn lookup<'a>(
            &'a self,
            _: &'a str,
        ) -> Pin<Box<dyn Future<Output = Result<Vec<IpAddr>>> + Send + 'a>> {
            Box::pin(async { self.0.clone() })
        }
    }

    #[test]
    fn capacity_expiry_and_late_packets_do_not_alias_domains() {
        let mut store = FakeIpStore::memory(1).unwrap();
        let first = store.allocate("EXAMPLE.test.", 10).unwrap();
        assert_eq!(store.allocate("example.test", 20).unwrap(), first);
        assert_eq!(store.allocate("other.test", 20), Err("FakeIpCapacity"));
        assert_eq!(
            store
                .domain_at(fake_address(first, false), 10)
                .unwrap()
                .as_deref(),
            Some("example.test")
        );
        assert_eq!(
            store.domain_at(fake_address(first, true), 311),
            Err("FakeIpExpired")
        );
        let second = store.allocate("other.test", 311).unwrap();
        assert_ne!(first, second);
        assert_eq!(
            store.domain_at(fake_address(first, false), 311),
            Err("FakeIpUnknown")
        );
        assert_eq!(
            store.domain_at("203.0.113.10".parse().unwrap(), 311),
            Ok(None)
        );
        assert_eq!(store.domain_at(DNS_IPV6.into(), 311), Err("FakeIpUnknown"));
    }

    #[test]
    fn durable_sequence_survives_reopen_and_torn_append() {
        let path = std::env::temp_dir().join(format!(
            "swirl-fakeip-{}-{}.jsonl",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let at = now().unwrap();
        let first = {
            let mut store = FakeIpStore::open(&path, 4).unwrap();
            store.allocate("one.test", at).unwrap()
        };
        OpenOptions::new()
            .append(true)
            .open(&path)
            .unwrap()
            .write_all(b"{\"torn\":")
            .unwrap();
        let mut store = FakeIpStore::open(&path, 4).unwrap();
        assert!(matches!(
            FakeIpStore::open(&path, 4),
            Err("FakeIpJournalOwned")
        ));
        assert_eq!(
            store
                .domain_at(fake_address(first, true), at)
                .unwrap()
                .as_deref(),
            Some("one.test")
        );
        assert_ne!(store.allocate("two.test", at).unwrap(), first);
        drop(store);
        let reopened = FakeIpStore::open(&path, 4).unwrap();
        assert_eq!(reopened.active_names(), 2);
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn journal_reopen_and_renewal_preserve_complete_record_prefix() {
        let path = std::env::temp_dir().join(format!(
            "swirl-fakeip-prefix-{}-{}.jsonl",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let at = now().unwrap();
        let (first, second) = {
            let mut store = FakeIpStore::open(&path, 4).unwrap();
            (
                store.allocate("one.test", at).unwrap(),
                store.allocate("two.test", at).unwrap(),
            )
        };
        let prefix = std::fs::read(&path).unwrap();
        OpenOptions::new()
            .append(true)
            .open(&path)
            .unwrap()
            .write_all(b"{\"torn\":")
            .unwrap();
        let renewed_at = at + RETENTION - u64::from(ANSWER_TTL);
        let third = {
            let mut store = FakeIpStore::open(&path, 4).unwrap();
            assert_eq!(store.allocate("one.test", renewed_at).unwrap(), first);
            store.allocate("three.test", renewed_at).unwrap()
        };
        let repaired = std::fs::read(&path).unwrap();
        assert!(repaired.starts_with(&prefix));
        let fourth = {
            let mut store = FakeIpStore::open(&path, 4).unwrap();
            store.allocate("four.test", renewed_at).unwrap()
        };
        let appended = std::fs::read(&path).unwrap();
        assert!(appended.starts_with(&repaired));
        let records: Vec<Record> = appended
            .split(|byte| *byte == b'\n')
            .filter(|line| !line.is_empty())
            .map(|line| serde_json::from_slice(line).unwrap())
            .collect();
        assert_eq!(
            records
                .iter()
                .map(|record| (record.name.as_str(), record.id))
                .collect::<Vec<_>>(),
            [
                ("one.test", first),
                ("two.test", second),
                ("one.test", first),
                ("three.test", third),
                ("four.test", fourth),
            ]
        );
        assert_eq!((second, third, fourth), (first + 1, first + 2, first + 3));
        std::fs::remove_file(path).unwrap();
    }

    #[tokio::test]
    async fn dual_stack_answers_preserve_question_and_recover_domain() {
        let dns = TunDns::new(FakeIpStore::memory(8).unwrap());
        let lookup = Lookup(Ok(vec![
            "203.0.113.1".parse().unwrap(),
            "2001:db8::1".parse().unwrap(),
        ]));
        for kind in [1, 28] {
            let request = crate::wire::query("ExAmPlE.test", kind).unwrap();
            let answer = dns.answer(&request, &lookup).await.unwrap();
            let crate::wire::Response::Answer(parsed) =
                crate::wire::parse(&answer, &request, "example.test", kind).unwrap()
            else {
                panic!("truncated");
            };
            assert_eq!(parsed.addresses.len(), 1);
            assert_eq!(parsed.ttl, ANSWER_TTL);
            assert_eq!(
                dns.target_host(parsed.addresses[0]).await.unwrap(),
                "example.test"
            );
            assert_eq!(&answer[12..request.len()], &request[12..]);
            assert_eq!(answer[3] & 0x20, 0);
        }
    }

    #[tokio::test]
    async fn failure_nxdomain_nodata_and_bad_queries_are_distinct() {
        let dns = TunDns::new(FakeIpStore::memory(1).unwrap());
        let request = crate::wire::query("name.test", 1).unwrap();
        for (error, rcode) in [("DnsNameError", 3), ("DnsEmpty", 0), ("DnsTimeout", 2)] {
            let answer = dns.answer(&request, &Lookup(Err(error))).await.unwrap();
            assert_eq!(answer[3] & 15, rcode);
            assert_eq!(answer[7], 0);
        }
        let mut bad = request.clone();
        bad[12] = 0xc0;
        bad[13] = 12;
        assert!(dns.answer(&bad, &Lookup(Err("DnsTimeout"))).await.is_err());
        let request = crate::wire::query("name.test", 28).unwrap();
        let answer = dns
            .answer(&request, &Lookup(Ok(vec!["203.0.113.1".parse().unwrap()])))
            .await
            .unwrap();
        assert_eq!((answer[3] & 15, answer[7]), (0, 0));
        let mut bad = request;
        bad.push(0);
        assert!(dns.answer(&bad, &Lookup(Err("DnsTimeout"))).await.is_err());
    }
}
