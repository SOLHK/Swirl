#!/usr/bin/env python3
"""Native experiments for master/extremum transforms; self-authored data only.

Do not change the production renderer based on a passing Python hypothesis.
This program records independent Apple observations and every competing model.
It never reads the Apple source font. No hypothesis is accepted automatically.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import numpy as np
from fontTools.ttLib import TTFont, newTable
from probe_hierarchy_rules import (align, shape_record, hvgl_table, HVGL,
    ExperimentalRenderer, native_quadratics, point_error)
from verify_tangent_projection import native_events
from make_synthetic_hvf import create

LIMIT = 1 / 32


def transforms(master, extreme, components):
    m = sorted(master.items())
    e = sorted(extreme.items())
    data = np.asarray([v for _, v in m], dtype='<f4').tobytes()
    data += np.asarray([v for _, v in e], dtype='<f4').tobytes()
    data += np.asarray([k for k, _ in e], dtype='<u2').tobytes()
    data += np.asarray([k for k, _ in m], dtype='<u2').tobytes()
    if any(len(v) != components for _, v in m + e):
        raise ValueError('transform component count')
    return align(data)


def composite(child, *, axes=1, tree_parts=2, tree_axes=2,
              axis_master=None, axis_extreme=None, tm=None, te=None, rm=None, re=None):
    axis_master, axis_extreme = axis_master or {}, axis_extreme or {}
    tm, te, rm, re = tm or {}, te or {}, rm or {}, re or {}
    rows, values, starts = [], [], [0]
    for col in range(2 * axes):
        for (row, column), value in sorted(axis_extreme.items()):
            if column == col:
                rows.append(row); values.append(value)
        starts.append(len(rows))
    mr = sorted(axis_master)
    indices = align(np.asarray(starts + mr + rows, dtype='<u2').tobytes())
    sections = [struct.pack('<IHH', child, 0, 0), indices,
                np.asarray([axis_master[r] for r in mr], dtype='<f4').tobytes(),
                np.asarray(values, dtype='<f4').tobytes(),
                transforms(tm, te, 2), transforms(rm, re, 1)]
    position, offsets = 36, []
    for data in sections:
        offsets.append(position // 4); position += len(data)
    return struct.pack('<18H', 1, axes, 1, tree_parts, tree_axes, 2 * max(axes, 1),
                       len(mr), len(rows), len(tm), len(rm), len(te), len(re), *offsets) + b''.join(sections)


def rotation(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s], [s, c]])


def direct_cases():
    for angle in (0., .371, math.pi / 2, -1.2):
        for varied_rotation in (False, True):
            kwargs = dict(tm={0: [30., -40.]}, rm={0: [angle]},
                          te={(0, 0): [17., -11.], (0, 1): [-5., 23.]})
            if varied_rotation:
                kwargs['re'] = {(0, 0): [-.21], (0, 1): [.16]}
            for x in (-1., -.375, 0., .375, 1.):
                yield f'direct_{angle}_{varied_rotation}_{x}', kwargs, [x]
    kwargs = dict(axes=3, tree_axes=4, tm={0: [30., -40.]}, rm={0: [.371]},
                  te={(0, 0): [17., -11.], (0, 1): [-5., 23.],
                      (0, 2): [13., 7.], (0, 3): [11., -3.],
                      (0, 4): [-7., 19.], (0, 5): [3., -17.]},
                  re={(0, 0): [-.21], (0, 1): [.16], (0, 2): [.11],
                      (0, 3): [-.07], (0, 4): [-.19], (0, 5): [.23]})
    for coords in ((0., 0., 0.), (-1., -1., -1.), (1., 1., 1.),
                   (.375, -.625, .25), (-.175, .325, -.725)):
        yield f'mixed_{coords}', kwargs, list(coords)


def predictions(part, coordinates, leaf):
    weights = np.array([v for x in coordinates for v in (max(-x, 0), max(x, 0))])
    def values(record):
        master = record.master_values.sum(axis=0, dtype=np.float64)
        extreme = np.zeros_like(master, dtype=np.float64)
        for (_, col), vector in zip(record.extreme_indices, record.extreme_values):
            extreme += weights[int(col)] * vector
        return master, extreme
    tm, te = values(part.translations); rm, re = values(part.rotations)
    rm, re = float(rm[0]), float(re[0])
    r = rotation(rm + re)
    alternatives = {
        'legacy_sum': tm + te,
        'master_after_extremum': tm + rotation(rm) @ te,
        'extremum_after_master': rotation(re) @ tm + te,
        'extremum_translation_before_its_rotation': tm + rotation(rm + re) @ te,
    }
    return {name: leaf @ r.T + shift for name, shift in alternatives.items()}


def run(binary, output):
    if output.exists():
        raise FileExistsError(output)
    records = []
    with tempfile.TemporaryDirectory(prefix='swirl-transform-original-') as tmp:
        font = Path(tmp) / 'self-authored.ttf'; create(font)
        experiments = []
        for name, kwargs, coords in direct_cases():
            experiments.append((name, [composite(1, **kwargs), shape_record()], coords, True))
        for outer in (.371, -1.2):
            for inner in (-.23, .41):
                for x in (-1., -.375, 0., .625, 1.):
                    # Both inherited descendant and local transforms; every
                    # coordinate below is an independently chosen test number.
                    parts = [composite(1, tree_parts=3, tree_axes=3,
                        axis_master={0: .125}, axis_extreme={(0, 0): -.5, (0, 1): .5},
                        tm={0: [30., 40.], 1: [13., -7.]}, rm={0: [outer]},
                        te={(0, 1): [11., 3.], (1, 0): [-17., 9.]}, re={(1, 1): [.17]}),
                        composite(2, tm={0: [-25., 17.]}, rm={0: [inner]},
                                  te={(0, 0): [5., -9.], (0, 1): [-3., 7.]},
                                  re={(0, 0): [-.13], (0, 1): [.21]}), shape_record()]
                    experiments.append((f'nested_{outer}_{inner}_{x}', parts, [x], False))
        for factor in (-2., -.25, 0., .25, 1., 1.25, 3.):
            experiments.append((f'parallel_factor_{factor}', [shape_record(parallel=factor)], [0.], False))
        for name, parts, coords, direct in experiments:
            raw = hvgl_table(parts); table = HVGL(raw); table.validate()
            with TTFont(font, recalcBBoxes=False, recalcTimestamp=False) as f:
                wrapper = newTable('hvgl'); wrapper.data = raw; f['hvgl'] = wrapper
                pending = Path(tmp) / 'pending.ttf'; f.save(pending)
            pending.replace(font)
            events = native_events(binary, font, coords + [0.] * (3 - len(coords)))
            native = native_quadratics(events)
            portable = ExperimentalRenderer(table).render(0, coords)
            error = point_error(portable, native)
            record = {'case': name, 'design_location': coords,
                      'synthetic_input_hvgl_hex': raw.hex(),
                      'synthetic_native_events': events,
                      'production_max_point_error': error, 'production_passed': error <= LIMIT}
            if direct:
                leaf = ExperimentalRenderer(table).render(1, [0.])[0]
                record['hypotheses'] = {label: point_error([points], native)
                    for label, points in predictions(table.part(0), coords, leaf).items()}
            records.append(record)
        report = {'status': 'NATIVE_TRANSFORM_DIAGNOSIS_NOT_FONT_ACCEPTANCE',
                  'data_origin': 'self_authored_geometry_only', 'font_data_used': False,
                  'tolerance_font_units': LIMIT, 'cases': len(records),
                  'production_failures': sum(not r['production_passed'] for r in records),
                  'results': records}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.binary, args.output)
