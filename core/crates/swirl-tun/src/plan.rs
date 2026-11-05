//! Route and DNS commands for a future elevated helper. Nothing here is executed.
use std::net::IpAddr;

use swirl_dns::{DNS_IPV4, DNS_IPV6, TUN_IPV6};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlannedCommand {
    pub program: &'static str,
    pub args: Vec<String>,
    pub mutates_host: bool,
}

pub fn plan_activation(
    owner: &str,
    physical: &str,
    proxies: &[IpAddr],
) -> Result<Vec<PlannedCommand>, &'static str> {
    if owner.is_empty() || physical.is_empty() || physical.eq_ignore_ascii_case("swirl") {
        return Err("TunPlan");
    }
    let mut commands = vec![
        route("0.0.0.0/0", "198.18.0.1", "Swirl"),
        route("::/0", &TUN_IPV6.to_string(), "Swirl"),
        PlannedCommand {
            program: "netsh",
            args: vec![
                "interface".into(),
                "ipv4".into(),
                "set".into(),
                "dnsservers".into(),
                "name=Swirl".into(),
                "static".into(),
                format!("address={DNS_IPV4}"),
                "validate=yes".into(),
            ],
            mutates_host: true,
        },
        PlannedCommand {
            program: "netsh",
            args: vec![
                "interface".into(),
                "ipv6".into(),
                "set".into(),
                "dnsservers".into(),
                "name=Swirl".into(),
                "static".into(),
                format!("address={DNS_IPV6}"),
                "validate=yes".into(),
            ],
            mutates_host: true,
        },
    ];
    for proxy in proxies {
        let prefix = match proxy {
            IpAddr::V4(ip) => format!("{ip}/32"),
            IpAddr::V6(ip) => format!("{ip}/128"),
        };
        commands.push(route(&prefix, "physical-gateway", physical));
    }
    let _ = owner;
    Ok(commands)
}

fn route(prefix: &str, gateway: &str, interface_name: &str) -> PlannedCommand {
    let family = if prefix.contains(':') { "ipv6" } else { "ipv4" };
    PlannedCommand {
        program: "netsh",
        args: vec![
            "interface".into(),
            family.into(),
            "add".into(),
            "route".into(),
            format!("prefix={prefix}"),
            format!("interface={interface_name}"),
            format!("nexthop={gateway}"),
            "store=active".into(),
        ],
        mutates_host: true,
    }
}

/// Host mutation is not available in this library. Authorization does not
/// spawn a shell or change a route table.
pub fn execute(commands: &[PlannedCommand], authorized: bool) -> Result<(), &'static str> {
    let _ = authorized;
    if commands.iter().any(|command| command.mutates_host) {
        return Err("HostMutationNotAuthorized");
    }
    Ok(())
}

pub fn foreign_tunnels(names: &[impl AsRef<str>]) -> Vec<String> {
    names
        .iter()
        .map(|name| name.as_ref().to_owned())
        .filter(|name| {
            let lower = name.to_ascii_lowercase();
            lower != "swirl"
                && ["tun", "tap", "wintun", "wireguard", "vpn"]
                    .iter()
                    .any(|needle| lower.contains(needle))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plans_are_not_executed_and_proxy_addresses_stay_on_the_physical_nic() {
        let proxy = "203.0.113.10".parse().unwrap();
        let commands = plan_activation("tun-owner-1", "Ethernet", &[proxy]).unwrap();
        assert!(commands.iter().any(|command| {
            command
                .args
                .iter()
                .any(|arg| arg.contains("203.0.113.10/32"))
                && command
                    .args
                    .iter()
                    .any(|arg| arg.contains("interface=Ethernet"))
        }));
        assert!(
            commands
                .iter()
                .any(|command| { command.args.iter().any(|arg| arg.contains("198.18.0.2")) })
        );
        assert_eq!(execute(&commands, true), Err("HostMutationNotAuthorized"));
        assert_eq!(execute(&commands, false), Err("HostMutationNotAuthorized"));
        assert_eq!(
            foreign_tunnels(&["Swirl", "Ethernet", "WireGuard Tunnel"]),
            vec!["WireGuard Tunnel".to_string()]
        );
    }
}
