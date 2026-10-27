"""HTTP CONNECT / SOCKS4/4a/5 through Swirl and the fixed official Xray server.

Only the unmodified Xray executable implements the proxy server. Python owns
application clients/targets and test lifecycle; the proxy client is Swirl Rust.
Xray JSON HTTP/SOCKS5 imports run without post-export credential or transport
changes; plain SOCKS5 exports preserve Xray's native UDP capability. SOCKS4/4a
import the V2Ray v4 JSON version field documented since v4.42.2, then use Xray's
official server handshake. This is not Qt acceptance.
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

import test_quic_core as core_fixture
import test_tuic_reference as tuic_fixture
import test_vmess_xray as vmess_fixture
from test_rust_core import exact, header
from transport_peer import Fixture, HTTP_BODY, XRAY, pattern_hash


USERNAME = "synthetic-basic-user"
PASSWORD = "synthetic-basic-password"


class BasicProxyXrayTests(unittest.TestCase):
    command = core_fixture.QuicCoreTests.command
    associate = core_fixture.QuicCoreTests.associate
    udp_exchange = core_fixture.QuicCoreTests.udp_exchange
    stop = core_fixture.QuicCoreTests.stop
    close_runtime = core_fixture.QuicCoreTests.close_runtime
    socks_connect = core_fixture.QuicCoreTests.connect
    echo_origin = core_fixture.QuicCoreTests.echo_origin
    dns_origin = core_fixture.QuicCoreTests.dns_origin
    udp_origin = tuic_fixture.TuicReferenceTests.origin
    finite_echo_origin = vmess_fixture._VmessXrayBase.finite_echo_origin
    records = []
    peer_records = []

    @classmethod
    def setUpClass(cls):
        cls.harness = Path(os.environ["SWIRL_TRANSPORT_RUNTIME"]).resolve(strict=True)
        cls.inspector = Path(os.environ["SWIRL_INSPECT_BINARY"]).resolve(strict=True)
        cls.xray = Path(os.environ["SWIRL_XRAY_BINARY"]).resolve(strict=True)
        cls.version = Fixture._version(str(cls.xray), XRAY)

    def setUp(self):
        self.fixture = Fixture("X14-A6-basic-proxies")
        self.addCleanup(self.fixture.close)
        self.addCleanup(self.record_peers)
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

    def peer(self, protocol, *, auth=False, host="127.0.0.1"):
        if protocol not in ("http", "socks"):
            raise ValueError("only official HTTP/SOCKS server protocols are used")
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as reserve:
            reserve.bind((host, 0))
            port = reserve.getsockname()[1]
        label = f"{len(self.fixture.peers):02d}-{protocol}-{'password' if auth else 'noauth'}"
        access = self.fixture.evidence / f"{label}-access.log"
        error = self.fixture.evidence / f"{label}-error.log"
        output = (self.fixture.evidence / f"{label}-process.log").open("w", encoding="utf-8")
        settings = {}
        if protocol == "socks":
            settings.update({"auth": "password" if auth else "noauth", "udp": True, "ip": host})
        if auth:
            settings["accounts"] = [{"user": USERNAME, "pass": PASSWORD}]
        config = {
            "log": {"access": str(access), "error": str(error), "loglevel": "debug"},
            "inbounds": [{"listen": host, "port": port, "protocol": protocol,
                          "settings": settings, "streamSettings": {"network": "raw"}}],
            "outbounds": [{"protocol": "freedom", "settings": {"finalRules": [
                {"action": "allow", "network": network, "ip": ["127.0.0.0/8", "::1/128"]}
                for network in ("tcp", "udp")]}}],
        }
        path = self.fixture.folder / f"{label}.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        peer = {"host": host, "port": port, "protocol": protocol, "auth": auth,
            "label": label, "version": self.version, "config": config,
            "output": output, "access": access, "error": error, "path": path}
        peer["process"] = subprocess.Popen([str(self.xray), "run", "-config", str(path)],
            stdout=output, stderr=subprocess.STDOUT)
        self.fixture.peers.append(peer)
        self.ready(peer)
        return peer

    def ready(self, peer):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.assertIsNone(peer["process"].poll(), "fixed official Xray server exited")
            try:
                with socket.create_connection((peer["host"], peer["port"]), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.02)
        self.fail("official Xray server readiness timeout")

    def record_peers(self):
        for peer in self.fixture.peers:
            config = copy.deepcopy(peer["config"])
            config["log"] = {"loglevel": "debug", "access": "access.log", "error": "error.log"}
            for account in config["inbounds"][0]["settings"].get("accounts", []):
                account.update({"user": "[synthetic fixture user]", "pass": "[redacted synthetic password]"})
            log = peer["access"].read_text(encoding="utf-8") if peer["access"].exists() else ""
            self.peer_records.append({"case": self._testMethodName, "label": peer["label"],
                "command": [self.xray.name, "run", "-config", peer["path"].name],
                "config": config, "accepted_requests": log.count("accepted"),
                "access_sha256": hashlib.sha256(log.encode()).hexdigest()})
            self.assertNotIn(PASSWORD, log)

    def imported(self, peer, *, credentials=None):
        endpoint = {"address": peer["host"], "port": peer["port"]}
        if credentials is None and peer["auth"]:
            credentials = (USERNAME, PASSWORD)
        if credentials:
            endpoint["users"] = [{"user": credentials[0], "pass": credentials[1]}]
        source = {"outbounds": [{"tag": "synthetic-basic-node", "protocol": peer["protocol"],
            "settings": {"servers": [endpoint]}, "streamSettings": {"network": "tcp", "security": "none"}}]}
        native = self.export(source)
        node = native["nodes"][0]["outbound"]
        self.assertEqual(node["type"], "http_connect" if peer["protocol"] == "http" else "socks5")
        if credentials:
            self.assertEqual(node["auth"], {"username": credentials[0], "password": credentials[1]})
        else:
            self.assertIsNone(node.get("auth"))
        return native

    def export(self, source):
        result = subprocess.run([str(self.inspector), "--xray-json", "--private-json",
            "--native-node", "0", "--listen", "127.0.0.1:0"], input=json.dumps(source),
            text=True, capture_output=True, timeout=10)
        exported = json.loads(result.stdout)
        report = exported.get("report", exported)
        self.assertEqual(result.returncode, 0, report)
        self.assertTrue(report["ok"], report)
        self.assertFalse(report["network_verified"])
        return exported["native_config"]

    def start(self, config, protocol):
        # No side-channel transport or alternate client core is supplied.
        response = self.command(op="start", config=config)
        self.assertTrue(response["ok"], response)
        self.port = int(response["status"]["address"].rsplit(":", 1)[1])
        self.protocol = protocol

    @contextlib.contextmanager
    def running(self, config, protocol):
        self.start(config, protocol)
        try:
            yield
        finally:
            self.stop()

    def tunnel(self, origin, ingress="http_connect"):
        if ingress == "socks5":
            return self.socks_connect(origin)
        stream = socket.create_connection(("127.0.0.1", self.port), timeout=6)
        stream.settimeout(6)
        host = getattr(origin, "target_host", origin.server_address[0])
        target = f"[{host}]:{origin.server_address[1]}" if ":" in host else f"{host}:{origin.server_address[1]}"
        try:
            stream.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
            self.assertIn(b"200 Connection Established", header(stream))
            return stream
        except BaseException:
            stream.close()
            raise

    def application(self, peer, origin, ingress="http_connect", *, native_import=True):
        started = time.monotonic()
        stream = self.tunnel(origin, ingress)
        if origin.context:
            context = ssl.create_default_context(cadata=self.fixture.ca_pem)
            stream = context.wrap_socket(stream, server_hostname="localhost")
        with stream:
            stream.sendall(b"GET /transport HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            self.assertIn(b"200 OK", header(stream))
            self.assertEqual(hashlib.sha256(exact(stream, len(HTTP_BODY))).digest(),
                             hashlib.sha256(HTTP_BODY).digest())
            if origin.context:
                stream.unwrap().close()
            else:
                stream.shutdown(socket.SHUT_WR)
                self.assertEqual(stream.recv(1), b"")
        self.fixture.assert_origin_closed(origin)
        self.fixture.assert_accepted(peer, origin)
        self.records.append({"case": self._testMethodName, "protocol": peer["protocol"],
            "authentication": "password" if peer["auth"] else "none", "ingress": ingress,
            "application_tls": bool(origin.context), "downloaded": len(HTTP_BODY),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "normal_close": True, "official_accepted": True, "native_import": native_import})

    def test_xray_import_http_https_authentication_and_normal_close(self):
        for protocol in ("http", "socks"):
            for auth in (False, True):
                with self.subTest(protocol=protocol, auth=auth):
                    peer = self.peer(protocol, auth=auth)
                    with self.running(self.imported(peer), protocol):
                        for ingress in ("http_connect", "socks5"):
                            for tls in (False, True):
                                self.application(peer, self.fixture.origin(tls=tls), ingress)

    def test_authenticated_socks5_udp_echo_dns_and_association_close(self):
        query = b"\x51\x72\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
        for auth in (False, True):
            with self.subTest(auth=auth):
                peer = self.peer("socks", auth=auth)
                config = self.imported(peer)
                self.assertTrue(config["nodes"][0]["outbound"]["udp"])
                origin, dns = self.udp_origin(udp=True), self.dns_origin()
                with self.running(config, "socks5-udp"):
                    association = self.associate()
                    for size in (1, 37, 1400, 4000):
                        payload = bytes([size % 251]) * size
                        self.assertEqual(self.udp_exchange(association, origin, payload), payload)
                    answer = self.udp_exchange(association, dns, query, host="localhost")
                    self.assertEqual(answer[:2], query[:2])
                    self.assertEqual(answer[2:4], b"\x81\x80")
                    self.assertEqual(answer[-4:], b"\xc0\x00\x02\x01")
                    self.assertEqual(origin.received, [bytes([size % 251]) * size for size in (1, 37, 1400, 4000)])
                    self.assertEqual(dns.received, [query])
                    origin.target_host, origin.target_port = "127.0.0.1", origin.server_address[1]
                    self.fixture.assert_accepted(peer, origin)
                    self.records.append({"case": self._testMethodName, "protocol": "socks5",
                        "authentication": "password" if auth else "none", "udp_sizes": [1, 37, 1400, 4000],
                        "dns_wire_query_and_reply": True, "remote_domain_destination": True,
                        "native_import": True, "xray_import_udp_enabled": True,
                        "official_accepted": True})

    def test_invalid_tcp_credentials_are_rejected_without_origin_traffic(self):
        for protocol in ("http", "socks"):
            peer = self.peer(protocol, auth=True)
            for label, credentials in (("wrong-user", ("incorrect-user", PASSWORD)),
                                       ("wrong-password", (USERNAME, "incorrect-password")),
                                       ("absent-auth", ())):
                with self.subTest(protocol=protocol, mutation=label):
                    origin = self.fixture.origin()
                    with self.running(self.imported(peer, credentials=credentials), protocol):
                        with socket.create_connection(("127.0.0.1", self.port), timeout=4) as stream:
                            stream.settimeout(4)
                            target = f"127.0.0.1:{origin.server_address[1]}"
                            stream.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
                            response = header(stream)
                            self.assertNotIn(b"200 Connection Established", response)
                            self.assertIn(b"502", response)
                        self.assertFalse(origin.requests)
                        status = self.command(op="status")["status"]
                        self.assertGreaterEqual(status["failed"], 1)
                        self.records.append({"case": self._testMethodName, "protocol": protocol,
                            "mutation": label, "rejected": True, "origin_requests": 0,
                            "last_error_stage": status.get("last_error_stage")})

    def test_invalid_udp_credentials_cannot_reach_the_dns_target(self):
        peer = self.peer("socks", auth=True)
        config = self.imported(peer, credentials=(USERNAME, "incorrect-password"))
        self.assertTrue(config["nodes"][0]["outbound"]["udp"])
        dns = self.udp_origin(udp=True, dns=True)
        with self.running(config, "socks5-udp"):
            association = self.associate()
            association[1].settimeout(0.5)
            with self.assertRaises(socket.timeout):
                self.udp_exchange(association, dns, b"blocked-before-dns")
            self.assertFalse(dns.received)
            status = self.command(op="status")["status"]
            self.assertGreaterEqual(status["udp_dropped"], 1)
            self.records.append({"case": self._testMethodName, "protocol": "socks5",
                "rejected": True, "dns_target_datagrams": 0, "udp_dropped": status["udp_dropped"]})

    def test_two_mib_binary_transfer_each_way_and_completed_application_close(self):
        size = 2 * 1024 * 1024
        for protocol in ("http", "socks"):
            with self.subTest(protocol=protocol):
                peer, origin = self.peer(protocol, auth=True), self.finite_echo_origin()
                with self.running(self.imported(peer), protocol):
                    started = time.monotonic()
                    digest = hashlib.sha256()
                    with self.tunnel(origin) as stream:
                        stream.sendall(size.to_bytes(8, "big"))
                        for offset in range(0, size, 16384):
                            payload = bytes((position * 31 + 17) % 251 for position in range(offset, min(offset + 16384, size)))
                            stream.sendall(payload)
                            reply = exact(stream, len(payload))
                            self.assertEqual(reply, payload)
                            digest.update(reply)
                        self.assertEqual(stream.recv(1), b"")
                        stream.shutdown(socket.SHUT_WR)
                    self.assertEqual(digest.hexdigest(), pattern_hash(size))
                    self.assertEqual(origin.received, size)
                    self.fixture.assert_origin_closed(origin)
                    self.fixture.assert_accepted(peer, origin)
                    self.records.append({"case": self._testMethodName, "protocol": protocol,
                        "uploaded": size, "downloaded": size, "native_import": True,
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                        "close": "application-complete", "official_accepted": True})

    def test_socks4_userid_ipv4_and_socks4a_remote_domain_through_official_server(self):
        peer = self.peer("socks", auth=False)
        for remote_dns in (False, True):
            for user_id in ("", "synthetic-user-id"):
                with self.subTest(remote_dns=remote_dns, user_id_present=bool(user_id)):
                    # This version selector is documented V2Ray v4 JSON, not
                    # a claim about the different Xray 26 client schema.
                    endpoint = {"address": peer["host"], "port": peer["port"]}
                    if user_id:
                        endpoint["users"] = [{"user": user_id}]
                    source = {"outbounds": [{"tag": "v2ray-socks4-import", "protocol": "socks",
                        "settings": {"version": "4a" if remote_dns else "4", "servers": [endpoint]},
                        "streamSettings": {"network": "tcp", "security": "none"}}]}
                    config = self.export(source)
                    self.assertEqual(config["nodes"][0]["outbound"], {
                        "type": "socks4", "host": peer["host"], "port": peer["port"],
                        "user_id": user_id, "remote_dns": remote_dns})
                    with self.running(config, "socks4a" if remote_dns else "socks4"):
                        for tls in (False, True):
                            origin = self.fixture.origin(tls=tls)
                            if remote_dns:
                                origin.target_host = "localhost"
                            self.application(peer, origin)
                        self.records.append({"case": self._testMethodName,
                            "protocol": "socks4a" if remote_dns else "socks4", "user_id_present": bool(user_id),
                            "authentication": "USERID identifier only; SOCKS4 has no password authentication",
                            "destination": "localhost" if remote_dns else "127.0.0.1",
                            "official_accepted": True, "native_import": True,
                            "source_format": "V2Ray v4 JSON (version available since v4.42.2)"})

    def test_existing_session_survives_node_switch_and_concurrent_new_connections(self):
        peers = [self.peer("http", auth=False), self.peer("http", auth=True),
                 self.peer("socks", auth=False), self.peer("socks", auth=True)]
        config = self.imported(peers[0])
        config["nodes"] = [{"id": f"n{index}", "outbound": self.imported(peer)["nodes"][0]["outbound"]}
                           for index, peer in enumerate(peers)]
        config["selected"] = "n0"
        echo = self.echo_origin()
        with self.running(config, "http-to-socks5-node-switch"):
            with self.tunnel(echo) as existing:
                existing.sendall(b"before-node-switch")
                self.assertEqual(exact(existing, 18), b"before-node-switch")
                for index, peer in enumerate(peers[1:], 1):
                    self.assertTrue(self.command(op="select_node", id=f"n{index}")["ok"])
                    self.application(peer, self.fixture.origin())
                    existing.sendall(b"after-node-switch")
                    self.assertEqual(exact(existing, 17), b"after-node-switch")
                origins = [self.fixture.origin(tls=index % 2 == 0) for index in range(4)]
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    list(executor.map(lambda origin: self.application(peers[-1], origin), origins))
            self.records.append({"case": self._testMethodName, "selected_nodes": len(peers),
                "old_connection_preserved": True, "parallel_connections": len(origins)})

    def test_ipv6_official_peer_and_reconnect_after_server_restart(self):
        for protocol in ("http", "socks"):
            with self.subTest(protocol=protocol):
                peer = self.peer(protocol, auth=True, host="::1")
                with self.running(self.imported(peer), protocol):
                    self.application(peer, self.fixture.origin())
                    self.fixture.terminate(peer)
                    peer["process"] = subprocess.Popen([str(self.xray), "run", "-config", str(peer["path"])],
                        stdout=peer["output"], stderr=subprocess.STDOUT)
                    self.ready(peer)
                    self.application(peer, self.fixture.origin(tls=True))
                    self.records.append({"case": self._testMethodName, "protocol": protocol,
                        "ipv6_proxy_endpoint": True, "fresh_connection_after_peer_restart": True})


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BasicProxyXrayTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if path := os.environ.get("SWIRL_BASIC_PROXY_EVIDENCE"):
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cls = BasicProxyXrayTests
        binaries = {}
        for label in ("harness", "inspector", "xray"):
            binary = getattr(cls, label, None)
            if binary is not None:
                binaries[label] = {"filename": binary.name, "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
        destination.write_text(json.dumps({"schema": 1, "platform": platform.platform(),
            "server": f"official Xray {XRAY[0]} {XRAY[1]}", "binaries": binaries,
            "client": "Swirl Rust Core", "qt_product_acceptance": False,
            "native_interoperability_passed": result.wasSuccessful() and not result.skipped,
            "tests_run": result.testsRun, "skipped": len(result.skipped),
            "failures": [test.id() for test, _ in result.failures],
            "errors": [test.id() for test, _ in result.errors],
            "records": cls.records, "peer_records": cls.peer_records}, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)


if __name__ == "__main__":
    main()
