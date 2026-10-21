"""Select a legal integer design grid using decoded continuous-model error.

The fixed eightfold lattice is not always the most accurate legal lattice.
At a standard HVAR corner every region weight is zero or one, so an integer
coefficient model cannot represent 1.5 target units exactly. This necessary
endpoint bound rejects hopeless grids before building. Surviving grids must
also pass an independent Fraction certificate on the actual serialized glyph
and advance models over the entire three-axis design cube.

This is a bounded candidate path for small standard q-space controls. It is
not enabled in the production builder and does not prove user-input mapping,
native rounding, Apple HVF equivalence or third-party software behavior.

References: OpenType otvarcommonformats, hmtx, otvaroverview; fontTools public
scale_upem/partial instancer APIs. No upstream implementation is copied.
"""
from __future__ import annotations

import copy
from fractions import Fraction
from itertools import product

from continuous_model import EndpointTransform, evaluate_model
from design_axis_basis import basis_from_axis
from font_model_certificate import advance_models, certify_font_models
from metric_variations import add_metric_variations, verify_metric_variations
from precision_metrics import scale_with_precision_metrics
from rebase_design_font import (PRECISION8_TABLES, _serialized_precision_font,
    _validate_standard_q, rebase_design_font)


LIMIT = Fraction(1, 32)


class RebasePrecisionError(ValueError):
    def __init__(self, reason, attempts=()):
        super().__init__(reason)
        self.attempts = tuple(attempts)


def require(condition, reason):
    if not condition:
        raise RebasePrecisionError(reason)


def nearest_integer(value):
    require(type(value) in (int, Fraction), 'exact_endpoint_value_required')
    value = Fraction(value) + Fraction(1, 2)
    return value.numerator // value.denominator


def endpoint_lattice_error(value, multiplier):
    """Sharp lower bound at a legal normalized corner, in source FUnits."""
    require(type(multiplier) is int and multiplier > 0, 'positive_integer_grid_required')
    value = Fraction(value)
    return abs(value - Fraction(nearest_integer(value * multiplier), multiplier))


def source_endpoint_transform(axes):
    bases = tuple(basis_from_axis(axis) for axis in axes)
    return EndpointTransform(tuple(Fraction(-basis.q_min, 16384) for basis in bases),
                             tuple(Fraction(basis.q_max, 16384) for basis in bases))


def endpoint_values(font, transform):
    """Actual decoded hmtx/HVAR and vmtx/VVAR at the 27 corner/default nodes."""
    return tuple(evaluate_model(model, transform.source_coordinates(point))[0]
                 for model in advance_models(font).values()
                 for point in product((Fraction(-1), Fraction(0), Fraction(1)), repeat=3))


def bounded_rebase(font, source_axes, *, max_points=4096, max_vertices=100000):
    """Return the smallest legal grid with a strict decoded-model certificate.

    No tolerance option exists. Each candidate's gvar phantom data regenerates
    its HVAR/VVAR through the existing exact writer, so independent rounding
    cannot leave disagreeing advance encodings. Unknown semantics and exhausted
    bounds reject the operation without writing files or changing the input.
    """
    _validate_standard_q(font, source_axes)
    require(type(max_points) is int and max_points > 0
            and type(max_vertices) is int and max_vertices > 0, 'positive_proof_budgets_required')
    require(set(font.keys()) <= PRECISION8_TABLES | {'MVAR', 'VORG', 'gasp'}, 'bounded_unsupported_table')
    # Tag-aware MVAR scaling is implemented separately. Its reparameterized
    # dimensionless values still need their own proof, rather than borrowing
    # a FUnit advance certificate.
    require('MVAR' not in font, 'bounded_MVAR_reparameterization_certificate_required')
    points = 0
    for name in font.getGlyphOrder():
        glyph = font['glyf'][name]
        require(not glyph.isComposite(), 'bounded_expanded_simple_glyphs_required')
        program = getattr(glyph, 'program', None)
        require(program is None or not program.getBytecode(), 'bounded_hint_program_not_supported')
        points += len(glyph.getCoordinates(font['glyf'])[0]) + 4
        require(points <= max_points, 'bounded_point_budget_exceeded')
    source = _serialized_precision_font(copy.deepcopy(font))
    attempts = []
    try:
        verify_metric_variations(source)
        transform = source_endpoint_transform(source_axes)
        values = endpoint_values(source, transform)
        upem = source['head'].unitsPerEm
        require(type(upem) is int and 16 <= upem <= 16384, 'invalid_source_UPEM')
        for multiplier in range(1, 16384 // upem + 1):
            lower = max((endpoint_lattice_error(value, multiplier) for value in values), default=Fraction(0))
            row = {'multiplier': multiplier, 'target_upem': upem * multiplier,
                   'endpoint_metric_lower_bound': lower}
            if lower > LIMIT:
                row['status'] = 'REFUSED_ENDPOINT_LATTICE'
                attempts.append(row)
                continue
            scaled = candidate = None
            try:
                scaled = scale_with_precision_metrics(source, upem * multiplier)
                scaled = _serialized_precision_font(scaled)
                candidate, report = rebase_design_font(scaled, source_axes)
                # Preserve one exact advance encoding of the final phantoms.
                for tag in ('HVAR', 'VVAR'):
                    if tag in candidate:
                        del candidate[tag]
                add_metric_variations(candidate)
                candidate = _serialized_precision_font(candidate)
                certificate = certify_font_models(source, candidate, transform,
                    target_upem_multiplier=multiplier,
                    max_vertices=max_vertices, max_points=max_points)
                row['certificate'] = certificate
                row['status'] = 'PASS_CONTINUOUS_MODEL' if certificate['within_1_32'] else 'REFUSED_CONTINUOUS_MODEL'
                attempts.append(row)
                if certificate['within_1_32']:
                    report.update(status='BOUNDED_STANDARD_Q_REBASE_CANDIDATE_ONLY',
                        selected_multiplier=multiplier, source_units_per_em=upem,
                        target_units_per_em=upem * multiplier, attempts=tuple(attempts),
                        continuous_model_certificate=certificate,
                        tolerance_source_font_units=LIMIT,
                        HVAR_VVAR_regenerated_from_serialized_gvar=True,
                        coordinate_mapping='NOT_PROVEN_BY_COEFFICIENT_CERTIFICATE',
                        platform_rounding='NOT_PROVEN_BY_COEFFICIENT_CERTIFICATE',
                        layout_equivalence='NOT_PROVEN_BY_COEFFICIENT_CERTIFICATE',
                        original_source_font_tested=False, application_compensation=False,
                        production_accepted=False)
                    result, candidate = candidate, None
                    return result, report
            except ValueError as error:
                row.update(status='REFUSED_CANDIDATE', reason=str(error))
                if not attempts or attempts[-1] is not row:
                    attempts.append(row)
            finally:
                if scaled is not None:
                    scaled.close()
                if candidate is not None:
                    candidate.close()
        raise RebasePrecisionError('no_legal_integer_grid_meets_continuous_budget', attempts)
    finally:
        source.close()
