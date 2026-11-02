//! IPv4/IPv6 and UDP/TCP header classification. TCP state stays in smoltcp.
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Packet {
    Tcp {
        source: SocketAddr,
        destination: SocketAddr,
        syn: bool,
        ack: bool,
    },
    Udp {
        source: SocketAddr,
        destination: SocketAddr,
        payload: Vec<u8>,
    },
    Other,
}

pub fn parse(packet: &[u8]) -> Result<Packet, &'static str> {
    if packet.is_empty() {
        return Err("TunPacketTruncated");
    }
    match packet[0] >> 4 {
        4 => parse_v4(packet),
        6 => parse_v6(packet),
        _ => Err("TunPacketVersion"),
    }
}

pub fn udp(
    source: SocketAddr,
    destination: SocketAddr,
    payload: &[u8],
    ident: u16,
) -> Result<Vec<u8>, &'static str> {
    if payload.len() > 2048 {
        return Err("TunDatagramTooLarge");
    }
    match (source, destination) {
        (SocketAddr::V4(src), SocketAddr::V4(dst)) => udp_v4(src, dst, payload, ident),
        (SocketAddr::V6(src), SocketAddr::V6(dst)) => udp_v6(src, dst, payload),
        _ => Err("TunPacketFamily"),
    }
}

fn parse_v4(packet: &[u8]) -> Result<Packet, &'static str> {
    if packet.len() < 20 {
        return Err("TunPacketTruncated");
    }
    let header = usize::from(packet[0] & 0x0f) * 4;
    if header < 20 || packet.len() < header {
        return Err("TunPacketTruncated");
    }
    let total = u16::from_be_bytes([packet[2], packet[3]]) as usize;
    if total < header || total > packet.len() {
        return Err("TunPacketLength");
    }
    let source = Ipv4Addr::new(packet[12], packet[13], packet[14], packet[15]);
    let destination = Ipv4Addr::new(packet[16], packet[17], packet[18], packet[19]);
    transport(
        IpAddr::V4(source),
        IpAddr::V4(destination),
        packet[9],
        &packet[header..total],
    )
}

fn parse_v6(packet: &[u8]) -> Result<Packet, &'static str> {
    if packet.len() < 40 {
        return Err("TunPacketTruncated");
    }
    let payload_len = u16::from_be_bytes([packet[4], packet[5]]) as usize;
    if 40 + payload_len > packet.len() {
        return Err("TunPacketLength");
    }
    let source =
        Ipv6Addr::from(<[u8; 16]>::try_from(&packet[8..24]).map_err(|_| "TunPacketTruncated")?);
    let destination =
        Ipv6Addr::from(<[u8; 16]>::try_from(&packet[24..40]).map_err(|_| "TunPacketTruncated")?);
    let mut next = packet[6];
    let mut offset = 40;
    let end = 40 + payload_len;
    for _ in 0..4 {
        if matches!(next, 6 | 17 | 58) {
            break;
        }
        if !matches!(next, 0 | 43 | 44 | 60) {
            return Ok(Packet::Other);
        }
        if offset + 8 > end {
            return Err("TunPacketTruncated");
        }
        let header_len = if next == 44 {
            8
        } else {
            (usize::from(packet[offset + 1]) + 1) * 8
        };
        if next == 44 {
            let fragment = u16::from_be_bytes([packet[offset + 2], packet[offset + 3]]);
            if fragment & !7 != 0 {
                return Ok(Packet::Other);
            }
        }
        next = packet[offset];
        offset += header_len;
        if offset > end {
            return Err("TunPacketTruncated");
        }
    }
    transport(
        IpAddr::V6(source),
        IpAddr::V6(destination),
        next,
        &packet[offset..end],
    )
}

fn transport(
    source: IpAddr,
    destination: IpAddr,
    protocol: u8,
    segment: &[u8],
) -> Result<Packet, &'static str> {
    match protocol {
        6 if segment.len() >= 20 => {
            let flags = segment[13];
            Ok(Packet::Tcp {
                source: SocketAddr::new(source, u16::from_be_bytes([segment[0], segment[1]])),
                destination: SocketAddr::new(
                    destination,
                    u16::from_be_bytes([segment[2], segment[3]]),
                ),
                syn: flags & 0x02 != 0,
                ack: flags & 0x10 != 0,
            })
        }
        17 if segment.len() >= 8 => {
            let length = u16::from_be_bytes([segment[4], segment[5]]) as usize;
            if length < 8 || length > segment.len() {
                return Err("TunPacketLength");
            }
            Ok(Packet::Udp {
                source: SocketAddr::new(source, u16::from_be_bytes([segment[0], segment[1]])),
                destination: SocketAddr::new(
                    destination,
                    u16::from_be_bytes([segment[2], segment[3]]),
                ),
                payload: segment[8..length].to_vec(),
            })
        }
        6 | 17 => Err("TunPacketTruncated"),
        _ => Ok(Packet::Other),
    }
}

fn udp_v4(
    source: std::net::SocketAddrV4,
    destination: std::net::SocketAddrV4,
    payload: &[u8],
    ident: u16,
) -> Result<Vec<u8>, &'static str> {
    let udp_len = 8 + payload.len();
    let mut packet = vec![0u8; 20 + udp_len];
    packet[0] = 0x45;
    let total = u16::try_from(packet.len()).map_err(|_| "TunPacketLength")?;
    packet[2..4].copy_from_slice(&total.to_be_bytes());
    packet[4..6].copy_from_slice(&ident.to_be_bytes());
    packet[6] = 0x40;
    packet[8] = 64;
    packet[9] = 17;
    packet[12..16].copy_from_slice(&source.ip().octets());
    packet[16..20].copy_from_slice(&destination.ip().octets());
    let checksum = internet_checksum(&packet[..20], 0);
    packet[10..12].copy_from_slice(&checksum.to_be_bytes());
    write_udp(
        &mut packet[20..],
        source.port(),
        destination.port(),
        payload,
    );
    let pseudo = udp_checksum_v4(*source.ip(), *destination.ip(), &packet[20..]);
    packet[26..28].copy_from_slice(&pseudo.to_be_bytes());
    Ok(packet)
}

fn udp_v6(
    source: std::net::SocketAddrV6,
    destination: std::net::SocketAddrV6,
    payload: &[u8],
) -> Result<Vec<u8>, &'static str> {
    let udp_len = 8 + payload.len();
    let mut packet = vec![0u8; 40 + udp_len];
    packet[0] = 0x60;
    packet[4..6].copy_from_slice(&(udp_len as u16).to_be_bytes());
    packet[6] = 17;
    packet[7] = 64;
    packet[8..24].copy_from_slice(&source.ip().octets());
    packet[24..40].copy_from_slice(&destination.ip().octets());
    write_udp(
        &mut packet[40..],
        source.port(),
        destination.port(),
        payload,
    );
    let checksum = udp_checksum_v6(*source.ip(), *destination.ip(), &packet[40..]);
    packet[46..48].copy_from_slice(&checksum.to_be_bytes());
    Ok(packet)
}

fn write_udp(header: &mut [u8], source: u16, destination: u16, payload: &[u8]) {
    header[0..2].copy_from_slice(&source.to_be_bytes());
    header[2..4].copy_from_slice(&destination.to_be_bytes());
    header[4..6].copy_from_slice(&(8 + payload.len() as u16).to_be_bytes());
    header[8..].copy_from_slice(payload);
}

fn udp_checksum_v4(source: Ipv4Addr, destination: Ipv4Addr, udp: &[u8]) -> u16 {
    let mut sum = 0u32;
    sum = add_bytes(sum, &source.octets());
    sum = add_bytes(sum, &destination.octets());
    sum += 17u32;
    sum += udp.len() as u32;
    finish_udp(sum, udp)
}

fn udp_checksum_v6(source: Ipv6Addr, destination: Ipv6Addr, udp: &[u8]) -> u16 {
    let mut sum = 0u32;
    sum = add_bytes(sum, &source.octets());
    sum = add_bytes(sum, &destination.octets());
    sum += udp.len() as u32;
    sum += 17u32;
    finish_udp(sum, udp)
}

fn finish_udp(sum: u32, udp: &[u8]) -> u16 {
    let mut body = udp.to_vec();
    body[6] = 0;
    body[7] = 0;
    let value = internet_checksum(&body, sum);
    if value == 0 { 0xffff } else { value }
}

fn add_bytes(mut sum: u32, bytes: &[u8]) -> u32 {
    for pair in bytes.chunks(2) {
        let word = if pair.len() == 2 {
            u16::from_be_bytes([pair[0], pair[1]])
        } else {
            u16::from_be_bytes([pair[0], 0])
        };
        sum += u32::from(word);
    }
    sum
}

fn internet_checksum(bytes: &[u8], mut sum: u32) -> u16 {
    sum = add_bytes(sum, bytes);
    while sum > 0xffff {
        sum = (sum & 0xffff) + (sum >> 16);
    }
    !(sum as u16)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn udp_headers_round_trip_for_both_families() {
        let v4 = udp(
            "10.0.0.8:53000".parse().unwrap(),
            "1.2.3.4:53".parse().unwrap(),
            b"query",
            7,
        )
        .unwrap();
        let Packet::Udp {
            source,
            destination,
            payload,
        } = parse(&v4).unwrap()
        else {
            panic!("v4 udp");
        };
        assert_eq!(source, "10.0.0.8:53000".parse().unwrap());
        assert_eq!(destination, "1.2.3.4:53".parse().unwrap());
        assert_eq!(payload, b"query");
        let header_sum = internet_checksum(&v4[..20], 0);
        assert_eq!(header_sum, 0);
        let v6 = udp(
            "[fd00::8]:53000".parse().unwrap(),
            "[2001:db8::1]:53".parse().unwrap(),
            b"query",
            1,
        )
        .unwrap();
        let Packet::Udp { payload, .. } = parse(&v6).unwrap() else {
            panic!("v6 udp");
        };
        assert_eq!(payload, b"query");
        assert_eq!(parse(&[0x45]).unwrap_err(), "TunPacketTruncated");
    }
}
