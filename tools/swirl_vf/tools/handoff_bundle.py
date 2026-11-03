"""Portable, hash-verified private Mac reference bundle, schema 1.

Only explicit normalized DESIGN coordinates are accepted by the evaluator.
Raw avar records and the unaccepted user-map hypothesis remain separate.
No pickle, CoreText, Apple library, absolute source path or network is used.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath

import numpy as np
from fontTools.ttLib import TTCollection

from batch_geometry import BatchGeometry
from hvf import HVGL
from source_metrics import SourceMetrics


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def write_rows(path, rows):
    """Bounded, deterministic gzip JSONL; every float retains binary64 precision."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, allow_nan=False,
                                         separators=(',', ':'))+'\n').encode('utf-8'))
                count += 1
    return {'path': path.name, 'rows': count, 'bytes': path.stat().st_size, 'sha256': digest(path)}


def read_rows(path):
    # Reject JSON non-finite literals, including the stdlib's permissive defaults.
    def invalid(value):
        raise ValueError('nonfinite_json_number:'+value)
    with gzip.open(path, 'rb') as stream:
        while line := stream.readline(32*1024*1024+1):
            require(len(line) <= 32*1024*1024 and line.endswith(b'\n'), 'oversized_or_unterminated_record')
            row = json.loads(line, parse_constant=invalid)
            require(type(row) is dict, 'record_must_be_object')
            yield row


def relative_file(root, name):
    """Use the same path policy on Windows and POSIX, without archive extraction."""
    require(type(name) is str and name and '\\' not in name and ':' not in name,
            'invalid_relative_path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and str(path) == name
            and all(part not in ('', '.', '..') for part in path.parts), 'unsafe_relative_path')
    target = Path(root).joinpath(*path.parts)
    require(not any(part.is_symlink() for part in (target, *target.parents)), 'symlink_not_allowed')
    require(target.resolve().is_relative_to(Path(root).resolve()), 'path_outside_bundle')
    return target


def seal(root):
    root = Path(root).resolve(strict=True)
    require(not (root/'manifest.json').exists(), 'bundle_already_sealed')
    entries = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'bundle_symlink')
        if path.is_file():
            name = path.relative_to(root).as_posix()
            relative_file(root, name)
            entries[name] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    require('package.json' in entries, 'package_metadata_missing')
    write_json(root/'manifest.json', {'schema': 1, 'algorithm': 'sha256', 'files': entries})
    return verify(root)


def verify(root):
    root = Path(root).resolve(strict=True)
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    require(manifest.get('schema') == 1 and manifest.get('algorithm') == 'sha256'
            and type(manifest.get('files')) is dict, 'unsupported_manifest')
    actual = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'bundle_symlink')
        if path.is_file() and path != root/'manifest.json':
            actual.add(path.relative_to(root).as_posix())
    require(actual == set(manifest['files']), 'missing_or_unlisted_file')
    total = records = 0
    for name, entry in manifest['files'].items():
        path = relative_file(root, name)
        require(type(entry.get('bytes')) is int and entry['bytes'] >= 0
                and path.stat().st_size == entry['bytes'] and digest(path) == entry.get('sha256'),
                'file_integrity_failed:'+name)
        total += entry['bytes']
        if name.endswith('.jsonl.gz'):
            records += sum(1 for _ in read_rows(path))  # forces gzip CRC/trailer verification
    package = json.loads((root/'package.json').read_text(encoding='utf-8'))
    require(package.get('schema') == 1, 'unsupported_package')
    source = relative_file(root, package['source']['path'])
    require(digest(source) == package['source']['sha256'], 'source_identity_mismatch')
    catalog = json.loads(relative_file(root, package['catalog']).read_text(encoding='utf-8'))
    count = catalog['glyph_count']
    expected = 0
    for chunk in package['defaults']:
        require(chunk['start'] == expected and chunk['count'] > 0, 'default_chunk_gap')
        seen = 0
        for row in read_rows(relative_file(root, chunk['path'])):
            require(type(row.get('gid')) is int and row['gid'] == expected, 'default_gid_gap_or_duplicate')
            require(row.get('design') == [0., 0., 0.], 'default_coordinate_mismatch')
            expected += 1
            seen += 1
        require(seen == chunk['count'], 'default_chunk_count_mismatch')
    require(expected == count, 'incomplete_default_coverage')
    for face in catalog['faces']:
        n = 0
        for row in read_rows(relative_file(root, face['glyph_index'])):
            require(row['gid'] == n, 'face_gid_gap_or_duplicate')
            n += 1
        require(n == count, 'incomplete_face_index')
    return {'status': 'PASS', 'files': len(actual), 'payload_bytes': total,
            'jsonl_records': records, 'default_glyphs': expected,
            'faces': len(catalog['faces']), 'manifest_sha256': digest(root/'manifest.json')}


class Reference:
    """On-demand evaluator. Call verify once after transfer; source is always hashed."""
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.package = json.loads((self.root/'package.json').read_text(encoding='utf-8'))
        require(self.package.get('schema') == 1, 'unsupported_package')
        self.catalog = json.loads(relative_file(self.root, self.package['catalog']).read_text(encoding='utf-8'))
        source = relative_file(self.root, self.package['source']['path'])
        require(digest(source) == self.package['source']['sha256'], 'source_identity_mismatch')
        self.collection = TTCollection(source, lazy=True)
        self.states = {}

    def close(self):
        self.collection.close()

    def evaluate(self, face, gid, design):
        require(type(face) is int and face in [f['source_index'] for f in self.catalog['faces']], 'unknown_target_face')
        require(type(gid) is int and 0 <= gid < self.catalog['glyph_count'], 'invalid_gid')
        require(len(design) == 3 and all(type(v) in (int, float) and math.isfinite(v) and -1 <= v <= 1
                                       for v in design), 'invalid_design_location')
        font = self.collection.fonts[face]
        if face not in self.states:
            table = HVGL(font.reader['hvgl'], font.reader['hvpm'] if 'hvpm' in font else None)
            self.states[face] = BatchGeometry(table, isolated_tangents=True), SourceMetrics(font)
        renderer, metrics = self.states[face]
        root_axes = renderer.table.part(gid).axis_count
        batch = renderer.render(gid, [design[:root_axes]])
        return {'gid': gid, 'source_face': face, 'design': list(design),
                'coordinate_space': 'normalized_design_after_avar',
                'paths': [p[0].tolist() for p in batch.paths],
                'metrics': metrics.at(gid, dict(zip(('WDTH', 'wght', 'HGHT'), design))),
                'native_observation': False, 'continuous_space_acceptance': False}

    def default(self, gid):
        require(type(gid) is int and 0 <= gid < self.catalog['glyph_count'], 'invalid_gid')
        chunk = next(c for c in self.package['defaults'] if c['start'] <= gid < c['start']+c['count'])
        path = relative_file(self.root, chunk['path'])
        manifest = json.loads((self.root/'manifest.json').read_text(encoding='utf-8'))
        require(digest(path) == manifest['files'][chunk['path']]['sha256'], 'default_chunk_integrity_failed')
        for row in read_rows(path):
            if row['gid'] == gid:
                return row
        raise ValueError('default_record_missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify', 'evaluate', 'default'))
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--face', type=int, default=0, help='original TTC face index: 0,5,1,6')
    parser.add_argument('--gid', type=int, default=1166)
    parser.add_argument('--design', default='0,0,0', help='WDTH,wght,HGHT after avar, each [-1,1]')
    parser.add_argument('--output', type=Path, help='fresh private JSON output for geometry')
    args = parser.parse_args()
    if args.command == 'verify':
        print(json.dumps(verify(args.bundle)))
        return
    require(args.output is not None, 'explicit_private_output_required')
    require(not any((p/'.git').exists() for p in (args.output.absolute(), *args.output.absolute().parents)),
            'geometry_output_must_be_outside_git')
    reference = Reference(args.bundle)
    try:
        value = (reference.default(args.gid) if args.command == 'default' else
                 reference.evaluate(args.face, args.gid, [float(v) for v in args.design.split(',')]))
        write_json(args.output, value)
        print(json.dumps({'status': 'EXPORTED_PRIVATE', 'gid': args.gid}))
    finally:
        reference.close()


if __name__ == '__main__':
    main()
