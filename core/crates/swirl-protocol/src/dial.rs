//! Bounded TCP address fallback. Resolve once; race only these socket addresses,
//! and drop every losing connect future before TLS or protocol bytes are sent.
use super::{Result, Target};
use crate::diagnostics::{TcpAttempt, TcpDiagnostic, TcpOutcome};
use crate::timing::{self, Phase};
use std::{
    future::{Future, poll_fn},
    io,
    net::SocketAddr,
    task::Poll,
};
use swirl_dns::Resolver;
use tokio::{
    net::TcpStream,
    time::{Duration, Instant, sleep_until, timeout_at},
};

const ATTEMPT_DELAY: Duration = Duration::from_millis(250);
const PENDING_LIMIT: usize = 2;
const ADDRESS_LIMIT: usize = 16;
// Retire a stalled attempt only when further resolved addresses need a slot.
// The final candidates retain the remainder of the original shared deadline.
const SLOT_LIMIT: Duration = Duration::from_secs(2);

fn millis(duration: Duration) -> u64 {
    duration.as_millis().min(u128::from(u64::MAX)) as u64
}

// An optional observer, not a second scheduler. It never retains endpoints or
// OS errors. Dropping the enclosing dial future records still-pending sockets
// as cancelled; the sockets themselves remain owned by the original scheduler.
struct Observation<'a> {
    report: Option<&'a mut TcpDiagnostic>,
    started: Instant,
    active: Vec<(usize, Instant)>,
}

impl<'a> Observation<'a> {
    fn new(report: Option<&'a mut TcpDiagnostic>, addresses: &[SocketAddr]) -> Self {
        let mut result = Self {
            report,
            started: Instant::now(),
            active: Vec::new(),
        };
        if let Some(report) = result.report.as_deref_mut() {
            report.address_count = addresses.len();
            report.ipv4_count = addresses.iter().filter(|a| a.is_ipv4()).count();
            report.ipv6_count = addresses.len() - report.ipv4_count;
            report.remaining_count = addresses.len();
        }
        result
    }

    fn start(&mut self, address: SocketAddr) -> usize {
        let Some(report) = self.report.as_deref_mut() else {
            return 0;
        };
        let index = report.attempts.len();
        let now = Instant::now();
        report.attempts.push(TcpAttempt {
            ordinal: index + 1,
            family: if address.is_ipv4() { "ipv4" } else { "ipv6" },
            started_ms: millis(now.duration_since(self.started)),
            elapsed_ms: 0,
            outcome: TcpOutcome::Cancelled,
        });
        self.active.push((index, now));
        report.attempted_count += 1;
        report.remaining_count -= 1;
        report.peak_pending = report.peak_pending.max(self.active.len());
        index
    }

    fn finish(&mut self, index: usize, outcome: TcpOutcome) {
        let Some(report) = self.report.as_deref_mut() else {
            return;
        };
        if let Some(position) = self.active.iter().position(|(id, _)| *id == index) {
            let (_, started) = self.active.swap_remove(position);
            report.attempts[index].elapsed_ms = millis(started.elapsed());
            report.attempts[index].outcome = outcome;
        }
    }

    fn finish_pending(&mut self, outcome: TcpOutcome) {
        while let Some((index, _)) = self.active.last().copied() {
            self.finish(index, outcome);
        }
    }
}

impl Drop for Observation<'_> {
    fn drop(&mut self) {
        self.finish_pending(TcpOutcome::Cancelled);
        if let Some(report) = self.report.as_deref_mut() {
            report.tcp_elapsed_ms = millis(self.started.elapsed());
        }
    }
}

/// Run the product's resolver and TCP address scheduler with a stricter
/// diagnostic budget. All connected sockets are immediately dropped, without
/// TLS, proxy authentication or application bytes. This is not a protocol test.
///
/// DNS is capped at three seconds, the total at ten seconds and pending TCP at
/// two. The existing product's timeouts and address-selection policy are not
/// changed. OS DNS lookups cannot always be cancelled: the resolver retains its
/// existing semaphore limit and the standalone CLI also bounds runtime shutdown.
pub async fn diagnose_tcp(
    resolver: &Resolver,
    target: &Target,
    total_budget: Duration,
    dns_budget: Duration,
) -> TcpDiagnostic {
    let (mut report, result) = diagnose_with(
        total_budget,
        dns_budget,
        timing::measure(
            Phase::Resolution,
            resolver.resolve(&target.host, target.port),
        ),
        TcpStream::connect,
    )
    .await;
    if let Ok(stream) = result {
        if stream.set_nodelay(true).is_err() {
            report.ok = false;
            report.error_code = Some("SocketOptions");
            report.failure_stage = Some("socket_options");
        }
        drop(stream);
    }
    report
}

async fn diagnose_with<T, F: Future<Output = io::Result<T>>>(
    total_budget: Duration,
    dns_budget: Duration,
    resolve: impl Future<Output = Result<Vec<SocketAddr>>>,
    connect: impl FnMut(SocketAddr) -> F,
) -> (TcpDiagnostic, Result<T>) {
    let started = Instant::now();
    let mut report = TcpDiagnostic::new(millis(total_budget), millis(dns_budget.min(total_budget)));
    if total_budget.is_zero()
        || total_budget > Duration::from_secs(10)
        || dns_budget.is_zero()
        || dns_budget > Duration::from_secs(3)
    {
        report.error_code = Some("DiagnosticBudget");
        report.failure_stage = Some("input");
        return (report, Err("DiagnosticBudget"));
    }
    let deadline = started + total_budget;
    let addresses = within(
        deadline.min(started + dns_budget),
        "UpstreamDnsTimeout",
        resolve,
    )
    .await;
    report.dns_elapsed_ms = millis(started.elapsed());
    let result = match addresses {
        Ok(addresses) => {
            dial_addresses_observed(addresses, deadline, connect, Some(&mut report)).await
        }
        Err("UpstreamDnsTimeout" | "DnsTimeout") => Err("UpstreamDnsTimeout"),
        // DNS has many detailed internal codes. This interface intentionally
        // emits a small fixed vocabulary, never a supplied error string.
        Err(_) => Err("DnsLookupFailed"),
    };
    report.total_elapsed_ms = millis(started.elapsed());
    match &result {
        Ok(_) => report.ok = true,
        Err(code) => {
            report.error_code = Some(code);
            report.failure_stage = Some(crate::failure_stage(code));
        }
    }
    (report, result)
}

pub(super) async fn within<T>(
    deadline: Instant,
    timeout_code: &'static str,
    future: impl Future<Output = Result<T>>,
) -> Result<T> {
    if Instant::now() >= deadline {
        return Err(timeout_code);
    }
    tokio::select! {
        biased;
        _ = sleep_until(deadline) => Err(timeout_code),
        result = future => result,
    }
}

pub(super) async fn connect_tcp(
    resolver: &Resolver,
    target: &Target,
    deadline: Instant,
) -> Result<TcpStream> {
    // Resolver returns a literal unchanged, including a route-pinned address.
    // Never re-resolve the original hostname or consult another route here.
    let addresses = within(
        deadline,
        "UpstreamDnsTimeout",
        timing::measure(
            Phase::Resolution,
            resolver.resolve(&target.host, target.port),
        ),
    )
    .await?;
    connect_tcp_addresses(addresses, deadline).await
}

/// Connect DIRECT to addresses that were already resolved and selected by the
/// caller. No second DNS lookup, proxy negotiation or application write occurs.
/// All address attempts share one deadline and the losing sockets are dropped.
pub async fn connect_direct_resolved(
    addresses: Vec<SocketAddr>,
    handshake_limit: Duration,
) -> Result<swirl_transport::BoxStream> {
    let deadline = Instant::now()
        .checked_add(handshake_limit)
        .ok_or("UpstreamTcpTimeout")?;
    Ok(Box::new(connect_tcp_addresses(addresses, deadline).await?))
}

async fn connect_tcp_addresses(addresses: Vec<SocketAddr>, deadline: Instant) -> Result<TcpStream> {
    let stream = timing::measure(
        Phase::TcpDial,
        dial_addresses(addresses, deadline, TcpStream::connect),
    )
    .await?;
    stream.set_nodelay(true).map_err(|_| "SocketOptions")?;
    Ok(stream)
}

fn ordered_addresses(addresses: Vec<SocketAddr>) -> Result<Vec<SocketAddr>> {
    if addresses.is_empty() {
        return Err("DnsEmpty");
    }
    if addresses.len() > ADDRESS_LIMIT {
        return Err("UpstreamAddressLimit");
    }
    let mut unique = Vec::with_capacity(addresses.len());
    for address in addresses {
        if !unique.contains(&address) {
            unique.push(address);
        }
    }
    let mut ipv6 = unique[0].is_ipv6();
    let mut ordered = Vec::with_capacity(unique.len());
    // Keep the resolver's preference and within-family ordering, while moving
    // the other family forward instead of exhausting one family first.
    while !unique.is_empty() {
        let index = unique
            .iter()
            .position(|address| address.is_ipv6() == ipv6)
            .unwrap_or(0);
        ordered.push(unique.remove(index));
        ipv6 = !ipv6;
    }
    Ok(ordered)
}

async fn dial_addresses<T, F: Future<Output = io::Result<T>>>(
    addresses: Vec<SocketAddr>,
    deadline: Instant,
    connect: impl FnMut(SocketAddr) -> F,
) -> Result<T> {
    dial_addresses_observed(addresses, deadline, connect, None).await
}

async fn dial_addresses_observed<T, F: Future<Output = io::Result<T>>>(
    addresses: Vec<SocketAddr>,
    deadline: Instant,
    mut connect: impl FnMut(SocketAddr) -> F,
    report: Option<&mut TcpDiagnostic>,
) -> Result<T> {
    let addresses = ordered_addresses(addresses)?;
    let mut observation = Observation::new(report, &addresses);
    let mut addresses = addresses.into_iter().peekable();
    let mut attempts = Vec::with_capacity(PENDING_LIMIT);
    let mut next_start = Instant::now();
    let mut timed_out = false;
    loop {
        let now = Instant::now();
        if now >= deadline {
            observation.finish_pending(TcpOutcome::Timeout);
            return Err("UpstreamTcpTimeout");
        }
        if attempts.len() < PENDING_LIMIT && addresses.peek().is_some() && now >= next_start {
            let address = addresses.next().ok_or("DnsEmpty")?;
            let expires = if addresses.peek().is_some() {
                deadline.min(now + SLOT_LIMIT)
            } else {
                deadline
            };
            let ordinal = observation.start(address);
            attempts.push((
                ordinal,
                Box::pin(timeout_at(
                    expires,
                    timing::measure(Phase::TcpAttempt, connect(address)),
                )),
            ));
            next_start = now + ATTEMPT_DELAY;
        }
        if attempts.is_empty() && addresses.peek().is_none() {
            return Err(if timed_out {
                "UpstreamTcpTimeout"
            } else {
                "UpstreamConnectFailed"
            });
        }
        tokio::select! {
            biased;
            _ = sleep_until(deadline) => {
                observation.finish_pending(TcpOutcome::Timeout);
                return Err("UpstreamTcpTimeout");
            },
            (index, result) = poll_fn(|cx| {
                for (index, (_, attempt)) in attempts.iter_mut().enumerate() {
                    if let Poll::Ready(result) = attempt.as_mut().poll(cx) {
                        return Poll::Ready((index, result));
                    }
                }
                Poll::Pending
            }), if !attempts.is_empty() => {
                // Futures are owned here, not spawned. Returning or cancellation
                // immediately drops all other sockets; no background dial lives
                // past a successful TCP connection or the total deadline.
                let (ordinal, attempt) = attempts.swap_remove(index);
                drop(attempt);
                match result {
                    Ok(Ok(stream)) => {
                        observation.finish(ordinal, TcpOutcome::Success);
                        return Ok(stream);
                    },
                    Ok(Err(error)) => observation.finish(ordinal, TcpOutcome::from_io(&error)),
                    Err(_) => {
                        observation.finish(ordinal, TcpOutcome::Timeout);
                        timed_out = true;
                    },
                }
                // A completed failure has already freed its socket slot. Do
                // not waste a short total budget waiting for a failed attempt;
                // the stagger applies while attempts are still pending.
                next_start = Instant::now();
            },
            _ = sleep_until(next_start), if attempts.len() < PENDING_LIMIT
                && addresses.peek().is_some() => {},
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        cell::{Cell, RefCell},
        future::pending,
        rc::Rc,
    };
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        net::{TcpListener, TcpSocket},
        time::{sleep, timeout},
    };

    struct AttemptGuard(Rc<Cell<usize>>);
    impl AttemptGuard {
        fn new(active: &Rc<Cell<usize>>, peak: &Cell<usize>) -> Self {
            active.set(active.get() + 1);
            peak.set(peak.get().max(active.get()));
            Self(active.clone())
        }
    }
    impl Drop for AttemptGuard {
        fn drop(&mut self) {
            self.0.set(self.0.get() - 1);
        }
    }
    fn address(value: &str) -> SocketAddr {
        value.parse().unwrap()
    }

    #[tokio::test(start_paused = true)]
    async fn hanging_first_family_does_not_block_other_family_and_losers_drop() {
        let first = address("[::1]:80");
        let unused = address("[::2]:80");
        let reachable = address("127.0.0.1:80");
        let calls = RefCell::new(Vec::new());
        let active = Rc::new(Cell::new(0));
        let peak = Cell::new(0);
        let started = Instant::now();
        let result = dial_addresses(
            vec![first, unused, reachable, reachable],
            started + Duration::from_secs(5),
            |endpoint| {
                calls.borrow_mut().push(endpoint);
                let guard = AttemptGuard::new(&active, &peak);
                async move {
                    let _guard = guard;
                    if endpoint.is_ipv6() {
                        pending::<()>().await;
                    }
                    Ok(endpoint)
                }
            },
        )
        .await;
        assert_eq!(result, Ok(reachable));
        assert_eq!(calls.into_inner(), vec![first, reachable]);
        assert_eq!(started.elapsed(), Duration::from_millis(250));
        assert_eq!(peak.get(), 2);
        assert_eq!(active.get(), 0);
    }

    #[tokio::test(start_paused = true)]
    async fn two_stalled_addresses_release_a_slot_for_the_third() {
        let active = Rc::new(Cell::new(0));
        let peak = Cell::new(0);
        let calls = RefCell::new(Vec::new());
        let endpoints: Vec<_> = (1..=3)
            .map(|port| SocketAddr::from(([127, 0, 0, 1], port)))
            .collect();
        let started = Instant::now();
        let result = dial_addresses(
            endpoints.clone(),
            started + Duration::from_secs(5),
            |endpoint| {
                calls.borrow_mut().push(endpoint);
                let guard = AttemptGuard::new(&active, &peak);
                async move {
                    let _guard = guard;
                    if endpoint.port() != 3 {
                        pending::<()>().await;
                    }
                    Ok(endpoint)
                }
            },
        )
        .await;
        assert_eq!(result, Ok(endpoints[2]));
        assert_eq!(calls.into_inner(), endpoints);
        assert_eq!(started.elapsed(), Duration::from_secs(2));
        assert_eq!(peak.get(), 2);
        assert_eq!(active.get(), 0);
    }

    #[tokio::test(start_paused = true)]
    async fn caller_cancellation_drops_all_pending_dials() {
        let active = Rc::new(Cell::new(0));
        let peak = Cell::new(0);
        let started = Instant::now();
        let result = timeout(
            Duration::from_millis(300),
            dial_addresses(
                vec![address("[::1]:80"), address("127.0.0.1:80")],
                started + Duration::from_secs(5),
                |_| {
                    let guard = AttemptGuard::new(&active, &peak);
                    async move {
                        let _guard = guard;
                        pending::<io::Result<()>>().await
                    }
                },
            ),
        )
        .await;
        assert!(result.is_err());
        assert_eq!(peak.get(), 2);
        assert_eq!(active.get(), 0);
        assert_eq!(started.elapsed(), Duration::from_millis(300));
    }

    #[tokio::test(start_paused = true)]
    async fn a_single_address_retains_the_original_budget() {
        let started = Instant::now();
        let result = dial_addresses(
            vec![address("127.0.0.1:80")],
            started + Duration::from_secs(5),
            |_| pending::<io::Result<()>>(),
        )
        .await;
        assert_eq!(result, Err("UpstreamTcpTimeout"));
        assert_eq!(started.elapsed(), Duration::from_secs(5));
    }

    #[tokio::test(start_paused = true)]
    async fn refusal_and_expiration_are_distinct_and_no_new_dial_passes_deadline() {
        let endpoints = vec![address("127.0.0.1:80"), address("[::1]:80")];
        assert_eq!(
            dial_addresses(
                endpoints.clone(),
                Instant::now() + Duration::from_secs(5),
                |_| async { Err::<(), _>(io::ErrorKind::ConnectionRefused.into()) },
            )
            .await,
            Err("UpstreamConnectFailed")
        );
        let calls = Cell::new(0);
        let started = Instant::now();
        assert_eq!(
            dial_addresses(endpoints, started + Duration::from_millis(100), |_| {
                calls.set(calls.get() + 1);
                pending::<io::Result<()>>()
            },)
            .await,
            Err("UpstreamTcpTimeout")
        );
        assert_eq!(calls.get(), 1);
        assert_eq!(started.elapsed(), Duration::from_millis(100));
        assert_eq!(
            dial_addresses(vec![address("127.0.0.1:80")], Instant::now(), |_| {
                calls.set(calls.get() + 1);
                async { Ok(()) }
            })
            .await,
            Err("UpstreamTcpTimeout")
        );
        assert_eq!(calls.get(), 1);
    }

    #[tokio::test(start_paused = true)]
    async fn refused_first_address_does_not_spend_a_short_budget_waiting_for_stagger() {
        let refused = address("[::1]:80");
        let reachable = address("127.0.0.1:80");
        let calls = RefCell::new(Vec::new());
        let started = Instant::now();
        let result = dial_addresses(
            vec![refused, reachable],
            started + Duration::from_millis(100),
            |endpoint| {
                calls.borrow_mut().push(endpoint);
                async move {
                    if endpoint == refused {
                        Err(io::ErrorKind::ConnectionRefused.into())
                    } else {
                        Ok(endpoint)
                    }
                }
            },
        )
        .await;
        assert_eq!(result, Ok(reachable));
        assert_eq!(calls.into_inner(), vec![refused, reachable]);
        assert_eq!(started.elapsed(), Duration::ZERO);
    }

    #[tokio::test(start_paused = true)]
    async fn address_limit_is_checked_before_any_socket_attempt() {
        let calls = Cell::new(0);
        let endpoints = (1..=17)
            .map(|port| SocketAddr::from(([127, 0, 0, 1], port)))
            .collect();
        assert_eq!(
            dial_addresses(endpoints, Instant::now() + Duration::from_secs(5), |_| {
                calls.set(calls.get() + 1);
                async { Ok(()) }
            })
            .await,
            Err("UpstreamAddressLimit")
        );
        assert_eq!(calls.get(), 0);
    }

    #[tokio::test(start_paused = true)]
    async fn protocol_phases_use_the_same_deadline_without_renewing_it() {
        let started = Instant::now();
        let deadline = started + Duration::from_millis(100);
        within(deadline, "UpstreamDnsTimeout", async {
            sleep(Duration::from_millis(70)).await;
            Ok(())
        })
        .await
        .unwrap();
        assert_eq!(
            within(deadline, "UpstreamTlsTimeout", pending::<Result<()>>()).await,
            Err("UpstreamTlsTimeout")
        );
        assert_eq!(started.elapsed(), Duration::from_millis(100));
        let polled = Cell::new(false);
        assert_eq!(
            within(deadline, "UpstreamProtocolTimeout", async {
                polled.set(true);
                Ok(())
            })
            .await,
            Err("UpstreamProtocolTimeout")
        );
        assert!(!polled.get());
    }

    #[tokio::test]
    async fn real_tcp_refusal_falls_back_without_sending_application_bytes() {
        let reserved = TcpSocket::new_v4().unwrap();
        reserved.bind(address("127.0.0.1:0")).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let mut connected = dial_addresses(
            vec![
                reserved.local_addr().unwrap(),
                listener.local_addr().unwrap(),
            ],
            Instant::now() + Duration::from_secs(3),
            TcpStream::connect,
        )
        .await
        .unwrap();
        let (mut peer, _) = listener.accept().await.unwrap();
        assert!(
            timeout(Duration::from_millis(20), peer.read_u8())
                .await
                .is_err()
        );
        connected.write_all(b"native").await.unwrap();
        let mut bytes = [0; 6];
        peer.read_exact(&mut bytes).await.unwrap();
        assert_eq!(&bytes, b"native");
    }

    #[tokio::test]
    async fn resolved_direct_uses_fallback_without_sending_application_bytes() {
        let reserved = TcpSocket::new_v4().unwrap();
        reserved.bind(address("127.0.0.1:0")).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let mut connected = connect_direct_resolved(
            vec![
                reserved.local_addr().unwrap(),
                listener.local_addr().unwrap(),
            ],
            Duration::from_secs(3),
        )
        .await
        .unwrap();
        let (mut peer, _) = listener.accept().await.unwrap();
        assert!(
            timeout(Duration::from_millis(20), peer.read_u8())
                .await
                .is_err()
        );
        connected.write_all(b"direct").await.unwrap();
        let mut bytes = [0; 6];
        peer.read_exact(&mut bytes).await.unwrap();
        assert_eq!(&bytes, b"direct");
    }

    #[tokio::test]
    async fn resolved_direct_expired_budget_prevents_socket_attempt() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let result =
            connect_direct_resolved(vec![listener.local_addr().unwrap()], Duration::ZERO).await;
        assert!(matches!(result, Err("UpstreamTcpTimeout")));
        assert!(
            timeout(Duration::from_millis(20), listener.accept())
                .await
                .is_err()
        );
    }

    #[tokio::test(start_paused = true)]
    async fn diagnostic_counts_unique_families_and_records_cancelled_loser() {
        let started = Instant::now();
        let endpoints = vec![
            address("[::1]:32123"),
            address("[::2]:32123"),
            address("127.0.0.1:32123"),
            address("127.0.0.1:32123"),
        ];
        let (report, result) = diagnose_with(
            Duration::from_secs(5),
            Duration::from_secs(3),
            async { Ok(endpoints) },
            |endpoint| async move {
                if endpoint.is_ipv6() {
                    pending::<()>().await;
                }
                sleep(Duration::from_millis(25)).await;
                Ok(())
            },
        )
        .await;
        assert!(result.is_ok());
        assert!(report.ok);
        assert_eq!(report.error_code, None);
        assert_eq!(report.failure_stage, None);
        assert_eq!(
            (report.address_count, report.ipv4_count, report.ipv6_count),
            (3, 1, 2)
        );
        assert_eq!(
            (
                report.attempted_count,
                report.remaining_count,
                report.peak_pending
            ),
            (2, 1, 2)
        );
        assert_eq!(
            (
                report.dns_elapsed_ms,
                report.tcp_elapsed_ms,
                report.total_elapsed_ms
            ),
            (0, 275, 275)
        );
        assert_eq!(report.attempts[0].family, "ipv6");
        assert_eq!(report.attempts[0].outcome, TcpOutcome::Cancelled);
        assert_eq!(report.attempts[0].elapsed_ms, 275);
        assert_eq!(report.attempts[1].family, "ipv4");
        assert_eq!(report.attempts[1].ordinal, 2);
        assert_eq!(report.attempts[1].started_ms, 250);
        assert_eq!(report.attempts[1].elapsed_ms, 25);
        assert_eq!(report.attempts[1].outcome, TcpOutcome::Success);
        assert_eq!(started.elapsed(), Duration::from_millis(275));
        let debug = format!("{report:?}");
        for private in ["127.0.0.1", "::1", "::2", "32123"] {
            assert!(!debug.contains(private));
        }
    }

    #[tokio::test(start_paused = true)]
    async fn diagnostic_dns_cap_prevents_tcp_and_total_cap_can_be_shorter() {
        for (total_ms, expected_ms) in [(10_000, 3_000), (700, 700)] {
            let called = Cell::new(false);
            let (report, result) = diagnose_with(
                Duration::from_millis(total_ms),
                Duration::from_secs(3),
                pending::<Result<Vec<SocketAddr>>>(),
                |_| {
                    called.set(true);
                    async { Ok(()) }
                },
            )
            .await;
            assert_eq!(result, Err("UpstreamDnsTimeout"));
            assert_eq!(report.error_code, Some("UpstreamDnsTimeout"));
            assert_eq!(report.failure_stage, Some("dns"));
            assert_eq!(report.total_elapsed_ms, expected_ms);
            assert_eq!(report.dns_elapsed_ms, expected_ms);
            assert_eq!(report.tcp_elapsed_ms, 0);
            assert_eq!(report.address_count, 0);
            assert_eq!(report.attempted_count, 0);
            assert_eq!(report.remaining_count, 0);
            assert!(!called.get());
        }
    }

    #[tokio::test(start_paused = true)]
    async fn diagnostic_dns_time_reduces_tcp_budget_and_counts_unattempted_addresses() {
        let (report, result) = diagnose_with(
            Duration::from_millis(100),
            Duration::from_secs(3),
            async {
                sleep(Duration::from_millis(70)).await;
                Ok(vec![
                    address("[::1]:80"),
                    address("[::2]:80"),
                    address("127.0.0.1:80"),
                ])
            },
            |_| pending::<io::Result<()>>(),
        )
        .await;
        assert_eq!(result, Err("UpstreamTcpTimeout"));
        assert_eq!(report.failure_stage, Some("tcp_connect"));
        assert_eq!(
            (
                report.dns_elapsed_ms,
                report.tcp_elapsed_ms,
                report.total_elapsed_ms
            ),
            (70, 30, 100)
        );
        assert_eq!(
            (
                report.address_count,
                report.attempted_count,
                report.remaining_count
            ),
            (3, 1, 2)
        );
        assert_eq!(report.attempts[0].outcome, TcpOutcome::Timeout);
        assert_eq!(report.attempts[0].elapsed_ms, 30);
        assert_eq!(report.peak_pending, 1);
    }

    #[tokio::test(start_paused = true)]
    async fn diagnostic_classifies_os_failures_without_preserving_error_messages() {
        let endpoints = (1..=6)
            .map(|port| SocketAddr::from(([127, 0, 0, 1], port)))
            .collect();
        let (report, result) = diagnose_with(
            Duration::from_secs(5),
            Duration::from_secs(3),
            async { Ok(endpoints) },
            |endpoint| async move {
                let kind = match endpoint.port() {
                    1 => io::ErrorKind::ConnectionRefused,
                    2 => io::ErrorKind::NetworkUnreachable,
                    3 => io::ErrorKind::HostUnreachable,
                    4 => io::ErrorKind::NetworkDown,
                    5 => io::ErrorKind::TimedOut,
                    _ => io::ErrorKind::PermissionDenied,
                };
                Err::<(), _>(io::Error::new(
                    kind,
                    "secret.invalid:32123 private-password",
                ))
            },
        )
        .await;
        // Preserve the product's existing top-level error semantics: only an
        // actual scheduler deadline changes this into UpstreamTcpTimeout.
        assert_eq!(result, Err("UpstreamConnectFailed"));
        assert_eq!(
            report
                .attempts
                .iter()
                .map(|a| a.outcome)
                .collect::<Vec<_>>(),
            vec![
                TcpOutcome::Refused,
                TcpOutcome::Unreachable,
                TcpOutcome::Unreachable,
                TcpOutcome::Unreachable,
                TcpOutcome::Timeout,
                TcpOutcome::Other,
            ]
        );
        assert_eq!(
            (
                report.attempted_count,
                report.remaining_count,
                report.peak_pending
            ),
            (6, 0, 1)
        );
        let debug = format!("{report:?}");
        for private in [
            "secret.invalid",
            "32123",
            "private-password",
            "PermissionDenied",
        ] {
            assert!(!debug.contains(private));
        }
    }

    #[tokio::test(start_paused = true)]
    async fn diagnostic_slot_timeout_and_winner_cancellation_remain_distinct() {
        let active = Rc::new(Cell::new(0));
        let peak = Cell::new(0);
        let endpoints = (1..=3)
            .map(|port| SocketAddr::from(([127, 0, 0, 1], port)))
            .collect();
        let (report, result) = diagnose_with(
            Duration::from_secs(5),
            Duration::from_secs(3),
            async { Ok(endpoints) },
            |endpoint| {
                let guard = AttemptGuard::new(&active, &peak);
                async move {
                    let _guard = guard;
                    if endpoint.port() != 3 {
                        pending::<()>().await;
                    }
                    Ok(())
                }
            },
        )
        .await;
        assert!(result.is_ok());
        assert_eq!(
            report
                .attempts
                .iter()
                .map(|a| a.outcome)
                .collect::<Vec<_>>(),
            vec![
                TcpOutcome::Timeout,
                TcpOutcome::Cancelled,
                TcpOutcome::Success,
            ]
        );
        assert_eq!(report.attempts[0].elapsed_ms, 2000);
        assert_eq!(report.attempts[1].elapsed_ms, 1750);
        assert_eq!(report.attempts[2].started_ms, 2000);
        assert_eq!(report.total_elapsed_ms, 2000);
        assert_eq!(report.peak_pending, 2);
        assert_eq!(peak.get(), 2);
        assert_eq!(active.get(), 0);
    }

    #[tokio::test(start_paused = true)]
    async fn external_cancellation_updates_trace_and_drops_all_connects() {
        let mut report = TcpDiagnostic::new(5000, 3000);
        let active = Rc::new(Cell::new(0));
        let peak = Cell::new(0);
        let started = Instant::now();
        let result = timeout(
            Duration::from_millis(300),
            dial_addresses_observed(
                vec![
                    address("[::1]:80"),
                    address("127.0.0.1:80"),
                    address("127.0.0.2:80"),
                ],
                started + Duration::from_secs(5),
                |_| {
                    let guard = AttemptGuard::new(&active, &peak);
                    async move {
                        let _guard = guard;
                        pending::<io::Result<()>>().await
                    }
                },
                Some(&mut report),
            ),
        )
        .await;
        assert!(result.is_err());
        assert_eq!(
            (
                report.attempted_count,
                report.remaining_count,
                report.peak_pending
            ),
            (2, 1, 2)
        );
        assert!(
            report
                .attempts
                .iter()
                .all(|a| a.outcome == TcpOutcome::Cancelled)
        );
        assert_eq!(report.attempts[0].elapsed_ms, 300);
        assert_eq!(report.attempts[1].elapsed_ms, 50);
        assert_eq!(report.tcp_elapsed_ms, 300);
        assert_eq!(active.get(), 0);
    }

    #[tokio::test(start_paused = true)]
    async fn diagnostic_invalid_budget_does_not_poll_dns_or_dial() {
        for (total, dns) in [(10_001, 3000), (10_000, 3001), (0, 3000), (10_000, 0)] {
            let polled = Cell::new(false);
            let (report, result) = diagnose_with(
                Duration::from_millis(total),
                Duration::from_millis(dns),
                async {
                    polled.set(true);
                    Ok(vec![address("127.0.0.1:80")])
                },
                |_| async { Ok(()) },
            )
            .await;
            assert_eq!(result, Err("DiagnosticBudget"));
            assert_eq!(report.failure_stage, Some("input"));
            assert!(!polled.get());
            assert!(report.attempts.is_empty());
        }
    }

    #[tokio::test(start_paused = true)]
    async fn diagnostic_dns_error_has_a_fixed_redacted_category() {
        let (report, result) = diagnose_with(
            Duration::from_secs(5),
            Duration::from_secs(3),
            async { Err("private-marker.invalid:32123") },
            |_| async { Ok(()) },
        )
        .await;
        assert_eq!(result, Err("DnsLookupFailed"));
        assert_eq!(report.error_code, Some("DnsLookupFailed"));
        assert_eq!(report.failure_stage, Some("dns"));
        assert!(!format!("{report:?}").contains("private-marker"));
        assert!(report.attempts.is_empty());
    }

    #[tokio::test]
    async fn diagnostic_real_loopback_connect_closes_without_application_data() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let target = Target {
            host: "127.0.0.1".into(),
            port: listener.local_addr().unwrap().port(),
        };
        let report = diagnose_tcp(
            &Resolver::default(),
            &target,
            Duration::from_secs(1),
            Duration::from_millis(300),
        )
        .await;
        assert!(report.ok, "{report:?}");
        assert_eq!(
            (
                report.address_count,
                report.attempted_count,
                report.remaining_count
            ),
            (1, 1, 0)
        );
        assert_eq!(report.attempts[0].outcome, TcpOutcome::Success);
        assert_eq!(report.attempts[0].family, "ipv4");
        let (mut peer, _) = timeout(Duration::from_secs(1), listener.accept())
            .await
            .unwrap()
            .unwrap();
        let mut bytes = [0; 1];
        assert_eq!(
            timeout(Duration::from_secs(1), peer.read(&mut bytes))
                .await
                .unwrap()
                .unwrap(),
            0
        );
    }
}
