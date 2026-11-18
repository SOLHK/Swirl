//! Pure validation and clamping for one latency sweep. The networked sweep is
//! covered by the product-level latency benchmark; these cases pin the bounds
//! that must never be widened silently.
use super::{BatchInputs, BatchProbeRuntime, BatchState};
use super::{MAX_BATCH_NODES, MAX_CONCURRENCY, effective_concurrency, validate_request};
use std::{collections::BTreeMap, sync::Arc};
use swirl_dns::Resolver;
use swirl_subscription::{HealthProbe, Outbound};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
    time::{Duration, timeout},
};

fn options(url: String) -> HealthProbe {
    HealthProbe {
        url,
        interval_ms: 300_000,
        timeout_ms: 8_000,
        expected_status: 204,
        tolerance_ms: 0,
        tls: None,
    }
}

fn inputs(expected_status: Option<u16>) -> BatchInputs {
    BatchInputs {
        targets: BTreeMap::from([("a".into(), (Outbound::Direct {}, None))]),
        resolver: Arc::new(Resolver::default()),
        physical_egress: false,
        expected_status,
    }
}

#[tokio::test]
async fn explicit_http_status_is_enforced_and_dns_tcp_timings_are_preserved() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}/", listener.local_addr().unwrap());
    let server = tokio::spawn(async move {
        for _ in 0..2 {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                request.push(stream.read_u8().await.unwrap());
            }
            assert!(request.starts_with(b"HEAD / HTTP/1.1\r\n"));
            stream
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
                .await
                .unwrap();
        }
    });
    let probes = BatchProbeRuntime::new(tokio::runtime::Handle::current());
    for (expected, state) in [(Some(204), BatchState::Failed), (None, BatchState::Ok)] {
        probes
            .start(
                inputs(expected),
                vec!["a".into()],
                options(url.clone()),
                Some(1),
            )
            .unwrap();
        timeout(Duration::from_secs(3), async {
            while !probes.snapshot().unwrap().done {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        let row = probes.snapshot().unwrap().rows.remove(0);
        assert_eq!(row.state, state);
        assert_eq!(row.http_status, Some(200));
        assert!(
            row.outbound_timing
                .unwrap()
                .tcp_connected_attempt_us
                .is_some()
        );
        if state == BatchState::Ok {
            assert!(row.latency_ms.unwrap() >= row.outbound_connect_ms.unwrap());
        } else {
            assert_eq!(row.failure_stage, Some("http_status"));
            assert_eq!(row.latency_ms, None);
        }
    }
    server.await.unwrap();
}

#[tokio::test]
async fn cancellation_closes_in_flight_request_and_retires_generation() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}/", listener.local_addr().unwrap());
    let probes = BatchProbeRuntime::new(tokio::runtime::Handle::current());
    let started = probes
        .start(inputs(None), vec!["a".into()], options(url), Some(1))
        .unwrap();
    let (mut stream, _) = timeout(Duration::from_secs(3), listener.accept())
        .await
        .unwrap()
        .unwrap();
    let mut request = Vec::new();
    while !request.ends_with(b"\r\n\r\n") {
        request.push(stream.read_u8().await.unwrap());
    }
    let cancelled = probes.cancel().unwrap();
    assert_eq!(cancelled.request_id, started.request_id);
    assert_eq!(cancelled.rows[0].failure_code, Some("ProbeCancelled"));
    assert_eq!(
        timeout(Duration::from_secs(3), stream.read_u8())
            .await
            .unwrap()
            .unwrap_err()
            .kind(),
        std::io::ErrorKind::UnexpectedEof
    );
    timeout(Duration::from_secs(3), async {
        while !probes.quiescent() {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    assert!(probes.snapshot().unwrap().done);
}

#[test]
fn physical_batch_rejects_a_policy_worker_before_any_network_io() {
    let config=swirl_subscription::Config::parse(br#"{"schema":1,"listen":"127.0.0.1:0","selected":"a","nodes":[{"id":"a","outbound":{"type":"direct"}}],"rules":[{"matcher":{"type":"match"},"outbound":"a"}]}"#).unwrap();
    let core = crate::Core::start(config).unwrap();
    assert_eq!(
        core.probe_nodes_with_egress(
            vec!["a".into()],
            "https://example.invalid/".into(),
            None,
            None,
            None,
            true
        )
        .unwrap_err(),
        "ProbePhysicalWorkerRequired"
    );
    assert_eq!(core.snapshot().unwrap().active, 0);
}

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
