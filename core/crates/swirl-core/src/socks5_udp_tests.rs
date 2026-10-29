use super::*;

#[tokio::test]
async fn queued_reply_cannot_outlive_its_control_worker() {
    let relay = UdpSocket::bind("127.0.0.1:0").await.unwrap();
    let client = UdpSocket::bind("127.0.0.1:0").await.unwrap();
    let (lifetime, alive) = watch::channel(());
    let reply = Reply {
        packet: b"must-not-forward".to_vec(),
        payload_len: 16,
        alive,
        cancellation: None,
    };
    drop(lifetime);
    assert!(
        reply
            .send_to(&relay, client.local_addr().unwrap())
            .await
            .is_err()
    );
    let mut bytes = [0; 32];
    assert!(
        tokio::time::timeout(Duration::from_millis(50), client.recv_from(&mut bytes))
            .await
            .is_err()
    );
}

#[tokio::test]
async fn queued_reply_revoked_before_worker_exit_cannot_forward() {
    let relay = UdpSocket::bind("127.0.0.1:0").await.unwrap();
    let client = UdpSocket::bind("127.0.0.1:0").await.unwrap();
    let (_lifetime, alive) = watch::channel(());
    let (revoke, cancellation) = watch::channel(false);
    let reply = Reply {
        packet: b"revoked-payload".to_vec(),
        payload_len: 15,
        alive,
        cancellation: Some(cancellation),
    };
    revoke.send(true).unwrap();
    assert!(
        reply
            .send_to(&relay, client.local_addr().unwrap())
            .await
            .is_err()
    );
    let mut bytes = [0; 32];
    assert!(
        matches!(client.try_recv_from(&mut bytes), Err(error) if error.kind() == std::io::ErrorKind::WouldBlock)
    );
}

#[tokio::test]
async fn queued_reply_with_closed_revocation_owner_cannot_forward() {
    let relay = UdpSocket::bind("127.0.0.1:0").await.unwrap();
    let client = UdpSocket::bind("127.0.0.1:0").await.unwrap();
    let (_lifetime, alive) = watch::channel(());
    let (revoke, cancellation) = watch::channel(false);
    let reply = Reply {
        packet: b"revoked-owner".to_vec(),
        payload_len: 13,
        alive,
        cancellation: Some(cancellation),
    };
    drop(revoke);
    assert!(
        reply
            .send_to(&relay, client.local_addr().unwrap())
            .await
            .is_err()
    );
}

#[tokio::test]
async fn queued_reply_with_live_owner_and_no_revocation_preserves_payload() {
    let relay = UdpSocket::bind("127.0.0.1:0").await.unwrap();
    let client = UdpSocket::bind("127.0.0.1:0").await.unwrap();
    let (_lifetime, alive) = watch::channel(());
    let (_revoke, cancellation) = watch::channel(false);
    let expected = b"permitted-payload";
    let reply = Reply {
        packet: expected.to_vec(),
        payload_len: expected.len(),
        alive,
        cancellation: Some(cancellation),
    };
    assert!(
        matches!(reply.send_to(&relay, client.local_addr().unwrap()).await, Ok(size) if size == expected.len())
    );
    let mut bytes = [0; 64];
    let (size, _) = tokio::time::timeout(Duration::from_secs(2), client.recv_from(&mut bytes))
        .await
        .unwrap()
        .unwrap();
    assert!(bytes[..size] == expected[..]);
}

#[tokio::test]
async fn dynamic_pool_shutdown_joins_cancelled_workers_and_drains_replies() {
    let mut pool = Pool::dynamic(Arc::new(Counters::default()), Arc::new(Counters::default()));
    assert!(pool.plan.is_none());
    let (started, ready) = tokio::sync::oneshot::channel();
    let (finished, done) = tokio::sync::oneshot::channel();
    struct Completion(Option<tokio::sync::oneshot::Sender<()>>);
    impl Drop for Completion {
        fn drop(&mut self) {
            if let Some(sender) = self.0.take() {
                let _ = sender.send(());
            }
        }
    }
    pool.workers.spawn(async move {
        let _completion = Completion(Some(finished));
        let _ = started.send(());
        std::future::pending::<()>().await;
    });
    ready.await.unwrap();
    let (_lifetime, alive) = watch::channel(());
    assert!(
        pool.reply_sender
            .try_send(Reply {
                packet: vec![0],
                payload_len: 1,
                alive,
                cancellation: None,
            })
            .is_ok()
    );
    pool.shutdown().await;
    assert!(done.await.is_ok());
    assert!(
        pool.workers.is_empty()
            && pool.nodes.is_empty()
            && pool.replies.is_empty()
            && pool.plan.is_none()
    );
}
