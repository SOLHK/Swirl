#!/usr/bin/env python3
"""Fit/serialize one private HVF glyph using projection factors and local cells.

Independent native acceptance is deliberately a separate command and data set.
Imported research archives are rechecked against the current source evaluator;
their old acceptance flags are not trusted. All output must stay outside Git.
"""
from __future__ import annotations
import argparse
import hashlib
from itertools import product
import json
from pathlib import Path
import sys
import time

import numpy as np
from fontTools.ttLib import TTCollection
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from hvf import HVGL
from cff2_geometry import require, LIMIT
from projection_factorization import ProjectionSource
from joint_cells import refine, load, branch_probes
from joint_projection_font import build
from sparse_projection import fit, SparseParameters, encode_clamp_ramps
from test_coretext_extract import make_fixture


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Source(ProjectionSource):
    def local_probes(self, bounds):
        return branch_probes(self.table, self.gid, bounds)


def run(args):
    output = args.private_output.resolve()
    require(not output.exists() and not output.is_relative_to(Path(__file__).resolve().parents[3]),
            'fresh_private_build_output_required')
    require(digest(args.source) == args.source_sha256, 'source_hash_mismatch')
    output.mkdir(parents=True, mode=0o700)
    start = time.monotonic()
    def progress(value):
        print(json.dumps({**value, 'seconds': time.monotonic()-start}), flush=True)
    with TTCollection(args.source, lazy=True) as collection:
        original = collection.fonts[args.face]
        table = HVGL(original.reader['hvgl'], original.reader['hvpm'] if 'hvpm' in original else None)
        source = Source(table, args.gid, batch_size=256); source(np.zeros((1, 3)))
        if args.import_cells:
            fields = load(args.import_cells, source.ops)
            # These are build/refinement probes, not final acceptance holdouts.
            probes = np.r_[np.asarray(list(product((0., .5, 1.), repeat=3))),
                           np.random.default_rng(2026110423).uniform(0, 1, (64, 3))]
            for i, cell in enumerate(fields.cells):
                model = cell.model(source.ops); points = model.from_local(probes)
                extra = source.local_probes(cell.bounds)
                if len(extra):
                    points = np.r_[points, extra]
                cell.error = float(source.errors(model.values(points), source(points)).max())
                if i % 128 == 0:
                    progress(dict(stage='recheck_imported_fields', cell=i, error=cell.error))
        else:
            fields = refine(source, max_cells=args.max_cells, progress=progress)
        fields.save(output/'cells.npz')
        report = dict(gid=args.gid, source_sha256=args.source_sha256, face=args.face,
            cells=len(fields.cells), max_source_field_probe_error=fields.maximum_error,
            refinement_budget=fields.budget, limit=LIMIT, source_samples=source.count,
            production_accepted=False, native_verification='NOT_RUN', full_font=False)
        (output/'build.json').write_text(json.dumps(report, indent=2))
        require(fields.maximum_error <= LIMIT, 'source_field_probe_failed_before_build')
        if args.import_parameters:
            with np.load(args.import_parameters, allow_pickle=False) as archive:
                parameters = SparseParameters(archive['supports'], archive['coefficients'], len(archive['supports']))
        else:
            parameters = fit(lambda points: source.components(points)[1], args.parameter_level, progress=progress)
        ramps = encode_clamp_ramps(parameters, args.ramps)
        np.savez_compressed(output/'parameters.npz', supports=parameters.supports, coefficients=parameters.coefficients)
        report.update(hidden_axes=ramps.parameter_count*ramps.ramps, parameter_regions=len(ramps.supports),
                      parameter_training_nodes=parameters.training_nodes)
        progress(dict(stage='serialize', **report))
        make_fixture(output/'template.ttc')
        with TTCollection(output/'template.ttc') as templates:
            font = build(templates.fonts[0], original, args.gid, fields, ramps, source)
            font.save(output/'candidate.otf')
            report['encoding'] = font.joint_encoding_evidence
        report.update(candidate_sha256=digest(output/'candidate.otf'),
            candidate_bytes=(output/'candidate.otf').stat().st_size, seconds=time.monotonic()-start,
            code_sha256={p.name: digest(p) for p in
                [Path(__file__).resolve(), *[Path(__file__).resolve().parents[1]/'tools'/name for name in
                    ('joint_cells.py', 'joint_polynomial.py', 'projection_factorization.py',
                     'sparse_projection.py', 'joint_projection_font.py', 'cff2_geometry.py', 'cff2_subroutines.py')]]})
        require(digest(args.source) == args.source_sha256, 'source_changed_during_build')
        (output/'build.json').write_text(json.dumps(report, indent=2, allow_nan=False))
        progress(report)
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--gid', type=int, required=True)
    parser.add_argument('--face', type=int, default=0)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--max-cells', type=int, default=4096)
    parser.add_argument('--parameter-level', type=int, default=14)
    parser.add_argument('--ramps', type=int, default=4)
    parser.add_argument('--import-cells', type=Path)
    parser.add_argument('--import-parameters', type=Path)
    run(parser.parse_args())
