#!/usr/bin/env python3
"""Independent authored reference for Qt; never reads a private source font."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import tempfile
import numpy as np
from fontTools.ttLib import TTCollection
from make_cff2_fixture import write_fixture, records, TAGS
from test_coretext_extract import make_fixture


def write(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    candidate = output/'hierarchical.ttc'
    write_fixture(candidate, hierarchical=True)
    # Binary-representable user coordinates avoid conflating transport loss
    # with interpolation. These are independent of the fitter's seed/nodes.
    points = [*itertools.product((-1.,0.,1.),repeat=3),
              *map(tuple,np.random.default_rng(831779).integers(-1023,1024,(64,3))/1024)]
    report = dict(schema=1, scope='independent_authored_CFF2_controls_only',
        font_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        limit_source_units=1/32, faces=[])
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp)/'source.ttc'; make_fixture(source)
        with TTCollection(source) as original, TTCollection(candidate) as saved:
            for reference,target in zip(original.fonts,saved.fonts):
                face = dict(family=target['name'].getDebugName(1),upm=target['head'].unitsPerEm,
                    cff2_sha256=hashlib.sha256(target.reader['CFF2']).hexdigest(),cases=[])
                for point in points:
                    normalized = dict(zip(TAGS,map(float,point)))
                    user = {a.axisTag:float(a.defaultValue+x*(a.defaultValue-a.minValue if x<0
                            else a.maxValue-a.defaultValue)) for a,x in zip(reference['fvar'].axes,point)}
                    face['cases'].append(dict(normalized=normalized,user=user,glyphs=[dict(gid=gid,
                        serialized_empty_cff2=target['CFF2'].cff.topDictIndex[0].CharStrings[name].bytecode == b'',
                        commands=records(reference,name,[normalized],.25,nonlinear=True)[0])
                        for gid,name in enumerate(reference.getGlyphOrder())]))
                report['faces'].append(face)
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);args=p.parse_args()
    result=write(args.output)
    print(json.dumps(dict(font_sha256=result['font_sha256'],observations=sum(len(c['glyphs'])
        for f in result['faces'] for c in f['cases']),scope=result['scope'])))
