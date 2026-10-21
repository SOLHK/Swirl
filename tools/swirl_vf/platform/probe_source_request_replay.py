#!/usr/bin/env python3
"""Bounded native source-input proof; original glyph payloads stay private.

The original and T(T(x)) coordinates are frozen before native execution. Each
is independently sampled twice by the new source-input backend; opposite
process orders must also agree. The old V2 gate is evaluated on these actual
measurements offline, preserving its failures rather than relabelling them.
"""
import argparse
import copy
from collections import Counter
import json
from pathlib import Path
import platform
import sys

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import rebuild
import source_request_oracle as source_oracle
import verified_axis_oracle as legacy
from d2_axis_readback import requests_for

ORIGINAL = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'


def fixed_plan(identities):
    if len(identities) != 32 or any(row['glyph_count'] < 19178 for row in identities):
        raise ValueError('this fixed proof requires the separate 32-face source profile')
    positions = [
        ('default', 0, None),
        ('decimal_echo', 0, {'WDTH': 1+999*.123456789, 'wght': 501., 'HGHT': 500.}),
        ('A3_weight', 0, {'WDTH': 500., 'wght': 415.09865, 'HGHT': 500.}),
        ('A3_mixed', 30, {'WDTH': 729.2925740388073, 'wght': 660.9898707384746, 'HGHT': 303.5934274824121}),
        ('A3_drift', 22, {'WDTH': 208.47406722792215, 'wght': 300.3333369872149, 'HGHT': 1.1280770592536593}),
        ('collision_low', 15, {'WDTH': 500., 'wght': 499.006199, 'HGHT': 500.}),
        ('collision_high', 15, {'WDTH': 500., 'wght': 499.006201, 'HGHT': 500.}),
    ]
    plan = []
    for label, face, location in positions:
        if location is None:
            location = {axis['tag']: axis['default'] for axis in identities[face]['axes']}
        canonical = {tag: value['canonical'] for tag, value in legacy.declare_readback(location).items()}
        for variant, point in (('original', location), ('canonical_control', canonical)):
            request = {'request_id': label+'/'+variant, 'face_index': face,
                       'location': point, 'glyph_ids': [5, 19177]}
            legacy.validate_request(request, identities)
            plan.append(request)
    # Reuse the original D2 cohort verbatim, now testing glyph payload replay
    # rather than axis getters alone. Do not double it into more T2 controls.
    for row in requests_for(identities):
        if row['phase'] == 'original':
            request = {key: copy.deepcopy(row[key]) for key in ('request_id', 'face_index', 'location')}
            request['request_id'] = 'D2/'+request['request_id']
            request['glyph_ids'] = [5, 19177]
            legacy.validate_request(request, identities)
            plan.append(request)
    return plan


def raw_record(record):
    return {key: value for key, value in record.items() if key != 'source_request_verification'}


def native_payload(record):
    return {key: value for key, value in raw_record(record).items()
            if key not in legacy.ENVELOPE} | {'reported_location': record['reported_location']}


def run(source, binary, output, expected, kind):
    source = source.resolve(strict=True)
    digest = legacy.source_hash(source)
    if digest != expected or (kind == 'original' and digest != ORIGINAL):
        raise ValueError('exact requested source identity required')
    output.mkdir(parents=True, exist_ok=False)
    with TTCollection(source, lazy=True) as collection:
        identities = legacy.source_identities(collection.fonts)
    plan = fixed_plan(identities)
    (output/'private-plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    launcher = source_oracle.make_launcher(output/'source-oracle', binary.resolve(strict=True))
    runs, summaries, metadata = [], [], []
    for order, requests in (('forward', plan), ('reverse', list(reversed(plan)))):
        oracle = rebuild.NativeOracle(launcher, source, output/(order+'.stderr.log'))
        rows = {}
        try:
            metadata.append(oracle.metadata)
            for request in requests:
                rows[request['request_id']] = oracle.samples(request['face_index'], request['glyph_ids'], request['location'])
            summaries.append(oracle.finish())
        finally:
            oracle.close()
        runs.append(rows)
    pairs = 0
    for request in plan:
        for gid in request['glyph_ids']:
            assert source_oracle.exact_json(native_payload(runs[0][request['request_id']][gid]),
                                           native_payload(runs[1][request['request_id']][gid]))
            pairs += 1
    old_counts, old_rows = Counter(), []
    for request in plan[:14:2]:
        base = request['request_id'].split('/')[0]
        def exchange(internal):
            variant = 'original' if internal['request_id'].endswith('-original') else 'canonical_control'
            for gid in internal['glyph_ids']:
                row = copy.deepcopy(raw_record(runs[0][base+'/'+variant][gid]))
                row['request_id'] = internal['request_id']
                yield row
        try:
            legacy.verify_batch(request, identities, digest, exchange, 1)
            result = 'STRICT_V2_PASS'
        except legacy.VerificationError as error:
            result = str(error)
        old_counts[result] += 1
        old_rows.append({'case': base, 'legacy_V2_offline_result': result})
    # Raw native data remains local; only the fixed aggregate below is exported.
    (output/'private-native.json').write_text(json.dumps({'runs': runs, 'summaries': summaries,
        'metadata': metadata, 'old_diagnostic': old_rows}, allow_nan=False)+'\n')
    original_axis_failures = 0
    originals = [request for request in plan if not request['request_id'].endswith('/canonical_control')]
    for request in originals:
        proof = runs[0][request['request_id']][5]['source_request_verification']
        original_axis_failures += proof['readback_diagnostic']['strict_axis_failure_count']
    d2_rows = [runs[0][request['request_id']][5]['source_request_verification']['readback_diagnostic']
               for request in plan if request['request_id'].startswith('D2/')]
    d2_failed = sum(row['strict_axis_failure_count'] > 0 for row in d2_rows)
    assert len(d2_rows) == 384
    unique_originals = {(request['face_index'], tuple((tag, source_oracle.binary64_bits(value))
                        for tag, value in sorted(request['location'].items()))) for request in originals}
    collision = []
    for gid in (5, 19177):
        low, high = (runs[0][label+'/original'][gid] for label in ('collision_low', 'collision_high'))
        collision.append({'gid': gid, 'raw_payload_differs': not source_oracle.exact_json(native_payload(low), native_payload(high)),
                          'absolute_advance_difference': abs(low['advance_width']-high['advance_width'])})
    assert legacy.source_hash(source) == digest
    summary = {'status': 'PASS_FINITE_ORIGINAL_REQUEST_REPLAY_NOT_MAPPING_ACCEPTANCE',
        'source_kind': kind, 'source_sha256': digest, 'host': platform.platform(),
        'native_os_version': metadata[0].get('os_version'),
        'physical_faces_verified': len(identities), 'labelled_original_requests': len(originals),
        'unique_original_positions': len(unique_originals),
        'predeclared_canonical_controls': 7, 'gids_per_position': 2,
        'processes': 2, 'source_verified_batches': sum(row['request_count'] for row in summaries),
        'internal_native_requests': sum(row['internal_native_request_count'] for row in summaries),
        'internal_native_glyph_records': sum(row['internal_native_glyph_count'] for row in summaries),
        'exact_opposite_order_payload_pairs': pairs,
        'original_strict_axis_failures_retained': original_axis_failures,
        'D2_cohort': {'source_request_cases': 384, 'all_cases_exact_source_replay': True,
                      'strict_request_passed': 384-d2_failed, 'strict_request_failed': d2_failed,
                      'mapping_accepted': False},
        'legacy_V2_offline_counts': dict(old_counts), 'input_collision_observations': collision,
        'source_unchanged': True, 'source_user_mapping_accepted': False,
        'strict_axis_echo_accepted': False, 'original_font_generated': False,
        'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN'}
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--source-kind', required=True, choices=('original', 'installed_system_control'))
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.binary, args.output, args.expected_sha256, args.source_kind)))
