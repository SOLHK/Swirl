"""Pure boundary controls only: no Qt execution, network, build or private data."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


sdk = load("sdk_boundary_tests", "Build-Qt612QmlDiagnosticSdk.py")
comparison = load("comparison_boundary_tests", "RunQt612RuntimeComparison.py")


class DiagnosticBoundaryTests(unittest.TestCase):
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
