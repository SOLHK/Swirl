//! VMess wire v1 with AEAD authentication (alterId=0), owned by Swirl.
//!
//! The authenticated request/response and body codec follow the independent
//! Xray v26.10.21 wire implementation. TLS and WebSocket remain generic outer
//! transports. No reference proxy executable participates in this client.
use aes::cipher::{BlockEncrypt, KeyInit};
use md5::{Digest, Md5};
use ring::{
    aead,
    rand::{SecureRandom, SystemRandom},
};
use sha2::Sha256;
use std::{
    future::Future,
    io,
    net::IpAddr,
    pin::Pin,
    task::{Context, Poll, ready},
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use swirl_transport::BoxStream;
use tokio::io::{AsyncRead, AsyncWrite, AsyncWriteExt, BufReader, ReadBuf};
use zeroize::Zeroizing;

const MAX_PAYLOAD: usize = 16 * 1024;
const MAX_RESPONSE_HEADER: usize = 259;
const TAG: usize = 16;

fn invalid() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "VmessAuthenticationOrFraming")
}

fn algorithm(security: &str) -> crate::Result<(u8, &'static aead::Algorithm)> {
    match security {
        "auto" | "aes-128-gcm" => Ok((3, &aead::AES_128_GCM)),
        "chacha20-poly1305" => Ok((4, &aead::CHACHA20_POLY1305)),
        _ => Err("VmessCipherUnsupported"),
    }
}

pub(crate) fn validate(uuid: &str, alter_id: u32, security: &str) -> crate::Result<()> {
    if swirl_subscription::uuid_bytes(uuid).is_none() {
        return Err("VmessUuid");
    }
    if alter_id != 0 {
        return Err("VmessLegacyAlterIdUnsupported");
    }
    algorithm(security)?;
    Ok(())
}

// VMess specifies recursively nested HMAC-SHA256, not HKDF. Each layer uses
// the previous HMAC as its hash function; pads therefore retain the SHA256
// block size (64) and output size (32). The primitive is RustCrypto SHA256.
fn nested_hmac(keys: &[&[u8]], message: &[u8]) -> [u8; 32] {
    let Some((key, parents)) = keys.split_last() else {
        return Sha256::digest(message).into();
    };
    let mut normalized = Zeroizing::new([0u8; 64]);
    if key.len() > 64 {
        normalized[..32].copy_from_slice(&nested_hmac(parents, key));
    } else {
        normalized[..key.len()].copy_from_slice(key);
    }
    let mut inner = Zeroizing::new(Vec::with_capacity(64 + message.len()));
    inner.extend(normalized.iter().map(|b| b ^ 0x36));
    inner.extend_from_slice(message);
    let digest = Zeroizing::new(nested_hmac(parents, &inner));
    let mut outer = Zeroizing::new(Vec::with_capacity(96));
    outer.extend(normalized.iter().map(|b| b ^ 0x5c));
    outer.extend_from_slice(&*digest);
    nested_hmac(parents, &outer)
}

fn kdf(key: &[u8], path: &[&[u8]]) -> Zeroizing<[u8; 32]> {
    let mut keys = Vec::with_capacity(path.len() + 1);
    keys.push(b"VMess AEAD KDF".as_slice());
    keys.extend_from_slice(path);
    Zeroizing::new(nested_hmac(&keys, key))
}

fn nonce(bytes: &[u8]) -> io::Result<aead::Nonce> {
    let value: [u8; 12] = bytes.try_into().map_err(|_| invalid())?;
    Ok(aead::Nonce::assume_unique_for_key(value))
}

fn aes_seal(key: &[u8], iv: &[u8], aad: &[u8], plain: &mut Vec<u8>) -> io::Result<()> {
    let cipher = aead::LessSafeKey::new(
        aead::UnboundKey::new(&aead::AES_128_GCM, key).map_err(|_| invalid())?,
    );
    cipher
        .seal_in_place_append_tag(nonce(iv)?, aead::Aad::from(aad), plain)
        .map_err(|_| invalid())
}

fn aes_open(key: &[u8], iv: &[u8], body: &mut Vec<u8>) -> io::Result<()> {
    let cipher = aead::LessSafeKey::new(
        aead::UnboundKey::new(&aead::AES_128_GCM, key).map_err(|_| invalid())?,
    );
    let count = cipher
        .open_in_place(nonce(iv)?, aead::Aad::empty(), body)
        .map_err(|_| invalid())?
        .len();
    body.truncate(count);
    Ok(())
}

fn crc32(bytes: &[u8]) -> u32 {
    let mut value = !0u32;
    for byte in bytes {
        value ^= u32::from(*byte);
        for _ in 0..8 {
            value = (value >> 1) ^ (0xedb8_8320 & (0u32.wrapping_sub(value & 1)));
        }
    }
    !value
}

fn fnv1a(bytes: &[u8]) -> u32 {
    bytes.iter().fold(0x811c_9dc5u32, |hash, byte| {
        (hash ^ u32::from(*byte)).wrapping_mul(0x0100_0193)
    })
}

struct Session {
    request_key: Zeroizing<[u8; 16]>,
    request_iv: Zeroizing<[u8; 16]>,
    response_key: Zeroizing<[u8; 16]>,
    response_iv: Zeroizing<[u8; 16]>,
    response_byte: u8,
    algorithm: &'static aead::Algorithm,
    security: u8,
}

impl Session {
    fn new(security: &str) -> crate::Result<Self> {
        let (security, algorithm) = algorithm(security)?;
        let mut random = Zeroizing::new([0; 33]);
        SystemRandom::new()
            .fill(&mut *random)
            .map_err(|_| "VmessRandom")?;
        let mut request_key = Zeroizing::new([0; 16]);
        let mut request_iv = Zeroizing::new([0; 16]);
        request_key.copy_from_slice(&random[..16]);
        request_iv.copy_from_slice(&random[16..32]);
        let mut response_key = Zeroizing::new([0; 16]);
        let mut response_iv = Zeroizing::new([0; 16]);
        response_key.copy_from_slice(&Sha256::digest(*request_key)[..16]);
        response_iv.copy_from_slice(&Sha256::digest(*request_iv)[..16]);
        Ok(Self {
            request_key,
            request_iv,
            response_key,
            response_iv,
            response_byte: random[32],
            algorithm,
            security,
        })
    }

    fn request(&self, uuid: &str, target: &crate::Target) -> crate::Result<Vec<u8>> {
        let uuid = swirl_subscription::uuid_bytes(uuid).ok_or("VmessUuid")?;
        if target.port == 0 || !swirl_subscription::valid_host(&target.host) {
            return Err("InvalidTarget");
        }
        let mut random = [0u8; 28];
        SystemRandom::new()
            .fill(&mut random)
            .map_err(|_| "VmessRandom")?;
        let padding = usize::from(random[12] & 0x0f);
        let mut header = Zeroizing::new(vec![1]);
        header.extend_from_slice(&*self.request_iv);
        header.extend_from_slice(&*self.request_key);
        // Chunk stream, without optional length masking/global padding. These
        // negotiated flags apply identically to both body directions.
        header.extend([
            self.response_byte,
            0x01,
            (padding as u8) << 4 | self.security,
            0,
            1,
        ]);
        header.extend(target.port.to_be_bytes());
        match target.host.parse::<IpAddr>() {
            Ok(IpAddr::V4(ip)) => {
                header.push(1);
                header.extend(ip.octets());
            }
            Ok(IpAddr::V6(ip)) => {
                header.push(3);
                header.extend(ip.octets());
            }
            Err(_) => {
                header.extend([2, target.host.len() as u8]);
                header.extend(target.host.as_bytes());
            }
        }
        header.extend_from_slice(&random[13..13 + padding]);
        let checksum = fnv1a(&header);
        header.extend(checksum.to_be_bytes());

        let mut command = Md5::new();
        command.update(uuid);
        command.update(b"c48619fe-8f02-49e0-b9e9-edf763e17e21");
        let command = Zeroizing::new(<[u8; 16]>::from(command.finalize()));
        let auth_key = kdf(&*command, &[b"AES Auth ID Encryption"]);
        let seconds = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "VmessClock")?
            .as_secs();
        if seconds > i64::MAX as u64 {
            return Err("VmessClock");
        }
        let mut auth = aes::cipher::Block::<aes::Aes128>::default();
        auth[..8].copy_from_slice(&seconds.to_be_bytes());
        auth[8..12].copy_from_slice(&random[..4]);
        let checksum = crc32(&auth[..12]);
        auth[12..].copy_from_slice(&checksum.to_be_bytes());
        aes::Aes128::new_from_slice(&auth_key[..16])
            .map_err(|_| "VmessCrypto")?
            .encrypt_block(&mut auth);
        let connection_nonce = &random[4..12];
        let mut length = (header.len() as u16).to_be_bytes().to_vec();
        let length_key = kdf(
            &*command,
            &[b"VMess Header AEAD Key_Length", &auth, connection_nonce],
        );
        let length_iv = kdf(
            &*command,
            &[b"VMess Header AEAD Nonce_Length", &auth, connection_nonce],
        );
        aes_seal(&length_key[..16], &length_iv[..12], &auth, &mut length)
            .map_err(|_| "VmessCrypto")?;
        let payload_key = kdf(
            &*command,
            &[b"VMess Header AEAD Key", &auth, connection_nonce],
        );
        let payload_iv = kdf(
            &*command,
            &[b"VMess Header AEAD Nonce", &auth, connection_nonce],
        );
        aes_seal(&payload_key[..16], &payload_iv[..12], &auth, &mut header)
            .map_err(|_| "VmessCrypto")?;
        let mut wire = Vec::with_capacity(42 + header.len());
        wire.extend_from_slice(&auth);
        wire.extend(length);
        wire.extend(connection_nonce);
        wire.extend_from_slice(&header);
        Ok(wire)
    }
}

struct BodyCipher {
    cipher: aead::LessSafeKey,
    iv: [u8; 12],
    next: u32,
}

impl BodyCipher {
    fn new(algorithm: &'static aead::Algorithm, key: &[u8], iv: &[u8]) -> io::Result<Self> {
        let mut chacha = Zeroizing::new([0; 32]);
        let key = if algorithm == &aead::CHACHA20_POLY1305 {
            chacha[..16].copy_from_slice(&Md5::digest(key));
            let second = Md5::digest(&chacha[..16]);
            chacha[16..].copy_from_slice(&second);
            &chacha[..]
        } else {
            key
        };
        Ok(Self {
            cipher: aead::LessSafeKey::new(
                aead::UnboundKey::new(algorithm, key).map_err(|_| invalid())?,
            ),
            iv: iv[..12].try_into().map_err(|_| invalid())?,
            next: 0,
        })
    }

    fn next_nonce(&mut self) -> io::Result<aead::Nonce> {
        // The wire counter is 16 bits. Never wrap and reuse an AEAD nonce.
        if self.next > u16::MAX as u32 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "VmessNonceExhausted",
            ));
        }
        self.iv[..2].copy_from_slice(&(self.next as u16).to_be_bytes());
        self.next += 1;
        Ok(aead::Nonce::assume_unique_for_key(self.iv))
    }

    fn seal(&mut self, bytes: &mut Vec<u8>) -> io::Result<()> {
        let iv = self.next_nonce()?;
        self.cipher
            .seal_in_place_append_tag(iv, aead::Aad::empty(), bytes)
            .map_err(|_| invalid())
    }

    fn open(&mut self, bytes: &mut Vec<u8>) -> io::Result<()> {
        let iv = self.next_nonce()?;
        let length = self
            .cipher
            .open_in_place(iv, aead::Aad::empty(), bytes)
            .map_err(|_| invalid())?
            .len();
        bytes.truncate(length);
        Ok(())
    }
}

enum ReadStage {
    HeaderLength,
    Header,
    Length,
    Payload,
}

struct Stream {
    inner: BufReader<BoxStream>,
    session: Session,
    sender: BodyCipher,
    receiver: BodyCipher,
    stage: ReadStage,
    needed: usize,
    input: Vec<u8>,
    plain: Vec<u8>,
    consumed: usize,
    pending: Vec<u8>,
    sent: usize,
    read_closed: bool,
    write_closed: bool,
    transport_closed: bool,
    failed: bool,
    limit: Duration,
    header_deadline: Option<Pin<Box<tokio::time::Sleep>>>,
}

impl Stream {
    fn new(inner: BoxStream, session: Session, limit: Duration) -> io::Result<Self> {
        let sender = BodyCipher::new(
            session.algorithm,
            &*session.request_key,
            &*session.request_iv,
        )?;
        let receiver = BodyCipher::new(
            session.algorithm,
            &*session.response_key,
            &*session.response_iv,
        )?;
        Ok(Self {
            inner: BufReader::with_capacity(4096, inner),
            session,
            sender,
            receiver,
            stage: ReadStage::HeaderLength,
            needed: 18,
            input: Vec::new(),
            plain: Vec::new(),
            consumed: 0,
            pending: Vec::new(),
            sent: 0,
            read_closed: false,
            write_closed: false,
            transport_closed: false,
            failed: false,
            limit,
            header_deadline: None,
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

    fn finish_transport(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.read_closed && self.write_closed && !self.transport_closed {
            ready!(self.drain(cx))?;
            ready!(Pin::new(&mut self.inner).poll_shutdown(cx))?;
            self.transport_closed = true;
        }
        Poll::Ready(Ok(()))
    }

    fn frame(&mut self, bytes: &[u8]) -> io::Result<()> {
        let mut body = bytes.to_vec();
        self.sender.seal(&mut body)?;
        self.pending.extend((body.len() as u16).to_be_bytes());
        self.pending.extend(body);
        Ok(())
    }

    fn read(&mut self, cx: &mut Context<'_>, out: &mut ReadBuf<'_>) -> Poll<io::Result<()>> {
        if out.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        if self.read_closed {
            return self.finish_transport(cx);
        }
        for _ in 0..8 {
            if self.consumed < self.plain.len() {
                let n = out.remaining().min(self.plain.len() - self.consumed);
                out.put_slice(&self.plain[self.consumed..self.consumed + n]);
                self.consumed += n;
                return Poll::Ready(Ok(()));
            }
            while self.input.len() < self.needed {
                if let Some(deadline) = &mut self.header_deadline
                    && deadline.as_mut().poll(cx).is_ready()
                {
                    return Poll::Ready(Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        "VmessResponseTimeout",
                    )));
                }
                let mut data = [0; MAX_PAYLOAD];
                let mut buffer =
                    ReadBuf::new(&mut data[..(self.needed - self.input.len()).min(MAX_PAYLOAD)]);
                ready!(Pin::new(&mut self.inner).poll_read(cx, &mut buffer))?;
                if buffer.filled().is_empty() {
                    // A transport FIN without an authenticated VMess terminal
                    // record is truncation, not an accepted normal close.
                    return Poll::Ready(Err(io::ErrorKind::UnexpectedEof.into()));
                }
                if matches!(self.stage, ReadStage::HeaderLength | ReadStage::Header)
                    && self.header_deadline.is_none()
                {
                    self.header_deadline = Some(Box::pin(tokio::time::sleep(self.limit)));
                }
                self.input.extend_from_slice(buffer.filled());
            }
            match self.stage {
                ReadStage::HeaderLength => {
                    let key = kdf(&*self.session.response_key, &[b"AEAD Resp Header Len Key"]);
                    let iv = kdf(&*self.session.response_iv, &[b"AEAD Resp Header Len IV"]);
                    aes_open(&key[..16], &iv[..12], &mut self.input)?;
                    let length = usize::from(u16::from_be_bytes([self.input[0], self.input[1]]));
                    if !(4..=MAX_RESPONSE_HEADER).contains(&length) {
                        return Poll::Ready(Err(invalid()));
                    }
                    self.stage = ReadStage::Header;
                    self.needed = length + TAG;
                }
                ReadStage::Header => {
                    let key = kdf(&*self.session.response_key, &[b"AEAD Resp Header Key"]);
                    let iv = kdf(&*self.session.response_iv, &[b"AEAD Resp Header IV"]);
                    aes_open(&key[..16], &iv[..12], &mut self.input)?;
                    // VMess dynamic user/connection-reuse commands are not
                    // supported; reject instead of silently applying them.
                    if self.input != [self.session.response_byte, 0, 0, 0] {
                        return Poll::Ready(Err(invalid()));
                    }
                    self.header_deadline = None;
                    self.stage = ReadStage::Length;
                    self.needed = 2;
                }
                ReadStage::Length => {
                    let length = usize::from(u16::from_be_bytes([self.input[0], self.input[1]]));
                    if length < TAG {
                        return Poll::Ready(Err(invalid()));
                    }
                    self.stage = ReadStage::Payload;
                    self.needed = length;
                }
                ReadStage::Payload => {
                    self.receiver.open(&mut self.input)?;
                    if self.input.is_empty() {
                        self.read_closed = true;
                        return self.finish_transport(cx);
                    }
                    self.plain = std::mem::take(&mut self.input);
                    self.consumed = 0;
                    self.stage = ReadStage::Length;
                    self.needed = 2;
                }
            }
            self.input.clear();
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
        let count = bytes.len().min(MAX_PAYLOAD);
        if let Err(error) = self.frame(&bytes[..count]) {
            self.failed = true;
            return Poll::Ready(Err(error));
        }
        Poll::Ready(Ok(count))
    }

    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.failed {
            return Poll::Ready(Err(invalid()));
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
        if self.failed {
            return Poll::Ready(Err(invalid()));
        }
        if !self.write_closed {
            if let Err(error) = ready!(self.drain(cx)) {
                self.failed = true;
                return Poll::Ready(Err(error));
            }
            if let Err(error) = self.frame(&[]) {
                self.failed = true;
                return Poll::Ready(Err(error));
            }
            self.write_closed = true;
        }
        ready!(self.as_mut().poll_flush(cx))?;
        // VMess's authenticated empty record half-closes the logical upload.
        // Retain the outer TLS/WS connection until the authenticated download
        // EOF arrives, so the server can still deliver its final response.
        let result = self.finish_transport(cx);
        if matches!(result, Poll::Ready(Err(_))) {
            self.failed = true;
        }
        result
    }
}

pub(crate) async fn connect(
    mut stream: BoxStream,
    uuid: &str,
    alter_id: u32,
    security: &str,
    target: &crate::Target,
    response_timeout: Duration,
) -> crate::Result<BoxStream> {
    validate(uuid, alter_id, security)?;
    let session = Session::new(security)?;
    let request = session.request(uuid, target)?;
    stream
        .write_all(&request)
        .await
        .map_err(|_| "VmessHandshakeWrite")?;
    stream.flush().await.map_err(|_| "VmessHandshakeWrite")?;
    // The server can wait for application bytes before returning a response.
    // This return means request written, never that authentication succeeded.
    Ok(Box::new(
        Stream::new(stream, session, response_timeout).map_err(|_| "VmessCrypto")?,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    const UUID: &str = "00112233-4455-6677-8899-aabbccddeeff";

    #[test]
    fn unsupported_security_and_legacy_authentication_are_not_downgraded() {
        for security in [
            "none",
            "zero",
            "aes-128-cfb",
            "aes-256-gcm",
            "chacha20-ietf-poly1305",
            "",
        ] {
            assert_eq!(validate(UUID, 0, security), Err("VmessCipherUnsupported"));
        }
        assert_eq!(
            validate(UUID, 1, "auto"),
            Err("VmessLegacyAlterIdUnsupported")
        );
        assert_eq!(validate("malformed", 0, "auto"), Err("VmessUuid"));
        for security in ["auto", "aes-128-gcm", "chacha20-poly1305"] {
            assert_eq!(validate(UUID, 0, security), Ok(()));
        }
    }

    #[test]
    fn checksum_known_answers() {
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
        assert_eq!(fnv1a(b"hello"), 0x4f9f_2cab);
    }

    #[test]
    fn hmac_primitive_matches_rfc4231_case_one() {
        // RFC 4231 section 4.2, independent known answer for the HMAC layer.
        let actual = nested_hmac(&[&[0x0b; 20]], b"Hi There");
        assert_eq!(
            actual,
            [
                0xb0, 0x34, 0x4c, 0x61, 0xd8, 0xdb, 0x38, 0x53, 0x5c, 0xa8, 0xaf, 0xce, 0xaf, 0x0b,
                0xf1, 0x2b, 0x88, 0x1d, 0xc2, 0x00, 0xc9, 0x83, 0x3d, 0xa7, 0x26, 0xe9, 0x37, 0x6c,
                0x2e, 0x32, 0xcf, 0xf7,
            ]
        );
    }

    #[test]
    fn body_nonce_exhaustion_never_reuses_a_nonce() {
        for algorithm in [&aead::AES_128_GCM, &aead::CHACHA20_POLY1305] {
            let mut cipher = BodyCipher::new(algorithm, &[1; 16], &[2; 16]).unwrap();
            cipher.next = u16::MAX as u32;
            cipher.seal(&mut vec![1, 2]).unwrap();
            assert_eq!(
                cipher.seal(&mut vec![]).unwrap_err().to_string(),
                "VmessNonceExhausted"
            );
        }
    }

    fn response(session: &Session, plain: &[u8]) -> Vec<u8> {
        let mut length = (plain.len() as u16).to_be_bytes().to_vec();
        let mut body = plain.to_vec();
        let key = kdf(&*session.response_key, &[b"AEAD Resp Header Len Key"]);
        let iv = kdf(&*session.response_iv, &[b"AEAD Resp Header Len IV"]);
        aes_seal(&key[..16], &iv[..12], &[], &mut length).unwrap();
        let key = kdf(&*session.response_key, &[b"AEAD Resp Header Key"]);
        let iv = kdf(&*session.response_iv, &[b"AEAD Resp Header IV"]);
        aes_seal(&key[..16], &iv[..12], &[], &mut body).unwrap();
        length.extend(body);
        length
    }

    #[tokio::test]
    async fn altered_response_header_fails_and_failure_is_sticky() {
        let (client, mut peer) = tokio::io::duplex(4096);
        let session = Session::new("auto").unwrap();
        let mut wire = response(&session, &[session.response_byte, 0, 0, 0]);
        wire[0] ^= 1;
        let mut client = Stream::new(Box::new(client), session, Duration::from_secs(1)).unwrap();
        peer.write_all(&wire).await.unwrap();
        assert_eq!(
            client.read_u8().await.unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );
        assert!(client.write_all(b"after failure").await.is_err());
    }

    #[tokio::test]
    async fn response_header_length_is_bounded_before_allocation() {
        for size in [0, 3, 260, 65535] {
            let (client, mut peer) = tokio::io::duplex(64);
            let session = Session::new("auto").unwrap();
            let mut length = (size as u16).to_be_bytes().to_vec();
            let key = kdf(&*session.response_key, &[b"AEAD Resp Header Len Key"]);
            let iv = kdf(&*session.response_iv, &[b"AEAD Resp Header Len IV"]);
            aes_seal(&key[..16], &iv[..12], &[], &mut length).unwrap();
            let mut client =
                Stream::new(Box::new(client), session, Duration::from_secs(1)).unwrap();
            peer.write_all(&length).await.unwrap();
            assert_eq!(
                client.read_u8().await.unwrap_err().kind(),
                io::ErrorKind::InvalidData
            );
            assert!(client.input.capacity() < 1024);
        }
    }

    #[tokio::test]
    async fn partial_response_times_out_but_idle_application_does_not() {
        let (client, mut peer) = tokio::io::duplex(128);
        let session = Session::new("auto").unwrap();
        let mut client = Stream::new(Box::new(client), session, Duration::from_millis(10)).unwrap();
        assert!(
            tokio::time::timeout(Duration::from_millis(30), client.read_u8())
                .await
                .is_err()
        );
        peer.write_all(&[1]).await.unwrap();
        let error = tokio::time::timeout(Duration::from_secs(1), client.read_u8())
            .await
            .unwrap()
            .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::TimedOut);
    }

    #[tokio::test]
    async fn truncated_body_and_unauthenticated_eof_are_rejected() {
        for partial in [vec![0, 1], vec![0, 16, 1, 2], vec![]] {
            let (client, mut peer) = tokio::io::duplex(4096);
            let session = Session::new("auto").unwrap();
            let mut wire = response(&session, &[session.response_byte, 0, 0, 0]);
            wire.extend(partial);
            let mut client =
                Stream::new(Box::new(client), session, Duration::from_secs(1)).unwrap();
            peer.write_all(&wire).await.unwrap();
            peer.shutdown().await.unwrap();
            assert!(client.read_u8().await.is_err());
        }
    }

    #[tokio::test]
    async fn altered_data_or_terminal_tags_cannot_be_accepted_as_payload_or_eof() {
        for plain in [b"payload".as_slice(), &[]] {
            let (client, mut peer) = tokio::io::duplex(4096);
            let session = Session::new("auto").unwrap();
            let mut wire = response(&session, &[session.response_byte, 0, 0, 0]);
            let mut cipher = BodyCipher::new(
                session.algorithm,
                &*session.response_key,
                &*session.response_iv,
            )
            .unwrap();
            let mut body = plain.to_vec();
            cipher.seal(&mut body).unwrap();
            *body.last_mut().unwrap() ^= 1;
            wire.extend((body.len() as u16).to_be_bytes());
            wire.extend(body);
            let mut client =
                Stream::new(Box::new(client), session, Duration::from_secs(1)).unwrap();
            peer.write_all(&wire).await.unwrap();
            assert_eq!(
                client.read_u8().await.unwrap_err().kind(),
                io::ErrorKind::InvalidData
            );
        }
    }

    #[tokio::test]
    async fn logical_half_close_retains_download_and_authenticates_terminal_record() {
        for algorithm in ["aes-128-gcm", "chacha20-poly1305"] {
            let (client, mut peer) = tokio::io::duplex(4096);
            let session = Session::new(algorithm).unwrap();
            let mut wire = response(&session, &[session.response_byte, 0, 0, 0]);
            let mut cipher = BodyCipher::new(
                session.algorithm,
                &*session.response_key,
                &*session.response_iv,
            )
            .unwrap();
            for plain in [b"late response".as_slice(), &[]] {
                let mut body = plain.to_vec();
                cipher.seal(&mut body).unwrap();
                wire.extend((body.len() as u16).to_be_bytes());
                wire.extend(body);
            }
            let mut client =
                Stream::new(Box::new(client), session, Duration::from_secs(1)).unwrap();
            client.shutdown().await.unwrap();
            let mut terminal = [0; 18];
            peer.read_exact(&mut terminal).await.unwrap();
            assert_eq!(&terminal[..2], &[0, 16]);
            assert!(client.write_all(b"too late").await.is_err());
            peer.write_all(&wire).await.unwrap();
            let mut got = Vec::new();
            client.read_to_end(&mut got).await.unwrap();
            assert_eq!(got, b"late response");
            assert_eq!(
                peer.read_u8().await.unwrap_err().kind(),
                io::ErrorKind::UnexpectedEof
            );
        }
    }
}
