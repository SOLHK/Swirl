//! Optional, bounded observations of the existing connector operations.
//!
//! Only an explicit URL probe installs this task-local scope. There are no
//! endpoints, credentials, strings, event queues or spawned observer tasks.
//! Durations describe operations, never proof of proxy authentication or data
//! delivery. In particular QUIC includes TLS, and request writes have no ACK.
use serde::Serialize;
use std::{cell::RefCell, future::Future};
use tokio::time::Instant;

/// Durations in microseconds, absent when an operation did not run. Repeated
/// resolution/write operations are accumulated. TCP attempts can overlap, so
/// these fields must not be added to reconstruct the overall URL-test time.
/// `resolution_us` includes local literals, hosts/cache and any DNS transport;
/// it is not a DNS packet RTT. `tcp_dial_us` includes address fallback delays;
/// only `tcp_connected_attempt_us` measures the winning socket-connect future.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize)]
pub struct ConnectTimings {
    pub resolution_us: Option<u64>,
    pub tcp_dial_us: Option<u64>,
    pub tcp_connected_attempt_us: Option<u64>,
    pub tcp_attempts: u32,
    pub tcp_failed_attempts: u32,
    pub tcp_cancelled_attempts: u32,
    pub proxy_tls_handshake_us: Option<u64>,
    pub reality_handshake_us: Option<u64>,
    /// Quinn exposes the combined QUIC/TLS 1.3 operation, not separable TCP
    /// and TLS durations. Address fallback and endpoint setup are included.
    pub quic_handshake_including_tls_us: Option<u64>,
    /// Some HTTP/2 transports defer their response until application bytes.
    /// This measures setup only, not acceptance of a deferred response.
    pub transport_setup_us: Option<u64>,
    pub protocol_request_encode_write_us: Option<u64>,
    /// TUIC sends AUTH without an acknowledgement. This must never be treated
    /// as a completed authentication exchange.
    pub authentication_request_encode_write_us: Option<u64>,
    pub authentication_exchange_us: Option<u64>,
    pub proxy_negotiation_us: Option<u64>,
    pub proxy_connect_exchange_us: Option<u64>,
    /// The returned TUIC connection came from the live pool. A concurrent
    /// insertion race can discard a newly created connection before choosing
    /// that pooled owner; its actual QUIC/AUTH work is still recorded above.
    /// Only an ordinary cache hit has no new handshake/write observations.
    pub quic_connection_reused: bool,
    /// True only after an explicit success response (SOCKS5 password auth or
    /// HY2 HTTP 233). False also means "no acknowledgement exists/not observed".
    pub authentication_response_accepted: bool,
    /// At least one measured operation returned an error. Existing fixed
    /// failure stage/code fields describe the actual URL-test failure.
    pub failed_operations: u32,
    /// A measured future was dropped before completion, including losing
    /// TCP attempts. Its elapsed time is retained as a partial observation.
    pub interrupted: bool,
}

#[derive(Clone, Copy)]
pub(crate) enum Phase {
    Resolution,
    TcpDial,
    TcpAttempt,
    ProxyTls,
    Reality,
    Quic,
    TransportSetup,
    RequestEncodeWrite,
    AuthenticationRequestEncodeWrite,
    AuthenticationExchange,
    ProxyNegotiation,
    ProxyConnectExchange,
}

tokio::task_local! {
    static TIMING: RefCell<ConnectTimings>;
}

/// The scope owns its data. Snapshot after the measured future finishes, while
/// timeout/cancellation drops still execute inside this same scope. A spawned
/// driver does not inherit Tokio task-local values and cannot alter this trace.
pub(crate) async fn collect<T>(future: impl Future<Output = T>) -> (T, ConnectTimings) {
    TIMING
        .scope(RefCell::new(ConnectTimings::default()), async {
            let output = future.await;
            let timing = TIMING.with(|value| *value.borrow());
            (output, timing)
        })
        .await
}

pub(crate) fn reused_quic_connection() {
    let _ = TIMING.try_with(|value| value.borrow_mut().quic_connection_reused = true);
}

pub(crate) fn authentication_response_accepted() {
    let _ = TIMING.try_with(|value| value.borrow_mut().authentication_response_accepted = true);
}

struct Observation {
    phase: Phase,
    started: Option<Instant>,
}

impl Observation {
    fn new(phase: Phase) -> Self {
        let started = TIMING
            .try_with(|value| {
                if matches!(phase, Phase::TcpAttempt) {
                    let mut value = value.borrow_mut();
                    value.tcp_attempts = value.tcp_attempts.saturating_add(1);
                }
                Instant::now()
            })
            .ok();
        Self { phase, started }
    }

    fn finish(&mut self, success: Option<bool>) {
        let Some(started) = self.started.take() else {
            return;
        };
        let elapsed = started.elapsed().as_micros().min(u128::from(u64::MAX)) as u64;
        let _ = TIMING.try_with(|value| {
            let mut value = value.borrow_mut();
            if success == Some(false) {
                value.failed_operations = value.failed_operations.saturating_add(1);
            }
            if success.is_none() {
                value.interrupted = true;
            }
            let slot = match self.phase {
                Phase::Resolution => &mut value.resolution_us,
                Phase::TcpDial => &mut value.tcp_dial_us,
                Phase::TcpAttempt => {
                    match success {
                        Some(true) => value.tcp_connected_attempt_us = Some(elapsed),
                        Some(false) => {
                            value.tcp_failed_attempts = value.tcp_failed_attempts.saturating_add(1);
                        }
                        None => {
                            value.tcp_cancelled_attempts =
                                value.tcp_cancelled_attempts.saturating_add(1);
                        }
                    }
                    return;
                }
                Phase::ProxyTls => &mut value.proxy_tls_handshake_us,
                Phase::Reality => &mut value.reality_handshake_us,
                Phase::Quic => &mut value.quic_handshake_including_tls_us,
                Phase::TransportSetup => &mut value.transport_setup_us,
                Phase::RequestEncodeWrite => &mut value.protocol_request_encode_write_us,
                Phase::AuthenticationRequestEncodeWrite => {
                    &mut value.authentication_request_encode_write_us
                }
                Phase::AuthenticationExchange => &mut value.authentication_exchange_us,
                Phase::ProxyNegotiation => &mut value.proxy_negotiation_us,
                Phase::ProxyConnectExchange => &mut value.proxy_connect_exchange_us,
            };
            *slot = Some(slot.unwrap_or(0).saturating_add(elapsed));
        });
    }
}

impl Drop for Observation {
    fn drop(&mut self) {
        self.finish(None);
    }
}

pub(crate) async fn measure<T, E>(
    phase: Phase,
    future: impl Future<Output = Result<T, E>>,
) -> Result<T, E> {
    let mut observation = Observation::new(phase);
    let result = future.await;
    observation.finish(Some(result.is_ok()));
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{future::pending, time::Duration};
    use tokio::time::{sleep, timeout};

    #[tokio::test(start_paused = true)]
    async fn cancelled_phase_retains_elapsed_without_a_success_claim() {
        let (result, timing) = collect(timeout(
            Duration::from_millis(7),
            measure(Phase::AuthenticationExchange, pending::<Result<(), ()>>()),
        ))
        .await;
        assert!(result.is_err());
        assert_eq!(timing.authentication_exchange_us, Some(7_000));
        assert!(timing.interrupted);
        assert!(!timing.authentication_response_accepted);
        assert_eq!(timing.proxy_tls_handshake_us, None);
    }

    #[tokio::test(start_paused = true)]
    async fn scopes_are_isolated_and_spawned_drivers_do_not_inherit_them() {
        let (_, outer) = collect(async {
            let (_, inner) = collect(measure(Phase::ProxyTls, async {
                sleep(Duration::from_millis(3)).await;
                Ok::<_, ()>(())
            }))
            .await;
            assert_eq!(inner.proxy_tls_handshake_us, Some(3_000));
            tokio::spawn(measure(Phase::Quic, async { Ok::<_, ()>(()) }))
                .await
                .unwrap()
                .unwrap();
            measure(Phase::Resolution, async {
                sleep(Duration::from_millis(2)).await;
                Ok::<_, ()>(())
            })
            .await
            .unwrap();
        })
        .await;
        assert_eq!(outer.resolution_us, Some(2_000));
        assert_eq!(outer.proxy_tls_handshake_us, None);
        assert_eq!(outer.quic_handshake_including_tls_us, None);
        assert!(TIMING.try_with(|_| ()).is_err());
        measure(Phase::Quic, async { Ok::<_, ()>(()) })
            .await
            .unwrap();
        let (_, empty) = collect(async {}).await;
        assert_eq!(empty, ConnectTimings::default());
    }

    #[tokio::test(start_paused = true)]
    async fn tcp_attempt_count_and_winner_do_not_include_the_resolution_delay() {
        let (_, timing) = collect(async {
            measure(Phase::Resolution, async {
                sleep(Duration::from_millis(20)).await;
                Ok::<_, ()>(())
            })
            .await
            .unwrap();
            let _ = measure(Phase::TcpAttempt, async {
                sleep(Duration::from_millis(2)).await;
                Err::<(), _>(())
            })
            .await;
            measure(Phase::TcpAttempt, async {
                sleep(Duration::from_millis(4)).await;
                Ok::<_, ()>(())
            })
            .await
            .unwrap();
        })
        .await;
        assert_eq!(timing.resolution_us, Some(20_000));
        assert_eq!(timing.tcp_connected_attempt_us, Some(4_000));
        assert_eq!(timing.tcp_attempts, 2);
        assert_eq!(timing.tcp_failed_attempts, 1);
        assert_eq!(timing.tcp_cancelled_attempts, 0);
        assert_eq!(timing.failed_operations, 1);
        assert!(!timing.interrupted);
        assert!(serde_json::to_vec(&timing).unwrap().len() < 2048);
    }
}
