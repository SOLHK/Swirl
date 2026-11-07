"""Private native-watchdog evidence for the owned synthetic Windows child.

The anonymous, non-executable mapping is duplicated only into the suspended
child's held process handle. It is neither named nor inherited. The child writes
a fixed record before its hard stop without filesystem or pipe I/O. This is a
stop-origin receipt, never budget authorization or proof of process retirement.
"""
from __future__ import annotations

import hashlib
import re
import struct

from PrivateSubscriptionBudget import BudgetError


SIZE = 256
MAGIC = b"SWIRL-STOP-V1\0\0\0"
STARTUP_NS = 20_000_000_000
REQUEST_NS = 8_000_000_000
ABSOLUTE_NS = 28_000_000_000


def initial_record(pid, manifest, ready_qpc, frequency):
    if (type(pid) is not int or not 0 < pid < 2**32
            or not re.fullmatch(r"[0-9a-f]{64}", manifest.get("nonce", ""))
            or not re.fullmatch(r"[0-9a-f]{40}", manifest.get("sourceSha", ""))
            or any(type(value) is not int or not 0 < value < 2**63
                   for value in (ready_qpc, frequency))):
        raise ValueError("NativeWatchdogIdentityRejected")
    data = bytearray(SIZE)
    data[:16] = MAGIC
    struct.pack_into("<II", data, 16, 1, pid)
    data[24:88] = manifest["nonce"].encode("ascii")
    data[88:128] = manifest["sourceSha"].encode("ascii")
    struct.pack_into("<Q", data, 168, ready_qpc)
    struct.pack_into("<Q", data, 184, frequency)
    return bytes(data)


def verify_record(data, *, initial, exit_code, exited_qpc):
    """Decode only after the held process is signaled and its Job is empty."""
    if (type(data) is not bytes or len(data) != SIZE or len(initial) != SIZE
            or initial[:16] != MAGIC or data[:128] != initial[:128]
            or data[168:176] != initial[168:176] or data[184:192] != initial[184:192]
            or any(data[200:])):
        raise ValueError("NativeWatchdogReceiptIdentityMismatch")
    started, absolute, request, deadline, fired, ready, fired_qpc, frequency = struct.unpack_from("<8Q", data, 128)
    phase, committed = struct.unpack_from("<II", data, 192)
    if committed not in (0, 1) or type(exited_qpc) is not int or exited_qpc < ready:
        raise ValueError("NativeWatchdogReceiptInvalid")
    if not committed:
        # The parent may terminate while the child is filling this record.
        # An incomplete record never supplies a native timeout assertion.
        if exit_code == 124:
            raise ValueError("NativeWatchdogExitUnproven")
        return {"triggered": False, "uncommittedRecord": bool(any(data[128:168]) or fired_qpc or phase)}
    if (exit_code not in (124, 125) or started <= 0 or absolute != started + ABSOLUTE_NS
            or phase != (2 if request else 1)
            or request and not started <= request < started + STARTUP_NS
            or deadline != (min(absolute, request + REQUEST_NS) if request else started + STARTUP_NS)
            or not deadline <= fired < 2**63 or not ready <= fired_qpc <= exited_qpc
            or frequency <= 0):
        raise ValueError("NativeWatchdogDeadlineUnproven")
    return {"triggered": True, "phase": "requests" if request else "startup",
            "deadlineMs": 8000 if request else 20000,
            "absoluteLimitMs": 28000, "deadlineOverrunNs": str(fired - deadline),
            "startedNs": str(started), "requestStartedNs": str(request),
            "deadlineNs": str(deadline), "triggeredNs": str(fired),
            "parentReadyQpc": str(ready), "triggeredQpc": str(fired_qpc),
            "parentExitQpc": str(exited_qpc), "qpcFrequency": str(frequency),
            "receiptSha256": hashlib.sha256(data).hexdigest()}


class NativeWatchdogReceipt:
    """One mapping for one actual _WindowsJob/_WindowsProcess pair."""

    def __init__(self, job, manifest):
        self.job, self.manifest = job, manifest
        self.c, self.w, self.kernel = job.c, job.w, job.kernel
        self.handle = self.view = self.initial = self.pid = None
        c, w, kernel = self.c, self.w, self.kernel
        for name, result, arguments in (
            ("CreateFileMappingW", w.HANDLE, [w.HANDLE, c.c_void_p, w.DWORD, w.DWORD, w.DWORD, w.LPCWSTR]),
            ("MapViewOfFile", c.c_void_p, [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, c.c_size_t]),
            ("UnmapViewOfFile", w.BOOL, [c.c_void_p]),
            ("GetCurrentProcess", w.HANDLE, []),
            ("DuplicateHandle", w.BOOL, [w.HANDLE, w.HANDLE, w.HANDLE, c.POINTER(w.HANDLE), w.DWORD, w.BOOL, w.DWORD]),
            ("QueryPerformanceCounter", w.BOOL, [c.POINTER(c.c_longlong)]),
            ("QueryPerformanceFrequency", w.BOOL, [c.POINTER(c.c_longlong)]),
        ):
            function = getattr(kernel, name)
            function.restype, function.argtypes = result, arguments
        try:
            frequency = c.c_longlong()
            if not kernel.QueryPerformanceFrequency(c.byref(frequency)) or frequency.value <= 0:
                raise BudgetError("NativeWatchdogClockUnavailable")
            self.frequency = frequency.value
            # INVALID_HANDLE_VALUE + no name: paging-file backing, no disk file,
            # no public name and no executable page permissions.
            self.handle = kernel.CreateFileMappingW(c.c_void_p(-1), None, 0x04, 0, SIZE, None)
            if not self.handle:
                raise BudgetError("NativeWatchdogMappingFailed")
            self.view = kernel.MapViewOfFile(self.handle, 0x02, 0, 0, SIZE)
            if not self.view:
                raise BudgetError("NativeWatchdogMappingFailed")
        except BaseException:
            self.close()
            raise

    def counter(self):
        value = self.c.c_longlong()
        if not self.kernel.QueryPerformanceCounter(self.c.byref(value)) or value.value <= 0:
            raise BudgetError("NativeWatchdogClockUnavailable")
        return value.value

    def duplicate_to(self, process):
        if self.initial is not None or not self.view or not process._thread:
            raise BudgetError("NativeWatchdogSingleSuspendedChildRequired")
        self.job.verify_member(process)
        if process.poll() is not None:
            raise BudgetError("NativeWatchdogLiveChildRequired")
        self.pid = process.pid
        self.initial = initial_record(process.pid, self.manifest, self.counter(), self.frequency)
        self.c.memmove(self.view, self.initial, SIZE)
        remote = self.w.HANDLE()
        # The held process handle identifies the exact child. No PID lookup,
        # inherited handle list, named object or generic Job policy is changed.
        with process._handle_lock:
            if not self.kernel.DuplicateHandle(self.kernel.GetCurrentProcess(), self.handle,
                    process._handle, self.c.byref(remote), 0x02, False, 0) or not remote.value:
                raise BudgetError("NativeWatchdogDuplicateFailed")
        return struct.pack("<Q", remote.value)

    def read_after_exit(self, process):
        if (self.initial is None or process.pid != self.pid or process.poll() is None
                or not self.job.empty(process)):
            raise BudgetError("NativeWatchdogRetirementRequired")
        return verify_record(self.c.string_at(self.view, SIZE), initial=self.initial,
                             exit_code=process.returncode, exited_qpc=self.counter())

    def close(self):
        failed = False
        if self.view:
            if not self.kernel.UnmapViewOfFile(self.view):
                failed = True
            self.view = None
        if self.handle:
            if not self.kernel.CloseHandle(self.handle):
                failed = True
            self.handle = None
        if failed:
            raise BudgetError("NativeWatchdogMappingCloseFailed")
