//! Bounded reader for the bundled MetaCubeX MRS v1 domain/IP rule sets.
//! The container is Zstandard-compressed; the decoded payload is validated
//! independently of routing so malformed assets can never become permissive.
use sha2::Digest;
use std::{io::Read, net::IpAddr};

const MAX_COMPRESSED: usize = 16 * 1024 * 1024;
const MAX_DECOMPRESSED: usize = 64 * 1024 * 1024;
const MAX_ITEMS: usize = 2_000_000;
const MRS_MAGIC: &[u8; 4] = b"MRS\x01";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Behavior { Domain, IpCidr }

#[derive(Debug, Clone)]
pub struct ChinaRules {
    domains: Vec<String>,
    networks: Vec<(IpAddr, IpAddr)>,
}

impl ChinaRules {
    pub fn parse(bytes: &[u8], expected: Behavior, expected_sha256: &[u8; 32]) -> Result<Self, &'static str> {
        if bytes.is_empty() || bytes.len() > MAX_COMPRESSED { return Err("MrsCompressedSize"); }
        let digest = sha2::Sha256::digest(bytes);
        if digest.as_slice() != expected_sha256 { return Err("MrsChecksum"); }
        let decoder = zstd::stream::read::Decoder::new(bytes).map_err(|_| "MrsZstdHeader")?;
        let mut decoded = Vec::new();
        decoder.take((MAX_DECOMPRESSED + 1) as u64).read_to_end(&mut decoded).map_err(|_| "MrsZstdDecode")?;
        if decoded.len() > MAX_DECOMPRESSED { return Err("MrsDecompressedSize"); }
        let mut c = Cursor::new(&decoded);
        if c.take(4)? != MRS_MAGIC { return Err("MrsMagic"); }
        let behavior = c.byte()?;
        let wanted = match expected { Behavior::Domain => 0, Behavior::IpCidr => 1 };
        if behavior != wanted { return Err("MrsBehavior"); }
        let count = c.i64()?; let extra_len = c.i64()?;
        if count < 1 || count as usize > MAX_ITEMS || extra_len < 0 || extra_len as usize > 1024 * 1024 { return Err("MrsHeaderBounds"); }
        c.take(extra_len as usize)?;
        let (domains, networks) = match expected {
            Behavior::Domain => (decode_domains(&mut c, count as usize)?, Vec::new()),
            Behavior::IpCidr => (Vec::new(), decode_ip_ranges(&mut c, count as usize)?),
        };
        if !c.is_empty() { return Err("MrsTrailingData"); }
        Ok(Self { domains, networks })
    }

    pub fn matches_domain(&self, host: &str) -> bool {
        let host = host.trim_end_matches('.').to_ascii_lowercase();
        self.domains.iter().any(|rule| {
            if let Some(suffix) = rule.strip_prefix("+.") {
                host == suffix || host.strip_suffix(suffix).is_some_and(|p| p.ends_with('.'))
            } else if let Some(suffix) = rule.strip_prefix('.') {
                host != suffix && host.strip_suffix(suffix).is_some_and(|p| p.ends_with('.'))
            } else if rule.contains('*') {
                wildcard_domain(rule, &host)
            } else { host == *rule }
        })
    }

    pub fn matches_ip(&self, ip: IpAddr) -> bool {
        self.networks.iter().any(|(start, end)| ip_cmp(ip, *start).is_some_and(|a| a >= 0) && ip_cmp(ip, *end).is_some_and(|b| b <= 0))
    }
}

fn wildcard_domain(pattern: &str, host: &str) -> bool {
    let p: Vec<_> = pattern.split('.').collect();
    let h: Vec<_> = host.split('.').collect();
    p.len() == h.len() && p.iter().zip(h).all(|(a,b)| *a == "*" || *a == b)
}

fn decode_domains(c: &mut Cursor<'_>, count: usize) -> Result<Vec<String>, &'static str> {
    let version = c.byte()?; if version != 1 { return Err("MrsDomainVersion"); }
    let leaves = c.u64_vec()?; let bitmap = c.u64_vec()?; let labels = c.bytes_vec()?;
    if leaves.len() > MAX_ITEMS || bitmap.len() > MAX_ITEMS * 4 || labels.len() > MAX_ITEMS * 64 { return Err("MrsDomainBounds"); }
    if leaves.is_empty() || bitmap.is_empty() || labels.is_empty() { return Err("MrsDomainEmpty"); }
    let mut out = Vec::with_capacity(count.min(65536));
    let mut path = Vec::new();
    walk_domain(0, &mut path, &leaves, &bitmap, &labels, &mut out)?;
    if out.is_empty() { return Err("MrsDomainEmpty"); }
    Ok(out)
}

fn bit(bits: &[u64], index: usize) -> bool { bits.get(index / 64).is_some_and(|v| (v & (1u64 << (index % 64))) != 0) }
fn select_one(bits: &[u64], nth: usize) -> Option<usize> {
    let mut seen = 0;
    for (wi, word) in bits.iter().enumerate() {
        let mut v = *word;
        while v != 0 {
            let bit = v.trailing_zeros() as usize;
            if seen == nth { return Some(wi * 64 + bit); }
            seen += 1; v &= v - 1;
        }
    }
    None
}
fn walk_domain(node: usize, path: &mut Vec<u8>, leaves: &[u64], bitmap: &[u64], labels: &[u8], out: &mut Vec<String>) -> Result<(), &'static str> {
    if node >= leaves.len() * 64 || out.len() > MAX_ITEMS { return Err("MrsDomainBounds"); }
    if bit(leaves, node) {
        let mut key = path.clone();
        key.reverse();
        let s = String::from_utf8(key).map_err(|_| "MrsDomainUtf8")?;
        if s.is_empty() { return Err("MrsDomainEmptyRule"); }
        out.push(s);
    }
    // MRS domain_set_bin.go stores a LOUDS-like bitmap: one zero per edge,
    // followed by a one at the end of each node's child list. The label array
    // is indexed by zero-rank, and the child node index is zero-rank + 1.
    let end = select_one(bitmap, node).ok_or("MrsDomainBitmap")?;
    let start = if node == 0 { 0 } else { select_one(bitmap, node - 1).ok_or("MrsDomainBitmap")? + 1 };
    for pos in start..end {
        if !bit(bitmap, pos) {
            let zero_rank = bitmap.iter().take(pos / 64).map(|v| (!v).count_ones() as usize).sum::<usize>()
                + (0..(pos % 64)).filter(|b| !bit(bitmap, *b)).count();
            let ch = *labels.get(zero_rank).ok_or("MrsDomainLabels")?;
            path.push(ch);
            walk_domain(zero_rank + 1, path, leaves, bitmap, labels, out)?;
            path.pop();
        }
    }
    Ok(())
}

fn decode_ip_ranges(c: &mut Cursor<'_>, count: usize) -> Result<Vec<(IpAddr, IpAddr)>, &'static str> {
    let version = c.byte()?; if version != 1 { return Err("MrsIpVersion"); }
    let n = c.i64()?; if n < 1 || n as usize > MAX_ITEMS { return Err("MrsIpCount"); }
    let mut ranges = Vec::with_capacity(n as usize);
    for _ in 0..n {
        let start = c.take(16)?; let end = c.take(16)?;
        let a = std::net::Ipv6Addr::from(<[u8;16]>::try_from(start).map_err(|_| "MrsIpTruncated")?);
        let b = std::net::Ipv6Addr::from(<[u8;16]>::try_from(end).map_err(|_| "MrsIpTruncated")?);
        let first = IpAddr::V6(a).to_canonical(); let last = IpAddr::V6(b).to_canonical();
        if first.is_ipv4() != last.is_ipv4() || ip_cmp(first, last).is_none_or(|order| order > 0) { return Err("MrsIpRange"); }
        ranges.push((first, last));
    }
    if ranges.is_empty() { return Err("MrsIpEmpty"); }
    Ok(ranges)
}

fn ip_cmp(a: IpAddr, b: IpAddr) -> Option<i8> {
    match (a, b) {
        (IpAddr::V4(a), IpAddr::V4(b)) => Some(if a < b {-1} else if a > b {1} else {0}),
        (IpAddr::V6(a), IpAddr::V6(b)) => Some(if a < b {-1} else if a > b {1} else {0}),
        _ => None,
    }
}

struct Cursor<'a> { bytes: &'a [u8], at: usize }
impl<'a> Cursor<'a> {
    fn new(bytes: &'a [u8]) -> Self { Self { bytes, at: 0 } }
    fn take(&mut self, n: usize) -> Result<&'a [u8], &'static str> {
        let end = self.at.checked_add(n).ok_or("MrsOffsetOverflow")?;
        if end > self.bytes.len() { return Err("MrsTruncated"); }
        let out = &self.bytes[self.at..end]; self.at = end; Ok(out)
    }
    fn byte(&mut self) -> Result<u8, &'static str> { Ok(self.take(1)?[0]) }
    fn i64(&mut self) -> Result<i64, &'static str> { Ok(i64::from_be_bytes(self.take(8)?.try_into().map_err(|_| "MrsTruncated")?)) }
    fn u64_vec(&mut self) -> Result<Vec<u64>, &'static str> {
        let n = self.i64()?; if n < 1 || n as usize > MAX_ITEMS * 4 { return Err("MrsVectorBounds"); }
        let mut out = Vec::with_capacity(n as usize);
        for _ in 0..n { out.push(u64::from_be_bytes(self.take(8)?.try_into().map_err(|_| "MrsTruncated")?)); }
        Ok(out)
    }
    fn bytes_vec(&mut self) -> Result<Vec<u8>, &'static str> {
        let n = self.i64()?; if n < 1 || n as usize > MAX_ITEMS * 64 { return Err("MrsVectorBounds"); }
        Ok(self.take(n as usize)?.to_vec())
    }
    fn is_empty(&self) -> bool { self.at == self.bytes.len() }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_truncated_and_wrong_checksum_before_parsing() {
        assert_eq!(ChinaRules::parse(b"bad", Behavior::Domain, &[0;32]).unwrap_err(), "MrsCompressedSize");
        let bytes = [0u8; 32];
        assert_eq!(ChinaRules::parse(&bytes, Behavior::Domain, &[0;32]).unwrap_err(), "MrsChecksum");
    }

    fn bundled(name: &str) -> Vec<u8> {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../src/Swirl.Quick/packaging/rules").join(name);
        std::fs::read(path).expect("bundled MRS asset must be present")
    }

    #[test]
    fn parses_bundled_mrs_assets_and_matches_domains_and_ips() {
        let domain = bundled("cn-domain.mrs");
        let domain_hash: [u8;32] = hex_literal_domain_hash();
        let domains = ChinaRules::parse(&domain, Behavior::Domain, &domain_hash).expect("valid domain MRS");
        assert!(domains.matches_domain("www.baidu.com"));
        assert!(domains.matches_domain("www.qq.com"));

        let ips = bundled("cn-ip.mrs");
        let ip_hash: [u8;32] = hex_literal_ip_hash();
        let networks = ChinaRules::parse(&ips, Behavior::IpCidr, &ip_hash).expect("valid IP MRS");
        assert!(networks.matches_ip("114.114.114.114".parse().unwrap()));
        assert!(networks.matches_ip("240e:3a1:1000::1".parse().unwrap()));
        assert!(!networks.matches_ip("8.8.8.8".parse().unwrap()));
    }

    fn hex_literal_domain_hash() -> [u8;32] {
        [0xe9,0x2b,0xda,0x4f,0x0b,0x9f,0x05,0x62,0x36,0x63,0xa8,0x82,0x33,0x1a,0x32,0x0a,0xb4,0xe2,0x66,0xca,0xda,0x20,0x46,0xd3,0x82,0x8a,0x94,0x57,0x2c,0xdd,0xed,0x46]
    }
    fn hex_literal_ip_hash() -> [u8;32] {
        [0xd9,0x5b,0x3d,0x12,0x5f,0x6c,0x74,0xce,0x3c,0x15,0xe1,0x9e,0xf7,0x94,0xf1,0x42,0xde,0x91,0xe2,0x1c,0x3b,0x8f,0xb7,0x76,0x7e,0x76,0xae,0xbf,0xab,0xff,0x51,0x49]
    }
    #[test]
    fn suffix_matching_is_label_bounded() {
        let r = ChinaRules { domains: vec!["+.example.cn".into()], networks: vec![] };
        assert!(r.matches_domain("example.cn"));
        assert!(r.matches_domain("www.example.cn"));
        assert!(!r.matches_domain("notexample.cn"));
    }
    #[test]
    fn ipv4_and_ipv6_cidr_matching() {
        let r = ChinaRules { domains: vec![], networks: vec![("10.0.0.0".parse().unwrap(), "10.255.255.255".parse().unwrap()), ("2001:db8::".parse().unwrap(), "2001:db8:ffff:ffff:ffff:ffff:ffff:ffff".parse().unwrap())] };
        assert!(r.matches_ip("10.1.2.3".parse().unwrap()));
        assert!(r.matches_ip("2001:db8::1".parse().unwrap()));
        assert!(!r.matches_ip("11.1.2.3".parse().unwrap()));
    }
}
