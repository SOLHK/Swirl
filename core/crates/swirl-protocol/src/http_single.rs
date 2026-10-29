//! One ordinary HTTP exchange per inbound socket. A CONNECT or a verified
//! WebSocket upgrade remains an opaque stream; ordinary HTTP cannot smuggle a later
//! logical request through the configuration snapshot of its first request.
use crate::Result;
use std::sync::{Arc, atomic::Ordering};
use swirl_transport::{BoxStream, Counters};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt},
    net::TcpStream,
    time::{Duration, timeout},
};

const HEADER_LIMIT: usize = 16 * 1024;
#[derive(Clone, Copy)]
enum Body {
    Empty,
    Length(u64),
    Chunked,
    Close,
}

fn upgrade_key(request: &httparse::Request<'_, '_>) -> Result<Option<String>> {
    use base64::{Engine, engine::general_purpose::STANDARD};
    if !request
        .headers
        .iter()
        .any(|header| header.name.eq_ignore_ascii_case("upgrade"))
    {
        return Ok(None);
    }
    let mut key = None;
    let mut version = false;
    for header in request.headers.iter() {
        if header.name.eq_ignore_ascii_case("sec-websocket-key") {
            if key.is_some()
                || STANDARD
                    .decode(header.value)
                    .map_err(|_| "HttpUpgradeKey")?
                    .len()
                    != 16
            {
                return Err("HttpUpgradeKey");
            }
            key = Some(
                std::str::from_utf8(header.value)
                    .map_err(|_| "HttpUpgradeKey")?
                    .to_owned(),
            );
        }
        if header.name.eq_ignore_ascii_case("sec-websocket-version") {
            if version || header.value != b"13" {
                return Err("HttpUpgradeVersion");
            }
            version = true;
        }
    }
    if request.method != Some("GET") || !version {
        return Err("HttpUpgradeRequest");
    }
    key.ok_or("HttpUpgradeKey").map(Some)
}
fn checked_upgrade(response: &httparse::Response<'_, '_>, key: &str) -> Result<()> {
    use base64::{Engine, engine::general_purpose::STANDARD};
    let expected = STANDARD.encode(ring::digest::digest(
        &ring::digest::SHA1_FOR_LEGACY_USE_ONLY,
        format!("{key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11").as_bytes(),
    ));
    let mut accepted = false;
    let mut upgrade = false;
    let mut connection = false;
    for header in response.headers.iter() {
        if header.name.eq_ignore_ascii_case("sec-websocket-accept") {
            if accepted || header.value != expected.as_bytes() {
                return Err("HttpUpgradeAccept");
            }
            accepted = true;
        }
        if header.name.eq_ignore_ascii_case("upgrade") {
            if upgrade || !header.value.eq_ignore_ascii_case(b"websocket") {
                return Err("HttpUpgradeProtocol");
            }
            upgrade = true;
        }
        if header.name.eq_ignore_ascii_case("connection") {
            connection |= header
                .value
                .split(|b| *b == b',')
                .any(|part| part.trim_ascii().eq_ignore_ascii_case(b"upgrade"));
        }
    }
    if response.version != Some(1) || !accepted || !upgrade || !connection {
        return Err("HttpUpgradeResponse");
    }
    match framing(response.headers, true)? {
        Body::Close | Body::Length(0) => Ok(()),
        _ => Err("HttpUpgradeBody"),
    }
}

fn framing(headers: &[httparse::Header<'_>], response: bool) -> Result<Body> {
    let mut length = None;
    let mut chunked = false;
    for header in headers {
        if header.name.eq_ignore_ascii_case("content-length") {
            if length.is_some()
                || header.value.is_empty()
                || !header.value.iter().all(u8::is_ascii_digit)
            {
                return Err("HttpContentLength");
            }
            length = Some(
                std::str::from_utf8(header.value)
                    .map_err(|_| "HttpContentLength")?
                    .parse::<u64>()
                    .map_err(|_| "HttpContentLength")?,
            );
        } else if header.name.eq_ignore_ascii_case("transfer-encoding") {
            if chunked || !header.value.eq_ignore_ascii_case(b"chunked") {
                return Err("HttpTransferEncoding");
            }
            chunked = true;
        }
        if header
            .value
            .iter()
            .any(|byte| byte.is_ascii_control() && *byte != b'\t')
        {
            return Err("HttpHeaderControl");
        }
    }
    if chunked && length.is_some() {
        return Err("HttpAmbiguousFraming");
    }
    Ok(if chunked {
        Body::Chunked
    } else if let Some(length) = length {
        Body::Length(length)
    } else if response {
        Body::Close
    } else {
        Body::Empty
    })
}

async fn write<W: AsyncWrite + Unpin>(
    writer: &mut W,
    data: &[u8],
    limit: Duration,
    counters: &Counters,
    total: &Counters,
    upload: bool,
) -> Result<()> {
    timeout(limit, async {
        writer.write_all(data).await?;
        writer.flush().await
    })
    .await
    .map_err(|_| "HttpWriteTimeout")?
    .map_err(|_| "HttpWrite")?;
    let (counter, aggregate) = if upload {
        (&counters.upload, &total.upload)
    } else {
        (&counters.download, &total.download)
    };
    counter.fetch_add(data.len() as u64, Ordering::Relaxed);
    aggregate.fetch_add(data.len() as u64, Ordering::Relaxed);
    Ok(())
}
async fn read<R: AsyncRead + Unpin>(
    reader: &mut R,
    buffer: &mut [u8],
    limit: Duration,
) -> Result<usize> {
    timeout(limit, reader.read(buffer))
        .await
        .map_err(|_| "HttpReadTimeout")?
        .map_err(|_| "HttpRead")
}
async fn line<R: AsyncRead + Unpin>(
    reader: &mut R,
    limit: Duration,
    maximum: usize,
) -> Result<Vec<u8>> {
    let mut result = Vec::new();
    loop {
        if result.len() >= maximum {
            return Err("HttpLineTooLarge");
        }
        let mut byte = [0];
        if read(reader, &mut byte, limit).await? == 0 {
            return Err("HttpBodyTruncated");
        }
        result.push(byte[0]);
        if result.ends_with(b"\r\n") {
            return Ok(result);
        }
    }
}
struct CopyContext<'a> {
    limit: Duration,
    counters: &'a Counters,
    total: &'a Counters,
    upload: bool,
}
impl CopyContext<'_> {
    async fn exact<R: AsyncRead + Unpin, W: AsyncWrite + Unpin>(
        &self,
        reader: &mut R,
        writer: &mut W,
        mut remaining: u64,
    ) -> Result<()> {
        let mut buffer = vec![0; 16 * 1024];
        while remaining != 0 {
            let capacity = remaining.min(buffer.len() as u64) as usize;
            let size = read(reader, &mut buffer[..capacity], self.limit).await?;
            if size == 0 {
                return Err("HttpBodyTruncated");
            }
            write(
                writer,
                &buffer[..size],
                self.limit,
                self.counters,
                self.total,
                self.upload,
            )
            .await?;
            remaining -= size as u64;
        }
        Ok(())
    }
    async fn body<R: AsyncRead + Unpin, W: AsyncWrite + Unpin>(
        &self,
        reader: &mut R,
        writer: &mut W,
        body: Body,
    ) -> Result<()> {
        match body {
            Body::Empty => Ok(()),
            Body::Length(size) => self.exact(reader, writer, size).await,
            Body::Close => {
                let mut buffer = vec![0; 16 * 1024];
                loop {
                    let size = read(reader, &mut buffer, self.limit).await?;
                    if size == 0 {
                        return Ok(());
                    }
                    write(
                        writer,
                        &buffer[..size],
                        self.limit,
                        self.counters,
                        self.total,
                        self.upload,
                    )
                    .await?;
                }
            }
            Body::Chunked => {
                loop {
                    let chunk = line(reader, self.limit, 8192).await?;
                    let value = &chunk[..chunk.len() - 2];
                    let end = value
                        .iter()
                        .position(|byte| *byte == b';')
                        .unwrap_or(value.len());
                    if end == 0
                        || end > 16
                        || !value[..end].iter().all(u8::is_ascii_hexdigit)
                        || value[end..]
                            .iter()
                            .any(|byte| !byte.is_ascii_graphic() && *byte != b' ')
                    {
                        return Err("HttpChunkSize");
                    }
                    let size = u64::from_str_radix(
                        std::str::from_utf8(&value[..end]).map_err(|_| "HttpChunkSize")?,
                        16,
                    )
                    .map_err(|_| "HttpChunkSize")?;
                    write(
                        writer,
                        &chunk,
                        self.limit,
                        self.counters,
                        self.total,
                        self.upload,
                    )
                    .await?;
                    if size == 0 {
                        let mut total = 0;
                        let mut count = 0;
                        loop {
                            let trailer = line(reader, self.limit, HEADER_LIMIT).await?;
                            total += trailer.len();
                            count += 1;
                            if total > HEADER_LIMIT || count > 64 {
                                return Err("HttpTrailerTooLarge");
                            }
                            if trailer != b"\r\n" {
                                let mut parsed = [httparse::EMPTY_HEADER; 1];
                                // httparse requires a terminating empty line for a header block.
                                let mut bytes = trailer.clone();
                                bytes.extend_from_slice(b"\r\n");
                                let httparse::Status::Complete((_, headers)) =
                                    httparse::parse_headers(&bytes, &mut parsed)
                                        .map_err(|_| "HttpTrailerSyntax")?
                                else {
                                    return Err("HttpTrailerSyntax");
                                };
                                if headers.len() != 1
                                    || [
                                        "content-length",
                                        "transfer-encoding",
                                        "host",
                                        "connection",
                                        "upgrade",
                                        "trailer",
                                    ]
                                    .iter()
                                    .any(|name| headers[0].name.eq_ignore_ascii_case(name))
                                {
                                    return Err("HttpTrailerFraming");
                                }
                            }
                            write(
                                writer,
                                &trailer,
                                self.limit,
                                self.counters,
                                self.total,
                                self.upload,
                            )
                            .await?;
                            if trailer == b"\r\n" {
                                return Ok(());
                            }
                        }
                    }
                    self.exact(reader, writer, size).await?;
                    let ending = line(reader, self.limit, 2).await?;
                    if ending != b"\r\n" {
                        return Err("HttpChunkEnding");
                    }
                    write(
                        writer,
                        &ending,
                        self.limit,
                        self.counters,
                        self.total,
                        self.upload,
                    )
                    .await?;
                }
            }
        }
    }
}

async fn response<R: AsyncRead + Unpin, W: AsyncWrite + Unpin>(
    reader: &mut R,
    writer: &mut W,
    head: bool,
    context: &CopyContext<'_>,
    upgrade: Option<&str>,
) -> Result<bool> {
    for _ in 0..8 {
        let mut bytes = Vec::new();
        while !bytes.ends_with(b"\r\n\r\n") {
            bytes.extend(line(reader, context.limit, HEADER_LIMIT).await?);
            if bytes.len() > HEADER_LIMIT {
                return Err("HttpHeaderTooLarge");
            }
        }
        let mut fields = [httparse::EMPTY_HEADER; 64];
        let mut response = httparse::Response::new(&mut fields);
        if !response
            .parse(&bytes)
            .map_err(|_| "HttpResponseSyntax")?
            .is_complete()
        {
            return Err("HttpResponseSyntax");
        }
        let code = response.code.ok_or("HttpResponseSyntax")?;
        if code == 101 {
            checked_upgrade(&response, upgrade.ok_or("HttpUnexpectedUpgrade")?)?;
            write(
                writer,
                &bytes,
                context.limit,
                context.counters,
                context.total,
                false,
            )
            .await?;
            return Ok(true);
        }
        let body = framing(response.headers, true)?;
        let mut header = format!(
            "HTTP/1.{} {code} {}\r\n",
            response.version.ok_or("HttpResponseSyntax")?,
            response.reason.unwrap_or("")
        )
        .into_bytes();
        for field in response.headers {
            if ["connection", "proxy-connection", "keep-alive"]
                .iter()
                .any(|name| field.name.eq_ignore_ascii_case(name))
            {
                continue;
            }
            header.extend_from_slice(field.name.as_bytes());
            header.extend_from_slice(b": ");
            header.extend_from_slice(field.value);
            header.extend_from_slice(b"\r\n");
        }
        header.extend_from_slice(b"Connection: close\r\n\r\n");
        write(
            writer,
            &header,
            context.limit,
            context.counters,
            context.total,
            false,
        )
        .await?;
        if (100..200).contains(&code) {
            continue;
        }
        context
            .body(
                reader,
                writer,
                if head || code == 204 || code == 304 {
                    Body::Empty
                } else {
                    body
                },
            )
            .await?;
        return Ok(false);
    }
    Err("HttpInformationalLimit")
}

pub async fn forward(
    inbound: &mut TcpStream,
    upstream: &mut BoxStream,
    initial: &[u8],
    limit: Duration,
    counters: Arc<Counters>,
    total: Arc<Counters>,
) -> Result<()> {
    let boundary = initial
        .windows(4)
        .position(|part| part == b"\r\n\r\n")
        .ok_or("HttpRequestSyntax")?
        + 4;
    let mut fields = [httparse::EMPTY_HEADER; 64];
    let mut request = httparse::Request::new(&mut fields);
    if !request
        .parse(&initial[..boundary])
        .map_err(|_| "HttpRequestSyntax")?
        .is_complete()
    {
        return Err("HttpRequestSyntax");
    }
    let head = request.method == Some("HEAD");
    let body = framing(request.headers, false)?;
    if let Some(key) = upgrade_key(&request)? {
        if !matches!(body, Body::Empty | Body::Length(0)) {
            return Err("HttpUpgradeBody");
        }
        write(
            upstream,
            &initial[..boundary],
            limit,
            &counters,
            &total,
            true,
        )
        .await?;
        let context = CopyContext {
            limit,
            counters: &counters,
            total: &total,
            upload: false,
        };
        if Box::pin(response(upstream, inbound, false, &context, Some(&key))).await? {
            if !initial[boundary..].is_empty() {
                write(
                    upstream,
                    &initial[boundary..],
                    limit,
                    &counters,
                    &total,
                    true,
                )
                .await?;
            }
            swirl_transport::relay(inbound, upstream, counters, total)
                .await
                .map_err(|_| "HttpUpgradeRelay")?;
        }
        return Ok(());
    }
    let (read_client, mut write_client) = inbound.split();
    let (mut read_origin, mut write_origin) = tokio::io::split(upstream);
    let mut request_body = initial[boundary..].chain(read_client);
    let upload_context = CopyContext {
        limit,
        counters: &counters,
        total: &total,
        upload: true,
    };
    let download_context = CopyContext {
        upload: false,
        ..upload_context
    };
    let upload = async {
        write(
            &mut write_origin,
            &initial[..boundary],
            limit,
            &counters,
            &total,
            true,
        )
        .await?;
        upload_context
            .body(&mut request_body, &mut write_origin, body)
            .await
    };
    let download = async {
        response(
            &mut read_origin,
            &mut write_client,
            head,
            &download_context,
            None,
        )
        .await
        .map(|_| ())
    };
    tokio::pin!(upload, download);
    tokio::select! {
        result = &mut upload => { result?; download.await },
        result = &mut download => result,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn complete_http_frame_reaches_a_buffered_transport_before_waiting_for_reply() {
        let (transport, mut peer) = tokio::io::duplex(1024);
        let mut buffered = tokio::io::BufWriter::new(transport);
        let counters = Counters::default();
        let total = Counters::default();
        write(
            &mut buffered,
            b"GET / HTTP/1.1\r\nHost: fixture.invalid\r\n\r\n",
            Duration::from_secs(1),
            &counters,
            &total,
            true,
        )
        .await
        .unwrap();
        let mut received = [0; 43];
        let size = b"GET / HTTP/1.1\r\nHost: fixture.invalid\r\n\r\n".len();
        timeout(
            Duration::from_secs(1),
            peer.read_exact(&mut received[..size]),
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(
            &received[..size],
            b"GET / HTTP/1.1\r\nHost: fixture.invalid\r\n\r\n"
        );
    }
}
