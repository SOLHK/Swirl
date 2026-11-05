"""Run the unmodified production QML in Qt Quick Test, with an optional old-code replay.

Only theme/motion presentation dependencies are substituted. ScrollView,
Flickable, focus, geometry and both production QML files are real Qt objects.
This is a geometry regression, not Windows proxy or Codex desktop acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
FORM = "src/Swirl.Quick/qml/components/PolicyFormScroll.qml"
BAR = "src/Swirl.Quick/qml/controls/SwirlScrollBar.qml"
REGRESSION = "test_viewportResizeRevealsBeforeReturningToEventLoop"
QML = r'''import QtQuick
import QtQuick.Controls.Basic
import QtTest
import "../qml/components" as Production

Item {
    id: root
    width: 760
    height: 760
    QtObject { id: motionPolicy; property bool alwaysShowScrollbars: true }
    TextField { id: outside; y: 700; width: 200; height: 32 }
    Production.PolicyFormScroll {
        id: form
        width: 604
        height: 543
        ownerItem: root
        formBody: body
        padding: 0
        Item {
            id: body
            width: form.availableWidth
            implicitHeight: 644
            TextField { id: field; y: 586; width: 300; height: 32 }
        }
    }
    TestCase {
        name: "PolicyFormScroll"
        when: windowShown
        function init() {
            outside.forceActiveFocus()
            form.bottomPadding = 0
            tryCompare(form.viewport, "height", 543)
            form.viewport.contentY = 0
            wait(0)
        }
        function focusLastField() {
            field.forceActiveFocus()
            tryVerify(function() { return field.activeFocus }, 120)
            tryCompare(form.viewport, "contentY", 81, 120)
        }
        function fieldIsContained() {
            const top = field.mapToItem(form.viewport, 0, 0).y
            return top >= 6 && top + field.height <= form.viewport.height - 6
        }
        function test_focusRevealsLastField() {
            focusLastField()
            verify(fieldIsContained())
        }
        function test_viewportResizeKeepsFocusedFieldVisible() {
            focusLastField()
            // Preserve outer height, focus and content extent. Only the real
            // viewport changes, reproducing the missing geometry notification.
            form.bottomPadding = 44
            tryCompare(form.viewport, "height", 499)
            compare(form.height, 543)
            compare(form.contentHeight, 644)
            verify(field.activeFocus)
            tryVerify(fieldIsContained, 120)
            compare(form.viewport.contentY, 125)
        }
        function test_viewportResizeRevealsBeforeReturningToEventLoop() {
            focusLastField()
            // A native layout can finish in the last event processed before a
            // frame or caller deadline. Its already-focused field must fit the
            // new viewport when that synchronous geometry update returns;
            // requiring another event turn can leave the next frame clipped.
            // Do not wait or force a second reveal after changing the viewport.
            form.bottomPadding = 44
            compare(form.viewport.height, 499)
            compare(form.height, 543)
            compare(form.contentHeight, 644)
            verify(field.activeFocus)
            verify(fieldIsContained())
            compare(form.viewport.contentY, 125)
        }
        function test_externalFocusDoesNotScrollTheForm() {
            focusLastField()
            outside.forceActiveFocus()
            tryVerify(function() { return outside.activeFocus }, 120)
            form.bottomPadding = 44
            tryCompare(form.viewport, "height", 499)
            wait(120)
            compare(form.viewport.contentY, 81)
            verify(outside.activeFocus)
        }
        function test_unfocusedManualScrollIsPreserved() {
            verify(outside.activeFocus)
            form.viewport.contentY = 60
            form.bottomPadding = 44
            tryCompare(form.viewport, "height", 499)
            wait(120)
            compare(form.viewport.contentY, 60)
            verify(outside.activeFocus)
        }
    }
}
'''
THEME = '''pragma Singleton
import QtQml
QtObject {
    function dp(value) { return value }
    readonly property string muted: "gray"
}
'''
MOTION = '''pragma Singleton
import QtQml
QtObject {
    readonly property bool reduced: true
    readonly property int releaseDuration: 0
}
'''


def run_case(runner: Path, directory: Path, form: bytes, bar: bytes) -> dict:
    files = {
        "qml/components/PolicyFormScroll.qml": form,
        "qml/controls/SwirlScrollBar.qml": bar,
        "imports/SwirlQuick/qmldir": b"module SwirlQuick\nsingleton Theme 1.0 Theme.qml\nsingleton SwirlMotion 1.0 SwirlMotion.qml\n",
        "imports/SwirlQuick/Theme.qml": THEME.encode(),
        "imports/SwirlQuick/SwirlMotion.qml": MOTION.encode(),
        "tests/tst_policy_form_scroll.qml": QML.encode(),
    }
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    report = directory / "junit.xml"
    command = [str(runner), "-input", str(directory / "tests"), "-import",
               str(directory / "imports"), "-o", str(report) + ",junitxml", "-o", "-,txt"]
    env = os.environ.copy()
    env["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    # Use the host platform plugin; CI explicitly selects native Windows.
    completed = subprocess.run(command, env=env, capture_output=True, text=True,
                               errors="replace", timeout=45, check=False)
    (directory / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (directory / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    print(completed.stdout, end="")
    print(completed.stderr, end="")
    if not report.is_file():
        raise RuntimeError(f"Qt Quick Test did not produce JUnit: {directory}")
    cases = list(ET.parse(report).getroot().iter("testcase"))
    failed = [c.get("name", "") for c in cases if c.find("failure") is not None or c.find("error") is not None]
    skipped = [c.get("name", "") for c in cases if c.find("skipped") is not None]
    names = [c.get("name", "") for c in cases]
    expected = ["test_focusRevealsLastField", "test_viewportResizeKeepsFocusedFieldVisible", REGRESSION,
                "test_externalFocusDoesNotScrollTheForm", "test_unfocusedManualScrollIsPreserved"]
    if any(not any(name == test or name.endswith("::" + test) for name in names) for test in expected):
        raise RuntimeError(f"Required tests did not execute: {names}")
    return {"returncode": completed.returncode, "tests": names, "failed": failed,
            "skipped": skipped, "form_sha256": hashlib.sha256(form).hexdigest(),
            "scrollbar_sha256": hashlib.sha256(bar).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qmltestrunner", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--regression-baseline", help="Git revision containing the old production form")
    args = parser.parse_args()
    runner = args.qmltestrunner.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Never reuse an old report or silently turn a missing Qt executable into PASS.
    work = Path(tempfile.mkdtemp(prefix="policy-form-", dir=output))
    form, bar = (ROOT / FORM).read_bytes(), (ROOT / BAR).read_bytes()
    result = {"scope": "production QML geometry; presentation-only theme doubles; no desktop proxy acceptance",
              "work_directory": str(work), "candidate": run_case(runner, work / "candidate", form, bar)}
    candidate = result["candidate"]
    passed = candidate["returncode"] == 0 and not candidate["failed"] and not candidate["skipped"]
    if args.regression_baseline:
        old = subprocess.run(["git", "show", f"{args.regression_baseline}:{FORM}"], cwd=ROOT,
                             capture_output=True, check=True).stdout
        if old == form:
            raise RuntimeError("Old-code replay must not use the candidate form")
        baseline = run_case(runner, work / "baseline", old, bar)
        result["baseline_revision"] = args.regression_baseline
        result["baseline"] = baseline
        expected_failure = (baseline["returncode"] != 0 and not baseline["skipped"]
                            and len(baseline["failed"]) == 1
                            and (baseline["failed"][0] == REGRESSION
                                 or baseline["failed"][0].endswith("::" + REGRESSION)))
        passed = passed and expected_failure
    result["passed"] = passed
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
