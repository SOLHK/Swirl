"""Read serialized research GSUB using the same coordinates as outline drawing.

fontTools is not a shaping engine. This deliberately restricted SingleSubst
reader covers the compiler's rvrn-only research fonts, not arbitrary text.
Mixing a HarfBuzz-selected GID with fontTools' unquantized location can select
one side of a seam and evaluate the other; neither engine executes that path.
"""
from cff2_geometry import require


def select_glyph(font, normalized, codepoint=ord('A')):
    name=font.getBestCmap()[codepoint]
    if 'GSUB' not in font:return font.getGlyphID(name)
    table=font['GSUB'].table
    records=table.FeatureList.FeatureRecord
    require(len(records)==1 and records[0].FeatureTag=='rvrn','unsupported_joint_gsub_features')
    feature=records[0].Feature
    axes=[a.axisTag for a in font['fvar'].axes]
    variation=getattr(table,'FeatureVariations',None)
    if variation:
        for record in variation.FeatureVariationRecord:
            conditions=record.ConditionSet.ConditionTable
            require(all(c.Format==1 and 0<=c.AxisIndex<len(axes) for c in conditions),
                    'unsupported_joint_gsub_condition')
            if not all(c.FilterRangeMinValue<=normalized.get(axes[c.AxisIndex],0)<=c.FilterRangeMaxValue
                       for c in conditions):continue
            for substitution in record.FeatureTableSubstitution.SubstitutionRecord:
                require(substitution.FeatureIndex==0,'unsupported_joint_gsub_feature_index')
                feature=substitution.Feature
            break  # Serialized first-match order, including closed boundaries.
    for index in feature.LookupListIndex:
        lookup=table.LookupList.Lookup[index]
        require(lookup.LookupType==1 and lookup.LookupFlag==0,'unsupported_joint_gsub_lookup')
        for subtable in lookup.SubTable:
            if name in subtable.mapping:
                name=subtable.mapping[name];break
    return font.getGlyphID(name)
