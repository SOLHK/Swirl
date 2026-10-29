"""Experimental HVF geometry -> standard glyf/gvar through existing C1 code.

This flattens an HVF DAG; contour provenance survives separately, component
structure does not. BatchGeometry is a portable interpretation, not an Apple
oracle. Caller-supplied table metrics are explicitly not native observations.
Failed 1/32 source-unit sample checks return a failed experimental model; no
production gate, tolerance, source coordinate or original font is changed.

Reuses fontTools VariationModel/TupleVariation through reconstruct_glyph;
https://fonttools.readthedocs.io/en/latest/varLib/models.html
https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html
"""
from __future__ import annotations

from dataclasses import asdict
import math
import numpy as np

from batch_geometry import BatchGeometry, ContourSource
from rebuild import reconstruct_glyph

LIMIT = 1 / 32
METRICS = ('advance_width', 'advance_height', 'lsb', 'horizontal_origin_x',
           'vertical_origin_x', 'vertical_origin_y')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _commands(paths, sample, multiplier):
    result = []
    for path in paths:
        points = path[sample] * multiplier
        result.append(['moveTo', *map(float, points[0])])
        # HVF pairs are (on_i, off_i), with Q_i ending at on_(i+1).
        # C1 retains an explicit duplicate on_0 at the closing endpoint.
        for index in range(0, len(points), 2):
            result.append(['qCurveTo', *map(float, points[index + 1]),
                           *map(float, points[(index + 2) % len(points)])])
        result.append(['closePath'])
    return result


def build_glyph_model(table, glyph_id, axis_tags, training_locations, holdout_locations,
                      metric_records, *, source_upem, multiplier=1, isolated_tangents=False):
    """Return (Glyph, tuples, hmtx, vmtx, report), including failed candidates.

    Locations are q-space dictionaries, in axis_tags order. Metric records are
    ordered training then holdout and contain all six METRICS fields. They must
    be actual caller-selected table values, never invented HVF-native metrics.
    The multiplier scales points and metric records before C1 integer encoding;
    the host font must use returned target_units_per_em at the same physical
    output size. This function does not build or accept a complete font.
    """
    require(type(source_upem) is int and type(multiplier) is int and multiplier >= 1
            and 16 <= source_upem <= source_upem * multiplier <= 16384,
            'invalid_physical_precision_grid')
    require(type(axis_tags) in (list, tuple) and 1 <= len(axis_tags) <= 3
            and all(type(tag) is str and len(tag) == 4 and tag.isascii() for tag in axis_tags)
            and len(set(axis_tags)) == len(axis_tags), 'invalid_model_axis_tags')
    require(type(training_locations) is list and training_locations
            and type(holdout_locations) is list and holdout_locations,
            'training_and_independent_holdouts_required')
    locations = training_locations + holdout_locations
    require(len(locations) <= 1024 and all(type(location) is dict
            and set(location) == set(axis_tags)
            and all(type(v) in (int, float) and math.isfinite(v) and -1 <= v <= 1
                    for v in location.values()) for location in locations),
            'invalid_model_q_locations')
    require(all(location not in training_locations for location in holdout_locations),
            'holdouts_must_be_independent_of_training')
    require(type(metric_records) in (list, tuple) and len(metric_records) == len(locations)
            and all(type(record) is dict and all(field in record
                    and type(record[field]) in (int, float) and math.isfinite(record[field])
                    for field in METRICS) for record in metric_records),
            'explicit_finite_table_metric_records_required')
    root = table.part(glyph_id)
    require(root.axis_count <= len(axis_tags), 'HVF_root_axes_exceed_model_axes')
    coordinates = np.asarray([[location[tag] for tag in axis_tags[:root.axis_count]]
                              for location in locations], dtype=float)
    batch = BatchGeometry(table, isolated_tangents=isolated_tangents).render(glyph_id, coordinates)
    require(batch.sample_count == len(locations) and len(batch.paths) == len(batch.sources)
            and all(isinstance(source, ContourSource) for source in batch.sources),
            'inconsistent_HVF_contour_provenance')
    require(all(isinstance(path, np.ndarray) and path.ndim == 3
                and path.shape[0] == len(locations) and path.shape[2] == 2
                and path.shape[1] >= 6 and path.shape[1] % 2 == 0
                and np.isfinite(path).all() for path in batch.paths),
            'unsupported_HVF_point_topology')
    records = [dict(commands=_commands(batch.paths, n, multiplier), location=location,
                    **{field: float(metrics[field]) * multiplier for field in METRICS})
               for n, (location, metrics) in enumerate(zip(locations, metric_records))]
    training_count = len(training_locations)
    glyph, tuples, horizontal, vertical, evidence = reconstruct_glyph(
        records[:training_count], records[training_count:], training_locations,
        holdout_locations, dict.fromkeys(axis_tags), None, None,
        outline_limit=LIMIT * multiplier, metric_limit=LIMIT * multiplier)
    passed = not evidence['failures']
    report = {
        'status': 'PASS_EXPERIMENTAL_SAMPLES_ONLY' if passed else 'FAIL_STRICT_EXPERIMENTAL_SAMPLES',
        'glyph_id': glyph_id, 'backend': BatchGeometry.backend,
        'source_units_per_em': source_upem, 'target_units_per_em': source_upem * multiplier,
        'physical_grid_multiplier': multiplier, 'scale_before_integer_encoding': True,
        'strict_limit_source_font_units': LIMIT,
        'max_point_error_source_units': evidence['max_point_error_units'] / multiplier,
        'max_outline_error_bound_source_units': evidence['max_outline_error_bound_units'] / multiplier,
        'max_metric_error_source_units': evidence['max_metric_error_units'] / multiplier,
        'strict_sample_check_passed': passed,
        'metrics_provenance': 'CALLER_SUPPLIED_TABLE_RECORDS_NOT_NATIVE',
        'source_contours': [asdict(source) for source in batch.sources],
        'HVF_DAG_flattened': True, 'original_component_structure_preserved': False,
        'explicit_closing_oncurve_duplicate': True,
        'native_geometry_validation': 'NOT_RUN', 'native_metrics_validation': 'NOT_RUN',
        'source_user_mapping_accepted': False, 'continuous_space_proof': False,
        'production_accepted': False, 'font_only_equivalence_accepted': False,
        'target_design_unit_evidence': evidence,
    }
    return glyph, tuples, horizontal, vertical, report
