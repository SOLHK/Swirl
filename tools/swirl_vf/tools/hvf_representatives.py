"""Deterministic HVF structural sampling without native extraction or rendering.

The existing HVGL reader supplies shared DAG metadata. Counts describe expanded
source on/off points and contours, not accepted gvar models or measured error.
Original GIDs/cmap and detailed plans belong only in private build directories.
Authored tests exercise the selector without shipping original font data.

Format reference already used by the shared reader:
https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache

import numpy as np

from hvf import Shape, Composite


REQUIRED_GIDS = (0, 2, 12, 1166, 2335, 19177)
REGIONS = (
    ('Latin_basic', 0x20, 0x7E), ('Latin_extended', 0xA0, 0x24F),
    ('Greek', 0x370, 0x3FF), ('Cyrillic', 0x400, 0x52F),
    ('Hebrew', 0x590, 0x5FF), ('Arabic', 0x600, 0x6FF),
    ('General_punctuation', 0x2000, 0x206F), ('Symbols', 0x2070, 0x2BFF),
    ('CJK_punctuation', 0x3000, 0x303F), ('Hiragana', 0x3040, 0x309F),
    ('Katakana', 0x30A0, 0x30FF), ('Bopomofo', 0x3100, 0x312F),
    ('CJK_extension_A', 0x3400, 0x4DBF), ('CJK_basic', 0x4E00, 0x9FFF),
    ('Hangul', 0xAC00, 0xD7A3), ('Private_use', 0xE000, 0xF8FF),
    ('CJK_compatibility', 0xF900, 0xFAFF), ('Fullwidth', 0xFF00, 0xFFEF),
    ('Supplementary_symbols', 0x1F000, 0x1FAFF),
    ('CJK_extension_B', 0x20000, 0x2A6DF), ('CJK_later_extensions', 0x2A700, 0x323AF),
)
PUNCTUATION = frozenset((0x21, 0x22, 0x27, 0x28, 0x29, 0x2C, 0x2E, 0x3A, 0x3B, 0x3F,
                         0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026,
                         0x3001, 0x3002, 0x3008, 0x3009, 0x300A, 0x300B,
                         0xFF01, 0xFF08, 0xFF09, 0xFF0C, 0xFF0E, 0xFF1A, 0xFF1B, 0xFF1F))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def hvf_metadata(table, glyph_count=None):
    """Summarize visible GIDs using cached structure, never coordinate evaluation.

    Shared descendants are summarized once; repeated child occurrences still
    contribute repeatedly to a root's expanded point/contour count. This is
    suitable for the full original GID range without one native process per GID.
    """
    count = table.glyph_count if glyph_count is None else glyph_count
    require(type(count) is int and 1 <= count <= table.glyph_count <= 65535,
            'representative_glyph_count_invalid')
    active = set()

    @lru_cache(maxsize=None)
    def summary(index):
        require(index not in active and len(active) < 256, 'representative_cyclic_or_deep_HVF_structure')
        active.add(index)
        part = table.part(index)
        if isinstance(part, Shape):
            sizes = [size for size in part.path_sizes if size >= 3]
            result = (sum(sizes)*2, len(sizes), 1, 1, tuple(sorted(set(part.blends))), False)
        else:
            require(isinstance(part, Composite), 'representative_unknown_HVF_part')
            children = [summary(child) for child, _, _ in part.subparts]
            result = (sum(c[0] for c in children), sum(c[1] for c in children),
                      1+max((c[2] for c in children), default=0), sum(c[3] for c in children),
                      tuple(sorted(set().union(*(set(c[4]) for c in children)))),
                      bool(np.any(part.rotations.master_values) or np.any(part.rotations.extreme_values))
                      or any(c[5] for c in children))
        active.remove(index)
        return result

    rows = []
    for gid in range(count):
        part = table.part(gid)
        points, contours, depth, leaves, tangents, rotation = summary(gid)
        rows.append({'gid': gid, 'point_count': points, 'contour_count': contours,
            'depth': depth, 'leaf_occurrences': leaves, 'is_composite': isinstance(part, Composite),
            'root_axis_count': int(part.axis_count), 'tangent_types': list(tangents),
            'has_rotation': rotation})
    return rows


def _checked_metadata(metadata):
    require(type(metadata) in (list, tuple) and metadata, 'representative_metadata_required')
    rows = {}
    for value in metadata:
        require(type(value) is dict and type(value.get('gid')) is int and 0 <= value['gid'] <= 65534
                and value['gid'] not in rows, 'representative_GID_invalid_or_duplicate')
        require(all(type(value.get(key)) is int and value[key] >= (1 if key == 'depth' else 0)
                    for key in ('point_count', 'contour_count', 'depth', 'leaf_occurrences', 'root_axis_count'))
                and value['root_axis_count'] <= 64 and type(value.get('is_composite')) is bool
                and type(value.get('has_rotation')) is bool, 'representative_complexity_invalid')
        tangents = value.get('tangent_types')
        require(type(tangents) in (list, tuple) and all(type(t) is int and 0 <= t <= 4 for t in tangents)
                and list(tangents) == sorted(set(tangents)), 'representative_tangent_classes_invalid')
        rows[value['gid']] = {key: value[key] for key in
            ('gid', 'point_count', 'contour_count', 'depth', 'leaf_occurrences', 'is_composite',
             'root_axis_count', 'tangent_types', 'has_rotation')}
        rows[value['gid']]['tangent_types'] = list(tangents)
    return rows


def select_representatives(metadata, cmap_gid, *, count=100, required_gids=REQUIRED_GIDS):
    """Return a stable exact-size plan from structure and Unicode→GID metadata.

    Required historical cases precede coverage/extreme selection. Remaining
    slots sample deterministic ranks across the entire complexity distribution.
    No source coordinates, observations or pass/fail fitting affect selection.
    """
    rows = _checked_metadata(metadata)
    require(type(count) is int and 1 <= count <= len(rows), 'representative_count_invalid')
    require(type(required_gids) in (list, tuple) and len(set(required_gids)) == len(required_gids)
            and all(type(gid) is int and gid in rows for gid in required_gids)
            and len(required_gids) <= count, 'representative_required_GIDs_invalid')
    require(type(cmap_gid) is dict and all(type(cp) is int and 0 <= cp <= 0x10FFFF
            and type(gid) is int and gid in rows for cp, gid in cmap_gid.items()), 'representative_cmap_invalid')
    buckets = {name: set() for name, _, _ in REGIONS}
    buckets.update(Punctuation=set(), Digits=set(), Latin_uppercase=set(), Latin_lowercase=set())
    for cp, gid in cmap_gid.items():
        for name, first, last in REGIONS:
            if first <= cp <= last:
                buckets[name].add(gid)
        if cp in PUNCTUATION:
            buckets['Punctuation'].add(gid)
        if 0x30 <= cp <= 0x39:
            buckets['Digits'].add(gid)
        if 0x41 <= cp <= 0x5A:
            buckets['Latin_uppercase'].add(gid)
        if 0x61 <= cp <= 0x7A:
            buckets['Latin_lowercase'].add(gid)
    selected = {}

    def choose(gid, reason):
        if gid not in selected and len(selected) < count:
            selected[gid] = []
        if gid in selected and reason not in selected[gid]:
            selected[gid].append(reason)

    def extremes(ids, reason, key, amount=1):
        for gid in sorted(ids, key=lambda gid: (*key(rows[gid]), gid))[:amount]:
            choose(gid, reason)

    for gid in required_gids:
        choose(gid, 'required_historical_case')
    categories = (
        ('measured_structure_empty', lambda r: r['point_count'] == 0),
        ('direct_shape', lambda r: not r['is_composite'] and r['point_count'] > 0),
        ('composite', lambda r: r['is_composite'] and r['point_count'] > 0),
        ('single_contour', lambda r: r['contour_count'] == 1),
        ('multiple_contours', lambda r: r['contour_count'] >= 2),
        ('many_contours', lambda r: r['contour_count'] >= 8),
        ('rotation', lambda r: r['has_rotation']),
    )
    for reason, predicate in categories:
        extremes([gid for gid, row in rows.items() if predicate(row)], reason,
                 lambda r: (r['point_count'], r['contour_count'], r['depth']))
    for axis_count in sorted({r['root_axis_count'] for r in rows.values()}):
        extremes([gid for gid, row in rows.items() if row['root_axis_count'] == axis_count],
                 f'root_axes_{axis_count}', lambda r: (r['point_count'],))
    for tangent in sorted({kind for row in rows.values() for kind in row['tangent_types']}):
        extremes([gid for gid, row in rows.items() if tangent in row['tangent_types']],
                 f'tangent_type_{tangent}', lambda r: (r['point_count'],))
    extremes(rows, 'largest_point_count', lambda r: (-r['point_count'], -r['contour_count']), 8)
    extremes(rows, 'largest_contour_count', lambda r: (-r['contour_count'], -r['point_count']), 4)
    extremes(rows, 'deepest_hierarchy', lambda r: (-r['depth'], -r['point_count']), 4)
    for name, ids in buckets.items():
        if ids:
            ordered = sorted(ids, key=lambda gid: (rows[gid]['point_count'], rows[gid]['contour_count'], gid))
            choose(ordered[0], 'unicode_'+name+'_simple')
            choose(ordered[-1], 'unicode_'+name+'_complex')
    remaining = sorted(set(rows)-set(selected), key=lambda gid:
        (rows[gid]['point_count'], rows[gid]['contour_count'], rows[gid]['depth'], gid))
    needed = count-len(selected)
    for i in range(needed):
        choose(remaining[(2*i+1)*len(remaining)//(2*needed)], 'complexity_rank_sample')
    gids = sorted(selected)
    require(len(gids) == count and set(required_gids) <= set(gids), 'representative_selection_incomplete')

    def coverage(ids):
        values = [rows[gid] for gid in ids]
        return {'glyphs': len(ids), 'empty_glyphs': sum(r['point_count'] == 0 for r in values),
            'composites': sum(r['is_composite'] for r in values),
            'direct_shapes': sum(not r['is_composite'] for r in values),
            'maximum_point_count': max(r['point_count'] for r in values),
            'maximum_contour_count': max(r['contour_count'] for r in values),
            'maximum_depth': max(r['depth'] for r in values),
            'rotation_glyphs': sum(r['has_rotation'] for r in values),
            'root_axis_counts': dict(sorted(Counter(r['root_axis_count'] for r in values).items())),
            'tangent_types': sorted({kind for r in values for kind in r['tangent_types']}),
            'unicode_region_GID_counts': {name: len(set(ids)&bucket) for name, bucket in buckets.items() if bucket}}
    return {'schema': 1, 'status': 'DETERMINISTIC_METADATA_SAMPLE_NOT_FONT_ACCEPTANCE',
        'gids': gids, 'reasons': {str(gid): selected[gid] for gid in gids},
        'selected_metadata': [rows[gid] for gid in gids],
        'coverage': {'pool': coverage(rows), 'selected': coverage(gids)},
        'required_gids': list(required_gids), 'native_calls': 0, 'geometry_evaluated': False,
        'complexity_basis': 'HVF_DAG_EXPANDED_ON_OFF_POINT_AND_CONTOUR_COUNTS',
        'sample_error_measured': False, 'production_accepted': False}
