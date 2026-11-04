"""Actual C1 reconstruction/restore/serialization using original analytic fonts.

Only the native oracle is replaced. The existing reconstruct_glyph algorithm,
model encoding/decoding, immutable storage, face verification, table validation
and streaming TTC packaging really run. Generated fonts stay in temporary
directories and are never described as Apple or platform acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock
import weakref

import numpy as np
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.models import normalizeLocation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import rebuild
import ttc_staging_engine as engine
from ttc_staging_contract import StagingError
from ttc_staging_store import canonical_bytes
from test_rebuild import AXES, analytic_record, reconstructed, write_fixture
from test_rebuild_pipeline import OriginalAnalyticOracle


ORACLE_SHA256 = hashlib.sha256(b"C1 independent analytic session fixture version 1").hexdigest()


class AnalyticSession(OriginalAnalyticOracle):
    synthetic_only = True

    def __init__(self, source):
        super().__init__(source)
        self.source = source
        self.source_sha256 = self.metadata["source_sha256"]


class Sessions:
    def __init__(self, source, configure=None):
        self.source = source
        self.configure = configure
        self.sessions = []

    def __call__(self):
        session = AnalyticSession(self.source)
        if self.configure is not None:
            self.configure(session, len(self.sessions))
        self.sessions.append(session)
        return session

    @property
    def requests(self):
        return [row for session in self.sessions for row in session.requests]


def fail_second_batch(session, index):
    if index == 1:
        session.samples = mock.Mock(side_effect=StagingError("platform_read", "original_test_interruption"))


class StagingEngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="c1-engine-original-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "original-three-face.ttc"
        write_fixture(self.source, faces=3)
        self.checkpoints = self.root / "private-batches"

    def invoke(self, factory, attempt=1, **settings):
        return engine.run_synthetic_staging(
            self.source, self.checkpoints, self.root / f"original-candidate-{attempt}.ttc",
            factory, oracle_sha256=settings.pop("oracle_sha256", ORACLE_SHA256),
            batch_size=settings.pop("batch_size", 2), **settings)

    def receipts(self):
        return list((self.checkpoints / "receipts").glob("*.json"))

    def snapshot(self):
        return {str(p.relative_to(self.checkpoints)): p.read_bytes()
                for p in self.checkpoints.rglob("*.json")}

    def interrupted(self):
        factory = Sessions(self.source, fail_second_batch)
        with self.assertRaisesRegex(StagingError, "original_test_interruption"):
            self.invoke(factory)
        self.assertEqual(len(self.receipts()), 1)
        self.assertFalse((self.root / "original-candidate-1.ttc").exists())
        self.assertEqual([s.close_count for s in factory.sessions], [1, 1])
        self.assertEqual([s.finish_count for s in factory.sessions], [1, 0])
        return factory

    def test_three_faces_all_gids_tail_batches_and_independent_random_interpolation(self):
        factory = Sessions(self.source)
        before = self.source.read_bytes()
        result = self.invoke(factory)
        self.assertEqual(result["status"], "SYNTHETIC_STAGING_PASS")
        self.assertEqual((result["batches_built"], result["batches_reused"]), (6, 0))
        self.assertEqual(len(result["faces"]), 3)
        self.assertEqual(result["original_faces_completed"], 0)
        self.assertFalse(result["production_accepted"])
        self.assertFalse(result["apple_or_coretext_executed"])
        self.assertTrue(result["synthetic_only"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(len(factory.sessions), 6)
        self.assertTrue(all(s.finish_count == s.close_count == 1 for s in factory.sessions))
        self.assertEqual([(s.requests[0][0], s.requests[0][1]) for s in factory.sessions],
                         [(0, (0, 1)), (0, (2,)), (1, (0, 1)), (1, (2,)), (2, (0, 1)), (2, (2,))])
        for face in result["faces"]:
            self.assertEqual(face["glyphs_checked"], 3)
            self.assertEqual(face["coefficients"]["status"], "PASS")
            self.assertEqual(face["coefficients"]["glyphs_checked"], 3)
            self.assertFalse(face["coefficients"]["continuous_native_space_proof"])
        self.assertFalse(list(self.root.glob("c1-face-assembly-*")))

        rng = random.Random(761903)
        unseen = [{tag: rng.uniform(low + 1, high - 1) for tag, (low, _, high) in AXES.items()}
                  for _ in range(8)]
        sampled = [location for _, _, location in factory.requests]
        self.assertTrue(all(location not in sampled for location in unseen))
        output = self.root / "original-candidate-1.ttc"
        with TTCollection(self.source) as original, TTCollection(output) as packed:
            self.assertEqual(len(packed.fonts), 3)
            for original_font, font in zip(original.fonts, packed.fonts):
                self.assertEqual(font.getGlyphOrder(), original_font.getGlyphOrder())
                self.assertEqual(font.getTableData("cmap"), original_font.getTableData("cmap"))
                self.assertEqual(font.getTableData("name"), original_font.getTableData("name"))
                self.assertEqual(font.getTableData("OS/2"), original_font.getTableData("OS/2"))
                self.assertEqual([(a.axisTag, a.minValue, a.defaultValue, a.maxValue)
                                  for a in font["fvar"].axes],
                                 [(tag, *values) for tag, values in AXES.items()])
                for location in unseen:
                    expected = analytic_record(normalizeLocation(location, AXES))
                    wanted = np.asarray([c[1:] for c in expected["commands"] if c[0] != "closePath"])
                    static = instantiateVariableFont(font, location, inplace=False)
                    try:
                        for gid, name in enumerate(static.getGlyphOrder()):
                            self.assertEqual(static.getGlyphID(name), gid)
                            error = np.linalg.norm(np.asarray(static["glyf"][name].coordinates) - wanted, axis=1)
                            self.assertLessEqual(float(error.max()), 1.0)
                            self.assertAlmostEqual(static["hmtx"].metrics[name][0], expected["advance_width"], delta=1.0)
                            self.assertEqual(static["vmtx"].metrics[name][0], 1000)
                    finally:
                        static.close()

    def test_failed_second_batch_resumes_only_pending_and_preserves_prior_receipt(self):
        self.interrupted()
        first_receipt = self.receipts()[0]
        before = first_receipt.read_bytes()
        factory = Sessions(self.source)
        result = self.invoke(factory, attempt=2)
        self.assertEqual((result["batches_built"], result["batches_reused"]), (5, 1))
        self.assertEqual(len(factory.sessions), 5)
        self.assertTrue(all(not (face == 0 and gids == (0, 1)) for face, gids, _ in factory.requests))
        self.assertEqual(first_receipt.read_bytes(), before)
        self.assertEqual(len(self.receipts()), 6)

    def test_all_committed_models_replay_without_sampling_and_identical_output(self):
        first = self.invoke(Sessions(self.source))
        before = self.snapshot()
        factory = mock.Mock(side_effect=AssertionError("restored models must not sample again"))
        repeated = self.invoke(factory, attempt=2)
        factory.assert_not_called()
        self.assertEqual((repeated["batches_built"], repeated["batches_reused"]), (0, 6))
        self.assertEqual(repeated["recipe_sha256"], first["recipe_sha256"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.root / "original-candidate-1.ttc").read_bytes(),
                         (self.root / "original-candidate-2.ttc").read_bytes())

    def test_previous_face_objects_released_before_next_face_sampling(self):
        """Closing TTFont streams must also release their decoded object graphs."""
        original_font = engine.TTFont
        first_face = []
        checks = []

        def track_font(path, *args, **kwargs):
            font = original_font(path, *args, **kwargs)
            if (Path(path) == self.source and kwargs.get("fontNumber") == 0
                    or Path(path).name == "face-00000.ttf"):
                first_face.append(weakref.ref(font))
            return font

        def check_boundary(session, index):
            if index == 2:  # First oracle of face 1, after both face-0 batches.
                self.assertGreaterEqual(len(first_face), 4)
                # Do not collect here: the runner must release the previous
                # face itself, including cycles retained by lazy gvar readers.
                self.assertTrue(all(reference() is None for reference in first_face),
                                "previous face remains resident when next face starts")
                checks.append(index)

        with mock.patch.object(engine, "TTFont", side_effect=track_font):
            result = self.invoke(Sessions(self.source, check_boundary))
        self.assertEqual(result["status"], "SYNTHETIC_STAGING_PASS")
        self.assertEqual(checks, [2])

    def test_second_session_finish_failure_cannot_commit_provisional_models(self):
        def configure(session, index):
            if index == 1:
                session.finish = mock.Mock(side_effect=StagingError("platform_read", "original_finish_failure"))
        factory = Sessions(self.source, configure)
        with self.assertRaisesRegex(StagingError, "original_finish_failure"):
            self.invoke(factory)
        self.assertEqual(len(self.receipts()), 1)
        self.assertEqual([s.close_count for s in factory.sessions], [1, 1])
        self.assertFalse((self.root / "original-candidate-1.ttc").exists())
        resumed = self.invoke(Sessions(self.source), attempt=2)
        self.assertEqual((resumed["batches_built"], resumed["batches_reused"]), (5, 1))

    def test_wrong_summary_counts_are_typed_and_never_committed(self):
        def configure(session, index):
            finish = session.finish
            def wrong_summary():
                summary = finish()
                summary["successful_glyph_count"] += 1
                return summary
            session.finish = wrong_summary
        factory = Sessions(self.source, configure)
        with self.assertRaises(StagingError) as caught:
            self.invoke(factory)
        self.assertEqual(caught.exception.category, "platform_read")
        self.assertEqual(self.receipts(), [])
        self.assertEqual(factory.sessions[0].close_count, 1)

    def test_missing_synthetic_summary_flag_never_commits(self):
        def configure(session, index):
            finish = session.finish
            def missing_marker():
                summary = finish()
                summary.pop("synthetic_test_double_only")
                return summary
            session.finish = missing_marker
        factory = Sessions(self.source, configure)
        with self.assertRaisesRegex(StagingError, "synthetic_summary_required"):
            self.invoke(factory)
        self.assertEqual(self.receipts(), [])
        self.assertEqual(factory.sessions[0].close_count, 1)

    def test_bad_synthetic_marker_closes_created_session(self):
        factory = Sessions(self.source, lambda session, index: setattr(session, "synthetic_only", False))
        with self.assertRaisesRegex(StagingError, "synthetic_oracle_marker_required"):
            self.invoke(factory)
        self.assertEqual(factory.sessions[0].requests, [])
        self.assertEqual(factory.sessions[0].close_count, 1)
        self.assertEqual(self.receipts(), [])

    def test_wrong_oracle_source_hash_closes_without_sampling(self):
        factory = Sessions(self.source, lambda session, index: setattr(session, "source_sha256", "f" * 64))
        with self.assertRaisesRegex(StagingError, "synthetic_oracle_source_mismatch"):
            self.invoke(factory)
        self.assertEqual(factory.requests, [])
        self.assertEqual(factory.sessions[0].close_count, 1)
        self.assertEqual(self.receipts(), [])

    def test_exact_requested_gid_set_required_before_model_commit(self):
        def configure(session, index):
            samples = session.samples
            def omitted(face, gids, location):
                rows = samples(face, gids, location)
                rows.pop(gids[-1])
                return rows
            session.samples = omitted
        factory = Sessions(self.source, configure)
        with self.assertRaisesRegex(StagingError, "batch_gids_mismatch"):
            self.invoke(factory)
        self.assertEqual(self.receipts(), [])
        self.assertEqual(factory.sessions[0].finish_count, 0)

    def test_corrupted_confirmed_model_fails_before_any_new_oracle(self):
        self.interrupted()
        path = next((self.checkpoints / "payloads").glob("*.json"))
        payload = json.loads(path.read_bytes())
        payload["records"][0]["points"][0][0] += 1
        damaged = canonical_bytes(payload)
        path.write_bytes(damaged)
        factory = mock.Mock(side_effect=AssertionError("damage must be detected before new sampling"))
        with self.assertRaisesRegex(StagingError, "checkpoint_payload_hash_mismatch"):
            self.invoke(factory, attempt=2)
        factory.assert_not_called()
        self.assertEqual(path.read_bytes(), damaged)
        self.assertEqual(len(self.receipts()), 1)

    def test_complete_model_schema_is_rechecked_on_restore(self):
        self.interrupted()
        original_restore = engine.BatchStore.restore
        def corrupt_decoded_model(store, face, start, stop):
            restored = original_restore(store, face, start, stop)
            if restored is not None:
                restored = copy.deepcopy(restored)
                restored[0][0]["variations"][0]["deltas"].pop()
            return restored
        factory = mock.Mock(side_effect=AssertionError("bad restored schema must not sample"))
        with mock.patch.object(engine.BatchStore, "restore", corrupt_decoded_model):
            with self.assertRaisesRegex(StagingError, "invalid_model_delta_count"):
                self.invoke(factory, attempt=2)
        factory.assert_not_called()

    def test_changed_oracle_or_batch_recipe_refuses_existing_checkpoints(self):
        self.interrupted()
        before = self.snapshot()
        for settings in ({"oracle_sha256": "e" * 64}, {"batch_size": 1}, {"max_sample_bytes": 1024 * 1024}):
            factory = mock.Mock(side_effect=AssertionError("changed recipe must fail before sampling"))
            with self.subTest(settings=settings), self.assertRaisesRegex(StagingError, "checkpoint_recipe_mismatch"):
                self.invoke(factory, attempt=2, **settings)
            factory.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_changed_source_refuses_existing_checkpoints(self):
        self.interrupted()
        before = self.snapshot()
        with TTCollection(self.source) as collection:
            collection.fonts[0]["name"].setName("Original different synthetic identity", 4, 3, 1, 0x409)
            collection.save(self.source)
        factory = mock.Mock(side_effect=AssertionError("changed source must fail before sampling"))
        with self.assertRaisesRegex(StagingError, "checkpoint_recipe_mismatch"):
            self.invoke(factory, attempt=2)
        factory.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_source_mutation_during_finished_batch_prevents_checkpoint(self):
        def configure(session, index):
            finish = session.finish
            def mutate_source():
                result = finish()
                self.source.write_bytes(self.source.read_bytes() + b"original test mutation")
                return result
            session.finish = mutate_source
        factory = Sessions(self.source, configure)
        with self.assertRaisesRegex(StagingError, "source_changed_during_batch"):
            self.invoke(factory)
        self.assertEqual(self.receipts(), [])
        self.assertEqual(factory.sessions[0].close_count, 1)

    def test_sample_budget_fails_without_promoting_observations(self):
        factory = Sessions(self.source)
        with self.assertRaisesRegex(StagingError, "sample_memory_budget"):
            self.invoke(factory, max_sample_bytes=1024)
        self.assertEqual(self.receipts(), [])
        self.assertEqual(factory.sessions[0].finish_count, 0)
        self.assertEqual(factory.sessions[0].close_count, 1)

    def test_batch_encoding_budget_fails_after_session_without_receipt(self):
        factory = Sessions(self.source)
        with self.assertRaisesRegex(StagingError, "checkpoint_size_limit"):
            self.invoke(factory, max_batch_bytes=1024)
        self.assertEqual(self.receipts(), [])
        self.assertEqual(factory.sessions[0].finish_count, 1)
        self.assertEqual(factory.sessions[0].close_count, 1)

    def test_face_budget_fails_before_assembly_but_preserves_completed_batches(self):
        factory = Sessions(self.source)
        with self.assertRaisesRegex(StagingError, "face_model_memory_budget"):
            self.invoke(factory, max_face_model_bytes=1024)
        self.assertEqual(len(self.receipts()), 2)
        self.assertEqual(len(factory.sessions), 2)
        self.assertFalse((self.root / "original-candidate-1.ttc").exists())

    def test_invalid_memory_budget_fails_before_checkpoint_directory_creation(self):
        for settings in ({"max_sample_bytes": True}, {"max_batch_bytes": 0},
                         {"max_face_model_bytes": 513 * 1024**2}):
            factory = mock.Mock()
            with self.subTest(settings=settings), self.assertRaisesRegex(StagingError, "invalid_memory_budget"):
                self.invoke(factory, **settings)
            factory.assert_not_called()
            self.assertFalse(self.checkpoints.exists())

    def test_final_collection_rejection_leaves_batches_resumable_and_no_output(self):
        factory = Sessions(self.source)
        with mock.patch.object(engine, "validate_collection", side_effect=StagingError("serialization", "original_collection_rejection")):
            with self.assertRaisesRegex(StagingError, "original_collection_rejection"):
                self.invoke(factory)
        self.assertEqual(len(self.receipts()), 6)
        self.assertFalse((self.root / "original-candidate-1.ttc").exists())
        no_sampling = mock.Mock(side_effect=AssertionError("all batches already finished"))
        result = self.invoke(no_sampling, attempt=2)
        no_sampling.assert_not_called()
        self.assertEqual((result["batches_built"], result["batches_reused"]), (0, 6))

    def test_production_filename_and_apple_identity_are_closed(self):
        factory = mock.Mock()
        with self.assertRaisesRegex(StagingError, "production_filename_reserved"):
            engine.run_synthetic_staging(self.source, self.checkpoints, self.root / "Swirl-VF.ttc", factory,
                                         oracle_sha256=ORACLE_SHA256)
        with mock.patch.object(engine, "file_digest", return_value=engine.APPLE_SOURCE_SHA256):
            with self.assertRaisesRegex(StagingError, "production_adapter_unavailable"):
                self.invoke(factory)
        factory.assert_not_called()
        self.assertFalse(self.checkpoints.exists())

    def test_output_no_clobber_keeps_existing_bytes(self):
        output = self.root / "original-candidate-1.ttc"
        output.write_bytes(b"earlier reviewed synthetic result")
        with self.assertRaisesRegex(StagingError, "output_exists"):
            self.invoke(mock.Mock())
        self.assertEqual(output.read_bytes(), b"earlier reviewed synthetic result")
        self.assertFalse(self.checkpoints.exists())

    def test_empty_gid_keeps_index_and_metrics_through_reconstruction(self):
        with TTCollection(self.source) as collection:
            for font in collection.fonts:
                font["glyf"].glyphs[".notdef"] = TTGlyphPen(None).glyph()
                font["gvar"].variations[".notdef"] = []
                font["hmtx"].metrics[".notdef"] = (250, 0)
                font["vmtx"].metrics[".notdef"] = (1000, 880)
            collection.save(self.source)
        def configure(session, index):
            samples = session.samples
            def empty(face, gids, location):
                rows = samples(face, gids, location)
                if 0 in rows:
                    rows[0] = {"commands": [], "advance_width": 250, "advance_height": 1000,
                               "lsb": 0, "horizontal_origin_x": 0, "vertical_origin_x": 125,
                               "vertical_origin_y": 880, "error": None}
                return rows
            session.samples = empty
        result = self.invoke(Sessions(self.source, configure))
        self.assertEqual(result["batches_built"], 6)
        with TTCollection(self.root / "original-candidate-1.ttc") as collection:
            for font in collection.fonts:
                self.assertEqual(font.getGlyphID(".notdef"), 0)
                self.assertEqual(font["glyf"][".notdef"].numberOfContours, 0)
                self.assertEqual(font["hmtx"].metrics[".notdef"], (250, 0))
                self.assertEqual(font["vmtx"].metrics[".notdef"], (1000, 880))
                self.assertEqual(len(font.getGlyphOrder()), 3)

    def test_model_serialization_is_exact_without_pickle_or_eval(self):
        result, _, _ = reconstructed()
        encoded = engine.encode_model(2, result)
        decoded = engine.decode_model(json.loads(canonical_bytes(encoded)))
        glyph, variations, hmtx, vmtx = decoded
        self.assertEqual(list(glyph.coordinates), list(result[0].coordinates))
        self.assertEqual(list(glyph.flags), list(result[0].flags))
        self.assertEqual(glyph.endPtsOfContours, result[0].endPtsOfContours)
        self.assertEqual((hmtx, vmtx), (result[2], result[3]))
        self.assertEqual([(v.axes, v.coordinates) for v in variations],
                         [(v.axes, v.coordinates) for v in result[1]])

    def test_malformed_restored_model_schemas_fail_closed(self):
        result, _, _ = reconstructed()
        good = engine.encode_model(0, result)
        changes = [
            lambda m: m.update(gid=True),
            lambda m: m.update(unrecognized="private value"),
            lambda m: m["points"][0].__setitem__(0, float("nan")),
            lambda m: m["points"][0].__setitem__(0, 32768),
            lambda m: m["flags"].__setitem__(0, 0xFF),
            lambda m: m["end_points"].__setitem__(-1, 0),
            lambda m: m["hmtx"].__setitem__(0, 65536),
            lambda m: m["vmtx"].__setitem__(1, True),
            lambda m: m["variations"][0]["axes"].update(wdth=[0, 1, 1]),
            lambda m: m["variations"][0]["deltas"].pop(),
            lambda m: m["verification"].update(holdout_count=0),
            lambda m: m["verification"].update(max_outline_error_bound_units=1.0001),
        ]
        for number, change in enumerate(changes):
            broken = copy.deepcopy(good)
            change(broken)
            with self.subTest(case=number), self.assertRaises(StagingError):
                engine.decode_model(broken)


class StagingRetainedSourceTableTests(unittest.TestCase):
    """A self-consistent candidate cannot silently replace source metadata."""

    setUp = StagingEngineTests.setUp
    invoke = StagingEngineTests.invoke
    receipts = StagingEngineTests.receipts
    snapshot = StagingEngineTests.snapshot

    def assert_change_rejected_and_resumable(self, table, change, category="font_tables"):
        before_source = self.source.read_bytes()
        encoder = engine.add_metric_variations

        def alter_after_valid_metrics(font):
            result = encoder(font)
            change(font)
            return result

        with mock.patch.object(engine, "add_metric_variations", side_effect=alter_after_valid_metrics):
            with self.assertRaises(StagingError) as caught:
                self.invoke(Sessions(self.source))
        self.assertEqual(caught.exception.category, category)
        self.assertEqual(caught.exception.code, "reconstruction_retained_table_changed")
        self.assertEqual(caught.exception.context.get("table"), table)
        self.assertFalse((self.root / "original-candidate-1.ttc").exists())
        self.assertEqual(self.source.read_bytes(), before_source)
        # The first face's two complete oracle sessions are reusable even
        # though the later assembly/retained-table check refused the candidate.
        self.assertEqual(len(self.receipts()), 2)
        confirmed = self.snapshot()
        resumed_sessions = Sessions(self.source)
        resumed = self.invoke(resumed_sessions, attempt=2)
        self.assertEqual((resumed["batches_built"], resumed["batches_reused"]), (4, 2))
        self.assertTrue(all(face != 0 for face, _, _ in resumed_sessions.requests))
        after = self.snapshot()
        self.assertTrue(all(after[path] == data for path, data in confirmed.items()))

    def test_localized_name_change_rejected_and_batches_recover(self):
        self.assert_change_rejected_and_resumable(
            "name", lambda f: f["name"].setName("C1 original changed localized name", 1, 3, 1, 0x804))

    def test_valid_os2_weight_and_width_change_rejected_and_batches_recover(self):
        def alter(font):
            font["OS/2"].usWeightClass = 650
            font["OS/2"].usWidthClass = 7
        self.assert_change_rejected_and_resumable("OS/2", alter)

    def test_valid_original_fvar_default_change_rejected_and_batches_recover(self):
        self.assert_change_rejected_and_resumable(
            "fvar", lambda f: setattr(f["fvar"].axes[0], "defaultValue", 600), category="input_axis")

    def test_valid_stat_axis_value_change_rejected_and_batches_recover(self):
        def alter(font):
            value = font["STAT"].table.AxisValueArray.AxisValue[0]
            value.ensureDecompiled()
            value.Value = 510
        self.assert_change_rejected_and_resumable("STAT", alter)

    def test_raw_source_cmap_invalid_gid_rejected_before_oracle_or_checkpoint(self):
        import struct
        # Alter an actual format-4 idDelta field, preserving a valid binary
        # cmap structure while pointing A beyond the physical three-GID face.
        # No TTFont.save call may normalize this malformed input away.
        with TTFont(self.source, fontNumber=0, lazy=True) as font:
            cmap_offset = font.reader.tables["cmap"].offset
        damaged = bytearray(self.source.read_bytes())
        table_count = struct.unpack_from(">H", damaged, cmap_offset + 2)[0]
        changed = False
        for index in range(table_count):
            _, _, relative = struct.unpack_from(">HHI", damaged, cmap_offset + 4 + 8 * index)
            offset = cmap_offset + relative
            if struct.unpack_from(">H", damaged, offset)[0] != 4:
                continue
            segments = struct.unpack_from(">H", damaged, offset + 6)[0] // 2
            for segment in range(segments):
                end = struct.unpack_from(">H", damaged, offset + 14 + 2 * segment)[0]
                start = struct.unpack_from(">H", damaged, offset + 16 + 2 * segments + 2 * segment)[0]
                if start <= 65 <= end:
                    range_offset = struct.unpack_from(">H", damaged,
                        offset + 16 + 6 * segments + 2 * segment)[0]
                    self.assertEqual(range_offset, 0)
                    struct.pack_into(">H", damaged, offset + 16 + 4 * segments + 2 * segment,
                                     (65534 - 65) & 0xFFFF)
                    changed = True
                    break
            if changed:
                break
        self.assertTrue(changed, "original analytic fixture must expose A in a format-4 segment")
        self.source.write_bytes(damaged)
        with TTFont(self.source, fontNumber=0, lazy=True) as malformed:
            order = set(malformed.getGlyphOrder())
            self.assertTrue(any(table.format != 14 and table.cmap.get(65) not in order
                                for table in malformed["cmap"].tables))
        factory = mock.Mock()
        with self.assertRaises(StagingError) as caught:
            self.invoke(factory)
        self.assertEqual(caught.exception.category, "font_tables")
        self.assertEqual(caught.exception.code, "source_cmap_gid_reference")
        factory.assert_not_called()
        self.assertFalse(self.checkpoints.exists())
        self.assertFalse((self.root / "original-candidate-1.ttc").exists())
        self.assertEqual(self.source.read_bytes(), damaged)


if __name__ == "__main__":
    unittest.main()
