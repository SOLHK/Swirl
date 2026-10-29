//! Admission metadata only; smoltcp performs TCP, UDP and IP reassembly.
use smoltcp::{
    phy::ChecksumCapabilities,
    wire::{IpProtocol, Ipv4Packet, Ipv6Packet, TcpPacket, TcpRepr},
};
use std::net::{IpAddr, SocketAddr};

pub(crate) struct Metadata {
    pub udp_destination: Option<SocketAddr>,
    pub new_tcp: Option<(SocketAddr, SocketAddr)>,
    pub tcp_key: Option<(SocketAddr, SocketAddr)>,
}

pub(crate) fn inspect(bytes: &[u8]) -> Result<Metadata, ()> {
    let version = bytes.first().ok_or(())? >> 4;
    let (source, destination, protocol, payload, fragmented, first_fragment) = match version {
        4 => {
            let packet = Ipv4Packet::new_checked(bytes).map_err(|_| ())?;
            if !packet.verify_checksum() || usize::from(packet.total_len()) != bytes.len() {
                return Err(());
            }
            let fragmented = packet.more_frags() || packet.frag_offset() != 0;
            if usize::from(packet.frag_offset())
                + packet.payload().len()
                + usize::from(packet.header_len())
                > 65535
                || (packet.more_frags() && !packet.payload().len().is_multiple_of(8))
            {
                return Err(());
            }
            (
                IpAddr::V4(packet.src_addr()),
                IpAddr::V4(packet.dst_addr()),
                packet.next_header(),
                packet.payload(),
                fragmented,
                packet.frag_offset() == 0,
            )
        }
        6 => {
            let packet = Ipv6Packet::new_checked(bytes).map_err(|_| ())?;
            if usize::from(packet.payload_len()) + 40 != bytes.len() {
                return Err(());
            }
            let mut next = packet.next_header();
            let mut payload = packet.payload();
            let mut fragmented = false;
            let mut first = true;
            // A bounded extension-header walk only discovers the transport
            // endpoint. The network stack validates extension semantics.
            for _ in 0..16 {
                match u8::from(next) {
                    0 | 43 | 60 => {
                        if payload.len() < 2 {
                            return Err(());
                        }
                        let len = (usize::from(payload[1]) + 1) * 8;
                        if payload.len() < len {
                            return Err(());
                        }
                        next = IpProtocol::from(payload[0]);
                        payload = &payload[len..];
                    }
                    44 => {
                        if payload.len() < 8 {
                            return Err(());
                        }
                        let bits = u16::from_be_bytes([payload[2], payload[3]]);
                        fragmented = bits & 0xfff9 != 0;
                        first = bits & 0xfff8 == 0;
                        next = IpProtocol::from(payload[0]);
                        payload = &payload[8..];
                        break;
                    }
                    _ => break,
                }
            }
            (
                IpAddr::V6(packet.src_addr()),
                IpAddr::V6(packet.dst_addr()),
                next,
                payload,
                fragmented,
                first,
            )
        }
        _ => return Err(()),
    };
    if source.is_unspecified()
        || source.is_multicast()
        || destination.is_unspecified()
        || destination.is_multicast()
        || source == IpAddr::V4(std::net::Ipv4Addr::BROADCAST)
        || destination == IpAddr::V4(std::net::Ipv4Addr::BROADCAST)
    {
        return Err(());
    }
    let mut result = Metadata {
        udp_destination: None,
        new_tcp: None,
        tcp_key: None,
    };
    if first_fragment && payload.len() >= 4 {
        let src = SocketAddr::new(source, u16::from_be_bytes([payload[0], payload[1]]));
        let dst = SocketAddr::new(destination, u16::from_be_bytes([payload[2], payload[3]]));
        if src.port() == 0 || dst.port() == 0 {
            return Err(());
        }
        if protocol == IpProtocol::Udp {
            result.udp_destination = Some(dst);
        }
        if protocol == IpProtocol::Tcp && !fragmented {
            let packet = TcpPacket::new_checked(payload).map_err(|_| ())?;
            TcpRepr::parse(
                &packet,
                &source.into(),
                &destination.into(),
                &ChecksumCapabilities::default(),
            )
            .map_err(|_| ())?;
            result.tcp_key = Some((src, dst));
            if packet.syn() && !packet.ack() && !packet.fin() && !packet.rst() {
                result.new_tcp = Some((src, dst));
            }
        }
    }
    Ok(result)
}
