//! Bounded L3 packet/flow adaptation for Swirl's native runtime.
//!
//! This crate owns no OS routes, DNS policy or proxy protocols. It terminates
//! application TCP using smoltcp and exposes byte streams to the same dispatcher
//! used by the system proxy. UDP datagrams retain both original endpoints.

use std::{
    io,
    net::SocketAddr,
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
    },
    time::Duration,
};
use std::{
    pin::Pin,
    task::{Context, Poll},
};
use tokio::{
    io::{AsyncRead, AsyncWrite, DuplexStream, ReadBuf},
    sync::{Notify, mpsc, watch},
    task::JoinHandle,
};

mod device;
mod ipv6;
mod packet;
mod stack;

/// Limits apply before accepting new flows. The four TCP buffers (smoltcp and
/// the bounded duplex bridge, in both directions) hold at most
/// `max_tcp_flows * tcp_buffer_bytes * 4` payload bytes. Allocator capacity,
/// socket metadata and the dispatcher's outbound state are additional.
#[derive(Debug, Clone)]
pub struct TunConfig {
    pub mtu: usize,
    pub max_tcp_flows: usize,
    /// UDP sockets are shared by clients using the same original destination.
    pub max_udp_endpoints: usize,
    pub tcp_buffer_bytes: usize,
    pub udp_buffer_bytes: usize,
    pub queue_capacity: usize,
    pub tcp_handshake_timeout: Duration,
    pub tcp_idle_timeout: Duration,
    pub udp_idle_timeout: Duration,
}

impl Default for TunConfig {
    fn default() -> Self {
        Self {
            mtu: 1500,
            max_tcp_flows: 512,
            max_udp_endpoints: 128,
            tcp_buffer_bytes: 64 * 1024,
            udp_buffer_bytes: 65536,
            queue_capacity: 128,
            tcp_handshake_timeout: Duration::from_secs(15),
            tcp_idle_timeout: Duration::from_secs(2 * 60 * 60),
            udp_idle_timeout: Duration::from_secs(60),
        }
    }
}

impl TunConfig {
    pub fn validate(&self) -> io::Result<()> {
        let valid = (1280..=65535).contains(&self.mtu)
            && (1..=4096).contains(&self.max_tcp_flows)
            && (1..=4096).contains(&self.max_udp_endpoints)
            && (4096..=1024 * 1024).contains(&self.tcp_buffer_bytes)
            && (65536..=1024 * 1024).contains(&self.udp_buffer_bytes)
            && (1..=4096).contains(&self.queue_capacity)
            && !self.tcp_handshake_timeout.is_zero()
            && !self.tcp_idle_timeout.is_zero()
            && !self.udp_idle_timeout.is_zero();
        if !valid {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "invalid TUN limits",
            ));
        }
        // Refuse configuration mistakes which otherwise reserve gigabytes under
        // an ordinary local connection burst. This is a memory budget, not a
        // throughput claim.
        let buffers = self.max_tcp_flows as u64 * self.tcp_buffer_bytes as u64 * 4
            + self.max_udp_endpoints as u64 * self.udp_buffer_bytes as u64 * 2
            + self.queue_capacity as u64 * (2 * self.mtu as u64 + 2 * 65507)
            + 32 * self.mtu as u64
            + 10 * 65536;
        if buffers > 1024 * 1024 * 1024 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "TUN socket budget exceeds 1 GiB",
            ));
        }
        Ok(())
    }
}

#[derive(Debug)]
pub struct TcpFlow {
    pub source: SocketAddr,
    pub destination: SocketAddr,
    pub stream: TunTcpStream,
}

/// A bounded byte stream with cancellation distinct from orderly half-close.
/// Dropping a dispatcher operation on failure resets its application TCP flow;
/// completing AsyncWrite::shutdown emits FIN after buffered reply bytes.
#[derive(Debug)]
pub struct TunTcpStream {
    inner: DuplexStream,
    abort: Arc<AtomicBool>,
    wake: Arc<Notify>,
    graceful: bool,
}

impl AsyncRead for TunTcpStream {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_read(cx, buffer)
    }
}

impl AsyncWrite for TunTcpStream {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.inner).poll_write(cx, bytes)
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let result = Pin::new(&mut self.inner).poll_shutdown(cx);
        if matches!(result, Poll::Ready(Ok(()))) {
            self.graceful = true;
        }
        result
    }
}

impl Drop for TunTcpStream {
    fn drop(&mut self) {
        if !self.graceful {
            self.abort.store(true, Ordering::Release);
            self.wake.notify_one();
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UdpDatagram {
    pub source: SocketAddr,
    pub destination: SocketAddr,
    pub payload: Vec<u8>,
}

/// Validates packet size before admitting a Vec to the bounded input queue.
#[derive(Debug, Clone)]
pub struct PacketSender {
    tx: mpsc::Sender<Vec<u8>>,
    mtu: usize,
}

impl PacketSender {
    pub async fn send(&self, packet: Vec<u8>) -> io::Result<()> {
        self.validate(&packet)?;
        self.tx.send(packet).await.map_err(|_| closed())
    }

    pub fn blocking_send(&self, packet: Vec<u8>) -> io::Result<()> {
        self.validate(&packet)?;
        self.tx.blocking_send(packet).map_err(|_| closed())
    }

    pub fn try_send(&self, packet: Vec<u8>) -> io::Result<()> {
        self.validate(&packet)?;
        self.tx.try_send(packet).map_err(|err| match err {
            mpsc::error::TrySendError::Full(_) => {
                io::Error::new(io::ErrorKind::WouldBlock, "TUN ingress full")
            }
            mpsc::error::TrySendError::Closed(_) => closed(),
        })
    }

    fn validate(&self, packet: &[u8]) -> io::Result<()> {
        if packet.len() > self.mtu {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "IP packet exceeds TUN MTU",
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct UdpReplySender {
    tx: mpsc::Sender<UdpDatagram>,
}

impl UdpReplySender {
    pub async fn send(&self, datagram: UdpDatagram) -> io::Result<()> {
        if datagram.source.is_ipv4() != datagram.destination.is_ipv4()
            || datagram.payload.len() > 65507
            || datagram.source.port() == 0
            || datagram.destination.port() == 0
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "invalid UDP reply endpoints or length",
            ));
        }
        self.tx.send(datagram).await.map_err(|_| closed())
    }
}

#[derive(Debug, Default)]
struct Counters {
    received_packets: AtomicU64,
    malformed_packets: AtomicU64,
    rejected_tcp_flows: AtomicU64,
    dropped_udp_datagrams: AtomicU64,
    active_tcp_flows: AtomicUsize,
    active_udp_endpoints: AtomicUsize,
}

#[derive(Debug, Clone)]
pub struct TunStats(Arc<Counters>);

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct TunStatsSnapshot {
    pub received_packets: u64,
    pub malformed_packets: u64,
    pub rejected_tcp_flows: u64,
    pub dropped_udp_datagrams: u64,
    pub active_tcp_flows: usize,
    pub active_udp_endpoints: usize,
}

impl TunStats {
    pub fn snapshot(&self) -> TunStatsSnapshot {
        TunStatsSnapshot {
            received_packets: self.0.received_packets.load(Ordering::Relaxed),
            malformed_packets: self.0.malformed_packets.load(Ordering::Relaxed),
            rejected_tcp_flows: self.0.rejected_tcp_flows.load(Ordering::Relaxed),
            dropped_udp_datagrams: self.0.dropped_udp_datagrams.load(Ordering::Relaxed),
            active_tcp_flows: self.0.active_tcp_flows.load(Ordering::Relaxed),
            active_udp_endpoints: self.0.active_udp_endpoints.load(Ordering::Relaxed),
        }
    }
}

/// Ownership of the task is explicit so callers may move the channel fields
/// into their I/O tasks without detaching the network stack's lifetime.
#[derive(Debug)]
pub struct TunControl {
    stop: watch::Sender<bool>,
    task: Option<JoinHandle<io::Result<()>>>,
}

impl TunControl {
    pub async fn shutdown(&mut self) -> io::Result<()> {
        let _ = self.stop.send(true);
        if let Some(task) = self.task.as_mut() {
            let result = task.await.map_err(io::Error::other);
            self.task = None;
            result??;
        }
        Ok(())
    }
}

impl Drop for TunControl {
    fn drop(&mut self) {
        let _ = self.stop.send(true);
        if let Some(task) = self.task.take() {
            task.abort();
        }
    }
}

#[derive(Debug)]
pub struct TunStack {
    pub ingress: PacketSender,
    pub egress: mpsc::Receiver<Vec<u8>>,
    pub tcp: mpsc::Receiver<TcpFlow>,
    pub udp: mpsc::Receiver<UdpDatagram>,
    pub udp_reply: UdpReplySender,
    pub stats: TunStats,
    pub control: TunControl,
}

impl TunStack {
    pub async fn shutdown(mut self) -> io::Result<()> {
        self.control.shutdown().await
    }
}

/// Requires an active Tokio runtime. Does not load a driver or modify the host.
pub fn spawn(config: TunConfig) -> io::Result<TunStack> {
    config.validate()?;
    let runtime = tokio::runtime::Handle::try_current().map_err(io::Error::other)?;
    let (input_tx, input_rx) = mpsc::channel(config.queue_capacity);
    let (output_tx, output_rx) = mpsc::channel(config.queue_capacity);
    let (tcp_tx, tcp_rx) = mpsc::channel(config.queue_capacity.min(config.max_tcp_flows));
    let (udp_tx, udp_rx) = mpsc::channel(config.queue_capacity);
    let (reply_tx, reply_rx) = mpsc::channel(config.queue_capacity);
    let (stop_tx, stop_rx) = watch::channel(false);
    let stats = TunStats(Arc::new(Counters::default()));
    let mtu = config.mtu;
    let driver = stack::Driver::new(config, output_tx, tcp_tx, udp_tx, stats.0.clone())?;
    let task = runtime.spawn(driver.run(input_rx, reply_rx, stop_rx));
    Ok(TunStack {
        ingress: PacketSender { tx: input_tx, mtu },
        egress: output_rx,
        tcp: tcp_rx,
        udp: udp_rx,
        udp_reply: UdpReplySender { tx: reply_tx },
        stats,
        control: TunControl {
            stop: stop_tx,
            task: Some(task),
        },
    })
}

fn closed() -> io::Error {
    io::Error::new(io::ErrorKind::BrokenPipe, "TUN stack stopped")
}
