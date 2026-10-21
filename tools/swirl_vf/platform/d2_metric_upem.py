#!/usr/bin/env python3
"""Small independent extension of B1's frozen UPEM metric hypothesis.

Self-authored fixture only. Six fresh UPEMs supplement the known 1000/1024
controls. Every raw measurement stays unchanged; candidate agreement is not a
strict metric pass and does not prove Apple's internal arithmetic.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import platform
import sys

from fontTools.ttLib import TTCollection
from macos_source_baseline import digest
from test_coretext_extract import make_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rebuild import NativeOracle

UPMS = (1000, 1024, 1001, 1023, 2047, 4093, 8191, 16383)
HEIGHTS = (1., 500., 1000., 625., 914.0625)
BITS = (6, 14, 16, 20, 24)


def round_away(x):
    x = Fraction(x)
    return (1 if x >= 0 else -1) * math.floor(abs(x) + Fraction(1, 2))


def predictions(upm, height):
    y = (Fraction(height) - 500) / (499 if height < 500 else 500)
    phantom_height = 1000 + round_away(60*y) - round_away(-90*y)
    quantized = Fraction(math.floor(Fraction(phantom_height*65536, upm))*upm, 65536)
    return {'continuous_height': float(1000 + 150*y),
            'frozen_B1_gvar_height': math.trunc(quantized),
            'horizontal_candidates': {str(bits): float(Fraction(
                math.floor(Fraction(670*(2**bits), upm))*upm, 2**bits)) for bits in BITS}}


def build_fixture(original, output, upm):
    with TTCollection(original) as collection:
        reference = collection.fonts[0]
        head_before = reference.reader['head']
        protected = {str(tag): reference.reader[tag] for tag in reference.reader.tables if tag != 'head'}
        reference['head'].unitsPerEm = upm
        reference.recalcTimestamp = False
        collection.fonts = [reference]
        collection.save(output)
    with TTCollection(output, lazy=True) as saved:
        font = saved.fonts[0]
        if len(saved.fonts) != 1 or font['head'].unitsPerEm != upm:
            raise ValueError('fixture_upem_or_face_changed')
        def mask_head(data):
            data = bytearray(data); data[8:12] = bytes(4); data[18:20] = bytes(2)
            return bytes(data)
        if mask_head(font.reader['head']) != mask_head(head_before):
            raise ValueError('unexpected_head_change_beyond_upem_and_checksum')
        if {str(tag): font.reader[tag] for tag in font.reader.tables if tag != 'head'} != protected:
            raise ValueError('only_head_units_per_em_may_change')
        return {str(tag): digest_bytes(font.reader[tag]) for tag in font.reader.tables}


def digest_bytes(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def validate_replay(left, right):
    if set(left) != set(right):
        raise ValueError('replay_case_set_changed')
    for key in left:
        # Ignore only the transport request ID changed by reverse request order.
        a = {k:v for k,v in left[key].items() if k != 'request_id'}
        b = {k:v for k,v in right[key].items() if k != 'request_id'}
        if a != b:
            raise ValueError('raw_native_replay_changed')


def run(binary, output):
    binary, output = Path(binary).resolve(strict=True), Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('fresh_private_metric_output_required')
    if platform.system() != 'Darwin':
        raise RuntimeError('CoreText unavailable; native metric diagnosis NOT_RUN')
    output.mkdir(parents=True, mode=0o700)
    original = output / 'self-authored-two-face.ttc'
    make_fixture(original)
    plan = {'upms': list(UPMS), 'heights': list(HEIGHTS),
            'cases': [{'upm': u, 'height': h, 'predictions': predictions(u, h)} for u in UPMS for h in HEIGHTS],
            'phase': 'FROZEN_BEFORE_NATIVE_OBSERVATION', 'source_is_Apple': False}
    (output / 'plan.json').write_text(json.dumps(plan, indent=2))
    observations = []
    for upm in UPMS:
        source = output / f'self-authored-{upm}.ttc'
        tables = build_fixture(original, source, upm)
        before = digest(source)
        orders = []
        for label, heights in (('forward', HEIGHTS), ('reverse', tuple(reversed(HEIGHTS)))):
            oracle = NativeOracle(binary, source, output / f'{upm}-{label}.stderr.log')
            try:
                face = oracle.metadata['faces'][0]
                if (len(oracle.metadata['faces']) != 1 or face['upm'] != upm or face['glyph_count'] != 3
                        or face['verified_table_sha256'] != tables):
                    raise ValueError('metric_fixture_identity_mismatch')
                rows = {height: oracle.samples(0, [2], {'WDTH':500., 'wght':100., 'HGHT':height})[2]
                        for height in heights}
                oracle.finish()
                orders.append(rows)
            finally:
                oracle.close()
        validate_replay(*orders)
        if digest(source) != before:
            raise ValueError('metric_fixture_changed')
        (output / f'{upm}-private-rows.json').write_text(json.dumps(orders, indent=2, allow_nan=False))
        for height in HEIGHTS:
            row = orders[0][height]
            wanted = predictions(upm, height)
            actual = row['advance_height']
            observations.append({'upm': upm, 'user_HGHT': height,
                'actual_height': actual, 'continuous_height': wanted['continuous_height'],
                'height_error': actual - wanted['continuous_height'],
                'strict_height_passed': abs(actual-wanted['continuous_height']) <= 1/32,
                'frozen_B1_height_candidate_matches': actual == wanted['frozen_B1_gvar_height'],
                'actual_horizontal_advance': row['advance_width'],
                'horizontal_candidate_matches': {bits: row['advance_width'] == value
                                                for bits, value in wanted['horizontal_candidates'].items()}})
    report = {'status':'SYNTHETIC_UPEM_DIAGNOSIS_COMPLETE_NOT_METRIC_ACCEPTANCE',
              'scope':'self_authored_only_no_Apple_data', 'platform':platform.platform(),
              'script_sha256':digest(Path(__file__)), 'native_binary_sha256':digest(binary),
              'unique_fixture_coordinate_observations':len(observations),
              'actual_native_records':2*len(observations), 'exact_reverse_pairs':len(observations),
              'strict_height_failures':sum(not x['strict_height_passed'] for x in observations),
              'frozen_B1_height_candidate_matches':sum(x['frozen_B1_height_candidate_matches'] for x in observations),
              'observations':observations, 'production_fix_accepted':False,
              'original_font_acceptance':'NOT_RUN','windows11_acceptance':'NOT_RUN'}
    (output / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({k:v for k,v in report.items() if k != 'observations'}), flush=True)
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    run(args.binary,args.output)
