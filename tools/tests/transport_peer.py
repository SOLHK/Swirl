"""Shared, bounded independent-Xray fixtures for native Rust transports.

No public endpoint or account is used. The Rust example is the proxy client;
the unmodified official Xray executable is only the independent test server.
Missing binaries and version mismatches are failures, never skipped tests.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time

from test_rust_core import certificates, exact, header


UUID = "00112233-4455-6677-8899-aabbccddeeff"
PASSWORD = "transport-synthetic-fixture-only"
HTTP_BODY = bytes(range(256)) * 513
XRAY = ("26.10.21", "1b1647c")
XRAY_LEGACY = ("1.8.24", "6baad79")


def pattern_hash(size):
    seed = bytes((i * 31 + 17) % 251 for i in range(251))
    digest = hashlib.sha256()
    while size:
        count = min(size, len(seed) * 64)
        digest.update((seed * 64)[:count])
        size -= count
    return digest.hexdigest()


class _Origin(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True

    def handle_error(self, request, address):
        self.errors.append("OriginHandlerFailed")


class _OriginHandler(socketserver.BaseRequestHandler):
    def handle(self):
        server = self.server
        stream = self.request
        wrapped = None
        stream.settimeout(6)
        with server.lock:
            server.active.add(stream)
        try:
            if server.context:
                stream = server.context.wrap_socket(stream, server_side=True)
                wrapped = stream
                with server.lock:
                    server.active.add(stream)
            with server.lock:
                server.requests.append(server.mode)
            if server.mode == "stall":
                server.stopped.wait(5)
                return
            if server.mode == "disconnect":
                # The authenticated proxy request reaches the destination, then
                # its application stream is deliberately truncated.
                stream.recv(16)
                return
            if server.mode == "echo":
                remaining = int.from_bytes(exact(stream, 8), "big")
                if not 0 <= remaining <= 64 * 1024 * 1024:
                    raise AssertionError("invalid bounded echo length")
                while remaining:
                    data = stream.recv(min(16384, remaining))
                    if not data:
                        return
                    with server.lock:
                        server.received += len(data)
                    stream.sendall(data)
                    remaining -= len(data)
                # Let the client half-close its upload, then return the final
                # EOF. Do not rely on a process kill to terminate the stream.
                if stream.recv(1) == b"":
                    with server.lock:
                        server.client_closes += 1
                return
            request = header(stream)
            if not request.startswith(b"GET /transport HTTP/1.1\r\n"):
                raise AssertionError("unexpected destination request")
            stream.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: "
                           + str(len(HTTP_BODY)).encode()
                           + b"\r\nConnection: close\r\n\r\n" + HTTP_BODY)
            if server.context:
                stream = stream.unwrap()
                with server.lock:
                    server.tls_closes += 1
            else:
                stream.shutdown(socket.SHUT_WR)
                if stream.recv(1) == b"":
                    with server.lock:
                        server.client_closes += 1
        except (ConnectionError, EOFError, TimeoutError, ssl.SSLError):
            # Cancellation and intentional interruption are tracked by the
            # test result and byte counters; they are not handler crashes.
            with server.lock:
                server.interruptions += 1
        finally:
            stream.close()
            with server.lock:
                server.active.discard(self.request)
                server.active.discard(stream)
                if wrapped is not None:
                    server.active.discard(wrapped)


class Fixture:
    """One isolated set of servers, certificates, target sockets and logs."""

    def __init__(self, stage="transport"):
        self.stage = stage
        self.temp = tempfile.TemporaryDirectory(prefix=f"swirl-{stage}-")
        self.folder = Path(self.temp.name)
        self.context, self.ca, self.ca_pem = certificates(self.temp.name)
        self.client = os.environ["SWIRL_TRANSPORT_CLIENT"]
        self.xray = os.environ["SWIRL_XRAY_BINARY"]
        self.legacy = os.environ.get("SWIRL_XRAY_LEGACY_BINARY")
        self.version = self._version(self.xray, XRAY)
        self.origins, self.peers, self.records = [], [], []
        self.serial = 0
        root = os.environ.get("SWIRL_TRANSPORT_EVIDENCE")
        self.evidence = Path(root) / self.folder.name if root else self.folder / "evidence"
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.records_lock = threading.Lock()

    @staticmethod
    def _version(binary, expected):
        result = subprocess.run([binary, "version"], capture_output=True, text=True,
                                check=True, timeout=10)
        if f"Xray {expected[0]}" not in result.stdout or expected[1] not in result.stdout:
            raise AssertionError(f"fixture requires pinned official Xray {expected}")
        return result.stdout.splitlines()[0]

    def origin(self, *, tls=False, mode="http", echo=False):
        if echo:
            mode = "echo"
        origin = _Origin(("127.0.0.1", 0), _OriginHandler)
        origin.context = self.context if tls else None
        origin.mode = mode
        origin.requests, origin.errors = [], []
        origin.active, origin.lock = set(), threading.Lock()
        origin.stopped = threading.Event()
        origin.received = origin.client_closes = origin.tls_closes = origin.interruptions = 0
        origin.target_host, origin.target_port = origin.server_address
        origin.worker = threading.Thread(target=origin.serve_forever,
                                         kwargs={"poll_interval": 0.02}, daemon=True)
        origin.worker.start()
        self.origins.append(origin)
        return origin

    def peer(self, network, *, protocol="vless", tls=False, legacy=False,
             host="transport.fixture.invalid", path="/native/nested",
             service_name="swirl", mode="stream-one", listen="127.0.0.1"):
        binary = self.legacy if legacy else self.xray
        if not binary:
            raise AssertionError("SWIRL_XRAY_LEGACY_BINARY is required")
        version = self._version(binary, XRAY_LEGACY) if legacy else self.version
        with socket.socket(socket.AF_INET6 if ":" in listen else socket.AF_INET) as reserve:
            reserve.bind((listen, 0))
            port = reserve.getsockname()[1]
        self.serial += 1
        label = f"{self.serial:02d}-{protocol}-{network}-{'tls' if tls else 'plain'}"
        access = self.evidence / f"{label}-access.log"
        error = self.evidence / f"{label}-error.log"
        output = (self.evidence / f"{label}-process.log").open("w", encoding="utf-8")
        stream = {"network": network, "security": "tls" if tls else "none"}
        alpn = "h2" if network in ("grpc", "h2", "http", "xhttp") else "http/1.1"
        if tls:
            stream["tlsSettings"] = {
                "alpn": [alpn],
                "certificates": [{"certificateFile": str(self.folder / "leaf.pem"),
                                  "keyFile": str(self.folder / "leaf.key")}],
            }
        transport = None
        if network == "grpc":
            stream["grpcSettings"] = {"serviceName": service_name}
            transport = {"type": "grpc", "config": {
                "authority": host, "service_name": service_name,
                "mode": "tun", "headers": []}}
        elif network in ("h2", "http"):
            stream["httpSettings"] = {"host": [host], "path": path}
            transport = {"type": "http2", "config": {"host": host, "path": path, "headers": []}}
        elif network == "httpupgrade":
            stream["httpupgradeSettings"] = {"host": host, "path": path}
            transport = {"type": "httpupgrade", "config": {
                "host": host, "path": path, "headers": [["X-Transport-Fixture", "custom"]]}}
        elif network == "xhttp":
            stream["xhttpSettings"] = {"host": host, "path": path, "mode": mode}
            transport = {"type": "xhttp", "config": {
                "host": host, "path": path, "mode": mode,
                "headers": [["X-Transport-Fixture", "custom"]]}}
        elif network == "ws":
            stream["wsSettings"] = {"host": host, "path": path}
            transport = {"type": "websocket", "settings": {"host": host, "path": path}, "headers": []}
        elif network in ("raw", "tcp"):
            transport = {"type": "tcp"}
        else:
            raise ValueError(f"unsupported fixture network {network}")
        settings = {"clients": [{"id": UUID}], "decryption": "none"}
        outbound = {"type": protocol, "host": listen, "port": port, "uuid": UUID}
        if tls:
            outbound["tls"] = self.tls_config(alpn)
        if protocol == "trojan":
            if not tls:
                raise ValueError("the current Rust Trojan IR requires TLS")
            settings = {"clients": [{"password": PASSWORD}]}
            outbound.pop("uuid")
            outbound["password"] = PASSWORD
        elif protocol != "vless":
            raise ValueError("fixture supports implemented VLESS/Trojan connectors only")
        freedom = {"protocol": "freedom"}
        if not legacy:
            # Current upstream deliberately protects private destinations by
            # default. Authorize only this suite's own loopback test services.
            freedom["settings"] = {"finalRules": [{"action": "allow", "network": "tcp",
                                                     "ip": ["127.0.0.0/8", "::1/128"]}]}
        config = {"log": {"access": str(access), "error": str(error), "loglevel": "debug"},
                  "inbounds": [{"listen": listen, "port": port, "protocol": protocol,
                                "settings": settings, "streamSettings": stream}],
                  "outbounds": [freedom]}
        config_path = self.folder / f"{label}.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        process = subprocess.Popen([binary, "run", "-config", str(config_path)],
                                   stdout=output, stderr=subprocess.STDOUT)
        peer = {"process": process, "output": output, "access": access, "error": error,
                "label": label, "port": port, "host": listen, "protocol": protocol,
                "network": network, "tls": tls, "version": version,
                "outbound": outbound, "transport": transport, "config": config}
        self.peers.append(peer)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(f"pinned server exited: {label}; {error.read_text() if error.exists() else ''}")
            try:
                with socket.create_connection((listen, port), timeout=0.1):
                    return peer
            except OSError:
                threading.Event().wait(0.02)
        raise AssertionError(f"pinned server startup timeout: {label}")

    def tls_config(self, alpn="http/1.1"):
        return {"server_name": "localhost", "alpn": [alpn], "ca_der_base64": self.ca}

    def request(self, peer, origin, *, mode="http", size=1024 * 1024, **overrides):
        request = {"outbound": copy.deepcopy(peer["outbound"]),
                   "transport": copy.deepcopy(peer["transport"]),
                   "target_host": origin.target_host, "target_port": origin.target_port,
                   "mode": mode, "path": "/transport", "size": size, "timeout_ms": 15000}
        if origin.context:
            request["target_tls"] = self.tls_config()
        request.update(overrides)
        return request

    def run(self, request, *, timeout=20):
        start = time.monotonic()
        result = subprocess.run([self.client], input=json.dumps(request),
                                capture_output=True, text=True, timeout=timeout)
        try:
            report = json.loads(result.stdout)
        except (ValueError, TypeError) as error:
            raise AssertionError(f"invalid client report: exit {result.returncode}; {result.stdout}; {result.stderr}") from error
        peer = next((peer for peer in self.peers
                     if peer["port"] == request["outbound"]["port"]), None)
        record = {"stage": self.stage, "platform": platform.system(),
                  "server": peer["version"] if peer else self.version,
                  "transport": request.get("transport", {}).get("type"),
                  "protocol": request["outbound"]["type"],
                  "tls": bool(request["outbound"].get("tls")),
                  "reality": bool(request["outbound"].get("reality")),
                  "target_tls": bool(request.get("target_tls")), "mode": request.get("mode"),
                  "exit_code": result.returncode, "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
                  "result": report}
        with self.records_lock:
            self.records.append(record)
        return result, report

    @staticmethod
    def assert_accepted(peer, origin):
        destination = f"{origin.target_host}:{origin.target_port}"
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if peer["access"].exists():
                data = peer["access"].read_text(encoding="utf-8")
                if "accepted" in data and destination in data:
                    return
            threading.Event().wait(0.02)
        raise AssertionError(f"no independent-server accepted request to {destination}")

    @staticmethod
    def assert_origin_closed(origin, count=1):
        """Require destination-side closure evidence, not just a client label."""
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with origin.lock:
                observed = origin.tls_closes if origin.context else origin.client_closes
                active = len(origin.active)
            if observed >= count and not active:
                return
            threading.Event().wait(0.01)
        raise AssertionError(f"destination closure not observed: {observed}/{count}; active={active}")

    @staticmethod
    def terminate(peer):
        process = peer["process"]
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    def close(self):
        errors = []
        for peer in self.peers:
            try:
                self.terminate(peer)
            except (OSError, subprocess.TimeoutExpired) as error:
                peer["process"].kill()
                peer["process"].wait(timeout=5)
                errors.append(str(error))
            peer["output"].close()
        for origin in self.origins:
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
            errors.extend(origin.errors)
        (self.evidence / "results.json").write_text(json.dumps({
            "command": [self.client], "server_version": self.version,
            "records": self.records, "cleanup_errors": errors,
            "origins": [{"mode": origin.mode, "tls": bool(origin.context),
                         "requests": len(origin.requests), "received": origin.received,
                         "client_closes": origin.client_closes,
                         "tls_closes": origin.tls_closes,
                         "interruptions": origin.interruptions,
                         "errors": origin.errors} for origin in self.origins],
        }, indent=2) + "\n", encoding="utf-8")
        self.temp.cleanup()
        if errors:
            raise AssertionError(f"fixture cleanup/handler errors: {errors}")
