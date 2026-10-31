//! Native UDP sockets with buffers sized for Swirl's supported datagram limit.
use socket2::SockRef;
use std::{io, net::SocketAddr};
use tokio::net::UdpSocket;

// Darwin rejects an atomic send larger than SO_SNDBUF before UDP output; its
// default UDP send buffer is only 9,216 bytes. This fixed minimum also leaves
// room for a 65,507-byte datagram and its source address on receive. It is an OS
// buffer minimum, independent of the Core's bounded queues and payload limits.
const BUFFER_MINIMUM: usize = 65_536;

pub fn reserve_datagram_buffers(socket: &UdpSocket) -> io::Result<()> {
    let socket = SockRef::from(socket);
    if socket.send_buffer_size()? < BUFFER_MINIMUM {
        socket.set_send_buffer_size(BUFFER_MINIMUM)?;
    }
    if socket.recv_buffer_size()? < BUFFER_MINIMUM {
        socket.set_recv_buffer_size(BUFFER_MINIMUM)?;
    }
    // An OS may clamp a successful setsockopt. Do not claim a usable association
    // if its buffers remain too small, or reduce larger existing OS defaults.
    if socket.send_buffer_size()? < BUFFER_MINIMUM || socket.recv_buffer_size()? < BUFFER_MINIMUM {
        return Err(io::Error::other(
            "UDP socket buffers below datagram minimum",
        ));
    }
    Ok(())
}

/// Bind a native UDP forwarding socket, returning buffer setup errors to the
/// caller. This changes only this socket; system-wide network limits are intact.
pub async fn bind_udp(address: SocketAddr) -> io::Result<UdpSocket> {
    let socket = UdpSocket::bind(address).await?;
    crate::egress::pin_udp(&socket, address)?;
    reserve_datagram_buffers(&socket)?;
    Ok(socket)
}

/// Bind an inbound proxy relay on its explicit local interface. This must not
/// inherit an outbound physical-interface constraint when Native TUN is active.
pub async fn bind_udp_inbound(address: SocketAddr) -> io::Result<UdpSocket> {
    let socket = UdpSocket::from_std(crate::inbound::bind_udp_std(address)?)?;
    reserve_datagram_buffers(&socket)?;
    Ok(socket)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    use tokio::time::timeout;

    #[tokio::test]
    async fn full_datagrams_survive_small_buffers_and_address_families() {
        for address in [
            SocketAddr::from(([127, 0, 0, 1], 0)),
            SocketAddr::from(([0, 0, 0, 0, 0, 0, 0, 1], 0)),
        ] {
            let first = bind_udp(address).await.unwrap();
            let second = UdpSocket::bind(address).await.unwrap();
            // Exercise the raising path even on hosts whose defaults already
            // accommodate full datagrams, then verify real bidirectional I/O.
            let options = SockRef::from(&second);
            options.set_send_buffer_size(4096).unwrap();
            options.set_recv_buffer_size(4096).unwrap();
            reserve_datagram_buffers(&second).unwrap();
            let payload: Vec<u8> = (0..65_507).map(|i| (i % 251) as u8).collect();
            let mut received = vec![0; 65_536];
            for (sender, receiver) in [(&first, &second), (&second, &first)] {
                let sent = sender
                    .send_to(&payload, receiver.local_addr().unwrap())
                    .await
                    .unwrap();
                assert_eq!(sent, payload.len());
                let (length, peer) =
                    timeout(Duration::from_secs(3), receiver.recv_from(&mut received))
                        .await
                        .unwrap()
                        .unwrap();
                assert_eq!(peer, sender.local_addr().unwrap());
                assert_eq!(&received[..length], &payload);
            }
        }
    }

    #[tokio::test]
    async fn buffer_setup_retains_larger_existing_values() {
        let socket = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let options = SockRef::from(&socket);
        options.set_send_buffer_size(2 * BUFFER_MINIMUM).unwrap();
        options.set_recv_buffer_size(2 * BUFFER_MINIMUM).unwrap();
        let previous = (
            options.send_buffer_size().unwrap(),
            options.recv_buffer_size().unwrap(),
        );
        assert!(previous.0 >= BUFFER_MINIMUM && previous.1 >= BUFFER_MINIMUM);
        reserve_datagram_buffers(&socket).unwrap();
        assert_eq!(options.send_buffer_size().unwrap(), previous.0);
        assert_eq!(options.recv_buffer_size().unwrap(), previous.1);
    }

    #[tokio::test]
    async fn inbound_relay_retains_full_datagrams_on_its_local_address() {
        let address = SocketAddr::from(([127, 0, 0, 1], 0));
        let relay = bind_udp_inbound(address).await.unwrap();
        let client = bind_udp(address).await.unwrap();
        let payload = vec![0x53; 65_507];
        relay
            .send_to(&payload, client.local_addr().unwrap())
            .await
            .unwrap();
        let mut bytes = vec![0; 65_536];
        let (length, source) = timeout(Duration::from_secs(3), client.recv_from(&mut bytes))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(source, relay.local_addr().unwrap());
        assert_eq!(&bytes[..length], &payload);
    }
}
