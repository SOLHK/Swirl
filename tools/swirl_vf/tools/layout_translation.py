"""Fractional CFF2 translation for a dedicated vertical-layout glyph model.

This does not change raw metric semantics or promise original GID equivalence.
The caller must provide an independently verified GSUB route to a dedicated
vertical alternate. It must never apply the translated model to a glyph still
used by default horizontal text. Installation needs explicit experimental
layout opt-in until the complete font's shaping and metric mapping is verified.
"""
from __future__ import annotations
import copy
import numpy as np
from cff2_geometry import OutlineModel, fixed, require
from metric_variations import _support_key


def translate_vertical_model(model, base, supports, deltas):
    require(isinstance(model,OutlineModel) and model.evidence.get('sampled_geometry_passed'),
            'verified_plain_outline_model_required')
    require(model.evidence.get('domain_kind') not in ('one_dimensional_slice','vertical_layout_variant'),
            'layout_translation_requires_original_full_domain_model')
    require(len(base)==2 and len(supports)==len(deltas)
            and all(len(v)==2 for v in deltas),'layout_translation_dimensions')
    require(model.operators and model.operators[0]==('rmoveto',2),
            'layout_translation_requires_nonempty_closed_outline')
    tags=model.axis_tags
    def key(s): return tuple((t,tuple(s[t])) for t in tags if t in s)
    new_supports=copy.deepcopy(model.supports); rows=[r.copy() for r in model.deltas]
    indices={key(s):i for i,s in enumerate(new_supports)}
    for support,vector in zip([{}]+list(supports),[base]+list(deltas)):
        if support:_support_key(support,tags)
        encoded=np.asarray([fixed(float(v)) for v in vector])
        k=key(support)
        if k not in indices:
            indices[k]=len(rows);new_supports.append(copy.deepcopy(support));rows.append(np.zeros_like(rows[0]))
        row=rows[indices[k]]
        # Relative CFF2 path coordinates carry this first movement through ALL
        # later contours. Shifting every moveto would accumulate an error.
        row[:2]=[fixed(float(v)) for v in row[:2]+encoded]
    evidence=copy.deepcopy(model.evidence)
    evidence.update(domain_kind='vertical_layout_variant',production_accepted=False,
                    raw_original_geometry_equivalence=False,
                    layout_translation={'base':list(base),'supports':copy.deepcopy(supports),
                                        'deltas':[list(v) for v in deltas]},
                    required_GSUB_route_verification='NOT_ESTABLISHED_BY_THIS_OPERATION')
    return OutlineModel(tags,model.operators,new_supports,np.asarray(rows),evidence)
