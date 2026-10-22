#!/usr/bin/env python3
"""Diagnose the original CoreText horizontal coordinate of the vertical origin.

The observation helper never emits outlines and is incompatible with the
reconstruction oracle protocol. Its differing axis readbacks are diagnostic
evidence, not accepted production coordinates. Whole-sample hypotheses compare
the original native origin with varied/default advances and source metrics;
bounded worst-case records retain the actual API values and source identity.

References: Apple CTFontGetVerticalTranslationsForGlyphs and CGFont
getGlyphAdvances(glyphs:count:advances:); OpenType vmtx/VORG. vmtx does not store
the x coordinate of a vertical origin. No origin is changed by this diagnostic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from fontTools.ttLib import TTCollection

from compare_axis_construction import EXPECTED, GUARD

LIMIT = 1 / 32
GLYPHS = (0, 1, 2, 3, 5, 20, 82, 263, 4985)

SWIFT = r'''
func originSnapshot(_ font: CTFont, _ gid: Int) throws -> [String: Any] {
    var glyph = CGGlyph(gid)
    var horizontal = CGSize.zero, vertical = CGSize.zero, translation = CGSize.zero
    let hsum = CTFontGetAdvancesForGlyphs(font, .horizontal, &glyph, &horizontal, 1)
    let vsum = CTFontGetAdvancesForGlyphs(font, .vertical, &glyph, &vertical, 1)
    CTFontGetVerticalTranslationsForGlyphs(font, &glyph, &translation, 1)
    let values = [Double(horizontal.width), Double(horizontal.height), Double(vertical.width),
                  Double(vertical.height), Double(translation.width), Double(translation.height), hsum, vsum]
    guard values.allSatisfy(\.isFinite) else { throw OracleError.invalid("nonfinite_origin_diagnostic") }
    let graphics = CTFontCopyGraphicsFont(font, nil)
    var graphicsAdvance: Int32 = 0
    let graphicsSuccess = graphics.getGlyphAdvances(glyphs: &glyph, count: 1, advances: &graphicsAdvance)
    var row: [String: Any] = ["advance_width": Double(horizontal.width), "advance_height": Double(vertical.width),
        "vertical_origin_x": -Double(translation.width), "vertical_origin_y": -Double(translation.height),
        "horizontal_advance_vector": [Double(horizontal.width), Double(horizontal.height)],
        "vertical_advance_vector": [Double(vertical.width), Double(vertical.height)],
        "vertical_origin_translation": [Double(translation.width), Double(translation.height)],
        "horizontal_advance_sum": hsum, "vertical_advance_sum": vsum,
        "font_size": Double(CTFontGetSize(font)), "font_upm": Int(CTFontGetUnitsPerEm(font)),
        "graphics_units_per_em": graphics.unitsPerEm, "graphics_advance_success": graphicsSuccess]
    if graphicsSuccess { row["graphics_advance"] = Int(graphicsAdvance) }
    return row
}

func verticalOriginDiagnosticMain() throws {
    guard CommandLine.arguments.count == 2 else { throw OracleError.invalid("source_argument_required") }
    let url = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL.resolvingSymlinksInPath()
    let data = try Data(contentsOf: url, options: [.mappedIfSafe])
    guard sha256(data) == "SOURCE_HASH" else { throw OracleError.invalid("wrong_original_source") }
    let states = try locateDescriptors(parseFaces(Bytes(data: data)), url: url)
    guard states.count == 32, states.allSatisfy({ $0.baseFont != nil && $0.raw.glyphCount == 47102 }) else {
        throw OracleError.invalid("all_original_physical_faces_required")
    }
    try emit(["type": "origin_diagnostic_metadata", "backend": "CoreText_origin_diagnostic_only",
        "source_sha256": sha256(data), "faces": states.map(\.metadata),
        "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
        "production_readback_guard_unchanged": true, "outlines_emitted": false])
    let glyphs = GLYPH_IDS
    var count = 0, positions = 0
    for state in states {
        let defaults = Dictionary(uniqueKeysWithValues: state.raw.axes.map { ($0.tag, $0.defaultValue) })
        let (defaultFont, _, _) = try observationInstance(state, defaults)
        var baseline: [Int: [String: Any]] = [:]
        for gid in glyphs { baseline[gid] = try originSnapshot(defaultFont, gid) }
        var cases: [(String, [String: Double])] = [("default", defaults)]
        let factors: [Double] = [-1, -0.5, 0.201171875, 0.5, 1, 0.123456789]
        for axis in state.raw.axes {
            for factor in factors {
                var location = defaults
                location[axis.tag] = axis.defaultValue + factor * (factor < 0 ? axis.defaultValue-axis.minimum : axis.maximum-axis.defaultValue)
                cases.append((axis.tag + ":" + String(factor), location))
            }
        }
        for factors in [[-1.0, 1.0, 0.5], [0.5, -0.5, 1.0], [0.201171875, 0.2475, 0.42225]] {
            var location = defaults
            for (axis, factor) in zip(state.raw.axes, factors) {
                location[axis.tag] = axis.defaultValue + factor * (factor < 0 ? axis.defaultValue-axis.minimum : axis.maximum-axis.defaultValue)
            }
            cases.append(("mixed:" + factors.map { String($0) }.joined(separator: ","), location))
        }
        for factor in [-1.0/65536, 1.0/65536] {
            guard let axis = state.raw.axes.first(where: { $0.tag == "wght" }) else { throw OracleError.invalid("wght_missing") }
            var location = defaults
            location[axis.tag] = axis.defaultValue + factor * (factor < 0 ? axis.defaultValue-axis.minimum : axis.maximum-axis.defaultValue)
            cases.append(("wght_near_zero:" + String(factor), location))
        }
        for (label, requested) in cases {
            try autoreleasepool {
                let (font, location, reported) = try observationInstance(state, requested)
                for gid in glyphs {
                    var row = try originSnapshot(font, gid)
                    row["type"] = "origin_diagnostic_glyph"
                    row["face_index"] = state.raw.index; row["glyph_id"] = gid; row["case"] = label
                    row["location"] = location; row["reported_location"] = reported
                    row["default_native_metrics"] = baseline[gid]!
                    try emit(row); count += 1
                }
                positions += 1
            }
        }
    }
    try emit(["type": "origin_diagnostic_summary", "source_sha256": sha256(data),
              "metric_records": count, "positions": positions, "error_count": 0])
}

do { try verticalOriginDiagnosticMain() }
catch {
    try? emit(["type": "origin_diagnostic_error", "error": String(describing: error)])
    exit(2)
}
'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def make_harness(production):
    require(production.count(GUARD) == 1 and production.count('\nfunc run() throws {') == 1,
            'review_changed_production_helper')
    prefix = production.split('\nfunc run() throws {', 1)[0]
    require(prefix.count('func makeInstance(') == 1, 'review_changed_instance_function')
    prefix = prefix.replace('func makeInstance(', 'func observationInstance(', 1)
    prefix = prefix.replace(GUARD, '        _ = effective // Observation only: this is not an accepted axis oracle.')
    return prefix + SWIFT.replace('SOURCE_HASH', EXPECTED).replace('GLYPH_IDS', str(list(GLYPHS)))


def hypotheses(row, stored_width):
    """Predeclared origin models; never choose a different model per sample."""
    baseline = row['default_native_metrics']
    result = {
        'half_current_native_advance': row['advance_width'] / 2,
        'half_stored_hmtx_advance': stored_width / 2,
        'half_default_native_advance': baseline['advance_width'] / 2,
        'unchanged_default_native_origin': baseline['vertical_origin_x'],
        'half_source_upm': row['font_upm'] / 2,
        'stored_half_advance_times_1000_over_upm': stored_width / 2 * 1000 / row['font_upm'],
        'stored_half_advance_times_upm_over_1000': stored_width / 2 * row['font_upm'] / 1000,
    }
    if row['graphics_advance_success']:
        require(row['graphics_units_per_em'] > 0, 'invalid_graphics_units_per_em')
        result['half_current_CGFont_advance'] = row['graphics_advance'] / 2
        result['half_current_CGFont_advance_scaled_to_CT_size'] = (
            row['graphics_advance'] / 2 * row['font_size'] / row['graphics_units_per_em'])
    require(all(math.isfinite(value) for value in result.values()), 'nonfinite_origin_model')
    return result


def new_stats():
    return {'checks': 0, 'over_budget': 0, 'maximum_error': 0., 'maximum_error_example': None}


def record_stat(stat, actual, expected, context):
    require(math.isfinite(actual) and math.isfinite(expected), 'nonfinite_origin_comparison')
    error = abs(actual - expected)
    stat['checks'] += 1
    stat['over_budget'] += error > LIMIT
    if stat['maximum_error_example'] is None or error > stat['maximum_error']:
        stat['maximum_error'] = error
        stat['maximum_error_example'] = {**context, 'expected_for_this_model': expected,
                                         'signed_error': actual - expected}


def analyze(rows, fonts):
    require(rows and rows[0].get('type') == 'origin_diagnostic_metadata'
            and rows[0].get('backend') == 'CoreText_origin_diagnostic_only'
            and rows[0].get('source_sha256') == EXPECTED, 'wrong_origin_diagnostic_metadata')
    metadata = rows[0]
    require(len(metadata.get('faces', [])) == len(fonts), 'source_face_count_mismatch')
    for index, (face, font) in enumerate(zip(metadata['faces'], fonts)):
        require(face.get('face_index') == index and face.get('status') == 'identity_verified'
                and face.get('glyph_count') == len(font.getGlyphOrder())
                and face.get('upm') == font['head'].unitsPerEm, 'physical_source_identity_mismatch')
    reports = {'hypotheses': {}, 'by_face': {}, 'by_gid': {}, 'by_axis_case': {},
               'unchanged_source_vertical_metrics': {}, 'graphics_advance_failures': 0,
               'axis_readback_differences': 0, 'metric_records': 0,
               'os_version': metadata.get('os_version'), 'physical_faces_verified': len(fonts)}
    seen = set()
    for row in rows[1:-1]:
        require(row.get('type') == 'origin_diagnostic_glyph', 'unexpected_or_failed_origin_diagnostic_record')
        face, gid = row['face_index'], row['glyph_id']
        require(type(face) is int and 0 <= face < len(fonts) and gid in GLYPHS, 'unexpected_source_face_or_gid')
        key = (face, gid, row['case'])
        require(key not in seen, 'duplicate_origin_diagnostic_record')
        seen.add(key)
        font = fonts[face]
        name = font.getGlyphOrder()[gid]
        width = font['hmtx'].metrics[name][0]
        height = font['vmtx'].metrics[name][0]
        top = font['VORG'][name]
        require(row['font_upm'] == row['font_size'] == font['head'].unitsPerEm,
                'native_font_size_or_upm_changed')
        context = {field: row[field] for field in ('face_index', 'glyph_id', 'case', 'location', 'reported_location',
            'font_size', 'font_upm', 'advance_width', 'advance_height', 'vertical_origin_x', 'vertical_origin_y',
            'vertical_origin_translation', 'default_native_metrics', 'graphics_units_per_em', 'graphics_advance_success')}
        if row['graphics_advance_success']:
            context['graphics_advance'] = row['graphics_advance']
        context['source_hmtx_advance'] = width
        context['half_current_native_advance'] = row['advance_width'] / 2
        models = hypotheses(row, width)
        for model, expected in models.items():
            for group in (reports['hypotheses'], reports['by_face'].setdefault(str(face), {}),
                          reports['by_gid'].setdefault(str(gid), {}),
                          reports['by_axis_case'].setdefault(row['case'], {})):
                record_stat(group.setdefault(model, new_stats()), row['vertical_origin_x'], expected, context)
        for field, expected in [('advance_height', height), ('vertical_origin_y', top)]:
            record_stat(reports['unchanged_source_vertical_metrics'].setdefault(field, new_stats()),
                        row[field], expected, context)
        reports['graphics_advance_failures'] += not row['graphics_advance_success']
        reports['axis_readback_differences'] += any(
            row['reported_location'].get(axis.axisTag, axis.defaultValue) != row['location'][axis.axisTag]
            for axis in font['fvar'].axes)
        reports['metric_records'] += 1
    summary = rows[-1]
    require(summary.get('type') == 'origin_diagnostic_summary' and summary.get('source_sha256') == EXPECTED
            and summary.get('error_count') == 0 and summary.get('metric_records') == reports['metric_records']
            and summary.get('positions') * len(GLYPHS) == reports['metric_records'], 'incomplete_native_origin_diagnostic')
    require(reports['metric_records'] == len(fonts) * 24 * len(GLYPHS), 'missing_native_origin_cases')
    for face in range(len(fonts)):
        cases = {label for f, _, label in seen if f == face}
        require(len(cases) == 24 and all({gid for f, gid, case in seen if f == face and case == label} == set(GLYPHS)
                                       for label in cases), 'incomplete_native_origin_face_or_glyph_cases')
    reports['positions'] = summary['positions']
    reports['models_with_all_records_within_budget'] = [model for model, stat in reports['hypotheses'].items()
        if stat['checks'] == reports['metric_records'] and not stat['over_budget']]
    return reports


def run(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    require(not output.exists() and output != source, 'new_report_path_required')
    require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, 'exact_original_source_required')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'NOT_RUN', 'source_sha256': EXPECTED, 'source_commit': os.environ.get('GITHUB_SHA'),
              'scope': 'native_vertical_origin_diagnosis_not_conversion_or_axis_acceptance',
              'production_oracle_changed': False, 'outlines_published': False, 'font_generated': False,
              'source_metric_origin_assumption_accepted': False, 'limit_font_units': LIMIT,
              'selected_glyphs': list(GLYPHS)}
    try:
        require(sys.platform == 'darwin', 'CoreText_unavailable_no_native_diagnostic_executed')
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix='swirl-origin-diagnostic-') as temp:
            require(len(collection.fonts) == 32 and all(len(f.getGlyphOrder()) == 47102 for f in collection.fonts),
                    'all_original_physical_faces_and_GIDs_required')
            production = Path(__file__).with_name('coretext_extract.swift')
            swift, binary = Path(temp) / 'origins.swift', Path(temp) / 'origins'
            swift.write_text(make_harness(production.read_text(encoding='utf-8')), encoding='utf-8')
            report['production_source_sha256'] = hashlib.sha256(production.read_bytes()).hexdigest()
            report['diagnostic_harness_sha256'] = hashlib.sha256(swift.read_bytes()).hexdigest()
            compiled = subprocess.run(['xcrun', 'swiftc', '-O', str(swift), '-o', str(binary)],
                                      capture_output=True, text=True, timeout=180)
            require(compiled.returncode == 0, 'origin_diagnostic_compile_failed:' + compiled.stderr[-4000:])
            observed = subprocess.run([str(binary), str(source)], capture_output=True, text=True, timeout=300)
            require(observed.returncode == 0, 'origin_diagnostic_execution_failed:' + observed.stderr[-2000:] + observed.stdout[-2000:])
            report.update(analyze([json.loads(line) for line in observed.stdout.splitlines() if line], collection.fonts))
            report['source_unchanged'] = hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED
            require(report['source_unchanged'], 'original_source_bytes_changed')
            report['status'] = 'NATIVE_VERTICAL_ORIGIN_DIAGNOSIS_COMPLETE_NOT_ACCEPTANCE'
    except Exception as error:
        report['status'] = 'NATIVE_VERTICAL_ORIGIN_DIAGNOSIS_FAILED'
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source, args.output)
    print(json.dumps({'status': result['status'], 'metric_records': result.get('metric_records', 0)}))
