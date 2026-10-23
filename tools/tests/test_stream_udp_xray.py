"""Classic VLESS/Trojan UDP through the actual Rust Core and official Xray.

Xray is the independently authenticated server only. Python implements SOCKS5
clients and application UDP/DNS targets; it never implements a proxy peer.
The native Core's existing transport selection is exercised unchanged.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import socket
import subprocess
import tempfile
import threading
import time
import unittest

import test_quic_core as core_fixture
import test_tuic_reference as tuic_fixture
from test_socks5_udp import packet
from transport_peer import Fixture, XRAY


class StreamUdpXrayTests(unittest.TestCase):
    command = core_fixture.QuicCoreTests.command
    associate = core_fixture.QuicCoreTests.associate
    udp_exchange = core_fixture.QuicCoreTests.udp_exchange
    stop = core_fixture.QuicCoreTests.stop
    close_runtime = core_fixture.QuicCoreTests.close_runtime
    dns_origin = core_fixture.QuicCoreTests.dns_origin
    origin = tuic_fixture.TuicReferenceTests.origin
    records = []

    @classmethod
    def setUpClass(cls):
        cls.harness = Path(os.environ["SWIRL_TRANSPORT_RUNTIME"]).resolve(strict=True)
        cls.xray = Path(os.environ["SWIRL_XRAY_BINARY"]).resolve(strict=True)
        Fixture._version(str(cls.xray), XRAY)

    def setUp(self):
        self.fixture = Fixture("X14-A6-stream-udp")
        self.addCleanup(self.fixture.close)
        self.origins, self.associations = [], []

        def close_origins():
            for origin in self.origins:
                origin.shutdown()
                origin.server_close()

        self.addCleanup(close_origins)
        self.stderr = tempfile.TemporaryFile()
        self.runtime = subprocess.Popen([str(self.harness)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self.stderr, text=True)
        self.responses = queue.Queue(maxsize=32)

        def reader():
            for line in self.runtime.stdout:
                self.responses.put(line)
            self.responses.put(None)

        self.reader = threading.Thread(target=reader, daemon=True)
        self.reader.start()
        self.addCleanup(self.close_runtime)

    def peer(self, protocol="vless", network="raw", tls=True):
        peer = self.fixture.peer(network, protocol=protocol, tls=tls)
        # The shared TCP suite permits only TCP loopback targets. Restart the
        # same fixed official server with an explicit UDP-only loopback rule.
        # No configuration outside this isolated fixture is modified.
        self.fixture.terminate(peer)
        peer["config"]["outbounds"][0]["settings"]["finalRules"][0]["network"] = "udp"
        path = self.fixture.folder / f"{peer['label']}.json"
        path.write_text(json.dumps(peer["config"]), encoding="utf-8")
        self.restart(peer)
        peer["outbound"]["udp"] = True
        return peer

    def restart(self, peer):
        path = self.fixture.folder / f"{peer['label']}.json"
        peer["process"] = subprocess.Popen([str(self.xray), "run", "-config", str(path)],
            stdout=peer["output"], stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.assertIsNone(peer["process"].poll(), "official Xray peer exited")
            try:
                with socket.create_connection((peer["host"], peer["port"]), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.02)
        self.fail("official Xray UDP peer did not start")

    def start(self, *peers, outbounds=None, embedded=False):
        outbounds = copy.deepcopy(outbounds or [peer["outbound"] for peer in peers])
        transports = {f"n{index}": peer["transport"] for index, peer in enumerate(peers)}
        if embedded:
            for node, peer in zip(outbounds, peers):
                node["transport"] = peer["transport"]
            transports = {}
        config = {"schema": 1, "listen": "127.0.0.1:0", "selected": "n0",
            "nodes": [{"id": f"n{index}", "outbound": node} for index, node in enumerate(outbounds)],
            "limits": {"max_connections": 128, "handshake_timeout_ms": 2000}}
        reply = self.command(op="start", config=config, transports=transports)
        self.assertTrue(reply["ok"], reply)
        self.port = int(reply["status"]["address"].rsplit(":", 1)[1])
        self.protocol = peers[0]["protocol"] + ":" + peers[0]["network"] + (
            ":tls" if peers[0]["tls"] else ":plain")
        return config

    @contextlib.contextmanager
    def running(self, *peers, **options):
        self.start(*peers, **options)
        try:
            yield
        finally:
            self.stop()

    def assert_accepted(self, peer, origin):
        origin.target_host, origin.target_port = "127.0.0.1", origin.server_address[1]
        self.fixture.assert_accepted(peer, origin)

    def test_tcp_tls_ws_and_grpc_transports_authenticate_and_relay_real_udp(self):
        cases = [("vless", "raw", False), ("vless", "raw", True),
                 ("vless", "ws", False), ("vless", "ws", True),
                 ("trojan", "raw", True), ("trojan", "ws", True),
                 ("vless", "grpc", True), ("trojan", "grpc", True)]
        for protocol, network, tls in cases:
            with self.subTest(protocol=protocol, network=network, tls=tls):
                peer, origin = self.peer(protocol, network, tls), self.origin(udp=True)
                with self.running(peer):
                    association = self.associate()
                    for size in (37, 1500, 4000):
                        payload = bytes([size % 251]) * size
                        self.assertEqual(self.udp_exchange(association, origin, payload), payload)
                    self.assertEqual([len(value) for value in origin.received], [37, 1500, 4000])
                    self.assert_accepted(peer, origin)

    def test_vless_targets_have_separate_carriers_and_trojan_frames_keep_each_address(self):
        for protocol in ("vless", "trojan"):
            with self.subTest(protocol=protocol):
                peer = self.peer(protocol)
                first, second = self.origin(udp=True), self.origin(udp=True)
                with self.running(peer):
                    association = self.associate()
                    for origin, payload in ((first, b"first"), (second, b"second"), (first, b"first-again")):
                        self.assertEqual(self.udp_exchange(association, origin, payload), payload)
                    self.assertEqual(first.received, [b"first", b"first-again"])
                    self.assertEqual(second.received, [b"second"])
                    self.assert_accepted(peer, first)
                    if protocol == "vless":
                        self.assert_accepted(peer, second)
                    # Trojan's access event records the authenticated carrier's
                    # initial destination only. The second independent origin's
                    # received bytes and address-bearing reply prove per-packet
                    # routing; no nonexistent per-datagram access event is used.

    def test_dns_and_ipv6_destination_over_classic_udp(self):
        query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
        for protocol in ("vless", "trojan"):
            with self.subTest(protocol=protocol):
                peer, origin = self.peer(protocol), self.dns_origin()
                with self.running(peer):
                    association = self.associate()
                    for host in ("127.0.0.1", "::1", "localhost"):
                        response = self.udp_exchange(association, origin, query, host)
                        self.assertEqual(response[:4], b"\x12\x34\x81\x80")
                    self.assertEqual(origin.received, [query] * 3)

    def test_wrong_credentials_and_tls_name_never_reach_the_udp_target(self):
        for protocol in ("vless", "trojan"):
            peer, origin = self.peer(protocol), self.origin(udp=True)
            for problem in ("credential", "sni"):
                with self.subTest(protocol=protocol, problem=problem):
                    node = copy.deepcopy(peer["outbound"])
                    if problem == "sni":
                        node["tls"]["server_name"] = "wrong.invalid"
                    elif protocol == "vless":
                        node["uuid"] = "ffeeddcc-bbaa-9988-7766-554433221100"
                    else:
                        node["password"] = "incorrect-synthetic-only"
                    with self.running(peer, outbounds=[node]):
                        association = self.associate()
                        association[1].settimeout(2.5)
                        with self.assertRaises(socket.timeout):
                            self.udp_exchange(association, origin, b"must-not-forward")
                        self.assertEqual(origin.received, [])

    def test_node_selection_preserves_existing_udp_association_and_control_close_stops_it(self):
        for protocol in ("vless", "trojan"):
            with self.subTest(protocol=protocol):
                first, second, origin = self.peer(protocol), self.peer(protocol), self.origin(udp=True)
                with self.running(first, second):
                    old = self.associate()
                    self.assertEqual(self.udp_exchange(old, origin, b"node-zero"), b"node-zero")
                    self.assertTrue(self.command(op="select_node", id="n1")["ok"])
                    new = self.associate()
                    self.assertEqual(self.udp_exchange(new, origin, b"node-one"), b"node-one")
                    self.assertEqual(self.udp_exchange(old, origin, b"old-retained"), b"old-retained")
                    self.assert_accepted(first, origin)
                    self.assert_accepted(second, origin)
                    old[0].close()
                    deadline = time.monotonic() + 2
                    while self.command(op="status")["status"]["active"] != 1 and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertEqual(self.command(op="status")["status"]["active"], 1)
                    old[1].settimeout(0.2)
                    old[1].sendto(packet("127.0.0.1", origin.server_address[1], b"closed"), old[2])
                    with self.assertRaises((socket.timeout, ConnectionResetError)):
                        old[1].recvfrom(65535)
                    self.assertEqual(origin.received, [b"node-zero", b"node-one", b"old-retained"])

    def test_embedded_transport_has_the_same_udp_behavior_as_runtime_override(self):
        for protocol in ("vless", "trojan"):
            with self.subTest(protocol=protocol):
                peer, origin = self.peer(protocol, "grpc"), self.origin(udp=True)
                with self.running(peer, embedded=True):
                    self.assertEqual(self.udp_exchange(self.associate(), origin, b"embedded-grpc"), b"embedded-grpc")
                    self.assert_accepted(peer, origin)

    def test_closed_carriers_do_not_replay_and_new_associations_reconnect(self):
        for protocol in ("vless", "trojan"):
            with self.subTest(protocol=protocol):
                peer, origin = self.peer(protocol), self.origin(udp=True)
                with self.running(peer):
                    old = self.associate()
                    self.assertEqual(self.udp_exchange(old, origin, b"before-restart"), b"before-restart")
                    self.fixture.terminate(peer)
                    old[1].settimeout(0.3)
                    with self.assertRaises(socket.timeout):
                        self.udp_exchange(old, origin, b"closed-carrier")
                    self.restart(peer)
                    with self.assertRaises(socket.timeout):
                        self.udp_exchange(old, origin, b"must-not-replay")
                    fresh = self.associate()
                    self.assertEqual(self.udp_exchange(fresh, origin, b"new-carrier"), b"new-carrier")
                    self.assertEqual(origin.received, [b"before-restart", b"new-carrier"])

    def test_official_reply_size_boundaries_and_retained_upstream_limits(self):
        for protocol, maximum in (("vless", 8190), ("trojan", 8181)):
            with self.subTest(protocol=protocol):
                peer, origin = self.peer(protocol), self.origin(udp=True)
                with self.running(peer):
                    association = self.associate()
                    payload = b"b" * maximum
                    self.assertEqual(self.udp_exchange(association, origin, payload), payload)
                    association[1].settimeout(0.4)
                    oversized = b"x" * (maximum + 1)
                    with self.assertRaises(socket.timeout):
                        self.udp_exchange(association, origin, oversized)
                    self.assertEqual(origin.received, [payload, oversized])
                    self.records.append({"case": self._testMethodName, "protocol": protocol,
                        "verified_ipv4_payload_limit": maximum,
                        "upstream_limitation_probe": True, "native_interoperability_pass": False,
                        "limitation": "official Xray 8192-byte response buffer includes framing; one byte larger reached the origin but was not returned"})

    @classmethod
    def tearDownClass(cls):
        if path := os.environ.get("SWIRL_STREAM_UDP_EVIDENCE"):
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps({"runtime": "Swirl Rust Core",
                "runtime_sha256": hashlib.sha256(cls.harness.read_bytes()).hexdigest(),
                "server": f"official Xray {XRAY[0]} {XRAY[1]}",
                "server_sha256": hashlib.sha256(cls.xray.read_bytes()).hexdigest(),
                "platform": platform.platform(), "qt_product_acceptance": False,
                "scope": "classic VLESS command 2 and Trojan command 3; no Vision/XUDP claim",
                "records": cls.records}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
