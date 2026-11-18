"""Apple request-stream integration with original authored geometry only."""
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'platform'))
from make_synthetic_hvf import create


@unittest.skipUnless(platform.system() == 'Darwin', 'Apple native oracle requires macOS')
class NativeStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.base = Path(cls.temp.name)
        cls.font = cls.base/'authored.ttf'; create(cls.font)
        cls.binary = cls.base/'oracle'
        subprocess.run(['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-mmacosx-version-min=15.4', str(ROOT/'platform/hvf_oracle.c'), '-lhvf', '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def run_stream(self, text):
        return subprocess.run([str(self.binary), str(self.font), '0', 'requests'],
                              input=text, text=True, capture_output=True, timeout=30)

    def test_multiple_coordinates_equal_legacy_independent_calls(self):
        coords = ('0,0,0', '.375,-.25,.625', '-1,1,-1', '1,-1,1')
        process = self.run_stream(''.join('0 '+q+'\n' for q in coords))
        self.assertEqual(process.returncode, 0, process.stderr)
        rows = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertTrue(rows[0]['request_stream']); self.assertEqual(rows[-1]['rendered'], len(coords))
        for index, q in enumerate(coords):
            one = subprocess.run([str(self.binary), str(self.font), '0', q, '0', '1'],
                                 text=True, capture_output=True, check=True, timeout=30)
            expected = json.loads(one.stdout.splitlines()[1])
            actual = dict(rows[index+1]); self.assertEqual(actual.pop('request_index'), index)
            self.assertEqual(actual.pop('normalized_coords'), list(map(float, q.split(','))))
            self.assertEqual(actual, expected)

    def test_malformed_requests_rejected_without_success_summary(self):
        for text in ('0 nan,0,0\n', '1 0,0,0\n', '0 2,0,0\n', '0 0,0\n', '0 0,0,0 trailing\n', '0 '+('0'*5000)+'\n'):
            with self.subTest(text=text[:40]):
                process = self.run_stream(text)
                self.assertNotEqual(process.returncode, 0)
                self.assertNotIn('"record":"summary"', process.stdout)


if __name__ == '__main__': unittest.main()
