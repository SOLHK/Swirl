"""Actual QA Qt/DLL/ledger integration; Windows-only results stay explicit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import PrivateSubscriptionBudget as budget
import PrivateSubscriptionProcess as process
import PrivateSubscriptionSupervisor as supervisor
import PrivateSubscriptionUi as ui

REPORTS = []


class UiAdmissionTests(unittest.TestCase):
    def test_live_and_private_inputs_refuse_before_any_path_or_child(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "must-not-exist"
            for flag in ("--live", "--live=yes", "--store=PRIVATE_MARKER", "--subscription=PRIVATE_MARKER", "--provider-url=PRIVATE_MARKER"):
                with self.subTest(flag=flag.split("=")[0]), \
                     mock.patch.object(ui.UiIdentity, "inspect", side_effect=AssertionError("identity spawned")), \
                     mock.patch.object(ui, "Ledger", side_effect=AssertionError("ledger accessed")):
                    with self.assertRaisesRegex(budget.BudgetError, "PrivateLiveUiAdmissionUnavailable"):
                        ui.main([flag, "--state-dir", str(missing)])
                command = subprocess.run([sys.executable, str(TOOLS / "PrivateSubscriptionUi.py"), flag,
                                          "--state-dir", str(missing)], capture_output=True, timeout=5)
                self.assertEqual(command.returncode, 64)
                self.assertNotIn(b"PRIVATE_MARKER", command.stdout + command.stderr)
                self.assertFalse(missing.exists())

    def test_both_trusted_hashes_are_required_before_metadata_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            executable = root / "not-a-qa-binary.exe"
            core = root / ("swirl_api.dll" if os.name == "nt" else "libswirl_api.so")
            executable.write_bytes(b"fixed non-executable test marker")
            core.write_bytes(b"fixed non-library test marker")
            actual = hashlib.sha256(executable.read_bytes()).hexdigest()
            with mock.patch.object(ui, "OwnedProcess", side_effect=AssertionError("untrusted metadata executed")):
                for exe_hash, core_hash in ((None, "1" * 64), (actual, None), ("0" * 64, "1" * 64), (actual, "0" * 64)):
                    with self.subTest(missing=exe_hash is None or core_hash is None), self.assertRaises(budget.BudgetError):
                        ui.UiIdentity.inspect(executable, "1" * 40, exe_hash, expected_core_sha256=core_hash)

    def test_ui_history_cannot_relabel_or_refund_a_residual_hold(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / "synthetic-ledger"
            with budget.Ledger(path) as ledger:
                ledger.initialize_synthetic()
                ticket = ledger.reserve_supervised(1, 31, 6, 8000, config_fingerprint="1" * 64,
                    source_sha="2" * 40, worker_sha256="3" * 64, build_id="4" * 64,
                    nonce="5" * 64, workload=ui.UI_WORKLOAD)
                ledger.bind_supervised_grant(ticket, "6" * 64)
                ledger.retain_supervised(ticket, "NoActualExitProof")
                before = ledger.path.read_bytes()
                with self.assertRaises(budget.BudgetError):
                    ledger.require_live_ready()
            with budget.Ledger(path, existing_only=True) as ledger:
                self.assertEqual(ledger.path.read_bytes(), before)
                self.assertEqual(ledger.summary()["heldBytes"], 31 + 6 * budget.TCP_RECEIVE_RESERVATION)
                self.assertIsNone(ledger.summary()["billingDelta"])
                with self.assertRaisesRegex(budget.BudgetError, "ConfigurationAlreadyAttempted"):
                    ledger.reserve_supervised(1, 31, 6, 8000, config_fingerprint="1" * 64,
                        source_sha="2" * 40, worker_sha256="3" * 64, build_id="4" * 64,
                        nonce="7" * 64, workload=ui.UI_WORKLOAD)

    def test_json_cannot_construct_a_ui_identity_or_exit_proof(self):
        with self.assertRaisesRegex(budget.BudgetError, "WorkerIdentityFactoryRequired"):
            ui.UiIdentity(Path("/not-an-executable"), {"role": ui.UI_ROLE}, "1" * 64)
        with self.assertRaisesRegex(budget.BudgetError, "PrivateUiIdentityRequired"):
            ui.SyntheticUiSession({"role": ui.UI_ROLE}, Path("/new"), Path("/fixtures"))
        with self.assertRaisesRegex(budget.BudgetError, "ProcessExitProofRequired"):
            process.ExitProof(None, 1, "1" * 64, 0, "windows-single-process-job")

    @unittest.skipUnless(os.name != "nt", "non-Windows admission boundary")
    def test_suspended_mode_rejects_before_non_windows_spawn(self):
        with mock.patch.object(process.subprocess, "Popen", side_effect=AssertionError("spawned")):
            with self.assertRaisesRegex(budget.BudgetError, "WindowsSuspendedOwnerRequired"):
                process.OwnedProcess([sys.executable], deadline=time.monotonic() + 1, suspended=True)


@unittest.skipUnless(os.name == "nt", "actual suspended Windows Job semantics")
class SuspendedOwnerTests(unittest.TestCase):
    def test_deadline_is_live_while_suspended_and_full_hold_survives(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            marker = root / "must-not-run.txt"
            path = root / "ledger"
            with budget.Ledger(path) as ledger:
                ledger.initialize_synthetic()
                ticket = ledger.reserve_supervised(1, 31, 6, 400, config_fingerprint="1" * 64,
                    source_sha="2" * 40, worker_sha256="3" * 64, build_id="4" * 64,
                    nonce="5" * 64, workload=ui.UI_WORKLOAD)
                ledger.bind_supervised_grant(ticket, "6" * 64)
                started = time.monotonic()
                with process.OwnedProcess([sys.executable, "-c", "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text('RUN')", str(marker)],
                                          deadline=started + 0.4, suspended=True) as child:
                    self.assertTrue(child._watchdog.is_alive())
                    child.job.verify_member(child.process)
                    ledger.advance_supervised(ticket, "spawned", process=child)
                    proof = child.wait(timeout=2)
                    self.assertTrue(child.timed_out)
                    self.assertFalse(marker.exists())
                    self.assertTrue(proof.record()["processSignaled"])
                    self.assertTrue(proof.record()["ownedProcessSetEmpty"])
                    self.assertLess(time.monotonic() - started, 2)
                    with self.assertRaises(budget.BudgetError):
                        child.resume()
                ledger.retain_supervised(ticket, "SuspendedDeadlineWithoutGuardReceipt")
                before = ledger.path.read_bytes()
            with budget.Ledger(path, existing_only=True) as ledger:
                self.assertEqual(ledger.path.read_bytes(), before)
                self.assertEqual(ledger.summary()["heldBytes"], 31 + 6 * budget.TCP_RECEIVE_RESERVATION)
                REPORTS.append({"test": self.id(), "scope": "actual-Windows-suspended-owner; no Qt networking",
                                "exit": proof.record(), "deadlineWhileSuspended": True,
                                "childCodeExecuted": False, "fullHoldBytes": ledger.summary()["heldBytes"]})

    def test_resume_is_single_use_and_exit_259_is_real_exit(self):
        with process.OwnedProcess([sys.executable, "-c", "import sys;print('RESUMED',flush=True);sys.exit(259)"],
                                  deadline=time.monotonic() + 2, suspended=True) as child:
            self.assertIsNone(child.process.poll())
            self.assertTrue(child._watchdog.is_alive())
            child.resume()
            with self.assertRaisesRegex(budget.BudgetError, "OwnedSuspendedProcessRequired"):
                child.resume()
            proof = child.wait(timeout=2)
            self.assertEqual(child.stdout.read(), b"RESUMED\r\n")
            self.assertEqual(proof.record()["exitCode"], 259)
            self.assertTrue(proof.record()["ownedProcessSetEmpty"])
            REPORTS.append({"test": self.id(), "scope": "actual-Windows-suspended-owner; no Qt networking",
                            "exit": proof.record(), "singleResume": True})


@unittest.skipUnless(os.name == "nt", "actual Windows Qt6.12/DPAPI/paired DLL acceptance")
class ActualQtQuotaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # On Windows, missing build outputs are an error, not a successful skip.
        cls.exe = Path(os.environ["SWIRL_PRIVATE_UI_EXE"])
        cls.exe_hash = os.environ["SWIRL_PRIVATE_UI_EXE_SHA256"]
        cls.core_hash = os.environ["SWIRL_PRIVATE_UI_CORE_SHA256"]
        cls.source = os.environ["SWIRL_PRIVATE_EXPECTED_SOURCE"]
        cls.fixtures = TOOLS.parent / "src/Swirl.Quick/tests/fixtures"
        cls.qt_root = os.environ.get("SWIRL_PRIVATE_UI_QT_ROOT")
        cls.identity = ui.UiIdentity.inspect(cls.exe, cls.source, cls.exe_hash, expected_core_sha256=cls.core_hash)
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()
        cls.ledger_path = cls.root / "one-synthetic-ledger"
        with budget.Ledger(cls.ledger_path) as ledger:
            ledger.initialize_synthetic()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_01_actual_cli_same_ledger_probe_http_and_verified_https(self):
        command = [sys.executable, str(TOOLS / "PrivateSubscriptionUi.py"),
                   "--exe", str(self.exe), "--exe-sha256", self.exe_hash, "--core-sha256", self.core_hash,
                   "--expected-source", self.source, "--state-dir", str(self.ledger_path),
                   "--output-directory", str(self.root / "positive"), "--fixture-directory", str(self.fixtures)]
        if self.qt_root:
            command += ["--qt-root", self.qt_root]
        completed = subprocess.run(command, capture_output=True, timeout=18)
        self.assertNotIn(b"Traceback", completed.stderr)
        record = json.loads(completed.stdout)
        REPORTS.append({"test": self.id(), "record": record, "actualCliExit": completed.returncode})
        self.assertEqual(completed.returncode, 0, record)
        self.assertEqual(record["outcome"], "QtUiSucceeded")
        self.assertTrue(record["settled"])
        self.assertTrue(record["persistentBudgetGuardExercised"])
        self.assertFalse(record["fixture"]["ui"]["persistentBudgetGuardExercised"])
        self.assertTrue(record["fixture"]["guardedSessionProof"]["rawTcpQuotaExercised"])
        self.assertEqual(record["parentBudgetEvidence"]["durableHistoryPhase"], "settled")
        self.assertEqual(record["parentBudgetEvidence"]["settledNativeExit"], record["exit"])
        self.assertFalse(record["parentBudgetEvidence"]["fullHoldRetained"])
        self.assertEqual(record["realNodeRequests"], 0)
        self.assertEqual(record["providerRequests"], 0)
        self.assertTrue(record["exit"]["ownedProcessSetEmpty"])
        self.assertGreater(record["guard"]["upload"], 0)
        self.assertGreater(record["guard"]["download"], 0)

    def test_02_same_ui_core_stops_at_31_actual_raw_bytes_and_preserves_total(self):
        with budget.Ledger(self.ledger_path, existing_only=True) as ledger:
            before = ledger.data["localUpload"] + ledger.data["localDownload"]
            session = ui.SyntheticUiSession(self.identity, self.root / "low-cap", self.fixtures, qt_root=self.qt_root)
            record = supervisor.Supervisor(ledger, self.identity).run_ui(session, byte_limit=31)
            REPORTS.append({"test": self.id(), "record": record})
            self.assertEqual(record["outcome"], "QtUiQuotaStopped", record)
            self.assertTrue(record["settled"])
            self.assertTrue(record["cleanupConfirmed"])
            self.assertEqual(record["guard"]["upload"] + record["guard"]["download"], 31)
            self.assertEqual(ledger.data["localUpload"] + ledger.data["localDownload"], before + 31)
            self.assertEqual(len(ledger.data["history"]), 2)
            self.assertIsNone(ledger.summary()["billingDelta"])
            self.assertFalse(record["liveReady"])

    def test_03_durable_reservation_write_failure_never_opens_fixture_or_qt(self):
        with budget.Ledger(self.ledger_path, existing_only=True) as ledger:
            before = ledger.path.read_bytes()
            session = ui.SyntheticUiSession(self.identity, self.root / "write-refusal", self.fixtures, qt_root=self.qt_root)
            with mock.patch.object(ledger.windows, "replace", side_effect=OSError("fixed synthetic storage failure")), \
                 mock.patch.object(session, "open", side_effect=AssertionError("fixture opened before reserve")) as fixture_open, \
                 mock.patch.object(session, "spawn", side_effect=AssertionError("Qt spawned before reserve")) as spawn:
                with self.assertRaisesRegex(OSError, "fixed synthetic storage failure"):
                    supervisor.Supervisor(ledger, self.identity).run_ui(session, byte_limit=32768)
                fixture_open.assert_not_called()
                spawn.assert_not_called()
            self.assertEqual(ledger.path.read_bytes(), before)
            self.assertFalse(session.root.exists())
        with budget.Ledger(self.ledger_path, existing_only=True) as ledger:
            self.assertEqual(ledger.path.read_bytes(), before)
            REPORTS.append({"test": self.id(), "scope": "actual Windows storage path with injected replace failure",
                            "injectedBackend": "windows-replace", "fixtureOpenCalls": 0, "qtSpawnCalls": 0,
                            "priorLedgerBytesUnchanged": True, "historyCount": len(ledger.data["history"])})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--evidence", type=Path)
    options, remaining = parser.parse_known_args()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"schema": 1, "scope": "fixed-synthetic-Qt-UI-with-actual-Rust-quota; no provider/wire/TUN acceptance",
              "platform": sys.platform, "testsRun": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
              "reports": REPORTS, "realNodeRequests": 0, "providerRequests": 0, "liveReady": False}
    if options.evidence:
        options.evidence.mkdir(parents=True, exist_ok=False)
        with (options.evidence / "private-ui-quota-results.json").open("x", encoding="utf-8") as destination:
            json.dump(report, destination, indent=2)
            destination.write("\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
