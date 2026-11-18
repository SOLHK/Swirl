"""Append an exact vertical-origin placement model to standard GPOS/GDEF.

Existing outlines, advances, glyph mapping, GSUB and existing GPOS lookups are
preserved. Every caller-supplied coefficient must already be an exact integer.
No platform raw metric is rewritten. Feature activation and actual placement
must still be verified on each target engine. FeatureVariations and an already
present requested feature are rejected rather than silently rewritten.
"""
from __future__ import annotations
import copy
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.otlLib.builder import buildLookup, buildSinglePosSubtable, buildValue
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.varStore import OnlineVarStoreBuilder
from metric_variations import _support_key, require


def append_origin_compensation(source, corrections, *, feature='vert'):
    """Return a detached font. corrections[glyph]=(baseXY,supports,deltaXY)."""
    require(feature in ('vkrn','vpal','vert'), 'unsupported_vertical_origin_feature')
    font=copy.deepcopy(source)
    tags=[a.axisTag for a in font['fvar'].axes]
    require(corrections and set(corrections)<=set(font.getGlyphOrder()), 'origin_glyph_mapping_invalid')
    if 'GPOS' in font:
        table=font['GPOS'].table
        require(getattr(table,'FeatureVariations',None) is None, 'origin_feature_variations_need_explicit_remap')
        require(feature not in [r.FeatureTag for r in table.FeatureList.FeatureRecord], 'origin_feature_already_present')
    else:
        table=ot.GPOS();table.Version=0x10000
        table.LookupList=ot.LookupList();table.LookupList.Lookup=[]
        table.FeatureList=ot.FeatureList();table.FeatureList.FeatureRecord=[]
        table.ScriptList=ot.ScriptList();table.ScriptList.ScriptRecord=[]
        font['GPOS']=newTable('GPOS');font['GPOS'].table=table
    builder=OnlineVarStoreBuilder(tags);pending={}
    for glyph,(base,supports,deltas) in corrections.items():
        require(len(base)==2 and len(supports)==len(deltas), 'origin_coefficient_dimensions')
        require(all(type(v) is int and -32768<=v<=32767 for v in base), 'origin_default_not_int16')
        require(all(len(row)==2 and all(type(v) is int and -(1<<31)<=v<(1<<31) for v in row)
                    for row in deltas), 'origin_delta_not_exact_integer')
        for support in supports:_support_key(support,tags)
        builder.setSupports(supports)
        pending[glyph]=(base,tuple(builder.storeDeltas([d[i] for d in deltas]) for i in range(2)))
    added=builder.finish()
    if 'GDEF' not in font:
        font['GDEF']=newTable('GDEF');font['GDEF'].table=ot.GDEF()
        gdef=font['GDEF'].table
        gdef.GlyphClassDef=gdef.AttachList=gdef.LigCaretList=gdef.MarkAttachClassDef=None
    gdef=font['GDEF'].table
    old=getattr(gdef,'VarStore',None);outer=0
    if old is None:gdef.VarStore=added
    else:
        require(old.Format==1 and old.VarRegionList.RegionAxisCount==len(tags), 'existing_GDEF_axis_mismatch')
        outer=len(old.VarData);offset=len(old.VarRegionList.Region)
        require(outer+len(added.VarData)<=65535 and offset+len(added.VarRegionList.Region)<=65535,
                'origin_GDEF_store_capacity')
        for data in added.VarData:data.VarRegionIndex=[i+offset for i in data.VarRegionIndex]
        old.VarData.extend(added.VarData);old.VarDataCount=len(old.VarData)
        old.VarRegionList.Region.extend(added.VarRegionList.Region)
        old.VarRegionList.RegionCount=len(old.VarRegionList.Region)
    gdef.Version=0x10003
    if not hasattr(gdef,'MarkGlyphSetsDef'):gdef.MarkGlyphSetsDef=None
    values={}
    for glyph,(base,indices) in pending.items():
        # The special no-variation index is preserved, not offset into a store.
        adjusted=[v if v==0xffffffff else v+(outer<<16) for v in indices]
        values[glyph]=buildValue(dict(XPlacement=base[0],YPlacement=base[1],
            XPlaDevice=buildVarDevTable(adjusted[0]),YPlaDevice=buildVarDevTable(adjusted[1])))
    lookup=buildLookup([buildSinglePosSubtable(values,font.getReverseGlyphMap())],table='GPOS')
    lookup_index=len(table.LookupList.Lookup);table.LookupList.Lookup.append(lookup)
    table.LookupList.LookupCount=len(table.LookupList.Lookup)
    records=table.FeatureList.FeatureRecord
    record=ot.FeatureRecord();record.FeatureTag=feature;record.Feature=ot.Feature()
    record.Feature.FeatureParams=None;record.Feature.LookupListIndex=[lookup_index];record.Feature.LookupCount=1
    old_records=list(records);records.append(record);records.sort(key=lambda r:r.FeatureTag)
    remap={i:records.index(r) for i,r in enumerate(old_records)};index=records.index(record)
    table.FeatureList.FeatureCount=len(records)
    def language():
        obj=ot.LangSys();obj.LookupOrder=None;obj.ReqFeatureIndex=0xffff
        obj.FeatureIndex=[];obj.FeatureCount=0;return obj
    scripts=table.ScriptList.ScriptRecord
    for tag in ('DFLT','hani','latn'):
        if not any(r.ScriptTag==tag for r in scripts):
            sr=ot.ScriptRecord();sr.ScriptTag=tag;sr.Script=ot.Script()
            sr.Script.DefaultLangSys=language();sr.Script.LangSysRecord=[];sr.Script.LangSysCount=0
            scripts.append(sr)
    scripts.sort(key=lambda r:r.ScriptTag);table.ScriptList.ScriptCount=len(scripts)
    for sr in scripts:
        for lang in [sr.Script.DefaultLangSys,*[lr.LangSys for lr in sr.Script.LangSysRecord]]:
            if lang is None:continue
            if lang.ReqFeatureIndex!=0xffff:lang.ReqFeatureIndex=remap[lang.ReqFeatureIndex]
            lang.FeatureIndex=[remap[i] for i in lang.FeatureIndex]+[index]
            lang.FeatureCount=len(lang.FeatureIndex)
    return font
