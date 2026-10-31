//! Swirl-owned RFC 1928/1929 negotiation and UDP association. The TCP socket
//! owns the association lifetime; UDP is connected to the advertised relay.
use super::{Result, Target, read_target};
use crate::dial::{connect_tcp, within};
use std::{io, net::SocketAddr, time::Duration};
use swirl_dns::Resolver;
use swirl_subscription::{Credentials, Outbound};
use swirl_transport::bind_udp;
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt},
    net::{TcpStream, UdpSocket},
    time::Instant,
};
use zeroize::Zeroizing;

const DATAGRAM_LIMIT: usize = 65507;

pub(super) async fn authenticate<S: AsyncRead + AsyncWrite + Unpin>(
    stream: &mut S,
    auth: Option<&Credentials>,
) -> Result<()> {
    if auth.is_some_and(|a| {
        a.username.is_empty()
            || a.password.is_empty()
            || a.username.len() > 255
            || a.password.len() > 255
    }) {
        return Err("UpstreamAuthentication");
    }
    let method = if auth.is_some() { 2 } else { 0 };
    stream
        .write_all(&[5, 1, method])
        .await
        .map_err(|_| "SocksUpstreamWrite")?;
    stream.flush().await.map_err(|_| "SocksUpstreamWrite")?;
    let mut response = [0; 2];
    stream
        .read_exact(&mut response)
        .await
        .map_err(|_| "SocksUpstreamRead")?;
    if response != [5, method] {
        return Err("UpstreamAuthentication");
    }
    if let Some(auth) = auth {
        let mut request = Zeroizing::new(vec![1, auth.username.len() as u8]);
        request.extend(auth.username.as_bytes());
        request.push(auth.password.len() as u8);
        request.extend(auth.password.as_bytes());
        stream
            .write_all(&request)
            .await
            .map_err(|_| "SocksUpstreamWrite")?;
        stream.flush().await.map_err(|_| "SocksUpstreamWrite")?;
        stream
            .read_exact(&mut response)
            .await
            .map_err(|_| "SocksUpstreamRead")?;
        if response != [1, 0] {
            return Err("UpstreamAuthentication");
        }
    }
    Ok(())
}

pub(super) async fn request<S: AsyncRead + AsyncWrite + Unpin>(
    stream: &mut S,
    command: u8,
    target: &Target,
    allow_zero_bound_port: bool,
) -> Result<Target> {
    let mut request = vec![5, command, 0];
    target.encode(&mut request)?;
    stream
        .write_all(&request)
        .await
        .map_err(|_| "SocksUpstreamWrite")?;
    stream.flush().await.map_err(|_| "SocksUpstreamWrite")?;
    let mut header = [0; 3];
    stream
        .read_exact(&mut header)
        .await
        .map_err(|_| "SocksUpstreamRead")?;
    if header != [5, 0, 0] {
        return Err("UpstreamRejected");
    }
    read_target(stream, allow_zero_bound_port).await
}

pub struct UdpAssociation {
    control: TcpStream,
    socket: UdpSocket,
}

impl UdpAssociation {
    pub async fn connect(
        outbound: &Outbound,
        resolver: &Resolver,
        handshake_limit: Duration,
    ) -> Result<Self> {
        let Outbound::Socks5 {
            host,
            port,
            auth,
            tls,
            udp: true,
        } = outbound
        else {
            return Err("Socks5UdpDisabled");
        };
        // TLS-protected control does not specify protection for UDP data.
        // This combination needs its own verified transport, never plaintext
        // UDP implicitly attached to a TLS node.
        if tls.is_some() {
            return Err("Socks5UdpTlsUnsupported");
        }
        let deadline = Instant::now() + handshake_limit;
        let mut control = connect_tcp(
            resolver,
            &Target {
                host: host.clone(),
                port: *port,
            },
            deadline,
        )
        .await?;
        let peer = control.peer_addr().map_err(|_| "Socks5UdpPeer")?;
        let bound = within(deadline, "UpstreamProtocolTimeout", async {
            authenticate(&mut control, auth.as_ref()).await?;
            request(
                &mut control,
                3,
                &Target {
                    host: if peer.is_ipv4() { "0.0.0.0" } else { "::" }.into(),
                    port: 0,
                },
                false,
            )
            .await
        })
        .await?;
        let address = if let Ok(ip) = bound.host.parse() {
            let ip: std::net::IpAddr = ip;
            // Only an unspecified BND.ADDR uses the actual connected peer;
            // explicit relay addresses are neither guessed nor overwritten.
            SocketAddr::new(if ip.is_unspecified() { peer.ip() } else { ip }, bound.port)
        } else {
            let addresses = within(
                deadline,
                "Socks5UdpRelayDnsTimeout",
                resolver.resolve(&bound.host, bound.port),
            )
            .await?;
            addresses
                .iter()
                .copied()
                .find(|a| valid_relay(*a) && a.is_ipv4() == peer.is_ipv4())
                .or_else(|| addresses.into_iter().find(|a| valid_relay(*a)))
                .ok_or("Socks5UdpRelayAddress")?
        };
        if !valid_relay(address) {
            return Err("Socks5UdpRelayAddress");
        }
        if !resolver.endpoint_allowed(address) {
            return Err("Socks5UdpRelayForbidden");
        }
        let socket = within(deadline, "UpstreamProtocolTimeout", async {
            let socket = bind_udp(if address.is_ipv4() {
                SocketAddr::from(([0, 0, 0, 0], 0))
            } else {
                SocketAddr::from(([0u16; 8], 0))
            })
            .await
            .map_err(|_| "Socks5UdpBind")?;
            socket
                .connect(address)
                .await
                .map_err(|_| "Socks5UdpConnect")?;
            Ok(socket)
        })
        .await?;
        Ok(Self { control, socket })
    }

    fn control_alive(&self) -> Result<()> {
        let mut byte = [0; 1];
        loop {
            match self.control.try_read(&mut byte) {
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(()),
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                Ok(0) | Err(_) => return Err("Socks5UdpControlClosed"),
                Ok(_) => return Err("Socks5UdpControlData"),
            }
        }
    }

    /// A cancellation-safe lifetime monitor. No control bytes are valid after
    /// a successful UDP ASSOCIATE reply. Dropping this object closes both sockets.
    pub async fn closed(&self) -> &'static str {
        loop {
            if self.control.readable().await.is_err() {
                return "Socks5UdpControlClosed";
            }
            if let Err(code) = self.control_alive() {
                return code;
            }
        }
    }

    pub async fn send(&self, target: &Target, payload: &[u8]) -> Result<()> {
        self.control_alive()?;
        let packet = Self::encode_datagram(target, payload)?;
        let written = self
            .socket
            .send(&packet)
            .await
            .map_err(|_| "Socks5UdpSend")?;
        if written != packet.len() {
            return Err("Socks5UdpSend");
        }
        Ok(())
    }

    /// A connected socket filters the relay source address and port in the OS.
    pub async fn recv(&self, buffer: &mut [u8]) -> io::Result<usize> {
        self.socket.recv(buffer).await
    }

    pub fn encode_datagram(target: &Target, payload: &[u8]) -> Result<Vec<u8>> {
        if target.port == 0 || payload.len() > DATAGRAM_LIMIT {
            return Err("Socks5UdpDatagram");
        }
        let mut data = vec![0, 0, 0];
        target.encode(&mut data)?;
        if data.len() + payload.len() > DATAGRAM_LIMIT {
            return Err("Socks5UdpDatagramSize");
        }
        data.extend(payload);
        Ok(data)
    }

    pub async fn decode_datagram(packet: &[u8]) -> Result<(Target, &[u8])> {
        if packet.len() < 4 || packet.len() > DATAGRAM_LIMIT || packet[..2] != [0, 0] {
            return Err("Socks5UdpDatagram");
        }
        if packet[2] != 0 {
            return Err("Socks5UdpFragmentUnsupported");
        }
        let mut cursor = &packet[3..];
        let target = read_target(&mut cursor, false).await?;
        Ok((target, cursor))
    }
}

fn valid_relay(address: SocketAddr) -> bool {
    address.port() != 0
        && !address.ip().is_unspecified()
        && !address.ip().is_multicast()
        && !matches!(address.ip(), std::net::IpAddr::V4(a) if a.is_broadcast())
}

#[cfg(test)]
#[path = "socks5_tests.rs"]
mod tests;
