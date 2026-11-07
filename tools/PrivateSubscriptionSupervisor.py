"""Durable synthetic acceptance coordinator; real subscriptions stay refused.

Only a freshly-created, parent-owned loopback fixture is an execution target.
The same Ledger owns reservations, source/config identity, actual child exit
receipts and crash holds. No URL, subscription, arbitrary endpoint or live
permission flag is accepted. Socket counters are not called wire/billing data.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import ssl
import stat
import sys
import tempfile
import threading
import time

from PrivateSubscriptionBudget import (BudgetError, Ledger, SYNTHETIC_DOMAIN, TASK, FIRST_ROUND,
    TCP_RECEIVE_RESERVATION, SUPERVISED_WORKLOADS, tcp_plan, validate_guard_receipt)
from PrivateSubscriptionProcess import OwnedProcess

MAX_LINE = 16384
WORKER_ROLE = "swirl_private_worker"
GUARD_MODE = "mandatory_before_grant"
_IDENTITY_ISSUER = object()
_EXECUTION_ISSUER = object()
OUTCOMES = {"quota_stopped": "QuotaStopped", "deadline_expired": "DeadlineExpired",
            "cancelled": "Cancelled", "fixture_rejected": "FixtureRejected",
            "fixture_closed": "FixtureClosed", "core_probe_succeeded": "CoreProbeSucceeded",
            "core_probe_failed": "CoreProbeFailed", "worker_protocol_error": "WorkerProtocolError",
            "worker_io_error": "WorkerIoError", "billing_snapshot_succeeded": "BillingSnapshotSucceeded",
            "billing_snapshot_failed": "BillingSnapshotFailed", "qt_ui_finished": "QtUiFinished"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BudgetError("DuplicateWorkerField")
        result[key] = value
    return result


def _decode(line):
    if not line or len(line) > MAX_LINE or not line.endswith(b"\n"):
        raise BudgetError("WorkerFrameRejected")
    try:
        value = json.loads(line.decode("utf-8"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError):
        raise BudgetError("WorkerFrameRejected") from None
    if not isinstance(value, dict):
        raise BudgetError("WorkerFrameRejected")
    return value


def _environment():
    # Credentials/proxy overrides are neither needed nor inherited by this QA
    # binary. Platform loader/temp variables remain available on Windows.
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
            "USERPROFILE", "LOCALAPPDATA", "APPDATA", "HOME", "LANG", "LC_ALL"}
    return {key: value for key, value in os.environ.items() if key.upper() in keep}


class _Frames:
    def __init__(self, process):
        self.process = process
        self.frames = queue.Queue(maxsize=32)
        self.error = None
        self.stderr_bytes = 0
        self.readers = [threading.Thread(target=self._stdout, daemon=True),
                        threading.Thread(target=self._stderr, daemon=True)]
        for reader in self.readers:
            reader.start()

    def _stdout(self):
        try:
            while True:
                line = self.process.stdout.readline(MAX_LINE + 1)
                if not line:
                    self.frames.put_nowait(None)
                    return
                self.frames.put_nowait(_decode(line))
        except (BudgetError, OSError, ValueError, queue.Full):
            self.error = "WorkerOutputRejected"

    def _stderr(self):
        try:
            while True:
                data = self.process.stderr.read(4096)
                if not data:
                    return
                self.stderr_bytes += len(data)
                if self.stderr_bytes > 65536:
                    self.error = "WorkerDiagnosticsLimit"
                    return
        except (OSError, ValueError):
            return

    def receive(self, deadline):
        while True:
            if self.error:
                raise BudgetError(self.error)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BudgetError("ParentDeadlineExpired")
            try:
                value = self.frames.get(timeout=min(0.025, remaining))
            except queue.Empty:
                continue
            if value is None:
                raise BudgetError("WorkerExitedWithoutReceipt")
            return value

    def send(self, value):
        data = canonical(value) + b"\n"
        if len(data) > MAX_LINE:
            raise BudgetError("WorkerInputLimit")
        try:
            offset = 0
            while offset < len(data):
                written = self.process.stdin.write(data[offset:])
                if not written:
                    raise BudgetError("WorkerInputClosed")
                offset += written
            self.process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            raise BudgetError("WorkerInputClosed") from None

    def finish(self):
        """OS exit alone does not validate buffered/extra protocol output."""
        deadline = time.monotonic() + 1
        for reader in self.readers:
            reader.join(timeout=max(0, deadline - time.monotonic()))
        if any(reader.is_alive() for reader in self.readers):
            raise BudgetError("WorkerReaderExitUnconfirmed")
        if self.error:
            raise BudgetError(self.error)
        eof = False
        while True:
            try:
                value = self.frames.get_nowait()
            except queue.Empty:
                break
            if value is not None or eof:
                raise BudgetError("UnexpectedWorkerTail")
            eof = True
        if not eof:
            raise BudgetError("WorkerEofUnconfirmed")


class WorkerIdentity:
    """Identity admitted by a trusted QA build digest before any execution.

    The expected digest must come from the designated QA build receipt. Merely
    hashing an arbitrary --worker path cannot establish a safe metadata entry.
    """
    __slots__ = ("_path", "_metadata", "_sha256", "_issuer")

    def __init__(self, path, metadata, sha256, *, _issuer=None):
        if _issuer is not _IDENTITY_ISSUER:
            raise BudgetError("WorkerIdentityFactoryRequired")
        self._path, self._metadata, self._sha256 = path, metadata.copy(), sha256
        self._issuer = _issuer

    @property
    def path(self):
        return self._path

    @property
    def metadata(self):
        return self._metadata.copy()

    @property
    def sha256(self):
        return self._sha256

    @staticmethod
    def _hash(path):
        try:
            if not path.is_absolute():
                raise BudgetError("WorkerExecutableRejected")
            if os.name == "nt":
                # Reject UNC/ADS/remote drives before any path lookup can
                # follow them. Check ancestors before their descendants.
                if not re.fullmatch(r"[A-Za-z]:", path.drive) or ":" in str(path)[2:]:
                    raise BudgetError("WorkerExecutableRejected")
                import ctypes as c
                from ctypes import wintypes as w
                kernel = c.WinDLL("kernel32", use_last_error=True)
                kernel.GetDriveTypeW.argtypes, kernel.GetDriveTypeW.restype = [w.LPCWSTR], w.UINT
                if kernel.GetDriveTypeW(path.anchor) != 3:
                    raise BudgetError("WorkerExecutableRejected")
            for component in reversed([path, *path.parents]):
                info = component.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise BudgetError("WorkerExecutableRejected")
            if not stat.S_ISREG(info.st_mode):
                raise BudgetError("WorkerExecutableRejected")
            with path.open("rb") as source:
                return hashlib.file_digest(source, "sha256").hexdigest()
        except OSError:
            raise BudgetError("WorkerExecutableRejected") from None

    @classmethod
    def inspect(cls, path, expected_source, expected_worker_sha256=None):
        if not isinstance(expected_source, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_source):
            raise BudgetError("ExpectedSourceRequired")
        if not isinstance(expected_worker_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_worker_sha256):
            raise BudgetError("ExpectedWorkerSha256Required")
        expected_worker_sha256 = expected_worker_sha256.lower()
        path = Path(path)
        checksum = cls._hash(path)
        if not hmac.compare_digest(checksum, expected_worker_sha256):
            raise BudgetError("WorkerDigestMismatch")
        # Only the externally pinned QA executable may use this read-only,
        # pre-reservation entry. An unknown program's --build-info cannot prove
        # its own startup is network-free. OS containment still applies here.
        with OwnedProcess([str(path), "--build-info"], deadline=time.monotonic() + 2,
                          environment=_environment()) as child:
            frames = _Frames(child)
            metadata = frames.receive(child.deadline)
            proof = child.wait(timeout=max(0.001, child.deadline - time.monotonic()))
            if proof.record()["exitCode"] != 0 or frames.error:
                raise BudgetError("WorkerIdentityQueryFailed")
            frames.finish()
        if (set(metadata) != {"source_sha", "role", "private_worker_schema", "guard_mode", "live",
                              "build_id", "target", "package_version", "abi_version"}
                or type(metadata.get("abi_version")) is not int or metadata["abi_version"] != 1
                or metadata.get("source_sha") != expected_source or metadata.get("role") != WORKER_ROLE
                or type(metadata.get("private_worker_schema")) is not int or metadata["private_worker_schema"] != 1
                or metadata.get("guard_mode") != GUARD_MODE or metadata.get("live") is not False
                or not isinstance(metadata.get("build_id"), str)
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", metadata["build_id"])
                or not isinstance(metadata.get("target"), str) or not re.fullmatch(r"[a-z0-9_-]{1,100}", metadata["target"])
                or not isinstance(metadata.get("package_version"), str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", metadata["package_version"])):
            raise BudgetError("WorkerIdentityMismatch")
        if cls._hash(path) != checksum:
            raise BudgetError("WorkerExecutableChanged")
        return cls(path, metadata, expected_worker_sha256, _issuer=_IDENTITY_ISSUER)

    def recheck(self):
        if self._issuer is not _IDENTITY_ISSUER:
            raise BudgetError("WorkerIdentityFactoryRequired")
        if self._hash(self.path) != self.sha256:
            raise BudgetError("WorkerExecutableChanged")


class _OwnedFixture:
    """Never accepts an endpoint argument and never resolves/forwards a host."""
    def __init__(self, root, workload, byte_limit, challenge, nonce, billing_query=None):
        self.workload, self.byte_limit = workload, byte_limit
        self.challenge, self.nonce = challenge, nonce
        self.billing_query = billing_query
        if workload == "billing_snapshot":
            from PrivateSubscriptionBilling import _BillingQuery, _QUERY_ISSUER
            if (not isinstance(billing_query, _BillingQuery) or billing_query._seal is not _QUERY_ISSUER
                    or billing_query.nonce != nonce):
                raise BudgetError("OwnedBillingQueryRequired")
        elif billing_query is not None:
            raise BudgetError("UnexpectedBillingQuery")
        self.key = bytes.fromhex(challenge)
        self.stop = threading.Event()
        self.authenticated = threading.Event()
        self.accepted = 0
        self.authenticated_connections = 0
        self.received = 0
        self.sent = 0
        self.protocol_errors = 0
        self.protocol_failure = None
        self.http_status = None
        self.active = []
        self.lock = threading.Lock()
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name == "nt":
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(3)
        self.server.settimeout(0.1)
        self.port = self.server.getsockname()[1]
        try:
            self.tls, self.context = self._tls(root) if workload in {"core_probe", "billing_snapshot"} else (None, None)
            if billing_query is not None:
                self.context.set_alpn_protocols(["http/1.1"])
                self.tls = billing_query.configure_tls(self.tls)
            self.thread = threading.Thread(target=self._serve, name="Swirl owned synthetic fixture", daemon=True)
            self.thread.start()
        except BaseException:
            self.server.close()
            raise

    def _tls(self, root):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        now = datetime.now(timezone.utc)
        issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Swirl temporary synthetic CA")])
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca = (x509.CertificateBuilder().subject_name(issuer).issuer_name(issuer).public_key(ca_key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
              .not_valid_after(now + timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
              .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), True)
              .sign(ca_key, hashes.SHA256()))
        key = ec.generate_private_key(ec.SECP256R1())
        name = "swirl-qa.fixture.invalid"
        certificate_name = "wrong-qa.fixture.invalid" if self.billing_query is not None and self.billing_query.fault == "wrong_sni" else name
        expired_certificate = self.billing_query is not None and self.billing_query.fault == "expired_certificate"
        cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, certificate_name)]))
                .issuer_name(issuer).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=2) if expired_certificate else now - timedelta(minutes=1))
                .not_valid_after(now - timedelta(days=1) if expired_certificate else now + timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(certificate_name)]), False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
                .sign(ca_key, hashes.SHA256()))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        with tempfile.TemporaryDirectory(prefix="synthetic-tls-", dir=root) as directory:
            cert_path, key_path = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            for path, data in ((cert_path, cert.public_bytes(serialization.Encoding.PEM)),
                               (key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                           serialization.NoEncryption()))):
                with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                    stream.write(data)
            context.load_cert_chain(str(cert_path), str(key_path))
        return {"server_name": name, "ca_der_base64": base64.b64encode(ca.public_bytes(serialization.Encoding.DER)).decode("ascii")}, context

    def _receive(self, conn, count):
        while not self.stop.is_set():
            try:
                data = conn.recv(count)
                self.received += len(data)
                return data
            except socket.timeout:
                continue
        return b""

    def _line(self, conn):
        result = bytearray()
        while len(result) <= 1024:
            data = self._receive(conn, 1)
            if not data:
                break
            result.extend(data)
            if data == b"\n":
                return bytes(result)
        raise BudgetError("FixtureProtocolRejected")

    def _send(self, conn, data):
        conn.sendall(data)
        self.sent += len(data)

    def _authenticate(self, conn):
        line = self._line(conn)
        if not re.fullmatch(rb"SWIRL-SYNTHETIC-V1 [0-9a-f]{64}\n", line):
            raise BudgetError("FixtureChallengeRejected")
        proof = hmac.new(self.key, line, hashlib.sha256).hexdigest().encode("ascii")
        self._send(conn, b"SWIRL-SYNTHETIC-ACK " + proof + b"\n")
        self.authenticated_connections += 1
        self.authenticated.set()

    def _headers(self, conn):
        data = bytearray()
        while len(data) <= 8192:
            data.extend(self._line(conn))
            if data.endswith(b"\r\n\r\n"):
                return bytes(data)
        raise BudgetError("FixtureProtocolRejected")

    def _core_probe(self, conn):
        wrapped = self.context.wrap_socket(conn, server_side=True, do_handshake_on_connect=False)
        with self.lock:
            self.active.append(wrapped)
        try:
            while not self.stop.is_set():
                try:
                    wrapped.do_handshake()
                    break
                except socket.timeout:
                    continue
            connect = self._headers(wrapped)
            auth = base64.b64encode(("swirl-private-qa:" + self.challenge).encode("ascii"))
            fields = {}
            for line in connect.split(b"\r\n")[1:]:
                if not line:
                    continue
                key, separator, value = line.partition(b":")
                key = key.lower()
                if not separator or key in fields:
                    raise BudgetError("FixtureProxyAuthenticationRejected")
                fields[key] = value.strip()
            scheme, _, encoded = fields.get(b"proxy-authorization", b"").partition(b" ")
            if (not connect.startswith(b"CONNECT qa-origin.fixture.invalid:80 HTTP/1.1\r\n")
                    or scheme.lower() != b"basic" or not hmac.compare_digest(encoded, auth)):
                raise BudgetError("FixtureProxyAuthenticationRejected")
            self._send(wrapped, b"HTTP/1.1 200 Connection Established\r\n\r\n")
            request = self._headers(wrapped)
            expected = ("HEAD /swirl-private-fixture/" + self.nonce + " HTTP/1.1\r\n").encode("ascii")
            if not request.startswith(expected) or b"host: qa-origin.fixture.invalid:80\r\n" not in request.lower():
                raise BudgetError("FixtureRequestRejected")
            self._send(wrapped, b"HTTP/1.1 204 No Content\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            self.http_status = 204
        finally:
            wrapped.close()

    def _serve(self):
        try:
            count = 2 if self.workload in {"core_probe", "billing_snapshot"} else 1
            for ordinal in range(count):
                while not self.stop.is_set():
                    try:
                        conn, peer = self.server.accept()
                        break
                    except socket.timeout:
                        continue
                else:
                    return
                if peer[0] != "127.0.0.1":
                    conn.close()
                    raise BudgetError("FixturePeerRejected")
                self.accepted += 1
                conn.settimeout(0.1)
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
                with self.lock:
                    self.active.append(conn)
                with conn:
                    if ordinal:
                        if self.billing_query is not None:
                            self.billing_query.serve(self, conn)
                        else:
                            self._core_probe(conn)
                    else:
                        self._authenticate(conn)
                        if self.workload in {"upload_until_stop", "stall_runtime_after_connect"}:
                            while self._receive(conn, 16384):
                                if self.received > self.byte_limit + TCP_RECEIVE_RESERVATION:
                                    raise BudgetError("FixtureByteLimit")
                        elif self.workload == "download_until_stop":
                            limit = self.byte_limit + TCP_RECEIVE_RESERVATION
                            while not self.stop.is_set() and self.sent < limit:
                                self._send(conn, b"s" * min(16384, limit - self.sent))
                                self.stop.wait(0.002)
        except (OSError, ssl.SSLError):
            # A stopped quota/parent closes real sockets; this is expected.
            return
        except BudgetError as error:
            self.protocol_errors += 1
            self.protocol_failure = str(error)

    def report(self):
        result = {"acceptedConnections": self.accepted, "authenticatedConnections": self.authenticated_connections,
                "fixtureSentBytes": self.sent, "fixtureReceivedBytes": self.received,
                "protocolErrors": self.protocol_errors, "httpStatus": self.http_status,
                "protocolFailure": self.protocol_failure,
                "scope": "owned-loopback-sockets; fixture application counts are not wire billing"}
        if self.billing_query is not None:
            result.update(billingRequestReceived=self.billing_query.request_received,
                          billingRequestAuthenticated=self.billing_query.request_authenticated)
        return result

    def close(self):
        self.stop.set()
        self.server.close()
        with self.lock:
            for conn in self.active:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                conn.close()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            raise BudgetError("FixtureExitUnconfirmed")


def _check_envelope(value, envelope, identity, op):
    fields = {"schema", "op", "ok", "reservation_id", "nonce", "plan_digest", "identity",
              "source_sha", "build_id", "guard_mode", "guard"}
    if op == "running":
        fields.add("fixture_verified")
    if op == "finished":
        fields |= {"fixture_verified", "outcome"}
        if identity.metadata["role"] == "swirl_private_qt_ui":
            fields |= {"scope", "raw_tcp_quota_exercised"}
    allowed = fields | ({"metrics", "billing"} if op == "finished" else set())
    if (not isinstance(value, dict) or not fields <= set(value) <= allowed
            or value.get("ok") is not True or value.get("guard_mode") != GUARD_MODE):
        raise BudgetError("WorkerReceiptSchemaMismatch")
    for key in ("schema", "reservation_id", "nonce", "plan_digest"):
        if type(value.get(key)) is not type(envelope[key]) or value[key] != envelope[key]:
            raise BudgetError("WorkerReceiptBindingMismatch")
    if value.get("op") != op or value.get("identity") != identity.metadata:
        raise BudgetError("WorkerReceiptIdentityMismatch")
    if op == "finished" and identity.metadata["role"] == "swirl_private_qt_ui":
        if (value.get("scope") != "synthetic-qt-ui-raw-tcp-v1"
                or type(value.get("raw_tcp_quota_exercised")) is not bool):
            raise BudgetError("PrivateUiRawScopeRequired")
    if value.get("source_sha", identity.metadata["source_sha"]) != identity.metadata["source_sha"] or value.get("build_id", identity.metadata["build_id"]) != identity.metadata["build_id"]:
        raise BudgetError("WorkerReceiptIdentityMismatch")


class _ExecutionEvidence:
    """Current-process evidence from the shared executor, never deserialized."""
    def __init__(self, issuer, record, *, exit_proof, guard, receipt, received, query, complete, cleanup):
        if issuer is not _EXECUTION_ISSUER:
            raise BudgetError("ControlledExecutionEvidenceRequired")
        self._issuer = issuer
        self.record = record
        self.exit_proof, self.guard = exit_proof, guard
        self._receipt = None if receipt is None else canonical(receipt)
        self.received, self.query = received, query
        self.complete, self.cleanup = complete, cleanup

    def billing_snapshot(self, query):
        if (self._issuer is not _EXECUTION_ISSUER or not self.complete or not self.cleanup
                or self.query is not query or self.record["workload"] != "billing_snapshot"
                or self.record["outcome"] != "BillingSnapshotSucceeded" or self._receipt is None
                or self.exit_proof is None):
            raise BudgetError("ControlledBillingExchangeRequired")
        return json.loads(self._receipt)["billing"], self.received


class Supervisor:
    def __init__(self, ledger, identity, billing=None, *, billing_response_contract="synthetic_qa_v1"):
        from PrivateSubscriptionBilling import QA_RESPONSE_CONTRACT, RESPONSE_CONTRACTS
        ledger.require_synthetic()
        if not isinstance(identity, WorkerIdentity) or getattr(identity, "_issuer", None) is not _IDENTITY_ISSUER:
            raise BudgetError("WorkerIdentityRequired")
        if ledger.data["schema"] == 4:
            ledger._require_billing_session(billing)
        elif billing is not None:
            raise BudgetError("SyntheticBillingSessionRequired")
        if (not isinstance(billing_response_contract, str) or billing_response_contract not in RESPONSE_CONTRACTS
                or (billing is None and billing_response_contract != QA_RESPONSE_CONTRACT)):
            raise BudgetError("BillingResponseContractRejected")
        self.ledger, self.identity, self.billing = ledger, identity, billing
        self.billing_response_contract = billing_response_contract

    def _identity_fields(self):
        return {"source_sha": self.identity.metadata["source_sha"], "worker_sha256": self.identity.sha256,
                "build_id": self.identity.metadata["build_id"]}

    def _execute_reserved(self, ticket, workload, plan, nonce, fingerprint, *, cancel_event=None, billing_query=None, ui_session=None):
        """One real reserve/grant/OS-exit boundary shared by node and billing I/O.

        This method never refunds. A typed result carries the actual ExitProof
        only after bounded process/reader/fixture cleanup. Ledger settlement is
        a separate caller action after all these checks have completed.
        """
        challenge = secrets.token_hex(32)
        fixture = child = frames = None
        child_closed = fixture_closed = frames_finished = False
        ui_frames_finish_attempted = False
        final_guard = exit_proof = metrics = final_receipt = received = None
        observed_running = complete = False
        outcome = "CoordinatorFailure"
        started = time.monotonic()
        elapsed = 0
        timeout_ms = plan["timeoutMs"]
        # Diagnostic observations only. All times share the existing deadline
        # epoch; no event changes admission, timing, persistence or cleanup.
        _diagnostic_phases = {key: None for key in (
            "clock_started", "spawn_returned", "spawn_state_persisted", "grant_send_started", "grant_sent",
            "ready_received", "ready_validated", "guard_ready_state_persisted", "running_state_persisted",
            "start_send_started", "start_sent", "first_running_received", "active_state_persisted",
            "cancel_send_started", "cancel_sent", "finished_received", "os_exit_proved", "readers_finished",
            "child_closed", "fixture_closed", "cleanup_checked")}
        _diagnostic_last_send = None

        def _diagnostic_mark(name, observed=None):
            if _diagnostic_phases["clock_started"] is not None:
                _diagnostic_phases[name] = int(((time.monotonic() if observed is None else observed) - started) * 1000)

        try:
            if ui_session is None:
                fixture = _OwnedFixture(self.ledger.root, workload, plan["byteLimit"], challenge, nonce, billing_query)
            else:
                from PrivateSubscriptionUi import SyntheticUiSession, UiIdentity, UI_WORKLOAD, _UI_ISSUER
                if (type(ui_session) is not SyntheticUiSession or ui_session._issuer is not _UI_ISSUER
                        or type(self.identity) is not UiIdentity or ui_session.identity is not self.identity
                        or workload != UI_WORKLOAD or billing_query is not None or self.billing is not None):
                    raise BudgetError("OwnedSyntheticUiSessionRequired")
                fixture = ui_session
                fixture.open(nonce)
            grant = {"task_id": TASK, "ledger_id": self.ledger.data["ledgerId"], "sequence": int(ticket),
                     "source_sha": self.identity.metadata["source_sha"], "build_id": self.identity.metadata["build_id"],
                     "role": "synthetic_loopback", "byte_limit": plan["byteLimit"], "connection_limit": plan["connectionLimit"],
                     "receive_reservation": plan["receiveReservation"], "timeout_ms": timeout_ms,
                     "workload": workload, "config_fingerprint": fingerprint}
            if ui_session is None:
                grant.update(endpoint={"host": "127.0.0.1", "port": fixture.port}, challenge=challenge, tls=fixture.tls)
            else:
                grant.update(ui_session.grant_fields())
            if billing_query is not None:
                grant["billing"] = billing_query.grant()
            envelope = {"schema": 1, "reservation_id": ticket, "nonce": nonce, "plan_digest": digest(grant)}
            self.ledger.bind_supervised_grant(ticket, envelope["plan_digest"])
            self.identity.recheck()
            started = time.monotonic()
            deadline = started + timeout_ms / 1000
            _diagnostic_phases["clock_started"] = 0
            child = (OwnedProcess([str(self.identity.path), "--internal-private-acceptance-worker"],
                                  deadline=deadline, environment=_environment())
                     if ui_session is None else ui_session.spawn(deadline))
            _diagnostic_mark("spawn_returned")
            self.ledger.advance_supervised(ticket, "spawned", process=child)
            _diagnostic_mark("spawn_state_persisted")
            frames = _Frames(child)
            _diagnostic_last_send = "grant"
            _diagnostic_mark("grant_send_started")
            frames.send({**envelope, "op": "grant", "grant": grant})
            _diagnostic_mark("grant_sent")
            ready = frames.receive(deadline)
            _diagnostic_mark("ready_received")
            _check_envelope(ready, envelope, self.identity, "ready")
            validate_guard_receipt(ready.get("guard"), plan, initial=True)
            _diagnostic_mark("ready_validated")
            previous_guard = ready["guard"]
            self.ledger.advance_supervised(ticket, "guard_ready")
            _diagnostic_mark("guard_ready_state_persisted")
            self.ledger.advance_supervised(ticket, "running")
            _diagnostic_mark("running_state_persisted")
            _diagnostic_last_send = "start"
            _diagnostic_mark("start_send_started")
            frames.send({**envelope, "op": "start"})
            if ui_session is not None:
                # The original binary fixture proof and EOF follow the one
                # START line; Qt does not prefetch across that line boundary.
                ui_session.send_fixture_proof(child)
            _diagnostic_mark("start_sent")
            cancelled = False
            while True:
                if cancel_event is not None and cancel_event.is_set() and not cancelled:
                    if ui_session is not None:
                        exit_proof = child.terminate_and_wait()
                        _diagnostic_mark("os_exit_proved")
                        raise BudgetError("UiCancelledWithoutFinalReceipt")
                    _diagnostic_last_send = "cancel"
                    _diagnostic_mark("cancel_send_started")
                    frames.send({**envelope, "op": "cancel"})
                    _diagnostic_mark("cancel_sent")
                    cancelled = True
                try:
                    reply = frames.receive(min(deadline, time.monotonic() + 0.025))
                except BudgetError as error:
                    if str(error) == "ParentDeadlineExpired" and time.monotonic() < deadline:
                        continue
                    raise
                received_at = time.monotonic()
                operation = reply.get("op")
                if operation not in {"running", "snapshot", "finished"}:
                    raise BudgetError("UnexpectedWorkerReceipt")
                _check_envelope(reply, envelope, self.identity, operation)
                validate_guard_receipt(reply.get("guard"), plan, terminal=operation == "finished")
                if any(reply["guard"][key] < previous_guard[key] for key in ("upload", "download", "connection_attempts")):
                    raise BudgetError("WorkerCounterRegression")
                previous_guard = reply["guard"]
                if operation == "running":
                    if observed_running or reply.get("fixture_verified") is not True:
                        raise BudgetError("InvalidRunningReceipt")
                    _diagnostic_mark("first_running_received", received_at)
                    observed_running = True
                    self.ledger.advance_supervised(ticket, "active")
                    _diagnostic_mark("active_state_persisted")
                    continue
                if operation == "snapshot":
                    raise BudgetError("UnrequestedSnapshotReceipt")
                _diagnostic_mark("finished_received", received_at)
                if reply.get("outcome") not in OUTCOMES or type(reply.get("fixture_verified")) is not bool:
                    raise BudgetError("InvalidWorkerOutcome")
                outcome = OUTCOMES[reply["outcome"]]
                final_guard, final_receipt, received = reply["guard"], reply, received_at
                if outcome == "CoreProbeSucceeded":
                    metrics = reply.get("metrics")
                    if (workload != "core_probe" or not isinstance(metrics, dict)
                            or set(metrics) != {"http_status", "outbound_connect_ms", "response_headers_ms"}
                            or any(type(value) is not int or value < 0 for value in metrics.values())
                            or metrics["http_status"] != 204
                            or not metrics["outbound_connect_ms"] <= metrics["response_headers_ms"] <= timeout_ms):
                        raise BudgetError("InvalidProbeMetrics")
                elif "metrics" in reply:
                    raise BudgetError("UnexpectedProbeMetrics")
                if outcome == "BillingSnapshotSucceeded":
                    # Only the Rust success route can produce this typed
                    # exchange; the modeled response is never taken directly.
                    if billing_query is None or workload != "billing_snapshot":
                        raise BudgetError("UnexpectedBillingReceipt")
                    billing_query.validate_payload(reply.get("billing"))
                elif "billing" in reply:
                    raise BudgetError("UnexpectedBillingReceipt")
                exit_proof = child.wait(timeout=max(0.001, deadline - time.monotonic()))
                _diagnostic_mark("os_exit_proved")
                if not reply["fixture_verified"] or not observed_running:
                    raise BudgetError("IncompleteSyntheticEvidence")
                if ui_session is not None:
                    # The native mapping is consumed only after every child
                    # reader has retired and the complete output is valid.
                    # Never retry a failed tail check into a passing result.
                    ui_frames_finish_attempted = True
                    frames.finish()
                    frames_finished = True
                    _diagnostic_mark("readers_finished")
                    outcome = ui_session.validate_finished(reply, exit_proof, child)
                elif (exit_proof.record()["exitCode"] != 0 or fixture.authenticated_connections != 1 or fixture.protocol_errors):
                    raise BudgetError("IncompleteSyntheticEvidence")
                elif workload == "billing_snapshot":
                    if outcome != "BillingSnapshotSucceeded" or fixture.http_status != 200:
                        raise BudgetError("BillingSnapshotFailed")
                elif (outcome not in {"QuotaStopped", "Cancelled", "CoreProbeSucceeded", "DeadlineExpired"}
                        or (workload == "core_probe" and (outcome != "CoreProbeSucceeded" or fixture.http_status != 204))):
                    raise BudgetError("IncompleteSyntheticEvidence")
                complete = True
                break
        except BudgetError as error:
            outcome = str(error)
        except Exception:
            outcome = "CoordinatorFailure"
        finally:
            if child is not None:
                try:
                    if exit_proof is None:
                        exit_proof = child.terminate_and_wait()
                        _diagnostic_mark("os_exit_proved")
                except BudgetError:
                    outcome = "ProcessExitUnconfirmed"
                if frames is not None and not frames_finished and not ui_frames_finish_attempted:
                    try:
                        frames.finish()
                        frames_finished = True
                        _diagnostic_mark("readers_finished")
                    except BudgetError as error:
                        if complete or outcome == "CoordinatorFailure":
                            outcome = str(error)
                if ui_session is not None and exit_proof is not None and frames_finished:
                    try:
                        ui_session.observe_exit(child)
                    except (BudgetError, ValueError, OSError):
                        complete = False
                        outcome = "NativeWatchdogExitUnconfirmed"
                try:
                    child.close()
                    child_closed = True
                    _diagnostic_mark("child_closed")
                except BudgetError:
                    outcome = "ProcessExitUnconfirmed"
                elapsed = int((time.monotonic() - started) * 1000)
            if fixture is not None:
                try:
                    fixture.close()
                    fixture_closed = True
                    _diagnostic_mark("fixture_closed")
                except BudgetError:
                    outcome = "FixtureExitUnconfirmed"
        cleanup = exit_proof is not None and frames_finished and child_closed and fixture_closed
        complete = complete and cleanup
        _diagnostic_mark("cleanup_checked")
        record = {"schema": 1, "scope": SYNTHETIC_DOMAIN, **self._identity_fields(),
                  "reservation_id": ticket, "config_fingerprint": fingerprint, "workload": workload,
                  "plan": plan, "outcome": outcome, "settled": False, "guard": final_guard,
                  "metrics": metrics, "observedRunning": observed_running,
                  "localMeasurement": "unknown-full-reservation-held", "cleanupConfirmed": cleanup,
                  "exit": None if exit_proof is None else exit_proof.record(), "parentElapsedMs": elapsed,
                  "fixture": None if fixture is None else fixture.report(),
                  "diagnostics": {"clock": "existing-parent-deadline-monotonic-ms", "phaseMs": _diagnostic_phases,
                      "lastSendOperation": _diagnostic_last_send,
                      "frames": None if frames is None else {"stderrBytes": frames.stderr_bytes,
                          "pendingFrames": frames.frames.qsize(), "liveReaders": sum(reader.is_alive() for reader in frames.readers)}},
                  "providerRequests": 0, "realNodeRequests": 0, "liveReady": False}
        return _ExecutionEvidence(_EXECUTION_ISSUER, record, exit_proof=exit_proof, guard=final_guard,
                                  receipt=final_receipt, received=received, query=billing_query,
                                  complete=complete, cleanup=cleanup)

    def run(self, workload, *, node=1, byte_limit=65536, timeout_ms=2000, cancel_event=None):
        if self.identity.metadata["role"] != WORKER_ROLE:
            raise BudgetError("SyntheticUiSessionRequired")
        if workload not in SUPERVISED_WORKLOADS:
            raise BudgetError("SyntheticWorkloadRequired")
        if self.billing is not None:
            return self._run_with_billing(workload, node=node, byte_limit=byte_limit,
                                          timeout_ms=timeout_ms, cancel_event=cancel_event)
        connections = 2 if workload == "core_probe" else 1
        plan = tcp_plan(byte_limit, connections, timeout_ms)
        self.identity.recheck()
        nonce = secrets.token_hex(32)
        fingerprint = digest({"protocol": 1, "node": node, "workload": workload, "configuration_version": 1})
        ticket = self.ledger.reserve_supervised(node, byte_limit, connections, timeout_ms,
            config_fingerprint=fingerprint, **self._identity_fields(), nonce=nonce, workload=workload)
        evidence = self._execute_reserved(ticket, workload, plan, nonce, fingerprint, cancel_event=cancel_event)
        if evidence.complete:
            self.ledger.settle_synthetic(ticket, evidence.guard, evidence.exit_proof, evidence.record["outcome"])
            evidence.record.update(settled=True, localMeasurement="socket-counters")
        else:
            self.ledger.retain_supervised(ticket, evidence.record["outcome"])
        return {**evidence.record, "ledger": self.ledger.summary()}

    def run_ui(self, session, *, byte_limit=65536, timeout_ms=8000, cancel_event=None):
        from PrivateSubscriptionUi import SyntheticUiSession, UiIdentity, UI_WORKLOAD, _UI_ISSUER
        if (type(session) is not SyntheticUiSession or session._issuer is not _UI_ISSUER
                or type(self.identity) is not UiIdentity or self.billing is not None):
            raise BudgetError("OwnedSyntheticUiSessionRequired")
        session.check(self.ledger, self.identity)
        plan = tcp_plan(byte_limit, 6, timeout_ms)
        if timeout_ms < 100:
            raise BudgetError("InvalidTcpTimeout")
        self.identity.recheck()
        fingerprint, nonce = session.fingerprint(plan), secrets.token_hex(32)
        ticket = self.ledger.reserve_supervised(1, byte_limit, 6, timeout_ms,
            config_fingerprint=fingerprint, nonce=nonce, workload=UI_WORKLOAD, **self._identity_fields())
        evidence = self._execute_reserved(ticket, UI_WORKLOAD, plan, nonce, fingerprint,
                                          cancel_event=cancel_event, ui_session=session)
        if evidence.complete:
            self.ledger.settle_synthetic(ticket, evidence.guard, evidence.exit_proof, evidence.record["outcome"])
            evidence.record.update(settled=True, localMeasurement="actual-shared-rust-raw-tcp-bytes")
        else:
            self.ledger.retain_supervised(ticket, evidence.record["outcome"])
        evidence.record["persistentBudgetGuardExercised"] = bool(evidence.complete and evidence.record["settled"])
        evidence.record["uiSubscriptionImportExercised"] = False
        with self.ledger.mutex:
            history = self.ledger.data["history"][str(ticket)]
            receipt = history["receipt"]
            evidence.record["parentBudgetEvidence"] = {
                "scope": "existing-synthetic-Ledger-and-current-OS-owner; no provider authority",
                "ledgerId": self.ledger.data["ledgerId"], "reservationId": str(ticket),
                "planDigest": history["planDigest"], "durableHistoryPhase": history["phase"],
                "guardDigest": None if receipt is None else receipt["guardDigest"],
                "settledNativeExit": None if receipt is None else receipt["exit"],
                "fullHoldRetained": str(ticket) in self.ledger.data["reservations"]}
        return {**evidence.record, "ledger": self.ledger.summary()}

    def _billing_query(self, purpose, parent_ticket=None, *, timeout_ms=2000):
        from PrivateSubscriptionBilling import BYTE_LIMIT, CONNECTION_LIMIT, WORKLOAD, HTTP_RESPONSE_CONTRACT
        self.ledger._require_billing_session(self.billing)
        self.identity.recheck()
        nonce = secrets.token_hex(32)
        fingerprint = digest({"domain": "synthetic-billing-control-v1", "nonce": nonce,
                              "purpose": purpose, "parent": parent_ticket, "response_contract": self.billing_response_contract})
        ticket = self.ledger.reserve_billing_control(self.billing, purpose=purpose, parent_ticket=parent_ticket,
            timeout_ms=timeout_ms, config_fingerprint=fingerprint, **self._identity_fields(), nonce=nonce,
            response_contract=self.billing_response_contract)
        query = self.billing.query(ticket, nonce)
        plan = tcp_plan(BYTE_LIMIT, CONNECTION_LIMIT, timeout_ms)
        evidence = self._execute_reserved(ticket, WORKLOAD, plan, nonce, fingerprint, billing_query=query)
        observation = http_observation = None
        if evidence.complete:
            try:
                if query.response_contract == HTTP_RESPONSE_CONTRACT:
                    http_observation = self.billing.http_observation(query, evidence)
                    self.ledger.check_http_billing_observation(self.billing, ticket, http_observation)
                    evidence.record["outcome"] = "ProviderAccountBindingUnproven"
                else:
                    observation = self.billing.observation(query, evidence)
                    self.ledger.check_billing_observation(self.billing, ticket, observation)
            except BudgetError as error:
                observation = http_observation = None
                evidence.record["outcome"] = str(error)
        if evidence.cleanup:
            self.ledger.consume_billing_control(self.billing, ticket, evidence.guard, evidence.exit_proof,
                                                evidence.record["outcome"], observation, http_observation=http_observation)
            evidence.record.update(controlConsumed=True, controlDebit=plan["byteLimit"] + plan["receiveReservation"],
                                   localMeasurement="socket-counters" if evidence.guard is not None else "unknown")
        else:
            self.ledger.retain_supervised(ticket, evidence.record["outcome"])
            evidence.record.update(controlConsumed=False, controlDebit=0)
        evidence.record["billingObservationAccepted"] = observation is not None
        if query.response_contract == HTTP_RESPONSE_CONTRACT:
            evidence.record.update(httpObservationRecorded=http_observation is not None and evidence.cleanup,
                                   httpObservation=None if http_observation is None else http_observation.record(),
                                   providerAuthorization="account-history-and-coverage-unproven")
        evidence.record["controlDebitIsMeasuredTraffic"] = False
        return observation, evidence.record

    def _run_with_billing(self, workload, *, node, byte_limit, timeout_ms, cancel_event):
        from PrivateSubscriptionBilling import DOMAIN
        self.ledger._require_billing_session(self.billing)
        connections = 2 if workload == "core_probe" else 1
        plan = tcp_plan(byte_limit, connections, timeout_ms)
        fingerprint = digest({"protocol": 1, "node": node, "workload": workload, "configuration_version": 1})
        with self.ledger.mutex:
            if any(h["configFingerprint"] == fingerprint for h in self.ledger.data["history"].values()):
                raise BudgetError("ConfigurationAlreadyAttempted")
            if self.ledger.data["attempts"] >= FIRST_ROUND:
                raise BudgetError("FirstRoundComplete")
        controls = []
        with self.billing.query_lock:
            before, report = self._billing_query("preflight", timeout_ms=timeout_ms)
            controls.append(report)
            if before is None:
                return {"schema": 1, "scope": SYNTHETIC_DOMAIN, "billingScope": DOMAIN, **self._identity_fields(),
                        "stage": "billing-preflight", "settled": False, "outcome": report["outcome"],
                        "nodeStarted": False, "controlQueries": controls, "ledger": self.ledger.summary(),
                        "providerRequests": 0, "realNodeRequests": 0, "liveReady": False}
            nonce = secrets.token_hex(32)
            ticket = self.ledger.reserve_billing_node(self.billing, before, node, byte_limit, connections, timeout_ms,
                config_fingerprint=fingerprint, **self._identity_fields(), nonce=nonce, workload=workload)
        evidence = self._execute_reserved(ticket, workload, plan, nonce, fingerprint, cancel_event=cancel_event)
        if not evidence.complete:
            self.ledger.retain_supervised(ticket, evidence.record["outcome"])
        else:
            self.ledger.record_billing_exit(self.billing, ticket, evidence.guard, evidence.exit_proof, evidence.record["outcome"])
            reconciliation = self.reconcile(ticket, timeout_ms=timeout_ms)
            controls.extend(reconciliation["controlQueries"])
            if reconciliation["settled"]:
                evidence.record.update(settled=True, localMeasurement="socket-counters")
            else:
                evidence.record["outcome"] = reconciliation["outcome"]
        return {**evidence.record, "billingScope": DOMAIN, "nodeStarted": True, "controlQueries": controls,
                "ledger": self.ledger.summary()}

    def reconcile(self, ticket, *, timeout_ms=2000):
        """Only the same live session can finish a prior exit-confirmed attempt."""
        from PrivateSubscriptionBilling import DOMAIN
        self.ledger._require_billing_session(self.billing)
        ticket = str(ticket)
        proof = self.billing._pending_exits.get(ticket)
        if proof is None:
            raise BudgetError("CurrentSessionExitProofRequired")
        outcome, settled, controls = "BillingReconciliationRequired", False, []
        with self.billing.query_lock:
            after, report = self._billing_query("reconcile", ticket, timeout_ms=timeout_ms)
            controls.append(report)
            if after is not None:
                try:
                    self.ledger.settle_billing_node(self.billing, ticket, after, proof)
                    settled, outcome = True, "BillingReconciled"
                except BudgetError as error:
                    outcome = str(error)
            else:
                outcome = report["outcome"]
            if not settled:
                self.ledger.retain_supervised(ticket, outcome)
        return {"schema": 1, "scope": SYNTHETIC_DOMAIN, "billingScope": DOMAIN, "reservation_id": ticket,
                "settled": settled, "outcome": outcome, "controlQueries": controls, "ledger": self.ledger.summary(),
                "providerRequests": 0, "realNodeRequests": 0, "liveReady": False}


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error repeats caller-supplied values/paths.
        raise BudgetError("SupervisorArgumentsRejected")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Refuse BEFORE argument paths, private files, ledger creation or metadata
    # subprocesses. There is no CLI flag or adapter boolean which enables live.
    if "--live" in argv:
        print(json.dumps({"error": "AuthenticatedBillingAndWireGuardRequired", "liveReady": False,
                          "blockedBy": ["OriginalLedgerHistory", "AuthenticatedProviderAdapter",
                                        "CompleteWireFence", "ControlledQtUiEntry"]}))
        return 2
    parser = _PrivateArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--worker-sha256", required=True,
                        help="SHA256 from the designated trusted QA-worker build receipt")
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--workload", choices=sorted(SUPERVISED_WORKLOADS), required=True)
    parser.add_argument("--node", type=int, default=1)
    parser.add_argument("--byte-limit", type=int, default=65536)
    parser.add_argument("--timeout-ms", type=int, default=2000)
    parser.add_argument("--synthetic-billing", action="store_true",
                        help="Use only the parent's owned TLS billing fixture; never an official provider")
    parser.add_argument("--billing-response-contract", choices=("synthetic_qa_v1", "subscription_userinfo_v1"),
                        default="synthetic_qa_v1", help="Owned fixture response shape; HTTP counters cannot authorize a node")
    try:
        args = parser.parse_args(argv)
        if args.billing_response_contract != "synthetic_qa_v1" and not args.synthetic_billing:
            raise BudgetError("SyntheticBillingSessionRequired")
        if args.synthetic_billing:
            Ledger.require_existing(args.state_dir)
        identity = WorkerIdentity.inspect(args.worker, args.expected_source, args.worker_sha256)
        with Ledger(args.state_dir, existing_only=args.synthetic_billing) as ledger:
            if ledger.data is None and not args.synthetic_billing:
                ledger.initialize_synthetic()
            billing_session = None
            if args.synthetic_billing:
                from PrivateSubscriptionBilling import BillingSession
                billing_session = BillingSession.register(ledger)
            report = Supervisor(ledger, identity, billing_session,
                                billing_response_contract=args.billing_response_contract).run(args.workload, node=args.node,
                                                    byte_limit=args.byte_limit, timeout_ms=args.timeout_ms)
        print(json.dumps(report, sort_keys=True))
        return 0 if report["settled"] else 2
    except BudgetError as error:
        print(json.dumps({"error": str(error), "liveReady": False}))
        return 2
    except Exception:
        print('{"error":"PrivateSupervisorFailed","liveReady":false}')
        return 2


if __name__ == "__main__":
    # Billing validates the exact sealed execution type through this canonical
    # module name. Running the CLI must not create a second issuer/type when
    # its late import resolves this file again under a different name.
    if sys.modules.setdefault("PrivateSubscriptionSupervisor", sys.modules[__name__]) is not sys.modules[__name__]:
        print('{"error":"PrivateSupervisorModuleIdentity","liveReady":false}')
        raise SystemExit(2)
    raise SystemExit(main())
