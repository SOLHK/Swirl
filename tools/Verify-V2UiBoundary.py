"""Extend the historical boundary only for approved V2 content edits."""
import importlib.util
import json
import re
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
STAGE6_SHELL_EDITS = {
    # Explicit user authorization: neutral materials and shared 14dp contours.
    "src/Swirl.Quick/qml/Theme.qml",
    "src/Swirl.Quick/qml/Main.qml",
    "src/Swirl.Quick/qml/components/SwirlGlassMaterial.qml",
    "src/Swirl.Quick/qml/components/SwirlShellOutline.qml",
    "src/Swirl.Quick/qml/components/SwirlSidebar.qml",
    # Expose the existing vector checkmark to native policy/mode selectors.
    "src/Swirl.Quick/qml/components/SwirlIcon.qml",
    "src/Swirl.Quick/app/WindowsBackdrop.cpp",
    "src/Swirl.Quick/app/WindowsBackdrop.h",
    # Replace the activity fact in place, keeping the existing four columns.
    "src/Swirl.Quick/qml/pages/ActivityPage.qml",
    # Stage-6 continuation: shared neutral controls, preserving public APIs and sizes.
    "src/Swirl.Quick/qml/controls/SwirlButton.qml",
    "src/Swirl.Quick/qml/controls/SwirlIconButton.qml",
    "src/Swirl.Quick/qml/controls/SwirlSearchField.qml",
    "src/Swirl.Quick/qml/controls/SwirlSegmentedControl.qml",
    "src/Swirl.Quick/qml/controls/SwirlToolTip.qml",
}


def shell_invariants(root):
    theme = (root / "src/Swirl.Quick/qml/Theme.qml").read_text("utf-8")
    main = (root / "src/Swirl.Quick/qml/Main.qml").read_text("utf-8")
    sidebar = (root / "src/Swirl.Quick/qml/components/SwirlSidebar.qml").read_text("utf-8")
    invariants = {
        "shared_14dp": bool(re.search(r"WindowCornerRadius\s*=\s*14,\s*SidebarCornerRadius\s*=\s*14", theme)),
        "default_window": "width:Theme.windowDefaultWidth; height:Theme.windowDefaultHeight" in main,
        "minimum_window": "minimumWidth:Theme.windowMinimumWidth; minimumHeight:Theme.windowMinimumHeight" in main,
        "sidebar_structure": "model:AppState.navigationGroups" in sidebar and 'pageId:"featurehub"' in sidebar and 'pageId:"external"' in sidebar,
        "sidebar_inset": "x:Theme.dp(8);y:Theme.dp(8)" in sidebar and "width:sidebar.width-Theme.dp(16);height:sidebar.height-Theme.dp(16)" in sidebar,
        "sidebar_selection": "x:Theme.dp(10);width:sidebar.width-Theme.dp(20);height:Theme.sidebarRowHeight" in sidebar,
        "shared_native_radius": 'm_window->property("swirlWindowRadius")' in (root / "src/Swirl.Quick/app/WindowsBackdrop.cpp").read_text("utf-8"),
        "shared_render_radius": "WindowEdge {anchors.fill:parent;z:10000;radius:window.shellRadius}" in main,
    }
    for key, value in {"windowDefaultWidth": 914, "windowDefaultHeight": 672,
                       "windowMinimumWidth": 760, "windowMinimumHeight": 672,
                       "sidebarWidth": 168, "sidebarRowHeight": 40}.items():
        invariants[key] = bool(re.search(r"readonly property real " + key + r":\s*dp\(" + str(value) + r"\)", theme))
    return invariants


def inspect(root):
    spec = importlib.util.spec_from_file_location(
        "s4_ui_boundary", root / "tools/Verify-S4UiBoundary.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    historical = module.inspect(root)
    return {
        "stage": 6,
        "historical": historical,
        "authorized_v2_content_edits": sorted(STAGE3_CONTENT_EDITS | STAGE4_CONTENT_EDITS | STAGE6_SHELL_EDITS),
        "unexpected_changes": sorted(set(historical["changed"]) - STAGE3_CONTENT_EDITS - STAGE4_CONTENT_EDITS - STAGE6_SHELL_EDITS),
        "shell_invariants": shell_invariants(root),
        "scope": "source boundary only; native geometry and interaction checks remain required",
    }


if __name__ == "__main__":
    result = inspect(ROOT)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["unexpected_changes"]) or not all(result["shell_invariants"].values()))
