"""Subscription JSON -> native config -> ordinary Core start -> official server.

The exported configuration is passed unmodified to Core. There is no external
transport map, no post-export certificate injection and no third-party client.
The official TLS usage=verify inline CA option supplies fixture trust at import.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

import test_quic_core as core_fixture
import test_vmess_xray as vmess_fixture
from test_rust_core import exact, header
from transport_peer import Fixture, HTTP_BODY, XRAY, XRAY_LEGACY, pattern_hash


class ImportedTransportXrayTests(unittest.TestCase):
    command = core_fixture.QuicCoreTests.command
    stop = core_fixture.QuicCoreTests.stop
    close_runtime = core_fixture.QuicCoreTests.close_runtime
    finite_echo_origin = vmess_fixture._VmessXrayBase.finite_echo_origin
    records = []

    @classmethod
    def setUpClass(cls):
        cls.harness = Path(os.environ["SWIRL_TRANSPORT_RUNTIME"]).resolve(strict=True)
        cls.inspector = Path(os.environ["SWIRL_INSPECT_BINARY"]).resolve(strict=True)
        cls.xray = Path(os.environ["SWIRL_XRAY_BINARY"]).resolve(strict=True)
        cls.legacy = Path(os.environ["SWIRL_XRAY_LEGACY_BINARY"]).resolve(strict=True)
        Fixture._version(str(cls.xray), XRAY)
        Fixture._version(str(cls.legacy), XRAY_LEGACY)

    def setUp(self):
        self.fixture = Fixture("X14-A5-imported-transport")
        self.addCleanup(self.fixture.close)
        self.associations = []
        self.stderr = tempfile.TemporaryFile()
        self.runtime = subprocess.Popen([str(self.harness)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.stderr, text=True)
        self.responses = queue.Queue(maxsize=32)

        def reader():
            for line in self.runtime.stdout:
                self.responses.put(line)
            self.responses.put(None)

        self.reader = threading.Thread(target=reader, daemon=True)
        self.reader.start()
        self.addCleanup(self.close_runtime)

    def peer(self, protocol, network):
        return self.fixture.peer(network, protocol=protocol, tls=True, legacy=network == "h2",
            host="import.fixture.invalid", path="/import/nested", service_name="import-service")

    def source(self, peer, *, legacy_envelope=False):
        stream = copy.deepcopy(peer["config"]["inbounds"][0]["streamSettings"])
        stream["tlsSettings"] = {
            "serverName": "localhost", "alpn": peer["outbound"]["tls"]["alpn"],
            "certificates": [{"usage": "verify", "certificate": self.fixture.ca_pem.splitlines()}],
        }
        network = peer["network"]
        if network == "grpc":
            stream["grpcSettings"]["authority"] = "import.fixture.invalid"
            stream["grpcSettings"]["user_agent"] = "Swirl-import-native-test"
        elif network == "h2":
            stream["httpSettings"]["headers"] = {"x-swirl-import": ["first", "second"]}
        else:
            field = "httpupgradeSettings" if network == "httpupgrade" else "xhttpSettings"
            stream[field]["headers"] = {"x-swirl-import": "native"}
        endpoint = {"address": peer["host"], "port": peer["port"]}
        if peer["protocol"] == "vless":
            endpoint["users"] = [{"id": peer["outbound"]["uuid"], "encryption": "none"}]
            settings = {"vnext": [endpoint]}
        else:
            endpoint["password"] = peer["outbound"]["password"]
            settings = {"servers": [endpoint]}
        node = {"tag": "synthetic-import", "protocol": peer["protocol"],
                "settings": settings, "streamSettings": stream}
        # Both envelope forms are real legacy/common Xray/V2Ray JSON forms.
        # V2Ray v5 transportSettings remains a distinct, unsupported dialect.
        return {"outbound": node} if legacy_envelope else {"outbounds": [node]}

    def export(self, source, *, success=True):
        result = subprocess.run([str(self.inspector), "--xray-json", "--private-json",
            "--native-node", "0", "--listen", "127.0.0.1:0"], input=json.dumps(source),
            text=True, capture_output=True, timeout=10)
        exported = json.loads(result.stdout)
        report = exported.get("report", exported)
        self.assertEqual(result.returncode, 0 if success else 1, report)
        self.assertEqual(report["network_verified"], False)
        self.assertEqual(report["ok"], success, report)
        if not success:
            self.assertNotIn("native_config", exported)
            self.assertNotIn("raw_json", exported)
            codes = [issue["code"] for node in report.get("nodes", []) for issue in node["diagnostics"]]
            codes.extend(issue["code"] for issue in report.get("diagnostics", []))
            self.records.append({"case": self._testMethodName, "native_export": False, "diagnostics": codes})
            return None
        native = exported["native_config"]
        outbound = native["nodes"][0]["outbound"]
        self.assertEqual(outbound["tls"]["ca_der_base64"], self.fixture.ca)
        self.assertIsNotNone(outbound.get("transport"))
        self.assertEqual(report["native_executable_nodes"], 1)
        return native

    def start(self, config):
        # Imported outbounds reach ordinary Core start without a separate
        # transports argument, CA patch, credential rewrite or fallback.
        result = self.command(op="start", config=config)
        self.assertTrue(result["ok"], result)
        self.port = int(result["status"]["address"].rsplit(":", 1)[1])
        node = config["nodes"][0]["outbound"]
        self.protocol = node["type"] + ":" + node["transport"]["type"]
        self.protocol += ":tls" if node.get("tls") else ":plain"

    @contextlib.contextmanager
    def running(self, config):
        self.start(config)
        try:
            yield
        finally:
            self.stop()

    def tunnel(self, origin):
        stream = socket.create_connection(("127.0.0.1", self.port), timeout=6)
        stream.settimeout(6)
        destination = f"127.0.0.1:{origin.server_address[1]}"
        stream.sendall(f"CONNECT {destination} HTTP/1.1\r\nHost: {destination}\r\n\r\n".encode())
        try:
            self.assertIn(b"200 Connection Established", header(stream))
        except BaseException:
            stream.close()
            raise
        return stream

    def application(self, origin):
        stream = self.tunnel(origin)
        if origin.context:
            context = ssl.create_default_context(cadata=self.fixture.ca_pem)
            stream = context.wrap_socket(stream, server_hostname="localhost")
        with stream:
            stream.sendall(b"GET /transport HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            self.assertIn(b"200 OK", header(stream))
            body = exact(stream, len(HTTP_BODY))
            self.assertEqual(hashlib.sha256(body).hexdigest(), hashlib.sha256(HTTP_BODY).hexdigest())
            if origin.context:
                plain = stream.unwrap()
                plain.close()
            else:
                stream.shutdown(socket.SHUT_WR)
                self.assertEqual(stream.recv(1), b"")
        self.fixture.assert_origin_closed(origin)

    def test_required_combinations_import_to_core_http_https_and_normal_close(self):
        for protocol, network in (("vless", "grpc"), ("trojan", "grpc"),
                                  ("vless", "h2"), ("vless", "httpupgrade"), ("vless", "xhttp")):
            with self.subTest(protocol=protocol, network=network):
                peer = self.peer(protocol, network)
                source = self.source(peer)
                native = self.export(source)
                expected = "http2" if network == "h2" else network
                mapped = native["nodes"][0]["outbound"]["transport"]
                self.assertEqual(mapped["type"], expected)
                if network == "grpc":
                    self.assertEqual(mapped["config"]["service_name"], "import-service")
                    self.assertIn(["user-agent", "Swirl-import-native-test"], mapped["config"]["headers"])
                else:
                    self.assertEqual(mapped["config"]["host"], "import.fixture.invalid")
                    self.assertEqual(mapped["config"]["path"], "/import/nested")
                    self.assertTrue(mapped["config"]["headers"])
                with self.running(native):
                    for tls in (False, True):
                        origin = self.fixture.origin(tls=tls)
                        self.application(origin)
                        self.fixture.assert_accepted(peer, origin)
                        self.records.append({"case": self._testMethodName, "protocol": protocol,
                            "transport": expected, "server": peer["version"], "application_tls": tls,
                            "downloaded": len(HTTP_BODY), "close": "clean", "native_export": True})

    def test_clash_grpc_import_reaches_official_server_without_transport_patch(self):
        # Regression for the formerly unsupported Clash gRPC product case. A
        # raw VLESS fixture cannot prove gRPC interoperability, so use the same
        # pinned official server as the retained Xray JSON transport cases.
        peer = self.fixture.peer("grpc", protocol="vless", service_name="synthetic")
        node = {"name": "synthetic-clash-grpc", "type": "vless",
                "server": peer["host"], "port": peer["port"],
                "uuid": peer["outbound"]["uuid"], "network": "grpc",
                "grpc-opts": {"grpc-service-name": "synthetic",
                              "grpc-user-agent": "Swirl-synthetic-product-chain",
                              "ping-interval": 0}}
        result = subprocess.run([str(self.inspector), "--private-json"],
            input=json.dumps({"proxies": [node]}), text=True, capture_output=True, timeout=10)
        exported = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, exported.get("report"))
        self.assertTrue(exported["report"]["parsed"])
        self.assertEqual(exported["nodes"], [node])
        self.assertTrue(exported["report"]["nodes"][0]["native_tcp_candidate"])
        self.assertFalse(exported["report"]["nodes"][0]["real_network_verified"])
        outbound = exported["tcpCandidates"][0]
        self.assertEqual((outbound["host"], outbound["port"], outbound["uuid"]),
                         (peer["host"], peer["port"], peer["outbound"]["uuid"]))
        self.assertEqual(outbound["transport"], {"type": "grpc", "config": {
            "authority": f'{peer["host"]}:{peer["port"]}', "service_name": "synthetic",
            "mode": "tun", "headers": [["user-agent", "Swirl-synthetic-product-chain"]]}})
        native = {"schema": 1, "listen": "127.0.0.1:0", "selected": "A",
                  "nodes": [{"id": "A", "outbound": outbound}]}
        with self.running(native):
            for tls in (False, True):
                origin = self.fixture.origin(tls=tls)
                self.application(origin)
                self.fixture.assert_accepted(peer, origin)
                self.records.append({"case": self._testMethodName, "source": "clash-json",
                    "protocol": "vless", "transport": "grpc", "server": peer["version"],
                    "application_tls": tls, "downloaded": len(HTTP_BODY), "close": "clean",
                    "native_export": True, "post_export_modifications": False})

    def test_four_mib_each_way_after_import_with_application_completed_close(self):
        size = 4 * 1024 * 1024
        for protocol, network in (("vless", "grpc"), ("trojan", "grpc"),
                                  ("vless", "h2"), ("vless", "httpupgrade"), ("vless", "xhttp")):
            with self.subTest(protocol=protocol, network=network):
                peer, origin = self.peer(protocol, network), self.finite_echo_origin()
                native = self.export(self.source(peer))
                with self.running(native):
                    started = time.monotonic()
                    digest = hashlib.sha256()
                    with self.tunnel(origin) as stream:
                        stream.sendall(size.to_bytes(8, "big"))
                        for offset in range(0, size, 16384):
                            data = bytes(((position * 31 + 17) % 251) for position in range(offset, min(offset + 16384, size)))
                            stream.sendall(data)
                            reply = exact(stream, len(data))
                            self.assertEqual(reply, data)
                            digest.update(reply)
                        # The application is complete before EOF; this does not
                        # change or reclassify the retained Xray half-close issue.
                        self.assertEqual(stream.recv(1), b"")
                        stream.shutdown(socket.SHUT_WR)
                    self.assertEqual(digest.hexdigest(), pattern_hash(size))
                    self.assertEqual(origin.received, size)
                    self.fixture.assert_origin_closed(origin)
                    self.fixture.assert_accepted(peer, origin)
                    self.records.append({"case": self._testMethodName, "protocol": protocol,
                        "transport": network, "server": peer["version"], "uploaded": size,
                        "downloaded": size, "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                        "close": "application-complete", "native_export": True})

    def test_legacy_v2ray_envelope_and_concurrent_core_sessions(self):
        peer = self.peer("vless", "h2")
        native = self.export(self.source(peer, legacy_envelope=True))
        with self.running(native):
            origins = [self.fixture.origin(tls=True) for _ in range(4)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
                list(workers.map(self.application, origins))
            for origin in origins:
                self.fixture.assert_accepted(peer, origin)
        self.records.append({"case": self._testMethodName, "source": "legacy-v2ray-outbound",
            "server": peer["version"], "concurrent_native_sessions": 4, "native_export": True})

    def test_unsupported_security_transport_modes_and_options_block_native_export(self):
        peer = self.peer("vless", "xhttp")
        original = self.source(peer)
        cases = []
        for mode in ("auto", "stream-up", "packet-up"):
            value = copy.deepcopy(original)
            value["outbounds"][0]["streamSettings"]["xhttpSettings"]["mode"] = mode
            cases.append(value)
        for key, value in (("extra", {}), ("downloadSettings", {}), ("xmux", {})):
            source = copy.deepcopy(original)
            source["outbounds"][0]["streamSettings"]["xhttpSettings"][key] = value
            cases.append(source)
        for key, value in (("fingerprint", "chrome"), ("allowInsecure", True), ("disableSystemRoot", True)):
            source = copy.deepcopy(original)
            source["outbounds"][0]["streamSettings"]["tlsSettings"][key] = value
            cases.append(source)
        upgrade = self.source(self.peer("vless", "httpupgrade"))
        for key, value in (("maxEarlyData", 2048), ("earlyDataHeaderName", "Sec-WebSocket-Protocol")):
            source = copy.deepcopy(upgrade)
            source["outbounds"][0]["streamSettings"]["httpupgradeSettings"][key] = value
            cases.append(source)
        source = copy.deepcopy(upgrade)
        source["outbounds"][0]["streamSettings"]["httpupgradeSettings"]["path"] += "?ed=2048"
        cases.append(source)
        for index, source in enumerate(cases):
            with self.subTest(index=index):
                self.export(source, success=False)

    def test_wrong_imported_service_path_sni_and_uuid_do_not_reach_the_target(self):
        for network in ("grpc", "h2", "httpupgrade", "xhttp"):
            peer, origin = self.peer("vless", network), self.fixture.origin()
            base = self.source(peer)
            for problem in ("transport", "sni", "uuid"):
                with self.subTest(network=network, problem=problem):
                    source = copy.deepcopy(base)
                    node = source["outbounds"][0]
                    if problem == "sni":
                        node["streamSettings"]["tlsSettings"]["serverName"] = "wrong.invalid"
                    elif problem == "uuid":
                        node["settings"]["vnext"][0]["users"][0]["id"] = "ffeeddcc-bbaa-9988-7766-554433221100"
                    else:
                        field = {"grpc": "grpcSettings", "h2": "httpSettings",
                                 "httpupgrade": "httpupgradeSettings", "xhttp": "xhttpSettings"}[network]
                        key = "serviceName" if network == "grpc" else "path"
                        node["streamSettings"][field][key] = "wrong-service" if network == "grpc" else "/wrong/path"
                    native = self.export(source)
                    with self.running(native):
                        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as stream:
                            destination = f"127.0.0.1:{origin.server_address[1]}"
                            stream.sendall(f"CONNECT {destination} HTTP/1.1\r\nHost: {destination}\r\n\r\n".encode())
                            response = header(stream)
                            if b"200 Connection Established" in response:
                                stream.sendall(b"GET /transport HTTP/1.1\r\nHost: localhost\r\n\r\n")
                                try:
                                    self.assertEqual(stream.recv(1), b"")
                                except (ConnectionResetError, ConnectionAbortedError):
                                    # Winsock can report WSAECONNABORTED (10053)
                                    # when the relay closes after authentication
                                    # rejection. Only terminal closure is valid:
                                    # timeouts and received application bytes
                                    # still fail, as does any origin request.
                                    pass
                            else:
                                self.assertIn(b"502 Bad Gateway", response)
                        self.assertEqual(origin.requests, [])
                        self.records.append({"case": self._testMethodName, "transport": network,
                            "negative_path": problem, "target_requests": 0, "native_export": True})

    @classmethod
    def tearDownClass(cls):
        if path := os.environ.get("SWIRL_IMPORTED_TRANSPORT_EVIDENCE"):
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps({"runtime": "Swirl Rust Core ordinary start",
                "runtime_sha256": hashlib.sha256(cls.harness.read_bytes()).hexdigest(),
                "inspector_sha256": hashlib.sha256(cls.inspector.read_bytes()).hexdigest(),
                "platform": platform.platform(), "server_versions": [XRAY, XRAY_LEGACY],
                "qt_product_acceptance": False, "post_export_modifications": False,
                "external_transport_map": False, "records": cls.records}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
