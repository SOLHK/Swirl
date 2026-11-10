#!/usr/bin/env python3
"""Publish allowlisted corpus aggregates, retaining every supplied attempt.

Inputs are ordered chronologically by the caller. Missing/preselected cases
stay in the denominator. No coordinates, coefficients, local paths or logs
are copied. A successful native recheck never erases earlier failures.
"""
import argparse,hashlib,json
from pathlib import Path
LIMIT=1/32
SCALARS=('seconds','seed','stage_passed','boxes','factors','max_refinement_error',
 'source_evaluation_seconds','source_positions_evaluated','computational_axes','patch_glyphs',
 'avar2_regions','raw_parameter_regions','maximum_operand_stack','font_bytes','candidate_bytes',
 'input_bytes','maximum_compressed_operations','maximum_original_operations','maximum_operand_stack_bound',
 'maximum_subroutine_depth','exact_expanded_bytes_verified','coefficients_changed','candidate_sha256',
 'atlas_sha256','parameter_archive_sha256','observations','strict_independent_native_passed',
 'sampled_geometry_passed','acceptance_scope','branch_probe_gate','resumed_boxes',
 'refinement_budget','refinement_budget_met','source_branch_cuts')
GROUPS={'component_holdout':('holdout_count','max_physical_error','physical_failures','max_envelope_error','envelope_failures','holdouts_disjoint'),
 'independence':('proven','observations','unique_positions','overlapping_observations','unique_independent_positions','duplicate_observations'),
 'stages':('source_initialize_seconds','field_fit_seconds','field_holdout_seconds','archive_write_seconds','parameter_fit_seconds','parameter_holdout_seconds','archive_load_seconds','font_encode_seconds','font_save_seconds'),
 'expression_pool':('shared_expressions','drawing_chunks','maximum_main_bytes','maximum_subroutine_bytes','maximum_interpreter_operations','glyphs_reaching_operation_limit')}
ENGINE_KEYS=('observations','independent_observations','max_error','independent_max_error','failures',
 'topology_failures','direction_failures','closure_failures','selection_failures','max_explicit_closure_gap',
 'max_advance_error','advance_failures')
FAILURES=('failures','topology_failures','direction_failures','closure_failures','selection_failures','advance_failures')


def metrics(report):
    result={k:report[k] for k in SCALARS if k in report}
    if report.get('command')=='fit-parameters':
        # Keep useful parameter-stage evidence without admitting the generic
        # failures key if a different producer puts private sample rows there.
        keys=('holdout_count','holdouts_disjoint','max_parameter_induced_error',
              'failures','budget','raw_regions','encoded_regions')
        values={k:report[k]for k in keys if k in report}
        if any(type(v)not in (int,float,bool)for v in values.values()):
            raise ValueError('non_scalar_parameter_evidence')
        result['parameter_holdout']=values
    for group,keys in GROUPS.items():
        if group in report:result[group]={k:report[group][k] for k in keys if k in report[group]}
    if 'engines' in report:
        result['engines']={e:{k:r[k]for k in ENGINE_KEYS if k in r}for e,r in report['engines'].items() if e in ('CoreText','HarfBuzz','fontTools')}
        contract=report.get('axis_mapping_contract',{})
        result['original_user_axis_equivalence']=contract.get('font_only_original_user_axis_equivalence',False)
        result['candidate_segment_maps_conformant']=contract.get('candidate_segment_maps_conformant',False)
    return result


def native_pass(report):
    engines=report.get('engines',{})
    return (report.get('strict_independent_native_passed') is True and report.get('limit')==LIMIT
        and report.get('independence',{}).get('proven') is True and {'CoreText','HarfBuzz'}<=set(engines)
        and all(r.get('observations',0)>0 and r.get('independent_observations',0)>0
                and r.get('max_error',float('inf'))<=LIMIT and all(r.get(k,1)==0 for k in FAILURES)for r in engines.values()))


def summarize(selection,reports):
    source=selection['source_sha256']
    cases={(r['face'],r['gid']):dict(face=r['face'],gid=r['gid'],reasons=r['reasons'],
        structure={k:r.get('structure',{})[k] for k in ('curves','contours','type0','type2','depth')if k in r.get('structure',{})},
        attempts=[],status='NOT_RUN',passed=False)for r in selection['selection']}
    def target(face,gid,identity):
        if identity.get('source_sha256')!=source or (face,gid)not in cases:raise ValueError('unselected_or_wrong_source_case')
        return cases[face,gid]
    for ordinal,report in enumerate(reports):
        if 'cases'in report:
            if report['source_sha256']!=source:raise ValueError('batch_source_mismatch')
            for c in report['cases']:
                case=target(c['face'],c['gid'],{'source_sha256':source});stages=[];native=None
                for stage in c['stages']:
                    r=stage.get('result',{})
                    if 'identity'in r and r['identity']!={'source_sha256':source,'face_index':c['face'],'glyph_id':c['gid']}:
                        raise ValueError('stage_identity_mismatch')
                    stages.append({**{k:stage[k]for k in ('stage','exit_code','elapsed_seconds','peak_rss_bytes','reused')if k in stage},'metrics':metrics(r)})
                    if stage['stage']=='native':native=r
                passed=native_pass(native or {})
                status='PASS_JOINT_Q' if passed else ('RUNNING' if c.get('running_stage') else 'FAIL_'+c.get('failed_stage','native').upper())
                case['attempts'].append(dict(report_index=ordinal,stages=stages,status=status,passed=passed));case.update(status=status,passed=passed)
        else:
            identity=report['identity'];case=target(identity['face_index'],identity['glyph_id'],identity)
            is_native='engines'in report;passed=native_pass(report) if is_native else False
            status=('PASS_JOINT_Q' if passed else 'FAIL_NATIVE')if is_native else ('FIELDS_ONLY' if report.get('stage_passed') else 'FAIL_FIELDS')
            case['attempts'].append(dict(report_index=ordinal,kind='native_recheck'if is_native else 'field_stage',metrics=metrics(report),status=status,passed=passed));case.update(status=status,passed=passed)
    rows=list(cases.values());accepted={r['gid']for r in rows if r['passed']};anchors={r['gid']for r in rows if 'retained_anchor'in r['reasons']}
    return dict(source_sha256=source,selection_seed=selection['seed'],limit=LIMIT,
        eligible_root_glyphs=selection.get('eligible_root_glyphs'),nonlinear_probe_pool=selection.get('nonlinear_probe_pool'),
        structural_distribution=selection.get('structural_distribution'),selected_cases=len(rows),
        selected_unique_gids=len({r['gid']for r in rows}),passed_cases=sum(r['passed']for r in rows),
        passed_unique_gids=len(accepted),new_passed_unique_gids=len(accepted-anchors),cases=rows,
        production_accepted=False,full_font_coverage=False,original_source_DirectWrite='NOT_RUN',
        scope='joint post-avar q-space geometry and reported metrics; original physical-axis parity not established')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--selection',type=Path,required=True)
    p.add_argument('--report',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=summarize(json.loads(a.selection.read_text()),[json.loads(p.read_text())for p in a.report])
    result['input_sha256']=[hashlib.sha256(p.read_bytes()).hexdigest()for p in [a.selection,*a.report]]
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in ('selected_cases','passed_cases','new_passed_unique_gids')}))
