"""Authored receipt contracts and real exclusive byte copies; no Apple data."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
import p7_original_glyf as p7
import p8_seed_batch as seed


def save(path, value):
    data = seed.canonical(value)+b'\n'; path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def checkpoint(directory, gid, batch_recipe):
    directory.mkdir()
    profile = seed.training(batch_recipe['profile'])
    points = seed.normalized_grid(seed.CUSTOM) if profile is None else profile
    names = ('hvf', 'batch_geometry', 'tangent_geometry', 'transform_geometry',
             'hvf_glyph_model', 'source_metrics', 'rebuild')
    recipe = dict(source_sha256=seed.EXPECTED, face_index=0, gids=[gid], multiplier=15,
        binary_sha256=batch_recipe['oracle_sha256'], driver_sha256=batch_recipe['p7_driver_sha256'],
        oracle_source_sha256=seed.sha256(seed.ROOT/'platform/hvf_oracle.c'),
        code={name: seed.sha256(seed.ROOT/'tools'/f'{name}.py') for name in names},
        training=points, holdout=[dict(zip(seed.CUSTOM, p)) for p in seed.HOLDOUT])
    model = {'glyph_id': gid, 'authored_not_a_font': True}
    model_hash = save(directory/f'gid-{gid:05d}.json', model)
    (directory/f'gid-{gid:05d}.glyf').write_bytes(b'authored not font data')
    native = {f'{gid}:{i}': save(directory/f'gid-{gid:05d}-native-{i:02d}.json', {'authored': i})
              for i in range(len(points)+len(seed.HOLDOUT))}
    receipt = dict(recipe=recipe, recipe_sha256=seed.digest_value(recipe), native_samples=native,
        models={str(gid): dict(sha256=model_hash, glyf_sha256=seed.sha256(directory/f'gid-{gid:05d}.glyf'))})
    digest = save(directory/'receipt.json', receipt)
    return dict(status='ENCODED_EXPERIMENTAL', sample_receipt_sha256=digest, tuple_count=0, point_count=1,
        outline_varies=False, metric_varies=False, strict_outline_pass=True, strict_table_metric_pass=True,
        max_outline_error=0., max_table_metric_error=0., source_native_geometry_pass=True,
        native_target_equivalence='NOT_RUN', continuous_proof=False, production_accepted=False)


def cheap_checked(directory):
    receipt = json.loads((directory/'receipt.json').read_text())
    gid = int(next(iter(receipt['models'])))
    record = receipt['models'][str(gid)]
    hashes = {f'gid-{gid:05d}.json': record['sha256'], f'gid-{gid:05d}.glyf': record['glyf_sha256']}
    hashes.update({f'gid-{gid:05d}-native-{int(key.split(":")[1]):02d}.json': value
                   for key, value in receipt['native_samples'].items()})
    if any(seed.sha256(directory/name) != expected for name, expected in hashes.items()):
        raise ValueError('authored_checkpoint_bytes_changed')
    model = (SimpleNamespace(coordinates=[(0, 0)]), [], (600, 0), (1000, 0),
             dict(max_outline_error_bound_source_units=0., max_metric_error_source_units=0.,
                  native_geometry_validation='PASS_FINITE_APPLE_HVF'))
    return gid, model, seed.sha256(directory/'receipt.json')


class SeedBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source, self.target = self.root/'source', self.root/'target'
        self.source.mkdir(); self.target.mkdir()
        self.patchers = [patch.object(seed, 'PRIVATE', self.root), patch.object(p7, 'PRIVATE', self.root),
                         patch.object(seed, 'checked_model', side_effect=cheap_checked)]
        for patcher in self.patchers:
            patcher.start(); self.addCleanup(patcher.stop)
        common = dict(source_sha256=seed.EXPECTED, face_index=0, multiplier=15, profile='p7', training=None,
            frozen_holdout=seed.HOLDOUT, oracle_sha256='a'*64,
            driver_sha256=seed.sha256(seed.ROOT/'platform/p8_batch_original.py'),
            p7_driver_sha256=seed.sha256(seed.ROOT/'platform/p7_original_glyf.py'), dependencies=seed.dependencies())
        self.receipts = []
        for directory, gids, encoded in ((self.source, [1, 2], [1, 2]), (self.target, [1, 2, 3], [1])):
            recipe = dict(common, gids=gids, plan_sha256=('b' if directory == self.source else 'c')*64)
            rows = {str(gid): checkpoint(directory/f'gid-{gid:05d}', gid, recipe) for gid in encoded}
            receipt = dict(recipe=recipe, recipe_sha256=seed.digest_value(recipe), rows=rows,
                           summary=seed.summarize(rows, len(gids)), production_accepted=False)
            save(directory/'batch-receipt.json', receipt); self.receipts.append(receipt)

    def refresh(self, index):
        receipt = self.receipts[index]
        receipt['recipe_sha256'] = seed.digest_value(receipt['recipe'])
        save((self.source if index == 0 else self.target)/'batch-receipt.json', receipt)

    def test_real_bytes_copy_existing_skip_source_unchanged_and_idempotence(self):
        before = {str(path.relative_to(self.source)): path.read_bytes()
                  for path in self.source.rglob('*') if path.is_file()}
        existing = {path.name: path.read_bytes() for path in (self.target/'gid-00001').iterdir()}
        result = seed.seed_batch(self.source, self.target)
        self.assertEqual(result['summary']['encoded_GIDs'], 2)
        self.assertEqual(result['summary']['pending_GIDs'], 1)
        self.assertEqual(result['seed_provenance'][0]['copied_GIDs'], [2])
        self.assertEqual(result['seed_provenance'][0]['native_calls'], 0)
        self.assertFalse(result['summary']['production_accepted'])
        for name, data in existing.items(): self.assertEqual((self.target/'gid-00001'/name).read_bytes(), data)
        for path in (self.source/'gid-00002').iterdir():
            self.assertEqual(path.read_bytes(), (self.target/'gid-00002'/path.name).read_bytes())
        for name, data in before.items(): self.assertEqual((self.source/name).read_bytes(), data)
        digest = seed.sha256(self.target/'batch-receipt.json')
        seed.seed_batch(self.source, self.target)
        self.assertEqual(seed.sha256(self.target/'batch-receipt.json'), digest)

    def test_rehashed_recipe_changes_and_boolean_aliases_refuse_before_copy(self):
        original = json.loads((self.target/'batch-receipt.json').read_text())
        for field, value in (('face_index', False), ('multiplier', 16), ('oracle_sha256', 'd'*64),
                             ('p7_driver_sha256', 'e'*64), ('training', [])):
            self.receipts[1] = json.loads(json.dumps(original))
            self.receipts[1]['recipe'][field] = value; self.refresh(1)
            with self.subTest(field=field), self.assertRaises(ValueError):
                seed.seed_batch(self.source, self.target)
            self.assertFalse((self.target/'gid-00002').exists())

    def test_interrupted_copy_stays_uncounted_and_next_attempt_refuses_orphan(self):
        before = (self.target/'batch-receipt.json').read_bytes()
        real_open = Path.open
        def interrupt(path, mode='r', *args, **kwargs):
            if mode == 'xb' and path == self.target/'gid-00002/gid-00002.glyf':
                raise OSError('authored interruption')
            return real_open(path, mode, *args, **kwargs)
        with patch.object(Path, 'open', interrupt), self.assertRaisesRegex(OSError, 'interruption'):
            seed.seed_batch(self.source, self.target)
        self.assertEqual((self.target/'batch-receipt.json').read_bytes(), before)
        self.assertTrue((self.target/'gid-00002/receipt.json').is_file())
        with self.assertRaisesRegex(ValueError, 'orphan_or_interrupted'):
            seed.seed_batch(self.source, self.target)

    def test_corrupt_or_symlink_cache_and_unfinished_source_are_refused(self):
        cache = self.source/'gid-00002/gid-00002-native-00.json'
        original = cache.read_bytes(); cache.write_bytes(b'corrupt authored cache')
        with self.assertRaisesRegex(ValueError, 'checkpoint_bytes_changed'):
            seed.seed_batch(self.source, self.target)
        cache.write_bytes(original)
        backup = self.root/'backup'; backup.write_bytes(original); cache.unlink(); cache.symlink_to(backup)
        with self.assertRaisesRegex(ValueError, 'regular_checkpoint_file_set'):
            seed.seed_batch(self.source, self.target)
        self.assertFalse((self.target/'gid-00002').exists())
        self.receipts[0]['rows'].pop('2'); self.refresh(0)
        with self.assertRaisesRegex(ValueError, 'finished_batch_rows'):
            seed.seed_batch(self.source, self.target)

    def test_existing_target_row_metadata_cannot_inflate_verified_counts(self):
        self.receipts[1]['rows']['1']['point_count'] = 999; self.refresh(1)
        with self.assertRaisesRegex(ValueError, 'row_disagrees'):
            seed.seed_batch(self.source, self.target)
        self.assertFalse((self.target/'gid-00002').exists())


if __name__ == '__main__':
    unittest.main()
