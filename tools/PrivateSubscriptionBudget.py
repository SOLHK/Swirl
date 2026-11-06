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
second machine. Restoring an older complete, valid ledger is not detected
either: the lock marker binds the task, not a monotonic accounting history.
A restored snapshot therefore cannot establish the latest cumulative usage
or serve as proof of remaining live budget. These unresolved conditions also
preclude live readiness.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time
import uuid

TASK = "swirl-0.2.40-private-acceptance"
GB = 1_000_000_000
TARGET, REVIEW, NO_EXPANSION, STOP, ABSOLUTE = (n * GB for n in (2, 5, 10, 15, 20))
RESERVE_PACKAGE = 80 * GB
MAX_CONCURRENT, FIRST_ROUND, TIMEOUT_MS, BODY_LIMIT = 3, 12, 8000, 65536
# Legacy, unstructured offline reservations keep their original ceiling. TCP
# plans have a separate, explicit cap matching swirl-transport's guarded path.
MAX_PROBE_RESERVATION = 1024 * 1024
TCP_MAX_BYTES = 16 * 1024 * 1024
TCP_MAX_CONNECTIONS = 48
TCP_RECEIVE_RESERVATION = 1024 * 1024
MAX_COUNTER = (1 << 63) - 1


class BudgetError(Exception):
    """Only fixed codes, never private exception text, cross the CLI boundary."""


class _WindowsStorage:
    """User-owned Windows handles with a protected DACL and exclusive lock file."""

    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        self.c = c
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        self.security = c.WinDLL("advapi32", use_last_error=True)
        pointer = c.c_void_p
        for library, name, result, arguments in (
            (self.kernel, "GetCurrentProcess", w.HANDLE, []),
            (self.kernel, "GetDriveTypeW", w.UINT, [w.LPCWSTR]),
            (self.kernel, "CloseHandle", w.BOOL, [w.HANDLE]),
            (self.kernel, "LocalFree", pointer, [pointer]),
            (self.kernel, "CreateDirectoryW", w.BOOL, [w.LPCWSTR, pointer]),
            (self.kernel, "CreateFileW", w.HANDLE, [w.LPCWSTR, w.DWORD, w.DWORD, pointer, w.DWORD, w.DWORD, w.HANDLE]),
            (self.kernel, "GetFileInformationByHandle", w.BOOL, [w.HANDLE, pointer]),
            (self.kernel, "MoveFileExW", w.BOOL, [w.LPCWSTR, w.LPCWSTR, w.DWORD]),
            (self.security, "OpenProcessToken", w.BOOL, [w.HANDLE, w.DWORD, pointer]),
            (self.security, "GetTokenInformation", w.BOOL, [w.HANDLE, c.c_int, pointer, w.DWORD, pointer]),
            (self.security, "ConvertSidToStringSidW", w.BOOL, [pointer, pointer]),
            (self.security, "ConvertStringSecurityDescriptorToSecurityDescriptorW", w.BOOL, [w.LPCWSTR, w.DWORD, pointer, pointer]),
            (self.security, "GetSecurityInfo", w.DWORD, [w.HANDLE, c.c_int, w.DWORD, pointer, pointer, pointer, pointer, pointer]),
            (self.security, "GetSecurityDescriptorControl", w.BOOL, [pointer, pointer, pointer]),
            (self.security, "GetAce", w.BOOL, [pointer, w.DWORD, pointer]),
            (self.security, "EqualSid", w.BOOL, [pointer, pointer]),
        ):
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments

        class SecurityAttributes(c.Structure):
            _fields_ = [("length", w.DWORD), ("descriptor", pointer), ("inherit", w.BOOL)]

        class FileInformation(c.Structure):
            _fields_ = [("attributes", w.DWORD), ("created", w.FILETIME),
                        ("accessed", w.FILETIME), ("written", w.FILETIME),
                        ("volume", w.DWORD), ("sizeHigh", w.DWORD), ("sizeLow", w.DWORD),
                        ("links", w.DWORD), ("indexHigh", w.DWORD), ("indexLow", w.DWORD)]

        self.FileInformation = FileInformation
        token, needed = w.HANDLE(), w.DWORD()
        if not self.security.OpenProcessToken(self.kernel.GetCurrentProcess(), 8, c.byref(token)):
            raise BudgetError("PrivateIdentityUnavailable")
        try:
            self.security.GetTokenInformation(token, 1, None, 0, c.byref(needed))
            self.token_user = c.create_string_buffer(needed.value)
            if not self.security.GetTokenInformation(token, 1, self.token_user, needed, c.byref(needed)):
                raise BudgetError("PrivateIdentityUnavailable")
            self.sid = pointer.from_buffer(self.token_user).value
        finally:
            self.kernel.CloseHandle(token)
        text_sid = w.LPWSTR()
        if not self.security.ConvertSidToStringSidW(self.sid, c.byref(text_sid)):
            raise BudgetError("PrivateIdentityUnavailable")
        try:
            sddl = f"O:{text_sid.value}D:P(A;OICI;FA;;;{text_sid.value})"
        finally:
            self.kernel.LocalFree(text_sid)
        self.descriptor = pointer()
        if not self.security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(self.descriptor), None):
            raise BudgetError("PrivateDescriptorUnavailable")
        self.attributes = SecurityAttributes(c.sizeof(SecurityAttributes), self.descriptor, False)
        self.directory = None

    def close(self):
        if self.directory is not None:
            self.kernel.CloseHandle(self.directory)
            self.directory = None
        self.kernel.LocalFree(self.descriptor)
        self.descriptor = None

    def validate(self, handle, directory=False):
        c = self.c
        info = self.FileInformation()
        if not self.kernel.GetFileInformationByHandle(handle, c.byref(info)):
            raise BudgetError("PrivateStorageRequired")
        if info.attributes & 0x400 or bool(info.attributes & 0x10) != directory or (not directory and info.links != 1):
            raise BudgetError("PrivateStorageRequired")
        owner, dacl, descriptor = c.c_void_p(), c.c_void_p(), c.c_void_p()
        if self.security.GetSecurityInfo(handle, 1, 5, c.byref(owner), None, c.byref(dacl), None, c.byref(descriptor)):
            raise BudgetError("PrivateAclRequired")
        try:
            if not owner or not self.security.EqualSid(owner, self.sid) or not dacl:
                raise BudgetError("PrivateAclRequired")
            # ACL header's AceCount is a WORD at offset 4. Require exactly one
            # full-control allow entry for the authenticated process user.
            if c.c_ushort.from_address(dacl.value + 4).value != 1:
                raise BudgetError("PrivateAclRequired")
            ace = c.c_void_p()
            if not self.security.GetAce(dacl, 0, c.byref(ace)):
                raise BudgetError("PrivateAclRequired")
            if (c.c_ubyte.from_address(ace.value).value != 0
                    or c.c_ubyte.from_address(ace.value + 1).value & 8
                    or c.c_uint32.from_address(ace.value + 4).value != 0x1F01FF
                    or not self.security.EqualSid(ace.value + 8, self.sid)):
                raise BudgetError("PrivateAclRequired")
            if directory:
                control, revision = c.c_ushort(), c.c_ulong()
                if (not self.security.GetSecurityDescriptorControl(descriptor, c.byref(control), c.byref(revision))
                        or not control.value & 0x1000):
                    raise BudgetError("PrivateAclRequired")
        finally:
            self.kernel.LocalFree(descriptor)

    def open(self, path, *, create=False, directory=False, exclusive=False):
        import msvcrt
        c = self.c
        access = 0x20080 if directory else 0xC0020000 if create or exclusive else 0x80020000
        flags = 0x00200000 | (0x02000000 if directory else 0x80000000)
        handle = self.kernel.CreateFileW(str(path), access, 0 if exclusive else 3,
                                        c.byref(self.attributes), 4 if exclusive else 1 if create else 3,
                                        flags, None)
        if handle == c.c_void_p(-1).value:
            if exclusive and c.get_last_error() == 32:
                raise BudgetError("AnotherAcceptanceProcessActive")
            raise BudgetError("PrivateStorageOpenFailed")
        try:
            self.validate(handle, directory)
            if directory:
                return handle
            return msvcrt.open_osfhandle(handle, (os.O_RDWR if create or exclusive else os.O_RDONLY) | os.O_BINARY)
        except BaseException:
            self.kernel.CloseHandle(handle)
            raise

    def prepare(self, root):
        if self.kernel.GetDriveTypeW(root.anchor) != 3:  # DRIVE_FIXED
            raise BudgetError("PrivateLocalDirectoryRequired")
        root.parent.mkdir(parents=True, exist_ok=True)
        if not self.kernel.CreateDirectoryW(str(root), self.c.byref(self.attributes)) and self.c.get_last_error() != 183:
            raise BudgetError("PrivateDirectoryRequired")
        # Keep the directory open without FILE_SHARE_DELETE for this session.
        self.directory = self.open(root, directory=True)

    def temporary(self, root):
        path = root / (".budget-" + uuid.uuid4().hex)
        return self.open(path, create=True), path

    def replace(self, source, target):
        # The temporary file was fsynced. WRITE_THROUGH completes the rename
        # before reporting success, within the same directory and volume.
        if not self.kernel.MoveFileExW(str(source), str(target), 0x9):
            raise BudgetError("PrivateLedgerCommitFailed")


def integer(value):
    if type(value) is not int or not 0 <= value <= MAX_COUNTER:
        raise BudgetError("InvalidCounter")
    return value


def tcp_plan(byte_limit, connection_limit, timeout_ms=TIMEOUT_MS):
    """Describe an offline TCP reservation, never permission to start traffic.

    The payload quota is below TLS/protocol framing. A separate receive reserve
    covers unread kernel buffers for EVERY allowed attempt, including failures;
    it cannot be spent as additional payload. Headers and retransmissions are
    still outside the Rust socket counters, so this is not a complete wire or
    provider-billing bound and cannot make ``require_live_ready`` succeed.
    """
    if not 1 <= integer(byte_limit) <= TCP_MAX_BYTES:
        raise BudgetError("InvalidTcpByteLimit")
    if not 1 <= integer(connection_limit) <= TCP_MAX_CONNECTIONS:
        raise BudgetError("InvalidTcpConnectionLimit")
    if not 1 <= integer(timeout_ms) <= TIMEOUT_MS:
        raise BudgetError("InvalidTcpTimeout")
    return {"byteLimit": byte_limit, "connectionLimit": connection_limit,
            "receiveReservation": connection_limit * TCP_RECEIVE_RESERVATION,
            "timeoutMs": timeout_ms}


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
        self.windows = None
        self.commit_uncertain = False

    def __enter__(self):
        if self.lock:
            raise BudgetError("LedgerAlreadyLocked")
        # Re-entering must reload the durable ledger rather than use any data
        # left in memory by a previous session or an interrupted commit.
        self.data = None
        self.initialized = False
        self.commit_uncertain = False
        if os.name not in {"posix", "nt"}:
            raise BudgetError("PrivateStorageAdapterRequired")
        if any(p.is_symlink() or (p.exists() and getattr(p.lstat(), "st_file_attributes", 0) & 0x400)
               for p in [self.root, *self.root.parents]):
            raise BudgetError("PrivateDirectoryRequired")
        if any((p / ".git").exists() for p in [self.root, *self.root.parents]):
            raise BudgetError("OutsideRepositoryRequired")
        try:
            if os.name == "nt":
                if not re.fullmatch(r"[A-Za-z]:", self.root.drive) or ":" in str(self.root)[2:]:
                    raise BudgetError("PrivateLocalDirectoryRequired")
                self.windows = _WindowsStorage()
                self.windows.prepare(self.root)
                fd = self.windows.open(self.root / "traffic-budget.lock", exclusive=True)
            else:
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                info = self.root.stat()
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise BudgetError("PrivateDirectoryRequired")
                fd = os.open(self.root / "traffic-budget.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            self.lock = os.fdopen(fd, "r+b")
            if os.name == "posix":
                import fcntl
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
                fd = self.windows.open(self.path) if self.windows else os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "r", encoding="utf-8") as stream:
                    info = os.fstat(stream.fileno())
                    if (not stat.S_ISREG(info.st_mode) or info.st_size > 65536
                            or (not self.windows and (stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid()))):
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
            self.__exit__()
            raise

    def __exit__(self, *unused):
        if self.lock:
            self.lock.close()
            self.lock = None
        if self.windows:
            self.windows.close()
            self.windows = None

    def _validate(self):
        d = self.data
        keys = {"schema", "task", "baseline", "provider", "localUpload", "localDownload",
                "attempts", "sequence", "reservations"}
        if not isinstance(d, dict) or set(d) != keys or type(d.get("schema")) is not int or d["schema"] not in (1, 2) or d["task"] != TASK:
            raise BudgetError("InvalidTaskLedger")
        for key in ("localUpload", "localDownload", "attempts", "sequence"):
            integer(d.get(key))
        for key in ("baseline", "provider"):
            s = d.get(key)
            if s is not None:
                if not isinstance(s, dict) or set(s) - {"upload", "download", "total", "expire"}:
                    raise BudgetError("InvalidBillingSnapshot")
                # Validate JSON types before the header parser can coerce a
                # numeric string while leaving it unchanged in the snapshot.
                for counter in s.values():
                    integer(counter)
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
            fields = {"node", "held", "sent", "received"}
            if not re.fullmatch(r"[1-9][0-9]{0,11}", key) or not isinstance(r, dict) or set(r) not in (fields, fields | {"tcp"}):
                raise BudgetError("InvalidReservations")
            if type(r["node"]) is not int or not 1 <= r["node"] <= 100000:
                raise BudgetError("InvalidNodeOrdinal")
            if r["node"] in seen_nodes or int(key) > d["sequence"]:
                raise BudgetError("InvalidReservations")
            seen_nodes.add(r["node"])
            integer(r["held"])
            integer(r["sent"])
            integer(r["received"])
            reserved = r["held"] + r["sent"] + r["received"]
            if "tcp" in r:
                plan = r["tcp"]
                if (d["schema"] != 2 or not isinstance(plan, dict)
                        or set(plan) != {"byteLimit", "connectionLimit", "receiveReservation", "timeoutMs"}):
                    raise BudgetError("InvalidTcpReservation")
                integer(plan["receiveReservation"])
                expected = tcp_plan(plan["byteLimit"], plan["connectionLimit"], plan["timeoutMs"])
                if (plan != expected or reserved != plan["byteLimit"] + plan["receiveReservation"]
                        or r["sent"] + r["received"] > plan["byteLimit"]):
                    raise BudgetError("InvalidTcpReservation")
            elif not 1 <= reserved <= MAX_PROBE_RESERVATION:
                raise BudgetError("InvalidReservations")
        if sum(r["sent"] for r in d["reservations"].values()) > d["localUpload"] or sum(r["received"] for r in d["reservations"].values()) > d["localDownload"]:
            raise BudgetError("InvalidLocalTotals")

    def _check_session(self):
        if not self.lock:
            raise BudgetError("LedgerNotLocked")
        if self.commit_uncertain:
            raise BudgetError("LedgerCommitUncertain")

    def _save(self):
        self._check_session()
        temporary = None
        try:
            self._validate()
            fd, temporary = self.windows.temporary(self.root) if self.windows else tempfile.mkstemp(prefix=".budget-", dir=self.root)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                if not self.windows:
                    os.fchmod(stream.fileno(), 0o600)
                json.dump(self.data, stream, separators=(",", ":"), sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            if self.windows:
                self.windows.replace(temporary, self.path)
            else:
                os.replace(temporary, self.path)
                parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(parent)
                finally:
                    os.close(parent)
        except BaseException:
            # A failure can happen either before or after replace. Rolling back
            # memory would pretend to know which bytes reached durable storage.
            # Poison this session instead: it must close and reload under the
            # exclusive lock before it can reserve, settle or report a budget.
            self.commit_uncertain = True
            raise
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except BaseException:
                    self.commit_uncertain = True
                    raise

    def initialize(self, userinfo=None):
        with self.mutex:
            self._check_session()
            if self.data is not None or self.initialized:
                raise BudgetError("TaskAlreadyInitialized")
            snapshot = parse_userinfo(userinfo) if userinfo is not None else None
            # Persist a separate initialization marker BEFORE the ledger. A
            # crash or deletion must stop rather than silently create baseline 0.
            try:
                self.lock.write((TASK + "\n").encode("ascii"))
                self.lock.flush()
                os.fsync(self.lock.fileno())
                self.initialized = True
                self.data = {"schema": 2, "task": TASK, "baseline": snapshot, "provider": snapshot,
                             "localUpload": 0, "localDownload": 0, "attempts": 0, "sequence": 0,
                             "reservations": {}}
                self._save()
            except BaseException:
                self.commit_uncertain = True
                raise

    def observe_provider(self, userinfo):
        with self.mutex:
            self._check_session()
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
            self._check_session()
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
            guarded = None if billed is None else max(billed, local) + held
            state = "BillingUnavailable" if billed is None else policy(billed, local, held, remaining)
            if current is not None and current.get("expire", 0) and current["expire"] <= int(time.time()):
                state = "BillingExpired"
            return {"task": TASK, "policy": state, "baselineUsed": used_start, "latestUsed": used_now,
                    "billingDelta": billed, "providerRemaining": remaining,
                    "guardedBytes": guarded,
                    "remainingAbsoluteBudget": None if guarded is None else max(0, ABSOLUTE - guarded),
                    "remainingStopBudget": None if guarded is None else max(0, STOP - guarded),
                    "localUpload": d["localUpload"], "localDownload": d["localDownload"],
                    "heldBytes": held, "attempts": d["attempts"],
                    "providerStatisticsAuthenticated": False, "wireAccountingAttached": False,
                    "hardCancellationAttached": False, "liveReady": False}

    def reserve_offline(self, node, amount=MAX_PROBE_RESERVATION):
        """Exercise admission without opening a socket. Never an execution grant."""
        if not 1 <= integer(amount) <= MAX_PROBE_RESERVATION:
            raise BudgetError("InvalidReservationSize")
        return self._reserve_offline(node, amount)

    def reserve_tcp_offline(self, node, byte_limit, connection_limit, timeout_ms=TIMEOUT_MS):
        """Persist the exact bounded TCP plan and ALL kernel receive reserves.

        Schema-1 accounting is preserved; adopting the explicit plan upgrades
        only its schema number and new reservation. Neither this method nor a
        successful disk commit provides authenticated billing or a live grant.
        """
        plan = tcp_plan(byte_limit, connection_limit, timeout_ms)
        return self._reserve_offline(node, plan["byteLimit"] + plan["receiveReservation"], plan)

    def _reserve_offline(self, node, amount, plan=None):
        with self.mutex:
            self._check_session()
            if type(node) is not int or not 1 <= node <= 100000:
                raise BudgetError("InvalidNodeOrdinal")
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
            if plan is not None:
                d["schema"] = 2
                d["reservations"][ticket]["tcp"] = plan
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
            if "tcp" in r and r["sent"] + r["received"] + upload + download > r["tcp"]["byteLimit"]:
                raise BudgetError("RequestByteLimit")
            r["held"] -= upload + download
            r["sent"] += upload
            r["received"] += download
            self.data["localUpload"] += upload
            self.data["localDownload"] += download
            self._save()

    def finish_offline(self, ticket, quiescent=False):
        """Simulate settlement; caller assertions are NOT live exit/billing proof."""
        with self.mutex:
            self._check_session()
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
