#!/usr/bin/env python3
"""Transparent CoreText-outline / source-table-metric conversion adapter.

CoreText output is not corrected or relabelled as an exact measurement. The raw
metric values remain in every adapted record, alongside table-derived converter
inputs, their provenance and signed discrepancies. Outlines, bounds, geometric
LSB, requested locations and API-reported locations are preserved verbatim.

The CLI deliberately accepts only standard glyf fonts with a verified identity
avar. Apple HVGL needs separately verified user-to-design coordinates and must
use adapt_record with those coordinates explicitly supplied by its caller. This
module contains no tentative Apple mapping and cannot grant source acceptance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

from fontTools.ttLib import TTCollection
from fontTools.varLib.models import normalizeLocation

from audit_font import raw_avar
from incremental_pipe import TimedLineReader
from source_metrics import SourceMetrics


FIELDS = ('advance_width', 'advance_height', 'horizontal_origin_x',
          'horizontal_origin_y', 'vertical_origin_x', 'vertical_origin_y')
RAW_FIELDS = FIELDS + ('lsb', 'horizontal_advance_vector', 'vertical_advance_vector',
                     'vertical_origin_translation', 'horizontal_advance_sum',
                     'vertical_advance_sum', 'vertical_origin_derivation')


def require(value, message):
    if not value:
        raise ValueError(message)


def source_hash(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def identity_design_coordinates(font, user_location):
    """Normalize a strictly verified standard identity mapping, without rounding.

    This is the mathematical source-table design location. It is separately
    labelled from an engine's quantized internal coordinate. Native geometry
    still has to meet the reconstruction/holdout error budget at each request.
    """
    require('glyf' in font and 'hvgl' not in font and 'hvpm' not in font,
            'identity CLI policy cannot accept Apple HVGL user-axis mapping')
    axes = list(font['fvar'].axes) if 'fvar' in font else []
    tags = [axis.axisTag for axis in axes]
    require(set(user_location) == set(tags), 'all source user axes must be explicit')
    if 'avar' in font:
        require(bool(axes), 'avar without fvar')
        data = font.reader['avar'] if font.reader and 'avar' in font.reader else font.getTableData('avar')
        report = raw_avar(data, tags)
        require(report.get('major') == 1 and report.get('minor') == 0
                and not report.get('violations') and report.get('trailing_bytes') == 0,
                'only avar version 1 identity mapping is supported')
        require(len(report.get('axes', [])) == len(tags), 'avar axis count differs')
        for axis in report['axes']:
            records = [(r['from_f2dot14'], r['to_f2dot14']) for r in axis['records']]
            require(all(a == b for a, b in records)
                    and all(a < b for (a, _), (b, _) in zip(records, records[1:]))
                    and all(pair in records for pair in [(-16384, -16384), (0, 0), (16384, 16384)])
                    and records[0] == (-16384, -16384) and records[-1] == (16384, 16384),
                    'nonidentity, duplicate, unordered or incomplete avar needs a verified mapping')
    ranges = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in axes}
    for tag, value in user_location.items():
        low, _, high = ranges[tag]
        require(isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and low <= value <= high,
                'source user coordinate is nonfinite or out of range')
    return normalizeLocation(user_location, ranges)


def adapt_record(provider, native_record, normalized_design_coordinates, coordinate_provenance):
    """Return converter metrics plus unchanged raw evidence, without mutation.

    The caller must bind source identity and verify the supplied coordinate
    mapping. A provenance label records that decision; it does not prove it.
    No unverified Apple mapping is inferred from the API's decimal readback.
    """
    require(isinstance(coordinate_provenance, dict)
            and isinstance(coordinate_provenance.get('policy'), str)
            and bool(coordinate_provenance['policy'])
            and isinstance(coordinate_provenance.get('source_sha256'), str)
            and len(coordinate_provenance['source_sha256']) == 64
            and all(c in '0123456789abcdef' for c in coordinate_provenance['source_sha256']),
            'explicit coordinate policy and source identity are required')
    require(type(native_record.get('face_index')) is int
            and native_record['face_index'] >= 0
            and coordinate_provenance.get('face_index') == native_record['face_index'],
            'metric provenance must bind the measured physical face')
    require(native_record.get('error') is None and 'glyph_id' in native_record
            and native_record.get('type') != 'request_error', 'failed native measurement cannot be adapted')
    require('raw_coretext_metrics' not in native_record, 'native metric record was already adapted')
    require(all(isinstance(native_record.get(field), (int, float))
                and not isinstance(native_record[field], bool)
                and math.isfinite(native_record[field]) for field in FIELDS),
            'native record is missing finite raw metrics')
    reference = provider.at(native_record['glyph_id'], normalized_design_coordinates)
    # SourceMetrics evaluates the stored SFNT coordinate frame. A renderer may
    # shift a nonzero left phantom point to its pen origin. Such paths cannot be
    # combined with unshifted table origins without a separately proven frame
    # conversion. The original fixtures and HVGL source use the common origin.
    require(all(reference[field] == native_record[field]
                for field in ('horizontal_origin_x', 'horizontal_origin_y')),
            'source-table and native-path coordinate origins differ; explicit frame verification required')
    result = copy.deepcopy(native_record)
    result['raw_coretext_metrics'] = {field: copy.deepcopy(native_record[field])
                                     for field in RAW_FIELDS if field in native_record}
    result['source_metric_provenance'] = {**copy.deepcopy(coordinate_provenance),
        'metric_source': reference['metric_source'],
        'vertical_origin_basis': reference['vertical_origin_basis'],
        'normalized_design_location': dict(normalized_design_coordinates),
        'native_API_values_replaced_in_evidence': False,
        'old_strict_native_API_gate': 'UNCHANGED_SEPARATE_CHECK_NOT_PASSED_BY_THIS_ADAPTER'}
    result['raw_coretext_metric_error_font_units'] = {
        field: native_record[field] - reference[field] for field in FIELDS}
    result['metric_backend'] = 'SourceTables'
    for field in FIELDS:
        result[field] = reference[field]
    result['vertical_origin_derivation'] = reference['vertical_origin_basis']
    return result


def adapted_metadata(native, digest, faces):
    require(native.get('type') == 'metadata' and native.get('backend') == 'CoreText'
            and native.get('source_sha256') == digest, 'native source/backend metadata mismatch')
    require(not native.get('diagnostic_readback_observation_only'),
            'diagnostic-only axis observation is not an accepted conversion oracle')
    require(len(native.get('faces', [])) == len(faces)
            and all(f.get('status') == 'identity_verified' and f.get('face_index') == i
                    for i, f in enumerate(native['faces'])), 'native physical source face mismatch')
    for font, face in zip(faces, native['faces']):
        require(face.get('upm') == font['head'].unitsPerEm
                and face.get('glyph_count') == len(font.getGlyphOrder()),
                'native source UPEM or GID count mismatch')
    result = copy.deepcopy(native)
    result.update({'outline_backend': 'CoreText', 'metric_backend': 'SourceTables',
                   'raw_coretext_metrics_retained_per_glyph': True,
                   'source_metric_coordinate_policy': 'standard_verified_identity_avar_unrounded_design_coordinates',
                   'strict_native_API_metric_acceptance': 'NOT_ESTABLISHED_BY_THIS_ADAPTER',
                   'native_metrics_policy': native.get('metrics_policy'),
                   'metrics_policy': 'source table converter inputs; raw CoreText metrics and discrepancies retained'})
    return result


def serve(source, native_binary, input_stream=sys.stdin, output_stream=sys.stdout):
    """Forward the original JSON-lines requests to one unchanged native process."""
    source, native_binary = Path(source).resolve(), Path(native_binary).resolve()
    digest = source_hash(source)
    process = reader = None
    adapted = 0
    try:
        with TTCollection(source, lazy=True) as collection:
            # Refuse unsupported source policies before launching CoreText.
            for font in collection.fonts:
                axes = list(font['fvar'].axes) if 'fvar' in font else []
                identity_design_coordinates(font, {a.axisTag: a.defaultValue for a in axes})
            providers = [SourceMetrics(font) for font in collection.fonts]
            process = subprocess.Popen([str(native_binary), str(source)], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=sys.stderr, text=True,
                                       encoding='utf-8', bufsize=1)
            reader = TimedLineReader(process.stdout.fileno())

            def read():
                line = reader.readline(timeout=120.)
                require(bool(line), 'CoreText ended before the complete response')
                return json.loads(line)

            def emit(record):
                output_stream.write(json.dumps(record, allow_nan=False, separators=(',', ':')) + '\n')
                output_stream.flush()

            emit(adapted_metadata(read(), digest, collection.fonts))
            for line in input_stream:
                if not line.strip():
                    continue
                require(len(line.encode('utf-8')) <= 1_048_576, 'adapter request line exceeds limit')
                request = json.loads(line)
                face = request['face_index']
                require(type(face) is int and 0 <= face < len(providers), 'adapter face index out of range')
                coordinates = identity_design_coordinates(collection.fonts[face], request['location'])
                require(isinstance(request['glyph_ids'], list) and 0 < len(request['glyph_ids']) <= 4096
                        and all(type(gid) is int and 0 <= gid < len(providers[face].names)
                                for gid in request['glyph_ids'])
                        and len(set(request['glyph_ids'])) == len(request['glyph_ids']), 'invalid adapter glyph batch')
                process.stdin.write(line if line.endswith('\n') else line + '\n')
                process.stdin.flush()
                seen = set()
                for _ in request['glyph_ids']:
                    record = read()
                    require(record.get('request_id') == request['request_id'] and record.get('face_index') == face,
                            'native response identity mismatch')
                    if record.get('error') is not None:
                        emit(record)  # Preserve the actual axis/path failure, then stop.
                        return 3
                    gid = record.get('glyph_id')
                    require(gid in request['glyph_ids'] and gid not in seen
                            and record.get('location') == request['location'],
                            'native GID/request coordinate mismatch')
                    seen.add(gid)
                    emit(adapt_record(providers[face], record, coordinates, {
                        'policy': 'standard_verified_identity_avar_unrounded_design_coordinates',
                        'source_sha256': digest, 'face_index': face}))
                    adapted += 1
            process.stdin.close()
            summary = read()
            require(summary.get('type') == 'summary' and summary.get('error_count') == 0
                    and summary.get('source_sha256') == digest
                    and summary.get('successful_glyph_count') == adapted,
                    'native summary incomplete or mismatched')
            summary.update({'table_metric_records': adapted, 'raw_coretext_metrics_retained': True})
            emit(summary)
            require(process.wait(timeout=10) == 0, 'native process failed')
            require(source_hash(source) == digest, 'source bytes changed during conversion')
        return 0
    finally:
        if reader is not None:
            reader.close()
        if process is not None:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--native', required=True, type=Path)
    parser.add_argument('--standard-identity', action='store_true', required=True,
                        help='Explicitly restrict the CLI to verified standard identity avar fonts')
    args = parser.parse_args()
    try:
        return serve(args.source, args.native)
    except Exception as error:
        print(json.dumps({'type': 'fatal_error', 'error': str(error)}, allow_nan=False), flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
