//! Swirl-owned TUIC v5 authentication, TCP commands and bounded UDP framing.
//! Wire specification: https://github.com/tuic-protocol/tuic/blob/master/SPEC.md
//! TUIC has no authentication/CONNECT acknowledgement. Returning a stream only
//! means the request was sent; successful target data is separate evidence.
use crate::{Result, Target};
use bytes::Bytes;
use quinn::VarInt;
use ring::{
    digest,
    rand::{SecureRandom, SystemRandom},
};
use std::{
    collections::{HashMap, VecDeque},
    io,
    net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr},
    pin::Pin,
    sync::{
        Arc, LazyLock, Mutex, Weak,
        atomic::{AtomicU16, Ordering},
    },
    task::{Context, Poll},
    time::Duration,
};
use swirl_dns::Resolver;
use swirl_subscription::{Tuic, uuid_bytes, valid_host};
use swirl_transport::{
    BoxStream,
    quic::{self, Session, TlsOptions},
};
use tokio::{
    io::{AsyncRead, AsyncWrite, ReadBuf},
    task::JoinHandle,
    time::{Instant, timeout, timeout_at},
};
use zeroize::Zeroizing;

const VERSION: u8 = 5;
const AUTHENTICATE: u8 = 0;
const CONNECT: u8 = 1;
const PACKET: u8 = 2;
const DISSOCIATE: u8 = 3;
const HEARTBEAT: u8 = 4;
const UDP_LIMIT: usize = 65_507;
const MAX_PACKET_WIRE: usize = UDP_LIMIT + 270;
const MAX_PENDING_PACKETS: usize = 32;
const REASSEMBLY_BYTES: usize = 256 * 1024;
const REASSEMBLY_TTL: Duration = Duration::from_secs(5);

struct Client {
    session: Arc<Session>,
    heartbeat: JoinHandle<()>,
}
impl Drop for Client {
    fn drop(&mut self) {
        self.heartbeat.abort();
    }
}
type Pool = VecDeque<((tokio::runtime::Id, [u8; 32]), Weak<Client>)>;
static TCP_SESSIONS: LazyLock<Mutex<Pool>> = LazyLock::new(|| Mutex::new(VecDeque::new()));

fn cache_key(config: &Tuic, addresses: &[SocketAddr]) -> [u8; 32] {
    let mut hash = digest::Context::new(&digest::SHA256);
    for value in [
        &config.host,
        &config.uuid,
        &config.password,
        &config.tls.server_name,
        &config.congestion_control,
        &config.udp_relay_mode,
    ] {
        hash.update(&(value.len() as u64).to_be_bytes());
        hash.update(value.as_bytes());
    }
    hash.update(&config.port.to_be_bytes());
    hash.update(&config.heartbeat_interval_ms.to_be_bytes());
    hash.update(&config.request_timeout_ms.to_be_bytes());
    hash.update(&[u8::from(config.insecure), u8::from(config.udp)]);
    hash.update(&(config.tls.alpn.len() as u64).to_be_bytes());
    for value in &config.tls.alpn {
        hash.update(&(value.len() as u64).to_be_bytes());
        hash.update(value.as_bytes());
    }
    for value in [&config.pin_sha256, &config.tls.ca_der_base64] {
        if let Some(value) = value {
            hash.update(&[1]);
            hash.update(&(value.len() as u64).to_be_bytes());
            hash.update(value.as_bytes());
        } else {
            hash.update(&[0]);
            hash.update(&0u64.to_be_bytes());
        }
    }
    // A new DNS configuration or expired DNS answer may resolve the same
    // proxy hostname differently. Existing streams retain their connection,
    // while new requests must use the current resolver's validated answers.
    hash.update(&(addresses.len() as u64).to_be_bytes());
    for address in addresses {
        match address {
            SocketAddr::V4(address) => {
                hash.update(&[4]);
                hash.update(&address.ip().octets());
                hash.update(&address.port().to_be_bytes());
            }
            SocketAddr::V6(address) => {
                hash.update(&[6]);
                hash.update(&address.ip().octets());
                hash.update(&address.port().to_be_bytes());
                hash.update(&address.flowinfo().to_be_bytes());
                hash.update(&address.scope_id().to_be_bytes());
            }
        }
    }
    hash.finish().as_ref().try_into().expect("SHA-256 length")
}

async fn resolve(config: &Tuic, resolver: &Resolver, deadline: Instant) -> Result<Vec<SocketAddr>> {
    timeout_at(deadline, resolver.resolve(&config.host, config.port))
        .await
        .map_err(|_| "TuicDnsTimeout")?
}

async fn new_client(
    config: &Tuic,
    addresses: &[SocketAddr],
    deadline: Instant,
) -> Result<Arc<Client>> {
    config.validate()?;
    let session = quic::connect(
        addresses,
        TlsOptions {
            tls: &config.tls,
            insecure: config.insecure,
            pin_sha256: config.pin_sha256.as_deref(),
        },
        None,
        &config.congestion_control,
        deadline,
    )
    .await?;
    let id = uuid_bytes(&config.uuid).ok_or("TuicUuid")?;
    let mut token = Zeroizing::new([0; 32]);
    session
        .connection
        .export_keying_material(&mut *token, &id, config.password.as_bytes())
        .map_err(|_| "TuicExporter")?;
    let mut request = Zeroizing::new(vec![VERSION, AUTHENTICATE]);
    request.extend_from_slice(&id);
    request.extend_from_slice(&*token);
    timeout_at(deadline, async {
        let mut stream = session
            .connection
            .open_uni()
            .await
            .map_err(|_| "TuicAuthenticationStream")?;
        stream
            .write_all(&request)
            .await
            .map_err(|_| "TuicAuthenticationWrite")?;
        stream.finish().map_err(|_| "TuicAuthenticationWrite")?;
        Ok::<(), &'static str>(())
    })
    .await
    .map_err(|_| "TuicAuthenticationTimeout")??;
    let connection = session.connection.clone();
    let interval = Duration::from_millis(config.heartbeat_interval_ms);
    let heartbeat = tokio::spawn(async move {
        let mut ticks = tokio::time::interval_at(Instant::now() + interval, interval);
        ticks.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        loop {
            tokio::select! {
                _ = connection.closed() => return,
                _ = ticks.tick() => {
                    if connection.send_datagram(Bytes::from_static(&[VERSION, HEARTBEAT])).is_err() { return; }
                }
            }
        }
    });
    Ok(Arc::new(Client { session, heartbeat }))
}

async fn tcp_client(config: &Tuic, resolver: &Resolver, deadline: Instant) -> Result<Arc<Client>> {
    let addresses = resolve(config, resolver, deadline).await?;
    let key = (
        tokio::runtime::Handle::current().id(),
        cache_key(config, &addresses),
    );
    {
        let mut pool = TCP_SESSIONS.lock().map_err(|_| "TuicSessionState")?;
        pool.retain(|(_, client)| client.strong_count() != 0);
        if let Some(client) = pool
            .iter()
            .find(|(other, _)| other == &key)
            .and_then(|(_, client)| client.upgrade())
            && client.session.connection.close_reason().is_none()
        {
            return Ok(client);
        }
    }
    let client = new_client(config, &addresses, deadline).await?;
    let mut pool = TCP_SESSIONS.lock().map_err(|_| "TuicSessionState")?;
    pool.retain(|(_, client)| client.strong_count() != 0);
    // Weak entries own neither sockets nor tasks. Race duplicates are dropped
    // and no global mutex is held during DNS/QUIC/authentication.
    if let Some(existing) = pool
        .iter()
        .find(|(other, _)| other == &key)
        .and_then(|(_, client)| client.upgrade())
        && existing.session.connection.close_reason().is_none()
    {
        return Ok(existing);
    }
    pool.retain(|(other, _)| other != &key);
    if pool.len() == 64 {
        pool.pop_front();
    }
    pool.push_back((key, Arc::downgrade(&client)));
    Ok(client)
}

pub async fn connect(
    config: &Tuic,
    target: &Target,
    resolver: &Resolver,
    handshake_limit: Duration,
) -> Result<BoxStream> {
    config.validate()?;
    let mut request = vec![VERSION, CONNECT];
    encode_address(target, &mut request)?;
    let deadline =
        Instant::now() + handshake_limit.min(Duration::from_millis(config.request_timeout_ms));
    let client = tcp_client(config, resolver, deadline).await?;
    let (mut send, recv) = timeout_at(deadline, client.session.connection.open_bi())
        .await
        .map_err(|_| "TuicConnectTimeout")?
        .map_err(|_| "TuicConnectStream")?;
    timeout_at(deadline, send.write_all(&request))
        .await
        .map_err(|_| "TuicConnectTimeout")?
        .map_err(|_| "TuicConnectWrite")?;
    Ok(Box::new(Stream {
        inner: quic::Stream::new(client.session.clone(), send, recv),
        _client: client,
    }))
}

struct Stream {
    inner: quic::Stream,
    _client: Arc<Client>,
}
impl AsyncRead for Stream {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        output: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_read(cx, output)
    }
}
impl AsyncWrite for Stream {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        input: &[u8],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.inner).poll_write(cx, input)
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_shutdown(cx)
    }
}

fn encode_address(target: &Target, bytes: &mut Vec<u8>) -> Result<()> {
    if target.port == 0 || !valid_host(&target.host) {
        return Err("TuicTarget");
    }
    match target.host.parse::<IpAddr>() {
        Ok(IpAddr::V4(ip)) => {
            bytes.push(1);
            bytes.extend_from_slice(&ip.octets());
        }
        Ok(IpAddr::V6(ip)) => {
            bytes.push(2);
            bytes.extend_from_slice(&ip.octets());
        }
        Err(_) if target.host.len() <= 255 => {
            bytes.extend_from_slice(&[0, target.host.len() as u8]);
            bytes.extend_from_slice(target.host.as_bytes());
        }
        _ => return Err("TuicTarget"),
    }
    bytes.extend_from_slice(&target.port.to_be_bytes());
    Ok(())
}

struct Cursor<'a> {
    bytes: &'a [u8],
    offset: usize,
}
impl<'a> Cursor<'a> {
    fn take(&mut self, len: usize) -> Result<&'a [u8]> {
        let end = self.offset.checked_add(len).ok_or("TuicPacket")?;
        let value = self.bytes.get(self.offset..end).ok_or("TuicPacket")?;
        self.offset = end;
        Ok(value)
    }
    fn byte(&mut self) -> Result<u8> {
        Ok(self.take(1)?[0])
    }
    fn short(&mut self) -> Result<u16> {
        let p = self.take(2)?;
        Ok(u16::from_be_bytes([p[0], p[1]]))
    }
    fn address(&mut self) -> Result<Option<Target>> {
        let host = match self.byte()? {
            255 => return Ok(None),
            0 => {
                let len = self.byte()? as usize;
                std::str::from_utf8(self.take(len)?)
                    .map_err(|_| "TuicAddress")?
                    .to_owned()
            }
            1 => {
                let mut bytes = [0; 4];
                bytes.copy_from_slice(self.take(4)?);
                Ipv4Addr::from(bytes).to_string()
            }
            2 => {
                let mut bytes = [0; 16];
                bytes.copy_from_slice(self.take(16)?);
                Ipv6Addr::from(bytes).to_string()
            }
            _ => return Err("TuicAddress"),
        };
        let port = self.short()?;
        if !valid_host(&host) || port == 0 {
            return Err("TuicAddress");
        }
        Ok(Some(Target { host, port }))
    }
}

struct Fragment {
    association: u16,
    packet: u16,
    total: u8,
    index: u8,
    target: Option<Target>,
    payload: Vec<u8>,
}
fn decode_fragment(bytes: &[u8]) -> Result<Fragment> {
    if bytes.len() > MAX_PACKET_WIRE {
        return Err("TuicPacketSize");
    }
    let mut cursor = Cursor { bytes, offset: 0 };
    if cursor.byte()? != VERSION || cursor.byte()? != PACKET {
        return Err("TuicPacketCommand");
    }
    let association = cursor.short()?;
    let packet = cursor.short()?;
    let total = cursor.byte()?;
    let index = cursor.byte()?;
    let size = cursor.short()? as usize;
    if total == 0 || index >= total || size > UDP_LIMIT {
        return Err("TuicPacketFragment");
    }
    let target = cursor.address()?;
    if (index == 0) != target.is_some() {
        return Err("TuicPacketAddress");
    }
    let payload = cursor.take(size)?.to_vec();
    if cursor.offset != bytes.len() {
        return Err("TuicPacketTrailingData");
    }
    Ok(Fragment {
        association,
        packet,
        total,
        index,
        target,
        payload,
    })
}

fn encode_packets(
    association: u16,
    packet: u16,
    target: &Target,
    payload: &[u8],
    limit: usize,
) -> Result<Vec<Vec<u8>>> {
    if payload.len() > UDP_LIMIT {
        return Err("TuicDatagramSize");
    }
    let mut address = Vec::new();
    encode_address(target, &mut address)?;
    let first = limit
        .checked_sub(10 + address.len())
        .filter(|v| *v != 0)
        .ok_or("TuicDatagramMtu")?;
    let later = limit
        .checked_sub(11)
        .filter(|v| *v != 0)
        .ok_or("TuicDatagramMtu")?;
    let total = if payload.len() <= first {
        1
    } else {
        1 + (payload.len() - first).div_ceil(later)
    };
    let total = u8::try_from(total).map_err(|_| "TuicFragmentCount")?;
    let mut frames = Vec::with_capacity(total as usize);
    let mut offset = 0;
    for index in 0..total {
        let size = (if index == 0 { first } else { later }).min(payload.len() - offset);
        let mut bytes = vec![VERSION, PACKET];
        bytes.extend_from_slice(&association.to_be_bytes());
        bytes.extend_from_slice(&packet.to_be_bytes());
        bytes.extend_from_slice(&[total, index]);
        bytes.extend_from_slice(&(size as u16).to_be_bytes());
        if index == 0 {
            bytes.extend_from_slice(&address);
        } else {
            bytes.push(255);
        }
        bytes.extend_from_slice(&payload[offset..offset + size]);
        offset += size;
        frames.push(bytes);
    }
    Ok(frames)
}

struct Pending {
    since: Instant,
    target: Option<Target>,
    pieces: Vec<Option<Vec<u8>>>,
    bytes: usize,
}
#[derive(Default)]
struct Reassembly {
    packets: HashMap<u16, Pending>,
    bytes: usize,
}
impl Reassembly {
    fn expire(&mut self) {
        self.packets
            .retain(|_, value| value.since.elapsed() < REASSEMBLY_TTL);
        self.bytes = self.packets.values().map(|value| value.bytes).sum();
    }
    fn insert(&mut self, fragment: Fragment) -> Result<Option<(Target, Vec<u8>)>> {
        self.expire();
        if fragment.total == 1 {
            return Ok(Some((
                fragment.target.ok_or("TuicPacketAddress")?,
                fragment.payload,
            )));
        }
        if !self.packets.contains_key(&fragment.packet) && self.packets.len() >= MAX_PENDING_PACKETS
        {
            return Err("TuicReassemblyLimit");
        }
        if self.bytes + fragment.payload.len() > REASSEMBLY_BYTES {
            return Err("TuicReassemblyLimit");
        }
        let entry = self
            .packets
            .entry(fragment.packet)
            .or_insert_with(|| Pending {
                since: Instant::now(),
                target: None,
                pieces: vec![None; fragment.total as usize],
                bytes: 0,
            });
        if entry.pieces.len() != fragment.total as usize {
            return Err("TuicFragmentConflict");
        }
        let slot = &mut entry.pieces[fragment.index as usize];
        if let Some(old) = slot {
            if old != &fragment.payload {
                return Err("TuicFragmentConflict");
            }
            return Ok(None);
        }
        if entry.bytes + fragment.payload.len() > UDP_LIMIT {
            return Err("TuicDatagramSize");
        }
        entry.bytes += fragment.payload.len();
        self.bytes += fragment.payload.len();
        *slot = Some(fragment.payload);
        if fragment.target.is_some() {
            entry.target = fragment.target;
        }
        if entry.pieces.iter().any(Option::is_none) {
            return Ok(None);
        }
        let entry = self
            .packets
            .remove(&fragment.packet)
            .ok_or("TuicReassemblyState")?;
        self.bytes -= entry.bytes;
        let mut payload = Vec::with_capacity(entry.bytes);
        for piece in entry.pieces {
            payload.extend(piece.ok_or("TuicReassemblyState")?);
        }
        Ok(Some((entry.target.ok_or("TuicPacketAddress")?, payload)))
    }
}

/// Each Core UDP association owns one TUIC session, so unrelated callers never
/// race over Quinn's single datagram receive queue. TCP sessions can multiplex.
pub struct UdpAssociation {
    client: Arc<Client>,
    association: u16,
    packet: AtomicU16,
    native: bool,
    assembly: Reassembly,
    incoming: Option<quinn::RecvStream>,
    incoming_data: Vec<u8>,
    incoming_deadline: Option<Instant>,
}
impl UdpAssociation {
    pub async fn connect(
        config: &Tuic,
        resolver: &Resolver,
        handshake_limit: Duration,
    ) -> Result<Self> {
        config.validate()?;
        if !config.udp {
            return Err("TuicUdpDisabled");
        }
        let deadline =
            Instant::now() + handshake_limit.min(Duration::from_millis(config.request_timeout_ms));
        let addresses = resolve(config, resolver, deadline).await?;
        let client = new_client(config, &addresses, deadline).await?;
        if client.session.connection.max_datagram_size().is_none() {
            return Err("TuicDatagramsNotNegotiated");
        }
        let mut id = [0; 2];
        SystemRandom::new()
            .fill(&mut id)
            .map_err(|_| "TuicRandom")?;
        Ok(Self {
            client,
            association: u16::from_be_bytes(id),
            packet: AtomicU16::new(0),
            native: config.udp_relay_mode == "native",
            assembly: Reassembly::default(),
            incoming: None,
            incoming_data: Vec::new(),
            incoming_deadline: None,
        })
    }

    pub async fn send(&self, target: &Target, payload: &[u8]) -> Result<()> {
        let connection = &self.client.session.connection;
        let limit = if self.native {
            connection
                .max_datagram_size()
                .ok_or("TuicDatagramsNotNegotiated")?
        } else {
            u16::MAX as usize
        };
        let packets = encode_packets(
            self.association,
            self.packet.fetch_add(1, Ordering::Relaxed),
            target,
            payload,
            limit,
        )?;
        timeout(Duration::from_secs(5), async {
            for packet in packets {
                if self.native {
                    connection
                        .send_datagram_wait(Bytes::from(packet))
                        .await
                        .map_err(|_| "TuicUdpSend")?;
                } else {
                    let mut stream = connection.open_uni().await.map_err(|_| "TuicUdpStream")?;
                    stream.write_all(&packet).await.map_err(|_| "TuicUdpSend")?;
                    stream.finish().map_err(|_| "TuicUdpSend")?;
                }
            }
            Ok::<(), &'static str>(())
        })
        .await
        .map_err(|_| "TuicUdpSendTimeout")?
    }

    pub async fn recv(&mut self) -> Result<(Target, Vec<u8>)> {
        let mut processed = 0;
        loop {
            // A peer can keep the receive queue ready with heartbeats or
            // incomplete fragments. Bound work per poll independently of the
            // QUIC implementation's own cooperative scheduling.
            if processed == 32 {
                tokio::task::yield_now().await;
                processed = 0;
            }
            let bytes = if self.native {
                self.client
                    .session
                    .connection
                    .read_datagram()
                    .await
                    .map_err(|_| "TuicUdpReceive")?
                    .to_vec()
            } else {
                self.receive_stream_packet().await?
            };
            processed += 1;
            if bytes == [VERSION, HEARTBEAT] {
                continue;
            }
            let fragment = decode_fragment(&bytes)?;
            if fragment.association != self.association {
                return Err("TuicUdpAssociation");
            }
            if let Some(message) = self.assembly.insert(fragment)? {
                return Ok(message);
            }
        }
    }

    // Core may cancel a receive future while servicing an outgoing packet.
    // Keep accepted stream ownership, partial bytes and its original deadline
    // in the association instead of an ephemeral read_to_end future.
    async fn receive_stream_packet(&mut self) -> Result<Vec<u8>> {
        if self.incoming.is_none() {
            self.incoming = Some(
                self.client
                    .session
                    .connection
                    .accept_uni()
                    .await
                    .map_err(|_| "TuicUdpStream")?,
            );
            self.incoming_deadline = Some(Instant::now() + Duration::from_secs(5));
            self.incoming_data.clear();
        }
        let deadline = self.incoming_deadline.ok_or("TuicUdpReceiveState")?;
        let result = async {
            loop {
                let mut chunk = [0u8; 4096];
                let stream = self.incoming.as_mut().ok_or("TuicUdpReceiveState")?;
                let amount = timeout_at(deadline, stream.read(&mut chunk))
                    .await
                    .map_err(|_| "TuicUdpReadTimeout")?
                    .map_err(|_| "TuicUdpReceive")?;
                let Some(amount) = amount else {
                    return Ok(std::mem::take(&mut self.incoming_data));
                };
                if self.incoming_data.len() + amount > MAX_PACKET_WIRE {
                    return Err("TuicPacketSize");
                }
                self.incoming_data.extend_from_slice(&chunk[..amount]);
            }
        }
        .await;
        self.incoming = None;
        self.incoming_deadline = None;
        if result.is_err() {
            self.incoming_data.clear();
        }
        result
    }

    pub async fn closed(&self) -> &'static str {
        self.client.session.connection.closed().await;
        "TuicConnectionClosed"
    }

    pub async fn close(&self) -> Result<()> {
        let result = timeout(Duration::from_secs(2), async {
            let mut stream = self
                .client
                .session
                .connection
                .open_uni()
                .await
                .map_err(|_| "TuicDissociate")?;
            let id = self.association.to_be_bytes();
            stream
                .write_all(&[VERSION, DISSOCIATE, id[0], id[1]])
                .await
                .map_err(|_| "TuicDissociate")?;
            stream.finish().map_err(|_| "TuicDissociate")?;
            stream.stopped().await.map_err(|_| "TuicDissociate")?;
            Ok::<(), &'static str>(())
        })
        .await
        .map_err(|_| "TuicDissociateTimeout");
        self.client
            .session
            .connection
            .close(VarInt::from_u32(0), b"");
        result?
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn address_types_are_tuic_not_socks() {
        for (host, expected) in [("example.com", 0), ("192.0.2.1", 1), ("2001:db8::1", 2)] {
            let target = Target {
                host: host.into(),
                port: 443,
            };
            let mut encoded = Vec::new();
            encode_address(&target, &mut encoded).unwrap();
            assert_eq!(encoded[0], expected);
            let decoded = Cursor {
                bytes: &encoded,
                offset: 0,
            }
            .address()
            .unwrap()
            .unwrap();
            assert_eq!(decoded.host, host);
            assert_eq!(decoded.port, 443);
        }
    }
    #[tokio::test]
    async fn fragmentation_reorders_without_leaking_protocol_bytes() {
        let target = Target {
            host: "2001:db8::1".into(),
            port: 53,
        };
        let payload: Vec<u8> = (0..UDP_LIMIT).map(|i| (i % 251) as u8).collect();
        let frames = encode_packets(42, 7, &target, &payload, 1200).unwrap();
        assert!(frames.len() > 1);
        assert!(frames.iter().all(|f| f.len() <= 1200));
        let mut assembly = Reassembly::default();
        let mut actual = None;
        for frame in frames.iter().rev() {
            let fragment = decode_fragment(frame).unwrap();
            assert_eq!(fragment.association, 42);
            actual = assembly.insert(fragment).unwrap().or(actual);
        }
        let (address, value) = actual.unwrap();
        assert_eq!(address.host, target.host);
        assert_eq!(address.port, 53);
        assert_eq!(value, payload);
        assert_eq!(assembly.bytes, 0);
    }
    #[test]
    fn malformed_and_truncated_packets_are_rejected() {
        let target = Target {
            host: "127.0.0.1".into(),
            port: 9,
        };
        let frame = encode_packets(1, 1, &target, b"abc", 1200)
            .unwrap()
            .remove(0);
        for length in 0..frame.len() {
            assert!(decode_fragment(&frame[..length]).is_err());
        }
        let mut bad = frame.clone();
        bad.push(0);
        assert!(decode_fragment(&bad).is_err());
        let mut bad = frame.clone();
        bad[0] = 4;
        assert!(decode_fragment(&bad).is_err());
        let mut bad = frame;
        bad[6] = 0;
        assert!(decode_fragment(&bad).is_err());
    }
    #[tokio::test]
    async fn incomplete_reassembly_is_bounded() {
        let target = Target {
            host: "example.com".into(),
            port: 53,
        };
        let mut assembly = Reassembly::default();
        for id in 0..MAX_PENDING_PACKETS {
            let frames = encode_packets(1, id as u16, &target, &[0; 1300], 1200).unwrap();
            assert!(
                assembly
                    .insert(decode_fragment(&frames[0]).unwrap())
                    .unwrap()
                    .is_none()
            );
        }
        let frames = encode_packets(1, 100, &target, &[0; 1300], 1200).unwrap();
        assert_eq!(
            assembly.insert(decode_fragment(&frames[0]).unwrap()).err(),
            Some("TuicReassemblyLimit")
        );
        assert_eq!(assembly.packets.len(), MAX_PENDING_PACKETS);
    }
}
