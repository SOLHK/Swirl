"""Guard the user-approved U2 geometry, glass, navigation and animation sources."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'docs/handoffs/s3-ui-baseline.json').read_text('utf-8'))
changed = []
for entry in manifest['protected_files']:
    path = ROOT / entry['path']
    # Git uses LF for source identity, including Windows checkouts with CRLF.
    if not path.is_file() or hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != entry['sha256']:
        changed.append(entry['path'])
print(json.dumps({'baseline': manifest['source_sha'], 'protected_files': len(manifest['protected_files']),
                  'changed': changed, 'scope': 'source preservation; visual/device acceptance is separate'}, indent=2))
raise SystemExit(bool(changed))
