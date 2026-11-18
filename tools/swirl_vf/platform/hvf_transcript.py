"""Validate complete native HVF transcripts without retaining outline data.

Counts alone cannot prove GID coverage: a duplicated, reordered or unrelated
record must never replace a missing glyph. This validator also checks the
callback grammar, finite coordinates, axis application and terminal receipt.
It establishes extraction coverage, not user-axis mapping or font equivalence.
"""
from __future__ import annotations

import collections
import json
import math


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    return type(value) is int and value >= 0


def validate_events(events, counters, total_parts):
    require(type(events) is list and type(counters) is dict, 'HVF callback arrays missing')
    lengths = {'begin_part': 2, 'end_part': 2, 'begin_path': 1, 'end_path': 1,
               'move': 3, 'line': 3, 'quad': 5, 'cubic': 7, 'close': 1}
    names = {'begin_part': 'parts_begun', 'end_part': 'parts_ended',
             'begin_path': 'paths_begun', 'end_path': 'paths_ended', 'move': 'moves',
             'line': 'lines', 'quad': 'quads', 'cubic': 'cubics', 'close': 'closes'}
    actual = dict.fromkeys(['events', *names.values()], 0)
    stack, in_path, moved, closed = [], False, False, False
    for event in events:
        require(type(event) is list and event and type(event[0]) is str
                and event[0] in lengths and len(event) == lengths[event[0]], 'HVF callback shape invalid')
        kind = event[0]
        actual['events'] += 1
        actual[names[kind]] += 1
        if kind in ('begin_part', 'end_part'):
            require(not in_path and integer(event[1]) and event[1] < total_parts,
                    'HVF part identity/path nesting invalid')
            if kind == 'begin_part':
                stack.append(event[1])
            else:
                require(stack and stack.pop() == event[1], 'HVF part callbacks unbalanced')
        elif kind == 'begin_path':
            require(stack and not in_path, 'HVF path nesting invalid')
            in_path, moved, closed = True, False, False
        elif kind == 'end_path':
            require(in_path and (not moved or closed), 'HVF path is not closed')
            in_path = False
        elif kind == 'close':
            require(in_path and moved and not closed, 'HVF close without open contour')
            closed = True
        else:
            require(in_path and not closed and (not moved if kind == 'move' else moved),
                    'HVF drawing callback outside contour')
            require(all(type(v) in (int, float) and math.isfinite(v) for v in event[1:]),
                    'HVF nonfinite coordinate')
            moved = True
    require(not stack and not in_path, 'HVF unterminated callback stream')
    require(set(counters) == set(actual) and all(integer(v) for v in counters.values())
            and counters == actual, 'HVF callback counters differ')
    return actual


def validate_transcript(path, *, face, coords, start, count, parts, input_bytes):
    """Read one bounded transcript and reject incomplete/duplicate coverage."""
    header = final = None
    outlines = failed = empty = 0
    totals = collections.Counter()
    with open(path, encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            require(type(row) is dict and final is None, 'HVF data after terminal receipt')
            kind = row.get('record')
            if header is None:
                require(kind == 'header' and row.get('schema') == 1
                        and row.get('engine') == 'Apple HVF'
                        and row.get('coordinate_space') == 'normalized_design_after_avar'
                        and row.get('metrics') == 'NOT_EXTRACTED'
                        and row.get('user_axis_mapping') == 'NOT_TESTED', 'HVF header missing or changed')
                for key in ('input_bytes', 'face_index', 'face_count', 'maxp_glyphs',
                            'hvf_visible_parts', 'hvf_total_parts', 'start', 'count'):
                    require(integer(row.get(key)), 'HVF header integer missing: '+key)
                available = row['hvf_total_parts'] if parts else row['maxp_glyphs']
                require(row['face_index'] == face < row['face_count']
                        and row['input_bytes'] == input_bytes and row['start'] == start
                        and start <= available and row['count'] == (count or available-start)
                        and start + row['count'] <= available, 'HVF request/header mismatch')
                axes = row.get('fvar_axis_tags')
                require(type(axes) is list and len(axes) == len(coords)
                        and len(set(axes)) == len(axes)
                        and all(type(a) is str and len(a) == 4 for a in axes)
                        and row.get('normalized_coords') == list(coords), 'HVF axis request mismatch')
                header = row
            elif kind == 'outline':
                require(integer(row.get('part_index')) and row['part_index'] == start + outlines
                        and outlines < header['count'], 'HVF GID coverage missing, duplicate or reordered')
                require(row.get('status') in ('OK', 'FAILED') and type(row.get('native_code')) is int,
                        'HVF outline verdict missing')
                outlines += 1
                if row['status'] == 'FAILED':
                    failed += 1
                    continue
                require(row['native_code'] == 0 and integer(row.get('part_axis_count'))
                        and row['part_axis_count'] <= len(coords)
                        and row.get('applied_axis_count') == row['part_axis_count'],
                        'HVF axes not applied or renderer failed')
                actual = validate_events(row.get('events'), row.get('counters'), header['hvf_total_parts'])
                totals.update(actual)
                empty += actual['moves'] == 0
            elif kind == 'summary':
                require(outlines == header['count'] and integer(row.get('rendered'))
                        and integer(row.get('failed')) and row['rendered'] == outlines-failed
                        and row['failed'] == failed
                        and row.get('status') == ('FAILED' if failed else 'EXTRACTED')
                        and row.get('preservation_verdict') == 'NOT_EVALUATED',
                        'HVF terminal coverage/verdict mismatch')
                final = row
            else:
                raise ValueError('HVF unexpected record')
    require(header is not None and final is not None, 'HVF transcript incomplete')
    return {'counts': {'headers': 1, 'outlines': outlines, 'failed_outlines': failed, 'summaries': 1},
            'native_header': header, 'native_summary': final, 'empty_outlines': empty,
            'callback_counts': dict(totals), 'ordered_complete_GID_coverage': True,
            'finite_closed_successful_outlines': outlines-failed}
