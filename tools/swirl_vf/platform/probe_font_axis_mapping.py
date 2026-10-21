#!/usr/bin/env python3
"""Finite original source-q falsification; safe aggregates only are public.

Nothing in this diagnostic authorizes the production builder. It checks the
frozen source hypothesis against actual CoreText/HVF, independently of target
transport, legal avar knot certificates, strict readback, or glyph conversion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import random
import subprocess
import sys

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from target_axis_mapping import source_plan, axes_from_font
from font_axis_mapping import compile_axis
from source_request_oracle import make_launcher, exact_json
from rebuild import NativeOracle
from probe_axis_anchor import (source_identities, hvf_events, raw_native_paths,
    raw_coretext_paths, control_stats, add_control, same_private_payload)
from probe_axis_a3_hvar import metric_residuals
from source_metrics import SourceMetrics
from d2_axis_readback import requests_for

EXPECTED = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'
TAGS = ('WDTH', 'wght', 'HGHT')
GIDS = (5, 12, 56, 169, 19177)
LIMIT = 1 / 32


def require(value, code):
    if not value:
        raise ValueError(code)


def cases_for(fonts, identities):
    rows = [{'face': row['face_index'], 'group': 'D2_strict_fraction', 'label': row['request_id'],
             'location': row['location']} for row in requests_for(identities)
            if row['phase'] == 'original' and row['fraction_index'] == 1]
    rng = random.Random(0x5034464F4E544D4150)
    for face, font in enumerate(fonts):
        axes = font['fvar'].axes
        rows.append({'face': face, 'group': 'fresh_seeded_triple', 'label': f'fresh-{face}',
                     'location': {str(a.axisTag): rng.uniform(a.minValue, a.maxValue) for a in axes}})
        rows.append({'face': face, 'group': 'endpoint_control', 'label': f'endpoint-{face}',
                     'location': {str(a.axisTag): (a.minValue if a.axisTag == 'WDTH' else a.maxValue)
                                  for a in axes}})
    for face, coordinates in [(0, (500., 415.09865, 500.)),
            (30, (729.2925740388073, 660.9898707384746, 303.5934274824121)),
            (22, (208.47406722792215, 300.3333369872149, 1.1280770592536593)),
            (15, (500., 499.006199, 500.)), (15, (500., 499.006201, 500.))]:
        rows.append({'face': face, 'group': 'historical_control', 'label': f'history-{len(rows)}',
                     'location': dict(zip(TAGS, coordinates))})
    require(len(rows) == 165, 'frozen_cohort_size_changed')
    return rows


def run(source, output, native, hvf):
    require(not output.exists(), 'fresh_private_output_required')
    require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, 'exact_original_required')
    output.mkdir(parents=True, mode=0o700)
    summary = {'status': 'NOT_RUN', 'source_sha256': EXPECTED, 'host': platform.platform(),
        'source_user_mapping_accepted': False, 'target_mapping_accepted': False,
        'font_only_equivalence_accepted': False, 'original_font_generated': False,
        'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN', 'limits_unchanged': True}
    code = 2
    try:
        with TTCollection(source, lazy=True) as collection:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(f['maxp'].numGlyphs == 47102 for f in fonts),
                    'all_original_faces_required')
            identities = source_identities(fonts)
            cases = cases_for(fonts, identities)
            plans = [source_plan(fonts[row['face']], row['location']) for row in cases]
            # Freeze all arithmetic before any new native observation.
            (output / 'private-plans.json').write_text(json.dumps(plans, allow_nan=False))
            legal, blocked = 0, {}
            for font in fonts:
                for axis in axes_from_font(font):
                    try:
                        compile_axis(axis)
                        legal += 1
                    except ValueError as error:
                        key = axis.tag + ':' + str(error)
                        blocked[key] = blocked.get(key, 0) + 1
            summary.update(physical_faces=32, source_positions=len(cases),
                fresh_seeded_positions=32, D2_fraction_positions=96, endpoint_controls=32,
                historical_controls=5, direct_q_space_legal_axis_candidates=legal,
                direct_q_space_compiler_refusals=blocked,
                glyph_model_reparameterization='NOT_IMPLEMENTED',
                all_plans_frozen_before_native=True)
            launcher = output / 'source-request-oracle'
            make_launcher(launcher, native)
            observations = {}
            opposite, strict_pass, strict_fail = 0, 0, 0
            for order in ('forward', 'reverse'):
                oracle = NativeOracle(launcher, source, output / f'{order}.private.log')
                try:
                    summary['native_os_version'] = oracle.metadata['os_version']
                    for i in (range(len(cases)) if order == 'forward' else reversed(range(len(cases)))):
                        row = cases[i]
                        records = oracle.samples(row['face'], list(GIDS), row['location'])
                        if order == 'forward':
                            observations[i] = records
                            if row['group'] == 'D2_strict_fraction':
                                diagnostic = records[GIDS[0]]['source_request_verification']['readback_diagnostic']
                                failed = diagnostic['strict_axis_failure_count'] > 0
                                strict_fail += failed
                                strict_pass += not failed
                        else:
                            for gid in GIDS:
                                a = {k: v for k, v in observations[i][gid].items()
                                     if k != 'source_request_verification'}
                                b = {k: v for k, v in records[gid].items()
                                     if k != 'source_request_verification'}
                                require(same_private_payload(a, b)
                                        and exact_json(a['reported_location'], b['reported_location']),
                                        'original_opposite_order_payload_changed')
                                opposite += 1
                    finished = oracle.finish()
                    summary.setdefault('native_sessions', []).append({
                        'requests': finished['request_count'],
                        'verified_glyph_records': finished['successful_glyph_count'],
                        'verified_batches': finished['verified_batch_count'],
                        'internal_native_requests': finished['internal_native_request_count'],
                        'internal_native_glyph_records': finished['internal_native_glyph_count']})
                finally:
                    oracle.close()
            geometry = control_stats()
            metric_max, metric_exact, metric_outside = 0., 0, 0
            for i, row in enumerate(cases):
                design = {tag: plans[i]['source_q'][tag] / 16384 for tag in TAGS}
                residual = metric_residuals(SourceMetrics(fonts[row['face']]), observations[i], design)
                metric_max = max(metric_max, residual['maximum_error'])
                metric_exact += residual['exact']
                metric_outside += not residual['within_1_32']
                for gid in (5, 19177):
                    add_control(geometry, raw_native_paths(hvf_events(hvf, source, row['face'], gid, design)),
                        raw_coretext_paths(observations[i][gid]['commands']), row['face'], gid, row['location'])
            (output / 'geometry-checks.private.json').write_text(json.dumps(geometry, allow_nan=False))
            safe_geometry = {key: ({k: v for k, v in value.items() if k != 'examples'}
                                  if isinstance(value, dict) else value) for key, value in geometry.items()}
            finite_controls = metric_outside == 0 and geometry['preserved_controls']['failures'] == 0
            summary.update(opposite_order_exact_glyph_pairs=opposite,
                D2_strict_fraction_pass=strict_pass, D2_strict_fraction_fail=strict_fail,
                HVAR={'positions': len(cases), 'exact_positions': metric_exact,
                      'outside_1_32': metric_outside, 'maximum_error': metric_max},
                native_HVF_geometry=safe_geometry, native_HVF_calls=2 * len(cases),
                finite_preserved_control_budget_passed=finite_controls,
                source_unchanged=hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED)
            require(summary['source_unchanged'], 'original_source_changed')
            code = 0 if finite_controls else 2
            summary['status'] = 'COMPLETED_FINITE_SOURCE_Q_AND_FONT_REPRESENTATION_TEST_NOT_ACCEPTANCE'
    except Exception as error:
        summary.update(status='FAILED_P4_NATIVE_GATE', failure_type=type(error).__name__)
        # Raw native exceptions/logs remain private; public summaries are fixed.
        (output / 'failure.private.txt').write_text(str(error))
    finally:
        (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    print(json.dumps(summary, allow_nan=False))
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--hvf', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.source, args.output, args.native, args.hvf))
