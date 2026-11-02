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

#[tokio::test]
async fn dial_denial_and_network_errors_keep_distinct_socks5_wire_replies() {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;

    // Inject typed OS failures into the product scheduler, not into the reply
    // encoder. The client reads real TCP bytes. This does not claim that the
    // runner's network routes or permissions were changed to induce failures.
    tokio::time::timeout(Duration::from_secs(5), async {
        for (kind, status) in [
            (io::ErrorKind::PermissionDenied, 2),
            (io::ErrorKind::NetworkUnreachable, 3),
        ] {
            let error = dial_addresses(
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
            .await
            .unwrap_err();
            let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
            let mut client = TcpStream::connect(listener.local_addr().unwrap())
                .await
                .unwrap();
            let (mut server, _) = listener.accept().await.unwrap();
            crate::reply_failure(&mut server, crate::InboundKind::Socks5, error)
                .await
                .unwrap();
            server.shutdown().await.unwrap();
            let mut response = Vec::new();
            client.read_to_end(&mut response).await.unwrap();
            assert_eq!(response, [5, status, 0, 1, 0, 0, 0, 0, 0, 0]);
        }
    })
    .await
    .expect("SOCKS5 failure reply fixture exceeded its deadline");
}
