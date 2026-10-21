//! Bounded, offline Xray/V2Ray JSON parsing, without protocol conversion.
//! Only diagnostics and the redacted `Debug` view are safe to publish. Raw
//! source and parsed values can contain credentials and must stay private.
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fmt;

mod schema;
mod strict;

pub const MAX_JSON_INPUT: usize = 4 * 1024 * 1024;
/// Maximum value depth, with the root at depth zero.
pub const MAX_JSON_DEPTH: usize = 32;
pub const MAX_JSON_NODES: usize = 2000;
pub const MAX_JSON_VALUES: usize = 100_000;
pub const MAX_JSON_DIAGNOSTICS: usize = 64;

/// Paths contain recognized field names and numeric array offsets only. Unknown
/// field names and parser excerpts can contain secrets and are never reflected.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Diagnostic {
    pub code: String,
    pub path: String,
    /// error = invalid parameters; unsupported = preserved, cannot execute;
    /// warning/info = semantics retained (e.g. an alias or ignored global log).
    pub severity: String,
    /// One-based syntax location, when available; never a source excerpt.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub line: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub column: Option<usize>,
}

impl fmt::Display for Diagnostic {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{} at {}", self.code, self.path)
    }
}
impl std::error::Error for Diagnostic {}

/// Caller-supplied provenance, deliberately without a filename or subscription
/// URL that could leak credentials. Shared JSON cannot identify its producer.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InputSource {
    #[default]
    Unknown,
    File,
    Clipboard,
    Subscription,
}

fn diagnostic(code: &str, path: &str, severity: &str) -> Diagnostic {
    Diagnostic {
        code: code.into(),
        path: path.into(),
        severity: severity.into(),
        line: None,
        column: None,
    }
}

/// The structural stage has no executable protocol assumptions. Inbound data
/// and globals stay in the exact document and never become client nodes.
pub struct ParsedDocument {
    /// configuration, outbound, or the Swirl-only swirl-outbound-array extension.
    pub input_kind: &'static str,
    pub source: InputSource,
    /// Parsed view, not a byte-exact serialization. Use `raw_json()` when
    /// preserving numeric lexemes, whitespace, key order or the optional BOM.
    pub configuration: Value,
    pub outbounds: Vec<Value>,
    /// Source paths aligned with outbounds, including legacy V2Ray envelopes.
    pub outbound_paths: Vec<String>,
    pub global_transport: Option<Value>,
    /// Recognized root sections, including outbounds; none is executed here.
    pub global_sections: Vec<&'static str>,
    pub diagnostics: Vec<Diagnostic>,
    original: Box<[u8]>,
}

impl ParsedDocument {
    /// Exact bounded input bytes, including an optional UTF-8 BOM. Private
    /// source data: do not put this in logs or public capability reports.
    pub fn raw_json(&self) -> &[u8] {
        &self.original
    }
}

impl fmt::Debug for ParsedDocument {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ParsedDocument")
            .field("input_kind", &self.input_kind)
            .field("source", &self.source)
            .field("outbound_count", &self.outbounds.len())
            .field("global_sections", &self.global_sections)
            .field("diagnostics", &self.diagnostics)
            .finish_non_exhaustive()
    }
}

/// Parse only strict JSON and the supported document envelopes. Protocol
/// validation/conversion is a separate stage so unsupported nodes remain data.
pub fn parse_document(bytes: &[u8]) -> Result<ParsedDocument, Diagnostic> {
    parse_document_with_source(bytes, InputSource::Unknown)
}

/// Parse with safe caller provenance. This never reads files, downloads a
/// subscription, resolves remote references, or constructs executable nodes.
pub fn parse_document_with_source(
    bytes: &[u8],
    source: InputSource,
) -> Result<ParsedDocument, Diagnostic> {
    let document = strict::parse(bytes)?;
    let mut parsed = structure(document)?;
    parsed.source = source;
    parsed.original = bytes.into();
    Ok(parsed)
}

fn structure(document: Value) -> Result<ParsedDocument, Diagnostic> {
    let mut diagnostics = Vec::new();
    let mut global_sections = Vec::new();
    let mut selected = Vec::new();
    let kind = match &document {
        Value::Array(nodes) => {
            diagnostics.push(diagnostic("SwirlOutboundArrayExtension", "", "info"));
            select_array(nodes, "", &mut selected)?;
            "swirl-outbound-array"
        }
        Value::Object(object) if object.contains_key("protocol") => {
            if [
                "outbounds",
                "inbounds",
                "outbound",
                "inbound",
                "outboundDetour",
                "inboundDetour",
            ]
            .iter()
            .any(|key| object.contains_key(*key))
            {
                return Err(diagnostic("AmbiguousJsonEnvelope", "protocol", "error"));
            }
            selected.push((&document, String::new()));
            "outbound"
        }
        Value::Object(object) => {
            const OBJECT_SECTIONS: &[&str] = &[
                "log",
                "dns",
                "routing",
                "policy",
                "transport",
                "stats",
                "api",
                "reverse",
                "metrics",
                "observatory",
                "burstObservatory",
                "router",
                "services",
            ];
            for (key, value) in object {
                let path = strict::key_path("", key);
                if let Some(&name) = OBJECT_SECTIONS.iter().find(|&&name| name == key) {
                    if !value.is_object() {
                        return Err(diagnostic("ExpectedObject", &path, "error"));
                    }
                    schema::global(key, value, &path)?;
                    global_sections.push(name);
                    diagnostics.push(diagnostic(
                        if key == "transport" {
                            "GlobalTransportPreservedNotApplied"
                        } else {
                            "GlobalConfigurationPreservedNotApplied"
                        },
                        &path,
                        "unsupported",
                    ));
                } else if key == "inbound" {
                    schema::inbound(value, &path)?;
                    global_sections.push("inbound");
                    diagnostics.push(diagnostic(
                        "ServerInboundsPreservedNotImported",
                        &path,
                        "info",
                    ));
                } else if key == "inbounds" || key == "inboundDetour" {
                    let items = value
                        .as_array()
                        .ok_or_else(|| diagnostic("ExpectedArray", &path, "error"))?;
                    for (index, item) in items.iter().enumerate() {
                        schema::inbound(item, &format!("{path}[{index}]"))?;
                    }
                    global_sections.push(if key == "inbounds" {
                        "inbounds"
                    } else {
                        "inboundDetour"
                    });
                    diagnostics.push(diagnostic(
                        "ServerInboundsPreservedNotImported",
                        &path,
                        "info",
                    ));
                } else if key == "fakedns" || key == "extension" {
                    if !value.is_array() {
                        return Err(diagnostic("ExpectedArray", &path, "error"));
                    }
                    global_sections.push(if key == "fakedns" {
                        "fakedns"
                    } else {
                        "extension"
                    });
                    diagnostics.push(diagnostic(
                        "GlobalConfigurationPreservedNotApplied",
                        &path,
                        "unsupported",
                    ));
                } else if key == "outbounds" || key == "outboundDetour" || key == "outbound" {
                    global_sections.push(match key.as_str() {
                        "outbound" => "outbound",
                        "outbounds" => "outbounds",
                        _ => "outboundDetour",
                    });
                    if key != "outbounds" {
                        diagnostics.push(diagnostic("LegacyOutboundEnvelope", &path, "info"));
                    }
                } else {
                    diagnostics.push(diagnostic("UnknownGlobalFieldPreserved", &path, "warning"));
                }
                if diagnostics.len() > MAX_JSON_DIAGNOSTICS {
                    return Err(diagnostic("DiagnosticLimit", "", "error"));
                }
            }
            // Fixed V2Ray v4 Build order: single outbound, outboundDetour[],
            // then outbounds[]. Keep source paths; do not merge global defaults.
            if let Some(node) = object.get("outbound") {
                selected.push((node, "outbound".into()));
            }
            for key in ["outboundDetour", "outbounds"] {
                if let Some(value) = object.get(key) {
                    let nodes = value
                        .as_array()
                        .ok_or_else(|| diagnostic("ExpectedArray", key, "error"))?;
                    select_array(nodes, key, &mut selected)?;
                }
            }
            if !["outbound", "outboundDetour", "outbounds"]
                .iter()
                .any(|key| object.contains_key(*key))
            {
                return Err(diagnostic("MissingClientOutbounds", "outbounds", "error"));
            }
            "configuration"
        }
        _ => {
            return Err(diagnostic(
                "ExpectedConfigurationObjectOrArray",
                "",
                "error",
            ));
        }
    };
    if selected.is_empty() {
        return Err(diagnostic(
            "EmptyOutbounds",
            if kind == "swirl-outbound-array" {
                ""
            } else {
                "outbounds"
            },
            "error",
        ));
    }
    for (node, path) in &selected {
        schema::outbound(node, path)?;
    }
    let (outbounds, outbound_paths) = selected
        .into_iter()
        .map(|(node, path)| (node.clone(), path))
        .unzip();
    let global_transport = if kind == "configuration" {
        document.get("transport").cloned()
    } else {
        None
    };
    Ok(ParsedDocument {
        input_kind: kind,
        source: InputSource::Unknown,
        configuration: document,
        outbounds,
        outbound_paths,
        global_transport,
        global_sections,
        diagnostics,
        original: Box::default(),
    })
}

fn select_array<'a>(
    nodes: &'a [Value],
    path: &str,
    selected: &mut Vec<(&'a Value, String)>,
) -> Result<(), Diagnostic> {
    if nodes.len() > MAX_JSON_NODES - selected.len() {
        return Err(diagnostic("NodeCountLimit", path, "error"));
    }
    selected.extend(
        nodes
            .iter()
            .enumerate()
            .map(|(index, node)| (node, format!("{path}[{index}]"))),
    );
    Ok(())
}

#[cfg(test)]
mod structure_tests {
    use super::*;
    use serde_json::json;
    fn parse(value: Value) -> Result<ParsedDocument, Diagnostic> {
        parse_document(&serde_json::to_vec(&value).unwrap())
    }

    #[test]
    fn recognizes_config_single_and_explicit_extension_array() {
        let outbound = json!({"protocol":"vless","tag":"sample","settings":{}});
        assert_eq!(parse(outbound.clone()).unwrap().input_kind, "outbound");
        assert_eq!(
            parse(json!([outbound.clone()])).unwrap().input_kind,
            "swirl-outbound-array"
        );
        let full = json!({"log":{},"dns":{},"inbounds":[{"protocol":"vless","settings":{"clients":[{}]}}],
            "outbounds":[outbound],"routing":{},"policy":{},"transport":{"wsSettings":{"path":"/example"}},"stats":{}});
        let result = parse(full.clone()).unwrap();
        assert_eq!(result.input_kind, "configuration");
        assert_eq!(result.outbounds.len(), 1);
        assert_eq!(result.configuration, full);
        assert_eq!(
            result.global_transport.unwrap()["wsSettings"]["path"],
            "/example"
        );
        assert!(
            result
                .diagnostics
                .iter()
                .any(|d| d.code == "ServerInboundsPreservedNotImported")
        );
    }
    #[test]
    fn rejects_empty_wrong_types_and_server_listeners() {
        for value in [
            Value::Null,
            json!(false),
            json!("text"),
            json!([]),
            json!({"outbounds":[]}),
            json!({"outbounds":null}),
            json!({"outbounds":[false]}),
            json!({"protocol":"vless","settings":null}),
            json!({"protocol":4,"settings":{}}),
            json!({"protocol":"vless","tag":false}),
            json!({"protocol":"vless","listen":"0.0.0.0","port":443}),
            json!({"protocol":"vless","settings":{"clients":[]}}),
            json!({"inbounds":[]}),
            json!({"dns":false,"outbounds":[{"protocol":"http"}]}),
            json!({"outbounds":[{"protocol":"vless"},{"type":"vless"}]}),
        ] {
            assert!(parse(value).is_err(), "accepted invalid client envelope");
        }
    }
    #[test]
    fn structural_diagnostics_are_paths_without_values() {
        let e =
            parse(json!({"outbounds":[{"protocol":"vless","streamSettings":"SECRET_PASSWORD"}]}))
                .err()
                .unwrap();
        assert_eq!(e.path, "outbounds[0].streamSettings");
        assert!(!serde_json::to_string(&e).unwrap().contains("SECRET"));
    }
}
