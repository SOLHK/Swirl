"""Owned Rust/TLS synthetic billing pipeline; no real provider or node inputs."""
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
import PrivateSubscriptionBilling as billing
import PrivateSubscriptionSupervisor as supervisor

REPORTS = []
IDENTITY = None


def control(ledger, session, ordinal=1):
    return ledger.reserve_billing_control(session, purpose="preflight", timeout_ms=2000,
        config_fingerprint=hashlib.sha256(str(ordinal).encode()).hexdigest(), source_sha="1" * 40,
        worker_sha256="2" * 64, build_id="synthetic-test", nonce=secrets.token_hex(32))


class BillingStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "billing"

    def tearDown(self):
        self.temp.cleanup()

    def test_original_offline_domains_are_never_initialized_or_relabelled(self):
        with budget.Ledger(self.path) as ledger:
            with self.assertRaisesRegex(budget.BudgetError, "SyntheticLedgerRequired"):
                billing.BillingSession.register(ledger)
            self.assertIsNone(ledger.data)
            ledger.initialize("upload=100;download=200;total=100000000000")
            ticket = ledger.reserve_offline(1)
            before = ledger.path.read_bytes()
            with self.assertRaisesRegex(budget.BudgetError, "SyntheticLedgerRequired"):
                billing.BillingSession.register(ledger)
            self.assertEqual(ledger.path.read_bytes(), before)
            self.assertIn(ticket, ledger.data["reservations"])

    def test_registration_preserves_existing_synthetic_history_and_requires_same_session(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            ticket = ledger.reserve_supervised(1, 512, 1, 1000, config_fingerprint="a" * 64,
                source_sha="1" * 40, worker_sha256="2" * 64, build_id="synthetic-test",
                nonce="3" * 64, workload="upload_until_stop")
            ledger.retain_supervised(ticket, "InterruptedSyntheticAttempt")
            original = ledger.data["history"][ticket].copy()
            session = billing.BillingSession.register(ledger)
            self.assertEqual({key: value for key, value in ledger.data["history"][ticket].items() if key != "billing"}, original)
            control(ledger, session)
            before = ledger.summary()
        self.assertTrue(session.closed)
        with budget.Ledger(self.path) as ledger:
            after = ledger.summary()
            self.assertEqual(before["heldBytes"], after["heldBytes"])
            self.assertEqual(before["attempts"], after["attempts"])
            self.assertFalse(after["syntheticBilling"]["currentSessionRegistered"])
            original = ledger.path.read_bytes()
            for action in (lambda: billing.BillingSession.register(ledger), lambda: control(ledger, session, 2), ledger.require_live_ready):
                with self.assertRaises(budget.BudgetError):
                    action()
            self.assertEqual(ledger.path.read_bytes(), original)

    def test_three_control_reservations_share_the_existing_process_limit(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            session = billing.BillingSession.register(ledger)
            for ordinal in range(3):
                control(ledger, session, ordinal)
            before = ledger.path.read_bytes()
            with self.assertRaisesRegex(budget.BudgetError, "ConcurrencyLimit"):
                control(ledger, session, 4)
            self.assertEqual(ledger.path.read_bytes(), before)
            state = ledger.summary()
            self.assertEqual(state["attempts"], 0)
            self.assertEqual(state["syntheticBilling"]["controlAttempts"], 3)
            self.assertEqual(state["heldBytes"], 3 * (billing.BYTE_LIMIT + 2 * budget.TCP_RECEIVE_RESERVATION))

    def test_snapshot_json_and_fresh_tls_booleans_are_not_capabilities(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            session = billing.BillingSession.register(ledger)
            ticket = control(ledger, session)
            nonce = ledger.data["history"][ticket]["nonce"]
            query = session.query(ticket, nonce)
            with self.assertRaisesRegex(budget.BudgetError, "SyntheticBillingObservationRequired"):
                billing.BillingObservation(None, session, query, query.payload, time.monotonic())
            with self.assertRaisesRegex(budget.BudgetError, "SyntheticBillingObservationRequired"):
                session.observation(query, {**query.payload, "fresh": True, "tls_verified": True})
            with self.assertRaisesRegex(budget.BudgetError, "ControlledExecutionEvidenceRequired"):
                supervisor._ExecutionEvidence(None, {}, exit_proof=None, guard=None, receipt=None,
                    received=time.monotonic(), query=query, complete=True, cleanup=True)
            self.assertIsNone(ledger.summary()["billingDelta"])
            self.assertIsNone(ledger.summary()["syntheticBilling"]["accountDelta"])

    def test_in_session_ledger_rollback_is_rejected_without_repair(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            session = billing.BillingSession.register(ledger)
            old = ledger.path.read_bytes()
            control(ledger, session)
            ledger.path.write_bytes(old)
            with self.assertRaisesRegex(budget.BudgetError, "SyntheticBillingHistoryUnconfirmed"):
                control(ledger, session, 2)
            self.assertEqual(ledger.path.read_bytes(), old)
        # No claim about whole-machine rollback: even this complete old schema4
        # copy cannot acquire a new registration and execute after reopening.
        with budget.Ledger(self.path) as ledger:
            with self.assertRaisesRegex(budget.BudgetError, "OriginalBillingSessionUnavailable"):
                billing.BillingSession.register(ledger)

    def test_live_still_refuses_before_registration_paths_or_metadata(self):
        output = io.StringIO()
        with mock.patch.object(supervisor.WorkerIdentity, "inspect", side_effect=AssertionError("spawn")), \
             mock.patch.object(billing.BillingSession, "register", side_effect=AssertionError("register")), \
             contextlib.redirect_stdout(output):
            result = supervisor.main(["--live", "--synthetic-billing", "--state-dir", str(self.path)])
        self.assertEqual(result, 2)
        self.assertFalse(self.path.exists())
        self.assertEqual(json.loads(output.getvalue())["error"], "AuthenticatedBillingAndWireGuardRequired")

    def test_actual_cli_missing_registered_path_never_creates_directory_or_lock(self):
        command = [sys.executable, str(TOOLS / "PrivateSubscriptionSupervisor.py"), "--synthetic-billing",
                   "--state-dir", str(self.path), "--worker", "PRIVATE_MARKER",
                   "--worker-sha256", "0" * 64, "--expected-source", "0" * 40, "--workload", "core_probe"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), {"error": "RegisteredLedgerRequired", "liveReady": False})
        self.assertNotIn("PRIVATE_MARKER", result.stdout)
        self.assertFalse(self.path.exists())
        with self.assertRaisesRegex(budget.BudgetError, "RegisteredLedgerRequired"):
            with budget.Ledger(self.path, existing_only=True):
                self.fail("missing registered ledger opened")
        self.assertFalse(self.path.exists())
        REPORTS.append({"case": "cli-missing-registered-ledger", "report": {"exit": result.returncode,
                        "error": "RegisteredLedgerRequired", "directoryCreated": False}})


class BillingEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global IDENTITY
        required = ("SWIRL_PRIVATE_WORKER", "SWIRL_PRIVATE_EXPECTED_SOURCE", "SWIRL_PRIVATE_EXPECTED_WORKER_SHA256")
        if any(not os.environ.get(key) for key in required):
            raise RuntimeError("PairedPrivateWorkerEnvironmentRequired")
        IDENTITY = supervisor.WorkerIdentity.inspect(Path(os.environ[required[0]]), os.environ[required[1]], os.environ[required[2]])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "billing"
        self.ledger = budget.Ledger(self.path).__enter__()
        self.ledger.initialize_synthetic()
        self.authority = billing.SyntheticBillingAuthority()
        self.session = billing.BillingSession.register(self.ledger, self.authority)
        self.runner = supervisor.Supervisor(self.ledger, IDENTITY, self.session)

    def tearDown(self):
        self.ledger.__exit__()
        self.temp.cleanup()

    def save(self, name, report):
        REPORTS.append({"case": name, "report": report})

    def cli(self, directory):
        command = [sys.executable, str(TOOLS / "PrivateSubscriptionSupervisor.py"), "--synthetic-billing",
                   "--state-dir", str(directory), "--worker", str(IDENTITY.path),
                   "--worker-sha256", IDENTITY.sha256, "--expected-source", IDENTITY.metadata["source_sha"],
                   "--workload", "core_probe"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_actual_cli_existing_offline_schemas_remain_byte_identical(self):
        for schema in (1, 2):
            with self.subTest(schema=schema):
                directory = self.path.with_name("offline-" + str(schema))
                with budget.Ledger(directory) as ledger:
                    ledger.initialize("upload=100;download=200;total=100000000000")
                    ledger.data["schema"] = schema
                    ledger._save()
                    ledger.reserve_offline(1)
                paths = [directory / "traffic-budget.json", directory / "traffic-budget.lock"]
                before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
                result = self.cli(directory)
                self.assertEqual(result, {"error": "SyntheticLedgerRequired", "liveReady": False})
                self.assertEqual([hashlib.sha256(path.read_bytes()).hexdigest() for path in paths], before)
                self.save("cli-offline-schema-" + str(schema), {**result, "ledgerAndMarkerUnchanged": True})

    def test_actual_cli_cannot_reregister_schema_four_or_refund_its_hold(self):
        control(self.ledger, self.session)
        amount = self.ledger.summary()["heldBytes"]
        before = hashlib.sha256(self.ledger.path.read_bytes()).hexdigest()
        self.ledger.__exit__()
        try:
            result = self.cli(self.path)
        finally:
            self.ledger = budget.Ledger(self.path, existing_only=True).__enter__()
        self.assertEqual(result, {"error": "OriginalBillingSessionUnavailable", "liveReady": False})
        self.assertEqual(hashlib.sha256(self.ledger.path.read_bytes()).hexdigest(), before)
        self.assertEqual(self.ledger.summary()["heldBytes"], amount)
        self.assertFalse(self.ledger.summary()["syntheticBilling"]["currentSessionRegistered"])
        self.save("cli-schema-four-no-anchor", {**result, "ledgerUnchanged": True, "heldBytes": amount})

    def test_real_tls_core_probe_and_post_exit_billing_form_one_chain(self):
        report = self.runner.run("core_probe", timeout_ms=3000)
        self.save("tls-core-probe-billing", report)
        self.assertTrue(report["settled"], report["outcome"])
        self.assertEqual(report["metrics"]["http_status"], 204)
        self.assertEqual(report["guard"]["connection_attempts"], 2)
        self.assertEqual(len(report["controlQueries"]), 2)
        control_charge = billing.BYTE_LIMIT + 2 * budget.TCP_RECEIVE_RESERVATION
        for query in report["controlQueries"]:
            self.assertTrue(query["controlConsumed"])
            self.assertTrue(query["billingObservationAccepted"])
            self.assertEqual(query["guard"]["connection_attempts"], 2)
            self.assertEqual(query["controlDebit"], control_charge)
            self.assertLess(query["guard"]["upload"] + query["guard"]["download"], control_charge)
            self.assertTrue(query["exit"]["ownedProcessSetEmpty"])
            self.assertTrue(query["cleanupConfirmed"])
        state = report["ledger"]
        self.assertEqual(state["syntheticBilling"]["controlDebitedBytes"], 2 * control_charge)
        self.assertEqual(state["heldBytes"], 0)
        self.assertEqual(state["attempts"], 1)
        self.assertEqual(state["guardedBytes"], 2 * control_charge + state["localUpload"] + state["localDownload"])
        self.assertIsNone(state["baselineUsed"])
        self.assertIsNone(state["billingDelta"])
        self.assertFalse(state["providerStatisticsAuthenticated"])
        self.assertFalse(state["liveReady"])
        with mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("unchanged node retried")):
            with self.assertRaisesRegex(budget.BudgetError, "ConfigurationAlreadyAttempted"):
                self.runner.run("core_probe", timeout_ms=3000)

    def test_lag_and_other_clients_keep_hold_until_explicit_coverage_without_attribution(self):
        self.authority.auto_cover = False
        report = self.runner.run("core_probe", timeout_ms=3000)
        self.save("billing-coverage-pending", report)
        self.assertFalse(report["settled"])
        self.assertEqual(report["outcome"], "SyntheticBillingCoveragePending")
        ticket = report["reservation_id"]
        h = self.ledger.data["history"][ticket]
        self.assertEqual(h["phase"], "reconcile_pending")
        held = report["plan"]["byteLimit"] + report["plan"]["receiveReservation"]
        self.assertEqual(self.ledger.summary()["heldBytes"], held)
        self.assertEqual(self.ledger.summary()["localUpload"] + self.ledger.summary()["localDownload"], 0)
        self.assertEqual(self.ledger.summary()["syntheticBilling"]["activeProcessSlots"], 0)
        self.authority.add_other_client_usage(download=50_000_000)
        # A later fresh equal-coverage snapshot must still not settle.
        pending = self.runner.reconcile(ticket, timeout_ms=3000)
        self.assertFalse(pending["settled"])
        self.assertEqual(pending["ledger"]["heldBytes"], held)
        self.authority.cover_exit(h["billing"]["exitSequence"])
        settled = self.runner.reconcile(ticket, timeout_ms=3000)
        self.save("billing-later-coverage", settled)
        self.assertTrue(settled["settled"])
        state = settled["ledger"]
        local = report["guard"]["upload"] + report["guard"]["download"]
        self.assertEqual(state["localUpload"] + state["localDownload"], local)
        self.assertEqual(state["syntheticBilling"]["accountDelta"], 50_000_000)
        self.assertEqual(state["guardedBytes"], 50_000_000 + local + state["syntheticBilling"]["controlDebitedBytes"])
        before = self.ledger.path.read_bytes()
        with mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("duplicate reconcile spawned")):
            with self.assertRaises(budget.BudgetError):
                self.runner.reconcile(ticket)
        self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_bad_tls_identity_headers_and_body_never_start_node_or_refund_control(self):
        faults = ("bad_ca", "wrong_sni", "expired_certificate", "wrong_account", "wrong_period", "wrong_nonce",
                  "unauthorized", "redirect", "duplicate_header", "unknown_header", "extra_body",
                  "oversized_header", "transfer_encoding", "nonzero_content_length", "noncanonical_number")
        for index, fault in enumerate(faults):
            with self.subTest(fault=fault):
                self.authority.fault_next(fault)
                report = self.runner.run("core_probe", node=index + 1, timeout_ms=3000)
                self.save("billing-rejection-" + fault, report)
                self.assertFalse(report["settled"])
                self.assertFalse(report["nodeStarted"])
                self.assertEqual(report["ledger"]["attempts"], 0)
                self.assertEqual(len(report["controlQueries"]), 1)
                query = report["controlQueries"][0]
                self.assertFalse(query["billingObservationAccepted"])
                self.assertTrue(query["controlConsumed"], query["outcome"])
                self.assertEqual(query["controlDebit"], billing.BYTE_LIMIT + 2 * budget.TCP_RECEIVE_RESERVATION)
                self.assertEqual(query["fixture"]["acceptedConnections"], 2)
                self.assertEqual(query["guard"]["connection_attempts"], 2)
                self.assertTrue(query["guard"]["stopped"])
                self.assertTrue(query["cleanupConfirmed"])
                self.assertTrue(query["exit"]["processSignaled"])
                if fault in {"bad_ca", "wrong_sni", "expired_certificate"}:
                    self.assertIsNone(query["fixture"]["httpStatus"])
                    self.assertFalse(query["fixture"]["billingRequestReceived"])
                else:
                    self.assertTrue(query["fixture"]["billingRequestReceived"])
                    self.assertEqual(query["fixture"]["billingRequestAuthenticated"], fault != "unauthorized")
                    self.assertEqual(query["fixture"]["httpStatus"], 401 if fault == "unauthorized" else 302 if fault == "redirect" else 200)
                self.assertEqual(report["ledger"]["heldBytes"], 0)

    def test_counter_rollback_and_stale_revision_do_not_release_pending(self):
        self.authority.auto_cover = False
        first = self.runner.run("core_probe", timeout_ms=3000)
        ticket, held = first["reservation_id"], first["ledger"]["heldBytes"]
        for fault in ("old_revision", "counter_reset"):
            self.authority.fault_next(fault)
            result = self.runner.reconcile(ticket, timeout_ms=3000)
            self.save("post-exit-" + fault, result)
            self.assertFalse(result["settled"])
            self.assertEqual(result["outcome"], "SyntheticBillingCounterRegression")
            self.assertEqual(result["ledger"]["heldBytes"], held)
            self.assertEqual(self.ledger.data["history"][ticket]["phase"], "reconcile_pending")

    def test_expired_actual_response_cannot_authorize_node(self):
        original = self.session.observation
        def late(query, exchange):
            time.sleep(billing.MAX_FRESHNESS_SECONDS + 0.05)
            return original(query, exchange)
        with mock.patch.object(self.session, "observation", side_effect=late):
            report = self.runner.run("core_probe", timeout_ms=3000)
        self.save("billing-observation-expired", report)
        self.assertFalse(report["nodeStarted"])
        self.assertEqual(report["outcome"], "SyntheticBillingObservationExpired")
        self.assertTrue(report["controlQueries"][0]["controlConsumed"])

    def test_reservation_commit_failure_prevents_every_workload_spawn(self):
        with mock.patch.object(budget.os, "replace", side_effect=OSError("injected reservation write")), \
             mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("spawn before durable reserve")):
            with self.assertRaises(OSError):
                self.runner.run("core_probe")
        with self.assertRaisesRegex(budget.BudgetError, "LedgerCommitUncertain"):
            self.ledger.summary()
        disk = json.loads(self.ledger.path.read_text())
        self.assertEqual(disk["sequence"], 0)
        self.assertEqual(disk["billing"]["controlAttempts"], 0)

    def test_pending_commit_failure_retains_durable_active_full_hold(self):
        replace = budget.os.replace
        def fail_pending(source, target):
            if any(h["phase"] == "reconcile_pending" for h in self.ledger.data["history"].values()):
                raise OSError("injected pending write")
            return replace(source, target)
        with mock.patch.object(budget.os, "replace", side_effect=fail_pending):
            with self.assertRaises(OSError):
                self.runner.run("core_probe", timeout_ms=3000)
        durable = json.loads(self.ledger.path.read_text())
        nodes = [h for h in durable["history"].values() if h["node"]]
        self.assertEqual([h["phase"] for h in nodes], ["active"])
        self.assertEqual(len(durable["reservations"]), 1)
        self.assertEqual(durable["localUpload"] + durable["localDownload"], 0)
        self.assertEqual(durable["billing"]["controlAttempts"], 1)
        with self.assertRaisesRegex(budget.BudgetError, "LedgerCommitUncertain"):
            self.ledger.summary()

    def test_settlement_commit_failure_reopen_keeps_full_hold_and_no_exit_json_reissue(self):
        replace = budget.os.replace
        def fail_settle(source, target):
            if any(h["phase"] == "settled" for h in self.ledger.data["history"].values()):
                raise OSError("injected settlement write")
            return replace(source, target)
        with mock.patch.object(budget.os, "replace", side_effect=fail_settle):
            with self.assertRaises(OSError):
                self.runner.run("core_probe", timeout_ms=3000)
        durable = self.ledger.path.read_bytes()
        self.ledger.__exit__()
        self.ledger = budget.Ledger(self.path).__enter__()
        self.assertEqual(self.ledger.path.read_bytes(), durable)
        self.assertEqual(self.ledger.summary()["syntheticBilling"]["pendingReconciliation"], 1)
        self.assertGreater(self.ledger.summary()["heldBytes"], 0)
        self.assertEqual(self.ledger.summary()["localUpload"] + self.ledger.summary()["localDownload"], 0)
        self.assertEqual(self.ledger.summary()["syntheticBilling"]["controlAttempts"], 2)
        with mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("recovery spawned")):
            with self.assertRaisesRegex(budget.BudgetError, "OriginalBillingSessionUnavailable"):
                billing.BillingSession.register(self.ledger)
        self.assertEqual(self.ledger.path.read_bytes(), durable)

    def test_cleanup_failure_keeps_control_hold_and_blocks_node(self):
        original = supervisor._OwnedFixture.close
        def fail_close(fixture):
            original(fixture)
            raise budget.BudgetError("FixtureExitUnconfirmed")
        with mock.patch.object(supervisor._OwnedFixture, "close", fail_close):
            report = self.runner.run("core_probe", timeout_ms=3000)
        self.save("billing-cleanup-unconfirmed", report)
        self.assertFalse(report["nodeStarted"])
        self.assertFalse(report["controlQueries"][0]["controlConsumed"])
        self.assertEqual(report["ledger"]["syntheticBilling"]["controlDebitedBytes"], 0)
        self.assertEqual(report["ledger"]["heldBytes"], billing.BYTE_LIMIT + 2 * budget.TCP_RECEIVE_RESERVATION)

    def test_billing_request_external_deadline_cannot_be_extended(self):
        self.authority.fault_next("delayed_response")
        started = time.monotonic()
        report = self.runner.run("core_probe", timeout_ms=400)
        self.save("billing-hard-deadline", report)
        self.assertFalse(report["nodeStarted"])
        self.assertLess(time.monotonic() - started, 3)
        self.assertTrue(report["controlQueries"][0]["fixture"]["billingRequestAuthenticated"])
        self.assertGreaterEqual(report["controlQueries"][0]["parentElapsedMs"], 300)
        state = report["ledger"]
        amount = billing.BYTE_LIMIT + 2 * budget.TCP_RECEIVE_RESERVATION
        self.assertEqual(state["heldBytes"] + state["syntheticBilling"]["controlDebitedBytes"], amount)
        self.assertEqual(state["attempts"], 0)

    def test_three_nodes_and_control_queries_share_three_slots_without_refund_deadlock(self):
        original = self.runner._execute_reserved
        barrier = threading.Barrier(3)
        active = []
        def synchronized(ticket, workload, *args, **kwargs):
            with self.ledger.mutex:
                active.append(self.ledger._active_reservations())
            if workload == "core_probe":
                barrier.wait(timeout=8)
            return original(ticket, workload, *args, **kwargs)
        with mock.patch.object(self.runner, "_execute_reserved", side_effect=synchronized):
            with ThreadPoolExecutor(max_workers=3) as pool:
                reports = list(pool.map(lambda node: self.runner.run("core_probe", node=node, timeout_ms=3000), (1, 2, 3)))
        for report in reports:
            self.save("concurrent-billing-node", report)
            self.assertTrue(report["settled"], report["outcome"])
        self.assertEqual(max(active), 3)
        self.assertEqual(self.ledger.summary()["attempts"], 3)
        self.assertEqual(self.ledger.summary()["syntheticBilling"]["controlAttempts"], 6)
        self.assertEqual(self.ledger.summary()["heldBytes"], 0)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=False)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    with (args.evidence / "billing-tests.log").open("x", encoding="utf-8") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    report = {"schema": 1, "scope": billing.DOMAIN, "collected": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
              "source_sha": None if IDENTITY is None else IDENTITY.metadata["source_sha"],
              "worker_sha256": None if IDENTITY is None else IDENTITY.sha256,
              "cases": REPORTS, "providerRequests": 0, "realNodeRequests": 0, "liveReady": False,
              "officialAccountStatistics": None, "externalHistoryAnchor": False}
    (args.evidence / "billing-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
