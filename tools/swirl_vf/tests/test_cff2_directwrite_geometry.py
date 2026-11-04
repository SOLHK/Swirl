"""Authored protocol/coordinate counterexamples, not Windows native evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTCollection

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from make_cff2_fixture import geometry, records
from test_coretext_extract import make_fixture
from verify_cff2_directwrite_geometry import compare, expected_positions, float32, validate_instances, verify


class DirectWriteGeometryValidationTests(unittest.TestCase):
    def transcript(self, sources):
        # Authored protocol records. These never stand in for Windows execution.
        transcript = [dict(record='header', physical_face_count=len(sources),
            directwrite_supported=True, all_glyphs=True,
            outline_coordinates_exported=True, input_sha256='authored-test-only')]
        for face, source in enumerate(sources):
            transcript.append(dict(record='face', face_index=face, glyph_count=3,
                probed_glyph_count=3, axes=[dict(tag=a.axisTag, min=a.minValue,
                    default=a.defaultValue, max=a.maxValue) for a in source['fvar'].axes]))
            for case, point in expected_positions(source).items():
                transcript.append(dict(record='instance', face_index=face, case=case,
                    requested=point, applied=dict(point, wdth=100, ital=0, slnt=0), status='PASS'))
            transcript.append(dict(record='face_result', face_index=face,
                status='PASS_NATIVE_PROBE', positions=62))
        transcript.append(dict(record='summary', status='PASS_NATIVE_PROBE',
            faces_passed=len(sources), faces_failed=0))
        return transcript, dict(input_sha256='authored-test-only', native_exit_code=0, input_unchanged=True)

    def test_declared_plan_contains_all_corners_and_fractional_three_axis_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as source:
                plan=expected_positions(source.fonts[0])
                self.assertEqual(len(plan),62)
                self.assertEqual(plan['grid_0'],dict(WDTH=1,wght=100,HGHT=1))
                self.assertEqual(plan['grid_26'],dict(WDTH=1000,wght=900,HGHT=1000))
                self.assertEqual(plan['grid_13'],plan['default'])
                self.assertEqual(plan['grid_1'],dict(WDTH=500,wght=100,HGHT=1))
                self.assertNotEqual(plan['internal_1'],plan['default'])
                transcript,native=self.transcript(source.fonts)
                instances,complete=validate_instances(transcript,native,source.fonts)
                self.assertEqual(len(instances),124); self.assertTrue(complete)

    def test_same_count_cannot_replace_mixed_axes_with_default_or_unknown_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as source:
                transcript,native=self.transcript(source.fonts)
                original=next(r for r in transcript if r.get('case')=='internal_1')
                for field,value,reason in (
                    ('case','invented_62nd_case','unrequested'),
                    ('requested',dict(WDTH=500,wght=400,HGHT=500),'coordinate_plan'),
                    ('applied',dict(WDTH=500,wght=400,HGHT=500),'readback'),
                ):
                    with self.subTest(field=field):
                        changed=copy.deepcopy(transcript)
                        changed[transcript.index(original)][field]=value
                        with self.assertRaisesRegex(ValueError,reason):
                            validate_instances(changed,native,source.fonts)

    def test_one_FLOAT_ulp_width_drift_is_rejected_without_decimal_epsilon(self):
        import struct
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as source:
                transcript,native=self.transcript(source.fonts)
                row=next(r for r in transcript if r.get('case')=='internal_1')
                wanted=row['requested']['WDTH']
                bits=struct.unpack('>I',struct.pack('>f',wanted))[0]
                row['applied']['WDTH']=struct.unpack('>f',struct.pack('>I',bits+1))[0]
                self.assertLess(abs(row['applied']['WDTH']-wanted),abs(wanted)*1e-6)
                with self.assertRaisesRegex(ValueError,'readback'):
                    validate_instances(transcript,native,source.fonts)
                row['applied']['WDTH']=float(format(wanted,'.9g'))
                self.assertEqual(float32(row['applied']['WDTH']),wanted)
                self.assertTrue(validate_instances(transcript,native,source.fonts)[1])

    def test_missing_duplicate_and_failed_terminal_receipts_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as source:
                transcript,native=self.transcript(source.fonts)
                for changed,reason in ((transcript[:-1],'completion'),
                        (transcript[:3]+[transcript[2]]+transcript[3:],'duplicate'),
                        (transcript[:2]+transcript[3:],'incomplete')):
                    with self.assertRaisesRegex(ValueError,reason):
                        validate_instances(changed,native,source.fonts)
                changed=copy.deepcopy(transcript)
                changed[-1].update(status='FAILED',faces_passed=1,faces_failed=1)
                self.assertFalse(validate_instances(changed,native,source.fonts)[1])
                with self.assertRaisesRegex(ValueError,'identity'):
                    validate_instances(transcript,dict(native,input_sha256='other'),source.fonts)

    def test_no_coordinate_export_and_removed_face_axis_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as source:
                transcript,native=self.transcript(source.fonts)
                changed=copy.deepcopy(transcript);changed[0]['all_glyphs']=False
                with self.assertRaisesRegex(ValueError,'export'):
                    validate_instances(changed,native,source.fonts)
                changed=copy.deepcopy(transcript);changed[1]['axes'].pop()
                with self.assertRaisesRegex(ValueError,'coverage'):
                    validate_instances(changed,native,source.fonts)

    def test_complete_geometry_does_not_override_failed_native_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as source:
                transcript,native=self.transcript(source.fonts)
                rows=[]
                for row in transcript:
                    if row.get('record')!='instance': continue
                    font=source.fonts[row['face_index']];user=row['requested']
                    point={a.axisTag:(user[a.axisTag]-a.defaultValue)/(
                        a.maxValue-a.defaultValue if user[a.axisTag]>=a.defaultValue
                        else a.defaultValue-a.minValue) for a in font['fvar'].axes}
                    for gid,name in enumerate(font.getGlyphOrder()):
                        commands=records(font,name,[point],.25)[0]
                        for command in commands:
                            for i in range(2,len(command),2): command[i]=-command[i]
                        rows.append(dict(record='outline',face_index=row['face_index'],
                            case=row['case'],glyph_id=gid,upm=font['head'].unitsPerEm,
                            axes=user,coordinate_frame='x_right_y_down_font_units',commands=commands))
                export=Path(tmp)/'authored-protocol.jsonl'
                export.write_text(''.join(json.dumps(r)+'\n' for r in rows))
                native['outline_coordinates_sha256']=hashlib.sha256(export.read_bytes()).hexdigest()
                result=verify(export,transcript,native,variant='flat')
                self.assertEqual(result['status'],'PASS_AUTHORED_GEOMETRY')
                self.assertEqual(result['observations'],372)
                native['native_exit_code']=1
                failed=verify(export,transcript,native,variant='flat')
                self.assertEqual(failed['status'],'FAIL_AUTHORED_GEOMETRY')
                self.assertEqual(failed['failed_observations'],0)
                self.assertFalse(failed['native_completed_successfully'])
                self.assertFalse(failed['production_accepted'])

    def test_screen_coordinates_require_explicit_y_inversion_and_matching_axes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'authored.ttc';make_fixture(path)
            with TTCollection(path) as original:
                for font in original.fonts:
                    for p in ({'WDTH':-1.,'wght':0.,'HGHT':1.},
                              {'WDTH':.25,'wght':-.5,'HGHT':.75}):
                        user={a.axisTag:a.defaultValue+p[a.axisTag]*(a.maxValue-a.defaultValue if
                            p[a.axisTag]>=0 else a.defaultValue-a.minValue) for a in font['fvar'].axes}
                        for gid,name in enumerate(font.getGlyphOrder()):
                            # Elevate through a CharString pen independently of
                            # the validator's coordinate-system adapter.
                            commands=records(font,name,[p],.25)[0]
                            for command in commands:
                                for i in range(2,len(command),2):command[i]=-command[i]
                            row={'record':'outline','coordinate_frame':'x_right_y_down_font_units',
                                 'glyph_id':gid,'upm':font['head'].unitsPerEm,'axes':user,'commands':commands}
                            self.assertTrue(compare(row,font)['passed'])
                            bad=copy.deepcopy(row);bad['coordinate_frame']='unknown'
                            with self.assertRaisesRegex(ValueError,'frame_not_proven'):compare(bad,font)
                            if commands:
                                bad=copy.deepcopy(row)
                                for command in bad['commands']:
                                    for i in range(1,len(command),2):command[i]+=.125
                                self.assertFalse(compare(bad,font)['passed'])

    def test_missing_path_and_invalid_numeric_input_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'authored.ttc';make_fixture(path)
            with TTCollection(path) as original:
                font=original.fonts[0]
                row={'record':'outline','coordinate_frame':'x_right_y_down_font_units',
                     'glyph_id':2,'upm':1000,'axes':{'WDTH':500.,'wght':400.,'HGHT':500.},'commands':[]}
                self.assertFalse(compare(row,font)['passed'])
                row['axes']['WDTH']=float('nan')
                with self.assertRaisesRegex(ValueError,'invalid_native_outline_axis_value'):compare(row,font)
                row['axes']['WDTH']=500.;row['axes']['wdth']=500.
                with self.assertRaisesRegex(ValueError,'axis_set_changed'):compare(row,font)
