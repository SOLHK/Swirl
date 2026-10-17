//! Strict encrypted DNS. Explicit IP bootstrap and separate authentication name
//! prevent implicit OS bootstrap and plaintext fallback. DoT reuses one stream;
//! explicit DoH uses bounded HTTP/1.1 POST exchanges, without a connection pool.
#[path = "doh.rs"]
mod doh;
use crate::wire::{self, Answer, MAX_PACKET, Resolution, Response};
use std::collections::HashSet;
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

async fn lookup(server: &DnsTlsServer, host: &str) -> Result<Resolution> {
    if server.https_path.is_some() {
        return doh::lookup(server, host).await;
    }
    let tcp = TcpStream::connect(server.address)
        .await
        .map_err(|_| "DnsTlsConnect")?;
    let mut stream = secure(tcp, &server.tls).await.map_err(|e| match e {
        "TlsTrustAnchor" => "DnsTlsTrustAnchor",
        "TlsServerName" => "DnsTlsServerName",
        _ => "DnsTlsVerificationOrHandshake",
    })?;
    let a = family(&mut stream, host, 1).await?;
    let aaaa = family(&mut stream, host, 28).await;
    let result = wire::combine(Ok(a), aaaa);
    let _ = timeout(Duration::from_millis(100), stream.shutdown()).await;
    result
}

pub(super) async fn resolve(servers: &[DnsTlsServer], host: &str) -> Result<Resolution> {
    let mut error = "DnsNoServers";
    for server in servers {
        // Resolver also owns a total three-second execution budget. All TLS and
        // A/AAAA/CNAME HTTP exchanges share this endpoint deadline.
        let result = timeout(Duration::from_millis(1400), lookup(server, host))
            .await
            .unwrap_or(Err("DnsTlsTimeout"));
        match result {
            Ok(answer) => return Ok(answer),
            Err(e) => error = e,
        }
    }
    Err(error)
}
