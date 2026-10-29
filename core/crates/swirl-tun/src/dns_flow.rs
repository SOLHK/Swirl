//! Answers intercepted DNS queries without changing `swirl_dns::Resolver`.
use std::{
    collections::BTreeMap,
    net::IpAddr,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

use swirl_dns::{AAAA, Association, DNS_A, RecordKind};

pub enum DnsReply {
    Addresses(Vec<IpAddr>),
    NameError,
}

pub trait DnsAnswer: Send {
    fn answer(&mut self, name: &str, kind: u16, now: Instant) -> Result<DnsReply, &'static str>;
}

pub struct TableDns {
    association: Arc<Mutex<Association>>,
    fake: bool,
    ttl: Duration,
    real: BTreeMap<String, Vec<IpAddr>>,
}

impl TableDns {
    pub fn fake(ttl: Duration) -> (Self, Arc<Mutex<Association>>) {
        Self::build(true, ttl)
    }

    pub fn real(ttl: Duration) -> (Self, Arc<Mutex<Association>>) {
        Self::build(false, ttl)
    }

    fn build(fake: bool, ttl: Duration) -> (Self, Arc<Mutex<Association>>) {
        let association = Arc::new(Mutex::new(Association::new()));
        (
            Self {
                association: association.clone(),
                fake,
                ttl,
                real: BTreeMap::new(),
            },
            association,
        )
    }

    pub fn insert_real(&mut self, name: impl Into<String>, addresses: Vec<IpAddr>) {
        self.real
            .insert(name.into().to_ascii_lowercase(), addresses);
    }
}

impl DnsAnswer for TableDns {
    fn answer(&mut self, name: &str, kind: u16, now: Instant) -> Result<DnsReply, &'static str> {
        let record = match kind {
            DNS_A => RecordKind::V4,
            AAAA => RecordKind::V6,
            _ => return Err("DnsKind"),
        };
        let mut table = self.association.lock().map_err(|_| "DnsState")?;
        if self.fake {
            let ip = table.allocate_fake(name, record, now, self.ttl)?;
            return Ok(DnsReply::Addresses(vec![ip]));
        }
        let key = name.trim_end_matches('.').to_ascii_lowercase();
        let Some(addresses) = self.real.get(&key).cloned() else {
            return Ok(DnsReply::NameError);
        };
        let selected: Vec<IpAddr> = addresses
            .into_iter()
            .filter(|ip| {
                matches!(
                    (record, ip),
                    (RecordKind::V4, IpAddr::V4(_)) | (RecordKind::V6, IpAddr::V6(_))
                )
            })
            .collect();
        if selected.is_empty() {
            return Ok(DnsReply::NameError);
        }
        table.remember_real(&key, &selected, now, self.ttl)?;
        Ok(DnsReply::Addresses(selected))
    }
}
