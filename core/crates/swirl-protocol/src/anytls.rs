//! Native AnyTLS v2, with v1 negotiation compatibility, bounded idle session
//! reuse and server padding updates. Wire facts: anytls/anytls-go protocol.md,
//! upstream fd6167acd6d73b9fa3e607659951847fbc9e6c50. No upstream runtime is used.
use crate::{Result, Target, dial::within};
use md5::{Digest, Md5};
use ring::{
    digest,
    rand::{SecureRandom, SystemRandom},
};
use std::{
    collections::{BTreeMap, VecDeque},
    io,
    pin::Pin,
    sync::{
        Arc, LazyLock, Mutex, Weak,
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
    },
    task::{Context, Poll},
    time::Duration,
};
use swirl_dns::Resolver;
use swirl_subscription::{
    AnyTls,
    anytls::{SessionOwner, SessionResource},
};
use swirl_transport::{BoxStream, egress::EgressToken};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, DuplexStream, ReadBuf},
    sync::{OwnedSemaphorePermit, Semaphore, mpsc, oneshot},
    task::AbortHandle,
    time::{Instant, timeout, timeout_at},
};
use zeroize::Zeroizing;

const DEFAULT_PADDING: &str = "stop=8\n0=30-30\n1=100-400\n2=400-500,c,500-1000,c,500-1000,c,500-1000,c,500-1000\n3=9-9,500-1000\n4=500-1000\n5=500-1000\n6=500-1000\n7=500-1000";
const MAX_SESSIONS: usize = 16;
const IO_LIMIT: Duration = Duration::from_secs(5);
const SYN_LIMIT: Duration = Duration::from_secs(3);

#[derive(Clone)]
enum Part {
    Check,
    Range(u16, u16),
}
#[derive(Clone)]
struct Padding {
    stop: u32,
    plans: BTreeMap<u32, Vec<Part>>,
    md5: String,
}
impl Padding {
    fn parse(raw: &[u8]) -> Result<Self> {
        if raw.len() > 4096 {
            return Err("AnyTlsPaddingLimit");
        }
        let text = std::str::from_utf8(raw).map_err(|_| "AnyTlsPaddingInvalid")?;
        let mut stop = None;
        let mut plans = BTreeMap::new();
        for line in text.lines() {
            let (key, value) = line.split_once('=').ok_or("AnyTlsPaddingInvalid")?;
            if key == "stop" {
                if stop.is_some() {
                    return Err("AnyTlsPaddingInvalid");
                }
                stop = Some(value.parse::<u32>().map_err(|_| "AnyTlsPaddingInvalid")?);
                continue;
            }
            let index = key.parse::<u32>().map_err(|_| "AnyTlsPaddingInvalid")?;
            if index >= 64 || plans.contains_key(&index) {
                return Err("AnyTlsPaddingLimit");
            }
            let mut parts = Vec::new();
            for part in value.split(',') {
                if parts.len() >= 16 {
                    return Err("AnyTlsPaddingLimit");
                }
                if part == "c" {
                    parts.push(Part::Check);
                    continue;
                }
                let (low, high) = part.split_once('-').ok_or("AnyTlsPaddingInvalid")?;
                let a = low.parse::<u16>().map_err(|_| "AnyTlsPaddingInvalid")?;
                let b = high.parse::<u16>().map_err(|_| "AnyTlsPaddingInvalid")?;
                if a == 0 || b == 0 || a > 16384 || b > 16384 {
                    return Err("AnyTlsPaddingLimit");
                }
                parts.push(Part::Range(a.min(b), a.max(b)));
            }
            plans.insert(index, parts);
        }
        let stop = stop.ok_or("AnyTlsPaddingInvalid")?;
        if stop > 64 {
            return Err("AnyTlsPaddingLimit");
        }
        Ok(Self {
            stop,
            plans,
            md5: format!("{:x}", Md5::digest(raw)),
        })
    }
    fn auth_length(&self) -> Result<usize> {
        match self.plans.get(&0).and_then(|parts| parts.first()) {
            Some(Part::Range(low, high)) => random_range(*low, *high),
            _ => Ok(0),
        }
    }
}
fn random_range(low: u16, high: u16) -> Result<usize> {
    if low == high {
        return Ok(usize::from(low));
    }
    let width = u32::from(high - low);
    let ceiling = u32::MAX - u32::MAX % width;
    loop {
        let mut bytes = [0; 4];
        SystemRandom::new()
            .fill(&mut bytes)
            .map_err(|_| "AnyTlsRandom")?;
        let value = u32::from_ne_bytes(bytes);
        if value < ceiling {
            return Ok(usize::from(low) + (value % width) as usize);
        }
    }
}
fn frame(command: u8, id: u32, data: &[u8]) -> Result<Vec<u8>> {
    let size = u16::try_from(data.len()).map_err(|_| "AnyTlsFrameLimit")?;
    let mut wire = Vec::with_capacity(data.len() + 7);
    wire.push(command);
    wire.extend(id.to_be_bytes());
    wire.extend(size.to_be_bytes());
    wire.extend(data);
    Ok(wire)
}
struct Frame {
    command: u8,
    id: u32,
    data: Vec<u8>,
}
async fn read_frame<R: AsyncRead + Unpin>(reader: &mut R) -> Result<Frame> {
    let mut header = [0; 7];
    reader
        .read_exact(&mut header[..1])
        .await
        .map_err(|_| "AnyTlsSessionClosed")?;
    timeout(IO_LIMIT, async {
        reader
            .read_exact(&mut header[1..])
            .await
            .map_err(|_| "AnyTlsFrameRead")?;
        let command = header[0];
        let id = u32::from_be_bytes(header[1..5].try_into().expect("fixed header"));
        let length = usize::from(u16::from_be_bytes([header[5], header[6]]));
        if command > 10 || matches!(command, 1 | 3 | 8 | 9) && length != 0 {
            return Err("AnyTlsFrameInvalid");
        }
        if matches!(command, 4 | 5 | 6 | 10) && (id != 0 || length > 4096) {
            return Err("AnyTlsControlInvalid");
        }
        let mut data = vec![0; length];
        reader
            .read_exact(&mut data)
            .await
            .map_err(|_| "AnyTlsFrameRead")?;
        Ok(Frame { command, id, data })
    })
    .await
    .map_err(|_| "AnyTlsFrameTimeout")?
}
async fn write_packet<W: AsyncWrite + Unpin>(
    writer: &mut W,
    data: &[u8],
    padding: &Padding,
    packet: &mut u32,
) -> Result<()> {
    *packet = packet.saturating_add(1);
    timeout(IO_LIMIT, async {
        let mut remaining = data;
        if *packet < padding.stop {
            for part in padding.plans.get(packet).into_iter().flatten() {
                let size = match part {
                    Part::Check if remaining.is_empty() => break,
                    Part::Check => continue,
                    Part::Range(low, high) => random_range(*low, *high)?,
                };
                if remaining.len() > size {
                    writer
                        .write_all(&remaining[..size])
                        .await
                        .map_err(|_| "AnyTlsWrite")?;
                    writer.flush().await.map_err(|_| "AnyTlsWrite")?;
                    remaining = &remaining[size..];
                } else {
                    let mut part = remaining.to_vec();
                    let waste = if remaining.is_empty() {
                        Some(size)
                    } else {
                        size.checked_sub(remaining.len() + 7).filter(|n| *n > 0)
                    };
                    if let Some(waste) = waste {
                        part.extend(frame(0, 0, &vec![0; waste])?);
                    }
                    writer.write_all(&part).await.map_err(|_| "AnyTlsWrite")?;
                    writer.flush().await.map_err(|_| "AnyTlsWrite")?;
                    remaining = &[];
                }
            }
        }
        if !remaining.is_empty() {
            writer
                .write_all(remaining)
                .await
                .map_err(|_| "AnyTlsWrite")?;
            writer.flush().await.map_err(|_| "AnyTlsWrite")?;
        }
        Ok(())
    })
    .await
    .map_err(|_| "AnyTlsWriteTimeout")?
}

struct Client {
    padding: Mutex<Padding>,
    sessions: Mutex<Vec<Arc<Session>>>,
    next: AtomicU64,
    closed: AtomicBool,
    slots: Arc<Semaphore>,
    pending: AtomicUsize,
}
impl Client {
    fn reserve(self: &Arc<Self>) -> Result<ClientReservation> {
        let _sessions = self.sessions.lock().map_err(|_| "AnyTlsSessionPool")?;
        if self.closed.load(Ordering::Acquire) {
            return Err("AnyTlsOwnerClosed");
        }
        if self.pending.load(Ordering::Relaxed) >= MAX_SESSIONS {
            return Err("AnyTlsSessionLimit");
        }
        self.pending.fetch_add(1, Ordering::Release);
        Ok(ClientReservation(self.clone()))
    }
    fn retire_if_unused(&self) {
        let mut sessions = self
            .sessions
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        sessions.retain(|session| !session.closed.load(Ordering::Acquire));
        if sessions.is_empty() && self.pending.load(Ordering::Acquire) == 0 {
            self.closed.store(true, Ordering::Release);
        }
    }
}
struct ClientReservation(Arc<Client>);
impl std::ops::Deref for ClientReservation {
    type Target = Arc<Client>;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}
impl Drop for ClientReservation {
    fn drop(&mut self) {
        self.0.pending.fetch_sub(1, Ordering::AcqRel);
        self.0.retire_if_unused();
    }
}
impl SessionResource for Client {
    fn is_closed(&self) -> bool {
        self.closed.load(Ordering::Acquire)
    }
    fn close(&self) {
        self.closed.store(true, Ordering::Release);
        for session in self
            .sessions
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .drain(..)
        {
            session.close();
        }
    }
}
impl Drop for Client {
    fn drop(&mut self) {
        self.close();
    }
}
struct Session {
    sequence: u64,
    busy: AtomicBool,
    closed: AtomicBool,
    open: mpsc::Sender<Open>,
    task: Mutex<Option<AbortHandle>>,
    idle: Mutex<Instant>,
    egress: EgressToken,
    _slot: OwnedSemaphorePermit,
}
impl Session {
    fn close(&self) {
        self.closed.store(true, Ordering::Release);
        if let Some(task) = self.task.lock().unwrap_or_else(|e| e.into_inner()).take() {
            task.abort();
        }
    }
}
impl Drop for Session {
    fn drop(&mut self) {
        self.close();
    }
}
struct PoolEntry {
    owner: Weak<SessionOwner>,
    runtime: tokio::runtime::Id,
    egress: EgressToken,
    digest: [u8; 32],
    client: Arc<Client>,
}
static CLIENTS: LazyLock<Mutex<VecDeque<PoolEntry>>> =
    LazyLock::new(|| Mutex::new(VecDeque::new()));

fn client(
    config: &AnyTls,
    egress: EgressToken,
    addresses: &[std::net::SocketAddr],
) -> Result<ClientReservation> {
    let mut serialized = Zeroizing::new(config_key(config));
    for address in addresses {
        let value = address.to_string();
        serialized.extend((value.len() as u64).to_be_bytes());
        serialized.extend(value.as_bytes());
    }
    let mut hash = [0; 32];
    hash.copy_from_slice(digest::digest(&digest::SHA256, &serialized).as_ref());
    let runtime = tokio::runtime::Handle::current().id();
    egress
        .with_current(|| {
            let mut pool = CLIENTS.lock().map_err(|_| "AnyTlsClientPool")?;
            pool.retain(|entry| {
                entry.owner.strong_count() != 0 && !entry.client.closed.load(Ordering::Acquire)
            });
            if let Some(entry) = pool.iter().find(|entry| {
                entry.runtime == runtime
                    && entry.egress == egress
                    && entry.digest == hash
                    && Weak::ptr_eq(&entry.owner, &Arc::downgrade(&config.session_owner))
            }) {
                match entry.client.reserve() {
                    Ok(reservation) => return Ok(reservation),
                    // Its last actor may have retired between registry lookup
                    // and reservation. No socket or protocol write happened.
                    Err("AnyTlsOwnerClosed") => (),
                    Err(code) => return Err(code),
                }
            }
            pool.retain(|entry| !entry.client.closed.load(Ordering::Acquire));
            if pool.len() >= 128 {
                return Err("AnyTlsClientLimit");
            }
            let client = Arc::new(Client {
                padding: Mutex::new(Padding::parse(DEFAULT_PADDING.as_bytes())?),
                sessions: Mutex::new(Vec::new()),
                next: AtomicU64::new(1),
                closed: AtomicBool::new(false),
                slots: Arc::new(Semaphore::new(MAX_SESSIONS)),
                pending: AtomicUsize::new(1),
            });
            let resource: Arc<dyn SessionResource> = client.clone();
            config.session_owner.register(Arc::downgrade(&resource))?;
            pool.push_back(PoolEntry {
                owner: Arc::downgrade(&config.session_owner),
                runtime,
                egress,
                digest: hash,
                client: client.clone(),
            });
            Ok(ClientReservation(client))
        })
        .map_err(|_| "AnyTlsEgressChanged")?
}
fn config_key(config: &AnyTls) -> Vec<u8> {
    // Length prefixes keep every trust/credential boundary distinct without
    // retaining password strings in the registry key.
    let mut key = Vec::new();
    for field in [&config.host, &config.password, &config.tls.server_name] {
        key.extend((field.len() as u64).to_be_bytes());
        key.extend(field.as_bytes());
    }
    key.extend(config.port.to_be_bytes());
    key.extend(config.idle_session_timeout_seconds.to_be_bytes());
    key.extend((config.tls.alpn.len() as u64).to_be_bytes());
    for alpn in &config.tls.alpn {
        key.extend((alpn.len() as u64).to_be_bytes());
        key.extend(alpn.as_bytes());
    }
    key.push(u8::from(config.tls.ca_der_base64.is_some()));
    if let Some(ca) = &config.tls.ca_der_base64 {
        key.extend((ca.len() as u64).to_be_bytes());
        key.extend(ca.as_bytes());
    }
    key
}

struct Open {
    target: Target,
    initial_data: Vec<u8>,
    stream: DuplexStream,
    ready: oneshot::Sender<Result<()>>,
    error: Arc<Mutex<Option<&'static str>>>,
}
struct Active {
    id: u32,
    stream: DuplexStream,
    error: Arc<Mutex<Option<&'static str>>>,
    ack_deadline: Option<Instant>,
    started: Instant,
    ready: Option<oneshot::Sender<Result<()>>>,
}
struct AnyStream {
    stream: DuplexStream,
    error: Arc<Mutex<Option<&'static str>>>,
    _owner: Arc<SessionOwner>,
}
impl AsyncRead for AnyStream {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let before = buf.filled().len();
        let result = Pin::new(&mut self.stream).poll_read(cx, buf);
        if matches!(result, Poll::Ready(Ok(())))
            && buf.filled().len() == before
            && let Some(code) = *self.error.lock().unwrap_or_else(|e| e.into_inner())
        {
            return Poll::Ready(Err(io::Error::other(code)));
        }
        result
    }
}
impl AsyncWrite for AnyStream {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        data: &[u8],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.stream).poll_write(cx, data)
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.stream).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.stream).poll_shutdown(cx)
    }
}
struct AbortOnDrop(AbortHandle);
impl Drop for AbortOnDrop {
    fn drop(&mut self) {
        self.0.abort();
    }
}
struct Opening(Arc<Session>, bool);
impl Drop for Opening {
    fn drop(&mut self) {
        if self.1 {
            self.0.close();
        }
    }
}

pub fn validate(config: &AnyTls) -> Result<()> {
    config.validate()?;
    swirl_transport::validate_tls(&config.tls, None)
}
pub async fn connect(
    config: &AnyTls,
    target: &Target,
    resolver: &Resolver,
    limit: Duration,
) -> Result<BoxStream> {
    if target.port == 0 {
        return Err("AnyTlsTarget");
    }
    connect_inner(config, target, Vec::new(), resolver, limit).await
}
pub(crate) async fn connect_udp(
    config: &AnyTls,
    target: &Target,
    resolver: &Resolver,
    limit: Duration,
) -> Result<BoxStream> {
    if !config.udp || target.port == 0 || !swirl_subscription::valid_host(&target.host) {
        return Err("AnyTlsUdpTarget");
    }
    let mut request = vec![1];
    target.encode(&mut request)?;
    // UoT v2 waits for this request before SYNACK. Queue it with the target,
    // otherwise a reused v2 session deadlocks waiting for its acknowledgement.
    connect_inner(
        config,
        &Target {
            host: "sp.v2.udp-over-tcp.arpa".into(),
            port: 0,
        },
        request,
        resolver,
        limit,
    )
    .await
}
async fn connect_inner(
    config: &AnyTls,
    target: &Target,
    initial_data: Vec<u8>,
    resolver: &Resolver,
    limit: Duration,
) -> Result<BoxStream> {
    validate(config)?;
    if !swirl_subscription::valid_host(&target.host)
        || (target.port == 0 && target.host != "sp.v2.udp-over-tcp.arpa")
    {
        return Err("AnyTlsTarget");
    }
    // Pooled sockets cannot migrate to a subsequently installed QA byte guard.
    // Admission also marks this process as used, closing the install/reuse race.
    swirl_transport::egress::check_unmetered_egress()
        .map_err(|_| "PrivateAcceptanceAnyTlsUnsupported")?;
    let deadline = Instant::now() + limit;
    let addresses = within(
        deadline,
        "UpstreamDnsTimeout",
        resolver.resolve(&config.host, config.port),
    )
    .await?;
    let egress = EgressToken::capture(&addresses).map_err(|_| "AnyTlsEgressUnavailable")?;
    let reservation = client(config, egress, &addresses)?;
    let client = reservation.0.clone();
    let selected = {
        let mut sessions = client.sessions.lock().map_err(|_| "AnyTlsSessionPool")?;
        if client.closed.load(Ordering::Acquire) {
            return Err("AnyTlsOwnerClosed");
        }
        sessions.retain(|session| !session.closed.load(Ordering::Acquire));
        let idle = sessions
            .iter()
            .filter(|session| !session.busy.load(Ordering::Acquire))
            .max_by_key(|session| session.sequence)
            .cloned();
        if let Some(session) = &idle {
            session.busy.store(true, Ordering::Release);
        }
        if idle.is_none() && sessions.len() >= MAX_SESSIONS {
            return Err("AnyTlsSessionLimit");
        }
        idle
    };
    let session = if let Some(session) = selected {
        session
    } else {
        let slot = client
            .slots
            .clone()
            .try_acquire_owned()
            .map_err(|_| "AnyTlsSessionLimit")?;
        let tcp = crate::connect_direct_resolved(
            addresses,
            deadline.saturating_duration_since(Instant::now()),
        )
        .await?;
        let mut tls = within(
            deadline,
            "UpstreamTlsTimeout",
            swirl_transport::secure(tcp, &config.tls),
        )
        .await?;
        let padding = client
            .padding
            .lock()
            .map_err(|_| "AnyTlsPaddingState")?
            .clone();
        let mut auth = Zeroizing::new(
            digest::digest(&digest::SHA256, config.password.as_bytes())
                .as_ref()
                .to_vec(),
        );
        let size = padding.auth_length()?;
        auth.extend((size as u16).to_be_bytes());
        let total = auth.len() + size;
        auth.resize(total, 0);
        within(deadline, "AnyTlsAuthenticationTimeout", async {
            tls.write_all(&auth)
                .await
                .map_err(|_| "AnyTlsAuthenticationWrite")?;
            tls.flush().await.map_err(|_| "AnyTlsAuthenticationWrite")
        })
        .await?;
        let (open, requests) = mpsc::channel(1);
        let mut sequence = client.next.load(Ordering::Relaxed);
        loop {
            let next = sequence.checked_add(1).ok_or("AnyTlsSessionIdLimit")?;
            match client.next.compare_exchange_weak(
                sequence,
                next,
                Ordering::Relaxed,
                Ordering::Relaxed,
            ) {
                Ok(_) => break,
                Err(current) => sequence = current,
            }
        }
        let session = Arc::new(Session {
            sequence,
            busy: AtomicBool::new(true),
            closed: AtomicBool::new(false),
            open,
            task: Mutex::new(None),
            idle: Mutex::new(Instant::now()),
            egress,
            _slot: slot,
        });
        let task = tokio::spawn(swirl_transport::egress::inherit_physical_probe_scope(
            run_session(
                tls,
                Arc::downgrade(&client),
                session.clone(),
                requests,
                Duration::from_secs(config.idle_session_timeout_seconds),
                padding,
            ),
        ));
        *session.task.lock().map_err(|_| "AnyTlsSessionState")? = Some(task.abort_handle());
        let mut sessions = client.sessions.lock().map_err(|_| "AnyTlsSessionPool")?;
        if client.closed.load(Ordering::Acquire) || sessions.len() >= MAX_SESSIONS {
            session.close();
            return Err("AnyTlsSessionLimit");
        }
        sessions.push(session.clone());
        session
    };
    let mut opening = Opening(session.clone(), true);
    egress
        .with_current(|| ())
        .map_err(|_| "AnyTlsEgressChanged")?;
    let (stream, server) = tokio::io::duplex(65536);
    let (ready, ack) = oneshot::channel();
    let error = Arc::new(Mutex::new(None));
    let open = Open {
        target: target.clone(),
        initial_data,
        stream: server,
        ready,
        error: error.clone(),
    };
    if !matches!(
        timeout_at(deadline, session.open.send(open)).await,
        Ok(Ok(()))
    ) {
        return Err("AnyTlsOpenTimeout");
    }
    match timeout_at(deadline, ack).await {
        Ok(Ok(Ok(()))) => {
            opening.1 = false;
            Ok(Box::new(AnyStream {
                stream,
                error,
                _owner: config.session_owner.clone(),
            }))
        }
        Ok(Ok(Err(code))) => {
            session.close();
            Err(code)
        }
        _ => {
            session.close();
            Err("AnyTlsOpenTimeout")
        }
    }
}

struct CheckedWriter<W> {
    writer: W,
    egress: EgressToken,
}
impl<W: AsyncWrite + Unpin> AsyncWrite for CheckedWriter<W> {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        data: &[u8],
    ) -> Poll<io::Result<usize>> {
        if let Err(error) = self.egress.with_current(|| ()) {
            return Poll::Ready(Err(error));
        }
        Pin::new(&mut self.writer).poll_write(cx, data)
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if let Err(error) = self.egress.with_current(|| ()) {
            return Poll::Ready(Err(error));
        }
        Pin::new(&mut self.writer).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if let Err(error) = self.egress.with_current(|| ()) {
            return Poll::Ready(Err(error));
        }
        Pin::new(&mut self.writer).poll_shutdown(cx)
    }
}
struct RetireSession {
    client: Weak<Client>,
    session: Arc<Session>,
}
impl Drop for RetireSession {
    fn drop(&mut self) {
        self.session.closed.store(true, Ordering::Release);
        if let Some(client) = self.client.upgrade() {
            client.retire_if_unused();
        }
    }
}
fn run_session(
    tls: BoxStream,
    client: Weak<Client>,
    session: Arc<Session>,
    opens: mpsc::Receiver<Open>,
    idle_timeout: Duration,
    initial_padding: Padding,
) -> impl std::future::Future<Output = ()> {
    // Construct before spawn so runtime cancellation before the first poll also
    // marks the session closed and releases its owner's registry allowance.
    let retirement = RetireSession {
        client: client.clone(),
        session: session.clone(),
    };
    async move {
        let _retirement = retirement;
        session_loop(tls, client, session, opens, idle_timeout, initial_padding).await;
    }
}
async fn session_loop(
    tls: BoxStream,
    client: Weak<Client>,
    session: Arc<Session>,
    mut opens: mpsc::Receiver<Open>,
    idle_timeout: Duration,
    initial_padding: Padding,
) {
    let (mut reader, writer) = tokio::io::split(tls);
    let mut writer = CheckedWriter {
        writer,
        egress: session.egress,
    };
    let (frames, mut received) = mpsc::channel(4);
    let reading = tokio::spawn(async move {
        loop {
            let next = read_frame(&mut reader).await;
            let failed = next.is_err();
            if frames.send(next).await.is_err() || failed {
                return;
            }
        }
    });
    let _reader = AbortOnDrop(reading.abort_handle());
    let mut active: Option<Active> = None;
    let mut last_id = 0u32;
    let mut packet = 0u32;
    let mut peer_version = 1u8;
    let mut settings_received = false;
    let mut settings = Some(
        format!(
            "v=2\nclient=Swirl/{}\npadding-md5={}",
            env!("CARGO_PKG_VERSION"),
            initial_padding.md5
        )
        .into_bytes(),
    );
    let mut buffer = [0; 16384];
    let result:Result<()>=async {loop {
        let Some(client)=client.upgrade() else{return Err("AnyTlsOwnerClosed")};
        if client.closed.load(Ordering::Acquire){return Err("AnyTlsOwnerClosed");}
        let until=match &active {
            Some(active)=>active.ack_deadline,
            None=>Some(*session.idle.lock().unwrap_or_else(|e|e.into_inner())+idle_timeout),
        };
        tokio::select! {
            opened=opens.recv(), if active.is_none()=>{
                let Some(opened)=opened else{return Ok(())};
                last_id=last_id.checked_add(1).ok_or("AnyTlsStreamIdLimit")?;
                session.egress.with_current(||()).map_err(|_| "AnyTlsEgressChanged")?;
                let mut data=Vec::new();if let Some(settings)=settings.take(){data.extend(frame(4,0,&settings)?);}
                data.extend(frame(1,last_id,&[])?);let mut address=Vec::new();opened.target.encode(&mut address)?;address.extend(opened.initial_data);data.extend(frame(2,last_id,&address)?);
                let padding=client.padding.lock().map_err(|_| "AnyTlsPaddingState")?.clone();
                let written=write_packet(&mut writer,&data,&padding,&mut packet).await;
                if let Err(code)=written{let _=opened.ready.send(Err(code));return Err(code);}
                let started=Instant::now();
                let ready=if peer_version>=2{Some(opened.ready)}else{let _=opened.ready.send(Ok(()));None};
                active=Some(Active{id:last_id,stream:opened.stream,error:opened.error,ack_deadline:(peer_version>=2).then(||started+SYN_LIMIT),started,ready});
            }
            incoming=received.recv()=>{
                let frame=incoming.ok_or("AnyTlsSessionClosed")??;
                match frame.command {
                    0=>(),
                    2=>if let Some(active)=&mut active && frame.id==active.id {
                        timeout(IO_LIMIT,active.stream.write_all(&frame.data)).await
                            .map_err(|_| "AnyTlsReceiveBackpressure")?.map_err(|_| "AnyTlsStreamClosed")?;
                    },
                    3=>if active.as_ref().is_some_and(|active|active.id==frame.id){active=None;*session.idle.lock().unwrap_or_else(|e|e.into_inner())=Instant::now();session.busy.store(false,Ordering::Release);},
                    5=>return Err("AnyTlsServerAlert"),
                    6=>{*client.padding.lock().map_err(|_| "AnyTlsPaddingState")?=Padding::parse(&frame.data)?;},
                    7=>if let Some(active)=&mut active && active.id==frame.id {
                        if !frame.data.is_empty(){return Err("AnyTlsConnectRejected");}
                        active.ack_deadline=None;
                        if let Some(ready)=active.ready.take(){let _=ready.send(Ok(()));}
                    },
                    8=>{let padding=client.padding.lock().map_err(|_| "AnyTlsPaddingState")?.clone();write_packet(&mut writer,&crate::anytls::frame(9,frame.id,&[])?,&padding,&mut packet).await?;},
                    9=>(),
                    10=>{
                        if settings_received{return Err("AnyTlsSettingsRepeated");}
                        settings_received=true;
                        let text=std::str::from_utf8(&frame.data).map_err(|_| "AnyTlsSettingsInvalid")?;
                        let mut versions=text.lines().filter_map(|line|line.strip_prefix("v="));
                        let version=versions.next().ok_or("AnyTlsSettingsInvalid")?;
                        if versions.next().is_some(){return Err("AnyTlsSettingsInvalid");}
                        peer_version=version.parse().map_err(|_| "AnyTlsSettingsInvalid")?;
                        if !(1..=2).contains(&peer_version){return Err("AnyTlsSettingsInvalid");}
                        if peer_version>=2 && let Some(active)=&mut active{
                            active.ack_deadline=Some(active.started+SYN_LIMIT);
                        }
                    },
                    _=>return Err("AnyTlsCommandInvalid"),
                }
            }
            read=async {match &mut active{Some(active)=>active.stream.read(&mut buffer).await,None=>std::future::pending().await}}=>{
                let size=read.map_err(|_| "AnyTlsStreamRead")?;
                let id=active.as_ref().ok_or("AnyTlsStreamState")?.id;
                let padding=client.padding.lock().map_err(|_| "AnyTlsPaddingState")?.clone();
                if size==0 {
                    write_packet(&mut writer,&frame(3,id,&[])?,&padding,&mut packet).await?;
                    active=None;*session.idle.lock().unwrap_or_else(|e|e.into_inner())=Instant::now();session.busy.store(false,Ordering::Release);
                }else {write_packet(&mut writer,&frame(2,id,&buffer[..size])?,&padding,&mut packet).await?;}
            }
            _=async{match until{Some(until)=>tokio::time::sleep_until(until).await,None=>std::future::pending().await}}=>{
                return if active.is_none(){Ok(())}else{Err("AnyTlsSynAckTimeout")};
            }
        }
    }}.await;
    if let Some(active) = active
        && let Err(code) = result
    {
        *active.error.lock().unwrap_or_else(|e| e.into_inner()) = Some(code);
        if let Some(ready) = active.ready {
            let _ = ready.send(Err(code));
        }
    }
}

#[cfg(test)]
#[path = "anytls_tests.rs"]
mod tests;
