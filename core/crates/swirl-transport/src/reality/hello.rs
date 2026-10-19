//! Bounded handshake-message validation. These are handshake bytes (including
//! type/uint24 length), never TLS record headers or an independently re-encoded
//! approximation of the bytes that will enter the transcript.
use super::{ClientParameters, kx::HybridKeyExchange};
use std::collections::BTreeSet;

pub(super) const SESSION_ID: std::ops::Range<usize> = 39..71;
const MAX_HELLO: usize = 16 * 1024;
const HYBRID: u16 = 0x11ec;
const X25519: u16 = 0x001d;
const HELLO_RETRY_RANDOM: [u8; 32] = [
    0xcf, 0x21, 0xad, 0x74, 0xe5, 0x9a, 0x61, 0x11, 0xbe, 0x1d, 0x8c, 0x02, 0x1e, 0x65, 0xb8, 0x91,
    0xc2, 0xa2, 0x11, 0x16, 0x7a, 0xbb, 0x8c, 0x5e, 0x07, 0x9e, 0x09, 0xe2, 0xc8, 0xa8, 0x33, 0x9c,
];

pub(super) struct ClientOffer {
    pub ciphers: Vec<u16>,
    pub classical: bool,
}

struct Cursor<'a>(&'a [u8]);
impl<'a> Cursor<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], &'static str> {
        let value = self.0.get(..n).ok_or("RealityHelloLength")?;
        self.0 = &self.0[n..];
        Ok(value)
    }
    fn byte(&mut self) -> Result<u8, &'static str> {
        Ok(self.take(1)?[0])
    }
    fn word(&mut self) -> Result<u16, &'static str> {
        let bytes = self.take(2)?;
        Ok(u16::from_be_bytes([bytes[0], bytes[1]]))
    }
    fn vector8(&mut self) -> Result<&'a [u8], &'static str> {
        let n = self.byte()? as usize;
        self.take(n)
    }
    fn vector16(&mut self) -> Result<&'a [u8], &'static str> {
        let n = self.word()? as usize;
        self.take(n)
    }
    fn finish(self) -> Result<(), &'static str> {
        if self.0.is_empty() {
            Ok(())
        } else {
            Err("RealityHelloTrailingData")
        }
    }
}

fn handshake(bytes: &[u8], kind: u8) -> Result<Cursor<'_>, &'static str> {
    if bytes.len() > MAX_HELLO || bytes.len() < 4 {
        return Err("RealityHelloLength");
    }
    if bytes[0] != kind {
        return Err("RealityHelloType");
    }
    let length = u32::from_be_bytes([0, bytes[1], bytes[2], bytes[3]]) as usize;
    if length != bytes.len() - 4 {
        return Err("RealityHelloLength");
    }
    Ok(Cursor(&bytes[4..]))
}

fn words(bytes: &[u8]) -> Result<Vec<u16>, &'static str> {
    if bytes.is_empty() || !bytes.len().is_multiple_of(2) {
        return Err("RealityHelloVector");
    }
    Ok(bytes
        .as_chunks::<2>()
        .0
        .iter()
        .map(|v| u16::from_be_bytes(*v))
        .collect())
}

fn extensions<'a>(body: &mut Cursor<'a>) -> Result<Vec<(u16, &'a [u8])>, &'static str> {
    let mut list = Cursor(body.vector16()?);
    let mut seen = BTreeSet::new();
    let mut entries = Vec::new();
    while !list.0.is_empty() {
        let kind = list.word()?;
        if !seen.insert(kind) {
            return Err("RealityDuplicateExtension");
        }
        if entries.len() == 64 {
            return Err("RealityExtensionLimit");
        }
        entries.push((kind, list.vector16()?));
    }
    Ok(entries)
}

fn extension<'a>(entries: &[(u16, &'a [u8])], kind: u16) -> Result<&'a [u8], &'static str> {
    entries
        .iter()
        .find_map(|(tag, value)| (*tag == kind).then_some(*value))
        .ok_or("RealityRequiredExtension")
}

pub(super) fn client(
    bytes: &[u8],
    random: &[u8; 32],
    key: &HybridKeyExchange,
    parameters: &ClientParameters,
) -> Result<ClientOffer, &'static str> {
    let mut body = handshake(bytes, 1)?;
    if body.word()? != 0x0303 || body.take(32)? != random {
        return Err("RealityClientHelloBinding");
    }
    if body.vector8()? != [0; 32] {
        return Err("RealitySessionIdMustBeZero");
    }
    let ciphers = words(body.vector16()?)?;
    if !ciphers
        .iter()
        .any(|cipher| (0x1301..=0x1303).contains(cipher))
    {
        return Err("RealityTls13Required");
    }
    if body.vector8()? != [0] {
        return Err("RealityCompression");
    }
    let entries = extensions(&mut body)?;
    body.finish()?;
    // This first-flight foundation does not authenticate resumption binders,
    // 0-RTT, ECH inner/outer transcripts, or a second ClientHello after HRR.
    if entries
        .iter()
        .any(|(kind, _)| matches!(kind, 41 | 42 | 44 | 0xfd00 | 0xfe0d))
    {
        return Err("RealityHelloExtensionUnsupported");
    }
    let mut versions = Cursor(extension(&entries, 43)?);
    if !words(versions.vector8()?)?.contains(&0x0304) {
        return Err("RealityTls13Required");
    }
    versions.finish()?;
    let mut names = Cursor(extension(&entries, 0)?);
    let mut name = Cursor(names.vector16()?);
    names.finish()?;
    if name.byte()? != 0
        || !name
            .vector16()?
            .eq_ignore_ascii_case(parameters.server_name.as_bytes())
    {
        return Err("RealityServerNameBinding");
    }
    name.finish()?;
    let mut signatures = Cursor(extension(&entries, 13)?);
    if !words(signatures.vector16()?)?.contains(&0x0807) {
        return Err("RealityEd25519Required");
    }
    signatures.finish()?;
    let mut groups = Cursor(extension(&entries, 10)?);
    let groups_list = words(groups.vector16()?)?;
    groups.finish()?;
    if groups_list.iter().collect::<BTreeSet<_>>().len() != groups_list.len() {
        return Err("RealityDuplicateSupportedGroup");
    }
    if !groups_list.contains(&HYBRID) {
        return Err("RealityHybridRequired");
    }
    let mut shares = Cursor(extension(&entries, 51)?);
    let mut share_list = Cursor(shares.vector16()?);
    shares.finish()?;
    let mut seen = BTreeSet::new();
    let mut hybrid = false;
    let mut classical = false;
    let mut last_group_index = None;
    while !share_list.0.is_empty() {
        let group = share_list.word()?;
        let public = share_list.vector16()?;
        if public.is_empty() {
            return Err("RealityKeyShareLength");
        }
        if !seen.insert(group) {
            return Err("RealityDuplicateKeyShare");
        }
        let index = groups_list
            .iter()
            .position(|offered| *offered == group)
            .ok_or("RealityKeyShareNotOffered")?;
        if last_group_index.is_some_and(|previous| previous >= index) {
            return Err("RealityKeyShareOrder");
        }
        last_group_index = Some(index);
        match group {
            HYBRID => {
                if classical || public != key.public_share() {
                    return Err("RealityKeyShareBinding");
                }
                hybrid = true;
            }
            X25519 => {
                if !hybrid || !groups_list.contains(&X25519) || public != key.classical_share() {
                    return Err("RealityKeyShareBinding");
                }
                classical = true;
            }
            // GREASE is an opaque offer, never an executable negotiated group.
            grease if grease & 0x0f0f == 0x0a0a && (grease >> 8) == (grease & 0xff) => {}
            _ => return Err("RealityUnownedKeyShare"),
        }
    }
    if !hybrid {
        return Err("RealityHybridRequired");
    }
    Ok(ClientOffer { ciphers, classical })
}

pub(super) struct ServerSelection<'a> {
    pub cipher: u16,
    pub group: tokio_rustls::rustls::NamedGroup,
    pub share: &'a [u8],
}

pub(super) fn server<'a>(
    bytes: &'a [u8],
    client_hello: &[u8],
    offer: &ClientOffer,
) -> Result<ServerSelection<'a>, &'static str> {
    let mut body = handshake(bytes, 2)?;
    if body.word()? != 0x0303 {
        return Err("RealityTls13Required");
    }
    if body.take(32)? == HELLO_RETRY_RANDOM {
        return Err("RealityHelloRetryUnsupported");
    }
    if body.vector8()? != &client_hello[SESSION_ID] {
        return Err("RealitySessionIdEcho");
    }
    let cipher = body.word()?;
    if !(0x1301..=0x1303).contains(&cipher) || !offer.ciphers.contains(&cipher) {
        return Err("RealityCipherSelection");
    }
    if body.byte()? != 0 {
        return Err("RealityCompression");
    }
    let entries = extensions(&mut body)?;
    body.finish()?;
    if entries.iter().any(|(kind, _)| !matches!(kind, 43 | 51)) {
        return Err("RealityServerExtensionUnsupported");
    }
    if extension(&entries, 43)? != [3, 4] {
        return Err("RealityTls13Required");
    }
    let mut share = Cursor(extension(&entries, 51)?);
    let group = match share.word()? {
        HYBRID => tokio_rustls::rustls::NamedGroup::X25519MLKEM768,
        X25519 if offer.classical => tokio_rustls::rustls::NamedGroup::X25519,
        _ => return Err("RealityKeyShareGroup"),
    };
    let public = share.vector16()?;
    share.finish()?;
    Ok(ServerSelection {
        cipher,
        group,
        share: public,
    })
}
