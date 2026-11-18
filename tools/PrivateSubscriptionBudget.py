"""Persistent offline and supervised-synthetic private acceptance accounting.

This module performs NO networking and accepts NO subscription URL or secret.
The current Swirl probe path has no authoritative wire counter / hard-stop
adapter. ``require_live_ready`` therefore always refuses live execution. A
successful offline reservation is not permission to launch a native probe.
Supervised synthetic reservations are a separately typed domain, executed only
by PrivateSubscriptionSupervisor against its own authenticated loopback peer.

The ledger survives batches, process restarts and interrupted reservations.
Provider billing and local transfer counts remain separate. Admission grants
no overlap credit without attribution evidence: account growth, settled local
counts and outstanding reservations are added conservatively. That upper bound
is not measured traffic or a claim that account growth came from this task.
Byte units are decimal GB, conservatively smaller than GiB. No reset operation
is provided.
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
import hashlib
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
SYNTHETIC_DOMAIN = "synthetic-loopback-v1"
SUPERVISED_PHASES = {"reserved", "prepared", "spawned", "guard_ready", "running", "active", "unresolved", "settled"}
_BILLING_PHASES = {"reconcile_pending", "control_consumed"}
SUPERVISED_WORKLOADS = {"upload_until_stop", "download_until_stop", "stall_runtime_after_connect", "core_probe"}


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

    def validate(self, handle, directory=False, *, allow_unlinked=False):
        c = self.c
        info = self.FileInformation()
        if not self.kernel.GetFileInformationByHandle(handle, c.byref(info)):
            raise BudgetError("PrivateStorageRequired")
        if (info.attributes & 0x400 or bool(info.attributes & 0x10) != directory
                or not directory and info.links not in ((0, 1) if allow_unlinked else (1,))):
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

    def open(self, path, *, create=False, directory=False, exclusive=False, existing_only=False):
        import msvcrt
        c = self.c
        access = 0x20080 if directory else 0xC0020000 if create or exclusive else 0x80020000
        flags = 0x00200000 | (0x02000000 if directory else 0x80000000)
        handle = self.kernel.CreateFileW(str(path), access, 0 if exclusive else 3,
                                        c.byref(self.attributes), 3 if existing_only else 4 if exclusive else 1 if create else 3,
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

    def prepare(self, root, *, existing_only=False):
        if self.kernel.GetDriveTypeW(root.anchor) != 3:  # DRIVE_FIXED
            raise BudgetError("PrivateLocalDirectoryRequired")
        if not existing_only:
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


def validate_guard_receipt(guard, plan, *, initial=False, terminal=True):
    fields = {"byte_limit", "upload", "download", "connection_limit", "connection_attempts",
              "receive_reservation", "timeout_ms", "timed_out", "stopped", "shutdown_failures"}
    if not isinstance(guard, dict) or set(guard) != fields:
        raise BudgetError("InvalidGuardReceipt")
    for key in fields - {"timed_out", "stopped"}:
        integer(guard[key])
    if (type(guard["timed_out"]) is not bool or type(guard["stopped"]) is not bool
            or guard["byte_limit"] != plan["byteLimit"]
            or guard["connection_limit"] != plan["connectionLimit"]
            or guard["receive_reservation"] != plan["receiveReservation"]
            or guard["timeout_ms"] != plan["timeoutMs"]
            or guard["upload"] + guard["download"] > plan["byteLimit"]
            or guard["connection_attempts"] > plan["connectionLimit"]
            or guard["shutdown_failures"] != 0):
        raise BudgetError("InvalidGuardReceipt")
    if initial:
        if any(guard[key] for key in ("upload", "download", "connection_attempts", "timed_out", "stopped")):
            raise BudgetError("NonzeroInitialGuard")
    elif terminal and not guard["stopped"]:
        raise BudgetError("FinalGuardNotStopped")


def _validate_exit_record(value, pid):
    if (not isinstance(value, dict) or set(value) != {"pid", "exitCode", "backend", "processSignaled", "ownedProcessSetEmpty"}
            or type(value["pid"]) is not int or value["pid"] != pid
            or type(value["exitCode"]) is not int or not -(1 << 31) <= value["exitCode"] < (1 << 32)
            or value["backend"] not in {"windows-single-process-job", "posix-synthetic-process-group"}
            or value["processSignaled"] is not True or value["ownedProcessSetEmpty"] is not True):
        raise BudgetError("InvalidStoredExitProof")


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
    # Account growth can be other clients' usage while this task's local bytes
    # are still unreported. Neither equal counts nor a larger billed count
    # proves overlap. Keep both for admission until a future authenticated
    # reconciliation supplies attribution/coverage evidence. This can count
    # reflected local bytes twice, but cannot spend unproven overlap credit.
    guarded = billed + local + held
    if guarded >= ABSOLUTE:
        return "AbsoluteLimit"
    if guarded >= STOP:
        return "MandatoryStop"
    if provider_remaining < RESERVE_PACKAGE + local + held:
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

    def __init__(self, directory, *, existing_only=False):
        if type(existing_only) is not bool:
            raise BudgetError("InvalidLedgerOpenMode")
        self.existing_only = existing_only
        self.root = Path(directory).absolute()
        self.path = self.root / "traffic-budget.json"
        self.lock = None
        self.data = None
        self.mutex = threading.RLock()
        self.initialized = False
        self.windows = None
        self.commit_uncertain = False
        self._billing_session = None

    @staticmethod
    def require_existing(directory):
        """Read-only preflight; the subsequent existing-only open repeats it."""
        root = Path(directory).absolute()
        try:
            if not root.is_dir() or not (root / "traffic-budget.json").is_file() or not (root / "traffic-budget.lock").is_file():
                raise BudgetError("RegisteredLedgerRequired")
        except OSError:
            raise BudgetError("RegisteredLedgerRequired") from None

    def __enter__(self):
        if self.lock:
            raise BudgetError("LedgerAlreadyLocked")
        # Re-entering must reload the durable ledger rather than use any data
        # left in memory by a previous session or an interrupted commit.
        self.data = None
        self.initialized = False
        self.commit_uncertain = False
        # A serialized exit record, a local sidecar, or reopening the same
        # object cannot restore the previous process's registration authority.
        self._billing_session = None
        if self.existing_only:
            self.require_existing(self.root)
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
                self.windows.prepare(self.root, existing_only=self.existing_only)
                fd = self.windows.open(self.root / "traffic-budget.lock", exclusive=True, existing_only=self.existing_only)
            else:
                if not self.existing_only:
                    self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                info = self.root.stat()
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise BudgetError("PrivateDirectoryRequired")
                fd = os.open(self.root / "traffic-budget.lock", os.O_RDWR | os.O_NOFOLLOW |
                             (0 if self.existing_only else os.O_CREAT), 0o600)
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
                    if (not stat.S_ISREG(info.st_mode) or info.st_size > 262144
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
                if self.data["schema"] != 4 and info.st_size > 65536:
                    raise BudgetError("PrivateLedgerRequired")
            if self.existing_only and self.data is None:
                raise BudgetError("RegisteredLedgerRequired")
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *unused):
        if self._billing_session is not None:
            self._billing_session.close()
            self._billing_session = None
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
        if (not isinstance(d, dict) or type(d.get("schema")) is not int
                or d["schema"] not in (1, 2, 3, 4) or d.get("task") != TASK
                or set(d) != (keys | {"domain", "ledgerId", "history", "billing"} if d["schema"] == 4 else
                              keys | {"domain", "ledgerId", "history"} if d["schema"] == 3 else keys)):
            raise BudgetError("InvalidTaskLedger")
        if d["schema"] in (3, 4):
            if (d["domain"] != SYNTHETIC_DOMAIN or not isinstance(d["ledgerId"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", d["ledgerId"])
                    or d["baseline"] is not None or d["provider"] is not None
                    or not isinstance(d["history"], dict)):
                raise BudgetError("InvalidSyntheticLedger")
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
        if not isinstance(d.get("reservations"), dict) or len(d["reservations"]) > (FIRST_ROUND + MAX_CONCURRENT if d["schema"] == 4 else MAX_CONCURRENT):
            raise BudgetError("InvalidReservations")
        control_attempts = 0
        if d["schema"] == 4:
            control_attempts = self._validate_billing()
        if d["attempts"] > FIRST_ROUND or d["sequence"] != d["attempts"] + control_attempts or len(d["reservations"]) > d["sequence"]:
            raise BudgetError("InvalidAttemptCount")
        seen_nodes = set()
        for key, r in d["reservations"].items():
            fields = {"node", "held", "sent", "received"}
            if not re.fullmatch(r"[1-9][0-9]{0,11}", key) or not isinstance(r, dict) or set(r) not in (fields, fields | {"tcp"}):
                raise BudgetError("InvalidReservations")
            is_control = d["schema"] == 4 and r["node"] == 0
            if type(r["node"]) is not int or not (is_control or 1 <= r["node"] <= 100000):
                raise BudgetError("InvalidNodeOrdinal")
            if (not is_control and r["node"] in seen_nodes) or int(key) > d["sequence"]:
                raise BudgetError("InvalidReservations")
            seen_nodes.add(r["node"])
            integer(r["held"])
            integer(r["sent"])
            integer(r["received"])
            if d["schema"] == 4 and (r["sent"] or r["received"]):
                # Both kinds retain their entire escrow until the single
                # typed control consumption or node reconciliation commit.
                raise BudgetError("InvalidBillingReservation")
            reserved = r["held"] + r["sent"] + r["received"]
            if "tcp" in r:
                plan = r["tcp"]
                if (d["schema"] not in (2, 3, 4) or not isinstance(plan, dict)
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
        if d["schema"] in (3, 4):
            self._validate_supervision()

    def _validate_supervision(self):
        d = self.data
        if set(d["history"]) != {str(n) for n in range(1, d["sequence"] + 1)}:
            raise BudgetError("InvalidSupervisedHistory")
        fingerprints = set()
        measured_up = measured_down = 0
        control_up = control_down = control_debit = control_attempts = node_attempts = 0
        exit_sequences = set()
        for ticket, h in d["history"].items():
            fields = {"node", "configFingerprint", "sourceSha", "workerSha256", "buildId", "nonce",
                      "workload", "plan", "planDigest", "phase", "pid", "ownerToken", "outcome", "receipt"}
            if d["schema"] == 4:
                fields.add("billing")
            if not isinstance(h, dict) or set(h) != fields:
                raise BudgetError("InvalidSupervisedHistory")
            for key, size in (("configFingerprint", 64), ("sourceSha", 40), ("workerSha256", 64), ("nonce", 64)):
                if not isinstance(h[key], str) or not re.fullmatch(r"[0-9a-f]{%d}" % size, h[key]):
                    raise BudgetError("InvalidSupervisedIdentity")
            billing = h.get("billing")
            kind = None
            if billing is not None:
                if not isinstance(billing, dict) or billing.get("kind") not in {"control", "node"}:
                    raise BudgetError("InvalidSupervisedBilling")
                kind = billing["kind"]
            is_control = kind == "control"
            if (not isinstance(h["buildId"], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", h["buildId"])
                    or h["phase"] not in (SUPERVISED_PHASES | _BILLING_PHASES if d["schema"] == 4 else SUPERVISED_PHASES)
                    or h["workload"] not in (SUPERVISED_WORKLOADS | {"billing_snapshot"} if is_control else SUPERVISED_WORKLOADS | {"qt_ui_session"})
                    or type(h["node"]) is not int or not (h["node"] == 0 if is_control else 1 <= h["node"] <= 100000)):
                raise BudgetError("InvalidSupervisedHistory")
            if is_control:
                from PrivateSubscriptionBilling import BYTE_LIMIT, CONNECTION_LIMIT, HTTP_RESPONSE_CONTRACT
                control_attempts += 1
                billing_fields = {"kind", "purpose", "parentTicket"}
                if "responseContract" in billing:
                    billing_fields.add("responseContract")
                    if billing["responseContract"] != HTTP_RESPONSE_CONTRACT:
                        raise BudgetError("InvalidSupervisedBilling")
                if (set(billing) != billing_fields
                        or billing["purpose"] not in {"preflight", "reconcile"}
                        or h["phase"] in {"settled", "reconcile_pending"}
                        or (billing["purpose"] == "preflight") != (billing["parentTicket"] is None)
                        or (billing["parentTicket"] is not None and billing["parentTicket"] not in d["history"])
                        or h["workload"] != "billing_snapshot"
                        or h["plan"]["byteLimit"] != BYTE_LIMIT or h["plan"]["connectionLimit"] != CONNECTION_LIMIT):
                    raise BudgetError("InvalidSupervisedBilling")
                if billing["parentTicket"] is not None:
                    parent = d["history"][billing["parentTicket"]]
                    if (int(billing["parentTicket"]) >= int(ticket) or not isinstance(parent.get("billing"), dict)
                            or parent["billing"].get("kind") != "node" or parent["billing"].get("exitSequence") is None):
                        raise BudgetError("InvalidBillingReconciliation")
            else:
                node_attempts += 1
            if kind == "node":
                if (set(billing) != {"kind", "preQuery", "postQuery", "exitSequence", "reconcileError"}
                        or billing["preQuery"] not in d["history"] or int(billing["preQuery"]) >= int(ticket)):
                    raise BudgetError("InvalidSupervisedBilling")
                pre = d["history"][billing["preQuery"]]
                if pre["phase"] != "control_consumed" or pre["receipt"]["observation"] is None:
                    raise BudgetError("InvalidBillingAdmission")
                if billing["reconcileError"] is not None and (not isinstance(billing["reconcileError"], str)
                        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", billing["reconcileError"])):
                    raise BudgetError("InvalidSupervisedBilling")
                if billing["exitSequence"] is not None:
                    sequence = integer(billing["exitSequence"])
                    if not sequence or sequence in exit_sequences:
                        raise BudgetError("InvalidExitCoverageSequence")
                    exit_sequences.add(sequence)
                if h["phase"] in {"reconcile_pending", "settled"} and billing["exitSequence"] is None:
                    raise BudgetError("InvalidExitCoverageSequence")
                if h["phase"] == "settled":
                    post = d["history"].get(billing["postQuery"])
                    if (post is None or int(billing["postQuery"]) <= int(ticket) or post["phase"] != "control_consumed"
                            or post["receipt"]["observation"] is None
                            or post["receipt"]["observation"]["covered_sequence"] < billing["exitSequence"]
                            or post["billing"]["parentTicket"] != ticket):
                        raise BudgetError("InvalidBillingReconciliation")
                elif billing["postQuery"] is not None:
                    raise BudgetError("InvalidBillingReconciliation")
            elif h["phase"] == "reconcile_pending":
                raise BudgetError("InvalidSupervisedBilling")
            if h["configFingerprint"] in fingerprints:
                raise BudgetError("DuplicateConfigurationAttempt")
            fingerprints.add(h["configFingerprint"])
            if h["planDigest"] is not None and (not isinstance(h["planDigest"], str) or not re.fullmatch(r"[0-9a-f]{64}", h["planDigest"])):
                raise BudgetError("InvalidSupervisedPlan")
            plan = h["plan"]
            if (not isinstance(plan, dict) or set(plan) != {"byteLimit", "connectionLimit", "receiveReservation", "timeoutMs"}
                    or plan != tcp_plan(plan["byteLimit"], plan["connectionLimit"], plan["timeoutMs"])):
                raise BudgetError("InvalidSupervisedPlan")
            if h["pid"] is not None and (type(h["pid"]) is not int or not 1 <= h["pid"] <= 0xffffffff):
                raise BudgetError("InvalidSupervisedProcess")
            if h["ownerToken"] is not None and (not isinstance(h["ownerToken"], str) or not re.fullmatch(r"[0-9a-f]{64}", h["ownerToken"])):
                raise BudgetError("InvalidSupervisedProcess")
            if (h["pid"] is None) != (h["ownerToken"] is None):
                raise BudgetError("InvalidSupervisedProcess")
            if h["outcome"] is not None and (not isinstance(h["outcome"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", h["outcome"])):
                raise BudgetError("InvalidSupervisedOutcome")
            if h["phase"] in {"spawned", "guard_ready", "running", "active", "settled", "reconcile_pending", "control_consumed"} and (h["pid"] is None or h["planDigest"] is None):
                raise BudgetError("InvalidSupervisedProcess")
            if h["phase"] == "control_consumed":
                from PrivateSubscriptionBilling import HTTP_RESPONSE_CONTRACT, validate_http_observation, validate_snapshot
                receipt = h["receipt"]
                receipt_fields = {"charge", "upload", "download", "exit", "guard", "guardDigest", "observation"}
                http_contract = is_control and billing.get("responseContract") == HTTP_RESPONSE_CONTRACT
                if http_contract:
                    receipt_fields.add("httpObservation")
                if (not is_control or ticket in d["reservations"] or not isinstance(receipt, dict)
                        or set(receipt) != receipt_fields
                        or receipt["charge"] != plan["byteLimit"] + plan["receiveReservation"]):
                    raise BudgetError("InvalidControlSettlement")
                _validate_exit_record(receipt["exit"], h["pid"])
                if receipt["guard"] is None:
                    if (any(receipt[key] is not None for key in ("upload", "download", "guardDigest", "observation"))
                            or receipt.get("httpObservation") is not None):
                        raise BudgetError("InvalidControlMeasurement")
                else:
                    validate_guard_receipt(receipt["guard"], plan)
                    if (receipt["upload"] != receipt["guard"]["upload"] or receipt["download"] != receipt["guard"]["download"]
                            or receipt["guardDigest"] != hashlib.sha256(json.dumps(receipt["guard"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()):
                        raise BudgetError("InvalidControlMeasurement")
                    control_up += integer(receipt["upload"])
                    control_down += integer(receipt["download"])
                if receipt["observation"] is not None:
                    if http_contract:
                        raise BudgetError("InvalidControlMeasurement")
                    validate_snapshot(receipt["observation"], d["billing"]["registration"])
                    if receipt["observation"]["request_nonce"] != h["nonce"]:
                        raise BudgetError("InvalidControlMeasurement")
                if receipt.get("httpObservation") is not None:
                    validate_http_observation(receipt["httpObservation"])
                    if receipt["httpObservation"]["query_nonce"] != h["nonce"]:
                        raise BudgetError("InvalidControlMeasurement")
                control_debit += integer(receipt["charge"])
            elif h["phase"] in {"settled", "reconcile_pending"}:
                receipt = h["receipt"]
                if ((ticket in d["reservations"]) != (h["phase"] == "reconcile_pending") or not isinstance(receipt, dict)
                        or set(receipt) != {"upload", "download", "exit", "guard", "guardDigest"}
                        or not isinstance(receipt["guardDigest"], str) or not re.fullmatch(r"[0-9a-f]{64}", receipt["guardDigest"])
                        or not isinstance(receipt["exit"], dict)):
                    raise BudgetError("InvalidSupervisedSettlement")
                if h["phase"] == "reconcile_pending" and (d["reservations"][ticket]["node"] != h["node"]
                        or d["reservations"][ticket].get("tcp") != plan):
                    raise BudgetError("InvalidSupervisedReservation")
                _validate_exit_record(receipt["exit"], h["pid"])
                validate_guard_receipt(receipt["guard"], plan)
                if (receipt["upload"] != receipt["guard"]["upload"] or receipt["download"] != receipt["guard"]["download"]
                        or receipt["guardDigest"] != hashlib.sha256(json.dumps(receipt["guard"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()):
                    raise BudgetError("InvalidSupervisedSettlement")
                if h["phase"] == "settled":
                    measured_up += integer(receipt["upload"])
                    measured_down += integer(receipt["download"])
            elif h["receipt"] is not None or ticket not in d["reservations"] or d["reservations"][ticket]["node"] != h["node"]:
                raise BudgetError("InvalidSupervisedReservation")
            elif d["reservations"][ticket].get("tcp") != plan:
                raise BudgetError("InvalidSupervisedPlan")
        if measured_up != d["localUpload"] or measured_down != d["localDownload"]:
            raise BudgetError("InvalidSupervisedTotals")
        if d["schema"] == 4:
            b = d["billing"]
            if (control_attempts != b["controlAttempts"] or node_attempts != d["attempts"]
                    or control_up != b["controlLocalUpload"] or control_down != b["controlLocalDownload"]
                    or control_debit != b["controlDebitedBytes"]
                    or exit_sequences != set(range(1, b["exitSequence"] + 1))
                    or self._active_reservations() > MAX_CONCURRENT):
                raise BudgetError("InvalidBillingTotals")
            observed = [(ticket, h["receipt"]["observation"]) for ticket, h in d["history"].items()
                        if h["phase"] == "control_consumed" and h["receipt"]["observation"] is not None]
            observed.sort(key=lambda entry: int(entry[0]))
            if (b["baselineQuery"] != (observed[0][0] if observed else None)
                    or b["latestQuery"] != (observed[-1][0] if observed else None)):
                raise BudgetError("InvalidBillingHistory")
            for (_, previous), (_, current) in zip(observed, observed[1:]):
                self._check_billing_progress(previous, current)

    def _validate_billing(self):
        from PrivateSubscriptionBilling import DOMAIN, MAX_CONTROL_ATTEMPTS
        b = self.data.get("billing")
        fields = {"schema", "registration", "baselineQuery", "latestQuery", "controlAttempts",
                  "controlDebitedBytes", "controlLocalUpload", "controlLocalDownload", "exitSequence"}
        if not isinstance(b, dict) or set(b) != fields or type(b["schema"]) is not int or b["schema"] != 1:
            raise BudgetError("InvalidSyntheticBillingState")
        registration = b["registration"]
        fields = {"schema", "domain", "authority_id", "account_id", "period_id", "session_id", "ledger_id", "path_digest"}
        if (not isinstance(registration, dict) or set(registration) != fields
                or type(registration["schema"]) is not int or registration["schema"] != 1
                or registration["domain"] != DOMAIN or registration["ledger_id"] != self.data["ledgerId"]):
            raise BudgetError("InvalidSyntheticBillingRegistration")
        for key in fields - {"schema", "domain"}:
            if not isinstance(registration[key], str) or not re.fullmatch(r"[0-9a-f]{64}", registration[key]):
                raise BudgetError("InvalidSyntheticBillingRegistration")
        for key in ("controlAttempts", "controlDebitedBytes", "controlLocalUpload", "controlLocalDownload", "exitSequence"):
            integer(b[key])
        if b["controlAttempts"] > MAX_CONTROL_ATTEMPTS or b["exitSequence"] > FIRST_ROUND:
            raise BudgetError("InvalidSyntheticBillingState")
        for key in ("baselineQuery", "latestQuery"):
            if b[key] is not None and (not isinstance(b[key], str) or not re.fullmatch(r"[1-9][0-9]{0,11}", b[key])):
                raise BudgetError("InvalidSyntheticBillingState")
        if (b["baselineQuery"] is None) != (b["latestQuery"] is None):
            raise BudgetError("InvalidSyntheticBillingState")
        return b["controlAttempts"]

    @staticmethod
    def _check_billing_progress(previous, current):
        if previous is not None and (current["revision"] <= previous["revision"]
                or current["total"] != previous["total"]
                or any(current[key] < previous[key] for key in ("upload", "download", "covered_sequence"))):
            raise BudgetError("SyntheticBillingCounterRegression")

    def _billing_snapshots(self):
        b = self.data["billing"]
        def snapshot(key):
            ticket = b[key]
            if ticket is None:
                return None
            h = self.data["history"].get(ticket)
            if not isinstance(h, dict) or h["phase"] != "control_consumed" or not isinstance(h["receipt"], dict):
                raise BudgetError("InvalidBillingHistory")
            return h["receipt"]["observation"]
        return snapshot("baselineQuery"), snapshot("latestQuery")

    def _active_reservations(self):
        if self.data["schema"] != 4:
            return len(self.data["reservations"])
        # Exit-confirmed node holds still consume budget but no longer occupy
        # a process slot. This permits its own post-exit control query when
        # three nodes have all exited with pending billing reconciliation.
        return sum(self.data["history"][ticket]["phase"] != "reconcile_pending"
                   for ticket in self.data["reservations"])

    def _require_billing_session(self, session=None):
        from PrivateSubscriptionBilling import BillingSession
        with self.mutex:
            session = self._billing_session if session is None else session
            if not isinstance(session, BillingSession) or self.data is None or self.data["schema"] != 4:
                raise BudgetError("SyntheticBillingSessionRequired")
            session.require(self)
            return session

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
            encoded = json.dumps(self.data, separators=(",", ":"), sort_keys=True)
            if len(encoded.encode("utf-8")) > (262144 if self.data["schema"] == 4 else 65536):
                raise BudgetError("PrivateLedgerSizeLimit")
            fd, temporary = self.windows.temporary(self.root) if self.windows else tempfile.mkstemp(prefix=".budget-", dir=self.root)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                if not self.windows:
                    os.fchmod(stream.fileno(), 0o600)
                stream.write(encoded)
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
            if self._billing_session is not None:
                self._billing_session._refresh_checkpoint()
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
            if self.data is not None and self.data["schema"] in (3, 4):
                raise BudgetError("SyntheticProviderObservationForbidden")
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
            if d["schema"] == 4 and self._billing_session is not None:
                self._require_billing_session()
            held = sum(r["held"] for r in d["reservations"].values())
            local = d["localUpload"] + d["localDownload"]
            baseline, current = d["baseline"], d["provider"]
            used_start = None if baseline is None else baseline["upload"] + baseline["download"]
            used_now = None if current is None else current["upload"] + current["download"]
            billed = None if current is None else used_now - used_start
            remaining = None if current is None else current["total"] - used_now
            synthetic = d["schema"] in (3, 4)
            synthetic_billed = synthetic_remaining = None
            control_debit = 0
            if d["schema"] == 4:
                b_start, b_now = self._billing_snapshots()
                if b_now is not None:
                    synthetic_billed = b_now["upload"] + b_now["download"] - b_start["upload"] - b_start["download"]
                    synthetic_remaining = b_now["total"] - b_now["upload"] - b_now["download"]
                control_debit = d["billing"]["controlDebitedBytes"]
            guarded = (synthetic_billed or 0) + local + control_debit + held if synthetic else None if billed is None else billed + local + held
            state = policy(synthetic_billed or 0, local + control_debit, held,
                           synthetic_remaining if synthetic_remaining is not None else MAX_COUNTER) if synthetic else "BillingUnavailable" if billed is None else policy(billed, local, held, remaining)
            if current is not None and current.get("expire", 0) and current["expire"] <= int(time.time()):
                state = "BillingExpired"
            result = {"task": TASK, "policy": state, "baselineUsed": used_start, "latestUsed": used_now,
                    "billingDelta": billed, "providerRemaining": remaining,
                    "guardedBytes": guarded,
                    "remainingAbsoluteBudget": None if guarded is None else max(0, ABSOLUTE - guarded),
                    "remainingStopBudget": None if guarded is None else max(0, STOP - guarded),
                    "localUpload": d["localUpload"], "localDownload": d["localDownload"],
                    "heldBytes": held, "attempts": d["attempts"],
                    "providerStatisticsAuthenticated": False, "wireAccountingAttached": False,
                    "hardCancellationAttached": False, "liveReady": False,
                    "accountingDomain": SYNTHETIC_DOMAIN if synthetic else "offline-unverified",
                    "localTotalsScope": "confirmed-settled-socket-counts" if synthetic else "offline-simulated-counts",
                    "unresolvedReservations": len(d["reservations"])}
            if d["schema"] == 4:
                b = d["billing"]
                result["syntheticBilling"] = {"domain": b["registration"]["domain"],
                    "accountDelta": synthetic_billed, "providerRemaining": synthetic_remaining,
                    "controlDebitedBytes": control_debit, "controlMeasuredUpload": b["controlLocalUpload"],
                    "controlMeasuredDownload": b["controlLocalDownload"], "controlAttempts": b["controlAttempts"],
                    "controlMeasurementsUnknown": sum(h["phase"] == "control_consumed" and h["receipt"]["guard"] is None
                                                      for h in d["history"].values()),
                    "pendingReconciliation": sum(h["phase"] == "reconcile_pending" for h in d["history"].values()),
                    "activeProcessSlots": self._active_reservations(),
                    "currentSessionRegistered": self._billing_session is not None and not self._billing_session.closed,
                    "externalHistoryAnchor": False, "controlDebitIsMeasuredTraffic": False,
                    "scope": "synthetic account model; no official provider statistics"}
            return result

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

    def _reserve_offline(self, node, amount, plan=None, execution=None):
        with self.mutex:
            self._check_session()
            if self.data is not None and (self.data["schema"] in (3, 4)) != (execution is not None):
                raise BudgetError("AccountingDomainMismatch")
            if self.data is not None and self.data["schema"] == 4:
                self._require_billing_session()
                if execution is None or execution.get("billing", {}).get("kind") != "node":
                    raise BudgetError("BillingAdmissionRequired")
            if type(node) is not int or not 1 <= node <= 100000:
                raise BudgetError("InvalidNodeOrdinal")
            state = self.summary()
            if state["policy"] != "WithinNormalTarget":
                raise BudgetError(state["policy"])
            d = self.data
            if any(r["node"] == node for r in d["reservations"].values()):
                raise BudgetError("NodeAlreadyReserved")
            if self._active_reservations() >= MAX_CONCURRENT:
                raise BudgetError("ConcurrencyLimit")
            if d["attempts"] >= FIRST_ROUND:
                raise BudgetError("FirstRoundComplete")
            model = state.get("syntheticBilling", {})
            predicted = policy(state["billingDelta"] if execution is None else model.get("accountDelta") or 0,
                               state["localUpload"] + state["localDownload"] + model.get("controlDebitedBytes", 0),
                               state["heldBytes"] + amount, state["providerRemaining"] if execution is None else
                               model.get("providerRemaining") if model.get("providerRemaining") is not None else MAX_COUNTER)
            if predicted != "WithinNormalTarget":
                raise BudgetError(predicted)
            d["attempts"] += 1
            d["sequence"] += 1
            ticket = str(d["sequence"])
            d["reservations"][ticket] = {"node": node, "held": amount, "sent": 0, "received": 0}
            if plan is not None:
                d["schema"] = max(2, d["schema"])
                d["reservations"][ticket]["tcp"] = plan
            if execution is not None:
                d["history"][ticket] = execution
            self._save()
            return ticket

    def account_offline(self, ticket, upload=0, download=0):
        """Debit a simulated bounded transfer before I/O, with no automatic refund.

        Production integration needs transport/OS byte counts including failed
        attempts. HTTP body size must never be used as provider billing here.
        """
        with self.mutex:
            self._check_session()
            if self.data is not None and self.data["schema"] in (3, 4):
                raise BudgetError("AccountingDomainMismatch")
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
            if self.data is not None and self.data["schema"] in (3, 4):
                raise BudgetError("AccountingDomainMismatch")
            if not quiescent:
                raise BudgetError("UnreleasedRequests")
            if self.data is None or str(ticket) not in self.data["reservations"]:
                raise BudgetError("UnknownReservation")
            del self.data["reservations"][str(ticket)]
            self._save()

    def initialize_synthetic(self):
        """Create a NEW synthetic domain. Never migrate/relabel an existing ledger.

        Provider counters stay unknown, not a fabricated zero billing baseline.
        This uses the same durable file, lock and limits as offline accounting.
        """
        with self.mutex:
            self._check_session()
            if self.data is not None or self.initialized:
                raise BudgetError("TaskAlreadyInitialized")
            try:
                self.lock.write((TASK + "\n").encode("ascii"))
                self.lock.flush()
                os.fsync(self.lock.fileno())
                self.initialized = True
                self.data = {"schema": 3, "task": TASK, "baseline": None, "provider": None,
                             "localUpload": 0, "localDownload": 0, "attempts": 0, "sequence": 0,
                             "reservations": {}, "domain": SYNTHETIC_DOMAIN,
                             "ledgerId": os.urandom(32).hex(), "history": {}}
                self._save()
            except BaseException:
                self.commit_uncertain = True
                raise

    def require_synthetic(self):
        self._check_session()
        if self.data is None or self.data["schema"] not in (3, 4) or self.data["domain"] != SYNTHETIC_DOMAIN:
            raise BudgetError("SyntheticLedgerRequired")
        if self.data["schema"] == 4:
            self._require_billing_session()

    def reserve_supervised(self, node, byte_limit, connection_limit, timeout_ms, *,
                           config_fingerprint, source_sha, worker_sha256, build_id, nonce, workload):
        with self.mutex:
            self.require_synthetic()
            if self.data["schema"] == 4:
                raise BudgetError("BillingAdmissionRequired")
            if any(h["configFingerprint"] == config_fingerprint for h in self.data["history"].values()):
                raise BudgetError("ConfigurationAlreadyAttempted")
            plan = tcp_plan(byte_limit, connection_limit, timeout_ms)
            execution = {"node": node, "configFingerprint": config_fingerprint, "sourceSha": source_sha,
                         "workerSha256": worker_sha256, "buildId": build_id, "nonce": nonce,
                         "workload": workload, "plan": plan.copy(), "planDigest": None, "phase": "reserved", "pid": None,
                         "ownerToken": None, "outcome": None, "receipt": None}
            return self._reserve_offline(node, plan["byteLimit"] + plan["receiveReservation"], plan, execution)

    def bind_supervised_grant(self, ticket, plan_digest):
        with self.mutex:
            self.require_synthetic()
            history = self.data["history"].get(str(ticket))
            if history is None or history["phase"] != "reserved":
                raise BudgetError("SupervisedPhaseMismatch")
            history["planDigest"], history["phase"] = plan_digest, "prepared"
            self._save()

    def advance_supervised(self, ticket, phase, *, process=None):
        with self.mutex:
            self.require_synthetic()
            history = self.data["history"].get(str(ticket))
            transitions = {"spawned": "prepared", "guard_ready": "spawned", "running": "guard_ready", "active": "running"}
            if history is None or transitions.get(phase) != history["phase"]:
                raise BudgetError("SupervisedPhaseMismatch")
            if phase == "spawned":
                from PrivateSubscriptionProcess import OwnedProcess
                if not isinstance(process, OwnedProcess):
                    raise BudgetError("OwnedProcessRequired")
                history["pid"], history["ownerToken"] = process.pid, process.owner_token
            history["phase"] = phase
            self._save()

    def retain_supervised(self, ticket, outcome):
        """Unknown bytes/exit remain a full hold; reopening never changes this."""
        with self.mutex:
            self.require_synthetic()
            history = self.data["history"].get(str(ticket))
            if history is None or history["phase"] in {"settled", "control_consumed"}:
                raise BudgetError("SupervisedPhaseMismatch")
            if history["phase"] == "reconcile_pending":
                history["billing"]["reconcileError"] = outcome
            else:
                history["phase"], history["outcome"] = "unresolved", outcome
            self._save()

    def settle_synthetic(self, ticket, guard, exit_proof, outcome):
        """Accept actual socket counts only after a locally issued OS exit proof.

        This releases SYNTHETIC holds only. Live provider/wire settlement remains
        deliberately unavailable; a child JSON `quiescent` flag is never proof.
        """
        from PrivateSubscriptionProcess import ExitProof
        with self.mutex:
            self.require_synthetic()
            if self.data["schema"] == 4:
                raise BudgetError("BillingReconciliationRequired")
            ticket = str(ticket)
            history = self.data["history"].get(ticket)
            if history is None or history["phase"] != "active":
                raise BudgetError("SupervisedPhaseMismatch")
            if not isinstance(exit_proof, ExitProof) or not exit_proof.matches(history["pid"], history["ownerToken"]):
                raise BudgetError("ProcessExitProofRequired")
            reservation = self.data["reservations"][ticket]
            plan = reservation["tcp"]
            validate_guard_receipt(guard, plan)
            upload, download = integer(guard.get("upload")), integer(guard.get("download"))
            self.data["localUpload"] += upload
            self.data["localDownload"] += download
            history["phase"], history["outcome"] = "settled", outcome
            history["receipt"] = {"upload": upload, "download": download, "exit": exit_proof.record(), "guard": guard.copy(),
                                  "guardDigest": hashlib.sha256(json.dumps(guard, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
            del self.data["reservations"][ticket]
            self._save()

    def register_synthetic_billing(self, session):
        """Bind an existing synthetic ledger for this live Python session only.

        This does not open or initialize an original ledger, infer an account,
        or provide restart/whole-snapshot rollback protection. Schema4 without
        the original in-memory issuer is readable but never admits or settles.
        """
        from PrivateSubscriptionBilling import BillingSession, _SESSION_ISSUER
        with self.mutex:
            self._check_session()
            if (not isinstance(session, BillingSession) or session._issuer is not _SESSION_ISSUER
                    or session.ledger is not self or session.closed):
                raise BudgetError("SyntheticBillingSessionRequired")
            if self.data is not None and self.data["schema"] == 4:
                raise BudgetError("OriginalBillingSessionUnavailable")
            self.require_synthetic()
            if self._billing_session is not None:
                raise BudgetError("SyntheticBillingAlreadyRegistered")
            self.data["schema"] = 4
            self.data["billing"] = {"schema": 1, "registration": session.registration(),
                "baselineQuery": None, "latestQuery": None, "controlAttempts": 0,
                "controlDebitedBytes": 0, "controlLocalUpload": 0, "controlLocalDownload": 0,
                "exitSequence": 0}
            for history in self.data["history"].values():
                history["billing"] = None
            self._billing_session = session
            self._save()

    @staticmethod
    def _execution_record(node, plan, config_fingerprint, source_sha, worker_sha256, build_id, nonce, workload, billing):
        return {"node": node, "configFingerprint": config_fingerprint, "sourceSha": source_sha,
                "workerSha256": worker_sha256, "buildId": build_id, "nonce": nonce,
                "workload": workload, "plan": plan.copy(), "planDigest": None, "phase": "reserved", "pid": None,
                "ownerToken": None, "outcome": None, "receipt": None, "billing": billing}

    def reserve_billing_control(self, session, *, purpose, parent_ticket=None, timeout_ms=2000,
                                response_contract="synthetic_qa_v1",
                                config_fingerprint, source_sha, worker_sha256, build_id, nonce):
        from PrivateSubscriptionBilling import (BYTE_LIMIT, CONNECTION_LIMIT, MAX_CONTROL_ATTEMPTS, WORKLOAD,
                                                HTTP_RESPONSE_CONTRACT, RESPONSE_CONTRACTS)
        with self.mutex:
            self._check_session()
            self._require_billing_session(session)
            if not isinstance(response_contract, str) or response_contract not in RESPONSE_CONTRACTS:
                raise BudgetError("BillingResponseContractRejected")
            if purpose not in {"preflight", "reconcile"} or (purpose == "preflight") != (parent_ticket is None):
                raise BudgetError("InvalidBillingControlPurpose")
            if not 100 <= integer(timeout_ms) <= TIMEOUT_MS:
                raise BudgetError("InvalidBillingControlTimeout")
            if parent_ticket is not None:
                parent_ticket = str(parent_ticket)
                h = self.data["history"].get(parent_ticket)
                if h is None or h["phase"] != "reconcile_pending":
                    raise BudgetError("BillingReconciliationRequired")
            if self._active_reservations() >= MAX_CONCURRENT:
                raise BudgetError("ConcurrencyLimit")
            if self.data["billing"]["controlAttempts"] >= MAX_CONTROL_ATTEMPTS:
                raise BudgetError("BillingControlLimit")
            if any(h["configFingerprint"] == config_fingerprint for h in self.data["history"].values()):
                raise BudgetError("ConfigurationAlreadyAttempted")
            plan = tcp_plan(BYTE_LIMIT, CONNECTION_LIMIT, timeout_ms)
            amount = plan["byteLimit"] + plan["receiveReservation"]
            state = self.summary()
            model = state["syntheticBilling"]
            predicted = policy(model["accountDelta"] or 0,
                state["localUpload"] + state["localDownload"] + model["controlDebitedBytes"],
                state["heldBytes"] + amount,
                model["providerRemaining"] if model["providerRemaining"] is not None else MAX_COUNTER)
            if predicted != "WithinNormalTarget":
                raise BudgetError(predicted)
            self.data["sequence"] += 1
            self.data["billing"]["controlAttempts"] += 1
            ticket = str(self.data["sequence"])
            self.data["reservations"][ticket] = {"node": 0, "held": amount, "sent": 0, "received": 0, "tcp": plan.copy()}
            billing = {"kind": "control", "purpose": purpose, "parentTicket": parent_ticket}
            if response_contract == HTTP_RESPONSE_CONTRACT:
                billing["responseContract"] = response_contract
            self.data["history"][ticket] = self._execution_record(0, plan, config_fingerprint, source_sha,
                worker_sha256, build_id, nonce, WORKLOAD, billing)
            self._save()
            return ticket

    def check_billing_observation(self, session, ticket, observation):
        from PrivateSubscriptionBilling import BillingObservation
        self._check_session()
        self._require_billing_session(session)
        if not isinstance(observation, BillingObservation) or observation._query.ticket != str(ticket):
            raise BudgetError("SyntheticBillingObservationRequired")
        snapshot = observation.require(session)
        history = self.data["history"].get(str(ticket))
        if (history is None or history.get("billing", {}).get("kind") != "control"
                or "responseContract" in history["billing"] or snapshot["request_nonce"] != history["nonce"]):
            raise BudgetError("SyntheticBillingObservationMismatch")
        _, previous = self._billing_snapshots()
        self._check_billing_progress(previous, snapshot)
        return snapshot

    def check_http_billing_observation(self, session, ticket, observation):
        from PrivateSubscriptionBilling import HttpBillingObservation, HTTP_RESPONSE_CONTRACT
        self._check_session()
        self._require_billing_session(session)
        if not isinstance(observation, HttpBillingObservation) or observation._query.ticket != str(ticket):
            raise BudgetError("HttpBillingObservationRequired")
        snapshot = observation.require(session)
        history = self.data["history"].get(str(ticket))
        if (history is None or history.get("billing", {}).get("kind") != "control"
                or history["billing"].get("responseContract") != HTTP_RESPONSE_CONTRACT
                or snapshot["query_nonce"] != history["nonce"]):
            raise BudgetError("HttpBillingObservationMismatch")
        return snapshot

    def consume_billing_control(self, session, ticket, guard, exit_proof, outcome, observation=None, *, http_observation=None):
        """Spend ALL control escrow; never recursively refund it from its reply.

        Unknown socket measurements stay null. Confirmed local counts are
        separately recorded, not charged twice over the conservative full debit.
        Unconfirmed child/cleanup never reaches this method from Supervisor.
        """
        from PrivateSubscriptionBilling import HTTP_RESPONSE_CONTRACT
        from PrivateSubscriptionProcess import ExitProof
        with self.mutex:
            self._check_session()
            self._require_billing_session(session)
            ticket = str(ticket)
            history = self.data["history"].get(ticket)
            if (history is None or history.get("billing", {}).get("kind") != "control"
                    or history["phase"] not in {"spawned", "guard_ready", "running", "active", "unresolved"}):
                raise BudgetError("SupervisedPhaseMismatch")
            if not isinstance(exit_proof, ExitProof) or not exit_proof.matches(history["pid"], history["ownerToken"]):
                raise BudgetError("ProcessExitProofRequired")
            reservation = self.data["reservations"][ticket]
            upload = download = guard_digest = None
            if guard is not None:
                validate_guard_receipt(guard, reservation["tcp"])
                upload, download = guard["upload"], guard["download"]
                guard_digest = hashlib.sha256(json.dumps(guard, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            elif observation is not None or http_observation is not None:
                raise BudgetError("BillingTransportReceiptRequired")
            http_contract = history["billing"].get("responseContract") == HTTP_RESPONSE_CONTRACT
            if (http_contract and observation is not None) or (not http_contract and http_observation is not None):
                raise BudgetError("BillingResponseContractRejected")
            snapshot = None if observation is None else self.check_billing_observation(session, ticket, observation)
            http_snapshot = (None if http_observation is None
                             else self.check_http_billing_observation(session, ticket, http_observation))
            charge = reservation["held"]
            b = self.data["billing"]
            b["controlDebitedBytes"] += charge
            if guard is not None:
                b["controlLocalUpload"] += upload
                b["controlLocalDownload"] += download
            if snapshot is not None:
                if b["baselineQuery"] is None:
                    b["baselineQuery"] = ticket
                b["latestQuery"] = ticket
            history["phase"], history["outcome"] = "control_consumed", outcome
            history["receipt"] = {"charge": charge, "upload": upload, "download": download,
                "exit": exit_proof.record(), "guard": None if guard is None else guard.copy(),
                "guardDigest": guard_digest, "observation": snapshot}
            if http_contract:
                history["receipt"]["httpObservation"] = http_snapshot
            del self.data["reservations"][ticket]
            self._save()

    def reserve_billing_node(self, session, observation, node, byte_limit, connection_limit, timeout_ms, *,
                             config_fingerprint, source_sha, worker_sha256, build_id, nonce, workload):
        from PrivateSubscriptionBilling import BillingObservation
        with self.mutex:
            self._check_session()
            self._require_billing_session(session)
            if not isinstance(observation, BillingObservation):
                raise BudgetError("SyntheticBillingObservationRequired")
            snapshot = observation.require(session)
            query = observation._query.ticket
            control = self.data["history"].get(query)
            if (control is None or control["phase"] != "control_consumed"
                    or control["billing"]["purpose"] != "preflight"
                    or control["receipt"]["observation"] != snapshot or self.data["billing"]["latestQuery"] != query):
                raise BudgetError("BillingAdmissionRequired")
            if any(isinstance(h.get("billing"), dict) and h["billing"].get("preQuery") == query
                   for h in self.data["history"].values()):
                raise BudgetError("BillingObservationAlreadyAdmitted")
            if any(h["configFingerprint"] == config_fingerprint for h in self.data["history"].values()):
                raise BudgetError("ConfigurationAlreadyAttempted")
            if workload not in SUPERVISED_WORKLOADS | {"qt_ui_session"}:
                raise BudgetError("SyntheticWorkloadRequired")
            plan = tcp_plan(byte_limit, connection_limit, timeout_ms)
            execution = self._execution_record(node, plan, config_fingerprint, source_sha, worker_sha256, build_id, nonce, workload,
                {"kind": "node", "preQuery": query, "postQuery": None, "exitSequence": None, "reconcileError": None})
            return self._reserve_offline(node, plan["byteLimit"] + plan["receiveReservation"], plan, execution)

    def record_billing_exit(self, session, ticket, guard, exit_proof, outcome):
        """Persist real exit/cleanup evidence without releasing any node hold."""
        from PrivateSubscriptionProcess import ExitProof
        with self.mutex:
            self._check_session()
            self._require_billing_session(session)
            ticket = str(ticket)
            history = self.data["history"].get(ticket)
            if history is None or history["phase"] != "active" or history.get("billing", {}).get("kind") != "node":
                raise BudgetError("SupervisedPhaseMismatch")
            if not isinstance(exit_proof, ExitProof) or not exit_proof.matches(history["pid"], history["ownerToken"]):
                raise BudgetError("ProcessExitProofRequired")
            validate_guard_receipt(guard, self.data["reservations"][ticket]["tcp"])
            self.data["billing"]["exitSequence"] += 1
            sequence = self.data["billing"]["exitSequence"]
            history["billing"]["exitSequence"] = sequence
            history["phase"], history["outcome"] = "reconcile_pending", outcome
            history["receipt"] = {"upload": guard["upload"], "download": guard["download"],
                "exit": exit_proof.record(), "guard": guard.copy(),
                "guardDigest": hashlib.sha256(json.dumps(guard, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
            self._save()
            session.mark_exit(ticket, exit_proof, sequence)

    def settle_billing_node(self, session, ticket, observation, exit_proof):
        from PrivateSubscriptionBilling import BillingObservation
        from PrivateSubscriptionProcess import ExitProof
        with self.mutex:
            self._check_session()
            self._require_billing_session(session)
            ticket = str(ticket)
            history = self.data["history"].get(ticket)
            if history is None or history["phase"] != "reconcile_pending":
                raise BudgetError("SupervisedPhaseMismatch")
            if not isinstance(exit_proof, ExitProof) or not exit_proof.matches(history["pid"], history["ownerToken"]):
                raise BudgetError("ProcessExitProofRequired")
            session.require_exit(ticket, exit_proof)
            if not isinstance(observation, BillingObservation):
                raise BudgetError("SyntheticBillingObservationRequired")
            snapshot = observation.require(session)
            query = observation._query.ticket
            control = self.data["history"].get(query)
            if (control is None or control["phase"] != "control_consumed"
                    or control["billing"]["purpose"] != "reconcile" or control["billing"]["parentTicket"] != ticket
                    or control["receipt"]["observation"] != snapshot or self.data["billing"]["latestQuery"] != query):
                raise BudgetError("BillingReconciliationRequired")
            if snapshot["covered_sequence"] < history["billing"]["exitSequence"]:
                raise BudgetError("SyntheticBillingCoveragePending")
            self.data["localUpload"] += history["receipt"]["upload"]
            self.data["localDownload"] += history["receipt"]["download"]
            history["phase"] = "settled"
            history["billing"]["postQuery"] = query
            history["billing"]["reconcileError"] = None
            del self.data["reservations"][ticket]
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
