"""Aggregate publication boundary regressions using invented sentinel data only."""
import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import b1_original_metric_check as metric
import b1_original_vorg_ablation as ablation


class PublicOutputTests(unittest.TestCase):
    def test_closed_typed_schema_drops_every_original_data_container(self):
        secret = {"glyph_id": 1234567, "native_metrics": {"advance_width": 987654.125},
                  "native_binary64_bits": "PRIVATE_BITS", "source_path": "PRIVATE_PATH"}
        report = {key: copy.deepcopy(secret) for key in (
            "observations", "variants", "physical_face_identities", "directory_patch_verification",
            "failure", "cleanup_failure", "sampled_faces", "sampled_glyphs", "plan",
            "platform", "source_sha256", "observed_source_sha256", "source_commit",
            "native_binary_sha256", "unknown_future_field")}
        report.update(status="STRICT_ORIGINAL_METRIC_CHECK_FAILED", diagnostics_complete=True,
                      strict_metric_failures=3, original_font_accepted=False,
                      native_finalization={"request_count": 15, "extra": secret},
                      comparison={"samples": 60, "original_repeat_binary64_exact": True,
                                  "differences": secret},
                      original_representation_gate={"strict_original_representation_failed_count": 48,
                                                    "sessions": secret})
        before = copy.deepcopy(report)
        result = metric.public_log_summary(report)
        self.assertEqual(report, before)
        self.assertEqual(result, ablation.public_log_summary(report))
        self.assertEqual(set(result), {"schema_version", "status", "public_output_scope",
            "native_finalization", "comparison", "original_representation_gate"}
            | set(metric.PUBLIC_BOOLEAN_FIELDS) | set(metric.PUBLIC_COUNT_FIELDS))
        self.assertEqual(result["strict_metric_failures"], 3)
        self.assertEqual(result["native_finalization"]["request_count"], 15)
        self.assertEqual(result["comparison"]["samples"], 60)
        self.assertEqual(result["original_representation_gate"]["strict_original_representation_failed_count"], 48)
        encoded = json.dumps(result, allow_nan=False)
        for forbidden in ("PRIVATE", "987654", "glyph_id", "observations", "variants",
                          '"differences"', "native_metrics", "source_sha256", "directory_patch_verification"):
            self.assertNotIn(forbidden, encoded)

    def test_unknown_status_and_untrusted_values_fail_closed_without_echo(self):
        for value in ("PRIVATE", {"PRIVATE": "PRIVATE"}, ["PRIVATE"], -1, 1.5,
                      float("nan"), float("inf"), 2**100):
            with self.subTest(kind=type(value).__name__):
                report = {key: value for key in metric.PUBLIC_BOOLEAN_FIELDS + metric.PUBLIC_COUNT_FIELDS}
                report.update(status=value, native_finalization=value, comparison=value,
                              original_representation_gate=value)
                result = metric.public_log_summary(report)
                self.assertEqual(result["status"], "UNRECOGNIZED_STATUS_NOT_ACCEPTED")
                self.assertNotIn("PRIVATE", json.dumps(result, allow_nan=False))
                self.assertTrue(all(result[k] is None for k in
                                    metric.PUBLIC_BOOLEAN_FIELDS + metric.PUBLIC_COUNT_FIELDS))
        self.assertIsNone(metric.public_log_summary({"strict_metric_failures": True})["strict_metric_failures"])
        self.assertIsNone(metric.public_log_summary({})["strict_metric_failures"])
        self.assertFalse(metric.public_log_summary({"diagnostics_complete": False})["diagnostics_complete"])

    def test_failed_cli_stdout_and_artifact_are_identical_aggregates(self):
        for module, prefix in ((metric, "B1_ORIGINAL_SUMMARY_JSON="),
                               (ablation, "B1_VORG_ABLATION_SUMMARY_JSON=")):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                output = root / "public.json"
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = module.run(root / "PRIVATE_MISSING_SOURCE", root / "PRIVATE_BINARY", output)
                self.assertEqual(code, 1)
                public = json.loads(output.read_text())
                self.assertEqual(json.loads(stdout.getvalue().split(prefix, 1)[1]), public)
                for name in ("observations", "variants", "failure", "source_sha256"):
                    self.assertNotIn(name, public)
                self.assertNotIn("PRIVATE", stdout.getvalue() + output.read_text())
                self.assertFalse(public["source_unchanged"])

    def test_workflows_only_publish_explicit_aggregate_original_reports(self):
        root = Path(__file__).resolve().parents[3]
        for name, filename in (("swirl-vf-b1-metrics.yml", "b1-original-metrics-public.json"),
                               ("swirl-vf-b1-followup.yml", "b1-original-vorg-ablation-public.json")):
            workflow = (root / ".github" / "workflows" / name).read_text()
            self.assertIn('--output build/' + filename + ' > "$RUNNER_TEMP/b1-original-private-process.log" 2>&1', workflow)
            self.assertIn('gate_status=$?', workflow)
            self.assertIn('exit "$gate_status"', workflow)
            self.assertIn('cat build/' + filename, workflow)
            upload = workflow.rsplit('uses: actions/upload-artifact@v4', 1)[1]
            self.assertIn('build/' + filename, upload)
            self.assertNotIn('b1-original-private-process.log', upload)
            self.assertNotIn('build/b1-original-*', upload)
            self.assertNotIn('b1-original-metrics.json', upload)
            self.assertNotIn('b1-original-vorg-ablation.json', upload)

    @unittest.skipUnless(shutil.which("bash"), "workflow shell test requires bash")
    def test_workflow_captures_private_process_streams_and_keeps_failure_exit(self):
        root = Path(__file__).resolve().parents[3]
        for name, script in (("swirl-vf-b1-metrics.yml", "b1_original_metric_check.py"),
                             ("swirl-vf-b1-followup.yml", "b1_original_vorg_ablation.py")):
            workflow = (root / ".github" / "workflows" / name).read_text()
            lines = workflow.splitlines()
            index = next(i for i, line in enumerate(lines) if "python tools/swirl_vf/platform/" + script in line)
            start = max(i for i in range(index) if lines[i].strip() == "run: |") + 1
            end = next(i for i in range(index + 1, len(lines)) if lines[i] and not lines[i].startswith("          "))
            command = "\n".join(line[10:] for line in lines[start:end])
            with self.subTest(workflow=name), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                (directory / "build").mkdir()
                executable = directory / "python"
                executable.write_text("#!" + sys.executable + "\n" +
                    "import json, pathlib, sys\n" +
                    "p = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])\n" +
                    "p.write_text(json.dumps({'status': 'STRICT_ORIGINAL_METRIC_CHECK_FAILED'}))\n" +
                    "print('PRIVATE_ORIGINAL_STDOUT')\n" +
                    "print('PRIVATE_ORIGINAL_STDERR', file=sys.stderr)\n" +
                    "sys.exit(1)\n")
                executable.chmod(0o700)
                environment = dict(os.environ, RUNNER_TEMP=tmp, PATH=tmp + os.pathsep + os.environ["PATH"])
                result = subprocess.run([shutil.which("bash"), "-e", "-c", command], cwd=directory,
                                        env=environment, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("PRIVATE", result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "STRICT_ORIGINAL_METRIC_CHECK_FAILED")
                private_log = (directory / "b1-original-private-process.log").read_text()
                self.assertIn("PRIVATE_ORIGINAL_STDOUT", private_log)
                self.assertIn("PRIVATE_ORIGINAL_STDERR", private_log)


if __name__ == "__main__":
    unittest.main()
