#!/usr/bin/env python3
"""Run the unchanged three Qt 6.12 fixtures once per isolated stock/patched runtime."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys


_spec = importlib.util.spec_from_file_location(
    "qt612_diagnostic_sdk", Path(__file__).with_name("Build-Qt612QmlDiagnosticSdk.py"))
sdk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sdk)

EXECUTABLES = ("PopupGcFixture.exe", "SweepSlotsProbe.exe")
CASES = ("popup-normal", "popup-incremental", "sweep-slots")
EXTERNAL_RUNTIME = re.compile(
    r"(?:vc_redist\.x64\.exe|(?:vcruntime140(?:_1|_threads)?|msvcp140(?:_[12]|_atomic_wait|_codecvt_ids)?"
    r"|concrt140|ucrtbase|api-ms-win-crt-[a-z0-9-]+|d3dcompiler_47|dxcompiler|dxil)\.dll)", re.IGNORECASE)


def deployment_files(value):
    """Qt v6.12.0 JsonOutput uses source-file / target-directory pairs (utils.h:74-106)."""
    sdk.require(isinstance(value, dict) and isinstance(value.get("files"), list),
                "UnknownWindeployqtJsonSchema")
    files = value["files"]
    sdk.require(files and len(files) <= 10000, "UnexpectedDeploymentFileCount")
    for item in files:
        sdk.require(isinstance(item, dict) and isinstance(item.get("source"), str)
                    and isinstance(item.get("target"), str), "UnrecognizedDeploymentMapping")
    return files


def verify_deployment_mapping(entries, kit, runtime, external_roots):
    result = {}
    for item in entries:
        source = sdk.plain_path(Path(item["source"]))
        target_path = Path(item["target"])
        target_directory = sdk.plain_path(target_path if target_path.is_absolute()
                                          else runtime / target_path)
        sdk.require(target_directory.is_dir()
                    and (target_directory == runtime or target_directory.is_relative_to(runtime)),
                    "DeploymentTargetDirectoryEscapesRuntime")
        target = sdk.plain_path(target_directory / source.name, root=runtime)
        sdk.require(source.is_file() and target.is_file(), "DeploymentMappingDoesNotNameFiles")
        relative = target.relative_to(runtime).as_posix()
        identity = sdk.file_identity(source)
        sdk.require(identity == sdk.file_identity(target), "DeploymentChangedSourceBytes:" + relative)
        if source.is_relative_to(kit):
            origin = "selected-qt-kit"
        else:
            sdk.require(EXTERNAL_RUNTIME.fullmatch(source.name)
                        and source.name.casefold() == target.name.casefold()
                        and any(source.is_relative_to(root) for root in external_roots),
                        "DeploymentSourceOutsideSelectedKit:" + relative)
            origin = "recorded-microsoft-runtime"
        record = {"source": str(source), "target": str(target), "origin": origin, **identity}
        sdk.require(relative not in result or result[relative] == record,
                    "ConflictingDeploymentMapping:" + relative)
        result[relative] = record
    sdk.require("Qt6Qml.dll" in result and "platforms/qoffscreen.dll" in result,
                "RequiredRuntimeMappingMissing")
    sdk.require(Path(result["Qt6Qml.dll"]["source"]).resolve() == (kit / "bin/Qt6Qml.dll").resolve()
                and Path(result["platforms/qoffscreen.dll"]["source"]).resolve()
                    == (kit / "plugins/platforms/qoffscreen.dll").resolve(), "SelectedQtModuleMappingMismatch")
    return result


def validate_case_retirement(aggregate, source_sha, head_sha):
    sdk.require(aggregate.get("source_sha") == source_sha
                and aggregate.get("pr_head_sha") == head_sha, "FixtureAggregateIdentityMismatch")
    cases = aggregate.get("cases", [])
    sdk.require([x.get("name") for x in cases] == list(CASES), "FixtureCaseSetIncomplete")
    for case in cases:
        proof = case.get("exit_proof") or {}
        sdk.require(proof.get("processSignaled") is True and proof.get("ownedProcessSetEmpty") is True
                    and proof.get("backend") == "windows-single-process-job"
                    and isinstance(proof.get("exitCode"), int)
                    and proof.get("pid") == case.get("pid"), "FixtureRetirementUnconfirmed:" + case["name"])
    return {case["name"]: {"success": case["success"], "errors": case["errors"],
                           "interpretation": case["interpretation"], "exit_proof": case["exit_proof"]}
            for case in cases}


def comparison_status(variants):
    # Baseline failures remain failures. Collection completeness is a separate field.
    complete = set(variants) == {"stock", "patched"} and all(
        value.get("collected") is True for value in variants.values())
    success = complete and all(value.get("runner_exit_code") == 0
                               and value.get("fixture_success") is True for value in variants.values())
    return {"comparison_collected": complete, "success": success}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-receipt", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--evidence-directory", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-pr-head-sha", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    report = {"schema": 1, "kind": "qt612-isolated-runtime-comparison",
              "success": False, "comparison_collected": False, "variants": {},
              "started_utc": sdk.utc(), "errors": [], "stage": "admission",
              "source_sha": args.expected_source_sha, "pr_head_sha": args.expected_pr_head_sha,
              "real_provider_requests": 0, "actual_process_module_sampling": False,
              "scope": "The existing normal, incremental and sweep fixtures, once per variant, "
                       "using identical fixture EXEs/source. No Swirl, native GPU, live node or VME fix claim."}
    evidence = None
    try:
        inputs = sdk.admit(repo, args.expected_source_sha, args.expected_pr_head_sha)
        evidence = sdk.fresh_directory(args.evidence_directory.absolute(), root=repo)
        work = sdk.fresh_directory(args.work_root.absolute(), root=Path(os.environ["RUNNER_TEMP"]).absolute())
        receipt_path = sdk.plain_path(args.sdk_receipt.absolute(), root=repo)
        receipt = sdk.read_json(receipt_path)
        sdk.require(receipt.get("success") is True and receipt.get("stage") == "complete"
                    and receipt.get("source_sha") == args.expected_source_sha
                    and receipt.get("pr_head_sha") == args.expected_pr_head_sha,
                    "DerivedSdkReceiptNotAdmitted")
        sdk.require(receipt.get("source_inputs") == inputs, "BuilderAndComparisonSourceDiffer")
        stock = sdk.plain_path(Path(receipt["stock_root"]), root=Path(os.environ["RUNNER_TEMP"]).absolute())
        derived = sdk.plain_path(Path(receipt["derived_root"]), root=Path(os.environ["RUNNER_TEMP"]).absolute())
        sdk.require(not stock.is_relative_to(derived) and not derived.is_relative_to(stock)
                    and stock != derived, "DiagnosticSdkRootsOverlap")
        expected = {}
        for flavor, directory, filename, identity in (
                ("stock", stock, "stock-files-before.json", receipt["stock_content_id"]),
                ("patched", derived, "derived-files.json", receipt["derived_content_id"])):
            expected[flavor] = sdk.read_json(receipt_path.parent / filename)
            sdk.require(sdk.canonical_digest(expected[flavor]) == identity, "SdkManifestIdentityMismatch")
            sdk.assert_same_tree(expected[flavor], sdk.inventory(directory))
        tools = sdk.tool_paths()
        for name, path in tools.items():
            sdk.require({"path": path, **sdk.file_identity(Path(path))} == receipt["tools"].get(name),
                        "ComparisonToolchainDiffersFromSdkBuild:" + name)
        sdk.require(sdk.canonical_digest(sdk.native_toolchain_files(tools))
                    == receipt["native_toolchain_content_id"], "ComparisonNativeToolchainChanged")
        report.update(source_inputs=inputs, sdk_receipt=sdk.file_identity(receipt_path),
                      derivation_id=receipt["derivation_id"], stock_content_id=receipt["stock_content_id"],
                      patched_content_id=receipt["derived_content_id"])
        commands = evidence / "commands"
        def run(name, arguments, cwd=work, seconds=120, env=None, accepted=(0,)):
            return sdk.run_logged(arguments, cwd, commands, name, seconds, env=env, accepted=accepted)
        report["stage"] = "build-identical-fixtures"
        build = sdk.fresh_directory(work / "fixtures", root=work)
        env = sdk.tool_environment()
        env.update(PATH=str(stock / "bin") + os.pathsep + env["PATH"],
                   CMAKE_PREFIX_PATH=str(stock), QT_ROOT_DIR=str(stock))
        repro = repo / "tools/repros/qt612-popup-gc"
        run("01-configure-fixtures", [tools["cmake.exe"], "-S", repro, "-B", build, "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + str(stock),
            "-DCMAKE_CXX_COMPILER=" + tools["cl.exe"], "-DCMAKE_MAKE_PROGRAM=" + tools["ninja.exe"],
            "-DCMAKE_LINKER=" + tools["link.exe"], "-DCMAKE_AR=" + tools["lib.exe"],
            "-DCMAKE_RC_COMPILER=" + tools["rc.exe"], "-DCMAKE_MT=" + tools["mt.exe"],
            "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL"], seconds=120, env=env)
        cache = sdk.cache_values((build / "CMakeCache.txt").read_text(encoding="utf-8"))
        sdk.require(cache.get("CMAKE_BUILD_TYPE") == "Release" and cache.get("CMAKE_GENERATOR") == "Ninja"
                    and cache.get("CMAKE_MSVC_RUNTIME_LIBRARY") == "MultiThreadedDLL",
                    "FixtureBuildConfigurationMismatch")
        for key, value in cache.items():
            if re.fullmatch(r"Qt6.*_DIR", key) and not value.endswith("-NOTFOUND"):
                sdk.plain_path(Path(value), root=stock)
        compiler_files = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
        sdk.require(len(compiler_files) == 1, "FixtureCompilerMetadataMissing")
        compiler = sdk.compiler_values(compiler_files[0].read_text(encoding="utf-8"))
        sdk.require(compiler == receipt["configuration"]["compiler"], "FixtureCompilerChanged")
        shutil.copyfile(build / "CMakeCache.txt", evidence / "fixture-CMakeCache.txt")
        shutil.copyfile(compiler_files[0], evidence / "fixture-CMakeCXXCompiler.cmake")
        run("02-build-fixtures", [tools["cmake.exe"], "--build", build, "--target",
                                 "PopupGcFixture", "SweepSlotsProbe", "--parallel", "2"], seconds=300, env=env)
        executables = {name: sdk.file_identity(build / name) for name in EXECUTABLES}
        report["fixture_executables"] = executables
        binaries = sdk.fresh_directory(evidence / "fixture-binaries", root=evidence)
        for name in EXECUTABLES:
            shutil.copyfile(build / name, binaries / name)
            sdk.require(sdk.file_identity(binaries / name) == executables[name], "PreservedFixtureChanged")
        external_roots = [sdk.plain_path(Path(os.environ[name]))
                          for name in ("VSINSTALLDIR", "WINDOWSSDKDIR") if os.environ.get(name)]
        external_roots.append(sdk.plain_path(Path(os.environ["WINDIR"]) / "System32"))
        runtime_data = {}
        report["stage"] = "deploy-complete-runtimes"
        for flavor, kit in (("stock", stock), ("patched", derived)):
            runtime = sdk.fresh_directory(work / ("runtime-" + flavor), root=work)
            for name in EXECUTABLES:
                shutil.copyfile(build / name, runtime / name)
                sdk.require(sdk.file_identity(runtime / name) == executables[name], "FixtureCopyChanged")
            deploy_env = sdk.tool_environment()
            deploy_env.update(PATH=str(kit / "bin") + os.pathsep + deploy_env["PATH"],
                              CMAKE_PREFIX_PATH=str(kit), QT_ROOT_DIR=str(kit))
            mappings = []
            for index, name in enumerate(EXECUTABLES):
                command_name = "03-" + flavor + "-deploy-" + str(index)
                run(command_name, [kit / "bin/windeployqt.exe", "--qtpaths", kit / "bin/qtpaths.exe",
                    "--release", "--compiler-runtime", "--no-translations", "--include-plugins", "qoffscreen",
                    "--qmldir", repro, "--json", runtime / name], seconds=120, env=deploy_env)
                mappings.extend(deployment_files(sdk.read_json(commands / (command_name + ".stdout.log"))))
            mapping = verify_deployment_mapping(mappings, kit, runtime, external_roots)
            deployed = sdk.inventory(runtime)
            sdk.require(set(deployed) == set(mapping) | set(EXECUTABLES),
                        "DeploymentMappingDoesNotCoverEntireRuntime")
            qt_conf = runtime / "qt.conf"
            sdk.require(not qt_conf.exists(), "UnexpectedPreexistingQtConf")
            qt_conf.write_text("[Paths]\nPrefix=.\nPlugins=.\nQmlImports=qml\n", encoding="ascii", newline="\n")
            font_source = next((Path(os.environ["WINDIR"]) / "Fonts" / name
                                for name in ("segoeui.ttf", "arial.ttf")
                                if (Path(os.environ["WINDIR"]) / "Fonts" / name).is_file()), None)
            sdk.require(font_source is not None, "TemporaryOffscreenFontMissing")
            font_dir = sdk.fresh_directory(runtime / "lib/fonts", root=runtime)
            font_target = font_dir / font_source.name
            shutil.copyfile(font_source, font_target)
            sdk.require(sdk.file_identity(font_target) == sdk.file_identity(font_source),
                        "TemporaryFontCopyChanged")
            before = sdk.inventory(runtime)
            sdk.write_json(evidence / (flavor + "-deployment-mapping.json"), mapping)
            sdk.write_json(evidence / (flavor + "-runtime-before.json"), before)
            sdk.write_json(evidence / (flavor + "-runtime-prerequisites.json"), {
                "temporary_font_source": {"path": str(font_source), **sdk.file_identity(font_source)},
                "temporary_font_copy": {"path": str(font_target), **sdk.file_identity(font_target)},
                "font_file_uploaded": False,
                "qtpaths": {"path": str(kit / "bin/qtpaths.exe"), **sdk.file_identity(kit / "bin/qtpaths.exe")},
                "windeployqt": {"path": str(kit / "bin/windeployqt.exe"),
                                **sdk.file_identity(kit / "bin/windeployqt.exe")}})
            runtime_data[flavor] = {"runtime": runtime, "kit": kit, "before": before}
        delta = sdk.compare_tree(runtime_data["stock"]["before"], runtime_data["patched"]["before"])
        sdk.write_json(evidence / "runtime-delta.json", delta)
        sdk.require(delta == {"added": [], "removed": [], "changed": ["Qt6Qml.dll"]},
                    "RuntimeComparisonHasAdditionalDifferences")
        report["runtime_delta"] = delta
        report["stage"] = "run-existing-fixtures"
        for flavor in ("stock", "patched"):
            value = runtime_data[flavor]
            sdk.assert_same_tree(value["before"], sdk.inventory(value["runtime"]))
            sdk.assert_same_tree(expected[flavor], sdk.inventory(value["kit"]))
            case_directory = evidence / flavor
            sdk.require(not case_directory.exists(), "FixtureCasesMustBeFresh")
            runner_env = sdk.tool_environment()
            runner_env.update(SWIRL_QT612_GC_PROBE="1")
            command = run("04-" + flavor + "-fixtures",
                [tools["python.exe"], repo / "tools/RunQt612GcProbe.py",
                 "--runtime-directory", value["runtime"], "--qt-root", value["kit"],
                 "--output-directory", case_directory, "--expected-source-sha", args.expected_source_sha,
                 "--expected-pr-head-sha", args.expected_pr_head_sha],
                cwd=repo, seconds=90, env=runner_env, accepted=(0, 1))
            aggregate = sdk.read_json(case_directory / "aggregate.json")
            summary = validate_case_retirement(aggregate, args.expected_source_sha, args.expected_pr_head_sha)
            after = sdk.inventory(value["runtime"])
            sdk.write_json(evidence / (flavor + "-runtime-after.json"), after)
            sdk.assert_same_tree(value["before"], after)
            sdk.assert_same_tree(expected[flavor], sdk.inventory(value["kit"]))
            sdk.require(command["exit_code"] == (0 if aggregate["success"] else 1),
                        "FixtureExitAndAggregateDisagree")
            report["variants"][flavor] = {
                "collected": True, "runner_exit_code": command["exit_code"],
                "fixture_success": aggregate["success"], "aggregate": sdk.file_identity(case_directory / "aggregate.json"),
                "runtime_content_id": sdk.canonical_digest(after), "cases": summary,
                "actual_process_module_sampling": False}
            # A safely retired, genuinely failed stock case does not skip the patched run.
        sdk.require(sdk.source_identity(repo, args.expected_source_sha, args.expected_pr_head_sha) == inputs,
                    "ComparisonSourceChanged")
        report.update(comparison_status(report["variants"]))
        report["stage"] = "complete"
        if not report["success"]:
            report["errors"].append("OriginalFixtureFailurePreserved; see separate stock and patched receipts")
    except BaseException as error:
        report["errors"].append(type(error).__name__ + ":" + str(error))
    finally:
        report["finished_utc"] = sdk.utc()
        if evidence is not None:
            sdk.write_json(evidence / "comparison.json", report)
        print(json.dumps({"success": report["success"], "comparison_collected": report["comparison_collected"],
                          "stage": report["stage"], "errors": report["errors"]}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
