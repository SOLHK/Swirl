#!/usr/bin/env python3
"""Boundary controls for the read-only current PR61 archive reader.

All fixtures are generated locally. No API, download, product executable,
subscription, system proxy or original private ledger is used.
"""
from __future__ import annotations

import base64
import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ReadCurrentPr61Artifacts as reader

HEAD, MERGE, PRODUCER, TREE = "1" * 40, "2" * 40, "3" * 40, "4" * 40


def identity():
    return {"head": HEAD, "base": reader.BASE, "merge": MERGE, "tree": TREE}


def event():
    return {
        "action": "labeled", "label": {"name": reader.LABEL}, "number": 61,
        "repository": {"id": reader.REPOSITORY_ID, "full_name": reader.REPOSITORY},
        "pull_request": {
            "number": 61, "merge_commit_sha": MERGE,
            "head": {"sha": HEAD, "ref": reader.BRANCH,
                     "repo": {"id": reader.REPOSITORY_ID, "full_name": reader.REPOSITORY}},
            "base": {"sha": reader.BASE, "ref": "test", "repo": {"id": reader.REPOSITORY_ID}},
        },
    }


def run(conclusion="success"):
    return {
        "id": 10, "workflow_id": reader.WORKFLOWS["ui"][0],
        "path": reader.WORKFLOWS["ui"][1], "head_sha": HEAD,
        "head_branch": reader.BRANCH, "event": "pull_request",
        "repository": {"id": reader.REPOSITORY_ID},
        "head_repository": {"id": reader.REPOSITORY_ID},
        "run_attempt": 1, "status": "completed", "conclusion": conclusion,
        "pull_requests": [{"number": 61, "head": {"sha": HEAD, "ref": reader.BRANCH},
                          "base": {"sha": reader.BASE, "ref": "test"}}],
    }


def artifact():
    return {
        "id": 20, "name": reader.ARTIFACTS["installer"], "expired": False,
        "size_in_bytes": 10, "digest": "sha256:" + "a" * 64,
        "expires_at": "2099-01-01T00:00:00Z",
        "workflow_run": {"id": 10, "repository_id": reader.REPOSITORY_ID,
                         "head_repository_id": reader.REPOSITORY_ID,
                         "head_sha": HEAD, "head_branch": reader.BRANCH},
    }


class CurrentReaderTests(unittest.TestCase):
    def test_event_rejects_wrong_label_fork_branch_base_and_merge(self):
        self.assertEqual(reader.validate_event(event(), MERGE)["head"], HEAD)
        variants = []
        for field, value in (("action", "synchronize"), ("number", 62)):
            item = event()
            item[field] = value
            variants.append(item)
        item = event()
        item["label"]["name"] = "qa-pr61-artifact-read"
        variants.append(item)
        for side, field, value in (("head", "ref", "main"), ("head", "sha", "bad"),
                                   ("base", "ref", "main"), ("base", "sha", "5" * 40)):
            item = event()
            item["pull_request"][side][field] = value
            variants.append(item)
        item = event()
        item["pull_request"]["head"]["repo"]["id"] += 1
        variants.append(item)
        item = event()
        item["pull_request"]["merge_commit_sha"] = HEAD
        variants.append(item)
        for item in variants:
            with self.subTest(item=item), self.assertRaises(reader.EvidenceError):
                reader.validate_event(item, MERGE)

    def test_merge_requires_exact_parent_order_and_content_tree(self):
        head = {"sha": HEAD, "tree": {"sha": TREE}}
        merged = {"sha": MERGE, "tree": {"sha": TREE},
                  "parents": [{"sha": reader.BASE}, {"sha": HEAD}]}
        self.assertEqual(reader.validate_tree(identity(), head, merged)["tree"], TREE)
        for bad in (
            {**merged, "parents": list(reversed(merged["parents"]))},
            {**merged, "tree": {"sha": "5" * 40}},
            {**merged, "parents": [{"sha": HEAD}]},
        ):
            with self.subTest(bad=bad), self.assertRaises(reader.EvidenceError):
                reader.validate_tree(identity(), head, bad)

    def test_run_requires_completed_exact_first_attempt_and_pr(self):
        self.assertEqual(reader.validate_run(run(), "ui", identity())["id"], 10)
        for field, value in (
            ("status", "in_progress"), ("conclusion", None), ("run_attempt", 2), ("run_attempt", True),
            ("workflow_id", 999), ("path", ".github/workflows/unknown.yml"),
            ("head_sha", MERGE), ("head_branch", "main"), ("event", "push"),
            ("pull_requests", []),
        ):
            bad = run()
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(reader.EvidenceError):
                reader.validate_run(bad, "ui", identity())

    def test_original_failure_and_cancellation_are_preserved(self):
        for conclusion in ("failure", "cancelled", "timed_out"):
            original = run(conclusion)
            before = copy.deepcopy(original)
            self.assertEqual(reader.validate_run(original, "ui", identity())["conclusion"], conclusion)
            self.assertEqual(original, before)

    def test_paginated_or_incomplete_api_lists_fail_closed(self):
        self.assertEqual(reader.complete_listing({"total_count": 1, "items": [1]}, "items", "x"), [1])
        for bad in ({"total_count": 101, "items": []},
                    {"total_count": 2, "items": [1]},
                    {"total_count": True, "items": [1]},
                    {"total_count": 0, "items": None}):
            with self.subTest(bad=bad), self.assertRaises(reader.EvidenceError):
                reader.complete_listing(bad, "items", "x")

    def test_artifact_ownership_digest_size_expiry_and_endpoint_are_bound(self):
        now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        self.assertEqual(reader.validate_artifact(artifact(), "installer", run(), identity(), now)["artifact"], 20)
        variants = []
        for field, value in (("name", "unrelated"), ("expired", True), ("size_in_bytes", 0),
                             ("size_in_bytes", reader.MAX_ZIP + 1), ("digest", "md5:" + "a" * 32),
                             ("expires_at", "2020-01-01T00:00:00Z"),
                             ("expires_at", "2099-01-01T00:00:00")):
            item = artifact()
            item[field] = value
            variants.append(item)
        for field, value in (("id", 11), ("repository_id", 1), ("head_sha", MERGE),
                             ("head_branch", "main"), ("head_repository_id", 1)):
            item = artifact()
            item["workflow_run"][field] = value
            variants.append(item)
        for bad in variants:
            with self.subTest(bad=bad), self.assertRaises(reader.EvidenceError):
                reader.validate_artifact(bad, "installer", run(), identity(), now)

    def scan(self, entries, kind="controlled", mutate=None, **limits):
        with tempfile.TemporaryDirectory(prefix="swirl-current-reader-") as directory:
            root = Path(directory)
            archive, output = root / "original.zip", root / "evidence"
            output.mkdir()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z:
                    for name, data in entries:
                        z.writestr(name, data)
            if mutate:
                mutate(archive)
            before = archive.read_bytes()
            log = io.StringIO()
            with contextlib.ExitStack() as stack:
                for key, value in limits.items():
                    stack.enter_context(mock.patch.object(reader, key, value))
                stack.enter_context(mock.patch.object(reader, "api", side_effect=AssertionError("No API in archive controls")))
                stack.enter_context(mock.patch.object(reader, "download", side_effect=AssertionError("No downloads in archive controls")))
                stack.enter_context(mock.patch.object(reader.subprocess, "run",
                                                      side_effect=AssertionError("No executable content")))
                stack.enter_context(contextlib.redirect_stdout(log))
                report, originals = reader.scan_archive(archive, kind, output)
            self.assertEqual(archive.read_bytes(), before, "Reading must preserve the original ZIP")
            return report, originals, log.getvalue()

    @staticmethod
    def controlled_entries():
        names = ("positive", "wrong-ca", "stall", "native-watchdog-500ms",
                 "missing-proof", "missing-fixture", "preexisting-store", "wrong-proof")
        return [(n + ".json", b"\xef\xbb\xbf{\r\n  \"value\": 1\r\n}\r\n") for n in names]

    def test_original_bom_crlf_bytes_and_chunk_digests_are_preserved(self):
        entries = self.controlled_entries()
        entries[0] = ("positive.json", b'\xef\xbb\xbf{"text":"' + "\u6c49".encode("utf-8") * 3000 + b'"}\r\n')
        report, originals, log = self.scan(entries)
        self.assertTrue(report["all_members_crc_verified"])
        self.assertEqual(report["selection_errors"], [])
        self.assertEqual(originals, dict(entries))
        records = []
        chunks = {}
        for line in log.splitlines():
            prefix, payload = line.split(" ", 1)
            data = json.loads(payload)
            if prefix == "SWIRL_CURRENT_MEMBER":
                records.append(data)
            if prefix == "SWIRL_CURRENT_CHUNK":
                chunks.setdefault(data["path"], {})[data["index"]] = data
        self.assertEqual(len(records), 8)
        for record in records:
            blocks = chunks[record["path"]]
            self.assertEqual(sorted(blocks), list(range(record["blocks"])))
            raw = b"".join(base64.b64decode(blocks[i]["data"], validate=True) for i in range(record["blocks"]))
            self.assertEqual(raw, originals[record["path"]])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
            self.assertEqual(len(raw), record["bytes"])

    def test_missing_expected_text_is_reported_without_inventing_results(self):
        report, originals, _ = self.scan(self.controlled_entries()[:1])
        self.assertTrue(report["all_members_crc_verified"])
        self.assertEqual(len(report["selection_errors"]), 7)
        self.assertEqual(set(originals), {"positive.json"})

    def test_installer_digest_is_of_downloaded_member_bytes(self):
        payload = b"MZ" + bytes(range(256)) * 32
        report, originals, _ = self.scan([("Swirl-Setup.exe", payload)], kind="installer")
        self.assertEqual(originals, {})
        self.assertEqual(report["inventory"], [{"path": "Swirl-Setup.exe", "bytes": len(payload),
                                              "sha256": hashlib.sha256(payload).hexdigest()}])
        with self.assertRaises(reader.EvidenceError):
            self.scan([("Swirl-Setup.exe", payload), ("extra.exe", payload)], kind="installer")

    def test_traversal_absolute_backslash_and_symbolic_link_are_rejected(self):
        for name in ("../escaped.json", "/absolute.json", "a\\b.json", "C:evil.json"):
            with self.subTest(name=name), self.assertRaises(reader.EvidenceError):
                self.scan([(name, b"{}")])
        link = zipfile.ZipInfo("link.json")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(reader.EvidenceError):
            self.scan([(link, b"target")])

    def test_duplicate_and_casefold_ambiguous_members_are_rejected(self):
        for other in ("positive.json", "POSITIVE.JSON"):
            with self.subTest(other=other), self.assertRaises(reader.EvidenceError):
                self.scan([("positive.json", b"{}"), (other, b"{}")])

    def test_corrupt_unselected_member_crc_is_not_skipped(self):
        def corrupt(path):
            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo("unselected.bin")
                offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
            data = bytearray(path.read_bytes())
            data[offset] ^= 0xFF
            path.write_bytes(data)
        with self.assertRaises(zipfile.BadZipFile):
            self.scan(self.controlled_entries() + [("unselected.bin", b"unique-data")], mutate=corrupt)

    def test_member_expansion_and_selected_text_limits_fail_closed(self):
        for limits in ({"MAX_MEMBERS": 1}, {"MAX_EXPANDED": 2},
                       {"MAX_SELECTED_TEXT": 1}, {"MAX_TEXT_MEMBER": 1}):
            with self.subTest(limits=limits), self.assertRaises(reader.EvidenceError):
                self.scan(self.controlled_entries(), **limits)

    def test_ambiguous_suffix_and_exact_final_delivery_are_not_substituted(self):
        selected, missing = reader.choose_members("engine", {
            "one/full-regression.xml", "two/full-regression.xml"})
        self.assertNotIn("one/full-regression.xml", selected)
        self.assertIn("missing-or-ambiguous:full-regression.xml", missing)
        selected, missing = reader.choose_members("package", {"snapshot/out/delivery.json"})
        self.assertNotIn("snapshot/out/delivery.json", selected)
        self.assertIn("out/delivery.json", missing)

    def test_cross_version_proxy_diagnostics_requires_exact_path_and_original_bytes(self):
        expected = "build-evidence/cross-version-installer-lifecycle/proxy-diagnostics.json"
        alternatives = (
            "proxy-diagnostics.json",
            "snapshot/" + expected,
            "build-evidence/normal-installer-lifecycle/proxy-diagnostics.json",
            "build-evidence/cross-version-installer-lifecycle/nested/proxy-diagnostics.json",
        )
        raw = b'\xef\xbb\xbf{\r\n  "schema": 1, "synthetic_control": true\r\n}\r\n'
        entries = [(expected, raw)] + [(name, b'{}') for name in alternatives]
        report, originals, _ = self.scan(entries, kind="package")
        self.assertTrue(report["all_members_crc_verified"])
        self.assertNotIn(expected, report["selection_errors"])
        self.assertEqual(originals, {expected: raw})
        self.assertEqual(report["selected_members"], [
            {"path": expected, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}])
        for name in (*alternatives, "unrelated.json"):
            with self.subTest(missing_expected_with=name):
                report, originals, _ = self.scan([(name, raw)], kind="package")
                self.assertTrue(report["all_members_crc_verified"])
                self.assertIn(expected, report["selection_errors"])
                self.assertEqual(originals, {})

    def test_producer_merge_is_verified_separately_from_reader_merge(self):
        qt_data = json.dumps({"source_sha": PRODUCER, "status": "complete"}).encode()
        delivery = {"source_sha": PRODUCER, "pr_head_sha": HEAD, "source_tree_sha": TREE,
                    "version": "0.2.40", "qt": "6.12.0", "installer_sha256": "a" * 64,
                    "qt_source_manifest_sha256": hashlib.sha256(qt_data).hexdigest()}
        originals = {
            "out/delivery.json": json.dumps(delivery).encode(),
            "installer-bin/package-manifest.json": json.dumps({"source_sha": PRODUCER}).encode(),
            "out/qt-corresponding-source/qt-source-bundle.json": qt_data,
        }
        commit = {"sha": PRODUCER, "tree": {"sha": TREE},
                  "parents": [{"sha": reader.BASE}, {"sha": HEAD}]}
        with mock.patch.object(reader, "api", return_value=commit) as request:
            result = reader.package_source(originals, identity(), "not-a-credential")
            self.assertTrue(result["verified"])
            self.assertNotEqual(result["producer_source_sha"], result["reader_source_sha"])
            self.assertEqual(request.call_args.args[0],
                             "/repos/" + reader.REPOSITORY + "/git/commits/" + PRODUCER)
        bad = {**commit, "parents": [{"sha": HEAD}, {"sha": reader.BASE}]}
        with mock.patch.object(reader, "api", return_value=bad), self.assertRaises(reader.EvidenceError):
            reader.package_source(originals, identity(), "not-a-credential")
        damaged = dict(originals)
        damaged["out/qt-corresponding-source/qt-source-bundle.json"] += b"\n"
        with mock.patch.object(reader, "api", return_value=commit), self.assertRaises(reader.EvidenceError):
            reader.package_source(damaged, identity(), "not-a-credential")



    def test_duplicate_and_nonstandard_evidence_json_are_rejected(self):
        for raw in (b'{"source_sha":"first","source_sha":"second"}',
                    b'{"count":NaN}', b'{"count":Infinity}', b'{"nested":{"x":1,"x":2}}'):
            with self.subTest(raw=raw), self.assertRaises(reader.EvidenceError):
                reader.decode_json(raw)

    def test_unsupported_zip_compression_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="swirl-current-compression-") as directory:
            root = Path(directory)
            archive, output = root / "unsupported.zip", root / "evidence"
            output.mkdir()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_BZIP2) as zipped:
                zipped.writestr("positive.json", b"{}")
            with self.assertRaises(reader.EvidenceError), contextlib.redirect_stdout(io.StringIO()):
                reader.scan_archive(archive, "controlled", output)



    def test_malformed_json_is_preserved_but_not_accepted_as_complete_evidence(self):
        for raw, code in (
            (b'{"source_sha":"one","source_sha":"two"}', "DuplicateEvidenceJsonKey"),
            (b'{"value":"\xff"}', "InvalidEvidenceJson"),
            (b'{"value":NaN}', "NonstandardEvidenceJsonNumber"),
            (b'{"value":', "InvalidEvidenceJson"),
        ):
            with self.subTest(raw=raw):
                entries = self.controlled_entries()
                entries[0] = ("positive.json", raw)
                report, originals, log = self.scan(entries)
                self.assertTrue(report["all_members_crc_verified"])
                self.assertEqual(report["selection_errors"], [])
                self.assertEqual(report["json_errors"], [{"path": "positive.json", "code": code}])
                self.assertEqual(originals["positive.json"], raw)
                self.assertIn("SWIRL_CURRENT_CHUNK", log)

    def test_private_text_export_excludes_grants_keys_and_environment(self):
        names = {"receipt.json", "logs/build.log", "logs/tests.log",
                 "grants/session.json", "environment.json", "fixture-key.pem",
                 "logs/arbitrary.log"}
        selected, _ = reader.choose_members("private", names)
        self.assertEqual(selected, {"receipt.json", "logs/build.log", "logs/tests.log"})



    @staticmethod
    def all_runs():
        result = {}
        for index, (kind, (workflow_id, path)) in enumerate(reader.WORKFLOWS.items(), 10):
            value = run()
            value.update(id=index, workflow_id=workflow_id, path=path)
            result[kind] = value
        return result

    def test_final_revalidation_preserves_exact_completed_first_attempts(self):
        originals = self.all_runs()
        by_id = {r["id"]: r for r in originals.values()}
        before = copy.deepcopy(originals)
        with tempfile.TemporaryDirectory(prefix="swirl-run-stability-") as directory:
            out = Path(directory)
            with mock.patch.object(reader, "api",
                    side_effect=lambda path, token: copy.deepcopy(by_id[int(path.rsplit("/", 1)[-1])])) as request:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertTrue(reader.revalidate_runs(originals, identity(), "not-a-credential", out))
                self.assertEqual(request.call_count, 8)
            self.assertEqual(len(list(out.glob("original-run-*-at-completion.json"))), 8)
        self.assertEqual(originals, before)

    def test_rerun_during_acquisition_revokes_current_eligibility_and_keeps_evidence(self):
        originals = self.all_runs()
        before = copy.deepcopy(originals)
        by_id = {r["id"]: copy.deepcopy(r) for r in originals.values()}
        by_id[originals["ui"]["id"]].update(run_attempt=2, status="in_progress", conclusion=None)
        with tempfile.TemporaryDirectory(prefix="swirl-rerun-evidence-") as directory:
            out = Path(directory)
            with mock.patch.object(reader, "api",
                    side_effect=lambda path, token: copy.deepcopy(by_id[int(path.rsplit("/", 1)[-1])])) as request:
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(
                        reader.EvidenceError, "CurrentProducerChangedDuringRead"):
                    reader.revalidate_runs(originals, identity(), "not-a-credential", out)
                self.assertEqual(request.call_count, 8)
            changed = json.loads((out / "original-run-ui-at-completion.json").read_text("utf-8"))
            self.assertEqual(changed["run_attempt"], 2)
            self.assertEqual(len(list(out.glob("original-run-*-at-completion.json"))), 8)
        self.assertEqual(originals, before)
        self.assertEqual(originals["ui"]["conclusion"], "success")

    def test_index_survives_unexpected_installer_members(self):
        with tempfile.TemporaryDirectory(prefix="swirl-reader-index-") as directory:
            root = Path(directory)
            archive, out = root / "original.zip", root / "evidence"
            out.mkdir()
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("Swirl-Setup.exe", b"MZfixture")
                zipped.writestr("unexpected.bin", b"also-original")
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(reader.EvidenceError):
                reader.scan_archive(archive, "installer", out)
            index = json.loads((out / "member-index.json").read_text("utf-8"))
            self.assertEqual({r["path"] for r in index}, {"Swirl-Setup.exe", "unexpected.bin"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
