"""C5 XHTTP stream-one H2/H2C against pinned official Xray v26.10.21.

No claims for stream-up, packet-up, HTTP/1.1, HTTP/3, XMUX policy, or separate
download settings are made. These unsupported inputs must fail explicitly.
"""

import concurrent.futures
import hashlib
import time
import unittest

from transport_peer import Fixture, HTTP_BODY, pattern_hash


class XHttpXrayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture("C5")
        self.addCleanup(self.fixture.close)

    def success(self, request, *, size=None):
        process, report = self.fixture.run(request)
        self.assertEqual(process.returncode, 0, (report, process.stderr))
        self.assertTrue(report["ok"])
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

    def test_stream_one_h2c_and_tls_with_custom_path_host_and_https_origin(self):
        for tls in (False, True):
            with self.subTest(tls=tls):
                peer = self.fixture.peer("xhttp", tls=tls, path="/nested/原样?token=fixture")
                origin = self.fixture.origin(tls=True)
                self.success(self.fixture.request(peer, origin))
                self.fixture.assert_accepted(peer, origin)
                self.assertEqual(origin.requests, ["http"])
                self.fixture.assert_origin_closed(origin)

    def test_trojan_over_stream_one_tls(self):
        peer = self.fixture.peer("xhttp", tls=True, protocol="trojan")
        origin = self.fixture.origin()
        self.success(self.fixture.request(peer, origin))
        self.fixture.assert_accepted(peer, origin)
        self.fixture.assert_origin_closed(origin)

    def test_eight_mib_bidirectional_flow_control(self):
        peer = self.fixture.peer("xhttp", tls=True)
        origin = self.fixture.origin(mode="echo")
        size = 8 * 1024 * 1024
        self.success(self.fixture.request(peer, origin, mode="echo", size=size), size=size)
        self.fixture.assert_accepted(peer, origin)
        self.assertEqual(origin.received, size)
        self.fixture.assert_origin_closed(origin)

    def test_eight_parallel_streams_and_client_cancel(self):
        peer = self.fixture.peer("xhttp", tls=True)
        origin = self.fixture.origin(mode="echo")
        size = 512 * 1024
        requests = [self.fixture.request(peer, origin, mode="cancel", size=size) for _ in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda request: self.success(request, size=size), requests))
        self.assertEqual(len(results), 8)
        self.assertEqual(len(origin.requests), 8)
        self.assertEqual(origin.received, size * 8)
        self.fixture.assert_accepted(peer, origin)

    def test_wrong_path_and_host_return_errors(self):
        peer = self.fixture.peer("xhttp", tls=True)
        origin = self.fixture.origin()
        for key, value in (("path", "/wrong/path"), ("host", "wrong.fixture.invalid")):
            with self.subTest(field=key):
                request = self.fixture.request(peer, origin, timeout_ms=1500)
                request["transport"]["config"][key] = value
                self.failure(request)
        self.assertEqual(origin.requests, [])

    def test_server_disallows_stream_one_without_transport_fallback(self):
        peer = self.fixture.peer("xhttp", tls=True, mode="packet-up")
        origin = self.fixture.origin()
        request = self.fixture.request(peer, origin, timeout_ms=1500)
        request["transport"]["config"]["mode"] = "stream-one"
        self.failure(request)
        self.assertEqual(origin.requests, [])

    def test_unsupported_modes_options_and_http3_fail_explicitly(self):
        peer = self.fixture.peer("xhttp", tls=True)
        origin = self.fixture.origin()
        for mode in ("auto", "packet-up", "stream-up", "", "stream-one-h3"):
            with self.subTest(mode=mode):
                request = self.fixture.request(peer, origin)
                request["transport"]["config"]["mode"] = mode
                self.assertEqual(self.failure(request), "XHttpModeUnsupported")
        for key, value in (("downloadSettings", {}), ("xPaddingObfsMode", True), ("xmux", {})):
            with self.subTest(option=key):
                request = self.fixture.request(peer, origin)
                request["transport"]["config"][key] = value
                self.assertEqual(self.failure(request), "InputSyntax")
        request = self.fixture.request(peer, origin)
        request["outbound"]["tls"]["alpn"] = ["h3"]
        self.failure(request)
        self.assertEqual(origin.requests, [])

    def test_untrusted_certificate_wrong_sni_and_authentication_fail(self):
        peer = self.fixture.peer("xhttp", tls=True)
        origin = self.fixture.origin()
        for case in ("ca", "sni", "uuid"):
            with self.subTest(case=case):
                request = self.fixture.request(peer, origin, timeout_ms=1500)
                if case == "ca":
                    request["outbound"]["tls"]["ca_der_base64"] = None
                elif case == "sni":
                    request["outbound"]["tls"]["server_name"] = "wrong.fixture.invalid"
                else:
                    request["outbound"]["uuid"] = "ffeeddcc-bbaa-9988-7766-554433221100"
                self.failure(request)
        self.assertEqual(origin.requests, [])

    def test_truncated_destination_fails_and_new_session_recovers(self):
        peer = self.fixture.peer("xhttp", tls=True)
        origin = self.fixture.origin(mode="disconnect")
        self.failure(self.fixture.request(peer, origin, timeout_ms=1500))
        self.assertEqual(origin.requests, ["disconnect"])
        recovered = self.fixture.origin()
        self.success(self.fixture.request(peer, recovered))
        self.fixture.assert_accepted(peer, recovered)
        self.fixture.assert_origin_closed(recovered)

    def test_server_cancellation_interrupts_stream_and_new_server_recovers(self):
        peer = self.fixture.peer("xhttp", tls=True)
        origin = self.fixture.origin(mode="stall")
        request = self.fixture.request(peer, origin, timeout_ms=4000)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.fixture.run, request)
            deadline = time.monotonic() + 3
            while not origin.requests and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(origin.requests, ["stall"])
            self.fixture.terminate(peer)
            process, report = pending.result(timeout=5)
            self.assertEqual(process.returncode, 1, report)
            self.assertFalse(report["ok"])
        restarted = self.fixture.peer("xhttp", tls=True)
        recovered = self.fixture.origin()
        self.success(self.fixture.request(restarted, recovered))
        self.fixture.assert_accepted(restarted, recovered)
        self.fixture.assert_origin_closed(recovered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
