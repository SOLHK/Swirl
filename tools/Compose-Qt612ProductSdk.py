#!/usr/bin/env python3
"""Compose one reviewed Qt 6.12 product SDK candidate; never build or replace stock.

The original diagnostic workflow remains a failed workflow.  Its exact completed
module build and explicit stock-negative/patched-positive results are admitted by
this separate product policy.  No diagnostic environment or permission is forged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / "qt612-product-sdk.lock.json"
OWN_PATHS = ("tools/Compose-Qt612ProductSdk.py", "tools/qt612-product-sdk.lock.json",
             "tools/tests/test_qt612_product_sdk.py")
SHA = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
MAX_JSON = 32 * 1024 * 1024
MAX_ARCHIVE_SECONDS = 180


class Rejected(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Rejected(code)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def byte_id(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DuplicateJsonKey")
        result[key] = value
    return result


def read_json(path):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= MAX_JSON, "JsonMissingOrOversized")
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=no_duplicates)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.write("\n")


def file_id(path):
    path = Path(path)
    with path.open("rb") as stream:
        return {"bytes": path.stat().st_size,
                "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}


def load_lock():
    lock = read_json(LOCK_PATH)
    require(lock.get("schema") == 1 and lock.get("kind") == "swirl-qt612-product-sdk-fixed-artifact-candidate",
            "ProductLockSchemaRejected")
    require(lock["producer"]["run"] == 42338365419 and lock["artifact"]["artifact"] == 13561016761
            and lock["artifact"]["sha256"] == "4e21e07c3c94738f74a1dda2448d3594121013f4ae68a2198c00dcd32036aea8",
            "FixedArtifactPolicyChanged")
    require(lock["recipe"]["patch"]["upstream_commit"] == "8c92fe01338c76885f412a68fd39238147e21a81"
            and lock["content"]["derived"] == "6a2b82cc4a2133e128f83511a91764a121178c90cd3717399af612136ab2fc1c",
            "FixedDerivationPolicyChanged")
    return lock


def load_support(repository, lock):
    # Validate existing, committed helpers before importing them. Their command
    # entry points/admission functions are never called by this product policy.
    repository = Path(repository).resolve(strict=True)
    for name, expected in lock["reuse_inputs"].items():
        require(file_id(repository / name) == expected, "SharedVerifierSourceChanged:" + name)
    modules = []
    for name, filename in (("product_sdk_shared", "Build-Qt612QmlDiagnosticSdk.py"),
                           ("product_sdk_transport", "ReadPr61ArtifactEvidence.py")):
        spec = importlib.util.spec_from_file_location(name, repository / "tools" / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return tuple(modules)


def validate_producer(run, jobs, artifact, lock, *, require_unexpired):
    p, a, repo = lock["producer"], lock["artifact"], lock["repository"]
    require(run.get("id") == p["run"] and run.get("run_attempt") == p["attempt"]
            and run.get("repository", {}).get("id") == repo["id"]
            and run.get("head_repository", {}).get("id") == repo["id"]
            and run.get("head_sha") == p["head"] and run.get("head_branch") == repo["branch"]
            and run.get("path") == p["workflow"] and run.get("event") == "pull_request"
            and run.get("status") == "completed" and run.get("conclusion") == "failure",
            "ProducerFinalRunRejected")
    require(jobs.get("total_count") == 1 and len(jobs.get("jobs", [])) == 1, "ProducerJobsIncomplete")
    job = jobs["jobs"][0]
    require(job.get("id") == p["job"] and job.get("run_id") == p["run"]
            and job.get("name") == p["job_name"] and job.get("status") == "completed"
            and job.get("conclusion") == "failure", "ProducerJobRejected")
    actual_steps = [{k: s.get(k) for k in ("number", "name", "conclusion")} for s in job.get("steps", [])]
    require(actual_steps == p["steps"], "ProducerExpectedNegativeStepsChanged")
    owner = artifact.get("workflow_run", {})
    require(artifact.get("id") == a["artifact"] and artifact.get("name") == a["name"]
            and artifact.get("size_in_bytes") == a["bytes"]
            and artifact.get("digest") == "sha256:" + a["sha256"]
            and owner.get("id") == p["run"] and owner.get("repository_id") == repo["id"]
            and owner.get("head_repository_id") == repo["id"]
            and owner.get("head_sha") == p["head"] and owner.get("head_branch") == repo["branch"],
            "ProducerArtifactMetadataRejected")
    if require_unexpired:
        require(artifact.get("expired") is False and datetime.fromisoformat(
            artifact["expires_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc),
            "ProducerArtifactExpired")
    return {"run_id": p["run"], "job_id": p["job"], "run_attempt": p["attempt"],
            "original_conclusion": "failure", "expected_negative_preserved": True,
            "metadata_checked_utc": datetime.now(timezone.utc).isoformat()}


def fetch_producer(lock, transport, evidence):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    require(bool(token), "GitHubActionsReadTokenMissing")
    prefix = "/repos/" + lock["repository"]["name"]
    run = transport.api(prefix + "/actions/runs/" + str(lock["producer"]["run"]), token)
    jobs = transport.api(prefix + "/actions/runs/" + str(lock["producer"]["run"])
                         + "/jobs?filter=all&per_page=100", token)
    listing = transport.api(prefix + "/actions/runs/" + str(lock["producer"]["run"])
                            + "/artifacts?per_page=100", token)
    require(type(listing.get("total_count")) is int and listing["total_count"] <= 100,
            "ProducerArtifactListingIncomplete")
    matches = [a for a in listing.get("artifacts", []) if a.get("id") == lock["artifact"]["artifact"]]
    require(len(matches) == 1, "ProducerArtifactMissingOrAmbiguous")
    artifact = matches[0]
    # The metadata endpoint URLs are public; temporary signed archive URLs and
    # authorization headers never enter a receipt, exception text, or stdout.
    for name, data in (("run", run), ("jobs", jobs), ("artifact", artifact)):
        write_json(evidence / ("original-" + name + ".json"), data)
    return validate_producer(run, jobs, artifact, lock, require_unexpired=True), token


def download_fixed_artifact(lock, destination, token, transport):
    # Only this fixed API URL receives authorization. A bounded read1 loop checks
    # the total wall-clock budget between individual socket reads, not just
    # between complete 256 KiB buffers. No temporary Location value is persisted.
    target = lock["artifact"]
    url = "https://api.github.com/repos/" + lock["repository"]["name"]
    url += "/actions/artifacts/" + str(target["artifact"]) + "/zip"
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Swirl-Qt612-Product-SDK"})
    deadline = time.monotonic() + 180
    try:
        response = transport.client().open(request, timeout=30)
    except urllib.error.HTTPError as error:
        try:
            require(error.code == 302, "FixedArtifactRedirectRequired")
            location = error.headers.get("Location", "")
        finally:
            error.close()
    else:
        response.close()
        raise Rejected("FixedArtifactRedirectRequired")
    transport.allowed_download(location)
    request = urllib.request.Request(location, headers={"Accept-Encoding": "identity"})
    total, hasher = 0, hashlib.sha256()
    with transport.client().open(request, timeout=30) as response, destination.open("xb") as output:
        require(response.status == 200, "FixedArtifactDownloadStatusRejected")
        while True:
            require(time.monotonic() < deadline, "FixedArtifactDownloadDeadline")
            block = response.read1(256 * 1024)
            require(time.monotonic() < deadline, "FixedArtifactDownloadDeadline")
            if not block:
                break
            total += len(block)
            require(total <= target["bytes"], "FixedArtifactDownloadSizeLimit")
            hasher.update(block)
            output.write(block)
    require({"bytes": total, "sha256": hasher.hexdigest()} == {k: target[k] for k in ("bytes", "sha256")},
            "FixedArtifactDownloadIdentityRejected")


def audit_archive(path, destination, lock, sdk, transport):
    require(sdk.file_identity(path) == {k: lock["artifact"][k] for k in ("bytes", "sha256")},
            "OriginalArchiveIdentityRejected")
    sdk.fresh_directory(destination)
    inventory, names, expanded = {}, set(), 0
    deadline = time.monotonic() + MAX_ARCHIVE_SECONDS
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(len(entries) == lock["artifact"]["member_count"], "OriginalArchiveMemberCountChanged")
        for entry in entries:
            require(time.monotonic() < deadline, "OriginalArchiveDeadline")
            transport.safe_member(entry)
            require(entry.filename.casefold() not in names, "OriginalArchiveDuplicatePath")
            names.add(entry.filename.casefold())
            expanded += entry.file_size
            require(expanded <= lock["artifact"]["expanded_bytes"], "OriginalArchiveExpansionRejected")
            target = sdk.plain_path(destination / entry.filename, root=destination, exists=False)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                require(archive.read(entry) == b"", "NonEmptyArchiveDirectory")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            count, hasher = 0, hashlib.sha256()
            with archive.open(entry) as source, target.open("xb") as output:
                while block := source.read(256 * 1024):
                    require(time.monotonic() < deadline, "OriginalArchiveDeadline")
                    count += len(block)
                    require(count <= entry.file_size, "OriginalArchiveMemberExpanded")
                    hasher.update(block)
                    output.write(block)
            require(count == entry.file_size, "OriginalArchiveMemberTruncated")
            inventory[entry.filename] = {"bytes": count, "sha256": hasher.hexdigest()}
    require(expanded == lock["artifact"]["expanded_bytes"]
            and canonical(inventory) == lock["artifact"]["member_inventory_sha256"],
            "OriginalArchiveInventoryChanged")
    for name, expected in lock["critical_members"].items():
        require(inventory.get(name) == expected, "OriginalArchiveCriticalMemberChanged:" + name)
    return inventory


def pe_interface(data, *, require_dll=True):
    """Bounded, file-only AMD64 PE import/export parser; does not load code."""
    require(64 <= len(data) <= 256 * 1024 * 1024 and data[:2] == b"MZ", "PeDosHeaderRejected")

    def unpack(fmt, offset):
        require(0 <= offset <= len(data) - struct.calcsize(fmt), "PeReadOutsideFile")
        return struct.unpack_from(fmt, data, offset)

    nt = unpack("<I", 60)[0]
    require(nt >= 64 and data[nt:nt + 4] == b"PE\0\0", "PeSignatureRejected")
    machine, sections, _, _, _, optsize, characteristics = unpack("<HHIIIHH", nt + 4)
    require(machine == 0x8664 and 0 < sections <= 96 and optsize >= 240
            and unpack("<H", nt + 24)[0] == 0x20B, "PeAmd64Required")
    require(bool(characteristics & 0x2000) is require_dll, "PeImageKindRejected")
    optional = nt + 24
    require(unpack("<I", optional + 108)[0] >= 16, "PeDirectoriesIncomplete")
    ranges = []
    for number in range(sections):
        offset = optional + optsize + 40 * number
        vsize, rva, size, raw = unpack("<IIII", offset + 8)
        require(raw + size <= len(data), "PeSectionOutsideFile")
        ranges.append((rva, size, raw, vsize))

    def address(rva, size=1):
        matches = [(raw + rva - start) for start, rawsize, raw, _ in ranges
                   if start <= rva and rva + size <= start + rawsize]
        require(len(matches) == 1, "PeRvaMissingOrAmbiguous")
        return matches[0]

    def string(rva):
        start = address(rva)
        end = data.find(b"\0", start, min(start + 8192, len(data)))
        require(end >= start, "PeStringNotTerminated")
        address(rva, end - start + 1)
        return data[start:end].decode("ascii", errors="strict")

    exports = {}
    export_rva, export_size = unpack("<II", optional + 112)
    if export_rva:
        exp = address(export_rva, 40)
        base, nfunc, nname, functions, names, ordinals = unpack("<IIIIII", exp + 16)
        require(0 <= nname <= nfunc <= 50000, "PeExportCountRejected")
        func = address(functions, nfunc * 4)
        names_offset = address(names, nname * 4)
        ord_offset = address(ordinals, nname * 2)
        for i in range(nname):
            name = string(unpack("<I", names_offset + i * 4)[0])
            ordinal = unpack("<H", ord_offset + i * 2)[0]
            require(name and name not in exports and ordinal < nfunc, "PeExportEntryRejected")
            function_rva = unpack("<I", func + ordinal * 4)[0]
            require(function_rva and not export_rva <= function_rva < export_rva + export_size,
                    "PeNullOrForwardedExportRejected")
            exports[name] = base + ordinal
    imported = []
    import_rva, import_size = unpack("<II", optional + 120)
    if import_rva:
        require(20 <= import_size <= 64 * 1024, "PeImportSizeRejected")
        for i in range(min(import_size // 20, 256)):
            row = unpack("<IIIII", address(import_rva + i * 20, 20))
            if row == (0, 0, 0, 0, 0):
                break
            name = string(row[3]).casefold()
            require(re.fullmatch(r"[a-z0-9_.-]+\.dll", name) and name not in imported,
                    "PeImportNameRejected")
            imported.append(name)
        else:
            raise Rejected("PeImportTerminatorMissing")
    return {"machine": "AMD64", "exports": exports, "dependencies": sorted(imported)}


def member(root, inventory, name, sdk):
    require(name in inventory, "RequiredOriginalMemberMissing:" + name)
    path = sdk.plain_path(root / name, root=root)
    require(sdk.file_identity(path) == inventory[name], "ExtractedOriginalMemberChanged:" + name)
    return path


def verify_source_archive(root, inventory, lock, sdk, transport):
    manifest = read_json(member(root, inventory, "sdk/source-snapshot-files.json", sdk))
    receipt = read_json(member(root, inventory, "sdk/corresponding-source.json", sdk))
    require(len(manifest) == 23849 and canonical(manifest) == receipt["file_manifest_content_id"]
            and receipt["source"] == lock["recipe"]["source"]
            and receipt["patch"] == lock["recipe"]["patch"], "CorrespondingSourceBindingRejected")
    archive_path = member(root, inventory, "sdk/qtdeclarative-corresponding-source.zip", sdk)
    require(sdk.file_identity(archive_path) == receipt["archive"], "CorrespondingSourceArchiveChanged")
    actual, deadline = {}, time.monotonic() + MAX_ARCHIVE_SECONDS
    with zipfile.ZipFile(archive_path) as archive:
        require(len(archive.infolist()) == len(manifest), "CorrespondingSourceClosureCount")
        for entry in archive.infolist():
            require(time.monotonic() < deadline, "CorrespondingSourceDeadline")
            transport.safe_member(entry)
            require(entry.filename.startswith("qtdeclarative/"), "CorrespondingSourceRootRejected")
            relative = entry.filename.removeprefix("qtdeclarative/")
            require(not entry.is_dir() and relative in manifest and relative not in actual,
                    "CorrespondingSourceMemberRejected")
            raw = archive.read(entry)
            expected = {k: manifest[relative][k] for k in ("bytes", "sha256")}
            require(byte_id(raw) == expected, "CorrespondingSourceBytesChanged")
            actual[relative] = expected
            if relative == lock["recipe"]["patch"]["production_path"]:
                require(expected["sha256"] == lock["recipe"]["patch"]["postimage_sha256"],
                        "AllocatorPostimageChanged")
    require(set(actual) == set(manifest), "CorrespondingSourceClosureMissing")
    return receipt


def verify_fixture_records(root, inventory, lock, sdk):
    def get(name):
        return read_json(member(root, inventory, name, sdk))
    comparison = get("comparison/comparison.json")
    require(comparison["source_sha"] == lock["producer"]["merge"]
            and comparison["pr_head_sha"] == lock["producer"]["head"]
            and comparison["stage"] == "complete" and comparison["comparison_collected"] is True
            and comparison["success"] is False
            and comparison["errors"] == ["OriginalFixtureFailurePreserved; see separate stock and patched receipts"]
            and comparison["runtime_delta"] == {"added": [], "removed": [], "changed": ["Qt6Qml.dll"]},
            "OriginalFixtureFailureNotPreserved")
    outcomes = get("step-outcomes.json")
    require(outcomes["executing_workflow_sha"] == lock["producer"]["merge"]
            and outcomes["executing_pr_head_sha"] == lock["producer"]["head"]
            and outcomes["run_id"] == str(lock["producer"]["run"])
            and outcomes["run_attempt"] == "1" and outcomes["prepare_step"] == "success"
            and outcomes["boundaries_step"] == "success" and outcomes["sdk_step"] == "success"
            and outcomes["comparison_step"] == "failure", "ProducerStepReceiptRejected")
    summary = {}
    for variant in ("stock", "patched"):
        aggregate_name = "comparison/" + variant + "/aggregate.json"
        aggregate = get(aggregate_name)
        variant_record = comparison["variants"][variant]
        require(variant_record["aggregate"] == inventory[aggregate_name]
                and variant_record["collected"] is True
                and variant_record["runner_exit_code"] == (1 if variant == "stock" else 0)
                and aggregate["success"] is (variant == "patched"), "FixtureAggregateRejected")
        summary[variant] = {}
        for case in ("popup-normal", "popup-incremental", "sweep-slots"):
            prefix = "comparison/" + variant + "/" + case + "/"
            result = get(prefix + "receipt.json")
            proof = result["exit_proof"]
            success = variant == "patched" or case != "sweep-slots"
            require(result["source_sha"] == lock["producer"]["merge"]
                    and result["success"] is success and result["timed_out"] is False
                    and proof["exitCode"] == (0 if success else 2)
                    and proof["processSignaled"] is True and proof["ownedProcessSetEmpty"] is True
                    and proof["backend"] == "windows-single-process-job", "FixtureExitProofRejected")
            interpretation = variant_record["cases"][case]["interpretation"]
            require(interpretation["conclusive"] is True and not interpretation["warning_lines"],
                    "FixtureInterpretationRejected")
            if case == "sweep-slots":
                require(interpretation["same_bitmap_word_allocations"] == 8
                        and interpretation["free_runs_inside_live_objects"] == (8 if variant == "stock" else 0),
                        "AllocatorInvariantEvidenceChanged")
            else:
                require(interpretation["completed_helpers"] == 288 and interpretation["fixture_exit"] == 0
                        and interpretation["qml_warning_count"] == 0, "PopupCompatibilityEvidenceChanged")
                if case == "popup-incremental":
                    require(interpretation["actual_time_limit_us"] == 1000 and interpretation["yield_observed"] is True
                            and interpretation["pending_returns"] > 0, "IncrementalCoverageMissing")
            for name in ("stdout.log", "stderr.log"):
                path = member(root, inventory, prefix + name, sdk)
                require(sdk.file_identity(path) == {k: result["outputs"][name][k] for k in ("bytes", "sha256")},
                        "FixtureOutputBindingChanged")
            summary[variant][case] = {"success": success, "exit_proof": proof,
                                      "interpretation": interpretation}
    return summary


def producer_compiler_binding(receipt, native, lock):
    binary = receipt["tools"]["cl.exe"]
    path_key = binary["path"].replace("\\", "/").casefold()
    matches = [value for root, files in native.items() for name, value in files.items()
               if (root + "/" + name).replace("\\", "/").casefold() == path_key]
    require(len(matches) == 1 and matches[0] == {k: binary[k] for k in ("bytes", "sha256")}
            and binary == lock["content"]["producer_compiler_binary"], "ProducerCompilerBinaryBindingRejected")
    metadata = receipt["configuration"]["compiler_file"]
    require(metadata == lock["content"]["producer_compiler_metadata"]
            and metadata != matches[0], "CompilerMetadataIsNotBinaryIdentity")
    return {"metadata_file": metadata, "binary": binary}


def verify_artifact(root, inventory, lock, sdk, transport):
    def get(name):
        return read_json(member(root, inventory, name, sdk))
    recipe = get("sdk/reproduction/tools/qt612-qml-patch.lock.json")
    require(recipe == lock["recipe"], "ProducerRecipeChanged")
    receipt = get("sdk/receipt.json")
    require(receipt["source_sha"] == lock["producer"]["merge"]
            and receipt["pr_head_sha"] == lock["producer"]["head"]
            and receipt["success"] is True and receipt["stage"] == "complete"
            and receipt["stock_unchanged"] is True and receipt["errors"] == []
            and receipt["qt_source"] == recipe["source"] and receipt["qt_patch"] == recipe["patch"],
            "ProducerCompletedModuleUnproved")
    for source, expected in receipt["source_inputs"]["files"].items():
        name = "sdk/reproduction/" + source
        if name in inventory:
            require(sdk.file_identity(member(root, inventory, name, sdk)) == expected,
                    "ProducerReproductionSourceChanged")
    native = get("sdk/native-toolchain-files.json")
    require(canonical(native) == receipt["native_toolchain_content_id"] == lock["content"]["native_toolchain"],
            "ProducerToolchainInventoryChanged")
    compiler_binding = producer_compiler_binding(receipt, native, lock)
    derivation = canonical({"lock": recipe, "source_inputs": receipt["source_inputs"]["files"],
                            "tools": receipt["tools"], "configuration": receipt["configuration"],
                            "stock": receipt["stock_content_id"], "derived": receipt["derived_content_id"],
                            "native_toolchain": receipt["native_toolchain_content_id"]})
    require(derivation == receipt["derivation_id"] == lock["content"]["derivation"],
            "ProducerDerivationChanged")
    for name in ("10-configure", "11-qml-build", "12-install-qml-only"):
        command = get("sdk/commands/" + name + ".json")
        require(command["exit_code"] == 0 and command["process_signaled"] is True
                and command["owned_job_empty"] is True and command["timed_out"] is False
                and command["errors"] == [], "ProducerModuleCommandUnproved")
        if command["forced_cleanup"]:
            policy = command.get("compiler_controlled_retirement", {})
            require(name in ("10-configure", "11-qml-build") and policy.get("accepted") is True
                    and policy.get("helper_signaled") is True and policy.get("proved_within_original_deadline") is True
                    and policy.get("file_identity", {}).get("sha256") == recipe["compiler_retirement"]["sha256"],
                    "ProducerCleanupContractChanged")
    headers = get("sdk/header-alignment.json")
    require(sdk.verify_header_contract(headers, recipe) == receipt["header_contract"], "HeaderContractChanged")
    for row in headers:
        relative = row["path"]
        stock = member(root, inventory, "sdk/header-inputs/stock/" + relative, sdk).read_bytes()
        candidate = member(root, inventory, "sdk/header-inputs/candidate/" + relative, sdk).read_bytes()
        require(byte_id(stock) == row["stock"] and byte_id(candidate) == row["candidate_raw"],
                "RawHeaderIdentityChanged")
        if row["method"] == "canonical-source-LF-to-stock-CRLF":
            require(sdk.source_header_stock_bytes(candidate) == stock
                    and member(root, inventory, "sdk/header-inputs/expected-stock/" + relative, sdk).read_bytes() == stock,
                    "ExactSourceHeaderTransformChanged")
        elif row["method"] == "pinned-parser-CRLF-and-seven-exact-line-paths":
            require(sdk.expected_parser_bytes(stock, recipe["header_identity"]["parser"]) == candidate,
                    "ExactParserTransformChanged")
        else:
            require(row["method"] == "exact-generated" and candidate == stock, "GeneratedHeaderChanged")
    before, after, derived = [get("sdk/" + name + ".json") for name in
                              ("stock-files-before", "stock-files-after", "derived-files")]
    require(before == after and len(before) == lock["content"]["stock_files"]
            and len(derived) == lock["content"]["derived_files"]
            and canonical(before) == lock["content"]["stock"] == receipt["stock_content_id"]
            and canonical(derived) == lock["content"]["derived"] == receipt["derived_content_id"],
            "WholeKitOriginalInventoryChanged")
    module = get("sdk/module-files.json")
    require(len(module) == lock["content"]["module_files"] == receipt["module_install"]["files"],
            "ModuleInstallClosureCountChanged")
    for name, expected in module.items():
        require(sdk.file_identity(member(root, inventory, "sdk/module-install-output/" + name, sdk)) == expected,
                "ModuleInstallBytesChanged")
    retained = receipt["module_install"]["retained_stock_headers"]
    require(len(retained) == 287 and len(set(retained)) == 287
            and sorted(retained) == sorted(r["path"] for r in headers if r["stock"] != r["candidate_raw"]),
            "RetainedOfficialHeadersChanged")
    expected = dict(before)
    expected.update({name: item for name, item in module.items() if name not in retained})
    require(derived == expected and sdk.compare_tree(before, derived) == lock["content"]["delta"],
            "DerivedKitDeltaChanged")
    pe_review = get("sdk/pe-interface-review.json")
    require(pe_review == lock["pe_interface"], "PeInterfaceReviewChanged")
    parsed = {}
    for variant in ("stock", "patched"):
        exports = member(root, inventory, "sdk/commands/13-" + variant + "-exports.stdout.log", sdk)
        dependents = member(root, inventory, "sdk/commands/15-" + variant + "-dependents.stdout.log", sdk)
        parsed[variant] = {"exports": sdk.parse_exports(exports.read_text(encoding="utf-8-sig")),
                           "dependencies": sdk.parse_dependents(dependents.read_text(encoding="utf-8-sig"))}
    require(parsed["stock"] == parsed["patched"] and len(parsed["patched"]["exports"]) == 6659
            and parsed["patched"]["dependencies"] == pe_review["patched_dependencies"],
            "ActualDumpbinInterfaceChanged")
    dll = member(root, inventory, "sdk/module-install-output/bin/Qt6Qml.dll", sdk)
    actual_pe = pe_interface(dll.read_bytes())
    require(actual_pe["exports"] == parsed["patched"]["exports"]
            and actual_pe["dependencies"] == parsed["patched"]["dependencies"]
            and sdk.file_identity(dll) == lock["content"]["qml_patched"], "ActualPatchedPeInterfaceChanged")
    source = verify_source_archive(root, inventory, lock, sdk, transport)
    fixtures = verify_fixture_records(root, inventory, lock, sdk)
    return {"receipt": receipt, "stock_files": before, "derived_files": derived, "module_files": module,
            "headers": headers, "retained_headers": retained, "interface": parsed["patched"],
            "corresponding_source": source, "fixtures": fixtures,
            "verification": {"original_conclusion": "failure", "stock_negative_preserved": True,
                             "patched_fixtures_passed": True, "actual_archive_members": len(inventory),
                             "source_files_checked": 23849, "actual_patched_pe_exports": len(actual_pe["exports"]),
                             "producer_compiler_binding": compiler_binding,
                             "stock_content_id": canonical(before), "derived_content_id": canonical(derived),
                             "derivation_id": derivation, "product_root_cause_claimed": False}}


def git(repository, *arguments):
    result = subprocess.run(["git", "-C", str(repository), *arguments], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    require(len(result.stdout) <= 1024 * 1024 and len(result.stderr) <= 64 * 1024, "GitSourceOutputLimit")
    return result.stdout.decode("utf-8", errors="strict").strip()


def commit_header(repository):
    # Unlike pretty-format %P, the raw commit object retains true parents at a
    # shallow checkout boundary. Do not require downloading repository history.
    raw = git(repository, "cat-file", "-p", "HEAD")
    header = raw.split("\n\n", 1)[0].splitlines()
    trees = [line.removeprefix("tree ") for line in header if line.startswith("tree ")]
    parents = [line.removeprefix("parent ") for line in header if line.startswith("parent ")]
    require(len(trees) == 1 and COMMIT.fullmatch(trees[0])
            and all(COMMIT.fullmatch(parent) for parent in parents), "CommitObjectHeadersRejected")
    return {"tree_sha": trees[0], "parents": parents}


def event_source(event, environment, source, parents, lock):
    """Read-only public build provenance, independent of diagnostic PR opt-ins."""
    expected = lock["repository"]
    require(environment.get("GITHUB_REPOSITORY") == expected["name"]
            and event.get("repository", {}).get("id") == expected["id"]
            and COMMIT.fullmatch(source) and source == environment.get("GITHUB_SHA")
            and all(COMMIT.fullmatch(parent) for parent in parents), "CurrentRepositorySourceRejected")
    kind, ref = environment.get("GITHUB_EVENT_NAME"), environment.get("GITHUB_REF", "")
    require(re.fullmatch(r"refs/(?:heads|tags|pull)/[A-Za-z0-9_./-]+", ref)
            and ".." not in ref, "CurrentGitHubRefRejected")
    head = base = None
    if kind == "pull_request":
        pr = event.get("pull_request", {})
        head, base = pr.get("head", {}).get("sha"), pr.get("base", {}).get("sha")
        number = pr.get("number")
        require(type(number) is int and event.get("number") == number
                and pr.get("head", {}).get("repo", {}).get("id") == expected["id"]
                and pr.get("base", {}).get("repo", {}).get("id") == expected["id"]
                and pr.get("base", {}).get("ref") in ("test", "main")
                and COMMIT.fullmatch(head or "") and COMMIT.fullmatch(base or "")
                and ref == "refs/pull/" + str(number) + "/merge" and parents == [base, head],
                "SameRepositoryPrMergeRequired")
    elif kind == "push":
        require(event.get("ref") == ref and ref.startswith(("refs/heads/", "refs/tags/"))
                and event.get("after") == source and event.get("deleted") is False,
                "PushSourceBindingRejected")
    elif kind == "workflow_dispatch":
        event_ref = event.get("ref", "")
        require(ref.startswith(("refs/heads/", "refs/tags/"))
                and event_ref in (ref, ref.split("/", 2)[2]), "DispatchSourceBindingRejected")
    else:
        raise Rejected("PublicBuildEventRejected")
    return {"source_sha": source, "pr_head_sha": head, "base_sha": base,
            "event_name": kind, "ref": ref, "parents": parents}


def current_context(repository, lock, sdk):
    require(os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_OS") == "Windows" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted",
            "GitHubHostedWindowsRequired")
    repository = sdk.plain_path(repository)
    require(repository == sdk.plain_path(Path(os.environ["GITHUB_WORKSPACE"])) and HERE.parent == repository,
            "CurrentRepositoryRequired")
    event = read_json(Path(os.environ["GITHUB_EVENT_PATH"]))
    source = git(repository, "rev-parse", "HEAD")
    commit = commit_header(repository)
    binding = event_source(event, os.environ, source, commit["parents"], lock)
    require(git(repository, "status", "--porcelain", "--untracked-files=no") == "", "TrackedSourceDirty")
    for name in (*OWN_PATHS, *lock["reuse_inputs"]):
        # The new product policy itself must come from this commit.
        require(git(repository, "ls-files", "--error-unmatch", "--", name) == name,
                "ProductSourceNotTracked")
    require(os.environ.get("GITHUB_RUN_ID", "").isdecimal()
            and os.environ.get("GITHUB_RUN_ATTEMPT", "").isdecimal(), "CurrentRunIdentityRejected")
    return {**binding, "tree_sha": commit["tree_sha"],
            "repository": lock["repository"]["name"],
            "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "product_inputs": {name: sdk.file_identity(repository / name) for name in OWN_PATHS},
            "shared_inputs": lock["reuse_inputs"]}


def require_disjoint(paths):
    values = [Path(p).resolve() for p in paths]
    for i, path in enumerate(values):
        for other in values[i + 1:]:
            require(path != other and not path.is_relative_to(other) and not other.is_relative_to(path),
                    "StockOutputEvidenceMustBeDisjoint")


def cmake_literal(value):
    value = str(value).replace("\\", "/")
    require(not any(c in value for c in '\x00\r\n";$<>'), "CmakeCaptureLiteralRejected")
    return value


def capture_hook(selected, context, content_id):
    prefix = cmake_literal(selected)
    source = context["source_sha"]
    require(COMMIT.fullmatch(source) and SHA.fullmatch(content_id), "CaptureIdentityRejected")
    # A read-only deferred query after the actual application target exists.
    # It neither sets a Qt property nor changes compile/link flags or test gates.
    return ('''# Generated by Compose-Qt612ProductSdk.py; product target observation only.
function(swirl_capture_selected_qt)
  if(NOT TARGET Qt6::Qml OR NOT TARGET Qt6::QmlPrivate OR NOT TARGET Swirl)
    message(FATAL_ERROR "Selected Qt product targets are missing")
  endif()
  get_target_property(dll Qt6::Qml IMPORTED_LOCATION_RELEASE)
  get_target_property(implib Qt6::Qml IMPORTED_IMPLIB_RELEASE)
  get_target_property(private_includes Qt6::QmlPrivate INTERFACE_INCLUDE_DIRECTORIES)
  if(NOT dll STREQUAL "@PREFIX@/bin/Qt6Qml.dll" OR NOT implib STREQUAL "@PREFIX@/lib/Qt6Qml.lib")
    message(FATAL_ERROR "Actual Qt6::Qml imports are outside the selected SDK")
  endif()
  if(NOT private_includes)
    message(FATAL_ERROR "Selected Qml private include property is missing")
  endif()
  # Qt exports conditional include properties. Capture the evaluated Release
  # paths at generation; the independent verifier requires both real private
  # directories and rejects every nonempty path outside this complete SDK.
  file(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/swirl-selected-qt-$<CONFIG>.txt"
    CONTENT "schema=1\\nsource_sha=@SOURCE@\\ncontent_id=@CONTENT@\\nconfiguration=$<CONFIG>\\nqml_dll=$<TARGET_FILE:Qt6::Qml>\\nqml_import_library=$<TARGET_LINKER_FILE:Qt6::Qml>\\nqml_private_includes=$<TARGET_GENEX_EVAL:Qt6::QmlPrivate,$<TARGET_PROPERTY:Qt6::QmlPrivate,INTERFACE_INCLUDE_DIRECTORIES>>\\napplication=$<TARGET_FILE:Swirl>\\ncompiler=${CMAKE_CXX_COMPILER}\\ncompiler_version=${CMAKE_CXX_COMPILER_VERSION}\\ncompiler_id=${CMAKE_CXX_COMPILER_ID}\\ncmake=${CMAKE_COMMAND}\\nsource_directory=${CMAKE_SOURCE_DIR}\\nbuild_directory=${CMAKE_BINARY_DIR}\\n")
endfunction()
cmake_language(DEFER CALL swirl_capture_selected_qt)
'''.replace("@PREFIX@", prefix).replace("@SOURCE@", source).replace("@CONTENT@", content_id)).encode()


def query_tools(selected, evidence, sdk):
    output = {}
    for name, arguments, expected in (
            ("qmake", ["-query", "QT_INSTALL_PREFIX"], selected),
            ("qtpaths", ["--query", "QT_INSTALL_PREFIX"], selected),
            ("windeployqt", ["--version"], "6.12.0")):
        executable = sdk.plain_path(selected / "bin" / (name + ".exe"), root=selected)
        command = sdk.run_logged([str(executable), *arguments], selected,
                                 evidence, "selected-" + name, 20, env=sdk.tool_environment())
        raw = (evidence / ("selected-" + name + ".stdout.log")).read_text(encoding="utf-8-sig").strip()
        require(not (evidence / ("selected-" + name + ".stderr.log")).read_bytes().strip(),
                "SelectedQtToolUnexpectedStderr")
        if name == "windeployqt":
            require(raw == expected or raw == "windeployqt " + expected, "SelectedQtToolVersionRejected")
        else:
            require(sdk.plain_path(Path(raw)) == expected, "SelectedQtToolPrefixRejected")
        output[name] = {"path": str(executable), **sdk.file_identity(executable),
                        "query": raw, "command_receipt": sdk.file_identity(evidence / ("selected-" + name + ".json")),
                        "actual_exit_code": command["exit_code"]}
    return output


def qtenv2_bytes(kit_root):
    # aqtinstall 3.3.0 Updater.make_qtenv2 writes exactly these five lines.
    # The two absolute paths are installer output, not invariant archive bytes.
    # Do not normalize the input file, execute it, or accept other substitutions.
    require(isinstance(kit_root, str) and len(kit_root) <= 240
            and re.fullmatch(r"[A-Za-z]:\\[A-Za-z0-9_. \\-]+", kit_root),
            "QtEnvironmentRootRejected")
    root = PureWindowsPath(kit_root)
    require(root.is_absolute() and str(root) == kit_root
            and all(part not in (".", "..") and not part.endswith((" ", "."))
                    for part in root.parts[1:]), "QtEnvironmentRootRejected")
    return ("@echo off\r\n"
            "echo Setting up environment for Qt usage...\r\n"
            "set PATH=" + kit_root + "\\bin;%PATH%\r\n"
            "cd /D " + kit_root + "\r\n"
            "echo Remember to call vcvarsall.bat to complete environment setup!\r\n").encode("ascii")


def installation_inventories(stock_root, artifact, lock):
    rule = lock["installation_qtenv2"]
    name = rule["path"]
    require(name == "bin/qtenv2.bat"
            and artifact["receipt"]["stock_root"] == rule["producer_kit_root"]
            and byte_id(qtenv2_bytes(rule["producer_kit_root"])) == rule["producer_file"]
            == artifact["stock_files"].get(name) == artifact["derived_files"].get(name),
            "ProducerQtEnvironmentIdentityRejected")
    installed = byte_id(qtenv2_bytes(str(stock_root)))
    before, derived = dict(artifact["stock_files"]), dict(artifact["derived_files"])
    before[name] = derived[name] = installed
    binding = {"schema": 1, "rule": rule, "stock_kit_root": str(stock_root),
               "installed_file": installed, "producer_stock_content_id": lock["content"]["stock"],
               "producer_selected_content_id": lock["content"]["derived"],
               "stock_content_id": canonical(before), "selected_content_id": canonical(derived),
               "selected_qtenv2_copied_from_stock": True, "qtenv2_executed": False,
               "scope": "Only the two exact installer path fields differ from the producer; "
                        "the cloned batch file still targets stock and is not a selected-kit launcher. "
                        "Product tools and CMake targets use verified absolute selected-kit paths."}
    return before, derived, binding


def validate_installed_identity(receipt, before, actual, binding, lock):
    require(receipt.get("stock_content_id") == canonical(before) == binding["stock_content_id"]
            and receipt.get("selected_content_id") == canonical(actual) == binding["selected_content_id"]
            and receipt.get("producer_stock_content_id") == lock["content"]["stock"]
            and receipt.get("producer_selected_content_id") == lock["content"]["derived"]
            and receipt.get("installation_binding") == binding,
            "InstalledReceiptContentBindingRejected")


def actual_kit_check(stock, selected, artifact, lock, sdk):
    expected_stock, expected_selected, binding = installation_inventories(stock, artifact, lock)
    before = sdk.inventory(stock)
    require(before == expected_stock, "InstalledOfficialKitContentMismatch")
    actual = sdk.inventory(selected)
    require(actual == expected_selected, "SelectedKitContentMismatch")
    require((stock / "bin/qtenv2.bat").read_bytes() == (selected / "bin/qtenv2.bat").read_bytes()
            == qtenv2_bytes(str(stock)), "InstalledQtEnvironmentBytesChanged")
    old_pe = pe_interface((stock / "bin/Qt6Qml.dll").read_bytes())
    new_pe = pe_interface((selected / "bin/Qt6Qml.dll").read_bytes())
    require(old_pe == new_pe and {k: old_pe[k] for k in ("exports", "dependencies")} == artifact["interface"],
            "ActualStockPatchedPeMismatch")
    return before, actual, binding


def compose(args, lock, sdk, transport, report):
    repository = sdk.plain_path(Path(args.repository))
    context = current_context(repository, lock, sdk)
    stock = sdk.plain_path(Path(args.stock_kit))
    selected = sdk.plain_path(Path(args.selected_kit), exists=False)
    evidence = sdk.plain_path(Path(args.evidence), exists=False)
    require_disjoint((stock, selected, evidence))
    require(not selected.exists(), "SelectedKitMustBeFresh")
    report.update({"consumer": context, "stock_kit": str(stock), "selected_kit": str(selected)})
    metadata, token = fetch_producer(lock, transport, evidence)
    report["producer_metadata"] = metadata
    archive = evidence / "original-sdk.zip"
    if args.archive:
        supplied = sdk.plain_path(Path(args.archive))
        require(sdk.file_identity(supplied) == {k: lock["artifact"][k] for k in ("bytes", "sha256")},
                "SuppliedArchiveIdentityRejected")
        shutil.copyfile(supplied, archive)
    else:
        # No URL/ID is accepted from argv. The shared transport strips auth on
        # the single allowlisted GitHub artifact redirect and checks TLS normally.
        download_fixed_artifact(lock, archive, token, transport)
    del token
    extracted = evidence / "original-sdk"
    inventory = audit_archive(archive, extracted, lock, sdk, transport)
    write_json(evidence / "original-member-inventory.json", inventory)
    artifact = verify_artifact(extracted, inventory, lock, sdk, transport)
    report["original_artifact_verification"] = artifact["verification"]
    before = sdk.inventory(stock)
    write_json(evidence / "stock-files-before.json", before)
    expected_stock, expected_selected, installation = installation_inventories(stock, artifact, lock)
    write_json(evidence / "expected-installation-identity.json", installation)
    require(before == expected_stock, "InstalledOfficialKitContentMismatch")
    raw_environment = (stock / "bin/qtenv2.bat").read_bytes()
    require(raw_environment == qtenv2_bytes(str(stock)), "InstalledQtEnvironmentBytesChanged")
    (evidence / "stock-qtenv2.bat.raw").write_bytes(raw_environment)
    stage = extracted / "sdk/module-install-output"
    staged, changes, retained = sdk.verify_module_stage(stage, stock, artifact["headers"])
    require(staged == artifact["module_files"] and sorted(retained) == sorted(artifact["retained_headers"])
            and sorted(changes) == sorted(artifact["receipt"]["module_install"]["approved_changes"]),
            "ActualModuleInstallClosureChanged")
    derived = sdk.compose_derived_kit(stock, stage, selected, before, staged, retained)
    require(derived == expected_selected, "ComposedKitContentMismatch")
    tools = query_tools(selected, evidence / "tool-queries", sdk)
    unchanged, actual, checked_installation = actual_kit_check(stock, selected, artifact, lock, sdk)
    require(unchanged == before and checked_installation == installation, "InstallationChangedDuringComposition")
    write_json(evidence / "stock-files-after.json", unchanged)
    write_json(evidence / "selected-files.json", actual)
    (evidence / "selected-qtenv2.bat.raw").write_bytes((selected / "bin/qtenv2.bat").read_bytes())
    require(current_context(repository, lock, sdk) == context, "ConsumerSourceChangedDuringComposition")
    hook = evidence / "selected-qt.cmake"
    hook.write_bytes(capture_hook(selected, context, canonical(actual)))
    dlls = {name: sdk.file_identity(selected / name) for name in ("bin/Qt6Qml.dll", "lib/Qt6Qml.lib")}
    pdb = {name: sdk.file_identity(selected / name) if (selected / name).is_file() else None
           for name in ("bin/Qt6Qml.pdb", "lib/Qt6Qml.pdb")}
    selected_receipt = {"schema": 1, "kind": "swirl-selected-qt612-product-sdk", "success": True,
        "consumer": context, "producer": lock["producer"], "artifact": lock["artifact"],
        "producer_metadata": metadata, "original_workflow_conclusion": "failure",
        "stock_negative_preserved": True, "qt_version": lock["qt_version"],
        "qt_source": lock["recipe"]["source"], "qt_patch": lock["recipe"]["patch"],
        "stock_kit_root": str(stock), "kit_root": str(selected),
        "stock_content_id": canonical(before), "selected_content_id": canonical(actual),
        "producer_stock_content_id": lock["content"]["stock"],
        "producer_selected_content_id": lock["content"]["derived"], "installation_binding": installation,
        "derivation_id": lock["content"]["derivation"], "content_delta": lock["content"]["delta"],
        "sdk_evidence_dir": str(extracted / "sdk"), "artifact_root": str(extracted),
        "artifact_archive": str(archive), "member_inventory": str(evidence / "original-member-inventory.json"),
        "lock": sdk.file_identity(LOCK_PATH), "qml_files": dlls, "qml_pdb_files": pdb,
        "producer_compiler": lock["content"]["producer_compiler"],
        "producer_compiler_binary": lock["content"]["producer_compiler_binary"],
        "producer_compiler_metadata": lock["content"]["producer_compiler_metadata"],
        "absolute_tools": tools, "cmake_capture_hook": {"path": str(hook), **sdk.file_identity(hook)},
        "corresponding_source": artifact["corresponding_source"],
        "stock_unchanged": True, "actual_process_module_sampling": False,
        "product_vme_root_cause_proved": False, "product_acceptance": "pending new source CI",
        "pairing_scope": "Qt SDK composition only; Rust/OpenSSL/CRT and installation gates remain independent",
        "created_utc": datetime.now(timezone.utc).isoformat()}
    write_json(evidence / "selected-sdk.json", selected_receipt)
    report.update({"success": True, "selected_receipt": sdk.file_identity(evidence / "selected-sdk.json"),
                   "selected_content_id": canonical(actual), "stock_unchanged": True})


def capture_values(text):
    require(len(text) <= 64 * 1024 and "\0" not in text, "CmakeCaptureSizeRejected")
    result = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        require(separator and re.fullmatch(r"[a-z_]+", key) and key not in result, "CmakeCaptureShapeRejected")
        result[key] = value
    expected = {"schema", "source_sha", "content_id", "configuration", "qml_dll", "qml_import_library",
                "qml_private_includes", "application", "compiler", "compiler_version", "compiler_id",
                "cmake", "source_directory", "build_directory"}
    require(set(result) == expected and result["schema"] == "1" and result["configuration"] == "Release",
            "CmakeCaptureSchemaRejected")
    return result


def validate_configuration(build, selected, repository, context, receipt, lock, sdk, *, require_application):
    content_id = receipt.get("selected_content_id")
    require(isinstance(content_id, str) and SHA.fullmatch(content_id), "InstalledContentIdentityMissing")
    cache_path = sdk.plain_path(build / "CMakeCache.txt", root=build)
    cache = sdk.cache_values(cache_path.read_text(encoding="utf-8-sig"))
    require(cache.get("CMAKE_BUILD_TYPE") == "Release" or "Release" in cache.get("CMAKE_CONFIGURATION_TYPES", "").split(";"),
            "ProductReleaseConfigurationMissing")
    for name in ("Qt6_DIR", "Qt6Qml_DIR", "Qt6QmlPrivate_DIR"):
        require(name in cache, "RequiredQtCmakeDirectoryMissing")
    directories, unavailable_optional_packages = {}, []
    for name, value in cache.items():
        if re.fullmatch(r"Qt6[A-Za-z0-9_]*_DIR", name):
            if not value or value.endswith("-NOTFOUND"):
                require(name not in ("Qt6_DIR", "Qt6Qml_DIR", "Qt6QmlPrivate_DIR"), "RequiredQtCmakePackageMissing")
                unavailable_optional_packages.append(name)
                continue
            path = sdk.plain_path(Path(value), root=selected)
            require(path == selected / "lib/cmake" / name[:-4], "QtCmakePackageOutsideSelectedKit")
            directories[name] = str(path)
    hook = Path(receipt["cmake_capture_hook"]["path"])
    require(cache.get("CMAKE_PROJECT_TOP_LEVEL_INCLUDES", "").replace("\\", "/") == hook.as_posix(),
            "ActualCmakeCaptureHookMissing")
    require(hook.read_bytes() == capture_hook(selected, context, content_id)
            and sdk.file_identity(hook) == {k: receipt["cmake_capture_hook"][k] for k in ("bytes", "sha256")},
            "CmakeCaptureHookChanged")
    capture_path = sdk.plain_path(build / "swirl-selected-qt-Release.txt", root=build)
    values = capture_values(capture_path.read_text(encoding="utf-8-sig"))
    require(values["source_sha"] == context["source_sha"] and values["content_id"] == content_id,
            "CmakeCaptureSourceChanged")
    for key, expected in (("qml_dll", selected / "bin/Qt6Qml.dll"),
                          ("qml_import_library", selected / "lib/Qt6Qml.lib"),
                          ("source_directory", repository / "src/Swirl.Quick"), ("build_directory", build)):
        require(sdk.plain_path(Path(values[key])) == expected, "CmakeActualTargetPathRejected:" + key)
    # Empty members are the actual result of Qt's conditional export entries;
    # they grant no header path. Both required directories must still be present.
    private = [value for value in values["qml_private_includes"].split(";") if value]
    required = {str(selected / "include/QtQml/6.12.0"), str(selected / "include/QtQml/6.12.0/QtQml")}
    actual = {str(sdk.plain_path(Path(value), root=selected)) for value in private}
    require(required <= actual, "CmakePrivateHeaderClosureMissing")
    compiler = sdk.plain_path(Path(values["compiler"]))
    producer = lock["content"]["producer_compiler"]
    require(values["compiler_id"] == producer["CMAKE_CXX_COMPILER_ID"]
            and values["compiler_version"] == producer["CMAKE_CXX_COMPILER_VERSION"]
            and sdk.file_identity(compiler) == {k: lock["content"]["producer_compiler_binary"][k] for k in ("bytes", "sha256")},
            "ProductCompilerDiffersFromPinnedQmlCompiler")
    version_parts = [cache.get("CMAKE_CACHE_" + part + "_VERSION", "") for part in ("MAJOR", "MINOR", "PATCH")]
    require(all(part.isdecimal() for part in version_parts), "CmakeCacheVersionMissing")
    compiler_metadata = sdk.plain_path(build / "CMakeFiles" / ".".join(version_parts) / "CMakeCXXCompiler.cmake", root=build)
    configured_compiler = sdk.compiler_values(compiler_metadata.read_text(encoding="utf-8-sig"))
    require(configured_compiler["CMAKE_CXX_COMPILER_ID"] == values["compiler_id"]
            and configured_compiler["CMAKE_CXX_COMPILER_VERSION"] == values["compiler_version"]
            and configured_compiler["MSVC_CXX_ARCHITECTURE_ID"] == "x64"
            and sdk.plain_path(Path(configured_compiler["CMAKE_CXX_COMPILER"])) == compiler,
            "GeneratedCompilerMetadataBindingChanged")
    # Visual Studio generators can keep the compiler path outside the cache.
    # Its generated compiler metadata and the actual DEFER capture remain
    # mandatory above; a cache entry, when present, must also agree.
    if "CMAKE_CXX_COMPILER" in cache:
        require(sdk.plain_path(Path(cache["CMAKE_CXX_COMPILER"])) == compiler,
                "CmakeCachedCompilerBindingChanged")
    require(sdk.plain_path(Path(cache["CMAKE_COMMAND"])) == sdk.plain_path(Path(values["cmake"])),
            "CmakeActualExecutableBindingChanged")
    application = sdk.plain_path(Path(values["application"]), root=build, exists=require_application)
    result = {"cache": sdk.file_identity(cache_path), "capture": sdk.file_identity(capture_path),
              "qt_directories": directories, "unavailable_optional_qt_packages": sorted(unavailable_optional_packages),
              "actual_target": values, "compiler_metadata": sdk.file_identity(compiler_metadata),
              "configured_compiler": configured_compiler,
              "compiler_file": sdk.file_identity(compiler), "application": None}
    if require_application:
        pe = pe_interface(application.read_bytes(), require_dll=False)
        require("qt6qml.dll" in pe["dependencies"], "ApplicationDoesNotImportSelectedQtQml")
        result["application"] = {"path": str(application), **sdk.file_identity(application),
                                  "actual_pe_imports": pe["dependencies"]}
    return result


def verify_deployment(runtime, selected_files, application, sdk, *, observed_inventory_path=None):
    files = sdk.inventory(runtime)
    # Preserve the actual disk observation even when a later comparison fails.
    # This file is not a successful deployment receipt.
    if observed_inventory_path is not None:
        write_json(observed_inventory_path, files)
    require(files.get("Qt6Qml.dll") == selected_files["bin/Qt6Qml.dll"], "DeployedQtQmlMismatch")
    app_name = Path(application["path"]).name
    require(files.get(app_name) == {k: application[k] for k in ("bytes", "sha256")},
            "DeployedApplicationMismatch")
    qt_files = {}
    for relative, actual in files.items():
        if not relative.lower().endswith(".dll"):
            continue
        candidates = ["bin/" + relative, "plugins/" + relative, relative]
        matches = [name for name in candidates if name in selected_files]
        if matches:
            require(any(selected_files[name] == actual for name in matches), "DeployedQtFileMismatch:" + relative)
            qt_files[relative] = {"file": actual, "sdk_members": matches}
        elif re.fullmatch(r"Qt6[A-Za-z0-9_]+\.dll", Path(relative).name, re.IGNORECASE):
            raise Rejected("UnmappedQtRuntimeDll:" + relative)
    for name in application["actual_pe_imports"]:
        if name.startswith("qt6"):
            matches = [relative for relative in qt_files if "/" not in relative and relative.casefold() == name]
            require(len(matches) == 1, "ApplicationQtImportNotDeployed")
    external_shader_compilers = {name: value for name, value in files.items()
        if Path(name).name.casefold() in ("dxcompiler.dll", "dxil.dll") and name not in qt_files}
    return {"runtime_content_id": canonical(files), "runtime_files": files, "qt_files": qt_files,
            "shader_compilers_outside_selected_kit": external_shader_compilers,
            "scope": "Disk bytes and PE imports; not process module sampling or Rust/OpenSSL/CRT acceptance"}


def verified_selection(args, lock, sdk, transport):
    repository = sdk.plain_path(Path(args.repository))
    context = current_context(repository, lock, sdk)
    receipt_path = sdk.plain_path(Path(args.receipt))
    receipt = read_json(receipt_path)
    require(receipt.get("schema") == 1 and receipt.get("kind") == "swirl-selected-qt612-product-sdk"
            and receipt.get("success") is True and receipt.get("consumer") == context
            and receipt.get("lock") == sdk.file_identity(LOCK_PATH)
            and receipt.get("producer") == lock["producer"] and receipt.get("artifact") == lock["artifact"],
            "SelectedReceiptBindingRejected")
    stock = sdk.plain_path(Path(receipt["stock_kit_root"]))
    selected = sdk.plain_path(Path(receipt["kit_root"]))
    evidence = sdk.plain_path(Path(args.evidence), exists=False)
    require_disjoint((stock, selected, evidence))
    extracted = sdk.plain_path(Path(receipt["artifact_root"]))
    archive = sdk.plain_path(Path(receipt["artifact_archive"]))
    require(sdk.file_identity(archive) == {k: lock["artifact"][k] for k in ("bytes", "sha256")},
            "SelectedReceiptArchiveChanged")
    inventory = read_json(Path(receipt["member_inventory"]))
    require(canonical(inventory) == lock["artifact"]["member_inventory_sha256"], "SelectedMemberInventoryChanged")
    # Every extracted member is checked, including original stdout/stderr bytes.
    for name in inventory:
        member(extracted, inventory, name, sdk)
    artifact = verify_artifact(extracted, inventory, lock, sdk, transport)
    before, actual, installation = actual_kit_check(stock, selected, artifact, lock, sdk)
    validate_installed_identity(receipt, before, actual, installation, lock)
    return {"repository": repository, "context": context, "receipt_path": receipt_path,
            "receipt": receipt, "stock": stock, "selected": selected, "evidence": evidence,
            "before": before, "actual": actual, "artifact": artifact}


def d3d_image_identity(data):
    """Read only the fixed redistributable's PE architecture; never load it."""
    require(len(data) >= 64 and data[:2] == b"MZ", "D3dImageHeaderRejected")
    nt = struct.unpack_from("<I", data, 60)[0]
    require(64 <= nt <= len(data) - 26 and data[nt:nt + 4] == b"PE\0\0",
            "D3dImageHeaderRejected")
    machine, _, _, _, _, optional_size, characteristics = struct.unpack_from("<HHIIIHH", data, nt + 4)
    require(machine == 0x8664 and characteristics & 0x2000
            and optional_size >= 240 and nt + 24 + optional_size <= len(data)
            and struct.unpack_from("<H", data, nt + 24)[0] == 0x20B, "D3dAmd64DllRequired")
    return {"machine": "AMD64", "image_kind": "DLL", "optional_header_magic": 0x20B}


def copy_fixed_d3d(selected, runtime, expected, sdk, record):
    # The caller obtains expected from the complete original-artifact and
    # installed-kit verification, not from a command-line hash or receipt flag.
    require_disjoint((selected, runtime))
    require(isinstance(expected, dict) and set(expected) == {"bytes", "sha256"} and type(expected["bytes"]) is int
            and 64 <= expected["bytes"] <= 16 * 1024 * 1024
            and isinstance(expected["sha256"], str) and SHA.fullmatch(expected["sha256"]),
            "D3dPinnedIdentityMissing")
    source = sdk.plain_path(selected / "bin/d3dcompiler_47.dll", root=selected)
    destination = sdk.plain_path(runtime / "d3dcompiler_47.dll", root=runtime, exists=False)
    require(source != destination and runtime.is_dir(), "D3dDestinationRejected")
    with source.open("rb") as stream:
        raw = stream.read(expected["bytes"] + 1)
    require(byte_id(raw) == expected == sdk.file_identity(source), "SelectedD3dCompilerChanged")
    pe = d3d_image_identity(raw)
    matches = [p for p in runtime.iterdir() if p.name.casefold() == "d3dcompiler_47.dll"]
    require(len(matches) <= 1 and (not matches or matches[0] == destination),
            "D3dDestinationAmbiguous")
    before = sdk.file_identity(destination) if destination.exists() else None
    record.update({"source": {"path": str(source), **expected, "pe": pe},
                   "destination": str(destination), "before": before,
                   "copied": False, "after": None})
    if before != expected:
        temporary = sdk.plain_path(runtime / ".swirl-selected-d3dcompiler-47.copy.tmp",
                                   root=runtime, exists=False)
        require(not temporary.exists(), "D3dTemporaryMustBeFresh")
        created = False
        try:
            with temporary.open("xb") as stream:
                created = True
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            require(sdk.file_identity(temporary) == expected
                    and sdk.file_identity(source) == expected, "D3dCopyIdentityChanged")
            os.replace(temporary, destination)
            record["copied"] = True
        except BaseException:
            if created and temporary.exists():
                try:
                    temporary.unlink()
                except OSError as error:
                    record["temporary_cleanup_error"] = type(error).__name__
            raise
    after = sdk.file_identity(destination)
    record["after"] = after
    require(after == expected and sdk.file_identity(source) == expected,
            "DeployedD3dCompilerChanged")
    # DXC is not supplied by this fixed Qt kit. Preserve its existing deployment
    # behavior and record any observed bytes without granting a selected-kit pin.
    record["shader_compilers_outside_selected_kit"] = {
        p.name: sdk.file_identity(sdk.plain_path(p, root=runtime)) for p in runtime.iterdir()
        if p.name.casefold() in ("dxcompiler.dll", "dxil.dll")}


def copy_d3d(args, lock, sdk, transport, report):
    state = verified_selection(args, lock, sdk, transport)
    stock, selected, evidence = (state[name] for name in ("stock", "selected", "evidence"))
    runtime = sdk.plain_path(Path(args.runtime_dir))
    require_disjoint((stock, selected, runtime, evidence))
    name = "bin/d3dcompiler_47.dll"
    expected = state["actual"].get(name)
    artifact = state["artifact"]
    require(expected is not None and expected == artifact["stock_files"].get(name)
            == artifact["derived_files"].get(name), "D3dOriginalArtifactBindingRejected")
    report.update({"consumer": state["context"],
                   "selected_receipt": sdk.file_identity(state["receipt_path"]),
                   "selected_content_id": canonical(state["actual"]),
                   "original_conclusion": "failure", "d3d_compiler": {},
                   "scope": "Copy only the fixed original-kit D3D compiler; no code execution. "
                            "DXC/DXIL retain their existing deployment behavior and are not selected-kit pins."})
    copy_fixed_d3d(selected, runtime, expected, sdk, report["d3d_compiler"])
    report["runtime_shader_metadata"] = {}
    write_shader_runtime_metadata(runtime, expected, sdk, report["runtime_shader_metadata"])
    require(current_context(state["repository"], lock, sdk) == state["context"],
            "ConsumerSourceChangedDuringD3dCopy")
    report.update({"success": True, "selected_source_unchanged": True,
                   "product_acceptance": "not implied by a file copy"})


def write_shader_runtime_metadata(runtime, expected, sdk, record):
    """Preserve the concurrent PS entry point's schema; metadata is not authority."""
    require(sdk.file_identity(sdk.plain_path(runtime / "d3dcompiler_47.dll", root=runtime)) == expected,
            "ShaderMetadataD3dIdentityChanged")
    document = {"schema": 1, "source": "selected-qt-sdk", "files": {
        "d3dcompiler_47.dll": {"sha256": expected["sha256"], "bytes": expected["bytes"]}}}
    raw = (json.dumps(document, ensure_ascii=True, indent=2) + "\n").encode()
    identity = byte_id(raw)
    target = sdk.plain_path(runtime / "qt-shader-runtime.json", root=runtime, exists=False)
    before = sdk.file_identity(target) if target.exists() else None
    record.update({"path": str(target), "before": before, "after": None,
                   "document": document, "written": False})
    if before != identity:
        temporary = sdk.plain_path(runtime / ".swirl-qt-shader-runtime.json.copy.tmp",
                                   root=runtime, exists=False)
        require(not temporary.exists(), "ShaderMetadataTemporaryMustBeFresh")
        created = False
        try:
            with temporary.open("xb") as stream:
                created = True
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            require(sdk.file_identity(temporary) == identity, "ShaderMetadataCopyChanged")
            os.replace(temporary, target)
            record["written"] = True
        except BaseException:
            if created and temporary.exists():
                try:
                    temporary.unlink()
                except OSError as error:
                    record["temporary_cleanup_error"] = type(error).__name__
            raise
    record["after"] = sdk.file_identity(target)
    require(record["after"] == identity, "ShaderMetadataChanged")


def verify(args, lock, sdk, transport, report):
    state = verified_selection(args, lock, sdk, transport)
    repository, context, receipt_path, receipt, stock, selected, evidence, before, actual = (
        state[name] for name in ("repository", "context", "receipt_path", "receipt", "stock",
                                "selected", "evidence", "before", "actual"))
    build = sdk.plain_path(Path(args.build_dir))
    require_disjoint((stock, selected, build, evidence))
    configuration = validate_configuration(build, selected, repository, context, receipt, lock, sdk,
                                          require_application=args.phase != "configured")
    report.update({"consumer": context, "selected_receipt": sdk.file_identity(receipt_path),
                   "selected_content_id": canonical(actual), "stock_content_id": canonical(before),
                   "configuration": configuration, "original_conclusion": "failure"})
    if args.phase == "post-deploy":
        require(args.runtime_dir is not None, "PostDeployRuntimeRequired")
        runtime = sdk.plain_path(Path(args.runtime_dir))
        require_disjoint((stock, selected, runtime, evidence))
        observed = evidence / "runtime-files-observed.json"
        report["observed_runtime_inventory"] = {"path": str(observed),
            "scope": "Raw disk observation written before comparisons; it does not indicate acceptance."}
        deployment = verify_deployment(runtime, actual, configuration["application"], sdk,
                                       observed_inventory_path=observed)
        report["observed_runtime_inventory"]["file"] = sdk.file_identity(observed)
        write_json(evidence / "runtime-files.json", deployment.pop("runtime_files"))
        report["deployment"] = deployment
    else:
        require(args.runtime_dir is None, "RuntimeOnlyAcceptedAfterDeployment")
    require(current_context(repository, lock, sdk) == context, "ConsumerSourceChangedDuringVerification")
    report.update({"success": True, "stock_unchanged": True,
                   "actual_process_module_sampling": False, "product_acceptance": "not implied by SDK verification"})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=HERE.parent)
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit-artifact", help="offline bytes/source verification only; no selected SDK")
    audit.add_argument("--archive", type=Path, required=True)
    audit.add_argument("--producer-metadata", type=Path, required=True)
    audit.add_argument("--evidence", type=Path, required=True)
    composition = commands.add_parser("compose")
    composition.add_argument("--stock-kit", type=Path, required=True)
    composition.add_argument("--selected-kit", type=Path, required=True)
    composition.add_argument("--archive", type=Path)
    composition.add_argument("--evidence", type=Path, required=True)
    verification = commands.add_parser("verify")
    verification.add_argument("--receipt", type=Path, required=True)
    verification.add_argument("--build-dir", type=Path, required=True)
    verification.add_argument("--runtime-dir", type=Path)
    verification.add_argument("--phase", choices=("configured", "pre-deploy", "post-deploy"), required=True)
    verification.add_argument("--evidence", type=Path, required=True)
    d3d_copy = commands.add_parser("copy-d3d", help="copy the one fixed selected-kit D3D compiler")
    d3d_copy.add_argument("--receipt", type=Path, required=True)
    d3d_copy.add_argument("--runtime-dir", type=Path, required=True)
    d3d_copy.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {"schema": 1, "kind": "qt612-product-sdk-" + args.command, "success": False,
              "errors": [], "started_utc": datetime.now(timezone.utc).isoformat(),
              "runtime_executed": False, "product_vme_root_cause_proved": False}
    evidence, owns_evidence = None, False
    try:
        lock = load_lock()
        sdk, transport = load_support(args.repository, lock)
        evidence = sdk.plain_path(Path(args.evidence), exists=False)
        # Refuse overwriting even an earlier failed attempt's evidence.
        require(not evidence.exists(), "FreshEvidenceRequired")
        if args.command == "compose":
            stock = sdk.plain_path(Path(args.stock_kit))
            selected = sdk.plain_path(Path(args.selected_kit), exists=False)
            require_disjoint((stock, selected, evidence))
            require(not selected.exists(), "SelectedKitMustBeFresh")
        elif args.command in ("verify", "copy-d3d"):
            selected_record = read_json(sdk.plain_path(Path(args.receipt)))
            require_disjoint((sdk.plain_path(Path(selected_record["stock_kit_root"])),
                              sdk.plain_path(Path(selected_record["kit_root"])), evidence))
        sdk.fresh_directory(evidence)
        owns_evidence = True
        if args.command == "audit-artifact":
            metadata = {name: read_json(args.producer_metadata / (name + ".json"))
                        for name in ("run", "jobs", "artifact")}
            report["historical_producer_metadata"] = validate_producer(**metadata, lock=lock, require_unexpired=False)
            inventory = audit_archive(sdk.plain_path(args.archive), evidence / "original-sdk", lock, sdk, transport)
            write_json(evidence / "original-member-inventory.json", inventory)
            result = verify_artifact(evidence / "original-sdk", inventory, lock, sdk, transport)
            report.update({"success": True, "verification": result["verification"],
                           "scope": "Offline fixed original evidence; no fresh SDK composition or current GitHub admission",
                           "selected_sdk_created": False})
        elif args.command == "compose":
            compose(args, lock, sdk, transport, report)
        elif args.command == "copy-d3d":
            copy_d3d(args, lock, sdk, transport, report)
        else:
            verify(args, lock, sdk, transport, report)
    except BaseException as error:
        # Do not serialize arbitrary exception strings: urllib errors can contain
        # temporary signed URLs. Fixed policy codes are safe; all other errors
        # retain their type, and public command logs are saved separately.
        code = str(error).split(":", 1)[0]
        report["errors"].append(str(error) if isinstance(error, Rejected) else
            type(error).__name__ + (":" + code if isinstance(error, RuntimeError)
                                   and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,100}", code) else ""))
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        if owns_evidence and args.command == "compose" and not report["success"]:
            original = evidence / "stock-files-before.json"
            if original.is_file() and "stock_kit" in report:
                try:
                    after = sdk.inventory(Path(report["stock_kit"]))
                    report["stock_unchanged"] = after == read_json(original)
                    if not (evidence / "stock-files-after.json").exists():
                        write_json(evidence / "stock-files-after.json", after)
                    if not report["stock_unchanged"]:
                        report["errors"].append("OfficialStockChangedAfterFailure")
                except Exception as error:
                    report["errors"].append("FailureStockEvidence:" + type(error).__name__)
        if owns_evidence:
            write_json(evidence / "receipt.json", report)
        print(json.dumps({"success": report["success"], "command": args.command, "errors": report["errors"]}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
