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
    sync::mpsc,
    task::JoinHandle,
    time::{Duration, timeout},
};

const BUFFER: usize = 16384;
const MAX_MESSAGE: u64 = 1024 * 1024;
type Control = (u8, Vec<u8>);
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
) -> io::Result<()> {
    let mut buffer = [0; BUFFER];
    loop {
        tokio::select! {
            biased;
            control = controls.recv() => {
                let Some((opcode, data)) = control else { return Err(invalid("WebSocketControlClosed")); };
                send_frame(&mut wire, opcode, &data).await?;
                if opcode == 8 { return wire.shutdown().await; }
            }
            read = app.read(&mut buffer) => {
                let size = read?;
                if size == 0 {
                    send_frame(&mut wire, 8, &1000u16.to_be_bytes()).await?;
                    return wire.shutdown().await;
                }
                send_frame(&mut wire, 2, &buffer[..size]).await?;
            }
        }
    }
}
async fn drive(wire: BoxStream, app: &mut DuplexStream) -> io::Result<()> {
    let (read_wire, write_wire) = tokio::io::split(wire);
    let (read_app, write_app) = tokio::io::split(app);
    let (controls, control_rx) = mpsc::channel(8);
    let read = read_frames(read_wire, write_app, controls);
    let write = write_frames(write_wire, read_app, control_rx);
    tokio::pin!(read, write);
    // Once either direction closes, finish the WS close exchange promptly.
    // Idle applications have no arbitrary keepalive/read timeout.
    tokio::select! {
        result = &mut read => {
            result?;
            timeout(Duration::from_secs(2), write).await.map_err(|_| invalid("WebSocketCloseTimeout"))??;
        }
        result = &mut write => {
            result?;
            timeout(Duration::from_secs(2), read).await.map_err(|_| invalid("WebSocketCloseTimeout"))??;
        }
    }
    Ok(())
}
struct Stream {
    io: DuplexStream,
    driver: JoinHandle<()>,
    ended: Arc<AtomicU8>,
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
        Pin::new(&mut self.get_mut().io).poll_shutdown(cx)
    }
}
pub(super) async fn connect(
    mut wire: BoxStream,
    settings: &WebSocket,
) -> Result<BoxStream, &'static str> {
    settings.validate()?;
    let mut nonce = [0; 16];
    SystemRandom::new()
        .fill(&mut nonce)
        .map_err(|_| "WebSocketRandom")?;
    let key = STANDARD.encode(nonce);
    let request = format!(
        "GET {} HTTP/1.1\r\nHost: {}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n",
        settings.path, settings.host
    );
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
    let (io, mut app) = tokio::io::duplex(BUFFER);
    let ended = Arc::new(AtomicU8::new(0));
    let result = ended.clone();
    let driver = tokio::spawn(async move {
        let success = drive(wire, &mut app).await.is_ok();
        result.store(if success { 1 } else { 2 }, Ordering::Release);
        // app remains owned until result has been published, so EOF cannot
        // race the error status or disguise malformed/truncated WS as success.
        drop(app);
    });
    Ok(Box::new(Stream { io, driver, ended }))
}

#[cfg(test)]
mod tests {
    use super::*;

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
            assert!(read_frames(&mut data, tokio::io::sink(), tx).await.is_err());
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
        let read = read_frames(wire.as_slice(), tokio::io::sink(), tx);
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
            read_frames(bytes.as_slice(), tokio::io::sink(), tx),
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
            let driver = tokio::spawn(async move { drive(Box::new(wire), &mut app).await });
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
