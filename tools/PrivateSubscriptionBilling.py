"""Owned synthetic billing fixtures and sealed, session-local observations.

This module has no outbound HTTP client, provider URL or live adapter. Its TLS
server is reached only by the existing mandatory-guard Rust worker. Synthetic
account identities and explicit coverage events are NOT a real provider's
account mapping, freshness, billing delay, wire usage or rollback protection.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets
import socket
import threading
import time

from PrivateSubscriptionBudget import BudgetError, MAX_COUNTER, integer

DOMAIN = "swirl-synthetic-billing-v1"
WORKLOAD = "billing_snapshot"
BYTE_LIMIT = 65536
CONNECTION_LIMIT = 2
MAX_CONTROL_ATTEMPTS = 36
MAX_FRESHNESS_SECONDS = 2.0
_SESSION_ISSUER = object()
_OBSERVATION_ISSUER = object()
_QUERY_ISSUER = object()
_FIELDS = {"schema", "domain", "authority_id", "account_id", "period_id", "request_nonce",
           "revision", "covered_sequence", "upload", "download", "total", "expire"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_snapshot(value, binding=None):
    if (not isinstance(value, dict) or set(value) != _FIELDS
            or type(value["schema"]) is not int or value["schema"] != 1
            or value["domain"] != DOMAIN):
        raise BudgetError("SyntheticBillingSnapshotRejected")
    for key in ("authority_id", "account_id", "period_id", "request_nonce"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise BudgetError("SyntheticBillingIdentityRejected")
    for key in ("revision", "covered_sequence", "upload", "download", "total", "expire"):
        integer(value[key])
    if not value["revision"] or not value["total"] or value["upload"] + value["download"] > value["total"]:
        raise BudgetError("SyntheticBillingCountersRejected")
    if binding is not None and any(value[key] != binding[key] for key in ("authority_id", "account_id", "period_id")):
        raise BudgetError("SyntheticBillingIdentityMismatch")


@dataclass(frozen=True, init=False)
class BillingObservation:
    """Issued after a real owned TLS exchange; JSON/booleans are not issuers."""

    _session: object
    _payload: bytes
    _received: float
    _query: object
    _seal: object

    def __init__(self, issuer, session, query, payload, received):
        if issuer is not _OBSERVATION_ISSUER:
            raise BudgetError("SyntheticBillingObservationRequired")
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_query", query)
        object.__setattr__(self, "_payload", canonical(payload))
        object.__setattr__(self, "_received", received)
        object.__setattr__(self, "_seal", issuer)

    def record(self):
        return json.loads(self._payload)

    def require(self, session, *, fresh=True):
        if self._seal is not _OBSERVATION_ISSUER or self._session is not session or session.closed:
            raise BudgetError("SyntheticBillingObservationRequired")
        now = time.monotonic()
        if fresh and not (self._query.created_monotonic <= self._received <= now
                          and now - self._query.created_monotonic <= MAX_FRESHNESS_SECONDS):
            raise BudgetError("SyntheticBillingObservationExpired")
        return self.record()


class SyntheticBillingAuthority:
    """Explicit test provider model. Never an original-account authority.

    It owns random test identities, counts and logical exit-coverage events.
    A request nonce authenticates a current response, while coverage remains a
    separate modeled assertion. No wall clock or repeated equal count implies
    coverage. Controlled failure modes affect only this parent's own TLS server.
    """

    FAULTS = {None, "wrong_account", "wrong_period", "wrong_nonce", "old_revision",
              "counter_reset", "redirect", "duplicate_header", "bad_ca", "wrong_sni",
              "expired_certificate", "unauthorized", "delayed_response", "oversized_header",
              "unknown_header", "extra_body", "transfer_encoding", "nonzero_content_length", "noncanonical_number"}

    def __init__(self, *, upload=1000, download=2000, total=200_000_000_000, auto_cover=True):
        for value in (upload, download, total):
            integer(value)
        if not total or upload + download > total or type(auto_cover) is not bool:
            raise BudgetError("InvalidSyntheticBillingModel")
        self.binding = {key: secrets.token_hex(32) for key in ("authority_id", "account_id", "period_id")}
        self.upload, self.download, self.total = upload, download, total
        self.revision = 0
        self.covered_sequence = 0
        self.auto_cover = auto_cover
        self._fault = None
        self.lock = threading.RLock()

    def add_other_client_usage(self, upload=0, download=0):
        with self.lock:
            upload, download = integer(upload), integer(download)
            if self.upload + self.download + upload + download > self.total:
                raise BudgetError("InvalidSyntheticBillingModel")
            self.upload += upload
            self.download += download

    def cover_exit(self, sequence):
        with self.lock:
            integer(sequence)
            self.covered_sequence = max(self.covered_sequence, sequence)

    def fault_next(self, fault):
        if fault not in self.FAULTS:
            raise BudgetError("InvalidSyntheticBillingFault")
        with self.lock:
            self._fault = fault

    def _response(self, nonce):
        with self.lock:
            self.revision += 1
            value = {"schema": 1, "domain": DOMAIN, **self.binding, "request_nonce": nonce,
                     "revision": self.revision, "covered_sequence": self.covered_sequence,
                     "upload": self.upload, "download": self.download, "total": self.total, "expire": 0}
            fault, self._fault = self._fault, None
        if fault == "wrong_account":
            value["account_id"] = "0" * 64
        elif fault == "wrong_period":
            value["period_id"] = "0" * 64
        elif fault == "wrong_nonce":
            value["request_nonce"] = "0" * 64
        elif fault == "old_revision":
            value["revision"] = max(1, value["revision"] - 1)
        elif fault == "counter_reset":
            value["upload"] = value["download"] = 0
        return value, fault


class _BillingQuery:
    def __init__(self, issuer, session, ticket, nonce):
        if issuer is not _QUERY_ISSUER:
            raise BudgetError("OwnedBillingQueryRequired")
        self._seal, self.session, self.ticket, self.nonce = issuer, session, str(ticket), nonce
        self.created_monotonic = time.monotonic()
        self.payload, self.fault = session.authority._response(nonce)
        self.http_status = None
        self.request_received = False
        self.request_authenticated = False

    def grant(self):
        return {"schema": 1, "domain": DOMAIN, **self.session.binding, "request_nonce": self.nonce}

    def configure_tls(self, tls):
        if self.fault == "bad_ca":
            # The real fixture certificate is unchanged. Supply a different
            # valid CA to the client so certificate verification must reject it.
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.x509.oid import NameOID
            from datetime import datetime, timedelta, timezone
            key = ec.generate_private_key(ec.SECP256R1())
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Unrelated synthetic CA")])
            now = datetime.now(timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                    .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
                    .not_valid_after(now + timedelta(days=1))
                    .add_extension(x509.BasicConstraints(ca=True, path_length=0), True).sign(key, hashes.SHA256()))
            return {**tls, "ca_der_base64": base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode("ascii")}
        return tls

    def serve(self, fixture, conn):
        if self._seal is not _QUERY_ISSUER:
            raise BudgetError("OwnedBillingQueryRequired")
        wrapped = fixture.context.wrap_socket(conn, server_side=True, do_handshake_on_connect=False)
        with fixture.lock:
            fixture.active.append(wrapped)
        try:
            while not fixture.stop.is_set():
                try:
                    wrapped.do_handshake()
                    break
                except socket.timeout:
                    continue
            request = fixture._headers(wrapped)
            expected = ("HEAD /swirl-private-billing/" + self.nonce + " HTTP/1.1\r\n").encode("ascii")
            fields = {}
            for line in request.split(b"\r\n")[1:]:
                if not line:
                    continue
                key, separator, value = line.partition(b":")
                key = key.lower()
                if not separator or key in fields:
                    raise BudgetError("FixtureBillingRequestRejected")
                fields[key] = value.strip()
            expected_password = fixture.challenge if self.fault != "unauthorized" else "explicitly-rejected-synthetic-credential"
            auth = base64.b64encode(("swirl-private-billing:" + expected_password).encode("ascii"))
            scheme, separator, token = fields.get(b"authorization", b"").partition(b" ")
            if (not request.startswith(expected) or fields.get(b"host") != b"swirl-qa.fixture.invalid"
                    or fields.get(b"connection", b"").lower() != b"close"
                    or set(fields) != {b"host", b"authorization", b"connection"}):
                raise BudgetError("FixtureBillingRequestRejected")
            self.request_received = True
            self.request_authenticated = scheme.lower() == b"basic" and bool(separator) and hmac.compare_digest(token, auth)
            if self.fault == "delayed_response":
                fixture.stop.wait(9)
                return
            if not self.request_authenticated:
                response = b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                self.http_status = 401
            elif self.fault == "redirect":
                response = b"HTTP/1.1 302 Found\r\nLocation: https://never-follow.fixture.invalid/\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                self.http_status = 302
            else:
                value = self.payload
                headers = [("Subscription-Userinfo", ";".join(f"{key}={value[key]}" for key in ("upload", "download", "total", "expire"))),
                           ("X-Swirl-QA-Billing-Schema", "1"), ("X-Swirl-QA-Billing-Domain", DOMAIN)]
                for header, key in (("Authority", "authority_id"), ("Account", "account_id"), ("Period", "period_id"),
                                    ("Nonce", "request_nonce"), ("Revision", "revision"), ("Covered-Sequence", "covered_sequence")):
                    headers.append(("X-Swirl-QA-Billing-" + header, str(value[key])))
                if self.fault == "duplicate_header":
                    headers.append(("Subscription-Userinfo", "upload=0;download=0;total=200000000000;expire=0"))
                if self.fault == "oversized_header":
                    headers.append(("X-Oversized", "x" * 8192))
                if self.fault == "unknown_header":
                    headers.append(("X-Unknown", "must-reject"))
                if self.fault == "transfer_encoding":
                    headers.append(("Transfer-Encoding", "chunked"))
                if self.fault == "noncanonical_number":
                    headers[0] = (headers[0][0], "upload=01000;download=2000;total=200000000000;expire=0")
                headers.extend((("Content-Length", "1" if self.fault == "nonzero_content_length" else "0"), ("Connection", "close")))
                response = ("HTTP/1.1 200 OK\r\n" + "".join(f"{key}: {value}\r\n" for key, value in headers) + "\r\n").encode("ascii")
                if self.fault == "extra_body":
                    response += b"x"
                self.http_status = 200
            fixture._send(wrapped, response)
            fixture.http_status = self.http_status
            # Send TLS close_notify so the worker can prove EOF with a single
            # bounded read after the headers. Waiting for its reciprocal alert
            # remains bounded by this owned socket's short timeout.
            try:
                raw = wrapped.unwrap()
                raw.close()
            except (OSError, TimeoutError):
                pass
        finally:
            wrapped.close()


class BillingSession:
    """A current-process synthetic registration, never a recovery trust anchor."""

    def __init__(self, issuer, ledger, authority):
        if issuer is not _SESSION_ISSUER or not isinstance(authority, SyntheticBillingAuthority):
            raise BudgetError("SyntheticBillingSessionRequired")
        self._issuer = issuer
        self.ledger, self.authority = ledger, authority
        self.binding = authority.binding.copy()
        self.session_id = secrets.token_hex(32)
        self.closed = False
        self.query_lock = threading.RLock()
        self._pending_exits = {}
        self._observations = {}
        self._checkpoint = None
        self._root_identity = None

    @classmethod
    def register(cls, ledger, authority=None):
        authority = SyntheticBillingAuthority() if authority is None else authority
        session = cls(_SESSION_ISSUER, ledger, authority)
        ledger.register_synthetic_billing(session)
        return session

    def registration(self):
        return {"schema": 1, "domain": DOMAIN, **self.binding, "session_id": self.session_id,
                "ledger_id": self.ledger.data["ledgerId"],
                "path_digest": hashlib.sha256(str(self.ledger.root.resolve()).encode("utf-8")).hexdigest()}

    def _refresh_checkpoint(self):
        self._checkpoint = hashlib.sha256(self.ledger.path.read_bytes()).hexdigest()
        info = self.ledger.root.stat()
        self._root_identity = (info.st_dev, info.st_ino)

    def require(self, ledger):
        # The ledger's atomic save changes memory, disk and the session digest
        # under this same lock. Do not observe a half-committed transition from
        # a concurrent worker while checking the current-process registration.
        with ledger.mutex:
            self._require_locked(ledger)

    def _require_locked(self, ledger):
        if (self._issuer is not _SESSION_ISSUER or self.closed or self.ledger is not ledger
                or getattr(ledger, "_billing_session", None) is not self or not ledger.lock):
            raise BudgetError("SyntheticBillingSessionRequired")
        if self._checkpoint is None:
            raise BudgetError("SyntheticBillingHistoryUnconfirmed")
        info = ledger.root.stat()
        if ((info.st_dev, info.st_ino) != self._root_identity
                or hashlib.sha256(ledger.path.read_bytes()).hexdigest() != self._checkpoint
                or digest(ledger.data) != self._checkpoint
                or ledger.data["billing"]["registration"] != self.registration()):
            raise BudgetError("SyntheticBillingHistoryUnconfirmed")

    def query(self, ticket, nonce):
        self.require(self.ledger)
        return _BillingQuery(_QUERY_ISSUER, self, ticket, nonce)

    def observation(self, query, exchange):
        from PrivateSubscriptionSupervisor import _ExecutionEvidence
        self.require(self.ledger)
        if (not isinstance(query, _BillingQuery) or query._seal is not _QUERY_ISSUER or query.session is not self
                or not isinstance(exchange, _ExecutionEvidence)):
            raise BudgetError("SyntheticBillingObservationRequired")
        payload, received_monotonic = exchange.billing_snapshot(query)
        now = time.monotonic()
        if (type(received_monotonic) is not float or not query.created_monotonic <= received_monotonic <= now
                or now - query.created_monotonic > MAX_FRESHNESS_SECONDS):
            raise BudgetError("SyntheticBillingObservationExpired")
        validate_snapshot(payload, self.binding)
        if payload["request_nonce"] != query.nonce or payload != query.payload:
            raise BudgetError("SyntheticBillingObservationMismatch")
        observation = BillingObservation(_OBSERVATION_ISSUER, self, query, payload, received_monotonic)
        self._observations[query.ticket] = observation
        return observation

    def mark_exit(self, ticket, proof, coverage_sequence):
        self._pending_exits[str(ticket)] = proof
        if self.authority.auto_cover:
            self.authority.cover_exit(coverage_sequence)

    def require_exit(self, ticket, proof):
        self.require(self.ledger)
        if self._pending_exits.get(str(ticket)) is not proof:
            raise BudgetError("CurrentSessionExitProofRequired")

    def close(self):
        self.closed = True
        self._pending_exits.clear()
        self._observations.clear()
