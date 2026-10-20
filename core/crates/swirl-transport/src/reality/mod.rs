//! REALITY authentication and a bounded native TLS 1.3 client.
//!
//! Swirl owns fresh hybrid key material, authenticated ClientHello finalization
//! and the first ServerHello transition. The exact finalized handshake bytes
//! enter the transcript. Neither a key exchange nor certificate authentication
//! establishes a data channel: the opt-in [`TlsClient`] also verifies the actual
//! CertificateVerify and Finished. Its two offline constructions bind the final
//! authenticated ClientHello to rustls's own transcript, without socket rewriting.
//! The async [`Stream`] owns the transport and preserves exact record boundaries.
//! This is a native rustls profile; a requested browser fingerprint must still be
//! rejected by the caller instead of being silently changed to this profile.
mod backend;
mod certificate;
mod client;
mod hello;
mod kx;
mod stream;

pub use certificate::ServerAuthenticator;
pub use client::TlsClient;
pub use kx::X25519_MLKEM768;
pub use stream::{Stream, connect};

use ring::{
    aead, digest, hkdf,
    rand::{SecureRandom, SystemRandom},
};
use tokio_rustls::rustls::{crypto::SharedSecret, pki_types::ServerName};
use zeroize::Zeroizing;

/// Explicit binary authentication inputs. This is not a subscription mapper;
/// callers must preserve/reject all other protocol and fingerprint parameters.
pub struct ClientParameters {
    server_name: String,
    public_key: [u8; 32],
    short_id: [u8; 8],
    version: [u8; 3],
}

impl ClientParameters {
    pub fn new(
        server_name: &str,
        public_key: [u8; 32],
        short_id: &[u8],
        version: [u8; 3],
    ) -> Result<Self, &'static str> {
        // pki-types accepts an absolute DNS name with a terminal dot, but
        // RFC 6066 forbids that dot in the SNI HostName sent on the wire.
        if server_name.ends_with('.')
            || !matches!(
                ServerName::try_from(server_name),
                Ok(ServerName::DnsName(_))
            )
        {
            return Err("RealityServerName");
        }
        if short_id.len() > 8 {
            return Err("RealityShortIdLength");
        }
        let mut padded_id = [0; 8];
        padded_id[..short_id.len()].copy_from_slice(short_id);
        Ok(Self {
            server_name: server_name.into(),
            public_key,
            short_id: padded_id,
            version,
        })
    }
}

/// A single first-flight attempt. No cloning, exported private seed, reusable
/// nonce or second authentication operation is available through this API.
pub struct ClientKeys {
    key_exchange: kx::HybridKeyExchange,
    random: [u8; 32],
}

impl ClientKeys {
    pub fn generate() -> Result<Self, &'static str> {
        let mut random = [0; 32];
        SystemRandom::new()
            .fill(&mut random)
            .map_err(|_| "RealityRandom")?;
        Ok(Self {
            key_exchange: kx::HybridKeyExchange::generate()?,
            random,
        })
    }

    pub fn client_random(&self) -> &[u8; 32] {
        &self.random
    }

    /// RFC 10024: 1184-byte ML-KEM public key followed by 32-byte X25519.
    pub fn hybrid_public_key(&self) -> &[u8] {
        self.key_exchange.public_share()
    }

    /// Optional second share, backed by the SAME ephemeral X25519 owner.
    pub fn x25519_public_key(&self) -> &[u8] {
        self.key_exchange.classical_share()
    }

    /// Authenticate a finalized first ClientHello with a 32-byte zero SessionID.
    /// Validates all lengths and bindings BEFORE modifying the owned byte buffer.
    /// This consumes the keys even on failure; retries need fresh material.
    ///
    /// ```compile_fail
    /// use swirl_transport::reality::{ClientKeys, ClientParameters};
    /// let keys = ClientKeys::generate().unwrap();
    /// let p = ClientParameters::new("reality.test", [9; 32], &[], [26, 10, 19]).unwrap();
    /// let _first = keys.authenticate(Vec::new(), &p, 0);
    /// let _reused_nonce = keys.authenticate(Vec::new(), &p, 0);
    /// ```
    pub fn authenticate(
        self,
        mut client_hello: Vec<u8>,
        parameters: &ClientParameters,
        unix_time: u32,
    ) -> Result<AuthenticatedClientHello, &'static str> {
        let offer = hello::client(&client_hello, &self.random, &self.key_exchange, parameters)?;
        let shared = self.key_exchange.classical_secret(&parameters.public_key)?;
        let authentication_key = derive_authentication_key(&shared, &self.random)?;
        let session_id = seal_session_id(
            &authentication_key,
            &self.random,
            parameters,
            unix_time,
            &client_hello,
        )?;
        client_hello[hello::SESSION_ID].copy_from_slice(&session_id);
        Ok(AuthenticatedClientHello {
            bytes: client_hello,
            key_exchange: self.key_exchange,
            authentication_key,
            offer,
        })
    }
}

fn derive_authentication_key(
    shared: &[u8; 32],
    random: &[u8; 32],
) -> Result<Zeroizing<[u8; 32]>, &'static str> {
    let extracted = hkdf::Salt::new(hkdf::HKDF_SHA256, &random[..20]).extract(shared);
    let mut key = Zeroizing::new([0; 32]);
    extracted
        .expand(&[b"REALITY"], hkdf::HKDF_SHA256)
        .map_err(|_| "RealityKeyDerivation")?
        .fill(key.as_mut())
        .map_err(|_| "RealityKeyDerivation")?;
    Ok(key)
}

fn seal_session_id(
    key: &[u8; 32],
    random: &[u8; 32],
    parameters: &ClientParameters,
    unix_time: u32,
    aad: &[u8],
) -> Result<[u8; 32], &'static str> {
    let mut plaintext = Zeroizing::new([0; 16]);
    plaintext[..3].copy_from_slice(&parameters.version);
    plaintext[4..8].copy_from_slice(&unix_time.to_be_bytes());
    plaintext[8..].copy_from_slice(&parameters.short_id);
    let cipher =
        aead::UnboundKey::new(&aead::AES_256_GCM, key).map_err(|_| "RealityAuthentication")?;
    let nonce: [u8; 12] = random[20..]
        .try_into()
        .map_err(|_| "RealityAuthentication")?;
    let tag = aead::LessSafeKey::new(cipher)
        .seal_in_place_separate_tag(
            aead::Nonce::assume_unique_for_key(nonce),
            aead::Aad::from(aad),
            plaintext.as_mut(),
        )
        .map_err(|_| "RealityAuthentication")?;
    let mut sealed = [0; 32];
    sealed[..16].copy_from_slice(plaintext.as_slice());
    sealed[16..].copy_from_slice(tag.as_ref());
    Ok(sealed)
}

pub struct AuthenticatedClientHello {
    bytes: Vec<u8>,
    key_exchange: kx::HybridKeyExchange,
    authentication_key: Zeroizing<[u8; 32]>,
    offer: hello::ClientOffer,
}

impl AuthenticatedClientHello {
    /// The immutable bytes to send and hash, including the authenticated ID.
    pub fn handshake_bytes(&self) -> &[u8] {
        &self.bytes
    }

    /// Validate the actual ServerHello, consume the sole key owner and compute
    /// the first transcript checkpoint. This is NOT a completed TLS handshake.
    /// HRR, TLS 1.2, PSK and unoffered groups/ciphers explicitly fail closed.
    pub fn accept_server_hello(
        self,
        server_hello: &[u8],
    ) -> Result<HandshakeSecrets, &'static str> {
        let selection = hello::server(server_hello, &self.bytes, &self.offer)?;
        let shared_secret = self.key_exchange.finish(selection.group, selection.share)?;
        let algorithm = if selection.cipher == 0x1302 {
            &digest::SHA384
        } else {
            &digest::SHA256
        };
        let mut transcript = digest::Context::new(algorithm);
        transcript.update(&self.bytes);
        transcript.update(server_hello);
        Ok(HandshakeSecrets {
            shared_secret,
            transcript,
            server_authenticator: ServerAuthenticator::new(self.authentication_key),
        })
    }
}

/// Secret material/checkpoint for a future TLS backend. No application stream,
/// authentication-success flag or socket is exposed by this foundation.
pub struct HandshakeSecrets {
    shared_secret: SharedSecret,
    transcript: digest::Context,
    server_authenticator: ServerAuthenticator,
}

impl HandshakeSecrets {
    pub fn shared_secret(&self) -> &[u8] {
        self.shared_secret.secret_bytes()
    }

    pub fn transcript_hash(&self) -> digest::Digest {
        self.transcript.clone().finish()
    }

    pub fn server_authenticator(&self) -> &ServerAuthenticator {
        &self.server_authenticator
    }
}

#[cfg(test)]
mod tests;
