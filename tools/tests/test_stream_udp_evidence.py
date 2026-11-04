"""Contracts for real UDP measurements and non-masking failure evidence."""
from __future__ import annotations

import contextlib
import hashlib
import json
import queue
import socket
import threading
import unittest
from unittest.mock import patch

import test_stream_udp_xray as fixture
import test_tuic_reference as udp_fixture


class StreamUdpEvidenceTests(unittest.TestCase):
    @contextlib.contextmanager
    def origin(self, *, dns=False, observer=None):
        origin = udp_fixture.UdpOrigin(("127.0.0.1", 0), udp_fixture.UdpHandler)
        origin.received, origin.dns = [], dns
        if observer is not None:
            origin.datagram_observer = observer
        thread = threading.Thread(target=origin.serve_forever,
                                  kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            yield origin
        finally:
            origin.shutdown()
            origin.server_close()
            thread.join(2)
            self.assertFalse(thread.is_alive())

    def test_real_udp_echo_empty_and_dns_measure_actual_received_and_sent_bytes(self):
        query = (b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
                 b"\x07example\x03com\x00\x00\x01\x00\x01")
        for dns, payload in ((False, b""), (False, bytes(range(256))), (True, query)):
            with self.subTest(dns=dns, payload_bytes=len(payload)):
                observations = fixture.DatagramObservations()
                completed = queue.Queue()

                def observe(stage, data, source, error=None):
                    observations.observe(stage, data, source, error)
                    if stage == "reply_sent":
                        completed.put(True)

                with self.origin(dns=dns, observer=observe) as origin, \
                        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                    client.bind(("127.0.0.1", 0))
                    client.settimeout(2)
                    client.sendto(payload, origin.server_address)
                    reply, source = client.recvfrom(65535)
                    self.assertTrue(completed.get(timeout=2))
                    self.assertEqual(source, origin.server_address)
                    if dns:
                        self.assertEqual(reply[:4], b"\x12\x34\x81\x80")
                        self.assertNotEqual(reply, payload)
                    else:
                        self.assertEqual(reply, payload)
                    snapshot = observations.snapshot()
                    self.assertEqual((snapshot["received_count"], snapshot["reply_sent_count"],
                                      snapshot["reply_error_count"]), (1, 1, 0))
                    self.assertEqual(snapshot["events"], [
                        {"stage": stage, "source": list(client.getsockname()),
                         "payload_bytes": len(data),
                         "payload_sha256": hashlib.sha256(data).hexdigest()}
                        for stage, data in (("received", payload), ("reply_sent", reply))])
                    self.assertEqual(origin.received, [payload])

    def test_default_handler_without_observer_preserves_wire_and_received_list(self):
        with self.origin() as origin, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(2)
            client.sendto(b"ordinary-handler", origin.server_address)
            reply, _ = client.recvfrom(65535)
            self.assertEqual(reply, b"ordinary-handler")
            self.assertEqual(origin.received, [b"ordinary-handler"])
            self.assertFalse(hasattr(origin, "datagram_observer"))

    def test_diagnostic_write_error_preserves_original_exchange_exception_and_redacts_text(self):
        case = fixture.StreamUdpXrayTests(
            "test_vless_targets_have_separate_carriers_and_trojan_frames_keep_each_address")
        case.failures, case.exchange_index, case.exchange_stage = [], 0, "first"
        original = TimeoutError("original exchange deadline")
        with patch.object(fixture.core_fixture.QuicCoreTests, "udp_exchange", side_effect=original), \
                patch.object(case, "record_udp_failure",
                             side_effect=OSError("diagnostic-only-secret-must-not-appear")):
            with self.assertRaises(TimeoutError) as caught:
                case.udp_exchange(None, None, b"synthetic-only")
        self.assertIs(caught.exception, original)
        self.assertEqual(case.failures[0]["error_type"], "TimeoutError")
        self.assertEqual(case.failures[0]["diagnostic_errors"], ["OSError"])
        self.assertEqual(case.failures[0]["stage"], "first")
        self.assertNotIn("diagnostic-only-secret", json.dumps(case.failures))


if __name__ == "__main__":
    unittest.main()
