"""Stream every saved glyph/tuple and compare full cmap/layout with the source.

This is structural and metric verification, not Windows installation or visual
acceptance. Glyph and tuple caches are evicted after inspection.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import time
from contextlib import ExitStack

from fontTools.ttLib import TTCollection
from fontTools.varLib.iup import iup_delta
from metric_variations import _phantom_models, _stored_model
from ttc_staging_binary import validate_ttc_binary
from windows_font_builder import FACE_PLAN, SOURCE_SHA
from windows_font_inventory import sha256
from windows_gvar import TAGS, require


def inspect_standard(font, expected_empty=None, progress_label=None, parent=None):
    order, counts = font.getGlyphOrder(), Counter()
    require(tuple(a.axisTag for a in font['fvar'].axes) == TAGS, 'axis_order_changed')
    require(font['head'].flags & 2 and font['avar'].majorVersion == 1, 'standard_variation_contract')
    for number, name in enumerate(order):
        glyph = font['glyf'][name]
        require(not glyph.isComposite(), 'unexpected_composite')
        points, ends, flags = glyph.getCoordinates(font['glyf'])
        require(len(points) == len(flags), 'coordinate_flag_mismatch')
        if expected_empty is not None:
            require((not len(points)) == expected_empty[number], 'saved_source_empty_mismatch')
        counts['glyphs'] += 1
        counts['empty_glyphs'] += not len(points)
        variations = font['gvar'].variations.get(name, [])
        if parent is not None:
            old = parent['gvar'].variations[name]
            require(len(old) == len(variations), 'reencoded_tuple_count_changed')
            base, control = font['glyf']._getCoordinatesAndControls(name, font['hmtx'].metrics, font['vmtx'].metrics)
            for a, b in zip(old, variations):
                require(a.axes == b.axes, 'reencoded_region_changed')
                original = iup_delta(a.coordinates, list(base), list(control.endPts)) if None in a.coordinates else a.coordinates
                require(original == b.coordinates, 'reencoded_outline_coefficients_changed')
                counts['exact_outline_tuple_maps'] += 1
            del parent['gvar'].variations[name]
        counts['variable_glyphs'] += bool(variations)
        for var in variations:
            require(len(var.coordinates) == len(points)+4, 'gvar_point_count_mismatch')
            counts['tuples'] += 1
            counts[str(len(var.axes))+'_axis_tuples'] += 1
            counts['inferred_points'] += sum(p is None for p in var.coordinates)
        phantom = _phantom_models(font, name, TAGS)
        for kind in ('HVAR', 'VVAR'):
            require(phantom[kind] == _stored_model(font, kind, name, TAGS), 'saved_'+kind+'_coefficient_mismatch')
            counts['exact_metric_models'] += 1
        del font['gvar'].variations[name]
        del font['glyf'].glyphs[name]
        if progress_label and (number+1) % 5000 == 0:
            print(json.dumps(dict(face=progress_label, audited_glyphs=number+1, tuples=counts['tuples'])), flush=True)
    return dict(counts)


def audit(args):
    started = time.monotonic()
    before = sha256(args.candidate)
    build = json.loads((args.candidate.parent/'report.json').read_text())
    require(before == build['sha256'] and sha256(args.source) == SOURCE_SHA, 'input_hash_mismatch')
    require(build['full_glyph_coverage'] and build['source_gids'] == list(range(47102)), 'full_source_GIDs_required')
    require(not args.output.exists(), 'fresh_audit_report_required')
    report = dict(candidate_sha256=before, source_sha256=SOURCE_SHA, faces=[],
                  TTC=validate_ttc_binary(args.candidate), DirectWrite='NOT_RUN', production_accepted=False)
    observed = {}
    with ExitStack() as stack:
        source = stack.enter_context(TTCollection(args.source, lazy=True))
        target = stack.enter_context(TTCollection(args.candidate, lazy=True))
        parent = stack.enter_context(TTCollection(args.parent, lazy=True)) if args.parent else None
        if parent:
            require(sha256(args.parent) == build['parent_candidate_sha256'], 'parent_candidate_identity_mismatch')
            report['parent_candidate_sha256'] = build['parent_candidate_sha256']
        require(len(target.fonts) == 4, 'four_faces_required')
        for index, (source_index, label) in enumerate(FACE_PLAN):
            sf, tf = source.fonts[source_index], target.fonts[index]
            require(tf['maxp'].numGlyphs == sf['maxp'].numGlyphs == 47102, 'glyph_count_changed')
            require(tf.getGlyphOrder() == sf.getGlyphOrder(), 'GID_order_changed')
            require(tf['cmap'].compile(tf) == sf['cmap'].compile(sf), 'cmap_or_UVS_changed')
            if 'GSUB' in sf:
                require(tf['GSUB'].compile(tf) == sf['GSUB'].compile(sf), 'GSUB_changed')
            ratio = tf['head'].unitsPerEm/sf['head'].unitsPerEm
            for field in ('ascent', 'descent', 'lineGap'):
                require(getattr(tf['hhea'], field) == getattr(sf['hhea'], field)*ratio, 'line_metric_changed')
            style = label.split()[1]
            if style not in observed:
                glyph_rows = json.loads((args.candidate.parent/(style+'-glyph-report.json')).read_text())['results']
                require([r['gid'] for r in glyph_rows] == list(range(47102)), 'glyph_report_incomplete')
                prior = parent.fonts[index] if parent else None
                if prior:
                    for tag in ('glyf', 'hmtx', 'vmtx', 'fvar'):
                        require(prior.reader[tag] == tf.reader[tag], 'reencoded_base_data_changed')
                observed[style] = inspect_standard(tf, [r['empty_source_outline'] for r in glyph_rows], label, prior)
            else:
                first = target.fonts[0 if style == 'Text' else 1]
                for tag in ('glyf', 'gvar', 'hmtx', 'vmtx', 'HVAR', 'VVAR', 'fvar'):
                    require(tf.reader[tag] == first.reader[tag], 'regional_shared_data_changed')
            report['faces'].append(dict(face=label, glyphs=47102, unicode_codepoints=len(tf.getBestCmap()),
                exact_cmap_UVS_GSUB=True, exact_scaled_line_metrics=True, standard=observed[style]))
            print(json.dumps(report['faces'][-1]), flush=True)
    require(sha256(args.candidate) == before, 'candidate_changed_during_audit')
    report.update(status='PASS_FULL_STRUCTURAL_AND_STANDARD_METRICS', seconds=time.monotonic()-started)
    args.output.write_text(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--parent', type=Path, help='Verify every expanded outline coefficient against the original IUP candidate')
    audit(p.parse_args())
