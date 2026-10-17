//! Native RFC 8484 DoH POST over authenticated HTTP/1.1. No redirects, OS
//! bootstrap, cookies, plaintext fallback, or external proxy engine. A fresh
//! connection per DNS exchange deliberately avoids ambiguous keep-alive reuse.
use crate::wire::{self, Answer, MAX_PACKET, Resolution, Response};
use std::collections::HashSet;
use swirl_subscription::DnsTlsServer;
use swirl_transport::{BoxStream, secure};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
};
type Result<T> = std::result::Result<T, &'static str>;
const MAX_HEADER: usize = 8192;

#[derive(Default)]
struct Metadata {
    length: Option<usize>,
    chunked: bool,
    age: u32,
    max_age: Option<u32>,
    no_cache: bool,
}
fn token(name: &str) -> bool {
    !name.is_empty()
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b))
}
fn field(line: &str) -> Result<(&str, &str)> {
    let (name, value) = line.split_once(':').ok_or("DnsHttpsHeader")?;
    if !token(name) || value.bytes().any(|b| b < 32 && b != b'\t' || b == 127) {
        return Err("DnsHttpsHeader");
    }
    Ok((name, value.trim_matches([' ', '\t'])))
}
fn decimal(value: &str) -> Result<u32> {
    if value.is_empty() || !value.bytes().all(|b| b.is_ascii_digit()) {
        return Err("DnsHttpsNumber");
    }
    value.parse().map_err(|_| "DnsHttpsNumber")
}
fn metadata(data: &[u8]) -> Result<Metadata> {
    let text = std::str::from_utf8(data).map_err(|_| "DnsHttpsHeader")?;
    let mut lines = text.split("\r\n");
    let mut status = lines.next().ok_or("DnsHttpsStatus")?.splitn(3, ' ');
    if !matches!(status.next(), Some("HTTP/1.1" | "HTTP/1.0"))
        || status.next() != Some("200")
        || status
            .next()
            .is_none_or(|s| s.bytes().any(|b| b < 32 || b == 127))
    {
        return Err("DnsHttpsStatus");
    }
    let mut result = Metadata::default();
    let mut seen = HashSet::new();
    let mut content_type = false;
    for (index, line) in lines.filter(|s| !s.is_empty()).enumerate() {
        if index >= 64 {
            return Err("DnsHttpsHeaderLimit");
        }
        let (key, value) = field(line)?;
        let key = key.to_ascii_lowercase();
        if matches!(
            key.as_str(),
            "content-length" | "transfer-encoding" | "content-type" | "content-encoding" | "age"
        ) && !seen.insert(key.clone())
        {
            return Err("DnsHttpsDuplicateHeader");
        }
        match key.as_str() {
            "content-length" => {
                let size = decimal(value)? as usize;
                if !(12..=MAX_PACKET).contains(&size) {
                    return Err("DnsHttpsBodyLimit");
                }
                result.length = Some(size);
            }
            "transfer-encoding" => {
                if !value.eq_ignore_ascii_case("chunked") {
                    return Err("DnsHttpsTransferEncoding");
                }
                result.chunked = true;
            }
            "content-type" => {
                if !value
                    .split(';')
                    .next()
                    .unwrap_or("")
                    .trim()
                    .eq_ignore_ascii_case("application/dns-message")
                {
                    return Err("DnsHttpsContentType");
                }
                content_type = true;
            }
            "content-encoding" if !value.eq_ignore_ascii_case("identity") => {
                return Err("DnsHttpsContentEncoding");
            }
            "age" => result.age = decimal(value)?,
            "cache-control" => {
                for directive in value.split(',').map(str::trim) {
                    let (name, value) = directive.split_once('=').unwrap_or((directive, ""));
                    match name.trim().to_ascii_lowercase().as_str() {
                        "no-store" | "no-cache" => result.no_cache = true,
                        "max-age" => {
                            // Ambiguous cache hints must not create a fresh DNS entry.
                            let seconds = decimal(value.trim().trim_matches('"')).unwrap_or(0);
                            result.max_age = Some(result.max_age.unwrap_or(u32::MAX).min(seconds));
                        }
                        _ => {}
                    }
                }
            }
            _ => {}
        }
    }
    if !content_type {
        return Err("DnsHttpsContentType");
    }
    if result.chunked && result.length.is_some() {
        return Err("DnsHttpsAmbiguousFraming");
    }
    Ok(result)
}
async fn line<R: AsyncRead + Unpin>(stream: &mut R, limit: usize) -> Result<Vec<u8>> {
    let mut data = Vec::new();
    while data.len() < limit {
        data.push(stream.read_u8().await.map_err(|_| "DnsHttpsRead")?);
        if data.ends_with(b"\r\n") {
            data.truncate(data.len() - 2);
            return Ok(data);
        }
    }
    Err("DnsHttpsHeaderLimit")
}
async fn response<R: AsyncRead + Unpin>(stream: &mut R) -> Result<(Vec<u8>, Metadata)> {
    let mut head = Vec::new();
    loop {
        if head.len() >= MAX_HEADER {
            return Err("DnsHttpsHeaderLimit");
        }
        let next = line(stream, MAX_HEADER - head.len()).await?;
        head.extend(&next);
        head.extend(b"\r\n");
        if next.is_empty() {
            break;
        }
    }
    let meta = metadata(&head)?;
    let mut body = Vec::new();
    if let Some(size) = meta.length {
        body.resize(size, 0);
        stream
            .read_exact(&mut body)
            .await
            .map_err(|_| "DnsHttpsRead")?;
    } else if meta.chunked {
        let mut complete = false;
        for _ in 0..256 {
            let raw = line(stream, 256).await?;
            let text = std::str::from_utf8(&raw).map_err(|_| "DnsHttpsChunk")?;
            if text.bytes().any(|b| !(32..=126).contains(&b)) {
                return Err("DnsHttpsChunk");
            }
            let size = text.split(';').next().unwrap_or("");
            if size.is_empty() || size.len() > 8 || !size.bytes().all(|b| b.is_ascii_hexdigit()) {
                return Err("DnsHttpsChunk");
            }
            let size = usize::from_str_radix(size, 16).map_err(|_| "DnsHttpsChunk")?;
            if size == 0 {
                let mut trailer_bytes = 0;
                for _ in 0..33 {
                    let trailer = line(stream, MAX_HEADER - trailer_bytes).await?;
                    trailer_bytes += trailer.len() + 2;
                    if trailer_bytes > MAX_HEADER {
                        return Err("DnsHttpsHeaderLimit");
                    }
                    if trailer.is_empty() {
                        complete = true;
                        break;
                    }
                    let (name, _) =
                        field(std::str::from_utf8(&trailer).map_err(|_| "DnsHttpsHeader")?)?;
                    if matches!(
                        name.to_ascii_lowercase().as_str(),
                        "content-length"
                            | "transfer-encoding"
                            | "content-type"
                            | "content-encoding"
                            | "cache-control"
                            | "age"
                    ) {
                        return Err("DnsHttpsTrailer");
                    }
                }
                break;
            }
            if size > MAX_PACKET - body.len() {
                return Err("DnsHttpsBodyLimit");
            }
            let start = body.len();
            body.resize(start + size, 0);
            stream
                .read_exact(&mut body[start..])
                .await
                .map_err(|_| "DnsHttpsRead")?;
            let mut end = [0; 2];
            stream
                .read_exact(&mut end)
                .await
                .map_err(|_| "DnsHttpsRead")?;
            if end != *b"\r\n" {
                return Err("DnsHttpsChunk");
            }
        }
        if !complete {
            return Err("DnsHttpsChunkLimit");
        }
    } else {
        stream
            .take((MAX_PACKET + 1) as u64)
            .read_to_end(&mut body)
            .await
            .map_err(|_| "DnsHttpsRead")?;
    }
    if !(12..=MAX_PACKET).contains(&body.len()) {
        return Err("DnsHttpsBodyLimit");
    }
    Ok((body, meta))
}
async fn exchange(server: &DnsTlsServer, host: &str, kind: u16) -> Result<Answer> {
    let mut request = wire::query(host, kind)?;
    // RFC 8484 recommends zero ID; HTTP associates the request and response.
    request[0] = 0;
    request[1] = 0;
    let path = server.https_path.as_deref().ok_or("DnsHttpsPath")?;
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
    let tcp = TcpStream::connect(server.address)
        .await
        .map_err(|_| "DnsHttpsConnect")?;
    let mut stream: BoxStream = secure(tcp, &server.tls)
        .await
        .map_err(|_| "DnsHttpsVerificationOrHandshake")?;
    let header = format!(
        "POST {path} HTTP/1.1\r\nHost: {authority}\r\nAccept: application/dns-message\r\nContent-Type: application/dns-message\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
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
    let (data, meta) = response(&mut stream).await?;
    let mut answer = match wire::parse(&data, &request, host, kind)? {
        Response::Answer(answer) => answer,
        Response::Truncated => return Err("DnsHttpsTruncated"),
    };
    answer.ttl = if meta.no_cache {
        0
    } else {
        answer
            .ttl
            .min(meta.max_age.unwrap_or(u32::MAX))
            .saturating_sub(meta.age)
    };
    Ok(answer)
}
async fn family(server: &DnsTlsServer, host: &str, kind: u16) -> Result<Answer> {
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
pub(super) async fn lookup(server: &DnsTlsServer, host: &str) -> Result<Resolution> {
    let a = family(server, host, 1).await?;
    let aaaa = family(server, host, 28).await;
    wire::combine(Ok(a), aaaa)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn strict_http_metadata_and_cache_hints() {
        let valid = b"HTTP/1.1 200 OK\r\nContent-Type: application/dns-message\r\nContent-Length: 12\r\nAge: 8\r\nCache-Control: max-age=20, no-store\r\n\r\n";
        let meta = metadata(valid).unwrap();
        assert_eq!(meta.length, Some(12));
        assert_eq!(meta.age, 8);
        assert_eq!(meta.max_age, Some(20));
        assert!(meta.no_cache);
        for suffix in [
            "Content-Length: 12\r\nContent-Length: 12",
            "Content-Length: 12\r\nTransfer-Encoding: chunked",
            "Content-Length: +12",
            "Transfer-Encoding: gzip, chunked",
            "Content-Encoding: gzip",
            " folded: value",
            "Age: -1",
        ] {
            let head = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/dns-message\r\n{suffix}\r\n\r\n"
            );
            assert!(metadata(head.as_bytes()).is_err(), "accepted {suffix}");
        }
    }
    #[tokio::test]
    async fn chunked_body_is_exact_and_bounded() {
        let mut raw = &b"HTTP/1.1 200 OK\r\nContent-Type: application/dns-message\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n7;fixture=1\r\n world!\r\n0\r\nX-Fixture: ok\r\n\r\n"[..];
        assert_eq!(response(&mut raw).await.unwrap().0, b"hello world!");
        for body in [
            "ffff\r\n",
            "-1\r\n",
            "0\r\nAge: 0\r\n\r\n",
            "c\r\ntoo short",
        ] {
            let text = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/dns-message\r\nTransfer-Encoding: chunked\r\n\r\n{body}"
            );
            assert!(response(&mut text.as_bytes()).await.is_err());
        }
    }
}
