//! Explicit I/O boundaries for an outer TLS stream carrying Vision.
//!
//! Xray may put its last authenticated Vision frame and its first raw inner
//! TLS record in one TCP read. A TLS implementation that decrypts that entire
//! read can reject the raw record before Vision sees the authenticated handoff
//! request. `TlsRecordIo` bounds ciphertext reads; `PlaintextChunks` bounds
//! plaintext delivery. Use both, respectively below and above the TLS engine.
//!
//! These adapters do not authenticate, decrypt, grant DirectReady, extract a
//! raw socket or turn TCP EOF into TLS close_notify. TLS still validates every
//! record and all handshake/closure semantics. The current Vision stream drops
//! this entire owner when it refuses a direct request.

use std::{
    io,
    pin::Pin,
    task::{Context, Poll, ready},
};
use tokio::io::{AsyncBufRead, AsyncRead, AsyncWrite, ReadBuf};

const HEADER: usize = 5;
// Includes TLS 1.2's maximum ciphertext expansion. TLS 1.3's tighter bound and
// all content-type/version validation remain the TLS engine's responsibility.
const MAX_CIPHERTEXT: usize = (1 << 14) + 2048;

/// Limits every read to the current TLS header or ciphertext body. It retains
/// only five header bytes and counters, even across partial reads/cancellation.
/// A complete record is delivered without an artificial Pending or time delay.
pub struct TlsRecordIo<S> {
    inner: S,
    header: [u8; HEADER],
    header_used: usize,
    body_remaining: usize,
    failed: Option<io::ErrorKind>,
}

impl<S> TlsRecordIo<S> {
    pub fn new(inner: S) -> Self {
        Self {
            inner,
            header: [0; HEADER],
            header_used: 0,
            body_remaining: 0,
            failed: None,
        }
    }
}

impl<S: AsyncRead + Unpin> AsyncRead for TlsRecordIo<S> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if let Some(kind) = this.failed {
            return Poll::Ready(Err(io::Error::new(kind, "VisionOuterRecordBoundary")));
        }
        if out.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        let header = this.body_remaining == 0;
        let remaining = if header {
            HEADER - this.header_used
        } else {
            this.body_remaining
        };
        let limit = out.remaining().min(remaining);
        let mut part = ReadBuf::new(out.initialize_unfilled_to(limit));
        ready!(Pin::new(&mut this.inner).poll_read(cx, &mut part))?;
        let count = part.filled().len();
        if count == 0 {
            if this.header_used != 0 || this.body_remaining != 0 {
                this.failed = Some(io::ErrorKind::UnexpectedEof);
                return Poll::Ready(Err(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "VisionTruncatedOuterRecord",
                )));
            }
            // Only the enclosing TLS reader can decide whether EOF followed a
            // verified close_notify. A boundary alone is never authenticated.
            return Poll::Ready(Ok(()));
        }
        if header {
            this.header[this.header_used..this.header_used + count].copy_from_slice(part.filled());
            this.header_used += count;
            if this.header_used == HEADER {
                this.body_remaining =
                    usize::from(u16::from_be_bytes([this.header[3], this.header[4]]));
                if this.body_remaining > MAX_CIPHERTEXT {
                    this.failed = Some(io::ErrorKind::InvalidData);
                    return Poll::Ready(Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "VisionOuterRecordTooLarge",
                    )));
                }
                this.header_used = 0;
            }
        } else {
            this.body_remaining -= count;
        }
        out.advance(count);
        Poll::Ready(Ok(()))
    }
}

impl<S: AsyncWrite + Unpin> AsyncWrite for TlsRecordIo<S> {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.get_mut().inner).poll_write(cx, bytes)
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_flush(cx)
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_shutdown(cx)
    }
}

/// Returns the current authenticated plaintext chunk before polling the TLS
/// engine again. `TlsStream::poll_read` may otherwise fill the caller's entire
/// buffer and read ahead after that chunk. This adapter never batches chunks.
pub struct PlaintextChunks<S> {
    inner: S,
}

impl<S> PlaintextChunks<S> {
    pub fn new(inner: S) -> Self {
        Self { inner }
    }
}

impl<S: AsyncBufRead + Unpin> AsyncRead for PlaintextChunks<S> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if out.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        let inner = &mut self.get_mut().inner;
        let chunk = ready!(Pin::new(&mut *inner).poll_fill_buf(cx))?;
        let count = chunk.len().min(out.remaining());
        out.put_slice(&chunk[..count]);
        Pin::new(inner).consume(count);
        Poll::Ready(Ok(()))
    }
}

impl<S: AsyncWrite + Unpin> AsyncWrite for PlaintextChunks<S> {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.get_mut().inner).poll_write(cx, bytes)
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_flush(cx)
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_shutdown(cx)
    }
}
