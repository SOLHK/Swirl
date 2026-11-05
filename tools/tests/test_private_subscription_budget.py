"""Offline accounting and real process-lock tests; zero provider requests."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

MODULE = Path(__file__).parents[1] / "PrivateSubscriptionBudget.py"
spec = importlib.util.spec_from_file_location("private_budget", MODULE)
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)

BASE = "upload=100000000; download=900000000; total=100000000000"


class PolicyTests(unittest.TestCase):
    def test_decimal_thresholds_and_package_reserve(self):
        for consumed, code in ((0, "WithinNormalTarget"), (2, "NormalTargetReached"),
                               (5, "ReviewRequired"), (10, "NoExpansion"),
                               (15, "MandatoryStop"), (20, "AbsoluteLimit")):
            with self.subTest(consumed=consumed):
                self.assertEqual(budget.policy(consumed * budget.GB, 0, 0, 100 * budget.GB), code)
        self.assertEqual(budget.policy(0, 0, 1, 80 * budget.GB), "PackageReserve")
        # Provider counters can lag; already-measured local traffic must also
        # preserve the user's 80 GB, without double-counting billed traffic.
        self.assertEqual(budget.policy(0, 1_500_000_000, 0, 81 * budget.GB), "PackageReserve")
        self.assertEqual(budget.policy(1_500_000_000, 1_500_000_000, 0, 81 * budget.GB), "WithinNormalTarget")
        self.assertEqual(budget.policy(15 * budget.GB, 0, 0, 79 * budget.GB), "MandatoryStop")
        self.assertEqual(budget.policy(0, 2 * budget.GB - 10, 10, 100 * budget.GB), "NormalTargetReached")

    def test_stats_are_strict_numeric_and_do_not_retain_unrelated_headers(self):
        expected = {"upload": 100000000, "download": 900000000, "total": 100000000000}
        self.assertEqual(budget.parse_userinfo(BASE + "; unrelated=PRIVATE_MARKER"), expected)
        invalid = [None, "", "upload=0; download=0", "upload=0; upload=1; download=0; total=2",
                   "upload=-1; download=0; total=100", "upload=1.5; download=0; total=100",
                   "upload=2; download=3; total=4", "upload=0; download=0; total=0",
                   "upload=18446744073709551615; download=0; total=9999999999999999999",
                   "upload=true; download=0; total=100", "upload=0; download=0; total=100; expire=-1"]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(budget.BudgetError):
                budget.parse_userinfo(value)
        for value in (True, -1, 1.5, None, "1"):
            with self.subTest(counter=value), self.assertRaises(budget.BudgetError):
                budget.policy(value, 0, 0, 100 * budget.GB)

    def test_execution_limits_remain_small(self):
        self.assertEqual((budget.MAX_CONCURRENT, budget.FIRST_ROUND, budget.TIMEOUT_MS, budget.BODY_LIMIT),
                         (3, 12, 8000, 65536))


@unittest.skipUnless(os.name == "posix", "Private storage adapter deliberately fails closed off POSIX")
class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / "private"

    def tearDown(self):
        self.temp.cleanup()

    def test_restart_keeps_baseline_counts_and_unsettled_reservations(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ticket = ledger.reserve_offline(1, 500)
            ledger.account_offline(ticket, upload=30, download=70)
            ledger.observe_provider("upload=100000050; download=900000250; total=100000000000")
            before = ledger.summary()
        with budget.Ledger(self.root) as ledger:
            self.assertEqual(ledger.summary(), before)
            self.assertEqual(before["billingDelta"], 300)
            self.assertEqual((before["localUpload"], before["localDownload"], before["heldBytes"]), (30, 70, 400))
            self.assertEqual(before["baselineUsed"], 1_000_000_000)
            with self.assertRaisesRegex(budget.BudgetError, "TaskAlreadyInitialized"):
                ledger.initialize("upload=0; download=0; total=100000000000")
            with self.assertRaisesRegex(budget.BudgetError, "UnreleasedRequests"):
                ledger.finish_offline(ticket)
            ledger.finish_offline(ticket, quiescent=True)
            self.assertEqual(ledger.summary()["heldBytes"], 0)
            self.assertEqual(ledger.summary()["attempts"], 1)

    def test_failed_process_cannot_reset_or_refund_its_reservation(self):
        # An actual abrupt exit bypasses finally/context-manager cleanup.
        program = """
import importlib.util, os, sys
spec=importlib.util.spec_from_file_location('budget', sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with m.Ledger(sys.argv[2]) as ledger:
 ledger.initialize(sys.argv[3])
 t=ledger.reserve_offline(3, 1024)
 ledger.account_offline(t, upload=23, download=31)
 os._exit(0)
"""
        child = subprocess.run([sys.executable, "-c", program, str(MODULE), str(self.root), BASE],
                               capture_output=True, timeout=10)
        self.assertEqual(child.returncode, 0, child.stderr.decode())
        with budget.Ledger(self.root) as ledger:
            state = ledger.summary()
            self.assertEqual((state["attempts"], state["heldBytes"], state["localUpload"], state["localDownload"]),
                             (1, 970, 23, 31))
            with self.assertRaisesRegex(budget.BudgetError, "NodeAlreadyReserved"):
                ledger.reserve_offline(3)

    def test_another_process_cannot_open_same_task(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            child = subprocess.run([sys.executable, str(MODULE), "status", "--state-dir", str(self.root)],
                                   capture_output=True, text=True, timeout=10)
            self.assertEqual(child.returncode, 2)
            self.assertEqual(json.loads(child.stdout)["error"], "AnotherAcceptanceProcessActive")
        child = subprocess.run([sys.executable, str(MODULE), "status", "--state-dir", str(self.root)],
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(child.returncode, 0, child.stderr)

    def test_unknown_bill_is_not_zero_and_cannot_be_late_reset(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize()
            state = ledger.summary()
            self.assertIsNone(state["billingDelta"])
            self.assertIsNone(state["remainingAbsoluteBudget"])
            self.assertEqual(state["policy"], "BillingUnavailable")
            with self.assertRaisesRegex(budget.BudgetError, "BillingUnavailable"):
                ledger.reserve_offline(1)
            with self.assertRaisesRegex(budget.BudgetError, "BaselineUnavailable"):
                ledger.observe_provider(BASE)
        with budget.Ledger(self.root) as ledger:
            self.assertIsNone(ledger.summary()["baselineUsed"])

    def test_billing_counter_rollback_or_changed_package_is_rejected(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            before = ledger.summary()
            for header in ("upload=99999999; download=900000000; total=100000000000",
                           "upload=100000000; download=899999999; total=100000000000",
                           "upload=100000000; download=900000000; total=200000000000"):
                with self.assertRaisesRegex(budget.BudgetError, "BillingCounterReset"):
                    ledger.observe_provider(header)
                self.assertEqual(ledger.summary(), before)

    def test_missing_ledger_cannot_create_new_zero_baseline(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
        (self.root / "traffic-budget.json").unlink()
        with self.assertRaisesRegex(budget.BudgetError, "LedgerMissingAfterInitialization"):
            with budget.Ledger(self.root):
                self.fail("missing persistent ledger was accepted")

    def test_private_modes_and_symlink_rejection(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.root / "traffic-budget.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.root / "traffic-budget.lock").stat().st_mode), 0o600)
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(budget.BudgetError, "PrivateDirectoryRequired"):
            with budget.Ledger(alias):
                self.fail("symlink accepted")
        (self.root / "traffic-budget.json").chmod(0o644)
        with self.assertRaisesRegex(budget.BudgetError, "PrivateLedgerRequired"):
            with budget.Ledger(self.root):
                self.fail("public ledger accepted")

    def test_invalid_ledger_not_auto_repaired(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
        file = self.root / "traffic-budget.json"
        original = json.loads(file.read_text())
        missing = original.copy()
        del missing["reservations"]
        corruptions = [missing, {**original, "task": "another-task"},
                       {**original, "localUpload": -1}, {**original, "attempts": True},
                       {**original, "attempts": 13, "sequence": 13},
                       {**original, "attempts": 1, "sequence": 0},
                       {**original, "reservations": {"PRIVATE_TOKEN": {}}}]
        for value in corruptions:
            file.write_text(json.dumps(value))
            with self.assertRaises(budget.BudgetError):
                with budget.Ledger(self.root):
                    self.fail("corrupt ledger accepted")
            self.assertEqual(json.loads(file.read_text()), value)

    def test_numeric_string_snapshots_rejected_on_entry(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE + "; expire=4102444800")
        file = self.root / "traffic-budget.json"
        value = json.loads(file.read_text())
        for snapshot in ("baseline", "provider"):
            value[snapshot] = {key: str(counter) for key, counter in value[snapshot].items()}
        file.write_text(json.dumps(value))
        corrupt = file.read_bytes()
        with self.assertRaisesRegex(budget.BudgetError, "InvalidCounter"):
            with budget.Ledger(self.root):
                pass
        self.assertEqual(file.read_bytes(), corrupt)

    def test_billing_snapshot_fields_require_integer_json_values(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE + "; expire=4102444800")
        file = self.root / "traffic-budget.json"
        original = file.read_bytes()
        for snapshot in ("baseline", "provider"):
            for field in ("upload", "download", "total", "expire"):
                counter = json.loads(original)[snapshot][field]
                for invalid in (str(counter), float(counter), True, False, None):
                    with self.subTest(snapshot=snapshot, field=field, invalid=invalid):
                        value = json.loads(original)
                        value[snapshot][field] = invalid
                        file.write_text(json.dumps(value))
                        corrupt = file.read_bytes()
                        with self.assertRaisesRegex(budget.BudgetError, "InvalidCounter"):
                            with budget.Ledger(self.root):
                                pass
                        self.assertEqual(file.read_bytes(), corrupt)
                        output, errors = io.StringIO(), io.StringIO()
                        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                            result = budget.main(["preflight", "--state-dir", str(self.root)])
                        self.assertEqual(result, 2)
                        self.assertEqual(json.loads(output.getvalue()), {"error": "InvalidCounter", "liveReady": False})
                        self.assertEqual(errors.getvalue(), "")
                        self.assertEqual(file.read_bytes(), corrupt)
        child = subprocess.run([sys.executable, str(MODULE), "status", "--state-dir", str(self.root)],
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(child.returncode, 2)
        self.assertEqual(json.loads(child.stdout), {"error": "InvalidCounter", "liveReady": False})
        self.assertEqual(child.stderr, "")
        self.assertEqual(file.read_bytes(), corrupt)

    def test_integer_snapshot_restoration_preserves_ledger(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE + "; expire=4102444800")
            ticket = ledger.reserve_offline(1, 256)
            ledger.account_offline(ticket, upload=16, download=32)
            ledger.observe_provider("upload=100000010; download=900000050; total=100000000000; expire=4102444900")
            before = ledger.summary()
        file = self.root / "traffic-budget.json"
        original = file.read_bytes()
        with budget.Ledger(self.root) as ledger:
            self.assertEqual(ledger.summary(), before)
            for snapshot in ("baseline", "provider"):
                self.assertEqual(set(ledger.data[snapshot]), {"upload", "download", "total", "expire"})
                self.assertTrue(all(type(counter) is int for counter in ledger.data[snapshot].values()))
            self.assertFalse(ledger.summary()["liveReady"])
        self.assertEqual(file.read_bytes(), original)

    def test_duplicate_json_key_and_invalid_json_never_rewrite_evidence(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
        file = self.root / "traffic-budget.json"
        original = file.read_text()
        for corrupt, code in ((original[:-1] + ',"attempts":0}', "DuplicateLedgerKey"),
                              ("{ PRIVATE_MARKER", "InvalidLedgerJson")):
            file.write_text(corrupt)
            with self.assertRaisesRegex(budget.BudgetError, code):
                with budget.Ledger(self.root):
                    self.fail("corrupt JSON accepted")
            self.assertEqual(file.read_text(), corrupt)

    def test_reservation_relations_are_validated_before_resume(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ledger.reserve_offline(1, 100)
            ledger.reserve_offline(2, 100)
        file = self.root / "traffic-budget.json"
        original = file.read_text()
        cases = []
        value = json.loads(original)
        value["reservations"]["2"]["node"] = 1
        cases.append(value)
        value = json.loads(original)
        value["reservations"]["3"] = value["reservations"].pop("2")
        cases.append(value)
        value = json.loads(original)
        value["reservations"]["1"]["sent"] = 1
        cases.append(value)
        value = json.loads(original)
        value["localUpload"] = budget.MAX_PROBE_RESERVATION
        value["reservations"]["1"]["sent"] = budget.MAX_PROBE_RESERVATION
        cases.append(value)
        value = json.loads(original)
        value["reservations"]["1"]["held"] = 0
        cases.append(value)
        for value in cases:
            file.write_text(json.dumps(value))
            with self.assertRaises(budget.BudgetError):
                with budget.Ledger(self.root):
                    self.fail("invalid reservation relationships accepted")
            self.assertEqual(json.loads(file.read_text()), value)

    def test_request_limit_concurrency_and_no_duplicate_inflight(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            first = ledger.reserve_offline(1, 100)
            with self.assertRaisesRegex(budget.BudgetError, "NodeAlreadyReserved"):
                ledger.reserve_offline(1)
            ledger.reserve_offline(2)
            ledger.reserve_offline(3)
            with self.assertRaisesRegex(budget.BudgetError, "ConcurrencyLimit"):
                ledger.reserve_offline(4)
            before = ledger.summary()
            with self.assertRaisesRegex(budget.BudgetError, "RequestByteLimit"):
                ledger.account_offline(first, upload=50, download=51)
            self.assertEqual(ledger.summary(), before)
            ledger.account_offline(first, upload=50, download=50)
            with self.assertRaisesRegex(budget.BudgetError, "RequestByteLimit"):
                ledger.account_offline(first, download=1)

    def test_first_round_and_restarts_never_expand_scope(self):
        for ordinal in range(1, 13):
            with budget.Ledger(self.root) as ledger:
                if ordinal == 1:
                    ledger.initialize(BASE)
                ticket = ledger.reserve_offline(ordinal, 128)
                ledger.finish_offline(ticket, quiescent=True)
        with budget.Ledger(self.root) as ledger:
            with self.assertRaisesRegex(budget.BudgetError, "FirstRoundComplete"):
                ledger.reserve_offline(13)
            self.assertEqual(ledger.summary()["attempts"], 12)

    def test_inflight_gate_stops_when_provider_limit_is_observed(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ticket = ledger.reserve_offline(1)
            ledger.observe_provider("upload=100000000; download=15900000000; total=100000000000")
            self.assertEqual(ledger.summary()["policy"], "MandatoryStop")
            with self.assertRaisesRegex(budget.BudgetError, "MandatoryStop"):
                ledger.account_offline(ticket, download=1)
            with self.assertRaisesRegex(budget.BudgetError, "MandatoryStop"):
                ledger.reserve_offline(2)

    def test_request_reservation_cannot_cross_normal_target(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ledger.observe_provider("upload=100000000; download=2899999999; total=100000000000")
            self.assertEqual(ledger.summary()["policy"], "WithinNormalTarget")
            with self.assertRaisesRegex(budget.BudgetError, "NormalTargetReached"):
                ledger.reserve_offline(1, 1)
            self.assertEqual(ledger.summary()["attempts"], 0)

    def test_known_stats_never_fake_native_readiness(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            state = ledger.summary()
            self.assertFalse(state["liveReady"])
            self.assertFalse(state["providerStatisticsAuthenticated"])
            self.assertFalse(state["wireAccountingAttached"])
            self.assertFalse(state["hardCancellationAttached"])
            with self.assertRaisesRegex(budget.BudgetError, "AuthenticatedBillingAndWireGuardRequired"):
                ledger.require_live_ready()
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(budget.main(["preflight", "--state-dir", str(self.root)]), 2)
        self.assertFalse(json.loads(stream.getvalue())["liveReady"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
