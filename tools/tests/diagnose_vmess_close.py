"""Compare native and official VMess clients against the same pinned Xray.

This is a diagnostic, not a replacement for VmessXrayHalfCloseTests. Its exit
code stays nonzero when either client fails strict target half-close. All
addresses, credentials and certificates are isolated synthetic fixtures.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import socketserver
import subprocess
import threading
import time

from test_rust_core import exact
from test_r1_public_proxy import BoundedControl
from transport_peer import Fixture, UUID, _Origin, pattern_hash


class ReceiptHandler(socketserver.BaseRequestHandler):
    def handle(self):
        origin, stream = self.server, self.request
        stream.settimeout(6)
        receipt = {"received": 0, "upload_eof": False, "response_finished": False,
                   "failure": None}
        with origin.lock:
            origin.active.add(stream)
            origin.requests.append("echo")
            origin.receipts.append(receipt)
        try:
            count = int.from_bytes(exact(stream, 8), "big")
            if not 0 <= count <= 64 * 1024 * 1024:
                raise ValueError("bounded echo length")
            digest = hashlib.sha256()
            while receipt["received"] < count:
                data = stream.recv(min(16384, count - receipt["received"]))
                if not data:
                    raise EOFError("upload truncated")
                digest.update(data)
                stream.sendall(data)
                with origin.lock:
                    receipt["received"] += len(data)
                    origin.received += len(data)
            with origin.lock:
                receipt["sha256"] = digest.hexdigest()
                receipt["all_bytes_at"] = time.monotonic()
            tail = stream.recv(1)
            with origin.lock:
                receipt["upload_eof"] = tail == b""
                receipt["upload_eof_at"] = time.monotonic() if tail == b"" else None
                if tail == b"":
                    origin.client_closes += 1
            if tail:
                raise ValueError("unexpected trailing upload")
            # A cancellation can close the target socket without delivering
            # its response. Only this post-EOF digest proves half-close worked.
            stream.sendall(digest.digest())
            stream.shutdown(socket.SHUT_WR)
            with origin.lock:
                receipt["response_finished"] = True
        except (OSError, EOFError, ValueError) as error:
            with origin.lock:
                receipt["failure"] = type(error).__name__
                origin.interruptions += 1
        finally:
            stream.close()
            with origin.lock:
                origin.active.discard(stream)
                receipt["finished_at"] = time.monotonic()
            origin.completed.set()


def receipt_origin(fixture):
    origin = _Origin(("127.0.0.1", 0), ReceiptHandler)
    origin.context, origin.mode = None, "echo"
    origin.requests, origin.errors, origin.receipts = [], [], []
    origin.active, origin.lock = set(), threading.Lock()
    origin.stopped, origin.completed = threading.Event(), threading.Event()
    origin.received = origin.client_closes = origin.tls_closes = origin.interruptions = 0
    origin.target_host, origin.target_port = origin.server_address
    origin.worker = threading.Thread(target=origin.serve_forever,
        kwargs={"poll_interval": 0.02}, daemon=True)
    origin.worker.start()
    fixture.origins.append(origin)
    return origin


def official_client(fixture, peer):
    """Run the exact same official binary in a separate control-client role."""
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    label = peer["label"] + "-official-client"
    stream = copy.deepcopy(peer["config"]["inbounds"][0]["streamSettings"])
    if peer["tls"]:
        stream["tlsSettings"] = {
            "serverName": "localhost", "alpn": ["http/1.1"],
            "disableSystemRoot": True,
            "certificates": [{"usage": "verify", "certificate": fixture.ca_pem.splitlines()}],
        }
    config = {
        "log": {"loglevel": "debug"},
        "inbounds": [{"listen": "127.0.0.1", "port": port, "protocol": "socks",
                      "settings": {"auth": "noauth", "udp": False}}],
        "outbounds": [{"protocol": "vmess", "settings": {"vnext": [
            {"address": peer["host"], "port": peer["port"],
             "users": [{"id": UUID, "alterId": 0, "security": "aes-128-gcm"}]}]},
            "streamSettings": stream}],
    }
    path = fixture.folder / (label + ".json")
    path.write_text(json.dumps(config), encoding="utf-8")
    log = (fixture.evidence / (label + ".log")).open("w", encoding="utf-8")
    process = subprocess.Popen([fixture.xray, "run", "-config", str(path)],
                               stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("official client exited before ready")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return process, log, port
            except OSError:
                threading.Event().wait(0.02)
        raise AssertionError("official client startup timeout")
    except BaseException:
        process.terminate()
        process.wait(timeout=5)
        log.close()
        raise


def socket_echo(origin, size, port=None):
    stream = socket.create_connection(("127.0.0.1", port or origin.target_port), timeout=5)
    result = {"uploaded": 0, "downloaded": 0, "close": None, "failure": None,
              "post_eof_receipt_verified": False}
    try:
        if port:
            stream.sendall(b"\x05\x01\x00")
            if exact(stream, 2) != b"\x05\x00":
                raise AssertionError("official SOCKS authentication response")
            stream.sendall(b"\x05\x01\x00\x01" + socket.inet_aton(origin.target_host)
                           + origin.target_port.to_bytes(2, "big"))
            response = exact(stream, 4)
            if response[:2] != b"\x05\x00":
                raise AssertionError("official SOCKS connect response")
            if response[3] == 1:
                exact(stream, 6)
            elif response[3] == 4:
                exact(stream, 18)
            else:
                raise AssertionError("official SOCKS response address type")
        stream.sendall(size.to_bytes(8, "big"))
        seed = bytes((i * 31 + 17) % 251 for i in range(251))

        def upload():
            sent = 0
            while sent < size:
                count = min(16384, size - sent)
                part = (seed * 67)[sent % 251:sent % 251 + count]
                stream.sendall(part)
                sent += count
            return sent

        digest = hashlib.sha256()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            sending = pool.submit(upload)
            while result["downloaded"] < size:
                data = stream.recv(min(16384, size - result["downloaded"]))
                if not data:
                    raise EOFError("echo response truncated")
                digest.update(data)
                result["downloaded"] += len(data)
            result["uploaded"] = sending.result(timeout=5) + 8
        result["sha256"] = digest.hexdigest()
        stream.shutdown(socket.SHUT_WR)
        result["upload_shutdown_at"] = time.monotonic()
        # Match transport-client's existing strict close deadline exactly.
        stream.settimeout(2)
        result["post_eof_receipt_verified"] = exact(stream, 32) == digest.digest()
        result["close"] = "clean" if stream.recv(1) == b"" else "trailing_data"
    except (OSError, EOFError, AssertionError) as error:
        result["failure"] = type(error).__name__
        result["close"] = result["close"] or "failed"
    finally:
        result["client_completed_at"] = time.monotonic()
        with origin.lock:
            # Freeze before local socket cleanup can manufacture an EOF.
            result["target_receipts_before_client_cleanup"] = copy.deepcopy(origin.receipts)
        stream.close()
    return result


def strict_result(result, size):
    result["bytes_match"] = (result.get("downloaded") == size
                              and result.get("sha256") == pattern_hash(size))
    receipts = result["target_receipts_before_client_cleanup"]
    result["strict_target_half_close"] = bool(result["bytes_match"]
        and result["post_eof_receipt_verified"] and result.get("close") == "clean"
        and len(receipts) == 1 and receipts[0]["upload_eof"]
        and receipts[0]["received"] == size and receipts[0].get("sha256") == pattern_hash(size)
        and receipts[0]["failure"] is None)
    return result


def run(output, size):
    fixture = Fixture("S4-vmess-close-control")
    results = []
    repository = Path(__file__).resolve().parents[2]
    report = {"schema": 1, "scope": "diagnostic-only-independent-loopback",
              "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "source_base_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository,
                  check=True, capture_output=True, text=True, timeout=5).stdout.strip(),
              "source_sha256": {name: hashlib.sha256((repository / name).read_bytes()).hexdigest()
                  for name in ("core/crates/swirl-protocol/src/vmess.rs",
                               "core/crates/swirl-core/src/lib.rs",
                               "tools/tests/test_vmess_xray.py",
                               "tools/tests/diagnose_vmess_close.py")},
              "platform": platform.platform(), "size": size, "private_inputs": False,
              "public_network": False, "original_strict_tests_replaced": False,
              "xray_version": fixture.version,
              "xray_sha256": hashlib.sha256(Path(fixture.xray).read_bytes()).hexdigest(),
              "native_client_sha256": hashlib.sha256(Path(fixture.client).read_bytes()).hexdigest(),
              "native_runtime_sha256": hashlib.sha256(Path(os.environ["SWIRL_TRANSPORT_RUNTIME"]).read_bytes()).hexdigest(),
              "results": results, "all_strict_cases_accepted": False}
    try:
        direct = receipt_origin(fixture)
        results.append({"client": "direct-socket", "network": "raw", "tls": False,
                        "result": strict_result(socket_echo(direct, size), size)})
        for network in ("raw", "ws"):
            for tls in (False, True):
                peer = fixture.peer(network, protocol="vmess", tls=tls)
                for client in ("swirl-native", "official-xray-control"):
                    origin = receipt_origin(fixture)
                    if client == "swirl-native":
                        control = BoundedControl(os.environ["SWIRL_TRANSPORT_RUNTIME"])
                        try:
                            config = {"schema": 1, "listen": "127.0.0.1:0", "selected": "a",
                                      "nodes": [{"id": "a", "outbound": peer["outbound"]}]}
                            started = control.command(time.monotonic() + 5, op="start", config=config,
                                                      transports={"a": peer["transport"]})
                            if not started["ok"]:
                                raise AssertionError("native runtime start rejected")
                            port = int(started["status"]["address"].rsplit(":", 1)[1])
                            result = socket_echo(origin, size, port)
                            result["native_status"] = control.command(time.monotonic() + 5, op="status")
                            control.command(time.monotonic() + 5, op="stop")
                        finally:
                            control.close()
                    else:
                        process, log, port = official_client(fixture, peer)
                        try:
                            result = socket_echo(origin, size, port)
                        finally:
                            process.terminate()
                            process.wait(timeout=5)
                            log.close()
                    fixture.assert_accepted(peer, origin)
                    strict_result(result, size)
                    results.append({"client": client, "network": network, "tls": tls,
                                    "result": result})
        report["all_strict_cases_accepted"] = all(
            row["result"]["strict_target_half_close"]
            for row in results)
    finally:
        fixture.close()
        report["server_context_cancellations"] = sum(
            peer["error"].read_text(encoding="utf-8").count("context canceled")
            for peer in fixture.peers if peer["error"].exists())
        report["evidence_directory"] = str(fixture.evidence)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["all_strict_cases_accepted"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--size", type=int, default=4 * 1024 * 1024 + 17)
    args = parser.parse_args()
    if not 0 < args.size <= 64 * 1024 * 1024:
        parser.error("size must be between 1 and 64 MiB")
    raise SystemExit(run(args.output, args.size))
