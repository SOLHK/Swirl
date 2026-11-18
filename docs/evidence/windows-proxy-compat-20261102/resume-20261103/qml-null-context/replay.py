"""Reproduce the C++ QQmlExpression diagnostic crash through Qt's Python binding.

This is an isolated Linux Qt 6.12 constructor regression. It is not the complete
Swirl application or Windows policy UI acceptance. Run with a PySide6 interpreter.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import PySide6
from PySide6.QtCore import qVersion


CHILD = r'''
from PySide6.QtCore import QUrl, qVersion, QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtQml import QQmlEngine, QQmlComponent, QQmlExpression, qmlContext
app = QGuiApplication([])
engine = QQmlEngine()
component = QQmlComponent(engine)
component.setData(b"""import QtQuick
import QtQuick.Controls
Item {
    width: 300; height: 300
    ScrollView {
        objectName: "form"; anchors.fill: parent
        Item { implicitHeight: 600; width: 300 }
    }
}""", QUrl())
root = component.create()
assert root, component.errors()
form = root.findChild(QObject, "form")
viewport = form.property("contentItem")
print("Qt", qVersion(), "viewport type", type(viewport).__name__,
      "viewportContext", qmlContext(viewport),
      "rootContext", bool(qmlContext(root)), flush=True)
context = CONTEXT
expression = QQmlExpression(context, viewport, "contentY")
print("constructed", flush=True)
expression.setNotifyOnValueChanged(True)
value = expression.evaluate()
print("evaluated", value, "error", expression.hasError(), flush=True)
assert not expression.hasError()
assert value == (-0.0, False)
'''


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    output = Path(__file__).resolve().parent
    library = Path(PySide6.__file__).parent / "Qt/lib/libQt6Qml.so.6"
    result = {
        "scope": "Isolated Linux Qt QQmlExpression constructor; no full-application or Windows acceptance claim",
        "qt_version": qVersion(),
        "pyside_version": PySide6.__version__,
        "python": sys.version,
        "script_sha256": sha256(Path(__file__)),
        "qt_qml_library_sha256": sha256(library),
        "cases": {},
    }
    for label, context in (("old", "qmlContext(viewport)"),
                           ("candidate", "qmlContext(root)")):
        program = CHILD.replace("CONTEXT", context)
        child_path = output / f"{label}.py"
        child_path.write_text(program, encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(child_path)],
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
            capture_output=True, timeout=30, check=False,
        )
        stdout_path = output / f"{label}.stdout.log"
        stderr_path = output / f"{label}.stderr.log"
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        result["cases"][label] = {
            "exit_code": completed.returncode,
            "program_sha256": sha256(child_path),
            "stdout_sha256": sha256(stdout_path),
            "stderr_sha256": sha256(stderr_path),
            "stdout": completed.stdout.decode("utf-8", errors="replace"),
            "stderr": completed.stderr.decode("utf-8", errors="replace"),
        }
    result["reproduced"] = (
        result["cases"]["old"]["exit_code"] == -11
        and result["cases"]["candidate"]["exit_code"] == 0
    )
    (output / "result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0 if result["reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
