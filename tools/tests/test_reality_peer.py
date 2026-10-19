#!/usr/bin/env python3
"""Offline/fixed-vector and bounded socket self-checks for reality_peer.

The known AES-GCM Client Finished record and traffic-key values in one test are
numeric interoperability vectors from RFC 8448 section 3. Their exact byte
comparison guards the record header, HKDF labels, nonce, content type and tag.
These checks are not Rust-client or mature-REALITY interoperability evidence.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import socket
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519, mlkem, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from reality_peer import (
    DEFAULT_FIXTURE, HYBRID, X25519, ClientHello, Cursor, KeyExchange,
    MAX_PLAINTEXT, PeerError, RealityPeer, RecordCipher, Wire,
    authenticate_client, build_server_flight, digest, expand_label, finished,
    flipped, handshake, vector,
)


class RealityPeerSelfChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(DEFAULT_FIXTURE.read_bytes())
        cls.auth = cls.fixture["cases"][1]
        cls.hello = ClientHello.parse(bytes.fromhex(cls.auth["authenticated_client_hello_hex"]), cls.auth["server_name"])
        cls.auth_private = x25519.X25519PrivateKey.from_private_bytes(bytes.fromhex(cls.auth["server_private_key_hex"]))
        cls.auth_key = bytes.fromhex(cls.auth["auth_key_hex"])
        cls.short_id = bytes.fromhex(cls.auth["short_id_hex"])
        certificate = cls.fixture["certificate"]
        cls.template = bytes.fromhex(certificate["der_hex"])
        cls.signing_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(certificate["ed25519_seed_hex"]))

    def auth_check(self, hello, **kwargs):
        return authenticate_client(hello, self.auth_private, self.short_id, self.auth["unix_time"], **kwargs)

    def fixture_flight(self, suite, *, mode="valid"):
        hybrid = self.fixture["hybrid"]
        exchange = KeyExchange(HYBRID, bytes.fromhex(hybrid["server_key_share_hex"]), bytes.fromhex(hybrid["tls_shared_secret_hex"]))
        return build_server_flight(self.hello, self.auth_key, exchange, suite, self.template, self.signing_key,
                                   server_random=hashlib.sha256(b"Swirl public REALITY server random").digest(), mode=mode)

    def test_modern_authentication_matches_both_independent_fixtures(self):
        for case in self.fixture["cases"][1:]:
            with self.subTest(case=case["name"]):
                hello = ClientHello.parse(bytes.fromhex(case["authenticated_client_hello_hex"]), case["server_name"])
                key, metadata = self.auth_check(hello)
                self.assertEqual(key.hex(), case["auth_key_hex"])
                self.assertEqual(hello.zero_session_hello().hex(), case["client_hello_zero_session_id_hex"])
                self.assertTrue(metadata["timestampVerified"])
                self.assertTrue(metadata["shortIdVerified"])

    def test_two_complete_server_transcripts_match_fixed_checkpoints(self):
        fields = {"server_hello": "server_hello_hex", "encrypted_extensions": "encrypted_extensions_hex",
                  "certificate": "certificate_message_hex", "certificate_verify": "certificate_verify_message_hex",
                  "server_finished": "server_finished_message_hex", "hello_transcript": "transcript_after_server_hello_hex",
                  "before_certificate_verify": "transcript_before_certificate_verify_hex",
                  "handshake_secret": "handshake_secret_hex", "client_handshake_secret": "client_handshake_traffic_secret_hex",
                  "server_handshake_secret": "server_handshake_traffic_secret_hex"}
        for case in self.fixture["tls13"]:
            with self.subTest(case=case["name"]):
                flight = self.fixture_flight(case["cipher_suite"])
                for attribute, field in fields.items():
                    self.assertEqual(getattr(flight, attribute).hex(), case[field], field)
                self.assertEqual(finished(flight.client_handshake_secret, flight.through_server_finished, flight.hash_name).hex(),
                                 case["client_finished_message_hex"])

    def test_rfc8448_client_finished_record_and_key_derivation(self):
        secret = bytes.fromhex("b3eddb126e067f35a780b3abf45e2d8f3b1a950738f52e9600746a0e27a55a21")
        expected_key = bytes.fromhex("dbfaa693d1762c5b666af5d950258d01")
        expected_iv = bytes.fromhex("5bd3c71b836e0b76bb73265f")
        payload = bytes.fromhex("14000020a8ec436d677634ae525ac1fcebe11a039ec17694fac6e98527b642f2edd5ce61")
        expected = bytes.fromhex("170303003575ec4dc238cce60b298044a71e219c56cc77b0517fe9b93c7a4bfc44d87f38f80338ac98fc46deb384bd1caeacab6867d726c40546")
        self.assertEqual(expand_label(secret, b"key", b"", "sha256", 16), expected_key)
        self.assertEqual(expand_label(secret, b"iv", b"", "sha256", 12), expected_iv)
        self.assertEqual(RecordCipher(secret, 0x1301).encrypt(22, payload), expected)
        self.assertEqual(RecordCipher(secret, 0x1301).decrypt(expected), (22, payload))

    def test_live_hybrid_and_classical_exchanges_decapsulate_independently(self):
        case = self.fixture["cases"][2]
        hello = ClientHello.parse(bytes.fromhex(case["authenticated_client_hello_hex"]), case["server_name"])
        classical = x25519.X25519PrivateKey.from_private_bytes(bytes.fromhex(case["client_private_key_hex"]))
        kem = mlkem.MLKEM768PrivateKey.from_seed_bytes(bytes.fromhex(self.fixture["hybrid"]["mlkem_seed_hex"]))
        observed = set()
        for group in (HYBRID, X25519):
            for _ in range(2):
                exchange = KeyExchange.fresh(hello, group)
                classical_secret = classical.exchange(x25519.X25519PublicKey.from_public_bytes(exchange.server_share[-32:]))
                shared = kem.decapsulate(exchange.server_share[:-32]) + classical_secret if group == HYBRID else classical_secret
                self.assertEqual(shared, exchange.shared_secret)
                self.assertNotIn(exchange.server_share, observed)
                observed.add(exchange.server_share)

    def test_authentication_binds_hello_random_sni_key_share_and_session_tag(self):
        raw = self.hello.raw
        for offset in (6, 39, 70, raw.index(b"reality.test"), len(raw) - 1):
            with self.subTest(offset=offset):
                changed = raw[:offset] + flipped(raw[offset:offset + 1]) + raw[offset + 1:]
                # Keep parse-time fields so this case independently verifies
                # the AEAD binding to the original, actual handshake bytes.
                bad = dataclasses.replace(self.hello, raw=changed,
                    session_id=changed[self.hello.session_offset:self.hello.session_offset + 32])
                with self.assertRaisesRegex(PeerError, "authentication_tag"):
                    self.auth_check(bad)
        with self.assertRaisesRegex(PeerError, "authentication_tag"):
            self.auth_check(self.hello, wrong_auth=True)

    def test_authentication_rejects_authenticated_invalid_parameters(self):
        plain = bytes.fromhex(self.auth["plaintext_hex"])
        for field, changed in (
            ("reserved", plain[:3] + b"\x01" + plain[4:]),
            ("version", flipped(plain)),
            ("time", plain[:4] + bytes(4) + plain[8:]),
            ("short_id", plain[:8] + flipped(plain[8:])),
        ):
            with self.subTest(field=field):
                sid = AESGCM(self.auth_key).encrypt(self.hello.random[20:], changed, self.hello.zero_session_hello())
                raw = self.hello.raw[:39] + sid + self.hello.raw[71:]
                with self.assertRaisesRegex(PeerError, "authentication_" + field):
                    self.auth_check(dataclasses.replace(self.hello, raw=raw, session_id=sid))

    def test_parser_rejects_truncations_extra_data_and_legacy_profile(self):
        raw = self.hello.raw
        for size in (0, 3, 38, 71, len(raw) - 1):
            with self.subTest(size=size), self.assertRaises(PeerError):
                ClientHello.parse(raw[:size], self.auth["server_name"])
        with self.assertRaisesRegex(PeerError, "trailing_vector_bytes"):
            ClientHello.parse(raw + b"\x00", self.auth["server_name"])
        with self.assertRaisesRegex(PeerError, "modern_share_order"):
            ClientHello.parse(bytes.fromhex(self.fixture["cases"][0]["authenticated_client_hello_hex"]), self.auth["server_name"])

    def test_distinct_optional_x25519_and_duplicate_shares_are_refused(self):
        case = self.fixture["cases"][2]
        raw = bytes.fromhex(case["authenticated_client_hello_hex"])
        # key_share is the final extension in this independent fixture.
        with self.assertRaisesRegex(PeerError, "distinct_classical_owner"):
            ClientHello.parse(raw[:-1] + flipped(raw[-1:]), case["server_name"])
        # Replace the optional group's ID with the already-offered hybrid ID.
        offset = len(raw) - 36
        with self.assertRaisesRegex(PeerError, "duplicate_key_share"):
            ClientHello.parse(raw[:offset] + HYBRID.to_bytes(2, "big") + raw[offset + 2:], case["server_name"])

    def test_all_three_record_suites_boundary_padding_integrity_and_replay(self):
        for suite in (0x1301, 0x1302, 0x1303):
            with self.subTest(suite=suite):
                secret = bytes(range(48 if suite == 0x1302 else 32))
                sender, receiver = RecordCipher(secret, suite), RecordCipher(secret, suite)
                first = sender.encrypt(23, b"binary\x00payload", padding=17)
                self.assertEqual(receiver.decrypt(first), (23, b"binary\x00payload"))
                with self.assertRaisesRegex(PeerError, "record_authentication"):
                    receiver.decrypt(first)
                data = bytes(range(256)) * 64
                self.assertEqual(len(data), MAX_PLAINTEXT)
                record = sender.encrypt(23, data)
                self.assertEqual(receiver.decrypt(record), (23, data))
                for changed in (record[:-1] + flipped(record[-1:]), record[:4] + flipped(record[4:5]) + record[5:]):
                    with self.assertRaises(PeerError):
                        RecordCipher(secret, suite).decrypt(changed)
                with self.assertRaisesRegex(PeerError, "plaintext_record_overflow"):
                    sender.encrypt(23, data, padding=1)
                with self.assertRaisesRegex(PeerError, "empty_control_record"):
                    sender.encrypt(22, b"")
                sender.sequence = 1 << 64
                with self.assertRaisesRegex(PeerError, "record_sequence_exhausted"):
                    sender.encrypt(23, b"never sent")

    def test_server_mutations_change_the_exact_authenticated_fields(self):
        good = self.fixture_flight(0x1301)
        for mode, field in (("bad_session_echo", "server_hello"), ("bad_certificate_mac", "certificate"),
                            ("bad_certificate_verify", "certificate_verify"), ("bad_finished", "server_finished")):
            with self.subTest(mode=mode):
                bad = self.fixture_flight(0x1301, mode=mode)
                self.assertNotEqual(getattr(good, field), getattr(bad, field))
        bad = self.fixture_flight(0x1301, mode="bad_certificate_verify")
        message = b" " * 64 + b"TLS 1.3, server CertificateVerify\x00" + digest(bad.before_certificate_verify, bad.hash_name)
        with self.assertRaises(InvalidSignature):
            self.signing_key.public_key().verify(bad.certificate_verify[8:], message)

    def test_fragmented_client_finished_is_verified_before_application(self):
        flight = self.fixture_flight(0x1301)
        peer = RealityPeer()
        cf = finished(flight.client_handshake_secret, flight.through_server_finished, flight.hash_name)
        sender, receiver = socket.socketpair()
        with sender, receiver:
            cipher = RecordCipher(flight.client_handshake_secret, 0x1301)
            fragments = b"".join(cipher.encrypt(22, cf[i:i + 5]) for i in range(0, len(cf), 5))
            sender.sendall(b"\x14\x03\x03\x00\x01\x01" + fragments)
            peer._read_finished(Wire(receiver, 2), RecordCipher(flight.client_handshake_secret, 0x1301), flight)
        self.assertEqual(peer.result["applicationBytesReceived"], 0)

    def test_wrong_client_finished_and_early_application_are_rejected(self):
        flight = self.fixture_flight(0x1301)
        cf = finished(flight.client_handshake_secret, flight.through_server_finished, flight.hash_name)
        for kind, content, error in ((22, cf[:4] + flipped(cf[4:]), "client_finished_verification"),
                                     (23, b"application-before-finished", "application_before_client_finished")):
            with self.subTest(error=error):
                sender, receiver = socket.socketpair()
                with sender, receiver:
                    sender.sendall(RecordCipher(flight.client_handshake_secret, 0x1301).encrypt(kind, content))
                    with self.assertRaisesRegex(PeerError, error):
                        RealityPeer()._read_finished(Wire(receiver, 2), RecordCipher(flight.client_handshake_secret, 0x1301), flight)

    def test_record_header_length_is_rejected_before_reading_body(self):
        sender, receiver = socket.socketpair()
        with sender, receiver:
            sender.sendall(b"\x17\x03\x03\xff\xff")
            with self.assertRaisesRegex(PeerError, "record_length"):
                Wire(receiver, 2).read()

    def test_plaintext_ccs_is_forbidden_after_client_finished(self):
        sender, receiver = socket.socketpair()
        with sender, receiver:
            sender.sendall(b"\x14\x03\x03\x00\x01\x01")
            with self.assertRaisesRegex(PeerError, "compatibility_ccs_after_finished"):
                Wire(receiver, 2).protected(RecordCipher(bytes(32), 0x1301), allow_ccs=False)

    def test_loopback_wrong_authentication_reports_explicit_rejection(self):
        with RealityPeer("wrong_auth", timeout=2, now=self.auth["unix_time"]) as peer:
            with socket.create_connection(("127.0.0.1", peer.port), timeout=2) as connection:
                wire = Wire(connection, 2)
                wire.plain(22, self.hello.raw)
                self.assertEqual(wire.read(), b"\x15\x03\x03\x00\x02\x02\x28")
            result = peer.wait(3)
        self.assertEqual(result["status"], "authentication_rejected")
        self.assertEqual(result["error"], "authentication_tag")
        self.assertFalse(result["clientHelloAuthenticated"])
        self.assertFalse(result["clientFinishedVerified"])
        self.assertEqual(result["applicationBytesReceived"], 0)

    def test_context_manager_does_not_hide_a_server_failure(self):
        with self.assertRaisesRegex(PeerError, "transport_eof_without_close_notify"):
            with RealityPeer(timeout=2) as peer:
                with socket.create_connection(("127.0.0.1", peer.port), timeout=2):
                    pass
                self.assertEqual(peer.wait(3)["status"], "failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
