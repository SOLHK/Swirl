"""Authored avar2 native probes; finite grid results grant no acceptance."""
import io
from pathlib import Path
import sys
import unittest

from fontTools.ttLib import TTFont
import uharfbuzz as hb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from avar2_rounding_control import COMPATIBILITY, PRODUCTION_ACCEPTED, make_avar2_control
from design_axis_basis import basis_from_axis, decode_target_r, encode_source_q, nearest
from make_rounding_controls import authored_source, CLIP, IDENTITY, ORDER, PROFILES
from target_axis_mapping import SourceAxis, source_axis_plan


def axes():
    return tuple(SourceAxis(tag, *PROFILES[tag], CLIP if tag == 'wght' else IDENTITY) for tag in ORDER)


def blob(font):
    stream = io.BytesIO()
    font.save(stream)
    return stream.getvalue()


def native(font):
    result = hb.Font(hb.Face(blob(font)))
    hb.ot_font_set_funcs(result)
    result.scale = (64000, 64000)
    return result


class Avar2RoundingControlTests(unittest.TestCase):
    def test_serialized_model_metric_bytes_and_source_are_unchanged(self):
        source = authored_source()
        before = blob(source)
        target = make_avar2_control(source, axes())
        self.assertEqual(blob(source), before)
        self.assertEqual(source['head'].unitsPerEm, target['head'].unitsPerEm)
        with TTFont(io.BytesIO(before)) as a, TTFont(io.BytesIO(blob(target))) as b:
            for tag in ('glyf', 'gvar', 'HVAR', 'VVAR', 'hmtx', 'vmtx', 'cmap'):
                self.assertEqual(a.reader[tag], b.reader[tag], tag)
            self.assertEqual(b['avar'].majorVersion, 2)
            self.assertEqual([(axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue)
                              for axis in b['fvar'].axes], [(tag, *PROFILES[tag]) for tag in ORDER])
            for mapping in b['avar'].segments.values():
                self.assertTrue(all(mapping[value] == value for value in (-1., 0., 1.)))
        self.assertEqual(COMPATIBILITY, 'NOT_VERIFIED')
        self.assertFalse(PRODUCTION_ACCEPTED)

    def test_actual_nominal_requests_include_both_retained_rounding_witnesses(self):
        source = authored_source()
        target = make_avar2_control(source, axes())
        reference, output = native(source), native(target)
        for a, b, c, expected in ((63, 16384, 0, 18688), (9522, 6290, 8581, 21888),
                                  (1141, 7749, 10955, 19072)):
            location = {'WDTH': 500 + 500*a/16384, 'wght': 500 + 400*b/16384,
                        'HGHT': 500 + 500*c/16384}
            q = [source_axis_plan(axis, location[axis.tag])['source_q'] for axis in axes()]
            reference.set_variations(dict(zip(('XWDT', 'XWGT', 'XHGT'), [v/16384 for v in q])))
            output.set_variations(location)
            self.assertEqual(output.get_var_coords_normalized(), reference.get_var_coords_normalized())
            self.assertEqual([reference.get_glyph_h_advance(2), output.get_glyph_h_advance(2)],
                             [expected, expected])
            for gid in range(7):
                for method in ('get_glyph_h_advance', 'get_glyph_v_advance', 'get_glyph_extents'):
                    self.assertEqual(getattr(reference, method)(gid), getattr(output, method)(gid))

    def test_complete_nominal_F2_weight_grid_and_independent_integer_basis_recovery(self):
        source = authored_source()
        target = make_avar2_control(source, axes())
        reference, output = native(source), native(target)
        axis = axes()[1]
        basis = basis_from_axis(axis)
        for q in range(-3072, 3073):
            self.assertEqual(nearest(decode_target_r(basis, encode_source_q(basis, q))), q)
        for n in range(-16384, 16385):
            user = 500 + n*400/16384
            q = source_axis_plan(axis, user)['source_q']
            reference.set_variations({'XWGT': q/16384})
            output.set_variations({'wght': user})
            self.assertEqual(output.get_var_coords_normalized(), reference.get_var_coords_normalized())
            self.assertEqual(output.get_glyph_h_advance(2), reference.get_glyph_h_advance(2))

    def test_control_rejects_other_UPM_glyph_counts_metadata_and_basis(self):
        for mutation in ('UPM', 'GIDs', 'family', 'instances'):
            source = authored_source()
            if mutation == 'UPM': source['head'].unitsPerEm = 2000
            if mutation == 'GIDs': source['maxp'].numGlyphs = 8
            if mutation == 'family':
                for record in source['name'].names:
                    if record.nameID == 1:
                        source['name'].setName('Unrelated font', 1, record.platformID,
                                               record.platEncID, record.langID)
            if mutation == 'instances': source['fvar'].instances = [object()]
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, 'authored_seven'):
                make_avar2_control(source, axes())
        wrong = tuple(SourceAxis(axis.tag, axis.minimum, axis.default, axis.maximum, IDENTITY)
                      for axis in axes())
        with self.assertRaisesRegex(ValueError, 'authored_seven'):
            make_avar2_control(authored_source(), wrong)


if __name__ == '__main__':
    unittest.main()
