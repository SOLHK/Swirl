#!/usr/bin/env python3
"""Focused source/closure controls. No application, Qt fixture or real network."""
from __future__ import annotations

import argparse
import contextlib
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("product_sdk_under_test", HERE.parent / "Compose-Qt612ProductSdk.py")
product = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = product
spec.loader.exec_module(product)
REPOSITORY = HERE.parents[1]
CMAKE = None
LOCK = product.load_lock()
SDK = TRANSPORT = None


def producer_metadata():
    p, a, repo = LOCK["producer"], LOCK["artifact"], LOCK["repository"]
    run = {"id": p["run"], "run_attempt": 1, "repository": {"id": repo["id"]},
           "head_repository": {"id": repo["id"]}, "head_sha": p["head"],
           "head_branch": repo["branch"], "path": p["workflow"], "event": "pull_request",
           "status": "completed", "conclusion": "failure"}
    jobs = {"total_count": 1, "jobs": [{"id": p["job"], "run_id": p["run"],
             "name": p["job_name"], "status": "completed", "conclusion": "failure",
             "steps": copy.deepcopy(p["steps"])}]}
    artifact = {"id": a["artifact"], "name": a["name"], "size_in_bytes": a["bytes"],
                "digest": "sha256:" + a["sha256"], "expired": False,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "workflow_run": {"id": p["run"], "repository_id": repo["id"],
                    "head_repository_id": repo["id"], "head_sha": p["head"], "head_branch": repo["branch"]}}
    return run, jobs, artifact


def pr_event(base_ref="test"):
    source, base, head = "a" * 40, "b" * 40, "c" * 40
    repo_id = LOCK["repository"]["id"]
    event = {"repository": {"id": repo_id}, "number": 84, "pull_request": {
        "number": 84, "head": {"sha": head, "repo": {"id": repo_id}, "ref": "work/future-safe-fix"},
        "base": {"sha": base, "repo": {"id": repo_id}, "ref": base_ref}}}
    environment = {"GITHUB_REPOSITORY": LOCK["repository"]["name"], "GITHUB_EVENT_NAME": "pull_request",
                   "GITHUB_REF": "refs/pull/84/merge", "GITHUB_SHA": source}
    return event, environment, source, [base, head]


def minimal_pe(*, dll=True):
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, 0x8664, 1, 0, 0, 0, 240, 0x2002 if dll else 2)
    struct.pack_into("<H", data, 152, 0x20B)
    struct.pack_into("<I", data, 152 + 108, 16)
    struct.pack_into("<IIII", data, 152 + 240 + 8, 512, 4096, 512, 512)
    return data


class ProductSdkBoundaries(unittest.TestCase):
    def test_compiler_metadata_cannot_replace_binary_inventory_identity(self):
        binary = LOCK["content"]["producer_compiler_binary"]
        root, name = binary["path"].rsplit("\\", 1)
        native = {root: {name: {k: binary[k] for k in ("bytes", "sha256")}}}
        receipt = {"tools": {"cl.exe": binary}, "configuration": {
            "compiler_file": LOCK["content"]["producer_compiler_metadata"]}}
        actual = product.producer_compiler_binding(receipt, native, LOCK)
        self.assertEqual(actual["binary"]["bytes"], 677776)
        self.assertEqual(actual["metadata_file"]["bytes"], 6603)
        self.assertNotEqual(actual["binary"]["sha256"], actual["metadata_file"]["sha256"])
        native[root][name] = receipt["configuration"]["compiler_file"]
        with self.assertRaisesRegex(product.Rejected, "ProducerCompilerBinaryBindingRejected"):
            product.producer_compiler_binding(receipt, native, LOCK)

    def test_raw_commit_parent_proof_survives_actual_shallow_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "repository.git"
            env = os.environ.copy()
            env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_AUTHOR_NAME="Synthetic fixture", GIT_COMMITTER_NAME="Synthetic fixture",
                       GIT_AUTHOR_EMAIL="fixture@example.invalid", GIT_COMMITTER_EMAIL="fixture@example.invalid")
            def command(*arguments, data=None):
                return subprocess.check_output(["git", "-C", str(root), *arguments], input=data,
                                               stderr=subprocess.PIPE, env=env, timeout=15).decode().strip()
            root.mkdir()
            command("init", "--bare", "--template=")
            tree = command("hash-object", "-w", "-t", "tree", "--stdin", data=b"")
            base = command("commit-tree", tree, "-m", "Synthetic base")
            head = command("commit-tree", tree, "-p", base, "-m", "Synthetic head")
            merge = command("commit-tree", tree, "-p", base, "-p", head, "-m", "Synthetic merge")
            command("update-ref", "refs/heads/fixed-fixture", merge)
            command("symbolic-ref", "HEAD", "refs/heads/fixed-fixture")
            (root / "shallow").write_text(merge + "\n")
            self.assertEqual(command("show", "-s", "--format=%P", "HEAD"), "")
            self.assertEqual(product.commit_header(root), {"tree_sha": tree, "parents": [base, head]})

    def test_only_original_expected_negative_producer_is_admitted(self):
        self.assertTrue(product.validate_producer(*producer_metadata(), LOCK, require_unexpired=True)["expected_negative_preserved"])
        for field, value in (("status", "in_progress"), ("conclusion", "success"), ("run_attempt", 2),
                             ("head_sha", "f" * 40)):
            with self.subTest(field=field):
                run, jobs, artifact = producer_metadata()
                run[field] = value
                with self.assertRaises(product.Rejected):
                    product.validate_producer(run, jobs, artifact, LOCK, require_unexpired=True)

    def test_patched_fixture_step_cannot_be_skipped_or_promoted_green(self):
        for value in ("success", "skipped", "cancelled"):
            run, jobs, artifact = producer_metadata()
            next(s for s in jobs["jobs"][0]["steps"] if s["number"] == 9)["conclusion"] = value
            with self.assertRaises(product.Rejected):
                product.validate_producer(run, jobs, artifact, LOCK, require_unexpired=True)

    def test_other_job_failure_cannot_masquerade_as_stock_negative(self):
        run, jobs, artifact = producer_metadata()
        next(s for s in jobs["jobs"][0]["steps"] if s["number"] == 8)["conclusion"] = "failure"
        with self.assertRaises(product.Rejected):
            product.validate_producer(run, jobs, artifact, LOCK, require_unexpired=True)

    def test_artifact_digest_owner_and_expiry_are_required(self):
        mutations = (lambda a: a.update(digest="sha256:" + "0" * 64),
                     lambda a: a["workflow_run"].update(id=0),
                     lambda a: a.update(expired=True),
                     lambda a: a.update(expires_at="2000-01-01T00:00:00Z"))
        for mutation in mutations:
            run, jobs, artifact = producer_metadata()
            mutation(artifact)
            with self.assertRaises(product.Rejected):
                product.validate_producer(run, jobs, artifact, LOCK, require_unexpired=True)

    def test_archive_identity_rejection_creates_no_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / "untrusted.zip"
            archive.write_bytes(b"not the original archive")
            target = root / "output"
            with self.assertRaisesRegex(product.Rejected, "OriginalArchiveIdentityRejected"):
                product.audit_archive(archive, target, LOCK, SDK, TRANSPORT)
            self.assertFalse(target.exists())

    def test_corrupted_extracted_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "data").write_bytes(b"actual")
            with self.assertRaisesRegex(product.Rejected, "ExtractedOriginalMemberChanged"):
                product.member(root, {"data": product.byte_id(b"expected")}, "data", SDK)

    def test_stock_and_output_ancestors_cannot_overlap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for paths in ((root, root), (root / "stock", root / "stock/new"),
                          (root / "stock", root / "evidence", root / "evidence/new")):
                with self.assertRaises(product.Rejected):
                    product.require_disjoint(paths)
            product.require_disjoint((root / "stock", root / "selected", root / "evidence"))

    def test_future_same_repo_test_and_main_prs_can_read_only_build(self):
        for base in ("test", "main"):
            result = product.event_source(*pr_event(base), LOCK)
            self.assertEqual(result["event_name"], "pull_request")
            self.assertEqual(result["ref"], "refs/pull/84/merge")

    def test_fork_wrong_parent_or_stale_merge_is_rejected(self):
        for mutation in ("fork", "parents", "source", "base"):
            event, env, source, parents = pr_event()
            if mutation == "fork":
                event["pull_request"]["head"]["repo"]["id"] = 1
            elif mutation == "parents":
                parents.reverse()
            elif mutation == "source":
                source = "e" * 40
            else:
                event["pull_request"]["base"]["ref"] = "unapproved-base"
            with self.assertRaises(product.Rejected):
                product.event_source(event, env, source, parents, LOCK)

    def test_later_test_push_requires_actual_event_source_and_ref(self):
        source = "a" * 40
        event = {"repository": {"id": LOCK["repository"]["id"]}, "ref": "refs/heads/test",
                 "after": source, "deleted": False}
        env = {"GITHUB_REPOSITORY": LOCK["repository"]["name"], "GITHUB_EVENT_NAME": "push",
               "GITHUB_REF": "refs/heads/test", "GITHUB_SHA": source}
        self.assertIsNone(product.event_source(event, env, source, ["b" * 40], LOCK)["pr_head_sha"])
        event["after"] = "c" * 40
        with self.assertRaises(product.Rejected):
            product.event_source(event, env, source, ["b" * 40], LOCK)

    def test_dispatch_ref_mismatch_cannot_select_another_checkout(self):
        event = {"repository": {"id": LOCK["repository"]["id"]}, "ref": "test"}
        env = {"GITHUB_REPOSITORY": LOCK["repository"]["name"], "GITHUB_EVENT_NAME": "workflow_dispatch",
               "GITHUB_REF": "refs/heads/test", "GITHUB_SHA": "a" * 40}
        product.event_source(event, env, "a" * 40, ["b" * 40], LOCK)
        event["ref"] = "main"
        with self.assertRaises(product.Rejected):
            product.event_source(event, env, "a" * 40, ["b" * 40], LOCK)

    def test_cmake_hook_rejects_literal_code_injection(self):
        for value in ('C:/kit;$ENV{TOKEN}', 'C:/kit"evil', "C:/kit\nset(x y)", "C:/kit$<1:other>"):
            with self.assertRaises(product.Rejected):
                product.capture_hook(value, {"source_sha": "a" * 40}, "b" * 64)

    def test_cmake_capture_duplicates_or_wrong_config_rejected(self):
        with self.assertRaises(product.Rejected):
            product.capture_values("schema=1\nschema=1\n")
        values = {key: "value" for key in ("schema", "source_sha", "content_id", "configuration", "qml_dll",
            "qml_import_library", "qml_private_includes", "application", "compiler", "compiler_version",
            "compiler_id", "cmake", "source_directory", "build_directory")}
        values.update(schema="1", configuration="Debug")
        with self.assertRaises(product.Rejected):
            product.capture_values("\n".join(k + "=" + v for k, v in values.items()))

    def test_pe_parser_requires_exact_amd64_kind_and_bounds(self):
        data = minimal_pe()
        self.assertEqual(product.pe_interface(data)["machine"], "AMD64")
        with self.assertRaises(product.Rejected):
            product.pe_interface(data, require_dll=False)
        with self.assertRaises(product.Rejected):
            product.pe_interface(data[:150])
        struct.pack_into("<H", data, 132, 0x14C)
        with self.assertRaises(product.Rejected):
            product.pe_interface(data)

    def test_pe_parser_checks_import_table_from_actual_bytes(self):
        data = minimal_pe(dll=False)
        struct.pack_into("<II", data, 152 + 120, 4096, 40)
        struct.pack_into("<IIIII", data, 512, 0, 0, 0, 4160, 4200)
        data[576:587] = b"Qt6Qml.dll\0"
        self.assertEqual(product.pe_interface(data, require_dll=False)["dependencies"], ["qt6qml.dll"])
        struct.pack_into("<I", data, 512 + 12, 0x7FFFFFFF)
        with self.assertRaises(product.Rejected):
            product.pe_interface(data, require_dll=False)

    def test_deployed_qml_and_plugins_must_match_selected_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "platforms").mkdir()
            for name, data in (("Qt6Qml.dll", b"selected-qml"), ("Swirl.exe", b"same-app"),
                               ("platforms/qwindows.dll", b"selected-platform")):
                (root / name).write_bytes(data)
            selected = {"bin/Qt6Qml.dll": product.byte_id(b"selected-qml"),
                        "plugins/platforms/qwindows.dll": product.byte_id(b"selected-platform")}
            app = {"path": str(root / "Swirl.exe"), **product.byte_id(b"same-app"),
                   "actual_pe_imports": ["qt6qml.dll"]}
            report = product.verify_deployment(root, selected, app, SDK)
            self.assertEqual(len(report["qt_files"]), 2)
            (root / "platforms/qwindows.dll").write_bytes(b"other-platform")
            with self.assertRaisesRegex(product.Rejected, "DeployedQtFileMismatch"):
                product.verify_deployment(root, selected, app, SDK)

    def test_unknown_qt_dll_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for name in ("Qt6Qml.dll", "Qt6Unreviewed.dll", "Swirl.exe"):
                (root / name).write_bytes(b"same")
            app = {"path": str(root / "Swirl.exe"), **product.byte_id(b"same"), "actual_pe_imports": ["qt6qml.dll"]}
            with self.assertRaisesRegex(product.Rejected, "UnmappedQtRuntimeDll"):
                product.verify_deployment(root, {"bin/Qt6Qml.dll": product.byte_id(b"same")}, app, SDK)

    def test_failure_before_composition_is_recorded_and_does_not_touch_stock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            stock = root / "stock"
            stock.mkdir()
            (stock / "untouched").write_bytes(b"original")
            evidence = root / "evidence"
            with mock.patch.object(product, "current_context", side_effect=product.Rejected("DeliberateSourceRejection")):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = product.main(["--repository", str(REPOSITORY), "compose", "--stock-kit", str(stock),
                        "--selected-kit", str(root / "selected"), "--evidence", str(evidence)])
            self.assertEqual(result, 1)
            self.assertEqual((stock / "untouched").read_bytes(), b"original")
            self.assertFalse((root / "selected").exists())
            self.assertEqual(product.read_json(evidence / "receipt.json")["errors"], ["DeliberateSourceRejection"])
            self.assertFalse((evidence / "selected-sdk.json").exists())

    def test_existing_or_stock_nested_evidence_is_never_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            stock, existing = root / "stock", root / "existing"
            stock.mkdir()
            existing.mkdir()
            (existing / "original").write_bytes(b"keep")
            for evidence in (existing, stock / "invalid-evidence"):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = product.main(["--repository", str(REPOSITORY), "compose", "--stock-kit", str(stock),
                        "--selected-kit", str(root / "selected"), "--evidence", str(evidence)])
                self.assertEqual(result, 1)
            self.assertEqual(list(stock.iterdir()), [])
            self.assertEqual([p.name for p in existing.iterdir()], ["original"])


class CmakeObservationBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.root, self.selected, self.repo, self.build = root, root / "selected", root / "repo", root / "build"
        for path in (self.repo / "src/Swirl.Quick", self.build / "Release",
                     self.selected / "bin", self.selected / "lib", self.selected / "include/QtQml/6.12.0/QtQml"):
            path.mkdir(parents=True)
        for name in ("Qt6", "Qt6Qml", "Qt6QmlPrivate"):
            (self.selected / "lib/cmake" / name).mkdir(parents=True)
        for name in ("bin/Qt6Qml.dll", "lib/Qt6Qml.lib"):
            (self.selected / name).write_bytes(b"test bytes; never executed")
        self.compiler, self.cmake = root / "cl.exe", root / "cmake.exe"
        self.compiler.write_bytes(b"compiler identity only")
        self.cmake.write_bytes(b"cmake identity only")
        self.context = {"source_sha": "a" * 40}
        self.lock = copy.deepcopy(LOCK)
        self.lock["content"]["producer_compiler_binary"] = product.file_id(self.compiler)
        self.hook = root / "selected-qt.cmake"
        self.hook.write_bytes(product.capture_hook(self.selected, self.context, self.lock["content"]["derived"]))
        self.receipt = {"cmake_capture_hook": {"path": str(self.hook), **product.file_id(self.hook)}}
        self.cache = {"CMAKE_BUILD_TYPE": "Release", "CMAKE_CXX_COMPILER": str(self.compiler),
                      "CMAKE_COMMAND": str(self.cmake), "CMAKE_PROJECT_TOP_LEVEL_INCLUDES": self.hook.as_posix(),
                      "CMAKE_CACHE_MAJOR_VERSION": "3", "CMAKE_CACHE_MINOR_VERSION": "31", "CMAKE_CACHE_PATCH_VERSION": "6"}
        self.cache.update({name + "_DIR": str(self.selected / "lib/cmake" / name)
                           for name in ("Qt6", "Qt6Qml", "Qt6QmlPrivate")})
        self.capture = {"schema": "1", "source_sha": "a" * 40, "content_id": self.lock["content"]["derived"],
            "configuration": "Release", "qml_dll": str(self.selected / "bin/Qt6Qml.dll"),
            "qml_import_library": str(self.selected / "lib/Qt6Qml.lib"),
            "qml_private_includes": ";".join(str(self.selected / n) for n in ("include/QtQml/6.12.0", "include/QtQml/6.12.0/QtQml")),
            "application": str(self.build / "Release/Swirl.exe"), "compiler": str(self.compiler),
            "compiler_version": self.lock["content"]["producer_compiler"]["CMAKE_CXX_COMPILER_VERSION"],
            "compiler_id": "MSVC", "cmake": str(self.cmake), "source_directory": str(self.repo / "src/Swirl.Quick"),
            "build_directory": str(self.build)}
        self.compiler_metadata = self.build / "CMakeFiles/3.31.6/CMakeCXXCompiler.cmake"
        self.compiler_metadata.parent.mkdir(parents=True)
        self.compiler_metadata.write_text('set(CMAKE_CXX_COMPILER "' + self.compiler.as_posix() + '")\n'
            'set(CMAKE_CXX_COMPILER_ID "MSVC")\n'
            'set(CMAKE_CXX_COMPILER_VERSION "' + self.capture["compiler_version"] + '")\n'
            'set(MSVC_CXX_ARCHITECTURE_ID x64)\n')

    def check(self):
        (self.build / "CMakeCache.txt").write_text("\n".join(k + ":STRING=" + v for k, v in self.cache.items()))
        (self.build / "swirl-selected-qt-Release.txt").write_text("\n".join(k + "=" + v for k, v in self.capture.items()))
        return product.validate_configuration(self.build, self.selected, self.repo, self.context,
                                               self.receipt, self.lock, SDK, require_application=False)

    def test_configuration_records_real_import_paths(self):
        result = self.check()
        self.assertEqual(result["actual_target"]["qml_dll"], str(self.selected / "bin/Qt6Qml.dll"))
        self.assertIsNone(result["application"])

    def test_stale_qt_cache_path_rejected(self):
        stale = self.root / "stock/lib/cmake/Qt6Qml"
        stale.mkdir(parents=True)
        self.cache["Qt6Qml_DIR"] = str(stale)
        with self.assertRaises(RuntimeError):
            self.check()

    def test_vs_compiler_metadata_is_mandatory_without_cache_entry(self):
        del self.cache["CMAKE_CXX_COMPILER"]
        result = self.check()
        self.assertEqual(result["configured_compiler"]["MSVC_CXX_ARCHITECTURE_ID"], "x64")
        self.compiler_metadata.write_text(self.compiler_metadata.read_text().replace("x64", "X86"))
        with self.assertRaisesRegex(product.Rejected, "GeneratedCompilerMetadataBindingChanged"):
            self.check()

    def test_unavailable_optional_qt_probe_is_recorded_but_required_qml_is_rejected(self):
        self.cache["Qt6WaylandClient_DIR"] = "Qt6WaylandClient_DIR-NOTFOUND"
        self.assertEqual(self.check()["unavailable_optional_qt_packages"], ["Qt6WaylandClient_DIR"])
        self.cache["Qt6Qml_DIR"] = "Qt6Qml_DIR-NOTFOUND"
        with self.assertRaisesRegex(product.Rejected, "RequiredQtCmakePackageMissing"):
            self.check()

    def test_actual_target_cannot_point_to_other_dll_despite_correct_cache(self):
        wrong = self.root / "other.dll"
        wrong.write_bytes(b"wrong")
        self.capture["qml_dll"] = str(wrong)
        with self.assertRaisesRegex(product.Rejected, "CmakeActualTargetPathRejected"):
            self.check()

    def test_hook_and_compiler_byte_mutations_are_rejected(self):
        self.hook.write_bytes(self.hook.read_bytes() + b"# mutated\n")
        with self.assertRaisesRegex(product.Rejected, "CmakeCaptureHookChanged"):
            self.check()
        self.hook.write_bytes(product.capture_hook(self.selected, self.context, self.lock["content"]["derived"]))
        self.compiler.write_bytes(b"changed compiler")
        with self.assertRaisesRegex(product.Rejected, "ProductCompilerDiffers"):
            self.check()

    def test_missing_private_header_path_rejected(self):
        self.capture["qml_private_includes"] = str(self.selected / "include/QtQml/6.12.0")
        with self.assertRaisesRegex(product.Rejected, "CmakePrivateHeaderClosureMissing"):
            self.check()

    def test_deferred_capture_runs_in_cmake_without_compiling_or_running_any_image(self):
        if not CMAKE:
            self.skipTest("CMake not available; native Windows product configure remains pending")
        # This is a language-NONE descriptor exercise, not a Qt or application
        # build. The harmless placeholder DLL/EXE contents are never loaded.
        app = self.root / "descriptor-app.exe"
        app.write_bytes(b"descriptor only; not an executable")
        source, build = self.root / "descriptor-source", self.root / "descriptor-build"
        source.mkdir()
        text = '''cmake_minimum_required(VERSION 3.24)
project(SelectedQtObservation LANGUAGES NONE)
add_library(Qt6::Qml SHARED IMPORTED)
set_target_properties(Qt6::Qml PROPERTIES IMPORTED_LOCATION_RELEASE "@DLL@" IMPORTED_IMPLIB_RELEASE "@LIB@")
add_library(Qt6::QmlPrivate INTERFACE IMPORTED)
set_target_properties(Qt6::QmlPrivate PROPERTIES INTERFACE_INCLUDE_DIRECTORIES "@INC@")
add_executable(Swirl IMPORTED)
set_target_properties(Swirl PROPERTIES IMPORTED_LOCATION_RELEASE "@APP@")
'''.replace("@DLL@", (self.selected / "bin/Qt6Qml.dll").as_posix()).replace("@LIB@", (self.selected / "lib/Qt6Qml.lib").as_posix()).replace("@INC@", self.capture["qml_private_includes"].replace("\\", "/")).replace("@APP@", app.as_posix())
        (source / "CMakeLists.txt").write_text(text)
        command = [str(CMAKE), "-S", str(source), "-B", str(build), "-DCMAKE_SYSTEM_NAME=Windows",
                   "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CONFIGURATION_TYPES=Release",
                   "-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES=" + self.hook.as_posix()]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode(errors="replace"))
        capture = product.capture_values((build / "swirl-selected-qt-Release.txt").read_text())
        self.assertEqual(Path(capture["qml_import_library"]), self.selected / "lib/Qt6Qml.lib")
        self.assertEqual(Path(capture["qml_dll"]), self.selected / "bin/Qt6Qml.dll")
        self.assertEqual(Path(capture["application"]), app)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=REPOSITORY)
    parser.add_argument("--cmake", type=Path, default=shutil.which("cmake"))
    args, remaining = parser.parse_known_args()
    REPOSITORY = args.repository.resolve(strict=True)
    CMAKE = args.cmake
    SDK, TRANSPORT = product.load_support(REPOSITORY, LOCK)
    unittest.main(argv=[sys.argv[0], *remaining])
