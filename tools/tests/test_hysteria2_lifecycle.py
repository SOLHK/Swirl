"""Actual future cancellation and cleanup before exit through pinned Hysteria2.

The native driver reuses one runtime for cancellation and reconnect. Its task
counts are asserted before process exit; terminating a process is not a pass.
This suite deliberately does not inherit or alter the original 17-method suite.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest

from native_client_stack import client_command, stack_receipt
from test_hysteria2_official import (
    OFFICIAL_COMMIT,
    OFFICIAL_SHA256,
    OFFICIAL_VERSION,
    OfficialPeer,
    TCP,
    certificate_files,
)


class LifecycleEcho(socketserver.BaseRequestHandler):
    condition = threading.Condition()
    active = 0
    accepted = 0
    received_bytes = 0
    closed = 0

    def handle(self):
        cls = type(self)
        with cls.condition:
            cls.active += 1
            cls.accepted += 1
            cls.condition.notify_all()
        self.request.settimeout(10)
        try:
            while True:
                data = self.request.recv(16384)
                if not data:
                    self.request.shutdown(socket.SHUT_WR)
                    return
                with cls.condition:
                    cls.received_bytes += len(data)
                self.request.sendall(data)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # Cancellation is allowed to reset the target connection. The
            # reconnect independently has to perform authenticated normal EOF.
            pass
        finally:
            with cls.condition:
                cls.active -= 1
                cls.closed += 1
                cls.condition.notify_all()


class Hysteria2Lifecycle(unittest.TestCase):
    def test_pending_and_authenticated_future_drop_then_same_runtime_reconnect(self):
        server = Path(os.environ["HY2_SERVER"]).resolve(strict=True)
        client = Path(os.environ["HY2_LIFECYCLE_CLIENT"]).resolve(strict=True)
        server_hash = hashlib.sha256(server.read_bytes()).hexdigest()
        self.assertIn(server_hash, OFFICIAL_SHA256.values())
        version = subprocess.check_output(
            [str(server), "version"], stderr=subprocess.STDOUT, timeout=10
        ).decode()
        self.assertIn(OFFICIAL_VERSION, version)
        self.assertIn(OFFICIAL_COMMIT, version)
        receipt = {
            "official_version": OFFICIAL_VERSION,
            "official_commit": OFFICIAL_COMMIT,
            "official_server_sha256": server_hash,
            "client_sha256": hashlib.sha256(client.read_bytes()).hexdigest(),
            "client_role": "Swirl native Rust",
            "server_role": "official Hysteria2 only",
            "qt_product_acceptance": False,
        }
        with tempfile.TemporaryDirectory(prefix="swirl-hy2-lifecycle-") as temporary:
            directory = Path(temporary)
            cert, key, ca, _ = certificate_files(directory)
            peer = OfficialPeer(
                server, directory, cert, key, "synthetic-lifecycle-only", "lifecycle"
            )
            origin = None
            thread = None
            try:
                with LifecycleEcho.condition:
                    LifecycleEcho.active = LifecycleEcho.accepted = 0
                    LifecycleEcho.received_bytes = LifecycleEcho.closed = 0
                origin = TCP(("127.0.0.1", 0), LifecycleEcho)
                thread = threading.Thread(target=origin.serve_forever, daemon=True)
                thread.start()
                request = {
                    "config": {
                        "host": "127.0.0.1",
                        "port": peer.port,
                        "password": peer.password,
                        "tls": {
                            "server_name": "hy2.test",
                            "alpn": ["h3"],
                            "ca_der_base64": ca,
                        },
                    },
                    "target_host": "127.0.0.1",
                    "target_port": origin.server_address[1],
                    "timeout_ms": 10000,
                }
                started = time.monotonic()
                completed = subprocess.run(
                    client_command(client), input=json.dumps(request), text=True,
                    capture_output=True, timeout=15
                )
                measured_stack = stack_receipt(completed.stderr)
                try:
                    report = json.loads(completed.stdout)
                except (TypeError, ValueError):
                    report = {"ok": False, "code": "LifecycleDriverOutput"}
                receipt.update(
                    client_exit=completed.returncode,
                    elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                    main_stack_limit=measured_stack,
                    result=report,
                )
                self.assertEqual(completed.returncode, 0, report)
                self.assertTrue(report.get("ok"), report)
                self.assertEqual(report["runtime"], "current_thread")
                self.assertEqual(report["baseline_alive_tasks"], 0)
                self.assertTrue(report["cleanup_asserted_before_process_exit"])
                early = report["connect_future_cancel"]
                self.assertGreater(early["alive_tasks_before_cancel"], 0)
                self.assertEqual(early["alive_tasks_after_drop"], 0)
                cancelled = report["authenticated_read_cancel"]
                self.assertTrue(cancelled["future_owned_stream"])
                self.assertGreater(cancelled["alive_tasks_before_cancel"], 0)
                self.assertEqual(cancelled["alive_tasks_after_drop"], 0)
                reconnect = report["same_runtime_reconnect"]
                self.assertEqual(reconnect["close"], "clean")
                self.assertEqual(reconnect["alive_tasks_after_close"], 0)
                for result, size in ((cancelled, 4096), (reconnect, 65536)):
                    payload = bytes((position * 37 + 11) % 251 for position in range(size))
                    self.assertEqual(result["uploaded"], size)
                    self.assertEqual(result["downloaded"], size)
                    self.assertEqual(result["sha256"], hashlib.sha256(payload).hexdigest())
                with LifecycleEcho.condition:
                    closed = LifecycleEcho.condition.wait_for(
                        lambda: LifecycleEcho.active == 0 and LifecycleEcho.closed == 2,
                        timeout=2,
                    )
                    receipt["independent_target"] = {
                        "accepted_connections": LifecycleEcho.accepted,
                        "closed_connections": LifecycleEcho.closed,
                        "active_connections": LifecycleEcho.active,
                        "received_bytes": LifecycleEcho.received_bytes,
                    }
                self.assertTrue(closed, receipt["independent_target"])
                self.assertEqual(LifecycleEcho.accepted, 2)
                self.assertEqual(LifecycleEcho.received_bytes, 4096 + 65536)
            finally:
                peer.stop()
                if origin is not None:
                    origin.shutdown()
                    origin.server_close()
                if thread is not None:
                    thread.join(timeout=5)
                destination = os.environ.get("HY2_LIFECYCLE_EVIDENCE")
                if destination:
                    path = Path(destination)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
