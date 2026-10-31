//! Bounded, explicitly requested DHCP conflict observation on one dedicated LAN.
//! A timeout is only an observation; it is not proof that a silent DHCP server
//! does not exist. The separate dedicated-LAN confirmation remains mandatory.
use crate::{dhcp_probe, gateway_policy::GatewayIsolationPolicy, socket_pin};
use sha2::{Digest, Sha256};
use socket2::{Domain, MsgHdr, Protocol, SockRef, Socket, Type};
use std::{
    io,
    net::{Ipv4Addr, SocketAddr, UdpSocket},
    os::windows::io::AsRawSocket,
    time::{Duration, Instant},
};

/// Called by elevated-helper preflight before installing WFP or enabling LAN
/// forwarding. No host/network settings are changed. The socket closes on every
/// exit and is never shared with the Windows DHCP client or another process.
pub(crate) fn observe(policy: &GatewayIsolationPolicy, hardware: &str) -> io::Result<()> {
    let mac = dhcp_probe::hardware_address(hardware).ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "DHCP requires a verified Ethernet hardware address",
        )
    })?;
    let digest = Sha256::digest(format!("Swirl.DhcpInform.v1.{}", policy.owner).as_bytes());
    let transaction = [digest[0], digest[1], digest[2], digest[3]];
    let packet = dhcp_probe::inform(transaction, mac, policy.gateway);
    let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
    constrain(&socket, policy.lan.index)?;
    socket
        .bind(&SocketAddr::from((policy.gateway, 68)).into())
        .map_err(|error| {
            io::Error::new(
                error.kind(),
                "dedicated LAN DHCP conflict probe cannot exclusively bind UDP/68",
            )
        })?;
    socket.set_broadcast(true)?;
    socket.set_write_timeout(Some(Duration::from_secs(1)))?;
    let socket: UdpSocket = socket.into();
    let mut buffer = [0; 1501];
    for _ in 0..2 {
        if send_inform(&socket, policy.gateway, policy.lan.index, &packet)? != packet.len() {
            return Err(io::Error::other("incomplete DHCP conflict probe datagram"));
        }
        let until = Instant::now() + Duration::from_secs(1);
        let mut received = 0;
        while let Some(remaining) = until.checked_duration_since(Instant::now()) {
            if remaining.is_zero() {
                break;
            }
            if received >= 256 {
                return Err(io::Error::other(
                    "DHCP conflict probe receive limit reached",
                ));
            }
            socket.set_read_timeout(Some(remaining))?;
            match socket.recv_from(&mut buffer) {
                Ok((size, peer)) => {
                    received += 1;
                    if peer.port() == 67
                        && dhcp_probe::responding_server(&buffer[..size], transaction, mac)
                            .is_some()
                    {
                        return Err(io::Error::new(
                            io::ErrorKind::AlreadyExists,
                            "another DHCP server responded on the dedicated LAN",
                        ));
                    }
                }
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock
                    ) =>
                {
                    break;
                }
                Err(error) => return Err(error),
            }
        }
    }
    Ok(())
}

#[allow(unsafe_code)]
fn constrain(socket: &Socket, interface_index: u32) -> io::Result<()> {
    use windows_sys::Win32::Networking::WinSock::{
        IP_ADD_IFLIST, IP_IFLIST, IPPROTO_IP, SO_EXCLUSIVEADDRUSE, SOCKET_ERROR, SOL_SOCKET,
        WSAGetLastError, setsockopt,
    };
    // The exclusive setting must precede bind. IP_IFLIST rejects datagrams
    // received on any other interface, including with weak-host reception.
    for (level, option, value) in [
        (SOL_SOCKET, SO_EXCLUSIVEADDRUSE, 1u32),
        (IPPROTO_IP, IP_IFLIST, 1),
        (IPPROTO_IP, IP_ADD_IFLIST, interface_index),
    ] {
        // SAFETY: socket owns a live handle; WinSock reads this DWORD only for
        // the call. These documented options take a DWORD and retain no pointer.
        let result = unsafe {
            setsockopt(
                socket.as_raw_socket() as usize,
                level,
                option,
                (&value as *const u32).cast(),
                std::mem::size_of::<u32>() as i32,
            )
        };
        if result == SOCKET_ERROR {
            return Err(io::Error::from_raw_os_error(unsafe { WSAGetLastError() }));
        }
    }
    // Unicast replies and any future unicast request remain physically bound.
    // Broadcast transmission uses a separate per-message IP_PKTINFO constraint.
    socket_pin::pin_outbound_socket(socket, false, interface_index)
}

#[allow(unsafe_code)]
fn send_inform(
    socket: &UdpSocket,
    source: Ipv4Addr,
    interface: u32,
    packet: &[u8],
) -> io::Result<usize> {
    use windows_sys::Win32::Networking::WinSock::{CMSGHDR, IN_PKTINFO, IP_PKTINFO, IPPROTO_IP};
    // WSACMSGHDR is SIZE_T + INT + INT; IN_PKTINFO is IN_ADDR + ULONG.
    // Aligned, initialized machine-word storage avoids reading struct padding.
    const WORD: usize = std::mem::size_of::<usize>();
    const HEADER: usize = std::mem::size_of::<CMSGHDR>();
    const LENGTH: usize = HEADER + std::mem::size_of::<IN_PKTINFO>();
    const WORDS: usize = LENGTH.div_ceil(WORD);
    const {
        assert!(HEADER == WORD + 8);
        assert!(std::mem::size_of::<IN_PKTINFO>() == 8);
    };
    let mut storage = [0usize; WORDS];
    // SAFETY: every byte of this aligned machine-word array is initialized and
    // the bounded slice does not outlive storage. It remains borrowed until the
    // synchronous WSASendMsg wrapper returns, with no overlapped I/O retained.
    let control =
        unsafe { std::slice::from_raw_parts_mut(storage.as_mut_ptr().cast::<u8>(), WORDS * WORD) };
    control[..WORD].copy_from_slice(&LENGTH.to_ne_bytes());
    control[WORD..WORD + 4].copy_from_slice(&IPPROTO_IP.to_ne_bytes());
    control[WORD + 4..HEADER].copy_from_slice(&IP_PKTINFO.to_ne_bytes());
    control[HEADER..HEADER + 4].copy_from_slice(&source.octets());
    control[HEADER + 4..LENGTH].copy_from_slice(&interface.to_ne_bytes());
    let destination = SocketAddr::from((Ipv4Addr::BROADCAST, 67)).into();
    let buffers = [io::IoSlice::new(packet)];
    let message = MsgHdr::new()
        .with_addr(&destination)
        .with_buffers(&buffers)
        .with_control(control);
    // RFC 2131 uses the limited broadcast address. IP_UNICAST_IF alone does not
    // constrain broadcasts; IN_PKTINFO supplies both the source and LAN index.
    SockRef::from(socket).sendmsg(&message, 0)
}
