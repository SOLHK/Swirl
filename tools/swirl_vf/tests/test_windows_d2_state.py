"""Portable fail-closed tests. Mock records are NOT Windows evidence."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform' / 'win_axis_precision'))
import d2_state as d2


def records(mode='guard'):
    state = {'matrix_16_16': [65536,0,0,65536], 'delta_26_6': [0,0],
             'qt_cached_matrix_16_16': [65536,0,0,65536]}
    path = [[0,0,0], [1,1,1], [1,2,0], [1,0,0]]
    head = dict(record='header', source_commit='source', input_sha256='font',
                actual_backend='QFontEngineFT', qt_version='6.10.3', freetype_version='2.14.3',
                table_identity_exact=True, mode=mode, baseline_path=path, baseline_advance=[3,0],
                baseline_state=state, fixed_axes={'wght':499.006195068359375,'WDTH':100,'HGHT':100},
                scope='PRIVATE_ABI_DIAGNOSTIC_NOT_PRODUCTION_FIX')
    rows = [head]
    for i, offset in enumerate(d2.OFFSETS):
        original = copy.deepcopy(path)
        if i:
            original[1][1] += 1/64
        rows.append(dict(record='observation', index=i, offset=offset, original_path=original,
                         isolated_path=copy.deepcopy(path if mode=='guard' else original),
                         original_replay=copy.deepcopy(original), advance=[3,0],
                         before_draw=copy.deepcopy(state), after_draw=copy.deepcopy(state),
                         before_guard=copy.deepcopy(state), after_guard=copy.deepcopy(state),
                         cache_after=[], cache_after_guard=[]))
    rows.append(dict(record='summary', status='DIAGNOSTIC_PASS_NOT_D1_ACCEPTANCE', production_fix=False,
                     observations=12, original_path_mismatches=11,
                     isolated_path_mismatches=0 if mode=='guard' else 11))
    return copy.deepcopy(rows)


class D2Tests(unittest.TestCase):
    def test_both_modes_preserve_original_failure(self):
        for mode in ('control','guard'):
            self.assertEqual(d2.validate(records(mode),'source','font')['original_mismatches'],11)

    def reject(self, mutate):
        rows=records(); mutate(rows)
        with self.assertRaises(ValueError): d2.validate(rows,'source','font')

    def test_no_tolerance_for_single_path_coordinate(self):
        self.reject(lambda r: r[1]['isolated_path'][1].__setitem__(1, 1+1/65536))

    def test_reject_failure_erasure(self):
        self.reject(lambda r: r[2].__setitem__('original_replay',r[0]['baseline_path']))

    def test_reject_unrestored_delta(self):
        self.reject(lambda r: r[1]['after_guard']['delta_26_6'].__setitem__(0,16))

    def test_reject_unrestored_matrix(self):
        self.reject(lambda r: r[1]['after_guard']['matrix_16_16'].__setitem__(0,81920))

    def test_reject_changed_cache(self):
        self.reject(lambda r: r[1].__setitem__('cache_after_guard',[{'data_present':True}]))

    def test_reject_changed_advance(self):
        self.reject(lambda r: r[1].__setitem__('advance',[3+1/64,0]))

    def test_reject_changed_axis(self):
        self.reject(lambda r: r[0]['fixed_axes'].__setitem__('WDTH',99))

    def test_reject_incomplete_or_reordered_evidence(self):
        self.reject(lambda r: r.pop(2))
        self.reject(lambda r: r[1].__setitem__('index',1))

    def test_reject_wrong_identity_and_acceptance(self):
        for key,value in [('source_commit','wrong'),('input_sha256','wrong'),('actual_backend','DirectWrite'),
                          ('freetype_version','2.13.0'),('table_identity_exact',False)]:
            self.reject(lambda r,k=key,v=value:r[0].__setitem__(k,v))
        self.reject(lambda r:r[-1].__setitem__('production_fix',True))

    def test_reject_nonfinite_or_missing_transform(self):
        self.reject(lambda r:r[1]['original_path'][0].__setitem__(1,float('nan')))
        self.reject(lambda r:r[1]['after_guard'].__setitem__('delta_26_6',[]))

    def test_reject_dishonest_counts(self):
        self.reject(lambda r:r[-1].__setitem__('original_path_mismatches',0))

    def test_accessor_extraction_only_self_contained_unique_functions(self):
        text='FT_EXPORT_DEF( void ) FT_Get_Transform(int f) { if (f) { f = 2; } }'
        self.assertEqual(d2.extract_function(text,'FT_Get_Transform'),text)
        for bad in (text+text, text[:-1], text.replace('f = 2;', 'FT_Load_Glyph(f);')):
            with self.assertRaises(ValueError): d2.extract_function(bad,'FT_Get_Transform')

    def test_patch_scope_restore_order_and_original_load(self):
        text='prefix\nvoid QFontEngineFT::addGlyphsToPath()\n{\n    FT_Face face = lockFace(Unscaled);\n    FT_Load_Glyph(face, glyph, FT_LOAD_NO_BITMAP);\n    unlockFace();\n}\n\nglyph_t QFontEngineFT::glyphIndex()\n{}\n'
        patched=d2.patch_source(text)
        self.assertTrue(patched.startswith('prefix\n'))
        self.assertTrue(patched.endswith('glyph_t QFontEngineFT::glyphIndex()\n{}\n'))
        self.assertEqual(patched.count('FT_Load_Glyph(face, glyph, FT_LOAD_NO_BITMAP);'),1)
        self.assertLess(patched.index('const auto unlock'),patched.index('const auto restore'))
        self.assertIn('FT_Set_Transform(face, &outlineMatrix, nullptr);',patched)
        with self.assertRaises(ValueError): d2.patch_source(patched)

    def test_git_blob_identity(self):
        data=b'original\n'
        self.assertEqual(d2.blob(data),hashlib.sha1(b'blob 9\0'+data).hexdigest())


if __name__=='__main__': unittest.main()
