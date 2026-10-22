"""Actual writer interleavings for the existing whole-face checkpoint path.

The accepted-face proofs below are explicitly synthetic test doubles. No
native equivalence or Apple outline acceptance is granted by storage tests.
"""
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

from fontTools.ttLib import TTCollection, TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import rebuild
from test_rebuild import write_fixture


class CheckpointWriterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root/'source.ttc'
        write_fixture(self.source, faces=2)
        self.executable = self.root/'analytic-oracle'
        self.executable.write_text('synthetic identity only')
        with TTCollection(self.source) as collection:
            self.identities = rebuild.checkpoint_source_faces(collection.fonts)
            self.paths = []
            for index, font in enumerate(collection.fonts):
                path = self.root/f'face{index}.ttf'
                font.save(path)
                self.paths.append(path)
        self.directory = self.root/'checkpoints'

    def writer(self):
        return rebuild.FaceCheckpoints(self.directory, self.source, self.executable,
                                       (), {}, self.identities)

    def report(self, writer, index, path=None):
        recipe = writer.state['recipe']
        summary = {'type': 'summary', 'source_sha256': recipe['source_sha256'],
                   'error_count': 0, 'request_count': 1, 'successful_glyph_count': 3,
                   'synthetic_test_double_only': True}
        proof = {'status': 'PASS', 'session_index': index+1, 'face_index': index,
                 **{key: recipe[key] for key in ('source_sha256', 'source_identity_sha256', 'oracle_sha256')},
                 'source_face_identity_sha256': recipe['source_face_identity_sha256'][index],
                 'source_unchanged': True, 'native_metadata_verified_against_all_source_tables': True,
                 'native_summary_eof_exit_accepted': True, 'request_count': 1,
                 'successful_glyph_count': 3, 'summary': summary}
        return {'face_index': index, 'glyph_count': 3, 'glyphs_completed': 3,
                'serialized_model_verification': {'status': 'PASS', 'glyphs_checked': 3},
                'serialized_model_sha256': rebuild.sha256(self.paths[index] if path is None else path),
                'native_face_transcript': proof}

    def test_stale_writer_preserves_both_confirmed_faces(self):
        first, second = self.writer(), self.writer()
        first.save(0, self.paths[0], self.report(first, 0))
        second.save(1, self.paths[1], self.report(second, 1))
        saved = json.loads(first.manifest.read_text())
        self.assertEqual(set(saved['faces']), {'0', '1'})
        with TTCollection(self.source) as collection:
            # Even the stale reader must see the independently committed face.
            self.assertIsNotNone(first.restore(1, collection.fonts[1]))
            self.assertIsNotNone(second.restore(0, collection.fonts[0]))

    def test_confirmed_face_conflict_is_refused_without_replacing_manifest(self):
        first, second = self.writer(), self.writer()
        report = self.report(first, 0)
        first.save(0, self.paths[0], report)
        before = first.manifest.read_bytes()
        first.save(0, self.paths[0], report)  # Identical publication is idempotent.
        with TTFont(self.paths[0], recalcTimestamp=False) as font:
            font['hhea'].ascent += 1
            font.save(self.root/'different.ttf')
        with self.assertRaisesRegex(rebuild.ReconstructionError, 'confirmed checkpoint face differs'):
            second.save(0, self.root/'different.ttf', self.report(second, 0, self.root/'different.ttf'))
        self.assertEqual(first.manifest.read_bytes(), before)

    def test_missing_or_wrong_serialized_hash_cannot_authorize_a_checkpoint(self):
        writer = self.writer()
        before = writer.manifest.read_bytes()
        for value in (None, '0' * 64):
            report = self.report(writer, 0)
            if value is None:
                del report['serialized_model_sha256']
            else:
                report['serialized_model_sha256'] = value
            with self.subTest(value=value), self.assertRaisesRegex(
                    rebuild.ReconstructionError, 'serialized model changed after verification'):
                writer.save(0, self.paths[0], report)
            self.assertEqual(writer.manifest.read_bytes(), before)
            self.assertFalse(list(self.directory.glob('*.ttf')))

    def test_changed_recipe_is_not_overwritten_by_a_stale_writer(self):
        first, second = self.writer(), self.writer()
        changed = json.loads(first.manifest.read_text())
        changed['recipe']['settings']['externally_changed'] = True
        first.manifest.write_text(json.dumps(changed))
        before = first.manifest.read_bytes()
        with self.assertRaisesRegex(rebuild.ReconstructionError, 'checkpoint recipe differs'):
            second.save(1, self.paths[1], self.report(second, 1))
        self.assertEqual(first.manifest.read_bytes(), before)
        self.assertFalse(list(self.directory.glob('*.ttf')))

    def test_native_process_lock_refuses_competitor_and_releases_on_death(self):
        writer = self.writer()
        before = writer.manifest.read_bytes()
        code = ('import sys;sys.path.insert(0, ' + repr(str(Path(rebuild.__file__).parent)) + ')\n'
                'from pathlib import Path\nfrom rebuild import checkpoint_writer\n'
                'with checkpoint_writer(Path(sys.argv[1])):\n'
                ' sys.stdout.buffer.write(b"READY\\n")\n sys.stdout.buffer.flush()\n'
                ' sys.stdin.buffer.read(1)\n')
        child = subprocess.Popen([sys.executable, '-c', code, str(self.directory)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        ready = queue.Queue()
        reader = threading.Thread(target=lambda: ready.put(child.stdout.readline()), daemon=True)
        reader.start()
        try:
            self.assertEqual(ready.get(timeout=10), b'READY\n')
            with self.assertRaisesRegex(rebuild.ReconstructionError, 'checkpoint writer busy'):
                writer.save(0, self.paths[0], self.report(writer, 0))
            with self.assertRaisesRegex(rebuild.ReconstructionError, 'checkpoint writer busy'):
                self.writer()
            self.assertEqual(writer.manifest.read_bytes(), before)
            self.assertFalse(list(self.directory.glob('*.ttf')))
            child.kill()
            child.wait(timeout=10)
            writer.save(0, self.paths[0], self.report(writer, 0))
            self.assertEqual(set(json.loads(writer.manifest.read_text())['faces']), {'0'})
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            child.stdin.close()
            child.stdout.close()
            reader.join(timeout=10)

    def test_lock_alias_cannot_modify_an_unrelated_file(self):
        writer = self.writer()
        lock = self.directory/'.writer.lock'
        # Remove only this test's own unused lock and replace it with an alias.
        lock.unlink()
        sentinel = self.root/'keep.txt'
        sentinel.write_bytes(b'keep these user bytes')
        lock.hardlink_to(sentinel)
        with self.assertRaisesRegex(rebuild.ReconstructionError, 'invalid checkpoint writer lock'):
            writer.save(0, self.paths[0], self.report(writer, 0))
        self.assertEqual(sentinel.read_bytes(), b'keep these user bytes')


if __name__ == '__main__':
    unittest.main()
