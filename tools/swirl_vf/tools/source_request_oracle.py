#!/usr/bin/env python3
"""Replay an unchanged source request, without mistaking readback for identity.

CoreText may return the same axis dictionary for different native instances.
The legacy exact-readback adapter intentionally tests a different proposition:
whether T(T(x)) reproduces x. This backend leaves that diagnostic untouched and
tests two independent constructions of x itself. It grants only finite source
sampling evidence; it does not accept any user-to-design or target-font mapping.
Raw axes, paths and metrics are never corrected. The shared transport retains
its source/table identity, complete-batch, resource, EOF and exit checks.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import re
import struct
import sys

import verified_axis_oracle as legacy


BACKEND = 'CoreTextExactOriginalRequestReplayV1'
POLICY = {
    'contract': 'unchanged_source_request_sampling_only_v1',
    'replay_location': 'original_binary64_request_declared_before_first_native_request',
    'replay_count': 1,
    'batch_release': 'all_requested_GIDs_require_exact_native_payload_and_reported_dictionary_replay',
    'numeric_equality': 'finite_binary64_bit_equality_including_signed_zero',
    'readback_is_instance_key': False,
    'strict_axis_echo_accepted': False,
    'source_user_mapping_inferred': False,
    'source_user_mapping_accepted': False,
    'target_mapping_accepted': False,
    'continuous_space_acceptance': False,
    'native_values_modified': False,
}


def binary64_bits(value):
    return struct.pack('>d', float(value)).hex()


def exact_json(left, right):
    """Retain all fields and numeric bits, including an observed signed zero."""
    if legacy.finite_number(left) or legacy.finite_number(right):
        return (legacy.same_json(left, right)
                and binary64_bits(left) == binary64_bits(right))
    if type(left) is not type(right):
        return False
    if type(left) is list:
        return len(left) == len(right) and all(exact_json(a, b) for a, b in zip(left, right))
    if type(left) is dict:
        return left.keys() == right.keys() and all(exact_json(left[k], right[k]) for k in left)
    return legacy.same_json(left, right)


def verified_metadata(native, digest, byte_size, identities):
    # Reuse the existing complete original-table/native identity checks, but do
    # not retain their distinct V2 axis-equivalence acceptance claim.
    legacy.require(type(native) is dict
                   and 'source_request_verification_backend' not in native
                   and 'source_request_verification_policy' not in native,
                   'native_source_request_was_already_adapted')
    result = legacy.verified_metadata(native, digest, byte_size, identities)
    result.pop('axis_verification_backend')
    result.pop('axis_verification_policy')
    result.update(axis_observations_only=True,
                  source_request_verification_backend=BACKEND,
                  source_request_verification_policy=copy.deepcopy(POLICY))
    return result


def validate_source_metadata(metadata, digest, byte_size, identities):
    """Check the narrow sampling contract before a consumer admits observations."""
    legacy.require(type(metadata) is dict
                   and metadata.get('axis_observations_only') is True
                   and metadata.get('upstream_axis_observations_only') is True
                   and metadata.get('source_request_verification_backend') == BACKEND
                   and exact_json(metadata.get('source_request_verification_policy'), POLICY)
                   and 'axis_verification_backend' not in metadata
                   and 'axis_verification_policy' not in metadata,
                   'source_request_sampling_contract_invalid')
    raw = copy.deepcopy(metadata)
    for key in ('source_request_verification_backend', 'source_request_verification_policy',
                'source_request_verification_dependency_binding', 'upstream_axis_observations_only'):
        raw.pop(key, None)
    # This rechecks every physical face, source table and axis against the
    # consumer's independent fontTools inspection, not against copied metadata.
    legacy.verified_metadata(raw, digest, byte_size, identities)
    binding = metadata.get('source_request_verification_dependency_binding')
    directory = Path(__file__).resolve().parent
    expected = {str(path): legacy.source_hash(path) for path in
                (Path(__file__).resolve(), directory / 'verified_axis_oracle.py', directory / 'incremental_pipe.py')}
    legacy.require(type(binding) is dict and set(binding) == {'backend', 'files', 'runtime'}
                   and binding['backend'] == BACKEND and exact_json(binding['runtime'], legacy.runtime_identity())
                   and type(binding['files']) is dict and len(binding['files']) == 4
                   and all(type(path) is str and type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
                           for path, value in binding['files'].items())
                   and all(binding['files'].get(path) == value for path, value in expected.items()),
                   'source_request_dependency_binding_invalid')
    binaries = set(binding['files']) - set(expected)
    legacy.require(len(binaries) == 1, 'source_request_native_dependency_invalid')
    binary = Path(next(iter(binaries)))
    legacy.require(binary.is_file() and binary.is_absolute()
                   and legacy.source_hash(binary) == binding['files'][str(binary)],
                   'source_request_native_dependency_changed')
    return metadata


def readback_diagnostic(record, identity, requested):
    """Observe raw readback and preserve the original 1e-6 strict result."""
    reported = record.get('reported_location')
    axes = identity['axes']
    legacy.require(type(reported) is dict and set(reported) <= {a['tag'] for a in axes},
                   'native_reported_axis_set_invalid')
    rows = []
    for axis in axes:
        tag = axis['tag']
        effective = reported.get(tag, axis['default'])
        legacy.require(legacy.finite_number(effective)
                       and axis['minimum'] <= effective <= axis['maximum'],
                       'native_axis_readback_nonfinite_or_out_of_range', axis=tag)
        strict = ((tag in reported or requested[tag] == axis['default'])
                  and abs(effective - requested[tag]) <= 1e-6)
        rows.append({'axis': tag, 'reported_axis_present': tag in reported,
                     'requested_value': requested[tag], 'effective_reported_value': effective,
                     'absolute_error': abs(effective - requested[tag]), 'strict_echo_passed': strict})
    return {'strict_axis_count': len(rows),
            'strict_axis_pass_count': sum(row['strict_echo_passed'] for row in rows),
            'strict_axis_failure_count': sum(not row['strict_echo_passed'] for row in rows),
            'strict_axis_tolerance': 1e-6, 'axes': rows}


def verify_batch(request, identities, digest, exchange, sequence):
    """Release x only after a second, unchanged x exactly reproduces every GID."""
    identity = legacy.validate_request(request, identities)
    request = copy.deepcopy(request)
    # Freeze both requests before observing native output. Native/exchange code
    # must not be able to mutate the outer source request or the replay plan.
    original_request = copy.deepcopy(request)
    original_request['request_id'] = f'source-{sequence}-original'
    replay_request = copy.deepcopy(request)
    replay_request['request_id'] = f'source-{sequence}-replay'
    planned_location = copy.deepcopy(request['location'])
    planned_bits = {tag: binary64_bits(value) for tag, value in planned_location.items()}
    original, original_reported, diagnostic = {}, None, None
    for phase, native_request in (('original', original_request), ('replay', replay_request)):
        legacy.require(exact_json(native_request['location'], planned_location), 'source_replay_plan_changed')
        seen = set()
        for record in exchange(copy.deepcopy(native_request)):
            legacy.require(type(record) is dict and 'source_request_verification' not in record,
                           'native_source_request_record_was_already_adapted')
            gid = legacy.validate_native_record(record, native_request, seen)
            legacy.require(exact_json(record['location'], planned_location),
                           'native_original_request_binary64_changed', glyph_id=gid)
            observed = readback_diagnostic(record, identity, planned_location)
            if phase == 'original':
                if original_reported is None:
                    original_reported = copy.deepcopy(record['reported_location'])
                    diagnostic = observed
                legacy.require(exact_json(record['reported_location'], original_reported),
                               'native_inconsistent_batch_readback', glyph_id=gid)
                original[gid] = copy.deepcopy(record)
                continue
            legacy.require(exact_json(record['reported_location'], original_reported),
                           'source_request_replay_reported_dictionary_changed', glyph_id=gid)
            left = {k: v for k, v in original[gid].items() if k not in legacy.ENVELOPE}
            right = {k: v for k, v in record.items() if k not in legacy.ENVELOPE}
            legacy.require(left.keys() == right.keys(), 'source_request_replay_payload_fields_changed', glyph_id=gid)
            for field in left:
                legacy.require(exact_json(left[field], right[field]), 'source_request_replay_payload_not_exact',
                               glyph_id=gid, field=field)
        legacy.require(seen == set(request['glyph_ids']), f'source_request_{phase}_batch_incomplete')
    evidence = {
        'backend': BACKEND, 'source_sha256': digest,
        'input_binary64_bits': planned_bits, 'replay_input_binary64_bits': copy.deepcopy(planned_bits),
        'replay_declared_before_native_observations': True,
        'verified_GIDs_in_batch': len(original), 'native_replay_count': 1,
        'verified_GID_list': copy.deepcopy(request['glyph_ids']),
        'exact_native_payload_equality': True, 'exact_reported_dictionary_equality': True,
        'source_user_mapping_accepted': False, 'strict_axis_echo_accepted': False,
        'native_values_modified': False, 'readback_diagnostic': diagnostic,
        'upstream_original_request_id': original_request['request_id'],
        'upstream_replay_request_id': replay_request['request_id'],
    }
    return [{**original[gid], 'request_id': request['request_id'],
             'source_request_verification': copy.deepcopy(evidence)} for gid in request['glyph_ids']]


def validate_source_evidence(record, request, digest, identity):
    """Bind a returned proof to this exact consumer request and original face."""
    legacy.require(type(request) is dict and type(request.get('face_index')) is int
                   and request['face_index'] == identity['face_index'], 'source_request_face_identity_invalid')
    legacy.validate_request({**request, 'face_index': 0}, [identity])
    proof = record.get('source_request_verification')
    bits = {tag: binary64_bits(value) for tag, value in request['location'].items()}
    diagnostic = readback_diagnostic(record, identity, request['location'])
    expected = {
        'backend': BACKEND, 'source_sha256': digest,
        'input_binary64_bits': bits, 'replay_input_binary64_bits': bits,
        'replay_declared_before_native_observations': True,
        'verified_GIDs_in_batch': len(request['glyph_ids']), 'native_replay_count': 1,
        'verified_GID_list': request['glyph_ids'],
        'exact_native_payload_equality': True, 'exact_reported_dictionary_equality': True,
        'source_user_mapping_accepted': False, 'strict_axis_echo_accepted': False,
        'native_values_modified': False, 'readback_diagnostic': diagnostic,
    }
    legacy.require(type(proof) is dict
                   and set(proof) == set(expected) | {'upstream_original_request_id', 'upstream_replay_request_id'}
                   and all(exact_json(proof.get(key), value) for key, value in expected.items()),
                   'source_request_evidence_invalid')
    original_id, replay_id = proof['upstream_original_request_id'], proof['upstream_replay_request_id']
    legacy.require(type(original_id) is str and re.fullmatch(r'source-[1-9][0-9]*-original', original_id)
                   and replay_id == original_id[:-8] + 'replay', 'source_request_replay_identity_invalid')
    legacy.require(record.get('request_id') == request['request_id']
                   and type(record.get('face_index')) is int and record['face_index'] == request['face_index']
                   and type(record.get('glyph_id')) is int and record['glyph_id'] in request['glyph_ids']
                   and exact_json(record.get('location'), request['location']),
                   'source_request_response_identity_invalid')
    return proof


def make_launcher(path, native_binary):
    return legacy.make_launcher(path, native_binary, source_request_replay=True)


def serve(source, native_binary, input_stream=sys.stdin, output_stream=sys.stdout, **limits):
    return legacy.serve(source, native_binary, input_stream, output_stream,
                        source_request_replay=True, **limits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--native', required=True, type=Path)
    args = parser.parse_args()
    return serve(args.source, args.native)


if __name__ == '__main__':
    raise SystemExit(main())
