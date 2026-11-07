"""Offline boundary controls; actual source archives are exercised separately."""

import argparse
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock
import urllib.request
import zipfile


TOOLS = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("qt_product_source", TOOLS / "Prepare-Qt612ProductSource.py")
SOURCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SOURCE)


class ProductSourceControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.lock = SOURCE.source_lock()[1]

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def minimal_runtime(self):
        files = {"Qt6Core.dll": b"core", "Qt6Qml.dll": b"patched-qml",
                 "Qt6Svg.dll": b"svg", "translations/qt_zh_CN.qm": b"merged"}
        rules = {"root_dlls": {"Qt6Core.dll": "qtbase", "Qt6Qml.dll": "qtdeclarative",
                              "Qt6Svg.dll": "qtsvg"},
                 "plugins": {}, "qml_roots": ["qml/QtQuick/"],
                 "generated_translations": {"translations/qt_zh_CN.qm": SOURCE.sha(b"merged")},
                 "non_qt_root_dlls": ["swirl_api.dll"], "required_files": list(files)}
        lock = {**self.lock, "runtime_rules": rules}
        derived = {}
        for name, data in files.items():
            self.write("runtime/" + name, data)
            derived[SOURCE.sdk_name(name)] = {"bytes": len(data), "sha256": SOURCE.sha(data)}
        return self.root / "runtime", lock, derived

    def tar(self, entries, *, tag="a" * 40):
        path = self.root / "source.tar.xz"
        prefix = "qtbase-everywhere-src-6.12.0/"
        with tarfile.open(path, "w:xz") as archive:
            for name, data in [(".tag", (tag + "\n").encode()), ("CMakeLists.txt", b"project(QtBase)"),
                               ("LICENSES/LGPL-3.0-only.txt", b"test license fixture"), *entries]:
                info = tarfile.TarInfo(prefix + name)
                if data is None:
                    info.type, info.linkname = tarfile.SYMTYPE, "/outside"
                    archive.addfile(info)
                else:
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
        item = {"module": "qtbase", "commit": "a" * 40, **SOURCE.file_identity(path)}
        return path, item

    def package_fixture(self):
        directory = self.root / "bundle"
        directory.mkdir()
        receipt = {"schema": 1, "status": "complete", "source_sha": "a" * 40,
                   "runtime_files": {"Qt6Qml.dll": {"sha256": "c" * 64}},
                   "installer_notes": {"licenses/qt/SOURCE-BUNDLE.json": {"sha256": "d" * 64}}}
        receipt["runtime_content_id"] = SOURCE.sha(SOURCE.canonical(receipt["runtime_files"]))
        with zipfile.ZipFile(directory / "source.zip", "x") as container:
            container.writestr("bundle-manifest.json", SOURCE.json_bytes({
                k: receipt[k] for k in ["schema", "source_sha", "runtime_files", "runtime_content_id"]}))
        archive = {"filename": "source.zip", **SOURCE.file_identity(directory / "source.zip")}
        receipt["archive"] = archive
        self.write("bundle/qt-source-bundle.json", SOURCE.json_bytes(receipt))
        manifest = {"schema": 1, "source_sha": receipt["source_sha"],
                    "files": [{"path": p, "sha256": row["sha256"]}
                              for p, row in {**receipt["runtime_files"], **receipt["installer_notes"]}.items()]}
        self.write("package.json", SOURCE.json_bytes(manifest))
        delivery = {"source_sha": receipt["source_sha"], "qt": "6.12.0", "installer_sha256": "e" * 64,
                    "qt_source_archive": archive,
                    "qt_source_manifest_sha256": SOURCE.file_identity(directory / "qt-source-bundle.json")["sha256"]}
        self.write("delivery.json", SOURCE.json_bytes(delivery))
        args = argparse.Namespace(bundle_dir=directory, package_manifest=self.root / "package.json",
                                  delivery=self.root / "delivery.json")
        return args, manifest, delivery

    def test_actual_release_scope_excludes_qa_and_unknown_modules(self):
        rules = self.lock["runtime_rules"]
        self.assertEqual(SOURCE.classify_runtime("Qt6QuickControls2.dll", rules), "qtdeclarative")
        for name in ["Qt6Test.dll", "platforms/qoffscreen.dll", "Qt6WebEngineCore.dll",
                     "Qt6ShaderTools.dll", "qml/QtQuick3D/plugin.dll", "unexpected/native.dll"]:
            with self.subTest(name=name), self.assertRaises(SOURCE.SourceError):
                SOURCE.classify_runtime(name, rules)

    def test_runtime_actual_bytes_and_module_closure(self):
        runtime, lock, derived = self.minimal_runtime()
        rows, excluded = SOURCE.verify_runtime(runtime, lock, derived)
        self.assertEqual(len(rows), 4)
        self.assertEqual(excluded, [])
        (runtime / "Qt6Qml.dll").write_bytes(b"stock-qml")
        with self.assertRaisesRegex(SOURCE.SourceError, "RuntimeSdkIdentityMismatch"):
            SOURCE.verify_runtime(runtime, lock, derived)

    def test_missing_runtime_module_is_not_silently_omitted(self):
        runtime, lock, derived = self.minimal_runtime()
        (runtime / "Qt6Svg.dll").unlink()
        with self.assertRaisesRegex(SOURCE.SourceError, "RequiredQtRuntimeMissing"):
            SOURCE.verify_runtime(runtime, lock, derived)

    def test_same_named_translation_index_is_not_accepted_as_merged_output(self):
        runtime, lock, derived = self.minimal_runtime()
        (runtime / "translations/qt_zh_CN.qm").write_bytes(b"sdk dependency index")
        with self.assertRaisesRegex(SOURCE.SourceError, "GeneratedTranslationIdentityMismatch"):
            SOURCE.verify_runtime(runtime, lock, derived)

    def test_source_paths_reject_traversal_and_ambiguous_names(self):
        for name in ["../escape", "/absolute", "C:/drive", "dir\\file", "a//b", "a/./b", "a\0b"]:
            with self.subTest(name=name), self.assertRaisesRegex(SOURCE.SourceError, "ArchivePathRejected"):
                SOURCE.relative_name(name)

    def test_official_archive_requires_pinned_tag_and_preserves_licenses(self):
        path, item = self.tar([])
        result, notices = SOURCE.inspect_official_archive(path, item, self.lock["limits"])
        self.assertEqual(result["tag_commit"], "a" * 40)
        self.assertIn("LICENSES/LGPL-3.0-only.txt", notices)
        item["commit"] = "b" * 40
        with self.assertRaisesRegex(SOURCE.SourceError, "OfficialSourceProvenanceMismatch"):
            SOURCE.inspect_official_archive(path, item, self.lock["limits"])

    def test_archive_path_and_link_controls_do_not_extract(self):
        for name, data in [("../escape", b"x"), ("link", None), (".tag", b"duplicate")]:
            with self.subTest(name=name):
                path, item = self.tar([(name, data)])
                with self.assertRaises(SOURCE.SourceError):
                    SOURCE.inspect_official_archive(path, item, self.lock["limits"])
                self.assertFalse((self.root / "escape").exists())

    def test_archive_expansion_bound_is_enforced(self):
        path, item = self.tar([])
        with self.assertRaisesRegex(SOURCE.SourceError, "SourceArchiveBoundExceeded"):
            SOURCE.inspect_official_archive(path, item, {**self.lock["limits"], "archive_uncompressed_bytes": 1})

    def test_corrupt_cached_source_is_rejected_before_network(self):
        item = dict(self.lock["official_sources"][0])
        self.write("cache/" + item["archive"], b"corrupt")
        with mock.patch.object(SOURCE.urllib.request, "build_opener") as request:
            with self.assertRaisesRegex(SOURCE.SourceError, "CachedSourceIdentityMismatch"):
                SOURCE.acquire_archive(item, self.root / "cache", 1)
            request.assert_not_called()

    def test_non_official_source_url_and_downgrade_redirect_are_rejected(self):
        item = {**self.lock["official_sources"][0], "url": "https://unrelated.invalid/source.tar.xz"}
        with mock.patch.object(SOURCE.urllib.request, "build_opener") as request:
            with self.assertRaisesRegex(SOURCE.SourceError, "SourceUrlRejected"):
                SOURCE.acquire_archive(item, self.root / "cache", 1)
            request.assert_not_called()
        handler = SOURCE.HttpsRedirects()
        req = urllib.request.Request("https://download.qt.io/source")
        for destination in ["http://mirror.invalid/source", "https://user:password@mirror.invalid/source"]:
            with self.assertRaisesRegex(SOURCE.SourceError, "SourceRedirectRejected"):
                handler.redirect_request(req, None, 302, "Found", {}, destination)

    def test_modified_archive_requires_every_manifest_member(self):
        path = self.root / "modified.zip"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("qtdeclarative/LICENSES/LGPL-3.0-only.txt")
            info.external_attr = 0o100644 << 16
            archive.writestr(info, b"license fixture")
        snapshot = {"LICENSES/LGPL-3.0-only.txt": {"bytes": 15, "sha256": SOURCE.sha(b"license fixture")},
                    "missing.cpp": {"bytes": 1, "sha256": SOURCE.sha(b"x")}}
        source = {"archive": SOURCE.file_identity(path), "tracked_regular_files": 2, "tracked_bytes": 16}
        with self.assertRaisesRegex(SOURCE.SourceError, "ModifiedSourceClosureMismatch"):
            SOURCE.inspect_modified_archive(path, source, snapshot, self.lock["limits"])

    def test_preparation_never_overwrites_existing_notes(self):
        runtime = self.root / "runtime"
        self.write("runtime/licenses/qt/keep.txt", b"preserve")
        sdk = self.root / "sdk"
        sdk.mkdir()
        args = argparse.Namespace(source_sha="a" * 40, runtime_dir=runtime, sdk_evidence=sdk,
                                  output_dir=self.root / "output", cache_dir=self.root / "cache")
        with self.assertRaisesRegex(SOURCE.SourceError, "InstallerQtNotesAlreadyExist"):
            SOURCE.prepare(args)
        self.assertEqual((runtime / "licenses/qt/keep.txt").read_bytes(), b"preserve")
        self.assertFalse((self.root / "output").exists())

    def test_final_package_binding_records_exact_delivery_without_workflow_claim(self):
        args, _, delivery = self.package_fixture()
        result = SOURCE.verify_package(args)
        self.assertEqual(result["delivery"], delivery)
        self.assertFalse(result["whole_workflow_final_conclusion_checked_here"])
        self.assertTrue((self.root / "bundle/package-binding.json").is_file())
        before = (self.root / "bundle/delivery-packaging-snapshot.json").read_bytes()
        self.write("delivery.json", b'{"later_workflow_result": "changed"}\n')
        self.assertEqual(SOURCE.sha(before), result["delivery_receipt"]["sha256"])
        self.assertEqual(result["stable_delivery_fields"]["installer_sha256"], "e" * 64)

    def test_final_package_rejects_changed_qt_payload_and_notes(self):
        args, manifest, _ = self.package_fixture()
        for row in manifest["files"]:
            original = row["sha256"]
            row["sha256"] = "f" * 64
            self.write("package.json", SOURCE.json_bytes(manifest))
            with self.assertRaisesRegex(SOURCE.SourceError, "PackagedQtOrSourceNoticeChanged"):
                SOURCE.verify_package(args)
            self.assertFalse((self.root / "bundle/package-binding.json").exists())
            row["sha256"] = original

    def test_final_package_rejects_wrong_source_and_archive_delivery_link(self):
        args, _, delivery = self.package_fixture()
        delivery["source_sha"] = "f" * 40
        self.write("delivery.json", SOURCE.json_bytes(delivery))
        with self.assertRaisesRegex(SOURCE.SourceError, "PackageSourceIdentityMismatch"):
            SOURCE.verify_package(args)
        delivery["source_sha"] = "a" * 40
        delivery["qt_source_archive"] = {**delivery["qt_source_archive"], "sha256": "f" * 64}
        self.write("delivery.json", SOURCE.json_bytes(delivery))
        with self.assertRaisesRegex(SOURCE.SourceError, "DeliverySourceBindingMismatch"):
            SOURCE.verify_package(args)

    def test_final_package_rejects_new_qt_module_and_corrupt_source_zip(self):
        args, manifest, _ = self.package_fixture()
        manifest["files"].append({"path": "Qt6WebEngineCore.dll", "sha256": "f" * 64})
        self.write("package.json", SOURCE.json_bytes(manifest))
        with self.assertRaisesRegex(SOURCE.SourceError, "UnknownRuntimeLibrary"):
            SOURCE.verify_package(args)
        self.write("bundle/source.zip", b"changed after preparation")
        with self.assertRaisesRegex(SOURCE.SourceError, "SourceBundleIdentityMismatch"):
            SOURCE.verify_package(args)

    def test_bundle_verifies_payload_sha_not_only_recomputed_zip_crc(self):
        path = self.root / "bundle.zip"
        with zipfile.ZipFile(path, "w") as container:
            container.writestr("source.tar.xz", b"changed cache bytes before ZIP creation")
        expected = {"source.tar.xz": {"bytes": 5, "sha256": SOURCE.sha(b"known")}}
        with self.assertRaisesRegex(SOURCE.SourceError, "SourceBundleMemberIdentityMismatch"):
            SOURCE.verify_bundle_members(path, expected)

    def test_source_receipt_cannot_rebind_unchanged_source_container(self):
        args, _, _ = self.package_fixture()
        path = self.root / "bundle/qt-source-bundle.json"
        receipt = SOURCE.read_json(path)
        receipt["runtime_files"]["Qt6Qml.dll"]["sha256"] = "f" * 64
        path.write_bytes(SOURCE.json_bytes(receipt))
        with self.assertRaisesRegex(SOURCE.SourceError, "SourceBundleReceiptMismatch"):
            SOURCE.verify_package(args)


if __name__ == "__main__":
    unittest.main()
