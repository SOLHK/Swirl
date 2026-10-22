"""Authored cache/identity guards; no original data or native extraction."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
import p7_original_glyf
import p8_validate_models as validator
from rebuild import normalized_grid


def write(path, value):
    data = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def fixture(directory):
    gid = 1
    folder = directory/'gid-00001'
    folder.mkdir()
    recipe = dict(source_sha256=validator.EXPECTED, face_index=0, gids=[gid], multiplier=15,
                  binary_sha256='a'*64, training=normalized_grid(validator.CUSTOM),
                  holdout=[dict(zip(validator.CUSTOM, p)) for p in validator.HOLDOUT])
    digest = validator.digest_value(recipe)
    model = {'glyph_id': gid, 'recipe_sha256': digest,
             'report': dict(source_units_per_em=1000, target_units_per_em=15000, physical_grid_multiplier=15)}
    model_hash = write(folder/'gid-00001.json', model)
    (folder/'gid-00001.glyf').write_bytes(b'authored glyph bytes for cache-identity tests only')
    glyph_hash = validator.sha256(folder/'gid-00001.glyf')
    hashes = {}
    for i, location in enumerate(recipe['training']+recipe['holdout']):
        value = dict(glyph_id=gid, recipe_sha256=digest, events=[],
                     source_q=dict(zip(validator.TAGS, (location[tag] for tag in validator.CUSTOM))))
        hashes[f'{gid}:{i}'] = write(folder/f'gid-00001-native-{i:02d}.json', value)
    receipt = dict(recipe=recipe, recipe_sha256=digest, native_samples=hashes,
                   models={'1': dict(sha256=model_hash, glyf_sha256=glyph_hash)})
    row = dict(status='ENCODED_EXPERIMENTAL', sample_receipt_sha256=write(folder/'receipt.json', receipt))
    batch_recipe = dict(source_sha256=validator.EXPECTED, face_index=0, gids=[1], multiplier=15,
                        oracle_sha256='a'*64)
    return recipe, receipt, row, batch_recipe


class CachedModelValidatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.recipe, self.receipt, self.row, self.batch_recipe = fixture(self.root)
        self.folder = self.root/'gid-00001'

    def refresh_receipt(self):
        self.row['sample_receipt_sha256'] = write(self.folder/'receipt.json', self.receipt)

    def native(self):
        return validator.checked_native_cases(self.root, 1, self.row, self.batch_recipe)

    def test_seven_cases_and_every_cached_hash_verified_without_native_calls(self):
        with patch('subprocess.run') as native:
            cases, binding = self.native()
        native.assert_not_called()
        self.assertEqual([c['name'] for c in cases], ['default', 'holdout_0', 'holdout_1',
                         'holdout_2', 'holdout_3', 'weight_min', 'weight_max'])
        self.assertEqual(len(cases), 7)
        self.assertEqual(binding['native_cache_files_verified'], 31)

    def test_unchosen_cache_corruption_is_still_rejected(self):
        chosen = {index for _, index in validator.case_indices(self.recipe)}
        index = next(i for i in range(31) if i not in chosen)
        path = self.folder/f'gid-00001-native-{index:02d}.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'cached_bytes_changed'):
            self.native()

    def test_rehashed_native_payload_still_requires_GID_q_and_recipe_binding(self):
        original = json.loads((self.folder/'gid-00001-native-00.json').read_text())
        for field, value in (('glyph_id', True), ('recipe_sha256', 'b'*64),
                             ('source_q', dict.fromkeys(validator.TAGS, .125))):
            changed = dict(original, **{field: value})
            self.receipt['native_samples']['1:0'] = write(self.folder/'gid-00001-native-00.json', changed)
            self.refresh_receipt()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'source_binding'):
                self.native()

    def test_missing_or_unbound_sha_is_refused(self):
        for digest in (None, False, 'bad', 'A'*64):
            self.row['sample_receipt_sha256'] = digest
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, 'bound_SHA256'):
                self.native()

    def test_model_and_glyf_hashes_are_required(self):
        self.receipt['models']['1']['sha256'] = None
        self.refresh_receipt()
        with self.assertRaisesRegex(ValueError, 'bound_SHA256'):
            self.native()
        self.receipt['models']['1']['sha256'] = validator.sha256(self.folder/'gid-00001.json')
        self.refresh_receipt()
        (self.folder/'gid-00001.glyf').write_bytes(b'changed authored glyph')
        with self.assertRaisesRegex(ValueError, 'glyf_bytes_changed'):
            self.native()

    def test_GID_recipe_cannot_alias_booleans_or_other_sources(self):
        original = copy.deepcopy(self.receipt)
        for field, value in (('gids', [True]), ('face_index', False), ('multiplier', True),
                             ('source_sha256', 'b'*64)):
            self.receipt = copy.deepcopy(original)
            self.receipt['recipe'][field] = value
            self.receipt['recipe_sha256'] = validator.digest_value(self.receipt['recipe'])
            self.refresh_receipt()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'source_bound_GID'):
                self.native()

    def test_complete_native_key_set_and_non_symlink_files_required(self):
        self.receipt['native_samples'].pop('1:30')
        self.refresh_receipt()
        with self.assertRaisesRegex(ValueError, 'complete_source_native_cache'):
            self.native()
        self.receipt['native_samples']['1:30'] = validator.sha256(self.folder/'gid-00001-native-30.json')
        self.refresh_receipt()
        path = self.folder/'gid-00001-native-00.json'
        backup = self.root/'authored-backup.json'
        path.rename(backup)
        path.symlink_to(backup)
        with self.assertRaisesRegex(ValueError, 'regular_cache_file'):
            self.native()

    def test_frozen_holdouts_and_unique_training_are_required(self):
        for changed in (dict(self.recipe, holdout=[]), dict(self.recipe, training=self.recipe['training']*2),
                        dict(self.recipe, training=[dict.fromkeys(validator.CUSTOM, 0.)])):
            with self.subTest(points=len(changed['training'])), self.assertRaises(ValueError):
                validator.case_indices(changed)

    def test_tensor_training_and_holdout_plans_are_bound_to_batch(self):
        self.batch_recipe['training'] = copy.deepcopy(self.recipe['training'])
        self.batch_recipe['frozen_holdout'] = validator.HOLDOUT
        self.assertEqual(len(self.native()[0]), 7)
        self.batch_recipe['training'][0] = dict.fromkeys(validator.CUSTOM, .125)
        with self.assertRaisesRegex(ValueError, 'batch_training_plan_changed'):
            self.native()
        self.batch_recipe['training'] = self.recipe['training']
        self.batch_recipe['frozen_holdout'] = [(0., 0., 0.)]*4
        with self.assertRaisesRegex(ValueError, 'batch_holdout_plan_changed'):
            self.native()

    def test_candidate_assembly_receipt_binds_exact_batch_GIDs_and_bytes(self):
        candidate = self.root/'authored-candidate.ttf'
        candidate.write_bytes(b'authored font bytes for assembly guard only')
        digest = validator.sha256(candidate)
        batch_digest = 'b'*64
        report = dict(source_sha256=validator.EXPECTED, model_receipt_sha256=batch_digest,
                      glyph_count=47102, selected_variable_GIDs=[1], serialization={'status':'PASS'},
                      candidate_sha256=digest)
        path = self.root/'face-report.json'
        write(path, report)
        self.assertEqual(validator.checked_assembly(candidate, batch_digest, [1], digest),
                         (path, validator.sha256(path)))
        for change in (dict(model_receipt_sha256='c'*64), dict(selected_variable_GIDs=[2]),
                       dict(selected_variable_GIDs=[True]), dict(selected_variable_GIDs=[1, 1]),
                       dict(glyph_count=True), dict(serialization={'status':'FAIL'}),
                       dict(source_sha256='d'*64)):
            write(path, dict(report, **change))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'assembly_source_batch'):
                validator.checked_assembly(candidate, batch_digest, [1], digest)
        write(path, dict(report, candidate_sha256='e'*64))
        with self.assertRaisesRegex(ValueError, 'assembly_bytes_changed'):
            validator.checked_assembly(candidate, batch_digest, [1], digest)
        candidate.write_bytes(b'ttcf authored collection for assembly guard only')
        digest = validator.sha256(candidate)
        write(path, dict(report, packing={'sha256':digest}))
        self.assertEqual(validator.checked_assembly(candidate, batch_digest, [1], digest)[0], path)
        write(path, dict(report, packing={'sha256':'f'*64}))
        with self.assertRaisesRegex(ValueError, 'assembly_bytes_changed'):
            validator.checked_assembly(candidate, batch_digest, [1], digest)

    def test_batch_snapshot_must_finish_and_bind_all_rows(self):
        receipt = dict(recipe=self.batch_recipe, recipe_sha256=validator.digest_value(self.batch_recipe), rows={'1': self.row})
        path = self.root/'batch-receipt.json'
        write(path, receipt)
        self.assertEqual(validator.checked_batch(self.root)[0], receipt)
        for rows in ({}, {'1': dict(status='RUNNING')}, {'1': dict(status='FAILED')}):
            write(path, dict(receipt, rows=rows))
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validator.checked_batch(self.root)

    def test_partial_plan_requires_optin_and_reports_pending_honestly(self):
        recipe = dict(self.batch_recipe, gids=[1, 2, 3])
        receipt = dict(recipe=recipe, recipe_sha256=validator.digest_value(recipe), rows={'1': self.row})
        write(self.root/'batch-receipt.json', receipt)
        with self.assertRaisesRegex(ValueError, 'complete_batch_rows_required'):
            validator.checked_batch(self.root)
        saved, _ = validator.checked_batch(self.root, allow_incomplete_batch=True)
        self.assertEqual(validator.batch_scope(saved, True), dict(requested_GIDs=3, attempted_GIDs=1,
            pending_GIDs=2, source_batch_complete=False, partial_batch_diagnostic=True, allow_incomplete_batch=True))
        complete = dict(receipt, rows={'1': self.row, '2': {'status':'FAILED'}, '3': {'status':'FAILED'}})
        write(self.root/'batch-receipt.json', complete)
        saved, _ = validator.checked_batch(self.root)
        self.assertEqual(validator.batch_scope(saved, False), dict(requested_GIDs=3, attempted_GIDs=3,
            pending_GIDs=0, source_batch_complete=True, partial_batch_diagnostic=False, allow_incomplete_batch=False))

    def test_partial_optin_does_not_admit_running_or_unplanned_GIDs(self):
        recipe = dict(self.batch_recipe, gids=[1, 2, 3])
        base = dict(recipe=recipe, recipe_sha256=validator.digest_value(recipe))
        for rows in ({'1': self.row, '2': {'status':'RUNNING'}}, {'1': self.row, '4': {'status':'FAILED'}}):
            write(self.root/'batch-receipt.json', dict(base, rows=rows))
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validator.checked_batch(self.root, allow_incomplete_batch=True)
        with self.assertRaisesRegex(ValueError, 'explicit_partial_batch_optin'):
            validator.checked_batch(self.root, allow_incomplete_batch=1)

    def test_wrong_source_and_output_traversal_rejected_before_font_or_cache_reads(self):
        source, candidate = self.root/'authored-source', self.root/'authored-candidate'
        for path in (source, candidate):
            path.write_bytes(b'authored invalid font')
        output = self.root/'output-not-created'
        with self.assertRaisesRegex(ValueError, 'exact_original_source'):
            validator.validate(source, self.root, candidate, output)
        self.assertFalse(output.exists())
        outside = self.root.parent/(self.root.name+'-never-created')
        traversal = self.root/'..'/outside.name
        with patch.object(validator, 'sha256', return_value=validator.EXPECTED), \
             patch.object(validator, 'PRIVATE', self.root.resolve()), patch.object(p7_original_glyf, 'PRIVATE', self.root.resolve()), \
             patch.object(validator, 'checked_batch') as read:
            with self.assertRaisesRegex(ValueError, 'private_build_output_required'):
                validator.validate(source, self.root, candidate, traversal)
        read.assert_not_called()
        self.assertFalse(outside.exists())


if __name__ == '__main__':
    unittest.main()
