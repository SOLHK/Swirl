"""Authored callback records test full coverage and malformed output rejection."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from hvf_transcript import validate_transcript
from hvf_coverage import summary, chunks


def authored_rows():
    events = [['begin_part', 0], ['begin_path'], ['move', 0, 0], ['line', 20, 0],
              ['quad', 20, 10, 0, 10], ['close'], ['end_path'], ['end_part', 0]]
    counters = {'events': 8, 'parts_begun': 1, 'parts_ended': 1, 'paths_begun': 1,
                'paths_ended': 1, 'moves': 1, 'lines': 1, 'quads': 1, 'cubics': 0, 'closes': 1}
    header = {'record': 'header', 'schema': 1, 'engine': 'Apple HVF',
        'coordinate_space': 'normalized_design_after_avar', 'input_bytes': 123,
        'face_index': 0, 'face_count': 1, 'maxp_glyphs': 2, 'hvf_visible_parts': 2,
        'hvf_total_parts': 2, 'start': 0, 'count': 2, 'fvar_axis_tags': ['WDTH', 'wght', 'HGHT'],
        'normalized_coords': [0., 0., 0.], 'metrics': 'NOT_EXTRACTED', 'user_axis_mapping': 'NOT_TESTED'}
    one = {'record': 'outline', 'part_index': 0, 'part_axis_count': 3,
           'applied_axis_count': 3, 'events': events, 'status': 'OK', 'native_code': 0, 'counters': counters}
    two = copy.deepcopy(one)
    two['part_index'] = 1
    two['events'][0][1] = two['events'][-1][1] = 1
    return [header, one, two, {'record': 'summary', 'status': 'EXTRACTED',
            'rendered': 2, 'failed': 0, 'preservation_verdict': 'NOT_EVALUATED'}]


class TranscriptTests(unittest.TestCase):
    def check_rows(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'authored.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            return validate_transcript(path, face=0, coords=(0., 0., 0.), start=0,
                                       count=0, parts=False, input_bytes=123)

    def test_ordered_complete_callback_coverage(self):
        report = self.check_rows(authored_rows())
        self.assertEqual(report['finite_closed_successful_outlines'], 2)
        self.assertTrue(report['ordered_complete_GID_coverage'])

    def test_duplicate_missing_reordered_or_excess_GIDs_cannot_pass_counts(self):
        rows = authored_rows()
        for bad in ([rows[0], rows[1], rows[1], rows[-1]],
                    [rows[0], rows[2], rows[1], rows[-1]], rows[:2]+rows[-1:],
                    rows[:-1]+[rows[2], rows[-1]], rows[:-1], rows+[rows[-1]]):
            with self.subTest(rows=len(bad)), self.assertRaises(ValueError):
                self.check_rows(bad)

    def test_coordinates_axes_counters_and_closure_must_be_real(self):
        changes = [lambda r: r[1]['events'][2].__setitem__(1, float('nan')),
            lambda r: r[1]['counters'].__setitem__('quads', 0),
            lambda r: r[1].__setitem__('applied_axis_count', 2),
            lambda r: r[0].__setitem__('normalized_coords', [1., 0., 0.]),
            lambda r: r[1]['events'].pop(5),
            lambda r: r[1]['events'][-1].__setitem__(1, 1),
            lambda r: r[-1].__setitem__('rendered', 1)]
        for change in changes:
            rows = authored_rows(); change(rows)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check_rows(rows)

    def test_a_measured_empty_outline_is_preserved(self):
        rows = authored_rows()
        row = rows[2]
        row['events'] = [['begin_part', 1], ['end_part', 1]]
        row['counters'] = dict.fromkeys(row['counters'], 0)
        row['counters'].update(events=2, parts_begun=1, parts_ended=1)
        self.assertEqual(self.check_rows(rows)['empty_outlines'], 1)

    def test_failed_native_record_remains_failed(self):
        rows = authored_rows()
        rows[1].update(status='FAILED', native_code=-1, events=[])
        rows[-1].update(status='FAILED', rendered=1, failed=1)
        result = self.check_rows(rows)
        self.assertEqual(result['counts']['failed_outlines'], 1)
        self.assertEqual(result['finite_closed_successful_outlines'], 1)

    def test_batch_plan_includes_final_short_chunk_and_all_positions(self):
        recipe = {'positions': [[0, 0, 0], [1, 1, 1]], 'glyph_count': 5, 'batch_size': 2, 'face_index': 0}
        self.assertEqual([v[3] for v in chunks(recipe)], [2, 2, 1, 2, 2, 1])
        rows = {key: {'status': 'EXTRACTED', 'glyph_records': count} for key, _, _, count in chunks(recipe)}
        report = summary(recipe, rows)
        self.assertEqual(report['native_glyph_records'], 10)
        self.assertFalse(report['production_accepted'])
        self.assertFalse(report['continuous_variation_proof'])
        self.assertEqual(report['user_axis_mapping'], 'NOT_TESTED')
        rows.pop(next(iter(rows)))
        self.assertEqual(summary(recipe, rows)['status'], 'IN_PROGRESS')
        rows[next(iter(rows))]['status'] = 'FAILED'
        self.assertEqual(summary(recipe, rows)['status'], 'FAILED')


if __name__ == '__main__':
    unittest.main()
