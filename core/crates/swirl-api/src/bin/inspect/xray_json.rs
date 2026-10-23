//! Explicit strict Xray/V2Ray JSON inspection and private single-node export.
//! stdin is classified as a local file stream; no file path, URL, DNS lookup,
//! listener or network test is opened by this mode.
use serde_json::{Value, json};
use std::{
    ffi::OsString,
    io::{Read, Write},
    net::SocketAddr,
};
use swirl_subscription::xray::{
    Diagnostic, InputSource, MAX_JSON_INPUT,
    convert::{ConvertedDocument, NativeStatus, ValidationStatus, import_document},
};

struct Options {
    private_json: bool,
    native: Option<(usize, SocketAddr)>,
}

fn arguments(args: &[OsString]) -> Result<Options, &'static str> {
    let mut mode = false;
    let mut private_json = false;
    let mut node = None;
    let mut listen = None;
    let mut args = args.iter();
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("--xray-json") if !mode => mode = true,
            Some("--private-json") if !private_json => private_json = true,
            Some("--native-node") if node.is_none() => {
                let value = args
                    .next()
                    .and_then(|arg| arg.to_str())
                    .ok_or("XrayNativeNodeArgument")?;
                if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
                    return Err("XrayNativeNodeArgument");
                }
                node = Some(
                    value
                        .parse::<usize>()
                        .map_err(|_| "XrayNativeNodeArgument")?,
                );
            }
            Some("--listen") if listen.is_none() => {
                let address = args
                    .next()
                    .and_then(|arg| arg.to_str())
                    .and_then(|value| value.parse::<SocketAddr>().ok())
                    .ok_or("XrayListenArgument")?;
                if !address.ip().is_loopback() {
                    return Err("XrayListenMustBeLoopback");
                }
                listen = Some(address);
            }
            _ => return Err("XrayArgumentsInvalid"),
        }
    }
    if !mode {
        return Err("XrayModeRequired");
    }
    let native = match (node, listen) {
        (None, None) => None,
        (Some(node), Some(listen)) if private_json => Some((node, listen)),
        (Some(_), Some(_)) => return Err("XrayNativeExportRequiresPrivateJson"),
        _ => return Err("XrayNativeExportRequiresNodeAndListen"),
    };
    Ok(Options {
        private_json,
        native,
    })
}

fn diagnostic(code: &str) -> Diagnostic {
    Diagnostic {
        code: code.into(),
        path: String::new(),
        severity: "error".into(),
        line: None,
        column: None,
    }
}

fn error_report(error: Diagnostic, syntax: &str, validation: &str, stage: &str) -> Value {
    json!({
        "schema": 1, "mode": "xray_json", "ok": false,
        "syntax": syntax, "validation": validation, "failure_stage": stage,
        "native_executable_nodes": 0, "network_verified": false,
        "complete_configuration_execution_supported": false,
        "original_preserved": false, "nodes": [], "diagnostics": [error]
    })
}

fn import_failure(error: Diagnostic) -> Value {
    // This classifies A's closed diagnostic vocabulary, not the source JSON.
    // Unknown future errors remain unverified; never fall back to a permissive
    // parser or infer successful syntax from a failed import.
    let (syntax, validation, stage) = match error.code.as_str() {
        "JsonSyntax" | "InvalidUtf8" | "EmptyJsonInput" | "JsonNumber" => {
            ("invalid", "not_run", "syntax")
        }
        "DuplicateJsonKey" => ("rejected", "not_run", "strict_json"),
        "JsonInputSize" | "JsonDepthLimit" | "JsonValueLimit" => {
            ("unverified", "not_run", "input_limit")
        }
        "ExpectedObject"
        | "ExpectedArray"
        | "ExpectedString"
        | "ExpectedBoolean"
        | "ExpectedUnsigned16BitInteger"
        | "ExpectedUnsigned32BitInteger"
        | "ExpectedSigned32BitInteger"
        | "ExpectedStringOrStringArray"
        | "ExpectedPortNumberOrRangeString"
        | "AmbiguousJsonEnvelope"
        | "MissingClientOutbounds"
        | "ExpectedConfigurationObjectOrArray"
        | "EmptyOutbounds"
        | "MixedOrUnsupportedJsonDialect"
        | "MissingProtocol"
        | "ProtocolMustBeString"
        | "EmptyProtocol"
        | "InboundIsNotClientOutbound" => ("valid", "invalid", "structure"),
        "NodeCountLimit" | "DiagnosticLimit" | "ExpandedNodeLimit" => {
            ("valid", "unverified", "conversion_limit")
        }
        _ => ("unverified", "unverified", "import"),
    };
    error_report(error, syntax, validation, stage)
}

fn report(document: &ConvertedDocument) -> Value {
    let validation = if document
        .nodes()
        .iter()
        .any(|node| node.validation() == ValidationStatus::Invalid)
    {
        ValidationStatus::Invalid
    } else if document
        .nodes()
        .iter()
        .any(|node| node.validation() == ValidationStatus::Unverified)
    {
        ValidationStatus::Unverified
    } else {
        ValidationStatus::Valid
    };
    let nodes: Vec<_> = document
        .nodes()
        .iter()
        .enumerate()
        .map(|(index, node)| {
            json!({
                "index": index, "protocol": node.protocol(), "source": node.source(),
                "transport": node.transport(), "security": node.security(),
                "validation": node.validation(), "native_status": node.native_status(),
                "network_verified": node.network_verified(), "diagnostics": node.diagnostics()
            })
        })
        .collect();
    json!({
        "schema": 1, "mode": "xray_json", "ok": true,
        "syntax": "valid", "validation": validation, "validation_scope": "outbound_nodes",
        "source": document.source(), "nodes": nodes, "diagnostics": document.diagnostics(),
        "native_executable_nodes": document.nodes().iter()
            .filter(|node| node.native_status() == NativeStatus::Executable).count(),
        "native_execution_scope": "explicit_single_node_tcp",
        "network_verified": false, "original_preserved": true,
        "complete_configuration_execution_supported": false
    })
}

fn execute(args: &[OsString]) -> (Value, i32) {
    // Fully validate arguments first, including duplicates and options that
    // follow --private-json; rejected argv must never enter the private path.
    let options = match arguments(args) {
        Ok(options) => options,
        Err(code) => {
            return (
                error_report(diagnostic(code), "not_run", "not_run", "arguments"),
                2,
            );
        }
    };
    let mut input = Vec::new();
    if std::io::stdin()
        .take((MAX_JSON_INPUT + 1) as u64)
        .read_to_end(&mut input)
        .is_err()
    {
        return (
            error_report(diagnostic("XrayInputRead"), "not_run", "not_run", "input"),
            1,
        );
    }
    let document = match import_document(&input, InputSource::File) {
        Ok(document) => document,
        Err(error) => return (import_failure(error), 1),
    };
    let mut report = report(&document);
    let native_config = if let Some((index, listen)) = options.native {
        match document.native_config(index, listen) {
            Ok(config) => {
                report["native_export"] = json!({
                    "node_index": index, "source": document.nodes()[index].source(),
                    "scope": "single_node_tcp"
                });
                Some(config)
            }
            Err(error) => {
                report["ok"] = json!(false);
                report["failure_stage"] = json!("native_export");
                report["export_diagnostic"] = json!(error);
                // Even with explicit private mode a failed export emits only a
                // safe report. No partial config, raw source or archive escapes.
                return (report, 1);
            }
        }
    } else {
        None
    };
    if !options.private_json {
        return (report, 0);
    }
    let raw_json = match std::str::from_utf8(document.raw_json()) {
        Ok(raw) => raw,
        Err(_) => {
            return (
                error_report(
                    diagnostic("XrayPrivateEncoding"),
                    "unverified",
                    "unverified",
                    "export",
                ),
                1,
            );
        }
    };
    let archive = match document
        .save()
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok())
    {
        Some(archive) => archive,
        None => {
            return (
                error_report(
                    diagnostic("XrayArchiveSerialization"),
                    "valid",
                    "unverified",
                    "export",
                ),
                1,
            );
        }
    };
    let candidates: Vec<_> = document
        .nodes()
        .iter()
        .map(|node| node.native_outbound())
        .collect();
    let mut output = json!({
        "report": report, "raw_json": raw_json, "archive": archive,
        "native_candidates": candidates
    });
    if let Some(config) = native_config {
        output["native_config"] = json!(config);
    }
    (output, 0)
}

pub(super) fn run(args: &[OsString]) -> i32 {
    // Only this one-shot explicit mode suppresses panic text. Dependency
    // messages may contain source values; the legacy path remains unchanged.
    std::panic::set_hook(Box::new(|_| {}));
    let (output, status) = std::panic::catch_unwind(|| execute(args)).unwrap_or_else(|_| {
        (
            error_report(
                diagnostic("XrayInspectionInternal"),
                "unverified",
                "unverified",
                "internal",
            ),
            1,
        )
    });
    let Ok(bytes) = serde_json::to_vec(&output) else {
        return 1;
    };
    if std::io::stdout().write_all(&bytes).is_err() {
        return 1;
    }
    status
}
