//! Owned RFC 10024 key material. Cryptographic primitives come from maintained
//! libraries; Swirl owns the TLS share layout, lifecycle and rejection policy.
use ml_kem::{Ciphertext, Decapsulate, DecapsulationKey, KeyExport, MlKem768};
use ring::rand::{SecureRandom, SystemRandom};
use tokio_rustls::rustls::{
    Error, NamedGroup, PeerMisbehaved, ProtocolVersion,
    crypto::{ActiveKeyExchange, CompletedKeyExchange, SharedSecret, SupportedKxGroup},
    ffdhe_groups::FfdheGroup,
};
use x25519_dalek::{PublicKey, StaticSecret};
use zeroize::Zeroizing;

pub(crate) const MLKEM_PUBLIC_LEN: usize = 1184;
pub(crate) const MLKEM_CIPHERTEXT_LEN: usize = 1088;
pub(crate) const CLIENT_SHARE_LEN: usize = MLKEM_PUBLIC_LEN + 32;
pub(crate) const SERVER_SHARE_LEN: usize = MLKEM_CIPHERTEXT_LEN + 32;

/// An opt-in key-exchange provider, not a REALITY connection or fingerprint.
/// Installing this client-only group does not customize rustls's ClientHello transcript.
pub const X25519_MLKEM768: &dyn SupportedKxGroup = &HybridGroup;

#[derive(Debug)]
struct HybridGroup;

impl SupportedKxGroup for HybridGroup {
    fn start(&self) -> Result<Box<dyn ActiveKeyExchange>, Error> {
        HybridKeyExchange::generate()
            .map(|key| Box::new(key) as Box<dyn ActiveKeyExchange>)
            .map_err(|_| Error::FailedToGetRandomBytes)
    }

    fn name(&self) -> NamedGroup {
        NamedGroup::X25519MLKEM768
    }

    fn start_and_complete(&self, _peer: &[u8]) -> Result<CompletedKeyExchange, Error> {
        // The default trait implementation is for symmetric DH, not KEM server
        // encapsulation. Never masquerade a client's key share as a server's.
        Err(Error::General(
            "Swirl REALITY key provider is client-only".into(),
        ))
    }

    fn usable_for_version(&self, version: ProtocolVersion) -> bool {
        version == ProtocolVersion::TLSv1_3
    }

    fn ffdhe_group(&self) -> Option<FfdheGroup<'static>> {
        None
    }
}

// Deliberately no Clone or Debug: one protocol run owns both ephemeral secrets.
pub(crate) struct HybridKeyExchange {
    x25519: StaticSecret,
    mlkem: DecapsulationKey<MlKem768>,
    public: [u8; CLIENT_SHARE_LEN],
}

impl HybridKeyExchange {
    pub(crate) fn generate() -> Result<Self, &'static str> {
        let mut x25519_seed = Zeroizing::new([0; 32]);
        let mut mlkem_seed = Zeroizing::new([0; 64]);
        let random = SystemRandom::new();
        random
            .fill(x25519_seed.as_mut())
            .and_then(|()| random.fill(mlkem_seed.as_mut()))
            .map_err(|_| "RealityRandom")?;
        Ok(Self::from_seeds(&x25519_seed, &mlkem_seed))
    }

    // Only fresh OS-random seeds reach this function in production. Keeping the
    // deterministic constructor private permits independent known-answer tests.
    pub(super) fn from_seeds(x25519_seed: &[u8; 32], mlkem_seed: &[u8; 64]) -> Self {
        let x25519 = StaticSecret::from(*x25519_seed);
        let mlkem = DecapsulationKey::<MlKem768>::from_seed((*mlkem_seed).into());
        let mut public = [0; CLIENT_SHARE_LEN];
        public[..MLKEM_PUBLIC_LEN].copy_from_slice(&mlkem.encapsulation_key().to_bytes());
        public[MLKEM_PUBLIC_LEN..].copy_from_slice(PublicKey::from(&x25519).as_bytes());
        Self {
            x25519,
            mlkem,
            public,
        }
    }

    pub(crate) fn public_share(&self) -> &[u8] {
        &self.public
    }

    pub(crate) fn classical_share(&self) -> &[u8] {
        &self.public[MLKEM_PUBLIC_LEN..]
    }

    pub(crate) fn classical_secret(
        &self,
        peer: &[u8],
    ) -> Result<Zeroizing<[u8; 32]>, &'static str> {
        let peer: [u8; 32] = peer.try_into().map_err(|_| "RealityKeyShareLength")?;
        let secret = self.x25519.diffie_hellman(&PublicKey::from(peer));
        if !secret.was_contributory() {
            return Err("RealityNonContributoryKey");
        }
        Ok(Zeroizing::new(secret.to_bytes()))
    }

    pub(crate) fn finish(
        self,
        group: NamedGroup,
        peer: &[u8],
    ) -> Result<SharedSecret, &'static str> {
        if group == NamedGroup::X25519 {
            return Ok(SharedSecret::from(self.classical_secret(peer)?.as_slice()));
        }
        if group != NamedGroup::X25519MLKEM768 {
            return Err("RealityKeyShareGroup");
        }
        if peer.len() != SERVER_SHARE_LEN {
            return Err("RealityKeyShareLength");
        }
        let x25519 = self.classical_secret(&peer[MLKEM_CIPHERTEXT_LEN..])?;
        let ciphertext = Ciphertext::<MlKem768>::try_from(&peer[..MLKEM_CIPHERTEXT_LEN])
            .map_err(|_| "RealityKeyShareLength")?;
        // FIPS 203 implicit rejection returns a pseudorandom secret for a
        // modified, correctly sized ciphertext. Only TLS Finished authenticates
        // that result; decapsulation success is never handshake success.
        let mlkem = Zeroizing::new(self.mlkem.decapsulate(&ciphertext));
        let mut combined = Zeroizing::new([0; 64]);
        combined[..32].copy_from_slice(&mlkem[..]);
        combined[32..].copy_from_slice(x25519.as_slice());
        Ok(SharedSecret::from(combined.as_slice()))
    }
}

impl ActiveKeyExchange for HybridKeyExchange {
    fn complete(self: Box<Self>, peer: &[u8]) -> Result<SharedSecret, Error> {
        self.finish(NamedGroup::X25519MLKEM768, peer)
            .map_err(|_| PeerMisbehaved::InvalidKeyShare.into())
    }

    fn hybrid_component(&self) -> Option<(NamedGroup, &[u8])> {
        Some((NamedGroup::X25519, self.classical_share()))
    }

    fn complete_hybrid_component(self: Box<Self>, peer: &[u8]) -> Result<SharedSecret, Error> {
        self.finish(NamedGroup::X25519, peer)
            .map_err(|_| PeerMisbehaved::InvalidKeyShare.into())
    }

    fn pub_key(&self) -> &[u8] {
        self.public_share()
    }

    fn group(&self) -> NamedGroup {
        NamedGroup::X25519MLKEM768
    }

    fn ffdhe_group(&self) -> Option<FfdheGroup<'static>> {
        None
    }
}
