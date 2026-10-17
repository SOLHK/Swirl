"""Explicit public HTTPS checks through the native Rust harness.

Uses only fixed public endpoints and a DIRECT route, with no existing proxy,
private subscription, trust-store changes or provider credentials. The DoH case
uses Rust's authenticated DNS transport with explicit IP bootstrap; it cannot
fall back to system DNS. A failure is evidence, never silently retried elsewhere.
The CLI remains public-origin evidence, not remote proxy-provider or TUN
acceptance. An authorized in-memory caller may pass one SS/Trojan outbound to
probe(); that caller must redact the returned diagnostics before saving them.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import queue
import socket
import ssl
import subprocess
import threading
import time


PROBE_TIMEOUT_SECONDS = 45
CLEANUP_RESERVE_SECONDS = 5
CONTROL_ERRORS = (OSError, EOFError, ValueError, KeyError, TypeError, RuntimeError, queue.Empty)


def remaining(deadline, maximum):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("ProbeDeadlineExceeded")
    return min(seconds, maximum)


def read_header(stream, deadline):
    data = bytearray()
    while not data.endswith(b"\r\n\r\n"):
        if len(data) >= 16384:
            raise ValueError("HeaderLimit")
        # A peer sending one byte at a time cannot restart the total budget.
        stream.settimeout(remaining(deadline, 12))
        part = stream.recv(1)
        if not part:
            raise EOFError("HeaderClosed")
        data.extend(part)
    return bytes(data)


def close_https(stream, deadline):
    # SSLSocket.close() does not exchange close_notify. Closing immediately
    # after the HEAD headers can reset a TCP socket with an unread TLS alert,
    # causing a real relay error even though HTTP status parsing succeeded.
    stream.settimeout(remaining(deadline, 12))
    with stream.unwrap() as plain:
        plain.settimeout(remaining(deadline, 12))
        plain.shutdown(socket.SHUT_WR)
        if plain.recv(1):
            raise RuntimeError("UnexpectedDataAfterTlsClose")


def settled_snapshot(command, handle, deadline, outcome):
    while True:
        result = command(deadline, op="snapshot", handle=handle)
        if not result.get("ok"):
            raise RuntimeError("SnapshotRejected")
        state = result["status"]
        if not isinstance(state, dict):
            raise ValueError("CoreSnapshotShape")
        keys = ("accepted", "active", "failed", "upload", "download")
        for key in keys:
            if type(state[key]) is not int or state[key] < 0:
                raise ValueError("CoreSnapshotShape")
        if not isinstance(state["last_error"], str):
            raise ValueError("CoreSnapshotShape")
        connections = state["connections"]
        if (not isinstance(connections, list) or len(connections) > 256 or
                any(not isinstance(record, dict) or type(record.get("ended")) is not bool
                    for record in connections)):
            raise ValueError("CoreSnapshotShape")
        outcome["core"] = {key: state[key] for key in (*keys, "last_error")}
        outcome["core"]["recorded_connections"] = len(connections)
        # A header can arrive before relay shutdown is accounted. The guard
        # decrements active before marking its record ended, so wait for both.
        if state["active"] == 0 and all(record["ended"] for record in connections):
            return outcome["core"]
        time.sleep(remaining(deadline, 0.02))


def native_traffic_error(state):
    if state["active"] != 0:
        return "NativeConnectionsNotSettled"
    if state["failed"] != 0 or state["last_error"]:
        return "NativeRelayFailed"
    if state["recorded_connections"] != 1:
        return "NativeConnectionRecordCount"
    if state["accepted"] != 1 or not state["upload"] or not state["download"]:
        return "MissingNativeTraffic"
    return None


def probe_configuration(encrypted_dns=False, outbound=None):
    selected = "public-direct" if outbound is None else "anonymous-node"
    if outbound is not None:
        fields = {
            "shadowsocks": {"type", "host", "port", "password", "cipher", "udp", "obfs_http"},
            "trojan": {"type", "host", "port", "password", "tls", "websocket"},
        }
        if (not isinstance(outbound, dict) or not isinstance(outbound.get("type"), str)
                or outbound["type"] not in fields
                or not set(outbound).issubset(fields[outbound["type"]])
                or encrypted_dns):
            raise ValueError("IsolatedOutboundRejected")
    config = {"schema": 1, "listen": "127.0.0.1:0", "selected": selected,
              "nodes": [{"id": selected, "outbound":
                         {"type": "direct"} if outbound is None else outbound}],
              "limits": {"max_connections": 2, "handshake_timeout_ms": 10000}}
    if encrypted_dns:
        config["dns"] = {"use_system_hosts": False, "tls_servers": [{
            "address": "1.1.1.1:443", "https_path": "/dns-query",
            "tls": {"server_name": "cloudflare-dns.com", "alpn": ["http/1.1"]}}]}
    # The initial command fits an empty 4 KiB stdin pipe even if the child
    # fails before reading. No caller-supplied rules, groups or DIRECT fallback.
    encoded = json.dumps({"op": "start", "config": config})
    if len(encoded.encode("utf-8")) + 1 > 4096:
        raise ValueError("ProbeConfigurationLimit")
    return json.loads(encoded)["config"]


def probe(harness, host, encrypted_dns=False, *, outbound=None):
    config = probe_configuration(encrypted_dns, outbound)
    selected = config["selected"]
    started = time.monotonic()
    deadline = started + PROBE_TIMEOUT_SECONDS
    # All work phases share one cutoff; cleanup consumes a reserved part of
    # the same total budget rather than receiving a new timeout after failure.
    work_deadline = deadline - CLEANUP_RESERVE_SECONDS
    outcome = {"host": host, "port": 443, "method": "HEAD", "path": "/",
               "dns": "native-doh" if encrypted_dns else "system",
               "route": "explicit-native-direct" if outbound is None else "explicit-native-outbound",
               "success": False}
    if encrypted_dns:
        outcome["dns_endpoint"] = "https://cloudflare-dns.com/dns-query"
        outcome["dns_bootstrap"] = "1.1.1.1:443"
    process = None
    reader = None
    replies = queue.Queue(maxsize=4)
    control_usable = True

    def deliver_reply(reply):
        try:
            replies.put_nowait(reply)
            return True
        except queue.Full:
            return False

    def read_replies():
        try:
            while True:
                line = process.stdout.readline(65537)
                if not line:
                    deliver_reply(EOFError("CoreControlClosed"))
                    return
                if len(line) > 65536 or not line.endswith("\n"):
                    deliver_reply(ValueError("CoreControlReplyLimit"))
                    return
                if not deliver_reply(line):
                    return
        except (OSError, ValueError):
            deliver_reply(EOFError("CoreControlReadFailed"))

    def command(control_deadline, **value):
        nonlocal control_usable
        if not control_usable:
            raise RuntimeError("CoreControlUnavailable")
        try:
            remaining(control_deadline, 15)
            # These fixed commands together fit well within the stdin pipe.
            process.stdin.write(json.dumps(value) + "\n")
            process.stdin.flush()
            reply = replies.get(timeout=remaining(control_deadline, 15))
            if isinstance(reply, (OSError, EOFError, ValueError)):
                raise reply
            result = json.loads(reply)
            if not isinstance(result, dict):
                raise ValueError("CoreControlReplyShape")
            return result
        except CONTROL_ERRORS:
            # Replies have no request IDs. After a timeout or malformed reply,
            # do not mistake a delayed response for the next cleanup command.
            control_usable = False
            raise

    def cleanup_failure(reason, error=None):
        outcome["success"] = False
        outcome.setdefault("failure_phase", "cleanup")
        outcome.setdefault("cleanup_error", reason)
        if error is not None:
            outcome.setdefault("cleanup_error_type", type(error).__name__)

    handle = None
    phase = "start"
    try:
        process = subprocess.Popen([str(harness)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   text=True)
        reader = threading.Thread(target=read_replies, daemon=True)
        reader.start()
        result = command(work_deadline, op="start", config=config)
        if not result.get("ok"):
            outcome["core_error"] = result.get("error")
            raise RuntimeError("CoreStartRejected")
        handle = result["handle"]
        state = result["status"]
        if not isinstance(state, dict):
            raise ValueError("CoreStatusShape")
        if state["engine"] != "swirl-rust" or state["selected"] != selected:
            raise RuntimeError("CoreIdentityMismatch")
        outcome["engine"] = state["engine"]
        if not isinstance(state["address"], str):
            raise ValueError("CoreAddressShape")
        address = state["address"].rsplit(":", 1)
        if len(address) != 2:
            raise ValueError("CoreAddressShape")
        port = int(address[1])
        if not 1 <= port <= 65535:
            raise ValueError("CoreAddressShape")
        authority = f"{host}:443"
        phase = "native-connect"
        # socket and rust TcpStream do not consult HTTP(S)_PROXY. Only the
        # fresh loopback harness is used as this client's forwarding endpoint.
        with socket.create_connection(("127.0.0.1", port), timeout=remaining(work_deadline, 12)) as raw:
            raw.settimeout(remaining(work_deadline, 12))
            raw.sendall(f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode())
            if not read_header(raw, work_deadline).startswith(b"HTTP/1.1 200 "):
                raise RuntimeError("NativeConnectRejected")
            outcome["native_connect_accepted"] = True
            phase = "origin-tls"
            with ssl.create_default_context().wrap_socket(
                    raw, server_hostname=host, do_handshake_on_connect=False) as tls:
                tls.settimeout(remaining(work_deadline, 12))
                tls.do_handshake()
                outcome["certificate_verified"] = True
                outcome["tls_version"] = tls.version()
                phase = "public-https"
                tls.settimeout(remaining(work_deadline, 12))
                tls.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
                status = read_header(tls, work_deadline).split(b"\r\n", 1)[0].split()
                if len(status) < 2 or status[0] not in (b"HTTP/1.0", b"HTTP/1.1"):
                    raise ValueError("HttpStatusSyntax")
                code = int(status[1])
                outcome["http_status"] = code
                if not 200 <= code < 400:
                    raise RuntimeError("HttpStatusRejected")
                phase = "origin-close"
                close_https(tls, work_deadline)
                outcome["orderly_close"] = True
                outcome["success"] = True
    except CONTROL_ERRORS as error:
        outcome["failure_phase"] = phase
        outcome["error_type"] = type(error).__name__
        # Only fixed public traffic is used, but keep diagnostics bounded and
        # avoid printing arbitrary response headers or environment variables.
        if isinstance(error, RuntimeError):
            outcome["error"] = str(error)
    finally:
        if process is not None and handle is not None:
            try:
                # Keep the last two seconds of the original budget for process
                # termination if a broken control channel does not acknowledge.
                state = settled_snapshot(command, handle, deadline - 2, outcome)
                outcome["native_session_settled"] = True
                traffic_error = native_traffic_error(state)
                if outcome["success"] and traffic_error:
                    outcome.update(success=False, failure_phase="accounting",
                                   error=traffic_error)
            except CONTROL_ERRORS as error:
                cleanup_failure("CoreSnapshotFailed", error)
            try:
                if not command(deadline - 2, op="stop", handle=handle).get("ok"):
                    raise RuntimeError("StopRejected")
            except CONTROL_ERRORS as error:
                cleanup_failure("CoreStopFailed", error)
        if process is not None:
            try:
                process.stdin.close()
            except (OSError, ValueError) as error:
                cleanup_failure("CoreInputCloseFailed", error)
            try:
                process.wait(timeout=remaining(deadline - 1, 5))
            except (subprocess.TimeoutExpired, TimeoutError) as error:
                cleanup_failure("CoreDidNotStop", error)
                try:
                    process.kill()  # Only the harness created by this probe.
                    process.wait(timeout=remaining(deadline, 5))
                except (OSError, subprocess.TimeoutExpired) as error:
                    cleanup_failure("CoreTerminationFailed", error)
            except OSError as error:
                cleanup_failure("CoreWaitFailed", error)
            if reader is not None and reader.ident is not None:
                reader.join(timeout=max(0, min(1, deadline - time.monotonic())))
            if reader is not None and reader.is_alive():
                # Closing a pipe while another thread holds its read lock can
                # block; the already terminated process will release its reader.
                cleanup_failure("CoreReaderDidNotStop")
            else:
                try:
                    process.stdout.close()
                except (OSError, ValueError) as error:
                    cleanup_failure("CoreOutputCloseFailed", error)
            if process.returncode != 0:
                outcome.update(success=False, harness_exit_code=process.returncode)
        outcome["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    harness = args.harness.resolve(strict=True)
    repository = Path(__file__).resolve().parents[1]
    identity = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True, timeout=5,
                              cwd=repository).stdout.strip()
    tracked_worktree_clean = False
    source_identity_error = None
    try:
        source_status = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", "core", "tools/Verify-PublicRustCore.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            cwd=repository,
        ).returncode
        # git diff ignores untracked files. An as-yet-uncommitted verifier must
        # not imply that HEAD describes the script that produced the evidence.
        tracked_status = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", "tools/Verify-PublicRustCore.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            cwd=repository,
        ).returncode
        if source_status not in (0, 1) or tracked_status not in (0, 1):
            source_identity_error = "GitSourceIdentityFailed"
        else:
            tracked_worktree_clean = source_status == 0 and tracked_status == 0
    except (OSError, subprocess.TimeoutExpired):
        source_identity_error = "GitSourceIdentityUnavailable"
    report = {"schema": 1, "commit": identity, "platform": platform.system(),
              "tracked_worktree_clean": tracked_worktree_clean,
              "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "harness_sha256": hashlib.sha256(harness.read_bytes()).hexdigest(),
              "scope": "Public HTTPS via native DIRECT and native DoH; no provider, UDP, TUN or performance claim",
              "checks": [probe(harness, "example.com"),
                         probe(harness, "www.rust-lang.org"),
                         probe(harness, "example.com", encrypted_dns=True)]}
    if source_identity_error is not None:
        report["source_identity_error"] = source_identity_error
    report["success"] = tracked_worktree_clean and all(check["success"] for check in report["checks"])
    text = json.dumps(report, indent=2)
    args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
