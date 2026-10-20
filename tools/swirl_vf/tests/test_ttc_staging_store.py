"""Crash/replay tests use only original synthetic JSON, never font payloads."""
import copy
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from ttc_staging_contract import StagingError
from ttc_staging_store import BatchStore, atomic_immutable, canonical_bytes
import ttc_staging_store as storage


BINDING = {"source_sha256": "a" * 64, "builder_sha256": "b" * 64,
           "mode": "synthetic", "dependencies": {"fixture": "original-v1"}}


def evidence(store, face=0, start=0, stop=2):
    return {"schema": 1, "source_sha256": BINDING["source_sha256"],
            "recipe_sha256": store.recipe_sha256, "face_index": face,
            "gid_start": start, "gid_stop": stop, "session_finished": True,
            "source_unchanged": True, "request_count": 5,
            "observation_count": (stop - start) * 5, "kind": "synthetic_analytic"}


def records(start=0, stop=2):
    return [{"gid": gid, "original_test_model": [gid, gid + 2]} for gid in range(start, stop)]


class BatchStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="c1-original-staging-")
        self.root = Path(self.tmp.name).resolve()
        self.store = BatchStore(self.root / "private", BINDING, [5, 3], batch_size=2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_32_face_47102_gid_plan_has_no_gap_or_duplicate_and_exact_tail(self):
        store = BatchStore(self.root / "large-plan", BINDING, [47102] * 32, batch_size=64)
        batches = total = 0
        for face in range(32):
            next_gid = 0
            for actual_face, start, stop in store.ranges(face):
                self.assertEqual(actual_face, face)
                self.assertEqual(start, next_gid)
                self.assertLessEqual(stop - start, 64)
                next_gid = stop
                total += stop - start
                batches += 1
            self.assertEqual(next_gid, 47102)
            self.assertEqual(stop - start, 62)
        self.assertEqual((batches, total), (23552, 1507264))
        self.assertFalse((self.root / "large-plan").exists(), "planning must be read-only")

    def test_restored_order_tail_and_idempotent_replay(self):
        with self.store.writer():
            for f, a, b in reversed(list(self.store.ranges())):
                self.assertTrue(self.store.commit(f, a, b, records(a, b), evidence(self.store, f, a, b)))
            snapshot = {p.name: p.read_bytes() for p in (self.store.directory / "receipts").iterdir()}
        other = BatchStore(self.store.directory, BINDING, [5, 3], batch_size=2)
        with other.writer():
            for f, a, b in other.ranges():
                saved, proof = other.restore(f, a, b)
                self.assertEqual(saved, records(a, b))
                self.assertEqual(proof, evidence(other, f, a, b))
                self.assertFalse(other.commit(f, a, b, saved, proof))
            self.assertEqual(other.progress()["staged_glyph_models"], 8)
            self.assertEqual(other.progress()["staged_faces"], 2)
            self.assertFalse(other.progress()["production_accepted"])
        self.assertEqual(snapshot, {p.name: p.read_bytes() for p in (self.store.directory / "receipts").iterdir()})

    def test_requires_writer_and_forbids_reentrant_writer(self):
        with self.assertRaisesRegex(StagingError, "writer_required"):
            self.store.restore(0, 0, 2)
        with self.store.writer():
            with self.assertRaisesRegex(StagingError, "reentrant"):
                with self.store.writer():
                    self.fail("reentrant lock accepted")

    def test_changed_binding_or_plan_cannot_reuse_checkpoint(self):
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
        before = {str(p.relative_to(self.store.directory)): p.read_bytes()
                  for p in self.store.directory.rglob("*.json")}
        for change in ("source_sha256", "builder_sha256", "dependencies"):
            changed = copy.deepcopy(BINDING)
            changed[change] = "c" * 64 if change != "dependencies" else {"fixture": "different"}
            other = BatchStore(self.store.directory, changed, [5, 3], batch_size=2)
            with self.subTest(change=change), self.assertRaisesRegex(StagingError, "recipe_mismatch"):
                with other.writer():
                    pass
        for counts, size, limit in (([4, 3], 2, 64 * 1024**2), ([5, 3], 3, 64 * 1024**2), ([5, 3], 2, 1024)):
            other = BatchStore(self.store.directory, BINDING, counts, batch_size=size, max_payload_bytes=limit)
            with self.assertRaisesRegex(StagingError, "recipe_mismatch"):
                with other.writer():
                    pass
        after = {str(p.relative_to(self.store.directory)): p.read_bytes()
                 for p in self.store.directory.rglob("*.json")}
        self.assertEqual(before, after)

    def test_binding_is_copied_before_caller_mutation(self):
        binding = copy.deepcopy(BINDING)
        store = BatchStore(self.root / "copy", binding, [2], batch_size=2)
        binding["source_sha256"] = "c" * 64
        with store.writer():
            self.assertTrue(store.commit(0, 0, 2, records(), evidence(store)))

    def test_batch_ranges_reject_holes_overlap_reindexing_and_boolean_gids(self):
        with self.store.writer():
            for batch in ((0, 1, 3), (0, 0, 1), (0, 4, 6), (2, 0, 2), (True, 0, 2), (0, 0, True)):
                with self.subTest(batch=batch), self.assertRaises(StagingError):
                    self.store.restore(*batch)
            for rows in ([], records(1, 3), records(0, 3), list(reversed(records())),
                         [{"gid": False}, {"gid": 1}]):
                with self.subTest(rows=rows), self.assertRaisesRegex(StagingError, "gid_coverage"):
                    self.store.commit(0, 0, 2, rows, evidence(self.store))
            self.assertEqual(self.store.progress()["staged_glyph_models"], 0)

    def test_unfinished_wrong_source_and_unbound_transcripts_rejected_before_write(self):
        changes = {"session_finished": False, "source_unchanged": False, "request_count": 0,
                   "observation_count": 1, "source_sha256": "c" * 64,
                   "recipe_sha256": "d" * 64, "face_index": True, "gid_start": 1,
                   "gid_stop": 3, "schema": True}
        with self.store.writer():
            for key, value in changes.items():
                proof = evidence(self.store)
                proof[key] = value
                with self.subTest(key=key), self.assertRaisesRegex(StagingError, "incomplete_batch_session"):
                    self.store.commit(0, 0, 2, records(), proof)
            self.assertFalse(list((self.store.directory / "payloads").iterdir()))

    def test_native_label_alone_never_unlocks_production(self):
        with self.store.writer():
            proof = evidence(self.store)
            proof["kind"] = "native_validated"
            with self.assertRaisesRegex(StagingError, "production_adapter_unavailable"):
                self.store.commit(0, 0, 2, records(), proof)

    def test_conflicting_repeat_is_rejected_without_modifying_confirmed_bytes(self):
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
            before = {p.name: p.read_bytes() for p in self.store.directory.rglob("*.json")}
            changed = records()
            changed[0]["original_test_model"][0] = 999
            with self.assertRaisesRegex(StagingError, "immutable_checkpoint_conflict"):
                self.store.commit(0, 0, 2, changed, evidence(self.store))
            self.assertEqual(before, {p.name: p.read_bytes() for p in self.store.directory.rglob("*.json")})

    def test_crash_between_payload_and_receipt_is_not_accepted_and_retry_recovers(self):
        original = storage.atomic_immutable
        def crash(path, data):
            if path.parent.name == "receipts":
                raise OSError("simulated loss before receipt publication")
            return original(path, data)
        with self.store.writer():
            with mock.patch.object(storage, "atomic_immutable", side_effect=crash):
                with self.assertRaises(OSError):
                    self.store.commit(0, 0, 2, records(), evidence(self.store))
            self.assertEqual(len(list((self.store.directory / "payloads").iterdir())), 1)
            self.assertEqual(self.store.progress()["staged_glyph_models"], 0)
            self.assertIsNone(self.store.restore(0, 0, 2))
        with self.store.writer():
            self.assertTrue(self.store.commit(0, 0, 2, records(), evidence(self.store)))
            self.assertEqual(self.store.progress()["staged_glyph_models"], 2)

    def test_crash_after_receipt_commit_and_before_temporary_unlink_is_resumable(self):
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
            receipt = next((self.store.directory / "receipts").iterdir())
            os.link(receipt, receipt.parent / ".uncommitted-dead-process")
        with self.store.writer():
            self.assertEqual(self.store.progress()["staged_glyph_models"], 2)

    def test_failure_in_later_batch_preserves_previous_confirmed_records(self):
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
            before = self.store.restore(0, 0, 2)
            with self.assertRaises(StagingError):
                self.store.commit(0, 2, 4, records(2, 3), evidence(self.store, 0, 2, 4))
            self.assertEqual(self.store.restore(0, 0, 2), before)
            self.assertEqual(self.store.progress()["staged_faces"], 0)

    def test_corrupted_confirmed_payload_is_not_recomputed_or_overwritten(self):
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
            payload = next((self.store.directory / "payloads").iterdir())
            damaged = payload.read_bytes().replace(b'"original_test_model":[0,2]', b'"original_test_model":[0,3]')
            payload.write_bytes(damaged)
            for operation in (lambda: self.store.restore(0, 0, 2),
                              lambda: self.store.commit(0, 0, 2, records(), evidence(self.store))):
                with self.assertRaisesRegex(StagingError, "payload_hash_mismatch"):
                    operation()
            self.assertEqual(payload.read_bytes(), damaged)

    def test_receipt_missing_payload_and_invalid_json_fail_closed(self):
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
            payload = next((self.store.directory / "payloads").iterdir())
            data = payload.read_bytes()
            payload.unlink()
            with self.assertRaisesRegex(StagingError, "checkpoint_missing"):
                self.store.restore(0, 0, 2)
            for damaged in (b'{"gid":1,"gid":1}', b'{"x":NaN}', b'{"x":', data + b" "):
                payload.write_bytes(damaged)
                with self.subTest(damaged=damaged[:20]), self.assertRaises(StagingError):
                    self.store.restore(0, 0, 2)

    def test_strict_receipt_fields_hashes_and_types(self):
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
            path = next((self.store.directory / "receipts").iterdir())
            good = json.loads(path.read_bytes())
            for field, value in (("payload_sha256", "../wrong"), ("payload_bytes", True),
                                 ("record_count", 1), ("gid_stop", 3), ("face_index", False),
                                 ("schema", 2), ("recipe_sha256", "c" * 64)):
                bad = {**good, field: value}
                path.write_bytes(canonical_bytes(bad))
                with self.subTest(field=field), self.assertRaisesRegex(StagingError, "invalid_batch_receipt"):
                    self.store.restore(0, 0, 2)

    def test_payload_cap_and_nonfinite_values_are_rejected(self):
        store = BatchStore(self.root / "capped", BINDING, [1], batch_size=1, max_payload_bytes=1024)
        with store.writer():
            with self.assertRaisesRegex(StagingError, "size_limit"):
                store.commit(0, 0, 1, [{"gid": 0, "data": "x" * 1500}], evidence(store, 0, 0, 1))
            for value in (float("nan"), float("inf"), object()):
                with self.assertRaisesRegex(StagingError, "noncanonical_json"):
                    store.commit(0, 0, 1, [{"gid": 0, "data": value}], evidence(store, 0, 0, 1))

    def test_reader_rejects_oversized_receipt_before_decoding(self):
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
            path = next((self.store.directory / "receipts").iterdir())
            path.write_bytes(b" " * 16385)
            with self.assertRaisesRegex(StagingError, "size_limit"):
                self.store.restore(0, 0, 2)

    def test_initialization_after_crash_preserves_orphan_temporary(self):
        self.store.directory.mkdir()
        orphan = self.store.directory / ".uncommitted-dead-process"
        orphan.write_bytes(b"untrusted incomplete original test payload")
        with self.store.writer():
            self.assertEqual(self.store.progress()["staged_glyph_models"], 0)
        self.assertTrue(orphan.exists())

    def test_existing_unbound_directory_is_not_adopted(self):
        self.store.directory.mkdir()
        (self.store.directory / "unrelated.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(StagingError, "recipe_missing"):
            with self.store.writer():
                pass

    def test_symlink_ancestors_and_payloads_are_rejected(self):
        # On Windows the hosted runner supports Developer Mode symlinks; a
        # caller lacking that privilege still exercises the non-link cases.
        target = self.root / "target"
        target.mkdir()
        link = self.root / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            return
        with self.assertRaisesRegex(StagingError, "symlink"):
            BatchStore(link / "child", BINDING, [1])
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
            path = next((self.store.directory / "payloads").iterdir())
            outside = self.root / "outside"
            path.rename(outside)
            path.symlink_to(outside)
            with self.assertRaisesRegex(StagingError, "symlink"):
                self.store.restore(0, 0, 2)

    def test_real_process_lock_blocks_concurrent_writer_and_releases_after_termination(self):
        script = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from ttc_staging_store import BatchStore
store=BatchStore(Path(sys.argv[2]),json.loads(sys.argv[3]),[5,3],batch_size=2)
with store.writer():
    print('LOCKED',flush=True)
    sys.stdin.read()
"""
        process = subprocess.Popen([sys.executable, "-c", script, str(TOOLS), str(self.store.directory),
                                    json.dumps(BINDING)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        messages = queue.Queue()
        reader = threading.Thread(target=lambda: messages.put(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            self.assertEqual(messages.get(timeout=15).strip(), "LOCKED")
            with self.assertRaisesRegex(StagingError, "writer_busy"):
                with self.store.writer():
                    pass
        finally:
            process.terminate()
            process.communicate(timeout=15)
        with self.store.writer():
            self.assertTrue(self.store.commit(0, 0, 2, records(), evidence(self.store)))

    def test_nonfinite_boolean_empty_and_oversized_plans_rejected(self):
        for counts, batch, limit in (([], 2, 1024), ([0], 2, 1024), ([65536], 2, 1024),
                                     ([True], 2, 1024), ([1], True, 1024), ([1], 0, 1024),
                                     ([1], 2, 10), ([1], 2, 2**40)):
            with self.subTest(counts=counts, batch=batch, limit=limit), self.assertRaises(StagingError):
                BatchStore(self.root / "invalid", BINDING, counts, batch_size=batch, max_payload_bytes=limit)

    def test_valid_numeric_corruption_of_finished_session_is_detected(self):
        with self.store.writer():
            self.store.commit(0, 0, 2, records(), evidence(self.store))
            path = next((self.store.directory / "receipts").iterdir())
            changed = json.loads(path.read_bytes())
            changed["evidence"]["request_count"] += 1
            path.write_bytes(canonical_bytes(changed))
            with self.assertRaisesRegex(StagingError, "receipt_hash_mismatch"):
                self.store.restore(0, 0, 2)

    def test_oversized_recipe_rejected_before_creating_any_directory(self):
        path = self.root / "large-recipe"
        with self.assertRaisesRegex(StagingError, "recipe_size_limit"):
            BatchStore(path, {**BINDING, "data": "x" * (4 * 1024**2)}, [1])
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
