//! SOCKS4/4a CONNECT (original NEC specification). USERID is not password
//! authentication. BIND and UDP are explicitly unsupported; IPv6 is rejected.
use super::{Inbound, InboundKind, Result, Target};
use crate::timing::{self, Phase};
use std::net::{IpAddr, Ipv4Addr};
use swirl_dns::Resolver;
use swirl_subscription::{Credentials, valid_host};
use swirl_transport::BoxStream;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
    time::Instant,
};

async fn terminated(stream: &mut TcpStream, limit: usize) -> Result<Vec<u8>> {
    let mut data = Vec::new();
    for _ in 0..=limit {
        let byte = stream.read_u8().await.map_err(|_| "Socks4Read")?;
        if byte == 0 {
            return Ok(data);
        }
        data.push(byte);
    }
    Err("Socks4FieldLimit")
}
pub(super) async fn accept(stream: &mut TcpStream, auth: &Option<Credentials>) -> Result<Inbound> {
    let result = async {
        // SOCKS4 cannot fulfill the mixed listener's password policy. Refuse
        // before routing, rather than treating USERID as a substitute password.
        if auth.is_some() {
            return Err("InboundAuthentication");
        }
        if stream.read_u8().await.map_err(|_| "Socks4Read")? != 1 {
            return Err("Socks4Command");
        }
        let port = stream.read_u16().await.map_err(|_| "Socks4Read")?;
        let mut address = [0; 4];
        stream
            .read_exact(&mut address)
            .await
            .map_err(|_| "Socks4Read")?;
        let _user = terminated(stream, 255).await?;
        let host = if address[..3] == [0, 0, 0] && address[3] != 0 {
            let bytes = terminated(stream, 253).await?;
            let host = String::from_utf8(bytes).map_err(|_| "InvalidDomain")?;
            if host.parse::<IpAddr>().is_ok() {
                return Err("Socks4Domain");
            }
            host
        } else {
            Ipv4Addr::from(address).to_string()
        };
        if port == 0 || !valid_host(&host) || host == "0.0.0.0" {
            return Err("InvalidTarget");
        }
        Ok(Inbound {
            kind: InboundKind::Socks4,
            target: Target { host, port },
            initial: Vec::new(),
            udp: false,
        })
    }
    .await;
    if result.is_err() {
        let _ = stream.write_all(&[0, 91, 0, 0, 0, 0, 0, 0]).await;
    }
    result
}

pub(super) async fn connect(
    host: &str,
    port: u16,
    user_id: &str,
    remote_dns: bool,
    target: &Target,
    resolver: &Resolver,
    deadline: Instant,
) -> Result<BoxStream> {
    let mut domain = None;
    let ip = match target.host.parse::<IpAddr>() {
        Ok(IpAddr::V4(ip)) => ip,
        Ok(IpAddr::V6(_)) => return Err("Socks4Ipv6Unsupported"),
        Err(_) if remote_dns => {
            domain = Some(target.host.as_str());
            Ipv4Addr::new(0, 0, 0, 1)
        }
        Err(_) => super::within(
            deadline,
            "UpstreamDnsTimeout",
            timing::measure(
                Phase::Resolution,
                resolver.resolve(&target.host, target.port),
            ),
        )
        .await?
        .iter()
        .find_map(|a| {
            if let IpAddr::V4(ip) = a.ip() {
                Some(ip)
            } else {
                None
            }
        })
        .ok_or("Socks4Ipv6Unsupported")?,
    };
    if domain.is_none() && ip.octets()[..3] == [0, 0, 0] {
        return Err("Socks4AmbiguousAddress");
    }
    if user_id.len() > 255
        || user_id.chars().any(char::is_control)
        || target.port == 0
        || !valid_host(&target.host)
    {
        return Err("Socks4Parameters");
    }
    let mut stream = super::connect_tcp(
        resolver,
        &Target {
            host: host.to_owned(),
            port,
        },
        deadline,
    )
    .await?;
    let mut request = vec![4, 1];
    request.extend(target.port.to_be_bytes());
    request.extend(ip.octets());
    request.extend(user_id.as_bytes());
    request.push(0);
    if let Some(domain) = domain {
        request.extend(domain.as_bytes());
        request.push(0);
    }
    super::within(
        deadline,
        "UpstreamProtocolTimeout",
        timing::measure(Phase::ProxyConnectExchange, async {
            stream
                .write_all(&request)
                .await
                .map_err(|_| "Socks4Write")?;
            let mut reply = [0; 8];
            stream
                .read_exact(&mut reply)
                .await
                .map_err(|_| "Socks4Read")?;
            if reply[0] != 0 || reply[1] != 90 {
                return Err("Socks4Rejected");
            }
            Ok(())
        }),
    )
    .await?;
    Ok(Box::new(stream))
}
