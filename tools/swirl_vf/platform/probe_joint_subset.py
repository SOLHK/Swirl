#!/usr/bin/env python3
"""Measure default fontTools text subsetting and fresh HarfBuzz preservation.

Not a source-accuracy certificate: compare the same serialized font before and
after subsetting, including shuffled reuse of a mutable native font instance.
All input/output fonts remain private. A failed subset is recorded, not hidden.
"""
import argparse,hashlib,json,resource,sys,time
from pathlib import Path
import numpy as np
import uharfbuzz as hb
from fontTools import subset
from fontTools.ttLib import TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from projection_research import fresh_private
from p7_validate_candidate import commands
from probe_joint_representations import compare,implicit_closures
from cff2_geometry import operands


def run(path,out,*,samples=512,seed=2026110823):
    out=fresh_private(out);before=path.read_bytes();start=time.perf_counter()
    report=dict(scope='subset_and_mutable_instance_preservation_only',seed=seed,samples=samples,
        input_sha256=hashlib.sha256(before).hexdigest(),input_bytes=len(before),CoreText='NOT_RUN',
        production_accepted=False,original_source_accuracy=False,passed=False)
    try:
        with TTFont(path) as f:
            axes=list(f['fvar'].axes);report['original_glyphs']=len(f.getGlyphOrder())
            options=subset.Options();options.layout_features=['*']
            worker=subset.Subsetter(options=options);worker.populate(text='A');worker.subset(f)
            report['subset_glyphs']=len(f.getGlyphOrder());f.save(out/'subset.otf')
        report['subset_seconds']=time.perf_counter()-start;after=(out/'subset.otf').read_bytes()
        report.update(output_bytes=len(after),output_sha256=hashlib.sha256(after).hexdigest())
        def native(blob):
            font=hb.Font(hb.Face(blob));hb.ot_font_set_funcs(font);font.scale=(font.face.upem*64,)*2;return font
        a,b=native(before),native(after);points=np.random.default_rng(seed).uniform(-1,1,(samples,3))
        stats=dict(observations=0,failures=0,max_error=0.,topology_failures=0,
                   exact_outline_mismatches=0,advance_mismatches=0,mutable_cache_mismatches=0)
        expected=[]
        def draw(font,location):
            font.set_variations(location);buf=hb.Buffer();buf.add_str('A');buf.guess_segment_properties();hb.shape(font,buf)
            if len(buf.glyph_infos)!=1:raise ValueError('subset_shaping_count')
            return commands(font,buf.glyph_infos[0].codepoint),buf.glyph_positions[0].x_advance
        for p in points:
            loc={axis.axisTag:float(axis.defaultValue+x*(axis.defaultValue-axis.minValue if x<0 else axis.maxValue-axis.defaultValue)) for axis,x in zip(axes,p)}
            old,advance=draw(a,loc);new,width=draw(b,loc);verdict=compare(operands(implicit_closures(old)),new)
            stats['observations']+=1;stats['failures']+=not verdict['passed'];stats['max_error']=max(stats['max_error'],verdict['error'] or 0.)
            stats['topology_failures']+=verdict['error'] is None
            stats['exact_outline_mismatches']+=old!=new;stats['advance_mismatches']+=advance!=width
            expected.append((loc,new,width))
        for i in np.random.default_rng(seed+1).permutation(len(expected)):
            loc,outline,width=expected[i];got,advance=draw(b,loc)
            stats['mutable_cache_mismatches']+=got!=outline or advance!=width
        report['HarfBuzz']=stats
        report['passed']=not any(stats[k] for k in ('failures','exact_outline_mismatches','advance_mismatches','mutable_cache_mismatches'))
    except Exception as error:
        report['error']=f'{type(error).__name__}: {error}'
    report.update(seconds=time.perf_counter()-start,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--font',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--samples',type=int,default=512)
    p.add_argument('--seed',type=int,default=2026110823);a=p.parse_args()
    if a.samples<1:raise ValueError('positive_samples_required')
    raise SystemExit(0 if run(a.font,a.private_output,samples=a.samples,seed=a.seed)['passed'] else 1)
