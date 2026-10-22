//! Native transport interoperability client. Settings arrive on stdin; stdout
//! contains only byte counts, hashes, fixed error codes and timings. Xray is an
//! independent server fixture, never a client runtime dependency.
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{io::Read, time::Duration};
use swirl_protocol::{Target, Transport};
use swirl_subscription::{Outbound, Tls};
use swirl_transport::BoxStream;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    outbound: Outbound,
    #[serde(default)]
    transport: Option<Transport>,
    target_host: String,
    target_port: u16,
    #[serde(default)]
    target_tls: Option<Tls>,
    #[serde(default = "http")]
    mode: String,
    #[serde(default = "path")]
    path: String,
    #[serde(default = "size")]
    size: usize,
    #[serde(default = "timeout")]
    timeout_ms: u64,
}
fn http() -> String {
    "http".into()
}
fn path() -> String {
    "/transport".into()
}
fn size() -> usize {
    1024 * 1024
}
fn timeout() -> u64 {
    15000
}
fn pattern(at: usize) -> u8 {
    ((at * 31 + 17) % 251) as u8
}

async fn close(stream: &mut BoxStream) -> &'static str {
    match tokio::time::timeout(Duration::from_secs(2), async {
        stream.shutdown().await?;
        let mut tail = [0];
        match stream.read(&mut tail).await? {
            0 => Ok::<(), std::io::Error>(()),
            _ => Err(std::io::ErrorKind::InvalidData.into()),
        }
    })
    .await
    {
        Ok(Ok(())) => "clean",
        Ok(Err(error)) if error.kind() == std::io::ErrorKind::UnexpectedEof => "unexpected_eof",
        Ok(Err(_)) => "transport_error",
        Err(_) => "timeout",
    }
}

async fn run(input: Input) -> Result<Value, &'static str> {
    if input.size > 64 * 1024 * 1024 || input.timeout_ms == 0 || input.timeout_ms > 120000 {
        return Err("InputLimit");
    }
    let target = Target {
        host: input.target_host,
        port: input.target_port,
    };
    let resolver = swirl_dns::Resolver::default();
    let started = std::time::Instant::now();
    let limit = Duration::from_millis(input.timeout_ms.min(15000));
    let mut stream = match input.transport.as_ref() {
        Some(transport) => {
            swirl_protocol::connect_with_transport(
                &input.outbound,
                &target,
                &resolver,
                limit,
                transport,
            )
            .await?
        }
        None => swirl_protocol::connect(&input.outbound, &target, &resolver, limit).await?,
    };
    let connect_us = started.elapsed().as_micros();
    if let Some(tls) = input.target_tls.as_ref() {
        stream = swirl_transport::secure(stream, tls).await?;
    }
    let transfer = std::time::Instant::now();
    let (uploaded, downloaded, sha256) = if input.mode == "echo" || input.mode == "cancel" {
        stream
            .write_all(&(input.size as u64).to_be_bytes())
            .await
            .map_err(|_| "EchoLengthWrite")?;
        let (mut reader, mut writer) = tokio::io::split(stream);
        let upload = async {
            let mut sent = 0;
            let mut chunk = [0; 16384];
            while sent < input.size {
                let n = (input.size - sent).min(chunk.len());
                for (i, byte) in chunk[..n].iter_mut().enumerate() {
                    *byte = pattern(sent + i);
                }
                writer
                    .write_all(&chunk[..n])
                    .await
                    .map_err(|_| "EchoWrite")?;
                sent += n;
            }
            writer.flush().await.map_err(|_| "EchoFlush")?;
            Ok::<_, &'static str>(sent)
        };
        let download = async {
            let mut received = 0;
            let mut chunk = [0; 16384];
            let mut digest = Sha256::new();
            while received < input.size {
                let n = (input.size - received).min(chunk.len());
                reader
                    .read_exact(&mut chunk[..n])
                    .await
                    .map_err(|_| "EchoRead")?;
                if chunk[..n]
                    .iter()
                    .enumerate()
                    .any(|(i, byte)| *byte != pattern(received + i))
                {
                    return Err("EchoContentMismatch");
                }
                digest.update(&chunk[..n]);
                received += n;
            }
            Ok::<_, &'static str>((received, format!("{:x}", digest.finalize())))
        };
        let (sent, (received, digest)) = tokio::try_join!(upload, download)?;
        stream = reader.unsplit(writer);
        (sent + 8, received, digest)
    } else if input.mode == "http" {
        if !input.path.starts_with('/') || input.path.bytes().any(|b| !(33..=126).contains(&b)) {
            return Err("HttpPath");
        }
        let request = format!(
            "GET {} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\n\r\n",
            input.path,
            target.authority()
        );
        stream
            .write_all(request.as_bytes())
            .await
            .map_err(|_| "HttpWrite")?;
        stream.flush().await.map_err(|_| "HttpFlush")?;
        let mut header = Vec::new();
        while !header.ends_with(b"\r\n\r\n") {
            if header.len() >= 16384 {
                return Err("HttpHeaderLimit");
            }
            header.push(stream.read_u8().await.map_err(|_| "HttpRead")?);
        }
        let mut fields = [httparse::EMPTY_HEADER; 64];
        let mut response = httparse::Response::new(&mut fields);
        response.parse(&header).map_err(|_| "HttpResponse")?;
        if response.code != Some(200) {
            return Err("HttpStatus");
        }
        let length = response
            .headers
            .iter()
            .find(|h| h.name.eq_ignore_ascii_case("content-length"))
            .and_then(|h| std::str::from_utf8(h.value).ok())
            .and_then(|n| n.parse::<usize>().ok())
            .ok_or("HttpLength")?;
        if length > 64 * 1024 * 1024 {
            return Err("HttpBodyLimit");
        }
        let mut digest = Sha256::new();
        let mut received = 0;
        let mut chunk = [0; 16384];
        while received < length {
            let n = (length - received).min(chunk.len());
            stream
                .read_exact(&mut chunk[..n])
                .await
                .map_err(|_| "HttpBodyRead")?;
            digest.update(&chunk[..n]);
            received += n;
        }
        (request.len(), received, format!("{:x}", digest.finalize()))
    } else {
        return Err("ModeUnsupported");
    };
    let transfer_us = transfer.elapsed().as_micros();
    let closure = if input.mode == "cancel" {
        drop(stream);
        "cancelled"
    } else {
        close(&mut stream).await
    };
    Ok(
        json!({"ok":true,"uploaded":uploaded,"downloaded":downloaded,"sha256":sha256,
        "connect_us":connect_us,"transfer_us":transfer_us,"close":closure}),
    )
}

fn main() {
    let mut input = Vec::new();
    let result = std::io::stdin().take(65537).read_to_end(&mut input);
    let input = if result.is_ok() && input.len() <= 65536 {
        serde_json::from_slice::<Input>(&input).ok()
    } else {
        None
    };
    let report = if let Some(input) = input {
        let limit = Duration::from_millis(input.timeout_ms.min(120000));
        let runtime = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .max_blocking_threads(2)
            .enable_all()
            .build()
            .expect("test runtime");
        match runtime.block_on(async { tokio::time::timeout(limit, run(input)).await }) {
            Ok(Ok(report)) => report,
            Ok(Err(error)) => json!({"ok":false,"error":error}),
            Err(_) => json!({"ok":false,"error":"OperationTimeout"}),
        }
    } else {
        json!({"ok":false,"error":"InputSyntax"})
    };
    println!("{report}");
    if report["ok"] != true {
        std::process::exit(1);
    }
}
