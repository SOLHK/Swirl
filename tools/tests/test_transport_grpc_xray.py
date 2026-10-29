"""C2 bidirectional gRPC interop against unmodified Xray v26.10.21.

The client is Swirl's real Rust protocol/transport connector. An accepted
TCP socket or HTTP/2 handshake is never counted as proxy authentication.
"""

import concurrent.futures
import hashlib
import time
import unittest

from transport_peer import Fixture, HTTP_BODY, pattern_hash


class GrpcXrayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture("C2")
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

    def test_tun_and_multi_plain_tls_http_and_verified_https(self):
        for tls in (False, True):
            for mode in ("tun", "tun_multi"):
                for target_tls in (False, True):
                    with self.subTest(tls=tls, mode=mode, target_tls=target_tls):
                        peer = self.fixture.peer("grpc", tls=tls,
                                                 host="grpc-authority.fixture.invalid",
                                                 service_name="swirl-interoperability")
                        origin = self.fixture.origin(tls=target_tls)
                        request = self.fixture.request(peer, origin)
                        request["transport"]["config"]["mode"] = mode
                        request["transport"]["config"]["headers"] = [["x-swirl-case", "grpc-custom"]]
                        self.success(request)
                        self.fixture.assert_accepted(peer, origin)
                        self.assertEqual(origin.requests, ["http"])
                        self.wait_for(lambda: origin.tls_closes == 1 if target_tls else origin.client_closes == 1)

    def test_trojan_tls_authentication_uses_same_native_grpc_adapter(self):
        peer = self.fixture.peer("grpc", protocol="trojan", tls=True)
        origin = self.fixture.origin(tls=True)
        self.success(self.fixture.request(peer, origin))
        self.fixture.assert_accepted(peer, origin)
        self.wait_for(lambda: origin.tls_closes == 1)
        rejected = self.fixture.origin()
        request = self.fixture.request(peer, rejected, timeout_ms=1500)
        request["outbound"]["password"] = "incorrect-synthetic-password"
        self.failure(request)
        self.assertEqual(rejected.requests, [])

    def test_service_name_percent_escape_and_custom_tun_paths(self):
        for name in ("nested/service!", "/native/service/single|multi"):
            for mode in ("tun", "tun_multi"):
                with self.subTest(service=name, mode=mode):
                    peer = self.fixture.peer("grpc", tls=True, service_name=name)
                    origin = self.fixture.origin()
                    request = self.fixture.request(peer, origin)
                    request["transport"]["config"]["mode"] = mode
                    self.success(request)
                    self.fixture.assert_accepted(peer, origin)

    def test_two_modes_eight_mib_duplex_and_half_close(self):
        for mode in ("tun", "tun_multi"):
            with self.subTest(mode=mode):
                peer = self.fixture.peer("grpc", tls=True)
                origin = self.fixture.origin(echo=True)
                size = 8 * 1024 * 1024 + 1
                request = self.fixture.request(peer, origin, mode="echo", size=size)
                request["transport"]["config"]["mode"] = mode
                self.success(request, size=size)
                self.fixture.assert_accepted(peer, origin)
                self.assertEqual(origin.received, size)
                self.wait_for(lambda: origin.client_closes == 1)

    def test_eight_concurrent_connections_and_client_cancellation_release_targets(self):
        peer = self.fixture.peer("grpc", tls=True)
        origin = self.fixture.origin(echo=True)
        size = 256 * 1024 + 3
        requests = [self.fixture.request(peer, origin, mode="cancel", size=size) for _ in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            reports = list(pool.map(lambda request: self.success(request, size=size), requests))
        self.assertEqual(len(reports), 8)
        self.assertEqual(len(origin.requests), 8)
        self.assertEqual(origin.received, 8 * size)
        self.fixture.assert_accepted(peer, origin)
        self.wait_for(lambda: not origin.active)

    def test_wrong_service_name_returns_rpc_error_without_origin_access(self):
        peer = self.fixture.peer("grpc", tls=True)
        origin = self.fixture.origin()
        request = self.fixture.request(peer, origin, timeout_ms=1500)
        request["transport"]["config"]["service_name"] = "missing-service"
        self.assertNotEqual(self.failure(request), "OperationTimeout")
        self.assertEqual(origin.requests, [])

    def test_untrusted_certificate_wrong_sni_alpn_and_uuid_are_rejected(self):
        peer = self.fixture.peer("grpc", tls=True)
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

    def test_unsupported_grpc_options_and_metadata_fail_without_downgrade(self):
        peer = self.fixture.peer("grpc", tls=True)
        origin = self.fixture.origin()
        for key, value in (("idle_timeout", 30), ("initial_windows_size", 1024),
                           ("permit_without_stream", True)):
            with self.subTest(option=key):
                request = self.fixture.request(peer, origin)
                request["transport"]["config"][key] = value
                self.assertEqual(self.failure(request), "InputSyntax")
        request = self.fixture.request(peer, origin)
        request["transport"]["config"]["headers"] = [["content-type", "text/plain"]]
        self.assertEqual(self.failure(request), "Http2ReservedHeader")
        self.assertEqual(origin.requests, [])

    def test_network_timeout_cancels_accepted_proxy_stream(self):
        peer = self.fixture.peer("grpc", tls=True)
        origin = self.fixture.origin(mode="stall")
        request = self.fixture.request(peer, origin, timeout_ms=250)
        started = time.monotonic()
        self.assertIn(self.failure(request), ("OperationTimeout", "TransportReadTimeout"))
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(origin.requests, ["stall"])
        self.fixture.assert_accepted(peer, origin)

    def test_server_interruption_is_detected_and_a_new_session_works(self):
        peer = self.fixture.peer("grpc", tls=True)
        origin = self.fixture.origin(mode="stall")
        request = self.fixture.request(peer, origin, timeout_ms=4000)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.fixture.run, request)
            self.wait_for(lambda: bool(origin.requests))
            self.fixture.assert_accepted(peer, origin)
            self.fixture.terminate(peer)
            process, report = pending.result(timeout=5)
            self.assertEqual(process.returncode, 1, report)
            self.assertNotEqual(report.get("error"), "OperationTimeout", report)
        restarted = self.fixture.peer("grpc", tls=True)
        recovered = self.fixture.origin()
        self.success(self.fixture.request(restarted, recovered))
        self.fixture.assert_accepted(restarted, recovered)

    def test_truncated_target_response_is_not_successful_proxy_result(self):
        peer = self.fixture.peer("grpc", tls=True)
        origin = self.fixture.origin(mode="disconnect")
        self.failure(self.fixture.request(peer, origin, timeout_ms=1500))
        self.assertEqual(origin.requests, ["disconnect"])
        self.fixture.assert_accepted(peer, origin)


if __name__ == "__main__":
    unittest.main(verbosity=2)
