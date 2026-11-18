"""Canonical unhinted metric frames and exact vertical layout compensation.

All coordinates below are design units, X right/Y up, in the SAME outline
frame. Raw APIs, pen placement and raster output are separate contracts. The
DirectWrite X-origin identity is normative; it does not describe Apple's
independent HVGL origin. GPOS can translate ink without changing a raw metric.

https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_metrics
https://learn.microsoft.com/en-us/typography/opentype/spec/gpos
https://learn.microsoft.com/en-us/typography/opentype/spec/vorg
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
import math


@dataclass(frozen=True)
class Metrics:
    advance_width: float
    advance_height: float
    horizontal_origin: tuple[float, float]
    vertical_origin: tuple[float, float]

    def __post_init__(self):
        values = (self.advance_width, self.advance_height, *self.horizontal_origin, *self.vertical_origin)
        if len(self.horizontal_origin) != 2 or len(self.vertical_origin) != 2 or not all(math.isfinite(v) for v in values):
            raise ValueError('finite_canonical_metric_frame_required')
        if self.advance_width < 0 or self.advance_height < 0:
            raise ValueError('negative_canonical_advance')

    @property
    def directwrite_origin_x(self):
        return self.horizontal_origin[0] + self.advance_width/2

    @property
    def independent_origin_x_gap(self):
        return self.vertical_origin[0] - self.directwrite_origin_x

    def phantom_points(self):
        # The vertical phantom X coordinates cannot encode independent Vx.
        hx = self.horizontal_origin[0]; vy = self.vertical_origin[1]
        return ((hx,0.), (hx+self.advance_width,0.), (0.,vy), (0.,vy-self.advance_height))

    def bearings(self, control_bounds):
        xmin,ymin,xmax,ymax = control_bounds
        if not all(math.isfinite(v) for v in control_bounds) or xmin>xmax or ymin>ymax:
            raise ValueError('ordered_control_bounds_required')
        hx = self.horizontal_origin[0]; vy = self.vertical_origin[1]
        return dict(lsb=xmin-hx, rsb=hx+self.advance_width-xmax,
                    tsb=vy-ymax, bsb=self.advance_height-vy+ymin)


def placement_correction(source: Metrics, target: Metrics):
    """Translate target ink to P-source.V, without claiming raw API equality.

    The target path is P-target.V. Thus correction is target.V-source.V in
    the common Y-up frame. Negate its Y component for a Y-down draw API.
    Advances are intentionally not repaired by changing a placement offset.
    """
    return tuple(a-b for a,b in zip(target.vertical_origin, source.vertical_origin))


def coretext_placement_in_outline_frame(base_origin, text_matrix):
    """Invert the run's linear frame for a CTRun base-origin displacement.

    CTRunGetAdvances includes positioning; it is not the raw font advance or
    CTRunGetBaseAdvancesAndOrigins' base advance. A displaced final glyph may
    have a compensating transverse component in its advance. Keep that raw
    vector as evidence, and compare base advances when testing pen spacing.
    The text matrix's translation does not act on a displacement vector.
    """
    if len(base_origin)!=2 or len(text_matrix)!=6 or not all(
            math.isfinite(v) for v in (*base_origin,*text_matrix)):
        raise ValueError('invalid_CoreText_run_frame')
    a,b,c,d,_,_=text_matrix;det=a*d-b*c
    if not det:raise ValueError('singular_CoreText_run_frame')
    x,y=base_origin
    return ((d*x-c*y)/det,(-b*x+a*y)/det)


def raw_origin_feasibility(source: Metrics, epsilon=1/32, *, fixed_horizontal_origin=True):
    if not math.isfinite(epsilon) or epsilon <= 0:
        raise ValueError('positive_metric_error_contract_required')
    # |Vx-(Hx+A/2)| <= |dVx|+|dHx|+|dA|/2 is necessary. For a fixed
    # outline frame Hx must match exactly, giving 3*epsilon/2.
    bound = (1.5 if fixed_horizontal_origin else 2.5)*epsilon
    gap = abs(source.independent_origin_x_gap)
    return {'necessary_condition_satisfied': gap <= bound, 'gap': gap,
            'maximum_gap_within_raw_contract': bound,
            'layout_or_visual_impossibility_asserted': False}


def origin_coefficients(target_base, source_base, target_deltas, source_deltas):
    """Exact GPOS coefficients for matched supports, rejecting lost fractions.

    Inputs are (X,Y) coefficients in a common frame. Callers must align support
    identities before calling; no sample fit or platform rounding is inferred.
    """
    if len(target_deltas) != len(source_deltas):
        raise ValueError('origin_support_count_mismatch')
    result=[]
    for a,b in zip([target_base,*target_deltas],[source_base,*source_deltas]):
        if len(a)!=2 or len(b)!=2: raise ValueError('two_origin_components_required')
        pair=tuple(Fraction(x)-Fraction(y) for x,y in zip(a,b))
        if any(v.denominator != 1 for v in pair):
            raise ValueError('fractional_GPOS_origin_coefficient_not_encodable')
        result.append(tuple(int(v) for v in pair))
    if any(not -32768<=v<=32767 for v in result[0]):
        raise ValueError('GPOS_default_origin_overflow')
    return result[0], result[1:]
