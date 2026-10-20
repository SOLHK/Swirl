#!/usr/bin/env python3
"""Verify native axis observations before exposing converter input.

The upstream CoreText process explicitly observes axis readbacks without granting
acceptance. This adapter binds every source table, validates complete requests,
and checks one independently constructed readback instance for every request.
The named positive-decimal candidate only explains a reported number; acceptance
also requires every requested GID's original native payload to match exactly.

No glyph, metric, requested coordinate or reported coordinate is corrected.
There is no avar/HVGL inference, tolerance increase, recursive canonicalization,
or claim of continuous-space equivalence. Entire batches stay private until all
their GIDs pass. Native stderr and outline payloads are never printed to logs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

import fontTools
from fontTools.ttLib import TTCollection

from incremental_pipe import TimedLineReader


BACKEND = 'CoreTextExactAxisReadbackBatchV1'
CANDIDATE = 'positive_binary64_product_truncate_decimal4_v1'
MAX_REQUEST_BYTES = 1_048_576
MAX_BATCH_BYTES = 128 * 1024 * 1024
SCALARS = ('advance_width', 'advance_height', 'lsb', 'horizontal_origin_x',
           'horizontal_origin_y', 'vertical_origin_x', 'vertical_origin_y',
           'horizontal_advance_sum', 'vertical_advance_sum')
VECTORS = {'bounds': 4, 'horizontal_advance_vector': 2,
           'vertical_advance_vector': 2, 'vertical_origin_translation': 2}
STRINGS = ('lsb_derivation', 'vertical_origin_derivation', 'path_status')
ENVELOPE = frozenset(('request_id', 'face_index', 'glyph_id', 'location', 'reported_location'))
COMMAND_SIZES = {'moveTo': 2, 'lineTo': 2, 'qCurveTo': 4, 'curveTo': 6, 'closePath': 0}


class VerificationError(ValueError):
    def __init__(self, reason, **context):
        super().__init__(reason)
        self.context = context


def require(value, reason, **context):
    if not value:
        raise VerificationError(reason, **context)


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def source_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def runtime_identity():
    return {'python': sys.version, 'implementation': platform.python_implementation(),
            'fonttools': fontTools.__version__}


def launcher_binding(native_binary):
    directory = Path(__file__).resolve().parent
    files = [Path(__file__).resolve(), directory / 'incremental_pipe.py', Path(native_binary).resolve()]
    return {'backend': BACKEND, 'files': {str(path): source_hash(path) for path in files},
            'runtime': runtime_identity()}


def make_launcher(path, native_binary):
    """Create a new executable whose own hash binds native, adapter and runtime.

    NativeOracle invokes launchers as ``launcher SOURCE``. Changing a dependency
    after this checkpoint recipe was created fails before observations are read.
    The caller must generate a new launcher to use newly reviewed dependencies.
    """
    path, native_binary = Path(path).resolve(), Path(native_binary).resolve()
    binding = launcher_binding(native_binary)
    require(not path.exists() and str(path) not in binding['files'], 'new_launcher_path_required')
    require(native_binary.is_file() and os.access(native_binary, os.X_OK), 'native_binary_not_executable')
    require('\n' not in sys.executable and ' ' not in sys.executable, 'unsupported_launcher_interpreter_path')
    code = (f'#!{sys.executable}\n' +
            '"""Generated exact-axis adapter launcher; source/font bytes are not embedded."""\n'
            'import hashlib, json, platform, sys\n'
            'from pathlib import Path\n'
            'import fontTools\n' +
            f'BINDING = {binding!r}\n' +
            'def fail(reason):\n'
            '    print(json.dumps({"type":"fatal_error","error":reason}), flush=True)\n'
            '    raise SystemExit(2)\n'
            'try:\n'
            '    for name, expected in BINDING["files"].items():\n'
            '        value = hashlib.sha256()\n'
            '        with Path(name).open("rb") as stream:\n'
            '            for block in iter(lambda: stream.read(1048576), b""):\n'
            '                value.update(block)\n'
            '        if value.hexdigest() != expected: fail("axis_launcher_dependency_changed")\n'
            '    runtime = {"python":sys.version,"implementation":platform.python_implementation(),\n'
            '               "fonttools":fontTools.__version__}\n'
            '    if runtime != BINDING["runtime"]: fail("axis_launcher_runtime_changed")\n'
            '    if len(sys.argv) != 2: fail("axis_launcher_requires_only_source_path")\n' +
            f'    sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n' +
            '    from verified_axis_oracle import serve\n' +
            f'    raise SystemExit(serve(sys.argv[1], {str(native_binary)!r}))\n' +
            'except Exception:\n'
            '    fail("axis_launcher_dependency_or_startup_failed")\n')
    with path.open('x', encoding='utf-8') as stream:
        stream.write(code)
    path.chmod(0o700)
    return path


def source_identities(fonts):
    """Bind raw TTC faces, including every original table; hash shared bytes once."""
    identities, hashes = [], {}
    for index, font in enumerate(fonts):
        axes = []
        for axis in font['fvar'].axes if 'fvar' in font else ():
            tag = axis.axisTag
            require(isinstance(tag, str) and len(tag) == 4 and tag.isascii()
                    and all(finite_number(v) for v in (axis.minValue, axis.defaultValue, axis.maxValue))
                    and axis.minValue <= axis.defaultValue <= axis.maxValue,
                    'invalid_source_axis', face_index=index)
            axes.append({'tag': tag, 'identifier': int.from_bytes(tag.encode('ascii'), 'big'),
                         'minimum': axis.minValue, 'default': axis.defaultValue, 'maximum': axis.maxValue,
                         'flags': axis.flags, 'hidden': bool(axis.flags & 1)})
        require(len({a['tag'] for a in axes}) == len(axes), 'duplicate_source_axis', face_index=index)
        tables = {}
        for tag, entry in font.reader.tables.items():
            key = (entry.offset, entry.length)
            if key not in hashes:
                hashes[key] = hashlib.sha256(font.reader[tag]).hexdigest()
            tables[tag] = hashes[key]
        identities.append({'face_index': index, 'upm': font['head'].unitsPerEm,
                           'glyph_count': font['maxp'].numGlyphs, 'axes': axes,
                           'verified_table_sha256': tables})
    require(bool(identities), 'source_has_no_physical_faces')
    return identities


def same_json(left, right):
    """Exact finite numeric equality; booleans cannot masquerade as numbers."""
    if finite_number(left) or finite_number(right):
        return finite_number(left) and finite_number(right) and left == right
    if type(left) is not type(right):
        return False
    if type(left) is list:
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    if type(left) is dict:
        return left.keys() == right.keys() and all(same_json(left[k], right[k]) for k in left)
    if left is None or type(left) in (str, bool):
        return left == right
    return False


def verified_metadata(native, digest, byte_size, identities):
    require(type(native) is dict and native.get('type') == 'metadata'
            and native.get('backend') == 'CoreText' and native.get('source_sha256') == digest
            and native.get('source_byte_size') == byte_size, 'native_source_metadata_mismatch')
    require(native.get('axis_observations_only') is True
            and not native.get('diagnostic_readback_observation_only')
            and 'axis_verification_backend' not in native
            and 'upstream_axis_observations_only' not in native,
            'explicit_unverified_axis_observation_metadata_required')
    require(native.get('metric_backend', 'CoreText') == 'CoreText', 'raw_native_metric_backend_required')
    faces = native.get('faces')
    require(type(faces) is list and len(faces) == len(identities), 'native_physical_face_count_mismatch')
    for expected, actual in zip(identities, faces):
        require(type(actual) is dict and actual.get('status') == 'identity_verified'
                and all(same_json(actual.get(key), value) for key, value in expected.items()),
                'native_face_or_original_table_identity_mismatch', face_index=expected['face_index'])
    result = copy.deepcopy(native)
    result.update(upstream_axis_observations_only=True, axis_observations_only=False,
                  axis_verification_backend=BACKEND,
                  axis_verification_policy={'readback_candidate': CANDIDATE,
                      'batch_release': 'all_requested_GIDs_require_exact_native_payload_replay',
                      'numeric_equality': 'finite_binary64_values_no_tolerance_signed_zeros_equal',
                      'source_user_mapping_inferred': False, 'raw_metrics_modified': False,
                      'continuous_space_acceptance': False})
    return result


def validate_request(request, identities):
    require(type(request) is dict and set(request) == {'request_id', 'face_index', 'location', 'glyph_ids'},
            'invalid_request_fields')
    identifier = request['request_id']
    require(type(identifier) is str and bool(identifier) and len(identifier.encode('utf-8')) <= 1024,
            'invalid_request_id')
    face = request['face_index']
    require(type(face) is int and 0 <= face < len(identities), 'request_face_out_of_range')
    identity = identities[face]
    location = request['location']
    require(type(location) is dict and set(location) == {a['tag'] for a in identity['axes']},
            'all_source_axes_must_be_explicit')
    for axis in identity['axes']:
        value = location[axis['tag']]
        require(finite_number(value) and axis['minimum'] <= value <= axis['maximum'],
                'request_axis_nonfinite_or_out_of_range', axis=axis['tag'])
    gids = request['glyph_ids']
    require(type(gids) is list and 0 < len(gids) <= 4096
            and all(type(gid) is int and 0 <= gid < identity['glyph_count'] for gid in gids)
            and len(set(gids)) == len(gids), 'invalid_or_duplicate_request_GIDs')
    return identity


def effective_readback(record, identity, requested, *, replay=False):
    reported = record.get('reported_location')
    axes = identity['axes']
    require(type(reported) is dict and set(reported) <= {a['tag'] for a in axes},
            'native_reported_axis_set_invalid')
    result = {}
    for axis in axes:
        tag = axis['tag']; expected = requested[tag]
        # Preserve the actual binary64 observations on a failure. A decimal
        # label alone cannot distinguish division from reciprocal multiplication
        # or diagnose a second application's one-ULP / one-decimal-step drift.
        # These are axis coordinates only, never native outline/metric payloads.
        context = {'axis': tag, 'phase': 'replay' if replay else 'original',
                   'requested_value': expected, 'requested_value_hex': float(expected).hex(),
                   'reported_axis_present': tag in reported}
        require(expected == axis['default'] or tag in reported,
                'native_nondefault_axis_not_reported', **context)
        value = reported.get(tag, axis['default'])
        if finite_number(value):
            context.update(reported_value=value, reported_value_hex=float(value).hex())
        require(finite_number(value) and axis['minimum'] <= value <= axis['maximum'],
                'native_axis_readback_nonfinite_or_out_of_range', **context)
        if replay:
            # Do not run the decimal candidate again: multiplication/truncation
            # is not idempotent for some binary64 encodings of four decimals.
            require(value == expected, 'native_readback_replay_not_exactly_stable', **context)
        elif value != expected:
            require(expected > 0 and value > 0 and math.isfinite(expected * 10000),
                    'positive_decimal4_candidate_unavailable', **context)
            candidate = math.trunc(expected * 10000) / 10000
            context.update(expected_candidate_value=candidate,
                           expected_candidate_value_hex=float(candidate).hex())
            require(value == candidate, 'native_readback_not_named_decimal4_candidate', **context)
        result[tag] = value
    return result


def validate_native_record(record, request, seen):
    require(type(record) is dict and record.get('request_id') == request['request_id']
            and type(record.get('face_index')) is int and record['face_index'] == request['face_index'],
            'native_response_request_identity_mismatch')
    if record.get('error') is not None:
        raise VerificationError('upstream_native_request_failed',
                                native_error=str(record['error'])[:1000],
                                **({'glyph_id': record['glyph_id']} if type(record.get('glyph_id')) is int else {}))
    require(record.get('type') != 'request_error' and 'error' in record,
            'invalid_native_success_record')
    gid = record.get('glyph_id')
    require(type(gid) is int and gid in request['glyph_ids'] and gid not in seen,
            'native_missing_duplicate_or_unrequested_GID')
    require(same_json(record.get('location'), request['location']), 'native_requested_location_mismatch', glyph_id=gid)
    require('axis_verification' not in record and 'raw_coretext_metrics' not in record
            and record.get('metric_backend', 'CoreText') == 'CoreText',
            'native_record_was_already_adapted', glyph_id=gid)
    for field in SCALARS:
        require(finite_number(record.get(field)), 'native_scalar_missing_or_nonfinite', glyph_id=gid, field=field)
    for field, size in VECTORS.items():
        values = record.get(field)
        require(type(values) is list and len(values) == size and all(finite_number(v) for v in values),
                'native_vector_missing_or_nonfinite', glyph_id=gid, field=field)
    for field in STRINGS:
        require(type(record.get(field)) is str and bool(record[field]),
                'native_provenance_or_path_status_missing', glyph_id=gid, field=field)
    require(record['path_status'] in ('path', 'empty_path', 'nil_path_but_source_proves_empty'),
            'unknown_native_path_status', glyph_id=gid)
    commands = record.get('commands')
    require(type(commands) is list and len(commands) <= 1_000_000,
            'native_command_list_invalid', glyph_id=gid)
    for command in commands:
        require(type(command) is list and bool(command) and type(command[0]) is str
                and command[0] in COMMAND_SIZES and len(command) == COMMAND_SIZES[command[0]] + 1
                and all(finite_number(v) for v in command[1:]),
                'native_command_type_arity_or_number_invalid', glyph_id=gid)
    seen.add(gid)
    return gid


def verify_batch(request, identities, digest, exchange, sequence):
    """Return only a complete verified batch; exchange supplies native records."""
    identity = validate_request(request, identities)
    original_request = {**request, 'request_id': f'axis-{sequence}-original'}
    original, seen, reported = {}, set(), None
    for record in exchange(original_request):
        gid = validate_native_record(record, original_request, seen)
        try:
            effective = effective_readback(record, identity, request['location'])
        except VerificationError as error:
            error.context.setdefault('glyph_id', gid)
            tag = error.context.get('axis')
            if tag in request['location']:
                value = request['location'][tag]
                error.context.update(source_requested_value=value,
                                     source_requested_value_hex=float(value).hex())
            raise
        if reported is None:
            reported = (copy.deepcopy(record['reported_location']), effective)
        require(same_json(record['reported_location'], reported[0]), 'native_inconsistent_batch_readback', glyph_id=gid)
        original[gid] = record
    require(seen == set(request['glyph_ids']), 'native_original_batch_incomplete')
    replay_request = {**request, 'request_id': f'axis-{sequence}-reported', 'location': reported[1]}
    seen, replay_reported = set(), None
    for record in exchange(replay_request):
        gid = validate_native_record(record, replay_request, seen)
        try:
            effective_readback(record, identity, replay_request['location'], replay=True)
        except VerificationError as error:
            error.context.setdefault('glyph_id', gid)
            tag = error.context.get('axis')
            if tag in request['location']:
                value = request['location'][tag]
                error.context.update(source_requested_value=value,
                                     source_requested_value_hex=float(value).hex())
            raise
        if replay_reported is None:
            replay_reported = copy.deepcopy(record['reported_location'])
        require(same_json(record['reported_location'], replay_reported), 'native_inconsistent_replay_readback', glyph_id=gid)
        left = {k: v for k, v in original[gid].items() if k not in ENVELOPE}
        right = {k: v for k, v in record.items() if k not in ENVELOPE}
        require(left.keys() == right.keys(), 'native_replay_payload_fields_changed', glyph_id=gid)
        for field in left:
            require(same_json(left[field], right[field]), 'native_replay_payload_not_exact', glyph_id=gid, field=field)
    require(seen == set(request['glyph_ids']), 'native_replay_batch_incomplete')
    evidence = {'backend': BACKEND, 'candidate': CANDIDATE, 'source_sha256': digest,
                'effective_reported_location': reported[1], 'replay_reported_location': replay_reported,
                'changed_axes': [a['tag'] for a in identity['axes']
                                 if request['location'][a['tag']] != reported[1][a['tag']]],
                'verified_GIDs_in_batch': len(seen), 'native_replay_count': 1,
                'exact_native_payload_equality': True, 'native_values_modified': False,
                'upstream_original_request_id': original_request['request_id'],
                'upstream_replay_request_id': replay_request['request_id']}
    return [{**original[gid], 'request_id': request['request_id'], 'axis_verification': copy.deepcopy(evidence)}
            for gid in request['glyph_ids']]


def decode(line):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'duplicate_JSON_object_key')
            result[key] = value
        return result
    def constant(_):
        raise VerificationError('nonfinite_JSON_number')
    return json.loads(line, object_pairs_hook=pairs, parse_constant=constant)


def serve(source, native_binary, input_stream=sys.stdin, output_stream=sys.stdout,
          *, response_timeout=120., maximum_batch_bytes=MAX_BATCH_BYTES):
    source, native_binary = Path(source).resolve(), Path(native_binary).resolve()
    process = reader = request = None
    external_requests = verified_glyphs = internal_requests = internal_glyphs = 0

    def emit(record):
        output_stream.write(json.dumps(record, allow_nan=False, separators=(',', ':')) + '\n')
        output_stream.flush()

    try:
        require(finite_number(response_timeout) and response_timeout > 0
                and type(maximum_batch_bytes) is int and maximum_batch_bytes > 0, 'invalid_transport_limits')
        digest = source_hash(source); byte_size = source.stat().st_size
        with TTCollection(source, lazy=True) as collection:
            identities = source_identities(collection.fonts)
            process = subprocess.Popen([str(native_binary), str(source), '--axis-observations'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       text=True, encoding='utf-8', bufsize=1)
            reader = TimedLineReader(process.stdout.fileno())

            def read():
                line = reader.readline(timeout=response_timeout)
                require(bool(line), 'native_process_ended_before_complete_response')
                return decode(line), len(line.encode('utf-8'))

            metadata = verified_metadata(read()[0], digest, byte_size, identities)
            metadata['axis_verification_dependency_binding'] = launcher_binding(native_binary)
            emit(metadata)

            def exchange(native_request):
                nonlocal internal_requests, internal_glyphs
                process.stdin.write(json.dumps(native_request, allow_nan=False, separators=(',', ':')) + '\n')
                process.stdin.flush()
                internal_requests += 1
                total = 0
                for _ in native_request['glyph_ids']:
                    record, size = read(); total += size
                    require(total <= maximum_batch_bytes, 'native_batch_response_resource_limit')
                    if type(record) is dict and record.get('error') is None and 'glyph_id' in record:
                        internal_glyphs += 1
                    yield record

            while True:
                request = None
                line = input_stream.readline(MAX_REQUEST_BYTES + 2)
                if not line:
                    break
                require(len(line.encode('utf-8')) <= MAX_REQUEST_BYTES, 'request_line_resource_limit')
                if not line.strip():
                    continue
                request = decode(line)
                batch = verify_batch(request, identities, digest, exchange, external_requests + 1)
                for record in batch:
                    emit(record)
                verified_glyphs += len(batch); external_requests += 1
            process.stdin.close()
            summary = read()[0]
            require(type(summary) is dict and summary.get('type') == 'summary'
                    and summary.get('error_count') == 0 and summary.get('source_sha256') == digest
                    and all(type(summary.get(field)) is int for field in
                            ('error_count', 'request_count', 'successful_glyph_count'))
                    and summary.get('request_count') == internal_requests
                    and summary.get('successful_glyph_count') == internal_glyphs,
                    'native_final_summary_mismatch')
            require(not reader.readline(timeout=response_timeout), 'native_unexpected_output_after_summary')
            require(process.wait(timeout=10) == 0, 'native_process_exit_failed')
            require(source_hash(source) == digest, 'source_changed_during_axis_verification')
            emit({**summary, 'request_count': external_requests, 'successful_glyph_count': verified_glyphs,
                  'axis_verification_backend': BACKEND, 'verified_batch_count': external_requests,
                  'internal_native_request_count': internal_requests, 'internal_native_glyph_count': internal_glyphs,
                  'upstream_native_summary': summary, 'source_unchanged': True})
        return 0
    except Exception as error:
        context = error.context if isinstance(error, VerificationError) else {}
        if isinstance(error, VerificationError):
            reason = str(error)
        elif isinstance(error, TimeoutError):
            reason = 'native_response_deadline_exceeded'
        elif isinstance(error, json.JSONDecodeError):
            reason = 'invalid_request_or_native_JSON'
        else:
            reason = 'axis_verification_transport_or_source_failed'
        response = {'type': 'request_error' if type(request) is dict else 'fatal_error',
                    'error': reason,
                    'error_type': type(error).__name__, 'axis_verification_backend': BACKEND, **context}
        if type(request) is dict:
            for field, kind in (('request_id', str), ('face_index', int)):
                if type(request.get(field)) is kind:
                    response[field] = request[field]
            gids = request.get('glyph_ids')
            if type(gids) is list and gids and all(type(gid) is int for gid in gids):
                response.update(requested_GID_count=len(gids), requested_first_GID=gids[0], requested_last_GID=gids[-1])
        emit(response)
        return 3 if type(request) is dict else 2
    finally:
        if reader is not None:
            reader.close()
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--native', required=True, type=Path)
    args = parser.parse_args()
    return serve(args.source, args.native)


if __name__ == '__main__':
    raise SystemExit(main())
