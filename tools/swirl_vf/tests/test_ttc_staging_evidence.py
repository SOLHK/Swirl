"""Original source-only provenance tests; never read a user's font."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

MODULE = Path(__file__).resolve().parents[1] / 'platform/rebuild_c1_evidence.py'
spec = importlib.util.spec_from_file_location('c1_source_evidence', MODULE)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'C1 Original Test')
        self.git('config', 'user.email', 'c1@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        self.write('tools/swirl_vf/tools/original.py', '# original source\n')
        self.write('docs/SWIRL_VF_ORIGINAL.md', '# Original documentation\n')
        self.commit()
        self.output = self.root / 'evidence.zip'

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args],
                                       stderr=subprocess.PIPE)

    def write(self, name, content):
        p = self.repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content.encode() if isinstance(content, str) else content)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'Original fixture')

    def snapshot(self, **kwargs):
        return evidence.write_source_snapshot(self.repo, self.output, **kwargs)

    def test_exact_source_and_manifest_hashes(self):
        result = self.snapshot()
        self.assertEqual(result['source_commit'], self.git('rev-parse', 'HEAD').decode().strip())
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(json.loads(archive.read('C1_SOURCE_MANIFEST.json')), result)
            for item in result['files']:
                data = archive.read(item['path'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
                self.assertEqual(len(data), item['bytes'])
        self.assertFalse(result['font_generated'])
        self.assertFalse(result['production_acceptance'])

    def test_dirty_and_untracked_content_never_archived(self):
        self.write('tools/swirl_vf/tools/original.py', 'UNCOMMITTED')
        self.write('tools/swirl_vf/tools/untracked.py', 'UNTRACKED')
        result = self.snapshot()
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.read('tools/swirl_vf/tools/original.py'), b'# original source\n')
            self.assertNotIn('tools/swirl_vf/tools/untracked.py', archive.namelist())
        self.assertEqual(len(result['files']), 2)

    def test_no_font_checkpoint_json_or_unrelated_source(self):
        for suffix in ('ttc', 'ttf', 'otf', 'woff', 'woff2', 'json', 'jsonl', 'zip', 'bin'):
            self.write('tools/swirl_vf/private.' + suffix, 'EXCLUDED')
        self.write('unrelated.py', 'EXCLUDED')
        self.write('docs/unrelated.md', 'EXCLUDED')
        self.commit()
        self.assertEqual(len(self.snapshot()['files']), 2)

    def test_identical_revision_is_byte_reproducible(self):
        self.snapshot()
        other = self.root / 'second.zip'
        evidence.write_source_snapshot(self.repo, other)
        self.assertEqual(self.output.read_bytes(), other.read_bytes())

    def test_existing_destination_never_replaced(self):
        self.output.write_bytes(b'confirmed')
        with self.assertRaises(FileExistsError):
            self.snapshot()
        self.assertEqual(self.output.read_bytes(), b'confirmed')

    def test_publish_race_preserves_winner(self):
        def competing_link(source, destination):
            Path(destination).write_bytes(b'other confirmed writer')
            raise FileExistsError('race')
        with patch.object(evidence.os, 'link', side_effect=competing_link):
            with self.assertRaises(FileExistsError):
                self.snapshot()
        self.assertEqual(self.output.read_bytes(), b'other confirmed writer')
        self.assertEqual(list(self.root.glob('.c1-source-*')), [])

    def test_failure_before_publish_leaves_no_evidence(self):
        with patch.object(evidence, '_member', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.snapshot()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.c1-source-*')), [])

    def test_file_budget_rejects_without_publication(self):
        with self.assertRaisesRegex(ValueError, 'source_budget_exceeded'):
            self.snapshot(max_file_bytes=1)
        self.assertFalse(self.output.exists())

    def test_aggregate_budget_rejects_without_publication(self):
        with self.assertRaisesRegex(ValueError, 'source_budget_exceeded'):
            self.snapshot(max_total_bytes=40)
        self.assertFalse(self.output.exists())

    def test_invalid_budgets(self):
        for value in (0, -1, True, 0.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'source_budget_invalid'):
                self.snapshot(max_file_bytes=value)

    def test_text_suffix_does_not_allow_binary(self):
        self.write('tools/swirl_vf/fake.py', b'text\0binary')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'source_not_text'):
            self.snapshot()
        self.assertFalse(self.output.exists())

    def test_utf8_is_required(self):
        self.write('tools/swirl_vf/fake.py', b'\xff')
        self.commit()
        with self.assertRaises(UnicodeDecodeError):
            self.snapshot()
        self.assertFalse(self.output.exists())

    def test_git_symlink_rejected_without_host_symlink_privileges(self):
        target = self.repo / 'link-target'
        target.write_text('../outside')
        oid = self.git('hash-object', '-w', str(target)).decode().strip()
        self.git('update-index', '--add', '--cacheinfo',
                 '120000,' + oid + ',tools/swirl_vf/link.py')
        self.git('commit', '-qm', 'Original link fixture')
        with self.assertRaisesRegex(ValueError, 'source_not_regular_blob'):
            self.snapshot()

    def test_invalid_revision_never_creates_evidence(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.snapshot(revision='does-not-exist')
        self.assertFalse(self.output.exists())

    def test_old_revision_ignores_new_commit(self):
        old = self.git('rev-parse', 'HEAD').decode().strip()
        self.write('tools/swirl_vf/tools/later.py', '# new\n')
        self.commit()
        result = self.snapshot(revision=old)
        self.assertEqual(result['source_commit'], old)
        self.assertEqual(len(result['files']), 2)


if __name__ == '__main__':
    unittest.main()
