// Native layout and outline observations for private joint-interpolation probes.
// No reconstructed or fontTools-derived geometry is used by this observer.
import Foundation
import CoreText
import CoreGraphics
import CryptoKit

enum ProbeError: Error { case invalid(String) }
func require(_ ok: Bool, _ message: String) throws {
    if !ok { throw ProbeError.invalid(message) }
}
func digest(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}
func tag(_ text: String) -> UInt32 { text.utf8.reduce(0) { $0 << 8 | UInt32($1) } }
func emit(_ value: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    FileHandle.standardOutput.write(data); FileHandle.standardOutput.write(Data([10]))
}
func commands(_ path: CGPath) -> [[Any]] {
    var result = [[Any]]()
    path.applyWithBlock { ptr in
        let e = ptr.pointee
        var row: [Any]
        var count: Int
        switch e.type {
        case .moveToPoint: row = ["moveTo"]; count = 1
        case .addLineToPoint: row = ["lineTo"]; count = 1
        case .addQuadCurveToPoint: row = ["qCurveTo"]; count = 2
        case .addCurveToPoint: row = ["curveTo"]; count = 3
        case .closeSubpath: row = ["closePath"]; count = 0
        @unknown default: row = ["unsupported"]; count = 0
        }
        for i in 0..<count { row.append(Double(e.points[i].x)); row.append(Double(e.points[i].y)) }
        result.append(row)
    }
    return result
}
func main() throws {
    try require(CommandLine.arguments.count == 2, "manifest_required")
    let manifest = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    guard let config = try JSONSerialization.jsonObject(with: manifest) as? [String: Any],
          let path = config["font_path"] as? String,
          let expected = config["font_sha256"] as? String,
          let defaults = config["axis_defaults"] as? [String: Double],
          let tables = config["table_hashes"] as? [String: String],
          let requests = config["requests"] as? [[String: Any]] else {
        throw ProbeError.invalid("invalid_manifest")
    }
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    try require(digest(data) == expected, "source_digest_mismatch")
    guard let provider = CGDataProvider(data: data as CFData), let graphics = CGFont(provider) else {
        throw ProbeError.invalid("cannot_open_font")
    }
    let upm = graphics.unitsPerEm
    var count = 0
    for request in requests {
        guard let id = request["id"] as? String, let text = request["text"] as? String,
              let coordinates = request["coordinates"] as? [String: Double] else {
            throw ProbeError.invalid("invalid_request")
        }
        try require(Set(coordinates.keys) == Set(defaults.keys), "incomplete_axes")
        let axes = Dictionary(uniqueKeysWithValues: coordinates.map {
            (NSNumber(value: tag($0.key)), NSNumber(value: $0.value))
        })
        let descriptor = CTFontDescriptorCreateWithAttributes([
            kCTFontVariationAttribute: axes,
            kCTFontOpenTypeFeatureTag: "rvrn"
        ] as CFDictionary)
        var matrix = CGAffineTransform.identity
        let font = CTFontCreateWithGraphicsFont(graphics, CGFloat(upm), &matrix, descriptor)
        let attributed = NSAttributedString(string: text,
            attributes: [NSAttributedString.Key(kCTFontAttributeName as String): font])
        let line = CTLineCreateWithAttributedString(attributed)
        let runs = CTLineGetGlyphRuns(line) as! [CTRun]
        var observations = [[String: Any]]()
        for run in runs {
            let attributes = CTRunGetAttributes(run) as NSDictionary
            guard let runFont = attributes[kCTFontAttributeName] else { throw ProbeError.invalid("missing_run_font") }
            let actual = runFont as! CTFont
            try require(CTFontGetUnitsPerEm(actual) == upm && CTFontGetSize(actual) == CGFloat(upm), "run_scale_changed")
            for (key, wanted) in tables {
                guard let bytes = CTFontCopyTable(actual, tag(key), CTFontTableOptions(rawValue: 0)) else {
                    throw ProbeError.invalid("missing_run_table:\(key)")
                }
                try require(digest(bytes as Data) == wanted, "run_table_changed:\(key)")
            }
            let observed = CTFontCopyVariation(actual) as? [NSNumber: NSNumber] ?? [:]
            for (key, wanted) in coordinates {
                let value = observed[NSNumber(value: tag(key))]?.doubleValue ?? defaults[key]!
                try require(value == wanted, "axis_readback_mismatch:\(id):\(key):requested=\(wanted):observed=\(value)")
            }
            let n = CTRunGetGlyphCount(run)
            var glyphs = [CGGlyph](repeating: 0, count: n)
            var advances = [CGSize](repeating: .zero, count: n)
            CTRunGetGlyphs(run, CFRange(location: 0, length: 0), &glyphs)
            CTRunGetAdvances(run, CFRange(location: 0, length: 0), &advances)
            for i in 0..<n {
                guard let outline = CTFontCreatePathForGlyph(actual, glyphs[i], nil) else {
                    throw ProbeError.invalid("missing_outline")
                }
                observations.append(["gid": Int(glyphs[i]), "commands": commands(outline),
                                     "advance_width": Double(advances[i].width)])
            }
        }
        try emit(["type": "sample", "id": id, "coordinates": coordinates, "glyphs": observations])
        count += 1
    }
    try emit(["type": "summary", "request_count": count, "font_sha256": expected,
              "exact_axis_readback": true, "run_tables_verified": true])
}
do { try main() } catch {
    try? emit(["type": "error", "error": String(describing: error)])
    exit(1)
}
