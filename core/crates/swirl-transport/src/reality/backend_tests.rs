use super::*;
use ring::{aead, hkdf, hmac};
use std::{
    collections::BTreeMap,
    io::{Cursor, Read, Write},
    sync::atomic::{AtomicUsize, Ordering},
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

fn wire_classical_key(hello: &[u8]) -> [u8; 32] {
    let shares = extensions(hello)[&51];
    assert_eq!(word(shares), shares.len() - 2);
    assert_eq!(word(&shares[2..]), 0x11ec);
    assert_eq!(word(&shares[4..]), 1216);
    let classical: [u8; 32] = shares[6 + 1184..6 + 1216].try_into().unwrap();
    let tail = &shares[6 + 1216..];
    assert_eq!(word(tail), 29);
    assert_eq!(word(&tail[2..]), 32);
    assert_eq!(&tail[4..], classical);
    classical
}

fn server_auth_key(hello: &[u8]) -> Zeroizing<[u8; 32]> {
    let server = StaticSecret::from([0x42; 32]);
    let shared = server.diffie_hellman(&PublicKey::from(wire_classical_key(hello)));
    assert!(shared.was_contributory());
    let prk = hkdf::Salt::new(hkdf::HKDF_SHA256, &hello[6..26]).extract(shared.as_bytes());
    let mut key = Zeroizing::new([0; 32]);
    prk.expand(&[b"REALITY"], hkdf::HKDF_SHA256)
        .unwrap()
        .fill(key.as_mut())
        .unwrap();
    key
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

#[derive(Clone, Copy)]
enum Fault {
    None,
    CertificateMac,
    CertificateVerifyTranscript,
}

#[derive(Debug)]
struct WrongTranscriptKey(Arc<dyn SigningKey>);

impl SigningKey for WrongTranscriptKey {
    fn choose_scheme(&self, offered: &[SignatureScheme]) -> Option<Box<dyn Signer>> {
        self.0
            .choose_scheme(offered)
            .map(|signer| Box::new(WrongTranscriptSigner(signer)) as Box<dyn Signer>)
    }

    fn public_key(&self) -> Option<SubjectPublicKeyInfoDer<'_>> {
        self.0.public_key()
    }

    fn algorithm(&self) -> SignatureAlgorithm {
        self.0.algorithm()
    }
}

#[derive(Debug)]
struct WrongTranscriptSigner(Box<dyn Signer>);

impl Signer for WrongTranscriptSigner {
    fn sign(&self, message: &[u8]) -> Result<Vec<u8>, Error> {
        let mut wrong = message.to_vec();
        *wrong.last_mut().unwrap() ^= 1;
        self.0.sign(&wrong)
    }

    fn scheme(&self) -> SignatureScheme {
        self.0.scheme()
    }
}

fn server(prepared: &Prepared, suite: SupportedCipherSuite, fault: Fault) -> ServerConnection {
    let auth_key = server_auth_key(&prepared.client_hello);
    let (mut certificate, private) = server_certificate(auth_key.as_ref());
    if matches!(fault, Fault::CertificateMac) {
        let mut encoded = certificate.as_ref().to_vec();
        *encoded.last_mut().unwrap() ^= 1;
        certificate = CertificateDer::from(encoded);
    }
    let mut provider = rustls::crypto::ring::default_provider();
    provider.cipher_suites = vec![suite];
    provider.kx_groups = vec![rustls::crypto::ring::kx_group::X25519];
    let key = provider.key_provider.load_private_key(private).unwrap();
    let key: Arc<dyn SigningKey> = match fault {
        Fault::CertificateVerifyTranscript => Arc::new(WrongTranscriptKey(key)),
        _ => key,
    };
    let certified = CertifiedKey::new(vec![certificate], key);
    certified.keys_match().unwrap();
    let mut config = ServerConfig::builder_with_provider(Arc::new(provider))
        .with_protocol_versions(&[&rustls::version::TLS13])
        .unwrap()
        .with_no_client_auth()
        .with_cert_resolver(Arc::new(SingleCertAndKey::from(certified)));
    if let Some(alpn) = extensions(&prepared.client_hello).get(&16) {
        config.alpn_protocols = vec![alpn[3..3 + usize::from(alpn[2])].to_vec()];
    }
    config.send_tls13_tickets = 0;
    ServerConnection::new(Arc::new(config)).unwrap()
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
        Box::new(PreviewKey(keys.hybrid_public_key().to_vec()))
            .complete(&[0; 1120])
            .is_err()
    );
    assert!(
        Box::new(PreviewKey(keys.hybrid_public_key().to_vec()))
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
