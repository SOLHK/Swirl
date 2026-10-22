#!/usr/bin/env python3
"""Native Swirl REALITY TLS against the pinned, unmodified Xray server wrapper.

Build with tools/Build-XrayPeer.py, set SWIRL_XRAY_PEER_DIR and
SWIRL_REALITY_CLIENT, then run this file. Missing builds, mismatched executable
hashes, missing outcomes and peer failures are errors, never skipped tests.
Every connection uses fresh synthetic credentials and loopback listeners. The
test helper is an isolated upstream oracle; Swirl never links or launches it
as a production outbound. Chrome133 and the native profile both exercise the
actual hybrid and classical key exchanges. Browser wire compatibility has its
own independent uTLS gate; VLESS, Vision, real providers and the complete
product path are outside this TLS component's evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
X25519 = 0x001D
HYBRID = 0x11EC
MAX_PAYLOAD = 1024 * 1024


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def executable(path: Path) -> Path:
    path = path.resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(f"Required test executable is not executable: {path.name}")
    return path


class XrayPeer:
    """One bounded helper process and one independently authenticated session."""

    def __init__(self, binary: Path, directory: Path, **config):
        self.binary = binary
        self.directory = directory
        self.config = {"mode": "echo", "group": "hybrid", "timeout_ms": 8000, **config}
        self.events: queue.Queue[str | None] = queue.Queue()
        self.process = None
        self.reader = None
        self.stderr = None
        self.ready = None
        self.result = None
        self.lines: list[str] = []
        self.reaped = False
        self.forced_cleanup = False

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=False)
        (self.directory / "peer-config.json").write_text(json.dumps(self.config, indent=2) + "\n", encoding="utf-8")
        self.stderr = (self.directory / "peer-stderr.log").open("w", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                [str(self.binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.stderr, encoding="utf-8", bufsize=1,
            )

            def pump():
                try:
                    for line in self.process.stdout:
                        self.lines.append(line)
                        self.events.put(line)
                finally:
                    self.events.put(None)

            self.reader = threading.Thread(target=pump, name="swirl-xray-outcome", daemon=True)
            self.reader.start()
            self.process.stdin.write(json.dumps(self.config) + "\n")
            self.process.stdin.flush()
            self.process.stdin.close()
            self.ready = self.read_event(8)
            if self.ready.get("event") != "ready":
                raise AssertionError(f"Xray helper did not become ready: {self.ready}")
            settings = self.ready["settings"]
            if settings["host"] != "127.0.0.1" or not 1 <= settings["port"] <= 65535:
                raise AssertionError("Xray helper must listen on a concrete loopback port")
            return self
        except BaseException:
            self.close()
            raise

    def read_event(self, timeout):
        try:
            line = self.events.get(timeout=timeout)
        except queue.Empty as error:
            raise AssertionError("Xray helper outcome deadline exceeded") from error
        if line is None:
            raise AssertionError("Xray helper exited without the required JSON outcome")
        event = json.loads(line)
        if not isinstance(event, dict):
            raise AssertionError("Xray helper outcome must be a JSON object")
        return event

    def finish(self):
        self.result = self.read_event(10)
        if self.result.get("event") != "result":
            raise AssertionError(f"Missing Xray result event: {self.result}")
        for key in ("handshake_complete", "client_hello_authenticated", "client_finished_verified",
                    "close_notify_received", "close_notify_sent", "transport_eof"):
            if type(self.result[key]) is not bool:
                raise AssertionError(f"Xray outcome {key} must be boolean")
        for key in ("tls_version", "group", "cipher_suite", "received_bytes", "sent_bytes",
                    "active_connections", "camouflage_application_bytes"):
            if type(self.result[key]) is not int or self.result[key] < 0:
                raise AssertionError(f"Xray outcome {key} must be a nonnegative integer")
        self.process.wait(timeout=3)
        self.reaped = True
        self.reader.join(timeout=2)
        if self.reader.is_alive():
            raise AssertionError("Xray outcome reader was not released")
        if self.process.returncode != 0:
            raise AssertionError(f"Xray helper failed ({self.process.returncode}): {self.result}")
        if self.events.get(timeout=1) is not None or not self.events.empty():
            raise AssertionError("Xray helper emitted unexpected extra outcomes")
        if self.result["active_connections"] != 0:
            raise AssertionError(f"Xray helper leaked active connections: {self.result}")
        # The process outcome is not sufficient: ensure its listening socket is
        # gone as well, after all helper goroutines reported their cleanup.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", self.ready["settings"]["port"])) == 0:
                raise AssertionError("Xray listener still accepts after the peer process exited")
        return self.result

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.forced_cleanup = True
                self.process.kill()
            self.process.wait(timeout=3)
            self.reaped = True
        if self.reader is not None:
            self.reader.join(timeout=2)
        if self.process is not None and self.process.stdout is not None:
            self.process.stdout.close()
        if self.stderr is not None:
            self.stderr.close()
        # All credentials in readiness are generated afresh inside this local
        # helper, never private subscriptions. Keep exact upstream output so a
        # failed handshake can be audited instead of replaced by a summary.
        (self.directory / "peer-stdout.jsonl").write_text("".join(self.lines), encoding="utf-8")
        (self.directory / "lifecycle.json").write_text(json.dumps({
            "process_reaped": self.reaped,
            "forced_cleanup": self.forced_cleanup,
            "reader_released": self.reader is None or not self.reader.is_alive(),
            "exit_code": self.process.returncode if self.process is not None else None,
        }, indent=2) + "\n", encoding="utf-8")

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class RealityXrayInterop(unittest.TestCase):
    evidence: Path
    sequence = 0

    @classmethod
    def setUpClass(cls):
        client = os.environ.get("SWIRL_REALITY_CLIENT")
        peer_dir = os.environ.get("SWIRL_XRAY_PEER_DIR")
        if not client or not peer_dir:
            raise RuntimeError("SWIRL_REALITY_CLIENT and SWIRL_XRAY_PEER_DIR are required; build failures cannot be skipped")
        cls.client = executable(Path(client))
        cls.peer_dir = Path(peer_dir).resolve(strict=True)
        suffix = ".exe" if os.name == "nt" else ""
        cls.peer = executable(cls.peer_dir / f"reality-peer{suffix}")
        cls.xray = executable(cls.peer_dir / f"xray{suffix}")
        cls.manifest = json.loads((cls.peer_dir / "build-manifest.json").read_text(encoding="utf-8"))
        cls.evidence = Path(os.environ.get("SWIRL_XRAY_EVIDENCE", ROOT / "build" / "reality-xray-evidence")).resolve()
        cls.evidence.mkdir(parents=True, exist_ok=True)
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, timeout=5, check=True,
        ).stdout.strip()
        if os.environ.get("GITHUB_SHA", revision) != revision:
            raise RuntimeError("CI GITHUB_SHA does not identify this checked-out source")
        dirty = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--"], cwd=ROOT,
            capture_output=True, timeout=5, check=False,
        )
        if dirty.returncode not in (0, 1):
            raise RuntimeError("Cannot determine source worktree identity")
        identity = {
            "git_sha": revision, "tracked_changes": dirty.returncode == 1,
            "platform": sys.platform, "python": sys.version,
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "client_sha256": sha256(cls.client), "peer_sha256": sha256(cls.peer),
            "xray_sha256": sha256(cls.xray), "build_manifest": cls.manifest,
            "test_source_sha256": sha256(Path(__file__)),
            "client_source_sha256": sha256(ROOT / "core/crates/swirl-transport/examples/reality-client.rs"),
        }
        (cls.evidence / "source-identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
        # Executable provenance is validated against the builder's digest map
        # below; no arbitrary downloaded binary is accepted by this suite.
        if cls.manifest["schema_version"] != 1 or cls.manifest["status"] != "success":
            raise RuntimeError("Xray build manifest does not attest to a completed verified build")
        if cls.manifest["swirl_source_commit"] != revision:
            raise RuntimeError("Xray helper build belongs to a different Swirl source commit")
        lock_path = ROOT / "tools/tests/xray_peer/lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if cls.manifest["lock_sha256"] != sha256(lock_path) or cls.manifest["go_version"] != lock["go_version"]:
            raise RuntimeError("Xray helper build differs from the checked-in source/toolchain lock")
        if cls.manifest["helper_source_sha256"] != sha256(ROOT / "tools/tests/xray_peer/main.go"):
            raise RuntimeError("Xray helper source changed after its verified build")
        for section, keys in (
            ("xray", ("commit", "tree", "go_mod_sha256", "go_sum_sha256")),
            ("reality", ("module", "version", "commit", "sum", "go_mod_sum")),
        ):
            if any(cls.manifest[section][key] != lock[section][key] for key in keys):
                raise RuntimeError(f"Xray helper {section} identity differs from the checked-in source lock")
        for name, path in (("reality_peer", cls.peer), ("xray", cls.xray)):
            binary = cls.manifest["binaries"][name]
            if binary["file"] != path.name or binary["sha256"] != sha256(path):
                raise RuntimeError(f"Upstream executable identity changed after the verified build: {path.name}")
        version_process = subprocess.run(
            [str(cls.peer), "--version"], capture_output=True, text=True, timeout=5, check=True,
        )
        (cls.evidence / "peer-version.json").write_text(version_process.stdout, encoding="utf-8")
        version = json.loads(version_process.stdout)
        if (version["event"] != "version"
                or version["xray_commit"] != cls.manifest["xray"]["commit"]
                or version["reality_version"] != cls.manifest["reality"]["version"]
                or version["go_version"] != cls.manifest["go_version"]):
            raise RuntimeError("Xray peer runtime identity differs from the pinned build manifest")

    def peer_session(self, **config):
        type(self).sequence += 1
        directory = self.evidence / f"{type(self).sequence:03d}-{self._testMethodName}"
        # Repeated local runs keep previous failure logs intact.
        if directory.exists():
            directory = directory.with_name(f"{directory.name}-{time.time_ns()}")
        return XrayPeer(self.peer, directory, **config)

    def invoke(self, peer, payload, **changes):
        request = {**peer.ready["settings"], "payload_hex": payload.hex(), **changes}
        start = time.monotonic()
        try:
            process = subprocess.run(
                [str(self.client)], input=json.dumps(request), encoding="utf-8",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False,
            )
        except subprocess.TimeoutExpired as error:
            # subprocess.run has already killed and reaped the client. Preserve
            # partial output too; timeout failures must remain diagnosable.
            for name, output in (("client-stdout.jsonl", error.stdout), ("client-stderr.log", error.stderr)):
                if isinstance(output, bytes):
                    output = output.decode("utf-8", errors="replace")
                (peer.directory / name).write_text(output or "", encoding="utf-8")
            raise
        elapsed = time.monotonic() - start
        (peer.directory / "client-stdout.jsonl").write_text(process.stdout, encoding="utf-8")
        (peer.directory / "client-stderr.log").write_text(process.stderr, encoding="utf-8")
        (peer.directory / "client-invocation.json").write_text(json.dumps({
            "payload_bytes": len(payload), "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "changes": {key: value for key, value in changes.items() if key not in ("public_key_hex", "short_id_hex")},
            "changed_auth_fields": [key for key in changes if key in ("public_key_hex", "short_id_hex")],
            "elapsed_seconds": elapsed, "exit_code": process.returncode,
        }, indent=2) + "\n", encoding="utf-8")
        self.assertEqual(process.stderr, "", "Rust client must use its structured JSON outcome")
        lines = process.stdout.splitlines()
        self.assertEqual(len(lines), 1, "Rust client must emit exactly one JSON outcome")
        report = json.loads(lines[0])
        for key in ("handshake_verified", "payload_matches", "client_close_notify", "server_close_notify"):
            self.assertIs(type(report[key]), bool, key)
        for key in ("uploaded_bytes", "received_bytes"):
            self.assertIs(type(report[key]), int, key)
            self.assertGreaterEqual(report[key], 0, key)
        self.assertNotIn(request["public_key_hex"], process.stdout)
        self.assertNotIn(request["short_id_hex"], process.stdout)
        return process.returncode, report, elapsed

    def negotiated(self, client, server, group):
        self.assertTrue(client["handshake_verified"], client)
        self.assertTrue(server["handshake_complete"], server)
        self.assertTrue(server["client_hello_authenticated"], server)
        self.assertTrue(server["client_finished_verified"], server)
        self.assertEqual(server["tls_version"], 0x0304, server)
        self.assertEqual(client["group"], group, client)
        self.assertEqual(server["group"], group, server)
        self.assertIn(server["cipher_suite"], (0x1301, 0x1302, 0x1303), server)
        self.assertEqual(client["cipher_suite"], server["cipher_suite"], (client, server))
        self.assertEqual(server["camouflage_application_bytes"], 0, server)

    def positive(self, payload, *, group="hybrid", read_chunk=16384, write_chunk=16384,
                 peer_read_chunk=4093, peer_write_chunk=997, fingerprint="rustls"):
        with self.peer_session(group=group, read_chunk=peer_read_chunk, write_chunk=peer_write_chunk) as peer:
            code, client, _ = self.invoke(peer, payload, read_chunk=read_chunk,
                                         write_chunk=write_chunk, fingerprint=fingerprint)
            server = peer.finish()
            self.assertEqual(code, 0, client)
            self.assertEqual(client["status"], "ok", client)
            self.assertEqual(server["status"], "completed", server)
            self.negotiated(client, server, HYBRID if group == "hybrid" else X25519)
            self.assertEqual(client["stage"], "close", client)
            self.assertTrue(client["payload_matches"], client)
            for key in ("uploaded_bytes", "received_bytes"):
                self.assertEqual(client[key], len(payload), client)
            for key in ("received_bytes", "sent_bytes"):
                self.assertEqual(server[key], len(payload), server)
            for key in ("received_sha256", "sent_sha256"):
                self.assertEqual(server[key], hashlib.sha256(payload).hexdigest(), server)
            self.assertTrue(client["client_close_notify"], client)
            self.assertTrue(client["server_close_notify"], client)
            self.assertTrue(server["close_notify_received"], server)
            self.assertTrue(server["close_notify_sent"], server)
            self.assertFalse(peer.forced_cleanup)

    def test_native_hybrid_authentication_finished_bidirectional_data_and_close(self):
        self.positive((bytes(range(256)) * 129)[:32769])

    def test_native_x25519_authentication_finished_bidirectional_data_and_close(self):
        self.positive((bytes(range(255, -1, -1)) * 129)[:32769], group="x25519")

    def test_chrome_hybrid_authentication_finished_bidirectional_data_and_close(self):
        self.positive((bytes(range(256)) * 129)[:32769], fingerprint="chrome")

    def test_chrome_independent_x25519_authentication_finished_bidirectional_data_and_close(self):
        self.positive((bytes(range(255, -1, -1)) * 129)[:32769], group="x25519",
                      fingerprint="chrome_133")

    def test_one_mebibyte_binary_transfer_with_short_reads_and_writes(self):
        self.positive(bytes(range(256)) * (MAX_PAYLOAD // 256), read_chunk=257, write_chunk=131,
                      peer_read_chunk=509, peer_write_chunk=127)

    def test_single_byte_socket_boundaries(self):
        for read_chunk, write_chunk, group in ((1, 3, "hybrid"), (7, 1, "x25519")):
            with self.subTest(read_chunk=read_chunk, write_chunk=write_chunk, group=group):
                self.positive(b"\x00\xffshort-io" * 31, group=group, read_chunk=read_chunk,
                              write_chunk=write_chunk, peer_read_chunk=13, peer_write_chunk=17)

    def test_empty_application_still_requires_both_finished_and_close_notify(self):
        self.positive(b"")

    def bad_credentials(self, field):
        with self.peer_session() as peer:
            raw = bytearray.fromhex(peer.ready["settings"][field])
            raw[0] ^= 1
            code, client, _ = self.invoke(peer, b"never-forward-this-unauthenticated-application", **{field: raw.hex()})
            server = peer.finish()
            self.assertEqual(code, 1, client)
            self.assertEqual(client["status"], "error", client)
            self.assertEqual(client["stage"], "handshake", client)
            self.assertFalse(client["handshake_verified"], client)
            self.assertFalse(client["client_close_notify"], client)
            self.assertFalse(client["server_close_notify"], client)
            self.assertEqual(server["status"], "authentication_rejected", server)
            self.assertFalse(server["handshake_complete"], server)
            self.assertFalse(server["client_hello_authenticated"], server)
            self.assertFalse(server["client_finished_verified"], server)
            for key in ("uploaded_bytes", "received_bytes"):
                self.assertEqual(client[key], 0, client)
            for key in ("received_bytes", "sent_bytes", "camouflage_application_bytes"):
                self.assertEqual(server[key], 0, server)

    def test_wrong_short_id_never_exposes_application_data(self):
        self.bad_credentials("short_id_hex")

    def test_wrong_reality_public_key_never_exposes_application_data(self):
        self.bad_credentials("public_key_hex")

    def test_bare_tcp_fin_is_rejected_after_valid_echo(self):
        payload = b"a-real-echo-does-not-authenticate-a-TCP-close"
        with self.peer_session(mode="unclean-eof") as peer:
            code, client, _ = self.invoke(peer, payload)
            server = peer.finish()
            self.assertEqual(code, 1, client)
            self.assertEqual(client["status"], "error", client)
            self.assertEqual(client["stage"], "close", client)
            self.assertEqual(client["error_kind"], "UnexpectedEof", client)
            self.assertIn("close_notify", client["error"], client)
            self.assertTrue(client["payload_matches"], client)
            self.assertTrue(client["client_close_notify"], client)
            self.assertFalse(client["server_close_notify"], client)
            self.negotiated(client, server, HYBRID)
            self.assertEqual(server["status"], "intentional_unclean_eof", server)
            self.assertEqual(client["uploaded_bytes"], len(payload), client)
            self.assertEqual(client["received_bytes"], len(payload), client)
            self.assertEqual(server["received_bytes"], len(payload), server)
            self.assertEqual(server["sent_bytes"], len(payload), server)
            self.assertTrue(server["close_notify_received"], server)
            self.assertFalse(server["close_notify_sent"], server)

    def interrupted(self, stage, *, cancellation):
        delay = 600 if stage == "handshake" else 1500
        changes = {"cancel_after_ms": delay} if cancellation else {"timeout_ms": delay}
        payload = b"cancel-or-expire-with-an-owned-socket"
        with self.peer_session(mode=f"stall-{stage}") as peer:
            code, client, elapsed = self.invoke(peer, payload, **changes)
            server = peer.finish()
            self.assertEqual(code, 1, client)
            self.assertEqual(client["status"], "error", client)
            self.assertEqual(client["stage"], stage, client)
            self.assertEqual(client["error_kind"], "Interrupted" if cancellation else "TimedOut", client)
            self.assertEqual(client["error"], "SyntheticPeerCancelled" if cancellation else "SyntheticPeerDeadline", client)
            self.assertLess(elapsed, delay / 1000 + 3, client)
            self.assertFalse(client["payload_matches"], client)
            self.assertFalse(client["client_close_notify"], client)
            self.assertFalse(client["server_close_notify"], client)
            self.assertEqual(client["received_bytes"], 0, client)
            self.assertEqual(server["status"], "cancelled", server)
            self.assertTrue(server["transport_eof"], server)
            self.assertFalse(server["close_notify_received"], server)
            self.assertFalse(server["close_notify_sent"], server)
            self.assertEqual(server["sent_bytes"], 0, server)
            self.assertEqual(server["camouflage_application_bytes"], 0, server)
            if stage == "handshake":
                self.assertFalse(client["handshake_verified"], client)
                self.assertFalse(server["handshake_complete"], server)
                self.assertFalse(server["client_finished_verified"], server)
                self.assertEqual(client["uploaded_bytes"], 0, client)
                self.assertEqual(server["received_bytes"], 0, server)
            else:
                self.negotiated(client, server, HYBRID)
                self.assertEqual(client["uploaded_bytes"], len(payload), client)
                self.assertEqual(server["received_bytes"], len(payload), server)

    def test_handshake_timeout_drops_transport_and_reaps_peer(self):
        self.interrupted("handshake", cancellation=False)

    def test_handshake_cancellation_drops_transport_and_reaps_peer(self):
        self.interrupted("handshake", cancellation=True)

    def test_data_timeout_drops_transport_and_reaps_peer(self):
        self.interrupted("data", cancellation=False)

    def test_data_cancellation_drops_transport_and_reaps_peer(self):
        self.interrupted("data", cancellation=True)


class EvidenceResult(unittest.TextTestResult):
    """Preserve assertion failures alongside the exact process observations."""

    def stopTestRun(self):
        super().stopTestRun()
        directory = Path(os.environ.get("SWIRL_XRAY_EVIDENCE", ROOT / "build" / "reality-xray-evidence"))
        directory.mkdir(parents=True, exist_ok=True)
        summary = {
            "tests_run": self.testsRun, "successful": self.wasSuccessful(),
            "failures": [{"test": test.id(), "traceback": detail} for test, detail in self.failures],
            "errors": [{"test": test.id(), "traceback": detail} for test, detail in self.errors],
            "skipped": [{"test": test.id(), "reason": reason} for test, reason in self.skipped],
        }
        (directory / "test-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(resultclass=EvidenceResult, verbosity=2))
