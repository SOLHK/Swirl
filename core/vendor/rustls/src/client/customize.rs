//! Swirl's opt-in, first-flight REALITY wire adapter. No TLS cryptography lives here.

use alloc::vec::Vec;
use core::fmt::Debug;

use super::common::ClientHelloDetails;
use crate::Error;
use crate::enums::{ContentType, ProtocolVersion};
use crate::msgs::codec::{Codec, Reader};
use crate::msgs::enums::ExtensionType;
use crate::msgs::handshake::HandshakePayload;
use crate::msgs::message::MessagePayload;

/// Customize a fresh REALITY ClientHello before it is hashed or transmitted.
///
/// The input and result include the four-byte TLS handshake header, without a
/// record header. This local API is not a general TLS fingerprinting API. It
/// preserves rustls's random, session ID, SNI, ALPN, certificate decompression
/// capabilities and all actual key shares. A bounded browser offer may add
/// GREASE and TLS 1.2 camouflage offers; negotiation remains TLS 1.3 only.
/// Unsupported negotiated extensions fail closed. The callback does not waive
/// certificate, CertificateVerify or Finished verification.
pub trait ClientHelloCustomizer: Debug + Send + Sync {
    /// Return a bounded replacement for the supplied handshake encoding.
    fn customize(&self, client_hello: &[u8]) -> Result<Vec<u8>, Error>;
}

pub(super) fn apply(
    customizer: &dyn ClientHelloCustomizer,
    original: &MessagePayload<'_>,
    hello: &mut ClientHelloDetails,
) -> Result<(MessagePayload<'static>, bool), Error> {
    let MessagePayload::Handshake { encoded, .. } = original else {
        return Err(invalid());
    };
    let before = WireHello::read(encoded.bytes())?;
    let replacement = customizer.customize(encoded.bytes())?;
    let after = WireHello::read(&replacement)?;
    validate(&before, &after)?;

    // Parse for state metadata, but keep the exact returned encoding. The
    // upstream ClientExtensions decoder deliberately drops unknown extensions,
    // so re-encoding it would lose GREASE/ALPS and corrupt the transcript.
    let payload = MessagePayload::new(
        ContentType::Handshake,
        ProtocolVersion::TLSv1_3,
        &replacement,
    )?
    .into_owned();
    let MessagePayload::Handshake { parsed, .. } = &payload else {
        return Err(invalid());
    };
    let HandshakePayload::ClientHello(parsed) = &parsed.0 else {
        return Err(invalid());
    };
    hello.customized = true;
    hello.sent_extensions = after
        .extensions
        .iter()
        .map(|(kind, _)| ExtensionType::from(*kind))
        .collect();
    hello.offered_cipher_suites = parsed.cipher_suites.clone();
    hello.alpn_protocols = parsed
        .protocols
        .clone()
        .unwrap_or_default();
    hello.offered_cert_compression = parsed
        .certificate_compression_algorithms
        .is_some();
    let grease_ech = after.extension(0xfe0d).is_some();
    Ok((payload, grease_ech))
}

fn invalid() -> Error {
    Error::General("CustomClientHelloInvalid".into())
}

fn grease(value: u16) -> bool {
    value & 0x0f0f == 0x0a0a && value >> 8 == value & 0xff
}

fn vector<'a>(reader: &mut Reader<'a>, wide: bool) -> Result<&'a [u8], Error> {
    let length = if wide {
        usize::from(u16::read(reader)?)
    } else {
        usize::from(u8::read(reader)?)
    };
    reader.take(length).ok_or_else(invalid)
}

fn words(bytes: &[u8]) -> Result<Vec<u16>, Error> {
    if bytes.is_empty() || bytes.len() % 2 != 0 {
        return Err(invalid());
    }
    let mut result = Vec::new();
    for pair in bytes.chunks_exact(2) {
        let value = u16::from_be_bytes([pair[0], pair[1]]);
        if result.contains(&value) {
            return Err(invalid());
        }
        result.push(value);
    }
    Ok(result)
}

struct WireHello<'a> {
    identity: &'a [u8],
    ciphers: Vec<u16>,
    compression: &'a [u8],
    extensions: Vec<(u16, &'a [u8])>,
}

impl<'a> WireHello<'a> {
    fn read(bytes: &'a [u8]) -> Result<Self, Error> {
        if bytes.len() < 4
            || bytes.len() > 16 * 1024
            || bytes[0] != 1
            || u32::from_be_bytes([0, bytes[1], bytes[2], bytes[3]]) as usize != bytes.len() - 4
        {
            return Err(invalid());
        }
        let body = &bytes[4..];
        let mut reader = Reader::init(body);
        if u16::read(&mut reader)? != 0x0303 {
            return Err(invalid());
        }
        reader.take(32).ok_or_else(invalid)?;
        if vector(&mut reader, false)?.len() != 32 {
            return Err(invalid());
        }
        let identity = &body[..reader.used()];
        let ciphers = words(vector(&mut reader, true)?)?;
        let compression = vector(&mut reader, false)?;
        let mut entries = Reader::init(vector(&mut reader, true)?);
        reader.expect_empty("CustomClientHello")?;
        let mut extensions = Vec::new();
        while entries.any_left() {
            if extensions.len() >= 64 {
                return Err(invalid());
            }
            let kind = u16::read(&mut entries)?;
            if extensions
                .iter()
                .any(|(existing, _)| *existing == kind)
            {
                return Err(invalid());
            }
            extensions.push((kind, vector(&mut entries, true)?));
        }
        Ok(Self {
            identity,
            ciphers,
            compression,
            extensions,
        })
    }

    fn extension(&self, kind: u16) -> Option<&'a [u8]> {
        self.extensions
            .iter()
            .find_map(|(tag, body)| (*tag == kind).then_some(*body))
    }

    fn required(&self, kind: u16) -> Result<&'a [u8], Error> {
        self.extension(kind).ok_or_else(invalid)
    }
}

fn validate(before: &WireHello<'_>, after: &WireHello<'_>) -> Result<(), Error> {
    if before.identity != after.identity
        || after.compression != [0]
        || before.compression != after.compression
        || before
            .ciphers
            .iter()
            .any(|suite| !after.ciphers.contains(suite))
    {
        return Err(invalid());
    }
    // Preserve handshake identity and configured application/decompression
    // semantics. Signature schemes may differ for REALITY's pinned Ed25519
    // authentication, whose verifier remains responsible for the actual proof.
    for kind in [0, 5, 16, 27] {
        if before.extension(kind) != after.extension(kind) {
            return Err(invalid());
        }
    }
    for (kind, body) in &after.extensions {
        if !matches!(
            *kind,
            0 | 5 | 10 | 11 | 13 | 16 | 18 | 23 | 27 | 35 | 43 | 45 | 51 | 17613 | 0xfe0d | 0xff01
        ) && !grease(*kind)
        {
            return Err(invalid());
        }
        // Tickets are only camouflage, never a resumption input. Cookie,
        // PSK, early-data, real ECH inner and QUIC are absent from the allowlist.
        if *kind == 35 && !body.is_empty() {
            return Err(invalid());
        }
    }
    let mut versions = Reader::init(after.required(43)?);
    let versions_list = words(vector(&mut versions, false)?)?;
    versions.expect_empty("CustomClientHelloVersions")?;
    if !versions_list.contains(&0x0304)
        || versions_list
            .iter()
            .any(|v| !matches!(*v, 0x0303 | 0x0304) && !grease(*v))
    {
        return Err(invalid());
    }
    let mut groups = Reader::init(after.required(10)?);
    let groups_list = words(vector(&mut groups, true)?)?;
    groups.expect_empty("CustomClientHelloGroups")?;
    let original_shares = shares(before.required(51)?)?;
    let replacement_shares = shares(after.required(51)?)?;
    let actual_shares: Vec<_> = replacement_shares
        .iter()
        .copied()
        .filter(|(g, _)| !grease(*g))
        .collect();
    if original_shares != actual_shares {
        return Err(invalid());
    }
    let mut previous_group = None;
    for (group, bytes) in replacement_shares {
        if grease(group) && bytes != [0] {
            return Err(invalid());
        }
        let index = groups_list
            .iter()
            .position(|value| *value == group)
            .ok_or_else(invalid)?;
        if previous_group.is_some_and(|previous| previous >= index) {
            return Err(invalid());
        }
        previous_group = Some(index);
    }
    if let Some(ech) = after.extension(0xfe0d) {
        validate_grease_ech(ech)?;
    }
    Ok(())
}

fn shares(bytes: &[u8]) -> Result<Vec<(u16, &[u8])>, Error> {
    let mut outer = Reader::init(bytes);
    let mut reader = Reader::init(vector(&mut outer, true)?);
    outer.expect_empty("CustomClientHelloKeyShares")?;
    let mut shares = Vec::new();
    while reader.any_left() {
        let group = u16::read(&mut reader)?;
        if shares
            .iter()
            .any(|(existing, _)| *existing == group)
        {
            return Err(invalid());
        }
        let public = vector(&mut reader, true)?;
        if public.is_empty() {
            return Err(invalid());
        }
        shares.push((group, public));
    }
    Ok(shares)
}

fn validate_grease_ech(bytes: &[u8]) -> Result<(), Error> {
    let mut reader = Reader::init(bytes);
    if u8::read(&mut reader)? != 0 || u16::read(&mut reader)? != 1 || u16::read(&mut reader)? != 1 {
        return Err(invalid());
    }
    u8::read(&mut reader)?; // Fresh opaque config ID.
    if vector(&mut reader, true)?.len() != 32
        || !matches!(vector(&mut reader, true)?.len(), 144 | 176 | 208 | 240)
    {
        return Err(invalid());
    }
    reader.expect_empty("CustomClientHelloGreaseEch")?;
    Ok(())
}
