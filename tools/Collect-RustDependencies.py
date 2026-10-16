"""Generate pinned dependency metadata and preserve registry license notices."""
import argparse
import json
from pathlib import Path
import shutil

p=argparse.ArgumentParser()
p.add_argument('--metadata',required=True)
p.add_argument('--inventory',required=True)
p.add_argument('--notices',required=True)
a=p.parse_args()
metadata=json.loads(Path(a.metadata).read_text(encoding='utf-8-sig'))
root=Path(a.notices);root.mkdir(parents=True,exist_ok=True)
rows=[]
for package in metadata['packages']:
    if not package['source']:continue
    folder=Path(package['manifest_path']).parent
    destination=root/(package['name']+'-'+package['version']);destination.mkdir(exist_ok=True)
    notices=[]
    # Include nested notices too (e.g. ring's C/assembly upstream licenses).
    for path in folder.rglob('*'):
        if path.is_file() and (path.name.upper().startswith(('LICENSE','COPYING','NOTICE','COPYRIGHT')) or path.name.endswith('.LICENSE')):
            relative=path.relative_to(folder);target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,target);notices.append(str(relative).replace('\\','/'))
    rows.append({'name':package['name'],'version':package['version'],'license':package.get('license'),
                 'source':package['source'],'repository':package.get('repository'),'notices':sorted(notices)})
Path(a.inventory).write_text(json.dumps({'scope':'Cargo.lock resolved dependencies, including target-specific and build dependencies','packages':sorted(rows,key=lambda r:r['name'])},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'packages':len(rows),'packagesWithNotices':sum(bool(r['notices']) for r in rows)}))
