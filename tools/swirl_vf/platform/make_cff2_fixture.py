#!/usr/bin/env python3
"""Generate original CFF2 controls; accepts no private source font.

The quadratic control comes from the existing authored CoreText fixture. A
quarter-unit X translation deliberately exercises fractional default points.
Its two TTC faces, GIDs and three axes are retained. This is not SwirlVF.ttc.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
import tempfile

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cff2_geometry as geometry
from cff2_metrics import prepare_from_truetype
from cff2_certificate import certify
from test_coretext_extract import make_fixture

TAGS = ('WDTH', 'wght', 'HGHT')
GRID = [dict(zip(TAGS, p)) for p in itertools.product((-1., 0., 1.), repeat=3)]
HOLDOUTS = [dict(zip(TAGS, p)) for p in ((.25, -.5, .75), (.125, .375, -.625))]


def records(font, name, locations, translation=0., *, repeat_contours=1, nonlinear=False):
    result = []
    for location in locations:
        glyph = font.getGlyphSet(location=location, normalized=True, recalcBounds=False)[name]
        commands = geometry.source_commands(glyph)
        if nonlinear:
            # Authored non-additive curvature: zero on each individual axis,
            # nonzero when width, weight and height move together. The formula
            # is evaluated directly from the source, never from fitted deltas.
            x, y, z = (location.get(tag, 0.) for tag in TAGS)
            for command in commands:
                if command[0] == 'qCurveTo':
                    command[2] += .11*x*x*y*y*z
        for command in commands:
            for index in range(1, len(command), 2):
                command[index] += translation
        result.append(commands * repeat_contours)
    return result


def convert(font, translation=0., *, factored=False, compact=False, adaptive=False, ramp=False, hierarchical=False, repeat_contours=1):
    if type(repeat_contours) is not int or not 1 <= repeat_contours <= 1024:
        raise ValueError('invalid_authored_contour_repeat')
    if sum((factored, compact, adaptive, ramp, hierarchical)) > 1:
        raise ValueError('choose_one_cff2_encoding')
    grid, held = GRID, HOLDOUTS
    if factored or compact:
        # More Cartesian regions than the CFF2 operand stack can hold in a
        # flat blend. Algebraic factoring must preserve the same function.
        grid = [dict(zip(TAGS, p)) for p in itertools.product(
            tuple(i / 4 for i in range(-4, 5)), repeat=3)]
        held = [dict(zip(TAGS, p)) for p in ((.17, -.31, .79), (-.77, .42, .57))]
    models = {}
    for name in font.getGlyphOrder():
        if ramp or hierarchical:
            import numpy as np
            from local_cff2_geometry import encode
            knots = [np.linspace(-1,1,9)]*3
            positions = list(itertools.product(*knots))
            observed = [geometry.operands(c) for c in records(font,name,
                [dict(zip(TAGS,map(float,p))) for p in positions],translation,
                repeat_contours=repeat_contours,nonlinear=True)]
            ops = observed[0][0]
            geometry.require(all(o==ops for o,_ in observed),'authored_ramp_topology_changed')
            values = np.asarray([v for _,v in observed]).reshape(9,9,9,-1)
            model = encode(knots,values,ops,TAGS,basis='hierarchical' if hierarchical else 'ramp')
            if hierarchical:
                from hierarchical_cff2_compression import compress
                model = compress(model, max_regions=96, error_budget=1/256)
                geometry.require(model.evidence['uniform_model_compression']['within_budget'],
                                 'authored_hierarchical_compression_failed')
            held = np.random.default_rng(179331).uniform(-1,1,(128,3))
            locations = [dict(zip(TAGS,map(float,p))) for p in held]
            truth = [geometry.operands(c) for c in records(font,name,locations,translation,
                repeat_contours=repeat_contours,nonlinear=True)]
            geometry.require(all(o==ops for o,_ in truth),'authored_ramp_holdout_topology_changed')
            expected = np.asarray([geometry.control_points(o,v) for o,v in truth])
            actual = np.asarray([model.evaluate(p) for p in locations])
            errors = np.linalg.norm(actual-expected,axis=2).max(axis=1,initial=0)
            model.evidence.update(sampled_geometry_passed=bool((errors<=geometry.LIMIT).all()),
                max_holdout_error=float(errors.max()),holdout_count=len(held),
                failures=[dict(index=int(i),error=float(errors[i])) for i in np.flatnonzero(errors>geometry.LIMIT)],
                fixture_scope='authored_full_cube_local_basis_control')
            models[name] = model
            continue
        if adaptive:
            import numpy as np
            from adaptive_cff2_geometry import fit_tensor
            operators = geometry.operands(records(font, name, [{}], translation, nonlinear=True, repeat_contours=repeat_contours)[0])[0]
            def evaluate(points):
                commands = records(font, name, [dict(zip(TAGS, map(float, p))) for p in points],
                    translation, repeat_contours=repeat_contours, nonlinear=True)
                values = [geometry.operands(row) for row in commands]
                if any(ops != operators for ops, _ in values):
                    raise ValueError('authored_adaptive_topology_changed')
                return np.asarray([v for _, v in values])
            model = fit_tensor(evaluate, operators, TAGS,
                np.random.default_rng(19277).uniform(-1, 1, (64, 3)))
            models[name] = geometry.compact(model)
            continue
        model = geometry.fit(records(font, name, grid, translation, repeat_contours=repeat_contours), grid,
                             records(font, name, held, translation, repeat_contours=repeat_contours), held, TAGS)
        models[name] = (geometry.factor(model) if factored else
                        geometry.compact(model) if compact else model)
    return geometry.install(prepare_from_truetype(font), models,
                            experimental_local=ramp or hierarchical,experimental_nested=factored), models


def write_fixture(path, *, factored=False, compact=False, adaptive=False, ramp=False, hierarchical=False, repeat_contours=1):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError('fresh_authored_cff2_output_required')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as tmp:
        source = Path(tmp) / 'authored-source.ttc'; make_fixture(source)
        with TTCollection(source) as original:
            conversions = [convert(font, .25, factored=factored, compact=compact,
                                   adaptive=adaptive, ramp=ramp, hierarchical=hierarchical, repeat_contours=repeat_contours)
                           for font in original.fonts]
            result = TTCollection(); result.fonts = [font for font, _ in conversions]
            output = Path(tmp) / 'authored-cff2.ttc'; result.save(output)
            # A serialized read is required before exposing even an authored control.
            certificates = []
            with TTCollection(output) as saved:
                if len(saved.fonts) != 2 or not all('CFF2' in font and
                        font['maxp'].numGlyphs == 3 for font in saved.fonts):
                    raise ValueError('authored_cff2_serialized_coverage_changed')
                if not factored:
                    for font, (_, models) in zip(saved.fonts, conversions):
                        certificates.append(certify(font, models))
            output.replace(path)
    return {'scope': 'authored CFF2 control, not original-font conversion',
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size, 'faces': 2, 'glyphs_per_face': 3,
            'axes': list(TAGS), 'factored_blends': factored, 'compact_blends': compact,
            'adaptive_three_axis_blends': adaptive,
            'ramp_three_axis_blends': ramp,
            'compressed_hierarchical_three_axis_blends': hierarchical,
            'repeat_contours': repeat_contours,
            'serialized_coefficient_certificates': certificates, 'production_accepted': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    encoding = parser.add_mutually_exclusive_group()
    encoding.add_argument('--factored', action='store_true')
    encoding.add_argument('--compact', action='store_true')
    encoding.add_argument('--adaptive', action='store_true')
    encoding.add_argument('--ramp', action='store_true')
    encoding.add_argument('--hierarchical', action='store_true')
    args = parser.parse_args()
    print(json.dumps(write_fixture(args.output, factored=args.factored, compact=args.compact,
                                  adaptive=args.adaptive, ramp=args.ramp, hierarchical=args.hierarchical), indent=2))
