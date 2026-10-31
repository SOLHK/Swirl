//! Explicit, authenticated LAN ingress configuration. The existing system
//! listener remains loopback-only; a LAN listener has its own lifecycle.
use serde::{Deserialize, Serialize};
use std::net::{IpAddr, Ipv4Addr};
use swirl_subscription::Credentials;

type Result<T> = std::result::Result<T, &'static str>;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LanConfig {
    pub listen_ip: IpAddr,
    pub http_port: u16,
    pub socks_port: u16,
    pub udp_port_start: u16,
    pub udp_port_end: u16,
    pub allowed_cidrs: Vec<String>,
    pub auth: Credentials,
    pub max_connections: usize,
    pub max_connections_per_client: usize,
    pub auth_failures_per_minute: u32,
    pub idle_timeout_secs: u64,
    /// All host addresses enumerated by the platform controller. The native
    /// core additionally rejects intrinsically unsafe destination ranges.
    pub host_addresses: Vec<IpAddr>,
}

#[derive(Clone, Copy)]
pub(crate) struct Cidr {
    network: u32,
    mask: u32,
    prefix: u32,
}

impl Cidr {
    fn parse(value: &str) -> Result<Self> {
        let (address, prefix) = value.split_once('/').unwrap_or((value, "32"));
        let address = address.parse::<Ipv4Addr>().map_err(|_| "LanClientCidr")?;
        let prefix = prefix.parse::<u32>().map_err(|_| "LanClientCidr")?;
        if prefix > 32 {
            return Err("LanClientCidr");
        }
        let mask = u32::MAX.checked_shl(32 - prefix).unwrap_or(0);
        let network = u32::from(address) & mask;
        let last = network | !mask;
        if !Ipv4Addr::from(network).is_private() || !Ipv4Addr::from(last).is_private() {
            return Err("LanClientCidrNotPrivate");
        }
        Ok(Self {
            network,
            mask,
            prefix,
        })
    }

    pub(crate) fn contains(self, ip: IpAddr) -> bool {
        let IpAddr::V4(ip) = ip else { return false };
        let value = u32::from(ip);
        value & self.mask == self.network
            && (self.prefix >= 31
                || (value != self.network && value != (self.network | !self.mask)))
    }
}

impl LanConfig {
    pub fn validate(&self) -> Result<()> {
        let IpAddr::V4(ip) = self.listen_ip else {
            return Err("LanIpv6NotValidated");
        };
        if !ip.is_private() {
            return Err("LanPrivateAddressRequired");
        }
        self.validate_common()?;
        self.cidrs()?;
        Ok(())
    }

    pub(crate) fn validate_common(&self) -> Result<()> {
        if self.http_port == 0 || self.socks_port == 0 {
            return Err("LanPort");
        }
        if self.udp_port_start == 0
            || self.udp_port_end < self.udp_port_start
            || u32::from(self.udp_port_end) - u32::from(self.udp_port_start) >= 64
        {
            return Err("LanUdpPortRange");
        }
        if self.allowed_cidrs.is_empty() || self.allowed_cidrs.len() > 64 {
            return Err("LanClientCidrCount");
        }
        if self.auth.username.is_empty()
            || self.auth.username.len() > 255
            || self.auth.username.contains(':')
            || !(12..=255).contains(&self.auth.password.len())
            || self
                .auth
                .username
                .chars()
                .chain(self.auth.password.chars())
                .any(char::is_control)
        {
            return Err("LanCredentials");
        }
        if !(1..=256).contains(&self.max_connections)
            || !(1..=64).contains(&self.max_connections_per_client)
            || self.max_connections_per_client > self.max_connections
            || !(1..=20).contains(&self.auth_failures_per_minute)
            || !(60..=86400).contains(&self.idle_timeout_secs)
        {
            return Err("LanLimits");
        }
        if self.host_addresses.is_empty()
            || self.host_addresses.len() > 128
            || !self.host_addresses.contains(&self.listen_ip)
        {
            return Err("LanHostAddressInventory");
        }
        Ok(())
    }

    pub(crate) fn cidrs(&self) -> Result<Vec<Cidr>> {
        self.allowed_cidrs
            .iter()
            .map(|value| Cidr::parse(value))
            .collect()
    }

    pub(crate) fn check_target(&self, host: &str) -> Result<()> {
        let host = host.trim_end_matches('.');
        if host.eq_ignore_ascii_case("localhost")
            || host.to_ascii_lowercase().ends_with(".localhost")
        {
            return Err("LanHostAccessDenied");
        }
        let Ok(ip) = host.parse::<IpAddr>() else {
            return Ok(());
        };
        let ip = normalize_ip(ip);
        let unsafe_ip = match ip {
            IpAddr::V4(v4) => {
                v4.is_loopback()
                    || v4.is_unspecified()
                    || v4.is_link_local()
                    || v4.is_multicast()
                    || v4.is_broadcast()
                    || v4.octets()[0] == 0
                    || v4.octets()[0] >= 240
                    || v4 == Ipv4Addr::new(100, 100, 100, 200)
                    || v4 == Ipv4Addr::new(168, 63, 129, 16)
            }
            IpAddr::V6(v6) => {
                v6.is_loopback()
                || v6.is_unspecified()
                || v6.is_multicast()
                || v6.is_unicast_link_local()
                // Reject deprecated IPv4-compatible forms as well as scoped
                // link-local targets. IPv4-mapped addresses are checked above.
                || v6.segments()[..6] == [0; 6]
            }
        };
        if unsafe_ip
            || self
                .host_addresses
                .iter()
                .any(|address| normalize_ip(*address) == ip)
            || ip == normalize_ip(self.listen_ip)
        {
            return Err("LanHostAccessDenied");
        }
        Ok(())
    }
}

fn normalize_ip(ip: IpAddr) -> IpAddr {
    match ip {
        IpAddr::V6(ip) => ip.to_ipv4_mapped().map_or(IpAddr::V6(ip), IpAddr::V4),
        ip => ip,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    pub(super) fn config() -> LanConfig {
        LanConfig {
            listen_ip: "192.168.50.1".parse().unwrap(),
            http_port: 7899,
            socks_port: 7899,
            udp_port_start: 7900,
            udp_port_end: 7915,
            allowed_cidrs: vec!["192.168.50.0/24".into()],
            auth: Credentials {
                username: "fixture".into(),
                password: "fixture-secret-123".into(),
            },
            max_connections: 128,
            max_connections_per_client: 16,
            auth_failures_per_minute: 5,
            idle_timeout_secs: 300,
            host_addresses: vec!["192.168.50.1".parse().unwrap()],
        }
    }

    #[test]
    fn listener_and_allowlist_fail_closed() {
        let good = config();
        assert!(good.validate().is_ok());
        for address in [
            "0.0.0.0",
            "127.0.0.1",
            "169.254.0.1",
            "8.8.8.8",
            "::",
            "::1",
            "fd00::1",
        ] {
            let mut bad = good.clone();
            bad.listen_ip = address.parse().unwrap();
            assert!(bad.validate().is_err(), "accepted {address}");
        }
        for cidr in [
            "0.0.0.0/0",
            "10.0.0.0/7",
            "192.168.0.0/15",
            "127.0.0.1",
            "192.168.0.0/33",
            "::/0",
        ] {
            let mut bad = good.clone();
            bad.allowed_cidrs = vec![cidr.into()];
            assert!(bad.validate().is_err(), "accepted {cidr}");
        }
        let cidr = good.cidrs().unwrap()[0];
        assert!(cidr.contains("192.168.50.22".parse().unwrap()));
        assert!(!cidr.contains("192.168.51.22".parse().unwrap()));
        assert!(!cidr.contains("192.168.50.0".parse().unwrap()));
        assert!(!cidr.contains("192.168.50.255".parse().unwrap()));
    }

    #[test]
    fn host_and_special_destinations_are_never_proxy_targets() {
        let config = config();
        for host in [
            "localhost",
            "LOCALHOST",
            "a.localhost",
            "127.0.0.8",
            "0.1.2.3",
            "169.254.169.254",
            "192.168.50.1",
            "224.0.0.1",
            "255.255.255.255",
            "::ffff:127.0.0.1",
            "::ffff:192.168.50.1",
            "fe80::1",
            "ff02::1",
            "100.100.100.200",
            "168.63.129.16",
            "localhost.",
            "example.localhost.",
        ] {
            assert_eq!(
                config.check_target(host),
                Err("LanHostAccessDenied"),
                "{host}"
            );
        }
        assert!(config.check_target("example.com").is_ok());
        assert!(config.check_target("8.8.8.8").is_ok());
        assert!(config.check_target("2001:4860:4860::8888").is_ok());
        assert!(config.check_target("::ffff:8.8.8.8").is_ok());
        assert!(config.check_target("192.168.50.20").is_ok());
    }

    #[test]
    fn credentials_and_resource_bounds_are_required() {
        let good = config();
        let mut bad = good.clone();
        bad.auth.password = "short".into();
        assert_eq!(bad.validate(), Err("LanCredentials"));
        let mut bad = good.clone();
        bad.udp_port_end = bad.udp_port_start + 64;
        assert_eq!(bad.validate(), Err("LanUdpPortRange"));
        let mut bad = good.clone();
        bad.host_addresses.clear();
        assert_eq!(bad.validate(), Err("LanHostAddressInventory"));
        let mut bad = good;
        bad.max_connections_per_client = bad.max_connections + 1;
        assert_eq!(bad.validate(), Err("LanLimits"));
    }
}
