//! IPv4 gateway admission for the existing packet stack.
//!
//! This is not a routing engine or a replacement for Windows filtering. Wintun
//! exposes IP packets without physical arrival-interface metadata. The Windows
//! gateway lease must therefore reject spoofed source addresses on its dedicated
//! LAN before forwarding them to this stack. Host traffic uses the same stack.
use ipnet::Ipv4Net;
use std::{
    collections::HashMap,
    io,
    net::{IpAddr, Ipv4Addr},
    sync::{Arc, Mutex},
};

#[derive(Clone, Debug)]
pub struct GatewayIngress {
    pub lan_subnet: Ipv4Net,
    pub gateway: Ipv4Addr,
    pub allowed_sources: Vec<Ipv4Net>,
    pub local_sources: Vec<IpAddr>,
    pub protected_hosts: Vec<IpAddr>,
    pub max_tcp_per_client: usize,
    pub max_udp_per_client: usize,
    pub max_dns_per_client: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SourceKind {
    Host,
    Lan,
}

impl GatewayIngress {
    pub fn validate(&self) -> io::Result<()> {
        if !private_subnet(self.lan_subnet)
            || !self.lan_subnet.contains(&self.gateway)
            || self.gateway == self.lan_subnet.network()
            || self.gateway == self.lan_subnet.broadcast()
            || self.allowed_sources.is_empty()
            || self.allowed_sources.len() > 64
            || self.local_sources.is_empty()
            || self.local_sources.len() > 256
            || self.protected_hosts.is_empty()
            || self.protected_hosts.len() > 256
            || !self.local_sources.contains(&self.gateway.into())
            || !self.protected_hosts.contains(&self.gateway.into())
            || self.allowed_sources.iter().any(|net| {
                net.addr() != net.network()
                    || net.prefix_len() < self.lan_subnet.prefix_len()
                    || !self.lan_subnet.contains(&net.network())
                    || !self.lan_subnet.contains(&net.broadcast())
            })
            || self
                .local_sources
                .iter()
                .chain(self.protected_hosts.iter())
                .any(|ip| ip.is_unspecified() || ip.is_multicast())
            || !(1..=1024).contains(&self.max_tcp_per_client)
            || !(1..=512).contains(&self.max_udp_per_client)
            || !(1..=16).contains(&self.max_dns_per_client)
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "invalid dedicated IPv4 gateway admission",
            ));
        }
        Ok(())
    }

    /// This distinction is based on source addresses only. Its Host result is
    /// safe only while the Windows lease's physical-source filters are active.
    pub fn source(&self, address: IpAddr) -> Option<SourceKind> {
        if self.local_sources.contains(&address) {
            return Some(SourceKind::Host);
        }
        let IpAddr::V4(address) = address else {
            // Gateway clients are IPv4-only. Local host IPv6 remains supported.
            return None;
        };
        if address == self.gateway
            || address == self.lan_subnet.network()
            || address == self.lan_subnet.broadcast()
            || self.protected_hosts.contains(&address.into())
            || !self
                .allowed_sources
                .iter()
                .any(|net| net.contains(&address))
        {
            return None;
        }
        Some(SourceKind::Lan)
    }

    pub fn permits(&self, source: IpAddr, destination: IpAddr) -> bool {
        match self.source(source) {
            Some(SourceKind::Host) => true,
            Some(SourceKind::Lan) => {
                let IpAddr::V4(address) = destination else {
                    return false;
                };
                !address.is_loopback()
                    && !address.is_unspecified()
                    && !address.is_multicast()
                    && !address.is_link_local()
                    && !address.is_broadcast()
                    && address.octets()[0] != 0
                    && address.octets()[0] < 240
                    && address != Ipv4Addr::new(100, 100, 100, 200)
                    && address != Ipv4Addr::new(168, 63, 129, 16)
                    && address != self.lan_subnet.network()
                    && address != self.lan_subnet.broadcast()
                    && !self.protected_hosts.contains(&destination)
                    && !self.local_sources.contains(&destination)
            }
            None => false,
        }
    }
}

fn private_subnet(net: Ipv4Net) -> bool {
    let private = [
        Ipv4Net::new(Ipv4Addr::new(10, 0, 0, 0), 8),
        Ipv4Net::new(Ipv4Addr::new(172, 16, 0, 0), 12),
        Ipv4Net::new(Ipv4Addr::new(192, 168, 0, 0), 16),
    ];
    net.addr() == net.network()
        && net.prefix_len() <= 30
        && private.into_iter().flatten().any(|private| {
            net.prefix_len() >= private.prefix_len()
                && private.contains(&net.network())
                && private.contains(&net.broadcast())
        })
}

#[derive(Clone, Copy, Debug)]
pub enum FlowClass {
    Tcp,
    Udp,
    Dns,
}

#[derive(Clone, Debug, Default)]
pub struct ClientBudget(Arc<Mutex<HashMap<IpAddr, [usize; 3]>>>);

/// RAII release covers normal close, cancellation, rejected outbound and a task
/// dropped before its first poll. Empty entries are removed, bounding the map.
pub struct ClientPermit {
    budget: ClientBudget,
    source: IpAddr,
    class: usize,
}

impl ClientBudget {
    pub fn acquire(
        &self,
        config: &GatewayIngress,
        source: IpAddr,
        destination: IpAddr,
        class: FlowClass,
    ) -> io::Result<Option<ClientPermit>> {
        if !config.permits(source, destination) {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "gateway source or host destination denied",
            ));
        }
        if config.source(source) == Some(SourceKind::Host) {
            return Ok(None);
        }
        let (class, limit) = match class {
            FlowClass::Tcp => (0, config.max_tcp_per_client),
            FlowClass::Udp => (1, config.max_udp_per_client),
            FlowClass::Dns => (2, config.max_dns_per_client),
        };
        let mut clients = self
            .0
            .lock()
            .map_err(|_| io::Error::other("gateway admission state unavailable"))?;
        let counts = clients.entry(source).or_default();
        if counts[class] >= limit {
            return Err(io::Error::new(
                io::ErrorKind::WouldBlock,
                "gateway client flow limit",
            ));
        }
        counts[class] += 1;
        Ok(Some(ClientPermit {
            budget: self.clone(),
            source,
            class,
        }))
    }
}

impl Drop for ClientPermit {
    fn drop(&mut self) {
        if let Ok(mut clients) = self.budget.0.lock()
            && let Some(counts) = clients.get_mut(&self.source)
        {
            counts[self.class] = counts[self.class].saturating_sub(1);
            if counts.iter().all(|count| *count == 0) {
                clients.remove(&self.source);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn policy() -> GatewayIngress {
        GatewayIngress {
            lan_subnet: "192.168.137.0/24".parse().unwrap(),
            gateway: "192.168.137.1".parse().unwrap(),
            allowed_sources: vec!["192.168.137.128/25".parse().unwrap()],
            local_sources: vec!["192.168.137.1".parse().unwrap(), "fd00::1".parse().unwrap()],
            protected_hosts: vec![
                "192.168.137.1".parse().unwrap(),
                "192.168.1.2".parse().unwrap(),
            ],
            max_tcp_per_client: 1,
            max_udp_per_client: 1,
            max_dns_per_client: 1,
        }
    }
    #[test]
    fn source_and_host_isolation_preserve_local_ipv6_only() {
        let p = policy();
        p.validate().unwrap();
        let destination = "203.0.113.1".parse().unwrap();
        assert!(p.permits("192.168.137.129".parse().unwrap(), destination));
        for source in ["192.168.137.2", "192.168.137.255", "203.0.113.2", "fd00::2"] {
            assert!(!p.permits(source.parse().unwrap(), destination));
        }
        for destination in [
            "127.0.0.1",
            "192.168.137.1",
            "192.168.1.2",
            "ff02::1",
            "169.254.169.254",
            "100.100.100.200",
            "0.1.2.3",
            "240.0.0.1",
            "192.168.137.255",
        ] {
            assert!(!p.permits(
                "192.168.137.129".parse().unwrap(),
                destination.parse().unwrap()
            ));
        }
        assert!(p.permits("fd00::1".parse().unwrap(), "2001:db8::1".parse().unwrap()));
    }
    #[test]
    fn independent_client_budgets_release_on_drop() {
        let p = policy();
        let budget = ClientBudget::default();
        let source = "192.168.137.129".parse().unwrap();
        let destination = "203.0.113.1".parse().unwrap();
        let first = budget
            .acquire(&p, source, destination, FlowClass::Udp)
            .unwrap();
        assert!(
            budget
                .acquire(&p, source, destination, FlowClass::Udp)
                .is_err()
        );
        let other = budget
            .acquire(
                &p,
                "192.168.137.130".parse().unwrap(),
                destination,
                FlowClass::Udp,
            )
            .unwrap();
        let dns = budget
            .acquire(&p, source, destination, FlowClass::Dns)
            .unwrap();
        drop((first, other, dns));
        assert!(budget.0.lock().unwrap().is_empty());
        assert!(
            budget
                .acquire(&p, source, destination, FlowClass::Udp)
                .is_ok()
        );
    }
    #[test]
    fn public_or_wider_network_and_missing_host_inventory_are_rejected() {
        let mut p = policy();
        p.allowed_sources = vec!["0.0.0.0/0".parse().unwrap()];
        assert!(p.validate().is_err());
        let mut p = policy();
        p.protected_hosts.clear();
        assert!(p.validate().is_err());
        let mut p = policy();
        p.lan_subnet = "203.0.113.0/24".parse().unwrap();
        assert!(p.validate().is_err());
    }
}
