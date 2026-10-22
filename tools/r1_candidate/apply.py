"""Apply a content-bound R1 candidate in an isolated CI checkout.

This helper creates no commit or ref and cannot push a branch. Its export mode
only uploads verified Git blobs; promotion is a separate compare-and-swap
connector operation after examining the actual test results.
"""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
BRANCH = 'refs/heads/work/rust-core-full-replacement-20261022'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def entries():
    result = []
    names = set()
    parts = sorted(Path(__file__).parent.glob('part-*.json'))
    require(len(parts) == 4, 'Four reviewed candidate parts required')
    for part in parts:
        document = json.loads(part.read_text('utf-8'))
        require(document['base_commit'] == '5a35bc3a1a0bef19837eda5db9c63f939f4b7e2d', 'Wrong candidate base')
        for row in document['entries']:
            name = row['path']
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in name,
                    'Unsafe candidate path')
            require(name.startswith(('src/Swirl.Quick/', 'scripts/', 'tools/', 'docs/', '.github/workflows/')),
                    'Candidate path is outside the review scope')
            require(not name.startswith('tools/r1_candidate/') and name not in names,
                    'Duplicate or self-modifying candidate path')
            local = ROOT / path
            require(local.resolve().is_relative_to(ROOT) and not local.is_symlink(), 'Linked candidate path')
            names.add(name)
            result.append(row)
    require(len(result) == 54, 'Unexpected candidate file count')
    return result


def apply(rows):
    prepared = []
    for row in rows:
        path = ROOT / row['path']
        old = path.read_bytes() if path.exists() else b''
        require((digest(old) if path.exists() else None) == row['before'],
                'Source changed before candidate application: ' + row['path'])
        if row['after'] is None:
            new = None
        else:
            new = old
            end = 0
            for start, stop, replacement in row['edits']:
                require(type(start) is int and type(stop) is int and end <= start <= stop <= len(old),
                        'Invalid or overlapping edit: ' + row['path'])
                require(isinstance(replacement, str), 'Replacement must be UTF-8 text')
                end = stop
            for start, stop, replacement in reversed(row['edits']):
                new = new[:start] + replacement.encode('utf-8') + new[stop:]
            require(digest(new) == row['after'], 'Candidate output mismatch: ' + row['path'])
        prepared.append((path, new))
    # Validate every input and output before changing any checkout file.
    for path, new in prepared:
        if new is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(new)
    print('Applied 54 content-verified files; no branch or commit changed.')


def export(rows):
    require(os.environ.get('GITHUB_REPOSITORY') == 'SOLHK/Swirl', 'Wrong repository')
    require(os.environ.get('GITHUB_REF') == BRANCH, 'Wrong branch')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(head == os.environ.get('GITHUB_SHA'), 'Checkout identity mismatch')
    token = os.environ.get('R1_BLOB_TOKEN')
    require(bool(token), 'Blob creation token is missing')
    tree = []
    for row in rows:
        path = ROOT / row['path']
        data = path.read_bytes() if path.exists() else None
        require((digest(data) if data is not None else None) == row['after'],
                'Candidate changed after validation: ' + row['path'])
        sha = None
        if data is not None:
            body = json.dumps({'encoding': 'base64', 'content': base64.b64encode(data).decode('ascii')}).encode()
            request = urllib.request.Request('https://api.github.com/repos/SOLHK/Swirl/git/blobs',
                data=body, method='POST', headers={'Authorization': 'Bearer ' + token,
                    'Content-Type': 'application/json', 'Accept': 'application/vnd.github+json',
                    'User-Agent': 'Swirl-R1-content-validation'})
            with urllib.request.urlopen(request, timeout=30) as response:
                require(response.status == 201, 'Blob creation failed')
                sha = json.load(response)['sha']
            require(sha == hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
                    'Git blob content mismatch')
        tree.append({'path': row['path'], 'mode': '100644', 'type': 'blob', 'sha': sha})
    result = {'candidate_commit': head, 'base_commit': '5a35bc3a1a0bef19837eda5db9c63f939f4b7e2d',
              'tree_elements': tree, 'checksums': [{'path': row['path'], 'sha256': row['after']} for row in rows],
              'note': 'Blob publication is not a test-pass claim. Check both candidate jobs before promotion.'}
    output = Path(os.environ['RUNNER_TEMP']) / 'r1-candidate-blobs.json'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Exported content-addressed blobs only; refs and commits were not changed.')


if __name__ == '__main__':
    require(len(sys.argv) == 2 and sys.argv[1] in ('apply', 'export'), 'Expected apply or export')
    {'apply': apply, 'export': export}[sys.argv[1]](entries())
