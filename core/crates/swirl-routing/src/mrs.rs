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

static BUNDLED_RULES: std::sync::OnceLock<Result<(ChinaRules, ChinaRules), &'static str>> = std::sync::OnceLock::new();

pub fn bundled_rules() -> Result<(&'static ChinaRules, &'static ChinaRules), &'static str> {
    match BUNDLED_RULES.get_or_init(load_bundled_rules) {
        Ok((domains, ips)) => Ok((domains, ips)),
        Err(error) => Err(*error),
    }
}

pub fn validate_bundled_rules() -> Result<(), &'static str> {
    bundled_rules().map(|_| ())
}

fn load_bundled_rules() -> Result<(ChinaRules, ChinaRules), &'static str> {
    let executable_dir = std::env::current_exe().ok().and_then(|p| p.parent().map(|p| p.to_path_buf()));
    let packaged = executable_dir.as_ref().map(|p| p.join("rules"));
    let source = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../src/Swirl.Quick/packaging/rules");
    let directory = packaged.filter(|p| p.join("cn-domain.mrs").is_file() && p.join("cn-ip.mrs").is_file())
        .unwrap_or(source);
    let domain_bytes = std::fs::read(directory.join("cn-domain.mrs")).map_err(|_| "ChinaDomainRulesRead")?;
    let ip_bytes = std::fs::read(directory.join("cn-ip.mrs")).map_err(|_| "ChinaIpRulesRead")?;
    let domains = ChinaRules::parse(&domain_bytes, Behavior::Domain, "e92bda4f0b9f05623663a882331a320ab4e266cada2046d3828a94572cdded46")
        .map_err(|_| "ChinaDomainRulesInvalid")?;
    let ips = ChinaRules::parse(&ip_bytes, Behavior::IpCidr, "d95b3d125f6c74ce3c15e19ef794f142de91e21c3b8fb7767e76aebfabff5149")
        .map_err(|_| "ChinaIpRulesInvalid")?;
    Ok((domains, ips))
}

#[derive(Debug, Clone)]
pub struct ChinaRules {
    domains: Vec<String>,
    networks: Vec<(IpAddr, IpAddr)>,
}

impl ChinaRules {
    pub fn parse(bytes: &[u8], expected: Behavior, expected_sha256_hex: &str) -> Result<Self, &'static str> {
        if bytes.is_empty() || bytes.len() > MAX_COMPRESSED { return Err("MrsCompressedSize"); }
        let digest = format!("{:x}", sha2::Sha256::digest(bytes));
        if digest != expected_sha256_hex { return Err("MrsChecksum"); }
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
            Behavior::IpCidr => (Vec::new(), decode_ip_ranges(&mut c)?),
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
    let nodes = bitmap.iter().map(|word| word.count_ones() as usize).sum::<usize>();
    let edges = bitmap.iter().map(|word| word.count_zeros() as usize).sum::<usize>();
    if nodes == 0 || nodes > MAX_ITEMS || leaves.len() != nodes.div_ceil(64)
        || bitmap.len() != (nodes + labels.len()).div_ceil(64)
        || edges.saturating_sub(nodes) < labels.len() {
        return Err("MrsDomainNodeCount");
    }
    let mut out = Vec::with_capacity(count.min(65536));
    let mut path = Vec::new();
    walk_domain(0, nodes, &mut path, &leaves, &bitmap, &labels, &mut out)?;
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
fn walk_domain(node: usize, node_count: usize, path: &mut Vec<u8>, leaves: &[u64], bitmap: &[u64], labels: &[u8], out: &mut Vec<String>) -> Result<(), &'static str> {
    if node >= node_count || path.len() > 253 || out.len() > MAX_ITEMS { return Err("MrsDomainBounds"); }
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
            walk_domain(zero_rank + 1, node_count, path, leaves, bitmap, labels, out)?;
            path.pop();
        }
    }
    Ok(())
}

fn decode_ip_ranges(c: &mut Cursor<'_>) -> Result<Vec<(IpAddr, IpAddr)>, &'static str> {
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

const CN_DOMAIN_SHA256: &str = "e92bda4f0b9f05623663a882331a320ab4e266cada2046d3828a94572cdded46";
const CN_IP_SHA256: &str = "d95b3d125f6c74ce3c15e19ef794f142de91e21c3b8fb7767e76aebfabff5149";
static BUNDLED: std::sync::OnceLock<Result<(ChinaRules, ChinaRules), &'static str>> = std::sync::OnceLock::new();

/// Load the repository's checksum-pinned MRS assets once. Failure is sticky and
/// explicit: routing must not silently turn an unavailable rule set into proxy-all.
pub fn bundled_rules() -> Result<(&'static ChinaRules, &'static ChinaRules), &'static str> {
    match BUNDLED.get_or_init(|| {
        let domain = include_bytes!("../../../../src/Swirl.Quick/packaging/rules/cn-domain.mrs");
        let ip = include_bytes!("../../../../src/Swirl.Quick/packaging/rules/cn-ip.mrs");
        Ok((
            ChinaRules::parse(domain, Behavior::Domain, CN_DOMAIN_SHA256)?,
            ChinaRules::parse(ip, Behavior::IpCidr, CN_IP_SHA256)?,
        ))
    }) {
        Ok((domain, ip)) => Ok((domain, ip)),
        Err(error) => Err(*error),
    }
}

pub fn validate_bundled_rules() -> Result<(), &'static str> {
    bundled_rules().map(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_truncated_and_wrong_checksum_before_parsing() {
        assert_eq!(ChinaRules::parse(b"bad", Behavior::Domain, "00").unwrap_err(), "MrsCompressedSize");
        assert_eq!(ChinaRules::parse(b"not a zstd stream but long enough", Behavior::Domain, "00").unwrap_err(), "MrsChecksum");
        let bytes = [0u8; 32];
        assert_eq!(ChinaRules::parse(&bytes, Behavior::Domain, "00").unwrap_err(), "MrsChecksum");
    }

    #[test]
    fn rejects_truncated_payload_and_unsupported_mrs_version() {
        use std::io::Write;
        let payload = b"MRS\x01\x00\x00\x00";
        let compressed = zstd::stream::encode_all(&payload[..], 1).unwrap();
        let checksum = format!("{:x}", sha2::Sha256::digest(&compressed));
        assert_eq!(ChinaRules::parse(&compressed, Behavior::Domain, &checksum).unwrap_err(), "MrsTruncated");

        let mut wrong_version = b"MRS\x01\x00".to_vec();
        wrong_version.extend_from_slice(&1i64.to_be_bytes());
        wrong_version.extend_from_slice(&0i64.to_be_bytes());
        wrong_version.push(2); // unsupported domain trie payload version
        let mut encoder = zstd::stream::Encoder::new(Vec::new(), 1).unwrap();
        encoder.write_all(&wrong_version).unwrap();
        let compressed = encoder.finish().unwrap();
        let checksum = format!("{:x}", sha2::Sha256::digest(&compressed));
        assert_eq!(ChinaRules::parse(&compressed, Behavior::Domain, &checksum).unwrap_err(), "MrsDomainVersion");
    }

    fn bundled(name: &str) -> Vec<u8> {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../src/Swirl.Quick/packaging/rules").join(name);
        std::fs::read(path).expect("bundled MRS asset must be present")
    }

    #[test]
    fn parses_bundled_mrs_assets_and_matches_domains_and_ips() {
        let domain = bundled("cn-domain.mrs");
        let domain_hash = "e92bda4f0b9f05623663a882331a320ab4e266cada2046d3828a94572cdded46";
        let domains = ChinaRules::parse(&domain, Behavior::Domain, domain_hash).expect("valid domain MRS");
        assert!(domains.matches_domain("www.baidu.com"));
        assert!(domains.matches_domain("www.qq.com"));

        let ips = bundled("cn-ip.mrs");
        let ip_hash = "d95b3d125f6c74ce3c15e19ef794f142de91e21c3b8fb7767e76aebfabff5149";
        let networks = ChinaRules::parse(&ips, Behavior::IpCidr, ip_hash).expect("valid IP MRS");
        assert!(networks.matches_ip("114.114.114.114".parse().unwrap()));
        assert!(networks.matches_ip("240e:3a1:1000::1".parse().unwrap()));
        assert!(!networks.matches_ip("8.8.8.8".parse().unwrap()));
    }

    #[test]
    fn ordered_routing_applies_cn_fallback_but_preserves_user_reject() {
        use std::net::SocketAddr;
        use swirl_subscription::Config;
        use crate::select_with_trace_and_china;
        let config = Config::parse(br#"{
          "schema":1,"listen":"127.0.0.1:0","selected":"proxy",
          "nodes":[
            {"id":"proxy","outbound":{"type":"socks5","host":"127.0.0.1","port":1080,"auth":null}},
            {"id":"direct","outbound":{"type":"direct"}},
            {"id":"reject","outbound":{"type":"reject"}}
          ],
          "rules":[
            {"matcher":{"type":"domain","value":"blocked.example.cn"},"outbound":"reject"},
            {"matcher":{"type":"match"},"outbound":"proxy"}
          ]
        }"#).unwrap();
        let domains = ChinaRules { domains: vec!["+.example.cn".into()], networks: vec![] };
        let ips = ChinaRules { domains: vec![], networks: vec![("10.0.0.0".parse().unwrap(), "10.255.255.255".parse().unwrap())] };
        let choose = |_| Err("NoAutomaticGroup");
        let source = "127.0.0.1".parse().unwrap();
        let cn = select_with_trace_and_china(&config, "www.example.cn", 443, source, None, &choose, Some(&domains), Some(&ips)).unwrap();
        assert!(matches!(cn.decision, crate::Decision::Node(n) if n.id == "direct"));
        let reject = select_with_trace_and_china(&config, "blocked.example.cn", 443, source, None, &choose, Some(&domains), Some(&ips)).unwrap();
        assert!(matches!(reject.decision, crate::Decision::Node(n) if n.id == "reject"));
        let foreign = select_with_trace_and_china(&config, "www.example.com", 443, source, Some(&["8.8.8.8:443".parse::<SocketAddr>().unwrap()]), &choose, Some(&domains), Some(&ips)).unwrap();
        assert!(matches!(foreign.decision, crate::Decision::Node(n) if n.id == "proxy"));
        let china_ip = select_with_trace_and_china(&config, "www.example.com", 443, source, Some(&["10.2.3.4:443".parse::<SocketAddr>().unwrap()]), &choose, Some(&domains), Some(&ips)).unwrap();
        assert!(matches!(china_ip.decision, crate::Decision::Node(n) if n.id == "direct"));
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
