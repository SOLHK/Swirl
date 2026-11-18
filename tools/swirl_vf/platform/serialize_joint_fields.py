#!/usr/bin/env python3
"""Serialize a completed private field-recheck checkpoint directly as HOI CFF2.

No uncompressed intermediate font is required. The checkpoint's source identity,
cell count and error envelope must agree with the numerical archive. Both input
archives and the source are hash-bound for the operation. This does not turn
field probes into native acceptance; verify_joint_candidate is still required.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
from fontTools.ttLib import TTCollection
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import cff2_geometry as g
from hvf import HVGL
from projection_factorization import ProjectionSource
from joint_cells import load
from joint_projection_font import build
from sparse_projection import SparseParameters, encode_clamp_ramps
from test_coretext_extract import make_fixture
from build_joint_candidate import digest


def run(args):
    output = args.private_output.resolve(); inputs = args.build_directory.resolve()
    g.require(not output.exists() and not output.is_relative_to(Path(__file__).resolve().parents[3]),
              'fresh_private_serialization_output_required')
    receipt = json.loads((inputs/'build.json').read_text())
    source_sha = digest(args.source)
    g.require(source_sha == args.source_sha256 == receipt['source_sha256'], 'field_checkpoint_source_mismatch')
    g.require(receipt['limit'] == g.LIMIT and receipt['max_source_field_probe_error'] <= g.LIMIT,
              'field_checkpoint_error_limit_not_met')
    hashes = {name: digest(inputs/name) for name in ('cells.npz', 'parameters.npz')}
    code = {p.name: digest(p) for p in [Path(__file__).resolve(), *[
        Path(__file__).resolve().parents[1]/'tools'/name for name in ('joint_projection_font.py',
        'joint_hoi.py', 'joint_polynomial.py', 'sparse_projection.py', 'cff2_geometry.py',
        'cff2_expression_pool.py', 'cff2_subroutines.py')]]}
    output.mkdir(parents=True, mode=0o700); started = time.monotonic()
    make_fixture(output/'template.ttc')
    with TTCollection(args.source, lazy=True) as collection, TTCollection(output/'template.ttc') as templates:
        original = collection.fonts[receipt['face']]
        table = HVGL(original.reader['hvgl'], original.reader['hvpm'] if 'hvpm' in original else None)
        source = ProjectionSource(table, receipt['gid']); source(np.zeros((1, 3)))
        fields = load(inputs/'cells.npz', source.ops)
        g.require(len(fields.cells) == receipt['cells'] and
                  fields.maximum_error == receipt['max_source_field_probe_error'], 'field_checkpoint_archive_mismatch')
        with np.load(inputs/'parameters.npz', allow_pickle=False) as data:
            parameters = SparseParameters(data['supports'], data['coefficients'], len(data['supports']))
        ramps = encode_clamp_ramps(parameters, args.ramps)
        report = dict(gid=receipt['gid'], face=receipt['face'], source_sha256=source_sha,
            input_archives_sha256=hashes, code_sha256=code, cells=len(fields.cells),
            max_source_field_probe_error=fields.maximum_error, parameter_regions=len(ramps.supports),
            limit=g.LIMIT, native_verification='NOT_RUN', production_accepted=False,
            refitted_samples=0, scope='direct_serialization_of_rechecked_source_fields')
        print(json.dumps(report), flush=True)
        font = build(templates.fonts[0], original, receipt['gid'], fields, ramps, source,
                     encoding='hoi', share_expressions=True)
        font.save(output/'candidate.otf')
        report.update(candidate_sha256=digest(output/'candidate.otf'),
                      candidate_bytes=(output/'candidate.otf').stat().st_size,
                      encoding=font.joint_encoding_evidence, seconds=time.monotonic()-started)
    g.require(digest(args.source) == source_sha and
              all(digest(inputs/name) == value for name, value in hashes.items()), 'serialization_input_changed')
    (output/'report.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'build-directory', 'private-output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--ramps', type=int, default=4)
    run(parser.parse_args())
