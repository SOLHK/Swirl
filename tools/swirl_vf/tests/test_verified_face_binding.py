"""Bind packaging to the exact bytes that passed the production face gate.

Faults modify only generated analytic fixtures in private TemporaryDirectory.
The actual production pipeline, coefficients, checksums and TTC packer run;
only the native oracle is the existing explicit analytic test double.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.ttLib import TTCollection, TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import rebuild
from test_rebuild import write_fixture
from test_rebuild_pipeline import OriginalAnalyticOracle
from test_rebuild_checkpoints import OracleSessions


def alter_outline_coefficient(path):
    """Change a legal gvar outline coefficient, retaining valid SFNT checksums."""
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    altered = path.with_name("binding-mutant.ttf")
    with TTFont(path, recalcTimestamp=False) as font:
        name = font.getGlyphOrder()[0]
        variation = font["gvar"].variations[name][0]
        x, y = variation.coordinates[0]
        variation.coordinates[0] = (x + 200, y)
        font.save(altered)
    altered.replace(path)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    if before == after:
        raise AssertionError("coefficient fault did not change generated font")
    return {"before": before, "after": after, "new_delta": (x + 200, y)}


class VerifiedFaceBindingTests(unittest.TestCase):
    def fixture(self, root):
        source = root / "source.ttc"
        write_fixture(source, faces=3)
        executable = root / "analytic-oracle-identity"
        executable.write_text("authored protocol double identity\n")
        return source, executable, root / "Swirl-VF.ttc", root / "report.json"

    def assert_rejected_binding(self, operation, source, source_bytes, output, report, mutations):
        error = None
        try:
            operation()
        except rebuild.ReconstructionError as caught:
            error = caught
        self.assertEqual(len(mutations), 1, "actual generated-font fault was not injected")
        self.assertEqual(source.read_bytes(), source_bytes)
        saved = json.loads(report.read_text())
        if output.exists():
            # On the old false-pass path, independently prove the altered
            # coefficient reached the real serialized TTC before failing.
            with TTCollection(output) as collection:
                font = collection.fonts[0]
                actual = font["gvar"].variations[font.getGlyphOrder()[0]][0].coordinates[0]
                self.assertEqual(actual, mutations[0]["new_delta"])
            self.assertEqual(saved["status"], "RECONSTRUCTION_SAMPLED_PASS_PLATFORM_UNVERIFIED")
            self.fail("production published a gvar model changed after its accepted face gate")
        self.assertIsNotNone(error, "changed verified face bytes were silently accepted")
        self.assertEqual(saved["status"], "BLOCKED")
        self.assertFalse(saved["output_generated"])

    def test_fresh_face_changed_after_its_gate_cannot_be_rebound_at_pack_time(self):
        with tempfile.TemporaryDirectory(prefix="verified-face-binding-") as folder:
            root = Path(folder)
            source, executable, output, report = self.fixture(root)
            before = source.read_bytes()
            oracle = OriginalAnalyticOracle(source)
            original_verify = rebuild.verify_serialized_face
            accepted = []
            mutations = []

            def verify_then_modify_earlier_face(reference, serialized):
                proof = original_verify(reference, serialized)
                accepted.append(Path(serialized.reader.file.name))
                if len(accepted) == 3:
                    mutations.append(alter_outline_coefficient(accepted[0]))
                return proof

            def run():
                with mock.patch.object(rebuild, "NativeOracle", return_value=oracle), \
                     mock.patch.object(rebuild, "verify_serialized_face", side_effect=verify_then_modify_earlier_face):
                    rebuild.run(source, executable, output, report, batch_size=2)

            self.assert_rejected_binding(run, source, before, output, report, mutations)
            self.assertEqual(len(accepted), 3)
            self.assertTrue(oracle.closed)
            self.assertFalse(list(root.glob("swirl-vf-*")))

    def test_face_changed_during_its_gate_cannot_be_blessed_by_a_later_hash(self):
        with tempfile.TemporaryDirectory(prefix="during-face-binding-") as folder:
            root = Path(folder)
            source, executable, output, report = self.fixture(root)
            before = source.read_bytes()
            oracle = OriginalAnalyticOracle(source)
            original_verify = rebuild.verify_serialized_face
            mutations = []

            def verify_then_modify_current_face(reference, serialized):
                proof = original_verify(reference, serialized)
                if not mutations:
                    mutations.append(alter_outline_coefficient(Path(serialized.reader.file.name)))
                return proof

            def run():
                with mock.patch.object(rebuild, "NativeOracle", return_value=oracle), \
                     mock.patch.object(rebuild, "verify_serialized_face", side_effect=verify_then_modify_current_face):
                    rebuild.run(source, executable, output, report, batch_size=2)

            self.assert_rejected_binding(run, source, before, output, report, mutations)
            self.assertTrue(oracle.closed)
            self.assertFalse(list(root.glob("swirl-vf-*")))

    def test_restored_face_changed_after_restore_cannot_be_rebound_at_pack_time(self):
        with tempfile.TemporaryDirectory(prefix="restored-face-binding-") as folder:
            root = Path(folder)
            source, executable, first_output, first_report = self.fixture(root)
            before = source.read_bytes()
            checkpoints = root / "checkpoints"
            first_sessions = OracleSessions(source)
            with mock.patch.object(rebuild, "NativeOracle", side_effect=first_sessions):
                rebuild.run(source, executable, first_output, first_report,
                            batch_size=2, checkpoint_dir=checkpoints)
            self.assertTrue(first_output.is_file())
            manifest = checkpoints / "verified-faces.json"
            accepted_manifest = manifest.read_bytes()
            output = root / "resumed" / "Swirl-VF.ttc"
            report = root / "resumed-report.json"
            original_restore = rebuild.FaceCheckpoints.restore
            accepted = []
            mutations = []
            sessions = OracleSessions(source)

            def restore_then_modify_earlier_face(writer, index, source_font):
                result = original_restore(writer, index, source_font)
                if result is not None:
                    accepted.append(result[0])
                    if len(accepted) == 3:
                        mutations.append(alter_outline_coefficient(accepted[0]))
                return result

            def run():
                with mock.patch.object(rebuild, "NativeOracle", side_effect=sessions), \
                     mock.patch.object(rebuild.FaceCheckpoints, "restore", new=restore_then_modify_earlier_face):
                    rebuild.run(source, executable, output, report,
                                batch_size=2, checkpoint_dir=checkpoints)

            self.assert_rejected_binding(run, source, before, output, report, mutations)
            self.assertEqual(len(accepted), 3)
            self.assertEqual(sessions.requests, [])
            self.assertEqual(manifest.read_bytes(), accepted_manifest)
            self.assertEqual(first_output.stat().st_size,
                             json.loads(first_report.read_text())["output_size_bytes"])


if __name__ == "__main__":
    unittest.main()
