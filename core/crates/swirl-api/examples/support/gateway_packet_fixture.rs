//! Small IPv4 packet fixtures for the explicitly disposable dual-Wintun smoke.
//! These helpers never dispatch packets or perform any network operation.
use smoltcp::{
    phy::ChecksumCapabilities,
    wire::{
        IpProtocol, Ipv4Packet, Ipv4Repr, TcpControl, TcpPacket, TcpRepr, TcpSeqNumber, UdpPacket,
        UdpRepr,
    },
};
use std::{
    io,
    net::{Ipv4Addr, SocketAddrV4},
};

fn invalid(reason: impl ToString) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason.to_string())
}

fn ip_packet(
    source: Ipv4Addr,
    destination: Ipv4Addr,
    protocol: IpProtocol,
    payload: &[u8],
) -> Vec<u8> {
    let mut bytes = vec![0; 20 + payload.len()];
    Ipv4Repr {
        src_addr: source,
        dst_addr: destination,
        next_header: protocol,
        payload_len: payload.len(),
        hop_limit: 64,
    }
    .emit(
        &mut Ipv4Packet::new_unchecked(&mut bytes[..]),
        &ChecksumCapabilities::default(),
    );
    bytes[20..].copy_from_slice(payload);
    bytes
}

pub fn udp_packet(source: SocketAddrV4, destination: SocketAddrV4, data: &[u8]) -> Vec<u8> {
    let mut bytes = vec![0; 8 + data.len()];
    UdpRepr {
        src_port: source.port(),
        dst_port: destination.port(),
    }
    .emit(
        &mut UdpPacket::new_unchecked(&mut bytes[..]),
        &(*source.ip()).into(),
        &(*destination.ip()).into(),
        data.len(),
        |buffer| buffer.copy_from_slice(data),
        &ChecksumCapabilities::default(),
    );
    ip_packet(*source.ip(), *destination.ip(), IpProtocol::Udp, &bytes)
}

pub fn tcp_packet(
    source: SocketAddrV4,
    destination: SocketAddrV4,
    sequence: i32,
    acknowledgement: Option<i32>,
    control: TcpControl,
    data: &[u8],
) -> Vec<u8> {
    let repr = TcpRepr {
        src_port: source.port(),
        dst_port: destination.port(),
        control,
        seq_number: TcpSeqNumber(sequence),
        ack_number: acknowledgement.map(TcpSeqNumber),
        window_len: 65535,
        window_scale: None,
        max_seg_size: (control == TcpControl::Syn).then_some(1200),
        sack_permitted: false,
        sack_ranges: [None; 3],
        timestamp: None,
        payload: data,
    };
    let mut bytes = vec![0; repr.buffer_len()];
    repr.emit(
        &mut TcpPacket::new_unchecked(&mut bytes[..]),
        &(*source.ip()).into(),
        &(*destination.ip()).into(),
        &ChecksumCapabilities::default(),
    );
    ip_packet(*source.ip(), *destination.ip(), IpProtocol::Tcp, &bytes)
}

pub struct Envelope<'a> {
    pub source: Ipv4Addr,
    pub destination: Ipv4Addr,
    pub protocol: IpProtocol,
    pub ttl: u8,
    pub payload: &'a [u8],
}

pub fn envelope(bytes: &[u8]) -> io::Result<Envelope<'_>> {
    let packet = Ipv4Packet::new_checked(bytes).map_err(invalid)?;
    if packet.version() != 4
        || !packet.verify_checksum()
        || usize::from(packet.total_len()) != bytes.len()
        || packet.more_frags()
        || packet.frag_offset() != 0
    {
        return Err(invalid("invalid or fragmented IPv4 fixture packet"));
    }
    Ok(Envelope {
        source: packet.src_addr(),
        destination: packet.dst_addr(),
        protocol: packet.next_header(),
        ttl: packet.hop_limit(),
        payload: packet.payload(),
    })
}

/// Every byte other than the router-decremented TTL and its header checksum
/// must survive both forwarding hops. This is not a loose tuple-only match.
pub fn forwarding_identity(bytes: &[u8]) -> io::Result<(Vec<u8>, u8)> {
    let ttl = envelope(bytes)?.ttl;
    let mut identity = bytes.to_vec();
    identity[8] = 0;
    identity[10] = 0;
    identity[11] = 0;
    Ok((identity, ttl))
}

pub struct Segment {
    pub source: SocketAddrV4,
    pub destination: SocketAddrV4,
    pub sequence: i32,
    pub acknowledgement: Option<i32>,
    pub control: TcpControl,
    pub payload: Vec<u8>,
}

pub fn tcp_segment(bytes: &[u8]) -> io::Result<Option<Segment>> {
    let ip = envelope(bytes)?;
    if ip.protocol != IpProtocol::Tcp {
        return Ok(None);
    }
    let packet = TcpPacket::new_checked(ip.payload).map_err(invalid)?;
    let repr = TcpRepr::parse(
        &packet,
        &ip.source.into(),
        &ip.destination.into(),
        &ChecksumCapabilities::default(),
    )
    .map_err(invalid)?;
    Ok(Some(Segment {
        source: SocketAddrV4::new(ip.source, repr.src_port),
        destination: SocketAddrV4::new(ip.destination, repr.dst_port),
        sequence: repr.seq_number.0,
        acknowledgement: repr.ack_number.map(|ack| ack.0),
        control: repr.control,
        payload: repr.payload.to_vec(),
    }))
}

pub type Datagram = (SocketAddrV4, SocketAddrV4, Vec<u8>);

pub fn udp_datagram(bytes: &[u8]) -> io::Result<Option<Datagram>> {
    let ip = envelope(bytes)?;
    if ip.protocol != IpProtocol::Udp {
        return Ok(None);
    }
    let packet = UdpPacket::new_checked(ip.payload).map_err(invalid)?;
    let repr = UdpRepr::parse(
        &packet,
        &ip.source.into(),
        &ip.destination.into(),
        &ChecksumCapabilities::default(),
    )
    .map_err(invalid)?;
    Ok(Some((
        SocketAddrV4::new(ip.source, repr.src_port),
        SocketAddrV4::new(ip.destination, repr.dst_port),
        packet.payload().to_vec(),
    )))
}
