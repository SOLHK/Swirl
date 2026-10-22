//! REALITY's pinned-key certificate authentication, independent of WebPKI.
//!
//! The certificate's outer signature is an HMAC over its Ed25519 public key.
//! This authenticates the key; TLS 1.3 CertificateVerify must separately prove
//! possession of its private key and bind it to the handshake transcript.
//! No CA certificate, hostname match or successful DER parse replaces either
//! authentication step. The TLS backend must additionally verify Finished.

use std::fmt;

use ring::{hmac, signature};
use tokio_rustls::rustls::{
    CertificateError, DigitallySignedStruct, Error, SignatureScheme,
    client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier},
    pki_types::{CertificateDer, ServerName, UnixTime},
};
use x509_cert::{
    Version,
    der::{
        Decode, Sequence, Tag, Tagged,
        asn1::{AnyRef, BitStringRef, GeneralizedTime, ObjectIdentifier, UtcTime},
    },
    ext::Extensions,
    name::Name,
    serial_number::SerialNumber,
    spki::{AlgorithmIdentifierRef, SubjectPublicKeyInfoRef},
};
use zeroize::Zeroizing;

const ED25519: ObjectIdentifier = ObjectIdentifier::new_unwrap("1.3.101.112");
const MAX_CERTIFICATE_LEN: usize = 16 * 1024;

/// Authenticates the extension-free Ed25519 REALITY certificate profile.
///
/// Only the authenticated ClientHello/key-exchange owner can construct this
/// verifier. It contains the derived per-attempt authentication key, never a
/// caller-supplied "skip verification" flag. Optional ML-DSA authentication,
/// certificate chains and OCSP are deliberately unsupported by this profile.
pub struct ServerAuthenticator {
    authentication_key: Zeroizing<[u8; 32]>,
}

impl fmt::Debug for ServerAuthenticator {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("ServerAuthenticator { authentication_key: [REDACTED] }")
    }
}

impl ServerAuthenticator {
    pub(crate) fn new(authentication_key: Zeroizing<[u8; 32]>) -> Self {
        Self { authentication_key }
    }

    fn authenticate_certificate(&self, encoded: &[u8]) -> Result<[u8; 32], Error> {
        if encoded.len() > MAX_CERTIFICATE_LEN {
            return Err(CertificateError::BadEncoding.into());
        }

        // Decode consumes the entire certificate and each nested SEQUENCE;
        // valid prefixes, nonminimal lengths and trailing fields are rejected.
        let certificate =
            RealityCertificate::from_der(encoded).map_err(|_| CertificateError::BadEncoding)?;
        let tbs = &certificate.tbs;
        tbs.validity.validate_encoding()?;
        if tbs.version != Version::V3
            || tbs.issuer_unique_id.is_some()
            || tbs.subject_unique_id.is_some()
            || tbs.extensions.is_some()
        {
            return Err(Error::General(
                "RealityCertificateProfileUnsupported".into(),
            ));
        }

        let spki = &tbs.subject_public_key_info;
        for algorithm in [
            &tbs.signature,
            &certificate.signature_algorithm,
            &spki.algorithm,
        ] {
            // RFC 8410 requires Ed25519 AlgorithmIdentifier parameters absent;
            // ASN.1 NULL is not interchangeable with absent parameters.
            if algorithm.oid != ED25519 || algorithm.parameters.is_some() {
                return Err(Error::General(
                    "RealityCertificateAlgorithmUnsupported".into(),
                ));
            }
        }
        let public_key: [u8; 32] = spki
            .subject_public_key
            .as_bytes()
            .and_then(|bytes| bytes.try_into().ok())
            .ok_or(CertificateError::BadEncoding)?;
        let certificate_mac = certificate
            .signature
            .as_bytes()
            .filter(|bytes| bytes.len() == 64)
            .ok_or(CertificateError::BadEncoding)?;
        let mac_key = hmac::Key::new(hmac::HMAC_SHA512, self.authentication_key.as_ref());
        hmac::verify(&mac_key, &public_key, certificate_mac)
            .map_err(|_| CertificateError::BadSignature)?;
        Ok(public_key)
    }
}

impl ServerCertVerifier for ServerAuthenticator {
    fn verify_server_cert(
        &self,
        end_entity: &CertificateDer<'_>,
        intermediates: &[CertificateDer<'_>],
        _server_name: &ServerName<'_>,
        ocsp_response: &[u8],
        _now: UnixTime,
    ) -> Result<ServerCertVerified, Error> {
        if !intermediates.is_empty() || !ocsp_response.is_empty() {
            return Err(Error::General(
                "RealityCertificateProfileUnsupported".into(),
            ));
        }
        // Names and validity do not provide REALITY's trust anchor. Its genuine
        // synthetic certificates may have empty names and year-0001 dates.
        // SNI is instead bound by the authenticated ClientHello, and the pinned
        // server key supplies the authentication key used here. Never fall back
        // to normal CA validation of a cover server's certificate.
        self.authenticate_certificate(end_entity.as_ref())?;
        Ok(ServerCertVerified::assertion())
    }

    fn verify_tls12_signature(
        &self,
        _message: &[u8],
        _cert: &CertificateDer<'_>,
        _dss: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, Error> {
        Err(Error::General("RealityTls13Required".into()))
    }

    fn verify_tls13_signature(
        &self,
        message: &[u8],
        cert: &CertificateDer<'_>,
        dss: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, Error> {
        if dss.scheme != SignatureScheme::ED25519 {
            return Err(Error::General(
                "RealityCertificateVerifyAlgorithmUnsupported".into(),
            ));
        }
        let public_key = self.authenticate_certificate(cert.as_ref())?;
        // rustls supplies the full TLS 1.3 CertificateVerify signing input:
        // 64 spaces || server context || zero byte || transcript hash. Verify
        // that exact message with Ed25519, not just an extracted digest or MAC.
        signature::UnparsedPublicKey::new(&signature::ED25519, public_key)
            .verify(message, dss.signature())
            .map_err(|_| CertificateError::BadSignature)?;
        Ok(HandshakeSignatureValid::assertion())
    }

    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> {
        vec![SignatureScheme::ED25519]
    }
}

// A narrow RFC 5280 schema, decoded by maintained RustCrypto DER types. The
// normal x509-cert Time type cannot represent dates before 1970; upstream
// REALITY uses the exact year-0001 placeholder below. Keeping the two time
// values borrowed allows that one canonical representation without rewriting
// the certificate bytes, relaxing DER parsing or implementing a time parser.
#[derive(Sequence)]
struct RealityCertificate<'a> {
    tbs: RealityTbsCertificate<'a>,
    signature_algorithm: AlgorithmIdentifierRef<'a>,
    signature: BitStringRef<'a>,
}

#[derive(Sequence)]
struct RealityTbsCertificate<'a> {
    #[asn1(context_specific = "0", default = "Default::default")]
    version: Version,
    serial_number: SerialNumber,
    signature: AlgorithmIdentifierRef<'a>,
    issuer: Name,
    validity: RealityValidity<'a>,
    subject: Name,
    subject_public_key_info: SubjectPublicKeyInfoRef<'a>,
    #[asn1(context_specific = "1", tag_mode = "IMPLICIT", optional = "true")]
    issuer_unique_id: Option<BitStringRef<'a>>,
    #[asn1(context_specific = "2", tag_mode = "IMPLICIT", optional = "true")]
    subject_unique_id: Option<BitStringRef<'a>>,
    #[asn1(context_specific = "3", tag_mode = "EXPLICIT", optional = "true")]
    extensions: Option<Extensions>,
}

#[derive(Sequence)]
struct RealityValidity<'a> {
    not_before: AnyRef<'a>,
    not_after: AnyRef<'a>,
}

impl RealityValidity<'_> {
    fn validate_encoding(&self) -> Result<(), Error> {
        for time in [self.not_before, self.not_after] {
            let valid = match time.tag() {
                Tag::GeneralizedTime if time.value() == b"00010101000000Z" => true,
                Tag::GeneralizedTime => time.decode_as::<GeneralizedTime>().is_ok(),
                Tag::UtcTime => time.decode_as::<UtcTime>().is_ok(),
                _ => false,
            };
            if !valid {
                return Err(CertificateError::BadEncoding.into());
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;
    use std::{
        io::{Cursor, Read, Write},
        sync::Arc,
    };
    use tokio_rustls::rustls::{
        ClientConfig, ClientConnection, IoState, NamedGroup, ProtocolVersion, ServerConfig,
        ServerConnection,
        crypto::ring::{default_provider, kx_group},
        internal::msgs::codec::Codec,
        pki_types::{PrivateKeyDer, PrivatePkcs8KeyDer},
        version::TLS13,
    };

    fn fixture() -> Value {
        serde_json::from_str(include_str!("../../tests/fixtures/reality_auth.json")).unwrap()
    }

    fn hex(value: &Value) -> Vec<u8> {
        let (pairs, trailing) = value.as_str().unwrap().as_bytes().as_chunks::<2>();
        assert!(trailing.is_empty(), "fixture hex must encode whole bytes");
        pairs
            .iter()
            .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
            .collect()
    }

    fn authenticator(f: &Value) -> ServerAuthenticator {
        ServerAuthenticator::new(Zeroizing::new(
            hex(&f["certificate"]["auth_key_hex"]).try_into().unwrap(),
        ))
    }

    fn verify(
        authenticator: &ServerAuthenticator,
        certificate: &[u8],
    ) -> Result<ServerCertVerified, Error> {
        authenticator.verify_server_cert(
            &CertificateDer::from(certificate),
            &[],
            &ServerName::try_from("reality.test").unwrap(),
            &[],
            UnixTime::since_unix_epoch(std::time::Duration::from_secs(1_792_368_000)),
        )
    }

    // Test-only rustls wire decoding exercises the real verifier trait methods;
    // production never depends on rustls's internal message codec API.
    fn signed(encoding: &[u8]) -> DigitallySignedStruct {
        DigitallySignedStruct::read_bytes(encoding).unwrap()
    }

    #[test]
    fn independent_certificate_hmac_and_upstream_minimal_profile_are_accepted() {
        let f = fixture();
        for field in ["der_hex", "upstream_minimal_der_hex"] {
            assert!(
                verify(&authenticator(&f), &hex(&f["certificate"][field])).is_ok(),
                "{field}"
            );
        }
    }

    #[test]
    fn wrong_authentication_key_is_rejected() {
        let f = fixture();
        let mut key: [u8; 32] = hex(&f["certificate"]["auth_key_hex"]).try_into().unwrap();
        key[0] ^= 1;
        assert!(matches!(
            verify(
                &ServerAuthenticator::new(Zeroizing::new(key)),
                &hex(&f["certificate"]["der_hex"])
            ),
            Err(Error::InvalidCertificate(CertificateError::BadSignature))
        ));
    }

    #[test]
    fn certificate_mac_and_public_key_tampering_are_rejected() {
        let f = fixture();
        let auth = authenticator(&f);
        let mut certificate = hex(&f["certificate"]["der_hex"]);
        *certificate.last_mut().unwrap() ^= 1;
        assert!(matches!(
            verify(&auth, &certificate),
            Err(Error::InvalidCertificate(CertificateError::BadSignature))
        ));

        let mut certificate = hex(&f["certificate"]["der_hex"]);
        let public_key = hex(&f["certificate"]["ed25519_public_key_hex"]);
        let at = certificate
            .windows(public_key.len())
            .position(|bytes| bytes == public_key)
            .unwrap();
        certificate[at] ^= 1;
        assert!(matches!(
            verify(&auth, &certificate),
            Err(Error::InvalidCertificate(CertificateError::BadSignature))
        ));
    }

    #[test]
    fn ordinary_valid_certificate_and_unsupported_mldsa_have_no_fallback() {
        let f = fixture();
        for field in ["ordinary_self_signed_der_hex", "unsupported_mldsa_der_hex"] {
            assert!(
                verify(&authenticator(&f), &hex(&f["certificate"][field])).is_err(),
                "{field}"
            );
        }
    }

    #[test]
    fn certificate_chain_and_ocsp_are_explicitly_rejected() {
        let f = fixture();
        let auth = authenticator(&f);
        let certificate = CertificateDer::from(hex(&f["certificate"]["der_hex"]));
        let name = ServerName::try_from("reality.test").unwrap();
        let now = UnixTime::since_unix_epoch(std::time::Duration::from_secs(0));
        assert!(
            auth.verify_server_cert(
                &certificate,
                std::slice::from_ref(&certificate),
                &name,
                &[],
                now
            )
            .is_err()
        );
        assert!(
            auth.verify_server_cert(&certificate, &[], &name, &[0], now)
                .is_err()
        );
    }

    #[test]
    fn every_truncated_certificate_and_trailing_data_are_rejected() {
        let f = fixture();
        let auth = authenticator(&f);
        let certificate = hex(&f["certificate"]["der_hex"]);
        for len in 0..certificate.len() {
            assert!(
                verify(&auth, &certificate[..len]).is_err(),
                "truncated length {len}"
            );
        }
        let mut trailing = certificate;
        trailing.extend_from_slice(&[5, 0]);
        assert!(verify(&auth, &trailing).is_err());
        assert!(verify(&auth, &vec![0; MAX_CERTIFICATE_LEN + 1]).is_err());
    }

    // Independent test-only DER framing lets negatives retain correct parent
    // lengths. A malformed child must fail for its contents, not an unrelated
    // enclosing length error. This is never used by the certificate verifier.
    fn tlv(input: &[u8]) -> (&[u8], &[u8]) {
        let (header, len) = if input[1] & 128 == 0 {
            (2, usize::from(input[1]))
        } else {
            let octets = usize::from(input[1] & 127);
            let len = input[2..2 + octets]
                .iter()
                .fold(0, |len, byte| (len << 8) | usize::from(*byte));
            (2 + octets, len)
        };
        (&input[header..header + len], &input[header + len..])
    }

    fn wrap(tag: u8, content: &[u8]) -> Vec<u8> {
        let mut output = vec![tag];
        if content.len() < 128 {
            output.push(content.len() as u8);
        } else {
            let bytes = content.len().to_be_bytes();
            let at = bytes.iter().position(|byte| *byte != 0).unwrap();
            output.push(128 | (bytes.len() - at) as u8);
            output.extend_from_slice(&bytes[at..]);
        }
        output.extend_from_slice(content);
        output
    }

    fn replace(input: &[u8], path: &[usize], replacement: &[u8]) -> Vec<u8> {
        if path.is_empty() {
            return replacement.to_vec();
        }
        let (mut content, trailing) = tlv(input);
        assert!(trailing.is_empty());
        let mut children = Vec::new();
        while !content.is_empty() {
            let (_, remaining) = tlv(content);
            let child_len = content.len() - remaining.len();
            children.push(content[..child_len].to_vec());
            content = remaining;
        }
        children[path[0]] = replace(&children[path[0]], &path[1..], replacement);
        wrap(input[0], &children.concat())
    }

    fn child<'a>(mut input: &'a [u8], path: &[usize]) -> &'a [u8] {
        for &index in path {
            let (mut content, trailing) = tlv(input);
            assert!(trailing.is_empty());
            for _ in 0..index {
                content = tlv(content).1;
            }
            let remaining = tlv(content).1;
            input = &content[..content.len() - remaining.len()];
        }
        input
    }

    #[test]
    fn nested_trailing_fields_and_nonminimal_lengths_are_rejected() {
        let f = fixture();
        let auth = authenticator(&f);
        let certificate = hex(&f["certificate"]["der_hex"]);
        for path in [&[][..], &[0], &[0, 4], &[0, 6], &[1]] {
            let original = child(&certificate, path);
            let mut content = tlv(original).0.to_vec();
            content.extend_from_slice(&[5, 0]);
            let malformed = replace(&certificate, path, &wrap(original[0], &content));
            assert!(verify(&auth, &malformed).is_err(), "trailing at {path:?}");

            let content = tlv(original).0;
            let bytes = content.len().to_be_bytes();
            let at = bytes.iter().position(|byte| *byte != 0).unwrap();
            let mut nonminimal = vec![original[0], 128 | (bytes.len() - at + 1) as u8, 0];
            nonminimal.extend_from_slice(&bytes[at..]);
            nonminimal.extend_from_slice(content);
            let malformed = replace(&certificate, path, &nonminimal);
            assert!(
                verify(&auth, &malformed).is_err(),
                "nonminimal length at {path:?}"
            );
        }
    }

    #[test]
    fn all_three_ed25519_algorithm_identifiers_require_absent_parameters() {
        let f = fixture();
        let auth = authenticator(&f);
        let certificate = hex(&f["certificate"]["der_hex"]);
        for path in [&[0, 2][..], &[0, 6, 0], &[1]] {
            let original = child(&certificate, path);
            let mut content = tlv(original).0.to_vec();
            content.extend_from_slice(&[5, 0]);
            let malformed = replace(&certificate, path, &wrap(0x30, &content));
            assert!(
                verify(&auth, &malformed).is_err(),
                "NULL parameters at {path:?}"
            );

            let mut wrong_oid = original.to_vec();
            *wrong_oid.last_mut().unwrap() ^= 1;
            let malformed = replace(&certificate, path, &wrong_oid);
            assert!(
                verify(&auth, &malformed).is_err(),
                "wrong algorithm at {path:?}"
            );
        }
    }

    #[test]
    fn bit_strings_require_exact_key_and_mac_lengths_and_no_unused_bits() {
        let f = fixture();
        let auth = authenticator(&f);
        let certificate = hex(&f["certificate"]["der_hex"]);
        for path in [&[0, 6, 1][..], &[2]] {
            let original = child(&certificate, path);
            let content = tlv(original).0;
            let short = wrap(3, &content[..content.len() - 1]);
            assert!(verify(&auth, &replace(&certificate, path, &short)).is_err());
            let mut long = content.to_vec();
            long.push(0);
            assert!(verify(&auth, &replace(&certificate, path, &wrap(3, &long))).is_err());
            let mut unused = content.to_vec();
            unused[0] = 1;
            *unused.last_mut().unwrap() &= !1;
            assert!(verify(&auth, &replace(&certificate, path, &wrap(3, &unused))).is_err());
        }
    }

    #[test]
    fn malformed_year_one_placeholder_is_not_accepted_as_arbitrary_time() {
        let f = fixture();
        let auth = authenticator(&f);
        let certificate = hex(&f["certificate"]["upstream_minimal_der_hex"]);
        for bad_time in [
            b"00010230000000Z".as_slice(),
            b"00010101000000+",
            b"not-a-time",
        ] {
            let malformed = replace(&certificate, &[0, 4, 0], &wrap(0x18, bad_time));
            assert!(verify(&auth, &malformed).is_err());
        }
        let wrong_tag = replace(&certificate, &[0, 4, 0], &wrap(0x04, b"00010101000000Z"));
        assert!(verify(&auth, &wrong_tag).is_err());
    }

    #[test]
    fn independent_sha256_and_sha384_certificate_verify_transcripts_are_accepted() {
        let f = fixture();
        let auth = authenticator(&f);
        let certificate = CertificateDer::from(hex(&f["certificate"]["der_hex"]));
        for flight in f["tls13"].as_array().unwrap() {
            let message = hex(&flight["certificate_verify_input_hex"]);
            let wire = hex(&flight["certificate_verify_message_hex"]);
            assert!(
                auth.verify_tls13_signature(&message, &certificate, &signed(&wire[4..]))
                    .is_ok(),
                "{}",
                flight["hash"]
            );
        }
    }

    #[test]
    fn certificate_verify_rejects_modified_transcript_context_and_signature() {
        let f = fixture();
        let auth = authenticator(&f);
        let certificate = CertificateDer::from(hex(&f["certificate"]["der_hex"]));
        for flight in f["tls13"].as_array().unwrap() {
            let message = hex(&flight["certificate_verify_input_hex"]);
            let wire = hex(&flight["certificate_verify_message_hex"]);
            let dss = signed(&wire[4..]);
            for at in [0, 64, message.len() - 1] {
                let mut tampered = message.clone();
                tampered[at] ^= 1;
                assert!(
                    auth.verify_tls13_signature(&tampered, &certificate, &dss)
                        .is_err()
                );
            }
            let mut signature = wire[4..].to_vec();
            *signature.last_mut().unwrap() ^= 1;
            assert!(
                auth.verify_tls13_signature(&message, &certificate, &signed(&signature))
                    .is_err()
            );
            assert!(
                auth.verify_tls13_signature(
                    &hex(&flight["transcript_hash_hex"]),
                    &certificate,
                    &dss
                )
                .is_err()
            );
        }
    }

    #[test]
    fn tls12_and_other_certificate_verify_algorithms_are_rejected() {
        let f = fixture();
        let auth = authenticator(&f);
        let certificate = CertificateDer::from(hex(&f["certificate"]["der_hex"]));
        let flight = &f["tls13"][0];
        let message = hex(&flight["certificate_verify_input_hex"]);
        let wire = hex(&flight["certificate_verify_message_hex"]);
        let dss = signed(&wire[4..]);
        assert!(
            auth.verify_tls12_signature(&message, &certificate, &dss)
                .is_err()
        );
        let mut other_algorithm = wire[4..].to_vec();
        other_algorithm[..2].copy_from_slice(&[0x04, 0x03]);
        assert!(
            auth.verify_tls13_signature(&message, &certificate, &signed(&other_algorithm))
                .is_err()
        );
        assert_eq!(auth.supported_verify_schemes(), [SignatureScheme::ED25519]);
        assert!(!auth.requires_raw_public_keys());
        assert!(auth.root_hint_subjects().is_none());
    }

    #[test]
    fn certificate_verify_never_accepts_an_unauthenticated_key() {
        let f = fixture();
        let mut key: [u8; 32] = hex(&f["certificate"]["auth_key_hex"]).try_into().unwrap();
        key[0] ^= 1;
        let auth = ServerAuthenticator::new(Zeroizing::new(key));
        let certificate = CertificateDer::from(hex(&f["certificate"]["der_hex"]));
        let flight = &f["tls13"][0];
        let wire = hex(&flight["certificate_verify_message_hex"]);
        assert!(
            auth.verify_tls13_signature(
                &hex(&flight["certificate_verify_input_hex"]),
                &certificate,
                &signed(&wire[4..])
            )
            .is_err()
        );
    }

    #[test]
    fn debug_redacts_authentication_key() {
        let f = fixture();
        assert_eq!(
            format!("{:?}", authenticator(&f)),
            "ServerAuthenticator { authentication_key: [REDACTED] }"
        );
    }

    // These are verifier/provider integration tests using stock rustls TLS.
    // The synthetic leaf's HMAC key is supplied by the fixture: no REALITY
    // ClientHello authentication, fingerprint or REALITY data channel is
    // claimed. A real TLS server signs CertificateVerify, sends Finished and
    // encrypts data; the client must complete all normal rustls checks.
    fn tls_peers(
        f: &Value,
        wrong_authentication_key: bool,
    ) -> (ClientConnection, ServerConnection) {
        let mut client_provider = default_provider();
        client_provider.kx_groups = vec![super::super::X25519_MLKEM768, kx_group::X25519];
        let mut key: [u8; 32] = hex(&f["certificate"]["auth_key_hex"]).try_into().unwrap();
        if wrong_authentication_key {
            key[0] ^= 1;
        }
        let client_config = ClientConfig::builder_with_provider(Arc::new(client_provider))
            .with_protocol_versions(&[&TLS13])
            .unwrap()
            .dangerous()
            .with_custom_certificate_verifier(Arc::new(ServerAuthenticator::new(Zeroizing::new(
                key,
            ))))
            .with_no_client_auth();
        let mut server_provider = default_provider();
        server_provider.kx_groups = vec![kx_group::X25519];
        let mut server_config = ServerConfig::builder_with_provider(Arc::new(server_provider))
            .with_protocol_versions(&[&TLS13])
            .unwrap()
            .with_no_client_auth()
            .with_single_cert(
                vec![CertificateDer::from(hex(&f["certificate"]["der_hex"]))],
                PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(hex(
                    &f["certificate"]["ed25519_pkcs8_der_hex"],
                ))),
            )
            .unwrap();
        server_config.send_tls13_tickets = 0;
        (
            ClientConnection::new(
                Arc::new(client_config),
                ServerName::try_from("reality.test").unwrap(),
            )
            .unwrap(),
            ServerConnection::new(Arc::new(server_config)).unwrap(),
        )
    }

    fn client_to_server(
        client: &mut ClientConnection,
        server: &mut ServerConnection,
    ) -> Result<IoState, Error> {
        let mut wire = Vec::new();
        client.write_tls(&mut wire).unwrap();
        assert!(!wire.is_empty());
        server.read_tls(&mut Cursor::new(wire)).unwrap();
        server.process_new_packets()
    }

    fn server_to_client(
        server: &mut ServerConnection,
        client: &mut ClientConnection,
    ) -> Result<IoState, Error> {
        let mut wire = Vec::new();
        server.write_tls(&mut wire).unwrap();
        assert!(!wire.is_empty());
        client.read_tls(&mut Cursor::new(wire)).unwrap();
        client.process_new_packets()
    }

    fn take<'a>(input: &mut &'a [u8], len: usize) -> &'a [u8] {
        let (value, rest) = input.split_at(len);
        *input = rest;
        value
    }

    fn vector16<'a>(input: &mut &'a [u8]) -> &'a [u8] {
        let length = take(input, 2);
        take(
            input,
            usize::from(u16::from_be_bytes([length[0], length[1]])),
        )
    }

    fn assert_owned_hybrid_and_classical_shares(wire: &[u8]) {
        // Inspect the actual stock-rustls wire flight. Negotiating X25519 alone
        // would not prove that rustls exercised our hybrid component adapter.
        assert_eq!(wire[0], 22);
        assert_eq!(
            usize::from(u16::from_be_bytes([wire[3], wire[4]])),
            wire.len() - 5
        );
        assert_eq!(wire[5], 1);
        let mut body = &wire[9..];
        take(&mut body, 34); // legacy version and random
        let id_len = usize::from(take(&mut body, 1)[0]);
        take(&mut body, id_len);
        vector16(&mut body); // cipher suites
        let compression_len = usize::from(take(&mut body, 1)[0]);
        take(&mut body, compression_len);
        let mut extensions = vector16(&mut body);
        assert!(body.is_empty());
        let mut found = false;
        while !extensions.is_empty() {
            let kind = take(&mut extensions, 2);
            let mut value = vector16(&mut extensions);
            if kind == [0, 51] {
                let mut shares = vector16(&mut value);
                assert!(value.is_empty());
                assert_eq!(take(&mut shares, 2), [0x11, 0xec]);
                let hybrid = vector16(&mut shares);
                assert_eq!(hybrid.len(), 1216);
                assert_eq!(take(&mut shares, 2), [0, 0x1d]);
                let classical = vector16(&mut shares);
                assert_eq!(classical, &hybrid[1184..]);
                assert!(shares.is_empty());
                found = true;
            }
        }
        assert!(
            found,
            "owned hybrid and identical classical shares must be sent"
        );
    }

    #[test]
    fn rustls_verifier_and_classical_hybrid_component_complete_tls13_data_and_close() {
        let f = fixture();
        let (mut client, mut server) = tls_peers(&f, false);
        let mut first_flight = Vec::new();
        client.write_tls(&mut first_flight).unwrap();
        assert_owned_hybrid_and_classical_shares(&first_flight);
        server.read_tls(&mut Cursor::new(first_flight)).unwrap();
        server.process_new_packets().unwrap();
        for _ in 0..8 {
            if client.wants_write() {
                client_to_server(&mut client, &mut server).unwrap();
            }
            if server.wants_write() {
                server_to_client(&mut server, &mut client).unwrap();
            }
            if !client.is_handshaking() && !server.is_handshaking() {
                break;
            }
        }
        assert!(!client.is_handshaking() && !server.is_handshaking());
        assert_eq!(client.protocol_version(), Some(ProtocolVersion::TLSv1_3));
        assert_eq!(
            client.negotiated_key_exchange_group().unwrap().name(),
            NamedGroup::X25519
        );

        let request = b"independent verifier integration request";
        client.writer().write_all(request).unwrap();
        client_to_server(&mut client, &mut server).unwrap();
        let mut received = vec![0; request.len()];
        server.reader().read_exact(&mut received).unwrap();
        assert_eq!(received, request);

        let response = b"independent verifier integration response";
        server.writer().write_all(response).unwrap();
        server_to_client(&mut server, &mut client).unwrap();
        let mut received = vec![0; response.len()];
        client.reader().read_exact(&mut received).unwrap();
        assert_eq!(received, response);

        client.send_close_notify();
        assert!(
            client_to_server(&mut client, &mut server)
                .unwrap()
                .peer_has_closed()
        );
        assert_eq!(server.reader().read(&mut [0; 1]).unwrap(), 0);
        server.send_close_notify();
        assert!(
            server_to_client(&mut server, &mut client)
                .unwrap()
                .peer_has_closed()
        );
        assert_eq!(client.reader().read(&mut [0; 1]).unwrap(), 0);
    }

    #[test]
    fn rustls_rejects_wrong_reality_authentication_before_plaintext() {
        let f = fixture();
        let (mut client, mut server) = tls_peers(&f, true);
        client_to_server(&mut client, &mut server).unwrap();
        server
            .writer()
            .write_all(b"must not reach the client")
            .unwrap();
        assert!(matches!(
            server_to_client(&mut server, &mut client),
            Err(Error::InvalidCertificate(CertificateError::BadSignature))
        ));
        assert!(client.is_handshaking());
        assert!(client.reader().read(&mut [0; 1]).is_err());
    }

    #[test]
    fn rustls_rejects_tampered_encrypted_server_flight_before_plaintext() {
        let f = fixture();
        let (mut client, mut server) = tls_peers(&f, false);
        client_to_server(&mut client, &mut server).unwrap();
        server
            .writer()
            .write_all(b"must not reach the client")
            .unwrap();
        let mut wire = Vec::new();
        server.write_tls(&mut wire).unwrap();
        let mut offset = 0;
        let mut tampered = false;
        for _ in 0..16 {
            assert!(offset + 5 <= wire.len());
            let len = usize::from(u16::from_be_bytes([wire[offset + 3], wire[offset + 4]]));
            assert!(offset + 5 + len <= wire.len());
            if wire[offset] == 23 {
                assert!(len > 16);
                wire[offset + 5] ^= 1;
                tampered = true;
                break;
            }
            offset += 5 + len;
        }
        assert!(tampered, "the test must corrupt an encrypted TLS record");
        client.read_tls(&mut Cursor::new(wire)).unwrap();
        assert!(matches!(
            client.process_new_packets(),
            Err(Error::DecryptError)
        ));
        assert!(client.is_handshaking());
        assert!(client.reader().read(&mut [0; 1]).is_err());
    }
}
