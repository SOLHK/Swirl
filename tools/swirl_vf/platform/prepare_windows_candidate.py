"""Prepare an offline Windows test kit next to a private candidate, no uploads."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from windows_font_inventory import sha256
from windows_font_builder import FACE_PLAN
from windows_gvar import require


def prepare(candidate, artifacts):
    candidate, artifacts = candidate.resolve(), artifacts.resolve()
    build = json.loads((candidate.parent/'report.json').read_text())
    require(sha256(candidate) == build['sha256'], 'candidate_hash_mismatch')
    output = candidate.parent/'windows-test'
    require(not output.exists() and not any((p/'.git').exists() for p in (output, *output.parents)), 'fresh_private_kit_required')
    output.mkdir(mode=0o700)
    plan = dict(candidate_sha256=build['sha256'], version=build['version'], faces=[], binaries=[], requests=0,
                original_font_acceptance=False, Windows_DirectWrite='NOT_RUN')
    requests = []
    with TTCollection(candidate, lazy=True) as collection:
        for index, (_, label) in enumerate(FACE_PLAN):
            font = collection.fonts[index]
            cmap = font.getBestCmap()
            codepoints = {ord(c): font.getGlyphID(cmap[ord(c)]) for c in '中文國體龍鬱永AaWg019，。！？（）' if ord(c) in cmap}
            gids = set(codepoints.values()) | {build['source_gids'].index(g) for g in (0, 1166, 19177) if g in build['source_gids']}
            default = {a.axisTag: float(a.defaultValue) for a in font['fvar'].axes}
            positions = [default]
            for tag, values in [('wght', (100, 300, 400, 500, 600, 700, 900)), ('wdth', (80, 90, 110, 120)), ('HGHT', (1, 250, 750, 1000))]:
                positions.extend(default | {tag: float(v)} for v in values)
            positions.extend([dict(wdth=90., wght=650., HGHT=800.), dict(wdth=112., wght=350., HGHT=300.),
                              dict(wdth=99.5, wght=500.5, HGHT=500.5)])
            for position in positions:
                for gid in sorted(gids):
                    values = [float(np.float32(position[t])) for t in ('wdth', 'wght', 'HGHT')]
                    requests.append(' '.join(map(str, [len(requests), index, gid, *values])))
            plan['faces'].append(dict(face=label, glyphs=font['maxp'].numGlyphs, unicode_probes=codepoints,
                glyphs_sampled=len(gids), positions=len(positions),
                line_metrics=dict(ascent=font['hhea'].ascent, descent=-font['hhea'].descent, line_gap=font['hhea'].lineGap)))
    for name, relative in [('observe.exe', 'observe.exe'), ('medium.exe', 'medium.exe'),
                           ('directwrite_probe.exe', 'native/build/Release/directwrite_probe.exe')]:
        source = artifacts/relative
        require(source.is_file(), 'missing_prebuilt_Windows_probe')
        shutil.copyfile(source, output/name)
        plan['binaries'].append(dict(file=name, sha256=sha256(output/name)))
    plan['requests'] = len(requests)
    (output/'requests.txt').write_text('\n'.join(requests)+'\n')
    plan['requests_sha256'] = sha256(output/'requests.txt')
    (output/'plan.json').write_text(json.dumps(plan, indent=2))
    shutil.copyfile(Path(__file__).with_name('run_windows_candidate.ps1'), output/'Run-Windows-Test.ps1')
    (output/'README.txt').write_text(
        'Copy SwirlVF.ttc and the windows-test directory together to Windows 11. No font upload is needed.\n'
        'In PowerShell, run: .\\windows-test\\Run-Windows-Test.ps1\n'
        'Keep results private: they contain outline coordinates. The script records DirectWrite loading,\n'
        'Medium selection, all requested axis positions, Unicode probes and raster samples.\n'
        'It does not assert desktop installation or visual acceptance. Persistent installation and\n'
        'normal-application visual review remain separate checks. The strict historical failure is retained.\n')
    print(json.dumps(dict(kit=str(output), requests=len(requests), candidate_sha256=build['sha256'])))
    return plan


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', required=True, type=Path)
    p.add_argument('--artifacts', required=True, type=Path)
    a = p.parse_args()
    prepare(a.candidate, a.artifacts)
