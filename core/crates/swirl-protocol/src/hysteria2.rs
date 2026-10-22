//! Swirl's Hysteria 2 client: HTTP/3 authentication, native QUIC TCP streams,
//! and bounded fragmented UDP datagrams. No external proxy process is used.
//! The independent reference server is HyNetworks/hysteria, protocol v2.
#[cfg(test)]
mod authentication_tests;
mod rate;
mod salamander;
use crate::timing::{self, Phase};
use crate::{Result, Target};
use bytes::Bytes;
use ring::rand::{SecureRandom, SystemRandom};
use std::{
    collections::HashMap,
    future::poll_fn,
    io,
    pin::Pin,
    sync::{
        Arc, Mutex,
        atomic::{AtomicU16, Ordering},
    },
    task::{Context, Poll},
    time::Duration,
};
use swirl_dns::Resolver;
use swirl_subscription::Hysteria2;
use swirl_transport::{BoxStream, quic};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, ReadBuf},
    time::{Instant, timeout_at},
};

const MAX_ADDRESS: usize = 2048;
const MAX_MESSAGE: usize = 2048;
const MAX_PADDING: usize = 4096;
const MAX_UDP: usize = 65507;
const MAX_ASSEMBLIES: usize = 16;
const ASSEMBLY_TTL: Duration = Duration::from_secs(5);

struct Task(tokio::task::JoinHandle<()>);
impl Drop for Task {
    fn drop(&mut self) {
        self.0.abort();
    }
}

/// One authenticated QUIC session. Its HTTP/3 handles stay alive until all
/// active native streams are dropped, avoiding premature H3 connection close.
pub struct Session {
    transport: Arc<quic::Session>,
    _requester: Mutex<h3::client::SendRequest<h3_quinn::OpenStreams, Bytes>>,
    _driver: Task,
    pub udp_enabled: bool,
}

impl Drop for Session {
    fn drop(&mut self) {
        self.transport.connection.close(0x100u32.into(), b"");
    }
}

async fn bounded<T>(
    deadline: Instant,
    code: &'static str,
    operation: impl Future<Output = Result<T>>,
) -> Result<T> {
    timeout_at(deadline, operation).await.map_err(|_| code)?
}

fn random<const N: usize>() -> Result<[u8; N]> {
    let mut value = [0; N];
    SystemRandom::new()
        .fill(&mut value)
        .map_err(|_| "Hysteria2Random")?;
    Ok(value)
}

fn padding() -> Result<String> {
    use base64::Engine;
    Ok(base64::engine::general_purpose::STANDARD.encode(random::<24>()?))
}

fn authentication_finish(result: std::result::Result<(), h3::error::StreamError>) -> Result<()> {
    match result {
        Ok(()) => Ok(()),
        // The header-only auth request can receive an early response. RFC 9114
        // section 4.1 permits the peer to stop the request direction with
        // H3_NO_ERROR; h3 can observe that while writing its final GREASE frame.
        // This only permits reading the response, never authenticates it.
        Err(h3::error::StreamError::RemoteTerminate {
            code: h3::error::Code::H3_NO_ERROR,
            ..
        }) => Ok(()),
        Err(_) => Err("Hysteria2AuthenticationWrite"),
    }
}

/// Validate credentials and certificate material before resolving the proxy.
pub fn validate(config: &Hysteria2) -> Result<()> {
    config.validate()?;
    quic::validate(
        quic::TlsOptions {
            tls: &config.tls,
            insecure: config.insecure,
            pin_sha256: config.pin_sha256.as_deref(),
        },
        Some(b"h3"),
        "cubic",
    )
}

impl Session {
    pub async fn connect(
        config: &Hysteria2,
        resolver: &Resolver,
        deadline: Instant,
    ) -> Result<Arc<Self>> {
        validate(config)?;
        let addresses = bounded(
            deadline,
            "Hysteria2DnsTimeout",
            timing::measure(
                Phase::Resolution,
                resolver.resolve(&config.host, config.port),
            ),
        )
        .await?;
        let options = quic::TlsOptions {
            tls: &config.tls,
            insecure: config.insecure,
            pin_sha256: config.pin_sha256.as_deref(),
        };
        let (upload_rate, download_rate) = config.bandwidth_bytes()?;
        let upload_limit = rate::Limit::new(upload_rate);
        let socket_limit = upload_limit.clone();
        let password = config
            .obfs_password
            .as_ref()
            .map(|password| zeroize::Zeroizing::new(password.as_bytes().to_vec()));
        let transport = timing::measure(
            Phase::Quic,
            quic::connect_with_socket_wrapper(
                &addresses,
                options,
                Some(b"h3"),
                "cubic",
                deadline,
                &move |socket| {
                    // Apply pacing outside the obfuscator so its salt bytes count
                    // toward the negotiated wire rate as well.
                    let socket = rate::Socket::wrap(socket, socket_limit.clone());
                    match &password {
                        Some(password) => salamander::Socket::wrap(socket, password),
                        None => socket,
                    }
                },
            ),
        )
        .await?;
        let (mut driver, mut requester) = timing::measure(
            Phase::TransportSetup,
            bounded(deadline, "Hysteria2Http3Timeout", async {
                h3::client::builder()
                    .max_field_section_size(16384)
                    .build(h3_quinn::Connection::new(transport.connection.clone()))
                    .await
                    .map_err(|_| "Hysteria2Http3Setup")
            }),
        )
        .await?;
        let driver = Task(tokio::spawn(async move {
            let _ = poll_fn(|context| driver.poll_close(context)).await;
        }));
        let result = timing::measure(
            Phase::AuthenticationExchange,
            bounded(deadline, "Hysteria2AuthenticationTimeout", async {
                let request = http::Request::builder()
                    .method(http::Method::POST)
                    .uri("https://hysteria/auth")
                    .header("hysteria-auth", &config.password)
                    // Zero negotiates automatic congestion control. Nonzero
                    // values are the receive limit, already converted to bytes/s.
                    .header("hysteria-cc-rx", download_rate.to_string())
                    .header("hysteria-padding", padding()?)
                    .body(())
                    .map_err(|_| "Hysteria2AuthenticationParameters")?;
                let mut stream = requester
                    .send_request(request)
                    .await
                    .map_err(|_| "Hysteria2AuthenticationWrite")?;
                authentication_finish(stream.finish().await)?;
                let response = stream
                    .recv_response()
                    .await
                    .map_err(|_| "Hysteria2AuthenticationRead")?;
                if response.status().as_u16() != 233 {
                    return Err("Hysteria2AuthenticationRejected");
                }
                let headers = response.headers();
                let udp = match headers
                    .get("hysteria-udp")
                    .and_then(|value| value.to_str().ok())
                {
                    Some("true") => true,
                    Some("false") => false,
                    _ => return Err("Hysteria2AuthenticationResponse"),
                };
                let server_rate = match headers
                    .get("hysteria-cc-rx")
                    .and_then(|value| value.to_str().ok())
                {
                    Some("auto") => 0,
                    Some(value)
                        if !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit()) =>
                    {
                        value
                            .parse::<u64>()
                            .map_err(|_| "Hysteria2AuthenticationResponse")?
                    }
                    _ => return Err("Hysteria2AuthenticationResponse"),
                };
                // Cubic is retained for congestion response in every mode. This
                // wire-rate ceiling honours client/server bandwidth limits; it is
                // deliberately not advertised as the Brutal controller.
                upload_limit.set(match (upload_rate, server_rate) {
                    (0, server) => server,
                    (client, 0) => client,
                    (client, server) => client.min(server),
                });
                // Authentication has no useful response body. Drop its stream;
                // retain the SendRequest owner because h3 closes on its last drop.
                Ok(udp && config.udp)
            }),
        )
        .await;
        let udp_enabled = match result {
            Ok(value) => value,
            Err(error) => {
                transport.connection.close(0x101u32.into(), b"");
                return Err(error);
            }
        };
        timing::authentication_response_accepted();
        Ok(Arc::new(Self {
            transport,
            _requester: Mutex::new(requester),
            _driver: driver,
            udp_enabled,
        }))
    }

    pub async fn tcp(self: &Arc<Self>, target: &Target, deadline: Instant) -> Result<BoxStream> {
        let address = target.authority();
        Target::parse(&address, None)?;
        if address.len() > MAX_ADDRESS {
            return Err("Hysteria2AddressLength");
        }
        timing::measure(
            Phase::ProxyConnectExchange,
            bounded(deadline, "Hysteria2StreamTimeout", async {
                let (mut send, mut recv) = self
                    .transport
                    .connection
                    .open_bi()
                    .await
                    .map_err(|_| "Hysteria2StreamOpen")?;
                let mut request = Vec::with_capacity(address.len() + 64);
                put_varint(0x401, &mut request)?;
                put_varint(address.len() as u64, &mut request)?;
                request.extend(address.as_bytes());
                let padding = padding()?;
                put_varint(padding.len() as u64, &mut request)?;
                request.extend(padding.as_bytes());
                send.write_all(&request)
                    .await
                    .map_err(|_| "Hysteria2RequestWrite")?;
                read_tcp_response(&mut recv).await?;
                Ok(Box::new(Stream {
                    stream: quic::Stream::new(self.transport.clone(), send, recv),
                    _session: self.clone(),
                }) as BoxStream)
            }),
        )
        .await
    }
}

pub async fn connect(
    config: &Hysteria2,
    target: &Target,
    resolver: &Resolver,
    limit: Duration,
) -> Result<BoxStream> {
    let deadline = Instant::now() + limit;
    Session::connect(config, resolver, deadline)
        .await?
        .tcp(target, deadline)
        .await
}

struct Stream {
    stream: quic::Stream,
    _session: Arc<Session>,
}
impl AsyncRead for Stream {
    fn poll_read(
        mut self: Pin<&mut Self>,
        context: &mut Context<'_>,
        output: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        Pin::new(&mut self.stream).poll_read(context, output)
    }
}
impl AsyncWrite for Stream {
    fn poll_write(
        mut self: Pin<&mut Self>,
        context: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.stream).poll_write(context, bytes)
    }
    fn poll_flush(mut self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.stream).poll_flush(context)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.stream).poll_shutdown(context)
    }
}

async fn read_tcp_response<R: AsyncRead + Unpin>(reader: &mut R) -> Result<()> {
    let status = reader
        .read_u8()
        .await
        .map_err(|_| "Hysteria2ResponseRead")?;
    if status > 1 {
        return Err("Hysteria2ResponseStatus");
    }
    let message_len = read_varint(reader).await?;
    if message_len > MAX_MESSAGE as u64 {
        return Err("Hysteria2ResponseMessageLength");
    }
    let mut discard = [0; MAX_PADDING];
    reader
        .read_exact(&mut discard[..message_len as usize])
        .await
        .map_err(|_| "Hysteria2ResponseRead")?;
    let padding_len = read_varint(reader).await?;
    if padding_len > MAX_PADDING as u64 {
        return Err("Hysteria2ResponsePaddingLength");
    }
    reader
        .read_exact(&mut discard[..padding_len as usize])
        .await
        .map_err(|_| "Hysteria2ResponseRead")?;
    if status == 0 {
        Ok(())
    } else {
        Err("Hysteria2TargetRejected")
    }
}

fn put_varint(value: u64, output: &mut Vec<u8>) -> Result<()> {
    match value {
        0..=63 => output.push(value as u8),
        64..=16383 => output.extend(((value as u16) | 0x4000).to_be_bytes()),
        16384..=1073741823 => output.extend(((value as u32) | 0x80000000).to_be_bytes()),
        1073741824..=4611686018427387903 => {
            output.extend((value | 0xc000000000000000).to_be_bytes())
        }
        _ => return Err("Hysteria2VarintOverflow"),
    }
    Ok(())
}

async fn read_varint<R: AsyncRead + Unpin>(reader: &mut R) -> Result<u64> {
    let first = reader.read_u8().await.map_err(|_| "Hysteria2VarintRead")?;
    let mut value = u64::from(first & 0x3f);
    for _ in 1..(1 << (first >> 6)) {
        value =
            (value << 8) | u64::from(reader.read_u8().await.map_err(|_| "Hysteria2VarintRead")?);
    }
    Ok(value)
}

fn take_varint(input: &mut &[u8]) -> Result<u64> {
    let first = *input.first().ok_or("Hysteria2DatagramTruncated")?;
    let length = 1usize << (first >> 6);
    if input.len() < length {
        return Err("Hysteria2DatagramTruncated");
    }
    let mut value = u64::from(first & 0x3f);
    for byte in &input[1..length] {
        value = (value << 8) | u64::from(*byte);
    }
    *input = &input[length..];
    Ok(value)
}

struct Fragment<'a> {
    session: u32,
    packet: u16,
    index: u8,
    count: u8,
    address: &'a str,
    payload: &'a [u8],
}
fn decode_fragment(mut input: &[u8]) -> Result<Fragment<'_>> {
    if input.len() < 9 {
        return Err("Hysteria2DatagramTruncated");
    }
    let session = u32::from_be_bytes(
        input[..4]
            .try_into()
            .map_err(|_| "Hysteria2DatagramTruncated")?,
    );
    let packet = u16::from_be_bytes(
        input[4..6]
            .try_into()
            .map_err(|_| "Hysteria2DatagramTruncated")?,
    );
    let index = input[6];
    let count = input[7];
    if count == 0 || (count != 1 && index >= count) {
        return Err("Hysteria2FragmentIndex");
    }
    input = &input[8..];
    let address_len = take_varint(&mut input)?;
    if address_len == 0 || address_len > MAX_ADDRESS as u64 || address_len >= input.len() as u64 {
        return Err("Hysteria2DatagramAddress");
    }
    let address = std::str::from_utf8(&input[..address_len as usize])
        .map_err(|_| "Hysteria2DatagramAddress")?;
    Target::parse(address, None)?;
    let payload = &input[address_len as usize..];
    if payload.len() > MAX_UDP {
        return Err("Hysteria2DatagramLength");
    }
    Ok(Fragment {
        session,
        packet,
        index,
        count,
        address,
        payload,
    })
}

struct Assembly {
    created: Instant,
    address: String,
    fragments: Vec<Option<Vec<u8>>>,
    bytes: usize,
}
#[derive(Default)]
struct Reassembly {
    entries: HashMap<u16, Assembly>,
}
impl Reassembly {
    fn push(&mut self, fragment: Fragment<'_>, now: Instant) -> Result<Option<(Target, Vec<u8>)>> {
        self.entries
            .retain(|_, value| now.duration_since(value.created) < ASSEMBLY_TTL);
        if fragment.count == 1 {
            return Ok(Some((
                Target::parse(fragment.address, None)?,
                fragment.payload.to_vec(),
            )));
        }
        if !self.entries.contains_key(&fragment.packet) && self.entries.len() >= MAX_ASSEMBLIES {
            return Err("Hysteria2ReassemblyLimit");
        }
        let entry = self
            .entries
            .entry(fragment.packet)
            .or_insert_with(|| Assembly {
                created: now,
                address: fragment.address.into(),
                fragments: vec![None; fragment.count as usize],
                bytes: 0,
            });
        if entry.address != fragment.address || entry.fragments.len() != fragment.count as usize {
            self.entries.remove(&fragment.packet);
            return Err("Hysteria2FragmentConflict");
        }
        let slot = &mut entry.fragments[fragment.index as usize];
        if let Some(previous) = slot {
            if previous != fragment.payload {
                self.entries.remove(&fragment.packet);
                return Err("Hysteria2FragmentConflict");
            }
            return Ok(None);
        }
        entry.bytes += fragment.payload.len();
        if entry.bytes > MAX_UDP {
            self.entries.remove(&fragment.packet);
            return Err("Hysteria2ReassemblyLength");
        }
        *slot = Some(fragment.payload.to_vec());
        if entry.fragments.iter().any(Option::is_none) {
            return Ok(None);
        }
        let entry = self
            .entries
            .remove(&fragment.packet)
            .ok_or("Hysteria2ReassemblyState")?;
        let mut payload = Vec::with_capacity(entry.bytes);
        for fragment in entry.fragments.into_iter().flatten() {
            payload.extend(fragment);
        }
        Ok(Some((Target::parse(&entry.address, None)?, payload)))
    }
}

/// A native Hysteria UDP association. One session owns exactly one datagram
/// reader; caller cancellation drops its H3 task, QUIC connection and endpoint.
pub struct UdpAssociation {
    session: Arc<Session>,
    id: u32,
    packet: AtomicU16,
    reassembly: Reassembly,
}
impl UdpAssociation {
    pub async fn connect(config: &Hysteria2, resolver: &Resolver, limit: Duration) -> Result<Self> {
        if !config.udp {
            return Err("Hysteria2UdpDisabled");
        }
        let session = Session::connect(config, resolver, Instant::now() + limit).await?;
        if !session.udp_enabled {
            return Err("Hysteria2UdpNotNegotiated");
        }
        Ok(Self {
            session,
            id: u32::from_be_bytes(random()?),
            packet: AtomicU16::new(u16::from_be_bytes(random()?)),
            reassembly: Reassembly::default(),
        })
    }

    pub async fn send(&self, target: &Target, payload: &[u8]) -> Result<()> {
        if payload.is_empty() || payload.len() > MAX_UDP {
            return Err("Hysteria2DatagramLength");
        }
        let address = target.authority();
        Target::parse(&address, None)?;
        if address.len() > MAX_ADDRESS {
            return Err("Hysteria2DatagramAddress");
        }
        let mut address_header = Vec::with_capacity(address.len() + 8);
        put_varint(address.len() as u64, &mut address_header)?;
        address_header.extend(address.as_bytes());
        let maximum = self
            .session
            .transport
            .connection
            .max_datagram_size()
            .ok_or("Hysteria2DatagramUnavailable")?;
        let capacity = maximum
            .checked_sub(8 + address_header.len())
            .filter(|size| *size != 0)
            .ok_or("Hysteria2DatagramMtu")?;
        let count = payload.len().div_ceil(capacity);
        if count > 255 {
            return Err("Hysteria2FragmentCount");
        }
        let packet = self.packet.fetch_add(1, Ordering::Relaxed);
        for (index, part) in payload.chunks(capacity).enumerate() {
            let mut encoded = Vec::with_capacity(8 + address_header.len() + part.len());
            encoded.extend(self.id.to_be_bytes());
            encoded.extend(packet.to_be_bytes());
            encoded.extend([index as u8, count as u8]);
            encoded.extend(&address_header);
            encoded.extend(part);
            self.session
                .transport
                .connection
                .send_datagram_wait(encoded.into())
                .await
                .map_err(|_| "Hysteria2DatagramSend")?;
        }
        Ok(())
    }

    pub async fn recv(&mut self) -> Result<(Target, Vec<u8>)> {
        let mut discarded = 0;
        loop {
            let datagram = self
                .session
                .transport
                .connection
                .read_datagram()
                .await
                .map_err(|_| "Hysteria2DatagramReceive")?;
            if let Ok(fragment) = decode_fragment(&datagram)
                && fragment.session == self.id
                && let Ok(Some(packet)) = self.reassembly.push(fragment, Instant::now())
            {
                return Ok(packet);
            }
            discarded += 1;
            if discarded % 32 == 0 {
                tokio::task::yield_now().await;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn varint_boundaries_match_quic_encoding() {
        for value in [
            0,
            63,
            64,
            16383,
            16384,
            1073741823,
            1073741824,
            4611686018427387903,
        ] {
            let mut encoded = Vec::new();
            put_varint(value, &mut encoded).unwrap();
            assert_eq!(take_varint(&mut encoded.as_slice()).unwrap(), value);
            assert_eq!(read_varint(&mut encoded.as_slice()).await.unwrap(), value);
        }
        let mut encoded = Vec::new();
        put_varint(0x401, &mut encoded).unwrap();
        assert_eq!(encoded, [0x44, 0x01]);
        assert!(put_varint(1 << 62, &mut encoded).is_err());
        assert!(take_varint(&mut [0xc0, 0].as_slice()).is_err());
    }

    #[tokio::test]
    async fn response_parser_bounds_and_rejection() {
        assert_eq!(read_tcp_response(&mut [0, 0, 0].as_slice()).await, Ok(()));
        assert_eq!(
            read_tcp_response(&mut [1, 0, 0].as_slice()).await,
            Err("Hysteria2TargetRejected")
        );
        assert_eq!(
            read_tcp_response(&mut [2].as_slice()).await,
            Err("Hysteria2ResponseStatus")
        );
        let mut response = vec![0];
        put_varint(2049, &mut response).unwrap();
        assert_eq!(
            read_tcp_response(&mut response.as_slice()).await,
            Err("Hysteria2ResponseMessageLength")
        );
        let mut response = vec![0, 0];
        put_varint(4097, &mut response).unwrap();
        assert_eq!(
            read_tcp_response(&mut response.as_slice()).await,
            Err("Hysteria2ResponsePaddingLength")
        );
    }

    #[test]
    fn reordered_fragments_duplicates_conflicts_and_expiry() {
        let now = Instant::now();
        let mut state = Reassembly::default();
        let fragment = |index, payload| Fragment {
            session: 1,
            packet: 2,
            index,
            count: 2,
            address: "[::1]:53",
            payload,
        };
        assert!(state.push(fragment(1, b"b"), now).unwrap().is_none());
        assert!(state.push(fragment(1, b"b"), now).unwrap().is_none());
        let (target, bytes) = state.push(fragment(0, b"a"), now).unwrap().unwrap();
        assert_eq!(target.host, "::1");
        assert_eq!(bytes, b"ab");
        state.push(fragment(0, b"a"), now).unwrap();
        assert_eq!(
            state.push(fragment(0, b"x"), now).err(),
            Some("Hysteria2FragmentConflict")
        );
        state.push(fragment(0, b"a"), now).unwrap();
        assert!(
            state
                .push(fragment(1, b"b"), now + ASSEMBLY_TTL)
                .unwrap()
                .is_none()
        );
    }

    #[test]
    fn reassembly_memory_and_malformed_datagrams_are_bounded() {
        let now = Instant::now();
        let mut state = Reassembly::default();
        for packet in 0..MAX_ASSEMBLIES as u16 {
            assert!(
                state
                    .push(
                        Fragment {
                            session: 1,
                            packet,
                            index: 0,
                            count: 2,
                            address: "host.test:53",
                            payload: b"a"
                        },
                        now
                    )
                    .unwrap()
                    .is_none()
            );
        }
        assert_eq!(
            state
                .push(
                    Fragment {
                        session: 1,
                        packet: 99,
                        index: 0,
                        count: 2,
                        address: "host.test:53",
                        payload: b"a"
                    },
                    now
                )
                .err(),
            Some("Hysteria2ReassemblyLimit")
        );
        for input in [
            vec![],
            vec![0; 9],
            vec![0, 0, 0, 0, 0, 0, 2, 2, 0],
            vec![0, 0, 0, 0, 0, 0, 0, 1, 0xff],
        ] {
            assert!(decode_fragment(&input).is_err());
        }
    }
}
