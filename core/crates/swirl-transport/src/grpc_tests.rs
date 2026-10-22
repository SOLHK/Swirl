use super::*;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

#[test]
fn paths_follow_xray_normal_and_custom_service_semantics() {
    let mut config = Config {
        authority: "server.example".into(),
        service_name: "hello/world!".into(),
        ..Default::default()
    };
    assert_eq!(service_path(&config).unwrap(), "/hello%2Fworld%21/Tun");
    config.mode = Mode::TunMulti;
    assert_eq!(service_path(&config).unwrap(), "/hello%2Fworld%21/TunMulti");
    config.service_name = "/m y/service/tun_name|multi!".into();
    assert_eq!(service_path(&config).unwrap(), "/m%20y/service/multi%21");
    config.mode = Mode::Tun;
    assert_eq!(service_path(&config).unwrap(), "/m%20y/service/tun_name");
    config.service_name = "/single".into();
    assert!(service_path(&config).is_err());
}

#[test]
fn protocol_is_bidirectional_post_and_headers_cannot_replace_framing() {
    let mut config = Config {
        authority: "[::1]:443".into(),
        service_name: "swirl".into(),
        ..Default::default()
    };
    let req = request(&config, true).unwrap();
    assert_eq!(req.method(), "POST");
    assert_eq!(req.uri().path(), "/swirl/Tun");
    assert_eq!(req.headers()["te"], "trailers");
    assert_eq!(req.headers()["content-type"], "application/grpc");
    config
        .headers
        .push(("Content-Type".into(), "text/plain".into()));
    assert!(request(&config, true).is_err());
}

#[test]
fn known_wire_bytes_singular_last_value_multi_concatenation_and_unknown_fields() {
    assert_eq!(
        &encode_message(b"abc")[..],
        b"\x00\x00\x00\x00\x05\x0a\x03abc"
    );
    let message = b"\x0a\x03one\x10\x7f\x0a\x03two\x1d\x00\x00\x00\x00";
    assert_eq!(decode_message(message, Mode::Tun).unwrap(), "two");
    assert_eq!(decode_message(message, Mode::TunMulti).unwrap(), "onetwo");
    for invalid in [
        &b"\x00"[..],
        &b"\x08\x01"[..],
        &b"\x0a\xff\xff\xff\xff\xff\xff\xff\xff\xff\x02"[..],
        &b"\x0a\x03a"[..],
    ] {
        assert!(decode_message(invalid, Mode::Tun).is_err());
    }
}

#[tokio::test]
async fn arbitrary_envelope_fragmentation_preserves_binary_stream() {
    let (client, mut peer) = tokio::io::duplex(7);
    let payload: Vec<u8> = (0..65537).map(|i| (i % 251) as u8).collect();
    let frame = encode_message(&payload);
    let writer = tokio::spawn(async move {
        for part in frame.chunks(3) {
            peer.write_all(part).await.unwrap();
        }
        peer.shutdown().await.unwrap();
    });
    let mut stream = GrpcStream::new(Box::new(client), Mode::Tun);
    let mut output = Vec::new();
    stream.read_to_end(&mut output).await.unwrap();
    assert_eq!(output, payload);
    writer.await.unwrap();
}

#[tokio::test]
async fn oversized_compressed_truncated_envelopes_fail() {
    for (frame, expected) in [
        (vec![1, 0, 0, 0, 0], "GrpcCompressionUnsupported"),
        (vec![0, 0xff, 0xff, 0xff, 0xff], "GrpcMessageTooLarge"),
        (vec![0, 0], "GrpcEnvelopeTruncated"),
        (vec![0, 0, 0, 0, 4, 10, 2, 65], "GrpcMessageTruncated"),
    ] {
        let (client, mut peer) = tokio::io::duplex(32);
        peer.write_all(&frame).await.unwrap();
        peer.shutdown().await.unwrap();
        let mut stream = GrpcStream::new(Box::new(client), Mode::Tun);
        assert_eq!(stream.read_u8().await.unwrap_err().to_string(), expected);
    }
}

#[tokio::test]
async fn write_then_read_without_flush_delivers_pending_frame() {
    let (client, mut peer) = tokio::io::duplex(3);
    let server = tokio::spawn(async move {
        let mut expected = [0; 10];
        peer.read_exact(&mut expected).await.unwrap();
        assert_eq!(&expected, b"\x00\x00\x00\x00\x05\x0a\x03abc");
        peer.write_all(&encode_message(b"ok")).await.unwrap();
        peer.shutdown().await.unwrap();
    });
    let mut stream = GrpcStream::new(Box::new(client), Mode::Tun);
    stream.write_all(b"abc").await.unwrap();
    let mut result = Vec::new();
    tokio::time::timeout(Duration::from_secs(1), stream.read_to_end(&mut result))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(result, b"ok");
    server.await.unwrap();
}

#[tokio::test(flavor = "current_thread")]
async fn early_response_preserves_reverse_bytes_with_a_blocked_upload() {
    for terminal_status in ["0", "13"] {
        let (client, server) = tokio::io::duplex(4096);
        let peer = tokio::spawn(async move {
            let mut connection = h2::server::Builder::new()
                .initial_window_size(1)
                .handshake(server)
                .await
                .unwrap();
            let (mut request, mut respond) = connection.accept().await.unwrap().unwrap();
            let handler = tokio::spawn(async move {
                let mut response = respond
                    .send_response(
                        http::Response::builder()
                            .header("content-type", "application/grpc")
                            .body(())
                            .unwrap(),
                        false,
                    )
                    .unwrap();
                // Receiving this message proves the client processed SETTINGS
                // with the one-byte upload window before it starts its upload.
                response.send_data(encode_message(b"ready"), false).unwrap();
                let partial = request.body_mut().data().await.unwrap().unwrap();
                assert_eq!(partial.len(), 1);
                response.send_data(encode_message(b"reply"), false).unwrap();
                let mut trailers = http::HeaderMap::new();
                trailers.insert(
                    "grpc-status",
                    http::HeaderValue::from_static(terminal_status),
                );
                response.send_trailers(trailers).unwrap();
                // Abandoning the incomplete request after a complete response
                // schedules the normal HTTP/2 NO_ERROR reset.
                drop(request);
            });
            while connection.accept().await.is_some() {}
            handler.await.unwrap();
        });
        let inner = h2_stream::connect(
            Box::new(client),
            request(
                &Config {
                    authority: "fixture.test".into(),
                    ..Default::default()
                },
                false,
            )
            .unwrap(),
            h2_stream::ResponseKind::Grpc,
        )
        .await
        .unwrap();
        let mut stream = GrpcStream::new(inner, Mode::Tun);
        let mut ready = [0; 5];
        stream.read_exact(&mut ready).await.unwrap();
        assert_eq!(&ready, b"ready");
        stream.write_all(&vec![42; WRITE_CHUNK]).await.unwrap();
        assert!(!stream.pending_write.is_empty());
        let mut response = Vec::new();
        let result =
            tokio::time::timeout(Duration::from_secs(1), stream.read_to_end(&mut response))
                .await
                .unwrap();
        assert_eq!(response, b"reply");
        if terminal_status == "0" {
            result.unwrap();
        } else {
            assert_eq!(result.unwrap_err().to_string(), "GrpcStatus");
        }
        // Accepted-but-unsent upload bytes must remain a write-side failure.
        assert!(stream.flush().await.is_err());
        assert!(stream.shutdown().await.is_err());
        drop(stream);
        tokio::time::timeout(Duration::from_secs(2), peer)
            .await
            .unwrap()
            .unwrap();
    }
}
