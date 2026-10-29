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
    content = path.read_bytes().replace(b'\r\n', b'\n') if path.is_file() else b''
    for replacement in entry.get('allowed_replacements', []):
        before, after = (replacement[key].encode('utf-8') for key in ('before', 'after'))
        # The only accepted edit is this exact backend-only expression; all
        # geometry and other content must still equal the approved UI source.
        if content.count(after) != 1 or before in content:
            changed.append(entry['path'])
        content = content.replace(after, before)
    if not path.is_file() or hashlib.sha256(content).hexdigest() != entry['sha256']:
        changed.append(entry['path'])
print(json.dumps({'baseline': manifest['source_sha'], 'protected_files': len(manifest['protected_files']),
                  'changed': changed, 'scope': 'source preservation; visual/device acceptance is separate'}, indent=2))
raise SystemExit(bool(changed))
