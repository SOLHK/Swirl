//! Swirl-owned bounded DNS stub wire protocol, RFC 1035. No external resolver
//! engine. Connected UDP sockets validate peer; TC responses retry over TCP.
use ring::rand::{SecureRandom, SystemRandom};
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr};
use swirl_subscription::DnsQueryFamily;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpStream, UdpSocket},
    time::{Duration, timeout},
};
type Result<T> = std::result::Result<T, &'static str>;
pub(super) const MAX_PACKET: usize = 16384;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Negative {
    NameError,
    NoData,
}

#[derive(Clone, Debug)]
pub(super) enum Outcome {
    Addresses(Vec<IpAddr>),
    Negative(Negative),
    // A local, short-lived resolution failure, never an NXDOMAIN/NODATA fact.
    Failure(&'static str),
}
impl Outcome {
    pub(super) fn for_port(&self, port: u16) -> Result<Vec<SocketAddr>> {
        match self {
            Self::Addresses(addresses) => Ok(addresses
                .iter()
                .map(|ip| SocketAddr::new(*ip, port))
                .collect()),
            Self::Negative(Negative::NameError) => Err("DnsNameError"),
            Self::Negative(Negative::NoData) => Err("DnsEmpty"),
            Self::Failure(error) => Err(error),
        }
    }
}
pub(super) struct Resolution {
    pub(super) outcome: Outcome,
    pub(super) ttl: u32,
}

fn word(data: &[u8], at: usize) -> Result<u16> {
    let bytes = data.get(at..at + 2).ok_or("DnsTruncated")?;
    Ok(u16::from_be_bytes([bytes[0], bytes[1]]))
}
fn dword(data: &[u8], at: usize) -> Result<u32> {
    Ok((u32::from(word(data, at)?) << 16) | u32::from(word(data, at + 2)?))
}
fn covers(zone: &str, host: &str) -> bool {
    zone.is_empty()
        || host == zone
        || host
            .strip_suffix(zone)
            .is_some_and(|prefix| prefix.ends_with('.'))
}
fn name_labels<'a>(data: &'a [u8], cursor: &mut usize) -> Result<Vec<&'a [u8]>> {
    let mut at = *cursor;
    let mut end = None;
    let mut labels = Vec::new();
    let mut length = 0;
    for _ in 0..128 {
        let tag = *data.get(at).ok_or("DnsTruncated")?;
        if tag & 0xc0 == 0xc0 {
            let to = (word(data, at)? & 0x3fff) as usize;
            // Compression refers to an earlier occurrence, never forward/self.
            if to >= at {
                return Err("DnsCompression");
            }
            end.get_or_insert(at + 2);
            at = to;
            continue;
        }
        if tag & 0xc0 != 0 {
            return Err("DnsLabel");
        }
        at += 1;
        if tag == 0 {
            *cursor = end.unwrap_or(at);
            return Ok(labels);
        }
        let bytes = data.get(at..at + tag as usize).ok_or("DnsTruncated")?;
        length += bytes.len() + 1;
        if length > 254 {
            return Err("DnsNameLength");
        }
        labels.push(bytes);
        at += bytes.len();
    }
    Err("DnsCompressionDepth")
}
fn name(data: &[u8], cursor: &mut usize) -> Result<String> {
    let mut labels = Vec::new();
    for bytes in name_labels(data, cursor)? {
        if !bytes
            .iter()
            .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(b))
        {
            return Err("DnsLabel");
        }
        labels.push(
            std::str::from_utf8(bytes)
                .map_err(|_| "DnsLabel")?
                .to_ascii_lowercase(),
        );
    }
    Ok(labels.join("."))
}
pub(super) fn query(host: &str, kind: u16) -> Result<Vec<u8>> {
    let mut id = [0; 2];
    SystemRandom::new().fill(&mut id).map_err(|_| "DnsRandom")?;
    let mut data = vec![id[0], id[1], 1, 0, 0, 1, 0, 0, 0, 0, 0, 0];
    for label in host.split('.') {
        if label.is_empty() || label.len() > 63 {
            return Err("DnsQueryName");
        }
        data.push(label.len() as u8);
        data.extend(label.as_bytes());
    }
    data.push(0);
    data.extend(kind.to_be_bytes());
    data.extend([0, 1]);
    Ok(data)
}
pub(super) struct Answer {
    pub(super) addresses: Vec<IpAddr>,
    pub(super) alias: Option<String>,
    pub(super) ttl: u32,
    canonical: String,
    negative: Option<Negative>,
    // A denial without an applicable, fully decoded authority SOA has no TTL.
    negative_cacheable: bool,
}
pub(super) enum Response {
    Truncated,
    Answer(Answer),
}
pub(super) fn parse(data: &[u8], request: &[u8], host: &str, kind: u16) -> Result<Response> {
    if data.len() < 12 || data.len() > MAX_PACKET || word(data, 0)? != word(request, 0)? {
        return Err("DnsIdentity");
    }
    let flags = word(data, 2)?;
    if flags & 0x8000 == 0 || flags & 0x7800 != 0 || flags & 0x0040 != 0 || word(data, 4)? != 1 {
        return Err("DnsHeader");
    }
    let mut cursor = 12;
    if !name(data, &mut cursor)?.eq_ignore_ascii_case(host)
        || word(data, cursor)? != kind
        || word(data, cursor + 2)? != 1
    {
        return Err("DnsQuestion");
    }
    cursor += 4;
    if flags & 0x0200 != 0 {
        return Ok(Response::Truncated);
    }
    match flags & 15 {
        0 | 3 => {}
        _ => return Err("DnsServerError"),
    }
    let answers = word(data, 6)? as usize;
    let authorities = word(data, 8)? as usize;
    let total = answers + authorities + word(data, 10)? as usize;
    if total > 128 {
        return Err("DnsRecordLimit");
    }
    let mut aliases = Vec::new();
    let mut addresses = Vec::new();
    let mut negative_ttls = Vec::new();
    let mut referral = false;
    for index in 0..total {
        let owner = name(data, &mut cursor)?;
        let record = word(data, cursor)?;
        let class = word(data, cursor + 2)?;
        let ttl = dword(data, cursor + 4)?;
        // RFC 2181 section 8 treats a received TTL with its high bit set as zero.
        let ttl = if ttl > i32::MAX as u32 { 0 } else { ttl };
        let size = word(data, cursor + 8)? as usize;
        cursor += 10;
        let end = cursor
            .checked_add(size)
            .filter(|n| *n <= data.len())
            .ok_or("DnsTruncated")?;
        if (answers..answers + authorities).contains(&index) && class == 1 {
            if record == 6 {
                let mut offset = cursor;
                // SOA mailbox labels may contain dots and other non-hostname
                // bytes (RFC 1035 section 8); only DNS structure is relevant.
                name_labels(data, &mut offset)?;
                if offset > end {
                    return Err("DnsSoaLength");
                }
                name_labels(data, &mut offset)?;
                if offset.checked_add(20) != Some(end) {
                    return Err("DnsSoaLength");
                }
                // RFC 2308: both the RR TTL and SOA.MINIMUM limit a denial.
                negative_ttls.push((owner.clone(), ttl.min(dword(data, offset + 16)?)));
            } else if record == 2 {
                referral = true;
            }
        }
        if index < answers && class == 1 {
            match record {
                5 => {
                    let mut offset = cursor;
                    let alias = name(data, &mut offset)?;
                    if offset != end || !swirl_subscription::valid_host(&alias) {
                        return Err("DnsAlias");
                    }
                    aliases.push((owner, alias, ttl));
                }
                1 if size == 4 => addresses.push((
                    owner,
                    IpAddr::V4(Ipv4Addr::new(
                        data[cursor],
                        data[cursor + 1],
                        data[cursor + 2],
                        data[cursor + 3],
                    )),
                    ttl,
                )),
                28 if size == 16 => {
                    let octets: [u8; 16] = data[cursor..end]
                        .try_into()
                        .map_err(|_| "DnsAddressLength")?;
                    addresses.push((owner, IpAddr::V6(Ipv6Addr::from(octets)), ttl));
                }
                1 | 28 => return Err("DnsAddressLength"),
                _ => {}
            }
        }
        cursor = end;
    }
    if cursor != data.len() {
        return Err("DnsTrailingData");
    }
    let mut current = host.to_ascii_lowercase();
    let mut seen = std::collections::HashSet::new();
    let mut ttl = 300;
    for _ in 0..9 {
        if !seen.insert(current.clone()) {
            return Err("DnsAliasLoop");
        }
        let matching: Vec<_> = aliases
            .iter()
            .filter(|(owner, _, _)| owner == &current)
            .collect();
        if matching.len() > 1 {
            return Err("DnsAliasConflict");
        }
        if let Some((_, alias, age)) = matching.first() {
            if addresses.iter().any(|(owner, _, _)| owner == &current) {
                return Err("DnsAliasConflict");
            }
            ttl = ttl.min(*age);
            current = alias.clone();
            continue;
        }
        let mut result = Vec::new();
        for (owner, ip, age) in &addresses {
            if owner == &current && ((kind == 1 && ip.is_ipv4()) || (kind == 28 && ip.is_ipv6())) {
                ttl = ttl.min(*age);
                if result.len() < 16 && !result.contains(ip) {
                    result.push(*ip);
                }
            }
        }
        let soa_ttl = negative_ttls
            .iter()
            .filter(|(zone, _)| covers(zone, &current))
            .map(|(_, age)| *age)
            .min();
        let name_error = flags & 15 == 3;
        if name_error && addresses.iter().any(|(owner, _, _)| owner == &current) {
            return Err("DnsInconsistentAnswer");
        }
        let alias = if result.is_empty()
            && !name_error
            && soa_ttl.is_none()
            && !current.eq_ignore_ascii_case(host)
        {
            Some(current.clone())
        } else {
            None
        };
        let negative = if name_error {
            Some(Negative::NameError)
        } else if result.is_empty() && alias.is_none() {
            if soa_ttl.is_none() && referral {
                return Err("DnsReferral");
            }
            Some(Negative::NoData)
        } else {
            None
        };
        if negative.is_some() {
            ttl = ttl.min(soa_ttl.unwrap_or(300));
        }
        return Ok(Response::Answer(Answer {
            addresses: result,
            alias,
            ttl,
            canonical: current,
            negative,
            negative_cacheable: negative.is_some() && soa_ttl.is_some(),
        }));
    }
    Err("DnsAliasDepth")
}
async fn exchange(server: SocketAddr, host: &str, kind: u16) -> Result<Answer> {
    let request = query(host, kind)?;
    let socket = UdpSocket::bind(if server.is_ipv4() {
        "0.0.0.0:0"
    } else {
        "[::]:0"
    })
    .await
    .map_err(|_| "DnsSocket")?;
    socket.connect(server).await.map_err(|_| "DnsConnect")?;
    socket.send(&request).await.map_err(|_| "DnsSend")?;
    let mut data = vec![0; MAX_PACKET + 1];
    let n = socket.recv(&mut data).await.map_err(|_| "DnsReceive")?;
    data.truncate(n);
    match parse(&data, &request, host, kind)? {
        Response::Answer(answer) => Ok(answer),
        Response::Truncated => {
            let mut stream = TcpStream::connect(server)
                .await
                .map_err(|_| "DnsTcpConnect")?;
            stream
                .write_all(&(request.len() as u16).to_be_bytes())
                .await
                .map_err(|_| "DnsTcpWrite")?;
            stream
                .write_all(&request)
                .await
                .map_err(|_| "DnsTcpWrite")?;
            let size = stream.read_u16().await.map_err(|_| "DnsTcpRead")? as usize;
            if !(12..=MAX_PACKET).contains(&size) {
                return Err("DnsTcpSize");
            }
            let mut data = vec![0; size];
            stream
                .read_exact(&mut data)
                .await
                .map_err(|_| "DnsTcpRead")?;
            match parse(&data, &request, host, kind)? {
                Response::Answer(a) => Ok(a),
                Response::Truncated => Err("DnsTcpTruncated"),
            }
        }
    }
}
async fn family(server: SocketAddr, host: &str, kind: u16) -> Result<Answer> {
    let mut host = host.to_owned();
    let mut ttl = 300;
    let mut seen = std::collections::HashSet::new();
    for _ in 0..8 {
        if !seen.insert(host.clone()) {
            return Err("DnsAliasLoop");
        }
        let mut answer = exchange(server, &host, kind).await?;
        ttl = ttl.min(answer.ttl);
        if let Some(alias) = answer.alias {
            host = alias;
        } else {
            answer.ttl = ttl;
            return Ok(answer);
        }
    }
    Err("DnsAliasDepth")
}
/// A completed single-family lookup needs only that family's SOA proof. Never
/// invent a response for a family that policy prohibited us from requesting.
pub(super) fn single(answer: Answer) -> Result<Resolution> {
    if answer.negative == Some(Negative::NameError) {
        return Ok(Resolution {
            outcome: Outcome::Negative(Negative::NameError),
            ttl: if answer.negative_cacheable {
                answer.ttl
            } else {
                0
            },
        });
    }
    if answer.addresses.is_empty() {
        if !answer.negative_cacheable {
            return Err("DnsEmpty");
        }
        return Ok(Resolution {
            outcome: Outcome::Negative(Negative::NoData),
            ttl: answer.ttl,
        });
    }
    Ok(Resolution {
        outcome: Outcome::Addresses(answer.addresses),
        ttl: answer.ttl,
    })
}
pub(super) fn combine(a: Result<Answer>, aaaa: Result<Answer>) -> Result<Resolution> {
    // Preserve a received NXDOMAIN as terminal if the other family failed,
    // but never turn that partial result into a cached denial.
    if matches!((&a, &aaaa), (Ok(answer), Err(_)) | (Err(_), Ok(answer))
        if answer.negative == Some(Negative::NameError))
    {
        return Ok(Resolution {
            outcome: Outcome::Negative(Negative::NameError),
            ttl: 0,
        });
    }
    let a = a?;
    let aaaa = aaaa?;
    let ttl = a.ttl.min(aaaa.ttl);
    let negative_ttl =
        if a.negative_cacheable && aaaa.negative_cacheable && a.canonical == aaaa.canonical {
            ttl
        } else {
            0
        };
    if a.negative == Some(Negative::NameError) || aaaa.negative == Some(Negative::NameError) {
        if a.negative != aaaa.negative || a.canonical != aaaa.canonical {
            return Err("DnsInconsistentAnswer");
        }
        return Ok(Resolution {
            outcome: Outcome::Negative(Negative::NameError),
            ttl: negative_ttl,
        });
    }
    let addresses: Vec<_> = a
        .addresses
        .into_iter()
        .chain(aaaa.addresses)
        .take(16)
        .collect();
    if addresses.is_empty() {
        if !a.negative_cacheable || !aaaa.negative_cacheable {
            // Unproven empty answers keep the existing explicit-server retry.
            // An actual SOA with TTL zero is still a valid terminal NODATA.
            return Err("DnsEmpty");
        }
        return Ok(Resolution {
            outcome: Outcome::Negative(Negative::NoData),
            ttl: negative_ttl,
        });
    }
    // A positive cache entry is the known usable IP set. An empty family without
    // SOA does not establish a cached NODATA fact for that family.
    Ok(Resolution {
        outcome: Outcome::Addresses(addresses),
        ttl,
    })
}
pub(super) async fn resolve(
    servers: &[SocketAddr],
    host: &str,
    query_family: DnsQueryFamily,
) -> Result<Resolution> {
    let mut error = "DnsNoServers";
    for server in servers {
        let result = timeout(Duration::from_millis(900), async {
            match query_family {
                DnsQueryFamily::Ipv4Only => single(family(*server, host, 1).await?),
                DnsQueryFamily::Dual => {
                    let (a, aaaa) =
                        tokio::join!(family(*server, host, 1), family(*server, host, 28));
                    combine(a, aaaa)
                }
            }
        })
        .await
        .unwrap_or(Err("DnsTimeout"));
        match result {
            Ok(answer) => return Ok(answer),
            Err(e) => error = e,
        }
    }
    Err(error)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn response(request: &[u8], records: &[(u16, Vec<u8>)]) -> Vec<u8> {
        let mut data = request.to_vec();
        data[2] = 0x81;
        data[3] = 0x80;
        data[6..8].copy_from_slice(&(records.len() as u16).to_be_bytes());
        for (kind, body) in records {
            data.extend([0xc0, 12]);
            data.extend(kind.to_be_bytes());
            data.extend([0, 1, 0, 0, 0, 7]);
            data.extend((body.len() as u16).to_be_bytes());
            data.extend(body);
        }
        data
    }
    #[test]
    fn validates_identity_question_and_all_truncations() {
        let request = query("a.test", 1).unwrap();
        let data = response(&request, &[(1, vec![127, 0, 0, 1])]);
        let Response::Answer(answer) = parse(&data, &request, "a.test", 1).unwrap() else {
            panic!()
        };
        assert_eq!(answer.ttl, 7);
        assert_eq!(answer.addresses, ["127.0.0.1".parse::<IpAddr>().unwrap()]);
        for length in 0..data.len() {
            assert!(parse(&data[..length], &request, "a.test", 1).is_err());
        }
        for offset in [0, 13, request.len() - 1] {
            let mut bad = data.clone();
            bad[offset] ^= 1;
            assert!(parse(&bad, &request, "a.test", 1).is_err());
        }
        let mut tc = data.clone();
        tc[2] |= 2;
        assert!(matches!(
            parse(&tc, &request, "a.test", 1),
            Ok(Response::Truncated)
        ));
    }
    #[test]
    fn rejects_alias_loops_compression_cycles_and_foreign_answers() {
        let request = query("a.test", 1).unwrap();
        let data = response(&request, &[(5, vec![0xc0, 12])]);
        assert!(parse(&data, &request, "a.test", 1).is_err());
        let mut data = response(&request, &[(1, vec![127, 0, 0, 1])]);
        let at = request.len();
        data[at..at + 2].copy_from_slice(&(0xc000 | at as u16).to_be_bytes());
        assert!(parse(&data, &request, "a.test", 1).is_err());
        let mut data = response(&request, &[(1, vec![127, 0, 0, 1])]);
        data.splice(at..at + 2, [1, b'b', 4, b't', b'e', b's', b't', 0]);
        let Response::Answer(answer) = parse(&data, &request, "a.test", 1).unwrap() else {
            panic!()
        };
        assert!(answer.addresses.is_empty());
        let short = response(&request, &[(1, vec![127, 0, 0])]);
        assert!(parse(&short, &request, "a.test", 1).is_err());
    }
    #[test]
    fn ipv6_and_cname_only_responses_preserve_ttl() {
        let request = query("a.test", 28).unwrap();
        let data = response(&request, &[(28, Ipv6Addr::LOCALHOST.octets().to_vec())]);
        let Response::Answer(answer) = parse(&data, &request, "a.test", 28).unwrap() else {
            panic!()
        };
        assert_eq!(answer.addresses, [IpAddr::V6(Ipv6Addr::LOCALHOST)]);
        let data = response(
            &request,
            &[(5, vec![1, b'b', 4, b't', b'e', b's', b't', 0])],
        );
        let Response::Answer(answer) = parse(&data, &request, "a.test", 28).unwrap() else {
            panic!()
        };
        assert_eq!(answer.alias.as_deref(), Some("b.test"));
        assert_eq!(answer.ttl, 7);
    }

    fn encoded_name(value: &str) -> Vec<u8> {
        let mut data = Vec::new();
        for label in value.split('.').filter(|label| !label.is_empty()) {
            data.push(label.len() as u8);
            data.extend(label.as_bytes());
        }
        data.push(0);
        data
    }

    fn authority(data: &mut Vec<u8>, zone: &str, ttl: u32, minimum: u32) {
        data[8..10].copy_from_slice(&1_u16.to_be_bytes());
        let mut soa = encoded_name("ns.test");
        soa.extend(encoded_name("hostmaster.test"));
        for number in [1_u32, 60, 60, 3600, minimum] {
            soa.extend(number.to_be_bytes());
        }
        data.extend(encoded_name(zone));
        data.extend([0, 6, 0, 1]);
        data.extend(ttl.to_be_bytes());
        data.extend((soa.len() as u16).to_be_bytes());
        data.extend(soa);
    }

    fn denial(host: &str, kind: u16, code: u8, soa: Option<(&str, u32, u32)>) -> Answer {
        let request = query(host, kind).unwrap();
        let mut data = response(&request, &[]);
        data[3] |= code;
        if let Some((zone, ttl, minimum)) = soa {
            authority(&mut data, zone, ttl, minimum);
        }
        let Response::Answer(answer) = parse(&data, &request, host, kind).unwrap() else {
            panic!("unexpected truncation");
        };
        answer
    }

    #[test]
    fn negative_responses_require_complete_matching_messages_and_applicable_soa() {
        for code in [0, 3] {
            let request = query("missing.test", 1).unwrap();
            let mut data = response(&request, &[]);
            data[3] |= code;
            authority(&mut data, "test", 40, 9);
            let Response::Answer(answer) = parse(&data, &request, "missing.test", 1).unwrap()
            else {
                panic!("unexpected truncation");
            };
            assert!(answer.negative_cacheable);
            assert_eq!(answer.ttl, 9);
            assert_eq!(
                answer.negative,
                Some(if code == 3 {
                    Negative::NameError
                } else {
                    Negative::NoData
                })
            );
            for length in 0..data.len() {
                assert!(parse(&data[..length], &request, "missing.test", 1).is_err());
            }
            let mut extra = data.clone();
            extra.push(0);
            assert!(matches!(
                parse(&extra, &request, "missing.test", 1),
                Err("DnsTrailingData")
            ));
            let mut tc = data.clone();
            tc[2] |= 2;
            assert!(matches!(
                parse(&tc, &request, "missing.test", 1),
                Ok(Response::Truncated)
            ));
            for offset in [0, 13, request.len() - 1] {
                let mut bad = data.clone();
                bad[offset] ^= 1;
                assert!(parse(&bad, &request, "missing.test", 1).is_err());
            }
            assert!(!denial("missing.test", 1, code, None).negative_cacheable);
            assert!(!denial("missing.test", 1, code, Some(("ing.test", 40, 9))).negative_cacheable);
            assert_eq!(denial("missing.test", 1, code, Some(("test", 2, 9))).ttl, 2);
            assert_eq!(
                denial("missing.test", 1, code, Some(("test", 40, 0))).ttl,
                0
            );
            assert_eq!(denial("missing.test", 1, code, Some(("test", 0, 9))).ttl, 0);
            assert_eq!(
                denial("missing.test", 1, code, Some(("test", u32::MAX, 9))).ttl,
                0
            );
            assert_eq!(
                denial("missing.test", 1, code, Some(("", 900, 900))).ttl,
                300
            );
        }
    }

    #[test]
    fn soa_rdata_names_must_fit_the_record_and_use_valid_compression() {
        let request = query("missing.test", 1).unwrap();
        let mut data = response(&request, &[]);
        data[3] |= 3;
        let start = data.len();
        // SOA's two names may legitimately refer to an earlier question name.
        data[8..10].copy_from_slice(&1_u16.to_be_bytes());
        data.extend([0xc0, 12, 0, 6, 0, 1, 0, 0, 0, 20, 0, 24, 0xc0, 12, 0xc0, 12]);
        for number in [1_u32, 60, 60, 3600, 4] {
            data.extend(number.to_be_bytes());
        }
        let Response::Answer(answer) = parse(&data, &request, "missing.test", 1).unwrap() else {
            panic!("unexpected truncation");
        };
        assert!(answer.negative_cacheable);
        assert_eq!(answer.ttl, 4);
        for offset in [start + 12, start + 14] {
            let mut bad = data.clone();
            bad[offset..offset + 2].copy_from_slice(&(0xc000 | offset as u16).to_be_bytes());
            assert!(matches!(
                parse(&bad, &request, "missing.test", 1),
                Err("DnsCompression")
            ));
        }
        let mut long = data.clone();
        long[start + 11] += 1;
        long.push(0);
        assert!(matches!(
            parse(&long, &request, "missing.test", 1),
            Err("DnsSoaLength")
        ));
        let mut short = data.clone();
        short[start + 11] -= 1;
        short.pop();
        assert!(matches!(
            parse(&short, &request, "missing.test", 1),
            Err("DnsSoaLength")
        ));
        // A same-looking SOA in Additional cannot authorize a negative cache.
        data[8..10].copy_from_slice(&0_u16.to_be_bytes());
        data[10..12].copy_from_slice(&1_u16.to_be_bytes());
        let Response::Answer(answer) = parse(&data, &request, "missing.test", 1).unwrap() else {
            panic!("unexpected truncation");
        };
        assert!(!answer.negative_cacheable);
    }

    #[test]
    fn soa_mailbox_local_part_is_a_dns_label_not_a_hostname() {
        let request = query("missing.test", 1).unwrap();
        let mut data = response(&request, &[]);
        data[3] |= 3;
        data[8..10].copy_from_slice(&1_u16.to_be_bytes());
        let mut soa = vec![0xc0, 12];
        // One mailbox label containing a literal dot, as in RFC 1035 section 8.
        soa.extend(b"\x0bhost.master\x04test\0");
        for number in [1_u32, 60, 60, 3600, 1] {
            soa.extend(number.to_be_bytes());
        }
        data.extend([0xc0, 12, 0, 6, 0, 1, 0, 0, 0, 30]);
        data.extend((soa.len() as u16).to_be_bytes());
        data.extend(soa);
        let Response::Answer(answer) = parse(&data, &request, "missing.test", 1).unwrap() else {
            panic!("unexpected truncation");
        };
        assert!(answer.negative_cacheable);
        assert_eq!(answer.ttl, 1);
        // The same dot inside a query label must not be flattened into a name.
        let mut cursor = 0;
        assert_eq!(
            name(b"\x0bhost.master\x04test\0", &mut cursor),
            Err("DnsLabel")
        );
    }

    #[test]
    fn cname_denials_belong_to_the_terminal_name_and_obey_alias_ttl() {
        for code in [0, 3] {
            let request = query("alias.test", 1).unwrap();
            let mut data = response(&request, &[(5, encoded_name("gone.other"))]);
            data[3] |= code;
            authority(&mut data, "other", 90, 20);
            let Response::Answer(answer) = parse(&data, &request, "alias.test", 1).unwrap() else {
                panic!("unexpected truncation");
            };
            assert_eq!(answer.canonical, "gone.other");
            assert!(answer.alias.is_none());
            assert!(answer.negative_cacheable);
            assert_eq!(answer.ttl, 7);
            let mut wrong = response(&request, &[(5, encoded_name("gone.other"))]);
            wrong[3] |= code;
            authority(&mut wrong, "test", 90, 20);
            let Response::Answer(answer) = parse(&wrong, &request, "alias.test", 1).unwrap() else {
                panic!("unexpected truncation");
            };
            assert!(!answer.negative_cacheable);
            assert_eq!(
                answer.alias.as_deref(),
                if code == 0 { Some("gone.other") } else { None }
            );
        }
    }

    fn positive() -> Answer {
        let request = query("mixed.test", 1).unwrap();
        let data = response(&request, &[(1, vec![127, 0, 0, 1])]);
        let Response::Answer(answer) = parse(&data, &request, "mixed.test", 1).unwrap() else {
            panic!("unexpected truncation");
        };
        answer
    }

    #[test]
    fn family_merge_never_confuses_nodata_name_error_or_transport_failure() {
        let answer = combine(
            Ok(positive()),
            Ok(denial("mixed.test", 28, 0, Some(("test", 5, 3)))),
        )
        .unwrap();
        assert!(matches!(answer.outcome, Outcome::Addresses(_)));
        assert_eq!(answer.ttl, 3);
        for reverse in [false, true] {
            let nx = Ok(denial("mixed.test", 28, 3, Some(("test", 5, 3))));
            let yes = Ok(positive());
            let (a, aaaa) = if reverse { (nx, yes) } else { (yes, nx) };
            assert!(matches!(combine(a, aaaa), Err("DnsInconsistentAnswer")));
        }
        for code in [0, 3] {
            let answer = combine(
                Ok(denial("mixed.test", 1, code, Some(("test", 30, 20)))),
                Ok(denial("mixed.test", 28, code, Some(("test", 10, 5)))),
            )
            .unwrap();
            assert_eq!(answer.ttl, 5);
            assert!(matches!(answer.outcome, Outcome::Negative(_)));
            let answer = combine(
                Ok(denial("mixed.test", 1, code, None)),
                Ok(denial("mixed.test", 28, code, Some(("test", 10, 5)))),
            );
            if code == 0 {
                assert!(matches!(answer, Err("DnsEmpty")));
            } else {
                assert_eq!(answer.unwrap().ttl, 0);
            }
        }
        let partial = combine(
            Err("DnsServerError"),
            Ok(denial("mixed.test", 28, 3, Some(("test", 30, 20)))),
        )
        .unwrap();
        assert_eq!(partial.ttl, 0);
        assert!(matches!(
            partial.outcome,
            Outcome::Negative(Negative::NameError)
        ));
        assert!(matches!(
            combine(Ok(positive()), Err("DnsServerError")),
            Err("DnsServerError")
        ));
        assert!(matches!(
            combine(
                Ok(denial("mixed.test", 1, 0, Some(("test", 30, 20)))),
                Ok(denial("mixed.test", 28, 3, Some(("test", 30, 20)))),
            ),
            Err("DnsInconsistentAnswer")
        ));
    }
}
