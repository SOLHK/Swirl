//! Bounded loopback-only VLESS/Vision interoperability client. The native
//! product outbound remains disabled. All credentials arrive on stdin and no
//! endpoint, credential or application bytes are echoed in its JSON report.
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    io::{self, Read},
    net::{IpAddr, SocketAddr},
    pin::Pin,
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicUsize, Ordering},
    },
    task::{Context, Poll},
    time::Duration,
};
use swirl_protocol::{
    Target,
    vision::{
        self,
        stream::{ReadMode, Stream},
        tls::Eligibility,
    },
};
use swirl_subscription::Tls;
use swirl_transport::BoxStream;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, ReadBuf};

const MAX_PAYLOAD: usize = 1024 * 1024;
const MAX_INPUT: usize = 2 * MAX_PAYLOAD + 64 * 1024;

fn chunk() -> usize {
    16384
}
fn timeout() -> u64 {
    10000
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    host: String,
    port: u16,
    uuid: String,
    target_host: String,
    target_port: u16,
    outer_server_name: String,
    outer_ca_der_base64: String,
    #[serde(default)]
    inner_tls: bool,
    #[serde(default)]
    server_first: bool,
    #[serde(default)]
    inner_server_name: String,
    #[serde(default)]
    inner_ca_der_base64: String,
    payload_hex: String,
    #[serde(default = "timeout")]
    timeout_ms: u64,
    #[serde(default = "chunk")]
    read_chunk: usize,
    #[serde(default = "chunk")]
    write_chunk: usize,
}

fn invalid() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, "InvalidSyntheticVisionInput")
}

fn loopback(host: &str, port: u16) -> io::Result<SocketAddr> {
    let address: IpAddr = host.parse().map_err(|_| invalid())?;
    if !address.is_loopback() || port == 0 {
        return Err(invalid());
    }
    Ok(SocketAddr::new(address, port))
}

fn payload(input: &str) -> io::Result<Vec<u8>> {
    if !input.len().is_multiple_of(2) || input.len() / 2 > MAX_PAYLOAD {
        return Err(invalid());
    }
    input
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| {
            let digits = std::str::from_utf8(pair).map_err(|_| invalid())?;
            u8::from_str_radix(digits, 16).map_err(|_| invalid())
        })
        .collect()
}

#[derive(Default)]
struct Observation {
    direct_rejected: AtomicBool,
    tls13_candidate: AtomicBool,
    uploaded: AtomicUsize,
    received: AtomicUsize,
}

struct Observed {
    stream: Stream<BoxStream>,
    observation: Arc<Observation>,
}

impl Observed {
    fn observe(&self) {
        if self.stream.read_mode() == ReadMode::DirectRequested {
            self.observation
                .direct_rejected
                .store(true, Ordering::SeqCst);
        }
        if matches!(
            self.stream.inspection().eligibility(),
            Eligibility::Candidate { .. }
        ) {
            self.observation
                .tls13_candidate
                .store(true, Ordering::SeqCst);
        }
    }
}

impl AsyncRead for Observed {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let result = Pin::new(&mut self.stream).poll_read(cx, out);
        self.observe();
        result
    }
}

impl AsyncWrite for Observed {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        let result = Pin::new(&mut self.stream).poll_write(cx, bytes);
        self.observe();
        result
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.stream).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.stream).poll_shutdown(cx)
    }
}

async fn run(input: Input, report: &mut Value, observation: Arc<Observation>) -> io::Result<()> {
    let address = loopback(&input.host, input.port)?;
    loopback(&input.target_host, input.target_port)?;
    let payload = payload(&input.payload_hex)?;
    if !(1..=30000).contains(&input.timeout_ms)
        || !(1..=16384).contains(&input.read_chunk)
        || !(1..=16384).contains(&input.write_chunk)
        || input.outer_ca_der_base64.len() > 32768
        || input.inner_ca_der_base64.len() > 32768
        || (input.server_first && !input.inner_tls)
    {
        return Err(invalid());
    }
    let limit = Duration::from_millis(input.timeout_ms);
    let operation = async {
        report["stage"] = json!("tcp");
        let socket = tokio::net::TcpStream::connect(address).await?;
        report["stage"] = json!("outer_tls");
        let outer = swirl_transport::secure(
            socket,
            &Tls {
                server_name: input.outer_server_name,
                alpn: Vec::new(),
                ca_der_base64: Some(input.outer_ca_der_base64),
            },
        )
        .await
        .map_err(io::Error::other)?;
        report["stage"] = json!("vision_request");
        let vision = vision::client_over_authenticated(
            outer,
            &input.uuid,
            &Target {
                host: input.target_host,
                port: input.target_port,
            },
            limit,
        )
        .await
        .map_err(io::Error::other)?;
        let observed = Observed {
            stream: vision,
            observation: observation.clone(),
        };
        let mut transport: BoxStream = if input.inner_tls {
            report["stage"] = json!("inner_tls");
            swirl_transport::secure(
                observed,
                &Tls {
                    server_name: input.inner_server_name,
                    alpn: Vec::new(),
                    ca_der_base64: Some(input.inner_ca_der_base64),
                },
            )
            .await
            .map_err(io::Error::other)?
        } else {
            Box::new(observed)
        };
        if input.server_first {
            // Negative-test probe: a real TLS 1.3 target proactively emits
            // application data, causing its Xray peer to request direct mode.
            // No application upload starts before we see that actual request.
            report["stage"] = json!("server_first_probe");
            let kind = if transport.read(&mut [0; 1]).await? == 0 {
                io::ErrorKind::UnexpectedEof
            } else {
                io::ErrorKind::InvalidData
            };
            return Err(io::Error::new(kind, "VisionExpectedDirectRejection"));
        }
        report["stage"] = json!("exchange_and_close");
        let (mut reader, mut writer) = tokio::io::split(&mut transport);
        let upload = async {
            for part in payload.chunks(input.write_chunk) {
                writer.write_all(part).await?;
                writer.flush().await?;
                observation.uploaded.fetch_add(part.len(), Ordering::SeqCst);
            }
            writer.shutdown().await
        };
        let download = async {
            let mut buffer = vec![0; input.read_chunk];
            let mut received = 0;
            loop {
                let count = reader.read(&mut buffer).await?;
                if count == 0 {
                    break;
                }
                if count > payload.len() - received
                    || buffer[..count] != payload[received..received + count]
                {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "VisionEchoMismatch",
                    ));
                }
                received += count;
                observation.received.store(received, Ordering::SeqCst);
            }
            if received != payload.len() {
                return Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "VisionEchoTruncated",
                ));
            }
            Ok(())
        };
        tokio::try_join!(upload, download)?;
        report["payload_sha256"] = json!(format!("{:x}", Sha256::digest(&payload)));
        report["stage"] = json!("complete");
        Ok(())
    };
    tokio::time::timeout(limit, operation)
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "VisionPeerDeadline"))?
}

#[tokio::main]
async fn main() {
    let mut report = json!({"ok": false, "stage": "input", "direct_ready": false});
    let observation = Arc::new(Observation::default());
    let mut bytes = Vec::new();
    let input = io::stdin()
        .take((MAX_INPUT + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| invalid())
        .and_then(|_| {
            if bytes.len() > MAX_INPUT {
                return Err(invalid());
            }
            serde_json::from_slice::<Input>(&bytes).map_err(|_| invalid())
        });
    let result = match input {
        Ok(input) => run(input, &mut report, observation.clone()).await,
        Err(error) => Err(error),
    };
    report["uploaded"] = json!(observation.uploaded.load(Ordering::SeqCst));
    report["received"] = json!(observation.received.load(Ordering::SeqCst));
    report["direct_rejected"] = json!(observation.direct_rejected.load(Ordering::SeqCst));
    report["tls13_candidate"] = json!(observation.tls13_candidate.load(Ordering::SeqCst));
    let failed = result.is_err();
    match result {
        Ok(()) => report["ok"] = json!(true),
        Err(error) => {
            report["error_kind"] = json!(format!("{:?}", error.kind()));
            // Only static protocol markers; native OS messages can contain paths.
            report["error"] = json!(if observation.direct_rejected.load(Ordering::SeqCst) {
                "VisionDirectOwnershipUnavailable"
            } else {
                "SyntheticVisionSessionFailed"
            });
        }
    }
    println!("{report}");
    if failed {
        std::process::exit(1);
    }
}
