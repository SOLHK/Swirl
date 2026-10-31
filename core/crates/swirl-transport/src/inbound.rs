//! Explicitly addressed ingress sockets with platform-specific port ownership.
//! These sockets never inherit the physical outbound constraint used by TUN.
use socket2::{Domain, Protocol, Socket, Type};
use std::{io, net::SocketAddr};
use tokio::net::TcpListener;

#[cfg(windows)]
#[path = "inbound_windows.rs"]
mod windows;

fn bound_socket(address: SocketAddr, kind: Type, protocol: Protocol) -> io::Result<Socket> {
    if address.ip().is_unspecified() || address.ip().is_multicast() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "ingress requires an explicit unicast address",
        ));
    }
    let socket = Socket::new(Domain::for_address(address), kind, Some(protocol))?;
    // Winsock's default bind can be stolen by another same-user socket that
    // opts into SO_REUSEADDR. This must be set BEFORE bind; a firewall rule
    // and a successful bind do not themselves confer exclusive ownership.
    #[cfg(windows)]
    windows::require_exclusive(&socket)?;
    // Match Tokio's Unix TCP restart behavior. Do not enable UDP reuse or
    // SO_REUSEPORT, and never translate this option to Winsock SO_REUSEADDR.
    #[cfg(unix)]
    if kind == Type::STREAM {
        socket.set_reuse_address(true)?;
    }
    socket.set_nonblocking(true)?;
    socket.bind(&address.into())?;
    Ok(socket)
}

/// Bind a TCP ingress on exactly the requested address. Must be called inside
/// a Tokio I/O runtime. Port zero is available for internal socket fixtures;
/// product configuration continues to enforce its own nonzero port contract.
pub fn bind_tcp(address: SocketAddr) -> io::Result<TcpListener> {
    let socket = bound_socket(address, Type::STREAM, Protocol::TCP)?;
    socket.listen(128)?;
    TcpListener::from_std(socket.into())
}

/// Bind an owned nonblocking UDP ingress before handing it to a Tokio runtime.
/// LAN port reservations and active associations must use the same primitive.
/// The caller remains responsible for the established datagram buffer contract.
pub fn bind_udp_std(address: SocketAddr) -> io::Result<std::net::UdpSocket> {
    bound_socket(address, Type::DGRAM, Protocol::UDP).map(Into::into)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::{TcpStream, UdpSocket};
    use tokio::time::timeout;

    fn addresses() -> [SocketAddr; 2] {
        [
            SocketAddr::from(([127, 0, 0, 1], 0)),
            SocketAddr::from(([0, 0, 0, 0, 0, 0, 0, 1], 0)),
        ]
    }

    #[tokio::test]
    async fn tcp_ingress_retains_exact_address_bytes_and_half_close() {
        for address in addresses() {
            timeout(Duration::from_secs(3), async {
                let listener = bind_tcp(address).unwrap();
                let local = listener.local_addr().unwrap();
                assert_eq!(local.ip(), address.ip());
                assert!(bind_tcp(local).is_err());
                let mut client = TcpStream::connect(local).await.unwrap();
                let (mut accepted, peer) = listener.accept().await.unwrap();
                assert_eq!(accepted.local_addr().unwrap(), local);
                assert_eq!(peer, client.local_addr().unwrap());
                client.write_all(b"request").await.unwrap();
                client.shutdown().await.unwrap();
                let mut request = Vec::new();
                accepted.read_to_end(&mut request).await.unwrap();
                assert_eq!(request, b"request");
                accepted.write_all(b"reply-after-fin").await.unwrap();
                accepted.shutdown().await.unwrap();
                let mut reply = Vec::new();
                client.read_to_end(&mut reply).await.unwrap();
                assert_eq!(reply, b"reply-after-fin");
            })
            .await
            .unwrap();
        }
    }

    #[tokio::test]
    async fn ingress_port_reservations_release_without_widening_bindings() {
        for address in addresses() {
            let listener = bind_tcp(address).unwrap();
            let local = listener.local_addr().unwrap();
            assert!(bind_tcp(local).is_err());
            drop(listener);
            let replacement = bind_tcp(local).unwrap();
            assert_eq!(replacement.local_addr().unwrap(), local);
            let datagram = bind_udp_std(address).unwrap();
            let local = datagram.local_addr().unwrap();
            assert!(bind_udp_std(local).is_err());
            drop(datagram);
            assert_eq!(bind_udp_std(local).unwrap().local_addr().unwrap(), local);
        }
        for address in ["0.0.0.0:0", "[::]:0", "224.0.0.1:0", "[ff02::1]:0"] {
            let address = address.parse().unwrap();
            assert_eq!(
                bind_tcp(address).unwrap_err().kind(),
                io::ErrorKind::InvalidInput
            );
            assert_eq!(
                bind_udp_std(address).unwrap_err().kind(),
                io::ErrorKind::InvalidInput
            );
        }
    }

    #[tokio::test]
    async fn udp_ingress_keeps_empty_and_full_bidirectional_datagrams() {
        for address in addresses() {
            timeout(Duration::from_secs(3), async {
                let ingress = crate::bind_udp_inbound(address).await.unwrap();
                let client = UdpSocket::bind(address).await.unwrap();
                crate::reserve_datagram_buffers(&client).unwrap();
                let payload = vec![0x53; 65_507];
                let mut bytes = vec![0; 65_536];
                for payload in [b"".as_slice(), payload.as_slice()] {
                    for (sender, receiver) in [(&client, &ingress), (&ingress, &client)] {
                        sender
                            .send_to(payload, receiver.local_addr().unwrap())
                            .await
                            .unwrap();
                        let (length, source) = receiver.recv_from(&mut bytes).await.unwrap();
                        assert_eq!(source, sender.local_addr().unwrap());
                        assert_eq!(&bytes[..length], payload);
                    }
                }
            })
            .await
            .unwrap();
        }
    }

    #[cfg(windows)]
    fn assert_reuse_cannot_steal(address: SocketAddr, kind: Type, protocol: Protocol) {
        let competitor = Socket::new(Domain::for_address(address), kind, Some(protocol)).unwrap();
        competitor.set_reuse_address(true).unwrap();
        let error = competitor.bind(&address.into()).unwrap_err();
        assert!(
            matches!(error.raw_os_error(), Some(10013 | 10048)),
            "expected Winsock address ownership rejection, got {error}"
        );
    }

    #[cfg(windows)]
    #[tokio::test]
    async fn windows_ingress_rejects_reuseaddr_takeover_for_tcp_and_udp() {
        use socket2::SockRef;
        for address in addresses() {
            // Positive control: reproduce same-user default bind sharing, on
            // our own ephemeral loopback socket only. No external port, rule
            // or interface is touched by this fixture.
            for (kind, protocol) in [(Type::STREAM, Protocol::TCP), (Type::DGRAM, Protocol::UDP)] {
                let ordinary =
                    Socket::new(Domain::for_address(address), kind, Some(protocol)).unwrap();
                ordinary.bind(&address.into()).unwrap();
                if kind == Type::STREAM {
                    ordinary.listen(1).unwrap();
                }
                let other =
                    Socket::new(Domain::for_address(address), kind, Some(protocol)).unwrap();
                other.set_reuse_address(true).unwrap();
                other.bind(&ordinary.local_addr().unwrap()).unwrap();
            }
            let listener = bind_tcp(address).unwrap();
            assert!(windows::exclusive(&listener).unwrap());
            assert!(!SockRef::from(&listener).reuse_address().unwrap());
            assert_reuse_cannot_steal(listener.local_addr().unwrap(), Type::STREAM, Protocol::TCP);
            let reservation = bind_udp_std(address).unwrap();
            assert!(windows::exclusive(&reservation).unwrap());
            assert_reuse_cannot_steal(
                reservation.local_addr().unwrap(),
                Type::DGRAM,
                Protocol::UDP,
            );
            let relay = crate::bind_udp_inbound(address).await.unwrap();
            assert!(windows::exclusive(&relay).unwrap());
            assert_reuse_cannot_steal(relay.local_addr().unwrap(), Type::DGRAM, Protocol::UDP);
        }
    }
}
