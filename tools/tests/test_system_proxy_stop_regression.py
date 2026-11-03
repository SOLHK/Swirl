"""Execute current stop regressions against old and current production C++.

Run only in the disposable Windows CI checkout after its Qt runtime is deployed.
The negative control replaces only EngineController.cpp/.h with exact Git blobs;
the tests, SystemProxySession, Rust library and toolchain stay the same. Restore
the candidate bytes and rebuild before any product test or packaging continues.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


BASELINE = "0a38491d2b87ba9790ebe4e9b797d30680c9e960"
CONTROLLER_FILES = (
    "src/Swirl.Quick/engine/EngineController.cpp",
    "src/Swirl.Quick/engine/EngineController.h",
)
TEST_FILE = "src/Swirl.Quick/tests/PolicyConfigurationTests.cpp"
UNCHANGED_FILES = (
    TEST_FILE,
    "src/Swirl.Quick/engine/SystemProxySession.cpp",
    "src/Swirl.Quick/engine/SystemProxySession.h",
)
CASES = (
    "normalStopKeepsTheCoreAliveUntilOwnedProxyReleaseCompletes",
    "normalStopReleaseFailureAndTimeoutKeepTheOwnedListenerRetryable",
    "releaseCompletionResumesOnlyTheCurrentProxyIntent",
    "acquisitionFailureStopsTheCoreAndRestorationFailureRetainsItsRetry",
    "durablePolicyStopWaitsForProxyRelease",
    "durablePolicyStopTimeoutKeepsTheOwnedListenerAndTransactionRetryable",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_report(path: Path, exit_code: int, negative: bool) -> dict:
    root = ET.parse(path).getroot()
    assert root.tag == "TestCase" and root.get("name") == "PolicyConfigurationTests", "Unexpected QTest suite"
    assert root.findtext("Environment/QtVersion") == "6.12.0", "Expected actual Qt 6.12.0 execution"
    functions = {node.get("name"): node for node in root.findall("TestFunction")}
    expected = set(CASES) | {"initTestCase", "cleanupTestCase"}
    assert set(functions) == expected, "Missing, duplicate or unexpected QTest function"
    assert len(root.findall("TestFunction")) == len(expected), "Duplicate QTest function"
    results = {}
    for name, node in functions.items():
        incidents = node.findall("Incident")
        assert incidents, f"No execution incidents: {name}"
        assert not any(item.get("type") == "skip" for item in node.iter()), f"Skipped case: {name}"
        kinds = [item.get("type") for item in incidents]
        assert all(kind in {"pass", "fail"} for kind in kinds), f"Unexpected incident: {name}"
        results[name] = {"passed": kinds.count("pass"), "failed": kinds.count("fail")}
        if negative and name in CASES:
            assert kinds.count("fail") >= 1, f"Old implementation did not expose the regression: {name}"
        else:
            assert kinds.count("fail") == 0 and kinds.count("pass") >= 1, f"Unexpected test failure: {name}"
    if negative:
        assert 0 < exit_code < 128, f"Negative control crashed or did not fail: {exit_code}"
    else:
        assert exit_code == 0, f"Candidate process failed: {exit_code}"
        assert results[CASES[1]]["passed"] == 2, "Both failure and real-timeout rows must execute"
    return {"exit_code": exit_code, "functions": results, "xml_sha256": digest(path.read_bytes())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This regression requires the real Windows Qt 6.12 build")
    repo = Path(__file__).resolve().parents[2]
    build = args.build_dir.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    executable = build / "Release/SwirlPolicyConfigurationTests.exe"
    summary = {"schema": 1, "baseline_controller_commit": BASELINE,
               "scope": "Exact old controller blobs with current tests and dependencies; isolated backend, not Windows Desktop acceptance",
               "success": False, "candidate_restored": False, "errors": []}
    snapshots = {name: (repo / name).read_bytes() for name in (*CONTROLLER_FILES, *UNCHANGED_FILES)}
    summary["candidate_file_sha256"] = {name: digest(data) for name, data in snapshots.items()}
    process_tree_safe = True

    def run(command: list[str], name: str, timeout: int) -> int:
        nonlocal process_tree_safe
        with (output / f"{name}.stdout.log").open("wb") as stdout, (output / f"{name}.stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=repo, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            try:
                return process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Killing only cmake leaves MSBuild/cl descendants compiling
                # while source is restored. Retire the whole Windows tree and
                # fail the gate; never start a second build after this timeout.
                process_tree_safe = False
                summary["timed_out_command"] = name
                cleanup = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                         stdout=stdout, stderr=stderr, timeout=30, check=False)
                if cleanup.returncode == 0:
                    process.wait(timeout=30)
                    process_tree_safe = True
                raise RuntimeError(f"{name} exceeded its bound; process_tree_retired={process_tree_safe}") from None

    def execute(label: str, negative: bool) -> dict:
        code = run(["cmake", "--build", str(build), "--config", "Release", "--target",
                    "SwirlPolicyConfigurationTests", "--parallel", "4"], f"{label}-build", 900)
        assert code == 0, f"{label} controller build failed: {code}; compilation failure is not an expected test failure"
        xml = output / f"{label}.xml"
        code = run([str(executable), *CASES, "-o", f"{xml},xml", "-o",
                    f"{output / (label + '.txt')},txt"], label, 120)
        return check_report(xml, code, negative)

    try:
        summary["source_sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", *snapshots], cwd=repo, check=True)
        baseline = {name: subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=repo)
                    for name in CONTROLLER_FILES}
        summary["baseline_file_sha256"] = {name: digest(data) for name, data in baseline.items()}
        assert any(baseline[name] != snapshots[name] for name in CONTROLLER_FILES), "Negative control equals candidate"
        try:
            for name, data in baseline.items():
                (repo / name).write_bytes(data)
            summary["negative_control"] = execute("baseline", True)
        except Exception as error:
            summary["errors"].append(f"negative_control: {type(error).__name__}: {error}")
        finally:
            if process_tree_safe:
                for name in CONTROLLER_FILES:
                    (repo / name).write_bytes(snapshots[name])
            summary["candidate_restored"] = all((repo / name).read_bytes() == data for name, data in snapshots.items())
        assert summary["candidate_restored"], "Current production source or tests were not restored exactly"
        assert "timed_out_command" not in summary, "A timed-out build/test cannot proceed to candidate execution"
        summary["candidate"] = execute("candidate", False)
        subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", *snapshots], cwd=repo, check=True)
        summary["success"] = not summary["errors"] and "negative_control" in summary
    except Exception as error:
        summary["errors"].append(f"candidate: {type(error).__name__}: {error}")
    finally:
        (output / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
