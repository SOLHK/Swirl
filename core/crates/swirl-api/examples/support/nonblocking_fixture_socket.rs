//! Socket handoff shared by the Windows driver fixture and its kernel-contract
//! regression. Callers configure the original socket as nonblocking first.

use std::{
    io,
    net::{TcpListener, UdpSocket},
};

pub(crate) fn clone_listener_for_tokio(socket: &TcpListener) -> io::Result<TcpListener> {
    socket.try_clone()
}

pub(crate) fn clone_udp_for_tokio(socket: &UdpSocket) -> io::Result<UdpSocket> {
    socket.try_clone()
}
