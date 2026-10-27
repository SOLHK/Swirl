use super::*;

#[tokio::test(start_paused = true)]
async fn uniform_os_failure_categories_reach_the_product_without_private_error_text() {
    for (kind, expected) in [
        (
            io::ErrorKind::ConnectionRefused,
            "UpstreamConnectionRefused",
        ),
        (io::ErrorKind::ConnectionReset, "UpstreamConnectionReset"),
        (
            io::ErrorKind::ConnectionAborted,
            "UpstreamConnectionAborted",
        ),
        (io::ErrorKind::TimedOut, "UpstreamTcpTimeout"),
        (
            io::ErrorKind::NetworkUnreachable,
            "UpstreamNetworkUnreachable",
        ),
        (io::ErrorKind::HostUnreachable, "UpstreamNetworkUnreachable"),
        (io::ErrorKind::NetworkDown, "UpstreamNetworkUnreachable"),
        (io::ErrorKind::PermissionDenied, "UpstreamPermissionDenied"),
        (io::ErrorKind::Other, "UpstreamConnectFailed"),
    ] {
        let result = dial_addresses(
            vec![
                SocketAddr::from(([127, 0, 0, 1], 1)),
                SocketAddr::from(([127, 0, 0, 1], 2)),
            ],
            Instant::now() + Duration::from_secs(1),
            |_| async move {
                Err::<(), _>(io::Error::new(
                    kind,
                    "private-server.invalid:443 private-password",
                ))
            },
        )
        .await;
        assert_eq!(result, Err(expected));
        assert_eq!(crate::failure_stage(expected), "tcp_connect");
    }
}

#[tokio::test(start_paused = true)]
async fn mixed_address_failures_are_ambiguous_regardless_of_completion_order() {
    for reverse in [false, true] {
        let result = dial_addresses(
            vec![
                SocketAddr::from(([127, 0, 0, 1], 1)),
                SocketAddr::from(([127, 0, 0, 1], 2)),
                SocketAddr::from(([127, 0, 0, 1], 3)),
            ],
            Instant::now() + Duration::from_secs(1),
            |address| async move {
                let refused = (address.port() == 1) != reverse;
                Err::<(), _>(
                    if refused {
                        io::ErrorKind::ConnectionRefused
                    } else {
                        io::ErrorKind::ConnectionReset
                    }
                    .into(),
                )
            },
        )
        .await;
        assert_eq!(result, Err("UpstreamConnectFailed"));
    }
}
