//! Native Snell v4 AEAD framing. Surge documents v5 servers as accepting v4 clients.
//! Wire facts cross-checked against winmin/snell-client ada74659 (MIT metadata)
//! and independent peers; no external proxy process is used by this module.
use crate::{Result, Target};
use argon2::{Algorithm, Argon2, Params, Version};
use ring::{
    aead,
    rand::{SecureRandom, SystemRandom},
};
use std::{
    collections::{HashSet, VecDeque},
    io,
    pin::Pin,
    sync::{Mutex, OnceLock},
    task::{Context, Poll, ready},
    time::Duration,
};
use swirl_transport::BoxStream;
use tokio::io::{AsyncRead, AsyncWrite, AsyncWriteExt, ReadBuf, ReadHalf, WriteHalf};
use tokio::time::{Sleep, sleep};
use zeroize::Zeroizing;

const PAYLOAD_LIMIT: usize = 0x3fff;
const HEADER_SIZE: usize = 23;
const FRAME_TIMEOUT: Duration = Duration::from_secs(5);

// Match the existing AEAD replay policy: bounded, key-scoped, ten minutes,
// and no eviction of unexpired entries. No credentials or endpoints are kept.
#[derive(Default)]
struct ReplayWindow {
    entries: VecDeque<(std::time::Instant, [u8; 32])>,
    seen: HashSet<[u8; 32]>,
}
fn remember_response(value: [u8; 32]) -> io::Result<()> {
    static WINDOW: OnceLock<Mutex<ReplayWindow>> = OnceLock::new();
    let mut window = WINDOW
        .get_or_init(|| Mutex::new(ReplayWindow::default()))
        .lock()
        .map_err(|_| invalid())?;
    let now = std::time::Instant::now();
    while window
        .entries
        .front()
        .is_some_and(|(at, _)| now.duration_since(*at) > Duration::from_secs(600))
    {
        if let Some((_, digest)) = window.entries.pop_front() {
            window.seen.remove(&digest);
        }
    }
    if window.entries.len() >= 65536 || !window.seen.insert(value) {
        return Err(invalid());
    }
    window.entries.push_back((now, value));
    Ok(())
}

fn invalid() -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        "Snell framing or authentication failed",
    )
}

struct Cipher {
    key: aead::LessSafeKey,
    nonce: [u8; 12],
    exhausted: bool,
}
impl Cipher {
    fn new(psk: &[u8], salt: &[u8]) -> io::Result<Self> {
        let params = Params::new(8, 3, 1, Some(32)).map_err(|_| invalid())?;
        let mut key = Zeroizing::new([0u8; 32]);
        Argon2::new(Algorithm::Argon2id, Version::V0x13, params)
            .hash_password_into(psk, salt, &mut *key)
            .map_err(|_| invalid())?;
        Ok(Self {
            key: aead::LessSafeKey::new(
                aead::UnboundKey::new(&aead::AES_128_GCM, &key[..16]).map_err(|_| invalid())?,
            ),
            nonce: [0; 12],
            exhausted: false,
        })
    }
    fn nonce(&mut self) -> io::Result<aead::Nonce> {
        if self.exhausted {
            return Err(invalid());
        }
        let result = aead::Nonce::assume_unique_for_key(self.nonce);
        for byte in &mut self.nonce {
            let (value, carry) = byte.overflowing_add(1);
            *byte = value;
            if !carry {
                return Ok(result);
            }
        }
        self.exhausted = true;
        Ok(result)
    }
    fn seal(&mut self, bytes: &mut Vec<u8>) -> io::Result<()> {
        let nonce = self.nonce()?;
        self.key
            .seal_in_place_append_tag(nonce, aead::Aad::empty(), bytes)
            .map_err(|_| invalid())
    }
    fn open(&mut self, bytes: &mut Vec<u8>) -> io::Result<()> {
        let nonce = self.nonce()?;
        let length = self
            .key
            .open_in_place(nonce, aead::Aad::empty(), bytes)
            .map_err(|_| invalid())?
            .len();
        bytes.truncate(length);
        Ok(())
    }
}

enum Receive {
    Salt,
    Header,
    Body { padding: usize, payload: usize },
    Eof,
}
struct Reader {
    inner: ReadHalf<BoxStream>,
    psk: Zeroizing<Vec<u8>>,
    cipher: Option<Cipher>,
    response_identity: Option<[u8; 32]>,
    state: Receive,
    wire: Vec<u8>,
    data: Vec<u8>,
    position: usize,
    deadline: Option<Pin<Box<Sleep>>>,
    failed: bool,
    response_pending: bool,
}
impl Reader {
    fn fill(&mut self, cx: &mut Context<'_>, required: usize) -> Poll<io::Result<()>> {
        use std::future::Future;
        while self.wire.len() < required {
            if self
                .deadline
                .as_mut()
                .is_some_and(|deadline| deadline.as_mut().poll(cx).is_ready())
            {
                return Poll::Ready(Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Snell partial frame deadline",
                )));
            }
            let mut block = [0; 4096];
            let remaining = (required - self.wire.len()).min(block.len());
            let mut buffer = ReadBuf::new(&mut block[..remaining]);
            ready!(Pin::new(&mut self.inner).poll_read(cx, &mut buffer))?;
            if buffer.filled().is_empty() {
                return Poll::Ready(Err(io::ErrorKind::UnexpectedEof.into()));
            }
            if self.deadline.is_none() {
                self.deadline = Some(Box::pin(sleep(FRAME_TIMEOUT)));
            }
            self.wire.extend_from_slice(buffer.filled());
        }
        Poll::Ready(Ok(()))
    }
    fn frame(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<bool>> {
        loop {
            match self.state {
                Receive::Salt => {
                    ready!(self.fill(cx, 16))?;
                    self.cipher = Some(Cipher::new(&self.psk, &self.wire)?);
                    let mut digest = ring::digest::Context::new(&ring::digest::SHA256);
                    digest.update(&self.psk);
                    digest.update(&self.wire);
                    self.response_identity =
                        Some(digest.finish().as_ref().try_into().map_err(|_| invalid())?);
                    self.psk = Zeroizing::new(Vec::new());
                    self.wire.clear();
                    self.state = Receive::Header;
                }
                Receive::Header => {
                    match ready!(self.fill(cx, HEADER_SIZE)) {
                        Err(error)
                            if error.kind() == io::ErrorKind::UnexpectedEof
                                && self.wire.is_empty()
                                && !self.response_pending =>
                        {
                            // Non-reuse v4 peers may close TCP at a complete
                            // authenticated-record boundary instead of sending
                            // the reuse-mode zero chunk. Partial records and
                            // closure before authentication still fail closed.
                            self.state = Receive::Eof;
                            self.deadline = None;
                            return Poll::Ready(Ok(false));
                        }
                        result => result?,
                    }
                    self.cipher
                        .as_mut()
                        .ok_or_else(invalid)?
                        .open(&mut self.wire)?;
                    if self.wire.len() != 7 || self.wire[0] != 4 || self.wire[1..3] != [0, 0] {
                        return Poll::Ready(Err(invalid()));
                    }
                    // Unauthenticated salts cannot consume the replay budget.
                    if let Some(identity) = self.response_identity.take() {
                        remember_response(identity)?;
                    }
                    let padding = usize::from(u16::from_be_bytes([self.wire[3], self.wire[4]]));
                    let payload = usize::from(u16::from_be_bytes([self.wire[5], self.wire[6]]));
                    self.wire.clear();
                    if payload == 0 {
                        if padding != 0 || self.response_pending {
                            return Poll::Ready(Err(invalid()));
                        }
                        self.state = Receive::Eof;
                        self.deadline = None;
                        return Poll::Ready(Ok(false));
                    }
                    if payload > PAYLOAD_LIMIT {
                        return Poll::Ready(Err(invalid()));
                    }
                    self.state = Receive::Body { padding, payload };
                }
                Receive::Body { padding, payload } => {
                    let encrypted = payload + 16;
                    ready!(self.fill(cx, padding + encrypted))?;
                    for index in (0..padding.min(encrypted)).step_by(2) {
                        self.wire.swap(index, padding + index);
                    }
                    self.wire.drain(..padding);
                    self.cipher
                        .as_mut()
                        .ok_or_else(invalid)?
                        .open(&mut self.wire)?;
                    if self.wire.len() != payload {
                        return Poll::Ready(Err(invalid()));
                    }
                    self.data = std::mem::take(&mut self.wire);
                    self.position = 0;
                    if self.response_pending {
                        if self.data.first() != Some(&0) {
                            return Poll::Ready(Err(invalid()));
                        }
                        self.position = 1;
                        self.response_pending = false;
                    }
                    self.state = Receive::Header;
                    self.deadline = None;
                    return Poll::Ready(Ok(true));
                }
                Receive::Eof => return Poll::Ready(Ok(false)),
            }
        }
    }
}
impl AsyncRead for Reader {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        output: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if self.failed {
            return Poll::Ready(Err(invalid()));
        }
        if output.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        while self.position == self.data.len() {
            self.data.clear();
            self.position = 0;
            match ready!(self.frame(cx)) {
                Ok(false) => return Poll::Ready(Ok(())),
                Ok(true) => {}
                Err(error) => {
                    self.failed = true;
                    return Poll::Ready(Err(error));
                }
            }
        }
        let length = (self.data.len() - self.position).min(output.remaining());
        output.put_slice(&self.data[self.position..self.position + length]);
        self.position += length;
        Poll::Ready(Ok(()))
    }
}

struct Writer {
    inner: WriteHalf<BoxStream>,
    cipher: Cipher,
    pending: Vec<u8>,
    position: usize,
    first: bool,
    closed: bool,
    failed: bool,
}
impl Writer {
    fn drain(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        while self.position < self.pending.len() {
            let count = match ready!(
                Pin::new(&mut self.inner).poll_write(cx, &self.pending[self.position..])
            ) {
                Ok(0) => {
                    self.failed = true;
                    return Poll::Ready(Err(io::ErrorKind::WriteZero.into()));
                }
                Ok(count) => count,
                Err(error) => {
                    self.failed = true;
                    return Poll::Ready(Err(error));
                }
            };
            self.position += count;
        }
        self.pending.clear();
        self.position = 0;
        Poll::Ready(Ok(()))
    }
    fn frame(&mut self, data: &[u8]) -> io::Result<()> {
        let padding = if data.is_empty() {
            0
        } else if self.first {
            let mut value = [0];
            SystemRandom::new()
                .fill(&mut value)
                .map_err(|_| invalid())?;
            256 + usize::from(value[0])
        } else {
            0
        };
        self.first = false;
        let mut header = vec![4, 0, 0];
        header.extend_from_slice(&(padding as u16).to_be_bytes());
        header.extend_from_slice(&(data.len() as u16).to_be_bytes());
        self.cipher.seal(&mut header)?;
        self.pending.extend(header);
        if data.is_empty() {
            return Ok(());
        }
        let mut payload = data.to_vec();
        self.cipher.seal(&mut payload)?;
        let mut wire = vec![0; padding];
        SystemRandom::new().fill(&mut wire).map_err(|_| invalid())?;
        wire.extend(&payload);
        for index in (0..padding.min(payload.len())).step_by(2) {
            wire.swap(index, padding + index);
        }
        self.pending.extend(wire);
        Ok(())
    }
}
impl AsyncWrite for Writer {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        data: &[u8],
    ) -> Poll<io::Result<usize>> {
        if self.failed || self.closed {
            return Poll::Ready(Err(invalid()));
        }
        ready!(self.drain(cx))?;
        if data.is_empty() {
            return Poll::Ready(Ok(0));
        }
        let length = data.len().min(PAYLOAD_LIMIT);
        if let Err(error) = self.frame(&data[..length]) {
            self.failed = true;
            return Poll::Ready(Err(error));
        }
        Poll::Ready(Ok(length))
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.failed {
            return Poll::Ready(Err(invalid()));
        }
        ready!(self.drain(cx))?;
        Pin::new(&mut self.inner).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.failed {
            return Poll::Ready(Err(invalid()));
        }
        ready!(self.drain(cx))?;
        // This client sends non-reuse CONNECT. Its half-close is TCP FIN;
        // adding a reuse-mode zero chunk after the destination has closed can
        // make the peer reset TCP because those bytes are no longer consumed.
        self.closed = true;
        Pin::new(&mut self.inner).poll_shutdown(cx)
    }
}

pub struct Stream {
    reader: Reader,
    writer: Writer,
}
impl Stream {
    fn new(inner: BoxStream, psk: &str) -> io::Result<Self> {
        if psk.is_empty() || psk.len() > 1024 {
            return Err(invalid());
        }
        let mut salt = [0; 16];
        SystemRandom::new().fill(&mut salt).map_err(|_| invalid())?;
        let cipher = Cipher::new(psk.as_bytes(), &salt)?;
        let (read, write) = tokio::io::split(inner);
        Ok(Self {
            reader: Reader {
                inner: read,
                psk: Zeroizing::new(psk.as_bytes().to_vec()),
                cipher: None,
                response_identity: None,
                state: Receive::Salt,
                wire: Vec::new(),
                data: Vec::new(),
                position: 0,
                deadline: None,
                failed: false,
                response_pending: true,
            },
            writer: Writer {
                inner: write,
                cipher,
                pending: salt.to_vec(),
                position: 0,
                first: true,
                closed: false,
                failed: false,
            },
        })
    }
}
impl AsyncRead for Stream {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        output: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if self.writer.failed {
            return Poll::Ready(Err(invalid()));
        }
        let result = Pin::new(&mut self.reader).poll_read(cx, output);
        if matches!(&result, Poll::Ready(Err(_))) {
            self.writer.failed = true;
        }
        result
    }
}
impl AsyncWrite for Stream {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        data: &[u8],
    ) -> Poll<io::Result<usize>> {
        if self.reader.failed {
            return Poll::Ready(Err(invalid()));
        }
        let result = Pin::new(&mut self.writer).poll_write(cx, data);
        if matches!(&result, Poll::Ready(Err(_))) {
            self.reader.failed = true;
        }
        result
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.reader.failed {
            return Poll::Ready(Err(invalid()));
        }
        let result = Pin::new(&mut self.writer).poll_flush(cx);
        if matches!(&result, Poll::Ready(Err(_))) {
            self.reader.failed = true;
        }
        result
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.reader.failed {
            return Poll::Ready(Err(invalid()));
        }
        let result = Pin::new(&mut self.writer).poll_shutdown(cx);
        if matches!(&result, Poll::Ready(Err(_))) {
            self.reader.failed = true;
        }
        result
    }
}

pub async fn connect(inner: BoxStream, psk: &str, target: &Target) -> Result<BoxStream> {
    if !swirl_subscription::valid_host(&target.host) || target.host.len() > 255 || target.port == 0
    {
        return Err("SnellTarget");
    }
    let mut stream = Stream::new(inner, psk).map_err(|_| "SnellSetup")?;
    let mut request = vec![1, 1, 0, target.host.len() as u8];
    request.extend(target.host.as_bytes());
    request.extend(target.port.to_be_bytes());
    stream
        .write_all(&request)
        .await
        .map_err(|_| "SnellHandshakeWrite")?;
    stream.flush().await.map_err(|_| "SnellHandshakeWrite")?;
    // The peer can delay its authenticated status byte until target data.
    // Reader consumes that byte before exposing any application payload.
    Ok(Box::new(stream))
}

/// One bounded UDP-over-TCP carrier. Datagram boundaries are AEAD-frame
/// boundaries; partial receives survive cancellation and retain their deadline.
pub struct UdpAssociation {
    reader: Reader,
    writer: Writer,
    failed: bool,
}
impl UdpAssociation {
    pub async fn connect(
        config: &swirl_subscription::Snell,
        resolver: &swirl_dns::Resolver,
        limit: Duration,
    ) -> Result<Self> {
        config.validate()?;
        if !config.udp {
            return Err("SnellUdpDisabled");
        }
        let deadline = tokio::time::Instant::now() + limit;
        let inner = crate::dial::connect_tcp(
            resolver,
            &Target {
                host: config.host.clone(),
                port: config.port,
            },
            deadline,
        )
        .await?;
        crate::dial::within(deadline, "SnellHandshakeTimeout", async {
            let mut stream = Stream::new(Box::new(inner), &config.psk).map_err(|_| "SnellSetup")?;
            stream
                .write_all(&[1, 6, 0])
                .await
                .map_err(|_| "SnellHandshakeWrite")?;
            stream.flush().await.map_err(|_| "SnellHandshakeWrite")?;
            Ok(Self {
                reader: stream.reader,
                writer: stream.writer,
                failed: false,
            })
        })
        .await
    }
    pub async fn send(&mut self, target: &Target, payload: &[u8]) -> Result<()> {
        if self.failed {
            return Err("SnellUdpClosed");
        }
        if !swirl_subscription::valid_host(&target.host) || target.port == 0 {
            return Err("SnellUdpTarget");
        }
        let mut packet = vec![1];
        match target.host.parse::<std::net::IpAddr>() {
            Ok(std::net::IpAddr::V4(ip)) => {
                packet.extend([0, 4]);
                packet.extend(ip.octets());
            }
            Ok(std::net::IpAddr::V6(ip)) => {
                packet.extend([0, 6]);
                packet.extend(ip.octets());
            }
            Err(_) if target.host.len() <= 255 => {
                packet.push(target.host.len() as u8);
                packet.extend(target.host.as_bytes());
            }
            _ => return Err("SnellUdpTarget"),
        }
        packet.extend(target.port.to_be_bytes());
        if payload.len() > PAYLOAD_LIMIT - packet.len() {
            return Err("SnellUdpPayloadTooLarge");
        }
        packet.extend(payload);
        // A cancelled write retires this carrier rather than replaying an
        // ambiguously sent datagram on its next use.
        self.failed = true;
        std::future::poll_fn(|cx| self.writer.drain(cx))
            .await
            .map_err(|_| "SnellUdpWrite")?;
        self.writer.frame(&packet).map_err(|_| "SnellUdpWrite")?;
        self.writer.flush().await.map_err(|_| "SnellUdpWrite")?;
        self.failed = false;
        Ok(())
    }
    pub async fn recv(&mut self) -> Result<(Target, Vec<u8>)> {
        if self.failed {
            return Err("SnellUdpClosed");
        }
        loop {
            self.reader.data.clear();
            self.reader.position = 0;
            match std::future::poll_fn(|cx| self.reader.frame(cx)).await {
                Ok(true) => {}
                Ok(false) => {
                    self.failed = true;
                    return Err("SnellUdpClosed");
                }
                Err(_) => {
                    self.failed = true;
                    return Err("SnellUdpRead");
                }
            }
            if self.reader.position == self.reader.data.len() {
                continue;
            }
            let data = &self.reader.data[self.reader.position..];
            let parsed = parse_udp(data);
            if parsed.is_err() {
                self.failed = true;
            }
            return parsed;
        }
    }
}
fn parse_udp(data: &[u8]) -> Result<(Target, Vec<u8>)> {
    let (host, offset) = match data.first() {
        Some(4) if data.len() >= 7 => (
            std::net::Ipv4Addr::new(data[1], data[2], data[3], data[4]).to_string(),
            5,
        ),
        Some(6) if data.len() >= 19 => {
            let bytes = <[u8; 16]>::try_from(&data[1..17]).map_err(|_| "SnellUdpAddress")?;
            (std::net::Ipv6Addr::from(bytes).to_string(), 17)
        }
        _ => return Err("SnellUdpAddress"),
    };
    let port = u16::from_be_bytes([data[offset], data[offset + 1]]);
    if port == 0 || data.len() > PAYLOAD_LIMIT {
        return Err("SnellUdpAddress");
    }
    Ok((Target { host, port }, data[offset + 2..].to_vec()))
}

#[cfg(test)]
#[path = "snell_tests.rs"]
mod tests;
