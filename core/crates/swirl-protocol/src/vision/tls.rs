//! Bounded, incremental inspection of the inner TLS wire stream.
//!
//! Hello messages may cross both reads and TLS records. Extensions are parsed
//! structurally, never found by searching for a byte pattern in application
//! data. This observer does not own inner TLS keys or verify its Finished;
//! those responsibilities stay with the actual inner TLS endpoints. A
//! `Candidate` is consequently never permission to bypass the outer channel.

use sha2::{Digest, Sha256};

const MAX_HELLO: usize = 64 * 1024;
const MAX_SUITES: usize = 256;
const MAX_EXTENSIONS: usize = 256;
const RETRY_RANDOM: [u8; 32] = [
    0xcf, 0x21, 0xad, 0x74, 0xe5, 0x9a, 0x61, 0x11, 0xbe, 0x1d, 0x8c, 0x02, 0x1e, 0x65, 0xb8, 0x91,
    0xc2, 0xa2, 0x11, 0x16, 0x7a, 0xbb, 0x8c, 0x5e, 0x07, 0x9e, 0x09, 0xe2, 0xc8, 0xa8, 0x33, 0x9c,
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Direction {
    ClientToServer,
    ServerToClient,
}

impl Direction {
    fn index(self) -> usize {
        match self {
            Self::ClientToServer => 0,
            Self::ServerToClient => 1,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Ineligible {
    NotTls,
    Malformed,
    InspectionLimit,
    HelloRetryRequest,
    Version,
    CipherNotOffered,
    CipherUnsupported,
    SessionIdMismatch,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Eligibility {
    Pending,
    Ineligible(Ineligible),
    /// Both complete hellos describe TLS 1.3 with a supported selected suite.
    /// Record boundaries, encrypted data and transport ownership are separate.
    Candidate {
        cipher_suite: u16,
    },
}

struct Hello {
    tls13: bool,
    retry: bool,
    random: [u8; 32],
    session_id: Vec<u8>,
    suites: Vec<u16>,
    stable_extensions: [u8; 32],
    supported_groups: Vec<u16>,
    key_share_groups: Vec<u16>,
    key_share: Option<[u8; 32]>,
    selected_group: Option<u16>,
    cookie: Option<[u8; 32]>,
    early_data: bool,
    pre_shared_key: bool,
}

enum Status {
    Inspecting,
    Hello(Box<Hello>),
    Ineligible(Ineligible),
}

struct DirectionState {
    direction: Direction,
    status: Status,
    record_header: [u8; 5],
    header_used: usize,
    record_remaining: usize,
    hello: Vec<u8>,
    hello_total: Option<usize>,
    application_record: bool,
    retrying: bool,
}

impl DirectionState {
    fn new(direction: Direction) -> Self {
        Self {
            direction,
            status: Status::Inspecting,
            record_header: [0; 5],
            header_used: 0,
            record_remaining: 0,
            hello: Vec::new(),
            hello_total: None,
            application_record: false,
            retrying: false,
        }
    }

    fn reject(&mut self, reason: Ineligible) {
        self.status = Status::Ineligible(reason);
        self.hello = Vec::new();
        self.hello_total = None;
    }

    fn hello_bytes(&mut self, mut bytes: &[u8]) {
        while !bytes.is_empty() && matches!(self.status, Status::Inspecting) {
            let target = self.hello_total.unwrap_or(4);
            let count = (target - self.hello.len()).min(bytes.len());
            let needed = self.hello.len() + count;
            if needed > self.hello.capacity() {
                // Keep capacity bounded as well as length. Unrestricted Vec
                // growth could double a nearly full 64 KiB partial hello.
                let capacity = needed.max(self.hello.capacity() * 2).min(MAX_HELLO);
                self.hello.reserve_exact(capacity - self.hello.len());
            }
            self.hello.extend_from_slice(&bytes[..count]);
            bytes = &bytes[count..];
            if self.hello.len() != target {
                break;
            }
            if self.hello_total.is_none() {
                let expected = match self.direction {
                    Direction::ClientToServer => 1,
                    Direction::ServerToClient => 2,
                };
                if self.hello[0] != expected {
                    self.reject(Ineligible::Malformed);
                    break;
                }
                let length = ((self.hello[1] as usize) << 16)
                    | ((self.hello[2] as usize) << 8)
                    | self.hello[3] as usize;
                if length == 0 || length > MAX_HELLO - 4 {
                    self.reject(Ineligible::InspectionLimit);
                    break;
                }
                self.hello_total = Some(length + 4);
            } else {
                let parsed = parse_hello(self.direction, &self.hello[4..]);
                self.hello = Vec::new();
                self.hello_total = None;
                self.status = match parsed {
                    Ok(hello) => Status::Hello(Box::new(hello)),
                    Err(reason) => Status::Ineligible(reason),
                };
                if !bytes.is_empty() && matches!(&self.status, Status::Hello(hello) if hello.retry)
                {
                    self.reject(Ineligible::HelloRetryRequest);
                }
            }
        }
    }

    fn observe(&mut self, mut bytes: &[u8]) {
        while !bytes.is_empty() {
            if matches!(self.status, Status::Ineligible(_)) {
                return;
            }
            let retrying =
                self.retrying || matches!(&self.status, Status::Hello(hello) if hello.retry);
            if self.header_used < 5 {
                let count = (5 - self.header_used).min(bytes.len());
                self.record_header[self.header_used..self.header_used + count]
                    .copy_from_slice(&bytes[..count]);
                self.header_used += count;
                bytes = &bytes[count..];
                // Detect ordinary application protocols without retaining a
                // false TLS header until a later read happens to complete it.
                if self.record_header[0] != 22
                    && !(retrying && self.record_header[0] == 20)
                    && matches!(self.status, Status::Inspecting)
                {
                    self.reject(Ineligible::NotTls);
                    return;
                }
                if self.header_used < 5 {
                    continue;
                }
                let kind = self.record_header[0];
                if kind == 22 && matches!(&self.status, Status::Hello(hello) if hello.retry) {
                    self.reject(Ineligible::HelloRetryRequest);
                    return;
                }
                let length =
                    u16::from_be_bytes([self.record_header[3], self.record_header[4]]) as usize;
                let inspecting = matches!(self.status, Status::Inspecting);
                let maximum = if inspecting {
                    16 * 1024
                } else {
                    16 * 1024 + 256
                };
                if !matches!(kind, 20..=23)
                    || self.record_header[1] != 3
                    || !matches!(self.record_header[2], 1..=3)
                    || length == 0
                    || length > maximum
                    || (inspecting && kind != 22 && !(retrying && kind == 20))
                    || (retrying && kind == 20 && (length != 1 || !self.hello.is_empty()))
                {
                    self.reject(Ineligible::Malformed);
                    return;
                }
                self.record_remaining = length;
            }
            let count = self.record_remaining.min(bytes.len());
            if retrying && self.record_header[0] == 20 {
                if count != 0 && bytes[..count] != [1] {
                    self.reject(Ineligible::Malformed);
                    return;
                }
            } else if matches!(self.status, Status::Inspecting) {
                self.hello_bytes(&bytes[..count]);
                // A plaintext HRR must end its record. Otherwise a read split
                // at the hello boundary could hide a trailing handshake.
                if self.record_remaining != count
                    && matches!(&self.status, Status::Hello(hello) if hello.retry)
                {
                    self.reject(Ineligible::HelloRetryRequest);
                    return;
                }
            }
            bytes = &bytes[count..];
            self.record_remaining -= count;
            if self.record_remaining == 0 {
                if self.record_header[0] == 23 {
                    self.application_record = true;
                }
                self.header_used = 0;
            }
        }
    }
}

struct Cursor<'a>(&'a [u8]);

impl<'a> Cursor<'a> {
    fn take(&mut self, length: usize) -> Result<&'a [u8], Ineligible> {
        if length > self.0.len() {
            return Err(Ineligible::Malformed);
        }
        let (bytes, tail) = self.0.split_at(length);
        self.0 = tail;
        Ok(bytes)
    }

    fn byte(&mut self) -> Result<u8, Ineligible> {
        Ok(self.take(1)?[0])
    }

    fn word(&mut self) -> Result<u16, Ineligible> {
        let bytes = self.take(2)?;
        Ok(u16::from_be_bytes([bytes[0], bytes[1]]))
    }

    fn vector8(&mut self) -> Result<&'a [u8], Ineligible> {
        let length = self.byte()? as usize;
        self.take(length)
    }

    fn vector16(&mut self) -> Result<&'a [u8], Ineligible> {
        let length = self.word()? as usize;
        self.take(length)
    }
}

fn parse_hello(direction: Direction, bytes: &[u8]) -> Result<Hello, Ineligible> {
    let mut cursor = Cursor(bytes);
    let legacy_version = cursor.word()?;
    if !(0x0301..=0x0303).contains(&legacy_version) {
        return Err(Ineligible::Version);
    }
    let mut random = [0; 32];
    random.copy_from_slice(cursor.take(32)?);
    let retry = direction == Direction::ServerToClient && random == RETRY_RANDOM;
    let session_id = cursor.vector8()?.to_vec();
    if session_id.len() > 32 {
        return Err(Ineligible::Malformed);
    }
    let mut suites = Vec::new();
    let compression;
    match direction {
        Direction::ClientToServer => {
            let offered = cursor.vector16()?;
            if offered.is_empty() || !offered.len().is_multiple_of(2) {
                return Err(Ineligible::Malformed);
            }
            if offered.len() / 2 > MAX_SUITES {
                return Err(Ineligible::InspectionLimit);
            }
            suites.extend(
                offered
                    .as_chunks::<2>()
                    .0
                    .iter()
                    .map(|pair| u16::from_be_bytes([pair[0], pair[1]])),
            );
            compression = cursor.vector8()?.to_vec();
            if !compression.contains(&0) {
                return Err(Ineligible::Malformed);
            }
        }
        Direction::ServerToClient => {
            suites.push(cursor.word()?);
            compression = vec![cursor.byte()?];
            if compression != [0] {
                return Err(Ineligible::Malformed);
            }
        }
    }
    let mut tls13 = false;
    let mut stable_extensions = Sha256::new();
    let mut supported_groups = Vec::new();
    let mut key_share_groups = Vec::new();
    let mut key_share = None;
    let mut selected_group = None;
    let mut cookie = None;
    let mut early_data = false;
    let mut pre_shared_key = false;
    if !cursor.0.is_empty() {
        let mut extensions = Cursor(cursor.vector16()?);
        if !cursor.0.is_empty() {
            return Err(Ineligible::Malformed);
        }
        let mut seen = Vec::new();
        while !extensions.0.is_empty() {
            let kind = extensions.word()?;
            let value = extensions.vector16()?;
            if seen.contains(&kind) {
                return Err(Ineligible::Malformed);
            }
            if seen.len() == MAX_EXTENSIONS {
                return Err(Ineligible::InspectionLimit);
            }
            seen.push(kind);
            // RFC 8446 4.1.2 permits only these changes in ClientHello2.
            // Retain a fixed-size digest, rather than another full hello.
            if !matches!(kind, 21 | 41 | 42 | 44 | 51) {
                stable_extensions.update(kind.to_be_bytes());
                stable_extensions.update((value.len() as u16).to_be_bytes());
                stable_extensions.update(value);
            }
            if retry && !matches!(kind, 43 | 44 | 51) {
                return Err(Ineligible::HelloRetryRequest);
            }
            if kind == 10 && direction == Direction::ClientToServer {
                let mut groups = Cursor(value);
                let list = groups.vector16()?;
                if !groups.0.is_empty()
                    || list.is_empty()
                    || !list.len().is_multiple_of(2)
                    || list.len() / 2 > MAX_EXTENSIONS
                {
                    return Err(Ineligible::Malformed);
                }
                supported_groups.extend(
                    list.as_chunks::<2>()
                        .0
                        .iter()
                        .map(|v| u16::from_be_bytes(*v)),
                );
            }
            if kind == 51 {
                key_share = Some(Sha256::digest(value).into());
                let mut share = Cursor(value);
                if direction == Direction::ClientToServer {
                    let mut entries = Cursor(share.vector16()?);
                    if !share.0.is_empty() {
                        return Err(Ineligible::Malformed);
                    }
                    while !entries.0.is_empty() {
                        let group = entries.word()?;
                        if entries.vector16()?.is_empty()
                            || key_share_groups.contains(&group)
                            || key_share_groups.len() == MAX_EXTENSIONS
                        {
                            return Err(Ineligible::Malformed);
                        }
                        key_share_groups.push(group);
                    }
                } else {
                    selected_group = Some(share.word()?);
                    if (!retry && share.vector16()?.is_empty()) || !share.0.is_empty() {
                        return Err(Ineligible::Malformed);
                    }
                }
            }
            if kind == 44 {
                let mut encoded = Cursor(value);
                if encoded.vector16()?.is_empty() || !encoded.0.is_empty() {
                    return Err(Ineligible::Malformed);
                }
                cookie = Some(Sha256::digest(value).into());
            }
            early_data |= kind == 42;
            pre_shared_key |= kind == 41;
            if kind == 43 {
                match direction {
                    Direction::ClientToServer => {
                        let mut versions = Cursor(value);
                        let values = versions.vector8()?;
                        if !versions.0.is_empty()
                            || values.is_empty()
                            || !values.len().is_multiple_of(2)
                        {
                            return Err(Ineligible::Malformed);
                        }
                        tls13 = values.as_chunks::<2>().0.contains(&[3, 4]);
                    }
                    Direction::ServerToClient => {
                        if value != [3, 4] {
                            return Err(Ineligible::Version);
                        }
                        tls13 = true;
                    }
                }
            }
        }
    }
    if tls13 && (legacy_version != 0x0303 || compression != [0]) {
        return Err(Ineligible::Malformed);
    }
    if retry && (!tls13 || (selected_group.is_none() && cookie.is_none())) {
        return Err(Ineligible::HelloRetryRequest);
    }
    Ok(Hello {
        tls13,
        retry,
        random,
        session_id,
        suites,
        stable_extensions: stable_extensions.finalize().into(),
        supported_groups,
        key_share_groups,
        key_share,
        selected_group,
        cookie,
        early_data,
        pre_shared_key,
    })
}

/// Observes both directions of one inner connection. Retained memory is bounded
/// to one 64 KiB hello per direction and bounded hello metadata. One retry keeps
/// only the first flight's metadata and extension digests, not another transcript.
pub struct Inspection {
    directions: [DirectionState; 2],
    retry: Option<(Box<Hello>, Box<Hello>)>,
}

impl Default for Inspection {
    fn default() -> Self {
        Self::new()
    }
}

impl Inspection {
    pub fn new() -> Self {
        Self {
            directions: [
                DirectionState::new(Direction::ClientToServer),
                DirectionState::new(Direction::ServerToClient),
            ],
            retry: None,
        }
    }

    pub fn observe(&mut self, direction: Direction, bytes: &[u8]) {
        self.directions[direction.index()].observe(bytes);
        if self.retry.is_some()
            && matches!(&self.directions[1].status, Status::Hello(hello) if hello.retry)
        {
            self.directions[1].reject(Ineligible::HelloRetryRequest);
            return;
        }
        let (Status::Hello(client), Status::Hello(server)) =
            (&self.directions[0].status, &self.directions[1].status)
        else {
            return;
        };
        if !server.retry {
            return;
        }
        let selected = server.suites[0];
        if !client.tls13
            || !server.tls13
            || client.session_id != server.session_id
            || !client.suites.contains(&selected)
            || !(0x1301..=0x1304).contains(&selected)
            || client.cookie.is_some()
            // PSK binder/identity updates need a separate retry-aware parser.
            // Do not grant direct eligibility based on opaque PSK changes.
            || client.pre_shared_key
            || self.directions[1].application_record
            || server.selected_group.is_some_and(|group| {
                !client.supported_groups.contains(&group)
                    || client.key_share_groups.contains(&group)
            })
        {
            self.directions[1].reject(Ineligible::HelloRetryRequest);
            return;
        }
        // Do not reset record offsets: HRR and a partial compatibility CCS can
        // arrive in one read. Only the hello parser starts a new flight.
        let Status::Hello(client) =
            std::mem::replace(&mut self.directions[0].status, Status::Inspecting)
        else {
            unreachable!()
        };
        let Status::Hello(server) =
            std::mem::replace(&mut self.directions[1].status, Status::Inspecting)
        else {
            unreachable!()
        };
        self.retry = Some((client, server));
        for state in &mut self.directions {
            state.retrying = true;
            state.application_record = false;
        }
    }

    pub fn eligibility(&self) -> Eligibility {
        for state in &self.directions {
            if let Status::Ineligible(reason) = state.status {
                return Eligibility::Ineligible(reason);
            }
        }
        let (Status::Hello(client), Status::Hello(server)) =
            (&self.directions[0].status, &self.directions[1].status)
        else {
            return Eligibility::Pending;
        };
        if let Some((first, retry)) = &self.retry
            && (server.retry
                || client.random != first.random
                || client.session_id != first.session_id
                || client.suites != first.suites
                || client.stable_extensions != first.stable_extensions
                || client.cookie != retry.cookie
                || client.early_data
                || client.pre_shared_key
                || server.pre_shared_key
                || server.suites != retry.suites
                || server.cookie.is_some()
                || match retry.selected_group {
                    Some(group) => {
                        client.key_share_groups != [group] || server.selected_group != Some(group)
                    }
                    None => {
                        client.key_share != first.key_share
                            || server
                                .selected_group
                                .is_some_and(|group| !client.key_share_groups.contains(&group))
                    }
                })
        {
            return Eligibility::Ineligible(Ineligible::HelloRetryRequest);
        }
        if !client.tls13 || !server.tls13 {
            return Eligibility::Ineligible(Ineligible::Version);
        }
        if client.session_id != server.session_id {
            return Eligibility::Ineligible(Ineligible::SessionIdMismatch);
        }
        let selected = server.suites[0];
        if !client.suites.contains(&selected) {
            return Eligibility::Ineligible(Ineligible::CipherNotOffered);
        }
        // The pinned Xray peer supports 0x1301..=0x1304 for Vision direct
        // eligibility, but excludes the short-tag CCM_8 suite (0x1305).
        if !(0x1301..=0x1304).contains(&selected) {
            return Eligibility::Ineligible(Ineligible::CipherUnsupported);
        }
        Eligibility::Candidate {
            cipher_suite: selected,
        }
    }

    pub fn at_record_boundary(&self, direction: Direction) -> bool {
        let state = &self.directions[direction.index()];
        !matches!(state.status, Status::Ineligible(_))
            && state.header_used == 0
            && state.record_remaining == 0
    }

    pub fn application_record_seen(&self, direction: Direction) -> bool {
        self.directions[direction.index()].application_record
    }

    pub fn is_tls(&self, direction: Direction) -> bool {
        let state = &self.directions[direction.index()];
        matches!(state.status, Status::Hello(_))
            || (state.retrying && matches!(state.status, Status::Inspecting))
            || (matches!(state.status, Status::Inspecting)
                && (state.header_used > 0 || !state.hello.is_empty())
                && state.record_header[0] == 22)
    }

    /// Current retained hello bytes, for bounded-memory assertions/diagnostics.
    pub fn buffered_bytes(&self) -> usize {
        self.directions.iter().map(|state| state.hello.len()).sum()
    }
}
