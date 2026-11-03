"""Tensor powers from distinct, synchronized axes; no duplicated axis tags.

The axis-synchronization idea is demonstrated by arrowtype/HOI-test and
googlefonts/how2avar2. This is an independent CFF2 implementation: three
physical inputs remain independent, and two avar2 copies per input supply
the repeated factors needed for a tensor cubic. No upstream code or outlines
are incorporated. See docs/SWIRL_VF_OPEN_SOURCE_INTERPOLATION_20261103.md.
"""
from __future__ import annotations

from itertools import product
import numpy as np
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.builder import buildVarData, buildDeltaSetIndexMap

from cff2_geometry import fixed, require
from joint_polynomial import PolynomialBox, TAGS

COPIES = tuple(f'P{i}{j:02d}' for i in range(3) for j in (1, 2))
GROUPS = tuple((tag, *COPIES[2*i:2*i+2]) for i, tag in enumerate(TAGS))


def add_axis_copies(font):
    """Append six simultaneous identity outputs before installing CFF2.

    Existing avar2 rows and all axis indices are preserved. Copies read the
    post-avar1 input, as every avar2 output does; they never read another
    output. Their user coordinate must be its hidden default, zero.
    """
    tags = tuple(a.axisTag for a in font['fvar'].axes)
    require(tags[:3] == TAGS and not set(tags).intersection(COPIES), 'invalid_HOI_axis_layout')
    avar = font['avar']
    require(avar.majorVersion == 2 and avar.table.VarStore is not None,
            'HOI_copies_require_avar2')
    for tag in COPIES:
        axis = Axis(); axis.axisTag = tag
        axis.minValue = -1.; axis.defaultValue = 0.; axis.maxValue = 1.
        axis.flags = 1; axis.axisNameID = font['name'].addName('Polynomial factor '+tag)
        font['fvar'].axes.append(axis)
        avar.segments[tag] = {-1.: -1., 0.: 0., 1.: 1.}
    stores = [avar.table.VarStore]
    stores += [font[tag].table.VarStore for tag in ('HVAR', 'VVAR') if tag in font]
    for store in stores:
        for region in store.VarRegionList.Region:
            for _ in COPIES:
                axis = otTables.VarRegionAxis()
                axis.StartCoord = axis.PeakCoord = axis.EndCoord = 0.
                region.VarRegionAxis.append(axis)
        store.VarRegionList.RegionAxisCount += len(COPIES)
    store = avar.table.VarStore
    first = len(store.VarRegionList.Region)
    for physical in range(3):
        for sign in (-1, 1):
            region = otTables.VarRegion(); region.VarRegionAxis = []
            for i in range(len(tags)+len(COPIES)):
                axis = otTables.VarRegionAxis()
                axis.StartCoord, axis.PeakCoord, axis.EndCoord = (
                    (min(0, sign), sign, max(0, sign)) if i == physical else (0., 0., 0.))
                region.VarRegionAxis.append(axis)
            store.VarRegionList.Region.append(region)
    store.VarRegionList.RegionCount += 6
    require(store.VarRegionList.RegionCount < 32768, 'HOI_avar_region_overflow')
    rows = np.zeros((6, 6), dtype=int)
    for i in range(6):
        rows[i, 2*(i//2):2*(i//2)+2] = (-16384, 16384)
    outer = len(store.VarData)
    store.VarData.append(buildVarData(list(range(first, first+6)), rows.tolist(), optimize=False))
    store.VarDataCount = len(store.VarData)
    old = avar.table.VarIdxMap
    indices = list(range(len(tags))) if old is None else list(old.mapping)
    require(len(indices) == len(tags), 'HOI_requires_explicit_axis_map')
    avar.table.VarIdxMap = buildDeltaSetIndexMap(indices+[(outer << 16)+i for i in range(6)])
    return tags+COPIES


class HOIPolynomialBox(PolynomialBox):
    """A sparse tensor-power blend, nested once for projection directions."""

    def __post_init__(self):
        super().__post_init__()
        require(self.axis_tags[:3] == TAGS and set(COPIES) <= set(self.axis_tags)
                and not set(COPIES).intersection(self.factors), 'missing_HOI_axis_copies')
        arrays = [self.coefficients, *self.factors.values()]
        self.degrees = [p for p in product(range(4), repeat=3)
                        if any(p) and any(np.any(c[p]) for c in arrays)]

    @property
    def supports(self):
        result = [{}]
        for degree in self.degrees:
            support = {}
            for group, exponent, (lo, hi) in zip(GROUPS, degree, self.bounds):
                support.update({tag: (lo, lo if hi <= 0 else hi, hi) for tag in group[:exponent]})
            result.append(support)
        result.extend({tag: triple} for tag in self.factors
                      for triple in (((-1, -1, 0), (0, 1, 1)) if self.signed_factors else ((0, 1, 1),)))
        return result

    def _program(self, vsindex, expression_pool=None):
        if not self.operators:
            return []
        program = [vsindex, 'vsindex']; regions = len(self.supports)-1
        stack = maximum = 0

        def push(value):
            nonlocal stack, maximum
            program.append(fixed(float(value))); stack += 1; maximum = max(maximum, stack)
            require(stack <= 513, 'HOI_blend_operand_stack_overflow')

        def blend():
            nonlocal stack
            push(1); program[-1] = 1; program.append('blend'); stack -= regions+1

        def polynomial(c):
            begin = len(program)
            push(c[0, 0, 0])
            if any(c[degree] != 0 for degree in self.degrees):
                for degree in self.degrees:
                    push(c[degree])
                for _ in range(regions-len(self.degrees)):
                    push(0)
                blend()
            if expression_pool is not None:
                program[begin:] = [expression_pool.intern(program[begin:], regions)]

        column = 0
        for operator, count in self.operators:
            for _ in range(count):
                polynomial(self.coefficients[..., column])
                if any(np.any(c[..., column]) for c in self.factors.values()):
                    for _ in self.degrees:
                        push(0)
                    for c in self.factors.values():
                        if self.signed_factors:
                            polynomial(-c[..., column])
                        polynomial(c[..., column])
                    blend()
                column += 1
            require(stack == count, 'HOI_operator_stack_mismatch')
            program.append(operator); stack = 0
        self.evidence['maximum_operand_stack'] = maximum
        return program


class HOIAxisPowerBox(HOIPolynomialBox):
    """Use nine per-axis powers when full tensor regions exceed uint16 capacity.

    Multiplication across different physical axes is nested, but each power
    uses one repeated-axis region. This trades bytes for bounded region count,
    without changing any polynomial coefficient or moving any sample.
    """
    @property
    def supports(self):
        powers = []
        for group, (lo, hi) in zip(GROUPS, self.bounds):
            for exponent in (1, 2, 3):
                powers.append({tag: (lo, lo if hi <= 0 else hi, hi) for tag in group[:exponent]})
        factors = [{tag: triple} for tag in self.factors for triple in
                   (((-1, -1, 0), (0, 1, 1)) if self.signed_factors else ((0, 1, 1),))]
        return [{}]+powers+factors

    def _program(self, vsindex, expression_pool=None):
        if not self.operators:
            return []
        program = [vsindex, 'vsindex']; regions = len(self.supports)-1
        stack = maximum = 0

        def push(value):
            nonlocal stack, maximum
            program.append(fixed(float(value))); stack += 1; maximum = max(maximum, stack)
            require(stack <= 513, 'HOI_power_blend_operand_stack_overflow')

        def blend():
            nonlocal stack
            push(1); program[-1] = 1; program.append('blend'); stack -= regions+1

        def polynomial(c, axis=0):
            if not np.any(c):
                push(0); return
            if axis == 3:
                push(c); return
            polynomial(c[0], axis+1)
            if np.any(c[1:]):
                for region in range(regions):
                    if region//3 == axis:
                        polynomial(c[region % 3+1], axis+1)
                    else:
                        push(0)
                blend()

        def operand(c):
            begin = len(program)
            polynomial(c)
            if expression_pool is not None:
                program[begin:] = [expression_pool.intern(program[begin:], regions)]

        column = 0
        for operator, count in self.operators:
            for _ in range(count):
                operand(self.coefficients[..., column])
                if any(np.any(c[..., column]) for c in self.factors.values()):
                    for _ in range(9):
                        push(0)
                    for c in self.factors.values():
                        if self.signed_factors:
                            operand(-c[..., column])
                        operand(c[..., column])
                    blend()
                column += 1
            require(stack == count, 'HOI_power_operator_stack_mismatch')
            program.append(operator); stack = 0
        self.evidence['maximum_operand_stack'] = maximum
        return program
