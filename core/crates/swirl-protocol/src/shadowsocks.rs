//! SIP004/SIP007 TCP framing. Crypto primitives are ring and RustCrypto MD5.
//! HTTP obfs is framing only, not TLS or WebSocket security.
use base64::{Engine, engine::general_purpose::STANDARD};
use md5::{Digest, Md5};
use ring::{
    aead, hkdf,
    rand::{SecureRandom, SystemRandom},
};
use std::{
    collections::{HashSet, VecDeque},
    io,
    pin::Pin,
    sync::{Mutex, OnceLock},
    task::{Context, Poll, ready},
    time::{Duration, Instant},
};
use swirl_transport::BoxStream;
use tokio::io::{AsyncRead, AsyncWrite, BufReader, ReadBuf};
use zeroize::Zeroizing;

const MAX_CHUNK: usize = 0x3fff;
fn invalid() -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        "Shadowsocks framing or authentication failed",
    )
}
fn algorithm(cipher: &str) -> io::Result<&'static aead::Algorithm> {
    match cipher {
        "aes-128-gcm" => Ok(&aead::AES_128_GCM),
        "aes-256-gcm" => Ok(&aead::AES_256_GCM),
        "chacha20-ietf-poly1305" => Ok(&aead::CHACHA20_POLY1305),
        _ => Err(invalid()),
    }
}
fn master(password: &str, length: usize) -> Zeroizing<Vec<u8>> {
    let mut key = Zeroizing::new(Vec::new());
    let mut previous = Zeroizing::new(Vec::new());
    while key.len() < length {
        let mut digest = Md5::new();
        digest.update(&*previous);
        digest.update(password.as_bytes());
        *previous = digest.finalize().to_vec();
        key.extend_from_slice(&previous);
    }
    key.truncate(length);
    key
}
struct KeyLength(usize);
impl hkdf::KeyType for KeyLength {
    fn len(&self) -> usize {
        self.0
    }
}
struct Cipher {
    key: aead::LessSafeKey,
    nonce: [u8; 12],
    exhausted: bool,
}
impl Cipher {
    fn new(algorithm: &'static aead::Algorithm, master: &[u8], salt: &[u8]) -> io::Result<Self> {
        let prk = hkdf::Salt::new(hkdf::HKDF_SHA1_FOR_LEGACY_USE_ONLY, salt).extract(master);
        let mut bytes = Zeroizing::new(vec![0; algorithm.key_len()]);
        prk.expand(&[b"ss-subkey"], KeyLength(algorithm.key_len()))
            .map_err(|_| invalid())?
            .fill(&mut bytes)
            .map_err(|_| invalid())?;
        Ok(Self {
            key: aead::LessSafeKey::new(
                aead::UnboundKey::new(algorithm, &bytes).map_err(|_| invalid())?,
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
            let (n, overflow) = byte.overflowing_add(1);
            *byte = n;
            if !overflow {
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
        let len = self
            .key
            .open_in_place(nonce, aead::Aad::empty(), bytes)
            .map_err(|_| invalid())?
            .len();
        bytes.truncate(len);
        Ok(())
    }
}

// Process-local replay window: ten minutes, fail closed at capacity. No eviction
// of unexpired entries. Stored digests reveal neither passwords nor peer hosts.
#[derive(Default)]
struct Salts {
    entries: VecDeque<(Instant, [u8; 32])>,
    seen: HashSet<[u8; 32]>,
}
fn remember(master: &[u8], salt: &[u8]) -> io::Result<()> {
    static SALTS: OnceLock<Mutex<Salts>> = OnceLock::new();
    remember_in(&SALTS, 600, master, salt)
}
fn remember_udp(master: &[u8], salt: &[u8]) -> io::Result<()> {
    static SALTS: OnceLock<Mutex<Salts>> = OnceLock::new();
    remember_in(&SALTS, 30, master, salt)
}
fn remember_in(
    store: &OnceLock<Mutex<Salts>>,
    seconds: u64,
    master: &[u8],
    salt: &[u8],
) -> io::Result<()> {
    let mut hash = ring::digest::Context::new(&ring::digest::SHA256);
    hash.update(master);
    hash.update(salt);
    let value: [u8; 32] = hash.finish().as_ref().try_into().map_err(|_| invalid())?;
    let mut salts = store
        .get_or_init(|| Mutex::new(Salts::default()))
        .lock()
        .map_err(|_| invalid())?;
    let now = Instant::now();
    while salts
        .entries
        .front()
        .is_some_and(|(time, _)| now.duration_since(*time) > Duration::from_secs(seconds))
    {
        if let Some((_, digest)) = salts.entries.pop_front() {
            salts.seen.remove(&digest);
        }
    }
    if salts.entries.len() >= 65536 || salts.seen.contains(&value) {
        return Err(invalid());
    }
    salts.entries.push_back((now, value));
    salts.seen.insert(value);
    Ok(())
}

pub fn encrypt_datagram(password: &str, cipher: &str, plain: &[u8]) -> io::Result<Vec<u8>> {
    let algorithm = algorithm(cipher)?;
    if plain.len() + algorithm.key_len() + 16 > 65507 {
        return Err(invalid());
    }
    let master = master(password, algorithm.key_len());
    let mut salt = vec![0; algorithm.key_len()];
    SystemRandom::new().fill(&mut salt).map_err(|_| invalid())?;
    remember_udp(&master, &salt)?;
    let mut body = plain.to_vec();
    Cipher::new(algorithm, &master, &salt)?.seal(&mut body)?;
    salt.extend(body);
    Ok(salt)
}
pub fn decrypt_datagram(password: &str, cipher: &str, wire: &[u8]) -> io::Result<Vec<u8>> {
    let algorithm = algorithm(cipher)?;
    if wire.len() < algorithm.key_len() + 16 || wire.len() > 65507 {
        return Err(invalid());
    }
    let master = master(password, algorithm.key_len());
    let (salt, encrypted) = wire.split_at(algorithm.key_len());
    let mut body = encrypted.to_vec();
    Cipher::new(algorithm, &master, salt)?.open(&mut body)?;
    remember_udp(&master, salt)?;
    Ok(body)
}

enum Stage {
    Salt,
    Length,
    Payload,
}
pub struct Stream {
    inner: BufReader<BoxStream>,
    algorithm: &'static aead::Algorithm,
    master: Zeroizing<Vec<u8>>,
    sender: Cipher,
    receiver: Option<Cipher>,
    send_salt: Vec<u8>,
    receive_salt: Vec<u8>,
    pending: Vec<u8>,
    sent: usize,
    http_host: Option<String>,
    http_port: u16,
    header: Option<Vec<u8>>,
    stage: Stage,
    input: Vec<u8>,
    needed: usize,
    plain: Vec<u8>,
    consumed: usize,
    failed: bool,
    eof: bool,
}
impl Stream {
    pub fn new(
        inner: BoxStream,
        password: &str,
        cipher: &str,
        http_host: Option<String>,
        port: u16,
    ) -> io::Result<Self> {
        let algorithm = algorithm(cipher)?;
        let master = master(password, algorithm.key_len());
        let mut salt = vec![0; algorithm.key_len()];
        SystemRandom::new().fill(&mut salt).map_err(|_| invalid())?;
        remember(&master, &salt)?;
        let sender = Cipher::new(algorithm, &master, &salt)?;
        let header = http_host.as_ref().map(|_| Vec::new());
        Ok(Self {
            // Header parsing may request one byte, but never one socket read per
            // byte. Bytes following CRLFCRLF remain buffered for AEAD parsing.
            inner: BufReader::with_capacity(4096, inner),
            algorithm,
            master,
            sender,
            receiver: None,
            send_salt: salt,
            receive_salt: Vec::new(),
            pending: Vec::new(),
            sent: 0,
            http_host,
            http_port: port,
            header,
            stage: Stage::Salt,
            input: Vec::new(),
            needed: algorithm.key_len(),
            plain: Vec::new(),
            consumed: 0,
            failed: false,
            eof: false,
        })
    }
    fn drain(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        while self.sent < self.pending.len() {
            let n = ready!(Pin::new(&mut self.inner).poll_write(cx, &self.pending[self.sent..]))?;
            if n == 0 {
                return Poll::Ready(Err(io::ErrorKind::WriteZero.into()));
            }
            self.sent += n;
        }
        self.pending.clear();
        self.sent = 0;
        Poll::Ready(Ok(()))
    }
    fn read(&mut self, cx: &mut Context<'_>, out: &mut ReadBuf<'_>) -> Poll<io::Result<()>> {
        if out.remaining() == 0 || self.eof {
            return Poll::Ready(Ok(()));
        }
        if let Some(header) = &mut self.header {
            while !header.ends_with(b"\r\n\r\n") {
                if header.len() >= 16384 {
                    return Poll::Ready(Err(invalid()));
                }
                let mut byte = [0];
                let mut buf = ReadBuf::new(&mut byte);
                ready!(Pin::new(&mut self.inner).poll_read(cx, &mut buf))?;
                if buf.filled().is_empty() {
                    return Poll::Ready(Err(io::ErrorKind::UnexpectedEof.into()));
                }
                header.push(byte[0]);
            }
            if !header.starts_with(b"HTTP/1.1 101 ") {
                return Poll::Ready(Err(invalid()));
            }
            self.header = None;
        }
        for _ in 0..32 {
            if self.consumed < self.plain.len() {
                let n = out.remaining().min(self.plain.len() - self.consumed);
                out.put_slice(&self.plain[self.consumed..self.consumed + n]);
                self.consumed += n;
                return Poll::Ready(Ok(()));
            }
            while self.input.len() < self.needed {
                let mut bytes = [0; 16384];
                let mut buf =
                    ReadBuf::new(&mut bytes[..(self.needed - self.input.len()).min(16384)]);
                ready!(Pin::new(&mut self.inner).poll_read(cx, &mut buf))?;
                if buf.filled().is_empty() {
                    if self.input.is_empty() && matches!(self.stage, Stage::Length) {
                        self.eof = true;
                        return Poll::Ready(Ok(()));
                    }
                    return Poll::Ready(Err(io::ErrorKind::UnexpectedEof.into()));
                }
                self.input.extend_from_slice(buf.filled());
            }
            match self.stage {
                Stage::Salt => {
                    // Commit only after authenticating the first length to avoid
                    // unauthenticated peers exhausting the shared replay budget.
                    self.receiver = Some(Cipher::new(self.algorithm, &self.master, &self.input)?);
                    self.receive_salt = std::mem::take(&mut self.input);
                    self.stage = Stage::Length;
                    self.needed = 18;
                }
                Stage::Length => {
                    self.receiver
                        .as_mut()
                        .ok_or_else(invalid)?
                        .open(&mut self.input)?;
                    if !self.receive_salt.is_empty() {
                        remember(&self.master, &self.receive_salt)?;
                        self.receive_salt.clear();
                    }
                    let length = u16::from_be_bytes([self.input[0], self.input[1]]) as usize;
                    if length > MAX_CHUNK {
                        return Poll::Ready(Err(invalid()));
                    }
                    self.input.clear();
                    self.stage = Stage::Payload;
                    self.needed = length + 16;
                }
                Stage::Payload => {
                    self.receiver
                        .as_mut()
                        .ok_or_else(invalid)?
                        .open(&mut self.input)?;
                    self.plain = std::mem::take(&mut self.input);
                    self.consumed = 0;
                    self.stage = Stage::Length;
                    self.needed = 18;
                }
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
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if self.failed {
            return Poll::Ready(Err(invalid()));
        }
        let result = self.read(cx, out);
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
            return Poll::Ready(Err(invalid()));
        }
        ready!(self.drain(cx))?;
        if bytes.is_empty() {
            return Poll::Ready(Ok(0));
        }
        let n = bytes.len().min(MAX_CHUNK);
        let mut length = (n as u16).to_be_bytes().to_vec();
        self.sender.seal(&mut length)?;
        let mut payload = bytes[..n].to_vec();
        self.sender.seal(&mut payload)?;
        let mut wire = std::mem::take(&mut self.send_salt);
        wire.extend(length);
        wire.extend(payload);
        if let Some(host) = self.http_host.take() {
            let mut key = [0; 16];
            SystemRandom::new().fill(&mut key).map_err(|_| invalid())?;
            let authority = if self.http_port == 80 {
                host
            } else {
                format!("{host}:{}", self.http_port)
            };
            self.pending=format!("GET / HTTP/1.1\r\nHost: {authority}\r\nUser-Agent: curl/7.88.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {}\r\nContent-Length: {}\r\n\r\n",STANDARD.encode(key),wire.len()).into_bytes();
        }
        self.pending.extend(wire);
        Poll::Ready(Ok(n))
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        ready!(self.drain(cx))?;
        Pin::new(&mut self.inner).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        ready!(self.drain(cx))?;
        Pin::new(&mut self.inner).poll_shutdown(cx)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Counted {
        inner: tokio::io::DuplexStream,
        reads: std::sync::Arc<std::sync::atomic::AtomicUsize>,
    }
    impl AsyncRead for Counted {
        fn poll_read(
            mut self: Pin<&mut Self>,
            cx: &mut Context<'_>,
            buf: &mut ReadBuf<'_>,
        ) -> Poll<io::Result<()>> {
            self.reads
                .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            Pin::new(&mut self.inner).poll_read(cx, buf)
        }
    }
    impl AsyncWrite for Counted {
        fn poll_write(
            mut self: Pin<&mut Self>,
            cx: &mut Context<'_>,
            b: &[u8],
        ) -> Poll<io::Result<usize>> {
            Pin::new(&mut self.inner).poll_write(cx, b)
        }
        fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
            Pin::new(&mut self.inner).poll_flush(cx)
        }
        fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
            Pin::new(&mut self.inner).poll_shutdown(cx)
        }
    }
    #[tokio::test]
    async fn coalesced_http_header_and_ciphertext_are_buffered_without_loss() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let (client, mut peer) = tokio::io::duplex(4096);
        let reads = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let mut client = Stream::new(
            Box::new(Counted {
                inner: client,
                reads: reads.clone(),
            }),
            "fixture",
            "aes-128-gcm",
            Some("obfs.example".into()),
            80,
        )
        .unwrap();
        let mut salt = [0; 16];
        SystemRandom::new().fill(&mut salt).unwrap();
        let mut cipher = Cipher::new(&aead::AES_128_GCM, &master("fixture", 16), &salt).unwrap();
        let mut length = vec![0, 7];
        cipher.seal(&mut length).unwrap();
        let mut payload = b"payload".to_vec();
        cipher.seal(&mut payload).unwrap();
        let mut wire = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n".to_vec();
        wire.extend(salt);
        wire.extend(length);
        wire.extend(payload);
        peer.write_all(&wire).await.unwrap();
        let mut got = [0; 7];
        client.read_exact(&mut got).await.unwrap();
        assert_eq!(&got, b"payload");
        assert_eq!(reads.load(std::sync::atomic::Ordering::Relaxed), 1);
    }
    #[test]
    fn nonce_overflow_fails_closed() {
        let mut c = Cipher::new(&aead::AES_128_GCM, &[7; 16], &[8; 16]).unwrap();
        c.nonce = [255; 12];
        c.seal(&mut vec![1]).unwrap();
        assert!(c.seal(&mut vec![1]).is_err());
    }
    #[test]
    fn replay_is_key_scoped() {
        remember(b"synthetic-key-a", b"synthetic-salt").unwrap();
        assert!(remember(b"synthetic-key-a", b"synthetic-salt").is_err());
        remember(b"synthetic-key-b", b"synthetic-salt").unwrap();
    }
}
