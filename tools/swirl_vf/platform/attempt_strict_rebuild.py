#!/usr/bin/env python3
"""Execute the strict builder on an identified source; return safe aggregates.

The caller owns a new private directory. No font, native outline, full report
or compiler log is a public artifact. Timeout and failure never grant acceptance.
"""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import build_swirlvf
from rebuild import native_failure_details, metric_failure_details, sha256
from verified_axis_oracle import make_launcher

REASONS = (
    'native horizontal coordinate of vertical origin is not representable by standard vmtx',
    'native outline command topology differs between instances',
    'training/default quantization exceeds error budget', 'holdout error persists',
    'native oracle could not verify every requested physical face',
    'native_readback_replay_not_exactly_stable', 'native_readback_not_named_decimal4_candidate',
    'native_replay_payload_not_exact', 'native_nondefault_axis_not_reported',
    'predeclared_axis_candidate_outside_source_range', 'native_final_summary_mismatch',
    'source_changed_during_axis_verification', 'native final summary is incomplete',
    'native oracle failed after its final glyph',
)


def numbers(record, keys):
    return {key: record[key] for key in keys
            if type(record.get(key)) in (int, float) and math.isfinite(record[key])}


def public_report(raw):
    """Never copy arbitrary strings, file paths, metadata or native payloads."""
    result = {'status': raw['status'] if raw.get('status') in (
        'BLOCKED', 'RECONSTRUCTION_SAMPLED_PASS_PLATFORM_UNVERIFIED') else 'FAILED',
        'output_generated': raw.get('output_generated') is True,
        'native_faces_verified': len(raw.get('oracle', {}).get('faces', [])),
        'face_progress': [numbers(face, ('face_index', 'glyph_count', 'glyphs_completed',
                            'max_outline_error', 'max_metric_error')) for face in raw.get('faces', [])],
        'native_observation_progress': numbers(raw.get('native_observation_progress', {}),
            ('attempted_batches_this_run', 'completed_batches_this_run',
             'glyph_observations_in_completed_batches_this_run')),
        'failures': []}
    result.update(numbers(raw, ('outline_limit_font_units', 'metric_limit_font_units',
                               'cubic_approximation_limit_font_units')))
    for failure in raw.get('failures', []):
        context = failure.get('context', {})
        safe = numbers(context, ('face_index', 'glyph_id', 'gid_first', 'gid_last',
                                 'sample_number', 'adaptive_points', 'max_outline_error', 'max_metric_error'))
        if context.get('stage') in ('native_metadata', 'face_preflight', 'native_batch',
            'glyph_reconstruction', 'native_adaptive', 'native_adaptive_holdout',
            'face_tables', 'native_finalization', 'collection_verification'):
            safe['stage'] = context['stage']
        safe['user_location'] = numbers(context.get('user_location', {}), ('WDTH', 'wght', 'HGHT'))
        if 'native_observation' in context:
            safe['native_observation'] = native_failure_details(context['native_observation'])
        if 'metric_representation' in context:
            safe['metric_representation'] = metric_failure_details(context['metric_representation'])
        result['failures'].append({'reason': next((reason for reason in REASONS
            if reason in failure.get('message', '')), 'OTHER_PRIVATE_FAILURE'), 'context': safe})
    return result


def run(source, private, expected_sha256):
    if sha256(source) != expected_sha256:
        raise ValueError('exact source identity is required before reconstruction')
    private.mkdir(mode=0o700)
    binary, report, candidate = private/'extractor', private/'rebuild.json', private/'SwirlVF.ttc'
    summary = {'status': 'NOT_RUN', 'source_sha256': expected_sha256,
        'outline_limit_font_units': build_swirlvf.PRECISION,
        'metric_limit_font_units': build_swirlvf.PRECISION,
        'cubic_approximation_limit_font_units': build_swirlvf.CUBIC_APPROXIMATION,
        'output_generated': False, 'production_accepted': False, 'windows11_acceptance': 'NOT_RUN'}
    with (private/'compiler.log').open('wb') as log:
        compiled = subprocess.run(['xcrun', 'swiftc', '-O',
            str(Path(__file__).with_name('coretext_extract.swift')), '-o', str(binary)],
            stdout=log, stderr=log, timeout=180)
    summary['compiler_exit_code'] = compiled.returncode
    if compiled.returncode:
        summary['status'] = 'COMPILE_FAILED'
        return summary
    oracle = make_launcher(private/'verified-axis-oracle', binary)
    command = [sys.executable, str(TOOLS/'build_swirlvf.py'), str(source),
        '--expected-source-sha256', expected_sha256, '--oracle', str(oracle),
        '--output', str(candidate), '--report', str(report), '--batch-size', '64',
        '--checkpoint-dir', str(private/'verified-faces')]
    summary.update(native_binary_sha256=sha256(binary), verified_axis_launcher_sha256=sha256(oracle),
        builder_sha256=sha256(TOOLS/'build_swirlvf.py'), engine_sha256=sha256(TOOLS/'rebuild.py'),
        axis_acceptance='every_requested_GID_exact_native_replay_before_batch_release',
        original_strict_readback_tolerance=1e-6)
    with (private/'stdout.log').open('wb') as stdout, (private/'stderr.log').open('wb') as stderr:
        with subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True) as process:
            try:
                summary['process_exit_code'] = process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                summary['status'] = 'TIME_LIMIT_NOT_ACCEPTED'
    if report.is_file():
        summary.update(public_report(json.loads(report.read_text())))
    if candidate.is_file():
        summary.update(output_sha256=sha256(candidate), output_bytes=candidate.stat().st_size)
    summary['source_unchanged'] = sha256(source) == expected_sha256
    return summary
