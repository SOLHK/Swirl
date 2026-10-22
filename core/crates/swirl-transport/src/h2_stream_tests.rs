use super::*;
use std::{
    future::poll_fn,
    sync::atomic::{AtomicUsize, Ordering},
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    sync::oneshot,
    time::timeout,
};

fn request() -> Request<()> {
    Request::builder()
        .method("POST")
        .uri("http://example.test/native")
        .body(())
        .unwrap()
}

async fn send(send: &mut SendStream<Bytes>, bytes: Bytes) {
    let mut bytes = bytes;
    while !bytes.is_empty() {
        send.reserve_capacity(bytes.len().min(CHUNK));
        let capacity = poll_fn(|cx| send.poll_capacity(cx)).await.unwrap().unwrap();
        let n = capacity.min(bytes.len()).min(CHUNK);
        send.send_data(bytes.split_to(n), false).unwrap();
    }
}

async fn echo(mut request: Request<RecvStream>, mut response: h2::server::SendResponse<Bytes>) {
    let mut output = response.send_response(Response::new(()), false).unwrap();
    while let Some(bytes) = request.body_mut().data().await {
        let Ok(bytes) = bytes else {
            return;
        };
        let n = bytes.len();
        send(&mut output, bytes).await;
        request
            .body_mut()
            .flow_control()
            .release_capacity(n)
            .unwrap();
    }
    output.send_data(Bytes::new(), true).unwrap();
}

async fn exchange(mut stream: BoxStream, length: usize) {
    let payload: Vec<u8> = (0..length).map(|i| (i % 251) as u8).collect();
    let (mut read, mut write) = tokio::io::split(&mut stream);
    let upload = async {
        write.write_all(&payload).await.unwrap();
        write.shutdown().await.unwrap();
    };
    let download = async {
        let mut bytes = Vec::new();
        read.read_to_end(&mut bytes).await.unwrap();
        assert_eq!(bytes, payload);
    };
    timeout(Duration::from_secs(5), async {
        tokio::join!(upload, download);
    })
    .await
    .unwrap();
}

#[tokio::test]
async fn multi_megabyte_duplex_and_half_close_obey_flow_control() {
    let (client, server) = tokio::io::duplex(8192);
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::Builder::new()
            .initial_window_size(1024)
            .initial_connection_window_size(4096)
            .handshake(server)
            .await
            .unwrap();
        while let Some(Ok((request, response))) = connection.accept().await {
            tokio::spawn(echo(request, response));
        }
    });
    let stream = connect(Box::new(client), request(), ResponseKind::Raw)
        .await
        .unwrap();
    exchange(stream, 2 * 1024 * 1024 + 17).await;
    timeout(Duration::from_secs(1), peer)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn response_can_wait_for_first_request_bytes() {
    let (client, server) = tokio::io::duplex(4096);
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (mut request, mut respond) = connection.accept().await.unwrap().unwrap();
        let handler = tokio::spawn(async move {
            let bytes = request.body_mut().data().await.unwrap().unwrap();
            assert_eq!(bytes, "client-protocol-header");
            request
                .body_mut()
                .flow_control()
                .release_capacity(bytes.len())
                .unwrap();
            let mut response = respond.send_response(Response::new(()), false).unwrap();
            response
                .send_data(Bytes::from_static(b"accepted"), true)
                .unwrap();
        });
        while connection.accept().await.is_some() {}
        handler.await.unwrap();
    });
    let mut stream = connect(Box::new(client), request(), ResponseKind::Raw)
        .await
        .unwrap();
    stream.write_all(b"client-protocol-header").await.unwrap();
    stream.shutdown().await.unwrap();
    let mut result = Vec::new();
    timeout(Duration::from_secs(1), stream.read_to_end(&mut result))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(result, b"accepted");
    drop(stream);
    timeout(Duration::from_secs(1), peer)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test(flavor = "current_thread")]
async fn response_first_then_shutdown_drop_delivers_request_end_stream() {
    let (client, server) = tokio::io::duplex(4096);
    let (closed_tx, closed_rx) = oneshot::channel();
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (mut request, mut respond) = connection.accept().await.unwrap().unwrap();
        respond.send_response(Response::new(()), true).unwrap();
        let handler = tokio::spawn(async move {
            let closed = loop {
                match request.body_mut().data().await {
                    // END_STREAM may be carried by an empty DATA frame.
                    Some(Ok(bytes)) if bytes.is_empty() => continue,
                    None => break true,
                    _ => break false,
                }
            };
            closed_tx.send(closed).unwrap();
        });
        while connection.accept().await.is_some() {}
        handler.await.unwrap();
    });
    let mut stream = connect(Box::new(client), request(), ResponseKind::Raw)
        .await
        .unwrap();
    let mut bytes = Vec::new();
    stream.read_to_end(&mut bytes).await.unwrap();
    stream.shutdown().await.unwrap();
    drop(stream);
    assert!(
        timeout(Duration::from_secs(2), closed_rx)
            .await
            .unwrap()
            .unwrap(),
        "peer must observe request END_STREAM before socket closes"
    );
    timeout(Duration::from_secs(2), peer)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test(flavor = "current_thread")]
async fn shutdown_then_drop_keeps_final_data_with_an_unread_response() {
    let (client, server) = tokio::io::duplex(256);
    let payload = vec![0x5a; 16 * 1024 + 17];
    let expected = payload.clone();
    let (received_tx, received_rx) = oneshot::channel();
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (mut request, mut respond) = connection.accept().await.unwrap().unwrap();
        let _response = respond.send_response(Response::new(()), false).unwrap();
        let handler = tokio::spawn(async move {
            let mut received = Vec::new();
            while let Some(Ok(bytes)) = request.body_mut().data().await {
                received.extend_from_slice(&bytes);
                request
                    .body_mut()
                    .flow_control()
                    .release_capacity(bytes.len())
                    .unwrap();
            }
            received_tx.send(received).unwrap();
        });
        while connection.accept().await.is_some() {}
        handler.await.unwrap();
    });
    let mut stream = connect(Box::new(client), request(), ResponseKind::Raw)
        .await
        .unwrap();
    stream.write_all(&payload).await.unwrap();
    stream.shutdown().await.unwrap();
    // An upper TLS stream can finish after reading its own close_notify while
    // the HTTP/2 response remains unread. Dropping must preserve its last bytes.
    drop(stream);
    let received = timeout(Duration::from_secs(2), received_rx)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(received.len(), expected.len());
    assert!(received == expected);
    timeout(Duration::from_secs(2), peer)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn graceful_drop_bounds_an_unfinished_response_and_keeps_session_usable() {
    let (client, server) = tokio::io::duplex(4096);
    let (reset_tx, reset_rx) = oneshot::channel();
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (mut request, mut respond) = connection.accept().await.unwrap().unwrap();
        let mut response = respond.send_response(Response::new(()), false).unwrap();
        let stalled = tokio::spawn(async move {
            while let Some(bytes) = request.body_mut().data().await {
                let bytes = bytes.unwrap();
                request
                    .body_mut()
                    .flow_control()
                    .release_capacity(bytes.len())
                    .unwrap();
            }
            // The request ended normally, but this server never ends its
            // response. The bounded graceful drain must eventually cancel it.
            let reason = poll_fn(|cx| response.poll_reset(cx)).await.unwrap();
            reset_tx.send(reason).unwrap();
        });
        while let Some(Ok((request, response))) = connection.accept().await {
            tokio::spawn(echo(request, response));
        }
        stalled.await.unwrap();
    });
    let session = Session::connect(Box::new(client)).await.unwrap();
    let mut first = session.open(request(), ResponseKind::Raw).await.unwrap();
    first.write_all(b"final-request-bytes").await.unwrap();
    first.shutdown().await.unwrap();
    drop(first);
    assert_eq!(
        timeout(Duration::from_secs(3), reset_rx)
            .await
            .unwrap()
            .unwrap(),
        h2::Reason::CANCEL
    );
    assert_eq!(session.driver.slots.available_permits(), MAX_STREAMS);
    exchange(
        session.open(request(), ResponseKind::Raw).await.unwrap(),
        1024,
    )
    .await;
    drop(session);
    timeout(Duration::from_secs(2), peer)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn early_response_no_error_reset_does_not_hide_grpc_status() {
    for (grpc_status, expected_error) in [
        (Some("0"), None),
        (Some("13"), Some("GrpcStatus")),
        (None, Some("GrpcStatusMissing")),
    ] {
        let (client, server) = tokio::io::duplex(4096);
        let peer = tokio::spawn(async move {
            let mut connection = h2::server::handshake(server).await.unwrap();
            let (request, mut respond) = connection.accept().await.unwrap().unwrap();
            let mut response = respond
                .send_response(
                    Response::builder()
                        .header("content-type", "application/grpc")
                        .body(())
                        .unwrap(),
                    false,
                )
                .unwrap();
            response
                .send_data(Bytes::from_static(b"body"), false)
                .unwrap();
            if let Some(value) = grpc_status {
                let mut trailers = HeaderMap::new();
                trailers.insert("grpc-status", header::HeaderValue::from_static(value));
                response.send_trailers(trailers).unwrap();
            } else {
                response.send_data(Bytes::new(), true).unwrap();
            }
            // h2 emits the RFC-mandated NO_ERROR after the complete early
            // response when the server abandons the unfinished request.
            drop(request);
            drop(response);
            while connection.accept().await.is_some() {}
        });
        let mut stream = connect(Box::new(client), request(), ResponseKind::Grpc)
            .await
            .unwrap();
        let mut body = [0; 4];
        stream.read_exact(&mut body).await.unwrap();
        assert_eq!(&body, b"body");
        stream.shutdown().await.unwrap();
        let end = timeout(Duration::from_secs(1), stream.read(&mut [0]))
            .await
            .unwrap();
        if let Some(expected) = expected_error {
            assert_eq!(end.unwrap_err().to_string(), expected);
        } else {
            assert_eq!(end.unwrap(), 0);
        }
        drop(stream);
        timeout(Duration::from_secs(2), peer)
            .await
            .unwrap()
            .unwrap();
    }
}

#[tokio::test]
async fn initial_grpc_status_does_not_mask_missing_terminal_trailers() {
    let (client, server) = tokio::io::duplex(4096);
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (_, mut respond) = connection.accept().await.unwrap().unwrap();
        let mut output = respond
            .send_response(
                Response::builder()
                    .header("content-type", "application/grpc")
                    .header("grpc-status", "0")
                    .body(())
                    .unwrap(),
                false,
            )
            .unwrap();
        output
            .send_data(
                Bytes::from_static(b"invalid-body-after-terminal-status"),
                true,
            )
            .unwrap();
        while connection.accept().await.is_some() {}
    });
    let mut stream = connect(Box::new(client), request(), ResponseKind::Grpc)
        .await
        .unwrap();
    let mut bytes = Vec::new();
    let error = timeout(Duration::from_secs(1), stream.read_to_end(&mut bytes))
        .await
        .unwrap()
        .unwrap_err();
    assert_eq!(error.to_string(), "GrpcPrematureStatus");
    drop(stream);
    timeout(Duration::from_secs(2), peer)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn one_connection_serves_concurrent_independent_streams() {
    let (client, server) = tokio::io::duplex(8192);
    let accepted = Arc::new(AtomicUsize::new(0));
    let count = accepted.clone();
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        while let Some(Ok((request, response))) = connection.accept().await {
            count.fetch_add(1, Ordering::SeqCst);
            tokio::spawn(echo(request, response));
        }
    });
    let session = Session::connect(Box::new(client)).await.unwrap();
    let first = session.open(request(), ResponseKind::Raw).await.unwrap();
    let second = session.open(request(), ResponseKind::Raw).await.unwrap();
    tokio::join!(
        exchange(first, 128 * 1024),
        exchange(second, 256 * 1024 + 1)
    );
    assert_eq!(accepted.load(Ordering::SeqCst), 2);
    drop(session);
    timeout(Duration::from_secs(1), peer)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn cancelling_one_stream_resets_it_without_poisoning_session() {
    let (client, server) = tokio::io::duplex(8192);
    let (seen_tx, seen_rx) = oneshot::channel();
    let (reset_tx, reset_rx) = oneshot::channel();
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (mut first, _respond) = connection.accept().await.unwrap().unwrap();
        let first_handler = tokio::spawn(async move {
            seen_tx.send(()).unwrap();
            let error = first.body_mut().data().await.unwrap().unwrap_err();
            reset_tx.send(error.reason()).unwrap();
        });
        while let Some(Ok((request, response))) = connection.accept().await {
            tokio::spawn(echo(request, response));
        }
        first_handler.await.unwrap();
    });
    let session = Session::connect(Box::new(client)).await.unwrap();
    let stream = session.open(request(), ResponseKind::Raw).await.unwrap();
    timeout(Duration::from_secs(1), seen_rx)
        .await
        .unwrap()
        .unwrap();
    drop(stream);
    assert_eq!(
        timeout(Duration::from_secs(1), reset_rx)
            .await
            .unwrap()
            .unwrap(),
        Some(h2::Reason::CANCEL)
    );
    exchange(
        session.open(request(), ResponseKind::Raw).await.unwrap(),
        1024,
    )
    .await;
    drop(session);
    timeout(Duration::from_secs(1), peer)
        .await
        .unwrap()
        .unwrap();
}

async fn response_case(
    status_code: u16,
    grpc_status: Option<&'static str>,
    reset: bool,
) -> io::Error {
    let (client, server) = tokio::io::duplex(4096);
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (_, mut respond) = connection.accept().await.unwrap().unwrap();
        if reset {
            respond.send_reset(h2::Reason::REFUSED_STREAM);
        } else {
            let mut response = Response::builder()
                .status(status_code)
                .header("content-type", "application/grpc");
            if let Some(status) = grpc_status {
                response = response.header("grpc-status", status);
            }
            respond
                .send_response(response.body(()).unwrap(), true)
                .unwrap();
        }
        while connection.accept().await.is_some() {}
    });
    let mut stream = connect(Box::new(client), request(), ResponseKind::Grpc)
        .await
        .unwrap();
    let error = timeout(Duration::from_secs(1), stream.read_u8())
        .await
        .unwrap()
        .unwrap_err();
    drop(stream);
    timeout(Duration::from_secs(1), peer)
        .await
        .unwrap()
        .unwrap();
    error
}

#[tokio::test]
async fn non_success_http_grpc_status_and_rst_are_errors() {
    assert_eq!(
        response_case(403, None, false).await.kind(),
        io::ErrorKind::ConnectionRefused
    );
    assert_eq!(
        response_case(200, Some("12"), false).await.kind(),
        io::ErrorKind::PermissionDenied
    );
    assert_eq!(
        response_case(200, None, false).await.to_string(),
        "GrpcStatusMissing"
    );
    assert_eq!(
        response_case(200, None, true).await.to_string(),
        "Http2ResponseReset"
    );
}

#[tokio::test]
async fn grpc_nonzero_terminal_trailer_is_not_successful_eof() {
    let (client, server) = tokio::io::duplex(4096);
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (_, mut respond) = connection.accept().await.unwrap().unwrap();
        let mut stream = respond
            .send_response(
                Response::builder()
                    .header("content-type", "application/grpc")
                    .body(())
                    .unwrap(),
                false,
            )
            .unwrap();
        stream
            .send_data(Bytes::from_static(b"body-before-error"), false)
            .unwrap();
        let mut trailers = HeaderMap::new();
        trailers.insert("grpc-status", header::HeaderValue::from_static("13"));
        stream.send_trailers(trailers).unwrap();
        while connection.accept().await.is_some() {}
    });
    let mut stream = connect(Box::new(client), request(), ResponseKind::Grpc)
        .await
        .unwrap();
    let mut result = Vec::new();
    let error = timeout(Duration::from_secs(1), stream.read_to_end(&mut result))
        .await
        .unwrap()
        .unwrap_err();
    assert_eq!(result, b"body-before-error");
    assert_eq!(error.to_string(), "GrpcStatus");
    drop(stream);
    timeout(Duration::from_secs(1), peer)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn response_deadline_cancels_an_unresponsive_peer() {
    let (client, server) = tokio::io::duplex(4096);
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (_request, _response) = connection.accept().await.unwrap().unwrap();
        while connection.accept().await.is_some() {}
    });
    let mut stream = connect_with_timeout(
        Box::new(client),
        request(),
        ResponseKind::Raw,
        Duration::from_millis(30),
    )
    .await
    .unwrap();
    let error = timeout(Duration::from_secs(1), stream.read_u8())
        .await
        .unwrap()
        .unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::TimedOut);
    drop(stream);
    timeout(Duration::from_secs(1), peer)
        .await
        .unwrap()
        .unwrap();
}

#[tokio::test]
async fn goaway_rejects_new_stream_without_replaying_bytes() {
    let (client, server) = tokio::io::duplex(4096);
    let (sent_tx, sent_rx) = oneshot::channel();
    let peer = tokio::spawn(async move {
        let mut connection = h2::server::handshake(server).await.unwrap();
        let (_request, mut respond) = connection.accept().await.unwrap().unwrap();
        respond.send_response(Response::new(()), true).unwrap();
        connection.abrupt_shutdown(h2::Reason::NO_ERROR);
        let _ = connection.accept().await;
        let _ = sent_tx.send(());
    });
    let session = Session::connect(Box::new(client)).await.unwrap();
    let mut first = session.open(request(), ResponseKind::Raw).await.unwrap();
    let _ = timeout(Duration::from_secs(1), first.read_u8())
        .await
        .unwrap();
    timeout(Duration::from_secs(1), sent_rx)
        .await
        .unwrap()
        .unwrap();
    assert!(session.open(request(), ResponseKind::Raw).await.is_err());
    drop(first);
    drop(session);
    peer.await.unwrap();
}

#[test]
fn reserved_and_injected_headers_are_rejected() {
    for name in [
        "Connection",
        "host",
        "TE",
        "content-length",
        "upgrade",
        "transfer-encoding",
    ] {
        assert_eq!(
            append_headers(&mut request(), &[(name.into(), "x".into())], &[]),
            Err("Http2ReservedHeader")
        );
    }
    assert_eq!(
        append_headers(
            &mut request(),
            &[("x-good".into(), "value\r\nbad: x".into())],
            &[]
        ),
        Err("Http2Header")
    );
    assert_eq!(
        append_headers(
            &mut request(),
            &[("content-type".into(), "bad".into())],
            &["content-type"]
        ),
        Err("Http2ReservedHeader")
    );
}
