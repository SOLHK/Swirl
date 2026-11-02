#!/usr/bin/env python3
"""Isolate CFF2 DirectWrite rejection using bounded, authored font controls.

Collection variants retain both authored faces, all GIDs and WDTH/wght/HGHT.
One additional control isolates face 0 in a standalone file. Alternative
serializations do not grant acceptance. The separate strict native gate stays
in place; this matrix continues after a failed case to preserve the evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile

from fontTools.cffLib import FDSelect
from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTCollection

from make_cff2_fixture import write_fixture

VARIANTS = ('flat', 'flat_standalone', 'flat_stat', 'flat_fdselect',
            'flat_private_vsindex', 'flat_default_vsindex', 'flat_post3', 'factored')


def generate(output):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    rows = []
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        flat = Path(tmp) / 'flat.ttc'; write_fixture(flat)
        for variant in VARIANTS:
            path = output / (variant + ('.otf' if variant == 'flat_standalone' else '.ttc'))
            if variant == 'factored':
                write_fixture(path, factored=True)
            else:
                with TTCollection(flat, recalcTimestamp=False) as collection:
                    for font in collection.fonts:
                        top = font['CFF2'].cff.topDictIndex[0]
                        if variant == 'flat_stat':
                            buildStatTable(font, [{'tag': a.axisTag, 'name': a.axisNameID,
                                'ordering': i} for i, a in enumerate(font['fvar'].axes)])
                        elif variant == 'flat_fdselect':
                            top.FDSelect = FDSelect(format=0)
                            top.FDSelect.gidArray = [0] * len(font.getGlyphOrder())
                        elif variant == 'flat_private_vsindex':
                            top.FDArray[0].Private.vsindex = 0
                        elif variant == 'flat_default_vsindex':
                            for cs in top.CharStrings.values():
                                cs.decompile()
                                if cs.program[:2] == [0, 'vsindex']:
                                    cs.program = cs.program[2:]; cs.bytecode = None
                        elif variant == 'flat_post3':
                            font['post'].formatType = 3.0
                    if variant == 'flat_standalone':
                        collection.fonts[0].save(path)
                    else:
                        collection.save(path)
            rows.append({'variant': variant, 'file': path.name,
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'bytes': path.stat().st_size})
    (output / 'generated.json').write_text(json.dumps(rows, indent=2))
    return rows


def run(output, binary):
    if platform.system() != 'Windows':
        raise RuntimeError('DirectWrite CFF2 diagnosis NOT_RUN: Windows required')
    output, binary = Path(output), Path(binary).resolve(strict=True)
    generated = generate(output / 'fonts')
    report = {'status': 'IN_PROGRESS', 'platform': platform.platform(), 'cases': [],
              'scope': 'authored structural controls; not original-font or Windows 11 acceptance',
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'production_accepted': False}
    try:
        for row in generated:
            directory = output / row['variant']
            command = ['pwsh', '-NoProfile', '-File', str(Path(__file__).with_name('run_directwrite_probe.ps1')),
                '-Font', str(output / 'fonts' / row['file']), '-OutputDirectory', str(directory),
                '-Binary', str(binary), '-AllGlyphs', '-Render']
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
            (output / (row['variant'] + '.log')).write_text(result.stdout + result.stderr)
            native = json.loads((directory / 'directwrite-run.json').read_text(encoding='utf-8-sig'))
            if native['input_sha256'] != row['sha256'] or native.get('input_unchanged') is not True:
                raise AssertionError('CFF2 diagnosis input identity changed')
            transcript = [json.loads(line) for line in (directory / 'directwrite.jsonl').read_text().splitlines()]
            report['cases'].append(dict(row, exit_code=result.returncode, native=native,
                face_results=[r for r in transcript if r.get('record') == 'face_result'],
                default_geometry=[r for r in transcript if r.get('record') == 'instance' and r.get('case') == 'default']))
            (output / 'matrix.json').write_text(json.dumps(report, indent=2))
        report['status'] = 'DIAGNOSIS_COMPLETE_NOT_ACCEPTANCE'
    except Exception as error:
        report['status'] = 'FAIL_EXECUTION'; report['error'] = str(error)
        raise
    finally:
        (output / 'matrix.json').write_text(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--generate-only', action='store_true')
    args = parser.parse_args()
    if args.generate_only:
        print(json.dumps(generate(args.output), indent=2))
    else:
        if not args.binary: parser.error('--binary is required for native execution')
        report = run(args.output, args.binary)
        print(json.dumps({'status': report['status'], 'native_exit_codes': {
            row['variant']: row['exit_code'] for row in report['cases']}}, indent=2))
