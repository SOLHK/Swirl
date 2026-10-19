//! Synthetic loopback interoperability harness, not an enabled proxy outbound.
//! One bounded JSON request on stdin; one redacted result on stdout. This binary
//! deliberately accepts only loopback IPs and never fetches subscriptions.
use serde_json::{Value, json};
use std::{
    io::{self, Read, Write},
    net::{IpAddr, SocketAddr, TcpStream},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use swirl_transport::reality::{ClientParameters, TlsClient};

const MAX_PAYLOAD: usize = 1024 * 1024;
const MAX_REQUEST: usize = 2 * MAX_PAYLOAD + 16 * 1024;

fn invalid(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, reason)
}

fn text<'a>(input: &'a Value, key: &str) -> io::Result<&'a str> {
    input
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| invalid("InvalidSyntheticPeerInput"))
}

fn hex(input: &str, limit: usize) -> io::Result<Vec<u8>> {
    if !input.len().is_multiple_of(2) || input.len() / 2 > limit {
        return Err(invalid("InvalidSyntheticPeerHex"));
    }
    input
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| {
            let digits =
                std::str::from_utf8(pair).map_err(|_| invalid("InvalidSyntheticPeerHex"))?;
            u8::from_str_radix(digits, 16).map_err(|_| invalid("InvalidSyntheticPeerHex"))
        })
        .collect()
}

fn chunk(input: &Value, key: &str) -> io::Result<usize> {
    match input.get(key) {
        None => Ok(16 * 1024),
        Some(value) => value
            .as_u64()
            .filter(|n| (1..=16384).contains(n))
            .map(|n| n as usize)
            .ok_or_else(|| invalid("InvalidSyntheticPeerChunk")),
    }
}

struct Wire {
    socket: TcpStream,
    deadline: Instant,
    calls: usize,
    read_chunk: usize,
    write_chunk: usize,
    read_bytes: usize,
    written_bytes: usize,
}

impl Wire {
    fn tick(&mut self) -> io::Result<Duration> {
        self.calls += 1;
        if self.calls > 262_144
            || self.read_bytes > 2 * MAX_PAYLOAD
            || self.written_bytes > 2 * MAX_PAYLOAD
        {
            return Err(invalid("SyntheticPeerIoBudget"));
        }
        self.deadline
            .checked_duration_since(Instant::now())
            .map(|left| left.min(Duration::from_secs(3)))
            .filter(|left| !left.is_zero())
            .ok_or_else(|| io::ErrorKind::TimedOut.into())
    }
}

impl Read for Wire {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        let timeout = self.tick()?;
        self.socket.set_read_timeout(Some(timeout))?;
        let end = bytes.len().min(self.read_chunk);
        let read = self.socket.read(&mut bytes[..end])?;
        self.read_bytes += read;
        Ok(read)
    }
}

impl Write for Wire {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let timeout = self.tick()?;
        self.socket.set_write_timeout(Some(timeout))?;
        let written = self
            .socket
            .write(&bytes[..bytes.len().min(self.write_chunk)])?;
        self.written_bytes += written;
        Ok(written)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.socket.flush()
    }
}

fn flush(client: &mut TlsClient, wire: &mut Wire) -> io::Result<()> {
    while client.wants_write() {
        if client.write_tls(wire)? == 0 {
            return Err(io::ErrorKind::WriteZero.into());
        }
    }
    wire.flush()
}

fn run(input: Value, report: &mut Value) -> io::Result<()> {
    let object = input
        .as_object()
        .ok_or_else(|| invalid("InvalidSyntheticPeerInput"))?;
    const KEYS: &[&str] = &[
        "host",
        "port",
        "server_name",
        "public_key_hex",
        "short_id_hex",
        "version",
        "alpn",
        "payload_hex",
        "read_chunk",
        "write_chunk",
    ];
    if object.keys().any(|key| !KEYS.contains(&key.as_str())) {
        return Err(invalid("UnknownSyntheticPeerInput"));
    }
    let host: IpAddr = text(&input, "host")?
        .parse()
        .map_err(|_| invalid("SyntheticPeerRequiresLoopback"))?;
    if !host.is_loopback() {
        return Err(invalid("SyntheticPeerRequiresLoopback"));
    }
    let port = input
        .get("port")
        .and_then(Value::as_u64)
        .filter(|n| (1..=65535).contains(n))
        .ok_or_else(|| invalid("InvalidSyntheticPeerPort"))? as u16;
    let public_key = hex(text(&input, "public_key_hex")?, 32)?
        .try_into()
        .map_err(|_| invalid("InvalidSyntheticPeerPublicKey"))?;
    let short_id = hex(text(&input, "short_id_hex")?, 8)?;
    let version: [u8; 3] = input
        .get("version")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid("InvalidSyntheticPeerVersion"))?
        .iter()
        .map(|n| {
            n.as_u64()
                .and_then(|n| u8::try_from(n).ok())
                .ok_or_else(|| invalid("InvalidSyntheticPeerVersion"))
        })
        .collect::<io::Result<Vec<_>>>()?
        .try_into()
        .map_err(|_| invalid("InvalidSyntheticPeerVersion"))?;
    let alpn = match input.get("alpn") {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::String(value)) => vec![value.as_bytes().to_vec()],
        Some(Value::Array(values)) => values
            .iter()
            .map(|v| {
                v.as_str()
                    .map(|s| s.as_bytes().to_vec())
                    .ok_or_else(|| invalid("InvalidSyntheticPeerAlpn"))
            })
            .collect::<io::Result<Vec<_>>>()?,
        _ => return Err(invalid("InvalidSyntheticPeerAlpn")),
    };
    let payload = match input.get("payload_hex") {
        None => Vec::new(),
        Some(Value::String(value)) => hex(value, MAX_PAYLOAD)?,
        _ => return Err(invalid("InvalidSyntheticPeerPayload")),
    };
    let read_chunk = chunk(&input, "read_chunk")?;
    let write_chunk = chunk(&input, "write_chunk")?;
    let parameters =
        ClientParameters::new(text(&input, "server_name")?, public_key, &short_id, version)
            .map_err(invalid)?;
    let unix_time = u32::try_from(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| invalid("SyntheticPeerClock"))?
            .as_secs(),
    )
    .map_err(|_| invalid("SyntheticPeerClock"))?;
    let mut client = TlsClient::new(&parameters, unix_time, &alpn).map_err(invalid)?;
    report["stage"] = "connect".into();
    let socket = TcpStream::connect_timeout(&SocketAddr::new(host, port), Duration::from_secs(3))?;
    socket.set_nodelay(true)?;
    let mut wire = Wire {
        socket,
        deadline: Instant::now() + Duration::from_secs(15),
        calls: 0,
        read_chunk,
        write_chunk,
        read_bytes: 0,
        written_bytes: 0,
    };
    report["stage"] = "handshake".into();
    while client.is_handshaking() || client.wants_write() {
        flush(&mut client, &mut wire)?;
        if client.is_handshaking() && client.read_tls(&mut wire)? == 0 {
            return Err(io::ErrorKind::UnexpectedEof.into());
        }
    }
    report["handshake_verified"] = true.into();
    report["cipher_suite"] = u16::from(
        client
            .negotiated_cipher_suite()
            .ok_or_else(|| invalid("MissingNegotiatedSuite"))?,
    )
    .into();
    report["group"] = u16::from(
        client
            .negotiated_group()
            .ok_or_else(|| invalid("MissingNegotiatedGroup"))?,
    )
    .into();
    report["alpn"] = client
        .alpn_protocol()
        .map(|value| String::from_utf8_lossy(value).into_owned())
        .into();
    report["stage"] = "data".into();
    let mut uploaded = 0;
    let mut received = 0;
    let mut buffer = [0; 16 * 1024];
    while uploaded < payload.len() {
        let end = (uploaded + buffer.len()).min(payload.len());
        let written = client.write_plaintext(&payload[uploaded..end])?;
        if written == 0 {
            return Err(io::ErrorKind::WriteZero.into());
        }
        uploaded += written;
        report["uploaded_bytes"] = uploaded.into();
        flush(&mut client, &mut wire)?;
        // Interleave reads and writes so an echo peer's send backpressure cannot
        // deadlock a large application transfer behind an all-write-first loop.
        while received < uploaded {
            match client.read_plaintext(&mut buffer) {
                Ok(0) => return Err(io::ErrorKind::UnexpectedEof.into()),
                Ok(read) => {
                    if received + read > uploaded
                        || payload[received..received + read] != buffer[..read]
                    {
                        return Err(invalid("SyntheticPeerEchoMismatch"));
                    }
                    received += read;
                    report["received_bytes"] = received.into();
                }
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    flush(&mut client, &mut wire)?;
                    client.read_tls(&mut wire)?;
                }
                Err(error) => return Err(error),
            }
        }
    }
    report["payload_matches"] = (received == payload.len()).into();
    report["stage"] = "close".into();
    client.send_close_notify()?;
    flush(&mut client, &mut wire)?;
    report["client_close_notify"] = true.into();
    loop {
        match client.read_plaintext(&mut buffer) {
            Ok(0) => break,
            Ok(_) => return Err(invalid("SyntheticPeerUnexpectedTail")),
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                client.read_tls(&mut wire)?;
            }
            Err(error) => return Err(error),
        }
    }
    if !client.peer_has_closed() {
        return Err(io::ErrorKind::UnexpectedEof.into());
    }
    report["server_close_notify"] = true.into();
    report["transport_read_bytes"] = wire.read_bytes.into();
    report["transport_written_bytes"] = wire.written_bytes.into();
    report["status"] = "ok".into();
    Ok(())
}

fn main() {
    let mut report = json!({"status":"error", "stage":"input", "handshake_verified":false,
        "uploaded_bytes":0, "received_bytes":0, "payload_matches":false,
        "client_close_notify":false, "server_close_notify":false});
    let mut encoded = Vec::new();
    let result = io::stdin()
        .lock()
        .take((MAX_REQUEST + 1) as u64)
        .read_to_end(&mut encoded)
        .and_then(|_| {
            if encoded.len() > MAX_REQUEST {
                return Err(invalid("SyntheticPeerInputLimit"));
            }
            serde_json::from_slice(&encoded).map_err(|_| invalid("InvalidSyntheticPeerJson"))
        })
        .and_then(|input| run(input, &mut report));
    let code = match result {
        Ok(()) => 0,
        Err(error) => {
            report["error_kind"] = format!("{:?}", error.kind()).into();
            report["error"] = error.to_string().into();
            1
        }
    };
    println!("{report}");
    std::process::exit(code);
}
