//! Native SIP022 UDP interoperability client; official proxy executable is
//! exclusively the independently launched server. Secrets enter via stdin.
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{io::Read, time::Duration};
use swirl_protocol::{Target, ss2022::UdpAssociation};
use swirl_subscription::Outbound;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    #[serde(default)]
    outbound: Option<Outbound>,
    #[serde(default)]
    source_document: Option<String>,
    target_host: String,
    target_port: u16,
    #[serde(default = "mode")]
    mode: String,
    #[serde(default = "size")]
    size: usize,
    #[serde(default = "rounds")]
    rounds: usize,
    #[serde(default = "timeout")]
    timeout_ms: u64,
    #[serde(default)]
    payload_hex: Option<String>,
}
fn mode() -> String {
    "udp".into()
}
fn size() -> usize {
    1024
}
fn rounds() -> usize {
    1
}
fn timeout() -> u64 {
    5000
}

async fn run(input: Input) -> Result<Value, &'static str> {
    if input.size > 65_000
        || input.rounds == 0
        || input.rounds > 128
        || input.timeout_ms == 0
        || input.timeout_ms > 120_000
    {
        return Err("InputLimit");
    }
    if !["udp", "dns", "udp-replay", "udp-reconnect"].contains(&input.mode.as_str()) {
        return Err("InputMode");
    }
    let imported = input.source_document.is_some();
    let outbound = match (input.outbound, input.source_document) {
        (Some(node), None) => node,
        (None, Some(source)) => {
            let mut result = swirl_subscription::inspect::inspect(source.as_bytes());
            if !result.report.parsed || result.tcp_candidates.len() != 1 {
                return Err("ImportRejected");
            }
            result
                .tcp_candidates
                .remove(0)
                .ok_or("ImportNotExecutable")?
        }
        _ => return Err("InputSource"),
    };
    let Outbound::Shadowsocks {
        host,
        port,
        password,
        cipher,
        udp: true,
        obfs_http: None,
    } = &outbound
    else {
        return Err("InputProtocol");
    };
    swirl_protocol::ss2022::validate(password, cipher)?;
    let resolver = swirl_dns::Resolver::default();
    let target = Target {
        host: input.target_host,
        port: input.target_port,
    };
    let begin = std::time::Instant::now();
    let mut association = UdpAssociation::connect(
        host,
        *port,
        password,
        cipher,
        &resolver,
        Duration::from_millis(input.timeout_ms),
    )
    .await?;
    let setup_us = begin.elapsed().as_micros();
    let custom = input
        .payload_hex
        .map(|encoded| {
            if encoded.len() % 2 != 0 || encoded.len() > 130_000 {
                return Err("InputPayload");
            }
            (0..encoded.len())
                .step_by(2)
                .map(|at| {
                    encoded
                        .get(at..at + 2)
                        .ok_or("InputPayload")
                        .and_then(|pair| u8::from_str_radix(pair, 16).map_err(|_| "InputPayload"))
                })
                .collect::<Result<Vec<_>, _>>()
        })
        .transpose()?;
    let mut uploaded = 0;
    let mut downloaded = 0;
    let mut digest = Sha256::new();
    for round in 0..input.rounds {
        let payload = custom.clone().unwrap_or_else(|| {
            (0..input.size)
                .map(|at| ((at * 31 + 17 + round * 7) % 251) as u8)
                .collect()
        });
        association.send(&target, &payload).await?;
        let (returned_target, returned) = association.recv().await?;
        if returned_target.port != target.port {
            return Err("UdpSourceMismatch");
        }
        if input.mode == "dns" {
            if returned.len() < 12
                || payload.len() < 12
                || returned[..2] != payload[..2]
                || returned[2] & 0x80 == 0
            {
                return Err("DnsResponse");
            }
        } else if returned != payload {
            return Err("UdpPayloadMismatch");
        }
        uploaded += payload.len();
        downloaded += returned.len();
        digest.update(&returned);
        if input.mode == "udp-reconnect" && round + 1 < input.rounds {
            tokio::time::sleep(Duration::from_millis(1500)).await;
        }
    }
    let replay_rejected = if input.mode == "udp-replay" {
        if tokio::time::timeout(Duration::from_millis(300), association.recv())
            .await
            .is_ok()
        {
            return Err("UnexpectedDuplicateResponse");
        }
        true
    } else {
        false
    };
    drop(association);
    Ok(
        json!({"ok":true,"mode":input.mode,"imported":imported,"rounds":input.rounds,
        "uploaded":uploaded,"downloaded":downloaded,"sha256":format!("{:x}",digest.finalize()),
        "setup_including_dns_udp_socket_us":setup_us,"total_us":begin.elapsed().as_micros(),
        "duplicate_responses_rejected":replay_rejected,"local_socket_released":true}),
    )
}

fn main() {
    let mut source = String::new();
    let parsed = std::io::stdin()
        .take(1_048_577)
        .read_to_string(&mut source)
        .ok()
        .filter(|_| source.len() <= 1_048_576)
        .and_then(|_| serde_json::from_str::<Input>(&source).ok());
    let report = if let Some(input) = parsed {
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let timeout = Duration::from_millis(input.timeout_ms);
        runtime.block_on(async {
            match tokio::time::timeout(timeout, run(input)).await {
                Ok(Ok(report)) => report,
                Ok(Err(code)) => json!({"ok":false,"error":code}),
                Err(_) => json!({"ok":false,"error":"OperationTimeout"}),
            }
        })
    } else {
        json!({"ok":false,"error":"InputSyntax"})
    };
    println!("{report}");
    if report["ok"] != true {
        std::process::exit(1);
    }
}
