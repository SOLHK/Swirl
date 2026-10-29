#!/usr/bin/env python3
"""Read-only local source baseline; never exports outlines or claims conversion.

Reuse the production extractor's parser, exact table identity and strict axis
validator unchanged. Full reports are private; stdout contains only counts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess

from fontTools.ttLib import TTCollection

MAIN = r'''
func baselineMain() throws {
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data = try Data(contentsOf: url, options: [.mappedIfSafe])
    let states = try locateDescriptors(parseFaces(Bytes(data: data)), url: url)
    let urlDescriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor]
    let dataDescriptors = CTFontManagerCreateFontDescriptorsFromData(data as CFData) as? [CTFontDescriptor]
    let provider = CGDataProvider(data: data as CFData)
    let graphicsFont = provider.flatMap { CGFont($0) }
    var faces: [[String: Any]] = []
    for state in states {
        var row: [String: Any] = ["face_index": state.raw.index,
            "identity_verified": state.baseFont != nil,
            "verified_table_sha256": state.metadata["verified_table_sha256"] ?? [:]]
        var attempted = 0, passed = 0
        var failures: [String: Int] = [:]
        if state.baseFont != nil {
            // Global metrics are measured only after exact source identity.
            do {
                let (font, _, _) = try makeInstance(state, [:])
                row["default_global_metrics"] = [
                    "size": Double(CTFontGetSize(font)),
                    "ascent": Double(CTFontGetAscent(font)),
                    "descent": Double(CTFontGetDescent(font)),
                    "leading": Double(CTFontGetLeading(font)),
                    "cap_height": Double(CTFontGetCapHeight(font)),
                    "x_height": Double(CTFontGetXHeight(font))]
            } catch { row["default_instance_error"] = String(describing: error) }
            for axis in state.raw.axes {
                // Fixed finite samples, including fractional values. No mapping inference.
                for fraction in [0.0, 0.123456789, 0.5, 1.0] {
                    let value = axis.minimum + fraction * (axis.maximum - axis.minimum)
                    attempted += 1
                    do { _ = try makeInstance(state, [axis.tag: value]); passed += 1 }
                    catch { failures[String(describing: error), default: 0] += 1 }
                }
            }
        }
        row["axis_requests"] = attempted
        row["axis_strict_passes"] = passed
        row["axis_failure_counts"] = failures
        faces.append(row)
    }
    try emit(["source_sha256": sha256(data), "faces": faces,
        "url_descriptor_count": urlDescriptors?.count ?? 0,
        "data_descriptor_count": dataDescriptors?.count ?? 0,
        "cgfont_created": graphicsFont != nil,
        "os_version": ProcessInfo.processInfo.operatingSystemVersionString])
}
do { try baselineMain() }
catch { stderr("Source baseline: \(error)"); exit(2) }
'''


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def harness(extractor):
    text = Path(extractor).read_text()
    marker = '\nfunc run() throws {'
    if text.count(marker) != 1:
        raise ValueError('extractor entry point changed; review baseline harness')
    return text[:text.index(marker)] + MAIN


def inspect_source(source):
    """Counts/metadata only; existing audit_font.py provides deeper private audit."""
    faces = []
    with TTCollection(source, lazy=True) as collection:
        for index, font in enumerate(collection.fonts):
            tables = font.reader.tables
            cmap = font.getBestCmap() or {}
            axes = [{'tag': a.axisTag, 'minimum': a.minValue, 'default': a.defaultValue,
                     'maximum': a.maxValue, 'flags': a.flags} for a in font['fvar'].axes] if 'fvar' in font else []
            faces.append({'face_index': index, 'glyph_count': font['maxp'].numGlyphs,
                          'upm': font['head'].unitsPerEm, 'unicode_codepoint_count': len(cmap),
                          'cmap_formats': sorted({t.format for t in font['cmap'].tables}),
                          'windows_name_record_count': sum(n.platformID == 3 for n in font['name'].names),
                          'axes': axes, 'tables': {
                              str(tag): {'length': entry.length, 'offset': entry.offset,
                                         'sha256': hashlib.sha256(font.reader[tag]).hexdigest()}
                              for tag, entry in tables.items()}})
    return faces


def summarize_native(native, source_hash, faces):
    """Reject partial, duplicate or unrelated native reports before counting passes."""
    if native.get('source_sha256') != source_hash:
        raise ValueError('native source identity mismatch')
    rows = native.get('faces')
    if not isinstance(rows, list) or len(rows) != len(faces):
        raise ValueError('native face count mismatch')
    for expected, actual in zip(faces, rows):
        if type(actual.get('face_index')) is not int or actual['face_index'] != expected['face_index']:
            raise ValueError('native face order mismatch')
        verified = actual.get('identity_verified')
        if type(verified) is not bool:
            raise ValueError('native identity verdict missing')
        wanted = {tag: table['sha256'] for tag, table in expected['tables'].items()}
        if actual.get('verified_table_sha256') != (wanted if verified else {}):
            raise ValueError('native table identity mismatch')
        attempted, passed = actual.get('axis_requests'), actual.get('axis_strict_passes')
        failures = actual.get('axis_failure_counts')
        if (type(attempted) is not int or type(passed) is not int or not isinstance(failures, dict)
                or any(type(v) is not int or v < 0 for v in failures.values())
                or not 0 <= passed <= attempted or passed + sum(failures.values()) != attempted
                or attempted != (4 * len(expected['axes']) if verified else 0)
                or (not verified and 'default_global_metrics' in actual)):
            raise ValueError('inconsistent native axis/metric evidence')
    verified = sum(row['identity_verified'] for row in rows)
    return {'status': ('SOURCE_IDENTITY_VERIFIED_NOT_CONVERSION' if verified == len(faces)
                       else 'BLOCKED_SOURCE_IDENTITY'),
            'face_count': len(faces), 'physical_faces_verified': verified,
            'axis_requests': sum(row['axis_requests'] for row in rows),
            'axis_strict_passes': sum(row['axis_strict_passes'] for row in rows),
            'font_generated': False, 'windows11_acceptance': 'NOT_RUN'}


def run(source, output, expected_sha256=None):
    source, output = Path(source).resolve(strict=True), Path(output).absolute()
    source_hash = digest(source)
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise ValueError('source SHA-256 differs from requested baseline')
    # Refuse an existing result, including a directory symlink. Never rewrite input.
    if output.exists() or output.is_symlink():
        raise ValueError('choose a fresh private output directory')
    output.mkdir(parents=True, mode=0o700)
    faces = inspect_source(source)
    report = {'source_sha256': source_hash, 'source_bytes': source.stat().st_size,
              'faces': faces, 'host': platform.platform(), 'native': None,
              'summary': {'status': 'NOT_RUN', 'font_generated': False, 'windows11_acceptance': 'NOT_RUN'}}
    extractor = Path(__file__).with_name('coretext_extract.swift')
    report['extractor_sha256'] = digest(extractor)
    text = harness(extractor)
    report['harness_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    code = 2
    try:
        if platform.system() == 'Darwin':
            swift, binary = output / 'baseline.swift', output / 'baseline'
            swift.write_text(text)
            build = subprocess.run(['xcrun', 'swiftc', '-O', str(swift), '-o', str(binary)],
                                   capture_output=True, timeout=180)
            (output / 'compile.log').write_bytes(build.stdout + build.stderr)
            if build.returncode:
                raise RuntimeError('native compile failed; see private compile.log')
            result = subprocess.run([str(binary), str(source)], capture_output=True, timeout=180)
            (output / 'native.stderr.log').write_bytes(result.stderr)
            if result.returncode:
                raise RuntimeError('native baseline failed; see private native.stderr.log')
            report['native'] = json.loads(result.stdout)
            report['summary'] = summarize_native(report['native'], source_hash, faces)
            code = 0 if report['summary']['status'] == 'SOURCE_IDENTITY_VERIFIED_NOT_CONVERSION' else 2
    except Exception as error:
        report['summary']['status'] = 'FAILED'
        report['error_type'] = type(error).__name__
        raise
    finally:
        report['source_unchanged'] = digest(source) == source_hash
        if not report['source_unchanged']:
            report['summary']['status'] = 'FAILED_SOURCE_CHANGED'
            code = 2
        with (output / 'baseline.json').open('x') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
        print(json.dumps(report['summary'], allow_nan=False))
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='fresh private directory')
    parser.add_argument('--expected-sha256')
    args = parser.parse_args()
    raise SystemExit(run(args.source, args.output, args.expected_sha256))
