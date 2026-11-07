"""Boundary controls; Windows adds held-file and harmless owned-child checks, never Qt/live data."""

import copy
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


sdk = load("sdk_boundary_tests", "Build-Qt612QmlDiagnosticSdk.py")
comparison = load("comparison_boundary_tests", "RunQt612RuntimeComparison.py")


def synthetic_compiler_context(root):
    repo, work, stock = root / "repo", root / "work", root / "stock"
    for path in (repo / "tools/repros/qt612-popup-gc", work / "source", work / "build",
                 work / "fixtures", work / "module-stage", stock / "bin"):
        path.mkdir(parents=True)
    for path in (work / "source/CMakeLists.txt", repo / "tools/repros/qt612-popup-gc/CMakeLists.txt"):
        path.write_bytes(b"# Synthetic path binding only; never executed.\n")
    (stock / "bin/qt-configure-module.bat").write_bytes(b"synthetic unexecuted wrapper")
    directory = root / "VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64"
    directory.mkdir(parents=True)
    tools = {}
    for name in ("cmake.exe", "pwsh.exe", "cl.exe", "link.exe", "lib.exe", "rc.exe", "mt.exe", "ninja.exe"):
        path = directory / name
        path.write_bytes(("synthetic unexecuted " + name).encode())
        tools[name] = str(path)
    helper = directory / "vctip.exe"
    helper.write_bytes(b"synthetic image identity only; never launched")
    identities = {name: {"path": path, **sdk.file_identity(Path(path))} for name, path in tools.items()}
    lock = json.loads((TOOLS / "qt612-qml-patch.lock.json").read_text())
    lock["compiler_retirement"].update(sdk.file_identity(helper))
    known = {str(helper).replace("\\", "/").casefold(): {"path": str(helper), **sdk.file_identity(helper)}}
    (work / "msvc-initial-cache.cmake").write_bytes(sdk.MSVC_INITIAL_CACHE.encode())
    (work / "configure-module.ps1").write_bytes(
        sdk.module_configure_script(sdk.module_configure_arguments(work, stock, tools)))
    return {"repo": repo, "work": work, "stock": stock, "tools": tools}, lock, identities, known


def completed_compiler_record():
    return {"atomic_job_membership": True, "process_signaled": True, "owned_job_empty": False,
            "errors": [], "timed_out": False, "exit_code": 0, "forced_cleanup": False,
            "root_first_signal": {"exit_code": 0, "before_any_termination": True}}


def native_control_evidence(root, name):
    path = root / "native-evidence" / name
    if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("SWIRL_QT612_RUNTIME_PATCH") == "1":
        path = Path(os.environ["GITHUB_WORKSPACE"]) / "build-evidence/qt612-runtime-patch/native-boundaries" / name
    return sdk.fresh_directory(path) if path.parent.is_dir() else _make_native_parent(path)


def _make_native_parent(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    return sdk.fresh_directory(path)


class DiagnosticBoundaryTests(unittest.TestCase):
    def test_only_four_exact_compiler_invocations_can_construct_a_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            context, lock, identities, known = synthetic_compiler_context(Path(directory).resolve())
            work, tools = context["work"], context["tools"]
            cases = [
                ("sdk:10-configure", [tools["pwsh.exe"], "-NoLogo", "-NoProfile", "-NonInteractive",
                                       "-File", work / "configure-module.ps1"], work / "build"),
                ("sdk:11-qml-build", [tools["cmake.exe"], "--build", work / "build", "--target",
                                      "Qml", "BuiltinsOutput", "--parallel", "2"], work),
                ("comparison:01-configure-fixtures", sdk.fixture_configure_arguments(
                    context["repo"], work, context["stock"], tools), work),
                ("comparison:02-build-fixtures", [tools["cmake.exe"], "--build", work / "fixtures",
                    "--target", "PopupGcFixture", "SweepSlotsProbe", "--parallel", "2"], work)]
            for phase, args, cwd in cases:
                with self.subTest(phase=phase):
                    plan = sdk.compiler_phase_plan(phase, args, cwd, context, lock, identities, known)
                    self.assertEqual(plan["phase"], phase)
                    with self.assertRaisesRegex(RuntimeError, "CompilerPhaseInvocationMismatch"):
                        sdk.compiler_phase_plan(phase, [*args, "-P", "arbitrary.cmake"], cwd,
                                                context, lock, identities, known)
            phase, args, cwd = cases[0]
            for invalid in ("sdk:12-install-qml-only", "comparison:04-stock-fixtures", "git", "sdk:10-configure-other"):
                with self.assertRaisesRegex(RuntimeError, "UnrecognizedCompilerPhase"):
                    sdk.compiler_phase_plan(invalid, args, cwd, context, lock, identities, known)
            with self.assertRaisesRegex(RuntimeError, "CompilerPhaseInvocationMismatch"):
                sdk.compiler_phase_plan(phase, args, work, context, lock, identities, known)
            with self.assertRaisesRegex(RuntimeError, "CompilerCapabilityFactoryRequired"):
                sdk._CompilerPhase(object(), {}, {})

    def test_changed_script_cache_tool_or_helper_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            context, lock, identities, known = synthetic_compiler_context(Path(directory).resolve())
            work, tools = context["work"], context["tools"]
            args = [tools["pwsh.exe"], "-NoLogo", "-NoProfile", "-NonInteractive", "-File", work / "configure-module.ps1"]
            for path, failure in ((work / "configure-module.ps1", "CompilerConfigureScriptChanged"),
                                  (work / "msvc-initial-cache.cmake", "CompilerInitialCacheChanged"),
                                  (Path(tools["cmake.exe"]), "CompilerToolIdentityChanged"),
                                  (Path(tools["cl.exe"]).parent / "vctip.exe", "CompilerHelperPinMismatch")):
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"changed")
                    with patch.object(sdk, "_run_logged") as launch:
                        with self.assertRaisesRegex(RuntimeError, failure):
                            sdk.run_compiler_logged("sdk:10-configure", args, work / "build", work / "logs", 10,
                                context=context, lock=lock, tool_identities=identities, known_executables=known, env={})
                        launch.assert_not_called()
                finally:
                    path.write_bytes(original)
            with self.assertRaisesRegex(RuntimeError, "CompilerHelperNotInPrelaunchInventory"):
                sdk.compiler_phase_plan("sdk:10-configure", args, work / "build", context, lock, identities, {})
            altered = copy.deepcopy(lock)
            altered["compiler_retirement"]["msvc_tools_version"] = "14.45.12345"
            with self.assertRaisesRegex(RuntimeError, "CompilerRetirementToolsetMismatch"):
                sdk.compiler_phase_plan("sdk:10-configure", args, work / "build", context, altered, identities, known)

    def test_receipt_flags_cannot_create_live_compiler_retirement_proof(self):
        record = completed_compiler_record()
        record.update(owned_job_empty=True, forced_cleanup=True,
                      termination_reason="controlled-pinned-compiler-helper",
                      compiler_controlled_retirement={"accepted": True, "helper_signaled": True,
                                                     "proved_within_original_deadline": True})
        capability = sdk._CompilerPhase(sdk._COMPILER_PHASE_FACTORY, {}, {})
        for value in (None, {}, record["compiler_controlled_retirement"], capability):
            self.assertFalse(sdk.compiler_completion_allowed(record, value))
        self.assertFalse(sdk.command_completion_allowed(record, (0,)))
        # A simulated backend proof is used only to test the independent failure conditions.
        capability.proved = capability.targeted = True
        self.assertTrue(sdk.compiler_completion_allowed(record, capability))
        for key, value in (("exit_code", 1), ("timed_out", True), ("errors", ["OutputLimitExceeded"]),
                           ("owned_job_empty", False), ("process_signaled", False),
                           ("atomic_job_membership", False), ("termination_reason", "exception-cleanup")):
            self.assertFalse(sdk.compiler_completion_allowed({**record, key: value}, capability), key)
        first = {"exit_code": 0, "before_any_termination": False}
        self.assertFalse(sdk.compiler_completion_allowed({**record, "root_first_signal": first}, capability))

    def test_targeted_retirement_rechecks_same_handle_and_preserves_deadline(self):
        events = []
        capability = sdk._CompilerPhase(sdk._COMPILER_PHASE_FACTORY, {}, {})
        capability.process, capability.creation, capability.root_creation = 1234, 200, 100
        capability.c = SimpleNamespace(byref=ctypes.byref, get_last_error=lambda: 0)
        capability.w = SimpleNamespace(DWORD=ctypes.c_uint32)
        def inspect(job, handle):
            events.append(("inspect", job, handle))
            return 200, 258, "bound-path-hash"
        def terminate(handle, code):
            events.append(("terminate", handle, code))
            return True
        def get_exit(handle, output):
            events.append(("exit", handle))
            output._obj.value = 125
            return True
        capability.inspect_process = inspect
        capability.creation_time = lambda handle: 200
        capability.k = SimpleNamespace(TerminateProcess=terminate, WaitForSingleObject=lambda h, t: 0,
                                       GetExitCodeProcess=get_exit)
        record = completed_compiler_record()
        with patch.object(sdk.time, "monotonic", return_value=100):
            capability.terminate(88, record, 105)
            record["owned_job_empty"] = True
            capability.prove(record, 105)
        self.assertEqual(events, [("inspect", 88, 1234), ("terminate", 1234, 125), ("exit", 1234)])
        self.assertTrue(record["forced_cleanup"])
        self.assertEqual(record["exit_code"], 0)
        self.assertTrue(sdk.compiler_completion_allowed(record, capability))
        with patch.object(sdk.time, "monotonic", return_value=105):
            with self.assertRaisesRegex(RuntimeError, "CompilerHelperExitProofExpired"):
                capability.prove(record, 105)

    def test_changed_creation_nonzero_root_or_expired_deadline_never_terminates_candidate(self):
        for scenario in ("creation", "nonzero", "deadline", "prior-error"):
            capability = sdk._CompilerPhase(sdk._COMPILER_PHASE_FACTORY, {}, {})
            capability.process, capability.creation = 1234, 200
            capability.inspect_process = lambda job, handle: (201 if scenario == "creation" else 200, 258, "hash")
            calls = []
            capability.k = SimpleNamespace(TerminateProcess=lambda *args: calls.append(args))
            record = completed_compiler_record()
            if scenario == "nonzero":
                record["exit_code"] = record["root_first_signal"]["exit_code"] = 7
            if scenario == "prior-error":
                record["errors"].append("OutputLimitExceeded")
            with patch.object(sdk.time, "monotonic", return_value=100):
                with self.assertRaises(RuntimeError):
                    capability.terminate(88, record, 99 if scenario == "deadline" else 105)
            self.assertEqual(calls, [], scenario)
            self.assertFalse(record["forced_cleanup"])

    def test_failed_targeted_api_is_recorded_as_forced_and_never_proved(self):
        capability = sdk._CompilerPhase(sdk._COMPILER_PHASE_FACTORY, {}, {})
        capability.process, capability.creation = 1234, 200
        capability.inspect_process = lambda job, handle: (200, 258, "bound-path-hash")
        calls = []
        capability.k = SimpleNamespace(TerminateProcess=lambda *args: calls.append(args) or False)
        capability.c = SimpleNamespace(get_last_error=lambda: 5)
        record = completed_compiler_record()
        with patch.object(sdk.time, "monotonic", return_value=100):
            with self.assertRaisesRegex(RuntimeError, "CompilerHelperTerminationFailed:5"):
                capability.terminate(88, record, 105)
        self.assertEqual(calls, [(1234, 125)])
        self.assertTrue(record["forced_cleanup"])
        self.assertFalse(capability.proof["terminate_process_returned"])
        self.assertFalse(capability.proved)
        self.assertEqual(record["exit_code"], 0)
        self.assertFalse(sdk.compiler_completion_allowed(record, capability))

    def test_actual_helper_exit_and_job_proof_fail_closed_and_keep_observed_exit(self):
        for scenario in ("active", "query-failed", "wrong-exit", "creation-changed", "job-not-empty", "root-failed"):
            capability = sdk._CompilerPhase(sdk._COMPILER_PHASE_FACTORY, {}, {})
            capability.process, capability.creation, capability.targeted = 1234, 200, True
            capability.c = SimpleNamespace(byref=ctypes.byref)
            capability.w = SimpleNamespace(DWORD=ctypes.c_uint32)
            calls = []
            def get_exit(handle, output):
                calls.append(handle)
                output._obj.value = 7 if scenario == "wrong-exit" else 125
                return scenario != "query-failed"
            capability.k = SimpleNamespace(
                WaitForSingleObject=lambda h, t: 258 if scenario == "active" else 0,
                GetExitCodeProcess=get_exit)
            capability.creation_time = lambda handle: 201 if scenario == "creation-changed" else 200
            record = completed_compiler_record()
            record.update(owned_job_empty=scenario != "job-not-empty", forced_cleanup=True,
                          termination_reason="controlled-pinned-compiler-helper")
            if scenario == "root-failed":
                record["exit_code"] = 1
            with self.subTest(scenario=scenario), patch.object(sdk.time, "monotonic", return_value=100):
                with self.assertRaises(RuntimeError):
                    capability.prove(record, 105)
                self.assertFalse(capability.proved)
                self.assertFalse(sdk.compiler_completion_allowed(record, capability))
                if scenario == "active":
                    self.assertEqual(calls, [])
                elif scenario == "wrong-exit":
                    self.assertEqual(capability.proof["helper_exit_code"], 7)
                    self.assertTrue(capability.proof["helper_signaled"])

    def test_foreign_or_unconfirmed_job_handle_is_not_inspected_further(self):
        for success in (False, True):
            capability = sdk._CompilerPhase(sdk._COMPILER_PHASE_FACTORY, {}, {})
            capability.c, capability.w = ctypes, SimpleNamespace(BOOL=ctypes.c_int32)
            calls = []
            def membership(handle, job, output):
                calls.append((handle, job))
                output._obj.value = 0
                return success
            capability.k = SimpleNamespace(IsProcessInJob=membership)
            capability.creation_time = lambda handle: self.fail("must not inspect a foreign process")
            with self.assertRaisesRegex(RuntimeError, "CompilerHelperNotInOwnedJob"):
                capability.inspect_process(88, 1234)
            self.assertEqual(calls, [(1234, 88)])

    def test_multiple_owned_residues_do_not_open_a_target_handle(self):
        capability = sdk._CompilerPhase(sdk._COMPILER_PHASE_FACTORY, {}, {})
        calls = []
        def query(job, kind, output, size, length):
            calls.append(("query", job, kind))
            output._obj.assigned = output._obj.count = 2
            output._obj.pids[0], output._obj.pids[1] = 10, 11
            return True
        capability.c, capability.w = ctypes, SimpleNamespace(DWORD=ctypes.c_uint32)
        capability.k = SimpleNamespace(QueryInformationJobObject=query,
                                       OpenProcess=lambda *args: calls.append(("open", *args)))
        snapshot = {}
        with self.assertRaisesRegex(RuntimeError, "CompilerRetirementRequiresExactlyOneSurvivor"):
            capability.capture(88, snapshot)
        self.assertEqual(calls, [("query", 88, 3)])
        self.assertEqual(snapshot["listed_pids"], [10, 11])

    def test_compiler_resource_close_failure_does_not_skip_the_image_lock(self):
        capability = sdk._CompilerPhase(sdk._COMPILER_PHASE_FACTORY, {}, {})
        capability.process, capability.image = 1234, SimpleNamespace(handle=5678)
        calls = []
        def close(handle):
            calls.append(handle)
            if handle == 1234:
                raise OSError("controlled process handle close failure")
            return True
        capability.k = SimpleNamespace(CloseHandle=close)
        record = {"errors": ["OriginalNativeFailure"], "exit_code": 7}
        capability.close(record)
        self.assertEqual(calls, [1234, 5678])
        self.assertEqual(record["errors"][0], "OriginalNativeFailure")
        self.assertEqual(record["exit_code"], 7)
        self.assertIn("CompilerHelperHandleCloseFailed:OSError", record["errors"][1])

    def test_same_path_with_changed_file_id_is_rejected_and_alias_handle_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "identity-control.bin"
            path.write_bytes(b"not executed")
            image = object.__new__(sdk._PinnedCompilerImage)
            image.handle = 1
            image.identity = {"path_key": str(path).replace("\\", "/").casefold(), "file_id_128": "11" * 16}
            image.read_identity = lambda handle: (image.identity if handle == 1 else
                                                  {**image.identity, "file_id_128": "22" * 16})
            image.open = lambda candidate: 2
            closed = []
            image.k = SimpleNamespace(CloseHandle=lambda handle: closed.append(handle) or True)
            with patch.object(sdk, "_windows_image_path", side_effect=lambda value: value):
                with self.assertRaisesRegex(RuntimeError, "CompilerProcessImageIdentityMismatch"):
                    image.validate_process_image(str(path))
            self.assertEqual(closed, [2])

    @unittest.skipUnless(os.name == "nt", "Actual Windows held-file identity/sharing required")
    def test_windows_image_file_pin_rejects_writes_delete_and_other_path(self):
        from ctypes import wintypes
        with tempfile.TemporaryDirectory(prefix="swirl image pin ") as directory:
            root = Path(directory).resolve()
            evidence = native_control_evidence(root, "held-image-file")
            report = {"success": False, "scope": "ordinary public file only; no executable started",
                      "actual_process_module_sampling": False}
            original, other = root / "public-image-control.bin", root / "other-control.bin"
            original.write_bytes(b"Public synthetic file identity control; not executable.")
            other.write_bytes(original.read_bytes())
            expected = {"path": str(original), **sdk.file_identity(original)}
            try:
                image = sdk._PinnedCompilerImage(ctypes.WinDLL("kernel32", use_last_error=True), ctypes, wintypes, expected)
                try:
                    report["locked_image"] = image.identity
                    self.assertEqual(len(image.identity["file_id_128"]), 32)
                    self.assertNotEqual(image.identity["file_id_128"], "0" * 32)
                    image.validate_process_image(str(original))
                    with self.assertRaises(OSError) as write_error:
                        with original.open("wb"):
                            pass
                    report["denied_write_winerror"] = getattr(write_error.exception, "winerror", None)
                    with self.assertRaises(OSError) as delete_error:
                        original.unlink()
                    report["denied_delete_winerror"] = getattr(delete_error.exception, "winerror", None)
                    with self.assertRaisesRegex(RuntimeError, "CompilerProcessImagePathMismatch"):
                        image.validate_process_image(str(other))
                finally:
                    report["image_handle_closed"] = bool(image.k.CloseHandle(image.handle))
                    image.handle = None
                    self.assertTrue(report["image_handle_closed"])
                original.write_bytes(b"Read lock released after all handle checks.")
                report["write_after_close_succeeded"] = True
                report["success"] = True
            except BaseException as error:
                report["error"] = type(error).__name__ + ":" + str(error)
                raise
            finally:
                sdk.write_json(evidence / "held-file-result.json", report)

    @unittest.skipUnless(os.name == "nt", "Actual Windows Job retirement required")
    def test_windows_generic_unknown_child_still_fails_after_owned_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="swirl owned child ") as directory:
            root = Path(directory).resolve()
            evidence = native_control_evidence(root, "generic-child")
            program = ("import subprocess,sys; child=subprocess.Popen([sys.executable,'-c',"
                       "'import time; time.sleep(30)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
                       "print('public harmless owned child',child.pid)")
            with self.assertRaisesRegex(RuntimeError, "CommandFailed:native-unknown-child"):
                sdk.run_logged([str(Path(sys.executable).resolve()), "-c", program], root, evidence,
                               "native-unknown-child", 5)
            record = json.loads((evidence / "native-unknown-child.json").read_text())
            self.assertEqual(record["exit_code"], 0)
            self.assertTrue(record["root_first_signal"]["before_any_termination"])
            self.assertTrue(record["forced_cleanup"])
            self.assertTrue(record["process_signaled"] and record["owned_job_empty"])
            self.assertIn("UnexpectedDescendantsAfterSuccessfulRoot", record["errors"])
            self.assertNotIn("compiler_phase", record)

    @unittest.skipUnless(os.name == "nt", "Actual Windows batch parsing required")
    def test_initial_cache_survives_batch_reexpansion_and_preserves_release_format(self):
        cmake, powershell, ninja = shutil.which("cmake"), shutil.which("pwsh"), shutil.which("ninja")
        if not cmake or not powershell or not ninja:
            self.skipTest("CMake, Ninja and PowerShell 7 are required for the configuration-only control")
        with tempfile.TemporaryDirectory(prefix="swirl cache regression ") as directory:
            root = Path(directory).resolve()
            source = root / "source"
            source.mkdir()
            (source / "CMakeLists.txt").write_text(
                'cmake_minimum_required(VERSION 3.25)\nproject(FormatBoundary NONE)\n'
                'file(GENERATE OUTPUT "selected-format.txt" '
                'CONTENT "${CMAKE_MSVC_DEBUG_INFORMATION_FORMAT}")\n', encoding="utf-8")
            cache = root / "initial-cache.cmake"
            cache.write_text(sdk.MSVC_INITIAL_CACHE, encoding="utf-8")
            wrapper = root / "forward.bat"
            wrapper.write_text('@echo off\nsetlocal ENABLEEXTENSIONS\nset ARGS=%*\n'
                               'call :forward %ARGS%\nexit /b %errorlevel%\n:forward\n"'
                               + cmake + '" %*\nexit /b %errorlevel%\n', encoding="utf-8")
            def configure(name, arguments):
                build = root / name
                script = root / (name + ".ps1")
                command = [wrapper, "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=" + ninja,
                           "-S", source, "-B", build, *arguments]
                script.write_text("& " + " ".join(sdk.ps_quote(x) for x in command)
                                  + "\nexit $LASTEXITCODE\n", encoding="utf-8")
                result = subprocess.run([powershell, "-NoLogo", "-NoProfile", "-NonInteractive",
                                         "-File", str(script)], cwd=root, capture_output=True,
                                        text=True, timeout=30)
                return build, result
            # This reproduces cmd redirection of the previous direct -D value.
            _, negative = configure("direct-expression", ["-DCMAKE_MSVC_DEBUG_INFORMATION_FORMAT="
                                                          + sdk.MSVC_DEBUG_INFORMATION_FORMAT])
            self.assertNotEqual(negative.returncode, 0)
            for config, expected in (("Debug", "Embedded"), ("RelWithDebInfo", "Embedded"),
                                     ("Release", "")):
                with self.subTest(configuration=config):
                    build, result = configure(config, ["-C", cache, "-DCMAKE_BUILD_TYPE=" + config])
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual((build / "selected-format.txt").read_text(), expected)
                    values = sdk.cache_values((build / "CMakeCache.txt").read_text())
                    self.assertEqual(values["CMAKE_MSVC_DEBUG_INFORMATION_FORMAT"],
                                     sdk.MSVC_DEBUG_INFORMATION_FORMAT)
                    self.assertEqual(values["CMAKE_POLICY_DEFAULT_CMP0141"], "NEW")

    def test_compiler_opt_out_is_scoped_and_cannot_forward_parent_secrets(self):
        original = {"PATH": "synthetic-toolchain", "VCTIP_NO_TELEMETRY": "0",
                    "GITHUB_TOKEN": "synthetic-secret", "HTTPS_PROXY": "synthetic-proxy",
                    "CL": "/Zi", "_CL_": "/Zi"}
        with patch.dict(os.environ, original, clear=True):
            environment = sdk.tool_environment()
            self.assertEqual(environment["VCTIP_NO_TELEMETRY"], "1")
            self.assertEqual(environment["PATH"], original["PATH"])
            for name in ("GITHUB_TOKEN", "HTTPS_PROXY", "CL", "_CL_"):
                self.assertNotIn(name, environment)
            self.assertEqual(dict(os.environ), original)

    def test_patch_lock_matches_exact_retained_production_patch(self):
        lock = json.loads((TOOLS / "qt612-qml-patch.lock.json").read_text())
        self.assertEqual(lock["patch"]["sha256"], sdk.digest(TOOLS.parent / lock["patch"]["path"]))
        self.assertEqual(lock["build"]["targets"], ["Qml", "BuiltinsOutput"])
        self.assertEqual(len(lock["stock"]["archives"]), 9)

    def test_corrupt_official_archive_receipt_is_rejected(self):
        lock = json.loads((TOOLS / "qt612-qml-patch.lock.json").read_text())
        stock = lock["stock"]
        receipt = {"version": lock["qt_version"], "arch": lock["architecture"],
                   "metadata_url": stock["metadata_url"], "metadata_sha256": stock["metadata_sha256"],
                   "package_names": stock["package_names"],
                   "packages": [{"name": k, "version": v} for k, v in stock["package_versions"].items()],
                   "archives": copy.deepcopy(stock["archives"])}
        sdk.check_receipt(lock, receipt)
        receipt["archives"][2]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "StockArchivePinMismatch"):
            sdk.check_receipt(lock, receipt)

    def test_cmake_windows_paths_are_typed_and_do_not_create_escapes(self):
        path = r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\rc.exe"
        self.assertEqual(sdk.cmake_path_definition("CMAKE_RC_COMPILER", path, "FILEPATH"),
                         "-DCMAKE_RC_COMPILER:FILEPATH=C:/Program Files (x86)/Windows Kits/10/bin/"
                         "10.0.26100.0/x64/rc.exe")
        for name in ("CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER", "CMAKE_LINKER", "CMAKE_AR",
                     "CMAKE_RC_COMPILER", "CMAKE_MT", "CMAKE_MAKE_PROGRAM"):
            self.assertNotIn("\\", sdk.cmake_path_definition(name, path, "FILEPATH"))
        self.assertEqual(sdk.cmake_path_definition("CMAKE_INSTALL_PREFIX", r"D:\stage", "PATH"),
                         "-DCMAKE_INSTALL_PREFIX:PATH=D:/stage")
        for bad in ("", "D:/one;D:/two", 'D:/bad"name', "D:/bad\nname", "D:/${untrusted}"):
            with self.assertRaisesRegex(RuntimeError, "UnsafeCmakePathDefinition"):
                sdk.cmake_path_definition("CMAKE_PREFIX_PATH", bad, "PATH")
        with self.assertRaisesRegex(RuntimeError, "InvalidCmakePathDefinition"):
            sdk.cmake_path_definition("CMAKE_PREFIX_PATH", path, "STRING")

    def test_official_qml_metadata_uses_exact_observed_abi_label_and_raw_bytes(self):
        lock = json.loads((TOOLS / "qt612-qml-patch.lock.json").read_text())
        pinned = lock["stock"]["qml_module_json"]
        self.assertEqual(pinned["targets"],
                         [{"architecture": "x86_64", "abi": "x86_64-little_endian-lp64"}])
        self.assertEqual(pinned["sha256"],
                         "b801cee3cc9546b50b263ec8b7906c8137441d726ae0cbead37b6b881021214f")
        metadata = {"schema_version": 3, "name": "Qml", "repository": "qtdeclarative",
                    "version": "6.12.0", "platforms": [{"name": "Windows", "compiler_id": "MSVC",
                    "compiler_version": pinned["compiler_version"], "targets": copy.deepcopy(pinned["targets"])}]}
        sdk.module_platform(metadata, pinned["targets"])
        for field, invalid in (("abi", "x86_64-little_endian-llp64"), ("architecture", "arm64")):
            changed = copy.deepcopy(metadata)
            changed["platforms"][0]["targets"][0][field] = invalid
            with self.assertRaisesRegex(RuntimeError, "UnexpectedModuleCompilerOrAbi"):
                sdk.module_platform(changed, pinned["targets"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "Qml.json"
            data = json.dumps(metadata, sort_keys=True).encode()
            path.write_bytes(data)
            synthetic_lock = copy.deepcopy(lock)
            synthetic_lock["stock"]["qml_module_json"].update(
                bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            self.assertEqual(sdk.verify_stock_qml_metadata(synthetic_lock, path), metadata)
            path.write_bytes(data + b"\n")  # Semantically identical JSON still has different original bytes.
            with self.assertRaisesRegex(RuntimeError, "OfficialQmlMetadataFilePinMismatch"):
                sdk.verify_stock_qml_metadata(synthetic_lock, path)

    def test_actual_cmake_command_cannot_use_another_path_or_changed_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            original, other = root / "cmake.exe", root / "other-cmake.exe"
            original.write_bytes(b"synthetic executable identity; never executed")
            other.write_bytes(original.read_bytes())
            pinned = {"path": str(original), **sdk.file_identity(original)}
            cache = {"CMAKE_COMMAND": str(original), "CMAKE_CACHE_MAJOR_VERSION": "3",
                     "CMAKE_CACHE_MINOR_VERSION": "31", "CMAKE_CACHE_PATCH_VERSION": "6"}
            self.assertEqual(sdk.verify_cmake_executable(cache, pinned)["cache_version"], "3.31.6")
            with self.assertRaisesRegex(RuntimeError, "ConfiguredCmakePathMismatch"):
                sdk.verify_cmake_executable({**cache, "CMAKE_COMMAND": str(other)}, pinned)
            original.write_bytes(b"changed bytes at the original absolute path")
            with self.assertRaisesRegex(RuntimeError, "ConfiguredCmakeBytesChanged"):
                sdk.verify_cmake_executable(cache, pinned)

    def test_failed_configuration_retains_original_cache_and_generated_rc_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            build, evidence = root / "build", root / "evidence"
            compiler = build / "CMakeFiles/3.31.6/CMakeRCCompiler.cmake"
            compiler.parent.mkdir(parents=True)
            evidence.mkdir()
            raw = b'set(CMAKE_RC_COMPILER "C:\\Program Files (x86)\\rc.exe")\r\n'
            compiler.write_bytes(raw)
            (build / "CMakeCache.txt").write_bytes(b"CMAKE_COMMAND:INTERNAL=C:/cmake.exe\r\n")
            receipt = sdk.preserve_configuration_snapshot(build, evidence)
            relative = compiler.relative_to(build).as_posix()
            copied = evidence / "configuration-at-exit" / relative
            self.assertEqual(copied.read_bytes(), raw)
            self.assertEqual(receipt["files"][relative], sdk.file_identity(compiler))
            self.assertIn("config.summary", receipt["absent_optional"])

    def test_native_failure_is_preserved_and_forced_cleanup_cannot_make_success(self):
        completed = {"atomic_job_membership": True, "process_signaled": True, "owned_job_empty": True,
                     "errors": [], "timed_out": False, "exit_code": 0, "forced_cleanup": False,
                     "root_first_signal": {"exit_code": 0, "before_any_termination": True}}
        self.assertTrue(sdk.command_completion_allowed(completed, (0,)))
        failed = copy.deepcopy(completed)
        failed.update(exit_code=1, forced_cleanup=True)
        failed["root_first_signal"]["exit_code"] = 1
        self.assertFalse(sdk.command_completion_allowed(failed, (0,)))
        self.assertTrue(sdk.command_completion_allowed(failed, (0, 1)))
        self.assertEqual(failed["exit_code"], 1)  # Collection permission does not rewrite the native result.
        for field, invalid in (("forced_cleanup", True), ("owned_job_empty", False),
                               ("process_signaled", False), ("timed_out", True),
                               ("atomic_job_membership", False), ("errors", ["UnconfirmedRetirement"])):
            changed = {**completed, field: invalid}
            self.assertFalse(sdk.command_completion_allowed(changed, (0, 1)))
        for first in ({"exit_code": 1, "before_any_termination": True},
                      {"exit_code": 0, "before_any_termination": False}):
            self.assertFalse(sdk.command_completion_allowed({**completed, "root_first_signal": first}, (0, 1)))

    def test_stream_close_error_does_not_skip_later_owned_handle_callbacks(self):
        calls, record = [], {"errors": [], "exit_code": 1, "owned_job_empty": True}
        class BrokenStream:
            def close(self):
                calls.append("broken-stream")
                raise OSError("controlled stream flush failure")
        operations = [("CommandStreamCloseFailed:0", BrokenStream().close),
                      ("CommandStreamCloseFailed:1", lambda: calls.append("next-stream")),
                      ("CommandHandleCloseFailed:process", lambda: calls.append("process-handle")),
                      ("CommandHandleCloseFailed:job", lambda: calls.append("job-handle") or False)]
        sdk.close_command_resources(operations, record)
        self.assertEqual(calls, ["broken-stream", "next-stream", "process-handle", "job-handle"])
        self.assertEqual(record["exit_code"], 1)
        self.assertTrue(record["owned_job_empty"])
        self.assertEqual(record["errors"], [
            "CommandStreamCloseFailed:0:OSError:controlled stream flush failure",
            "CommandHandleCloseFailed:job:ReturnedFalse"])

    def test_output_read_failure_keeps_native_receipt_and_other_log_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            stdout, stderr = root / "command.stdout.log", root / "command.stderr.log"
            stdout.write_bytes(b"retained raw stdout"); stderr.write_bytes(b"retained raw stderr")
            original_identity = sdk.file_identity
            def fail_one(path):
                if path == stdout:
                    raise OSError("controlled evidence read failure")
                return original_identity(path)
            record = {"errors": [], "exit_code": 1, "process_signaled": True, "owned_job_empty": True}
            with patch.object(sdk, "file_identity", side_effect=fail_one):
                sdk.collect_command_output_evidence((stdout, stderr), record)
            target = root / "command.json"
            sdk.write_json(target, record)
            actual = sdk.read_json(target)
            self.assertEqual(actual["exit_code"], 1)
            self.assertTrue(actual["process_signaled"] and actual["owned_job_empty"])
            self.assertEqual(actual["outputs"], {stderr.name: original_identity(stderr)})
            self.assertEqual(actual["errors"], [
                "CommandOutputEvidenceFailed:command.stdout.log:OSError:controlled evidence read failure"])

    def test_wrong_preimage_is_rejected_before_patch_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patch, source = root / "change.patch", root / "source.cpp"
            patch.write_bytes(b"synthetic patch bytes\n")
            source.write_bytes(b"wrong synthetic preimage\n")
            lock = {"patch": {"sha256": sdk.digest(patch),
                              "preimage_sha256": hashlib.sha256(b"expected bytes\n").hexdigest()}}
            with self.assertRaisesRegex(RuntimeError, "PatchPreimageMismatch"):
                sdk.check_patch(lock, patch, source)

    def test_unpinned_network_inputs_are_rejected_before_extraction(self):
        body = b"synthetic official metadata bytes"
        url = "https://download.qt.io/test/Updates.xml"
        fingerprint = hashlib.sha256(body).hexdigest()
        lock = {"stock": {"metadata_url": url, "metadata_sha256": fingerprint,
                          "archives": [{"url": "https://download.qt.io/test/qtbase.7z",
                                        "sha256": "a" * 64}]}}
        sdk.verify_locked_fetch(lock, url, body)
        sdk.verify_locked_fetch(lock, url + ".sha256", fingerprint.encode() + b"  Updates.xml\n")
        with self.assertRaisesRegex(RuntimeError, "MetadataChangedBeforeExtraction"):
            sdk.verify_locked_fetch(lock, url, body + b"changed")
        with self.assertRaisesRegex(RuntimeError, "OfficialDigestChangedBeforeExtraction"):
            sdk.verify_locked_fetch(lock, url + ".sha256", b"b" * 64)
        with self.assertRaisesRegex(RuntimeError, "UnexpectedInstallerFetchUrl"):
            sdk.verify_locked_fetch(lock, "https://other.invalid/metadata", body)

    def test_source_check_does_not_broadly_normalize_crlf(self):
        lock = json.loads((TOOLS / "qt612-qml-patch.lock.json").read_text())
        canonical = b"synthetic\n"
        blob = hashlib.sha1(b"blob 10\0" + canonical).hexdigest()
        self.assertEqual(sdk.verify_source_bytes(lock, "src/ordinary.cpp", canonical, blob), "exact-git-blob")
        with self.assertRaisesRegex(RuntimeError, "SourceCheckoutDiffersFromPinnedIndex"):
            sdk.verify_source_bytes(lock, "src/ordinary.cpp", b"synthetic\r\n", blob)
        with self.assertRaisesRegex(RuntimeError, "UpstreamCrLfFixtureIdentityMismatch"):
            sdk.verify_source_bytes(lock, lock["source"]["checkout_eol_contract"]["path"],
                                    b"wrong\r\n", lock["source"]["checkout_eol_contract"]["git_blob_sha1"])

    def test_owned_directory_cannot_reuse_or_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sdk.fresh_directory(root / "owned", root=root)
            with self.assertRaisesRegex(RuntimeError, "FreshDirectoryRequired"):
                sdk.fresh_directory(root / "owned", root=root)
            with self.assertRaisesRegex(RuntimeError, "OutputEscapesOwnedRoot"):
                sdk.plain_path(root / ".." / "outside", root=root, exists=False)
            with self.assertRaisesRegex(RuntimeError, "OutputEscapesOwnedRoot"):
                sdk.plain_path(root, root=root)

    def test_linked_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            original = root / "original"
            original.write_bytes(b"file")
            link = root / "linked"
            try:
                link.symlink_to(original)
            except OSError as error:
                self.skipTest("This host cannot create a symbolic link: " + str(error))
            with self.assertRaisesRegex(RuntimeError, "LinkedPathRejected"):
                sdk.file_identity(link)

    def test_only_qml_changes_are_eligible_for_module_overlay(self):
        self.assertFalse(sdk.permitted_override("bin/Qt6Core.dll", b"old", b"changed"))
        self.assertFalse(sdk.permitted_override("bin/Qt6Quick.dll", None, b"new"))
        self.assertFalse(sdk.permitted_override("include/QtQml/6.12.0/QtQml/private/qv4mm_p.h",
                                               b"old ABI", b"new ABI"))
        path = "include/QtQml/6.12.0/QtQml/private/qqmljsparser_p.h"
        self.assertFalse(sdk.permitted_override(path, None, b"new"))
        self.assertTrue(sdk.permitted_override(path, b'#line 10 "stock/path"\nint field;\n',
                                              b'#line 10 "build/path"\nint field;\n'))
        self.assertFalse(sdk.permitted_override(path, b'#line 10 "stock/path"\nint field;\n',
                                               b'#line 10 "build/path"\nlong field;\n'))

    def test_manifest_byte_change_cannot_pass_by_matching_filenames(self):
        expected = {"Qt6Qml.dll": {"bytes": 1, "sha256": "a" * 64}}
        changed = {"Qt6Qml.dll": {"bytes": 1, "sha256": "b" * 64}}
        with self.assertRaisesRegex(RuntimeError, "TreeIdentityChanged"):
            sdk.assert_same_tree(expected, changed)
        self.assertNotEqual(sdk.canonical_digest(expected), sdk.canonical_digest(changed))

    def test_ambiguous_or_missing_export_tables_are_rejected(self):
        table = "    ordinal hint RVA      name\n" + "\n".join(
            "       %d    0 00001000 symbol%d" % (i, i) for i in range(1, 102))
        self.assertEqual(len(sdk.parse_exports(table)), 101)
        with self.assertRaisesRegex(RuntimeError, "AmbiguousExportTable"):
            sdk.parse_exports(table + "\nordinal hint RVA name")
        with self.assertRaisesRegex(RuntimeError, "UnnamedOrDuplicateExport"):
            sdk.parse_exports(table + "\n       102    0 00001000 symbol1")
        with self.assertRaisesRegex(RuntimeError, "AmbiguousExportTable"):
            sdk.parse_exports("unrecognized native output")

    def test_legacy_or_ambiguous_deployment_schema_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "UnknownWindeployqtJsonSchema"):
            comparison.deployment_files([{"source": "a", "target": "b"}])
        with self.assertRaisesRegex(RuntimeError, "UnrecognizedDeploymentMapping"):
            comparison.deployment_files({"files": [{"path": "a"}]})

    def test_changed_deployed_bytes_and_unbound_qt_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            kit, runtime, other = root / "kit", root / "runtime", root / "other"
            for path in (kit / "bin", kit / "plugins/platforms", runtime / "platforms", other):
                path.mkdir(parents=True)
            entries = []
            for relative, name in (("bin/Qt6Qml.dll", "Qt6Qml.dll"),
                                   ("plugins/platforms/qoffscreen.dll", "platforms/qoffscreen.dll")):
                source, target = kit / relative, runtime / name
                source.write_bytes(b"synthetic runtime identity")
                target.write_bytes(source.read_bytes())
                entries.append({"source": str(source), "target": str(target.parent)})
            self.assertEqual(len(comparison.verify_deployment_mapping(entries, kit, runtime, [other])), 2)
            (runtime / "Qt6Qml.dll").write_bytes(b"tampered")
            with self.assertRaisesRegex(RuntimeError, "DeploymentChangedSourceBytes"):
                comparison.verify_deployment_mapping(entries, kit, runtime, [other])
            foreign = other / "Qt6Qml.dll"
            foreign.write_bytes(b"tampered")
            entries[0]["source"] = str(foreign)
            with self.assertRaisesRegex(RuntimeError, "DeploymentSourceOutsideSelectedKit"):
                comparison.verify_deployment_mapping(entries, kit, runtime, [other])

    def test_missing_process_retirement_proof_is_rejected(self):
        aggregate = {"source_sha": "a" * 40, "pr_head_sha": "b" * 40,
                     "cases": [{"name": name, "pid": 100, "exit_proof": None}
                               for name in comparison.CASES]}
        with self.assertRaisesRegex(RuntimeError, "FixtureRetirementUnconfirmed"):
            comparison.validate_case_retirement(aggregate, "a" * 40, "b" * 40)

    def test_baseline_failure_is_collected_but_never_becomes_success(self):
        stock = {"collected": True, "runner_exit_code": 1, "fixture_success": False}
        patched = {"collected": True, "runner_exit_code": 0, "fixture_success": True}
        self.assertEqual(comparison.comparison_status({"stock": stock, "patched": patched}),
                         {"comparison_collected": True, "success": False})
        self.assertEqual(comparison.comparison_status({"stock": stock}),
                         {"comparison_collected": False, "success": False})
        bad_exit = {"collected": True, "runner_exit_code": 1, "fixture_success": True}
        self.assertFalse(comparison.comparison_status({"stock": patched, "patched": bad_exit})["success"])


if __name__ == "__main__":
    unittest.main()
