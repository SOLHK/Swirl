// SPDX-License-Identifier: MIT
// Build on macOS: swiftc -O platform/coretext_extract.swift -o coretext_extract
// Usage: ./coretext_extract /private/path/PingFangUI.ttc < requests.jsonl > oracle.jsonl
// Source fonts and the resulting outlines must remain outside a public repository.

import Foundation
import CoreFoundation
import CoreText
import CoreGraphics
import CryptoKit
import Darwin

enum OracleError: Error, CustomStringConvertible {
    case invalid(String)
    var description: String {
        switch self { case .invalid(let message): return message }
    }
}

func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func stderr(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

// Keep binary64 measurements round-trippable. Foundation JSONSerialization on
// Darwin can spell a Double through an NSNumber decimal conversion that changes
// its least significant bits. JSONEncoder directly encodes the typed Double.
// The paired native transport test retains the legacy output as evidence.
private enum OracleJSON: Encodable {
    case null
    case boolean(Bool)
    case integer(Int64)
    case unsignedInteger(UInt64)
    case number(Double)
    case string(String)
    case array([OracleJSON])
    case object([String: OracleJSON])

    init(_ value: Any) throws {
        if value is NSNull {
            self = .null
        } else if let string = value as? String {
            self = .string(string)
        } else if type(of: value) == Double.self {
            let number = value as! Double
            guard number.isFinite else { throw OracleError.invalid("non_finite_output_number") }
            self = .number(number)
        } else if type(of: value) == Float.self {
            let number = value as! Float
            guard number.isFinite else { throw OracleError.invalid("non_finite_output_number") }
            self = .number(Double(number))
        } else if let number = value as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                self = .boolean(number.boolValue)
            } else {
                switch String(cString: number.objCType) {
                case "f", "d":
                    guard number.doubleValue.isFinite else {
                        throw OracleError.invalid("non_finite_output_number")
                    }
                    self = .number(number.doubleValue)
                case "Q":
                    self = .unsignedInteger(number.uint64Value)
                default:
                    self = .integer(number.int64Value)
                }
            }
        } else if let dictionary = value as? [String: Any] {
            self = .object(try dictionary.mapValues { try OracleJSON($0) })
        } else if let array = value as? [Any] {
            self = .array(try array.map { try OracleJSON($0) })
        } else {
            throw OracleError.invalid("unsupported_output_json_type")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case .boolean(let value): try container.encode(value)
        case .integer(let value): try container.encode(value)
        case .unsignedInteger(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .string(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        }
    }
}

func encodedJSON(_ value: [String: Any]) throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    return try encoder.encode(OracleJSON(value))
}

func emit(_ value: [String: Any]) throws {
    let data = try encodedJSON(value)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([10]))
}

struct Bytes {
    let data: Data
    func checked(_ offset: Int, _ length: Int) throws -> Range<Int> {
        guard offset >= 0, length >= 0, offset <= data.count, length <= data.count - offset else {
            throw OracleError.invalid("font_byte_range_out_of_bounds")
        }
        return offset ..< offset + length
    }
    func u16(_ offset: Int) throws -> UInt16 {
        _ = try checked(offset, 2)
        return UInt16(data[offset]) << 8 | UInt16(data[offset + 1])
    }
    func u32(_ offset: Int) throws -> UInt32 {
        _ = try checked(offset, 4)
        return UInt32(data[offset]) << 24 | UInt32(data[offset + 1]) << 16 |
               UInt32(data[offset + 2]) << 8 | UInt32(data[offset + 3])
    }
    func le16(_ offset: Int) throws -> UInt16 {
        _ = try checked(offset, 2)
        return UInt16(data[offset]) | UInt16(data[offset + 1]) << 8
    }
    func le32(_ offset: Int) throws -> UInt32 {
        _ = try checked(offset, 4)
        return UInt32(data[offset]) | UInt32(data[offset + 1]) << 8 |
               UInt32(data[offset + 2]) << 16 | UInt32(data[offset + 3]) << 24
    }
    func slice(_ offset: Int, _ length: Int) throws -> Data {
        data.subdata(in: try checked(offset, length))
    }
    func tag(_ offset: Int) throws -> String {
        let values = try slice(offset, 4)
        guard let text = String(data: values, encoding: .ascii) else {
            throw OracleError.invalid("non_ascii_sfnt_table_tag")
        }
        return text
    }
    func fixed(_ offset: Int) throws -> Double {
        Double(Int32(bitPattern: try u32(offset))) / 65536.0
    }
}

struct TableSlice {
    let offset: Int
    let length: Int
    let digest: String
}

struct Axis {
    let tag: String
    let identifier: UInt32
    let minimum: Double
    let defaultValue: Double
    let maximum: Double
    let flags: UInt16
    var json: [String: Any] {
        ["tag": tag, "identifier": identifier, "minimum": minimum,
         "default": defaultValue, "maximum": maximum, "flags": flags,
         "hidden": flags & 1 != 0]
    }
}

struct RawFace {
    let index: Int
    let tables: [String: TableSlice]
    let upm: UInt16
    let glyphCount: UInt16
    let axes: [Axis]
}

func parseFaces(_ bytes: Bytes) throws -> [RawFace] {
    let offsets: [Int]
    if try bytes.tag(0) == "ttcf" {
        let count = Int(try bytes.u32(8))
        guard count > 0, count <= 4096 else { throw OracleError.invalid("invalid_ttc_face_count") }
        _ = try bytes.checked(12, count * 4)
        offsets = try (0 ..< count).map { Int(try bytes.u32(12 + $0 * 4)) }
    } else {
        offsets = [0]
    }
    var cachedHashes: [String: String] = [:]
    return try offsets.enumerated().map { index, offset in
        let tableCount = Int(try bytes.u16(offset + 4))
        guard tableCount > 0, tableCount <= 4096 else { throw OracleError.invalid("invalid_sfnt_table_count") }
        _ = try bytes.checked(offset + 12, tableCount * 16)
        var tables: [String: TableSlice] = [:]
        for item in 0 ..< tableCount {
            let position = offset + 12 + item * 16
            let tag = try bytes.tag(position)
            let tableOffset = Int(try bytes.u32(position + 8))
            let length = Int(try bytes.u32(position + 12))
            _ = try bytes.checked(tableOffset, length)
            guard tables[tag] == nil else { throw OracleError.invalid("duplicate_sfnt_table_tag") }
            let key = "\(tableOffset):\(length)"
            let value: String
            if let cached = cachedHashes[key] { value = cached }
            else { value = sha256(try bytes.slice(tableOffset, length)) }
            cachedHashes[key] = value
            tables[tag] = TableSlice(offset: tableOffset, length: length, digest: value)
        }
        guard let head = tables["head"], let maxp = tables["maxp"], head.length >= 54, maxp.length >= 6 else {
            throw OracleError.invalid("missing_or_truncated_head_maxp")
        }
        let upm = try bytes.u16(head.offset + 18)
        let glyphCount = try bytes.u16(maxp.offset + 4)
        guard upm > 0, glyphCount > 0 else { throw OracleError.invalid("invalid_upm_or_glyph_count") }
        var axes: [Axis] = []
        if let fvar = tables["fvar"] {
            guard fvar.length >= 16 else { throw OracleError.invalid("fvar_header_truncated") }
            let dataOffset = Int(try bytes.u16(fvar.offset + 4))
            let axisCount = Int(try bytes.u16(fvar.offset + 8))
            let axisSize = Int(try bytes.u16(fvar.offset + 10))
            guard axisCount <= 256, axisSize >= 20, dataOffset + axisCount * axisSize <= fvar.length else {
                throw OracleError.invalid("fvar_axis_records_invalid")
            }
            for axisIndex in 0 ..< axisCount {
                let position = fvar.offset + dataOffset + axisIndex * axisSize
                let axis = Axis(tag: try bytes.tag(position), identifier: try bytes.u32(position),
                                minimum: try bytes.fixed(position + 4), defaultValue: try bytes.fixed(position + 8),
                                maximum: try bytes.fixed(position + 12), flags: try bytes.u16(position + 16))
                guard axis.minimum <= axis.defaultValue, axis.defaultValue <= axis.maximum,
                      !axes.contains(where: { $0.tag == axis.tag }) else {
                    throw OracleError.invalid("fvar_axis_range_or_tag_invalid")
                }
                axes.append(axis)
            }
        }
        return RawFace(index: index, tables: tables, upm: upm, glyphCount: glyphCount, axes: axes)
    }
}

func tagIdentifier(_ tag: String) -> UInt32 {
    tag.utf8.reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
}

func tagString(_ value: UInt32) -> String {
    String(bytes: [UInt8((value >> 24) & 255), UInt8((value >> 16) & 255),
                   UInt8((value >> 8) & 255), UInt8(value & 255)], encoding: .ascii) ?? "?"
}

func copiedTable(_ font: CTFont, _ tag: String) -> Data? {
    // The current macOS SDK explicitly marks excludeSynthetic unavailable
    // ("Unsupported"). Use supported default options; verifyIdentity still
    // requires exact byte length and SHA-256 equality with every source table.
    CTFontCopyTable(font, CTFontTableTag(tagIdentifier(tag)), CTFontTableOptions(rawValue: 0)) as Data?
}

func verifyIdentity(_ font: CTFont, _ face: RawFace, allTables: Bool) throws -> [String: String] {
    guard CTFontGetUnitsPerEm(font) == UInt32(face.upm), CTFontGetGlyphCount(font) == Int(face.glyphCount) else {
        throw OracleError.invalid("coretext_face_upm_or_glyph_count_mismatch")
    }
    let tags = allTables ? face.tables.keys.sorted() : ["name", "head", "maxp", "cmap", "fvar", "avar"].filter { face.tables[$0] != nil }
    var hashes: [String: String] = [:]
    for tag in tags {
        guard let source = face.tables[tag], let actual = copiedTable(font, tag) else {
            throw OracleError.invalid("coretext_missing_original_table:\(tag)")
        }
        let hash = sha256(actual)
        guard actual.count == source.length, hash == source.digest else {
            throw OracleError.invalid("coretext_table_identity_mismatch:\(tag)")
        }
        hashes[tag] = hash
    }
    return hashes
}

struct FaceState {
    let raw: RawFace
    var baseFont: CTFont?
    var metadata: [String: Any]
}

func coreTextAxes(_ font: CTFont) -> [[String: Any]] {
    guard let axes = CTFontCopyVariationAxes(font) as? [NSDictionary] else { return [] }
    return axes.map { dictionary in
        let identifier = (dictionary[kCTFontVariationAxisIdentifierKey] as? NSNumber)?.uint32Value ?? 0
        return ["tag": tagString(identifier), "identifier": identifier,
                "minimum": dictionary[kCTFontVariationAxisMinimumValueKey] ?? NSNull(),
                "default": dictionary[kCTFontVariationAxisDefaultValueKey] ?? NSNull(),
                "maximum": dictionary[kCTFontVariationAxisMaximumValueKey] ?? NSNull(),
                "name": dictionary[kCTFontVariationAxisNameKey] as? String ?? ""]
    }
}

func locateDescriptors(_ rawFaces: [RawFace], url: URL) throws -> [FaceState] {
    var states = rawFaces.map { face in
        FaceState(raw: face, baseFont: nil,
                  metadata: ["face_index": face.index, "upm": face.upm,
                             "glyph_count": face.glyphCount, "axes": face.axes.map(\.json),
                             "status": "unavailable", "error": "no_identical_coretext_descriptor"])
    }
    guard let descriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor] else {
        return states
    }
    for (descriptorIndex, descriptor) in descriptors.enumerated() {
        var matrix = CGAffineTransform.identity
        let probe = CTFontCreateWithFontDescriptor(descriptor, 0, &matrix)
        guard let nameData = copiedTable(probe, "name") else { continue }
        let nameHash = sha256(nameData)
        let candidates = rawFaces.filter { $0.tables["name"]?.digest == nameHash }
        for raw in candidates {
            do {
                let hashes = try verifyIdentity(probe, raw, allTables: true)
                guard states[raw.index].baseFont == nil else {
                    // Multiple descriptors may expose the same exact source face; keep the first.
                    continue
                }
                var metadata = states[raw.index].metadata
                metadata["status"] = "identity_verified"
                metadata["error"] = NSNull()
                metadata["descriptor_index"] = descriptorIndex
                metadata["name"] = CTFontCopyPostScriptName(probe) as String
                metadata["family"] = CTFontCopyFamilyName(probe) as String
                metadata["coretext_axes"] = coreTextAxes(probe)
                metadata["verified_table_sha256"] = hashes
                metadata["source_url_reported_by_coretext"] = (CTFontCopyAttribute(probe, kCTFontURLAttribute) as? URL)?.path ?? ""
                metadata["identity_probe_size"] = Double(CTFontGetSize(probe))
                metadata["output_font_size"] = raw.upm
                states[raw.index] = FaceState(raw: raw, baseFont: probe, metadata: metadata)
            } catch {
                stderr("descriptor \(descriptorIndex), raw face \(raw.index): \(error)")
                states[raw.index].metadata["last_identity_error"] = String(describing: error)
            }
        }
    }
    return states
}

struct Request: Decodable {
    let request_id: String
    let face_index: Int
    let location: [String: Double]
    let glyph_ids: [Int]
}

// Construction and acceptance are distinct. The explicit observation protocol
// below may expose this result only to an independent per-request verifier.
// The ordinary extraction path continues through makeInstance's strict guard.
func constructInstance(_ state: FaceState, _ requested: [String: Double]) throws -> (CTFont, [String: Double], [String: Double]) {
    guard let baseFont = state.baseFont else {
        throw OracleError.invalid("requested_face_has_no_verified_coretext_descriptor")
    }
    let raw = state.raw
    let axisTags = Set(raw.axes.map(\.tag))
    guard requested.keys.allSatisfy({ axisTags.contains($0) }) else {
        throw OracleError.invalid("unknown_axis_tag")
    }
    var location: [String: Double] = [:]
    var variations: [NSNumber: NSNumber] = [:]
    for axis in raw.axes {
        let value = requested[axis.tag] ?? axis.defaultValue
        guard value.isFinite, value >= axis.minimum, value <= axis.maximum else {
            throw OracleError.invalid("axis_value_out_of_source_range:\(axis.tag)")
        }
        location[axis.tag] = value
        variations[NSNumber(value: axis.identifier)] = NSNumber(value: value)
    }
    // CoreText may apply 'trak' even through its ideal-advance API. Skia uses this
    // undocumented descriptor attribute to disable it. We record the choice and
    // test it with a synthetic font having deliberately nonzero tracking.
    // Reference: SkCTFontCreateExactCopy.cpp, Skia commit d2b9e48baf1697760afc1dc8ea3ad40110b8cacc.
    var attributes: [String: Any] = [kCTFontVariationAttribute as String: variations,
                                     "NSCTFontUnscaledTrackingAttribute": NSNumber(value: 0)]
    // Preserve optical selection when increasing the point size to UPEM. Creating
    // a fresh font from its family at a large size can select a different UI face.
    let baseOpticalSize = (CTFontCopyAttribute(baseFont, kCTFontOpticalSizeAttribute) as? NSNumber)?.doubleValue
    let opticalSize = location["opsz"] ?? ((baseOpticalSize ?? 0) > 0 ? baseOpticalSize! : Double(CTFontGetSize(baseFont)))
    attributes[kCTFontOpticalSizeAttribute as String] = NSNumber(value: opticalSize)
    let varied = CTFontDescriptorCreateWithAttributes(attributes as CFDictionary)
    var matrix = CGAffineTransform.identity
    let font = CTFontCreateCopyWithAttributes(baseFont, CGFloat(raw.upm), &matrix, varied)
    _ = try verifyIdentity(font, raw, allTables: false)
    guard abs(Double(CTFontGetSize(font)) - Double(raw.upm)) < 1e-9 else {
        throw OracleError.invalid("coretext_font_size_mismatch")
    }
    let actualMatrix = CTFontGetMatrix(font)
    guard actualMatrix.isIdentity else { throw OracleError.invalid("coretext_non_identity_font_matrix") }
    var reported: [String: Double] = [:]
    if let dictionary = CTFontCopyVariation(font) as? [NSNumber: NSNumber] {
        for (key, value) in dictionary { reported[tagString(key.uint32Value)] = value.doubleValue }
    }
    return (font, location, reported)
}

func validateReportedAxes(_ axes: [Axis], _ location: [String: Double], _ reported: [String: Double]) throws {
    for axis in axes {
        // A default omitted by CoreText is allowed; a nondefault that is not reported fails.
        let effective = reported[axis.tag] ?? axis.defaultValue
        guard let expected = location[axis.tag],
              (reported[axis.tag] != nil || expected == axis.defaultValue),
              abs(effective - expected) <= 1e-6 else {
            throw OracleError.invalid("coretext_did_not_report_requested_axis_value:\(axis.tag)")
        }
    }
}

func makeInstance(_ state: FaceState, _ requested: [String: Double]) throws -> (CTFont, [String: Double], [String: Double]) {
    let (font, location, reported) = try constructInstance(state, requested)
    try validateReportedAxes(state.raw.axes, location, reported)
    return (font, location, reported)
}

func sourceProvesEmpty(_ face: RawFace, _ glyph: Int, _ bytes: Bytes) throws -> Bool {
    if let loca = face.tables["loca"], let head = face.tables["head"], let glyf = face.tables["glyf"] {
        let format = try bytes.u16(head.offset + 50)
        let start: Int
        let end: Int
        if format == 0 {
            guard (glyph + 2) * 2 <= loca.length else { throw OracleError.invalid("short_loca_truncated") }
            start = Int(try bytes.u16(loca.offset + glyph * 2)) * 2
            end = Int(try bytes.u16(loca.offset + (glyph + 1) * 2)) * 2
        } else if format == 1 {
            guard (glyph + 2) * 4 <= loca.length else { throw OracleError.invalid("long_loca_truncated") }
            start = Int(try bytes.u32(loca.offset + glyph * 4))
            end = Int(try bytes.u32(loca.offset + (glyph + 1) * 4))
        } else { throw OracleError.invalid("loca_format_invalid") }
        guard start <= end, end <= glyf.length else { throw OracleError.invalid("glyf_loca_range_invalid") }
        if start == end { return true }
        if end - start < 10 { return false }
        return try bytes.u16(glyf.offset + start) == 0
    }
    guard let hvgl = face.tables["hvgl"], face.tables["hvpm"] == nil else { return false }
    guard try bytes.le16(hvgl.offset) == 3, try bytes.le16(hvgl.offset + 2) == 1 else { return false }
    let count = Int(try bytes.le32(hvgl.offset + 8))
    let indexOffset = Int(try bytes.le32(hvgl.offset + 12))
    guard glyph < Int(try bytes.le32(hvgl.offset + 16)), indexOffset + (count + 1) * 4 <= hvgl.length else {
        throw OracleError.invalid("hvgl_index_invalid_for_empty_check")
    }
    var active = Set<Int>()
    var memo: [Int: Bool] = [:]
    func visit(_ part: Int, depth: Int) throws -> Bool {
        if let cached = memo[part] { return cached }
        guard part >= 0, part < count, depth <= 256, !active.contains(part) else {
            throw OracleError.invalid("hvgl_invalid_or_cyclic_tree_in_empty_check")
        }
        active.insert(part)
        defer { active.remove(part) }
        let start = indexOffset + Int(try bytes.le32(hvgl.offset + indexOffset + part * 4))
        let end = indexOffset + Int(try bytes.le32(hvgl.offset + indexOffset + (part + 1) * 4))
        guard start >= indexOffset + (count + 1) * 4, end >= start + 8, end <= hvgl.length else {
            throw OracleError.invalid("hvgl_part_range_invalid_in_empty_check")
        }
        let position = hvgl.offset + start
        let flags = try bytes.le16(position)
        if flags & 1 == 0 {
            let paths = Int(try bytes.le16(position + 4))
            guard start + 8 + paths * 2 <= end else { throw OracleError.invalid("hvgl_shape_path_count_invalid") }
            let empty = try (0 ..< paths).allSatisfy { try bytes.le16(position + 8 + $0 * 2) < 3 }
            memo[part] = empty
            return empty
        }
        guard end - start >= 36 else { throw OracleError.invalid("hvgl_composite_header_truncated") }
        let subparts = Int(try bytes.le16(position + 4))
        let subpartOffset = Int(try bytes.le16(position + 24)) * 4
        guard subpartOffset >= 36, start + subpartOffset + subparts * 8 <= end else {
            throw OracleError.invalid("hvgl_subpart_array_invalid")
        }
        for child in 0 ..< subparts {
            let childPart = Int(try bytes.le32(position + subpartOffset + child * 8))
            if try !visit(childPart, depth: depth + 1) { memo[part] = false; return false }
        }
        memo[part] = true
        return true
    }
    return try visit(glyph, depth: 0)
}

func pathCommands(_ path: CGPath) throws -> [[Any]] {
    var commands: [[Any]] = []
    var error: String?
    path.applyWithBlock { pointer in
        guard error == nil else { return }
        let element = pointer.pointee
        var command: [Any]
        let count: Int
        switch element.type {
        case .moveToPoint: command = ["moveTo"]; count = 1
        case .addLineToPoint: command = ["lineTo"]; count = 1
        case .addQuadCurveToPoint: command = ["qCurveTo"]; count = 2
        case .addCurveToPoint: command = ["curveTo"]; count = 3
        case .closeSubpath: command = ["closePath"]; count = 0
        @unknown default: error = "unknown_coregraphics_path_element"; return
        }
        for index in 0 ..< count {
            let point = element.points[index]
            guard point.x.isFinite, point.y.isFinite else { error = "non_finite_path_coordinate"; return }
            command.append(Double(point.x)); command.append(Double(point.y))
        }
        commands.append(command)
        if commands.count > 1_000_000 { error = "glyph_path_command_limit_exceeded" }
    }
    if let error { throw OracleError.invalid(error) }
    return commands
}

func extractGlyph(_ request: Request, _ glyphID: Int, _ state: FaceState,
                  _ font: CTFont, _ location: [String: Double], _ reported: [String: Double], _ bytes: Bytes) throws -> [String: Any] {
    guard glyphID >= 0, glyphID < Int(state.raw.glyphCount) else { throw OracleError.invalid("glyph_id_out_of_range") }
    var glyph = CGGlyph(glyphID)
    var horizontal = CGSize.zero
    var vertical = CGSize.zero
    var verticalTranslation = CGSize.zero
    let horizontalSum = CTFontGetAdvancesForGlyphs(font, .horizontal, &glyph, &horizontal, 1)
    let verticalSum = CTFontGetAdvancesForGlyphs(font, .vertical, &glyph, &vertical, 1)
    CTFontGetVerticalTranslationsForGlyphs(font, &glyph, &verticalTranslation, 1)
    let values = [Double(horizontal.width), Double(horizontal.height), Double(vertical.width), Double(vertical.height),
                  Double(verticalTranslation.width), Double(verticalTranslation.height), horizontalSum, verticalSum]
    guard values.allSatisfy(\.isFinite) else { throw OracleError.invalid("non_finite_coretext_metrics") }
    let commands: [[Any]]
    let bounds: [Double]
    let pathStatus: String
    if let path = CTFontCreatePathForGlyph(font, glyph, nil) {
        commands = try pathCommands(path)
        let rect = path.boundingBoxOfPath
        if path.isEmpty {
            bounds = [0, 0, 0, 0]; pathStatus = "empty_path"
        } else {
            bounds = [Double(rect.origin.x), Double(rect.origin.y), Double(rect.width), Double(rect.height)]
            guard bounds.allSatisfy(\.isFinite) else { throw OracleError.invalid("non_finite_path_bounds") }
            pathStatus = "path"
        }
    } else if try sourceProvesEmpty(state.raw, glyphID, bytes) {
        commands = []; bounds = [0, 0, 0, 0]; pathStatus = "nil_path_but_source_proves_empty"
    } else {
        throw OracleError.invalid("coretext_returned_nil_path_without_source_empty_proof")
    }
    return ["request_id": request.request_id, "face_index": request.face_index, "glyph_id": glyphID,
            "location": location, "reported_location": reported, "commands": commands,
            // CoreText's vertical advance is pre-rotated into CGSize.width.
            // HarfBuzz's CoreText backend uses width and negates the origin vector.
            "advance_width": Double(horizontal.width), "advance_height": Double(vertical.width),
            "lsb": bounds[0], "lsb_derivation": "effective_geometric_bearing_from_path_min_x_at_original_horizontal_origin",
            "horizontal_origin_x": 0.0, "horizontal_origin_y": 0.0,
            "vertical_origin_x": -Double(verticalTranslation.width),
            "vertical_origin_y": -Double(verticalTranslation.height),
            "vertical_origin_derivation": "negative_CTFontGetVerticalTranslationsForGlyphs_raw_vector_in_y_up_font_units",
            "horizontal_advance_vector": [Double(horizontal.width), Double(horizontal.height)],
            "vertical_advance_vector": [Double(vertical.width), Double(vertical.height)],
            "vertical_origin_translation": [Double(verticalTranslation.width), Double(verticalTranslation.height)],
            "horizontal_advance_sum": horizontalSum, "vertical_advance_sum": verticalSum,
            "bounds": bounds, "path_status": pathStatus, "error": NSNull()]
}

final class JSONLines {
    private var buffer = Data()
    private var ended = false
    let maximumLength = 1_048_576
    func next() throws -> Data? {
        while true {
            if let newline = buffer.firstIndex(of: 10) {
                guard newline <= maximumLength else { throw OracleError.invalid("request_line_limit_exceeded") }
                let line = Data(buffer.prefix(upTo: newline))
                buffer.removeSubrange(buffer.startIndex ... newline)
                return line
            }
            guard buffer.count <= maximumLength else { throw OracleError.invalid("request_line_limit_exceeded") }
            if ended {
                if buffer.isEmpty { return nil }
                let result = buffer; buffer.removeAll(); return result
            }
            // A request/response pipe must return after one available chunk.
            // Foundation's read(upToCount:) can wait to fill its requested size,
            // deadlocking a caller waiting for this request's response before
            // sending the next request. POSIX read permits short pipe reads.
            var chunk = [UInt8](repeating: 0, count: 65_536)
            let count = chunk.withUnsafeMutableBytes { pointer in
                read(FileHandle.standardInput.fileDescriptor, pointer.baseAddress, pointer.count)
            }
            if count < 0 {
                if errno == EINTR { continue }
                throw OracleError.invalid("stdin_read_failed_errno:\(errno)")
            }
            ended = count == 0
            if count > 0 { buffer.append(contentsOf: chunk.prefix(count)) }
        }
    }
}

func run() throws {
    let observationsOnly = CommandLine.arguments.count == 3 && CommandLine.arguments[2] == "--axis-observations"
    guard CommandLine.arguments.count == 2 || observationsOnly else {
        throw OracleError.invalid("usage: coretext_extract /path/font.ttc [--axis-observations] < requests.jsonl > private_oracle.jsonl")
    }
    let url = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL.resolvingSymlinksInPath()
    let data = try Data(contentsOf: url, options: [.mappedIfSafe])
    let bytes = Bytes(data: data)
    let rawFaces = try parseFaces(bytes)
    let states = try locateDescriptors(rawFaces, url: url)
    try emit(["type": "metadata", "schema_version": 1, "backend": "CoreText",
              "axis_observations_only": observationsOnly,
              "axis_observation_acceptance": observationsOnly ? "NOT_ACCEPTED_requires_independent_per_request_verification" : "strict_reported_coordinate_check",
              "source_sha256": sha256(data), "source_byte_size": data.count,
              "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
              "source_path": url.path, "face_index_basis": "raw_TTC_directory_order_verified_by_original_table_hashes",
              "coordinates": "source_font_units_with_original_horizontal_origin_and_y_up",
              "metrics_policy": "CTFontGetAdvancesForGlyphs with NSCTFontUnscaledTrackingAttribute=0; no CTLine/CTRun or optical bounds layout; vertical advance taken from raw vector width",
              "tracking_attribute": ["name": "NSCTFontUnscaledTrackingAttribute", "value": 0,
                                     "documented_public_api": false, "validation_required": "synthetic nonzero-trak fixture and native original metric checks"],
              "axis_policy": "all source fvar user axes set explicitly; effective reported coordinates checked; no manual avar interpretation",
              "registration_policy": "unregistered file descriptors; no system font installation",
              "path_policy": "quadratic_and_cubic_commands_preserved; nil_path_requires_structural_empty_proof",
              "faces": states.map(\.metadata)])
    let reader = JSONLines()
    let decoder = JSONDecoder()
    var requestCount = 0
    var glyphCount = 0
    var errorCount = 0
    while let line = try reader.next() {
        if line.isEmpty { continue }
        var decodedRequest: Request?
        do {
            let request = try decoder.decode(Request.self, from: line)
            decodedRequest = request
            guard !request.request_id.isEmpty, request.request_id.utf8.count <= 1024,
                  request.face_index >= 0, request.face_index < states.count,
                  !request.glyph_ids.isEmpty, request.glyph_ids.count <= 4096 else {
                throw OracleError.invalid("request_id_face_or_glyph_batch_invalid")
            }
            requestCount += 1
            let state = states[request.face_index]
            let (font, location, reported) = try (observationsOnly
                ? constructInstance(state, request.location) : makeInstance(state, request.location))
            for glyph in request.glyph_ids {
                do {
                    let result = try autoreleasepool { try extractGlyph(request, glyph, state, font, location, reported, bytes) }
                    try emit(result)
                    glyphCount += 1
                } catch {
                    errorCount += 1
                    try emit(["request_id": request.request_id, "face_index": request.face_index,
                              "glyph_id": glyph, "location": location, "commands": NSNull(),
                              "error": String(describing: error)])
                }
            }
        } catch {
            errorCount += 1
            var response: [String: Any] = ["type": "request_error", "error": String(describing: error)]
            if let request = decodedRequest {
                response["request_id"] = request.request_id; response["face_index"] = request.face_index
            }
            try emit(response)
        }
    }
    try emit(["type": "summary", "request_count": requestCount, "successful_glyph_count": glyphCount,
              "error_count": errorCount, "source_sha256": sha256(data)])
    if errorCount > 0 { exit(3) }
}

do {
    try run()
} catch {
    stderr("CoreText oracle failed: \(error)")
    try? emit(["type": "fatal_error", "error": String(describing: error)])
    exit(2)
}
