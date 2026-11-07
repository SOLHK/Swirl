#!/usr/bin/env python3
"""Read the current PR61 CI archives without executing their contents.

The reader and producer identities are recorded separately. Archive integrity
does not change any original workflow conclusion or establish live acceptance.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from ReadPr61ArtifactEvidence import (
    BRANCH, REPOSITORY, REPOSITORY_ID, EvidenceError, api, download,
    require, safe_member, write_json,
)

LABEL = "qa-pr61-current-evidence"
BASE = "acd7005c99a99c4f81b62d328fcc15883d51b62a"
WORKFLOWS = {
    "ui": (380316715, ".github/workflows/build-qt-quick-ui.yml"),
    "rust": (386980783, ".github/workflows/rust-core.yml"),
    "qt_http": (393587329, ".github/workflows/qt-network-security.yml"),
    "isolated_tun": (401010502, ".github/workflows/native-tun-isolated.yml"),
    "native_tun": (400977261, ".github/workflows/native-tun.yml"),
    "lan": (402634905, ".github/workflows/native-lan.yml"),
    "fonts": (388637416, ".github/workflows/font-system-windows.yml"),
    "source": (379741604, ".github/workflows/build-windows.yml"),
}
ARTIFACTS = {
    "node": "Swirl-Node-Regression-Evidence",
    "controlled": "Swirl-Controlled-Node-Session-Evidence",
    "engine": "Swirl-Engine-Test-Evidence",
    "package": "Swirl-Qt612-Package-Evidence",
    "private": "Swirl-Private-Qt-Quota-Evidence",
    "installer": "Swirl-Windows-Installer-EXE",
    "qt_source": "Swirl-Qt-Corresponding-Source",
}
TERMINAL = {"success", "failure", "cancelled", "timed_out",
            "action_required", "neutral", "skipped", "stale"}
MAX_ZIP = 512 * 1024 * 1024
MAX_MEMBERS = 10000
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
MAX_TEXT_MEMBER = 2 * 1024 * 1024
MAX_SELECTED_TEXT = 6 * 1024 * 1024
MAX_SELECTED_MEMBERS = 250
BLOCK_BYTES = 3072
_NAMESPACE = "unbound"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def emit(kind, value):
    # Every record is scoped to one producer artifact; text is always base64.
    print("SWIRL_CURRENT_" + kind + " " + json.dumps(
        {"namespace": _NAMESPACE, **value}, ensure_ascii=True, separators=(",", ":")), flush=True)


def decode_json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "DuplicateEvidenceJsonKey")
            result[key] = value
        return result

    def invalid_constant(value):
        raise EvidenceError("NonstandardEvidenceJsonNumber")

    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=invalid_constant)


def positive_integer(value):
    return type(value) is int and value > 0


def sha(value, length=40):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is not None


def complete_listing(value, field, code):
    require(type(value.get("total_count")) is int
            and 0 <= value["total_count"] <= 100
            and isinstance(value.get(field), list)
            and value["total_count"] == len(value[field]), code)
    return value[field]


def validate_event(event, reader_sha):
    pr = event.get("pull_request", {})
    head, base = pr.get("head", {}), pr.get("base", {})
    require(event.get("action") == "labeled" and event.get("label", {}).get("name") == LABEL
            and event.get("number") == 61 and pr.get("number") == 61
            and event.get("repository", {}).get("id") == REPOSITORY_ID
            and event.get("repository", {}).get("full_name") == REPOSITORY
            and head.get("ref") == BRANCH and head.get("repo", {}).get("id") == REPOSITORY_ID
            and head.get("repo", {}).get("full_name") == REPOSITORY
            and base.get("ref") == "test" and base.get("sha") == BASE
            and base.get("repo", {}).get("id") == REPOSITORY_ID
            and sha(head.get("sha")) and sha(reader_sha)
            and pr.get("merge_commit_sha") == reader_sha, "CurrentReaderEventRejected")
    return {"head": head["sha"], "base": BASE, "merge": reader_sha}


def validate_tree(identity, head, merge):
    require(head.get("sha") == identity["head"] and merge.get("sha") == identity["merge"]
            and sha(head.get("tree", {}).get("sha"))
            and merge.get("tree", {}).get("sha") == head["tree"]["sha"]
            and [p.get("sha") for p in merge.get("parents", [])]
            == [identity["base"], identity["head"]], "CurrentMergeIdentityMismatch")
    return {**identity, "tree": head["tree"]["sha"]}


def validate_run(run, kind, identity):
    workflow_id, path = WORKFLOWS[kind]
    prs = run.get("pull_requests")
    require(positive_integer(run.get("id")) and run.get("workflow_id") == workflow_id
            and run.get("path") == path and run.get("head_sha") == identity["head"]
            and run.get("head_branch") == BRANCH and run.get("event") == "pull_request"
            and run.get("repository", {}).get("id") == REPOSITORY_ID
            and run.get("head_repository", {}).get("id") == REPOSITORY_ID
            and type(run.get("run_attempt")) is int and run["run_attempt"] == 1
            and run.get("status") == "completed"
            and run.get("conclusion") in TERMINAL
            and isinstance(prs, list) and len(prs) == 1
            and prs[0].get("number") == 61
            and prs[0].get("head", {}).get("sha") == identity["head"]
            and prs[0].get("head", {}).get("ref") == BRANCH
            and prs[0].get("base", {}).get("sha") == identity["base"]
            and prs[0].get("base", {}).get("ref") == "test",
            "CurrentWorkflowIdentityOrCompletionMismatch")
    return run


def validate_artifact(artifact, kind, run, identity, now):
    owner = artifact.get("workflow_run", {})
    require(positive_integer(artifact.get("id"))
            and artifact.get("name") == ARTIFACTS[kind]
            and artifact.get("expired") is False
            and positive_integer(artifact.get("size_in_bytes"))
            and artifact["size_in_bytes"] <= MAX_ZIP
            and isinstance(artifact.get("digest"), str)
            and re.fullmatch("sha256:[0-9a-f]{64}", artifact["digest"]) is not None
            and owner.get("id") == run["id"]
            and owner.get("repository_id") == REPOSITORY_ID
            and owner.get("head_repository_id") == REPOSITORY_ID
            and owner.get("head_sha") == identity["head"]
            and owner.get("head_branch") == BRANCH, "CurrentArtifactIdentityMismatch")
    try:
        expires = dt.datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
        require(expires.tzinfo is not None and expires > now, "CurrentArtifactExpired")
    except (KeyError, TypeError, ValueError):
        raise EvidenceError("CurrentArtifactExpiryInvalid") from None
    return {"artifact": artifact["id"], "bytes": artifact["size_in_bytes"],
            "sha256": artifact["digest"][7:]}


def acquire_source(repo, token):
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_EVENT_NAME") == "pull_request",
            "CurrentReaderEnvironmentRejected")
    event_path = Path(os.environ["GITHUB_EVENT_PATH"])
    require(event_path.stat().st_size <= 2 * 1024 * 1024, "CurrentEventSizeRejected")
    event = json.loads(event_path.read_text("utf-8"))
    reader_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(reader_sha == os.environ.get("GITHUB_SHA"), "CurrentReaderCheckoutMismatch")
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=repo, check=True)
    identity = validate_event(event, reader_sha)
    current = api("/repos/" + REPOSITORY + "/pulls/61", token)
    require(current.get("state") == "open" and current.get("merged") is False
            and current.get("head", {}).get("sha") == identity["head"]
            and current.get("head", {}).get("ref") == BRANCH
            and current.get("base", {}).get("ref") == "test"
            and current.get("base", {}).get("sha") == identity["base"]
            and current.get("merge_commit_sha") == identity["merge"],
            "CurrentPrMovedOrClosed")
    head = api("/repos/" + REPOSITORY + "/git/commits/" + identity["head"], token)
    merge = api("/repos/" + REPOSITORY + "/git/commits/" + identity["merge"], token)
    return validate_tree(identity, head, merge)


def acquire_runs(identity, token, out):
    listing = api("/repos/" + REPOSITORY + "/actions/runs?event=pull_request&head_sha="
                  + identity["head"] + "&per_page=100", token)
    listed = complete_listing(listing, "workflow_runs", "CurrentRunListingIncomplete")
    runs = {}
    for kind, (workflow_id, path) in WORKFLOWS.items():
        candidates = [run for run in listed if run.get("workflow_id") == workflow_id
                      or run.get("path") == path]
        require(len(candidates) == 1, "CurrentWorkflowMissingOrAmbiguous:" + kind)
        # Read the full record. Final revalidation detects any later rerun.
        run = api("/repos/" + REPOSITORY + "/actions/runs/" + str(candidates[0]["id"]), token)
        runs[kind] = validate_run(run, kind, identity)
        write_json(out / ("original-run-" + kind + ".json"), run)
        jobs_listing = api("/repos/" + REPOSITORY + "/actions/runs/" + str(run["id"])
                           + "/attempts/1/jobs?per_page=100", token)
        jobs = complete_listing(jobs_listing, "jobs", "CurrentJobListingIncomplete")
        require(jobs and all(job.get("run_id") == run["id"]
                            and job.get("head_sha") == identity["head"]
                            and type(job.get("run_attempt")) is int and job["run_attempt"] == 1
                            and job.get("status") == "completed" for job in jobs),
                "CurrentJobIdentityOrCompletionMismatch")
        write_json(out / ("original-jobs-" + kind + ".json"), jobs_listing)
    emit("WORKFLOWS", {"identity": identity, "workflows": {
        key: {"run": run["id"], "attempt": run["run_attempt"],
              "status": run["status"], "conclusion": run["conclusion"],
              "workflow_id": run["workflow_id"], "path": run["path"]}
        for key, run in runs.items()},
        "all_key_workflows_success": all(r["conclusion"] == "success" for r in runs.values()),
        "reader_changed_original_conclusions": False})
    return runs



def revalidate_runs(runs, identity, token, out):
    require(set(runs) == set(WORKFLOWS), "CurrentCompletionRunSetIncomplete")
    changed, observations = [], {}
    for kind, original in runs.items():
        latest = api("/repos/" + REPOSITORY + "/actions/runs/" + str(original["id"]), token)
        write_json(out / ("original-run-" + kind + "-at-completion.json"), latest)
        try:
            validate_run(latest, kind, identity)
            require(latest["id"] == original["id"]
                    and latest["conclusion"] == original["conclusion"],
                    "CurrentProducerChangedDuringRead")
        except EvidenceError:
            changed.append(kind)
        observations[kind] = {"run": latest.get("id"), "attempt": latest.get("run_attempt"),
                              "status": latest.get("status"), "conclusion": latest.get("conclusion")}
    emit("COMPLETION_WORKFLOWS", {"observations": observations, "changed": changed,
                                 "reader_changed_original_conclusions": False})
    require(not changed, "CurrentProducerChangedDuringRead")
    return True


def choose_members(kind, names):
    selected, missing = set(), []
    names = set(names)

    def exact(name, required=True):
        if name in names:
            selected.add(name)
        elif required:
            missing.append(name)

    def suffix(value, required=True):
        found = [n for n in names if n == value or n.endswith("/" + value)]
        if len(found) == 1:
            selected.add(found[0])
        elif len(found) > 1 or required:
            missing.append("missing-or-ambiguous:" + value)

    if kind == "installer":
        require(names == {"Swirl-Setup.exe"}, "InstallerArchiveContentMismatch")
    elif kind == "controlled":
        for mode in ("positive", "wrong-ca", "stall", "native-watchdog-500ms",
                     "missing-proof", "missing-fixture", "preexisting-store", "wrong-proof"):
            exact(mode + ".json")
    elif kind == "private":
        for name in ("receipt.json", "ordinary-runtime-before.json", "ordinary-runtime-after.json",
                     "qa-crt-import-closure.json", "billing-binary-identity.json",
                     "tests/private-ui-quota-results.json",
                     "billing-tests/private-ui-billing-results.json",
                     "import-tests/private-ui-import-results.json",
                     "dns-tests/private-ui-dns-results.json"):
            exact(name)
        for name in ("logs/tests.log", "logs/billing-tests.log", "logs/import-tests.log",
                     "logs/dns-tests.log", "logs/configure.log", "logs/build.log"):
            exact(name, required=False)
    elif kind == "node":
        for name in ("critical-ui.xml", "critical-network.xml", "node-chain.xml",
                     "node-chain.txt", "swirl-native-tun-recovery.xml"):
            suffix(name)
        suffix("node-diagnostic-regression.xml", required=False)
        for group in ("node-ui-evidence", "node-ui-native-evidence"):
            found = [n for n in names if re.search(
                r"(?:^|/)" + group + r"/node-probe-[A-Za-z0-9_.-]+\.json$", n)]
            if not 1 <= len(found) <= 40:
                missing.append("node-json-set:" + group)
            selected.update(found)
    elif kind == "package":
        # Multiple upload roots preserve these complete paths. Never choose an
        # arbitrary delivery.json suffix, which could select an older snapshot.
        for name in ("out/delivery.json", "installer-bin/package-manifest.json",
                     "out/qt-corresponding-source/qt-source-bundle.json",
                     "out/qt-corresponding-source/package-binding.json",
                     "build-evidence/critical-ui.xml", "build-evidence/critical-network.xml",
                     "build-evidence/ctest-inventory.json",
                     "build-evidence/full-regression.xml",
                     "build-evidence/deployed-all-pages.json",
                     "build-evidence/production-ui/startup.json"):
            exact(name)
        for group in ("full-motion-qa", "full-motion-release"):
            for leaf in ("receipt.json", "runtime-before.json", "runtime-after.json",
                         "rapid/result.json", "ready/result.json",
                         "rapid/Swirl-diagnostics.txt", "ready/Swirl-diagnostics.txt",
                         "rapid/stdout.log", "rapid/stderr.log",
                         "ready/stdout.log", "ready/stderr.log"):
                suffix(group + "/" + leaf)
        for name in ("build-evidence/installer-lifecycle/lifecycle.json",
                     "build-evidence/normal-installer-lifecycle/lifecycle.json",
                     "build-evidence/normal-installer-lifecycle/standard-user-runner.json",
                     "build-evidence/cross-version-installer-lifecycle/cross-version.json",
                     "build-evidence/d3d11-frame-latency/receipt.json",
                     "build-evidence/d3d11-frame-latency/runtime-manifest.json",
                     "build-evidence/d3d11-frame-latency/protected-changes.json",
                     "build-evidence/d3d11-frame-latency/maximum-1/result.json",
                     "build-evidence/d3d11-frame-latency/maximum-2/result.json",
                     "out/package-evidence/msvc-runtime-policy/msvc-runtime-policy.json"):
            exact(name)
        # Only result/identity receipts in fixed producer directories are text
        # exports. Grants, keys, environment dumps and arbitrary configs are not.
        receipt_names = {"receipt.json", "result.json", "lifecycle.json",
                         "standard-user-runner.json", "runtime-before.json",
                         "runtime-after.json", "runtime-manifest.json",
                         "protected-changes.json", "validation.json",
                         "configuration-identity.json", "package-binding.json"}
        for name in names:
            if (name.startswith(("build-evidence/installer-lifecycle/",
                                 "build-evidence/normal-installer-lifecycle/",
                                 "build-evidence/cross-version-installer-lifecycle/",
                                 "build-evidence/d3d11-frame-latency/",
                                 "build-evidence/qt-product-release-",
                                 "build-evidence/qt-product-qa-",
                                 "out/package-evidence/"))
                    and name.rsplit("/", 1)[-1] in receipt_names):
                selected.add(name)
    elif kind == "engine":
        for name in ("full-regression.xml", "critical-ui.xml", "critical-network.xml",
                     "swirl-native-tun-recovery.xml", "swirl-system-proxy-state.xml",
                     "swirl-system-proxy-recovery.xml", "swirl-system-proxy-app-exit.xml",
                     "swirl-system-proxy-normal-stop.xml"):
            suffix(name)
    elif kind == "qt_source":
        for name in ("qt-source-bundle.json", "package-binding.json"):
            exact(name)
        for name in names:
            if re.search(r"(?:^|/)(receipt|configuration-identity|corresponding-source|module-files|"
                         r"module-header-retention|header-alignment|stock-Qml|pe-interface-review)\.json$", name):
                selected.add(name)
            if name.endswith((".patch", ".diff")):
                selected.add(name)
    else:
        raise EvidenceError("CurrentArtifactKindRejected")
    require(len(selected) <= MAX_SELECTED_MEMBERS, "CurrentSelectedMemberCountLimit")
    return selected, sorted(missing)


def scan_archive(path, kind, out):
    originals, inventory, missing = {}, [], []
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(0 < len(entries) <= MAX_MEMBERS, "CurrentArchiveMemberCountLimit")
        seen, folded, expanded, index_bytes = set(), set(), 0, 0
        for info in entries:
            safe_member(info)
            require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                    "CurrentArchiveCompressionRejected")
            require(info.filename not in seen and info.filename.casefold() not in folded,
                    "CurrentArchiveDuplicateMember")
            seen.add(info.filename)
            folded.add(info.filename.casefold())
            expanded += info.file_size
            index_bytes += len(info.filename.encode("utf-8"))
            require(expanded <= MAX_EXPANDED and index_bytes <= 4 * 1024 * 1024,
                    "CurrentArchiveExpansionLimit")
        names = [info.filename for info in entries if not info.is_dir()]
        # Preserve the bounded observed index even if expected content is
        # missing, ambiguous, or too large to emit as selected text.
        index = [{"path": info.filename, "bytes": info.file_size, "crc32": info.CRC,
                  "directory": info.is_dir()} for info in entries]
        write_json(out / "member-index.json", index)
        emit("INDEX", {"kind": kind, "member_count": len(index), "expanded_bytes": expanded})
        for row in index:
            emit("INDEX_MEMBER", {"kind": kind, **row})
        selected, missing = choose_members(kind, names)
        require(sum(info.file_size for info in entries if info.filename in selected)
                <= MAX_SELECTED_TEXT, "CurrentSelectedTextBudgetExceeded")
        for info in entries:
            hasher, actual, blocks = hashlib.sha256(), 0, []
            with archive.open(info) as member:
                while True:
                    data = member.read(256 * 1024)
                    if not data:
                        break
                    actual += len(data)
                    require(actual <= info.file_size, "CurrentArchiveActualSizeLimit")
                    hasher.update(data)
                    if info.filename in selected:
                        require(actual <= MAX_TEXT_MEMBER, "CurrentTextMemberLimit")
                        blocks.append(data)
            require(actual == info.file_size, "CurrentArchiveActualSizeMismatch")
            # Reading the whole ZipExtFile checks CRC, even for unselected files.
            if not info.is_dir():
                row = {"path": info.filename, "bytes": actual, "sha256": hasher.hexdigest()}
                inventory.append(row)
                emit("VERIFIED_MEMBER", {"kind": kind, **row})
            if info.filename in selected:
                data = b"".join(blocks)
                if not info.filename.endswith(".json"):
                    data.decode("utf-8-sig", errors="strict")
                originals[info.filename] = data
        require(set(originals) == selected, "CurrentSelectedEvidenceIncomplete")
    write_json(out / "verified-member-inventory.json", inventory)
    emit_originals(kind, originals)
    # Preserve original text first, including malformed evidence. Reject
    # ambiguous JSON without normalizing or inventing replacement results.
    json_errors = []
    for name, data in sorted(originals.items()):
        if name.endswith(".json"):
            try:
                decode_json(data)
            except EvidenceError as error:
                json_errors.append({"path": name, "code": str(error)})
            except (ValueError, UnicodeError, TypeError):
                json_errors.append({"path": name, "code": "InvalidEvidenceJson"})
    return {"all_members_crc_verified": True, "crc_scope": "outer ZIP members only; nested archive bytes hashed, not recursively expanded",
            "expanded_bytes": expanded,
            "regular_files": len(inventory), "inventory": inventory,
            "selected_members": [{"path": n, "bytes": len(b), "sha256": digest(b)}
                                 for n, b in sorted(originals.items())],
            "selection_errors": missing, "json_errors": json_errors, "truncated": False}, originals


def emit_originals(kind, originals):
    for name, data in sorted(originals.items()):
        count = max(1, (len(data) + BLOCK_BYTES - 1) // BLOCK_BYTES)
        record = {"kind": kind, "path": name, "bytes": len(data),
                  "sha256": digest(data), "encoding": "base64", "blocks": count}
        emit("MEMBER", record)
        for index in range(count):
            block = data[index * BLOCK_BYTES:(index + 1) * BLOCK_BYTES]
            emit("CHUNK", {"kind": kind, "path": name, "index": index, "blocks": count,
                           "data": base64.b64encode(block).decode("ascii")})


def package_source(originals, identity, token):
    data = originals.get("out/delivery.json")
    if data is None:
        return {"verified": False, "reason": "FinalDeliveryUnavailable"}
    delivery = decode_json(data)
    source = delivery.get("source_sha")
    require(sha(source) and delivery.get("pr_head_sha") == identity["head"]
            and delivery.get("source_tree_sha") == identity["tree"]
            and delivery.get("version") == "0.2.40" and delivery.get("qt") == "6.12.0",
            "PackageSourceFieldsMismatch")
    # A new merge object may have the same parents/tree. Do not confuse the
    # reader merge SHA with the actual source SHA printed by the producer.
    commit = api("/repos/" + REPOSITORY + "/git/commits/" + source, token)
    require(commit.get("sha") == source and commit.get("tree", {}).get("sha") == identity["tree"]
            and [p.get("sha") for p in commit.get("parents", [])]
            == [identity["base"], identity["head"]], "PackageProducerMergeMismatch")
    require(sha(delivery.get("installer_sha256"), 64), "PackageInstallerDigestMissing")
    manifest_data = originals.get("installer-bin/package-manifest.json")
    require(manifest_data is not None, "PackageManifestUnavailable")
    manifest = decode_json(manifest_data)
    require(manifest.get("source_sha") == source, "PackageManifestSourceMismatch")
    qt_data = originals.get("out/qt-corresponding-source/qt-source-bundle.json")
    require(qt_data is not None
            and digest(qt_data) == delivery.get("qt_source_manifest_sha256"),
            "PackageQtSourceDigestMismatch")
    qt_source = decode_json(qt_data)
    require(qt_source.get("source_sha") == source and qt_source.get("status") == "complete",
            "PackageQtSourceIdentityMismatch")
    return {"verified": True, "producer_source_sha": source,
            "reader_source_sha": identity["merge"], "pr_head_sha": identity["head"],
            "source_tree": identity["tree"], "installer_sha256": delivery["installer_sha256"],
            "delivery_sha256": digest(data), "package_manifest_sha256": digest(manifest_data),
            "scope": "Source and receipt integrity only; correlate separately with downloaded EXE digest."}


def main(argv=None):
    global _NAMESPACE
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--kind", choices=sorted(ARTIFACTS), required=True)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    token = os.environ.get("GH_TOKEN")
    require(isinstance(token, str) and token, "CurrentReadOnlyTokenRequired")
    identity = acquire_source(repo, token)
    _NAMESPACE = "pr61/" + identity["head"] + "/" + args.kind
    out = repo / "build-evidence" / "pr61-current-artifacts" / args.kind
    require(not out.exists() and not any(p.is_symlink() for p in (out, *out.parents)),
            "CurrentFreshEvidenceDirectoryRequired")
    out.mkdir(parents=True)
    report = {"schema": 1, "kind": args.kind, "identity": identity,
              "reader_source_sha": identity["merge"], "success": False,
              "all_key_workflows_success": False, "reader_changed_original_conclusions": False,
              "producer_runs_stable_at_completion": False,
              "current_pr_unchanged_at_completion": False, "current_ci_eligible": False,
              "runtime_executed": False, "real_provider_requests": 0, "real_node_requests": 0,
              "live_acceptance": False, "delivery_qualified": False,
              "scope": "Read-only original archive acquisition; never runtime or live acceptance.",
              "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "error_code": None}
    try:
        write_json(out / "source-identity.json", identity)
        runs = acquire_runs(identity, token, out)
        report["original_workflows"] = {k: {"run": r["id"], "conclusion": r["conclusion"]}
                                        for k, r in runs.items()}
        report["all_key_workflows_success"] = all(r["conclusion"] == "success" for r in runs.values())
        run = runs["ui"]
        listing = api("/repos/" + REPOSITORY + "/actions/runs/" + str(run["id"])
                      + "/artifacts?per_page=100", token)
        artifacts = complete_listing(listing, "artifacts", "CurrentArtifactListingIncomplete")
        found = [a for a in artifacts if a.get("name") == ARTIFACTS[args.kind]]
        require(len(found) == 1, "CurrentArtifactMissingOrAmbiguous")
        artifact = found[0]
        _NAMESPACE = "pr61/" + identity["head"] + "/" + str(run["id"]) + "/" + str(artifact["id"]) + "/" + args.kind
        target = validate_artifact(artifact, args.kind, run, identity, dt.datetime.now(dt.timezone.utc))
        write_json(out / "original-artifact-list.json", listing)
        write_json(out / "original-artifact.json", artifact)
        original = out / "original.zip"
        report["artifact"] = {"id": artifact["id"], "name": artifact["name"], "run": run["id"]}
        report["downloaded_zip"] = download(target, original, token)
        emit("IDENTITY", {"identity": identity, "kind": args.kind,
                          "original_conclusion": run["conclusion"],
                          "artifact": report["artifact"], **report["downloaded_zip"]})
        report["archive"], originals = scan_archive(original, args.kind, out)
        if args.kind == "installer":
            exe = report["archive"]["inventory"][0]
            require(exe["path"] == "Swirl-Setup.exe" and 10_000_000 <= exe["bytes"] < 100_000_000,
                    "CurrentInstallerSizeMismatch")
            report["downloaded_exe"] = exe
            report["installer_binding"] = "Must match the same producer's final package delivery receipt."
            emit("EXE", {**exe, "producer_run": run["id"], "pr_head_sha": identity["head"],
                         "downloaded_body_hashed": True, "executed": False})
        if args.kind == "package":
            report["package_source"] = package_source(originals, identity, token)
            emit("SOURCE", report["package_source"])
        report["producer_runs_stable_at_completion"] = revalidate_runs(runs, identity, token, out)
        current = api("/repos/" + REPOSITORY + "/pulls/61", token)
        unchanged = (current.get("state") == "open" and current.get("merged") is False
                     and current.get("head", {}).get("sha") == identity["head"]
                     and current.get("head", {}).get("ref") == BRANCH
                     and current.get("base", {}).get("sha") == identity["base"]
                     and current.get("base", {}).get("ref") == "test")
        report["current_pr_unchanged_at_completion"] = unchanged
        report["current_ci_eligible"] = (unchanged and report["producer_runs_stable_at_completion"]
                                         and report["all_key_workflows_success"])
        report["success"] = not (report["archive"]["selection_errors"] or report["archive"]["json_errors"])
        if not report["success"]:
            report["error_code"] = "CurrentSelectedEvidenceIncomplete"
    except EvidenceError as error:
        report["error_code"] = str(error)
    except Exception as error:
        # URLs, response bodies and signed redirects never enter the log.
        report["error_code"] = "CurrentEvidenceFailure:" + type(error).__name__
    finally:
        report["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(out / "reader-result.json", report)
        # The full inventory already has per-member bounded records.
        emitted = {**report}
        if "archive" in emitted:
            emitted["archive"] = {k: v for k, v in emitted["archive"].items() if k != "inventory"}
        emit("RESULT", emitted)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as error:
        emit("ADMISSION", {"success": False, "error_code": str(error), "runtime_executed": False})
        raise SystemExit(1)
    except Exception as error:
        emit("ADMISSION", {"success": False, "error_code": "CurrentAdmissionFailure:" + type(error).__name__,
                           "runtime_executed": False})
        raise SystemExit(1)
