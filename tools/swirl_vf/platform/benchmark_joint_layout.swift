// Measured CoreText loading/shaping/drawing and omitted hidden-axis defaults.
// Performance observations do not replace the separate HVF accuracy verifier.
import Foundation
import CoreText
import CoreGraphics
import CryptoKit
import Darwin
func now() -> Double { Double(DispatchTime.now().uptimeNanoseconds)/1e9 }
func tag(_ s: String) -> UInt32 { s.utf8.reduce(0) { $0 << 8 | UInt32($1) } }
func sha(_ d: Data) -> String { SHA256.hash(data:d).map { String(format:"%02x",$0) }.joined() }
func fingerprint(_ path: CGPath) -> String {
    var d=Data()
    path.applyWithBlock { p in
        var kind=Int32(p.pointee.type.rawValue)
        withUnsafeBytes(of:&kind) { d.append(contentsOf:$0) }
        let count: Int
        switch p.pointee.type {
        case .moveToPoint,.addLineToPoint: count=1
        case .addQuadCurveToPoint: count=2
        case .addCurveToPoint: count=3
        default: count=0
        }
        for i in 0..<count {
            var x=Double(p.pointee.points[i].x),y=Double(p.pointee.points[i].y)
            withUnsafeBytes(of:&x) { d.append(contentsOf:$0) }
            withUnsafeBytes(of:&y) { d.append(contentsOf:$0) }
        }
    }
    return sha(d)
}
enum Failure: Error { case invalid(String) }
func run() throws {
    let cfg=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any]
    let path=cfg["font_path"] as! String, locations=cfg["locations"] as! [[String:Double]]
    let defaults=cfg["defaults"] as! [String:Double], baseGID=cfg["base_gid"] as! Int
    let t=now();let data=try Data(contentsOf:URL(fileURLWithPath:path));let read=now()-t
    guard sha(data)==cfg["font_sha256"] as? String else { throw Failure.invalid("font_hash") }
    let g=now();guard let provider=CGDataProvider(data:data as CFData),let graphics=CGFont(provider) else { throw Failure.invalid("CGFont") }
    let load=now()-g;var observations=[[String:Any]](), reference=[String](), omittedMismatch=0, directMismatch=0
    for explicit in [true,false] {
        var instances=[Double](),shaping=[Double](),drawing=[Double]()
        for (index,location) in locations.enumerated() {
            var coords=explicit ? defaults : [:];coords.merge(location){_,new in new}
            let attributes=Dictionary(uniqueKeysWithValues:coords.map{(NSNumber(value:tag($0.key)),NSNumber(value:$0.value))})
            let a=now();let descriptor=CTFontDescriptorCreateWithAttributes([kCTFontVariationAttribute:attributes] as CFDictionary)
            let font=CTFontCreateWithGraphicsFont(graphics,CGFloat(graphics.unitsPerEm),nil,descriptor);instances.append(now()-a)
            let b=now();let text=NSAttributedString(string:"A",attributes:[NSAttributedString.Key(kCTFontAttributeName as String):font])
            let line=CTLineCreateWithAttributedString(text),runs=CTLineGetGlyphRuns(line) as! [CTRun]
            guard runs.count==1,CTRunGetGlyphCount(runs[0])==1 else {throw Failure.invalid("layout_run")}
            let actual=(CTRunGetAttributes(runs[0]) as NSDictionary)[kCTFontAttributeName] as! CTFont
            var gid=CGGlyph(0);CTRunGetGlyphs(runs[0],CFRange(location:0,length:1),&gid);shaping.append(now()-b)
            let observed=CTFontCopyVariation(actual) as? [NSNumber:NSNumber] ?? [:]
            for (key,value) in defaults {
                let expected=location[key] ?? value
                guard (observed[NSNumber(value:tag(key))]?.doubleValue ?? value)==expected else {throw Failure.invalid("axis_readback")}
            }
            let c=now();guard let outline=CTFontCreatePathForGlyph(actual,gid,nil) else {throw Failure.invalid("outline")};drawing.append(now()-c)
            let signature=String(gid)+":"+fingerprint(outline)
            if explicit {
                reference.append(signature)
                if let direct=CTFontCreatePathForGlyph(actual,CGGlyph(baseGID),nil) {
                    if fingerprint(direct) != fingerprint(outline) {directMismatch+=1}
                } else {directMismatch+=1}
            } else if signature != reference[index] {omittedMismatch+=1}
        }
        observations.append(["explicit_hidden_defaults":explicit,"font_instance_seconds":instances,"shaping_seconds":shaping,"outline_seconds":drawing])
    }
    var usage=rusage();getrusage(RUSAGE_SELF,&usage)
    let result:[String:Any] = ["engine":"CoreText","requests_per_mode":locations.count,"read_seconds":read,
        "graphics_load_seconds":load,"peak_rss_bytes":usage.ru_maxrss,"measurements":observations,
        "omitted_hidden_default_mismatches":omittedMismatch,"unshaped_base_outline_mismatches":directMismatch,
        "accuracy_acceptance":false,"font_sha256":sha(data)]
    print(String(data:try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]),encoding:.utf8)!)
}
do {try run()} catch {fputs(String(describing:error)+"\n",stderr);exit(1)}
