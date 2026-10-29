#!/usr/bin/env python3
"""Reproduce public REALITY/TLS 1.3 primitives independently of Swirl Rust.

Every private key, nonce, timestamp and ciphertext here is PUBLIC TEST MATERIAL.
This file never opens a network connection and must not be used as a client.
The small ClientHellos are protocol fixtures, not browser fingerprints or proof
of a successful REALITY/Vision connection. The classical-only case exercises
the auth primitive; the pinned modern server requires a hybrid key share.

Protocol behavior was read from the primary sources recorded in the JSON, then
independently expressed using Python's standard library and cryptography's
OpenSSL-backed primitives. No source from Xray/REALITY is incorporated.

Run with cryptography==50.0.2:
    python tools/tests/generate_reality_vectors.py --check
Omit --check to regenerate the checked-in JSON. Generation is deterministic:
the ML-KEM seed and one genuine OpenSSL-generated encapsulation ciphertext are
fixed inputs, and its expected shared secret is independently decapsulated.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import sys
import warnings

from cryptography import x509
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, mlkem, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF, HKDFExpand
from cryptography.utils import CryptographyDeprecationWarning
from cryptography.x509.oid import NameOID


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "core/crates/swirl-transport/tests/fixtures/reality_auth.json"
)
XRAY_REF = "92ccc939aaf4f8965f369cf0b142e005aeaa11d5"
REALITY_REF = "83f621788ca88b83179810b12baa7ae518aacb83"
SERVER_NAME = "reality.test"
CLIENT_PRIVATE = bytes(range(1, 33))
REALITY_SERVER_PRIVATE = bytes(range(65, 97))
TLS_SERVER_PRIVATE = bytes(range(33, 65))
CLIENT_RANDOM = bytes(range(160, 192))
MLKEM_SEED = bytes(range(128, 192))
ED25519_SEED = bytes(range(192, 224))
CLIENT_VERSION = bytes([26, 10, 19])
UNIX_TIME = 1792368000
SHORT_ID = bytes.fromhex("0102030405060708")

# Generated ONCE by MLKEM768PrivateKey.from_seed_bytes(MLKEM_SEED).public_key()
# .encapsulate() in cryptography 50.0.2. This is an immutable public INPUT to the
# decapsulation fixture; no deterministic or weakened runtime RNG is installed.
MLKEM_CIPHERTEXT = bytes.fromhex(
    "1270d039744f23fc3f653d731c4300959e0226cd419fd72312570c7f58855486d4d05c8e589d049b1df0a7bf607f1dcce0b8ae3f6acac6d0e51c65030826f04d"
    "32b723069dde3dd36a77f7051cdc1ee84117bd2cf7068806272d86cdd75242a8ab5b06878b5a51859203f9fd3d6c09eff1e95b818e6eda2fa9a841cc5dd8f1e62"
    "b7eddf63036fe96fe911996b0d366404c640ab3abe7c90345a447a702488e652108a4dfaf457b13b37dfec463c63adf77be217f4162eb44cf418e36d5430c2010"
    "f92d36e13ccef547d0a7b22c9ee82a5f9b845be572156bc10ea0957ed05619e98861f5b1601671adba7ab1ef4baf1a0a7c5cd1e17b1cecaa97d7e766461b7480"
    "fac11e67610efdf658475563130e764479e5b1b4e8b496edf4d16c7246d8101b93c9f312af157cb0092d3bac606318acecfdbddcd6f1e625f0aec535d4efb37ac"
    "1bb7741faebafaac08a78c8511d07350be69386c2678c7c7bd421956a2c6a13ea85504d42796f36c1d9a26c58497c136cacce003a04c0a1482ecadada36898f623"
    "bcc7bd4480fd33041821cd73e57784d43f0f18cb06bf66b69396bd93579b9e06b36884643286c5a0ebfebdc1b3291edbd65b2ca58eeee199eb11f558050521351"
    "b0859cab1bb3d4e3f373ebc6a57d975127823fab53f8a63d01af7f24e80b8db30ccb51531f040a42cee5c53fdf672cbf61daf25b2a7fbb5b23940bc716171cc749"
    "f4b26b4f8305fdec6361dc2c4a2108494f74e33e73a4af33481df7f0d1d6a3b16ab781db0249c59592ff80b153989097f87eebc8264bcbd403f7130b913d433e"
    "bc85e91b76383081cbce91cb7958bd2c68364e3425afc923f3f9ed7037253ce0c77dd01ad8b030713f63f1ccf0e787134748bc615a6e97d9db7fd4bac424de61e4"
    "312eb5ff6b7ef2b80a4cb18659e86640aa0d0b5ed7ef60bc10d544aeb442423416b67179ee231edf3c9dcb0f325e04b13deca7652fc134d2f588bf3980c2646a6"
    "eab975bf9c2bd38bb423f3be3495e08669a6c9e6acf4b21a0e299f1258f7a9cf6a8fc1a105386c997733f4b10b4e46ead801507a4e78ad5eaee993cc59745227f6"
    "14ac71616e5d897d9c998d580689996a6ebc4ee785cc131e9bb3d57452980184560d7a82e6c362715fe4aa61044353c80a2cabbf89df4db632a6a80e9648d7e4a2"
    "1586319754fe9fed540597c2f147fe01ccbd7f10a1ebecf33654424d507e41d6071bccc64c51deb3d31ea673b47321804adf15abfa02a12274b159a02a6d365d251"
    "c05387a51616213c83016ee97afec332e7f8b7a76179618ba506faaaae24a42f382d1b5ac20c53bdcdb801a545fd250af7b8c840ca76bf11c62bd43c993639e32db"
    "8845c866f83efde367418bb220fa54c93701fb0d9f583cc980fc67098de0230926e7454a0e2b888ba590d16f87fb76677fe086f3ca6f96acc98239e3a84eaa7e7916a"
    "96451b87f433613a9a09e69da3a71476290dd869d3d971022fe23bf5dae61dd20e4ffac9c2501ff6c25268f1a117d51c8534fa"
)
ENCAPSULATED_SECRET = bytes.fromhex(
    "4c0f34393ffbc55e74f5f9868cbc42ea226bb0be10d6bc97e0b8929749a69dc8"
)


def vector(data: bytes, width: int = 2) -> bytes:
    return len(data).to_bytes(width, "big") + data


def handshake(kind: int, body: bytes) -> bytes:
    return bytes([kind]) + vector(body, 3)


def extension(kind: int, body: bytes) -> bytes:
    return kind.to_bytes(2, "big") + vector(body)


def client_hello(shares: list[tuple[int, bytes]]) -> bytes:
    """A full handshake message; its TLS record header is deliberately absent."""
    name = b"\x00" + vector(SERVER_NAME.encode("ascii"))
    groups = b"".join(group.to_bytes(2, "big") for group, _ in shares)
    encoded_shares = b"".join(
        group.to_bytes(2, "big") + vector(key) for group, key in shares
    )
    extensions = (
        extension(0, vector(name))
        + extension(10, vector(groups))
        + extension(13, vector(b"\x08\x07"))  # Ed25519 CertificateVerify.
        + extension(43, vector(b"\x03\x04", 1))  # TLS 1.3 only.
        + extension(51, vector(encoded_shares))
    )
    return handshake(
        1,
        b"\x03\x03"
        + CLIENT_RANDOM
        + vector(bytes(32), 1)
        + vector(b"\x13\x01\x13\x02")
        + vector(b"\x00", 1)
        + vector(extensions),
    )


def make_auth_case(name: str, shares: list[tuple[int, bytes]]) -> dict:
    client = x25519.X25519PrivateKey.from_private_bytes(CLIENT_PRIVATE)
    server = x25519.X25519PrivateKey.from_private_bytes(REALITY_SERVER_PRIVATE)
    shared = client.exchange(server.public_key())
    assert shared == server.exchange(client.public_key())
    auth_key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=CLIENT_RANDOM[:20], info=b"REALITY"
    ).derive(shared)
    plaintext = CLIENT_VERSION + b"\x00" + UNIX_TIME.to_bytes(4, "big") + SHORT_ID
    aad = client_hello(shares)
    assert aad[38] == 32 and aad[39:71] == bytes(32)
    session_id = AESGCM(auth_key).encrypt(CLIENT_RANDOM[20:], plaintext, aad)
    assert len(session_id) == 32
    assert AESGCM(auth_key).decrypt(CLIENT_RANDOM[20:], session_id, aad) == plaintext
    sealed = aad[:39] + session_id + aad[71:]
    return {
        "name": name,
        "modern_reality_share_structure": shares[0][0] == 0x11EC,
        "server_name": SERVER_NAME,
        "client_private_key_hex": CLIENT_PRIVATE.hex(),
        "client_public_key_hex": client.public_key().public_bytes_raw().hex(),
        "server_private_key_hex": REALITY_SERVER_PRIVATE.hex(),
        "server_public_key_hex": server.public_key().public_bytes_raw().hex(),
        "client_random_hex": CLIENT_RANDOM.hex(),
        "client_version": list(CLIENT_VERSION),
        "unix_time": UNIX_TIME,
        "short_id_hex": SHORT_ID.hex(),
        "key_share_groups": [group for group, _ in shares],
        "shared_secret_hex": shared.hex(),
        "auth_key_hex": auth_key.hex(),
        "plaintext_hex": plaintext.hex(),
        "client_hello_zero_session_id_hex": aad.hex(),
        "session_id_hex": session_id.hex(),
        "authenticated_client_hello_hex": sealed.hex(),
        "authenticated_client_hello_sha256_hex": hashlib.sha256(sealed).hexdigest(),
        "authenticated_client_hello_sha384_hex": hashlib.sha384(sealed).hexdigest(),
    }


def der(tag: int, content: bytes) -> bytes:
    """Encode one DER value; used only to regenerate the outer certificate."""
    size = len(content)
    if size < 128:
        length = bytes([size])
    else:
        octets = size.to_bytes((size.bit_length() + 7) // 8, "big")
        length = bytes([0x80 | len(octets)]) + octets
    return bytes([tag]) + length + content


def make_certificate(auth_key: bytes) -> dict:
    key = ed25519.Ed25519PrivateKey.from_private_bytes(ED25519_SEED)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SERVER_NAME)])
    ordinary = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime(2020, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2050, 1, 1, tzinfo=timezone.utc))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(SERVER_NAME)]), False)
        .sign(key, algorithm=None)
    )
    pub = key.public_key().public_bytes_raw()
    mac = hmac.digest(auth_key, pub, "sha512")
    # RFC 8410: id-Ed25519 has absent parameters. Rebuild DER with the REALITY
    # HMAC in signatureValue, rather than assuming a signature's byte offset.
    signature_algorithm = bytes.fromhex("300506032b6570")

    def authenticate(tbs: bytes) -> bytes:
        return der(0x30, tbs + signature_algorithm + der(3, b"\x00" + mac))

    bare_builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([]))
        .issuer_name(x509.Name([]))
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime(2020, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2050, 1, 1, tzinfo=timezone.utc))
    )
    bare = bare_builder.sign(key, algorithm=None)
    certificate_der = authenticate(bare.tbs_certificate_bytes)
    parsed = x509.load_der_x509_certificate(certificate_der)
    assert parsed.public_key().public_bytes_raw() == pub
    assert parsed.signature == mac
    assert parsed.tbs_certificate_bytes == bare.tbs_certificate_bytes
    assert not parsed.extensions
    key.public_key().verify(ordinary.signature, ordinary.tbs_certificate_bytes)

    # The pinned upstream's default certificate has serial zero and year-one
    # validity, which ordinary PKIX builders reject. Express that known DER
    # structure as a separate interoperability input, not as a trusted PKI cert.
    year_one = der(0x18, b"00010101000000Z")
    minimal_tbs = der(
        0x30,
        bytes.fromhex("a003020102020100")  # Explicit v3, serial INTEGER zero.
        + signature_algorithm
        + der(0x30, b"")
        + der(0x30, year_one + year_one)
        + der(0x30, b"")
        + der(0x30, signature_algorithm + der(3, b"\x00" + pub)),
    )
    minimal_der = authenticate(minimal_tbs)
    with warnings.catch_warnings(record=True) as observed:
        warnings.simplefilter("always", CryptographyDeprecationWarning)
        minimal = x509.load_der_x509_certificate(minimal_der)
    assert all(isinstance(item.message, CryptographyDeprecationWarning) for item in observed)
    assert minimal.signature == mac and not minimal.extensions
    assert minimal.not_valid_before_utc == datetime(1, 1, 1, tzinfo=timezone.utc)

    unsupported = bare_builder.add_extension(
        x509.UnrecognizedExtension(x509.ObjectIdentifier("0.0"), b"unsupported-ml-dsa-test"),
        critical=False,
    ).sign(key, algorithm=None)
    unsupported_der = authenticate(unsupported.tbs_certificate_bytes)
    assert x509.load_der_x509_certificate(unsupported_der).signature == mac
    return {
        "server_name": SERVER_NAME,
        "ed25519_seed_hex": ED25519_SEED.hex(),
        "ed25519_public_key_hex": pub.hex(),
        "ed25519_pkcs8_der_hex": key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).hex(),
        "auth_key_hex": auth_key.hex(),
        "der_hex": certificate_der.hex(),
        "tbs_certificate_der_hex": bare.tbs_certificate_bytes.hex(),
        "hmac_signature_hex": mac.hex(),
        "ordinary_self_signed_der_hex": ordinary.public_bytes(serialization.Encoding.DER).hex(),
        "upstream_minimal_der_hex": minimal_der.hex(),
        "unsupported_mldsa_der_hex": unsupported_der.hex(),
    }


def expand_label(secret: bytes, label: bytes, context: bytes, hash_name: str) -> bytes:
    algorithm = hashes.SHA256() if hash_name == "sha256" else hashes.SHA384()
    size = algorithm.digest_size
    info = size.to_bytes(2, "big") + vector(b"tls13 " + label, 1) + vector(context, 1)
    return HKDFExpand(algorithm=algorithm, length=size, info=info).derive(secret)


def tls13_case(auth: dict, certificate: dict, hybrid: dict, hash_name: str) -> dict:
    """A synthetic RFC 8446 transcript; no TLS record transport is simulated."""
    digest = lambda data: hashlib.new(hash_name, data).digest()
    suite = 0x1301 if hash_name == "sha256" else 0x1302
    server_public = bytes.fromhex(hybrid["tls_server_public_key_hex"])
    peer_share = MLKEM_CIPHERTEXT + server_public
    extensions = extension(43, b"\x03\x04") + extension(51, b"\x11\xec" + vector(peer_share))
    server_hello = handshake(
        2,
        b"\x03\x03"
        + hashlib.sha256(b"Swirl public REALITY server random").digest()
        + vector(bytes.fromhex(auth["session_id_hex"]), 1)
        + suite.to_bytes(2, "big")
        + b"\x00"
        + vector(extensions),
    )
    encrypted_extensions = handshake(8, vector(extension(0, b"")))  # SNI ack.
    cert_entry = vector(bytes.fromhex(certificate["der_hex"]), 3) + vector(b"")
    cert_message = handshake(11, vector(b"", 1) + vector(cert_entry, 3))
    hello_transcript = bytes.fromhex(auth["authenticated_client_hello_hex"]) + server_hello
    transcript = hello_transcript + encrypted_extensions + cert_message
    cv_input = b" " * 64 + b"TLS 1.3, server CertificateVerify\x00" + digest(transcript)
    key = ed25519.Ed25519PrivateKey.from_private_bytes(ED25519_SEED)
    signature = key.sign(cv_input)
    key.public_key().verify(signature, cv_input)
    cv_message = handshake(15, b"\x08\x07" + vector(signature))

    zero = bytes(len(digest(b"")))
    early = hmac.digest(zero, zero, hash_name)
    derived = expand_label(early, b"derived", digest(b""), hash_name)
    secret = hmac.digest(derived, bytes.fromhex(hybrid["tls_shared_secret_hex"]), hash_name)
    server_traffic = expand_label(secret, b"s hs traffic", digest(hello_transcript), hash_name)
    client_traffic = expand_label(secret, b"c hs traffic", digest(hello_transcript), hash_name)
    server_finished_key = expand_label(server_traffic, b"finished", b"", hash_name)
    before_finished = transcript + cv_message
    server_finished_data = hmac.digest(server_finished_key, digest(before_finished), hash_name)
    server_finished = handshake(20, server_finished_data)
    client_finished_key = expand_label(client_traffic, b"finished", b"", hash_name)
    client_finished_data = hmac.digest(client_finished_key, digest(before_finished + server_finished), hash_name)

    return {
        "name": "hybrid_" + hash_name,
        "auth_case": auth["name"],
        "hash": hash_name,
        "cipher_suite": suite,
        "server_hello_hex": server_hello.hex(),
        "transcript_after_server_hello_hex": hello_transcript.hex(),
        "transcript_hash_after_server_hello_hex": digest(hello_transcript).hex(),
        "encrypted_extensions_hex": encrypted_extensions.hex(),
        "certificate_message_hex": cert_message.hex(),
        "transcript_before_certificate_verify_hex": transcript.hex(),
        "transcript_hash_hex": digest(transcript).hex(),
        "certificate_verify_input_hex": cv_input.hex(),
        "certificate_verify_signature_hex": signature.hex(),
        "certificate_verify_message_hex": cv_message.hex(),
        "tls_shared_secret_hex": hybrid["tls_shared_secret_hex"],
        "handshake_secret_hex": secret.hex(),
        "server_handshake_traffic_secret_hex": server_traffic.hex(),
        "client_handshake_traffic_secret_hex": client_traffic.hex(),
        "server_finished_key_hex": server_finished_key.hex(),
        "transcript_hash_before_server_finished_hex": digest(before_finished).hex(),
        "server_finished_verify_data_hex": server_finished_data.hex(),
        "server_finished_message_hex": server_finished.hex(),
        "client_finished_key_hex": client_finished_key.hex(),
        "transcript_hash_before_client_finished_hex": digest(before_finished + server_finished).hex(),
        "client_finished_verify_data_hex": client_finished_data.hex(),
        "client_finished_message_hex": handshake(20, client_finished_data).hex(),
    }


def flipped(data: bytes, offset: int = 0) -> bytes:
    changed = bytearray(data)
    changed[offset] ^= 1
    return bytes(changed)


def expect_failure(kind: type[Exception], action) -> None:
    try:
        action()
    except kind:
        return
    raise AssertionError(f"expected {kind.__name__}")


def negative_checks(auth: dict, certificate: dict, tls: list[dict], kem_key) -> list[dict]:
    key = bytes.fromhex(auth["auth_key_hex"])
    nonce = CLIENT_RANDOM[20:]
    aad = bytes.fromhex(auth["client_hello_zero_session_id_hex"])
    ciphertext = bytes.fromhex(auth["session_id_hex"])
    results = []
    mutations = [
        ("client_random_bit", key, nonce, ciphertext, flipped(aad, 6)),
        ("key_share_bit", key, nonce, ciphertext, flipped(aad, len(aad) - 1)),
        ("sni_bit", key, nonce, ciphertext, flipped(aad, aad.index(SERVER_NAME.encode()))),
        ("ciphertext_bit", key, nonce, flipped(ciphertext), aad),
        ("tag_bit", key, nonce, flipped(ciphertext, 31), aad),
        ("nonce_bit", key, flipped(nonce), ciphertext, aad),
        ("auth_key_bit", flipped(key), nonce, ciphertext, aad),
        ("sealed_hello_used_as_aad", key, nonce, ciphertext, bytes.fromhex(auth["authenticated_client_hello_hex"])),
        ("missing_handshake_header_aad", key, nonce, ciphertext, aad[4:]),
    ]
    for name, bad_key, bad_nonce, bad_ciphertext, bad_aad in mutations:
        expect_failure(InvalidTag, lambda: AESGCM(bad_key).decrypt(bad_nonce, bad_ciphertext, bad_aad))
        results.append({"name": name, "expected": "AES-GCM InvalidTag"})
    client = x25519.X25519PrivateKey.from_private_bytes(CLIENT_PRIVATE)
    expect_failure(ValueError, lambda: client.exchange(x25519.X25519PublicKey.from_public_bytes(bytes(32))))
    results.append({"name": "all_zero_x25519_peer", "expected": "X25519 exchange rejects null shared key"})
    ordinary = x509.load_der_x509_certificate(bytes.fromhex(certificate["ordinary_self_signed_der_hex"]))
    pub = ordinary.public_key()
    assert not hmac.compare_digest(ordinary.signature, bytes.fromhex(certificate["hmac_signature_hex"]))
    results.append({"name": "ordinary_valid_ed25519_certificate", "expected": "REALITY HMAC does not match"})
    assert not hmac.compare_digest(hmac.digest(flipped(key), pub.public_bytes_raw(), "sha512"), bytes.fromhex(certificate["hmac_signature_hex"]))
    results.append({"name": "certificate_auth_key_bit", "expected": "REALITY HMAC does not match"})
    for case in tls:
        cv_input = bytes.fromhex(case["certificate_verify_input_hex"])
        sig = bytes.fromhex(case["certificate_verify_signature_hex"])
        for label, message, changed_sig in [
            ("transcript_bit", flipped(cv_input, len(cv_input) - 1), sig),
            ("wrong_client_context", cv_input.replace(b"server", b"client"), sig),
            ("signature_bit", cv_input, flipped(sig)),
        ]:
            expect_failure(InvalidSignature, lambda: pub.verify(changed_sig, message))
            results.append({"name": case["name"] + "_" + label, "expected": "Ed25519 InvalidSignature"})
        wrong_finished = hmac.digest(
            bytes.fromhex(case["server_finished_key_hex"]),
            flipped(bytes.fromhex(case["transcript_hash_before_server_finished_hex"])),
            case["hash"],
        )
        assert not hmac.compare_digest(wrong_finished, bytes.fromhex(case["server_finished_verify_data_hex"]))
        results.append({"name": case["name"] + "_finished_transcript_bit", "expected": "Finished verify_data mismatch"})
    rejected = kem_key.decapsulate(flipped(MLKEM_CIPHERTEXT))
    assert rejected != ENCAPSULATED_SECRET and len(rejected) == 32
    results.append({
        "name": "mlkem_ciphertext_bit",
        "expected": "ML-KEM implicit rejection returns a different secret",
        "ciphertext_byte_offset": 0,
        "xor_mask": 1,
        "rejected_secret_hex": rejected.hex(),
    })
    expect_failure(ValueError, lambda: kem_key.decapsulate(MLKEM_CIPHERTEXT[:-1]))
    results.append({"name": "truncated_mlkem_ciphertext", "expected": "ML-KEM length rejection"})
    return results


def generate() -> dict:
    client = x25519.X25519PrivateKey.from_private_bytes(CLIENT_PRIVATE)
    client_pub = client.public_key().public_bytes_raw()
    tls_server = x25519.X25519PrivateKey.from_private_bytes(TLS_SERVER_PRIVATE)
    tls_ecdh = client.exchange(tls_server.public_key())
    assert tls_ecdh == tls_server.exchange(client.public_key())
    kem_key = mlkem.MLKEM768PrivateKey.from_seed_bytes(MLKEM_SEED)
    kem_pub = kem_key.public_key().public_bytes_raw()
    kem_secret = kem_key.decapsulate(MLKEM_CIPHERTEXT)
    assert len(kem_pub) == 1184 and len(MLKEM_CIPHERTEXT) == 1088
    assert kem_secret == ENCAPSULATED_SECRET
    hybrid = {
        "group": 0x11EC,
        "mlkem_seed_hex": MLKEM_SEED.hex(),
        "mlkem_public_key_hex": kem_pub.hex(),
        "mlkem_ciphertext_hex": MLKEM_CIPHERTEXT.hex(),
        "mlkem_shared_secret_hex": kem_secret.hex(),
        "tls_server_private_key_hex": TLS_SERVER_PRIVATE.hex(),
        "tls_server_public_key_hex": tls_server.public_key().public_bytes_raw().hex(),
        "tls_x25519_shared_secret_hex": tls_ecdh.hex(),
        "client_key_share_hex": (kem_pub + client_pub).hex(),
        "server_key_share_hex": (MLKEM_CIPHERTEXT + tls_server.public_key().public_bytes_raw()).hex(),
        "tls_shared_secret_hex": (kem_secret + tls_ecdh).hex(),
        "ciphertext_provenance": "One cryptography 50.0.2 OpenSSL-backed encapsulate() result; fixed public input, independently decapsulated on every regeneration.",
    }
    cases = [
        make_auth_case("x25519_legacy_auth_only", [(0x001D, client_pub)]),
        make_auth_case("x25519mlkem768", [(0x11EC, kem_pub + client_pub)]),
        make_auth_case("x25519mlkem768_with_x25519", [(0x11EC, kem_pub + client_pub), (0x001D, client_pub)]),
    ]
    certificate = make_certificate(bytes.fromhex(cases[1]["auth_key_hex"]))
    tls = [tls13_case(cases[1], certificate, hybrid, name) for name in ("sha256", "sha384")]
    negatives = negative_checks(cases[1], certificate, tls, kem_key)
    return {
        "schema_version": 1,
        "public_test_material": True,
        "scope": "Independent primitive and synthetic transcript fixtures; no browser fingerprint, live peer, REALITY connection or Vision acceptance is claimed.",
        "generator": "tools/tests/generate_reality_vectors.py",
        "dependency": "cryptography==50.0.2",
        "sources": [
            f"https://github.com/XTLS/Xray-core/blob/{XRAY_REF}/transport/internet/reality/reality.go",
            f"https://github.com/XTLS/REALITY/blob/{REALITY_REF}/tls.go",
            f"https://github.com/XTLS/REALITY/blob/{REALITY_REF}/handshake_server_tls13.go",
            "https://www.rfc-editor.org/rfc/rfc8446#section-4.4.3",
            "https://www.rfc-editor.org/rfc/rfc8446#section-4.4.4",
            "https://www.rfc-editor.org/rfc/rfc8446#section-7.1",
            "https://www.rfc-editor.org/rfc/rfc9954#section-3.2",
            "https://www.rfc-editor.org/rfc/rfc10024#section-4",
            "https://cryptography.io/en/50.0.2/hazmat/primitives/asymmetric/mlkem/",
        ],
        "cases": cases,
        "hybrid": hybrid,
        "certificate": certificate,
        "tls13": tls,
        "negative_checks": negatives,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify exact regeneration without changing files.")
    args = parser.parse_args()
    fixture = generate()
    expected = (json.dumps(fixture, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if args.check:
        if not FIXTURE.is_file() or FIXTURE.read_bytes() != expected:
            print("REALITY fixture is missing or differs from independent regeneration.", file=sys.stderr)
            return 1
    else:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_bytes(expected)
    print(
        f"REALITY vectors {'verified' if args.check else 'generated'}: "
        f"{len(fixture['cases'])} auth cases, genuine ML-KEM decapsulation, "
        f"{len(fixture['tls13'])} TLS transcripts, "
        f"{len(fixture['negative_checks'])} negative checks. "
        "No network or provider test."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
