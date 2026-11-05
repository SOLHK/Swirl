"""Persistent, offline budget gate for a single private acceptance task.

This module performs NO networking and accepts NO subscription URL or secret.
The current Swirl probe path has no authoritative wire counter / hard-stop
adapter. ``require_live_ready`` therefore always refuses live execution. A
successful offline reservation is not permission to launch a native probe.

The ledger survives batches, process restarts and interrupted reservations.
Provider billing and local transfer counts remain separate. Byte units are
decimal GB, conservatively smaller than GiB. No reset operation is provided.
Every window/process must use the same stable, persistent state directory. A
different directory or machine is not automatically linked; moving execution
requires preserving the complete ledger and its initialization/lock marker.
This module cannot detect deletion of the whole directory or coordinate a
second machine. Those unresolved conditions also preclude live readiness.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time

TASK = "swirl-0.2.40-private-acceptance"
GB = 1_000_000_000
TARGET, REVIEW, NO_EXPANSION, STOP, ABSOLUTE = (n * GB for n in (2, 5, 10, 15, 20))
RESERVE_PACKAGE = 80 * GB
MAX_CONCURRENT, FIRST_ROUND, TIMEOUT_MS, BODY_LIMIT = 3, 12, 8000, 65536
MAX_PROBE_RESERVATION = 1024 * 1024
MAX_COUNTER = (1 << 63) - 1


class BudgetError(Exception):
    """Only fixed codes, never private exception text, cross the CLI boundary."""


def integer(value):
    if type(value) is not int or not 0 <= value <= MAX_COUNTER:
        raise BudgetError("InvalidCounter")
    return value


def parse_userinfo(header):
    """Validate numeric subscription-userinfo without retaining the raw header.

    Parsing a supplied header does not verify its provenance or freshness.
    A future authenticated provider adapter must establish those separately.
    """
    if not isinstance(header, str) or not 1 <= len(header) <= 4096:
        raise BudgetError("BillingUnavailable")
    fields = {}
    for item in header.split(";"):
        if not item.strip():
            continue
        pair = item.strip().split("=", 1)
        if len(pair) != 2 or not re.fullmatch(r"[a-zA-Z_-]{1,64}", pair[0].strip()):
            raise BudgetError("InvalidBillingHeader")
        name, value = pair[0].strip().lower(), pair[1].strip()
        if name not in {"upload", "download", "total", "expire"}:
            continue
        if name in fields or not re.fullmatch(r"[0-9]{1,19}", value):
            raise BudgetError("InvalidBillingHeader")
        fields[name] = integer(int(value))
    if not {"upload", "download", "total"} <= fields.keys():
        raise BudgetError("BillingUnavailable")
    if not fields["total"] or fields["upload"] + fields["download"] > fields["total"]:
        raise BudgetError("InvalidBillingTotals")
    return fields


def policy(billed, local, held, provider_remaining):
    values = [integer(v) for v in (billed, local, held, provider_remaining)]
    billed, local, held, provider_remaining = values
    # These are independent observations, not amounts to add and double-count.
    # Held reservations cover unaccounted or interrupted traffic conservatively.
    guarded = max(billed, local) + held
    if guarded >= ABSOLUTE:
        return "AbsoluteLimit"
    if guarded >= STOP:
        return "MandatoryStop"
    unbilled_local = max(0, local - billed)
    if provider_remaining < RESERVE_PACKAGE + unbilled_local + held:
        return "PackageReserve"
    if guarded >= NO_EXPANSION:
        return "NoExpansion"
    if guarded >= REVIEW:
        return "ReviewRequired"
    if guarded >= TARGET:
        return "NormalTargetReached"
    return "WithinNormalTarget"


class Ledger:
    """One exclusive process and atomic accounting for the entire task.

    Reservations are held after a crash or timeout until reconciled explicitly;
    merely reopening the ledger never refunds them. Methods are thread-safe.
    This is the offline half of the gate, not a network meter.
    """

    def __init__(self, directory):
        self.root = Path(directory).absolute()
        self.path = self.root / "traffic-budget.json"
        self.lock = None
        self.data = None
        self.mutex = threading.RLock()
        self.initialized = False

    def __enter__(self):
        if os.name != "posix":
            # chmod(0600) is not a private Windows ACL. Do not pretend it is.
            raise BudgetError("PrivateStorageAdapterRequired")
        if any(p.is_symlink() for p in [self.root, *self.root.parents]):
            raise BudgetError("PrivateDirectoryRequired")
        if any((p / ".git").exists() for p in [self.root, *self.root.parents]):
            raise BudgetError("OutsideRepositoryRequired")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.root.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise BudgetError("PrivateDirectoryRequired")
        import fcntl
        fd = os.open(self.root / "traffic-budget.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(fd, "r+b")
        try:
            lock_info = os.fstat(fd)
            if not stat.S_ISREG(lock_info.st_mode) or stat.S_IMODE(lock_info.st_mode) != 0o600 or lock_info.st_uid != os.getuid():
                raise BudgetError("PrivateLockRequired")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise BudgetError("AnotherAcceptanceProcessActive") from None
            marker = self.lock.read(4096)
            if marker not in (b"", (TASK + "\n").encode("ascii")):
                raise BudgetError("InvalidTaskBinding")
            self.initialized = bool(marker)
            if self.initialized and not (self.path.exists() or self.path.is_symlink()):
                raise BudgetError("LedgerMissingAfterInitialization")
            if self.path.exists() or self.path.is_symlink():
                if not self.initialized:
                    raise BudgetError("TaskBindingMissing")
                fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "r", encoding="utf-8") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid() or info.st_size > 65536:
                        raise BudgetError("PrivateLedgerRequired")
                    def unique_keys(pairs):
                        result = {}
                        for key, value in pairs:
                            if key in result:
                                raise BudgetError("DuplicateLedgerKey")
                            result[key] = value
                        return result
                    try:
                        self.data = json.load(stream, object_pairs_hook=unique_keys)
                    except (ValueError, UnicodeError, RecursionError):
                        raise BudgetError("InvalidLedgerJson") from None
                self._validate()
            return self
        except BaseException:
            self.lock.close()
            self.lock = None
            raise

    def __exit__(self, *unused):
        if self.lock:
            self.lock.close()
            self.lock = None

    def _validate(self):
        d = self.data
        keys = {"schema", "task", "baseline", "provider", "localUpload", "localDownload",
                "attempts", "sequence", "reservations"}
        if not isinstance(d, dict) or set(d) != keys or type(d.get("schema")) is not int or d["schema"] != 1 or d["task"] != TASK:
            raise BudgetError("InvalidTaskLedger")
        for key in ("localUpload", "localDownload", "attempts", "sequence"):
            integer(d.get(key))
        for key in ("baseline", "provider"):
            s = d.get(key)
            if s is not None:
                if not isinstance(s, dict) or set(s) - {"upload", "download", "total", "expire"}:
                    raise BudgetError("InvalidBillingSnapshot")
                parse_userinfo(";".join(f"{k}={v}" for k, v in s.items()))
        if (d["baseline"] is None) != (d["provider"] is None):
            raise BudgetError("InvalidBillingSnapshot")
        if d["baseline"] is not None:
            if d["provider"]["total"] != d["baseline"]["total"] or any(d["provider"][k] < d["baseline"][k] for k in ("upload", "download")):
                raise BudgetError("BillingCounterReset")
        if not isinstance(d.get("reservations"), dict) or len(d["reservations"]) > MAX_CONCURRENT:
            raise BudgetError("InvalidReservations")
        if d["attempts"] > FIRST_ROUND or d["sequence"] != d["attempts"] or len(d["reservations"]) > d["attempts"]:
            raise BudgetError("InvalidAttemptCount")
        seen_nodes = set()
        for key, r in d["reservations"].items():
            if not re.fullmatch(r"[1-9][0-9]{0,11}", key) or not isinstance(r, dict) or set(r) != {"node", "held", "sent", "received"}:
                raise BudgetError("InvalidReservations")
            if type(r["node"]) is not int or not 1 <= r["node"] <= 100000:
                raise BudgetError("InvalidNodeOrdinal")
            if r["node"] in seen_nodes or int(key) > d["sequence"]:
                raise BudgetError("InvalidReservations")
            seen_nodes.add(r["node"])
            if integer(r["held"]) > MAX_PROBE_RESERVATION:
                raise BudgetError("InvalidReservations")
            integer(r["sent"])
            integer(r["received"])
            if not 1 <= r["held"] + r["sent"] + r["received"] <= MAX_PROBE_RESERVATION:
                raise BudgetError("InvalidReservations")
        if sum(r["sent"] for r in d["reservations"].values()) > d["localUpload"] or sum(r["received"] for r in d["reservations"].values()) > d["localDownload"]:
            raise BudgetError("InvalidLocalTotals")

    def _save(self):
        if not self.lock:
            raise BudgetError("LedgerNotLocked")
        self._validate()
        fd, temporary = tempfile.mkstemp(prefix=".budget-", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(self.data, stream, separators=(",", ":"), sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)

    def initialize(self, userinfo=None):
        with self.mutex:
            if self.data is not None or self.initialized:
                raise BudgetError("TaskAlreadyInitialized")
            if not self.lock:
                raise BudgetError("LedgerNotLocked")
            snapshot = parse_userinfo(userinfo) if userinfo is not None else None
            # Persist a separate initialization marker BEFORE the ledger. A
            # crash or deletion must stop rather than silently create baseline 0.
            self.lock.write((TASK + "\n").encode("ascii"))
            self.lock.flush()
            os.fsync(self.lock.fileno())
            self.initialized = True
            self.data = {"schema": 1, "task": TASK, "baseline": snapshot, "provider": snapshot,
                         "localUpload": 0, "localDownload": 0, "attempts": 0, "sequence": 0,
                         "reservations": {}}
            self._save()

    def observe_provider(self, userinfo):
        with self.mutex:
            fresh = parse_userinfo(userinfo)
            if self.data is None or self.data["baseline"] is None:
                raise BudgetError("BaselineUnavailable")
            previous = self.data["provider"]
            if fresh["total"] != previous["total"] or any(fresh[k] < previous[k] for k in ("upload", "download")):
                raise BudgetError("BillingCounterReset")
            self.data["provider"] = fresh
            self._save()

    def summary(self):
        with self.mutex:
            if self.data is None:
                raise BudgetError("TaskNotInitialized")
            d = self.data
            held = sum(r["held"] for r in d["reservations"].values())
            local = d["localUpload"] + d["localDownload"]
            baseline, current = d["baseline"], d["provider"]
            used_start = None if baseline is None else baseline["upload"] + baseline["download"]
            used_now = None if current is None else current["upload"] + current["download"]
            billed = None if current is None else used_now - used_start
            remaining = None if current is None else current["total"] - used_now
            state = "BillingUnavailable" if billed is None else policy(billed, local, held, remaining)
            if current is not None and current.get("expire", 0) and current["expire"] <= int(time.time()):
                state = "BillingExpired"
            return {"task": TASK, "policy": state, "baselineUsed": used_start, "latestUsed": used_now,
                    "billingDelta": billed, "providerRemaining": remaining,
                    "remainingAbsoluteBudget": None if billed is None else max(0, ABSOLUTE - billed),
                    "localUpload": d["localUpload"], "localDownload": d["localDownload"],
                    "heldBytes": held, "attempts": d["attempts"],
                    "providerStatisticsAuthenticated": False, "wireAccountingAttached": False,
                    "hardCancellationAttached": False, "liveReady": False}

    def reserve_offline(self, node, amount=MAX_PROBE_RESERVATION):
        """Exercise admission without opening a socket. Never an execution grant."""
        with self.mutex:
            if type(node) is not int or not 1 <= node <= 100000:
                raise BudgetError("InvalidNodeOrdinal")
            if not 1 <= integer(amount) <= MAX_PROBE_RESERVATION:
                raise BudgetError("InvalidReservationSize")
            state = self.summary()
            if state["policy"] != "WithinNormalTarget":
                raise BudgetError(state["policy"])
            d = self.data
            if any(r["node"] == node for r in d["reservations"].values()):
                raise BudgetError("NodeAlreadyReserved")
            if len(d["reservations"]) >= MAX_CONCURRENT:
                raise BudgetError("ConcurrencyLimit")
            if d["attempts"] >= FIRST_ROUND:
                raise BudgetError("FirstRoundComplete")
            predicted = policy(state["billingDelta"], state["localUpload"] + state["localDownload"],
                               state["heldBytes"] + amount, state["providerRemaining"])
            if predicted != "WithinNormalTarget":
                raise BudgetError(predicted)
            d["attempts"] += 1
            d["sequence"] += 1
            ticket = str(d["sequence"])
            d["reservations"][ticket] = {"node": node, "held": amount, "sent": 0, "received": 0}
            self._save()
            return ticket

    def account_offline(self, ticket, upload=0, download=0):
        """Debit a simulated bounded transfer before I/O, with no automatic refund.

        Production integration needs transport/OS byte counts including failed
        attempts. HTTP body size must never be used as provider billing here.
        """
        with self.mutex:
            upload, download = integer(upload), integer(download)
            if self.summary()["policy"] != "WithinNormalTarget":
                raise BudgetError(self.summary()["policy"])
            r = self.data["reservations"].get(str(ticket))
            if r is None:
                raise BudgetError("UnknownReservation")
            if upload + download > r["held"]:
                raise BudgetError("RequestByteLimit")
            r["held"] -= upload + download
            r["sent"] += upload
            r["received"] += download
            self.data["localUpload"] += upload
            self.data["localDownload"] += download
            self._save()

    def finish_offline(self, ticket, quiescent=False):
        with self.mutex:
            if not quiescent:
                raise BudgetError("UnreleasedRequests")
            if self.data is None or str(ticket) not in self.data["reservations"]:
                raise BudgetError("UnknownReservation")
            del self.data["reservations"][str(ticket)]
            self._save()

    def require_live_ready(self):
        # No caller-provided boolean, CLI flag or stale statistics can bypass
        # the absent production transport counter / cancellation integration.
        raise BudgetError("AuthenticatedBillingAndWireGuardRequired")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "status", "preflight"))
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        with Ledger(args.state_dir) as ledger:
            if args.command == "init":
                # Unknown is not zero; authenticated subscription acquisition
                # belongs in the future protected adapter, not this CLI.
                ledger.initialize()
            report = ledger.summary()
            if args.command == "preflight":
                report["blockedBy"] = ["AuthenticatedProviderStatisticsRequired",
                    "TransportWireCounterRequired", "HardCancellationAdapterRequired"]
            print(json.dumps(report, sort_keys=True))
            return 2 if args.command == "preflight" else 0
    except BudgetError as error:
        print(json.dumps({"error": str(error), "liveReady": False}))
        return 2
    except Exception:
        print('{"error":"PrivateBudgetGateFailed","liveReady":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
