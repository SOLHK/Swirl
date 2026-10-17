//! VLESS wire version 0, TCP command, no flow or addons. Generic TLS is separate.
use crate::{Result, Target};
use std::{
    future::Future,
    io,
    net::IpAddr,
    pin::Pin,
    task::{Context, Poll, ready},
};
use swirl_transport::BoxStream;
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};

pub fn request(uuid: &str, target: &Target) -> Result<Vec<u8>> {
    let id = swirl_subscription::uuid_bytes(uuid).ok_or("VlessUuid")?;
    let mut bytes = vec![0];
    bytes.extend(id);
    bytes.extend([0, 1]);
    bytes.extend(target.port.to_be_bytes());
    match target.host.parse::<IpAddr>() {
        Ok(IpAddr::V4(ip)) => {
            bytes.push(1);
            bytes.extend(ip.octets());
        }
        Ok(IpAddr::V6(ip)) => {
            bytes.push(3);
            bytes.extend(ip.octets());
        }
        Err(_) if swirl_subscription::valid_host(&target.host) && target.host.len() <= 255 => {
            bytes.extend([2, target.host.len() as u8]);
            bytes.extend(target.host.as_bytes());
        }
        _ => return Err("InvalidTarget"),
    }
    Ok(bytes)
}
fn invalid() -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        "VLESS response version or addons unsupported",
    )
}
pub struct Stream {
    inner: BoxStream,
    header: [u8; 2],
    received: usize,
    failed: bool,
    limit: std::time::Duration,
    partial_deadline: Option<Pin<Box<tokio::time::Sleep>>>,
}
impl Stream {
    pub fn new(inner: BoxStream, limit: std::time::Duration) -> Self {
        Self {
            inner,
            header: [0; 2],
            received: 0,
            failed: false,
            limit,
            partial_deadline: None,
        }
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
        if out.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        while self.received < 2 {
            if let Some(deadline) = &mut self.partial_deadline
                && deadline.as_mut().poll(cx).is_ready()
            {
                self.failed = true;
                return Poll::Ready(Err(io::ErrorKind::TimedOut.into()));
            }
            let mut bytes = [0; 2];
            let mut part = ReadBuf::new(&mut bytes[..2 - self.received]);
            let result = ready!(Pin::new(&mut self.inner).poll_read(cx, &mut part));
            if let Err(error) = result {
                self.failed = true;
                return Poll::Ready(Err(error));
            }
            let count = part.filled().len();
            if count == 0 {
                self.failed = true;
                return Poll::Ready(Err(io::ErrorKind::UnexpectedEof.into()));
            }
            let start = self.received;
            self.header[start..start + count].copy_from_slice(part.filled());
            self.received += count;
            if self.received == 1 && self.partial_deadline.is_none() {
                self.partial_deadline = Some(Box::pin(tokio::time::sleep(self.limit)));
            }
        }
        self.partial_deadline = None;
        if self.header != [0, 0] {
            self.failed = true;
            return Poll::Ready(Err(invalid()));
        }
        Pin::new(&mut self.inner).poll_read(cx, out)
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
        Pin::new(&mut self.inner).poll_write(cx, bytes)
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_shutdown(cx)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    #[tokio::test]
    async fn partial_response_header_has_deadline_without_timing_out_idle_application() {
        let (client, mut peer) = tokio::io::duplex(32);
        let mut client = Stream::new(Box::new(client), std::time::Duration::from_millis(10));
        peer.write_all(&[0]).await.unwrap();
        let mut out = [0; 1];
        let error = tokio::time::timeout(
            std::time::Duration::from_secs(1),
            client.read_exact(&mut out),
        )
        .await
        .unwrap()
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::TimedOut);
        let (client, mut peer) = tokio::io::duplex(32);
        let mut client = Stream::new(Box::new(client), std::time::Duration::from_millis(10));
        let worker = tokio::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(40)).await;
            peer.write_all(&[0, 0, 7]).await.unwrap();
        });
        client.read_exact(&mut out).await.unwrap();
        assert_eq!(out, [7]);
        worker.await.unwrap();
    }
    #[test]
    fn canonical_uuid_and_domain_wire_layout() {
        let bytes = request(
            "00112233-4455-6677-8899-aabbccddeeff",
            &Target {
                host: "example.org".into(),
                port: 443,
            },
        )
        .unwrap();
        assert_eq!(&bytes[..4], &[0, 0, 0x11, 0x22]);
        assert_eq!(&bytes[17..23], &[0, 1, 1, 0xbb, 2, 11]);
        assert_eq!(&bytes[23..], b"example.org");
        assert!(swirl_subscription::uuid_bytes("00112233-4455-6677-8899-aabbccddeezz").is_none());
        assert!(
            swirl_subscription::uuid_bytes("00112233-4455-6677-8899-aabbccddeeff-extra").is_none()
        );
    }
}
