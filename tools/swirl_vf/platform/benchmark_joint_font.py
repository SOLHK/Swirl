#!/usr/bin/env python3
"""Isolated native performance/usage checks; independent accuracy is separate."""
import argparse,hashlib,json,resource,subprocess,sys,time
from pathlib import Path
import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from projection_research import fresh_private
from probe_projection_candidate import declared_user_location
from p7_validate_candidate import commands


def statistics(values):
    return dict(count=len(values),sum_seconds=sum(values),minimum_seconds=min(values),
                p50_seconds=float(np.median(values)),p95_seconds=float(np.percentile(values,95)))


def harfbuzz(config):
    started=time.perf_counter();blob=Path(config['font_path']).read_bytes();read=time.perf_counter()-started
    assert hashlib.sha256(blob).hexdigest()==config['font_sha256']
    started=time.perf_counter();font=hb.Font(hb.Face(blob));hb.ot_font_set_funcs(font);font.scale=(config['upm']*64,)*2
    loaded=time.perf_counter()-started;reference=[];omitted=direct=0;measurements=[]
    for explicit in (True,False):
        instances=[];shapes=[];draws=[]
        for i,location in enumerate(config['locations']):
            coords=dict(config['defaults']) if explicit else {};coords.update(location)
            start=time.perf_counter();font.set_variations(coords);instances.append(time.perf_counter()-start)
            start=time.perf_counter();b=hb.Buffer();b.add_str('A');b.guess_segment_properties();hb.shape(font,b);shapes.append(time.perf_counter()-start)
            assert len(b.glyph_infos)==1;gid=b.glyph_infos[0].codepoint
            start=time.perf_counter();outline=commands(font,gid);draws.append(time.perf_counter()-start)
            signature=(gid,outline)
            if explicit:
                reference.append(signature);direct+=commands(font,config['base_gid'])!=outline
            else:omitted+=signature!=reference[i]
        measurements.append(dict(explicit_hidden_defaults=explicit,font_instance_seconds=instances,shaping_seconds=shapes,outline_seconds=draws))
    return dict(engine='HarfBuzz',version=hb.version_string(),read_seconds=read,graphics_load_seconds=loaded,
        requests_per_mode=len(config['locations']),measurements=measurements,omitted_hidden_default_mismatches=omitted,
        unshaped_base_outline_mismatches=direct,accuracy_acceptance=False,font_sha256=config['font_sha256'],
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))


def run(args):
    if args.child:
        print(json.dumps(harfbuzz(json.loads(args.child.read_text()))));return
    out=fresh_private(args.private_output)
    with TTFont(args.font,lazy=True) as font:
        axes=font['fvar'].axes;rng=np.random.default_rng(args.seed)
        locations=[declared_user_location({a.axisTag:round(float(x)*8192)/8192
            for a,x in zip(axes,rng.uniform([a.minValue for a in axes[:3]],[a.maxValue for a in axes[:3]]))}) for _ in range(args.samples)]
        config=dict(font_path=str(args.font.resolve()),font_sha256=hashlib.sha256(args.font.read_bytes()).hexdigest(),
            locations=locations,defaults={a.axisTag:a.defaultValue for a in axes},upm=font['head'].unitsPerEm,
            base_gid=font.getGlyphID(font.getBestCmap()[65]))
    path=out/'manifest.json';path.write_text(json.dumps(config))
    binary=args.coretext_binary
    if not binary and sys.platform=='darwin':
        binary=out/'coretext-benchmark'
        subprocess.run(['swiftc','-O',str(Path(__file__).with_name('benchmark_joint_layout.swift')),'-o',str(binary)],check=True,capture_output=True)
    report=dict(font_sha256=config['font_sha256'],font_bytes=args.font.stat().st_size,seed=args.seed,
        samples=args.samples,repetitions=args.repeats,cold_processes=True,OS_file_cache_controlled=False,
        production_accepted=False,accuracy_acceptance=False,engines={})
    for engine in ('HarfBuzz','CoreText'):
        if engine=='CoreText' and not binary:report['engines'][engine]='NOT_RUN';continue
        rows=[]
        for repeat in range(args.repeats):
            command=[sys.executable,__file__,'--child',str(path)] if engine=='HarfBuzz' else [str(binary),str(path)]
            result=subprocess.run(command,capture_output=True,text=True)
            (out/f'{engine}-{repeat}.stderr.log').write_text(result.stderr);result.check_returncode()
            row=json.loads(result.stdout)
            for mode in row['measurements']:
                for key in ('font_instance_seconds','shaping_seconds','outline_seconds'):mode[key]=statistics(mode[key])
            rows.append(row)
        report['engines'][engine]=rows
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('font',type=Path,nargs='?')
    p.add_argument('--private-output',type=Path);p.add_argument('--coretext-binary',type=Path);p.add_argument('--child',type=Path)
    p.add_argument('--samples',type=int,default=128);p.add_argument('--repeats',type=int,default=3);p.add_argument('--seed',type=int,default=2026110723)
    a=p.parse_args()
    if not a.child and (not a.font or not a.private_output or a.samples<=0 or a.repeats<=0):p.error('font, private output and positive counts required')
    run(a)
