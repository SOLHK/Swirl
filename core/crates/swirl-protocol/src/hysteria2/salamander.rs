//! The optional Hysteria Salamander UDP packet layer. Quinn still owns QUIC;
//! this wrapper adds/removes the specification's 8-byte salt and keyed mask.
use blake2::{
    Blake2bVar,
    digest::{Update, VariableOutput},
};
use quinn::{
    AsyncUdpSocket, UdpPoller,
    udp::{RecvMeta, Transmit},
};
use ring::rand::{SecureRandom, SystemRandom};
use std::{
    fmt,
    io::{self, IoSliceMut},
    net::SocketAddr,
    pin::Pin,
    sync::Arc,
    task::{Context, Poll},
};

pub struct Socket {
    inner: Arc<dyn AsyncUdpSocket>,
    password: zeroize::Zeroizing<Vec<u8>>,
}
impl Socket {
    pub fn wrap(inner: Arc<dyn AsyncUdpSocket>, password: &[u8]) -> Arc<dyn AsyncUdpSocket> {
        Arc::new(Self {
            inner,
            password: zeroize::Zeroizing::new(password.to_vec()),
        })
    }
}
impl fmt::Debug for Socket {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("SalamanderSocket")
    }
}

fn mask(password: &[u8], salt: &[u8]) -> io::Result<[u8; 32]> {
    let mut hasher = Blake2bVar::new(32).map_err(|_| io::ErrorKind::InvalidInput)?;
    hasher.update(password);
    hasher.update(salt);
    let mut output = [0; 32];
    hasher
        .finalize_variable(&mut output)
        .map_err(|_| io::ErrorKind::InvalidInput)?;
    Ok(output)
}

fn encode(password: &[u8], salt: [u8; 8], bytes: &[u8]) -> io::Result<Vec<u8>> {
    if bytes.len() > 65527 {
        return Err(io::ErrorKind::InvalidInput.into());
    }
    let key = mask(password, &salt)?;
    let mut result = Vec::with_capacity(bytes.len() + 8);
    result.extend(salt);
    result.extend(
        bytes
            .iter()
            .enumerate()
            .map(|(index, byte)| byte ^ key[index % 32]),
    );
    Ok(result)
}

fn decode(
    password: &[u8],
    bytes: &mut [u8],
    length: usize,
    stride: usize,
) -> io::Result<(usize, usize)> {
    if length > bytes.len() || length <= 8 {
        return Err(io::ErrorKind::InvalidData.into());
    }
    let stride = if stride == 0 { length } else { stride };
    if stride <= 8 {
        return Err(io::ErrorKind::InvalidData.into());
    }
    let mut written = 0;
    for offset in (0..length).step_by(stride) {
        let end = (offset + stride).min(length);
        if end - offset <= 8 {
            return Err(io::ErrorKind::InvalidData.into());
        }
        let key = mask(password, &bytes[offset..offset + 8])?;
        for (index, byte) in bytes[offset + 8..end].iter_mut().enumerate() {
            *byte ^= key[index % 32];
        }
        bytes.copy_within(offset + 8..end, written);
        written += end - offset - 8;
    }
    Ok((written, stride - 8))
}

impl AsyncUdpSocket for Socket {
    fn create_io_poller(self: Arc<Self>) -> Pin<Box<dyn UdpPoller>> {
        self.inner.clone().create_io_poller()
    }
    fn try_send(&self, transmit: &Transmit<'_>) -> io::Result<()> {
        // Advertising one GSO segment prevents partial multiple-datagram sends.
        if transmit
            .segment_size
            .is_some_and(|size| size < transmit.contents.len())
        {
            return Err(io::ErrorKind::InvalidInput.into());
        }
        let mut salt = [0; 8];
        SystemRandom::new()
            .fill(&mut salt)
            .map_err(|_| io::ErrorKind::Other)?;
        let contents = encode(&self.password, salt, transmit.contents)?;
        self.inner.try_send(&Transmit {
            destination: transmit.destination,
            ecn: transmit.ecn,
            contents: &contents,
            segment_size: None,
            src_ip: transmit.src_ip,
        })
    }
    fn poll_recv(
        &self,
        context: &mut Context<'_>,
        buffers: &mut [IoSliceMut<'_>],
        metadata: &mut [RecvMeta],
    ) -> Poll<io::Result<usize>> {
        if buffers.is_empty() || metadata.is_empty() {
            return Poll::Ready(Err(io::ErrorKind::InvalidInput.into()));
        }
        // Single receive buffer is deliberate. GRO segments inside that buffer
        // are decoded independently and their shortened stride is preserved.
        for _ in 0..32 {
            let received =
                match self
                    .inner
                    .poll_recv(context, &mut buffers[..1], &mut metadata[..1])
                {
                    Poll::Pending => return Poll::Pending,
                    Poll::Ready(Err(error)) => return Poll::Ready(Err(error)),
                    Poll::Ready(Ok(received)) => received,
                };
            if received == 0 {
                return Poll::Ready(Ok(0));
            }
            if let Ok((length, stride)) = decode(
                &self.password,
                &mut buffers[0],
                metadata[0].len,
                metadata[0].stride,
            ) {
                metadata[0].len = length;
                metadata[0].stride = stride;
                return Poll::Ready(Ok(1));
            }
        }
        context.waker().wake_by_ref();
        Poll::Pending
    }
    fn local_addr(&self) -> io::Result<SocketAddr> {
        self.inner.local_addr()
    }
    fn max_transmit_segments(&self) -> usize {
        1
    }
    fn max_receive_segments(&self) -> usize {
        self.inner.max_receive_segments()
    }
    fn may_fragment(&self) -> bool {
        self.inner.may_fragment()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn blake2b_256_password_then_salt_known_vector() {
        // Independently derived with Python hashlib.blake2b(digest_size=32).
        let encoded = encode(
            b"synthetic-password",
            [0, 1, 2, 3, 4, 5, 6, 7],
            &(0..48).collect::<Vec<_>>(),
        )
        .unwrap();
        let actual = encoded
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        assert_eq!(
            actual,
            "0001020304050607242451d454cb21812cb95a233a54f1f0e9182897824c1cf1e21cfb9b9c07fc2a040471f474eb01a10c997a031a74d1d0"
        );
    }

    #[test]
    fn salt_changes_ciphertext_and_gro_segments_keep_packet_boundaries() {
        let a = encode(b"password", [1; 8], b"first").unwrap();
        let b = encode(b"password", [2; 8], b"other").unwrap();
        assert_ne!(&a[8..], &b[8..]);
        let stride = a.len();
        let mut joined = [a, b].concat();
        let length = joined.len();
        let (decoded, stride) = decode(b"password", &mut joined, length, stride).unwrap();
        assert_eq!(stride, 5);
        assert_eq!(&joined[..decoded], b"firstother");
    }

    #[test]
    fn short_packets_and_inconsistent_gro_lengths_are_rejected() {
        assert!(decode(b"password", &mut [0; 8], 8, 8).is_err());
        assert!(decode(b"password", &mut [0; 20], 20, 15).is_err());
    }
}
