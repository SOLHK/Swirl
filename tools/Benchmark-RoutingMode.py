"""Synthetic loopback A/B for Rust routing cost; no system proxy or public nodes.

The two configurations use the same Direct outbound and 127.0.0.1 echo peer.
The only routing difference is zero rules versus one matching port rule, with
an optional 100 nonmatching suffix rules ahead of it. Results do not establish
private-provider throughput or the performance of an installed Windows app.
"""

import argparse
import concurrent.futures
import hashlib
import json
import math
from pathlib import Path
import queue
import re
import socket
import socketserver
import statistics
import subprocess
import threading
import time


CONCURRENCY = 16
TRANSFERS_PER_STREAM = 32
PAYLOAD = b"x" * 65536
ORDER = ("global", "rule", "rule", "global")


class BenchmarkError(RuntimeError):
    pass


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(20)
        try:
            while block := self.request.recv(len(PAYLOAD)):
                self.request.sendall(block)
        except OSError:
            pass


class EchoServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128


class Harness:
    def __init__(self, executable):
        self.process = subprocess.Popen(
            [str(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def command(self, **value):
        if self.process.poll() is not None:
            raise BenchmarkError("Rust harness exited before control command")
        try:
            self.process.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            line = self.lines.get(timeout=20)
        except (BrokenPipeError, queue.Empty) as error:
            raise BenchmarkError("Rust harness control timed out or closed") from error
        if line is None:
            raise BenchmarkError("Rust harness closed its output")
        try:
            result = json.loads(line)
        except json.JSONDecodeError as error:
            raise BenchmarkError("Rust harness emitted invalid JSON") from error
        if result.get("ok") is not True:
            raise BenchmarkError(f"Rust harness rejected command: {result.get('error', 'unknown')}")
        return result

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        self.process.stdout.close()


def configuration(mode, echo_port, suffix_rules):
    rules = []
    if mode == "rule":
        rules.extend(
            {
                "matcher": {"type": "domain_suffix", "value": f"nomatch{index:03}.invalid"},
                "outbound": "direct",
            }
            for index in range(suffix_rules)
        )
        rules.append(
            {
                "matcher": {"type": "destination_port", "value": echo_port},
                "outbound": "direct",
            }
        )
    return {
        "schema": 1,
        "listen": "127.0.0.1:0",
        "selected": "direct",
        "nodes": [{"id": "direct", "outbound": {"type": "direct"}}],
        "rules": rules,
        "smart_routing": False,
    }


def read_headers(sock):
    data = bytearray()
    while b"\r\n\r\n" not in data:
        part = sock.recv(1024)
        if not part:
            raise BenchmarkError("CONNECT response closed before headers")
        data.extend(part)
        if len(data) > 16384:
            raise BenchmarkError("CONNECT response exceeded header limit")
    return data


def open_tunnel(core_port, echo_port):
    started = time.perf_counter()
    sock = socket.create_connection(("127.0.0.1", core_port), timeout=20)
    try:
        sock.settimeout(20)
        target = f"127.0.0.1:{echo_port}"
        sock.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode("ascii"))
        if not read_headers(sock).startswith(b"HTTP/1.1 200"):
            raise BenchmarkError("CONNECT was rejected")
        return sock, (time.perf_counter() - started) * 1000
    except BaseException:
        sock.close()
        raise


def wait_for_idle(harness, handle):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = harness.command(op="snapshot", handle=handle)["status"]
        if status["active"] == 0:
            return status
        time.sleep(0.01)
    raise BenchmarkError("Rust Core still has active sessions after loopback transfer")


def transfer(sock, barrier):
    barrier.wait(timeout=20)
    for _ in range(TRANSFERS_PER_STREAM):
        sock.sendall(PAYLOAD)
        remaining = len(PAYLOAD)
        while remaining:
            block = sock.recv(remaining)
            if not block or block != PAYLOAD[: len(block)]:
                raise BenchmarkError("Loopback echo bytes differ or ended early")
            remaining -= len(block)
    return TRANSFERS_PER_STREAM * len(PAYLOAD)


def distribution(values):
    ordered = sorted(values)
    return {
        "samples": len(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def one_round(harness, server_port, mode, suffix_rules, warmups, samples):
    started = harness.command(op="start", config=configuration(mode, server_port, suffix_rules))
    handle = started["handle"]
    core_port = int(started["status"]["address"].rsplit(":", 1)[1])
    try:
        for _ in range(warmups):
            sock, _ = open_tunnel(core_port, server_port)
            sock.close()
        wait_for_idle(harness, handle)
        setup_ms = []
        for _ in range(samples):
            sock, elapsed = open_tunnel(core_port, server_port)
            setup_ms.append(elapsed)
            sock.close()
        wait_for_idle(harness, handle)

        sockets = []
        try:
            for _ in range(CONCURRENCY):
                sock, _ = open_tunnel(core_port, server_port)
                sockets.append(sock)
            barrier = threading.Barrier(CONCURRENCY + 1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
                tasks = [pool.submit(transfer, sock, barrier) for sock in sockets]
                transfer_started = time.perf_counter()
                barrier.wait(timeout=20)
                upload = sum(task.result(timeout=40) for task in tasks)
                seconds = time.perf_counter() - transfer_started
        finally:
            for sock in sockets:
                sock.close()

        status = wait_for_idle(harness, handle)
        expected = CONCURRENCY * TRANSFERS_PER_STREAM * len(PAYLOAD)
        expected_connections = warmups + samples + CONCURRENCY
        if upload != expected or any(
            (
                status["upload"] != expected,
                status["download"] != expected,
                status["failed"] != 0,
                status["rejected"] != 0,
                status["accepted"] != expected_connections,
            )
        ):
            raise BenchmarkError("Rust Core totals or session outcomes differ from fixture")
        return {
            "mode": mode,
            "rule_count": 0 if mode == "global" else suffix_rules + 1,
            "connect_setup_ms": distribution(setup_ms),
            "connect_setup_samples_ms": setup_ms,
            "transfer_seconds": seconds,
            "payload_mbps_each_direction": expected * 8 / seconds / 1e6,
            "bytes_each_direction": expected,
            "accepted": status["accepted"],
            "failed": status["failed"],
            "rejected": status["rejected"],
        }
    finally:
        harness.command(op="stop", handle=handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-harness-sha256", required=True)
    parser.add_argument("--source-commit", required=True, help="verified full commit used to build the harness")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--warmups", type=int, default=16)
    parser.add_argument("--setup-samples", type=int, default=100)
    parser.add_argument("--nonmatching-suffix-rules", type=int, choices=(0, 100), default=0)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 5 or not 1 <= args.warmups <= 100 or not 20 <= args.setup_samples <= 500:
        parser.error("cycles, warmups or setup samples are outside bounded ranges")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.source_commit):
        parser.error("source commit must be a full Git SHA")
    executable = args.harness.resolve(strict=True)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    if digest.lower() != args.expected_harness_sha256.lower():
        parser.error("harness SHA-256 differs from the independently verified build")

    report = {
        "schema": 1,
        "scope": "synthetic 127.0.0.1 Rust Core Direct outbound; no system proxy, public or private node",
        "source_binary_identity": "source commit supplied by operator; build provenance must be verified separately",
        "source_commit": args.source_commit.lower(),
        "harness_sha256": digest,
        "order": list(ORDER) * args.cycles,
        "warmups_per_round": args.warmups,
        "setup_samples_per_round": args.setup_samples,
        "transfer": {"concurrency": CONCURRENCY, "writes_per_stream": TRANSFERS_PER_STREAM, "bytes_per_write": len(PAYLOAD)},
        "nonmatching_suffix_rules": args.nonmatching_suffix_rules,
        "rounds": [],
    }
    with EchoServer(("127.0.0.1", 0), Echo) as server:
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        harness = Harness(executable)
        try:
            for mode in report["order"]:
                report["rounds"].append(
                    one_round(
                        harness,
                        server.server_address[1],
                        mode,
                        args.nonmatching_suffix_rules,
                        args.warmups,
                        args.setup_samples,
                    )
                )
        finally:
            harness.close()
            server.shutdown()
            server_thread.join(timeout=5)

    report["summary"] = {}
    for mode in ("global", "rule"):
        rounds = [row for row in report["rounds"] if row["mode"] == mode]
        report["summary"][mode] = {
            "connect_setup_ms": distribution(
                [sample for row in rounds for sample in row["connect_setup_samples_ms"]]
            ),
            "transfer_seconds": distribution([row["transfer_seconds"] for row in rounds]),
            "payload_mbps_each_direction": distribution([row["payload_mbps_each_direction"] for row in rounds]),
            "total_bytes_each_direction": sum(row["bytes_each_direction"] for row in rounds),
            "total_failed": sum(row["failed"] for row in rounds),
            "total_rejected": sum(row["rejected"] for row in rounds),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}))


if __name__ == "__main__":
    main()
