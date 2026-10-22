"""VMess AEAD interoperability against the pinned, unmodified official Xray.

Swirl's transport-client is the client, Xray is only the server, and a separate
Python TCP/HTTP(S) origin verifies bytes and closure. Missing tools fail; no
network result comes from a mock, configuration check or handshaking alone.
"""
import argparse
import base64
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import socketserver
import subprocess
import threading
import time
import unittest

from test_rust_core import exact, header
from transport_peer import Fixture, HTTP_BODY, UUID, _Origin, pattern_hash


class _FiniteEchoHandler(socketserver.BaseRequestHandler):
    """A real length-delimited origin which finishes its own response.

    Xray's freedom outbound does not forward a client TCP half-close to the
    target. A separate strict suite below retains that failing acceptance case.
    This origin tests a normal completed application response, including the
    server's authenticated VMess terminal record and the client FIN.
    """
    def handle(self):
        server, stream = self.server, self.request
        stream.settimeout(6)
        with server.lock:
            server.active.add(stream)
            server.requests.append(server.mode)
        try:
            remaining = int.from_bytes(exact(stream, 8), "big")
            if not 0 <= remaining <= 64 * 1024 * 1024:
                raise AssertionError("invalid bounded echo length")
            while remaining:
                data = stream.recv(min(16384, remaining))
                if not data:
                    raise EOFError("truncated origin upload")
                with server.lock:
                    server.received += len(data)
                stream.sendall(data)
                remaining -= len(data)
            stream.shutdown(socket.SHUT_WR)
            if stream.recv(1) == b"":
                with server.lock:
                    server.client_closes += 1
        except (ConnectionError, EOFError, TimeoutError):
            with server.lock:
                server.interruptions += 1
        finally:
            stream.close()
            with server.lock:
                server.active.discard(stream)


class _VmessXrayBase(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture("X14-A2-vmess")
        self.addCleanup(self.fixture.close)

    def peer(self, network="raw", tls=False, **options):
        return self.fixture.peer(network, protocol="vmess", tls=tls, **options)

    def success(self, request, size=None):
        process, report = self.fixture.run(request)
        self.assertEqual(process.returncode, 0, (report, process.stderr))
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["downloaded"], len(HTTP_BODY) if size is None else size)
        self.assertEqual(report["sha256"], hashlib.sha256(HTTP_BODY).hexdigest()
                         if size is None else pattern_hash(size))
        self.assertEqual(report["close"], "clean", report)
        self.assertEqual(report["remaining_tasks"], 0, report)
        return report

    def failure(self, request):
        process, report = self.fixture.run(request)
        self.assertEqual(process.returncode, 1, report)
        self.assertFalse(report["ok"], report)
        return report["error"]

    def finite_echo_origin(self):
        origin = _Origin(("127.0.0.1", 0), _FiniteEchoHandler)
        origin.context, origin.mode = None, "finite-echo"
        origin.requests, origin.errors = [], []
        origin.active, origin.lock = set(), threading.Lock()
        origin.stopped = threading.Event()
        origin.received = origin.client_closes = origin.tls_closes = origin.interruptions = 0
        origin.target_host, origin.target_port = origin.server_address
        origin.worker = threading.Thread(target=origin.serve_forever,
            kwargs={"poll_interval": 0.02}, daemon=True)
        origin.worker.start()
        self.fixture.origins.append(origin)
        return origin


class VmessXrayTests(_VmessXrayBase):

    def test_tcp_tls_ws_wss_aes_and_chacha_authentication_data_and_close(self):
        for network in ("raw", "ws"):
            for tls in (False, True):
                peer = self.peer(network, tls)
                for cipher in ("aes-128-gcm", "chacha20-poly1305"):
                    with self.subTest(network=network, tls=tls, cipher=cipher):
                        origin = self.fixture.origin()
                        request = self.fixture.request(peer, origin)
                        request["outbound"]["security"] = cipher
                        self.success(request)
                        self.fixture.assert_accepted(peer, origin)
                        self.fixture.assert_origin_closed(origin)

    def test_four_transports_four_mib_duplex_and_completed_response_close(self):
        for network in ("raw", "ws"):
            for tls in (False, True):
                with self.subTest(network=network, tls=tls):
                    peer, origin = self.peer(network, tls), self.finite_echo_origin()
                    size = 4 * 1024 * 1024 + 17
                    request = self.fixture.request(peer, origin, mode="echo", size=size)
                    self.success(request, size)
                    self.fixture.assert_accepted(peer, origin)
                    self.assertEqual(origin.received, size)
                    self.fixture.assert_origin_closed(origin)

    def test_https_target_certificate_and_tls_close_over_vmess_tls(self):
        peer, origin = self.peer(tls=True), self.fixture.origin(tls=True)
        self.success(self.fixture.request(peer, origin))
        self.fixture.assert_accepted(peer, origin)
        self.fixture.assert_origin_closed(origin)

    def test_wrong_uuid_never_reaches_origin_on_any_transport(self):
        for network in ("raw", "ws"):
            for tls in (False, True):
                peer, origin = self.peer(network, tls), self.fixture.origin()
                request = self.fixture.request(peer, origin, timeout_ms=1200)
                request["outbound"]["uuid"] = "ffeeddcc-bbaa-9988-7766-554433221100"
                self.failure(request)
                self.assertEqual(origin.requests, [])

    def test_legacy_alterid_and_invalid_cipher_never_dial(self):
        peer, origin = self.peer(), self.fixture.origin()
        for key, value, expected in (
            ("alter_id", 1, "VmessLegacyAlterIdUnsupported"),
            ("security", "none", "VmessCipherUnsupported"),
            ("security", "aes-128-cfb", "VmessCipherUnsupported"),
            ("security", "invalid", "VmessCipherUnsupported"),
            ("uuid", "malformed", "VmessUuid"),
        ):
            request = self.fixture.request(peer, origin)
            request["outbound"][key] = value
            self.assertEqual(self.failure(request), expected)
        self.assertEqual(origin.requests, [])

    def test_untrusted_certificate_and_incorrect_sni_are_rejected(self):
        peer, origin = self.peer(tls=True), self.fixture.origin()
        for case in ("untrusted", "wrong_sni"):
            request = self.fixture.request(peer, origin)
            if case == "untrusted":
                request["outbound"]["tls"]["ca_der_base64"] = None
            else:
                request["outbound"]["tls"]["server_name"] = "wrong.fixture.invalid"
            self.failure(request)
        self.assertEqual(origin.requests, [])

    def test_wrong_websocket_path_is_rejected_without_origin_access(self):
        peer, origin = self.peer("ws", True), self.fixture.origin()
        request = self.fixture.request(peer, origin)
        request["transport"]["settings"]["path"] = "/incorrect-path"
        self.failure(request)
        self.assertEqual(origin.requests, [])

    def test_eight_concurrent_independent_sessions(self):
        peer, origin = self.peer("ws", True), self.finite_echo_origin()
        size = 128 * 1024 + 3
        requests = [self.fixture.request(peer, origin, mode="echo", size=size) for _ in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            reports = list(pool.map(lambda request: self.success(request, size), requests))
        self.assertEqual(len(reports), 8)
        self.assertEqual(origin.received, 8 * size)
        self.fixture.assert_accepted(peer, origin)
        self.fixture.assert_origin_closed(origin, count=8)

    def test_ipv6_peer_and_domain_destination(self):
        peer, origin = self.peer(listen="::1"), self.fixture.origin()
        request = self.fixture.request(peer, origin, target_host="localhost")
        self.success(request)
        self.assertEqual(origin.requests, ["http"])
        self.fixture.assert_origin_closed(origin)

    def test_abrupt_peer_disconnect_and_new_session_recovery(self):
        peer, stalled = self.peer(), self.fixture.origin(mode="stall")
        request = self.fixture.request(peer, stalled, timeout_ms=4000)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.fixture.run, request)
            deadline = time.monotonic() + 2
            while not stalled.requests and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(stalled.requests)
            self.fixture.assert_accepted(peer, stalled)
            self.fixture.terminate(peer)
            process, report = pending.result(timeout=5)
            self.assertEqual(process.returncode, 1, report)
            self.assertNotEqual(report.get("error"), "OperationTimeout", report)
        fresh, origin = self.peer(), self.fixture.origin()
        self.success(self.fixture.request(fresh, origin))
        self.fixture.assert_accepted(fresh, origin)
        self.fixture.assert_origin_closed(origin)

    def test_clash_vmess_uri_and_xray_json_import_to_real_connection(self):
        inspector = os.environ["SWIRL_INSPECT_BINARY"]
        for network in ("raw", "ws"):
            peer = self.peer(network)
            source_network = "tcp" if network == "raw" else "ws"
            clash = {"type": "vmess", "name": "synthetic-import", "server": peer["host"],
                     "port": peer["port"], "uuid": UUID, "alterId": 0,
                     "cipher": "auto", "network": source_network}
            raw = {"v": "2", "ps": "synthetic-import", "add": peer["host"],
                   "port": str(peer["port"]), "id": UUID, "aid": "0", "scy": "auto",
                   "net": source_network, "type": "none"}
            stream = {"network": source_network, "security": "none"}
            if network == "ws":
                settings = peer["transport"]["settings"]
                clash["ws-opts"] = {"path": settings["path"], "headers": {"Host": settings["host"]}}
                raw.update(settings)
                stream["wsSettings"] = {"path": settings["path"], "host": settings["host"]}
            xray = {"outbounds": [{"protocol": "vmess", "tag": "synthetic-import",
                "settings": {"vnext": [{"address": peer["host"], "port": peer["port"],
                    "users": [{"id": UUID, "alterId": 0, "security": "auto"}]}]},
                "streamSettings": stream}]}
            documents = [
                ("clash", json.dumps({"proxies": [clash]}), ["--private-json"], "tcpCandidates"),
                ("uri", "vmess://" + base64.b64encode(json.dumps(raw).encode()).decode(),
                 ["--private-json"], "tcpCandidates"),
                ("xray", json.dumps(xray), ["--xray-json", "--private-json"], "native_candidates"),
            ]
            for source, document, arguments, field in documents:
                with self.subTest(source=source, network=network):
                    result = subprocess.run([inspector, *arguments], input=document,
                        text=True, capture_output=True, timeout=10, check=True)
                    exported = json.loads(result.stdout)
                    self.assertEqual(len(exported[field]), 1)
                    native = exported[field][0]
                    self.assertIsNotNone(native, exported["report"])
                    self.assertEqual(native["type"], "vmess")
                    origin = self.fixture.origin()
                    request = self.fixture.request(peer, origin)
                    request["outbound"] = native
                    request.pop("transport")
                    self.success(request)
                    self.fixture.assert_accepted(peer, origin)
                    self.fixture.assert_origin_closed(origin)

    def test_core_node_switch_preserves_established_vmess_session(self):
        first, second = self.peer(), self.peer("ws", True)
        runtime = subprocess.Popen([os.environ["SWIRL_TRANSPORT_RUNTIME"]],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            runtime.stdin.close()
            try:
                runtime.wait(timeout=5)
            except subprocess.TimeoutExpired:
                runtime.kill()
                runtime.wait(timeout=5)
            runtime.stdout.close()
            runtime.stderr.close()
        self.addCleanup(cleanup)
        def command(**message):
            runtime.stdin.write(json.dumps(message) + "\n")
            runtime.stdin.flush()
            result = json.loads(runtime.stdout.readline())
            self.assertTrue(result["ok"], result)
            return result
        config = {"schema": 1, "listen": "127.0.0.1:0", "selected": "a",
                  "nodes": [{"id": name, "outbound": copy.deepcopy(peer["outbound"])}
                            for name, peer in [("a", first), ("b", second)]]}
        started = command(op="start", config=config,
                          transports={"a": first["transport"], "b": second["transport"]})
        port = int(started["status"]["address"].rsplit(":", 1)[1])
        origin = self.fixture.origin(echo=True)
        def tunnel():
            stream = socket.create_connection(("127.0.0.1", port), timeout=5)
            self.addCleanup(stream.close)
            destination = f"{origin.target_host}:{origin.target_port}"
            stream.sendall(f"CONNECT {destination} HTTP/1.1\r\nHost: {destination}\r\n\r\n".encode())
            self.assertIn(b"200 Connection Established", header(stream))
            return stream
        old = tunnel()
        old.sendall((12).to_bytes(8, "big") + b"before")
        self.assertEqual(exact(old, 6), b"before")
        self.fixture.assert_accepted(first, origin)
        command(op="select_node", id="b")
        new = tunnel()
        new.sendall((3).to_bytes(8, "big") + b"new")
        self.assertEqual(exact(new, 3), b"new")
        new.shutdown(socket.SHUT_WR)
        self.assertEqual(new.recv(1), b"")
        self.fixture.assert_accepted(second, origin)
        old.sendall(b"-after")
        self.assertEqual(exact(old, 6), b"-after")
        old.shutdown(socket.SHUT_WR)
        self.assertEqual(old.recv(1), b"")
        self.fixture.assert_origin_closed(origin, count=2)
        deadline = time.monotonic() + 3
        while command(op="status")["status"]["active"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(command(op="status")["status"]["active"], 0)
        command(op="stop")


class VmessXrayHalfCloseTests(_VmessXrayBase):
    """Unweakened acceptance probe, known to fail with pinned Xray freedom.

    Run explicitly with --strict-half-close. Its nonzero exit and raw reports
    are evidence of an outstanding limitation, not a skipped or passed test.
    """
    def test_four_transports_four_mib_duplex_and_logical_half_close(self):
        for network in ("raw", "ws"):
            for tls in (False, True):
                with self.subTest(network=network, tls=tls):
                    peer, origin = self.peer(network, tls), self.fixture.origin(echo=True)
                    size = 4 * 1024 * 1024 + 17
                    request = self.fixture.request(peer, origin, mode="echo", size=size)
                    self.success(request, size)
                    self.fixture.assert_accepted(peer, origin)
                    self.assertEqual(origin.received, size)
                    self.fixture.assert_origin_closed(origin)

    def test_eight_concurrent_independent_sessions_with_target_half_close(self):
        peer, origin = self.peer("ws", True), self.fixture.origin(echo=True)
        size = 128 * 1024 + 3
        requests = [self.fixture.request(peer, origin, mode="echo", size=size) for _ in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            reports = list(pool.map(lambda request: self.success(request, size), requests))
        self.assertEqual(len(reports), 8)
        self.assertEqual(origin.received, 8 * size)
        self.fixture.assert_accepted(peer, origin)
        self.fixture.assert_origin_closed(origin, count=8)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-half-close", action="store_true",
        help="run the outstanding target half-close acceptance probe; failure remains failure")
    options = parser.parse_args()
    started = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        VmessXrayHalfCloseTests if options.strict_half_close else VmessXrayTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if folder := os.environ.get("SWIRL_VMESS_EVIDENCE"):
        destination = Path(folder)
        destination.mkdir(parents=True, exist_ok=True)
        summary = {"evidence_level": "independent_official_xray_loopback",
            "suite": "strict_half_close" if options.strict_half_close else "data_and_completed_response_close",
            "target_half_close_accepted": False,
            "public_network_tested": False, "qt_product_tested": False,
            "server_release": "v26.10.21", "server_commit": "1b1647cd9ddf0abc34b981d4611fc03bcac1ca74",
            "platform": platform.platform(), "tests_run": result.testsRun,
            "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "client_sha256": hashlib.sha256(Path(os.environ["SWIRL_TRANSPORT_CLIENT"]).read_bytes()).hexdigest(),
            "exit_code": 0 if result.wasSuccessful() else 1}
        (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
