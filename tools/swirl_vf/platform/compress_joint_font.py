#!/usr/bin/env python3
"""Apply a lossless generated-CFF2 encoding pass to a fresh private output."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
from fontTools.ttLib import TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from cff2_structural_pool import compress
from projection_research import fresh_private


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def run(args):
    out=fresh_private(args.private_output);start=time.monotonic();identity=digest(args.font)
    with TTFont(args.font,lazy=True) as font:
        # Saving must retain every other table. head.checkSumAdjustment alone
        # is allowed to reflect the changed whole-font checksum.
        before={t:font.reader[t] for t in font.reader.keys() if t != 'CFF2'}
        opened=time.monotonic();report=compress(font,maximum_helpers=getattr(args,'maximum_helpers',215))
        compiled=time.monotonic();font.save(out/'candidate.otf');saved=time.monotonic()
    with TTFont(out/'candidate.otf',lazy=True) as font:
        assert set(font.reader.keys())==set(before)|{'CFF2'},'font_table_set_changed'
        for tag,data in before.items():
            actual=font.reader[tag]
            if tag=='head':
                actual=actual[:8]+b'\0'*4+actual[12:]
                data=data[:8]+b'\0'*4+data[12:]
            assert actual==data,'non_CFF2_table_changed:'+tag
    assert identity==digest(args.font),'input_font_changed'
    report.update(input_sha256=identity,candidate_sha256=digest(out/'candidate.otf'),
        input_bytes=args.font.stat().st_size,candidate_bytes=(out/'candidate.otf').stat().st_size,
        load_seconds=opened-start,compression_seconds=compiled-opened,save_seconds=saved-compiled,
        seconds=time.monotonic()-start,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
        all_non_CFF2_tables_unchanged=True,native_verification='NOT_RUN',production_accepted=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('font',type=Path)
    p.add_argument('--private-output',type=Path,required=True)
    p.add_argument('--maximum-helpers',type=int,default=215,
                   help='1..1239; above 215 uses a bias-preserving three-byte call tier')
    run(p.parse_args())
