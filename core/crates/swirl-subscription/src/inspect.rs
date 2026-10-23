//! Content-based, offline format inspection. Original data is never included in
//! the public report. Only explicitly supported and fully mapped TCP nodes can
//! yield an executable isolated-test outbound; all original fields are retained.
use crate::{Config, Credentials, Limits, Node, ObfsHttp, Outbound, Tls};
#[cfg(test)]
#[path = "inspect_boundaries.rs"]
mod inspect_boundaries;
#[path = "inspect_reality.rs"]
mod inspect_reality;
#[path = "inspect_socks4.rs"]
mod inspect_socks4;
#[path = "inspect_stream.rs"]
mod inspect_stream;
#[path = "inspect_websocket.rs"]
mod inspect_websocket;
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
    /// Preserved non-node sections whose client-specific semantics are not validated.
    pub configuration_sections_unvalidated: usize,
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
        "socks4" => "socks4",
        "socks4a" => "socks4a",
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
fn legacy_ss(encoded: &str, original: &str) -> Result<Value, &'static str> {
    // The legacy format does not follow RFC3986: the decoded password is
    // literal, including '@', '/', '#', and '%'. Only its final authority is
    // split further. Never send the decoded credentials through a URL parser.
    let decoded = String::from_utf8(decode(encoded.as_bytes())?).map_err(|_| "UriEncoding")?;
    let (auth, authority) = decoded.rsplit_once('@').ok_or("SsAuthentication")?;
    let (cipher, password) = auth.split_once(':').ok_or("SsAuthentication")?;
    let (host, port) = authority.rsplit_once(':').ok_or("UriPort")?;
    let host = if let Some(host) = host.strip_prefix('[') {
        host.strip_suffix(']')
            .ok_or("UriHost")?
            .parse::<std::net::Ipv6Addr>()
            .map_err(|_| "UriHost")?
            .to_string()
    } else {
        host.to_owned()
    };
    let port = port.parse::<u16>().map_err(|_| "UriPort")?;
    Ok(
        json!({"type":"ss","server":host,"port":port,"cipher":cipher,"password":password,"raw-uri":original}),
    )
}
fn ss_percent(value: &str) -> Result<String, &'static str> {
    let bytes = value.as_bytes();
    for (i, byte) in bytes.iter().enumerate() {
        if *byte == b'%'
            && bytes
                .get(i + 1..i + 3)
                .is_none_or(|pair| !pair.iter().all(u8::is_ascii_hexdigit))
        {
            return Err("InvalidUriEncoding");
        }
    }
    percent(value)
}
fn uri(line: &str) -> Result<Value, &'static str> {
    if line.starts_with("hysteria2://") || line.starts_with("hy2://") {
        return crate::hysteria2::parse_uri(line);
    }
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
    if let Some(rest) = line.strip_prefix("ss://") {
        let main = rest.split('#').next().unwrap_or(rest);
        if !main.contains('@') {
            return legacy_ss(main, line);
        }
    }
    let u = url::Url::parse(line).map_err(|_| "UriSyntax")?;
    if matches!(u.scheme(), "socks4" | "socks4a") && !matches!(u.path(), "" | "/") {
        return Err("Socks4UriPath");
    }
    if u.scheme() == "vless" {
        // The official sharing syntax has a UUID authority and query-based
        // transport paths: https://github.com/XTLS/Xray-core/discussions/716
        // Do not discard an extra password or URL path before native mapping.
        if u.password().is_some_and(|password| !password.is_empty()) {
            return Err("VlessUriPassword");
        }
        // url::Url shortens dot segments before exposing path(). Inspect the
        // original path so /private/.. and encoded dots cannot become a neutral
        // slash and erase a source requirement before candidate validation.
        let authority_and_path = line.split_once("://").ok_or("UriSyntax")?.1;
        let before_query = authority_and_path.split(['?', '#']).next().unwrap_or("");
        let original_path = before_query
            .find('/')
            .map_or("", |start| &before_query[start..]);
        if !matches!(original_path, "" | "/") {
            return Err("VlessUriPath");
        }
    }
    // URL serialization brackets IPv6 addresses; the typed IR expects an IP
    // literal, not an authority. Keep the exact URI in raw-uri for preservation.
    let host = match u.host().ok_or("UriHost")? {
        url::Host::Domain(host) => host.to_owned(),
        url::Host::Ipv4(address) => address.to_string(),
        url::Host::Ipv6(address) => address.to_string(),
    };
    let mut n = json!({"type":protocol(u.scheme()),"server":host,"port":u.port().or_else(||if u.scheme()=="https"{Some(443)}else{None}).ok_or("UriPort")?,"raw-uri":line});
    match n["type"].as_str().unwrap_or("") {
        "ss" => {
            let (cipher, password) = if let Some(pass) = u.password() {
                (ss_percent(u.username())?, ss_percent(pass)?)
            } else {
                let auth = String::from_utf8(decode(ss_percent(u.username())?.as_bytes())?)
                    .map_err(|_| "UriEncoding")?;
                let (cipher, password) = auth.split_once(':').ok_or("SsAuthentication")?;
                (cipher.to_owned(), password.to_owned())
            };
            n["cipher"] = cipher.into();
            n["password"] = password.into();
        }
        "trojan" | "anytls" => n["password"] = percent(u.username())?.into(),
        "vless" => n["uuid"] = percent(u.username())?.into(),
        "tuic" => {
            n["uuid"] = percent(u.username())?.into();
            if let Some(password) = u.password() {
                n["password"] = percent(password)?.into();
            }
        }
        _ => {
            n["username"] = percent(u.username())?.into();
            if let Some(pass) = u.password() {
                n["password"] = percent(pass)?.into();
            }
        }
    }
    if matches!(u.scheme(), "socks4" | "socks4a") {
        // Proxy URI query extensions have no mapped SOCKS4 semantics. Retain
        // the original and report them instead of reusing another protocol's
        // authentication, TLS, or transport query aliases.
        if u.query().is_some_and(|query| !query.is_empty()) {
            n["unmapped-socks4-query"] = true.into();
        }
        return Ok(n);
    }
    if matches!(u.scheme(), "https" | "socks5-tls") {
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
        let (key, aliases): (&str, &[&str]) = match key.as_ref() {
            "type" => ("network", &["type", "network"]),
            "network" => ("network", &["type", "network"]),
            "sni" => ("sni", &["sni", "peer"]),
            "peer" => ("sni", &["sni", "peer"]),
            "allowInsecure" | "insecure" | "skip-cert-verify" => (
                "skip-cert-verify",
                &["allowInsecure", "insecure", "skip-cert-verify"],
            ),
            _ => (key.as_ref(), &[]),
        };
        let value = if matches!(key, "skip-cert-verify" | "udp") {
            match value.as_ref() {
                "1" | "true" => Value::Bool(true),
                "0" | "false" => Value::Bool(false),
                _ => return Err("InvalidUriBoolean"),
            }
        } else if key == "alpn" {
            // The sharing-link format encodes an ordered comma-separated list.
            // Keep raw-uri unchanged; never drop empty entries or trim a token.
            let protocols: Vec<_> = value.split(',').collect();
            if protocols.len() > 16
                || protocols.iter().any(|protocol| {
                    protocol.is_empty()
                        || protocol.len() > 255
                        || !protocol.bytes().all(|byte| byte.is_ascii_graphic())
                })
            {
                return Err("InvalidUriAlpn");
            }
            json!(protocols)
        } else {
            Value::String(value.into_owned())
        };
        if let Some(previous) = n.get(key) {
            // Only distinct, known aliases may share an identical typed value.
            // raw-uri retains both spellings; no authority or credential field
            // can be overwritten, and repeated source keys still fail above.
            if aliases
                .iter()
                .filter(|alias| seen.contains(**alias))
                .count()
                > 1
                && previous == &value
            {
                continue;
            }
            return Err("ConflictingUriParameter");
        }
        n[key] = value;
    }
    // v2rayN explicitly exports headerType=none for RAW/TCP sharing URIs:
    // https://github.com/2dust/v2rayN/blob/66dd7da6e69b3bcad51115d1c7d5e017b7ef0dd0/v2rayN/ServiceLib/Handler/Fmt/BaseFmt.cs
    // Independently map that declared neutral option only at this URI boundary.
    // raw-uri keeps its exact spelling; other headers and their extra fields
    // stay present for strict capability rejection, including on non-TCP nodes.
    if n["type"] == "vless"
        && n["security"] == "reality"
        && n.get("network")
            .is_none_or(|value| value.as_str() == Some("tcp"))
        && n.get("headerType").and_then(Value::as_str) == Some("none")
    {
        n.as_object_mut().expect("URI node").remove("headerType");
    }
    Ok(n)
}
fn clean_ini(text: &str) -> String {
    let text = text.trim();
    if text.len() >= 2
        && ((text.starts_with('"') && text.ends_with('"'))
            || (text.starts_with('\'') && text.ends_with('\'')))
    {
        let quote = text.chars().next().unwrap();
        text[1..text.len() - 1]
            .replace(&format!("\\{quote}"), &quote.to_string())
            .replace("\\\\", "\\")
    } else {
        text.to_string()
    }
}
fn csv(text: &str) -> Result<Vec<(String, bool)>, &'static str> {
    let mut out = Vec::new();
    let mut field = String::new();
    let mut quote = None;
    let mut escaped = false;
    let finish = |field: &str| {
        let raw = field.trim();
        (clean_ini(raw), raw.starts_with(['"', '\'']))
    };
    for c in text.chars() {
        if escaped {
            field.push(c);
            escaped = false;
            continue;
        }
        if c == '\\' && quote.is_some() {
            escaped = true;
            field.push(c);
            continue;
        }
        if quote == Some(c) {
            quote = None;
        } else if quote.is_none() && (c == '"' || c == '\'') {
            quote = Some(c);
        } else if c == ',' && quote.is_none() {
            out.push(finish(&field));
            field.clear();
            continue;
        }
        field.push(c);
    }
    if quote.is_some() || escaped {
        return Err("IniQuotation");
    }
    out.push(finish(&field));
    Ok(out)
}
// Only the section envelope is common across these client formats. Rule,
// rewrite and script bodies have different grammars: retain them verbatim and
// report unvalidated semantics instead of pretending to parse them as key=value.
fn ini_section(line: &str) -> Result<Option<String>, &'static str> {
    let Some(rest) = line.strip_prefix('[') else {
        return Ok(None);
    };
    let (name, trailing) = rest.split_once(']').ok_or("IniSectionHeader")?;
    let name = name.trim();
    let trailing = trailing.trim();
    if name.is_empty()
        || name.len() > 128
        || name.contains(['[', ']'])
        || name.chars().any(char::is_control)
        || (!trailing.is_empty() && !trailing.starts_with(['#', ';']))
    {
        return Err("IniSectionHeader");
    }
    Ok(Some(name.to_ascii_lowercase()))
}

fn ini(text: &str) -> Result<Vec<Value>, &'static str> {
    if text
        .chars()
        .any(|c| c.is_control() && !matches!(c, '\t' | '\r' | '\n'))
    {
        return Err("IniControlCharacter");
    }
    let mut section = String::new();
    let mut sections = std::collections::HashSet::new();
    let mut nodes = Vec::new();
    for line in text.lines().map(str::trim) {
        if line.is_empty() || line.starts_with(['#', ';']) {
            continue;
        }
        if let Some(name) = ini_section(line)? {
            if !sections.insert(name.clone()) {
                return Err("DuplicateIniSection");
            }
            if sections.len() > 256 {
                return Err("IniSectionLimit");
            }
            section = name;
            continue;
        }
        if section.is_empty() {
            return Err("IniMissingSection");
        }
        if !matches!(section.as_str(), "proxy" | "server_local") {
            continue;
        }
        let (name, value) = line.split_once('=').ok_or("IniAssignment")?;
        if name.trim().is_empty() {
            return Err("IniAssignment");
        }
        let (fields, quoted): (Vec<_>, Vec<_>) = csv(value)?.into_iter().unzip();
        let qx = section == "server_local";
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
        // Historical Loon Shadowsocks exports append an obfuscation mode and
        // host to the positional cipher/password. Require the complete pair;
        // mixed named credentials must never shift these positions.
        let loon_obfs = !qx
            && fields[0].eq_ignore_ascii_case("shadowsocks")
            && fields.len() >= 7
            && (3..7).all(|index| quoted[index] || !fields[index].contains('='));
        let mut positional = 0;
        let mut seen = std::collections::HashSet::new();
        for (index, field) in fields[start..].iter().enumerate() {
            // Older Loon Trojan exports use key:value after the password.
            // Do not interpret a colon inside the positional password as a key.
            let parameter = if quoted[start + index] {
                None
            } else {
                field.split_once('=').or_else(|| {
                    if qx || kind != "trojan" || n.get("password").is_none() {
                        return None;
                    }
                    field.split_once(':').filter(|(key, _)| {
                        let key = key.trim();
                        !key.is_empty()
                            && key
                                .bytes()
                                .all(|b| b.is_ascii_alphanumeric() || b"-_".contains(&b))
                    })
                })
            };
            if let Some((key, value)) = parameter {
                let key = key.trim();
                let canonical = match key {
                    "encrypt-method" | "method" => "cipher",
                    "tls-host" | "tls-name" => "sni",
                    "udp-relay" => "udp",
                    "over-tls" => "tls",
                    "fast-open" => "tfo",
                    "obfs-name" => "obfs",
                    _ => key,
                };
                if !seen.insert(canonical) || n.get(canonical).is_some() {
                    return Err("DuplicateIniParameter");
                }
                let value = clean_ini(value);
                n[canonical] = if matches!(
                    canonical,
                    "udp" | "tls" | "tfo" | "skip-cert-verify" | "tls-verification"
                ) {
                    match value.to_ascii_lowercase().as_str() {
                        "true" => true.into(),
                        "false" => false.into(),
                        _ => value.into(),
                    }
                } else {
                    value.into()
                };
            } else {
                let key = match (kind, positional) {
                    ("ss", 0) => "cipher",
                    ("ss", 1) | ("trojan", 0) => "password",
                    ("ss", 2) if loon_obfs => "obfs",
                    ("ss", 3) if loon_obfs => "obfs-host",
                    _ => "unmapped-positional",
                };
                if n.get(key).is_some() {
                    return Err("DuplicateIniParameter");
                }
                n[key] = field.as_str().into();
                positional += 1;
            }
        }
        let source_protocol = if qx { name.trim() } else { &fields[0] };
        if kind == "trojan"
            || ["https", "socks5-tls"]
                .iter()
                .any(|p| source_protocol.eq_ignore_ascii_case(p))
        {
            if n.get("tls")
                .is_some_and(|value| value != &Value::Bool(true))
            {
                return Err("ConflictingIniTls");
            }
            n["tls"] = true.into();
        }
        nodes.push(n);
    }
    Ok(nodes)
}
fn parse(bytes: &[u8], depth: usize) -> Result<(&'static str, Value, Vec<Value>), &'static str> {
    if depth > 2 {
        return Err("EncodingDepth");
    }
    let original_text = std::str::from_utf8(bytes)
        .map_err(|_| "EncodingNotUtf8")?
        .trim_start_matches('\u{feff}');
    let text = original_text.trim();
    if text.is_empty() {
        return Err("EmptyDocument");
    }
    if text
        .lines()
        .map(str::trim)
        .find(|line| !line.is_empty() && !line.starts_with(['#', ';']))
        .is_some_and(|line| line.starts_with('['))
        && text.lines().any(|line| {
            ini_section(line.trim())
                .ok()
                .flatten()
                .is_some_and(|name| matches!(name.as_str(), "proxy" | "server_local"))
        })
    {
        return Ok(("ini", Value::String(text.to_string()), ini(original_text)?));
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
fn endpoint_port(raw: &Value) -> Result<u16, &'static str> {
    let parse = |value: &Value| {
        value
            .as_u64()
            .or_else(|| value.as_str().and_then(|text| text.parse().ok()))
            .and_then(|port| u16::try_from(port).ok())
            .filter(|port| *port != 0)
            .ok_or("NodeParameters")
    };
    // Validate both supplied aliases, including explicit null, before choosing.
    // Source types remain in Inspection; numeric strings retain prior support.
    let port = raw.get("port").map(parse).transpose()?;
    let server_port = raw.get("server_port").map(parse).transpose()?;
    match (port, server_port) {
        (Some(a), Some(b)) if a != b => Err("ConflictingServerPort"),
        (Some(port), _) | (_, Some(port)) => Ok(port),
        (None, None) => Err("NodeParameters"),
    }
}
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
    if ![
        "aes-128-gcm",
        "aes-256-gcm",
        "chacha20-ietf-poly1305",
        "2022-blake3-aes-128-gcm",
        "2022-blake3-aes-256-gcm",
    ]
    .contains(&cipher)
    {
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
    let port = endpoint_port(raw)?;
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
        smart_routing: false,
        selectors: vec![],
        china_rules_directory: None,
        dns: Default::default(),
        inbound_auth: None,
        limits: Limits::default(),
    };
    config.validate()?;
    Ok(outbound)
}
fn capability(raw: &Value, index: usize, family: &str) -> (NodeCapability, Option<Outbound>) {
    let source_protocol = raw
        .get("type")
        .or_else(|| raw.get("protocol"))
        .and_then(Value::as_str)
        .unwrap_or("");
    let kind = protocol(source_protocol);
    let implicit_tls = kind == "trojan"
        || source_protocol.eq_ignore_ascii_case("socks5-tls")
        || source_protocol.eq_ignore_ascii_case("https");
    if matches!(kind, "socks4" | "socks4a")
        || (raw.get("type").and_then(Value::as_str) == Some("socks")
            && matches!(raw.get("version").and_then(Value::as_str), Some("4" | "4a")))
    {
        return inspect_socks4::inspect(raw, index, family);
    }
    let transport_raw = raw
        .get("network")
        .or_else(|| raw.pointer("/transport/type"))
        .map_or("tcp", |value| value.as_str().unwrap_or("unknown"));
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
    if matches!(kind, "vless" | "trojan") && inspect_stream::declared(raw) {
        return inspect_stream::inspect(raw, index, family);
    }
    if kind == "vless" && inspect_reality::declared(raw) {
        return inspect_reality::inspect(raw, index, family);
    }
    if transport == "ws" && matches!(kind, "vless" | "trojan") {
        return inspect_websocket::inspect(raw, index, family);
    }
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
    let tls_enabled = implicit_tls
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
    let native = match kind {
        "vmess" => Some(crate::vmess::from_raw(raw)),
        "hysteria2" | "tuic"
            if family == "sing-box-json" || raw.get("_swirl-source-format").is_some() =>
        {
            Some(crate::singbox_quic::outbound(raw))
        }
        "hysteria2" => Some(crate::hysteria2::from_raw(raw).map(Outbound::Hysteria2)),
        "tuic" => Some(crate::Tuic::from_raw(raw).map(Outbound::Tuic)),
        _ => None,
    };
    if let Some(result) = native {
        match result {
            Ok(outbound) => {
                candidate = Some(outbound);
                diagnostic = "TcpCandidateNotYetVerified";
            }
            Err(code) => diagnostic = code,
        }
    }
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
        let port = endpoint_port(raw);
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
        let conflicting_alpn = raw
            .get("alpn")
            .zip(raw.pointer("/tls/alpn"))
            .is_some_and(|(outer, inner)| outer != inner);
        // Trojan authenticates with its password hash, not a username. An
        // explicit empty string has no authentication meaning; preserve its
        // source spelling but reject every other value instead of dropping it.
        let unsupported_trojan_username = kind == "trojan"
            && raw
                .get("username")
                .is_some_and(|value| value.as_str() != Some(""));
        let tls_invalid = tls_obj.is_some_and(|v| !v.is_boolean() && !v.is_object())
            || (implicit_tls && (declared_tls == Some(false) || security == Some("none")))
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
        } else if let Err(error) = port {
            error
        } else if conflicting_alpn {
            "ConflictingAlpn"
        } else if unsupported_trojan_username {
            "TrojanUsernameUnsupported"
        } else if kind == "socks5" && udp && tls_enabled {
            "Socks5UdpTlsUnsupported"
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
            && !conflicting_alpn
            && !unsupported_trojan_username
            && !skip
            && !reality
            && transport == "tcp"
            && family != "xray-v2ray-json"
            && let Ok(port) = port
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
                    // Clash's omitted/empty SNI both use the endpoint name;
                    // aliases and source types were checked above. Retaining
                    // an empty source string must not break saved Qt nodes.
                    .filter(|name| !name.is_empty())
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
                    port,
                    uuid: raw.get("uuid").and_then(Value::as_str).unwrap_or("").into(),
                    tls,
                    websocket: None,
                    reality: None,
                    flow: None,
                    transport: None,
                    udp,
                }),
                "trojan" => tls.map(|tls| Outbound::Trojan {
                    host,
                    port,
                    password,
                    tls,
                    websocket: None,
                    transport: None,
                    udp,
                }),
                "http" => Some(Outbound::HttpConnect {
                    host,
                    port,
                    auth,
                    tls,
                }),
                _ => Some(Outbound::Socks5 {
                    host,
                    port,
                    auth,
                    tls,
                    udp,
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
                    smart_routing: false,
                    selectors: Vec::new(),
                    china_rules_directory: None,
                    dns: Default::default(),
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
    let (transport, udp, unrecognized) = match &candidate {
        Some(Outbound::Hysteria2(config)) => ("quic", config.udp, 0),
        Some(Outbound::Tuic(config)) => ("quic", config.udp, 0),
        _ => (transport, udp, unrecognized),
    };
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
            native_udp_supported: (["ss", "socks5", "vless", "trojan"].contains(&kind)
                && udp
                && candidate.is_some())
                || matches!(&candidate, Some(Outbound::Hysteria2(config)) if config.udp)
                || matches!(&candidate, Some(Outbound::Tuic(config)) if config.udp),
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
        configuration_sections_unvalidated: 0,
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
    report.full_configuration_sections_preserved = if let Some(object) = document.as_object() {
        object
            .keys()
            .filter(|k| !matches!(k.as_str(), "proxies" | "outbounds"))
            .count()
    } else {
        // This also covers Base64-wrapped INI. URI lists have no section headers.
        document.as_str().map_or(0, |text| {
            text.lines()
                .filter_map(|line| ini_section(line.trim()).ok().flatten())
                .filter(|name| !matches!(name.as_str(), "proxy" | "server_local"))
                .count()
        })
    };
    report.configuration_sections_unvalidated = report.full_configuration_sections_preserved;
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
    fn ini_rejects_malformed_structure_after_valid_nodes() {
        let prefix = "[Proxy]\nfixture = trojan, example.org, 443, SECRET_PASSWORD\n";
        for suffix in [
            "[Rule",
            "[]",
            "[[Rule]]",
            "[Rule] SECRET_SUFFIX",
            "[Rule]\nSECRET\0TAIL",
            "[Rule]\n[rule]",
        ] {
            let input = format!("{prefix}{suffix}");
            for bytes in [
                input.as_bytes().to_vec(),
                STANDARD.encode(input.as_bytes()).into_bytes(),
            ] {
                let result = inspect(&bytes);
                assert!(!result.report.parsed, "accepted malformed INI structure");
                assert!(result.tcp_candidates.is_empty());
                assert_eq!(result.original, bytes);
                assert!(
                    !serde_json::to_string(&result.report)
                        .unwrap()
                        .contains("SECRET")
                );
            }
        }
    }

    #[test]
    fn ini_section_spacing_comments_and_unknown_bodies_are_preserved() {
        let input = "\u{feff}; heading\r\n[ Proxy ] # nodes\r\nfixture = trojan, example.org, 443, secret\r\n[General]\r\ndns-server = system\r\n[Rule]\r\nFINAL,fixture\r\n[Future]\r\nopaque SECRET syntax preserved\r\n";
        for bytes in [
            input.as_bytes().to_vec(),
            STANDARD.encode(input.as_bytes()).into_bytes(),
        ] {
            let result = inspect(&bytes);
            assert!(result.report.parsed);
            assert_eq!(result.report.nodes.len(), 1);
            assert!(result.report.nodes[0].native_tcp_candidate);
            assert_eq!(result.report.full_configuration_sections_preserved, 3);
            let report = serde_json::to_value(&result.report).unwrap();
            assert_eq!(report["configuration_sections_unvalidated"], 3);
            assert!(!result.report.complete_configuration_execution_supported);
            assert_eq!(result.original, bytes);
            assert!(
                result
                    .document
                    .as_str()
                    .unwrap()
                    .contains("opaque SECRET syntax preserved")
            );
            assert!(!report.to_string().contains("SECRET"));
        }
    }

    #[test]
    fn ini_control_validation_precedes_whitespace_normalization() {
        let node = "[Proxy]\nfixture = trojan, example.org, 443, secret\n";
        for control in ['\u{000b}', '\u{000c}', '\u{0085}', '\u{007f}'] {
            for input in [format!("{control}{node}"), format!("{node}{control}")] {
                for bytes in [
                    input.as_bytes().to_vec(),
                    STANDARD.encode(&input).into_bytes(),
                ] {
                    let result = inspect(&bytes);
                    assert!(!result.report.parsed);
                    assert!(result.tcp_candidates.is_empty());
                    assert_eq!(result.original, bytes);
                }
            }
        }
    }

    #[test]
    fn ini_duplicate_proxy_sections_and_empty_node_names_fail_closed() {
        for text in [
            "[Proxy]\nfixture = trojan, example.org, 443, secret\n[proxy]\nother = trojan, other.example, 443, secret",
            "[Proxy]\n = trojan, example.org, 443, secret",
        ] {
            let result = inspect(text.as_bytes());
            assert!(!result.report.parsed);
            assert!(result.tcp_candidates.is_empty());
        }
    }
    #[test]
    fn vless_base_tls_maps_but_flow_and_reality_never_downgrade() {
        let base = "vless://00112233-4455-6677-8899-aabbccddeeff@example.org:443?security=tls&encryption=none";
        let r = inspect(base.as_bytes());
        assert!(r.report.nodes[0].native_tcp_candidate);
        assert!(!r.report.nodes[0].native_udp_supported);
        for suffix in [
            "&flow=xtls-rprx-vision",
            "&type=grpc",
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
    fn equivalent_distinct_uri_aliases_preserve_originals_and_typed_values() {
        for (first, second, key, expected) in [
            (
                "peer=local%68ost",
                "sni=localhost",
                "sni",
                json!("localhost"),
            ),
            ("type=t%63p", "network=tcp", "network", json!("tcp")),
            (
                "allowInsecure=0",
                "skip-cert-verify=false",
                "skip-cert-verify",
                json!(false),
            ),
        ] {
            for query in [format!("{first}&{second}"), format!("{second}&{first}")] {
                let uri = format!("trojan://fixture@example.org:443?{query}");
                for input in [uri.clone(), STANDARD.encode(uri.as_bytes())] {
                    let result = inspect(input.as_bytes());
                    assert!(result.report.parsed, "{:?}", result.report.error);
                    assert!(result.report.nodes[0].native_tcp_candidate);
                    assert!(!result.report.nodes[0].real_network_verified);
                    assert_eq!(result.originals[0][key], expected);
                    assert_eq!(result.originals[0]["raw-uri"], uri);
                    assert_eq!(result.original, input.as_bytes());
                    let report = serde_json::to_string(&result.report).unwrap();
                    assert!(!report.contains("fixture"));
                    assert!(!report.contains("example.org"));
                }
            }
        }
    }
    #[test]
    fn ini_implicit_tls_cannot_be_downgraded() {
        for protocol in ["https", "socks5-tls", "trojan"] {
            for option in ["", ",tls=true", ",over-tls=TRUE"] {
                let source = format!(
                    "[Proxy]\nfixture = {protocol},example.org,443,password=synthetic{option}"
                );
                let nodes = ini(&source).unwrap();
                assert_eq!(nodes[0]["tls"], true);
            }
            for option in ["tls=false", "over-tls=false", "tls=unknown"] {
                let source = format!(
                    "[Proxy]\nfixture = {protocol},example.org,443,password=synthetic,{option}"
                );
                assert!(ini(&source).is_err());
            }
        }
    }
    #[test]
    fn quoted_ini_credentials_preserve_spaces_and_escaped_quotes() {
        for field in [
            r#""  fixture=with,comma:and\"quote\\slash  ""#,
            r#"password="  fixture=with,comma:and\"quote\\slash  ""#,
        ] {
            let source = format!("[Proxy]\nfixture = trojan,example.org,443,{field}");
            let nodes = ini(&source).unwrap();
            assert_eq!(
                nodes[0]["password"],
                "  fixture=with,comma:and\"quote\\slash  "
            );
        }
    }
    #[test]
    fn uri_insecure_alias_is_typed_and_never_overwrites() {
        for query in [
            "insecure=0&allowInsecure=false&skip-cert-verify=0",
            "skip-cert-verify=false&insecure=false&allowInsecure=0",
        ] {
            let value = uri(&format!("trojan://synthetic@example.org:443?{query}")).unwrap();
            assert_eq!(value["skip-cert-verify"], Value::Bool(false));
            assert!(value.get("insecure").is_none());
        }
        for query in [
            "insecure=off",
            "insecure=FALSE",
            "insecure=0&insecure=0",
            "insecure=0&allowInsecure=1",
            "skip-cert-verify=true&insecure=false",
        ] {
            assert!(uri(&format!("trojan://synthetic@example.org:443?{query}")).is_err());
        }
    }
    #[test]
    fn quoted_ini_password_delimiters_remain_credentials() {
        let nodes=ini("[Proxy]\nfixture = trojan,example.org,443,\"secret:with,comma=plus+percent%25\",tls-name:tls.example.org,skip-cert-verify:false").unwrap();
        assert_eq!(nodes[0]["password"], "secret:with,comma=plus+percent%25");
        assert_eq!(nodes[0]["sni"], "tls.example.org");
        assert_eq!(nodes[0]["skip-cert-verify"], false);
        assert!(ini("[Proxy]\nfixture = trojan,example.org,443,\"secret=a\",password=b").is_err());
        let nodes=ini("[Proxy]\nfixture = Shadowsocks,example.org,443,aes-128-gcm,\"secret=a,b:c\",http,obfs.example").unwrap();
        assert_eq!(nodes[0]["password"], "secret=a,b:c");
        assert_eq!(nodes[0]["obfs"], "http");
    }
    #[test]
    fn unequal_aliases_repeated_keys_and_invalid_booleans_fail_closed() {
        for (expected, queries) in [
            (
                "ConflictingUriParameter",
                &[
                    "peer=first.example&sni=second.example",
                    "sni=second.example&peer=first.example",
                    "peer=&sni=second.example",
                    "type=tcp&network=ws",
                    "network=ws&type=tcp",
                    "allowInsecure=0&skip-cert-verify=true",
                    "skip-cert-verify=true&allowInsecure=0",
                ][..],
            ),
            (
                "DuplicateUriParameter",
                &[
                    "sni=first.example&sni=first.example",
                    "sni=first.example&%73ni=first.example",
                    "peer=first.example&sni=first.example&peer=first.example",
                    "type=tcp&type=tcp",
                    "allowInsecure=0&allowInsecure=false",
                    "udp=0&udp=false",
                ][..],
            ),
            (
                "InvalidUriBoolean",
                &[
                    "allowInsecure=TRUE&skip-cert-verify=true",
                    "skip-cert-verify=false&allowInsecure=",
                    "allowInsecure=0&skip-cert-verify=no",
                    "udp=TRUE",
                    "udp=2",
                    "udp=",
                ][..],
            ),
        ] {
            for query in queries {
                let input = format!("trojan://fixture@example.org:443?{query}");
                let result = inspect(input.as_bytes());
                assert_eq!(result.report.error, Some(expected));
                assert!(!result.report.parsed);
                assert!(result.tcp_candidates.is_empty());
                assert_eq!(result.original, input.as_bytes());
            }
        }
    }
    #[test]
    fn alias_coalescing_cannot_override_authority_authentication_or_plugin_options() {
        for input in [
            "trojan://fixture@example.org:443?password=fixture",
            "trojan://fixture@example.org:443?server=example.org",
            "trojan://fixture@example.org:443?port=443",
            "trojan://fixture@example.org:443?raw-uri=retained",
            "vless://00112233-4455-6677-8899-aabbccddeeff@example.org:443?uuid=00112233-4455-6677-8899-aabbccddeeff",
            "https://fixture@example.org:8443?tls=true",
            "ss://aes-128-gcm:fixture@example.org:443?cipher=aes-128-gcm",
            "ss://aes-128-gcm:fixture@example.org:443?plugin=obfs-local%3Bobfs%3Dhttp%3Bobfs-host%3Dexample.org&plugin-opts=retained",
            "ss://aes-128-gcm:fixture@example.org:443?plugin-opts=retained&plugin=obfs-local%3Bobfs%3Dhttp%3Bobfs-host%3Dexample.org",
        ] {
            let result = inspect(input.as_bytes());
            assert_eq!(result.report.error, Some("ConflictingUriParameter"));
            assert!(result.tcp_candidates.is_empty());
            assert_eq!(result.original, input.as_bytes());
        }
    }
    #[test]
    fn uri_udp_boolean_mapping_preserves_capability_and_certificate_limits() {
        for (udp, declared) in [("0", false), ("false", false), ("1", true), ("true", true)] {
            let input = format!(
                "trojan://fixture@example.org:443?allowInsecure=0&peer=example.org&sni=example.org&udp={udp}"
            );
            let result = inspect(input.as_bytes());
            assert!(result.report.parsed);
            assert!(result.report.nodes[0].native_tcp_candidate);
            assert_eq!(result.originals[0]["udp"], declared);
            assert_eq!(result.report.nodes[0].udp_declared, declared);
            assert_eq!(result.report.nodes[0].native_udp_supported, declared);
            assert_eq!(result.originals[0]["raw-uri"], input);
            assert_eq!(result.original, input.as_bytes());
            for query in [
                "allowInsecure=1&skip-cert-verify=true",
                "skip-cert-verify=true&allowInsecure=1",
            ] {
                let unsafe_input = input.replace("allowInsecure=0", query);
                let rejected = inspect(unsafe_input.as_bytes());
                assert!(rejected.report.parsed);
                assert_eq!(rejected.originals[0]["skip-cert-verify"], true);
                assert!(!rejected.report.nodes[0].native_tcp_candidate);
                assert!(!rejected.report.nodes[0].native_udp_supported);
                assert_eq!(rejected.report.nodes[0].udp_declared, declared);
                assert_eq!(
                    rejected.report.nodes[0].diagnostic,
                    "CertificateVerificationDisabledUnsupported"
                );
                assert_eq!(rejected.original, unsafe_input.as_bytes());
            }
        }
    }
    #[test]
    fn socks5_udp_capability_requires_plain_standard_transport() {
        for (parameter, enabled) in [("", false), ("?udp=false", false), ("?udp=1", true)] {
            let input = format!("socks5://user:secret@proxy.fixture.test:1080{parameter}");
            let result = inspect(input.as_bytes());
            assert!(result.report.parsed);
            let node = &result.report.nodes[0];
            assert!(node.native_tcp_candidate);
            assert_eq!(node.native_udp_supported, enabled);
            assert!(!node.real_network_verified);
            assert_eq!(result.original, input.as_bytes());
            assert!(
                matches!(result.tcp_candidates[0].as_ref(), Some(Outbound::Socks5 { udp, .. }) if *udp == enabled)
            );
        }
        for input in [
            "socks5-tls://user:secret@proxy.fixture.test:1080?udp=1",
            "socks5://user:secret@proxy.fixture.test:1080?udp=1&security=tls",
        ] {
            let result = inspect(input.as_bytes());
            assert!(result.report.parsed);
            let node = &result.report.nodes[0];
            assert_eq!(node.diagnostic, "Socks5UdpTlsUnsupported");
            assert!(!node.native_tcp_candidate);
            assert!(!node.native_udp_supported);
            assert!(!node.real_network_verified);
            assert!(result.tcp_candidates[0].is_none());
        }
        let tls_uri = "socks5-tls://user:secret@proxy.fixture.test:1080";
        for input in [tls_uri.to_owned(), format!("{tls_uri}?udp=false")] {
            let result = inspect(input.as_bytes());
            assert!(matches!(
                result.tcp_candidates[0].as_ref(),
                Some(Outbound::Socks5 {
                    tls: Some(_),
                    udp: false,
                    ..
                })
            ));
        }
        for input in [
            format!("{tls_uri}?tls=false"),
            format!("{tls_uri}?security=none"),
            "socks5://user:secret@proxy.fixture.test:1080?udp=1&tls=true".into(),
        ] {
            assert!(
                !inspect(input.as_bytes())
                    .report
                    .nodes
                    .first()
                    .is_some_and(|n| n.native_tcp_candidate)
            );
        }
        for extra in [
            "",
            ",\"udp\":false",
            ",\"udp\":true",
            ",\"tls\":false",
            ",\"security\":\"none\"",
        ] {
            let input = format!(
                r#"{{"proxies":[{{"type":"socks5-tls","server":"proxy.fixture.test","port":1080{extra}}}]}}"#
            );
            let result = inspect(input.as_bytes());
            if matches!(extra, "" | ",\"udp\":false") {
                assert!(matches!(
                    result.tcp_candidates[0].as_ref(),
                    Some(Outbound::Socks5 {
                        tls: Some(_),
                        udp: false,
                        ..
                    })
                ));
            } else {
                assert!(!result.report.nodes[0].native_tcp_candidate);
                assert!(!result.report.nodes[0].native_udp_supported);
            }
        }
        for value in ["1", "null", "\"true\""] {
            let document = format!(
                r#"{{"proxies":[{{"type":"socks5","server":"proxy.fixture.test","port":1080,"udp":{value}}}]}}"#
            );
            assert!(!inspect(document.as_bytes()).report.nodes[0].native_tcp_candidate);
        }
    }
    #[test]
    fn ipv6_uri_hosts_are_literals_in_typed_outbounds() {
        let uuid = "00112233-4455-6677-8899-aabbccddeeff";
        let inputs = [
            "ss://YWVzLTEyOC1nY206Zml4dHVyZQ@[2001:db8::1234]:443".to_owned(),
            "ss://aes-128-gcm:fixture%3Apass@[2001:db8::1234]:443".to_owned(),
            "trojan://fixture@[2001:db8::1234]:443?sni=proxy.example".to_owned(),
            format!("vless://{uuid}@[2001:db8::1234]:443?encryption=none"),
            format!("vless://{uuid}@[2001:db8::1234]:443?type=ws&path=%2Fsocket"),
            "socks5://fixture:password@[2001:db8::1234]:1080".to_owned(),
            "http://fixture:password@[2001:db8::1234]:8080".to_owned(),
        ];
        for input in inputs {
            let result = inspect(input.as_bytes());
            assert!(result.report.parsed, "{:?}", result.report.error);
            assert!(result.report.nodes[0].native_tcp_candidate);
            assert!(!result.report.nodes[0].real_network_verified);
            let outbound =
                serde_json::to_value(result.tcp_candidates[0].as_ref().unwrap()).unwrap();
            assert_eq!(outbound["host"], "2001:db8::1234");
            assert_eq!(result.originals[0]["server"], "2001:db8::1234");
            assert_eq!(result.originals[0]["raw-uri"], input);
            assert_eq!(result.original, input.as_bytes());
        }
    }
    #[test]
    fn ipv6_base64_subscription_preserves_ss_authentication_and_unknowns() {
        let password = "fixture:/%40?#+";
        let user = URL_SAFE_NO_PAD.encode(format!("aes-128-gcm:{password}"));
        let input = format!("ss://{user}@[2001:db8::1]:8388#synthetic");
        for engine in [&STANDARD, &STANDARD_NO_PAD, &URL_SAFE, &URL_SAFE_NO_PAD] {
            let wrapped = engine.encode(input.as_bytes());
            let result = inspect(wrapped.as_bytes());
            assert_eq!(result.report.format, "base64");
            assert!(result.report.nodes[0].native_tcp_candidate);
            let outbound =
                serde_json::to_value(result.tcp_candidates[0].as_ref().unwrap()).unwrap();
            assert_eq!(outbound["host"], "2001:db8::1");
            assert_eq!(outbound["password"], password);
            assert_eq!(result.original, wrapped.as_bytes());
            assert_eq!(result.originals[0]["raw-uri"], input);
        }
        let unknown = format!("ss://{user}@[2001:db8::1]:8388?future=retained");
        let result = inspect(unknown.as_bytes());
        assert!(result.report.parsed);
        assert!(!result.report.nodes[0].native_tcp_candidate);
        assert_eq!(result.originals[0]["future"], "retained");
        assert_eq!(result.original, unknown.as_bytes());
    }
    #[test]
    fn legacy_ss_passwords_keep_reserved_characters_and_literal_percent_sequences() {
        for password in ["test/!@#:", "literal%40/%2f?@#:%GG", "space and\t瀵嗛挜@"] {
            for authority in ["example.org:8388", "[2001:db8::2]:8388", "::1:8388"] {
                let decoded = format!("chacha20-ietf-poly1305:{password}@{authority}");
                let uri = format!(
                    "ss://{}#operator@synthetic",
                    STANDARD_NO_PAD.encode(decoded.as_bytes())
                );
                for input in [uri.clone(), URL_SAFE.encode(uri.as_bytes())] {
                    let result = inspect(input.as_bytes());
                    assert!(result.report.parsed, "{:?}", result.report.error);
                    assert!(result.report.nodes[0].native_tcp_candidate);
                    let outbound =
                        serde_json::to_value(result.tcp_candidates[0].as_ref().unwrap()).unwrap();
                    assert_eq!(outbound["password"], password);
                    assert_eq!(outbound["port"], 8388);
                    assert_eq!(outbound["cipher"], "chacha20-ietf-poly1305");
                    let expected_host = authority.rsplit_once(':').unwrap().0;
                    assert_eq!(outbound["host"], expected_host.trim_matches(['[', ']']));
                    assert_eq!(result.originals[0]["raw-uri"], uri);
                    assert_eq!(result.original, input.as_bytes());
                    assert!(
                        !serde_json::to_string(&result.report)
                            .unwrap()
                            .contains(password)
                    );
                }
            }
        }
    }
    #[test]
    fn sip002_percent_encoding_is_distinct_from_legacy_password_text() {
        let legacy = format!(
            "ss://{}",
            STANDARD.encode("aes-128-gcm:%40@example.org:8388")
        );
        let legacy_result = inspect(legacy.as_bytes());
        assert_eq!(legacy_result.originals[0]["password"], "%40");
        let sip = inspect(b"ss://aes-128-gcm:%40@example.org:8388");
        assert!(sip.report.nodes[0].native_tcp_candidate);
        assert_eq!(sip.originals[0]["password"], "@");
        let ambiguous = inspect(b"ss://aes-128-gcm%3Ainjected:fixture@example.org:8388");
        assert!(!ambiguous.report.nodes[0].native_tcp_candidate);
        assert_eq!(ambiguous.originals[0]["cipher"], "aes-128-gcm:injected");
        assert_eq!(ambiguous.originals[0]["password"], "fixture");
        for invalid in ["%", "%0", "%GG", "%FF"] {
            let input = format!("ss://aes-128-gcm:{invalid}@example.org:8388");
            let result = inspect(input.as_bytes());
            assert_eq!(result.report.error, Some("InvalidUriEncoding"));
            assert!(result.tcp_candidates.is_empty());
            assert_eq!(result.original, input.as_bytes());
            let input = format!(
                "ss://{}",
                STANDARD.encode(format!("aes-128-gcm:{invalid}@example.org:8388"))
            );
            let result = inspect(input.as_bytes());
            assert!(result.report.nodes[0].native_tcp_candidate);
            assert_eq!(result.originals[0]["password"], invalid);
        }
    }
    #[test]
    fn sip002_base64_userinfo_can_escape_its_padding() {
        let encoded = STANDARD.encode("aes-128-gcm:f");
        assert!(encoded.ends_with("=="));
        let input = format!("ss://{}@[::1]:8388", encoded.replace('=', "%3D"));
        let result = inspect(input.as_bytes());
        assert!(result.report.nodes[0].native_tcp_candidate);
        assert_eq!(result.originals[0]["password"], "f");
        assert_eq!(result.originals[0]["server"], "::1");
        assert_eq!(result.original, input.as_bytes());
    }
    #[test]
    fn legacy_ss_does_not_discard_authority_options_or_accept_unknown_ciphers() {
        for authority in [
            "example.org:443/extra",
            "example.org:443?plugin=unmapped",
            "[not-an-ip]:443",
            "[::1:443",
            "example.org/path:443",
            "example.org:0",
        ] {
            let input = format!(
                "ss://{}",
                STANDARD.encode(format!("aes-128-gcm:fixture@{authority}"))
            );
            let result = inspect(input.as_bytes());
            assert!(result.tcp_candidates.iter().all(Option::is_none));
            assert_eq!(result.original, input.as_bytes());
        }
        let input = format!(
            "ss://{}",
            STANDARD.encode("unknown-cipher:fixture@example.org:8388")
        );
        let result = inspect(input.as_bytes());
        assert!(result.report.parsed);
        assert!(!result.report.nodes[0].native_tcp_candidate);
        assert_eq!(result.report.nodes[0].diagnostic, "CipherNotImplemented");
        assert_eq!(result.originals[0]["cipher"], "unknown-cipher");
    }
    #[test]
    fn malformed_ipv6_authorities_do_not_become_candidates() {
        for host in [
            "[2001:db8::1",
            "[[2001:db8::1]]",
            "[fe80::1%25eth0]",
            "[not-an-ip]",
        ] {
            let input = format!("ss://YWVzLTEyOC1nY206Zml4dHVyZQ@{host}:443");
            let result = inspect(input.as_bytes());
            assert!(!result.report.parsed);
            assert!(result.tcp_candidates.is_empty());
            assert_eq!(result.original, input.as_bytes());
        }
    }
    #[test]
    fn ini_positional_and_named_authentication_cannot_overwrite_each_other() {
        for declaration in [
            "ss, example.org, 443, cipher=aes-256-gcm, aes-128-gcm, fixture",
            "ss, example.org, 443, encrypt-method=aes-128-gcm, aes-128-gcm, fixture",
            "ss, example.org, 443, aes-128-gcm, password=first, second",
            "ss, example.org, 443, password=first, aes-128-gcm, second",
            "ss, example.org, 443, aes-128-gcm, fixture, method=aes-256-gcm",
            "ss, example.org, 443, aes-128-gcm, first, password=second",
            "trojan, example.org, 443, password=first, second",
            "trojan, example.org, 443, first, password=second",
        ] {
            let input = format!("[Proxy]\nfixture = {declaration}\n");
            let result = inspect(input.as_bytes());
            assert_eq!(result.report.error, Some("DuplicateIniParameter"));
            assert!(!result.report.parsed);
            assert!(result.tcp_candidates.is_empty());
            assert_eq!(result.original, input.as_bytes());
        }
        for declaration in [
            "ss, example.org, 443, aes-128-gcm, fixture",
            "ss, example.org, 443, encrypt-method=aes-128-gcm, password=fixture",
            "trojan, example.org, 443, fixture",
            "trojan, example.org, 443, password=fixture",
        ] {
            let input = format!("[Proxy]\nfixture = {declaration}\n");
            let result = inspect(input.as_bytes());
            assert!(result.report.parsed);
            assert!(result.report.nodes[0].native_tcp_candidate);
            assert_eq!(result.original, input.as_bytes());
        }
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
    fn legacy_loon_trojan_options_preserve_credentials_and_tls_policy() {
        let input = b"[Proxy]\nfixture = trojan, example.org, 443, \"secret:with:colons\", tls-name:tls.example.org, skip-cert-verify:false";
        let r = inspect(input);
        assert!(r.report.parsed);
        assert!(r.report.nodes[0].native_tcp_candidate);
        assert_eq!(r.original, input);
        assert_eq!(r.originals[0]["password"], "secret:with:colons");
        match r.tcp_candidates[0].as_ref().unwrap() {
            Outbound::Trojan { password, tls, .. } => {
                assert_eq!(password, "secret:with:colons");
                assert_eq!(tls.server_name, "tls.example.org");
            }
            _ => panic!("expected native Trojan"),
        }
        for suffix in [
            "skip-cert-verify:true",
            "skip-cert-verify:invalid",
            "future:retained",
        ] {
            let input = format!("[Proxy]\nfixture = trojan, example.org, 443, secret, {suffix}");
            let r = inspect(input.as_bytes());
            assert!(r.report.parsed);
            assert!(!r.report.nodes[0].native_tcp_candidate);
            assert_eq!(r.original, input.as_bytes());
        }
    }
    #[test]
    fn legacy_loon_colon_options_cannot_overwrite_named_parameters() {
        for suffix in [
            "tls-name:first.example, sni=second.example",
            "sni=first.example, tls-name:second.example",
            "skip-cert-verify:false, skip-cert-verify=true",
            "password:replacement",
        ] {
            let input = format!("[Proxy]\nfixture = trojan, example.org, 443, secret, {suffix}");
            let r = inspect(input.as_bytes());
            assert!(!r.report.parsed);
            assert_eq!(r.report.error, Some("DuplicateIniParameter"));
            assert!(r.tcp_candidates.is_empty());
            assert_eq!(r.original, input.as_bytes());
        }
    }
    #[test]
    fn loon_http_obfs_positional_and_named_exports_use_native_ss() {
        for parameters in [
            "aes-128-gcm,\"fixture,with:punctuation\",http,obfs.example",
            "aes-128-gcm,\"fixture,with:punctuation\",obfs-name=http,obfs-host=obfs.example",
        ] {
            let input = format!("[Proxy]\nfixture = Shadowsocks, example.org, 443, {parameters}");
            let r = inspect(input.as_bytes());
            assert!(r.report.parsed);
            assert_eq!(r.original, input.as_bytes());
            assert_eq!(r.originals[0]["raw-ini"], input.lines().nth(1).unwrap());
            assert!(r.report.nodes[0].native_tcp_candidate);
            match r.tcp_candidates[0].as_ref().unwrap() {
                Outbound::Shadowsocks {
                    password,
                    obfs_http: Some(obfs),
                    ..
                } => {
                    assert_eq!(password, "fixture,with:punctuation");
                    assert_eq!(obfs.host, "obfs.example");
                }
                _ => panic!("expected native SS with HTTP obfuscation"),
            }
        }
    }
    #[test]
    fn loon_obfs_unsupported_modes_options_and_incomplete_pairs_never_downgrade() {
        for tail in [
            "http",
            "http,",
            "tls,obfs.example",
            "future,obfs.example",
            "http,obfs.example,future=retained",
            "http,obfs.example,extra-positional",
            "http,obfs.example,fast-open=true",
            "obfs-name=http,obfs-host=obfs.example,obfs-uri=/custom",
        ] {
            let input = format!(
                "[Proxy]\nfixture = Shadowsocks, example.org, 443, aes-128-gcm,fixture,{tail}"
            );
            let r = inspect(input.as_bytes());
            assert_eq!(r.original, input.as_bytes());
            assert!(r.tcp_candidates.iter().all(Option::is_none));
        }
        for tail in [
            "fixture,http,obfs.example,obfs=tls",
            "fixture,http,obfs.example,obfs-name=http",
            "fixture,http,obfs.example,obfs-host=other.example",
            "fixture,obfs-name=http,obfs=tls,obfs-host=obfs.example",
            "password=first,second,http,obfs.example",
        ] {
            let input =
                format!("[Proxy]\nfixture = Shadowsocks, example.org, 443, aes-128-gcm,{tail}");
            let r = inspect(input.as_bytes());
            assert!(!r.report.parsed);
            assert_eq!(r.report.error, Some("DuplicateIniParameter"));
            assert_eq!(r.original, input.as_bytes());
        }
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
        let r=inspect(br#"{"proxies":[{"type":"trojan","server":"example.org","port":443,"password":"s","network":"grpc"},{"type":"trojan","server":"example.org","port":443,"password":"s","skip-cert-verify":"false"}]}"#);
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
