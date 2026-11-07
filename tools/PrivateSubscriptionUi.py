"""Same-ledger mandatory raw-TCP quota for one actual synthetic Qt session.

No private input, provider URL, DNS override, alternate node, live flag or new
account ledger can authorize this path. Qt keeps its actual probe/proxy code;
the paired QA Rust DLL owns the one shared transport quota. This is not a wire
meter or official billing integration.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import time

from PrivateSubscriptionBudget import BudgetError, Ledger, _WindowsStorage
from PrivateSubscriptionProcess import OwnedProcess
from PrivateSubscriptionSupervisor import (WorkerIdentity, Supervisor, _IDENTITY_ISSUER,
    _Frames, _environment, digest, _unique, _PrivateArgumentParser)

_UI_ISSUER = object()
UI_ROLE = "swirl_private_qt_ui"
UI_WORKLOAD = "qt_ui_session"

_IMPORT_INPUTS = ["review-migration", "confirm-migration", "bootstrap-picker", "bootstrap-node", "bootstrap-confirm",
                  "mode-picker", "global-mode", "add-subscription", "subscription-name", "subscription-url",
                  "disable-automatic-refresh", "save-subscription", "use-subscription", "imported-picker",
                  "imported-node", "imported-confirm", "open-imported-node-details", "probe-url", "probe-button"]
_IMPORT_RECEIPT_STAGES = ["migration", "bootstrap-target", "global-mode", "subscription-import", "subscription-scope", "imported-target"]
_IMPORT_ROUTE_STAGES = {"policy-applied", "probe-click", "probe-result", "proxy-http-start", "proxy-https-start",
                        "proxy-http-complete", "proxy-https-complete"}


def _validate_actual_core_routes(evidence, fixture, *, positive):
    """Main-Core observations are independent of UI selection/model witnesses."""
    from RunControlledNodeAcceptance import UI_IMPORT_ORIGIN_HOST
    value = evidence["coreRouting"]
    receipt_fields = {"engine_epoch", "generation", "store_id", "request_id", "applied_revision", "plan_digest"}
    row_fields = {"scheme", "id", "host", "port", "category", "nodeReference", "leafNodeReference", "sourceReference",
                  "rule", "ruleId", "mode", "tier", "revision", "generation", "beforeConnectionRevision",
                  "responseConnectionRevision", "observedConnectionRevision", "preexistingConnectionIds", "closed"}
    def number(text, minimum=1):
        return (type(text) is str and re.fullmatch(r"0|[1-9][0-9]{0,19}", text) is not None
                and minimum <= int(text) <= 2**64 - 1)
    if (type(value) is not dict or set(value) != {"scope", "receipt", "requests"}
            or value["scope"] != "actual-main-core-records-v1" or type(value["receipt"]) is not dict
            or type(value["requests"]) is not list or len(value["requests"]) > 2):
        raise BudgetError("ActualUiCoreRouteEvidenceRejected")
    receipt, rows = value["receipt"], value["requests"]
    if not receipt:
        if positive or rows:
            raise BudgetError("ActualUiCoreRouteEvidenceRejected")
        return
    committed = evidence["committedReceipts"]
    if (set(receipt) != receipt_fields or len(committed) != 6
            or any(not number(receipt[key]) for key in ("engine_epoch", "generation", "applied_revision"))
            or any(receipt[key] != committed[-1][key] for key in ("store_id", "request_id", "applied_revision", "plan_digest"))):
        raise BudgetError("ActualUiCoreRouteEvidenceRejected")
    node = hashlib.sha256(evidence["importedNodeId"].encode("ascii")).hexdigest()[:12]
    source = hashlib.sha256(evidence["sourceId"].encode("ascii")).hexdigest()[:12]
    schemes, ids = set(), set()
    for row in rows:
        if (type(row) is not dict or set(row) != row_fields or row["scheme"] not in ("http", "https")
                or row["scheme"] in schemes or not number(row["id"]) or row["id"] in ids
                or row["host"] != UI_IMPORT_ORIGIN_HOST or type(row["port"]) is not int
                or row["port"] != (fixture.http if row["scheme"] == "http" else fixture.https)
                or row["category"] != "proxy" or row["nodeReference"] != node or row["leafNodeReference"] != node
                or row["sourceReference"] != source or row["rule"] != "policy:default" or row["ruleId"] != "policy:default"
                or row["mode"] != "global" or type(row["tier"]) is not int or row["tier"] != 5
                or row["revision"] != receipt["applied_revision"] or row["generation"] != receipt["generation"]
                or any(not number(row[key], 0) for key in ("beforeConnectionRevision", "responseConnectionRevision", "observedConnectionRevision"))
                or not int(row["beforeConnectionRevision"]) <= int(row["responseConnectionRevision"]) < int(row["observedConnectionRevision"])
                or type(row["preexistingConnectionIds"]) is not list or len(row["preexistingConnectionIds"]) > 128
                or any(not number(old) for old in row["preexistingConnectionIds"])
                or len(set(row["preexistingConnectionIds"])) != len(row["preexistingConnectionIds"])
                or row["id"] in row["preexistingConnectionIds"] or type(row["closed"]) is not bool):
            raise BudgetError("ActualUiCoreRouteEvidenceRejected")
        schemes.add(row["scheme"]); ids.add(row["id"])
    if positive and schemes != {"http", "https"}:
        raise BudgetError("ActualUiCoreRouteSuccessUnproven")


def _validate_import_observations(result, fixture, control, *, positive, proxy_port):
    """Validate observed UI facts only; never manufacture admission/ExitProof."""
    from RunControlledNodeAcceptance import UI_IMPORT_WORKFLOW
    evidence = result.get("uiImportEvidence")
    fields = {"workflow", "control", "phase", "inputEvents", "committedReceipts", "readbacks", "routeWitnesses", "probePresentation", "sourceId",
              "importedNodeId", "bootstrapNodeId", "probeButtonClicked", "download", "coreRouting"}
    download_fields = {"capabilityInstalled", "requests", "tlsVerified", "responseVerified", "responseBytes",
                       "httpStatus", "expectedBodySha256", "failureCode", "route", "bodyLimit", "revoked"}
    receipt_fields = {"stage", "request_id", "store_id", "saved_revision", "applied_revision", "plan_digest"}
    readback_fields = {"stage", "independentNodeStore", "configurationV2", "sourceCount", "nodeCount",
                       "importedNodeId", "sourceId", "selectedImportedNode", "saved_revision", "ciphertextSha256"}
    route_fields = {"stage", "selectedNodeReference", "activeNodeReference", "defaultNodeReference", "resultNodeReference",
                    "request_id", "saved_revision", "applied_revision", "plan_digest", "proxyPort", "routingMode"}

    def uuid(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value) is not None and value != "00000000-0000-0000-0000-000000000000"

    def sha(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    def revision(value):
        return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value) is not None and int(value) <= 2**64 - 1

    if (type(evidence) is not dict or set(evidence) != fields or evidence["workflow"] != UI_IMPORT_WORKFLOW
            or evidence["control"] != (control or "") or type(evidence["phase"]) is not int or not 0 <= evidence["phase"] <= 32
            or type(evidence["inputEvents"]) is not list
            or evidence["inputEvents"] != _IMPORT_INPUTS[:len(evidence["inputEvents"])]
            or type(evidence["probeButtonClicked"]) is not bool
            or any(type(result.get(key)) is not bool for key in ("uiProbeButtonExercised", "uiDisplayedLatencyMatches"))
            or not uuid(evidence["bootstrapNodeId"])
            or any(value != "" and not uuid(value) for value in (evidence["sourceId"], evidence["importedNodeId"]))):
        raise BudgetError("ActualUiImportEvidenceRejected")
    download = evidence["download"]
    if (type(download) is not dict or set(download) != download_fields
            or any(type(download[key]) is not bool for key in ("capabilityInstalled", "tlsVerified", "responseVerified", "revoked"))
            or type(download["requests"]) is not int or download["requests"] not in (0, 1)
            or type(download["httpStatus"]) is not int or not 0 <= download["httpStatus"] <= 599
            or type(download["responseBytes"]) is not int or not 0 <= download["responseBytes"] <= 65537
            or download["expectedBodySha256"] not in ("", fixture.subscription_body_sha256)
            or type(download["failureCode"]) is not str or len(download["failureCode"]) > 128
            or download["route"] != "granted-core-http-listener" or type(download["bodyLimit"]) is not int
            or download["bodyLimit"] != 65536 or download["revoked"] is not True):
        raise BudgetError("ActualUiImportEvidenceRejected")
    receipts, readbacks = evidence["committedReceipts"], evidence["readbacks"]
    if (type(receipts) is not list or len(receipts) > 6 or type(readbacks) is not list or len(readbacks) > 2):
        raise BudgetError("ActualUiImportEvidenceRejected")
    previous = 0
    request_ids, store_ids = set(), set()
    for index, receipt in enumerate(receipts):
        if (type(receipt) is not dict or set(receipt) != receipt_fields or receipt["stage"] != _IMPORT_RECEIPT_STAGES[index]
                or not uuid(receipt["request_id"]) or not uuid(receipt["store_id"]) or not sha(receipt["plan_digest"])
                or not revision(receipt["saved_revision"]) or int(receipt["saved_revision"]) <= previous
                or receipt["applied_revision"] not in ("", receipt["saved_revision"]) or receipt["request_id"] in request_ids):
            raise BudgetError("ActualUiImportEvidenceRejected")
        previous = int(receipt["saved_revision"])
        request_ids.add(receipt["request_id"])
        store_ids.add(receipt["store_id"])
    if len(store_ids) > 1:
        raise BudgetError("ActualUiImportEvidenceRejected")
    for index, readback in enumerate(readbacks):
        if (type(readback) is not dict or set(readback) != readback_fields
                or readback["stage"] != ("imported-catalog", "selected-imported-node")[index]
                or readback["independentNodeStore"] is not True or readback["configurationV2"] is not True
                or type(readback["sourceCount"]) is not int or readback["sourceCount"] != 1
                or type(readback["nodeCount"]) is not int or readback["nodeCount"] != 2
                or readback["importedNodeId"] != evidence["importedNodeId"] or not uuid(readback["importedNodeId"])
                or readback["sourceId"] != evidence["sourceId"] or not uuid(readback["sourceId"])
                or readback["selectedImportedNode"] is not (index == 1)
                or not revision(readback["saved_revision"]) or not sha(readback["ciphertextSha256"])):
            raise BudgetError("ActualUiImportEvidenceRejected")
    routes = evidence["routeWitnesses"]
    if type(routes) is not list or len(routes) > len(_IMPORT_ROUTE_STAGES):
        raise BudgetError("ActualUiImportEvidenceRejected")
    reference = hashlib.sha256(evidence["importedNodeId"].encode("ascii")).hexdigest()[:12]
    stages = []
    for route in routes:
        if (type(route) is not dict or set(route) != route_fields or type(route["stage"]) is not str or route["stage"] not in _IMPORT_ROUTE_STAGES
                or route["stage"] in stages or len(receipts) != 6 or not uuid(evidence["importedNodeId"])
                or any(route[key] != reference for key in ("selectedNodeReference", "activeNodeReference", "defaultNodeReference"))
                or route["resultNodeReference"] != (reference if route["stage"] == "probe-result" else "")
                or route["request_id"] != receipts[-1]["request_id"] or route["plan_digest"] != receipts[-1]["plan_digest"]
                or route["saved_revision"] != receipts[-1]["saved_revision"] or route["applied_revision"] != route["saved_revision"]
                or type(route["proxyPort"]) is not int or route["proxyPort"] != proxy_port or route["routingMode"] != "global"):
            raise BudgetError("ActualUiImportEvidenceRejected")
        stages.append(route["stage"])
    presentation = evidence["probePresentation"]
    if (type(presentation) is not dict or set(presentation) != {"visible", "text", "nodeReference", "latency", "outboundConnectMs", "httpStatus"}
            or type(presentation["visible"]) is not bool or type(presentation["text"]) is not str or len(presentation["text"]) > 1024
            or presentation["nodeReference"] not in ("", reference)
            or any(type(presentation[key]) is not int or presentation[key] < -1 for key in ("latency", "outboundConnectMs"))
            or type(presentation["httpStatus"]) is not int or not 0 <= presentation["httpStatus"] <= 599):
        raise BudgetError("ActualUiImportEvidenceRejected")
    _validate_actual_core_routes(evidence, fixture, positive=positive)
    if not positive:
        return
    if (control is not None or result.get("uiSubscriptionImportExercised") is not True
            or result.get("uiPolicySelectionExercised") is not True or result.get("uiProbeButtonExercised") is not True
            or result.get("uiDisplayedLatencyMatches") is not True or evidence["probeButtonClicked"] is not True
            or evidence["phase"] != 32 or evidence["inputEvents"] != _IMPORT_INPUTS
            or len(receipts) != 6 or len(readbacks) != 2 or evidence["importedNodeId"] == evidence["bootstrapNodeId"]
            or result.get("selectedNodeReference") != reference or set(stages) != _IMPORT_ROUTE_STAGES
            or stages[:2] != ["policy-applied", "probe-click"]
            or any(stages.index("proxy-" + scheme + "-start") > stages.index("proxy-" + scheme + "-complete") for scheme in ("http", "https"))
            or presentation["visible"] is not True or presentation["nodeReference"] != reference
            or presentation["httpStatus"] != 204 or presentation["httpStatus"] != result.get("probeHttpStatus")
            or presentation["latency"] != result.get("uiHeadersMs") or presentation["outboundConnectMs"] != result.get("outboundConnectMs")
            or presentation["outboundConnectMs"] < 0 or "HTTP 204" not in presentation["text"]
            or f'{presentation["outboundConnectMs"]} ms' not in presentation["text"]
            or download["capabilityInstalled"] is not True or download["requests"] != 1 or download["tlsVerified"] is not True
            or download["responseVerified"] is not True or download["httpStatus"] != 200 or download["failureCode"] != ""
            or download["expectedBodySha256"] != fixture.subscription_body_sha256
            or fixture.subscription_requests != 1 or download["responseBytes"] != fixture.subscription_declared_body_bytes
            or not 0 < download["responseBytes"] <= 65536
            or readbacks[0]["saved_revision"] != receipts[3]["saved_revision"]
            or readbacks[1]["saved_revision"] != receipts[5]["saved_revision"]
            or receipts[-1]["applied_revision"] != receipts[-1]["saved_revision"]):
        raise BudgetError("ActualUiImportSuccessUnproven")


def _local_path(path):
    # Reject remote/ADS/current-drive ambiguity before exists/stat/resolve can
    # follow an attacker-supplied network path outside the synthetic guard.
    if os.name == "nt":
        if not re.fullmatch(r"[A-Za-z]:", path.drive) or ":" in str(path)[2:]:
            raise BudgetError("LocalUiPathRequired")
        import ctypes as c
        from ctypes import wintypes as w
        kernel = c.WinDLL("kernel32", use_last_error=True)
        kernel.GetDriveTypeW.argtypes, kernel.GetDriveTypeW.restype = [w.LPCWSTR], w.UINT
        if kernel.GetDriveTypeW(path.anchor) != 3:
            raise BudgetError("LocalUiPathRequired")
    if not path.is_absolute():
        raise BudgetError("LocalUiPathRequired")
    for component in reversed([path, *path.parents]):
        try:
            info = component.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BudgetError("LocalUiPathRequired")
    return path


class UiIdentity(WorkerIdentity):
    """A separately hashed EXE/DLL pair, inspected before workload admission."""

    @classmethod
    def inspect(cls, path, expected_source, expected_worker_sha256=None, *, expected_core_sha256=None):
        if (not isinstance(expected_source, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_source)
                or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in (expected_worker_sha256, expected_core_sha256))):
            raise BudgetError("TrustedQaBinaryIdentityRequired")
        path = Path(path).absolute()
        core = path.parent / ("swirl_api.dll" if os.name == "nt" else "libswirl_api.so")
        if cls._hash(path) != expected_worker_sha256 or cls._hash(core) != expected_core_sha256:
            raise BudgetError("TrustedQaBinaryIdentityRequired")
        process = frames = None
        readers_finished = False
        try:
            deadline = time.monotonic() + 2
            process = OwnedProcess([str(path), "--private-ui-quota-build-info"],
                                   deadline=deadline, environment=_environment())
            frames = _Frames(process)
            value = frames.receive(deadline)
            proof = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            frames.finish()
            readers_finished = True
            metadata = value.get("identity")
            fields = {"private_worker_schema", "role", "guard_mode", "live", "abi_version",
                      "source_sha", "build_id", "target", "package_version"}
            if (set(value) != {"identity", "qt_version", "scope"}
                    or value["qt_version"] != "6.12.0" or value["scope"] != "fixed-synthetic-qt-ui"
                    or not isinstance(metadata, dict) or set(metadata) != fields
                    or type(metadata["private_worker_schema"]) is not int or metadata["private_worker_schema"] != 1
                    or metadata["role"] != UI_ROLE or metadata["guard_mode"] != "mandatory_before_grant"
                    or metadata["live"] is not False or type(metadata["abi_version"]) is not int or metadata["abi_version"] != 1
                    or metadata["source_sha"] != expected_source
                    or not isinstance(metadata["build_id"], str) or not re.fullmatch(r"[0-9a-f]{64}", metadata["build_id"])
                    or not isinstance(metadata["target"], str) or not re.fullmatch(r"[a-z0-9_-]{1,80}", metadata["target"])
                    or not isinstance(metadata["package_version"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,63}", metadata["package_version"])
                    or proof.record()["exitCode"] != 0):
                raise BudgetError("PrivateUiIdentityRejected")
            identity = cls(path, metadata, expected_worker_sha256, _issuer=_IDENTITY_ISSUER)
            identity.core_path, identity.core_sha256 = core, expected_core_sha256
            identity.qt_version = value["qt_version"]
            identity.recheck()
            return identity
        finally:
            if process is not None:
                try:
                    process.terminate_and_wait()
                    if frames is not None and not readers_finished:
                        frames.finish()
                finally:
                    process.close()

    def recheck(self):
        super().recheck()
        if self._hash(self.core_path) != self.core_sha256:
            raise BudgetError("PrivateUiCoreChanged")


def _validate_dns_observations(result, fixture, control, *, plan, binding, final_guard, positive):
    """Require production-resolver and native-quota facts, never a DNS-ready flag."""
    from RunControlledNodeAcceptance import (UI_DNS_WORKFLOW, UI_DNS_HOST, FIXTURE_CERT_SHA256,
        WRONG_CA_SHA256, fixed_dns_configuration, json_bytes)
    value = result.get("uiDnsEvidence")
    fields = {"workflow", "control", "configured", "configurationSha256", "trustBindingSha256",
              "caSha256", "queryHost", "resolverAddress", "snapshots"}
    if (type(value) is not dict or set(value) != fields or value["workflow"] != UI_DNS_WORKFLOW
            or value["control"] != (control or "") or type(value["configured"]) is not bool
            or value["queryHost"] != UI_DNS_HOST or value["resolverAddress"] != f"127.0.0.1:{fixture.socks}"
            or value["caSha256"] != (WRONG_CA_SHA256 if control == "wrong-ca" else FIXTURE_CERT_SHA256)
            or value["trustBindingSha256"] != digest(binding)
            or type(value["snapshots"]) is not list or len(value["snapshots"]) > len(_IMPORT_ROUTE_STAGES)
            or any(type(row) is not dict or set(row) != {"stage", "guard"} for row in value["snapshots"])):
        raise BudgetError("ActualUiDnsEvidenceRejected")
    expected_config = hashlib.sha256(json_bytes(fixed_dns_configuration(fixture.socks))).hexdigest()
    if value["configurationSha256"] != (expected_config if value["configured"] else ""):
        raise BudgetError("ActualUiDnsEvidenceRejected")
    routes = result.get("uiImportEvidence", {}).get("routeWitnesses", [])
    if [row.get("stage") for row in value["snapshots"]] != [row.get("stage") for row in routes]:
        raise BudgetError("ActualUiDnsEvidenceRejected")
    last = {"upload": 0, "download": 0, "connection_attempts": 0}
    from PrivateSubscriptionBudget import validate_guard_receipt
    for row in value["snapshots"]:
        if type(row) is not dict or set(row) != {"stage", "guard"}:
            raise BudgetError("ActualUiDnsEvidenceRejected")
        validate_guard_receipt(row["guard"], plan, terminal=False)
        if any(not last[key] <= row["guard"][key] <= final_guard[key] for key in last):
            raise BudgetError("ActualUiDnsCounterRegression")
        last = {key: row["guard"][key] for key in last}
    if not positive:
        return
    observed = fixture.dns_report()
    stages = [row["stage"] for row in routes]
    guards = {row["stage"]: row["guard"] for row in value["snapshots"]}
    expected_attempts = {"policy-applied": 1, "probe-click": 1, "probe-result": 3,
                        "proxy-http-start": 3, "proxy-http-complete": 5,
                        "proxy-https-start": 5, "proxy-https-complete": 6}
    if (control is not None or value["configured"] is not True or len(observed["queries"]) != 2
            or observed["tlsAttempts"] != 2 or observed["tlsCompleted"] != 2
            or final_guard["timed_out"] is not False
            or any(row["guard"]["timed_out"] is not False or row["guard"]["stopped"] is not False
                   for row in value["snapshots"])
            or set(guards) != set(expected_attempts)
            or stages.index("probe-result") > stages.index("proxy-http-start")
            or stages.index("proxy-http-complete") > stages.index("proxy-https-start")
            or any(guards[stage]["connection_attempts"] != count for stage, count in expected_attempts.items())
            or any(row["queryHost"] != UI_DNS_HOST or row["queryType"] != "A"
                   or row["answerAddress"] != "127.0.0.1" or row["questionMatched"] is not True
                   or row["responseSent"] is not True for row in observed["queries"])):
        raise BudgetError("ActualUiDnsSuccessUnproven")


class SyntheticUiSession:
    """One exact parent-owned fixed TLS/SOCKS fixture, never an endpoint API."""

    def __init__(self, identity, output, fixture_directory, *, qt_root=None, import_workflow=False, import_control=None,
                 dns_workflow=False, dns_control=None):
        if type(identity) is not UiIdentity or getattr(identity, "_issuer", None) is not _IDENTITY_ISSUER:
            raise BudgetError("PrivateUiIdentityRequired")
        from RunControlledNodeAcceptance import UI_IMPORT_CONTROLS
        if (type(import_workflow) is not bool or import_control is not None and import_control not in UI_IMPORT_CONTROLS
                or import_control is not None and not import_workflow):
            raise BudgetError("PrivateUiImportWorkflowRequired")
        from RunControlledNodeAcceptance import UI_DNS_CONTROLS
        if (type(dns_workflow) is not bool or dns_control is not None and dns_control not in UI_DNS_CONTROLS
                or dns_control is not None and not dns_workflow
                or dns_workflow and (not import_workflow or import_control is not None)):
            raise BudgetError("PrivateUiDnsWorkflowRequired")
        self._issuer, self.identity = _UI_ISSUER, identity
        self.import_workflow, self.import_control = import_workflow, import_control
        self.dns_workflow, self.dns_control = dns_workflow, dns_control
        self.root, self.fixture_directory = _local_path(Path(output)), _local_path(Path(fixture_directory))
        self.qt_root = None if qt_root is None else _local_path(Path(qt_root))
        self.fixture = self.storage = self.native_receipt = None
        self.manifest = self.proof = self.native_handle = self.child_environment = None
        self.ui_result = self.native_stop = None
        self.import_success_verified = False
        self.dns_success_verified = False
        self.quota_proof = None
        self.closed = False

    def check(self, ledger, identity, *, billing=None):
        if (self._issuer is not _UI_ISSUER or self.identity is not identity or self.fixture is not None
                or ledger.data["schema"] not in (3, 4) or self.root.exists()
                or any(path.is_symlink() for path in (self.root, *self.root.parents))):
            raise BudgetError("NewSyntheticUiSessionRequired")
        if ledger.data["schema"] == 4:
            if billing is None:
                raise BudgetError("SyntheticBillingSessionRequired")
            ledger._require_billing_session(billing)
        elif billing is not None:
            raise BudgetError("SyntheticBillingSessionRequired")
        if os.name != "nt":
            raise BudgetError("NativeWindowsUiAcceptanceRequired")

    def fingerprint(self, plan):
        from RunControlledNodeAcceptance import FIXTURE_CERT_SHA256, FIXTURE_KEY_SHA256
        # No ephemeral port or nonce can turn the same failed configuration into
        # a new attempt. Plan/source changes are explicit reviewable differences.
        configuration = {"workload": UI_WORKLOAD, "fixture_schema": 2, "node": 1,
                       "source": self.identity.metadata["source_sha"], "exe": self.identity.sha256,
                       "core": self.identity.core_sha256, "plan": plan,
                       "ca": FIXTURE_CERT_SHA256, "key": FIXTURE_KEY_SHA256}
        if self.import_workflow:
            from RunControlledNodeAcceptance import UI_IMPORT_WORKFLOW, fixed_ui_origin
            configuration.update(uiWorkflow=UI_IMPORT_WORKFLOW, uiImportControl=self.import_control,
                                 uiOrigin=fixed_ui_origin())
        if self.dns_workflow:
            from RunControlledNodeAcceptance import UI_DNS_WORKFLOW
            configuration.update(uiDnsWorkflow=UI_DNS_WORKFLOW, uiDnsControl=self.dns_control)
        return digest(configuration)

    def open(self, nonce):
        from RunControlledNodeAcceptance import (LoopbackFixture, FIXTURE_CERT_SHA256,
            FIXTURE_KEY_SHA256, WRONG_CA_SHA256, UI_IMPORT_WORKFLOW, local_file, environment, write_json)
        certificate = local_file(self.fixture_directory / "localhost-cert.pem")
        key = local_file(self.fixture_directory / "localhost-key.pem")
        if (hashlib.sha256(certificate.read_bytes()).hexdigest() != FIXTURE_CERT_SHA256
                or hashlib.sha256(key.read_bytes()).hexdigest() != FIXTURE_KEY_SHA256):
            raise BudgetError("CommittedSyntheticTlsFixtureRequired")
        ca = certificate
        if self.import_control == "wrong-ca":
            ca = local_file(self.fixture_directory / "xray-download-server-cert.pem")
            if hashlib.sha256(ca.read_bytes()).hexdigest() != WRONG_CA_SHA256:
                raise BudgetError("CommittedSyntheticTlsFixtureRequired")
        self.storage = _WindowsStorage()
        self.storage.prepare(self.root)
        self.fixture = LoopbackFixture(certificate, key)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            proxy_port = reservation.getsockname()[1]
        self.manifest = {"schema": 2, "sourceSha": self.identity.metadata["source_sha"],
                         "nonce": nonce, "nodeOrdinal": 1, "proxyPort": proxy_port,
                         "fixture": {"httpPort": self.fixture.http, "httpsPort": self.fixture.https,
                                     "socksPort": self.fixture.socks, "caSha256": hashlib.sha256(ca.read_bytes()).hexdigest()}}
        if self.import_workflow:
            self.manifest["uiWorkflow"] = UI_IMPORT_WORKFLOW
            from RunControlledNodeAcceptance import fixed_ui_origin
            self.manifest["uiOrigin"] = fixed_ui_origin()
            if self.import_control is not None:
                self.manifest["uiImportControl"] = self.import_control
        if self.dns_workflow:
            from RunControlledNodeAcceptance import UI_DNS_WORKFLOW
            dns_ca = certificate
            if self.dns_control == "wrong-ca":
                dns_ca = local_file(self.fixture_directory / "xray-download-server-cert.pem")
                if hashlib.sha256(dns_ca.read_bytes()).hexdigest() != WRONG_CA_SHA256:
                    raise BudgetError("CommittedSyntheticTlsFixtureRequired")
            self.manifest["uiDns"] = {"workflow": UI_DNS_WORKFLOW, "control": self.dns_control or "",
                                      "caSha256": hashlib.sha256(dns_ca.read_bytes()).hexdigest()}
            with (self.root / "dns-ca.pem").open("xb") as destination:
                destination.write(dns_ca.read_bytes())
        self.proof = self.fixture.bind_session(self.manifest)
        with (self.root / "fixture-ca.pem").open("xb") as destination:
            destination.write(ca.read_bytes())
        write_json(self.root / "session.json", self.manifest)
        self.child_environment = environment(self.root, self.qt_root)
        return self

    def grant_fields(self):
        if self.fixture is None or self.manifest is None or self.closed:
            raise BudgetError("OwnedSyntheticUiFixtureRequired")
        return {"role": "synthetic_qt_ui", "workload": UI_WORKLOAD,
                "endpoint": {"host": "127.0.0.1", "port": self.fixture.socks},
                "listener": {"host": "127.0.0.1", "port": self.manifest["proxyPort"]}}

    def spawn(self, deadline):
        from ControlledNodeWatchdog import NativeWatchdogReceipt
        child = OwnedProcess([str(self.identity.path), "--private-ui-quota",
                              "--controlled-node-session=" + str(self.root)],
                             deadline=deadline, environment=self.child_environment, suspended=True)
        try:
            self.native_receipt = NativeWatchdogReceipt(child.job, self.manifest)
            self.native_handle = self.native_receipt.duplicate_to(child.process)
            child.resume()
            return child
        except BaseException:
            # This does not settle a reservation. Actual owner cleanup failure
            # is visible, and the caller conservatively retains the full hold.
            child.close()
            raise

    def send_fixture_proof(self, child):
        if self.native_handle is None:
            raise BudgetError("NativeWatchdogPreparationRequired")
        from RunControlledNodeAcceptance import PROOF_MAGIC
        if PROOF_MAGIC != b"SWIRL-FIXTURE-PROOF-2\n":
            raise BudgetError("NativeWatchdogV2ProofRequired")
        frame = self.proof.pipe_frame(self.manifest) + self.native_handle
        if len(frame) != len(PROOF_MAGIC) + 104:
            raise BudgetError("NativeWatchdogV2ProofRequired")
        try:
            if child.stdin.write(frame) != len(frame):
                raise BudgetError("PrivateFixtureProofWriteFailed")
            child.stdin.flush()
            child.stdin.close()
            child.process.stdin = None
        except (OSError, ValueError):
            raise BudgetError("PrivateFixtureProofWriteFailed") from None

    def observe_exit(self, child):
        if self.native_receipt is None:
            raise BudgetError("NativeWatchdogPreparationRequired")
        if self.native_stop is None:
            self.native_stop = self.native_receipt.read_after_exit(child.process)

    def validate_finished(self, reply, exit_proof, child):
        self.import_success_verified = False
        self.dns_success_verified = False
        self.observe_exit(child)
        path = self.root / "result.json"
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
            raise BudgetError("ActualUiReceiptRequired")
        try:
            result = json.loads(path.read_text("utf-8"), object_pairs_hook=_unique)
        except (OSError, ValueError, UnicodeError):
            raise BudgetError("ActualUiReceiptRejected") from None
        fields = {"schema", "nonce", "sourceSha", "nodeOrdinal", "passed", "failureCode",
                  "selectedNodeReference", "probeCompleted", "probeSuccess", "uiHeadersMs", "proxyRequests",
                  "probeHttpStatus", "probePhase", "probeFailureCode", "outboundConnectMs", "originTlsMs",
                  "fixtureOnly", "liveReady", "persistentBudgetGuardExercised", "uiSubscriptionImportExercised",
                  "uiPolicySelectionExercised", "tasksReleased", "systemNetworkChanged", "requestDeadlineMs", "elapsedMs"}
        row_fields = {"scheme", "httpStatus", "success", "qtError", "tlsRejected", "bodyLimitExceeded",
                      "elapsedMs", "exitIpSha256", "responseEncrypted"}
        if self.import_workflow:
            fields.update({"uiImportEvidence", "uiProbeButtonExercised", "uiDisplayedLatencyMatches"})
        if self.dns_workflow:
            fields.add("uiDnsEvidence")
        if (not isinstance(result, dict) or set(result) != fields or type(result["schema"]) is not int or result["schema"] != 1
                or result.get("nonce") != self.manifest["nonce"]
                or result.get("sourceSha") != self.identity.metadata["source_sha"]
                or type(result.get("nodeOrdinal")) is not int or result["nodeOrdinal"] != 1 or result.get("fixtureOnly") is not True
                or result.get("liveReady") is not False or result.get("tasksReleased") is not True
                or result.get("systemNetworkChanged") is not False
                or result.get("requestDeadlineMs") != 8000 or self.native_stop.get("triggered")
                or type(result.get("proxyRequests")) is not list
                or any(type(row) is not dict or set(row) != row_fields for row in result["proxyRequests"])
                or result.get("persistentBudgetGuardExercised") is not False
                or type(result.get("uiSubscriptionImportExercised")) is not bool
                or type(result.get("uiPolicySelectionExercised")) is not bool
                or not self.import_workflow and (result["uiSubscriptionImportExercised"] is not False
                                               or result["uiPolicySelectionExercised"] is not False)
                or self.fixture.proofs != 1):
            raise BudgetError("ActualUiReceiptRejected")
        self.ui_result = {key: value for key, value in result.items() if key != "nonce"}
        if self.import_workflow:
            _validate_import_observations(result, self.fixture, self.import_control, positive=False, proxy_port=self.manifest["proxyPort"])
        guard = reply["guard"]
        if self.dns_workflow:
            from PrivateSubscriptionBudget import tcp_plan
            plan = tcp_plan(guard["byte_limit"], guard["connection_limit"], guard["timeout_ms"])
            binding = {key: reply[key] for key in ("schema", "reservation_id", "nonce", "plan_digest")}
            _validate_dns_observations(result, self.fixture, self.dns_control, plan=plan, binding=binding,
                                       final_guard=guard, positive=False)
        if reply.get("raw_tcp_quota_exercised") is not True:
            raise BudgetError("ActualUiRawQuotaUnproven")
        self.quota_proof = {"scope": reply["scope"], "rawTcpQuotaExercised": reply["raw_tcp_quota_exercised"],
                            "sourceSha": reply["source_sha"], "buildId": reply["build_id"],
                            "reservationId": reply["reservation_id"], "planDigest": reply["plan_digest"],
                            "guard": guard.copy()}
        if reply["outcome"] == "quota_stopped":
            if (exit_proof.record()["exitCode"] != 2 or result.get("passed") is not False
                    or guard["upload"] + guard["download"] != guard["byte_limit"]
                    or guard["connection_attempts"] == 0 or self.fixture.socks_connections == 0
                    or any(row.get("success") is True for row in result.get("proxyRequests", []))):
                raise BudgetError("ActualUiQuotaStopUnproven")
            return "QtUiQuotaStopped"
        rows = result.get("proxyRequests")
        if (reply["outcome"] != "qt_ui_finished" or exit_proof.record()["exitCode"] != 0
                or result.get("passed") is not True or result.get("probeCompleted") is not True
                or result.get("probeSuccess") is not True or result.get("probeHttpStatus") != 204
                or type(result.get("uiHeadersMs")) is not int or result["uiHeadersMs"] < 0
                or type(rows) is not list or len(rows) != 2 or {row.get("scheme") for row in rows} != {"http", "https"}
                or any(row.get("httpStatus") != 200 or row.get("success") is not True
                       or row.get("tlsRejected") is not False or row.get("bodyLimitExceeded") is not False
                       or row.get("responseEncrypted") is not True for row in rows)
                or not any(row.get("scheme") == "https" and re.fullmatch(r"[0-9a-f]{64}", row.get("exitIpSha256", "")) for row in rows)
                or guard["upload"] <= 0 or guard["download"] <= 0 or guard["connection_attempts"] < 3
                or self.fixture.forwarded < 3 or self.fixture.rejected != 0):
            raise BudgetError("ActualUiSuccessUnproven")
        if self.import_workflow:
            _validate_import_observations(result, self.fixture, self.import_control, positive=True, proxy_port=self.manifest["proxyPort"])
            if guard["connection_attempts"] < 4 or self.fixture.forwarded < 4:
                raise BudgetError("ActualUiImportTransportUnproven")
            if self.dns_workflow:
                _validate_dns_observations(result, self.fixture, self.dns_control, plan=plan, binding=binding,
                                           final_guard=guard, positive=True)
                if guard["connection_attempts"] != 6 or self.fixture.socks_connections != 4 or self.fixture.forwarded != 4:
                    raise BudgetError("ActualUiDnsTransportUnproven")
                self.dns_success_verified = True
            self.import_success_verified = True
        return "QtUiSucceeded"

    def report(self):
        result = {"scope": "owned-fixed-synthetic-qt-ui", "coreSha256": self.identity.core_sha256,
                "qtVersion": self.identity.qt_version, "ui": self.ui_result, "nativeWatchdog": self.native_stop,
                "guardedSessionProof": self.quota_proof,
                "ownershipProofs": 0 if self.fixture is None else self.fixture.proofs,
                "socksConnections": 0 if self.fixture is None else self.fixture.socks_connections,
                "forwarded": 0 if self.fixture is None else self.fixture.forwarded,
                "rejected": 0 if self.fixture is None else self.fixture.rejected,
                "tasksReleased": self.closed, "uiSubscriptionImportExercised": bool(
                    self.import_workflow and self.import_success_verified),
                "rawCounterScope": "shared Rust TCP below TLS/protocol; excludes Qt-only local control proof",
                "wireMeteringProven": False}
        if self.import_workflow:
            result.update(uiWorkflow="subscription-policy-v1", uiImportControl=self.import_control,
                subscriptionRequests=0 if self.fixture is None else self.fixture.subscription_requests,
                subscriptionDeclaredBodyBytes=0 if self.fixture is None else self.fixture.subscription_declared_body_bytes)
        if self.dns_workflow:
            result.update(uiDnsExercised=self.dns_success_verified,
                          dns=None if self.fixture is None else self.fixture.dns_report())
        return result

    def close(self):
        if self.closed:
            return
        failures = []
        for resource in (self.fixture, self.native_receipt, self.storage):
            if resource is not None:
                try:
                    resource.close()
                    if self.dns_workflow and resource is self.fixture:
                        observed = resource.dns_report()
                        if (type(observed) is not dict or observed.get("listenersClosed") is not True
                                or observed.get("tasksReleased") is not True):
                            raise BudgetError("UiFixtureExitUnconfirmed")
                except (OSError, ValueError, BudgetError):
                    failures.append(True)
        if failures:
            raise BudgetError("UiFixtureExitUnconfirmed")
        self.closed = True


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # No file, output directory, identity subprocess or socket precedes this.
    if any(value == flag or value.startswith(flag + "=") for value in argv
           for flag in ("--live", "--store", "--subscription", "--provider-url")):
        raise BudgetError("PrivateLiveUiAdmissionUnavailable")
    parser = _PrivateArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--exe-sha256", required=True)
    parser.add_argument("--core-sha256", required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--fixture-directory", type=Path, required=True)
    parser.add_argument("--qt-root", type=Path)
    parser.add_argument("--byte-limit", type=int, default=65536)
    parser.add_argument("--synthetic-ui-import-policy", action="store_true")
    parser.add_argument("--synthetic-ui-import-control", choices=("wrong-ca", "over-limit", "wrong-url", "missing-capability"))
    parser.add_argument("--synthetic-ui-dns", action="store_true")
    parser.add_argument("--synthetic-ui-dns-control", choices=("wrong-ca", "wrong-address", "wrong-question", "stall"))
    parser.add_argument("--synthetic-billing", action="store_true")
    parser.add_argument("--billing-worker", type=Path)
    parser.add_argument("--billing-worker-sha256")
    parser.add_argument("--billing-response-contract", choices=("synthetic_qa_v1", "subscription_userinfo_v1"),
                        default="synthetic_qa_v1")
    args = parser.parse_args(argv)
    if args.synthetic_ui_import_control is not None and not args.synthetic_ui_import_policy:
        raise BudgetError("PrivateUiImportWorkflowRequired")
    if ((args.synthetic_ui_dns_control is not None and not args.synthetic_ui_dns)
            or args.synthetic_ui_dns and (not args.synthetic_ui_import_policy or args.synthetic_ui_import_control is not None)):
        raise BudgetError("PrivateUiDnsWorkflowRequired")
    if ((args.synthetic_billing and (args.billing_worker is None or args.billing_worker_sha256 is None))
            or (not args.synthetic_billing and (args.billing_worker is not None or args.billing_worker_sha256 is not None
                                              or args.billing_response_contract != "synthetic_qa_v1"))):
        raise BudgetError("PairedBillingWorkerIdentityRequired")
    if os.name != "nt":
        raise BudgetError("NativeWindowsUiAcceptanceRequired")
    _local_path(args.state_dir)
    Ledger.require_existing(args.state_dir)
    with Ledger(args.state_dir, existing_only=True) as ledger:
        ledger.require_synthetic()
        if ledger.data["schema"] != 3:
            raise BudgetError("SyntheticUiLedgerRequired")
        identity = UiIdentity.inspect(args.exe, args.expected_source, args.exe_sha256,
                                      expected_core_sha256=args.core_sha256)
        billing = None
        try:
            billing_identity = None
            if args.synthetic_billing:
                from PrivateSubscriptionBilling import BillingSession
                billing_identity = WorkerIdentity.inspect(args.billing_worker, args.expected_source, args.billing_worker_sha256)
                billing = BillingSession.register(ledger)
            session = SyntheticUiSession(identity, args.output_directory, args.fixture_directory, qt_root=args.qt_root,
                import_workflow=args.synthetic_ui_import_policy, import_control=args.synthetic_ui_import_control,
                dns_workflow=args.synthetic_ui_dns, dns_control=args.synthetic_ui_dns_control)
            result = Supervisor(ledger, identity, billing, billing_worker_identity=billing_identity,
                billing_response_contract=args.billing_response_contract).run_ui(session, byte_limit=args.byte_limit)
        finally:
            if billing is not None:
                billing.close()
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["settled"] and result["outcome"] in {"QtUiSucceeded", "QtUiQuotaStopped"} else 2


if __name__ == "__main__":
    # Preserve strict capability class identity when invoked as a real script.
    sys.modules.setdefault("PrivateSubscriptionUi", sys.modules[__name__])
    try:
        raise SystemExit(main())
    except (BudgetError, OSError, ValueError):
        print('{"error":"PrivateUiAcceptanceRejected","liveReady":false,"networkAdmissionGranted":false}', file=sys.stderr)
        raise SystemExit(64)
