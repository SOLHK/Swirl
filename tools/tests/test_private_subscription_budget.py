"""Offline accounting and real process-lock tests; zero provider requests."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
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
from unittest import mock

MODULE = Path(__file__).parents[1] / "PrivateSubscriptionBudget.py"
spec = importlib.util.spec_from_file_location("private_budget", MODULE)
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)

BASE = "upload=100000000; download=900000000; total=100000000000"


class PolicyTests(unittest.TestCase):
    def test_delayed_local_usage_and_other_clients_cannot_share_budget_credit(self):
        # These observations may be disjoint: the provider has reported other
        # clients while this task's settled socket counts have not arrived yet.
        # No timestamp or attribution proof permits treating their overlap as
        # known. Test every task boundary with individually smaller observations.
        cases = ((1_100_000_000, 900_000_000, "NormalTargetReached"),
                 (4_000_000_000, 1_000_000_000, "ReviewRequired"),
                 (9_000_000_000, 1_000_000_000, "NoExpansion"),
                 (14_000_000_000, 1_000_000_000, "MandatoryStop"),
                 (19_000_000_000, 1_000_000_000, "AbsoluteLimit"))
        for billed, local, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(budget.policy(billed, local, 0, 100 * budget.GB), expected)
        # Even equal values do not establish that the same bytes were billed.
        self.assertEqual(budget.policy(600, 600, 0, budget.RESERVE_PACKAGE + 599), "PackageReserve")

    def test_decimal_thresholds_and_package_reserve(self):
        for consumed, code in ((0, "WithinNormalTarget"), (2, "NormalTargetReached"),
                               (5, "ReviewRequired"), (10, "NoExpansion"),
                               (15, "MandatoryStop"), (20, "AbsoluteLimit")):
            with self.subTest(consumed=consumed):
                self.assertEqual(budget.policy(consumed * budget.GB, 0, 0, 100 * budget.GB), code)
        self.assertEqual(budget.policy(0, 0, 1, 80 * budget.GB), "PackageReserve")
        # Provider counters can lag, and their growth may be other clients.
        # Without attribution evidence, retain all local traffic in headroom.
        self.assertEqual(budget.policy(0, 1_500_000_000, 0, 81 * budget.GB), "PackageReserve")
        self.assertEqual(budget.policy(1_500_000_000, 1_500_000_000, 0, 81 * budget.GB), "PackageReserve")
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

    def test_tcp_plan_includes_every_connection_receive_reserve(self):
        plan = budget.tcp_plan(65536, 3, 8000)
        self.assertEqual(plan, {"byteLimit": 65536, "connectionLimit": 3,
                                "receiveReservation": 3 * 1024 * 1024, "timeoutMs": 8000})
        maximum = budget.tcp_plan(budget.TCP_MAX_BYTES, budget.TCP_MAX_CONNECTIONS)
        self.assertEqual(maximum["byteLimit"] + maximum["receiveReservation"], 64 * 1024 * 1024)
        # A one-byte transfer still needs a full distinct kernel allowance;
        # the old 1 MiB reservation could not cover this minimum TCP plan.
        minimum = budget.tcp_plan(1, 1)
        self.assertGreater(minimum["byteLimit"] + minimum["receiveReservation"], budget.MAX_PROBE_RESERVATION)
        for values in ((0, 1, 1), (budget.TCP_MAX_BYTES + 1, 1, 1), (1, 0, 1),
                       (1, budget.TCP_MAX_CONNECTIONS + 1, 1), (1, 1, 0), (1, 1, 8001),
                       (True, 1, 1), (1, "1", 1), (1, 1, 1.0)):
            with self.subTest(values=values), self.assertRaises(budget.BudgetError):
                budget.tcp_plan(*values)


@unittest.skipUnless(os.name in {"posix", "nt"}, "Private storage adapter unavailable")
class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / "private"

    def tearDown(self):
        self.temp.cleanup()

    def test_unattributed_provider_growth_keeps_delayed_local_debit_after_restart(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ticket = ledger.reserve_offline(1, 1000)
            ledger.account_offline(ticket, download=1000)
            ledger.finish_offline(ticket, quiescent=True)
            ledger.observe_provider(f"upload=100000000; download={900000000 + budget.TARGET - 500}; total=100000000000")
            state = ledger.summary()
            self.assertEqual(state["billingDelta"], budget.TARGET - 500)
            self.assertEqual((state["localUpload"], state["localDownload"], state["heldBytes"]), (0, 1000, 0))
            durable = ledger.path.read_bytes()
        with budget.Ledger(self.root) as ledger:
            self.assertEqual(ledger.summary(), state)
            self.assertEqual(state["policy"], "NormalTargetReached")
            with self.assertRaisesRegex(budget.BudgetError, "NormalTargetReached"):
                ledger.reserve_offline(2, 1)
            self.assertEqual(ledger.path.read_bytes(), durable)
            self.assertEqual(ledger.summary()["attempts"], 1)

    def test_other_client_growth_does_not_release_package_headroom(self):
        # Only numeric offline fixtures; no provider request or private ledger.
        total = budget.RESERVE_PACKAGE + 1200
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(f"upload=100; download=900; total={total}")
            ticket = ledger.reserve_offline(1, 100)
            ledger.account_offline(ticket, download=100)
            ledger.finish_offline(ticket, quiescent=True)
            ledger.observe_provider(f"upload=100; download=1001; total={total}")
            state = ledger.summary()
            self.assertEqual((state["billingDelta"], state["localDownload"], state["providerRemaining"]),
                             (101, 100, budget.RESERVE_PACKAGE + 99))
            durable = ledger.path.read_bytes()
            self.assertEqual(state["policy"], "PackageReserve")
            with self.assertRaisesRegex(budget.BudgetError, "PackageReserve"):
                ledger.reserve_offline(2, 1)
            self.assertEqual(ledger.path.read_bytes(), durable)

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

    def test_failed_atomic_commit_retains_previous_durable_accounting(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ticket = ledger.reserve_offline(1, 1024)
            before = ledger.summary()
            committed = ledger.path.read_bytes()
            target = ledger.windows if ledger.windows else budget.os
            with mock.patch.object(target, "replace", side_effect=OSError("synthetic commit failure")):
                with self.assertRaises(OSError):
                    ledger.account_offline(ticket, upload=10, download=20)
            self.assertEqual(ledger.path.read_bytes(), committed)
            self.assertEqual(list(self.root.glob(".budget-*")), [])
        with budget.Ledger(self.root) as ledger:
            self.assertEqual(ledger.summary(), before)
            self.assertEqual(ledger.summary()["heldBytes"], 1024)

    def test_failed_reservation_poisons_session_before_any_subsequent_work(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            existing = ledger.reserve_offline(1, 128)
            committed = ledger.path.read_bytes()
            target = ledger.windows if ledger.windows else budget.os
            with mock.patch.object(target, "replace", side_effect=OSError("synthetic commit failure")):
                with self.assertRaises(OSError):
                    ledger.reserve_tcp_offline(2, 1024, 2)
            self.assertEqual(ledger.path.read_bytes(), committed)
            # No ticket was returned for the failed reservation. Catching the
            # write exception must not let that in-memory attempt be used or
            # let another request consume a budget which was never committed.
            operations = [ledger.summary, lambda: ledger.reserve_offline(3, 64),
                          lambda: ledger.reserve_tcp_offline(3, 1024, 1),
                          lambda: ledger.account_offline(existing, upload=1),
                          lambda: ledger.finish_offline(existing, quiescent=True),
                          lambda: ledger.observe_provider(BASE), lambda: ledger.initialize(BASE)]
            for operation in operations:
                with self.assertRaisesRegex(budget.BudgetError, "LedgerCommitUncertain"):
                    operation()
            self.assertEqual(ledger.path.read_bytes(), committed)
        # Reusing the object is safe only after closing, reacquiring the lock
        # and reading actual disk state. The failed new attempt was not saved.
        with ledger:
            self.assertEqual(ledger.summary()["attempts"], 1)
            self.assertEqual(ledger.summary()["heldBytes"], 128)
            self.assertEqual(ledger.reserve_tcp_offline(2, 1024, 2), "2")

    def test_failed_settlement_cannot_refund_reservation_in_same_session(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ticket = ledger.reserve_tcp_offline(1, 128, 2)
            ledger.account_offline(ticket, upload=17, download=19)
            before = ledger.summary()
            target = ledger.windows if ledger.windows else budget.os
            with mock.patch.object(target, "replace", side_effect=OSError("synthetic commit failure")):
                with self.assertRaises(OSError):
                    ledger.finish_offline(ticket, quiescent=True)
            with self.assertRaisesRegex(budget.BudgetError, "LedgerCommitUncertain"):
                ledger.reserve_offline(2, 1)
        with budget.Ledger(self.root) as ledger:
            self.assertEqual(ledger.summary(), before)
            with self.assertRaisesRegex(budget.BudgetError, "NodeAlreadyReserved"):
                ledger.reserve_tcp_offline(1, 128, 2)

    @unittest.skipUnless(os.name == "posix", "POSIX directory durability check")
    def test_post_replace_fsync_failure_never_rolls_back_a_committed_reservation(self):
        real_fsync = os.fsync

        def fail_directory_sync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("synthetic directory sync failure")
            return real_fsync(fd)

        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            with mock.patch.object(budget.os, "fsync", side_effect=fail_directory_sync):
                with self.assertRaises(OSError):
                    ledger.reserve_tcp_offline(1, 256, 3)
            with self.assertRaisesRegex(budget.BudgetError, "LedgerCommitUncertain"):
                ledger.summary()
        with budget.Ledger(self.root) as ledger:
            # Replace happened before fsync failed. Reading the durable file
            # retains that uncertainty conservatively instead of refunding it.
            self.assertEqual(ledger.summary()["attempts"], 1)
            self.assertEqual(ledger.summary()["heldBytes"], 256 + 3 * budget.TCP_RECEIVE_RESERVATION)

    def test_initialization_sync_failure_cannot_reinitialize_in_same_session(self):
        with budget.Ledger(self.root) as ledger:
            with mock.patch.object(budget.os, "fsync", side_effect=OSError("synthetic marker sync failure")):
                with self.assertRaises(OSError):
                    ledger.initialize(BASE)
            with self.assertRaisesRegex(budget.BudgetError, "LedgerCommitUncertain"):
                ledger.initialize(BASE)
        with self.assertRaisesRegex(budget.BudgetError, "LedgerMissingAfterInitialization"):
            with budget.Ledger(self.root):
                self.fail("initialization failure silently reset baseline")

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

    @unittest.skipUnless(os.name == "posix", "POSIX ownership and mode checks")
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

    @unittest.skipUnless(os.name == "nt", "Windows handle and ACL checks")
    def test_windows_lock_prevents_removal_and_directory_rename(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            with self.assertRaises(PermissionError):
                (self.root / "traffic-budget.lock").unlink()
            with self.assertRaises(PermissionError):
                self.root.rename(self.root.with_name("renamed"))

    @unittest.skipUnless(os.name == "nt", "Windows handle and ACL checks")
    def test_windows_refuses_permissive_existing_directory_and_file(self):
        # A normal temporary directory inherits broader permissions. Opening
        # existing storage must reject it without silently replacing its ACL.
        self.root.mkdir()
        with self.assertRaisesRegex(budget.BudgetError, "PrivateAclRequired"):
            with budget.Ledger(self.root):
                self.fail("inherited directory ACL accepted")
        self.root.rmdir()
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
        path = self.root / "traffic-budget.json"
        before = path.read_bytes()
        command = subprocess.run(["icacls.exe", str(path), "/grant", "*S-1-1-0:(R)"],
                                 capture_output=True, timeout=10)
        self.assertEqual(command.returncode, 0, command.stderr.decode(errors="replace"))
        with self.assertRaisesRegex(budget.BudgetError, "PrivateAclRequired"):
            with budget.Ledger(self.root):
                self.fail("Everyone-readable ledger accepted")
        self.assertEqual(path.read_bytes(), before)

    @unittest.skipUnless(os.name == "nt", "Windows junction and hard-link checks")
    def test_windows_refuses_junctions_and_multiply_linked_files(self):
        import _winapi
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
        alias = Path(self.temp.name) / "junction"
        _winapi.CreateJunction(str(self.root), str(alias))
        try:
            with self.assertRaisesRegex(budget.BudgetError, "PrivateDirectoryRequired"):
                with budget.Ledger(alias):
                    self.fail("junction accepted")
        finally:
            alias.rmdir()
        linked = Path(self.temp.name) / "linked-budget.json"
        os.link(self.root / "traffic-budget.json", linked)
        try:
            with self.assertRaisesRegex(budget.BudgetError, "PrivateStorageRequired"):
                with budget.Ledger(self.root):
                    self.fail("multiply linked ledger accepted")
        finally:
            linked.unlink()

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

    def test_tcp_payload_cannot_consume_held_kernel_reserve(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ticket = ledger.reserve_tcp_offline(1, 256, 3, timeout_ms=4000)
            plan = ledger.data["reservations"][ticket]["tcp"].copy()
            before = ledger.summary()
            ledger.account_offline(ticket, upload=100, download=156)
            after = ledger.summary()
            self.assertEqual(after["heldBytes"], 3 * budget.TCP_RECEIVE_RESERVATION)
            self.assertEqual(after["guardedBytes"], before["guardedBytes"])
            for debit in ({"upload": 1}, {"download": 1}):
                with self.assertRaisesRegex(budget.BudgetError, "RequestByteLimit"):
                    ledger.account_offline(ticket, **debit)
            with self.assertRaisesRegex(budget.BudgetError, "UnreleasedRequests"):
                ledger.finish_offline(ticket)
            self.assertEqual(ledger.summary(), after)
        with budget.Ledger(self.root) as ledger:
            self.assertEqual(ledger.data["reservations"][ticket]["tcp"], plan)
            self.assertEqual(ledger.summary(), after)
            self.assertFalse(ledger.summary()["liveReady"])

    def test_tcp_reservation_migration_preserves_schema_one_accounting(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            existing = ledger.reserve_offline(1, 1024)
            ledger.account_offline(existing, upload=10, download=20)
            before = ledger.summary()
        path = self.root / "traffic-budget.json"
        data = json.loads(path.read_text())
        data["schema"] = 1
        path.write_text(json.dumps(data))
        legacy = path.read_bytes()
        with budget.Ledger(self.root) as ledger:
            self.assertEqual(ledger.summary(), before)
            self.assertEqual(path.read_bytes(), legacy)
            ticket = ledger.reserve_tcp_offline(2, 2048, 2)
            self.assertEqual(ledger.data["schema"], 2)
            self.assertEqual(ledger.data["reservations"][existing], data["reservations"][existing])
            self.assertEqual(ledger.summary()["heldBytes"], 994 + 2048 + 2 * budget.TCP_RECEIVE_RESERVATION)
        with budget.Ledger(self.root) as ledger:
            self.assertEqual((ledger.summary()["baselineUsed"], ledger.summary()["attempts"]), (1_000_000_000, 2))
            self.assertEqual((ledger.summary()["localUpload"], ledger.summary()["localDownload"]), (10, 20))
            self.assertEqual(ledger.data["reservations"][ticket]["tcp"], budget.tcp_plan(2048, 2))

    def test_full_tcp_plan_is_reserved_before_concurrent_admission(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)

            def attempt(ordinal):
                try:
                    return ledger.reserve_tcp_offline(ordinal, 65536, 2)
                except budget.BudgetError as error:
                    return str(error)

            with ThreadPoolExecutor(max_workers=8) as workers:
                results = list(workers.map(attempt, range(1, 9)))
            self.assertEqual(sorted(x for x in results if x != "ConcurrencyLimit"), ["1", "2", "3"])
            self.assertEqual(results.count("ConcurrencyLimit"), 5)
            self.assertEqual(ledger.summary()["heldBytes"], 3 * (65536 + 2 * budget.TCP_RECEIVE_RESERVATION))
            self.assertEqual(ledger.summary()["attempts"], 3)
            saved = json.loads(ledger.path.read_text())
            self.assertEqual(saved, ledger.data)

    def test_tcp_admission_counts_receive_reserve_at_target_and_package_boundary(self):
        amount = 65536 + 2 * budget.TCP_RECEIVE_RESERVATION
        cases = [("target", f"upload=100000000; download={900000000 + budget.TARGET - amount}; total=100000000000", "NormalTargetReached"),
                 ("package", f"upload=100000000; download=900000000; total={budget.RESERVE_PACKAGE + 1_000_000_000 + amount - 1}", "PackageReserve")]
        for name, header, error in cases:
            with self.subTest(name=name), budget.Ledger(self.root / name) as ledger:
                ledger.initialize(BASE if name == "target" else header)
                if name == "target":
                    ledger.observe_provider(header)
                # Payload alone would fit; admitting the full plan must fail.
                state = ledger.summary()
                self.assertEqual(budget.policy(state["billingDelta"], 0, 65536, state["providerRemaining"]), "WithinNormalTarget")
                with self.assertRaisesRegex(budget.BudgetError, error):
                    ledger.reserve_tcp_offline(1, 65536, 2)
                self.assertEqual(ledger.summary()["attempts"], 0)
                self.assertEqual(ledger.summary()["heldBytes"], 0)

    def test_tcp_crash_keeps_every_unsettled_byte_and_attempt_across_processes(self):
        program = """
import importlib.util, os, sys
spec=importlib.util.spec_from_file_location('budget', sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with m.Ledger(sys.argv[2]) as ledger:
 ledger.initialize(sys.argv[3])
 t=ledger.reserve_tcp_offline(1, 4096, 4, 1000)
 ledger.account_offline(t, upload=23, download=31)
 os._exit(0)
"""
        child = subprocess.run([sys.executable, "-c", program, str(MODULE), str(self.root), BASE],
                               capture_output=True, timeout=10)
        self.assertEqual(child.returncode, 0, child.stderr.decode())
        with budget.Ledger(self.root) as ledger:
            state = ledger.summary()
            self.assertEqual(state["heldBytes"], 4096 + 4 * budget.TCP_RECEIVE_RESERVATION - 54)
            self.assertEqual(state["guardedBytes"], 4096 + 4 * budget.TCP_RECEIVE_RESERVATION)
            self.assertEqual((state["attempts"], state["localUpload"], state["localDownload"]), (1, 23, 31))
            self.assertEqual(ledger.data["reservations"]["1"]["tcp"]["timeoutMs"], 1000)
            with self.assertRaisesRegex(budget.BudgetError, "NodeAlreadyReserved"):
                ledger.reserve_tcp_offline(1, 4096, 4)

    def test_tcp_plan_tampering_is_rejected_without_rewriting_evidence(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ledger.reserve_tcp_offline(1, 256, 2)
        path = self.root / "traffic-budget.json"
        original = path.read_bytes()
        mutations = [lambda d: d.update(schema=1),
                     lambda d: d["reservations"]["1"].update(held=256),
                     lambda d: d["reservations"]["1"]["tcp"].pop("timeoutMs")]
        for field, bad in (("byteLimit", 0), ("byteLimit", "256"), ("connectionLimit", 49),
                           ("connectionLimit", True), ("receiveReservation", 0),
                           ("receiveReservation", float(2 * budget.TCP_RECEIVE_RESERVATION)),
                           ("timeoutMs", 8001), ("timeoutMs", True)):
            mutations.append(lambda d, f=field, b=bad: d["reservations"]["1"]["tcp"].update({f: b}))
        for mutate in mutations:
            value = json.loads(original)
            mutate(value)
            path.write_text(json.dumps(value))
            corrupt = path.read_bytes()
            with self.assertRaises(budget.BudgetError):
                with budget.Ledger(self.root):
                    self.fail("altered TCP plan accepted")
            self.assertEqual(path.read_bytes(), corrupt)

    def test_remaining_budget_accounts_for_local_bytes_and_holds_separately_from_billing(self):
        with budget.Ledger(self.root) as ledger:
            ledger.initialize(BASE)
            ticket = ledger.reserve_offline(1, 1024)
            ledger.account_offline(ticket, upload=128, download=256)
            state = ledger.summary()
            self.assertEqual(state["billingDelta"], 0)
            self.assertEqual(state["guardedBytes"], 1024)
            self.assertEqual(state["remainingAbsoluteBudget"], budget.ABSOLUTE - 1024)
            self.assertEqual(state["remainingStopBudget"], budget.STOP - 1024)
            # Growth from another client is NOT attributed to local testing.
            ledger.observe_provider("upload=100001000; download=900000000; total=100000000000")
            state = ledger.summary()
            self.assertEqual((state["billingDelta"], state["localUpload"], state["localDownload"]), (1000, 128, 256))
            self.assertEqual(state["guardedBytes"], 1000 + 384 + 640)
            self.assertEqual(state["remainingAbsoluteBudget"], budget.ABSOLUTE - 2024)
            ledger.finish_offline(ticket, quiescent=True)
            self.assertEqual(ledger.summary()["remainingAbsoluteBudget"], budget.ABSOLUTE - 1384)

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
