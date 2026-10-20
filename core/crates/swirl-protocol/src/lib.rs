//! Swirl-owned HTTP/SOCKS state machines. Underlying Tokio is generic socket I/O.
use base64::{Engine, engine::general_purpose::STANDARD};
mod diagnostics;
mod dial;
mod probe;
mod shadowsocks;
mod socks4;
mod socks5;
pub mod vision;
mod vless;
mod websocket;
pub use diagnostics::{TcpAttempt, TcpDiagnostic, TcpOutcome, failure_stage};
pub use dial::diagnose_tcp;
use dial::{connect_tcp, within};
pub use probe::health_probe;
pub use shadowsocks::{
    decrypt_datagram as ss_decrypt_datagram, encrypt_datagram as ss_encrypt_datagram,
};
pub use socks5::UdpAssociation as Socks5UdpAssociation;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use swirl_dns::Resolver;
use swirl_subscription::{Credentials, Outbound, valid_host};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
    time::Instant,
};

pub type Result<T> = std::result::Result<T, &'static str>;
#[derive(Clone, Debug)]
pub struct Target {
    pub host: String,
    pub port: u16,
}
impl Target {
    pub fn authority(&self) -> String {
        if self.host.contains(':') {
            format!("[{}]:{}", self.host, self.port)
        } else {
            format!("{}:{}", self.host, self.port)
        }
    }
    pub fn parse(value: &str, default_port: Option<u16>) -> Result<Self> {
        let (host, port) = if value.starts_with('[') {
            let close = value.find(']').ok_or("InvalidTarget")?;
            let host = &value[1..close];
            if host.parse::<Ipv6Addr>().is_err() {
                return Err("InvalidTarget");
            }
            (
                host.to_string(),
                value[close + 1..]
                    .strip_prefix(':')
                    .and_then(|p| p.parse().ok())
                    .or_else(|| {
                        if close + 1 == value.len() {
                            default_port
                        } else {
                            None
                        }
                    })
                    .ok_or("InvalidTarget")?,
            )
        } else if let Some((host, port)) = value.rsplit_once(':') {
            if host.contains(':') {
                return Err("InvalidTarget");
            }
            (host.to_string(), port.parse().map_err(|_| "InvalidTarget")?)
        } else {
            (value.to_string(), default_port.ok_or("InvalidTarget")?)
        };
        if !valid_host(&host) || port == 0 {
            return Err("InvalidTarget");
        }
        Ok(Self { host, port })
    }
    pub fn encode(&self, output: &mut Vec<u8>) -> Result<()> {
        match self.host.parse::<IpAddr>() {
            Ok(IpAddr::V4(ip)) => {
                output.push(1);
                output.extend(ip.octets());
            }
            Ok(IpAddr::V6(ip)) => {
                output.push(4);
                output.extend(ip.octets());
            }
            Err(_) if valid_host(&self.host) && self.host.len() <= 255 => {
                output.extend([3, self.host.len() as u8]);
                output.extend(self.host.as_bytes());
            }
            _ => return Err("InvalidTarget"),
        }
        output.extend(self.port.to_be_bytes());
        Ok(())
    }
}

pub async fn read_target<R: AsyncRead + Unpin>(stream: &mut R, allow_zero: bool) -> Result<Target> {
    let host = match stream.read_u8().await.map_err(|_| "AddressRead")? {
        1 => {
            let mut a = [0; 4];
            stream.read_exact(&mut a).await.map_err(|_| "AddressRead")?;
            Ipv4Addr::from(a).to_string()
        }
        4 => {
            let mut a = [0; 16];
            stream.read_exact(&mut a).await.map_err(|_| "AddressRead")?;
            Ipv6Addr::from(a).to_string()
        }
        3 => {
            let len = stream.read_u8().await.map_err(|_| "AddressRead")? as usize;
            let mut a = vec![0; len];
            stream.read_exact(&mut a).await.map_err(|_| "AddressRead")?;
            String::from_utf8(a).map_err(|_| "InvalidDomain")?
        }
        _ => return Err("AddressType"),
    };
    let port = stream.read_u16().await.map_err(|_| "AddressRead")?;
    if !valid_host(&host) || (!allow_zero && port == 0) {
        return Err("InvalidTarget");
    }
    Ok(Target { host, port })
}

#[derive(Clone, Copy)]
pub enum InboundKind {
    Socks4,
    Socks5,
    HttpConnect,
    HttpForward,
}
pub struct Inbound {
    pub kind: InboundKind,
    pub target: Target,
    pub initial: Vec<u8>,
    pub udp: bool,
}

async fn http_header(stream: &mut TcpStream, mut data: Vec<u8>) -> Result<(Vec<u8>, Vec<u8>)> {
    loop {
        if let Some(end) = data.windows(4).position(|w| w == b"\r\n\r\n") {
            if end + 4 > 16 * 1024 {
                return Err("HeaderTooLarge");
            }
            let tail = data.split_off(end + 4);
            return Ok((data, tail));
        }
        if data.len() >= 16 * 1024 {
            return Err("HeaderTooLarge");
        }
        let mut block = [0u8; 1024];
        let n = stream.read(&mut block).await.map_err(|_| "HeaderRead")?;
        if n == 0 {
            return Err("HeaderClosed");
        }
        data.extend_from_slice(&block[..n]);
    }
}

pub async fn accept(stream: &mut TcpStream, auth: &Option<Credentials>) -> Result<Inbound> {
    let first = stream.read_u8().await.map_err(|_| "InboundClosed")?;
    if first == 4 {
        return socks4::accept(stream, auth).await;
    }
    if first == 5 {
        return accept_socks(stream, auth).await;
    }
    let result = accept_http(stream, auth, first).await;
    if result
        .as_ref()
        .is_err_and(|e| *e != "InboundAuthentication")
    {
        let _ = stream
            .write_all(
                b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n",
            )
            .await;
    }
    result
}
async fn accept_socks(stream: &mut TcpStream, auth: &Option<Credentials>) -> Result<Inbound> {
    let count = stream.read_u8().await.map_err(|_| "SocksGreeting")? as usize;
    if count == 0 {
        return Err("SocksGreeting");
    }
    let mut methods = vec![0; count];
    stream
        .read_exact(&mut methods)
        .await
        .map_err(|_| "SocksGreeting")?;
    let required = if auth.is_some() { 2 } else { 0 };
    if !methods.contains(&required) {
        let _ = stream.write_all(&[5, 255]).await;
        return Err("InboundAuthentication");
    }
    stream
        .write_all(&[5, required])
        .await
        .map_err(|_| "SocksWrite")?;
    if let Some(auth) = auth {
        if stream
            .read_u8()
            .await
            .map_err(|_| "InboundAuthentication")?
            != 1
        {
            return Err("InboundAuthentication");
        }
        let n = stream
            .read_u8()
            .await
            .map_err(|_| "InboundAuthentication")? as usize;
        let mut user = vec![0; n];
        stream
            .read_exact(&mut user)
            .await
            .map_err(|_| "InboundAuthentication")?;
        let n = stream
            .read_u8()
            .await
            .map_err(|_| "InboundAuthentication")? as usize;
        let mut pass = vec![0; n];
        stream
            .read_exact(&mut pass)
            .await
            .map_err(|_| "InboundAuthentication")?;
        let ok = user == auth.username.as_bytes() && pass == auth.password.as_bytes();
        stream
            .write_all(&[1, if ok { 0 } else { 1 }])
            .await
            .map_err(|_| "SocksWrite")?;
        if !ok {
            return Err("InboundAuthentication");
        }
    }
    let mut header = [0; 3];
    stream
        .read_exact(&mut header)
        .await
        .map_err(|_| "SocksRequest")?;
    if header[0] != 5 || header[2] != 0 || ![1, 3].contains(&header[1]) {
        let _ = stream.write_all(&[5, 7, 0, 1, 0, 0, 0, 0, 0, 0]).await;
        return Err("SocksCommand");
    }
    let target = read_target(stream, header[1] == 3).await?;
    Ok(Inbound {
        kind: InboundKind::Socks5,
        target,
        initial: Vec::new(),
        udp: header[1] == 3,
    })
}
async fn accept_http(
    stream: &mut TcpStream,
    auth: &Option<Credentials>,
    first: u8,
) -> Result<Inbound> {
    let (header, tail) = http_header(stream, vec![first]).await?;
    let mut fields = [httparse::EMPTY_HEADER; 64];
    let mut req = httparse::Request::new(&mut fields);
    if !req.parse(&header).map_err(|_| "HttpSyntax")?.is_complete() || req.version != Some(1) {
        return Err("HttpVersion");
    }
    let method = req.method.ok_or("HttpMethod")?;
    let path = req.path.ok_or("HttpTarget")?;
    let mut seen = std::collections::HashSet::new();
    let mut authorization = None;
    let mut content_length = false;
    let mut transfer_encoding = false;
    let mut upgrade = false;
    for h in req.headers.iter() {
        let name = h.name.to_ascii_lowercase();
        if !seen.insert(name.clone())
            && [
                "host",
                "content-length",
                "transfer-encoding",
                "proxy-authorization",
                "connection",
                "upgrade",
            ]
            .contains(&name.as_str())
        {
            return Err("DuplicateHeader");
        }
        if h.value.iter().any(|b| b.is_ascii_control() && *b != b'\t') {
            return Err("HeaderControl");
        }
        match name.as_str() {
            "proxy-authorization" => authorization = Some(h.value),
            "content-length" => {
                content_length = true;
                if h.value.is_empty() || !h.value.iter().all(u8::is_ascii_digit) {
                    return Err("ContentLength");
                }
            }
            "transfer-encoding" => {
                transfer_encoding = true;
                if !h.value.eq_ignore_ascii_case(b"chunked") {
                    return Err("TransferEncoding");
                }
            }
            "upgrade" => {
                if !h.value.eq_ignore_ascii_case(b"websocket") {
                    return Err("UpgradeUnsupported");
                }
                upgrade = true;
            }
            "connection" => {
                let value = std::str::from_utf8(h.value).map_err(|_| "HeaderControl")?;
                if value.split(',').any(|s| {
                    !["close", "keep-alive", "upgrade"]
                        .contains(&s.trim().to_ascii_lowercase().as_str())
                }) {
                    return Err("ConnectionTokens");
                }
            }
            _ => {}
        }
    }
    if content_length && transfer_encoding {
        return Err("AmbiguousFraming");
    }
    if let Some(auth) = auth {
        let expected = format!(
            "Basic {}",
            STANDARD.encode(format!("{}:{}", auth.username, auth.password))
        );
        if authorization != Some(expected.as_bytes()) {
            stream.write_all(b"HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm=\"Swirl\"\r\nConnection: close\r\nContent-Length: 0\r\n\r\n").await.map_err(|_|"HttpWrite")?;
            // Return a distinct marker; caller must not emit a second response.
            return Err("InboundAuthentication");
        }
    }
    if method == "CONNECT" {
        if content_length || transfer_encoding {
            return Err("ConnectBody");
        }
        return Ok(Inbound {
            kind: InboundKind::HttpConnect,
            target: Target::parse(path, None)?,
            initial: tail,
            udp: false,
        });
    }
    let rest = path
        .strip_prefix("http://")
        .ok_or("HttpSchemeUnsupported")?;
    let boundary = rest.find(['/', '?']).unwrap_or(rest.len());
    let target = Target::parse(&rest[..boundary], Some(80))?;
    if rest.contains('#') || !seen.contains("host") {
        return Err("HttpTarget");
    }
    let suffix = &rest[boundary..];
    let origin_path = if suffix.is_empty() {
        "/".to_string()
    } else if suffix.starts_with('?') {
        format!("/{suffix}")
    } else {
        suffix.to_string()
    };
    let mut initial = format!("{method} {origin_path} HTTP/1.1\r\n").into_bytes();
    for h in req.headers.iter() {
        if h.name.eq_ignore_ascii_case("host") {
            let host = std::str::from_utf8(h.value).map_err(|_| "HttpHost")?;
            let declared = Target::parse(host, Some(80))?;
            if !declared.host.eq_ignore_ascii_case(&target.host) || declared.port != target.port {
                return Err("HostMismatch");
            }
        }
        if [
            "proxy-authorization",
            "proxy-connection",
            "connection",
            "keep-alive",
        ]
        .iter()
        .any(|name| h.name.eq_ignore_ascii_case(name))
        {
            continue;
        }
        initial.extend(h.name.as_bytes());
        initial.extend(b": ");
        initial.extend(h.value);
        initial.extend(b"\r\n");
    }
    initial.extend(if upgrade {
        b"Connection: Upgrade\r\n\r\n".as_slice()
    } else {
        b"Connection: close\r\n\r\n".as_slice()
    });
    initial.extend(tail);
    Ok(Inbound {
        kind: InboundKind::HttpForward,
        target,
        initial,
        udp: false,
    })
}
pub async fn reply(stream: &mut TcpStream, kind: InboundKind, ok: bool) -> Result<()> {
    let bytes = match kind {
        InboundKind::Socks4 => vec![0, if ok { 90 } else { 91 }, 0, 0, 0, 0, 0, 0],
        InboundKind::Socks5 => {
            if ok {
                vec![5, 0, 0, 1, 0, 0, 0, 0, 0, 0]
            } else {
                vec![5, 5, 0, 1, 0, 0, 0, 0, 0, 0]
            }
        }
        InboundKind::HttpConnect if ok => b"HTTP/1.1 200 Connection Established\r\n\r\n".to_vec(),
        InboundKind::HttpForward if ok => Vec::new(),
        _ => b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".to_vec(),
    };
    stream.write_all(&bytes).await.map_err(|_| "InboundReply")
}
pub async fn connect(
    outbound: &Outbound,
    target: &Target,
    resolver: &Resolver,
    handshake_limit: std::time::Duration,
) -> Result<swirl_transport::BoxStream> {
    // DNS, all address attempts, TLS and protocol negotiation share this one
    // budget. A successful TCP connection ends address fallback permanently.
    let deadline = Instant::now() + handshake_limit;
    if let Outbound::Vless {
        host,
        port,
        uuid,
        reality: Some(reality),
        tls,
        websocket,
        flow,
        ..
    } = outbound
    {
        // Validate before any socket or DNS operation even for direct callers
        // of this API. There is no ordinary TLS/TCP or DIRECT failure branch.
        reality.validate()?;
        if tls.is_some() || websocket.is_some() {
            return Err("RealityTransportConflict");
        }
        let flow = flow.as_deref().unwrap_or("");
        if !flow.is_empty() && flow != "xtls-rprx-vision" {
            return Err("VlessFlowUnsupported");
        }
        let (key, short_id) = reality.key_material()?;
        let parameters = swirl_transport::reality::ClientParameters::new(
            &reality.server_name,
            key,
            &short_id,
            [0, 1, 0],
        )?
        .with_fingerprint(&reality.fingerprint)?;
        let tcp = connect_tcp(
            resolver,
            &Target {
                host: host.clone(),
                port: *port,
            },
            deadline,
        )
        .await?;
        let unix_time = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .ok()
            .and_then(|value| u32::try_from(value.as_secs()).ok())
            .ok_or("RealityClock")?;
        let alpn: Vec<Vec<u8>> = reality
            .alpn
            .iter()
            .map(|value| value.as_bytes().to_vec())
            .collect();
        let stream = within(deadline, "RealityHandshakeTimeout", async {
            swirl_transport::reality::connect(tcp, &parameters, unix_time, &alpn)
                .await
                .map_err(|_| "RealityAuthenticationOrHandshake")
        })
        .await?;
        if flow == "xtls-rprx-vision" {
            // Keep the concrete authenticated owner until the Vision adapter
            // installs its directional raw handoff. The wire request retains
            // the declared flow; no ordinary VLESS request is sent first.
            let stream = within(
                deadline,
                "UpstreamProtocolTimeout",
                vision::client_over_reality(stream, uuid, target, handshake_limit),
            )
            .await?;
            return Ok(Box::new(stream));
        }
        return within(
            deadline,
            "UpstreamProtocolTimeout",
            handshake(
                outbound,
                target,
                Box::new(stream),
                None,
                *port,
                handshake_limit,
            ),
        )
        .await;
    }
    if matches!(outbound, Outbound::Vless { flow: Some(flow), .. } if !flow.is_empty()) {
        return Err("VlessFlowUnsupported");
    }
    let (host, port, auth, tls) = match outbound {
        Outbound::Direct {} => {
            return Ok(Box::new(connect_tcp(resolver, target, deadline).await?));
        }
        Outbound::Reject {} => return Err("RouteRejected"),
        Outbound::Socks4 {
            host,
            port,
            user_id,
            remote_dns,
        } => {
            return socks4::connect(
                host,
                *port,
                user_id,
                *remote_dns,
                target,
                resolver,
                deadline,
            )
            .await;
        }
        Outbound::Shadowsocks { host, port, .. } => (host, *port, None, None),
        Outbound::Socks5 {
            host,
            port,
            auth,
            tls,
            ..
        }
        | Outbound::HttpConnect {
            host,
            port,
            auth,
            tls,
        } => (host, *port, auth.as_ref(), tls.as_ref()),
        Outbound::Trojan {
            host, port, tls, ..
        } => (host, *port, None, Some(tls)),
        Outbound::Vless {
            host, port, tls, ..
        } => (host, *port, None, tls.as_ref()),
    };
    let tcp = connect_tcp(
        resolver,
        &Target {
            host: host.clone(),
            port,
        },
        deadline,
    )
    .await?;
    let mut stream: swirl_transport::BoxStream = if let Some(tls) = tls {
        within(
            deadline,
            "UpstreamTlsTimeout",
            swirl_transport::secure(tcp, tls),
        )
        .await?
    } else {
        Box::new(tcp)
    };
    let ws = match outbound {
        Outbound::Vless { websocket, .. } | Outbound::Trojan { websocket, .. } => {
            websocket.as_ref()
        }
        _ => None,
    };
    if let Some(ws) = ws {
        stream = within(
            deadline,
            "WebSocketUpgradeTimeout",
            websocket::connect(stream, ws),
        )
        .await?;
    }
    let timeout_code = if matches!(
        outbound,
        Outbound::Shadowsocks {
            obfs_http: Some(_),
            ..
        }
    ) {
        "ShadowsocksObfsWriteTimeout"
    } else {
        "UpstreamProtocolTimeout"
    };
    within(
        deadline,
        timeout_code,
        handshake(outbound, target, stream, auth, port, handshake_limit),
    )
    .await
}

async fn handshake(
    outbound: &Outbound,
    target: &Target,
    mut stream: swirl_transport::BoxStream,
    auth: Option<&Credentials>,
    port: u16,
    handshake_limit: std::time::Duration,
) -> Result<swirl_transport::BoxStream> {
    if let Outbound::Shadowsocks {
        password,
        cipher,
        obfs_http,
        ..
    } = outbound
    {
        let write_error = if obfs_http.is_some() {
            "ShadowsocksObfsWrite"
        } else {
            "ShadowsocksHandshakeWrite"
        };
        let mut encrypted = shadowsocks::Stream::new(
            stream,
            password,
            cipher,
            obfs_http.as_ref().map(|o| o.host.clone()),
            port,
        )
        .map_err(|_| "ShadowsocksSetup")?;
        let mut address = Vec::new();
        target.encode(&mut address)?;
        encrypted
            .write_all(&address)
            .await
            .map_err(|_| write_error)?;
        encrypted.flush().await.map_err(|_| write_error)?;
        return Ok(Box::new(encrypted));
    }
    if let Outbound::Trojan { password, .. } = outbound {
        use sha2::{Digest, Sha224};
        let mut request = format!("{:x}\r\n", Sha224::digest(password.as_bytes())).into_bytes();
        request.push(1);
        target.encode(&mut request)?;
        request.extend(b"\r\n");
        stream
            .write_all(&request)
            .await
            .map_err(|_| "TrojanHandshakeWrite")?;
        stream.flush().await.map_err(|_| "TrojanHandshakeWrite")?;
        return Ok(stream);
    }
    if let Outbound::Vless { uuid, .. } = outbound {
        stream
            .write_all(&vless::request(uuid, target)?)
            .await
            .map_err(|_| "VlessHandshakeWrite")?;
        stream.flush().await.map_err(|_| "VlessHandshakeWrite")?;
        // The server may wait for application data before responding. Decode
        // its prefix lazily, retaining partial reads and never forwarding it.
        return Ok(Box::new(vless::Stream::new(stream, handshake_limit)));
    }
    if matches!(outbound, Outbound::Socks5 { .. }) {
        socks5::authenticate(&mut stream, auth).await?;
        socks5::request(&mut stream, 1, target, true).await?;
    } else {
        let mut request = format!(
            "CONNECT {} HTTP/1.1\r\nHost: {}\r\n",
            target.authority(),
            target.authority()
        );
        if let Some(auth) = auth {
            request += &format!(
                "Proxy-Authorization: Basic {}\r\n",
                STANDARD.encode(format!("{}:{}", auth.username, auth.password))
            );
        }
        request += "\r\n";
        stream
            .write_all(request.as_bytes())
            .await
            .map_err(|_| "HttpUpstreamWrite")?;
        stream.flush().await.map_err(|_| "HttpUpstreamWrite")?;
        // Read exactly through the header: tunnel bytes must stay in the socket.
        let mut header = Vec::new();
        while !header.ends_with(b"\r\n\r\n") {
            if header.len() >= 16384 {
                return Err("UpstreamHeaderTooLarge");
            }
            header.push(stream.read_u8().await.map_err(|_| "HttpUpstreamRead")?);
        }
        let mut fields = [httparse::EMPTY_HEADER; 64];
        let mut response = httparse::Response::new(&mut fields);
        if !response
            .parse(&header)
            .map_err(|_| "HttpUpstreamSyntax")?
            .is_complete()
            || response.code != Some(200)
        {
            return Err("UpstreamRejected");
        }
    }
    Ok(stream)
}

#[cfg(test)]
mod connect_tests {
    use super::*;
    use std::time::Duration;

    fn ss(obfs: bool) -> Outbound {
        Outbound::Shadowsocks {
            host: "fixture.invalid".into(),
            port: 443,
            password: "local-synthetic-only".into(),
            cipher: "aes-128-gcm".into(),
            udp: false,
            obfs_http: obfs.then(|| swirl_subscription::ObfsHttp {
                host: "obfs.invalid".into(),
            }),
        }
    }

    #[tokio::test]
    async fn shadowsocks_initial_write_reports_plain_and_obfs_failures_separately() {
        let target = Target {
            host: "target.invalid".into(),
            port: 443,
        };
        for (obfs, expected) in [
            (false, "ShadowsocksHandshakeWrite"),
            (true, "ShadowsocksObfsWrite"),
        ] {
            let (stream, peer) = tokio::io::duplex(256);
            drop(peer);
            let error = handshake(
                &ss(obfs),
                &target,
                Box::new(stream),
                None,
                443,
                Duration::from_secs(1),
            )
            .await
            .err()
            .unwrap();
            assert_eq!(error, expected);
            assert_eq!(
                failure_stage(error),
                if obfs {
                    "http_obfs"
                } else {
                    "protocol_handshake"
                }
            );
        }
    }

    #[tokio::test]
    async fn shadowsocks_obfs_does_not_wait_for_application_response_during_connect() {
        let (stream, mut peer) = tokio::io::duplex(4096);
        let target = Target {
            host: "target.invalid".into(),
            port: 443,
        };
        let connected = tokio::time::timeout(
            Duration::from_millis(100),
            handshake(
                &ss(true),
                &target,
                Box::new(stream),
                None,
                443,
                Duration::from_secs(1),
            ),
        )
        .await
        .expect("connection establishment must not await a lazy response")
        .unwrap();
        let mut prefix = [0; 4];
        peer.read_exact(&mut prefix).await.unwrap();
        assert_eq!(&prefix, b"GET ");
        drop(connected);
    }
}
