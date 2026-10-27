//! Independent TUIC reference-server client. JSON input is private stdin;
//! output contains fixed diagnostics, byte counts, hashes and stage timings.
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{io::Read, time::Duration};
use swirl_protocol::{Target, tuic::UdpAssociation};
use swirl_subscription::Outbound;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    #[serde(default)]
    outbound: Option<Outbound>,
    #[serde(default)]
    source_document: Option<String>,
    target_host: String,
    target_port: u16,
    #[serde(default = "tcp")]
    mode: String,
    #[serde(default = "size")]
    size: usize,
    #[serde(default = "timeout")]
    timeout_ms: u64,
    #[serde(default)]
    payload_hex: Option<String>,
}
fn tcp() -> String {
    "tcp".into()
}
fn size() -> usize {
    1024 * 1024
}
fn timeout() -> u64 {
    10_000
}
fn pattern(at: usize) -> u8 {
    ((at * 31 + 17) % 251) as u8
}

async fn run(input: Input) -> Result<Value, &'static str> {
    if input.size > 16 * 1024 * 1024 || input.timeout_ms == 0 || input.timeout_ms > 120_000 {
        return Err("InputLimit");
    }
    let imported = input.source_document.is_some();
    let outbound = match (input.outbound, input.source_document) {
        (Some(outbound), None) => outbound,
        (None, Some(source)) => {
            let mut inspection = swirl_subscription::inspect::inspect(source.as_bytes());
            if !inspection.report.parsed || inspection.tcp_candidates.len() != 1 {
                return Err("ImportRejected");
            }
            inspection
                .tcp_candidates
                .remove(0)
                .ok_or("ImportNotExecutable")?
        }
        _ => return Err("InputSource"),
    };
    let Outbound::Tuic(config) = &outbound else {
        return Err("InputProtocol");
    };
    config.validate()?;
    let resolver = swirl_dns::Resolver::default();
    let target = Target {
        host: input.target_host,
        port: input.target_port,
    };
    let began = std::time::Instant::now();
    let limit = Duration::from_millis(input.timeout_ms);
    if input.mode == "udp" || input.mode == "dns" {
        let mut association = UdpAssociation::connect(config, &resolver, limit).await?;
        let connected_us = began.elapsed().as_micros();
        let payload = if let Some(encoded) = input.payload_hex {
            if encoded.len() % 2 != 0
                || encoded.len() > 2 * 65_507
                || !encoded.bytes().all(|byte| byte.is_ascii_hexdigit())
            {
                return Err("InputPayload");
            }
            (0..encoded.len())
                .step_by(2)
                .map(|at| u8::from_str_radix(&encoded[at..at + 2], 16).map_err(|_| "InputPayload"))
                .collect::<Result<Vec<_>, _>>()?
        } else {
            if input.size > 65_507 {
                return Err("InputPayload");
            }
            (0..input.size).map(pattern).collect()
        };
        association.send(&target, &payload).await?;
        let (returned_target, returned) = association.recv().await?;
        if input.mode == "udp" && returned != payload {
            return Err("UdpPayloadMismatch");
        }
        if input.mode == "dns"
            && (returned.len() < 12
                || payload.len() < 12
                || returned[..2] != payload[..2]
                || returned[2] & 128 == 0)
        {
            return Err("DnsResponse");
        }
        association.close().await?;
        return Ok(
            json!({"ok":true,"mode":input.mode,"imported":imported,"uploaded":payload.len(),"downloaded":returned.len(),"sha256":format!("{:x}",Sha256::digest(&returned)),"source_port":returned_target.port,"connect_including_dns_quic_auth_us":connected_us,"total_us":began.elapsed().as_micros(),"close":"clean"}),
        );
    }
    if input.mode != "tcp" {
        return Err("InputMode");
    }
    let mut stream = swirl_protocol::connect(&outbound, &target, &resolver, limit).await?;
    let connected_us = began.elapsed().as_micros();
    stream
        .write_all(&(input.size as u64).to_be_bytes())
        .await
        .map_err(|_| "TcpLengthWrite")?;
    let (mut reader, mut writer) = tokio::io::split(stream);
    let upload = async {
        let mut at = 0;
        let mut data = [0u8; 16_384];
        while at < input.size {
            let size = data.len().min(input.size - at);
            for (i, byte) in data[..size].iter_mut().enumerate() {
                *byte = pattern(at + i);
            }
            writer
                .write_all(&data[..size])
                .await
                .map_err(|_| "TcpWrite")?;
            at += size;
        }
        writer.shutdown().await.map_err(|_| "TcpShutdown")?;
        Ok::<(), &'static str>(())
    };
    let download = async {
        let mut at = 0;
        let mut data = [0u8; 16_384];
        let mut digest = Sha256::new();
        while at < input.size {
            let size = data.len().min(input.size - at);
            let n = reader
                .read(&mut data[..size])
                .await
                .map_err(|_| "TcpRead")?;
            if n == 0 {
                return Err("TcpEarlyEof");
            }
            if data[..n]
                .iter()
                .enumerate()
                .any(|(i, v)| *v != pattern(at + i))
            {
                return Err("TcpPayloadMismatch");
            }
            digest.update(&data[..n]);
            at += n;
        }
        let mut tail = [0];
        if reader.read(&mut tail).await.map_err(|_| "TcpClose")? != 0 {
            return Err("TcpTrailingData");
        }
        Ok::<_, &'static str>(format!("{:x}", digest.finalize()))
    };
    let (_, sha256) = tokio::try_join!(upload, download)?;
    Ok(
        json!({"ok":true,"mode":"tcp","imported":imported,"uploaded":input.size,"downloaded":input.size,"sha256":sha256,"connect_including_dns_quic_auth_us":connected_us,"total_us":began.elapsed().as_micros(),"close":"clean"}),
    )
}

#[tokio::main]
async fn main() {
    let mut bytes = Vec::new();
    let input = std::io::stdin()
        .take(1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "InputRead")
        .and_then(|_| {
            if bytes.len() > 1024 * 1024 {
                Err("InputLimit")
            } else {
                serde_json::from_slice::<Input>(&bytes).map_err(|_| "InputJson")
            }
        });
    let result = match input {
        Ok(input) => tokio::time::timeout(
            Duration::from_millis(input.timeout_ms.saturating_add(3000)),
            run(input),
        )
        .await
        .unwrap_or(Err("TotalTimeout")),
        Err(error) => Err(error),
    };
    match result {
        Ok(report) => println!("{report}"),
        Err(error) => {
            println!("{}", json!({"ok":false,"error":error}));
            std::process::exit(1);
        }
    }
}
