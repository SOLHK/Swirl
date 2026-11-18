//! Import a one-use WinSock socket-sharing token for read-only attestation.
//! The helper never receives, sends, changes options, or changes notification
//! registration on the GUI's DHCP socket. It closes its descriptor immediately.
#![allow(unsafe_code)]

use base64::{Engine as _, engine::general_purpose::STANDARD};
use socket2::{Domain, Protocol, Socket, Type};
use std::{
    io,
    mem::size_of,
    net::Ipv4Addr,
    os::windows::io::{AsRawSocket, FromRawSocket},
};
use windows_sys::Win32::Networking::WinSock::{
    AF_INET, FROM_PROTOCOL_INFO, INVALID_SOCKET, IP_GET_IFLIST, IP_IFLIST, IP_UNICAST_IF,
    IPPROTO_IP, IPPROTO_UDP, SO_EXCLUSIVEADDRUSE, SO_PROTOCOL_INFOW, SO_TYPE, SOCK_DGRAM,
    SOCKET_ERROR, SOL_SOCKET, WSA_FLAG_NO_HANDLE_INHERIT, WSA_FLAG_OVERLAPPED, WSAGetLastError,
    WSAPROTOCOL_INFOW, WSASocketW, getsockopt,
};

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message)
}

fn protocol_token(encoded: &str) -> io::Result<WSAPROTOCOL_INFOW> {
    if encoded.is_empty() || encoded.len() > 1024 {
        return Err(invalid("invalid DHCP socket-sharing token size"));
    }
    let bytes = STANDARD
        .decode(encoded)
        .map_err(|_| invalid("invalid DHCP socket-sharing token encoding"))?;
    if bytes.len() != size_of::<WSAPROTOCOL_INFOW>() || STANDARD.encode(&bytes) != encoded {
        return Err(invalid("invalid DHCP socket-sharing token structure"));
    }
    let mut info = WSAPROTOCOL_INFOW::default();
    // SAFETY: this SDK structure contains only integers, a GUID, and fixed
    // integer arrays, with no pointers, Rust enum discriminants or references.
    // The exact-size initialized byte buffer is copied into aligned storage.
    unsafe {
        std::ptr::copy_nonoverlapping(
            bytes.as_ptr(),
            (&mut info as *mut WSAPROTOCOL_INFOW).cast(),
            bytes.len(),
        );
    }
    if info.iAddressFamily != i32::from(AF_INET)
        || info.iSocketType != SOCK_DGRAM
        || info.iProtocol != IPPROTO_UDP
    {
        return Err(invalid("DHCP attestation requires an IPv4 UDP socket"));
    }
    Ok(info)
}

fn option(socket: &Socket, level: i32, name: i32) -> io::Result<u32> {
    let mut value = 0u32;
    let mut length = size_of::<u32>() as i32;
    // SAFETY: the descriptor is owned; both output buffers have the supplied
    // lengths. WinSock retains no pointers after this synchronous read.
    if unsafe {
        getsockopt(
            socket.as_raw_socket() as usize,
            level,
            name,
            (&mut value as *mut u32).cast(),
            &mut length,
        )
    } == SOCKET_ERROR
    {
        return Err(io::Error::from_raw_os_error(unsafe { WSAGetLastError() }));
    }
    if length != size_of::<u32>() as i32 {
        return Err(invalid("unexpected WinSock option length"));
    }
    Ok(value)
}

pub(crate) fn attest(
    encoded: &str,
    helper_pid: u32,
    interface: u32,
    gateway: Ipv4Addr,
) -> io::Result<()> {
    if helper_pid != std::process::id() || interface == 0 || interface > 0x00ff_ffff {
        return Err(invalid(
            "DHCP socket-sharing token targets another helper or invalid interface",
        ));
    }
    let info = protocol_token(encoded)?;
    // socket2 performs WinSock initialization. This unbound temporary socket
    // sends no data and does not reserve a DHCP port or alter any NIC setting.
    let _winsock = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
    // SAFETY: an aligned checked SDK token is borrowed for this call only.
    // A token can be consumed once; all success paths immediately give the
    // returned descriptor to Socket, so early errors close it as well.
    let raw = unsafe {
        WSASocketW(
            FROM_PROTOCOL_INFO,
            FROM_PROTOCOL_INFO,
            FROM_PROTOCOL_INFO,
            &info,
            0,
            WSA_FLAG_OVERLAPPED | WSA_FLAG_NO_HANDLE_INHERIT,
        )
    };
    if raw == INVALID_SOCKET {
        return Err(io::Error::from_raw_os_error(unsafe { WSAGetLastError() }));
    }
    let socket = unsafe { Socket::from_raw_socket(raw as _) };
    inspect(&socket, interface, gateway)
}

fn inspect(socket: &Socket, interface: u32, gateway: Ipv4Addr) -> io::Result<()> {
    let address = socket
        .local_addr()?
        .as_socket_ipv4()
        .ok_or_else(|| invalid("DHCP socket is not IPv4"))?;
    if address.port() != 67 || ![Ipv4Addr::UNSPECIFIED, gateway].contains(address.ip()) {
        return Err(invalid(
            "DHCP socket is not bound to UDP67 on the dedicated LAN",
        ));
    }
    let mut info = WSAPROTOCOL_INFOW::default();
    let mut length = size_of::<WSAPROTOCOL_INFOW>() as i32;
    // Read back the actual imported socket protocol, not the sender's claim.
    if unsafe {
        getsockopt(
            socket.as_raw_socket() as usize,
            SOL_SOCKET,
            SO_PROTOCOL_INFOW,
            (&mut info as *mut WSAPROTOCOL_INFOW).cast(),
            &mut length,
        )
    } == SOCKET_ERROR
    {
        return Err(io::Error::from_raw_os_error(unsafe { WSAGetLastError() }));
    }
    if length != size_of::<WSAPROTOCOL_INFOW>() as i32 || info.iAddressFamily != i32::from(AF_INET)
        || info.iSocketType != SOCK_DGRAM || info.iProtocol != IPPROTO_UDP
        || option(socket, SOL_SOCKET, SO_TYPE)? != SOCK_DGRAM as u32
        || option(socket, SOL_SOCKET, SO_EXCLUSIVEADDRUSE)? != 1
        || option(socket, IPPROTO_IP, IP_IFLIST)? != 1
        // IP_UNICAST_IF's getter returns host order; its setter uses network order.
        || option(socket, IPPROTO_IP, IP_UNICAST_IF)? != interface
    {
        return Err(invalid(
            "DHCP socket protocol, exclusivity or interface constraint is invalid",
        ));
    }
    // Deliberately permit exactly one entry. Extra interfaces, truncated
    // responses or a provider reporting an unsupported option all fail closed.
    let mut interfaces = [0u32; 2];
    let mut length = size_of::<[u32; 2]>() as i32;
    if unsafe {
        getsockopt(
            socket.as_raw_socket() as usize,
            IPPROTO_IP,
            IP_GET_IFLIST,
            interfaces.as_mut_ptr().cast(),
            &mut length,
        )
    } == SOCKET_ERROR
    {
        return Err(io::Error::from_raw_os_error(unsafe { WSAGetLastError() }));
    }
    if length != size_of::<u32>() as i32 || interfaces[0] != interface {
        return Err(invalid(
            "DHCP receive interface list is not the dedicated LAN alone",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use windows_sys::Win32::Networking::WinSock::{IP_ADD_IFLIST, WSADuplicateSocketW, setsockopt};

    fn encoded(socket: &Socket) -> String {
        let mut info = WSAPROTOCOL_INFOW::default();
        assert_eq!(
            unsafe {
                WSADuplicateSocketW(
                    socket.as_raw_socket() as usize,
                    std::process::id(),
                    &mut info,
                )
            },
            0
        );
        let bytes = unsafe {
            std::slice::from_raw_parts(
                (&info as *const WSAPROTOCOL_INFOW).cast::<u8>(),
                size_of::<WSAPROTOCOL_INFOW>(),
            )
        };
        STANDARD.encode(bytes)
    }

    fn set(socket: &Socket, level: i32, name: i32, value: u32) {
        assert_eq!(
            unsafe {
                setsockopt(
                    socket.as_raw_socket() as usize,
                    level,
                    name,
                    (&value as *const u32).cast(),
                    size_of::<u32>() as i32,
                )
            },
            0
        );
    }

    #[test]
    fn rejects_malformed_tokens_and_wrong_helper_without_import() {
        for token in ["", "!", "AAAA", "AAAA===="] {
            assert!(protocol_token(token).is_err());
        }
        assert!(protocol_token(&"A".repeat(1025)).is_err());
        assert!(
            attest(
                "AAAA",
                std::process::id().wrapping_add(1),
                1,
                Ipv4Addr::LOCALHOST
            )
            .is_err()
        );
    }

    #[test]
    fn real_socket_duplicate_is_read_only_and_rejects_non_dhcp_port() {
        // No administrative rights or LAN traffic: only a loopback ephemeral
        // UDP socket is imported. The original stays open and carries data
        // after its helper duplicate has been rejected and closed.
        let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP)).unwrap();
        socket
            .bind(&std::net::SocketAddr::from((Ipv4Addr::LOCALHOST, 0)).into())
            .unwrap();
        assert!(
            attest(
                &encoded(&socket),
                std::process::id(),
                1,
                Ipv4Addr::LOCALHOST
            )
            .is_err()
        );
        let peer = std::net::UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        peer.set_read_timeout(Some(std::time::Duration::from_secs(2)))
            .unwrap();
        socket
            .send_to(b"still-owned", &peer.local_addr().unwrap().into())
            .unwrap();
        let mut bytes = [0; 32];
        let (count, _) = peer.recv_from(&mut bytes).unwrap();
        assert_eq!(&bytes[..count], b"still-owned");
    }

    #[test]
    fn live_socket_constraint_readback_uses_host_order() {
        // Windows loopback's index is obtained from its address, rather than
        // assuming a fixed numeric index. This test changes socket options only.
        let index: u32 = crate::windows_network::run_json(
            "@(Get-NetIPAddress -AddressFamily IPv4 -IPAddress '127.0.0.1' -ErrorAction Stop)[0].InterfaceIndex | ConvertTo-Json -Compress", &serde_json::json!({})).unwrap();
        let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP)).unwrap();
        set(&socket, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, 1);
        set(&socket, IPPROTO_IP, IP_IFLIST, 1);
        set(&socket, IPPROTO_IP, IP_ADD_IFLIST, index);
        set(&socket, IPPROTO_IP, IP_UNICAST_IF, index.to_be());
        assert_eq!(option(&socket, IPPROTO_IP, IP_UNICAST_IF).unwrap(), index);
        assert_eq!(option(&socket, IPPROTO_IP, IP_IFLIST).unwrap(), 1);
        assert_eq!(option(&socket, IPPROTO_IP, IP_GET_IFLIST).unwrap(), index);
        assert_eq!(option(&socket, SOL_SOCKET, SO_EXCLUSIVEADDRUSE).unwrap(), 1);
    }

    #[test]
    #[ignore = "reserves loopback UDP67; explicitly run on a disposable Windows validation runner"]
    fn real_udp67_attestation_accepts_single_interface_and_rejects_replay() {
        let index: u32 = crate::windows_network::run_json(
            "@(Get-NetIPAddress -AddressFamily IPv4 -IPAddress '127.0.0.1' -ErrorAction Stop)[0].InterfaceIndex | ConvertTo-Json -Compress", &serde_json::json!({})).unwrap();
        let socket = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP)).unwrap();
        set(&socket, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, 1);
        set(&socket, IPPROTO_IP, IP_IFLIST, 1);
        set(&socket, IPPROTO_IP, IP_ADD_IFLIST, index);
        set(&socket, IPPROTO_IP, IP_UNICAST_IF, index.to_be());
        socket
            .bind(&std::net::SocketAddr::from((Ipv4Addr::LOCALHOST, 67)).into())
            .unwrap();
        let token = encoded(&socket);
        attest(&token, std::process::id(), index, Ipv4Addr::LOCALHOST).unwrap();
        assert!(attest(&token, std::process::id(), index, Ipv4Addr::LOCALHOST).is_err());
        assert_eq!(
            socket
                .local_addr()
                .unwrap()
                .as_socket_ipv4()
                .unwrap()
                .port(),
            67
        );
        assert_eq!(option(&socket, IPPROTO_IP, IP_GET_IFLIST).unwrap(), index);
    }
}
