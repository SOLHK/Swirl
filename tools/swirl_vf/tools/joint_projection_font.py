"""Serialize local projection fields as an experimental, standard OpenType font.

Three physical axes retain the source ranges and first-stage avar mapping.
Hidden axes contain simultaneous avar2 ramp outputs. Required FeatureVariations
select one local CFF2 polynomial glyph. This diagnostic font covers one source
glyph through ordinary shaping; it is not a full-font conversion or release.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import numpy as np
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.builder import buildVarIdxMap
from fontTools.varLib.featureVars import buildGSUB, buildSubstitutionLookups, addFeatureVariationsRaw

import cff2_geometry as geometry
from joint_polynomial import PolynomialBox, TAGS


@dataclass
class LocalProjectionModel:
    cell: object
    field_operators: tuple
    operators: tuple
    axis_tags: tuple
    factor_count: int
    ramps: int
    maximum_stack: int = 0
    encoding: str = 'horner'

    @property
    def evidence(self):
        return dict(sampled_geometry_passed=np.isfinite(self.cell.error) and self.cell.error <= geometry.LIMIT,
                    scope='local_source_field_probe_only', production_accepted=False)

    @property
    def supports(self):
        if self.encoding != 'horner':
            return self.model().supports
        return ([{}]+[{tag: (lo, lo if hi <= 0 else hi, hi)}
                      for tag, (lo, hi) in zip(TAGS, self.cell.bounds)] +
                [{tag: triple} for tag in self.axis_tags[3:]
                 for triple in ((-1, -1, 0), (0, 1, 1))])

    def model(self):
        # Materialize only the current glyph; no dense per-ramp copies persist
        # across thousands of variants. A direction's ramps share one array.
        width = sum(n for _, n in self.operators)
        values = self.cell.model(self.field_operators).coefficients.reshape(4, 4, 4, self.factor_count+1, width)
        base = values[..., 0, :]+values[..., 1:, :].sum(axis=3)/2
        factors = {}
        for factor in range(self.factor_count):
            direction = values[..., factor+1, :]/(2*self.ramps)
            for ramp in range(self.ramps):
                factors[self.axis_tags[3+factor*self.ramps+ramp]] = direction
        cls = PolynomialBox
        if self.encoding != 'horner':
            from joint_hoi import HOIPolynomialBox, HOIAxisPowerBox
            cls = HOIPolynomialBox if self.encoding == 'hoi' else HOIAxisPowerBox
        return cls(self.cell.bounds, self.operators, base, self.evidence, self.axis_tags, factors, True)

    def _program(self, vsindex, expression_pool=None):
        model = self.model(); result = model._program(vsindex, expression_pool)
        self.maximum_stack = model.evidence['maximum_operand_stack']
        return result

    def charstring(self, vsindex):
        model = self.model()
        result = model.charstring(vsindex)
        self.maximum_stack = model.evidence['maximum_operand_stack']
        return result


def copy_metric_table(source, candidate, source_gid, tag, fields, hidden_count):
    if tag not in source:
        if tag in candidate:
            del candidate[tag]
        return
    table = copy.deepcopy(source[tag]); source_name = source.getGlyphOrder()[source_gid]
    order = candidate.getGlyphOrder()
    for field in fields:
        mapping = getattr(table.table, field, None)
        if mapping is None and field not in ('AdvWidthMap', 'AdvHeightMap'):
            continue
        index = source_gid if mapping is None else mapping.mapping[source_name]
        setattr(table.table, field, buildVarIdxMap([index]*len(order), order))
    for region in table.table.VarStore.VarRegionList.Region:
        for _ in range(hidden_count):
            axis = otTables.VarRegionAxis(); axis.StartCoord = axis.PeakCoord = axis.EndCoord = 0.
            region.VarRegionAxis.append(axis)
    table.table.VarStore.VarRegionList.RegionAxisCount += hidden_count
    candidate[tag] = table


def build(template, source, source_gid, fields, ramps, field_source, *, encoding='horner', share_expressions=False):
    geometry.require(encoding in ('horner', 'hoi'), 'unknown_joint_polynomial_encoding')
    geometry.require(tuple(a.axisTag for a in source['fvar'].axes) == TAGS,
                     'original_three_physical_axes_required')
    geometry.require(fields.operators == field_source.ops and field_source.factors == ramps.parameter_count,
                     'projection_field_parameter_topology_mismatch')
    geometry.require(0 < len(fields.cells) <= 32768 and fields.maximum_error <= geometry.LIMIT,
                     'source_field_probe_failed_before_serialization')
    font = copy.deepcopy(template)
    hidden = tuple(f'H{i:03X}' for i in range(ramps.parameter_count*ramps.ramps))
    geometry.require(len(hidden) <= 4096, 'hidden_axis_tag_capacity')
    tags = TAGS+hidden
    order = ['.notdef', 'space', 'probe']+[f'joint{i}' for i in range(len(fields.cells))]
    geometry.require(font.getGlyphOrder() == ['.notdef', 'space', 'probe'], 'three_glyph_research_template_required')
    font.setGlyphOrder(order)
    font['head'].unitsPerEm = source['head'].unitsPerEm
    font['fvar'] = copy.deepcopy(source['fvar']); font['fvar'].instances = []
    for axis in font['fvar'].axes:
        axis.axisNameID = font['name'].addName(axis.axisTag)
    for tag in hidden:
        axis = Axis(); axis.axisTag = tag; axis.minValue = -1.; axis.defaultValue = 0.; axis.maxValue = 1.
        axis.flags = 1; axis.axisNameID = font['name'].addName('Joint projection '+tag)
        font['fvar'].axes.append(axis)
    for tag in ('GSUB', 'GPOS', 'trak'):
        if tag in font:
            del font[tag]
    name = source.getGlyphOrder()[source_gid]
    font['hmtx'].metrics = dict.fromkeys(order, source['hmtx'].metrics[name])
    font['vmtx'].metrics = dict.fromkeys(order, source['vmtx'].metrics[name])
    copy_metric_table(source, font, source_gid, 'HVAR', ('AdvWidthMap', 'LsbMap', 'RsbMap'), len(hidden))
    copy_metric_table(source, font, source_gid, 'VVAR', ('AdvHeightMap', 'TsbMap', 'BsbMap', 'VOrgMap'), len(hidden))
    if 'VORG' in source:
        font['VORG'] = newTable('VORG'); font['VORG'].majorVersion = 1; font['VORG'].minorVersion = 0
        font['VORG'].defaultVertOriginY = source['VORG'][name]; font['VORG'].VOriginRecords = {}
    avar = newTable('avar'); avar.majorVersion = 2; avar.minorVersion = 0
    avar.segments = copy.deepcopy(source['avar'].segments)
    avar.segments.update({tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in hidden})
    avar.table = otTables.avar(); avar.table.Reserved = 0
    avar.table.VarStore, avar.table.VarIdxMap = ramps.var_store(TAGS, hidden)
    font['avar'] = avar
    if encoding == 'hoi':
        from joint_hoi import add_axis_copies
        tags = add_axis_copies(font)
    empty = geometry.OutlineModel(tags, (), [{}], np.zeros((1, 0)), {'sampled_geometry_passed': True})
    models = dict.fromkeys(order, empty)
    for i, cell in enumerate(fields.cells):
        models[f'joint{i}'] = LocalProjectionModel(cell, fields.operators, field_source.base_ops,
                                                  tags, field_source.factors, ramps.ramps, encoding=encoding)
    if encoding == 'hoi':
        leaves = [models[f'joint{i}'] for i in range(len(fields.cells))]
        key = lambda s: tuple(sorted(s.items()))
        for model in leaves:
            model.encoding = 'hoi-axis'
        reserved = {key(s) for model in leaves for s in model.supports[1:]}
        geometry.require(len(reserved) <= 64000, 'joint_HOI_axis_region_budget_exceeded')
        for model in leaves:
            model.encoding = 'hoi'
            extra = {key(s) for s in model.supports[1:]}-reserved
            if len(reserved)+len(extra) > 64000:
                model.encoding = 'hoi-axis'
            else:
                reserved.update(extra)
    models['probe'] = models['joint0']
    font = geometry.install(font, models, release_programs=True, share_expressions=share_expressions)
    font['GSUB'] = buildGSUB()
    substitutions = [(('probe', f'joint{i}'),) for i in range(len(fields.cells))]
    lookups = buildSubstitutionLookups(font['GSUB'].table, substitutions, False)
    conditions = [({tag: tuple(b) for tag, b in zip(TAGS, cell.bounds)}, [lookups[sub]])
                  for cell, sub in zip(fields.cells, substitutions)]
    addFeatureVariationsRaw(font, font['GSUB'].table, conditions)
    top = font['CFF2'].cff.topDictIndex[0]
    font.joint_encoding_evidence = dict(
        maximum_operand_stack=max(getattr(model, 'maximum_stack', 0) for model in models.values()),
        cff2_regions=len(top.VarStore.otVarStore.VarRegionList.Region),
        local_glyphs=len(fields.cells), global_subroutines=len(font['CFF2'].cff.GlobalSubrs),
        polynomial_encoding=encoding, share_expressions=share_expressions,
        expression_pool=getattr(font, '_swirl_expression_pool_report', None))
    return font
