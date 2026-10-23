"""Core sessions and probes use the same explicit native transport selection.

Requires SWIRL_TRANSPORT_RUNTIME, SWIRL_TRANSPORT_CLIENT and the pinned
SWIRL_XRAY_BINARY. All settings and origins are synthetic and loopback-only.
The example harness calls Core directly and does not extend the B-stage IR.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from test_rust_core import certificates, exact, header
import test_transport_c1_xray as c1
from transport_peer import Fixture


RECORDS = []


class ProbeOrigin(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        request = header(self.request)
        line = request.split(b"\r\n", 1)[0].decode("ascii")
        if line not in ("HEAD /health HTTP/1.1", "GET /health HTTP/1.1",
                        "HEAD /stall HTTP/1.1"):
            raise AssertionError("unexpected health request")
        self.server.requests.append(line)
        if "/stall " in line:
            self.server.stall_started.set()
            try:
                while self.request.recv(1024):
                    pass
            except ConnectionResetError:
                pass
            self.server.stall_closed.set()
            return
        self.request.sendall(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")


class TransportRuntimeTests(unittest.TestCase):
    # Share the already-pinned, independently-authenticating C1 server fixture
    # without inheriting and re-counting the unrelated C1 test methods.
    peer = c1.C1XrayTests.peer
    outbound = c1.C1XrayTests.outbound
    origin = c1.C1XrayTests.origin
    command = c1.C1XrayTests.command
    close = c1.C1XrayTests.close
    tunnel = c1.C1XrayTests.tunnel
    http = c1.C1XrayTests.http

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="swirl-c6-xray-")
        cls.folder = Path(cls.temp.name)
        cls.context, cls.ca, cls.ca_pem = certificates(cls.temp.name)
        cls.xray = os.environ["SWIRL_XRAY_BINARY"]
        cls.harness = os.environ["SWIRL_TRANSPORT_RUNTIME"]
        cls.version = subprocess.run([cls.xray, "version"], check=True,
                                     capture_output=True, text=True).stdout
        if "Xray 26.10.21" not in cls.version or "1b1647c" not in cls.version:
            raise AssertionError("fixture requires the pinned official Xray v26.10.21")
        cls.evidence = Path(os.environ.get("SWIRL_C6_EVIDENCE", cls.temp.name))
        cls.evidence.mkdir(parents=True, exist_ok=True)
        cls.serial = 0

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.origins, self.peers = [], []
        self.runtime = subprocess.Popen([self.harness], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True)
        self.addCleanup(self.close)

    def native_config(self, *peers):
        nodes, transports = [], {}
        for index, peer in enumerate(peers):
            node_id = chr(ord("a") + index)
            outbound = self.outbound(peer)
            settings = outbound.pop("websocket")
            nodes.append({"id": node_id, "outbound": outbound})
            transports[node_id] = {"type": "websocket", "settings": settings,
                                   "headers": [["X-Swirl-Probe", "c6-runtime"]]}
        return {"schema": 1, "listen": "127.0.0.1:0", "selected": "a",
                "nodes": nodes}, transports

    def start(self, config, transports):
        reply = self.command(op="start", config=config, transports=transports)
        self.assertTrue(reply["ok"], reply)
        self.port = int(reply["status"]["address"].rsplit(":", 1)[1])

    def stop(self):
        self.wait_for(lambda: self.command(op="status")["status"]["active"] == 0,
                      "completed client sessions retained their Core tasks")
        self.assertTrue(self.command(op="stop")["ok"])
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", self.port), timeout=0.5)

    def probe_origin(self):
        origin = c1.Origin(("127.0.0.1", 0), ProbeOrigin)
        origin.requests, origin.errors = [], []
        origin.stall_started, origin.stall_closed = threading.Event(), threading.Event()
        threading.Thread(target=origin.serve_forever, daemon=True).start()
        self.origins.append(origin)
        return origin

    def wait_for(self, predicate, label):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(0.01)
        self.fail(label)

    def finished_probe(self):
        def completed():
            result = self.command(op="probe_status")["probe"]
            return result if result["state"] != "running" else None
        return self.wait_for(completed, "native HEAD probe did not finish")

    def access_count(self, peer):
        return peer["access"].read_text(encoding="utf-8").count(" accepted ") \
            if peer["access"].exists() else 0

    def assert_access(self, peer, count):
        self.wait_for(lambda: self.access_count(peer) >= count,
                      "independent Xray did not authenticate all proxy requests")
        RECORDS.append({"case": self._testMethodName, "peer": peer["label"],
                        "authenticated_requests": self.access_count(peer)})

    def test_session_selection_and_reconfiguration_preserve_native_transport(self):
        first, second = self.peer(network="ws"), self.peer(network="ws")
        config, transports = self.native_config(first, second)
        config["selectors"] = [{"id": "manual", "members": ["a", "b"], "selected": "a"}]
        self.start(config, transports)
        origin, echo = self.origin(), self.origin(echo=True)
        stream, response = self.tunnel(echo)
        self.addCleanup(stream.close)
        self.assertIn(b"200 Connection Established", response)
        stream.sendall(b"before-reconfigure")
        self.assertEqual(exact(stream, 18), b"before-reconfigure")

        self.assertTrue(self.command(op="select_node", id="b")["ok"])
        self.http(origin)
        self.assertTrue(self.command(op="select_group", id="manual", member="b")["ok"])
        self.assertTrue(self.command(op="select_node", id="manual")["ok"])
        self.http(origin)
        self.assertTrue(self.command(op="configure", config=config)["ok"])
        self.http(origin)

        before = self.command(op="status")["status"]["generation"]
        removed = copy.deepcopy(config)
        removed["selected"] = "b"
        removed["nodes"].pop(0)
        removed["selectors"] = []
        rejected = self.command(op="configure", config=removed)
        self.assertEqual(rejected, {"ok": False, "error": "TransportNodeMissing"})
        incompatible = copy.deepcopy(config)
        incompatible["nodes"][0]["outbound"] = {"type": "direct"}
        rejected = self.command(op="configure", config=incompatible)
        self.assertEqual(rejected, {"ok": False, "error": "TransportProtocolUnsupported"})
        self.assertEqual(self.command(op="status")["status"]["generation"], before)

        wrong = copy.deepcopy(transports)
        wrong["a"]["settings"]["path"] = "/incorrect-path"
        self.assertTrue(self.command(op="configure_with_transports", config=config,
                                     transports=wrong)["ok"])
        rejected, response = self.tunnel(origin)
        rejected.close()
        self.assertIn(b"502 Bad Gateway", response)
        stream.sendall(b"old-session-survives")
        self.assertEqual(exact(stream, 20), b"old-session-survives")
        self.assertTrue(self.command(op="configure_with_transports", config=config,
                                     transports=transports)["ok"])
        self.http(origin)
        self.assertEqual(len(origin.requests), 4)
        self.assert_access(first, 3)  # existing echo plus two successful HTTP requests
        self.assert_access(second, 2)
        stream.close()
        self.stop()

    def test_user_and_automatic_health_probes_share_the_native_transport(self):
        peer = self.peer(network="ws")
        config, transports = self.native_config(peer)
        health, origin = self.probe_origin(), self.origin()
        url = f"http://127.0.0.1:{health.server_address[1]}/health"
        self.start(config, transports)
        self.assertTrue(self.command(op="probe_start", url=url, timeout_ms=1000)["ok"])
        self.assertEqual(self.finished_probe()["state"], "succeeded")
        self.assertEqual(health.requests, ["HEAD /health HTTP/1.1"])

        automatic = copy.deepcopy(config)
        automatic["selected"] = "healthy"
        automatic["selectors"] = [{"id": "healthy", "strategy": "fallback", "members": ["a"],
                                    "probe": {"url": url, "interval_ms": 10000,
                                              "timeout_ms": 1000, "expected_status": 204}}]
        self.assertTrue(self.command(op="configure", config=automatic)["ok"])
        self.wait_for(lambda: self.command(op="status")["status"]["policies"]["healthy"]["selected"] == "a",
                      "automatic policy did not probe through WebSocket")
        self.http(origin)
        self.assertIn("GET /health HTTP/1.1", health.requests)

        wrong = copy.deepcopy(transports)
        wrong["a"]["settings"]["path"] = "/incorrect-path"
        self.assertTrue(self.command(op="configure_with_transports", config=automatic,
                                     transports=wrong)["ok"])
        def unhealthy():
            result = self.command(op="status")["status"]["policies"]["healthy"]
            return result if result["checks"] else None
        result = self.wait_for(unhealthy, "wrong-path health attempt did not finish")
        self.assertIsNone(result["selected"])
        self.assertFalse(result["members"][0]["healthy"])
        self.assertEqual(result["members"][0]["error"], "WebSocketUpgradeRejected")
        self.assertTrue(self.command(op="select_node", id="a")["ok"])
        self.assertTrue(self.command(op="probe_start", url=url, timeout_ms=1000)["ok"])
        failed = self.finished_probe()
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["failure"]["code"], "WebSocketUpgradeRejected")
        self.assertEqual(health.requests, ["HEAD /health HTTP/1.1", "GET /health HTTP/1.1"])
        self.assert_access(peer, 3)
        self.stop()

    def test_probe_cancellation_timeout_and_wss_runtime_payload(self):
        peer = self.peer(network="ws")
        config, transports = self.native_config(peer)
        stalled = self.probe_origin()
        url = f"http://127.0.0.1:{stalled.server_address[1]}/stall"
        self.start(config, transports)
        self.assertTrue(self.command(op="probe_start", url=url, timeout_ms=3000)["ok"])
        self.assertTrue(stalled.stall_started.wait(3))
        self.assertEqual(self.command(op="probe_cancel")["probe"]["state"], "cancelled")
        self.assertTrue(stalled.stall_closed.wait(3), "cancelled proxy request retained its socket")
        stalled.stall_started.clear()
        stalled.stall_closed.clear()
        self.assertTrue(self.command(op="probe_start", url=url, timeout_ms=200)["ok"])
        timed_out = self.finished_probe()
        self.assertEqual(timed_out["state"], "failed")
        self.assertEqual(timed_out["failure"]["code"], "UrlTestTimeout")
        self.assertTrue(stalled.stall_closed.wait(3))
        self.assert_access(peer, 2)
        self.stop()

        secured = self.peer(network="ws", tls=True)
        config, transports = self.native_config(secured)
        self.start(config, transports)
        origin = self.origin(tls=True)
        self.http(origin)
        self.assertEqual(origin.tls_closes, 1)
        self.assert_access(secured, 1)
        self.stop()

    def test_grpc_and_xhttp_maps_route_sessions_and_both_probe_types(self):
        native = Fixture("C6-core-map")
        native.evidence = self.evidence / native.folder.name
        native.evidence.mkdir(parents=True, exist_ok=True)
        self.addCleanup(native.close)
        peers = {
            "grpc-node": native.peer("grpc", tls=True, service_name="swirl-core-c6"),
            "xhttp-node": native.peer("xhttp", tls=True, path="/c6/core/xhttp?token=runtime"),
        }
        config = {"schema": 1, "listen": "127.0.0.1:0", "selected": "grpc-node",
                  "nodes": [{"id": node_id, "outbound": copy.deepcopy(peer["outbound"])}
                            for node_id, peer in peers.items()],
                  "selectors": [{"id": "manual", "members": list(peers),
                                 "selected": "grpc-node"}]}
        transports = {node_id: copy.deepcopy(peer["transport"])
                      for node_id, peer in peers.items()}
        health, origin = self.probe_origin(), self.origin()
        url = f"http://127.0.0.1:{health.server_address[1]}/health"
        self.start(config, transports)
        self.http(origin)
        self.assertTrue(self.command(op="probe_start", url=url, timeout_ms=1000)["ok"])
        self.assertEqual(self.finished_probe()["state"], "succeeded")

        self.assertTrue(self.command(op="select_group", id="manual", member="xhttp-node")["ok"])
        self.assertTrue(self.command(op="select_node", id="manual")["ok"])
        self.http(origin)
        self.assertTrue(self.command(op="select_node", id="xhttp-node")["ok"])
        self.assertTrue(self.command(op="probe_start", url=url, timeout_ms=1000)["ok"])
        self.assertEqual(self.finished_probe()["state"], "succeeded")
        self.assertEqual(health.requests, ["HEAD /health HTTP/1.1"] * 2)
        for peer in peers.values():
            self.assert_access(peer, 2)

        automatic = copy.deepcopy(config)
        automatic["selected"] = "healthy-grpc-node"
        automatic["selectors"] = [
            {"id": f"healthy-{node_id}", "strategy": "fallback", "members": [node_id],
             "probe": {"url": url, "interval_ms": 60000,
                       "timeout_ms": 1000, "expected_status": 204}}
            for node_id in peers
        ]
        self.assertTrue(self.command(op="configure", config=automatic)["ok"])

        def checked_policies():
            result = self.command(op="status")["status"]["policies"]
            return result if all(result[f"healthy-{node_id}"]["checks"] for node_id in peers) else None

        policies = self.wait_for(checked_policies, "native automatic health probes did not complete")
        for node_id in peers:
            policy = policies[f"healthy-{node_id}"]
            self.assertEqual(policy["selected"], node_id, policy)
            self.assertTrue(policy["members"][0]["healthy"], policy)
        self.http(origin)
        self.assertTrue(self.command(op="select_node", id="healthy-xhttp-node")["ok"])
        self.http(origin)
        self.assertEqual(health.requests.count("GET /health HTTP/1.1"), 2)
        self.assertEqual(origin.requests, ["http"] * 4)
        for peer in peers.values():
            self.assert_access(peer, 4)

        # A rejected typed mode must not replace either node's valid map or
        # reset policy health; wrong but syntactically valid routes then prove
        # that both probe paths actually retain their selected transport.
        before = self.command(op="status")["status"]["generation"]
        unsupported = copy.deepcopy(transports)
        unsupported["xhttp-node"]["config"]["mode"] = "auto"
        self.assertEqual(self.command(op="configure_with_transports", config=automatic,
                                      transports=unsupported),
                         {"ok": False, "error": "XHttpModeUnsupported"})
        self.assertEqual(self.command(op="status")["status"]["generation"], before)
        wrong = copy.deepcopy(transports)
        wrong["grpc-node"]["config"]["service_name"] = "unknown-core-service"
        wrong["xhttp-node"]["config"]["path"] = "/incorrect-core-path"
        self.assertTrue(self.command(op="configure_with_transports", config=automatic,
                                     transports=wrong)["ok"])
        failed = self.wait_for(checked_policies, "wrong native service/path health probes did not finish")
        failures = {}
        for node_id in peers:
            policy = failed[f"healthy-{node_id}"]
            self.assertIsNone(policy["selected"], policy)
            self.assertFalse(policy["members"][0]["healthy"], policy)
            self.assertNotEqual(policy["members"][0]["error"], "PolicyProbeTimeout", policy)
            self.assertTrue(self.command(op="select_node", id=node_id)["ok"])
            self.assertTrue(self.command(op="probe_start", url=url, timeout_ms=1000)["ok"])
            probe = self.finished_probe()
            self.assertEqual(probe["state"], "failed", probe)
            self.assertNotEqual(probe["failure"]["code"], "UrlTestTimeout", probe)
            failures[node_id] = {"automatic": policy["members"][0]["error"],
                                 "manual": probe["failure"]["code"]}
            self.assertEqual(self.access_count(peers[node_id]), 4)
        self.assertEqual(health.requests, ["HEAD /health HTTP/1.1"] * 2
                         + ["GET /health HTTP/1.1"] * 2)
        RECORDS.append({"case": self._testMethodName, "negative_probe_errors": failures,
                        "origin_http_requests": len(origin.requests),
                        "origin_health_requests": len(health.requests)})
        self.stop()


if __name__ == "__main__":
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TransportRuntimeTests))
    if directory := os.environ.get("SWIRL_C6_EVIDENCE"):
        evidence = {"tests_run": result.testsRun, "failures": len(result.failures),
                    "errors": len(result.errors), "skips": len(result.skipped),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "exit_code": 0 if result.wasSuccessful() else 1,
                    "platform": platform.platform(), "public_network_tested": False,
                    "xray_version": TransportRuntimeTests.version.strip(), "cases": RECORDS,
                    "runtime_sha256": hashlib.sha256(Path(os.environ["SWIRL_TRANSPORT_RUNTIME"])
                                                      .read_bytes()).hexdigest()}
        Path(directory).mkdir(parents=True, exist_ok=True)
        (Path(directory) / "summary.json").write_text(json.dumps(evidence, indent=2) + "\n")
    sys.exit(0 if result.wasSuccessful() else 1)
