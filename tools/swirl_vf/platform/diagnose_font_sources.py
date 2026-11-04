#!/usr/bin/env python3
"""Discover actual system fonts and compare exact files through native APIs.

No font-name fallback is used to accept the supplied source. A byte-identical
private copy controls for location-dependent loading. Reports and copies stay
in a fresh private directory; no source data is written to stdout. A successful
diagnostic is not a conversion, precision result or distribution authorization.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

import fontTools
from fontTools.ttLib import TTCollection, TTFont
import uharfbuzz as hb

from macos_source_baseline import digest

MAIN = r'''
func sourceFontSummary(_ font: CTFont) -> [String: Any] {
    var characters = Array("中文Ab09，。".utf16)
    var glyphs = [CGGlyph](repeating: 0, count: characters.count)
    let mapped = CTFontGetGlyphsForCharacters(font, &characters, &glyphs, characters.count)
    return ["postscript": CTFontCopyPostScriptName(font) as String,
        "family": CTFontCopyFamilyName(font) as String,
        "url": (CTFontCopyAttribute(font, kCTFontURLAttribute) as? URL)?.path ?? "",
        "glyph_count": CTFontGetGlyphCount(font), "upem": CTFontGetUnitsPerEm(font),
        "axes": coreTextAxes(font), "mixed_cmap_complete": mapped,
        "mixed_glyph_count": glyphs.count,
        "mixed_nonempty_paths": glyphs.filter { CTFontCreatePathForGlyph(font, $0, nil) != nil }.count]
}

func sourceInventory() throws {
    let names = CTFontManagerCopyAvailablePostScriptNames() as? [String] ?? []
    let collection = CTFontCollectionCreateFromAvailableFonts(nil)
    let descriptors = CTFontCollectionCreateMatchingFontDescriptors(collection) as? [CTFontDescriptor] ?? []
    let selected = descriptors.filter { descriptor in
        [kCTFontNameAttribute, kCTFontFamilyNameAttribute, kCTFontDisplayNameAttribute].contains { key in
            let name = (CTFontDescriptorCopyAttribute(descriptor, key) as? String ?? "").lowercased()
            return name.contains("pingfang") || name.contains("苹方")
        }
    }
    try emit(["available_postscript_count": names.count, "available_descriptor_count": descriptors.count,
        "matching_names": names.filter { $0.lowercased().contains("pingfang") },
        "fonts": selected.map { sourceFontSummary(CTFontCreateWithFontDescriptor($0, 32, nil)) }])
}

func sourceFile(_ path: String) throws {
    let url = URL(fileURLWithPath: path)
    let data = try Data(contentsOf: url)
    let raw = try parseFaces(Bytes(data: data))
    let descriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor]
    let fromData = CTFontManagerCreateFontDescriptorsFromData(data as CFData) as? [CTFontDescriptor]
    let graphics = CGDataProvider(data: data as CFData).flatMap { CGFont($0) }
    let states = try locateDescriptors(raw, url: url)
    var result: [String: Any] = ["path": path, "sha256": sha256(data), "bytes": data.count,
        "physical_faces": raw.count, "url_descriptors": descriptors?.count ?? 0,
        "data_descriptors": fromData?.count ?? 0, "cgfont": graphics != nil,
        "native_identity_faces": states.filter { $0.baseFont != nil }.count,
        "faces": states.map { $0.metadata },
        "loaded_samples": (descriptors ?? []).prefix(2).map {
            sourceFontSummary(CTFontCreateWithFontDescriptor($0, 32, nil)) }]
    var error: Unmanaged<CFError>?
    let registered = CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error)
    result["registered"] = registered
    if let value = error?.takeRetainedValue() {
        result["register_error_code"] = CFErrorGetCode(value)
        result["register_error_domain"] = CFErrorGetDomain(value) as String
    }
    result["post_registration_url_descriptors"] =
        (CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor])?.count ?? 0
    if registered {
        var cleanup: Unmanaged<CFError>?
        result["unregistered"] = CTFontManagerUnregisterFontsForURL(url as CFURL, .process, &cleanup)
        if let value = cleanup?.takeRetainedValue() { result["unregister_error_code"] = CFErrorGetCode(value) }
    }
    result["source_unchanged"] = sha256(try Data(contentsOf: url)) == sha256(data)
    try emit(result)
}
do {
    if CommandLine.arguments.count == 1 { try sourceInventory() }
    else if CommandLine.arguments.count == 2 { try sourceFile(CommandLine.arguments[1]) }
    else { throw OracleError.invalid("expected zero arguments or an exact file path") }
} catch { stderr("Font source diagnosis: \(error)"); exit(2) }
'''


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def harness():
    source = Path(__file__).with_name('coretext_extract.swift').read_text()
    marker = '\nfunc run() throws {'
    require(source.count(marker) == 1, 'review changed extractor entry point')
    return source.split(marker)[0] + MAIN


def discover(inventory, roots):
    paths = {Path(row['url']).resolve() for row in inventory['fonts'] if row.get('url')}
    errors = []
    for root in roots:
        if not root.is_dir():
            errors.append({'path': str(root), 'error': 'directory_missing'})
            continue
        def failed(error):
            errors.append({'path': error.filename, 'error': type(error).__name__})
        for directory, _, files in os.walk(root, onerror=failed, followlinks=False):
            for name in files:
                if ('pingfang' in name.lower() or '苹方' in name) and Path(name).suffix.lower() in ('.ttc', '.ttf', '.otf'):
                    paths.add((Path(directory) / name).resolve())
    return sorted(paths), errors


def inspect(path):
    data = path.read_bytes()
    collection = TTCollection(path, lazy=True) if data[:4] == b'ttcf' else None
    fonts = collection.fonts if collection else [TTFont(path, lazy=True)]
    rows = []
    try:
        for i, font in enumerate(fonts):
            other = hb.Face(data, i)
            tables = {str(tag): hashlib.sha256(font.reader[tag]).hexdigest() for tag in font.reader.tables}
            axes = [{'tag': a.axisTag, 'minimum': a.minValue, 'default': a.defaultValue,
                     'maximum': a.maxValue, 'flags': a.flags} for a in font['fvar'].axes] if 'fvar' in font else []
            rows.append({'face_index': i, 'glyph_count': font['maxp'].numGlyphs,
                'upem': font['head'].unitsPerEm, 'version': font['name'].getDebugName(5),
                'axes': axes, 'tables': tables,
                'harfbuzz': {'physical_faces': other.count, 'glyph_count': other.glyph_count,
                    'upem': other.upem, 'axes': [a.tag for a in other.axis_infos],
                    'outline_rendering': 'NOT_TESTED'}})
            require(other.count == len(fonts) and other.glyph_count == font['maxp'].numGlyphs
                    and other.upem == font['head'].unitsPerEm, 'independent parser face metadata differs')
    finally:
        if collection:
            collection.close()
        else:
            fonts[0].close()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'faces': rows}


def validate_native(native, inspected):
    require(native.get('source_unchanged') is True and native.get('sha256') == inspected['sha256']
            and native.get('bytes') == inspected['bytes'], 'native file identity changed')
    rows = native.get('faces')
    require(type(rows) is list and len(rows) == len(inspected['faces']) == native.get('physical_faces'),
            'native face coverage differs')
    verified = 0
    for actual, expected in zip(rows, inspected['faces']):
        require(type(actual.get('face_index')) is int and actual['face_index'] == expected['face_index'],
                'native face index changed')
        if actual.get('status') == 'identity_verified':
            require(actual.get('verified_table_sha256') == expected['tables']
                    and actual.get('glyph_count') == expected['glyph_count']
                    and actual.get('upm') == expected['upem'], 'system substitution or table mismatch')
            verified += 1
    require(type(native.get('native_identity_faces')) is int and native['native_identity_faces'] == verified,
            'native identity count differs')
    require(type(native.get('registered')) is bool and type(native.get('cgfont')) is bool
            and all(type(native.get(k)) is int and native[k] >= 0
                    for k in ('url_descriptors', 'data_descriptors', 'post_registration_url_descriptors')),
            'native API verdict missing or malformed')
    require(not native.get('registered') or native.get('unregistered') is True,
            'process registration cleanup failed')
    return verified


def compare_copy(original, copied):
    require(original['sha256'] == copied['sha256'] and original['bytes'] == copied['bytes']
            and original['source_unchanged'] and copied['source_unchanged'], 'copy control bytes differ')
    keys = ('physical_faces', 'url_descriptors', 'data_descriptors', 'native_identity_faces',
            'cgfont', 'registered', 'register_error_code')
    differences = {key: [original.get(key), copied.get(key)] for key in keys
                   if original.get(key) != copied.get(key)}
    return {'byte_identical': True, 'location_dependent_api_differences': differences,
            'private_platform_implementation_cause': 'NOT_PROVEN'}


def public_summary(report):
    """Fixed aggregate allowlist: never export paths, inventories or raw tables."""
    cases = {}
    for label, case in report['cases'].items():
        parsed, native = case['parsed'], case['native']
        cases[label] = {'sha256': parsed['sha256'], 'bytes': parsed['bytes'],
            'physical_faces': len(parsed['faces']),
            'glyph_counts': sorted({f['glyph_count'] for f in parsed['faces']}),
            'versions': sorted({f['version'] for f in parsed['faces'] if f['version']}),
            'native_identity_faces': native['native_identity_faces'],
            'url_descriptors': native['url_descriptors'], 'data_descriptors': native['data_descriptors'],
            'cgfont': native['cgfont'], 'registered': native['registered'],
            'register_error_code': native.get('register_error_code'), 'source_unchanged': native['source_unchanged']}
    return {'status': report['status'], 'host': report['host'], 'source_sha256': report['source_sha256'],
            'source_unchanged': report['source_unchanged'], 'cases': cases,
            'same_bytes_different_location_controls': {
                key: {'byte_identical': value['byte_identical'],
                      'differing_api_fields': sorted(value['location_dependent_api_differences'])}
                for key, value in report['copy_controls'].items()},
            'font_generated': False, 'production_accepted': False, 'windows11_acceptance': 'NOT_RUN'}


def run(source, output, expected_sha256=None, candidate=None, scan_root=None):
    source, output = Path(source).resolve(strict=True), Path(output).absolute()
    require(platform.system() == 'Darwin', 'CoreText diagnosis NOT_RUN: macOS required')
    require(not output.exists() and not output.is_symlink(), 'fresh private output required')
    original_hash = digest(source)
    require(expected_sha256 is None or original_hash == expected_sha256, 'supplied source SHA differs')
    output.mkdir(parents=True, mode=0o700)
    report = {'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'host': platform.platform(),
        'python': platform.python_version(), 'fonttools': fontTools.__version__, 'harfbuzz': hb.version_string(),
        'source_sha256': original_hash, 'cases': {}, 'copy_controls': {}, 'font_generated': False,
        'status': 'IN_PROGRESS', 'windows11_acceptance': 'NOT_RUN'}

    def persist():
        temporary = output / 'report.pending'
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False))
        temporary.replace(output / 'report.json')

    def execute(label, command):
        result = subprocess.run(command, capture_output=True, timeout=300)
        (output / (label+'.stdout')).write_bytes(result.stdout)
        (output / (label+'.stderr')).write_bytes(result.stderr)
        report.setdefault('commands', []).append({'command': command, 'exit': result.returncode})
        persist()
        require(result.returncode == 0, label+' failed; see private logs')
        return result.stdout

    def measure(label, path):
        metadata = inspect(path)
        native = json.loads(execute(label, [str(binary), str(path)]))
        validate_native(native, metadata)
        report['cases'][label] = {'path': str(path), 'parsed': metadata, 'native': native}
        persist()
        return native

    try:
        swift, binary = output / 'probe.swift', output / 'probe'
        swift.write_text(harness())
        report['harness_sha256'] = digest(swift)
        report['extractor_sha256'] = digest(Path(__file__).with_name('coretext_extract.swift'))
        execute('compile', ['xcrun', 'swiftc', '-O', str(swift), '-o', str(binary)])
        report['binary_sha256'] = digest(binary)
        inventory = json.loads(execute('inventory', [str(binary)]))
        report['inventory'] = inventory
        roots = scan_root or [Path('/System/Library'), Path('/Library/Fonts'), Path.home()/'Library/Fonts']
        paths, errors = discover(inventory, roots)
        report['discovery'] = {'paths': [str(p) for p in paths], 'errors': errors}
        measure('supplied-source', source)
        for index, path in enumerate(paths):
            label = f'system-{index}'
            native = measure(label, path)
            copied = output / (label+'-private-copy'+path.suffix)
            shutil.copyfile(path, copied)
            copied.chmod(0o400)
            require(digest(copied) == native['sha256'], 'copy control SHA differs')
            other = measure(label+'-copy', copied)
            report['copy_controls'][label] = compare_copy(native, other)
            persist()
        if candidate:
            if Path(candidate).is_file():
                measure('candidate', Path(candidate).resolve(strict=True))
            else:
                report['candidate'] = {'status': 'NOT_GENERATED', 'path': str(candidate)}
        report['status'] = 'DIAGNOSIS_COMPLETE_NOT_FONT_ACCEPTANCE'
    except Exception as error:
        report.update(status='FAILED', error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        report['source_unchanged'] = digest(source) == original_hash
        if not report['source_unchanged']:
            report['status'] = 'FAILED_SOURCE_CHANGED'
        persist()
        print(json.dumps({key: report[key] for key in ('status', 'source_unchanged', 'font_generated')}))
        require(report['source_unchanged'], 'source changed during diagnosis')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path, required=True, help='fresh private directory outside repository')
    p.add_argument('--expected-sha256')
    p.add_argument('--candidate', type=Path)
    p.add_argument('--scan-root', type=Path, action='append')
    run(**vars(p.parse_args()))
