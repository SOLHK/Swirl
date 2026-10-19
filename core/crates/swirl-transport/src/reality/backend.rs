//! A bounded, native-rustls first-flight adapter; never a browser fingerprint.
//!
//! rustls 0.23.46 constructs and buffers its ClientHello inside `new()`. Its
//! public API has no SessionID setter before that transcript input. Two entirely
//! offline constructors let us finalize REALITY authentication first: a preview
//! advertises public bytes only, then the final constructor receives the same
//! random/extension-order bytes, authenticated SessionID and sole live key owner.
//! Nothing may leave this module until both complete first flights agree.
//!
//! The private scoped provider is deliberately not a general-purpose RNG. Its
//! pinned constructor contract is SID(32), extension order(2), random(32), then
//! one key start. Shape, order, reentry or additional calls fail closed. The
//! caller must validate ServerHello (including echo and HRR) before giving it to
//! rustls; this module does not establish an authenticated application channel.

use super::{AuthenticatedClientHello, ClientKeys, ClientParameters, ServerAuthenticator, hello};
use ring::rand::{SecureRandom as _, SystemRandom};
use std::{cell::RefCell, collections::BTreeSet, marker::PhantomData, rc::Rc, sync::Arc};
use tokio_rustls::rustls::{
    self, ClientConfig, ClientConnection, Error, NamedGroup, ProtocolVersion,
    client::{
        Resumption,
        danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier},
    },
    crypto::{
        ActiveKeyExchange, CompletedKeyExchange, GetRandomFailed, SharedSecret, SupportedKxGroup,
    },
    pki_types::{CertificateDer, ServerName, UnixTime},
};

const MAX_FIRST_FLIGHT: usize = 16 * 1024 + 5;
const BUFFER_LIMIT: usize = 64 * 1024;

pub(super) struct Prepared {
    pub(super) connection: ClientConnection,
    pub(super) first_flight: Vec<u8>,
    pub(super) client_hello: Vec<u8>,
    pub(super) offer: hello::ClientOffer,
}

pub(super) fn prepare(
    parameters: &ClientParameters,
    unix_time: u32,
    alpn: &[Vec<u8>],
) -> Result<Prepared, &'static str> {
    validate_alpn(alpn)?;
    let keys = ClientKeys::generate()?;
    let random = *keys.client_random();
    let mut preview_id = [0; 32];
    let mut order = [0; 2];
    SystemRandom::new()
        .fill(&mut preview_id)
        .and_then(|()| SystemRandom::new().fill(&mut order))
        .map_err(|_| "RealityRandom")?;

    // Public bytes may be copied. The actual private keys stay in `keys` until
    // authenticate consumes them; the preview cannot complete a key exchange.
    let public = PreviewKey(keys.hybrid_public_key().to_vec());
    let (preview, mut expected_records) = construct(
        configuration(Arc::new(DenyPreviewCertificate), alpn)?,
        parameters,
        Construction::new(preview_id, order, random, Box::new(public)),
    )?;
    drop(preview);
    let mut candidate = first_handshake(&expected_records)?.to_vec();
    candidate
        .get_mut(hello::SESSION_ID)
        .ok_or("RealityBackendFirstFlight")?
        .fill(0);

    let AuthenticatedClientHello {
        bytes,
        key_exchange,
        authentication_key,
        offer,
    } = keys.authenticate(candidate, parameters, unix_time)?;
    let session_id: [u8; 32] = bytes
        .get(hello::SESSION_ID)
        .ok_or("RealityBackendFirstFlight")?
        .try_into()
        .map_err(|_| "RealityBackendFirstFlight")?;
    expected_records
        .get_mut(5 + hello::SESSION_ID.start..5 + hello::SESSION_ID.end)
        .ok_or("RealityBackendFirstFlight")?
        .copy_from_slice(&session_id);

    // No shared owner, seed replay or leaked per-connection provider is needed.
    // Only the final rustls connection takes the real key, by value, once.
    let (connection, first_flight) = construct(
        configuration(Arc::new(ServerAuthenticator::new(authentication_key)), alpn)?,
        parameters,
        Construction::new(session_id, order, random, Box::new(key_exchange)),
    )?;
    if first_handshake(&first_flight)? != bytes || first_flight != expected_records {
        return Err("RealityBackendClientHelloMismatch");
    }
    Ok(Prepared {
        connection,
        first_flight,
        client_hello: bytes,
        offer,
    })
}

fn validate_alpn(alpn: &[Vec<u8>]) -> Result<(), &'static str> {
    if alpn.len() > 16 {
        return Err("RealityAlpn");
    }
    let mut total = 0usize;
    let mut seen = BTreeSet::new();
    for protocol in alpn {
        if protocol.is_empty() || protocol.len() > 255 || !seen.insert(protocol.as_slice()) {
            return Err("RealityAlpn");
        }
        total += protocol.len(); // At most 16 * 255, before the stricter total bound.
        if total > 1024 {
            return Err("RealityAlpn");
        }
    }
    Ok(())
}

fn configuration(
    verifier: Arc<dyn ServerCertVerifier>,
    alpn: &[Vec<u8>],
) -> Result<Arc<ClientConfig>, &'static str> {
    use rustls::crypto::ring::cipher_suite::{
        TLS13_AES_128_GCM_SHA256, TLS13_AES_256_GCM_SHA384, TLS13_CHACHA20_POLY1305_SHA256,
    };
    let mut provider = rustls::crypto::ring::default_provider();
    provider.cipher_suites = vec![
        TLS13_AES_256_GCM_SHA384,
        TLS13_AES_128_GCM_SHA256,
        TLS13_CHACHA20_POLY1305_SHA256,
    ];
    provider.secure_random = &ScopedRandom;
    provider.kx_groups = vec![&ScopedHybridGroup, &AdvertiseClassicalOnly];
    let mut config = ClientConfig::builder_with_provider(Arc::new(provider))
        .with_protocol_versions(&[&rustls::version::TLS13])
        .map_err(|_| "RealityBackendConfig")?
        .dangerous()
        .with_custom_certificate_verifier(verifier)
        .with_no_client_auth();
    config.alpn_protocols = alpn.to_vec();
    config.enable_sni = true;
    config.resumption = Resumption::disabled();
    config.enable_early_data = false;
    config.cert_decompressors.clear();
    config.cert_compressors.clear();
    config.send_ticket_request = None;
    Ok(Arc::new(config))
}

struct Construction {
    session_id: [u8; 32],
    order: [u8; 2],
    random: [u8; 32],
    random_calls: u8,
    key: Option<Box<dyn ActiveKeyExchange>>,
    key_starts: u8,
    failed: bool,
}

impl Construction {
    fn new(
        session_id: [u8; 32],
        order: [u8; 2],
        random: [u8; 32],
        key: Box<dyn ActiveKeyExchange>,
    ) -> Self {
        Self {
            session_id,
            order,
            random,
            random_calls: 0,
            key: Some(key),
            key_starts: 0,
            failed: false,
        }
    }
}

thread_local! {
    static CONSTRUCTION: RefCell<Option<Construction>> = const { RefCell::new(None) };
}

// The guard cannot cross threads; the constructor is synchronous, never async.
// The private callbacks release their RefCell borrow before returning to rustls.
struct Scope(PhantomData<Rc<()>>);

impl Scope {
    fn enter(state: Construction) -> Result<Self, &'static str> {
        CONSTRUCTION.with(|cell| {
            let mut slot = cell
                .try_borrow_mut()
                .map_err(|_| "RealityBackendReentrant")?;
            if slot.is_some() {
                return Err("RealityBackendReentrant");
            }
            *slot = Some(state);
            Ok(Self(PhantomData))
        })
    }

    fn validate(&self) -> Result<(), &'static str> {
        CONSTRUCTION.with(|cell| {
            let slot = cell
                .try_borrow()
                .map_err(|_| "RealityBackendConstruction")?;
            let state = slot.as_ref().ok_or("RealityBackendConstruction")?;
            if state.failed
                || state.random_calls != 3
                || state.key_starts != 1
                || state.key.is_some()
            {
                return Err("RealityBackendConstruction");
            }
            Ok(())
        })
    }
}

impl Drop for Scope {
    fn drop(&mut self) {
        // Also drops any key that a failed constructor did not take.
        CONSTRUCTION.with(|cell| *cell.borrow_mut() = None);
    }
}

#[derive(Debug)]
struct ScopedRandom;

impl rustls::crypto::SecureRandom for ScopedRandom {
    fn fill(&self, out: &mut [u8]) -> Result<(), GetRandomFailed> {
        CONSTRUCTION.with(|cell| {
            let mut slot = cell.try_borrow_mut().map_err(|_| GetRandomFailed)?;
            let state = slot.as_mut().ok_or(GetRandomFailed)?;
            if state.failed || state.random_calls >= 3 {
                state.failed = true;
                return Err(GetRandomFailed);
            }
            let source: &[u8] = match state.random_calls {
                0 => &state.session_id,
                1 => &state.order,
                _ => &state.random,
            };
            if source.len() != out.len() {
                state.failed = true;
                return Err(GetRandomFailed);
            }
            out.copy_from_slice(source);
            state.random_calls += 1;
            Ok(())
        })
    }
}

#[derive(Debug)]
struct ScopedHybridGroup;

impl SupportedKxGroup for ScopedHybridGroup {
    fn name(&self) -> NamedGroup {
        NamedGroup::X25519MLKEM768
    }

    fn start(&self) -> Result<Box<dyn ActiveKeyExchange>, Error> {
        CONSTRUCTION.with(|cell| {
            let mut slot = cell.try_borrow_mut().map_err(|_| backend_error())?;
            let state = slot.as_mut().ok_or_else(backend_error)?;
            if state.failed || state.random_calls != 3 || state.key_starts != 0 {
                state.failed = true;
                return Err(backend_error());
            }
            state.key_starts += 1;
            state.key.take().ok_or_else(backend_error)
        })
    }

    fn start_and_complete(&self, _peer: &[u8]) -> Result<CompletedKeyExchange, Error> {
        Err(backend_error())
    }

    fn usable_for_version(&self, version: ProtocolVersion) -> bool {
        version == ProtocolVersion::TLSv1_3
    }

    fn ffdhe_group(&self) -> Option<rustls::ffdhe_groups::FfdheGroup<'static>> {
        None
    }
}

#[derive(Debug)]
struct AdvertiseClassicalOnly;

impl SupportedKxGroup for AdvertiseClassicalOnly {
    fn name(&self) -> NamedGroup {
        NamedGroup::X25519
    }

    fn start(&self) -> Result<Box<dyn ActiveKeyExchange>, Error> {
        // This group only enables the original hybrid owner's free component.
        // HRR must not mint a second private key under the authenticated hello.
        Err(backend_error())
    }

    fn usable_for_version(&self, version: ProtocolVersion) -> bool {
        version == ProtocolVersion::TLSv1_3
    }

    fn ffdhe_group(&self) -> Option<rustls::ffdhe_groups::FfdheGroup<'static>> {
        None
    }
}

struct PreviewKey(Vec<u8>);

impl ActiveKeyExchange for PreviewKey {
    fn pub_key(&self) -> &[u8] {
        &self.0
    }

    fn group(&self) -> NamedGroup {
        NamedGroup::X25519MLKEM768
    }

    fn complete(self: Box<Self>, _peer: &[u8]) -> Result<SharedSecret, Error> {
        Err(backend_error())
    }

    fn hybrid_component(&self) -> Option<(NamedGroup, &[u8])> {
        Some((NamedGroup::X25519, &self.0[super::kx::MLKEM_PUBLIC_LEN..]))
    }

    fn complete_hybrid_component(self: Box<Self>, _peer: &[u8]) -> Result<SharedSecret, Error> {
        Err(backend_error())
    }

    fn ffdhe_group(&self) -> Option<rustls::ffdhe_groups::FfdheGroup<'static>> {
        None
    }
}

#[derive(Debug)]
struct DenyPreviewCertificate;

impl ServerCertVerifier for DenyPreviewCertificate {
    fn verify_server_cert(
        &self,
        _cert: &CertificateDer<'_>,
        _intermediates: &[CertificateDer<'_>],
        _name: &ServerName<'_>,
        _ocsp: &[u8],
        _now: UnixTime,
    ) -> Result<ServerCertVerified, Error> {
        Err(backend_error())
    }

    fn verify_tls12_signature(
        &self,
        _message: &[u8],
        _cert: &CertificateDer<'_>,
        _signature: &rustls::DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, Error> {
        Err(backend_error())
    }

    fn verify_tls13_signature(
        &self,
        _message: &[u8],
        _cert: &CertificateDer<'_>,
        _signature: &rustls::DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, Error> {
        Err(backend_error())
    }

    fn supported_verify_schemes(&self) -> Vec<rustls::SignatureScheme> {
        vec![rustls::SignatureScheme::ED25519]
    }
}

fn backend_error() -> Error {
    Error::General("RealityBackendConstruction".into())
}

fn construct(
    config: Arc<ClientConfig>,
    parameters: &ClientParameters,
    state: Construction,
) -> Result<(ClientConnection, Vec<u8>), &'static str> {
    let scope = Scope::enter(state)?;
    let server_name =
        ServerName::try_from(parameters.server_name.clone()).map_err(|_| "RealityServerName")?;
    let mut connection =
        ClientConnection::new(config, server_name).map_err(|_| "RealityBackendConstruction")?;
    connection.set_buffer_limit(Some(BUFFER_LIMIT));
    scope.validate()?;
    let mut records = Vec::new();
    // Vec writes do not block. The fixed, unfragmented profile currently needs
    // one call; a small bound refuses an unexpected output/state transition.
    for _ in 0..4 {
        if !connection.wants_write() {
            break;
        }
        let written = connection
            .write_tls(&mut records)
            .map_err(|_| "RealityBackendFirstFlight")?;
        if written == 0 || records.len() > MAX_FIRST_FLIGHT {
            return Err("RealityBackendFirstFlight");
        }
    }
    if connection.wants_write() {
        return Err("RealityBackendFirstFlight");
    }
    first_handshake(&records)?;
    drop(scope);
    Ok((connection, records))
}

fn first_handshake(records: &[u8]) -> Result<&[u8], &'static str> {
    let header = records.get(..5).ok_or("RealityBackendFirstFlight")?;
    let length = usize::from(u16::from_be_bytes([header[3], header[4]]));
    if records.len() > MAX_FIRST_FLIGHT
        || header[0] != 22
        || header[1] != 3
        || !matches!(header[2], 1 | 3)
        || records.len() != 5 + length
        || records.get(5) != Some(&1)
    {
        return Err("RealityBackendFirstFlight");
    }
    Ok(&records[5..])
}

#[cfg(test)]
#[path = "backend_tests.rs"]
mod tests;
