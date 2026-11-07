"""Pure boundary controls only: no Qt execution, network, build or private data."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
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


class DiagnosticBoundaryTests(unittest.TestCase):
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
