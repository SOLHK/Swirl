//! A nonblocking upper bound on QUIC wire upload rate. Cubic still controls
//! congestion; this adds a ceiling negotiated through Hysteria-CC-RX. There is
//! no packet queue or background task: Quinn waits on the existing UDP poller.
use quinn::{
    AsyncUdpSocket, UdpPoller,
    udp::{RecvMeta, Transmit},
};
use std::{
    fmt,
    io::{self, IoSliceMut},
    net::SocketAddr,
    pin::Pin,
    sync::{
        Arc, Mutex,
        atomic::{AtomicU64, Ordering},
    },
    task::{Context, Poll},
    time::Duration,
};
use tokio::time::{Instant, Sleep};

#[derive(Debug)]
pub struct Limit(AtomicU64);
impl Limit {
    pub fn new(bytes_per_second: u64) -> Arc<Self> {
        Arc::new(Self(AtomicU64::new(bytes_per_second)))
    }

    /// Zero is unlimited. Authentication can reduce the initial client limit
    /// to the server's receive ceiling without recreating the QUIC connection.
    pub fn set(&self, bytes_per_second: u64) {
        self.0.store(bytes_per_second, Ordering::Relaxed);
    }
}

#[derive(Clone, Copy)]
struct Sent {
    at: Instant,
    bytes: usize,
}

fn next_allowed(sent: Option<Sent>, bytes_per_second: u64) -> Option<Instant> {
    if bytes_per_second == 0 {
        return None;
    }
    sent.map(|sent| {
        let nanos = (sent.bytes as u64 * 1_000_000_000).div_ceil(bytes_per_second);
        sent.at + Duration::from_nanos(nanos)
    })
}

pub struct Socket {
    inner: Arc<dyn AsyncUdpSocket>,
    limit: Arc<Limit>,
    sent: Mutex<Option<Sent>>,
}
impl Socket {
    pub fn wrap(inner: Arc<dyn AsyncUdpSocket>, limit: Arc<Limit>) -> Arc<dyn AsyncUdpSocket> {
        Arc::new(Self {
            inner,
            limit,
            sent: Mutex::new(None),
        })
    }

    fn deadline(&self) -> io::Result<Option<Instant>> {
        Ok(next_allowed(
            *self.sent.lock().map_err(|_| io::ErrorKind::Other)?,
            self.limit.0.load(Ordering::Relaxed),
        ))
    }
}
impl fmt::Debug for Socket {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("HysteriaRateSocket")
    }
}

struct Poller {
    socket: Arc<Socket>,
    inner: Pin<Box<dyn UdpPoller>>,
    timer: Pin<Box<Sleep>>,
}
impl fmt::Debug for Poller {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("HysteriaRatePoller")
    }
}
impl UdpPoller for Poller {
    fn poll_writable(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        let deadline = this.socket.deadline()?;
        if let Some(deadline) = deadline
            && deadline > Instant::now()
        {
            this.timer.as_mut().reset(deadline);
            if this.timer.as_mut().poll(context).is_pending() {
                return Poll::Pending;
            }
        }
        this.inner.as_mut().poll_writable(context)
    }
}

impl AsyncUdpSocket for Socket {
    fn create_io_poller(self: Arc<Self>) -> Pin<Box<dyn UdpPoller>> {
        Box::pin(Poller {
            inner: self.inner.clone().create_io_poller(),
            socket: self,
            timer: Box::pin(tokio::time::sleep(Duration::ZERO)),
        })
    }

    fn try_send(&self, transmit: &Transmit<'_>) -> io::Result<()> {
        // Single-datagram sends make the bound independent of kernel GSO.
        if transmit.contents.len() > 65535
            || transmit
                .segment_size
                .is_some_and(|size| size < transmit.contents.len())
        {
            return Err(io::ErrorKind::InvalidInput.into());
        }
        let mut sent = self.sent.lock().map_err(|_| io::ErrorKind::Other)?;
        let now = Instant::now();
        if next_allowed(*sent, self.limit.0.load(Ordering::Relaxed))
            .is_some_and(|deadline| deadline > now)
        {
            return Err(io::ErrorKind::WouldBlock.into());
        }
        self.inner.try_send(transmit)?;
        *sent = Some(Sent {
            at: now,
            bytes: transmit.contents.len(),
        });
        Ok(())
    }

    fn poll_recv(
        &self,
        context: &mut Context<'_>,
        buffers: &mut [IoSliceMut<'_>],
        metadata: &mut [RecvMeta],
    ) -> Poll<io::Result<usize>> {
        self.inner.poll_recv(context, buffers, metadata)
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
    fn rate_bound_counts_wire_bytes_and_does_not_accumulate_idle_credit() {
        let now = Instant::now();
        let sent = Some(Sent {
            at: now,
            bytes: 1250,
        });
        assert_eq!(next_allowed(None, 125000), None);
        assert_eq!(next_allowed(sent, 0), None);
        assert_eq!(
            next_allowed(sent, 125000),
            Some(now + Duration::from_millis(10))
        );
        assert_eq!(
            next_allowed(sent, 250000),
            Some(now + Duration::from_millis(5))
        );
        let next = Some(Sent {
            at: now + Duration::from_secs(100),
            bytes: 1250,
        });
        assert_eq!(
            next_allowed(next, 125000),
            Some(now + Duration::from_millis(100010))
        );
    }
}
