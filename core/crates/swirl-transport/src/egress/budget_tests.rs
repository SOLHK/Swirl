use super::*;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
    time::{Duration, timeout},
};

fn quota(bytes: u64, connections: u32) -> Arc<TcpQuota> {
    Arc::new(TcpQuota::new(bytes, connections, MAX_TIMEOUT_MS).unwrap())
}

async fn connection(guard: &Arc<TcpQuota>) -> (TcpConnection, TcpStream) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let admission = guard.admit().unwrap();
    let socket = admission.socket(address).unwrap();
    let (stream, (peer, _)) = timeout(Duration::from_secs(5), async {
        tokio::try_join!(socket.connect(address), listener.accept())
    })
    .await
    .expect("loopback connection timed out")
    .expect("loopback connection failed");
    (TcpConnection::new(stream, Some(admission)).unwrap(), peer)
}

#[tokio::test]
async fn writes_are_clipped_before_tcp_and_idle_peers_are_closed_at_limit() {
    let guard = quota(31, 2);
    let (mut client, mut peer) = connection(&guard).await;
    let (_idle, mut idle_peer) = connection(&guard).await;
    assert_eq!(client.write(&[7; 4096]).await.unwrap(), 31);
    assert!(client.write(b"overflow").await.is_err());
    let mut received = Vec::new();
    timeout(Duration::from_secs(2), peer.read_to_end(&mut received))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(received, [7; 31]);
    assert_eq!(
        timeout(Duration::from_secs(2), idle_peer.read_u8())
            .await
            .unwrap()
            .unwrap_err()
            .kind(),
        io::ErrorKind::UnexpectedEof
    );
    let snapshot = guard.snapshot().unwrap();
    assert_eq!(
        (
            snapshot.upload,
            snapshot.download,
            snapshot.stopped,
            snapshot.shutdown_failures
        ),
        (31, 0, true, 0)
    );
    assert_eq!(snapshot.receive_reservation, 2 * RECEIVE_RESERVATION);
}

#[tokio::test]
async fn download_limit_includes_bytes_before_protocol_parsing() {
    let guard = quota(29, 1);
    let (mut client, mut peer) = connection(&guard).await;
    peer.write_all(&[9; 1024]).await.unwrap();
    let mut buffer = [0; 1024];
    assert_eq!(client.read(&mut buffer).await.unwrap(), 29);
    assert_eq!(&buffer[..29], &[9; 29]);
    assert!(client.read(&mut buffer).await.is_err());
    let snapshot = guard.snapshot().unwrap();
    assert_eq!(
        (snapshot.upload, snapshot.download, snapshot.stopped),
        (0, 29, true)
    );
}

#[tokio::test]
async fn nonblocking_read_shares_the_async_write_allowance() {
    let guard = quota(5, 1);
    let (mut client, mut peer) = connection(&guard).await;
    client.write_all(&[1; 3]).await.unwrap();
    peer.write_all(&[2; 16]).await.unwrap();
    let mut buffer = [0; 16];
    let received = timeout(Duration::from_secs(2), async {
        loop {
            client.readable().await.unwrap();
            match client.try_read(&mut buffer) {
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => continue,
                result => break result.unwrap(),
            }
        }
    })
    .await
    .unwrap();
    assert_eq!(received, 2);
    assert!(client.try_read(&mut buffer).is_err());
    assert_eq!(guard.snapshot().unwrap().download, 2);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 3)]
async fn concurrent_connections_share_one_combined_allowance() {
    let guard = quota(257, 3);
    let mut peers = Vec::new();
    let mut clients = Vec::new();
    for _ in 0..3 {
        let (client, peer) = connection(&guard).await;
        clients.push(client);
        peers.push(peer);
    }
    let barrier = Arc::new(tokio::sync::Barrier::new(3));
    let mut writers = tokio::task::JoinSet::new();
    for mut client in clients {
        let barrier = Arc::clone(&barrier);
        writers.spawn(async move {
            barrier.wait().await;
            client.write(&[1; 128]).await.unwrap_or(0)
        });
    }
    let mut sent = 0;
    while let Some(result) = writers.join_next().await {
        sent += result.unwrap();
    }
    assert_eq!(sent, 257);
    let mut observed = 0;
    for mut peer in peers {
        let mut data = Vec::new();
        timeout(Duration::from_secs(2), peer.read_to_end(&mut data))
            .await
            .unwrap()
            .unwrap();
        observed += data.len();
    }
    assert_eq!(observed, 257);
    assert_eq!(guard.snapshot().unwrap().upload, 257);
}

#[tokio::test]
async fn cancellation_shuts_idle_socket_without_another_client_poll() {
    let guard = quota(4096, 1);
    let (_client, mut peer) = connection(&guard).await;
    guard.cancel();
    guard.cancel();
    assert_eq!(
        timeout(Duration::from_secs(2), peer.read_u8())
            .await
            .unwrap()
            .unwrap_err()
            .kind(),
        io::ErrorKind::UnexpectedEof
    );
    let snapshot = guard.snapshot().unwrap();
    assert_eq!(
        (
            snapshot.upload,
            snapshot.download,
            snapshot.stopped,
            snapshot.shutdown_failures
        ),
        (0, 0, true, 0)
    );
    assert!(guard.admit().is_err());
}

#[tokio::test]
async fn pending_read_does_not_consume_allowance_and_half_close_preserves_reply() {
    let guard = quota(100, 1);
    let (mut client, mut peer) = connection(&guard).await;
    let mut bytes = [0; 4];
    let pending = std::future::poll_fn(|cx| {
        let mut buffer = ReadBuf::new(&mut bytes);
        Poll::Ready(Pin::new(&mut client).poll_read(cx, &mut buffer))
    })
    .await;
    assert!(pending.is_pending());
    assert_eq!(guard.snapshot().unwrap().download, 0);
    client.write_all(b"ping").await.unwrap();
    client.shutdown().await.unwrap();
    let mut request = Vec::new();
    peer.read_to_end(&mut request).await.unwrap();
    assert_eq!(request, b"ping");
    peer.write_all(b"pong").await.unwrap();
    client.read_exact(&mut bytes).await.unwrap();
    assert_eq!(&bytes, b"pong");
    let snapshot = guard.snapshot().unwrap();
    assert_eq!(
        (snapshot.upload, snapshot.download, snapshot.stopped),
        (4, 4, false)
    );
}

#[test]
fn connection_attempts_are_not_refunded_and_parameters_are_bounded() {
    let guard = quota(100, 1);
    drop(guard.admit().unwrap());
    assert!(guard.admit().is_err());
    assert_eq!(guard.snapshot().unwrap().connection_attempts, 1);
    assert!(guard.snapshot().unwrap().stopped);
    for (bytes, connections) in [(0, 1), (MAX_BYTES + 1, 1), (1, 0), (1, MAX_CONNECTIONS + 1)] {
        assert!(TcpQuota::new(bytes, connections, MAX_TIMEOUT_MS).is_err());
    }
    assert!(TcpQuota::new(100, 1, 0).is_err());
    assert!(TcpQuota::new(100, 1, MAX_TIMEOUT_MS + 1).is_err());
}

#[tokio::test]
async fn cancelled_quota_never_polls_a_new_connection() {
    let guard = quota(100, 1);
    guard.cancel();
    let mut polled = false;
    let result = guard
        .while_running(async {
            polled = true;
            Ok(())
        })
        .await;
    assert_eq!(result.unwrap_err().kind(), io::ErrorKind::PermissionDenied);
    assert!(!polled);
}

#[tokio::test]
async fn cancellation_drops_a_connect_future_before_socket_registration() {
    let guard = quota(100, 1);
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let admission = guard.admit().unwrap();
    let socket = admission.socket(address).unwrap();
    let (connected_tx, connected_rx) = tokio::sync::oneshot::channel();
    let connecting = tokio::spawn(async move {
        admission
            .while_running(async move {
                let stream = socket.connect(address).await?;
                connected_tx.send(()).unwrap();
                // Keep a real native socket inside an unfinished connect
                // operation, before TcpConnection can register its duplicate.
                std::future::pending::<()>().await;
                Ok(stream)
            })
            .await
    });
    let (mut peer, _) = timeout(Duration::from_secs(2), listener.accept())
        .await
        .unwrap()
        .unwrap();
    connected_rx.await.unwrap();
    assert!(guard.state.lock().unwrap().sockets.is_empty());
    guard.cancel();
    assert_eq!(
        timeout(Duration::from_secs(2), connecting)
            .await
            .unwrap()
            .unwrap()
            .unwrap_err()
            .kind(),
        io::ErrorKind::PermissionDenied
    );
    assert_eq!(
        timeout(Duration::from_secs(2), peer.read_u8())
            .await
            .unwrap()
            .unwrap_err()
            .kind(),
        io::ErrorKind::UnexpectedEof
    );
    let receipt = guard.snapshot().unwrap();
    assert_eq!(receipt.connection_attempts, 1);
    assert_eq!(receipt.upload + receipt.download, 0);
}

#[tokio::test]
async fn failed_native_connect_keeps_its_attempt_and_buffer_reservation() {
    let guard = quota(100, 1);
    // A bound but non-listening local TCP socket produces a real refusal
    // without relying on a port that another process might claim.
    let refused = TcpSocket::new_v4().unwrap();
    refused.bind("127.0.0.1:0".parse().unwrap()).unwrap();
    let address = refused.local_addr().unwrap();
    let admission = guard.admit().unwrap();
    let socket = admission.socket(address).unwrap();
    assert!(
        timeout(
            Duration::from_secs(2),
            admission.while_running(socket.connect(address))
        )
        .await
        .unwrap()
        .is_err()
    );
    let receipt = guard.snapshot().unwrap();
    assert_eq!(receipt.connection_attempts, 1);
    assert_eq!(receipt.upload + receipt.download, 0);
    assert_eq!(receipt.receive_reservation, RECEIVE_RESERVATION);
    assert!(guard.admit().is_err());
}

#[test]
fn watchdog_closes_idle_socket_without_a_running_async_timer() {
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let guard = Arc::new(TcpQuota::new(4096, 1, 1000).unwrap());
    let (_client, mut peer) = runtime.block_on(connection(&guard));
    let watchdog = guard.start_watchdog().unwrap();
    // The Tokio runtime is not polling anything here. Only the independent
    // watchdog can expire and close this socket without another client read.
    watchdog.join().unwrap();
    let receipt = guard.snapshot().unwrap();
    assert!(receipt.timed_out && receipt.stopped);
    assert_eq!(receipt.timeout_ms, 1000);
    assert_eq!(receipt.shutdown_failures, 0);
    runtime.block_on(async {
        assert_eq!(
            timeout(Duration::from_secs(2), peer.read_u8())
                .await
                .unwrap()
                .unwrap_err()
                .kind(),
            io::ErrorKind::UnexpectedEof
        );
    });
}

#[test]
fn cancelling_quota_wakes_watchdog_before_its_deadline() {
    let guard = quota(100, 1);
    let watchdog = guard.start_watchdog().unwrap();
    guard.cancel();
    watchdog.join().unwrap();
    let receipt = guard.snapshot().unwrap();
    assert!(receipt.stopped);
    assert!(!receipt.timed_out);
}
