use super::*;
use serde_json::Value;
use tokio_rustls::rustls::{NamedGroup, ProtocolVersion};

fn fixture() -> Value {
    serde_json::from_str(include_str!("../../tests/fixtures/reality_auth.json")).unwrap()
}

fn hex(value: &Value) -> Vec<u8> {
    let text = value.as_str().unwrap();
    assert!(text.len().is_multiple_of(2));
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap())
        .collect()
}

fn inputs(case: &Value, vectors: &Value) -> (ClientKeys, ClientParameters, u32) {
    let key_exchange = kx::HybridKeyExchange::from_seeds(
        &hex(&case["client_private_key_hex"]).try_into().unwrap(),
        &hex(&vectors["hybrid"]["mlkem_seed_hex"])
            .try_into()
            .unwrap(),
    );
    let keys = ClientKeys {
        key_exchange,
        random: hex(&case["client_random_hex"]).try_into().unwrap(),
    };
    let parameters = ClientParameters::new(
        case["server_name"].as_str().unwrap(),
        hex(&case["server_public_key_hex"]).try_into().unwrap(),
        &hex(&case["short_id_hex"]),
        serde_json::from_value(case["client_version"].clone()).unwrap(),
    )
    .unwrap();
    (keys, parameters, case["unix_time"].as_u64().unwrap() as u32)
}

fn authenticated(vectors: &Value, case_index: usize) -> AuthenticatedClientHello {
    let case = &vectors["cases"][case_index];
    let (keys, parameters, time) = inputs(case, vectors);
    keys.authenticate(
        hex(&case["client_hello_zero_session_id_hex"]),
        &parameters,
        time,
    )
    .unwrap()
}

fn extension_offset(hello: &[u8]) -> usize {
    let cipher_length = u16::from_be_bytes([hello[71], hello[72]]) as usize;
    let compression_length_offset = 73 + cipher_length;
    compression_length_offset + 1 + hello[compression_length_offset] as usize
}

fn set_handshake_length(bytes: &mut [u8]) {
    let length = ((bytes.len() - 4) as u32).to_be_bytes();
    bytes[1..4].copy_from_slice(&length[1..]);
}

fn rewrite_extension(hello: &[u8], kind: u16, replacement: Option<&[u8]>) -> Vec<u8> {
    let position = extension_offset(hello);
    let mut entries = Vec::new();
    let mut offset = position + 2;
    let mut found = false;
    while offset < hello.len() {
        let tag = u16::from_be_bytes([hello[offset], hello[offset + 1]]);
        let length = u16::from_be_bytes([hello[offset + 2], hello[offset + 3]]) as usize;
        if tag == kind {
            found = true;
            if let Some(value) = replacement {
                entries.extend(kind.to_be_bytes());
                entries.extend((value.len() as u16).to_be_bytes());
                entries.extend(value);
            }
        } else {
            entries.extend(&hello[offset..offset + 4 + length]);
        }
        offset += 4 + length;
    }
    if !found && let Some(value) = replacement {
        entries.extend(kind.to_be_bytes());
        entries.extend((value.len() as u16).to_be_bytes());
        entries.extend(value);
    }
    let mut result = hello[..position].to_vec();
    result.extend((entries.len() as u16).to_be_bytes());
    result.extend(entries);
    set_handshake_length(&mut result);
    result
}

#[test]
fn authentication_matches_independent_python_vectors_byte_for_byte() {
    let vectors = fixture();
    assert_eq!(vectors["public_test_material"], true);
    for case in vectors["cases"].as_array().unwrap() {
        let (keys, parameters, time) = inputs(case, &vectors);
        assert_eq!(
            keys.x25519_public_key(),
            hex(&case["client_public_key_hex"])
        );
        assert_eq!(
            keys.hybrid_public_key(),
            hex(&vectors["hybrid"]["client_key_share_hex"])
        );
        let shared = keys
            .key_exchange
            .classical_secret(&parameters.public_key)
            .unwrap();
        assert_eq!(shared.as_slice(), hex(&case["shared_secret_hex"]));
        let key = derive_authentication_key(&shared, &keys.random).unwrap();
        assert_eq!(key.as_slice(), hex(&case["auth_key_hex"]));
        let raw = hex(&case["client_hello_zero_session_id_hex"]);
        let id = seal_session_id(&key, &keys.random, &parameters, time, &raw).unwrap();
        assert_eq!(id.as_slice(), hex(&case["session_id_hex"]));
        if !case["modern_reality_share_structure"].as_bool().unwrap() {
            assert!(keys.authenticate(raw, &parameters, time).is_err());
            continue;
        }
        let sealed = keys.authenticate(raw, &parameters, time).unwrap();
        assert_eq!(
            sealed.handshake_bytes(),
            hex(&case["authenticated_client_hello_hex"])
        );
        assert_eq!(
            digest::digest(&digest::SHA256, sealed.handshake_bytes()).as_ref(),
            hex(&case["authenticated_client_hello_sha256_hex"])
        );
        assert_eq!(
            digest::digest(&digest::SHA384, sealed.handshake_bytes()).as_ref(),
            hex(&case["authenticated_client_hello_sha384_hex"])
        );
    }
}

#[test]
fn real_mlkem_ciphertext_matches_independent_openssl_shared_secret() {
    let vectors = fixture();
    let (keys, _, _) = inputs(&vectors["cases"][1], &vectors);
    let result = keys
        .key_exchange
        .finish(
            NamedGroup::X25519MLKEM768,
            &hex(&vectors["hybrid"]["server_key_share_hex"]),
        )
        .unwrap();
    assert_eq!(
        result.secret_bytes(),
        hex(&vectors["hybrid"]["tls_shared_secret_hex"])
    );
}

#[test]
fn corrupted_mlkem_ciphertext_requires_later_finished_rejection() {
    let vectors = fixture();
    let (keys, _, _) = inputs(&vectors["cases"][1], &vectors);
    let mut share = hex(&vectors["hybrid"]["server_key_share_hex"]);
    share[0] ^= 0x80;
    let result = keys
        .key_exchange
        .finish(NamedGroup::X25519MLKEM768, &share)
        .unwrap();
    assert_ne!(
        &result.secret_bytes()[..32],
        hex(&vectors["hybrid"]["mlkem_shared_secret_hex"])
    );
    assert_eq!(
        &result.secret_bytes()[32..],
        hex(&vectors["hybrid"]["tls_x25519_shared_secret_hex"])
    );
}

#[test]
fn hybrid_key_share_lengths_and_noncontributory_peers_fail() {
    let vectors = fixture();
    let peer = hex(&vectors["hybrid"]["server_key_share_hex"]);
    for length in [0, 31, 32, 1087, 1088, 1119, 1121, 1216, 16384] {
        let (keys, _, _) = inputs(&vectors["cases"][1], &vectors);
        assert!(
            keys.key_exchange
                .finish(NamedGroup::X25519MLKEM768, &vec![7; length])
                .is_err()
        );
    }
    for group in [NamedGroup::X25519, NamedGroup::X25519MLKEM768] {
        for low_order in [[0; 32], {
            let mut p = [0; 32];
            p[0] = 1;
            p
        }] {
            let (keys, _, _) = inputs(&vectors["cases"][1], &vectors);
            let mut share = if group == NamedGroup::X25519 {
                Vec::new()
            } else {
                peer[..1088].to_vec()
            };
            share.extend(low_order);
            assert!(keys.key_exchange.finish(group, &share).is_err());
        }
    }
    let (keys, _, _) = inputs(&vectors["cases"][1], &vectors);
    assert!(
        keys.key_exchange
            .finish(NamedGroup::secp256r1, &peer)
            .is_err()
    );
}

#[test]
fn key_group_advertises_only_tls13_and_retains_the_classical_owner() {
    use tokio_rustls::rustls::crypto::ActiveKeyExchange;
    assert_eq!(X25519_MLKEM768.name(), NamedGroup::X25519MLKEM768);
    assert!(X25519_MLKEM768.usable_for_version(ProtocolVersion::TLSv1_3));
    assert!(!X25519_MLKEM768.usable_for_version(ProtocolVersion::TLSv1_2));
    let vectors = fixture();
    let (keys, _, _) = inputs(&vectors["cases"][1], &vectors);
    let active = Box::new(keys.key_exchange);
    let (group, classical) = active.hybrid_component().unwrap();
    assert_eq!(group, NamedGroup::X25519);
    assert_eq!(classical, &active.pub_key()[1184..]);
    let result = active
        .complete_hybrid_component(&hex(&vectors["hybrid"]["tls_server_public_key_hex"]))
        .unwrap();
    assert_eq!(
        result.secret_bytes(),
        hex(&vectors["hybrid"]["tls_x25519_shared_secret_hex"])
    );
    let fresh = X25519_MLKEM768.start().unwrap();
    assert_eq!(fresh.pub_key().len(), 1216);
    assert!(X25519_MLKEM768.start_and_complete(fresh.pub_key()).is_err());
}

#[test]
fn fresh_key_owners_do_not_reuse_random_or_either_share() {
    let a = ClientKeys::generate().unwrap();
    let b = ClientKeys::generate().unwrap();
    assert_ne!(a.client_random(), b.client_random());
    assert_ne!(a.x25519_public_key(), b.x25519_public_key());
    assert_ne!(
        &a.hybrid_public_key()[..1184],
        &b.hybrid_public_key()[..1184]
    );
}

#[test]
fn every_truncated_client_hello_is_rejected_without_panic() {
    let vectors = fixture();
    let case = &vectors["cases"][1];
    let raw = hex(&case["client_hello_zero_session_id_hex"]);
    // Reuse a borrowed key only for syntax checks, never for authentication.
    let (keys, parameters, _) = inputs(case, &vectors);
    for end in 0..raw.len() {
        assert!(
            hello::client(&raw[..end], &keys.random, &keys.key_exchange, &parameters).is_err(),
            "prefix {end}"
        );
    }
    for length in [raw.len() + 1, 16384, 16385, 65536] {
        let mut input = raw.clone();
        input.resize(length, 0);
        assert!(hello::client(&input, &keys.random, &keys.key_exchange, &parameters).is_err());
    }
}

#[test]
fn client_hello_requires_owned_random_keys_name_and_zero_session_id() {
    let vectors = fixture();
    let case = &vectors["cases"][1];
    let raw = hex(&case["client_hello_zero_session_id_hex"]);
    let (keys, parameters, _) = inputs(case, &vectors);
    for index in [0, 1, 4, 6, 37, 38, 39, 70, raw.len() - 1] {
        let mut input = raw.clone();
        input[index] ^= 1;
        assert!(
            hello::client(&input, &keys.random, &keys.key_exchange, &parameters).is_err(),
            "offset {index}"
        );
    }
    let other = ClientKeys::generate().unwrap();
    assert!(hello::client(&raw, &keys.random, &other.key_exchange, &parameters).is_err());
    let wrong_name =
        ClientParameters::new("other.test", parameters.public_key, &[], [1, 2, 3]).unwrap();
    assert!(hello::client(&raw, &keys.random, &keys.key_exchange, &wrong_name).is_err());
    for name in [
        "",
        "127.0.0.1",
        "::1",
        "bad name",
        "https://reality.test",
        "reality.test.",
    ] {
        assert!(ClientParameters::new(name, [9; 32], &[], [1, 2, 3]).is_err());
    }
    let mut dotted_sni = vec![0, 16, 0, 0, 13];
    dotted_sni.extend(b"reality.test.");
    let input = rewrite_extension(&raw, 0, Some(&dotted_sni));
    assert!(hello::client(&input, &keys.random, &keys.key_exchange, &parameters).is_err());
    assert!(ClientParameters::new("reality.test", [9; 32], &[0; 9], [1, 2, 3]).is_err());
    for n in 0..=8 {
        assert!(ClientParameters::new("reality.test", [9; 32], &vec![1; n], [1, 2, 3]).is_ok());
    }
}

#[test]
fn client_hello_extension_semantics_never_silently_downgrade() {
    let vectors = fixture();
    let case = &vectors["cases"][1];
    let raw = hex(&case["client_hello_zero_session_id_hex"]);
    let (keys, parameters, _) = inputs(case, &vectors);
    let check = |input: &[u8]| hello::client(input, &keys.random, &keys.key_exchange, &parameters);
    for kind in [0, 10, 13, 43, 51] {
        assert!(check(&rewrite_extension(&raw, kind, None)).is_err());
        assert!(check(&rewrite_extension(&raw, kind, Some(&[]))).is_err());
    }
    for kind in [41, 42, 44, 0xfd00, 0xfe0d] {
        assert!(check(&rewrite_extension(&raw, kind, Some(&[0]))).is_err());
    }
    assert!(check(&rewrite_extension(&raw, 43, Some(&[2, 3, 3]))).is_err());
    assert!(check(&rewrite_extension(&raw, 13, Some(&[0, 2, 4, 3]))).is_err());
    assert!(check(&rewrite_extension(&raw, 10, Some(&[0, 2, 0, 29]))).is_err());
    let mut duplicate = raw.clone();
    duplicate.extend([0, 43, 0, 3, 2, 3, 4]);
    let offset = extension_offset(&duplicate);
    let length = ((duplicate.len() - offset - 2) as u16).to_be_bytes();
    duplicate[offset..offset + 2].copy_from_slice(&length);
    set_handshake_length(&mut duplicate);
    assert!(check(&duplicate).is_err());
}

#[test]
fn nested_client_hello_vectors_reject_truncation_with_correct_outer_lengths() {
    let vectors = fixture();
    let case = &vectors["cases"][1];
    let raw = hex(&case["client_hello_zero_session_id_hex"]);
    let (keys, parameters, _) = inputs(case, &vectors);
    let mut offset = extension_offset(&raw) + 2;
    while offset < raw.len() {
        let kind = u16::from_be_bytes([raw[offset], raw[offset + 1]]);
        let length = u16::from_be_bytes([raw[offset + 2], raw[offset + 3]]) as usize;
        if [0, 10, 13, 43, 51].contains(&kind) {
            let value = &raw[offset + 4..offset + 4 + length];
            for end in 0..value.len() {
                // Repair the handshake and extension lengths, leaving the
                // nested SNI/group/signature/version/share length truncated.
                let input = rewrite_extension(&raw, kind, Some(&value[..end]));
                assert!(
                    hello::client(&input, &keys.random, &keys.key_exchange, &parameters).is_err(),
                    "extension {kind}, nested prefix {end}"
                );
            }
        }
        offset += 4 + length;
    }
}

#[test]
fn grease_key_shares_must_follow_the_unique_supported_group_order() {
    let vectors = fixture();
    let case = &vectors["cases"][2];
    let raw = hex(&case["client_hello_zero_session_id_hex"]);
    let (keys, parameters, _) = inputs(case, &vectors);
    let mut shares = vec![0x0a, 0x0a, 0, 1, 0];
    for (group, key) in [
        (0x11ecu16, keys.hybrid_public_key()),
        (0x001d, keys.x25519_public_key()),
    ] {
        shares.extend(group.to_be_bytes());
        shares.extend((key.len() as u16).to_be_bytes());
        shares.extend(key);
    }
    let mut value = (shares.len() as u16).to_be_bytes().to_vec();
    value.extend(shares);
    let with_grease = rewrite_extension(&raw, 51, Some(&value));
    let check_groups = |groups: &[u16]| {
        let mut value = ((groups.len() * 2) as u16).to_be_bytes().to_vec();
        for group in groups {
            value.extend(group.to_be_bytes());
        }
        let input = rewrite_extension(&with_grease, 10, Some(&value));
        hello::client(&input, &keys.random, &keys.key_exchange, &parameters)
    };
    assert!(check_groups(&[0x0a0a, 0x11ec, 0x001d]).is_ok());
    assert!(check_groups(&[0x11ec, 0x001d]).is_err());
    assert!(check_groups(&[0x11ec, 0x0a0a, 0x001d]).is_err());
    assert!(check_groups(&[0x0a0a, 0x001d, 0x11ec]).is_err());
    assert!(check_groups(&[0x0a0a, 0x11ec, 0x11ec, 0x001d]).is_err());
    let with_groups = rewrite_extension(
        &with_grease,
        10,
        Some(&[0, 6, 0x0a, 0x0a, 0x11, 0xec, 0, 0x1d]),
    );
    // GREASE is opaque but still obeys key_exchange<1..2^16-1>.
    // Remove its sole byte and repair the surrounding vector lengths.
    let mut empty_grease = value.clone();
    empty_grease[4..6].copy_from_slice(&[0, 0]);
    empty_grease.remove(6);
    let length = ((empty_grease.len() - 2) as u16).to_be_bytes();
    empty_grease[..2].copy_from_slice(&length);
    let input = rewrite_extension(&with_groups, 51, Some(&empty_grease));
    assert!(hello::client(&input, &keys.random, &keys.key_exchange, &parameters).is_err());
}

#[test]
fn optional_classical_share_must_follow_hybrid_and_use_same_key() {
    let vectors = fixture();
    let case = &vectors["cases"][2];
    let raw = hex(&case["client_hello_zero_session_id_hex"]);
    let (keys, parameters, _) = inputs(case, &vectors);
    let entry = |group: u16, key: &[u8]| {
        let mut bytes = group.to_be_bytes().to_vec();
        bytes.extend((key.len() as u16).to_be_bytes());
        bytes.extend(key);
        bytes
    };
    let hybrid = entry(0x11ec, keys.hybrid_public_key());
    let classical = entry(0x001d, keys.x25519_public_key());
    let wrong_classical = entry(0x001d, &[5; 32]);
    for shares in [
        [classical.as_slice(), hybrid.as_slice()].concat(),
        [hybrid.as_slice(), hybrid.as_slice()].concat(),
        [hybrid.as_slice(), wrong_classical.as_slice()].concat(),
        classical,
        entry(23, &[4; 65]),
    ] {
        let mut data = (shares.len() as u16).to_be_bytes().to_vec();
        data.extend(shares);
        let input = rewrite_extension(&raw, 51, Some(&data));
        assert!(hello::client(&input, &keys.random, &keys.key_exchange, &parameters).is_err());
    }
}

#[test]
fn all_aad_bytes_are_authenticated_and_records_are_not_in_the_transcript() {
    let vectors = fixture();
    let case = &vectors["cases"][1];
    let (keys, parameters, time) = inputs(case, &vectors);
    let raw = hex(&case["client_hello_zero_session_id_hex"]);
    let expected = hex(&case["session_id_hex"]);
    let key: [u8; 32] = hex(&case["auth_key_hex"]).try_into().unwrap();
    for offset in 0..raw.len() {
        let mut changed = raw.clone();
        changed[offset] ^= 1;
        let actual = seal_session_id(&key, &keys.random, &parameters, time, &changed).unwrap();
        assert_ne!(
            actual.as_slice(),
            expected,
            "unauthenticated AAD byte {offset}"
        );
    }
    let mut record = vec![22, 3, 1];
    record.extend((raw.len() as u16).to_be_bytes());
    record.extend(raw);
    assert!(keys.authenticate(record, &parameters, time).is_err());
}

#[test]
fn server_hello_matches_independent_sha256_and_sha384_checkpoints() {
    let vectors = fixture();
    for vector in vectors["tls13"].as_array().unwrap() {
        let hello = authenticated(&vectors, 1);
        let secrets = hello
            .accept_server_hello(&hex(&vector["server_hello_hex"]))
            .unwrap();
        assert_eq!(
            secrets.shared_secret(),
            hex(&vector["tls_shared_secret_hex"])
        );
        assert_eq!(
            secrets.transcript_hash().as_ref(),
            hex(&vector["transcript_hash_after_server_hello_hex"])
        );
    }
}

#[test]
fn server_hello_rejects_truncation_echo_hrr_tls12_and_unoffered_cipher() {
    let vectors = fixture();
    let raw = hex(&vectors["tls13"][0]["server_hello_hex"]);
    let hello = authenticated(&vectors, 1);
    for end in 0..raw.len() {
        assert!(hello::server(&raw[..end], &hello.bytes, &hello.offer).is_err());
        if end >= 4 {
            let mut nested = raw[..end].to_vec();
            set_handshake_length(&mut nested);
            if end >= 76 {
                nested[74..76].copy_from_slice(&((end - 76) as u16).to_be_bytes());
            }
            assert!(hello::server(&nested, &hello.bytes, &hello.offer).is_err());
        }
    }
    for index in [0, 1, 4, 38, 39, 70, 71, 73, 79] {
        let mut changed = raw.clone();
        changed[index] ^= 0x80;
        assert!(
            hello::server(&changed, &hello.bytes, &hello.offer).is_err(),
            "server offset {index}"
        );
    }
    let mut hrr = raw.clone();
    hrr[6..38].copy_from_slice(&[
        0xcf, 0x21, 0xad, 0x74, 0xe5, 0x9a, 0x61, 0x11, 0xbe, 0x1d, 0x8c, 0x02, 0x1e, 0x65, 0xb8,
        0x91, 0xc2, 0xa2, 0x11, 0x16, 0x7a, 0xbb, 0x8c, 0x5e, 0x07, 0x9e, 0x09, 0xe2, 0xc8, 0xa8,
        0x33, 0x9c,
    ]);
    assert!(hello.accept_server_hello(&hrr).is_err());
}

#[test]
fn ordinary_low_order_server_authentication_key_is_rejected() {
    let vectors = fixture();
    let case = &vectors["cases"][1];
    let (keys, mut parameters, time) = inputs(case, &vectors);
    parameters.public_key = [0; 32];
    assert!(
        keys.authenticate(
            hex(&case["client_hello_zero_session_id_hex"]),
            &parameters,
            time
        )
        .is_err()
    );
}
