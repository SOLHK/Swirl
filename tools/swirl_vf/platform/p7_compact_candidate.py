#!/usr/bin/env python3
"""Compact redundant closure points in a PRIVATE P7 q-face, not production.

Only a closure proven identical in its base and every gvar tuple is removed.
The existing comparator, sampled model and original acceptance gates stay intact.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import json
import sys

from fontTools.ttLib import TTFont, TTCollection

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from p7_original_glyf import EXPECTED, PRIVATE, private_directory, save_new, require
from hvf_glyf_closure import compact_closing_points
from metric_variations import verify_metric_variations
from rebuild import sha256, verify_serialized_face
from ttc_staging_pack import pack_collection


def run(source, parent, output):
    source, parent = Path(source).resolve(strict=True), Path(parent).resolve(strict=True)
    require(sha256(source) == EXPECTED, 'exact_original_source_required')
    require(parent.is_relative_to(PRIVATE), 'private_P7_parent_required')
    receipt_path = parent/'face-report.json'
    receipt = json.loads(receipt_path.read_text())
    path = parent/'P7-Original-face0-EXPERIMENTAL.ttf'
    require(receipt['source_sha256'] == EXPECTED and receipt['production_accepted'] is False
            and receipt['axis_models_partial'] is True and receipt['glyph_count'] == 47102
            and sha256(path) == receipt['candidate_sha256'], 'verified_private_P7_parent_required')
    before, receipt_digest = sha256(path), sha256(receipt_path)
    output = private_directory(output)
    require(not any(output.iterdir()), 'fresh_compaction_output_required')
    with TTFont(source, fontNumber=0, lazy=True) as original, TTFont(path, recalcTimestamp=False) as font:
        order = font.getGlyphOrder()
        require(order == original.getGlyphOrder() and len(order) == 47102
                and font['cmap'].compile(font) == original['cmap'].compile(original),
                'original_cmap_or_GID_order_changed')
        require(tuple(axis.axisTag for axis in font['fvar'].axes) == ('XWDT', 'XWGT', 'XHGT'),
                'explicit_q_parent_required')
        metric_tables = {tag: font.getTableData(tag) for tag in ('hmtx', 'vmtx', 'HVAR', 'VVAR')}
        total = dict(glyphs_checked=0, glyphs_compacted=0, points_removed=0)
        for name in order:
            old = font['glyf'][name]
            glyph, variations, _ = compact_closing_points(old, font['gvar'].variations[name])
            removed = len(old.getCoordinates(None)[0])-len(glyph.getCoordinates(None)[0])
            require(removed >= 0, 'compaction_added_points')
            require(tuple(getattr(old, key, 0) for key in ('xMin', 'yMin', 'xMax', 'yMax'))
                    == tuple(getattr(glyph, key, 0) for key in ('xMin', 'yMin', 'xMax', 'yMax')),
                    'compaction_changed_bounds')
            if removed:
                font['glyf'][name], font['gvar'].variations[name] = glyph, variations
                total['glyphs_compacted'] += 1
                total['points_removed'] += removed
            total['glyphs_checked'] += 1
        require(all(font.getTableData(tag) == data for tag, data in metric_tables.items()),
                'compaction_changed_metric_table_bytes')
        metrics = verify_metric_variations(font)
        target = output/'P7-Original-face0-EXPERIMENTAL.ttf'
        font.save(target)
        digest = sha256(target)
        with TTFont(target) as reopened:
            serialization = verify_serialized_face(font, reopened)
            verify_metric_variations(reopened)
        require(sha256(target) == digest, 'candidate_changed_after_verification')
        def verify(packed):
            with TTCollection(packed) as collection:
                require(len(collection.fonts) == 1, 'compaction_face_count_changed')
                verify_serialized_face(font, collection.fonts[0])
        packing = pack_collection([target], output/'P7-Original-face0-EXPERIMENTAL.ttc',
                                  expected_sha256=[digest], validate=verify)
        require(sha256(source) == EXPECTED and sha256(path) == before
                and sha256(receipt_path) == receipt_digest, 'original_or_parent_changed')
        report = copy.deepcopy(receipt)
        report.update(candidate_sha256=digest, serialization=serialization, packing=packing,
                      status='EXPERIMENTAL_COMPACT_ORIGINAL_Q_PARTIAL_VARIABLE_NOT_ACCEPTED')
        report['closure_compaction'] = dict(total, parent_candidate_sha256=before,
            parent_receipt_sha256=receipt_digest, driver_sha256=sha256(Path(__file__)),
            helper_sha256=sha256(ROOT/'tools/hvf_glyf_closure.py'),
            metric_table_bytes_unchanged=True, metric_encoding=metrics,
            internal_zero_segments_removed=False, strict_failure_records_inherited_without_rejudgment=True,
            native_candidate_validation='NOT_RUN', production_accepted=False)
        save_new(output/'face-report.json', report)
    print(json.dumps({'candidate_sha256': digest, **total, 'production_accepted': False}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.parent, args.output)
