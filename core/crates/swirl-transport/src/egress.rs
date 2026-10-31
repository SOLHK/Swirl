//! Physical-interface egress while a Windows full tunnel is active.
//!
//! Only socket creation and pooled-connection admission read this state; the
//! packet hot path does not. A short lock publishes interfaces and their epoch
//! together so a reused connection cannot cross a suspend/rebuild boundary.
//! Existing sockets retain their interface. A lost interface must cancel old
//! flows before the controller updates this lease. Dropping an unrecovered lease
//! fails closed instead of letting new sockets follow the tunnel's own routes.
use std::{io, net::SocketAddr, sync::Mutex};
use tokio::net::{TcpSocket, TcpStream, UdpSocket};

const BLOCKED: u32 = u32::MAX;
const SUSPENDED: u64 = u64::MAX;
const ORPHANED: u64 = u64::MAX - 1;
static EGRESS: Mutex<EgressState> = Mutex::new(EgressState::new());

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct EgressToken(u64);

struct EgressState {
    interfaces: u64,
    token: EgressToken,
}

impl EgressState {
    const fn new() -> Self {
        Self {
            interfaces: 0,
            token: EgressToken(0),
        }
    }

    fn transition(&mut self, interfaces: u64) -> io::Result<()> {
        let generation = self
            .token
            .0
            .checked_add(1)
            .ok_or_else(|| io::Error::other("TunEgressGenerationLimit"))?;
        self.interfaces = interfaces;
        self.token = EgressToken(generation);
        Ok(())
    }

    fn token(&self, loopback_only: bool) -> io::Result<EgressToken> {
        if !loopback_only && (self.interfaces == SUSPENDED || self.interfaces == ORPHANED) {
            select(self.interfaces, false)?;
        }
        Ok(self.token)
    }

    fn check(&self, token: EgressToken) -> io::Result<()> {
        if self.token != token {
            return Err(io::Error::new(
                io::ErrorKind::NetworkUnreachable,
                "TunEgressChanged",
            ));
        }
        Ok(())
    }
}

impl EgressToken {
    /// An opaque identity for pooled connection admission, including ordinary
    /// unbound operation. Every ownership/state transition creates a new epoch,
    /// even when a rebuilt physical interface has the same numeric index.
    /// Explicit loopback peers retain the ordinary socket helpers' local-only
    /// exemption. Mixed or empty endpoint sets never receive that exemption.
    pub fn capture(addresses: &[SocketAddr]) -> io::Result<Self> {
        let loopback_only = !addresses.is_empty() && addresses.iter().all(|a| a.ip().is_loopback());
        EGRESS
            .lock()
            .map_err(|_| io::Error::other("TunEgressState"))?
            .token(loopback_only)
    }

    /// Admit a synchronous cache lookup/update only while this epoch is current.
    /// The callback must not perform IO, await, or call another egress API. The
    /// lock covers the check and admission, never the connection handshake.
    pub fn with_current<T>(self, admit: impl FnOnce() -> T) -> io::Result<T> {
        let state = EGRESS
            .lock()
            .map_err(|_| io::Error::other("TunEgressState"))?;
        state.check(self)?;
        let result = admit();
        drop(state);
        Ok(result)
    }
}

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
    if state == ORPHANED {
        return Err(io::Error::new(
            io::ErrorKind::NetworkUnreachable,
            "TunEgressRecoveryRequired",
        ));
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
    token: EgressToken,
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
        let mut current = EGRESS
            .lock()
            .map_err(|_| io::Error::other("TunEgressState"))?;
        if current.interfaces != 0 {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "TunEgressOwned",
            ));
        }
        current.transition(state)?;
        Ok(Self {
            state,
            token: current.token,
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
        let mut current = EGRESS
            .lock()
            .map_err(|_| io::Error::other("TunEgressState"))?;
        if current.interfaces != self.state || current.token != self.token {
            return Err(io::Error::other("TunEgressOwnershipChanged"));
        }
        current.transition(next)?;
        self.state = next;
        self.token = current.token;
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
            let _ = self.replace(ORPHANED);
        }
    }
}

/// Reset only a dropped owner's fail-closed guard. A live lease, including a
/// suspended one, cannot be stolen. The privileged caller must first verify
/// that all durable network journals are restored and no other owner is active.
pub fn release_orphan_after_routes_restored() -> io::Result<()> {
    let mut current = EGRESS
        .lock()
        .map_err(|_| io::Error::other("TunEgressState"))?;
    match current.interfaces {
        ORPHANED => current.transition(0),
        0 => Ok(()),
        _ => Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "TunEgressStillOwned",
        )),
    }
}

pub async fn connect_tcp(address: SocketAddr) -> io::Result<TcpStream> {
    if address.ip().is_loopback() {
        return TcpStream::connect(address).await;
    }
    let interface = select(
        EGRESS
            .lock()
            .map_err(|_| io::Error::other("TunEgressState"))?
            .interfaces,
        address.is_ipv6(),
    )?;
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
    if let Some(interface) = select(
        EGRESS
            .lock()
            .map_err(|_| io::Error::other("TunEgressState"))?
            .interfaces,
        local.is_ipv6(),
    )? {
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
    fn pooled_tokens_expire_on_suspend_and_same_interface_rebuild() {
        let mut state = EgressState::new();
        let unbound = state.token(false).unwrap();
        let interfaces = encode(Some(7), Some(11)).unwrap();
        state.transition(interfaces).unwrap();
        let running = state.token(false).unwrap();
        assert!(state.check(unbound).is_err());
        assert!(state.check(running).is_ok());

        state.transition(SUSPENDED).unwrap();
        assert_eq!(
            state.token(false).unwrap_err().to_string(),
            "TunEgressUnavailable"
        );
        assert!(state.check(running).is_err());
        state.transition(interfaces).unwrap();
        let rebuilt = state.token(false).unwrap();
        assert_eq!(state.interfaces, interfaces);
        assert_ne!(rebuilt, running, "same interface indices are a new epoch");
        assert!(state.check(running).is_err());
        assert!(state.check(rebuilt).is_ok());

        state.transition(0).unwrap();
        let stopped = state.token(false).unwrap();
        assert_ne!(stopped, unbound, "release must not resurrect unbound pools");
        assert!(state.check(rebuilt).is_err());
        state.transition(interfaces).unwrap();
        assert!(state.check(stopped).is_err());
        assert!(state.check(running).is_err());
        assert!(state.check(rebuilt).is_err());
    }

    #[test]
    fn orphan_recovery_does_not_resurrect_any_previous_pool_epoch() {
        let mut state = EgressState::new();
        let unbound = state.token(false).unwrap();
        state.transition(encode(Some(7), None).unwrap()).unwrap();
        let running = state.token(false).unwrap();
        state.transition(ORPHANED).unwrap();
        assert_eq!(
            state.token(false).unwrap_err().to_string(),
            "TunEgressRecoveryRequired"
        );
        assert!(state.check(running).is_err());
        state.transition(0).unwrap();
        assert!(state.check(unbound).is_err());
        assert!(state.check(running).is_err());
        assert!(state.check(state.token(false).unwrap()).is_ok());
    }

    #[test]
    fn loopback_keeps_local_access_but_never_an_old_pool_epoch() {
        let mut state = EgressState::new();
        let previous = state.token(true).unwrap();
        for interfaces in [SUSPENDED, ORPHANED, 0] {
            state.transition(interfaces).unwrap();
            let local = state.token(true).unwrap();
            assert!(state.check(local).is_ok());
            assert!(state.check(previous).is_err());
            if interfaces != 0 {
                assert!(state.token(false).is_err());
            }
        }
    }

    #[test]
    fn families_are_atomic_and_missing_family_fails_closed() {
        let state = encode(Some(7), Some(11)).unwrap();
        assert_eq!(select(state, false).unwrap(), Some(7));
        assert_eq!(select(state, true).unwrap(), Some(11));
        assert!(select(encode(Some(7), None).unwrap(), true).is_err());
        assert!(select(SUSPENDED, false).is_err());
        assert!(select(SUSPENDED, true).is_err());
        assert!(select(ORPHANED, false).is_err());
        assert!(select(ORPHANED, true).is_err());
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
