#!/usr/bin/env python3
"""Reproducible loopback diagnostics for native Rust transports, not a WAN benchmark.

Every transport uses TLS, VLESS authentication, the same pinned independent
server family, origin implementation, byte pattern, payload size, and number
of samples. Legacy HTTP/2 necessarily uses the pinned historical Xray server;
that difference is reported. CPU and peak RSS cover only the native client
process (including its startup and shutdown), never Xray or Python. The client
reports connection and transfer intervals separately from process startup.

Environment: SWIRL_TRANSPORT_CLIENT, SWIRL_XRAY_BINARY,
SWIRL_XRAY_LEGACY_BINARY. GNU time is required on Linux; specify --time-binary
for a separately installed copy. This script installs no dependencies.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import statistics
import subprocess
import time

from transport_peer import Fixture, pattern_hash


TRANSPORTS = ("raw", "ws", "grpc", "http2", "httpupgrade", "xhttp")


class BenchmarkFailure(Exception):
    def __init__(self, reason, **details):
        super().__init__(reason)
        self.details = {"reason": reason, **details}


def wait_for_origin_release(origin, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with origin.lock:
            active = len(origin.active)
        if not active:
            return
        time.sleep(0.01)
    raise AssertionError(f"destination retained {active} active sockets after client exit")


def descriptor_count(peer):
    return len(list(Path(f"/proc/{peer['process'].pid}/fd").iterdir()))


def timed_client(fixture, request, time_binary, label):
    metrics = fixture.evidence / f"{label}-time.txt"
    command = [str(time_binary), "-o", str(metrics), "-f", "%U %S %M %e %x", fixture.client]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(json.dumps(request), timeout=60)
    except subprocess.TimeoutExpired:
        # The process group contains only this invocation of GNU time and its
        # native client, so timeout cleanup cannot orphan a benchmark client.
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=5)
        raise BenchmarkFailure("NativeClientTimeout", stdout=stdout, stderr=stderr) from None
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        raise BenchmarkFailure("InvalidNativeClientReport", stdout=stdout,
                               stderr=stderr, exit_code=process.returncode) from None
    if process.returncode != 0 or not report.get("ok"):
        raise BenchmarkFailure("NativeClientFailed", native_report=report,
                               stderr=stderr, exit_code=process.returncode)
    size = request["size"]
    if (report["uploaded"] != size + 8 or report["downloaded"] != size
            or report["sha256"] != pattern_hash(size)):
        raise BenchmarkFailure("DataIntegrityOrByteCount", native_report=report,
                               exit_code=process.returncode, payload_verified=False)
    if report["close"] != "clean":
        raise BenchmarkFailure("NormalCloseFailed", native_report=report,
                               exit_code=process.returncode, payload_verified=True,
                               time_output=metrics.read_text(encoding="utf-8"))
    fields = metrics.read_text(encoding="utf-8").strip().splitlines()[-1].split()
    if len(fields) != 5 or fields[4] != "0":
        raise AssertionError("GNU time metrics missing or unsuccessful")
    seconds = report["transfer_us"] / 1_000_000
    if seconds <= 0:
        raise AssertionError("invalid native transfer duration")
    return {
        **report, "client_cpu_user_s": float(fields[0]),
        "client_cpu_system_s": float(fields[1]), "client_peak_rss_kib": int(fields[2]),
        "client_process_elapsed_s": float(fields[3]), "exit_code": int(fields[4]),
        "payload_mib": size / (1024 * 1024),
        "payload_mib_per_s_each_direction": (size / (1024 * 1024)) / seconds,
        "payload_mib_per_s_sum_directions": 2 * (size / (1024 * 1024)) / seconds,
    }


def measure_transport(name, args):
    fixture = None
    completed_samples = []
    phase = "fixture"
    try:
        fixture = Fixture(f"C6-benchmark-{name}")
        legacy = name == "http2"
        peer = fixture.peer("h2" if legacy else name, tls=True, legacy=legacy)
        origin = fixture.origin(mode="echo")
        warmup = fixture.request(peer, origin, mode="echo", size=64 * 1024)
        phase = "warmup"
        timed_client(fixture, warmup, args.time_binary, "warmup")
        fixture.assert_accepted(peer, origin)
        wait_for_origin_release(origin)
        before = descriptor_count(peer)
        for sample in range(args.samples):
            phase = f"transfer-sample-{sample + 1}"
            request = fixture.request(peer, origin, mode="echo", size=args.size_mib * 1024 * 1024,
                                      timeout_ms=45000)
            completed_samples.append(timed_client(fixture, request, args.time_binary,
                                                   f"sample-{sample + 1}"))
            wait_for_origin_release(origin)
        after_samples = descriptor_count(peer)
        descriptor_samples = []
        for iteration in range(args.repetitions):
            phase = f"lifecycle-sample-{iteration + 1}"
            request = fixture.request(peer, origin, mode="echo", size=64 * 1024)
            result, report = fixture.run(request)
            if (result.returncode != 0 or not report.get("ok")
                    or report["close"] != "clean"
                    or report["sha256"] != pattern_hash(64 * 1024)):
                raise BenchmarkFailure("SequentialLifecycleFailed", native_report=report,
                                       exit_code=result.returncode)
            wait_for_origin_release(origin)
            descriptor_samples.append(descriptor_count(peer))
        with origin.lock:
            active = len(origin.active)
        summary_fields = ("connect_us", "transfer_us", "client_cpu_user_s",
                          "client_cpu_system_s", "client_peak_rss_kib",
                          "payload_mib_per_s_each_direction", "payload_mib_per_s_sum_directions")
        return {
            "transport": name, "protocol": "vless", "security": "tls", "outcome": "passed",
            "server_version": peer["version"], "samples": completed_samples,
            "median": {field: statistics.median(sample[field] for sample in completed_samples)
                       for field in summary_fields},
            "resource_observation": {
                "server_fd_after_warmup": before,
                "server_fd_after_transfer_samples": after_samples,
                "server_fd_after_each_sequential_client": descriptor_samples,
                "server_fd_end": descriptor_count(peer),
                "sequential_clients": args.repetitions,
                "destination_active_at_end": active,
                "destination_authenticated_connections": len(origin.requests),
                "destination_half_closes": origin.client_closes,
                "scope": "Persistent independent server, fresh native client process per connection. "
                         "Finite observations do not establish absence of all leaks in a long-lived client runtime.",
            },
        }
    except Exception as error:
        # Preserve the failure and continue unrelated transports. There is no
        # median/throughput conclusion for a combination that did not complete
        # all integrity, closure and lifecycle checks; main returns exit 1.
        details = error.details if isinstance(error, BenchmarkFailure) else {
            "reason": type(error).__name__, "detail": str(error)}
        return {"transport": name, "protocol": "vless", "security": "tls",
                "outcome": "failed", "phase": phase, "failure": details,
                "completed_samples_before_failure": completed_samples,
                "evidence_directory": str(fixture.evidence) if fixture else None}
    finally:
        if fixture:
            try:
                fixture.close()
            except Exception as error:
                raise BenchmarkFailure("FixtureCleanupFailed", detail=str(error),
                                       evidence_directory=str(fixture.evidence)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--time-binary", default=os.environ.get("GNU_TIME", "/usr/bin/time"), type=Path)
    parser.add_argument("--size-mib", type=int, default=16)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--transports", nargs="+", choices=TRANSPORTS, default=list(TRANSPORTS))
    parser.add_argument("--build-label", default="unspecified")
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("these GNU time /proc resource diagnostics require Linux")
    if not (1 <= args.size_mib <= 64 and 1 <= args.samples <= 20 and 1 <= args.repetitions <= 200):
        parser.error("payload, sample or repetition count outside bounded range")
    if not args.time_binary.is_file():
        parser.error("GNU time missing; provide --time-binary")
    version = subprocess.run([str(args.time_binary), "--version"], capture_output=True,
                             text=True, check=True, timeout=5).stdout.splitlines()[0]
    client = Path(os.environ["SWIRL_TRANSPORT_CLIENT"])
    os.environ.setdefault("SWIRL_TRANSPORT_EVIDENCE",
                          str(args.output.parent / f"{args.output.stem}-peers"))
    output = {
        "scope": "Loopback native-client diagnostics; not public-node, WAN, Clash or Loon comparisons.",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "machine": platform.machine(),
        "build_label": args.build_label,
        "client_sha256": hashlib.sha256(client.read_bytes()).hexdigest(),
        "time_version": version,
        "conditions": {"tls": True, "proxy_protocol": "vless", "samples": args.samples,
                       "mib_each_direction": args.size_mib,
                       "sequential_lifecycle_connections": args.repetitions,
                       "cpu_scope": "native client process including startup/shutdown; excludes server/fixture",
                       "rss_unit": "KiB (GNU time on Linux)",
                       "connect_time_scope": "native connector return timer; excludes process startup; "
                                             "deferred server authentication/response can occur during transfer",
                       "throughput_scope": "verified payload bytes / native full-duplex transfer timer",
                       "latency_note": "connector-return latency; deferred response/auth validation "
                                       "is included in transfer_us",
                       "throughput_note": "each_direction=size/transfer_seconds; "
                                          "sum_directions=2*size/transfer_seconds; units are MiB/s"},
        "results": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name in args.transports:
        try:
            result = measure_transport(name, args)
        except BenchmarkFailure as error:
            # A cleanup failure is still a failed combination and must not
            # prevent the unrelated transports from producing their evidence.
            result = {"transport": name, "outcome": "failed", "phase": "cleanup",
                      "failure": error.details}
        output["results"].append(result)
        args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: result[key] for key in (
            "transport", "outcome", "median", "resource_observation", "phase", "failure")
            if key in result}), flush=True)
    return 1 if any(result["outcome"] != "passed" for result in output["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
