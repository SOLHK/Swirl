"""C3 legacy streaming HTTP/2 PUT against unmodified Xray v1.8.24.

Current Xray explicitly removed this transport. This suite deliberately uses
the pinned legacy peer and never substitutes CONNECT or XHTTP.
"""

import concurrent.futures
import hashlib
import time
import unittest

from transport_peer import Fixture, HTTP_BODY, pattern_hash


class Http2XrayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture("C3")
        self.addCleanup(self.fixture.close)

    def success(self, request, *, size=None):
        process, report = self.fixture.run(request)
        self.assertEqual(process.returncode, 0, (report, process.stderr))
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["downloaded"], len(HTTP_BODY) if size is None else size)
        self.assertEqual(report["sha256"], hashlib.sha256(HTTP_BODY).hexdigest()
                         if size is None else pattern_hash(size))
        self.assertEqual(report["close"], "cancelled" if request["mode"] == "cancel" else "clean", report)
        return report

    def failure(self, request):
        process, report = self.fixture.run(request)
        self.assertEqual(process.returncode, 1, (report, process.stderr))
        self.assertFalse(report["ok"], report)
        return report["error"]

    def wait_for(self, predicate):
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(predicate())

    def test_vless_and_trojan_tls_custom_host_path_http_and_https(self):
        for protocol in ("vless", "trojan"):
            for target_tls in (False, True):
                with self.subTest(protocol=protocol, target_tls=target_tls):
                    peer = self.fixture.peer("h2", protocol=protocol, tls=True, legacy=True,
                                             host="legacy-h2.fixture.invalid", path="/legacy/nested")
                    origin = self.fixture.origin(tls=target_tls)
                    request = self.fixture.request(peer, origin)
                    request["transport"]["config"]["headers"] = [["x-swirl-h2", "custom"]]
                    self.success(request)
                    self.fixture.assert_accepted(peer, origin)
                    self.assertEqual(origin.requests, ["http"])
                    self.wait_for(lambda: origin.tls_closes == 1 if target_tls else origin.client_closes == 1)

    def test_eight_mib_bidirectional_flow_control_and_half_close(self):
        peer = self.fixture.peer("h2", tls=True, legacy=True)
        origin = self.fixture.origin(echo=True)
        size = 8 * 1024 * 1024 + 7
        self.success(self.fixture.request(peer, origin, mode="echo", size=size), size=size)
        self.assertEqual(origin.received, size)
        self.fixture.assert_accepted(peer, origin)
        self.wait_for(lambda: origin.client_closes == 1)

    def test_eight_concurrent_connections_and_client_drop_release_targets(self):
        peer = self.fixture.peer("h2", tls=True, legacy=True)
        origin = self.fixture.origin(echo=True)
        size = 256 * 1024
        requests = [self.fixture.request(peer, origin, mode="cancel", size=size) for _ in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            reports = list(pool.map(lambda request: self.success(request, size=size), requests))
        self.assertEqual(len(reports), 8)
        self.assertEqual(len(origin.requests), 8)
        self.assertEqual(origin.received, size * 8)
        self.fixture.assert_accepted(peer, origin)
        self.wait_for(lambda: not origin.active)

    def test_wrong_host_path_and_server_status_are_errors(self):
        peer = self.fixture.peer("h2", tls=True, legacy=True)
        origin = self.fixture.origin()
        for key, value in (("host", "wrong.fixture.invalid"), ("path", "/different-service")):
            with self.subTest(field=key):
                request = self.fixture.request(peer, origin, timeout_ms=1500)
                request["transport"]["config"][key] = value
                self.assertNotEqual(self.failure(request), "OperationTimeout")
        self.assertEqual(origin.requests, [])

    def test_tls_certificate_sni_alpn_and_vless_auth_are_checked(self):
        peer = self.fixture.peer("h2", tls=True, legacy=True)
        origin = self.fixture.origin()
        for case in ("ca", "sni", "alpn", "uuid"):
            with self.subTest(case=case):
                request = self.fixture.request(peer, origin, timeout_ms=1500)
                if case == "ca":
                    request["outbound"]["tls"]["ca_der_base64"] = None
                elif case == "sni":
                    request["outbound"]["tls"]["server_name"] = "wrong.fixture.invalid"
                elif case == "alpn":
                    request["outbound"]["tls"]["alpn"] = ["http/1.1"]
                else:
                    request["outbound"]["uuid"] = "ffeeddcc-bbaa-9988-7766-554433221100"
                self.failure(request)
        self.assertEqual(origin.requests, [])

    def test_plain_legacy_h2_and_framing_override_fail_explicitly(self):
        peer = self.fixture.peer("h2", tls=False, legacy=True)
        origin = self.fixture.origin()
        request = self.fixture.request(peer, origin)
        self.assertEqual(self.failure(request), "Http2TlsRequired")
        secured = self.fixture.peer("h2", tls=True, legacy=True)
        for name in ("Connection", "Content-Length", "TE"):
            with self.subTest(header=name):
                request = self.fixture.request(secured, origin)
                request["transport"]["config"]["headers"] = [[name, "invalid"]]
                self.assertEqual(self.failure(request), "Http2ReservedHeader")
        request = self.fixture.request(secured, origin)
        request["transport"]["config"]["method"] = "CONNECT"
        self.assertEqual(self.failure(request), "InputSyntax")
        self.assertEqual(origin.requests, [])

    def test_timeout_cancel_and_server_interruption_are_bounded(self):
        peer = self.fixture.peer("h2", tls=True, legacy=True)
        origin = self.fixture.origin(mode="stall")
        started = time.monotonic()
        self.assertIn(self.failure(self.fixture.request(peer, origin, timeout_ms=250)),
                      ("OperationTimeout", "TransportReadTimeout"))
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(origin.requests, ["stall"])
        self.fixture.assert_accepted(peer, origin)
        interrupted = self.fixture.origin(mode="stall")
        request = self.fixture.request(peer, interrupted, timeout_ms=4000)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.fixture.run, request)
            self.wait_for(lambda: bool(interrupted.requests))
            self.fixture.assert_accepted(peer, interrupted)
            self.fixture.terminate(peer)
            process, report = pending.result(timeout=5)
            self.assertEqual(process.returncode, 1, report)
            self.assertNotEqual(report.get("error"), "OperationTimeout", report)

    def test_truncated_response_fails_and_fresh_connection_recovers(self):
        peer = self.fixture.peer("h2", tls=True, legacy=True)
        interrupted = self.fixture.origin(mode="disconnect")
        self.failure(self.fixture.request(peer, interrupted, timeout_ms=1500))
        self.fixture.assert_accepted(peer, interrupted)
        recovered = self.fixture.origin()
        self.success(self.fixture.request(peer, recovered))
        self.fixture.assert_accepted(peer, recovered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
