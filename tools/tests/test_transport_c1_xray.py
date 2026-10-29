"""C1 native Runtime interoperability with the unmodified, pinned Xray server.

Requires SWIRL_RUST_HARNESS, SWIRL_TRANSPORT_CLIENT and SWIRL_XRAY_BINARY (Xray v26.10.21,
commit 1b1647cd9ddf0abc34b981d4611fc03bcac1ca74). All credentials,
certificates, listeners and destinations are synthetic loopback fixtures.
Xray is only the independent server; the client is the existing Rust Runtime.
Set SWIRL_C1_EVIDENCE to preserve server logs and an exact test summary.
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from test_rust_core import certificates, exact, header


UUID = "00112233-4455-6677-8899-aabbccddeeff"
PASSWORD = "c1-synthetic-fixture-only"
BODY = bytes(range(256)) * 513
RECORDS = []


class Origin(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True

    def handle_error(self, request, address):
        self.errors.append(f"{type(sys.exc_info()[1]).__name__}: {sys.exc_info()[1]}")


class OriginHandler(socketserver.BaseRequestHandler):
    def handle(self):
        stream = self.request
        stream.settimeout(10)
        if self.server.tls:
            stream = self.server.tls.wrap_socket(stream, server_side=True)
        try:
            if self.server.echo:
                self.server.requests.append("echo")
                while data := stream.recv(16384):
                    self.server.received += len(data)
                    stream.sendall(data)
                return
            request = header(stream)
            if not request.startswith(b"GET /c1-origin HTTP/1.1\r\n"):
                raise AssertionError("unexpected origin request")
            self.server.requests.append("https" if self.server.tls else "http")
            stream.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: "
                           + str(len(BODY)).encode()
                           + b"\r\nConnection: close\r\n\r\n" + BODY)
            if self.server.tls:
                plain = stream.unwrap()
                self.server.tls_closes += 1
                self.server.close_complete.set()
                plain.close()
        except (ConnectionError, EOFError, TimeoutError):
            if not self.server.echo:
                raise
        finally:
            stream.close()


class C1XrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="swirl-c1-xray-")
        cls.folder = Path(cls.temp.name)
        cls.context, cls.ca, cls.ca_pem = certificates(cls.temp.name)
        cls.xray = os.environ["SWIRL_XRAY_BINARY"]
        cls.harness = os.environ["SWIRL_RUST_HARNESS"]
        cls.client = os.environ["SWIRL_TRANSPORT_CLIENT"]
        cls.version = subprocess.run([cls.xray, "version"], check=True,
                                     capture_output=True, text=True).stdout
        if "Xray 26.10.21" not in cls.version or "1b1647c" not in cls.version:
            raise AssertionError("fixture requires the pinned official Xray v26.10.21")
        cls.evidence = Path(os.environ.get("SWIRL_C1_EVIDENCE", cls.temp.name))
        cls.evidence.mkdir(parents=True, exist_ok=True)
        cls.serial = 0

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.origins = []
        self.peers = []
        self.handle = None
        self.runtime = subprocess.Popen([self.harness], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True)
        self.addCleanup(self.close)

    def close(self):
        self.runtime.stdin.close()
        try:
            self.runtime.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.runtime.kill()
            self.runtime.wait(timeout=5)
            self.fail("Runtime failed to release its tasks")
        finally:
            for peer in self.peers:
                if peer["process"].poll() is None:
                    peer["process"].terminate()
                    peer["process"].wait(timeout=5)
                peer["output"].close()
            for origin in self.origins:
                origin.shutdown()
                origin.server_close()
        stderr = self.runtime.stderr.read()
        self.runtime.stdout.close()
        self.runtime.stderr.close()
        self.assertEqual(self.runtime.returncode, 0, stderr)
        for origin in self.origins:
            self.assertEqual(origin.errors, [])

    def command(self, **value):
        self.runtime.stdin.write(json.dumps(value) + "\n")
        self.runtime.stdin.flush()
        return json.loads(self.runtime.stdout.readline())

    def origin(self, *, tls=False, echo=False):
        result = Origin(("127.0.0.1", 0), OriginHandler)
        result.tls = self.context if tls else None
        result.echo = echo
        result.requests, result.errors = [], []
        result.received = result.tls_closes = 0
        result.close_complete = threading.Event()
        threading.Thread(target=result.serve_forever, daemon=True).start()
        self.origins.append(result)
        return result

    def peer(self, protocol="vless", network="raw", tls=False,
             listen="127.0.0.1", authority="ws.fixture.invalid"):
        with socket.socket(socket.AF_INET6 if ":" in listen else socket.AF_INET) as probe:
            probe.bind((listen, 0))
            port = probe.getsockname()[1]
        host_config = authority
        if authority.startswith("[") and authority.endswith("]"):
            # Xray's IsValidHTTPHost uses SplitHostPort whenever ':' exists;
            # supply an explicit authority port and the bare configured host.
            host_config = authority[1:-1]
            authority = f"{authority}:{port}"
        type(self).serial += 1
        label = f"{self.serial:02d}-{protocol}-{network}-{'tls' if tls else 'plain'}"
        access = self.evidence / f"{label}-access.log"
        error = self.evidence / f"{label}-error.log"
        output = open(self.evidence / f"{label}-process.log", "w", encoding="utf-8")
        security = {"network": network, "security": "tls" if tls else "none"}
        if tls:
            security["tlsSettings"] = {
                "alpn": ["http/1.1"],
                "certificates": [{"certificateFile": str(self.folder / "leaf.pem"),
                                  "keyFile": str(self.folder / "leaf.key")}],
            }
        if network == "ws":
            security["wsSettings"] = {"path": "/c1/nested/ws", "host": host_config}
        settings = {"clients": [{"id": UUID}] , "decryption": "none"}
        if protocol == "trojan":
            settings = {"clients": [{"password": PASSWORD}]}
        config = {"log": {"access": str(access), "error": str(error), "loglevel": "debug"},
                  "inbounds": [{"listen": listen, "port": port, "protocol": protocol,
                                "settings": settings, "streamSettings": security}],
                  # v26.10.21 defaults to blocking private targets for proxy
                  # inbounds. Authorize only the synthetic loopback origins.
                  "outbounds": [{"protocol": "freedom", "settings": {"finalRules": [
                      {"action": "allow", "network": "tcp", "ip": ["127.0.0.1/32", "::1/128"]}
                  ]}}]}
        path = self.folder / f"{label}.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        process = subprocess.Popen([self.xray, "run", "-config", str(path)],
                                   stdout=output, stderr=subprocess.STDOUT)
        result = {"process": process, "output": output, "access": access, "label": label,
                  "port": port, "host": listen, "tls": tls, "network": network,
                  "protocol": protocol, "authority": authority}
        self.peers.append(result)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail(f"pinned Xray exited: {label}")
            try:
                with socket.create_connection((listen, port), timeout=0.2):
                    return result
            except OSError:
                time.sleep(0.02)
        self.fail(f"pinned Xray failed to listen: {label}")

    def outbound(self, peer):
        result = {"type": peer["protocol"], "host": peer["host"], "port": peer["port"]}
        result.update({"uuid": UUID} if peer["protocol"] == "vless" else {"password": PASSWORD})
        if peer["tls"]:
            result["tls"] = {"server_name": "localhost", "alpn": ["http/1.1"],
                             "ca_der_base64": self.ca}
        if peer["network"] == "ws":
            result["websocket"] = {"host": peer["authority"], "path": "/c1/nested/ws"}
        return result

    def start(self, outbound):
        if self.handle is not None:
            self.stop()
        config = {"schema": 1, "listen": "127.0.0.1:0", "selected": "fixture",
                  "nodes": [{"id": "fixture", "outbound": outbound}]}
        result = self.command(op="start", config=config)
        self.assertTrue(result["ok"], result)
        self.handle = result["handle"]
        self.port = int(result["status"]["address"].rsplit(":", 1)[1])

    def stop(self):
        self.assertTrue(self.command(op="stop", handle=self.handle)["ok"])
        self.handle = None
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", self.port), timeout=0.5)

    def tunnel(self, origin):
        stream = socket.create_connection(("127.0.0.1", self.port), timeout=8)
        port = origin.server_address[1]
        stream.sendall(f"CONNECT 127.0.0.1:{port} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
        return stream, header(stream)

    def http(self, origin):
        stream, response = self.tunnel(origin)
        self.assertIn(b"200 Connection Established", response)
        if origin.tls:
            context = ssl.create_default_context(cadata=self.ca_pem)
            stream = context.wrap_socket(stream, server_hostname="localhost")
        with stream:
            stream.sendall(b"GET /c1-origin HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            self.assertIn(b"200 OK", header(stream))
            self.assertEqual(exact(stream, len(BODY)), BODY)
            if origin.tls:
                # WebSocket close terminates both directions. Keep the raw
                # application socket open until its last TLS bytes have been
                # consumed, then initiate transport close; do not demand a TCP
                # half-close from WebSocket.
                with stream.unwrap():
                    self.assertTrue(origin.close_complete.wait(3), origin.errors)

    def assert_accepted(self, peer, count):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            text = peer["access"].read_text(encoding="utf-8") if peer["access"].exists() else ""
            if text.count(" accepted ") >= count:
                RECORDS.append({"case": peer["label"], "protocol": peer["protocol"],
                                "transport": peer["network"], "tls": peer["tls"],
                                "xray_accepted": text.count(" accepted "),
                                "expected_proxy_requests": count})
                return
            time.sleep(0.01)
        self.fail(f"Xray did not record {count} authenticated proxy requests for {peer['label']}")

    def test_http_and_verified_https_through_native_tcp_ws_wss(self):
        for protocol, network, tls in [
            ("vless", "raw", False), ("vless", "raw", True),
            ("vless", "ws", False), ("vless", "ws", True),
            ("trojan", "raw", True), ("trojan", "ws", True),
        ]:
            with self.subTest(protocol=protocol, network=network, tls=tls):
                peer = self.peer(protocol, network, tls)
                self.start(self.outbound(peer))
                plain, secure = self.origin(), self.origin(tls=True)
                self.http(plain)
                self.http(secure)
                self.assertEqual(plain.requests, ["http"])
                self.assertEqual(secure.requests, ["https"])
                self.assert_accepted(peer, 2)
                self.stop()

    def test_additive_selector_raw_alias_and_custom_websocket_headers(self):
        for network, tls in [("raw", False), ("ws", False), ("ws", True)]:
            with self.subTest(network=network, tls=tls):
                peer = self.peer(network=network, tls=tls)
                origin = self.origin()
                outbound = self.outbound(peer)
                transport = {"type": "raw"}
                if network == "ws":
                    transport = {"type": "websocket", "settings": outbound.pop("websocket"),
                                 "headers": [["X-Swirl-Probe", "synthetic-c1"],
                                             ["Origin", "https://fixture.invalid"]]}
                request = {"outbound": outbound, "transport": transport,
                           "target_host": "127.0.0.1", "target_port": origin.server_address[1],
                           "mode": "http", "path": "/c1-origin"}
                result = subprocess.run([self.client], input=json.dumps(request),
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads(result.stdout)
                self.assertTrue(report["ok"], report)
                self.assertEqual(report["downloaded"], len(BODY))
                self.assertEqual(report["sha256"], hashlib.sha256(BODY).hexdigest())
                self.assertEqual(origin.requests, ["http"])
                self.assert_accepted(peer, 1)
                RECORDS[-1]["additive_transport_api"] = True
                RECORDS[-1]["client_report"] = report

    def test_websocket_large_binary_and_eight_concurrent_connections(self):
        for tls in [False, True]:
            peer = self.peer(network="ws", tls=tls)
            self.start(self.outbound(peer))
            origin = self.origin(echo=True)
            data = bytes(range(256)) * 8193

            def echo(payload):
                stream, response = self.tunnel(origin)
                with stream, concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    self.assertIn(b"200", response)
                    sent = pool.submit(stream.sendall, payload)
                    self.assertEqual(exact(stream, len(payload)), payload)
                    sent.result(timeout=8)

            echo(data)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(echo, [data[:65537]] * 8))
            self.assert_accepted(peer, 9)
            self.assertEqual(origin.received, len(data) + 8 * 65537)
            self.stop()

    def test_wrong_host_path_certificate_and_uuid_are_rejected(self):
        peer = self.peer(network="ws", tls=True)
        origin = self.origin(echo=True)
        for field, value in [
            ("path", "/wrong"), ("host", "wrong.fixture.invalid"),
            ("server_name", "wrong.fixture.invalid"), ("ca_der_base64", None),
            ("uuid", "10112233-4455-6677-8899-aabbccddeeff"),
        ]:
            with self.subTest(field=field):
                outbound = self.outbound(peer)
                if field in ("path", "host"):
                    outbound["websocket"][field] = value
                elif field in ("server_name", "ca_der_base64"):
                    outbound["tls"][field] = value
                else:
                    outbound[field] = value
                self.start(outbound)
                stream, response = self.tunnel(origin)
                with stream:
                    if field == "uuid":
                        # VLESS has a lazy response prefix; local CONNECT alone
                        # is not authentication evidence. No origin is reached.
                        stream.sendall(b"invalid-authentication-probe")
                        try:
                            self.assertEqual(stream.recv(64), b"")
                        except ConnectionResetError:
                            pass
                    else:
                        self.assertIn(b"502", response)
                self.assertEqual(origin.requests, [])
                self.stop()

    def test_ipv6_websocket_socket_and_authority(self):
        peer = self.peer(network="ws", tls=True, listen="::1", authority="[::1]")
        self.start(self.outbound(peer))
        origin = self.origin()
        self.http(origin)
        self.assertEqual(origin.requests, ["http"])
        self.assert_accepted(peer, 1)
        self.stop()

    def test_server_interrupt_terminates_active_stream(self):
        peer = self.peer(network="ws", tls=True)
        self.start(self.outbound(peer))
        origin = self.origin(echo=True)
        stream, response = self.tunnel(origin)
        with stream:
            self.assertIn(b"200", response)
            stream.sendall(b"before-interruption")
            self.assertEqual(exact(stream, 19), b"before-interruption")
            self.assert_accepted(peer, 1)
            peer["process"].terminate()
            peer["process"].wait(timeout=5)
            try:
                self.assertEqual(stream.recv(1), b"")
            except ConnectionResetError:
                pass
        self.stop()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(C1XrayTests)
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if destination := os.environ.get("SWIRL_C1_EVIDENCE"):
        Path(destination).mkdir(parents=True, exist_ok=True)
        summary = {"evidence_level": "independent_official_xray_loopback",
                   "public_network_tested": False,
                   "xray_commit": "1b1647cd9ddf0abc34b981d4611fc03bcac1ca74",
                   "xray_version": getattr(C1XrayTests, "version", "unavailable"),
                   "platform": platform.platform(),
                   "rust_harness_sha256": hashlib.sha256(Path(os.environ["SWIRL_RUST_HARNESS"]).read_bytes()).hexdigest(),
                   "tests_run": result.testsRun, "failures": len(result.failures),
                   "errors": len(result.errors), "skipped": len(result.skipped),
                   "elapsed_seconds": time.monotonic() - started,
                   "cases": RECORDS, "exit_code": 0 if result.wasSuccessful() else 1}
        (Path(destination) / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
