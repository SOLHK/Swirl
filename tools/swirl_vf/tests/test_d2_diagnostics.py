import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import d2_axis_readback as axis
import d2_metric_upem as metric
from test_coretext_extract import make_fixture


class AxisDiagnosisTests(unittest.TestCase):
    def evidence(self):
        faces=[{'face_index':0,'axes':[{'tag':'WDTH','minimum':1.,'default':500.,'maximum':1000.}],
                'tables':{'head':{'sha256':'head'}}}]
        requests=axis.requests_for(faces)
        rows=[]
        for request in requests:
            actual={k:axis.canonical(v) for k,v in request['location'].items()}
            passed=all(abs(actual[k]-v)<=1e-6 for k,v in request['location'].items())
            rows.append({'request_id':request['request_id'],'face_index':0,'location':request['location'],
                         'reported':actual,'strict_passed':passed,
                         'failure':'' if passed else 'coretext_did_not_report_requested_axis_value:WDTH'})
        native={'source_sha256':'original','physical_faces_verified':1,
                'faces':[{'face_index':0,'status':'identity_verified','verified_table_sha256':{'head':'head'}}],
                'rows':rows}
        return faces,requests,native

    def test_fractional_failure_retained_even_when_frozen_replay_passes(self):
        faces,requests,native=self.evidence()
        result=axis.analyze(native,faces,requests,'original')
        self.assertEqual((result['original_requests'],result['original_strict_passed'],result['original_strict_failed']),(4,3,1))
        self.assertEqual((result['replay_strict_passed'],result['replay_echo_exact'],result['original_errors_match_predeclared_TT']),(1,1,1))
        self.assertEqual(result['failure_fraction_counts'],{'1':1})
        self.assertFalse(result['mapping_accepted'])
        self.assertFalse(result['glyph_equivalence_tested'])

    def test_substitution_missing_duplicate_and_falsified_pass_are_rejected(self):
        faces,requests,native=self.evidence()
        variants=[]
        n=copy.deepcopy(native);n['faces'][0]['verified_table_sha256']['head']='fallback';variants.append(n)
        n=copy.deepcopy(native);n['rows'].pop();variants.append(n)
        n=copy.deepcopy(native);n['rows'][-1]=copy.deepcopy(n['rows'][0]);variants.append(n)
        n=copy.deepcopy(native);n['rows'][1]['strict_passed']=True;variants.append(n)
        n=copy.deepcopy(native);n['physical_faces_verified']=0;variants.append(n)
        for n in variants:
            with self.assertRaises(ValueError):axis.analyze(n,faces,requests,'original')

    def test_unavailable_face_is_blocked_with_no_measurement(self):
        faces,requests,native=self.evidence()
        native.update(physical_faces_verified=0,rows=[],faces=[{'face_index':0,'status':'unavailable'}])
        self.assertEqual(axis.analyze(native,faces,requests,'original')['status'],'BLOCKED_SOURCE_IDENTITY')
        native['rows']=[{}]
        with self.assertRaises(ValueError):axis.analyze(native,faces,requests,'original')

    def test_native_constructor_and_guard_are_preserved_and_no_glyph_api_added(self):
        path=Path(axis.__file__).with_name('coretext_extract.swift')
        prefix=path.read_text().split('\nfunc run() throws {')[0]
        self.assertTrue(axis.harness(path).startswith(prefix))
        self.assertIn('try validateReportedAxes',axis.MAIN)
        self.assertNotIn('CTFontCreatePathForGlyph',axis.MAIN)
        self.assertNotIn('CTFontGetAdvancesForGlyphs',axis.MAIN)


class MetricReproductionTests(unittest.TestCase):
    def test_frozen_formula_reproduces_known_849_850_without_correcting_it(self):
        self.assertEqual(metric.predictions(1000,1.)['frozen_B1_gvar_height'],849)
        self.assertEqual(metric.predictions(1024,1.)['frozen_B1_gvar_height'],850)
        self.assertEqual(metric.predictions(1000,1.)['continuous_height'],850)
        self.assertEqual(metric.predictions(1000,914.0625)['frozen_B1_gvar_height'],1125)
        self.assertGreater(metric.predictions(1000,914.0625)['frozen_B1_gvar_height'],
                           metric.predictions(1000,914.0625)['continuous_height'])

    def test_fresh_upem_separates_preregistered_horizontal_candidates(self):
        p=metric.predictions(1001,1.)['horizontal_candidates']
        self.assertEqual(len(set(p.values())),5)
        self.assertEqual(p['16'],669.9961090087890625)

    def test_only_head_changes_in_real_serialized_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'original.ttc';target=Path(tmp)/'fresh.ttc'
            make_fixture(source);before=source.read_bytes()
            tables=metric.build_fixture(source,target,4093)
            self.assertEqual(source.read_bytes(),before)
            self.assertTrue({'head','gvar','fvar','vmtx'}<=set(tables))
            self.assertNotIn('VVAR',tables)

    def test_replay_checks_every_raw_payload_field_not_only_metrics(self):
        left={1.:{'request_id':'1','advance_height':849,'commands':[['moveTo',0,0]],'extra':1}}
        right=copy.deepcopy(left);right[1.]['request_id']='other'
        metric.validate_replay(left,right)
        right[1.]['extra']=2
        with self.assertRaises(ValueError):metric.validate_replay(left,right)


if __name__=='__main__':unittest.main()
