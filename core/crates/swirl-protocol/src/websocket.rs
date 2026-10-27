//! RFC 6455 binary byte transport for proxy protocols. No compression,
//! subprotocol negotiation, early data, request replay or external proxy engine.
//! The owned driver is aborted on Drop. WebSocket close is full-duplex; TCP
//! half-close semantics are deliberately not claimed for a WS transport.
use base64::{Engine, engine::general_purpose::STANDARD};
use ring::{
    digest,
    rand::{SecureRandom, SystemRandom},
};
use std::{
    io,
    pin::Pin,
    sync::{
        Arc,
        atomic::{AtomicU8, Ordering},
    },
    task::{Context, Poll},
};
use swirl_subscription::WebSocket;
use swirl_transport::BoxStream;
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, DuplexStream, ReadBuf},
    sync::{mpsc, watch},
    task::JoinHandle,
    time::{Duration, Instant, sleep_until},
};

const BUFFER: usize = 16384;
const MAX_MESSAGE: u64 = 1024 * 1024;
const CLOSE_TIMEOUT: Duration = Duration::from_secs(2);
type Control = (u8, Vec<u8>);

#[derive(Clone)]
struct CloseBudget {
    deadline: watch::Sender<Option<Instant>>,
}
impl Default for CloseBudget {
    fn default() -> Self {
        Self {
            deadline: watch::channel(None).0,
        }
    }
}
impl CloseBudget {
    fn start(&self) {
        // Queueing, writes, flush, peer acknowledgement and transport shutdown
        // share this first deadline. Repeated shutdown/Close cannot extend it.
        self.deadline.send_if_modified(|deadline| {
            if deadline.is_some() {
                return false;
            }
            *deadline = Some(Instant::now() + CLOSE_TIMEOUT);
            true
        });
    }
    async fn started(&self) -> Instant {
        let mut signal = self.deadline.subscribe();
        loop {
            if let Some(deadline) = *signal.borrow_and_update() {
                return deadline;
            }
            // self owns a Sender for this entire wait, so it cannot close.
            signal
                .changed()
                .await
                .expect("close budget sender is alive");
        }
    }
    async fn expired(&self) {
        sleep_until(self.started().await).await;
    }
}
fn invalid(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason)
}
fn accept_key(key: &str) -> String {
    let value = format!("{key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11");
    // SHA-1 here is the protocol's non-secret handshake token, not TLS security.
    STANDARD.encode(digest::digest(
        &digest::SHA1_FOR_LEGACY_USE_ONLY,
        value.as_bytes(),
    ))
}
fn check_upgrade(data: &[u8], key: &str) -> Result<(), &'static str> {
    let mut headers = [httparse::EMPTY_HEADER; 64];
    let mut response = httparse::Response::new(&mut headers);
    if !response
        .parse(data)
        .map_err(|_| "WebSocketUpgradeSyntax")?
        .is_complete()
        || response.version != Some(1)
        || response.code != Some(101)
    {
        return Err("WebSocketUpgradeRejected");
    }
    let mut accept = None;
    let mut upgrade = false;
    let mut connection = false;
    for header in response.headers.iter() {
        let value = std::str::from_utf8(header.value).map_err(|_| "WebSocketUpgradeSyntax")?;
        match header.name.to_ascii_lowercase().as_str() {
            "sec-websocket-accept" => {
                if accept.replace(value.trim()).is_some() {
                    return Err("WebSocketDuplicateAccept");
                }
            }
            "upgrade" => {
                if upgrade || !value.trim().eq_ignore_ascii_case("websocket") {
                    return Err("WebSocketUpgradeProtocol");
                }
                upgrade = true;
            }
            "connection" => {
                connection |= value
                    .split(',')
                    .any(|s| s.trim().eq_ignore_ascii_case("upgrade"))
            }
            "sec-websocket-extensions" | "sec-websocket-protocol" | "transfer-encoding" => {
                return Err("WebSocketUnsolicitedExtension");
            }
            "content-length" if value.trim() != "0" => return Err("WebSocketUpgradeBody"),
            _ => {}
        }
    }
    if !upgrade || !connection || accept != Some(accept_key(key).as_str()) {
        return Err("WebSocketUpgradeAuthentication");
    }
    Ok(())
}

fn close_valid(data: &[u8]) -> bool {
    if data.is_empty() {
        return true;
    }
    if data.len() < 2 {
        return false;
    }
    let code = u16::from_be_bytes([data[0], data[1]]);
    // Registered standard codes plus application/private-use ranges only.
    (matches!(code, 1000..=1003 | 1007..=1014) || (3000..=4999).contains(&code))
        && std::str::from_utf8(&data[2..]).is_ok()
}
async fn send_frame<W: AsyncWrite + Unpin>(
    writer: &mut W,
    opcode: u8,
    data: &[u8],
) -> io::Result<()> {
    let mut mask = [0; 4];
    SystemRandom::new()
        .fill(&mut mask)
        .map_err(|_| invalid("WebSocketRandom"))?;
    let mut frame = Vec::with_capacity(data.len() + 14);
    frame.push(0x80 | opcode);
    if data.len() < 126 {
        frame.push(0x80 | data.len() as u8);
    } else if data.len() <= 65535 {
        frame.push(0xfe);
        frame.extend((data.len() as u16).to_be_bytes());
    } else {
        frame.push(0xff);
        frame.extend((data.len() as u64).to_be_bytes());
    }
    frame.extend(mask);
    frame.extend(data.iter().enumerate().map(|(i, b)| b ^ mask[i % 4]));
    writer.write_all(&frame).await?;
    writer.flush().await
}
async fn read_frames<R: AsyncRead + Unpin, W: AsyncWrite + Unpin>(
    mut wire: R,
    mut app: W,
    controls: mpsc::Sender<Control>,
    close: &CloseBudget,
) -> io::Result<()> {
    let mut fragmented = false;
    let mut message_size = 0u64;
    let mut fragments = 0u32;
    let mut buffer = [0; BUFFER];
    loop {
        let mut header = [0; 2];
        wire.read_exact(&mut header).await?;
        let fin = header[0] & 0x80 != 0;
        let opcode = header[0] & 15;
        if header[0] & 0x70 != 0 || header[1] & 0x80 != 0 {
            return Err(invalid("WebSocketFlags"));
        }
        let encoded = header[1] & 127;
        let size = match encoded {
            126 => {
                let size = u64::from(wire.read_u16().await?);
                if size < 126 {
                    return Err(invalid("WebSocketLength"));
                }
                size
            }
            127 => {
                let size = wire.read_u64().await?;
                if size < 65536 || size >> 63 != 0 {
                    return Err(invalid("WebSocketLength"));
                }
                size
            }
            size => u64::from(size),
        };
        match opcode {
            0 | 2 => {
                if (opcode == 0) != fragmented {
                    return Err(invalid("WebSocketFragmentOrder"));
                }
                if opcode == 2 {
                    message_size = 0;
                    fragments = 0;
                }
                message_size = message_size
                    .checked_add(size)
                    .ok_or_else(|| invalid("WebSocketMessageLimit"))?;
                fragments += 1;
                if message_size > MAX_MESSAGE || fragments > 1024 {
                    return Err(invalid("WebSocketMessageLimit"));
                }
                fragmented = !fin;
                let mut remaining = size;
                while remaining != 0 {
                    let count = remaining.min(BUFFER as u64) as usize;
                    wire.read_exact(&mut buffer[..count]).await?;
                    app.write_all(&buffer[..count]).await?;
                    remaining -= count as u64;
                }
            }
            8..=10 => {
                if !fin || size > 125 {
                    return Err(invalid("WebSocketControlFrame"));
                }
                let mut data = vec![0; size as usize];
                wire.read_exact(&mut data).await?;
                if opcode == 8 {
                    if !close_valid(&data) {
                        return Err(invalid("WebSocketClose"));
                    }
                    close.start();
                    controls
                        .send((8, data))
                        .await
                        .map_err(|_| invalid("WebSocketControlClosed"))?;
                    return Ok(());
                }
                if opcode == 9 {
                    // A coalesced burst may fill the bounded queue before the
                    // writer is polled. Apply backpressure instead of treating
                    // valid control traffic as a malformed frame. The driver
                    // polls both directions and Drop cancels a blocked send.
                    controls
                        .send((10, data))
                        .await
                        .map_err(|_| invalid("WebSocketControlClosed"))?;
                }
            }
            // Proxy transports carry binary bytes, never text messages.
            _ => return Err(invalid("WebSocketOpcode")),
        }
    }
}
async fn write_frames<W: AsyncWrite + Unpin, R: AsyncRead + Unpin>(
    mut wire: W,
    mut app: R,
    mut controls: mpsc::Receiver<Control>,
    close: &CloseBudget,
) -> io::Result<()> {
    let mut buffer = [0; BUFFER];
    let mut sent_close = false;
    loop {
        tokio::select! {
            biased;
            control = controls.recv() => {
                let Some((opcode, data)) = control else { return Err(invalid("WebSocketControlClosed")); };
                if opcode == 8 {
                    if !sent_close {
                        send_frame(&mut wire, opcode, &data).await?;
                    }
                    return wire.shutdown().await;
                }
                send_frame(&mut wire, opcode, &data).await?;
            }
            read = app.read(&mut buffer), if !sent_close => {
                let size = read?;
                if size == 0 {
                    close.start();
                    send_frame(&mut wire, 8, &1000u16.to_be_bytes()).await?;
                    sent_close = true;
                    // RFC 6455 5.5.2 still requires Pong until a peer Close.
                    // Keep the control receiver and wire write half alive,
                    // but never send another application frame after Close.
                    continue;
                }
                send_frame(&mut wire, 2, &buffer[..size]).await?;
            }
        }
    }
}
async fn drive(wire: BoxStream, app: &mut DuplexStream, close: &CloseBudget) -> io::Result<()> {
    let (read_wire, write_wire) = tokio::io::split(wire);
    let (read_app, write_app) = tokio::io::split(app);
    let (controls, control_rx) = mpsc::channel(8);
    let read = read_frames(read_wire, write_app, controls, close);
    let write = write_frames(write_wire, read_app, control_rx, close);
    // Start timing at the first close request, before either direction can
    // stall on a full control queue or wire. Both futures are owned here and
    // dropped together on timeout, error or driver cancellation. Idle
    // applications have no arbitrary keepalive/read timeout.
    tokio::select! {
        biased;
        () = close.expired() => Err(invalid("WebSocketCloseTimeout")),
        result = async { tokio::try_join!(read, write)?; Ok(()) } => result,
    }
}
struct Stream {
    io: DuplexStream,
    driver: JoinHandle<()>,
    ended: Arc<AtomicU8>,
    close: CloseBudget,
}
impl Stream {
    fn new(wire: BoxStream) -> Self {
        let (io, mut app) = tokio::io::duplex(BUFFER);
        let ended = Arc::new(AtomicU8::new(0));
        let result = ended.clone();
        let close = CloseBudget::default();
        let driver_close = close.clone();
        let driver = tokio::spawn(async move {
            let success = drive(wire, &mut app, &driver_close).await.is_ok();
            result.store(if success { 1 } else { 2 }, Ordering::Release);
            // app remains owned until result has been published, so EOF cannot
            // race the error status or disguise malformed/truncated WS as success.
            drop(app);
        });
        Self {
            io,
            driver,
            ended,
            close,
        }
    }
}
impl Drop for Stream {
    fn drop(&mut self) {
        self.driver.abort();
    }
}
impl AsyncRead for Stream {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        let before = buffer.filled().len();
        let remaining = buffer.remaining();
        match Pin::new(&mut this.io).poll_read(cx, buffer) {
            Poll::Ready(Ok(()))
                if remaining > 0
                    && buffer.filled().len() == before
                    && this.ended.load(Ordering::Acquire) != 1 =>
            {
                Poll::Ready(Err(invalid("WebSocketTransportClosed")))
            }
            other => other,
        }
    }
}
impl AsyncWrite for Stream {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        data: &[u8],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.get_mut().io).poll_write(cx, data)
    }
    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().io).poll_flush(cx)
    }
    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        // The writer may be blocked sending an earlier data frame and unable
        // to read application EOF. Bound shutdown from the caller's request.
        this.close.start();
        Pin::new(&mut this.io).poll_shutdown(cx)
    }
}
pub(super) async fn connect(
    wire: BoxStream,
    settings: &WebSocket,
) -> Result<BoxStream, &'static str> {
    connect_with_headers(wire, settings, &[]).await
}

/// Validate application headers without allowing them to replace the opening
/// handshake, request framing, or unsupported WebSocket extensions/early data.
/// Host is supplied by `WebSocket::host`, not by this additional header list.
pub fn validate_headers(headers: &[(String, String)]) -> Result<(), &'static str> {
    if headers.len() > 32 {
        return Err("WebSocketHeadersLimit");
    }
    let mut bytes = 0usize;
    let mut names = std::collections::HashSet::new();
    for (name, value) in headers {
        bytes = bytes
            .checked_add(name.len())
            .and_then(|size| size.checked_add(value.len()))
            .and_then(|size| size.checked_add(4))
            .ok_or("WebSocketHeadersLimit")?;
        if bytes > 8192 {
            return Err("WebSocketHeadersLimit");
        }
        if name.is_empty()
            || !name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&byte))
            || !value
                .bytes()
                .all(|byte| byte == b'\t' || (32..=126).contains(&byte))
        {
            return Err("WebSocketHeadersSyntax");
        }
        let name = name.to_ascii_lowercase();
        if name.starts_with("sec-websocket-")
            || matches!(
                name.as_str(),
                "host"
                    | "connection"
                    | "upgrade"
                    | "content-length"
                    | "transfer-encoding"
                    | "te"
                    | "trailer"
                    | "expect"
                    | "proxy-connection"
            )
        {
            return Err("WebSocketReservedHeader");
        }
        if !names.insert(name) {
            return Err("WebSocketDuplicateHeader");
        }
    }
    Ok(())
}

fn requests_early_data(path: &str) -> bool {
    let Some((_, query)) = path.split_once('?') else {
        return false;
    };
    query.split('&').any(|parameter| {
        let key = parameter.split('=').next().unwrap_or_default();
        // Xray reads this as a URL query, so percent-encoded "ed" is the same
        // setting. Paths have already passed the strict ASCII/escape validator.
        let mut decoded = Vec::with_capacity(key.len());
        let mut at = 0;
        while at < key.len() {
            if key.as_bytes()[at] == b'%'
                && let Some(encoded) = key.get(at + 1..at + 3)
                && let Ok(byte) = u8::from_str_radix(encoded, 16)
            {
                decoded.push(byte);
                at += 3;
                continue;
            }
            decoded.push(key.as_bytes()[at]);
            at += 1;
        }
        decoded == b"ed"
    })
}

/// Shared preflight for Core activation, protocol dialing and direct callers.
/// Unsupported early data must fail before DNS or opening the outer socket.
pub(crate) fn validate_settings(
    settings: &WebSocket,
    headers: &[(String, String)],
) -> Result<(), &'static str> {
    settings.validate()?;
    validate_headers(headers)?;
    if requests_early_data(&settings.path) {
        return Err("WebSocketEarlyDataUnsupported");
    }
    Ok(())
}

/// Open the existing RFC 6455 binary stream with bounded custom HTTP headers.
/// The caller supplies an already authenticated TLS stream for WSS and bounds
/// this opening handshake with its shared connection deadline.
pub async fn connect_with_headers(
    mut wire: BoxStream,
    settings: &WebSocket,
    headers: &[(String, String)],
) -> Result<BoxStream, &'static str> {
    validate_settings(settings, headers)?;
    let mut nonce = [0; 16];
    SystemRandom::new()
        .fill(&mut nonce)
        .map_err(|_| "WebSocketRandom")?;
    let key = STANDARD.encode(nonce);
    let mut request = format!(
        "GET {} HTTP/1.1\r\nHost: {}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n",
        settings.path, settings.host
    );
    for (name, value) in headers {
        request.push_str(name);
        request.push_str(": ");
        request.push_str(value);
        request.push_str("\r\n");
    }
    request.push_str("\r\n");
    wire.write_all(request.as_bytes())
        .await
        .map_err(|_| "WebSocketUpgradeWrite")?;
    wire.flush().await.map_err(|_| "WebSocketUpgradeWrite")?;
    let mut response = Vec::new();
    while !response.ends_with(b"\r\n\r\n") {
        if response.len() >= BUFFER {
            return Err("WebSocketUpgradeLimit");
        }
        response.push(wire.read_u8().await.map_err(|_| "WebSocketUpgradeRead")?);
    }
    check_upgrade(&response, &key)?;
    Ok(Box::new(Stream::new(wire)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{sync::Mutex, task::Waker};
    use tokio::sync::{Notify, oneshot};
    use tokio::time::{advance, timeout};

    #[derive(Default)]
    struct Gate {
        state: Mutex<(bool, Option<Waker>)>,
        reached: Notify,
    }
    impl Gate {
        fn block(&self) {
            self.state.lock().unwrap().0 = true;
        }
        fn release(&self) {
            let waker = {
                let mut state = self.state.lock().unwrap();
                state.0 = false;
                state.1.take()
            };
            if let Some(waker) = waker {
                waker.wake();
            }
        }
        fn poll(&self, cx: &mut Context<'_>) -> Poll<()> {
            let mut state = self.state.lock().unwrap();
            if state.0 {
                state.1 = Some(cx.waker().clone());
                self.reached.notify_one();
                Poll::Pending
            } else {
                Poll::Ready(())
            }
        }
    }
    #[derive(Default)]
    struct Gates {
        write: Gate,
        flush: Gate,
        shutdown: Gate,
    }
    struct GatedWire {
        io: DuplexStream,
        gates: Arc<Gates>,
        dropped: Option<oneshot::Sender<()>>,
    }
    impl Drop for GatedWire {
        fn drop(&mut self) {
            if let Some(dropped) = self.dropped.take() {
                let _ = dropped.send(());
            }
        }
    }
    impl AsyncRead for GatedWire {
        fn poll_read(
            self: Pin<&mut Self>,
            cx: &mut Context<'_>,
            buffer: &mut ReadBuf<'_>,
        ) -> Poll<io::Result<()>> {
            Pin::new(&mut self.get_mut().io).poll_read(cx, buffer)
        }
    }
    impl AsyncWrite for GatedWire {
        fn poll_write(
            self: Pin<&mut Self>,
            cx: &mut Context<'_>,
            data: &[u8],
        ) -> Poll<io::Result<usize>> {
            let this = self.get_mut();
            std::task::ready!(this.gates.write.poll(cx));
            Pin::new(&mut this.io).poll_write(cx, data)
        }
        fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
            let this = self.get_mut();
            std::task::ready!(this.gates.flush.poll(cx));
            Pin::new(&mut this.io).poll_flush(cx)
        }
        fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
            let this = self.get_mut();
            std::task::ready!(this.gates.shutdown.poll(cx));
            Pin::new(&mut this.io).poll_shutdown(cx)
        }
    }
    fn gated_wire() -> (BoxStream, DuplexStream, Arc<Gates>, oneshot::Receiver<()>) {
        let (io, peer) = tokio::io::duplex(BUFFER);
        let gates = Arc::new(Gates::default());
        let (dropped, observe_drop) = oneshot::channel();
        (
            Box::new(GatedWire {
                io,
                gates: gates.clone(),
                dropped: Some(dropped),
            }),
            peer,
            gates,
            observe_drop,
        )
    }

    fn server_frame(opcode: u8, fin: bool, data: &[u8]) -> Vec<u8> {
        let mut frame = vec![opcode | if fin { 128 } else { 0 }];
        if data.len() < 126 {
            frame.push(data.len() as u8);
        } else {
            assert!(data.len() <= 65535);
            frame.push(126);
            frame.extend((data.len() as u16).to_be_bytes());
        }
        frame.extend(data);
        frame
    }

    async fn client_frame<R: AsyncRead + Unpin>(reader: &mut R) -> (u8, Vec<u8>) {
        let mut header = [0; 2];
        reader.read_exact(&mut header).await.unwrap();
        assert_eq!(header[0] & 0xf0, 0x80);
        assert_ne!(header[1] & 0x80, 0);
        let size = match header[1] & 127 {
            126 => {
                let size = reader.read_u16().await.unwrap();
                assert!(size >= 126);
                usize::from(size)
            }
            127 => panic!("client frames must respect the fixed transport buffer"),
            size => usize::from(size),
        };
        assert!(size <= BUFFER);
        let mut mask = [0; 4];
        reader.read_exact(&mut mask).await.unwrap();
        let mut data = vec![0; size];
        reader.read_exact(&mut data).await.unwrap();
        for (i, byte) in data.iter_mut().enumerate() {
            *byte ^= mask[i % 4];
        }
        (header[0] & 15, data)
    }

    #[tokio::test(start_paused = true)]
    async fn one_close_deadline_covers_write_flush_peer_reply_and_shutdown() {
        timeout(Duration::from_secs(3), async {
            let (wire, mut peer, gates, dropped) = gated_wire();
            gates.write.block();
            gates.flush.block();
            gates.shutdown.block();
            let (mut application, mut app) = tokio::io::duplex(32);
            let close = CloseBudget::default();
            let driver_close = close.clone();
            let start = Instant::now();
            let driver = tokio::spawn(async move { drive(wire, &mut app, &driver_close).await });
            application.shutdown().await.unwrap();
            gates.write.reached.notified().await;
            assert_eq!(close.started().await, start + CLOSE_TIMEOUT);

            advance(Duration::from_millis(500)).await;
            gates.write.release();
            assert_eq!(
                client_frame(&mut peer).await,
                (8, 1000u16.to_be_bytes().to_vec())
            );
            gates.flush.reached.notified().await;
            advance(Duration::from_millis(500)).await;
            gates.flush.release();

            advance(Duration::from_millis(500)).await;
            peer.write_all(&server_frame(8, true, &1000u16.to_be_bytes()))
                .await
                .unwrap();
            gates.shutdown.reached.notified().await;
            // Peer Close and repeated local close requests must not restart it.
            close.start();
            assert_eq!(close.started().await, start + CLOSE_TIMEOUT);
            advance(Duration::from_millis(499)).await;
            assert!(!driver.is_finished());
            advance(Duration::from_millis(1)).await;
            assert_eq!(
                driver.await.unwrap().unwrap_err().to_string(),
                "WebSocketCloseTimeout"
            );
            dropped.await.unwrap();
            assert_eq!(Instant::now() - start, CLOSE_TIMEOUT);
        })
        .await
        .unwrap();
    }

    #[tokio::test(start_paused = true)]
    async fn peer_close_behind_a_full_control_queue_has_a_deadline() {
        timeout(Duration::from_secs(3), async {
            let (wire, mut peer, gates, dropped) = gated_wire();
            gates.write.block();
            let mut frames = Vec::new();
            // One Pong is stuck in write_all; eight more fill the queue.
            for value in 0..9 {
                frames.extend(server_frame(9, true, &[value]));
            }
            frames.extend(server_frame(8, true, &1000u16.to_be_bytes()));
            peer.write_all(&frames).await.unwrap();
            let (_application, mut app) = tokio::io::duplex(32);
            let close = CloseBudget::default();
            let driver_close = close.clone();
            let start = Instant::now();
            let driver = tokio::spawn(async move { drive(wire, &mut app, &driver_close).await });
            assert_eq!(close.started().await, start + CLOSE_TIMEOUT);
            gates.write.reached.notified().await;
            advance(CLOSE_TIMEOUT - Duration::from_millis(1)).await;
            assert!(!driver.is_finished());
            advance(Duration::from_millis(1)).await;
            assert_eq!(
                driver.await.unwrap().unwrap_err().to_string(),
                "WebSocketCloseTimeout"
            );
            dropped.await.unwrap();
        })
        .await
        .unwrap();
    }

    #[tokio::test(start_paused = true)]
    async fn local_shutdown_bounds_a_previously_backpressured_data_frame() {
        timeout(Duration::from_secs(3), async {
            let (wire, _peer, gates, dropped) = gated_wire();
            gates.write.block();
            let mut stream = Stream::new(wire);
            stream
                .write_all(b"request already being framed")
                .await
                .unwrap();
            gates.write.reached.notified().await;
            assert!(stream.close.deadline.borrow().is_none());
            stream.shutdown().await.unwrap();
            advance(CLOSE_TIMEOUT).await;
            (&mut stream.driver).await.unwrap();
            assert_eq!(stream.ended.load(Ordering::Acquire), 2);
            assert_eq!(
                stream.read_u8().await.unwrap_err().to_string(),
                "WebSocketTransportClosed"
            );
            dropped.await.unwrap();
        })
        .await
        .unwrap();
    }

    #[tokio::test(start_paused = true)]
    async fn silent_peer_and_repeated_shutdown_cannot_extend_the_close_budget() {
        timeout(Duration::from_secs(3), async {
            let (wire, mut peer, _gates, dropped) = gated_wire();
            let mut stream = Stream::new(wire);
            let start = Instant::now();
            stream.shutdown().await.unwrap();
            assert_eq!(client_frame(&mut peer).await.0, 8);
            advance(Duration::from_secs(1)).await;
            stream.shutdown().await.unwrap();
            assert_eq!(stream.close.started().await, start + CLOSE_TIMEOUT);
            advance(Duration::from_secs(1)).await;
            (&mut stream.driver).await.unwrap();
            assert_eq!(stream.ended.load(Ordering::Acquire), 2);
            dropped.await.unwrap();
            let mut trailing = Vec::new();
            peer.read_to_end(&mut trailing).await.unwrap();
            assert!(trailing.is_empty());
            assert_eq!(Instant::now() - start, CLOSE_TIMEOUT);
        })
        .await
        .unwrap();
    }

    #[tokio::test(start_paused = true)]
    async fn local_eof_flushes_queued_data_and_answers_ping_until_peer_close() {
        timeout(CLOSE_TIMEOUT, async {
            let (wire, mut peer, _gates, dropped) = gated_wire();
            let mut stream = Stream::new(wire);
            stream.write_all(b"queued before EOF").await.unwrap();
            stream.shutdown().await.unwrap();
            assert_eq!(
                client_frame(&mut peer).await,
                (2, b"queued before EOF".to_vec())
            );
            assert_eq!(
                client_frame(&mut peer).await,
                (8, 1000u16.to_be_bytes().to_vec())
            );
            assert!(stream.write_all(b"after Close").await.is_err());
            peer.write_all(&server_frame(9, true, b"still closing"))
                .await
                .unwrap();
            assert_eq!(
                client_frame(&mut peer).await,
                (10, b"still closing".to_vec())
            );
            peer.write_all(&server_frame(8, true, &1000u16.to_be_bytes()))
                .await
                .unwrap();
            let mut data = Vec::new();
            stream.read_to_end(&mut data).await.unwrap();
            assert!(data.is_empty());
            (&mut stream.driver).await.unwrap();
            assert_eq!(stream.ended.load(Ordering::Acquire), 1);
            dropped.await.unwrap();
            // A simultaneous/acknowledged Close must not send a second Close.
            peer.read_to_end(&mut data).await.unwrap();
            assert!(data.is_empty());
        })
        .await
        .unwrap();
    }

    #[tokio::test(start_paused = true)]
    async fn transport_eof_without_peer_close_is_never_reported_as_success() {
        for local_close in [false, true] {
            timeout(CLOSE_TIMEOUT, async {
                let (wire, mut peer, _gates, dropped) = gated_wire();
                let mut stream = Stream::new(wire);
                if local_close {
                    stream.shutdown().await.unwrap();
                    assert_eq!(client_frame(&mut peer).await.0, 8);
                }
                peer.shutdown().await.unwrap();
                assert_eq!(
                    stream.read_u8().await.unwrap_err().to_string(),
                    "WebSocketTransportClosed"
                );
                (&mut stream.driver).await.unwrap();
                assert_eq!(stream.ended.load(Ordering::Acquire), 2);
                dropped.await.unwrap();
            })
            .await
            .unwrap();
        }
    }

    #[tokio::test(start_paused = true)]
    async fn idle_has_no_deadline_and_drop_cancels_blocked_drivers() {
        for state in 0..3 {
            let (wire, mut peer, gates, dropped) = gated_wire();
            let mut stream = Stream::new(wire);
            match state {
                0 => {
                    advance(Duration::from_secs(86400)).await;
                    assert!(!stream.driver.is_finished());
                    assert!(stream.close.deadline.borrow().is_none());
                }
                1 => {
                    gates.write.block();
                    stream.write_all(b"pending write").await.unwrap();
                    gates.write.reached.notified().await;
                }
                _ => {
                    gates.write.block();
                    let mut frames = Vec::new();
                    for value in 0..9 {
                        frames.extend(server_frame(9, true, &[value]));
                    }
                    frames.extend(server_frame(8, true, &1000u16.to_be_bytes()));
                    peer.write_all(&frames).await.unwrap();
                    stream.close.started().await;
                }
            }
            let driver = stream.driver.abort_handle();
            drop(stream);
            // Observe owned wire destruction, not just an abort request. A
            // leaked close task would still wait for its two-second deadline.
            timeout(Duration::from_millis(1), dropped)
                .await
                .unwrap()
                .unwrap();
            assert!(driver.is_finished());
        }
    }

    #[test]
    fn handshake_token_and_unsolicited_extensions() {
        let key = "dGhlIHNhbXBsZSBub25jZQ==";
        assert_eq!(accept_key(key), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=");
        let valid = format!(
            "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: keep-alive, Upgrade\r\nSec-WebSocket-Accept: {}\r\n",
            accept_key(key)
        );
        assert!(check_upgrade(format!("{valid}\r\n").as_bytes(), key).is_ok());
        for extra in [
            "Sec-WebSocket-Extensions: permessage-deflate",
            "Sec-WebSocket-Protocol: injected",
            "Sec-WebSocket-Accept: wrong",
            "Transfer-Encoding: chunked",
        ] {
            assert!(check_upgrade(format!("{valid}{extra}\r\n\r\n").as_bytes(), key).is_err());
        }
    }
    #[test]
    fn custom_headers_cannot_replace_handshake_or_inject_requests() {
        for name in [
            "Host",
            "cOnNeCtIoN",
            "Upgrade",
            "Content-Length",
            "Transfer-Encoding",
            "TE",
            "Trailer",
            "Expect",
            "Proxy-Connection",
            "Sec-WebSocket-Key",
            "Sec-WebSocket-Version",
            "Sec-WebSocket-Protocol",
            "Sec-WebSocket-Extensions",
        ] {
            assert_eq!(
                validate_headers(&[(name.into(), "fixture".into())]),
                Err("WebSocketReservedHeader")
            );
        }
        for (name, value) in [
            ("", "fixture"),
            ("Bad Name", "fixture"),
            ("Bad:Name", "fixture"),
            ("X-Test", "value\r\nInjected: yes"),
            ("X-Test", "nul\0byte"),
            ("X-Test", "delete\x7f"),
        ] {
            assert_eq!(
                validate_headers(&[(name.into(), value.into())]),
                Err("WebSocketHeadersSyntax")
            );
        }
        assert_eq!(
            validate_headers(&[("X-Test".into(), "a".into()), ("x-test".into(), "b".into())]),
            Err("WebSocketDuplicateHeader")
        );
        assert_eq!(
            validate_headers(&[("X-Test".into(), "x".repeat(8192))]),
            Err("WebSocketHeadersLimit")
        );
        assert_eq!(
            validate_headers(
                &(0..33)
                    .map(|n| (format!("X-{n}"), String::new()))
                    .collect::<Vec<_>>()
            ),
            Err("WebSocketHeadersLimit")
        );
        assert!(
            validate_headers(&[
                ("Origin".into(), "https://fixture.example".into()),
                ("X-Test".into(), "visible\tvalue".into()),
            ])
            .is_ok()
        );
    }

    #[tokio::test]
    async fn early_data_is_rejected_before_any_handshake_bytes() {
        for path in ["/ws?ed=256", "/ws?token=fixture&%65%64=1", "/ws?ed"] {
            let (wire, mut peer) = tokio::io::duplex(512);
            let result = connect(
                Box::new(wire),
                &WebSocket {
                    host: "fixture.example".into(),
                    path: path.into(),
                },
            )
            .await;
            assert!(matches!(result, Err("WebSocketEarlyDataUnsupported")));
            assert_eq!(peer.read(&mut [0; 1]).await.unwrap(), 0);
        }
        assert!(!requests_early_data("/ws?embedded=1"));
    }

    #[tokio::test]
    async fn custom_path_ipv6_authority_headers_and_coalesced_binary_payload() {
        let (wire, mut peer) = tokio::io::duplex(4096);
        let server = tokio::spawn(async move {
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                request.push(peer.read_u8().await.unwrap());
            }
            let request = String::from_utf8(request).unwrap();
            assert!(request.starts_with("GET /nested/ws%20path?fixture=yes HTTP/1.1\r\n"));
            assert!(request.contains("\r\nHost: [::1]:8443\r\n"));
            assert!(request.contains("\r\nOrigin: https://fixture.example\r\n"));
            assert!(request.contains("\r\nX-Fixture: exact-value\r\n"));
            let key = request
                .lines()
                .find_map(|line| line.strip_prefix("Sec-WebSocket-Key: "))
                .unwrap();
            assert_eq!(STANDARD.decode(key).unwrap().len(), 16);
            let mut response = format!(
                "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {}\r\n\r\n",
                accept_key(key)
            )
            .into_bytes();
            response.extend(server_frame(2, true, b"\0\xffserver-binary"));
            peer.write_all(&response).await.unwrap();
            let (opcode, bytes) = client_frame(&mut peer).await;
            assert_eq!(opcode, 2);
            assert_eq!(bytes, b"\xff\0client-binary");
            peer.write_all(&server_frame(8, true, &1000u16.to_be_bytes()))
                .await
                .unwrap();
            let (opcode, bytes) = client_frame(&mut peer).await;
            assert_eq!(opcode, 8);
            assert_eq!(bytes, 1000u16.to_be_bytes());
        });
        let mut stream = connect_with_headers(
            Box::new(wire),
            &WebSocket {
                host: "[::1]:8443".into(),
                path: "/nested/ws%20path?fixture=yes".into(),
            },
            &[
                ("Origin".into(), "https://fixture.example".into()),
                ("X-Fixture".into(), "exact-value".into()),
            ],
        )
        .await
        .unwrap();
        stream.write_all(b"\xff\0client-binary").await.unwrap();
        let mut data = Vec::new();
        timeout(Duration::from_secs(2), stream.read_to_end(&mut data))
            .await
            .unwrap()
            .unwrap();
        assert_eq!(data, b"\0\xffserver-binary");
        server.await.unwrap();
    }

    #[test]
    fn close_codes_and_utf8_are_validated() {
        assert!(close_valid(&[]));
        assert!(close_valid(&1000u16.to_be_bytes()));
        assert!(close_valid(&4001u16.to_be_bytes()));
        for code in [0u16, 999, 1004, 1005, 1006, 1015, 2000, 5000] {
            assert!(!close_valid(&code.to_be_bytes()));
        }
        assert!(!close_valid(&[3, 232, 255]));
        assert!(!close_valid(&[0]));
    }
    #[tokio::test]
    async fn invalid_server_frame_headers_fail_before_releasing_data() {
        for bytes in [
            &b"\x82\x80"[..],
            &b"\xc2\x00"[..],
            &b"\x80\x01x"[..],
            &b"\x89\x7e\x00\x01x"[..],
            &b"\x82\x7f\x80\0\0\0\0\0\0\0"[..],
        ] {
            let mut data = bytes;
            let (tx, _rx) = mpsc::channel(8);
            assert!(
                read_frames(&mut data, tokio::io::sink(), tx, &CloseBudget::default())
                    .await
                    .is_err()
            );
        }
    }

    #[tokio::test]
    async fn coalesced_ping_burst_backpressures_the_bounded_control_queue() {
        let mut wire = Vec::new();
        let mut expected = Vec::new();
        for i in 0u16..32 {
            wire.extend(server_frame(9, true, &i.to_be_bytes()));
            expected.push((10, i.to_be_bytes().to_vec()));
        }
        wire.extend(server_frame(8, true, &1000u16.to_be_bytes()));
        expected.push((8, 1000u16.to_be_bytes().to_vec()));
        let (tx, mut rx) = mpsc::channel(8);
        let close = CloseBudget::default();
        let read = read_frames(wire.as_slice(), tokio::io::sink(), tx, &close);
        let drain = async {
            let mut received = Vec::new();
            while let Some(control) = rx.recv().await {
                received.push(control);
            }
            received
        };
        let (result, received) = timeout(Duration::from_secs(2), async {
            // Poll the reader first with all 33 controls immediately available.
            // try_send fails on the ninth control before the writer can drain.
            tokio::join!(biased; read, drain)
        })
        .await
        .unwrap();
        result.unwrap();
        assert_eq!(received, expected);
    }

    #[tokio::test]
    async fn closed_control_receiver_fails_without_waiting_or_releasing_payload() {
        let bytes = server_frame(9, true, b"ping");
        let (tx, rx) = mpsc::channel(8);
        drop(rx);
        let error = timeout(
            Duration::from_secs(2),
            read_frames(
                bytes.as_slice(),
                tokio::io::sink(),
                tx,
                &CloseBudget::default(),
            ),
        )
        .await
        .unwrap()
        .unwrap_err();
        assert_eq!(error.to_string(), "WebSocketControlClosed");
    }

    #[tokio::test]
    async fn full_duplex_fragmented_transfer_and_ping_survive_backpressure() {
        timeout(Duration::from_secs(3), async {
            // Both buffers are far smaller than one application write or WS
            // fragment, forcing partial reads/writes in both directions.
            let (wire, server) = tokio::io::duplex(31);
            let (application, mut app) = tokio::io::duplex(17);
            let driver = tokio::spawn(async move {
                drive(Box::new(wire), &mut app, &CloseBudget::default()).await
            });
            let upload: Vec<_> = (0..BUFFER + 11).map(|i| i as u8).collect();
            let download: Vec<_> = (0..BUFFER * 2 + 7).map(|i| (i % 251) as u8).collect();
            let fragments = download.chunks(1024).len();
            let (mut server_read, mut server_write) = tokio::io::split(server);
            let (received_tx, received_rx) = tokio::sync::oneshot::channel();
            let send = async {
                for (index, data) in download.chunks(1024).enumerate() {
                    server_write
                        .write_all(&server_frame(
                            if index == 0 { 2 } else { 0 },
                            index + 1 == fragments,
                            data,
                        ))
                        .await
                        .unwrap();
                    server_write
                        .write_all(&server_frame(9, true, &(index as u16).to_be_bytes()))
                        .await
                        .unwrap();
                }
                received_rx.await.unwrap();
                server_write
                    .write_all(&server_frame(8, true, &1000u16.to_be_bytes()))
                    .await
                    .unwrap();
            };
            let receive = async {
                let mut received = Vec::new();
                let mut pongs = 0;
                let mut completed = Some(received_tx);
                loop {
                    let (opcode, data) = client_frame(&mut server_read).await;
                    match opcode {
                        2 => received.extend(data),
                        10 => {
                            assert_eq!(data, (pongs as u16).to_be_bytes());
                            pongs += 1;
                        }
                        8 => {
                            assert_eq!(data, 1000u16.to_be_bytes());
                            break;
                        }
                        _ => panic!("unexpected client opcode"),
                    }
                    assert!(received.len() <= upload.len());
                    assert!(pongs <= fragments);
                    if received.len() == upload.len()
                        && pongs == fragments
                        && let Some(completed) = completed.take()
                    {
                        completed.send(()).unwrap();
                    }
                }
                assert_eq!(received, upload);
                assert_eq!(pongs, fragments);
            };
            let (mut application_read, mut application_write) = tokio::io::split(application);
            let application_upload = application_write.write_all(&upload);
            let application_download = async {
                let mut data = Vec::new();
                application_read.read_to_end(&mut data).await.unwrap();
                assert_eq!(data, download);
            };
            let (_, _, uploaded, _, result) = tokio::join!(
                send,
                receive,
                application_upload,
                application_download,
                driver
            );
            uploaded.unwrap();
            result.unwrap().unwrap();
        })
        .await
        .unwrap();
    }
}
