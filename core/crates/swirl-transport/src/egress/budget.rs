//! Opt-in private QA process budget, below TLS and protocol framing.
//!
//! Counts bytes accepted by TCP writes and delivered by TCP reads. TCP/IP
//! headers, retransmissions and unread kernel data are outside these counters.
//! The parent must persist the full request reservation before starting this
//! process, including RECEIVE_RESERVATION per permitted connection attempt.
//! This guard never supplies provider billing or persistent task accounting.
use socket2::{SockRef, Socket};
use std::{
    io,
    net::{Shutdown, SocketAddr},
    pin::Pin,
    sync::{Arc, Mutex, OnceLock, Weak},
    task::{Context, Poll},
};
use tokio::{
    io::{AsyncRead, AsyncWrite, ReadBuf},
    net::{TcpSocket, TcpStream},
};

pub const MAX_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_CONNECTIONS: u32 = 48;
pub const RECEIVE_RESERVATION: u64 = 1024 * 1024;
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
    pub stopped: bool,
    pub shutdown_failures: u32,
}

struct State {
    receipt: Snapshot,
    sockets: Vec<Weak<Socket>>,
}

impl State {
    fn check(&self) -> io::Result<()> {
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
}

impl TcpQuota {
    fn new(bytes: u64, connections: u32) -> io::Result<Self> {
        if bytes == 0 || bytes > MAX_BYTES || connections == 0 || connections > MAX_CONNECTIONS {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "PrivateQuotaParameters",
            ));
        }
        Ok(Self {
            state: Mutex::new(State {
                receipt: Snapshot {
                    byte_limit: bytes,
                    upload: 0,
                    download: 0,
                    connection_limit: connections,
                    connection_attempts: 0,
                    receive_reservation: u64::from(connections) * RECEIVE_RESERVATION,
                    stopped: false,
                    shutdown_failures: 0,
                },
                sockets: Vec::new(),
            }),
        })
    }

    pub fn snapshot(&self) -> io::Result<Snapshot> {
        Ok(self
            .state
            .lock()
            .map_err(|_| io::Error::other("PrivateQuotaState"))?
            .receipt)
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
    let started = STARTED
        .lock()
        .map_err(|_| io::Error::other("PrivateQuotaState"))?;
    if *started {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "PrivateQuotaLateInstall",
        ));
    }
    let guard = Arc::new(TcpQuota::new(bytes, connections)?);
    GUARD
        .set(Arc::clone(&guard))
        .map_err(|_| io::Error::other("PrivateQuotaAlreadyInstalled"))?;
    Ok(guard)
}

pub(super) fn active() -> bool {
    GUARD.get().is_some()
}

pub(super) fn admit_connection() -> io::Result<Option<Arc<TcpQuota>>> {
    *STARTED
        .lock()
        .map_err(|_| io::Error::other("PrivateQuotaState"))? = true;
    GUARD.get().map(TcpQuota::admit).transpose()
}

pub(super) fn check_udp() -> io::Result<()> {
    *STARTED
        .lock()
        .map_err(|_| io::Error::other("PrivateQuotaState"))? = true;
    if active() {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "PrivateQuotaUdpDenied",
        ));
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
