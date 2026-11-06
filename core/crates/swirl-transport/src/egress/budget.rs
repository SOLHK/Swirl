//! Opt-in private QA process budget, below TLS and protocol framing.
//!
//! Counts bytes accepted by TCP writes and delivered by TCP reads. TCP/IP
//! headers, retransmissions and unread kernel data are outside these counters.
//! The parent must persist the full request reservation before starting this
//! process, including RECEIVE_RESERVATION per permitted connection attempt.
//! This guard never supplies provider billing or persistent task accounting.
//! The independent deadline closes registered streams; cancelling a still
//! pending connect wakes its Tokio future so it can drop the owned socket.
//! An externally supervised process deadline is still required if that runtime
//! stops polling, and only confirmed process exit can settle its reservation.
use socket2::{SockRef, Socket};
use std::{
    future::Future,
    io,
    net::{Shutdown, SocketAddr},
    pin::Pin,
    sync::{Arc, Condvar, Mutex, OnceLock, Weak},
    task::{Context, Poll},
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncRead, AsyncWrite, ReadBuf},
    net::{TcpSocket, TcpStream},
    sync::watch,
};

pub const MAX_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_CONNECTIONS: u32 = 48;
pub const RECEIVE_RESERVATION: u64 = 1024 * 1024;
pub const MAX_TIMEOUT_MS: u32 = 8000;
const RECEIVE_BUFFER: u32 = 64 * 1024;
static GUARD: OnceLock<Arc<TcpQuota>> = OnceLock::new();
static STARTED: Mutex<bool> = Mutex::new(false);

#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize)]
pub struct Snapshot {
    pub byte_limit: u64,
    pub upload: u64,
    pub download: u64,
    pub connection_limit: u32,
    pub connection_attempts: u32,
    pub receive_reservation: u64,
    pub timeout_ms: u32,
    pub timed_out: bool,
    pub stopped: bool,
    pub shutdown_failures: u32,
}

struct State {
    receipt: Snapshot,
    sockets: Vec<Weak<Socket>>,
    deadline: Instant,
    cancelled: watch::Sender<bool>,
    deadline_wakeup: Arc<Condvar>,
}

impl State {
    fn expire_if_due(&mut self) {
        if !self.receipt.stopped && Instant::now() >= self.deadline {
            self.receipt.timed_out = true;
            self.stop();
        }
    }

    fn check(&mut self) -> io::Result<()> {
        // The watchdog also closes idle sockets. This check prevents a late
        // scheduler wake from granting another read/write after the deadline.
        self.expire_if_due();
        if self.receipt.stopped {
            Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "PrivateQuotaStopped",
            ))
        } else {
            Ok(())
        }
    }

    fn remaining(&self) -> u64 {
        self.receipt.byte_limit - self.receipt.upload - self.receipt.download
    }

    fn charge_read(&mut self, received: usize) {
        self.receipt.download += received as u64;
        if self.remaining() == 0 {
            self.stop();
        }
    }

    fn stop(&mut self) {
        if self.receipt.stopped {
            return;
        }
        self.receipt.stopped = true;
        self.cancelled.send_replace(true);
        self.deadline_wakeup.notify_all();
        for socket in self.sockets.iter().filter_map(Weak::upgrade) {
            if let Err(error) = socket.shutdown(Shutdown::Both)
                && error.kind() != io::ErrorKind::NotConnected
            {
                self.receipt.shutdown_failures += 1;
            }
        }
    }
}

pub struct TcpQuota {
    state: Mutex<State>,
    // Only the dedicated synthetic worker installs this immutable endpoint.
    // Ordinary opt-in quota callers keep their existing transport behavior.
    endpoint: Option<SocketAddr>,
}

impl TcpQuota {
    fn new(bytes: u64, connections: u32, timeout_ms: u32) -> io::Result<Self> {
        if bytes == 0
            || bytes > MAX_BYTES
            || connections == 0
            || connections > MAX_CONNECTIONS
            || timeout_ms == 0
            || timeout_ms > MAX_TIMEOUT_MS
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "PrivateQuotaParameters",
            ));
        }
        let (cancelled, _) = watch::channel(false);
        Ok(Self {
            endpoint: None,
            state: Mutex::new(State {
                receipt: Snapshot {
                    byte_limit: bytes,
                    upload: 0,
                    download: 0,
                    connection_limit: connections,
                    connection_attempts: 0,
                    receive_reservation: u64::from(connections) * RECEIVE_RESERVATION,
                    timeout_ms,
                    timed_out: false,
                    stopped: false,
                    shutdown_failures: 0,
                },
                sockets: Vec::new(),
                deadline: Instant::now() + Duration::from_millis(u64::from(timeout_ms)),
                cancelled,
                deadline_wakeup: Arc::new(Condvar::new()),
            }),
        })
    }

    pub fn snapshot(&self) -> io::Result<Snapshot> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| io::Error::other("PrivateQuotaState"))?;
        state.expire_if_due();
        Ok(state.receipt)
    }

    fn start_watchdog(self: &Arc<Self>) -> io::Result<std::thread::JoinHandle<()>> {
        let guard = Arc::clone(self);
        // Installation may happen before the worker creates a Tokio runtime.
        // One bounded watchdog must therefore not depend on that runtime's
        // timer or on a stalled protocol task polling its socket again.
        std::thread::Builder::new()
            .name("swirl-private-quota-deadline".into())
            .spawn(move || {
                let state = guard
                    .state
                    .lock()
                    .unwrap_or_else(|poison| poison.into_inner());
                let wakeup = Arc::clone(&state.deadline_wakeup);
                let remaining = state.deadline.saturating_duration_since(Instant::now());
                let (mut state, _) = wakeup
                    .wait_timeout_while(state, remaining, |state| !state.receipt.stopped)
                    .unwrap_or_else(|poison| poison.into_inner());
                if !state.receipt.stopped {
                    state.receipt.timed_out = true;
                    state.stop();
                }
            })
    }

    async fn cancelled(&self) {
        let mut signal = match self.state.lock() {
            Ok(state) => state.cancelled.subscribe(),
            Err(_) => return,
        };
        let _ = signal.wait_for(|stopped| *stopped).await;
    }

    pub(super) async fn while_running<T>(
        &self,
        operation: impl Future<Output = io::Result<T>>,
    ) -> io::Result<T> {
        // TcpSocket is owned by this future before it becomes a registered
        // TcpConnection. Dropping it cancels even an unfinished TCP connect.
        tokio::select! {
            biased;
            _ = self.cancelled() => Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "PrivateQuotaStopped",
            )),
            result = operation => result,
        }
    }

    /// Actively shuts down every registered TCP socket, including idle streams
    /// held by protocol tasks. There is no reset or refund operation.
    pub fn cancel(&self) {
        self.state
            .lock()
            .unwrap_or_else(|poison| poison.into_inner())
            .stop();
    }

    fn admit(self: &Arc<Self>) -> io::Result<Arc<Self>> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| io::Error::other("PrivateQuotaState"))?;
        state.check()?;
        if state.receipt.connection_attempts == state.receipt.connection_limit {
            state.stop();
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "PrivateQuotaConnections",
            ));
        }
        // Attempts are charged before connect and never refunded after failure.
        state.receipt.connection_attempts += 1;
        Ok(Arc::clone(self))
    }

    pub(super) fn socket(&self, address: SocketAddr) -> io::Result<TcpSocket> {
        if self.endpoint.is_some_and(|endpoint| endpoint != address) {
            self.cancel();
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "PrivateQuotaEndpointDenied",
            ));
        }
        let socket = if address.is_ipv6() {
            TcpSocket::new_v6()?
        } else {
            TcpSocket::new_v4()?
        };
        // Set before the TCP handshake. On Windows SO_RCVBUF disables receive
        // window autotuning for this socket, leaving the host configuration intact.
        socket.set_recv_buffer_size(RECEIVE_BUFFER)?;
        let actual = socket.recv_buffer_size()?;
        if actual == 0 || u64::from(actual) > RECEIVE_RESERVATION {
            return Err(io::Error::other("PrivateQuotaReceiveBuffer"));
        }
        Ok(socket)
    }
}

/// Install once, before any outbound TCP socket is created in this dedicated
/// process. A second install and late installation both fail closed.
pub fn install(bytes: u64, connections: u32) -> io::Result<Arc<TcpQuota>> {
    install_with_timeout(bytes, connections, MAX_TIMEOUT_MS)
}

/// As `install`, with one immutable deadline shared by every connection and
/// retry in this process. It starts at installation and cannot be extended.
pub fn install_with_timeout(
    bytes: u64,
    connections: u32,
    timeout_ms: u32,
) -> io::Result<Arc<TcpQuota>> {
    install_inner(bytes, connections, timeout_ms, None)
}

/// The QA worker may contact only its one parent-owned loopback fixture.
/// This function is not exported through the ordinary product C ABI. The
/// worker's private IPC admission must authenticate the grant before calling it.
#[cfg(feature = "private-acceptance-worker")]
pub fn install_worker(
    bytes: u64,
    connections: u32,
    timeout_ms: u32,
    endpoint: SocketAddr,
) -> io::Result<Arc<TcpQuota>> {
    if !endpoint.ip().is_loopback()
        || endpoint.port() == 0
        || matches!(endpoint, SocketAddr::V6(address) if address.scope_id() != 0 || address.flowinfo() != 0)
    {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "PrivateQuotaEndpointDenied",
        ));
    }
    install_inner(bytes, connections, timeout_ms, Some(endpoint))
}

fn install_inner(
    bytes: u64,
    connections: u32,
    timeout_ms: u32,
    endpoint: Option<SocketAddr>,
) -> io::Result<Arc<TcpQuota>> {
    if cfg!(feature = "private-acceptance-worker") && endpoint.is_none() {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "PrivateQuotaWorkerGrantRequired",
        ));
    }
    let started = STARTED
        .lock()
        .map_err(|_| io::Error::other("PrivateQuotaState"))?;
    if *started {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "PrivateQuotaLateInstall",
        ));
    }
    if GUARD.get().is_some() {
        return Err(io::Error::other("PrivateQuotaAlreadyInstalled"));
    }
    let mut guard = TcpQuota::new(bytes, connections, timeout_ms)?;
    guard.endpoint = endpoint;
    let guard = Arc::new(guard);
    let watchdog = guard.start_watchdog()?;
    GUARD.set(Arc::clone(&guard)).map_err(|_| {
        guard.cancel();
        io::Error::other("PrivateQuotaAlreadyInstalled")
    })?;
    // The watchdog has a fixed deadline and is woken immediately by cancel.
    // The dedicated process supervisor still owns task/process exit and billing.
    drop(watchdog);
    Ok(guard)
}

pub(super) fn active() -> bool {
    GUARD.get().is_some()
}

pub(super) fn admit_connection() -> io::Result<Option<Arc<TcpQuota>>> {
    *STARTED
        .lock()
        .map_err(|_| io::Error::other("PrivateQuotaState"))? = true;
    if cfg!(feature = "private-acceptance-worker") && GUARD.get().is_none() {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "PrivateQuotaWorkerGrantRequired",
        ));
    }
    GUARD.get().map(TcpQuota::admit).transpose()
}

#[cfg(feature = "private-acceptance-worker")]
pub(super) fn check_listener(address: SocketAddr) -> io::Result<()> {
    *STARTED
        .lock()
        .map_err(|_| io::Error::other("PrivateQuotaState"))? = true;
    let guard = GUARD.get().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::PermissionDenied,
            "PrivateQuotaWorkerGrantRequired",
        )
    })?;
    if !address.ip().is_loopback() || address.port() != 0 {
        guard.cancel();
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "PrivateQuotaListenerDenied",
        ));
    }
    guard
        .state
        .lock()
        .map_err(|_| io::Error::other("PrivateQuotaState"))?
        .check()
}

pub(super) fn check_udp() -> io::Result<()> {
    reject_unmetered("PrivateQuotaUdpDenied")
}

pub(super) fn check_unmetered_egress() -> io::Result<()> {
    reject_unmetered("PrivateQuotaUnmeteredDenied")
}

fn reject_unmetered(code: &'static str) -> io::Result<()> {
    *STARTED
        .lock()
        .map_err(|_| io::Error::other("PrivateQuotaState"))? = true;
    if active() || cfg!(feature = "private-acceptance-worker") {
        #[cfg(feature = "private-acceptance-worker")]
        if let Some(guard) = GUARD.get() {
            guard.cancel();
        }
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, code));
    }
    Ok(())
}

pub struct TcpConnection {
    stream: TcpStream,
    guard: Option<Arc<TcpQuota>>,
    // A safe duplicate permits shutdown from the quota owner without sharing
    // mutable access to Tokio's stream. It is dropped with this connection.
    _shutdown: Option<Arc<Socket>>,
}

impl TcpConnection {
    pub(super) fn new(stream: TcpStream, guard: Option<Arc<TcpQuota>>) -> io::Result<Self> {
        let shutdown = if let Some(guard) = &guard {
            let socket = Arc::new(SockRef::from(&stream).try_clone()?);
            let mut state = guard
                .state
                .lock()
                .map_err(|_| io::Error::other("PrivateQuotaState"))?;
            if let Err(error) = state.check() {
                let _ = socket.shutdown(Shutdown::Both);
                return Err(error);
            }
            state.sockets.retain(|entry| entry.strong_count() != 0);
            state.sockets.push(Arc::downgrade(&socket));
            Some(socket)
        } else {
            None
        };
        Ok(Self {
            stream,
            guard,
            _shutdown: shutdown,
        })
    }

    pub fn set_nodelay(&self, value: bool) -> io::Result<()> {
        self.stream.set_nodelay(value)
    }
    pub fn peer_addr(&self) -> io::Result<SocketAddr> {
        self.stream.peer_addr()
    }
    pub fn local_addr(&self) -> io::Result<SocketAddr> {
        self.stream.local_addr()
    }

    pub async fn readable(&self) -> io::Result<()> {
        self.stream.readable().await
    }

    pub fn try_read(&self, buffer: &mut [u8]) -> io::Result<usize> {
        let Some(guard) = &self.guard else {
            return self.stream.try_read(buffer);
        };
        let mut state = guard
            .state
            .lock()
            .map_err(|_| io::Error::other("PrivateQuotaState"))?;
        state.check()?;
        let allowed = buffer.len().min(state.remaining() as usize);
        let received = self.stream.try_read(&mut buffer[..allowed])?;
        state.charge_read(received);
        Ok(received)
    }
}

impl AsyncRead for TcpConnection {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        let Some(guard) = &this.guard else {
            return Pin::new(&mut this.stream).poll_read(cx, buffer);
        };
        let mut state = guard
            .state
            .lock()
            .map_err(|_| io::Error::other("PrivateQuotaState"))?;
        state.check()?;
        let allowed = buffer.remaining().min(state.remaining() as usize);
        let (result, received) = {
            let mut limited = ReadBuf::new(buffer.initialize_unfilled_to(allowed));
            let result = Pin::new(&mut this.stream).poll_read(cx, &mut limited);
            (result, limited.filled().len())
        };
        buffer.advance(received);
        state.charge_read(received);
        result
    }
}

impl AsyncWrite for TcpConnection {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        let Some(guard) = &this.guard else {
            return Pin::new(&mut this.stream).poll_write(cx, buffer);
        };
        let mut state = guard
            .state
            .lock()
            .map_err(|_| io::Error::other("PrivateQuotaState"))?;
        state.check()?;
        let allowed = buffer.len().min(state.remaining() as usize);
        let result = Pin::new(&mut this.stream).poll_write(cx, &buffer[..allowed]);
        if let Poll::Ready(Ok(sent)) = result {
            state.receipt.upload += sent as u64;
        }
        if state.remaining() == 0 {
            state.stop();
        }
        result
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if let Some(guard) = &this.guard {
            guard
                .state
                .lock()
                .map_err(|_| io::Error::other("PrivateQuotaState"))?
                .check()?;
        }
        Pin::new(&mut this.stream).poll_flush(cx)
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().stream).poll_shutdown(cx)
    }
}

#[cfg(test)]
#[path = "budget_tests.rs"]
mod tests;
