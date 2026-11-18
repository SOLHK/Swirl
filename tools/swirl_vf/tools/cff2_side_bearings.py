"""Install exact, explicitly supplied CFF2 top-side-bearing models.

VORG permits engines to use yMax + vmtx.tsb instead of VORG. Moving a vertical
alternate in Y therefore requires a consistent bearing model as well as VORG.
This operation does not infer nonlinear bounding extrema or round coefficients.
The caller must independently verify bounds + bearing against the origin over
the design space. Native rounding and actual layout still need acceptance.
"""
from __future__ import annotations
import copy
from fontTools.varLib.builder import buildVarIdxMap
from fontTools.varLib.varStore import OnlineVarStoreBuilder
from metric_variations import _support_key, require


def install_top_bearings(source, models):
    """models[name] = (absolute_default_tsb, supports, absolute_tsb_deltas)."""
    require(all(t in source for t in ('CFF2','fvar','vmtx','VVAR','VORG')),
            'explicit_CFF2_vertical_metrics_required')
    font=copy.deepcopy(source);table=font['VVAR'].table
    require(table.TsbMap is None,'existing_TsbMap_requires_explicit_model_remap')
    tags=[a.axisTag for a in font['fvar'].axes];order=font.getGlyphOrder()
    require(models and set(models)<=set(order),'invalid_top_bearing_glyphs')
    builder=OnlineVarStoreBuilder(tags);indices={}
    for name,(base,supports,deltas) in models.items():
        require(type(base) is int and -32768<=base<=32767,'top_bearing_default_not_int16')
        require(len(supports)==len(deltas) and all(type(v) is int and -(1<<31)<=v<(1<<31) for v in deltas),
                'top_bearing_deltas_not_exact_integers')
        for support in supports:_support_key(support,tags)
        builder.setSupports(supports);indices[name]=builder.storeDeltas(deltas)
        font['vmtx'].metrics[name]=(font['vmtx'].metrics[name][0],base)
    added=builder.finish();old=table.VarStore
    require(old.Format==1 and old.VarRegionList.RegionAxisCount==len(tags),'top_bearing_store_axis_mismatch')
    outer=len(old.VarData);offset=len(old.VarRegionList.Region)
    require(outer+len(added.VarData)<=65535 and offset+len(added.VarRegionList.Region)<=65535,
            'top_bearing_store_capacity')
    for data in added.VarData:data.VarRegionIndex=[i+offset for i in data.VarRegionIndex]
    old.VarData.extend(added.VarData);old.VarDataCount=len(old.VarData)
    old.VarRegionList.Region.extend(added.VarRegionList.Region);old.VarRegionList.RegionCount=len(old.VarRegionList.Region)
    mapping=[indices.get(name,0xffffffff) for name in order]
    table.TsbMap=buildVarIdxMap([v if v==0xffffffff else v+(outer<<16) for v in mapping],order)
    return font
