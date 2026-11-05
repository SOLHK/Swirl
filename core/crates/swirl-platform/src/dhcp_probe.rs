//! DHCPINFORM wire messages used by the dedicated-LAN conflict observation.
//! INFORM requests configuration for an already configured address; it never
//! requests a lease or changes the host's address, gateway, or DNS settings.
use std::net::Ipv4Addr;

pub(crate) fn hardware_address(value: &str) -> Option<[u8; 6]> {
    if value.len() > 17 {
        return None;
    }
    let compact = value.replace(['-', ':'], "");
    if compact.len() != 12 || !compact.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return None;
    }
    let mut address = [0; 6];
    for (index, byte) in address.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&compact[index * 2..index * 2 + 2], 16).ok()?;
    }
    (address != [0; 6] && address[0] & 1 == 0).then_some(address)
}

pub(crate) fn inform(transaction: [u8; 4], mac: [u8; 6], source: Ipv4Addr) -> Vec<u8> {
    let mut packet = vec![0; 240];
    packet[0] = 1; // BOOTREQUEST
    packet[1] = 1; // Ethernet
    packet[2] = 6;
    packet[4..8].copy_from_slice(&transaction);
    packet[12..16].copy_from_slice(&source.octets()); // ciaddr, already static
    packet[28..34].copy_from_slice(&mac);
    packet[236..240].copy_from_slice(&[99, 130, 83, 99]);
    packet.extend_from_slice(&[53, 1, 8, 55, 4, 1, 3, 6, 54, 61, 7, 1]);
    packet.extend_from_slice(&mac);
    packet.push(255);
    packet.resize(300, 0);
    packet
}

pub(crate) fn responding_server(
    packet: &[u8],
    transaction: [u8; 4],
    mac: [u8; 6],
) -> Option<Ipv4Addr> {
    if !(240..=1500).contains(&packet.len())
        || packet[..3] != [2, 1, 6]
        || packet[4..8] != transaction
        || packet[28..34] != mac
        || packet[236..240] != [99, 130, 83, 99]
    {
        return None;
    }
    let mut options = ProbeOptions::default();
    options.scan(&packet[240..], true)?;
    match options.overload {
        Some(1) => options.scan(&packet[108..236], false)?,
        Some(2) => options.scan(&packet[44..108], false)?,
        Some(3) => {
            options.scan(&packet[108..236], false)?;
            options.scan(&packet[44..108], false)?;
        }
        Some(_) => return None,
        None => {}
    }
    if !matches!(options.kind.as_slice(), [2 | 5 | 6]) || options.server.len() != 4 {
        return None;
    }
    let address = Ipv4Addr::new(
        options.server[0],
        options.server[1],
        options.server[2],
        options.server[3],
    );
    (!address.is_unspecified() && !address.is_multicast() && !address.is_broadcast())
        .then_some(address)
}

#[derive(Default)]
struct ProbeOptions {
    kind: Vec<u8>,
    server: Vec<u8>,
    overload: Option<u8>,
}

impl ProbeOptions {
    fn scan(&mut self, block: &[u8], primary: bool) -> Option<()> {
        let mut offset = 0;
        while let Some(&option) = block.get(offset) {
            offset += 1;
            if option == 255 {
                return Some(());
            }
            if option == 0 {
                continue;
            }
            let length = usize::from(*block.get(offset)?);
            offset += 1;
            let value = block.get(offset..offset.checked_add(length)?)?;
            offset += length;
            match option {
                52 => {
                    if !primary || value.len() != 1 || self.overload.replace(value[0]).is_some() {
                        return None;
                    }
                }
                53 => {
                    if self.kind.len() + value.len() > 1 {
                        return None;
                    }
                    self.kind.extend_from_slice(value);
                }
                54 => {
                    if self.server.len() + value.len() > 4 {
                        return None;
                    }
                    self.server.extend_from_slice(value);
                }
                // RFC 3396 permits repeated option fragments. Only the fields
                // needed by this observation are concatenated, with fixed caps;
                // unrelated repeated options must not hide a real DHCP server.
                _ => {}
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const MAC: [u8; 6] = [2, 0, 0, 0, 0, 1];
    const TRANSACTION: [u8; 4] = [1, 2, 3, 4];

    fn answer() -> Vec<u8> {
        let mut packet = inform(TRANSACTION, MAC, Ipv4Addr::new(192, 168, 77, 1));
        packet[0] = 2;
        packet.truncate(240);
        packet.extend_from_slice(&[53, 1, 5, 54, 4, 192, 168, 77, 254, 255]);
        packet
    }

    #[test]
    fn inform_does_not_request_or_offer_an_address_lease() {
        let packet = inform(TRANSACTION, MAC, Ipv4Addr::new(192, 168, 77, 1));
        assert_eq!(packet.len(), 300);
        assert_eq!(&packet[12..16], &[192, 168, 77, 1]);
        assert_eq!(&packet[16..28], &[0; 12]);
        assert_eq!(&packet[240..249], &[53, 1, 8, 55, 4, 1, 3, 6, 54]);
        assert_eq!(responding_server(&packet, TRANSACTION, MAC), None);
    }

    #[test]
    fn server_observation_requires_transaction_mac_and_valid_options() {
        let packet = answer();
        assert_eq!(
            responding_server(&packet, TRANSACTION, MAC),
            Some(Ipv4Addr::new(192, 168, 77, 254))
        );
        assert_eq!(responding_server(&packet, [4, 3, 2, 1], MAC), None);
        assert_eq!(responding_server(&packet, TRANSACTION, [4; 6]), None);
        for length in [0, 239, 240, packet.len() - 1] {
            assert_eq!(responding_server(&packet[..length], TRANSACTION, MAC), None);
        }
        let mut duplicate = packet.clone();
        duplicate.pop();
        duplicate.extend_from_slice(&[53, 1, 5, 255]);
        assert_eq!(responding_server(&duplicate, TRANSACTION, MAC), None);
        let mut multicast = packet;
        multicast[245] = 224;
        assert_eq!(responding_server(&multicast, TRANSACTION, MAC), None);
    }

    #[test]
    fn physical_mac_parser_rejects_non_ethernet_and_non_unicast_values() {
        assert_eq!(hardware_address("02-00-00-00-00-01"), Some(MAC));
        assert_eq!(hardware_address("02:00:00:00:00:01"), Some(MAC));
        for invalid in [
            "",
            "00-00-00-00-00-00",
            "ff-ff-ff-ff-ff-ff",
            "010000000001",
            "02000000000g",
        ] {
            assert_eq!(hardware_address(invalid), None);
        }
    }

    #[test]
    fn legitimate_option_fragments_and_overload_do_not_hide_a_server() {
        let expected = Some(Ipv4Addr::new(192, 168, 77, 254));
        let mut repeated = answer();
        repeated.pop();
        repeated.extend_from_slice(&[43, 1, 1, 43, 1, 2, 255]);
        assert_eq!(responding_server(&repeated, TRANSACTION, MAC), expected);
        let mut fragmented = answer();
        fragmented.truncate(243);
        fragmented.extend_from_slice(&[54, 2, 192, 168, 54, 2, 77, 254, 255]);
        assert_eq!(responding_server(&fragmented, TRANSACTION, MAC), expected);
        let mut overloaded = answer();
        overloaded.truncate(240);
        overloaded.extend_from_slice(&[53, 1, 5, 52, 1, 1, 255]);
        overloaded[108..115].copy_from_slice(&[54, 4, 192, 168, 77, 254, 255]);
        assert_eq!(responding_server(&overloaded, TRANSACTION, MAC), expected);
    }
}
