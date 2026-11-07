"""Same-ledger synthetic billing plus actual Windows Qt raw-TCP quota.

Portable controls exercise the real guarded Rust worker and durable ledger.
Only the explicitly Windows cases claim actual Qt/DPAPI/DLL execution. Neither
kind grants provider authority, restores a private ledger, or enables live.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import PrivateSubscriptionBilling as billing
import PrivateSubscriptionBudget as budget
import PrivateSubscriptionSupervisor as supervisor
import PrivateSubscriptionUi as ui

REPORTS = []
IDENTITIES = {"billingWorker": None, "qtUi": None}


def worker_identity():
    # Missing designated outputs must fail the gate, including on Windows.
    identity = supervisor.WorkerIdentity.inspect(Path(os.environ["SWIRL_PRIVATE_WORKER"]),
        os.environ["SWIRL_PRIVATE_EXPECTED_SOURCE"], os.environ["SWIRL_PRIVATE_EXPECTED_WORKER_SHA256"])
    IDENTITIES["billingWorker"] = {**identity.metadata, "exe_sha256": identity.sha256}
    return identity


def assert_history_identity(test, history, identity):
    test.assertEqual(history["sourceSha"], identity.metadata["source_sha"])
    test.assertEqual(history["buildId"], identity.metadata["build_id"])
    test.assertEqual(history["workerSha256"], identity.sha256)


class UiBillingAdmissionTests(unittest.TestCase):
    def test_billing_cli_requires_complete_pair_before_paths_or_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            common = ["--exe", "PRIVATE_MARKER", "--exe-sha256", "1" * 64,
                      "--core-sha256", "2" * 64, "--expected-source", "3" * 40,
                      "--state-dir", str(root / "ledger"), "--output-directory", str(root / "ui"),
                      "--fixture-directory", str(root / "fixtures")]
            variants = (["--synthetic-billing", "--billing-worker", "PRIVATE_MARKER"],
                        ["--billing-worker", "PRIVATE_MARKER", "--billing-worker-sha256", "4" * 64],
                        ["--billing-response-contract", billing.HTTP_RESPONSE_CONTRACT])
            for extra in variants:
                with self.subTest(arguments=extra[0]), \
                     mock.patch.object(ui, "Ledger", side_effect=AssertionError("ledger accessed")), \
                     mock.patch.object(ui.UiIdentity, "inspect", side_effect=AssertionError("UI metadata executed")), \
                     mock.patch.object(ui.WorkerIdentity, "inspect", side_effect=AssertionError("worker metadata executed")):
                    with self.assertRaisesRegex(budget.BudgetError, "PairedBillingWorkerIdentityRequired"):
                        ui.main(common + extra)
                child = subprocess.run([sys.executable, str(TOOLS / "PrivateSubscriptionUi.py"), *common, *extra],
                                       capture_output=True, timeout=5, check=False)
                self.assertEqual(child.returncode, 64)
                self.assertNotIn(b"PRIVATE_MARKER", child.stdout + child.stderr)
                self.assertFalse((root / "ledger").exists())
                self.assertFalse((root / "ui").exists())
            for extra in (["--live", "--synthetic-billing"],
                          ["--provider-url=PRIVATE_MARKER", "--synthetic-billing"]):
                with mock.patch.object(ui, "Ledger", side_effect=AssertionError("ledger accessed")), \
                     mock.patch.object(ui.UiIdentity, "inspect", side_effect=AssertionError("metadata executed")):
                    with self.assertRaisesRegex(budget.BudgetError, "PrivateLiveUiAdmissionUnavailable"):
                        ui.main(common + extra)
            REPORTS.append({"test": self.id(), "scope": "actual CLI admission only", "privateInputAccessed": False,
                            "metadataStarted": False, "ledgerCreated": False, "liveReady": False})


class ExplicitExecutionIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.primary = worker_identity()
        cls.copied = tempfile.TemporaryDirectory()
        duplicate = Path(cls.copied.name).resolve() / cls.primary.path.name
        shutil.copy2(cls.primary.path, duplicate)
        cls.control = supervisor.WorkerIdentity.inspect(duplicate, cls.primary.metadata["source_sha"], cls.primary.sha256)

    @classmethod
    def tearDownClass(cls):
        cls.copied.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "one-ledger"
        self.ledger = budget.Ledger(self.path).__enter__()
        self.ledger.initialize_synthetic()
        self.session = billing.BillingSession.register(self.ledger)

    def tearDown(self):
        self.ledger.__exit__()
        self.temp.cleanup()

    def test_json_identity_cannot_authorize_a_billing_child(self):
        before = self.ledger.path.read_bytes()
        with mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("child executed")):
            with self.assertRaisesRegex(budget.BudgetError, "PairedBillingWorkerIdentityRequired"):
                supervisor.Supervisor(self.ledger, self.primary, self.session,
                    billing_worker_identity={"metadata": self.control.metadata, "sha256": self.control.sha256})
        self.assertEqual(self.ledger.path.read_bytes(), before)
        self.assertEqual(self.ledger.data["sequence"], 0)

    def test_real_billing_children_use_explicit_identity_without_replacing_primary(self):
        runner = supervisor.Supervisor(self.ledger, self.primary, self.session, billing_worker_identity=self.control)
        actual_owner, launches = supervisor.OwnedProcess, []

        def observe_launch(arguments, **keywords):
            self.assertIs(runner.identity, self.primary)
            launches.append(str(Path(arguments[0])))
            return actual_owner(arguments, **keywords)

        with mock.patch.object(supervisor, "OwnedProcess", side_effect=observe_launch):
            record = runner.run("core_probe", timeout_ms=3000)
        REPORTS.append({"test": self.id(), "scope": "real Rust worker route, not actual Qt", "record": record,
                        "launchRoles": ["billing", "primary", "billing"],
                        "distinctExecutablePaths": str(self.primary.path) != str(self.control.path),
                        "sameVerifiedExecutableBytes": self.primary.sha256 == self.control.sha256})
        self.assertEqual(launches, [str(self.control.path), str(self.primary.path), str(self.control.path)])
        self.assertIs(runner.identity, self.primary)
        self.assertTrue(record["settled"], record)
        self.assertEqual(record["metrics"]["http_status"], 204)
        self.assertEqual(record["guard"]["connection_attempts"], 2)
        self.assertEqual(len(record["controlQueries"]), 2)
        for history in self.ledger.data["history"].values():
            assert_history_identity(self, history, self.primary if history["node"] else self.control)
        self.assertEqual(self.ledger.summary()["heldBytes"], 0)
        self.assertFalse(self.ledger.summary()["providerStatisticsAuthenticated"])

    def test_durable_ticket_identity_mismatch_opens_no_fixture_and_retains_full_hold(self):
        nonce, fingerprint = secrets.token_hex(32), "6" * 64
        wrong_hash = ("0" if self.control.sha256[0] != "0" else "1") + self.control.sha256[1:]
        ticket = self.ledger.reserve_billing_control(self.session, purpose="preflight", timeout_ms=1000,
            config_fingerprint=fingerprint, source_sha=self.control.metadata["source_sha"],
            worker_sha256=wrong_hash, build_id=self.control.metadata["build_id"], nonce=nonce)
        plan = budget.tcp_plan(billing.BYTE_LIMIT, billing.CONNECTION_LIMIT, 1000)
        query = self.session.query(ticket, nonce)
        runner = supervisor.Supervisor(self.ledger, self.primary, self.session, billing_worker_identity=self.control)
        with mock.patch.object(supervisor, "_OwnedFixture", side_effect=AssertionError("fixture opened")) as fixture, \
             mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("child executed")) as spawn:
            evidence = runner._execute_reserved(ticket, billing.WORKLOAD, plan, nonce, fingerprint,
                                                 billing_query=query, execution_identity=self.control)
            fixture.assert_not_called()
            spawn.assert_not_called()
        self.assertEqual(evidence.record["outcome"], "ExecutionTicketIdentityMismatch")
        self.assertFalse(evidence.complete)
        self.assertIsNone(evidence.exit_proof)
        self.ledger.retain_supervised(ticket, evidence.record["outcome"])
        amount = plan["byteLimit"] + plan["receiveReservation"]
        self.assertEqual(self.ledger.summary()["heldBytes"], amount)
        before = self.ledger.path.read_bytes()
        self.ledger.__exit__()
        self.ledger = budget.Ledger(self.path, existing_only=True).__enter__()
        self.assertEqual(self.ledger.path.read_bytes(), before)
        self.assertEqual(self.ledger.summary()["heldBytes"], amount)
        self.assertEqual(self.ledger.data["history"][ticket]["phase"], "unresolved")
        self.assertIsNone(self.ledger.data["history"][ticket]["pid"])
        with self.assertRaisesRegex(budget.BudgetError, "OriginalBillingSessionUnavailable"):
            billing.BillingSession.register(self.ledger)
        REPORTS.append({"test": self.id(), "record": evidence.record, "heldBytesAfterReopen": amount,
                        "fixtureOpened": False, "processStarted": False, "sameLedgerBytesAfterReopen": True})


@unittest.skipUnless(os.name == "nt", "actual Windows Qt6.12/DPAPI/paired DLL and synthetic billing")
class ActualQtBillingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(os.environ["SWIRL_PRIVATE_UI_EXE"])
        cls.exe_hash = os.environ["SWIRL_PRIVATE_UI_EXE_SHA256"]
        cls.core_hash = os.environ["SWIRL_PRIVATE_UI_CORE_SHA256"]
        cls.source = os.environ["SWIRL_PRIVATE_EXPECTED_SOURCE"]
        cls.qt_root = os.environ.get("SWIRL_PRIVATE_UI_QT_ROOT")
        cls.fixtures = TOOLS.parent / "src/Swirl.Quick/tests/fixtures"
        cls.identity = ui.UiIdentity.inspect(cls.exe, cls.source, cls.exe_hash, expected_core_sha256=cls.core_hash)
        IDENTITIES["qtUi"] = {**cls.identity.metadata, "exe_sha256": cls.identity.sha256,
                              "core_sha256": cls.identity.core_sha256, "qt_version": cls.identity.qt_version}
        cls.control = worker_identity()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "one-ledger"
        self.ledger = budget.Ledger(self.path).__enter__()
        self.ledger.initialize_synthetic()

    def tearDown(self):
        self.ledger.__exit__()
        self.temp.cleanup()

    def session(self, name):
        return ui.SyntheticUiSession(self.identity, self.root / name, self.fixtures, qt_root=self.qt_root)

    def runner(self, *, auto_cover=True, contract=billing.QA_RESPONSE_CONTRACT):
        authority = billing.SyntheticBillingAuthority(auto_cover=auto_cover)
        session = billing.BillingSession.register(self.ledger, authority)
        runner = supervisor.Supervisor(self.ledger, self.identity, session,
            billing_worker_identity=self.control, billing_response_contract=contract)
        return authority, session, runner

    def assert_controls(self, record, *, count=2):
        self.assertEqual(len(record["controlQueries"]), count)
        control_charge = billing.BYTE_LIMIT + billing.CONNECTION_LIMIT * budget.TCP_RECEIVE_RESERVATION
        for query in record["controlQueries"]:
            self.assertEqual(query["worker_sha256"], self.control.sha256)
            self.assertEqual(query["build_id"], self.control.metadata["build_id"])
            self.assertTrue(query["controlConsumed"])
            self.assertEqual(query["controlDebit"], control_charge)
            self.assertFalse(query["controlDebitIsMeasuredTraffic"])
            self.assertTrue(query["cleanupConfirmed"])
            self.assertTrue(query["exit"]["processSignaled"])
            self.assertTrue(query["exit"]["ownedProcessSetEmpty"])
        self.assertFalse(record["liveReady"])
        self.assertFalse(record["ledger"]["providerStatisticsAuthenticated"])
        self.assertEqual(record["providerRequests"], 0)
        self.assertEqual(record["realNodeRequests"], 0)
        for history in self.ledger.data["history"].values():
            assert_history_identity(self, history, self.identity if history["node"] else self.control)

    def cli(self, contract):
        self.ledger.__exit__()
        command = [sys.executable, str(TOOLS / "PrivateSubscriptionUi.py"), "--exe", str(self.exe),
            "--exe-sha256", self.exe_hash, "--core-sha256", self.core_hash, "--expected-source", self.source,
            "--state-dir", str(self.path), "--output-directory", str(self.root / "actual-cli-ui"),
            "--fixture-directory", str(self.fixtures), "--synthetic-billing", "--billing-worker", str(self.control.path),
            "--billing-worker-sha256", self.control.sha256, "--billing-response-contract", contract]
        if self.qt_root:
            command += ["--qt-root", self.qt_root]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=32, check=False)
            self.assertNotIn(b"Traceback", completed.stderr)
            self.assertEqual(completed.stderr, b"")
            record = json.loads(completed.stdout)
        finally:
            self.ledger = budget.Ledger(self.path, existing_only=True).__enter__()
        REPORTS.append({"test": self.id(), "scope": "actual Windows CLI and paired Qt/Rust binaries",
                        "record": record, "actualCliExit": completed.returncode})
        return completed.returncode, record

    def test_actual_cli_billing_preflight_qt_probe_proxy_and_post_exit_settle(self):
        code, record = self.cli(billing.QA_RESPONSE_CONTRACT)
        self.assertEqual(code, 0, record)
        self.assertEqual(record["outcome"], "QtUiSucceeded")
        self.assertTrue(record["settled"])
        self.assertTrue(record["persistentBudgetGuardExercised"])
        self.assertFalse(record["fixture"]["ui"]["persistentBudgetGuardExercised"])
        self.assertTrue(record["fixture"]["guardedSessionProof"]["rawTcpQuotaExercised"])
        self.assertEqual(record["parentBudgetEvidence"]["durableHistoryPhase"], "settled")
        self.assertEqual(record["parentBudgetEvidence"]["settledNativeExit"], record["exit"])
        self.assertFalse(record["parentBudgetEvidence"]["fullHoldRetained"])
        self.assert_controls(record)
        self.assertEqual(self.ledger.data["schema"], 4)
        self.assertEqual(self.ledger.summary()["heldBytes"], 0)
        self.assertEqual(self.ledger.summary()["attempts"], 1)
        self.assertEqual(record["fixture"]["ui"]["probeHttpStatus"], 204)
        self.assertEqual([row["httpStatus"] for row in record["fixture"]["ui"]["proxyRequests"]], [200, 200])
        self.assertEqual(self.ledger.summary()["localUpload"] + self.ledger.summary()["localDownload"],
                         record["guard"]["upload"] + record["guard"]["download"])
        self.assertIsNone(self.ledger.summary()["billingDelta"])

    def test_actual_ui_31_byte_stop_still_reconciles_separately_charged_queries(self):
        _, _, runner = self.runner()
        record = runner.run_ui(self.session("raw-cap"), byte_limit=31)
        REPORTS.append({"test": self.id(), "scope": "actual Windows Qt same shared Rust quota", "record": record})
        self.assertEqual(record["outcome"], "QtUiQuotaStopped", record)
        self.assertTrue(record["settled"])
        self.assertEqual(record["guard"]["upload"] + record["guard"]["download"], 31)
        self.assertEqual(self.ledger.summary()["localUpload"] + self.ledger.summary()["localDownload"], 31)
        self.assert_controls(record)
        self.assertEqual(self.ledger.summary()["syntheticBilling"]["controlDebitedBytes"],
                         2 * (billing.BYTE_LIMIT + billing.CONNECTION_LIMIT * budget.TCP_RECEIVE_RESERVATION))
        self.assertEqual(self.ledger.summary()["heldBytes"], 0)

    def test_actual_http_observation_cli_cannot_start_qt_or_authorize_account(self):
        code, record = self.cli(billing.HTTP_RESPONSE_CONTRACT)
        self.assertEqual(code, 2, record)
        self.assertEqual(record["outcome"], "ProviderAccountBindingUnproven")
        self.assertFalse(record["nodeStarted"])
        self.assertFalse(record["settled"])
        self.assertFalse(record["persistentBudgetGuardExercised"])
        self.assertIsNone(record["parentBudgetEvidence"])
        self.assertFalse((self.root / "actual-cli-ui").exists())
        self.assert_controls(record, count=1)
        query = record["controlQueries"][0]
        self.assertTrue(query["httpObservationRecorded"])
        self.assertFalse(query["billingObservationAccepted"])
        self.assertTrue(query["fixture"]["billingRequestReceived"])
        self.assertEqual(query["guard"]["connection_attempts"], 2)
        self.assertEqual(self.ledger.summary()["attempts"], 0)
        self.assertTrue(all(h["node"] == 0 for h in self.ledger.data["history"].values()))

    def test_actual_ui_exit_waits_for_model_coverage_without_restarting_qt(self):
        authority, _, runner = self.runner(auto_cover=False)
        session = self.session("coverage-pending")
        record = runner.run_ui(session)
        REPORTS.append({"test": self.id(), "stage": "pending", "record": record})
        self.assertEqual(record["outcome"], "SyntheticBillingCoveragePending", record)
        self.assertFalse(record["settled"])
        self.assertTrue(record["cleanupConfirmed"])
        self.assertTrue(record["fixture"]["ui"]["passed"])
        self.assertFalse(record["persistentBudgetGuardExercised"])
        self.assertTrue(record["parentBudgetEvidence"]["fullHoldRetained"])
        self.assert_controls(record)
        ticket = record["reservation_id"]
        history = self.ledger.data["history"][ticket]
        held = record["plan"]["byteLimit"] + record["plan"]["receiveReservation"]
        self.assertEqual(history["phase"], "reconcile_pending")
        self.assertEqual(self.ledger.summary()["heldBytes"], held)
        self.assertEqual(self.ledger.summary()["localUpload"] + self.ledger.summary()["localDownload"], 0)
        authority.add_other_client_usage(download=2_500_000)
        with mock.patch.object(ui.SyntheticUiSession, "spawn", side_effect=AssertionError("Qt retried during reconcile")):
            still_pending = runner.reconcile(ticket, timeout_ms=3000)
            self.assertFalse(still_pending["settled"])
            self.assertEqual(still_pending["outcome"], "SyntheticBillingCoveragePending")
            self.assertEqual(self.ledger.summary()["heldBytes"], held)
            authority.cover_exit(history["billing"]["exitSequence"])
            settled = runner.reconcile(ticket, timeout_ms=3000)
        REPORTS.append({"test": self.id(), "stage": "current-session-model-coverage", "record": settled,
                        "qtExecutions": 1, "accountDeltaIsSyntheticOtherClientUse": True})
        self.assertTrue(settled["settled"])
        self.assertEqual(settled["ledger"]["syntheticBilling"]["accountDelta"], 2_500_000)
        self.assertEqual(settled["ledger"]["localUpload"] + settled["ledger"]["localDownload"],
                         record["guard"]["upload"] + record["guard"]["download"])
        self.assertEqual(settled["ledger"]["heldBytes"], 0)
        self.assertEqual(self.ledger.summary()["attempts"], 1)

    def test_actual_ui_pending_exit_json_cannot_release_hold_after_reopening(self):
        _, _, runner = self.runner(auto_cover=False)
        record = runner.run_ui(self.session("restart-pending"))
        self.assertEqual(record["outcome"], "SyntheticBillingCoveragePending", record)
        ticket, held = record["reservation_id"], record["ledger"]["heldBytes"]
        self.assertGreater(held, 0)
        before = self.ledger.path.read_bytes()
        self.ledger.__exit__()
        self.ledger = budget.Ledger(self.path, existing_only=True).__enter__()
        self.assertEqual(self.ledger.path.read_bytes(), before)
        self.assertEqual(self.ledger.summary()["heldBytes"], held)
        self.assertEqual(self.ledger.data["history"][ticket]["phase"], "reconcile_pending")
        self.assertFalse(self.ledger.summary()["syntheticBilling"]["currentSessionRegistered"])
        with mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("recovery executed")), \
             mock.patch.object(ui.SyntheticUiSession, "spawn", side_effect=AssertionError("recovery Qt executed")):
            with self.assertRaisesRegex(budget.BudgetError, "OriginalBillingSessionUnavailable"):
                billing.BillingSession.register(self.ledger)
            with self.assertRaises(budget.BudgetError):
                runner.reconcile(ticket)
            with self.assertRaises(budget.BudgetError):
                self.ledger.require_live_ready()
        self.assertEqual(self.ledger.path.read_bytes(), before)
        REPORTS.append({"test": self.id(), "record": record, "sameLedgerBytesAfterReopen": True,
                        "pendingHoldBytes": held, "exitJsonReissuedAsProof": False, "newSessionRefused": True})

    def test_actual_ui_cleanup_uncertainty_retains_full_hold_without_post_query(self):
        _, _, runner = self.runner()
        session = self.session("cleanup-uncertain")
        original = session.close

        def uncertain_cleanup():
            original()
            raise budget.BudgetError("UiFixtureExitUnconfirmed")

        with mock.patch.object(session, "close", side_effect=uncertain_cleanup):
            record = runner.run_ui(session)
        REPORTS.append({"test": self.id(), "scope": "actual UI with injected cleanup confirmation failure", "record": record})
        self.assertEqual(record["outcome"], "FixtureExitUnconfirmed", record)
        self.assertFalse(record["settled"])
        self.assertFalse(record["cleanupConfirmed"])
        self.assertTrue(record["exit"]["ownedProcessSetEmpty"])
        self.assertTrue(record["parentBudgetEvidence"]["fullHoldRetained"])
        self.assert_controls(record, count=1)
        self.assertEqual(self.ledger.summary()["heldBytes"], record["plan"]["byteLimit"] + record["plan"]["receiveReservation"])
        self.assertEqual(self.ledger.summary()["localUpload"] + self.ledger.summary()["localDownload"], 0)
        self.assertEqual(self.ledger.data["history"][record["reservation_id"]]["phase"], "unresolved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--evidence", type=Path)
    options, remaining = parser.parse_known_args()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"schema": 1, "scope": "same synthetic Ledger, explicit billing-worker identity and actual Windows Qt quota",
              "platform": sys.platform, "testsRun": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
              "reports": REPORTS, "identities": IDENTITIES, "realNodeRequests": 0, "providerRequests": 0,
              "providerStatisticsAuthenticated": False, "liveReady": False}
    if options.evidence:
        options.evidence.mkdir(parents=True, exist_ok=False)
        with (options.evidence / "private-ui-billing-results.json").open("x", encoding="utf-8") as destination:
            json.dump(report, destination, indent=2)
            destination.write("\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
