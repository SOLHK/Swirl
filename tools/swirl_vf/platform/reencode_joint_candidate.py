#!/usr/bin/env python3
"""Lossless polynomial-basis change of an already built private joint font.

No source/refinement/acceptance samples enter this transformation. It reuses
the candidate's metrics, avar2 clamps and GSUB regions, adds simultaneous axis
copies, and chooses tensor or axis-power encoding within CFF2 region capacity.
The output still requires a new independent native acceptance run.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from fontTools.ttLib import TTCollection, TTFont
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import cff2_geometry as g
from hvf import HVGL
from projection_factorization import ProjectionSource
from joint_cells import load
from joint_hoi import HOIPolynomialBox, HOIAxisPowerBox, add_axis_copies, COPIES


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@dataclass
class EncodedCell:
    cell: object
    source: object
    axis_tags: tuple
    factor_tags: tuple
    mode: str = 'axis'
    maximum_stack: int = 0

    @property
    def evidence(self):
        return dict(sampled_geometry_passed=np.isfinite(self.cell.error) and self.cell.error <= g.LIMIT,
                    production_accepted=False, scope='previous_build_field_probes_only')

    def model(self):
        width = sum(n for _, n in self.source.base_ops)
        fields = self.cell.model(self.source.ops).coefficients.reshape(4, 4, 4, self.source.factors+1, width)
        ramps = len(self.factor_tags)//self.source.factors
        directions = [fields[..., i+1, :]/(2*ramps) for i in range(self.source.factors)]
        cls = HOIPolynomialBox if self.mode == 'tensor' else HOIAxisPowerBox
        return cls(self.cell.bounds, self.source.base_ops, fields[..., 0, :]+fields[..., 1:, :].sum(axis=3)/2,
                   self.evidence, self.axis_tags,
                   {tag: directions[i//ramps] for i, tag in enumerate(self.factor_tags)}, True)

    @property
    def supports(self):
        return self.model().supports

    @property
    def operators(self):
        return self.source.base_ops

    def _program(self, vsindex, expression_pool=None):
        model = self.model(); result = model._program(vsindex, expression_pool)
        self.maximum_stack = model.evidence['maximum_operand_stack']
        return result

    def charstring(self, vsindex):
        model = self.model(); result = model.charstring(vsindex)
        self.maximum_stack = model.evidence['maximum_operand_stack']
        return result


def run(args):
    output = args.private_output.resolve()
    g.require(not output.exists() and not output.is_relative_to(Path(__file__).resolve().parents[3]),
              'fresh_private_reencoding_output_required')
    g.require(digest(args.source) == args.source_sha256, 'source_digest_mismatch')
    g.require(1024 <= args.region_budget <= 65535, 'invalid_HOI_region_budget')
    output.mkdir(parents=True, mode=0o700); started = time.monotonic()
    provenance = {p.name: digest(p) for p in (Path(__file__).resolve(),
        *[Path(__file__).resolve().parents[1]/'tools'/name for name in
          ('joint_hoi.py', 'joint_polynomial.py', 'cff2_geometry.py',
           'cff2_subroutines.py', 'cff2_expression_pool.py')])}
    input_hash = digest(args.candidate)
    with TTCollection(args.source, lazy=True) as collection, TTFont(args.candidate, lazy=True) as font:
        original = collection.fonts[args.face]
        table = HVGL(original.reader['hvgl'], original.reader['hvpm'] if 'hvpm' in original else None)
        source = ProjectionSource(table, args.gid); source(np.zeros((1, 3)))
        fields = load(args.cells, source.ops)
        g.require(fields.maximum_error <= g.LIMIT, 'unaccepted_build_fields')
        order = font.getGlyphOrder()
        g.require(order == ['.notdef', 'space', 'probe']+[f'joint{i}' for i in range(len(fields.cells))],
                  'candidate_cell_order_mismatch')
        factor_tags = tuple(a.axisTag for a in font['fvar'].axes[3:])
        g.require(len(factor_tags) % source.factors == 0, 'candidate_parameter_axis_mismatch')
        tags = add_axis_copies(font)
        # Avoid retaining the previous large CharString table during assembly.
        del font['CFF2']; font.setGlyphOrder(order)
        models = [EncodedCell(cell, source, tags, factor_tags) for cell in fields.cells]
        key = lambda support: tuple(sorted(support.items()))
        # Reserve the compact per-axis basis first. Tensor regions are optional.
        reserved = {key(s) for model in models for s in model.supports[1:]}
        g.require(len(reserved) <= args.region_budget, 'HOI_axis_basis_exceeds_region_budget')
        for model in models:
            model.mode = 'tensor'
            extra = {key(s) for s in model.supports[1:]}-reserved
            if len(reserved)+len(extra) > args.region_budget:
                model.mode = 'axis'
            else:
                reserved.update(extra)
        empty = g.OutlineModel(tags, (), [{}], np.zeros((1, 0)), {'sampled_geometry_passed': True})
        mapping = {'.notdef': empty, 'space': empty, 'probe': models[0]}
        mapping.update({f'joint{i}': m for i, m in enumerate(models)})
        report = dict(gid=args.gid, source_sha256=args.source_sha256, input_sha256=input_hash,
                      scope='polynomial_basis_reencoding', refitted_samples=0,
                      tensor_cells=sum(m.mode == 'tensor' for m in models),
                      axis_power_cells=sum(m.mode == 'axis' for m in models),
                      share_expressions=args.share_expressions,
                      reserved_regions=len(reserved), production_accepted=False, code_sha256=provenance)
        print(json.dumps(report), flush=True)
        candidate = g.install(font, mapping, release_programs=True, share_expressions=args.share_expressions)
        candidate.save(output/'candidate.otf')
        report.update(candidate_sha256=digest(output/'candidate.otf'),
            candidate_bytes=(output/'candidate.otf').stat().st_size,
            maximum_operand_stack=max(m.maximum_stack for m in models),
            expression_pool=getattr(candidate, '_swirl_expression_pool_report', None),
            actual_regions=len(candidate['CFF2'].cff.topDictIndex[0].VarStore.otVarStore.VarRegionList.Region),
            seconds=time.monotonic()-started)
    g.require(digest(args.candidate) == input_hash and digest(args.source) == args.source_sha256,
              'reencoding_input_changed')
    (output/'report.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('source', 'candidate', 'cells', 'private-output'):
        parser.add_argument('--'+argument, type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--gid', type=int, required=True)
    parser.add_argument('--face', type=int, default=0)
    parser.add_argument('--region-budget', type=int, default=64000)
    parser.add_argument('--share-expressions', action='store_true')
    run(parser.parse_args())
