"""TUIC v5 interoperability against the historical official reference server.

The only proxy client is Swirl's Rust connector. The pinned TUIC executable is
used exclusively as an independent server. Missing binaries are failures.
Run with SWIRL_TUIC_CLIENT and SWIRL_TUIC_SERVER set; optional SWIRL_TUIC_EVIDENCE
writes a redacted JSON report. All credentials are synthetic local fixtures.
"""
from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from test_rust_core import certificates
from transport_peer import _Origin, _OriginHandler, pattern_hash

UUID = "00112233-4455-6677-8899-aabbccddeeff"
PASSWORD = "tuic-local-synthetic-only"
OFFICIAL_SHA256 = {
    ("Linux", "x86_64"): "adb808944ca829857bf408d2ee438a156e8171543dbbed3e94964b66b4135393",
    ("Darwin", "x86_64"): "2031a3ae3c76d64ed63b803f4f3ff34536d4ecfdf3b0e190acb518657819f5fe",
    ("Darwin", "arm64"): "989c9fe8288bd07217198b844af83bfac7d949f1445b7447f324701e0e0b8825",
    ("Windows", "AMD64"): "09c3bf3790117bf4c0d0505ada439800f19b68a52a018ca2cda7e7f8125adeb6",
}
RECORDS = []
PEER_LOGS = []


def verify_peer(binary):
    version = subprocess.run([binary, "--version"], check=True, text=True,
                             capture_output=True, timeout=10).stdout.strip()
    if version != "1.0.0":
        raise AssertionError("requires pinned tuic-server-1.0.0")
    digest = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    if digest != OFFICIAL_SHA256.get((platform.system(), platform.machine())):
        raise AssertionError("reference peer binary digest/platform mismatch")
    return version, digest


class UdpOrigin(socketserver.ThreadingUDPServer):
    allow_reuse_address = False
    daemon_threads = True
    max_packet_size = 65535


class UdpHandler(socketserver.BaseRequestHandler):
    def handle(self):
        payload, sock = self.request
        self.server.received.append(payload)
        if self.server.dns:
            # A bounded authoritative fixture responds to the real wire query.
            if len(payload) < 12 or payload[4:6] != b"\x00\x01":
                return
            payload = payload[:2] + b"\x81\x80" + payload[4:6] + b"\x00\x01\x00\x00\x00\x00" + payload[12:] + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04\xc0\x00\x02\x01"
        sock.sendto(payload, self.client_address)


class TuicReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = os.environ["SWIRL_TUIC_SERVER"]
        cls.client = os.environ["SWIRL_TUIC_CLIENT"]
        cls.version, cls.server_sha256 = verify_peer(cls.server)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="swirl-tuic-reference-")
        self.folder = Path(self.temp.name)
        self.context, self.ca, _ = certificates(self.temp.name)
        leaf = x509.load_pem_x509_certificate((self.folder / "leaf.pem").read_bytes())
        self.pin = hashlib.sha256(leaf.public_bytes(serialization.Encoding.DER)).hexdigest()
        self.peers, self.origins = [], []
        self.addCleanup(self.close)

    def close(self):
        for process, output in self.peers:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
            output.close()
            with open(output.name, "rb") as source:
                size = source.seek(0, 2)
                source.seek(max(0, size - 65_536))
                message = source.read(65_536).decode("utf-8", errors="replace")
            # Retain independent-peer failures without publishing identity or
            # fixture secrets. The original CI artifact did not keep these.
            message = re.sub(r"(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b",
                             "<redacted-uuid>", message).replace(PASSWORD, "<redacted-password>")
            PEER_LOGS.append({"case": self.id().rsplit(".", 1)[-1],
                              "peer_exit_code": process.returncode,
                              "log_tail": message, "log_truncated": size > 65_536})
        for origin in self.origins:
            origin.shutdown()
            origin.server_close()
        self.temp.cleanup()

    def peer(self, *, host="127.0.0.1", idle_timeout="10s", log_level="warn"):
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(family, socket.SOCK_DGRAM) as reserve:
            reserve.bind((host, 0))
            port = reserve.getsockname()[1]
        sequence = len(self.peers)
        config = {"server": f"[{host}]:{port}" if family == socket.AF_INET6 else f"{host}:{port}",
                  "users": {UUID: PASSWORD}, "certificate": str(self.folder / "leaf.pem"),
                  "private_key": str(self.folder / "leaf.key"), "alpn": ["h3"],
                  "congestion_control": "cubic", "zero_rtt_handshake": False,
                  "max_idle_time": idle_timeout, "auth_timeout": "2s", "max_external_packet_size": 65535,
                  "log_level": log_level}
        path = self.folder / f"server-{sequence}.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        output = open(self.folder / f"server-{sequence}.log", "wb")
        process = subprocess.Popen([self.server, "-c", str(path)], stdout=output, stderr=subprocess.STDOUT)
        self.peers.append((process, output))
        # There is no TCP readiness port. A short bounded startup allowance is
        # followed by an actual QUIC/target exchange in every positive test.
        time.sleep(0.08)
        self.assertIsNone(process.poll(), "reference peer exited before the test")
        return {"type": "tuic", "host": host, "port": port, "uuid": UUID,
                "password": PASSWORD, "tls": {"server_name": "localhost", "alpn": ["h3"], "ca_der_base64": self.ca},
                "insecure": False, "udp": True, "udp_relay_mode": "native", "congestion_control": "cubic",
                "heartbeat_interval_ms": 1000, "request_timeout_ms": 5000}

    def origin(self, *, udp=False, dns=False):
        if udp:
            origin = UdpOrigin(("127.0.0.1", 0), UdpHandler)
            origin.received, origin.dns = [], dns
        else:
            origin = _Origin(("127.0.0.1", 0), _OriginHandler)
            origin.context, origin.mode = None, "echo"
            origin.requests, origin.errors, origin.active = [], [], set()
            origin.lock, origin.stopped = threading.Lock(), threading.Event()
            origin.received = origin.client_closes = origin.tls_closes = origin.interruptions = 0
        threading.Thread(target=origin.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.origins.append(origin)
        return origin

    def request(self, outbound, origin, **kwargs):
        return {"outbound": outbound, "target_host": origin.server_address[0], "target_port": origin.server_address[1],
                "size": 65_536, "timeout_ms": 8000, **kwargs}

    def run_client(self, request, *, ok=True):
        process = subprocess.run([self.client], input=json.dumps(request), capture_output=True, text=True, timeout=20)
        report = json.loads(process.stdout)
        record = {"case": self.id().rsplit(".", 1)[-1], "expect_success": ok,
                  "mode": request.get("mode", "tcp"), "payload_bytes": request["size"],
                  "udp_relay_mode": request.get("outbound", {}).get("udp_relay_mode"),
                  "client_exit_code": process.returncode, "result": report,
                  "native_interoperability_pass": False}
        # Append before asserting: failed positive cases must remain visible in
        # JSON receipts as well as in the unittest traceback.
        RECORDS.append(record)
        self.assertEqual(process.returncode, 0 if ok else 1, (report, process.stderr))
        self.assertEqual(report["ok"], ok, report)
        if ok:
            self.assertEqual(report["close"], "clean")
            self.assertEqual(report["downloaded"], request["size"] if request.get("mode") != "dns" else report["downloaded"])
            if request.get("mode") != "dns":
                self.assertEqual(report["sha256"], pattern_hash(request["size"]))
            record["native_interoperability_pass"] = True
        record["expected_outcome_verified"] = True
        return report

    def test_tcp_authentication_large_bidirectional_transfer_and_half_close(self):
        outbound, origin = self.peer(), self.origin()
        self.run_client(self.request(outbound, origin, size=4 * 1024 * 1024))
        self.assertEqual(origin.received, 4 * 1024 * 1024)
        self.assertEqual(origin.client_closes, 1)
        self.assertEqual(origin.errors, [])

    def test_wrong_password_and_uuid_never_reach_destination(self):
        outbound, origin = self.peer(), self.origin()
        for key, value in (("password", "wrong-local-fixture"), ("uuid", "ffeeddcc-bbaa-9988-7766-554433221100")):
            wrong = copy.deepcopy(outbound); wrong[key] = value
            self.run_client(self.request(wrong, origin, timeout_ms=3000), ok=False)
        self.assertEqual(origin.requests, [])

    def test_tls_ca_sni_alpn_and_pin_fail_closed(self):
        outbound, origin = self.peer(), self.origin()
        for field, value in (("ca_der_base64", None), ("server_name", "wrong.invalid"), ("alpn", ["wrong"])):
            wrong = copy.deepcopy(outbound); wrong["tls"][field] = value
            self.run_client(self.request(wrong, origin, timeout_ms=2500), ok=False)
        wrong = copy.deepcopy(outbound); wrong["insecure"] = True; wrong["pin_sha256"] = "00" * 32
        self.run_client(self.request(wrong, origin, timeout_ms=2500), ok=False)
        self.assertEqual(origin.requests, [])
        pinned = copy.deepcopy(outbound); pinned["pin_sha256"] = self.pin
        self.run_client(self.request(pinned, origin))

    def test_udp_native_and_quic_modes_small_and_fragmented(self):
        outbound, origin = self.peer(log_level="info"), self.origin(udp=True)
        for mode in ("native", "quic"):
            for size in (123, 4096, 65_507):
                with self.subTest(mode=mode, size=size):
                    node = copy.deepcopy(outbound); node["udp_relay_mode"] = mode
                    log_path = Path(self.peers[-1][1].name)
                    before = log_path.stat().st_size
                    self.run_client(self.request(node, origin, mode="udp", size=size))
                    if mode == "native" and size == 4096:
                        messages = log_path.read_bytes()[before:].decode("utf-8", errors="replace")
                        fragments = [(int(index), int(total)) for index, total in re.findall(
                            r"(?i)\[from-native\].*?fragment (\d+)/(\d+)", messages)]
                        self.assertTrue(fragments, "official peer did not record native fragment reception")
                        count = max(total for _, total in fragments)
                        self.assertGreater(count, 1, "4096-byte payload did not exercise real TUIC fragmentation")
                        self.assertEqual({index for index, total in fragments if total == count}, set(range(1, count + 1)))
                        RECORDS[-1]["official_server_observed_fragments"] = count
        self.assertEqual([len(value) for value in origin.received], [123, 4096, 65_507] * 2)

    def test_historical_reference_empty_reply_limitation_is_recorded(self):
        # This is retained failure evidence, not a successful empty-packet
        # interoperability claim. Upstream a299ef0 Fragments::next indexes
        # payload[0] even for a zero-length reply and its release binary aborts.
        # Keep this peer isolated so its abort cannot invalidate later cases.
        outbound, origin = self.peer(), self.origin(udp=True)
        report = self.run_client(self.request(outbound, origin, mode="udp", size=0), ok=False)
        self.assertEqual(origin.received, [b""])
        self.assertIsNotNone(self.peers[-1][0].poll())
        RECORDS[-1]["reference_peer_limitation"] = "empty UDP reply aborts tuic-server-1.0.0"
        RECORDS[-1]["native_interoperability_pass"] = False
        self.assertIn(report["error"], ["TuicUdpReceive", "TotalTimeout"])

    def test_dns_request_through_both_udp_modes(self):
        outbound, origin = self.peer(), self.origin(udp=True, dns=True)
        query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
        for mode in ("native", "quic"):
            node = copy.deepcopy(outbound); node["udp_relay_mode"] = mode
            result = self.run_client(self.request(node, origin, mode="dns", size=len(query), payload_hex=query.hex()))
            self.assertEqual(result["source_port"], origin.server_address[1])
            self.assertGreater(result["downloaded"], len(query))
        self.assertEqual(origin.received, [query, query])

    def test_clash_and_uri_import_reach_the_reference_server(self):
        outbound, origin = self.peer(), self.origin()
        raw = {"type": "tuic", "name": "synthetic", "server": outbound["host"], "port": outbound["port"],
               "uuid": UUID, "password": PASSWORD, "tls": outbound["tls"], "alpn": ["h3"]}
        request = self.request(outbound, origin)
        del request["outbound"]
        request["source_document"] = json.dumps({"proxies": [raw]})
        self.assertTrue(self.run_client(request)["imported"])
        request["source_document"] = f"tuic://{UUID}:{PASSWORD}@127.0.0.1:{outbound['port']}?sni=localhost&alpn=h3&insecure=1&pinSHA256={self.pin}"
        self.assertTrue(self.run_client(request)["imported"])
        self.assertEqual(len(origin.requests), 2)

    def test_ipv6_endpoint_and_domain_destination(self):
        outbound, origin = self.peer(host="::1"), self.origin()
        request = self.request(outbound, origin)
        request["target_host"] = "localhost"
        self.run_client(request)
        self.assertEqual(origin.client_closes, 1)

    def test_reconnect_node_switch_and_parallel_connections(self):
        first, second, origin = self.peer(), self.peer(), self.origin()
        for node in (first, second, first):
            self.run_client(self.request(node, origin))
        requests = [self.request(first if i % 2 else second, origin) for i in range(4)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(self.run_client, requests))
        self.assertEqual(len(origin.requests), 7)
        self.assertEqual(origin.received, 7 * 65_536)

    @classmethod
    def tearDownClass(cls):
        if path := os.environ.get("SWIRL_TUIC_EVIDENCE"):
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps({"peer": "historical official tuic-server", "version": cls.version,
                                               "binary_sha256": cls.server_sha256, "platform": platform.platform(),
                                               "client": "Swirl Rust", "known_limitations": ["Historical reference server aborts while framing an empty UDP reply; this combination is not passed."],
                                               "records": RECORDS, "peer_logs": PEER_LOGS}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
