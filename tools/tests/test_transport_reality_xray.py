"""C6 REALITY with native gRPC/XHTTP against the locked official Xray server.

The unmodified official executable handles REALITY, VLESS authentication and
transport framing. Reuse the established ticket-free TLS 1.3 camouflage target,
ephemeral credentials, exact loopback routing and authenticated-handshake
observations. The native Rust example remains the only proxy client.
"""

import concurrent.futures
import copy
import hashlib
import socket
import subprocess
import time
import unittest

from test_reality_runtime import SNI, XrayRuntimePeer, b64url, write_json
from transport_peer import Fixture, HTTP_BODY, pattern_hash


class _TransportRealityPeer(XrayRuntimePeer):
    """Extend only the existing fixture's raw-only transport configuration."""

    def __init__(self, fixture, network, ports, *, mode="tun", fingerprint="rustls", flow=""):
        fixture.serial += 1
        identity = f"reality-{fixture.serial:02d}-{network}-{mode}-{fingerprint}"
        super().__init__(fixture.xray, fixture.folder / identity, fixture.evidence,
                         identity, ports, fingerprint=fingerprint, flow=flow)
        self.network, self.mode = network, mode
        self.camouflage.context.set_alpn_protocols(["h2"])
        self.log_path = fixture.evidence / f"{identity}-process.log"
        self.access_path = fixture.evidence / f"{identity}-access.log"

    def start(self):
        outbounds, rules = self.outbound_routes()
        stream = {"network": self.network, "security": "reality", "realitySettings": {
            "show": True, "target": f"127.0.0.1:{self.camouflage.port}",
            "serverNames": [SNI], "privateKey": self.private_key,
            "shortIds": [self.short_id], "maxTimeDiff": 60000}}
        if self.network == "grpc":
            stream["grpcSettings"] = {"serviceName": "swirl-reality"}
        elif self.network == "xhttp":
            stream["xhttpSettings"] = {"host": "transport.fixture.invalid",
                                       "path": "/reality/nested", "mode": "stream-one"}
        elif self.network != "raw":
            raise AssertionError("unsupported REALITY test-server transport")
        client = {"id": self.uuid}
        if self.flow:
            client["flow"] = self.flow
        config = {
            "log": {"loglevel": "debug", "access": str(self.access_path)},
            "inbounds": [{"listen": "127.0.0.1", "port": self.port, "protocol": "vless",
                          "settings": {"clients": [client], "decryption": "none"},
                          "streamSettings": stream}],
            "outbounds": outbounds, "routing": {"domainStrategy": "AsIs", "rules": rules},
        }
        config_path = self.folder / "xray-config.json"
        write_json(config_path, config)
        checked = subprocess.run([str(self.binary), "run", "-test", "-config", str(config_path)],
                                 capture_output=True, text=True, timeout=10)
        if checked.returncode:
            raise AssertionError("official Xray rejected the REALITY transport fixture")
        self.log = self.log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen([str(self.binary), "run", "-config", str(config_path)],
                                        stdout=self.log, stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError("official REALITY transport server exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.02)
        raise AssertionError("official REALITY transport server startup deadline")

    def native(self, version):
        alpn = ["h2"] if self.fingerprint == "rustls" else ["h2", "http/1.1"]
        outbound = {"type": "vless", "host": "127.0.0.1", "port": self.port,
                    "uuid": self.uuid, "reality": {
                        "server_name": SNI, "public_key": self.public_key,
                        "short_id": self.short_id, "fingerprint": self.fingerprint,
                        "alpn": alpn}}
        if self.network == "grpc":
            transport = {"type": "grpc", "config": {
                "authority": "transport.fixture.invalid", "service_name": "swirl-reality",
                "mode": self.mode, "headers": []}}
        elif self.network == "xhttp":
            transport = {"type": "xhttp", "config": {
                "host": "transport.fixture.invalid", "path": "/reality/nested",
                "mode": "stream-one", "headers": []}}
        else:
            transport = {"type": "tcp"}
        if self.flow:
            outbound["flow"] = self.flow
        return {"process": self.process, "output": self.log, "access": self.access_path,
                "error": self.log_path, "label": self.identity, "port": self.port,
                "host": "127.0.0.1", "protocol": "vless", "network": self.network,
                "tls": False, "reality": True, "version": version,
                "outbound": outbound, "transport": transport}


class RealityTransportXrayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture("C6-reality")
        self.addCleanup(self.fixture.close)

    def peer(self, network, origins, *, mode="tun", fingerprint="rustls", flow=""):
        runtime = _TransportRealityPeer(self.fixture, network,
                                        [origin.target_port for origin in origins],
                                        mode=mode, fingerprint=fingerprint, flow=flow)
        self.addCleanup(runtime.close)
        runtime.start()
        peer = runtime.native(self.fixture.version)
        self.fixture.peers.append(peer)
        return peer, runtime

    def success(self, request, *, size=None):
        process, report = self.fixture.run(request)
        self.assertEqual(process.returncode, 0, (report, process.stderr))
        self.assertTrue(report["ok"])
        self.assertEqual(report["downloaded"], len(HTTP_BODY) if size is None else size)
        self.assertEqual(report["sha256"], hashlib.sha256(HTTP_BODY).hexdigest()
                         if size is None else pattern_hash(size))
        if size is not None:
            self.assertEqual(report["uploaded"], size + 8)
        self.assertEqual(report["close"], "cancelled" if request["mode"] == "cancel" else "clean", report)
        self.assertEqual(report.get("remaining_tasks", 0), 0, report)
        return report

    def failure(self, request):
        process, report = self.fixture.run(request)
        self.assertEqual(process.returncode, 1, (report, process.stderr))
        self.assertFalse(report["ok"], report)
        self.assertIsInstance(report["error"], str)
        return report["error"]

    def authenticated(self, peer, runtime, origins):
        for origin in origins:
            self.fixture.assert_accepted(peer, origin)
        report = runtime.observations()
        self.assertGreaterEqual(report["reality_authenticated_sessions"], len(origins), report)
        self.assertGreaterEqual(report["client_finished_verified_sessions"], len(origins), report)
        self.assertGreaterEqual(report["vless_accepted_sessions"], len(origins), report)
        self.assertEqual(report["camouflage_application_bytes"], 0, report)
        self.assertEqual(report["camouflage_record_size_failures"], 0, report)

    def test_grpc_tun_and_multi_with_http_and_verified_https(self):
        for mode in ("tun", "tun_multi"):
            with self.subTest(mode=mode):
                origins = [self.fixture.origin(), self.fixture.origin(tls=True)]
                peer, runtime = self.peer("grpc", origins, mode=mode)
                for origin in origins:
                    self.success(self.fixture.request(peer, origin))
                    self.fixture.assert_origin_closed(origin)
                self.authenticated(peer, runtime, origins)

    def test_raw_reality_authenticated_http_regression(self):
        origin = self.fixture.origin()
        peer, runtime = self.peer("raw", [origin])
        self.success(self.fixture.request(peer, origin))
        self.authenticated(peer, runtime, [origin])
        self.fixture.assert_origin_closed(origin)

    def test_raw_reality_vision_authenticated_https_regression(self):
        origin = self.fixture.origin(tls=True)
        peer, runtime = self.peer("raw", [origin], fingerprint="chrome_133",
                                  flow="xtls-rprx-vision")
        self.success(self.fixture.request(peer, origin))
        self.authenticated(peer, runtime, [origin])
        self.fixture.assert_origin_closed(origin)
        observations = runtime.observations()
        self.assertGreater(observations["vision_padding_events"], 0, observations)
        self.assertGreater(observations["vision_unpadding_events"], 0, observations)

    def test_xhttp_stream_one_http_https_and_large_duplex(self):
        origins = [self.fixture.origin(), self.fixture.origin(tls=True),
                   self.fixture.origin(mode="echo")]
        peer, runtime = self.peer("xhttp", origins)
        for origin in origins[:2]:
            self.success(self.fixture.request(peer, origin))
            self.fixture.assert_origin_closed(origin)
        size = 4 * 1024 * 1024
        self.success(self.fixture.request(peer, origins[2], mode="echo", size=size), size=size)
        self.fixture.assert_origin_closed(origins[2])
        self.authenticated(peer, runtime, origins)
        self.assertEqual(origins[2].received, size)

    def test_chrome_133_h2_profile_is_preserved_for_both_transports(self):
        for network in ("grpc", "xhttp"):
            with self.subTest(network=network):
                origin = self.fixture.origin()
                peer, runtime = self.peer(network, [origin], fingerprint="chrome_133")
                self.success(self.fixture.request(peer, origin))
                self.fixture.assert_origin_closed(origin)
                self.authenticated(peer, runtime, [origin])
                self.assertEqual(runtime.observations()["client_hello_profile"], "chrome_133")

    def test_parallel_bidirectional_streams_and_explicit_client_cancel(self):
        for network in ("grpc", "xhttp"):
            with self.subTest(network=network):
                origin = self.fixture.origin(mode="echo")
                peer, runtime = self.peer(network, [origin], mode="tun_multi")
                size = 512 * 1024
                requests = [self.fixture.request(peer, origin, mode="cancel", size=size)
                            for _ in range(4)]
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    reports = list(pool.map(lambda request: self.success(request, size=size), requests))
                self.assertEqual(len(reports), 4)
                self.assertEqual(origin.received, size * 4)
                self.authenticated(peer, runtime, [origin])

    def test_empty_rustls_alpn_derives_h2_and_explicit_http1_offer_is_rejected(self):
        for network in ("grpc", "xhttp"):
            with self.subTest(network=network):
                origin = self.fixture.origin()
                peer, runtime = self.peer(network, [origin])
                request = self.fixture.request(peer, origin)
                request["outbound"]["reality"]["alpn"] = []
                self.success(request)
                self.authenticated(peer, runtime, [origin])
                self.fixture.assert_origin_closed(origin)
                request = self.fixture.request(peer, origin)
                request["outbound"]["reality"]["alpn"] = ["http/1.1"]
                self.assertEqual(self.failure(request), "RealityAlpnUnsupported")
                self.assertEqual(origin.requests, ["http"])

    def test_bad_public_key_short_id_sni_and_proxy_authentication_fail_closed(self):
        for network in ("grpc", "xhttp"):
            with self.subTest(network=network):
                origin = self.fixture.origin()
                peer, runtime = self.peer(network, [origin])
                for field in ("public_key", "short_id", "server_name", "uuid"):
                    with self.subTest(field=field):
                        request = self.fixture.request(peer, origin, timeout_ms=2000)
                        if field == "uuid":
                            request["outbound"]["uuid"] = "ffeeddcc-bbaa-9988-7766-554433221100"
                        else:
                            request["outbound"]["reality"][field] = {
                                "public_key": b64url(bytes(range(1, 33))),
                                "short_id": "01" if runtime.short_id != "01" else "02",
                                "server_name": "wrong-reality.fixture.invalid",
                            }[field]
                        self.failure(request)
                self.assertEqual(origin.requests, [])
                self.assertEqual(runtime.camouflage.application_bytes, 0)

    def test_unsupported_transport_vision_and_spider_options_are_explicit_errors(self):
        origin = self.fixture.origin()
        peer, runtime = self.peer("grpc", [origin])
        unsupported = [
            {"type": "websocket", "settings": {"host": "transport.fixture.invalid", "path": "/"}},
            {"type": "httpupgrade", "config": {"host": "transport.fixture.invalid", "path": "/"}},
            {"type": "http2", "config": {"host": "transport.fixture.invalid", "path": "/"}},
        ]
        for transport in unsupported:
            with self.subTest(transport=transport["type"]):
                request = self.fixture.request(peer, origin)
                request["transport"] = transport
                self.assertEqual(self.failure(request), "RealityTransportUnsupported")
        for transport in (peer["transport"], {"type": "xhttp", "config": {
                "host": "transport.fixture.invalid", "path": "/", "mode": "stream-one"}}):
            request = self.fixture.request(peer, origin)
            request["transport"] = copy.deepcopy(transport)
            request["outbound"]["flow"] = "xtls-rprx-vision"
            self.assertEqual(self.failure(request), "VisionTransportUnsupported")
        for name in ("spiderX", "spider_x"):
            request = self.fixture.request(peer, origin)
            request["outbound"]["reality"][name] = "/unsupported"
            self.assertEqual(self.failure(request), "InputSyntax")
        request = self.fixture.request(peer, origin)
        request["outbound"]["reality"]["fingerprint"] = "safari"
        self.assertEqual(self.failure(request), "RealityFingerprintUnsupported")
        self.assertEqual(origin.requests, [])
        self.assertEqual(runtime.camouflage.application_bytes, 0)

    def test_https_destination_certificate_error_remains_fatal_inside_reality(self):
        for network in ("grpc", "xhttp"):
            with self.subTest(network=network):
                origin = self.fixture.origin(tls=True)
                peer, runtime = self.peer(network, [origin])
                request = self.fixture.request(peer, origin)
                request["target_tls"]["ca_der_base64"] = None
                self.failure(request)
                self.fixture.assert_accepted(peer, origin)
                self.assertEqual(origin.requests, [])
                self.assertEqual(runtime.camouflage.application_bytes, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
