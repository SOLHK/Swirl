"""Serialize a selected-glyph atlas as an OpenType/CFF2 probe using avar2.

Physical fvar axes and the decoded avar segment dictionaries are retained.
This is a joint post-avar research compiler, not a raw-record mapping repair:
duplicate source avar records cannot survive the fontTools dictionary, and
segment-map conformance / original user-coordinate parity require a separate
audit (platform/audit_joint_axis_contract.py).
Hidden computational axes carry avar2 clamp ramps; rvrn selects variable CFF2
patches using Format-1 conditions. This is an explicitly labelled diagnostic
font, not a full-font conversion or an installation/delivery artifact.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.featureVars import buildGSUB, buildSubstitutionLookups, addFeatureVariationsRaw
from fontTools.otlLib.builder import buildStatTable

import cff2_geometry as geometry
from joint_polynomial import TAGS, PolynomialBox
from sparse_projection import encode_clamp_ramps


@dataclass
class LocalizedBox:
    """Retain one source coefficient array; materialize one output glyph at a time."""
    box: object
    operators: tuple
    axis_tags: tuple
    count: int
    ramps: int
    constants: np.ndarray
    localize: bool
    evidence: dict = field(default_factory=lambda:dict(sampled_geometry_passed=True,
        production_accepted=False,scope='component_fields_only_composed_native_acceptance_required'))

    @property
    def supports(self):
        return ([{}]+[{tag:(lo,lo if hi<=0 else hi,hi)}
            for tag,(lo,hi) in zip(TAGS,self.box.bounds)]
            +[{tag:triple} for tag,constant in zip(self.axis_tags[3:],self.constants)
              if not np.isfinite(constant) for triple in ((-1,-1,0),(0,1,1))])

    def materialize(self):
        width=sum(n for _,n in self.operators)
        coefficients=self.box.coefficients.reshape(4,4,4,self.count+1,width)
        baseline=coefficients[...,0,:]+.5*coefficients[...,1:,:].sum(axis=3)
        directions=[coefficients[...,k+1,:]/(2*self.ramps) for k in range(self.count)]
        factors={self.axis_tags[3+k*self.ramps+j]:directions[k]
                 for k in range(self.count) for j in range(self.ramps)}
        if self.localize:
            baseline=np.floor(baseline*65536+.5)/65536
            for tag,constant in zip(self.axis_tags[3:],self.constants):
                if np.isfinite(constant):
                    baseline+=np.floor(constant*factors.pop(tag)*65536+.5)/65536
        return PolynomialBox(self.box.bounds,self.operators,baseline,self.evidence,
                             self.axis_tags,factors,True)

    def _program(self,vsindex,expression_pool=None):
        return self.materialize()._program(vsindex,expression_pool)

    def charstring(self,vsindex):
        return self.materialize().charstring(vsindex)


def copy_metric_variations(source, candidate, tag, source_name, source_gid, hidden):
    if tag not in source:
        return
    table = copy.deepcopy(source[tag])
    primary = 'AdvWidthMap' if tag == 'HVAR' else 'AdvHeightMap'
    names = (primary, 'LsbMap', 'RsbMap') if tag == 'HVAR' else (
        primary, 'TsbMap', 'BsbMap', 'VOrgMap')
    for name in names:
        mapping = getattr(table.table, name, None)
        if mapping is None and name != primary:
            continue
        index = source_gid if mapping is None else mapping.mapping[source_name]
        replacement = otTables.VarIdxMap()
        replacement.mapping = dict.fromkeys(candidate.getGlyphOrder(), index)
        setattr(table.table, name, replacement)
    for region in table.table.VarStore.VarRegionList.Region:
        for _ in hidden:
            axis = otTables.VarRegionAxis()
            axis.StartCoord = axis.PeakCoord = axis.EndCoord = 0.
            region.VarRegionAxis.append(axis)
    table.table.VarStore.VarRegionList.RegionAxisCount += len(hidden)
    candidate[tag] = table


def build(source, source_gid, atlas, parameters, *, ramps=4, share_expressions=True,
          localize_clamps=True, eager_fields=False):
    """Encoding gate covers component fields only; native acceptance is separate."""
    require = geometry.require
    require(tuple(a.axisTag for a in source['fvar'].axes) == TAGS,
            'original_physical_WDTH_wght_HGHT_order_required')
    require(type(source_gid) is int and 0 <= source_gid < len(source.getGlyphOrder()),
            'invalid_projection_source_gid')
    require(8 <= len(atlas.boxes) <= 65532, 'projection_patch_glyph_capacity_exceeded')
    proof = atlas.evidence.get('component_holdout', {})
    require(atlas.evidence['max_refinement_error'] <= geometry.LIMIT
            and proof.get('holdouts_disjoint') is True
            and proof.get('max_envelope_error', float('inf')) <= geometry.LIMIT,
            'unverified_projection_component_fields')
    clamp = encode_clamp_ramps(parameters, ramps)
    count = clamp.parameter_count
    ops = atlas.boxes[0].operators
    require(len(ops) % (count+1) == 0, 'projection_component_operator_count_mismatch')
    base_ops = ops[:len(ops)//(count+1)]
    require(ops == base_ops*(count+1), 'projection_component_topology_mismatch')
    width = sum(n for _, n in base_ops)
    hidden = tuple(f'H{i:03X}' for i in range(count*ramps))
    require(len(hidden) <= 4096 and not set(hidden).intersection(TAGS),
            'projection_hidden_axis_tag_capacity_exceeded')
    tags = TAGS+hidden
    order = ['.notdef', 'space', 'probe']+[f'box{i}' for i in range(len(atlas.boxes))]
    source_name = source.getGlyphOrder()[source_gid]
    builder = FontBuilder(source['head'].unitsPerEm, isTTF=False)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({32: 'space', 65: 'probe'})
    builder.setupHorizontalMetrics(dict.fromkeys(order, source['hmtx'].metrics[source_name]))
    builder.setupHorizontalHeader(ascent=source['hhea'].ascent, descent=source['hhea'].descent)
    if 'vmtx' in source:
        builder.setupVerticalMetrics(dict.fromkeys(order, source['vmtx'].metrics[source_name]))
        builder.setupVerticalHeader(ascent=source['vhea'].ascent, descent=source['vhea'].descent)
    builder.setupNameTable(dict(familyName='Swirl Joint Projection Research Probe', styleName='Regular',
                               uniqueFontIdentifier='SwirlJointProjectionResearchProbe-1',
                               fullName='Swirl Joint Projection Research Probe',
                               psName='SwirlJointProjectionResearchProbe', version='Version 1.000'))
    builder.setupOS2(sTypoAscender=source['hhea'].ascent, sTypoDescender=source['hhea'].descent,
                     usWinAscent=max(0, source['hhea'].ascent), usWinDescent=max(0, -source['hhea'].descent))
    builder.setupPost()
    template = builder.font
    template['fvar'] = copy.deepcopy(source['fvar'])
    template['fvar'].instances = []
    for axis in template['fvar'].axes:
        axis.axisNameID = template['name'].addName(axis.axisTag)
    for i, tag in enumerate(hidden):
        axis = Axis()
        axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue = tag, -1., 0., 1.
        axis.flags, axis.axisNameID = 1, template['name'].addName('Projection ramp '+str(i))
        template['fvar'].axes.append(axis)
    avar = newTable('avar')
    avar.majorVersion, avar.minorVersion = (2 if count else 1), 0
    avar.segments = copy.deepcopy(source['avar'].segments) if 'avar' in source else {
        tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in TAGS}
    avar.segments.update({tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in hidden})
    avar.table = otTables.avar()
    avar.table.Reserved = 0
    if count:
        avar.table.VarStore, avar.table.VarIdxMap = clamp.var_store(TAGS, hidden)
    template['avar'] = avar
    for tag in ('HVAR', 'VVAR'):
        copy_metric_variations(source, template, tag, source_name, source_gid, hidden)
    empty = geometry.OutlineModel(tags, (), [{}], np.zeros((1, 0)), {'sampled_geometry_passed': True})
    models = dict.fromkeys(order, empty)
    certificates, active_counts = 0, []
    for index, box in enumerate(atlas.boxes):
        require(box.operators == ops, 'projection_patch_topology_changed')
        constants=clamp.constant_axes(box.bounds) if localize_clamps else np.full(len(hidden),np.nan)
        certificates+=int(np.isfinite(constants).sum())
        active_counts.append(int((~np.isfinite(constants)).sum()))
        model=LocalizedBox(box,base_ops,tags,count,ramps,constants,localize_clamps)
        models[f'box{index}']=model.materialize() if eager_fields else model
    models['probe'] = models['box0']
    result = geometry.install(template, models, release_programs=True, share_expressions=share_expressions)
    if share_expressions:
        require(result._swirl_expression_pool_report['glyphs_reaching_operation_limit'] == 0,
                'cff2_HarfBuzz_14_6_interpreter_operation_limit_exceeded:maximum='
                +str(result._swirl_expression_pool_report['maximum_interpreter_operations']))
    result['GSUB'] = buildGSUB()
    substitutions = [(('probe', f'box{i}'),) for i in range(len(atlas.boxes))]
    lookups = buildSubstitutionLookups(result['GSUB'].table, substitutions, False)
    conditions = [({tag: tuple(b) for tag, b in zip(TAGS, box.bounds)}, [lookups[sub]])
                  for box, sub in zip(atlas.boxes, substitutions)]
    addFeatureVariationsRaw(result, result['GSUB'].table, conditions)
    buildStatTable(result, [dict(tag=a.axisTag, name=a.axisNameID, ordering=i)
                           for i, a in enumerate(result['fvar'].axes)], elidedFallbackName=2)
    result._swirl_projection_receipt = dict(scope='selected_source_glyph_research_probe',
        source_gid=source_gid, physical_axes=list(TAGS), computational_axes=len(hidden),
        patch_glyphs=len(atlas.boxes), avar2_regions=len(clamp.supports),
        raw_parameter_regions=clamp.source_region_count, production_accepted=False,
        eager_field_materialization=eager_fields,
        maximum_operand_stack=max(m.evidence.get('maximum_operand_stack',0) for m in models.values()),
        certified_constant_ramps=certificates, maximum_active_ramps=max(active_counts),
        minimum_active_ramps=min(active_counts), clamp_certificate_padding=2/16384,
        serialized_native_verification='NOT_RUN',
        expression_pool=getattr(result, '_swirl_expression_pool_report', None))
    return result
