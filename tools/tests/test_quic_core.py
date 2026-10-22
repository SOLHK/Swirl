"""Real Core SOCKS5/HTTP -> native QUIC protocols -> independent official peers.

No proxy implementation lives in this fixture. SOCKS5 clients are Python sockets,
the client engine is the compiled Rust Core, and the only proxy
servers are pinned Hysteria 2 and historical official TUIC v5 reference binaries.
By default the host is transport-runtime. Explicit SWIRL_NATIVE_LIBRARY selects
the ctypes host that loads the actual exported C ABI, with unchanged network tests.
Missing runtime/peer executables fail the suite. This is not Qt product acceptance.
"""
from __future__ import annotations

import base64
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import test_hysteria2_official as hy2
import test_tuic_reference as tuic
from test_rust_core import exact, header
from test_socks5_udp import address, packet, read_address, udp_socket, unpack_packet
from transport_peer import HTTP_BODY, _Origin


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(8)
        with self.server.lock:
            self.server.requests.append("tcp")
        try:
            while data := self.request.recv(16384):
                with self.server.lock:
                    self.server.received += len(data)
                self.request.sendall(data)
            self.request.shutdown(socket.SHUT_WR)
        except (OSError, TimeoutError):
            # Error-path tests deliberately terminate the native session.
            pass


class QuicCoreTests(unittest.TestCase):
    """Reuse peer lifecycle helpers without inheriting or recounting their tests."""

    tuic_peer = tuic.TuicReferenceTests.peer
    origin = tuic.TuicReferenceTests.origin
    close = tuic.TuicReferenceTests.close
    records = []
    evidence_env = "SWIRL_QUIC_CORE_EVIDENCE"

    @classmethod
    def setUpClass(cls):
        cls.records, cls.ffi_hosts = [], []
        cls.server = os.environ["SWIRL_TUIC_SERVER"]
        cls.tuic_version, cls.tuic_hash = tuic.verify_peer(cls.server)
        cls.hy2_server = Path(os.environ["HY2_SERVER"]).resolve(strict=True)
        cls.hy2_hash = hashlib.sha256(cls.hy2_server.read_bytes()).hexdigest()
        if cls.hy2_hash not in hy2.OFFICIAL_SHA256.values():
            raise AssertionError("official Hysteria binary digest mismatch")
        version = subprocess.check_output([str(cls.hy2_server), "version"],
                                          stderr=subprocess.STDOUT, timeout=10).decode()
        if hy2.OFFICIAL_VERSION not in version or hy2.OFFICIAL_COMMIT not in version:
            raise AssertionError("official Hysteria version/commit mismatch")
        cls.native_library = (Path(os.environ["SWIRL_NATIVE_LIBRARY"]).resolve(strict=True)
                              if os.environ.get("SWIRL_NATIVE_LIBRARY") else None)
        if cls.native_library:
            cls.harness = Path(__file__).with_name("native_ffi_host.py").resolve(strict=True)
            cls.harness_command = [sys.executable, "-u", str(cls.harness)]
        else:
            cls.harness = Path(os.environ["SWIRL_TRANSPORT_RUNTIME"]).resolve(strict=True)
            cls.harness_command = [str(cls.harness)]
        cls.runtime_hash = hashlib.sha256((cls.native_library or cls.harness).read_bytes()).hexdigest()

    def setUp(self):
        tuic.TuicReferenceTests.setUp(self)
        self.hy2_peers = []
        self.addCleanup(lambda: [peer.stop() for peer in self.hy2_peers])
        self.associations = []
        self.stderr = tempfile.TemporaryFile()
        self.runtime = subprocess.Popen(self.harness_command, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.stderr, text=True)
        self.responses = queue.Queue(maxsize=32)

        def reader():
            for line in self.runtime.stdout:
                self.responses.put(line)
            self.responses.put(None)

        self.reader = threading.Thread(target=reader, daemon=True)
        self.reader.start()
        self.addCleanup(self.close_runtime)
        if self.native_library:
            identity = self.command(op="host_identity")
            self.assertEqual(identity["control_boundary"], "exported_c_abi_dynamic_library")
            self.assertEqual(identity["abi_version"], 1)
            self.assertEqual(identity["library_sha256"], self.runtime_hash)
            self.assertTrue(all(identity["buffer_boundaries"].values()))
            self.ffi_record = {"case": self._testMethodName, "startup": identity}
            self.ffi_hosts.append(self.ffi_record)

    def close_runtime(self):
        for control, client, _ in self.associations:
            control.close()
            client.close()
        identity_error = None
        if getattr(self, "native_library", None) and hasattr(self, "ffi_record") and self.runtime.poll() is None:
            try:
                self.ffi_record["before_eof"] = self.command(op="host_identity")
            except Exception as error:
                # A broken control channel must still close stdin and reap its
                # child; metadata failure never bypasses runtime cleanup.
                identity_error = error
        self.runtime.stdin.close()
        try:
            self.runtime.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.runtime.kill()
            self.runtime.wait(timeout=5)
            self.fail("native Core failed to stop")
        finally:
            self.reader.join(2)
            self.runtime.stdout.close()
            self.stderr.seek(0)
            diagnostic = self.stderr.read().decode(errors="replace")
            self.stderr.close()
        self.assertEqual(self.runtime.returncode, 0, diagnostic)
        self.assertFalse(self.reader.is_alive())
        self.assertNotIn(tuic.PASSWORD, diagnostic)
        self.assertNotIn("synthetic-hy2-core", diagnostic)
        if identity_error is not None:
            raise identity_error
        if getattr(self, "native_library", None) and hasattr(self, "ffi_record"):
            identity = self.ffi_record["before_eof"]
            self.assertEqual(identity["active_handles"], 0)
            self.assertEqual(identity["handles_started"], identity["handles_stopped"])

    def command(self, **value):
        self.runtime.stdin.write(json.dumps(value) + "\n")
        self.runtime.stdin.flush()
        try:
            line = self.responses.get(timeout=6)
        except queue.Empty:
            self.fail("native Core control response timed out")
        self.assertIsNotNone(line, "native Core exited before replying")
        return json.loads(line)

    def peer(self, protocol, **options):
        if protocol.startswith("tuic"):
            node = self.tuic_peer(**options)
            node["udp_relay_mode"] = "quic" if protocol.endswith("quic") else "native"
            return node
        peer = hy2.OfficialPeer(self.hy2_server, self.folder,
            self.folder / "leaf.pem", self.folder / "leaf.key",
            "synthetic-hy2-core", f"hy2-core-{len(self.hy2_peers)}")
        self.hy2_peers.append(peer)
        return {"type": "hysteria2", "host": "127.0.0.1", "port": peer.port,
            "password": peer.password,
            "tls": {"server_name": "localhost", "alpn": ["h3"], "ca_der_base64": self.ca}}

    def start(self, *outbounds, **options):
        config = {"schema": 1, "listen": "127.0.0.1:0", "selected": "n0",
            "nodes": [{"id": f"n{index}", "outbound": value}
                      for index, value in enumerate(outbounds)], **options}
        result = self.command(op="start", config=config)
        self.assertTrue(result["ok"], result)
        self.port = int(result["status"]["address"].rsplit(":", 1)[1])
        self.protocol = outbounds[0]["type"] + (
            ":" + outbounds[0].get("udp_relay_mode", "native")
            if outbounds[0]["type"] == "tuic" else "")
        return config

    def stop(self):
        for control, client, _ in self.associations:
            control.close()
            client.close()
        self.associations.clear()
        deadline = time.monotonic() + 4
        while self.command(op="status")["status"]["active"] and time.monotonic() < deadline:
            time.sleep(0.01)
        status = self.command(op="status")["status"]
        self.assertEqual(status["active"], 0, "completed sessions retained native Core tasks")
        self.records.append({"case": self._testMethodName, "protocol": self.protocol,
            "active_after_close": status["active"], "uploaded": status["upload"],
            "downloaded": status["download"], "udp_dropped": status["udp_dropped"]})
        self.assertTrue(self.command(op="stop")["ok"])

    def echo_origin(self):
        origin = _Origin(("127.0.0.1", 0), Echo)
        origin.requests, origin.errors, origin.received = [], [], 0
        origin.lock = threading.Lock()
        threading.Thread(target=origin.serve_forever,
                         kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.origins.append(origin)
        return origin

    def dns_origin(self):
        # localhost may resolve to ::1 first at the independent proxy server.
        # A dual-stack target verifies remote domain resolution without tying
        # the test outcome to the operating system's address preference.
        class DualStack(tuic.UdpOrigin):
            address_family = socket.AF_INET6

        origin = DualStack(("::", 0), tuic.UdpHandler, bind_and_activate=False)
        origin.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        origin.server_bind()
        origin.server_activate()
        origin.received, origin.dns = [], True
        threading.Thread(target=origin.serve_forever,
                         kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.origins.append(origin)
        return origin

    def connect(self, origin):
        stream = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        stream.settimeout(5)
        try:
            stream.sendall(b"\x05\x01\x00")
            self.assertEqual(exact(stream, 2), b"\x05\x00")
            stream.sendall(b"\x05\x01\x00" + address(*origin.server_address))
            response = exact(stream, 3)
            if response != b"\x05\x00\x00":
                raise ConnectionError("SOCKS connect rejected")
            read_address(lambda size: exact(stream, size))
            return stream
        except BaseException:
            stream.close()
            raise

    def associate(self):
        client = udp_socket()
        client.bind(("127.0.0.1", 0))
        client.settimeout(4)
        control = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            control.sendall(b"\x05\x01\x00")
            self.assertEqual(exact(control, 2), b"\x05\x00")
            control.sendall(b"\x05\x03\x00" + address("0.0.0.0", 0))
            self.assertEqual(exact(control, 3), b"\x05\x00\x00")
            _, host, port = read_address(lambda size: exact(control, size))
            association = (control, client, (host, port))
            self.associations.append(association)
            return association
        except BaseException:
            client.close()
            control.close()
            raise

    def udp_exchange(self, association, origin, payload, host="127.0.0.1"):
        _, client, relay = association
        port = origin.server_address[1]
        client.sendto(packet(host, port, payload), relay)
        wire, sender = client.recvfrom(65535)
        self.assertEqual(sender, relay)
        _, _, source_port, reply = unpack_packet(wire)
        self.assertEqual(source_port, port)
        return reply

    def test_live_tcp_sessions_node_switch_parallel_streams_and_runtime_restart(self):
        for protocol in ("tuic-native", "tuic-quic", "hysteria2"):
            with self.subTest(protocol=protocol):
                first, second, origin = self.peer(protocol), self.peer(protocol), self.echo_origin()
                self.start(first, second)
                with self.connect(origin) as old:
                    old.sendall(b"before-node-switch")
                    self.assertEqual(exact(old, 18), b"before-node-switch")
                    self.assertTrue(self.command(op="select_node", id="n1")["ok"])

                    def exchange(index):
                        data = bytes([index]) * 65_536
                        with self.connect(origin) as stream:
                            stream.sendall(data)
                            self.assertEqual(exact(stream, len(data)), data)
                            stream.shutdown(socket.SHUT_WR)
                            self.assertEqual(stream.recv(1), b"")

                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
                        list(workers.map(exchange, range(4)))
                    old.sendall(b"preserved-after-switch")
                    self.assertEqual(exact(old, 22), b"preserved-after-switch")
                    old.shutdown(socket.SHUT_WR)
                    self.assertEqual(old.recv(1), b"")
                self.assertEqual(len(origin.requests), 5)
                self.stop()
                self.start(first)
                with self.connect(origin) as restarted:
                    restarted.sendall(b"new-runtime")
                    self.assertEqual(exact(restarted, 11), b"new-runtime")
                self.stop()

    def test_udp_association_fragments_dns_and_control_close(self):
        query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
        for protocol in ("tuic-native", "tuic-quic", "hysteria2"):
            with self.subTest(protocol=protocol):
                self.start(self.peer(protocol))
                udp, dns = self.origin(udp=True), self.dns_origin()
                association = self.associate()
                for size in (123, 3072, 4000):
                    payload = bytes([size % 251]) * size
                    self.assertEqual(self.udp_exchange(association, udp, payload), payload)
                response = self.udp_exchange(association, dns, query, "localhost")
                self.assertEqual(response[:2], query[:2])
                self.assertEqual(response[2:4], b"\x81\x80")
                self.assertEqual(dns.received, [query])
                control, client, relay = association
                control.close()
                deadline = time.monotonic() + 3
                while self.command(op="status")["status"]["active"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(self.command(op="status")["status"]["active"], 0)
                client.settimeout(0.25)
                client.sendto(packet("127.0.0.1", udp.server_address[1], b"after-control-close"), relay)
                with self.assertRaises((socket.timeout, ConnectionResetError)):
                    client.recvfrom(65535)
                self.assertEqual([len(value) for value in udp.received], [123, 3072, 4000])
                fresh = self.associate()
                self.assertEqual(self.udp_exchange(fresh, udp, b"new-association"), b"new-association")
                self.stop()

    def test_wrong_credentials_never_forward_tcp_or_udp_and_existing_session_survives_selection(self):
        for protocol in ("tuic-native", "tuic-quic", "hysteria2"):
            with self.subTest(protocol=protocol):
                valid = self.peer(protocol)
                invalid = copy.deepcopy(valid)
                invalid["password"] = "wrong-synthetic-core-password"
                tcp, udp = self.echo_origin(), self.origin(udp=True)
                self.start(valid, invalid)
                old = self.associate()
                self.assertEqual(self.udp_exchange(old, udp, b"authenticated-before"), b"authenticated-before")
                self.assertTrue(self.command(op="select_node", id="n1")["ok"])
                try:
                    with self.connect(tcp) as stream:
                        stream.sendall(b"must-not-forward")
                        self.assertEqual(stream.recv(1), b"")
                except (ConnectionError, EOFError, socket.timeout):
                    pass
                rejected = self.associate()
                with self.assertRaises(socket.timeout):
                    self.udp_exchange(rejected, udp, b"must-not-forward")
                self.assertEqual(tcp.requests, [])
                self.assertEqual(udp.received, [b"authenticated-before"])
                self.assertEqual(self.udp_exchange(old, udp, b"preserved-after"), b"preserved-after")
                self.assertTrue(self.command(op="select_node", id="n0")["ok"])
                with self.connect(tcp) as stream:
                    stream.sendall(b"recovered")
                    self.assertEqual(exact(stream, 9), b"recovered")
                self.stop()

    def test_https_application_tls_through_native_core(self):
        for protocol in ("tuic-native", "tuic-quic", "hysteria2"):
            with self.subTest(protocol=protocol):
                origin = self.origin()
                origin.context, origin.mode = self.context, "http"
                self.start(self.peer(protocol))
                context = ssl.create_default_context(cadata=ssl.DER_cert_to_PEM_cert(base64.b64decode(self.ca)))
                raw = socket.create_connection(("127.0.0.1", self.port), timeout=5)
                self.addCleanup(raw.close)
                raw.sendall(f"CONNECT 127.0.0.1:{origin.server_address[1]} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
                self.assertIn(b"200 Connection Established", header(raw))
                with context.wrap_socket(raw, server_hostname="localhost") as stream:
                    stream.sendall(b"GET /transport HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                    self.assertIn(b"200 OK", header(stream))
                    self.assertEqual(exact(stream, len(HTTP_BODY)), HTTP_BODY)
                    plain = stream.unwrap()
                    plain.close()
                self.assertEqual(origin.received, 0)
                self.assertEqual(origin.requests, ["http"])
                self.stop()
                self.assertEqual(origin.tls_closes, 1)

    def test_tuic_heartbeat_keeps_idle_authenticated_stream_open(self):
        origin = self.echo_origin()
        self.start(self.peer("tuic-native", idle_timeout="2s"))
        with self.connect(origin) as stream:
            stream.sendall(b"before-idle")
            self.assertEqual(exact(stream, 11), b"before-idle")
            # Longer than the peer's two-second idle limit, shorter than the
            # generic ten-second QUIC keepalive: TUIC heartbeat keeps it alive.
            time.sleep(3.1)
            stream.sendall(b"after-idle")
            self.assertEqual(exact(stream, 10), b"after-idle")
        self.stop()

    def test_tuic_dns_configuration_change_does_not_reuse_an_old_resolved_endpoint(self):
        node, origin = self.peer("tuic-native"), self.echo_origin()
        node["host"] = "proxy.fixture.invalid"
        node["request_timeout_ms"] = 500
        config = self.start(node, dns={"hosts": [{"name": node["host"], "address": "127.0.0.1"}]},
                            limits={"max_connections": 128, "handshake_timeout_ms": 500})
        with self.connect(origin) as existing:
            existing.sendall(b"first-mapping")
            self.assertEqual(exact(existing, 13), b"first-mapping")
            changed = copy.deepcopy(config)
            changed["dns"]["hosts"][0]["address"] = "127.0.0.2"
            self.assertTrue(self.command(op="configure", config=changed)["ok"])
            with self.assertRaises((ConnectionError, EOFError)):
                with self.connect(origin):
                    self.fail("new connection reused the stale DNS endpoint")
            self.assertEqual(len(origin.requests), 1)
            existing.sendall(b"existing-kept")
            self.assertEqual(exact(existing, 13), b"existing-kept")
            self.assertTrue(self.command(op="configure", config=config)["ok"])
            with self.connect(origin) as restored:
                restored.sendall(b"new-valid-mapping")
                self.assertEqual(exact(restored, 17), b"new-valid-mapping")
        self.stop()

    @classmethod
    def tearDownClass(cls):
        if path := os.environ.get(cls.evidence_env):
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps({"runtime": "Swirl Rust Core",
                "runtime_sha256": cls.runtime_hash,
                "control_boundary": "exported_c_abi_dynamic_library" if cls.native_library else "rust_core_example",
                "control_host_sha256": hashlib.sha256(cls.harness.read_bytes()).hexdigest(),
                "platform": platform.platform(), "tuic_version": cls.tuic_version,
                "tuic_peer_sha256": cls.tuic_hash, "hysteria_version": hy2.OFFICIAL_VERSION,
                "hysteria_peer_sha256": cls.hy2_hash, "qt_product_acceptance": False,
                "records": cls.records, "ffi_hosts": cls.ffi_hosts}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
