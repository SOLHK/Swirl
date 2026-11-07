#!/usr/bin/env python3
"""Read fixed, public PR61 CI evidence; never execute archive contents.

Reader source and target source are separate identities. Success means only
verified acquisition of the original evidence. Original test failures remain.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = "SOLHK/Swirl"
REPOSITORY_ID = 1411888911
BRANCH = "work/node-probe-render-20261105"
LABEL = "qa-pr61-artifact-read"
TARGET_HEAD = "d136505cb1ac8cfeb5b80c554daebbbb06ff1aa9"
TARGET_MERGE = "e76d264b9b5dfe1f1becdbef7dc8fceb3506a0ab"
TARGET_BASE = "acd7005c99a99c4f81b62d328fcc15883d51b62a"
TARGET_TREE = "7c90f7e754f373e4dcac0bbfd656ccaa5ec061bc"
TARGETS = {
    "package": {
        "run": 42338343469, "artifact": 13561392211,
        "workflow": ".github/workflows/build-qt-quick-ui.yml",
        "name": "Swirl-Qt612-Package-Evidence", "conclusion": "failure",
        "bytes": 1881078,
        "sha256": "c913aeb14bea2269d0cb9e212363ab593cca471ffb2dd156e0d2b7c2abd517d9",
    },
    "node": {
        "run": 42338343469, "artifact": 13560877627,
        "workflow": ".github/workflows/build-qt-quick-ui.yml",
        "name": "Swirl-Node-Regression-Evidence", "conclusion": "failure",
        "bytes": 615139,
        "sha256": "3902aaece8c924904424867e72673e045a72da19801d37234cfdf8175f30edd3",
    },
    "sdk": {
        "run": 42338365419, "artifact": 13561016761,
        "workflow": ".github/workflows/diagnose-qt612-runtime-patch.yml",
        "name": "Swirl-Qt612-Isolated-Runtime-Patch-Diagnosis", "conclusion": "failure",
        "bytes": 60774580,
        "sha256": "4e21e07c3c94738f74a1dda2448d3594121013f4ae68a2198c00dcd32036aea8",
    },
}
MAX_MEMBERS = 5000
MAX_MEMBER = 128 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_TEXT_MEMBER = 2 * 1024 * 1024
MAX_SELECTED_TEXT = 8 * 1024 * 1024
BLOCK_BYTES = 3072


class EvidenceError(Exception):
    pass


def require(value, code):
    if not value:
        raise EvidenceError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def emit(kind, value):
    # No raw archive text can become an Actions workflow command.
    print("SWIRL_ORIGINAL_" + kind + " " + json.dumps(value, ensure_ascii=True, separators=(",", ":")),
          flush=True)


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=True, indent=2)
        output.write("\n")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def client():
    # Two independent clients are used; neither automatically follows redirects.
    return urllib.request.build_opener(NoRedirect())


def api(path, token):
    require(path.startswith("/repos/" + REPOSITORY + "/"), "ApiPathRejected")
    request = urllib.request.Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Swirl-PR61-Evidence-Reader",
    })
    with client().open(request, timeout=30) as response:
        require(response.status == 200, "ApiStatusRejected")
        data = response.read(2 * 1024 * 1024 + 1)
    require(len(data) <= 2 * 1024 * 1024, "ApiBodyLimit")
    return json.loads(data)


def allowed_download(url):
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    require(parsed.scheme == "https" and not parsed.username and not parsed.password
            and parsed.port in (None, 443) and not parsed.fragment
            and (host.endswith(".blob.core.windows.net")
                 or host.endswith(".actions.githubusercontent.com")
                 or host == "objects.githubusercontent.com"),
            "DownloadOriginRejected")


def download(target, destination, token):
    url = "https://api.github.com/repos/" + REPOSITORY + "/actions/artifacts/" + str(target["artifact"]) + "/zip"
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Swirl-PR61-Evidence-Reader",
    })
    try:
        response = client().open(request, timeout=30)
    except urllib.error.HTTPError as error:
        try:
            require(error.code == 302, "ArtifactRedirectRequired")
            location = error.headers.get("Location", "")
        finally:
            error.close()
    else:
        response.close()
        raise EvidenceError("ArtifactRedirectRequired")
    allowed_download(location)
    # This client and Request have no Authorization header. Do not print Location.
    request = urllib.request.Request(location, headers={"Accept-Encoding": "identity"})
    total, hasher = 0, hashlib.sha256()
    with client().open(request, timeout=45) as response, destination.open("xb") as output:
        require(response.status == 200, "ArtifactDownloadStatusRejected")
        while True:
            data = response.read(256 * 1024)
            if not data:
                break
            total += len(data)
            require(total <= target["bytes"], "ArtifactDownloadLimit")
            output.write(data)
            hasher.update(data)
    require(total == target["bytes"] and hasher.hexdigest() == target["sha256"],
            "DownloadedArtifactIdentityMismatch")
    return {"bytes": total, "sha256": hasher.hexdigest()}


def safe_member(info):
    name = info.filename
    require(info.orig_filename == name, "ArchiveOriginalPathChanged")
    path = PurePosixPath(name)
    require(name and len(name) <= 1024 and "\\" not in name and ":" not in name and "\x00" not in name
            and not any(ord(c) < 32 for c in name)
            and not path.is_absolute() and ".." not in path.parts
            and not name.startswith("/") and "//" not in name
            and path.as_posix().rstrip("/") == name.rstrip("/"), "ArchivePathRejected")
    mode = (info.external_attr >> 16) & 0xFFFF
    require(not stat.S_ISLNK(mode) and stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR)
            and not info.flag_bits & 1, "ArchiveEntryKindRejected")
    require(0 <= info.file_size <= MAX_MEMBER, "ArchiveMemberLimit")


def select_members(kind, names, conditional_absence):
    selected, errors = set(), []

    def unique(suffix, required=True):
        matches = [name for name in names if name == suffix or name.endswith("/" + suffix)]
        if len(matches) > 1 or (required and len(matches) != 1):
            errors.append("RequiredMemberMissingOrAmbiguous:" + suffix)
        else:
            selected.update(matches)

    if kind == "package":
        for suffix in ("receipt.json", "runtime-before.json", "runtime-after.json"):
            unique("full-motion-qa/" + suffix)
        for mode in ("rapid", "ready"):
            for name in ("result.json", "Swirl-diagnostics.txt", "stdout.log", "stderr.log",
                         "settings-before.ini", "settings-after.ini"):
                unique("full-motion-qa/" + mode + "/" + name)
        for suffix in ("deployed-all-pages.json", "deployed-all-pages.log", "critical-ui.xml",
                       "ctest-inventory.json", "d3d11-frame-latency/runtime-manifest.json",
                       "d3d11-frame-latency/receipt.json", "d3d11-frame-latency/protected-changes.json",
                       "d3d11-frame-latency/maximum-1/result.json",
                       "d3d11-frame-latency/maximum-2/result.json", "dist/msvc-runtime.json",
                       "runtime-refusal-qa/runtime-refusal.json",
                       "profile-residual-cleanup-controls/receipt.json"):
            unique(suffix)
    elif kind == "node":
        for suffix in ("critical-ui.xml", "critical-network.xml",
                       "node-chain.xml", "node-chain.txt", "swirl-native-tun-recovery.xml"):
            unique(suffix)
        diagnostic = "node-diagnostic-regression.xml"
        unique(diagnostic, required=diagnostic not in conditional_absence)
        if diagnostic in conditional_absence and any(
                name == diagnostic or name.endswith("/" + diagnostic) for name in names):
            errors.append("ArtifactPresentForSkippedProducer:" + diagnostic)
        for group in ("node-ui-evidence", "node-ui-native-evidence"):
            matches = [name for name in names
                       if re.search(r"(?:^|/)" + group + r"/node-probe-[A-Za-z0-9_.-]+\.json$", name)]
            if not 1 <= len(matches) <= 40:
                errors.append("NodeEvidenceSetMissingOrOversized:" + group)
            else:
                selected.update(matches)
    else:
        for suffix in ("step-outcomes.json", "boundary-tests.log", "sdk-driver.log",
                       "comparison-driver.log", "sdk/receipt.json", "sdk/header-alignment.json",
                       "sdk/module-header-retention.json", "sdk/module-files.json",
                       "sdk/pe-interface-review.json", "sdk/configuration-identity.json",
                       "sdk/stock-Qml.json", "sdk/corresponding-source.json",
                       "comparison/comparison.json", "comparison/runtime-delta.json",
                       "sdk/commands/10-configure.json", "sdk/commands/11-qml-build.json",
                       "sdk/commands/12-install-qml-only.json",
                       "comparison/commands/01-configure-fixtures.json",
                       "comparison/commands/02-build-fixtures.json",
                       "comparison/commands/04-stock-fixtures.json",
                       "comparison/commands/04-patched-fixtures.json",
                       "native-boundaries/generic-child/native-unknown-child.json",
                       "native-boundaries/held-image-file/held-file-result.json"):
            unique(suffix)
        # These four generated headers have actual stock/candidate/predicted
        # and installed originals in this fixed SDK ZIP. Other source headers
        # are compared by the complete verified member hash inventory.
        for header in ("include/QtQml/6.12.0/QtQml/private/qqmljsgrammar_p.h",
                       "include/QtQml/6.12.0/QtQml/private/qqmljsparser_p.h",
                       "include/QtQml/6.12.0/QtQml/private/qtqml-config_p.h",
                       "include/QtQml/qtqml-config.h"):
            for prefix in ("sdk/header-inputs/stock/", "sdk/header-inputs/candidate/",
                           "sdk/header-inputs/expected-candidate/", "sdk/module-install-output/"):
                unique(prefix + header)
        for flavor in ("stock", "patched"):
            unique("comparison/" + flavor + "/aggregate.json")
            for case in ("popup-normal", "popup-incremental", "sweep-slots"):
                for name in ("receipt.json", "stdout.log", "stderr.log"):
                    unique("comparison/" + flavor + "/" + case + "/" + name)
    require(0 < len(selected) <= 150, "SelectionLimit")
    return selected, errors


def inspect_archive(path, kind, out, conditional_absence):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(0 < len(entries) <= MAX_MEMBERS, "ArchiveMemberCountLimit")
        seen, folded, expanded = set(), set(), 0
        for info in entries:
            safe_member(info)
            require(info.filename not in seen and info.filename.casefold() not in folded,
                    "DuplicateOrAmbiguousArchiveMember")
            seen.add(info.filename)
            folded.add(info.filename.casefold())
            expanded += info.file_size
            require(expanded <= MAX_EXPANDED, "ArchiveExpansionLimit")
        require(sum(len(info.filename.encode("utf-8")) for info in entries) <= 1024 * 1024,
                "ArchiveIndexTextLimit")
        file_names = [info.filename for info in entries if not info.is_dir()]
        # Preserve the bounded index even if a fixed required file is missing.
        index = [{"path": info.filename, "bytes": info.file_size, "crc32": info.CRC}
                 for info in entries]
        write_json(out / "member-index.json", index)
        emit("INDEX", {"kind": kind, "member_count": len(index),
                       "expanded_bytes": expanded})
        for item in index:
            emit("INDEX_MEMBER", {"kind": kind, **item})
        selected, selection_errors = select_members(kind, file_names, conditional_absence)
        selected_bytes = sum(info.file_size for info in entries if info.filename in selected)
        require(selected_bytes <= MAX_SELECTED_TEXT, "SelectedTextBudgetExceeded")
        originals, inventory = {}, []
        for info in entries:
            hasher, actual, blocks = hashlib.sha256(), 0, []
            with archive.open(info) as member:
                while True:
                    data = member.read(256 * 1024)
                    if not data:
                        break
                    actual += len(data)
                    require(actual <= info.file_size and actual <= MAX_MEMBER, "ArchiveActualSizeLimit")
                    hasher.update(data)
                    if info.filename in selected:
                        require(actual <= MAX_TEXT_MEMBER, "SelectedMemberTextLimit")
                        blocks.append(data)
            require(actual == info.file_size, "ArchiveActualSizeMismatch")
            # ZipExtFile has now checked the complete member CRC, without extraction.
            if not info.is_dir():
                inventory.append({"path": info.filename, "bytes": actual, "sha256": hasher.hexdigest()})
            if info.filename in selected:
                data = b"".join(blocks)
                data.decode("utf-8-sig", errors="strict")
                originals[info.filename] = data
        require(set(originals) == selected, "SelectionIncomplete")
        if kind == "package":
            match = [name for name in originals if name.endswith("full-motion-qa/receipt.json")]
            if len(match) == 1:
                smoke = json.loads(originals[match[0]].decode("utf-8-sig"))
                require(smoke.get("source_sha") == TARGET_MERGE and smoke.get("pr_head_sha") == TARGET_HEAD,
                        "SmokeSourceIdentityMismatch")
            else:
                selection_errors.append("SmokeReceiptUnavailable")
        if kind == "sdk":
            match = [name for name in originals if name == "sdk/receipt.json"
                     or name.endswith("/sdk/receipt.json")]
            if len(match) == 1:
                sdk = json.loads(originals[match[0]].decode("utf-8-sig"))
                require(sdk.get("source_sha") == TARGET_MERGE and sdk.get("pr_head_sha") == TARGET_HEAD,
                        "SdkSourceIdentityMismatch")
            else:
                selection_errors.append("SdkReceiptUnavailable")
        write_json(out / "verified-member-inventory.json", inventory)
        for item in inventory:
            emit("VERIFIED_MEMBER", {"kind": kind, **item})
        records = []
        for name in sorted(originals):
            data = originals[name]
            count = max(1, (len(data) + BLOCK_BYTES - 1) // BLOCK_BYTES)
            record = {"path": name, "bytes": len(data), "sha256": digest(data),
                      "encoding": "base64", "blocks": count}
            records.append(record)
            emit("MEMBER", record)
            for index in range(count):
                block = data[index * BLOCK_BYTES:(index + 1) * BLOCK_BYTES]
                emit("CHUNK", {"path": name, "index": index, "blocks": count,
                               "data": base64.b64encode(block).decode("ascii")})
        write_json(out / "selected-member-identities.json", records)
        return {"all_members_crc_verified": True, "regular_files": len(inventory),
                "expanded_bytes": expanded, "selected_bytes": selected_bytes,
                "selected_members": records, "selection_errors": selection_errors,
                "expected_absent_evidence": conditional_absence, "truncated": False}


def original_conditional_evidence(kind, token):
    if kind != "node":
        return {}
    # d136's diagnostic rerun is conditional on an early critical-UI failure.
    # Its normal critical UI/network reports are still mandatory. Verify the
    # original producer outcome before treating the diagnostic XML as absent.
    listing = api("/repos/" + REPOSITORY + "/actions/runs/42338343469/jobs?per_page=100", token)
    require(type(listing.get("total_count")) is int and listing["total_count"] <= 100,
            "OriginalJobListingIncomplete")
    jobs = [job for job in listing.get("jobs", []) if job.get("id") == 128300247013]
    require(len(jobs) == 1, "OriginalProducerJobMissingOrAmbiguous")
    job = jobs[0]
    require(job.get("run_id") == 42338343469 and job.get("head_sha") == TARGET_HEAD
            and job.get("head_branch") == BRANCH and job.get("status") == "completed"
            and job.get("conclusion") == "failure", "OriginalProducerJobIdentityMismatch")
    expected = {
        42: ("Critical UI startup, rendering and interaction checks", "success"),
        43: ("Preserve node probe regression after an early UI failure", "skipped"),
        44: ("Upload current node regression evidence before production builds", "success"),
    }
    verified = []
    for number, (name, conclusion) in expected.items():
        matches = [step for step in job.get("steps", []) if step.get("number") == number]
        require(len(matches) == 1 and matches[0].get("name") == name
                and matches[0].get("status") == "completed"
                and matches[0].get("conclusion") == conclusion,
                "OriginalConditionalProducerOutcomeMismatch")
        verified.append(matches[0])
    return {"node-diagnostic-regression.xml": {
        "job_id": job["id"], "run_id": job["run_id"], "source_head_sha": job["head_sha"],
        "reason": "Original conditional diagnostic producer was skipped; normal critical reports remain required.",
        "producer_steps": verified, "classification": "not_generated_by_original_workflow",
        "original_run_conclusion_changed": False,
    }}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--kind", choices=sorted(TARGETS), required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_EVENT_NAME") == "pull_request", "ReaderEnvironmentRejected")
    event_path = Path(os.environ["GITHUB_EVENT_PATH"])
    require(event_path.stat().st_size <= 2 * 1024 * 1024, "EventSizeRejected")
    event = json.loads(event_path.read_text("utf-8"))
    pr = event.get("pull_request", {})
    require(event.get("action") == "labeled" and event.get("label", {}).get("name") == LABEL
            and event.get("number") == 61 and event.get("repository", {}).get("id") == REPOSITORY_ID
            and pr.get("head", {}).get("ref") == BRANCH
            and pr.get("head", {}).get("repo", {}).get("id") == REPOSITORY_ID
            and pr.get("base", {}).get("ref") == "test", "ReaderEventRejected")
    reader_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    require(re.fullmatch(r"[0-9a-f]{40}", reader_sha)
            and reader_sha == os.environ.get("GITHUB_SHA"), "ReaderSourceMismatch")
    subprocess.run(["git", "diff", "--quiet"], cwd=repo, check=True)
    token = os.environ.get("GH_TOKEN")
    require(isinstance(token, str) and len(token) > 0, "ReadOnlyActionsTokenRequired")
    target = TARGETS[args.kind]
    out = repo / "build-evidence" / "pr61-original-artifacts" / args.kind
    require(not out.exists() and not any(path.is_symlink() for path in (out, *out.parents)),
            "FreshEvidenceDirectoryRequired")
    out.mkdir(parents=True)
    report = {"schema": 1, "kind": args.kind, "reader_source_sha": reader_sha,
              "reader_pr_head_sha": pr["head"]["sha"], "target_head_sha": TARGET_HEAD,
              "target_merge_sha": TARGET_MERGE, "target_tree_sha": TARGET_TREE,
              "target": target, "original_conclusion": None, "success": False,
              "runtime_executed": False, "real_provider_requests": 0,
              "scope": "Read-only integrity and original evidence acquisition; not a test rerun or acceptance result.",
              "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "error_code": None}
    try:
        merge = api("/repos/" + REPOSITORY + "/git/commits/" + TARGET_MERGE, token)
        require(merge.get("sha") == TARGET_MERGE and merge.get("tree", {}).get("sha") == TARGET_TREE
                and [value.get("sha") for value in merge.get("parents", [])] == [TARGET_BASE, TARGET_HEAD],
                "TargetMergeIdentityMismatch")
        run = api("/repos/" + REPOSITORY + "/actions/runs/" + str(target["run"]), token)
        require(run.get("id") == target["run"] and run.get("repository", {}).get("id") == REPOSITORY_ID
                and run.get("head_repository", {}).get("id") == REPOSITORY_ID
                and run.get("head_sha") == TARGET_HEAD and run.get("head_branch") == BRANCH
                and run.get("event") == "pull_request" and run.get("path") == target["workflow"]
                and run.get("run_attempt") == 1 and run.get("status") == "completed"
                and run.get("conclusion") == target["conclusion"],
                "OriginalRunIdentityOrConclusionMismatch")
        report["original_conclusion"] = run["conclusion"]
        listing = api("/repos/" + REPOSITORY + "/actions/runs/" + str(target["run"])
                      + "/artifacts?per_page=100", token)
        require(type(listing.get("total_count")) is int and listing["total_count"] <= 100,
                "ArtifactListingIncomplete")
        artifacts = [value for value in listing.get("artifacts", []) if value.get("id") == target["artifact"]]
        require(len(artifacts) == 1, "FixedArtifactMissingOrAmbiguous")
        artifact = artifacts[0]
        owner = artifact.get("workflow_run", {})
        require(artifact.get("name") == target["name"] and artifact.get("expired") is False
                and artifact.get("size_in_bytes") == target["bytes"]
                and artifact.get("digest") == "sha256:" + target["sha256"]
                and owner.get("id") == target["run"] and owner.get("repository_id") == REPOSITORY_ID
                and owner.get("head_repository_id") == REPOSITORY_ID
                and owner.get("head_sha") == TARGET_HEAD and owner.get("head_branch") == BRANCH,
                "FixedArtifactIdentityMismatch")
        expires = dt.datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
        require(expires > dt.datetime.now(dt.timezone.utc), "FixedArtifactExpired")
        write_json(out / "original-run.json", run)
        write_json(out / "original-artifact.json", artifact)
        conditional_absence = original_conditional_evidence(args.kind, token)
        write_json(out / "original-conditional-producers.json", conditional_absence)
        original = out / "original.zip"
        report["downloaded_zip"] = download(target, original, token)
        emit("IDENTITY", {"reader_source_sha": reader_sha, "target_head_sha": TARGET_HEAD,
                          "target_merge_sha": TARGET_MERGE, "target_run": target["run"],
                          "original_conclusion": run["conclusion"], "artifact": target["artifact"],
                          **report["downloaded_zip"]})
        report["archive"] = inspect_archive(original, args.kind, out, conditional_absence)
        report["success"] = not report["archive"]["selection_errors"]
        if not report["success"]:
            report["error_code"] = "SelectedEvidenceIncomplete"
    except EvidenceError as error:
        report["error_code"] = str(error)
    except Exception as error:
        # Do not print exception URLs, response bodies, credentials or signed Locations.
        report["error_code"] = "EvidenceReadFailure:" + type(error).__name__
    finally:
        report["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(out / "reader-result.json", report)
        emit("RESULT", report)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as error:
        emit("ADMISSION", {"success": False, "error_code": str(error), "runtime_executed": False})
        raise SystemExit(1)
