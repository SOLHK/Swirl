"""Prevent font CI's XML summary from silently reporting skipped tests as green."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("font_report", Path(__file__).resolve().parents[1] / "SummarizeFontTests.py")
font_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(font_report)


class FontCiReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.selection = {
            "initTestCase": "pass", "defaultSelectionAndPersistence": "pass",
            "importKeepsOriginalFile": "pass", "malformedImportPreservesState": "pass",
            "optionalMetadataReplacement": "pass", "optionalCffImport": "pass",
            "automaticAxesRespectDesignAndDpi": "pass", "manualProfilesAndAutomaticRestore": "pass",
            "automaticProfilesRestartAcrossProcess": "pass", "legacyAxisSettingsArePreserved": "pass",
            "automaticAxesProduceRealGlyphsAndFallback": "pass", "fontCachesAreBoundedAndStable": "pass",
            "displayContextHasBoundedLifecycle": "pass", "qmlLiveAutomaticFonts": "pass",
            "fontDisplayContextLifetime": "pass", "previewFontResourcesInvalidateRaster": "pass",
            "previewWindowMetricsAndIdleStability": "pass",
            "previewRepeatedAxesReuseResources": "pass",
            "automaticWidthUsesRealAdvances": "pass",
            "importOptionalPingFangUiCollection": "skip", "cleanupTestCase": "pass",
        }
        self.write("font-selection.xml", self.selection)
        self.write("font-axis-policy.xml", {"originalDesignerDefaults": "pass"})

    def write(self, name, cases):
        root = ET.Element("TestCase", name="FontTests")
        for name_, status in cases.items():
            function = ET.SubElement(root, "TestFunction", name=name_)
            incident = ET.SubElement(function, "Incident", type=status)
            if status == "skip":
                ET.SubElement(incident, "Description").text = "Local font fixture required"
        ET.ElementTree(root).write(self.root / name, encoding="utf-8", xml_declaration=True)

    def test_skipped_private_fixture_is_separate_from_passes(self):
        result = font_report.summarize(self.root, False)
        self.assertEqual(result["countsExcludingLifecycle"], {"pass": 19, "skip": 1})
        self.assertEqual(result["errors"], [])
        self.assertFalse(result["physicalDpiVerified"])
        self.assertFalse(result["refresh240HzVerified"])

    def test_required_synthetic_fixture_skip_fails_gate(self):
        for name in ("optionalMetadataReplacement", "automaticWidthUsesRealAdvances", "previewRepeatedAxesReuseResources"):
            with self.subTest(name=name):
                skipped = dict(self.selection)
                skipped[name] = "skip"
                self.write("font-selection.xml", skipped)
                result = font_report.summarize(self.root, False)
                self.assertTrue(any(name in error for error in result["errors"]))

    def test_private_physical_identity_skip_is_reported_as_unverified(self):
        self.selection["optionalPhysicalFontIdentity"] = "skip"
        self.write("font-selection.xml", self.selection)
        result = font_report.summarize(self.root, False)
        self.assertEqual(result["countsExcludingLifecycle"], {"pass": 19, "skip": 2})
        self.assertEqual(result["errors"], [])
        self.assertFalse(result["physicalDpiVerified"])
        self.assertFalse(result["refresh240HzVerified"])
        actual = [case for case in result["cases"] if case["function"] == "optionalPhysicalFontIdentity"]
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0]["status"], "skip")

    def test_failed_private_physical_identity_still_fails_gate(self):
        self.selection["optionalPhysicalFontIdentity"] = "fail"
        self.write("font-selection.xml", self.selection)
        result = font_report.summarize(self.root, False)
        self.assertTrue(any("optionalPhysicalFontIdentity: fail" in error for error in result["errors"]))
        self.assertEqual(result["countsExcludingLifecycle"], {"pass": 19, "skip": 1})

    def test_missing_or_truncated_report_fails_gate(self):
        for contents in (None, "<TestCase><TestFunction>"):
            path = self.root / "font-axis-policy.xml"
            if contents is None:
                path.unlink()
            else:
                path.write_text(contents)
            self.assertTrue(font_report.summarize(self.root, False)["errors"])

    def test_windows_native_gate_cannot_be_absent_or_skipped(self):
        self.assertTrue(font_report.summarize(self.root, True)["errors"])
        complete = {"nativeGlyphsHaveNoColourFringes": "pass", "previewRepeatedAxesReuseResources": "pass"}
        for name in complete:
            for status in (None, "skip"):
                with self.subTest(name=name, status=status):
                    cases = dict(complete)
                    if status is None:
                        del cases[name]
                    else:
                        cases[name] = status
                    self.write("font-native-raster.xml", cases)
                    self.assertTrue(any(name in error for error in font_report.summarize(self.root, True)["errors"]))
        self.write("font-native-raster.xml", complete)
        self.assertEqual(font_report.summarize(self.root, True)["errors"], [])

    def test_failed_lifecycle_is_retained_as_failure(self):
        self.selection["initTestCase"] = "fail"
        self.write("font-selection.xml", self.selection)
        self.assertTrue(any("initTestCase" in error for error in font_report.summarize(self.root, False)["errors"]))

    def test_skipped_policy_case_is_not_optional(self):
        self.write("font-axis-policy.xml", {"originalDesignerDefaults": "skip"})
        self.assertTrue(font_report.summarize(self.root, False)["errors"])

    def test_new_public_case_cannot_silently_skip(self):
        self.selection["automaticModeUsesActualQmlControl"] = "skip"
        self.write("font-selection.xml", self.selection)
        self.assertTrue(any("Unexpected public font case skip" in error for error in font_report.summarize(self.root, False)["errors"]))

    def test_missing_registered_qml_or_restart_case_fails_gate(self):
        for name in ("qmlLiveAutomaticFonts", "automaticProfilesRestartAcrossProcess", "previewRepeatedAxesReuseResources"):
            with self.subTest(name=name):
                missing = dict(self.selection)
                del missing[name]
                self.write("font-selection.xml", missing)
                self.assertTrue(any(name in error for error in font_report.summarize(self.root, False)["errors"]))


if __name__ == "__main__":
    unittest.main()
