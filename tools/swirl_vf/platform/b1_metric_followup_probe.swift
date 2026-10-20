// SPDX-License-Identifier: MIT
// Independent B1 diagnostic; never a reconstruction oracle or acceptance gate.
// Follow-up-only copy: failed readback evidence, unchanged strict admission.
// Build: xcrun swiftc -O b1_metric_followup_probe.swift -o b1_metric_followup_probe
// Usage: b1_metric_followup_probe --font fixture.ttf --requests requests.json --output raw.json
// This probe is intended for self-authored single-face SFNT fixtures only.

import Foundation
import CoreFoundation
import CoreText
import CoreGraphics
import CryptoKit
import Darwin

enum B1Error: Error, CustomStringConvertible {
    case invalid(String)
    var description: String {
        switch self { case .invalid(let message): return message }
    }
}

func require(_ condition: Bool, _ message: String) throws {
    if !condition { throw B1Error.invalid(message) }
}

func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

// JSONEncoder encodes typed Double directly. Do not route floating-point
// observations through JSONSerialization's NSNumber decimal conversion.
private enum ExactJSON: Encodable {
    case null, boolean(Bool), integer(Int64), unsignedInteger(UInt64)
    case number(Double), string(String), array([ExactJSON]), object([String: ExactJSON])

    init(_ value: Any) throws {
        if value is NSNull {
            self = .null
        } else if let text = value as? String {
            self = .string(text)
        } else if type(of: value) == Double.self {
            let number = value as! Double
            try require(number.isFinite, "nonfinite_output_double")
            self = .number(number)
        } else if let number = value as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                self = .boolean(number.boolValue)
            } else {
                switch String(cString: number.objCType) {
                case "f", "d":
                    try require(number.doubleValue.isFinite, "nonfinite_output_number")
                    self = .number(number.doubleValue)
                case "Q": self = .unsignedInteger(number.uint64Value)
                default: self = .integer(number.int64Value)
                }
            }
        } else if let object = value as? [String: Any] {
            self = .object(try object.mapValues { try ExactJSON($0) })
        } else if let array = value as? [Any] {
            self = .array(try array.map { try ExactJSON($0) })
        } else {
            throw B1Error.invalid("unsupported_json_type:\(type(of: value))")
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .boolean(let v): try c.encode(v)
        case .integer(let v): try c.encode(v)
        case .unsignedInteger(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        }
    }
}

func appendBits(_ value: Any, _ path: String, _ output: inout [String: String]) throws {
    if type(of: value) == Double.self {
        let number = value as! Double
        try require(number.isFinite, "nonfinite_binary64_observation")
        output[path] = String(format: "%016llx", number.bitPattern)
    } else if let object = value as? [String: Any] {
        for key in object.keys.sorted() {
            try appendBits(object[key]!, path + "." + key, &output)
        }
    } else if let array = value as? [Any] {
        for (index, item) in array.enumerated() {
            try appendBits(item, path + "[\(index)]", &output)
        }
    }
}

func save(_ report: [String: Any], _ url: URL) throws {
    var result = report
    var bits: [String: String] = [:]
    try appendBits(report, "$", &bits)
    result["binary64_hex_by_json_path"] = bits
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    var data = try encoder.encode(ExactJSON(result))
    data.append(10)
    try data.write(to: url, options: [.atomic])
}

struct FontBytes {
    let data: Data
    func range(_ offset: Int, _ count: Int) throws -> Range<Int> {
        try require(offset >= 0 && count >= 0 && offset <= data.count && count <= data.count-offset,
                    "sfnt_byte_range_out_of_bounds")
        return offset..<(offset+count)
    }
    func u16(_ offset: Int) throws -> UInt16 {
        _ = try range(offset, 2)
        return UInt16(data[offset]) << 8 | UInt16(data[offset+1])
    }
    func u32(_ offset: Int) throws -> UInt32 {
        _ = try range(offset, 4)
        return UInt32(data[offset]) << 24 | UInt32(data[offset+1]) << 16 |
               UInt32(data[offset+2]) << 8 | UInt32(data[offset+3])
    }
    func fixed(_ offset: Int) throws -> Double {
        Double(Int32(bitPattern: try u32(offset))) / 65536.0
    }
    func slice(_ offset: Int, _ count: Int) throws -> Data {
        data.subdata(in: try range(offset, count))
    }
    func tag(_ offset: Int) throws -> String {
        guard let value = String(data: try slice(offset, 4), encoding: .ascii) else {
            throw B1Error.invalid("non_ascii_table_tag")
        }
        return value
    }
}

func tagID(_ value: String) -> UInt32 {
    value.utf8.reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
}

func tagString(_ value: UInt32) -> String {
    String(bytes: [UInt8((value >> 24) & 255), UInt8((value >> 16) & 255),
                   UInt8((value >> 8) & 255), UInt8(value & 255)], encoding: .ascii) ?? "?"
}

struct Axis {
    let tag: String
    let minimum: Double
    let defaultValue: Double
    let maximum: Double
    var json: [String: Any] {
        ["tag": tag, "minimum": minimum, "default": defaultValue, "maximum": maximum]
    }
}

struct Table {
    let offset: Int
    let count: Int
    let hash: String
}

struct Source {
    let data: Data
    let hash: String
    let tables: [String: Table]
    let upem: Int
    let glyphCount: Int
    let axes: [Axis]

    init(_ data: Data) throws {
        let b = FontBytes(data: data)
        let signature = try b.u32(0)
        try require(signature == 0x00010000 || signature == tagID("OTTO"),
                    "single_face_sfnt_required_no_TTC")
        let count = Int(try b.u16(4))
        try require(count > 0 && count < 1024, "invalid_table_count")
        _ = try b.range(12, count*16)
        var tables: [String: Table] = [:]
        for index in 0..<count {
            let p = 12 + index*16
            let tag = try b.tag(p)
            let offset = Int(try b.u32(p+8)), length = Int(try b.u32(p+12))
            try require(tables[tag] == nil, "duplicate_sfnt_table")
            let raw = try b.slice(offset, length)
            tables[tag] = Table(offset: offset, count: length, hash: sha256(raw))
        }
        guard let head = tables["head"], let maxp = tables["maxp"] else {
            throw B1Error.invalid("missing_head_or_maxp")
        }
        try require(head.count >= 54 && maxp.count >= 6, "truncated_head_or_maxp")
        let upem = Int(try b.u16(head.offset+18)), glyphCount = Int(try b.u16(maxp.offset+4))
        try require(upem > 0 && glyphCount > 0, "invalid_upem_or_glyph_count")
        var axes: [Axis] = []
        if let fvar = tables["fvar"] {
            try require(fvar.count >= 16, "truncated_fvar_header")
            let arrayOffset = Int(try b.u16(fvar.offset+4))
            let axisCount = Int(try b.u16(fvar.offset+8))
            let axisSize = Int(try b.u16(fvar.offset+10))
            try require(axisSize >= 20 && arrayOffset >= 16 &&
                        arrayOffset + axisCount*axisSize <= fvar.count, "invalid_fvar_axis_range")
            for index in 0..<axisCount {
                let p = fvar.offset + arrayOffset + index*axisSize
                let axis = Axis(tag: try b.tag(p), minimum: try b.fixed(p+4),
                                defaultValue: try b.fixed(p+8), maximum: try b.fixed(p+12))
                try require(axis.minimum <= axis.defaultValue && axis.defaultValue <= axis.maximum,
                            "unordered_fvar_axis")
                try require(!axes.contains(where: { $0.tag == axis.tag }), "duplicate_fvar_axis")
                axes.append(axis)
            }
        }
        self.data = data; self.hash = sha256(data); self.tables = tables
        self.upem = upem; self.glyphCount = glyphCount; self.axes = axes
    }

    var metadata: [String: Any] {
        ["sha256": hash, "byte_length": data.count, "upem": upem,
         "glyph_count": glyphCount, "axes": axes.map(\.json),
         "table_sha256": tables.mapValues(\.hash), "table_lengths": tables.mapValues(\.count),
         "input_format": "single_face_sfnt", "source_modified": false]
    }
}

func verifiedTables(_ font: CTFont, _ source: Source) throws -> [String: String] {
    try require(CTFontGetUnitsPerEm(font) == UInt32(source.upem) &&
                CTFontGetGlyphCount(font) == source.glyphCount, "font_upem_or_glyph_count_changed")
    var hashes: [String: String] = [:]
    for tag in source.tables.keys.sorted() {
        guard let raw = CTFontCopyTable(font, CTFontTableTag(tagID(tag)),
                                       CTFontTableOptions(rawValue: 0)) as Data? else {
            throw B1Error.invalid("font_missing_source_table:\(tag)")
        }
        let expected = source.tables[tag]!
        try require(raw.count == expected.count && sha256(raw) == expected.hash,
                    "font_table_identity_mismatch:\(tag)")
        hashes[tag] = sha256(raw)
    }
    return hashes
}

func reportedAxes(_ font: CTFont) -> [String: Double] {
    var values: [String: Double] = [:]
    if let raw = CTFontCopyVariation(font) as? [NSNumber: NSNumber] {
        for (key, value) in raw { values[tagString(key.uint32Value)] = value.doubleValue }
    }
    return values
}

func matrix(_ m: CGAffineTransform) -> [Double] {
    [Double(m.a), Double(m.b), Double(m.c), Double(m.d), Double(m.tx), Double(m.ty)]
}
func vector(_ p: CGPoint) -> [Double] { [Double(p.x), Double(p.y)] }
func size(_ p: CGSize) -> [Double] { [Double(p.width), Double(p.height)] }
func rectangle(_ r: CGRect) -> [Double] {
    [Double(r.origin.x), Double(r.origin.y), Double(r.width), Double(r.height)]
}

struct Request: Decodable {
    let id: String
    let axes: [String: Double]
    let point_size: Double
}

func fullLocation(_ request: Request, _ source: Source) throws -> [String: Double] {
    let tags = Set(source.axes.map(\.tag))
    try require(request.axes.keys.allSatisfy({ tags.contains($0) }), "unknown_request_axis")
    var location: [String: Double] = [:]
    for axis in source.axes {
        let value = request.axes[axis.tag] ?? axis.defaultValue
        try require(value.isFinite && value >= axis.minimum && value <= axis.maximum,
                    "request_axis_out_of_range:\(axis.tag)")
        location[axis.tag] = value
    }
    return location
}

func verifyInstance(_ font: CTFont, _ source: Source, _ location: [String: Double],
                    _ pointSize: Double) throws -> [String: Any] {
    let hashes = try verifiedTables(font, source)
    try require(Double(CTFontGetSize(font)) == pointSize && CTFontGetMatrix(font).isIdentity,
                "instance_size_or_font_matrix_changed")
    let reported = reportedAxes(font)
    try require(Set(reported.keys).isSubset(of: Set(source.axes.map(\.tag))), "unexpected_native_axis")
    for axis in source.axes {
        let actual = reported[axis.tag] ?? axis.defaultValue
        let requested = location[axis.tag]!
        let requestedBits = String(format: "%016llx", requested.bitPattern)
        let actualBits = String(format: "%016llx", actual.bitPattern)
        try require(actual == requested,
                    "native_axis_readback_not_exact:\(axis.tag):requested=\(requested):requested_binary64=\(requestedBits):actual=\(actual):actual_binary64=\(actualBits)")
    }
    return ["postscript_name": CTFontCopyPostScriptName(font) as String,
            "point_size": Double(CTFontGetSize(font)), "upem": Int(CTFontGetUnitsPerEm(font)),
            "glyph_count": CTFontGetGlyphCount(font), "font_matrix": matrix(CTFontGetMatrix(font)),
            "requested_axes_with_defaults": location, "reported_axes": reported,
            "verified_table_sha256": hashes, "all_source_tables_verified": true,
            "axes_size_and_matrix_verified": true]
}

func makeInstance(_ base: CTFont, _ source: Source, _ request: Request,
                  _ readbackEvidence: inout [String: Any]) throws -> (CTFont, [String: Double]) {
    try require(request.point_size.isFinite && request.point_size > 0 && request.point_size <= 1_048_576,
                "invalid_request_point_size")
    let location = try fullLocation(request, source)
    var variations: [NSNumber: NSNumber] = [:]
    for (tag, value) in location { variations[NSNumber(value: tagID(tag))] = NSNumber(value: value) }
    let attributes: [String: Any] = [kCTFontVariationAttribute as String: variations,
        "NSCTFontUnscaledTrackingAttribute": NSNumber(value: 0)]
    let descriptor = CTFontDescriptorCreateWithAttributes(attributes as CFDictionary)
    var identity = CGAffineTransform.identity
    let font = CTFontCreateCopyWithAttributes(base, CGFloat(request.point_size), &identity, descriptor)
    // Preserve typed Double values before any strict instance rejection. This
    // does not mark source tables or axes verified and measures no glyph data.
    readbackEvidence["reported_axes"] = reportedAxes(font)
    readbackEvidence["requested_defaults"] = location
    _ = try verifyInstance(font, source, location, request.point_size)
    return (font, location)
}

func directObservation(_ font: CTFont, _ glyphID: CGGlyph) throws -> [String: Any] {
    var glyph = glyphID
    var h = CGSize.zero, v = CGSize.zero, t = CGSize.zero
    let horizontalSum = CTFontGetAdvancesForGlyphs(font, .horizontal, &glyph, &h, 1)
    let verticalSum = CTFontGetAdvancesForGlyphs(font, .vertical, &glyph, &v, 1)
    CTFontGetVerticalTranslationsForGlyphs(font, &glyph, &t, 1)
    let all = size(h) + size(v) + size(t) + [horizontalSum, verticalSum]
    try require(all.allSatisfy(\.isFinite), "nonfinite_direct_observation")
    let graphics = CTFontCopyGraphicsFont(font, nil)
    var advance: Int32 = 0
    let success = graphics.getGlyphAdvances(glyphs: &glyph, count: 1, advances: &advance)
    var auxiliary: [String: Any] = ["status": success ? "MEASURED" : "API_RETURNED_FALSE",
        "api": "CGFont.getGlyphAdvances", "orientation": "horizontal_only",
        "units": "CGFont_integer_design_units", "graphics_upem": graphics.unitsPerEm,
        "not_a_vertical_metric_observation": true]
    if success { auxiliary["advance_int32"] = Int(advance) }
    return ["direct_advances": ["api": "CTFontGetAdvancesForGlyphs", "units": "points",
                "horizontal_vector": size(h), "vertical_vector": size(v),
                "horizontal_sum": horizontalSum, "vertical_sum": verticalSum,
                "vertical_advance_component": "vertical_vector[0] (raw CGSize.width)",
                "count": 1, "raw_values_unmodified": true],
            "vertical_translation": ["api": "CTFontGetVerticalTranslationsForGlyphs",
                "units": "points", "raw_vector": size(t), "raw_values_unmodified": true,
                "origin_interpretation": "negative raw vector; no negation is applied to this record"],
            "cgfont_horizontal_auxiliary": auxiliary,
            "global_font_metrics": ["units": "points", "ascent": Double(CTFontGetAscent(font)),
                "descent": Double(CTFontGetDescent(font)), "leading": Double(CTFontGetLeading(font)),
                "cap_height": Double(CTFontGetCapHeight(font)), "x_height": Double(CTFontGetXHeight(font)),
                "underline_position": Double(CTFontGetUnderlinePosition(font)),
                "underline_thickness": Double(CTFontGetUnderlineThickness(font))]]
}

func witnessPath(_ font: CTFont, _ glyph: CGGlyph) throws -> [String: Any] {
    guard let path = CTFontCreatePathForGlyph(font, glyph, nil), !path.isEmpty else {
        throw B1Error.invalid("nonempty_CJK_witness_path_required")
    }
    var commands: [[Any]] = []
    var pathError: String? = nil
    path.applyWithBlock { pointer in
        guard pathError == nil else { return }
        let element = pointer.pointee
        var command: [Any]
        let count: Int
        switch element.type {
        case .moveToPoint: command = ["moveTo"]; count = 1
        case .addLineToPoint: command = ["lineTo"]; count = 1
        case .addQuadCurveToPoint: command = ["qCurveTo"]; count = 2
        case .addCurveToPoint: command = ["curveTo"]; count = 3
        case .closeSubpath: command = ["closePath"]; count = 0
        @unknown default: pathError = "unknown_path_element"; return
        }
        for index in 0..<count {
            let p = element.points[index]
            guard p.x.isFinite && p.y.isFinite else { pathError = "nonfinite_path_point"; return }
            command.append(Double(p.x)); command.append(Double(p.y))
        }
        commands.append(command)
        if commands.count > 100_000 { pathError = "witness_path_limit_exceeded" }
    }
    if let error = pathError { throw B1Error.invalid(error) }
    return ["api": "CTFontCreatePathForGlyph", "units": "points", "commands": commands,
            "geometric_bounds_xywh": rectangle(path.boundingBoxOfPath),
            "control_bounds_xywh": rectangle(path.boundingBox),
            "raw_values_unmodified": true,
            "meaning": "visible self-authored witness contour; not direct access to hidden phantom points"]
}

func verticalLayout(_ font: CTFont, _ source: Source, _ location: [String: Double],
                    _ glyphID: CGGlyph, _ pointSize: Double) throws -> [String: Any] {
    let attributes: [String: Any] = [kCTFontAttributeName as String: font,
        kCTVerticalFormsAttributeName as String: true, kCTKernAttributeName as String: 0]
    guard let text = CFAttributedStringCreate(nil, "一一" as CFString, attributes as CFDictionary) else {
        throw B1Error.invalid("vertical_attributed_string_creation_failed")
    }
    let setter = CTFramesetterCreateWithAttributedString(text)
    let rect = CGRect(x: 0, y: 0, width: CGFloat(max(8192.0, pointSize*4)),
                      height: CGFloat(max(8192.0, pointSize*8)))
    let frame = CTFramesetterCreateFrame(setter, CFRange(location: 0, length: 0),
        CGPath(rect: rect, transform: nil),
        [kCTFrameProgressionAttributeName as String: CTFrameProgression.rightToLeft.rawValue] as CFDictionary)
    let visible = CTFrameGetVisibleStringRange(frame)
    guard visible.location == 0 && visible.length == 2,
          let lines = CTFrameGetLines(frame) as? [CTLine], lines.count == 1 else {
        throw B1Error.invalid("vertical_frame_must_layout_both_characters_on_one_line")
    }
    var lineOrigins = [CGPoint](repeating: .zero, count: lines.count)
    CTFrameGetLineOrigins(frame, CFRange(location: 0, length: 0), &lineOrigins)
    var runRows: [[String: Any]] = []
    var glyphRows: [[String: Any]] = []
    var lineRows: [[String: Any]] = []
    var seenStringIndices: [Int] = []
    for (lineIndex, line) in lines.enumerated() {
        var lineAscent: CGFloat = 0, lineDescent: CGFloat = 0, lineLeading: CGFloat = 0
        let lineWidth = CTLineGetTypographicBounds(line, &lineAscent, &lineDescent, &lineLeading)
        lineRows.append(["index": lineIndex, "origin": vector(lineOrigins[lineIndex]),
            "typographic_width": lineWidth, "ascent": Double(lineAscent),
            "descent": Double(lineDescent), "leading": Double(lineLeading)])
        guard let runs = CTLineGetGlyphRuns(line) as? [CTRun], !runs.isEmpty else {
            throw B1Error.invalid("vertical_runs_missing")
        }
        for run in runs {
            let attrs = CTRunGetAttributes(run) as NSDictionary
            guard let rawFont = attrs[kCTFontAttributeName] else { throw B1Error.invalid("run_font_missing") }
            let runFont = rawFont as! CTFont
            let identity = try verifyInstance(runFont, source, location, pointSize)
            let n = CTRunGetGlyphCount(run)
            try require(n > 0 && n <= 2, "unexpected_vertical_run_glyph_count")
            let range = CFRange(location: 0, length: 0)
            var glyphs = [CGGlyph](repeating: 0, count: n)
            var positions = [CGPoint](repeating: .zero, count: n)
            var advances = [CGSize](repeating: .zero, count: n)
            var baseAdvances = [CGSize](repeating: .zero, count: n)
            var baseOrigins = [CGPoint](repeating: .zero, count: n)
            var indices = [CFIndex](repeating: 0, count: n)
            CTRunGetGlyphs(run, range, &glyphs)
            CTRunGetPositions(run, range, &positions)
            CTRunGetAdvances(run, range, &advances)
            CTRunGetBaseAdvancesAndOrigins(run, range, &baseAdvances, &baseOrigins)
            CTRunGetStringIndices(run, range, &indices)
            let runIndex = runRows.count
            var ascent: CGFloat = 0, descent: CGFloat = 0, leading: CGFloat = 0
            let width = CTRunGetTypographicBounds(run, range, &ascent, &descent, &leading)
            runRows.append(["index": runIndex, "line": lineIndex, "font_identity": identity,
                "text_matrix": matrix(CTRunGetTextMatrix(run)), "status_flags": Int(CTRunGetStatus(run).rawValue),
                "typographic_width": width, "ascent": Double(ascent),
                "descent": Double(descent), "leading": Double(leading)])
            for i in 0..<n {
                try require(glyphs[i] == glyphID && indices[i] >= 0 && indices[i] < 2,
                            "vertical_substitution_or_fallback_not_comparable")
                seenStringIndices.append(indices[i])
                glyphRows.append(["glyph_id": Int(glyphs[i]), "string_index": indices[i],
                    "line": lineIndex, "run": runIndex, "line_origin": vector(lineOrigins[lineIndex]),
                    "position": vector(positions[i]), "advance": size(advances[i]),
                    "base_advance": size(baseAdvances[i]), "base_origin": vector(baseOrigins[i])])
            }
        }
    }
    try require(glyphRows.count == 2 && seenStringIndices.sorted() == [0, 1],
                "both_nominal_CJK_glyphs_required_without_fallback")
    return ["api": "CTFramesetter/CTFrame/CTRun", "text": "一一", "codepoints": [0x4E00, 0x4E00],
        "units": "points", "frame_rect_xywh": rectangle(rect), "frame_progression": "right_to_left",
        "vertical_forms": true, "kern_attribute": 0, "visible_utf16_range": [visible.location, visible.length],
        "lines": lineRows, "runs": runRows, "glyphs": glyphRows,
        "raw_values_unmodified": true, "both_nominal_glyphs_and_all_source_tables_verified": true,
        "base_origins_need_run_and_frame_transform_before_drawing": true]
}

func arguments() throws -> [String: String] {
    let tokens = Array(CommandLine.arguments.dropFirst())
    try require(tokens.count == 6, "usage: --font PATH --requests JSON --output JSON")
    let allowed = Set(["--font", "--requests", "--output"])
    var result: [String: String] = [:]
    for i in stride(from: 0, to: tokens.count, by: 2) {
        try require(allowed.contains(tokens[i]) && result[tokens[i]] == nil && !tokens[i+1].isEmpty,
                    "invalid_or_duplicate_argument")
        result[tokens[i]] = tokens[i+1]
    }
    return result
}

func run() throws -> Int32 {
    let args = try arguments()
    let url = URL(fileURLWithPath: args["--font"]!).standardizedFileURL.resolvingSymlinksInPath()
    let requestsURL = URL(fileURLWithPath: args["--requests"]!).standardizedFileURL.resolvingSymlinksInPath()
    let output = URL(fileURLWithPath: args["--output"]!).standardizedFileURL
    try require(output != url && output != requestsURL && !FileManager.default.fileExists(atPath: output.path),
                "new_output_path_required")
    var report: [String: Any] = ["schema_version": 1, "status": "NOT_RUN",
        "backend": "CoreText_B1_independent_diagnostic_only",
        "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
        "native_font_acceptance": "NOT_ESTABLISHED", "production_oracle_modified": false,
        "measurement_correction_applied": false, "raw_point_values_retained": true,
        "observations": [[String: Any]]()]
    var rows: [[String: Any]] = []
    do {
        let data = try Data(contentsOf: url)
        let source = try Source(data)
        let requestData = try Data(contentsOf: requestsURL)
        let requests = try JSONDecoder().decode([Request].self, from: requestData)
        try require(!requests.isEmpty && requests.count <= 10_000, "invalid_request_count")
        try require(requests.allSatisfy({ !$0.id.isEmpty }) && Set(requests.map(\.id)).count == requests.count,
                    "request_ids_must_be_unique_and_nonempty")
        report["source"] = source.metadata
        report["requests_sha256"] = sha256(requestData)
        report["expected_request_count"] = requests.count
        var registrationError: Unmanaged<CFError>?
        let registered = CTFontManagerRegisterFontsForURL(url as CFURL, .process, &registrationError)
        guard registered else {
            let detail = registrationError.map { String(describing: $0.takeRetainedValue()) } ?? "unknown"
            throw B1Error.invalid("process_font_registration_failed:\(detail)")
        }
        defer { CTFontManagerUnregisterFontsForURL(url as CFURL, .process, nil) }
        report["registration_scope"] = "isolated_process_current_fixture_URL_only"
        guard let descriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor],
              !descriptors.isEmpty else { throw B1Error.invalid("source_descriptor_missing") }
        var base: CTFont? = nil
        for descriptor in descriptors {
            var identity = CGAffineTransform.identity
            let candidate = CTFontCreateWithFontDescriptor(descriptor, CGFloat(source.upem), &identity)
            if (try? verifiedTables(candidate, source)) != nil { base = candidate; break }
        }
        guard let base = base else { throw B1Error.invalid("no_exact_source_descriptor") }
        report["base_reported_axes"] = reportedAxes(base)
        for request in requests {
            try autoreleasepool {
                var row: [String: Any] = ["id": request.id, "requested_axes": request.axes,
                    "point_size": request.point_size, "upem": source.upem,
                    "point_to_design_unit_basis": ["numerator_upem": source.upem,
                        "denominator_point_size": request.point_size,
                        "formula": "raw_points * numerator_upem / denominator_point_size",
                        "conversion_applied_to_raw_observations": false]]
                do {
                    let (font, location) = try makeInstance(base, source, request, &row)
                    row["font_identity"] = try verifyInstance(font, source, location, request.point_size)
                    var character = UniChar(0x4E00), glyph = CGGlyph(0)
                    try require(CTFontGetGlyphsForCharacters(font, &character, &glyph, 1) && glyph != 0,
                                "fixture_must_map_U4E00_to_nonzero_witness_glyph")
                    row["nominal_glyph_id"] = Int(glyph)
                    row.merge(try directObservation(font, glyph)) { _, new in new }
                    row["witness_path"] = try witnessPath(font, glyph)
                    row["vertical_layout"] = try verticalLayout(font, source, location, glyph, request.point_size)
                    row["status"] = "COMPLETE"
                    rows.append(row)
                } catch {
                    // A layout rejection must not discard already observed raw
                    // advances, translations or witness-path coordinates.
                    row["status"] = "FAILED"
                    row["error"] = String(describing: error)
                    rows.append(row)
                    throw error
                }
            }
        }
        try require(sha256(try Data(contentsOf: url)) == source.hash, "source_changed_during_observation")
        report["observations"] = rows
        report["completed_request_count"] = rows.filter { ($0["status"] as? String) == "COMPLETE" }.count
        report["source_unchanged_after_measurement"] = true
        report["status"] = "NATIVE_DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE"
        try save(report, output)
        return 0
    } catch {
        report["status"] = "NATIVE_DIAGNOSTIC_FAILED"
        report["observations"] = rows
        report["completed_request_count"] = rows.filter { ($0["status"] as? String) == "COMPLETE" }.count
        report["error"] = String(describing: error)
        try save(report, output)
        FileHandle.standardError.write(Data(("B1 metric diagnostic failed: \(error)\n").utf8))
        return 2
    }
}

do { exit(try run()) }
catch {
    FileHandle.standardError.write(Data(("B1 metric probe: \(error)\n").utf8))
    exit(2)
}
