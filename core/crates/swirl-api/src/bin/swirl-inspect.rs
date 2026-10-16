//! Offline stdin inspector. Default output is strictly redacted. The explicit
//! --private-json mode is only for a local encrypted-cache pipeline; never log it.
use std::io::{Read, Write};
fn main() {
    let mut input = Vec::new();
    if std::io::stdin()
        .take((swirl_subscription::inspect::MAX_INPUT + 1) as u64)
        .read_to_end(&mut input)
        .is_err()
    {
        return;
    }
    let result = swirl_subscription::inspect::inspect(&input);
    let output = if std::env::args().any(|a| a == "--private-json") {
        serde_json::json!({"report":result.report,"document":result.document,"nodes":result.originals,"tcpCandidates":result.tcp_candidates})
    } else {
        serde_json::to_value(&result.report).unwrap_or(serde_json::Value::Null)
    };
    if let Ok(bytes) = serde_json::to_vec(&output) {
        let _ = std::io::stdout().write_all(&bytes);
    }
}
