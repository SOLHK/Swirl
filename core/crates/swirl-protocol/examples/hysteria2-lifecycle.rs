//! Official-peer cancellation regression. Every cleanup assertion runs before
//! process exit, in the same runtime used for the subsequent real connection.
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{future::Future, future::poll_fn, io::Read, task::Poll, time::Duration};
use swirl_protocol::Target;
use swirl_subscription::{Hysteria2, Outbound};
use swirl_transport::BoxStream;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    runtime::RuntimeMetrics,
    time::{Instant, sleep, timeout, timeout_at},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    config: Hysteria2,
    target_host: String,
    target_port: u16,
    #[serde(default = "timeout_ms")]
    timeout_ms: u64,
}

fn timeout_ms() -> u64 {
    10000
}

async fn wait_for_cleanup(
    metrics: &RuntimeMetrics,
    baseline: usize,
    deadline: Instant,
) -> Result<usize, &'static str> {
    timeout_at(deadline, async {
        loop {
            let tasks = metrics.num_alive_tasks();
            if tasks == baseline {
                return tasks;
            }
            sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .map_err(|_| "Hysteria2LifecycleTaskLeak")
}

async fn exchange(stream: &mut BoxStream, size: usize) -> Result<String, &'static str> {
    let payload: Vec<u8> = (0..size)
        .map(|position| ((position * 37 + 11) % 251) as u8)
        .collect();
    stream
        .write_all(&payload)
        .await
        .map_err(|_| "LifecycleWrite")?;
    stream.flush().await.map_err(|_| "LifecycleFlush")?;
    let mut response = vec![0; size];
    stream
        .read_exact(&mut response)
        .await
        .map_err(|_| "LifecycleRead")?;
    if response != payload {
        return Err("LifecycleContentMismatch");
    }
    Ok(format!("{:x}", Sha256::digest(&response)))
}

async fn run(input: Input) -> Result<Value, &'static str> {
    if input.timeout_ms == 0 || input.timeout_ms > 10000 {
        return Err("LifecycleInputLimit");
    }
    input.config.validate()?;
    let deadline = Instant::now() + Duration::from_millis(input.timeout_ms);
    let metrics = tokio::runtime::Handle::current().metrics();
    let baseline = metrics.num_alive_tasks();
    // This example owns a dedicated current-thread runtime. Requiring an empty
    // baseline makes a leaked H3/QUIC driver observable before process teardown.
    if baseline != 0 {
        return Err("LifecycleRuntimeNotIsolated");
    }
    let outbound = Outbound::Hysteria2(input.config);
    let target = Target {
        host: input.target_host,
        port: input.target_port,
    };
    let resolver = swirl_dns::Resolver::default();

    let mut connecting = Box::pin(swirl_protocol::connect(
        &outbound,
        &target,
        &resolver,
        deadline.saturating_duration_since(Instant::now()),
    ));
    let connecting_tasks = timeout_at(
        deadline,
        poll_fn(|context| match connecting.as_mut().poll(context) {
            Poll::Pending => {
                let tasks = metrics.num_alive_tasks();
                if tasks > baseline {
                    Poll::Ready(Ok(tasks))
                } else {
                    Poll::Pending
                }
            }
            Poll::Ready(Ok(_)) => Poll::Ready(Err("LifecycleConnectCompletedBeforeCancel")),
            Poll::Ready(Err(code)) => Poll::Ready(Err(code)),
        }),
    )
    .await
    .map_err(|_| "LifecycleConnectCancelTimeout")??;
    // This is an actual pending public-connector future owning Quinn tasks.
    // The first datagram or TLS/authentication completion is not asserted here.
    drop(connecting);
    let after_connect_cancel = wait_for_cleanup(&metrics, baseline, deadline).await?;

    let mut stream = swirl_protocol::connect(
        &outbound,
        &target,
        &resolver,
        deadline.saturating_duration_since(Instant::now()),
    )
    .await?;
    let authenticated_digest = exchange(&mut stream, 4096).await?;
    let authenticated_tasks = metrics.num_alive_tasks();
    if authenticated_tasks <= baseline {
        return Err("LifecycleMissingSessionTasks");
    }
    // The independent target only echoes received data. There is no remaining
    // data after exchange(), so this read must suspend. The async block owns
    // the stream: timeout drops it and its session, not just a borrowed read.
    let cancelled = timeout(Duration::from_millis(50), async move {
        let mut byte = [0];
        stream.read_exact(&mut byte).await
    })
    .await;
    if cancelled.is_ok() {
        return Err("LifecycleReadDidNotSuspend");
    }
    let after_read_cancel = wait_for_cleanup(&metrics, baseline, deadline).await?;

    let mut stream = swirl_protocol::connect(
        &outbound,
        &target,
        &resolver,
        deadline.saturating_duration_since(Instant::now()),
    )
    .await?;
    let reconnected_digest = exchange(&mut stream, 65536).await?;
    stream.shutdown().await.map_err(|_| "LifecycleShutdown")?;
    let mut tail = [0];
    if stream
        .read(&mut tail)
        .await
        .map_err(|_| "LifecycleCloseRead")?
        != 0
    {
        return Err("LifecycleUnexpectedTail");
    }
    drop(stream);
    let after_reconnect_close = wait_for_cleanup(&metrics, baseline, deadline).await?;

    Ok(json!({
        "ok": true,
        "runtime": "current_thread",
        "baseline_alive_tasks": baseline,
        "connect_future_cancel": {
            "stage": "pending connector with QUIC tasks; TLS and authentication not asserted",
            "alive_tasks_before_cancel": connecting_tasks,
            "alive_tasks_after_drop": after_connect_cancel
        },
        "authenticated_read_cancel": {
            "uploaded": 4096,
            "downloaded": 4096,
            "sha256": authenticated_digest,
            "future_owned_stream": true,
            "alive_tasks_before_cancel": authenticated_tasks,
            "alive_tasks_after_drop": after_read_cancel
        },
        "same_runtime_reconnect": {
            "uploaded": 65536,
            "downloaded": 65536,
            "sha256": reconnected_digest,
            "close": "clean",
            "alive_tasks_after_close": after_reconnect_close
        },
        "cleanup_asserted_before_process_exit": true
    }))
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let mut bytes = Vec::new();
    let input = std::io::stdin()
        .take(65537)
        .read_to_end(&mut bytes)
        .ok()
        .filter(|_| bytes.len() <= 65536)
        .and_then(|_| serde_json::from_slice::<Input>(&bytes).ok());
    let result = match input {
        Some(input) => {
            let limit = Duration::from_millis(input.timeout_ms.min(10000));
            match timeout(limit, run(input)).await {
                Ok(value) => value,
                Err(_) => Err("Hysteria2LifecycleTimeout"),
            }
        }
        None => Err("LifecycleInputSyntax"),
    };
    match result {
        Ok(value) => println!("{value}"),
        Err(code) => {
            println!("{}", json!({"ok": false, "code": code}));
            std::process::exit(1);
        }
    }
}
