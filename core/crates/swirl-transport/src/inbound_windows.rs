//! Private Winsock option boundary for the locked socket2 0.6.5 release.
//! That release does not expose SO_EXCLUSIVEADDRUSE. Keep the ABI wrapper here
//! rather than upgrading the dependency to an unreleased upstream revision.
#![allow(unsafe_code)]

use std::{
    ffi::{c_char, c_int},
    io,
    os::windows::io::AsRawSocket,
};

// Winsock2.h: SOCKET is UINT_PTR, BOOL/int are 32-bit, and
// SO_EXCLUSIVEADDRUSE is defined as ~SO_REUSEADDR (0x0004).
const SOL_SOCKET: c_int = 0xffff;
const SO_EXCLUSIVEADDRUSE: c_int = !0x0004;
const OPTION_BYTES: c_int = std::mem::size_of::<c_int>() as c_int;

#[link(name = "ws2_32")]
unsafe extern "system" {
    fn setsockopt(
        socket: usize,
        level: c_int,
        name: c_int,
        value: *const c_char,
        length: c_int,
    ) -> c_int;
    fn getsockopt(
        socket: usize,
        level: c_int,
        name: c_int,
        value: *mut c_char,
        length: *mut c_int,
    ) -> c_int;
    fn WSAGetLastError() -> c_int;
}

pub(super) fn require_exclusive(socket: &impl AsRawSocket) -> io::Result<()> {
    let enabled: c_int = 1;
    // SAFETY: the borrowed socket is not transferred or closed. The option
    // identifier is valid at SOL_SOCKET, and the synchronous call reads only
    // the initialized, correctly sized Win32 int that lives until return.
    let result = unsafe {
        setsockopt(
            socket.as_raw_socket() as usize,
            SOL_SOCKET,
            SO_EXCLUSIVEADDRUSE,
            std::ptr::from_ref(&enabled).cast(),
            OPTION_BYTES,
        )
    };
    if result != 0 {
        // SAFETY: WSAGetLastError has no arguments; read immediately on the
        // calling thread before any other Winsock operation can replace it.
        return Err(io::Error::from_raw_os_error(unsafe { WSAGetLastError() }));
    }
    if !exclusive(socket)? {
        return Err(io::Error::other("ingress socket is not exclusive"));
    }
    Ok(())
}

pub(super) fn exclusive(socket: &impl AsRawSocket) -> io::Result<bool> {
    let mut value: c_int = 0;
    let mut length = OPTION_BYTES;
    // SAFETY: both writable buffers are initialized and have the exact ABI
    // types. Winsock may write at most length bytes to value and one int to
    // length. Neither pointer escapes the synchronous call; no handle owner
    // is reconstructed. Reject an unexpected returned size before using it.
    let result = unsafe {
        getsockopt(
            socket.as_raw_socket() as usize,
            SOL_SOCKET,
            SO_EXCLUSIVEADDRUSE,
            std::ptr::from_mut(&mut value).cast(),
            &mut length,
        )
    };
    if result != 0 {
        // SAFETY: same immediate thread-local error retrieval contract above.
        return Err(io::Error::from_raw_os_error(unsafe { WSAGetLastError() }));
    }
    if length != OPTION_BYTES {
        return Err(io::Error::other("invalid Winsock option size"));
    }
    Ok(value != 0)
}
