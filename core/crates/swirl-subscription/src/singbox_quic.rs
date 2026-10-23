//! Closed sing-box 1.12 QUIC subset. The Qt layer preserves the source options;
//! this platform-independent adapter alone decides their executable meaning.
//! Newer/unmapped requirements are retained by inspection and fail closed.
use crate::{Hysteria2, Outbound, Tls, Tuic};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Map, Value};

type Object = Map<String, Value>;

fn closed(object: &Object, keys: &[&str]) -> Result<(), &'static str> {
    if object.keys().any(|key| !keys.contains(&key.as_str())) {
        return Err("SingBoxQuicUnmappedFields");
    }
    Ok(())
}
fn string(object: &Object, key: &str) -> Result<Option<String>, &'static str> {
    object
        .get(key)
        .map(|value| value.as_str().map(str::to_owned).ok_or("SingBoxQuicString"))
        .transpose()
}
fn boolean(object: &Object, key: &str, default: bool) -> Result<bool, &'static str> {
    object
        .get(key)
        .map(|value| value.as_bool().ok_or("SingBoxQuicBoolean"))
        .transpose()
        .map(|value| value.unwrap_or(default))
}
fn unsigned(object: &Object, key: &str) -> Result<Option<u64>, &'static str> {
    object
        .get(key)
        .map(|value| value.as_u64().ok_or("SingBoxQuicInteger"))
        .transpose()
}
fn certificate(value: &Value) -> Result<String, &'static str> {
    let pem = match value {
        Value::String(text) => text.clone(),
        Value::Array(lines) => {
            let mut result = String::new();
            for line in lines {
                let line = line.as_str().ok_or("SingBoxQuicCertificate")?;
                if result.len() + line.len() + 1 > 65_536 {
                    return Err("SingBoxQuicCertificate");
                }
                result.push_str(line);
                result.push('\n');
            }
            result
        }
        _ => return Err("SingBoxQuicCertificate"),
    };
    if pem.len() > 65_536 {
        return Err("SingBoxQuicCertificate");
    }
    let body = pem
        .trim()
        .strip_prefix("-----BEGIN CERTIFICATE-----")
        .and_then(|text| text.strip_suffix("-----END CERTIFICATE-----"))
        .ok_or("SingBoxQuicCertificate")?;
    let encoded: String = body
        .chars()
        .filter(|ch| !ch.is_ascii_whitespace())
        .collect();
    let der = STANDARD
        .decode(encoded)
        .map_err(|_| "SingBoxQuicCertificate")?;
    if der.is_empty() || der.len() > 49_152 {
        return Err("SingBoxQuicCertificate");
    }
    // The TLS backend validates DER and CA semantics. Do not read local paths.
    Ok(STANDARD.encode(der))
}
fn tls(raw: &Object, host: &str) -> Result<(Tls, bool), &'static str> {
    let tls = raw
        .get("tls")
        .and_then(Value::as_object)
        .ok_or("SingBoxQuicTlsRequired")?;
    closed(
        tls,
        &[
            "enabled",
            "server_name",
            "insecure",
            "alpn",
            "certificate",
            "disable_sni",
        ],
    )?;
    if !boolean(tls, "enabled", false)? {
        return Err("SingBoxQuicTlsRequired");
    }
    if boolean(tls, "disable_sni", false)? {
        return Err("SingBoxQuicDisableSniUnsupported");
    }
    let server_name = string(tls, "server_name")?
        .filter(|name| !name.is_empty())
        .unwrap_or_else(|| host.into());
    let alpn = match tls.get("alpn") {
        None => vec!["h3".into()],
        Some(Value::Array(values)) if values.is_empty() => vec!["h3".into()],
        Some(Value::Array(values)) => values
            .iter()
            .map(|value| value.as_str().map(str::to_owned).ok_or("SingBoxQuicAlpn"))
            .collect::<Result<_, _>>()?,
        _ => return Err("SingBoxQuicAlpn"),
    };
    Ok((
        Tls {
            server_name,
            alpn,
            ca_der_base64: tls.get("certificate").map(certificate).transpose()?,
        },
        boolean(tls, "insecure", false)?,
    ))
}
fn udp(raw: &Object) -> Result<bool, &'static str> {
    let values = match raw.get("network") {
        None => return Ok(true),
        Some(Value::String(value)) if value.is_empty() => return Ok(true),
        Some(Value::String(value)) => vec![value.as_str()],
        Some(Value::Array(values)) => values
            .iter()
            .map(|value| value.as_str().ok_or("SingBoxQuicNetwork"))
            .collect::<Result<_, _>>()?,
        _ => return Err("SingBoxQuicNetwork"),
    };
    if values.is_empty() {
        return Ok(true);
    }
    if values.iter().any(|value| !["tcp", "udp"].contains(value)) {
        return Err("SingBoxQuicNetwork");
    }
    // The current IR always permits TCP. Enabling it on a UDP-only source
    // would silently broaden that source's semantics.
    if !values.contains(&"tcp") {
        return Err("SingBoxQuicUdpOnlyUnsupported");
    }
    Ok(values.contains(&"udp"))
}

/// Parse a bounded Go-style duration exactly, rejecting sub-millisecond values
/// rather than rounding a heartbeat requirement to a different duration.
fn duration_ms(text: &str) -> Result<u64, &'static str> {
    if text.len() > 128 || text.is_empty() {
        return Err("SingBoxQuicDuration");
    }
    if text == "0" {
        return Ok(0);
    }
    let mut rest = text.strip_prefix('+').unwrap_or(text);
    if rest.is_empty() {
        return Err("SingBoxQuicDuration");
    }
    let mut total = 0u128;
    while !rest.is_empty() {
        let end = rest
            .find(|ch: char| !ch.is_ascii_digit() && ch != '.')
            .ok_or("SingBoxQuicDuration")?;
        let number = &rest[..end];
        rest = &rest[end..];
        let (unit, factor) = [
            ("ns", 1u128),
            ("us", 1_000),
            ("µs", 1_000),
            ("μs", 1_000),
            ("ms", 1_000_000),
            ("s", 1_000_000_000),
            ("m", 60_000_000_000),
            ("h", 3_600_000_000_000),
        ]
        .into_iter()
        .find(|(unit, _)| rest.starts_with(unit))
        .ok_or("SingBoxQuicDuration")?;
        rest = &rest[unit.len()..];
        let (whole, fraction) = number.split_once('.').unwrap_or((number, ""));
        if (whole.is_empty() && fraction.is_empty())
            || fraction.len() > 9
            || !fraction.bytes().all(|ch| ch.is_ascii_digit())
        {
            return Err("SingBoxQuicDuration");
        }
        let whole = if whole.is_empty() {
            0
        } else {
            whole.parse::<u128>().map_err(|_| "SingBoxQuicDuration")?
        };
        let denominator = 10u128.pow(fraction.len() as u32);
        let numerator = if fraction.is_empty() {
            0
        } else {
            fraction
                .parse::<u128>()
                .map_err(|_| "SingBoxQuicDuration")?
        };
        let fractional = numerator.checked_mul(factor).ok_or("SingBoxQuicDuration")?;
        if fractional % denominator != 0 {
            return Err("SingBoxQuicDuration");
        }
        total = total
            .checked_add(whole.checked_mul(factor).ok_or("SingBoxQuicDuration")?)
            .and_then(|v| v.checked_add(fractional / denominator))
            .ok_or("SingBoxQuicDuration")?;
    }
    if !total.is_multiple_of(1_000_000) {
        return Err("SingBoxQuicDuration");
    }
    u64::try_from(total / 1_000_000).map_err(|_| "SingBoxQuicDuration")
}

pub(crate) fn outbound(value: &Value) -> Result<Outbound, &'static str> {
    let raw = value.as_object().ok_or("SingBoxQuicObject")?;
    let normalized = match raw.get("_swirl-source-format") {
        None => false,
        Some(Value::String(value)) if value == "sing-box" => true,
        _ => return Err("SingBoxQuicSourceFormat"),
    };
    let kind = string(raw, "type")?.ok_or("SingBoxQuicProtocol")?;
    let mut known = vec!["type", "server", "password", "tls", "network"];
    known.extend(if normalized {
        vec!["name", "port", "_swirl-source-format"]
    } else {
        vec!["tag", "server_port"]
    });
    match kind.as_str() {
        "tuic" => known.extend([
            "uuid",
            "congestion_control",
            "udp_relay_mode",
            "udp_over_stream",
            "zero_rtt_handshake",
            "heartbeat",
        ]),
        "hysteria2" => known.extend(["up_mbps", "down_mbps", "obfs"]),
        _ => return Err("SingBoxQuicProtocol"),
    }
    closed(raw, &known)?;
    string(raw, if normalized { "name" } else { "tag" })?;
    let host = string(raw, "server")?.ok_or("SingBoxQuicEndpoint")?;
    let port = unsigned(raw, if normalized { "port" } else { "server_port" })?
        .and_then(|port| u16::try_from(port).ok())
        .filter(|port| *port != 0)
        .ok_or("SingBoxQuicEndpoint")?;
    let password = string(raw, "password")?.ok_or("SingBoxQuicPassword")?;
    let (tls, insecure) = tls(raw, &host)?;
    let udp = udp(raw)?;
    if kind == "tuic" {
        // sing-box TUIC does not supply an application protocol when omitted.
        // The current native TUIC runtime requires one; never invent h3 here.
        if raw
            .get("tls")
            .and_then(|tls| tls.get("alpn"))
            .and_then(Value::as_array)
            .is_none_or(Vec::is_empty)
        {
            return Err("SingBoxTuicExplicitAlpnRequired");
        }
        if boolean(raw, "udp_over_stream", false)? {
            return Err("SingBoxQuicUdpOverStreamUnsupported");
        }
        if boolean(raw, "zero_rtt_handshake", false)? {
            return Err("SingBoxQuicZeroRttUnsupported");
        }
        let heartbeat = string(raw, "heartbeat")?
            .map(|text| duration_ms(&text))
            .transpose()?
            .unwrap_or(0);
        let config = Tuic {
            host,
            port,
            password,
            tls,
            insecure,
            pin_sha256: None,
            udp,
            uuid: string(raw, "uuid")?.ok_or("SingBoxQuicUuid")?,
            udp_relay_mode: string(raw, "udp_relay_mode")?
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| "native".into()),
            congestion_control: string(raw, "congestion_control")?
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| "cubic".into()),
            heartbeat_interval_ms: if heartbeat == 0 { 10_000 } else { heartbeat },
            request_timeout_ms: 10_000,
        };
        config.validate()?;
        Ok(Outbound::Tuic(config))
    } else {
        let (obfs, obfs_password) = match raw.get("obfs") {
            None => (None, None),
            Some(Value::Object(obfs)) => {
                closed(obfs, &["type", "password"])?;
                (
                    Some(string(obfs, "type")?.ok_or("SingBoxQuicObfs")?),
                    Some(string(obfs, "password")?.ok_or("SingBoxQuicObfs")?),
                )
            }
            _ => return Err("SingBoxQuicObfs"),
        };
        let config = Hysteria2 {
            host,
            port,
            password,
            tls,
            insecure,
            pin_sha256: None,
            obfs,
            obfs_password,
            ports: None,
            up_mbps: unsigned(raw, "up_mbps")?,
            down_mbps: unsigned(raw, "down_mbps")?,
            ech: None,
            udp,
        };
        config.validate()?;
        Ok(Outbound::Hysteria2(config))
    }
}

#[cfg(test)]
#[path = "singbox_quic_tests.rs"]
mod tests;
