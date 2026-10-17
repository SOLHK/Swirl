//! Bounded TCP address fallback. Resolve once; race only these socket addresses,
//! and drop every losing connect future before TLS or protocol bytes are sent.
use super::{Result, Target};
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
        resolver.resolve(&target.host, target.port),
    )
    .await?;
    let stream = dial_addresses(addresses, deadline, TcpStream::connect).await?;
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
    mut connect: impl FnMut(SocketAddr) -> F,
) -> Result<T> {
    let mut addresses = ordered_addresses(addresses)?.into_iter().peekable();
    let mut attempts = Vec::with_capacity(PENDING_LIMIT);
    let mut next_start = Instant::now();
    let mut timed_out = false;
    loop {
        let now = Instant::now();
        if now >= deadline {
            return Err("UpstreamTcpTimeout");
        }
        if attempts.len() < PENDING_LIMIT && addresses.peek().is_some() && now >= next_start {
            let address = addresses.next().ok_or("DnsEmpty")?;
            let expires = if addresses.peek().is_some() {
                deadline.min(now + SLOT_LIMIT)
            } else {
                deadline
            };
            attempts.push(Box::pin(timeout_at(expires, connect(address))));
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
            _ = sleep_until(deadline) => return Err("UpstreamTcpTimeout"),
            (index, result) = poll_fn(|cx| {
                for (index, attempt) in attempts.iter_mut().enumerate() {
                    if let Poll::Ready(result) = attempt.as_mut().poll(cx) {
                        return Poll::Ready((index, result));
                    }
                }
                Poll::Pending
            }), if !attempts.is_empty() => {
                // Futures are owned here, not spawned. Returning or cancellation
                // immediately drops all other sockets; no background dial lives
                // past a successful TCP connection or the total deadline.
                drop(attempts.swap_remove(index));
                match result {
                    Ok(Ok(stream)) => return Ok(stream),
                    Ok(Err(_)) => {},
                    Err(_) => timed_out = true,
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
}
