//! Xray/V2Ray bidirectional gRPC transport, implemented independently from
//! the pinned upstream wire schema (Hunk/MultiHunk bytes field number one).
//!
//! It is a streaming RPC. The gRPC envelope and protobuf message boundaries
//! are removed before proxy-protocol bytes reach the caller.

use crate::{BoxStream, h2_stream};
use bytes::{Buf, Bytes};
use http::{Request, Uri};
use std::{
    io,
    pin::Pin,
    task::{Context, Poll, ready},
    time::Duration,
};
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};

const WRITE_CHUNK: usize = 16 * 1024;
const MAX_MESSAGE: usize = 4 * 1024 * 1024;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    #[default]
    Tun,
    TunMulti,
}

#[derive(Clone, Debug, Default, serde::Serialize, serde::Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub authority: String,
    pub service_name: String,
    pub mode: Mode,
    pub headers: Vec<(String, String)>,
}

impl Config {
    /// Reject malformed or unsupported transport fields before DNS/TCP/TLS.
    pub fn validate(&self) -> Result<(), &'static str> {
        request(self, false).map(|_| ())
    }
}

fn escape_segment(value: &str) -> String {
    let mut escaped = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric()
            || matches!(
                byte,
                b'-' | b'_' | b'.' | b'~' | b'$' | b'&' | b'+' | b':' | b'=' | b'@'
            )
        {
            escaped.push(byte as char);
        } else {
            escaped.push('%');
            escaped.push(b"0123456789ABCDEF"[(byte >> 4) as usize] as char);
            escaped.push(b"0123456789ABCDEF"[(byte & 15) as usize] as char);
        }
    }
    escaped
}

fn service_path(config: &Config) -> Result<String, &'static str> {
    if config.service_name.len() > 4096 {
        return Err("GrpcServiceNameTooLong");
    }
    if !config.service_name.starts_with('/') {
        return Ok(format!(
            "/{}/{}",
            escape_segment(&config.service_name),
            match config.mode {
                Mode::Tun => "Tun",
                Mode::TunMulti => "TunMulti",
            }
        ));
    }
    let (service, methods) = config
        .service_name
        .rsplit_once('/')
        .ok_or("GrpcServiceName")?;
    if service.is_empty() || methods.is_empty() {
        return Err("GrpcServiceName");
    }
    let (tun, multi) = methods
        .split_once('|')
        .map_or((methods, methods), |(tun, multi)| (tun, multi));
    let method = match config.mode {
        Mode::Tun => tun,
        Mode::TunMulti => multi,
    };
    if method.is_empty() || method.contains('|') {
        return Err("GrpcServiceName");
    }
    let service = service
        .split('/')
        .map(escape_segment)
        .collect::<Vec<_>>()
        .join("/");
    Ok(format!("{service}/{}", escape_segment(method)))
}

fn request(config: &Config, tls: bool) -> Result<Request<()>, &'static str> {
    let uri = Uri::builder()
        .scheme(if tls { "https" } else { "http" })
        .authority(h2_stream::authority(&config.authority)?)
        .path_and_query(service_path(config)?)
        .build()
        .map_err(|_| "GrpcServiceName")?;
    let mut request = Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/grpc")
        .header("te", "trailers")
        .header("grpc-accept-encoding", "identity")
        .body(())
        .map_err(|_| "GrpcRequest")?;
    h2_stream::append_headers(
        &mut request,
        &config.headers,
        &[
            "content-type",
            "grpc-encoding",
            "grpc-accept-encoding",
            "grpc-status",
        ],
    )?;
    Ok(request)
}

pub async fn connect(
    stream: BoxStream,
    config: &Config,
    tls: bool,
) -> Result<BoxStream, &'static str> {
    let request = request(config, tls)?;
    let stream = h2_stream::connect(stream, request, h2_stream::ResponseKind::Grpc).await?;
    Ok(Box::new(GrpcStream::new(stream, config.mode)))
}

pub async fn connect_with_timeout(
    stream: BoxStream,
    config: &Config,
    tls: bool,
    header_timeout: Duration,
) -> Result<BoxStream, &'static str> {
    let request = request(config, tls)?;
    let stream = h2_stream::connect_with_timeout(
        stream,
        request,
        h2_stream::ResponseKind::Grpc,
        header_timeout,
    )
    .await?;
    Ok(Box::new(GrpcStream::new(stream, config.mode)))
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn varint(bytes: &[u8], offset: &mut usize) -> io::Result<u64> {
    let mut value = 0u64;
    for shift in (0..=63).step_by(7) {
        let byte = *bytes
            .get(*offset)
            .ok_or_else(|| invalid("GrpcProtobufTruncated"))?;
        *offset += 1;
        if shift == 63 && byte > 1 {
            return Err(invalid("GrpcProtobufVarint"));
        }
        value |= u64::from(byte & 0x7f) << shift;
        if byte & 0x80 == 0 {
            return Ok(value);
        }
    }
    Err(invalid("GrpcProtobufVarint"))
}

fn advance(bytes: &[u8], offset: &mut usize, length: usize) -> io::Result<()> {
    *offset = offset
        .checked_add(length)
        .filter(|end| *end <= bytes.len())
        .ok_or_else(|| invalid("GrpcProtobufTruncated"))?;
    Ok(())
}

fn decode_message(bytes: &[u8], mode: Mode) -> io::Result<Bytes> {
    let mut offset = 0usize;
    let mut output = Vec::new();
    while offset < bytes.len() {
        let tag = varint(bytes, &mut offset)?;
        let field = tag >> 3;
        if field == 0 || field > 0x1fff_ffff {
            return Err(invalid("GrpcProtobufField"));
        }
        match tag & 7 {
            0 => {
                if field == 1 {
                    return Err(invalid("GrpcProtobufWireType"));
                }
                varint(bytes, &mut offset)?;
            }
            1 | 5 => {
                if field == 1 {
                    return Err(invalid("GrpcProtobufWireType"));
                }
                advance(bytes, &mut offset, if tag & 7 == 1 { 8 } else { 4 })?;
            }
            2 => {
                let length = usize::try_from(varint(bytes, &mut offset)?)
                    .map_err(|_| invalid("GrpcProtobufLength"))?;
                let start = offset;
                advance(bytes, &mut offset, length)?;
                if field == 1 {
                    if mode == Mode::Tun {
                        // A singular protobuf bytes field uses the last value.
                        output.clear();
                    }
                    output.extend_from_slice(&bytes[start..offset]);
                }
            }
            // Groups are absent from this proto3 schema; reject rather than
            // recursively consuming an unbounded adversarial nesting tree.
            _ => return Err(invalid("GrpcProtobufWireType")),
        }
    }
    Ok(Bytes::from(output))
}

fn encode_message(bytes: &[u8]) -> Bytes {
    let mut body = Vec::with_capacity(bytes.len() + 10);
    body.extend_from_slice(&[0; 5]);
    body.push(0x0a);
    let mut length = bytes.len();
    while length >= 0x80 {
        body.push((length as u8 & 0x7f) | 0x80);
        length >>= 7;
    }
    body.push(length as u8);
    body.extend_from_slice(bytes);
    let length = (body.len() - 5) as u32;
    body[1..5].copy_from_slice(&length.to_be_bytes());
    Bytes::from(body)
}

struct GrpcStream {
    inner: BoxStream,
    mode: Mode,
    prefix: [u8; 5],
    prefix_read: usize,
    body: Vec<u8>,
    body_read: usize,
    payload: Bytes,
    pending_write: Bytes,
    write_failure: Option<io::ErrorKind>,
    send_done: bool,
    eof: bool,
}

impl GrpcStream {
    fn new(inner: BoxStream, mode: Mode) -> Self {
        Self {
            inner,
            mode,
            prefix: [0; 5],
            prefix_read: 0,
            body: Vec::new(),
            body_read: 0,
            payload: Bytes::new(),
            pending_write: Bytes::new(),
            write_failure: None,
            send_done: false,
            eof: false,
        }
    }

    fn poll_drain(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if let Some(kind) = self.write_failure {
            return Poll::Ready(Err(io::Error::new(kind, "GrpcUploadFailed")));
        }
        while !self.pending_write.is_empty() {
            let n = match ready!(Pin::new(&mut self.inner).poll_write(cx, &self.pending_write)) {
                Ok(n) => n,
                Err(error) => {
                    self.write_failure = Some(error.kind());
                    self.pending_write = Bytes::new();
                    return Poll::Ready(Err(error));
                }
            };
            if n == 0 {
                self.write_failure = Some(io::ErrorKind::WriteZero);
                self.pending_write = Bytes::new();
                return Poll::Ready(Err(io::ErrorKind::WriteZero.into()));
            }
            self.pending_write.advance(n);
        }
        Poll::Ready(Ok(()))
    }
}

impl AsyncRead for GrpcStream {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        output: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if output.remaining() == 0 || this.eof {
            return Poll::Ready(Ok(()));
        }
        // A caller may write then read without an explicit flush. Attempt to
        // drain accepted bytes, but do not block the reverse direction when
        // upload flow control is stalled.
        // Upload errors remain visible to write/flush/shutdown. Do not discard
        // a valid early response because its server stopped accepting upload;
        // response framing and terminal status are still validated below.
        let _ = this.poll_drain(cx);
        for _ in 0..32 {
            if !this.payload.is_empty() {
                let n = this.payload.len().min(output.remaining());
                output.put_slice(&this.payload[..n]);
                this.payload.advance(n);
                return Poll::Ready(Ok(()));
            }
            while this.prefix_read < 5 {
                let mut buffer = ReadBuf::new(&mut this.prefix[this.prefix_read..]);
                ready!(Pin::new(&mut this.inner).poll_read(cx, &mut buffer))?;
                let n = buffer.filled().len();
                if n == 0 {
                    if this.prefix_read == 0 {
                        this.eof = true;
                        return Poll::Ready(Ok(()));
                    }
                    return Poll::Ready(Err(io::Error::new(
                        io::ErrorKind::UnexpectedEof,
                        "GrpcEnvelopeTruncated",
                    )));
                }
                this.prefix_read += n;
            }
            if this.body.is_empty() && this.body_read == 0 {
                if this.prefix[0] != 0 {
                    return Poll::Ready(Err(invalid("GrpcCompressionUnsupported")));
                }
                let length = u32::from_be_bytes(this.prefix[1..5].try_into().unwrap()) as usize;
                if length > MAX_MESSAGE {
                    return Poll::Ready(Err(invalid("GrpcMessageTooLarge")));
                }
                this.body.resize(length, 0);
            }
            while this.body_read < this.body.len() {
                let mut buffer = ReadBuf::new(&mut this.body[this.body_read..]);
                ready!(Pin::new(&mut this.inner).poll_read(cx, &mut buffer))?;
                let n = buffer.filled().len();
                if n == 0 {
                    return Poll::Ready(Err(io::Error::new(
                        io::ErrorKind::UnexpectedEof,
                        "GrpcMessageTruncated",
                    )));
                }
                this.body_read += n;
            }
            this.payload = decode_message(&this.body, this.mode)?;
            this.body.clear();
            this.body_read = 0;
            this.prefix_read = 0;
        }
        cx.waker().wake_by_ref();
        Poll::Pending
    }
}

impl AsyncWrite for GrpcStream {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        if this.send_done {
            return Poll::Ready(Err(io::ErrorKind::BrokenPipe.into()));
        }
        ready!(this.poll_drain(cx))?;
        let n = bytes.len().min(WRITE_CHUNK);
        if n == 0 {
            return Poll::Ready(Ok(0));
        }
        this.pending_write = encode_message(&bytes[..n]);
        if let Poll::Ready(Err(error)) = this.poll_drain(cx) {
            return Poll::Ready(Err(error));
        }
        // At most one 16 KiB encoded message is held by this adapter.
        Poll::Ready(Ok(n))
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        ready!(this.poll_drain(cx))?;
        Pin::new(&mut this.inner).poll_flush(cx)
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        ready!(this.poll_drain(cx))?;
        ready!(Pin::new(&mut this.inner).poll_shutdown(cx))?;
        this.send_done = true;
        Poll::Ready(Ok(()))
    }
}

#[cfg(test)]
#[path = "grpc_tests.rs"]
mod tests;
