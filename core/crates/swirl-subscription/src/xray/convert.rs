//! Lossless, offline protocol projection. The exact original document is the
//! persistence authority; derived fields and execution decisions are rebuilt.
//! Never log archives, raw values, endpoints, or authentication fields.
use super::{
    Diagnostic, InputSource, MAX_JSON_DIAGNOSTICS, MAX_JSON_INPUT, MAX_JSON_NODES, ParsedDocument,
    diagnostic, parse_document_with_source, strict::key_path,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fmt;

/// Expansion is bounded separately from the parser's outbound-object count.
pub const MAX_EXPANDED_NODES: usize = MAX_JSON_NODES;
/// JSON string escaping can expand each source byte by at most six bytes.
pub const MAX_ARCHIVE_BYTES: usize = MAX_JSON_INPUT * 6 + 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Protocol {
    Vless,
    Vmess,
    Trojan,
    Shadowsocks,
    Socks,
    Http,
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ValidationStatus {
    Valid,
    Invalid,
    Unverified,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Transport {
    Tcp,
    WebSocket,
    Grpc,
    Http2,
    HttpUpgrade,
    Xhttp,
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Security {
    None,
    Tls,
    Reality,
    Unknown,
}

/// Source indices refer to the original envelope, never to a renamed tag.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct NodeSource {
    pub outbound_index: usize,
    pub outbound_path: String,
    pub server_index: Option<usize>,
    pub user_index: Option<usize>,
    pub server_path: String,
    pub user_path: Option<String>,
}

#[derive(Clone, PartialEq, Eq)]
pub struct Endpoint {
    pub address: String,
    pub port: u16,
}
impl fmt::Debug for Endpoint {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("Endpoint([redacted])")
    }
}

/// Missing values are not silently defaulted in the retained representation.
/// These views contain secrets. Only their explicitly redacted Debug is public.
#[derive(Clone, PartialEq, Eq)]
pub enum Authentication {
    Vless {
        id: Option<String>,
        encryption: Option<String>,
        flow: Option<String>,
        level: Option<u32>,
        email: Option<String>,
    },
    Vmess {
        id: Option<String>,
        alter_id: Option<u16>,
        security: Option<String>,
        level: Option<u32>,
        email: Option<String>,
    },
    Password {
        password: Option<String>,
        method: Option<String>,
        level: Option<u32>,
        email: Option<String>,
    },
    UserPassword {
        user: Option<String>,
        pass: Option<String>,
        level: Option<u32>,
    },
    None,
    Unknown,
}
impl fmt::Debug for Authentication {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("Authentication([redacted])")
    }
}

pub struct ValidatedOutbound {
    protocol: Protocol,
    endpoint: Option<Endpoint>,
    authentication: Authentication,
    source: NodeSource,
    transport: Transport,
    security: Security,
    validation: ValidationStatus,
    diagnostics: Vec<Diagnostic>,
}
impl ValidatedOutbound {
    pub fn protocol(&self) -> Protocol {
        self.protocol
    }
    pub fn endpoint(&self) -> Option<&Endpoint> {
        self.endpoint.as_ref()
    }
    pub fn authentication(&self) -> &Authentication {
        &self.authentication
    }
    pub fn source(&self) -> &NodeSource {
        &self.source
    }
    pub fn transport(&self) -> Transport {
        self.transport
    }
    pub fn security(&self) -> Security {
        self.security
    }
    pub fn validation(&self) -> ValidationStatus {
        self.validation
    }
    pub fn diagnostics(&self) -> &[Diagnostic] {
        &self.diagnostics
    }
    /// Conversion is not a network test and cannot manufacture network evidence.
    pub fn network_verified(&self) -> bool {
        false
    }
}
impl fmt::Debug for ValidatedOutbound {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ValidatedOutbound")
            .field("protocol", &self.protocol)
            .field("source", &self.source)
            .field("validation", &self.validation)
            .field("diagnostics", &self.diagnostics)
            .finish_non_exhaustive()
    }
}

pub struct ConvertedDocument {
    parsed: ParsedDocument,
    nodes: Vec<ValidatedOutbound>,
}
impl fmt::Debug for ConvertedDocument {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ConvertedDocument")
            .field("source", &self.parsed.source)
            .field("node_count", &self.nodes.len())
            .finish_non_exhaustive()
    }
}

#[derive(Serialize)]
struct Archive<'a> {
    schema: u32,
    source: InputSource,
    raw_json: &'a str,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredArchive {
    schema: u32,
    source: InputSource,
    raw_json: String,
}

impl ConvertedDocument {
    pub fn nodes(&self) -> &[ValidatedOutbound] {
        &self.nodes
    }
    pub fn source(&self) -> InputSource {
        self.parsed.source
    }
    pub fn diagnostics(&self) -> &[Diagnostic] {
        &self.parsed.diagnostics
    }
    /// Exact input, including optional BOM, whitespace, unknowns and number lexemes.
    pub fn raw_json(&self) -> &[u8] {
        self.parsed.raw_json()
    }
    /// Private parsed view. Use raw_json for byte-exact recovery.
    pub fn configuration(&self) -> &Value {
        &self.parsed.configuration
    }
    pub fn raw_outbound(&self, node: usize) -> Option<&Value> {
        self.nodes
            .get(node)
            .map(|n| &self.parsed.outbounds[n.source.outbound_index])
    }
    pub fn stream_settings(&self, node: usize) -> Option<&Value> {
        self.raw_outbound(node)?.get("streamSettings")
    }
    pub fn mux(&self, node: usize) -> Option<&Value> {
        self.raw_outbound(node)?.get("mux")
    }
    /// Explicit secret-bearing persistence operation; not a logging interface.
    pub fn save(&self) -> Result<Vec<u8>, Diagnostic> {
        let raw_json = std::str::from_utf8(self.raw_json())
            .map_err(|_| diagnostic("InvalidUtf8", "", "error"))?;
        serde_json::to_vec(&Archive {
            schema: 1,
            source: self.source(),
            raw_json,
        })
        .map_err(|_| diagnostic("ArchiveSerialization", "", "error"))
    }
    /// Rejects duplicate/unknown archive fields. Re-runs A and B from raw source;
    /// no serialized status, normalized node, diagnostic or flag is trusted.
    pub fn restore(bytes: &[u8]) -> Result<Self, Diagnostic> {
        if bytes.len() > MAX_ARCHIVE_BYTES {
            return Err(diagnostic("ArchiveSize", "", "error"));
        }
        let archive: StoredArchive =
            serde_json::from_slice(bytes).map_err(|_| diagnostic("ArchiveSyntax", "", "error"))?;
        if archive.schema != 1 {
            return Err(diagnostic("ArchiveVersion", "schema", "error"));
        }
        import_document(archive.raw_json.as_bytes(), archive.source)
    }
}

/// Reparse the immutable original rather than trusting A's public mutable views.
pub fn convert_document(parsed: &ParsedDocument) -> Result<ConvertedDocument, Diagnostic> {
    import_document(parsed.raw_json(), parsed.source)
}
pub fn import_document(bytes: &[u8], source: InputSource) -> Result<ConvertedDocument, Diagnostic> {
    let parsed = parse_document_with_source(bytes, source)?;
    let mut nodes = Vec::new();
    let mut diagnostics_used = parsed.diagnostics.len();
    for (outbound_index, outbound) in parsed.outbounds.iter().enumerate() {
        let path = &parsed.outbound_paths[outbound_index];
        let protocol = protocol(outbound["protocol"].as_str().unwrap_or(""));
        let settings = outbound.get("settings").unwrap_or(&Value::Null);
        let base = NodeSource {
            outbound_index,
            outbound_path: path.clone(),
            server_index: None,
            user_index: None,
            server_path: key_path(path, "settings"),
            user_path: None,
        };
        let key = if matches!(protocol, Protocol::Vless | Protocol::Vmess) {
            "vnext"
        } else {
            "servers"
        };
        let flat = settings.get("address").is_some();
        let array = settings.get(key).and_then(Value::as_array);
        if flat && array.is_some() {
            let mut sink = Sink::default();
            sink.error("AmbiguousEndpointForms", &base.server_path);
            append(
                &mut nodes,
                outbound,
                protocol,
                settings,
                None,
                base,
                sink,
                &mut diagnostics_used,
            )?;
            continue;
        }
        if let Some(servers) = array {
            if servers.is_empty() {
                let mut sink = Sink::default();
                sink.error("EmptyServers", &key_path(&base.server_path, key));
                append(
                    &mut nodes,
                    outbound,
                    protocol,
                    settings,
                    None,
                    base,
                    sink,
                    &mut diagnostics_used,
                )?;
            } else {
                for (server_index, server) in servers.iter().enumerate() {
                    let mut loc = base.clone();
                    loc.server_index = Some(server_index);
                    loc.server_path =
                        format!("{}[{server_index}]", key_path(&base.server_path, key));
                    expand_users(
                        &mut nodes,
                        outbound,
                        protocol,
                        server,
                        loc,
                        &mut diagnostics_used,
                    )?;
                }
            }
        } else {
            expand_users(
                &mut nodes,
                outbound,
                protocol,
                settings,
                base,
                &mut diagnostics_used,
            )?;
        }
    }
    Ok(ConvertedDocument { parsed, nodes })
}

fn protocol(name: &str) -> Protocol {
    match name {
        "vless" => Protocol::Vless,
        "vmess" => Protocol::Vmess,
        "trojan" => Protocol::Trojan,
        "shadowsocks" => Protocol::Shadowsocks,
        "socks" => Protocol::Socks,
        "http" => Protocol::Http,
        _ => Protocol::Unknown,
    }
}
fn transport(outbound: &Value) -> Transport {
    match outbound
        .pointer("/streamSettings/network")
        .and_then(Value::as_str)
        .unwrap_or("tcp")
    {
        "tcp" | "raw" => Transport::Tcp,
        "ws" => Transport::WebSocket,
        "grpc" | "gun" => Transport::Grpc,
        "http" | "h2" => Transport::Http2,
        "httpupgrade" => Transport::HttpUpgrade,
        "xhttp" | "splithttp" => Transport::Xhttp,
        _ => Transport::Unknown,
    }
}
fn security(outbound: &Value) -> Security {
    match outbound
        .pointer("/streamSettings/security")
        .and_then(Value::as_str)
        .unwrap_or("none")
    {
        "" | "none" => Security::None,
        "tls" => Security::Tls,
        "reality" => Security::Reality,
        _ => Security::Unknown,
    }
}

#[derive(Default)]
struct Sink {
    issues: Vec<Diagnostic>,
    unverified: bool,
    overflow: bool,
}
impl Sink {
    fn issue(&mut self, code: &str, path: &str, severity: &str) {
        if self.issues.len() == MAX_JSON_DIAGNOSTICS {
            self.overflow = true;
            return;
        }
        self.issues.push(diagnostic(code, path, severity));
    }
    fn error(&mut self, code: &str, path: &str) {
        self.issue(code, path, "error");
    }
    fn unsupported(&mut self, code: &str, path: &str) {
        self.issue(code, path, "unsupported");
    }
    fn unknown(&mut self, code: &str, path: &str) {
        self.unverified = true;
        self.unsupported(code, path);
    }
    fn status(&self) -> ValidationStatus {
        if self.issues.iter().any(|d| d.severity == "error") {
            ValidationStatus::Invalid
        } else if self.unverified {
            ValidationStatus::Unverified
        } else {
            ValidationStatus::Valid
        }
    }
}

fn expand_users(
    nodes: &mut Vec<ValidatedOutbound>,
    outbound: &Value,
    protocol: Protocol,
    server: &Value,
    loc: NodeSource,
    used: &mut usize,
) -> Result<(), Diagnostic> {
    let account_array = matches!(
        protocol,
        Protocol::Vless | Protocol::Vmess | Protocol::Socks | Protocol::Http
    );
    if account_array
        && let Some(users) = server.get("users").and_then(Value::as_array)
        && !users.is_empty()
    {
        // Every server retains only its own users; no cross-server Cartesian product.
        for (user_index, user) in users.iter().enumerate() {
            let mut source = loc.clone();
            source.user_index = Some(user_index);
            source.user_path = Some(format!(
                "{}[{user_index}]",
                key_path(&loc.server_path, "users")
            ));
            append(
                nodes,
                outbound,
                protocol,
                server,
                Some(user),
                source,
                Sink::default(),
                used,
            )?;
        }
    } else {
        let mut sink = Sink::default();
        let flat_uuid =
            matches!(protocol, Protocol::Vless | Protocol::Vmess) && loc.server_index.is_none();
        if matches!(protocol, Protocol::Vless | Protocol::Vmess) && !flat_uuid {
            sink.error("MissingUsers", &key_path(&loc.server_path, "users"));
        }
        let account = if flat_uuid { Some(server) } else { None };
        append(nodes, outbound, protocol, server, account, loc, sink, used)?;
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn append(
    nodes: &mut Vec<ValidatedOutbound>,
    outbound: &Value,
    protocol: Protocol,
    server: &Value,
    user: Option<&Value>,
    source: NodeSource,
    mut sink: Sink,
    used: &mut usize,
) -> Result<(), Diagnostic> {
    if nodes.len() == MAX_EXPANDED_NODES {
        return Err(diagnostic("ExpandedNodeLimit", "", "error"));
    }
    let endpoint = endpoint(server, &source.server_path, &mut sink);
    let authentication = validate_protocol(outbound, protocol, server, user, &source, &mut sink);
    let validation = sink.status();
    if sink.overflow || sink.issues.len() > MAX_JSON_DIAGNOSTICS - *used {
        return Err(diagnostic("DiagnosticLimit", "", "error"));
    }
    *used += sink.issues.len();
    nodes.push(ValidatedOutbound {
        protocol,
        endpoint,
        authentication,
        source,
        transport: transport(outbound),
        security: security(outbound),
        validation,
        diagnostics: sink.issues,
    });
    Ok(())
}

fn string(value: &Value, key: &str) -> Option<String> {
    value.get(key).and_then(Value::as_str).map(str::to_owned)
}
fn level(value: &Value) -> Option<u32> {
    value
        .get("level")
        .and_then(Value::as_u64)
        .and_then(|v| u32::try_from(v).ok())
}
fn endpoint(value: &Value, path: &str, sink: &mut Sink) -> Option<Endpoint> {
    let address = value.get("address").and_then(Value::as_str);
    let port = value
        .get("port")
        .and_then(Value::as_u64)
        .and_then(|p| u16::try_from(p).ok());
    if !address.is_some_and(crate::valid_host) {
        sink.error("InvalidServerAddress", &key_path(path, "address"));
    }
    if !port.is_some_and(|p| p != 0) {
        sink.error("InvalidServerPort", &key_path(path, "port"));
    }
    match (address, port) {
        (Some(address), Some(port)) if crate::valid_host(address) && port != 0 => Some(Endpoint {
            address: address.into(),
            port,
        }),
        _ => None,
    }
}
fn allow_keys(value: &Value, path: &str, allowed: &[&str], sink: &mut Sink) {
    if let Some(object) = value.as_object() {
        for key in object.keys() {
            if !allowed.contains(&key.as_str()) {
                sink.unknown("UnmappedFieldPreserved", &key_path(path, key));
            }
            if sink.overflow {
                break;
            }
        }
    }
}
fn validate_id(value: &Value, path: &str, sink: &mut Sink) {
    let id = value.get("id").and_then(Value::as_str);
    match id {
        Some(id) if crate::uuid_bytes(id).is_some() => (),
        // Xray accepts short custom IDs via UUIDv5. Preserve, do not invent a
        // UUID or claim that a V2Ray producer necessarily accepts the same ID.
        Some(id) if !id.is_empty() && id.len() < 30 => {
            sink.unknown("CustomIdMappingUnsupported", &key_path(path, "id"))
        }
        _ => sink.error("InvalidUuid", &key_path(path, "id")),
    }
}
fn validate_protocol(
    outbound: &Value,
    protocol: Protocol,
    server: &Value,
    user: Option<&Value>,
    source: &NodeSource,
    sink: &mut Sink,
) -> Authentication {
    let path = source.user_path.as_deref().unwrap_or(&source.server_path);
    let user = user.unwrap_or(&Value::Null);
    let settings_path = key_path(&source.outbound_path, "settings");
    allow_keys(
        outbound,
        &source.outbound_path,
        &["protocol", "tag", "settings", "streamSettings", "mux"],
        sink,
    );
    match protocol {
        Protocol::Vless | Protocol::Vmess => {
            let fields: &[&str] = if protocol == Protocol::Vless {
                &["id", "encryption", "flow", "level", "email"]
            } else {
                &["id", "alterId", "security", "level", "email"]
            };
            if source.server_index.is_some() {
                allow_keys(&outbound["settings"], &settings_path, &["vnext"], sink);
                allow_keys(
                    server,
                    &source.server_path,
                    &["address", "port", "users"],
                    sink,
                );
                allow_keys(user, path, fields, sink);
            } else {
                let mut flat = fields.to_vec();
                flat.extend(["address", "port"]);
                allow_keys(server, &source.server_path, &flat, sink);
            }
            validate_id(user, path, sink);
            if level(user).is_some_and(|v| v != 0) {
                sink.unsupported("UserLevelPolicyUnsupported", &key_path(path, "level"));
            }
            if protocol == Protocol::Vless {
                match user.get("encryption").and_then(Value::as_str) {
                    Some("none") => (),
                    Some("") | None => {
                        sink.error("MissingVlessEncryption", &key_path(path, "encryption"))
                    }
                    _ => sink.unknown("VlessEncryptionUnsupported", &key_path(path, "encryption")),
                }
                Authentication::Vless {
                    id: string(user, "id"),
                    encryption: string(user, "encryption"),
                    flow: string(user, "flow"),
                    level: level(user),
                    email: string(user, "email"),
                }
            } else {
                if let Some(cipher) = user.get("security").and_then(Value::as_str)
                    && ![
                        "",
                        "auto",
                        "aes-128-gcm",
                        "chacha20-poly1305",
                        "none",
                        "zero",
                    ]
                    .contains(&cipher)
                {
                    sink.unknown("VmessCipherUnsupported", &key_path(path, "security"));
                }
                let alter_id = user
                    .get("alterId")
                    .and_then(Value::as_u64)
                    .and_then(|n| u16::try_from(n).ok());
                if alter_id.is_some_and(|n| n != 0) {
                    sink.unsupported("VmessLegacyAlterIdUnsupported", &key_path(path, "alterId"));
                }
                sink.unsupported(
                    "VmessNativeOutboundUnavailable",
                    &key_path(&source.outbound_path, "protocol"),
                );
                Authentication::Vmess {
                    id: string(user, "id"),
                    alter_id,
                    security: string(user, "security"),
                    level: level(user),
                    email: string(user, "email"),
                }
            }
        }
        _ => {
            sink.unknown(
                "ProtocolConversionUnsupported",
                &key_path(&source.outbound_path, "protocol"),
            );
            Authentication::Unknown
        }
    }
}
