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
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            endpoint = reserved.getsockname()
            report = DIAG.diagnose_python(
                {"host": "private.invalid", "port": endpoint[1], "total_budget_ms": 500},
                resolver=lambda *args, **kwargs: [row(socket.AF_INET, endpoint)])
        self.assertFalse(report["ok"])
        self.assertEqual(report["attempts"][0]["outcome"], "refused")
        self.assertEqual(report["error_code"], "UpstreamConnectFailed")
        self.assertLess(report["total_elapsed_ms"], 500)

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
        with socket.socket() as reserved, socket.socket() as listener:
            reserved.bind(("127.0.0.1", 0))
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(1)
            rows = [row(socket.AF_INET, reserved.getsockname()),
                    row(socket.AF_INET, listener.getsockname()),
                    row(socket.AF_INET, listener.getsockname())]
            report = DIAG.diagnose_python(
                {"host": "private.invalid", "port": 1, "total_budget_ms": 200},
                resolver=lambda *args, **kwargs: rows)
            self.assertTrue(report["ok"])
            self.assertEqual(report["address_count"], 2)
            self.assertEqual([entry["outcome"] for entry in report["attempts"]], ["refused", "success"])
            self.assertLessEqual(report["peak_pending"], 2)
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
import importlib.util, json, threading
spec = importlib.util.spec_from_file_location("diagnostic", {str(SCRIPT)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def stalled(*args, **kwargs):
    threading.Event().wait()
report = module.diagnose_python({{"host":"fixture.invalid","port":443,
    "total_budget_ms":100,"dns_budget_ms":30}}, resolver=stalled)
print(json.dumps(report), flush=True)
'''
        process = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=3)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(process.stderr, b"")
        report = DIAG.safe_report(json.loads(process.stdout), "python-socket")
        self.assertEqual(report["error_code"], "UpstreamDnsTimeout")
        self.assertEqual(report["attempted_count"], 0)

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
