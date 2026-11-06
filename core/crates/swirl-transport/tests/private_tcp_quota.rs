#![cfg(feature = "private-acceptance")]
use swirl_transport::{bind_udp, bind_udp_inbound, connect_tcp, egress::budget};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};

// Separate test executable gives the irreversible process guard its own process.
#[tokio::test]
async fn installed_guard_covers_spawned_connectors_and_refuses_udp_and_reset() {
    let guard = budget::install(32, 2).unwrap();
    assert!(budget::install(64, 2).is_err());
    let local = "127.0.0.1:0".parse().unwrap();
    assert!(bind_udp(local).await.is_err());
    assert!(bind_udp_inbound(local).await.is_err());
    let listener = TcpListener::bind(local).await.unwrap();
    let address = listener.local_addr().unwrap();
    let writer = tokio::spawn(async move {
        let mut client = connect_tcp(address).await.unwrap();
        client.write(&[1; 64]).await.unwrap()
    });
    let bytes = tokio::time::timeout(std::time::Duration::from_secs(5), async {
        let (mut peer, _) = listener.accept().await.unwrap();
        let mut bytes = Vec::new();
        peer.read_to_end(&mut bytes).await.unwrap();
        bytes
    })
    .await
    .expect("quota test peer did not complete");
    assert_eq!(writer.await.unwrap(), 32);
    assert_eq!(bytes.len(), 32);
    let snapshot = guard.snapshot().unwrap();
    assert_eq!(
        (snapshot.upload, snapshot.download, snapshot.stopped),
        (32, 0, true)
    );
    assert!(connect_tcp(address).await.is_err());
    assert!(budget::install(32, 2).is_err());
}
