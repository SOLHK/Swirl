"""Independent sockets, cancellation, accounting and privacy for TCP diagnostics."""
import importlib.util
import copy
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/Diagnose-NativeConnectivity.py"
SPEC = importlib.util.spec_from_file_location("swirl_connectivity", SCRIPT)
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)
RUST = Path(os.environ.get("SWIRL_RUST_DIAGNOSTIC", str(
    ROOT / "core/target/release" / ("swirl-diagnose.exe" if os.name == "nt" else "swirl-diagnose"))))


def row(family, address):
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)


def successful_report(engine="python-socket", total=1000, dns=300):
    result = DIAG.empty_report(total, dns)
    result.update(engine=engine, ok=True, dns_elapsed_ms=10, tcp_elapsed_ms=20,
                  total_elapsed_ms=30, address_count=1, ipv4_count=1,
                  attempted_count=1, peak_pending=1,
                  attempts=[{"ordinal": 1, "family": "ipv4", "started_ms": 0,
                             "elapsed_ms": 20, "outcome": "success"}])
    return result


class VirtualNetwork:
    """Drive actual scheduler code with socket lifetimes and a monotonic clock."""
    def __init__(self, connect, ready):
        self.now = 0.0
        self.connect = connect
        self.ready = ready
        self.sockets = []
        self.registered = {}
        self.alive = 0
        self.peak = 0

    def socket(self, *_):
        network = self

        class Endpoint:
            def __init__(self):
                self.ordinal = len(network.sockets) + 1
                self.closed = False
                self.status_reads = 0
                network.sockets.append(self)
                network.alive += 1
                network.peak = max(network.peak, network.alive)

            def setblocking(self, _):
                pass

            def connect_ex(self, _):
                return network.connect(network, self)

            def getsockopt(self, *_):
                self.status_reads += 1
                return 0

            def close(self):
                if not self.closed:
                    self.closed = True
                    network.alive -= 1

        return Endpoint()

    def register(self, sock, events):
        self.registered[sock] = events

    def unregister(self, sock):
        self.registered.pop(sock)

    def select(self, timeout):
        return [(types.SimpleNamespace(fileobj=sock), 2) for sock in self.ready(self, timeout)]

    def close(self):
        if self.registered:
            raise AssertionError("registered sockets leaked")

    def diagnose(self, request, rows):
        with patch.object(DIAG.time, "monotonic", side_effect=lambda: self.now), \
                patch.object(DIAG.socket, "socket", self.socket), \
                patch.object(DIAG.selectors, "DefaultSelector", return_value=self):
            return DIAG.diagnose_python(request, resolver=lambda *args, **kwargs: rows)


class ConnectivityDiagnostics(unittest.TestCase):
    def test_python_cli_actual_tcp_without_application_data(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(2)
            request = {"host": "127.0.0.1", "port": listener.getsockname()[1],
                       "total_budget_ms": 1000, "dns_budget_ms": 300}
            result = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(request),
                                    text=True, capture_output=True, timeout=3)
            report = DIAG.safe_report(json.loads(result.stdout), "python-socket")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(report["ok"])
            self.assertEqual(report["ipv4_count"], 1)
            self.assertEqual(report["attempted_count"], 1)
            self.assertEqual(report["remaining_count"], 0)
            self.assertNotIn("127.0.0.1", result.stdout)
            self.assertNotIn('"port"', result.stdout)
            with listener.accept()[0] as peer:
                peer.settimeout(1)
                self.assertEqual(peer.recv(1), b"")

    def test_refusal_is_distinct_and_does_not_consume_full_budget(self):
        def unexpected_wait(*_):
            self.fail("An immediate refusal must not wait for a timer")
        for code in (errno.ECONNREFUSED, 10061):
            with self.subTest(error_code=code):
                network = VirtualNetwork(lambda *_: code, unexpected_wait)
                immediate = network.diagnose(
                    {"host": "fixture.invalid", "port": 1, "total_budget_ms": 500},
                    [row(socket.AF_INET, ("127.0.0.1", 1))])
                self.assertFalse(immediate["ok"])
                self.assertEqual(immediate["attempts"][0]["outcome"], "refused")
                self.assertEqual(immediate["error_code"], "UpstreamConnectFailed")
                self.assertEqual(immediate["total_elapsed_ms"], 0)
                self.assertEqual(network.peak, 1)
                self.assertEqual(network.alive, 0)
                DIAG.safe_report(immediate, "python-socket")

        # A bound, non-listening socket is not a portable refusal fixture:
        # Windows and macOS can leave its incoming connection pending.
        with socket.socket() as closed_listener:
            closed_listener.bind(("127.0.0.1", 0))
            closed_listener.listen()
            endpoint = closed_listener.getsockname()
        # Observe the OS separately: localhost refusal notification can be
        # delayed on Windows (https://github.com/python/cpython/issues/85480).
        # Both probes have a fixed three-second test deadline; neither changes
        # the production scheduler, and an OS timeout remains a real failure.
        reference_started = time.monotonic()
        with socket.socket() as reference:
            remaining = 3 - (time.monotonic() - reference_started)
            if remaining <= 0:
                reference_outcome = "timeout"
            else:
                reference.settimeout(remaining)
                try:
                    reference.connect(endpoint)
                    reference_outcome = "success"
                except ConnectionRefusedError:
                    reference_outcome = "refused"
                except TimeoutError:
                    reference_outcome = "timeout"
                except OSError:
                    reference_outcome = "other"
        reference_elapsed_ms = int((time.monotonic() - reference_started) * 1000)
        report = DIAG.diagnose_python(
            {"host": "private.invalid", "port": endpoint[1], "total_budget_ms": 3000},
            resolver=lambda *args, **kwargs: [row(socket.AF_INET, endpoint)])
        print("LOOPBACK REFUSAL OBSERVATION: " + json.dumps({
            "per_probe_budget_ms": 3000, "os_outcome": reference_outcome,
            "os_elapsed_ms": reference_elapsed_ms,
            "diagnostic_outcomes": [entry["outcome"] for entry in report["attempts"]],
            "diagnostic_elapsed_ms": report["total_elapsed_ms"]}), flush=True)
        self.assertEqual(reference_outcome, "refused",
                         "OS refusal was unavailable within the fixed observation deadline")
        self.assertLess(reference_elapsed_ms, 3000)
        self.assertFalse(report["ok"])
        self.assertEqual(report["attempts"][0]["outcome"], "refused")
        self.assertEqual(report["error_code"], "UpstreamConnectFailed")
        self.assertLess(report["total_elapsed_ms"], 3000)
        DIAG.safe_report(report, "python-socket")

    def test_independent_dns_timeout_prevents_all_tcp_work(self):
        def stalled(*args, **kwargs):
            time.sleep(0.08)
            return [row(socket.AF_INET, ("127.0.0.1", 1))]
        started = time.monotonic()
        report = DIAG.diagnose_python(
            {"host": "private.invalid", "port": 1, "dns_budget_ms": 20, "total_budget_ms": 60},
            resolver=stalled)
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertEqual(report["error_code"], "UpstreamDnsTimeout")
        self.assertEqual(report["failure_stage"], "dns")
        self.assertEqual(report["attempted_count"], 0)
        self.assertEqual(report["tcp_elapsed_ms"], 0)

    def test_refused_first_address_immediately_falls_back(self):
        def unexpected_wait(*_):
            self.fail("An immediate refusal must open the next slot without waiting")
        network = VirtualNetwork(
            lambda _, sock: errno.ECONNREFUSED if sock.ordinal == 1 else 0, unexpected_wait)
        immediate = network.diagnose(
            {"host": "fixture.invalid", "port": 1, "total_budget_ms": 200},
            [row(socket.AF_INET, ("127.0.0.1", port)) for port in (1, 2)])
        self.assertTrue(immediate["ok"])
        self.assertEqual([entry["outcome"] for entry in immediate["attempts"]], ["refused", "success"])
        self.assertEqual(immediate["attempts"][1]["started_ms"], 0)
        self.assertEqual(network.peak, 1)
        self.assertEqual(network.alive, 0)
        DIAG.safe_report(immediate, "python-socket")

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(1)
            # Allocate both endpoints before closing the refusal listener, so
            # the accepting listener cannot reuse its port.
            with socket.socket() as closed_listener:
                closed_listener.bind(("127.0.0.1", 0))
                closed_listener.listen()
                refused_endpoint = closed_listener.getsockname()
            rows = [row(socket.AF_INET, refused_endpoint),
                    row(socket.AF_INET, listener.getsockname()),
                    row(socket.AF_INET, listener.getsockname())]
            # The real OS may report refusal after the existing 250ms stagger;
            # the live second endpoint must still win and close a pending loser.
            report = DIAG.diagnose_python(
                {"host": "private.invalid", "port": 1, "total_budget_ms": 1000},
                resolver=lambda *args, **kwargs: rows)
            print("LOOPBACK FALLBACK OBSERVATION: " + json.dumps({
                "budget_ms": 1000, "elapsed_ms": report["total_elapsed_ms"],
                "outcomes": [entry["outcome"] for entry in report["attempts"]],
                "started_ms": [entry["started_ms"] for entry in report["attempts"]],
                "peak_pending": report["peak_pending"]}), flush=True)
            self.assertTrue(report["ok"])
            self.assertEqual(report["address_count"], 2)
            self.assertEqual(report["attempted_count"], 2)
            self.assertEqual(report["remaining_count"], 0)
            self.assertIn(report["attempts"][0]["outcome"], ("refused", "cancelled"))
            self.assertEqual(report["attempts"][1]["outcome"], "success")
            if report["attempts"][0]["outcome"] == "cancelled":
                self.assertGreaterEqual(report["attempts"][1]["started_ms"], 249)
                self.assertEqual(report["peak_pending"], 2)
            self.assertLessEqual(report["peak_pending"], 2)
            DIAG.safe_report(report, "python-socket")
            with listener.accept()[0] as peer:
                peer.settimeout(1)
                self.assertEqual(peer.recv(1), b"")

    def test_address_family_interleaving_and_limit(self):
        rows = [row(socket.AF_INET6, ("::1", 1, 0, 0)),
                row(socket.AF_INET6, ("::2", 1, 0, 0)),
                row(socket.AF_INET, ("127.0.0.1", 1))]
        self.assertEqual([entry[0] for entry in DIAG.ordered_addresses(rows)],
                         [socket.AF_INET6, socket.AF_INET, socket.AF_INET6])
        report = DIAG.diagnose_python(
            {"host": "private.invalid", "port": 1},
            resolver=lambda *args, **kwargs: [
                row(socket.AF_INET, ("127.0.0.1", port)) for port in range(1, 18)])
        self.assertEqual(report["error_code"], "UpstreamAddressLimit")
        self.assertEqual(report["attempted_count"], 0)

    def test_error_classification_and_whitelist_never_echo_private_fields(self):
        self.assertEqual(DIAG.error_category(10061), "refused")
        self.assertEqual(DIAG.error_category(10060), "timeout")
        self.assertEqual(DIAG.error_category(10051), "unreachable")
        report = successful_report()
        report.update(host="private-marker.invalid", port=43210, password="private-marker")
        safe = DIAG.safe_report(report, "python-socket")
        self.assertNotIn("private-marker", json.dumps(safe))
        self.assertNotIn("43210", json.dumps(safe))
        with self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
            DIAG.safe_report({**report, "attempts": [{"outcome": "private-marker"}]}, "python-socket")
        for changes in ({"error_code": "private-marker.invalid"},
                        {"failure_stage": "private-marker"}, {"error_code": ["private-marker"]}):
            with self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
                DIAG.safe_report({**report, **changes}, "python-socket")

    def test_selector_readiness_after_total_deadline_cannot_succeed(self):
        def late(network, timeout):
            network.now += timeout + 0.01
            return [network.sockets[0]]
        network = VirtualNetwork(lambda *_: errno.EINPROGRESS, late)
        report = network.diagnose(
            {"host": "fixture.invalid", "port": 443, "total_budget_ms": 100},
            [row(socket.AF_INET, ("127.0.0.1", 443))])
        self.assertFalse(report["ok"])
        self.assertEqual(report["error_code"], "UpstreamTcpTimeout")
        self.assertEqual(report["attempts"][0]["outcome"], "timeout")
        self.assertGreaterEqual(report["total_elapsed_ms"], 109)
        self.assertEqual(network.sockets[0].status_reads, 0)
        self.assertEqual(network.alive, 0)
        self.assertEqual(network.peak, 1)
        DIAG.safe_report(report, "python-socket")

    def test_expired_slot_readiness_is_ignored_and_third_address_gets_a_slot(self):
        def ready(network, timeout):
            network.now += timeout
            if network.now < 2:
                return []
            network.now += 0.01
            return [network.sockets[0]]
        network = VirtualNetwork(
            lambda _, sock: 0 if sock.ordinal == 3 else errno.EINPROGRESS, ready)
        report = network.diagnose(
            {"host": "fixture.invalid", "port": 443, "total_budget_ms": 5000},
            [row(socket.AF_INET, ("127.0.0.1", port)) for port in (1, 2, 3)])
        self.assertTrue(report["ok"])
        self.assertEqual([a["outcome"] for a in report["attempts"]],
                         ["timeout", "cancelled", "success"])
        self.assertEqual(network.sockets[0].status_reads, 0)
        self.assertEqual(network.alive, 0)
        self.assertEqual(network.peak, 2)
        self.assertEqual(report["peak_pending"], 2)
        self.assertEqual(report["attempted_count"], 3)
        self.assertEqual(report["remaining_count"], 0)
        DIAG.safe_report(report, "python-socket")

    def test_immediate_connects_record_elapsed_time_and_live_socket_peak(self):
        for code, outcome in ((0, "success"), (errno.ECONNREFUSED, "refused")):
            with self.subTest(outcome=outcome):
                def connect(network, _):
                    network.now += 0.012
                    return code
                network = VirtualNetwork(connect, lambda *_: [])
                report = network.diagnose(
                    {"host": "fixture.invalid", "port": 443, "total_budget_ms": 100},
                    [row(socket.AF_INET, ("127.0.0.1", 443))])
                self.assertEqual(report["attempts"][0]["outcome"], outcome)
                self.assertGreaterEqual(report["attempts"][0]["elapsed_ms"], 11)
                self.assertEqual(report["peak_pending"], 1)
                self.assertEqual(network.alive, 0)
                DIAG.safe_report(report, "python-socket")

    def test_dns_worker_startup_consumes_absolute_dns_deadline(self):
        clock = [0.0]

        class DelayedStartup:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                clock[0] += 0.02
                self.target(*self.args)

        with patch.object(DIAG.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(DIAG.threading, "Thread", DelayedStartup), \
                patch.object(DIAG.socket, "socket") as connect:
            report = DIAG.diagnose_python(
                {"host": "fixture.invalid", "port": 443, "dns_budget_ms": 10,
                 "total_budget_ms": 100},
                resolver=lambda *args, **kwargs: [row(socket.AF_INET, ("127.0.0.1", 443))])
        connect.assert_not_called()
        self.assertEqual(report["error_code"], "UpstreamDnsTimeout")
        self.assertEqual(report["dns_elapsed_ms"], 20)
        self.assertEqual(report["attempted_count"], 0)

    def test_permanently_stalled_dns_worker_does_not_hold_process_open(self):
        code = f'''
import importlib.util, json, threading, time
spec = importlib.util.spec_from_file_location("diagnostic", {str(SCRIPT)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def stalled(*args, **kwargs):
    threading.Event().wait()
observed = {{}}
original_start = threading.Thread.start
original_get = module.queue.Queue.get
def measured_start(self):
    start = time.monotonic()
    try:
        return original_start(self)
    finally:
        observed["worker_start_ms"] = int((time.monotonic() - start) * 1000)
def measured_get(self, *args, **kwargs):
    start = time.monotonic()
    try:
        return original_get(self, *args, **kwargs)
    finally:
        observed["queue_wait_ms"] = int((time.monotonic() - start) * 1000)
threading.Thread.start = measured_start
module.queue.Queue.get = measured_get
report = module.diagnose_python({{"host":"fixture.invalid","port":443,
    "total_budget_ms":100,"dns_budget_ms":30}}, resolver=stalled)
report.update(observed)
print(json.dumps(report), flush=True)
'''
        process = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=3)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(process.stderr, b"")
        raw = json.loads(process.stdout)
        # This child uses only the synthetic fixture above. Preserve the measured
        # timing on failure without printing any target or arbitrary child text.
        print("STALLED DNS OBSERVATION: " + json.dumps({
            key: raw.get(key) for key in (
                "total_budget_ms", "dns_budget_ms", "dns_elapsed_ms",
                "tcp_elapsed_ms", "total_elapsed_ms", "attempted_count",
                "worker_start_ms", "queue_wait_ms")
            if type(raw.get(key)) is int
        }), flush=True)
        self.assertEqual(raw["error_code"], "UpstreamDnsTimeout")
        self.assertEqual(raw["failure_stage"], "dns")
        self.assertIs(raw["ok"], False)
        self.assertEqual(raw["attempted_count"], 0)
        self.assertEqual(raw["tcp_elapsed_ms"], 0)
        self.assertEqual(raw["attempts"], [])
        self.assertEqual(raw["total_elapsed_ms"], raw["dns_elapsed_ms"])
        # This is the process-lifecycle check: the real stalled worker must not
        # prevent exit within the unchanged parent timeout. macOS can wake a
        # timed condition wait late (158 ms observed for a 30 ms deadline).
        # A late measurement must be rejected, never clipped or called valid.
        if raw["dns_elapsed_ms"] > raw["dns_budget_ms"] + DIAG.TIMING_SLACK_MS:
            with self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
                DIAG.safe_report(raw, "python-socket")
        else:
            report = DIAG.safe_report(raw, "python-socket")
            self.assertEqual(report["error_code"], "UpstreamDnsTimeout")

    def test_late_dns_wait_never_dials_or_becomes_valid_budget_evidence(self):
        # The deadline/validation contract is deterministic even when the OS
        # scheduler suspends a thread beyond its requested wait. Exercise both
        # an empty queue and a DNS result delivered after the absolute deadline.
        for answer_arrives in (False, True):
            clock = [0.0]
            def delayed_get(*args, **kwargs):
                clock[0] = 0.158
                if not answer_arrives:
                    raise DIAG.queue.Empty()
                return True, [row(socket.AF_INET, ("127.0.0.1", 443))]
            with self.subTest(answer_arrives=answer_arrives), \
                    patch.object(DIAG.time, "monotonic", side_effect=lambda: clock[0]), \
                    patch.object(DIAG.queue.Queue, "get", side_effect=delayed_get), \
                    patch.object(DIAG.threading, "Thread"), \
                    patch.object(DIAG.socket, "socket") as connect:
                report = DIAG.diagnose_python({"host": "fixture.invalid", "port": 443,
                                              "total_budget_ms": 100, "dns_budget_ms": 30})
            connect.assert_not_called()
            self.assertEqual(report["error_code"], "UpstreamDnsTimeout")
            self.assertEqual(report["dns_elapsed_ms"], 158)
            self.assertEqual(report["total_elapsed_ms"], 158)
            self.assertEqual(report["attempted_count"], 0)
            self.assertEqual(report["attempts"], [])
            with self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
                DIAG.safe_report(report, "python-socket")

    def test_report_validator_rejects_inconsistent_budgets_and_trace(self):
        changes = [
            {"schema": True}, {"total_budget_ms": 10001}, {"dns_budget_ms": 3001},
            {"dns_budget_ms": 0}, {"dns_budget_ms": 1001},
            {"total_elapsed_ms": 29 - 1}, {"dns_elapsed_ms": 500},
            {"attempted_count": 0}, {"remaining_count": 1}, {"ipv6_count": 1},
            {"peak_pending": 0}, {"peak_pending": 2},
            {"ok": False}, {"error_code": "UpstreamTcpTimeout", "failure_stage": "tcp_connect"},
        ]
        for values in changes:
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
                DIAG.safe_report({**successful_report(), **values}, "python-socket")
        for values in ({"ordinal": 0}, {"ordinal": 2}, {"started_ms": 22},
                       {"elapsed_ms": 22}, {"family": "ipv6"}, {"outcome": ["private-marker"]}):
            report = successful_report()
            report["attempts"][0].update(values)
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
                DIAG.safe_report(report, "python-socket")

    def test_report_validator_rejects_three_overlapping_attempts(self):
        report = successful_report()
        report.update(address_count=3, ipv4_count=3, attempted_count=3, peak_pending=2)
        report["attempts"] = [{"ordinal": index, "family": "ipv4", "started_ms": 0,
                               "elapsed_ms": 20, "outcome": "success" if index == 3 else "cancelled"}
                              for index in range(1, 4)]
        with self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
            DIAG.safe_report(report, "python-socket")

    def test_report_validator_rejects_reordered_or_duplicate_attempt_ordinals(self):
        report = successful_report()
        report.update(address_count=2, ipv4_count=2, attempted_count=2, peak_pending=2)
        report["attempts"] = [
            {"ordinal": 1, "family": "ipv4", "started_ms": 0, "elapsed_ms": 20, "outcome": "cancelled"},
            {"ordinal": 2, "family": "ipv4", "started_ms": 10, "elapsed_ms": 10, "outcome": "success"},
        ]
        DIAG.safe_report(report, "python-socket")
        for entries in [list(reversed(report["attempts"])),
                        [report["attempts"][0], {**report["attempts"][1], "ordinal": 1}],
                        [{**report["attempts"][0], "started_ms": 10, "elapsed_ms": 10},
                         {**report["attempts"][1], "started_ms": 0, "elapsed_ms": 20}]]:
            invalid = copy.deepcopy(report)
            invalid["attempts"] = entries
            with self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
                DIAG.safe_report(invalid, "python-socket")

    def test_socket_options_error_keeps_tcp_success_but_not_diagnostic_success(self):
        report = successful_report("swirl-rust")
        report.update(ok=False, error_code="SocketOptions", failure_stage="socket_options")
        safe = DIAG.safe_report(report, "swirl-rust")
        self.assertFalse(safe["ok"])
        self.assertEqual(safe["attempts"][0]["outcome"], "success")
        report["error_code"] = "UpstreamConnectFailed"
        report["failure_stage"] = "tcp_connect"
        with self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
            DIAG.safe_report(report, "swirl-rust")

    def test_native_typed_tcp_failures_keep_their_stage_and_closed_output_contract(self):
        for code, outcome in (
                ("UpstreamConnectionRefused", "refused"),
                ("UpstreamConnectionReset", "other"),
                ("UpstreamConnectionAborted", "other"),
                ("UpstreamNetworkUnreachable", "unreachable"),
                ("UpstreamPermissionDenied", "other")):
            with self.subTest(code=code):
                report = successful_report("swirl-rust")
                report.update(ok=False, error_code=code, failure_stage="tcp_connect",
                              private_endpoint="private-marker.invalid")
                report["attempts"][0]["outcome"] = outcome
                safe = DIAG.safe_report(report, "swirl-rust")
                self.assertEqual((safe["error_code"], safe["failure_stage"]), (code, "tcp_connect"))
                self.assertNotIn("private-marker", json.dumps(safe))
                report["failure_stage"] = "dns"
                with self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
                    DIAG.safe_report(report, "swirl-rust")
        report["failure_stage"] = "tcp_connect"
        report["error_code"] = "UpstreamFuturePrivateMessage"
        with self.assertRaisesRegex(ValueError, "^DiagnosticOutputInvalid$"):
            DIAG.safe_report(report, "swirl-rust")

    def test_duplicate_fields_are_rejected_before_private_input_can_dial(self):
        payload = b'{"host":"fixture.invalid","host":"private-marker.invalid","port":443}'
        process = subprocess.run([sys.executable, str(SCRIPT)], input=payload,
                                 capture_output=True, timeout=3)
        self.assertEqual(process.returncode, 1)
        report = DIAG.safe_report(json.loads(process.stdout), "python-socket")
        self.assertEqual(report["error_code"], "InvalidDiagnosticInput")
        self.assertEqual(report["attempted_count"], 0)
        self.assertNotIn(b"private-marker", process.stdout + process.stderr)

    def test_invalid_input_never_dials(self):
        inputs = [
            {"host": "private.invalid", "port": True},
            {"host": "private.invalid", "port": 443, "total_budget_ms": 10001},
            {"host": "private.invalid", "port": 443, "dns_budget_ms": 3001},
            {"host": "private.invalid", "port": 443, "password": "private-marker"},
        ]
        for request in inputs:
            with self.subTest(request=request), patch.object(DIAG.threading, "Thread") as thread:
                report = DIAG.diagnose_python(request)
                self.assertEqual(report["error_code"], "InvalidDiagnosticInput")
                thread.assert_not_called()

    @unittest.skipUnless(RUST.exists(), "native diagnostic binary not built")
    def test_native_refusal_keeps_typed_code_through_the_output_validator(self):
        with socket.socket() as closed_listener:
            closed_listener.bind(("127.0.0.1", 0))
            closed_listener.listen()
            port = closed_listener.getsockname()[1]
        request = {"host": "127.0.0.1", "port": port,
                   "total_budget_ms": 3000, "dns_budget_ms": 300}
        process = subprocess.run([str(RUST)], input=json.dumps(request),
                                 text=True, capture_output=True, timeout=4)
        report = DIAG.safe_report(json.loads(process.stdout), "swirl-rust")
        self.assertFalse(report["ok"])
        self.assertEqual(report["error_code"], "UpstreamConnectionRefused")
        self.assertEqual(report["failure_stage"], "tcp_connect")
        self.assertEqual([attempt["outcome"] for attempt in report["attempts"]], ["refused"])
        self.assertNotIn("127.0.0.1", process.stdout)
        self.assertNotIn('"port"', process.stdout)

    @unittest.skipUnless(RUST.exists(), "native diagnostic binary not built")
    def test_two_real_implementations_share_budget_and_close_without_payload(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(2)
            started = time.monotonic()
            report = DIAG.compare(RUST, "127.0.0.1", listener.getsockname()[1])
            self.assertLess(time.monotonic() - started, 10)
            self.assertEqual(report["agreement"], "both_connected")
            for engine in ("python-socket", "swirl-rust"):
                self.assertTrue(report["checks"][engine]["ok"], report)
                self.assertLessEqual(report["checks"][engine]["peak_pending"], 2)
                with listener.accept()[0] as peer:
                    peer.settimeout(1)
                    self.assertEqual(peer.recv(1), b"")
            self.assertNotIn("127.0.0.1", json.dumps(report))

    @unittest.skipUnless(RUST.exists(), "native diagnostic binary not built")
    def test_nonzero_exit_after_valid_success_json_is_not_connectivity_success(self):
        original_run = subprocess.run
        for bad_exit in (1, 7):
            with self.subTest(exit_code=bad_exit), socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                listener.settimeout(2)
                calls = []

                def run(command, **kwargs):
                    calls.append(command)
                    if len(calls) == 1:
                        request = json.loads(kwargs["input"])
                        payload = json.dumps(successful_report(
                            total=request["total_budget_ms"], dns=request["dns_budget_ms"]))
                        code = f"import sys; print({payload!r}, flush=True); raise SystemExit({bad_exit})"
                        return original_run([sys.executable, "-c", code], **kwargs)
                    return original_run(command, **kwargs)

                with patch.object(DIAG.subprocess, "run", side_effect=run):
                    report = DIAG.compare(RUST, "127.0.0.1", listener.getsockname()[1])
                self.assertEqual(report["checks"]["python-socket"],
                                 {"ok": False, "error_code": "DiagnosticProcessFailed"})
                self.assertTrue(report["checks"]["swirl-rust"]["ok"])
                self.assertEqual(report["agreement"], "inconclusive")
                with listener.accept()[0] as peer:
                    peer.settimeout(1)
                    self.assertEqual(peer.recv(1), b"")

    @unittest.skipUnless(RUST.exists(), "native diagnostic binary not built")
    def test_hung_first_child_is_reaped_before_second_and_sample_stays_within_ten_seconds(self):
        original_run = subprocess.run
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener:
            port_file = Path(directory) / "synthetic-child-port.txt"
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(2)
            code = f'''
import pathlib, socket, time
with socket.socket() as held:
    held.bind(("127.0.0.1", 0))
    held.listen()
    pathlib.Path({str(port_file)!r}).write_text(str(held.getsockname()[1]), encoding="ascii")
    time.sleep(30)
'''
            requests = []
            confirmed_reaped = []

            def run(command, **kwargs):
                requests.append(json.loads(kwargs["input"]))
                if len(requests) == 1:
                    return original_run([sys.executable, "-c", code], **kwargs)
                # The first process held this exclusive listener while hung.
                # Successful rebinding proves its socket was closed before the
                # real Rust process is even launched, not just reported timed out.
                self.assertTrue(port_file.exists())
                port = int(port_file.read_text(encoding="ascii"))
                with socket.socket() as reclaimed:
                    reclaimed.bind(("127.0.0.1", port))
                confirmed_reaped.append(True)
                return original_run(command, **kwargs)

            started = time.monotonic()
            with patch.object(DIAG.subprocess, "run", side_effect=run):
                report = DIAG.compare(RUST, "127.0.0.1", listener.getsockname()[1])
            self.assertLess(time.monotonic() - started, 10)
            self.assertLess(report["elapsed_ms"], 10000)
            self.assertEqual(confirmed_reaped, [True])
            self.assertEqual(len(requests), 2)
            self.assertLessEqual(sum(request["dns_budget_ms"] for request in requests), 3000)
            self.assertLessEqual(sum(request["total_budget_ms"] for request in requests), 10000)
            self.assertEqual(report["checks"]["python-socket"],
                             {"ok": False, "error_code": "DiagnosticProcessTimeout"})
            self.assertTrue(report["checks"]["swirl-rust"]["ok"])
            self.assertEqual(report["agreement"], "inconclusive")
            with listener.accept()[0] as peer:
                peer.settimeout(1)
                self.assertEqual(peer.recv(1), b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
