"""Bounded, anonymous DNS/TCP comparison; never refreshes subscriptions.

The Python worker uses OS getaddrinfo and nonblocking sockets independently of
Rust. Each CLI invocation owns one DNS worker and exits without waiting for a
stalled OS resolver. compare() runs isolated Python and Rust children serially
inside one ten-second budget, so their TCP attempts never overlap.
"""
import errno
import ipaddress
import json
from pathlib import Path
import queue
import selectors
import socket
import subprocess
import sys
import threading
import time


MAX_INPUT = 65536
MAX_ADDRESSES = 16
MAX_BUDGET_MS = 10000
OUTCOMES = {"success", "refused", "timeout", "unreachable", "other", "cancelled"}
ERRORS = {None, "UpstreamDnsTimeout", "DnsLookupFailed", "DnsEmpty",
          "UpstreamAddressLimit", "UpstreamTcpTimeout", "UpstreamConnectFailed",
          "SocketOptions", "InvalidDiagnosticInput", "DiagnosticProcessFailed",
          "DiagnosticProcessTimeout", "DiagnosticOutputInvalid", "DnsInvalidTarget",
          "DnsBusy", "DnsStopped", "DnsTimeout", "DnsTask", "DnsNameError",
          "DnsState", "DnsConfiguration", "DiagnosticInput", "DiagnosticBudget",
          "DiagnosticDnsConfig", "DiagnosticRuntime", "DiagnosticInternal"}
INPUT_ERRORS = {"InvalidDiagnosticInput", "DiagnosticInput", "DiagnosticBudget",
                "DiagnosticDnsConfig", "DiagnosticRuntime", "DiagnosticInternal",
                "DiagnosticProcessFailed", "DiagnosticProcessTimeout", "DiagnosticOutputInvalid"}
# Timing observations retain real scheduler delay instead of being clipped to a
# claimed budget. A materially late or malformed report is rejected by compare.
TIMING_SLACK_MS = 100


class AddressLimit(ValueError):
    pass


def load_json(payload):
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DiagnosticOutputInvalid")
            result[key] = value
        return result
    return json.loads(payload, object_pairs_hook=unique_fields)


def error_category(code):
    if code in {errno.ECONNREFUSED, 10061}:
        return "refused"
    if code in {errno.ETIMEDOUT, 10060}:
        return "timeout"
    if code in {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN, 10050, 10051, 10065}:
        return "unreachable"
    return "other"


def valid_request(request):
    if not isinstance(request, dict) or set(request) - {
            "host", "port", "total_budget_ms", "dns_budget_ms"}:
        return False
    host, port = request.get("host"), request.get("port")
    total = request.get("total_budget_ms", MAX_BUDGET_MS)
    dns = request.get("dns_budget_ms", 3000)
    return (isinstance(host, str) and 0 < len(host) <= 253
            and not any(c.isspace() or ord(c) < 32 for c in host)
            and not any(c in host for c in "/[]\\")
            and type(port) is int and 1 <= port <= 65535
            and type(total) is int and 1 <= total <= MAX_BUDGET_MS
            and type(dns) is int and 1 <= dns <= 3000)


def empty_report(total=MAX_BUDGET_MS, dns=3000):
    return {"schema": 1, "engine": "python-socket", "scope": "dns_tcp_only",
            "ok": False, "error_code": None, "failure_stage": None,
            "total_budget_ms": total, "dns_budget_ms": min(dns, total),
            "dns_elapsed_ms": 0, "tcp_elapsed_ms": 0, "total_elapsed_ms": 0,
            "address_count": 0, "ipv4_count": 0, "ipv6_count": 0,
            "attempted_count": 0, "remaining_count": 0, "peak_pending": 0,
            "attempts": []}


def ordered_addresses(rows):
    unique = []
    for index, (family, kind, _, _, address) in enumerate(rows):
        if index >= MAX_ADDRESSES:
            raise AddressLimit("UpstreamAddressLimit")
        if family not in (socket.AF_INET, socket.AF_INET6) or kind != socket.SOCK_STREAM:
            continue
        # Validate that TCP work cannot trigger another implicit hostname lookup.
        ipaddress.ip_address(address[0].split("%", 1)[0])
        if (family, address) not in unique:
            unique.append((family, address))
    ordered = []
    preferred = unique[0][0] if unique else socket.AF_INET6
    while unique:
        position = next((i for i, row in enumerate(unique) if row[0] == preferred), 0)
        ordered.append(unique.pop(position))
        preferred = socket.AF_INET if preferred == socket.AF_INET6 else socket.AF_INET6
    return ordered


def _resolve(host, port, output, resolver):
    try:
        output.put((True, resolver(host, port, family=socket.AF_UNSPEC,
                                   type=socket.SOCK_STREAM)), block=False)
    except Exception:
        output.put((False, None), block=False)


def diagnose_python(request, *, resolver=socket.getaddrinfo):
    """Called in an isolated worker by compare(); returns only fixed metadata."""
    if not valid_request(request):
        result = empty_report()
        result.update(error_code="InvalidDiagnosticInput", failure_stage="input")
        return result
    total = request.get("total_budget_ms", MAX_BUDGET_MS)
    dns_budget = min(request.get("dns_budget_ms", 3000), total)
    report = empty_report(total, dns_budget)
    started = time.monotonic()
    deadline = started + total / 1000
    dns_deadline = min(deadline, started + dns_budget / 1000)
    answers = queue.Queue(maxsize=1)
    worker = threading.Thread(target=_resolve,
                              args=(request["host"], request["port"], answers, resolver),
                              daemon=True)
    worker.start()
    try:
        ok, rows = answers.get(timeout=max(0, dns_deadline - time.monotonic()))
        # Thread startup and late queue delivery consume the same DNS budget;
        # an answer delivered after that deadline cannot start TCP work.
        if time.monotonic() >= dns_deadline:
            raise queue.Empty()
        if not ok:
            report.update(error_code="DnsLookupFailed", failure_stage="dns")
            return report
        addresses = ordered_addresses(rows)
        if not addresses:
            report.update(error_code="DnsEmpty", failure_stage="dns")
            return report
    except queue.Empty:
        report.update(error_code="UpstreamDnsTimeout", failure_stage="dns")
        return report
    except AddressLimit:
        report.update(error_code="UpstreamAddressLimit", failure_stage="tcp_connect")
        return report
    except (ValueError, TypeError, IndexError):
        report.update(error_code="DnsLookupFailed", failure_stage="dns")
        return report
    finally:
        report["dns_elapsed_ms"] = int((time.monotonic() - started) * 1000)
        report["total_elapsed_ms"] = report["dns_elapsed_ms"]

    report["address_count"] = len(addresses)
    report["ipv4_count"] = sum(family == socket.AF_INET for family, _ in addresses)
    report["ipv6_count"] = len(addresses) - report["ipv4_count"]
    tcp_started = time.monotonic()
    pending = {}
    next_position = 0
    next_start = tcp_started
    selector = selectors.DefaultSelector()

    def finish(sock, outcome):
        attempt, attempt_started, _ = pending.pop(sock)
        try:
            selector.unregister(sock)
        except (KeyError, ValueError):
            pass
        sock.close()
        attempt.update(outcome=outcome, elapsed_ms=int((time.monotonic() - attempt_started) * 1000))

    def expire(now):
        expired = False
        for sock, (_, _, expiry) in list(pending.items()):
            if now >= expiry:
                finish(sock, "timeout")
                expired = True
        return expired

    try:
        while True:
            now = time.monotonic()
            if now >= deadline:
                for sock in list(pending):
                    finish(sock, "timeout")
                report.update(error_code="UpstreamTcpTimeout", failure_stage="tcp_connect")
                break
            if expire(now):
                next_start = now
            if next_position < len(addresses) and len(pending) < 2 and now >= next_start:
                family, address = addresses[next_position]
                next_position += 1
                attempt = {"ordinal": next_position, "family": "ipv4" if family == socket.AF_INET else "ipv6",
                           "started_ms": int((now - tcp_started) * 1000), "elapsed_ms": 0, "outcome": "other"}
                report["attempts"].append(attempt)
                report["peak_pending"] = max(report["peak_pending"], len(pending) + 1)
                sock = None
                try:
                    sock = socket.socket(family, socket.SOCK_STREAM)
                    sock.setblocking(False)
                    code = sock.connect_ex(address)
                    attempt["elapsed_ms"] = int((time.monotonic() - now) * 1000)
                    if time.monotonic() >= deadline:
                        sock.close()
                        attempt["outcome"] = "timeout"
                        for other in list(pending):
                            finish(other, "timeout")
                        report.update(error_code="UpstreamTcpTimeout", failure_stage="tcp_connect")
                        break
                    if code == 0:
                        sock.close()
                        attempt["outcome"] = "success"
                        report["ok"] = True
                        break
                    if code not in {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY,
                                    errno.EINTR, 10035, 10036, 10037}:
                        sock.close()
                        attempt["outcome"] = error_category(code)
                        next_start = now
                        continue
                    selector.register(sock, selectors.EVENT_WRITE)
                    pending[sock] = (attempt, now, min(deadline, now + 2)
                                     if next_position < len(addresses) else deadline)
                    next_start = now + 0.25
                except OSError as error:
                    if sock is not None:
                        sock.close()
                    attempt["outcome"] = error_category(error.errno)
                    attempt["elapsed_ms"] = int((time.monotonic() - now) * 1000)
                    next_start = time.monotonic()
                    continue
            if not pending and next_position == len(addresses):
                report.update(error_code="UpstreamTcpTimeout" if any(
                    row["outcome"] == "timeout" for row in report["attempts"])
                    else "UpstreamConnectFailed", failure_stage="tcp_connect")
                break
            wake = min([deadline] + [value[2] for value in pending.values()])
            if next_position < len(addresses) and len(pending) < 2:
                wake = min(wake, next_start)
            ready = selector.select(max(0, wake - time.monotonic()))
            now = time.monotonic()
            if now >= deadline:
                for sock in list(pending):
                    finish(sock, "timeout")
                report.update(error_code="UpstreamTcpTimeout", failure_stage="tcp_connect")
                break
            if expire(now):
                next_start = now
            for key, _ in ready:
                sock = key.fileobj
                # A selector can return readiness for an already expired slot.
                if sock not in pending:
                    continue
                try:
                    code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                except OSError as error:
                    code = error.errno
                now = time.monotonic()
                if now >= deadline:
                    for other in list(pending):
                        finish(other, "timeout")
                    report.update(error_code="UpstreamTcpTimeout", failure_stage="tcp_connect")
                    break
                if now >= pending[sock][2]:
                    finish(sock, "timeout")
                    next_start = now
                    continue
                finish(sock, "success" if code == 0 else error_category(code))
                if code == 0:
                    report["ok"] = True
                    break
                next_start = time.monotonic()
            if report["ok"] or report["error_code"] == "UpstreamTcpTimeout":
                break
    finally:
        for sock in list(pending):
            finish(sock, "cancelled")
        selector.close()
        report["attempted_count"] = len(report["attempts"])
        report["remaining_count"] = len(addresses) - report["attempted_count"]
        report["tcp_elapsed_ms"] = int((time.monotonic() - tcp_started) * 1000)
        report["total_elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return report


def safe_report(raw, engine):
    """Never forward an arbitrary child's strings, extra fields, or input."""
    if (engine not in {"python-socket", "swirl-rust"}
            or not isinstance(raw, dict) or type(raw.get("schema")) is not int
            or raw.get("schema") != 1 or raw.get("engine") != engine
            or raw.get("scope") != "dns_tcp_only" or type(raw.get("ok")) is not bool):
        raise ValueError("DiagnosticOutputInvalid")
    result = {key: raw[key] for key in ("schema", "engine", "scope", "ok")}
    code, stage = raw.get("error_code"), raw.get("failure_stage")
    if ("error_code" not in raw or "failure_stage" not in raw
            or (code is not None and type(code) is not str) or code not in ERRORS
            or (stage is not None and type(stage) is not str)):
        raise ValueError("DiagnosticOutputInvalid")
    expected_stage = (None if code is None else "input" if code in INPUT_ERRORS
                      else "socket_options" if code == "SocketOptions"
                      else "tcp_connect" if code in {"UpstreamAddressLimit", "UpstreamTcpTimeout",
                                                      "UpstreamConnectFailed"} else "dns")
    if stage != expected_stage or raw["ok"] != (code is None):
        raise ValueError("DiagnosticOutputInvalid")
    result.update(error_code=code, failure_stage=stage)
    for key in ("total_budget_ms", "dns_budget_ms", "dns_elapsed_ms", "tcp_elapsed_ms", "total_elapsed_ms",
                "address_count", "ipv4_count", "ipv6_count", "attempted_count", "remaining_count", "peak_pending"):
        value = raw.get(key)
        limit = (MAX_ADDRESSES if key.endswith("_count") else 2 if key == "peak_pending"
                 else MAX_BUDGET_MS if key == "total_budget_ms" else 3000 if key == "dns_budget_ms"
                 else MAX_BUDGET_MS + TIMING_SLACK_MS)
        minimum = 1 if key.endswith("_budget_ms") else 0
        if type(value) is not int or not minimum <= value <= limit:
            raise ValueError("DiagnosticOutputInvalid")
        result[key] = value
    if (result["dns_budget_ms"] > result["total_budget_ms"]
            or result["dns_elapsed_ms"] > result["dns_budget_ms"] + TIMING_SLACK_MS
            or result["total_elapsed_ms"] > result["total_budget_ms"] + TIMING_SLACK_MS
            or result["dns_elapsed_ms"] + result["tcp_elapsed_ms"] > result["total_elapsed_ms"] + 1
            or (raw["ok"] and result["total_elapsed_ms"] > result["total_budget_ms"] + 1)):
        raise ValueError("DiagnosticOutputInvalid")
    result["attempts"] = []
    if not isinstance(raw.get("attempts"), list) or len(raw["attempts"]) > MAX_ADDRESSES:
        raise ValueError("DiagnosticOutputInvalid")
    for ordinal, row in enumerate(raw["attempts"], 1):
        if (not isinstance(row, dict) or row.get("family") not in ("ipv4", "ipv6")
                or type(row.get("outcome")) is not str or row.get("outcome") not in OUTCOMES):
            raise ValueError("DiagnosticOutputInvalid")
        clean = {key: row[key] for key in ("family", "outcome")}
        for key, limit in (("ordinal", MAX_ADDRESSES),
                           ("started_ms", MAX_BUDGET_MS + TIMING_SLACK_MS),
                           ("elapsed_ms", MAX_BUDGET_MS + TIMING_SLACK_MS)):
            value = row.get(key)
            if type(value) is not int or not 0 <= value <= limit:
                raise ValueError("DiagnosticOutputInvalid")
            clean[key] = value
        if (clean["ordinal"] != ordinal
                or clean["started_ms"] + clean["elapsed_ms"] > result["tcp_elapsed_ms"] + 1
                or (result["attempts"] and clean["started_ms"] < result["attempts"][-1]["started_ms"])):
            raise ValueError("DiagnosticOutputInvalid")
        result["attempts"].append(clean)
    successes = sum(row["outcome"] == "success" for row in result["attempts"])
    socket_options_failure = engine == "swirl-rust" and code == "SocketOptions"
    if (result["attempted_count"] != len(result["attempts"])
            or result["address_count"] != result["attempted_count"] + result["remaining_count"]
            or result["address_count"] != result["ipv4_count"] + result["ipv6_count"]
            or successes != int(result["ok"] or socket_options_failure)
            or result["peak_pending"] > min(2, result["attempted_count"])
            or (result["attempted_count"] > 0 and result["peak_pending"] == 0)
            or (stage in {"input", "dns"} and (
                result["address_count"] != 0 or result["tcp_elapsed_ms"] != 0))
            or (stage == "input" and result["total_elapsed_ms"] != 0)):
        raise ValueError("DiagnosticOutputInvalid")
    for family in ("ipv4", "ipv6"):
        if sum(row["family"] == family for row in result["attempts"]) > result[family + "_count"]:
            raise ValueError("DiagnosticOutputInvalid")
    # Millisecond rounding may hide overlap, but cannot justify three intervals
    # that visibly overlap, or a peak lower than that observed overlap.
    events = []
    for row in result["attempts"]:
        if row["elapsed_ms"]:
            events.extend([(row["started_ms"], 1), (row["started_ms"] + row["elapsed_ms"], -1)])
    active = 0
    for _, delta in sorted(events):
        active += delta
        if active > result["peak_pending"]:
            raise ValueError("DiagnosticOutputInvalid")
    return result


def compare(rust_binary, host, port):
    """Two serial diagnostic processes share <=10s; no subscription HTTP here."""
    started = time.monotonic()
    deadline = started + 10
    result = {"scope": "paired-dns-tcp-only", "sample_budget_ms": 10000,
              "dns_budget_ms": 3000, "per_engine_dns_budget_ms": 1500,
              "maximum_simultaneous_tcp": 2, "checks": {}}
    commands = [("python-socket", [sys.executable, str(Path(__file__).resolve())]),
                ("swirl-rust", [str(rust_binary)])]
    for engine, command in commands:
        # Reserve process cleanup time within, not after, the shared budget.
        budget = min(4750, int((deadline - time.monotonic() - 0.25) * 1000))
        if budget <= 0:
            result["checks"][engine] = {"ok": False, "error_code": "DiagnosticProcessTimeout"}
            continue
        request = {"host": host, "port": port, "total_budget_ms": budget,
                   "dns_budget_ms": min(1500, budget)}
        try:
            process = subprocess.run(command, input=json.dumps(request).encode(),
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     timeout=max(0.001, min(budget / 1000 + 0.15,
                                                          deadline - time.monotonic() - 0.1)))
            if len(process.stdout) > MAX_INPUT:
                raise ValueError("DiagnosticOutputInvalid")
            checked = safe_report(load_json(process.stdout), engine)
            # The Python CLI uses 1 for a reported negative result; Rust always
            # returns 0 after writing its report. A crash after printing a valid
            # JSON object must not become a successful connectivity check.
            expected_exit = 1 if engine == "python-socket" and not checked["ok"] else 0
            if process.returncode != expected_exit:
                result["checks"][engine] = {"ok": False, "error_code": "DiagnosticProcessFailed"}
                continue
            if checked["failure_stage"] != "input" and (
                    checked["total_budget_ms"] != budget
                    or checked["dns_budget_ms"] != min(1500, budget)):
                raise ValueError("DiagnosticOutputInvalid")
            if time.monotonic() > deadline:
                result["checks"][engine] = {"ok": False, "error_code": "DiagnosticProcessTimeout"}
                continue
            result["checks"][engine] = checked
        except subprocess.TimeoutExpired:
            result["checks"][engine] = {"ok": False, "error_code": "DiagnosticProcessTimeout"}
        except (ValueError, TypeError, OSError):
            result["checks"][engine] = {"ok": False, "error_code": "DiagnosticOutputInvalid"}
    values = [row.get("ok") is True for row in result["checks"].values()]
    complete = all("attempted_count" in row and row.get("failure_stage") != "input"
                   for row in result["checks"].values())
    result["agreement"] = ("inconclusive" if not complete else "both_connected" if all(values)
                           else "different_outcomes" if any(values) else "both_failed")
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result


def main():
    try:
        payload = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(payload) > MAX_INPUT:
            raise ValueError()
        report = diagnose_python(load_json(payload))
    except Exception:
        report = empty_report()
        report.update(error_code="InvalidDiagnosticInput", failure_stage="input")
    print(json.dumps(report, separators=(",", ":")), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
