"""Fixed owned HTTPS subscription through actual private Qt UI and Rust quota.

Portable cases are contract/receipt checks only. Windows cases require the
paired QA EXE/DLL, perform real input/DPAPI/Core requests, and never skip missing
build outputs. No test accepts an arbitrary subscription URL or private store.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
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

REPORTS = []
IDENTITIES = {"qtUi": None, "billingWorker": None}


def sample_observations():
    """Only data-validator inputs; these objects cannot issue an ExitProof."""
    owner = SimpleNamespace(subscription_body_sha256="a" * 64, subscription_requests=1, subscription_declared_body_bytes=241,
                            http=12346, https=12347)
    source, imported, bootstrap, store = (f"{number:08x}-1111-1111-1111-111111111111" for number in range(1, 5))
    receipts = [{"stage": stage, "request_id": f"{index + 10:08x}-2222-2222-2222-222222222222",
                 "store_id": store, "saved_revision": str(index + 1),
                 "applied_revision": str(index + 1) if index >= 3 else "", "plan_digest": "b" * 64}
                for index, stage in enumerate(ui._IMPORT_RECEIPT_STAGES)]
    readbacks = [{"stage": stage, "independentNodeStore": True, "configurationV2": True, "sourceCount": 1,
                  "nodeCount": 2, "importedNodeId": imported, "sourceId": source,
                  "selectedImportedNode": index == 1, "saved_revision": "4" if index == 0 else "6",
                  "ciphertextSha256": "c" * 64}
                 for index, stage in enumerate(("imported-catalog", "selected-imported-node"))]
    reference = hashlib.sha256(imported.encode("ascii")).hexdigest()[:12]
    routes = [{"stage": stage, "selectedNodeReference": reference, "activeNodeReference": reference,
               "defaultNodeReference": reference, "resultNodeReference": reference if stage == "probe-result" else "",
               "request_id": receipts[-1]["request_id"], "saved_revision": "6", "applied_revision": "6",
               "plan_digest": "b" * 64, "proxyPort": 12345, "routingMode": "global"}
              for stage in ("policy-applied", "probe-click", "proxy-http-start", "proxy-https-start",
                            "probe-result", "proxy-https-complete", "proxy-http-complete")]
    result = {"uiSubscriptionImportExercised": True, "uiPolicySelectionExercised": True,
              "selectedNodeReference": reference, "probeHttpStatus": 204, "uiHeadersMs": 7, "outboundConnectMs": 3,
              "uiProbeButtonExercised": True, "uiDisplayedLatencyMatches": True,
              "uiImportEvidence": {"workflow": fixture.UI_IMPORT_WORKFLOW, "control": "", "phase": 32,
                  "inputEvents": list(ui._IMPORT_INPUTS), "committedReceipts": receipts, "readbacks": readbacks,
                  "routeWitnesses": routes, "coreRouting": {"scope": "actual-main-core-records-v1",
                      "receipt": {"engine_epoch": "17", "generation": "5", "store_id": store,
                          "request_id": receipts[-1]["request_id"], "applied_revision": "6", "plan_digest": "b" * 64},
                      "requests": [{"scheme": scheme, "id": str(index + 2), "host": fixture.UI_IMPORT_ORIGIN_HOST,
                          "port": owner.http if scheme == "http" else owner.https, "category": "proxy",
                          "nodeReference": reference, "leafNodeReference": reference,
                          "sourceReference": hashlib.sha256(source.encode("ascii")).hexdigest()[:12],
                          "rule": "policy:default", "ruleId": "policy:default", "mode": "global", "tier": 5,
                          "revision": "6", "generation": "5", "beforeConnectionRevision": "20",
                          "responseConnectionRevision": "21", "observedConnectionRevision": "22",
                          "preexistingConnectionIds": ["1"], "closed": True} for index, scheme in enumerate(("http", "https"))]},
                  "probePresentation": {"visible": True, "text": "出站建立 3 ms · HTTP 204",
                      "nodeReference": reference, "latency": 7, "outboundConnectMs": 3, "httpStatus": 204},
                  "sourceId": source, "importedNodeId": imported, "bootstrapNodeId": bootstrap,
                  "probeButtonClicked": True, "download": {"capabilityInstalled": True, "requests": 1,
                      "tlsVerified": True, "responseVerified": True, "responseBytes": 241, "httpStatus": 200,
                      "expectedBodySha256": "a" * 64, "failureCode": "", "route": "granted-core-http-listener",
                      "bodyLimit": 65536, "revoked": True}}}
    return result, owner


class ImportContractTests(unittest.TestCase):
    def test_fixed_yaml_is_bounded_and_cannot_choose_an_endpoint_or_document(self):
        body = fixture.fixed_subscription_body(12345, "a" * 64)
        self.assertEqual(body, b'proxies:\n  - name: Synthetic imported SOCKS5\n    type: socks5\n    server: 127.0.0.1\n    port: 12345\n    username: fixture\n    password: "' + b"a" * 64 + b'"\n')
        self.assertLess(len(body), 65536)
        for port, password in ((True, "a" * 64), (0, "a" * 64), (65536, "a" * 64), (1, "x\nserver: remote"), (1, "A" * 64)):
            with self.subTest(port=port), self.assertRaisesRegex(ValueError, "OwnedSyntheticSubscriptionRequired"):
                fixture.fixed_subscription_body(port, password)

    def test_fixed_workflow_rejects_unknown_or_conflicting_control(self):
        self.assertIsNone(fixture.ui_import_contract({}))
        self.assertEqual(fixture.ui_import_contract({"uiWorkflow": fixture.UI_IMPORT_WORKFLOW}), "")
        for control in fixture.UI_IMPORT_CONTROLS:
            self.assertEqual(fixture.ui_import_contract({"uiWorkflow": fixture.UI_IMPORT_WORKFLOW, "uiImportControl": control}), control)
        for manifest in ({"uiImportControl": "wrong-url"}, {"uiWorkflow": "https://unowned.invalid/"},
                         {"uiWorkflow": fixture.UI_IMPORT_WORKFLOW, "uiImportControl": ""},
                         {"uiWorkflow": fixture.UI_IMPORT_WORKFLOW, "uiImportControl": True},
                         {"uiWorkflow": fixture.UI_IMPORT_WORKFLOW, "nativeWatchdogControl": "native-watchdog-500ms"}):
            with self.subTest(keys=sorted(manifest)), self.assertRaisesRegex(ValueError, "PrivateUiImportWorkflowRequired"):
                fixture.ui_import_contract(manifest)

    def test_unknown_import_options_refuse_before_file_or_process_access(self):
        identity = ui.UiIdentity.__new__(ui.UiIdentity)
        identity._issuer = supervisor._IDENTITY_ISSUER
        with mock.patch.object(ui, "_local_path", side_effect=AssertionError("path accessed")), \
             mock.patch.object(ui, "OwnedProcess", side_effect=AssertionError("child started")):
            for workflow, control in ((False, "wrong-ca"), (True, "https://unowned.invalid"), (1, None)):
                with self.subTest(workflow=workflow), self.assertRaisesRegex(budget.BudgetError, "PrivateUiImportWorkflowRequired"):
                    ui.SyntheticUiSession(identity, Path("/new"), Path("/fixtures"), import_workflow=workflow, import_control=control)

    def test_failed_workflow_fingerprint_cannot_reset_with_a_new_nonce_or_path(self):
        identity = ui.UiIdentity.__new__(ui.UiIdentity)
        identity._issuer, identity._metadata = supervisor._IDENTITY_ISSUER, {"source_sha": "1" * 40}
        identity._sha256, identity.core_sha256 = "2" * 64, "3" * 64
        plan = budget.tcp_plan(65536, 6, 8000)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            old = ui.SyntheticUiSession(identity, root / "old", root)
            first = ui.SyntheticUiSession(identity, root / "first", root, import_workflow=True)
            other = ui.SyntheticUiSession(identity, root / "other", root, import_workflow=True)
            negative = ui.SyntheticUiSession(identity, root / "negative", root, import_workflow=True, import_control="wrong-ca")
            expected_old = supervisor.digest({"workload": ui.UI_WORKLOAD, "fixture_schema": 2, "node": 1,
                "source": "1" * 40, "exe": "2" * 64, "core": "3" * 64, "plan": plan,
                "ca": fixture.FIXTURE_CERT_SHA256, "key": fixture.FIXTURE_KEY_SHA256})
            self.assertEqual(old.fingerprint(plan), expected_old)
            self.assertEqual(first.fingerprint(plan), other.fingerprint(plan))
            self.assertNotEqual(first.fingerprint(plan), old.fingerprint(plan))
            self.assertNotEqual(first.fingerprint(plan), negative.fingerprint(plan))
            with budget.Ledger(root / "synthetic-ledger") as ledger:
                ledger.initialize_synthetic()
                ticket = ledger.reserve_supervised(1, 65536, 6, 8000, config_fingerprint=first.fingerprint(plan),
                    source_sha="1" * 40, worker_sha256="2" * 64, build_id="4" * 64, nonce="5" * 64, workload=ui.UI_WORKLOAD)
                ledger.retain_supervised(ticket, "FailedUiImport")
            with budget.Ledger(root / "synthetic-ledger", existing_only=True) as ledger:
                with self.assertRaisesRegex(budget.BudgetError, "ConfigurationAlreadyAttempted"):
                    ledger.reserve_supervised(1, 65536, 6, 8000, config_fingerprint=other.fingerprint(plan),
                        source_sha="1" * 40, worker_sha256="2" * 64, build_id="4" * 64, nonce="6" * 64, workload=ui.UI_WORKLOAD)
                self.assertEqual(ledger.summary()["heldBytes"], 65536 + 6 * budget.TCP_RECEIVE_RESERVATION)

    def test_ui_flags_cannot_replace_actual_input_receipts_readback_and_transport(self):
        good, owner = sample_observations()
        self.assertIsNone(ui._validate_import_observations(good, owner, None, positive=True, proxy_port=12345))
        changes = [lambda row: row.update(uiDisplayedLatencyMatches=False),
                   lambda row: row["uiImportEvidence"].update(inputEvents=[]),
                   lambda row: row["uiImportEvidence"]["download"].update(tlsVerified=False),
                   lambda row: row["uiImportEvidence"]["download"].update(expectedBodySha256="d" * 64),
                   lambda row: row["uiImportEvidence"].update(importedNodeId=row["uiImportEvidence"]["bootstrapNodeId"]),
                   lambda row: row["uiImportEvidence"]["committedReceipts"][5].update(applied_revision=""),
                   lambda row: row["uiImportEvidence"]["committedReceipts"][5].update(request_id=row["uiImportEvidence"]["committedReceipts"][0]["request_id"]),
                   lambda row: row["uiImportEvidence"]["readbacks"][1].update(selectedImportedNode=False),
                   lambda row: row["uiImportEvidence"]["readbacks"][1].update(saved_revision="5"),
                   lambda row: row["uiImportEvidence"]["routeWitnesses"][2].update(activeNodeReference="0" * 12),
                   lambda row: row["uiImportEvidence"]["routeWitnesses"][4].update(resultNodeReference="0" * 12),
                   lambda row: row["uiImportEvidence"]["routeWitnesses"][6].update(applied_revision="5"),
                   lambda row: row["uiImportEvidence"]["routeWitnesses"][1].update(proxyPort=23456),
                   lambda row: row["uiImportEvidence"].update(routeWitnesses=row["uiImportEvidence"]["routeWitnesses"][:-1]),
                   lambda row: row["uiImportEvidence"]["probePresentation"].update(visible=False),
                   lambda row: row["uiImportEvidence"]["probePresentation"].update(text="出站建立 7 ms · HTTP 204"),
                   lambda row: row["uiImportEvidence"]["coreRouting"]["requests"][0].update(category="direct", rule="builtin:local-v1"),
                   lambda row: row["uiImportEvidence"]["coreRouting"]["requests"][0].update(nodeReference="0" * 12),
                   lambda row: row["uiImportEvidence"]["coreRouting"]["requests"][1].update(sourceReference="0" * 12),
                   lambda row: row["uiImportEvidence"]["coreRouting"]["requests"][1].update(generation="4"),
                   lambda row: row["uiImportEvidence"]["coreRouting"]["requests"][1].update(preexistingConnectionIds=["3"]),
                   lambda row: row["uiImportEvidence"]["coreRouting"]["requests"][0].update(observedConnectionRevision="21"),
                   lambda row: row["uiImportEvidence"]["coreRouting"].update(requests=[])]
        for change in changes:
            altered = copy.deepcopy(good); change(altered)
            with self.assertRaises(budget.BudgetError):
                ui._validate_import_observations(altered, owner, None, positive=True, proxy_port=12345)
        with self.assertRaises(budget.BudgetError):
            ui._validate_import_observations(good, SimpleNamespace(**{**owner.__dict__, "subscription_requests": 0}), None, positive=True, proxy_port=12345)
        with self.assertRaises(budget.BudgetError):
            ui._validate_import_observations(good, owner, "wrong-ca", positive=True, proxy_port=12345)
        # Exercise the actual receipt rejection/report ordering. This pure test
        # issues no ExitProof and never calls admission or settlement: the bad
        # child data must fail before any exit/guard result could be trusted.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            identity = ui.UiIdentity.__new__(ui.UiIdentity)
            identity._issuer, identity._metadata = supervisor._IDENTITY_ISSUER, {"source_sha": "1" * 40}
            identity.core_sha256, identity.qt_version = "2" * 64, "6.12.0"
            session = ui.SyntheticUiSession(identity, root, root, import_workflow=True)
            session.manifest, session.native_stop = {"nonce": "3" * 64, "proxyPort": 12345}, {"triggered": False}
            session.fixture = SimpleNamespace(**owner.__dict__, proofs=1, socks_connections=4, forwarded=4, rejected=0)
            raw = copy.deepcopy(good)
            raw.update(schema=1, nonce="3" * 64, sourceSha="1" * 40, nodeOrdinal=1, passed=True, failureCode="",
                probeCompleted=True, probeSuccess=True, proxyRequests=[], probePhase="response_headers", probeFailureCode="",
                originTlsMs=-1, fixtureOnly=True, liveReady=False, persistentBudgetGuardExercised=False,
                tasksReleased=True, systemNetworkChanged=False, requestDeadlineMs=8000, elapsedMs=100)
            raw["uiImportEvidence"]["routeWitnesses"][4]["resultNodeReference"] = "0" * 12
            (root / "result.json").write_text(json.dumps(raw), encoding="utf-8")
            with mock.patch.object(session, "observe_exit"), self.assertRaisesRegex(budget.BudgetError, "ActualUiImportEvidenceRejected"):
                session.validate_finished({}, None, None)
            self.assertTrue(session.ui_result["uiSubscriptionImportExercised"])
            self.assertFalse(session.import_success_verified)
            self.assertFalse(session.report()["uiSubscriptionImportExercised"])

    def test_live_and_arbitrary_subscription_flags_still_refuse_first(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "must-not-create"
            for flag in ("--live", "--store=PRIVATE_MARKER", "--subscription=PRIVATE_MARKER", "--provider-url=PRIVATE_MARKER"):
                with self.subTest(flag=flag.split("=")[0]), \
                     mock.patch.object(ui, "Ledger", side_effect=AssertionError("ledger accessed")), \
                     mock.patch.object(ui.UiIdentity, "inspect", side_effect=AssertionError("identity process started")):
                    with self.assertRaisesRegex(budget.BudgetError, "PrivateLiveUiAdmissionUnavailable"):
                        ui.main(["--synthetic-ui-import-policy", flag, "--state-dir", str(missing)])
                self.assertFalse(missing.exists())


@unittest.skipUnless(os.name == "nt", "actual paired Windows Qt UI, DPAPI, Job and Core; never simulated")
class ActualUiImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(os.environ["SWIRL_PRIVATE_UI_EXE"])
        cls.exe_hash, cls.core_hash = os.environ["SWIRL_PRIVATE_UI_EXE_SHA256"], os.environ["SWIRL_PRIVATE_UI_CORE_SHA256"]
        cls.source = os.environ["SWIRL_PRIVATE_EXPECTED_SOURCE"]
        cls.fixtures = TOOLS.parent / "src/Swirl.Quick/tests/fixtures"
        cls.qt_root = os.environ.get("SWIRL_PRIVATE_UI_QT_ROOT")
        cls.identity = ui.UiIdentity.inspect(cls.exe, cls.source, cls.exe_hash, expected_core_sha256=cls.core_hash)
        IDENTITIES["qtUi"] = {**cls.identity.metadata, "exe_sha256": cls.exe_hash, "core_sha256": cls.core_hash,
                               "qt_version": cls.identity.qt_version}
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()
        cls.ledger_path = cls.root / "one-synthetic-ledger"
        with budget.Ledger(cls.ledger_path) as ledger:
            ledger.initialize_synthetic()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def invoke(self, label, *, control=None, limit=65536, billing=False):
        state = self.ledger_path
        if billing or control is not None:
            # A failed synthetic case deliberately retains a node hold and
            # cannot admit the next case. Each fault gets a separately declared
            # test fixture account; no original/live ledger is reset or moved.
            # The success and 31-byte controls share one cumulative ledger.
            state = self.root / ("modeled-billing-same-ledger" if billing else "synthetic-fault-ledger-" + control)
            with budget.Ledger(state) as ledger:
                ledger.initialize_synthetic()
        command = [sys.executable, str(TOOLS / "PrivateSubscriptionUi.py"), "--synthetic-ui-import-policy",
                   "--exe", str(self.exe), "--exe-sha256", self.exe_hash, "--core-sha256", self.core_hash,
                   "--expected-source", self.source, "--state-dir", str(state), "--output-directory", str(self.root / label),
                   "--fixture-directory", str(self.fixtures), "--byte-limit", str(limit)]
        if self.qt_root:
            command += ["--qt-root", self.qt_root]
        if control:
            command += ["--synthetic-ui-import-control", control]
        if billing:
            worker = supervisor.WorkerIdentity.inspect(Path(os.environ["SWIRL_PRIVATE_WORKER"]), self.source,
                                                       os.environ["SWIRL_PRIVATE_EXPECTED_WORKER_SHA256"])
            IDENTITIES["billingWorker"] = {**worker.metadata, "exe_sha256": worker.sha256}
            command += ["--synthetic-billing", "--billing-worker", str(worker.path), "--billing-worker-sha256", worker.sha256]
        completed = subprocess.run(command, capture_output=True, timeout=40 if billing else 18)
        self.assertNotIn(b"Traceback", completed.stderr)
        record = json.loads(completed.stdout)
        REPORTS.append({"test": self.id(), "record": record, "actualCliExit": completed.returncode})
        self.assertEqual(record["source_sha"], self.source)
        self.assertFalse(record["liveReady"])
        self.assertEqual(record["providerRequests"], 0)
        self.assertEqual(record["realNodeRequests"], 0)
        self.assertEqual(record["plan"]["timeoutMs"], 8000)
        self.assertEqual(record["plan"]["connectionLimit"], 6)
        self.assertTrue(record["exit"]["processSignaled"])
        self.assertTrue(record["exit"]["ownedProcessSetEmpty"])
        self.assertTrue(record["cleanupConfirmed"])
        self.assertTrue(record["fixture"]["tasksReleased"])
        self.assertFalse(record["fixture"]["ui"]["persistentBudgetGuardExercised"])
        self.assertFalse(record["providerStatisticsAuthenticated"])
        return record, completed.returncode, state

    def assert_success(self, record, code):
        self.assertEqual(code, 0, record)
        self.assertEqual(record["outcome"], "QtUiSucceeded")
        self.assertTrue(record["settled"])
        self.assertTrue(record["uiSubscriptionImportExercised"])
        result = record["fixture"]["ui"]
        self.assertTrue(result["uiPolicySelectionExercised"])
        self.assertTrue(result["uiProbeButtonExercised"])
        self.assertTrue(result["uiDisplayedLatencyMatches"])
        self.assertEqual(record["fixture"]["subscriptionRequests"], 1)
        self.assertEqual(result["probeHttpStatus"], 204)
        self.assertEqual({row["scheme"] for row in result["proxyRequests"]}, {"http", "https"})
        self.assertTrue(all(row["success"] and row["httpStatus"] == 200 for row in result["proxyRequests"]))
        self.assertGreaterEqual(record["guard"]["connection_attempts"], 4)
        self.assertLessEqual(record["guard"]["connection_attempts"], 6)
        self.assertEqual(record["parentBudgetEvidence"]["settledNativeExit"], record["exit"])

    def assert_rejected(self, control, expected, *, request_count, limit=65536):
        record, code, state = self.invoke(control, control=control, limit=limit)
        self.assertEqual(code, 2, record)
        self.assertFalse(record["settled"])
        self.assertTrue(record["parentBudgetEvidence"]["fullHoldRetained"])
        result = record["fixture"]["ui"]
        self.assertFalse(result["passed"])
        self.assertEqual(result["failureCode"], expected)
        self.assertFalse(result["uiSubscriptionImportExercised"])
        self.assertFalse(result["uiPolicySelectionExercised"])
        self.assertFalse(result["uiProbeButtonExercised"])
        self.assertEqual(result["proxyRequests"], [])
        self.assertEqual(record["fixture"]["subscriptionRequests"], request_count)
        with budget.Ledger(state, existing_only=True) as ledger:
            history = ledger.data["history"][record["reservation_id"]]
            self.assertEqual(history["phase"], "unresolved")
            self.assertEqual(history["plan"]["byteLimit"], limit)
            self.assertEqual(history["plan"]["receiveReservation"], 6 * budget.TCP_RECEIVE_RESERVATION)
        return record

    def test_01_real_form_policy_probe_and_same_node_http_https(self):
        record, code, _ = self.invoke("positive")
        self.assert_success(record, code)

    def test_02_same_import_transport_stops_at_31_raw_bytes(self):
        record, code, state = self.invoke("raw-31", limit=31)
        self.assertEqual(code, 0, record)
        self.assertEqual(record["outcome"], "QtUiQuotaStopped")
        self.assertTrue(record["settled"])
        self.assertEqual(record["guard"]["upload"] + record["guard"]["download"], 31)
        self.assertEqual(record["guard"]["connection_attempts"], 1)
        self.assertFalse(record["fixture"]["ui"]["uiSubscriptionImportExercised"])
        self.assertEqual(record["fixture"]["subscriptionRequests"], 0)
        with budget.Ledger(state, existing_only=True) as ledger:
            self.assertEqual(len(ledger.data["history"]), 2)
            self.assertEqual(ledger.summary()["heldBytes"], 0)
            self.assertGreater(ledger.summary()["localUpload"] + ledger.summary()["localDownload"], 31)

    def test_03_wrong_ca_rejects_real_import_tls_without_fallback(self):
        record = self.assert_rejected("wrong-ca", "PrivateUiSubscriptionTlsRejected", request_count=0)
        self.assertEqual(record["guard"]["connection_attempts"], 1)
        self.assertGreater(record["guard"]["upload"] + record["guard"]["download"], 31)

    def test_04_body_limit_rejects_before_parser_commit(self):
        record = self.assert_rejected("over-limit", "PrivateUiSubscriptionBodyLimit", request_count=1, limit=262144)
        self.assertTrue(record["fixture"]["ui"]["uiImportEvidence"]["download"]["tlsVerified"])
        self.assertEqual(record["fixture"]["subscriptionDeclaredBodyBytes"], 65537)
        self.assertEqual(record["guard"]["connection_attempts"], 1)

    def test_05_form_url_mismatch_refuses_before_transport(self):
        record = self.assert_rejected("wrong-url", "PrivateUiSubscriptionDefinitionRejected", request_count=0)
        self.assertEqual(record["guard"]["connection_attempts"], 0)
        self.assertEqual(record["guard"]["upload"] + record["guard"]["download"], 0)

    def test_06_missing_capability_refuses_real_form_before_transport(self):
        record = self.assert_rejected("missing-capability", "PrivateUiSubscriptionDefinitionRejected", request_count=0)
        self.assertFalse(record["fixture"]["ui"]["uiImportEvidence"]["download"]["capabilityInstalled"])
        self.assertEqual(record["guard"]["connection_attempts"], 0)

    def test_07_modeled_billing_same_ledger_wraps_the_real_import_ui(self):
        record, code, state = self.invoke("billing-positive", billing=True)
        self.assert_success(record, code)
        self.assertEqual(len(record["controlQueries"]), 2)
        with budget.Ledger(state, existing_only=True) as ledger:
            self.assertEqual(ledger.data["schema"], 4)
            self.assertEqual(len(ledger.data["history"]), 3)
            self.assertEqual(ledger.summary()["heldBytes"], 0)
            self.assertFalse(ledger.summary()["providerStatisticsAuthenticated"])
            with self.assertRaises(budget.BudgetError):
                ledger.require_live_ready()

    def test_08_missing_grant_has_no_ready_ui_store_or_owned_network_start(self):
        state, output = self.root / "synthetic-no-grant-ledger", self.root / "no-grant-ui"
        plan = budget.tcp_plan(65536, 6, 8000)
        session = ui.SyntheticUiSession(self.identity, output, self.fixtures, qt_root=self.qt_root, import_workflow=True)
        nonce, fingerprint = secrets.token_hex(32), supervisor.digest({"case": "missing-grant", "configuration": session.fingerprint(plan)})
        child = frames = proof = None
        readers_finished = child_closed = fixture_closed = False
        with budget.Ledger(state) as ledger:
            ledger.initialize_synthetic()
            session.check(ledger, self.identity)
            ticket = ledger.reserve_supervised(1, 65536, 6, 8000, config_fingerprint=fingerprint,
                source_sha=self.source, worker_sha256=self.identity.sha256, build_id=self.identity.metadata["build_id"],
                nonce=nonce, workload=ui.UI_WORKLOAD)
            try:
                # The exact owned fixture and manifest exist, but this test
                # deliberately withholds both GRANT/START and the private proof.
                session.open(nonce)
                grant = {"task_id": supervisor.TASK, "ledger_id": ledger.data["ledgerId"], "sequence": int(ticket),
                    "source_sha": self.source, "build_id": self.identity.metadata["build_id"],
                    "byte_limit": 65536, "connection_limit": 6, "receive_reservation": plan["receiveReservation"],
                    "timeout_ms": 8000, "config_fingerprint": fingerprint, **session.grant_fields()}
                ledger.bind_supervised_grant(ticket, supervisor.digest(grant))
                self.identity.recheck()
                deadline = time.monotonic() + 8
                child = session.spawn(deadline)
                ledger.advance_supervised(ticket, "spawned", process=child)
                frames = supervisor._Frames(child)
                child.stdin.close()
                child.process.stdin = None
                proof = child.wait(timeout=max(0.001, deadline - time.monotonic()))
                frames.finish()  # A READY/running/finished line is an error, not ignored output.
                readers_finished = True
                self.assertEqual(proof.record()["exitCode"], 64)
                self.assertFalse(child.timed_out)
                self.assertTrue(proof.record()["processSignaled"])
                self.assertTrue(proof.record()["ownedProcessSetEmpty"])
                self.assertEqual(session.fixture.proofs, 0)
                self.assertEqual(session.fixture.socks_connections, 0)
                self.assertEqual(session.fixture.subscription_requests, 0)
                self.assertEqual(session.fixture.forwarded, 0)
                self.assertFalse(list(output.glob("fixture-store-*")))
                self.assertFalse(list(output.rglob("*.dpapi")))
                self.assertTrue(all(not (output / name).exists() for name in ("state.json", "result.json")))
            finally:
                try:
                    if child is not None:
                        try:
                            child.terminate_and_wait()
                            if frames is not None and not readers_finished:
                                frames.finish()
                        finally:
                            child.close()
                            child_closed = True
                finally:
                    try:
                        session.close()
                        fixture_closed = True
                    finally:
                        # No guard receipt exists. Even a genuine OS exit
                        # cannot turn unknown local transport bytes into zero.
                        ledger.retain_supervised(ticket, "MissingGrantRejected")
            before = ledger.path.read_bytes()
            held = ledger.summary()["heldBytes"]
        with budget.Ledger(state, existing_only=True) as reopened:
            self.assertEqual(reopened.path.read_bytes(), before)
            self.assertEqual(reopened.summary()["heldBytes"], 65536 + 6 * budget.TCP_RECEIVE_RESERVATION)
            self.assertEqual(reopened.summary()["heldBytes"], held)
            self.assertEqual(reopened.data["history"][str(ticket)]["phase"], "unresolved")
            self.assertIsNone(reopened.data["history"][str(ticket)]["receipt"])
        REPORTS.append({"test": self.id(), "scope": "actual paired Qt pre-GRANT rejection; no packet trace or zero-byte inference",
            "sourceSha": self.source, "exit": proof.record(), "readersFinishedWithoutProtocolFrames": readers_finished,
            "childClosed": child_closed, "fixtureClosed": fixture_closed, "fixtureProofs": session.fixture.proofs,
            "socksConnections": session.fixture.socks_connections, "subscriptionRequests": session.fixture.subscription_requests,
            "forwarded": session.fixture.forwarded, "uiStateAndStoreAbsent": True,
            "retainedHoldBytes": held, "localTransportBytes": None, "settled": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--evidence", type=Path)
    options, remaining = parser.parse_known_args()
    if remaining:
        raise SystemExit("Unknown fixed-test option")
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"schema": 1, "scope": "fixed owned HTTPS subscription via actual private Qt form/policy/probe and shared Rust TCP quota",
              "platform": sys.platform, "testsRun": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped], "identities": IDENTITIES,
              "reports": REPORTS, "realNodeRequests": 0, "providerRequests": 0, "providerStatisticsAuthenticated": False, "liveReady": False}
    if options.evidence:
        options.evidence.mkdir(parents=True, exist_ok=False)
        with (options.evidence / "private-ui-import-results.json").open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
