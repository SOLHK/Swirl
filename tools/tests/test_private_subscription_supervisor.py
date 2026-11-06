"""Real synthetic OS-child/transport acceptance; never real provider traffic."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import contextlib
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import PrivateSubscriptionBudget as budget
import PrivateSubscriptionProcess as process
import PrivateSubscriptionSupervisor as supervisor

REPORTS = []
IDENTITY = None


def reservation(ledger, node=1, workload="upload_until_stop"):
    return ledger.reserve_supervised(node, 65536, 1, 2000,
        config_fingerprint=hashlib.sha256(str(node).encode()).hexdigest(), source_sha="1" * 40,
        worker_sha256="2" * 64, build_id="synthetic-test", nonce=secrets.token_hex(32), workload=workload)


class SyntheticLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "budget"

    def tearDown(self):
        self.temp.cleanup()

    def test_domain_never_relabels_or_invents_provider_baseline(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            report = ledger.summary()
            self.assertIsNone(report["baselineUsed"])
            self.assertIsNone(report["billingDelta"])
            self.assertEqual(report["accountingDomain"], budget.SYNTHETIC_DOMAIN)
            for action in (lambda: ledger.initialize(), lambda: ledger.observe_provider("upload=0;download=0;total=100000000000"),
                           lambda: ledger.reserve_offline(1), ledger.require_live_ready):
                with self.assertRaises(budget.BudgetError):
                    action()
        other = self.path.with_name("prior-offline-history")
        with budget.Ledger(other) as ledger:
            ledger.initialize("upload=100;download=200;total=100000000000")
            old = ledger.path.read_bytes()
            with self.assertRaises(budget.BudgetError):
                ledger.initialize_synthetic()
            with self.assertRaisesRegex(budget.BudgetError, "SyntheticLedgerRequired"):
                reservation(ledger)
            self.assertEqual(ledger.path.read_bytes(), old)

    def test_residual_hold_identity_and_fingerprint_survive_reopen(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            ticket = reservation(ledger)
            ledger.bind_supervised_grant(ticket, "a" * 64)
            ledger.retain_supervised(ticket, "ChildExitUnconfirmed")
            before = ledger.summary()
            history = ledger.data["history"].copy()
        with budget.Ledger(self.path) as ledger:
            self.assertEqual(ledger.summary(), before)
            self.assertEqual(ledger.data["history"], history)
            self.assertEqual(before["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)
            self.assertEqual(before["localTotalsScope"], "confirmed-settled-socket-counts")
            with self.assertRaisesRegex(budget.BudgetError, "ConfigurationAlreadyAttempted"):
                reservation(ledger)
            with self.assertRaisesRegex(budget.BudgetError, "AccountingDomainMismatch"):
                ledger.finish_offline(ticket, quiescent=True)

    def test_only_three_full_reservations_can_compete(self):
        with budget.Ledger(self.path) as ledger:
            ledger.initialize_synthetic()
            def attempt(node):
                try:
                    return reservation(ledger, node)
                except budget.BudgetError as error:
                    return str(error)
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(attempt, range(1, 9)))
            self.assertEqual(results.count("ConcurrencyLimit"), 5)
            self.assertEqual(ledger.summary()["heldBytes"], 3 * (65536 + budget.TCP_RECEIVE_RESERVATION))

    def test_guard_and_exit_json_cannot_fake_proof(self):
        plan = budget.tcp_plan(512, 1, 1000)
        guard = {"byte_limit": 512, "upload": 10, "download": 11, "connection_limit": 1,
                 "connection_attempts": 1, "receive_reservation": 1048576, "timeout_ms": 1000,
                 "timed_out": False, "stopped": True, "shutdown_failures": 0}
        budget.validate_guard_receipt(guard, plan)
        for key, value in (("upload", True), ("download", 1.0), ("connection_attempts", 2),
                           ("receive_reservation", 0), ("timeout_ms", 1001), ("stopped", 1),
                           ("shutdown_failures", 1)):
            with self.subTest(key=key), self.assertRaises(budget.BudgetError):
                budget.validate_guard_receipt({**guard, key: value}, plan)
        with self.assertRaisesRegex(budget.BudgetError, "ProcessExitProofRequired"):
            process.ExitProof(None, 1, "a", 0, "windows-single-process-job")

    def test_live_refuses_before_any_path_or_metadata_access(self):
        output = io.StringIO()
        with mock.patch.object(supervisor.WorkerIdentity, "inspect", side_effect=AssertionError("metadata spawned")), \
             mock.patch.object(supervisor, "Ledger", side_effect=AssertionError("ledger accessed")), \
             contextlib.redirect_stdout(output):
            result = supervisor.main(["--live", "--state-dir", str(self.path), "--worker", "PRIVATE_MARKER"])
        self.assertEqual(result, 2)
        self.assertFalse(self.path.exists())
        self.assertNotIn("PRIVATE_MARKER", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["error"], "AuthenticatedBillingAndWireGuardRequired")

    def test_argument_errors_never_echo_values_or_touch_paths(self):
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(supervisor.WorkerIdentity, "inspect", side_effect=AssertionError("metadata spawned")), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = supervisor.main(["--state-dir", str(self.path), "--worker", "PRIVATE_MARKER",
                                      "--worker-sha256", "0" * 64,
                                      "--expected-source", "0" * 40, "--workload", "PRIVATE_MARKER"])
        self.assertEqual(result, 2)
        self.assertFalse(self.path.exists())
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(json.loads(output.getvalue()), {"error": "SupervisorArgumentsRejected", "liveReady": False})


class OwnedProcessTests(unittest.TestCase):
    def test_windows_launch_requires_fully_qualified_unicode_arguments(self):
        for arguments in ([], ["worker.exe"], [r"C:worker.exe"], [r"\worker.exe"],
                          [r"C:\worker.exe", "PRIVATE_MARKER\0tail"], [r"C:\worker.exe", b"bytes"],
                          [r"C:\worker.exe", "x" * 32767]):
            with self.subTest(argument_count=len(arguments)), self.assertRaises(budget.BudgetError) as failure:
                process._windows_launch_values(arguments, None)
            self.assertNotIn("PRIVATE_MARKER", str(failure.exception))
        application, command, block = process._windows_launch_values([r"C:\QA tools\worker.exe", ""], None)
        self.assertEqual(application, r"C:\QA tools\worker.exe")
        self.assertEqual(command, '"C:\\QA tools\\worker.exe" ""')
        self.assertIsNone(block)

    def test_windows_environment_rejects_ambiguous_or_embedded_null_fields(self):
        for environment in ({"": "value"}, {"BAD=KEY": "value"}, {"KEY": "PRIVATE_MARKER\0tail"},
                            {"Path": "first", "PATH": "second"}, {"KEY": 1}):
            with self.subTest(keys=list(environment)), self.assertRaises(budget.BudgetError) as failure:
                process._windows_launch_values([r"C:\worker.exe"], environment)
            self.assertNotIn("PRIVATE_MARKER", str(failure.exception))
        _, _, block = process._windows_launch_values([r"C:\worker.exe"], {"z": "last", "Alpha": "回环"})
        self.assertEqual(block, "Alpha=回环\0z=last\0\0")

    def test_real_child_deadline_cannot_be_renewed_or_asserted_by_child(self):
        started = time.monotonic()
        with process.OwnedProcess([sys.executable, "-c", "import time;time.sleep(30)"], deadline=started + 0.4) as child:
            proof = child.wait(timeout=2)
            self.assertTrue(child.timed_out)
            self.assertTrue(proof.matches(child.pid, child.owner_token))
            self.assertFalse(proof.matches(child.pid, "0" * 64))
            self.assertLess(time.monotonic() - started, 2)
            self.assertTrue(proof.record()["ownedProcessSetEmpty"])

    def test_too_large_deadline_never_spawns(self):
        with mock.patch.object(process.subprocess, "Popen", side_effect=AssertionError("spawned")):
            with self.assertRaisesRegex(budget.BudgetError, "InvalidProcessDeadline"):
                process.OwnedProcess([sys.executable], deadline=time.monotonic() + 8.1)

    @unittest.skipUnless(os.name == "posix", "POSIX process-group lifecycle")
    def test_signal_eperm_requires_real_reaping_and_absent_group(self):
        child = process.OwnedProcess([sys.executable, "-c", "import time;time.sleep(30)"],
                                     deadline=time.monotonic() + 4)
        killpg = os.killpg
        signals = []
        def exiting_group(group, sig):
            result = killpg(group, sig)
            if group == child.pid and sig == signal.SIGKILL:
                signals.append(sig)
                # Model Darwin's exited-but-unreaped group errno. The child
                # really dies; poll and the subsequent group query stay real.
                raise PermissionError(errno.EPERM, "Injected exiting group")
            return result
        try:
            with mock.patch.object(process.os, "killpg", exiting_group):
                proof = child.terminate_and_wait(timeout=1)
            self.assertEqual(signals, [signal.SIGKILL])
            self.assertEqual(proof.record()["exitCode"], -signal.SIGKILL)
            self.assertTrue(proof.record()["ownedProcessSetEmpty"])
            with self.assertRaises(ProcessLookupError):
                killpg(child.pid, 0)
        finally:
            child.close()

    @unittest.skipUnless(os.name == "posix", "POSIX process-group lifecycle")
    def test_denied_signal_to_live_child_never_proves_exit_and_can_retry(self):
        child = process.OwnedProcess([sys.executable, "-c", "import time;time.sleep(30)"],
                                     deadline=time.monotonic() + 4)
        killpg = os.killpg
        def denied_signal(group, sig):
            if group == child.pid and sig == signal.SIGKILL:
                raise PermissionError(errno.EPERM, "Injected live group denial")
            return killpg(group, sig)
        try:
            with mock.patch.object(process.os, "killpg", denied_signal):
                with self.assertRaisesRegex(budget.BudgetError, "ChildExitUnconfirmed"):
                    child.terminate_and_wait(timeout=0.05)
                self.assertIsNone(child._proof)
                self.assertIsNone(child.process.poll())
            # A denied first signal must not suppress a later real stop.
            proof = child.terminate_and_wait(timeout=1)
            self.assertEqual(proof.record()["exitCode"], -signal.SIGKILL)
        finally:
            child.close()

    @unittest.skipUnless(os.name == "posix", "POSIX process-group lifecycle")
    def test_exited_child_with_denied_group_query_never_proves_empty(self):
        child = process.OwnedProcess([sys.executable, "-c", "import time;time.sleep(30)"],
                                     deadline=time.monotonic() + 4)
        killpg = os.killpg
        def denied_query(group, sig):
            if group == child.pid and sig == 0:
                raise PermissionError(errno.EPERM, "Injected group query denial")
            return killpg(group, sig)
        try:
            with mock.patch.object(process.os, "killpg", denied_query):
                with self.assertRaisesRegex(budget.BudgetError, "OwnedProcessSetNotEmpty"):
                    child.terminate_and_wait(timeout=0.05)
                self.assertIsNone(child._proof)
                self.assertEqual(child.process.returncode, -signal.SIGKILL)
            self.assertTrue(child.wait(timeout=1).record()["ownedProcessSetEmpty"])
        finally:
            child.close()

    @unittest.skipUnless(os.name == "posix", "POSIX process-group lifecycle")
    def test_concurrent_termination_sends_one_successful_group_signal(self):
        child = process.OwnedProcess([sys.executable, "-c", "import time;time.sleep(30)"],
                                     deadline=time.monotonic() + 4)
        killpg, prove = os.killpg, child._prove
        signals = []
        both_terminators = threading.Barrier(2)
        def count_signals(group, sig):
            if group == child.pid and sig == signal.SIGKILL:
                signals.append(sig)
            return killpg(group, sig)
        def wait_for_other_terminator(timeout):
            # Hold the first caller at the proof boundary so the second stop
            # decision runs before the first proof completes. Actual child
            # polling and group-absence checks remain unchanged.
            both_terminators.wait(timeout=2)
            return prove(timeout)
        try:
            with mock.patch.object(process.os, "killpg", count_signals), \
                 mock.patch.object(child, "_prove", wait_for_other_terminator), \
                 ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(child.terminate_and_wait, 1) for _ in range(2)]
                proofs = [future.result(timeout=3) for future in futures]
            self.assertEqual(signals, [signal.SIGKILL])
            self.assertIs(proofs[0], proofs[1])
            self.assertTrue(proofs[0].record()["ownedProcessSetEmpty"])
        finally:
            child.close()

    @unittest.skipUnless(os.name == "nt", "Windows Job active-process limit")
    def test_windows_job_prevents_a_second_process(self):
        command = ("import subprocess,sys\n"
                   "try:\n p=subprocess.Popen([sys.executable,'-c','pass']);p.wait();print('ESCAPED')\n"
                   "except OSError:\n print('DENIED')\n")
        with process.OwnedProcess([sys.executable, "-c", command], deadline=time.monotonic() + 3) as child:
            proof = child.wait(timeout=3)
            self.assertEqual(child.stdout.read(128).strip(), b"DENIED")
            self.assertEqual(proof.record()["exitCode"], 0)
            self.assertEqual(proof.record()["backend"], "windows-single-process-job")

    @unittest.skipUnless(os.name == "nt", "Windows atomic Job creation and real stdio")
    def test_windows_atomic_stdio_unicode_environment_and_exit_259(self):
        code = ("import json,os,sys\n"
                "data=sys.stdin.buffer.read(5)\n"
                "print(json.dumps({'args':sys.argv[1:],'value':os.environ['SWIRL_PRIVATE_TEST_TEXT'],"
                "'input':data.decode('ascii')}))\n"
                "sys.stderr.write('fixture-stderr')\n"
                "sys.exit(259)\n")
        arguments = ['空 格\\end\\"quoted"', ""]
        environment = {**supervisor._environment(), "SWIRL_PRIVATE_TEST_TEXT": "回环值"}
        child = process.OwnedProcess([sys.executable, "-c", code, *arguments],
                                     deadline=time.monotonic() + 4, environment=environment)
        try:
            self.assertEqual(child.stdin.write(b"abcde"), 5)
            child.stdin.close()
            proof = child.wait(timeout=3)
            self.assertEqual(proof.record()["exitCode"], 259)
            self.assertTrue(proof.record()["ownedProcessSetEmpty"])
            self.assertEqual(json.loads(child.stdout.read(4096)),
                             {"args": arguments, "value": "回环值", "input": "abcde"})
            self.assertEqual(child.stderr.read(128), b"fixture-stderr")
            self.assertIsNone(child.process._thread)
            self.assertEqual(child.process.abi, {"pointerSize": 8, "startupInfoSize": 104,
                                                 "startupInfoExSize": 112, "processInformationSize": 24})
            REPORTS.append({"test": self.id(), "scope": "synthetic Windows OS-child fixture only",
                            "atomicJobCreation": True, "abi": child.process.abi, "exit": proof.record()})
        finally:
            child.close()
        child.close()  # Native handle ownership is explicitly idempotent.
        self.assertIsNone(child.process._handle)
        self.assertIsNone(child.process._thread)
        self.assertIsNone(child.job.handle)
        self.assertTrue(all(stream.closed for stream in (child.stdin, child.stdout, child.stderr)))
        for action in (lambda: child.job.verify_member(child.process),
                       lambda: child.job.empty(child.process), child.job.terminate):
            with self.assertRaises(budget.BudgetError):
                action()  # A NULL handle must not query the runner's outer Job.

    @unittest.skipUnless(os.name == "nt", "Windows atomic Job attribute failure")
    def test_windows_atomic_attribute_or_create_failure_never_falls_back(self):
        for stage in ("job_attribute", "create"):
            with self.subTest(stage=stage):
                job = process._WindowsJob()
                c, w, kernel = job.c, job.w, job.kernel
                update = kernel.UpdateProcThreadAttribute
                update.restype = w.BOOL
                update.argtypes = [c.c_void_p, w.DWORD, c.c_size_t, c.c_void_p,
                                   c.c_size_t, c.c_void_p, c.POINTER(c.c_size_t)]
                def update_or_reject(attributes, flags, key, value, size, previous, returned):
                    if stage == "job_attribute" and key == 0x0002000D:
                        return False
                    return update(attributes, flags, key, value, size, previous, returned)
                expected = "PrivateProcessAttributeUpdateFailed" if stage == "job_attribute" else "PrivateAtomicProcessCreateFailed"
                try:
                    with mock.patch.object(process, "_WindowsJob", return_value=job), \
                         mock.patch.object(kernel, "UpdateProcThreadAttribute", side_effect=update_or_reject), \
                         mock.patch.object(kernel, "CreateProcessW", return_value=False) as create, \
                         mock.patch.object(kernel, "AssignProcessToJobObject", side_effect=AssertionError("post-create assignment")) as assign, \
                         mock.patch.object(process.subprocess, "Popen", side_effect=AssertionError("uncontained fallback")) as fallback:
                        with self.assertRaisesRegex(budget.BudgetError, expected):
                            process.OwnedProcess([sys.executable, "-c", "raise SystemExit(0)"],
                                                 deadline=time.monotonic() + 3)
                        self.assertEqual(create.call_count, 0 if stage == "job_attribute" else 1)
                        assign.assert_not_called()
                        fallback.assert_not_called()
                    self.assertIsNone(job.handle)
                finally:
                    job.close()

    @unittest.skipUnless(os.name == "nt", "Windows post-create wrapping failure cleanup")
    def test_windows_post_create_pipe_wrapping_failure_kills_and_closes_child(self):
        job = process._WindowsJob()
        c, w, kernel = job.c, job.w, job.kernel
        create = kernel.CreateProcessW
        create.restype = w.BOOL
        create.argtypes = [w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL, w.DWORD,
                           c.c_void_p, w.LPCWSTR, c.c_void_p, c.c_void_p]
        kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
        observer, initial_wait, original_handles = None, None, []
        def create_and_observe(*arguments):
            nonlocal observer, initial_wait
            result = create(*arguments)
            if result:
                information = arguments[-1]._obj
                original_handles.extend((information.process, information.thread))
                observer = kernel.OpenProcess(0x100000 | 0x0001, False, information.pid)
                if observer:
                    initial_wait = kernel.WaitForSingleObject(observer, 0)
            return result
        try:
            with mock.patch.object(process, "_WindowsJob", return_value=job), \
                 mock.patch.object(kernel, "CreateProcessW", side_effect=create_and_observe), \
                 mock.patch.object(kernel, "ResumeThread", side_effect=AssertionError("resumed incomplete owner")) as resume, \
                 mock.patch.object(process.os, "fdopen", side_effect=OSError("Injected CRT stream wrapping failure")) as wrapping, \
                 mock.patch.object(process.subprocess, "Popen", side_effect=AssertionError("uncontained fallback")) as fallback:
                with self.assertRaisesRegex(budget.BudgetError, "PrivateAtomicProcessLaunchFailed"):
                    process.OwnedProcess([sys.executable, "-c", "import time;time.sleep(30)"],
                                         deadline=time.monotonic() + 3)
                resume.assert_not_called()
                fallback.assert_not_called()
                wrapping.assert_called_once()
            self.assertTrue(observer)
            self.assertEqual(initial_wait, 258)
            self.assertEqual(kernel.WaitForSingleObject(observer, 2000), 0)
            self.assertIsNone(job.handle)
            for handle in original_handles:
                flags = w.DWORD()
                self.assertFalse(kernel.GetHandleInformation(handle, c.byref(flags)))
            REPORTS.append({"test": self.id(), "scope": "synthetic Windows OS-child fixture only",
                            "postCreateWrapFailureChildExitConfirmed": True,
                            "originalProcessAndThreadHandlesClosed": True, "exitProofIssued": False})
        finally:
            if observer:
                if kernel.WaitForSingleObject(observer, 0) == 258:
                    kernel.TerminateProcess(observer, 125)
                    kernel.WaitForSingleObject(observer, 2000)
                kernel.CloseHandle(observer)
            job.close()

    @unittest.skipUnless(os.name == "nt", "Windows atomic Job before primary-thread resume")
    def test_windows_pre_resume_parent_crash_kills_child_and_retains_prepared_hold(self):
        # The observer keeps only a process handle across the parent's death.
        # Keeping any Job handle would suppress its kill-on-last-close policy.
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            ledger_path, ready, marker = directory / "budget", directory / "ready.json", directory / "executed.txt"
            code = ("import hashlib,json,sys,time\nfrom pathlib import Path\nfrom unittest import mock\n"
                    "sys.path.insert(0,sys.argv[1])\n"
                    "from PrivateSubscriptionBudget import Ledger\n"
                    "import PrivateSubscriptionProcess as owned\n"
                    "fixture=\"from pathlib import Path;import sys,time;Path(sys.argv[1]).write_text('executed');time.sleep(30)\"\n"
                    "def pause_at_creation(*arguments):\n"
                    " native_create.restype=pause_at_creation.restype;native_create.argtypes=pause_at_creation.argtypes\n"
                    " result=native_create(*arguments)\n"
                    " if not result:return result\n"
                    " child=arguments[-1]._obj;startup=arguments[-2]._obj\n"
                    " member=job.w.BOOL()\n"
                    " assert arguments[5]&4\n"
                    " assert job.kernel.IsProcessInJob(child.process,job.handle,job.c.byref(member)) and member.value\n"
                    " info=job.Accounting();limits=job.ExtendedLimits()\n"
                    " assert job.kernel.QueryInformationJobObject(job.handle,1,job.c.byref(info),job.c.sizeof(info),None)\n"
                    " assert job.kernel.QueryInformationJobObject(job.handle,9,job.c.byref(limits),job.c.sizeof(limits),None)\n"
                    " assert info.activeProcesses==1 and limits.basic.activeProcesses==1 and limits.basic.flags==0x2008\n"
                    " with Path(sys.argv[3]).open('x',encoding='utf-8') as out:\n"
                    "  json.dump({'pid':child.pid,'inJob':True,'activeProcesses':info.activeProcesses,"
                    "'activeProcessLimit':limits.basic.activeProcesses,'jobFlags':limits.basic.flags,"
                    "'pauseBoundary':'CreateProcessW-success-before-wrapper-ownership',"
                    "'abi':{'pointerSize':job.c.sizeof(job.c.c_void_p),'startupInfoSize':job.c.sizeof(startup),"
                    "'startupInfoExSize':startup.cb,'processInformationSize':job.c.sizeof(child)}},out)\n"
                    " time.sleep(15)\n"
                    " raise RuntimeError('observer did not terminate fixture parent')\n"
                    "with Ledger(sys.argv[2]) as ledger:\n"
                    " ledger.initialize_synthetic()\n"
                    " ticket=ledger.reserve_supervised(1,65536,1,8000,config_fingerprint=hashlib.sha256(fixture.encode()).hexdigest(),"
                    "source_sha='1'*40,worker_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),"
                    "build_id='python-os-fixture',nonce='2'*64,workload='stall_runtime_after_connect')\n"
                    " ledger.bind_supervised_grant(ticket,hashlib.sha256(b'pre-resume-no-grant-fixture').hexdigest())\n"
                    " job=owned._WindowsJob();native_create=job.kernel.CreateProcessW\n"
                    " with mock.patch.object(owned,'_WindowsJob',return_value=job),mock.patch.object(job.kernel,'CreateProcessW',pause_at_creation):\n"
                    "  owned.OwnedProcess([sys.executable,'-c',fixture,sys.argv[4]],deadline=time.monotonic()+8)\n")
            outer = subprocess.Popen([sys.executable, "-c", code, str(TOOLS), str(ledger_path), str(ready), str(marker)],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            handle = None
            try:
                stop, observation = time.monotonic() + 5, None
                while time.monotonic() < stop:
                    try:
                        observation = json.loads(ready.read_text())
                        break
                    except (OSError, ValueError):
                        time.sleep(0.01)
                self.assertIsNotNone(observation)
                self.assertTrue(observation["inJob"])
                self.assertEqual(observation["activeProcesses"], 1)
                self.assertEqual(observation["activeProcessLimit"], 1)
                self.assertEqual(observation["jobFlags"], 0x2008)
                self.assertEqual(observation["pauseBoundary"], "CreateProcessW-success-before-wrapper-ownership")
                import ctypes as c
                from ctypes import wintypes as w
                kernel = c.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
                kernel.WaitForSingleObject.argtypes, kernel.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
                kernel.TerminateProcess.argtypes, kernel.TerminateProcess.restype = [w.HANDLE, w.UINT], w.BOOL
                kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
                handle = kernel.OpenProcess(0x100000 | 0x1000 | 0x0001, False, observation["pid"])
                self.assertTrue(handle)
                self.assertEqual(kernel.WaitForSingleObject(handle, 0), 258)
                self.assertFalse(marker.exists())
                outer.kill()
                outer.wait(timeout=2)
                self.assertEqual(kernel.WaitForSingleObject(handle, 2000), 0)
                self.assertFalse(marker.exists())
                with budget.Ledger(ledger_path) as ledger:
                    self.assertEqual(ledger.summary()["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)
                    self.assertEqual(ledger.summary()["attempts"], 1)
                    history = ledger.data["history"]["1"]
                    self.assertEqual(history["phase"], "prepared")
                    self.assertIsNone(history["receipt"])
                    self.assertIsNone(history["pid"])
                REPORTS.append({"test": self.id(), "scope": "synthetic Python OS-child; no grant or worker workload",
                                "preResumeMembershipConfirmed": True, "preResumeParentCrashChildExitConfirmed": True,
                                "primaryUserCodeMarkerAbsent": True, "preparedHoldRetained": True, "abi": observation["abi"],
                                "pauseBoundary": observation["pauseBoundary"],
                                "postCrashJobEmptyQuery": "not-available-after-last-job-handle-close",
                                "exitProofIssued": False})
            finally:
                if outer.poll() is None:
                    outer.kill()
                    outer.wait(timeout=2)
                if handle:
                    if kernel.WaitForSingleObject(handle, 0) == 258:
                        # Cleanup a failed negative outcome without turning it
                        # into a successful crash/exit assertion.
                        kernel.TerminateProcess(handle, 125)
                        kernel.WaitForSingleObject(handle, 2000)
                    kernel.CloseHandle(handle)


class WorkerIdentityAdmissionTests(unittest.TestCase):
    def test_missing_expected_digest_never_reads_or_spawns(self):
        with mock.patch.object(supervisor.WorkerIdentity, "_hash", side_effect=AssertionError("untrusted file read")), \
             mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("untrusted executable started")) as spawn:
            for missing in (None, "", "PRIVATE_MARKER", "0" * 63, True):
                with self.subTest(value_type=type(missing).__name__), \
                     self.assertRaisesRegex(budget.BudgetError, "ExpectedWorkerSha256Required"):
                    supervisor.WorkerIdentity.inspect(Path(sys.executable), "1" * 40, missing)
            spawn.assert_not_called()

    def test_wrong_expected_digest_never_starts_unknown_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            unknown = Path(temporary).resolve() / "Swirl.exe"
            unknown.write_bytes(b"Unknown executable must not self-attest through --build-info")
            with mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("untrusted executable started")) as spawn:
                with self.assertRaisesRegex(budget.BudgetError, "WorkerDigestMismatch"):
                    supervisor.WorkerIdentity.inspect(unknown, "1" * 40, "0" * 64)
                spawn.assert_not_called()

    def test_missing_cli_digest_fails_before_inspection_or_directory_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary).resolve() / "not-created"
            output = io.StringIO()
            with mock.patch.object(supervisor.WorkerIdentity, "inspect", side_effect=AssertionError("metadata attempted")) as inspect, \
                 contextlib.redirect_stdout(output):
                result = supervisor.main(["--worker", "PRIVATE_MARKER", "--state-dir", str(state),
                                          "--expected-source", "1" * 40, "--workload", "core_probe"])
            inspect.assert_not_called()
            self.assertEqual(result, 2)
            self.assertFalse(state.exists())
            self.assertEqual(json.loads(output.getvalue()), {"error": "SupervisorArgumentsRejected", "liveReady": False})

    def test_identity_factory_cannot_be_bypassed_by_direct_construction(self):
        with self.assertRaisesRegex(budget.BudgetError, "WorkerIdentityFactoryRequired"):
            supervisor.WorkerIdentity(Path(sys.executable), {}, "1" * 64)


class RealWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global IDENTITY
        executable = os.environ.get("SWIRL_PRIVATE_WORKER")
        if not executable:
            raise unittest.SkipTest("SWIRL_PRIVATE_WORKER not supplied; no Rust e2e claimed")
        expected = os.environ.get("SWIRL_PRIVATE_EXPECTED_SOURCE")
        expected_digest = os.environ.get("SWIRL_PRIVATE_EXPECTED_WORKER_SHA256")
        IDENTITY = cls.identity = supervisor.WorkerIdentity.inspect(executable, expected, expected_digest)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name).resolve() / "budget"
        self.ledger = budget.Ledger(self.path).__enter__()
        self.ledger.initialize_synthetic()
        self.coordinator = supervisor.Supervisor(self.ledger, self.identity)

    def tearDown(self):
        self.ledger.__exit__()
        self.temp.cleanup()

    def run_case(self, workload, **options):
        result = self.coordinator.run(workload, **options)
        REPORTS.append({"test": self.id(), **result})
        return result

    def test_upload_and_download_use_real_guard_bytes(self):
        for ordinal, workload in enumerate(("upload_until_stop", "download_until_stop"), 1):
            report = self.run_case(workload, node=ordinal)
            self.assertTrue(report["settled"], report)
            self.assertEqual(report["outcome"], "QuotaStopped")
            self.assertTrue(report["observedRunning"])
            self.assertEqual(report["guard"]["upload"] + report["guard"]["download"], 65536)
            self.assertEqual(report["guard"]["connection_attempts"], 1)
            self.assertEqual(report["fixture"]["authenticatedConnections"], 1)
            self.assertEqual(report["ledger"]["heldBytes"], 0)
            self.assertIsNone(report["ledger"]["billingDelta"])
            self.assertFalse(report["liveReady"])

    def test_real_core_tls_authenticated_connect_probe_204(self):
        report = self.run_case("core_probe", timeout_ms=4000)
        self.assertTrue(report["settled"], report)
        self.assertEqual(report["outcome"], "CoreProbeSucceeded")
        self.assertEqual(report["fixture"]["httpStatus"], 204)
        self.assertEqual(report["guard"]["connection_attempts"], 2)
        self.assertGreater(report["guard"]["upload"], 0)
        self.assertGreater(report["guard"]["download"], 0)

    def test_stalled_runtime_is_killed_and_full_unknown_hold_survives(self):
        report = self.run_case("stall_runtime_after_connect", timeout_ms=600)
        self.assertFalse(report["settled"])
        self.assertTrue(report["observedRunning"], report)
        self.assertTrue(report["exit"]["ownedProcessSetEmpty"])
        self.assertIsNone(report["guard"])
        self.assertLess(report["parentElapsedMs"], 1800)
        held = 65536 + budget.TCP_RECEIVE_RESERVATION
        self.assertEqual(report["ledger"]["heldBytes"], held)
        self.assertEqual(report["localMeasurement"], "unknown-full-reservation-held")
        self.ledger.__exit__()
        self.ledger.__enter__()
        self.assertEqual(self.ledger.summary()["heldBytes"], held)
        with self.assertRaisesRegex(budget.BudgetError, "ConfigurationAlreadyAttempted"):
            self.coordinator.run("stall_runtime_after_connect", timeout_ms=600)

    def test_cancel_releases_real_sockets_before_settlement(self):
        event = threading.Event()
        stop = threading.Event()
        def cancel_after_actual_running():
            deadline = time.monotonic() + 5
            while not stop.is_set() and time.monotonic() < deadline:
                with self.ledger.mutex:
                    active = any(h["phase"] == "active" for h in self.ledger.data["history"].values())
                if active:
                    stop.wait(0.05)
                    event.set()
                    return
                stop.wait(0.005)
        timer = threading.Thread(target=cancel_after_actual_running, daemon=True)
        timer.start()
        try:
            report = self.run_case("download_until_stop", byte_limit=4 * 1024 * 1024,
                                   timeout_ms=2000, cancel_event=event)
        finally:
            stop.set()
            timer.join(timeout=1)
        self.assertTrue(report["settled"], report)
        self.assertEqual(report["outcome"], "Cancelled")
        self.assertGreater(report["guard"]["upload"] + report["guard"]["download"], 0)
        self.assertLess(report["guard"]["upload"] + report["guard"]["download"], 4 * 1024 * 1024)
        self.assertTrue(report["exit"]["ownedProcessSetEmpty"])

    def test_failed_durable_reservation_never_spawns_workload(self):
        with mock.patch.object(self.ledger, "_save", side_effect=budget.BudgetError("InjectedDurableFailure")), \
             mock.patch.object(supervisor, "OwnedProcess", side_effect=AssertionError("workload spawned before durable reservation")):
            with self.assertRaisesRegex(budget.BudgetError, "InjectedDurableFailure"):
                self.coordinator.run("upload_until_stop")

    def test_start_requires_durable_reservation_and_guard_ack(self):
        original = supervisor._Frames.send
        seen = []
        def observe(frames, value):
            if value["op"] in {"grant", "start"}:
                data = json.loads(self.ledger.path.read_text())
                history = data["history"][value["reservation_id"]]
                self.assertIn(value["reservation_id"], data["reservations"])
                self.assertEqual(history["planDigest"], value["plan_digest"])
                self.assertEqual(history["phase"], "spawned" if value["op"] == "grant" else "running")
                seen.append(value["op"])
            return original(frames, value)
        with mock.patch.object(supervisor._Frames, "send", observe):
            report = self.run_case("upload_until_stop")
        self.assertTrue(report["settled"], report)
        self.assertEqual(seen, ["grant", "start"])

    def test_mismatched_real_ready_receipt_never_starts(self):
        original = supervisor._Frames.receive
        def corrupt(frames, deadline):
            value = original(frames, deadline)
            return {**value, "nonce": "0" * 64} if value.get("op") == "ready" else value
        with mock.patch.object(supervisor._Frames, "receive", corrupt):
            report = self.run_case("upload_until_stop")
        self.assertFalse(report["settled"])
        self.assertEqual(report["outcome"], "WorkerReceiptBindingMismatch")
        self.assertEqual(report["fixture"]["acceptedConnections"], 0)
        self.assertEqual(report["ledger"]["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)

    def test_cleanup_failure_cannot_refund_a_valid_final_receipt(self):
        original = supervisor._OwnedFixture.close
        def fail_after_close(fixture):
            original(fixture)
            raise budget.BudgetError("InjectedFixtureCleanupFailure")
        with mock.patch.object(supervisor._OwnedFixture, "close", fail_after_close):
            report = self.run_case("upload_until_stop")
        self.assertFalse(report["settled"])
        self.assertEqual(report["outcome"], "FixtureExitUnconfirmed")
        self.assertTrue(report["exit"]["ownedProcessSetEmpty"])
        self.assertIsNotNone(report["guard"])
        self.assertEqual(report["ledger"]["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)

    def test_extra_protocol_output_cannot_refund(self):
        original = supervisor._Frames.finish
        def inject_tail(frames):
            frames.frames.put_nowait({"op": "unexpected"})
            return original(frames)
        with mock.patch.object(supervisor._Frames, "finish", inject_tail):
            report = self.run_case("upload_until_stop")
        self.assertFalse(report["settled"])
        self.assertEqual(report["outcome"], "UnexpectedWorkerTail")
        self.assertEqual(report["ledger"]["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)

    def test_real_workers_compete_under_three_held_slots(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            def run(node):
                try:
                    return self.coordinator.run("stall_runtime_after_connect", node=node, timeout_ms=700)
                except budget.BudgetError as error:
                    return str(error)
            results = list(pool.map(run, range(1, 5)))
        self.assertEqual(results.count("ConcurrencyLimit"), 1)
        reports = [value for value in results if isinstance(value, dict)]
        REPORTS.extend({"test": self.id(), **value} for value in reports)
        self.assertTrue(all(value["observedRunning"] and value["exit"]["ownedProcessSetEmpty"] for value in reports), reports)
        self.assertEqual(self.ledger.summary()["heldBytes"], 3 * (65536 + budget.TCP_RECEIVE_RESERVATION))

    @unittest.skipUnless(os.name == "nt", "Windows kill-on-close after parent crash")
    def test_windows_parent_crash_kills_rust_child_and_retains_history(self):
        self.ledger.__exit__()
        self.path = self.path.with_name("crash-budget")
        code = ("import sys\nsys.path.insert(0,sys.argv[1])\n"
                "from PrivateSubscriptionBudget import Ledger\n"
                "from PrivateSubscriptionSupervisor import WorkerIdentity,Supervisor\n"
                "identity=WorkerIdentity.inspect(sys.argv[2],sys.argv[3],sys.argv[5])\n"
                "with Ledger(sys.argv[4]) as ledger:\n"
                " ledger.initialize_synthetic()\n"
                " Supervisor(ledger,identity).run('stall_runtime_after_connect',timeout_ms=8000)\n")
        outer = subprocess.Popen([sys.executable, "-c", code, str(TOOLS), str(self.identity.path),
                                  self.identity.metadata["source_sha"], str(self.path), self.identity.sha256],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        handle = None
        try:
            stop = time.monotonic() + 5
            history = None
            while time.monotonic() < stop:
                try:
                    data = json.loads((self.path / "traffic-budget.json").read_text())
                    history = data["history"].get("1")
                    if history and history["phase"] == "active":
                        break
                except (OSError, ValueError, KeyError):
                    pass
                time.sleep(0.01)
            self.assertIsNotNone(history)
            self.assertEqual(history["phase"], "active")
            import ctypes as c
            from ctypes import wintypes as w
            kernel = c.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
            kernel.WaitForSingleObject.argtypes, kernel.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
            kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
            handle = kernel.OpenProcess(0x100000, False, history["pid"])
            self.assertTrue(handle)
            outer.kill()
            outer.wait(timeout=2)
            self.assertEqual(kernel.WaitForSingleObject(handle, 2000), 0)
            self.ledger = budget.Ledger(self.path).__enter__()
            self.assertEqual(self.ledger.summary()["heldBytes"], 65536 + budget.TCP_RECEIVE_RESERVATION)
            self.assertEqual(self.ledger.data["history"]["1"]["phase"], "active")
            with self.assertRaisesRegex(budget.BudgetError, "ConfigurationAlreadyAttempted"):
                supervisor.Supervisor(self.ledger, self.identity).run("stall_runtime_after_connect", timeout_ms=8000)
            REPORTS.append({"test": self.id(), "scope": budget.SYNTHETIC_DOMAIN,
                            "parentCrashJobExitConfirmed": True, "unsettledHoldRetained": True,
                            "source_sha": self.identity.metadata["source_sha"], "worker_sha256": self.identity.sha256})
        finally:
            if outer.poll() is None:
                outer.kill()
                outer.wait(timeout=2)
            if handle:
                kernel.CloseHandle(handle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--evidence", type=Path)
    options, remaining = parser.parse_known_args()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    metadata = {"schema": 1, "scope": "synthetic-loopback-only; not live/UI/wire/TUN acceptance",
                "platform": sys.platform, "testsRun": result.testsRun, "failures": len(result.failures),
                "errors": len(result.errors), "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
                "source_sha": None if IDENTITY is None else IDENTITY.metadata["source_sha"],
                "worker_sha256": None if IDENTITY is None else IDENTITY.sha256,
                "reports": REPORTS, "realNodeRequests": 0, "providerRequests": 0, "liveReady": False}
    if options.evidence:
        directory = options.evidence / (time.strftime("attempt-%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(4))
        directory.mkdir(parents=True, exist_ok=False)
        with (directory / "supervisor-results.json").open("x", encoding="utf-8") as output:
            json.dump(metadata, output, ensure_ascii=True, sort_keys=True, indent=2)
    raise SystemExit(0 if result.wasSuccessful() else 1)
