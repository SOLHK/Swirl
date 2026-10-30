//! Socket handoff shared by the Windows driver fixture and its kernel-contract
//! regression. Callers configure the original socket as nonblocking first.

use std::{
    io,
    net::{TcpListener, UdpSocket},
};

pub(crate) fn clone_listener_for_tokio(socket: &TcpListener) -> io::Result<TcpListener> {
    let cloned = socket.try_clone()?;
    // Restore the mode on the cloned handle before Tokio registers it. Windows
    // socket duplication can otherwise leave accept (and inherited reads)
    // blocking, even when the original listener was explicitly nonblocking.
    cloned.set_nonblocking(true)?;
    Ok(cloned)
}

pub(crate) fn clone_udp_for_tokio(socket: &UdpSocket) -> io::Result<UdpSocket> {
    socket.try_clone()
}
