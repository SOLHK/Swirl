"""Read-only TTC structure/variation census; never exports outline coordinates.

fontTools 4.61.1 supplies the SFNT and tuple parsers (MIT). Inspect physical
table offsets, not decompiled-object identity, when reporting TTC sharing.
The optional complete gvar census consumes one glyph's tuples at a time.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import time

from fontTools.ttLib import TTCollection


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def tuple_census(font):
    variations = font['gvar'].variations
    counts, patterns = Counter(), Counter()
    supports = Counter()
    maximum = 0
    for name in font.getGlyphOrder():
        tuples = variations[name]
        maximum = max(maximum, len(tuples))
        counts['glyphs'] += 1
        counts['variable_glyphs'] += bool(tuples)
        seen = set()
        for variation in tuples:
            active = tuple(sorted(tag for tag, (_, peak, _) in variation.axes.items() if peak))
            patterns['+'.join(active) or 'constant'] += 1
            signature = tuple(sorted((k, tuple(v)) for k, v in variation.axes.items()))
            counts['repeated_region_in_glyph'] += signature in seen
            seen.add(signature)
            supports[signature] += 1
            counts['tuples'] += 1
            missing = sum(point is None for point in variation.coordinates)
            counts['tuples_with_inferred_points'] += bool(missing)
            counts['inferred_points'] += missing
            counts['explicit_points'] += len(variation.coordinates) - missing
            counts['all_zero_or_inferred_tuples'] += all(p is None or p == (0, 0) for p in variation.coordinates)
        # LazyDict caches decompiled tuples. This census never revisits a glyph.
        del variations[name]
    return dict(counts=counts, axis_patterns=patterns, unique_regions=len(supports),
                maximum_tuples_per_glyph=maximum)


def avar_summary(font):
    raw = font.reader['avar']
    major, minor, _, count = struct.unpack_from('>4H', raw)
    offset, axes = 8, []
    for axis in font['fvar'].axes[:count]:
        n, = struct.unpack_from('>H', raw, offset)
        offset += 2
        records = [struct.unpack_from('>hh', raw, offset + 4*i) for i in range(n)]
        offset += 4*n
        xs, ys = zip(*records)
        axes.append(dict(tag=axis.axisTag, record_count=n,
                         duplicate_inputs=n-len(set(xs)),
                         strictly_increasing_inputs=all(a < b for a, b in zip(xs, xs[1:])),
                         nondecreasing_outputs=all(a <= b for a, b in zip(ys, ys[1:]))))
    return dict(version=[major, minor], axes=axes)


def inspect(path, *, census=False):
    path = Path(path)
    start = time.monotonic()
    result = dict(schema=1, filename=path.name, bytes=path.stat().st_size,
                  sha256=sha256(path), faces=[], gvar_census_scope='ALL_GLYPHS' if census else 'NOT_RUN')
    hashes, stats, shared = {}, {}, {}
    with TTCollection(path, lazy=True, shareTables=False) as collection:
        for index, font in enumerate(collection.fonts):
            name = font['name']
            tables = {}
            for tag, entry in font.reader.tables.items():
                key = (entry.offset, entry.length)
                if key not in hashes:
                    hashes[key] = hashlib.sha256(font.reader[tag]).hexdigest()
                tables[tag] = dict(offset=entry.offset, bytes=entry.length, sha256=hashes[key])
                shared.setdefault(key, []).append([index, tag])
            face = dict(index=index, names={str(k): name.getDebugName(k) for k in (1, 2, 5, 6, 16, 17)},
                        units_per_em=font['head'].unitsPerEm, glyph_count=font['maxp'].numGlyphs,
                        outline_format='glyf' if 'glyf' in font else 'hvgl' if 'hvgl' in font else 'CFF2' if 'CFF2' in font else 'OTHER',
                        tables=tables)
            face['metrics'] = {tag: {field: getattr(font[tag], field, None) for field in fields}
                for tag, fields in {'hhea': ('ascent', 'descent', 'lineGap'),
                    'OS/2': ('usWeightClass', 'usWidthClass', 'fsType', 'sTypoAscender', 'sTypoDescender',
                             'sTypoLineGap', 'usWinAscent', 'usWinDescent', 'sxHeight', 'sCapHeight',
                             'usLowerOpticalPointSize', 'usUpperOpticalPointSize')}.items() if tag in font}
            if 'fvar' in font:
                face['axes'] = [dict(tag=a.axisTag, minimum=a.minValue, default=a.defaultValue,
                                    maximum=a.maxValue, name=name.getDebugName(a.axisNameID)) for a in font['fvar'].axes]
                face['instances'] = [dict(name=name.getDebugName(x.subfamilyNameID), coordinates=x.coordinates)
                                     for x in font['fvar'].instances]
            if 'avar' in font:
                face['avar'] = avar_summary(font)
            if census and 'gvar' in font:
                key = (tables['gvar']['sha256'], tables['glyf']['sha256'], tables['fvar']['sha256'])
                if key not in stats:
                    stats[key] = tuple_census(font)
                face['gvar'] = stats[key]
            result['faces'].append(face)
    result.update(face_count=len(result['faces']), unique_table_bytes=sum(n for _, n in hashes),
                  unshared_table_bytes=sum(t['bytes'] for f in result['faces'] for t in f['tables'].values()),
                  shared_tables=[dict(offset=k[0], bytes=k[1], references=v) for k, v in shared.items() if len(v) > 1],
                  seconds=time.monotonic()-start)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('font', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gvar-census', action='store_true')
    args = parser.parse_args()
    result = inspect(args.font, census=args.gvar_census)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps({k: result[k] for k in ('filename', 'bytes', 'sha256', 'face_count', 'seconds')}))
