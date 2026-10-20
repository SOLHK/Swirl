//! Typed REALITY parameters. Native rustls and the fixed Chrome 133 profile
//! retain their source names; unsupported profiles never downgrade.
use base64::{
    Engine,
    engine::general_purpose::{URL_SAFE, URL_SAFE_NO_PAD},
};
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Reality {
    pub server_name: String,
    pub public_key: String,
    pub short_id: String,
    pub fingerprint: String,
    #[serde(default)]
    pub alpn: Vec<String>,
}

impl Reality {
    pub fn validate(&self) -> Result<(), &'static str> {
        if !crate::valid_host(&self.server_name)
            || self.server_name.ends_with('.')
            || self.server_name.parse::<std::net::IpAddr>().is_ok()
        {
            return Err("RealityServerName");
        }
        match self.fingerprint.as_str() {
            "rustls" => {}
            "chrome" | "chrome_133" => {
                // This browser profile has a fixed ALPN offer. Empty selects
                // that offer in the transport without changing the source IR.
                if !self.alpn.is_empty() && self.alpn != ["h2", "http/1.1"] {
                    return Err("RealityFingerprintAlpnUnsupported");
                }
            }
            _ => return Err("RealityFingerprintUnsupported"),
        }
        let mut seen = std::collections::HashSet::new();
        if self.alpn.len() > 16
            || self.alpn.iter().map(String::len).sum::<usize>() > 1024
            || self.alpn.iter().any(|value| {
                value.is_empty()
                    || value.len() > 255
                    || !value.is_ascii()
                    || value.bytes().any(|b| b.is_ascii_control())
                    || !seen.insert(value)
            })
        {
            return Err("RealityAlpn");
        }
        self.key_material()?;
        Ok(())
    }

    pub fn key_material(&self) -> Result<([u8; 32], Vec<u8>), &'static str> {
        if self.public_key.len() > 44 {
            return Err("RealityPublicKey");
        }
        let decoded = URL_SAFE_NO_PAD
            .decode(&self.public_key)
            .or_else(|_| URL_SAFE.decode(&self.public_key))
            .map_err(|_| "RealityPublicKey")?;
        let key: [u8; 32] = decoded.try_into().map_err(|_| "RealityPublicKey")?;
        if key.iter().all(|byte| *byte == 0) {
            return Err("RealityPublicKey");
        }
        if self.short_id.len() > 16
            || !self.short_id.len().is_multiple_of(2)
            || !self.short_id.bytes().all(|byte| byte.is_ascii_hexdigit())
        {
            return Err("RealityShortId");
        }
        let short_id = self
            .short_id
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| {
                u8::from_str_radix(std::str::from_utf8(pair).expect("ASCII hex"), 16)
                    .expect("validated hex")
            })
            .collect();
        Ok((key, short_id))
    }
}
