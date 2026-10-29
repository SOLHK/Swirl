//! Tokio ownership for the native REALITY record engine. There is no background
//! task, unbounded queue or ordinary-TLS fallback. Dropping the connecting future
//! or stream releases its sole transport and TLS owners.
use super::{ClientParameters, TlsClient};
use std::{
    future::poll_fn,
    io::{self, Read, Write},
    pin::Pin,
    task::{Context, Poll, ready},
};
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};

const POLL_BUDGET: usize = 64;
const WRITE_LIMIT: usize = 16 * 1024;

/// An authenticated native REALITY connection. The caller retains responsibility
/// for the overall connection deadline; cancellation requires no detached cleanup.
pub struct Stream<S> {
    io: S,
    tls: TlsClient,
    failed: bool,
    shutdown: bool,
    read_raw: bool,
    write_raw: bool,
}

impl<S> std::fmt::Debug for Stream<S> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("RealityStream")
            .field("tls", &self.tls)
            .field("failed", &self.failed)
            .field("shutdown", &self.shutdown)
            .field("read_raw", &self.read_raw)
            .field("write_raw", &self.write_raw)
            .finish_non_exhaustive()
    }
}

/// Establish fresh REALITY authentication and both Finished messages on an
/// already connected transport. No application bytes can be written before this
/// future succeeds. Each invocation constructs fresh, non-reusable key material.
pub async fn connect<S: AsyncRead + AsyncWrite + Unpin>(
    io: S,
    parameters: &ClientParameters,
    unix_time: u32,
    alpn: &[Vec<u8>],
) -> io::Result<Stream<S>> {
    let tls = TlsClient::new(parameters, unix_time, alpn)
        .map_err(|reason| io::Error::new(io::ErrorKind::InvalidInput, reason))?;
    let mut stream = Stream {
        io,
        tls,
        failed: false,
        shutdown: false,
        read_raw: false,
        write_raw: false,
    };
    poll_fn(|cx| stream.poll_handshake(cx)).await?;
    Ok(stream)
}

impl<S: AsyncRead + AsyncWrite + Unpin> Stream<S> {
    /// Read-only TLS state for negotiated-suite and authenticated-close evidence.
    pub fn tls(&self) -> &TlsClient {
        &self.tls
    }

    pub fn is_authenticated(&self) -> bool {
        !self.failed && self.tls.negotiated_cipher_suite().is_some()
    }

    pub fn raw_read_enabled(&self) -> bool {
        self.read_raw
    }

    pub fn raw_write_enabled(&self) -> bool {
        self.write_raw
    }

    /// Transfer the receive direction after the caller has authenticated and
    /// validated its Direct command. Return every remaining authenticated TLS
    /// byte for the caller to deliver before reading the raw transport. There is
    /// no socket read here, and a partial outer record makes transfer fail closed.
    pub fn enable_raw_read(&mut self) -> io::Result<Vec<u8>> {
        self.check_live()?;
        if self.read_raw {
            return Ok(Vec::new());
        }
        if !self.is_authenticated() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "RealityRawReadState",
            ));
        }
        let remaining = self.tls.take_plaintext_for_raw().inspect_err(|_| {
            self.failed = true;
        })?;
        self.read_raw = true;
        Ok(remaining)
    }

    /// Transfer only the send direction, after all framed data and the Direct
    /// command have reached the underlying transport. Partial writes keep the
    /// transition pending; later raw bytes cannot overtake outer TLS ciphertext.
    pub fn poll_enable_raw_write(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        self.check_live()?;
        if self.write_raw {
            return Poll::Ready(Ok(()));
        }
        if !self.is_authenticated() || self.shutdown {
            return self.failure(io::Error::new(
                io::ErrorKind::InvalidData,
                "RealityRawWriteState",
            ));
        }
        ready!(Pin::new(&mut *self).poll_flush(cx))?;
        self.write_raw = true;
        Poll::Ready(Ok(()))
    }

    fn check_live(&self) -> io::Result<()> {
        if self.failed {
            Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "RealityConnectionFailed",
            ))
        } else {
            Ok(())
        }
    }

    fn failure<T>(&mut self, error: io::Error) -> Poll<io::Result<T>> {
        self.failed = true;
        Poll::Ready(Err(error))
    }

    fn poll_tls_write(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.write_raw && self.tls.wants_write() {
            // An outer KeyUpdate response cannot be inserted after the peer has
            // switched this direction to raw application bytes.
            return self.failure(io::Error::new(
                io::ErrorKind::InvalidData,
                "RealityOuterWriteAfterDirect",
            ));
        }
        for _ in 0..POLL_BUDGET {
            if !self.tls.wants_write() {
                return Poll::Ready(Ok(()));
            }
            match self.tls.write_tls(&mut PollIo {
                io: &mut self.io,
                cx,
            }) {
                Ok(_) => {}
                Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    return Poll::Pending;
                }
                Err(error) => return self.failure(error),
            }
        }
        cx.waker().wake_by_ref();
        Poll::Pending
    }

    fn read_record(&mut self, cx: &mut Context<'_>) -> io::Result<usize> {
        self.tls.read_tls(&mut PollIo {
            io: &mut self.io,
            cx,
        })
    }

    fn poll_handshake(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        self.check_live()?;
        for _ in 0..POLL_BUDGET {
            let writes = self.poll_tls_write(cx);
            if let Poll::Ready(Err(error)) = writes {
                return self.failure(error);
            }
            if !self.tls.is_handshaking() && writes.is_ready() {
                return match Pin::new(&mut self.io).poll_flush(cx) {
                    Poll::Ready(Err(error)) => self.failure(error),
                    result => result,
                };
            }
            if !self.tls.wants_read() {
                return Poll::Pending;
            }
            match self.read_record(cx) {
                Ok(_) => {}
                Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    return Poll::Pending;
                }
                Err(error) => return self.failure(error),
            }
        }
        cx.waker().wake_by_ref();
        Poll::Pending
    }
}

impl<S: AsyncRead + AsyncWrite + Unpin> AsyncRead for Stream<S> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        this.check_live()?;
        if out.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        if this.read_raw {
            return match Pin::new(&mut this.io).poll_read(cx, out) {
                Poll::Ready(Err(error)) => this.failure(error),
                result => result,
            };
        }
        for _ in 0..POLL_BUDGET {
            let capacity = out.remaining().min(WRITE_LIMIT);
            match this
                .tls
                .read_plaintext(out.initialize_unfilled_to(capacity))
            {
                Ok(count) => {
                    out.advance(count);
                    return Poll::Ready(Ok(()));
                }
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
                Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
                Err(error) => return this.failure(error),
            }
            // A pending reverse-direction write must not prevent reading a
            // complete authenticated record. This matters under duplex pressure.
            if let Poll::Ready(Err(error)) = this.poll_tls_write(cx) {
                return this.failure(error);
            }
            match this.read_record(cx) {
                Ok(_) => {}
                Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
                Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                    return Poll::Pending;
                }
                Err(error) => return this.failure(error),
            }
        }
        cx.waker().wake_by_ref();
        Poll::Pending
    }
}

impl<S: AsyncRead + AsyncWrite + Unpin> AsyncWrite for Stream<S> {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        this.check_live()?;
        if this.shutdown {
            return Poll::Ready(Err(io::ErrorKind::BrokenPipe.into()));
        }
        if bytes.is_empty() {
            return Poll::Ready(Ok(0));
        }
        if this.write_raw {
            return match Pin::new(&mut this.io).poll_write(cx, bytes) {
                Poll::Ready(Err(error)) => this.failure(error),
                result => result,
            };
        }
        ready!(this.poll_tls_write(cx))?;
        // Drain the preceding ciphertext before accepting at most one record's
        // plaintext. Never return Pending after consuming this call's bytes.
        match this
            .tls
            .write_plaintext(&bytes[..bytes.len().min(WRITE_LIMIT)])
        {
            Ok(0) => this.failure(io::ErrorKind::WriteZero.into()),
            Ok(count) => Poll::Ready(Ok(count)),
            Err(error) => this.failure(error),
        }
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        this.check_live()?;
        ready!(this.poll_tls_write(cx))?;
        match Pin::new(&mut this.io).poll_flush(cx) {
            Poll::Ready(Err(error)) => this.failure(error),
            result => result,
        }
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        this.check_live()?;
        if !this.shutdown {
            // Once either direction enters Direct, an outer close_notify would
            // be interpreted as inner-stream bytes by the peer. The inner TLS
            // owner, when present, authenticates its own closure instead.
            if !this.read_raw
                && !this.write_raw
                && let Err(error) = this.tls.send_close_notify()
            {
                return this.failure(error);
            }
            this.shutdown = true;
        }
        ready!(Pin::new(&mut *this).poll_flush(cx))?;
        // TCP half-close after the authenticated alert; reads remain available
        // for peer responses and its independent close_notify.
        match Pin::new(&mut this.io).poll_shutdown(cx) {
            Poll::Ready(Err(error)) => this.failure(error),
            result => result,
        }
    }
}

struct PollIo<'a, 'b, S> {
    io: &'a mut S,
    cx: &'a mut Context<'b>,
}

impl<S: AsyncRead + Unpin> Read for PollIo<'_, '_, S> {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        let mut out = ReadBuf::new(bytes);
        match Pin::new(&mut *self.io).poll_read(self.cx, &mut out) {
            Poll::Ready(Ok(())) => Ok(out.filled().len()),
            Poll::Ready(Err(error)) => Err(error),
            Poll::Pending => Err(io::ErrorKind::WouldBlock.into()),
        }
    }
}

impl<S: AsyncWrite + Unpin> Write for PollIo<'_, '_, S> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        match Pin::new(&mut *self.io).poll_write(self.cx, bytes) {
            Poll::Ready(result) => result,
            Poll::Pending => Err(io::ErrorKind::WouldBlock.into()),
        }
    }

    fn flush(&mut self) -> io::Result<()> {
        match Pin::new(&mut *self.io).poll_flush(self.cx) {
            Poll::Ready(result) => result,
            Poll::Pending => Err(io::ErrorKind::WouldBlock.into()),
        }
    }
}

#[cfg(test)]
#[path = "stream_tests.rs"]
mod tests;
