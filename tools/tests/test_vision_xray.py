#!/usr/bin/env python3
"""Native VLESS/Vision streams against the pinned complete Xray executable.

Each case uses ephemeral certificates, credentials and loopback listeners. The
full reference process is a test-only oracle. No private subscriptions, public
providers, product routing, Qt integration or Direct-ready support are claimed.

Primary reference behavior was read at the locked upstream SHA:
https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/proxy/proxy.go
https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/proxy/vless/inbound/inbound.go
https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/infra/conf/freedom.go
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
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
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from test_reality_xray import executable, sha256

ROOT = Path(__file__).resolve().parents[2]
DIRECT_PROBE = b"server-first-vision-direct-probe\x00\xff"


def certificates(directory: Path):
    """Fresh test CA and two named leafs; never change the OS certificate store."""
    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Swirl Vision temporary CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(hours=1)).not_valid_after(now + timedelta(hours=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))
    result = {"ca_der_base64": base64.b64encode(ca.public_bytes(serialization.Encoding.DER)).decode("ascii")}
    for role in ("outer", "inner"):
        name = f"{role}.swirl-vision.test"
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
                .issuer_name(ca.subject).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(hours=1)).not_valid_after(now + timedelta(hours=1))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
                .sign(ca_key, hashes.SHA256()))
        cert_path, key_path = directory / f"{role}.pem", directory / f"{role}.key"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
        result[role] = {"name": name, "certificate": str(cert_path), "key": str(key_path)}
    return result


class Target:
    """A bounded independent Python/OpenSSL TLS echo target behind Xray."""

    def __init__(self, certs, tls13=False, pause_reads=False, expect_rejection=False):
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_3 if tls13 else ssl.TLSVersion.TLSv1_2
        self.context.maximum_version = self.context.minimum_version
        self.context.load_cert_chain(certs["inner"]["certificate"], certs["inner"]["key"])
        self.context.options |= ssl.OP_NO_TICKET
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(2)
        self.listener.settimeout(12)
        self.port = self.listener.getsockname()[1]
        self.pause_reads = pause_reads
        self.expect_rejection = expect_rejection
        self.server_first = tls13
        self.connection = None
        self.thread = None
        self.result = {"tls_version": None, "handshake_complete": False, "received_bytes": 0,
                       "sent_bytes": 0, "close_notify_received": False, "close_notify_sent": False,
                       "probe_bytes_sent": 0,
                       "connection_closed": False, "thread_released": False, "error": None}

    def start(self):
        self.thread = threading.Thread(target=self.serve, name="vision-independent-target", daemon=True)
        self.thread.start()

    def serve(self):
        received_hash, sent_hash = hashlib.sha256(), hashlib.sha256()
        raw = None
        try:
            raw, address = self.listener.accept()
            if address[0] != "127.0.0.1":
                raise AssertionError("target accepted a non-loopback client")
            raw.settimeout(8)
            self.connection = raw
            conn = self.context.wrap_socket(raw, server_side=True, suppress_ragged_eofs=False)
            self.connection = conn
            self.result["handshake_complete"] = True
            self.result["tls_version"] = conn.version()
            self.result["cipher"] = conn.cipher()[0]
            if self.server_first:
                # Xray requests Direct on the first post-handshake inner TLS
                # record. A server-first probe triggers that request before
                # the Rust application is permitted to submit any payload.
                conn.sendall(DIRECT_PROBE)
                self.result["probe_bytes_sent"] = len(DIRECT_PROBE)
                self.result["probe_sha256"] = hashlib.sha256(DIRECT_PROBE).hexdigest()
            if self.pause_reads:
                time.sleep(0.15)
            while True:
                data = conn.recv(4093)
                if not data:
                    self.result["close_notify_received"] = True
                    # With suppress_ragged_eofs=False, only authenticated TLS
                    # closure reaches this branch. unwrap sends our close alert.
                    self.connection = conn.unwrap()
                    self.result["close_notify_sent"] = True
                    break
                self.result["received_bytes"] += len(data)
                if self.result["received_bytes"] > 1024 * 1024:
                    raise AssertionError("target application budget exceeded")
                received_hash.update(data)
                for begin in range(0, len(data), 997):
                    part = data[begin:begin + 997]
                    conn.sendall(part)
                    self.result["sent_bytes"] += len(part)
                    sent_hash.update(part)
        except BaseException as error:
            self.result["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            if self.connection is not None:
                self.connection.close()
            if raw is not None:
                raw.close()
            self.listener.close()
            self.result["received_sha256"] = received_hash.hexdigest()
            self.result["sent_sha256"] = sent_hash.hexdigest()
            self.result["connection_closed"] = True

    def finish(self):
        self.thread.join(timeout=10)
        self.result["thread_released"] = not self.thread.is_alive()
        if self.thread.is_alive():
            raise AssertionError("independent TLS target did not finish")
        if self.result["error"] and not self.expect_rejection:
            raise AssertionError(f"independent TLS target failed: {self.result}")
        if self.result["error"] and self.result["error"]["type"] == "TimeoutError":
            raise AssertionError(f"independent target reached its cleanup deadline: {self.result}")
        return self.result

    def close(self):
        for connection in (self.listener, self.connection):
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
        if self.thread is not None:
            self.thread.join(timeout=3)
            self.result["thread_released"] = not self.thread.is_alive()


class XrayServer:
    def __init__(self, binary, directory, certs, user_id, target_port):
        self.binary, self.directory, self.certs, self.user_id = binary, directory, certs, user_id
        self.target_port = target_port
        self.process = self.log = None
        self.port = None
        self.lifecycle = {}

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserve:
            reserve.bind(("127.0.0.1", 0))
            self.port = reserve.getsockname()[1]
        config = {
            "log": {"loglevel": "debug"},
            "inbounds": [{"listen": "127.0.0.1", "port": self.port, "protocol": "vless",
                          "settings": {"clients": [{"id": self.user_id, "flow": "xtls-rprx-vision"}],
                                       "decryption": "none"},
                          "streamSettings": {"network": "raw", "security": "tls", "tlsSettings": {
                              "minVersion": "1.3", "maxVersion": "1.3", "certificates": [{
                                  "certificateFile": self.certs["outer"]["certificate"],
                                  "keyFile": self.certs["outer"]["key"]}]}}}],
            # This upstream release blocks private targets by default for
            # VLESS. Authorize exactly this case's independently bound local
            # target; no private network or public destination is permitted.
            "outbounds": [{"tag": "loopback", "protocol": "freedom", "settings": {
                "finalRules": [{"action": "allow", "network": "tcp", "ip": ["127.0.0.1/32"],
                                "port": self.target_port}]}},
                          {"tag": "blocked", "protocol": "blackhole"}],
            "routing": {"rules": [{"type": "field", "ip": ["127.0.0.1/32"], "port": self.target_port, "outboundTag": "loopback"},
                                    {"type": "field", "network": "tcp,udp", "outboundTag": "blocked"}]},
        }
        path = self.directory / "xray-config.json"
        path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        checked = subprocess.run([str(self.binary), "run", "-test", "-config", str(path)],
                                 capture_output=True, text=True, timeout=10, check=False)
        (self.directory / "xray-config-validation.log").write_text(checked.stdout + checked.stderr, encoding="utf-8")
        if checked.returncode:
            raise AssertionError("pinned Xray rejected the test configuration")
        self.log = (self.directory / "xray.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen([str(self.binary), "run", "-config", str(path)],
                                        stdout=self.log, stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError("pinned Xray exited during startup; see xray.log")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.02)
        raise AssertionError("pinned Xray listener did not become ready")

    def close(self):
        if self.lifecycle:
            return
        forced = False
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                forced = True
                self.process.kill()
                self.process.wait(timeout=3)
        if self.log is not None:
            self.log.close()
        port_closed = True
        if self.port is not None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.5)
                port_closed = probe.connect_ex(("127.0.0.1", self.port)) != 0
        self.lifecycle = {"process_reaped": self.process is None or self.process.poll() is not None,
                          "forced_kill": forced, "listener_closed": port_closed,
                          "exit_code": self.process.returncode if self.process is not None else None}
        (self.directory / "xray-lifecycle.json").write_text(json.dumps(self.lifecycle, indent=2) + "\n", encoding="utf-8")


class VisionXrayInterop(unittest.TestCase):
    sequence = 0

    @classmethod
    def setUpClass(cls):
        if not os.environ.get("SWIRL_VISION_CLIENT") or not os.environ.get("SWIRL_XRAY_PEER_DIR"):
            raise RuntimeError("SWIRL_VISION_CLIENT and SWIRL_XRAY_PEER_DIR are required; no skipped peer builds")
        cls.client = executable(Path(os.environ["SWIRL_VISION_CLIENT"]))
        cls.peer_dir = Path(os.environ["SWIRL_XRAY_PEER_DIR"]).resolve(strict=True)
        manifest = json.loads((cls.peer_dir / "build-manifest.json").read_text(encoding="utf-8"))
        lock_path = ROOT / "tools/tests/xray_peer/lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        cls.xray = executable(cls.peer_dir / ("xray.exe" if os.name == "nt" else "xray"))
        if manifest.get("status") != "success" or manifest.get("schema_version") != 1:
            raise RuntimeError("full Xray peer has no successful verified source build")
        if manifest["lock_sha256"] != sha256(lock_path) or manifest["go_version"] != lock["go_version"]:
            raise RuntimeError("full Xray peer differs from pinned source/toolchain")
        if manifest["xray"] != lock["xray"] or manifest["reality"] != lock["reality"]:
            raise RuntimeError("full Xray peer dependency identity mismatch")
        identity = manifest["binaries"]["xray"]
        if identity["file"] != cls.xray.name or identity["sha256"] != sha256(cls.xray):
            raise RuntimeError("full Xray executable changed after verified build")
        repeated = manifest["reproducible_rebuild"]["xray"]
        if repeated["matches"] is not True or repeated["first_sha256"] != identity["sha256"] or repeated["repeated_sha256"] != identity["sha256"]:
            raise RuntimeError("full Xray repeat build was not reproduced")
        cls.evidence = Path(os.environ.get("SWIRL_VISION_EVIDENCE", ROOT / "build/vision-xray-evidence")).resolve()
        cls.evidence.mkdir(parents=True, exist_ok=True)
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                  check=True, timeout=5).stdout.strip()
        if os.environ.get("GITHUB_SHA", revision) != revision:
            raise RuntimeError("CI SHA does not match the tested source")
        if manifest["swirl_source_commit"] != revision:
            raise RuntimeError("reference build manifest belongs to a different Swirl checkout")
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=ROOT,
                               capture_output=True, timeout=5, check=False)
        if dirty.returncode not in (0, 1):
            raise RuntimeError("cannot determine source worktree status")
        source = {"git_sha": revision, "tracked_changes": dirty.returncode == 1,
                  "client_sha256": sha256(cls.client), "test_sha256": sha256(Path(__file__)),
                  "client_source_sha256": sha256(ROOT / "core/crates/swirl-protocol/examples/vision-client.rs"),
                  "python": sys.version, "openssl": ssl.OPENSSL_VERSION, "platform": sys.platform,
                  "github_run_id": os.environ.get("GITHUB_RUN_ID"), "build_manifest": manifest}
        (cls.evidence / "source-identity.json").write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")

    def exchange(self, payload, *, tls13=False, pause_reads=False, read_chunk=16384, write_chunk=16384):
        type(self).sequence += 1
        case = self.evidence / f"{type(self).sequence:03d}-{self._testMethodName}-{time.time_ns()}"
        case.mkdir()
        with tempfile.TemporaryDirectory(prefix="swirl-vision-") as temporary:
            certs = certificates(Path(temporary))
            identity = str(uuid.uuid4())
            target = Target(certs, tls13=tls13, pause_reads=pause_reads, expect_rejection=tls13)
            server = XrayServer(self.xray, case, certs, identity, target.port)
            try:
                target.start()
                server.start()
                request = {"host": "127.0.0.1", "port": server.port, "uuid": identity,
                           "target_host": "127.0.0.1", "target_port": target.port,
                           "outer_server_name": certs["outer"]["name"], "outer_ca_der_base64": certs["ca_der_base64"],
                           "inner_tls": True, "inner_server_name": certs["inner"]["name"],
                           "inner_ca_der_base64": certs["ca_der_base64"], "payload_hex": payload.hex(),
                           "timeout_ms": 10000, "read_chunk": read_chunk, "write_chunk": write_chunk}
                if tls13:
                    request["server_first"] = True
                started = time.monotonic()
                result = subprocess.run([str(self.client)], input=json.dumps(request), capture_output=True,
                                        encoding="utf-8", timeout=15, check=False)
                (case / "client-stdout.jsonl").write_text(result.stdout, encoding="utf-8")
                (case / "client-stderr.log").write_text(result.stderr, encoding="utf-8")
                (case / "invocation.json").write_text(json.dumps({
                    "elapsed_seconds": time.monotonic() - started, "exit_code": result.returncode,
                    "payload_bytes": len(payload), "payload_sha256": hashlib.sha256(payload).hexdigest(),
                    "tls13": tls13, "pause_reads": pause_reads, "read_chunk": read_chunk,
                    "write_chunk": write_chunk}, indent=2) + "\n", encoding="utf-8")
                self.assertEqual(result.stderr, "", "client must use its structured redacted report")
                self.assertEqual(len(result.stdout.splitlines()), 1)
                client = json.loads(result.stdout)
                for key in ("ok", "direct_ready", "direct_rejected", "tls13_candidate"):
                    self.assertIs(type(client[key]), bool, key)
                for key in ("uploaded", "received"):
                    self.assertIs(type(client[key]), int, key)
                    self.assertGreaterEqual(client[key], 0)
                self.assertNotIn(identity, result.stdout)
                if tls13:
                    # This case ends at the client's authenticated Direct
                    # refusal. Stop the reference service now and verify its
                    # target sockets release; never accept a target timeout as
                    # proof that the client or server cleaned up promptly.
                    server.close()
                target_report = target.finish()
                if tls13:
                    self.assertEqual(result.returncode, 1, client)
                    self.assertFalse(client["ok"], client)
                    self.assertTrue(client["direct_rejected"], client)
                    self.assertTrue(client["tls13_candidate"], client)
                    self.assertEqual(client["error"], "VisionDirectOwnershipUnavailable", client)
                    self.assertEqual(client["error_kind"], "PermissionDenied", client)
                    self.assertEqual(client["stage"], "server_first_probe", client)
                    self.assertEqual(client["uploaded"], 0, client)
                    self.assertEqual(client["received"], 0, client)
                    self.assertEqual(target_report["received_bytes"], 0, target_report)
                    self.assertEqual(target_report["sent_bytes"], 0, target_report)
                    self.assertTrue(target_report["handshake_complete"], target_report)
                    self.assertEqual(target_report["tls_version"], "TLSv1.3", target_report)
                    self.assertEqual(target_report["probe_bytes_sent"], len(DIRECT_PROBE), target_report)
                    self.assertEqual(target_report["probe_sha256"], hashlib.sha256(DIRECT_PROBE).hexdigest(), target_report)
                else:
                    self.assertEqual(result.returncode, 0, client)
                    self.assertTrue(client["ok"], client)
                    self.assertEqual(client["stage"], "complete", client)
                    self.assertFalse(client["direct_rejected"], client)
                    self.assertFalse(client["tls13_candidate"], client)
                    for key in ("uploaded", "received"):
                        self.assertEqual(client[key], len(payload), client)
                    self.assertEqual(client["payload_sha256"], hashlib.sha256(payload).hexdigest(), client)
                    self.assertTrue(target_report["handshake_complete"], target_report)
                    self.assertEqual(target_report["tls_version"], "TLSv1.2", target_report)
                    for key in ("received_bytes", "sent_bytes"):
                        self.assertEqual(target_report[key], len(payload), target_report)
                    for key in ("received_sha256", "sent_sha256"):
                        self.assertEqual(target_report[key], hashlib.sha256(payload).hexdigest(), target_report)
                    self.assertTrue(target_report["close_notify_received"], target_report)
                    self.assertTrue(target_report["close_notify_sent"], target_report)
                self.assertFalse(client["direct_ready"], client)
            finally:
                server.close()
                target.close()
                (case / "target-result.json").write_text(json.dumps(target.result, indent=2) + "\n", encoding="utf-8")
            self.assertTrue(target.result["thread_released"], target.result)
            self.assertTrue(target.result["connection_closed"], target.result)
            self.assertTrue(server.lifecycle["process_reaped"], server.lifecycle)
            self.assertTrue(server.lifecycle["listener_closed"], server.lifecycle)
            self.assertFalse(server.lifecycle["forced_kill"], server.lifecycle)

    def test_tls12_authentication_framing_bidirectional_data_and_close(self):
        self.exchange(b"Swirl native Vision through unmodified Xray\x00\xff")

    def test_tls12_large_transfer_pause_resume_and_application_boundaries(self):
        self.exchange(bytes(range(256)) * 2048, pause_reads=True, read_chunk=257, write_chunk=1021)

    def test_tls12_single_byte_reads_and_small_writes(self):
        self.exchange(b"partial-buffers\x00\xff" * 17, read_chunk=1, write_chunk=7)

    def test_tls13_direct_request_is_rejected_without_application_data(self):
        self.exchange(b"must-not-cross-unowned-direct-boundary", tls13=True)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(VisionXrayInterop)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = Path(os.environ.get("SWIRL_VISION_EVIDENCE", ROOT / "build/vision-xray-evidence")).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "test-summary.json").write_text(json.dumps({
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "successful": result.wasSuccessful(),
    }, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
