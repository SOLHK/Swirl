"""Experimental exact closure-point compaction; production C1 is unchanged.

Remove only a simple contour's terminal on-curve duplicate when its base and
every complete gvar tuple delta exactly equal the first on-curve point. The
last four phantom entries are remapped unchanged. Incomplete/IUP tuples or
different endpoint deltas make the contour ineligible; hints are rejected.
No comparator, tolerance, metric, axis, source object or font file is changed.

Primary precedent: fontTools TTGlyphPen.closePath removes an equal explicit
closing point; its point-pen adapter additionally checks both on-curve flags.
The additional full-gvar coefficient proof here is independently implemented.
https://fonttools.readthedocs.io/en/latest/_modules/fontTools/pens/ttGlyphPen.html
https://fonttools.readthedocs.io/en/latest/_modules/fontTools/pens/pointPen.html
https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats
"""
from __future__ import annotations

import array
from bisect import bisect_right
import copy
import math

from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _point(point):
    return (isinstance(point, (tuple, list)) and len(point) == 2
            and all(type(value) in (int, float) and math.isfinite(value) for value in point))


def compact_closing_points(glyph, variations):
    """Return detached (simple Glyph, full TupleVariation list, scalar stats)."""
    contours = getattr(glyph, 'numberOfContours', None)
    require(type(contours) is int and contours >= 0, 'simple_expanded_glyph_required')
    program = getattr(glyph, 'program', None)
    require(program is None or not program.getBytecode(), 'hint_program_not_supported')
    coordinates = getattr(glyph, 'coordinates', ())
    flags = getattr(glyph, 'flags', ())
    ends = list(getattr(glyph, 'endPtsOfContours', ()))
    count = len(coordinates)
    require(len(flags) == count and len(ends) == contours
            and (not ends and count == 0 or ends and ends[-1] == count - 1)
            and all(type(end) is int and 0 <= end < count for end in ends)
            and all(a < b for a, b in zip(ends, ends[1:])), 'invalid_glyph_point_counts')
    require(type(variations) in (tuple, list)
            and all(isinstance(variation, TupleVariation)
                    and len(variation.coordinates) == count + 4 for variation in variations),
            'full_tuple_point_count_required')
    require(all(point is None or _point(point) for variation in variations
                for point in variation.coordinates), 'invalid_tuple_coordinate')
    incomplete = any(point is None for variation in variations for point in variation.coordinates)
    removed, skipped = [], {'incomplete_tuple': 0, 'different_endpoint_delta': 0}
    start = 0
    for end in ends:
        if (end > start and flags[start] & 1 and flags[end] & 1
                and coordinates[start] == coordinates[end]):
            if incomplete:
                skipped['incomplete_tuple'] += 1
            elif any(variation.coordinates[start] != variation.coordinates[end] for variation in variations):
                skipped['different_endpoint_delta'] += 1
            else:
                removed.append(end)
        start = end + 1
    removed_set = set(removed)
    kept = [index for index in range(count) if index not in removed_set]
    output = copy.deepcopy(glyph)
    output.coordinates = GlyphCoordinates([coordinates[index] for index in kept])
    output.flags = array.array('B', [flags[index] for index in kept])
    output.endPtsOfContours = [end - bisect_right(removed, end) for end in ends]
    tuples = copy.deepcopy(list(variations))
    remapped = kept + list(range(count, count + 4))
    for output_tuple, source_tuple in zip(tuples, variations):
        output_tuple.coordinates = [copy.deepcopy(source_tuple.coordinates[index]) for index in remapped]
    return output, tuples, {
        'removed_terminal_points': len(removed), 'removed_original_indices': removed,
        'source_point_count': count, 'target_point_count': len(kept),
        'contour_count': contours, 'tuple_count': len(tuples), 'skipped': skipped,
        'proof': 'EXACT_BASE_AND_EVERY_FULL_TUPLE_ENDPOINT_EQUALITY',
        'phantom_entries_preserved': True, 'internal_points_preserved': True,
        'production_accepted': False,
    }
