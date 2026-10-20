//! Emits the actual finalized first flight using disposable public fixture
//! inputs. No sockets, subscriptions or provider credentials are used.
use serde_json::json;
use std::{
    fmt::Write as _,
    time::{SystemTime, UNIX_EPOCH},
};
use swirl_transport::reality::{ClientParameters, TlsClient};

fn hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        write!(out, "{byte:02x}").expect("writing a String cannot fail");
    }
    out
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut fingerprint = "chrome".to_owned();
    let mut name = "swirl-fingerprint.test".to_owned();
    let mut args = std::env::args().skip(1);
    while let Some(option) = args.next() {
        match option.as_str() {
            "--fingerprint" => fingerprint = args.next().ok_or("fingerprint value missing")?,
            "--server-name" => name = args.next().ok_or("server name missing")?,
            _ => return Err("unknown argument".into()),
        }
    }
    let parameters = ClientParameters::new(&name, [9; 32], &[0xab, 0xcd], [0, 1, 0])?
        .with_fingerprint(&fingerprint)?;
    let now = u32::try_from(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs())?;
    let mut client = TlsClient::new(&parameters, now, &[])?;
    let mut records = Vec::new();
    while client.wants_write() {
        client.write_tls(&mut records)?;
    }
    if records.len() < 5 || records[0] != 22 {
        return Err("missing ClientHello record".into());
    }
    let end = 5 + usize::from(u16::from_be_bytes([records[3], records[4]]));
    let handshake = records.get(5..end).ok_or("truncated ClientHello")?;
    println!(
        "{}",
        json!({
            "fingerprint": fingerprint,
            "profile": if fingerprint == "rustls" { "rustls" } else { "chrome_133" },
            "handshake_hex": hex(handshake), "record_hex": hex(&records),
        })
    );
    Ok(())
}
