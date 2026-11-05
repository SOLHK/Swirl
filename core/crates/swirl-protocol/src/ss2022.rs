//! Swirl-owned SIP022 Shadowsocks 2022 AES-GCM TCP and UDP client.
//!
//! Primary specification: https://shadowsocks.org/doc/sip022.html. A fixed
//! independent shadowsocks-rust server is used for interoperability only.
//! SIP023 multi-user identity headers and optional ChaCha variants are rejected.
use aes::cipher::{BlockDecrypt, BlockEncrypt, KeyInit};
use base64::{
    Engine,
    engine::general_purpose::{STANDARD, STANDARD_NO_PAD},
};
use ring::{
    aead,
    rand::{SecureRandom, SystemRandom},
};
use std::{
    future::Future,
    io,
    net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr},
    pin::Pin,
    sync::Mutex,
    task::{Context, Poll, ready},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use swirl_dns::Resolver;
use swirl_transport::{BoxStream, bind_udp};
use tokio::{
    io::{AsyncRead, AsyncWrite, AsyncWriteExt, ReadBuf},
    net::UdpSocket,
};
use zeroize::Zeroizing;

const TAG: usize = 16;
const MAX_PAYLOAD: usize = 65_535;
const MAX_DATAGRAM: usize = 65_507;
const UDP_WINDOW: usize = 1024;
const SESSION_RETENTION: Duration = Duration::from_secs(60);

fn error(code: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, code)
}

fn algorithm(cipher: &str) -> crate::Result<&'static aead::Algorithm> {
    match cipher {
        "2022-blake3-aes-128-gcm" => Ok(&aead::AES_128_GCM),
        "2022-blake3-aes-256-gcm" => Ok(&aead::AES_256_GCM),
        _ => Err("Ss2022CipherUnsupported"),
    }
}

pub fn validate(password: &str, cipher: &str) -> crate::Result<()> {
    swirl_subscription::ss2022::validate(password, cipher)
}

fn key(password: &str, cipher: &str) -> crate::Result<Zeroizing<Vec<u8>>> {
    validate(password, cipher)?;
    let value = STANDARD
        .decode(password)
        .or_else(|_| STANDARD_NO_PAD.decode(password))
        .map_err(|_| "Ss2022Key")?;
    Ok(Zeroizing::new(value))
}

fn timestamp() -> io::Result<u64> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_secs())
        .map_err(|_| error("Ss2022Clock"))
}

fn valid_timestamp(value: u64, now: u64) -> io::Result<()> {
    if value.abs_diff(now) > 30 {
        return Err(error("Ss2022Timestamp"));
    }
    Ok(())
}

fn random(bytes: &mut [u8]) -> io::Result<()> {
    SystemRandom::new()
        .fill(bytes)
        .map_err(|_| error("Ss2022Random"))
}

fn derive(
    algorithm: &'static aead::Algorithm,
    master: &[u8],
    salt: &[u8],
) -> io::Result<aead::LessSafeKey> {
    let mut material = Zeroizing::new(Vec::with_capacity(master.len() + salt.len()));
    material.extend_from_slice(master);
    material.extend_from_slice(salt);
    let derived = Zeroizing::new(blake3::derive_key(
        "shadowsocks 2022 session subkey",
        &material,
    ));
    Ok(aead::LessSafeKey::new(
        aead::UnboundKey::new(algorithm, &derived[..algorithm.key_len()])
            .map_err(|_| error("Ss2022Key"))?,
    ))
}

struct Cipher {
    key: aead::LessSafeKey,
    nonce: [u8; 12],
    exhausted: bool,
}

impl Cipher {
    fn new(algorithm: &'static aead::Algorithm, master: &[u8], salt: &[u8]) -> io::Result<Self> {
        Ok(Self {
            key: derive(algorithm, master, salt)?,
            nonce: [0; 12],
            exhausted: false,
        })
    }

    fn nonce(&mut self) -> io::Result<aead::Nonce> {
        if self.exhausted {
            return Err(error("Ss2022NonceExhausted"));
        }
        let nonce = aead::Nonce::assume_unique_for_key(self.nonce);
        for byte in &mut self.nonce {
            let (next, overflow) = byte.overflowing_add(1);
            *byte = next;
            if !overflow {
                return Ok(nonce);
            }
        }
        self.exhausted = true;
        Ok(nonce)
    }

    fn seal(&mut self, bytes: &mut Vec<u8>) -> io::Result<()> {
        let nonce = self.nonce()?;
        self.key
            .seal_in_place_append_tag(nonce, aead::Aad::empty(), bytes)
            .map_err(|_| error("Ss2022Encrypt"))
    }

    fn open(&mut self, bytes: &mut Vec<u8>) -> io::Result<()> {
        let nonce = self.nonce()?;
        let length = self
            .key
            .open_in_place(nonce, aead::Aad::empty(), bytes)
            .map_err(|_| error("Ss2022Authentication"))?
            .len();
        bytes.truncate(length);
        Ok(())
    }
}

enum Stage {
    Header,
    Length,
    Payload,
}

struct Stream {
    inner: BoxStream,
    algorithm: &'static aead::Algorithm,
    master: Zeroizing<Vec<u8>>,
    request_salt: Vec<u8>,
    sender: Cipher,
    receiver: Option<Cipher>,
    pending: Vec<u8>,
    sent: usize,
    stage: Stage,
    input: Vec<u8>,
    needed: usize,
    plain: Vec<u8>,
    consumed: usize,
    limit: Duration,
    progress_deadline: Option<Pin<Box<tokio::time::Sleep>>>,
    failed: bool,
    eof: bool,
    write_closed: bool,
}

impl Stream {
    fn drain(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        while self.sent < self.pending.len() {
            let size =
                ready!(Pin::new(&mut self.inner).poll_write(cx, &self.pending[self.sent..]))?;
            if size == 0 {
                return Poll::Ready(Err(io::ErrorKind::WriteZero.into()));
            }
            self.sent += size;
        }
        self.pending.clear();
        self.sent = 0;
        Poll::Ready(Ok(()))
    }

    fn read_record(
        &mut self,
        cx: &mut Context<'_>,
        output: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if self.eof || output.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        for _ in 0..8 {
            if self.consumed < self.plain.len() {
                let size = output.remaining().min(self.plain.len() - self.consumed);
                output.put_slice(&self.plain[self.consumed..self.consumed + size]);
                self.consumed += size;
                return Poll::Ready(Ok(()));
            }
            // SIP022 requires a single successful read of salt + fixed header.
            // A peer splitting its initial header is rejected explicitly; it
            // cannot keep an unbounded partially authenticated header alive.
            if matches!(self.stage, Stage::Header) {
                let mut bytes = [0u8; 2 * 32 + 11 + TAG];
                let mut buffer = ReadBuf::new(&mut bytes[..self.needed]);
                ready!(Pin::new(&mut self.inner).poll_read(cx, &mut buffer))?;
                if buffer.filled().len() != self.needed {
                    return Poll::Ready(Err(error("Ss2022IncompleteResponseHeader")));
                }
                let salt_len = self.algorithm.key_len();
                let bytes = buffer.filled();
                let mut receiver = Cipher::new(self.algorithm, &self.master, &bytes[..salt_len])?;
                let mut header = bytes[salt_len..].to_vec();
                receiver.open(&mut header)?;
                if header[0] != 1 || header[9..9 + salt_len] != self.request_salt {
                    return Poll::Ready(Err(error("Ss2022ResponseBinding")));
                }
                valid_timestamp(
                    u64::from_be_bytes(header[1..9].try_into().map_err(|_| error("Ss2022Header"))?),
                    timestamp()?,
                )?;
                let size = usize::from(u16::from_be_bytes([
                    header[9 + salt_len],
                    header[10 + salt_len],
                ]));
                if size == 0 {
                    return Poll::Ready(Err(error("Ss2022EmptyResponseHeader")));
                }
                self.receiver = Some(receiver);
                self.stage = Stage::Payload;
                self.needed = size + TAG;
                self.progress_deadline = Some(Box::pin(tokio::time::sleep(self.limit)));
            }
            while self.input.len() < self.needed {
                if let Some(deadline) = &mut self.progress_deadline
                    && deadline.as_mut().poll(cx).is_ready()
                {
                    return Poll::Ready(Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        "Ss2022RecordTimeout",
                    )));
                }
                let mut bytes = [0u8; 16_384];
                let mut buffer =
                    ReadBuf::new(&mut bytes[..(self.needed - self.input.len()).min(16_384)]);
                ready!(Pin::new(&mut self.inner).poll_read(cx, &mut buffer))?;
                if buffer.filled().is_empty() {
                    if matches!(self.stage, Stage::Length) && self.input.is_empty() {
                        // SIP022 has no authenticated terminal record. Only an
                        // exact encrypted-record boundary accepts transport FIN.
                        self.eof = true;
                        return Poll::Ready(Ok(()));
                    }
                    return Poll::Ready(Err(io::ErrorKind::UnexpectedEof.into()));
                }
                if self.progress_deadline.is_none() {
                    self.progress_deadline = Some(Box::pin(tokio::time::sleep(self.limit)));
                }
                self.input.extend_from_slice(buffer.filled());
            }
            self.receiver
                .as_mut()
                .ok_or_else(|| error("Ss2022State"))?
                .open(&mut self.input)?;
            match self.stage {
                Stage::Length => {
                    self.needed =
                        usize::from(u16::from_be_bytes([self.input[0], self.input[1]])) + TAG;
                    self.stage = Stage::Payload;
                    self.input.clear();
                }
                Stage::Payload => {
                    self.plain = std::mem::take(&mut self.input);
                    self.consumed = 0;
                    self.needed = 2 + TAG;
                    self.stage = Stage::Length;
                    self.progress_deadline = None;
                }
                Stage::Header => return Poll::Ready(Err(error("Ss2022State"))),
            }
        }
        cx.waker().wake_by_ref();
        Poll::Pending
    }
}

impl AsyncRead for Stream {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        output: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if self.failed {
            return Poll::Ready(Err(error("Ss2022StreamFailed")));
        }
        let result = self.read_record(cx, output);
        if matches!(result, Poll::Ready(Err(_))) {
            self.failed = true;
        }
        result
    }
}

impl AsyncWrite for Stream {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        if self.failed {
            return Poll::Ready(Err(error("Ss2022StreamFailed")));
        }
        if self.write_closed {
            return Poll::Ready(Err(io::ErrorKind::BrokenPipe.into()));
        }
        if let Err(error) = ready!(self.drain(cx)) {
            self.failed = true;
            return Poll::Ready(Err(error));
        }
        if bytes.is_empty() {
            return Poll::Ready(Ok(0));
        }
        let size = bytes.len().min(MAX_PAYLOAD);
        let mut length = (size as u16).to_be_bytes().to_vec();
        let mut payload = bytes[..size].to_vec();
        if let Err(error) = self
            .sender
            .seal(&mut length)
            .and_then(|()| self.sender.seal(&mut payload))
        {
            self.failed = true;
            return Poll::Ready(Err(error));
        }
        self.pending.extend(length);
        self.pending.extend(payload);
        Poll::Ready(Ok(size))
    }

    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.failed {
            return Poll::Ready(Err(error("Ss2022StreamFailed")));
        }
        if let Err(error) = ready!(self.drain(cx)) {
            self.failed = true;
            return Poll::Ready(Err(error));
        }
        let result = Pin::new(&mut self.inner).poll_flush(cx);
        if matches!(result, Poll::Ready(Err(_))) {
            self.failed = true;
        }
        result
    }

    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        ready!(self.as_mut().poll_flush(cx))?;
        let result = Pin::new(&mut self.inner).poll_shutdown(cx);
        if matches!(result, Poll::Ready(Ok(()))) {
            self.write_closed = true;
        }
        if matches!(result, Poll::Ready(Err(_))) {
            self.failed = true;
        }
        result
    }
}

pub async fn connect(
    mut inner: BoxStream,
    password: &str,
    cipher: &str,
    target: &crate::Target,
    response_timeout: Duration,
) -> crate::Result<BoxStream> {
    let master = key(password, cipher)?;
    let algorithm = algorithm(cipher)?;
    if target.port == 0 || !swirl_subscription::valid_host(&target.host) {
        return Err("InvalidTarget");
    }
    let mut salt = vec![0; algorithm.key_len()];
    random(&mut salt).map_err(|_| "Ss2022Random")?;
    let mut sender = Cipher::new(algorithm, &master, &salt).map_err(|_| "Ss2022Key")?;
    let mut variable = Vec::new();
    target.encode(&mut variable)?;
    let mut seed = [0; 2];
    random(&mut seed).map_err(|_| "Ss2022Random")?;
    let padding_size = u16::from_be_bytes(seed) % 900 + 1;
    variable.extend(padding_size.to_be_bytes());
    let start = variable.len();
    variable.resize(start + usize::from(padding_size), 0);
    random(&mut variable[start..]).map_err(|_| "Ss2022Random")?;
    let mut fixed = vec![0];
    fixed.extend(timestamp().map_err(|_| "Ss2022Clock")?.to_be_bytes());
    fixed.extend((variable.len() as u16).to_be_bytes());
    sender.seal(&mut fixed).map_err(|_| "Ss2022Encrypt")?;
    sender.seal(&mut variable).map_err(|_| "Ss2022Encrypt")?;
    let mut request = salt.clone();
    request.extend(fixed);
    request.extend(variable);
    // Buffer the complete salt + both header chunks into one write as SIP022
    // requires. A short initial write fails explicitly rather than fragmenting
    // the protocol header into recognizable separate writes.
    let written = inner
        .write(&request)
        .await
        .map_err(|_| "Ss2022HandshakeWrite")?;
    if written != request.len() {
        return Err("Ss2022ShortHandshakeWrite");
    }
    inner.flush().await.map_err(|_| "Ss2022HandshakeWrite")?;
    Ok(Box::new(Stream {
        inner,
        algorithm,
        master,
        request_salt: salt,
        sender,
        receiver: None,
        pending: Vec::new(),
        sent: 0,
        stage: Stage::Header,
        input: Vec::new(),
        needed: 2 * algorithm.key_len() + 11 + TAG,
        plain: Vec::new(),
        consumed: 0,
        limit: response_timeout,
        progress_deadline: None,
        failed: false,
        eof: false,
        write_closed: false,
    }))
}

enum HeaderCipher {
    Aes128(Box<aes::Aes128>),
    Aes256(Box<aes::Aes256>),
}
impl HeaderCipher {
    fn new(master: &[u8]) -> io::Result<Self> {
        match master.len() {
            16 => Ok(Self::Aes128(Box::new(
                aes::Aes128::new_from_slice(master).map_err(|_| error("Ss2022Key"))?,
            ))),
            32 => Ok(Self::Aes256(Box::new(
                aes::Aes256::new_from_slice(master).map_err(|_| error("Ss2022Key"))?,
            ))),
            _ => Err(error("Ss2022Key")),
        }
    }
    fn encrypt(&self, bytes: &mut [u8; 16]) {
        let mut block = aes::Block::from(*bytes);
        match self {
            Self::Aes128(cipher) => cipher.encrypt_block(&mut block),
            Self::Aes256(cipher) => cipher.encrypt_block(&mut block),
        }
        *bytes = block.into();
    }
    fn decrypt(&self, bytes: &mut [u8; 16]) {
        let mut block = aes::Block::from(*bytes);
        match self {
            Self::Aes128(cipher) => cipher.decrypt_block(&mut block),
            Self::Aes256(cipher) => cipher.decrypt_block(&mut block),
        }
        *bytes = block.into();
    }
}

#[derive(Default)]
struct ReplayWindow {
    maximum: Option<u64>,
    bitmap: [u64; UDP_WINDOW / 64],
}
impl ReplayWindow {
    fn accepts(&self, packet: u64) -> bool {
        let Some(maximum) = self.maximum else {
            return true;
        };
        if packet > maximum {
            return true;
        }
        let age = maximum - packet;
        if age >= UDP_WINDOW as u64 {
            return false;
        }
        self.bitmap[age as usize / 64] & (1u64 << (age % 64)) == 0
    }
    fn observe(&mut self, packet: u64) {
        if let Some(maximum) = self.maximum {
            if packet <= maximum {
                let age = (maximum - packet) as usize;
                self.bitmap[age / 64] |= 1u64 << (age % 64);
                return;
            }
            let shift = packet - maximum;
            if shift >= UDP_WINDOW as u64 {
                self.bitmap.fill(0);
            } else {
                let whole = shift as usize / 64;
                let part = shift as usize % 64;
                for index in (0..self.bitmap.len()).rev() {
                    let mut value = if index >= whole {
                        self.bitmap[index - whole] << part
                    } else {
                        0
                    };
                    if part != 0 && index > whole {
                        value |= self.bitmap[index - whole - 1] >> (64 - part);
                    }
                    self.bitmap[index] = value;
                }
            }
        }
        self.maximum = Some(packet);
        self.bitmap[0] |= 1;
    }
}

struct RemoteSession {
    id: [u8; 8],
    key: aead::LessSafeKey,
    window: ReplayWindow,
    last: Instant,
}

/// One source-address UDP association. Never share this state among unrelated
/// local UDP clients. At most two authenticated server sessions are retained,
/// each for >=60 seconds, as permitted by SIP022 server-restart handling.
pub struct UdpSession {
    algorithm: &'static aead::Algorithm,
    master: Zeroizing<Vec<u8>>,
    header: HeaderCipher,
    session: [u8; 8],
    sender: aead::LessSafeKey,
    next_packet: u64,
    exhausted: bool,
    remotes: [Option<RemoteSession>; 2],
}

fn address_length(bytes: &[u8]) -> io::Result<usize> {
    let size = match bytes.first() {
        Some(1) => 7,
        Some(4) => 19,
        Some(3) if bytes.len() >= 2 => {
            let count = usize::from(bytes[1]);
            if bytes.len() < count + 4
                || !std::str::from_utf8(&bytes[2..2 + count])
                    .is_ok_and(swirl_subscription::valid_host)
            {
                return Err(error("Ss2022Address"));
            }
            count + 4
        }
        _ => return Err(error("Ss2022Address")),
    };
    if bytes.len() < size || bytes[size - 2..size] == [0, 0] {
        return Err(error("Ss2022Address"));
    }
    Ok(size)
}

impl UdpSession {
    pub fn new(password: &str, cipher: &str) -> crate::Result<Self> {
        let master = key(password, cipher)?;
        let algorithm = algorithm(cipher)?;
        let header = HeaderCipher::new(&master).map_err(|_| "Ss2022Key")?;
        let mut session = [0; 8];
        random(&mut session).map_err(|_| "Ss2022Random")?;
        let sender = derive(algorithm, &master, &session).map_err(|_| "Ss2022Key")?;
        Ok(Self {
            algorithm,
            master,
            header,
            session,
            sender,
            next_packet: 0,
            exhausted: false,
            remotes: [None, None],
        })
    }

    pub fn encrypt(&mut self, address_and_payload: &[u8]) -> io::Result<Vec<u8>> {
        address_length(address_and_payload)?;
        if address_and_payload.len() > MAX_DATAGRAM - 16 - 11 - TAG {
            return Err(error("Ss2022DatagramLimit"));
        }
        if self.exhausted {
            return Err(error("Ss2022PacketIdExhausted"));
        }
        let mut separate = [0; 16];
        separate[..8].copy_from_slice(&self.session);
        separate[8..].copy_from_slice(&self.next_packet.to_be_bytes());
        if self.next_packet == u64::MAX {
            self.exhausted = true;
        } else {
            self.next_packet += 1;
        }
        let nonce = aead::Nonce::assume_unique_for_key(
            separate[4..].try_into().map_err(|_| error("Ss2022State"))?,
        );
        let mut body = vec![0];
        body.extend(timestamp()?.to_be_bytes());
        body.extend([0, 0]); // No optional UDP padding; preserve the path MTU.
        body.extend_from_slice(address_and_payload);
        self.sender
            .seal_in_place_append_tag(nonce, aead::Aad::empty(), &mut body)
            .map_err(|_| error("Ss2022Encrypt"))?;
        self.header.encrypt(&mut separate);
        let mut wire = separate.to_vec();
        wire.extend(body);
        Ok(wire)
    }

    pub fn decrypt(&mut self, wire: &[u8]) -> io::Result<Vec<u8>> {
        if wire.len() < 16 + 19 + 5 + TAG || wire.len() > MAX_DATAGRAM {
            return Err(error("Ss2022DatagramLimit"));
        }
        let mut separate: [u8; 16] = wire[..16].try_into().map_err(|_| error("Ss2022Header"))?;
        self.header.decrypt(&mut separate);
        let session: [u8; 8] = separate[..8]
            .try_into()
            .map_err(|_| error("Ss2022Header"))?;
        if session == self.session {
            return Err(error("Ss2022SessionDirection"));
        }
        let packet = u64::from_be_bytes(
            separate[8..]
                .try_into()
                .map_err(|_| error("Ss2022Header"))?,
        );
        let known = self
            .remotes
            .iter()
            .position(|item| item.as_ref().is_some_and(|item| item.id == session));
        if let Some(index) = known
            && !self.remotes[index]
                .as_ref()
                .is_some_and(|item| item.window.accepts(packet))
        {
            return Err(error("Ss2022Replay"));
        }
        let fresh_key = if known.is_none() {
            Some(derive(self.algorithm, &self.master, &session)?)
        } else {
            None
        };
        let key = if let Some(index) = known {
            &self.remotes[index]
                .as_ref()
                .ok_or_else(|| error("Ss2022State"))?
                .key
        } else {
            fresh_key.as_ref().ok_or_else(|| error("Ss2022State"))?
        };
        let mut body = wire[16..].to_vec();
        let nonce = aead::Nonce::assume_unique_for_key(
            separate[4..]
                .try_into()
                .map_err(|_| error("Ss2022Header"))?,
        );
        let size = key
            .open_in_place(nonce, aead::Aad::empty(), &mut body)
            .map_err(|_| error("Ss2022Authentication"))?
            .len();
        body.truncate(size);
        if body.len() < 19 || body[0] != 1 || body[9..17] != self.session {
            return Err(error("Ss2022SessionBinding"));
        }
        valid_timestamp(
            u64::from_be_bytes(body[1..9].try_into().map_err(|_| error("Ss2022Header"))?),
            timestamp()?,
        )?;
        let padding = usize::from(u16::from_be_bytes([body[17], body[18]]));
        let address = body
            .get(19 + padding..)
            .ok_or_else(|| error("Ss2022Padding"))?;
        address_length(address)?;
        let result = address.to_vec();
        // Only authenticated, semantically valid messages update the replay
        // window, session retention, or server session count.
        let now = Instant::now();
        let index = if let Some(index) = known {
            index
        } else {
            let index = self
                .remotes
                .iter()
                .position(|item| {
                    item.as_ref()
                        .is_none_or(|item| now.duration_since(item.last) >= SESSION_RETENTION)
                })
                .ok_or_else(|| error("Ss2022SessionLimit"))?;
            self.remotes[index] = Some(RemoteSession {
                id: session,
                key: fresh_key.ok_or_else(|| error("Ss2022State"))?,
                window: ReplayWindow::default(),
                last: now,
            });
            index
        };
        let remote = self.remotes[index]
            .as_mut()
            .ok_or_else(|| error("Ss2022State"))?;
        remote.window.observe(packet);
        remote.last = now;
        Ok(result)
    }
}

/// Connected native UDP socket and its authenticated SIP022 session. `recv`
/// is cancellation safe: no packet or replay-state update crosses an await.
pub struct UdpAssociation {
    socket: UdpSocket,
    session: Mutex<UdpSession>,
}
impl UdpAssociation {
    pub async fn connect(
        host: &str,
        port: u16,
        password: &str,
        cipher: &str,
        resolver: &Resolver,
        limit: Duration,
    ) -> crate::Result<Self> {
        let session = UdpSession::new(password, cipher)?;
        if port == 0 || !swirl_subscription::valid_host(host) {
            return Err("Ss2022Server");
        }
        let socket = tokio::time::timeout(limit, async {
            let addresses = resolver.resolve(host, port).await?;
            for address in addresses {
                let local = SocketAddr::new(
                    if address.is_ipv4() && address.ip().is_loopback() {
                        IpAddr::V4(Ipv4Addr::LOCALHOST)
                    } else if address.ip().is_loopback() {
                        IpAddr::V6(Ipv6Addr::LOCALHOST)
                    } else if address.is_ipv4() {
                        IpAddr::V4(Ipv4Addr::UNSPECIFIED)
                    } else {
                        IpAddr::V6(Ipv6Addr::UNSPECIFIED)
                    },
                    0,
                );
                // Every non-loopback proxy socket must pass the common egress
                // guard and buffer setup; UDP connect alone applies no binding.
                let Ok(socket) = bind_udp(local).await else {
                    continue;
                };
                if socket.connect(address).await.is_ok() {
                    return Ok(socket);
                }
            }
            Err("Ss2022UdpConnect")
        })
        .await
        .map_err(|_| "Ss2022UdpConnectTimeout")??;
        Ok(Self {
            socket,
            session: Mutex::new(session),
        })
    }

    pub async fn send(&self, target: &crate::Target, payload: &[u8]) -> crate::Result<()> {
        if payload.len() > MAX_DATAGRAM {
            return Err("Ss2022DatagramLimit");
        }
        let mut plain = Vec::with_capacity(259 + payload.len());
        target.encode(&mut plain)?;
        plain.extend_from_slice(payload);
        let wire = self
            .session
            .lock()
            .map_err(|_| "Ss2022State")?
            .encrypt(&plain)
            .map_err(|_| "Ss2022UdpEncode")?;
        if self.socket.send(&wire).await.map_err(|_| "Ss2022UdpSend")? != wire.len() {
            return Err("Ss2022UdpSend");
        }
        Ok(())
    }

    pub async fn recv(&mut self) -> crate::Result<(crate::Target, Vec<u8>)> {
        let mut wire = vec![0; MAX_DATAGRAM + 1];
        let mut rejected = 0;
        loop {
            let size = self
                .socket
                .recv(&mut wire)
                .await
                .map_err(|_| "Ss2022UdpReceive")?;
            let plain = self
                .session
                .lock()
                .map_err(|_| "Ss2022State")?
                .decrypt(&wire[..size]);
            if let Ok(plain) = plain {
                // Address validation already completed before replay commit.
                let size = address_length(&plain).map_err(|_| "Ss2022Address")?;
                let (host, port) = match plain[0] {
                    1 => (
                        Ipv4Addr::new(plain[1], plain[2], plain[3], plain[4]).to_string(),
                        u16::from_be_bytes([plain[5], plain[6]]),
                    ),
                    4 => (
                        Ipv6Addr::from(
                            <[u8; 16]>::try_from(&plain[1..17]).map_err(|_| "Ss2022Address")?,
                        )
                        .to_string(),
                        u16::from_be_bytes([plain[17], plain[18]]),
                    ),
                    3 => (
                        std::str::from_utf8(&plain[2..size - 2])
                            .map_err(|_| "Ss2022Address")?
                            .to_string(),
                        u16::from_be_bytes([plain[size - 2], plain[size - 1]]),
                    ),
                    _ => return Err("Ss2022Address"),
                };
                return Ok((crate::Target { host, port }, plain[size..].to_vec()));
            }
            rejected += 1;
            if rejected == 32 {
                tokio::task::yield_now().await;
                rejected = 0;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    const AES128: &str = "2022-blake3-aes-128-gcm";
    const AES256: &str = "2022-blake3-aes-256-gcm";

    fn udp(method: &str) -> UdpSession {
        let size = algorithm(method).unwrap().key_len();
        UdpSession::new(&STANDARD.encode(vec![7; size]), method).unwrap()
    }

    fn address() -> Vec<u8> {
        vec![1, 127, 0, 0, 1, 0, 53, 10, 20, 30]
    }

    fn server_packet(
        client: &UdpSession,
        server: [u8; 8],
        id: u64,
        clock: u64,
        binding: [u8; 8],
        direction: u8,
        address: &[u8],
    ) -> Vec<u8> {
        let mut separate = [0; 16];
        separate[..8].copy_from_slice(&server);
        separate[8..].copy_from_slice(&id.to_be_bytes());
        let nonce = aead::Nonce::assume_unique_for_key(separate[4..].try_into().unwrap());
        let key = derive(client.algorithm, &client.master, &server).unwrap();
        let mut body = vec![direction];
        body.extend(clock.to_be_bytes());
        body.extend(binding);
        body.extend([0, 0]);
        body.extend(address);
        key.seal_in_place_append_tag(nonce, aead::Aad::empty(), &mut body)
            .unwrap();
        client.header.encrypt(&mut separate);
        let mut packet = separate.to_vec();
        packet.extend(body);
        packet
    }

    #[test]
    fn clocks_are_bounded_in_both_directions() {
        assert!(valid_timestamp(30, 0).is_ok());
        assert!(valid_timestamp(0, 30).is_ok());
        assert!(valid_timestamp(0, 31).is_err());
        assert!(valid_timestamp(u64::MAX, 0).is_err());
        assert!(valid_timestamp(31, 0).is_err());
    }

    #[test]
    fn replay_window_handles_out_of_order_wrap_boundaries_and_large_jumps() {
        let mut window = ReplayWindow::default();
        for id in [0, 63, 64, 66, 65, 67, 1023, 1024, 33] {
            assert!(window.accepts(id), "new id {id}");
            window.observe(id);
            assert!(!window.accepts(id), "duplicate id {id}");
        }
        assert!(!window.accepts(0));
        assert!(window.accepts(1));
        window.observe(1);
        assert!(!window.accepts(1));
        window.observe(1_000_000);
        assert!(!window.accepts(1024));
        assert!(window.accepts(999_999));
        window.observe(999_999);
        assert!(!window.accepts(999_999));
    }

    #[test]
    fn udp_authentication_errors_do_not_poison_valid_packet_ids() {
        for method in [AES128, AES256] {
            let mut client = udp(method);
            let good = server_packet(
                &client,
                [3; 8],
                0,
                timestamp().unwrap(),
                client.session,
                1,
                &address(),
            );
            let mut bad = good.clone();
            *bad.last_mut().unwrap() ^= 1;
            assert!(client.decrypt(&bad).is_err());
            assert!(client.remotes.iter().all(Option::is_none));
            assert_eq!(client.decrypt(&good).unwrap(), address());
            assert_eq!(
                client.decrypt(&good).unwrap_err().to_string(),
                "Ss2022Replay"
            );
            let next = server_packet(
                &client,
                [3; 8],
                1,
                timestamp().unwrap(),
                client.session,
                1,
                &address(),
            );
            let mut damaged = next.clone();
            damaged[25] ^= 1;
            assert!(client.decrypt(&damaged).is_err());
            assert_eq!(client.decrypt(&next).unwrap(), address());
        }
    }

    #[test]
    fn udp_wrong_clock_binding_direction_address_and_reflection_are_rejected() {
        let mut client = udp(AES128);
        let now = timestamp().unwrap();
        let cases = [
            server_packet(&client, [3; 8], 0, now - 31, client.session, 1, &address()),
            server_packet(&client, [3; 8], 0, now + 60, client.session, 1, &address()),
            server_packet(&client, [3; 8], 0, now, [0; 8], 1, &address()),
            server_packet(&client, [3; 8], 0, now, client.session, 0, &address()),
            server_packet(
                &client,
                client.session,
                0,
                now,
                client.session,
                1,
                &address(),
            ),
            server_packet(
                &client,
                [3; 8],
                0,
                now,
                client.session,
                1,
                &[1, 127, 0, 0, 1, 0, 0],
            ),
        ];
        for packet in cases {
            assert!(client.decrypt(&packet).is_err());
            assert!(client.remotes.iter().all(Option::is_none));
        }
        let packet = server_packet(&client, [3; 8], 0, now, client.session, 1, &address());
        assert_eq!(client.decrypt(&packet).unwrap(), address());
        let reflected = client.encrypt(&address()).unwrap();
        assert!(client.decrypt(&reflected).is_err());
    }

    #[test]
    fn udp_server_restarts_retain_two_sessions_without_unbounded_growth() {
        let mut client = udp(AES256);
        let now = timestamp().unwrap();
        for server in [[3; 8], [4; 8]] {
            let packet = server_packet(&client, server, 0, now, client.session, 1, &address());
            assert_eq!(client.decrypt(&packet).unwrap(), address());
        }
        let third = server_packet(&client, [5; 8], 0, now, client.session, 1, &address());
        assert_eq!(
            client.decrypt(&third).unwrap_err().to_string(),
            "Ss2022SessionLimit"
        );
        // Old-session repeats cannot refresh retention because their packet ID
        // is rejected before any timestamp or retention-state update.
        let retained = client.remotes[0].as_ref().unwrap().last;
        let duplicate = server_packet(&client, [3; 8], 0, now, client.session, 1, &address());
        assert!(client.decrypt(&duplicate).is_err());
        assert_eq!(client.remotes[0].as_ref().unwrap().last, retained);
        client.remotes[0].as_mut().unwrap().last = Instant::now() - Duration::from_secs(61);
        assert_eq!(client.decrypt(&third).unwrap(), address());
        assert_eq!(client.remotes.iter().flatten().count(), 2);
    }

    #[test]
    fn nonces_packet_ids_and_datagram_sizes_never_wrap_or_grow_unbounded() {
        let mut cipher = Cipher::new(&aead::AES_128_GCM, &[7; 16], &[2; 16]).unwrap();
        cipher.nonce = [255; 12];
        cipher.seal(&mut vec![1]).unwrap();
        assert_eq!(
            cipher.seal(&mut vec![1]).unwrap_err().to_string(),
            "Ss2022NonceExhausted"
        );
        let mut client = udp(AES128);
        client.next_packet = u64::MAX;
        client.encrypt(&address()).unwrap();
        assert_eq!(
            client.encrypt(&address()).unwrap_err().to_string(),
            "Ss2022PacketIdExhausted"
        );
        assert!(client.decrypt(&vec![0; MAX_DATAGRAM + 1]).is_err());
        let mut oversized = address();
        oversized.resize(MAX_DATAGRAM, 0);
        assert!(udp(AES256).encrypt(&oversized).is_err());
    }

    fn stream(inner: BoxStream) -> Stream {
        let master = Zeroizing::new(vec![7; 16]);
        Stream {
            inner,
            algorithm: &aead::AES_128_GCM,
            sender: Cipher::new(&aead::AES_128_GCM, &master, &[1; 16]).unwrap(),
            master,
            request_salt: vec![1; 16],
            receiver: None,
            pending: Vec::new(),
            sent: 0,
            stage: Stage::Header,
            input: Vec::new(),
            needed: 16 * 2 + 11 + TAG,
            plain: Vec::new(),
            consumed: 0,
            limit: Duration::from_millis(40),
            progress_deadline: None,
            failed: false,
            eof: false,
            write_closed: false,
        }
    }

    fn response(direction: u8, clock: u64, salt: [u8; 16], payload: &[u8]) -> Vec<u8> {
        let server_salt = [2; 16];
        let mut cipher = Cipher::new(&aead::AES_128_GCM, &[7; 16], &server_salt).unwrap();
        let mut fixed = vec![direction];
        fixed.extend(clock.to_be_bytes());
        fixed.extend(salt);
        fixed.extend((payload.len() as u16).to_be_bytes());
        cipher.seal(&mut fixed).unwrap();
        let mut body = payload.to_vec();
        cipher.seal(&mut body).unwrap();
        let mut wire = server_salt.to_vec();
        wire.extend(fixed);
        wire.extend(body);
        wire
    }

    #[tokio::test]
    async fn tcp_response_binding_type_timestamp_and_aead_are_required_before_delivery() {
        let now = timestamp().unwrap();
        let mut damaged = response(1, now, [1; 16], b"secret");
        *damaged.last_mut().unwrap() ^= 1;
        for wire in [
            response(0, now, [1; 16], b"secret"),
            response(1, now, [8; 16], b"secret"),
            response(1, now - 31, [1; 16], b"secret"),
            damaged,
        ] {
            let (client, mut server) = tokio::io::duplex(1024);
            server.write_all(&wire).await.unwrap();
            let mut client = stream(Box::new(client));
            let mut output = [0; 8];
            assert!(client.read(&mut output).await.is_err());
            assert_eq!(output, [0; 8]);
            assert!(client.read(&mut output).await.is_err());
        }
    }

    #[tokio::test]
    async fn tcp_accepts_full_65535_byte_payload_and_record_boundary_fin() {
        let payload = vec![19; MAX_PAYLOAD];
        let wire = response(1, timestamp().unwrap(), [1; 16], &payload);
        let (client, mut server) = tokio::io::duplex(131_072);
        server.write_all(&wire).await.unwrap();
        server.shutdown().await.unwrap();
        let mut client = stream(Box::new(client));
        let mut result = Vec::new();
        client.read_to_end(&mut result).await.unwrap();
        assert_eq!(result, payload);
    }

    #[tokio::test]
    async fn tcp_partial_initial_header_and_payload_truncation_are_sticky_errors() {
        let wire = response(1, timestamp().unwrap(), [1; 16], b"hello");
        for size in [1, 58, wire.len() - 1] {
            let (client, mut server) = tokio::io::duplex(1024);
            server.write_all(&wire[..size]).await.unwrap();
            server.shutdown().await.unwrap();
            let mut client = stream(Box::new(client));
            assert!(client.read(&mut [0; 5]).await.is_err());
            assert!(client.read(&mut [0; 5]).await.is_err());
        }
    }

    #[tokio::test(start_paused = true)]
    async fn tcp_partial_record_timeout_is_bounded_but_idle_read_is_preserved() {
        let wire = response(1, timestamp().unwrap(), [1; 16], b"hello");
        let (client, mut server) = tokio::io::duplex(1024);
        let mut client = stream(Box::new(client));
        assert!(
            tokio::time::timeout(Duration::from_secs(1), client.read(&mut [0; 5]))
                .await
                .is_err()
        );
        server.write_all(&wire[..wire.len() - 1]).await.unwrap();
        let err = client.read(&mut [0; 5]).await.unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::TimedOut);
    }
}
