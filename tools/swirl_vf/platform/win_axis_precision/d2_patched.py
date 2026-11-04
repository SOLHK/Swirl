#!/usr/bin/env python3
"""Source-built Qt A/B validation. No application-side transform intervention.

Both builds run the unchanged D1 probe and D2's CONTROL mode. The original
failures remain evidence; only the separately rebuilt DLL must pass strictly.
"""
from __future__ import annotations
import argparse
import copy
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys

import d2_state as d2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analyze_win_axis_precision as d1

ENGINE = 'src/gui/text/freetype/qfontengine_ft.cpp'
SPECS = tuple(itertools.product((96, 144, 192), (1, 1.25, 1.5, 2), ('no', 'full'), (False, True)))


def read(path):
    return d1.load_json(path)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def records(path):
    data = path.read_text(encoding='utf-8-sig')
    d2.check(data.endswith('\n'), 'Truncated JSONL')
    return [d1.read_json(line) for line in data.splitlines() if line.strip()]


def label(spec):
    dpi, dpr, hint, disabled = spec
    return f'dpi{dpi}-dpr{dpr}-{hint}-cache{int(not disabled)}-control'


def apply_patch(qt, prepared, patch, proof, sha):
    binding = d2.load_binding(prepared, sha)
    d2.check(subprocess.check_output(['git', '-C', str(qt), 'rev-parse', 'HEAD'], text=True).strip()
             == d2.QT_COMMIT, 'Wrong Qt checkout')
    d2.check(not subprocess.check_output(['git', '-C', str(qt), 'diff', 'HEAD', '--name-only']),
             'Qt checkout already modified')
    original = (qt / ENGINE).read_bytes().replace(b'\r\n', b'\n')
    d2.check(d2.blob(original) == d2.SOURCE_BLOBS[ENGINE], 'Original engine blob mismatch')
    patch_bytes = patch.read_bytes().replace(b'\r\n', b'\n')
    generated = (prepared / 'qt-6.10.3-outline-delta.patch').read_bytes().replace(b'\r\n', b'\n')
    d2.check(patch_bytes == generated and d2.digest(patch_bytes) == binding['patch_sha256'],
             'Reviewed patch differs from source-verified proposal')
    canonical_patch = prepared / 'reviewed-lf.patch'
    canonical_patch.write_bytes(patch_bytes)
    subprocess.run(['git', '-C', str(qt), 'apply', '--check', str(canonical_patch)], check=True)
    subprocess.run(['git', '-C', str(qt), 'apply', str(canonical_patch)], check=True)
    changed = (qt / ENGINE).read_bytes().replace(b'\r\n', b'\n')
    d2.check(changed == d2.patch_source(original.decode()).encode(), 'Applied code is not exact scoped fix')
    paths = subprocess.check_output(['git', '-C', str(qt), 'diff', 'HEAD', '--name-only'], text=True).splitlines()
    d2.check(paths == [ENGINE], 'Patch escaped the one permitted upstream file')
    save(proof, {'source_commit': sha, 'qt_commit': d2.QT_COMMIT, 'patch_sha256': d2.digest(patch_bytes),
                 'original_engine_git_blob': d2.blob(original), 'patched_engine_sha256': d2.digest(changed),
                 'changed_upstream_files': paths, 'applied': True, 'production_integration': False})


def verify_pixels(directory, row):
    from PIL import Image
    d2.check(row['png'] == f"draw-{row['index']:02}.png", 'Unsafe/unexpected raster filename')
    data = (directory / (row['png'] + '.bin')).read_bytes()
    d2.check(len(data) == row['width'] * row['height'] * 4
             and d2.digest(data) == row['pixel_sha256'], 'Raw pixel evidence mismatch')
    d2.check(data != b'\xff' * len(data), 'Empty raster')
    with Image.open(directory / row['png']) as image:
        d2.check(image.size == (row['width'], row['height'])
                 and image.convert('RGBA').tobytes('raw', 'BGRA') == data,
                 'PNG does not decode to recorded BGRA bytes')
    return data


def validate_control(rows, sha, font_hash, binding, kind):
    result = d2.validate(rows, sha, font_hash, binding)
    d2.check(rows[0]['mode'] == 'control', 'Application-side guard is forbidden in DLL validation')
    if kind == 'patched':
        d2.check(result['original_mismatches'] == result['isolated_mismatches'] == 0,
                 'Patched public path query still changes with history')
    else:
        d2.check(kind == 'baseline', 'Unknown build kind')
    return result


def probe(exe, font, out, prepared, prefix, sha, kind):
    d2.check(os.name == 'nt' and os.environ.get('GITHUB_SHA') == sha, 'Native source-bound Windows required')
    out.mkdir(parents=True, exist_ok=False)
    binding = d2.load_binding(prepared, sha)
    report = {'source_commit': sha, 'kind': kind, 'status': 'FAILED', 'processes': [], 'errors': [],
              'font_sha256': d2.digest(font.read_bytes()), 'executable_sha256': d2.digest(exe.read_bytes()),
              'application_guard_used': False, 'production_integration': False}
    expected_dll = (prefix / 'bin' / 'Qt6Gui.dll').resolve()
    runtime = None
    for spec in SPECS:
        dpi, dpr, hint, disabled = spec
        name = label(spec)
        directory = out / name
        directory.mkdir()
        entry = {'label': name, 'status': 'FAILED'}
        report['processes'].append(entry)
        try:
            env = dict(os.environ, QT_QPA_PLATFORM='windows:fontengine=freetype', QT_NO_FT_CACHE=str(int(disabled)))
            command = [str(exe), str(font), str(directory), str(dpi), str(dpr), hint, 'control']
            process = subprocess.run(command, env=env, capture_output=True, timeout=90)
            (directory / 'stdout.log').write_bytes(process.stdout)
            (directory / 'stderr.log').write_bytes(process.stderr)
            entry.update(exit_code=process.returncode, command=command)
            d2.check(process.returncode == 0, f'Native exit {process.returncode}: {process.stderr.decode(errors="replace")}')
            rows = records(directory / 'd2.jsonl')
            entry.update(validate_control(rows, sha, report['font_sha256'], binding, kind))
            h = rows[0]
            d2.check((h['logical_dpi'], h['dpr'], h['hint'], h['cache_disabled']) == spec, 'Scenario mismatch')
            d2.check(Path(h['qt_gui_path']).resolve() == expected_dll
                     and d2.digest(expected_dll.read_bytes()) == h['qt_gui_sha256'], 'Wrong loaded rebuilt DLL')
            identity = {k: h[k] for k in ('qt_gui_path', 'qt_gui_sha256', 'qt_version', 'freetype_version')}
            if runtime is None:
                runtime = identity
                report['runtime_identity'] = identity
            d2.check(runtime == identity, 'Runtime changed between processes')
            seen = {}
            for row in rows[1:-1]:
                data = verify_pixels(directory, row)
                key = tuple(row['offset'])
                d2.check(key not in seen or seen[key] == data, 'Repeated raster changed')
                seen[key] = data
            entry.update(status='PASS', log_sha256=d2.digest((directory / 'd2.jsonl').read_bytes()))
        except Exception as exc:
            entry['error'] = str(exc)
            report['errors'].append(name + ': ' + str(exc))
        save(out / 'probe-analysis.json', report)
    report['observations'] = sum(p['status'] == 'PASS' for p in report['processes']) * len(d2.OFFSETS)
    report['status'] = 'PASS_REBUILT_' + kind.upper() if not report['errors'] else 'FAILED'
    save(out / 'probe-analysis.json', report)
    d2.check(not report['errors'], '; '.join(report['errors'][:3]))


def compare_control_rows(before, after):
    d2.check(before[0]['mode'] == after[0]['mode'] == 'control', 'Guarded evidence cannot validate DLL repair')
    for key in ('baseline_path', 'baseline_advance', 'baseline_state', 'fixed_axes', 'raw_pixel_size', 'gid'):
        d2.check(before[0][key] == after[0][key], 'Cold baseline changed: ' + key)
    d2.check(len(before) == len(after) == len(d2.OFFSETS) + 2, 'Incomplete A/B logs')
    for a, b in zip(before[1:-1], after[1:-1]):
        for key in ('index', 'offset', 'advance', 'before_draw', 'after_draw', 'before_guard', 'after_guard',
                    'cache_before', 'cache_after', 'cache_after_guard', 'pixel_sha256', 'width', 'height'):
            d2.check(a[key] == b[key], 'DLL patch changed state/advance/raster: ' + key)
        for key in ('original_path', 'isolated_path', 'original_replay'):
            d2.check(b[key] == before[0]['baseline_path'], 'Patched complete path differs from cold reference')


def without_paths(payload):
    value = copy.deepcopy(payload)
    for glyph in value['glyphs']:
        glyph.pop('path_px')
    for run in value['layout']['runs']:
        run.pop('paths_px')
    return value


def compare_d1(root, sha):
    base, patched = root / 'baseline-d1', root / 'patched-d1'
    partial = d1.collect_partial_evidence(base, sha)
    expected = {f'ordinary-qt-freetype-{mode}-{order}' for mode in ('private', 'installed')
                for order in ('forward', 'reverse')}
    d2.check(partial['validated_processes'] == 12 and partial['validated_observations'] == 3568
             and set(partial['rejected_processes']) == expected, 'Baseline failures differ from original D1 defect')
    for field in ('missing_processes', 'unexpected_process_labels', 'binding_errors', 'comparison_failures'):
        d2.check(not partial[field], 'Invalid baseline evidence: ' + field)
    for installation in partial['installation_lifecycle']:
        d2.check(installation['cleanup'] == 'PASS', 'Baseline cleanup failed')
    for name in expected:
        rows = records(base / name / 'qt-axis-precision.jsonl')
        comparisons = [r for r in rows if r['record'] == 'pair_comparison']
        d2.check(len(comparisons) == 1 and comparisons[0]['raw_outline_equal'] is False
                 and comparisons[0]['raw_advance_equal'] is True and comparisons[0]['raster_equal'] is True
                 and rows[-1]['status'] == 'FAILED'
                 and rows[-1]['error'] == 'Identical API inputs produced different actual pair outputs',
                 'Original outline failure not reproduced')
    complete = d1.analyze(patched, sha)
    d2.check(complete['processes'] == 16 and all(complete['opposite_process_replays'].values())
             and all(v['equal'] for v in complete['private_vs_installed'].values()), 'Patched D1 not exact')
    save(root / 'baseline-d1-revalidated.json', partial)
    save(root / 'patched-d1-revalidated.json', complete)
    compared = 0
    for name in complete['experiments']:
        native = '-dwrite-' in name
        filename = 'directwrite-axis-precision.jsonl' if native else 'qt-axis-precision.jsonl'
        aa = [r for r in records(base / name / filename) if r['record'] == 'observation']
        bb = [r for r in records(patched / name / filename) if r['record'] == 'observation']
        def key(r): return (r['case_id'], r['pass'], r.get('scenario'))
        indexed = {key(r): r for r in bb}
        for row in aa:
            other = indexed[key(row)]
            if native:
                d2.check(d1.native_payload(row) == d1.native_payload(other), 'DirectWrite regression')
            elif name in expected:
                d2.check(without_paths(row['payload']) == without_paths(other['payload']), 'FreeType non-path regression')
            else:
                d2.check(row['payload'] == other['payload'], 'Qt Native regression')
            compared += 1
    return {'baseline_passed_processes': 12, 'baseline_retained_failures': sorted(expected),
            'patched_passed_processes': 16, 'baseline_to_patched_observations_compared': compared,
            'patched_observations': sum(v['summary'].get('observation_count', v['summary'].get('observations', 0))
                                        for v in complete['experiments'].values())}


def compare(root, prepared, sha):
    report = {'source_commit': sha, 'status': 'FAILED', 'production_integration': False}
    try:
        proof = read(root / 'applied-patch.json')
        d2.check(proof['applied'] is True and proof['source_commit'] == sha and proof['qt_commit'] == d2.QT_COMMIT
                 and proof['changed_upstream_files'] == [ENGINE], 'Missing applied patch provenance')
        reports = [read(root / (kind + '-probe') / 'probe-analysis.json') for kind in ('baseline', 'patched')]
        a, b = reports
        for r, kind in zip(reports, ('baseline', 'patched')):
            d2.check(r['source_commit'] == sha and r['status'] == 'PASS_REBUILT_' + kind.upper()
                     and r['observations'] == 576 and len(r['processes']) == 48
                     and {e['label'] for e in r['processes']} == {label(s) for s in SPECS}
                     and r['application_guard_used'] is False, 'Incomplete control matrix')
        d2.check(a['font_sha256'] == b['font_sha256'], 'Font changed between DLLs')
        d2.check(a['runtime_identity']['qt_gui_sha256'] != b['runtime_identity']['qt_gui_sha256'], 'DLL was not rebuilt')
        d2.check(sum(p['original_mismatches'] for p in a['processes']) > 0, 'Baseline defect missing')
        binding = d2.load_binding(prepared, sha)
        for spec in SPECS:
            directories = [root / (k + '-probe') / label(spec) for k in ('baseline', 'patched')]
            rows = [records(d / 'd2.jsonl') for d in directories]
            for rr, kind in zip(rows, ('baseline', 'patched')):
                validate_control(rr, sha, a['font_sha256'], binding, kind)
            compare_control_rows(*rows)
            for ar, br in zip(rows[0][1:-1], rows[1][1:-1]):
                d2.check(verify_pixels(directories[0], ar) == verify_pixels(directories[1], br), 'Raster bytes differ')
        report.update(d1=compare_d1(root, sha), patch=proof,
                      baseline_runtime=a['runtime_identity'], patched_runtime=b['runtime_identity'],
                      source_built_control_pairs=48, compared_observations=576, decoded_pngs=1152,
                      baseline_path_mismatches=sum(p['original_mismatches'] for p in a['processes']),
                      patched_path_mismatches=sum(p['original_mismatches'] for p in b['processes']),
                      status='PASS_PATCHED_QT_SYNTHETIC', original_ttc='NOT_RUN', qt_quick_ui='NOT_RUN')
    except Exception as exc:
        report['error'] = str(exc)
    save(root / 'patched-qt-analysis.json', report)
    print(json.dumps(report))
    d2.check(report['status'] == 'PASS_PATCHED_QT_SYNTHETIC', report.get('error', 'Failed'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('apply')
    for name in ('qt', 'prepared', 'patch', 'proof'): p.add_argument(name, type=Path)
    p.add_argument('sha')
    p = sub.add_parser('probe')
    for name in ('exe', 'font', 'out', 'prepared', 'prefix'): p.add_argument(name, type=Path)
    p.add_argument('sha'); p.add_argument('kind', choices=('baseline', 'patched'))
    p = sub.add_parser('compare')
    for name in ('root', 'prepared'): p.add_argument(name, type=Path)
    p.add_argument('sha')
    args = vars(parser.parse_args())
    command = args.pop('command')
    for name, value in list(args.items()):
        if isinstance(value, Path): args[name] = value.resolve()
    {'apply': apply_patch, 'probe': probe, 'compare': compare}[command](**args)
