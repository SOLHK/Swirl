"""Check real CMake/Ninja graphs without compiling or executing the UI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


CORE_TESTS = {
    "swirl-node-view-model", "swirl-rust-library-loader", "swirl-rust-qt-integration",
    "swirl-codex-proxy-launcher", "swirl-telemetry-accounting", "swirl-diagnostic-export",
    "swirl-system-proxy-state", "swirl-node-real-chain", "swirl-stream-regression",
    "swirl-qt-network-policy", "swirl-subscription-formats", "swirl-import-subscription",
}
if "SWIRL_SYSTEM_PROXY_TEST" in os.environ:
    CORE_TESTS.add("swirl-system-proxy-recovery")
UI_TESTS = {
    "swirl-appearance-ui", "swirl-node-ui", "swirl-engine-ui", "swirl-overview-input",
    "swirl-all-pages", "swirl-motion", "swirl-hero", "swirl-navigation-ui",
    "swirl-gateway-network", "swirl-capture-network",
}


def checked(command):
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(result.stdout)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--ninja", default="ninja")
    parser.add_argument("cmake_options", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    build = args.build_dir.resolve()
    evidence = build / "profile-graph-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    options = args.cmake_options[1:] if args.cmake_options[:1] == ["--"] else args.cmake_options

    def configure(name, core, ui):
        output = checked([args.cmake, "-S", str(repo / "src/Swirl.Quick"), "-B", str(build),
                          "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                          *options, f"-DSWIRL_BUILD_CORE_TESTS={'ON' if core else 'OFF'}",
                          f"-DSWIRL_BUILD_UI_TESTS={'ON' if ui else 'OFF'}", "-DSWIRL_XRAY_UI_TESTS=OFF"])
        (evidence / f"{name}-configure.log").write_text(output, encoding="utf-8")
        entries = json.loads((build / "compile_commands.json").read_text(encoding="utf-8-sig"))
        app = sorted(entry["command"] for entry in entries
                     if "/CMakeFiles/Swirl.dir/" in ("/" + entry["output"].replace("\\", "/")))
        if not app:
            raise RuntimeError("No Swirl application compile commands found")
        commands = checked([args.ninja, "-C", str(build), "-t", "commands", "Swirl"]).splitlines()
        qml = sorted(command for command in commands if "qmlcachegen" in command.lower())
        if not qml:
            raise RuntimeError("No QML cache generation commands found")
        (evidence / f"{name}-application-commands.json").write_text(json.dumps(app, indent=2), encoding="utf-8")
        (evidence / f"{name}-qmlcache-commands.json").write_text(json.dumps(qml, indent=2), encoding="utf-8")
        # The generated test file is available even before test binaries exist.
        tests_file = build / "CTestTestfile.cmake"
        tests = tests_file.read_text(encoding="utf-8") if tests_file.exists() else ""
        return app, qml, tests

    production = configure("production", False, False)
    core = configure("core-only", True, False)
    if production[:2] != core[:2]:
        raise RuntimeError("Standalone core tests changed production C++ or QML generation commands")
    if any("SWIRL_UI_TESTS" in command for command in core[0]):
        raise RuntimeError("Standalone core tests exposed application UI test entry points")
    for name in CORE_TESTS:
        if name not in core[2]:
            raise RuntimeError(f"Required standalone test missing: {name}")
    if any(name in core[2] for name in UI_TESTS):
        raise RuntimeError("Standalone profile unexpectedly registered application UI tests")
    ui = configure("historical-ui", False, True)
    if not any("SWIRL_UI_TESTS" in command for command in ui[0]):
        raise RuntimeError("Historical UI test profile lost its entry points")
    for name in CORE_TESTS | UI_TESTS:
        if name not in ui[2]:
            raise RuntimeError(f"Historical UI profile lost test: {name}")
    restored = configure("restored-core-only", True, False)
    if restored[:2] != production[:2]:
        raise RuntimeError("Returning to standalone tests changed production commands")
    report = {
        "source_sha": checked(["git", "-C", str(repo), "rev-parse", "HEAD"]).strip(),
        "tracked_source_clean": not bool(checked(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"]).strip()),
        "application_compile_commands": len(core[0]), "qmlcache_generation_commands": len(core[1]),
        "standalone_tests_required": sorted(CORE_TESTS),
        "application_commands_unchanged": True, "qmlcache_commands_unchanged": True,
        "standalone_has_no_application_test_entry_points": True,
        "historical_ui_and_core_tests_preserved": True,
        "compiled_or_executed_application": False,
        "compiler_commands_sha256": hashlib.sha256("\n".join(core[0]).encode()).hexdigest(),
        "qmlcache_commands_sha256": hashlib.sha256("\n".join(core[1]).encode()).hexdigest(),
    }
    (evidence / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
