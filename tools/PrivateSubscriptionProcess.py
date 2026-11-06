"""Owned OS processes for synthetic private-acceptance supervision.

Windows starts suspended in an unnamed, non-inherited kill-on-close Job with
ActiveProcessLimit=1 and no breakaway permission. Settlement needs both a
signaled child handle and ActiveProcesses=0. POSIX process groups are provided
only for the Linux synthetic regression, not as Windows containment evidence.
No caller-supplied JSON or `exited=True` can construct an ExitProof.
"""
from __future__ import annotations

import errno
import os
import secrets
import signal
import subprocess
import threading
import time

from PrivateSubscriptionBudget import BudgetError

_PROOF_ISSUER = object()


class ExitProof:
    __slots__ = ("_pid", "_token", "_code", "_backend", "_seal")

    def __init__(self, issuer, pid, token, code, backend):
        if issuer is not _PROOF_ISSUER:
            raise BudgetError("ProcessExitProofRequired")
        self._pid, self._token, self._code, self._backend = pid, token, code, backend
        self._seal = _PROOF_ISSUER

    def matches(self, pid, token):
        return self._seal is _PROOF_ISSUER and self._pid == pid and secrets.compare_digest(self._token, token or "")

    def record(self):
        return {"pid": self._pid, "exitCode": self._code, "backend": self._backend,
                "processSignaled": True, "ownedProcessSetEmpty": True}


class _WindowsJob:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        self.c, self.w = c, w
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        pointer = c.c_void_p
        for name, result, arguments in (
            ("CreateJobObjectW", w.HANDLE, [pointer, w.LPCWSTR]),
            ("SetInformationJobObject", w.BOOL, [w.HANDLE, c.c_int, pointer, w.DWORD]),
            ("QueryInformationJobObject", w.BOOL, [w.HANDLE, c.c_int, pointer, w.DWORD, pointer]),
            ("AssignProcessToJobObject", w.BOOL, [w.HANDLE, w.HANDLE]),
            ("TerminateJobObject", w.BOOL, [w.HANDLE, w.UINT]),
            ("WaitForSingleObject", w.DWORD, [w.HANDLE, w.DWORD]),
            ("CloseHandle", w.BOOL, [w.HANDLE]),
            ("GetHandleInformation", w.BOOL, [w.HANDLE, pointer]),
            ("CreateToolhelp32Snapshot", w.HANDLE, [w.DWORD, w.DWORD]),
            ("Thread32First", w.BOOL, [w.HANDLE, pointer]),
            ("Thread32Next", w.BOOL, [w.HANDLE, pointer]),
            ("OpenThread", w.HANDLE, [w.DWORD, w.BOOL, w.DWORD]),
            ("GetProcessIdOfThread", w.DWORD, [w.HANDLE]),
            ("ResumeThread", w.DWORD, [w.HANDLE]),
        ):
            function = getattr(self.kernel, name)
            function.restype, function.argtypes = result, arguments

        class BasicLimits(c.Structure):
            _fields_ = [("processTime", c.c_longlong), ("jobTime", c.c_longlong),
                        ("flags", w.DWORD), ("minimumWorkingSet", c.c_size_t),
                        ("maximumWorkingSet", c.c_size_t), ("activeProcesses", w.DWORD),
                        ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class IoCounters(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in ("readOps", "writeOps", "otherOps", "readBytes", "writeBytes", "otherBytes")]

        class ExtendedLimits(c.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                        ("processMemory", c.c_size_t), ("jobMemory", c.c_size_t),
                        ("peakProcessMemory", c.c_size_t), ("peakJobMemory", c.c_size_t)]

        class Accounting(c.Structure):
            _fields_ = [("userTime", c.c_longlong), ("kernelTime", c.c_longlong),
                        ("periodUserTime", c.c_longlong), ("periodKernelTime", c.c_longlong),
                        ("pageFaults", w.DWORD), ("totalProcesses", w.DWORD),
                        ("activeProcesses", w.DWORD), ("terminatedProcesses", w.DWORD)]

        class ThreadEntry(c.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("threadId", w.DWORD),
                        ("processId", w.DWORD), ("basePriority", w.LONG),
                        ("deltaPriority", w.LONG), ("flags", w.DWORD)]

        self.Accounting, self.ThreadEntry = Accounting, ThreadEntry
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise BudgetError("PrivateJobCreateFailed")
        try:
            flags = w.DWORD()
            if not self.kernel.GetHandleInformation(self.handle, c.byref(flags)) or flags.value & 1:
                raise BudgetError("PrivateJobInheritanceRejected")
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE | ACTIVE_PROCESS.
            limits.basic.activeProcesses = 1
            if not self.kernel.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)):
                raise BudgetError("PrivateJobLimitsFailed")
        except BaseException:
            self.close()
            raise

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise BudgetError("PrivateJobAssignmentFailed")

    def resume(self, process):
        c = self.c
        snapshot = self.kernel.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD.
        if snapshot == c.c_void_p(-1).value:
            raise BudgetError("PrivatePrimaryThreadUnavailable")
        try:
            entry = self.ThreadEntry()
            entry.size = c.sizeof(entry)
            found = []
            success = self.kernel.Thread32First(snapshot, c.byref(entry))
            while success:
                if entry.processId == process.pid:
                    found.append(entry.threadId)
                entry.size = c.sizeof(entry)
                success = self.kernel.Thread32Next(snapshot, c.byref(entry))
            if c.get_last_error() != 18:  # ERROR_NO_MORE_FILES, not a partial enumeration.
                raise BudgetError("PrivateThreadEnumerationFailed")
            # The suspended, newly-created process must have one primary thread.
            if len(found) != 1:
                raise BudgetError("PrivatePrimaryThreadUnavailable")
            thread = self.kernel.OpenThread(0x0800 | 0x0002, False, found[0])
            if not thread:
                raise BudgetError("PrivatePrimaryThreadUnavailable")
            try:
                if self.kernel.GetProcessIdOfThread(thread) != process.pid or self.kernel.ResumeThread(thread) != 1:
                    raise BudgetError("PrivatePrimaryThreadResumeFailed")
            finally:
                self.kernel.CloseHandle(thread)
        finally:
            self.kernel.CloseHandle(snapshot)

    def terminate(self):
        if not self.kernel.TerminateJobObject(self.handle, 125):
            raise BudgetError("PrivateJobTerminationFailed")

    def empty(self, process):
        info = self.Accounting()
        if not self.kernel.QueryInformationJobObject(self.handle, 1, self.c.byref(info), self.c.sizeof(info), None):
            raise BudgetError("PrivateJobExitQueryFailed")
        return info.activeProcesses == 0 and self.kernel.WaitForSingleObject(int(process._handle), 0) == 0

    def close(self):
        if getattr(self, "handle", None):
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class OwnedProcess:
    """Exactly one owned child with an independent parent deadline thread.

    A deadline starts before spawn and is never renewed by ACK/START/progress.
    Failure to prove exit returns no proof. Cleanup errors cannot refund holds.
    """

    def __init__(self, arguments, *, deadline, environment=None):
        self.owner_token = secrets.token_hex(32)
        self.deadline = deadline
        self.process = None
        self.job = None
        self._proof = None
        self._posix_kill_sent = False
        self._lock = threading.RLock()
        self._done = threading.Event()
        self.timed_out = False
        self.stop_error = None
        if os.name not in {"nt", "posix"}:
            raise BudgetError("ProcessContainmentUnavailable")
        if not 0 < deadline - time.monotonic() <= 8.0:
            raise BudgetError("InvalidProcessDeadline")
        try:
            with self._lock:
                if os.name == "nt":
                    self.job = _WindowsJob()
                self.process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE, close_fds=True, env=environment,
                                                creationflags=0x00000004 | 0x08000000 if os.name == "nt" else 0,
                                                start_new_session=os.name == "posix", bufsize=0)
                if self.job:
                    self.job.assign(self.process)
                if time.monotonic() >= deadline:
                    raise BudgetError("ParentDeadlineBeforeResume")
                if self.job:
                    self.job.resume(self.process)
            self._watchdog = threading.Thread(target=self._deadline_watchdog, name="Swirl private parent deadline", daemon=True)
            self._watchdog.start()
        except BaseException as error:
            if self.process is not None:
                try:
                    self.process.kill()
                    self.process.wait(timeout=2)
                except BaseException:
                    pass
                self._close_pipes()
            if self.job:
                self.job.close()
            if isinstance(error, BudgetError):
                raise
            raise BudgetError("OwnedProcessLaunchFailed") from None

    @property
    def pid(self):
        return self.process.pid

    @property
    def stdin(self):
        return self.process.stdin

    @property
    def stdout(self):
        return self.process.stdout

    @property
    def stderr(self):
        return self.process.stderr

    def _deadline_watchdog(self):
        if not self._done.wait(max(0, self.deadline - time.monotonic())):
            self.timed_out = True
            try:
                self.terminate_and_wait()
            except BudgetError as error:
                self.stop_error = str(error)

    def _empty(self):
        if self.job:
            return self.job.empty(self.process)
        try:
            os.killpg(self.pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def _prove(self, timeout):
        stop = time.monotonic() + timeout
        while True:
            # Reaping and kill decisions share this short critical section.
            # A reaped POSIX pid is never blindly targeted by a later killpg.
            with self._lock:
                if self._proof is not None:
                    return self._proof
                code = self.process.poll()
                if code is not None and self._empty():
                    self._proof = ExitProof(_PROOF_ISSUER, self.pid, self.owner_token, code,
                                            "windows-single-process-job" if self.job else "posix-synthetic-process-group")
                    self._done.set()
                    return self._proof
            if time.monotonic() >= stop:
                raise BudgetError("ChildExitUnconfirmed" if code is None else "OwnedProcessSetNotEmpty")
            time.sleep(0.005)

    def wait(self, timeout=2):
        with self._lock:
            if self._proof is not None:
                return self._proof
        # Do not hold the termination mutex while waiting: the independent
        # deadline thread must still be able to kill a child that never exits.
        return self._prove(timeout)

    def terminate_and_wait(self, timeout=2):
        with self._lock:
            if self._proof is not None:
                return self._proof
            if self.job:
                self.job.terminate()
            else:
                if self.process.poll() is None and not self._posix_kill_sent:
                    try:
                        os.killpg(self.pid, signal.SIGKILL)
                    except OSError as error:
                        if error.errno not in {errno.EPERM, errno.ESRCH}:
                            raise BudgetError("PosixGroupSignalFailed") from None
                        # Darwin can report EPERM for an exited, unreaped group.
                        # Neither errno proves exit: the bounded poll + absent-
                        # group check below must still succeed. A denied signal
                        # remains retryable if the child is actually alive.
                    else:
                        # Concurrent deadline/cleanup callers share one signal
                        # and the same proof, rather than re-killing a zombie.
                        self._posix_kill_sent = True
        return self._prove(timeout)

    def _close_pipes(self):
        for stream in (self.stdin, self.stdout, self.stderr):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass

    def close(self):
        try:
            if self._proof is None:
                self.terminate_and_wait()
        finally:
            self._done.set()
            watchdog = getattr(self, "_watchdog", None)
            if watchdog and watchdog is not threading.current_thread():
                watchdog.join(timeout=2)
            self._close_pipes()
            if self.job:
                self.job.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()
