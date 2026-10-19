//! VLESS wire version 0 and TCP command. The executable path keeps empty Addons;
//! strict flow request encoding is an internal component, without Vision I/O.
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
    request_with_flow(uuid, target, None)
}

pub(crate) fn request_with_flow(
    uuid: &str,
    target: &Target,
    flow: Option<&str>,
) -> Result<Vec<u8>> {
    let addons = crate::vision::request_addons(flow).map_err(|_| "VlessFlow")?;
    let id = swirl_subscription::uuid_bytes(uuid).ok_or("VlessUuid")?;
    let mut bytes = vec![0];
    bytes.extend(id);
    bytes.extend(addons);
    bytes.push(1);
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

    #[test]
    fn vision_and_unchanged_empty_addons_complete_request_layouts() {
        let uuid = "00112233-4455-6677-8899-aabbccddeeff";
        // Fixed complete known-answer headers, including all three VLESS address types.
        let cases = [
            (
                "192.0.2.10",
                80,
                "0000112233445566778899aabbccddeeff0001005001c000020a",
                "0000112233445566778899aabbccddeeff120a1078746c732d727072782d766973696f6e01005001c000020a",
            ),
            (
                "example.org",
                443,
                "0000112233445566778899aabbccddeeff000101bb020b6578616d706c652e6f7267",
                "0000112233445566778899aabbccddeeff120a1078746c732d727072782d766973696f6e0101bb020b6578616d706c652e6f7267",
            ),
            (
                "2001:db8::1",
                8443,
                "0000112233445566778899aabbccddeeff000120fb0320010db8000000000000000000000001",
                "0000112233445566778899aabbccddeeff120a1078746c732d727072782d766973696f6e0120fb0320010db8000000000000000000000001",
            ),
        ];
        let hex = |text: &str| -> Vec<u8> {
            assert_eq!(text.len() % 2, 0);
            text.as_bytes()
                .as_chunks::<2>()
                .0
                .iter()
                .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
                .collect()
        };
        for (host, port, ordinary, vision) in cases {
            let target = Target {
                host: host.into(),
                port,
            };
            assert_eq!(request(uuid, &target).unwrap(), hex(ordinary));
            assert_eq!(
                request_with_flow(uuid, &target, None).unwrap(),
                hex(ordinary)
            );
            assert_eq!(
                request_with_flow(uuid, &target, Some("")).unwrap(),
                hex(ordinary)
            );
            assert_eq!(
                request_with_flow(uuid, &target, Some("xtls-rprx-vision")).unwrap(),
                hex(vision),
            );
        }
    }

    #[test]
    fn unsupported_request_flow_is_a_static_error_instead_of_empty_addons() {
        let target = Target {
            host: "example.org".into(),
            port: 443,
        };
        for flow in [
            "xtls-rprx-vision-udp443",
            "xtls-rprx-direct",
            "XTLS-RPRX-VISION",
            " xtls-rprx-vision",
            "xtls-rprx-vision ",
            "xtls-rprx-vision\0",
            " ",
            "none",
            "vision",
            "synthetic-secret-unknown-flow",
        ] {
            let error =
                request_with_flow("00112233-4455-6677-8899-aabbccddeeff", &target, Some(flow))
                    .unwrap_err();
            assert_eq!(error, "VlessFlow");
            assert!(!error.contains(flow));
        }
    }
}
