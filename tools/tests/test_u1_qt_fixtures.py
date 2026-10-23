"""Offline guards for the real ten-slot Qt evidence collector.

Synthetic XML here validates the gate, never counts as a Qt product test.
"""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("u1_qt_fixtures", ROOT / "tools/Run-U1QtFixtures.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class EvidenceGuards(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.xml = self.folder / "qt.xml"
        self.slot = "subscriptionProductChainAgainstIndependentPeer"

    def document(self, names=None, version="6.11.3"):
        root = ET.Element("TestCase", name="SwirlRustCoreTests")
        ET.SubElement(ET.SubElement(root, "Environment"), "QtVersion").text = version
        for name in ["initTestCase", *(names or [self.slot]), "cleanupTestCase"]:
            ET.SubElement(ET.SubElement(root, "TestFunction", name=name), "Incident", type="pass")
        return root

    def save(self, root):
        ET.ElementTree(root).write(self.xml, encoding="utf-8", xml_declaration=True)
        return self.xml

    def test_current_cpp_inventory_contains_exactly_the_ten_fixture_slots(self):
        source = (ROOT / "src/Swirl.Quick/tests/RustCoreTests.cpp").read_text(encoding="utf-8")
        self.assertEqual(gate.fixture_slots(source), gate.SLOTS)
        self.assertEqual(len(gate.SLOTS), 10)

    def test_complete_xml_requires_every_selected_slot(self):
        result = gate.verified_xml(self.save(self.document(sorted(gate.SLOTS))), sorted(gate.SLOTS), "6.11.3")
        self.assertTrue(result["success"])
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(len(result["slots"]), 10)

    def test_failure_skip_and_expected_failure_cannot_be_passes(self):
        for kind in ("fail", "skip", "xfail", "xpass"):
            with self.subTest(kind=kind):
                root = self.document()
                root.find("./TestFunction[@name='" + self.slot + "']/Incident").set("type", kind)
                observed = {}
                with self.assertRaises(AssertionError):
                    gate.verified_xml(self.save(root), [self.slot], "6.11.3", observation=observed)
                self.assertTrue(observed["xml_observed"])
                self.assertEqual(observed["skipped"], 1 if kind == "skip" else 0)

    def test_skip_messages_cannot_hide_behind_a_pass_incident(self):
        root = self.document()
        ET.SubElement(root.find("TestFunction"), "Message", type="skip")
        observed = {}
        with self.assertRaises(AssertionError):
            gate.verified_xml(self.save(root), [self.slot], "6.11.3", observation=observed)
        self.assertEqual(observed["skipped"], 1)

    def test_missing_or_duplicate_requested_slot_cannot_pass(self):
        for names in (["someOtherFunction"], [self.slot, self.slot]):
            with self.subTest(names=names), self.assertRaises(AssertionError):
                gate.verified_xml(self.save(self.document(names)), [self.slot], "6.11.3")

    def test_another_qt_version_cannot_pass(self):
        with self.assertRaises(AssertionError):
            gate.verified_xml(self.save(self.document(version="6.10.3")), [self.slot], "6.11.3")

    def test_missing_empty_or_malformed_xml_does_not_claim_zero_skips(self):
        for content in (None, "", "<broken"):
            if content is not None:
                self.xml.write_text(content, encoding="utf-8")
            observed = {"skipped": None, "xml_observed": False}
            with self.subTest(content=content), self.assertRaises((AssertionError, ET.ParseError)):
                gate.verified_xml(self.xml, [self.slot], "6.11.3", observation=observed)
            self.assertIsNone(observed["skipped"])
            self.assertFalse(observed["xml_observed"])

    def test_observer_preserves_original_harness_arguments_and_subprocess_result(self):
        binary = self.folder / "SwirlRustCoreTests.exe"
        observer = gate.QtObserver(binary, self.folder, "6.11.3")
        args = [str(binary), self.slot, "-o", "original.txt,txt"]
        environment = {"fixture": "unchanged"}
        result = subprocess.CompletedProcess(args, 0, "stdout", "stderr")
        calls = []

        def execute(actual, **options):
            calls.append((actual, options))
            self.assertEqual(actual[:-2], args)
            self.assertEqual(actual[-2], "-o")
            output = Path(actual[-1].removesuffix(",xml"))
            ET.ElementTree(self.document()).write(output, encoding="utf-8")
            return result

        observer.original_run = execute
        self.assertIs(observer.run(args, env=environment, capture_output=True, text=True, timeout=100), result)
        self.assertEqual(calls[0][1], {"env": environment, "capture_output": True, "text": True, "timeout": 100})
        self.assertTrue(observer.calls[0]["success"])
        self.assertEqual(observer.calls[0]["skipped"], 0)

    def test_subprocess_failure_cannot_hide_behind_pass_xml(self):
        binary = self.folder / "SwirlRustCoreTests.exe"
        observer = gate.QtObserver(binary, self.folder, "6.11.3")

        def execute(args):
            ET.ElementTree(self.document()).write(Path(args[-1].removesuffix(",xml")), encoding="utf-8")
            return subprocess.CompletedProcess(args, 1)

        observer.original_run = execute
        with self.assertRaises(AssertionError):
            observer.run([str(binary), self.slot])
        self.assertFalse(observer.calls[0]["success"])
        self.assertEqual(observer.calls[0]["exit_code"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
