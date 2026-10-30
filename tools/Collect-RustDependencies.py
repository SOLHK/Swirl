"""Generate locked dependency metadata and stage registry/runtime notices."""
import argparse
import json
from pathlib import Path
import shutil

p = argparse.ArgumentParser()
p.add_argument('--metadata', required=True)
p.add_argument('--inventory', required=True)
p.add_argument('--notices', required=True)
p.add_argument('--supplemental-inventory', help='Reviewed inventory; defaults to the Cargo workspace DEPENDENCIES.json')
a = p.parse_args()
metadata = json.loads(Path(a.metadata).read_text(encoding='utf-8-sig'))
workspace = Path(metadata['workspace_root']).resolve()
supplemental_path = Path(a.supplemental_inventory) if a.supplemental_inventory else workspace / 'DEPENDENCIES.json'
# Read before writing: this can be the same path as --inventory during refresh.
reviewed = json.loads(supplemental_path.read_text(encoding='utf-8-sig'))
supplements = {
    (row['name'], row['version']): row
    for row in reviewed['packages']
    if row.get('supplemental_notices') or row.get('notice_sources')
}
resolved = {(row['name'], row['version']) for row in metadata['packages']}
stale = supplements.keys() - resolved
if stale:
    raise ValueError(f'Supplemental notices need review for removed or changed package versions: {sorted(stale)}')
root = Path(a.notices).resolve()
root.mkdir(parents=True, exist_ok=True)
extra_notices = set()


def copy_extra_notice(relative):
    """Keep reviewed core-relative paths valid inside the staged notice root."""
    if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative
            or any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ValueError(f'Unsafe supplemental notice path: {relative!r}')
    source = (workspace / relative).resolve()
    destination = (root / relative).resolve()
    # Reject absolute paths and symlinks escaping either allowed directory.
    source.relative_to(workspace)
    destination.relative_to(root)
    if not source.is_file():
        raise FileNotFoundError(f'Missing reviewed supplemental notice: {source}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    extra_notices.add(relative)


rows = []
for package in metadata['packages']:
    folder = Path(package['manifest_path']).resolve().parent
    source = package['source']
    if not source:
        # Cargo uses a null source for both workspace code and vendored crates.
        # Keep third-party path dependencies in the inventory and license copy.
        try:
            relative = folder.relative_to(workspace / 'vendor')
        except ValueError:
            continue
        source = 'vendored+vendor/' + relative.as_posix()
    destination = root / (package['name'] + '-' + package['version'])
    destination.mkdir(exist_ok=True)
    notices = set()
    # Include nested notices too (e.g. ring's C/assembly upstream licenses).
    for path in folder.rglob('*'):
        name = path.name.upper()
        if path.is_file() and (name.startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT', 'UNLICENSE'))
                               or name.endswith('.LICENSE')):
            path.resolve().relative_to(folder)
            relative = path.relative_to(folder)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            notices.add(relative.as_posix())
    if package.get('license_file'):
        path = (folder / package['license_file']).resolve()
        relative = path.relative_to(folder)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        notices.add(relative.as_posix())
    row = {'name': package['name'], 'version': package['version'], 'license': package.get('license'),
           'source': source, 'repository': package.get('repository'), 'notices': sorted(notices)}
    supplement = supplements.get((package['name'], package['version']), {})
    for key in ('notice_sources', 'supplemental_notices'):
        if key in supplement:
            row[key] = supplement[key]
    for notice in row.get('supplemental_notices', []):
        copy_extra_notice(notice)
    rows.append(row)

artifacts = reviewed.get('runtime_artifacts', [])
for artifact in artifacts:
    for notice in artifact['notices']:
        copy_extra_notice(notice)
result = {
    'scope': 'Cargo.lock resolved dependencies, including target-specific and build dependencies; separately distributed runtime artifacts are listed independently',
    'packages': sorted(rows, key=lambda row: (row['name'], row['version'])),
    'runtime_artifacts': artifacts,
}
Path(a.inventory).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'packages': len(rows), 'packagesWithNotices': sum(bool(row['notices']) for row in rows),
                  'runtimeArtifacts': len(artifacts), 'extraNotices': len(extra_notices)}))
