//! DNS query and response codec for the TUN stub. Upstream resolution stays
//! in `Resolver`; this module only frames the packets the virtual adapter sees.
use std::net::IpAddr;

use crate::wire;

pub const DNS_A: u16 = 1;
pub const AAAA: u16 = 28;
const MAX_QUERY: usize = 2048;
const MAX_RESPONSE: usize = 512;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DnsQuestion {
    pub id: u16,
    pub name: String,
    pub kind: u16,
    pub recursion_desired: bool,
}

pub fn decode_query(packet: &[u8]) -> Result<DnsQuestion, &'static str> {
    if packet.len() < 12 || packet.len() > MAX_QUERY {
        return Err("DnsTruncated");
    }
    let id = wire::word(packet, 0)?;
    let flags = wire::word(packet, 2)?;
    if flags & 0x8000 != 0 || flags & 0x7a00 != 0 {
        return Err("DnsHeader");
    }
    if wire::word(packet, 4)? != 1 || wire::word(packet, 6)? != 0 || wire::word(packet, 8)? != 0 {
        return Err("DnsQuestion");
    }
    let additional = wire::word(packet, 10)? as usize;
    if additional > 4 {
        return Err("DnsRecordLimit");
    }
    let mut cursor = 12;
    let name = wire::name(packet, &mut cursor)?;
    if name.is_empty() {
        return Err("DnsQueryName");
    }
    let kind = wire::word(packet, cursor)?;
    let class = wire::word(packet, cursor + 2)?;
    cursor += 4;
    if class != 1 {
        return Err("DnsQuestion");
    }
    for _ in 0..additional {
        wire::name(packet, &mut cursor)?;
        let size = wire::word(packet, cursor + 8)? as usize;
        cursor = cursor
            .checked_add(10)
            .and_then(|next| next.checked_add(size))
            .ok_or("DnsTruncated")?;
        if cursor > packet.len() {
            return Err("DnsTruncated");
        }
    }
    if cursor != packet.len() {
        return Err("DnsTrailing");
    }
    Ok(DnsQuestion {
        id,
        name,
        kind,
        recursion_desired: flags & 0x0100 != 0,
    })
}

pub fn encode_query(question: &DnsQuestion) -> Result<Vec<u8>, &'static str> {
    let mut packet = vec![
        (question.id >> 8) as u8,
        question.id as u8,
        if question.recursion_desired { 1 } else { 0 },
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    ];
    push_name(&mut packet, &question.name)?;
    packet.extend(question.kind.to_be_bytes());
    packet.extend(1u16.to_be_bytes());
    Ok(packet)
}

pub fn encode_response(
    question: &DnsQuestion,
    answers: &[IpAddr],
    ttl: u32,
    rcode: u8,
) -> Result<Vec<u8>, &'static str> {
    if rcode > 5 {
        return Err("DnsHeader");
    }
    let ttl = ttl.min(i32::MAX as u32);
    let mut packet = vec![
        (question.id >> 8) as u8,
        question.id as u8,
        0x80 | u8::from(question.recursion_desired),
        0x80 | rcode,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
    ];
    push_name(&mut packet, &question.name)?;
    packet.extend(question.kind.to_be_bytes());
    packet.extend(1u16.to_be_bytes());
    if rcode != 0 {
        return Ok(packet);
    }
    let mut count = 0u16;
    for answer in answers {
        let (kind, bytes) = match answer {
            IpAddr::V4(ip) if question.kind == DNS_A => (DNS_A, ip.octets().to_vec()),
            IpAddr::V6(ip) if question.kind == AAAA => (AAAA, ip.octets().to_vec()),
            _ => continue,
        };
        let mut record = vec![0xc0, 0x0c];
        record.extend(kind.to_be_bytes());
        record.extend(1u16.to_be_bytes());
        record.extend(ttl.to_be_bytes());
        record.extend((bytes.len() as u16).to_be_bytes());
        record.extend(bytes);
        if packet.len() + record.len() > MAX_RESPONSE {
            packet[2] |= 0x02;
            break;
        }
        packet.extend(record);
        count += 1;
    }
    packet[6] = (count >> 8) as u8;
    packet[7] = count as u8;
    Ok(packet)
}

pub fn decode_answers(packet: &[u8]) -> Result<(u16, u8, Vec<IpAddr>), &'static str> {
    if packet.len() < 12 || packet.len() > 4096 {
        return Err("DnsTruncated");
    }
    let id = wire::word(packet, 0)?;
    let flags = wire::word(packet, 2)?;
    if flags & 0x8000 == 0 {
        return Err("DnsHeader");
    }
    let rcode = (flags & 0x000f) as u8;
    let questions = wire::word(packet, 4)? as usize;
    let answers = wire::word(packet, 6)? as usize;
    if questions != 1 || answers > 32 {
        return Err("DnsQuestion");
    }
    let mut cursor = 12;
    wire::name(packet, &mut cursor)?;
    cursor = cursor.checked_add(4).ok_or("DnsTruncated")?;
    let mut ips = Vec::new();
    for _ in 0..answers {
        wire::name(packet, &mut cursor)?;
        let kind = wire::word(packet, cursor)?;
        let class = wire::word(packet, cursor + 2)?;
        let size = wire::word(packet, cursor + 8)? as usize;
        cursor = cursor.checked_add(10).ok_or("DnsTruncated")?;
        let end = cursor.checked_add(size).ok_or("DnsTruncated")?;
        if end > packet.len() || class != 1 {
            return Err("DnsTruncated");
        }
        let data = &packet[cursor..end];
        if kind == DNS_A && data.len() == 4 {
            let octets = <[u8; 4]>::try_from(data).map_err(|_| "DnsTruncated")?;
            ips.push(IpAddr::V4(octets.into()));
        } else if kind == AAAA && data.len() == 16 {
            let octets = <[u8; 16]>::try_from(data).map_err(|_| "DnsTruncated")?;
            ips.push(IpAddr::V6(octets.into()));
        }
        cursor = end;
    }
    Ok((id, rcode, ips))
}

pub fn wrap_tcp(message: &[u8]) -> Result<Vec<u8>, &'static str> {
    if message.is_empty() || message.len() > u16::MAX as usize {
        return Err("DnsTruncated");
    }
    let mut frame = (message.len() as u16).to_be_bytes().to_vec();
    frame.extend(message);
    Ok(frame)
}

pub fn unwrap_tcp(frame: &[u8]) -> Result<&[u8], &'static str> {
    if frame.len() < 2 {
        return Err("DnsTruncated");
    }
    let len = u16::from_be_bytes([frame[0], frame[1]]) as usize;
    let message = frame.get(2..2 + len).ok_or("DnsTruncated")?;
    if message.len() != frame.len() - 2 {
        return Err("DnsTrailing");
    }
    Ok(message)
}

fn push_name(packet: &mut Vec<u8>, name: &str) -> Result<(), &'static str> {
    if name.is_empty() || name.len() > 253 || name.ends_with('.') {
        return Err("DnsQueryName");
    }
    for label in name.split('.') {
        if label.is_empty() || label.len() > 63 || !label.is_ascii() {
            return Err("DnsQueryName");
        }
        packet.push(label.len() as u8);
        packet.extend(label.as_bytes());
    }
    packet.push(0);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{Ipv4Addr, Ipv6Addr};

    #[test]
    fn query_and_dual_stack_answers_round_trip() {
        let question = DnsQuestion {
            id: 0x1234,
            name: "www.example.com".into(),
            kind: DNS_A,
            recursion_desired: true,
        };
        let encoded = encode_query(&question).unwrap();
        assert_eq!(decode_query(&encoded).unwrap(), question);
        let response =
            encode_response(&question, &[IpAddr::V4(Ipv4Addr::new(1, 2, 3, 4))], 30, 0).unwrap();
        let (id, rcode, ips) = decode_answers(&response).unwrap();
        assert_eq!(
            (id, rcode, ips),
            (0x1234, 0, vec!["1.2.3.4".parse().unwrap()])
        );
        let v6 = DnsQuestion {
            kind: AAAA,
            ..question.clone()
        };
        let response = encode_response(&v6, &[IpAddr::V6(Ipv6Addr::LOCALHOST)], 30, 0).unwrap();
        assert_eq!(
            decode_answers(&response).unwrap().2,
            vec![IpAddr::V6(Ipv6Addr::LOCALHOST)]
        );
        let denied = encode_response(&question, &[], 0, 3).unwrap();
        assert_eq!(decode_answers(&denied).unwrap().1, 3);
        assert!(decode_answers(&denied).unwrap().2.is_empty());
        let framed = wrap_tcp(&encoded).unwrap();
        assert_eq!(unwrap_tcp(&framed).unwrap(), encoded.as_slice());
    }

    #[test]
    fn edns_query_is_accepted_and_trailing_bytes_are_not() {
        let mut query = encode_query(&DnsQuestion {
            id: 7,
            name: "edns.example".into(),
            kind: DNS_A,
            recursion_desired: true,
        })
        .unwrap();
        query[11] = 1;
        query.extend([0, 0, 41, 2, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(decode_query(&query).unwrap().name, "edns.example");
        query.push(1);
        assert_eq!(decode_query(&query), Err("DnsTrailing"));
        assert_eq!(unwrap_tcp(&[0, 2, 1]), Err("DnsTruncated"));
    }
}
