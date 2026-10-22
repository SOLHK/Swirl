"""Original analytic data and subprocess doubles for the axis acceptance adapter.

These are protocol/verification tests, not CoreText execution or Apple-font
acceptance. No private font, Apple coordinates, or extracted outline is embedded.
"""
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from test_coretext_extract import make_fixture
from verified_axis_oracle import (BACKEND, SCALARS, VECTORS, VerificationError,
    declare_readback, effective_readback, make_launcher, serve, source_hash, source_identities,
    validate_request, verified_metadata, verify_batch)
from rebuild import NativeOracle


def native_record(request, gid, reported=None):
    """Distinct authored glyphs with both quadratic/cubic commands and raw values."""
    blank = gid == 1
    x = 13.25 + gid
    return {'request_id': request['request_id'], 'face_index': request['face_index'], 'glyph_id': gid,
            'location': copy.deepcopy(request['location']),
            'reported_location': copy.deepcopy(request['location'] if reported is None else reported),
            'commands': [] if blank else [['moveTo', x, -2.5], ['lineTo', 52.75, -2.5],
                ['qCurveTo', 73.125, 24.75, 52.75, 61.5],
                ['curveTo', 41.25, 70.125, 17.75, 35.875, x, -2.5], ['closePath']],
            'bounds': [0., 0., 0., 0.] if blank else [x, -2.5, 59.875, 72.625],
            'path_status': 'nil_path_but_source_proves_empty' if blank else 'path',
            'lsb': 0. if blank else x, 'lsb_derivation': 'authored_fixture_path_min_x',
            'advance_width': 431.25 + gid, 'advance_height': 849.875,
            'horizontal_origin_x': 0., 'horizontal_origin_y': 0.,
            'vertical_origin_x': 215.625, 'vertical_origin_y': 812.125,
            'vertical_origin_derivation': 'authored_raw_API_vector',
            'horizontal_advance_vector': [431.25 + gid, .0625],
            'vertical_advance_vector': [849.875, -.125],
            'vertical_origin_translation': [-215.625, -812.125],
            'horizontal_advance_sum': 431.25 + gid, 'vertical_advance_sum': 849.875, 'error': None}


FAKE_NATIVE = r'''
import hashlib, json, os, sys
from pathlib import Path
from fontTools.ttLib import TTCollection
sys.path.insert(0, TEST_DIRECTORY)
from test_verified_axis_oracle import native_record
if len(sys.argv) != 3 or sys.argv[2] != '--axis-observations':
    raise SystemExit(18)
source=Path(sys.argv[1]); digest=hashlib.sha256(source.read_bytes()).hexdigest()
scenario=os.environ.get('SWIRL_AXIS_ADAPTER_TEST', '')
def emit(value):
    print(json.dumps(value), flush=True)
faces=[]
with TTCollection(source, lazy=True) as fonts:
    for index,font in enumerate(fonts.fonts):
        axes=[{'tag':a.axisTag, 'identifier':int.from_bytes(a.axisTag.encode('ascii'),'big'),
               'minimum':a.minValue,'default':a.defaultValue,'maximum':a.maxValue,
               'flags':a.flags,'hidden':bool(a.flags & 1)} for a in font['fvar'].axes]
        faces.append({'face_index':index,'status':'identity_verified', 'upm':font['head'].unitsPerEm,
                      'glyph_count':font['maxp'].numGlyphs, 'axes':axes,
                      'verified_table_sha256':{tag:hashlib.sha256(font.reader[tag]).hexdigest()
                                                for tag in font.reader.tables}})
meta={'type':'metadata','backend':'CoreText','source_sha256':digest,
      'source_byte_size':source.stat().st_size,'faces':faces,'axis_observations_only':True,
      'metrics_policy':'authored subprocess double, not a native test'}
if scenario=='bad_metadata': meta['faces'][0]['verified_table_sha256']['head']='0'*64
emit(meta)
# The adapter must not turn native stderr into a public/private outline log.
print('ORIGINAL_OUTLINE_SENTINEL',file=sys.stderr,flush=True)
count=glyphs=0
for line in sys.stdin:
    request=json.loads(line); count+=1
    if scenario=='early_eof': raise SystemExit(0)
    if scenario=='timeout':
        import time
        time.sleep(.5)
    for gid in request['glyph_ids']:
        if scenario=='native_error' and gid==request['glyph_ids'][-1]:
            emit({'request_id':request['request_id'],'face_index':request['face_index'],
                  'glyph_id':gid,'error':'authored_native_failure'})
            continue
        record=native_record(request,gid)
        if scenario=='late_mismatch' and request['request_id'].endswith('-reported') and gid==request['glyph_ids'][-1]:
            record['vertical_advance_sum']+=.000001
        emit(record); glyphs+=1
if scenario=='changed_source':
    with source.open('ab') as stream: stream.write(b'original-test-only-change')
emit({'type':'summary','source_sha256':digest,'error_count':0,
      'request_count':count,'successful_glyph_count':glyphs+(1 if scenario=='bad_summary' else 0)})
'''


class VerifiedAxisOracleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.source = self.directory / 'original-independent-fixture.ttc'
        make_fixture(self.source)
        self.fonts = TTCollection(self.source, lazy=True)
        self.addCleanup(self.fonts.close)
        self.identities = source_identities(self.fonts.fonts)
        self.digest = source_hash(self.source)
        self.native = self.directory / 'native-test-double'
        self.native.write_text('#!' + sys.executable + '\n' + FAKE_NATIVE.replace(
            'TEST_DIRECTORY', repr(str(Path(__file__).resolve().parent))), encoding='utf-8')
        self.native.chmod(0o700)

    def request(self, **changes):
        return {'request_id': 'outer-exact-id', 'face_index': 0,
                'location': {'WDTH': 500., 'wght': 400., 'HGHT': 500.}, 'glyph_ids': [0, 1, 2], **changes}

    def metadata(self):
        # Spell out the Swift Axis.json protocol independently of the adapter's
        # source_identities implementation. WDTH/HGHT are deliberately hidden
        # in this original fixture; a missing flags/hidden schema must fail.
        axes = [{'tag': 'WDTH', 'identifier': 0x57445448, 'minimum': 1., 'default': 500.,
                 'maximum': 1000., 'flags': 1, 'hidden': True},
                {'tag': 'wght', 'identifier': 0x77676874, 'minimum': 100., 'default': 400.,
                 'maximum': 900., 'flags': 0, 'hidden': False},
                {'tag': 'HGHT', 'identifier': 0x48474854, 'minimum': 1., 'default': 500.,
                 'maximum': 1000., 'flags': 1, 'hidden': True}]
        return {'type': 'metadata', 'backend': 'CoreText', 'source_sha256': self.digest,
                'source_byte_size': self.source.stat().st_size, 'axis_observations_only': True,
                'faces': [{'face_index': i, 'status': 'identity_verified', 'upm': upm, 'glyph_count': 3,
                           'axes': copy.deepcopy(axes),
                           'verified_table_sha256': {tag: hashlib.sha256(font.reader[tag]).hexdigest()
                                                    for tag in font.reader.tables}}
                          for i, (font, upm) in enumerate(zip(self.fonts.fonts, (1000, 1128)))]}

    def exchange(self, *, reported=None, mutate=None):
        calls = []
        def exchange(request):
            calls.append(copy.deepcopy(request))
            rows = [native_record(request, gid,
                    reported if not request['request_id'].endswith('-reported') else None)
                    for gid in request['glyph_ids']]
            if mutate:
                mutate(request, rows)
            return rows
        return calls, exchange

    def adapter(self, request=None, scenario='', **options):
        output = io.StringIO()
        lines = json.dumps(self.request() if request is None else request) + '\n'
        with mock.patch.dict(os.environ, {'SWIRL_AXIS_ADAPTER_TEST': scenario}):
            code = serve(self.source, self.native, io.StringIO(lines), output, **options)
        return code, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_complete_request_requires_finite_explicit_axes_unique_valid_GIDs(self):
        self.assertEqual(validate_request(self.request(), self.identities), self.identities[0])
        changes = [{'location': {'WDTH': 500.}}, {'location': {'WDTH': 500., 'wght': 400., 'HGHT': 1001.}},
                   {'location': {'WDTH': float('nan'), 'wght': 400., 'HGHT': 500.}},
                   {'location': {'WDTH': True, 'wght': 400., 'HGHT': 500.}},
                   {'location': {'WDTH': 500., 'wght': 400., 'HGHT': 500., 'fake': 1.}},
                   {'face_index': -1}, {'face_index': True}, {'face_index': 2}, {'request_id': ''},
                   {'request_id': 1}, {'request_id': 'x' * 1025}, {'glyph_ids': []},
                   {'glyph_ids': [0, 0]}, {'glyph_ids': [3]}, {'glyph_ids': [True]}, {'ignored_flag': True}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(VerificationError):
                validate_request(self.request(**change), self.identities)

    def test_all_tables_faces_axes_and_explicit_observation_metadata_are_bound(self):
        native = self.metadata(); before = copy.deepcopy(native)
        actual = verified_metadata(native, self.digest, self.source.stat().st_size, self.identities)
        self.assertEqual(native, before)
        self.assertTrue(actual['upstream_axis_observations_only'])
        self.assertFalse(actual['axis_observations_only'])
        self.assertEqual(actual['axis_verification_backend'], BACKEND)
        self.assertEqual(actual['faces'], before['faces'])
        variants = []
        for changes in ({'source_sha256': '0' * 64}, {'source_byte_size': 1}, {'backend': 'other'},
                        {'axis_observations_only': False}, {'axis_observations_only': 1},
                        {'diagnostic_readback_observation_only': True}, {'metric_backend': 'SourceTables'},
                        {'axis_verification_backend': 'already_verified'}, {'faces': []}):
            variants.append({**native, **changes})
        for field, value in (('upm', 999), ('glyph_count', 4), ('face_index', 1), ('status', 'observed')):
            changed = copy.deepcopy(native); changed['faces'][0][field] = value; variants.append(changed)
        for field, value in (('head', '0' * 64), ('missing_table', 'a' * 64)):
            changed = copy.deepcopy(native); changed['faces'][0]['verified_table_sha256'][field] = value
            variants.append(changed)
        changed = copy.deepcopy(native); del changed['faces'][0]['verified_table_sha256']['name']; variants.append(changed)
        changed = copy.deepcopy(native); changed['faces'][0]['axes'][0]['default'] += 1; variants.append(changed)
        for changed in variants:
            with self.assertRaises(VerificationError):
                verified_metadata(changed, self.digest, self.source.stat().st_size, self.identities)

    def test_actual_swift_axis_schema_flags_and_hidden_are_required(self):
        native = self.metadata()
        self.assertEqual(native['faces'][0]['axes'][0]['flags'], 1)
        self.assertIs(native['faces'][0]['axes'][0]['hidden'], True)
        self.assertIs(native['faces'][0]['axes'][1]['hidden'], False)
        verified_metadata(native, self.digest, self.source.stat().st_size, self.identities)
        for field in ('flags', 'hidden'):
            changed = copy.deepcopy(native); del changed['faces'][0]['axes'][0][field]
            with self.assertRaisesRegex(VerificationError, 'table_identity_mismatch'):
                verified_metadata(changed, self.digest, self.source.stat().st_size, self.identities)
        changed = copy.deepcopy(native); changed['faces'][0]['axes'][0]['hidden'] = False
        with self.assertRaisesRegex(VerificationError, 'table_identity_mismatch'):
            verified_metadata(changed, self.digest, self.source.stat().st_size, self.identities)

    def test_exact_and_decimal_candidate_preserve_all_original_values(self):
        request = self.request(location={'WDTH': 612.3456789, 'wght': 412.3456789, 'HGHT': 712.3456789})
        reported = {'WDTH': 612.3456, 'wght': 412.3456, 'HGHT': 712.3456}
        calls, exchange = self.exchange(reported=reported)
        result = verify_batch(request, self.identities, self.digest, exchange, 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]['location'], request['location'])
        self.assertEqual(calls[1]['location'], reported)
        for gid, record in zip(request['glyph_ids'], result):
            expected = native_record(request, gid, reported)
            self.assertEqual({k: v for k, v in record.items() if k != 'axis_verification'}, expected)
            self.assertEqual(record['axis_verification']['changed_axes'], ['WDTH', 'wght', 'HGHT'])
            self.assertTrue(record['axis_verification']['exact_native_payload_equality'])
        calls, exchange = self.exchange()
        direct = verify_batch(self.request(), self.identities, self.digest, exchange, 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(direct[0]['axis_verification']['changed_axes'], [])

    def test_missing_nondefault_axis_fails_even_inside_the_old_epsilon(self):
        request = self.request(location={'WDTH': 500.00000001, 'wght': 400., 'HGHT': 500.})
        calls, exchange = self.exchange(reported={})
        with self.assertRaisesRegex(VerificationError, 'nondefault_axis_not_reported'):
            verify_batch(request, self.identities, self.digest, exchange, 1)
        self.assertEqual(len(calls), 1)
        calls, exchange = self.exchange(reported={})
        self.assertEqual(len(verify_batch(self.request(), self.identities, self.digest, exchange, 2)), 3)

    def test_wrong_decimal_candidate_unknown_axis_and_nonpositive_mismatch_fail(self):
        request = self.request(location={'WDTH': 612.3456789, 'wght': 400., 'HGHT': 500.})
        for reported in ({'WDTH': 612.3457}, {'WDTH': 612.34560001}, {'WDTH': 500.},
                         {'WDTH': 612.3456, 'fake': 1.}, {'WDTH': float('inf')}, {'WDTH': True}):
            _, exchange = self.exchange(reported=reported)
            with self.assertRaises(VerificationError):
                verify_batch(request, self.identities, self.digest, exchange, 1)
        identity = copy.deepcopy(self.identities[0]); identity['axes'][0]['minimum'] = -1000.
        with self.assertRaisesRegex(VerificationError, 'positive_decimal4_candidate_unavailable'):
            effective_readback({'reported_location': {'WDTH': -12.3456}}, identity,
                               {'WDTH': -12.3456789, 'wght': 400., 'HGHT': 500.})

    def test_echo_drift_is_rejected_without_any_recursive_request(self):
        request = self.request(location={'WDTH': 612.3456789, 'wght': 400., 'HGHT': 500.})
        def mutate(request, records):
            if request['request_id'].endswith('-reported'):
                for record in records: record['reported_location']['WDTH'] -= .0001
        calls, exchange = self.exchange(reported={'WDTH': 612.3456}, mutate=mutate)
        with self.assertRaisesRegex(VerificationError, 'replay_not_exactly_stable'):
            verify_batch(request, self.identities, self.digest, exchange, 1)
        self.assertEqual(len(calls), 2)

    def test_candidate_failure_preserves_exact_binary64_values_and_stage(self):
        # Original analytic input: the alternative is one binary64 ULP away,
        # not an approved native candidate and not accepted through tolerance.
        request = self.request(location={'WDTH': 612.3456789, 'wght': 400., 'HGHT': 500.})
        candidate = 612.3456
        observed = math.nextafter(candidate, math.inf)
        calls, exchange = self.exchange(reported={'WDTH': observed})
        with self.assertRaisesRegex(VerificationError, 'not_named_decimal4_candidate') as raised:
            verify_batch(request, self.identities, self.digest, exchange, 1)
        context = raised.exception.context
        self.assertEqual(context['phase'], 'original')
        self.assertEqual(context['axis'], 'WDTH')
        self.assertEqual(context['glyph_id'], 0)
        self.assertEqual(context['requested_value'], request['location']['WDTH'])
        self.assertEqual(context['reported_value'], observed)
        self.assertEqual(context['reported_value_hex'], observed.hex())
        self.assertEqual(context['expected_candidate_value'], candidate)
        self.assertEqual(context['expected_candidate_value_hex'], candidate.hex())
        self.assertNotEqual(context['reported_value_hex'], context['expected_candidate_value_hex'])
        self.assertEqual(len(calls), 1)

    def test_replay_failure_retains_original_request_and_actual_second_readback(self):
        request = self.request(location={'WDTH': 612.3456789, 'wght': 400., 'HGHT': 500.})
        def mutate(request, records):
            if request['request_id'].endswith('-reported'):
                for record in records: record['reported_location']['WDTH'] = 612.3455
        calls, exchange = self.exchange(reported={'WDTH': 612.3456}, mutate=mutate)
        with self.assertRaisesRegex(VerificationError, 'replay_not_exactly_stable') as raised:
            verify_batch(request, self.identities, self.digest, exchange, 1)
        context = raised.exception.context
        self.assertEqual(context['phase'], 'replay')
        self.assertEqual(context['source_requested_value'], 612.3456789)
        self.assertEqual(context['requested_value'], 612.3456)
        self.assertEqual(context['reported_value'], 612.3455)
        self.assertEqual(context['reported_value_hex'], float(612.3455).hex())
        self.assertNotIn('expected_candidate_value', context)
        self.assertEqual(len(calls), 2)

    def test_109_independent_binary64_boundary_values_need_no_repeated_truncation(self):
        # These grid values are generated analytically, not read from Apple data.
        cases = []
        for integer in range(6_000_000, 6_020_000):
            reported = integer / 10000
            requested = reported + .000037
            if (math.trunc(reported * 10000) / 10000 != reported
                    and math.trunc(requested * 10000) / 10000 == reported):
                cases.append((requested, reported))
                if len(cases) == 109: break
        self.assertEqual(len(cases), 109)
        for number, (requested, reported) in enumerate(cases):
            request = self.request(location={'WDTH': requested, 'wght': 400., 'HGHT': 500.}, glyph_ids=[0])
            calls, exchange = self.exchange(reported={'WDTH': reported})
            result = verify_batch(request, self.identities, self.digest, exchange, number)
            self.assertEqual(len(calls), 2)
            self.assertEqual(result[0]['location']['WDTH'], requested)
            self.assertEqual(result[0]['axis_verification']['native_replay_count'], 1)

    def test_fixed_second_step_is_predeclared_and_not_selected_from_the_first_echo(self):
        # An authored arithmetic grid, independent of either native artifact.
        value = next(n / 10000 + .000037 for n in range(6_000_000, 6_020_000)
                     if math.trunc((n / 10000) * 10000) / 10000 != n / 10000)
        location = {'WDTH': value, 'wght': 400., 'HGHT': 500.}
        declaration = declare_readback(location)
        once, twice = declaration['WDTH']['once'], declaration['WDTH']['twice']
        self.assertNotEqual(once, twice)
        request = self.request(location=location)
        for first_echo in (once, twice):
            calls, exchange = self.exchange(reported={'WDTH': first_echo})
            result = verify_batch(request, self.identities, self.digest, exchange, 1)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]['location'], location)
            self.assertEqual(calls[1]['location']['WDTH'], twice)
            for row in result:
                self.assertEqual(row['location'], location)
                self.assertEqual(row['reported_location'], {'WDTH': first_echo})
                proof = row['axis_verification']
                self.assertEqual(proof['predeclared_replay_location']['WDTH'], twice)
                self.assertTrue(proof['replay_declared_before_native_observations'])
                self.assertTrue(proof['replay_echo_exactly_stable'])

    def test_a_second_step_candidate_still_requires_actual_stable_echo_and_every_payload_field(self):
        location = {'WDTH': 600.000437, 'wght': 400., 'HGHT': 500.}
        # Pick a reproducible independently generated non-idempotent boundary.
        for n in range(6_000_000, 6_020_000):
            value = n / 10000 + .000037
            plan = declare_readback({'WDTH': value})['WDTH']
            if plan['once'] != plan['twice']:
                location['WDTH'] = value
                break
        request = self.request(location=location)
        for field in ('reported_location', 'commands', 'vertical_advance_sum'):
            def mutate(native_request, rows):
                if native_request['request_id'].endswith('-reported'):
                    if field == 'reported_location': rows[-1][field]['WDTH'] -= .0001
                    elif field == 'commands': rows[-1][field][0][1] += 1e-10
                    else: rows[-1][field] += 1e-10
            calls, exchange = self.exchange(reported={'WDTH': plan['twice']}, mutate=mutate)
            with self.subTest(field=field), self.assertRaises(VerificationError):
                verify_batch(request, self.identities, self.digest, exchange, 1)
            self.assertEqual(len(calls), 2, 'a failed fixed replay cannot trigger another construction')

    def test_predeclared_candidate_cannot_be_clamped_into_the_source_range(self):
        identities = copy.deepcopy(self.identities)
        identities[0]['axes'][0]['minimum'] = 600.000037
        request = self.request(location={'WDTH': 600.000037, 'wght': 400., 'HGHT': 500.})
        calls, exchange = self.exchange()
        with self.assertRaisesRegex(VerificationError, 'predeclared_axis_candidate_outside_source_range'):
            verify_batch(request, identities, self.digest, exchange, 1)
        self.assertEqual(calls, [])

    def test_one_changed_scalar_vector_sum_status_or_future_field_rejects_batch(self):
        mutations = []
        for field in SCALARS:
            mutations.append((field, lambda r, f=field: r.__setitem__(f, r[f] + 1e-10)))
        for field, size in VECTORS.items():
            for index in range(size):
                mutations.append((field, lambda r, f=field, i=index: r[f].__setitem__(i, r[f][i] + 1e-10)))
        mutations += [('path_status', lambda r: r.__setitem__('path_status', 'empty_path')),
                      ('lsb_derivation', lambda r: r.__setitem__('lsb_derivation', 'different_basis')),
                      ('new_native_value', lambda r: r.__setitem__('new_native_value', 123.))]
        for field, change in mutations:
            def mutate(request, rows):
                if request['request_id'].endswith('-reported'): change(rows[-1])
            _, exchange = self.exchange(mutate=mutate)
            with self.subTest(field=field), self.assertRaises(VerificationError):
                verify_batch(self.request(), self.identities, self.digest, exchange, 1)

    def test_commands_keep_type_order_and_every_coordinate_exact(self):
        for change in (lambda r: r['commands'][0].__setitem__(1, 15.25000000001),
                       lambda r: r['commands'].__setitem__(slice(0, 2), r['commands'][1::-1]),
                       lambda r: r['commands'][1].__setitem__(0, 'moveTo'),
                       lambda r: r['commands'][2].pop(),
                       lambda r: r['commands'][0].__setitem__(1, '15.25'),
                       lambda r: r['commands'][0].__setitem__(1, True)):
            def mutate(request, rows):
                if request['request_id'].endswith('-reported'): change(rows[-1])
            _, exchange = self.exchange(mutate=mutate)
            with self.assertRaises(VerificationError):
                verify_batch(self.request(), self.identities, self.digest, exchange, 1)

    def test_missing_nonfinite_and_already_adapted_native_values_are_rejected(self):
        for field, value in (('advance_width', None), ('advance_height', float('nan')),
                             ('horizontal_advance_sum', True), ('commands', None), ('bounds', [0., 0., float('inf'), 1.]),
                             ('raw_coretext_metrics', {}), ('axis_verification', {}), ('metric_backend', 'SourceTables')):
            def mutate(request, rows): rows[-1][field] = value
            _, exchange = self.exchange(mutate=mutate)
            with self.subTest(field=field), self.assertRaises(VerificationError):
                verify_batch(self.request(), self.identities, self.digest, exchange, 1)
        for field in SCALARS + tuple(VECTORS) + ('lsb_derivation', 'vertical_origin_derivation', 'path_status', 'error'):
            def mutate(request, rows): rows[-1].pop(field)
            _, exchange = self.exchange(mutate=mutate)
            with self.subTest(missing=field), self.assertRaises(VerificationError):
                verify_batch(self.request(), self.identities, self.digest, exchange, 1)

    def test_response_request_GID_location_and_batch_readback_identity_are_checked(self):
        mutations = [lambda rows: rows[-1].__setitem__('request_id', 'unrelated'),
                     lambda rows: rows[-1].__setitem__('face_index', 1),
                     lambda rows: rows[-1].__setitem__('glyph_id', 0),
                     lambda rows: rows[-1].__setitem__('glyph_id', 999),
                     lambda rows: rows[-1].__setitem__('location', {'WDTH': 500.}),
                     lambda rows: rows[-1].__setitem__('reported_location', {}),
                     lambda rows: rows.pop()]
        for change in mutations:
            _, exchange = self.exchange(mutate=lambda request, rows: change(rows))
            with self.assertRaises(VerificationError):
                verify_batch(self.request(), self.identities, self.digest, exchange, 1)

    def test_real_pipe_protocol_counts_only_verified_external_records(self):
        code, rows = self.adapter()
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), 5)
        self.assertFalse(rows[0]['axis_observations_only'])
        self.assertTrue(rows[0]['upstream_axis_observations_only'])
        for row in rows[1:-1]:
            self.assertEqual(row['request_id'], 'outer-exact-id')
            self.assertTrue(row['axis_verification']['exact_native_payload_equality'])
        self.assertEqual(rows[-1]['successful_glyph_count'], 3)
        self.assertEqual(rows[-1]['request_count'], 1)
        self.assertEqual(rows[-1]['internal_native_request_count'], 2)
        self.assertEqual(rows[-1]['internal_native_glyph_count'], 6)
        self.assertEqual(rows[-1]['upstream_native_summary']['successful_glyph_count'], 6)
        self.assertTrue(rows[-1]['source_unchanged'])
        self.assertNotIn('ORIGINAL_OUTLINE_SENTINEL', json.dumps(rows))

    def test_late_GID_failure_releases_no_successful_record_from_the_batch(self):
        code, rows = self.adapter(scenario='late_mismatch')
        self.assertEqual(code, 3)
        self.assertEqual([r.get('type') for r in rows], ['metadata', 'request_error'])
        self.assertEqual(rows[-1]['request_id'], 'outer-exact-id')
        self.assertEqual(rows[-1]['glyph_id'], 2)
        self.assertEqual(rows[-1]['field'], 'vertical_advance_sum')
        self.assertNotIn('commands', rows[-1])

    def test_native_error_is_forwarded_under_the_external_request_identity(self):
        code, rows = self.adapter(scenario='native_error')
        self.assertEqual(code, 3)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]['native_error'], 'authored_native_failure')
        self.assertEqual(rows[-1]['request_id'], 'outer-exact-id')
        self.assertEqual(rows[-1]['face_index'], 0)
        self.assertNotIn('commands', rows[-1])

    def test_bad_source_metadata_and_invalid_request_fail_before_glyph_release(self):
        code, rows = self.adapter(scenario='bad_metadata')
        self.assertEqual(code, 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['error'], 'native_face_or_original_table_identity_mismatch')
        code, rows = self.adapter(self.request(glyph_ids=[0, 0]))
        self.assertEqual(code, 3)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]['request_id'], 'outer-exact-id')
        output = io.StringIO()
        self.assertEqual(serve(self.directory / 'absent.ttc', self.native, io.StringIO(), output), 2)
        self.assertEqual(json.loads(output.getvalue())['type'], 'fatal_error')

    def test_EOF_deadline_and_buffer_limit_do_not_fabricate_empty_glyphs(self):
        for scenario, options in (('early_eof', {}), ('timeout', {'response_timeout': .2}),
                                  ('', {'maximum_batch_bytes': 50})):
            code, rows = self.adapter(scenario=scenario, **options)
            self.assertNotEqual(code, 0)
            self.assertFalse(any('commands' in row for row in rows))

    def test_invalid_summary_and_changed_source_have_no_success_summary(self):
        for scenario in ('bad_summary', 'changed_source'):
            with self.subTest(scenario=scenario):
                original = self.source.read_bytes()
                code, rows = self.adapter(scenario=scenario)
                self.assertNotEqual(code, 0)
                self.assertFalse(any(row.get('type') == 'summary' for row in rows))
                self.assertEqual(rows[-1]['type'], 'fatal_error')
                self.source.write_bytes(original)

    def test_launcher_runs_protocol_and_binds_native_and_dependency_hashes(self):
        launcher = make_launcher(self.directory / 'verified-oracle', self.native)
        content = launcher.read_text()
        self.assertIn(source_hash(self.native), content)
        self.assertIn('incremental_pipe.py', content)
        self.assertTrue(os.access(launcher, os.X_OK))
        completed = subprocess.run([str(launcher), str(self.source)],
            input=json.dumps(self.request()) + '\n', text=True, capture_output=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        rows = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(rows[-1]['successful_glyph_count'], 3)
        self.assertEqual(completed.stderr, '')
        with self.assertRaisesRegex(VerificationError, 'new_launcher_path_required'):
            make_launcher(launcher, self.native)
        self.native.write_text(self.native.read_text() + '\n# changed independently authored native fixture\n')
        changed = subprocess.run([str(launcher), str(self.source)],
            input='', text=True, capture_output=True, timeout=20)
        self.assertEqual(changed.returncode, 2)
        self.assertEqual(json.loads(changed.stdout)['error'], 'axis_launcher_dependency_changed')

    def test_builder_consumes_verified_launcher_and_external_final_summary(self):
        launcher = make_launcher(self.directory / 'builder-axis-oracle', self.native)
        oracle = NativeOracle(launcher, self.source, self.directory / 'private-native.log')
        try:
            point = self.request()['location']
            self.assertEqual(len(oracle.samples(0, [0, 1, 2], point)), 3)
            self.assertEqual(len(oracle.samples(1, [2], point)), 1)
            summary = oracle.finish()
            self.assertEqual(summary['request_count'], 2)
            self.assertEqual(summary['successful_glyph_count'], 4)
            self.assertEqual(summary['internal_native_request_count'], 4)
            self.assertEqual(summary['internal_native_glyph_count'], 8)
            self.assertIs(oracle.finish(), summary)
        finally:
            oracle.close()


if __name__ == '__main__':
    unittest.main()
