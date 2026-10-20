"""Run the production pipeline against an original analytic oracle double.

Only NativeOracle is replaced for successful reconstruction. No Apple font,
Apple HVF evaluator, CoreText process or Windows renderer runs in these tests.
All input/output font bytes live in TemporaryDirectory and are removed. The
negative serialization tests corrupt actual temporary files; the production
serialization gates still run and must block final-file publication.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.models import normalizeLocation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import rebuild
from test_rebuild import AXES, analytic_record, write_fixture


class OriginalAnalyticOracle:
    """An explicit synthetic test double, not native extraction/identity proof."""

    def __init__(self, source):
        self.metadata = {
            "type": "metadata",
            "backend": "SyntheticAnalyticOracle",
            "original_geometric_fixture": True,
            "apple_or_coretext_executed": False,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "source_byte_size": source.stat().st_size,
        }
        # The original fixture has real independent SFNT identities. Supplying
        # these hashes does not claim that CoreText or an Apple font was used.
        with TTCollection(source, lazy=True) as collection:
            self.metadata["faces"] = [
                {"face_index": index, "glyph_count": font["maxp"].numGlyphs,
                 "upm": font["head"].unitsPerEm, "status": "synthetic_fixture_only",
                 "verified_table_sha256": {tag: hashlib.sha256(font.reader[tag]).hexdigest()
                                           for tag in font.reader.tables}}
                for index, font in enumerate(collection.fonts)]
        self.requests = []
        self.close_count = 0
        self.finish_count = 0
        self.closed = self.finished = False

    def samples(self, face, glyph_ids, location):
        if self.closed or self.finished:
            raise AssertionError("cannot reuse a finished original oracle session")
        if face not in range(3) or not set(glyph_ids) <= {0, 1, 2}:
            raise AssertionError("unexpected synthetic face/GID request")
        if set(location) != set(AXES):
            raise AssertionError("source axis tags were changed or omitted")
        for tag, value in location.items():
            low, _, high = AXES[tag]
            if not low <= value <= high:
                raise AssertionError("source user coordinate is outside its axis")
        self.requests.append((face, tuple(glyph_ids), dict(location)))
        normalized = normalizeLocation(location, AXES)
        return {gid: analytic_record(normalized) for gid in glyph_ids}

    def close(self):
        self.close_count += 1
        self.closed = True

    def finish(self):
        if self.closed or self.finished:
            raise AssertionError("original oracle session already finished or closed")
        self.finish_count += 1
        self.finished = True
        return {'type': 'summary', 'source_sha256': self.metadata['source_sha256'],
                'error_count': 0, 'request_count': len(self.requests),
                'successful_glyph_count': sum(len(gids) for _, gids, _ in self.requests),
                'synthetic_test_double_only': True}


class RebuildPipelineTests(unittest.TestCase):
    def fixture(self, root):
        source = root / "original-analytic-fixture.ttc"
        write_fixture(source, faces=3)
        return source, root / "Swirl-VF.ttc", root / "synthetic-report.json"

    def invoke(self, source, output, report, oracle):
        with mock.patch.object(rebuild, "NativeOracle", return_value=oracle) as native:
            try:
                # A partial last batch must still include every GID. The
                # production outline/metric/adaptation thresholds are unchanged.
                return rebuild.run(source, source.parent / "no-native-process",
                                   output, report, batch_size=2)
            finally:
                native.assert_called_once()

    def assert_blocked(self, root, source, before, output, report, oracle):
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse(output.exists())
        self.assertEqual(oracle.close_count, 1)
        self.assertFalse(list(root.glob("swirl-vf-*")), "staging directory leaked")
        saved = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "BLOCKED")
        self.assertFalse(saved["output_generated"])
        self.assertFalse(saved["lossless_conversion"])
        self.assertEqual(saved["oracle"]["backend"], "SyntheticAnalyticOracle")
        self.assertTrue(saved["failures"])
        return saved

    def test_final_native_failure_blocks_already_serialized_collection(self):
        with tempfile.TemporaryDirectory(prefix='analytic-finalization-') as tmp:
            root = Path(tmp)
            source, output, report = self.fixture(root)
            before = source.read_bytes()
            oracle = OriginalAnalyticOracle(source)
            oracle.finish = mock.Mock(side_effect=rebuild.ReconstructionError('native final summary rejected'))
            with self.assertRaisesRegex(rebuild.ReconstructionError, 'native final summary rejected'):
                self.invoke(source, output, report, oracle)
            saved = self.assert_blocked(root, source, before, output, report, oracle)
            self.assertEqual(saved['collection_verification']['status'], 'PASS')
            self.assertEqual(saved['failures'][0]['context']['stage'], 'native_finalization')
            oracle.finish.assert_called_once()

    def test_complete_three_face_pipeline_and_unseen_mixed_coordinates(self):
        with tempfile.TemporaryDirectory(prefix="analytic-pipeline-") as tmp:
            root = Path(tmp)
            source, output, report = self.fixture(root)
            before = source.read_bytes()
            oracle = OriginalAnalyticOracle(source)
            real_face_gate = rebuild.verify_serialized_face
            real_collection_gate = rebuild.verify_collection_tables

            def face_gate(reference, actual):
                self.assertFalse(output.exists(), "published before face gate")
                return real_face_gate(reference, actual)

            def collection_gate(paths, actual):
                self.assertFalse(output.exists(), "published before TTC gate")
                return real_collection_gate(paths, actual)

            with mock.patch.object(rebuild, "verify_serialized_face", side_effect=face_gate) as faces, \
                 mock.patch.object(rebuild, "verify_collection_tables", side_effect=collection_gate) as collection:
                result = self.invoke(source, output, report, oracle)
            self.assertEqual(faces.call_count, 3)
            self.assertEqual(collection.call_count, 1)
            self.assertEqual(oracle.close_count, 1)
            self.assertEqual(source.read_bytes(), before)
            self.assertTrue(output.is_file())
            self.assertEqual(output.name, "Swirl-VF.ttc")
            self.assertFalse(list(root.glob("swirl-vf-*")))
            self.assertEqual(result["status"], "RECONSTRUCTION_SAMPLED_PASS_PLATFORM_UNVERIFIED")
            self.assertTrue(result["output_generated"])
            self.assertFalse(result["lossless_conversion"])
            self.assertEqual(result["windows_acceptance"], "NOT_RUN")
            self.assertEqual(result["oracle"]["backend"], "SyntheticAnalyticOracle")
            self.assertFalse(result["oracle"]["apple_or_coretext_executed"])
            self.assertEqual(result["outline_limit_font_units"], 1.0)
            self.assertEqual(result["metric_limit_font_units"], 1.0)
            self.assertEqual(result["source_sha256"], hashlib.sha256(before).hexdigest())
            self.assertEqual(result["output_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(result["output_size_bytes"], output.stat().st_size)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")),
                             json.loads(json.dumps(result)))
            self.assertEqual([f["face_index"] for f in result["faces"]], [0, 1, 2])
            self.assertEqual(result["collection_verification"]["status"], "PASS")
            self.assertEqual(result["collection_verification"]["faces_checked"], 3)
            for face in result["faces"]:
                self.assertEqual(face["glyph_count"], 3)
                checked = face["serialized_model_verification"]
                self.assertEqual(checked["status"], "PASS")
                self.assertEqual(checked["glyphs_checked"], 3)
                self.assertEqual(checked["default_points_including_phantoms_checked"], 24)
                self.assertGreater(checked["gvar_tuples_checked"], 0)
                self.assertFalse(checked["continuous_native_space_proof"])

            location = {"WDTH": 733.25, "wght": 623.5, "HGHT": 388.75}
            expected = analytic_record(normalizeLocation(location, AXES))
            wanted = np.asarray([c[1:] for c in expected["commands"] if c[0] != "closePath"])
            with TTCollection(source) as original, TTCollection(output) as actual:
                self.assertEqual(len(actual.fonts), 3)
                for face_index, (src, font) in enumerate(zip(original.fonts, actual.fonts)):
                    requests = [(gids, loc) for f, gids, loc in oracle.requests if f == face_index]
                    self.assertEqual({g for gids, _ in requests for g in gids}, {0, 1, 2})
                    self.assertEqual({gids for gids, _ in requests}, {(0, 1), (2,)})
                    self.assertGreater(len({tuple(loc.items()) for _, loc in requests}), 27)
                    self.assertNotIn(location, [loc for _, loc in requests])
                    self.assertEqual(font.getGlyphOrder(), src.getGlyphOrder())
                    self.assertEqual(font["cmap"].compile(font), src["cmap"].compile(src))
                    self.assertEqual({a.axisTag: (a.minValue, a.defaultValue, a.maxValue)
                                      for a in font["fvar"].axes}, AXES)
                    self.assertEqual(list(a.axisTag for a in font["fvar"].axes), list(AXES))
                    self.assertEqual(font["avar"].segments,
                                     {tag: {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0} for tag in AXES})
                    static = instantiateVariableFont(font, location, inplace=False)
                    try:
                        for gid, name in enumerate(static.getGlyphOrder()):
                            self.assertEqual(static.getGlyphID(name), gid)
                            glyph = static["glyf"][name]
                            difference = np.asarray(glyph.coordinates) - wanted
                            self.assertLessEqual(float(np.linalg.norm(difference, axis=1).max()),
                                                 result["outline_limit_font_units"])
                            self.assertAlmostEqual(static["hmtx"].metrics[name][0],
                                                   expected["advance_width"],
                                                   delta=result["metric_limit_font_units"])
                            self.assertEqual(static["vmtx"].metrics[name][0], 1000)
                    finally:
                        static.close()

    def test_corrupted_saved_gvar_blocks_publication_after_partial_face_progress(self):
        with tempfile.TemporaryDirectory(prefix="analytic-pipeline-") as tmp:
            root = Path(tmp)
            source, output, report = self.fixture(root)
            before = source.read_bytes()
            oracle = OriginalAnalyticOracle(source)
            original_save = TTFont.save
            corrupted = []

            def corrupt_saved_font(font, path, *args, **kwargs):
                result = original_save(font, path, *args, **kwargs)
                if Path(path).name == "face-1.ttf":
                    altered = Path(path).with_name("altered-face.ttf")
                    with TTFont(path, recalcTimestamp=False) as mutant:
                        name = mutant.getGlyphOrder()[2]
                        variation = mutant["gvar"].variations[name][0]
                        x, y = variation.coordinates[0]
                        variation.coordinates[0] = (x + 1, y)
                        original_save(mutant, altered)
                    altered.replace(path)
                    corrupted.append(path)
                return result

            with mock.patch.object(TTFont, "save", new=corrupt_saved_font), \
                 mock.patch.object(rebuild, "verify_collection_tables", wraps=rebuild.verify_collection_tables) as packing:
                with self.assertRaisesRegex(rebuild.ReconstructionError, "gvar outline/phantom delta changed"):
                    self.invoke(source, output, report, oracle)
            self.assertEqual(len(corrupted), 1)
            packing.assert_not_called()
            saved = self.assert_blocked(root, source, before, output, report, oracle)
            self.assertEqual(len(saved["faces"]), 2)
            self.assertEqual(saved["faces"][0]["serialized_model_verification"]["status"], "PASS")
            self.assertNotIn("serialized_model_verification", saved["faces"][1])

    def test_corrupted_ttc_face_order_blocks_publication_after_all_face_gates(self):
        with tempfile.TemporaryDirectory(prefix="analytic-pipeline-") as tmp:
            root = Path(tmp)
            source, output, report = self.fixture(root)
            before = source.read_bytes()
            oracle = OriginalAnalyticOracle(source)
            original_save = TTCollection.save
            corrupted = []

            def corrupt_saved_collection(collection, path, *args, **kwargs):
                result = original_save(collection, path, *args, **kwargs)
                if Path(path).name == "candidate.ttc":
                    altered = Path(path).with_name("altered-collection.ttc")
                    with TTCollection(path, recalcTimestamp=False) as mutant:
                        mutant.fonts.reverse()
                        original_save(mutant, altered, shareTables=True)
                    altered.replace(path)
                    corrupted.append(path)
                return result

            with mock.patch.object(TTCollection, "save", new=corrupt_saved_collection), \
                 mock.patch.object(rebuild, "verify_serialized_face", wraps=rebuild.verify_serialized_face) as faces:
                with self.assertRaisesRegex(rebuild.ReconstructionError, "TTC face 0: name bytes changed"):
                    self.invoke(source, output, report, oracle)
            self.assertEqual(len(corrupted), 1)
            self.assertEqual(faces.call_count, 3)
            saved = self.assert_blocked(root, source, before, output, report, oracle)
            self.assertEqual(len(saved["faces"]), 3)
            self.assertTrue(all(f["serialized_model_verification"]["status"] == "PASS" for f in saved["faces"]))

    def test_final_name_and_existing_output_are_guarded_before_oracle(self):
        with tempfile.TemporaryDirectory(prefix="analytic-pipeline-") as tmp:
            root = Path(tmp)
            source, output, report = self.fixture(root)
            before = source.read_bytes()
            with mock.patch.object(rebuild, "NativeOracle") as native:
                with self.assertRaisesRegex(rebuild.ReconstructionError, "final font filename"):
                    rebuild.run(source, root / "no-native-process", root / "Swirl-VF-Fixed.ttc", report)
                self.assertFalse((root / "Swirl-VF-Fixed.ttc").exists())
                output.write_bytes(b"existing-unreviewed-output")
                with self.assertRaisesRegex(rebuild.ReconstructionError, "destination already exists"):
                    rebuild.run(source, root / "no-native-process", output, report)
                self.assertEqual(output.read_bytes(), b"existing-unreviewed-output")
                native.assert_not_called()
            self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
