#!/usr/bin/env python3
"""Compare portable hierarchy math with Apple HVF using original synthetic data.

Every point and variation coefficient is self-authored here. Results may be
published; no Apple font is read. A completed comparison is not original-font
acceptance. --require-pass makes any native disagreement fail the process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

import numpy as np
from fontTools.ttLib import TTFont, newTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from hvf import HVGL, ExperimentalRenderer
from make_synthetic_hvf import create

LIMIT = 1 / 32


def align(data, n=4):
    return data + bytes((-len(data)) % n)


def shape_record(*, parallel=0.25, axes=1):
    # Three unequal segments avoid the square's rotational symmetry. Curve
    # factor deliberately differs from 1/2 to test its orientation.
    master = np.array([[parallel, 0, 150, 20], [300, 80, 210, 220],
                       [20, 300, -60, 140]], dtype='<f8')
    header = align(struct.pack('<5H', 0, axes, 1, 3, 3) + bytes([0, 1, 1]), 8)
    deltas = np.zeros((axes * 2, 3, 4), dtype='<f8')
    if axes:
        # Move one explicit on-point and two controls. Leave parallel factor
        # unchanged, so expected fractional interpolation has a simple formula.
        deltas[0, 1, 0] = -40
        deltas[1, 1, 0] = 80
        deltas[0, 0, 2] = -20
        deltas[1, 0, 2] = 40
        deltas[0, 2, 3] = -10
        deltas[1, 2, 3] = 30
    return header + master.tobytes() + deltas.tobytes()


def composite_record(child, descendant_parts, descendant_axes, *,
                     master=0.125, slope=0.5, rotation=0.0,
                     translation=(30.0, 40.0), deep_translation=None):
    # A single child root with one axis. An outer node may also translate its
    # grandchild, exercising a structure-tree row distinct from the child row.
    count = 1 + (deep_translation is not None)
    subparts = struct.pack('<IHH', child, 0, 0)
    indices = struct.pack('<6H', 0, 1, 2, 0, 0, 0)
    # indices = CSC starts [0,1,2], master rows [0], extreme rows [0,0]
    masters = struct.pack('<f', master)
    extremes = struct.pack('<ff', -slope, slope)
    translations = struct.pack('<ff', *translation)
    rows = [0]
    if deep_translation is not None:
        translations += struct.pack('<ff', *deep_translation)
        rows.append(descendant_parts - 1)
    translations = align(translations + struct.pack('<' + 'H' * count, *rows))
    rotations = align(struct.pack('<fH', rotation, 0))
    sections = [subparts, indices, masters, extremes, translations, rotations]
    position = 36
    offsets = []
    for section in sections:
        offsets.append(position // 4)
        position += len(section)
    header = struct.pack('<18H', 1, 1, 1, descendant_parts + 1,
                         descendant_axes + 1, 2, 1, 2, count, 1, 0, 0, *offsets)
    return header + b''.join(sections)


def hvgl_table(parts):
    payload = bytearray(bytes(4 * (len(parts) + 1)))
    starts = []
    for part in parts:
        payload.extend(bytes((-(24 + len(payload))) % 8))
        starts.append(len(payload))
        payload.extend(part)
    starts.append(len(payload))
    struct.pack_into('<' + 'I' * len(starts), payload, 0, *starts)
    return struct.pack('<HHIIIII', 3, 1, 0, len(parts), 24, 1, 0) + payload


def cases():
    for factor in (0.25, 0.75):
        yield f'curve_factor_{factor}', [shape_record(parallel=factor)], [0.0]
    for angle in (0.0, np.pi / 2, -np.pi / 2, 0.371):
        for axis in (-1.0, 0.0, 0.375, 1.0):
            yield f'single_rotation_{angle:.6f}_axis_{axis}', [
                composite_record(1, 1, 1, rotation=angle), shape_record()], [axis]
    for master in (-1.25, 1.25):
        yield f'internal_axis_{master}', [
            composite_record(1, 1, 1, master=master), shape_record()], [0.0]
    for outer_angle, inner_angle in ((0.0, 0.0), (0.371, 0.0),
                                      (0.0, -0.23), (0.371, -0.23)):
        for deep in (None, (13.0, -7.0)):
            yield f'nested_{outer_angle}_{inner_angle}_deep_{deep is not None}', [
                composite_record(1, 2, 2, rotation=outer_angle,
                                 translation=(30.0, 40.0), deep_translation=deep),
                composite_record(2, 1, 1, rotation=inner_angle,
                                 translation=(-25.0, 17.0)), shape_record()], [0.375]


def native_quadratics(events):
    """One synthetic contour, preserving exact native segment boundaries."""
    start = previous = None
    segments = []
    for event in events:
        if event[0] == 'move':
            if start is not None:
                raise ValueError('unexpected second contour')
            start = previous = np.array(event[1:], dtype=float)
        elif event[0] in ('quad', 'line'):
            if previous is None:
                raise ValueError('native segment before move')
            point = np.array(event[-2:], dtype=float)
            control = np.array(event[1:3]) if event[0] == 'quad' else (previous + point) / 2
            segments.append(np.array([previous, control, point]))
            previous = point
        elif event[0] == 'close':
            if start is not None and np.linalg.norm(previous - start) > 1e-10:
                segments.append(np.array([previous, (previous + start) / 2, start]))
                previous = start
        elif event[0] == 'cubic':
            raise ValueError('unexpected cubic in quadratic fixture')
    if start is None or not segments:
        raise ValueError('missing synthetic contour')
    if not np.isfinite(segments).all():
        raise ValueError('nonfinite native geometry')
    return segments


def point_error(portable, native):
    if len(portable) != 1:
        raise ValueError('unexpected portable contour count')
    pairs = portable[0].reshape(-1, 2, 2)
    wanted = [np.array([pair[0], pair[1], pairs[(i + 1) % len(pairs), 0]])
              for i, pair in enumerate(pairs)]
    if len(wanted) != len(native):
        raise ValueError('segment count differs')
    return min(max(float(np.abs(a - native[(i + shift) % len(native)]).max())
                   for i, a in enumerate(wanted)) for shift in range(len(wanted)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-pass', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('choose a new output report')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='swirl-original-hierarchy-') as temporary:
        font = Path(temporary) / 'synthetic.ttf'
        create(font)
        for name, parts, coordinates in cases():
            data = hvgl_table(parts)
            parsed = HVGL(data)
            structural = parsed.validate()
            portable = ExperimentalRenderer(parsed).render(0, coordinates)
            with TTFont(font, recalcBBoxes=False, recalcTimestamp=False) as fixture:
                table = newTable('hvgl')
                table.data = data
                fixture['hvgl'] = table
                pending = Path(temporary) / 'pending.ttf'
                fixture.save(pending)
            pending.replace(font)
            request = ','.join(map(str, coordinates + [0.0, 0.0]))
            result = subprocess.run([str(args.binary.resolve()), str(font), '0', request, '0', '1'],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError('native synthetic process failed: ' + result.stderr[:400])
            rows = [json.loads(line) for line in result.stdout.splitlines() if line]
            outlines = [r for r in rows if r.get('record') == 'outline']
            if len(outlines) != 1 or outlines[0].get('status') != 'OK':
                raise ValueError('missing native synthetic outline')
            record = {'case': name, 'design_coordinates': coordinates,
                      'binary_sha256': hashlib.sha256(data).hexdigest(),
                      'structure': structural['binary_and_structure_validation'],
                      'portable_paths': [p.tolist() for p in portable],
                      'native_events': outlines[0]['events']}
            try:
                error = point_error(portable, native_quadratics(outlines[0]['events']))
                record.update(max_control_point_error=error, passed=error <= LIMIT)
            except ValueError as failure:
                record.update(passed=False, error=str(failure))
            records.append(record)
            print('SYNTHETIC_HIERARCHY ' + json.dumps(record, allow_nan=False), flush=True)
    failures = sum(not r['passed'] for r in records)
    report = {'status': 'SYNTHETIC_HIERARCHY_PASS' if not failures else 'SYNTHETIC_HIERARCHY_FAILED',
              'data_origin': 'self_authored_geometry_no_Apple_font',
              'original_font_acceptance': 'NOT_RUN', 'tolerance_font_units': LIMIT,
              'cases': len(records), 'failures': failures, 'records': records}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return 1 if args.require_pass and failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
