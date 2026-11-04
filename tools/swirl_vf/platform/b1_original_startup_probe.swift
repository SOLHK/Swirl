// SPDX-License-Identifier: MIT
// Independent B1 startup diagnosis; never an extraction or acceptance oracle.
// Build on macOS: xcrun swiftc -O b1_original_startup_probe.swift -o b1_original_startup_probe
// Usage: b1_original_startup_probe /absolute/private/source.ttc > startup.json
// No registration, glyph request, outline, metric, font payload, or path output.
// Startup call order matches coretext_extract.swift: URL descriptors, then size 0
// and an identity matrix. Descriptor indices are never physical face indices.
// API/design references reviewed before this independent implementation:
// https://github.com/harfbuzz/harfbuzz/blob/11.5.0/src/hb-coretext.cc
// https://developer.apple.com/documentation/coretext/ctfontcreatewithfontdescriptor(_:_:_:)
// That creation API always returns a best match. Non-nil is not source identity.

import Foundation
import CoreFoundation
import CoreText
import CoreGraphics
import CryptoKit
import Darwin

enum StartupError: Error {
    case invalid(String)
}

func errorCode(_ error: Error) -> String {
    if let startup = error as? StartupError {
        switch startup { case .invalid(let code): return code }
    }
    return "unexpected_internal_error"
}

func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

// Preserve native binary64 startup metadata without NSNumber decimal transport.
private enum ExactJSON: Encodable {
    case null, boolean(Bool), integer(Int64), unsignedInteger(UInt64)
    case number(Double), string(String), array([ExactJSON]), object([String: ExactJSON])

    init(_ value: Any) throws {
        if value is NSNull { self = .null }
        else if let text = value as? String { self = .string(text) }
        else if type(of: value) == Double.self {
            let number = value as! Double
            guard number.isFinite else { throw StartupError.invalid("nonfinite_json_number") }
            self = .number(number)
        } else if let number = value as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() { self = .boolean(number.boolValue) }
            else {
                switch String(cString: number.objCType) {
                case "f", "d":
                    guard number.doubleValue.isFinite else { throw StartupError.invalid("nonfinite_json_number") }
                    self = .number(number.doubleValue)
                case "Q": self = .unsignedInteger(number.uint64Value)
                default: self = .integer(number.int64Value)
                }
            }
        } else if let object = value as? [String: Any] {
            self = .object(try object.mapValues { try ExactJSON($0) })
        } else if let array = value as? [Any] {
            self = .array(try array.map { try ExactJSON($0) })
        } else { throw StartupError.invalid("unsupported_json_value") }
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

struct Bytes {
    let data: Data

    func checked(_ offset: Int, _ length: Int) throws -> Range<Int> {
        guard offset >= 0, length >= 0, offset <= data.count, length <= data.count-offset else {
            throw StartupError.invalid("font_byte_range_out_of_bounds")
        }
        return offset..<(offset+length)
    }

    func u16(_ offset: Int) throws -> UInt16 {
        _ = try checked(offset, 2)
        return UInt16(data[offset]) << 8 | UInt16(data[offset+1])
    }

    func u32(_ offset: Int) throws -> UInt32 {
        _ = try checked(offset, 4)
        return UInt32(data[offset]) << 24 | UInt32(data[offset+1]) << 16 |
               UInt32(data[offset+2]) << 8 | UInt32(data[offset+3])
    }

    func slice(_ offset: Int, _ length: Int) throws -> Data {
        data.subdata(in: try checked(offset, length))
    }

    func tag(_ offset: Int) throws -> String {
        guard let tag = String(data: try slice(offset, 4), encoding: .ascii),
              tag.utf8.allSatisfy({ $0 >= 32 && $0 <= 126 }) else {
            throw StartupError.invalid("invalid_sfnt_table_tag")
        }
        return tag
    }
}

struct SourceTable {
    let offset: Int
    let length: Int
    let digest: String

    func json(_ tag: String) -> [String: Any] {
        ["tag": tag, "length": length, "sha256": digest]
    }
}

struct RawFace {
    let index: Int
    let tables: [String: SourceTable]
    let upem: UInt16
    let glyphCount: UInt16
}

func faceOffsets(_ bytes: Bytes) throws -> [Int] {
    if try bytes.u32(0) == 0x74746366 { // ttcf; offsets are absolute within TTC.
        let count = Int(try bytes.u32(8))
        guard count > 0, count <= 4096 else { throw StartupError.invalid("invalid_ttc_face_count") }
        _ = try bytes.checked(12, count*4)
        return try (0..<count).map { Int(try bytes.u32(12+$0*4)) }
    }
    return [0]
}

func parseFace(_ bytes: Bytes, _ index: Int, _ offset: Int,
               _ hashes: inout [String: String]) throws -> RawFace {
    let signature = try bytes.u32(offset)
    guard [UInt32(0x00010000), 0x4f54544f, 0x74727565, 0x74797031].contains(signature) else {
        throw StartupError.invalid("invalid_sfnt_signature")
    }
    let count = Int(try bytes.u16(offset+4))
    guard count > 0, count <= 4096 else { throw StartupError.invalid("invalid_sfnt_table_count") }
    _ = try bytes.checked(offset+12, count*16)
    var tables: [String: SourceTable] = [:]
    for item in 0..<count {
        let record = offset+12+item*16
        let tag = try bytes.tag(record)
        let tableOffset = Int(try bytes.u32(record+8))
        let length = Int(try bytes.u32(record+12))
        _ = try bytes.checked(tableOffset, length)
        guard tables[tag] == nil else { throw StartupError.invalid("duplicate_sfnt_table_tag") }
        let key = "\(tableOffset):\(length)"
        let digest: String
        if let cached = hashes[key] { digest = cached }
        else {
            digest = sha256(try bytes.slice(tableOffset, length))
            hashes[key] = digest
        }
        tables[tag] = SourceTable(offset: tableOffset, length: length, digest: digest)
    }
    guard let head = tables["head"], let maxp = tables["maxp"], head.length >= 54, maxp.length >= 6 else {
        throw StartupError.invalid("missing_or_truncated_head_maxp")
    }
    let upem = try bytes.u16(head.offset+18)
    let glyphCount = try bytes.u16(maxp.offset+4)
    guard upem > 0, glyphCount > 0 else { throw StartupError.invalid("invalid_upem_or_glyph_count") }
    return RawFace(index: index, tables: tables, upem: upem, glyphCount: glyphCount)
}

func tagID(_ tag: String) -> UInt32 {
    tag.utf8.reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
}

struct TableObservation {
    let present: Bool
    let length: Int?
    let digest: String?

    var json: [String: Any] {
        ["present": present, "length": length.map { $0 as Any } ?? NSNull(),
         "sha256": digest.map { $0 as Any } ?? NSNull(),
         "status": !present ? "API_NIL" : (length == 0 ? "PRESENT_EMPTY" : "PRESENT")]
    }
}

func copyTable(_ font: CTFont, _ tag: String) -> TableObservation {
    // excludeSynthetic is unsupported on current SDKs. Options 0 never excuses
    // a missing/different table: the explicit length/hash comparison is strict.
    guard let data = CTFontCopyTable(font, CTFontTableTag(tagID(tag)),
                                   CTFontTableOptions(rawValue: 0)) as Data? else {
        return TableObservation(present: false, length: nil, digest: nil)
    }
    return TableObservation(present: true, length: data.count, digest: sha256(data))
}

func compare(_ expected: SourceTable, _ actual: TableObservation, _ tag: String) -> [String: Any] {
    let lengthEqual = actual.present && actual.length == expected.length
    let digestEqual = actual.present && actual.digest == expected.digest
    let status: String
    if !actual.present { status = "SOURCE_TABLE_API_NIL" }
    else if !lengthEqual && !digestEqual { status = "SOURCE_TABLE_LENGTH_AND_SHA256_MISMATCH" }
    else if !lengthEqual { status = "SOURCE_TABLE_LENGTH_MISMATCH" }
    else if !digestEqual { status = "SOURCE_TABLE_SHA256_MISMATCH" }
    else { status = "EXACT" }
    return ["tag": tag, "expected_length": expected.length, "expected_sha256": expected.digest,
            "actual_present": actual.present, "actual_length": actual.length.map { $0 as Any } ?? NSNull(),
            "actual_sha256": actual.digest.map { $0 as Any } ?? NSNull(),
            "length_equal": lengthEqual, "sha256_equal": digestEqual,
            "exact": lengthEqual && digestEqual, "status": status]
}

func canonicalURL(_ url: URL) -> URL {
    url.standardizedFileURL.resolvingSymlinksInPath()
}

func urlEvidence(_ attribute: Any?, _ source: URL) -> (present: Bool, matches: Bool, status: String) {
    guard let attribute = attribute else { return (false, false, "ATTRIBUTE_MISSING") }
    guard let url = attribute as? URL else { return (true, false, "ATTRIBUTE_NOT_URL") }
    return (true, canonicalURL(url) == canonicalURL(source), "URL_PRESENT")
}

func binary64Hex(_ value: Double) -> String { String(format: "%016llx", value.bitPattern) }
func finiteJSON(_ value: Double) -> Any { value.isFinite ? value as Any : NSNull() }

func emptyReport() -> [String: Any] {
    ["schema": "swirl-vf-b1-original-startup-v1",
     "status": "DIAGNOSTIC_PARTIAL_NOT_ACCEPTANCE",
     "backend": "CoreText_B1_original_startup_only",
     "scope": "startup_table_identity_only_no_glyph_or_metric_equivalence",
     "source": ["sha256": NSNull(), "size": NSNull(), "sha256_after": NSNull(),
                "size_after": NSNull(), "unchanged": false] as [String: Any],
     "raw_face_count": 0,
     "descriptor_api": ["status": "NOT_CALLED", "count": 0] as [String: Any],
     "descriptors": [[String: Any]](), "faces": [[String: Any]](),
     "summary": ["parsed_face_count": 0, "identity_verified_face_count": 0,
                 "unbound_face_count": 0, "ambiguous_face_count": 0,
                 "descriptor_count": 0, "metrics_observed": 0,
                 "all_faces_identity_verified": false] as [String: Any],
     "error_codes": [String](),
     "startup_semantics": ["font_registration_called": false, "requested_font_size": 0,
                           "requested_identity_matrix": true,
                           "ctfont_creation_returns_nonoptional_best_match": true,
                           "table_options_raw_value": 0] as [String: Any]]
}

func diagnose() -> [String: Any] {
    var report = emptyReport()
    guard CommandLine.arguments.count == 2, CommandLine.arguments[1].hasPrefix("/") else {
        report["error_codes"] = ["argument_requires_one_absolute_source_path"]
        return report
    }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data: Data
    do { data = try Data(contentsOf: url) }
    catch {
        report["error_codes"] = ["source_read_failed"]
        return report
    }
    let sourceHash = sha256(data)
    var source: [String: Any] = ["sha256": sourceHash, "size": data.count,
                                 "sha256_after": NSNull(), "size_after": NSNull(), "unchanged": false]
    let bytes = Bytes(data: data)
    var codes = Set<String>()
    var offsets: [Int] = []
    do { offsets = try faceOffsets(bytes) }
    catch { codes.insert(errorCode(error)) }
    report["raw_face_count"] = offsets.count
    var faces: [RawFace] = []
    var faceRows: [[String: Any]] = []
    var cachedSourceHashes: [String: String] = [:]
    for (index, offset) in offsets.enumerated() {
        var row: [String: Any] = ["face_index": index, "parse_status": "FAILED",
                                  "expected_source_sha256": sourceHash, "expected_source_size": data.count,
                                  "expected_tables": [[String: Any]](), "parse_error_code": NSNull(),
                                  "name_candidate_descriptor_indices": [Int](),
                                  "exact_descriptor_indices": [Int](),
                                  "unambiguous_descriptor_indices": [Int](),
                                  "binding_status": "SOURCE_FACE_PARSE_FAILED"]
        do {
            let face = try parseFace(bytes, index, offset, &cachedSourceHashes)
            faces.append(face)
            row["parse_status"] = "PARSED"
            row["expected_upem"] = Int(face.upem)
            row["expected_glyph_count"] = Int(face.glyphCount)
            row["expected_tables"] = face.tables.keys.sorted().map { face.tables[$0]!.json($0) }
            row["source_directory_has_vorg"] = face.tables["VORG"] != nil
            row["binding_status"] = "NO_EXACT_DESCRIPTOR"
        } catch {
            let code = errorCode(error)
            row["parse_error_code"] = code
            codes.insert(code)
        }
        faceRows.append(row)
    }

    var descriptorRows: [[String: Any]] = []
    var exactDescriptors: [Int: [Int]] = [:]
    var unambiguousDescriptors: [Int: [Int]] = [:]
    var nameDescriptors: [Int: [Int]] = [:]
    // Each source table is copied once per descriptor, even for shared TTC data.
    // Always include VORG: absent directory membership is not proof of API nil.
    let requestedTags = Set(faces.flatMap { Array($0.tables.keys) }).union(["name", "VORG"]).sorted()
    if let array = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) {
        let count = CFArrayGetCount(array)
        if let descriptors = array as? [CTFontDescriptor] {
            report["descriptor_api"] = ["status": descriptors.isEmpty ? "EMPTY" : "NON_NIL", "count": count] as [String: Any]
            if descriptors.isEmpty { codes.insert("descriptor_api_returned_empty_array") }
            for (descriptorIndex, descriptor) in descriptors.enumerated() {
                var matrix = CGAffineTransform.identity
                let font = CTFontCreateWithFontDescriptor(descriptor, 0, &matrix)
                // No identity guard precedes recording this best-match result.
                let descriptorURL = urlEvidence(CTFontDescriptorCopyAttribute(descriptor, kCTFontURLAttribute), url)
                let fontURL = urlEvidence(CTFontCopyAttribute(font, kCTFontURLAttribute), url)
                let actualUpem = Int(CTFontGetUnitsPerEm(font))
                let actualGlyphCount = CTFontGetGlyphCount(font)
                let fontSize = Double(CTFontGetSize(font))
                let actualMatrix = CTFontGetMatrix(font)
                // x' = xx*x + xy*y + tx; y' = yx*x + yy*y + ty.
                let matrixValues: [String: Double] = ["xx": Double(actualMatrix.a), "yx": Double(actualMatrix.b),
                                                      "xy": Double(actualMatrix.c), "yy": Double(actualMatrix.d),
                                                      "tx": Double(actualMatrix.tx), "ty": Double(actualMatrix.ty)]
                var actualTables: [String: TableObservation] = [:]
                for tag in requestedTags { actualTables[tag] = copyTable(font, tag) }
                let name = actualTables["name"]!
                let nameCandidates = faces.filter { face in
                    guard let expected = face.tables["name"] else { return false }
                    return name.present && name.length == expected.length && name.digest == expected.digest
                }.map { $0.index }
                for index in nameCandidates { nameDescriptors[index, default: []].append(descriptorIndex) }

                var comparisons: [[String: Any]] = []
                var matchingFaces: [Int] = []
                for face in faces {
                    let tableRows = face.tables.keys.sorted().map { compare(face.tables[$0]!, actualTables[$0]!, $0) }
                    let allTablesExact = tableRows.allSatisfy { ($0["exact"] as? Bool) == true }
                    let upemEqual = actualUpem == Int(face.upem)
                    let countEqual = actualGlyphCount == Int(face.glyphCount)
                    let exact = upemEqual && countEqual && allTablesExact
                    var reasons: [String] = []
                    if !upemEqual { reasons.append("coretext_upem_mismatch") }
                    if !countEqual { reasons.append("coretext_glyph_count_mismatch") }
                    if !allTablesExact { reasons.append("coretext_retained_table_identity_mismatch") }
                    comparisons.append(["face_index": face.index, "upem_equal": upemEqual,
                                        "glyph_count_equal": countEqual, "all_retained_tables_exact": allTablesExact,
                                        "tables": tableRows, "source_directory_has_vorg": face.tables["VORG"] != nil,
                                        "status": exact ? "EXACT" : "IDENTITY_MISMATCH", "error_codes": reasons])
                    if exact {
                        matchingFaces.append(face.index)
                        exactDescriptors[face.index, default: []].append(descriptorIndex)
                    }
                }
                let bindingStatus: String
                if matchingFaces.count == 1 {
                    bindingStatus = "EXACT_PHYSICAL_FACE"
                    unambiguousDescriptors[matchingFaces[0], default: []].append(descriptorIndex)
                } else if matchingFaces.isEmpty {
                    bindingStatus = "NO_EXACT_PHYSICAL_FACE"
                    codes.insert("descriptor_has_no_exact_physical_face")
                } else {
                    bindingStatus = "AMBIGUOUS_IDENTICAL_PHYSICAL_FACES"
                    codes.insert("descriptor_matches_multiple_physical_faces")
                }
                descriptorRows.append([
                    "descriptor_index": descriptorIndex,
                    "descriptor_url_present": descriptorURL.present, "descriptor_url_matches_source": descriptorURL.matches,
                    "descriptor_url_status": descriptorURL.status,
                    "font_url_present": fontURL.present, "font_url_matches_source": fontURL.matches,
                    "font_url_status": fontURL.status,
                    "creation_api_nonoptional": true, "creation_status": "RETURNED_BEST_MATCH_CT_FONT",
                    "font_upem": actualUpem, "font_glyph_count": actualGlyphCount,
                    "font_size": finiteJSON(fontSize), "font_size_binary64_hex": binary64Hex(fontSize),
                    "font_size_finite": fontSize.isFinite,
                    "font_matrix": matrixValues.mapValues { finiteJSON($0) },
                    "font_matrix_binary64_hex": matrixValues.mapValues { binary64Hex($0) },
                    "font_matrix_is_identity": actualMatrix.isIdentity,
                    "name_table_present": name.present, "name_candidate_face_indices": nameCandidates,
                    "exact_matching_face_indices": matchingFaces,
                    "binding_method": "ALL_RETAINED_TABLES_LENGTH_SHA256_AND_UPM_GLYPH_COUNT",
                    "name_candidate_filter_is_binding_proof": false,
                    "binding_status": bindingStatus,
                    "direct_vorg": actualTables["VORG"]!.json,
                    "face_comparisons": comparisons])
            }
        } else {
            report["descriptor_api"] = ["status": "TYPE_MISMATCH", "count": count] as [String: Any]
            codes.insert("descriptor_array_type_mismatch")
        }
    } else {
        report["descriptor_api"] = ["status": "NIL", "count": 0] as [String: Any]
        codes.insert("descriptor_api_returned_nil")
    }

    var verifiedCount = 0
    var ambiguousCount = 0
    var unboundCount = 0
    for face in faces {
        let exact = exactDescriptors[face.index, default: []]
        let unambiguous = unambiguousDescriptors[face.index, default: []]
        faceRows[face.index]["name_candidate_descriptor_indices"] = nameDescriptors[face.index, default: []]
        faceRows[face.index]["exact_descriptor_indices"] = exact
        faceRows[face.index]["unambiguous_descriptor_indices"] = unambiguous
        if !unambiguous.isEmpty {
            faceRows[face.index]["binding_status"] = "EXACT_PHYSICAL_FACE"
            verifiedCount += 1
        } else if !exact.isEmpty {
            faceRows[face.index]["binding_status"] = "AMBIGUOUS_IDENTICAL_PHYSICAL_FACES"
            ambiguousCount += 1
        } else {
            faceRows[face.index]["binding_status"] = "NO_EXACT_DESCRIPTOR"
            unboundCount += 1
            codes.insert("source_face_has_no_exact_descriptor")
        }
    }

    var unchanged = false
    do {
        let after = try Data(contentsOf: url)
        let afterHash = sha256(after)
        unchanged = data.count == after.count && sourceHash == afterHash
        source["sha256_after"] = afterHash
        source["size_after"] = after.count
        source["unchanged"] = unchanged
        if !unchanged { codes.insert("source_changed_during_diagnosis") }
    } catch { codes.insert("source_reread_failed") }
    let parsingComplete = !offsets.isEmpty && faces.count == offsets.count
    report["status"] = parsingComplete && unchanged ? "DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE" : "DIAGNOSTIC_PARTIAL_NOT_ACCEPTANCE"
    report["source"] = source
    report["descriptors"] = descriptorRows
    report["faces"] = faceRows
    report["summary"] = ["parsed_face_count": faces.count, "identity_verified_face_count": verifiedCount,
                         "unbound_face_count": unboundCount, "ambiguous_face_count": ambiguousCount,
                         "descriptor_count": descriptorRows.count, "metrics_observed": 0,
                         "all_faces_identity_verified": parsingComplete && unchanged && verifiedCount == offsets.count] as [String: Any]
    report["error_codes"] = codes.sorted()
    return report
}

// A completed diagnostic exits zero even when no face can be bound. Consumers
// must inspect explicit identity fields; process success never means acceptance.
// Foundation/CoreText errors are never interpolated into public output.
do {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    var data = try encoder.encode(ExactJSON(diagnose()))
    data.append(10)
    FileHandle.standardOutput.write(data)
} catch {
    FileHandle.standardOutput.write(Data("{\"schema\":\"swirl-vf-b1-original-startup-v1\",\"status\":\"DIAGNOSTIC_OUTPUT_FAILED_NOT_ACCEPTANCE\",\"error_codes\":[\"diagnostic_json_encoding_failed\"]}\n".utf8))
    exit(2)
}
