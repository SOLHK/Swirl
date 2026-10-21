// Self-authored P5 control only: bounded physical-face/CoreText diagnostics.
// References: Apple CTFontCopyVariation, CTFontGetAdvancesForGlyphs,
// CTFontCreatePathForGlyph, CTFontGetVerticalTranslationsForGlyphs, CTRunGetPositions.
import Foundation
import CoreText
import CoreGraphics
import CryptoKit

enum ProbeError: Error { case invalid(String) }
func require(_ condition: Bool, _ message: String) throws {
    if !condition { throw ProbeError.invalid(message) }
}
func sha(_ data: Data) -> String { SHA256.hash(data: data).map { String(format:"%02x", $0) }.joined() }
func emit(_ record: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
}
func u16(_ d: Data, _ p: Int) throws -> Int {
    try require(p >= 0 && p+2 <= d.count, "truncated_u16")
    return Int(d[p]) << 8 | Int(d[p+1])
}
func u32(_ d: Data, _ p: Int) throws -> Int {
    try require(p >= 0 && p+4 <= d.count, "truncated_u32")
    return Int(d[p]) << 24 | Int(d[p+1]) << 16 | Int(d[p+2]) << 8 | Int(d[p+3])
}
func tag(_ value: String) throws -> CTFontTableTag {
    let bytes = Array(value.utf8)
    try require(bytes.count == 4, "axis_or_table_tag_length")
    return bytes.reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
}
func tagName(_ value: UInt32) -> String {
    String(bytes: [24,16,8,0].map { UInt8((value >> $0) & 255) }, encoding: .ascii)!
}
let identityTags = ["head", "maxp", "name", "cmap", "fvar", "avar", "glyf", "gvar", "hmtx", "vmtx", "HVAR", "VVAR"]
func verify(_ font: CTFont, _ tables: [String: Data]) throws {
    try require(CTFontGetGlyphCount(font) == 7, "not_authored_seven_GID_control")
    for name in identityTags {
        guard let native = CTFontCopyTable(font, try tag(name), CTFontTableOptions(rawValue: 0)) else {
            throw ProbeError.invalid("missing_native_table:\(name)")
        }
        try require(native as Data == tables[name]!, "physical_face_table_identity:\(name)")
    }
}
func matrix(_ m: CGAffineTransform) -> [Double] { [m.a,m.b,m.c,m.d,m.tx,m.ty].map(Double.init) }
func lineRecord(_ font: CTFont, _ tables: [String: Data], vertical: Bool) throws -> [String: Any] {
    let attributes = [kCTFontAttributeName as String: font,
                      kCTVerticalFormsAttributeName as String: vertical] as [String: Any]
    let text = CFAttributedStringCreate(nil, "A" as CFString, attributes as CFDictionary)!
    let line = CTLineCreateWithAttributedString(text)
    let runs = CTLineGetGlyphRuns(line) as! [CTRun]
    try require(runs.count == 1 && CTRunGetGlyphCount(runs[0]) == 1, "authored_A_run_shape_changed")
    let run = runs[0]
    let attrs = CTRunGetAttributes(run) as NSDictionary
    guard let actualFont = attrs[kCTFontAttributeName] else { throw ProbeError.invalid("run_font_missing") }
    try verify(actualFont as! CTFont, tables)
    var glyph = CGGlyph(0), point = CGPoint.zero, advance = CGSize.zero
    CTRunGetGlyphs(run, CFRange(location: 0, length: 1), &glyph)
    CTRunGetPositions(run, CFRange(location: 0, length: 1), &point)
    CTRunGetAdvances(run, CFRange(location: 0, length: 1), &advance)
    // The authored fixture deliberately has vert { sub A by regional; }.
    // Retain that actual final GID separately from the direct GID2 queries.
    try require(glyph > 0 && glyph < 7, "authored_A_missing_or_unrelated_GID")
    var ascent = CGFloat.zero, descent = CGFloat.zero, leading = CGFloat.zero
    let width = CTLineGetTypographicBounds(line, &ascent, &descent, &leading)
    return ["vertical": vertical, "nominal_gid": 2, "gid": Int(glyph), "position": [Double(point.x),Double(point.y)],
            "advance": [Double(advance.width),Double(advance.height)], "text_matrix": matrix(CTRunGetTextMatrix(run)),
            "typographic_width": width, "ascent": Double(ascent), "descent": Double(descent),
            "leading": Double(leading), "physical_run_face_verified": true]
}
func main() throws {
    try require(CommandLine.arguments.count >= 6, "font_face_sizes_and_three_axes_required")
    let url = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
    guard let face = Int(CommandLine.arguments[2]) else { throw ProbeError.invalid("face") }
    let sizes = CommandLine.arguments[3].split(separator:",").compactMap { Double($0) }
    try require(!sizes.isEmpty && sizes.allSatisfy { $0.isFinite && $0 > 0 && $0 <= 20000 }, "bounded_positive_sizes")
    var requested: [String: Double] = [:]
    for raw in CommandLine.arguments.dropFirst(4) {
        let pair = raw.split(separator:"=")
        try require(pair.count == 2 && requested[String(pair[0])] == nil, "duplicate_or_bad_axis")
        guard let number = Double(pair[1]), number.isFinite else { throw ProbeError.invalid("axis_number") }
        requested[String(pair[0])] = number
    }
    try require(requested.count == 3, "three_explicit_axes_required")
    let bytes = try Data(contentsOf: url)
    let magic = try u32(bytes, 0)
    var start = 0
    if magic == 0x74746366 {
        let faces = try u32(bytes, 8)
        try require((faces == 1 || faces == 32) && (0..<faces).contains(face), "bounded_authored_face_count_required")
        start = try u32(bytes, 12+4*face)
    } else {
        try require(magic == 0x00010000 && face == 0, "authored_TrueType_face_required")
    }
    try require(bytes.count < 2_000_000, "authored_control_size_limit")
    let count = try u16(bytes, start+4)
    var tables: [String: Data] = [:]
    for index in 0..<count {
        let record = start+12+16*index
        let name = tagName(UInt32(try u32(bytes, record)))
        let offset = try u32(bytes, record+8), length = try u32(bytes, record+12)
        try require(offset >= 0 && length >= 0 && offset+length <= bytes.count && tables[name] == nil, "invalid_table_range")
        tables[name] = bytes.subdata(in: offset..<offset+length)
    }
    try require(identityTags.allSatisfy { tables[$0] != nil }, "authored_control_tables_required")
    try require(try u16(tables["maxp"]!, 4) == 7, "authored_control_seven_GIDs_required")
    var registerError: Unmanaged<CFError>?
    try require(CTFontManagerRegisterFontsForURL(url as CFURL, .process, &registerError), "process_registration_failed")
    defer {
        var error: Unmanaged<CFError>?
        let ok = CTFontManagerUnregisterFontsForURL(url as CFURL, .process, &error)
        try? emit(["type": "cleanup", "process_unregistered": ok, "source_sha256": sha(bytes)])
    }
    guard let descriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor] else {
        throw ProbeError.invalid("no_URL_descriptors")
    }
    var matches: [CTFont] = []
    for descriptor in descriptors {
        let font = CTFontCreateWithFontDescriptor(descriptor, 1000, nil)
        if (try? verify(font, tables)) != nil { matches.append(font) }
    }
    try require(matches.count == 1, "physical_face_binding_not_unique")
    let base = matches[0]
    guard let axes = CTFontCopyVariationAxes(base) as? [[String: Any]] else { throw ProbeError.invalid("no_axes") }
    var variations: [NSNumber: NSNumber] = [:], defaults: [String: Double] = [:]
    for axis in axes {
        let id = axis[kCTFontVariationAxisIdentifierKey as String] as! NSNumber
        let name = tagName(id.uint32Value)
        guard let value = requested[name] else { throw ProbeError.invalid("wrong_axis_tags") }
        let minimum = (axis[kCTFontVariationAxisMinimumValueKey as String] as! NSNumber).doubleValue
        let maximum = (axis[kCTFontVariationAxisMaximumValueKey as String] as! NSNumber).doubleValue
        defaults[name] = (axis[kCTFontVariationAxisDefaultValueKey as String] as! NSNumber).doubleValue
        try require(value >= minimum && value <= maximum, "axis_range")
        variations[id] = NSNumber(value: value)
    }
    let descriptor = CTFontDescriptorCreateWithAttributes([
        kCTFontVariationAttribute as String: variations
    ] as CFDictionary)
    for size in sizes {
        var identity = CGAffineTransform.identity
        let font = CTFontCreateCopyWithAttributes(base, size, &identity, descriptor)
        try verify(font, tables)
        try require(CTFontGetSize(font) == size && CTFontGetMatrix(font).isIdentity, "native_size_or_matrix_changed")
        var reported: [String: Double] = [:]
        if let values = CTFontCopyVariation(font) as? [NSNumber: NSNumber] {
            for (key, value) in values { reported[tagName(key.uint32Value)] = value.doubleValue }
        }
        var glyph = CGGlyph(2), h = CGSize.zero, v = CGSize.zero, t = CGSize.zero
        let hsum = CTFontGetAdvancesForGlyphs(font, .horizontal, &glyph, &h, 1)
        let vsum = CTFontGetAdvancesForGlyphs(font, .vertical, &glyph, &v, 1)
        CTFontGetVerticalTranslationsForGlyphs(font, &glyph, &t, 1)
        guard let path = CTFontCreatePathForGlyph(font, glyph, nil) else { throw ProbeError.invalid("missing_authored_path") }
        var commands: [[Any]] = []
        path.applyWithBlock { pointer in
            let e = pointer.pointee
            let names: [CGPathElementType: (String, Int)] = [.moveToPoint:("moveTo",1), .addLineToPoint:("lineTo",1),
                .addQuadCurveToPoint:("qCurveTo",2), .addCurveToPoint:("curveTo",3), .closeSubpath:("closePath",0)]
            if let (name, n) = names[e.type] {
                var row: [Any] = [name]
                for i in 0..<n { row += [Double(e.points[i].x), Double(e.points[i].y)] }
                commands.append(row)
            }
        }
        try emit(["type": "measurement", "source_sha256": sha(bytes), "face_index": face, "glyph_id": 2,
            "postscript_name": CTFontCopyPostScriptName(font), "font_upem": CTFontGetUnitsPerEm(font), "point_size": size,
            "requested_axes": requested, "reported_axes": reported, "default_axes": defaults,
            "horizontal_vector": [Double(h.width),Double(h.height)], "vertical_vector": [Double(v.width),Double(v.height)],
            "horizontal_sum": hsum, "vertical_sum": vsum, "vertical_translation": [Double(t.width),Double(t.height)],
            "font_ascent": CTFontGetAscent(font), "font_descent": CTFontGetDescent(font), "font_leading": CTFontGetLeading(font),
            "commands": commands, "horizontal_layout": try lineRecord(font, tables, vertical:false),
            "vertical_layout": try lineRecord(font, tables, vertical:true), "physical_face_verified": true,
            "os_version": ProcessInfo.processInfo.operatingSystemVersionString])
    }
    try require(sha(try Data(contentsOf: url)) == sha(bytes), "authored_source_changed")
}
do { try main() }
catch { try? emit(["type":"error", "error":String(describing:error)]); exit(2) }
