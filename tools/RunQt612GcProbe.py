#!/usr/bin/env python3
"""Run only the freshly built, public Qt GC fixtures on an opted-in CI runner."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from PrivateSubscriptionProcess import OwnedProcess


CASE_SECONDS = 8.0  # Reuse OwnedProcess's existing, stricter maximum unchanged.
STREAM_LIMIT = 8 * 1024 * 1024
REPRO = Path("tools/repros/qt612-popup-gc")
SOURCE_FILES = [str(REPRO / name) for name in (
    "CMakeLists.txt", "main.cpp", "sweep.cpp", "Main.qml", "ProbeDialog.qml", "OwnedHelper.qml"
)] + ["tools/RunQt612GcProbe.py", "tools/PrivateSubscriptionProcess.py",
      "tools/PrivateSubscriptionBudget.py", "tools/Install-QtSdk.py",
      "tools/requirements-qt-sdk.txt", ".github/workflows/diagnose-qt612-gc.yml"]


def utc():
    return datetime.now(timezone.utc).isoformat()


def identity(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def command(arguments, root):
    return subprocess.run(arguments, cwd=root, check=True, capture_output=True,
                          text=True, timeout=10).stdout.strip()


def interpret(name, text):
    """Require actual completion/coverage, never turn a known defect into a pass."""
    lines = re.sub(r"^\[(?:debug|info|warning|critical|fatal)\] ", "", text,
                   flags=re.MULTILINE)
    warnings = re.findall(r"^\[(?:warning|critical|fatal)\].*$", text, re.MULTILINE)
    result = {"warning_lines": warnings, "errors": [], "conclusive": False}
    if warnings:
        result["errors"].append("QtWarningOrMoreSevereMessage")
    if name == "sweep-slots":
        matches = re.findall(r"^SWEEP_SLOTS_RESULT qt (\S+) sameBitmapWordAllocations (\d+) "
                             r"freeRunsInsideLiveObjects (\d+)\s*$", lines, re.MULTILINE)
        if len(matches) != 1:
            result["errors"].append("MissingOrAmbiguousSweepCompletion")
            return result
        version, allocations, free_runs = matches[0]
        result.update(qt_version=version, same_bitmap_word_allocations=int(allocations),
                      free_runs_inside_live_objects=int(free_runs))
        result["conclusive"] = int(allocations) > 0
        if version != "6.12.0" or not result["conclusive"]:
            result["errors"].append("WrongQtVersionOrInconclusiveSweep")
        if int(free_runs) != 0:
            result["errors"].append("ObservedLiveObjectFreeListInvariantViolation")
        return result
    modes = re.findall(r"^FIXTURE_GC_MODE incremental (true|false) actualTimeLimitUs (\d+)\s*$",
                       lines, re.MULTILINE)
    completions = re.findall(r"^FIXTURE_RESULT exit (-?\d+) warnings (\d+) collections (\d+) "
                             r"completedHelpers (\d+)\s*$", lines, re.MULTILINE)
    coverage = re.findall(r"^FIXTURE_INCREMENTAL_COVERAGE requested (true|false) pendingReturns (\d+) "
                          r"engineMetaCallObservations (\d+) pendingEngineMetaCallObservations (\d+) "
                          r'yieldObserved (true|false) status "?([a-z-]+)"?\s*$', lines, re.MULTILINE)
    if len(modes) != 1 or len(completions) != 1 or len(coverage) != 1:
        result["errors"].append("MissingOrAmbiguousPopupCompletion")
        return result
    mode, time_limit = modes[0]
    exit_code, warning_count, collections, helpers = map(int, completions[0])
    requested, pending, events, pending_events, yielded, status = coverage[0]
    incremental = name == "popup-incremental"
    result.update(incremental=mode == "true", actual_time_limit_us=int(time_limit),
                  fixture_exit=exit_code, qml_warning_count=warning_count, collections=collections,
                  completed_helpers=helpers, pending_returns=int(pending),
                  engine_meta_call_observations=int(events), pending_engine_meta_call_observations=int(pending_events),
                  yield_observed=yielded == "true", coverage_status=status)
    # Main.qml completes eight rounds of twelve dialogs, each with three helpers.
    result["conclusive"] = (exit_code == 0 and collections > 0 and helpers == 288
                            and (mode == "true") == incremental and (requested == "true") == incremental)
    if incremental:
        # GCStateMachine::timeLimit is stored and reported in microseconds.
        result["conclusive"] &= (int(time_limit) == 1000 and int(pending) > 0 and int(pending_events) > 0
                                  and yielded == "true" and status == "observed")
    else:
        result["conclusive"] &= status == "not-requested"
    if warning_count:
        result["errors"].append("QmlWarningsObserved")
    if not result["conclusive"]:
        result["errors"].append("PopupCompletionOrIncrementalCoverageInconclusive")
    return result


def run_case(name, arguments, output, runtime, source_sha, qt_identity):
    case = output / name
    case.mkdir()
    for directory in ("work", "temp", "appdata", "localappdata"):
        (case / directory).mkdir()
    env = dict(os.environ)
    for key in list(env):
        if key.upper().startswith(("QT_", "QML_", "QSG_", "QV4_")):
            del env[key]
    env.update(PATH=str(runtime) + os.pathsep + env.get("PATH", ""),
               QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
               QT_QPA_FONTDIR=str(runtime / "lib/fonts"),
               QT_PLUGIN_PATH=str(runtime), QML_IMPORT_PATH=str(runtime / "qml"),
               QML2_IMPORT_PATH=str(runtime / "qml"), QML_DISABLE_DISK_CACHE="1",
               QT_MESSAGE_PATTERN="[%{type}] %{message}",
               QT_LOGGING_RULES="*.warning=true\n*.critical=true",
               TEMP=str(case / "temp"), TMP=str(case / "temp"),
               APPDATA=str(case / "appdata"), LOCALAPPDATA=str(case / "localappdata"))
    record = {"name": name, "source_sha": source_sha, "arguments": arguments,
              "started_utc": utc(), "deadline_seconds": CASE_SECONDS,
              "executable_before": identity(arguments[0]), "qt_qml_dll_before": qt_identity,
              "errors": [], "exit_proof": None, "timed_out": False,
              "scope": "Public fixture; Windows Qt QML GC with offscreen/software, not native GPU or Swirl acceptance."}
    runtime_inputs = [runtime / "platforms/qoffscreen.dll", *sorted((runtime / "lib/fonts").glob("*.ttf"))]
    record["offscreen_font_directory"] = str(runtime / "lib/fonts")
    record["offscreen_inputs_before"] = [identity(path) for path in runtime_inputs]
    child = None
    readers = []
    stream_errors = []
    started = time.monotonic()

    def capture(stream, path):
        count = 0
        try:
            with path.open("xb") as destination:
                while chunk := stream.read(16384):
                    remaining = max(0, STREAM_LIMIT - count)
                    destination.write(chunk[:remaining])
                    count += len(chunk)
            if count > STREAM_LIMIT:
                stream_errors.append(path.name + ":OutputLimitExceeded")
        except Exception as error:
            stream_errors.append(path.name + ":" + type(error).__name__)

    try:
        previous_cwd = Path.cwd()
        try:
            os.chdir(case / "work")
            child = OwnedProcess(arguments, deadline=started + CASE_SECONDS, environment=env)
        finally:
            os.chdir(previous_cwd)
        record["pid"] = child.pid
        child.stdin.close()
        for stream, filename in ((child.stdout, "stdout.log"), (child.stderr, "stderr.log")):
            thread = threading.Thread(target=capture, args=(stream, case / filename), daemon=True)
            thread.start()
            readers.append(thread)
        record["exit_proof"] = child.wait(timeout=CASE_SECONDS + 2).record()
        record["exit_observed_elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    except Exception as error:
        record["errors"].append("Run:" + type(error).__name__ + ":" + str(error))
    finally:
        if child is not None:
            try:
                proof = child.terminate_and_wait(timeout=2).record()
                if record["exit_proof"] is None:
                    record["exit_proof"] = proof
                    record["exit_observed_elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
            except Exception as error:
                record["errors"].append("ExitUnconfirmed:" + type(error).__name__)
            record["timed_out"] = child.timed_out
            record["stop_error"] = child.stop_error
            for thread in readers:
                thread.join(timeout=2)
            try:
                child.close()
            except Exception as error:
                record["errors"].append("Close:" + type(error).__name__)
        if any(thread.is_alive() for thread in readers):
            record["errors"].append("OutputCaptureIncomplete")
        record["errors"].extend(stream_errors)
    record["finished_utc"] = utc()
    record["total_elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    record["executable_after"] = identity(arguments[0])
    record["qt_qml_dll_after"] = identity(runtime / "Qt6Qml.dll")
    record["offscreen_inputs_after"] = [identity(path) for path in runtime_inputs]
    record["outputs"] = {p.name: identity(p) for p in (case / "stdout.log", case / "stderr.log") if p.is_file()}
    text = "\n".join((case / name).read_bytes().decode("utf-8", errors="replace")
                     for name in ("stdout.log", "stderr.log") if (case / name).is_file())
    record["interpretation"] = interpret(name, text)
    record["errors"].extend(record["interpretation"]["errors"])
    if record["timed_out"] or record.get("stop_error"):
        record["errors"].append("DeadlineOrStopFailure")
    if not record["exit_proof"] or record["exit_proof"]["exitCode"] != 0:
        record["errors"].append("MissingOrNonzeroActualExit")
    if record["executable_before"] != record["executable_after"] or qt_identity != record["qt_qml_dll_after"]:
        record["errors"].append("RuntimeChangedDuringFixture")
    if record["offscreen_inputs_before"] != record["offscreen_inputs_after"]:
        record["errors"].append("OffscreenPluginOrFontChangedDuringFixture")
    record["success"] = not record["errors"] and record["interpretation"]["conclusive"]
    write_json(case / "receipt.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-directory", required=True, type=Path)
    parser.add_argument("--qt-root", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-pr-head-sha", required=True)
    args = parser.parse_args()
    output = args.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": 1, "started_utc": utc(), "success": False, "cases": [], "errors": [],
              "scope": "Three freshly built Qt 6.12 GC fixtures, once each; no Swirl launch or VME-root-cause claim.",
              "executing_workflow_sha": args.expected_source_sha, "pr_head_sha": args.expected_pr_head_sha}
    try:
        if (os.name != "nt" or struct.calcsize("P") != 8 or os.environ.get("GITHUB_ACTIONS") != "true"
                or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
                or os.environ.get("GITHUB_REPOSITORY") != "SOLHK/Swirl"
                or os.environ.get("SWIRL_QT612_GC_PROBE") != "1"):
            raise RuntimeError("RequiresExplicitHostedWindowsX64FixtureAdmission")
        root = Path(__file__).resolve().parents[1]
        source = command(["git", "rev-parse", "HEAD"], root)
        parents = command(["git", "show", "-s", "--format=%P", "HEAD"], root).split()
        if (not re.fullmatch(r"[0-9a-f]{40}", args.expected_source_sha)
                or source != args.expected_source_sha or args.expected_pr_head_sha not in parents):
            raise RuntimeError("CheckoutOrPrMergeIdentityMismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--", *SOURCE_FILES], root)
        report.update(source_sha=source, source_parents=parents,
                      sources_before={p: identity(root / p) for p in SOURCE_FILES},
                      run_id=os.environ.get("GITHUB_RUN_ID"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"))
        runtime = args.runtime_directory.resolve(strict=True)
        qt = identity(runtime / "Qt6Qml.dll")
        sdk_qt = identity(args.qt_root / "bin/Qt6Qml.dll")
        if qt["sha256"] != sdk_qt["sha256"] or qt["bytes"] != sdk_qt["bytes"]:
            raise RuntimeError("DeployedQtQmlDoesNotMatchVerifiedSdk")
        report.update(qt_qml_deployed=qt, qt_qml_verified_sdk=sdk_qt,
                      runtime_resolution="Fresh app-local DLLs deployed by the verified SDK; no loaded-module sampling.")
        offscreen = identity(runtime / "platforms/qoffscreen.dll")
        sdk_offscreen = identity(args.qt_root / "plugins/platforms/qoffscreen.dll")
        if offscreen["sha256"] != sdk_offscreen["sha256"] or offscreen["bytes"] != sdk_offscreen["bytes"]:
            raise RuntimeError("DeployedOffscreenPluginDoesNotMatchVerifiedSdk")
        fonts = sorted((runtime / "lib/fonts").glob("*.ttf"))
        if len(fonts) != 1 or fonts[0].name.lower() not in {"segoeui.ttf", "arial.ttf"}:
            raise RuntimeError("TemporaryOffscreenFontMissingOrUnexpected")
        font = identity(fonts[0])
        source_font = identity(Path(os.environ["WINDIR"]) / "Fonts" / fonts[0].name)
        if font["sha256"] != source_font["sha256"] or font["bytes"] != source_font["bytes"]:
            raise RuntimeError("TemporaryOffscreenFontDoesNotMatchRunnerSource")
        report.update(qoffscreen_deployed=offscreen, qoffscreen_verified_sdk=sdk_offscreen,
                      temporary_font_deployed=font, temporary_font_source=source_font,
                      offscreen_font_directory=str(runtime / "lib/fonts"), font_file_uploaded=False)
        cases = [("popup-normal", "PopupGcFixture.exe", [str(root / REPRO / "Main.qml")]),
                 ("popup-incremental", "PopupGcFixture.exe", [str(root / REPRO / "Main.qml"), "--incremental"]),
                 ("sweep-slots", "SweepSlotsProbe.exe", [])]
        for name, executable, arguments in cases:
            try:
                record = run_case(name, [str(runtime / executable), *arguments], output, runtime, source, qt)
            except Exception as error:
                record = {"name": name, "success": False, "errors": [type(error).__name__ + ":" + str(error)]}
                write_json(output / (name + "-runner-error.json"), record)
            report["cases"].append(record)
        report["sources_after"] = {p: identity(root / p) for p in SOURCE_FILES}
        if report["sources_before"] != report["sources_after"]:
            report["errors"].append("FixtureSourceChangedDuringExecution")
        report["success"] = len(report["cases"]) == 3 and all(c["success"] for c in report["cases"]) and not report["errors"]
    except Exception as error:
        report["errors"].append(type(error).__name__ + ":" + str(error))
    report["finished_utc"] = utc()
    write_json(output / "aggregate.json", report)
    print(json.dumps({"success": report["success"], "cases": [{"name": c["name"], "success": c["success"]}
                                                            for c in report["cases"]], "errors": report["errors"]}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
