"""Real native HEAD phase observations through fixed independent proxy peers.

Reuse existing official Xray/Hysteria/TUIC server fixtures without inheriting
or recounting their test methods. Timings accompany actual target HTTP bytes;
request-write completion is deliberately never called authentication success.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import platform
import socketserver
import threading
import time
import unittest

import test_quic_core as core
from test_rust_core import exact, header
from transport_peer import Fixture, UUID, PASSWORD, _Origin


class HeadTarget(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        request = header(self.request)
        line = request.split(b"\r\n", 1)[0].decode("ascii")
        if line not in ("HEAD /timing HTTP/1.1", "HEAD /status HTTP/1.1"):
            raise AssertionError("unexpected target request")
        response = (b"HTTP/1.1 503 Service Unavailable\r\n" if "/status " in line
                    else b"HTTP/1.1 204 No Content\r\n")
        response += b"Content-Length: 0\r\nConnection: close\r\n\r\n"
        self.request.sendall(response)
        with self.server.lock:
            self.server.requests.append(line)
            self.server.received += len(request)
            self.server.sent += len(response)


class NativeTimingTests(unittest.TestCase):
    # Lifecycle helpers only. No proxy protocol is implemented by this suite.
    setUpClass = classmethod(core.QuicCoreTests.setUpClass.__func__)
    setUp = core.QuicCoreTests.setUp
    tuic_peer = core.QuicCoreTests.tuic_peer
    close = core.QuicCoreTests.close
    close_runtime = core.QuicCoreTests.close_runtime
    command = core.QuicCoreTests.command
    peer = core.QuicCoreTests.peer
    start = core.QuicCoreTests.start
    stop = core.QuicCoreTests.stop
    echo_origin = core.QuicCoreTests.echo_origin
    connect = core.QuicCoreTests.connect
    records = []
    observations = []
    ffi_hosts = []

    @classmethod
    def tearDownClass(cls):
        path = os.environ.get("SWIRL_NATIVE_TIMING_EVIDENCE")
        if path:
            output = Path(path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({
                "platform": platform.platform(),
                "scope": "native Core HEAD phase observation; not Qt acceptance",
                "control_boundary": "exported_c_abi_dynamic_library" if cls.native_library
                                    else "native_core_runtime_example",
                "runtime_sha256": cls.runtime_hash,
                "tuic_reference_version": cls.tuic_version,
                "tuic_reference_sha256": cls.tuic_hash,
                "hysteria2_sha256": cls.hy2_hash,
                "observations": cls.observations,
                "core_sessions": cls.records,
                "ffi_hosts": cls.ffi_hosts,
            }, indent=2) + "\n", encoding="utf-8")

    def head_target(self):
        origin = _Origin(("127.0.0.1", 0), HeadTarget)
        origin.requests, origin.errors = [], []
        origin.received = origin.sent = 0
        origin.lock = threading.Lock()
        threading.Thread(target=origin.serve_forever,
                         kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.origins.append(origin)
        return origin

    def probe(self, origin, *, path="timing", success=True, timeout_ms=2500):
        before = len(origin.requests)
        sent_before = origin.sent
        launched = self.command(op="probe_start", timeout_ms=timeout_ms,
            url=f"http://127.0.0.1:{origin.server_address[1]}/{path}")
        self.assertTrue(launched["ok"], launched)
        deadline = time.monotonic() + timeout_ms / 1000 + 2
        while time.monotonic() < deadline:
            response = self.command(op="probe_status")
            self.assertTrue(response["ok"], response)
            status = response["probe"]
            if status["state"] != "running":
                break
            time.sleep(0.005)
        else:
            self.fail("native HEAD probe ignored its bounded deadline")
        # The target thread can be preempted just after sendall while the
        # native reader already publishes the response. Wait for its own
        # bounded accounting to finish rather than racing that thread.
        if success or status.get("failure", {}).get("http_status") == 503:
            accounting_deadline = time.monotonic() + 1
            while (len(origin.requests) == before or origin.sent == sent_before) \
                    and time.monotonic() < accounting_deadline:
                time.sleep(0.002)
        # Record before assertions so an unexpected outcome remains evidence.
        record = {"case": self._testMethodName, "protocol": self.protocol,
            "expected_success": success, "probe": status,
            "target_requests_before": before, "target_requests_after": len(origin.requests),
            "target_received_bytes": origin.received, "target_sent_bytes": origin.sent,
            "expected_outcome_verified": False}
        self.observations.append(record)
        self.assertEqual(status["request_id"], launched["probe"]["request_id"])
        self.assertEqual(status["state"], "succeeded" if success else "failed", status)
        result = status["metrics"] if success else status["failure"]
        timing = result["outbound_timing"]
        text = json.dumps(timing)
        self.assertLess(len(text), 2048)
        for secret in (UUID, PASSWORD, core.tuic.PASSWORD, "synthetic-hy2-core", "127.0.0.1"):
            self.assertNotIn(secret, text)
        self.assertLessEqual(timing["tcp_attempts"], 16)
        for name, value in timing.items():
            if name.endswith("_us") and value is not None:
                self.assertIsInstance(value, int)
                self.assertGreaterEqual(value, 0)
                self.assertLess(value, 30_000_000)
        if success:
            self.assertEqual(result["http_status"], 204)
            self.assertLessEqual(result["outbound_connect_ms"], result["response_headers_ms"])
            self.assertIsNone(result["origin_tls_ms"])
            self.assertEqual(len(origin.requests), before + 1)
            self.assertGreater(origin.received, 0)
            self.assertGreater(origin.sent, 0)
        self.assertFalse(origin.errors, origin.errors)
        return timing, record

    def assert_quic(self, timing, *, reused=False):
        self.assertIsNotNone(timing["resolution_us"])
        self.assertIsNone(timing["tcp_dial_us"])
        self.assertIsNone(timing["tcp_connected_attempt_us"])
        self.assertEqual(timing["tcp_attempts"], 0)
        self.assertIsNone(timing["proxy_tls_handshake_us"])
        self.assertEqual(timing["quic_connection_reused"], reused)
        if reused:
            self.assertIsNone(timing["quic_handshake_including_tls_us"])
        else:
            self.assertIsNotNone(timing["quic_handshake_including_tls_us"])

    def test_vmess_wss_and_failed_status_keep_distinct_setup_phases(self):
        fixture = Fixture("X14-A7-native-timing")
        self.addCleanup(fixture.close)
        peer = fixture.peer("ws", protocol="vmess", tls=True)
        node = copy.deepcopy(peer["outbound"])
        node["websocket"] = peer["transport"]["settings"]
        origin = self.head_target()
        self.start(node)
        for path, success in (("timing", True), ("status", False)):
            timing, record = self.probe(origin, path=path, success=success)
            for key in ("resolution_us", "tcp_dial_us", "tcp_connected_attempt_us",
                        "proxy_tls_handshake_us", "transport_setup_us",
                        "protocol_request_encode_write_us"):
                self.assertIsNotNone(timing[key], key)
            self.assertIsNone(timing["quic_handshake_including_tls_us"])
            self.assertIsNone(timing["authentication_exchange_us"])
            self.assertFalse(timing["authentication_response_accepted"])
            if not success:
                self.assertEqual(record["probe"]["failure"]["code"], "UrlTestStatus")
                self.assertEqual(record["probe"]["failure"]["http_status"], 503)
                self.assertEqual(record["target_requests_after"], record["target_requests_before"] + 1)
            record["official_xray_version"] = fixture.version
            record["expected_outcome_verified"] = True
        self.stop()
        bad = copy.deepcopy(node)
        bad["uuid"] = "10213243-5465-7687-98a9-bacbdcedfe0f"
        self.start(bad)
        timing, record = self.probe(origin, success=False)
        self.assertIsNotNone(timing["protocol_request_encode_write_us"])
        self.assertFalse(timing["authentication_response_accepted"])
        self.assertEqual(record["target_requests_after"], record["target_requests_before"])
        record["official_xray_version"] = fixture.version
        record["expected_outcome_verified"] = True
        self.stop()

    def test_hysteria_authentication_response_and_rejection_are_observed(self):
        node = self.peer("hysteria2")
        origin = self.head_target()
        self.start(node)
        timing, record = self.probe(origin)
        self.assert_quic(timing)
        self.assertIsNotNone(timing["transport_setup_us"])
        self.assertIsNotNone(timing["authentication_exchange_us"])
        self.assertIsNone(timing["authentication_request_encode_write_us"])
        self.assertIsNotNone(timing["proxy_connect_exchange_us"])
        self.assertTrue(timing["authentication_response_accepted"])
        record["expected_outcome_verified"] = True
        self.stop()
        bad = copy.deepcopy(node)
        bad["password"] = "synthetic-incorrect-password"
        self.start(bad)
        timing, record = self.probe(origin, success=False)
        self.assert_quic(timing)
        self.assertIsNotNone(timing["authentication_exchange_us"])
        self.assertFalse(timing["authentication_response_accepted"])
        self.assertIsNone(timing["proxy_connect_exchange_us"])
        self.assertEqual(record["probe"]["failure"]["stage"], "outbound_handshake")
        self.assertEqual(record["target_requests_after"], record["target_requests_before"])
        record["expected_outcome_verified"] = True
        self.stop()

    def test_tuic_auth_write_and_live_connection_reuse_are_not_fake_handshakes(self):
        node = self.peer("tuic-native")
        origin = self.head_target()
        self.start(node)
        timing, record = self.probe(origin)
        self.assert_quic(timing)
        self.assertIsNotNone(timing["authentication_request_encode_write_us"])
        self.assertIsNotNone(timing["protocol_request_encode_write_us"])
        self.assertIsNone(timing["authentication_exchange_us"])
        self.assertFalse(timing["authentication_response_accepted"])
        record["expected_outcome_verified"] = True
        # Keep an independently verified stream alive so the pool owns a live
        # weak entry. A later probe must observe reuse, not an invented zero RTT.
        echo = self.echo_origin()
        with self.connect(echo) as held:
            marker = b"real-native-tuic-stream-keeps-the-session-alive"
            held.sendall(marker)
            self.assertEqual(exact(held, len(marker)), marker)
            timing, record = self.probe(origin)
            self.assert_quic(timing, reused=True)
            self.assertIsNone(timing["authentication_request_encode_write_us"])
            self.assertIsNone(timing["authentication_exchange_us"])
            self.assertFalse(timing["authentication_response_accepted"])
            self.assertIsNotNone(timing["protocol_request_encode_write_us"])
            held.sendall(marker)
            self.assertEqual(exact(held, len(marker)), marker)
            record["live_stream_echo_bytes"] = len(marker) * 2
            record["expected_outcome_verified"] = True
        self.stop()
        bad = copy.deepcopy(node)
        bad["password"] = "synthetic-incorrect-password"
        self.start(bad)
        timing, record = self.probe(origin, success=False)
        self.assert_quic(timing)
        self.assertIsNotNone(timing["authentication_request_encode_write_us"])
        self.assertIsNone(timing["authentication_exchange_us"])
        self.assertFalse(timing["authentication_response_accepted"])
        self.assertEqual(record["target_requests_after"], record["target_requests_before"])
        record["expected_outcome_verified"] = True
        self.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
