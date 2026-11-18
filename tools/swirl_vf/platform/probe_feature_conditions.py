#!/usr/bin/env python3
"""Native capability probe for axis-aligned and coupled branch selection.

Only independently authored eight-glyph controls are used. Format 1 is the
published OpenType condition; format 2 is an experimental extension, *not* a
portable implementation choice. A successful measurement is not acceptance of
an unsupported condition or of a source glyph. Raw glyph-ID equivalence also
does not follow from a successful GSUB substitution.

References: Microsoft OpenType chapter2 (Condition table format 1), and
https://github.com/harfbuzz/boring-expansion-spec/blob/main/ConditionTree.md
"""
from __future__ import annotations
import argparse, hashlib, io, itertools, json, platform, subprocess
from pathlib import Path
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib.featureVars import addFeatureVariations
from fontTools.varLib.varStore import OnlineVarStoreBuilder
import experiment_vertical_gpos as fixture
import probe_coretext_vertical_gpos as ct
import probe_directwrite_vertical_layout as dw

POINTS = tuple(itertools.product((-1., 0., 1.), repeat=3)) + (
    (.125, .3, .125), (.125-1/1024, .3, .125),
    (.125+1/1024, .3, .125), (.5, -.2, -.5), (-.5, .2, .9),
)


def selected(point, kind):
    return point[0] >= .25 if kind == 'axis_range' else point[0]+point[2] > .25


def build(kind):
    fixture.require(kind in ('axis_range', 'coupled_value'), 'unknown_condition_control')
    raw, _ = fixture.original_fixture()
    font = TTFont(io.BytesIO(raw))
    addFeatureVariations(font, [([{'WDTH': (.25, 1.)}], {'han': 'latinB'})])
    if kind == 'coupled_value':
        builder = OnlineVarStoreBuilder([a.axisTag for a in font['fvar'].axes])
        builder.setSupports([{'WDTH': (0.,1.,1.)}, {'WDTH': (-1.,-1.,0.)},
                             {'HGHT': (0.,1.,1.)}, {'HGHT': (-1.,-1.,0.)}])
        index = builder.storeDeltas([4096,-4096,4096,-4096])
        font['GDEF'] = newTable('GDEF'); gdef = ot.GDEF(); font['GDEF'].table = gdef
        gdef.Version = 0x10003
        gdef.GlyphClassDef = gdef.AttachList = gdef.LigCaretList = gdef.MarkAttachClassDef = None
        gdef.MarkGlyphSetsDef = None; gdef.VarStore = builder.finish()
        condition = ot.ConditionTable(); condition.Format = 2
        condition.DefaultValue = -1024; condition.VarIdx = index
        variations = font['GSUB'].table.FeatureVariations.FeatureVariationRecord
        fixture.require(len(variations) == 1, 'unexpected_control_condition_count')
        variations[0].ConditionSet.ConditionTable = [condition]
    data = fixture.serialize(font)
    source = TTFont(io.BytesIO(raw)); restored = TTFont(io.BytesIO(data))
    for tag in fixture.PROTECTED:
        if tag != 'GSUB':
            fixture.require(source.getTableData(tag) == restored.getTableData(tag),
                            'condition_control_changed_geometry_or_metrics')
    return data


def native_records(data, directory, native, binary):
    directory.mkdir()
    path = directory/'control.ttf'; path.write_bytes(data)
    if native == 'coretext':
        requests = [r for r in ct.requests('vert', POINTS) if r['policy']=='default'
                    and r['direction']=='ltr' and r['language']=='zh-CN' and r['text']=='single_han']
        font = TTFont(io.BytesIO(data))
        config = {'scope':'independent_original_GPOS_fixture_only','font_path':str(path),
            'font_sha256':hashlib.sha256(data).hexdigest(),
            'table_hashes':{t:hashlib.sha256(font.getTableData(t)).hexdigest()
                for t in (*fixture.PROTECTED,'name','GPOS','GDEF') if t in font},
            'absent_tables':[t for t in ('GPOS','GDEF') if t not in font], 'requests':requests}
        manifest = directory/'manifest.json'; manifest.write_text(json.dumps(config))
        process = subprocess.run([str(binary),str(manifest)],capture_output=True,text=True,timeout=300)
        (directory/'native.jsonl').write_text(process.stdout)
        (directory/'native.stderr.log').write_text(process.stderr)
        rows = [json.loads(line) for line in process.stdout.splitlines()]
        observations = [r for r in rows if r.get('type')=='observation']
        fixture.require(process.returncode == 0 and len(observations)==len(requests), 'condition_CoreText_incomplete')
        ct.require_registration_cleanup([r for r in rows if r.get('type')=='fixture_registration_cleanup'],config['font_sha256'])
        return [r['glyphs'][0]['gid'] for r in observations]
    requests = [r for r in dw.requests(POINTS) if r['route']=='vert' and r['policy']=='default'
                and r['direction']=='H' and r['locale']=='zh-CN' and r['text_kind']=='single_han']
    process = subprocess.run([str(binary),str(path)],input=''.join(dw.request_line(r) for r in requests),
                             capture_output=True,text=True,timeout=300)
    (directory/'native.jsonl').write_text(process.stdout)
    (directory/'native.stderr.log').write_text(process.stderr)
    records = dw.parse_transcript(process.stdout,requests,data,process.returncode)['records']
    return [dw.flatten(r)[0][1]['gid'] for r in records]


def run(output, native, binary=None):
    output = Path(output).resolve(); output.mkdir(parents=True,exist_ok=False)
    report = {'scope':'authored_condition_capability_only','native':native,
        'os':platform.platform(),'source_glyph_acceptance':'NOT_RUN',
        'format2_is_published_Microsoft_OpenType_condition':False,'controls':{}}
    if native == 'coretext':
        source = output/'condition.swift'; source.write_text(ct.make_harness()); binary = output/'condition-native'
        process = subprocess.run(['xcrun','swiftc','-O',str(source),'-o',str(binary)],capture_output=True,text=True,timeout=180)
        fixture.require(process.returncode == 0,'condition_harness_compile_failed:'+process.stderr[-2000:])
    elif native == 'directwrite': binary = Path(binary).resolve(strict=True)
    for kind in ('axis_range','coupled_value'):
        data = build(kind)
        expected = [7 if selected(p,kind) else 2 for p in POINTS]
        hb = [fixture.shape(data,p,'ltr','zh-cn')['glyphs'][0]['gid'] for p in POINTS]
        row = {'sha256':hashlib.sha256(data).hexdigest(),'points':POINTS,'expected_gids':expected,
            'HarfBuzz_gids':hb,'HarfBuzz_mismatches':sum(a!=b for a,b in zip(hb,expected))}
        if native != 'none':
            try:
                actual = native_records(data,output/kind,native,binary)
                row.update(native_gids=actual,native_mismatches=sum(a!=b for a,b in zip(actual,expected)))
                row['status'] = 'SUPPORTED_ON_CONTROL_ONLY' if row['native_mismatches']==0 else 'CONDITION_NOT_SUPPORTED'
            except (ValueError, subprocess.TimeoutExpired) as error:
                row.update(status='NATIVE_CONTROL_FAILED',error=str(error))
        else: row['status'] = 'NATIVE_NOT_RUN'
        report['controls'][kind] = row
        (output/'report.json').write_text(json.dumps(report,indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native',choices=('none','coretext','directwrite'),default='none')
    p.add_argument('--binary',type=Path)
    args = p.parse_args(); result = run(args.output,args.native,args.binary)
    print(json.dumps(result))
    # The extension is a capability probe, never a green compatibility gate.
    # A broken standard-format control invalidates the comparison entirely.
    control = result['controls']['axis_range']
    if control['HarfBuzz_mismatches'] or (args.native!='none' and control['status']!='SUPPORTED_ON_CONTROL_ONLY'):
        raise SystemExit(1)
