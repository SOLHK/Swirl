"""Exact conditional reference for HarfBuzz14.6 HVAR advance rounding.

Pinned primary sources reviewed before independently implementing the math:
https://github.com/harfbuzz/harfbuzz/blob/14.6.0/src/hb-ot-hmtx-table.hh
https://github.com/harfbuzz/harfbuzz/blob/14.6.0/src/hb-ot-font.cc
https://github.com/harfbuzz/harfbuzz/blob/14.6.0/src/hb-font.hh

That path rounds the variation delta in design units before output scaling.
The integer scaling multiplier is built through binary32 arithmetic. This
reference accepts an already interpolated delta; it does not emulate every
floating operation inside a VarStore, DirectWrite, or CoreText. No font data,
native acceptance, or coefficient-grid selection is changed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


LIMIT = Fraction(1, 32)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def exact(value):
    require(type(value) in (int, Fraction), 'integer_or_exact_Fraction_required')
    return Fraction(value)


def round_away(value):
    """C roundf's nearest integer, with half ties away from zero."""
    value = exact(value)
    if value < 0:
        return -round_away(-value)
    return (value + Fraction(1, 2)).__floor__()


def _nearest_even(value):
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + (2 * remainder > value.denominator
                       or (2 * remainder == value.denominator and quotient % 2 != 0))


def binary32(value):
    """Exact finite IEEE binary32 nearest/even value, returned as a Fraction."""
    value = exact(value)
    if not value:
        return value
    if value < 0:
        return -binary32(-value)
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    magnitude = Fraction(2 ** exponent) if exponent >= 0 else Fraction(1, 2 ** -exponent)
    if value < magnitude:
        exponent -= 1
    require(exponent <= 127, 'binary32_overflow')
    power = max(exponent - 23, -149)
    step = Fraction(2 ** power) if power >= 0 else Fraction(1, 2 ** -power)
    result = _nearest_even(value / step) * step
    require(result < 2 ** 128, 'binary32_overflow')
    return result


def _upem(value):
    require(type(value) is int and 16 <= value <= 16384, 'legal_integer_UPEM_required')
    return value


def hb_multiplier_fixed16(font_upem, output_scale):
    """Pinned hb_font_t::changed: integer numerator / float upem -> float."""
    _upem(font_upem)
    require(type(output_scale) is int and 0 < output_scale <= (1 << 31) - 1,
            'positive_int32_HB_output_scale_required')
    return int(binary32(binary32(output_scale * 65536) / font_upem))


def scale_integer_advance(advance, multiplier):
    require(type(advance) is int and 0 <= advance <= (1 << 31) - 1
            and type(multiplier) is int and multiplier >= 0, 'safe_nonnegative_integer_advance_required')
    result = (advance * multiplier + 32768) // 65536
    require(result <= (1 << 31) - 1, 'HB_output_position_overflow_not_modelled')
    return result


@dataclass(frozen=True)
class AdvanceReference:
    base: int
    interpolated_delta: Fraction
    binary32_delta: Fraction
    rounded_delta: int
    rounded_design_advance: int
    font_upem: int
    source_upem: int
    output_scale: int
    multiplier_fixed16: int
    output_position: int
    ideal_source_value: Fraction
    output_source_value: Fraction
    native_execution: bool = False


def advance_reference(base, delta, *, font_upem, source_upem, output_scale):
    require(type(base) is int and 0 <= base <= 65535, 'UFWORD_base_advance_required')
    _upem(font_upem)
    _upem(source_upem)
    delta = exact(delta)
    native_delta = binary32(delta)
    rounded_delta = round_away(native_delta)
    advance = max(0, base + rounded_delta)
    require(advance <= (1 << 31) - 1, 'advance_outside_safe_signed_scaling_range')
    multiplier = hb_multiplier_fixed16(font_upem, output_scale)
    position = scale_integer_advance(advance, multiplier)
    return AdvanceReference(base, delta, native_delta, rounded_delta, advance,
        font_upem, source_upem, output_scale, multiplier, position,
        (base + delta) * source_upem / font_upem,
        Fraction(position * source_upem, output_scale))


@dataclass(frozen=True)
class ThresholdGapBound:
    font_upem: int
    source_upem: int
    output_scale: int
    rounded_design_unit_gap: int
    minimum_output_position_gap: int
    minimum_source_unit_gap: Fraction
    tolerance: Fraction = LIMIT
    condition: str = 'same_UPM_nonnegative_no_overflow_rounded_design_advances_differ_by_at_least_specified_gap'
    native_execution: bool = False
    font_equivalence_accepted: bool = False

    @property
    def necessarily_exceeds_limit(self):
        return self.minimum_source_unit_gap > self.tolerance


def threshold_gap_bound(*, font_upem, source_upem, output_scale, design_unit_gap=1):
    """A conditional, coefficient-independent lower bound; no fitted samples."""
    _upem(source_upem)
    require(type(design_unit_gap) is int and design_unit_gap > 0, 'positive_integer_design_gap_required')
    multiplier = hb_multiplier_fixed16(font_upem, output_scale)
    output_gap = design_unit_gap * multiplier // 65536
    return ThresholdGapBound(font_upem, source_upem, output_scale, design_unit_gap,
                             output_gap, Fraction(output_gap * source_upem, output_scale))


def legal_upem_gap_summary(*, source_upem, output_scale):
    """Enumerate the complete legal UPEM field, including noninteger ratios.

    This is arithmetic over every permitted integer table value, not a search
    fitted to any glyph/request. Different-UPM font pairs are outside the
    same-UPM conditional threshold theorem and are explicitly not accepted.
    """
    _upem(source_upem)
    rows = (threshold_gap_bound(font_upem=upem, source_upem=source_upem, output_scale=output_scale)
            for upem in range(16, 16385))
    minimum = min(rows, key=lambda row: row.minimum_source_unit_gap)
    return {'legal_integer_UPEM_count': 16369,
            'minimum_conditional_gap': minimum.minimum_source_unit_gap,
            'first_UPM_attaining_minimum': minimum.font_upem,
            'noninteger_target_source_ratios_included': True,
            'all_legal_grids_exceed_limit_if_same_UPM_threshold_mismatch_persists': minimum.necessarily_exceeds_limit,
            'different_UPM_native_pair_equivalence': 'NOT_ESTABLISHED',
            'font_equivalence_accepted': False}
