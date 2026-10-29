"""Exact continuous error bounds for supplied standard three-axis models.

On each cell of the union of support breakplanes and endpoint-basis zero
planes, the difference is multi-affine. A component's absolute maximum is at
a cell vertex. The squared Euclidean norm is convex in each coordinate with
the others fixed, so its maximum is also attained at a cell vertex. Enumerating
the unique grid vertices therefore certifies the supplied models exactly.

This proves ideal, unrounded model arithmetic only. No font parser, native
engine, source user mapping, avar, rasterization or whole-font acceptance is
implied. Unsupported discontinuities and excessive grids are rejected.

Primary scalar rule: OpenType Font Variations overview, interpolation process:
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview#interpolation-of-instance-values
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from math import prod


ZERO, ONE = Fraction(0), Fraction(1)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def rational(value):
    require(type(value) in (int, Fraction), 'exact_integer_or_Fraction_required')
    return Fraction(value)


@dataclass(frozen=True)
class AxisSupport:
    start: Fraction
    peak: Fraction
    end: Fraction

    def __post_init__(self):
        for field in ('start', 'peak', 'end'):
            object.__setattr__(self, field, rational(getattr(self, field)))
        require(-1 <= self.start <= self.peak <= self.end <= 1, 'invalid_axis_support_order_or_range')
        if self.peak == 0:
            return  # OpenType's neutral axis, including (0,0,0).
        require(not (self.start < 0 < self.end), 'nonzero_support_crosses_zero')
        require(self.start < self.end
                and (self.start < self.peak or self.peak == -1)
                and (self.peak < self.end or self.peak == 1),
                'discontinuous_support_requires_one_sided_analysis')

    def scalar(self, coordinate):
        coordinate = rational(coordinate)
        if self.peak == 0 or coordinate == self.peak:
            return ONE
        if coordinate <= self.start or coordinate >= self.end:
            return ZERO
        if coordinate < self.peak:
            return (coordinate - self.start) / (self.peak - self.start)
        return (self.end - coordinate) / (self.end - self.peak)


@dataclass(frozen=True)
class VectorRegion:
    supports: tuple[AxisSupport | None, AxisSupport | None, AxisSupport | None]
    delta: tuple[int, ...]

    def __post_init__(self):
        require(type(self.supports) is tuple and len(self.supports) == 3
                and all(support is None or type(support) is AxisSupport for support in self.supports),
                'three_standard_axis_supports_required')
        require(type(self.delta) is tuple and self.delta and all(type(v) is int for v in self.delta),
                'integer_vector_delta_required')


@dataclass(frozen=True)
class VectorModel:
    base: tuple[int, ...]
    regions: tuple[VectorRegion, ...] = ()

    def __post_init__(self):
        require(type(self.base) is tuple and self.base and all(type(v) is int for v in self.base),
                'integer_base_vector_required')
        require(type(self.regions) is tuple
                and all(type(region) is VectorRegion and len(region.delta) == len(self.base) for region in self.regions),
                'region_vector_dimensions_differ')


@dataclass(frozen=True)
class EndpointTransform:
    """Positive source-q spans: q(r)=negative_span*r or positive_span*r."""
    negative_spans: tuple[Fraction, Fraction, Fraction] = (ONE, ONE, ONE)
    positive_spans: tuple[Fraction, Fraction, Fraction] = (ONE, ONE, ONE)

    def __post_init__(self):
        for field in ('negative_spans', 'positive_spans'):
            values = getattr(self, field)
            require(type(values) is tuple and len(values) == 3, 'three_source_axis_spans_required')
            values = tuple(rational(value) for value in values)
            require(all(0 < value <= 1 for value in values), 'source_axis_span_out_of_range')
            object.__setattr__(self, field, values)

    def source_coordinates(self, target):
        return tuple(r * (self.negative_spans[i] if r < 0 else self.positive_spans[i])
                     for i, r in enumerate(target))


@dataclass(frozen=True)
class ContinuousCertificate:
    breakplanes: tuple[tuple[Fraction, ...], ...]
    vertex_count: int
    cell_count: int
    max_abs_components: tuple[Fraction, ...]
    component_witnesses: tuple[tuple[Fraction, Fraction, Fraction], ...]
    max_squared_norm: Fraction
    norm_witness: tuple[Fraction, Fraction, Fraction]
    target_upem_multiplier: Fraction
    status: str = 'CERTIFIED_CONTINUOUS_SUPPLIED_MODEL_BOUND'
    ideal_model_arithmetic_only: bool = True
    native_execution: bool = False
    source_user_mapping_accepted: bool = False
    whole_font_equivalence_accepted: bool = False

    @property
    def max_abs_component(self):
        return max(self.max_abs_components)


def _evaluate(model, coordinates):
    result = [Fraction(value) for value in model.base]
    for region in model.regions:
        scalar = ONE
        for support, coordinate in zip(region.supports, coordinates):
            if support is not None:
                scalar *= support.scalar(coordinate)
                if not scalar:
                    break
        if scalar:
            for index, value in enumerate(region.delta):
                result[index] += value * scalar
    return tuple(result)


def evaluate_model(model, coordinates):
    require(type(model) is VectorModel and type(coordinates) is tuple and len(coordinates) == 3,
            'model_and_three_exact_coordinates_required')
    coordinates = tuple(rational(value) for value in coordinates)
    require(all(-1 <= value <= 1 for value in coordinates), 'coordinate_outside_normalized_domain')
    return _evaluate(model, coordinates)


def certify_difference(source, target, transform=EndpointTransform(), *, target_upem_multiplier=1,
                       max_vertices=100000):
    require(type(source) is VectorModel and type(target) is VectorModel
            and len(source.base) == len(target.base) and type(transform) is EndpointTransform,
            'source_target_models_or_transform_invalid')
    multiplier = rational(target_upem_multiplier)
    require(multiplier > 0 and type(max_vertices) is int and max_vertices > 0,
            'invalid_multiplier_or_vertex_budget')
    planes = [set((Fraction(-1), ZERO, ONE)) for _ in range(3)]
    for model, is_source in ((source, True), (target, False)):
        for region in model.regions:
            for axis, support in enumerate(region.supports):
                if support is None or support.peak == 0:
                    continue
                for knot in (support.start, support.peak, support.end):
                    if is_source:
                        span = transform.negative_spans[axis] if knot < 0 else transform.positive_spans[axis]
                        knot /= span
                    if -1 <= knot <= 1:
                        planes[axis].add(knot)
    planes = tuple(tuple(sorted(values)) for values in planes)
    vertex_count = prod(len(values) for values in planes)
    require(vertex_count <= max_vertices, 'continuous_certificate_vertex_budget_exceeded')
    maxima = [ZERO] * len(source.base)
    witnesses = [tuple(values[0] for values in planes)] * len(source.base)
    norm_maximum, norm_witness = ZERO, witnesses[0]
    for point in product(*planes):
        a = _evaluate(source, transform.source_coordinates(point))
        b = _evaluate(target, point)
        difference = tuple(left - right / multiplier for left, right in zip(a, b))
        for index, value in enumerate(difference):
            if abs(value) > maxima[index]:
                maxima[index], witnesses[index] = abs(value), point
        norm = sum((value * value for value in difference), ZERO)
        if norm > norm_maximum:
            norm_maximum, norm_witness = norm, point
    return ContinuousCertificate(
        breakplanes=planes, vertex_count=vertex_count,
        cell_count=prod(len(values) - 1 for values in planes),
        max_abs_components=tuple(maxima), component_witnesses=tuple(witnesses),
        max_squared_norm=norm_maximum, norm_witness=norm_witness,
        target_upem_multiplier=multiplier)
