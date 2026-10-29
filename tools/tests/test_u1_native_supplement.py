"""Fail-closed checks for the U1 scheduler, not substitute protocol results."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("u1_native_supplement", Path(__file__).parents[1] / "Run-U1NativeSupplement.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class SupplementGateTests(unittest.TestCase):
    def observed(self, case):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(case)
        expected = sorted(test.id() for test in runner.flatten(suite))
        log = io.StringIO()
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            result = runner.observe_tests(lambda: unittest.TextTestRunner().run(suite), expected, case.__module__)
        return result

    def test_existing_inventory_is_76_plus_explicit_qt_assignments_and_strict_two(self):
        actual = {}
        assignments = {}
        for name in runner.SUITES:
            suite, ids, assigned = runner.planned_suite(name)
            self.assertEqual(suite.countTestCases(), len(ids))
            self.assertEqual(len(set(ids)), len(ids))
            actual[name] = len(ids)
            assignments.update(assigned)
        self.assertEqual(sum(value for name, value in actual.items() if name != "strict-vmess"), 76)
        self.assertEqual(actual["strict-vmess"], 2)
        self.assertEqual(assignments, runner.QT_ASSIGNMENTS)
        self.assertEqual(len(assignments), 2)

    def test_real_unittest_success_records_the_actual_method(self):
        class Case(unittest.TestCase):
            def test_ok(self):
                self.assertEqual(1 + 1, 2)
        result = self.observed(Case)
        self.assertTrue(result["success"])
        self.assertEqual(result["runs"][0]["executed"], 1)
        self.assertEqual(result["runs"][0]["executed_ids"], result["expected_ids"])

    def test_skip_is_failure_even_when_unittest_was_successful(self):
        class Case(unittest.TestCase):
            @unittest.skip("not an acceptance result")
            def test_skip(self):
                pass
        result = self.observed(Case)
        self.assertFalse(result["success"])
        self.assertTrue(result["runs"][0]["successful"])
        self.assertEqual(result["runs"][0]["skipped"], 1)

    def test_subtest_failures_keep_method_count_separate_from_failure_count(self):
        class Case(unittest.TestCase):
            def test_subtests(self):
                for number in range(3):
                    with self.subTest(number=number):
                        self.assertEqual(number, -1)
        result = self.observed(Case)
        self.assertFalse(result["success"])
        self.assertEqual(result["runs"][0]["executed"], 1)
        self.assertEqual(result["runs"][0]["failures"], 3)

    def test_expected_failure_cannot_turn_a_compatibility_failure_green(self):
        class Case(unittest.TestCase):
            @unittest.expectedFailure
            def test_failure(self):
                self.fail("retained failure")
        result = self.observed(Case)
        self.assertFalse(result["success"])
        self.assertEqual(result["runs"][0]["expected_failures"], 1)

    def test_socks_inventory_rejects_new_unassigned_methods(self):
        module = __import__("test_socks4")
        with patch.object(module.Socks4Integration, "test_new_unassigned", lambda self: None, create=True):
            with self.assertRaisesRegex(RuntimeError, "SuitePartitionDrift"):
                runner.planned_suite("socks4")

    def test_reference_binary_source_and_repeat_must_all_match(self):
        lock = {"go_version": "go1.27.2", "xray": {"commit": "pinned"}, "reality": {"version": "pinned"}}
        revision = "1" * 40
        manifest = {"status": "success", "schema_version": 1, "swirl_source_commit": revision,
                    **lock, "binaries": {}, "reproducible_rebuild": {}}
        hashes = {}
        for index, (key, role) in enumerate((("xray", "source-xray"), ("reality_peer", "source-reality-peer"), ("utls_hello", "source-utls-hello"))):
            value = str(index) * 64
            hashes[role] = value
            manifest["binaries"][key] = {"sha256": value}
            manifest["reproducible_rebuild"][key] = {"matches": True, "first_sha256": value, "repeated_sha256": value}
        runner.validate_source_peer(manifest, lock, revision, hashes)
        for mutate in (
            lambda data: data.update(swirl_source_commit="2" * 40),
            lambda data: data["binaries"]["xray"].update(sha256="f" * 64),
            lambda data: data["reproducible_rebuild"]["utls_hello"].update(matches=False),
        ):
            changed = copy.deepcopy(manifest)
            mutate(changed)
            with self.assertRaises(RuntimeError):
                runner.validate_source_peer(changed, lock, revision, hashes)

    def test_summary_rejects_missing_failed_and_other_sha_receipts(self):
        identity = {"os": "Linux", "source_sha": "1" * 40}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertFalse(runner.collect_summary(output, identity)["success"])
            for phase in runner.required_phases("Linux"):
                runner.write_json(output / (phase + "-result.json"), {"phase": phase, "identity": identity, "success": True})
            self.assertTrue(runner.collect_summary(output, identity)["success"])
            target = output / "strict-vmess-result.json"
            document = json.loads(target.read_text())
            document["success"] = False
            runner.write_json(target, document)
            self.assertFalse(runner.collect_summary(output, identity)["success"])
            document["success"] = True
            document["identity"]["source_sha"] = "2" * 40
            runner.write_json(target, document)
            self.assertFalse(runner.collect_summary(output, identity)["success"])
        self.assertEqual(runner.required_phases("Windows"), ["deterministic", "strict-vmess"])
        self.assertEqual(runner.required_phases("Darwin"), ["deterministic", "strict-vmess"])

    def test_failed_suite_does_not_prevent_other_deterministic_suites(self):
        attempted = []
        def suite(name):
            attempted.append(name)
            if name == "reality-tls":
                raise RuntimeError("SyntheticGateFailure")
            return {"success": True}
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            arguments = ["runner", "--phase", "deterministic", "--output", directory]
            with patch.object(runner.sys, "argv", arguments), patch.object(runner, "configure", return_value=({}, None, None)), \
                    patch.object(runner, "identity", return_value={"source_sha": "1" * 40}), \
                    patch.object(runner, "command", return_value={"success": True}), patch.object(runner, "run_suite", side_effect=suite):
                outcome = runner.main()
            report = json.loads((Path(directory) / "deterministic-result.json").read_text())
        self.assertEqual(outcome, 1)
        self.assertEqual(attempted, [name for name in runner.SUITES if name != "strict-vmess"])
        self.assertEqual(len(report["stages"]), 9)
        self.assertFalse(report["success"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
