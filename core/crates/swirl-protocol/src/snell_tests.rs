use super::*;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
const PSK: &str = "synthetic-snell-key";

fn response(data: &[u8], padding: usize) -> Vec<u8> {
    static NEXT_SALT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);
    let mut salt = [31; 16];
    salt[..8].copy_from_slice(
        &NEXT_SALT
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            .to_be_bytes(),
    );
    let mut cipher = Cipher::new(PSK.as_bytes(), &salt).unwrap();
    let mut header = vec![4, 0, 0];
    header.extend((padding as u16).to_be_bytes());
    header.extend((data.len() as u16).to_be_bytes());
    cipher.seal(&mut header).unwrap();
    let mut payload = data.to_vec();
    cipher.seal(&mut payload).unwrap();
    let mut body = vec![42; padding];
    body.extend(&payload);
    for index in (0..padding.min(payload.len())).step_by(2) {
        body.swap(index, padding + index);
    }
    [salt.to_vec(), header, body].concat()
}

#[tokio::test]
async fn fragmented_padded_ack_is_consumed_before_application_bytes() {
    let (client, mut peer) = tokio::io::duplex(37);
    let mut stream = Stream::new(Box::new(client), PSK).unwrap();
    let wire = response(b"\0authenticated target response", 511);
    let writer = tokio::spawn(async move {
        for byte in wire {
            peer.write_all(&[byte]).await.unwrap();
        }
    });
    let mut data = [0; 29];
    stream.read_exact(&mut data).await.unwrap();
    assert_eq!(&data, b"authenticated target response");
    writer.await.unwrap();
}

#[tokio::test]
async fn authentication_failure_never_exposes_plaintext_and_poisons_reader() {
    let (client, mut peer) = tokio::io::duplex(512);
    let mut stream = Stream::new(Box::new(client), PSK).unwrap();
    let mut wire = response(b"\0private plaintext", 0);
    *wire.last_mut().unwrap() ^= 1;
    peer.write_all(&wire).await.unwrap();
    let mut data = [0x55; 32];
    assert!(stream.read(&mut data).await.is_err());
    assert!(
        stream
            .write_all(b"not forwarded after authentication failure")
            .await
            .is_err()
    );
    assert_eq!(data, [0x55; 32]);
    assert!(stream.read(&mut data).await.is_err());
}

#[tokio::test]
async fn authenticated_response_cannot_be_replayed_on_another_connection() {
    let wire = response(b"\0ok", 0);
    let (first, mut peer) = tokio::io::duplex(512);
    let mut first = Stream::new(Box::new(first), PSK).unwrap();
    peer.write_all(&wire).await.unwrap();
    let mut data = [0; 2];
    first.read_exact(&mut data).await.unwrap();
    assert_eq!(&data, b"ok");
    let (second, mut peer) = tokio::io::duplex(512);
    let mut second = Stream::new(Box::new(second), PSK).unwrap();
    peer.write_all(&wire).await.unwrap();
    let mut untouched = [0x55; 2];
    assert!(second.read_exact(&mut untouched).await.is_err());
    assert_eq!(untouched, [0x55; 2]);
}

#[tokio::test]
async fn eof_is_clean_only_after_a_complete_authenticated_record() {
    let (client, mut peer) = tokio::io::duplex(512);
    let mut stream = Stream::new(Box::new(client), PSK).unwrap();
    peer.write_all(&response(b"\0ok", 0)).await.unwrap();
    peer.shutdown().await.unwrap();
    let mut data = Vec::new();
    stream.read_to_end(&mut data).await.unwrap();
    assert_eq!(data, b"ok");
    for keep in [0, 17, 40] {
        let (client, mut peer) = tokio::io::duplex(512);
        let mut stream = Stream::new(Box::new(client), PSK).unwrap();
        let wire = response(b"\0ok", 0);
        peer.write_all(&wire[..keep]).await.unwrap();
        peer.shutdown().await.unwrap();
        let mut data = Vec::new();
        assert_eq!(
            stream.read_to_end(&mut data).await.unwrap_err().kind(),
            io::ErrorKind::UnexpectedEof
        );
        assert!(data.is_empty());
    }
}

#[tokio::test(start_paused = true)]
async fn cancelled_read_preserves_partial_frame_and_its_original_deadline() {
    let (client, mut peer) = tokio::io::duplex(512);
    let mut stream = Stream::new(Box::new(client), PSK).unwrap();
    let wire = response(b"\0ok", 0);
    peer.write_all(&wire[..17]).await.unwrap();
    let started = tokio::time::Instant::now();
    let mut byte = [0];
    assert!(
        tokio::time::timeout(Duration::from_millis(1), stream.read_exact(&mut byte))
            .await
            .is_err()
    );
    let error = stream.read_exact(&mut byte).await.unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::TimedOut);
    assert_eq!(tokio::time::Instant::now() - started, FRAME_TIMEOUT);
}

#[tokio::test(start_paused = true)]
async fn cancelled_read_resumes_without_losing_ciphertext() {
    let (client, mut peer) = tokio::io::duplex(512);
    let mut stream = Stream::new(Box::new(client), PSK).unwrap();
    let wire = response(b"\0ok", 0);
    peer.write_all(&wire[..17]).await.unwrap();
    let mut data = [0; 2];
    assert!(
        tokio::time::timeout(Duration::from_millis(1), stream.read_exact(&mut data))
            .await
            .is_err()
    );
    peer.write_all(&wire[17..]).await.unwrap();
    stream.read_exact(&mut data).await.unwrap();
    assert_eq!(&data, b"ok");
}

#[test]
fn nonce_exhaustion_refuses_reuse() {
    let mut cipher = Cipher::new(PSK.as_bytes(), &[1; 16]).unwrap();
    cipher.nonce = [255; 12];
    cipher.seal(&mut vec![1]).unwrap();
    assert!(cipher.seal(&mut vec![2]).is_err());
}

#[test]
fn udp_reply_requires_complete_address_port_and_bounded_frame() {
    let (target, data) = parse_udp(&[4, 127, 0, 0, 1, 0, 53, 7, 8]).unwrap();
    assert_eq!(target.host, "127.0.0.1");
    assert_eq!(target.port, 53);
    assert_eq!(data, [7, 8]);
    for bytes in [
        vec![],
        vec![4; 6],
        vec![6; 18],
        vec![3; 20],
        vec![4, 127, 0, 0, 1, 0, 0],
        vec![4; PAYLOAD_LIMIT + 1],
    ] {
        assert!(parse_udp(&bytes).is_err());
    }
}
