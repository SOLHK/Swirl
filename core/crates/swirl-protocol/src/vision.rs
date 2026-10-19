//! Incremental Vision framing, bounded stream I/O and inner-TLS inspection.
//!
//! `DirectRequested` is a decoded handoff request. Decoding does not authenticate
//! the request or grant permission to bypass TLS. This module has no TLS-version
//! input or raw stream access. The stream adapter keeps its outer transport and
//! rejects requests for a raw handoff that transport cannot safely provide.
//! Inner-TLS inspection describes wire eligibility; it is not authentication.

pub mod record;
pub mod stream;
pub mod tls;

use std::{fmt, ops::Range};

/// Component client for an already authenticated outer transport. It writes the
/// existing VLESS request with the exact Vision Addons, and retains the existing
/// lazy, strict response-prefix decoder beneath Vision framing. The caller owns
/// the authentication/connect deadline; native configuration/runtime startup
/// still rejects unsupported REALITY/Vision product requirements.
///
/// No authentication is inferred from a successful TCP connection. This API
/// cannot extract its supplied transport or perform a raw/direct handoff.
pub async fn client_over_authenticated(
    mut transport: swirl_transport::BoxStream,
    uuid: &str,
    target: &crate::Target,
    prefix_limit: std::time::Duration,
) -> crate::Result<stream::Stream<swirl_transport::BoxStream>> {
    use tokio::io::AsyncWriteExt;

    let request = crate::vless::request_with_flow(uuid, target, Some("xtls-rprx-vision"))?;
    let id = swirl_subscription::uuid_bytes(uuid).ok_or("VlessUuid")?;
    tokio::time::timeout(prefix_limit, async {
        transport.write_all(&request).await?;
        transport.flush().await
    })
    .await
    .map_err(|_| "VisionRequestTimeout")?
    .map_err(|_| "VisionRequestWrite")?;
    let response: swirl_transport::BoxStream =
        Box::new(crate::vless::Stream::new(transport, prefix_limit));
    Ok(stream::Stream::new(response, id, stream::Role::Client))
}

pub const UUID_LEN: usize = 16;
pub const HEADER_LEN: usize = 5;
pub const MAX_PART_LEN: usize = u16::MAX as usize;
pub const MAX_FRAME_LEN: usize = UUID_LEN + HEADER_LEN + 2 * MAX_PART_LEN;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Command {
    Continue,
    EndPadding,
    DirectRequested,
}

impl Command {
    fn wire(self) -> u8 {
        match self {
            Self::Continue => 0,
            Self::EndPadding => 1,
            Self::DirectRequested => 2,
        }
    }
}

impl TryFrom<u8> for Command {
    type Error = Error;

    fn try_from(value: u8) -> Result<Self, Error> {
        match value {
            0 => Ok(Self::Continue),
            1 => Ok(Self::EndPadding),
            2 => Ok(Self::DirectRequested),
            _ => Err(Error::UnknownCommand),
        }
    }
}

/// Static errors deliberately contain no UUID, flow string or application data.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Error {
    UnsupportedFlow,
    UnknownCommand,
    UuidMismatch,
    ContentTooLarge,
    PaddingTooLarge,
    TruncatedUuid,
    TruncatedHeader,
    TruncatedContent,
    TruncatedPadding,
    AfterTerminal,
    AfterEof,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Vision{self:?}")
    }
}

impl std::error::Error for Error {}

/// Complete length-prefixed VLESS request Addons for the supported flow names.
/// Missing/empty flow keeps the existing no-Addons request. Unknown flows fail.
pub fn request_addons(flow: Option<&str>) -> Result<&'static [u8], Error> {
    match flow {
        None | Some("") => Ok(&[0]),
        Some("xtls-rprx-vision") => Ok(b"\x12\x0a\x10xtls-rprx-vision"),
        _ => Err(Error::UnsupportedFlow),
    }
}

/// One encoder per direction. Successful terminal frames cannot be followed by
/// another Vision frame. Validation failures leave the prior state unchanged.
pub struct Encoder {
    uuid: [u8; UUID_LEN],
    first: bool,
    terminal: bool,
}

impl Encoder {
    pub fn new(uuid: [u8; UUID_LEN]) -> Self {
        Self {
            uuid,
            first: true,
            terminal: false,
        }
    }

    pub fn frame(
        &mut self,
        command: Command,
        content: &[u8],
        padding: &[u8],
    ) -> Result<Vec<u8>, Error> {
        if self.terminal {
            return Err(Error::AfterTerminal);
        }
        let content_len = u16::try_from(content.len()).map_err(|_| Error::ContentTooLarge)?;
        let padding_len = u16::try_from(padding.len()).map_err(|_| Error::PaddingTooLarge)?;
        let prefix = if self.first { UUID_LEN } else { 0 };
        let mut bytes = Vec::with_capacity(prefix + HEADER_LEN + content.len() + padding.len());
        if self.first {
            bytes.extend_from_slice(&self.uuid);
        }
        bytes.push(command.wire());
        bytes.extend_from_slice(&content_len.to_be_bytes());
        bytes.extend_from_slice(&padding_len.to_be_bytes());
        bytes.extend_from_slice(content);
        bytes.extend_from_slice(padding);
        self.first = false;
        self.terminal = command != Command::Continue;
        Ok(bytes)
    }
}

#[derive(Clone, Copy)]
enum State {
    Uuid {
        received: usize,
        difference: u8,
    },
    Header {
        bytes: [u8; HEADER_LEN],
        received: usize,
        boundary: bool,
    },
    Content {
        command: Command,
        remaining: usize,
        padding: usize,
    },
    Padding {
        command: Command,
        remaining: usize,
    },
    Terminal,
    Eof,
    Failed(Error),
}

/// At most one frame boundary and one borrowed payload slice per call. Bytes
/// after `consumed` belong to a later step or to the caller's pending handoff.
/// Nonempty input makes progress or returns an error; empty input is not EOF.
pub struct Step<'a> {
    pub consumed: usize,
    pub payload: &'a [u8],
    pub boundary: Option<Command>,
}

/// Fixed state memory; it never buffers a remotely declared content/padding
/// length. The first UUID must match, even when split across arbitrary reads.
/// The UUID prefix identifies framing; it does not authenticate the server.
pub struct Decoder {
    uuid: [u8; UUID_LEN],
    state: State,
}

impl Decoder {
    pub fn new(uuid: [u8; UUID_LEN]) -> Self {
        Self {
            uuid,
            state: State::Uuid {
                received: 0,
                difference: 0,
            },
        }
    }

    fn fail<T>(&mut self, error: Error) -> Result<T, Error> {
        self.state = State::Failed(error);
        Err(error)
    }

    // A transport with no direct owner may refuse this unsupported request as
    // soon as its header is known, before returning any partial terminal body.
    // This is not a completed-boundary event or a handoff permission.
    fn pending_direct_request(&self) -> bool {
        matches!(
            self.state,
            State::Content {
                command: Command::DirectRequested,
                ..
            } | State::Padding {
                command: Command::DirectRequested,
                ..
            }
        )
    }

    pub fn decode<'a>(&mut self, input: &'a [u8]) -> Result<Step<'a>, Error> {
        match self.state {
            State::Terminal => return self.fail(Error::AfterTerminal),
            State::Eof => return self.fail(Error::AfterEof),
            State::Failed(error) => return Err(error),
            _ => {}
        }
        let mut position = 0;
        let mut payload: Range<usize> = 0..0;
        loop {
            match self.state {
                State::Uuid {
                    received,
                    mut difference,
                } => {
                    let count = (UUID_LEN - received).min(input.len() - position);
                    for index in 0..count {
                        difference |= self.uuid[received + index] ^ input[position + index];
                    }
                    position += count;
                    let received = received + count;
                    self.state = State::Uuid {
                        received,
                        difference,
                    };
                    if received < UUID_LEN {
                        break;
                    }
                    if difference != 0 {
                        return self.fail(Error::UuidMismatch);
                    }
                    self.state = State::Header {
                        bytes: [0; HEADER_LEN],
                        received: 0,
                        boundary: false,
                    };
                }
                State::Header {
                    mut bytes,
                    received,
                    boundary,
                } => {
                    let count = (HEADER_LEN - received).min(input.len() - position);
                    bytes[received..received + count]
                        .copy_from_slice(&input[position..position + count]);
                    position += count;
                    let received = received + count;
                    self.state = State::Header {
                        bytes,
                        received,
                        boundary,
                    };
                    if received < HEADER_LEN {
                        break;
                    }
                    let command = match Command::try_from(bytes[0]) {
                        Ok(command) => command,
                        Err(error) => return self.fail(error),
                    };
                    self.state = State::Content {
                        command,
                        remaining: u16::from_be_bytes([bytes[1], bytes[2]]) as usize,
                        padding: u16::from_be_bytes([bytes[3], bytes[4]]) as usize,
                    };
                }
                State::Content {
                    command,
                    remaining,
                    padding,
                } => {
                    let count = remaining.min(input.len() - position);
                    payload = position..position + count;
                    position += count;
                    let remaining = remaining - count;
                    self.state = State::Content {
                        command,
                        remaining,
                        padding,
                    };
                    if remaining > 0 {
                        break;
                    }
                    self.state = State::Padding {
                        command,
                        remaining: padding,
                    };
                }
                State::Padding { command, remaining } => {
                    let count = remaining.min(input.len() - position);
                    position += count;
                    let remaining = remaining - count;
                    self.state = State::Padding { command, remaining };
                    if remaining > 0 {
                        break;
                    }
                    self.state = if command == Command::Continue {
                        State::Header {
                            bytes: [0; HEADER_LEN],
                            received: 0,
                            boundary: true,
                        }
                    } else {
                        State::Terminal
                    };
                    return Ok(Step {
                        consumed: position,
                        payload: &input[payload],
                        boundary: Some(command),
                    });
                }
                State::Failed(error) => return Err(error),
                State::Terminal | State::Eof => unreachable!("terminal states return at entry"),
            }
        }
        Ok(Step {
            consumed: position,
            payload: &input[payload],
            boundary: None,
        })
    }

    /// Framing EOF only, not proof of TLS close_notify or a completed proxy
    /// request. A complete Continue frame may legitimately be the last frame.
    /// A bare UUID already starts a frame, so UUID-without-header is truncated.
    pub fn finish(&mut self) -> Result<(), Error> {
        let error = match self.state {
            State::Uuid { received: 0, .. }
            | State::Header {
                received: 0,
                boundary: true,
                ..
            }
            | State::Terminal
            | State::Eof => {
                self.state = State::Eof;
                return Ok(());
            }
            State::Uuid { .. } => Error::TruncatedUuid,
            State::Header { .. } => Error::TruncatedHeader,
            State::Content { .. } => Error::TruncatedContent,
            State::Padding { .. } => Error::TruncatedPadding,
            State::Failed(error) => return Err(error),
        };
        self.fail(error)
    }
}
