use super::*;
use ml_kem::{EncapsulationKey, MlKem768};
use ring::{aead, hkdf, hmac};
use std::{
    collections::BTreeMap,
    io::{Cursor, Read, Write},
    sync::{
        Mutex,
        atomic::{AtomicUsize, Ordering},
    },
};
use tokio_rustls::rustls::{
    CertificateError, ServerConfig, ServerConnection, SignatureAlgorithm, SignatureScheme,
    SupportedCipherSuite,
    crypto::SecureRandom as _,
    pki_types::{PrivateKeyDer, PrivatePkcs8KeyDer, SubjectPublicKeyInfoDer},
    sign::{CertifiedKey, Signer, SigningKey, SingleCertAndKey},
};
use x25519_dalek::{PublicKey, StaticSecret};
use zeroize::Zeroizing;

const TEST_TIME: u32 = 1_792_353_600;

fn parameters() -> ClientParameters {
    ClientParameters::new(
        "reality.test",
        *PublicKey::from(&StaticSecret::from([0x42; 32])).as_bytes(),
        &[0xab, 0xcd],
        [26, 10, 19],
    )
    .unwrap()
}

fn word(bytes: &[u8]) -> usize {
    usize::from(u16::from_be_bytes(bytes[..2].try_into().unwrap()))
}

// Test-side parsing operates on the actual emitted CH. The server's auth key
// is derived from that wire share and a synthetic server private key, never
// read out of the client or its certificate verifier.
fn extensions(hello: &[u8]) -> BTreeMap<u16, &[u8]> {
    assert_eq!(hello[0], 1);
    assert_eq!(hello[38], 32);
    let mut at = 71;
    at += 2 + word(&hello[at..]);
    at += 1 + usize::from(hello[at]);
    let end = at + 2 + word(&hello[at..]);
    at += 2;
    assert_eq!(end, hello.len());
    let mut result = BTreeMap::new();
    while at < end {
        let kind = u16::from_be_bytes(hello[at..at + 2].try_into().unwrap());
        let size = word(&hello[at + 2..]);
        assert!(result.insert(kind, &hello[at + 4..at + 4 + size]).is_none());
        at += 4 + size;
    }
    assert_eq!(at, end);
    result
}

fn wire_shares(hello: &[u8]) -> BTreeMap<u16, &[u8]> {
    let shares = extensions(hello)[&51];
    assert_eq!(word(shares), shares.len() - 2);
    let mut remaining = &shares[2..];
    let mut result = BTreeMap::new();
    while !remaining.is_empty() {
        let group = word(remaining) as u16;
        let length = word(&remaining[2..]);
        assert!(result.insert(group, &remaining[4..4 + length]).is_none());
        remaining = &remaining[4 + length..];
    }
    result
}

fn wire_classical_key(hello: &[u8]) -> [u8; 32] {
    wire_shares(hello)[&29].try_into().unwrap()
}

fn wire_hybrid_component(hello: &[u8]) -> [u8; 32] {
    let shares = wire_shares(hello);
    let hybrid = shares[&0x11ec];
    assert_eq!(hybrid.len(), 1216);
    hybrid[1184..].try_into().unwrap()
}

fn server_auth_key_for_share(hello: &[u8], share: [u8; 32]) -> Zeroizing<[u8; 32]> {
    let server = StaticSecret::from([0x42; 32]);
    let shared = server.diffie_hellman(&PublicKey::from(share));
    assert!(shared.was_contributory());
    let prk = hkdf::Salt::new(hkdf::HKDF_SHA256, &hello[6..26]).extract(shared.as_bytes());
    let mut key = Zeroizing::new([0; 32]);
    prk.expand(&[b"REALITY"], hkdf::HKDF_SHA256)
        .unwrap()
        .fill(key.as_mut())
        .unwrap();
    key
}

fn server_auth_key(hello: &[u8]) -> Zeroizing<[u8; 32]> {
    server_auth_key_for_share(hello, wire_classical_key(hello))
}

fn hex(value: &str) -> Vec<u8> {
    value
        .as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

fn server_certificate(key: &[u8]) -> (CertificateDer<'static>, PrivateKeyDer<'static>) {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("../../tests/fixtures/reality_auth.json")).unwrap();
    let cert = &fixture["certificate"];
    let mut encoded = hex(cert["der_hex"].as_str().unwrap());
    let public_key = hex(cert["ed25519_public_key_hex"].as_str().unwrap());
    let old_mac = hex(cert["hmac_signature_hex"].as_str().unwrap());
    let end = encoded.len() - 64;
    assert_eq!(&encoded[end..], old_mac);
    let signature = hmac::sign(&hmac::Key::new(hmac::HMAC_SHA512, key), &public_key);
    encoded[end..].copy_from_slice(signature.as_ref());
    let private =
        PrivatePkcs8KeyDer::from(hex(cert["ed25519_pkcs8_der_hex"].as_str().unwrap())).into();
    (CertificateDer::from(encoded), private)
}

#[derive(Clone, Copy, Debug)]
enum Fault {
    None,
    CertificateMac,
    CertificateVerifyTranscript,
    CertificateVerifyAlgorithm,
    WrongAuthenticationShare,
}

#[derive(Debug)]
struct RealityTestSigningKey {
    key: Arc<dyn SigningKey>,
    fault: Fault,
}

impl SigningKey for RealityTestSigningKey {
    fn choose_scheme(&self, _offered: &[SignatureScheme]) -> Option<Box<dyn Signer>> {
        // The official REALITY server always signs its synthetic certificate's
        // proof with Ed25519, including Chrome's offer without that scheme.
        // This is a test peer behavior, never a change to client verification.
        self.key
            .choose_scheme(&[SignatureScheme::ED25519])
            .map(|signer| {
                Box::new(RealityTestSigner {
                    signer,
                    fault: self.fault,
                }) as Box<dyn Signer>
            })
    }

    fn public_key(&self) -> Option<SubjectPublicKeyInfoDer<'_>> {
        self.key.public_key()
    }

    fn algorithm(&self) -> SignatureAlgorithm {
        self.key.algorithm()
    }
}

#[derive(Debug)]
struct RealityTestSigner {
    signer: Box<dyn Signer>,
    fault: Fault,
}

impl Signer for RealityTestSigner {
    fn sign(&self, message: &[u8]) -> Result<Vec<u8>, Error> {
        if matches!(self.fault, Fault::CertificateVerifyTranscript) {
            let mut wrong = message.to_vec();
            *wrong.last_mut().unwrap() ^= 1;
            self.signer.sign(&wrong)
        } else {
            self.signer.sign(message)
        }
    }

    fn scheme(&self) -> SignatureScheme {
        if matches!(self.fault, Fault::CertificateVerifyAlgorithm) {
            SignatureScheme::RSA_PSS_SHA256
        } else {
            self.signer.scheme()
        }
    }
}

fn server_configuration(
    hello: &[u8],
    suite: SupportedCipherSuite,
    group: &'static dyn SupportedKxGroup,
    fault: Fault,
    key_log: Option<Arc<dyn rustls::KeyLog>>,
) -> Arc<ServerConfig> {
    let auth_key = if matches!(fault, Fault::WrongAuthenticationShare) {
        server_auth_key_for_share(hello, wire_hybrid_component(hello))
    } else {
        server_auth_key(hello)
    };
    let (mut certificate, private) = server_certificate(auth_key.as_ref());
    if matches!(fault, Fault::CertificateMac) {
        let mut encoded = certificate.as_ref().to_vec();
        *encoded.last_mut().unwrap() ^= 1;
        certificate = CertificateDer::from(encoded);
    }
    let mut provider = rustls::crypto::ring::default_provider();
    provider.cipher_suites = vec![suite];
    provider.kx_groups = vec![group];
    let key = provider.key_provider.load_private_key(private).unwrap();
    let key = Arc::new(RealityTestSigningKey { key, fault });
    let certified = CertifiedKey::new(vec![certificate], key);
    certified.keys_match().unwrap();
    let mut config = ServerConfig::builder_with_provider(Arc::new(provider))
        .with_protocol_versions(&[&rustls::version::TLS13])
        .unwrap()
        .with_no_client_auth()
        .with_cert_resolver(Arc::new(SingleCertAndKey::from(certified)));
    if let Some(alpn) = extensions(hello).get(&16) {
        config.alpn_protocols = vec![alpn[3..3 + usize::from(alpn[2])].to_vec()];
    }
    config.send_tls13_tickets = 0;
    if let Some(log) = key_log {
        config.key_log = log;
    }
    Arc::new(config)
}

fn server(prepared: &Prepared, suite: SupportedCipherSuite, fault: Fault) -> ServerConnection {
    ServerConnection::new(server_configuration(
        &prepared.client_hello,
        suite,
        rustls::crypto::ring::kx_group::X25519,
        fault,
        None,
    ))
    .unwrap()
}

fn drain_client(client: &mut ClientConnection) -> Vec<u8> {
    let mut records = Vec::new();
    for _ in 0..4 {
        if !client.wants_write() {
            break;
        }
        client.write_tls(&mut records).unwrap();
    }
    assert!(!client.wants_write());
    records
}

fn drain_server(server: &mut ServerConnection) -> Vec<u8> {
    let mut records = Vec::new();
    for _ in 0..4 {
        if !server.wants_write() {
            break;
        }
        server.write_tls(&mut records).unwrap();
    }
    assert!(!server.wants_write());
    records
}

fn server_first_flight(prepared: &Prepared, server: &mut ServerConnection) -> Vec<u8> {
    server
        .read_tls(&mut Cursor::new(&prepared.first_flight))
        .unwrap();
    server.process_new_packets().unwrap();
    let records = drain_server(server);
    assert_eq!(records[0], 22);
    let hello = &records[5..5 + word(&records[3..])];
    super::hello::server(hello, &prepared.client_hello, &prepared.offer).unwrap();
    records
}

fn handshake(prepared: &mut Prepared, server: &mut ServerConnection) {
    let records = server_first_flight(prepared, server);
    prepared
        .connection
        .read_tls(&mut Cursor::new(records))
        .unwrap();
    prepared.connection.process_new_packets().unwrap();
    for _ in 0..8 {
        if !prepared.connection.is_handshaking() && !server.is_handshaking() {
            break;
        }
        let client_records = drain_client(&mut prepared.connection);
        if !client_records.is_empty() {
            server.read_tls(&mut Cursor::new(client_records)).unwrap();
            server.process_new_packets().unwrap();
        }
        let server_records = drain_server(server);
        if !server_records.is_empty() {
            prepared
                .connection
                .read_tls(&mut Cursor::new(server_records))
                .unwrap();
            prepared.connection.process_new_packets().unwrap();
        }
    }
    assert!(!prepared.connection.is_handshaking() && !server.is_handshaking());
}

#[test]
fn native_three_suite_profile_authenticates_cv_finished_data_and_close() {
    use rustls::crypto::ring::cipher_suite::{
        TLS13_AES_128_GCM_SHA256, TLS13_AES_256_GCM_SHA384, TLS13_CHACHA20_POLY1305_SHA256,
    };
    for suite in [
        TLS13_AES_128_GCM_SHA256,
        TLS13_AES_256_GCM_SHA384,
        TLS13_CHACHA20_POLY1305_SHA256,
    ] {
        let mut prepared = prepare(&parameters(), TEST_TIME, &[b"h2".to_vec()]).unwrap();
        let mut server = server(&prepared, suite, Fault::None);
        handshake(&mut prepared, &mut server);
        assert_eq!(
            prepared
                .connection
                .negotiated_cipher_suite()
                .unwrap()
                .suite(),
            suite.suite()
        );
        assert_eq!(prepared.connection.alpn_protocol(), Some(b"h2".as_slice()));
        prepared
            .connection
            .writer()
            .write_all(b"bound real TLS data")
            .unwrap();
        server
            .read_tls(&mut Cursor::new(drain_client(&mut prepared.connection)))
            .unwrap();
        server.process_new_packets().unwrap();
        let mut request = [0; 19];
        server.reader().read_exact(&mut request).unwrap();
        assert_eq!(&request, b"bound real TLS data");
        server.writer().write_all(&request).unwrap();
        server.send_close_notify();
        prepared
            .connection
            .read_tls(&mut Cursor::new(drain_server(&mut server)))
            .unwrap();
        assert!(
            prepared
                .connection
                .process_new_packets()
                .unwrap()
                .peer_has_closed()
        );
        let mut response = Vec::new();
        prepared
            .connection
            .reader()
            .read_to_end(&mut response)
            .unwrap();
        assert_eq!(response, request);
        prepared.connection.send_close_notify();
        server
            .read_tls(&mut Cursor::new(drain_client(&mut prepared.connection)))
            .unwrap();
        assert!(server.process_new_packets().unwrap().peer_has_closed());
    }
}

#[test]
fn actual_clienthello_has_bound_authentication_and_only_native_tls13_profile() {
    let prepared = prepare(&parameters(), TEST_TIME, &[]).unwrap();
    assert_eq!(
        first_handshake(&prepared.first_flight).unwrap(),
        prepared.client_hello
    );
    let hello = &prepared.client_hello;
    assert_eq!(&hello[71..79], &[0, 6, 0x13, 2, 0x13, 1, 0x13, 3]);
    let exts = extensions(hello);
    // The native profile still shares its original X25519 component. Chrome's
    // independent component must not weaken these existing native assertions.
    assert_eq!(&exts[&51][2..6], &[0x11, 0xec, 4, 0xc0]);
    assert_eq!(&exts[&51][6 + 1216..6 + 1216 + 4], &[0, 29, 0, 32]);
    assert_eq!(exts[&51].len(), 2 + 4 + 1216 + 4 + 32);
    assert_eq!(wire_classical_key(hello), wire_hybrid_component(hello));
    assert_eq!(exts[&43], &[2, 3, 4]);
    assert_eq!(exts[&13], &[0, 2, 8, 7]);
    for absent in [16, 27, 41, 42, 44, 0xfd00, 0xfe0d] {
        assert!(!exts.contains_key(&absent));
    }
    let key = server_auth_key(hello);
    let mut aad = hello.clone();
    aad[super::hello::SESSION_ID].fill(0);
    let mut sealed = hello[super::hello::SESSION_ID].to_vec();
    let cipher =
        aead::LessSafeKey::new(aead::UnboundKey::new(&aead::AES_256_GCM, key.as_ref()).unwrap());
    let plaintext = cipher
        .open_in_place(
            aead::Nonce::assume_unique_for_key(hello[26..38].try_into().unwrap()),
            aead::Aad::from(aad),
            &mut sealed,
        )
        .unwrap();
    assert_eq!(&plaintext[..4], &[26, 10, 19, 0]);
    assert_eq!(&plaintext[4..8], TEST_TIME.to_be_bytes());
    assert_eq!(&plaintext[8..], &[0xab, 0xcd, 0, 0, 0, 0, 0, 0]);
    assert!(!prepared.connection.wants_write());
}

#[test]
fn alpn_limits_preserve_raw_values_order_and_exact_boundaries() {
    let limit: Vec<_> = (0..4).map(|i| vec![i; 255]).chain([vec![9; 4]]).collect();
    assert_eq!(limit.iter().map(Vec::len).sum::<usize>(), 1024);
    let prepared = prepare(&parameters(), TEST_TIME, &limit).unwrap();
    let exts = extensions(&prepared.client_hello);
    let mut expected = Vec::new();
    for protocol in &limit {
        expected.push(protocol.len() as u8);
        expected.extend_from_slice(protocol);
    }
    assert_eq!(word(exts[&16]), expected.len());
    assert_eq!(&exts[&16][2..], expected);
    let sixteen: Vec<_> = (0..16).map(|i| vec![i]).collect();
    prepare(&parameters(), TEST_TIME, &sixteen).unwrap();
    let mut oversized_total = limit;
    oversized_total.last_mut().unwrap().push(1);
    for invalid in [
        vec![vec![]],
        vec![vec![1; 256]],
        vec![b"h2".to_vec(), b"h2".to_vec()],
        (0..17).map(|i| vec![i]).collect(),
        oversized_total,
    ] {
        assert!(matches!(
            prepare(&parameters(), TEST_TIME, &invalid),
            Err("RealityAlpn")
        ));
    }
    assert!(CONSTRUCTION.with(|cell| cell.borrow().is_none()));
}

#[test]
fn preview_has_no_completion_or_server_authentication_capability() {
    let keys = ClientKeys::generate().unwrap();
    assert!(
        Box::new(PreviewKey(
            keys.hybrid_public_key().to_vec(),
            keys.x25519_public_key().to_vec()
        ))
        .complete(&[0; 1120])
        .is_err()
    );
    assert!(
        Box::new(PreviewKey(
            keys.hybrid_public_key().to_vec(),
            keys.x25519_public_key().to_vec()
        ))
        .complete_hybrid_component(&[0; 32])
        .is_err()
    );
    assert!(AdvertiseClassicalOnly.start().is_err());
    assert!(ScopedHybridGroup.start_and_complete(&[0; 1216]).is_err());
    let (certificate, _) = server_certificate(&[0; 32]);
    assert!(
        DenyPreviewCertificate
            .verify_server_cert(
                &certificate,
                &[],
                &ServerName::try_from("reality.test").unwrap(),
                &[],
                UnixTime::since_unix_epoch(std::time::Duration::ZERO)
            )
            .is_err()
    );
}

struct CountDrop {
    public: Vec<u8>,
    drops: Arc<AtomicUsize>,
}

impl Drop for CountDrop {
    fn drop(&mut self) {
        self.drops.fetch_add(1, Ordering::SeqCst);
    }
}

impl ActiveKeyExchange for CountDrop {
    fn pub_key(&self) -> &[u8] {
        &self.public
    }
    fn group(&self) -> NamedGroup {
        NamedGroup::X25519MLKEM768
    }
    fn complete(self: Box<Self>, _: &[u8]) -> Result<SharedSecret, Error> {
        Err(backend_error())
    }
}

fn context(drops: &Arc<AtomicUsize>) -> Construction {
    Construction::new(
        [1; 32],
        [2; 2],
        [3; 32],
        Box::new(CountDrop {
            public: vec![0; 1216],
            drops: drops.clone(),
        }),
    )
}

#[test]
fn scoped_rng_refuses_wrong_shape_extra_calls_and_outside_calls() {
    assert!(ScopedRandom.fill(&mut [0; 32]).is_err());
    assert!(ScopedHybridGroup.start().is_err());
    let drops = Arc::new(AtomicUsize::new(0));
    {
        let scope = Scope::enter(context(&drops)).unwrap();
        assert!(ScopedRandom.fill(&mut [0; 31]).is_err());
        assert!(ScopedRandom.fill(&mut [0; 32]).is_err());
        assert_eq!(scope.validate(), Err("RealityBackendConstruction"));
    }
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    {
        let scope = Scope::enter(context(&drops)).unwrap();
        ScopedRandom.fill(&mut [0; 32]).unwrap();
        ScopedRandom.fill(&mut [0; 2]).unwrap();
        ScopedRandom.fill(&mut [0; 32]).unwrap();
        assert!(ScopedRandom.fill(&mut [0; 1]).is_err());
        assert!(ScopedHybridGroup.start().is_err());
        assert_eq!(scope.validate(), Err("RealityBackendConstruction"));
    }
    assert_eq!(drops.load(Ordering::SeqCst), 2);
    assert!(CONSTRUCTION.with(|cell| cell.borrow().is_none()));
}

#[test]
fn reentry_and_key_start_order_are_bounded_without_owner_aliases() {
    let drops = Arc::new(AtomicUsize::new(0));
    {
        let scope = Scope::enter(context(&drops)).unwrap();
        assert!(matches!(
            Scope::enter(context(&drops)),
            Err("RealityBackendReentrant")
        ));
        assert_eq!(drops.load(Ordering::SeqCst), 1);
        assert!(ScopedHybridGroup.start().is_err());
        assert_eq!(scope.validate(), Err("RealityBackendConstruction"));
    }
    assert_eq!(drops.load(Ordering::SeqCst), 2);
    {
        let scope = Scope::enter(context(&drops)).unwrap();
        ScopedRandom.fill(&mut [0; 32]).unwrap();
        ScopedRandom.fill(&mut [0; 2]).unwrap();
        ScopedRandom.fill(&mut [0; 32]).unwrap();
        let owner = ScopedHybridGroup.start().unwrap();
        scope.validate().unwrap();
        assert!(ScopedHybridGroup.start().is_err());
        assert_eq!(scope.validate(), Err("RealityBackendConstruction"));
        drop(scope);
        assert_eq!(drops.load(Ordering::SeqCst), 2);
        drop(owner);
    }
    assert_eq!(drops.load(Ordering::SeqCst), 3);
    assert!(CONSTRUCTION.with(|cell| cell.borrow().is_none()));
}

#[test]
fn failed_constructor_and_unwind_drop_untransferred_material() {
    let drops = Arc::new(AtomicUsize::new(0));
    let mut bad = context(&drops);
    bad.failed = true;
    assert!(matches!(
        construct(
            configuration(Arc::new(DenyPreviewCertificate), &[]).unwrap(),
            &parameters(),
            bad
        ),
        Err("RealityBackendConstruction")
    ));
    assert_eq!(drops.load(Ordering::SeqCst), 1);
    assert!(CONSTRUCTION.with(|cell| cell.borrow().is_none()));
    assert!(
        std::panic::catch_unwind(|| {
            let _scope = Scope::enter(context(&drops)).unwrap();
            panic!("injected construction unwind");
        })
        .is_err()
    );
    assert_eq!(drops.load(Ordering::SeqCst), 2);
    assert!(CONSTRUCTION.with(|cell| cell.borrow().is_none()));
    prepare(&parameters(), TEST_TIME, &[]).unwrap();
}

#[test]
fn simultaneous_connections_get_distinct_randoms_sessions_and_keys() {
    let handles: Vec<_> = (0..4)
        .map(|_| {
            std::thread::spawn(|| {
                let mut prepared = prepare(&parameters(), TEST_TIME, &[]).unwrap();
                let mut server = server(
                    &prepared,
                    rustls::crypto::ring::cipher_suite::TLS13_AES_128_GCM_SHA256,
                    Fault::None,
                );
                handshake(&mut prepared, &mut server);
                prepared.client_hello
            })
        })
        .collect();
    let hellos: Vec<_> = handles
        .into_iter()
        .map(|thread| thread.join().unwrap())
        .collect();
    for i in 0..hellos.len() {
        for j in i + 1..hellos.len() {
            assert_ne!(&hellos[i][6..38], &hellos[j][6..38]);
            assert_ne!(
                &hellos[i][super::hello::SESSION_ID],
                &hellos[j][super::hello::SESSION_ID]
            );
            assert_ne!(
                wire_classical_key(&hellos[i]),
                wire_classical_key(&hellos[j])
            );
        }
    }
}

#[test]
fn valid_der_and_possession_do_not_replace_certificate_authentication() {
    let mut prepared = prepare(&parameters(), TEST_TIME, &[]).unwrap();
    let mut server = server(
        &prepared,
        rustls::crypto::ring::cipher_suite::TLS13_AES_128_GCM_SHA256,
        Fault::CertificateMac,
    );
    let records = server_first_flight(&prepared, &mut server);
    prepared
        .connection
        .read_tls(&mut Cursor::new(records))
        .unwrap();
    assert!(matches!(
        prepared.connection.process_new_packets(),
        Err(Error::InvalidCertificate(CertificateError::BadSignature))
    ));
    assert!(prepared.connection.is_handshaking());
    assert!(prepared.connection.reader().read(&mut [0; 1]).is_err());
}

#[test]
fn valid_certificate_mac_does_not_replace_real_certificateverify_transcript() {
    let mut prepared = prepare(&parameters(), TEST_TIME, &[]).unwrap();
    let mut server = server(
        &prepared,
        rustls::crypto::ring::cipher_suite::TLS13_AES_128_GCM_SHA256,
        Fault::CertificateVerifyTranscript,
    );
    let records = server_first_flight(&prepared, &mut server);
    prepared
        .connection
        .read_tls(&mut Cursor::new(records))
        .unwrap();
    assert!(matches!(
        prepared.connection.process_new_packets(),
        Err(Error::InvalidCertificate(CertificateError::BadSignature))
    ));
    assert!(prepared.connection.is_handshaking());
    assert!(prepared.connection.reader().read(&mut [0; 1]).is_err());
}

#[test]
fn encrypted_flight_tampering_fails_before_application_plaintext() {
    let mut prepared = prepare(&parameters(), TEST_TIME, &[]).unwrap();
    let mut server = server(
        &prepared,
        rustls::crypto::ring::cipher_suite::TLS13_AES_128_GCM_SHA256,
        Fault::None,
    );
    let mut records = server_first_flight(&prepared, &mut server);
    *records.last_mut().unwrap() ^= 1;
    prepared
        .connection
        .read_tls(&mut Cursor::new(records))
        .unwrap();
    assert!(matches!(
        prepared.connection.process_new_packets(),
        Err(Error::DecryptError)
    ));
    assert!(prepared.connection.is_handshaking());
    assert!(prepared.connection.reader().read(&mut [0; 1]).is_err());
}

#[test]
fn modifying_only_queued_network_bytes_cannot_match_the_tls_transcript() {
    let mut prepared = prepare(&parameters(), TEST_TIME, &[]).unwrap();
    let mut server = server(
        &prepared,
        rustls::crypto::ring::cipher_suite::TLS13_AES_128_GCM_SHA256,
        Fault::None,
    );
    prepared.first_flight[5 + super::hello::SESSION_ID.start] ^= 1;
    server
        .read_tls(&mut Cursor::new(&prepared.first_flight))
        .unwrap();
    server.process_new_packets().unwrap();
    let records = drain_server(&mut server);
    let server_hello = &records[5..5 + word(&records[3..])];
    assert!(matches!(
        super::hello::server(server_hello, &prepared.client_hello, &prepared.offer),
        Err("RealitySessionIdEcho")
    ));
    prepared
        .connection
        .read_tls(&mut Cursor::new(records))
        .unwrap();
    assert!(matches!(
        prepared.connection.process_new_packets(),
        Err(Error::DecryptError)
    ));
    assert!(prepared.connection.is_handshaking());
}

#[test]
fn first_flight_rejects_partial_records_extra_records_and_unknown_framing() {
    let prepared = prepare(&parameters(), TEST_TIME, &[]).unwrap();
    for truncated in [0, 1, 4, 5, prepared.first_flight.len() - 1] {
        assert_eq!(
            first_handshake(&prepared.first_flight[..truncated]),
            Err("RealityBackendFirstFlight")
        );
    }
    for (offset, value) in [(0, 23), (1, 2), (2, 2), (5, 2)] {
        let mut wrong = prepared.first_flight.clone();
        wrong[offset] = value;
        assert_eq!(first_handshake(&wrong), Err("RealityBackendFirstFlight"));
    }
    let mut extra = prepared.first_flight.clone();
    extra.extend_from_slice(&[20, 3, 3, 0, 1, 1]);
    assert_eq!(first_handshake(&extra), Err("RealityBackendFirstFlight"));
    assert_eq!(
        first_handshake(&vec![0; MAX_FIRST_FLIGHT + 1]),
        Err("RealityBackendFirstFlight")
    );
}

// The test peer's hybrid server operation is deliberately the opposite of the
// production client path: maintained ML-KEM encapsulation plus ring's X25519
// server agreement, starting only with public bytes read from ClientHello.
#[derive(Debug)]
struct TestHybridServer;

impl SupportedKxGroup for TestHybridServer {
    fn name(&self) -> NamedGroup {
        NamedGroup::X25519MLKEM768
    }

    fn start(&self) -> Result<Box<dyn ActiveKeyExchange>, Error> {
        Err(Error::General(
            "test hybrid server requires a client share".into(),
        ))
    }

    fn start_and_complete(&self, peer: &[u8]) -> Result<CompletedKeyExchange, Error> {
        assert_eq!(peer.len(), 1216);
        let public = ml_kem::Key::<EncapsulationKey<MlKem768>>::try_from(&peer[..1184]).unwrap();
        let kem = EncapsulationKey::<MlKem768>::new(&public).unwrap();
        let mut entropy = Zeroizing::new([0; 32]);
        ring::rand::SecureRandom::fill(&SystemRandom::new(), entropy.as_mut()).unwrap();
        let (ciphertext, shared) = kem.encapsulate_deterministic(&(*entropy).into());
        let classical = rustls::crypto::ring::kx_group::X25519.start_and_complete(&peer[1184..])?;
        let mut secret = Zeroizing::new(shared.to_vec());
        secret.extend_from_slice(classical.secret.secret_bytes());
        let mut public = ciphertext.to_vec();
        public.extend_from_slice(&classical.pub_key);
        Ok(CompletedKeyExchange {
            group: self.name(),
            pub_key: public,
            secret: SharedSecret::from(secret.as_slice()),
        })
    }

    fn usable_for_version(&self, version: ProtocolVersion) -> bool {
        version == ProtocolVersion::TLSv1_3
    }

    fn ffdhe_group(&self) -> Option<rustls::ffdhe_groups::FfdheGroup<'static>> {
        None
    }
}

fn chrome_parameters() -> ClientParameters {
    parameters().with_fingerprint("chrome").unwrap()
}

fn open_session(
    hello: &[u8],
    key: &[u8],
    nonce: [u8; 12],
    aad: &[u8],
) -> Result<Vec<u8>, ring::error::Unspecified> {
    let cipher = aead::LessSafeKey::new(aead::UnboundKey::new(&aead::AES_256_GCM, key)?);
    let mut session = hello[super::hello::SESSION_ID].to_vec();
    cipher
        .open_in_place(
            aead::Nonce::assume_unique_for_key(nonce),
            aead::Aad::from(aad),
            &mut session,
        )
        .map(|plain| plain.to_vec())
}

#[test]
fn chrome_authentication_uses_standalone_key_and_binds_every_hello_byte() {
    let prepared = prepare(&chrome_parameters(), TEST_TIME, &[]).unwrap();
    let hello = &prepared.client_hello;
    assert_ne!(wire_classical_key(hello), wire_hybrid_component(hello));
    let key = server_auth_key(hello);
    let wrong_branch = server_auth_key_for_share(hello, wire_hybrid_component(hello));
    assert_ne!(key.as_ref(), wrong_branch.as_ref());
    let nonce: [u8; 12] = hello[26..38].try_into().unwrap();
    let mut aad = hello.clone();
    aad[super::hello::SESSION_ID].fill(0);
    let mut expected = vec![26, 10, 19, 0];
    expected.extend_from_slice(&TEST_TIME.to_be_bytes());
    expected.extend_from_slice(&[0xab, 0xcd, 0, 0, 0, 0, 0, 0]);
    assert_eq!(
        open_session(hello, key.as_ref(), nonce, &aad).unwrap(),
        expected
    );
    assert!(open_session(hello, wrong_branch.as_ref(), nonce, &aad).is_err());
    assert!(open_session(hello, key.as_ref(), nonce, hello).is_err());
    let mut wrong_nonce = nonce;
    wrong_nonce[0] ^= 1;
    assert!(open_session(hello, key.as_ref(), wrong_nonce, &aad).is_err());
    // This checks all actual browser fields, including shuffled GREASE, ECH,
    // ALPN and signatures, without reconstructing the production encoder.
    for offset in 0..aad.len() {
        let mut altered = aad.clone();
        altered[offset] ^= 1;
        assert!(
            open_session(hello, key.as_ref(), nonce, &altered).is_err(),
            "AAD byte {offset}"
        );
    }
    let second = prepare(&chrome_parameters(), TEST_TIME, &[]).unwrap();
    assert_ne!(&hello[6..38], &second.client_hello[6..38]);
    assert_ne!(
        wire_classical_key(hello),
        wire_classical_key(&second.client_hello)
    );
    assert_ne!(
        wire_hybrid_component(hello),
        wire_hybrid_component(&second.client_hello)
    );
    assert_ne!(
        &hello[super::hello::SESSION_ID],
        &second.client_hello[super::hello::SESSION_ID]
    );
}

#[test]
fn chrome_both_owned_key_branches_complete_real_tls_data_and_close() {
    use rustls::crypto::ring::cipher_suite::{
        TLS13_AES_128_GCM_SHA256, TLS13_AES_256_GCM_SHA384, TLS13_CHACHA20_POLY1305_SHA256,
    };
    let groups: [&'static dyn SupportedKxGroup; 2] =
        [&TestHybridServer, rustls::crypto::ring::kx_group::X25519];
    for group in groups {
        for suite in [
            TLS13_AES_128_GCM_SHA256,
            TLS13_AES_256_GCM_SHA384,
            TLS13_CHACHA20_POLY1305_SHA256,
        ] {
            let mut prepared = prepare(&chrome_parameters(), TEST_TIME, &[]).unwrap();
            assert_ne!(
                wire_classical_key(&prepared.client_hello),
                wire_hybrid_component(&prepared.client_hello)
            );
            let mut server = ServerConnection::new(server_configuration(
                &prepared.client_hello,
                suite,
                group,
                Fault::None,
                None,
            ))
            .unwrap();
            handshake(&mut prepared, &mut server);
            assert_eq!(
                prepared
                    .connection
                    .negotiated_key_exchange_group()
                    .unwrap()
                    .name(),
                group.name()
            );
            assert_eq!(
                prepared
                    .connection
                    .negotiated_cipher_suite()
                    .unwrap()
                    .suite(),
                suite.suite()
            );
            assert_eq!(prepared.connection.alpn_protocol(), Some(b"h2".as_slice()));
            let message = b"Chrome branch authenticates real TLS data".repeat(97);
            prepared.connection.writer().write_all(&message).unwrap();
            server
                .read_tls(&mut Cursor::new(drain_client(&mut prepared.connection)))
                .unwrap();
            server.process_new_packets().unwrap();
            let mut received = vec![0; message.len()];
            server.reader().read_exact(&mut received).unwrap();
            assert_eq!(received, message);
            server.writer().write_all(&received).unwrap();
            server.send_close_notify();
            prepared
                .connection
                .read_tls(&mut Cursor::new(drain_server(&mut server)))
                .unwrap();
            assert!(
                prepared
                    .connection
                    .process_new_packets()
                    .unwrap()
                    .peer_has_closed()
            );
            let mut echoed = Vec::new();
            prepared
                .connection
                .reader()
                .read_to_end(&mut echoed)
                .unwrap();
            assert_eq!(echoed, message);
            prepared.connection.send_close_notify();
            server
                .read_tls(&mut Cursor::new(drain_client(&mut prepared.connection)))
                .unwrap();
            assert!(server.process_new_packets().unwrap().peer_has_closed());
        }
    }
}

#[test]
fn chrome_certificate_authentication_and_certificate_verify_stay_strict() {
    for fault in [
        Fault::CertificateMac,
        Fault::WrongAuthenticationShare,
        Fault::CertificateVerifyTranscript,
        Fault::CertificateVerifyAlgorithm,
    ] {
        let mut prepared = prepare(&chrome_parameters(), TEST_TIME, &[]).unwrap();
        let mut server = server(
            &prepared,
            rustls::crypto::ring::cipher_suite::TLS13_AES_128_GCM_SHA256,
            fault,
        );
        let records = server_first_flight(&prepared, &mut server);
        prepared
            .connection
            .read_tls(&mut Cursor::new(records))
            .unwrap();
        let error = prepared.connection.process_new_packets().unwrap_err();
        if matches!(fault, Fault::CertificateVerifyAlgorithm) {
            assert!(
                matches!(error, Error::General(ref reason) if reason == "RealityCertificateVerifyAlgorithmUnsupported"),
                "{error:?}"
            );
        } else {
            assert!(
                matches!(
                    error,
                    Error::InvalidCertificate(CertificateError::BadSignature)
                ),
                "{fault:?}: {error:?}"
            );
        }
        assert!(prepared.connection.is_handshaking());
        assert!(prepared.connection.reader().read(&mut [0; 1]).is_err());
    }
}

// In-memory secrets of this synthetic test server only. Nothing is written to
// disk or emitted in logs, and the client still uses the production verifier.
#[derive(Default)]
struct TestHandshakeSecret(Mutex<Zeroizing<Vec<u8>>>);

impl std::fmt::Debug for TestHandshakeSecret {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("TestHandshakeSecret([REDACTED])")
    }
}

impl rustls::KeyLog for TestHandshakeSecret {
    fn log(&self, label: &str, _client_random: &[u8], secret: &[u8]) {
        if label == "SERVER_HANDSHAKE_TRAFFIC_SECRET" {
            *self.0.lock().unwrap() = Zeroizing::new(secret.to_vec());
        }
    }

    fn will_log(&self, label: &str) -> bool {
        label == "SERVER_HANDSHAKE_TRAFFIC_SECRET"
    }
}

fn traffic_key_material(secret: &[u8], label: &[u8], length: usize) -> Zeroizing<Vec<u8>> {
    struct Length(usize);
    impl hkdf::KeyType for Length {
        fn len(&self) -> usize {
            self.0
        }
    }
    let mut info = (length as u16).to_be_bytes().to_vec();
    info.push((6 + label.len()) as u8);
    info.extend_from_slice(b"tls13 ");
    info.extend_from_slice(label);
    info.push(0);
    let mut output = Zeroizing::new(vec![0; length]);
    hkdf::Prk::new_less_safe(hkdf::HKDF_SHA256, secret)
        .expand(&[&info], Length(length))
        .unwrap()
        .fill(output.as_mut())
        .unwrap();
    output
}

fn authenticated_server_edit(
    records: &[u8],
    secret: &[u8],
    kind: u8,
    edit: fn(&mut Vec<u8>),
) -> Vec<u8> {
    // Fixed to the AES-128/SHA-256 suite used by the two negative tests.
    // Decrypt/reseal with a valid record tag: a Finished failure then cannot be
    // explained by random ciphertext corruption or broken record protection.
    assert_eq!(secret.len(), 32);
    let key = traffic_key_material(secret, b"key", 16);
    let iv = traffic_key_material(secret, b"iv", 12);
    let cipher = aead::LessSafeKey::new(aead::UnboundKey::new(&aead::AES_128_GCM, &key).unwrap());
    let mut remaining = records;
    let mut output = Vec::new();
    let mut sequence = 0u64;
    let mut edits = 0;
    while !remaining.is_empty() {
        let length = word(&remaining[3..]);
        let record = &remaining[..5 + length];
        remaining = &remaining[record.len()..];
        if record[0] != 23 {
            output.extend_from_slice(record);
            continue;
        }
        let mut nonce: [u8; 12] = iv.as_slice().try_into().unwrap();
        for (byte, count) in nonce[4..].iter_mut().zip(sequence.to_be_bytes()) {
            *byte ^= count;
        }
        sequence += 1;
        let mut ciphertext = record[5..].to_vec();
        let plaintext = cipher
            .open_in_place(
                aead::Nonce::assume_unique_for_key(nonce),
                aead::Aad::from(&record[..5]),
                &mut ciphertext,
            )
            .unwrap();
        let end = plaintext.iter().rposition(|byte| *byte != 0).unwrap();
        assert_eq!(plaintext[end], 22);
        let mut messages = &plaintext[..end];
        let mut modified = Vec::new();
        while !messages.is_empty() {
            let count = u32::from_be_bytes([0, messages[1], messages[2], messages[3]]) as usize;
            let message = &messages[..4 + count];
            messages = &messages[message.len()..];
            if message[0] == kind {
                let mut body = message[4..].to_vec();
                edit(&mut body);
                modified.push(kind);
                modified.extend_from_slice(&(body.len() as u32).to_be_bytes()[1..]);
                modified.extend_from_slice(&body);
                edits += 1;
            } else {
                modified.extend_from_slice(message);
            }
        }
        modified.push(22);
        let mut header = vec![23, 3, 3];
        header.extend_from_slice(&((modified.len() + 16) as u16).to_be_bytes());
        let expected = modified.clone();
        cipher
            .seal_in_place_append_tag(
                aead::Nonce::assume_unique_for_key(nonce),
                aead::Aad::from(&header),
                &mut modified,
            )
            .unwrap();
        let mut verified = modified.clone();
        assert_eq!(
            cipher
                .open_in_place(
                    aead::Nonce::assume_unique_for_key(nonce),
                    aead::Aad::from(&header),
                    &mut verified
                )
                .unwrap(),
            expected
        );
        output.extend_from_slice(&header);
        output.extend_from_slice(&modified);
    }
    assert_eq!(edits, 1);
    output
}

fn feed_tls_client(client: &mut super::super::TlsClient, records: &[u8]) -> std::io::Result<()> {
    let mut input = Cursor::new(records);
    while (input.position() as usize) < records.len() {
        while client.wants_write() {
            let mut compatibility_ccs = Vec::new();
            client.write_tls(&mut compatibility_ccs)?;
            assert_eq!(compatibility_ccs, [20, 3, 3, 0, 1, 1]);
        }
        assert!(client.read_tls(&mut input)? > 0);
    }
    Ok(())
}

#[test]
fn chrome_finished_and_unimplemented_alps_fail_with_valid_record_authentication() {
    for kind in [20, 8] {
        let mut client =
            super::super::TlsClient::new(&chrome_parameters(), TEST_TIME, &[]).unwrap();
        assert_eq!(
            client
                .write_plaintext(b"must never leave")
                .unwrap_err()
                .kind(),
            std::io::ErrorKind::WouldBlock
        );
        let mut first_flight = Vec::new();
        client.write_tls(&mut first_flight).unwrap();
        let log = Arc::new(TestHandshakeSecret::default());
        let mut server = ServerConnection::new(server_configuration(
            &first_flight[5..],
            rustls::crypto::ring::cipher_suite::TLS13_AES_128_GCM_SHA256,
            rustls::crypto::ring::kx_group::X25519,
            Fault::None,
            Some(log.clone()),
        ))
        .unwrap();
        server.read_tls(&mut Cursor::new(first_flight)).unwrap();
        server.process_new_packets().unwrap();
        let records = drain_server(&mut server);
        let secret = log.0.lock().unwrap();
        let altered = authenticated_server_edit(
            &records,
            &secret,
            kind,
            if kind == 20 {
                |finished| {
                    finished[0] ^= 1;
                }
            } else {
                |extensions| {
                    assert_eq!(word(extensions), extensions.len() - 2);
                    extensions.extend_from_slice(&[0x44, 0xcd, 0, 0]); // Negotiated ALPS.
                    let count = (extensions.len() - 2) as u16;
                    extensions[..2].copy_from_slice(&count.to_be_bytes());
                }
            },
        );
        let error = feed_tls_client(&mut client, &altered).unwrap_err();
        let source = error.get_ref().unwrap().downcast_ref::<Error>().unwrap();
        if kind == 20 {
            assert!(matches!(source, Error::DecryptError));
        } else {
            assert!(
                matches!(source, Error::General(reason) if reason == "CustomClientHelloExtensionNegotiationUnsupported")
            );
        }
        assert!(client.is_handshaking());
        assert!(client.negotiated_cipher_suite().is_none());
        assert!(client.negotiated_group().is_none());
        assert!(client.alpn_protocol().is_none());
        assert!(!client.wants_read() && !client.wants_write());
        assert_eq!(
            client
                .write_plaintext(b"must never leave")
                .unwrap_err()
                .kind(),
            std::io::ErrorKind::InvalidData
        );
        assert_eq!(
            client.read_plaintext(&mut [0; 1]).unwrap_err().kind(),
            std::io::ErrorKind::InvalidData
        );
    }
}

#[test]
fn chrome_profile_rejects_unsupported_names_and_alpn_without_constructing_a_connection() {
    for fingerprint in ["firefox", "safari", "chrome_155", "random", ""] {
        assert!(matches!(
            parameters().with_fingerprint(fingerprint),
            Err("RealityFingerprintUnsupported")
        ));
    }
    for alpn in [
        vec![b"h2".to_vec()],
        vec![b"http/1.1".to_vec()],
        vec![b"http/1.1".to_vec(), b"h2".to_vec()],
        vec![b"custom".to_vec()],
    ] {
        assert!(matches!(
            prepare(&chrome_parameters(), TEST_TIME, &alpn),
            Err("RealityFingerprintAlpnUnsupported")
        ));
    }
    let explicit = parameters().with_fingerprint("chrome_133").unwrap();
    prepare(
        &explicit,
        TEST_TIME,
        &[b"h2".to_vec(), b"http/1.1".to_vec()],
    )
    .unwrap();
    assert!(CONSTRUCTION.with(|cell| cell.borrow().is_none()));
}
