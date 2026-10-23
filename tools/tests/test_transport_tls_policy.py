"""Required-ALPN rejection before proxy bytes, using a trusted local TLS peer.

This peer implements TLS only. Even the h2 positive control is NOT a proxy or
Xray interoperability result. Requires SWIRL_TRANSPORT_CLIENT built with gRPC.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from test_rust_core import certificates


RECORDS = []
H2_PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"


class TransportTlsPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="swirl-transport-alpn-")
        cls.folder = Path(cls.temp.name)
        _, cls.ca, _ = certificates(cls.temp.name)
        cls.client = os.environ["SWIRL_TRANSPORT_CLIENT"]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def tls_case(self, server_protocols, expected_protocol):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.folder / "leaf.pem", self.folder / "leaf.key")
        context.set_alpn_protocols(server_protocols)
        # This one-shot fixture does not use session resumption. Avoid an
        # unrelated TLS 1.3 ticket write racing the client's deliberate rejection.
        context.num_tickets = 0
        observed = {"application_bytes": b"", "errors": []}
        finished = threading.Event()
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)

        def serve():
            try:
                connection, _ = listener.accept()
                connection.settimeout(5)
                with context.wrap_socket(connection, server_side=True,
                                         suppress_ragged_eofs=False) as stream:
                    observed["selected_alpn"] = stream.selected_alpn_protocol()
                    observed["tls_handshake"] = True
                    while len(observed["application_bytes"]) < len(H2_PREFACE):
                        try:
                            data = stream.recv(4096)
                        except ssl.SSLEOFError:
                            # A rejected outer transport can close its socket
                            # without TLS close_notify. This is not a clean-close
                            # assertion; we only verify zero application bytes.
                            break
                        if not data:
                            break
                        observed["application_bytes"] += data
            except Exception as error:
                observed["errors"].append(type(error).__name__)
            finally:
                finished.set()

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        request = {
            "outbound": {"type": "vless", "host": "127.0.0.1",
                         "port": listener.getsockname()[1],
                         "uuid": "00112233-4455-6677-8899-aabbccddeeff",
                         "tls": {"server_name": "localhost", "ca_der_base64": self.ca,
                                 "alpn": []}},
            "transport": {"type": "grpc", "config": {"authority": "localhost",
                            "service_name": "alpn-policy", "mode": "tun"}},
            "target_host": "127.0.0.1", "target_port": 9, "timeout_ms": 3000,
        }
        result = subprocess.run([self.client], input=json.dumps(request), text=True,
                                capture_output=True, timeout=8)
        self.assertTrue(finished.wait(5), "TLS policy fixture did not close")
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        report = json.loads(result.stdout)
        self.assertEqual(observed["errors"], [], observed)
        self.assertTrue(observed.get("tls_handshake"), observed)
        self.assertEqual(observed["selected_alpn"], expected_protocol)
        self.assertEqual(result.returncode, 1, report)
        self.assertFalse(report["ok"], report)
        if expected_protocol == "h2":
            self.assertTrue(observed["application_bytes"].startswith(H2_PREFACE))
            self.assertFalse(report["error"].startswith("Tls"), report)
        else:
            self.assertEqual(report["error"], "TlsAlpnNegotiation")
            self.assertEqual(observed["application_bytes"], b"")
        RECORDS.append({"case": self._testMethodName, "client_alpn": [],
                        "server_alpn": server_protocols, "selected_alpn": expected_protocol,
                        "tls_handshake": True, "application_bytes": len(observed["application_bytes"]),
                        "proxy_interoperability": False, "client_result": report})

    def test_missing_negotiated_alpn_rejects_before_proxy_bytes(self):
        self.tls_case([], None)

    def test_h1_only_server_cannot_accept_automatic_h2_offer(self):
        # There is no mutually offered protocol, so OpenSSL negotiates None.
        self.tls_case(["http/1.1"], None)

    def test_empty_client_alpn_offers_h2_to_the_tls_peer(self):
        self.tls_case(["h2"], "h2")


if __name__ == "__main__":
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TransportTlsPolicyTests))
    if directory := os.environ.get("SWIRL_TLS_POLICY_EVIDENCE"):
        evidence = {"tests_run": result.testsRun, "failures": len(result.failures),
                    "errors": len(result.errors), "skips": len(result.skipped),
                    "exit_code": 0 if result.wasSuccessful() else 1,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "proxy_interoperability": False, "public_network_tested": False,
                    "client_sha256": hashlib.sha256(Path(os.environ["SWIRL_TRANSPORT_CLIENT"])
                                                     .read_bytes()).hexdigest(),
                    "cases": RECORDS}
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "summary.json").write_text(json.dumps(evidence, indent=2) + "\n")
    sys.exit(0 if result.wasSuccessful() else 1)
