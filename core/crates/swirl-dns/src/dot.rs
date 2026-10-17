//! Strict DNS over TLS, RFC 7858 / RFC 8310. Connections go only to explicit
//! IP bootstrap endpoints; authentication always uses the separately set name.
//! Reuse one authenticated stream for A, AAAA and CNAME follow-ups in a lookup.
//! Cross-lookup connection pooling and pipelining are deliberately not claimed.
use crate::wire::{self, Answer, MAX_PACKET, Response};
use std::{collections::HashSet, net::SocketAddr};
use swirl_subscription::DnsTlsServer;
use swirl_transport::{BoxStream, secure};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
    time::{Duration, timeout},
};

type Result<T> = std::result::Result<T, &'static str>;

async fn exchange(stream: &mut BoxStream, host: &str, kind: u16) -> Result<Answer> {
    let request = wire::query(host, kind)?;
    // DNS-over-TLS uses the same two-byte length framing as DNS-over-TCP.
    stream
        .write_all(&(request.len() as u16).to_be_bytes())
        .await
        .map_err(|_| "DnsTlsWrite")?;
    stream
        .write_all(&request)
        .await
        .map_err(|_| "DnsTlsWrite")?;
    stream.flush().await.map_err(|_| "DnsTlsWrite")?;
    let size = stream.read_u16().await.map_err(|_| "DnsTlsRead")? as usize;
    if !(12..=MAX_PACKET).contains(&size) {
        return Err("DnsTlsSize");
    }
    let mut data = vec![0; size];
    stream
        .read_exact(&mut data)
        .await
        .map_err(|_| "DnsTlsRead")?;
    match wire::parse(&data, &request, host, kind)? {
        Response::Answer(answer) => Ok(answer),
        // There is no plaintext retry after an authenticated TLS exchange.
        Response::Truncated => Err("DnsTlsTruncated"),
    }
}

async fn family(stream: &mut BoxStream, host: &str, kind: u16) -> Result<Answer> {
    let mut current = host.to_owned();
    let mut seen = HashSet::new();
    let mut ttl = 300;
    for _ in 0..8 {
        if !seen.insert(current.clone()) {
            return Err("DnsAliasLoop");
        }
        let mut answer = exchange(stream, &current, kind).await?;
        ttl = ttl.min(answer.ttl);
        if let Some(alias) = answer.alias {
            current = alias;
        } else {
            answer.ttl = ttl;
            return Ok(answer);
        }
    }
    Err("DnsAliasDepth")
}

async fn lookup(server: &DnsTlsServer, host: &str, port: u16) -> Result<(Vec<SocketAddr>, u32)> {
    let tcp = TcpStream::connect(server.address)
        .await
        .map_err(|_| "DnsTlsConnect")?;
    let mut stream = secure(tcp, &server.tls).await.map_err(|e| match e {
        "TlsTrustAnchor" => "DnsTlsTrustAnchor",
        "TlsServerName" => "DnsTlsServerName",
        _ => "DnsTlsVerificationOrHandshake",
    })?;
    let a = family(&mut stream, host, 1).await?;
    let aaaa = family(&mut stream, host, 28).await?;
    let ttl = a.ttl.min(aaaa.ttl);
    let addresses: Vec<_> = a
        .addresses
        .into_iter()
        .chain(aaaa.addresses)
        .take(16)
        .map(|ip| SocketAddr::new(ip, port))
        .collect();
    if addresses.is_empty() {
        return Err("DnsEmpty");
    }
    // Best-effort close_notify must not keep a completed lookup alive forever.
    let _ = timeout(Duration::from_millis(100), stream.shutdown()).await;
    Ok((addresses, ttl))
}

pub(super) async fn resolve(
    servers: &[DnsTlsServer],
    host: &str,
    port: u16,
) -> Result<(Vec<SocketAddr>, u32)> {
    let mut error = "DnsNoServers";
    for server in servers {
        // The enclosing Resolver also owns a total three-second lookup budget.
        // Authentication, all queries and close share this endpoint deadline.
        let result = timeout(Duration::from_millis(1400), lookup(server, host, port))
            .await
            .unwrap_or(Err("DnsTlsTimeout"));
        match result {
            Ok(answer) => return Ok(answer),
            Err("DnsNameError") => return Err("DnsNameError"),
            Err(e) => error = e,
        }
    }
    Err(error)
}
