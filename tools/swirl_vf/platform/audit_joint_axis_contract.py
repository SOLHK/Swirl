#!/usr/bin/env python3
"""Aggregate-only raw avar audit: a segment dictionary is not source identity."""
import argparse,json
from collections import Counter
from pathlib import Path
import sys
from fontTools.ttLib import TTCollection,TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audit_font import raw_avar


def summarize_records(data,tags,segments):
    raw=raw_avar(data,tags)
    return dict(version=raw['major'],header_violations=raw['violations'],axes=[dict(tag=a['tag'],
        raw_records=a['raw_record_count'],dictionary_records=len(segments.get(a['tag'],{})),
        violations=dict(Counter([v['kind'] for v in a['violations']]+
            (['insufficient_segment_records'] if a['raw_record_count']<3 else [])))) for a in raw['axes']])


def summary(font):
    return summarize_records(font.reader['avar'],[a.axisTag for a in font['fvar'].axes],font['avar'].segments)


def compare_fonts(source,candidate):
    a,b=summary(source),summary(candidate)
    target={x['tag']:x for x in b['axes']}
    return dict(source=a,candidate=b,source_segment_record_counts_preserved=
        all(x['tag'] in target and x['raw_records']==target[x['tag']]['raw_records'] for x in a['axes']),
        candidate_segment_maps_conformant=not b['header_violations'] and not any(x['violations'] for x in b['axes']),
        font_only_original_user_axis_equivalence=False,
        note='Joint-q-space native geometry success does not establish original physical-user mapping parity.')


def run(source,candidate,face):
    with TTCollection(source,lazy=True) as collection,TTFont(candidate,lazy=True) as font:
        result=compare_fonts(collection.fonts[face],font)
    print(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--face',type=int,default=0)
    a=p.parse_args();run(a.source,a.candidate,a.face)
