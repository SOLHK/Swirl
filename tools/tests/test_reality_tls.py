#!/usr/bin/env python3
"""Actual Rust TLS engine interoperability with an independent Python peer.

SWIRL_REALITY_CLIENT must name the built reality-client example. Missing or
non-executable clients are errors, never skipped tests. All identities/payloads
are public synthetic test material; connections are loopback only. This tests
an explicit TLS engine profile, not Vision, browser fingerprints or providers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest

from reality_peer import HYBRID, X25519, RealityPeer


class RealityTlsInterop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.environ.get("SWIRL_REALITY_CLIENT")
        if not value:
            raise RuntimeError("SWIRL_REALITY_CLIENT must point to the built Rust reality-client example")
        cls.client = Path(value).resolve(strict=True)
        if not cls.client.is_file() or not os.access(cls.client, os.X_OK):
            raise RuntimeError("SWIRL_REALITY_CLIENT is not an executable file")

    def invoke(self, peer: RealityPeer, payload: bytes, **changes):
        request = {**peer.settings(), "payload_hex": payload.hex(), **changes}
        process = subprocess.run(
            [str(self.client)], input=json.dumps(request), encoding="utf-8",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False,
        )
        self.assertEqual(process.stderr, "", "Rust test client must report only its structured stdout outcome")
        lines = [line for line in process.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, "Rust test client must emit exactly one JSON outcome")
        report = json.loads(lines[0])
        self.assertIsInstance(report, dict)
        for field in ("handshake_verified", "payload_matches", "server_close_notify", "client_close_notify"):
            self.assertIs(type(report[field]), bool, field)
        for field in ("uploaded_bytes", "received_bytes"):
            self.assertIs(type(report[field]), int, field)
            self.assertGreaterEqual(report[field], 0, field)
        self.assertIn(report["stage"], ("input", "connect", "handshake", "data", "close"))
        self.assertNotIn(request["public_key_hex"], process.stdout)
        self.assertNotIn(request["short_id_hex"], process.stdout)
        if payload:
            self.assertNotIn(payload.hex(), process.stdout)
        return process.returncode, report

    def positive(self, *, suite=0x1301, group=HYBRID, payload=b"Swirl independent REALITY echo\x00\xff",
                 alpn=None, offered_alpn=None, read_chunk=16384, write_chunk=16384, fragment_handshake=0):
        with RealityPeer(suite=suite, group=group, alpn=alpn, fragment_handshake=fragment_handshake) as peer:
            code, report = self.invoke(peer, payload, alpn=offered_alpn, read_chunk=read_chunk, write_chunk=write_chunk)
            self.assertEqual(code, 0, report)
            self.assertEqual(report["status"], "ok", report)
            self.assertEqual(report["stage"], "close", report)
            self.assertTrue(report["handshake_verified"], report)
            self.assertTrue(report["payload_matches"], report)
            self.assertEqual(report["uploaded_bytes"], len(payload))
            self.assertEqual(report["received_bytes"], len(payload))
            self.assertTrue(report["client_close_notify"], report)
            self.assertTrue(report["server_close_notify"], report)
            self.assertEqual(report["cipher_suite"], suite)
            self.assertEqual(report["group"], group)
            self.assertEqual(report["alpn"], alpn.decode("ascii") if alpn is not None else None)
            observed = peer.wait()
            self.assertEqual(observed["status"], "completed", observed)
            self.assertTrue(observed["clientHelloAuthenticated"], observed)
            self.assertTrue(observed["serverFlightSent"], observed)
            self.assertTrue(observed["clientFinishedVerified"], observed)
            self.assertEqual(observed["applicationBytesReceived"], len(payload))
            self.assertEqual(observed["applicationBytesSent"], len(payload))
            self.assertTrue(observed["closeNotifyReceived"], observed)
            self.assertTrue(observed["closeNotifySent"], observed)
            return observed

    def handshake_failure(self, mode, error, *, expected_failure=None, **request_changes):
        # Offering an ALPN lets the unoffered-alpn case reach the exact selected
        # protocol check instead of failing as an unsolicited extension.
        with RealityPeer(mode, expected_failure=expected_failure) as peer:
            code, report = self.invoke(peer, b"must-never-reach-application", alpn=["h2"], **request_changes)
            self.assertEqual(code, 1, report)
            self.assertEqual(report["status"], "error", report)
            self.assertEqual(report["stage"], "handshake", report)
            self.assertEqual(report["error_kind"], "InvalidData", report)
            self.assertEqual(report["error"], error, report)
            self.assertFalse(report["handshake_verified"], report)
            self.assertEqual(report["uploaded_bytes"], 0)
            self.assertEqual(report["received_bytes"], 0)
            self.assertFalse(report["server_close_notify"], report)
            self.assertFalse(report["client_close_notify"], report)
            observed = peer.wait()
            self.assertFalse(observed["clientFinishedVerified"], observed)
            self.assertEqual(observed["applicationBytesReceived"], 0)
            self.assertEqual(observed["applicationBytesSent"], 0)
            self.assertFalse(observed["closeNotifyReceived"], observed)
            self.assertFalse(observed["closeNotifySent"], observed)
            if mode == "wrong_auth" or expected_failure is not None:
                self.assertFalse(observed["clientHelloAuthenticated"], observed)
            else:
                self.assertTrue(observed["clientHelloAuthenticated"], observed)
                self.assertEqual(observed["status"], "client_rejected", observed)
            return observed

    def test_aes128_hybrid_transcript_data_and_close(self):
        self.positive(suite=0x1301, group=HYBRID)

    def test_aes128_offered_classical_transcript_data_and_close(self):
        self.positive(suite=0x1301, group=X25519)

    def test_aes256_hybrid_transcript_data_and_close(self):
        self.positive(suite=0x1302, group=HYBRID)

    def test_aes256_offered_classical_transcript_data_and_close(self):
        self.positive(suite=0x1302, group=X25519)

    def test_chacha_hybrid_transcript_data_and_close(self):
        self.positive(suite=0x1303, group=HYBRID)

    def test_chacha_offered_classical_transcript_data_and_close(self):
        self.positive(suite=0x1303, group=X25519)

    def test_alpn_selection_preserves_explicit_offer(self):
        for selected, offered in ((None, None), (b"h2", "h2"), (b"http/1.1", ["h2", "http/1.1"])):
            with self.subTest(selected=selected):
                self.positive(alpn=selected, offered_alpn=offered)

    def test_small_socket_writes_reads_and_fragmented_encrypted_handshake(self):
        for read_chunk, write_chunk in ((1, 3), (3, 7), (7, 1)):
            with self.subTest(read_chunk=read_chunk, write_chunk=write_chunk):
                self.positive(payload=b"small-boundaries\x00\x01\x02\x03", read_chunk=read_chunk,
                              write_chunk=write_chunk, fragment_handshake=37)

    def test_empty_full_record_and_multiple_record_payloads(self):
        pattern = bytes(range(256))
        for length in (0, 16384, 32769):
            with self.subTest(length=length):
                payload = (pattern * ((length + 255) // 256))[:length]
                self.positive(payload=payload)

    def test_wrong_server_authentication_key_never_reaches_finished(self):
        observed = self.handshake_failure("wrong_auth", "RealityPeerHandshakeAlert")
        self.assertEqual(observed["status"], "authentication_rejected")
        self.assertEqual(observed["error"], "authentication_tag")

    def test_wrong_client_static_public_key_is_refused(self):
        peer = RealityPeer()
        # Change a non-clamped public-key byte; this remains a well-formed
        # X25519 public input but gives a different authentication secret.
        wrong = bytes([peer.public_key[0] ^ 1]) + peer.public_key[1:]
        observed = self.handshake_failure("valid", "RealityPeerHandshakeAlert",
            expected_failure="authentication_tag", public_key_hex=wrong.hex())
        self.assertEqual(observed["error"], "authentication_tag")

    def test_authenticated_wrong_short_id_is_refused(self):
        observed = self.handshake_failure("valid", "RealityPeerHandshakeAlert",
            expected_failure="authentication_short_id", short_id_hex="0902030405060708")
        self.assertEqual(observed["error"], "authentication_short_id")

    def test_bad_certificate_mac_is_refused(self):
        self.handshake_failure("bad_certificate_mac", "invalid peer certificate: BadSignature")

    def test_bad_certificate_verify_is_refused(self):
        self.handshake_failure("bad_certificate_verify", "invalid peer certificate: BadSignature")

    def test_bad_server_finished_is_refused(self):
        self.handshake_failure("bad_finished", "cannot decrypt peer's message")

    def test_wrong_session_id_echo_is_refused(self):
        self.handshake_failure("bad_session_echo", "RealitySessionIdEcho")

    def test_hello_retry_request_is_refused_without_second_client_hello(self):
        self.handshake_failure("hello_retry_request", "RealityHelloRetryUnsupported")

    def test_unoffered_alpn_is_refused(self):
        self.handshake_failure("unoffered_alpn", "peer misbehaved: SelectedUnofferedApplicationProtocol")

    def test_tcp_eof_after_echo_is_not_authenticated_close(self):
        payload = b"echo-is-not-proof-of-clean-tls-close"
        with RealityPeer("eof_without_close_notify") as peer:
            code, report = self.invoke(peer, payload)
            self.assertEqual(code, 1, report)
            self.assertEqual(report["status"], "error", report)
            self.assertEqual(report["stage"], "close", report)
            self.assertEqual(report["error_kind"], "UnexpectedEof", report)
            self.assertIn("close_notify", report["error"], report)
            self.assertTrue(report["handshake_verified"], report)
            self.assertEqual(report["uploaded_bytes"], len(payload))
            self.assertEqual(report["received_bytes"], len(payload))
            self.assertTrue(report["payload_matches"], report)
            self.assertTrue(report["client_close_notify"], report)
            self.assertFalse(report["server_close_notify"], report)
            observed = peer.wait()
            self.assertEqual(observed["status"], "intentional_unclean_eof", observed)
            self.assertTrue(observed["clientFinishedVerified"], observed)
            self.assertEqual(observed["applicationBytesReceived"], len(payload))
            self.assertEqual(observed["applicationBytesSent"], len(payload))
            self.assertTrue(observed["closeNotifyReceived"], observed)
            self.assertFalse(observed["closeNotifySent"], observed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
