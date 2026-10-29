#!/usr/bin/env python3
"""Verify native axis observations before exposing converter input.

The upstream CoreText process explicitly observes axis readbacks without granting
acceptance. This adapter binds every source table, validates complete requests,
and checks one independently constructed, predeclared instance per request.
Two finite positive-decimal expressions explain observed API numbers. Neither
selects the native design coordinate. A fixed twice-evaluated candidate is
declared before the first native request, must actually echo exactly, and must
match every requested GID's original native payload exactly.

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


BACKEND = 'CoreTextExactAxisReadbackBatchV2'
CANDIDATE = 'positive_binary64_decimal4_once_or_twice_with_predeclared_stable_replay_v2'
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


def launcher_binding(native_binary, *, source_request_replay=False):
    directory = Path(__file__).resolve().parent
    files = [Path(__file__).resolve(), directory / 'incremental_pipe.py', Path(native_binary).resolve()]
    backend = BACKEND
    if source_request_replay:
        from source_request_oracle import BACKEND as backend
        files.append(directory / 'source_request_oracle.py')
    return {'backend': backend, 'files': {str(path): source_hash(path) for path in files},
            'runtime': runtime_identity()}


def make_launcher(path, native_binary, *, source_request_replay=False):
    """Create a new executable whose own hash binds native, adapter and runtime.

    NativeOracle invokes launchers as ``launcher SOURCE``. Changing a dependency
    after this checkpoint recipe was created fails before observations are read.
    The caller must generate a new launcher to use newly reviewed dependencies.
    """
    path, native_binary = Path(path).resolve(), Path(native_binary).resolve()
    require(type(source_request_replay) is bool, 'invalid_source_request_replay_policy')
    binding = launcher_binding(native_binary, source_request_replay=source_request_replay)
    module = 'source_request_oracle' if source_request_replay else 'verified_axis_oracle'
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
            f'    from {module} import serve\n' +
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
                      'readback_expressions': ['x', 'T(x)', 'T(T(x))'],
                      'T_definition': 'binary64_trunc(x*10000)/10000_for_positive_finite_x',
                      'replay_location': 'T(T(x))_declared_before_first_native_request',
                      'replay_acceptance': 'actual_echo_exactly_equals_predeclared_location',
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


def declare_readback(location):
    """A fixed finite plan, independent of any native response or glyph data.

    Negative/zero coordinates retain the existing exact-only behavior. There
    is no search for a convenient decimal or loop until a native echo stops
    changing. If the fixed candidate fails its actual echo or payload check,
    the batch fails; no third native construction is attempted.
    """
    result = {}
    for tag, value in location.items():
        plan = {'requested': value, 'canonical': value}
        if finite_number(value) and value > 0 and math.isfinite(value * 10000):
            once = math.trunc(value * 10000) / 10000
            twice = math.trunc(once * 10000) / 10000
            plan.update(once=once, twice=twice, canonical=twice)
        result[tag] = plan
    return result


def effective_readback(record, identity, requested, *, replay=False, declaration=None):
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
            # The fixed, predeclared second instance must really be stable.
            # Never feed another observed value back into a retry loop.
            require(value == expected, 'native_readback_replay_not_exactly_stable', **context)
        elif value != expected:
            require(expected > 0 and value > 0 and math.isfinite(expected * 10000),
                    'positive_decimal4_candidate_unavailable', **context)
            plan = (declaration or declare_readback(requested))[tag]
            candidate, second = plan['once'], plan['twice']
            context.update(expected_candidate_value=candidate,
                           expected_candidate_value_hex=float(candidate).hex(),
                           expected_secondary_candidate_value=second,
                           expected_secondary_candidate_value_hex=float(second).hex())
            require(value == candidate or value == second,
                    'native_readback_not_named_decimal4_candidate', **context)
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
    declaration = declare_readback(request['location'])
    canonical = {tag: value['canonical'] for tag, value in declaration.items()}
    for axis in identity['axes']:
        require(axis['minimum'] <= canonical[axis['tag']] <= axis['maximum'],
                'predeclared_axis_candidate_outside_source_range', axis=axis['tag'])
    original_request = {**request, 'request_id': f'axis-{sequence}-original'}
    original, seen, reported = {}, set(), None
    for record in exchange(original_request):
        gid = validate_native_record(record, original_request, seen)
        try:
            effective = effective_readback(record, identity, request['location'], declaration=declaration)
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
    # Keep the opaque legacy request-ID suffix for protocol compatibility. The
    # coordinate was computed before exchange(), not selected from reported[1].
    replay_request = {**request, 'request_id': f'axis-{sequence}-reported', 'location': canonical}
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
                'predeclared_replay_location': canonical,
                'replay_declared_before_native_observations': True,
                'replay_echo_exactly_stable': True,
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
          *, response_timeout=120., maximum_batch_bytes=MAX_BATCH_BYTES, source_request_replay=False):
    source, native_binary = Path(source).resolve(), Path(native_binary).resolve()
    process = reader = request = None
    external_requests = verified_glyphs = internal_requests = internal_glyphs = 0
    backend, backend_key = BACKEND, 'axis_verification_backend'
    metadata_verifier, batch_verifier = verified_metadata, verify_batch
    source_strict_counts = {'strict_axis_count': 0, 'strict_axis_pass_count': 0, 'strict_axis_failure_count': 0}

    def emit(record):
        output_stream.write(json.dumps(record, allow_nan=False, separators=(',', ':')) + '\n')
        output_stream.flush()

    try:
        require(type(source_request_replay) is bool, 'invalid_source_request_replay_policy')
        if source_request_replay:
            from source_request_oracle import (BACKEND as backend, verified_metadata as metadata_verifier,
                                               verify_batch as batch_verifier)
            backend_key = 'source_request_verification_backend'
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

            metadata = metadata_verifier(read()[0], digest, byte_size, identities)
            binding_key = ('source_request_verification_dependency_binding' if source_request_replay
                           else 'axis_verification_dependency_binding')
            metadata[binding_key] = launcher_binding(native_binary, source_request_replay=source_request_replay)
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
                batch = batch_verifier(request, identities, digest, exchange, external_requests + 1)
                if source_request_replay:
                    observed = batch[0]['source_request_verification']['readback_diagnostic']
                    for key in source_strict_counts:
                        source_strict_counts[key] += observed[key]
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
            extra = {}
            if source_request_replay:
                from source_request_oracle import POLICY
                extra = {'source_request_verification_policy': copy.deepcopy(POLICY),
                         'source_request_readback_diagnostic': source_strict_counts}
            emit({**summary, 'request_count': external_requests, 'successful_glyph_count': verified_glyphs,
                  backend_key: backend, 'verified_batch_count': external_requests,
                  'internal_native_request_count': internal_requests, 'internal_native_glyph_count': internal_glyphs,
                  'upstream_native_summary': summary, 'source_unchanged': True, **extra})
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
                    'error_type': type(error).__name__, backend_key: backend, **context}
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
