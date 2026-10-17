//! Swirl-owned bounded DNS stub wire protocol, RFC 1035. No external resolver
//! engine. Connected UDP sockets validate peer; TC responses retry over TCP.
use ring::rand::{SecureRandom, SystemRandom};
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpStream, UdpSocket},
    time::{Duration, timeout},
};
type Result<T> = std::result::Result<T, &'static str>;
const MAX_PACKET: usize = 16384;

fn word(data: &[u8], at: usize) -> Result<u16> {
    let bytes = data.get(at..at + 2).ok_or("DnsTruncated")?;
    Ok(u16::from_be_bytes([bytes[0], bytes[1]]))
}
fn name(data: &[u8], cursor: &mut usize) -> Result<String> {
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
            return Ok(labels.join("."));
        }
        let bytes = data.get(at..at + tag as usize).ok_or("DnsTruncated")?;
        if !bytes
            .iter()
            .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(b))
        {
            return Err("DnsLabel");
        }
        length += bytes.len() + 1;
        if length > 254 {
            return Err("DnsNameLength");
        }
        labels.push(
            std::str::from_utf8(bytes)
                .map_err(|_| "DnsLabel")?
                .to_ascii_lowercase(),
        );
        at += bytes.len();
    }
    Err("DnsCompressionDepth")
}
fn query(host: &str, kind: u16) -> Result<Vec<u8>> {
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
struct Answer {
    addresses: Vec<IpAddr>,
    alias: Option<String>,
    ttl: u32,
}
enum Response {
    Truncated,
    Answer(Answer),
}
fn parse(data: &[u8], request: &[u8], host: &str, kind: u16) -> Result<Response> {
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
        0 => {}
        3 => return Err("DnsNameError"),
        _ => return Err("DnsServerError"),
    }
    let answers = word(data, 6)? as usize;
    let total = answers + word(data, 8)? as usize + word(data, 10)? as usize;
    if total > 128 {
        return Err("DnsRecordLimit");
    }
    let mut aliases = Vec::new();
    let mut addresses = Vec::new();
    for index in 0..total {
        let owner = name(data, &mut cursor)?;
        let record = word(data, cursor)?;
        let class = word(data, cursor + 2)?;
        let ttl = ((word(data, cursor + 4)? as u32) << 16) | word(data, cursor + 6)? as u32;
        let size = word(data, cursor + 8)? as usize;
        cursor += 10;
        let end = cursor
            .checked_add(size)
            .filter(|n| *n <= data.len())
            .ok_or("DnsTruncated")?;
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
        let alias = if result.is_empty() && !current.eq_ignore_ascii_case(host) {
            Some(current)
        } else {
            None
        };
        return Ok(Response::Answer(Answer {
            addresses: result,
            alias,
            ttl,
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
pub async fn resolve(
    servers: &[SocketAddr],
    host: &str,
    port: u16,
) -> Result<(Vec<SocketAddr>, u32)> {
    let mut error = "DnsNoServers";
    for server in servers {
        let result = timeout(Duration::from_millis(900), async {
            let (a, aaaa) = tokio::join!(family(*server, host, 1), family(*server, host, 28));
            if matches!(&a, Err("DnsNameError")) || matches!(&aaaa, Err("DnsNameError")) {
                return Err("DnsNameError");
            }
            let a = a?;
            let aaaa = aaaa?;
            let ttl = a.ttl.min(aaaa.ttl);
            let addresses: Vec<_> = a
                .addresses
                .into_iter()
                .chain(aaaa.addresses)
                .take(16)
                .map(|ip| SocketAddr::new(ip, port))
                .collect();
            if addresses.is_empty() {
                return Err("DnsEmpty");
            }
            Ok((addresses, ttl))
        })
        .await
        .unwrap_or(Err("DnsTimeout"));
        match result {
            Ok(answer) => return Ok(answer),
            Err("DnsNameError") => return Err("DnsNameError"),
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
}
