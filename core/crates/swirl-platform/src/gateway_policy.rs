//! A typed description of dedicated-LAN isolation, shared with its recovery
//! journal. It contains no packet forwarding engine: Windows admits packets
//! only to the existing Swirl TUN and that TUN's FlowDispatcher owns sessions.
use crate::network_transaction::InterfaceIdentity;
use ipnet::Ipv4Net;
use serde::{Deserialize, Serialize};
use std::{collections::HashSet, io, net::{IpAddr, Ipv4Addr}};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GatewayRequest {
    pub lan: InterfaceIdentity,
    pub subnet: Ipv4Net,
    pub gateway: Ipv4Addr,
    pub allowed_sources: Vec<Ipv4Net>,
    pub dedicated_lan_confirmed: bool,
    pub dhcp: bool,
}

impl GatewayRequest {
    pub fn validate(&self) -> io::Result<()> {
        self.lan.validate()?;
        if !self.dedicated_lan_confirmed || self.subnet.addr() != self.subnet.network()
            || self.subnet.prefix_len() > 30 || !private_subnet(self.subnet)
            || !self.subnet.contains(&self.gateway) || self.gateway == self.subnet.network()
            || self.gateway == self.subnet.broadcast() || self.allowed_sources.is_empty()
            || self.allowed_sources.len() > 64
            || self.allowed_sources.iter().any(|net| net.addr() != net.network() || !self.subnet.contains(net))
        {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid dedicated-LAN request"));
        }
        Ok(())
    }
}

fn private_subnet(subnet: Ipv4Net) -> bool {
    [
        Ipv4Net::new(Ipv4Addr::new(10, 0, 0, 0), 8).expect("constant subnet"),
        Ipv4Net::new(Ipv4Addr::new(172, 16, 0, 0), 12).expect("constant subnet"),
        Ipv4Net::new(Ipv4Addr::new(192, 168, 0, 0), 16).expect("constant subnet"),
    ].iter().any(|net| net.contains(&subnet))
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GatewayIsolationPolicy {
    /// Rule compiler version. Future helpers must retain the corresponding
    /// compiler to recover an older generation instead of changing its shape.
    pub version: u32,
    pub owner: String,
    pub lan: InterfaceIdentity,
    pub lan_luid: u64,
    pub tun: InterfaceIdentity,
    pub tun_luid: u64,
    pub subnet: Ipv4Net,
    pub gateway: Ipv4Addr,
    pub allowed_sources: Vec<Ipv4Net>,
    /// Actual host addresses captured by the elevated Windows preflight.
    /// LAN packets claiming these addresses must never acquire host privileges.
    pub host_addresses: Vec<IpAddr>,
    pub dhcp: bool,
}

impl GatewayIsolationPolicy {
    pub fn name(&self) -> String {
        format!("Swirl.NativeGateway.{}.{}", self.lan.guid, self.owner)
    }

    pub fn validate(&self) -> io::Result<()> {
        self.lan.validate()?;
        self.tun.validate()?;
        if self.version != 1 || self.owner.len() != 32
            || !self.owner.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            || self.lan == self.tun || self.lan.index == self.tun.index
            || self.lan_luid == 0 || self.tun_luid == 0 || self.lan_luid == self.tun_luid
            || self.subnet.addr() != self.subnet.network() || self.subnet.prefix_len() > 30
            || !private_subnet(self.subnet)
            || !self.subnet.contains(&self.gateway)
            || self.gateway == self.subnet.network() || self.gateway == self.subnet.broadcast()
            || self.allowed_sources.is_empty() || self.allowed_sources.len() > 64
            || self.allowed_sources.iter().any(|net| net.addr() != net.network() || !self.subnet.contains(net))
            || self.host_addresses.is_empty() || self.host_addresses.len() > 256
            || !self.host_addresses.contains(&IpAddr::V4(self.gateway))
            || self.host_addresses.iter().any(|ip| ip.is_unspecified() || ip.is_multicast())
            || self.host_addresses.iter().collect::<HashSet<_>>().len() != self.host_addresses.len()
        {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "invalid dedicated-LAN isolation policy"));
        }
        Ok(())
    }

    fn permits_client_address(&self, address: Ipv4Addr) -> bool {
        address != self.subnet.network() && address != self.subnet.broadcast()
            && !self.host_addresses.contains(&IpAddr::V4(address))
            && self.allowed_sources.iter().any(|net| net.contains(&address))
    }

    /// Reference policy for forwarded packets, independent of WFP's compiled
    /// condition layout. Host-local connections do not traverse IPFORWARD.
    /// Return traffic must enter from the owned TUN and target an allowed LAN
    /// client. All IPv6 forwarding in either direction of this LAN is denied.
    pub fn permits_forward(&self, source: IpAddr, destination: IpAddr, incoming_luid: u64, outgoing_luid: u64, private_profile: bool) -> bool {
        if incoming_luid == self.lan_luid {
            let (IpAddr::V4(source), IpAddr::V4(_)) = (source, destination) else { return false };
            return outgoing_luid == self.tun_luid && private_profile && self.permits_client_address(source);
        }
        if outgoing_luid == self.tun_luid { return false; }
        if outgoing_luid == self.lan_luid {
            let (IpAddr::V4(_), IpAddr::V4(destination)) = (source, destination) else { return false };
            return incoming_luid == self.tun_luid && private_profile && self.permits_client_address(destination);
        }
        true
    }

}

#[cfg(test)]
pub(crate) fn fixture() -> GatewayIsolationPolicy {
    GatewayIsolationPolicy {
        version: 1,
        owner: "a".repeat(32),
        lan: InterfaceIdentity::new(11, 1), lan_luid: 110,
        tun: InterfaceIdentity::new(12, 2), tun_luid: 120,
        subnet: "192.168.77.0/24".parse().unwrap(),
        gateway: "192.168.77.1".parse().unwrap(),
        allowed_sources: vec!["192.168.77.0/25".parse().unwrap()],
        host_addresses: vec!["192.168.77.1".parse().unwrap(), "127.0.0.1".parse().unwrap()],
        dhcp: false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forwarding_is_confined_to_authorized_clients_and_tun() {
        let policy = fixture();
        policy.validate().unwrap();
        let check = |ip: &str, dest| policy.permits_forward(ip.parse().unwrap(), "203.0.113.1".parse().unwrap(), 110, dest, true);
        assert!(check("192.168.77.10", 120));
        for ip in ["192.168.77.1", "192.168.77.0", "192.168.77.255", "192.168.77.200", "203.0.113.4", "fd00::1"] {
            assert!(!check(ip, 120), "source {ip}");
        }
        assert!(!check("192.168.77.10", 130));
        assert!(!policy.permits_forward("fd00::1".parse().unwrap(), "fd00::2".parse().unwrap(), 130, 120, true));
        assert!(policy.permits_forward("fd00::1".parse().unwrap(), "fd00::2".parse().unwrap(), 130, 140, true));
    }

    #[test]
    fn return_path_only_accepts_tun_and_known_ipv4_clients() {
        let policy = fixture();
        let remote = "203.0.113.7".parse().unwrap();
        let client = "192.168.77.10".parse().unwrap();
        assert!(policy.permits_forward(remote, client, 120, 110, true));
        assert!(!policy.permits_forward(remote, client, 130, 110, true));
        assert!(!policy.permits_forward(remote, client, 120, 110, false));
        assert!(!policy.permits_forward(client, remote, 110, 120, false));
        for address in ["192.168.77.1", "192.168.77.0", "192.168.77.255", "192.168.77.200", "fd00::1"] {
            assert!(!policy.permits_forward(remote, address.parse().unwrap(), 120, 110, true));
        }
        assert!(!policy.permits_forward("fd00::1".parse().unwrap(), "fd00::2".parse().unwrap(), 120, 110, true));
    }

    #[test]
    fn journal_policy_rejects_public_and_recycled_interface_identities() {
        let mut policy = fixture();
        policy.subnet = "0.0.0.0/0".parse().unwrap();
        assert!(policy.validate().is_err());
        let mut policy = fixture();
        policy.tun.index = policy.lan.index;
        assert!(policy.validate().is_err());
        let mut policy = fixture();
        policy.host_addresses.clear();
        assert!(policy.validate().is_err());
    }
}
