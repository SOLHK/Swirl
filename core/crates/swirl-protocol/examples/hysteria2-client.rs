//! Pinned official-server acceptance driver. Configuration is stdin-only;
//! stdout contains fixed error codes, byte counts and hashes, never credentials.
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{io::Read, time::Duration};
use swirl_protocol::{Target, hysteria2::UdpAssociation};
use swirl_subscription::{Hysteria2, Outbound, Tls};
use tokio::io::{AsyncReadExt, AsyncWriteExt};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    #[serde(default)]
    config: Option<Hysteria2>,
    #[serde(default)]
    source: Option<String>,
    target_host: String,
    target_port: u16,
    #[serde(default)]
    target_tls: Option<Tls>,
    mode: String,
    #[serde(default = "size")]
    size: usize,
    #[serde(default = "timeout")]
    timeout_ms: u64,
}
fn size() -> usize {
    4096
}
fn timeout() -> u64 {
    15000
}
fn pattern(position: usize) -> u8 {
    ((position * 37 + 11) % 251) as u8
}

async fn run(input: Input) -> Result<Value, &'static str> {
    if input.size == 0
        || input.size > 16 * 1024 * 1024
        || input.timeout_ms == 0
        || input.timeout_ms > 120000
    {
        return Err("InputLimit");
    }
    let imported = input.source.is_some();
    let config = match (input.config, input.source) {
        (Some(config), None) => config,
        (None, Some(source)) => {
            let inspection = swirl_subscription::inspect::inspect(source.as_bytes());
            match inspection.tcp_candidates.into_iter().next().flatten() {
                Some(Outbound::Hysteria2(config)) => config,
                _ => return Err("Hysteria2ImportRejected"),
            }
        }
        _ => return Err("InputConfiguration"),
    };
    config.validate()?;
    let target = Target {
        host: input.target_host,
        port: input.target_port,
    };
    let resolver = swirl_dns::Resolver::default();
    let started = std::time::Instant::now();
    let limit = Duration::from_millis(input.timeout_ms);
    if input.mode == "udp" || input.mode == "dns" {
        let mut association = UdpAssociation::connect(&config, &resolver, limit).await?;
        let connection_us = started.elapsed().as_micros();
        let payload = if input.mode == "dns" {
            b"\x23\x17\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x04test\x00\x00\x01\x00\x01".to_vec()
        } else {
            (0..input.size).map(pattern).collect()
        };
        association.send(&target, &payload).await?;
        let (_, response) = association.recv().await?;
        if input.mode == "dns" {
            if response.len() < 12
                || response[..2] != payload[..2]
                || response[2] & 0x80 == 0
                || response[3] & 0xf != 0
                || response[7] == 0
            {
                return Err("DnsResponseMismatch");
            }
        } else if response != payload {
            return Err("UdpContentMismatch");
        }
        return Ok(
            json!({"ok":true,"mode":input.mode,"imported":imported,"uploaded":payload.len(),"downloaded":response.len(),"sha256":format!("{:x}",Sha256::digest(&response)),"dns_quic_auth_us":connection_us}),
        );
    }
    let mut stream =
        swirl_protocol::connect(&Outbound::Hysteria2(config), &target, &resolver, limit).await?;
    let connection_us = started.elapsed().as_micros();
    if let Some(tls) = input.target_tls {
        stream = swirl_transport::secure(stream, &tls).await?;
    }
    if input.mode == "http" {
        let request =
            b"GET /hysteria2-native HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n";
        stream.write_all(request).await.map_err(|_| "HttpWrite")?;
        stream.flush().await.map_err(|_| "HttpFlush")?;
        let mut response = Vec::new();
        (&mut stream)
            .take(1024 * 1024)
            .read_to_end(&mut response)
            .await
            .map_err(|_| "HttpRead")?;
        if !response.starts_with(b"HTTP/1.1 200 ") || !response.ends_with(b"swirl-hysteria2-native")
        {
            return Err("HttpResponseMismatch");
        }
        stream.shutdown().await.map_err(|error| {
            let detail = match error.to_string().as_str() {
                "QuicShutdownPeerStopped" => "QuicShutdownPeerStopped",
                "QuicShutdownPeerStoppedNoError" => "QuicShutdownPeerStoppedNoError",
                "QuicShutdownConnectionLost" => "QuicShutdownConnectionLost",
                "QuicShutdownAckTimeout" => "QuicShutdownAckTimeout",
                _ => "Other",
            };
            eprintln!("HY2_HTTP_SHUTDOWN:{detail}");
            "HttpShutdown"
        })?;
        return Ok(
            json!({"ok":true,"mode":"http","imported":imported,"uploaded":request.len(),"downloaded":response.len(),"sha256":format!("{:x}",Sha256::digest(&response)),"dns_quic_auth_tcp_us":connection_us}),
        );
    }
    if !matches!(input.mode.as_str(), "tcp" | "half-close") {
        return Err("InputMode");
    }
    let (mut reader, mut writer) = tokio::io::split(stream);
    let write = async {
        let mut uploaded = 0;
        let mut buffer = [0; 16384];
        while uploaded < input.size {
            let length = buffer.len().min(input.size - uploaded);
            for (offset, byte) in buffer[..length].iter_mut().enumerate() {
                *byte = pattern(uploaded + offset);
            }
            writer
                .write_all(&buffer[..length])
                .await
                .map_err(|_| "TcpWrite")?;
            uploaded += length;
        }
        writer.flush().await.map_err(|_| "TcpFlush")?;
        if input.mode == "half-close" {
            writer.shutdown().await.map_err(|_| "TcpShutdown")?;
        }
        Ok::<_, &'static str>(uploaded)
    };
    let read = async {
        let mut downloaded = 0;
        let mut digest = Sha256::new();
        let mut buffer = [0; 16384];
        while downloaded < input.size {
            let capacity = buffer.len().min(input.size - downloaded);
            let length = reader
                .read(&mut buffer[..capacity])
                .await
                .map_err(|_| "TcpRead")?;
            if length == 0 {
                break;
            }
            if downloaded + length > input.size
                || buffer[..length]
                    .iter()
                    .enumerate()
                    .any(|(offset, byte)| *byte != pattern(downloaded + offset))
            {
                return Err("TcpContentMismatch");
            }
            digest.update(&buffer[..length]);
            downloaded += length;
        }
        if downloaded != input.size {
            return Err("TcpTruncated");
        }
        Ok::<_, &'static str>((downloaded, format!("{:x}", digest.finalize())))
    };
    let (uploaded, (downloaded, sha256)) = tokio::try_join!(write, read)?;
    let mut stream = reader.unsplit(writer);
    stream.shutdown().await.map_err(|_| "TcpShutdown")?;
    let mut tail = [0];
    if stream.read(&mut tail).await.map_err(|_| "TcpCloseRead")? != 0 {
        return Err("TcpUnexpectedTail");
    }
    Ok(
        json!({"ok":true,"mode":"tcp","imported":imported,"uploaded":uploaded,"downloaded":downloaded,"sha256":sha256,"close":"clean","dns_quic_auth_tcp_us":connection_us,"total_us":started.elapsed().as_micros()}),
    )
}

#[tokio::main]
async fn main() {
    let mut bytes = Vec::new();
    let input = std::io::stdin()
        .take(65537)
        .read_to_end(&mut bytes)
        .ok()
        .filter(|_| bytes.len() <= 65536)
        .and_then(|_| serde_json::from_slice::<Input>(&bytes).ok());
    let result = match input {
        Some(input) => {
            let limit = Duration::from_millis(input.timeout_ms.min(120000));
            match tokio::time::timeout(limit, run(input)).await {
                Ok(value) => value,
                Err(_) => Err("Hysteria2AcceptanceTimeout"),
            }
        }
        None => Err("InputSyntax"),
    };
    match result {
        Ok(value) => println!("{value}"),
        Err(code) => {
            println!("{}", json!({"ok":false,"code":code}));
            std::process::exit(1);
        }
    }
}
