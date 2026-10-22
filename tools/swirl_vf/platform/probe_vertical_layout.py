#!/usr/bin/env python3
"""Observe actual CoreText vertical layout/drawing without accepting font axes.

The exact original source is read only. Every native run must retain its physical
source face, point size and the already observed instance coordinates. Glyph
paths and three raster measurements per character exist only in native memory;
the report contains bounded numerical examples and aggregate displacement data.
Raster residuals are diagnostic measurements, never a replacement for the
unchanged 1/32 FUnit outline/metric acceptance gate.

Primary references consulted before this independent implementation:
https://developer.apple.com/documentation/coretext/kctverticalformsattributename
https://developer.apple.com/documentation/coretext/ctrungetbaseadvancesandorigins(_:_:_:_:)
https://developer.apple.com/documentation/coretext/ctrungettextmatrix(_:)
https://developer.apple.com/documentation/coretext/ctframeprogression/righttoleft
https://developer.apple.com/documentation/coretext/ctframedraw(_:_:)
https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_metrics
https://learn.microsoft.com/en-us/typography/opentype/spec/vmtx

Base advances/origins alone require further processing before drawing, per
Apple. Therefore this diagnostic uses both CTRunDraw and CTFrameDraw. The
independent path-fill centroid removes changes to the glyph's own geometry from
the observed displacement. Every predeclared orientation/origin model is kept;
the tool never selects a different hypothesis for each point to produce a pass.
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

FACES = (0, 5, 10, 15, 20, 24, 28)
CODEPOINTS = (0x4E2D, 0x6F22, 0x0041, 0x0069, 0x0057, 0x0031, 0x0037, 0x0020, 0x3000)
CASES = ('default', 'WDTH_min', 'WDTH_max', 'WDTH_fractional', 'mixed_min', 'mixed_fractional')
BITMAP_PIXELS = 1536
RASTER_SCALE = 0.375
FONT_ACCEPTANCE_LIMIT = 1 / 32

SWIFT = r'''
let layoutPixels = BITMAP_PIXELS
let layoutScale = CGFloat(RASTER_SCALE)
let layoutAnchor = CGPoint(x: 2048, y: 2048)

func layoutVector(_ p: CGPoint) -> [Double] { [Double(p.x), Double(p.y)] }
func layoutSize(_ p: CGSize) -> [Double] { [Double(p.width), Double(p.height)] }
func layoutMatrix(_ m: CGAffineTransform) -> [Double] {
    [Double(m.a), Double(m.b), Double(m.c), Double(m.d), Double(m.tx), Double(m.ty)]
}

func layoutInk(_ draw: (CGContext) throws -> Void) throws -> [String: Any] {
    // Rasterization measures API drawing only. The font and path coordinates
    // remain at the source UPM; no transformed path is saved or reconstructed.
    guard let context = CGContext(data: nil, width: layoutPixels, height: layoutPixels,
        bitsPerComponent: 8, bytesPerRow: layoutPixels, space: CGColorSpaceCreateDeviceGray(),
        bitmapInfo: CGImageAlphaInfo.none.rawValue) else {
        throw OracleError.invalid("layout_bitmap_allocation_failed")
    }
    context.setFillColor(gray: 1, alpha: 1)
    context.fill(CGRect(x: 0, y: 0, width: CGFloat(layoutPixels), height: CGFloat(layoutPixels)))
    context.scaleBy(x: layoutScale, y: layoutScale)
    context.setFillColor(gray: 0, alpha: 1)
    context.setAllowsAntialiasing(true)
    context.setShouldAntialias(true)
    context.setShouldSmoothFonts(false)
    context.textMatrix = .identity
    try draw(context)
    guard let bytes = context.data?.assumingMemoryBound(to: UInt8.self) else {
        throw OracleError.invalid("layout_bitmap_data_unavailable")
    }
    var mass = 0.0, momentX = 0.0, momentY = 0.0
    var borderInk = 0
    for y in 0..<layoutPixels {
        for x in 0..<layoutPixels {
            let value = Double(255 - Int(bytes[y * layoutPixels + x]))
            if value == 0 { continue }
            mass += value; momentX += value * (Double(x) + 0.5)
            momentY += value * (Double(y) + 0.5)
            if x < 2 || y < 2 || x >= layoutPixels-2 || y >= layoutPixels-2 { borderInk += 1 }
        }
    }
    var result: [String: Any] = ["has_ink": mass > 0, "border_ink_pixels": borderInk]
    if mass > 0 {
        result["centroid"] = [momentX/mass/Double(layoutScale), momentY/mass/Double(layoutScale)]
    }
    return result
}

func layoutAxes(_ font: CTFont, _ state: FaceState) -> [String: Double] {
    var values = Dictionary(uniqueKeysWithValues: state.raw.axes.map { ($0.tag, $0.defaultValue) })
    if let raw = CTFontCopyVariation(font) as? [NSNumber: NSNumber] {
        for (key, value) in raw { values[tagString(key.uint32Value)] = value.doubleValue }
    }
    return values
}

func layoutSnapshot(_ font: CTFont, _ state: FaceState, _ codepoints: [Int],
                    _ raster: Bool) throws -> [String: Any] {
    let scalars = codepoints.map { UnicodeScalar($0)! }
    let string = String(String.UnicodeScalarView(scalars))
    let attributes: [String: Any] = [kCTFontAttributeName as String: font,
        kCTVerticalFormsAttributeName as String: true,
        kCTForegroundColorAttributeName as String: CGColor(gray: 0, alpha: 1),
        kCTKernAttributeName as String: 0]
    guard let text = CFAttributedStringCreate(nil, string as CFString, attributes as CFDictionary) else {
        throw OracleError.invalid("layout_attributed_string_failed")
    }
    let setter = CTFramesetterCreateWithAttributedString(text)
    let rectangle = raster ? CGRect(x: 768, y: 768, width: 1536, height: 1536)
                           : CGRect(x: 768, y: 768, width: 12000, height: 20000)
    let path = CGPath(rect: rectangle, transform: nil)
    let frame = CTFramesetterCreateFrame(setter, CFRange(location: 0, length: 0), path,
        [kCTFrameProgressionAttributeName as String: CTFrameProgression.rightToLeft.rawValue] as CFDictionary)
    let visible = CTFrameGetVisibleStringRange(frame)
    guard visible.location == 0, visible.length == string.utf16.count,
          let lines = CTFrameGetLines(frame) as? [CTLine], !lines.isEmpty else {
        throw OracleError.invalid("vertical_frame_did_not_layout_entire_text")
    }
    var origins = [CGPoint](repeating: .zero, count: lines.count)
    CTFrameGetLineOrigins(frame, CFRange(location: 0, length: 0), &origins)
    var glyphRows: [[String: Any]] = []
    var oneRun: CTRun? = nil
    var oneFont: CTFont? = nil
    var oneGlyph = CGGlyph(0)
    var runNumber = 0
    for (lineNumber, line) in lines.enumerated() {
        guard let runs = CTLineGetGlyphRuns(line) as? [CTRun] else {
            throw OracleError.invalid("vertical_frame_runs_unavailable")
        }
        for run in runs {
            let runAttributes = CTRunGetAttributes(run) as NSDictionary
            guard let value = runAttributes[kCTFontAttributeName] else {
                throw OracleError.invalid("vertical_run_font_missing")
            }
            let runFont = value as! CTFont
            _ = try verifyIdentity(runFont, state.raw, allTables: false)
            guard CTFontGetSize(runFont) == CTFontGetSize(font),
                  layoutAxes(runFont, state) == layoutAxes(font, state) else {
                throw OracleError.invalid("vertical_run_changed_observed_source_instance")
            }
            let count = CTRunGetGlyphCount(run)
            var glyphs = [CGGlyph](repeating: 0, count: count)
            var positions = [CGPoint](repeating: .zero, count: count)
            var advances = [CGSize](repeating: .zero, count: count)
            var baseAdvances = [CGSize](repeating: .zero, count: count)
            var baseOrigins = [CGPoint](repeating: .zero, count: count)
            var indices = [CFIndex](repeating: 0, count: count)
            let range = CFRange(location: 0, length: 0)
            CTRunGetGlyphs(run, range, &glyphs)
            CTRunGetPositions(run, range, &positions)
            CTRunGetAdvances(run, range, &advances)
            CTRunGetBaseAdvancesAndOrigins(run, range, &baseAdvances, &baseOrigins)
            CTRunGetStringIndices(run, range, &indices)
            let matrix = CTRunGetTextMatrix(run)
            for i in 0..<count {
                var glyph = glyphs[i]
                var horizontal = CGSize.zero, vertical = CGSize.zero, translation = CGSize.zero
                CTFontGetAdvancesForGlyphs(runFont, .horizontal, &glyph, &horizontal, 1)
                CTFontGetAdvancesForGlyphs(runFont, .vertical, &glyph, &vertical, 1)
                CTFontGetVerticalTranslationsForGlyphs(runFont, &glyph, &translation, 1)
                glyphRows.append(["glyph_id": Int(glyph), "string_index": indices[i],
                    "line": lineNumber, "run": runNumber,
                    "line_origin": layoutVector(origins[lineNumber]),
                    "position": layoutVector(positions[i]), "advance": layoutSize(advances[i]),
                    "base_origin": layoutVector(baseOrigins[i]), "base_advance": layoutSize(baseAdvances[i]),
                    "text_matrix": layoutMatrix(matrix), "font_matrix": layoutMatrix(CTFontGetMatrix(runFont)),
                    "advance_width": Double(horizontal.width), "advance_height": Double(vertical.width),
                    "vertical_origin_x": -Double(translation.width),
                    "vertical_origin_y": -Double(translation.height)])
                oneRun = run; oneFont = runFont; oneGlyph = glyph
            }
            runNumber += 1
        }
    }
    var result: [String: Any] = ["glyphs": glyphRows, "codepoints": codepoints,
        "line_count": lines.count, "run_count": runNumber,
        "physical_face_and_observed_axes_verified": true]
    if raster {
        guard glyphRows.count == 1, let run = oneRun, let runFont = oneFont else {
            throw OracleError.invalid("single_character_vertical_layout_not_one_glyph")
        }
        result["frame_ink"] = try layoutInk { context in CTFrameDraw(frame, context) }
        result["run_ink"] = try layoutInk { context in
            context.textPosition = layoutAnchor
            CTRunDraw(run, context, CFRange(location: 0, length: 0))
        }
        // Raw path data is deliberately never serialized or sent to stdout.
        let glyphPath = CTFontCreatePathForGlyph(runFont, oneGlyph, nil)
        result["path_ink"] = try layoutInk { context in
            if let glyphPath = glyphPath {
                context.translateBy(x: layoutAnchor.x, y: layoutAnchor.y)
                context.addPath(glyphPath); context.fillPath()
            }
        }
    }
    return result
}

func verticalLayoutDiagnosticMain() throws {
    guard CommandLine.arguments.count == 2 else { throw OracleError.invalid("source_argument_required") }
    let url = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL.resolvingSymlinksInPath()
    let data = try Data(contentsOf: url, options: [.mappedIfSafe])
    guard sha256(data) == "SOURCE_HASH" else { throw OracleError.invalid("wrong_original_source") }
    let states = try locateDescriptors(parseFaces(Bytes(data: data)), url: url)
    guard states.count == 32, states.allSatisfy({ $0.baseFont != nil && $0.raw.glyphCount == 47102 }) else {
        throw OracleError.invalid("all_original_physical_faces_required")
    }
    let calibration0 = try layoutInk { $0.fill(CGRect(x: 1200, y: 1300, width: 117, height: 91)) }
    let calibration1 = try layoutInk { $0.fill(CGRect(x: 1337.25, y: 1226.5, width: 117, height: 91)) }
    try emit(["type": "vertical_layout_metadata", "backend": "CoreText_vertical_layout_diagnostic_only",
        "source_sha256": sha256(data), "faces": states.map(\.metadata),
        "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
        "production_readback_guard_unchanged": true, "axis_observations_accepted": false,
        "paths_or_images_emitted": false, "font_acceptance_limit": 1.0/32,
        "raster_font_units_per_pixel": 1/Double(layoutScale),
        "raster_calibration": ["before": calibration0, "after": calibration1,
            "requested_translation": [137.25, -73.5]]])
    let selectedFaces = SELECTED_FACES
    let codepoints = SELECTED_CODEPOINTS
    var count = 0
    for faceIndex in selectedFaces {
        let state = states[faceIndex]
        let defaults = Dictionary(uniqueKeysWithValues: state.raw.axes.map { ($0.tag, $0.defaultValue) })
        let factors: [(String, [String: Double])] = [
            ("default", [:]), ("WDTH_min", ["WDTH": -1]), ("WDTH_max", ["WDTH": 1]),
            ("WDTH_fractional", ["WDTH": 0.201171875]),
            ("mixed_min", ["WDTH": -1, "wght": 1, "HGHT": 0.5]),
            ("mixed_fractional", ["WDTH": 0.201171875, "wght": -0.5, "HGHT": -0.375])]
        for (label, factor) in factors {
            try autoreleasepool {
                var requested = defaults
                for axis in state.raw.axes {
                    let f = factor[axis.tag] ?? 0
                    requested[axis.tag] = axis.defaultValue + f * (f < 0 ? axis.defaultValue-axis.minimum : axis.maximum-axis.defaultValue)
                }
                // Explicit observation only. The unchanged strict wrapper is
                // still present in this harness and in production extraction.
                let (font, location, reported) = try constructInstance(state, requested)
                for cp in codepoints {
                    var character = UniChar(cp), nominal = CGGlyph(0)
                    guard CTFontGetGlyphsForCharacters(font, &character, &nominal, 1), nominal != 0 else {
                        throw OracleError.invalid("selected_character_missing_from_original_face")
                    }
                    var row = try layoutSnapshot(font, state, [cp], true)
                    row["type"] = "vertical_layout_character"; row["face_index"] = faceIndex
                    row["case"] = label; row["location"] = location; row["reported_location"] = reported
                    row["nominal_glyph_id"] = Int(nominal)
                    try emit(row); count += 1
                }
                var row = try layoutSnapshot(font, state, codepoints, false)
                row["type"] = "vertical_layout_mixed"; row["face_index"] = faceIndex
                row["case"] = label; row["location"] = location; row["reported_location"] = reported
                try emit(row); count += 1
            }
        }
    }
    try emit(["type": "vertical_layout_summary", "records": count, "error_count": 0])
}

do { try verticalLayoutDiagnosticMain() }
catch { try? emit(["type": "vertical_layout_error", "error": String(describing: error)]); exit(2) }
'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def make_harness(production):
    require(production.count(GUARD) == 1 and production.count('\nfunc run() throws {') == 1,
            'review_changed_production_helper')
    prefix = production.split('\nfunc run() throws {', 1)[0]
    require(prefix.count('func constructInstance(') == prefix.count('func makeInstance(') == 1,
            'explicit_observation_constructor_required')
    # Keep acceptance code byte-for-byte. Only the diagnostic main calls the
    # observation constructor, with a backend the production oracle rejects.
    return prefix + (SWIFT.replace('SOURCE_HASH', EXPECTED)
                     .replace('SELECTED_FACES', str(list(FACES)))
                     .replace('SELECTED_CODEPOINTS', str(list(CODEPOINTS)))
                     .replace('BITMAP_PIXELS', str(BITMAP_PIXELS))
                     .replace('RASTER_SCALE', str(RASTER_SCALE)))


def sub(a, b):
    require(len(a) == len(b) and all(math.isfinite(x) for x in (*a, *b)), 'invalid_layout_vector')
    return [x-y for x, y in zip(a, b)]


def apply(matrix, vector):
    a, b, c, d = matrix[:4]
    x, y = vector
    return [a*x+c*y, b*x+d*y]


def orientations(matrix):
    a, b, c, d = matrix[:4]
    return {'upright': [1, 0, 0, 1], 'run_matrix': [a, b, c, d],
            'frame_clockwise_run_matrix': [b, -a, d, -c],
            'frame_counterclockwise_run_matrix': [-b, a, -d, c]}


def calibration_sign(calibration):
    before, after = calibration['before'], calibration['after']
    require(before['has_ink'] and after['has_ink'] and not before['border_ink_pixels']
            and not after['border_ink_pixels'], 'raster_instrument_calibration_clipped_or_empty')
    actual = sub(after['centroid'], before['centroid'])
    wanted = calibration['requested_translation']
    require(wanted == [137.25, -73.5], 'unexpected_raster_instrument_calibration')
    sign = [1 if a*w >= 0 else -1 for a, w in zip(actual, wanted)]
    residual = sub([s*a for s, a in zip(sign, actual)], wanted)
    # This is a raster-instrument check at 2.667 FUnit/px, not a font gate.
    require(max(abs(x) for x in residual) <= 1/RASTER_SCALE, 'raster_instrument_translation_failed')
    return sign, residual


def drawing_hypotheses(before, after, sign):
    """Return all drawing models, with no per-character best-model selection.

    Single characters permit interpreting translation when the reported line,
    run and base origins and text matrix are unchanged. Other layout changes
    remain explicit observations, not raster comparisons with guessed frames.
    """
    bg, ag = before['glyphs'][0], after['glyphs'][0]
    if bg['glyph_id'] != ag['glyph_id']:
        return 'SHAPED_GLYPH_CHANGED', {}
    if bg['text_matrix'] != ag['text_matrix'] or bg['font_matrix'] != ag['font_matrix']:
        return 'DRAWING_MATRIX_CHANGED', {}
    if any(bg[field] != ag[field] for field in ('line_origin', 'position', 'base_origin')):
        return 'LAYOUT_ORIGIN_CHANGED', {}
    ink_fields = ('frame_ink', 'run_ink', 'path_ink')
    for row in (before, after):
        if any(row[field]['border_ink_pixels'] for field in ink_fields):
            return 'RASTER_CLIPPED', {}
    statuses = [row[field]['has_ink'] for row in (before, after) for field in ink_fields]
    if not any(statuses):
        return 'EMPTY_GLYPH_LAYOUT_RETAINED', {}
    if not all(statuses):
        return 'PATH_AND_DRAWING_INK_DISAGREE', {}
    deltas = {field: [s*x for s, x in zip(sign, sub(after[field]['centroid'], before[field]['centroid']))]
              for field in ink_fields}
    width_delta = ag['advance_width'] - bg['advance_width']
    result = {}
    for orientation, matrix in orientations(ag['text_matrix']).items():
        for origin, shift in [('unchanged_origin', 0), ('half_current_advance', -width_delta/2)]:
            expected = apply(matrix, [deltas['path_ink'][0] + shift, deltas['path_ink'][1]])
            for drawing in ('frame_ink', 'run_ink'):
                key = '/'.join((drawing, orientation, origin))
                result[key] = {'residual': sub(deltas[drawing], expected),
                               'observed_drawing_delta': deltas[drawing],
                               'raw_path_centroid_delta': deltas['path_ink'],
                               'expected_drawing_delta_for_model': expected,
                               'advance_width_delta': width_delta}
    return 'MEASURED_RELATIVE_DRAWING', result


def add_stat(group, name, vector, context):
    require(vector and all(math.isfinite(v) for v in vector), 'nonfinite_layout_comparison')
    value = math.hypot(*vector)
    stat = group.setdefault(name, {'checks': 0, 'maximum_magnitude': 0., 'sum_magnitude': 0.,
                                   'maximum_example': None})
    stat['checks'] += 1; stat['sum_magnitude'] += value
    if stat['maximum_example'] is None or value > stat['maximum_magnitude']:
        stat['maximum_magnitude'] = value
        stat['maximum_example'] = {**context, 'difference': vector}


def analyze(rows, fonts):
    require(rows and rows[0].get('type') == 'vertical_layout_metadata'
            and rows[0].get('backend') == 'CoreText_vertical_layout_diagnostic_only'
            and rows[0].get('source_sha256') == EXPECTED, 'wrong_vertical_layout_metadata')
    meta = rows[0]
    require(meta.get('production_readback_guard_unchanged') is True
            and meta.get('axis_observations_accepted') is False
            and meta.get('paths_or_images_emitted') is False, 'unsafe_vertical_layout_scope')
    require(len(meta.get('faces', [])) == len(fonts) == 32, 'all_physical_source_faces_required')
    for index, (face, font) in enumerate(zip(meta['faces'], fonts)):
        require(face.get('face_index') == index and face.get('status') == 'identity_verified'
                and face.get('upm') == font['head'].unitsPerEm
                and face.get('glyph_count') == len(font.getGlyphOrder()) == 47102,
                'wrong_physical_source_face')
    sign, residual = calibration_sign(meta['raster_calibration'])
    result = {'physical_faces_verified': len(fonts), 'selected_faces': list(FACES),
              'selected_codepoints': list(CODEPOINTS), 'os_version': meta['os_version'],
              'raster_coordinate_sign': sign, 'raster_calibration_residual': residual,
              'raster_font_units_per_pixel': 1/RASTER_SCALE, 'character_records': 0,
              'mixed_text_records': 0, 'axis_readback_difference_records': 0,
              'raster_comparison_status': {}, 'layout_deltas': {}, 'drawing_hypotheses': {},
              'measured_ink_centroid_deltas': {},
              'by_face': {}, 'by_character': {}, 'by_case': {}, 'substitution_records': 0,
              'noncomparable_examples': []}
    seen, baselines = set(), {}
    for row in rows[1:-1]:
        kind = row.get('type')
        require(kind in ('vertical_layout_character', 'vertical_layout_mixed'), 'failed_vertical_layout_record')
        face, label, cps = row['face_index'], row['case'], tuple(row['codepoints'])
        require(face in FACES and label in CASES and row['physical_face_and_observed_axes_verified'] is True,
                'unexpected_vertical_layout_case')
        require(cps == CODEPOINTS if kind.endswith('mixed') else len(cps) == 1 and cps[0] in CODEPOINTS,
                'unexpected_vertical_layout_text')
        key = (face, label, cps)
        require(key not in seen, 'duplicate_vertical_layout_case')
        seen.add(key)
        font = fonts[face]
        require(set(row['location']) == {axis.axisTag for axis in font['fvar'].axes}, 'incomplete_requested_axes')
        for axis in font['fvar'].axes:
            require(axis.minValue <= row['location'][axis.axisTag] <= axis.maxValue, 'layout_axis_out_of_range')
        result['axis_readback_difference_records'] += any(
            row['reported_location'].get(axis.axisTag, axis.defaultValue) != row['location'][axis.axisTag]
            for axis in font['fvar'].axes)
        require(row['glyphs'], 'empty_layout_glyph_record')
        for glyph in row['glyphs']:
            require(0 < glyph['glyph_id'] < len(font.getGlyphOrder()), 'layout_missing_or_invalid_glyph')
            require(all(math.isfinite(glyph[f]) for f in ('advance_width', 'advance_height',
                    'vertical_origin_x', 'vertical_origin_y')), 'nonfinite_native_layout_metrics')
            for field in ('line_origin', 'position', 'advance', 'base_origin', 'base_advance', 'text_matrix', 'font_matrix'):
                require(all(math.isfinite(x) for x in glyph[field]), 'nonfinite_native_layout_vector')
        if kind.endswith('character'):
            require(len(row['glyphs']) == 1, 'single_character_layout_count_changed')
            nominal = font.getGlyphID(font.getBestCmap()[cps[0]])
            require(row['nominal_glyph_id'] == nominal, 'native_nominal_cmap_changed')
            result['substitution_records'] += row['glyphs'][0]['glyph_id'] != nominal
            result['character_records'] += 1
        else:
            result['mixed_text_records'] += 1
        baseline_key = (face, cps)
        if label == 'default':
            baselines[baseline_key] = row
            continue
        require(baseline_key in baselines, 'default_layout_baseline_missing')
        before = baselines[baseline_key]
        context = {'face_index': face, 'case': label, 'codepoints': list(cps),
                   'location': row['location'], 'reported_location': row['reported_location']}
        if len(before['glyphs']) != len(row['glyphs']):
            if len(result['noncomparable_examples']) < 12:
                result['noncomparable_examples'].append({**context, 'reason': 'GLYPH_COUNT_CHANGED'})
            continue
        for bg, ag in zip(before['glyphs'], row['glyphs']):
            c = {**context, 'glyph_id': ag['glyph_id'], 'default_glyph_id': bg['glyph_id'],
                 'default_advance_width': bg['advance_width'], 'advance_width': ag['advance_width'],
                 'vertical_origin_x': ag['vertical_origin_x'], 'text_matrix': ag['text_matrix']}
            for field in ('line_origin', 'position', 'advance', 'base_origin', 'base_advance',
                          'vertical_origin_x', 'vertical_origin_y', 'advance_width', 'advance_height'):
                delta = sub(ag[field], bg[field]) if isinstance(ag[field], list) else [ag[field]-bg[field]]
                add_stat(result['layout_deltas'], ('mixed/' if kind.endswith('mixed') else 'character/')+field, delta, c)
        if not kind.endswith('character'):
            continue
        # Keep actual drawing observations even when a changed layout origin or
        # matrix makes the restricted origin hypotheses inapplicable.
        observed_deltas = {}
        for field in ('frame_ink', 'run_ink', 'path_ink'):
            bink, aink = before[field], row[field]
            if bink['has_ink'] and aink['has_ink'] and not (bink['border_ink_pixels'] or aink['border_ink_pixels']):
                observed_deltas[field] = [s*x for s, x in zip(sign, sub(aink['centroid'], bink['centroid']))]
        for field, delta in observed_deltas.items():
            add_stat(result['measured_ink_centroid_deltas'], field, delta, {**context,
                'default_layout': before['glyphs'], 'layout': row['glyphs'],
                'measured_deltas': observed_deltas})
        status, models = drawing_hypotheses(before, row, sign)
        result['raster_comparison_status'][status] = result['raster_comparison_status'].get(status, 0) + 1
        if not models and status != 'EMPTY_GLYPH_LAYOUT_RETAINED' and len(result['noncomparable_examples']) < 12:
            result['noncomparable_examples'].append({**context, 'reason': status,
                'default_layout': before['glyphs'], 'layout': row['glyphs']})
        for name, model in models.items():
            c = {**context, 'glyph_id': row['glyphs'][0]['glyph_id'],
                 'text_matrix': row['glyphs'][0]['text_matrix'], **model}
            for group in (result['drawing_hypotheses'], result['by_face'].setdefault(str(face), {}),
                          result['by_character'].setdefault(f'U+{cps[0]:04X}', {}),
                          result['by_case'].setdefault(label, {})):
                add_stat(group, name, model['residual'], c)
    summary = rows[-1]
    expected = {(face, case, cps) for face in FACES for case in CASES
                for cps in [*(tuple([cp]) for cp in CODEPOINTS), CODEPOINTS]}
    require(seen == expected and summary.get('type') == 'vertical_layout_summary'
            and summary.get('records') == len(expected) and summary.get('error_count') == 0,
            'incomplete_vertical_layout_diagnostic')
    result['interpretation'] = ('All model residuals are retained. Raster resolution is diagnostic only; '
        'unchanged positions/matrices are required for relative drawing models. Layout changes, empty '
        'glyphs, substitutions, clipping and ink disagreements remain explicit, without font acceptance.')
    return result


def run(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    require(not output.exists() and output != source, 'new_report_path_required')
    require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, 'exact_original_source_required')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'NOT_RUN', 'source_sha256': EXPECTED, 'source_commit': os.environ.get('GITHUB_SHA'),
              'scope': 'native_vertical_text_layout_drawing_diagnosis_not_font_or_axis_acceptance',
              'original_font_modified': False, 'production_oracle_changed': False,
              'paths_or_images_published': False, 'font_generated': False,
              'native_vertical_origin_x_accepted': False, 'original_strict_gate_limit': FONT_ACCEPTANCE_LIMIT}
    try:
        require(sys.platform == 'darwin', 'CoreText_unavailable_no_native_diagnostic_executed')
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix='swirl-vertical-layout-') as temp:
            production = Path(__file__).with_name('coretext_extract.swift')
            swift, binary = Path(temp) / 'layout.swift', Path(temp) / 'layout'
            swift.write_text(make_harness(production.read_text(encoding='utf-8')), encoding='utf-8')
            report['production_source_sha256'] = hashlib.sha256(production.read_bytes()).hexdigest()
            report['diagnostic_harness_sha256'] = hashlib.sha256(swift.read_bytes()).hexdigest()
            compiled = subprocess.run(['xcrun', 'swiftc', '-O', str(swift), '-o', str(binary)],
                                      capture_output=True, text=True, timeout=180)
            require(compiled.returncode == 0, 'vertical_layout_compile_failed:' + compiled.stderr[-4000:])
            observed = subprocess.run([str(binary), str(source)], capture_output=True, text=True, timeout=900)
            require(observed.returncode == 0, 'vertical_layout_execution_failed:' + observed.stderr[-2000:] + observed.stdout[-2000:])
            report.update(analyze([json.loads(line) for line in observed.stdout.splitlines() if line], collection.fonts))
            report['source_unchanged'] = hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED
            require(report['source_unchanged'], 'original_source_bytes_changed')
            report['status'] = 'NATIVE_VERTICAL_LAYOUT_DIAGNOSIS_COMPLETE_NOT_ACCEPTANCE'
    except Exception as error:
        report['status'] = 'NATIVE_VERTICAL_LAYOUT_DIAGNOSIS_FAILED'
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
    print(json.dumps({key: result.get(key) for key in ('status', 'character_records', 'mixed_text_records')}))
