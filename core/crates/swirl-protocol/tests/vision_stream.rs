use std::{
    io,
    pin::Pin,
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
    task::{Context, Poll},
    time::Duration,
};
use swirl_protocol::vision::{
    Command, Decoder, Encoder,
    stream::{ReadMode, Role, Stream, WRITE_CONTENT_LIMIT},
};
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, ReadBuf};

const UUID: [u8; 16] = [0x41; 16];

struct Chopped<S> {
    inner: S,
    width: usize,
    pause: bool,
    drops: Arc<AtomicUsize>,
}

impl<S> Chopped<S> {
    fn new(inner: S, width: usize, drops: Arc<AtomicUsize>) -> Self {
        Self {
            inner,
            width,
            pause: false,
            drops,
        }
    }
}

impl<S> Drop for Chopped<S> {
    fn drop(&mut self) {
        self.drops.fetch_add(1, Ordering::SeqCst);
    }
}

impl<S: AsyncRead + Unpin> AsyncRead for Chopped<S> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        let mut buffer = [0; 257];
        let count = this.width.min(buffer.len()).min(out.remaining());
        let mut part = ReadBuf::new(&mut buffer[..count]);
        match Pin::new(&mut this.inner).poll_read(cx, &mut part) {
            Poll::Ready(Ok(())) => {
                out.put_slice(part.filled());
                Poll::Ready(Ok(()))
            }
            other => other,
        }
    }
}

impl<S: AsyncWrite + Unpin> AsyncWrite for Chopped<S> {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        this.pause = !this.pause;
        if this.pause {
            cx.waker().wake_by_ref();
            return Poll::Pending;
        }
        let count = this.width.min(bytes.len());
        Pin::new(&mut this.inner).poll_write(cx, &bytes[..count])
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_flush(cx)
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_shutdown(cx)
    }
}

fn data(length: usize, seed: usize) -> Vec<u8> {
    (0..length)
        .map(|index| ((index * 37 + seed) % 251) as u8)
        .collect()
}

fn unframe(wire: &[u8]) -> Vec<u8> {
    let mut decoder = Decoder::new(UUID);
    let mut position = 0;
    let mut output = Vec::new();
    while position < wire.len() {
        let step = decoder.decode(&wire[position..]).unwrap();
        output.extend_from_slice(step.payload);
        position += step.consumed;
        if step.boundary == Some(Command::EndPadding) {
            output.extend_from_slice(&wire[position..]);
            return output;
        }
        assert_ne!(step.boundary, Some(Command::DirectRequested));
    }
    decoder.finish().unwrap();
    output
}

#[tokio::test]
async fn large_bidirectional_transfer_survives_partial_writes_and_backpressure() {
    tokio::time::timeout(Duration::from_secs(20), async {
        let (a, b) = tokio::io::duplex(23);
        let drops = Arc::new(AtomicUsize::new(0));
        let mut client = Stream::new(Chopped::new(a, 7, drops.clone()), UUID, Role::Client);
        let mut server = Stream::new(Chopped::new(b, 11, drops.clone()), UUID, Role::Server);
        let upload = data(262_147, 4);
        let download = data(196_631, 7);
        let (mut cr, mut cw) = tokio::io::split(&mut client);
        let (mut sr, mut sw) = tokio::io::split(&mut server);
        let mut received_up = Vec::new();
        let mut received_down = Vec::new();
        tokio::try_join!(
            async {
                cw.write_all(&upload).await?;
                cw.shutdown().await
            },
            async {
                sw.write_all(&download).await?;
                sw.shutdown().await
            },
            async { cr.read_to_end(&mut received_down).await.map(|_| ()) },
            async { sr.read_to_end(&mut received_up).await.map(|_| ()) },
        )
        .unwrap();
        assert_eq!(received_up, upload);
        assert_eq!(received_down, download);
        drop((cr, cw, sr, sw));
        assert_eq!(client.buffered_bytes(), 0);
        assert_eq!(server.buffered_bytes(), 0);
        drop((client, server));
        assert_eq!(drops.load(Ordering::SeqCst), 2);
    })
    .await
    .unwrap();
}

#[tokio::test]
async fn terminal_frame_tail_and_many_padding_frames_keep_exact_order() {
    let mut encoder = Encoder::new(UUID);
    let mut wire = encoder.frame(Command::Continue, b"", &[0x99; 127]).unwrap();
    let mut expected = Vec::new();
    for index in 0..87 {
        let payload = data(113 + index, index);
        wire.extend(
            encoder
                .frame(Command::Continue, &payload, &data(index % 17, 9))
                .unwrap(),
        );
        expected.extend(payload);
    }
    wire.extend(
        encoder
            .frame(Command::EndPadding, b"terminal", &[0x53; 11])
            .unwrap(),
    );
    expected.extend(b"terminal");
    let tail = [
        b"untouched-tail".as_slice(),
        UUID.as_slice(),
        &[2, 0, 0, 0, 0],
        &data(32771, 8),
    ]
    .concat();
    wire.extend(&tail);
    expected.extend(tail);
    for width in [1, 3, 31, 257] {
        let (a, mut b) = tokio::io::duplex(71);
        let mut stream = Stream::new(
            Chopped::new(a, width, Arc::new(AtomicUsize::new(0))),
            UUID,
            Role::Client,
        );
        let send = async {
            b.write_all(&wire).await.unwrap();
            b.shutdown().await.unwrap();
        };
        let receive = async {
            let mut actual = Vec::new();
            let mut chunk = [0; 19];
            loop {
                let count = stream.read(&mut chunk).await.unwrap();
                if count == 0 {
                    break;
                }
                actual.extend_from_slice(&chunk[..count]);
                assert!(stream.buffered_bytes() <= 2 * 8192);
            }
            assert_eq!(actual, expected);
            assert_eq!(stream.read_mode(), ReadMode::Closed);
        };
        tokio::time::timeout(Duration::from_secs(10), async {
            tokio::join!(send, receive);
        })
        .await
        .unwrap();
    }
}

#[tokio::test]
async fn paused_reader_limits_writer_to_one_owned_frame_and_resumes_without_replay() {
    let (a, mut b) = tokio::io::duplex(7);
    let mut stream = Stream::new(a, UUID, Role::Client);
    let first = data(WRITE_CONTENT_LIMIT, 2);
    assert_eq!(stream.write(&first).await.unwrap(), first.len());
    assert!(stream.buffered_bytes() <= WRITE_CONTENT_LIMIT + 16 + 5 + 255);
    assert!(
        tokio::time::timeout(Duration::from_millis(30), stream.write(b"second"))
            .await
            .is_err()
    );
    assert!(stream.buffered_bytes() <= WRITE_CONTENT_LIMIT + 16 + 5 + 255);
    let read = tokio::spawn(async move {
        let mut wire = Vec::new();
        b.read_to_end(&mut wire).await.unwrap();
        wire
    });
    stream.write_all(b"second").await.unwrap();
    stream.shutdown().await.unwrap();
    let wire = read.await.unwrap();
    assert_eq!(unframe(&wire), [first, b"second".to_vec()].concat());
    assert!(!stream.write_padding_active());
}

#[tokio::test]
async fn cancelling_flush_keeps_the_exact_partial_wire_offset() {
    let (a, mut b) = tokio::io::duplex(9);
    let mut stream = Stream::new(a, UUID, Role::Client);
    let payload = data(1027, 3);
    stream.write_all(&payload).await.unwrap();
    assert!(
        tokio::time::timeout(Duration::from_millis(30), stream.flush())
            .await
            .is_err()
    );
    let receive = tokio::spawn(async move {
        let mut wire = Vec::new();
        b.read_to_end(&mut wire).await.unwrap();
        wire
    });
    stream.flush().await.unwrap();
    stream.shutdown().await.unwrap();
    assert_eq!(unframe(&receive.await.unwrap()), payload);
}

#[tokio::test]
async fn cancelling_read_keeps_partial_uuid_and_padding_state() {
    let (a, mut b) = tokio::io::duplex(4096);
    let mut stream = Stream::new(a, UUID, Role::Client);
    let wire = Encoder::new(UUID)
        .frame(Command::EndPadding, b"after-resume", &[0x25; 43])
        .unwrap();
    b.write_all(&wire[..7]).await.unwrap();
    let mut out = [0; 64];
    assert!(
        tokio::time::timeout(Duration::from_millis(30), stream.read(&mut out))
            .await
            .is_err()
    );
    b.write_all(&wire[7..wire.len() - 1]).await.unwrap();
    let count = stream.read(&mut out).await.unwrap();
    assert_eq!(&out[..count], b"after-resume");
    assert!(
        tokio::time::timeout(Duration::from_millis(30), stream.read(&mut out))
            .await
            .is_err()
    );
    b.write_all(&wire[wire.len() - 1..]).await.unwrap();
    b.write_all(b"tail").await.unwrap();
    b.shutdown().await.unwrap();
    let mut remainder = Vec::new();
    stream.read_to_end(&mut remainder).await.unwrap();
    assert_eq!(remainder, b"tail");
}

#[tokio::test]
async fn upload_half_close_keeps_downlink_alive_and_cannot_be_reopened() {
    let (a, b) = tokio::io::duplex(47);
    let mut client = Stream::new(a, UUID, Role::Client);
    let mut server = Stream::new(b, UUID, Role::Server);
    tokio::time::timeout(Duration::from_secs(5), async {
        tokio::join!(
            async {
                client.write_all(b"complete upload").await.unwrap();
                client.shutdown().await.unwrap();
                client.shutdown().await.unwrap();
                assert_eq!(
                    client.write_all(b"forbidden").await.unwrap_err().kind(),
                    io::ErrorKind::BrokenPipe
                );
                let mut reply = Vec::new();
                client.read_to_end(&mut reply).await.unwrap();
                assert_eq!(reply, b"response after upload half-close");
            },
            async {
                let mut request = Vec::new();
                server.read_to_end(&mut request).await.unwrap();
                assert_eq!(request, b"complete upload");
                server
                    .write_all(b"response after upload half-close")
                    .await
                    .unwrap();
                server.shutdown().await.unwrap();
            },
        );
    })
    .await
    .unwrap();
}

#[tokio::test]
async fn direct_command_drops_owned_stream_and_never_releases_terminal_tail() {
    let (a, mut b) = tokio::io::duplex(4096);
    let drops = Arc::new(AtomicUsize::new(0));
    let mut stream = Stream::new(Chopped::new(a, 1, drops.clone()), UUID, Role::Client);
    let mut wire = Encoder::new(UUID)
        .frame(Command::DirectRequested, b"terminal-data", b"pad")
        .unwrap();
    wire.extend(b"raw-looking-unowned-tail");
    b.write_all(&wire).await.unwrap();
    let mut out = [0; 128];
    let error = stream.read(&mut out).await.unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
    assert_eq!(error.to_string(), "VisionDirectOwnershipUnavailable");
    assert_eq!(out, [0; 128]);
    assert_eq!(stream.read_mode(), ReadMode::DirectRequested);
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    assert_eq!(
        stream.write(b"no fallback").await.unwrap_err().kind(),
        io::ErrorKind::PermissionDenied
    );
    assert_eq!(b.read(&mut out).await.unwrap(), 0);
}

#[tokio::test]
async fn invalid_uuid_or_command_is_fatal_in_both_directions() {
    for mutate in [0, 16] {
        let (a, mut b) = tokio::io::duplex(4096);
        let mut stream = Stream::new(a, UUID, Role::Client);
        let mut wire = Encoder::new(UUID)
            .frame(Command::EndPadding, b"hidden", b"")
            .unwrap();
        wire[mutate] ^= 0xff;
        b.write_all(&wire).await.unwrap();
        let mut out = [0; 128];
        assert_eq!(
            stream.read(&mut out).await.unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(
            stream.write(b"no").await.unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(out, [0; 128]);
    }
}

#[tokio::test]
async fn incomplete_direct_frame_is_rejected_before_releasing_terminal_content() {
    let wire = Encoder::new(UUID)
        .frame(
            Command::DirectRequested,
            b"cannot-pass-before-boundary",
            &[0x31; 127],
        )
        .unwrap();
    for length in [21, 22, 39, wire.len() - 1] {
        let (a, mut b) = tokio::io::duplex(4096);
        let mut stream = Stream::new(a, UUID, Role::Client);
        b.write_all(&wire[..length]).await.unwrap();
        let mut out = [0; 128];
        let error = tokio::time::timeout(Duration::from_secs(1), stream.read(&mut out))
            .await
            .unwrap()
            .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
        assert_eq!(out, [0; 128]);
        assert_eq!(stream.read_mode(), ReadMode::DirectRequested);
    }
}

#[tokio::test]
async fn eof_in_every_partial_frame_position_remains_an_error() {
    let wire = Encoder::new(UUID)
        .frame(Command::Continue, b"content", b"padding")
        .unwrap();
    for length in 1..wire.len() {
        let (a, mut b) = tokio::io::duplex(4096);
        let mut stream = Stream::new(a, UUID, Role::Client);
        b.write_all(&wire[..length]).await.unwrap();
        b.shutdown().await.unwrap();
        let error = stream.read_to_end(&mut Vec::new()).await.unwrap_err();
        assert_eq!(
            error.kind(),
            io::ErrorKind::UnexpectedEof,
            "offset {length}"
        );
    }
}

#[tokio::test]
async fn abort_releases_paused_transport_and_cannot_resume() {
    let (a, mut b) = tokio::io::duplex(7);
    let drops = Arc::new(AtomicUsize::new(0));
    let mut stream = Stream::new(Chopped::new(a, 3, drops.clone()), UUID, Role::Client);
    stream.write_all(&data(4096, 1)).await.unwrap();
    assert!(
        tokio::time::timeout(Duration::from_millis(30), stream.flush())
            .await
            .is_err()
    );
    stream.abort();
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    assert_eq!(stream.buffered_bytes(), 0);
    let mut remainder = Vec::new();
    tokio::time::timeout(Duration::from_secs(1), b.read_to_end(&mut remainder))
        .await
        .unwrap()
        .unwrap();
    assert!(remainder.len() <= 7);
    assert_eq!(
        stream.flush().await.unwrap_err().kind(),
        io::ErrorKind::Interrupted
    );
    assert_eq!(
        stream.shutdown().await.unwrap_err().kind(),
        io::ErrorKind::Interrupted
    );
}

#[tokio::test]
async fn abort_releases_partial_inner_tls_hello_and_pending_frame_memory() {
    let (a, mut b) = tokio::io::duplex(7);
    let drops = Arc::new(AtomicUsize::new(0));
    let mut stream = Stream::new(Chopped::new(a, 3, drops.clone()), UUID, Role::Client);
    // First record of an unfinished, bounded 60,000-byte ClientHello.
    let mut prefix = vec![22, 3, 3, 64, 0, 1, 0, 0xea, 0x60];
    prefix.extend([0x53; 12_000]);
    stream.write_all(&prefix).await.unwrap();
    assert!(stream.inspection().buffered_bytes() > 12_000);
    assert!(
        tokio::time::timeout(Duration::from_millis(30), stream.flush())
            .await
            .is_err()
    );
    stream.abort();
    assert_eq!(stream.inspection().buffered_bytes(), 0);
    assert_eq!(stream.buffered_bytes(), 0);
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    let mut tail = Vec::new();
    tokio::time::timeout(Duration::from_secs(1), b.read_to_end(&mut tail))
        .await
        .unwrap()
        .unwrap();
    assert!(tail.len() <= 7);
}

struct FailingOuter {
    read_error: io::ErrorKind,
    drops: Arc<AtomicUsize>,
}

impl Drop for FailingOuter {
    fn drop(&mut self) {
        self.drops.fetch_add(1, Ordering::SeqCst);
    }
}

impl AsyncRead for FailingOuter {
    fn poll_read(
        self: Pin<&mut Self>,
        _: &mut Context<'_>,
        _: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        Poll::Ready(Err(self.read_error.into()))
    }
}

impl AsyncWrite for FailingOuter {
    fn poll_write(self: Pin<&mut Self>, _: &mut Context<'_>, _: &[u8]) -> Poll<io::Result<usize>> {
        Poll::Ready(Ok(0))
    }
    fn poll_flush(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> {
        Poll::Ready(Ok(()))
    }
    fn poll_shutdown(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> {
        Poll::Ready(Ok(()))
    }
}

#[tokio::test]
async fn outer_tls_truncation_is_not_converted_to_clean_framing_eof() {
    for kind in [
        io::ErrorKind::UnexpectedEof,
        io::ErrorKind::TimedOut,
        io::ErrorKind::ConnectionReset,
    ] {
        let drops = Arc::new(AtomicUsize::new(0));
        let mut stream = Stream::new(
            FailingOuter {
                read_error: kind,
                drops: drops.clone(),
            },
            UUID,
            Role::Client,
        );
        assert_eq!(stream.read(&mut [0; 1]).await.unwrap_err().kind(), kind);
        assert_eq!(drops.load(Ordering::SeqCst), 1);
        assert_eq!(stream.write(b"no").await.unwrap_err().kind(), kind);
    }
}

#[tokio::test]
async fn write_zero_drops_owner_instead_of_reencoding_or_spinning() {
    let drops = Arc::new(AtomicUsize::new(0));
    let mut stream = Stream::new(
        FailingOuter {
            read_error: io::ErrorKind::Other,
            drops: drops.clone(),
        },
        UUID,
        Role::Client,
    );
    stream.write_all(b"payload").await.unwrap();
    assert_eq!(
        stream.flush().await.unwrap_err().kind(),
        io::ErrorKind::WriteZero
    );
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    assert_eq!(stream.buffered_bytes(), 0);
}

#[tokio::test]
async fn client_component_uses_real_vless_flow_request_and_lazy_response_prefix() {
    let (a, mut b) = tokio::io::duplex(4096);
    let mut client = swirl_protocol::vision::client_over_authenticated(
        Box::new(a),
        "41414141-4141-4141-4141-414141414141",
        &swirl_protocol::Target {
            host: "127.0.0.1".into(),
            port: 443,
        },
        Duration::from_secs(1),
    )
    .await
    .unwrap();
    // A server may deliberately wait for application data before this prefix.
    let mut request = [0; 44];
    b.read_exact(&mut request).await.unwrap();
    assert_eq!(request[0], 0);
    assert_eq!(&request[1..17], &UUID);
    assert_eq!(&request[17..36], b"\x12\x0a\x10xtls-rprx-vision");
    assert_eq!(&request[36..], &[1, 1, 187, 1, 127, 0, 0, 1]);
    client.write_all(b"request body").await.unwrap();
    client.flush().await.unwrap();
    let mut first = [0; 4096];
    let count = b.read(&mut first).await.unwrap();
    assert_eq!(unframe(&first[..count]), b"request body");
    let mut response = vec![0, 0];
    response.extend(
        Encoder::new(UUID)
            .frame(Command::EndPadding, b"response body", b"padding")
            .unwrap(),
    );
    response.extend(b"tail");
    b.write_all(&response).await.unwrap();
    b.shutdown().await.unwrap();
    let mut bytes = Vec::new();
    client.read_to_end(&mut bytes).await.unwrap();
    assert_eq!(bytes, b"response bodytail");
}

#[tokio::test]
async fn invalid_vless_response_cannot_be_reinterpreted_as_vision_payload() {
    for prefix in [[1, 0], [0, 1]] {
        let (a, mut b) = tokio::io::duplex(4096);
        let mut client = swirl_protocol::vision::client_over_authenticated(
            Box::new(a),
            "41414141-4141-4141-4141-414141414141",
            &swirl_protocol::Target {
                host: "127.0.0.1".into(),
                port: 443,
            },
            Duration::from_secs(1),
        )
        .await
        .unwrap();
        let mut response = prefix.to_vec();
        response.extend(
            Encoder::new(UUID)
                .frame(Command::EndPadding, b"hidden", b"")
                .unwrap(),
        );
        b.write_all(&response).await.unwrap();
        let mut output = [0; 32];
        assert_eq!(
            client.read(&mut output).await.unwrap_err().kind(),
            io::ErrorKind::InvalidData
        );
        assert_eq!(output, [0; 32]);
    }
}
