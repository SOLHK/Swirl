"""Real synthetic OS-child/transport acceptance; never real provider traffic."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import PrivateSubscriptionBudget as budget
import PrivateSubscriptionProcess as process
import PrivateSubscriptionSupervisor as supervisor

REPORTS = []
IDENTITY = None


def reservation(ledger, node=1, workload="upload_until_stop"):
    return ledger.reserve_supervised(node, 65536, 1, 2000,
        config_fingerprint=hashlib.sha256(str(node).encode()).hexdigest(), source_sha="1" * 40,
        worker_sha256="2" * 64, build_id="synthetic-test", nonce=secrets.token_hex(32), workload=workload)


class SyntheticLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "budget"

    def tearDown(self):
        self.temp.cleanup()

    def test_domain_never_relabels_or_invents_provider_baseline(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            report = ledger.summary()
            self.assertIsNone(report["baselineUsed"])
            self.assertIsNone(report["billingDelta"])
            self.assertEqual(report["accountingDomain"], budget.SYNTHETIC_DOMAIN)
            for action in (lambda: ledger.initialize(), lambda: ledger.observe_provider("upload=0;download=0;total=100000000000"),
                           lambda: ledger.reserve_offline(1), ledger.require_live_ready):
                with self.assertRaises(budget.BudgetError):
                    action()
        other = self.path.with_name("prior-offline-history")
        with budget.Ledger(other) as ledger:
            ledger.initialize("upload=100;download=200;total=100000000000")
            old = ledger.path.read_bytes()
            with self.assertRaises(budget.BudgetError):
                ledger.initialize_synthetic()
            with self.assertRaisesRegex(budget.BudgetError, "SyntheticLedgerRequired"):
                reservation(ledger)
            self.assertEqual(ledger.path.read_bytes(), old)

    def test_residual_hold_identity_and_fingerprint_survive_reopen(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            ticket = reservation(ledger)
            ledger.bind_supervised_grant(ticket, "a" * 64)
            ledger.retain_supervised(ticket, "ChildExitUnconfirmed")
            before = ledger.summary()
            history = ledger.data["history"].copy()
        with budget.Ledger(self.path) as ledger:
            self.assertEqual(ledger.summary(), before)
            self.assertEqual(ledger.data["history"], history)
            self.assertEqual(before["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)
            self.assertEqual(before["localTotalsScope"], "confirmed-settled-socket-counts")
            with self.assertRaisesRegex(budget.BudgetError, "ConfigurationAlreadyAttempted"):
                reservation(ledger)
            with self.assertRaisesRegex(budget.BudgetError, "AccountingDomainMismatch"):
                ledger.finish_offline(ticket, quiescent=True)

    def test_only_three_full_reservations_can_compete(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            def attempt(node):
                try:
                    return reservation(ledger, node)
                except budget.BudgetError as error:
                    return str(error)
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(attempt, range(1, 9)))
            self.assertEqual(results.count("ConcurrencyLimit"), 5)
            self.assertEqual(ledger.summary()["heldBytes"], 3 * (65536 + budget.TCP_RECEIVE_RESERVATION))

    def test_guard_and_exit_json_cannot_fake_proof(self):
        plan = budget.tcp_plan(512, 1, 1000)
        guard = {"byte_limit": 512, "upload": 10, "download": 11, "connection_limit": 1,
                 "connection_attempts": 1, "receive_reservation": 1048576, "timeout_ms": 1000,
                 "timed_out": False, "stopped": True, "shutdown_failures": 0}
        budget.validate_guard_receipt(guard, plan)
        for key, value in (("upload", True), ("download", 1.0), ("connection_attempts", 2),
                           ("receive_reservation", 0), ("timeout_ms", 1001), ("stopped", 1),
                           ("shutdown_failures", 1)):
            with self.subTest(key=key), self.assertRaises(budget.BudgetError):
                budget.validate_guard_receipt({**guard, key: value}, plan)
        with self.assertRaisesRegex(budget.BudgetError, "ProcessExitProofRequired"):
            process.ExitProof(None, 1, "a", 0, "windows-single-process-job")

    def test_live_refuses_before_any_path_or_metadata_access(self):
        output = io.StringIO()
        with mock.patch.object(supervisor.WorkerIdentity, "inspect", side_effect=AssertionError("metadata spawned")), \
             mock.patch.object(supervisor, "Ledger", side_effect=AssertionError("ledger accessed")), \
             contextlib.redirect_stdout(output):
            result = supervisor.main(["--live", "--state-dir", str(self.path), "--worker", "PRIVATE_MARKER"])
        self.assertEqual(result, 2)
        self.assertFalse(self.path.exists())
        self.assertNotIn("PRIVATE_MARKER", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["error"], "AuthenticatedBillingAndWireGuardRequired")

    def test_argument_errors_never_echo_values_or_touch_paths(self):
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(supervisor.WorkerIdentity, "inspect", side_effect=AssertionError("metadata spawned")), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = supervisor.main(["--state-dir", str(self.path), "--worker", "PRIVATE_MARKER",
                                      "--expected-source", "0" * 40, "--workload", "PRIVATE_MARKER"])
        self.assertEqual(result, 2)
        self.assertFalse(self.path.exists())
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(json.loads(output.getvalue()), {"error": "SupervisorArgumentsRejected", "liveReady": False})


class OwnedProcessTests(unittest.TestCase):
    def test_real_child_deadline_cannot_be_renewed_or_asserted_by_child(self):
        started = time.monotonic()
        with process.OwnedProcess([sys.executable, "-c", "import time;time.sleep(30)"], deadline=started + 0.4) as child:
            proof = child.wait(timeout=2)
            self.assertTrue(child.timed_out)
            self.assertTrue(proof.matches(child.pid, child.owner_token))
            self.assertFalse(proof.matches(child.pid, "0" * 64))
            self.assertLess(time.monotonic() - started, 2)
            self.assertTrue(proof.record()["ownedProcessSetEmpty"])

    def test_too_large_deadline_never_spawns(self):
        with mock.patch.object(process.subprocess, "Popen", side_effect=AssertionError("spawned")):
            with self.assertRaisesRegex(budget.BudgetError, "InvalidProcessDeadline"):
                process.OwnedProcess([sys.executable], deadline=time.monotonic() + 8.1)

    @unittest.skipUnless(os.name == "nt", "Windows Job active-process limit")
    def test_windows_job_prevents_a_second_process(self):
        command = ("import subprocess,sys\n"
                   "try:\n p=subprocess.Popen([sys.executable,'-c','pass']);p.wait();print('ESCAPED')\n"
                   "except OSError:\n print('DENIED')\n")
        with process.OwnedProcess([sys.executable, "-c", command], deadline=time.monotonic() + 3) as child:
            proof = child.wait(timeout=3)
            self.assertEqual(child.stdout.read(128).strip(), b"DENIED")
            self.assertEqual(proof.record()["exitCode"], 0)
            self.assertEqual(proof.record()["backend"], "windows-single-process-job")


class RealWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global IDENTITY
        executable = os.environ.get("SWIRL_PRIVATE_WORKER")
        if not executable:
            raise unittest.SkipTest("SWIRL_PRIVATE_WORKER not supplied; no Rust e2e claimed")
        expected = os.environ.get("SWIRL_PRIVATE_EXPECTED_SOURCE")
        IDENTITY = cls.identity = supervisor.WorkerIdentity.inspect(executable, expected)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "budget"
        self.ledger = budget.Ledger(self.path).__enter__()
        self.ledger.initialize_synthetic()
        self.coordinator = supervisor.Supervisor(self.ledger, self.identity)

    def tearDown(self):
        self.ledger.__exit__()
        self.temp.cleanup()

    def run_case(self, workload, **options):
        result = self.coordinator.run(workload, **options)
        REPORTS.append({"test": self.id(), **result})
        return result

    def test_upload_and_download_use_real_guard_bytes(self):
        for ordinal, workload in enumerate(("upload_until_stop", "download_until_stop"), 1):
            report = self.run_case(workload, node=ordinal)
            self.assertTrue(report["settled"], report)
            self.assertEqual(report["outcome"], "QuotaStopped")
            self.assertTrue(report["observedRunning"])
            self.assertEqual(report["guard"]["upload"] + report["guard"]["download"], 65536)
            self.assertEqual(report["guard"]["connection_attempts"], 1)
            self.assertEqual(report["fixture"]["authenticatedConnections"], 1)
            self.assertEqual(report["ledger"]["heldBytes"], 0)
            self.assertIsNone(report["ledger"]["billingDelta"])
            self.assertFalse(report["liveReady"])

    def test_real_core_tls_authenticated_connect_probe_204(self):
        report = self.run_case("core_probe", timeout_ms=4000)
        self.assertTrue(report["settled"], report)
        self.assertEqual(report["outcome"], "CoreProbeSucceeded")
        self.assertEqual(report["fixture"]["httpStatus"], 204)
        self.assertEqual(report["guard"]["connection_attempts"], 2)
        self.assertGreater(report["guard"]["upload"], 0)
        self.assertGreater(report["guard"]["download"], 0)

    def test_stalled_runtime_is_killed_and_full_unknown_hold_survives(self):
        report = self.run_case("stall_runtime_after_connect", timeout_ms=600)
        self.assertFalse(report["settled"])
        self.assertTrue(report["observedRunning"], report)
        self.assertTrue(report["exit"]["ownedProcessSetEmpty"])
        self.assertIsNone(report["guard"])
        self.assertLess(report["parentElapsedMs"], 1800)
        held = 65536 + budget.TCP_RECEIVE_RESERVATION
        self.assertEqual(report["ledger"]["heldBytes"], held)
        self.assertEqual(report["localMeasurement"], "unknown-full-reservation-held")
        self.ledger.__exit__()
        self.ledger.__enter__()
        self.assertEqual(self.ledger.summary()["heldBytes"], held)
        with self.assertRaisesRegex(budget.BudgetError, "ConfigurationAlreadyAttempted"):
            self.coordinator.run("stall_runtime_after_connect", timeout_ms=600)

    def test_cancel_releases_real_sockets_before_settlement(self):
        event = threading.Event()
        stop = threading.Event()
        def cancel_after_actual_running():
            deadline = time.monotonic() + 5
            while not stop.is_set() and time.monotonic() < deadline:
                with self.ledger.mutex:
                    active = any(h["phase"] == "active" for h in self.ledger.data["history"].values())
                if active:
                    stop.wait(0.05)
                    event.set()
                    return
                stop.wait(0.005)
        timer = threading.Thread(target=cancel_after_actual_running, daemon=True)
        timer.start()
        try:
            report = self.run_case("download_until_stop", byte_limit=4 * 1024 * 1024,
                                   timeout_ms=2000, cancel_event=event)
        finally:
            stop.set()
            timer.join(timeout=1)
        self.assertTrue(report["settled"], report)
        self.assertEqual(report["outcome"], "Cancelled")
        self.assertGreater(report["guard"]["upload"] + report["guard"]["download"], 0)
        self.assertLess(report["guard"]["upload"] + report["guard"]["download"], 4 * 1024 * 1024)
        self.assertTrue(report["exit"]["ownedProcessSetEmpty"])

    def test_failed_durable_reservation_never_spawns_workload(self):
        with mock.patch.object(self.ledger, "_save", side_effect=budget.BudgetError("InjectedDurableFailure")), \
             mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("workload spawned before durable reservation")):
            with self.assertRaisesRegex(budget.BudgetError, "InjectedDurableFailure"):
                self.coordinator.run("upload_until_stop")

    def test_start_requires_durable_reservation_and_guard_ack(self):
        original = supervisor._Frames.send
        seen = []
        def observe(frames, value):
            if value["op"] in {"grant", "start"}:
                data = json.loads(self.ledger.path.read_text())
                history = data["history"][value["reservation_id"]]
                self.assertIn(value["reservation_id"], data["reservations"])
                self.assertEqual(history["planDigest"], value["plan_digest"])
                self.assertEqual(history["phase"], "spawned" if value["op"] == "grant" else "running")
                seen.append(value["op"])
            return original(frames, value)
        with mock.patch.object(supervisor._Frames, "send", observe):
            report = self.run_case("upload_until_stop")
        self.assertTrue(report["settled"], report)
        self.assertEqual(seen, ["grant", "start"])

    def test_mismatched_real_ready_receipt_never_starts(self):
        original = supervisor._Frames.receive
        def corrupt(frames, deadline):
            value = original(frames, deadline)
            return {**value, "nonce": "0" * 64} if value.get("op") == "ready" else value
        with mock.patch.object(supervisor._Frames, "receive", corrupt):
            report = self.run_case("upload_until_stop")
        self.assertFalse(report["settled"])
        self.assertEqual(report["outcome"], "WorkerReceiptBindingMismatch")
        self.assertEqual(report["fixture"]["acceptedConnections"], 0)
        self.assertEqual(report["ledger"]["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)

    def test_cleanup_failure_cannot_refund_a_valid_final_receipt(self):
        original = supervisor._OwnedFixture.close
        def fail_after_close(fixture):
            original(fixture)
            raise budget.BudgetError("InjectedFixtureCleanupFailure")
        with mock.patch.object(supervisor._OwnedFixture, "close", fail_after_close):
            report = self.run_case("upload_until_stop")
        self.assertFalse(report["settled"])
        self.assertEqual(report["outcome"], "FixtureExitUnconfirmed")
        self.assertTrue(report["exit"]["ownedProcessSetEmpty"])
        self.assertIsNotNone(report["guard"])
        self.assertEqual(report["ledger"]["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)

    def test_extra_protocol_output_cannot_refund(self):
        original = supervisor._Frames.finish
        def inject_tail(frames):
            frames.frames.put_nowait({"op": "unexpected"})
            return original(frames)
        with mock.patch.object(supervisor._Frames, "finish", inject_tail):
            report = self.run_case("upload_until_stop")
        self.assertFalse(report["settled"])
        self.assertEqual(report["outcome"], "UnexpectedWorkerTail")
        self.assertEqual(report["ledger"]["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)

    def test_real_workers_compete_under_three_held_slots(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            def run(node):
                try:
                    return self.coordinator.run("stall_runtime_after_connect", node=node, timeout_ms=700)
                except budget.BudgetError as error:
                    return str(error)
            results = list(pool.map(run, range(1, 5)))
        self.assertEqual(results.count("ConcurrencyLimit"), 1)
        reports = [value for value in results if isinstance(value, dict)]
        REPORTS.extend({"test": self.id(), **value} for value in reports)
        self.assertTrue(all(value["observedRunning"] and value["exit"]["ownedProcessSetEmpty"] for value in reports), reports)
        self.assertEqual(self.ledger.summary()["heldBytes"], 3 * (65536 + budget.TCP_RECEIVE_RESERVATION))

    @unittest.skipUnless(os.name == "nt", "Windows kill-on-close after parent crash")
    def test_windows_parent_crash_kills_rust_child_and_retains_history(self):
        self.ledger.__exit__()
        self.path = self.path.with_name("crash-budget")
        code = ("import sys\nsys.path.insert(0,sys.argv[1])\n"
                "from PrivateSubscriptionBudget import Ledger\n"
                "from PrivateSubscriptionSupervisor import WorkerIdentity,Supervisor\n"
                "identity=WorkerIdentity.inspect(sys.argv[2],sys.argv[3])\n"
                "with Ledger(sys.argv[4]) as ledger:\n"
                " ledger.initialize_synthetic()\n"
                " Supervisor(ledger,identity).run('stall_runtime_after_connect',timeout_ms=8000)\n")
        outer = subprocess.Popen([sys.executable, "-c", code, str(TOOLS), str(self.identity.path),
                                  self.identity.metadata["source_sha"], str(self.path)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        handle = None
        try:
            stop = time.monotonic() + 5
            history = None
            while time.monotonic() < stop:
                try:
                    data = json.loads((self.path / "traffic-budget.json").read_text())
                    history = data["history"].get("1")
                    if history and history["phase"] == "active":
                        break
                except (OSError, ValueError, KeyError):
                    pass
                time.sleep(0.01)
            self.assertIsNotNone(history)
            self.assertEqual(history["phase"], "active")
            import ctypes as c
            from ctypes import wintypes as w
            kernel = c.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
            kernel.WaitForSingleObject.argtypes, kernel.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
            kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
            handle = kernel.OpenProcess(0x100000, False, history["pid"])
            self.assertTrue(handle)
            outer.kill()
            outer.wait(timeout=2)
            self.assertEqual(kernel.WaitForSingleObject(handle, 2000), 0)
            self.ledger = budget.Ledger(self.path).__enter__()
            self.assertEqual(self.ledger.summary()["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)
            self.assertEqual(self.ledger.data["history"]["1"]["phase"], "active")
            with self.assertRaisesRegex(budget.BudgetError, "ConfigurationAlreadyAttempted"):
                supervisor.Supervisor(self.ledger, self.identity).run("stall_runtime_after_connect", timeout_ms=8000)
            REPORTS.append({"test": self.id(), "scope": budget.SYNTHETIC_DOMAIN,
                            "parentCrashJobExitConfirmed": True, "unsettledHoldRetained": True,
                            "source_sha": self.identity.metadata["source_sha"], "worker_sha256": self.identity.sha256})
        finally:
            if outer.poll() is None:
                outer.kill()
                outer.wait(timeout=2)
            if handle:
                kernel.CloseHandle(handle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--evidence", type=Path)
    options, remaining = parser.parse_known_args()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    metadata = {"schema": 1, "scope": "synthetic-loopback-only; not live/UI/wire/TUN acceptance",
                "platform": sys.platform, "testsRun": result.testsRun, "failures": len(result.failures),
                "errors": len(result.errors), "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
                "source_sha": None if IDENTITY is None else IDENTITY.metadata["source_sha"],
                "worker_sha256": None if IDENTITY is None else IDENTITY.sha256,
                "reports": REPORTS, "realNodeRequests": 0, "providerRequests": 0, "liveReady": False}
    if options.evidence:
        directory = options.evidence / (time.strftime("attempt-%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(4))
        directory.mkdir(parents=True, exist_ok=False)
        with (directory / "supervisor-results.json").open("x", encoding="utf-8") as output:
            json.dump(metadata, output, ensure_ascii=True, sort_keys=True, indent=2)
    raise SystemExit(0 if result.wasSuccessful() else 1)
