//! Pure validation and clamping for one latency sweep. The networked sweep is
//! covered by the product-level latency benchmark; these cases pin the bounds
//! that must never be widened silently.
use super::{MAX_BATCH_NODES, MAX_CONCURRENCY, effective_concurrency, validate_request};

fn ids(count: usize) -> Vec<String> {
    (0..count).map(|index| format!("node-{index}")).collect()
}

#[test]
fn rejects_empty_and_oversized_sweeps() {
    assert_eq!(validate_request(&[]), Err("ProbeNodesSize"));
    assert_eq!(
        validate_request(&ids(MAX_BATCH_NODES + 1)),
        Err("ProbeNodesSize")
    );
    assert_eq!(validate_request(&ids(MAX_BATCH_NODES)), Ok(()));
}

#[test]
fn rejects_duplicate_nodes() {
    let mut nodes = ids(2);
    nodes.push("node-0".to_string());
    assert_eq!(validate_request(&nodes), Err("ProbeNodesDuplicate"));
}

#[test]
fn clamps_concurrency_into_the_supported_band() {
    assert_eq!(effective_concurrency(None), 16);
    assert_eq!(effective_concurrency(Some(0)), 1);
    assert_eq!(effective_concurrency(Some(1)), 1);
    assert_eq!(effective_concurrency(Some(8)), 8);
    assert_eq!(
        effective_concurrency(Some(MAX_CONCURRENCY)),
        MAX_CONCURRENCY
    );
    assert_eq!(effective_concurrency(Some(1_000)), MAX_CONCURRENCY);
}
