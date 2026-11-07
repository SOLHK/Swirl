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


class SyntheticUiSession:
    """One exact parent-owned fixed TLS/SOCKS fixture, never an endpoint API."""

    def __init__(self, identity, output, fixture_directory, *, qt_root=None):
        if type(identity) is not UiIdentity or getattr(identity, "_issuer", None) is not _IDENTITY_ISSUER:
            raise BudgetError("PrivateUiIdentityRequired")
        self._issuer, self.identity = _UI_ISSUER, identity
        self.root, self.fixture_directory = _local_path(Path(output)), _local_path(Path(fixture_directory))
        self.qt_root = None if qt_root is None else _local_path(Path(qt_root))
        self.fixture = self.storage = self.native_receipt = None
        self.manifest = self.proof = self.native_handle = self.child_environment = None
        self.ui_result = self.native_stop = None
        self.quota_proof = None
        self.closed = False

    def check(self, ledger, identity):
        if (self._issuer is not _UI_ISSUER or self.identity is not identity or self.fixture is not None
                or ledger.data["schema"] != 3 or self.root.exists()
                or any(path.is_symlink() for path in (self.root, *self.root.parents))):
            raise BudgetError("NewSyntheticUiSessionRequired")
        if os.name != "nt":
            raise BudgetError("NativeWindowsUiAcceptanceRequired")

    def fingerprint(self, plan):
        from RunControlledNodeAcceptance import FIXTURE_CERT_SHA256, FIXTURE_KEY_SHA256
        # No ephemeral port or nonce can turn the same failed configuration into
        # a new attempt. Plan/source changes are explicit reviewable differences.
        return digest({"workload": UI_WORKLOAD, "fixture_schema": 2, "node": 1,
                       "source": self.identity.metadata["source_sha"], "exe": self.identity.sha256,
                       "core": self.identity.core_sha256, "plan": plan,
                       "ca": FIXTURE_CERT_SHA256, "key": FIXTURE_KEY_SHA256})

    def open(self, nonce):
        from RunControlledNodeAcceptance import (LoopbackFixture, FIXTURE_CERT_SHA256,
            FIXTURE_KEY_SHA256, local_file, environment, write_json)
        certificate = local_file(self.fixture_directory / "localhost-cert.pem")
        key = local_file(self.fixture_directory / "localhost-key.pem")
        if (hashlib.sha256(certificate.read_bytes()).hexdigest() != FIXTURE_CERT_SHA256
                or hashlib.sha256(key.read_bytes()).hexdigest() != FIXTURE_KEY_SHA256):
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
                                     "socksPort": self.fixture.socks, "caSha256": FIXTURE_CERT_SHA256}}
        self.proof = self.fixture.bind_session(self.manifest)
        with (self.root / "fixture-ca.pem").open("xb") as destination:
            destination.write(certificate.read_bytes())
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
                or result.get("uiSubscriptionImportExercised") is not False
                or result.get("uiPolicySelectionExercised") is not False
                or self.fixture.proofs != 1):
            raise BudgetError("ActualUiReceiptRejected")
        self.ui_result = {key: value for key, value in result.items() if key != "nonce"}
        guard = reply["guard"]
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
        return "QtUiSucceeded"

    def report(self):
        return {"scope": "owned-fixed-synthetic-qt-ui", "coreSha256": self.identity.core_sha256,
                "qtVersion": self.identity.qt_version, "ui": self.ui_result, "nativeWatchdog": self.native_stop,
                "guardedSessionProof": self.quota_proof,
                "ownershipProofs": 0 if self.fixture is None else self.fixture.proofs,
                "socksConnections": 0 if self.fixture is None else self.fixture.socks_connections,
                "forwarded": 0 if self.fixture is None else self.fixture.forwarded,
                "rejected": 0 if self.fixture is None else self.fixture.rejected,
                "tasksReleased": self.closed, "uiSubscriptionImportExercised": False,
                "rawCounterScope": "shared Rust TCP below TLS/protocol; excludes Qt-only local control proof",
                "wireMeteringProven": False}

    def close(self):
        if self.closed:
            return
        failures = []
        for resource in (self.fixture, self.native_receipt, self.storage):
            if resource is not None:
                try:
                    resource.close()
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
    args = parser.parse_args(argv)
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
        session = SyntheticUiSession(identity, args.output_directory, args.fixture_directory, qt_root=args.qt_root)
        result = Supervisor(ledger, identity).run_ui(session, byte_limit=args.byte_limit)
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
