//! The only socket FFI boundary used by portable-core outbound transports.
use std::{io, mem::size_of, os::windows::io::AsRawSocket};
use windows_sys::Win32::Networking::WinSock::{
    IP_UNICAST_IF, IPPROTO_IP, IPPROTO_IPV6, IPV6_UNICAST_IF, SOCKET_ERROR, WSAGetLastError,
    getsockopt, setsockopt,
};

/// Pin a not-yet-connected TCP or UDP socket to the physical egress interface.
/// IPv4 uses network byte order; IPv6 uses host byte order. A readback mismatch
/// fails closed so callers cannot accidentally continue through TUN routes.
#[allow(unsafe_code)]
pub fn pin_outbound_socket(
    socket: &impl AsRawSocket,
    ipv6: bool,
    interface_index: u32,
) -> io::Result<()> {
    if interface_index == 0 || (!ipv6 && interface_index > 0x00ff_ffff) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "physical interface index must be nonzero",
        ));
    }
    let (level, option, value) = if ipv6 {
        (IPPROTO_IPV6, IPV6_UNICAST_IF, interface_index)
    } else {
        (IPPROTO_IP, IP_UNICAST_IF, interface_index.to_be())
    };
    let raw = socket.as_raw_socket() as usize;
    // SAFETY: the caller lends a live socket; the pointer is a valid DWORD for
    // exactly its size and setsockopt does not retain it.
    let set = unsafe {
        setsockopt(
            raw,
            level,
            option,
            (&value as *const u32).cast(),
            size_of::<u32>() as i32,
        )
    };
    if set == SOCKET_ERROR {
        // SAFETY: thread-local WinSock error getter has no preconditions.
        return Err(io::Error::from_raw_os_error(unsafe { WSAGetLastError() }));
    }
    let mut actual: u32 = 0;
    let mut length = size_of::<u32>() as i32;
    // SAFETY: output buffer/length point to live, writable DWORD-sized values;
    // WinSock writes at most the supplied length and retains neither pointer.
    let get = unsafe {
        getsockopt(
            raw,
            level,
            option,
            (&mut actual as *mut u32).cast(),
            &mut length,
        )
    };
    if get == SOCKET_ERROR {
        // SAFETY: thread-local WinSock error getter has no preconditions.
        return Err(io::Error::from_raw_os_error(unsafe { WSAGetLastError() }));
    }
    // Both getters return host order, unlike the IPv4 setter.
    if length != size_of::<u32>() as i32 || actual != interface_index {
        return Err(io::Error::other(
            "physical egress binding readback mismatch",
        ));
    }
    Ok(())
}
