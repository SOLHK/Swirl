"""Extend the historical boundary only for approved V2 content edits."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE3_CONTENT_EDITS = {
    "src/Swirl.Quick/app/NodeViewModel.h",
    "src/Swirl.Quick/qml/controls/SwirlContextMenu.qml",
    # Native regression exposed a deferred Binding parser failure on fonts page.
    "src/Swirl.Quick/qml/controls/SwirlFontBinding.qml",
    "src/Swirl.Quick/qml/pages/PolicyGroupsPage.qml",
}
STAGE4_CONTENT_EDITS = {
    # Additive transaction dismissal guards; existing callers retain defaults.
    "src/Swirl.Quick/qml/controls/SwirlDialog.qml",
    # Actual, sanitized Rust route observations in the existing detail view.
    "src/Swirl.Quick/qml/pages/ConnectionsPage.qml",
    # Typed V2 targets and matching durable-transaction receipts.
    "src/Swirl.Quick/qml/pages/RulesPage.qml",
}


def inspect(root):
    spec = importlib.util.spec_from_file_location(
        "s4_ui_boundary", root / "tools/Verify-S4UiBoundary.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    historical = module.inspect(root)
    return {
        "stage": 4,
        "historical": historical,
        "authorized_v2_content_edits": sorted(STAGE3_CONTENT_EDITS | STAGE4_CONTENT_EDITS),
        "unexpected_changes": sorted(set(historical["changed"]) - STAGE3_CONTENT_EDITS - STAGE4_CONTENT_EDITS),
        "scope": "source boundary only; native geometry and interaction checks remain required",
    }


if __name__ == "__main__":
    result = inspect(ROOT)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["unexpected_changes"]))
