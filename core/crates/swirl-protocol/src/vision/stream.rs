//! Async Vision framing while retaining ownership of the supplied outer stream.
//!
//! Construct only after outer authentication and VLESS request/response handling.
//! The outer stream must itself distinguish authenticated TLS closure from bare
//! TCP EOF. This adapter neither authenticates that stream nor reinterprets its
//! EOF as close_notify. No raw socket is extracted or cloned.
//!
//! EndPadding keeps using the same outer stream. Generic transports still reject
//! DirectRequested. Only the concrete authenticated REALITY constructor installs
//! the private operations that switch its retained socket owner in each direction.
//! Inner TLS eligibility and a completed boundary must precede those operations.

use super::{Command, Decoder, Encoder, UUID_LEN, tls};
use ring::rand::{SecureRandom, SystemRandom};
use std::{
    io,
    pin::Pin,
    task::{Context, Poll, ready},
};
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};

const READ_BUFFER: usize = 8192;
pub const WRITE_CONTENT_LIMIT: usize = 16 * 1024;
const POLL_BUDGET: usize = 64;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Role {
    Client,
    Server,
}

impl Role {
    fn read_direction(self) -> tls::Direction {
        match self {
            Self::Client => tls::Direction::ServerToClient,
            Self::Server => tls::Direction::ClientToServer,
        }
    }

    fn write_direction(self) -> tls::Direction {
        match self {
            Self::Client => tls::Direction::ClientToServer,
            Self::Server => tls::Direction::ServerToClient,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReadMode {
    Framed,
    OuterStream,
    DirectRequested,
    Direct,
    Closed,
}

struct Handoff<S> {
    read: fn(&mut S) -> io::Result<Vec<u8>>,
    write: fn(&mut S, &mut Context<'_>) -> Poll<io::Result<()>>,
}

#[derive(Clone, Copy)]
struct Failure {
    kind: io::ErrorKind,
    message: &'static str,
}

impl Failure {
    fn error(self) -> io::Error {
        io::Error::new(self.kind, self.message)
    }
}

/// Holds at most one encoded outbound frame and one read block. Successful
/// writes acknowledge copied application bytes; pending polls never acknowledge
/// new bytes. Dropping an I/O future preserves its exact frame offset in this
/// owner, and dropping/aborting this owner releases the underlying stream.
/// Like other buffered writers, flush after writing a request before waiting
/// for its response. A read does not implicitly drive or flush the write side.
pub struct Stream<S> {
    inner: Option<S>,
    role: Role,
    encoder: Encoder,
    decoder: Decoder,
    inspection: tls::Inspection,
    read_mode: ReadMode,
    wire: Box<[u8; READ_BUFFER]>,
    wire_used: usize,
    wire_position: usize,
    payload: Vec<u8>,
    payload_position: usize,
    write_frame: Vec<u8>,
    write_position: usize,
    write_framed: bool,
    handoff: Option<Handoff<S>>,
    write_direct_pending: bool,
    write_direct: bool,
    read_direct: bool,
    shutdown_started: bool,
    write_closed: bool,
    failure: Option<Failure>,
}

impl<S> Stream<S> {
    pub fn new(inner: S, uuid: [u8; UUID_LEN], role: Role) -> Self {
        Self {
            inner: Some(inner),
            role,
            encoder: Encoder::new(uuid),
            decoder: Decoder::new(uuid),
            inspection: tls::Inspection::new(),
            read_mode: ReadMode::Framed,
            wire: Box::new([0; READ_BUFFER]),
            wire_used: 0,
            wire_position: 0,
            payload: Vec::with_capacity(READ_BUFFER),
            payload_position: 0,
            write_frame: Vec::new(),
            write_position: 0,
            write_framed: true,
            handoff: None,
            write_direct_pending: false,
            write_direct: false,
            read_direct: false,
            shutdown_started: false,
            write_closed: false,
            failure: None,
        }
    }

    pub fn inspection(&self) -> &tls::Inspection {
        &self.inspection
    }

    pub fn read_mode(&self) -> ReadMode {
        self.read_mode
    }

    pub fn write_padding_active(&self) -> bool {
        self.write_framed
    }

    pub fn direct_read_active(&self) -> bool {
        self.read_direct
    }

    pub fn direct_write_active(&self) -> bool {
        self.write_direct
    }

    pub fn buffered_bytes(&self) -> usize {
        self.wire_used - self.wire_position + self.payload.len() - self.payload_position
            + self.write_frame.len()
            - self.write_position
            + self.inspection.buffered_bytes()
    }

    fn fail(&mut self, kind: io::ErrorKind, message: &'static str) -> io::Error {
        let failure = *self.failure.get_or_insert(Failure { kind, message });
        // No task or independently owned split socket can outlive this owner.
        // A fatal protocol error must not leave an outbound writer usable.
        self.inner = None;
        self.payload = Vec::new();
        self.payload_position = 0;
        self.write_frame = Vec::new();
        self.write_position = 0;
        self.write_direct_pending = false;
        self.wire_used = 0;
        self.wire_position = 0;
        self.inspection = tls::Inspection::new();
        failure.error()
    }

    /// Abort both directions immediately. Normal upload half-close instead uses
    /// AsyncWrite::shutdown and leaves the downlink readable.
    pub fn abort(&mut self) {
        let _ = self.fail(io::ErrorKind::Interrupted, "VisionCancelled");
    }
}

impl<S: AsyncRead + AsyncWrite + Unpin>
    Stream<crate::vless::Stream<swirl_transport::reality::Stream<S>>>
{
    pub(super) fn over_reality(
        inner: crate::vless::Stream<swirl_transport::reality::Stream<S>>,
        uuid: [u8; UUID_LEN],
    ) -> Self {
        let mut stream = Self::new(inner, uuid, Role::Client);
        stream.handoff = Some(Handoff {
            read: |owner| owner.response_transport_mut()?.enable_raw_read(),
            write: |owner, cx| match owner.transport_mut() {
                Ok(owner) => owner.poll_enable_raw_write(cx),
                Err(error) => Poll::Ready(Err(error)),
            },
        });
        stream
    }
}

fn random_below(random: &SystemRandom, upper: u32) -> io::Result<usize> {
    // Rejection sampling preserves the selected padding distribution without
    // modulo bias; ring owns all entropy production.
    let accepted = u32::MAX - u32::MAX % upper;
    for _ in 0..128 {
        let mut bytes = [0; 4];
        random
            .fill(&mut bytes)
            .map_err(|_| io::Error::other("VisionPaddingEntropy"))?;
        let value = u32::from_be_bytes(bytes);
        if value < accepted {
            return Ok((value % upper) as usize);
        }
    }
    Err(io::Error::other("VisionPaddingEntropy"))
}

fn padding(content: usize, long: bool) -> io::Result<Vec<u8>> {
    let random = SystemRandom::new();
    let length = if long && content < 900 {
        900 - content + random_below(&random, 500)?
    } else {
        random_below(&random, 256)?
    };
    let mut bytes = vec![0; length];
    random
        .fill(&mut bytes)
        .map_err(|_| io::Error::other("VisionPaddingEntropy"))?;
    Ok(bytes)
}

impl<S: AsyncWrite + Unpin> Stream<S> {
    fn poll_drain(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        for _ in 0..POLL_BUDGET {
            if self.write_position == self.write_frame.len() {
                self.write_frame.clear();
                self.write_position = 0;
                if self.write_direct_pending {
                    let switch = self.handoff.as_ref().expect("owned direct request").write;
                    match ready!(switch(
                        self.inner
                            .as_mut()
                            .expect("live stream after failure check"),
                        cx,
                    )) {
                        Ok(()) => {
                            self.write_direct_pending = false;
                            self.write_direct = true;
                        }
                        Err(error) => {
                            return Poll::Ready(Err(
                                self.fail(error.kind(), "VisionDirectWriteHandoff")
                            ));
                        }
                    }
                }
                return Poll::Ready(Ok(()));
            }
            let result = ready!(
                Pin::new(
                    self.inner
                        .as_mut()
                        .expect("live stream after failure check")
                )
                .poll_write(cx, &self.write_frame[self.write_position..])
            );
            match result {
                Ok(0) => {
                    return Poll::Ready(Err(
                        self.fail(io::ErrorKind::WriteZero, "VisionOuterWriteZero")
                    ));
                }
                Ok(count) => self.write_position += count,
                Err(error) => {
                    return Poll::Ready(Err(self.fail(error.kind(), "VisionOuterWrite")));
                }
            }
        }
        cx.waker().wake_by_ref();
        Poll::Pending
    }
}

impl<S: AsyncRead + Unpin> AsyncRead for Stream<S> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        out: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if let Some(failure) = this.failure {
            return Poll::Ready(Err(failure.error()));
        }
        if out.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        for _ in 0..POLL_BUDGET {
            if this.payload_position < this.payload.len() {
                let count = out
                    .remaining()
                    .min(this.payload.len() - this.payload_position);
                out.put_slice(&this.payload[this.payload_position..this.payload_position + count]);
                this.payload_position += count;
                return Poll::Ready(Ok(()));
            }
            this.payload.clear();
            this.payload_position = 0;
            if this.read_mode == ReadMode::Closed {
                return Poll::Ready(Ok(()));
            }
            if this.wire_position < this.wire_used {
                if this.read_mode == ReadMode::Framed {
                    let step = match this
                        .decoder
                        .decode(&this.wire[this.wire_position..this.wire_used])
                    {
                        Ok(step) => step,
                        Err(_) => {
                            return Poll::Ready(Err(
                                this.fail(io::ErrorKind::InvalidData, "VisionInvalidFraming")
                            ));
                        }
                    };
                    let direct = step.boundary == Some(Command::DirectRequested);
                    if (direct || this.decoder.pending_direct_request()) && this.handoff.is_none() {
                        this.read_mode = ReadMode::DirectRequested;
                        return Poll::Ready(Err(this.fail(
                            io::ErrorKind::PermissionDenied,
                            "VisionDirectOwnershipUnavailable",
                        )));
                    }
                    this.wire_position += step.consumed;
                    this.payload.extend_from_slice(step.payload);
                    this.inspection
                        .observe(this.role.read_direction(), &this.payload);
                    if direct {
                        this.read_mode = ReadMode::DirectRequested;
                        if !matches!(
                            this.inspection.eligibility(),
                            tls::Eligibility::Candidate { .. }
                        ) || !this
                            .inspection
                            .application_record_seen(this.role.read_direction())
                            || !this
                                .inspection
                                .at_record_boundary(this.role.read_direction())
                        {
                            return Poll::Ready(Err(this.fail(
                                io::ErrorKind::PermissionDenied,
                                "VisionDirectInnerTlsIneligible",
                            )));
                        }
                        let switch = this.handoff.as_ref().expect("checked direct owner").read;
                        let residual = match switch(
                            this.inner
                                .as_mut()
                                .expect("live stream after failure check"),
                        ) {
                            Ok(residual) => residual,
                            Err(error) => {
                                return Poll::Ready(Err(
                                    this.fail(error.kind(), "VisionDirectReadHandoff")
                                ));
                            }
                        };
                        // All these bytes precede the first raw socket read:
                        // terminal payload, already-delivered TLS plaintext tail,
                        // then plaintext still buffered in the TLS engine.
                        this.payload
                            .extend_from_slice(&this.wire[this.wire_position..this.wire_used]);
                        this.payload.extend_from_slice(&residual);
                        this.wire_position = this.wire_used;
                        this.read_mode = ReadMode::Direct;
                        this.read_direct = true;
                    }
                    if step.boundary == Some(Command::EndPadding) {
                        this.read_mode = ReadMode::OuterStream;
                    }
                } else {
                    // Post-padding bytes preserve their order in the active
                    // direction; the transport owns whether they use outer TLS.
                    this.payload
                        .extend_from_slice(&this.wire[this.wire_position..this.wire_used]);
                    this.wire_position = this.wire_used;
                    if !this.read_direct {
                        this.inspection
                            .observe(this.role.read_direction(), &this.payload);
                    }
                }
                continue;
            }
            this.wire_position = 0;
            this.wire_used = 0;
            let mut bytes = ReadBuf::new(this.wire.as_mut());
            let result = ready!(
                Pin::new(
                    this.inner
                        .as_mut()
                        .expect("live stream after failure check")
                )
                .poll_read(cx, &mut bytes)
            );
            if let Err(error) = result {
                return Poll::Ready(Err(this.fail(error.kind(), "VisionOuterRead")));
            }
            this.wire_used = bytes.filled().len();
            if this.wire_used == 0 {
                if this.read_mode == ReadMode::Framed && this.decoder.finish().is_err() {
                    return Poll::Ready(Err(
                        this.fail(io::ErrorKind::UnexpectedEof, "VisionTruncatedFrame")
                    ));
                }
                this.read_mode = ReadMode::Closed;
                return Poll::Ready(Ok(()));
            }
        }
        cx.waker().wake_by_ref();
        Poll::Pending
    }
}

impl<S: AsyncWrite + Unpin> AsyncWrite for Stream<S> {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bytes: &[u8],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        if let Some(failure) = this.failure {
            return Poll::Ready(Err(failure.error()));
        }
        if this.shutdown_started {
            return Poll::Ready(Err(io::Error::new(
                io::ErrorKind::BrokenPipe,
                "VisionWriteClosed",
            )));
        }
        if bytes.is_empty() {
            return Poll::Ready(Ok(0));
        }
        ready!(this.poll_drain(cx))?;
        if !this.write_framed {
            return match ready!(
                Pin::new(
                    this.inner
                        .as_mut()
                        .expect("live stream after failure check")
                )
                .poll_write(cx, bytes)
            ) {
                Ok(0) => Poll::Ready(Err(
                    this.fail(io::ErrorKind::WriteZero, "VisionOuterWriteZero")
                )),
                Ok(count) => {
                    this.inspection
                        .observe(this.role.write_direction(), &bytes[..count]);
                    Poll::Ready(Ok(count))
                }
                Err(error) => Poll::Ready(Err(this.fail(error.kind(), "VisionOuterWrite"))),
            };
        }
        let count = bytes.len().min(WRITE_CONTENT_LIMIT);
        this.inspection
            .observe(this.role.write_direction(), &bytes[..count]);
        let eligibility = this.inspection.eligibility();
        let ending = matches!(eligibility, tls::Eligibility::Ineligible(_))
            || (this
                .inspection
                .application_record_seen(this.role.write_direction())
                && this
                    .inspection
                    .at_record_boundary(this.role.write_direction())
                && (this.handoff.is_none() || eligibility != tls::Eligibility::Pending));
        let direct = ending
            && this.handoff.is_some()
            && matches!(eligibility, tls::Eligibility::Candidate { .. });
        let command = if direct {
            Command::DirectRequested
        } else if ending {
            Command::EndPadding
        } else {
            Command::Continue
        };
        let padding = match padding(count, this.inspection.is_tls(this.role.write_direction())) {
            Ok(padding) => padding,
            Err(_) => {
                return Poll::Ready(Err(this.fail(io::ErrorKind::Other, "VisionPaddingEntropy")));
            }
        };
        this.write_frame = match this.encoder.frame(command, &bytes[..count], &padding) {
            Ok(frame) => frame,
            Err(_) => {
                return Poll::Ready(Err(
                    this.fail(io::ErrorKind::InvalidData, "VisionFrameEncode")
                ));
            }
        };
        this.write_framed = !ending;
        this.write_direct_pending = direct;
        // Return the accepted application count before attempting transport I/O.
        // A later pending/error poll must never replay or double-ack this frame.
        Poll::Ready(Ok(count))
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if let Some(failure) = this.failure {
            return Poll::Ready(Err(failure.error()));
        }
        ready!(this.poll_drain(cx))?;
        match ready!(
            Pin::new(
                this.inner
                    .as_mut()
                    .expect("live stream after failure check")
            )
            .poll_flush(cx)
        ) {
            Ok(()) => Poll::Ready(Ok(())),
            Err(error) => Poll::Ready(Err(this.fail(error.kind(), "VisionOuterFlush"))),
        }
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if let Some(failure) = this.failure {
            return Poll::Ready(Err(failure.error()));
        }
        if this.write_closed {
            return Poll::Ready(Ok(()));
        }
        this.shutdown_started = true;
        ready!(this.poll_drain(cx))?;
        match ready!(
            Pin::new(
                this.inner
                    .as_mut()
                    .expect("live stream after failure check")
            )
            .poll_shutdown(cx)
        ) {
            Ok(()) => {
                this.write_closed = true;
                Poll::Ready(Ok(()))
            }
            Err(error) => Poll::Ready(Err(this.fail(error.kind(), "VisionOuterShutdown"))),
        }
    }
}

#[cfg(test)]
#[path = "direct_tests.rs"]
mod direct_tests;
