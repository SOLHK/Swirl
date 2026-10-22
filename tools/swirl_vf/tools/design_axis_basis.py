"""Endpoint coordinate basis for a legal font-level mapping candidate.

Source post-avar q and target standard normalized r are distinct spaces.
The source's used endpoint q need not be +/-16384. Mapping those endpoints to
legal target anchors is possible, but re-expressing glyph and metric variation
models in r remains separate unfinished work. This module modifies no font.

Integer q is encoded to nearest integer r, ties toward positive infinity. The
fractional inverse generally has nonzero coordinate error; it is not lossless
numeric replay and supplies no bound on glyph/metric error. Upstream user-input
collisions and normalized16 intermediate samples are not repaired here.

References: OpenType avar, otvaroverview normalization and variation regions.
https://learn.microsoft.com/en-us/typography/opentype/spec/avar
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from fontTools.ttLib import newTable

from font_axis_mapping import ANCHORS, GRID, compress_integer_mapping
from target_axis_mapping import A3_SOURCE_COMMIT, CANDIDATE, SourceAxis, source_axis_plan


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def nearest(value):
    value = Fraction(value) + Fraction(1, 2)
    return value.numerator // value.denominator


@dataclass(frozen=True)
class DesignAxisBasis:
    tag: str
    q_min: int
    q_default: int
    q_max: int

    def __post_init__(self):
        require(type(self.tag) is str and len(self.tag) == 4 and self.tag.isascii(), 'invalid_basis_axis_tag')
        require(all(type(q) is int for q in (self.q_min, self.q_default, self.q_max))
                and -GRID <= self.q_min < 0 and self.q_default == 0
                and 0 < self.q_max <= GRID, 'invalid_source_q_endpoint_basis')


def basis_from_axis(axis):
    """Freeze endpoint/default q from the unchanged raw-axis hypothesis."""
    require(isinstance(axis, SourceAxis), 'raw_source_axis_required')
    q = tuple(source_axis_plan(axis, user)['source_q']
              for user in (axis.minimum, axis.default, axis.maximum))
    return DesignAxisBasis(axis.tag, *q)


def encode_source_q(basis, q):
    """Embed integer source q in target r; this is not a glyph-model transform."""
    require(isinstance(basis, DesignAxisBasis), 'source_q_basis_required')
    require(type(q) is int and basis.q_min <= q <= basis.q_max, 'source_q_outside_endpoint_basis')
    span = -basis.q_min if q < 0 else basis.q_max
    return nearest(Fraction(q * GRID, span))


def decode_target_r(basis, r):
    """Return fractional source-q units for a target-r integer coordinate."""
    require(isinstance(basis, DesignAxisBasis), 'source_q_basis_required')
    require(type(r) is int and -GRID <= r <= GRID, 'target_r_not_integer_f2dot14')
    span = -basis.q_min if r < 0 else basis.q_max
    return Fraction(r * span, GRID)


def coordinate_error_bound(basis, q):
    require(isinstance(basis, DesignAxisBasis) and type(q) is int
            and basis.q_min <= q <= basis.q_max, 'source_q_outside_endpoint_basis')
    span = -basis.q_min if q < 0 else basis.q_max
    return Fraction(span, 2 * GRID)


@lru_cache(maxsize=128)
def _compile_rebased_axis(axis):
    basis = basis_from_axis(axis)
    points = []
    previous = None
    for n in range(-GRID, GRID + 1):
        span = axis.default - axis.minimum if n < 0 else axis.maximum - axis.default
        q = source_axis_plan(axis, axis.default + n * span / GRID)['source_q']
        r = encode_source_q(basis, q)
        require(previous is None or r >= previous, 'rebased_candidate_mapping_not_monotonic')
        require(n not in (-GRID, 0, GRID) or r == n, 'rebased_required_anchor_not_preserved')
        previous = r
        points.append((n, r))
    records = compress_integer_mapping(points)
    require(all(anchor in records for anchor in ANCHORS), 'rebased_anchor_missing')
    return basis, records


def compile_rebased_axis(axis):
    """Return (frozen basis, legal integer avar records) without fitting data."""
    require(isinstance(axis, SourceAxis), 'raw_source_axis_required')
    return _compile_rebased_axis(axis)


def build_rebased_avar(axes):
    """Return a detached avar v1 and coordinate-only candidate certificate."""
    require(type(axes) in (tuple, list) and axes and len(axes) <= 65535
            and all(isinstance(axis, SourceAxis) for axis in axes), 'raw_source_axes_required')
    require(len({axis.tag for axis in axes}) == len(axes), 'duplicate_source_axis_tags')
    results = tuple(compile_rebased_axis(axis) for axis in axes)
    table = newTable('avar')
    table.majorVersion, table.minorVersion = 1, 0
    table.segments = {axis.tag: {n / GRID: r / GRID for n, r in records}
                      for axis, (_, records) in zip(axes, results)}
    certificate = {
        'schema': 1, 'status': 'REBASED_AVAR_COORDINATE_CANDIDATE_ONLY',
        'mapping_candidate_only': True, 'font_only': True,
        'mapping_candidate': CANDIDATE, 'a3_source_commit': A3_SOURCE_COMMIT,
        'source_coordinate_space': 'source_post_avar_q',
        'target_coordinate_space': 'standard_normalized_r',
        'axis_order': [axis.tag for axis in axes],
        'bases': [{'tag': basis.tag, 'q_min': basis.q_min, 'q_default': basis.q_default,
                   'q_max': basis.q_max, 'target_r_endpoints': [-GRID, 0, GRID],
                   'input_grid_knots_checked': 2 * GRID + 1, 'compiled_records': len(records),
                   'negative_source_q_error_bound': [-basis.q_min, 2 * GRID],
                   'positive_source_q_error_bound': [basis.q_max, 2 * GRID],
                   'error_bound_unit': 'source_q_grid_units',
                   'source_raw_records_unchanged': True}
                  for basis, records in results],
        'fractional_decode_is_numerically_lossless': False,
        'source_glyph_model_unchanged': True, 'glyph_model_status': 'NOT_REBUILT',
        'glyph_error_bound': 'NOT_ESTABLISHED',
        'glyph_model_reparameterization': 'NOT_IMPLEMENTED',
        'HVAR_reparameterization': 'NOT_IMPLEMENTED',
        'VVAR_reparameterization': 'NOT_IMPLEMENTED',
        'GDEF_layout_region_reparameterization': 'NOT_IMPLEMENTED',
        'target_normalized16_between_grid_knots': 'NOT_EVALUATED',
        'original_binary64_input_collisions': 'NOT_RESOLVED',
        'native_normalization_test': 'NOT_RUN', 'native_glyph_test': 'NOT_RUN',
        'source_user_mapping_accepted': False, 'target_mapping_accepted': False,
        'continuous_space_acceptance': False, 'font_conversion_accepted': False,
        'font_only_equivalence_accepted': False,
    }
    return table, certificate
