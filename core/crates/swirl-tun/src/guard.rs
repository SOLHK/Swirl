//! Packets that must not re-enter the proxy. Bypass is a route instruction,
//! not a silent DIRECT dial.
use std::{collections::BTreeSet, net::IpAddr};

use swirl_dns::{TUN_IPV4, TUN_IPV6};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LoopVerdict {
    Forward,
    Bypass,
    Reject,
}

#[derive(Clone, Debug)]
pub struct LoopGuard {
    proxies: BTreeSet<IpAddr>,
}

impl LoopGuard {
    pub fn new(proxies: impl IntoIterator<Item = IpAddr>) -> Self {
        Self {
            proxies: proxies.into_iter().collect(),
        }
    }

    pub fn proxies(&self) -> &BTreeSet<IpAddr> {
        &self.proxies
    }

    pub fn check(&self, destination: IpAddr) -> LoopVerdict {
        if destination.is_unspecified()
            || destination.is_multicast()
            || matches!(destination, IpAddr::V4(ip) if ip.is_broadcast())
        {
            return LoopVerdict::Reject;
        }
        if destination == IpAddr::V4(TUN_IPV4) || destination == IpAddr::V6(TUN_IPV6) {
            return LoopVerdict::Reject;
        }
        if self.proxies.contains(&destination) {
            return LoopVerdict::Bypass;
        }
        LoopVerdict::Forward
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn proxy_endpoints_are_bypass_and_the_adapter_is_rejected() {
        let guard = LoopGuard::new(["203.0.113.10".parse().unwrap()]);
        assert_eq!(
            guard.check("203.0.113.10".parse().unwrap()),
            LoopVerdict::Bypass
        );
        assert_eq!(guard.check(IpAddr::V4(TUN_IPV4)), LoopVerdict::Reject);
        assert_eq!(
            guard.check("1.2.3.4".parse().unwrap()),
            LoopVerdict::Forward
        );
        assert_eq!(
            guard.check(IpAddr::V4(std::net::Ipv4Addr::BROADCAST)),
            LoopVerdict::Reject
        );
    }
}
