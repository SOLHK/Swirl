"""Direct negative controls for fixed original-byte product comparison admission."""
import importlib.util
import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("product_comparison_under_test", TOOLS / "RunQt612ProductRuntimeComparison.py")
product = importlib.util.module_from_spec(spec)
spec.loader.exec_module(product)
sdk = product.sdk


class ProductBoundaryTests(unittest.TestCase):
    def phase(self, **extra):
        plan = {"kind": "full-motion", "variant": "stock", "accepted": [0, 1], **extra}
        return sdk._ProductPhase(sdk._PRODUCT_FACTORY, plan, {})

    def test_product_capability_cannot_be_constructed_from_receipt_or_boolean(self):
        for token in (None, True, {}, {"success": True, "complete": True}):
            with self.subTest(token=token):
                with self.assertRaisesRegex(RuntimeError, "LiveProductCapabilityRequired"):
                    sdk._ProductPhase(token, {}, {})

    def test_generic_public_runner_has_no_product_or_compiler_capability_argument(self):
        parameters = inspect.signature(sdk.run_logged).parameters
        self.assertNotIn("product", parameters)
        self.assertNotIn("compiler", parameters)
        with mock.patch.object(sdk.os, "name", "nt"):
            with self.assertRaisesRegex(RuntimeError, "LiveProductCapabilityRequired"):
                sdk._run_logged([], ".", ".", "case", 1, product={"complete": True})

    def test_changed_manifest_pin_fails_before_parsing_or_runtime_enumeration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "manifest.json"
            path.write_text('{"all_1516_matched":true}', encoding="utf-8")
            with mock.patch.object(sdk, "read_json") as read:
                with self.assertRaisesRegex(RuntimeError, "ProductOriginalManifestPinMismatch"):
                    sdk.product_manifest(path)
                read.assert_not_called()

    def test_wrong_variant_and_extra_runtime_file_fail_closed(self):
        base = {"Swirl.exe": sdk.PRODUCT_EXE_PIN, "Qt6Qml.dll": sdk.PRODUCT_QML_PINS["stock"]}
        with mock.patch.object(sdk, "product_manifest", return_value=dict(base)):
            with mock.patch.object(sdk, "inventory", return_value={**base, "unknown.dll": {"bytes": 1, "sha256": "0"*64}}):
                with self.assertRaisesRegex(RuntimeError, "ProductRuntimeClosureMismatch"):
                    sdk.product_runtime_identity(Path("/unused"), Path("/unused"), "stock")
            with self.assertRaisesRegex(RuntimeError, "ProductVariantRejected"):
                sdk.product_runtime_identity(Path("/unused"), Path("/unused"), "release")

    def test_only_the_pinned_Qml_difference_is_accepted(self):
        base = {"Swirl.exe": sdk.PRODUCT_EXE_PIN, "swirl_api.dll": sdk.PRODUCT_RUST_PIN,
                "Qt6Qml.dll": sdk.PRODUCT_QML_PINS["stock"]}
        with mock.patch.object(sdk, "product_manifest", side_effect=lambda p: dict(base)):
            candidate = {**base, "Qt6Qml.dll": sdk.PRODUCT_QML_PINS["patched"]}
            with mock.patch.object(sdk, "inventory", return_value=candidate):
                self.assertEqual(sdk.product_runtime_identity(Path("/unused"), Path("/unused"), "patched"), candidate)
            with mock.patch.object(sdk, "inventory", return_value={**candidate, "swirl_api.dll": {"bytes": 1, "sha256": "0"*64}}):
                with self.assertRaisesRegex(RuntimeError, "ProductRuntimeClosureMismatch"):
                    sdk.product_runtime_identity(Path("/unused"), Path("/unused"), "patched")

    def test_actual_full_motion_child_path_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory).resolve()
            phase = self.phase(scratch=str(scratch))
            for role in ("rapid", "ready"):
                image = scratch / ("swirl-full-motion-" + "a"*32) / role / "app/Swirl.exe"
                self.assertEqual(phase.app_role(image), role)
            for relative in ("app/Swirl.exe", "swirl-full-motion-b/rapid/app/Swirl.exe",
                             "swirl-full-motion-" + "a"*32 + "/other/app/Swirl.exe"):
                with self.subTest(relative=relative):
                    with self.assertRaisesRegex(RuntimeError, "ProductUnexpectedSmokeImagePath"):
                        phase.app_role(scratch / relative)
            with self.assertRaisesRegex(RuntimeError, "ProductUnexpectedSmokeImagePath"):
                phase.app_role(scratch.parent / "foreign/Swirl.exe")

    def test_forced_cleanup_never_satisfies_product_exit_proof(self):
        with self.assertRaisesRegex(RuntimeError, "ProductRootOrJobRetirementUnproved"):
            self.phase().finish(None, {"process_signaled": True, "owned_job_empty": True,
                                      "forced_cleanup": True, "timed_out": False})

    def test_no_actual_module_observation_is_not_a_success_receipt(self):
        with self.assertRaisesRegex(RuntimeError, "ProductActualProcessCoverageIncomplete"):
            self.phase().finish(None, {"process_signaled": True, "owned_job_empty": True,
                                      "forced_cleanup": False, "timed_out": False})

    def test_missing_and_changed_files_are_both_preserved_in_closure_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            wrong = root / "changed.bin"
            wrong.write_bytes(b"changed")
            wanted = {"bytes": 1, "sha256": "0"*64}
            expected = {"missing.dll": wanted, "changed.dll": wanted}
            def sources(name, *unused):
                return (root / "absent.bin" if name == "missing.dll" else wrong), "test-controlled-file"
            with mock.patch.object(product, "recovery_source", side_effect=sources):
                result = product.restore_runtime(expected, root, root, {}, root / "output")
            self.assertFalse(result["all_1516_matched"])
            self.assertEqual({row["status"] for row in result["failures"]}, {"missing", "mismatch"})
            self.assertEqual(list((root / "output").iterdir()), [])

    def test_duplicate_suffix_cannot_choose_an_arbitrary_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaisesRegex(RuntimeError, "OriginalMemberMissingOrAmbiguous"):
                product.locate(root, {"a/receipt.json": {}, "b/receipt.json": {}}, "receipt.json")

    def test_original_diagnostic_uses_the_fixed_package_copy(self):
        with mock.patch.object(product, "locate", return_value=Path("/fixed-original")) as locate:
            source, origin = product.recovery_source("Swirl-diagnostics.txt", Path("/repo"),
                                                     Path("/package"), {}, Path("/cache"))
            self.assertEqual(origin, "original-package-text")
            self.assertEqual(source, Path("/fixed-original"))
            self.assertEqual(locate.call_args.args[2], "build-evidence/deployed-all-pages.log")

    def test_original_artifact_sha_is_required_before_zip_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "original.zip"
            path.write_bytes(b"not an archive")
            with mock.patch.object(product.zipfile, "ZipFile") as opened:
                with self.assertRaisesRegex(RuntimeError, "OriginalZipIdentityChanged"):
                    product.audit_zip(path, product.reader.TARGETS["sdk"])
                opened.assert_not_called()


@unittest.skipUnless(os.name == "nt", "Windows file-handle and ctypes ABI control required")
class ProductMultipleFilePinTests(unittest.TestCase):
    def test_two_actual_file_pins_remain_valid_after_each_others_abi_binding(self):
        import ctypes as c
        from ctypes import wintypes as w
        phase = sdk._ProductPhase(sdk._PRODUCT_FACTORY,
                                  {"kind": "full-motion", "variant": "stock", "accepted": [0, 1]}, {})
        phase.c, phase.w = c, w
        phase.k = c.WinDLL("kernel32", use_last_error=True)
        phase.k.CloseHandle.restype, phase.k.CloseHandle.argtypes = w.BOOL, [w.HANDLE]
        record = {"scope": "Two ordinary owned temporary files; no product or module execution",
                  "success": False, "validation_rounds": 0, "errors": []}
        try:
            with tempfile.TemporaryDirectory(prefix="swirl-product-pin-") as directory:
                root = Path(directory).resolve()
                first, second = root / "owned-first.bin", root / "owned-second.bin"
                first.write_bytes(b"first ordinary held file\n")
                second.write_bytes(b"second ordinary held file\n")
                try:
                    pins = [phase.pin_file({"path": str(path), **sdk.file_identity(path)})
                            for path in (first, second)]
                    self.assertIsNot(pins[0].k, pins[1].k)
                    self.assertIsNot(pins[0].k.GetFileInformationByHandle,
                                     pins[1].k.GetFileInformationByHandle)
                    self.assertIsNot(pins[0].FileInfo, pins[1].FileInfo)
                    for _ in range(4):
                        for pin in pins:
                            pin.validate_process_image(pin.expected["path"])
                        record["validation_rounds"] += 1
                    record["files"] = [{**pin.identity, "volume_serial": str(pin.identity["volume_serial"])}
                                       for pin in pins]
                finally:
                    phase.close(record)
                self.assertEqual(record["errors"], [])
                self.assertTrue(all(pin.handle is None for pin in phase.pins))
                # Actual held file handles are closed before temporary deletion.
                first.unlink(); second.unlink()
                record["success"] = True
        finally:
            if os.environ.get("SWIRL_QT612_RUNTIME_PATCH") == "1":
                output = Path(os.environ["GITHUB_WORKSPACE"]) / "build-evidence/qt612-runtime-patch/native-boundaries/product-multiple-held-files/receipt.json"
                sdk.write_json(output, record)


if __name__ == "__main__":
    unittest.main()
