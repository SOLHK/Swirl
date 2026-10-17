//! Active health requests are separate, explicitly configured traffic. Failure
//! never replays an application request or substitutes a direct connection.
use crate::{Result, Target};
use std::time::Instant;
use swirl_dns::Resolver;
use swirl_subscription::{HealthProbe, Outbound};
use tokio::{io::{AsyncReadExt, AsyncWriteExt}, time::{Duration, timeout}};

pub async fn health_probe(outbound: &Outbound, options: &HealthProbe, resolver: &Resolver) -> Result<u64> {
    let target = options.target()?;
    let started = Instant::now();
    timeout(Duration::from_millis(options.timeout_ms), async {
        let mut stream = crate::connect(outbound, &Target {host: target.host.clone(), port: target.port}, resolver,
            Duration::from_millis(options.timeout_ms)).await?;
        if let Some(tls) = target.tls {stream = swirl_transport::secure(stream, &tls).await?;}
        let request = format!("GET {} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\nUser-Agent: Swirl-Core-Health/1\r\nAccept: */*\r\n\r\n", target.path, target.authority);
        stream.write_all(request.as_bytes()).await.map_err(|_| "PolicyProbeWrite")?;
        stream.flush().await.map_err(|_| "PolicyProbeWrite")?;
        let mut response = Vec::new();
        while !response.ends_with(b"\r\n\r\n") {
            if response.len() >= 8192 {return Err("PolicyProbeHeaderLimit");}
            response.push(stream.read_u8().await.map_err(|_| "PolicyProbeRead")?);
        }
        let mut headers = [httparse::EMPTY_HEADER; 64];
        let mut parsed = httparse::Response::new(&mut headers);
        if !parsed.parse(&response).map_err(|_| "PolicyProbeHttp")?.is_complete()
            || !matches!(parsed.version, Some(0 | 1)) || parsed.code != Some(options.expected_status) {
            return Err("PolicyProbeStatus");
        }
        // Headers prove an actual configured HTTP exchange. No response body is
        // buffered, no redirect followed, and no user cookies/auth are attached.
        Ok(started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64)
    }).await.map_err(|_| "PolicyProbeTimeout")?
}
