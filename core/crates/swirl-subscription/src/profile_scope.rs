//! Bounded scope eligibility for AUTOMATIC DATA-ONLY node extraction.
//! Full-profile execution is validated separately and remains strict. Every
//! foreign non-node field, including code/file/provider declarations, is opaque
//! encrypted provenance. Only independently validated canonical nodes may cross
//! this boundary; source globals are never evaluated, fetched or executed.
use crate::inspect::ini_section;
use serde_json::Value;

fn text(configuration: &Value) -> Option<&str> {
    let object = configuration.as_object()?;
    (object.len() == 1)
        .then(|| object.get("document")?.as_str())
        .flatten()
}

pub(super) fn has_semantics(format: &str, configuration: &Value) -> bool {
    if format == "ini"
        && let Some(text) = text(configuration)
    {
        let mut section = String::new();
        for line in text.lines().map(str::trim) {
            if line.is_empty() || line.starts_with(['#', ';']) || line.starts_with("//") {
                continue;
            }
            match ini_section(line) {
                Ok(Some(next)) => {
                    section = next;
                    continue;
                }
                Err(_) => return true,
                _ => {}
            }
            if matches!(section.as_str(), "proxy" | "server_local") {
                continue;
            }
            if section == "general"
                && line.split_once('=').is_some_and(|(key, value)| {
                    super::ini::client_setting_safe(&key.trim().to_ascii_lowercase(), value.trim())
                })
            {
                continue;
            }
            return true;
        }
        return false;
    }
    configuration.as_object().is_none_or(|o| {
        if format == "sing-box"
            && o.get("outbounds")
                .and_then(Value::as_array)
                .is_some_and(|outbounds| {
                    outbounds.iter().any(|outbound| {
                        outbound
                            .get("type")
                            .and_then(Value::as_str)
                            .is_some_and(|kind| matches!(kind, "selector" | "urltest" | "dns"))
                    })
                })
        {
            return true;
        }
        o.keys()
            .any(|key| !matches!(key.as_str(), "proxies" | "outbounds" | "log-level"))
    })
}

// Eligibility here is deliberately STRUCTURAL, not permission to execute an
// external document. The node parser owns the closed protocol/security schema;
// the shell may apply only its canonical nodes to the existing native policy.
// Every other source section is opaque encrypted provenance: it is never
// projected, evaluated, fetched, loaded from disk or promoted during reload.
fn bounded_data(value: &Value, depth: usize, budget: &mut usize) -> bool {
    if depth > 32 || *budget == 0 {
        return false;
    }
    *budget -= 1;
    match value {
        Value::Array(array) => array
            .iter()
            .all(|value| bounded_data(value, depth + 1, budget)),
        Value::Object(object) => object
            .iter()
            .all(|(key, value)| key.len() <= 4096 && bounded_data(value, depth + 1, budget)),
        Value::String(text) => text.len() <= 4 * 1024 * 1024,
        _ => true,
    }
}

fn bounded_ini(text: &str) -> bool {
    if text.is_empty()
        || text.len() > 4 * 1024 * 1024
        || text
            .chars()
            .any(|c| c.is_control() && !matches!(c, '\t' | '\r' | '\n'))
    {
        return false;
    }
    let mut sections = std::collections::HashSet::new();
    let mut section = String::new();
    let mut count = 0_u32;
    for line in text.lines().map(str::trim) {
        if line.is_empty() || line.starts_with(['#', ';']) || line.starts_with("//") {
            continue;
        }
        count += 1;
        if count > 100000 {
            return false;
        }
        match ini_section(line) {
            Ok(Some(next)) => {
                if !sections.insert(next.clone()) || sections.len() > 256 {
                    return false;
                }
                section = next;
            }
            Err(_) => return false,
            _ if section.is_empty() => return false,
            _ => {}
        }
    }
    sections.contains("proxy") || sections.contains("server_local")
}

pub(super) fn node_only_allowed(format: &str, configuration: &Value) -> bool {
    if format == "ini" && configuration.get("document").is_some() {
        return text(configuration).is_some_and(bounded_ini);
    }
    matches!(format, "clash" | "ini" | "sing-box")
        && configuration.is_object()
        && bounded_data(configuration, 0, &mut 100000)
}

#[cfg(test)]
#[path = "profile_scope_tests.rs"]
mod tests;
