//! Versioned REALITY ClientHello shapes. Cryptography and the TLS transcript
//! remain owned by rustls; this hook executes before either hashing or sending.
//!
//! Chrome 133 is the Chrome_Auto profile in the project's locked uTLS oracle:
//! https://github.com/refraction-networking/utls/blob/aa6edf4b11af82e110eea845bb2983d30138d651/u_parrots.go
//! These wire constants describe the protocol, not a copied TLS implementation.
//! This is a TLS-1.3-only REALITY adapter, not a general browser TLS client.
use ring::{
    agreement,
    rand::{SecureRandom, SystemRandom},
};
use std::collections::BTreeMap;
use tokio_rustls::rustls::{self, client::ClientHelloCustomizer};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Fingerprint {
    Rustls,
    Chrome133,
}

impl Fingerprint {
    pub(super) fn parse(value: &str) -> Result<Self, &'static str> {
        match value {
            "rustls" => Ok(Self::Rustls),
            "chrome" | "chrome_133" => Ok(Self::Chrome133),
            _ => Err("RealityFingerprintUnsupported"),
        }
    }
}

pub(super) const CHROME_SIGNATURES: &[u16] = &[
    0x0403, 0x0804, 0x0401, 0x0503, 0x0805, 0x0501, 0x0806, 0x0601,
];
const CIPHERS: &[u16] = &[
    0x1301, 0x1302, 0x1303, 0xc02b, 0xc02f, 0xc02c, 0xc030, 0xcca9, 0xcca8, 0xc013, 0xc014, 0x009c,
    0x009d, 0x002f, 0x0035,
];
const EXTENSIONS: &[u16] = &[
    0, 23, 65281, 10, 11, 35, 16, 5, 13, 18, 51, 45, 43, 27, 17613, 0xfe0d,
];

/// Randomized once per connection, then reused by the offline preview and
/// authenticated constructor. It contains only public first-flight bytes.
#[derive(Debug)]
pub(super) struct Chrome133 {
    grease: [u16; 5], // cipher, group, version, first extension, last extension
    order: Vec<u16>,
    ech: Vec<u8>,
}

fn random_index(upper: usize) -> Result<usize, &'static str> {
    // Rejection sampling avoids bias in the extension permutation. A broken
    // entropy source fails closed instead of making construction unbounded.
    let limit = 256 - 256 % upper;
    for _ in 0..64 {
        let mut byte = [0];
        SystemRandom::new()
            .fill(&mut byte)
            .map_err(|_| "RealityRandom")?;
        if usize::from(byte[0]) < limit {
            return Ok(usize::from(byte[0]) % upper);
        }
    }
    Err("RealityRandom")
}

impl Chrome133 {
    pub(super) fn generate() -> Result<Self, &'static str> {
        let rng = SystemRandom::new();
        let mut seed = [0; 6];
        rng.fill(&mut seed).map_err(|_| "RealityRandom")?;
        let mut grease = [0; 5];
        for (value, random) in grease.iter_mut().zip(seed) {
            let byte = (random & 0xf0) | 0x0a;
            *value = u16::from_be_bytes([byte, byte]);
        }
        if grease[3] == grease[4] {
            grease[4] ^= 0x1010;
        }
        let mut order = EXTENSIONS.to_vec();
        for i in (1..order.len()).rev() {
            let j = random_index(i + 1)?;
            order.swap(i, j);
        }
        // GREASE ECH advertises no real ECH configuration. Generate an actual
        // X25519 public encoding, matching the oracle's HPKE encapsulation shape.
        // There is no reusable secret or ECH inner transcript.
        let ephemeral = agreement::EphemeralPrivateKey::generate(&agreement::X25519, &rng)
            .map_err(|_| "RealityRandom")?;
        let encapsulated = ephemeral
            .compute_public_key()
            .map_err(|_| "RealityRandom")?;
        let mut payload = vec![0; 144 + 32 * random_index(4)?];
        rng.fill(&mut payload).map_err(|_| "RealityRandom")?;
        let mut ech = vec![0, 0, 1, 0, 1, seed[5]];
        vector16(&mut ech, encapsulated.as_ref())?;
        vector16(&mut ech, &payload)?;
        Ok(Self { grease, order, ech })
    }

    fn rewrite(&self, input: &[u8]) -> Result<Vec<u8>, &'static str> {
        let extensions = input_extensions(input)?;
        let required = |kind| {
            extensions
                .get(&kind)
                .copied()
                .ok_or("RealityBrowserHelloInput")
        };
        if required(16)? != b"\x00\x0c\x02h2\x08http/1.1" {
            return Err("RealityFingerprintAlpnUnsupported");
        }
        let mut wire_extensions = Vec::new();
        extension(&mut wire_extensions, self.grease[3], &[])?;
        for kind in &self.order {
            let value = match *kind {
                0 | 16 => required(*kind)?.to_vec(),
                23 | 35 | 18 => Vec::new(),
                65281 => vec![0],
                10 => words16(&[self.grease[1], 0x11ec, 29, 23, 24])?,
                11 => vec![1, 0],
                5 => vec![1, 0, 0, 0, 0],
                13 => words16(CHROME_SIGNATURES)?,
                51 => {
                    let shares = required(51)?;
                    if shares.len() < 2
                        || usize::from(u16::from_be_bytes([shares[0], shares[1]]))
                            != shares.len() - 2
                    {
                        return Err("RealityBrowserHelloInput");
                    }
                    let mut combined = self.grease[1].to_be_bytes().to_vec();
                    combined.extend_from_slice(&[0, 1, 0]);
                    combined.extend_from_slice(&shares[2..]);
                    let mut result = Vec::new();
                    vector16(&mut result, &combined)?;
                    result
                }
                45 => vec![1, 1],
                43 => {
                    let mut value = vec![6];
                    value.extend_from_slice(&self.grease[2].to_be_bytes());
                    value.extend_from_slice(&[3, 4, 3, 3]);
                    value
                }
                27 => vec![2, 0, 2], // RFC 8879: Brotli, implemented by rustls.
                17613 => b"\x00\x03\x02h2".to_vec(),
                0xfe0d => self.ech.clone(),
                _ => return Err("RealityBrowserHelloExtension"),
            };
            extension(&mut wire_extensions, *kind, &value)?;
        }
        extension(&mut wire_extensions, self.grease[4], &[0])?;
        let mut result = input.get(..71).ok_or("RealityBrowserHelloInput")?.to_vec();
        let mut ciphers = vec![self.grease[0]];
        ciphers.extend_from_slice(CIPHERS);
        result.extend_from_slice(&words16(&ciphers)?);
        result.extend_from_slice(&[1, 0]);
        vector16(&mut result, &wire_extensions)?;
        let length = u32::try_from(result.len() - 4).map_err(|_| "RealityBrowserHelloLength")?;
        result[1..4].copy_from_slice(&length.to_be_bytes()[1..]);
        Ok(result)
    }
}

impl ClientHelloCustomizer for Chrome133 {
    fn customize(&self, client_hello: &[u8]) -> Result<Vec<u8>, rustls::Error> {
        self.rewrite(client_hello)
            .map_err(|reason| rustls::Error::General(reason.into()))
    }
}

fn vector16(output: &mut Vec<u8>, value: &[u8]) -> Result<(), &'static str> {
    let length = u16::try_from(value.len()).map_err(|_| "RealityBrowserHelloLength")?;
    output.extend_from_slice(&length.to_be_bytes());
    output.extend_from_slice(value);
    Ok(())
}

fn words16(words: &[u16]) -> Result<Vec<u8>, &'static str> {
    let mut value = Vec::with_capacity(words.len() * 2 + 2);
    let bytes: Vec<u8> = words.iter().flat_map(|word| word.to_be_bytes()).collect();
    vector16(&mut value, &bytes)?;
    Ok(value)
}

fn extension(output: &mut Vec<u8>, kind: u16, value: &[u8]) -> Result<(), &'static str> {
    output.extend_from_slice(&kind.to_be_bytes());
    vector16(output, value)
}

fn input_extensions(input: &[u8]) -> Result<BTreeMap<u16, &[u8]>, &'static str> {
    let fail = "RealityBrowserHelloInput";
    if input.len() < 71
        || input[0] != 1
        || input[38] != 32
        || u32::from_be_bytes([0, input[1], input[2], input[3]]) as usize != input.len() - 4
    {
        return Err(fail);
    }
    fn take16<'a>(rest: &mut &'a [u8]) -> Result<&'a [u8], &'static str> {
        let size = rest.get(..2).ok_or("RealityBrowserHelloInput")?;
        let len = usize::from(u16::from_be_bytes([size[0], size[1]]));
        let value = rest.get(2..2 + len).ok_or("RealityBrowserHelloInput")?;
        *rest = &rest[2 + len..];
        Ok(value)
    }
    let mut rest = &input[71..];
    take16(&mut rest)?;
    if rest.get(..2) != Some(&[1, 0]) {
        return Err(fail);
    }
    rest = &rest[2..];
    let mut list = take16(&mut rest)?;
    if !rest.is_empty() {
        return Err(fail);
    }
    let mut result = BTreeMap::new();
    while !list.is_empty() {
        let bytes = list.get(..2).ok_or(fail)?;
        let kind = u16::from_be_bytes([bytes[0], bytes[1]]);
        list = &list[2..];
        let value = take16(&mut list)?;
        if result.insert(kind, value).is_some() {
            return Err(fail);
        }
    }
    Ok(result)
}

pub(super) fn valid_grease_ech(value: &[u8]) -> bool {
    value.len() >= 42
        && value[..5] == [0, 0, 1, 0, 1]
        && value[6..8] == [0, 32]
        && matches!(
            u16::from_be_bytes([value[40], value[41]]),
            144 | 176 | 208 | 240
        )
        && usize::from(u16::from_be_bytes([value[40], value[41]])) == value.len() - 42
}
