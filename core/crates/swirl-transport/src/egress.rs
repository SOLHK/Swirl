//! Physical-interface egress while a Windows full tunnel is active.
//!
//! Only socket creation reads this atomic state; the packet hot path does not.
//! Existing sockets retain their interface. A lost interface must cancel old
//! flows before the controller updates this lease. Dropping an unrecovered lease
//! fails closed instead of letting new sockets follow the tunnel's own routes.
use std::{
    io,
    net::SocketAddr,
    sync::atomic::{AtomicU64, Ordering},
};
use tokio::net::{TcpSocket, TcpStream, UdpSocket};

const BLOCKED: u32 = u32::MAX;
const SUSPENDED: u64 = u64::MAX;
static INTERFACES: AtomicU64 = AtomicU64::new(0);

fn encode(v4: Option<u32>, v6: Option<u32>) -> io::Result<u64> {
    if v4.is_none() && v6.is_none()
        || [v4, v6]
            .into_iter()
            .flatten()
            .any(|index| index == 0 || index > 0x00ff_ffff)
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "TunEgressInterface",
        ));
    }
    Ok(u64::from(v4.unwrap_or(BLOCKED)) | (u64::from(v6.unwrap_or(BLOCKED)) << 32))
}

fn select(state: u64, ipv6: bool) -> io::Result<Option<u32>> {
    if state == 0 {
        return Ok(None);
    }
    let index = if ipv6 {
        (state >> 32) as u32
    } else {
        state as u32
    };
    if index == BLOCKED {
        return Err(io::Error::new(
            io::ErrorKind::NetworkUnreachable,
            "TunEgressUnavailable",
        ));
    }
    Ok(Some(index))
}

/// One full-tunnel owner per process. Acquire before installing capture routes.
/// The caller obtains indices from a verified physical-interface snapshot.
pub struct EgressLease {
    state: u64,
    released: bool,
}

impl EgressLease {
    pub fn acquire(ipv4_interface: Option<u32>, ipv6_interface: Option<u32>) -> io::Result<Self> {
        Self::acquire_state(encode(ipv4_interface, ipv6_interface)?)
    }

    /// Reserve ownership before checking Core quiescence or discovering a new
    /// physical network. Keep this same lease across every capture restart.
    pub fn acquire_suspended() -> io::Result<Self> {
        Self::acquire_state(SUSPENDED)
    }

    fn acquire_state(state: u64) -> io::Result<Self> {
        if !cfg!(windows) {
            return Err(io::Error::new(
                io::ErrorKind::Unsupported,
                "WindowsEgressRequired",
            ));
        }
        INTERFACES
            .compare_exchange(0, state, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| io::Error::new(io::ErrorKind::AlreadyExists, "TunEgressOwned"))?;
        Ok(Self {
            state,
            released: false,
        })
    }

    /// Prevent new network sockets while a physical network is unavailable.
    pub fn suspend(&mut self) -> io::Result<()> {
        self.replace(SUSPENDED)
    }

    /// Existing connections must have been cancelled before changing egress.
    pub fn update(&mut self, ipv4: Option<u32>, ipv6: Option<u32>) -> io::Result<()> {
        self.replace(encode(ipv4, ipv6)?)
    }

    fn replace(&mut self, next: u64) -> io::Result<()> {
        INTERFACES
            .compare_exchange(self.state, next, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| io::Error::other("TunEgressOwnershipChanged"))?;
        self.state = next;
        Ok(())
    }

    /// Only call after the owned capture routes have verifiably been removed.
    /// A failed network rollback must retain this lease or let Drop suspend it.
    pub fn release_after_routes_restored(mut self) -> io::Result<()> {
        self.replace(0)?;
        self.released = true;
        Ok(())
    }
}

impl Drop for EgressLease {
    fn drop(&mut self) {
        if !self.released {
            let _ = INTERFACES.compare_exchange(
                self.state,
                SUSPENDED,
                Ordering::AcqRel,
                Ordering::Acquire,
            );
        }
    }
}

pub async fn connect_tcp(address: SocketAddr) -> io::Result<TcpStream> {
    if address.ip().is_loopback() {
        return TcpStream::connect(address).await;
    }
    let interface = select(INTERFACES.load(Ordering::Acquire), address.is_ipv6())?;
    let Some(interface) = interface else {
        return TcpStream::connect(address).await;
    };
    let socket = if address.is_ipv6() {
        TcpSocket::new_v6()?
    } else {
        TcpSocket::new_v4()?
    };
    #[cfg(windows)]
    swirl_platform::pin_outbound_socket(&socket, address.is_ipv6(), interface)?;
    #[cfg(not(windows))]
    let _ = interface;
    socket.connect(address).await
}

pub(crate) fn pin_udp(socket: &UdpSocket, local: SocketAddr) -> io::Result<()> {
    // Local SOCKS UDP relays and test peers must remain on loopback.
    if local.ip().is_loopback() {
        return Ok(());
    }
    if let Some(interface) = select(INTERFACES.load(Ordering::Acquire), local.is_ipv6())? {
        #[cfg(windows)]
        swirl_platform::pin_outbound_socket(socket, local.is_ipv6(), interface)?;
        #[cfg(not(windows))]
        let _ = (socket, interface);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn families_are_atomic_and_missing_family_fails_closed() {
        let state = encode(Some(7), Some(11)).unwrap();
        assert_eq!(select(state, false).unwrap(), Some(7));
        assert_eq!(select(state, true).unwrap(), Some(11));
        assert!(select(encode(Some(7), None).unwrap(), true).is_err());
        assert!(select(SUSPENDED, false).is_err());
        assert!(select(SUSPENDED, true).is_err());
        assert_eq!(select(0, false).unwrap(), None);
        assert!(encode(None, None).is_err());
        assert!(encode(Some(0), Some(1)).is_err());
        assert!(encode(Some(0x0100_0000), None).is_err());
    }

    #[tokio::test]
    async fn ordinary_tcp_still_transfers_with_half_close() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let client = connect_tcp(listener.local_addr().unwrap());
        let (client, peer) = tokio::join!(client, listener.accept());
        let mut client = client.unwrap();
        let mut peer = peer.unwrap().0;
        client.write_all(b"egress").await.unwrap();
        client.shutdown().await.unwrap();
        let mut data = Vec::new();
        peer.read_to_end(&mut data).await.unwrap();
        assert_eq!(data, b"egress");
        peer.write_all(b"reply").await.unwrap();
        peer.shutdown().await.unwrap();
        data.clear();
        client.read_to_end(&mut data).await.unwrap();
        assert_eq!(data, b"reply");
    }
}
