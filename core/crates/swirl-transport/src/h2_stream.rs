//! Bounded HTTP/2 request/response byte streams shared by native transports.
//!
//! HTTP framing, HPACK, SETTINGS, GOAWAY and flow control belong to the `h2`
//! library. This adapter owns the connection driver and never retries a stream
//! after bytes may have reached the peer.

use crate::BoxStream;
use bytes::{Buf, Bytes};
use h2::{RecvStream, SendStream, client};
use http::{HeaderMap, Request, Response, StatusCode, header};
use std::{
    future::{Future, poll_fn},
    io,
    pin::Pin,
    sync::Arc,
    task::{Context, Poll, ready},
    time::Duration,
};
use tokio::{
    io::{AsyncRead, AsyncWrite, ReadBuf},
    sync::{OwnedSemaphorePermit, Semaphore, mpsc, oneshot},
    task::JoinHandle,
    time::{Sleep, sleep, timeout},
};

const CHUNK: usize = 16 * 1024;
const RECEIVE_WINDOW: u32 = 64 * 1024;
const HEADER_TIMEOUT: Duration = Duration::from_secs(10);
const CLOSE_GRACE: Duration = Duration::from_secs(1);
const MAX_STREAMS: usize = 64;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ResponseKind {
    Raw,
    Grpc,
}

/// The last owner asks the existing driver to flush queued END_STREAM/RST
/// before closing. Its bounded grace period prevents both frame loss and a
/// permanent background task if the peer stops reading.
struct Driver {
    close: Option<oneshot::Sender<()>>,
    retired: mpsc::Sender<RetiredResponse>,
    slots: Arc<Semaphore>,
    _task: JoinHandle<()>,
}

impl Drop for Driver {
    fn drop(&mut self) {
        if let Some(close) = self.close.take() {
            let _ = close.send(());
        }
    }
}

/// Keep a gracefully shut down request alive while its final bytes reach the
/// peer. Dropping the response immediately would enqueue CANCEL, which can
/// cause a peer to discard DATA it has received but not yet consumed.
struct RetiredResponse {
    _send: SendStream<Bytes>,
    response: Option<client::ResponseFuture>,
    receive: Option<RecvStream>,
    unconsumed: usize,
    _slot: OwnedSemaphorePermit,
}

impl RetiredResponse {
    async fn drain(mut self) {
        let _ = timeout(CLOSE_GRACE, async {
            if self.receive.is_none() {
                let Some(response) = self.response.take() else {
                    return;
                };
                let Ok(response) = response.await else {
                    return;
                };
                self.receive = Some(response.into_body());
            }
            let receive = self.receive.as_mut().expect("retired response");
            if receive
                .flow_control()
                .release_capacity(self.unconsumed)
                .is_err()
            {
                return;
            }
            while let Some(Ok(bytes)) = receive.data().await {
                if receive
                    .flow_control()
                    .release_capacity(bytes.len())
                    .is_err()
                {
                    return;
                }
            }
            let _ = receive.trailers().await;
        })
        .await;
    }
}

/// A reusable HTTP/2 connection. Every opened request remains an independent
/// byte stream. Dropping one request resets only that request.
pub(crate) struct Session {
    sender: client::SendRequest<Bytes>,
    driver: Arc<Driver>,
}

impl Session {
    pub(crate) async fn connect(stream: BoxStream) -> Result<Self, &'static str> {
        let (sender, connection) = client::Builder::new()
            .enable_push(false)
            .initial_window_size(RECEIVE_WINDOW)
            .initial_connection_window_size(RECEIVE_WINDOW)
            .max_frame_size(CHUNK as u32)
            .max_send_buffer_size(RECEIVE_WINDOW as usize)
            .max_header_list_size(16 * 1024)
            .handshake(stream)
            .await
            .map_err(|_| "Http2Handshake")?;
        let (close, mut closed) = oneshot::channel();
        let (retired, mut retirement) = mpsc::channel::<RetiredResponse>(MAX_STREAMS);
        let task = tokio::spawn(async move {
            // The h2 library forwards connection failures to every pending
            // response/body future. No duplicate background error is invented.
            tokio::pin!(connection);
            let mut deadline = None::<Pin<Box<Sleep>>>;
            let mut draining: Vec<Pin<Box<dyn Future<Output = ()> + Send>>> = Vec::new();
            poll_fn(|cx| {
                if connection.as_mut().poll(cx).is_ready() {
                    return Poll::Ready(());
                }
                if deadline.is_none() && Pin::new(&mut closed).poll(cx).is_ready() {
                    deadline = Some(Box::pin(sleep(CLOSE_GRACE)));
                }
                if deadline
                    .as_mut()
                    .is_some_and(|deadline| deadline.as_mut().poll(cx).is_ready())
                {
                    return Poll::Ready(());
                }
                while let Poll::Ready(Some(response)) = retirement.poll_recv(cx) {
                    draining.push(Box::pin(response.drain()));
                }
                for i in (0..draining.len()).rev() {
                    if draining[i].as_mut().poll(cx).is_ready() {
                        drop(draining.swap_remove(i));
                    }
                }
                Poll::Pending
            })
            .await;
        });
        Ok(Self {
            sender,
            driver: Arc::new(Driver {
                close: Some(close),
                retired,
                slots: Arc::new(Semaphore::new(MAX_STREAMS)),
                _task: task,
            }),
        })
    }

    pub(crate) async fn open(
        &self,
        request: Request<()>,
        kind: ResponseKind,
    ) -> Result<BoxStream, &'static str> {
        self.open_with_timeout(request, kind, HEADER_TIMEOUT).await
    }

    pub(crate) async fn open_with_timeout(
        &self,
        request: Request<()>,
        kind: ResponseKind,
        header_timeout: Duration,
    ) -> Result<BoxStream, &'static str> {
        // The permit includes any graceful response drain, bounding both
        // active requests and retired responses on this session.
        let slot = self
            .driver
            .slots
            .clone()
            .try_acquire_owned()
            .map_err(|_| "Http2ConcurrentStreamsLimit")?;
        let mut sender = self
            .sender
            .clone()
            .ready()
            .await
            .map_err(|_| "Http2ConnectionClosed")?;
        let (response, send) = sender
            .send_request(request, false)
            .map_err(|_| "Http2Request")?;
        Ok(Box::new(H2Stream {
            send: Some(send),
            response: Some(response),
            receive: None,
            buffer: Bytes::new(),
            kind,
            initial_grpc_status: false,
            receive_done: false,
            send_done: false,
            failure: None,
            header_timeout,
            header_deadline: None,
            slot: Some(slot),
            _driver: self.driver.clone(),
        }))
    }
}

pub(crate) async fn connect(
    stream: BoxStream,
    request: Request<()>,
    kind: ResponseKind,
) -> Result<BoxStream, &'static str> {
    Session::connect(stream).await?.open(request, kind).await
}

pub(crate) async fn connect_with_timeout(
    stream: BoxStream,
    request: Request<()>,
    kind: ResponseKind,
    header_timeout: Duration,
) -> Result<BoxStream, &'static str> {
    Session::connect(stream)
        .await?
        .open_with_timeout(request, kind, header_timeout)
        .await
}

/// Apply user metadata without permitting HTTP/2 hop-by-hop fields, body
/// length overrides, pseudo headers or replacement of transport framing.
pub(crate) fn append_headers(
    request: &mut Request<()>,
    headers: &[(String, String)],
    reserved: &[&str],
) -> Result<(), &'static str> {
    if headers.len() > 64 {
        return Err("Http2HeadersTooLarge");
    }
    let mut length = 0usize;
    for (name, value) in headers {
        length = length
            .checked_add(name.len() + value.len() + 32)
            .ok_or("Http2HeadersTooLarge")?;
        if length > 16 * 1024 {
            return Err("Http2HeadersTooLarge");
        }
        let name = header::HeaderName::from_bytes(name.as_bytes()).map_err(|_| "Http2Header")?;
        if matches!(
            name.as_str(),
            "host"
                | "connection"
                | "proxy-connection"
                | "keep-alive"
                | "transfer-encoding"
                | "upgrade"
                | "content-length"
                | "te"
        ) || reserved.contains(&name.as_str())
        {
            return Err("Http2ReservedHeader");
        }
        let value = header::HeaderValue::from_str(value).map_err(|_| "Http2Header")?;
        request.headers_mut().append(name, value);
    }
    Ok(())
}

pub(crate) fn authority(value: &str) -> Result<http::uri::Authority, &'static str> {
    let parsed: http::uri::Authority = value.parse().map_err(|_| "Http2Authority")?;
    if parsed.host().is_empty() || value.contains('@') {
        return Err("Http2Authority");
    }
    Ok(parsed)
}

#[derive(Clone, Copy)]
struct Failure(io::ErrorKind, &'static str);

impl Failure {
    fn error(self) -> io::Error {
        io::Error::new(self.0, self.1)
    }
}

struct H2Stream {
    send: Option<SendStream<Bytes>>,
    response: Option<client::ResponseFuture>,
    receive: Option<RecvStream>,
    buffer: Bytes,
    kind: ResponseKind,
    initial_grpc_status: bool,
    receive_done: bool,
    send_done: bool,
    failure: Option<Failure>,
    header_timeout: Duration,
    header_deadline: Option<Pin<Box<Sleep>>>,
    slot: Option<OwnedSemaphorePermit>,
    _driver: Arc<Driver>,
}

fn status(headers: &HeaderMap) -> Result<bool, Failure> {
    let Some(value) = headers.get("grpc-status") else {
        return Ok(false);
    };
    if headers.get_all("grpc-status").iter().count() != 1 || value.as_bytes() != b"0" {
        return Err(Failure(io::ErrorKind::PermissionDenied, "GrpcStatus"));
    }
    Ok(true)
}

fn check_response(response: &Response<RecvStream>, kind: ResponseKind) -> Result<bool, Failure> {
    if response.status() != StatusCode::OK {
        return Err(Failure(
            io::ErrorKind::ConnectionRefused,
            "Http2ResponseStatus",
        ));
    }
    let headers = response.headers();
    if headers
        .get(header::CONTENT_ENCODING)
        .is_some_and(|encoding| encoding.as_bytes() != b"identity")
    {
        return Err(Failure(io::ErrorKind::InvalidData, "Http2ContentEncoding"));
    }
    if kind == ResponseKind::Raw {
        return Ok(false);
    }
    let content_type = headers
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    if !(content_type == "application/grpc"
        || content_type.starts_with("application/grpc+")
        || content_type.starts_with("application/grpc;"))
    {
        return Err(Failure(io::ErrorKind::InvalidData, "GrpcContentType"));
    }
    if headers
        .get("grpc-encoding")
        .is_some_and(|encoding| encoding.as_bytes() != b"identity")
    {
        return Err(Failure(
            io::ErrorKind::InvalidData,
            "GrpcCompressionUnsupported",
        ));
    }
    let terminal_status = status(headers)?;
    if terminal_status && !response.body().is_end_stream() {
        return Err(Failure(io::ErrorKind::InvalidData, "GrpcPrematureStatus"));
    }
    Ok(terminal_status)
}

impl H2Stream {
    fn send(&mut self) -> &mut SendStream<Bytes> {
        self.send.as_mut().expect("live HTTP/2 send stream")
    }

    fn fail(&mut self, failure: Failure) -> io::Error {
        self.failure = Some(failure);
        self.send().send_reset(h2::Reason::CANCEL);
        failure.error()
    }

    fn peer_finished_request(&mut self, cx: &mut Context<'_>) -> bool {
        matches!(
            self.send().poll_reset(cx),
            Poll::Ready(Ok(h2::Reason::NO_ERROR))
        )
    }

    fn send_failure(&mut self, cx: &mut Context<'_>, failure: Failure) -> io::Error {
        // The driver may receive a reset between the initial poll_reset and
        // poll_capacity/send_data. Classify that race the same as an already
        // observed early-response reset, preserving its receive direction.
        if self.peer_finished_request(cx) {
            io::Error::new(io::ErrorKind::BrokenPipe, "Http2RequestClosed")
        } else {
            self.fail(failure)
        }
    }

    fn poll_response(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if let Some(failure) = self.failure {
            return Poll::Ready(Err(failure.error()));
        }
        let Some(response) = self.response.as_mut() else {
            return Poll::Ready(Ok(()));
        };
        match Pin::new(response).poll(cx) {
            Poll::Ready(Ok(response)) => {
                let initial_status = match check_response(&response, self.kind) {
                    Ok(value) => value,
                    Err(failure) => return Poll::Ready(Err(self.fail(failure))),
                };
                self.initial_grpc_status = initial_status;
                self.receive = Some(response.into_body());
                self.response = None;
                Poll::Ready(Ok(()))
            }
            Poll::Ready(Err(_)) => Poll::Ready(Err(self.fail(Failure(
                io::ErrorKind::ConnectionAborted,
                "Http2ResponseReset",
            )))),
            Poll::Pending => {
                let deadline = self
                    .header_deadline
                    .get_or_insert_with(|| Box::pin(sleep(self.header_timeout)));
                if deadline.as_mut().poll(cx).is_ready() {
                    Poll::Ready(Err(
                        self.fail(Failure(io::ErrorKind::TimedOut, "Http2ResponseTimeout"))
                    ))
                } else {
                    Poll::Pending
                }
            }
        }
    }

    fn poll_send_reset(&mut self, cx: &mut Context<'_>) -> io::Result<()> {
        if let Some(failure) = self.failure {
            return Err(failure.error());
        }
        match self.send().poll_reset(cx) {
            Poll::Ready(Ok(h2::Reason::NO_ERROR)) => {
                // The server's early response remains readable. An attempted
                // further upload fails without replacing that response with a
                // locally generated CANCEL or poisoning the receive half.
                Err(io::Error::new(
                    io::ErrorKind::BrokenPipe,
                    "Http2RequestClosed",
                ))
            }
            Poll::Ready(Ok(_)) | Poll::Ready(Err(_)) => {
                Err(self.fail(Failure(io::ErrorKind::ConnectionReset, "Http2StreamReset")))
            }
            Poll::Pending => Ok(()),
        }
    }
}

impl AsyncRead for H2Stream {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        output: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if output.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        ready!(this.poll_response(cx))?;
        if this.receive_done {
            return Poll::Ready(Ok(()));
        }
        // Avoid monopolizing an executor on a peer's sequence of empty DATA.
        for _ in 0..32 {
            if !this.buffer.is_empty() {
                let n = output.remaining().min(this.buffer.len());
                output.put_slice(&this.buffer[..n]);
                this.buffer.advance(n);
                if this
                    .receive
                    .as_mut()
                    .expect("validated HTTP/2 response")
                    .flow_control()
                    .release_capacity(n)
                    .is_err()
                {
                    return Poll::Ready(Err(
                        this.fail(Failure(io::ErrorKind::InvalidData, "Http2FlowControl"))
                    ));
                }
                return Poll::Ready(Ok(()));
            }
            let receive = this.receive.as_mut().expect("validated HTTP/2 response");
            match ready!(receive.poll_data(cx)) {
                Some(Ok(bytes)) => this.buffer = bytes,
                Some(Err(_)) => {
                    return Poll::Ready(Err(
                        this.fail(Failure(io::ErrorKind::ConnectionReset, "Http2BodyReset"))
                    ));
                }
                None => {
                    if this.kind == ResponseKind::Grpc {
                        let trailers = match ready!(receive.poll_trailers(cx)) {
                            Ok(value) => value,
                            Err(_) => {
                                return Poll::Ready(Err(this.fail(Failure(
                                    io::ErrorKind::ConnectionReset,
                                    "GrpcTrailersReset",
                                ))));
                            }
                        };
                        let final_status = trailers.as_ref().map(status).transpose();
                        match final_status {
                            Err(failure) => return Poll::Ready(Err(this.fail(failure))),
                            Ok(Some(true)) => {}
                            Ok(_) if this.initial_grpc_status => {}
                            Ok(_) => {
                                return Poll::Ready(Err(this.fail(Failure(
                                    io::ErrorKind::UnexpectedEof,
                                    "GrpcStatusMissing",
                                ))));
                            }
                        }
                    }
                    this.receive_done = true;
                    return Poll::Ready(Ok(()));
                }
            }
        }
        cx.waker().wake_by_ref();
        Poll::Pending
    }
}

impl AsyncWrite for H2Stream {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        this.poll_send_reset(cx)?;
        if this.send_done {
            return Poll::Ready(Err(io::ErrorKind::BrokenPipe.into()));
        }
        if buffer.is_empty() {
            return Poll::Ready(Ok(0));
        }
        let wanted = CHUNK.min(buffer.len());
        this.send().reserve_capacity(wanted);
        let capacity = match ready!(this.send().poll_capacity(cx)) {
            Some(Ok(value)) => value,
            _ => {
                return Poll::Ready(Err(
                    this.send_failure(cx, Failure(io::ErrorKind::BrokenPipe, "Http2SendClosed"))
                ));
            }
        };
        let n = wanted.min(capacity);
        if this
            .send()
            .send_data(Bytes::copy_from_slice(&buffer[..n]), false)
            .is_err()
        {
            return Poll::Ready(Err(
                this.send_failure(cx, Failure(io::ErrorKind::BrokenPipe, "Http2Send"))
            ));
        }
        Poll::Ready(Ok(n))
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        // send_data transferred ownership to the continuously polled h2
        // driver. No unbounded adapter write buffer remains to flush.
        Poll::Ready(self.get_mut().poll_send_reset(cx))
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if this.send_done {
            return Poll::Ready(Ok(()));
        }
        if let Some(failure) = this.failure {
            return Poll::Ready(Err(failure.error()));
        }
        match this.send().poll_reset(cx) {
            // RFC 9113 section 8.1 permits an early response followed by
            // NO_ERROR to stop the remaining request. Only the send half is
            // complete: the response and (for gRPC) terminal status must still
            // be independently consumed and validated by poll_read.
            Poll::Ready(Ok(h2::Reason::NO_ERROR)) => {
                this.send_done = true;
                return Poll::Ready(Ok(()));
            }
            Poll::Ready(Ok(_)) | Poll::Ready(Err(_)) => {
                return Poll::Ready(Err(
                    this.fail(Failure(io::ErrorKind::ConnectionReset, "Http2StreamReset"))
                ));
            }
            Poll::Pending => {}
        }
        if this.send().send_data(Bytes::new(), true).is_err() && !this.peer_finished_request(cx) {
            return Poll::Ready(Err(
                this.fail(Failure(io::ErrorKind::BrokenPipe, "Http2Shutdown"))
            ));
        }
        this.send_done = true;
        Poll::Ready(Ok(()))
    }
}

impl Drop for H2Stream {
    fn drop(&mut self) {
        if !self.send_done {
            self.send().send_reset(h2::Reason::CANCEL);
        } else if !self.receive_done && self.failure.is_none() {
            let response = RetiredResponse {
                _send: self.send.take().expect("live HTTP/2 send stream"),
                response: self.response.take(),
                receive: self.receive.take(),
                unconsumed: self.buffer.len(),
                _slot: self.slot.take().expect("live HTTP/2 stream permit"),
            };
            // Every queued/draining response owns one of MAX_STREAMS permits,
            // so the same-sized channel cannot overflow while the driver lives.
            // If the connection already failed, dropping the returned value
            // promptly releases its handles instead.
            let _ = self._driver.retired.try_send(response);
        }
    }
}

#[cfg(test)]
#[path = "h2_stream_tests.rs"]
mod tests;
