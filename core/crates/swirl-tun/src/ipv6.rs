//! Bounded IPv6 UDP reply framing using smoltcp's wire types. smoltcp 0.14
//! does not process IPv6 Fragment headers in its L3 interface.
use crate::UdpDatagram;
use smoltcp::{
    phy::ChecksumCapabilities,
    wire::{
        IpProtocol, Ipv6FragmentHeader, Ipv6FragmentRepr, Ipv6Packet, Ipv6Repr, UdpPacket, UdpRepr,
    },
};
use std::net::Ipv6Addr;

pub(crate) struct UdpFragments {
    source: Ipv6Addr,
    destination: Ipv6Addr,
    bytes: Vec<u8>,
    offset: usize,
    ident: u32,
}

impl UdpFragments {
    pub fn new(datagram: UdpDatagram, ident: u32) -> Option<Self> {
        let (std::net::IpAddr::V6(source), std::net::IpAddr::V6(destination)) =
            (datagram.source.ip(), datagram.destination.ip())
        else {
            return None;
        };
        let mut bytes = vec![0; 8 + datagram.payload.len()];
        UdpRepr {
            src_port: datagram.source.port(),
            dst_port: datagram.destination.port(),
        }
        .emit(
            &mut UdpPacket::new_unchecked(&mut bytes[..]),
            &source.into(),
            &destination.into(),
            datagram.payload.len(),
            |target| target.copy_from_slice(&datagram.payload),
            &ChecksumCapabilities::default(),
        );
        Some(Self {
            source,
            destination,
            bytes,
            offset: 0,
            ident,
        })
    }

    pub fn next(&mut self, mtu: usize) -> Vec<u8> {
        // IPv6 + Fragment headers consume 48 bytes. Non-final fragments must
        // contain a multiple of 8 bytes. MTU validation guarantees >= 1280.
        let capacity = (mtu - 48) / 8 * 8;
        let len = (self.bytes.len() - self.offset).min(capacity);
        let mut packet = vec![0; 48 + len];
        Ipv6Repr {
            src_addr: self.source,
            dst_addr: self.destination,
            next_header: IpProtocol::Ipv6Frag,
            payload_len: 8 + len,
            hop_limit: 64,
        }
        .emit(&mut Ipv6Packet::new_unchecked(&mut packet[..]));
        packet[40] = u8::from(IpProtocol::Udp);
        Ipv6FragmentRepr {
            frag_offset: (self.offset / 8) as u16,
            more_frags: self.offset + len < self.bytes.len(),
            ident: self.ident,
        }
        .emit(&mut Ipv6FragmentHeader::new_unchecked(&mut packet[42..48]));
        packet[48..].copy_from_slice(&self.bytes[self.offset..self.offset + len]);
        self.offset += len;
        packet
    }

    pub fn finished(&self) -> bool {
        self.offset == self.bytes.len()
    }
}

use smoltcp::storage::Assembler;
use std::{
    collections::HashMap,
    time::{Duration, Instant},
};

type FragmentKey = (Ipv6Addr, Ipv6Addr, u32);
const MAX_REASSEMBLIES: usize = 4;
const FRAGMENT_TTL: Duration = Duration::from_secs(60);

struct Assembly {
    created: Instant,
    next_header: u8,
    prefix: Vec<u8>,
    previous_header: usize,
    data: Vec<u8>,
    ranges: Assembler,
    total: Option<usize>,
    rejected: bool,
}

/// The upstream L3 interface does not consume IPv6 Fragment headers. This
/// bounded adapter uses smoltcp's range assembler and wire parsing, discards
/// overlapping fragment sets, and hands complete packets back to smoltcp.
pub(crate) struct Reassembler {
    entries: HashMap<FragmentKey, Assembly>,
}

impl Reassembler {
    pub fn new() -> Self {
        Self {
            entries: HashMap::new(),
        }
    }

    pub fn expire(&mut self) {
        self.entries
            .retain(|_, entry| entry.created.elapsed() < FRAGMENT_TTL);
    }

    pub fn ingest(&mut self, bytes: Vec<u8>) -> Result<Option<Vec<u8>>, ()> {
        if bytes.first().is_none_or(|b| b >> 4 != 6) {
            return Ok(Some(bytes));
        }
        let packet = Ipv6Packet::new_checked(&bytes[..]).map_err(|_| ())?;
        if usize::from(packet.payload_len()) + 40 != bytes.len() {
            return Err(());
        }
        let mut next = u8::from(packet.next_header());
        let mut offset = 40;
        let mut previous_header = 6;
        // Locate the Fragment header without interpreting extension semantics;
        // unsupported extension headers are left for smoltcp to reject.
        for _ in 0..16 {
            if next == 44 {
                break;
            }
            if !matches!(next, 0 | 43 | 60) {
                return Ok(Some(bytes));
            }
            if bytes.len() < offset + 2 {
                return Err(());
            }
            let len = (usize::from(bytes[offset + 1]) + 1) * 8;
            if bytes.len() < offset + len {
                return Err(());
            }
            previous_header = offset;
            next = bytes[offset];
            offset += len;
        }
        if next != 44 {
            return Err(());
        }
        if bytes.len() < offset + 8 || offset > 2048 {
            return Err(());
        }
        let header =
            Ipv6FragmentHeader::new_checked(&bytes[offset + 2..offset + 8]).map_err(|_| ())?;
        let start = usize::from(header.frag_offset()) * 8;
        let more = header.more_frags();
        let next_header = bytes[offset];
        let payload = &bytes[offset + 8..];
        let end = start.checked_add(payload.len()).ok_or(())?;
        if payload.is_empty()
            || end + offset - 40 > 65535
            || (more && !payload.len().is_multiple_of(8))
            || bytes[offset + 1] != 0
            || bytes[offset + 3] & 0x06 != 0
        {
            return Err(());
        }
        // Fragment headers are not allowed recursively; the first fragment
        // must include a complete supported transport header (RFC 7112).
        if next_header == 44
            || (start == 0
                && match next_header {
                    6 => payload.len() < 20,
                    17 => payload.len() < 8,
                    _ => false,
                })
        {
            return Err(());
        }
        let mut prefix = bytes[..offset].to_vec();
        prefix[previous_header] = next_header;
        // Atomic fragments are processed independently of cached fragment IDs.
        if start == 0 && !more {
            prefix.extend_from_slice(payload);
            let len = (prefix.len() - 40) as u16;
            prefix[4..6].copy_from_slice(&len.to_be_bytes());
            return Ok(Some(prefix));
        }
        let key = (packet.src_addr(), packet.dst_addr(), header.ident());
        self.expire();
        if !self.entries.contains_key(&key) {
            if self.entries.len() >= MAX_REASSEMBLIES {
                return Err(());
            }
            self.entries.insert(
                key,
                Assembly {
                    created: Instant::now(),
                    next_header,
                    prefix,
                    previous_header,
                    data: Vec::new(),
                    ranges: Assembler::new(),
                    total: None,
                    rejected: false,
                },
            );
        }
        let entry = self.entries.get_mut(&key).ok_or(())?;
        if entry.rejected {
            return Err(());
        }
        let incompatible = entry.next_header != next_header
            || entry.prefix.len() != offset
            || entry.previous_header != previous_header;
        let overlap = entry
            .ranges
            .iter_data()
            .any(|(left, right)| left < end && start < right);
        let past_end = entry
            .total
            .is_some_and(|total| end > total || (!more && end != total));
        let conflicting_end = !more && entry.ranges.iter_data().any(|(_, right)| right > end);
        if incompatible
            || overlap
            || past_end
            || conflicting_end
            || entry.ranges.add(start, payload.len()).is_err()
        {
            // Keep a small tombstone until expiry, so later fragments cannot
            // revive an explicitly rejected overlapping datagram (RFC 5722).
            entry.rejected = true;
            entry.data.clear();
            entry.data.shrink_to_fit();
            return Err(());
        }
        if !more {
            entry.total = Some(end);
        }
        if entry.data.len() < end {
            entry.data.resize(end, 0);
        }
        entry.data[start..end].copy_from_slice(payload);
        if start == 0 {
            entry.prefix.copy_from_slice(&bytes[..offset]);
            entry.prefix[previous_header] = next_header;
        }
        if entry.total != Some(entry.ranges.peek_front()) {
            return Ok(None);
        }
        let mut entry = self.entries.remove(&key).ok_or(())?;
        entry.prefix.extend_from_slice(&entry.data);
        let len = (entry.prefix.len() - 40) as u16;
        entry.prefix[4..6].copy_from_slice(&len.to_be_bytes());
        Ok(Some(entry.prefix))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fragments(id: u32) -> Vec<Vec<u8>> {
        let mut sender = UdpFragments::new(
            UdpDatagram {
                source: "[2001:db8::10]:40000".parse().unwrap(),
                destination: "[2001:db8::20]:4444".parse().unwrap(),
                payload: vec![42; 5000],
            },
            id,
        )
        .unwrap();
        let mut result = Vec::new();
        while !sender.finished() {
            result.push(sender.next(1500));
        }
        result
    }

    #[test]
    fn overlapping_ipv6_fragments_poison_the_whole_set_until_expiry() {
        let parts = fragments(123);
        let mut receiver = Reassembler::new();
        assert!(receiver.ingest(parts[0].clone()).unwrap().is_none());
        assert!(receiver.ingest(parts[0].clone()).is_err());
        for part in &parts[1..] {
            assert!(receiver.ingest(part.clone()).is_err());
        }
        assert!(
            receiver
                .entries
                .values()
                .all(|entry| entry.rejected && entry.data.is_empty())
        );
        // An independent datagram remains usable after malformed input.
        let mut complete = None;
        for part in fragments(124) {
            complete = receiver.ingest(part).unwrap().or(complete);
        }
        assert!(complete.is_some());
    }

    #[test]
    fn ipv6_reassembly_slots_are_bounded_and_expire() {
        let mut receiver = Reassembler::new();
        for id in 0..MAX_REASSEMBLIES as u32 {
            assert!(receiver.ingest(fragments(id)[0].clone()).unwrap().is_none());
        }
        assert!(receiver.ingest(fragments(99)[0].clone()).is_err());
        assert_eq!(receiver.entries.len(), MAX_REASSEMBLIES);
        for entry in receiver.entries.values_mut() {
            entry.created -= FRAGMENT_TTL + Duration::from_secs(1);
        }
        receiver.expire();
        assert!(receiver.entries.is_empty());
        assert!(receiver.ingest(fragments(99)[0].clone()).unwrap().is_none());
    }
}
