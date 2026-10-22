"""Finite A3 source-map candidate and exact identity-avar target transport.

Source arithmetic is the unchanged ONCE_ALL hypothesis from A3 commit
6d6a7b5eec6e2c7a630dfd4f692e29a7ecc52115, functions prereadback_mappings
and prereadback_design_inputs. Its 140-position native cohort supports finite
observations, not a global source mapping. Raw avar order and duplicates are
retained. Neither native readback nor a glyph measurement enters this mapper.

Once q is known, target y = default + q*sideSpan/16384 can preserve every q
exactly through FLOAT and user 16.16 for the integer ranges used here. This is
an application adapter: y is not generally the original user request x.

Primary references (design and API semantics; no copied upstream code):
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview
https://harfbuzz.github.io/harfbuzz-hb-font.html#hb-font-set-var-coords-normalized
https://freetype.org/freetype2/docs/reference/ft2-multiple_masters.html#ft_set_var_blend_coordinates
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
import struct

from audit_font import raw_avar


CANDIDATE = 'prereadback_once_all_axes_endpoint_normalized16_truncate'
A3_SOURCE_COMMIT = '6d6a7b5eec6e2c7a630dfd4f692e29a7ecc52115'
TAGS = frozenset(('WDTH', 'wght', 'HGHT'))
FLAGS = {'source_user_mapping_accepted': False, 'target_mapping_accepted': False,
         'continuous_space_acceptance': False, 'font_conversion_accepted': False,
         'font_only_equivalence_accepted': False}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def float32(value):
    return struct.unpack('>f', struct.pack('>f', value))[0]


@dataclass(frozen=True)
class SourceAxis:
    tag: str
    minimum: float
    default: float
    maximum: float
    records: tuple[tuple[int, int], ...]

    def __post_init__(self):
        require(type(self.tag) is str and len(self.tag) == 4 and self.tag.isascii(), 'invalid_axis_tag')
        bounds = (self.minimum, self.default, self.maximum)
        require(all(finite(value) and -32768 <= value < 32768
                    and value * 65536 == int(value * 65536) for value in bounds)
                and self.minimum < self.default < self.maximum, 'invalid_source_axis_bounds')
        require(type(self.records) is tuple and len(self.records) >= 3
                and all(type(row) is tuple and len(row) == 2
                        and all(type(value) is int and -16384 <= value <= 16384 for value in row)
                        for row in self.records), 'invalid_raw_avar_records')
        require(self.records[0] == (-16384, -16384) and self.records[-1] == (16384, 16384)
                and (0, 0) in self.records, 'raw_avar_required_anchors_missing')

    @property
    def identity(self):
        return (all(x == y for x, y in self.records)
                and all(left[0] < right[0] for left, right in zip(self.records, self.records[1:])))


def axes_from_font(font):
    """Read raw serialized avar bytes; never round-trip the lossy segment dict."""
    require('fvar' in font and 'avar' in font and font.reader is not None,
            'serialized_fvar_and_raw_avar_required')
    tags = [axis.axisTag for axis in font['fvar'].axes]
    require(len(tags) == 3 and set(tags) == TAGS, 'three_original_axis_tags_required')
    parsed = raw_avar(font.reader['avar'], tags)
    require(parsed['major'] == 1 and parsed['minor'] == 0 and parsed['reserved'] == 0
            and parsed['axis_count'] == len(tags) and parsed['trailing_bytes'] == 0,
            'unsupported_raw_avar_header')
    result = []
    for axis, raw in zip(font['fvar'].axes, parsed['axes']):
        records = tuple((row['from_f2dot14'], row['to_f2dot14']) for row in raw['records'])
        result.append(SourceAxis(str(axis.axisTag), axis.minValue, axis.defaultValue, axis.maxValue, records))
    return tuple(result)


def ordered_map(value, records):
    """A3's zero fast path and first matching raw adjacent interval."""
    if value == 0:
        return 0.
    pairs = tuple((x / 16384, y / 16384) for x, y in records)
    if value < pairs[0][0]:
        return pairs[0][1]
    for (start, low), (end, high) in zip(pairs, pairs[1:]):
        if value <= end:
            if start == end:
                return high
            return low + (value - start) * (high - low) / (end - start)
    return pairs[-1][1]


def source_axis_plan(axis, value):
    require(isinstance(axis, SourceAxis) and finite(value) and axis.minimum <= value <= axis.maximum,
            'source_user_coordinate_out_of_range')
    once = math.trunc(value * 10000) / 10000 if value > 0 else value
    require(axis.minimum <= once <= axis.maximum, 'source_decimal_stage_out_of_range')
    if once == axis.default:
        normalized = 0.
    else:
        span = axis.default - axis.minimum if once < axis.default else axis.maximum - axis.default
        normalized = (once - axis.default) / span
    if axis.identity:
        if once < axis.default:
            normalized = float32((once - axis.minimum) / (axis.default - axis.minimum)) - 1
    else:
        normalized = float32(normalized)
    normalized16 = math.trunc(normalized * 65536) / 65536
    mapped = ordered_map(normalized16, axis.records)
    q = math.floor(mapped * 16384 + .5)
    require(-16384 <= q <= 16384, 'source_candidate_outside_normalized_space')
    return {'original_user': value, 'once_user': once, 'normalized16': normalized16, 'source_q': q}


def source_plan(font, location):
    axes = axes_from_font(font)
    require(type(location) is dict and set(location) == {axis.tag for axis in axes},
            'all_original_source_axes_required')
    plans = {axis.tag: source_axis_plan(axis, location[axis.tag]) for axis in axes}
    return {'axis_order': [axis.tag for axis in axes], 'mapping_candidate': CANDIDATE,
            'a3_source_commit': A3_SOURCE_COMMIT,
            **{field: {tag: plan[field] for tag, plan in plans.items()}
               for field in ('original_user', 'once_user', 'normalized16', 'source_q')}, **FLAGS}


def axis_transport(axis, q):
    """Encode a known integer q without an observed-value search or tolerance."""
    require(isinstance(axis, SourceAxis) and axis.identity, 'target_identity_avar_required')
    require(type(q) is int and -16384 <= q <= 16384, 'invalid_normalized_q')
    default = Fraction(axis.default)
    span = default - Fraction(axis.minimum) if q < 0 else Fraction(axis.maximum) - default
    rational = default + q * span / 16384
    user = float(rational)
    require(Fraction(user) == rational and Fraction(float32(user)) == rational,
            'target_user_not_exactly_float32')
    fixed = rational * 65536
    require(fixed.denominator == 1 and -(1 << 31) <= fixed < (1 << 31),
            'target_user_not_exactly_fixed16')
    # This verifies the target normalization independently of user decimal text.
    normalized = (rational - default) / span if q else Fraction(0)
    require(normalized * 16384 == q and normalized * 65536 == q * 4,
            'target_normalized_coordinate_changed')
    return {'target_user': user, 'target_float32': float32(user), 'target_fixed16': int(fixed),
            'hb_normalized': q, 'ft_normalized': q * 4}


def target_plan(font, q, *, source_axes=None):
    axes = axes_from_font(font)
    require(all(axis.identity for axis in axes), 'target_identity_avar_required')
    require(type(q) is dict and set(q) == {axis.tag for axis in axes}, 'all_target_normalized_axes_required')
    if source_axes is not None:
        require(tuple((a.tag, a.minimum, a.default, a.maximum) for a in axes)
                == tuple((a.tag, a.minimum, a.default, a.maximum) for a in source_axes),
                'target_axis_tags_or_ranges_changed')
    plans = {axis.tag: axis_transport(axis, q[axis.tag]) for axis in axes}
    return {'axis_order': [axis.tag for axis in axes], 'source_q': dict(q),
            **{field: {tag: plan[field] for tag, plan in plans.items()}
               for field in ('target_user', 'target_float32', 'target_fixed16')},
            'hb_normalized': [plans[axis.tag]['hb_normalized'] for axis in axes],
            'ft_normalized': [plans[axis.tag]['ft_normalized'] for axis in axes],
            'transport_exact': True, 'application_adapter_required': True, **FLAGS}
