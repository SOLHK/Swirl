#!/usr/bin/env python3
"""Strict native verification of known plus unseen original transform fixtures."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
from fontTools.ttLib import TTFont, newTable
from probe_transform_stages import composite, run as observe, LIMIT
from probe_hierarchy_rules import shape_record, hvgl_table, HVGL, ExperimentalRenderer, native_quadratics, point_error
from verify_tangent_projection import native_events
from make_synthetic_hvf import create
from batch_geometry import BatchGeometry


def heldout_cases():
    # This seed and these fixtures were not used to infer the transformation.
    rng = np.random.default_rng(20371021)
    for i in range(48):
        coords = rng.uniform(-.97, .97, 3).tolist()
        tm = {0: rng.uniform(-150, 150, 2).tolist()}
        rm = {0: [float(rng.uniform(-2.7, 2.7))]}
        te = {(0, k): rng.uniform(-100, 100, 2).tolist() for k in range(6)}
        re = {(0, k): [float(rng.uniform(-.9, .9))] for k in range(6)}
        kwargs = dict(axes=3, tm=tm, rm=rm, te=te, re=re)
        if i % 2:
            parts = [composite(1, tree_parts=3, tree_axes=5, axis_master={0: .125},
                axis_extreme={(0, 0): -.5, (0, 1): .5}, **kwargs),
                composite(2, tm={0: [13., -19.]}, rm={0: [.317]},
                    te={(0, 0): [-17., 11.], (0, 1): [31., -7.]},
                    re={(0, 0): [-.21], (0, 1): [.37]}), shape_record()]
        else:
            parts = [composite(1, tree_axes=4, **kwargs), shape_record()]
        yield f'unseen_{i}', hvgl_table(parts), coords


def check_case(raw, coords, events):
    table = HVGL(raw); table.validate(); native = native_quadratics(events)
    errors = {}
    for tangents in (False, True):
        scalar = ExperimentalRenderer(table, isolated_tangents=tangents).render(0, coords)
        batch = BatchGeometry(table, isolated_tangents=tangents).render(0, [coords])
        errors[f'scalar_tangents_{tangents}'] = point_error(scalar, native)
        errors[f'batch_tangents_{tangents}'] = point_error([p[0] for p in batch.paths], native)
    return errors


def verify(binary, output):
    if output.exists():
        raise FileExistsError(output)
    known = observe(binary, output.with_name('transform-known.json'))
    results = []
    for row in known['results']:
        errors = check_case(bytes.fromhex(row['synthetic_input_hvgl_hex']), row['design_location'], row['synthetic_native_events'])
        results.append({'case': row['case'], 'errors': errors})
    with tempfile.TemporaryDirectory(prefix='swirl-transform-heldout-') as tmp:
        font = Path(tmp) / 'original.ttf'; create(font)
        for name, raw, coords in heldout_cases():
            with TTFont(font, recalcBBoxes=False, recalcTimestamp=False) as f:
                table = newTable('hvgl'); table.data = raw; f['hvgl'] = table
                pending = Path(tmp) / 'pending.ttf'; f.save(pending)
            pending.replace(font)
            events = native_events(binary, font, coords)
            errors = check_case(raw, coords, events)
            results.append({'case': name, 'errors': errors, 'synthetic_hvgl_hex': raw.hex(),
                            'design_location': coords, 'synthetic_native_events': events})
    failed = sum(any(e > LIMIT for e in row['errors'].values()) for row in results)
    report = {'status': 'NATIVE_TRANSFORM_REGRESSION_PASS' if not failed else 'NATIVE_TRANSFORM_REGRESSION_FAILED',
              'data_origin': 'self_authored_geometry_only', 'original_font_acceptance': 'NOT_ESTABLISHED',
              'cases': len(results), 'previous_cases_retained': len(known['results']), 'new_cases': 48,
              'failures': failed, 'tolerance_font_units': LIMIT,
              'max_point_error': max(e for row in results for e in row['errors'].values()), 'results': results}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}), flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(verify(args.binary, args.output))
