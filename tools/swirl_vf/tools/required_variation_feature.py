"""Declare a patch selector as required in every present GSUB language system."""
from cff2_geometry import require


def require_feature(font,tag='rvrn'):
    table=font['GSUB'].table
    matches=[i for i,r in enumerate(table.FeatureList.FeatureRecord) if r.FeatureTag==tag]
    require(len(matches)==1,'unique_variation_feature_required')
    index=matches[0];systems=[]
    for record in table.ScriptList.ScriptRecord:
        script=record.Script
        systems.extend(r.LangSys for r in script.LangSysRecord)
        if script.DefaultLangSys is not None:systems.append(script.DefaultLangSys)
    require(bool(systems) and all(s.ReqFeatureIndex in (0xFFFF,index) for s in systems),
            'existing_required_feature_conflict')
    for system in systems:
        system.ReqFeatureIndex=index
        system.FeatureIndex=[i for i in system.FeatureIndex if i!=index]
        system.FeatureCount=len(system.FeatureIndex)
    return len(systems)
