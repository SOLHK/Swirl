"""Compile a legal font-level avar candidate from a frozen source hypothesis.

The source is the raw-record SourceAxis and ONCE_ALL arithmetic, never a lossy
avar dictionary or an observed glyph. Every nominal 2.14 input grid location is
evaluated before exact collinear compression. This proves a finite mathematical
grid relation, not that a native fixed-point normalizer follows that relation
for arbitrary original binary64 user inputs. Upstream input loss remains.

This module returns a new table only. It does not modify any supplied font or
convert its glyph model from nominal coordinates to source design-q space.
The caller must independently establish that target-space contract first.

Primary references inspected before implementation:
https://learn.microsoft.com/en-us/typography/opentype/spec/avar
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview#coordinate-scales-and-normalization
"""
from __future__ import annotations

from functools import lru_cache

from fontTools.ttLib import newTable

from target_axis_mapping import A3_SOURCE_COMMIT, CANDIDATE, SourceAxis, source_axis_plan


GRID = 16384
ANCHORS = ((-GRID, -GRID), (0, 0), (GRID, GRID))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def compress_integer_mapping(points):
    """Compress validated integer pairs exactly, always retaining x=0.

    Callers establish F2DOT14 range, monotonicity and required anchors before
    supplying their points. No rounding or raw-source record editing occurs.
    """
    records = []
    for point in points:
        while len(records) >= 2 and records[-1][0] != 0:
            a, b = records[-2:]
            if (b[1] - a[1]) * (point[0] - b[0]) != (point[1] - b[1]) * (b[0] - a[0]):
                break
            records.pop()
        records.append(point)
    return tuple(records)


def compile_axis(axis):
    """Return immutable unique/increasing integer records for one source axis.

    Endpoints and zero must already have their required output. A backwards
    output step, invalid candidate result or missing anchor rejects the whole
    axis. Existing raw source records are never sorted, deduplicated, patched,
    or assigned directly to a fontTools segments dictionary.
    """
    require(isinstance(axis, SourceAxis), 'raw_source_axis_required')
    return _compile_axis(axis)


@lru_cache(maxsize=128)
def _compile_axis(axis):
    points = []
    previous = None
    for n in range(-GRID, GRID + 1):
        span = axis.default - axis.minimum if n < 0 else axis.maximum - axis.default
        original_user = axis.default + n * span / GRID
        q = source_axis_plan(axis, original_user)['source_q']
        require(type(q) is int and -GRID <= q <= GRID, 'candidate_q_not_integer_f2dot14')
        require(previous is None or q >= previous, 'candidate_mapping_not_monotonic')
        if n in (-GRID, 0, GRID):
            require(q == n, 'candidate_required_anchor_not_preserved')
        previous = q
        points.append((n, q))
    result = compress_integer_mapping(points)
    require(len(result) <= 65535 and all(anchor in result for anchor in ANCHORS),
            'compiled_axis_records_or_anchors_invalid')
    return result


def build_standard_avar(axes):
    """Create a new avar v1 candidate and a deliberately limited certificate.

    ``axes`` is an ordered sequence of raw SourceAxis objects. No font object,
    native output, glyph data, fitting observations or approval flag is input.
    The returned table remains detached from every caller-owned source font.
    """
    require(type(axes) in (tuple, list) and 1 <= len(axes) <= 65535
            and all(isinstance(axis, SourceAxis) for axis in axes), 'raw_source_axes_required')
    require(len({axis.tag for axis in axes}) == len(axes), 'duplicate_source_axis_tags')
    compiled = tuple(compile_axis(axis) for axis in axes)
    table = newTable('avar')
    table.majorVersion, table.minorVersion = 1, 0
    table.segments = {
        axis.tag: {x / GRID: y / GRID for x, y in records}
        for axis, records in zip(axes, compiled)
    }
    certificate = {
        'schema': 1,
        'status': 'LEGAL_AVAR_MAPPING_CANDIDATE_ONLY',
        'mapping_candidate_only': True,
        'font_only': True,
        'mapping_candidate': CANDIDATE,
        'a3_source_commit': A3_SOURCE_COMMIT,
        'axis_order': [axis.tag for axis in axes],
        'axes': [{'tag': axis.tag, 'input_grid_knots_checked': 2 * GRID + 1,
                  'compiled_records': len(records),
                  'source_raw_record_count': len(axis.records),
                  'source_raw_records_unchanged': True,
                  'required_anchors_preserved': True,
                  'integer_grid_mapping_preserved_by_exact_collinear_compression': True}
                 for axis, records in zip(axes, compiled)],
        'input_grid_format': 'signed_F2DOT14',
        'target_normalized16_between_grid_knots': 'NOT_EVALUATED',
        'original_binary64_user_to_native_target_equivalence': 'NOT_ESTABLISHED',
        'target_glyph_model_required_space': 'independently_verified_source_design_q',
        'source_output_space': 'source_post_avar_design_q',
        'target_design_r_contract': 'direct_source_q_coordinates_only',
        'source_q_to_distinct_target_r_reparameterization': 'NOT_IMPLEMENTED',
        'source_glyph_model_unchanged': True,
        'glyph_model_status': 'NOT_REBUILT',
        'native_normalization_test': 'NOT_RUN',
        'native_glyph_test': 'NOT_RUN',
        'source_user_mapping_accepted': False,
        'target_mapping_accepted': False,
        'continuous_space_acceptance': False,
        'font_conversion_accepted': False,
        'font_only_equivalence_accepted': False,
    }
    return table, certificate
