"""Unrounded CFF2 geometry models with a fixed source-unit error contract.

This is a geometry backend, not a completed font converter. It preserves
fractional coordinates through 16.16 CharString operands instead of forcing
every default point onto the glyf integer lattice. Quadratics are elevated
exactly to cubics. Every source GID must have a verified model before assembly.
Metrics, layout, user-coordinate mapping and native acceptance remain separate.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import math

import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.psCharStrings import T2CharString
from fontTools.misc.roundTools import otRound
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import newTable
from fontTools.varLib.builder import buildVarData, buildVarRegionList, buildVarStore
from fontTools.cffLib import VarStoreData
from fontTools.varLib.models import VariationModel, supportScalar

LIMIT = 1 / 32


class CFF2GeometryError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise CFF2GeometryError(reason)


def operands(commands):
    """Use deterministic exact degree elevation; no cu2qu or point rounding."""
    pen = T2CharStringPen(None, None, roundTolerance=0, CFF2=True)
    opened = False
    for command in commands:
        require(type(command) in (list, tuple) and command, 'invalid_source_command')
        operator, values = command[0], command[1:]
        sizes = {'moveTo': 2, 'lineTo': 2, 'qCurveTo': 4, 'curveTo': 6, 'closePath': 0}
        require(operator in sizes and len(values) == sizes[operator], 'unsupported_source_command')
        require(all(type(v) in (int, float) and math.isfinite(v) for v in values), 'nonfinite_source_point')
        if operator == 'moveTo':
            require(not opened, 'unclosed_source_contour')
            opened = True
        else:
            require(opened, 'source_command_outside_contour')
        getattr(pen, operator)(*[(values[i], values[i+1]) for i in range(0, len(values), 2)])
        if operator == 'closePath':
            opened = False
    require(not opened, 'unclosed_source_contour')
    program = pen.getCharString(optimize=False).program
    operators, numbers, count = [], [], 0
    for token in program:
        if isinstance(token, str):
            operators.append((token, count)); count = 0
        else:
            numbers.append(float(token)); count += 1
    require(count == 0, 'unfinished_charstring_operands')
    return tuple(operators), np.asarray(numbers, dtype=np.float64)


def source_commands(glyph):
    """Decompose implied quadratic points into the native oracle's vocabulary."""
    class Recorder(BasePen):
        def __init__(self):
            super().__init__(None)
            self.commands = []

        def _moveTo(self, point): self.commands.append(['moveTo', *point])
        def _lineTo(self, point): self.commands.append(['lineTo', *point])
        def _curveToOne(self, a, b, c): self.commands.append(['curveTo', *a, *b, *c])
        def _qCurveToOne(self, a, b): self.commands.append(['qCurveTo', *a, *b])
        def _closePath(self): self.commands.append(['closePath'])
        def _endPath(self): raise CFF2GeometryError('open_source_contour')
    pen = Recorder()
    glyph.draw(pen)
    return pen.commands


def control_points(operators, values):
    current = np.zeros(2)
    points = []
    offset = 0
    for operator, count in operators:
        require(operator in ('rmoveto', 'rlineto', 'rrcurveto') and
                count == (6 if operator == 'rrcurveto' else 2), 'unsupported_cff2_operator')
        for i in range(0, count, 2):
            current = current + values[offset+i:offset+i+2]
            points.append(current.copy())
        offset += count
    require(offset == len(values), 'charstring_operand_count_mismatch')
    return np.asarray(points, dtype=float).reshape(-1, 2)


def fixed(value):
    require(math.isfinite(value), 'nonfinite_cff2_coefficient')
    encoded = otRound(value * 65536) / 65536
    require(-32768 <= encoded < 32768, 'cff2_fixed_coefficient_overflow')
    return encoded


@dataclass
class OutlineModel:
    axis_tags: tuple
    operators: tuple
    supports: list
    deltas: np.ndarray
    evidence: dict

    def evaluate(self, location):
        scalars = np.asarray([supportScalar(location, support) for support in self.supports])
        return control_points(self.operators, scalars @ self.deltas)

    def charstring(self, vsindex):
        regions = len(self.supports) - 1
        # A genuinely empty glyph needs no variation-state instruction. Keeping
        # its CharString empty also permits a structural native empty-path proof.
        program = [vsindex, 'vsindex'] if regions and self.operators else []
        column = 0
        for operator, count in self.operators:
            for argument in range(count):
                values = self.deltas[:, column]
                program.append(float(values[0]))
                if regions and np.any(values[1:]):
                    require(argument + regions + 2 <= 513, 'cff2_blend_operand_stack_overflow')
                    program.extend(float(value) for value in values[1:])
                    program.extend((1, 'blend'))
                column += 1
            program.append(operator)
        return T2CharString(program=program)


@dataclass
class FactoredOutlineModel:
    """The same fitted function, with products evaluated by nested blends.

    CFF2 permits blended blend operands, but only one vsindex per CharString.
    Select the union of one-axis regions once, and factor each original region
    into its axis factors. This avoids one stack operand per Cartesian region.
    It neither adds samples nor improves an inaccurate interpolation model.
    """
    original: OutlineModel
    supports: list
    coefficients: dict

    @property
    def axis_tags(self): return self.original.axis_tags
    @property
    def operators(self): return self.original.operators
    @property
    def evidence(self): return self.original.evidence

    def evaluate(self, location):
        values = np.zeros(self.original.deltas.shape[1])
        scalars = [1.] + [supportScalar(location, s) for s in self.supports[1:]]
        for indices, row in self.coefficients.items():
            values += math.prod(scalars[i] for i in indices) * row
        return control_points(self.operators, values)

    def charstring(self, vsindex):
        if not self.operators:
            return T2CharString(program=[])
        regions = len(self.supports) - 1
        program = [vsindex, 'vsindex'] if regions else []
        stack = 0

        def push(value):
            nonlocal stack
            program.append(fixed(float(value))); stack += 1
            require(stack <= 513, 'cff2_factored_blend_operand_stack_overflow')

        def expression(rows, axis):
            nonlocal stack
            if not rows:
                push(0); return
            if axis == len(self.axis_tags):
                push(sum(value for _, value in rows)); return
            groups = {}
            for indices, value in rows:
                groups.setdefault(indices[axis], []).append((indices, value))
            expression(groups.get(0, []), axis + 1)
            if not any(index != 0 for index in groups):
                return
            for index in range(1, regions + 1):
                expression(groups.get(index, []), axis + 1)
            push(1); program[-1] = 1  # blend's count is an integer operand.
            program.append('blend'); stack -= regions + 1

        column = 0
        for operator, count in self.operators:
            for _ in range(count):
                rows = [(indices, row[column]) for indices, row in self.coefficients.items()
                        if row[column] != 0]
                expression(rows, 0); column += 1
            require(stack == count, 'cff2_factored_operator_stack_mismatch')
            program.append(operator); stack = 0
        return T2CharString(program=program)


def factor(model):
    """Exact algebraic factorization of already quantized variation deltas."""
    require(isinstance(model, OutlineModel), 'unfactored_outline_model_required')
    # Group factors by fvar axis order to bound stack use during recursion.
    supports, ids = [{}], {}
    for tag in model.axis_tags:
        for support in model.supports:
            if tag in support:
                key = (tag, tuple(support[tag]))
                if key not in ids:
                    ids[key] = len(supports)
                    supports.append({tag: key[1]})
    coefficients = {}
    for support, row in zip(model.supports, model.deltas):
        indices = tuple(ids[(tag, tuple(support[tag]))] if tag in support else 0
                        for tag in model.axis_tags)
        if indices not in coefficients:
            coefficients[indices] = row.copy()
        else:
            coefficients[indices] += row
    return FactoredOutlineModel(model, supports, coefficients)


def compact(model):
    """Remove only regions whose encoded delta is exactly zero for every operand.

    This preserves the already quantized function at every axis location. It
    does not refit a model, discard small deltas, or change its acceptance
    evidence. Ordinary blends avoid the nested-blend incompatibility observed
    in DirectWrite; genuinely dense models still fail the stack limit.
    """
    require(isinstance(model, OutlineModel), 'unfactored_outline_model_required')
    keep = [0] + [index for index in range(1, len(model.supports))
                  if np.any(model.deltas[index] != 0)]
    evidence = copy.deepcopy(model.evidence)
    evidence['lossless_compaction'] = {'input_regions': len(model.supports) - 1,
                                      'output_regions': len(keep) - 1}
    return OutlineModel(model.axis_tags, model.operators,
                        [model.supports[index] for index in keep],
                        model.deltas[keep].copy(), evidence)


def fit(training_commands, training_locations, holdout_commands, holdout_locations, axis_tags):
    require(len(training_commands) == len(training_locations) > 0 and
            len(holdout_commands) == len(holdout_locations) > 0, 'training_and_holdouts_required')
    tags = tuple(axis_tags)
    require(tags and len(tags) == len(set(tags)) and all(type(t) is str and len(t) == 4 for t in tags),
            'invalid_model_axes')
    locations = training_locations + holdout_locations
    require(all(set(p) <= set(tags) and all(type(v) in (int, float) and math.isfinite(v)
            and -1 <= v <= 1 for v in p.values()) for p in locations), 'invalid_model_location')
    # Omitted axes mean normalized zero. Dictionary inequality must not let a
    # default master reappear as a supposedly independent holdout just because
    # the caller spelled its zero-valued axes explicitly (or used -0.0).
    training_keys = {tuple(p.get(tag, 0.) for tag in tags) for p in training_locations}
    require(len(training_keys) == len(training_locations), 'duplicate_training_design_location')
    require(all(tuple(p.get(tag, 0.) for tag in tags) not in training_keys
                for p in holdout_locations), 'holdouts_must_be_independent')
    recordings = [operands(commands) for commands in training_commands + holdout_commands]
    operators = recordings[0][0]
    require(all(ops == operators for ops, _ in recordings), 'source_cubic_topology_changed')
    variation = VariationModel(training_locations, axisOrder=list(tags))
    for support in variation.supports:
        require(all(all(v * 16384 == int(v * 16384) for v in triple) for triple in support.values()),
                'support_not_exactly_F2DOT14')
    # Quantize actual residuals only once to the CFF2 16.16 operand format.
    deltas = variation.getDeltas([values.copy() for _, values in recordings[:len(training_commands)]])
    encoded = np.asarray([[fixed(v) for v in row] for row in deltas])
    evidence = {'limit_source_font_units': LIMIT, 'training_count': len(training_locations),
        'holdout_count': len(holdout_locations), 'max_control_error_source_units': 0.,
        'failures': [], 'serialized_verification': 'NOT_RUN', 'native_verification': 'NOT_RUN',
        'metrics_and_layout_acceptance': 'NOT_ESTABLISHED', 'production_accepted': False}
    model = OutlineModel(tags, operators, variation.supports, encoded, evidence)
    for index, (location, (_, values)) in enumerate(zip(locations, recordings)):
        expected = control_points(operators, values)
        actual = model.evaluate(location)
        error = float(np.linalg.norm(actual-expected, axis=1).max(initial=0))
        evidence['max_control_error_source_units'] = max(error, evidence['max_control_error_source_units'])
        if error > LIMIT:
            evidence['failures'].append({'sample_kind': 'training' if index < len(training_locations)
                else 'holdout', 'location': dict(location), 'error_source_units': error})
    evidence['sampled_geometry_passed'] = not evidence['failures']
    return model


def install(font, models, *, experimental_slice=False, experimental_layout=False, experimental_local=False, experimental_nested=False, release_programs=False, share_expressions=False):
    """Install all modeled GIDs on a detached font; never fill missing models.

    Callers must supply correct CFF2-compatible metrics before serialization.
    This operation cannot certify those metrics or publish a formal candidate.
    """
    order = font.getGlyphOrder()
    require(set(models) == set(order), 'complete_original_GID_model_coverage_required')
    # OpenType 1.9.1 permits this encoding, but our actual Windows Server and
    # Windows 11 controls lose its variable outlines. CoreText/FontTools success
    # cannot admit it to the normal Windows-targeted construction path. Retain
    # an explicit authored-diagnostic route so the native failure stays tested.
    require(experimental_nested or not any(isinstance(model, FactoredOutlineModel)
                                          for model in models.values()),
            'nested_blends_lack_DirectWrite_compatibility')
    require(experimental_slice or all(model.evidence.get('domain_kind') != 'one_dimensional_slice'
                                    for model in models.values()),
            'slice_model_is_not_a_complete_design_space')
    require(experimental_layout or all(model.evidence.get('domain_kind') != 'vertical_layout_variant'
                                     for model in models.values()),
            'layout_variant_requires_verified_GSUB_route')
    require(experimental_local or all(model.evidence.get('domain_kind') != 'local_box_only'
                                    for model in models.values()),
            'local_box_requires_verified_selection')
    tags = tuple(axis.axisTag for axis in font['fvar'].axes)
    require(all(model.axis_tags == tags and model.evidence['sampled_geometry_passed']
                for model in models.values()), 'unaccepted_or_mismatched_outline_model')
    candidate = copy.deepcopy(font)
    for tag in ('glyf', 'loca', 'gvar', 'CFF ', 'CFF2', 'hvgl', 'hvpm', 'cvt ', 'fpgm', 'prep', 'gasp'):
        if tag in candidate:
            del candidate[tag]
    candidate.setGlyphOrder(order)
    builder = FontBuilder(font=candidate, isTTF=False)
    require(type(share_expressions) is bool, 'invalid_shared_expression_policy')
    pool = None
    if share_expressions:
        from cff2_expression_pool import ExpressionPool
        pool = ExpressionPool()
    regions, region_ids, data, data_ids, strings = [], {}, [], {}, {}
    for name in order:
        model = models[name]
        indices = []
        for support in model.supports[1:]:
            key = tuple((tag, tuple(support.get(tag, (0, 0, 0)))) for tag in tags)
            if key not in region_ids:
                # OpenType reserves the high bit of regionCount, despite the
                # uint16 storage type (otvarcommonformats VariationRegionList).
                require(len(regions) < 32767, 'cff2_region_count_overflow')
                region_ids[key] = len(regions); regions.append(support)
            indices.append(region_ids[key])
        key = tuple(indices)
        if key not in data_ids:
            require(len(data) < 65535, 'cff2_vsindex_overflow')
            data_ids[key] = len(data)
            data.append(buildVarData(indices, None, optimize=False))
        if pool is not None:
            require(not model.operators or hasattr(model, '_program'), 'polynomial_model_required_for_expression_pool')
            strings[name] = model._program(data_ids[key], pool) if model.operators else []
        else:
            strings[name] = model.charstring(data_ids[key])
        if release_programs and pool is None:
            strings[name].compile(isCFF2=True)
    shared = []
    if pool is not None:
        strings, shared, pool_report = pool.compile(strings)
        candidate._swirl_expression_pool_report = pool_report
    builder.setupCFF2(strings)
    for subroutine in shared:
        candidate['CFF2'].cff.GlobalSubrs.append(subroutine)
    if regions:
        store = VarStoreData(otVarStore=buildVarStore(buildVarRegionList(regions, list(tags)), data))
        top = candidate['CFF2'].cff.topDictIndex[0]
        top.VarStore = store
        # FontTools' in-memory glyph set reads this reference, while serialized
        # loading reconstructs it from TopDICT. Keep both views equivalent.
        top.CharStrings.varStore = store
        for fd in top.FDArray:
            fd.Private.vstore = store
    from cff2_subroutines import pack
    pack(candidate, release_programs=release_programs)
    candidate['maxp'] = newTable('maxp')
    candidate['maxp'].tableVersion = 0x00005000
    candidate['maxp'].numGlyphs = len(order)
    candidate['head'].indexToLocFormat = 0
    candidate['head'].glyphDataFormat = 0
    # CFF2 default bounds are recomputed by the head table compiler from the
    # actual CharStrings, including fractional points and implicit closures.
    candidate.recalcBBoxes = True
    candidate.recalcTimestamp = False
    return candidate
