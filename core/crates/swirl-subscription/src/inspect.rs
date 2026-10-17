//! Content-based, offline format inspection. Original data is never included in
//! the public report. Only explicitly supported and fully mapped TCP nodes can
//! yield an executable isolated-test outbound; all original fields are retained.
use crate::{Config, Credentials, Limits, Node, ObfsHttp, Outbound, Tls};
use base64::{
    Engine,
    engine::general_purpose::{STANDARD, STANDARD_NO_PAD, URL_SAFE, URL_SAFE_NO_PAD},
};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;

pub const MAX_INPUT: usize = 8 * 1024 * 1024;
#[derive(Serialize)]
pub struct NodeCapability {
    pub index: usize,
    pub protocol: &'static str,
    pub version: &'static str,
    pub transport: &'static str,
    pub obfuscation: &'static str,
    pub tls: &'static str,
    pub cipher: &'static str,
    pub udp_declared: bool,
    pub unrecognized_fields: usize,
    pub native_tcp_candidate: bool,
    pub native_udp_supported: bool,
    pub real_network_verified: bool,
    pub diagnostic: &'static str,
}
#[derive(Serialize)]
pub struct Report {
    pub schema: u32,
    pub format: &'static str,
    pub recognized: bool,
    pub parsed: bool,
    pub error: Option<&'static str>,
    pub nodes: Vec<NodeCapability>,
    pub protocols: BTreeMap<&'static str, usize>,
    pub full_configuration_sections_preserved: usize,
    pub complete_configuration_execution_supported: bool,
    pub original_preserved: bool,
}
pub struct Inspection {
    pub report: Report,
    pub original: Vec<u8>,
    pub document: Value,
    pub originals: Vec<Value>,
    pub tcp_candidates: Vec<Option<Outbound>>,
}
fn decode(data: &[u8]) -> Result<Vec<u8>, &'static str> {
    let bytes: Vec<u8> = data
        .iter()
        .copied()
        .filter(|b| !b.is_ascii_whitespace())
        .collect();
    for engine in [&STANDARD, &STANDARD_NO_PAD, &URL_SAFE, &URL_SAFE_NO_PAD] {
        if let Ok(value) = engine.decode(&bytes) {
            return Ok(value);
        }
    }
    Err("InvalidBase64")
}
fn percent(value: &str) -> Result<String, &'static str> {
    percent_encoding::percent_decode_str(value)
        .decode_utf8()
        .map(|s| s.to_string())
        .map_err(|_| "InvalidUriEncoding")
}
fn allowed<'a>(value: &str, options: &[&'a str], fallback: &'a str) -> &'a str {
    options
        .iter()
        .copied()
        .find(|s| *s == value)
        .unwrap_or(fallback)
}
fn protocol(value: &str) -> &'static str {
    match value.to_ascii_lowercase().as_str() {
        "shadowsocks" | "ss" => "ss",
        "shadowsocksr" | "ssr" => "ssr",
        "http" | "https" => "http",
        "socks" | "socks5" | "socks5-tls" => "socks5",
        "trojan" => "trojan",
        "vless" => "vless",
        "vmess" => "vmess",
        "hysteria" => "hysteria",
        "hysteria2" | "hy2" => "hysteria2",
        "tuic" => "tuic",
        "anytls" => "anytls",
        "snell" => "snell",
        "mieru" => "mieru",
        "wireguard" => "wireguard",
        "ssh" => "ssh",
        "naive" | "naive+https" => "naive",
        "direct" => "direct",
        "reject" | "block" => "reject",
        _ => "unknown",
    }
}
fn yaml(text: &str) -> Result<Value, &'static str> {
    let mut options = serde_saphyr::Options::default();
    options.with_snippet = false;
    options.reject_unsupported_tags = true;
    options.strict_booleans = true;
    options.duplicate_keys = serde_saphyr::DuplicateKeyPolicy::Error;
    let mut budget = serde_saphyr::Budget::default();
    budget.max_depth = 64;
    budget.max_documents = 1;
    budget.max_nodes = 100000;
    budget.max_events = 300000;
    budget.max_aliases = 256;
    budget.max_anchors = 128;
    budget.max_total_scalar_bytes = MAX_INPUT;
    budget.max_recorded_anchor_bytes = MAX_INPUT;
    budget.max_recorded_anchor_events = 100000;
    options.budget = Some(budget);
    serde_saphyr::from_str_with_options(text, options).map_err(|_| "DocumentSyntaxOrBudget")
}
fn plugin_options(value: &str) -> Result<(String, serde_json::Map<String, Value>), &'static str> {
    if value.len() > 8192 {
        return Err("PluginParametersLimit");
    }
    // SIP002/SIP003 delimiters may be escaped. Splitting on ';' loses their meaning.
    let mut fields = Vec::new();
    let mut field = String::new();
    let mut equal = None;
    let mut escaped = false;
    for c in value.chars() {
        if escaped {
            if !matches!(c, ':' | ';' | '=' | '\\') {
                return Err("PluginEscape");
            }
            field.push(c);
            escaped = false;
        } else {
            match c {
                '\\' => escaped = true,
                ';' => {
                    if fields.len() >= 64 {
                        return Err("PluginParametersLimit");
                    }
                    if field.is_empty() {
                        return Err("PluginParameters");
                    }
                    fields.push((std::mem::take(&mut field), equal.take()));
                }
                '=' => {
                    if equal.is_some() {
                        return Err("PluginParameters");
                    }
                    equal = Some(field.len());
                    field.push(c);
                }
                _ => field.push(c),
            }
        }
    }
    if escaped || field.is_empty() {
        return Err("PluginParameters");
    }
    fields.push((field, equal));
    let (name, separator) = fields.remove(0);
    if separator.is_some() || name.is_empty() {
        return Err("PluginParameters");
    }
    let mut options = serde_json::Map::new();
    for (field, equal) in fields {
        let (key, value) = match equal {
            Some(i) => (&field[..i], Value::String(field[i + 1..].into())),
            None => (field.as_str(), Value::Bool(true)),
        };
        let key = match key {
            "obfs" => "mode",
            "obfs-host" => "host",
            _ => key,
        };
        if key.is_empty() || options.insert(key.into(), value).is_some() {
            return Err("DuplicatePluginParameter");
        }
    }
    Ok((name, options))
}
fn uri(line: &str) -> Result<Value, &'static str> {
    if let Some(encoded) = line.strip_prefix("vmess://") {
        let raw: Value =
            serde_json::from_slice(&decode(encoded.as_bytes())?).map_err(|_| "VmessJson")?;
        return Ok(
            json!({"type":"vmess","server":raw["add"],"port":raw["port"],"network":raw["net"],"tls":raw["tls"],"raw-vmess":raw}),
        );
    }
    if let Some(encoded) = line.strip_prefix("ssr://") {
        let decoded = String::from_utf8(decode(encoded.as_bytes())?).map_err(|_| "UriEncoding")?;
        let fields: Vec<_> = decoded
            .split("/?")
            .next()
            .unwrap_or("")
            .split(':')
            .collect();
        if fields.len() != 6 {
            return Err("SsrUri");
        }
        return Ok(
            json!({"type":"ssr","server":fields[0],"port":fields[1],"protocol":fields[2],"cipher":fields[3],"obfs":fields[4],"raw-uri":line}),
        );
    }
    let mut source = line.to_owned();
    if let Some(rest) = line.strip_prefix("ss://")
        && !rest.contains('@')
    {
        let main = rest.split('#').next().unwrap_or(rest);
        source = format!(
            "ss://{}",
            String::from_utf8(decode(main.as_bytes())?).map_err(|_| "UriEncoding")?
        );
    }
    let u = url::Url::parse(&source).map_err(|_| "UriSyntax")?;
    let mut n = json!({"type":protocol(u.scheme()),"server":u.host_str().ok_or("UriHost")?,"port":u.port().or_else(||if u.scheme()=="https"{Some(443)}else{None}).ok_or("UriPort")?,"raw-uri":line});
    match n["type"].as_str().unwrap_or("") {
        "ss" => {
            let auth = if let Some(pass) = u.password() {
                format!("{}:{}", percent(u.username())?, percent(pass)?)
            } else {
                String::from_utf8(decode(u.username().as_bytes())?).map_err(|_| "UriEncoding")?
            };
            let (cipher, password) = auth.split_once(':').ok_or("SsAuthentication")?;
            n["cipher"] = cipher.into();
            n["password"] = password.into();
        }
        "trojan" | "hysteria2" | "anytls" => n["password"] = percent(u.username())?.into(),
        "vless" | "tuic" => n["uuid"] = percent(u.username())?.into(),
        _ => {
            n["username"] = percent(u.username())?.into();
            if let Some(pass) = u.password() {
                n["password"] = percent(pass)?.into();
            }
        }
    }
    if u.scheme() == "https" {
        n["tls"] = true.into();
    }
    let mut seen = std::collections::HashSet::new();
    for (key, value) in u.query_pairs() {
        if !seen.insert(key.to_string()) {
            return Err("DuplicateUriParameter");
        }
        if n["type"] == "ss" && key == "plugin" {
            if n.get("plugin").is_some() || n.get("plugin-opts").is_some() {
                return Err("ConflictingUriParameter");
            }
            let (name, options) = plugin_options(&value)?;
            n["plugin"] = name.into();
            n["plugin-opts"] = options.into();
            continue;
        }
        let key = match key.as_ref() {
            "type" => "network",
            "security" => "security",
            "sni" | "peer" => "sni",
            "allowInsecure" => "skip-cert-verify",
            _ => key.as_ref(),
        };
        if n.get(key).is_some() {
            return Err("ConflictingUriParameter");
        }
        n[key] = if key == "skip-cert-verify" {
            match value.as_ref() {
                "1" | "true" => Value::Bool(true),
                "0" | "false" => Value::Bool(false),
                _ => return Err("InvalidUriBoolean"),
            }
        } else {
            Value::String(value.into_owned())
        };
    }
    Ok(n)
}
fn csv(text: &str) -> Result<Vec<String>, &'static str> {
    let mut out = Vec::new();
    let mut field = String::new();
    let mut quote = None;
    for c in text.chars() {
        if quote == Some(c) {
            quote = None;
        } else if quote.is_none() && (c == '"' || c == '\'') {
            quote = Some(c);
        } else if c == ',' && quote.is_none() {
            out.push(field.trim().to_string());
            field.clear();
        } else {
            field.push(c);
        }
    }
    if quote.is_some() {
        return Err("IniQuotation");
    }
    out.push(field.trim().to_string());
    Ok(out)
}
fn ini(text: &str) -> Result<Vec<Value>, &'static str> {
    let mut section = String::new();
    let mut nodes = Vec::new();
    for line in text.lines().map(str::trim) {
        if line.starts_with('[') {
            section = line.to_ascii_lowercase();
            continue;
        }
        if line.is_empty()
            || line.starts_with(['#', ';'])
            || !matches!(section.as_str(), "[proxy]" | "[server_local]")
        {
            continue;
        }
        let (name, value) = line.split_once('=').ok_or("IniAssignment")?;
        let fields = csv(value)?;
        let qx = section == "[server_local]";
        if !qx && matches!(protocol(&fields[0]), "direct" | "reject") {
            continue;
        }
        if fields.len() < 2 {
            return Err("IniFields");
        }
        let (kind, host, port, start) = if qx {
            let (host, port) = fields[0].rsplit_once(':').ok_or("IniEndpoint")?;
            (
                protocol(name.trim()),
                host.trim_matches(['[', ']']).to_string(),
                port.parse::<u16>().map_err(|_| "IniPort")?,
                1,
            )
        } else {
            if fields.len() < 3 {
                return Err("IniFields");
            }
            (
                protocol(&fields[0]),
                fields[1].clone(),
                fields[2].parse::<u16>().map_err(|_| "IniPort")?,
                3,
            )
        };
        if matches!(kind, "direct" | "reject") {
            continue;
        }
        let mut n =
            json!({"type":kind,"server":host,"port":port,"name":name.trim(),"raw-ini":line});
        let mut positional = 0;
        let mut seen = std::collections::HashSet::new();
        for field in &fields[start..] {
            if let Some((key, value)) = field.split_once('=') {
                let key = key.trim();
                let canonical = match key {
                    "encrypt-method" | "method" => "cipher",
                    "tls-host" | "tls-name" => "sni",
                    "udp-relay" => "udp",
                    "over-tls" => "tls",
                    "fast-open" => "tfo",
                    _ => key,
                };
                if !seen.insert(canonical) || n.get(canonical).is_some() {
                    return Err("DuplicateIniParameter");
                }
                n[canonical] = if matches!(
                    canonical,
                    "udp" | "tls" | "tfo" | "skip-cert-verify" | "tls-verification"
                ) {
                    match value.trim().to_ascii_lowercase().as_str() {
                        "true" => true.into(),
                        "false" => false.into(),
                        _ => value.trim().into(),
                    }
                } else {
                    value.trim().into()
                };
            } else {
                let key = match (kind, positional) {
                    ("ss", 0) => "cipher",
                    ("ss", 1) | ("trojan", 0) => "password",
                    _ => "unmapped-positional",
                };
                n[key] = field.as_str().into();
                positional += 1;
            }
        }
        nodes.push(n);
    }
    Ok(nodes)
}
fn parse(bytes: &[u8], depth: usize) -> Result<(&'static str, Value, Vec<Value>), &'static str> {
    if depth > 2 {
        return Err("EncodingDepth");
    }
    let text = std::str::from_utf8(bytes)
        .map_err(|_| "EncodingNotUtf8")?
        .trim_start_matches('\u{feff}')
        .trim();
    if text.is_empty() {
        return Err("EmptyDocument");
    }
    if text
        .lines()
        .map(str::trim)
        .find(|line| !line.is_empty() && !line.starts_with(['#', ';']))
        .is_some_and(|line| line.starts_with('['))
        && text.lines().any(|l| {
            matches!(
                l.trim().to_ascii_lowercase().as_str(),
                "[proxy]" | "[server_local]"
            )
        })
    {
        return Ok(("ini", Value::String(text.to_string()), ini(text)?));
    }
    if text.lines().filter(|l| !l.trim().is_empty()).all(|l| {
        l.trim().split_once("://").is_some_and(|(scheme, _)| {
            !scheme.is_empty()
                && scheme.len() < 32
                && scheme
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"+.-".contains(&b))
        })
    }) {
        let nodes = text
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(|l| uri(l.trim()))
            .collect::<Result<Vec<_>, _>>()?;
        return Ok(("uri-list", Value::String(text.to_string()), nodes));
    }
    if text
        .bytes()
        .all(|b| b.is_ascii_alphanumeric() || b"+/=_-\r\n \t".contains(&b))
    {
        let decoded = decode(text.as_bytes())?;
        let (_, doc, nodes) = parse(&decoded, depth + 1)?;
        return Ok(("base64", doc, nodes));
    }
    let document = yaml(text)?;
    if let Some(nodes) = document.get("proxies").and_then(Value::as_array) {
        return Ok((
            if text.starts_with('{') {
                "clash-json"
            } else {
                "clash-yaml"
            },
            document.clone(),
            nodes.clone(),
        ));
    }
    if let Some(nodes) = document.get("outbounds").and_then(Value::as_array) {
        let family = if nodes.iter().any(|n| n.get("protocol").is_some()) {
            "xray-v2ray-json"
        } else {
            "sing-box-json"
        };
        return Ok((family, document.clone(), nodes.clone()));
    }
    Err("UnknownConfigurationShape")
}
const SS_FIELDS: &[&str] = &[
    "type",
    "name",
    "tag",
    "server",
    "port",
    "server_port",
    "password",
    "cipher",
    "method",
    "udp",
    "network",
    "tfo",
    "plugin",
    "plugin-opts",
    "obfs",
    "obfs-host",
    "raw-uri",
    "raw-ini",
];
fn ss_outbound(raw: &Value, family: &str) -> Result<Outbound, &'static str> {
    if family == "xray-v2ray-json" {
        return Err("UnmappedFields");
    }
    let object = raw.as_object().ok_or("UnmappedFields")?;
    if object.keys().any(|k| !SS_FIELDS.contains(&k.as_str())) {
        return Err("UnmappedFields");
    }
    if raw
        .get("network")
        .is_some_and(|v| v.as_str() != Some("tcp"))
    {
        return Err("TransportNotImplemented");
    }
    if raw.get("tfo").is_some_and(|v| v.as_bool() != Some(false)) {
        return Err("TcpFastOpenNotImplemented");
    }
    if raw.get("udp").is_some_and(|v| !v.is_boolean()) {
        return Err("UnmappedOrInvalidParameters");
    }
    let cipher = raw
        .get("cipher")
        .or_else(|| raw.get("method"))
        .and_then(Value::as_str)
        .ok_or("CipherNotImplemented")?;
    if raw.get("cipher").is_some() && raw.get("method").is_some() && raw["cipher"] != raw["method"]
    {
        return Err("ConflictingCipher");
    }
    if !["aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305"].contains(&cipher) {
        return Err("CipherNotImplemented");
    }
    let obfs_http = if let Some(plugin) = raw.get("plugin") {
        if !matches!(plugin.as_str(), Some("obfs" | "obfs-local" | "simple-obfs"))
            || raw.get("obfs").is_some()
            || raw.get("obfs-host").is_some()
        {
            return Err("PluginNotImplemented");
        }
        let options = raw
            .get("plugin-opts")
            .and_then(Value::as_object)
            .ok_or("PluginParameters")?;
        if options
            .keys()
            .any(|k| !["mode", "host"].contains(&k.as_str()))
            || options.get("mode").and_then(Value::as_str) != Some("http")
        {
            return Err("PluginNotImplemented");
        }
        Some(ObfsHttp {
            host: options
                .get("host")
                .and_then(Value::as_str)
                .ok_or("PluginParameters")?
                .to_string(),
        })
    } else if raw.get("obfs").is_some() {
        if raw["obfs"].as_str() != Some("http") || raw.get("plugin-opts").is_some() {
            return Err("PluginNotImplemented");
        }
        Some(ObfsHttp {
            host: raw
                .get("obfs-host")
                .and_then(Value::as_str)
                .ok_or("PluginParameters")?
                .to_string(),
        })
    } else {
        if raw.get("plugin-opts").is_some() || raw.get("obfs-host").is_some() {
            return Err("PluginParameters");
        }
        None
    };
    let host = raw
        .get("server")
        .and_then(Value::as_str)
        .ok_or("NodeParameters")?
        .to_string();
    let port = raw
        .get("port")
        .or_else(|| raw.get("server_port"))
        .and_then(|p| {
            p.as_u64()
                .or_else(|| p.as_str().and_then(|s| s.parse().ok()))
        })
        .and_then(|p| u16::try_from(p).ok())
        .ok_or("NodeParameters")?;
    let password = raw
        .get("password")
        .and_then(Value::as_str)
        .ok_or("NodeParameters")?
        .to_string();
    let outbound = Outbound::Shadowsocks {
        host,
        port,
        password,
        cipher: cipher.into(),
        udp: raw.get("udp").and_then(Value::as_bool).unwrap_or(false),
        obfs_http,
    };
    let config = Config {
        schema: 1,
        listen: "127.0.0.1:0".parse().expect("constant"),
        selected: "isolated".into(),
        nodes: vec![Node {
            id: "isolated".into(),
            outbound: outbound.clone(),
        }],
        rules: vec![],
        selectors: vec![],
        inbound_auth: None,
        limits: Limits::default(),
    };
    config.validate()?;
    Ok(outbound)
}
fn capability(raw: &Value, index: usize, family: &str) -> (NodeCapability, Option<Outbound>) {
    let kind = protocol(
        raw.get("type")
            .or_else(|| raw.get("protocol"))
            .and_then(Value::as_str)
            .unwrap_or(""),
    );
    let transport_raw = raw
        .get("network")
        .and_then(Value::as_str)
        .or_else(|| raw.pointer("/transport/type").and_then(Value::as_str))
        .unwrap_or("tcp");
    let transport = allowed(
        transport_raw,
        &[
            "tcp",
            "ws",
            "grpc",
            "h2",
            "http",
            "httpupgrade",
            "xhttp",
            "quic",
        ],
        "unknown",
    );
    let obfuscation = if kind == "ss" && (raw.get("plugin").is_some() || raw.get("obfs").is_some())
    {
        if raw
            .get("plugin")
            .is_none_or(|p| matches!(p.as_str(), Some("obfs" | "obfs-local" | "simple-obfs")))
        {
            allowed(
                raw.pointer("/plugin-opts/mode")
                    .or_else(|| raw.get("obfs"))
                    .and_then(Value::as_str)
                    .unwrap_or(""),
                &["http", "tls"],
                "declared-unrecognized",
            )
        } else {
            "declared-unrecognized"
        }
    } else {
        "none"
    };
    let tls_obj = raw.get("tls");
    let reality = raw.get("reality-opts").is_some()
        || raw.pointer("/tls/reality").is_some()
        || raw.get("security").and_then(Value::as_str) == Some("reality");
    let tls_enabled = kind == "trojan"
        || tls_obj.and_then(Value::as_bool) == Some(true)
        || raw.pointer("/tls/enabled").and_then(Value::as_bool) == Some(true)
        || raw.get("security").and_then(Value::as_str) == Some("tls");
    let tls = if reality {
        "reality"
    } else if tls_enabled {
        "tls"
    } else {
        "not-enabled"
    };
    let cipher = allowed(
        raw.get("cipher")
            .or_else(|| raw.get("method"))
            .and_then(Value::as_str)
            .unwrap_or(""),
        &[
            "aes-128-gcm",
            "aes-256-gcm",
            "chacha20-ietf-poly1305",
            "2022-blake3-aes-128-gcm",
            "2022-blake3-aes-256-gcm",
            "2022-blake3-chacha20-poly1305",
            "none",
            "auto",
            "aes-128-cfb",
            "rc4-md5",
        ],
        "not-declared-or-unrecognized",
    );
    let version = if cipher.starts_with("2022-") {
        "cipher-family-2022"
    } else {
        match raw.get("version").or_else(|| raw.get("v")) {
            None => "not-declared",
            Some(Value::Number(n)) if n.as_u64() == Some(1) => "1",
            Some(Value::Number(n)) if n.as_u64() == Some(2) => "2",
            Some(Value::String(s)) if s == "1" => "1",
            Some(Value::String(s)) if s == "2" => "2",
            _ => "declared-unrecognized",
        }
    };
    let known = [
        "type",
        "name",
        "tag",
        "server",
        "port",
        "server_port",
        "username",
        "password",
        "tls",
        "sni",
        "servername",
        "alpn",
        "skip-cert-verify",
        "udp",
        "cipher",
        "method",
        "raw-uri",
        "raw-ini",
        "network",
        "security",
        "tfo",
        "tls-verification",
    ];
    let unrecognized = raw.as_object().map_or(1, |o| {
        o.keys()
            .filter(|k| {
                if kind == "ss" {
                    !SS_FIELDS.contains(&k.as_str())
                } else {
                    !known.contains(&k.as_str())
                        && !(kind == "vless"
                            && ["uuid", "flow", "encryption"].contains(&k.as_str()))
                }
            })
            .count()
    });
    let udp = raw.get("udp").and_then(Value::as_bool) == Some(true);
    let mut diagnostic = "ProtocolNotImplemented";
    let mut candidate = None;
    if kind == "ss" {
        match ss_outbound(raw, family) {
            Ok(outbound) => {
                candidate = Some(outbound);
                diagnostic = "TcpCandidateNotYetVerified";
            }
            Err(reason) => diagnostic = reason,
        }
    }
    if ["http", "socks5", "trojan", "vless"].contains(&kind) {
        diagnostic = "UnmappedOrInvalidParameters";
        let host = raw
            .get("server")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let port = raw
            .get("port")
            .or_else(|| raw.get("server_port"))
            .and_then(|p| {
                p.as_u64()
                    .or_else(|| p.as_str().and_then(|s| s.parse().ok()))
            })
            .unwrap_or(0);
        let skip = raw.get("skip-cert-verify").and_then(Value::as_bool) == Some(true)
            || raw.pointer("/tls/insecure").and_then(Value::as_bool) == Some(true)
            || raw.get("tls-verification").and_then(Value::as_bool) == Some(false);
        let unsafe_booleans = ["udp", "skip-cert-verify", "tfo", "tls-verification"]
            .iter()
            .any(|key| raw.get(*key).is_some_and(|v| !v.is_boolean()));
        let tls_unknown = tls_obj.and_then(Value::as_object).is_some_and(|o| {
            o.keys()
                .any(|k| !["enabled", "server_name", "alpn", "insecure"].contains(&k.as_str()))
        });
        let declared_tls = tls_obj
            .and_then(Value::as_bool)
            .or_else(|| raw.pointer("/tls/enabled").and_then(Value::as_bool));
        let security = raw.get("security").and_then(Value::as_str);
        let names = [
            raw.get("sni"),
            raw.get("servername"),
            raw.pointer("/tls/server_name"),
        ];
        let first_name = names.iter().flatten().next().copied();
        let tls_invalid = tls_obj.is_some_and(|v| !v.is_boolean() && !v.is_object())
            || (kind == "trojan" && declared_tls == Some(false))
            || matches!(
                (declared_tls, security),
                (Some(false), Some("tls")) | (Some(true), Some("none"))
            )
            || ["/tls/enabled", "/tls/insecure"]
                .iter()
                .any(|p| raw.pointer(p).is_some_and(|v| !v.is_boolean()))
            || names
                .iter()
                .flatten()
                .any(|n| !n.is_string() || Some(*n) != first_name)
            || (!tls_enabled
                && tls_obj
                    .and_then(Value::as_object)
                    .is_some_and(|o| o.keys().any(|k| k != "enabled")));
        diagnostic = if skip {
            "CertificateVerificationDisabledUnsupported"
        } else if raw.get("tfo").and_then(Value::as_bool) == Some(true) {
            "TcpFastOpenNotImplemented"
        } else if reality {
            "RealityNotImplemented"
        } else if transport != "tcp" {
            "TransportNotImplemented"
        } else if unrecognized > 0 || tls_unknown {
            "UnmappedFields"
        } else {
            diagnostic
        };
        // TFO is preserved; a true request is not silently claimed as implemented.
        if unrecognized == 0
            && (kind != "vless"
                || (raw.get("username").is_none()
                    && raw.get("password").is_none()
                    && raw.get("flow").is_none_or(|v| v.as_str() == Some(""))
                    && raw
                        .get("encryption")
                        .is_none_or(|v| v.as_str() == Some("none"))))
            && ["username", "password", "server", "sni", "servername"]
                .iter()
                .all(|key| raw.get(*key).is_none_or(Value::is_string))
            && raw.get("cipher").is_none()
            && raw.get("method").is_none()
            && raw
                .get("security")
                .is_none_or(|v| matches!(v.as_str(), Some("tls" | "none")))
            && (tls_enabled
                || (raw.get("sni").is_none()
                    && raw.get("servername").is_none()
                    && raw.get("alpn").is_none()))
            && !raw.get("tfo").and_then(Value::as_bool).unwrap_or(false)
            && !unsafe_booleans
            && !tls_unknown
            && !tls_invalid
            && !skip
            && !reality
            && transport == "tcp"
            && port > 0
            && port <= 65535
            && family != "xray-v2ray-json"
        {
            let password = raw
                .get("password")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let username = raw
                .get("username")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let auth = if username.is_empty() && password.is_empty() {
                None
            } else {
                Some(Credentials {
                    username,
                    password: password.clone(),
                })
            };
            let tls = if tls_enabled {
                let name = raw
                    .get("sni")
                    .or_else(|| raw.get("servername"))
                    .or_else(|| raw.pointer("/tls/server_name"))
                    .and_then(Value::as_str)
                    .unwrap_or(&host)
                    .to_string();
                let alpn = raw
                    .get("alpn")
                    .or_else(|| raw.pointer("/tls/alpn"))
                    .map_or(Ok(Vec::new()), |v| {
                        serde_json::from_value::<Vec<String>>(v.clone())
                    });
                match alpn {
                    Ok(alpn) => Some(Tls {
                        server_name: name,
                        alpn,
                        ca_der_base64: None,
                    }),
                    Err(_) => {
                        return (
                            NodeCapability {
                                index,
                                protocol: kind,
                                version,
                                transport,
                                obfuscation,
                                tls: "tls",
                                cipher,
                                udp_declared: udp,
                                unrecognized_fields: unrecognized,
                                native_tcp_candidate: false,
                                native_udp_supported: false,
                                real_network_verified: false,
                                diagnostic: "InvalidAlpn",
                            },
                            None,
                        );
                    }
                }
            } else {
                None
            };
            let outbound = match kind {
                "vless" => Some(Outbound::Vless {
                    host,
                    port: port as u16,
                    uuid: raw.get("uuid").and_then(Value::as_str).unwrap_or("").into(),
                    tls,
                }),
                "trojan" => tls.map(|tls| Outbound::Trojan {
                    host,
                    port: port as u16,
                    password,
                    tls,
                }),
                "http" => Some(Outbound::HttpConnect {
                    host,
                    port: port as u16,
                    auth,
                    tls,
                }),
                _ => Some(Outbound::Socks5 {
                    host,
                    port: port as u16,
                    auth,
                    tls,
                }),
            };
            if let Some(outbound) = outbound {
                let config = Config {
                    schema: 1,
                    listen: "127.0.0.1:0".parse().expect("constant address"),
                    selected: "isolated".into(),
                    nodes: vec![Node {
                        id: "isolated".into(),
                        outbound: outbound.clone(),
                    }],
                    rules: Vec::new(),
                    selectors: Vec::new(),
                    inbound_auth: None,
                    limits: Limits::default(),
                };
                if config.validate().is_ok() {
                    candidate = Some(outbound);
                    diagnostic = "TcpCandidateNotYetVerified";
                }
            }
        }
    }
    (
        NodeCapability {
            index,
            protocol: kind,
            version,
            transport,
            obfuscation,
            tls,
            cipher,
            udp_declared: udp,
            unrecognized_fields: unrecognized,
            native_tcp_candidate: candidate.is_some(),
            native_udp_supported: kind == "ss" && udp && candidate.is_some(),
            real_network_verified: false,
            diagnostic,
        },
        candidate,
    )
}
pub fn inspect(bytes: &[u8]) -> Inspection {
    let mut report = Report {
        schema: 1,
        format: "unknown",
        recognized: false,
        parsed: false,
        error: None,
        nodes: Vec::new(),
        protocols: BTreeMap::new(),
        full_configuration_sections_preserved: 0,
        complete_configuration_execution_supported: false,
        original_preserved: true,
    };
    if bytes.len() > MAX_INPUT {
        report.error = Some("DocumentSize");
        report.original_preserved = false;
        return Inspection {
            report,
            original: Vec::new(),
            document: Value::Null,
            originals: Vec::new(),
            tcp_candidates: Vec::new(),
        };
    }
    let (format, document, nodes) = match parse(bytes, 0) {
        Ok(v) => v,
        Err(e) => {
            report.error = Some(e);
            return Inspection {
                report,
                original: bytes.to_vec(),
                document: Value::Null,
                originals: Vec::new(),
                tcp_candidates: Vec::new(),
            };
        }
    };
    report.format = format;
    report.recognized = true;
    report.parsed = true;
    report.full_configuration_sections_preserved = document.as_object().map_or(0, |o| {
        o.keys()
            .filter(|k| !matches!(k.as_str(), "proxies" | "outbounds"))
            .count()
    });
    if nodes.len() > 2000 {
        report.error = Some("NodeCountLimit");
        report.parsed = false;
        return Inspection {
            report,
            original: bytes.to_vec(),
            document,
            originals: Vec::new(),
            tcp_candidates: Vec::new(),
        };
    }
    let mut candidates = Vec::new();
    for (index, node) in nodes.iter().enumerate() {
        let (capability, candidate) = capability(node, index + 1, format);
        *report.protocols.entry(capability.protocol).or_default() += 1;
        report.nodes.push(capability);
        candidates.push(candidate);
    }
    Inspection {
        report,
        original: bytes.to_vec(),
        document,
        originals: nodes,
        tcp_candidates: candidates,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vless_base_tls_maps_but_flow_and_reality_never_downgrade() {
        let base = "vless://00112233-4455-6677-8899-aabbccddeeff@example.org:443?security=tls&encryption=none";
        let r = inspect(base.as_bytes());
        assert!(r.report.nodes[0].native_tcp_candidate);
        assert!(!r.report.nodes[0].native_udp_supported);
        for suffix in [
            "&flow=xtls-rprx-vision",
            "&type=ws",
            "&encryption=mlkem768x25519plus.native.0rtt",
        ] {
            let text = format!("{base}{suffix}");
            assert!(
                !inspect(text.as_bytes())
                    .report
                    .nodes
                    .first()
                    .is_some_and(|n| n.native_tcp_candidate)
            );
        }
        let reality = base.replace("security=tls", "security=reality");
        assert!(!inspect(reality.as_bytes()).report.nodes[0].native_tcp_candidate);
        let encrypted = base.replace("encryption=none", "encryption=unsupported");
        let r = inspect(encrypted.as_bytes());
        assert!(r.report.parsed);
        assert!(!r.report.nodes[0].native_tcp_candidate);
        for tls in [
            r#"{"enabled":"true"}"#,
            r#"{"enabled":false,"server_name":"example.org"}"#,
            r#"{"enabled":true,"insecure":"false"}"#,
        ] {
            let text = format!(
                r#"{{"outbounds":[{{"type":"vless","server":"example.org","server_port":443,"uuid":"00112233-4455-6677-8899-aabbccddeeff","tls":{tls}}}]}}"#
            );
            assert!(!inspect(text.as_bytes()).report.nodes[0].native_tcp_candidate);
        }
        let conflicting = base.to_owned() + "&sni=example.org&servername=other.example";
        assert!(!inspect(conflicting.as_bytes()).report.nodes[0].native_tcp_candidate);
    }
    #[test]
    fn sip002_plugin_mapping_escaping_and_unknown_retention() {
        let prefix = "ss://YWVzLTEyOC1nY206Zml4dHVyZQ@example.org:443/?plugin=";
        for name in ["obfs-local", "simple-obfs", "obfs"] {
            let input = format!("{prefix}{name}%3Bobfs%3Dhttp%3Bobfs-host%3Dobfs.example");
            let r = inspect(input.as_bytes());
            assert!(r.report.nodes[0].native_tcp_candidate);
            assert_eq!(r.report.nodes[0].obfuscation, "http");
            assert_eq!(r.original, input.as_bytes());
        }
        let (_, options) = plugin_options(r"obfs-local;future=a\;b\=c\\d\:e;flag").unwrap();
        assert_eq!(options["future"], r"a;b=c\d:e");
        assert_eq!(options["flag"], true);
        for tail in [
            "%3Bobfs%3Dhttp%3Bmode%3Dtls",
            "%3Bflag%3Bflag",
            "%3Bhost%3Dx%5C",
        ] {
            assert!(
                !inspect(format!("{prefix}obfs-local{tail}").as_bytes())
                    .report
                    .parsed
            );
        }
        let input = format!(
            "{prefix}obfs-local%3Bobfs%3Dhttp%3Bobfs-host%3Dobfs.example%3Bobfs-uri%3D%2Fcustom"
        );
        let r = inspect(input.as_bytes());
        assert!(r.report.parsed);
        assert!(!r.report.nodes[0].native_tcp_candidate);
        assert_eq!(r.originals[0]["plugin-opts"]["obfs-uri"], "/custom");
        let r=inspect(br#"{"proxies":[{"type":"ss","server":"example.org","port":443,"cipher":"aes-128-gcm","password":"fixture","tls":true}]}"#);
        assert!(!r.report.nodes[0].native_tcp_candidate);
        assert_eq!(r.report.nodes[0].unrecognized_fields, 1);
    }
    #[test]
    fn private_fields_retained_not_reported() {
        let input=b"proxies:\n - {name: SECRET_NAME, type: trojan, server: edge.example, port: 443, password: SECRET_PASSWORD, private-extension: SECRET_VALUE}\ndns: {enable: true}\n";
        let result = inspect(input);
        assert!(result.report.parsed);
        assert_eq!(result.original, input);
        assert_eq!(result.report.nodes[0].protocol, "trojan");
        assert!(!result.report.nodes[0].native_tcp_candidate);
        let report = serde_json::to_string(&result.report).unwrap();
        assert!(!report.contains("SECRET"));
        assert!(!report.contains("edge.example"));
        assert_eq!(result.document["dns"]["enable"], true);
    }
    #[test]
    fn names_never_determine_protocol() {
        let r=inspect(br#"{"proxies":[{"name":"Trojan","type":"ss","server":"example.org","port":443,"cipher":"2022-blake3-aes-128-gcm","password":"secret"}]}"#);
        assert_eq!(r.report.nodes[0].protocol, "ss");
        assert_eq!(r.report.nodes[0].version, "cipher-family-2022");
        assert!(!r.report.nodes[0].native_tcp_candidate);
    }
    #[test]
    fn ss_aead_http_obfs_maps_without_losing_unsupported_options() {
        let input=br#"{"proxies":[{"type":"ss","server":"example.org","port":443,"cipher":"aes-128-gcm","password":"fixture","udp":true,"plugin":"obfs","plugin-opts":{"mode":"http","host":"obfs.example"}}]}"#;
        let result = inspect(input);
        assert!(result.report.nodes[0].native_tcp_candidate);
        assert!(result.report.nodes[0].native_udp_supported);
        assert_eq!(result.original, input);
        match result.tcp_candidates[0].as_ref().unwrap() {
            Outbound::Shadowsocks {
                obfs_http: Some(obfs),
                ..
            } => assert_eq!(obfs.host, "obfs.example"),
            _ => panic!("incorrect mapping"),
        }
        for options in [
            r#""mode":"tls","host":"obfs.example""#,
            r#""mode":"http","host":"obfs.example","extra":"retained""#,
        ] {
            let text = String::from_utf8(input.to_vec())
                .unwrap()
                .replace(r#""mode":"http","host":"obfs.example""#, options);
            let rejected = inspect(text.as_bytes());
            assert!(!rejected.report.nodes[0].native_tcp_candidate);
            assert_eq!(rejected.original, text.as_bytes());
        }
    }
    #[test]
    fn base64_uri_and_ini() {
        let r = inspect(
            STANDARD
                .encode(b"trojan://fixture@example.org:443?sni=example.org")
                .as_bytes(),
        );
        assert!(r.report.nodes[0].native_tcp_candidate);
        let r=inspect(b"[Proxy]\nlabel = Trojan, example.org, 443, password=fixture, sni=example.org\n[Rule]\nFINAL,DIRECT");
        assert!(r.report.nodes[0].native_tcp_candidate);
        assert_eq!(r.original,b"[Proxy]\nlabel = Trojan, example.org, 443, password=fixture, sni=example.org\n[Rule]\nFINAL,DIRECT");
    }
    #[test]
    fn ini_comments_and_builtin_policies_do_not_hide_nodes() {
        let input = b"# exported configuration\n; another comment\n[General]\nloglevel=notify\n[Proxy]\nDIRECT = direct\nBLOCK = reject\nfixture = trojan, example.org, 443, password=fixture\n[Rule]\nFINAL,DIRECT";
        let r = inspect(input);
        assert!(r.report.parsed, "{:?}", r.report.error);
        assert_eq!(r.report.format, "ini");
        assert_eq!(r.report.nodes.len(), 1);
        assert!(r.report.nodes[0].native_tcp_candidate);
        assert_eq!(r.original, input);
    }
    #[test]
    fn ini_string_credentials_and_alias_collisions() {
        let r = inspect(b"[Proxy]\nfixture = trojan, example.org, 443, password=true");
        assert_eq!(r.originals[0]["password"], "true");
        assert!(r.report.nodes[0].native_tcp_candidate);
        let r = inspect(b"[Proxy]\nfixture = trojan, example.org, 443, password=x, tls-host=example.org, sni=other.example");
        assert!(!r.report.parsed);
        assert_eq!(r.report.error, Some("DuplicateIniParameter"));
    }
    #[test]
    fn duplicate_keys_and_remote_tags_fail() {
        for value in [
            "proxies: []\nproxies: []",
            "proxies: !include https://example.org/secret",
            "a: &a [*a]\nproxies: *a",
        ] {
            assert!(!inspect(value.as_bytes()).report.parsed);
        }
    }
    #[test]
    fn unsupported_transport_and_bool_rejected() {
        let r=inspect(br#"{"proxies":[{"type":"trojan","server":"example.org","port":443,"password":"s","network":"ws"},{"type":"trojan","server":"example.org","port":443,"password":"s","skip-cert-verify":"false"}]}"#);
        assert!(r.report.nodes.iter().all(|n| !n.native_tcp_candidate));
    }
    #[test]
    fn unsupported_tls_policy_is_explicit_and_preserved() {
        let input = br#"{"proxies":[{"type":"trojan","server":"example.org","port":443,"password":"x","skip-cert-verify":true},{"type":"trojan","server":"example.org","port":443,"password":"x","tfo":true}]}"#;
        let r = inspect(input);
        assert_eq!(
            r.report.nodes[0].diagnostic,
            "CertificateVerificationDisabledUnsupported"
        );
        assert_eq!(r.report.nodes[1].diagnostic, "TcpFastOpenNotImplemented");
        assert!(r.tcp_candidates.iter().all(Option::is_none));
        assert_eq!(r.original, input);
        assert_eq!(r.originals[0]["skip-cert-verify"], true);
    }
    #[test]
    fn json_with_resource_urls_is_not_misclassified_as_uri() {
        let r=inspect(br#"{"proxies":[{"type":"http","server":"example.org","port":8080}],"rule-providers":{"example":{"url":"https://example.org/rules"}}}"#);
        assert_eq!(r.report.format, "clash-json");
        assert_eq!(r.report.nodes.len(), 1);
        assert!(r.report.nodes[0].native_tcp_candidate);
    }
}
