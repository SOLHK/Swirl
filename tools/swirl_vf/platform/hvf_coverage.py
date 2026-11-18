#!/usr/bin/env python3
"""Resumable, private, complete-GID Apple HVF extraction at fixed design points.

Reuses the existing native oracle and run_hvf_oracle driver. This is an outline
checkpoint, never a converted font, a user-axis calibration or metric acceptance.
Each completed chunk is checked again before reuse; failed chunks remain failed.
The default plan covers all 27 min/default/max design-coordinate combinations.
"""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import os
from pathlib import Path
import platform

from fontTools.ttLib import TTCollection

import run_hvf_oracle as driver
from hvf_transcript import validate_transcript


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    temporary = path.with_suffix('.pending')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def plan(source, binary, face, batch_size, positions):
    require(type(face) is int and face >= 0 and type(batch_size) is int and batch_size > 0,
            'nonnegative face and positive batch size required')
    with TTCollection(source, lazy=True) as collection:
        require(face < len(collection.fonts), 'source face index out of range')
        font = collection.fonts[face]
        axes = [a.axisTag for a in font['fvar'].axes]
        require(axes == ['WDTH', 'wght', 'HGHT'] and 'hvgl' in font,
                'three-axis HVGL source required')
        glyphs = font['maxp'].numGlyphs
        require(glyphs > 0, 'empty source face')
        shared = [i for i, f in enumerate(collection.fonts)
                  if f.reader.tables['hvgl'].offset == font.reader.tables['hvgl'].offset
                  and f.reader.tables['hvgl'].length == font.reader.tables['hvgl'].length]
    coords = list(itertools.product((-1., 0., 1.), repeat=3)) if positions == 'grid27' else [(0., 0., 0.)]
    root = Path(__file__).parent
    return {'source_sha256': driver.sha256(source), 'source_bytes': source.stat().st_size,
            'binary_sha256': driver.sha256(binary), 'face_index': face, 'glyph_count': glyphs,
            'same_source_hvgl_byte_range_faces': shared, 'axes': axes,
            'coordinate_space': 'normalized_design_after_avar', 'positions': [list(v) for v in coords],
            'batch_size': batch_size, 'platform': platform.platform(),
            'code_sha256': {name: driver.sha256(root / name) for name in
                           ('hvf_coverage.py', 'hvf_transcript.py', 'run_hvf_oracle.py', 'hvf_oracle.c')}}


def chunks(recipe):
    for position, coords in enumerate(recipe['positions']):
        for start in range(0, recipe['glyph_count'], recipe['batch_size']):
            yield f'p{position:02d}-g{start:05d}', coords, start, min(recipe['batch_size'], recipe['glyph_count']-start)


def checked_chunk(directory, recipe, coords, start, count):
    report = json.loads((directory / 'hvf-run.json').read_text())
    outline = directory / 'hvf-outlines.jsonl'
    require(report['input']['sha256'] == report['input_sha256_after'] == recipe['source_sha256']
            and report['input_unchanged'] is True and report['binary_sha256'] == recipe['binary_sha256']
            and report['source_sha256'] == recipe['code_sha256']['hvf_oracle.c']
            and report['outline_sha256'] == driver.sha256(outline), 'chunk identity/hash changed')
    checked = validate_transcript(outline, face=recipe['face_index'], coords=coords, start=start,
                                  count=count, parts=False, input_bytes=recipe['source_bytes'])
    require(all(report.get(k) == v for k, v in checked.items()), 'chunk receipt differs from native transcript')
    return {'status': report['status'], 'runtime_exit_code': report['runtime_exit_code'],
            'report_sha256': driver.sha256(directory / 'hvf-run.json'),
            'outline_sha256': report['outline_sha256'], 'glyph_records': checked['counts']['outlines'],
            'failed_outlines': checked['counts']['failed_outlines'], 'empty_outlines': checked['empty_outlines'],
            'callback_counts': checked['callback_counts']}


def summary(recipe, rows):
    total = len(recipe['positions']) * recipe['glyph_count']
    observed = sum(r.get('glyph_records', 0) for r in rows.values())
    failed = sum(r['status'] != 'EXTRACTED' for r in rows.values())
    complete = len(rows) == sum(1 for _ in chunks(recipe))
    return {'status': 'FAILED' if failed else 'EXTRACTED_FINITE_DESIGN_GRID' if complete else 'IN_PROGRESS',
            'planned_native_glyph_records': total, 'native_glyph_records': observed,
            'failed_chunks': failed, 'completed_chunks': len(rows),
            'source_face_index': recipe['face_index'], 'glyphs_per_position': recipe['glyph_count'],
            'positions': len(recipe['positions']), 'metrics': 'NOT_EXTRACTED',
            'user_axis_mapping': 'NOT_TESTED', 'continuous_variation_proof': False,
            'font_generated': False, 'production_accepted': False}


def run(source, binary, output, face=0, batch_size=1024, positions='grid27', max_chunks=None):
    require(platform.system() == 'Darwin', 'Apple HVF coverage NOT_RUN: macOS required')
    require(positions in ('grid27', 'default') and (max_chunks is None or max_chunks > 0), 'invalid coverage plan')
    source, binary = Path(source).resolve(strict=True), Path(binary).resolve(strict=True)
    output = Path(output).absolute()
    require(not output.is_symlink() and not source.is_relative_to(output)
            and not binary.is_relative_to(output), 'separate non-symlink output required')
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    import fcntl
    lock = os.open(output / '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        recipe = plan(source, binary, face, batch_size, positions)
        path = output / 'checkpoint.json'
        if path.exists():
            checkpoint = json.loads(path.read_text())
            require(checkpoint['recipe'] == recipe, 'source/tool/plan changed; choose a new checkpoint')
        else:
            require(set(p.name for p in output.iterdir()) == {'.lock'}, 'unrelated existing output directory')
            checkpoint = {'recipe': recipe, 'rows': {}, 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
            save(path, checkpoint)
        rows = checkpoint['rows']
        require(set(rows) <= {key for key, *_ in chunks(recipe)}, 'unexpected checkpoint chunks')
        completed_now = 0
        for key, coords, start, count in chunks(recipe):
            directory = output / key
            if key in rows:
                # A prior failed attempt is not retried silently or counted as a pass.
                if rows[key]['status'] == 'EXTRACTED':
                    require(rows[key] == checked_chunk(directory, recipe, coords, start, count),
                            'checkpoint chunk changed')
                continue
            if max_chunks is not None and completed_now >= max_chunks:
                break
            require(driver.sha256(source) == recipe['source_sha256']
                    and driver.sha256(binary) == recipe['binary_sha256'], 'source/oracle changed during coverage')
            try:
                if not directory.exists():
                    args = argparse.Namespace(font=source, binary=binary, out=directory, face=face,
                        coords=','.join(map(str, coords)), start=start, count=count, parts=False, timeout=300.)
                    driver.run(args)
                rows[key] = checked_chunk(directory, recipe, coords, start, count)
            except (OSError, ValueError, KeyError) as error:
                rows[key] = {'status': 'FAILED', 'error_type': type(error).__name__, 'reason': str(error)}
            completed_now += 1
            checkpoint['summary'] = summary(recipe, rows)
            checkpoint['updated_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
            save(path, checkpoint)
        checkpoint['summary'] = summary(recipe, rows)
        save(path, checkpoint)
        print(json.dumps(checkpoint['summary']), flush=True)
        return 0 if checkpoint['summary']['status'] == 'EXTRACTED_FINITE_DESIGN_GRID' else 2
    finally:
        os.close(lock)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='private directory outside public repository')
    parser.add_argument('--face', type=int, default=0)
    parser.add_argument('--batch-size', type=int, default=1024)
    parser.add_argument('--positions', choices=('grid27', 'default'), default='grid27')
    parser.add_argument('--max-chunks', type=int)
    raise SystemExit(run(**vars(parser.parse_args())))
