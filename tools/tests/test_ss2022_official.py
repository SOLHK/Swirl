"""SIP022 interoperability with pinned, unmodified shadowsocks-rust ssserver.

Native Swirl Rust is the only proxy client. Python provides independent
TCP/HTTP(S)/DNS/UDP destinations and transparent attack relays, never a
replacement Shadowsocks server. Missing executables fail, never skip.
"""
import base64
import concurrent.futures
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import select
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import quote

from test_rust_core import certificates, exact, target
from transport_peer import _Origin, _OriginHandler, HTTP_BODY, pattern_hash


CIPHERS = ("2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm")


def _exclusive_address(sock):
    # Winsock otherwise permits another SO_REUSEADDR socket to share an
    # occupied port. Set this before bind for both reservations and conflicts.
    option = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
    if option is not None:
        sock.setsockopt(socket.SOL_SOCKET, option, 1)


def _unused_tcp_udp_port(listen):
    """Check both transports; a later bind race is handled only at startup."""
    family = socket.AF_INET6 if ":" in listen else socket.AF_INET
    for _ in range(32):
        with socket.socket(family, socket.SOCK_STREAM) as tcp, socket.socket(family, socket.SOCK_DGRAM) as udp:
            _exclusive_address(tcp)
            _exclusive_address(udp)
            tcp.bind((listen, 0))
            port = tcp.getsockname()[1]
            try:
                udp.bind((listen, port))
            except OSError as error:
                if error.errno in (errno.EADDRINUSE, 10048):
                    continue
                raise
            return port
    raise RuntimeError("No unused TCP/UDP peer port found")


def _startup_log(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        value = handle.read(65537)
    if len(value) > 65536:
        raise AssertionError("official ssserver startup log exceeded its bound")
    return value


def _startup_bind_conflict(exit_code, log):
    # The pinned ssserver reports fatal bind failures with EX_SOFTWARE (70).
    # These are EADDRINUSE on Darwin/Linux/Windows, not protocol/auth failures.
    return exit_code == 70 and re.search(
        r"(?m)^server aborted with [^\r\n]*\(os error (?:48|98|10048)\)\s*$", log) is not None


class _UdpOrigin(socketserver.ThreadingUDPServer):
    allow_reuse_address = False
    daemon_threads = True

    def handle_error(self, request, address):
        self.errors.append("UdpOriginHandlerFailed")


class _UdpHandler(socketserver.BaseRequestHandler):
    def handle(self):
        packet, stream = self.request
        server = self.server
        with server.lock:
            server.packets.append(packet)
        if server.dns:
            if packet[12:] != b"\x06native\x05swirl\x04test\0\0\x01\0\x01":
                raise AssertionError("unexpected bounded DNS question")
            response = packet[:2] + b"\x81\x80\0\x01\0\x01\0\0\0\0" + packet[12:]
            response += b"\xc0\x0c\0\x01\0\x01\0\0\0\x3c\0\x04\xc0\0\x02\x07"
        else:
            response = packet
        stream.sendto(response, self.client_address)


class _UdpAttackRelay:
    """Replay/tamper captured ciphertext without implementing any proxy codec."""
    def __init__(self, upstream):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.address = self.socket.getsockname()
        self.upstream = upstream
        self.client = None
        self.requests = self.responses = 0
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def run(self):
        while not self.stop.is_set():
            ready, _, _ = select.select([self.socket], [], [], 0.02)
            if not ready:
                continue
            packet, source = self.socket.recvfrom(65535)
            if source == self.upstream:
                self.responses += 1
                damaged = bytearray(packet)
                damaged[-1] ^= 1
                for payload in (damaged, packet, packet):
                    self.socket.sendto(payload, self.client)
            else:
                self.client = source
                self.requests += 1
                damaged = bytearray(packet)
                damaged[-1] ^= 1
                for payload in (damaged, packet, packet):
                    self.socket.sendto(payload, self.upstream)

    def close(self):
        self.stop.set()
        self.worker.join(timeout=2)
        self.socket.close()


class _TcpCapture(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True


class _TcpCaptureHandler(socketserver.BaseRequestHandler):
    def handle(self):
        client = self.request
        upstream = socket.create_connection(self.server.upstream, timeout=3)
        client.settimeout(3)
        sent_replay = False
        readers = [client, upstream]
        try:
            while readers:
                ready, _, _ = select.select(readers, [], [], 3)
                if not ready:
                    return
                for source in ready:
                    data = source.recv(65536)
                    destination = upstream if source is client else client
                    if not data:
                        readers.remove(source)
                        destination.shutdown(socket.SHUT_WR)
                        continue
                    if source is client:
                        with self.server.lock:
                            if len(self.server.request_bytes) + len(data) > 131072:
                                raise AssertionError("bounded capture exceeded")
                            self.server.request_bytes.extend(data)
                        destination.sendall(data)
                    elif self.server.replay_response is not None:
                        if not sent_replay:
                            destination.sendall(self.server.replay_response)
                            destination.shutdown(socket.SHUT_WR)
                            sent_replay = True
                    else:
                        with self.server.lock:
                            if len(self.server.response_bytes) + len(data) > 262144:
                                raise AssertionError("bounded capture exceeded")
                            self.server.response_bytes.extend(data)
                        destination.sendall(data)
        except (ConnectionError, OSError):
            # Intentional ciphertext substitution makes Swirl reject and close.
            pass
        finally:
            upstream.close()


class Ss2022OfficialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="swirl-ss2022-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.evidence = Path(os.environ.get("SWIRL_SS2022_EVIDENCE", self.temp.name)) / self.folder.name
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.server = os.environ["SWIRL_SS2022_SERVER"]
        self.client = os.environ["SWIRL_TRANSPORT_CLIENT"]
        self.udp_client = os.environ["SWIRL_SS2022_CLIENT"]
        version = subprocess.run([self.server, "--version"], text=True, capture_output=True,
                                 timeout=5, check=True).stdout.strip()
        self.assertEqual(version, "shadowsocks 1.25.0")
        self.context, self.ca, _ = certificates(self.temp.name)
        self.origins, self.peers, self.records, self.relays = [], [], [], []
        self.addCleanup(self.finish)

    def peer(self, cipher, *, listen="127.0.0.1", port=None):
        key = base64.b64encode(bytes([73]) * (16 if cipher == CIPHERS[0] else 32)).decode()
        # ssserver cannot inherit our reservations, so another process may bind
        # between the check and spawn. Re-select only before traffic, only for an
        # observed bind conflict, and never for the fixed-port restart tests.
        attempts = 4 if port is None else 1
        for attempt in range(attempts):
            selected_port = _unused_tcp_udp_port(listen) if port is None else port
            config = {"server": listen, "server_port": selected_port, "password": key, "method": cipher,
                      "mode": "tcp_and_udp", "timeout": 3, "udp_timeout": 60,
                      "udp_max_associations": 32, "no_delay": True}
            label = f"{len(self.peers):02d}-{cipher}"
            path = self.folder / f"{label}.json"
            path.write_text(json.dumps(config))
            log_path = self.evidence / f"{label}-server.log"
            log = log_path.open("w")
            command = [self.server, "--config", str(path), "--single-threaded", "-v"]
            # Readiness requires the child's own TCP and UDP bind receipts.
            # Host RUST_LOG=warn/off overrides -v in the pinned peer and hides
            # both receipts. Scope deterministic logging to this synthetic
            # server; leave the user's environment and every assertion intact.
            peer_env = dict(os.environ, RUST_LOG="info", NO_COLOR="1")
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=peer_env)
            startup = {"attempt": attempt + 1, "fixed_port": port is not None, "port": selected_port,
                       "log": log_path.name, "reason": "pending", "exit_code": None}
            peer = {"process": process, "log": log, "command": command, "host": listen, "port": selected_port,
                    "startup": startup,
                    "outbound": {"type": "shadowsocks", "host": listen, "port": selected_port,
                                 "password": key, "cipher": cipher, "udp": True}}
            self.peers.append(peer)
            endpoint = f"[{listen}]:{selected_port}" if ":" in listen else f"{listen}:{selected_port}"
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                exited = process.poll()
                observed = _startup_log(log_path)
                if exited is not None:
                    collision = _startup_bind_conflict(exited, observed)
                    startup.update(exit_code=exited, reason="AddressInUse" if collision else "StartupExit")
                    if collision and port is None and attempt + 1 < attempts:
                        break
                    self.fail(f"official ssserver startup {startup['reason']} (exit {exited}); see {log_path.name}")
                # A connection to an unrelated listener is not evidence that
                # our child owns both endpoints. Confirm the pinned server's
                # actual TCP and UDP bind messages before the TCP readiness probe.
                if all(f"shadowsocks {protocol} server listening on {endpoint}," in observed
                       for protocol in ("tcp", "udp")):
                    try:
                        with socket.create_connection((listen, selected_port), timeout=0.1):
                            self.assertIsNone(process.poll(), "official ssserver exited after binding")
                            startup["reason"] = "ready"
                            return peer
                    except OSError:
                        pass
                threading.Event().wait(0.02)
            else:
                startup["reason"] = "StartupTimeout"
                self.fail(f"official ssserver startup timed out; see {log_path.name}")
        self.fail("official ssserver exhausted its bounded bind attempts")

    def test_peer_owned_bind_receipts_survive_disabled_ambient_logging(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {"RUST_LOG": "off"}):
            peer = self.peer("2022-blake3-aes-128-gcm")
            self.assertEqual(os.environ["RUST_LOG"], "off")
            self.assertEqual(peer["startup"]["reason"], "ready")

    def test_random_startup_port_conflict_reselects_before_protocol_traffic(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            _exclusive_address(occupied)
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            blocked = occupied.getsockname()[1]
            original = _unused_tcp_udp_port
            calls = []
            def allocate(listen):
                calls.append(listen)
                return blocked if len(calls) == 1 else original(listen)
            # Force the real check/spawn race. Both server processes are the
            # actual pinned binary, and the successful attempt carries traffic.
            with patch(__name__ + "._unused_tcp_udp_port", side_effect=allocate):
                peer = self.peer(CIPHERS[0])
            self.assertEqual(len(calls), 2)
            self.assertEqual(self.peers[-2]["startup"]["reason"], "AddressInUse")
            self.assertEqual(self.peers[-2]["process"].returncode, 70)
            self.assertNotEqual(peer["port"], blocked)
            origin = self.origin()
            self.run_client(self.request(peer, origin))
            self.assert_closed(origin)

    def test_fixed_port_conflict_and_non_bind_startup_failures_are_not_retried(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as occupied:
            _exclusive_address(occupied)
            occupied.bind(("127.0.0.1", 0))
            blocked = occupied.getsockname()[1]
            with self.assertRaisesRegex(AssertionError, "AddressInUse"):
                self.peer(CIPHERS[0], port=blocked)
            self.assertEqual(len(self.peers), 1)
            self.assertEqual(self.peers[0]["port"], blocked)
        with self.assertRaisesRegex(AssertionError, "StartupExit"):
            self.peer("invalid-synthetic-cipher")
        self.assertEqual(len(self.peers), 2, "unrelated startup failures must not be retried")

    def origin(self, *, echo=False, tls=False, ipv6=False):
        server_type = type("Ipv6Origin", (_Origin,), {"address_family": socket.AF_INET6}) if ipv6 else _Origin
        origin = server_type(("::1" if ipv6 else "127.0.0.1", 0), _OriginHandler)
        origin.context, origin.mode = self.context if tls else None, "echo" if echo else "http"
        origin.requests, origin.errors, origin.active = [], [], set()
        origin.lock, origin.stopped = threading.Lock(), threading.Event()
        origin.received = origin.client_closes = origin.tls_closes = origin.interruptions = 0
        origin.target_host, origin.target_port = origin.server_address[:2]
        origin.worker = threading.Thread(target=origin.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        origin.worker.start()
        self.origins.append(origin)
        return origin

    def udp_origin(self, *, dns=False, ipv6=False):
        server_type = type("Ipv6UdpOrigin", (_UdpOrigin,), {"address_family": socket.AF_INET6}) if ipv6 else _UdpOrigin
        origin = server_type(("::1" if ipv6 else "127.0.0.1", 0), _UdpHandler)
        origin.dns, origin.packets, origin.errors, origin.lock = dns, [], [], threading.Lock()
        origin.target_host, origin.target_port = origin.server_address[:2]
        origin.worker = threading.Thread(target=origin.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        origin.worker.start()
        self.origins.append(origin)
        return origin

    def request(self, peer, origin, **options):
        request = {"outbound": copy.deepcopy(peer["outbound"]),
                   "target_host": origin.target_host, "target_port": origin.target_port,
                   "timeout_ms": 5000}
        request.update(options)
        return request

    def run_client(self, request, *, udp=False, expected=True):
        result = subprocess.run([self.udp_client if udp else self.client], input=json.dumps(request),
                                text=True, capture_output=True, timeout=20)
        report = json.loads(result.stdout)
        self.records.append({"client": "ss2022-client" if udp else "transport-client",
            "cipher": request.get("outbound", {}).get("cipher"), "mode": request.get("mode", "http"),
            "imported": "source_document" in request, "exit_code": result.returncode, "result": report})
        self.assertEqual(result.returncode, 0 if expected else 1, (report, result.stderr))
        self.assertEqual(report["ok"], expected, report)
        if expected and not udp:
            self.assertEqual(report["close"], "clean", report)
            self.assertEqual(report["remaining_tasks"], 0, report)
        return report

    def assert_closed(self, origin, count=1):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            closes = origin.tls_closes if origin.context else origin.client_closes
            if closes >= count and not origin.active:
                return
            threading.Event().wait(0.01)
        self.fail(f"origin closure {closes}/{count}, active={len(origin.active)}")

    @staticmethod
    def terminate(peer):
        if peer["process"].poll() is None:
            peer["process"].terminate()
            peer["process"].wait(timeout=5)

    def test_aes128_aes256_tcp_http_https_four_mib_duplex_and_half_close(self):
        for cipher in CIPHERS:
            peer = self.peer(cipher)
            for tls in (False, True):
                with self.subTest(cipher=cipher, tls=tls):
                    origin = self.origin(tls=tls)
                    request = self.request(peer, origin)
                    if tls:
                        request["target_tls"] = {"server_name": "localhost", "ca_der_base64": self.ca, "alpn": ["http/1.1"]}
                    report = self.run_client(request)
                    self.assertEqual(report["sha256"], hashlib.sha256(HTTP_BODY).hexdigest())
                    self.assertEqual(report["downloaded"], len(HTTP_BODY))
                    self.assert_closed(origin)
            origin = self.origin(echo=True)
            size = 4 * 1024 * 1024 + 17
            report = self.run_client(self.request(peer, origin, mode="echo", size=size))
            self.assertEqual(report["sha256"], pattern_hash(size))
            self.assertEqual(origin.received, size)
            self.assert_closed(origin)

    def test_wrong_valid_key_and_invalid_parameters_rejected(self):
        for cipher in CIPHERS:
            peer, origin = self.peer(cipher), self.origin()
            wrong = self.request(peer, origin, timeout_ms=700)
            wrong["outbound"]["password"] = base64.b64encode(bytes([81]) * (16 if cipher == CIPHERS[0] else 32)).decode()
            self.run_client(wrong, expected=False)
            for field, value in [("password", "password"), ("password", "AA==:AA=="),
                                 ("cipher", "2022-blake3-chacha20-poly1305")]:
                invalid = self.request(peer, origin)
                invalid["outbound"][field] = value
                report = self.run_client(invalid, expected=False)
                self.assertIn(report["error"], ("Ss2022Key", "Ss2022IdentityChainUnsupported", "Ss2022CipherUnsupported"))
            self.assertEqual(origin.requests, [])

    def test_udp_dns_ipv4_ipv6_and_multiple_datagrams(self):
        for cipher in CIPHERS:
            peer = self.peer(cipher)
            for ipv6 in (False, True):
                with self.subTest(cipher=cipher, ipv6=ipv6):
                    origin = self.udp_origin(ipv6=ipv6)
                    report = self.run_client(self.request(peer, origin, rounds=5, size=1200), udp=True)
                    self.assertEqual(report["uploaded"], 6000)
                    self.assertEqual(report["downloaded"], 6000)
                    self.assertEqual(len(origin.packets), 5)
            origin = self.udp_origin(dns=True)
            query = b"\x31\x42\x01\0\0\x01\0\0\0\0\0\0\x06native\x05swirl\x04test\0\0\x01\0\x01"
            report = self.run_client(self.request(peer, origin, mode="dns", payload_hex=query.hex()), udp=True)
            self.assertGreater(report["downloaded"], len(query))
            self.assertEqual(origin.packets, [query])

    def test_udp_real_wire_tamper_and_replay_in_both_directions(self):
        for cipher in CIPHERS:
            peer, origin = self.peer(cipher), self.udp_origin()
            relay = _UdpAttackRelay((peer["host"], peer["port"]))
            self.relays.append(relay)
            request = self.request(peer, origin, mode="udp-replay", size=900)
            request["outbound"].update(host=relay.address[0], port=relay.address[1])
            report = self.run_client(request, udp=True)
            self.assertTrue(report["duplicate_responses_rejected"])
            self.assertEqual(len(origin.packets), 1, "official server must reject replayed client ciphertext")
            self.assertEqual(relay.requests, 1)
            self.assertEqual(relay.responses, 1)

    def test_udp_wrong_key_does_not_reach_destination(self):
        for cipher in CIPHERS:
            peer, origin = self.peer(cipher), self.udp_origin()
            request = self.request(peer, origin, timeout_ms=500)
            request["outbound"]["password"] = base64.b64encode(bytes([81]) * (16 if cipher == CIPHERS[0] else 32)).decode()
            report = self.run_client(request, udp=True, expected=False)
            self.assertEqual(report["error"], "OperationTimeout")
            self.assertEqual(origin.packets, [])

    def test_ipv6_proxy_endpoint_and_domain_tcp_destination(self):
        peer, origin = self.peer(CIPHERS[0], listen="::1"), self.origin()
        self.run_client(self.request(peer, origin, target_host="localhost"))
        self.assertEqual(origin.requests, ["http"])
        self.assert_closed(origin)

    def test_six_concurrent_sessions_and_reconnect(self):
        peer, origin = self.peer(CIPHERS[1]), self.origin(echo=True)
        size = 256 * 1024 + 17
        requests = [self.request(peer, origin, mode="echo", size=size) for _ in range(6)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            reports = list(pool.map(self.run_client, requests))
        self.assertTrue(all(report["sha256"] == pattern_hash(size) for report in reports))
        self.assertEqual(origin.received, 6 * size)
        self.assert_closed(origin, count=6)
        self.terminate(peer)
        fresh = self.peer(CIPHERS[1], port=peer["port"])
        target_origin = self.origin()
        self.run_client(self.request(fresh, target_origin))
        self.assert_closed(target_origin)

    def test_clash_and_ss_uri_import_to_real_tcp_and_udp(self):
        inspector = os.environ["SWIRL_INSPECT_BINARY"]
        for cipher in CIPHERS:
            peer = self.peer(cipher)
            node = peer["outbound"]
            clash = json.dumps({"proxies": [{"name": "synthetic-ss2022", "type": "ss",
                "server": node["host"], "port": node["port"], "cipher": cipher,
                "password": node["password"], "udp": True}]})
            # SIP002 forbids base64-encoding AEAD-2022's entire userinfo.
            # The base64 PSK itself is percent encoded, including '+' and '='.
            uri = f"ss://{cipher}:{quote(node['password'], safe='')}@{node['host']}:{node['port']}#synthetic-ss2022"
            for source in (clash, uri):
                exported = subprocess.run([inspector, "--private-json"], input=source, text=True,
                    capture_output=True, timeout=5, check=True)
                inspection = json.loads(exported.stdout)
                native = inspection["tcpCandidates"]
                self.assertEqual(len(native), 1)
                self.assertIsNotNone(native[0], inspection["report"])
                origin = self.origin()
                request = self.request(peer, origin)
                request["outbound"] = native[0]
                self.run_client(request)
                self.assert_closed(origin)
            origin = self.udp_origin()
            request = self.request(peer, origin)
            request.pop("outbound")
            request["source_document"] = clash
            report = self.run_client(request, udp=True)
            self.assertTrue(report["imported"])
            self.assertEqual(len(origin.packets), 1)

    def test_udp_same_client_session_survives_official_server_restart(self):
        peer, origin = self.peer(CIPHERS[1]), self.udp_origin()
        request = self.request(peer, origin, mode="udp-reconnect", rounds=2, size=900, timeout_ms=6000)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.run_client, request, udp=True)
            deadline = time.monotonic() + 2
            while not origin.packets and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertEqual(len(origin.packets), 1)
            # Allow the first response to traverse the loopback socket before
            # stopping the official server during the client's inter-round gap.
            threading.Event().wait(0.1)
            self.terminate(peer)
            self.peer(CIPHERS[1], port=peer["port"])
            report = pending.result(timeout=7)
        self.assertEqual(report["rounds"], 2)
        self.assertEqual(report["downloaded"], 1800)
        self.assertEqual(len(origin.packets), 2)

    def test_captured_tcp_request_replay_and_response_binding(self):
        peer, origin = self.peer(CIPHERS[0]), self.origin()
        relay = _TcpCapture(("127.0.0.1", 0), _TcpCaptureHandler)
        relay.upstream = (peer["host"], peer["port"])
        relay.lock = threading.Lock()
        relay.request_bytes, relay.response_bytes = bytearray(), bytearray()
        relay.replay_response = None
        worker = threading.Thread(target=relay.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        worker.start()
        self.addCleanup(relay.server_close)
        self.addCleanup(relay.shutdown)
        request = self.request(peer, origin)
        request["outbound"].update(host=relay.server_address[0], port=relay.server_address[1])
        self.run_client(request)
        self.assert_closed(origin)
        captured_request = bytes(relay.request_bytes)
        captured_response = bytes(relay.response_bytes)
        self.assertGreater(len(captured_request), 59)
        self.assertGreater(len(captured_response), len(HTTP_BODY))
        with socket.create_connection(relay.upstream, timeout=3) as attacker:
            attacker.sendall(captured_request)
            attacker.shutdown(socket.SHUT_WR)
            try:
                received = attacker.recv(1)
                self.assertEqual(received, b"")
            except ConnectionResetError:
                pass
        self.assertEqual(origin.requests, ["http"], "replayed request must not create a second target connection")
        relay.replay_response = captured_response
        fresh_origin = self.origin()
        request = self.request(peer, fresh_origin)
        request["outbound"].update(host=relay.server_address[0], port=relay.server_address[1])
        self.run_client(request, expected=False)
        self.assertEqual(fresh_origin.requests, ["http"], "negative response test must still reach the official server")

    def test_core_socks5_udp_uses_native_ss2022_connector(self):
        peer, origin = self.peer(CIPHERS[0]), self.udp_origin()
        self.core_udp_exchange(peer, origin)

    def test_existing_three_aead_ciphers_remain_official_tcp_udp_interoperable(self):
        for cipher in ("aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305"):
            with self.subTest(cipher=cipher):
                peer, origin = self.peer(cipher), self.origin()
                report = self.run_client(self.request(peer, origin))
                self.assertEqual(report["downloaded"], len(HTTP_BODY))
                self.assertEqual(report["sha256"], hashlib.sha256(HTTP_BODY).hexdigest())
                self.assert_closed(origin)
                self.core_udp_exchange(peer, self.udp_origin())

    def core_udp_exchange(self, peer, origin):
        runtime = subprocess.Popen([os.environ["SWIRL_TRANSPORT_RUNTIME"]],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            runtime.stdin.close()
            try:
                runtime.wait(timeout=5)
            except subprocess.TimeoutExpired:
                runtime.kill()
                runtime.wait(timeout=5)
            runtime.stdout.close()
            runtime.stderr.close()
        self.addCleanup(cleanup)
        def command(**message):
            runtime.stdin.write(json.dumps(message) + "\n")
            runtime.stdin.flush()
            result = json.loads(runtime.stdout.readline())
            self.assertTrue(result["ok"], result)
            return result
        config = {"schema": 1, "listen": "127.0.0.1:0", "selected": "a",
                  "nodes": [{"id": "a", "outbound": peer["outbound"]}]}
        started = command(op="start", config=config)
        port = int(started["status"]["address"].rsplit(":", 1)[1])
        with socket.create_connection(("127.0.0.1", port), timeout=5) as control:
            control.sendall(b"\x05\x01\x00")
            self.assertEqual(exact(control, 2), b"\x05\x00")
            control.sendall(b"\x05\x03\x00\x01" + bytes(6))
            self.assertEqual(exact(control, 3), b"\x05\x00\x00")
            relay_address = target(control)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(3)
                payload = b"core-native-ss2022-real-udp"
                address = b"\x01" + socket.inet_aton(origin.target_host) + origin.target_port.to_bytes(2, "big")
                client.sendto(bytes(3) + address + payload, relay_address)
                returned, _ = client.recvfrom(65535)
                self.assertEqual(returned, bytes(3) + address + payload)
        command(op="stop")
        self.assertEqual(origin.packets, [payload])

    def finish(self):
        for relay in self.relays:
            relay.close()
        for peer in self.peers:
            self.terminate(peer)
            peer["log"].close()
        origins = []
        for origin in self.origins:
            if hasattr(origin, "stopped"):
                origin.stopped.set()
                with origin.lock:
                    active = list(origin.active)
                for stream in active:
                    try:
                        stream.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
            origin.shutdown()
            origin.server_close()
            origin.worker.join(timeout=2)
            origins.append({"type": "udp" if hasattr(origin, "packets") else origin.mode,
                "requests": len(origin.packets) if hasattr(origin, "packets") else len(origin.requests),
                "received": getattr(origin, "received", None),
                "client_closes": getattr(origin, "client_closes", None),
                "tls_closes": getattr(origin, "tls_closes", None), "errors": origin.errors})
            self.assertEqual(origin.errors, [])
        (self.evidence / "results.json").write_text(json.dumps({
            "official_server": "shadowsocks-rust v1.25.0", "server_only": True,
            "server_sha256": hashlib.sha256(Path(self.server).read_bytes()).hexdigest(),
            "commands": [peer["command"] for peer in self.peers],
            "startups": [peer["startup"] for peer in self.peers],
            "records": self.records, "origins": origins,
        }, indent=2) + "\n")


if __name__ == "__main__":
    started = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Ss2022OfficialTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if folder := os.environ.get("SWIRL_SS2022_EVIDENCE"):
        Path(folder).mkdir(parents=True, exist_ok=True)
        (Path(folder) / "summary.json").write_text(json.dumps({
            "evidence_level": "official_server_independent_loopback", "public_network_tested": False,
            "qt_product_tested": False, "platform": platform.platform(), "official_server": "shadowsocks-rust v1.25.0",
            "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped), "elapsed_seconds": round(time.monotonic() - started, 3),
            "exit_code": 0 if result.wasSuccessful() else 1,
        }, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
