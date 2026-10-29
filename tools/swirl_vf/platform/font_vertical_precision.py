#!/usr/bin/env python3
"""Font-only precision control using self-authored glyphs, never Apple input.

This bounded prototype reuses the existing GPOS experiment and fontTools'
standard-table UPEM scaler. It changes the design grid while retaining the
physical outlines/advances. Exact half-width GPOS coefficients become integer
coefficients after an even scale. It does not claim equal raw metric APIs,
universal feature activation, original-font reconstruction or native-platform
acceptance. All errors are converted to the *source* design units.

References consulted before implementation:
https://fonttools.readthedocs.io/en/stable/ttLib/scaleUpem.html
https://learn.microsoft.com/en-us/typography/opentype/spec/head
https://learn.microsoft.com/en-us/typography/opentype/spec/gpos
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import sys

from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem

import experiment_vertical_gpos as fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from metric_variations import add_metric_variations, verify_metric_variations

SOURCE_UPEMS = (1000, 1028, 1064, 1100, 1128, 1144)
LIMIT = Fraction(1, 32)
# Frozen before this prototype's measurements; none occurs in fixture.POINTS.
HOLDOUTS = (
    (1/16, 3/8, -5/16), (-7/16, 11/16, 1/8),
    (307/16384, -991/16384, 5711/16384),
    (21/64, -47/64, 58/64), (-511/1024, 773/1024, -117/1024),
    (1/8192, -1/4096, 3/2048), (-8191/8192, 4095/4096, -2047/2048),
    (173/256, -65/256, 99/256), (-313/512, -127/512, 459/512),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _read(data):
    return TTFont(io.BytesIO(data), recalcTimestamp=False)


def verify_physical_tables(source_data, candidate_data, multiplier):
    """Check serialized geometry and both metric encodings, not API output."""
    source, candidate = _read(source_data), _read(candidate_data)
    require(candidate['head'].unitsPerEm == source['head'].unitsPerEm * multiplier,
            'physical_UPEM_scale_differs')
    require(candidate.getGlyphOrder() == source.getGlyphOrder(), 'physical_GID_order_changed')
    for tag in ('cmap', 'fvar', 'GSUB'):
        require(candidate.getTableData(tag) == source.getTableData(tag), f'physical_{tag}_changed')
    for tag, fields in (
        ('head', ('xMin', 'yMin', 'xMax', 'yMax')),
        ('hhea', ('ascent', 'descent', 'lineGap', 'advanceWidthMax')),
        ('vhea', ('ascent', 'descent', 'lineGap', 'advanceHeightMax')),
        ('OS/2', ('sTypoAscender', 'sTypoDescender', 'sTypoLineGap', 'usWinAscent', 'usWinDescent')),
    ):
        require(all(getattr(candidate[tag], field) == getattr(source[tag], field)*multiplier for field in fields),
                f'physical_global_{tag}_metrics_changed')
    for name in source.getGlyphOrder():
        a, ae, af = source['glyf'][name].getCoordinates(source['glyf'])
        b, be, bf = candidate['glyf'][name].getCoordinates(candidate['glyf'])
        require(ae == be and af == bf and list(b) == [(x*multiplier, y*multiplier) for x, y in a],
                'physical_outline_or_topology_changed')
        for tag in ('hmtx', 'vmtx'):
            require(candidate[tag].metrics[name] == tuple(v*multiplier for v in source[tag].metrics[name]),
                    f'physical_{tag}_changed')
        av, bv = source['gvar'].variations[name], candidate['gvar'].variations[name]
        require(len(av) == len(bv), 'physical_variation_count_changed')
        for a, b in zip(av, bv):
            require(a.axes == b.axes and b.coordinates == [
                None if p is None else (p[0]*multiplier, p[1]*multiplier) for p in a.coordinates],
                'physical_gvar_coefficients_changed')
    require(verify_metric_variations(source)['status'] == 'PASS_EXACT_STANDARD_METRIC_COEFFICIENTS'
            and verify_metric_variations(candidate)['status'] == 'PASS_EXACT_STANDARD_METRIC_COEFFICIENTS',
            'physical_HVAR_or_VVAR_coefficient_verification_failed')
    return {'status': 'PASS_SERIALIZED_PHYSICAL_GEOMETRY_AND_METRICS',
            'glyphs': len(source.getGlyphOrder()), 'multiplier': multiplier,
            'unchanged_tables': ['cmap', 'fvar', 'GSUB'],
            'scaled_and_verified': ['glyf', 'gvar', 'hmtx', 'vmtx', 'HVAR', 'VVAR',
                                    'head_bbox', 'hhea_metrics', 'vhea_metrics', 'OS/2_line_metrics'],
            'raw_native_API_equality_asserted': False}


def build_control(kind='even', source_upem=1000, multiplier=8):
    """Return two serialized authored controls; no external font is accepted."""
    require(type(source_upem) is int and source_upem in SOURCE_UPEMS, 'unsupported_control_source_UPEM')
    require(type(multiplier) is int and multiplier > 0 and multiplier % 2 == 0,
            'exact_half_coefficients_need_positive_even_integer_scale')
    require(16 <= source_upem * multiplier <= 16384, 'target_UPEM_outside_OpenType_range')
    data, symbols = fixture.original_fixture(kind)
    source = _read(data)
    source['head'].unitsPerEm = source_upem
    # Reuse the production metric writer to include and independently verify
    # both HVAR and VVAR. The original experiment already has HVAR only.
    del source['HVAR']
    add_metric_variations(source)
    source_data = fixture.serialize(source)
    scaled = _read(source_data)
    scale_upem(scaled, source_upem * multiplier)
    scaled_data = fixture.serialize(scaled)  # Serialize before any publication.
    scaled_symbols = tuple(replace(s, width=s.width*multiplier,
        coefficients=tuple(v*multiplier for v in s.coefficients)) for s in symbols)
    candidate_data, failures = fixture.add_adjustment(scaled_data, scaled_symbols, 'vert')
    require(not failures, 'scaled_exact_encoder_failed')
    candidate = _read(candidate_data)
    sub = candidate['GPOS'].table.LookupList.Lookup[0].SubTable[0]
    values = [sub.Value]*len(sub.Coverage.glyphs) if sub.Format == 1 else sub.Value
    specs = {s.name: s for s in symbols}
    for name, value in zip(sub.Coverage.glyphs, values):
        s = specs[name]
        # Preserve the ORIGINAL fixed origin floor(width/2), rather than
        # silently changing an odd-width source's origin when scaling it.
        correction = (Fraction(s.width, 2) - s.width//2) * multiplier
        require(correction.denominator == 1, 'source_fixed_origin_not_exactly_encodable')
        value.XPlacement += int(correction)
    candidate_data = fixture.serialize(candidate)
    evidence = verify_physical_tables(source_data, candidate_data, multiplier)
    return source_data, candidate_data, symbols, evidence


def _shape(data, point, direction, language, source_upem):
    import uharfbuzz as hb
    font = hb.Font(hb.Face(data)); hb.ot_font_set_funcs(font)
    # A fixed output scale in SOURCE units. Increasing it with target UPEM
    # would conceal rather than reduce physical placement errors.
    font.scale = (source_upem*64, source_upem*64)
    font.set_variations(fixture.requested_location(point))
    buffer = hb.Buffer(); buffer.add_str('中 AB')
    buffer.direction = direction; buffer.script = 'hani'; buffer.language = language
    hb.shape(font, buffer, {}, shapers=['ot'])
    return [(i.codepoint, i.cluster, p.x_advance/64, p.y_advance/64,
             p.x_offset/64, p.y_offset/64, font.get_glyph_h_advance(i.codepoint)/64,
             tuple(v/64 for v in font.get_glyph_v_origin(i.codepoint)))
            for i, p in zip(buffer.glyph_infos, buffer.glyph_positions)]


def measure_control(kind='even', source_upem=1000, multiplier=8):
    import uharfbuzz as hb
    source, candidate, symbols, physical = build_control(kind, source_upem, multiplier)
    baseline, rounded = fixture.add_adjustment(source, symbols, 'vert', diagnostic_rounding=True)
    maxima = {'unscaled_layout': 0., 'scaled_layout': 0., 'retained_raw_advance_change': 0.}
    counts = {'layout_glyphs': 0, 'scaled_above_1_over_32': 0, 'unscaled_above_1_over_32': 0,
              'horizontal_identity_checks': 0, 'raw_metric_changes': 0}
    for point in HOLDOUTS:
        for language in ('zh-cn', 'zh-hk'):
            a = _shape(baseline, point, 'ttb', language, source_upem)
            b = _shape(candidate, point, 'ttb', language, source_upem)
            require([(r[0], r[1]) for r in a] == [(r[0], r[1]) for r in b], 'layout_GSUB_or_clusters_changed')
            for old, new in zip(a, b):
                wanted = symbols[new[0]].width//2
                before, after = abs(old[4]+wanted), abs(new[4]+wanted)
                maxima['unscaled_layout'] = max(maxima['unscaled_layout'], before)
                maxima['scaled_layout'] = max(maxima['scaled_layout'], after)
                maxima['retained_raw_advance_change'] = max(maxima['retained_raw_advance_change'], abs(new[6]-old[6]))
                counts['raw_metric_changes'] += (new[6], new[7]) != (old[6], old[7])
                counts['layout_glyphs'] += 1
                counts['scaled_above_1_over_32'] += after > LIMIT
                counts['unscaled_above_1_over_32'] += before > LIMIT
            # GPOS must not affect the default horizontal shaping of this SAME
            # scaled font. Raw metrics need not equal the unscaled API output.
            without_gpos = _read(candidate); del without_gpos['GPOS']; del without_gpos['GDEF']
            require(_shape(fixture.serialize(without_gpos), point, 'ltr', language, source_upem)
                    == _shape(candidate, point, 'ltr', language, source_upem), 'default_horizontal_layout_changed')
            counts['horizontal_identity_checks'] += 1
    return {'status': 'BOUNDED_AUTHORED_HARFBUZZ_CONTROL_MEASURED',
            'kind': kind, 'source_upem': source_upem, 'target_upem': source_upem*multiplier,
            'multiplier': multiplier, 'harfbuzz_version': hb.version_string(),
            'limit_source_font_units': float(LIMIT), 'maximum_error_source_font_units': maxima,
            'counts': counts, 'holdouts': [list(p) for p in HOLDOUTS],
            'serialized_physical_preservation': physical,
            'unscaled_fractional_encoder_rejections_retained': rounded,
            'source_sha256': hashlib.sha256(source).hexdigest(),
            'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
            'raw_API_equality': 'NOT_ASSERTED_RETAINED_DIFFERENCES',
            'original_conversion': 'NOT_RUN', 'CoreText': 'NOT_RUN', 'DirectWrite': 'NOT_RUN',
            'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN', 'universal_layout_acceptance': False}


def write_control(output, kind='even', source_upem=1000, multiplier=8):
    # Build, serialize, reopen and measure before publishing anything. Inputs
    # cannot designate an original font, and existing output is never replaced.
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'fresh_control_output_required')
    source, candidate, _, _ = build_control(kind, source_upem, multiplier)
    result = measure_control(kind, source_upem, multiplier)
    output.mkdir(parents=True, mode=0o700)
    for name, data in [('authored-source.ttf', source), ('authored-scaled-gpos.ttf', candidate)]:
        with (output/name).open('xb') as stream:
            stream.write(data)
    with (output/'summary.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--kind', choices=('even', 'odd_width', 'odd_delta'), default='even')
    parser.add_argument('--source-upem', type=int, choices=SOURCE_UPEMS, default=1000)
    parser.add_argument('--multiplier', type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(write_control(args.output, args.kind, args.source_upem, args.multiplier), allow_nan=False))
