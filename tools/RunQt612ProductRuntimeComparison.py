#!/usr/bin/env python3
"""Fixed d136 QA bytes: closure audit, then original product cases. No build/deploy/live mode."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
def load_tool(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

sdk = load_tool("swirl_product_owned_job", "Build-Qt612QmlDiagnosticSdk.py")
reader = load_tool("swirl_product_fixed_artifacts", "ReadPr61ArtifactEvidence.py")
LABEL = "qa-qt612-product-runtime"
CACHE_KEY = "apec-qt612-msvc-Windows-59b4e3306e3d2b0956c30227f2b07b0bad7a34b0c9b7b0d7abb39c76e370419d-082b4956bfe1f416398b268e050cb933a8b0b72160d0c2bec1827df3045f0f2c-e76d264b9b5dfe1f1becdbef7dc8fceb3506a0ab"
SDK_RECEIPT_PIN = {"bytes": 66395, "sha256": "ca9c401827665956e929be87934d20252b61d525154da97148990fc1d0b7f361"}
PUBLIC_SOURCE_FILES = {
    "SwirlCodexManage.py": "tools/SwirlCodexManage.py",
    "SubscriptionCapture.py": "tools/SubscriptionCapture.py",
}
ORIGINAL_LOGS = {
    "Swirl-diagnostics.txt": "build-evidence/deployed-all-pages.log",
    "Swirl-input-diagnostics.txt": "build-evidence/overview-input.log",
}
OWN_FILES = (
    "tools/RunQt612ProductRuntimeComparison.py", "tools/Build-Qt612QmlDiagnosticSdk.py",
    "tools/ReadPr61ArtifactEvidence.py", "tools/tests/test_qt612_product_runtime_comparison.py",
    ".github/workflows/diagnose-qt612-product-runtime.yml",
)
require, plain, identity = sdk.require, sdk.plain_path, sdk.file_identity


def write(path, value):
    sdk.write_json(path, value)


def safe_error(error):
    # Neither signed download URLs nor inherited credentials enter public evidence.
    return type(error).__name__ + (":" + str(error) if isinstance(error, (RuntimeError, reader.EvidenceError)) else "")


def fixed_context():
    require(os.name == "nt", "WindowsOnly")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pr = event.get("pull_request", {})
    require(os.environ.get("GITHUB_REPOSITORY") == reader.REPOSITORY
            and event.get("repository", {}).get("id") == reader.REPOSITORY_ID
            and event.get("action") == "labeled" and event.get("label", {}).get("name") == LABEL
            and event.get("number") == 61 and pr.get("number") == 61
            and pr.get("head", {}).get("ref") == reader.BRANCH
            and pr.get("head", {}).get("repo", {}).get("id") == reader.REPOSITORY_ID
            and pr.get("base", {}).get("ref") == "test", "FixedProductEventRejected")
    repository = plain(Path(os.environ["GITHUB_WORKSPACE"]))
    helper = plain(HERE.parent)
    require(helper == repository / "diagnostic-helper", "SeparateHelperCheckoutRequired")
    helper_sha = subprocess.check_output(["git", "-C", str(helper), "rev-parse", "HEAD"], text=True).strip()
    require(helper_sha == os.environ["GITHUB_SHA"] and sdk.COMMIT.fullmatch(helper_sha), "HelperSourceMismatch")
    for root in (repository, helper):
        subprocess.run(["git", "-C", str(root), "diff", "--quiet", "HEAD", "--"], check=True)
    target = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    require(target == sdk.PRODUCT_MERGE, "TargetSourceMismatch")
    require(subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD^{tree}"],
                                     text=True).strip() == reader.TARGET_TREE, "TargetTreeMismatch")
    parents = subprocess.check_output(["git", "-C", str(repository), "show", "-s", "--format=%P", "HEAD"],
                                      text=True).strip().split()
    require(parents == [reader.TARGET_BASE, sdk.PRODUCT_HEAD], "TargetParentsMismatch")
    run, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    require(run.isdecimal() and attempt.isdecimal(), "InvalidOwnedRunIdentity")
    work = plain(Path(os.environ["RUNNER_TEMP"])) / ("swirl-product-d136-" + run + "-" + attempt)
    evidence = repository / "build-evidence/qt612-product-comparison"
    files = {name: identity(helper / name) for name in OWN_FILES}
    context = {"helper_source_sha": helper_sha, "helper_pr_head_sha": pr["head"]["sha"],
               "target_source_sha": target, "target_pr_head_sha": sdk.PRODUCT_HEAD,
               "target_tree_sha": reader.TARGET_TREE, "target_parents": parents,
               "run_id": run, "run_attempt": attempt, "helper_inputs": files,
               "cache_key": CACHE_KEY, "runtime_executed": False, "real_provider_requests": 0,
               "product_sdk_changed": False, "release_result": "not-run",
               "scope": "Fixed original d136 QA product comparison; not acceptance of helper-source product."}
    return repository, helper, work, evidence, context


def verify_original_metadata(kind, token, evidence):
    target = reader.TARGETS[kind]
    prefix = "/repos/" + reader.REPOSITORY
    run = reader.api(prefix + "/actions/runs/" + str(target["run"]), token)
    require(run.get("id") == target["run"] and run.get("repository", {}).get("id") == reader.REPOSITORY_ID
            and run.get("head_repository", {}).get("id") == reader.REPOSITORY_ID
            and run.get("head_sha") == sdk.PRODUCT_HEAD and run.get("head_branch") == reader.BRANCH
            and run.get("event") == "pull_request" and run.get("path") == target["workflow"]
            and run.get("run_attempt") == 1 and run.get("status") == "completed"
            and run.get("conclusion") == "failure", "OriginalRunBindingFailed")
    listing = reader.api(prefix + "/actions/runs/" + str(target["run"]) + "/artifacts?per_page=100", token)
    require(type(listing.get("total_count")) is int and listing["total_count"] <= 100, "OriginalArtifactListingIncomplete")
    matches = [a for a in listing["artifacts"] if a.get("id") == target["artifact"]]
    require(len(matches) == 1, "OriginalArtifactMissingOrAmbiguous")
    artifact = matches[0]
    owner = artifact.get("workflow_run", {})
    require(artifact.get("name") == target["name"] and artifact.get("expired") is False
            and artifact.get("size_in_bytes") == target["bytes"]
            and artifact.get("digest") == "sha256:" + target["sha256"]
            and owner.get("id") == target["run"] and owner.get("repository_id") == reader.REPOSITORY_ID
            and owner.get("head_repository_id") == reader.REPOSITORY_ID
            and owner.get("head_sha") == sdk.PRODUCT_HEAD and owner.get("head_branch") == reader.BRANCH,
            "OriginalArtifactBindingFailed")
    require(dt.datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
            > dt.datetime.now(dt.timezone.utc), "OriginalArtifactExpired")
    write(evidence / ("original-" + kind + "-run.json"), run)
    write(evidence / ("original-" + kind + "-artifact.json"), artifact)
    return target


def audit_zip(path, target, destination=None):
    require(identity(path) == {k: target[k] for k in ("bytes", "sha256")}, "OriginalZipIdentityChanged")
    result, folded, expanded = {}, set(), 0
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(0 < len(entries) <= reader.MAX_MEMBERS, "OriginalZipMemberLimit")
        for info in entries:
            reader.safe_member(info)
            require(info.filename.casefold() not in folded, "OriginalZipDuplicatePath")
            folded.add(info.filename.casefold())
            expanded += info.file_size
            require(expanded <= reader.MAX_EXPANDED, "OriginalZipExpansionLimit")
            output = None
            if destination is not None:
                target_path = plain(destination / info.filename, root=destination, exists=False)
                if info.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    output = target_path.open("xb")
            count, hasher = 0, hashlib.sha256()
            try:
                with archive.open(info) as stream:
                    while True:
                        block = stream.read(256 * 1024)
                        if not block:
                            break
                        count += len(block)
                        require(count <= info.file_size, "OriginalZipMemberActualSize")
                        hasher.update(block)
                        if output:
                            output.write(block)
                require(count == info.file_size, "OriginalZipMemberTruncated")
            finally:
                if output:
                    output.close()
            if not info.is_dir():
                result[info.filename] = {"bytes": count, "sha256": hasher.hexdigest()}
    return result


def locate(root, inventory, suffix):
    names = [name for name in inventory if name == suffix or name.endswith("/" + suffix)]
    require(len(names) == 1, "OriginalMemberMissingOrAmbiguous:" + suffix)
    path = plain(root / names[0], root=root)
    require(identity(path) == inventory[names[0]], "OriginalExtractedMemberChanged:" + suffix)
    return path


def json_member(root, inventory, suffix):
    return sdk.read_json(locate(root, inventory, suffix))


def verify_sdk(root, inventory):
    receipt_path = locate(root, inventory, "sdk/receipt.json")
    require(identity(receipt_path) == SDK_RECEIPT_PIN, "SdkReceiptPinMismatch")
    receipt = sdk.read_json(receipt_path)
    comparison = json_member(root, inventory, "comparison/comparison.json")
    require(receipt["source_sha"] == sdk.PRODUCT_MERGE and receipt["pr_head_sha"] == sdk.PRODUCT_HEAD
            and receipt["success"] is True and receipt["stage"] == "complete"
            and receipt["stock_unchanged"] is True and receipt["errors"] == [], "SdkBuildUnproved")
    require(comparison["source_sha"] == sdk.PRODUCT_MERGE and comparison["pr_head_sha"] == sdk.PRODUCT_HEAD
            and comparison["sdk_receipt"] == SDK_RECEIPT_PIN and comparison["comparison_collected"] is True
            and comparison["success"] is False
            and comparison["errors"] == ["OriginalFixtureFailurePreserved; see separate stock and patched receipts"],
            "SdkOriginalFailureNotPreserved")
    require(comparison["runtime_delta"] == {"added": [], "removed": [], "changed": ["Qt6Qml.dll"]},
            "SdkRuntimeHasOtherChanges")
    # Use the target's committed lock, never a caller-supplied hash or receipt flag.
    target_repo = plain(Path(os.environ["GITHUB_WORKSPACE"]))
    lock = sdk.read_json(target_repo / sdk.LOCK)
    require(receipt["qt_source"] == lock["source"] and receipt["qt_patch"] == lock["patch"], "SdkSourcePatchMismatch")
    headers = json_member(root, inventory, "sdk/header-alignment.json")
    require(sdk.verify_header_contract(headers, lock) == receipt["header_contract"], "SdkHeaderContractMismatch")
    module = json_member(root, inventory, "sdk/module-files.json")
    require(len(module) == 380 and receipt["module_install"]["files"] == 380, "SdkModuleClosureCount")
    for relative, expected in module.items():
        require(identity(locate(root, inventory, "sdk/module-install-output/" + relative)) == expected,
                "SdkInstalledModuleBytesChanged:" + relative)
    for row in headers:
        relative = row["path"]
        stock = locate(root, inventory, "sdk/header-inputs/stock/" + relative).read_bytes()
        candidate = locate(root, inventory, "sdk/header-inputs/candidate/" + relative).read_bytes()
        require(sdk.byte_identity(stock) == row["stock"] and sdk.byte_identity(candidate) == row["candidate_raw"],
                "SdkRawHeaderIdentityMismatch")
        if row["method"] == "canonical-source-LF-to-stock-CRLF":
            require(sdk.source_header_stock_bytes(candidate) == stock
                    and locate(root, inventory, "sdk/header-inputs/expected-stock/" + relative).read_bytes() == stock,
                    "SdkSourceHeaderTransformMismatch")
        elif row["method"] == "pinned-parser-CRLF-and-seven-exact-line-paths":
            require(sdk.expected_parser_bytes(stock, lock["header_identity"]["parser"]) == candidate,
                    "SdkParserExactTransformMismatch")
        else:
            require(row["method"] == "exact-generated" and candidate == stock, "SdkGeneratedHeaderMismatch")
    before = json_member(root, inventory, "sdk/stock-files-before.json")
    after = json_member(root, inventory, "sdk/stock-files-after.json")
    derived = json_member(root, inventory, "sdk/derived-files.json")
    require(before == after and sdk.canonical_digest(before) == receipt["stock_content_id"]
            and sdk.canonical_digest(derived) == receipt["derived_content_id"], "SdkWholeKitInventoryMismatch")
    retained = receipt["module_install"]["retained_stock_headers"]
    require(len(retained) == 287 and len(set(retained)) == 287
            and sorted(retained) == sorted(r["path"] for r in headers if r["stock"] != r["candidate_raw"]),
            "SdkRetainedHeaderSetMismatch")
    expected = dict(before)
    expected.update({k: v for k, v in module.items() if k not in retained})
    require(derived == expected and all(derived[p] == before[p] for p in retained), "SdkStockHeadersNotRetained")
    for variant in ("stock", "patched"):
        for case in ("popup-normal", "popup-incremental", "sweep-slots"):
            result = json_member(root, inventory, "comparison/" + variant + "/" + case + "/receipt.json")
            proof = result["exit_proof"]
            require(result["source_sha"] == sdk.PRODUCT_MERGE and not result["timed_out"]
                    and proof["processSignaled"] and proof["ownedProcessSetEmpty"]
                    and proof["backend"] == "windows-single-process-job", "SdkFixtureExitUnproved")
            expected_success = variant == "patched" or case != "sweep-slots"
            require(result["success"] is expected_success and proof["exitCode"] == (0 if expected_success else 2),
                    "SdkFixtureOutcomeChanged")
            for log in ("stdout.log", "stderr.log"):
                raw = locate(root, inventory, "comparison/" + variant + "/" + case + "/" + log)
                require(identity(raw) == {k: result["outputs"][log][k] for k in ("bytes", "sha256")},
                        "SdkFixtureLogBindingChanged")
    dll = locate(root, inventory, "sdk/module-install-output/bin/Qt6Qml.dll")
    require(identity(dll) == sdk.PRODUCT_QML_PINS["patched"], "SdkPatchedDllPinMismatch")
    return dll, {"receipt": SDK_RECEIPT_PIN, "derivation_id": receipt["derivation_id"],
                 "stock_content_id": receipt["stock_content_id"], "derived_content_id": receipt["derived_content_id"],
                 "original_workflow_conclusion": "failure", "stock_sweep_failure_preserved": True,
                 "loaded_module_sampling_in_original_sdk": False}


def recovery_source(name, repository, package_root, package_index, cached):
    if name in ORIGINAL_LOGS:
        return locate(package_root, package_index, ORIGINAL_LOGS[name]), "original-package-text"
    if name in PUBLIC_SOURCE_FILES:
        return repository / PUBLIC_SOURCE_FILES[name], "target-git-source"
    if name.startswith("rules/"):
        return repository / "src/Swirl.Quick/packaging" / name, "target-git-rules"
    path = cached / name
    if path.exists():
        return path, "exact-compiled-cache"
    if name in ("lib/fonts/segoeui.ttf", "lib/fonts/arial.ttf"):
        return Path(os.environ["WINDIR"]) / "Fonts" / Path(name).name, "local-windows-font"
    return path, "exact-compiled-cache"


def restore_runtime(expected, repository, package_root, package_index, destination):
    require(not destination.exists(), "FreshRuntimeDestinationRequired")
    destination.mkdir(parents=True)
    cached = repository / "build/swirl-quick/Release"
    rows, failures = [], []
    for name, wanted in sorted(expected.items()):
        row = {"path": name, "expected": wanted, "status": "not-restored"}
        try:
            source, origin = recovery_source(name, repository, package_root, package_index, cached)
            row.update(origin=origin, source_path=str(source))
            if not source.is_file():
                row["status"] = "missing"
            else:
                source = plain(source)
                actual = identity(source)
                row["actual"] = actual
                if actual != wanted:
                    row["status"] = "mismatch"
                else:
                    target = plain(destination / name, root=destination, exists=False)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open("rb") as incoming, target.open("xb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing, 256 * 1024)
                    require(identity(target) == wanted, "RestoredFileIdentityChanged")
                    row["status"] = "matched"
        except Exception as error:
            row.update(status="ambiguous-or-invalid", error=safe_error(error))
        rows.append(row)
        if row["status"] != "matched":
            failures.append(row)
    return {"files": rows, "failures": failures, "all_1516_matched": len(rows) == 1516 and not failures,
            "font_files_uploaded": False, "cache_key_is_not_a_byte_proof": True}


def prepare(repository, work, evidence, context):
    require(not work.exists() and not evidence.exists(), "FreshPreparationRequired")
    work.mkdir(parents=True)
    evidence.mkdir(parents=True)
    report = {**context, "phase": "prepare", "status": "not-run", "all_1516_matched": False,
              "started_utc": sdk.utc(), "errors": []}
    try:
        cache_ok = (os.environ.get("SWIRL_PRODUCT_CACHE_HIT") == "true"
                    and os.environ.get("SWIRL_PRODUCT_CACHE_KEY") == CACHE_KEY)
        report["exact_cache_restored"] = cache_ok
        if not cache_ok:
            report["errors"].append("ExactCompiledCacheNotRestored")
        token = os.environ.get("GH_TOKEN")
        require(type(token) is str and token, "ReadOnlyArtifactTokenRequired")
        indexes = {}
        for kind in ("package", "sdk"):
            target = verify_original_metadata(kind, token, evidence)
            archive = work / (kind + "-original.zip")
            reader.download(target, archive, token)
            root = work / "original" / kind
            root.mkdir(parents=True)
            indexes[kind] = audit_zip(archive, target, root)
            write(evidence / (kind + "-verified-members.json"), indexes[kind])
        package_root, package_index = work / "original/package", indexes["package"]
        original_manifest = locate(package_root, package_index, "build-evidence/full-motion-qa/runtime-before.json")
        require(identity(original_manifest) == sdk.PRODUCT_MANIFEST_PIN, "OriginalRuntimeManifestPinMismatch")
        inputs = work / "inputs"
        inputs.mkdir()
        manifest = inputs / "runtime-before.json"
        shutil.copyfile(original_manifest, manifest)
        expected = sdk.product_manifest(manifest)
        original_smoke = json_member(package_root, package_index, "build-evidence/full-motion-qa/receipt.json")
        require(original_smoke["source_sha"] == sdk.PRODUCT_MERGE
                and original_smoke["pr_head_sha"] == sdk.PRODUCT_HEAD
                and original_smoke["expected_flavor"] == "qa"
                and original_smoke["status"] == "failed"
                and original_smoke["original_runtime_unchanged"] is True, "OriginalProductFailureBinding")
        write(evidence / "original-full-motion-receipt.json", original_smoke)
        dll, sdk_review = verify_sdk(work / "original/sdk", indexes["sdk"])
        report["sdk"] = sdk_review
        restored = restore_runtime(expected, repository, package_root, package_index, work / "runtimes/stock")
        write(evidence / "closure-audit.json", restored)
        report["all_1516_matched"] = restored["all_1516_matched"]
        report["closure_failure_count"] = len(restored["failures"])
        if restored["failures"]:
            report["errors"].append("OriginalRuntimeClosureIncomplete")
        if not report["errors"]:
            sdk.product_runtime_identity(work / "runtimes/stock", manifest, "stock")
            require(identity(repository / "build/swirl-quick/Release/Swirl.exe") == sdk.PRODUCT_EXE_PIN,
                    "OriginalCachedReferenceMismatch")
            rust = sdk.read_json(work / "runtimes/stock/swirl-rust-build.json")
            require(rust["source_sha"] == sdk.PRODUCT_MERGE, "OriginalRustSourceMismatch")
            shutil.copytree(work / "runtimes/stock", work / "runtimes/patched")
            shutil.copyfile(dll, work / "runtimes/patched/Qt6Qml.dll")
            baseline = sdk.product_runtime_identity(work / "runtimes/stock", manifest, "stock")
            changed = sdk.product_runtime_identity(work / "runtimes/patched", manifest, "patched")
            delta = {"added": sorted(set(changed) - set(baseline)),
                     "removed": sorted(set(baseline) - set(changed)),
                     "changed": sorted(p for p in set(baseline) & set(changed) if baseline[p] != changed[p])}
            require(delta == {"added": [], "removed": [], "changed": ["Qt6Qml.dll"]}, "ProductUnexpectedRuntimeDelta")
            write(evidence / "runtime-delta.json", delta)
            write(evidence / "stock-runtime-before.json", baseline)
            write(evidence / "patched-runtime-before.json", changed)
            report.update(status="prepared", original_manifest=sdk.PRODUCT_MANIFEST_PIN,
                          stock_content_id=sdk.canonical_digest(baseline),
                          patched_content_id=sdk.canonical_digest(changed))
    except Exception as error:
        report["errors"].append(safe_error(error))
    finally:
        report["finished_utc"] = sdk.utc()
        write(evidence / "prepare.json", report)
        print(json.dumps({"phase": "prepare", "status": report["status"],
                          "all_1516_matched": report["all_1516_matched"], "errors": report["errors"]}))
    return 0 if report["status"] == "prepared" else 1


def revalidate_preparation(repository, work, evidence, context):
    previous = sdk.read_json(evidence / "prepare.json")
    require(previous["helper_source_sha"] == context["helper_source_sha"]
            and previous["target_source_sha"] == context["target_source_sha"]
            and previous["helper_inputs"] == context["helper_inputs"], "PreparationSourceChanged")
    # Neither the previous status nor its booleans grant permission. Fixed original
    # ZIP hashes, original manifest and SDK bytes are verified again in this process.
    indexes = {kind: audit_zip(work / (kind + "-original.zip"), reader.TARGETS[kind])
               for kind in ("package", "sdk")}
    package = work / "original/package"
    original = locate(package, indexes["package"], "build-evidence/full-motion-qa/runtime-before.json")
    require(identity(original) == sdk.PRODUCT_MANIFEST_PIN
            and identity(work / "inputs/runtime-before.json") == sdk.PRODUCT_MANIFEST_PIN,
            "OriginalManifestChangedBetweenPhases")
    verify_sdk(work / "original/sdk", indexes["sdk"])
    for variant in ("stock", "patched"):
        sdk.product_runtime_identity(work / "runtimes" / variant, work / "inputs/runtime-before.json", variant)
    require(identity(repository / "build/swirl-quick/Release/Swirl.exe") == sdk.PRODUCT_EXE_PIN,
            "CachedReferenceChangedBetweenPhases")
    return previous


def collect_full_motion(output, command):
    report = sdk.read_json(output / "receipt.json")
    require(report["source_sha"] == sdk.PRODUCT_MERGE and report["pr_head_sha"] == sdk.PRODUCT_HEAD
            and report["expected_flavor"] == "qa" and report["original_runtime_unchanged"] is True,
            "ProductSmokeReceiptBinding")
    observed = {item["role"]: item for item in command["product_phase"]["observations"]}
    require(len(report["cases"]) == 2 and set(observed) == {"rapid", "ready"}, "ProductSmokeCaseCoverage")
    vme = False
    for case in report["cases"]:
        mode = case["mode"]
        observation = observed[mode]
        require(case["process_id"] == observation["pid"] and case["process_exit_observed"]
                and case["exit_code"] == observation["actual_exit_code"], "ProductSmokeActualExitMismatch")
        raw = output / mode / "Swirl-diagnostics.txt"
        require(identity(raw)["sha256"] == case["log_sha256"], "ProductSmokeRawLogMismatch")
        text = raw.read_text(encoding="utf-8-sig")
        vme = vme or "Cannot find member data" in text or "is not a function" in text
    return {"status": report["status"], "success": report["status"] == "passed",
            "original_receipt": identity(output / "receipt.json"), "vme_observed": vme,
            "cases": report["cases"], "errors": report["errors"]}


def collect_node(output, plan, command):
    import re
    app = Path(plan["app"])
    raw = app / "Swirl-node-ui-diagnostics.txt"
    result = {"success": False, "status": "failed", "errors": [], "node_counts": [104, 88]}
    if raw.is_file():
        copied = output / raw.name
        shutil.copyfile(raw, copied)
        text = copied.read_text(encoding="utf-8-sig")
        result["raw_log"] = identity(copied)
        totals = re.findall(r"Node UI checks:\s*(\d+)\s*checks,\s*(\d+)\s*failures", text)
        result["test_totals"] = totals
        result["warning_lines"] = [line for line in text.splitlines()
                                  if re.search(r"^[123]: |Cannot find member data|is not a function", line)]
        if len(totals) != 1 or int(totals[0][0]) <= 0 or int(totals[0][1]) != 0:
            result["errors"].append("OriginalNodeAssertionsFailedOrMissing")
        if result["warning_lines"]:
            result["errors"].append("OriginalNodeWarningGateFailed")
    else:
        result["errors"].append("OriginalNodeDiagnosticMissing")
    manifests = []
    for count in (104, 88):
        suffix = "" if count == 104 else "-88"
        for name in ("node-probe-geometry" + suffix + ".json",
                     "node-probe-transition-negative-control-" + str(count) + ".json",
                     "node-probe-continuous-latency-" + str(count) + ".json",
                     "node-probe-lifecycle-" + str(count) + ".json"):
            path = output / name
            if not path.is_file():
                result["errors"].append("MissingNodeEvidence:" + name)
                continue
            value = sdk.read_json(path)
            if value.get("source_sha") != sdk.PRODUCT_MERGE or value.get("nodeCount") != count:
                result["errors"].append("NodeEvidenceIdentityMismatch:" + name)
            if "negative-control" in name and not (value.get("baselineClear") is True
                                                   and value.get("exactOverlapDetected") is True):
                result["errors"].append("NodeNegativeControlMissing:" + name)
            if "lifecycle" in name and value.get("warnings") != []:
                result["errors"].append("NodeLifecycleWarnings:" + name)
            manifests.append({"path": name, **identity(path)})
    result["required_reports"] = manifests
    observation = command["product_phase"]["observations"]
    require(len(observation) == 1 and observation[0]["pid"] == command["pid"]
            and observation[0]["actual_exit_code"] == command["exit_code"], "NodeActualExitMismatch")
    if command["exit_code"] != 0:
        result["errors"].append("OriginalNodeNonzeroExit")
    result["success"] = not result["errors"]
    result["status"] = "passed" if result["success"] else "failed"
    return result


def execute(repository, work, evidence, context):
    report = {**context, "phase": "execute", "status": "not-run", "success": False,
              "comparison_collected": False, "causal_result": "incomplete", "cases": {}, "execution_attempted": False,
              "original_run_conclusions": {"product": "failure", "sdk": "failure"},
              "started_utc": sdk.utc(), "errors": []}
    try:
        require(not (evidence / "comparison.json").exists(), "ExistingProductComparisonWillNotBeOverwritten")
        revalidate_preparation(repository, work, evidence, context)
        powershell = plain(Path(os.environ["ProgramFiles"]) / "PowerShell/7/pwsh.exe")
        for variant in ("stock", "patched"):
            report["cases"][variant] = {}
            for kind in ("full-motion", "node-offscreen", "node-native"):
                report["execution_attempted"] = True
                command = sdk.run_product_logged(kind, variant, repository, work, evidence, powershell)
                report["runtime_executed"] = True
                require(command["process_signaled"] and command["owned_job_empty"]
                        and command["product_phase"]["complete"] and not command["forced_cleanup"],
                        "PreviousOwnedProductProcessNotRetired")
                plan = sdk.read_json(evidence / variant / "commands" / (kind + ".product-plan.json"))
                output = Path(plan["output"])
                result = (collect_full_motion(output, command) if kind == "full-motion"
                          else collect_node(output, plan, command))
                result["command_receipt"] = identity(evidence / variant / "commands" / (kind + ".json"))
                result["actual_module_proof"] = command["product_phase"]
                report["cases"][variant][kind] = result
                write(evidence / variant / (kind + "-review.json"), result)
            # Test drivers operate on private copies; original admission bytes must survive.
            sdk.product_runtime_identity(work / "runtimes" / variant, work / "inputs/runtime-before.json", variant)
        report["comparison_collected"] = True
        stock = report["cases"]["stock"]
        patched = report["cases"]["patched"]
        patch_ok = all(value["success"] for value in patched.values())
        baseline_vme = stock["full-motion"]["vme_observed"]
        report["causal_result"] = ("vme-reproduced-stock-only" if baseline_vme and patch_ok
                                  else "vme-persists-with-patch" if patched["full-motion"]["vme_observed"]
                                  else "inconclusive")
        report["success"] = all(value["success"] for variant in report["cases"].values() for value in variant.values())
        report["status"] = "passed" if report["success"] else "failed"
        if not report["success"]:
            report["errors"].append("OriginalProductCaseFailurePreserved")
    except Exception as error:
        report["errors"].append(safe_error(error))
        # Native command receipts remain even if sampling/cleanup fails. Do not
        # start another variant after a missing module/exit/owned-Job proof.
        report["status"] = "failed"
    finally:
        # A command can start and then fail its observer/exit gate. Never report
        # zero execution merely because the call did not return successfully.
        if report["execution_attempted"] and not report["runtime_executed"]:
            report["runtime_executed"] = None
            report["runtime_execution_state"] = "attempted; consult preserved native command receipts"
        report["finished_utc"] = sdk.utc()
        report["font_files_uploaded"] = False
        write(evidence / "comparison.json", report)
        print(json.dumps({"phase": "execute", "status": report["status"],
                          "comparison_collected": report["comparison_collected"],
                          "causal_result": report["causal_result"], "errors": report["errors"]}))
    return 0 if report["success"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("prepare", "execute"))
    args = parser.parse_args()
    repository, helper, work, evidence, context = fixed_context()
    if args.phase == "prepare":
        return prepare(repository, work, evidence, context)
    return execute(repository, work, evidence, context)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "admission-or-evidence-failure", "error": safe_error(error), "runtime_executed": None}))
        raise SystemExit(1)
