#!/usr/bin/env python3
"""Rebase a private P7 partial original q-face using the existing P4 algorithm.

Experimental files only. This neither accepts source user mapping nor opens
the production builder. The parent default-only/partial-variable limitations
and all strict failures are inherited unchanged.
"""
import argparse
import json
from pathlib import Path
import sys

from fontTools.ttLib import TTFont, TTCollection

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from p7_original_glyf import private_directory, save_new, EXPECTED
from rebuild import sha256, verify_serialized_face
from target_axis_mapping import axes_from_font
from rebase_design_font import rebase_design_font, _serialized_precision_font
from metric_variations import add_metric_variations
from ttc_staging_pack import pack_collection


def require(condition, message):
    if not condition:
        raise ValueError(message)


def serialized_metric_candidate(candidate):
    """Derive metrics from the encoded support grid, never transient supports.

    Range restriction can map an interior support to, for example, 2/3. The
    OpenType serializer encodes that support in F2DOT14. Keep the metric writer's
    exact-F2 guard and derive its regions from those actual reopened gvar bytes.
    This records coordinate quantization; it does not certify font fidelity.
    """
    # The instancer removes empty gvar dictionary entries; the binary table
    # still has a slot for every GID and reopening restores those empty lists.
    before = {name: [dict(item.axes) for item in candidate['gvar'].variations.get(name, [])]
              for name in candidate.getGlyphOrder()}
    for tag in ('HVAR', 'VVAR'):
        if tag in candidate:
            del candidate[tag]
    encoded = _serialized_precision_font(candidate)
    require(encoded.getGlyphOrder() == list(before), 'support_encoding_changed_GID_order')
    changed, maximum = 0, 0.
    for name, variations in encoded['gvar'].variations.items():
        require(len(variations) == len(before[name]), 'support_encoding_changed_tuple_count')
        for item, wanted in zip(variations, before[name]):
            require(set(item.axes) == set(wanted), 'support_encoding_changed_axes')
            for tag, triple in item.axes.items():
                for old, new in zip(wanted[tag], triple):
                    error = abs(old-new)
                    require(error <= .5/16384, 'unexpected_F2_support_encoding_error')
                    changed += old != new
                    maximum = max(maximum, error)
    verification = add_metric_variations(encoded)
    return encoded, dict(stage='SERIALIZE_GVAR_BEFORE_DERIVING_METRIC_REGIONS',
        changed_support_coordinates=changed, maximum_normalized_support_encoding_error=maximum,
        error_unit='NORMALIZED_AXIS_COORDINATE_NOT_SOURCE_FUNIT',
        metric_encoding=verification, continuous_equivalence_proven=False,
        strict_font_acceptance=False, production_accepted=False)


def run(source, parent_directory, output):
    source, parent = Path(source).resolve(strict=True), Path(parent_directory).resolve(strict=True)
    require(sha256(source)==EXPECTED, 'exact_original_source_required')
    report_path = parent/'face-report.json'
    receipt = json.loads(report_path.read_text())
    qpath = parent/'P7-Original-face0-EXPERIMENTAL.ttf'
    require(receipt['source_sha256']==EXPECTED and receipt['production_accepted'] is False
            and receipt['axis_models_partial'] is True and receipt['glyph_count']==47102
            and sha256(qpath)==receipt['candidate_sha256'], 'verified_private_P7_parent_required')
    output = private_directory(output)
    require(not any(output.iterdir()), 'fresh_nominal_output_required')
    with TTCollection(source, lazy=True) as original, TTFont(qpath, recalcTimestamp=False) as qfont:
        src = original.fonts[0]
        axes = axes_from_font(src)
        candidate, mapped = rebase_design_font(qfont, axes)
        # Keep a single exactly consistent metric encoding of the final phantoms.
        candidate, support_encoding = serialized_metric_candidate(candidate)
        for axis, source_axis in zip(candidate['fvar'].axes, src['fvar'].axes):
            axis.flags = source_axis.flags
            axis.axisNameID = candidate['name'].addName('Experimental '+axis.axisTag)
        family = 'Swirl EXPERIMENTAL PARTIAL ORIGINAL AXES'
        names = {1:family, 2:'Incomplete', 3:'SwirlExperimentalPartialOriginalAxes',
                 4:family+' Incomplete', 6:'SwirlExperimentalPartialOriginalAxes',
                 16:family, 17:'Incomplete', 25:'SwirlExperimentalPartialOriginalAxes'}
        for record in list(candidate['name'].names):
            if record.nameID in names:
                candidate['name'].setName(names[record.nameID], record.nameID,
                                         record.platformID, record.platEncID, record.langID)
        for key,value in names.items(): candidate['name'].setName(value,key,3,1,0x409)
        candidate = _serialized_precision_font(candidate)
        require(candidate.getGlyphOrder()==src.getGlyphOrder()
                and candidate['cmap'].compile(candidate)==src['cmap'].compile(src),
                'original_cmap_or_GID_order_changed')
        path = output/'P7-Original-face0-NOMINAL-EXPERIMENTAL.ttf'
        candidate.save(path)
        before = sha256(path)
        with TTFont(path) as reopened:
            serialized = verify_serialized_face(candidate, reopened)
        require(sha256(path)==before, 'candidate_changed_after_verification')
        def verify(packed):
            with TTCollection(packed) as collection:
                require(len(collection.fonts)==1, 'nominal_candidate_face_count_changed')
                verify_serialized_face(candidate, collection.fonts[0])
        packed = pack_collection([path], output/'P7-Original-face0-NOMINAL-EXPERIMENTAL.ttc',
                                  expected_sha256=[before], validate=verify)
        require(sha256(qpath)==receipt['candidate_sha256'] and sha256(source)==EXPECTED,
                'parent_or_original_source_changed')
        report = {'status':'EXPERIMENTAL_ORIGINAL_NOMINAL_AXES_PARTIAL_VARIABLE_FACE_NOT_ACCEPTED',
            'source_sha256':EXPECTED, 'parent_candidate_sha256':receipt['candidate_sha256'],
            'parent_report_sha256':sha256(report_path), 'candidate_sha256':before,
            'glyph_count':47102, 'selected_variable_GIDs':receipt['selected_variable_GIDs'],
            'default_only_GIDs':receipt['default_only_GIDs'], 'axis_models_partial':True,
            'axes':[(a.axisTag,a.minValue,a.defaultValue,a.maxValue,a.flags) for a in candidate['fvar'].axes],
            'target_units_per_em':candidate['head'].unitsPerEm,
            'original_named_instances':'NOT_RESTORED_PENDING_METADATA_ACCEPTANCE',
            'inherited_model_failures':True, 'retained_unverified_tables':receipt['retained_unscaled_unverified_tables'],
            'mapping':mapped, 'support_encoding':support_encoding, 'serialization':serialized, 'packing':packed,
            'original_composite_relations_preserved':False, 'source_user_mapping_accepted':False,
            'strict_font_acceptance':False, 'font_only_equivalence_accepted':False,
            'production_accepted':False, 'DirectWrite':'NOT_RUN', 'Windows11':'NOT_RUN', 'Qt_Swirl':'NOT_RUN'}
        save_new(output/'nominal-report.json', report)
        candidate.close()
    print(json.dumps({k:report[k] for k in ('status','glyph_count','selected_variable_GIDs','axes','candidate_sha256')}))
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source,args.parent,args.output)
