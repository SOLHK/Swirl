//! A request-scoped physical path for an isolated GUI probe while the product's
//! TUN lives in another process. It owns no routes or process-global TUN lease.
#[cfg(any(windows, test))]
use std::sync::atomic::{AtomicU64, Ordering};
use std::{
    future::Future,
    io,
    net::{IpAddr, SocketAddr},
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) struct Binding {
    pub interface: u32,
    #[cfg(windows)]
    pub adapter_id: u64,
    pub source: IpAddr,
}

#[derive(Clone, Copy)]
struct Scope {
    id: u64,
    v4: Option<Binding>,
    v6: Option<Binding>,
}

#[cfg(any(windows, test))]
static NEXT_SCOPE: AtomicU64 = AtomicU64::new(1);
tokio::task_local! {
    static PHYSICAL_PROBE: Scope;
}

impl Scope {
    #[cfg(any(windows, test))]
    fn new(bindings: impl IntoIterator<Item = Binding>) -> io::Result<Self> {
        let mut v4 = None;
        let mut v6 = None;
        for binding in bindings {
            if binding.interface == 0
                || binding.interface > 0x00ff_ffff
                || binding.source.is_loopback()
                || binding.source.is_unspecified()
                || binding.source.is_multicast()
            {
                return Err(io::Error::other("ProbeEgressBindingInvalid"));
            }
            #[cfg(windows)]
            if binding.adapter_id == 0 {
                return Err(io::Error::other("ProbeEgressBindingInvalid"));
            }
            let selected = if binding.source.is_ipv6() {
                &mut v6
            } else {
                &mut v4
            };
            if selected.is_none() {
                *selected = Some(binding);
            }
        }
        if v4.is_none() && v6.is_none() {
            return Err(io::Error::new(
                io::ErrorKind::NetworkUnreachable,
                "ProbeEgressUnavailable",
            ));
        }
        let mut id = NEXT_SCOPE.load(Ordering::Acquire);
        loop {
            let next = id
                .checked_add(1)
                .ok_or_else(|| io::Error::other("ProbeEgressGenerationLimit"))?;
            match NEXT_SCOPE.compare_exchange_weak(id, next, Ordering::AcqRel, Ordering::Acquire) {
                Ok(_) => break,
                Err(current) => id = current,
            }
        }
        Ok(Self { id, v4, v6 })
    }

    fn binding(self, ipv6: bool) -> io::Result<Binding> {
        (if ipv6 { self.v6 } else { self.v4 }).ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::NetworkUnreachable,
                "ProbeEgressFamilyUnavailable",
            )
        })
    }
}

pub(super) fn current_id() -> u64 {
    PHYSICAL_PROBE.try_with(|scope| scope.id).unwrap_or(0)
}

pub fn physical_probe_active() -> bool {
    current_id() != 0
}

/// Capture the already verified request context before spawning a protocol
/// driver that owns an existing socket. This performs no discovery or dial;
/// unrelated spawned tasks keep their ordinary scope. The driver owner remains
/// responsible for cancelling the task and retiring its socket.
pub fn inherit_physical_probe_scope<F: Future>(future: F) -> impl Future<Output = F::Output> {
    let scope = PHYSICAL_PROBE.try_with(|scope| *scope).ok();
    async move {
        match scope {
            Some(scope) => PHYSICAL_PROBE.scope(scope, future).await,
            None => future.await,
        }
    }
}

pub(super) fn binding(ipv6: bool) -> io::Result<Option<Binding>> {
    PHYSICAL_PROBE
        .try_with(|scope| scope.binding(ipv6).map(Some))
        .unwrap_or(Ok(None))
}

/// Discover only verified hardware egress and reject competing VPN capture.
/// All socket creation for URL tests, including configured DNS, is awaited in
/// this future. Protocol driver tasks retain already-created sockets; they do
/// not dial. The OS resolver's spawned lookup is explicitly disallowed while
/// this scope is active. A future spawned to create sockets must explicitly
/// retain this context rather than relying on Tokio task-local inheritance.
pub async fn with_physical_probe<F: Future>(future: F) -> io::Result<F::Output> {
    #[cfg(windows)]
    {
        let interfaces = swirl_platform::physical_network::physical_probe_interfaces()?;
        let scope = Scope::new(interfaces.into_iter().map(|entry| Binding {
            interface: entry.index,
            adapter_id: entry.adapter_id,
            source: entry.source,
        }))?;
        Ok(PHYSICAL_PROBE.scope(scope, future).await)
    }
    #[cfg(not(windows))]
    {
        drop(future);
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "ProbeEgressWindowsRequired",
        ))
    }
}

/// A wildcard UDP bind must acquire the same source as the scoped physical
/// interface. An explicit local-only peer keeps the normal loopback exemption.
pub(super) fn udp_bind_address(requested: SocketAddr) -> io::Result<SocketAddr> {
    if requested.ip().is_loopback() {
        return Ok(requested);
    }
    let Some(binding) = binding(requested.is_ipv6())? else {
        return Ok(requested);
    };
    if !requested.ip().is_unspecified() && requested.ip() != binding.source {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "ProbeEgressSourceMismatch",
        ));
    }
    Ok(SocketAddr::new(binding.source, requested.port()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::egress::EgressToken;

    fn fixture() -> Scope {
        Scope::new([Binding {
            interface: 7,
            #[cfg(windows)]
            adapter_id: 7,
            source: "192.0.2.7".parse().unwrap(),
        }])
        .unwrap()
    }

    #[tokio::test]
    async fn explicit_socket_driver_inheritance_keeps_full_scope_identity() {
        let peer = "192.0.2.20:443".parse().unwrap();
        let token = PHYSICAL_PROBE
            .scope(fixture(), async {
                let token = EgressToken::capture(&[peer]).unwrap();
                tokio::spawn(inherit_physical_probe_scope(async move {
                    assert!(physical_probe_active());
                    assert!(token.with_current(|| ()).is_ok());
                    assert_eq!(EgressToken::capture(&[peer]).unwrap(), token);
                }))
                .await
                .unwrap();
                assert!(
                    !tokio::spawn(async { physical_probe_active() })
                        .await
                        .unwrap()
                );
                token
            })
            .await;
        assert!(!physical_probe_active());
        assert!(token.with_current(|| ()).is_err());
        PHYSICAL_PROBE
            .scope(fixture(), async {
                assert!(token.with_current(|| ()).is_err());
            })
            .await;
        assert!(
            !tokio::spawn(inherit_physical_probe_scope(async {
                physical_probe_active()
            }))
            .await
            .unwrap()
        );
    }

    #[tokio::test]
    async fn scopes_do_not_share_pool_tokens_or_change_other_tasks() {
        let peer = "192.0.2.20:443".parse().unwrap();
        let ordinary = EgressToken::capture(&[peer]).unwrap();
        let first = PHYSICAL_PROBE
            .scope(fixture(), async {
                let token = EgressToken::capture(&[peer]).unwrap();
                assert!(ordinary.with_current(|| ()).is_err());
                assert!(token.with_current(|| ()).is_ok());
                assert!(physical_probe_active());
                // Unrelated tasks retain their ordinary routing. Socket-owning
                // protocol children receive an already-bound socket instead.
                assert!(
                    !tokio::spawn(async { physical_probe_active() })
                        .await
                        .unwrap()
                );
                token
            })
            .await;
        assert!(!physical_probe_active());
        assert!(first.with_current(|| ()).is_err());
        assert!(ordinary.with_current(|| ()).is_ok());
        PHYSICAL_PROBE
            .scope(fixture(), async {
                let second = EgressToken::capture(&[peer]).unwrap();
                assert_ne!(first, second);
                assert!(first.with_current(|| ()).is_err());
                assert!(second.with_current(|| ()).is_ok());
            })
            .await;
    }

    #[tokio::test]
    async fn source_selection_and_missing_families_never_fall_back() {
        PHYSICAL_PROBE
            .scope(fixture(), async {
                assert_eq!(
                    udp_bind_address("0.0.0.0:0".parse().unwrap()).unwrap(),
                    "192.0.2.7:0".parse().unwrap()
                );
                assert_eq!(
                    udp_bind_address("127.0.0.1:0".parse().unwrap()).unwrap(),
                    "127.0.0.1:0".parse().unwrap()
                );
                assert!(binding(true).is_err());
                assert!(udp_bind_address("[::]:0".parse().unwrap()).is_err());
                assert!(udp_bind_address("192.0.2.8:0".parse().unwrap()).is_err());
            })
            .await;
        assert_eq!(
            udp_bind_address("0.0.0.0:0".parse().unwrap()).unwrap(),
            "0.0.0.0:0".parse().unwrap()
        );
    }

    #[tokio::test]
    async fn cancellation_drops_scope_without_changing_the_global_lease() {
        let (started, ready) = tokio::sync::oneshot::channel();
        let task = tokio::spawn(PHYSICAL_PROBE.scope(fixture(), async move {
            started.send(current_id()).unwrap();
            std::future::pending::<()>().await;
        }));
        assert_ne!(ready.await.unwrap(), 0);
        task.abort();
        assert!(task.await.unwrap_err().is_cancelled());
        assert_eq!(current_id(), 0);
        let token = EgressToken::capture(&["192.0.2.1:443".parse().unwrap()]).unwrap();
        assert!(token.with_current(|| ()).is_ok());
    }

    #[cfg(windows)]
    #[tokio::test]
    async fn windows_physical_probe_transfers_with_real_bound_tcp_and_udp_sockets() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let interfaces = swirl_platform::physical_network::physical_probe_interfaces().unwrap();
        let selected = interfaces.first().unwrap();
        let source = selected.source;
        let listener = tokio::net::TcpListener::bind(SocketAddr::new(source, 0))
            .await
            .unwrap();
        let address = listener.local_addr().unwrap();
        let peer = tokio::spawn(async move {
            let (mut stream, remote) = listener.accept().await.unwrap();
            assert_eq!(remote.ip(), source);
            let mut bytes = [0; 5];
            stream.read_exact(&mut bytes).await.unwrap();
            assert_eq!(&bytes, b"probe");
            stream.write_all(b"reply").await.unwrap();
        });
        tokio::time::timeout(
            std::time::Duration::from_secs(5),
            with_physical_probe(async {
                let mut stream = crate::connect_tcp(address).await.unwrap();
                assert_eq!(stream.local_addr().unwrap().ip(), source);
                stream.write_all(b"probe").await.unwrap();
                let mut bytes = [0; 5];
                stream.read_exact(&mut bytes).await.unwrap();
                assert_eq!(&bytes, b"reply");
                let udp = crate::bind_udp(SocketAddr::new(
                    if source.is_ipv6() {
                        "::".parse().unwrap()
                    } else {
                        "0.0.0.0".parse().unwrap()
                    },
                    0,
                ))
                .await
                .unwrap();
                assert_eq!(udp.local_addr().unwrap().ip(), source);
                udp.send_to(b"udp", udp.local_addr().unwrap())
                    .await
                    .unwrap();
                let mut bytes = [0; 3];
                assert_eq!(udp.recv(&mut bytes).await.unwrap(), 3);
                assert_eq!(&bytes, b"udp");
            }),
        )
        .await
        .unwrap()
        .unwrap();
        peer.await.unwrap();

        // Negative control: the same valid source and index must fail before
        // any connect if the adapter identity changed. An ordinary unbound
        // connect would reach this listener and make this assertion fail.
        let listener = tokio::net::TcpListener::bind(SocketAddr::new(source, 0))
            .await
            .unwrap();
        let address = listener.local_addr().unwrap();
        let changed = Scope::new([Binding {
            interface: selected.index,
            adapter_id: selected.adapter_id ^ u64::MAX,
            source,
        }])
        .unwrap();
        PHYSICAL_PROBE
            .scope(changed, async {
                assert!(crate::connect_tcp(address).await.is_err());
                assert!(crate::bind_udp(SocketAddr::new(source, 0)).await.is_err());
            })
            .await;
        assert!(
            tokio::time::timeout(std::time::Duration::from_millis(50), listener.accept())
                .await
                .is_err()
        );
    }
}
