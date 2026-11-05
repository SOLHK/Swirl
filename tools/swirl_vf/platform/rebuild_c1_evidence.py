#!/usr/bin/env python3
"""Archive committed C1 source only; never include fonts, samples or checkpoints.

Reads immutable Git objects, not working-tree content. This is provenance for
reproducing tests, not a font, a production gate, or a test-success assertion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile

SUFFIXES = frozenset({'.py', '.md', '.swift', '.cpp', '.h', '.hpp', '.c', '.cc',
                      '.yml', '.yaml', '.toml', '.txt', '.sh', '.ps1'})
WORKFLOW = '.github/workflows/swirl-vf-rebuild-c1.yml'


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(repo), *args],
                                   stderr=subprocess.PIPE)


def _selected(name: str) -> bool:
    p = PurePosixPath(name)
    return (not p.is_absolute() and '..' not in p.parts
            and p.suffix.lower() in SUFFIXES
            and (name.startswith('tools/swirl_vf/')
                 or name.startswith('docs/SWIRL_VF_') or name == WORKFLOW))


def _member(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data)


def write_source_snapshot(repo: Path, destination: Path, revision: str = 'HEAD', *,
                          max_file_bytes: int = 4 * 1024 * 1024,
                          max_total_bytes: int = 32 * 1024 * 1024) -> dict:
    """Return exact source identity after no-clobber publication of a ZIP.

    Limits bound input buffers, not whole-process RSS. JSON/JSONL, binary data,
    generated files, untracked files and edited working-tree bytes are excluded.
    Directory fsync is available on POSIX; no Windows power-loss claim is made.
    """
    for limit in (max_file_bytes, max_total_bytes):
        if type(limit) is not int or limit <= 0:
            raise ValueError('source_budget_invalid')
    repo, destination = Path(repo), Path(destination)
    commit = _git(repo, 'rev-parse', '--verify', '--end-of-options',
                  revision + '^{commit}').decode('ascii').strip()
    tree = _git(repo, 'rev-parse', commit + '^{tree}').decode('ascii').strip()
    entries = []
    total = 0
    records = _git(repo, 'ls-tree', '-r', '-z', commit, '--',
                   'tools/swirl_vf', 'docs', WORKFLOW).split(b'\0')
    for record in filter(None, records):
        metadata, raw_name = record.split(b'\t', 1)
        name = raw_name.decode('utf-8')
        if not _selected(name):
            continue
        mode, kind, oid = metadata.decode('ascii').split()
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('source_not_regular_blob')
        size = int(_git(repo, 'cat-file', '-s', oid))
        total += size
        if size > max_file_bytes or total > max_total_bytes:
            raise ValueError('source_budget_exceeded')
        entries.append((name, oid, size))
    if not entries:
        raise ValueError('source_snapshot_empty')
    if len(entries) > 10000:
        raise ValueError('source_file_count_exceeded')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('source_destination_exists')
    fd, temporary = tempfile.mkstemp(prefix='.c1-source-', suffix='.tmp',
                                     dir=destination.parent)
    manifest = {'schema': 'swirl-vf-c1-public-source-v1', 'source_commit': commit,
                'source_tree': tree, 'source_only': True, 'font_generated': False,
                'production_acceptance': False, 'files': []}
    try:
        with os.fdopen(fd, 'w+b') as stream:
            with zipfile.ZipFile(stream, 'w') as archive:
                for name, oid, size in sorted(entries):
                    data = _git(repo, 'cat-file', 'blob', oid)
                    if len(data) != size:
                        raise ValueError('source_size_changed')
                    data.decode('utf-8')
                    if b'\0' in data:
                        raise ValueError('source_not_text')
                    _member(archive, name, data)
                    manifest['files'].append({'path': name, 'git_blob': oid,
                                              'bytes': size,
                                              'sha256': hashlib.sha256(data).hexdigest()})
                _member(archive, 'C1_SOURCE_MANIFEST.json',
                        (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode())
            stream.flush()
            os.fsync(stream.fileno())
        # A competing publisher cannot replace already confirmed evidence.
        os.link(temporary, destination)
        if os.name == 'posix':
            directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', default='HEAD')
    args = parser.parse_args()
    result = write_source_snapshot(args.repo, args.output, args.revision)
    # Never echo arbitrary file paths or a false test/production success claim.
    print(json.dumps({k: result[k] for k in ('schema', 'source_commit',
                     'source_tree', 'source_only', 'font_generated',
                     'production_acceptance')} | {'file_count': len(result['files'])},
                     sort_keys=True))


if __name__ == '__main__':
    main()
