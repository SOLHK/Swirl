#!/usr/bin/env python3
"""Aggregate serialized resource accounting; never output font coordinates."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
from fontTools.ttLib import TTFont
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from cff2_structure import programs, bytecode, structural_runs, program_stats


def profile(path, *, instructions=False):
    started = time.monotonic()
    with path.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
    with TTFont(path, lazy=True) as font:
        cff = font['CFF2'].cff; top = cff.topDictIndex[0]
        top.VarStore.compile()
        store_bytes=len(top.VarStore.data)
        report = dict(font_sha256=digest, file_bytes=path.stat().st_size,
            tables={tag: entry.length for tag, entry in font.reader.tables.items()},
            glyphs=len(font.getGlyphOrder()), axes=len(font['fvar'].axes),
            flagged_hidden_axes=sum(bool(a.flags & 1) for a in font['fvar'].axes),
            computational_axes=len(font['fvar'].axes)-3,
            cff2_regions=len(top.VarStore.otVarStore.VarRegionList.Region),
            cff2_data_sets=len(top.VarStore.otVarStore.VarData),
            cff2_variation_store_payload_bytes=store_bytes,
            cff2_variation_store_length_sentinel=store_bytes>=65535,
            avar2_regions=len(font['avar'].table.VarStore.VarRegionList.Region) if font['avar'].majorVersion==2 else 0,
            font_dicts=len(top.FDArray), program_categories={})
        patterns = Counter(); totals = Counter()
        for kind, _, cs in programs(font):
            data = bytecode(cs)
            stats = report['program_categories'].setdefault(kind, dict(count=0,bytes=0,maximum_bytes=0))
            stats['count'] += 1; stats['bytes'] += len(data)
            stats['maximum_bytes'] = max(stats['maximum_bytes'], len(data))
            if instructions:
                totals.update(program_stats(data))
                patterns.update(data[a:b] for a,b in structural_runs(data))
        report['cff2_program_payload_bytes'] = sum(v['bytes'] for v in report['program_categories'].values())
        report['cff2_other_bytes'] = report['tables']['CFF2']-report['cff2_program_payload_bytes']
        if instructions:
            useful=sorted(((len(p)-2)*n-len(p)-4,len(p),n) for p,n in patterns.items())
            report['instructions']=dict(totals)
            report['structural_runs']=dict(unique=len(patterns),occurrences=sum(patterns.values()),
                best_215_net_bytes=sum(max(0,x[0]) for x in useful[-215:]),
                lengths=dict(Counter({str(k):sum(n for p,n in patterns.items() if len(p)==k) for k in sorted({len(p) for p in patterns})})))
    report.update(seconds=time.monotonic()-started, peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('font',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--instructions',action='store_true');a=p.parse_args()
    r=profile(a.font,instructions=a.instructions);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
