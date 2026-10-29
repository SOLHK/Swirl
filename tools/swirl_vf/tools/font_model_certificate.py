"""Continuous exact certificates for serialized expanded standard glyph models.

This adapts actual reopened glyf/gvar and HVAR/VVAR data to continuous_model.
It proves ideal coefficient arithmetic in a supplied design-domain transform;
it does not prove source user mapping, avar behavior, native rounding, layout,
rasterization, or whole-font equivalence. No supplied font is modified or saved
to disk. Unsupported implicit contour interpolation and composites are refused.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import io
from math import prod

from fontTools.ttLib import TTFont

from continuous_model import (AxisSupport, EndpointTransform, VectorModel,
                              VectorRegion, certify_difference)
from metric_variations import _stored_model, _support_key, verify_metric_variations


AXIS_ORDERS = (('XWDT', 'XWGT', 'XHGT'), ('WDTH', 'wght', 'HGHT'))
REQUIRED = frozenset(('head', 'maxp', 'glyf', 'gvar', 'fvar', 'hmtx', 'vmtx', 'HVAR', 'VVAR'))
LIMIT = Fraction(1, 32)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _tags(font):
    require(REQUIRED <= set(font.keys()), 'certificate_standard_variation_tables_required')
    tags = tuple(axis.axisTag for axis in font['fvar'].axes)
    require(tags in AXIS_ORDERS, 'certificate_fixed_three_axis_order_required')
    return tags


def _integer(value):
    require(type(value) in (int, float) and value == int(value), 'certificate_integer_model_value_required')
    return int(value)


def _supports(key):
    return tuple(None if peak == 0 else AxisSupport(
        Fraction(int(low * 16384), 16384), Fraction(int(peak * 16384), 16384),
        Fraction(int(high * 16384), 16384)) for low, peak, high in key)


def _profile(font, max_points):
    _tags(font)
    order = font.getGlyphOrder()
    require(order and len(order) == font['maxp'].numGlyphs and len(set(order)) == len(order),
            'certificate_glyph_order_or_count_invalid')
    require(set(font['glyf'].glyphs) == set(order)
            and set(font['gvar'].variations) <= set(order), 'certificate_glyph_table_coverage_invalid')
    total = 0
    for name in order:
        glyph = font['glyf'][name]
        require(not glyph.isComposite(), 'certificate_expanded_simple_glyphs_required')
        coordinates, ends, flags = glyph.getCoordinates(font['glyf'])
        require(glyph.numberOfContours == len(ends) and len(flags) == len(coordinates),
                'certificate_simple_topology_invalid')
        require(all(int(flag) & ~0x41 == 0 for flag in flags), 'certificate_nonstandard_contour_flags')
        total += len(coordinates) + 4
        require(total <= max_points, 'certificate_point_budget_exceeded')
        for variation in font['gvar'].variations.get(name, []):
            require(len(variation.coordinates) == len(coordinates) + 4,
                    'certificate_gvar_point_count_including_phantoms')
            require(all(pair is not None for pair in variation.coordinates),
                    'certificate_IUP_or_omitted_point_not_supported')
    return order, total


def _snapshot(font):
    try:
        candidate = copy.deepcopy(font)
        candidate.recalcTimestamp = False
        stream = io.BytesIO()
        candidate.save(stream)
        return TTFont(io.BytesIO(stream.getvalue()), lazy=False, recalcTimestamp=False)
    except Exception as error:
        raise ValueError('certificate_font_serialization_failed') from error


def advance_models(font):
    """Read all HVAR/VVAR advances from an actual serialized/reopened TTFont.

    Returned keys are (table kind, physical glyph name). Every GID is included,
    including constant/zero models. Optional bearing/origin maps are refused by
    the shared existing exact metric extractor, rather than silently ignored.
    """
    require(isinstance(font, TTFont) and font.reader is not None,
            'certificate_reopened_font_required')
    tags = _tags(font)
    models = {}
    try:
        for name in font.getGlyphOrder():
            for kind, metric in (('HVAR', 'hmtx'), ('VVAR', 'vmtx')):
                base = _integer(font[metric].metrics[name][0])
                stored = _stored_model(font, kind, name, tags)
                regions = tuple(VectorRegion(_supports(key), (_integer(delta),))
                                for key, delta in stored.items())
                models[kind, name] = VectorModel((base,), regions)
    except (KeyError, IndexError, AttributeError, TypeError) as error:
        raise ValueError('certificate_metric_model_decode_failed') from error
    return models


def _point_models(font, name):
    tags = _tags(font)
    glyf = font['glyf']
    coordinates, controls = glyf._getCoordinatesAndControls(
        name, font['hmtx'].metrics, font['vmtx'].metrics)
    bases = [tuple(_integer(value) for value in pair) for pair in coordinates]
    regions = [[] for _ in bases]
    for variation in font['gvar'].variations.get(name, []):
        key = _support_key(variation.axes, tags)
        support = _supports(key)
        require(len(variation.coordinates) == len(bases), 'certificate_gvar_point_count_including_phantoms')
        for index, pair in enumerate(variation.coordinates):
            require(pair is not None and len(pair) == 2, 'certificate_IUP_or_omitted_point_not_supported')
            # Zero coefficients remain explicit and their support is validated.
            regions[index].append(VectorRegion(support, tuple(_integer(value) for value in pair)))
    topology = (controls.numberOfContours, tuple(controls.endPts), tuple(controls.flags))
    return topology, tuple(VectorModel(base, tuple(parts)) for base, parts in zip(bases, regions))


def _vertices(source, target, transform):
    """Work-budget planning only; continuous_model owns evaluation/proof."""
    planes = [set((Fraction(-1), Fraction(0), Fraction(1))) for _ in range(3)]
    for model, is_source in ((source, True), (target, False)):
        for region in model.regions:
            for axis, support in enumerate(region.supports):
                if support is None or support.peak == 0:
                    continue
                for knot in (support.start, support.peak, support.end):
                    if is_source:
                        knot /= transform.negative_spans[axis] if knot < 0 else transform.positive_spans[axis]
                    if -1 <= knot <= 1:
                        planes[axis].add(knot)
    return prod(len(values) for values in planes)


def certify_font_models(source, target, transform=EndpointTransform(), *,
                        target_upem_multiplier=1, max_vertices=100000, max_points=4096):
    """Certify every supplied standard point/phantom and advance continuously.

    max_points counts outline plus four phantom points per source/target pair.
    max_vertices bounds the total evaluations across all point and metric
    models. The complete work plan is checked before any exact evaluation.
    Failures/unsupported encodings are never converted into partial acceptance.
    """
    require(isinstance(source, TTFont) and isinstance(target, TTFont)
            and type(transform) is EndpointTransform, 'certificate_fonts_and_transform_required')
    require(type(max_points) is int and max_points > 0
            and type(max_vertices) is int and max_vertices > 0, 'certificate_finite_positive_budgets_required')
    require(type(target_upem_multiplier) in (int, Fraction) and target_upem_multiplier > 0,
            'certificate_exact_positive_upem_multiplier_required')
    multiplier = Fraction(target_upem_multiplier)
    _profile(source, max_points)
    _profile(target, max_points)
    source, target = _snapshot(source), _snapshot(target)
    try:
        left_order, count = _profile(source, max_points)
        right_order, right_count = _profile(target, max_points)
        require(len(left_order) == len(right_order) and count == right_count,
                'certificate_physical_glyph_or_point_count_differs')
        require(Fraction(target['head'].unitsPerEm, source['head'].unitsPerEm) == multiplier,
                'certificate_declared_upem_ratio_differs')
        # Enforce both independent encodings; neither a mismatched metric table
        # nor matching point geometry alone can establish this certificate.
        verify_metric_variations(source)
        verify_metric_variations(target)
        left_metrics, right_metrics = advance_models(source), advance_models(target)
        work = []
        for gid, (left_name, right_name) in enumerate(zip(left_order, right_order)):
            left_topology, left_points = _point_models(source, left_name)
            right_topology, right_points = _point_models(target, right_name)
            require(left_topology == right_topology and len(left_points) == len(right_points),
                    'certificate_same_gid_contour_topology_differs')
            for index, (a, b) in enumerate(zip(left_points, right_points)):
                work.append(('point', gid, index, a, b, _vertices(a, b, transform)))
            for kind in ('HVAR', 'VVAR'):
                a, b = left_metrics[kind, left_name], right_metrics[kind, right_name]
                work.append((kind, gid, None, a, b, _vertices(a, b, transform)))
        total_vertices = sum(item[-1] for item in work)
        require(total_vertices <= max_vertices, 'certificate_global_vertex_budget_exceeded')
        point_max = metric_max = Fraction(0)
        points_checked = metric_checked = 0
        for kind, _, _, a, b, vertices in work:
            proof = certify_difference(a, b, transform, target_upem_multiplier=multiplier,
                                       max_vertices=vertices)
            require(proof.vertex_count == vertices, 'certificate_vertex_plan_differs')
            if kind == 'point':
                point_max = max(point_max, proof.max_squared_norm)
                points_checked += 1
            else:
                metric_max = max(metric_max, proof.max_abs_component)
                metric_checked += 1
        within = point_max <= LIMIT**2 and metric_max <= LIMIT
        return {
            'status': 'CERTIFIED_CONTINUOUS_STANDARD_DESIGN_MODELS' if within else 'CONTINUOUS_STANDARD_MODEL_LIMIT_EXCEEDED',
            'max_point_squared_error': point_max, 'max_metric_error': metric_max,
            'points_checked': points_checked, 'metric_models_checked': metric_checked,
            'glyphs_checked': len(left_order), 'phantom_points_checked': 4 * len(left_order),
            'outline_points_checked': points_checked - 4 * len(left_order),
            'vertex_evaluations': total_vertices, 'target_upem_multiplier': multiplier,
            'point_squared_limit': LIMIT**2, 'metric_limit': LIMIT,
            'within_1_32': within, 'design_domain_only': True,
            'serialized_models_reopened': True, 'metric_encodings_exactly_consistent': True,
            'ideal_model_arithmetic_only': True, 'native_execution': False,
            'source_user_mapping_accepted': False, 'avar_user_mapping_accepted': False,
            'font_conversion_accepted': False, 'whole_font_equivalence_accepted': False,
        }
    finally:
        source.close()
        target.close()
