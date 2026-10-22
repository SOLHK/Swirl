"""C4 native HTTPUpgrade through the locked, independent Xray server.

Run after building the transport-client example and Fetch-TransportPeers.py:
SWIRL_TRANSPORT_CLIENT=... SWIRL_XRAY_BINARY=... python -m unittest -v
test_transport_http_xray. Results and server logs can be retained by setting
SWIRL_TRANSPORT_EVIDENCE. All endpoint credentials and certificates are synthetic.
"""

import concurrent.futures
import hashlib
import time
import unittest

from transport_peer import Fixture, HTTP_BODY, pattern_hash


class HttpUpgradeXrayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture("C4")
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
        self.assertIsInstance(report["error"], str)
        return report["error"]

    def test_custom_literal_path_host_and_http_destination(self):
        peer = self.fixture.peer("httpupgrade", path="/nested/原样?value=1%2F")
        origin = self.fixture.origin()
        self.success(self.fixture.request(peer, origin))
        self.fixture.assert_accepted(peer, origin)
        self.assertEqual(origin.requests, ["http"])
        self.fixture.assert_origin_closed(origin)

    def test_tls_httpupgrade_with_vless_trojan_and_https_destinations(self):
        for protocol in ("vless", "trojan"):
            with self.subTest(protocol=protocol):
                peer = self.fixture.peer("httpupgrade", protocol=protocol, tls=True)
                origin = self.fixture.origin(tls=True)
                self.success(self.fixture.request(peer, origin))
                self.fixture.assert_accepted(peer, origin)
                self.assertEqual(origin.requests, ["http"])
                self.fixture.assert_origin_closed(origin)

    def test_four_mib_bidirectional_stream_with_plaintext_and_tls(self):
        for tls in (False, True):
            with self.subTest(tls=tls):
                peer = self.fixture.peer("httpupgrade", tls=tls)
                origin = self.fixture.origin(mode="echo")
                size = 4 * 1024 * 1024
                self.success(self.fixture.request(peer, origin, mode="echo", size=size), size=size)
                self.fixture.assert_accepted(peer, origin)
                self.assertEqual(origin.received, size)
                self.fixture.assert_origin_closed(origin)

    def test_wrong_path_and_host_are_rejected_before_proxy_request(self):
        peer = self.fixture.peer("httpupgrade")
        origin = self.fixture.origin()
        for key, value in (("path", "/wrong/path"), ("host", "wrong.fixture.invalid")):
            with self.subTest(field=key):
                request = self.fixture.request(peer, origin, timeout_ms=1500)
                request["transport"]["config"][key] = value
                self.failure(request)
        self.assertEqual(origin.requests, [])

    def test_failed_authentication_cannot_reach_the_destination(self):
        for protocol in ("vless", "trojan"):
            with self.subTest(protocol=protocol):
                peer = self.fixture.peer("httpupgrade", protocol=protocol, tls=True)
                origin = self.fixture.origin()
                request = self.fixture.request(peer, origin, timeout_ms=1500)
                if protocol == "vless":
                    request["outbound"]["uuid"] = "ffeeddcc-bbaa-9988-7766-554433221100"
                else:
                    request["outbound"]["password"] = "wrong-fixture-password"
                self.failure(request)
                self.assertEqual(origin.requests, [])

    def test_untrusted_certificate_wrong_sni_and_wrong_alpn_fail_closed(self):
        peer = self.fixture.peer("httpupgrade", tls=True)
        origin = self.fixture.origin()
        for case in ("ca", "sni", "alpn"):
            with self.subTest(case=case):
                request = self.fixture.request(peer, origin)
                if case == "ca":
                    request["outbound"]["tls"]["ca_der_base64"] = None
                elif case == "sni":
                    request["outbound"]["tls"]["server_name"] = "wrong.fixture.invalid"
                else:
                    request["outbound"]["tls"]["alpn"] = ["h2"]
                self.failure(request)
        self.assertEqual(origin.requests, [])

    def test_parallel_connections_and_client_cancellation(self):
        peer = self.fixture.peer("httpupgrade", tls=True)
        origin = self.fixture.origin(mode="echo")
        size = 512 * 1024
        requests = [self.fixture.request(peer, origin, mode="cancel", size=size) for _ in range(6)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            reports = list(pool.map(lambda request: self.success(request, size=size), requests))
        self.assertEqual(len(reports), 6)
        self.assertEqual(len(origin.requests), 6)
        self.assertEqual(origin.received, size * 6)
        self.fixture.assert_accepted(peer, origin)

    def test_truncation_and_network_interrupt_do_not_replay_requests(self):
        peer = self.fixture.peer("httpupgrade", tls=True)
        broken = self.fixture.origin(mode="disconnect")
        self.failure(self.fixture.request(peer, broken, timeout_ms=1500))
        self.assertEqual(broken.requests, ["disconnect"])
        healthy = self.fixture.origin()
        self.success(self.fixture.request(peer, healthy))
        self.fixture.assert_accepted(peer, healthy)
        self.fixture.assert_origin_closed(healthy)

    def test_server_termination_and_fresh_connection_recovery(self):
        peer = self.fixture.peer("httpupgrade", tls=True)
        stall = self.fixture.origin(mode="stall")
        request = self.fixture.request(peer, stall, timeout_ms=4000)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.fixture.run, request)
            deadline = time.monotonic() + 3
            while not stall.requests and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(stall.requests, ["stall"])
            self.fixture.terminate(peer)
            process, report = pending.result(timeout=5)
            self.assertEqual(process.returncode, 1, report)
            self.assertFalse(report["ok"])
        recovered = self.fixture.peer("httpupgrade", tls=True)
        origin = self.fixture.origin()
        self.success(self.fixture.request(recovered, origin))
        self.fixture.assert_accepted(recovered, origin)
        self.fixture.assert_origin_closed(origin)


if __name__ == "__main__":
    unittest.main(verbosity=2)
