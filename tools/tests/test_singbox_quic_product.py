"""Actual sing-box -> Qt import -> Windows DPAPI -> Rust -> independent QUIC peer.

Only synthetic loopback credentials are used. Server versions/hashes are checked
against the existing pinned fixtures; missing Qt/servers fail rather than skip.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET

from test_hysteria2_official import OfficialPeer, OFFICIAL_SHA256, certificate_files
import test_tuic_reference
from test_tuic_reference import UUID, PASSWORD, verify_peer


class Tcp(socketserver.ThreadingTCPServer):
    daemon_threads = True


class Udp(socketserver.ThreadingUDPServer):
    daemon_threads = True


class EchoTcp(socketserver.BaseRequestHandler):
    def handle(self):
        with self.server.lock:
            self.server.connections += 1
        self.request.settimeout(10)
        while True:
            data = self.request.recv(16384)
            if not data:
                return
            with self.server.lock:
                self.server.received += len(data)
            self.request.sendall(data)


class EchoUdp(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        with self.server.lock:
            self.server.received.append(data)
        sock.sendto(data, self.client_address)


class SingBoxQuicProduct(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise RuntimeError("WindowsDpapiFixtureRequired")
        cls.qt = Path(os.environ["SWIRL_RUST_QT_TESTS"]).resolve(strict=True)
        cls.tuic = Path(os.environ["SWIRL_TUIC_SERVER"]).resolve(strict=True)
        cls.hy2 = Path(os.environ["HY2_SERVER"]).resolve(strict=True)
        verify_peer(str(cls.tuic))
        if hashlib.sha256(cls.hy2.read_bytes()).hexdigest() != OFFICIAL_SHA256["windows-amd64"]:
            raise AssertionError("HysteriaPeerHashMismatch")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="swirl-singbox-quic-product-")
        self.folder = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.tcp = Tcp(("127.0.0.1", 0), EchoTcp)
        self.udp = Udp(("127.0.0.1", 0), EchoUdp)
        self.tcp.received, self.tcp.connections, self.udp.received = 0, 0, []
        for server in (self.tcp, self.udp):
            server.lock = threading.Lock()
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

    def run_qt(self, raw, *, reject=False):
        fixture, report = self.folder / "fixture.json", self.folder / "report.json"
        fixture.write_text(json.dumps({"subscription": json.dumps({"outbounds": [raw]}),
            "tcp_port": self.tcp.server_address[1], "udp_port": self.udp.server_address[1],
            "reject": reject}), encoding="utf-8")
        environment = dict(os.environ, SWIRL_QT_QUIC_FIXTURE=str(fixture),
                           SWIRL_QT_QUIC_REPORT=str(report))
        xml = self.folder / "qt.xml"
        result = subprocess.run([str(self.qt), "singBoxQuicProductChainAgainstIndependentPeer",
                                 "-o", str(xml) + ",xml", "-o", "-,txt"], env=environment,
                                capture_output=True, timeout=45)
        if result.returncode:
            # These logs contain only synthetic fixture values, but retain only
            # QTest failure locations in the public harness output.
            lines = result.stdout.decode("utf-8", errors="replace").splitlines()
            details = [line for line in lines if "FAIL!" in line or "Loc:" in line or ".cpp(" in line or "Actual" in line or "Expected" in line]
            raise AssertionError("QtQuicFixtureFailed: " + " | ".join(details))
        tree = ET.parse(xml).getroot()
        incidents = list(tree.iter("Incident"))
        self.assertTrue(incidents)
        self.assertTrue(all(item.get("type") == "pass" for item in incidents))
        self.assertFalse(any(item.get("type") == "skip" for item in tree.iter()))
        observed = json.loads(report.read_text(encoding="utf-8"))
        expected = {"schema": 1, "imported": True, "encrypted_store_reloaded": True,
                    "in_process_rust": True, "tcp_verified": not reject,
                    "udp_verified": not reject, "rejected": reject, "listener_released": True}
        self.assertEqual(observed, expected)
        with self.tcp.lock, self.udp.lock:
            self.assertEqual(self.tcp.received, 0 if reject else 65553)
            self.assertEqual(self.tcp.connections, 0 if reject else 1)
            self.assertEqual(self.udp.received, [] if reject else [b"s4-quic-udp-payload"])
        destination = os.environ.get("SWIRL_SINGBOX_QUIC_EVIDENCE")
        if destination:
            folder = Path(destination); folder.mkdir(parents=True, exist_ok=True)
            record = dict(observed, case=self.id().rsplit(".", 1)[-1],
                          independent_tcp_received=self.tcp.received,
                          independent_udp_received=len(self.udp.received),
                          provider_credentials_used=False,
                          qt_sha256=hashlib.sha256(self.qt.read_bytes()).hexdigest(),
                          rust=json.loads((self.qt.parent / "swirl-rust-build.json").read_text(encoding="utf-8-sig")),
                          rust_dll_sha256=hashlib.sha256((self.qt.parent / "swirl_api.dll").read_bytes()).hexdigest())
            (folder / (record["case"] + ".json")).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            (folder / (record["case"] + ".xml")).write_bytes(xml.read_bytes())

    def tuic_case(self, mode, *, reject=False):
        helper = test_tuic_reference.TuicReferenceTests(); helper.server = str(self.tuic); helper.setUp()
        self.addCleanup(helper.doCleanups)
        outbound = helper.peer()
        pem = "-----BEGIN CERTIFICATE-----\n" + outbound["tls"]["ca_der_base64"] + "\n-----END CERTIFICATE-----"
        raw = {"type": "tuic", "tag": "Synthetic TUIC", "server": "127.0.0.1",
               "server_port": outbound["port"], "uuid": UUID, "password": "wrong-synthetic" if reject else PASSWORD,
               "tls": {"enabled": True, "server_name": "localhost", "alpn": ["h3"], "certificate": pem},
               "udp_relay_mode": mode, "congestion_control": "cubic", "heartbeat": "1s250ms",
               "zero_rtt_handshake": False, "udp_over_stream": False}
        self.run_qt(raw, reject=reject)

    def hy2_case(self, *, obfs=False, reject=False):
        cert, key, ca, _ = certificate_files(self.folder)
        peer = OfficialPeer(self.hy2, self.folder, cert, key, "synthetic-hy2-password", "peer",
                            obfs_password="synthetic-salamander" if obfs else None)
        self.addCleanup(peer.stop)
        raw = {"type": "hysteria2", "tag": "Synthetic HY2", "server": "127.0.0.1",
               "server_port": peer.port, "password": "wrong-synthetic" if reject else "synthetic-hy2-password",
               "up_mbps": 3, "down_mbps": 5,
               "tls": {"enabled": True, "server_name": "localhost", "alpn": ["h3"],
                       "certificate": ["-----BEGIN CERTIFICATE-----", ca, "-----END CERTIFICATE-----"]}}
        if obfs:
            raw["obfs"] = {"type": "salamander", "password": "synthetic-salamander"}
        self.run_qt(raw, reject=reject)

    def test_tuic_native_tcp_udp(self): self.tuic_case("native")
    def test_tuic_quic_tcp_udp(self): self.tuic_case("quic")
    def test_tuic_bad_auth_never_reaches_origin(self): self.tuic_case("native", reject=True)
    def test_hy2_tcp_udp(self): self.hy2_case()
    def test_hy2_salamander_tcp_udp(self): self.hy2_case(obfs=True)
    def test_hy2_bad_auth_never_reaches_origin(self): self.hy2_case(reject=True)


if __name__ == "__main__":
    unittest.main()
