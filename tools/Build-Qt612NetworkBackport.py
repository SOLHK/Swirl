#!/usr/bin/env python3
"""Produce the pinned QtNetwork HTTP-bounds backport on a hosted Windows runner."""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import xml.etree.ElementTree as ET
import zipfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OVERLAY = (
    "bin/Qt6Network.dll", "lib/Qt6Network.lib",
    "include/QtNetwork/6.12.0/QtNetwork/private/qhttpnetworkreply_p.h",
)


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


sdk = module("network_sdk_util", "Build-Qt612QmlDiagnosticSdk.py")
sources = module("network_source_util", "Prepare-Qt612ProductSource.py")
require = sdk.require


def run(arguments, cwd, evidence, name, seconds, *, env=None, accepted=(0,)):
    """Bound each public compiler/fixture command; retain its original result."""
    args = [str(value) for value in arguments]
    evidence.mkdir(parents=True, exist_ok=True)
    result = {"arguments": args, "timeout_seconds": seconds, "success": False}
    started = time.monotonic()
    try:
        with (evidence / (name + ".stdout.log")).open("xb") as stdout, \
                (evidence / (name + ".stderr.log")).open("xb") as stderr:
            process = subprocess.run(args, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                                     timeout=seconds, creationflags=subprocess.CREATE_NO_WINDOW)
        result["exit_code"] = process.returncode
        result["success"] = process.returncode in accepted
        require(result["success"], "CommandFailed:" + name)
        return process.returncode
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        sdk.write_json(evidence / (name + ".json"), result)


def feature_map(paths):
    features = {}
    for path in paths:
        for name, value in re.findall(r"^#define QT_FEATURE_(\w+) (-?1)$",
                                      path.read_text(encoding="utf-8"), re.MULTILINE):
            require(name not in features, "DuplicateNetworkFeature:" + name)
            features[name] = int(value)
    require(features, "MissingNetworkFeatures")
    return features


def pe_machine(path):
    data = path.read_bytes()
    require(data[:2] == b"MZ" and len(data) > 64, "InvalidPeHeader")
    offset = struct.unpack_from("<I", data, 60)[0]
    require(data[offset:offset + 4] == b"PE\0\0"
            and struct.unpack_from("<H", data, offset + 4)[0] == 0x8664, "PeNotAmd64")
    return "AMD64"


def corresponding_source(source, evidence, source_item, patches):
    snapshot = sdk.inventory(source)
    sdk.write_json(evidence / "source-snapshot-files.json", snapshot)
    archive = evidence / "qtbase-corresponding-source.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for relative in snapshot:
            sources.zip_add(output, "qtbase/" + relative, (source / relative).read_bytes())
    result = {"source": source_item, "patches": patches, "archive": sdk.file_identity(archive),
              "file_manifest_content_id": sdk.canonical_digest(snapshot),
              "tracked_regular_files": len(snapshot),
              "tracked_bytes": sum(item["bytes"] for item in snapshot.values()),
              "omitted_gitlinks": [],
              "scope": "Complete verified QtBase release archive with the two recorded patches; "
                       "all original build files, license files and notices retained."}
    sdk.write_json(evidence / "corresponding-source.json", result)
    return result


def prepare_openssl_headers(root, work, evidence):
    receipt = sdk.read_json(root / "openssl-runtime.json")
    lock = sdk.read_json(HERE / "openssl-runtime.lock.json")
    require(receipt["status"] == "success" and receipt["target"] == "VC-WIN64A"
            and receipt["source"] == lock["source"], "OpenSslRuntimeIdentityMismatch")
    candidates = list(root.with_name(root.name + "-build").glob("*/compile/libssl.lib"))
    require(len(candidates) == 1, "FreshOpenSslDevelopmentBuildRequired")
    build = candidates[0].parent
    source_candidates = list(build.parent.glob("source/*/include/openssl/ssl.h"))
    require(len(source_candidates) == 1 and (build / "libcrypto.lib").is_file(),
            "OpenSslDevelopmentFilesMissing")
    include = work / "openssl-include"
    shutil.copytree(source_candidates[0].parent.parent, include)
    generated = build / "include/openssl"
    require((generated / "configuration.h").is_file(), "GeneratedOpenSslConfigurationMissing")
    for path in generated.glob("*.h"):
        shutil.copyfile(path, include / "openssl" / path.name)
    sdk.write_json(evidence / "openssl-development.json", {
        "runtime_receipt": receipt, "headers": sdk.inventory(include),
        "libraries": {name: sdk.file_identity(build / name) for name in ("libssl.lib", "libcrypto.lib")},
    })
    return include, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-receipt", type=Path, required=True)
    parser.add_argument("--openssl-root", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--evidence-directory", type=Path, required=True)
    args = parser.parse_args()
    report = {"schema": 1, "kind": "swirl-qt612-network-backport", "success": False,
              "errors": [], "source_sha": os.environ.get("GITHUB_SHA"),
              "qt_version": "6.12.0", "architecture": "x86_64-windows-msvc",
              "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
              "real_provider_requests": 0}
    evidence = None
    try:
        require(os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true"
                and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
                and os.environ.get("GITHUB_REPOSITORY") == "SOLHK/Swirl"
                and os.environ.get("VSCMD_ARG_TGT_ARCH") == "x64", "HostedMsvcBuildRequired")
        require(re.fullmatch(r"[0-9a-f]{40}", report["source_sha"] or ""), "SourceShaMissing")
        require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
                == report["source_sha"], "SourceShaMismatch")
        require(not subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                            cwd=REPO, text=True).strip(), "TrackedSourceDirty")
        evidence = sdk.fresh_directory(args.evidence_directory.absolute(), root=REPO)
        work = sdk.fresh_directory(args.work_root.absolute(), root=Path(os.environ["RUNNER_TEMP"]))
        commands = evidence / "commands"
        backports = sdk.read_json(HERE / "qt612-backports.lock.json")
        product = sdk.read_json(HERE / "qt612-product-sdk.lock.json")
        official = sdk.read_json(args.official_receipt)
        sdk.check_receipt(product["recipe"], official)
        stock = sdk.plain_path(Path(official["kit_root"]))
        stock_inventory = sdk.inventory(stock)
        sdk.write_json(evidence / "stock-sdk-receipt.json", official)
        report["stock_files"] = {name: stock_inventory[name] for name in OVERLAY}
        tools = {name: sdk.plain_path(Path(shutil.which(name) or ""))
                 for name in ("cmake.exe", "ninja.exe", "cl.exe", "dumpbin.exe", "git.exe")}
        compiler_binary = {"path": str(tools["cl.exe"]), **sdk.file_identity(tools["cl.exe"])}
        require({key: compiler_binary[key] for key in ("bytes", "sha256")}
                == {key: product["content"]["producer_compiler_binary"][key] for key in ("bytes", "sha256")},
                "CompilerDoesNotMatchSelectedQmlProducer")
        report["tools"] = {name: {"path": str(path), **sdk.file_identity(path)} for name, path in tools.items()}
        _, source_lock = sources.source_lock()
        item = next(value for value in source_lock["official_sources"] if value["module"] == "qtbase")
        require(item["commit"] == backports["sources"]["qtbase"], "BackportSourceMismatch")
        archive = sources.acquire_archive(item, work / "archives", 240)
        report["source_archive_verification"], _ = sources.inspect_official_archive(archive, item, source_lock["limits"])
        extraction = sdk.fresh_directory(work / "source-archive", root=work)
        with tarfile.open(archive, "r:xz") as source_archive:
            source_archive.extractall(extraction, filter="data")
        source = extraction / "qtbase-everywhere-src-6.12.0"
        patches = [value for value in backports["patches"] if value["module"] == "qtbase"]
        require([Path(value["path"]).name for value in patches] == [
            "CVE-2026-116337-qtbase-6.12-0002.diff", "CVE-2026-116337-qtbase-6.12-0001.diff"], "PatchOrderMismatch")
        for index, patch in enumerate(patches):
            path = REPO / patch["path"]
            require(sdk.digest(path) == patch["sha256"], "PatchDigestMismatch")
            run([tools["git.exe"], "apply", "--check", path], source, commands, f"patch-{index}-check", 30)
            run([tools["git.exe"], "apply", path], source, commands, f"patch-{index}-apply", 30)
        report.update(source=item, patches=patches)
        report["corresponding_source"] = corresponding_source(source, evidence, item, patches)
        reproduction = evidence / "reproduction"
        inputs = ["tools/Build-Qt612NetworkBackport.py", ".github/workflows/build-qt612-network-backport.yml",
                  "tools/qt612-backports.lock.json", "tools/qt612-product-sdk.lock.json",
                  "tools/qt612-product-source.lock.json", "tools/Build-OpenSslRuntime.py",
                  "tools/Build-Qt612QmlDiagnosticSdk.py", "tools/Prepare-Qt612ProductSource.py",
                  "tools/Install-QtSdk.py", "tools/requirements-qt-sdk.txt",
                  "scripts/Build-CiOpenSslRuntime.ps1", "scripts/Prepare-Nasm.ps1",
                  "scripts/RustProductPackagePolicy.ps1",
                  "tools/openssl-runtime.lock.json", *[patch["path"] for patch in patches],
                  "tools/repros/qt612-http-bounds/main.cpp", "tools/repros/qt612-http-bounds/CMakeLists.txt"]
        for relative in inputs:
            destination = reproduction / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, destination)
        report["source_inputs"] = {name: sdk.file_identity(REPO / name) for name in inputs}
        ssl_include, ssl_build = prepare_openssl_headers(args.openssl_root.absolute(), work, evidence)
        env = sdk.tool_environment()
        env["PATH"] = str(stock / "bin") + os.pathsep + env["PATH"]
        build = sdk.fresh_directory(work / "build", root=work)
        initial_cache = sdk.prepare_msvc_initial_cache(work, evidence)
        configure = [tools["cmake.exe"], "-S", source, "-B", build, "-G", "Ninja", "-C", initial_cache,
                     "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL",
                     "-DCMAKE_C_COMPILER=" + str(tools["cl.exe"]), "-DCMAKE_CXX_COMPILER=" + str(tools["cl.exe"]),
                     "-DCMAKE_MAKE_PROGRAM=" + str(tools["ninja.exe"]), "-DQT_BUILD_TESTS=OFF",
                     "-DQT_BUILD_EXAMPLES=OFF", "-DQT_BUILD_TOOLS_BY_DEFAULT=OFF", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                     "-DFEATURE_openssl=ON", "-DFEATURE_openssl_runtime=ON", "-DFEATURE_openssl_linked=OFF",
                     "-DFEATURE_dtls=ON", "-DFEATURE_ocsp=ON", "-DOPENSSL_INCLUDE_DIR=" + str(ssl_include),
                     "-DOPENSSL_SSL_LIBRARY=" + str(ssl_build / "libssl.lib"),
                     "-DOPENSSL_CRYPTO_LIBRARY=" + str(ssl_build / "libcrypto.lib")]
        run(configure, work, commands, "configure-network", 600, env=env)
        run([tools["cmake.exe"], "--build", build, "--target", "Network", "--parallel", "4"],
            work, commands, "build-network", 2400, env=env)
        compiler_files = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
        require(len(compiler_files) == 1, "AmbiguousCompilerMetadata")
        compiler = sdk.compiler_values(compiler_files[0].read_text(encoding="utf-8"))
        expected_compiler = product["content"]["producer_compiler"]
        require(all(compiler[key] == expected_compiler[key] for key in (
            "CMAKE_CXX_COMPILER_ID", "CMAKE_CXX_COMPILER_VERSION", "MSVC_CXX_ARCHITECTURE_ID")), "CompilerMetadataMismatch")
        report["compiler"] = {"binary": compiler_binary, "metadata": {
            "compiler_id": compiler["CMAKE_CXX_COMPILER_ID"], "compiler_version": compiler["CMAKE_CXX_COMPILER_VERSION"],
            "msvc_tools_version": os.environ.get("VCToolsVersion"), "windows_sdk_version": os.environ.get("WindowsSDKVersion")}}
        shutil.copyfile(compiler_files[0], evidence / "CMakeCXXCompiler.cmake")
        shutil.copyfile(build / "CMakeCache.txt", evidence / "CMakeCache.txt")
        stage = sdk.fresh_directory(evidence / "module-install-output", root=evidence)
        inputs = (build / OVERLAY[0], build / OVERLAY[1], source / "src/network/access/qhttpnetworkreply_p.h")
        for relative, original in zip(OVERLAY, inputs):
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)
        report["module_files"] = sdk.inventory(stage)
        sdk.write_json(evidence / "module-files.json", report["module_files"])
        stock_features = feature_map([stock / "include/QtNetwork/qtnetwork-config.h",
                                     stock / "include/QtNetwork/6.12.0/QtNetwork/private/qtnetwork-config_p.h"])
        patched_features = feature_map([build / "src/network/qtnetwork-config.h", build / "src/network/qtnetwork-config_p.h"])
        report["features"] = {"stock": stock_features, "patched": patched_features, "verified": stock_features == patched_features}
        sdk.write_json(evidence / "features.json", report["features"])
        cache = sdk.cache_values((build / "CMakeCache.txt").read_text(encoding="utf-8"))
        tls_features = {name: cache.get("QT_FEATURE_" + name) for name in
                        ("ssl", "openssl", "openssl_runtime", "openssl_linked", "dtls", "ocsp")}
        report["tls_features"] = tls_features
        require(stock_features == patched_features and all(patched_features.get(name) == 1 for name in
                ("ssl", "dtls", "ocsp")) and tls_features == {
                    "ssl": "ON", "openssl": "ON", "openssl_runtime": "ON", "openssl_linked": "OFF",
                    "dtls": "ON", "ocsp": "ON"}, "NetworkFeaturesChangedOrTlsIncomplete")
        interfaces = {}
        for flavor, root in (("stock", stock), ("patched", stage)):
            dll = root / "bin/Qt6Network.dll"
            run([tools["dumpbin.exe"], "/exports", dll], work, commands, flavor + "-exports", 30, env=env)
            run([tools["dumpbin.exe"], "/dependents", dll], work, commands, flavor + "-dependents", 30, env=env)
            interfaces[flavor] = {"machine": pe_machine(dll),
                "exports": sdk.parse_exports(sdk.output_text(commands, flavor + "-exports")),
                "dependencies": sdk.parse_dependents(sdk.output_text(commands, flavor + "-dependents"))}
        report["interface"] = interfaces
        sdk.write_json(evidence / "interface.json", interfaces)
        require(interfaces["stock"] == interfaces["patched"], "NetworkPeInterfaceChanged")
        fixture_source = sdk.fresh_directory(work / "fixture-source", root=work)
        original_fixture = (HERE / "repros/qt612-http-bounds/main.cpp").read_text(encoding="utf-8")
        needle = "QFETCH(QByteArray,response);QFETCH(bool,valid);"
        require(original_fixture.count(needle) == 1, "FixtureInstrumentationPointChanged")
        sample = '''
        wchar_t networkModulePath[32768];
        const DWORD networkModuleLength=GetModuleFileNameW(GetModuleHandleW(L"Qt6Network.dll"),networkModulePath,32768);
        QVERIFY(networkModuleLength>0&&networkModuleLength<32768);
        const QString loadedNetwork=QString::fromWCharArray(networkModulePath,networkModuleLength);
        QCOMPARE(loadedNetwork.compare(qEnvironmentVariable("SWIRL_EXPECTED_NETWORK_DLL"),Qt::CaseInsensitive),0);
        qInfo().noquote()<<"HTTP_BOUNDS_NETWORK_DLL"<<loadedNetwork;
'''
        (fixture_source / "main.cpp").write_text("#include <windows.h>\n" + original_fixture.replace(needle, needle + sample), encoding="utf-8")
        shutil.copyfile(HERE / "repros/qt612-http-bounds/CMakeLists.txt", fixture_source / "CMakeLists.txt")
        shutil.copytree(fixture_source, evidence / "fixture-source")
        fixture_build = work / "fixture-build"
        run([tools["cmake.exe"], "-S", fixture_source, "-B", fixture_build, "-G", "Ninja", "-C", initial_cache,
             "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + str(stock),
             "-DCMAKE_CXX_COMPILER=" + str(tools["cl.exe"]), "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL"],
            work, commands, "configure-fixture", 180, env=env)
        run([tools["cmake.exe"], "--build", fixture_build, "--parallel", "4"], work, commands, "build-fixture", 300, env=env)
        fixtures = {}
        for flavor, root in (("stock", stock), ("patched", stage)):
            runtime = sdk.fresh_directory(work / ("runtime-" + flavor), root=work)
            shutil.copyfile(fixture_build / "QtHttpBounds.exe", runtime / "QtHttpBounds.exe")
            for name in ("Qt6Core.dll", "Qt6Test.dll"):
                shutil.copyfile(stock / "bin" / name, runtime / name)
            shutil.copyfile(root / "bin/Qt6Network.dll", runtime / "Qt6Network.dll")
            before = sdk.inventory(runtime)
            runtime_env = sdk.tool_environment()
            runtime_env["PATH"] = str(runtime) + os.pathsep + str(Path(os.environ["SYSTEMROOT"]) / "System32")
            runtime_env["SWIRL_EXPECTED_NETWORK_DLL"] = str(runtime / "Qt6Network.dll")
            cases = {}
            for tag in ("valid-response", "unterminated-status-line", "unterminated-header-block"):
                xml = evidence / (flavor + "-" + tag + ".xml")
                expected_pass = flavor == "patched" or tag == "valid-response"
                code = run([runtime / "QtHttpBounds.exe", "responseBounds:" + tag, "-o", str(xml) + ",xml", "-o", "-,txt"],
                           runtime, commands, flavor + "-" + tag, 15, env=runtime_env, accepted=(0,) if expected_pass else (1,))
                functions = ET.parse(xml).getroot().findall("TestFunction")
                case_functions = [value for value in functions if value.attrib.get("name") == "responseBounds"]
                require(len(case_functions) == 1, "HttpFixtureCaseMissing")
                incidents = case_functions[0].findall("Incident")
                require(len(incidents) == 1 and incidents[0].attrib.get("type") == ("pass" if expected_pass else "fail")
                        and incidents[0].findtext("DataTag") == tag and not ET.parse(xml).getroot().findall(".//Incident[@type='skip']"),
                        "HttpFixtureResultMismatch")
                output = sdk.output_text(commands, flavor + "-" + tag)
                require("HTTP_BOUNDS_NETWORK_DLL " in output and re.search(
                    r"HTTP_BOUNDS\s+" + re.escape(tag) + r"\s+natural_finish\s+" + ("true" if expected_pass else "false"), output),
                    "HttpFixtureNaturalCompletionOrModuleProofMissing")
                if not expected_pass:
                    require("Qt must reject an impossible response before the peer ends it" in incidents[0].findtext("Description", ""),
                            "StockFailureWasNotTheExpectedHeaderBoundsAssertion")
                cases[tag] = {"exit_code": code, "expected_assertion_pass": expected_pass,
                              "actual_assertion_pass": code == 0, "actual_module_verified": True,
                              "finished_naturally": expected_pass}
            require(sdk.inventory(runtime) == before, "FixtureRuntimeChanged")
            fixtures[flavor] = {"cases": cases, "runtime_files": before}
        report["fixtures"] = fixtures
        report["stock_unchanged"] = sdk.inventory(stock) == stock_inventory
        require(report["stock_unchanged"], "StockSdkChanged")
        report["success"] = True
    except Exception as error:
        report["errors"].append(str(error))
        print(str(error), file=sys.stderr)
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        if evidence is not None:
            sdk.write_json(evidence / "receipt.json", report)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
