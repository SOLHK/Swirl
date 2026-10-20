#!/usr/bin/env python3
"""Real subscription -> production Runtime -> complete pinned Xray -> origins.

No REALITY/VLESS server code is implemented here. The identity-checked, complete
official Xray executable supplies the actual VLESS + REALITY inbound. A separate
Python/OpenSSL camouflage listener and HTTP/HTTPS/echo origins use ephemeral
credentials and loopback sockets. No upstream cache is seeded or overwritten.
The official target probes keep certificate verification enabled; their default
failure handling may record an empty post-handshake cache for the temporary CA.
The controlled camouflage server emits no tickets or application records.

Primary implementations inspected before writing this fixture:
https://github.com/XTLS/REALITY/blob/83f621788ca88b83179810b12baa7ae518aacb83/record_detect.go
https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/proxy/vless/inbound/inbound.go
https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/infra/conf/freedom.go

Private provider, browser-fingerprint and physical Windows GUI acceptance remain
separate. --qt requires the actual Windows Qt/DPAPI test executable; absence is
an error, not a skipped or simulated product test.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
from datetime import datetime, timedelta, timezone
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import random
import re
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from urllib.parse import urlencode

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.x509.oid import NameOID

from test_product_subscription_chain import BODY, TAIL, ChainBase, ProductChainIntegration, Server
from test_reality_xray import executable, sha256
from test_rust_core import exact, header

ROOT = Path(__file__).resolve().parents[2]
SNI = "swirl-reality-runtime.test"
SYNTHETIC_SECRETS = set()


def remember_secret(value):
    # Failure assertions can print a parsed node or its original encoded URI.
    # Register only this process's disposable fixture material, never providers.
    if value:
        SYNTHETIC_SECRETS.add(value)
        SYNTHETIC_SECRETS.add(json.dumps(value, ensure_ascii=True)[1:-1])
    return value


def redacted(value):
    for secret in sorted(SYNTHETIC_SECRETS, key=len, reverse=True):
        value = value.replace(secret, "[fixture-secret-redacted]")
    return value


class EvidenceStream:
    def __init__(self, stream, captured):
        self.stream, self.captured = stream, captured

    def write(self, value):
        value = redacted(value)
        self.stream.write(value)
        self.captured.write(value)

    def flush(self):
        self.stream.flush()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def b64url(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class Control:
    """Bounded stdin/stdout driver for the product's existing Rust control ABI."""

    def __init__(self):
        self.lines = queue.Queue()
        self.process = subprocess.Popen([os.environ["SWIRL_RUST_HARNESS"]],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)

        def read_lines():
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put(None)

        self.reader = threading.Thread(target=read_lines, daemon=True)
        self.reader.start()

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()
        try:
            line = self.lines.get(timeout=12)
        except queue.Empty as error:
            raise AssertionError("Rust control response deadline") from error
        if line is None:
            raise AssertionError("Rust control exited without response")
        return json.loads(line)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired as error:
            self.process.kill()
            self.process.wait(timeout=3)
            raise AssertionError("Rust runtime failed to release on shutdown") from error
        finally:
            self.reader.join(timeout=2)
            self.process.stdout.close()
            error_output = self.process.stderr.read()
            self.process.stderr.close()
        assert self.process.returncode == 0, "Rust control process failed"
        assert not error_output, "Rust control emitted unstructured diagnostics"
        assert not self.reader.is_alive(), "Rust control reader did not finish"


class LengthEchoOrigin:
    """Independent bounded echo target with an application length boundary.

    Official Xray freedom does not CloseWrite the target after client EOF; it
    waits for downlink or its configured deadline. Therefore this target reads a
    four-byte big-endian length, echoes exactly that many bytes, and releases the
    final response only after the test client actually half-closes its socket.
    A local signal coordinates that *target response*, never proxy success.
    """

    def __init__(self):
        self.errors, self.payloads, self.sessions = [], [], []
        self.signals, self.active = set(), set()
        self.condition = threading.Condition()
        self.cancel_expected = False
        self.halfclose_file = None
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                stream = self.request
                stream.settimeout(8)
                with owner.condition:
                    owner.active.add(stream)
                report = {"expected_bytes": 0, "received_bytes": 0, "cancelled": False,
                          "tail_after_client_halfclose": False, "target_closed": False}
                try:
                    size = int.from_bytes(exact(stream, 4), "big")
                    assert 0 < size <= 2 * 1024 * 1024, "echo application length budget"
                    report["expected_bytes"] = size
                    digest = hashlib.sha256()
                    while report["received_bytes"] < size:
                        try:
                            data = stream.recv(min(8191, size - report["received_bytes"]))
                        except ConnectionResetError:
                            if not owner.cancel_expected:
                                raise
                            data = b""
                        if not data:
                            assert owner.cancel_expected, "origin upload truncated"
                            report["cancelled"] = True
                            report["target_closed"] = True
                            return
                        owner.payloads.append(data)
                        report["received_bytes"] += len(data)
                        digest.update(data)
                        stream.sendall(data)
                    report["sha256"] = digest.hexdigest()
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        with owner.condition:
                            signalled = report["sha256"] in owner.signals
                        if owner.halfclose_file is not None and owner.halfclose_file.exists():
                            assert owner.halfclose_file.read_bytes() == b"half-closed"
                            signalled = True
                        if signalled:
                            report["tail_after_client_halfclose"] = True
                            break
                        time.sleep(0.005)
                    assert report["tail_after_client_halfclose"], "client half-close evidence absent"
                    # Deliberately hold a pending downlink after confirmed client
                    # SHUT_WR. Neither length framing nor this signal enters Xray.
                    time.sleep(0.025)
                    stream.sendall(TAIL)
                    try:
                        stream.shutdown(socket.SHUT_WR)
                    except OSError as error:
                        if error.errno != errno.ENOTCONN and getattr(error, "winerror", None) != 10057:
                            raise
                    assert stream.recv(1) == b"", "unexpected extra origin upload"
                    report["target_closed"] = True
                finally:
                    stream.close()
                    with owner.condition:
                        owner.sessions.append(report)
                        owner.active.discard(stream)
                        owner.condition.notify_all()

        self.server = Server(("127.0.0.1", 0), Handler)
        self.server.errors, self.server.fixture_kind = self.errors, "length-echo-origin"
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    def release_tail(self, payload):
        with self.condition:
            self.signals.add(hashlib.sha256(payload).hexdigest())

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        deadline = time.monotonic() + 8
        with self.condition:
            while self.active and time.monotonic() < deadline:
                self.condition.wait(timeout=0.02)
            active = list(self.active)
        for stream in active:
            stream.close()
        assert not active and not self.thread.is_alive(), "origin socket or worker retained"
        assert not self.errors, self.errors


class Camouflage:
    """Ticket-free TLS 1.3 Ed25519 target; accepted sockets have single owners."""

    def __init__(self, folder):
        now = datetime.now(timezone.utc)
        key = ed25519.Ed25519PrivateKey.generate()
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SNI)])
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(hours=1)).not_valid_after(now + timedelta(hours=1))
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(SNI)]), critical=False)
                .sign(key, None))
        cert_path, key_path = folder / "camouflage.pem", folder / "camouflage.key"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                              serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_3
        self.context.maximum_version = ssl.TLSVersion.TLSv1_3
        self.context.set_ecdh_curve("X25519")
        self.context.options |= ssl.OP_NO_TICKET
        self.context.num_tickets = 0
        self.context.load_cert_chain(cert_path, key_path)
        # The pinned Go 1.27 TLS server acknowledges SNI in EncryptedExtensions.
        # OpenSSL emits that standard acknowledgement only with an SNI callback;
        # without it the observed record is four bytes shorter than REALITY's
        # authenticated replacement and official REALITY rejects negative padding.
        self.context.set_servername_callback(lambda stream, name, context: None)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(32)
        self.listener.settimeout(0.2)
        self.port = self.listener.getsockname()[1]
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.connections, self.workers = set(), []
        self.accepted, self.application_bytes = 0, 0
        self.errors = []
        self.thread = threading.Thread(target=self.serve, name="reality-camouflage", daemon=True)
        self.thread.start()

    def serve(self):
        while not self.stopped.is_set():
            try:
                raw, address = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            assert address[0] == "127.0.0.1"
            raw.settimeout(12)
            with self.lock:
                self.accepted += 1
                self.connections.add(raw)
            worker = threading.Thread(target=self.session, args=(raw,), daemon=True)
            self.workers.append(worker)
            worker.start()

    def session(self, raw):
        stream = raw
        try:
            stream = self.context.wrap_socket(raw, server_side=True, do_handshake_on_connect=False,
                                             suppress_ragged_eofs=False)
            with self.lock:
                self.connections.discard(raw)
                self.connections.add(stream)
            stream.do_handshake()
            while data := stream.recv(4096):
                with self.lock:
                    self.application_bytes += len(data)
                raise AssertionError("REALITY fallback leaked application data into camouflage")
        except (ssl.SSLError, ConnectionError, EOFError, socket.timeout):
            # Official unauthenticated fallback and target-observation probes
            # can end here. They never count as successful REALITY sessions.
            pass
        except OSError as error:
            if not self.stopped.is_set():
                self.errors.append(type(error).__name__)
        except BaseException as error:
            self.errors.append(type(error).__name__)
        finally:
            stream.close()
            raw.close()
            with self.lock:
                self.connections.discard(raw)
                self.connections.discard(stream)

    def close(self):
        self.stopped.set()
        self.listener.close()
        self.thread.join(timeout=2)
        with self.lock:
            active = list(self.connections)
        for stream in active:
            try:
                stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            stream.close()
        for worker in self.workers:
            worker.join(timeout=2)
        assert not self.thread.is_alive() and not any(w.is_alive() for w in self.workers)
        assert not self.connections and not self.errors, "camouflage resources or fixture error"
        assert self.application_bytes == 0, "authentication failure leaked target bytes"


class XrayRuntimePeer:
    """Complete official executable, no seeded cache or alternate VLESS handler."""

    def __init__(self, binary, folder, evidence, identity, ports, flow=""):
        self.binary, self.folder, self.evidence, self.identity = binary, folder, evidence, identity
        self.folder.mkdir()
        self.flow, self.ports = flow, list(ports)
        self.camouflage = Camouflage(self.folder)
        self.uuid = str(uuid.uuid4())
        key = x25519.X25519PrivateKey.generate()
        self.private_key = b64url(key.private_bytes(serialization.Encoding.Raw,
                                                  serialization.PrivateFormat.Raw,
                                                  serialization.NoEncryption()))
        self.public_key = b64url(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                             serialization.PublicFormat.Raw))
        self.short_id = os.urandom(8).hex()
        for secret in (self.uuid, self.uuid.replace("-", ""), self.private_key,
                       self.public_key, self.short_id):
            remember_secret(secret)
        self.process = self.log = None
        self.closed = False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserve:
            reserve.bind(("127.0.0.1", 0))
            self.port = reserve.getsockname()[1]
        self.log_path, self.access_path = self.folder / "xray-private.log", self.folder / "access.log"

    def outbound_routes(self):
        """Strict loopback target allowlist; separate public gates may specialize."""
        outbounds, rules = [], []
        for port in self.ports:
            tag = f"origin-{port}"
            outbounds.append({"tag": tag, "protocol": "freedom", "settings": {
                "redirect": f"127.0.0.1:{port}",
                "finalRules": [{"action": "allow", "network": "tcp", "ip": ["127.0.0.1/32"], "port": port}]}})
            rules.append({"type": "field", "network": "tcp", "port": port, "outboundTag": tag})
        outbounds.append({"tag": "blocked", "protocol": "blackhole"})
        rules.append({"type": "field", "network": "tcp,udp", "outboundTag": "blocked"})
        return outbounds, rules

    def start(self):
        clients = {"id": self.uuid, "email": "fixture-" + self.identity}
        if self.flow:
            clients["flow"] = self.flow
        outbounds, rules = self.outbound_routes()
        config = {
            "log": {"loglevel": "debug", "access": str(self.access_path)},
            "inbounds": [{"tag": "reality-in", "listen": "127.0.0.1", "port": self.port,
                          "protocol": "vless", "settings": {"clients": [clients], "decryption": "none"},
                          "streamSettings": {"network": "raw", "security": "reality", "realitySettings": {
                              "show": True, "target": f"127.0.0.1:{self.camouflage.port}",
                              "serverNames": [SNI], "privateKey": self.private_key,
                              "shortIds": [self.short_id], "maxTimeDiff": 60000}}}],
            "outbounds": outbounds, "routing": {"domainStrategy": "AsIs", "rules": rules},
        }
        config_path = self.folder / "xray-config.json"
        write_json(config_path, config)
        checked = subprocess.run([str(self.binary), "run", "-test", "-config", str(config_path)],
                                 capture_output=True, text=True, timeout=10)
        if checked.returncode:
            raise AssertionError("official Xray rejected controlled REALITY configuration")
        self.log = self.log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen([str(self.binary), "run", "-config", str(config_path)],
                                        stdout=self.log, stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError("official Xray exited during initialization")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.02)
        raise AssertionError("official Xray listener startup deadline")

    def node(self):
        node = {"name": self.identity, "type": "vless", "server": "127.0.0.1", "port": self.port,
                "uuid": self.uuid, "network": "tcp", "tls": True, "servername": SNI,
                "client-fingerprint": "rustls", "reality-opts": {
                    "public-key": self.public_key, "short-id": self.short_id}}
        if self.flow:
            node["flow"] = self.flow
        return node

    def document(self, fmt="json"):
        if fmt == "json":
            return remember_secret(json.dumps({"proxies": [self.node()]}))
        if fmt == "yaml":
            node = self.node()
            rows = ["proxies:", "  - name: " + json.dumps(node.pop("name"))]
            for key, value in node.items():
                rows.append("    " + key + ": " + json.dumps(value))
            return remember_secret("\n".join(rows) + "\n")
        query = {"security": "reality", "type": "tcp", "encryption": "none", "sni": SNI,
                 "pbk": self.public_key, "sid": self.short_id, "fp": "rustls"}
        if self.flow:
            query["flow"] = self.flow
        uri = f"vless://{self.uuid}@127.0.0.1:{self.port}?{urlencode(query)}#{self.identity}"
        if fmt == "base64":
            return remember_secret(base64.b64encode(uri.encode()).decode())
        assert fmt == "uri"
        return remember_secret(uri)

    def observations(self):
        log = self.log_path.read_text(encoding="utf-8", errors="replace") if self.log_path.exists() else ""
        access = self.access_path.read_text(encoding="utf-8", errors="replace") if self.access_path.exists() else ""
        accepted = [line for line in access.splitlines() if " accepted tcp:" in line]
        return {"identity": self.identity, "protocol": "vless+reality" + ("+vision" if self.flow else ""),
                "tcp_listener_established": self.process is not None,
                "reality_authenticated_sessions": len(re.findall(r"isHandshakeComplete\.Load\(\): true", log)),
                "client_finished_verified_sessions": len(re.findall(r"readClientFinished\(\) err: <nil>", log)),
                "camouflage_record_size_failures": len(re.findall(r"payload\[0\]: \d+, padding: -\d+", log)),
                "vless_accepted_sessions": len(accepted),
                "vless_target_ports": [int(match.group(1)) for line in accepted
                                       if (match := re.search(r"accepted tcp:.*:(\d+) ", line))],
                "vision_padding_events": log.count("XtlsPadding"),
                "vision_unpadding_events": log.count("Xtls Unpadding"),
                "vision_direct_upload_commands": len(re.findall(r"Xtls Unpadding new block, content \d+ padding \d+ command 2(?:\r?\n|$)", log)),
                "vision_direct_download_commands": len(re.findall(r"XtlsPadding \d+ \d+ 2(?:\r?\n|$)", log)),
                "camouflage_connections": self.camouflage.accepted,
                "camouflage_application_bytes": self.camouflage.application_bytes}

    def close(self):
        if self.closed:
            return
        self.closed = True
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
        self.camouflage.close()
        report = self.observations()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            listener_closed = probe.connect_ex(("127.0.0.1", self.port)) != 0
        report.update(process_reaped=self.process is None or self.process.poll() is not None,
                      forced_kill=forced, listener_closed=listener_closed,
                      active_camouflage_connections=len(self.camouflage.connections))
        write_json(self.evidence / (self.identity + "-xray.json"), report)
        assert not forced and report["process_reaped"] and listener_closed


def verified_build(evidence, qt=False):
    for name in ("SWIRL_XRAY_PEER_DIR", "SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR"):
        if not os.environ.get(name):
            raise RuntimeError("Required Runtime/Xray executable not configured: " + name)
    if qt and not os.environ.get("SWIRL_RUST_QT_TESTS"):
        raise RuntimeError("The actual Windows Qt/DPAPI test executable is required")
    peer_dir = Path(os.environ["SWIRL_XRAY_PEER_DIR"]).resolve(strict=True)
    binary = executable(peer_dir / ("xray.exe" if os.name == "nt" else "xray"))
    manifest = json.loads((peer_dir / "build-manifest.json").read_text(encoding="utf-8"))
    lock_path = ROOT / "tools/tests/xray_peer/lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "success" or manifest.get("schema_version") != 1:
        raise RuntimeError("official Xray verified source build missing")
    if manifest["lock_sha256"] != sha256(lock_path) or manifest["go_version"] != lock["go_version"]:
        raise RuntimeError("Xray lock/toolchain mismatch")
    if manifest["xray"] != lock["xray"] or manifest["reality"] != lock["reality"]:
        raise RuntimeError("Xray/REALITY source identity mismatch")
    identity = manifest["binaries"]["xray"]
    repeated = manifest["reproducible_rebuild"]["xray"]
    if identity["file"] != binary.name or identity["sha256"] != sha256(binary):
        raise RuntimeError("complete Xray binary changed after build")
    if repeated["matches"] is not True or repeated["first_sha256"] != identity["sha256"] or repeated["repeated_sha256"] != identity["sha256"]:
        raise RuntimeError("complete Xray repeat-build evidence mismatch")
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                              capture_output=True, check=True, timeout=5).stdout.strip()
    if os.environ.get("GITHUB_SHA", revision) != revision or manifest["swirl_source_commit"] != revision:
        raise RuntimeError("tested checkout, CI SHA and Xray build manifest differ")
    binaries = {}
    for name in ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_QT_TESTS"):
        if os.environ.get(name):
            path = executable(Path(os.environ[name]))
            binaries[name] = {"file": path.name, "sha256": sha256(path)}
    changed = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                             text=True, capture_output=True, check=True, timeout=5).stdout.splitlines()
    write_json(evidence / "source-identity.json", {
        "git_sha": revision, "tracked_worktree_changes": changed, "binaries": binaries,
        "test_sha256": sha256(Path(__file__)), "python": sys.version, "openssl": ssl.OPENSSL_VERSION,
        "platform": sys.platform, "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "build_manifest": manifest,
        "scope": "actual Windows Qt/DPAPI" if qt else "production Rust control ABI with portable JSON test host",
        "provider_connection": False, "fingerprint": "rustls"})
    return binary


class RealityRuntimeInterop(ChainBase):
    # Reuse the established product-client and origin verifiers. Only their
    # transport peer changes to the complete official Xray process.
    inspect = ProductChainIntegration.inspect
    start = ProductChainIntegration.start
    tunnel = ProductChainIntegration.tunnel
    fetch = ProductChainIntegration.fetch
    idle = ProductChainIntegration.idle
    imported = ProductChainIntegration.imported
    flow = ""

    @classmethod
    def setUpClass(cls):
        cls.evidence_root = Path(os.environ.get("SWIRL_REALITY_RUNTIME_EVIDENCE",
                                                ROOT / "build/reality-runtime-evidence")).resolve()
        cls.evidence_root.mkdir(parents=True, exist_ok=True)
        cls.xray = verified_build(cls.evidence_root)

    def setUp(self):
        self.addCleanup(self.record)
        super().setUp()
        self.echo = self.keep(LengthEchoOrigin())
        self.case = self.evidence_root / (self._testMethodName + "-" + str(time.time_ns()))
        self.case.mkdir()
        self.peers = []
        self.core = self.keep(Control())

    def tearDown(self):
        # Capture the production error stage before cleanup releases the ABI
        # owner. Snapshot contains counters and route identities, not passwords
        # or TLS keys, including when the first CONNECT was rejected.
        if hasattr(self, "handle") and self.core.process.poll() is None:
            snapshot = self.core.command(op="snapshot", handle=self.handle)
            write_json(self.case / "runtime.json", snapshot)

    def record(self):
        if not hasattr(self, "case"):
            return
        write_json(self.case / "origins.json", {
            "http_paths": [r.split(b" ")[1].decode() for r in self.http.requests],
            "https_paths": [r.split(b" ")[1].decode() for r in self.https.requests],
            "https_sni": self.https.sni, "https_authenticated_closes": self.https.tls_closed,
            "echo_bytes": sum(map(len, self.echo.payloads)),
            "echo_sessions": self.echo.sessions,
            "origin_errors": {"http": self.http.errors, "https": self.https.errors, "echo": self.echo.errors}})

    def peer(self, identity="A", extra_ports=()):
        peer = XrayRuntimePeer(self.xray, Path(self.folder.name) / identity, self.case, identity,
                               [self.http.port, self.https.port, self.echo.port, *extra_ports], self.flow)
        self.addCleanup(peer.close)
        peer.start()
        self.peers.append(peer)
        return peer

    def observed(self, peer, expected):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = peer.observations()
            if result["vless_accepted_sessions"] == expected:
                break
            time.sleep(0.01)
        self.assertEqual(result["vless_accepted_sessions"], expected, result)
        self.assertGreaterEqual(result["reality_authenticated_sessions"], expected, result)
        self.assertGreaterEqual(result["client_finished_verified_sessions"], expected, result)
        self.assertEqual(result["camouflage_application_bytes"], 0)
        return result

    def test_import_uri_yaml_json_base64_to_http_and_verified_https(self):
        peer = self.peer()
        for fmt in ("uri", "json", "yaml", "base64"):
            with self.subTest(format=fmt):
                config = self.imported([peer], fmt)
                reality = config["nodes"][0]["outbound"]["reality"]
                self.assertEqual(reality["server_name"], SNI)
                self.assertEqual(reality["public_key"], peer.public_key)
                self.assertEqual(reality["short_id"], peer.short_id)
                self.assertEqual(reality["fingerprint"], "rustls")
                self.assertEqual(config["nodes"][0]["outbound"].get("flow") or "", self.flow)
                self.start(config)
                self.fetch(path="/" + fmt)
                self.fetch(path="/" + fmt + "-tls", tls=True)
                self.idle()
                self.assertTrue(self.core.command(op="stop", handle=self.handle)["ok"])
        self.observed(peer, 8)
        self.assertEqual(self.https.tls_closed, 4)

    def test_wrong_reality_authentication_and_vless_uuid_never_reach_target(self):
        peer, spare = self.peer(), self.peer("B")
        valid = self.imported([peer, spare])
        for kind in ("short_id", "public_key", "server_name", "uuid"):
            with self.subTest(invalid=kind):
                config = copy.deepcopy(valid)
                outbound = config["nodes"][0]["outbound"]
                if kind == "uuid":
                    outbound["uuid"] = str(uuid.uuid4())
                elif kind == "short_id":
                    outbound["reality"][kind] = os.urandom(8).hex()
                elif kind == "public_key":
                    outbound["reality"][kind] = b64url(x25519.X25519PrivateKey.generate().public_key().public_bytes(
                        serialization.Encoding.Raw, serialization.PublicFormat.Raw))
                else:
                    outbound["reality"][kind] = "incorrect.reality.invalid"
                self.start(config)
                with self.assertRaises((ConnectionError, EOFError, OSError)):
                    self.fetch(path="/must-not-arrive")
                self.idle(failures=1)
                self.assertTrue(self.core.command(op="stop", handle=self.handle)["ok"])
                self.assertEqual(self.http.requests, [])
                self.assertEqual(self.https.requests, [])
                self.assertEqual(spare.observations()["vless_accepted_sessions"], 0)
        self.assertEqual(peer.observations()["vless_accepted_sessions"], 0)

    def test_switch_preserves_old_session_and_routes_new_session_to_b(self):
        a, b = self.peer(), self.peer("B")
        self.start(self.imported([a, b], "uri"))
        with self.tunnel("localhost", self.echo.port) as old:
            payload = b"before-switchafter-switch"
            old.sendall(len(payload).to_bytes(4, "big"))
            old.sendall(b"before-switch")
            self.assertEqual(exact(old, 13), b"before-switch")
            self.observed(a, 1)
            self.assertEqual(b.observations()["vless_accepted_sessions"], 0)
            self.assertTrue(self.core.command(op="select", handle=self.handle, id="B")["ok"])
            self.fetch(path="/new-b")
            self.observed(b, 1)
            old.sendall(b"after-switch")
            self.assertEqual(exact(old, 12), b"after-switch")
            old.shutdown(socket.SHUT_WR)
            self.echo.release_tail(payload)
            self.assertEqual(exact(old, len(TAIL)), TAIL)
            self.assertEqual(old.recv(1), b"")
        self.observed(a, 1)
        self.assertEqual(self.idle()["selected"], "B")

    def test_large_fragmented_concurrent_bidirectional_halfclose(self):
        peer = self.peer()
        self.start(self.imported([peer]))

        def exchange(index):
            payload = random.Random(index).randbytes(256 * 1024 + 17)
            with self.tunnel("localhost", self.echo.port) as stream:
                stream.sendall(len(payload).to_bytes(4, "big"))
                offset = 0
                randomizer = random.Random(index + 51)
                while offset < len(payload):
                    size = min(randomizer.randint(1, 7919), len(payload) - offset)
                    part = payload[offset:offset + size]
                    stream.sendall(part)
                    self.assertEqual(exact(stream, len(part)), part)
                    offset += size
                stream.shutdown(socket.SHUT_WR)
                self.echo.release_tail(payload)
                self.assertEqual(exact(stream, len(TAIL)), TAIL)
                self.assertEqual(stream.recv(1), b"")

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(exchange, range(6)))
        self.assertEqual(self.idle()["accepted"], 6)
        self.assertEqual(sum(map(len, self.echo.payloads)), 6 * (256 * 1024 + 17))
        self.observed(peer, 6)

    def test_ordered_routes_reject_direct_domain_and_selected_exit(self):
        a, b = self.peer(), self.peer("B")
        config = self.imported([a, b])
        config["nodes"] += [{"id": "direct", "outbound": {"type": "direct"}},
                            {"id": "reject", "outbound": {"type": "reject"}}]
        config["rules"] = [
            {"matcher": {"type": "domain", "value": "denied.fixture.invalid"}, "outbound": "reject"},
            {"matcher": {"type": "domain", "value": "a.fixture.invalid"}, "outbound": "A"},
            {"matcher": {"type": "domain_suffix", "value": "suffix.fixture.invalid"}, "outbound": "B"},
            {"matcher": {"type": "cidr", "value": "127.0.0.0/8"}, "outbound": "direct"},
            {"matcher": {"type": "match"}, "outbound": "B"},
        ]
        self.start(config)
        self.fetch(host="a.fixture.invalid", path="/route-a")
        self.observed(a, 1)
        self.fetch(host="nested.suffix.fixture.invalid", path="/route-b")
        self.observed(b, 1)
        self.fetch(host="127.0.0.1", path="/direct")
        self.observed(a, 1)
        self.observed(b, 1)
        with self.assertRaises((ConnectionError, EOFError)):
            self.fetch(host="denied.fixture.invalid", path="/denied")
        self.assertEqual(len(self.http.requests), 3)
        self.idle(failures=1)

    def test_runtime_cancellation_releases_authenticated_stream(self):
        peer = self.peer()
        self.start(self.imported([peer]))
        with self.tunnel("localhost", self.echo.port) as stream:
            payload = b"cancel-after-authenticated-response"
            self.echo.cancel_expected = True
            stream.sendall((len(payload) + 1).to_bytes(4, "big"))
            stream.sendall(payload)
            self.assertEqual(exact(stream, len(payload)), payload)
            self.observed(peer, 1)
            self.assertTrue(self.core.command(op="stop", handle=self.handle)["ok"])
            self.assertEqual(stream.recv(1), b"")

    def test_handshake_timeout_drops_socket_and_never_tries_spare_or_direct(self):
        peer = self.peer()
        config = self.imported([peer])
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)
        config["nodes"].append(copy.deepcopy(config["nodes"][0]))
        config["nodes"][-1]["id"] = "stall"
        config["nodes"][-1]["outbound"]["port"] = listener.getsockname()[1]
        config["selected"] = "stall"
        config["limits"] = {"max_connections": 8, "handshake_timeout_ms": 250}
        observed = {"accepted": False, "client_hello_bytes": 0, "peer_eof": False, "error": None}
        finished = threading.Event()

        def stall():
            try:
                with listener.accept()[0] as stream:
                    observed["accepted"] = True
                    stream.settimeout(3)
                    while data := stream.recv(4096):
                        observed["client_hello_bytes"] += len(data)
                        if observed["client_hello_bytes"] > 64 * 1024:
                            raise AssertionError("handshake input limit")
                    observed["peer_eof"] = True
            except BaseException as error:
                observed["error"] = type(error).__name__
            finally:
                finished.set()

        worker = threading.Thread(target=stall, daemon=True)
        worker.start()
        try:
            self.start(config)
            began = time.monotonic()
            with self.assertRaises((ConnectionError, EOFError, OSError)):
                self.fetch(path="/timeout-must-not-arrive")
            self.assertLess(time.monotonic() - began, 3)
            self.idle(failures=1)
            self.assertTrue(finished.wait(2), "cancelled REALITY handshake retained its socket")
            self.assertTrue(observed["accepted"] and observed["peer_eof"], observed)
            self.assertIsNone(observed["error"], observed)
            self.assertGreater(observed["client_hello_bytes"], 0)
            self.assertEqual(peer.observations()["vless_accepted_sessions"], 0)
            self.assertEqual(self.http.requests, [])
        finally:
            listener.close()
            worker.join(timeout=4)
            write_json(self.case / "handshake-timeout.json", observed)
        self.assertFalse(worker.is_alive())


class VisionRuntimeInterop(RealityRuntimeInterop):
    flow = "xtls-rprx-vision"

    def test_tls13_server_first_direct_large_transfer_and_inner_authenticated_close(self):
        from test_vision_xray import DIRECT_PROBE, Target, certificates
        certs = certificates(Path(self.folder.name))
        target = Target(certs, tls13=True, pause_reads=True)
        self.addCleanup(target.close)
        target.start()
        peer = self.peer(extra_ports=[target.port])
        self.start(self.imported([peer], "uri"))
        context = ssl.create_default_context(cadata=ssl.DER_cert_to_PEM_cert(
            base64.b64decode(certs["ca_der_base64"])))
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        payload = bytes(range(256)) * 2048
        raw = self.tunnel("127.0.0.1", target.port)
        stream = raw
        try:
            stream = context.wrap_socket(raw, server_hostname=certs["inner"]["name"],
                                         suppress_ragged_eofs=False)
            self.assertEqual(stream.version(), "TLSv1.3")
            # This encrypted application record arrives before any client
            # application upload and requires the actual downlink Direct switch.
            self.assertEqual(exact(stream, len(DIRECT_PROBE)), DIRECT_PROBE)
            for start in range(0, len(payload), 16001):
                part = payload[start:start + 16001]
                stream.sendall(part)
                self.assertEqual(exact(stream, len(part)), part)
            stream = stream.unwrap()
            self.assertEqual(stream.recv(1), b"")
        finally:
            stream.close()
            raw.close()
        target_report = target.finish()
        write_json(self.case / "tls13-direct-target.json", target_report)
        self.assertTrue(target_report["handshake_complete"])
        self.assertEqual(target_report["tls_version"], "TLSv1.3")
        self.assertEqual(target_report["received_bytes"], len(payload))
        self.assertEqual(target_report["sent_bytes"], len(payload))
        self.assertEqual(target_report["received_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(target_report["sent_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertTrue(target_report["close_notify_received"] and target_report["close_notify_sent"])
        self.assertEqual(target_report["probe_bytes_sent"], len(DIRECT_PROBE))
        observed = self.observed(peer, 1)
        self.assertGreater(observed["vision_padding_events"], 0, observed)
        self.assertGreater(observed["vision_unpadding_events"], 0, observed)
        self.assertGreater(observed["vision_direct_upload_commands"], 0, observed)
        self.assertGreater(observed["vision_direct_download_commands"], 0, observed)
        self.idle()

    def test_tls12_remains_in_authenticated_vision_outer_stream(self):
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.maximum_version = ssl.TLSVersion.TLSv1_2
        peer = self.peer()
        self.start(self.imported([peer]))
        self.fetch(path="/inner-tls12", tls=True)
        observed = self.observed(peer, 1)
        self.assertGreater(observed["vision_padding_events"], 0, observed)
        self.assertGreater(observed["vision_unpadding_events"], 0, observed)
        self.assertEqual(observed["vision_direct_upload_commands"], 0, observed)
        self.assertEqual(observed["vision_direct_download_commands"], 0, observed)
        self.assertEqual(self.https.tls_closed, 1)
        self.idle()


class RealityQtInterop(RealityRuntimeInterop):
    """Only the existing real Qt product slot runs in this explicit mode."""
    client_closes_tls = True

    @classmethod
    def setUpClass(cls):
        cls.evidence_root = Path(os.environ["SWIRL_REALITY_RUNTIME_EVIDENCE"]).resolve()
        cls.evidence_root.mkdir(parents=True, exist_ok=True)
        cls.xray = verified_build(cls.evidence_root, qt=True)

    def test_actual_qt_import_dpapi_select_route_and_recreate(self):
        a, b = self.peer(), self.peer("B")
        document = {"proxies": [a.node(), b.node()],
                    "proxy-groups": [{"name": "choice", "type": "select", "proxies": ["A", "B"]}],
                    "rules": ["DOMAIN,a.product.invalid,A", "DOMAIN,b.product.invalid,B",
                              "DOMAIN,choice.product.invalid,choice", "DOMAIN,denied.product.invalid,REJECT",
                              "IP-CIDR,127.0.0.1/32,DIRECT,no-resolve", "DOMAIN-SUFFIX,suffix.product.invalid,B",
                              "DOMAIN-KEYWORD,keyword,A", f"DST-PORT,{self.http.port},B", "MATCH,REJECT"]}
        fixture = {"subscription": remember_secret(json.dumps(document)), "http_port": self.http.port,
                   "https_port": self.https.port, "stream_port": self.echo.port,
                   "ca_pem": self.ca_pem, "expected_body": BODY.decode()}
        self.echo.halfclose_file = Path(self.folder.name) / "qt-client-halfclosed"
        fixture.update(stream_length_header=True, stream_halfclose_signal=self.echo.halfclose_file.as_posix())
        path, log = Path(self.folder.name) / "qt-fixture.json", Path(self.folder.name) / "qt-private.log"
        write_json(path, fixture)
        try:
            result = subprocess.run([os.environ["SWIRL_RUST_QT_TESTS"],
                                     "subscriptionProductChainAgainstIndependentPeer", "-o", str(log) + ",txt"],
                                    env={**os.environ, "SWIRL_PRODUCT_FIXTURE": str(path)},
                                    text=True, capture_output=True, timeout=100)
        finally:
            output = redacted(log.read_text(encoding="utf-8")) if log.exists() else ""
            (self.case / "qt.log").write_text(output, encoding="utf-8")
        self.assertEqual(result.returncode, 0, output + redacted(result.stdout + result.stderr))
        self.assertNotIn("SKIP", output)
        self.assertCountEqual([r.split(b" ")[1].decode() for r in self.http.requests],
                              ["/selected-a", "/selected-b", "/restored-b", "/rule-a", "/rule-b",
                               "/rule-choice", "/rule-direct", "/rule-suffix", "/rule-keyword", "/rule-port"])
        self.assertEqual([r.split(b" ")[1] for r in self.https.requests], [b"/selected-a-tls"])
        self.assertEqual(self.https.sni, ["localhost", "wrong.fixture.invalid"])
        self.assertEqual(self.https.tls_closed, 1)
        for peer in (a, b):
            observed = self.observed(peer, 6)
            if self.flow:
                self.assertGreater(observed["vision_padding_events"], 0, observed)
                self.assertGreater(observed["vision_unpadding_events"], 0, observed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qt", action="store_true")
    parser.add_argument("--vision", action="store_true")
    args = parser.parse_args()
    if args.vision:
        RealityQtInterop.flow = VisionRuntimeInterop.flow
    suite = (unittest.TestSuite([RealityQtInterop("test_actual_qt_import_dpapi_select_route_and_recreate")])
             if args.qt else unittest.defaultTestLoader.loadTestsFromTestCase(
                 VisionRuntimeInterop if args.vision else RealityRuntimeInterop))
    evidence = Path(os.environ.get("SWIRL_REALITY_RUNTIME_EVIDENCE", ROOT / "build/reality-runtime-evidence")).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    captured = io.StringIO()
    result = unittest.TextTestRunner(stream=EvidenceStream(sys.stderr, captured), verbosity=2).run(suite)
    (evidence / "tests.log").write_text(captured.getvalue(), encoding="utf-8")
    write_json(evidence / "test-summary.json", {"tests_run": result.testsRun, "failures": len(result.failures),
               "errors": len(result.errors), "skipped": len(result.skipped), "successful": result.wasSuccessful(),
               "product_mode": "qt-dpapi" if args.qt else "rust-runtime", "provider_connection": False,
               "protocol": "vless+reality+vision" if args.vision else "vless+reality"})
    raise SystemExit(0 if result.wasSuccessful() else 1)
