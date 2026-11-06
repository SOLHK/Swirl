"""Owned OS processes for synthetic private-acceptance supervision.

Windows creates a suspended child atomically in an unnamed, non-inherited Job with
ActiveProcessLimit=1 and no breakaway permission. Settlement needs both a
signaled child handle and ActiveProcesses=0. The Job kills its child on last
handle close. POSIX groups support portable synthetic regression only.
No caller-supplied JSON or `exited=True` can construct an ExitProof.
"""
from __future__ import annotations

import errno
import ntpath
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
            ("IsProcessInJob", w.BOOL, [w.HANDLE, w.HANDLE, c.POINTER(w.BOOL)]),
            ("TerminateJobObject", w.BOOL, [w.HANDLE, w.UINT]),
            ("WaitForSingleObject", w.DWORD, [w.HANDLE, w.DWORD]),
            ("CloseHandle", w.BOOL, [w.HANDLE]),
            ("GetHandleInformation", w.BOOL, [w.HANDLE, pointer]),
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

        self.Accounting, self.ExtendedLimits = Accounting, ExtendedLimits
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

    def verify_member(self, process):
        if not self.handle or not process._handle:
            raise BudgetError("PrivateAtomicJobMembershipFailed")
        member = self.w.BOOL()
        info = self.Accounting()
        if (not self.kernel.IsProcessInJob(process._handle, self.handle, self.c.byref(member))
                or not member.value
                or not self.kernel.QueryInformationJobObject(self.handle, 1, self.c.byref(info), self.c.sizeof(info), None)
                or info.activeProcesses != 1):
            raise BudgetError("PrivateAtomicJobMembershipFailed")

    def resume(self, process):
        thread = process._thread
        try:
            if (not thread or self.kernel.GetProcessIdOfThread(thread) != process.pid
                    or self.kernel.ResumeThread(thread) != 1):
                raise BudgetError("PrivatePrimaryThreadResumeFailed")
        finally:
            process.close_thread()

    def terminate(self):
        if not self.handle or not self.kernel.TerminateJobObject(self.handle, 125):
            raise BudgetError("PrivateJobTerminationFailed")

    def empty(self, process):
        # NULL would query the caller's surrounding Job, not our closed Job.
        if not self.handle or not process._handle:
            raise BudgetError("PrivateJobExitQueryFailed")
        info = self.Accounting()
        if not self.kernel.QueryInformationJobObject(self.handle, 1, self.c.byref(info), self.c.sizeof(info), None):
            raise BudgetError("PrivateJobExitQueryFailed")
        return info.activeProcesses == 0 and self.kernel.WaitForSingleObject(int(process._handle), 0) == 0

    def close(self):
        if getattr(self, "handle", None):
            if not self.kernel.CloseHandle(self.handle):
                raise BudgetError("PrivateJobCloseFailed")
            self.handle = None


def _windows_launch_values(arguments, environment):
    """Prepare explicit Unicode inputs without searching PATH or echoing values."""
    if (not isinstance(arguments, (list, tuple)) or not arguments
            or any(not isinstance(value, str) or "\0" in value for value in arguments)
            or not ntpath.isabs(arguments[0]) or not ntpath.splitdrive(arguments[0])[0]):
        raise BudgetError("PrivateProcessArgumentsRejected")
    command = subprocess.list2cmdline(arguments)
    try:
        if len(command.encode("utf-16-le")) // 2 >= 32767:
            raise BudgetError("PrivateProcessArgumentsRejected")
        if environment is None:
            return arguments[0], command, None
        if (not isinstance(environment, dict)
                or any(not isinstance(key, str) or not key or "=" in key or "\0" in key
                       or not isinstance(value, str) or "\0" in value for key, value in environment.items())
                or len({key.upper() for key in environment}) != len(environment)):
            raise BudgetError("PrivateProcessEnvironmentRejected")
        block = "\0".join(key + "=" + environment[key] for key in sorted(environment, key=str.upper)) + "\0\0"
        block.encode("utf-16-le")
        return arguments[0], command, block
    except UnicodeError:
        raise BudgetError("PrivateProcessUnicodeRejected") from None


class _WindowsProcess:
    """Restricted CreateProcessW owner; never falls back to post-create assignment.

    Only the three child stdio handles are inherited. The private Job is an
    attribute, not an inherited handle, so parent death closes its last handle.
    """

    def __init__(self, arguments, *, job, environment):
        import msvcrt
        c, w, kernel = job.c, job.w, job.kernel
        self.c, self.w, self.kernel = c, w, kernel
        self._handle_lock = threading.RLock()
        self.pid = self._handle = self._thread = self.returncode = None
        self.stdin = self.stdout = self.stderr = None
        application, command, block = _windows_launch_values(arguments, environment)
        pointer = c.c_void_p

        class SecurityAttributes(c.Structure):
            _fields_ = [("length", w.DWORD), ("descriptor", pointer), ("inherit", w.BOOL)]

        class StartupInfo(c.Structure):
            _fields_ = [("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR), ("title", w.LPWSTR),
                        ("x", w.DWORD), ("y", w.DWORD), ("xSize", w.DWORD), ("ySize", w.DWORD),
                        ("xChars", w.DWORD), ("yChars", w.DWORD), ("fill", w.DWORD), ("flags", w.DWORD),
                        ("show", w.WORD), ("reservedSize", w.WORD), ("reservedBytes", c.POINTER(w.BYTE)),
                        ("input", w.HANDLE), ("output", w.HANDLE), ("error", w.HANDLE)]

        class StartupInfoEx(c.Structure):
            _fields_ = [("startup", StartupInfo), ("attributes", pointer)]

        class ProcessInformation(c.Structure):
            _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]

        self.abi = {"pointerSize": c.sizeof(pointer), "startupInfoSize": c.sizeof(StartupInfo),
                    "startupInfoExSize": c.sizeof(StartupInfoEx), "processInformationSize": c.sizeof(ProcessInformation)}
        expected = {8: (104, 112, 24), 4: (68, 72, 16)}.get(c.sizeof(pointer))
        if expected != (c.sizeof(StartupInfo), c.sizeof(StartupInfoEx), c.sizeof(ProcessInformation)):
            raise BudgetError("PrivateProcessAbiRejected")
        for name, result, types in (
            ("CreatePipe", w.BOOL, [c.POINTER(w.HANDLE), c.POINTER(w.HANDLE), c.POINTER(SecurityAttributes), w.DWORD]),
            ("SetHandleInformation", w.BOOL, [w.HANDLE, w.DWORD, w.DWORD]),
            ("InitializeProcThreadAttributeList", w.BOOL, [pointer, w.DWORD, w.DWORD, c.POINTER(c.c_size_t)]),
            ("UpdateProcThreadAttribute", w.BOOL, [pointer, w.DWORD, c.c_size_t, pointer, c.c_size_t, pointer, c.POINTER(c.c_size_t)]),
            ("DeleteProcThreadAttributeList", None, [pointer]),
            ("CreateProcessW", w.BOOL, [w.LPCWSTR, w.LPWSTR, pointer, pointer, w.BOOL, w.DWORD,
                                       pointer, w.LPCWSTR, c.POINTER(StartupInfo), c.POINTER(ProcessInformation)]),
            ("GetExitCodeProcess", w.BOOL, [w.HANDLE, c.POINTER(w.DWORD)]),
            ("TerminateProcess", w.BOOL, [w.HANDLE, w.UINT]),
        ):
            function = getattr(kernel, name)
            function.restype, function.argtypes = result, types

        raw_handles = []
        attributes = None
        info = ProcessInformation()
        try:
            try:
                child_handles, parent_handles = [], []
                security = SecurityAttributes(c.sizeof(SecurityAttributes), None, False)
                for index in range(3):
                    read, write = w.HANDLE(), w.HANDLE()
                    created = kernel.CreatePipe(c.byref(read), c.byref(write), c.byref(security), 0)
                    raw_handles.extend(handle for handle in (read.value, write.value) if handle)
                    if not created or not read.value or not write.value:
                        raise BudgetError("PrivateProcessPipeFailed")
                    child, parent = (read.value, write.value) if index == 0 else (write.value, read.value)
                    if (not kernel.SetHandleInformation(parent, 1, 0)
                            or not kernel.SetHandleInformation(child, 1, 1)):
                        raise BudgetError("PrivateProcessPipeInheritanceFailed")
                    child_handles.append(child)
                    parent_handles.append(parent)
                if job.handle in child_handles or len(set(child_handles)) != 3:
                    raise BudgetError("PrivateProcessHandleListRejected")
                inherited = (w.HANDLE * 3)(*child_handles)
                jobs = (w.HANDLE * 1)(job.handle)
                size = c.c_size_t()
                c.set_last_error(0)
                if (kernel.InitializeProcThreadAttributeList(None, 2, 0, c.byref(size))
                        or c.get_last_error() != 122 or not size.value):
                    raise BudgetError("PrivateProcessAttributeSizeFailed")
                memory = (c.c_size_t * ((size.value + c.sizeof(pointer) - 1) // c.sizeof(pointer)))()
                candidate = c.cast(memory, pointer)
                if not kernel.InitializeProcThreadAttributeList(candidate, 2, 0, c.byref(size)):
                    raise BudgetError("PrivateProcessAttributeInitFailed")
                attributes = candidate
                for attribute, value in ((0x00020002, inherited), (0x0002000D, jobs)):
                    # HANDLE_LIST and JOB_LIST values live through Delete below.
                    if not kernel.UpdateProcThreadAttribute(attributes, 0, attribute, value, c.sizeof(value), None, None):
                        raise BudgetError("PrivateProcessAttributeUpdateFailed")
                startup = StartupInfoEx()
                startup.startup.cb = c.sizeof(startup)
                startup.startup.flags = 0x100  # STARTF_USESTDHANDLES.
                startup.startup.input, startup.startup.output, startup.startup.error = child_handles
                startup.attributes = attributes
                mutable_command = c.create_unicode_buffer(command)
                environment_buffer = None if block is None else c.create_unicode_buffer(block)
                flags = 0x00000004 | 0x08000000 | 0x00080000 | 0x00000400
                # SUSPENDED | NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT | UNICODE_ENVIRONMENT.
                if not kernel.CreateProcessW(application, mutable_command, None, None, True, flags,
                                             environment_buffer, None, c.byref(startup.startup), c.byref(info)):
                    raise BudgetError("PrivateAtomicProcessCreateFailed")
                self._handle, self._thread, self.pid = info.process, info.thread, info.pid
                if not self._handle or not self._thread or not self.pid:
                    raise BudgetError("PrivateProcessIdentityFailed")
                for handle in child_handles:
                    if not kernel.CloseHandle(handle):
                        raise BudgetError("PrivateProcessPipeCloseFailed")
                    raw_handles.remove(handle)
                for name, handle, mode, access in zip(("stdin", "stdout", "stderr"), parent_handles,
                                                     ("wb", "rb", "rb"), (os.O_WRONLY, os.O_RDONLY, os.O_RDONLY)):
                    descriptor = msvcrt.open_osfhandle(handle, access | os.O_BINARY)
                    raw_handles.remove(handle)  # The CRT descriptor now owns it.
                    try:
                        stream = os.fdopen(descriptor, mode, buffering=0)
                    except BaseException:
                        os.close(descriptor)
                        raise
                    setattr(self, name, stream)
            finally:
                if attributes is not None:
                    kernel.DeleteProcThreadAttributeList(attributes)
                failed = False
                for handle in raw_handles:
                    if not kernel.CloseHandle(handle):
                        failed = True
                if failed:
                    raise BudgetError("PrivateProcessPipeCloseFailed")
        except BaseException as error:
            # Outer OwnedProcess has not received this owner yet. A child
            # created before a later wrapping error still needs actual cleanup.
            if not self._handle:
                self._handle = info.process
            if not self._thread:
                self._thread = info.thread
            if self.pid is None:
                self.pid = info.pid
            if self._handle:
                try:
                    job.terminate()
                except BaseException:
                    pass
                try:
                    # Also stop the returned process handle if an unexpected
                    # post-create failure happened before membership validation.
                    self.kill()
                except BaseException:
                    pass
                try:
                    self.wait(timeout=2)
                except BaseException:
                    pass
            for stream in (self.stdin, self.stdout, self.stderr):
                if stream:
                    try:
                        stream.close()
                    except OSError:
                        pass
            try:
                self.close_handles()
            except BudgetError:
                pass
            if isinstance(error, BudgetError):
                raise
            raise BudgetError("PrivateAtomicProcessLaunchFailed") from None

    def poll(self):
        with self._handle_lock:
            if self.returncode is not None:
                return self.returncode
            if not self._handle:
                raise BudgetError("PrivateProcessHandleClosed")
            state = self.kernel.WaitForSingleObject(self._handle, 0)
            if state == 258:  # WAIT_TIMEOUT, not an exit code (259 is a valid exit).
                return None
            code = self.w.DWORD()
            if state != 0 or not self.kernel.GetExitCodeProcess(self._handle, self.c.byref(code)):
                raise BudgetError("PrivateProcessExitQueryFailed")
            self.returncode = code.value
            return self.returncode

    def wait(self, timeout=2):
        stop = time.monotonic() + timeout
        while True:
            code = self.poll()
            if code is not None:
                return code
            if time.monotonic() >= stop:
                raise BudgetError("PrivateProcessWaitFailed")
            # Never leave a pending native wait while another owner closes the
            # handle. poll/kill/close serialize only their short native calls.
            time.sleep(0.005)

    def kill(self):
        with self._handle_lock:
            if self.poll() is None and not self.kernel.TerminateProcess(self._handle, 125):
                raise BudgetError("PrivateProcessTerminationFailed")

    def close_thread(self):
        with self._handle_lock:
            if self._thread:
                if not self.kernel.CloseHandle(self._thread):
                    raise BudgetError("PrivateThreadCloseFailed")
                self._thread = None

    def close_handles(self):
        with self._handle_lock:
            failed = False
            for name in ("_thread", "_handle"):
                handle = getattr(self, name)
                if handle:
                    if self.kernel.CloseHandle(handle):
                        setattr(self, name, None)
                    else:
                        failed = True
            if failed:
                raise BudgetError("PrivateProcessHandleCloseFailed")


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
                    self.process = _WindowsProcess(arguments, job=self.job, environment=environment)
                    self.job.verify_member(self.process)
                else:
                    self.process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE, close_fds=True, env=environment,
                                                    start_new_session=True, bufsize=0)
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
                    try:
                        self.process.close_handles()
                    except BudgetError:
                        pass
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
            if self.job:
                # The same owner mutex protects Job queries and termination.
                # A pending proof cannot race native handle closure here.
                with self._lock:
                    self._close_pipes()
                    try:
                        self.process.close_handles()
                    finally:
                        self.job.close()
            else:
                self._close_pipes()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()
