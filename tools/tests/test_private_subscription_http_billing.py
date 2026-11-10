"""Actual guarded TLS counter observations, without provider authorization.

Only the parent's fixed synthetic fixture is used. The original billing tests
remain a separate dependency; this file does not replace their assertions.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import PrivateSubscriptionBilling as billing
import PrivateSubscriptionBudget as budget
import PrivateSubscriptionSupervisor as supervisor

IDENTITY = None
REPORTS = []
CONTROL_CHARGE = billing.BYTE_LIMIT + billing.CONNECTION_LIMIT * budget.TCP_RECEIVE_RESERVATION


def raw_payload():
    return {"schema": 1, "contract": billing.HTTP_RESPONSE_CONTRACT, "scope": billing.HTTP_OBSERVATION_SCOPE,
            "query_nonce": "a" * 64,
            "counters": {"upload": 10, "download": 20, "total": 200_000_000_000, "expire": None},
            "http_metadata": {"date": None, "age": None, "cache_control": None}}


class HttpBillingBoundaryTests(unittest.TestCase):
    def test_plain_counters_dates_and_tls_flags_are_not_authority(self):
        value = raw_payload()
        billing.validate_http_observation(value)
        for mutation in (
            lambda item: item.update(fresh=True),
            lambda item: item.update(tls_verified=True),
            lambda item: item.update(account_id="a" * 64),
            lambda item: item.update(covered_sequence=1),
            lambda item: item["counters"].update(upload=True),
            lambda item: item["http_metadata"].update(age=False),
        ):
            invalid = copy.deepcopy(value)
            mutation(invalid)
            with self.assertRaises(budget.BudgetError):
                billing.validate_http_observation(invalid)
        with self.assertRaisesRegex(budget.BudgetError, "HttpBillingObservationRequired"):
            billing.HttpBillingObservation(None, None, None, value, time.monotonic())
        with self.assertRaisesRegex(budget.BudgetError, "SyntheticBillingObservationRequired"):
            billing.BillingObservation(None, None, None, value, time.monotonic())
        self.assertFalse(issubclass(billing.HttpBillingObservation, billing.BillingObservation))

    def test_live_refuses_new_contract_before_any_path_or_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "must-not-exist"
            output = io.StringIO()
            with mock.patch.object(supervisor.WorkerIdentity, "inspect", side_effect=AssertionError("spawn")), \
                 mock.patch.object(billing.BillingSession, "register", side_effect=AssertionError("register")), \
                 contextlib.redirect_stdout(output):
                code = supervisor.main(["--live", "--synthetic-billing", "--billing-response-contract",
                                        billing.HTTP_RESPONSE_CONTRACT, "--state-dir", str(missing)])
            self.assertEqual(code, 2)
            self.assertFalse(missing.exists())
            self.assertEqual(json.loads(output.getvalue())["error"], "AuthenticatedBillingAndWireGuardRequired")


class HttpBillingEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global IDENTITY
        keys = ("SWIRL_PRIVATE_WORKER", "SWIRL_PRIVATE_EXPECTED_SOURCE", "SWIRL_PRIVATE_EXPECTED_WORKER_SHA256")
        if any(not os.environ.get(key) for key in keys):
            raise RuntimeError("PairedPrivateWorkerEnvironmentRequired")
        IDENTITY = supervisor.WorkerIdentity.inspect(Path(os.environ[keys[0]]), os.environ[keys[1]], os.environ[keys[2]])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "billing"
        self.ledger = budget.Ledger(self.path).__enter__()
        self.ledger.initialize_synthetic()
        self.authority = billing.SyntheticBillingAuthority()
        self.session = billing.BillingSession.register(self.ledger, self.authority)
        self.runner = supervisor.Supervisor(self.ledger, IDENTITY, self.session,
                                            billing_response_contract=billing.HTTP_RESPONSE_CONTRACT)

    def tearDown(self):
        self.ledger.__exit__()
        self.temp.cleanup()

    def save(self, name, report):
        REPORTS.append({"case": name, "report": report})

    def assert_control(self, query, *, observed):
        self.assertTrue(query["cleanupConfirmed"], query["outcome"])
        self.assertTrue(query["exit"]["ownedProcessSetEmpty"])
        self.assertTrue(query["controlConsumed"])
        self.assertEqual(query["controlDebit"], CONTROL_CHARGE)
        self.assertFalse(query["controlDebitIsMeasuredTraffic"])
        self.assertFalse(query["billingObservationAccepted"])
        self.assertEqual(query["httpObservationRecorded"], observed)
        self.assertEqual(query["guard"]["connection_attempts"], 2)
        self.assertTrue(query["guard"]["stopped"])
        self.assertGreater(query["guard"]["upload"] + query["guard"]["download"], 100)
        self.assertLess(query["guard"]["upload"] + query["guard"]["download"], CONTROL_CHARGE)

    def test_actual_tls_counters_reach_same_ledger_but_never_start_node(self):
        report = self.runner.run("core_probe", timeout_ms=3000)
        self.save("http-counters-preflight", report)
        self.assertFalse(report["nodeStarted"])
        self.assertFalse(report["settled"])
        self.assertEqual(report["outcome"], "ProviderAccountBindingUnproven")
        query = report["controlQueries"][0]
        self.assert_control(query, observed=True)
        self.assertEqual(query["fixture"]["httpStatus"], 200)
        self.assertTrue(query["fixture"]["billingRequestAuthenticated"])
        raw = query["httpObservation"]
        self.assertEqual(raw["counters"], {"upload": 1000, "download": 2000, "total": 200_000_000_000, "expire": None})
        history = self.ledger.data["history"][query["reservation_id"]]
        self.assertEqual(history["billing"]["responseContract"], billing.HTTP_RESPONSE_CONTRACT)
        self.assertEqual(history["receipt"]["httpObservation"], raw)
        self.assertIsNone(history["receipt"]["observation"])
        self.assertIsNone(self.ledger.data["billing"]["baselineQuery"])
        self.assertIsNone(self.ledger.data["billing"]["latestQuery"])
        self.assertEqual(report["ledger"]["attempts"], 0)
        self.assertEqual(report["ledger"]["heldBytes"], 0)
        self.assertEqual(report["ledger"]["guardedBytes"], CONTROL_CHARGE)
        self.assertIsNone(report["ledger"]["billingDelta"])
        self.assertIsNone(report["ledger"]["syntheticBilling"]["accountDelta"])
        self.assertFalse(report["ledger"]["providerStatisticsAuthenticated"])
        self.assertEqual(json.loads(self.ledger.path.read_text())["history"][query["reservation_id"]], history)

    def test_dates_equal_counts_and_zero_age_cannot_create_admission(self):
        counts = []
        for index, date in enumerate(("Thu, 01 Jan 1970 00:00:00 GMT", "Fri, 01 Jan 2100 00:00:00 GMT", "not-a-date"), 1):
            self.authority.http_metadata_next(date=date, age=0, cache_control="no-store", expire=0)
            report = self.runner.run("core_probe", node=index, timeout_ms=3000)
            self.save("http-metadata-is-not-authorization", report)
            query = report["controlQueries"][0]
            self.assert_control(query, observed=True)
            self.assertFalse(report["nodeStarted"])
            self.assertEqual(query["httpObservation"]["http_metadata"], {"date": date, "age": 0, "cache_control": "no-store"})
            counts.append(query["httpObservation"]["counters"])
        self.assertEqual(counts, [counts[0]] * 3)
        self.assertEqual(self.ledger.summary()["syntheticBilling"]["controlDebitedBytes"], 3 * CONTROL_CHARGE)
        self.assertIsNone(self.ledger.data["billing"]["baselineQuery"])
        self.assertEqual(self.ledger.summary()["attempts"], 0)

    def test_real_exited_node_remains_pending_after_http_query_and_type_confusion(self):
        self.authority.auto_cover = False
        modeled = supervisor.Supervisor(self.ledger, IDENTITY, self.session)
        initial = modeled.run("core_probe", timeout_ms=3000)
        self.save("model-exit-pending-before-http", initial)
        self.assertFalse(initial["settled"])
        self.assertEqual(initial["outcome"], "SyntheticBillingCoveragePending")
        ticket = initial["reservation_id"]
        held = self.ledger.summary()["heldBytes"]
        old_queries = {key: self.ledger.data["billing"][key] for key in ("baselineQuery", "latestQuery")}
        self.authority.cover_exit(self.ledger.data["history"][ticket]["billing"]["exitSequence"])
        self.authority.add_other_client_usage(download=50_000_000)
        self.authority.http_metadata_next(date="Fri, 01 Jan 2100 00:00:00 GMT", age=0, cache_control="no-store")
        report = self.runner.reconcile(ticket, timeout_ms=3000)
        self.save("http-counters-cannot-release-real-exit-hold", report)
        self.assertFalse(report["settled"])
        self.assertEqual(report["outcome"], "ProviderAccountBindingUnproven")
        query = report["controlQueries"][0]
        self.assert_control(query, observed=True)
        self.assertEqual(query["httpObservation"]["counters"]["download"], 50_002_000)
        self.assertEqual(self.ledger.summary()["heldBytes"], held)
        self.assertEqual(self.ledger.data["history"][ticket]["phase"], "reconcile_pending")
        self.assertEqual({key: self.ledger.data["billing"][key] for key in old_queries}, old_queries)
        self.assertEqual(self.ledger.summary()["syntheticBilling"]["accountDelta"], 0)
        self.assertEqual(self.ledger.summary()["localUpload"] + self.ledger.summary()["localDownload"], 0)
        raw = self.session._http_observations[query["reservation_id"]]
        self.assertIsInstance(raw, billing.HttpBillingObservation)
        self.assertNotIsInstance(raw, billing.BillingObservation)
        before = self.ledger.path.read_bytes()
        for observation in (raw, raw.record(), {**raw.record(), "fresh": True, "account_matches": True}):
            with self.assertRaisesRegex(budget.BudgetError, "SyntheticBillingObservationRequired"):
                self.ledger.settle_billing_node(self.session, ticket, observation, self.session._pending_exits[ticket])
            with self.assertRaisesRegex(budget.BudgetError, "SyntheticBillingObservationRequired"):
                self.ledger.reserve_billing_node(self.session, observation, 2, 65536, 2, 2000,
                    config_fingerprint="f" * 64, **self.runner._identity_fields(), nonce=secrets.token_hex(32), workload="core_probe")
        self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_malformed_http_reaches_real_authenticated_stage_and_consumes_control_only(self):
        faults = ("missing_userinfo", "duplicate_parameter", "unknown_parameter", "forged_coverage",
                  "duplicate_header", "noncanonical_number", "extra_body", "redirect")
        for index, fault in enumerate(faults, 1):
            with self.subTest(fault=fault):
                self.authority.fault_next(fault)
                report = self.runner.run("core_probe", node=index, timeout_ms=3000)
                self.save("http-rejected-" + fault, report)
                query = report["controlQueries"][0]
                self.assert_control(query, observed=False)
                self.assertFalse(report["nodeStarted"])
                self.assertEqual(report["outcome"], "BillingSnapshotFailed")
                self.assertTrue(query["fixture"]["billingRequestReceived"])
                self.assertTrue(query["fixture"]["billingRequestAuthenticated"])
                self.assertEqual(query["fixture"]["httpStatus"], 302 if fault == "redirect" else 200)
        self.assertEqual(self.ledger.summary()["syntheticBilling"]["controlDebitedBytes"], len(faults) * CONTROL_CHARGE)
        self.assertEqual(self.ledger.summary()["attempts"], 0)
        self.assertIsNone(self.ledger.data["billing"]["latestQuery"])

    def test_cleanup_failure_prevents_observation_and_retains_control_hold(self):
        close = supervisor._OwnedFixture.close
        def failed_cleanup(fixture):
            close(fixture)
            raise budget.BudgetError("FixtureExitUnconfirmed")
        with mock.patch.object(supervisor._OwnedFixture, "close", failed_cleanup):
            report = self.runner.run("core_probe", timeout_ms=3000)
        self.save("http-cleanup-unconfirmed", report)
        self.assertFalse(report["nodeStarted"])
        query = report["controlQueries"][0]
        self.assertFalse(query["cleanupConfirmed"])
        self.assertFalse(query["controlConsumed"])
        self.assertFalse(query["httpObservationRecorded"])
        self.assertTrue(query["exit"]["ownedProcessSetEmpty"])
        self.assertEqual(report["ledger"]["heldBytes"], CONTROL_CHARGE)
        self.assertEqual(report["ledger"]["syntheticBilling"]["controlDebitedBytes"], 0)
        self.assertIsNone(self.ledger.data["history"][query["reservation_id"]]["receipt"])

    def test_actual_control_commit_failure_keeps_durable_hold_after_real_exit(self):
        backend = self.ledger.windows if self.ledger.windows else budget.os
        replace = backend.replace
        execution = self.runner._execute_reserved
        observed = []
        def capture(*args, **kwargs):
            result = execution(*args, **kwargs)
            observed.append(result)
            return result
        def fail_consumed(source, target):
            if any(item["phase"] == "control_consumed" for item in self.ledger.data["history"].values()):
                raise OSError("injected HTTP control commit")
            return replace(source, target)
        with mock.patch.object(backend, "replace", side_effect=fail_consumed), \
             mock.patch.object(self.runner, "_execute_reserved", side_effect=capture):
            with self.assertRaisesRegex(OSError, "injected HTTP control commit"):
                self.runner.run("core_probe", timeout_ms=3000)
        self.assertEqual(len(observed), 1)
        self.assertTrue(observed[0].complete)
        self.assertTrue(observed[0].cleanup)
        self.assertTrue(observed[0].exit_proof.record()["ownedProcessSetEmpty"])
        with self.assertRaisesRegex(budget.BudgetError, "LedgerCommitUncertain"):
            self.ledger.summary()
        durable = self.ledger.path.read_bytes()
        disk = json.loads(durable)
        self.assertEqual(disk["history"]["1"]["phase"], "active")
        self.assertIsNone(disk["history"]["1"]["receipt"])
        self.assertEqual(disk["billing"]["controlDebitedBytes"], 0)
        self.assertEqual(disk["reservations"]["1"]["held"], CONTROL_CHARGE)
        self.ledger.__exit__()
        self.ledger = budget.Ledger(self.path, existing_only=True).__enter__()
        self.assertEqual(self.ledger.summary()["heldBytes"], CONTROL_CHARGE)
        with self.assertRaisesRegex(budget.BudgetError, "OriginalBillingSessionUnavailable"):
            billing.BillingSession.register(self.ledger)
        self.assertEqual(self.ledger.path.read_bytes(), durable)
        self.save("http-control-commit-failure", {"execution": observed[0].record, "durablePhase": "active",
            "durableReceipt": None, "heldBytes": CONTROL_CHARGE, "reopenedSessionRefused": True,
            "backend": "windows-replace" if self.ledger.windows else "posix-replace"})

    def test_actual_cli_http_observation_survives_reopen_without_reauthorization(self):
        directory = self.path.with_name("cli-existing-synthetic")
        with budget.Ledger(directory) as ledger:
            ledger.initialize_synthetic()
        command = [sys.executable, str(TOOLS / "PrivateSubscriptionSupervisor.py"), "--synthetic-billing",
                   "--billing-response-contract", billing.HTTP_RESPONSE_CONTRACT,
                   "--state-dir", str(directory), "--worker", str(IDENTITY.path),
                   "--worker-sha256", IDENTITY.sha256, "--expected-source", IDENTITY.metadata["source_sha"],
                   "--workload", "core_probe", "--timeout-ms", "3000"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.save("http-observation-actual-cli", report)
        self.assertEqual(report["outcome"], "ProviderAccountBindingUnproven")
        self.assertFalse(report["nodeStarted"])
        self.assert_control(report["controlQueries"][0], observed=True)
        with budget.Ledger(directory, existing_only=True) as ledger:
            durable = ledger.path.read_bytes()
            self.assertEqual(ledger.summary()["syntheticBilling"]["controlDebitedBytes"], CONTROL_CHARGE)
            self.assertIsNone(ledger.data["billing"]["baselineQuery"])
            self.assertIsNotNone(ledger.data["history"]["1"]["receipt"]["httpObservation"])
            with self.assertRaisesRegex(budget.BudgetError, "OriginalBillingSessionUnavailable"):
                billing.BillingSession.register(ledger)
            self.assertEqual(ledger.path.read_bytes(), durable)

    def test_contract_choice_cannot_introduce_a_provider_or_spawn_before_validation(self):
        before = self.ledger.path.read_bytes()
        with mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("unexpected child")):
            for contract in ("official", True, None, {"fresh": True}):
                with self.subTest(contract=type(contract).__name__), self.assertRaisesRegex(budget.BudgetError, "BillingResponseContractRejected"):
                    supervisor.Supervisor(self.ledger, IDENTITY, self.session, billing_response_contract=contract)
        self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_actual_cli_legacy_contract_retains_sealed_execution_identity(self):
        directory = self.path.with_name("legacy-cli-existing-synthetic")
        with budget.Ledger(directory) as ledger:
            ledger.initialize_synthetic()
        command = [sys.executable, str(TOOLS / "PrivateSubscriptionSupervisor.py"), "--synthetic-billing",
                   "--state-dir", str(directory), "--worker", str(IDENTITY.path),
                   "--worker-sha256", IDENTITY.sha256, "--expected-source", IDENTITY.metadata["source_sha"],
                   "--workload", "core_probe", "--timeout-ms", "3000"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.save("legacy-billing-actual-cli-sealed-types", report)
        self.assertTrue(report["nodeStarted"])
        self.assertTrue(report["settled"])
        self.assertEqual(report["metrics"]["http_status"], 204)
        self.assertEqual(len(report["controlQueries"]), 2)
        self.assertTrue(all(query["billingObservationAccepted"] for query in report["controlQueries"]))
        self.assertEqual(report["ledger"]["heldBytes"], 0)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=False)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    with (args.evidence / "http-billing-tests.log").open("x", encoding="utf-8") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    report = {"schema": 1, "scope": billing.HTTP_OBSERVATION_SCOPE, "collected": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
              "source_sha": None if IDENTITY is None else IDENTITY.metadata["source_sha"],
              "worker_sha256": None if IDENTITY is None else IDENTITY.sha256,
              "cases": REPORTS, "providerRequests": 0, "realNodeRequests": 0, "liveReady": False,
              "officialAccountStatistics": None, "providerAccountAuthorization": "unimplemented",
              "externalHistoryAnchor": False}
    (args.evidence / "http-billing-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
