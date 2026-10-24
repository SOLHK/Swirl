"""Preserve frozen shell sources while checking the explicitly authorized S4 edits.

The S3 whole-UI guard is retained unchanged for historical reproduction. S4
authorizes content/motion/model work, but not window or sidebar geometry.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT_EDITS = {
    "src/Swirl.Quick/app/NodeViewModel.cpp",
    "src/Swirl.Quick/qml/SwirlMotion.qml",
    "src/Swirl.Quick/qml/components/SwirlStatusBadge.qml",
    "src/Swirl.Quick/qml/controls/SwirlActivityIndicator.qml",
    "src/Swirl.Quick/qml/controls/SwirlDataTable.qml",
    "src/Swirl.Quick/qml/controls/SwirlMotionButton.qml",
    "src/Swirl.Quick/qml/controls/SwirlPressMotion.qml",
    "src/Swirl.Quick/qml/controls/SwirlTransitionCoordinator.qml",
}
MAIN_PROXY_ACTION = (
    'SwirlStatusCapsule {id:proxyCapsule;objectName:"proxyCapsule";Layout.preferredWidth:implicitWidth;Layout.preferredHeight:Theme.dp(28);label:window.proxyStatusLabel;tone:engineController.systemProxy.error.length||engineController.routingError.length?"warning":engineController.systemProxy.systemEnabled?"success":"neutral";detail:"打开节点管理";onClicked:AppState.navigate("proxies")}',
    'SwirlSystemProxyCapsule {id:proxyCapsule;objectName:"proxyCapsule";Layout.preferredWidth:implicitWidth;Layout.preferredHeight:Theme.dp(28);controller:engineController}',
)


def inspect(root):
    baseline = json.loads((root / "docs/handoffs/s3-ui-baseline.json").read_text("utf-8"))
    changed, count = [], 0
    for entry in baseline["protected_files"]:
        if entry["path"] in CONTENT_EDITS:
            continue
        count += 1
        path = root / entry["path"]
        content = path.read_bytes().replace(b"\r\n", b"\n") if path.is_file() else b""
        if entry["path"] == "src/Swirl.Quick/qml/Main.qml":
            before, after = (value.encode() for value in MAIN_PROXY_ACTION)
            if content.count(after) != 1 or before in content:
                changed.append(entry["path"])
            content = content.replace(after, before)
        for replacement in entry.get("allowed_replacements", []):
            before, after = (replacement[key].encode() for key in ("before", "after"))
            if content.count(after) != 1 or before in content:
                changed.append(entry["path"])
            content = content.replace(after, before)
        if not path.is_file() or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            changed.append(entry["path"])
    return {"baseline": baseline["source_sha"], "protected_files": count,
            "changed": sorted(set(changed)), "authorized_content_edits": sorted(CONTENT_EDITS),
            "scope": "source boundary only; runtime geometry, input and rendering tests remain required"}


if __name__ == "__main__":
    result = inspect(ROOT)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["changed"]))
