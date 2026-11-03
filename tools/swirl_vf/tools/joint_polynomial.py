"""Local tensor polynomials encoded with three CFF2 Horner blend scalars.

Experimental representation, not production acceptance. Each polynomial is
valid only in its declared box; a caller must provide and verify region
selection. No private source data is stored by this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import numpy as np
from fontTools.misc.psCharStrings import T2CharString

from cff2_geometry import control_points, fixed, require

TAGS = ('WDTH', 'wght', 'HGHT')
NODES = np.asarray([0., .25, .75, 1.])
GRID = np.asarray(list(product(NODES, repeat=3)))
INVERSE = np.linalg.inv(np.vander(NODES, 4, increasing=True))


@dataclass
class PolynomialBox:
    bounds: np.ndarray
    operators: tuple
    coefficients: np.ndarray
    evidence: dict
    axis_tags: tuple = TAGS
    factors: dict = field(default_factory=dict)
    signed_factors: bool = False

    def __post_init__(self):
        self.bounds = np.asarray(self.bounds, dtype=float)
        require(self.bounds.shape == (3, 2) and np.isfinite(self.bounds).all()
                and np.all(self.bounds[:, 0] < self.bounds[:, 1])
                and np.all(np.abs(self.bounds) <= 1)
                and np.all(self.bounds * 16384 == np.round(self.bounds * 16384))
                and np.all(self.bounds[:, 0] * self.bounds[:, 1] >= 0),
                'polynomial_box_requires_F2DOT14_octant_bounds')
        require(self.coefficients.ndim == 4 and self.coefficients.shape[:3] == (4, 4, 4)
                and np.isfinite(self.coefficients).all()
                and self.coefficients.shape[3] == sum(n for _, n in self.operators),
                'invalid_tensor_polynomial_coefficients')
        require(len(self.axis_tags) >= 3 and len(set(self.axis_tags)) == len(self.axis_tags)
                and all(isinstance(t, str) and len(t) == 4 and t.isascii() for t in self.axis_tags)
                and type(self.signed_factors) is bool
                and all(tag in self.axis_tags[3:] and isinstance(c, np.ndarray)
                        and c.shape == self.coefficients.shape and np.isfinite(c).all()
                        for tag, c in self.factors.items()), 'invalid_polynomial_factor_axes')

    @property
    def supports(self):
        return ([{}] + [{tag: (lo, lo if hi <= 0 else hi, hi)}
                        for tag, (lo, hi) in zip(self.axis_tags[:3], self.bounds)]
                + [{tag: triple} for tag in self.factors
                   for triple in (((-1, -1, 0), (0, 1, 1)) if self.signed_factors
                                  else ((0, 1, 1),))])

    def from_local(self, local):
        local = np.asarray(local, dtype=float)
        lo, hi = self.bounds.T
        return np.where(hi <= 0, hi - local * (hi - lo), lo + local * (hi - lo))

    def to_local(self, locations):
        locations = np.asarray(locations, dtype=float)
        lo, hi = self.bounds.T
        return np.where(hi <= 0, (hi - locations) / (hi - lo), (locations - lo) / (hi - lo))

    def values(self, locations):
        t = self.to_local(locations)
        require(t.ndim == 2 and t.shape[1] == 3 and np.isfinite(t).all()
                and np.all((t >= 0) & (t <= 1)), 'polynomial_evaluation_outside_declared_box')
        v = [t[:, i, None] ** np.arange(4) for i in range(3)]
        return np.einsum('ni,nj,nk,ijkp->np', *v, self.coefficients, optimize=True)

    def evaluate(self, location):
        values = self.values([[location[t] for t in self.axis_tags[:3]]])[0]
        for tag, coefficients in self.factors.items():
            child = PolynomialBox(self.bounds, self.operators, coefficients, {})
            values += np.clip(location[tag], -1 if self.signed_factors else 0, 1) * child.values(
                [[location[t] for t in self.axis_tags[:3]]])[0]
        return control_points(self.operators, values)

    def charstring(self, vsindex):
        if not self.operators:
            return T2CharString(program=[])
        program = [vsindex, 'vsindex']
        regions = len(self.supports) - 1
        stack = maximum = 0

        def push(value):
            nonlocal stack, maximum
            program.append(fixed(float(value)))
            stack += 1
            maximum = max(maximum, stack)
            require(stack <= 513, 'polynomial_blend_operand_stack_overflow')

        def emit(coefs, axis):
            nonlocal stack
            if not np.any(coefs):
                push(0)
                return
            if axis == 3:
                push(coefs)
                return
            emit(coefs[0], axis + 1)
            if len(coefs) == 1 or not np.any(coefs[1:]):
                return
            # c0 + t_axis * (c1 + t_axis * (...)); all three region
            # scalars are selected once, including for recursive operands.
            for region in range(regions):
                if region == axis:
                    emit(coefs[1:], axis)
                else:
                    push(0)
            push(1)
            program[-1] = 1
            program.append('blend')
            stack -= regions + 1

        column = 0
        for operator, count in self.operators:
            for _ in range(count):
                emit(self.coefficients[..., column], 0)
                if any(np.any(c[..., column]) for c in self.factors.values()):
                    for _ in range(3):
                        push(0)
                    for c in self.factors.values():
                        if self.signed_factors:
                            emit(-c[..., column], 0)
                        emit(c[..., column], 0)
                    push(1)
                    program[-1] = 1
                    program.append('blend')
                    stack -= regions + 1
                column += 1
            require(stack == count, 'polynomial_operator_stack_mismatch')
            program.append(operator)
            stack = 0
        self.evidence['maximum_operand_stack'] = maximum
        return T2CharString(program=program)


def interpolate(bounds, operators, evaluate):
    """Fit 64 deterministic Lobatto nodes; no validation points enter the fit."""
    empty = np.zeros((4, 4, 4, sum(n for _, n in operators)))
    model = PolynomialBox(bounds, operators, empty, {'production_accepted': False})
    samples = np.asarray(evaluate(model.from_local(GRID)))
    require(samples.shape == (64, empty.shape[-1]) and np.isfinite(samples).all(),
            'invalid_polynomial_training_samples')
    # Quantize absolute cubic controls, then difference the encoded integers.
    # Rounding relative operands independently accumulates error along paths.
    absolute = np.cumsum(samples.reshape(64, -1, 2), axis=1).reshape(samples.shape)
    coefficients = np.einsum('ia,jb,kc,abcp->ijkp', INVERSE, INVERSE, INVERSE,
                             absolute.reshape(empty.shape), optimize=True)
    encoded = np.floor(coefficients * 65536 + .5) / 65536
    encoded = encoded.reshape(4, 4, 4, -1, 2)
    # The source adapter may certify explicit closure by supplying point pairs.
    # Generic callers with implicit closing edges do not make this assertion.
    for start, end in getattr(evaluate, 'closed_control_pairs', ()):
        require(np.all(np.abs(absolute.reshape(64, -1, 2)[:, start]
                              - absolute.reshape(64, -1, 2)[:, end]) < 1e-9),
                'source_did_not_preserve_certified_closure')
        encoded[..., end, :] = encoded[..., start, :]
    model.coefficients = np.diff(encoded, axis=3, prepend=np.zeros((4, 4, 4, 1, 2))).reshape(empty.shape)
    require(np.all(model.coefficients >= -32768) and np.all(model.coefficients < 32768),
            'polynomial_fixed_coefficient_overflow')
    model.evidence.update(training_count=64, domain_kind='local_polynomial_box',
                          sampled_geometry_passed=False)
    return model
