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
import zipfile
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("product_sdk_under_test", HERE.parent / "Compose-Qt612ProductSdk.py")
product = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = product
spec.loader.exec_module(product)
producer_spec = importlib.util.spec_from_file_location("network_producer_under_test", HERE.parent / "Build-Qt612NetworkBackport.py")
producer = importlib.util.module_from_spec(producer_spec)
sys.modules[producer_spec.name] = producer
producer_spec.loader.exec_module(producer)
REPOSITORY = HERE.parents[1]
CMAKE = None
LOCK = product.load_lock()
SDK = TRANSPORT = None


def producer_metadata():
    p, a, repo = LOCK["producer"], LOCK["artifact"], LOCK["repository"]
    run = {"id": p["run"], "run_attempt": 1, "repository": {"id": repo["id"]},
           "head_repository": {"id": repo["id"]}, "head_sha": p["head"],
           "head_branch": repo["branch"], "path": p["workflow"], "event": "pull_request",
           "status": "completed", "conclusion": p["conclusion"]}
    jobs = {"total_count": 1, "jobs": [{"id": p["job"], "run_id": p["run"],
             "name": p["job_name"], "status": "completed", "conclusion": p["conclusion"],
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


def minimal_pe(*, dll=True, exports=()):
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, 0x8664, 1, 0, 0, 0, 240, 0x2002 if dll else 2)
    struct.pack_into("<H", data, 152, 0x20B)
    struct.pack_into("<I", data, 152 + 108, 16)
    struct.pack_into("<IIII", data, 152 + 240 + 8, 512, 4096, 512, 512)
    if exports:
        count = len(exports)
        struct.pack_into("<II", data, 152 + 112, 4096, 40)
        func_rva = 4136
        names_rva = func_rva + count * 4
        ords_rva = names_rva + count * 4
        strings_rva = ords_rva + count * 2
        struct.pack_into("<IIIIII", data, 512 + 16, 1, count, count, func_rva, names_rva, ords_rva)
        cursor = strings_rva
        for i, name in enumerate(exports):
            encoded = name.encode("ascii") + b"\0"
            struct.pack_into("<I", data, 512 + (func_rva - 4096) + i * 4, 4400 + i)
            struct.pack_into("<I", data, 512 + (names_rva - 4096) + i * 4, cursor)
            struct.pack_into("<H", data, 512 + (ords_rva - 4096) + i * 2, i)
            offset = 512 + (cursor - 4096)
            data[offset:offset + len(encoded)] = encoded
            cursor += len(encoded)
    return data


class SelectedD3dDeploymentBoundaries(unittest.TestCase):
    def fixture(self, root, data=None):
        selected, runtime = root / "selected", root / "runtime"
        (selected / "bin").mkdir(parents=True)
        runtime.mkdir()
        raw = bytes(minimal_pe()) if data is None else bytes(data)
        source = selected / "bin/d3dcompiler_47.dll"
        source.write_bytes(raw)
        return selected, runtime, source, raw, product.byte_id(raw)

    def test_exact_copy_records_replacement_and_does_not_modify_dxc(self):
        with tempfile.TemporaryDirectory() as temporary:
            selected, runtime, source, raw, expected = self.fixture(Path(temporary).resolve())
            destination = runtime / "d3dcompiler_47.dll"
            destination.write_bytes(b"different deployment source")
            dxc = runtime / "dxcompiler.dll"
            dxc.write_bytes(b"unexecuted external fixture")
            record = {}
            product.copy_fixed_d3d(selected, runtime, expected, SDK, record)
            self.assertEqual(destination.read_bytes(), raw)
            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual(record["before"], product.byte_id(b"different deployment source"))
            self.assertEqual(record["after"], expected)
            self.assertTrue(record["copied"])
            self.assertEqual(record["source"]["pe"]["machine"], "AMD64")
            self.assertEqual(record["shader_compilers_outside_selected_kit"],
                             {"dxcompiler.dll": product.byte_id(dxc.read_bytes())})
            second = {}
            product.copy_fixed_d3d(selected, runtime, expected, SDK, second)
            self.assertFalse(second["copied"])
            self.assertEqual(dxc.read_bytes(), b"unexecuted external fixture")

    def test_changed_selected_source_cannot_overwrite_existing_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            selected, runtime, source, raw, expected = self.fixture(Path(temporary).resolve())
            destination = runtime / "d3dcompiler_47.dll"
            destination.write_bytes(b"original")
            source.write_bytes(raw + b"mutation")
            with self.assertRaisesRegex(product.Rejected, "SelectedD3dCompilerChanged"):
                product.copy_fixed_d3d(selected, runtime, expected, SDK, {})
            self.assertEqual(destination.read_bytes(), b"original")

    def test_existing_shader_metadata_is_replaced_with_the_compatible_schema_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            selected, runtime, _, _, expected = self.fixture(Path(temporary).resolve())
            product.copy_fixed_d3d(selected, runtime, expected, SDK, {})
            path = runtime / "qt-shader-runtime.json"
            path.write_bytes(b"previous metadata")
            record = {}
            product.write_shader_runtime_metadata(runtime, expected, SDK, record)
            self.assertEqual(product.read_json(path), {"schema": 1, "source": "selected-qt-sdk",
                "files": {"d3dcompiler_47.dll": {"sha256": expected["sha256"], "bytes": expected["bytes"]}}})
            self.assertEqual(record["before"], product.byte_id(b"previous metadata"))
            self.assertEqual(record["after"], product.byte_id(path.read_bytes()))
            second = {}
            product.write_shader_runtime_metadata(runtime, expected, SDK, second)
            self.assertFalse(second["written"])

    def test_x86_or_executable_image_is_rejected_before_copy(self):
        for mutation in ("x86", "exe"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                raw = minimal_pe(dll=mutation != "exe")
                if mutation == "x86":
                    struct.pack_into("<H", raw, 132, 0x14C)
                selected, runtime, _, _, expected = self.fixture(Path(temporary).resolve(), raw)
                with self.assertRaisesRegex(product.Rejected, "D3dAmd64DllRequired"):
                    product.copy_fixed_d3d(selected, runtime, expected, SDK, {})
                self.assertEqual(list(runtime.iterdir()), [])

    def test_destination_inside_selected_kit_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            selected, _, source, raw, expected = self.fixture(Path(temporary).resolve())
            with self.assertRaises(product.Rejected):
                product.copy_fixed_d3d(selected, selected / "bin", expected, SDK, {})
            self.assertEqual(source.read_bytes(), raw)

    def test_atomic_replace_failure_keeps_previous_bytes_and_removes_owned_temporary(self):
        with tempfile.TemporaryDirectory() as temporary:
            selected, runtime, source, raw, expected = self.fixture(Path(temporary).resolve())
            destination = runtime / "d3dcompiler_47.dll"
            destination.write_bytes(b"original")
            record = {}
            with mock.patch.object(product.os, "replace", side_effect=OSError("synthetic replacement failure")):
                with self.assertRaises(OSError):
                    product.copy_fixed_d3d(selected, runtime, expected, SDK, record)
            self.assertEqual(destination.read_bytes(), b"original")
            self.assertEqual(source.read_bytes(), raw)
            self.assertFalse(record["copied"])
            self.assertFalse((runtime / ".swirl-selected-d3dcompiler-47.copy.tmp").exists())

    def test_failed_deployment_preserves_raw_observed_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            selected, runtime, _, _, expected = self.fixture(root)
            (runtime / "Swirl.exe").write_bytes(b"unexecuted application fixture")
            (runtime / "Qt6Qml.dll").write_bytes(b"unexecuted Qml fixture")
            (runtime / "d3dcompiler_47.dll").write_bytes(b"actual mismatched bytes")
            application = {"path": str(runtime / "Swirl.exe"),
                           **product.byte_id((runtime / "Swirl.exe").read_bytes()),
                           "actual_pe_imports": ["qt6qml.dll"]}
            files = {"bin/Qt6Qml.dll": product.byte_id((runtime / "Qt6Qml.dll").read_bytes()),
                     "bin/d3dcompiler_47.dll": expected}
            observation = root / "evidence/runtime-files-observed.json"
            with self.assertRaisesRegex(product.Rejected, "DeployedQtFileMismatch:d3dcompiler_47.dll"):
                product.verify_deployment(runtime, files, application, SDK,
                                          observed_inventory_path=observation)
            observed = product.read_json(observation)
            self.assertEqual(observed["d3dcompiler_47.dll"], product.byte_id(b"actual mismatched bytes"))
            self.assertEqual((runtime / "d3dcompiler_47.dll").read_bytes(), b"actual mismatched bytes")

    def test_true_receipt_without_source_and_lock_binding_cannot_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            selected, runtime, _, _, _ = self.fixture(root)
            stock = root / "stock"
            stock.mkdir()
            receipt = root / "untrusted-selected-sdk.json"
            product.write_json(receipt, {"schema": 1, "kind": "swirl-selected-qt612-product-sdk",
                "success": True, "consumer": {}, "producer": LOCK["producer"], "artifact": LOCK["artifact"],
                "stock_kit_root": str(stock), "kit_root": str(selected),
                "lock": {"bytes": 1, "sha256": "0" * 64}})
            evidence = root / "evidence"
            with mock.patch.object(product, "current_context", return_value={}), contextlib.redirect_stdout(io.StringIO()):
                result = product.main(["--repository", str(REPOSITORY), "copy-d3d", "--receipt", str(receipt),
                    "--runtime-dir", str(runtime), "--evidence", str(evidence)])
            self.assertEqual(result, 1)
            self.assertEqual(product.read_json(evidence / "receipt.json")["errors"],
                             ["SelectedReceiptBindingRejected"])
            self.assertEqual(list(runtime.iterdir()), [])


class ProductSdkBoundaries(unittest.TestCase):
    def test_compiler_metadata_cannot_replace_binary_inventory_identity(self):
        binary = LOCK["content"]["producer_compiler_binary"]
        root, name = binary["path"].rsplit("\\", 1)
        native = {root: {name: {k: binary[k] for k in ("bytes", "sha256")}}}
        receipt = {"tools": {"cl.exe": binary}, "configuration": {
            "compiler_file": LOCK["content"]["producer_compiler_metadata"]}}
        actual = product.producer_compiler_binding(receipt, native, LOCK)
        self.assertEqual(actual["binary"]["bytes"], 677736)
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
        wrong_conclusion = "failure" if LOCK["producer"]["conclusion"] == "success" else "success"
        for field, value in (("status", "in_progress"), ("conclusion", wrong_conclusion), ("run_attempt", 2),
                             ("head_sha", "f" * 40)):
            with self.subTest(field=field):
                run, jobs, artifact = producer_metadata()
                run[field] = value
                with self.assertRaises(product.Rejected):
                    product.validate_producer(run, jobs, artifact, LOCK, require_unexpired=True)

    def test_patched_fixture_step_cannot_be_skipped_or_promoted_green(self):
        expected = next(step for step in LOCK["producer"]["steps"] if step["number"] == 9)["conclusion"]
        for value in ({"success", "failure", "skipped", "cancelled"} - {expected}):
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
            "qml_import_library", "qml_private_includes", "network_dll", "network_import_library", "application", "compiler", "compiler_version",
            "compiler_id", "linker", "cmake", "source_directory", "build_directory")}
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


class InstalledEnvironmentBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.stock_root = r"D:\a\_temp\swirl-qt-6.12.0\6.12.0\msvc2022_64"

        class KitView:
            # Files are harmless test data on the current OS. Only the recorded
            # Windows installation path is represented separately; no image runs.
            def __init__(self, local, recorded):
                self.local, self.recorded = local, recorded
            def __str__(self):
                return self.recorded
            def __fspath__(self):
                return str(self.local)
            def __truediv__(self, name):
                return self.local / name

        self.stock = KitView(root / "stock", self.stock_root)
        self.selected = KitView(root / "selected", r"D:\a\_temp\swirl-qt-6.12.0-product")
        self.raw = product.qtenv2_bytes(self.stock_root)
        for kit in (self.stock, self.selected):
            (kit / "bin").mkdir(parents=True)
            (kit / "bin/qtenv2.bat").write_bytes(self.raw)
            (kit / "bin/Qt6Qml.dll").write_bytes(minimal_pe())
            (kit / "unchanged-header.h").write_bytes(b"fixed header\r\n")
        before, derived = SDK.inventory(self.stock), SDK.inventory(self.selected)
        for inventory in (before, derived):
            inventory["bin/qtenv2.bat"] = copy.deepcopy(LOCK["installation_qtenv2"]["producer_file"])
        pe = product.pe_interface(minimal_pe())
        self.artifact = {"stock_files": before, "derived_files": derived,
                         "receipt": {"stock_root": LOCK["installation_qtenv2"]["producer_kit_root"]},
                         "interface": {key: pe[key] for key in ("exports", "dependencies")}}

    def check(self):
        return product.actual_kit_check(self.stock, self.selected, self.artifact, LOCK, SDK)

    def test_exact_template_reproduces_both_independent_ci_inventory_hashes(self):
        self.assertEqual(product.byte_id(product.qtenv2_bytes(LOCK["installation_qtenv2"]["producer_kit_root"])),
                         {"bytes": 276, "sha256": "7c4c98a70e26f044f0ff664be29740cb135d03a028d69180e61db5d6dd35d36a"})
        self.assertEqual(product.byte_id(self.raw),
                         {"bytes": 244, "sha256": "41aa852760cdc69ea031be1a6401c934816e4d453129c4227331c983cb68e0fe"})
        self.assertEqual(self.raw.count(b"\r\n"), 5)

    def test_actual_whole_inventory_and_unchanged_stock_are_bound(self):
        original = copy.deepcopy(self.artifact)
        before, actual, binding = self.check()
        self.assertEqual(self.artifact, original)
        self.assertEqual(binding["stock_content_id"], product.canonical(SDK.inventory(self.stock)))
        self.assertEqual(binding["selected_content_id"], product.canonical(SDK.inventory(self.selected)))
        self.assertNotEqual(binding["selected_content_id"], LOCK["content"]["derived"])
        self.assertEqual((self.stock / "bin/qtenv2.bat").read_bytes(), self.raw)
        self.assertEqual((self.selected / "bin/qtenv2.bat").read_bytes(), self.raw)
        self.assertFalse(binding["qtenv2_executed"])
        self.assertEqual(before, actual)

    def test_line_endings_bom_extra_bytes_wrong_root_and_partial_replacement_rejected(self):
        old_root = LOCK["installation_qtenv2"]["producer_kit_root"].encode()
        mutations = (self.raw.replace(b"\r\n", b"\n"), b"\xef\xbb\xbf" + self.raw,
                     self.raw + b"\r\n", self.raw.replace(self.stock_root.encode(), old_root),
                     self.raw.replace(self.stock_root.encode(), old_root, 1),
                     self.raw.replace(b";%PATH%", b";C:\\untrusted;%PATH%"))
        for kit in (self.stock, self.selected):
            for data in mutations:
                with self.subTest(kit=str(kit), data=product.byte_id(data)):
                    (kit / "bin/qtenv2.bat").write_bytes(data)
                    with self.assertRaisesRegex(product.Rejected, "(?:InstalledOfficial|Selected)KitContentMismatch"):
                        self.check()
                    (kit / "bin/qtenv2.bat").write_bytes(self.raw)

    def test_second_changed_missing_or_extra_file_is_still_rejected(self):
        for kit in (self.stock, self.selected):
            path = kit / "unchanged-header.h"
            original = path.read_bytes()
            for mode in ("changed", "missing", "extra"):
                with self.subTest(kit=str(kit), mode=mode):
                    if mode == "changed":
                        path.write_bytes(original + b"changed")
                    elif mode == "missing":
                        path.unlink()
                    else:
                        (kit / "extra-file").write_bytes(b"unexpected")
                    with self.assertRaisesRegex(product.Rejected, "(?:InstalledOfficial|Selected)KitContentMismatch"):
                        self.check()
                    path.write_bytes(original)
                    if (kit / "extra-file").exists():
                        (kit / "extra-file").unlink()

    def test_producer_qtenv_root_and_original_file_identity_remain_pinned(self):
        for mutation in (lambda a: a["receipt"].update(stock_root=self.stock_root),
                         lambda a: a["stock_files"]["bin/qtenv2.bat"].update(bytes=244),
                         lambda a: a["derived_files"].pop("bin/qtenv2.bat")):
            artifact = copy.deepcopy(self.artifact)
            mutation(artifact)
            with self.assertRaisesRegex(product.Rejected, "ProducerQtEnvironmentIdentityRejected"):
                product.installation_inventories(self.stock_root, artifact, LOCK)

    def test_forged_actual_content_receipts_cannot_replace_recomputed_inventory(self):
        before, actual, binding = self.check()
        receipt = {key: binding[key] for key in ("stock_content_id", "selected_content_id",
                                                "producer_stock_content_id", "producer_selected_content_id")}
        receipt["installation_binding"] = binding
        product.validate_installed_identity(receipt, before, actual, binding, LOCK)
        for key in ("stock_content_id", "selected_content_id", "producer_stock_content_id", "producer_selected_content_id"):
            forged = copy.deepcopy(receipt)
            forged[key] = "f" * 64
            forged["installation_binding"][key] = "f" * 64
            with self.subTest(key=key), self.assertRaisesRegex(product.Rejected, "InstalledReceiptContentBindingRejected"):
                product.validate_installed_identity(forged, before, actual, binding, LOCK)

    def test_batch_metacharacters_ambiguous_and_non_windows_roots_rejected(self):
        for root in ("relative", "/tmp/kit", r"C:\Qt\..\other", "C:\\Qt\\", r"C:\Qt.",
                     r"C:\Qt%PATH%", r"C:\Qt&echo", r"\\server\share\Qt", "C:\\Qt\r\necho injected"):
            with self.subTest(root=root), self.assertRaisesRegex(product.Rejected, "QtEnvironmentRootRejected"):
                product.qtenv2_bytes(root)


class NetworkArtifactBoundaries(unittest.TestCase):
    def fixture(self, root):
        evidence = root / "network-sdk"
        evidence.mkdir()
        stock_dll = bytes(minimal_pe(exports=("alpha", "omega")))
        patched_dll = bytes(minimal_pe(exports=("alpha", "?maxRawHeaderSize@QHttpHeaderParser@@QEBA_JXZ", "omega")))
        module = {}
        for name in product.NETWORK_FILES:
            path = evidence / "module-install-output" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(patched_dll if name.endswith(".dll") else b"patched fixture")
            module[name] = product.file_id(path)
        snapshot = {"LICENSES/LGPL.txt": product.byte_id(b"license fixture"),
                    "src/network/access/qhttpnetworkreply.cpp": product.byte_id(b"patched source")}
        archive = evidence / "qtbase-corresponding-source.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for name, raw in (("LICENSES/LGPL.txt", b"license fixture"),
                              ("src/network/access/qhttpnetworkreply.cpp", b"patched source")):
                output.writestr("qtbase/" + name, raw)
        source = {"source": {"commit": "a" * 40}, "patches": [{"sha256": "b" * 64}],
                  "archive": product.file_id(archive), "file_manifest_content_id": product.canonical(snapshot),
                  "tracked_regular_files": len(snapshot), "tracked_bytes": sum(v["bytes"] for v in snapshot.values())}
        receipt = {"schema": 1, "kind": "swirl-qt612-network-backport", "success": True, "errors": [],
                   "source_sha": "c" * 40, "qt_version": "6.12.0", "architecture": "x86_64-windows-msvc",
                   "source": source["source"], "patches": source["patches"], "module_files": module,
                   "corresponding_source": source,
                   "source_inputs": {},
                   "stock_files": {name: product.byte_id(b"stock fixture") for name in product.NETWORK_FILES},
                   "compiler": {"binary": copy.deepcopy(LOCK["content"]["producer_compiler_binary"]),
                       "linker": {"path": "C:/fixture/link.exe", **product.byte_id(b"linker fixture")}, "metadata": {
                       "compiler_id": LOCK["content"]["producer_compiler"]["CMAKE_CXX_COMPILER_ID"],
                       "compiler_version": LOCK["content"]["producer_compiler"]["CMAKE_CXX_COMPILER_VERSION"],
                       "linker_version": "14." + LOCK["content"]["producer_compiler"]["CMAKE_CXX_COMPILER_VERSION"].split(".", 1)[1],
                       "msvc_architecture": "x64"}},
                   "features": {"stock": {"ssl": 1}, "patched": {"ssl": 1}, "verified": True},
                   "interface": {"stock": product.pe_interface(stock_dll), "patched": product.pe_interface(patched_dll)}}
        receipt["tools"] = {"cl.exe": copy.deepcopy(receipt["compiler"]["binary"]),
                            "link.exe": copy.deepcopy(receipt["compiler"]["linker"])}
        (evidence / "CMakeCache.txt").write_text("CMAKE_LINKER:FILEPATH=" + receipt["compiler"]["linker"]["path"] + "\n")
        (evidence / "CMakeCXXCompiler.cmake").write_text(
            'set(CMAKE_CXX_COMPILER "' + receipt["compiler"]["binary"]["path"] + '")\n'
            'set(CMAKE_CXX_COMPILER_ID "MSVC")\n'
            'set(CMAKE_CXX_COMPILER_VERSION "' + receipt["compiler"]["metadata"]["compiler_version"] + '")\n'
            'set(MSVC_CXX_ARCHITECTURE_ID "x64")\n')
        for name, data in (("receipt.json", receipt), ("module-files.json", module),
                           ("corresponding-source.json", source), ("source-snapshot-files.json", snapshot)):
            product.write_json(evidence / name, data)
        inventory = {p.relative_to(root).as_posix(): product.file_id(p) for p in root.rglob("*") if p.is_file()}
        lock = {"receipt": copy.deepcopy(receipt), "producer": {"head": receipt["source_sha"]},
                "critical_members": inventory,
                "artifact": {"artifact": 1}}
        return lock, inventory

    def test_network_overlay_changes_new_content_identity_without_changing_qml_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock, inventory = self.fixture(root)
            network = product.verify_network_artifact(root, inventory, lock, LOCK, SDK, TRANSPORT)
            before = {**network["receipt"]["stock_files"], "bin/Qt6Qml.dll": product.byte_id(b"stock qml")}
            qml = {**before, "bin/Qt6Qml.dll": product.byte_id(b"patched qml")}
            artifact = {"stock_files": before, "derived_files": qml}
            combined = product.with_network_artifact(artifact, network)
            self.assertEqual(artifact["derived_files"], qml)
            self.assertEqual(combined["derived_files"], {**qml, **network["module_files"]})
            self.assertNotEqual(product.canonical(combined["derived_files"]), product.canonical(qml))

    def test_network_overlay_rejects_already_changed_or_unrelated_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock, inventory = self.fixture(root)
            network = product.verify_network_artifact(root, inventory, lock, LOCK, SDK, TRANSPORT)
            before = dict(network["receipt"]["stock_files"])
            for name in product.NETWORK_FILES:
                changed = {**before, name: product.byte_id(b"unrelated overlay")}
                with self.assertRaisesRegex(product.Rejected, "NetworkOverlayBaselineRejected"):
                    product.with_network_artifact({"stock_files": before, "derived_files": changed}, network)

    def test_network_source_snapshot_and_abi_are_verified_beyond_receipt_success(self):
        for mutation in ("source", "abi", "features", "compiler", "linker", "module"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                lock, inventory = self.fixture(root)
                receipt_path = root / "network-sdk/receipt.json"
                receipt = product.read_json(receipt_path)
                if mutation == "source":
                    source_path = root / "network-sdk/corresponding-source.json"
                    source = product.read_json(source_path)
                    source["tracked_bytes"] += 1
                    source_path.write_text(json.dumps(source))
                    inventory["network-sdk/corresponding-source.json"] = product.file_id(source_path)
                elif mutation == "linker":
                    cache = root / "network-sdk/CMakeCache.txt"
                    cache.write_text("CMAKE_LINKER:FILEPATH=C:/another/link.exe\n")
                    inventory["network-sdk/CMakeCache.txt"] = product.file_id(cache)
                elif mutation == "abi":
                    receipt["interface"]["patched"]["exports"]["unexpected"] = 1
                elif mutation == "features":
                    receipt["features"]["patched"]["ssl"] = -1
                elif mutation == "compiler":
                    receipt["compiler"]["binary"]["sha256"] = "f" * 64
                else:
                    receipt["module_files"]["bin/other.dll"] = product.byte_id(b"unapproved")
                if mutation not in ("source", "linker"):
                    receipt_path.write_text(json.dumps(receipt))
                    inventory["network-sdk/receipt.json"] = product.file_id(receipt_path)
                    lock["receipt"] = receipt
                with self.assertRaises(product.Rejected):
                    product.verify_network_artifact(root, inventory, lock, LOCK, SDK, TRANSPORT)

    def test_network_pin_is_required_before_composition(self):
        with mock.patch.object(product, "read_json", return_value={"schema": 1, "status": "pending"}):
            with self.assertRaisesRegex(product.Rejected, "NetworkArtifactPinIncomplete"):
                product.load_network_lock()

    def test_network_maintenance_admission_keeps_old_qml_identity_and_rejects_other_toolsets(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock, _ = self.fixture(Path(temporary))
            compiler = lock["receipt"]["compiler"]
            compiler["binary"]["sha256"] = "e" * 64
            compiler["metadata"].update(compiler_version="19.44.35299.0", linker_version="14.44.35299.0")
            admitted = product.network_compiler_compatibility(compiler, LOCK)
            self.assertEqual(admitted["network_compiler_binary"]["sha256"], "e" * 64)
            self.assertEqual(admitted["qml_compiler_binary"], LOCK["content"]["producer_compiler_binary"])
            for field, value in (("compiler_version", "19.44.1.0"), ("compiler_version", "19.45.35299.0"),
                                 ("msvc_architecture", "x86"), ("linker_version", "14.44.35298.0")):
                changed = copy.deepcopy(compiler)
                changed["metadata"][field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(product.Rejected, "NetworkCompilerCompatibilityRejected"):
                    product.network_compiler_compatibility(changed, LOCK)

    def test_network_pe_interface_requires_exact_max_raw_header_size_export_and_ordinal_shift(self):
        added = "?maxRawHeaderSize@QHttpHeaderParser@@QEBA_JXZ"
        stock = {"machine": "AMD64", "dependencies": ["qt6core.dll", "ws2_32.dll"],
                 "exports": {"alpha": 1, "beta": 2, "gamma": 3, "omega": 4}}
        patched = {"machine": "AMD64", "dependencies": ["qt6core.dll", "ws2_32.dll"],
                   "exports": {"alpha": 1, "beta": 2, added: 3, "gamma": 4, "omega": 5}}
        for verifier, exc in ((producer.verify_network_pe_interface, RuntimeError),
                              (product.verify_network_pe_interface, product.Rejected)):
            verifier(stock, patched)
            for label, mutation in (
                    ("unpatched-identical-exports", lambda p: p.update(exports=copy.deepcopy(stock["exports"]))),
                    ("wrong-added-symbol", lambda p: p.update(exports={"alpha": 1, "beta": 2, "?other@QHttpHeaderParser@@QEBA_JXZ": 3, "gamma": 4, "omega": 5})),
                    ("extra-added-symbol", lambda p: p["exports"].update({"?extra@QHttpHeaderParser@@QEBA_JXZ": 6})),
                    ("missing-original-symbol", lambda p: p["exports"].pop("omega")),
                    ("wrong-ordinal-before-insertion", lambda p: p["exports"].update({"beta": 3})),
                    ("wrong-ordinal-after-insertion", lambda p: p["exports"].update({"gamma": 3})),
                    ("machine-mismatch", lambda p: p.update(machine="I386")),
                    ("dependency-mismatch", lambda p: p.update(dependencies=["qt6core.dll"])),
            ):
                candidate = copy.deepcopy(patched)
                mutation(candidate)
                with self.subTest(verifier=verifier.__module__, case=label), self.assertRaises(exc):
                    verifier(stock, candidate)

    def test_network_producer_must_match_successful_run_job_head_and_artifact(self):
        lock = copy.deepcopy(LOCK)
        lock["producer"]["event"] = "push"
        run, jobs, artifact = producer_metadata()
        run.update(event="push", conclusion="success")
        jobs["jobs"][0]["conclusion"] = "success"
        product.validate_network_producer(run, jobs, artifact, lock, require_unexpired=True)
        for target, key, replacement in (("run", "head_sha", "f" * 40),
                                         ("run", "conclusion", "failure"),
                                         ("job", "conclusion", "failure"),
                                         ("artifact", "digest", "sha256:" + "f" * 64),
                                         ("artifact", "expired", True)):
            changed_run, changed_jobs, changed_artifact = copy.deepcopy((run, jobs, artifact))
            changed = {"run": changed_run, "job": changed_jobs["jobs"][0], "artifact": changed_artifact}[target]
            changed[key] = replacement
            with self.subTest(target=target, key=key), self.assertRaises(product.Rejected):
                product.validate_network_producer(changed_run, changed_jobs, changed_artifact, lock,
                                                  require_unexpired=True)


class SelectedMsvcBoundaries(unittest.TestCase):
    def fixture(self, root):
        compiler = {"binary": {"sha256": "c" * 64}, "linker": {"sha256": "d" * 64},
                    "metadata": {"compiler_version": "19.44.35229.0", "linker_version": "14.44.35229.0"},
                    "crt": {"files": {}}}
        receipt = {"schema": 1, "kind": "msvc-app-local", "architecture": "x64",
                   "source": {"compiler_sha256": "c" * 64, "compiler_version": "19.44.35229.0"},
                   "required_imports": [], "files": {}}
        for name in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
            (root / name).write_bytes((name + " synthetic runtime bytes").encode())
            identity = product.file_id(root / name)
            # DLL servicing builds need not equal the compiler/linker counter.
            compiler["crt"]["files"][name] = {**identity, "version": "14.44.35211.0"}
            receipt["required_imports"].append(name)
            receipt["files"][name] = {"size": identity["bytes"], "sha256": identity["sha256"],
                                      "file_version": "14.44.35211.0", "machine": "0x8664", "signature_status": "Valid"}
        product.write_json(root / "msvc-runtime.json", receipt)
        return compiler, receipt

    def test_pinned_producer_crt_is_required_without_comparing_unrelated_servicing_counters(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiler, receipt = self.fixture(root)
            result = product.verify_msvc_payload(root, compiler, SDK)
            self.assertEqual(result["files"], compiler["crt"]["files"])
            self.assertEqual(result["compiler_sha256"], receipt["source"]["compiler_sha256"])

    def test_modified_runtime_is_rejected_even_with_a_rewritten_copy_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiler, receipt = self.fixture(root)
            path = root / "msvcp140.dll"
            path.write_bytes(b"same-version different runtime")
            identity = product.file_id(path)
            receipt["files"][path.name].update(size=identity["bytes"], sha256=identity["sha256"])
            (root / "msvc-runtime.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(product.Rejected, "SelectedMsvcRuntimeChanged"):
                product.verify_msvc_payload(root, compiler, SDK)

    def test_unmatched_compiler_missing_core_and_invalid_signature_receipts_are_rejected(self):
        for mutation in ("compiler", "core", "signature"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                compiler, receipt = self.fixture(root)
                if mutation == "compiler":
                    receipt["source"]["compiler_sha256"] = "e" * 64
                elif mutation == "core":
                    receipt["files"].pop("vcruntime140_1.dll")
                    receipt["required_imports"].remove("vcruntime140_1.dll")
                else:
                    receipt["files"]["msvcp140.dll"]["signature_status"] = "UnknownError"
                (root / "msvc-runtime.json").write_text(json.dumps(receipt))
                with self.assertRaises(product.Rejected):
                    product.verify_msvc_payload(root, compiler, SDK)

    def test_product_and_qa_bind_crt_after_existing_copy_before_runtime_execution(self):
        stage = (REPOSITORY / "scripts/Stage-WindowsRustProduct.ps1").read_text()
        qa = (REPOSITORY / ".github/workflows/build-qt-quick-ui.yml").read_text()
        for text, runtime_marker in ((stage, "--rust-core-self-test"), (qa, "& dist/Swirl.exe --tls-runtime-self-test")):
            self.assertLess(text.index("Copy-VerifiedMsvcRuntime.ps1"), text.index(" verify-msvc "))
            self.assertLess(text.index(" verify-msvc "), text.index(runtime_marker))


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
        for name in ("bin/Qt6Qml.dll", "lib/Qt6Qml.lib", "bin/Qt6Network.dll", "lib/Qt6Network.lib"):
            (self.selected / name).write_bytes(b"test bytes; never executed")
        self.compiler, self.linker, self.cmake = root / "cl.exe", root / "link.exe", root / "cmake.exe"
        self.compiler.write_bytes(b"compiler identity only")
        self.linker.write_bytes(b"linker identity only")
        self.cmake.write_bytes(b"cmake identity only")
        self.context = {"source_sha": "a" * 40}
        self.lock = copy.deepcopy(LOCK)
        self.lock["content"]["producer_compiler_binary"] = product.file_id(self.compiler)
        self.installed_content_id = "d" * 64
        self.hook = root / "selected-qt.cmake"
        self.hook.write_bytes(product.capture_hook(self.selected, self.context, self.installed_content_id))
        self.receipt = {"cmake_capture_hook": {"path": str(self.hook), **product.file_id(self.hook)},
                        "selected_content_id": self.installed_content_id}
        self.receipt["product_toolchain"] = {"binary": product.file_id(self.compiler),
            "linker": product.file_id(self.linker), "metadata": {"compiler_id": "MSVC",
                "compiler_version": self.lock["content"]["producer_compiler"]["CMAKE_CXX_COMPILER_VERSION"]}}
        self.cache = {"CMAKE_BUILD_TYPE": "Release", "CMAKE_CXX_COMPILER": str(self.compiler),
                      "CMAKE_COMMAND": str(self.cmake), "CMAKE_PROJECT_TOP_LEVEL_INCLUDES": self.hook.as_posix(),
                      "CMAKE_CACHE_MAJOR_VERSION": "3", "CMAKE_CACHE_MINOR_VERSION": "31", "CMAKE_CACHE_PATCH_VERSION": "6"}
        self.cache.update({name + "_DIR": str(self.selected / "lib/cmake" / name)
                           for name in ("Qt6", "Qt6Qml", "Qt6QmlPrivate")})
        self.capture = {"schema": "1", "source_sha": "a" * 40, "content_id": self.installed_content_id,
            "configuration": "Release", "qml_dll": str(self.selected / "bin/Qt6Qml.dll"),
            "qml_import_library": str(self.selected / "lib/Qt6Qml.lib"),
            "network_dll": str(self.selected / "bin/Qt6Network.dll"),
            "network_import_library": str(self.selected / "lib/Qt6Network.lib"),
            "qml_private_includes": ";".join(str(self.selected / n) for n in ("include/QtQml/6.12.0", "include/QtQml/6.12.0/QtQml")),
            "application": str(self.build / "Release/Swirl.exe"), "compiler": str(self.compiler),
            "compiler_version": self.lock["content"]["producer_compiler"]["CMAKE_CXX_COMPILER_VERSION"],
            "compiler_id": "MSVC", "linker": str(self.linker), "cmake": str(self.cmake), "source_directory": str(self.repo / "src/Swirl.Quick"),
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

    def test_producer_content_id_cannot_replace_actual_installed_capture(self):
        self.assertNotEqual(self.receipt["selected_content_id"], self.lock["content"]["derived"])
        self.check()
        self.capture["content_id"] = self.lock["content"]["derived"]
        with self.assertRaisesRegex(product.Rejected, "CmakeCaptureSourceChanged"):
            self.check()

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

    def test_network_import_library_cannot_point_outside_selected_sdk(self):
        wrong = self.root / "stock-network.lib"
        wrong.write_bytes(b"stock")
        self.capture["network_import_library"] = str(wrong)
        with self.assertRaisesRegex(product.Rejected, "CmakeActualTargetPathRejected:network_import_library"):
            self.check()

    def test_hook_and_compiler_byte_mutations_are_rejected(self):
        self.hook.write_bytes(self.hook.read_bytes() + b"# mutated\n")
        with self.assertRaisesRegex(product.Rejected, "CmakeCaptureHookChanged"):
            self.check()
        self.hook.write_bytes(product.capture_hook(self.selected, self.context, self.installed_content_id))
        self.compiler.write_bytes(b"changed compiler")
        with self.assertRaisesRegex(product.Rejected, "ProductCompilerDiffers"):
            self.check()

    def test_actual_linker_must_match_the_successful_network_producer(self):
        self.check()
        self.linker.write_bytes(b"unrelated linker servicing update")
        with self.assertRaisesRegex(product.Rejected, "ProductLinkerDiffersFromPinnedNetworkLinker"):
            self.check()

    def test_missing_private_header_path_rejected(self):
        self.capture["qml_private_includes"] = str(self.selected / "include/QtQml/6.12.0")
        with self.assertRaisesRegex(product.Rejected, "CmakePrivateHeaderClosureMissing"):
            self.check()

    def generate_descriptor_capture(self, *, includes=None, private_headers="TRUE", suffix="plain"):
        if not CMAKE:
            self.skipTest("CMake not available; native Windows product configure remains pending")
        # This is a language-NONE descriptor exercise, not a Qt or application
        # build. The harmless placeholder DLL/EXE contents are never loaded.
        app = self.root / "descriptor-app.exe"
        app.write_bytes(b"descriptor only; not an executable")
        source, build = self.root / ("descriptor-source-" + suffix), self.root / ("descriptor-build-" + suffix)
        source.mkdir()
        text = '''cmake_minimum_required(VERSION 3.24)
project(SelectedQtObservation LANGUAGES NONE)
add_library(Qt6::Qml SHARED IMPORTED)
set_target_properties(Qt6::Qml PROPERTIES IMPORTED_LOCATION_RELEASE "@DLL@" IMPORTED_IMPLIB_RELEASE "@LIB@" _qt_module_has_private_headers "@PRIVATE_HEADERS@")
add_library(Qt6::QmlPrivate INTERFACE IMPORTED)
set_target_properties(Qt6::QmlPrivate PROPERTIES INTERFACE_INCLUDE_DIRECTORIES "@INC@")
add_library(Qt6::Network SHARED IMPORTED)
set_target_properties(Qt6::Network PROPERTIES IMPORTED_LOCATION_RELEASE "@NETWORK_DLL@" IMPORTED_IMPLIB_RELEASE "@NETWORK_LIB@")
add_executable(Swirl IMPORTED)
set_target_properties(Swirl PROPERTIES IMPORTED_LOCATION_RELEASE "@APP@")
'''.replace("@DLL@", (self.selected / "bin/Qt6Qml.dll").as_posix()).replace("@LIB@", (self.selected / "lib/Qt6Qml.lib").as_posix()).replace("@INC@", includes if includes is not None else self.capture["qml_private_includes"].replace("\\", "/")).replace("@APP@", app.as_posix()).replace("@PRIVATE_HEADERS@", private_headers)
        text = text.replace("@NETWORK_DLL@", (self.selected / "bin/Qt6Network.dll").as_posix()).replace("@NETWORK_LIB@", (self.selected / "lib/Qt6Network.lib").as_posix())
        (source / "CMakeLists.txt").write_text(text)
        command = [str(CMAKE), "-S", str(source), "-B", str(build), "-DCMAKE_SYSTEM_NAME=Windows",
                   "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CONFIGURATION_TYPES=Release",
                   "-DCMAKE_LINKER=" + self.linker.as_posix(),
                   "-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES=" + self.hook.as_posix()]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode(errors="replace"))
        return product.capture_values((build / "swirl-selected-qt-Release.txt").read_text())

    def test_deferred_capture_runs_in_cmake_without_compiling_or_running_any_image(self):
        capture = self.generate_descriptor_capture()
        self.assertEqual(Path(capture["qml_import_library"]), self.selected / "lib/Qt6Qml.lib")
        self.assertEqual(Path(capture["qml_dll"]), self.selected / "bin/Qt6Qml.dll")
        self.assertEqual(Path(capture["application"]), self.root / "descriptor-app.exe")

    def conditional_private_includes(self, prefix):
        # Exact four-element form from the pinned Qt6QmlPrivateTargets.cmake.
        # The first two generator expressions produce empty list members.
        condition = "$<BOOL:$<TARGET_PROPERTY:Qt6::Qml,_qt_module_has_private_headers>>"
        return ";".join("$<" + condition + ":" + value + ">" for value in
                        ("", "", (prefix / "include/QtQml/6.12.0").as_posix(),
                         (prefix / "include/QtQml/6.12.0/QtQml").as_posix()))

    def test_actual_export_form_evaluates_before_private_header_validation(self):
        capture = self.generate_descriptor_capture(includes=self.conditional_private_includes(self.selected))
        self.assertNotIn("$<", capture["qml_private_includes"])
        self.assertEqual([p for p in capture["qml_private_includes"].split(";") if p],
                         [(self.selected / "include/QtQml/6.12.0").as_posix(),
                          (self.selected / "include/QtQml/6.12.0/QtQml").as_posix()])
        self.capture["qml_private_includes"] = capture["qml_private_includes"]
        self.check()

    def test_evaluated_disabled_private_headers_and_foreign_prefix_still_rejected(self):
        capture = self.generate_descriptor_capture(includes=self.conditional_private_includes(self.selected),
                                                   private_headers="FALSE", suffix="disabled")
        self.capture["qml_private_includes"] = capture["qml_private_includes"]
        with self.assertRaisesRegex(product.Rejected, "CmakePrivateHeaderClosureMissing"):
            self.check()
        foreign = self.root / "foreign"
        (foreign / "include/QtQml/6.12.0/QtQml").mkdir(parents=True)
        capture = self.generate_descriptor_capture(includes=self.conditional_private_includes(foreign), suffix="foreign")
        self.capture["qml_private_includes"] = capture["qml_private_includes"]
        with self.assertRaisesRegex(RuntimeError, "OutputEscapesOwnedRoot"):
            self.check()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=REPOSITORY)
    parser.add_argument("--cmake", type=Path, default=shutil.which("cmake"))
    args, remaining = parser.parse_known_args()
    REPOSITORY = args.repository.resolve(strict=True)
    CMAKE = args.cmake
    SDK, TRANSPORT = product.load_support(REPOSITORY, LOCK)
    unittest.main(argv=[sys.argv[0], *remaining])
