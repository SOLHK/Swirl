//! Domain/IP association for callers that see only packet addresses.
//! `Resolver` does not allocate from this table.
use std::{
    collections::{BTreeMap, BTreeSet},
    net::{IpAddr, Ipv4Addr, Ipv6Addr},
    time::{Duration, Instant},
};

/// Virtual adapter address. The first /24 of the Fake-IP range stays reserved.
pub const TUN_IPV4: Ipv4Addr = Ipv4Addr::new(198, 18, 0, 1);
/// Virtual DNS listener. Client queries are answered here inside the TUN path.
pub const DNS_IPV4: Ipv4Addr = Ipv4Addr::new(198, 18, 0, 2);
/// Unique local adapter address. Not a public allocation.
pub const TUN_IPV6: Ipv6Addr = Ipv6Addr::new(0xfd53, 0x5749, 0x524c, 0, 0, 0, 0, 1);
/// Virtual DNS listener for IPv6 queries.
pub const DNS_IPV6: Ipv6Addr = Ipv6Addr::new(0xfd53, 0x5749, 0x524c, 0, 0, 0, 0, 2);

const DEFAULT_CAPACITY: usize = 4096;
const V4_START: u32 = u32::from_be_bytes([198, 18, 1, 0]);
const V4_END: u32 = u32::from_be_bytes([198, 20, 0, 0]);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RecordKind {
    V4,
    V6,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Mapping {
    pub name: String,
    pub expires: Instant,
    pub fake: bool,
}

/// Bounded name ↔ address table. Expired rows are invisible to lookup and are
/// reused. A live address is never silently moved to another name.
#[derive(Debug)]
pub struct Association {
    by_ip: BTreeMap<IpAddr, Mapping>,
    by_name: BTreeMap<String, Vec<IpAddr>>,
    v4_cursor: u32,
    v6_cursor: u64,
    capacity: usize,
    generation: u64,
}

impl Default for Association {
    fn default() -> Self {
        Self::with_capacity(DEFAULT_CAPACITY)
    }
}

impl Association {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self {
            by_ip: BTreeMap::new(),
            by_name: BTreeMap::new(),
            v4_cursor: V4_START,
            v6_cursor: 1,
            capacity: capacity.max(1),
            generation: 1,
        }
    }

    pub fn generation(&self) -> u64 {
        self.generation
    }

    pub fn len(&self) -> usize {
        self.by_ip.len()
    }

    pub fn is_empty(&self) -> bool {
        self.by_ip.is_empty()
    }

    pub fn lookup(&self, ip: IpAddr, now: Instant) -> Option<&str> {
        self.by_ip
            .get(&ip)
            .and_then(|mapping| (mapping.expires > now).then_some(mapping.name.as_str()))
    }

    pub fn addresses(&self, name: &str, now: Instant) -> Vec<IpAddr> {
        let Ok(name) = canonical(name) else {
            return Vec::new();
        };
        self.by_name
            .get(&name)
            .into_iter()
            .flatten()
            .copied()
            .filter(|ip| self.lookup(*ip, now).is_some())
            .collect()
    }

    /// Allocate or refresh one Fake-IP for `name`. The same name keeps its
    /// address until it expires.
    pub fn allocate_fake(
        &mut self,
        name: &str,
        kind: RecordKind,
        now: Instant,
        ttl: Duration,
    ) -> Result<IpAddr, &'static str> {
        let name = canonical(name)?;
        self.expire(now);
        if let Some(existing) = self.live_fake(&name, kind, now) {
            self.refresh(existing, now, ttl)?;
            return Ok(existing);
        }
        self.ensure_room(now)?;
        let ip = match kind {
            RecordKind::V4 => IpAddr::V4(self.take_v4()?),
            RecordKind::V6 => IpAddr::V6(self.take_v6()?),
        };
        self.insert(name, ip, now, ttl, true)?;
        Ok(ip)
    }

    /// Remember resolver answers. Fails closed on a live conflict or on any
    /// address inside the Fake-IP ranges.
    pub fn remember_real(
        &mut self,
        name: &str,
        ips: &[IpAddr],
        now: Instant,
        ttl: Duration,
    ) -> Result<(), &'static str> {
        let name = canonical(name)?;
        if ips.is_empty() || ttl.is_zero() {
            return Err("DnsAssociationEmpty");
        }
        self.expire(now);
        let mut unique = BTreeSet::new();
        for ip in ips {
            if !unique.insert(*ip) {
                continue;
            }
            if fake_range(*ip) {
                return Err("DnsFakeRangeCollision");
            }
            if let Some(mapping) = self.by_ip.get(ip)
                && mapping.expires > now
                && mapping.name != name
            {
                return Err("DnsMappingConflict");
            }
        }
        for ip in unique {
            if self
                .by_ip
                .get(&ip)
                .is_none_or(|mapping| mapping.expires <= now)
            {
                self.ensure_room(now)?;
            }
            self.insert(name.clone(), ip, now, ttl, false)?;
        }
        Ok(())
    }

    pub fn expire(&mut self, now: Instant) {
        let expired: Vec<IpAddr> = self
            .by_ip
            .iter()
            .filter(|(_, mapping)| mapping.expires <= now)
            .map(|(ip, _)| *ip)
            .collect();
        for ip in expired {
            self.remove_ip(ip);
        }
    }

    fn live_fake(&self, name: &str, kind: RecordKind, now: Instant) -> Option<IpAddr> {
        self.by_name.get(name).and_then(|ips| {
            ips.iter().copied().find(|ip| {
                let matching = matches!(
                    (kind, *ip),
                    (RecordKind::V4, IpAddr::V4(_)) | (RecordKind::V6, IpAddr::V6(_))
                );
                matching
                    && self.by_ip.get(ip).is_some_and(|mapping| {
                        mapping.fake && mapping.expires > now && mapping.name == name
                    })
            })
        })
    }

    fn refresh(&mut self, ip: IpAddr, now: Instant, ttl: Duration) -> Result<(), &'static str> {
        let mapping = self.by_ip.get_mut(&ip).ok_or("DnsAssociationMissing")?;
        mapping.expires = now + ttl;
        Ok(())
    }

    fn ensure_room(&mut self, now: Instant) -> Result<(), &'static str> {
        self.expire(now);
        if self.by_ip.len() >= self.capacity {
            Err("DnsAssociationFull")
        } else {
            Ok(())
        }
    }

    fn insert(
        &mut self,
        name: String,
        ip: IpAddr,
        now: Instant,
        ttl: Duration,
        fake: bool,
    ) -> Result<(), &'static str> {
        if let Some(previous) = self.by_ip.get(&ip)
            && previous.name != name
        {
            let old = previous.name.clone();
            self.detach(&old, ip);
        }
        self.by_ip.insert(
            ip,
            Mapping {
                name: name.clone(),
                expires: now + ttl,
                fake,
            },
        );
        let ips = self.by_name.entry(name).or_default();
        if !ips.contains(&ip) {
            ips.push(ip);
        }
        self.generation = self.generation.saturating_add(1);
        Ok(())
    }

    fn remove_ip(&mut self, ip: IpAddr) {
        if let Some(mapping) = self.by_ip.remove(&ip) {
            self.detach(&mapping.name, ip);
        }
    }

    fn detach(&mut self, name: &str, ip: IpAddr) {
        if let Some(ips) = self.by_name.get_mut(name) {
            ips.retain(|item| *item != ip);
            if ips.is_empty() {
                self.by_name.remove(name);
            }
        }
    }

    fn take_v4(&mut self) -> Result<Ipv4Addr, &'static str> {
        let start = self.v4_cursor;
        loop {
            let ip = Ipv4Addr::from(self.v4_cursor.to_be_bytes());
            self.v4_cursor = if self.v4_cursor.saturating_add(1) >= V4_END {
                V4_START
            } else {
                self.v4_cursor + 1
            };
            if !self.by_ip.contains_key(&IpAddr::V4(ip)) && !reserved_v4(ip) {
                return Ok(ip);
            }
            if self.v4_cursor == start {
                return Err("FakeIpExhausted");
            }
        }
    }

    fn take_v6(&mut self) -> Result<Ipv6Addr, &'static str> {
        let start = self.v6_cursor;
        loop {
            let ip = fake_v6(self.v6_cursor);
            self.v6_cursor = self.v6_cursor.saturating_add(1).max(1);
            if !self.by_ip.contains_key(&IpAddr::V6(ip)) && ip != TUN_IPV6 && ip != DNS_IPV6 {
                return Ok(ip);
            }
            if self.v6_cursor == start {
                return Err("FakeIpExhausted");
            }
        }
    }
}

pub fn fake_range(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ip) => {
            let value = u32::from(ip);
            value & 0xfffe_0000 == u32::from(Ipv4Addr::new(198, 18, 0, 0))
        }
        IpAddr::V6(ip) => {
            let segments = ip.segments();
            segments[0] == 0xfd53 && segments[1] == 0x5749 && segments[2] == 0x524c
        }
    }
}

fn reserved_v4(ip: Ipv4Addr) -> bool {
    let octets = ip.octets();
    octets[0] == 198 && octets[1] == 18 && octets[2] == 0
}

fn fake_v6(counter: u64) -> Ipv6Addr {
    Ipv6Addr::new(
        0xfd53,
        0x5749,
        0x524c,
        1,
        (counter >> 48) as u16,
        (counter >> 32) as u16,
        (counter >> 16) as u16,
        counter as u16,
    )
}

fn canonical(name: &str) -> Result<String, &'static str> {
    let name = name.trim_end_matches('.').to_ascii_lowercase();
    if name.parse::<IpAddr>().is_ok() || !swirl_subscription::valid_host(&name) {
        return Err("DnsAssociationName");
    }
    Ok(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fake_addresses_stick_to_a_name_and_cover_both_families() {
        let mut table = Association::new();
        let now = Instant::now();
        let ttl = Duration::from_secs(30);
        let v4 = table
            .allocate_fake("API.Example.com.", RecordKind::V4, now, ttl)
            .unwrap();
        let again = table
            .allocate_fake("api.example.com", RecordKind::V4, now, ttl)
            .unwrap();
        let v6 = table
            .allocate_fake("api.example.com", RecordKind::V6, now, ttl)
            .unwrap();
        assert_eq!(v4, again);
        assert!(fake_range(v4) && fake_range(v6));
        assert_ne!(v4, IpAddr::V4(TUN_IPV4));
        assert_ne!(v4, IpAddr::V4(DNS_IPV4));
        assert_eq!(table.lookup(v4, now), Some("api.example.com"));
        assert_eq!(table.lookup(v6, now), Some("api.example.com"));
        assert!(table.lookup(v4, now + ttl).is_none());
    }

    #[test]
    fn real_mappings_fail_closed_on_conflict_expiry_and_fake_range() {
        let mut table = Association::with_capacity(2);
        let now = Instant::now();
        let ttl = Duration::from_secs(10);
        let first = "1.1.1.1".parse().unwrap();
        let second = "8.8.8.8".parse().unwrap();
        let third = "9.9.9.9".parse().unwrap();
        table
            .remember_real("one.example", &[first], now, ttl)
            .unwrap();
        assert_eq!(
            table.remember_real("two.example", &[first], now, ttl),
            Err("DnsMappingConflict")
        );
        assert_eq!(table.lookup(first, now), Some("one.example"));
        assert_eq!(
            table.remember_real("two.example", &[IpAddr::V4(DNS_IPV4)], now, ttl),
            Err("DnsFakeRangeCollision")
        );
        table
            .remember_real("two.example", &[second], now, ttl)
            .unwrap();
        assert_eq!(
            table.remember_real("three.example", &[third], now, ttl),
            Err("DnsAssociationFull")
        );
        table.expire(now + ttl);
        table
            .remember_real("two.example", &[first, second], now + ttl, ttl)
            .unwrap();
        assert_eq!(table.lookup(first, now + ttl), Some("two.example"));
        assert_eq!(
            table.remember_real("empty.example", &[], now, ttl),
            Err("DnsAssociationEmpty")
        );
        assert_eq!(
            table.allocate_fake("1.2.3.4", RecordKind::V4, now, ttl),
            Err("DnsAssociationName")
        );
    }
}
