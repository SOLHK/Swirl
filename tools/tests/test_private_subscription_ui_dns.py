"""Fixed real DoT + imported-node UI proof under the existing six/8s grant.

Portable cases validate fixed contracts, reject forged receipts and check
actual owned loopback listener retirement without client requests or Qt.
Windows cases require actual paired QA binaries, DPAPI, UI input, production
Resolver, shared raw TCP quota and native process ownership. No provider input.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import PrivateSubscriptionBudget as budget
import PrivateSubscriptionSupervisor as supervisor
import PrivateSubscriptionUi as ui
import RunControlledNodeAcceptance as fixture
from test_private_subscription_ui_import import sample_observations

REPORTS = []
IDENTITIES = {"qtUi": None, "billingWorker": None}


def wire_query(host=fixture.UI_DNS_HOST):
    return (struct.pack("!6H", 123, 0x100, 1, 0, 0, 0)
            + b"".join(bytes([len(label)]) + label.encode("ascii") for label in host.split("."))
            + b"\0\0\1\0\1")


def sample_dns():
    """Receipt-validator inputs only; no ExitProof or admission capability."""
    result, owner = sample_observations()
    owner.socks = 12345
    stages = ["policy-applied", "probe-click", "probe-result", "proxy-http-start", "proxy-http-complete",
              "proxy-https-start", "proxy-https-complete"]
    routes = {row["stage"]: row for row in result["uiImportEvidence"]["routeWitnesses"]}
    result["uiImportEvidence"]["routeWitnesses"] = [routes[stage] for stage in stages]
    plan = budget.tcp_plan(65536, 6, 8000)
    binding = {"schema": 1, "reservation_id": "1", "nonce": "d" * 64, "plan_digest": "e" * 64}
    guard = {"byte_limit": 65536, "upload": 1000, "download": 2000, "connection_limit": 6,
             "connection_attempts": 6, "receive_reservation": 6 * budget.TCP_RECEIVE_RESERVATION,
             "timeout_ms": 8000, "timed_out": False, "stopped": True, "shutdown_failures": 0}
    snapshots = [{"stage": stage, "guard": {**guard, "connection_attempts": count, "stopped": False,
        "upload": index * 100, "download": index * 200}} for index, (stage, count) in enumerate(
            zip(stages, (1, 1, 3, 3, 5, 5, 6)), 1)]
    result["uiDnsEvidence"] = {"workflow": fixture.UI_DNS_WORKFLOW, "control": "", "configured": True,
        "configurationSha256": hashlib.sha256(fixture.json_bytes(fixture.fixed_dns_configuration(owner.socks))).hexdigest(),
        "trustBindingSha256": supervisor.digest(binding), "caSha256": fixture.FIXTURE_CERT_SHA256,
        "queryHost": fixture.UI_DNS_HOST, "resolverAddress": f"127.0.0.1:{owner.socks}", "snapshots": snapshots}
    _, answer = fixture.fixed_dns_response(wire_query(), "")
    answer["responseSent"] = True
    observed = {"tlsAttempts": 2, "tlsCompleted": 2, "queries": [answer.copy(), answer.copy()]}
    owner.dns_report = lambda: observed
    return result, owner, observed, plan, binding, guard


class DnsContractTests(unittest.TestCase):
    def test_contract_has_one_existing_endpoint_and_no_arbitrary_trust_or_host(self):
        valid = {"uiWorkflow": fixture.UI_IMPORT_WORKFLOW, "uiDns": {"workflow": fixture.UI_DNS_WORKFLOW,
                 "control": "", "caSha256": fixture.FIXTURE_CERT_SHA256}}
        self.assertEqual(fixture.ui_dns_contract(valid), "")
        self.assertIsNone(fixture.ui_dns_contract({}))
        for changed in ({**valid, "uiImportControl": "wrong-url"},
                        {"uiDns": valid["uiDns"]},
                        {**valid, "uiDns": {**valid["uiDns"], "address": "127.0.0.2"}},
                        {**valid, "uiDns": {**valid["uiDns"], "caSha256": "0" * 64}},
                        {**valid, "uiDns": {**valid["uiDns"], "control": True}}):
            with self.subTest(value=changed), self.assertRaises(ValueError):
                fixture.ui_dns_contract(changed)
        fixed = fixture.fixed_dns_configuration(12345)
        self.assertEqual(fixed["encrypted"], "tls://127.0.0.1:12345")
        self.assertEqual(fixed["hosts"], [])
        self.assertFalse(fixed["useHosts"])
        self.assertEqual(fixed["queryFamily"], "ipv4_only")
        self.assertIn(b"server: swirl-node.fixture.invalid\n", fixture.fixed_subscription_body(12345, "a" * 64, dns=True))
        self.assertIn(b"server: 127.0.0.1\n", fixture.fixed_subscription_body(12345, "a" * 64))
        self.assertEqual(fixture.fixed_ui_origin(), {"host": "203.0.113.1",
            "certificateSha256": "650152f76d410e5ae1a2b589002d1dd79a9c2af405021aed50da861fac52d748",
            "keySha256": "e62fd952d2f14fa39e6849032825d4e6a6b46837fce0037f6ed1abd46becc814"})
        directory = TOOLS.parent / "src/Swirl.Quick/tests/fixtures"
        self.assertEqual(fixture.digest(directory / "private-ui-origin-cert.pem"), fixture.UI_IMPORT_ORIGIN_CERT_SHA256)
        self.assertEqual(fixture.digest(directory / "private-ui-origin-key.pem"), fixture.UI_IMPORT_ORIGIN_KEY_SHA256)
        with self.assertRaises(ValueError):
            fixture.fixed_subscription_body(12345, "a" * 64, dns="remote.example")
        # Real local listener ownership: setting the stop event is not socket
        # retirement. No client, DNS query or Qt process is started here.
        owner = fixture.LoopbackFixture(directory / "localhost-cert.pem", directory / "localhost-key.pem")
        session = ui.SyntheticUiSession.__new__(ui.SyntheticUiSession)
        session.fixture, session.native_receipt, session.storage = owner, None, None
        session.dns_workflow, session.closed = True, False
        observation = {"test": self.id(), "scope": "actual owned loopback handles; no client requests or Qt",
                       "beforeClose": owner.dns_report(), "uiCleanupRejectedUnclosedFixture": False}
        try:
            self.assertEqual(len(owner._listeners), 3)
            self.assertTrue(all(peer.fileno() >= 0 for peer in owner._listeners))
            owner.done.set()
            observation["afterStopEventOnly"] = owner.dns_report()
            self.assertFalse(observation["afterStopEventOnly"]["listenersClosed"])
            # An incomplete cleanup returning normally must still fail the
            # session's post-close verification, before Supervisor settlement.
            with mock.patch.object(owner, "close", return_value=None), self.assertRaisesRegex(
                    budget.BudgetError, "UiFixtureExitUnconfirmed"):
                session.close()
            self.assertFalse(session.closed)
            observation["uiCleanupRejectedUnclosedFixture"] = True
        finally:
            owner.close()
            observation["afterActualClose"] = owner.dns_report()
            REPORTS.append(observation)
        self.assertTrue(observation["afterActualClose"]["listenersClosed"])
        self.assertTrue(observation["afterActualClose"]["tasksReleased"])
        self.assertTrue(all(peer.fileno() < 0 for peer in owner._listeners))
        self.assertEqual(owner.sockets, set())
        session.close()
        self.assertTrue(session.closed)

    def test_wire_fixture_requires_actual_exact_a_query_and_records_unsent_response(self):
        response, observed = fixture.fixed_dns_response(wire_query(), "")
        self.assertEqual(struct.unpack("!6H", response[:12]), (123, 0x8180, 1, 1, 0, 0))
        self.assertEqual(response[-4:], b"\x7f\0\0\1")
        self.assertFalse(observed["responseSent"])
        self.assertEqual(observed["requestBytes"], len(wire_query()))
        for request in (wire_query("other.invalid"), wire_query() + b"x", wire_query()[:-4] + b"\0\x1c\0\1",
                        b"x" * 513, wire_query()[:12] + b"\xc0\x0c\0\1\0\1"):
            with self.subTest(request=request.hex()), self.assertRaises(ValueError):
                fixture.fixed_dns_response(request, "")
        self.assertEqual(fixture.fixed_dns_response(wire_query(), "wrong-address")[0][-4:], b"\x7f\0\0\2")
        self.assertFalse(fixture.fixed_dns_response(wire_query(), "wrong-question")[1]["questionMatched"])

    def test_receipt_requires_two_real_queries_six_attempts_order_and_same_binding(self):
        value, owner, observed, plan, binding, guard = sample_dns()
        def validate(current=value, final=guard):
            ui._validate_dns_observations(current, owner, None, plan=plan, binding=binding, final_guard=final, positive=True)
        validate()
        self.assertTrue(guard["stopped"])  # Normal terminal close is allowed.
        for index in range(len(value["uiDnsEvidence"]["snapshots"])):
            for flag in ("timed_out", "stopped"):
                bad = copy.deepcopy(value)
                bad["uiDnsEvidence"]["snapshots"][index]["guard"][flag] = True
                with self.subTest(stage=index, flag=flag), self.assertRaisesRegex(
                        budget.BudgetError, "ActualUiDnsSuccessUnproven"):
                    validate(bad)
        with self.assertRaisesRegex(budget.BudgetError, "ActualUiDnsSuccessUnproven"):
            validate(final={**guard, "timed_out": True})
        changes = [lambda x: x["uiDnsEvidence"].update(configured=False),
                   lambda x: x["uiDnsEvidence"].update(trustBindingSha256="0" * 64),
                   lambda x: x["uiDnsEvidence"].update(resolverAddress="127.0.0.1:23456"),
                   lambda x: x["uiDnsEvidence"]["snapshots"][2]["guard"].update(connection_attempts=2),
                   lambda x: x["uiDnsEvidence"]["snapshots"][3]["guard"].update(upload=0),
                   lambda x: x["uiDnsEvidence"]["snapshots"][6]["guard"].update(timeout_ms=8001),
                   lambda x: x["uiDnsEvidence"]["snapshots"].__setitem__(0, None)]
        for change in changes:
            bad = copy.deepcopy(value); change(bad)
            with self.assertRaises(budget.BudgetError):
                validate(bad)
        for key, wrong in (("tlsAttempts", 1), ("tlsCompleted", 0), ("queries", observed["queries"][:1])):
            original = observed[key]; observed[key] = wrong
            with self.assertRaises(budget.BudgetError):
                validate()
            observed[key] = original
        observed["queries"][0]["responseSent"] = False
        with self.assertRaises(budget.BudgetError):
            validate()

    def test_invalid_mode_and_live_flags_refuse_before_paths_or_child(self):
        identity = ui.UiIdentity.__new__(ui.UiIdentity)
        identity._issuer = supervisor._IDENTITY_ISSUER
        with mock.patch.object(ui, "_local_path", side_effect=AssertionError("path accessed")), \
             mock.patch.object(ui, "OwnedProcess", side_effect=AssertionError("child started")):
            for options in ({"dns_workflow": True}, {"dns_control": "stall"}, {"dns_workflow": 1},
                            {"import_workflow": True, "import_control": "wrong-ca", "dns_workflow": True}):
                with self.assertRaisesRegex(budget.BudgetError, "PrivateUiDnsWorkflowRequired"):
                    ui.SyntheticUiSession(identity, Path("unused"), Path("unused"), **options)
            for private in ("--live", "--store=PRIVATE_MARKER", "--subscription=PRIVATE_MARKER", "--provider-url=PRIVATE_MARKER"):
                with self.assertRaisesRegex(budget.BudgetError, "PrivateLiveUiAdmissionUnavailable"):
                    ui.main(["--synthetic-ui-dns", private])


@unittest.skipUnless(os.name == "nt", "actual Windows Qt/DPAPI/Job/production Resolver; not simulated")
class ActualUiDnsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(os.environ["SWIRL_PRIVATE_UI_EXE"])
        cls.exe_hash = os.environ["SWIRL_PRIVATE_UI_EXE_SHA256"]
        cls.core_hash = os.environ["SWIRL_PRIVATE_UI_CORE_SHA256"]
        cls.source = os.environ["SWIRL_PRIVATE_EXPECTED_SOURCE"]
        cls.qt_root = os.environ.get("SWIRL_PRIVATE_UI_QT_ROOT")
        cls.fixtures = TOOLS.parent / "src/Swirl.Quick/tests/fixtures"
        cls.identity = ui.UiIdentity.inspect(cls.exe, cls.source, cls.exe_hash, expected_core_sha256=cls.core_hash)
        IDENTITIES["qtUi"] = {**cls.identity.metadata, "exe_sha256": cls.exe_hash, "core_sha256": cls.core_hash,
                              "qt_version": cls.identity.qt_version}
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def invoke(self, label, *, control=None, billing=False):
        # Each failure is its own explicitly synthetic fixture account. This is
        # not an original/live ledger, and no failed hold is reset or reused.
        state = self.root / (label + "-synthetic-ledger")
        with budget.Ledger(state) as ledger:
            ledger.initialize_synthetic()
        command = [sys.executable, str(TOOLS / "PrivateSubscriptionUi.py"), "--synthetic-ui-import-policy", "--synthetic-ui-dns",
                   "--exe", str(self.exe), "--exe-sha256", self.exe_hash, "--core-sha256", self.core_hash,
                   "--expected-source", self.source, "--state-dir", str(state), "--output-directory", str(self.root / label),
                   "--fixture-directory", str(self.fixtures)]
        if self.qt_root:
            command += ["--qt-root", self.qt_root]
        if control:
            command += ["--synthetic-ui-dns-control", control]
        if billing:
            worker = supervisor.WorkerIdentity.inspect(Path(os.environ["SWIRL_PRIVATE_WORKER"]), self.source,
                                                       os.environ["SWIRL_PRIVATE_EXPECTED_WORKER_SHA256"])
            IDENTITIES["billingWorker"] = {**worker.metadata, "exe_sha256": worker.sha256}
            command += ["--synthetic-billing", "--billing-worker", str(worker.path), "--billing-worker-sha256", worker.sha256]
        completed = subprocess.run(command, capture_output=True, timeout=40 if billing else 18)
        self.assertNotIn(b"Traceback", completed.stderr)
        record = json.loads(completed.stdout)
        REPORTS.append({"test": self.id(), "actualCliExit": completed.returncode, "record": record})
        self.assert_owner(record)
        return record, completed.returncode, state

    def assert_owner(self, record):
        self.assertEqual(record["sourceSha"], self.source)
        self.assertFalse(record["liveReady"])
        self.assertFalse(record["providerStatisticsAuthenticated"])
        self.assertEqual((record["providerRequests"], record["realNodeRequests"]), (0, 0))
        self.assertEqual((record["plan"]["connectionLimit"], record["plan"]["timeoutMs"]), (6, 8000))
        self.assertEqual(record["plan"]["receiveReservation"], 6 * budget.TCP_RECEIVE_RESERVATION)
        self.assertTrue(record["exit"]["processSignaled"])
        self.assertTrue(record["exit"]["ownedProcessSetEmpty"])
        self.assertTrue(record["cleanupConfirmed"])
        self.assertTrue(record["fixture"]["tasksReleased"])
        self.assertTrue(record["fixture"]["dns"]["tasksReleased"])
        self.assertTrue(record["fixture"]["dns"]["listenersClosed"])

    def assert_retained(self, record, state):
        self.assertFalse(record["settled"])
        self.assertFalse(record["fixture"]["uiDnsExercised"])
        self.assertTrue(record["parentBudgetEvidence"]["fullHoldRetained"])
        with budget.Ledger(state, existing_only=True) as ledger:
            self.assertEqual(ledger.summary()["heldBytes"], 65536 + 6 * budget.TCP_RECEIVE_RESERVATION)
            self.assertEqual(ledger.data["history"][record["reservation_id"]]["phase"], "unresolved")
            self.assertIsNone(ledger.data["history"][record["reservation_id"]]["receipt"])

    def assert_success(self, record, code):
        self.assertEqual(code, 0, record)
        self.assertEqual(record["outcome"], "QtUiSucceeded")
        self.assertTrue(record["settled"])
        self.assertTrue(record["fixture"]["uiDnsExercised"])
        self.assertTrue(record["uiSubscriptionImportExercised"])
        self.assertEqual(record["guard"]["connection_attempts"], 6)
        self.assertEqual(record["fixture"]["socksConnections"], 4)
        self.assertEqual(record["fixture"]["forwarded"], 4)
        dns = record["fixture"]["dns"]
        self.assertEqual((dns["tlsAttempts"], dns["tlsCompleted"], len(dns["queries"])), (2, 2, 2))
        self.assertTrue(all(row["responseSent"] for row in dns["queries"]))
        result = record["fixture"]["ui"]
        self.assertEqual(result["probeHttpStatus"], 204)
        self.assertTrue(result["uiDisplayedLatencyMatches"])
        self.assertEqual([row["scheme"] for row in result["proxyRequests"]], ["http", "https"])
        self.assertTrue(all(row["success"] for row in result["proxyRequests"]))
        self.assertEqual(record["parentBudgetEvidence"]["settledNativeExit"], record["exit"])

    def test_01_real_dot_resolves_imported_node_in_probe_and_normal_core(self):
        record, code, _ = self.invoke("positive")
        self.assert_success(record, code)

    def test_02_same_ledger_modeled_billing_wraps_real_dns_ui_path(self):
        record, code, state = self.invoke("billing", billing=True)
        self.assert_success(record, code)
        self.assertEqual(len(record["controlQueries"]), 2)
        with budget.Ledger(state, existing_only=True) as ledger:
            self.assertEqual(ledger.data["schema"], 4)
            self.assertEqual(len(ledger.data["history"]), 3)
            self.assertEqual(ledger.summary()["heldBytes"], 0)
            with self.assertRaises(budget.BudgetError):
                ledger.require_live_ready()

    def test_03_wrong_dns_ca_has_no_query_or_plaintext_fallback(self):
        record, code, state = self.invoke("wrong-ca", control="wrong-ca")
        self.assertEqual(code, 2)
        self.assert_retained(record, state)
        self.assertEqual(record["fixture"]["dns"]["tlsAttempts"], 1)
        self.assertEqual(record["fixture"]["dns"]["queries"], [])
        self.assertEqual(record["guard"]["connection_attempts"], 2)
        self.assertEqual(record["fixture"]["socksConnections"], 1)
        self.assertEqual(record["fixture"]["ui"]["proxyRequests"], [])

    def test_04_wrong_a_answer_cannot_expand_the_immutable_endpoint(self):
        record, code, state = self.invoke("wrong-address", control="wrong-address")
        self.assertEqual(code, 2)
        self.assert_retained(record, state)
        self.assertEqual(record["fixture"]["dns"]["queries"][0]["answerAddress"], "127.0.0.2")
        self.assertTrue(record["fixture"]["dns"]["queries"][0]["responseSent"])
        self.assertEqual(len(record["fixture"]["dns"]["queries"]), 1)
        self.assertEqual(record["guard"]["connection_attempts"], 3)
        self.assertTrue(record["guard"]["stopped"])
        self.assertEqual(record["fixture"]["socksConnections"], 1)
        self.assertEqual(record["fixture"]["ui"]["proxyRequests"], [])

    def test_05_wrong_question_is_rejected_by_the_real_dns_parser(self):
        record, code, state = self.invoke("wrong-question", control="wrong-question")
        self.assertEqual(code, 2)
        self.assert_retained(record, state)
        self.assertEqual(len(record["fixture"]["dns"]["queries"]), 1)
        self.assertFalse(record["fixture"]["dns"]["queries"][0]["questionMatched"])
        self.assertTrue(record["fixture"]["dns"]["queries"][0]["responseSent"])
        self.assertEqual(record["guard"]["connection_attempts"], 2)
        self.assertEqual(record["fixture"]["socksConnections"], 1)
        self.assertEqual(record["fixture"]["ui"]["proxyRequests"], [])

    def test_06_stalled_dns_has_no_later_node_dial_or_budget_renewal(self):
        record, code, state = self.invoke("stall", control="stall")
        self.assertEqual(code, 2)
        self.assert_retained(record, state)
        self.assertEqual(len(record["fixture"]["dns"]["queries"]), 1)
        self.assertFalse(record["fixture"]["dns"]["queries"][0]["responseSent"])
        self.assertEqual(record["fixture"]["socksConnections"], 1)
        self.assertEqual(record["fixture"]["forwarded"], 1)
        self.assertLess(record["parentElapsedMs"], 9800)

    def test_07_cancel_after_actual_dns_query_closes_owner_without_another_dial(self):
        state = self.root / "cancel-synthetic-ledger"
        session = ui.SyntheticUiSession(self.identity, self.root / "cancel", self.fixtures, qt_root=self.qt_root,
            import_workflow=True, dns_workflow=True, dns_control="cancel")
        cancelled, done = threading.Event(), threading.Event()
        observed = []
        def cancel_after_query():
            deadline = time.monotonic() + 8
            while not done.wait(0.005) and time.monotonic() < deadline:
                owner = session.fixture
                if owner is not None and owner.dns_query_observed.is_set():
                    observed.append(True)
                    cancelled.set()
                    return
        watcher = threading.Thread(target=cancel_after_query, daemon=True)
        with budget.Ledger(state) as ledger:
            ledger.initialize_synthetic()
            watcher.start()
            try:
                record = supervisor.Supervisor(ledger, self.identity).run_ui(session, cancel_event=cancelled)
            finally:
                done.set(); watcher.join(timeout=1)
                self.assertFalse(watcher.is_alive())
        REPORTS.append({"test": self.id(), "record": record, "cancelAfterActualQuery": observed == [True]})
        self.assertEqual(observed, [True])
        self.assert_owner(record)
        self.assert_retained(record, state)
        self.assertEqual(record["outcome"], "UiCancelledWithoutFinalReceipt")
        self.assertEqual(len(record["fixture"]["dns"]["queries"]), 1)
        self.assertFalse(record["fixture"]["dns"]["queries"][0]["responseSent"])
        self.assertEqual(record["fixture"]["socksConnections"], 1)
        self.assertEqual(record["fixture"]["forwarded"], 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--evidence", type=Path)
    options, remaining = parser.parse_known_args()
    if remaining:
        raise SystemExit("Unknown fixed-test option")
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    report = {"schema": 1, "scope": "fixed DoT through production Resolver in actual private Qt import/probe/normal proxy",
        "platform": sys.platform, "testsRun": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        "identities": IDENTITIES, "reports": REPORTS, "realNodeRequests": 0, "providerRequests": 0,
        "providerStatisticsAuthenticated": False, "liveReady": False}
    if options.evidence:
        options.evidence.mkdir(parents=True, exist_ok=False)
        with (options.evidence / "private-ui-dns-results.json").open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2); output.write("\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
