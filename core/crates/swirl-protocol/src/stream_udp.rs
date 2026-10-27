//! Native Trojan UDP ASSOCIATE and classic VLESS command-2 datagrams.
//!
//! TLS/REALITY and transport negotiation use the existing protocol connector.
//! VLESS binds a carrier to one destination; Core pools it by node and target.
//! No Vision/XUDP conversion or implicit flow downgrade is performed here.
//! Wire references: trojan-gfw/trojan/docs/protocol.md and the fixed Xray
//! v26.10.21 proxy/vless/encoding/{encoding,addons}.go implementations.
use crate::{Result, Target};
use std::{
    net::{IpAddr, Ipv4Addr, Ipv6Addr},
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};
use swirl_dns::Resolver;
use swirl_subscription::{Outbound, uuid_bytes, valid_host};
use swirl_transport::BoxStream;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt, ReadHalf, WriteHalf},
    sync::Mutex,
    time::{Instant, timeout, timeout_at},
};

const UDP_LIMIT: usize = 65_507;
const BUFFER_LIMIT: usize = UDP_LIMIT + 262 + 4096;
const FRAME_TIMEOUT: Duration = Duration::from_secs(5);

enum Encoding {
    Vless(Target),
    Trojan,
}

/// Owns a single authenticated stream carrier. Authentication acceptance is
/// proved only by returned target data because neither wire protocol has an
/// independent positive authentication acknowledgement.
pub struct UdpAssociation {
    encoding: Encoding,
    writer: Mutex<WriteHalf<BoxStream>>,
    reader: ReadHalf<BoxStream>,
    buffered: Vec<u8>,
    partial_deadline: Option<Instant>,
    failed: AtomicBool,
}

impl UdpAssociation {
    pub async fn connect(
        outbound: &Outbound,
        target: &Target,
        resolver: &Resolver,
        handshake_limit: Duration,
        transport: Option<&crate::Transport>,
    ) -> Result<Self> {
        if !valid_host(&target.host) || target.port == 0 {
            return Err("StreamUdpTarget");
        }
        let encoding = match outbound {
            Outbound::Vless {
                host,
                port,
                uuid,
                udp: true,
                flow,
                ..
            } => {
                if !valid_host(host) || *port == 0 || uuid_bytes(uuid).is_none() {
                    return Err("VlessParameters");
                }
                if flow.as_ref().is_some_and(|value| !value.is_empty()) {
                    return Err("VlessUdpFlowUnsupported");
                }
                Encoding::Vless(target.clone())
            }
            Outbound::Trojan {
                host,
                port,
                password,
                udp: true,
                ..
            } => {
                if !valid_host(host) || *port == 0 || password.is_empty() || password.len() > 1024 {
                    return Err("TrojanParameters");
                }
                Encoding::Trojan
            }
            _ => return Err("StreamUdpDisabledOrUnsupported"),
        };
        let stream =
            crate::connect_udp_stream(outbound, target, resolver, handshake_limit, transport)
                .await?;
        let (reader, writer) = tokio::io::split(stream);
        Ok(Self {
            encoding,
            writer: Mutex::new(writer),
            reader,
            buffered: Vec::new(),
            partial_deadline: None,
            failed: AtomicBool::new(false),
        })
    }

    pub async fn send(&mut self, target: &Target, payload: &[u8]) -> Result<()> {
        if self.failed.load(Ordering::Acquire) {
            return Err("StreamUdpClosed");
        }
        let frame = encode_packet(&self.encoding, target, payload)?;
        timeout(FRAME_TIMEOUT, async {
            let mut writer = self.writer.lock().await;
            if self.failed.load(Ordering::Acquire) {
                return Err("StreamUdpClosed");
            }
            // A cancelled write may have sent half a packet. Poison the
            // carrier even when an outer timeout drops this future entirely.
            let mut guard = IncompleteWrite {
                failed: &self.failed,
                armed: true,
            };
            writer
                .write_all(&frame)
                .await
                .map_err(|_| "StreamUdpWrite")?;
            writer.flush().await.map_err(|_| "StreamUdpWrite")?;
            guard.armed = false;
            Ok(())
        })
        .await
        .map_err(|_| "StreamUdpWriteTimeout")?
    }

    pub async fn recv(&mut self) -> Result<(Target, Vec<u8>)> {
        loop {
            if self.failed.load(Ordering::Acquire) {
                return Err("StreamUdpClosed");
            }
            match decode_packet(&self.encoding, &self.buffered) {
                Ok(Some((used, target, payload))) => {
                    self.buffered.drain(..used);
                    self.partial_deadline =
                        (!self.buffered.is_empty()).then(|| Instant::now() + FRAME_TIMEOUT);
                    return Ok((target, payload));
                }
                Err(code) => {
                    self.failed.store(true, Ordering::Release);
                    return Err(code);
                }
                Ok(None) => {}
            }
            let mut chunk = [0; 4096];
            // Tokio read is cancellation safe. Completed bytes are retained
            // in the association, not in a temporary read_exact future.
            let received = if let Some(deadline) = self.partial_deadline {
                match timeout_at(deadline, self.reader.read(&mut chunk)).await {
                    Ok(value) => value,
                    Err(_) => {
                        self.failed.store(true, Ordering::Release);
                        return Err("StreamUdpReadTimeout");
                    }
                }
            } else {
                self.reader.read(&mut chunk).await
            };
            let amount = match received {
                Ok(0) => {
                    self.failed.store(true, Ordering::Release);
                    return Err(if self.buffered.is_empty() {
                        "StreamUdpClosed"
                    } else {
                        "StreamUdpTruncated"
                    });
                }
                Ok(value) => value,
                Err(_) => {
                    self.failed.store(true, Ordering::Release);
                    return Err("StreamUdpRead");
                }
            };
            if self.buffered.len() + amount > BUFFER_LIMIT {
                self.failed.store(true, Ordering::Release);
                return Err("StreamUdpBufferLimit");
            }
            self.buffered.extend_from_slice(&chunk[..amount]);
            self.partial_deadline
                .get_or_insert_with(|| Instant::now() + FRAME_TIMEOUT);
        }
    }

    pub async fn close(&mut self) -> Result<()> {
        self.failed.store(true, Ordering::Release);
        timeout(FRAME_TIMEOUT, async {
            self.writer
                .lock()
                .await
                .shutdown()
                .await
                .map_err(|_| "StreamUdpClose")
        })
        .await
        .map_err(|_| "StreamUdpCloseTimeout")?
    }
}

struct IncompleteWrite<'a> {
    failed: &'a AtomicBool,
    armed: bool,
}
impl Drop for IncompleteWrite<'_> {
    fn drop(&mut self) {
        if self.armed {
            self.failed.store(true, Ordering::Release);
        }
    }
}

fn same_target(left: &Target, right: &Target) -> bool {
    left.port == right.port
        && match (left.host.parse::<IpAddr>(), right.host.parse::<IpAddr>()) {
            (Ok(left), Ok(right)) => left == right,
            _ => left.host.eq_ignore_ascii_case(&right.host),
        }
}

fn encode_packet(encoding: &Encoding, target: &Target, payload: &[u8]) -> Result<Vec<u8>> {
    if payload.len() > UDP_LIMIT {
        return Err("StreamUdpPayloadLimit");
    }
    if target.port == 0 || !valid_host(&target.host) {
        return Err("StreamUdpTarget");
    }
    let mut frame = Vec::with_capacity(payload.len() + 262);
    match encoding {
        Encoding::Vless(bound) => {
            if !same_target(bound, target) {
                return Err("VlessUdpTargetMismatch");
            }
        }
        Encoding::Trojan => target.encode(&mut frame)?,
    }
    frame.extend_from_slice(&(payload.len() as u16).to_be_bytes());
    if matches!(encoding, Encoding::Trojan) {
        frame.extend_from_slice(b"\r\n");
    }
    frame.extend_from_slice(payload);
    Ok(frame)
}

type Decoded = Option<(usize, Target, Vec<u8>)>;
fn decode_packet(encoding: &Encoding, bytes: &[u8]) -> Result<Decoded> {
    let (target, length_at) = match encoding {
        Encoding::Vless(target) => (target.clone(), 0),
        Encoding::Trojan => {
            let Some((target, used)) = decode_address(bytes)? else {
                return Ok(None);
            };
            (target, used)
        }
    };
    let header_end = length_at
        + if matches!(encoding, Encoding::Trojan) {
            4
        } else {
            2
        };
    if bytes.len() < header_end {
        return Ok(None);
    }
    let size = u16::from_be_bytes([bytes[length_at], bytes[length_at + 1]]) as usize;
    if size > UDP_LIMIT {
        return Err("StreamUdpPayloadLimit");
    }
    if matches!(encoding, Encoding::Trojan) && &bytes[length_at + 2..header_end] != b"\r\n" {
        return Err("TrojanUdpSeparator");
    }
    let end = header_end + size;
    if bytes.len() < end {
        return Ok(None);
    }
    Ok(Some((end, target, bytes[header_end..end].to_vec())))
}

fn decode_address(bytes: &[u8]) -> Result<Option<(Target, usize)>> {
    let Some(&kind) = bytes.first() else {
        return Ok(None);
    };
    let (host, port_at) = match kind {
        1 => {
            if bytes.len() < 7 {
                return Ok(None);
            }
            (
                Ipv4Addr::new(bytes[1], bytes[2], bytes[3], bytes[4]).to_string(),
                5,
            )
        }
        4 => {
            if bytes.len() < 19 {
                return Ok(None);
            }
            let mut octets = [0; 16];
            octets.copy_from_slice(&bytes[1..17]);
            (Ipv6Addr::from(octets).to_string(), 17)
        }
        3 => {
            let Some(&length) = bytes.get(1) else {
                return Ok(None);
            };
            if length == 0 {
                return Err("TrojanUdpAddress");
            }
            let port_at = 2 + length as usize;
            if bytes.len() < port_at + 2 {
                return Ok(None);
            }
            let host = std::str::from_utf8(&bytes[2..port_at])
                .map_err(|_| "TrojanUdpAddress")?
                .to_owned();
            (host, port_at)
        }
        _ => return Err("TrojanUdpAddressType"),
    };
    let port = u16::from_be_bytes([bytes[port_at], bytes[port_at + 1]]);
    if !valid_host(&host) || port == 0 {
        return Err("TrojanUdpAddress");
    }
    Ok(Some((Target { host, port }, port_at + 2)))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn target(host: &str) -> Target {
        Target {
            host: host.into(),
            port: 53,
        }
    }

    #[test]
    fn complete_and_partial_frames_preserve_datagram_boundaries() {
        for encoding in [Encoding::Trojan, Encoding::Vless(target("example.org"))] {
            let frame = encode_packet(&encoding, &target("example.org"), b"dns-payload").unwrap();
            for end in 0..frame.len() {
                assert!(decode_packet(&encoding, &frame[..end]).unwrap().is_none());
            }
            let mut joined = frame.clone();
            joined.extend_from_slice(&frame);
            let (used, destination, payload) = decode_packet(&encoding, &joined).unwrap().unwrap();
            assert_eq!(used, frame.len());
            assert_eq!(destination.host, "example.org");
            assert_eq!(destination.port, 53);
            assert_eq!(payload, b"dns-payload");
        }
    }

    #[test]
    fn different_targets_cannot_reuse_a_vless_carrier() {
        let encoding = Encoding::Vless(target("example.org"));
        assert!(encode_packet(&encoding, &target("EXAMPLE.ORG"), b"a").is_ok());
        assert_eq!(
            encode_packet(&encoding, &target("other.example"), b"a").err(),
            Some("VlessUdpTargetMismatch")
        );
        let mut other = target("example.org");
        other.port = 443;
        assert_eq!(
            encode_packet(&encoding, &other, b"a").err(),
            Some("VlessUdpTargetMismatch")
        );
    }

    #[test]
    fn address_families_empty_and_bounded_payloads() {
        for host in ["192.0.2.1", "2001:db8::1", "example.org"] {
            for payload in [vec![], vec![7; UDP_LIMIT]] {
                let frame = encode_packet(&Encoding::Trojan, &target(host), &payload).unwrap();
                let (used, actual, decoded) =
                    decode_packet(&Encoding::Trojan, &frame).unwrap().unwrap();
                assert_eq!(used, frame.len());
                assert_eq!(actual.host, host);
                assert_eq!(decoded, payload);
            }
        }
        assert!(
            encode_packet(
                &Encoding::Trojan,
                &target("example.org"),
                &vec![0; UDP_LIMIT + 1]
            )
            .is_err()
        );
        assert!(decode_packet(&Encoding::Vless(target("example.org")), &[255, 255]).is_err());
    }

    #[test]
    fn malformed_address_and_separator_are_rejected() {
        assert!(decode_packet(&Encoding::Trojan, &[99]).is_err());
        assert!(decode_packet(&Encoding::Trojan, &[3, 0]).is_err());
        let mut frame = encode_packet(&Encoding::Trojan, &target("127.0.0.1"), b"data").unwrap();
        frame[10] = b'x';
        assert_eq!(
            decode_packet(&Encoding::Trojan, &frame).err(),
            Some("TrojanUdpSeparator")
        );
    }

    fn memory_association(stream: tokio::io::DuplexStream) -> UdpAssociation {
        let (reader, writer) = tokio::io::split(Box::new(stream) as BoxStream);
        UdpAssociation {
            encoding: Encoding::Trojan,
            writer: Mutex::new(writer),
            reader,
            buffered: Vec::new(),
            partial_deadline: None,
            failed: AtomicBool::new(false),
        }
    }

    #[tokio::test]
    async fn cancelling_a_partial_receive_preserves_its_framing() {
        let (client, mut server) = tokio::io::duplex(128);
        let mut association = memory_association(client);
        let frame = encode_packet(&Encoding::Trojan, &target("example.org"), b"data").unwrap();
        server.write_all(&frame[..5]).await.unwrap();
        assert!(
            timeout(Duration::from_millis(10), association.recv())
                .await
                .is_err()
        );
        server.write_all(&frame[5..]).await.unwrap();
        let (destination, payload) = association.recv().await.unwrap();
        assert_eq!(destination.host, "example.org");
        assert_eq!(payload, b"data");
    }

    #[tokio::test]
    async fn cancelling_a_partial_write_prevents_further_packets() {
        let (client, _server) = tokio::io::duplex(1);
        let mut association = memory_association(client);
        assert!(
            timeout(
                Duration::from_millis(10),
                association.send(&target("example.org"), b"partial-payload")
            )
            .await
            .is_err()
        );
        assert_eq!(
            association
                .send(&target("example.org"), b"next")
                .await
                .err(),
            Some("StreamUdpClosed")
        );
    }
}
