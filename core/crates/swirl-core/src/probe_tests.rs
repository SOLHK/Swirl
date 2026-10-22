use super::*;
use crate::Core;
use swirl_subscription::Config;
use tokio::time::{Duration, timeout};

fn metrics() -> UrlTestMetrics {
    UrlTestMetrics {
        outbound_connect_ms: 12,
        origin_tls_ms: Some(7),
        response_headers_ms: 24,
        http_status: 200,
    }
}

#[tokio::test]
async fn cancellation_and_new_generation_discard_late_probe_results() {
    let probes = ProbeRuntime::new(Handle::current());
    let first = probes
        .start_with(std::future::pending::<
            std::result::Result<UrlTestMetrics, UrlTestFailure>,
        >())
        .unwrap();
    assert_eq!(first.state, ProbePhase::Running);
    probes.invalidate().unwrap();
    ProbeRuntime::finish(&probes.slot, first.request_id, Ok(metrics()));
    assert_eq!(probes.status().unwrap().state, ProbePhase::Idle);
    assert!(probes.status().unwrap().metrics.is_none());

    let second = probes.start_with(async { Ok(metrics()) }).unwrap();
    timeout(Duration::from_secs(1), async {
        while probes.status().unwrap().state == ProbePhase::Running {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    let completed = probes.status().unwrap();
    assert_eq!(completed.request_id, second.request_id);
    assert_eq!(completed.state, ProbePhase::Succeeded);
    assert_eq!(completed.metrics.unwrap().response_headers_ms, 24);

    let third = probes
        .start_with(std::future::pending::<
            std::result::Result<UrlTestMetrics, UrlTestFailure>,
        >())
        .unwrap();
    let cancelled = probes.cancel().unwrap();
    ProbeRuntime::finish(&probes.slot, third.request_id, Ok(metrics()));
    assert_eq!(cancelled.state, ProbePhase::Cancelled);
    assert_eq!(probes.status().unwrap(), cancelled);
}

#[test]
fn selecting_configuring_and_stopping_invalidate_running_probes() {
    let config = Config::parse(
        br#"{"schema":1,"listen":"127.0.0.1:0","selected":"a","nodes":[
            {"id":"a","outbound":{"type":"direct"}},
            {"id":"b","outbound":{"type":"direct"}}
        ]}"#,
    )
    .unwrap();
    let mut core = Core::start(config.clone()).unwrap();
    let pending = || std::future::pending::<std::result::Result<UrlTestMetrics, UrlTestFailure>>();

    let selected = core.probe.start_with(pending()).unwrap();
    core.select_node("b").unwrap();
    ProbeRuntime::finish(&core.probe.slot, selected.request_id, Ok(metrics()));
    assert_eq!(core.probe_status().unwrap().state, ProbePhase::Idle);

    let configured = core.probe.start_with(pending()).unwrap();
    core.configure(config).unwrap();
    ProbeRuntime::finish(&core.probe.slot, configured.request_id, Ok(metrics()));
    assert_eq!(core.probe_status().unwrap().state, ProbePhase::Idle);

    let stopped = core.probe.start_with(pending()).unwrap();
    core.stop();
    ProbeRuntime::finish(&core.probe.slot, stopped.request_id, Ok(metrics()));
    assert_eq!(core.probe_status().unwrap().state, ProbePhase::Idle);
}
