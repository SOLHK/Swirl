//! Bounded HTTPS POST DoH (HTTP/1.1). Explicit bootstrap, verified TLS, no
//! redirects, ambient proxies, cookies, decompression or plaintext downgrade.
use crate::wire::{self, Answer, MAX_PACKET, Response};
use std::{collections::HashSet, net::SocketAddr};
use swirl_subscription::DnsHttpsServer;
use swirl_transport::{BoxStream, secure};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt, BufReader},
    net::TcpStream,
    time::{Duration, timeout},
};
type Result<T> = std::result::Result<T, &'static str>;
struct Framing {
    length: Option<usize>,
    chunked: bool,
    age: u32,
    max_age: u32,
    cache: bool,
}
fn number(value: &str) -> Result<u32> {
    if value.is_empty() || !value.bytes().all(|b| b.is_ascii_digit()) {
        return Err("DnsHttpsNumber");
    }
    value.parse().map_err(|_| "DnsHttpsNumber")
}
fn headers(data: &[u8]) -> Result<Framing> {
    let mut fields = [httparse::EMPTY_HEADER; 64];
    let mut response = httparse::Response::new(&mut fields);
    if !response
        .parse(data)
        .map_err(|_| "DnsHttpsHeader")?
        .is_complete()
        || response.version != Some(1)
    {
        return Err("DnsHttpsHeader");
    }
    if response.code != Some(200) {
        return Err("DnsHttpsStatus");
    }
    let mut result = Framing {
        length: None,
        chunked: false,
        age: 0,
        max_age: u32::MAX,
        cache: true,
    };
    let mut seen = HashSet::new();
    let mut content_type = false;
    let mut max_age_seen = false;
    for h in response.headers {
        let key = h.name.to_ascii_lowercase();
        let value = std::str::from_utf8(h.value)
            .map_err(|_| "DnsHttpsHeader")?
            .trim();
        if value.bytes().any(|b| b.is_ascii_control() && b != b'\t') {
            return Err("DnsHttpsHeader");
        }
        if [
            "content-length",
            "transfer-encoding",
            "content-type",
            "content-encoding",
            "age",
        ]
        .contains(&key.as_str())
            && !seen.insert(key.clone())
        {
            return Err("DnsHttpsDuplicateHeader");
        }
        match key.as_str() {
            "content-type" => {
                if !value.eq_ignore_ascii_case("application/dns-message") {
                    return Err("DnsHttpsContentType");
                }
                content_type = true;
            }
            "content-length" => result.length = Some(number(value)? as usize),
            "transfer-encoding" => {
                if !value.eq_ignore_ascii_case("chunked") {
                    return Err("DnsHttpsTransferEncoding");
                }
                result.chunked = true;
            }
            "content-encoding" => {
                if !value.eq_ignore_ascii_case("identity") {
                    return Err("DnsHttpsContentEncoding");
                }
            }
            "age" => result.age = number(value)?,
            "cache-control" => {
                for field in value.split(',') {
                    let (key, value) = field.trim().split_once('=').unwrap_or((field.trim(), ""));
                    if key.trim().eq_ignore_ascii_case("max-age") {
                        if max_age_seen {
                            return Err("DnsHttpsCacheControl");
                        }
                        max_age_seen = true;
                        result.max_age = number(value.trim().trim_matches('"'))?;
                    } else if key.trim().eq_ignore_ascii_case("no-store")
                        || key.trim().eq_ignore_ascii_case("no-cache")
                    {
                        result.cache = false;
                    }
                }
            }
            _ => {}
        }
    }
    if !content_type {
        return Err("DnsHttpsContentType");
    }
    if result.chunked == result.length.is_some() {
        return Err("DnsHttpsFraming");
    }
    if result
        .length
        .is_some_and(|n| !(12..=MAX_PACKET).contains(&n))
    {
        return Err("DnsHttpsSize");
    }
    Ok(result)
}
async fn line(stream: &mut BufReader<BoxStream>, limit: usize) -> Result<Vec<u8>> {
    let mut data = Vec::new();
    while data.len() < limit {
        data.push(stream.read_u8().await.map_err(|_| "DnsHttpsRead")?);
        if data.ends_with(b"\r\n") {
            return Ok(data);
        }
    }
    Err("DnsHttpsLineLimit")
}
async fn body(stream: &mut BufReader<BoxStream>, framing: &Framing) -> Result<Vec<u8>> {
    if let Some(length) = framing.length {
        let mut data = vec![0; length];
        stream
            .read_exact(&mut data)
            .await
            .map_err(|_| "DnsHttpsRead")?;
        return Ok(data);
    }
    let mut data = Vec::new();
    for _ in 0..256 {
        let size = line(stream, 128).await?;
        let text = std::str::from_utf8(&size[..size.len() - 2]).map_err(|_| "DnsHttpsChunk")?;
        if text.is_empty() || !text.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err("DnsHttpsChunk");
        }
        let length = usize::from_str_radix(text, 16).map_err(|_| "DnsHttpsChunk")?;
        if length == 0 {
            if line(stream, 2).await? != b"\r\n" {
                return Err("DnsHttpsTrailer");
            }
            if data.len() < 12 {
                return Err("DnsHttpsSize");
            }
            return Ok(data);
        }
        if length > MAX_PACKET - data.len() {
            return Err("DnsHttpsSize");
        }
        let start = data.len();
        data.resize(start + length, 0);
        stream
            .read_exact(&mut data[start..])
            .await
            .map_err(|_| "DnsHttpsRead")?;
        let mut ending = [0; 2];
        stream
            .read_exact(&mut ending)
            .await
            .map_err(|_| "DnsHttpsRead")?;
        if ending != *b"\r\n" {
            return Err("DnsHttpsChunk");
        }
    }
    Err("DnsHttpsChunkLimit")
}
async fn exchange(server: &DnsHttpsServer, host: &str, kind: u16) -> Result<Answer> {
    let tcp = TcpStream::connect(server.address)
        .await
        .map_err(|_| "DnsHttpsConnect")?;
    let mut stream = secure(tcp, &server.tls)
        .await
        .map_err(|_| "DnsHttpsVerificationOrHandshake")?;
    let mut request = wire::query(host, kind)?;
    request[..2].fill(0);
    let name = &server.tls.server_name;
    let authority = if name.contains(':') {
        format!("[{name}]")
    } else {
        name.clone()
    };
    let authority = if server.address.port() == 443 {
        authority
    } else {
        format!("{authority}:{}", server.address.port())
    };
    let header = format!(
        "POST {} HTTP/1.1\r\nHost: {}\r\nAccept: application/dns-message\r\nContent-Type: application/dns-message\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        server.path,
        authority,
        request.len()
    );
    stream
        .write_all(header.as_bytes())
        .await
        .map_err(|_| "DnsHttpsWrite")?;
    stream
        .write_all(&request)
        .await
        .map_err(|_| "DnsHttpsWrite")?;
    stream.flush().await.map_err(|_| "DnsHttpsWrite")?;
    let mut stream = BufReader::with_capacity(4096, stream);
    let mut header = Vec::new();
    while !header.ends_with(b"\r\n\r\n") {
        if header.len() >= 8192 {
            return Err("DnsHttpsHeaderLimit");
        }
        header.push(stream.read_u8().await.map_err(|_| "DnsHttpsRead")?);
    }
    let framing = headers(&header)?;
    let data = body(&mut stream, &framing).await?;
    match wire::parse(&data, &request, host, kind)? {
        Response::Truncated => Err("DnsHttpsTruncated"),
        Response::Answer(mut answer) => {
            answer.ttl = if framing.cache {
                answer.ttl.min(framing.max_age).saturating_sub(framing.age)
            } else {
                0
            };
            Ok(answer)
        }
    }
}
async fn family(server: &DnsHttpsServer, host: &str, kind: u16) -> Result<Answer> {
    let mut current = host.to_owned();
    let mut seen = HashSet::new();
    let mut ttl = 300;
    for _ in 0..8 {
        if !seen.insert(current.clone()) {
            return Err("DnsAliasLoop");
        }
        let mut answer = exchange(server, &current, kind).await?;
        ttl = ttl.min(answer.ttl);
        if let Some(alias) = answer.alias {
            current = alias;
        } else {
            answer.ttl = ttl;
            return Ok(answer);
        }
    }
    Err("DnsAliasDepth")
}
pub(super) async fn resolve(
    servers: &[DnsHttpsServer],
    host: &str,
    port: u16,
) -> Result<(Vec<SocketAddr>, u32)> {
    let mut error = "DnsNoServers";
    for server in servers {
        let result = timeout(Duration::from_millis(1400), async {
            let a = family(server, host, 1).await?;
            let aaaa = family(server, host, 28).await?;
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
        .unwrap_or(Err("DnsHttpsTimeout"));
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
    #[test]
    fn strict_http_framing_and_cache_metadata() {
        let f=headers(b"HTTP/1.1 200 OK\r\nContent-Type: application/dns-message\r\nContent-Length: 32\r\nAge: 4\r\nCache-Control: max-age=10, no-store\r\n\r\n").unwrap();
        assert_eq!(f.age, 4);
        assert_eq!(f.max_age, 10);
        assert!(!f.cache);
        for fields in [
            "Content-Length: 12\r\nContent-Length: 12",
            "Content-Length: 12\r\nTransfer-Encoding: chunked",
            "Content-Length: 99999",
            "Transfer-Encoding: gzip",
            "Content-Length: 12\r\nContent-Encoding: gzip",
            "Content-Length: 12\r\nAge: -1",
        ] {
            assert!(headers(format!("HTTP/1.1 200 OK\r\nContent-Type: application/dns-message\r\n{fields}\r\n\r\n").as_bytes()).is_err());
        }
        assert!(headers(b"HTTP/1.1 302 Found\r\nContent-Length: 12\r\nContent-Type: application/dns-message\r\n\r\n").is_err());
    }
}
