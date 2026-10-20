#!/usr/bin/env python3
"""Measure CoreText GPOS feature routing and actual drawing on original symbols.

This tool accepts no Apple font input. It builds the independent fixture from
experiment_vertical_gpos, runs each source/candidate in its own native process,
and verifies source table hashes in every actual CTRun. Font bytes, glyph paths
and bitmaps stay in temporary storage/native memory; only synthetic numerical
observations and their bounded comparisons are reported. No production oracle,
axis acceptance rule, source metric or conversion behavior is changed.

CoreText may already use a fixed vertical X origin on a TrueType font. Therefore
the tool measures both candidate-minus-source at the same axes and candidate-
minus-source-default. The second comparison exposes double compensation. Raw
metric APIs, CTRun positions/base origins and CTFrameDraw/CTRunDraw are retained
separately. Raster measurements are diagnostic, never an exact font gate.

Primary references consulted before this independent implementation:
https://developer.apple.com/documentation/coretext/kctfontopentypefeaturetag
https://developer.apple.com/documentation/coretext/kctfontopentypefeaturevalue
https://developer.apple.com/documentation/coretext/kctfontfeaturesettingsattribute
https://developer.apple.com/documentation/coretext/ctfontcreatecopywithattributes(_:_:_:_:)
https://developer.apple.com/documentation/coretext/ctrungetbaseadvancesandorigins(_:_:_:_:)
https://developer.apple.com/documentation/coretext/ctrungettextmatrix(_:)
https://developer.apple.com/documentation/coretext/ctframedraw(_:_:)
https://github.com/harfbuzz/harfbuzz/blob/12.3.2/src/hb-coretext-shape.cc
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from fontTools.ttLib import TTFont

import experiment_vertical_gpos as fixture
from probe_vertical_layout import SWIFT as SHARED_LAYOUT_SWIFT, apply, orientations

POINTS = ((0., 0., 0.), (-1., 0., 0.), (1., 0., 0.), (.201171875, 0., 0.),
          (-1., 1., -1.), (1., 1., -1.), (.201171875, .2475, .42225))
TEXTS = {'single_han': [0x4E2D], 'single_latin': [0x42],
         'single_space': [0x20], 'mixed': [0x4E2D, 0x20, 0x41, 0x42]}
POLICIES = ('default', 'enabled', 'disabled')
DIRECTIONS = ('ltr', 'ttb')
LANGUAGES = ('zh-CN', 'zh-HK')
RASTER_SCALE = .375
BITMAP_PIXELS = 1536


HEADER = r'''
import Foundation
import CoreText
import CoreGraphics
import CryptoKit

enum OracleError: Error {
    case invalid(String)
    case diagnostic(String, [String: Any])
}
func emit(_ object: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
}
func sha256(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
func tagValue(_ tag: String) -> UInt32 { tag.utf8.reduce(UInt32(0)) { ($0 << 8) | UInt32($1) } }
func tagName(_ value: UInt32) -> String {
    String(bytes: [UInt8((value >> 24) & 255), UInt8((value >> 16) & 255),
        UInt8((value >> 8) & 255), UInt8(value & 255)], encoding: .ascii)!
}
let fixtureConstruction = "SHA256-verified original fixture bytes -> CGDataProvider -> CGFont -> CTFontCreateWithGraphicsFont; identity matrix; explicit variation and feature descriptor; unregistered font in an isolated process"
func nativeErrorRecord(_ error: Error, _ type: String) -> [String: Any] {
    var record: [String: Any] = ["type": type, "error": String(describing: error)]
    if let failure = error as? OracleError {
        switch failure {
        case .invalid: break
        case let .diagnostic(reason, context):
            record["error"] = reason; record["diagnostic"] = context
        }
    }
    return record
}
func fixtureIdentity(_ font: CTFont, _ expected: [String: String], _ absent: [String]) -> [String: Any] {
    var tables: [String: Any] = [:]
    for tag in Set(Array(expected.keys) + absent).sorted() {
        var observation: [String: Any] = ["available": false]
        if let data = CTFontCopyTable(font, tagValue(tag), CTFontTableOptions(rawValue: 0)) {
            let actualHash = sha256(data as Data)
            observation = ["available": true, "sha256": actualHash]
            if let expectedHash = expected[tag] {
                observation["matches_requested_fixture"] = actualHash == expectedHash
            }
        }
        if let expectedHash = expected[tag] { observation["expected_sha256"] = expectedHash }
        observation["expected_absent"] = absent.contains(tag)
        tables[tag] = observation
    }
    let matrix = CTFontGetMatrix(font)
    return ["postscript_name": CTFontCopyPostScriptName(font) as String,
        "family_name": CTFontCopyFamilyName(font) as String,
        "glyph_count": CTFontGetGlyphCount(font), "units_per_em": CTFontGetUnitsPerEm(font),
        "size": Double(CTFontGetSize(font)),
        "font_matrix": [Double(matrix.a), Double(matrix.b), Double(matrix.c), Double(matrix.d),
                        Double(matrix.tx), Double(matrix.ty)],
        "observed_axes": observedAxes(font), "tables": tables]
}
func verifyFixture(_ font: CTFont, _ expected: [String: String], _ absent: [String]) throws {
    guard CTFontGetGlyphCount(font) == 8, CTFontGetUnitsPerEm(font) == 1000,
          CTFontGetSize(font) == 1000 else { throw OracleError.invalid("wrong_original_fixture_identity") }
    for (tag, hash) in expected {
        // The current macOS SDK marks excludeSynthetic unavailable. Default
        // options are supported; exact data hashes still reject a different
        // font or any synthesized table that differs from the fixture bytes.
        guard let table = CTFontCopyTable(font, tagValue(tag), CTFontTableOptions(rawValue: 0)),
              sha256(table as Data) == hash else {
            throw OracleError.invalid("actual_run_changed_fixture_table:\(tag)")
        }
    }
    for tag in absent {
        guard CTFontCopyTable(font, tagValue(tag), CTFontTableOptions(rawValue: 0)) == nil else {
            throw OracleError.invalid("actual_run_added_unrequested_table:\(tag)")
        }
    }
}
func observedAxes(_ font: CTFont) -> [String: Double] {
    var result: [String: Double] = ["WDTH": 500, "wght": 400, "HGHT": 500]
    if let values = CTFontCopyVariation(font) as? [NSNumber: NSNumber] {
        for (key, value) in values { result[tagName(key.uint32Value)] = value.doubleValue }
    }
    return result
}
'''


NATIVE = r'''
func makeFixtureFont(_ graphics: CGFont, _ request: [String: Any],
                     _ expected: [String: String], _ absent: [String]) throws -> CTFont {
    guard let coordinates = request["requested"] as? [String: Double],
          let features = request["features"] as? [String: Int] else {
        throw OracleError.invalid("invalid_original_fixture_request")
    }
    var axisValues: [NSNumber: NSNumber] = [:]
    for (tag, value) in coordinates { axisValues[NSNumber(value: tagValue(tag))] = NSNumber(value: value) }
    var settings: [[String: Any]] = []
    for tag in features.keys.sorted() {
        settings.append([kCTFontOpenTypeFeatureTag as String: tag,
                         kCTFontOpenTypeFeatureValue as String: features[tag]!])
    }
    let attributes: [String: Any] = [kCTFontVariationAttribute as String: axisValues,
                                    kCTFontFeatureSettingsAttribute as String: settings]
    let descriptor = CTFontDescriptorCreateWithAttributes(attributes as CFDictionary)
    var matrix = CGAffineTransform.identity
    let font = CTFontCreateWithGraphicsFont(graphics, 1000, &matrix, descriptor)
    do { try verifyFixture(font, expected, absent) }
    catch {
        throw OracleError.diagnostic("constructed_fixture_identity_failed", [
            "cause": String(describing: error), "construction": fixtureConstruction,
            "requested_font": fixtureIdentity(font, expected, absent)])
    }
    return font
}

func fixtureSnapshot(_ font: CTFont, _ request: [String: Any],
                     _ expected: [String: String], _ absent: [String]) throws -> [String: Any] {
    let codepoints = request["codepoints"] as! [Int]
    let direction = request["direction"] as! String
    let language = request["language"] as! String
    let textName = request["text"] as! String
    let raster = textName == "single_han" || textName == "single_latin"
    let text = String(String.UnicodeScalarView(codepoints.map { UnicodeScalar($0)! }))
    // Do not set kCTKern: a zero value could itself override the vkrn policy.
    let attributes: [String: Any] = [kCTFontAttributeName as String: font,
        kCTVerticalFormsAttributeName as String: direction == "ttb",
        kCTLanguageAttributeName as String: language,
        kCTForegroundColorAttributeName as String: CGColor(gray: 0, alpha: 1)]
    guard let attributed = CFAttributedStringCreate(nil, text as CFString, attributes as CFDictionary) else {
        throw OracleError.invalid("original_fixture_attributed_text_failed")
    }
    let setter = CTFramesetterCreateWithAttributedString(attributed)
    let rectangle = codepoints.count == 1 ? CGRect(x: 768, y: 768, width: 1536, height: 1536)
                                         : CGRect(x: 768, y: 768, width: 12000, height: 20000)
    let path = CGPath(rect: rectangle, transform: nil)
    var frameAttributes: [String: Any] = [:]
    if direction == "ttb" {
        frameAttributes[kCTFrameProgressionAttributeName as String] = CTFrameProgression.rightToLeft.rawValue
    }
    let frame = CTFramesetterCreateFrame(setter, CFRange(location: 0, length: 0), path,
                                        frameAttributes as CFDictionary)
    let visible = CTFrameGetVisibleStringRange(frame)
    let frameLines = CTFrameGetLines(frame)
    guard visible.location == 0, visible.length == text.utf16.count,
          let lines = frameLines as? [CTLine], !lines.isEmpty else {
        let reportedFrameAttributes = CTFrameGetFrameAttributes(frame) as NSDictionary
        throw OracleError.diagnostic("original_fixture_layout_incomplete", [
            "visible_range": [visible.location, visible.length],
            "requested_range": [0, 0], "utf16_count": text.utf16.count,
            "line_count": CFArrayGetCount(frameLines),
            "frame_rect": [Double(rectangle.minX), Double(rectangle.minY),
                           Double(rectangle.width), Double(rectangle.height)],
            "requested_frame_progression": frameAttributes[kCTFrameProgressionAttributeName as String] ?? NSNull(),
            "reported_frame_progression": reportedFrameAttributes[kCTFrameProgressionAttributeName] ?? NSNull(),
            "vertical_forms": direction == "ttb", "construction": fixtureConstruction,
            "requested_font": fixtureIdentity(font, expected, absent)])
    }
    var lineOrigins = [CGPoint](repeating: .zero, count: lines.count)
    CTFrameGetLineOrigins(frame, CFRange(location: 0, length: 0), &lineOrigins)
    var rows: [[String: Any]] = []
    var oneRun: CTRun? = nil
    var oneFont: CTFont? = nil
    var oneGlyph = CGGlyph(0)
    var runNumber = 0
    for (lineIndex, line) in lines.enumerated() {
        guard let runs = CTLineGetGlyphRuns(line) as? [CTRun] else {
            throw OracleError.invalid("original_fixture_runs_unavailable")
        }
        for run in runs {
            let runAttributes = CTRunGetAttributes(run) as NSDictionary
            guard let value = runAttributes[kCTFontAttributeName] else {
                throw OracleError.invalid("original_fixture_run_font_missing")
            }
            let runFont = value as! CTFont
            do { try verifyFixture(runFont, expected, absent) }
            catch {
                throw OracleError.diagnostic("actual_run_fixture_identity_failed", [
                    "cause": String(describing: error), "construction": fixtureConstruction,
                    "line": lineIndex, "run": runNumber,
                    "requested_font": fixtureIdentity(font, expected, absent),
                    "actual_run_font": fixtureIdentity(runFont, expected, absent)])
            }
            guard observedAxes(runFont) == observedAxes(font) else {
                throw OracleError.invalid("original_fixture_run_changed_observed_axes")
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
            for index in 0..<count {
                var glyph = glyphs[index]
                var horizontal = CGSize.zero, vertical = CGSize.zero, translation = CGSize.zero
                CTFontGetAdvancesForGlyphs(runFont, .horizontal, &glyph, &horizontal, 1)
                CTFontGetAdvancesForGlyphs(runFont, .vertical, &glyph, &vertical, 1)
                CTFontGetVerticalTranslationsForGlyphs(runFont, &glyph, &translation, 1)
                var row: [String: Any] = ["gid": Int(glyph), "cluster": indices[index],
                    "line": lineIndex, "run": runNumber, "line_origin": layoutVector(lineOrigins[lineIndex]),
                    "position": layoutVector(positions[index]), "advance": layoutSize(advances[index]),
                    "base_origin": layoutVector(baseOrigins[index]), "base_advance": layoutSize(baseAdvances[index]),
                    "text_matrix": layoutMatrix(matrix), "font_matrix": layoutMatrix(CTFontGetMatrix(runFont)),
                    "metric_width": Double(horizontal.width), "metric_height": Double(vertical.width),
                    "metric_vertical_origin": [-Double(translation.width), -Double(translation.height)],
                    "actual_source_table_identity_verified": true]
                if let rawPath = CTFontCreatePathForGlyph(runFont, glyph, nil) {
                    let box = rawPath.boundingBoxOfPath
                    row["has_outline"] = !rawPath.isEmpty
                    row["path_bounds"] = [Double(box.minX), Double(box.minY), Double(box.width), Double(box.height)]
                } else { row["has_outline"] = false }
                rows.append(row); oneRun = run; oneFont = runFont; oneGlyph = glyph
            }
            runNumber += 1
        }
    }
    var result: [String: Any] = ["type": "observation", "request": request,
        "reported_axes": observedAxes(font), "glyphs": rows,
        "line_count": lines.count, "run_count": runNumber, "raster_executed": raster]
    if let settings = CTFontCopyFeatureSettings(font) as? [[String: Any]] {
        result["reported_feature_settings"] = settings
    } else { result["reported_feature_settings"] = [] as [[String: Any]] }
    if raster {
        guard rows.count == 1, let run = oneRun, let runFont = oneFont else {
            throw OracleError.invalid("original_fixture_single_text_not_one_glyph")
        }
        result["frame_ink"] = try layoutInk { CTFrameDraw(frame, $0) }
        result["run_ink"] = try layoutInk { context in
            context.textPosition = layoutAnchor
            CTRunDraw(run, context, CFRange(location: 0, length: 0))
        }
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

func originalGPOSMain() throws {
    guard CommandLine.arguments.count == 2 else { throw OracleError.invalid("fixture_manifest_required") }
    let configData = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    guard let config = try JSONSerialization.jsonObject(with: configData) as? [String: Any],
          config["scope"] as? String == "independent_original_GPOS_fixture_only",
          let source = config["font_path"] as? String,
          let wantedHash = config["font_sha256"] as? String,
          let expected = config["table_hashes"] as? [String: String],
          let absent = config["absent_tables"] as? [String],
          let requests = config["requests"] as? [[String: Any]] else {
        throw OracleError.invalid("invalid_original_fixture_manifest")
    }
    let bytes = try Data(contentsOf: URL(fileURLWithPath: source))
    guard sha256(bytes) == wantedHash,
          let provider = CGDataProvider(data: bytes as CFData), let graphics = CGFont(provider) else {
        throw OracleError.invalid("original_fixture_bytes_or_CGFont_failed")
    }
    let calibration0 = try layoutInk { $0.fill(CGRect(x: 1200, y: 1300, width: 117, height: 91)) }
    let calibration1 = try layoutInk { $0.fill(CGRect(x: 1337.25, y: 1226.5, width: 117, height: 91)) }
    try emit(["type": "metadata", "scope": "independent_original_GPOS_fixture_only",
        "font_sha256": wantedHash, "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
        "actual_font_table_identity_checked": true, "Apple_font_input": false,
        "paths_or_bitmaps_emitted": false, "raster_font_units_per_pixel": 1/Double(layoutScale),
        "raster_calibration": ["before": calibration0, "after": calibration1,
                               "requested_translation": [137.25, -73.5]]])
    var success = 0, errors = 0
    for request in requests {
        do {
            try autoreleasepool {
                let font = try makeFixtureFont(graphics, request, expected, absent)
                try emit(fixtureSnapshot(font, request, expected, absent))
                success += 1
            }
        } catch {
            var record = nativeErrorRecord(error, "request_error")
            record["request"] = request
            try emit(record)
            errors += 1
        }
    }
    try emit(["type": "summary", "requests": requests.count, "observations": success, "errors": errors])
    if errors != 0 { exit(3) }
}
do { try originalGPOSMain() }
catch { try? emit(nativeErrorRecord(error, "fatal")); exit(2) }
'''


def make_harness():
    shared = SHARED_LAYOUT_SWIFT.split('func layoutAxes(', 1)[0]
    fixture.require('func layoutInk(' in shared and 'constructInstance(' not in shared,
                    'review_changed_shared_raster_instrument')
    return HEADER + shared.replace('BITMAP_PIXELS', str(BITMAP_PIXELS)).replace(
        'RASTER_SCALE', str(RASTER_SCALE)) + NATIVE


def requests(route, points=POINTS):
    return [{'route': route, 'point': i, 'normalized': list(normalized),
             'requested': fixture.requested_location(normalized), 'policy': policy,
             'features': fixture.feature_settings(route, policy), 'direction': direction,
             'language': language, 'text': label, 'codepoints': codepoints}
            for i, normalized in enumerate(points) for policy in POLICIES
            for direction in DIRECTIONS for language in LANGUAGES for label, codepoints in TEXTS.items()]


def key(request):
    return tuple(request[k] for k in ('route', 'point', 'policy', 'direction', 'language', 'text'))


def stat(group, field, vector, context):
    fixture.require(vector and all(math.isfinite(v) for v in vector), 'nonfinite_CoreText_GPOS_observation')
    magnitude = math.hypot(*vector)
    value = group.setdefault(field, {'checks': 0, 'max_abs_error': 0., 'above_1_over_32': 0,
        'above_reconstruction_1_FUnit': 0, 'worst': None})
    value['checks'] += 1
    value['above_1_over_32'] += magnitude > fixture.LIMIT
    value['above_reconstruction_1_FUnit'] += magnitude > fixture.RECONSTRUCTION_LIMIT
    if value['worst'] is None or magnitude > value['max_abs_error']:
        value['max_abs_error'] = magnitude
        value['worst'] = {**context, 'difference': vector}


def subtract(a, b):
    fixture.require(len(a) == len(b), 'CoreText_GPOS_vector_size_mismatch')
    return [x-y for x, y in zip(a, b)]


def raster_sign(metadata):
    calibration = metadata['raster_calibration']
    b, a = calibration['before'], calibration['after']
    fixture.require(b['has_ink'] and a['has_ink'] and not b['border_ink_pixels']
                    and not a['border_ink_pixels'], 'CoreText_GPOS_raster_calibration_failed')
    delta = subtract(a['centroid'], b['centroid'])
    wanted = calibration['requested_translation']
    fixture.require(wanted == [137.25, -73.5], 'CoreText_GPOS_wrong_raster_calibration')
    sign = [1 if x*y >= 0 else -1 for x, y in zip(delta, wanted)]
    residual = subtract([s*x for s, x in zip(sign, delta)], wanted)
    fixture.require(max(map(abs, residual)) <= 1/RASTER_SCALE, 'CoreText_GPOS_raster_instrument_mismatch')
    return sign, residual


def drawing_comparisons(source_default, source, candidate, encoded, sign):
    """Return predeclared models; never select a different model per glyph."""
    all_rows = (source_default, source, candidate)
    if not all(row.get('raster_executed') for row in all_rows):
        return {'status': 'LAYOUT_RETAINED_WITHOUT_RASTER'}
    glyphs = [row['glyphs'][0] for row in all_rows]
    if len({g['gid'] for g in glyphs}) != 1:
        return {'status': 'GSUB_GLYPH_CHANGED'}
    if any(g['text_matrix'] != glyphs[0]['text_matrix'] or g['font_matrix'] != glyphs[0]['font_matrix']
           for g in glyphs[1:]):
        return {'status': 'DRAWING_MATRIX_CHANGED'}
    for row in all_rows:
        if any(row[f]['border_ink_pixels'] for f in ('frame_ink', 'run_ink', 'path_ink')):
            return {'status': 'RASTER_CLIPPED'}
        if not all(row[f]['has_ink'] for f in ('frame_ink', 'run_ink', 'path_ink')):
            return {'status': 'INK_MISSING'}
    result = {'status': 'ACTUAL_DRAWING_MODELS_MEASURED', 'fields': {}}
    for field in ('frame_ink', 'run_ink', 'path_ink'):
        def delta(a, b):
            return [s*x for s, x in zip(sign, subtract(a[field]['centroid'], b[field]['centroid']))]
        effect = delta(candidate, source)
        result['fields'][field + '/candidate_minus_source'] = effect
        result['fields'][field + '/source_minus_source_default'] = delta(source, source_default)
        result['fields'][field + '/candidate_minus_source_default'] = delta(candidate, source_default)
        if field == 'path_ink':
            continue
        for orientation, matrix in orientations(glyphs[-1]['text_matrix']).items():
            expected = apply(matrix, [encoded, 0])
            result['fields'][field + '/' + orientation + '/GPOS_effect_minus_encoded'] = subtract(effect, expected)
            result['fields'][field + '/' + orientation + '/GPOS_effect_minus_twice_encoded'] = subtract(
                effect, [2*x for x in expected])
    return result


def analyze(observations, candidates, symbols, signs, points=POINTS):
    indexed = {}
    for variant, rows in observations.items():
        for row in rows:
            fixture.require(row.get('type') == 'observation', 'failed_CoreText_GPOS_request_retained')
            k = (variant, *key(row['request']))
            fixture.require(k not in indexed, 'duplicate_CoreText_GPOS_observation')
            indexed[k] = row
    expected = {(variant, *key(request)) for route in fixture.ROUTES
                for request in requests(route, points) for variant in ('source', route)}
    fixture.require(set(indexed) == expected, 'incomplete_CoreText_GPOS_observations')
    result = {'layout_calls': len(indexed), 'paired_layout_calls': 0, 'glyph_comparisons': 0,
        'by_route_policy_direction': {}, 'drawing_statuses': {}, 'noncomparable_examples': [],
        'requested_vs_reported_axis_records': 0, 'regional_and_vertical_GSUB_differences': 0,
        'source_and_candidate_raw_metric_differences': 0}
    for route in fixture.ROUTES:
        for request in requests(route, points):
            k = key(request)
            source = indexed[('source', *k)]; candidate = indexed[(route, *k)]
            default_key = list(k); default_key[1] = 0
            default = indexed[('source', *default_key)]
            result['paired_layout_calls'] += 1
            result['requested_vs_reported_axis_records'] += any(
                row['reported_axes'] != request['requested'] for row in (source, candidate))
            group_key = '/'.join((route, request['policy'], request['direction']))
            group = result['by_route_policy_direction'].setdefault(group_key, {})
            context = {'request': request, 'source_reported_axes': source['reported_axes'],
                'candidate_reported_axes': candidate['reported_axes']}
            fixture.require(len(source['glyphs']) == len(candidate['glyphs']), 'CoreText_GPOS_changed_glyph_count')
            encoded = fixture.table_adjustments(candidates[route], symbols, request['normalized'])
            for b, a in zip(source['glyphs'], candidate['glyphs']):
                gid = a['gid']
                fixture.require(0 < gid < len(symbols) and a['actual_source_table_identity_verified']
                                and b['actual_source_table_identity_verified'], 'wrong_CoreText_GPOS_actual_font')
                c = {**context, 'source_glyph': b, 'candidate_glyph': a,
                     'continuous_source_advance': fixture.analytic_width(symbols[gid], request['normalized']),
                     'encoded_xPlacement_at_requested_normalized': encoded[symbols[gid].name]}
                result['regional_and_vertical_GSUB_differences'] += (a['gid'], a['cluster']) != (b['gid'], b['cluster'])
                for field in ('metric_width', 'metric_height', 'metric_vertical_origin', 'position', 'base_origin',
                              'advance', 'base_advance', 'line_origin', 'text_matrix', 'font_matrix'):
                    av, bv = a[field], b[field]
                    difference = subtract(av, bv) if isinstance(av, list) else [av-bv]
                    stat(group, field + '/candidate_minus_source', difference, c)
                    if field.startswith('metric_'):
                        result['source_and_candidate_raw_metric_differences'] += any(difference)
                stat(group, 'raw_width_minus_continuous_source',
                     [a['metric_width']-c['continuous_source_advance']], c)
                stat(group, 'raw_vertical_origin_X_minus_half_raw_width',
                     [a['metric_vertical_origin'][0]-a['metric_width']/2], c)
                result['glyph_comparisons'] += 1
            if len(candidate['glyphs']) == 1:
                glyph = candidate['glyphs'][0]
                compared = drawing_comparisons(default, source, candidate,
                    encoded[symbols[glyph['gid']].name], signs[route])
                status = compared['status']
                result['drawing_statuses'][status] = result['drawing_statuses'].get(status, 0) + 1
                if status == 'ACTUAL_DRAWING_MODELS_MEASURED':
                    c = {**context, 'source_default_glyph': default['glyphs'][0],
                         'source_glyph': source['glyphs'][0], 'candidate_glyph': glyph,
                         'encoded_xPlacement_at_requested_normalized': encoded[symbols[glyph['gid']].name]}
                    for field, delta in compared['fields'].items():
                        stat(group, field, delta, c)
                elif status != 'LAYOUT_RETAINED_WITHOUT_RASTER' and len(result['noncomparable_examples']) < 16:
                    result['noncomparable_examples'].append({**context, 'reason': status})
    result['raw_advance_axis_control_within_1_FUnit'] = all(
        not group['raw_width_minus_continuous_source']['above_reconstruction_1_FUnit']
        for group in result['by_route_policy_direction'].values())
    return result


def run(output):
    output = Path(output).resolve()
    fixture.require(not output.exists(), 'new_report_path_required')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'NOT_RUN', 'source_commit': os.environ.get('GITHUB_SHA'),
        'scope': 'independent_original_CoreText_GPOS_layout_and_drawing_only',
        'Apple_font_input': False, 'production_modified': False, 'font_binary_published': False,
        'paths_or_bitmaps_published': False, 'native_font_acceptance': False,
        'Windows_11_acceptance': 'NOT_RUN', 'Qt_acceptance': 'NOT_RUN',
        'exact_reference_limit': fixture.LIMIT, 'separate_reconstruction_reference_limit': fixture.RECONSTRUCTION_LIMIT,
        'raster_font_units_per_pixel': 1/RASTER_SCALE, 'points': [list(p) for p in POINTS],
        'native_processes': [], 'native_errors': []}
    try:
        fixture.require(sys.platform == 'darwin', 'CoreText_unavailable_native_layout_NOT_RUN')
        source, symbols = fixture.original_fixture()
        candidates = {route: fixture.add_adjustment(source, symbols, route)[0] for route in fixture.ROUTES}
        observations = {'source': [], **{route: [] for route in fixture.ROUTES}}
        # Retain already completed safe observations if a later native request,
        # process or protocol validation fails.
        report['synthetic_observations'] = observations
        signs = {}
        with tempfile.TemporaryDirectory(prefix='swirl-original-gpos-coretext-') as folder:
            temp = Path(folder)
            swift = temp/'gpos.swift'; binary = temp/'gpos'
            swift.write_text(make_harness(), encoding='utf-8')
            report['native_harness_sha256'] = hashlib.sha256(swift.read_bytes()).hexdigest()
            compiled = subprocess.run(['xcrun', 'swiftc', '-O', str(swift), '-o', str(binary)],
                                      capture_output=True, text=True, timeout=180)
            fixture.require(compiled.returncode == 0, 'CoreText_GPOS_compile_failed:' + compiled.stderr[-6000:])
            # Do not register the same family globally. Every baseline/route uses
            # a fresh native process, and every shaped run checks raw table hashes.
            for route in fixture.ROUTES:
                for variant, data in (('source', source), (route, candidates[route])):
                    font_path = temp/(variant+'-'+route+'.ttf')
                    font_path.write_bytes(data)
                    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
                    table_tags = (*fixture.PROTECTED, 'name', 'GPOS', 'GDEF')
                    hashes = {tag: hashlib.sha256(font.getTableData(tag)).hexdigest()
                              for tag in table_tags if tag in font}
                    configuration = {'scope': 'independent_original_GPOS_fixture_only',
                        'font_path': str(font_path), 'font_sha256': hashlib.sha256(data).hexdigest(),
                        'table_hashes': hashes, 'absent_tables': [tag for tag in ('GPOS', 'GDEF') if tag not in font],
                        'requests': requests(route)}
                    manifest = temp/'request.json'
                    manifest.write_text(json.dumps(configuration, allow_nan=False), encoding='utf-8')
                    observed = subprocess.run([str(binary), str(manifest)], capture_output=True, text=True, timeout=900)
                    rows = [json.loads(line) for line in observed.stdout.splitlines() if line]
                    errors = [row for row in rows if row.get('type') in ('request_error', 'fatal')]
                    report['native_errors'].extend({'variant': variant, 'route': route, **row} for row in errors)
                    meta = next((row for row in rows if row.get('type') == 'metadata'), None)
                    summary = next((row for row in rows if row.get('type') == 'summary'), None)
                    report['native_processes'].append({'variant': variant, 'route': route,
                        'returncode': observed.returncode, 'metadata': meta, 'summary': summary,
                        'stderr': observed.stderr[-3000:]})
                    observations[variant].extend(row for row in rows if row.get('type') == 'observation')
                    fixture.require(meta and meta.get('font_sha256') == configuration['font_sha256']
                        and meta.get('Apple_font_input') is False and meta.get('paths_or_bitmaps_emitted') is False,
                        'CoreText_GPOS_metadata_mismatch')
                    sign, calibration = raster_sign(meta)
                    report['native_processes'][-1]['raster_calibration_residual'] = calibration
                    if route in signs:
                        fixture.require(sign == signs[route], 'CoreText_GPOS_raster_coordinate_sign_changed')
                    signs[route] = sign
                    fixture.require(observed.returncode == 0 and summary and not errors
                        and summary.get('observations') == len(configuration['requests'])
                        and summary.get('errors') == 0, 'CoreText_GPOS_native_execution_incomplete')
            report['analysis'] = analyze(observations, candidates, symbols, signs)
            # Original synthetic observations allow independently auditing feature
            # selection, every cluster and layout metric without retaining images.
            report['synthetic_observations'] = observations
        report['interpretation'] = {
            'routing': 'Actual default/explicit/off behavior is observed, not assumed from a feature tag.',
            'double_compensation': 'candidate-minus-source-default drawing drift remains visible even if '
                'candidate-minus-source matches the encoded GPOS adjustment. A source already using a '
                'fixed X origin can be made wrong by an otherwise correctly applied adjustment.',
            'directions': 'Every declared matrix projection is retained; no best model is picked per glyph.',
            'precision': 'Raw metric and position comparisons keep both 1/32 and 1 FUnit references. Raster '
                'centroids are diagnostic at the stated resolution and cannot establish either font gate.',
            'scope': 'Independent fixture only. No Apple source conversion, Windows 11 or Qt acceptance.'}
        report['status'] = 'CORETEXT_GPOS_ACTUAL_LAYOUT_MEASURED_NOT_PRODUCTION_ACCEPTANCE'
    except Exception as error:
        report['status'] = ('CORETEXT_NATIVE_LAYOUT_NOT_RUN' if sys.platform != 'darwin'
                            else 'CORETEXT_GPOS_LAYOUT_DIAGNOSTIC_FAILED')
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({'status': result['status'], 'layout_calls': result['analysis']['layout_calls'],
                      'drawing_statuses': result['analysis']['drawing_statuses']}))
