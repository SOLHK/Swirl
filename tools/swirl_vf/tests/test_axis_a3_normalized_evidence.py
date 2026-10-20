"""Archived Windows execution, distinct from Linux reruns and Apple acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import axis_a3_normalized_evidence as evidence


class NativeNormalizedEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(evidence.MANIFEST.read_text())
        cls.reports = evidence.load_archives(manifest=cls.manifest)

    def test_exact_artifacts_and_full_native_checks(self):
        self.assertEqual(evidence.audit_reports(self.reports, self.manifest),
            {'processes': 4, 'native_observations': 144, 'opposite_order_pairs': 72,
             'normalized_glyph_checks': 128, 'cross_windows_comparison_pairs': 72,
             'mapping_accepted': False, 'status': 'VERIFIED_AUTHORED_CHANNEL_ONLY'})

    def test_independent_ci_source_and_original_artifact_ids(self):
        self.assertEqual(self.manifest['source_commit'], evidence.COMMIT)
        self.assertEqual(self.manifest['workflow_run_id'], 39406852651)
        self.assertEqual([x['artifact_id'] for x in self.manifest['artifacts']],
                         [12256872753, 12257861744, 12257711903])
        self.assertEqual([x['job_id'] for x in self.manifest['artifacts']],
                         [118574758864, 118574908949, 118574909027])

    def test_no_scope_or_acceptance_promotion(self):
        for key in evidence.FLAGS:
            reports = copy.deepcopy(self.reports)
            reports['windows-2025'][key] = True
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'acceptance_promoted'):
                evidence.audit_reports(reports, self.manifest)
        for key in ('synthetic_only', 'q_is_externally_supplied_not_derived_from_binary64'):
            reports = copy.deepcopy(self.reports)
            reports['windows-2022'][key] = False
            with self.assertRaises(ValueError): evidence.audit_reports(reports, self.manifest)

    def test_input_collapse_and_external_normalized_difference_coexist(self):
        for report in self.reports.values():
            for process in report['processes']:
                rows = {x['case']['id']: x for x in process['rows']}
                for engine in ('hb', 'ft'):
                    self.assertEqual(rows['collision_0'][engine], rows['collision_1'][engine])
                    self.assertEqual(rows['q_0_0'][engine]['advance'], 500)
                    self.assertEqual(rows['q_65_0'][engine]['advance'], 565)
                self.assertNotEqual(rows['q_0_0']['ft']['points'], rows['q_65_0']['ft']['points'])

    def test_real_windows_abi_versions_and_hashes_are_not_linux_results(self):
        for key in ('windows-2022', 'windows-2025'):
            for process in self.reports[key]['processes']:
                self.assertEqual(process['c_long_bytes'], 4)
                self.assertEqual(process['versions'], {'harfbuzz': '14.6.0', 'freetype': '2.15.0'})
                self.assertTrue(all(len(x['sha256']) == 64 for x in process['libraries']))
        self.assertFalse(self.reports['linux']['windows_tested'])
        self.assertEqual(self.reports['linux']['processes'][0]['c_long_bytes'], 8)

    def test_same_readback_does_not_waive_changed_outline_or_hvar(self):
        for field in ('advance', 'points'):
            reports = copy.deepcopy(self.reports)
            row = reports['windows-2022']['processes'][0]['rows'][5]['ft']
            if field == 'advance': row[field] += 1
            else: row[field][1][0] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                evidence.audit_reports(reports, self.manifest)

    def test_wrong_platform_commit_or_abi_is_rejected(self):
        for field, value in (('source_commit', '0' * 40), ('windows_tested', False),
                             ('platform', 'Windows-11'), ('python', '0.0')):
            reports = copy.deepcopy(self.reports)
            reports['windows-2025'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                evidence.audit_reports(reports, self.manifest)
        reports = copy.deepcopy(self.reports)
        reports['windows-2022']['processes'][0]['c_long_bytes'] = 8
        with self.assertRaises(ValueError): evidence.audit_reports(reports, self.manifest)

    def test_counts_cannot_double_pairs_or_import_linux_observations(self):
        for key in ('native_observations', 'opposite_order_pairs', 'cross_windows_comparison_pairs'):
            manifest = copy.deepcopy(self.manifest)
            manifest['windows_totals'][key] *= 2
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'totals'):
                evidence.audit_reports(self.reports, manifest)
        reports = copy.deepcopy(self.reports)
        reports['windows-2022']['checks']['all_exact'] = 1
        with self.assertRaises(ValueError): evidence.audit_reports(reports, self.manifest)

    def test_original_archive_bytes_are_mandatory(self):
        with tempfile.TemporaryDirectory() as directory:
            for item in self.manifest['artifacts']:
                (Path(directory) / item['archive_file']).write_bytes(
                    (evidence.ROOT / item['archive_file']).read_bytes())
            name = self.manifest['artifacts'][0]['archive_file']
            target = Path(directory) / name
            target.write_bytes(target.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'archive_hash_changed'):
                evidence.load_archives(directory, self.manifest)


if __name__ == '__main__': unittest.main()
