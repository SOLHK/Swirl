#!/usr/bin/env python3
"""Build an isolated, source-pinned QtQml diagnostic SDK; never alter a product SDK."""

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import time
import threading
import zipfile


LOCK = "tools/qt612-qml-patch.lock.json"
PATCH = "tools/patches/qt612-qv4-sweep-8c92fe0.patch"
NEW_INPUTS = [
    LOCK, PATCH, "tools/Build-Qt612QmlDiagnosticSdk.py",
    "tools/RunQt612RuntimeComparison.py", "tools/tests/test_qt612_diagnostic_sdk.py",
    ".github/workflows/diagnose-qt612-runtime-patch.yml",
]
SOURCE_INPUTS = NEW_INPUTS + [
    "tools/Install-QtSdk.py", "tools/requirements-qt-sdk.txt",
    "tools/RunQt612GcProbe.py", "tools/PrivateSubscriptionProcess.py",
    "tools/PrivateSubscriptionBudget.py", ".github/workflows/diagnose-qt612-gc.yml",
] + ["tools/repros/qt612-popup-gc/" + name for name in
     ("CMakeLists.txt", "main.cpp", "sweep.cpp", "Main.qml", "ProbeDialog.qml", "OwnedHelper.qml")]
SHA = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
MAX_LOG_BYTES = 64 * 1024 * 1024
MSVC_DEBUG_INFORMATION_FORMAT = "$<$<CONFIG:Debug,RelWithDebInfo>:Embedded>"
MSVC_INITIAL_CACHE = (
    'set(CMAKE_POLICY_DEFAULT_CMP0141 NEW CACHE STRING "MSVC debug information policy")\n'
    'set(CMAKE_MSVC_DEBUG_INFORMATION_FORMAT "' + MSVC_DEBUG_INFORMATION_FORMAT
    + '" CACHE STRING "Embedded debug information for compiler probes")\n'
)


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write("\n")


def read_json(path, limit=32 * 1024 * 1024):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= limit, "MissingOrOversizedJson")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def plain_path(path, *, root=None, exists=True):
    path = Path(path)
    require(path.is_absolute(), "AbsoluteLocalPathRequired")
    require(not str(path).startswith(("\\\\", "//")), "NetworkPathRejected")
    require(not any(ch in str(path) for ch in "\0\r\n"), "PathControlCharacterRejected")
    for candidate in [path, *path.parents]:
        if candidate.exists() or candidate.is_symlink():
            require(not candidate.is_symlink()
                    and not getattr(candidate, "is_junction", lambda: False)(),
                    "LinkedPathRejected")
            flags = getattr(candidate.stat(follow_symlinks=False), "st_file_attributes", 0)
            require(not flags & 0x400, "ReparsePathRejected")
    resolved = path.resolve(strict=exists)
    if root is not None:
        boundary = plain_path(root)
        require(resolved != boundary and resolved.is_relative_to(boundary), "OutputEscapesOwnedRoot")
    return resolved


def fresh_directory(path, *, root=None):
    path = plain_path(path, root=root, exists=False)
    require(not path.exists(), "FreshDirectoryRequired")
    path.mkdir(parents=True)
    return path


def file_identity(path):
    path = plain_path(path)
    require(path.is_file(), "RegularFileRequired")
    return {"bytes": path.stat().st_size, "sha256": digest(path)}


def inventory(root):
    root = plain_path(root)
    result, folded, total = {}, set(), 0
    deadline = time.monotonic() + 300
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        require(time.monotonic() < deadline, "InventoryDeadlineExceeded")
        plain_path(path, root=root)
        if path.is_dir():
            continue
        require(path.is_file(), "NonRegularInventoryEntry")
        relative = path.relative_to(root).as_posix()
        require(relative.casefold() not in folded, "CaseCollidingInventoryEntry")
        folded.add(relative.casefold())
        require(len(folded) <= 100000, "InventoryEntryLimitExceeded")
        item = file_identity(path)
        total += item["bytes"]
        require(total <= 16 * 1024**3, "InventorySizeLimitExceeded")
        result[relative] = item
    require(result, "EmptyInventory")
    return result


def compare_tree(expected, actual):
    return {
        "added": sorted(set(actual) - set(expected)),
        "removed": sorted(set(expected) - set(actual)),
        "changed": sorted(p for p in set(expected) & set(actual) if expected[p] != actual[p]),
    }


def assert_same_tree(expected, actual):
    delta = compare_tree(expected, actual)
    require(not any(delta.values()), "TreeIdentityChanged:" + json.dumps(delta))


def check_receipt(lock, receipt):
    require(receipt.get("version") == lock["qt_version"]
            and receipt.get("arch") == lock["architecture"], "StockSdkVersionOrArchitectureMismatch")
    stock = lock["stock"]
    require(receipt.get("metadata_url") == stock["metadata_url"]
            and receipt.get("metadata_sha256") == stock["metadata_sha256"], "StockMetadataPinMismatch")
    require(receipt.get("package_names") == stock["package_names"], "StockPackageSetMismatch")
    versions = {x["name"]: x["version"] for x in receipt.get("packages", [])}
    require(versions == stock["package_versions"], "StockPackageVersionMismatch")
    expected = {x["filename"]: {k: x[k] for k in ("package", "url", "sha256")}
                for x in stock["archives"]}
    actual = {}
    for item in receipt.get("archives", []):
        require(item["filename"] not in actual, "DuplicateStockArchive")
        actual[item["filename"]] = {k: item[k] for k in ("package", "url", "sha256")}
    require(actual == expected and len(actual) == 9, "StockArchivePinMismatch")


def check_patch(lock, patch, original):
    require(digest(patch) == lock["patch"]["sha256"], "PatchFilePinMismatch")
    require(digest(original) == lock["patch"]["preimage_sha256"], "PatchPreimageMismatch")


def verify_locked_fetch(lock, url, data):
    stock = lock["stock"]
    if url == stock["metadata_url"]:
        require(hashlib.sha256(data).hexdigest() == stock["metadata_sha256"],
                "MetadataChangedBeforeExtraction")
        return
    hashes = {stock["metadata_url"] + ".sha256": stock["metadata_sha256"]}
    hashes.update({entry["url"] + ".sha256": entry["sha256"] for entry in stock["archives"]})
    require(url in hashes, "UnexpectedInstallerFetchUrl")
    value = data.decode("ascii").split()
    require(value and SHA.fullmatch(value[0].lower()) and value[0].lower() == hashes[url],
            "OfficialDigestChangedBeforeExtraction")


def install_stock_worker(repo, args):
    """Constrain the unchanged installer before extraction or execution of SDK tools."""
    report = {"schema": 1, "success": False, "errors": [], "fetched": {},
              "downloaded": {}, "extracted": [], "started_utc": utc()}
    evidence = None
    try:
        admit(repo, args.expected_source_sha, args.expected_pr_head_sha)
        work = plain_path(args.work_root.absolute(), root=Path(os.environ["RUNNER_TEMP"]).absolute())
        evidence = fresh_directory(args.evidence_directory.absolute(), root=repo)
        output = plain_path(work / "stock", root=work, exists=False)
        require(not output.exists(), "StockWorkerOutputMustBeFresh")
        cache = plain_path(args.archive_cache.absolute(), root=work)
        lock = read_json(repo / LOCK, 65536)
        entries = {entry["filename"]: entry for entry in lock["stock"]["archives"]}
        require(len(entries) == 9, "UnexpectedPinnedArchiveCount")
        spec = importlib.util.spec_from_file_location("original_pinned_qt_installer",
                                                     repo / "tools/Install-QtSdk.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        original_fetch, original_download, original_extract = (
            installer.fetch, installer.download_archive, installer.extract_archive)
        mutex = threading.Lock()

        def locked_fetch(url):
            allowed = {lock["stock"]["metadata_url"], lock["stock"]["metadata_url"] + ".sha256"}
            allowed.update(x["url"] + ".sha256" for x in entries.values())
            require(url in allowed, "UnexpectedInstallerFetchUrl")
            data = original_fetch(url)  # Original HTTPS certificate validation remains enabled.
            verify_locked_fetch(lock, url, data)
            with mutex:
                report["fetched"][url] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if url == lock["stock"]["metadata_url"]:
                (evidence / "official-Updates.xml").write_bytes(data)
            return data

        def locked_download(entry, destination):
            expected = entries.get(entry.get("filename"))
            require(expected is not None and all(entry.get(k) == expected[k]
                                                for k in ("package", "filename", "url")),
                    "UnpinnedArchiveDownloadRejected")
            require(Path(destination).resolve() == cache, "ArchiveCacheIdentityMismatch")
            result = original_download(entry, destination)
            path = plain_path(Path(result["local_path"]), root=cache)
            require(result["sha256"] == expected["sha256"] and digest(path) == expected["sha256"],
                    "ArchiveBytesChangedBeforeExtraction")
            with mutex:
                require(entry["filename"] not in report["downloaded"], "DuplicateArchiveDownload")
                report["downloaded"][entry["filename"]] = file_identity(path)
            return result

        def locked_extract(path, destination):
            path = plain_path(Path(path), root=cache)
            expected = entries.get(path.name)
            require(expected is not None and digest(path) == expected["sha256"],
                    "UnpinnedArchiveExtractionRejected")
            destination = plain_path(Path(destination), root=output)
            require(path.name not in report["extracted"], "DuplicateArchiveExtraction")
            original_extract(path, destination)
            report["extracted"].append(path.name)

        installer.fetch, installer.download_archive, installer.extract_archive = (
            locked_fetch, locked_download, locked_extract)
        sys.argv = [str(repo / "tools/Install-QtSdk.py"), "--version", "6.12.0",
                    "--arch", "win64_msvc2022_64", "--output", str(output), "--archive-cache", str(cache)]
        installer.main()
        require(set(report["downloaded"]) == set(entries) and set(report["extracted"]) == set(entries),
                "PinnedArchiveSetIncomplete")
        check_receipt(lock, read_json(output / "sdk-install-result.json"))
        report["success"] = True
    except BaseException as error:
        report["errors"].append(type(error).__name__ + ":" + str(error))
    finally:
        report["finished_utc"] = utc()
        if evidence is not None:
            write_json(evidence / "receipt.json", report)
        print(json.dumps({"stock_worker_success": report["success"], "errors": report["errors"]}))
    return 0 if report["success"] else 1


def source_identity(repo, source_sha, head_sha):
    require(COMMIT.fullmatch(source_sha) and COMMIT.fullmatch(head_sha), "InvalidSourceSha")
    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(repo), *arguments],
                                       text=True, timeout=15).strip()
    require(git("rev-parse", "HEAD") == source_sha, "CheckoutIdentityMismatch")
    parents = git("show", "-s", "--format=%P", "HEAD").split()
    require(len(parents) == 2 and parents[1] == head_sha, "PrMergeParentIdentityMismatch")
    files = {}
    for name in SOURCE_INPUTS:
        path = plain_path(repo / name, root=repo)
        data = subprocess.check_output(["git", "-C", str(repo), "show", source_sha + ":" + name],
                                       timeout=15)
        require(path.read_bytes() == data, "SourceDiffersFromGitBlob:" + name)
        files[name] = file_identity(path)
    return {"source_sha": source_sha, "pr_head_sha": head_sha, "parents": parents, "files": files}


def admit(repo, source_sha, head_sha):
    require(os.name == "nt" and struct.calcsize("P") == 8, "WindowsX64Required")
    expected = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                "GITHUB_REPOSITORY": "SOLHK/Swirl", "GITHUB_BASE_REF": "test",
                "GITHUB_HEAD_REF": "work/node-probe-render-20261105",
                "SWIRL_QT612_RUNTIME_PATCH": "1", "SWIRL_DIAGNOSTIC_PR": "61",
                "SWIRL_EXECUTING_PR_HEAD": head_sha, "GITHUB_SHA": source_sha,
                "GITHUB_EVENT_NAME": "pull_request"}
    require(all(os.environ.get(k) == v for k, v in expected.items()), "HostedDiagnosticAdmissionRejected")
    event = read_json(plain_path(Path(os.environ["GITHUB_EVENT_PATH"])), 2 * 1024**2)
    pr = event.get("pull_request", {})
    require(event.get("action") == "labeled" and event.get("number") == 61
            and event.get("label", {}).get("name") == "qa-qt612-runtime-patch"
            and pr.get("head", {}).get("sha") == head_sha
            and pr.get("head", {}).get("ref") == "work/node-probe-render-20261105"
            and pr.get("head", {}).get("repo", {}).get("full_name") == "SOLHK/Swirl"
            and pr.get("base", {}).get("ref") == "test"
            and pr.get("base", {}).get("repo", {}).get("full_name") == "SOLHK/Swirl",
            "UnexpectedPullRequestLabelEvent")
    return source_identity(repo, source_sha, head_sha)


def tool_environment():
    # Compiler/OS inputs are explicit. Do not forward tokens, private profiles,
    # proxy overrides, Git credential configuration or other SDK selectors.
    names = {
        "ALLUSERSPROFILE", "APPDATA", "COMSPEC", "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)",
        "COMMONPROGRAMW6432", "INCLUDE", "LIB", "LIBPATH", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS",
        "OS", "PATH", "PATHEXT", "PROCESSOR_ARCHITECTURE", "PROGRAMDATA", "PROGRAMFILES",
        "PROGRAMFILES(X86)", "PROGRAMW6432", "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP",
        "USERPROFILE", "USERNAME", "WINDIR", "VCTOOLSINSTALLDIR", "VCTOOLSVERSION",
        "VSINSTALLDIR", "VCINSTALLDIR", "VISUALSTUDIOVERSION", "WINDOWSSDKDIR",
        "WINDOWSSDKVERSION", "WINDOWSSDKBINPATH", "WINDOWSSDKVERBINPATH", "UNIVERSALCRTSDKDIR",
        "UCRTVERSION", "VSCMD_ARG_HOST_ARCH", "VSCMD_ARG_TGT_ARCH",
        "GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "GITHUB_REPOSITORY", "GITHUB_SHA",
        "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_BASE_REF", "GITHUB_HEAD_REF",
        "GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH", "SWIRL_EXECUTING_PR_HEAD",
        "RUNNER_TEMP", "GITHUB_WORKSPACE", "SWIRL_QT612_RUNTIME_PATCH", "SWIRL_DIAGNOSTIC_PR",
    }
    env = {k.upper(): v for k, v in os.environ.items() if k.upper() in names}
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull, VSLANG="1033", PYTHONUTF8="1",
               QT_FORCE_STDERR_LOGGING="1", QT_MESSAGE_PATTERN="[%{type}] %{message}")
    # Retain the prior invocation-local setting; no supported effect is established.
    # Actual owned-Job exit and the exact compiler capability decide acceptance.
    env["VCTIP_NO_TELEMETRY"] = "1"
    return env


def executable_inventory(toolchain, tools):
    result = {}
    for directory, files in toolchain.items():
        for relative, identity in files.items():
            if relative.lower().endswith(".exe"):
                path = str(Path(directory) / relative)
                result[path.replace("\\", "/").casefold()] = {"path": path, **identity}
    for value in tools.values():
        result[value["path"].replace("\\", "/").casefold()] = value
    return result


def prepare_msvc_initial_cache(work, evidence):
    path = Path(work) / "msvc-initial-cache.cmake"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(MSVC_INITIAL_CACHE)
    copied = Path(evidence) / path.name
    with copied.open("xb") as stream:
        stream.write(path.read_bytes())
    require(file_identity(copied) == file_identity(path), "InitialCacheEvidenceChanged")
    return path


def module_configure_arguments(work, stock, tools):
    work, stock = Path(work), Path(stock)
    return [stock / "bin/qt-configure-module.bat", work / "source", "--", "-G", "Ninja",
            "-C", work / "msvc-initial-cache.cmake",
            cmake_path_definition("CMAKE_PREFIX_PATH", stock, "PATH"),
            "-DCMAKE_BUILD_TYPE=Release",
            cmake_path_definition("CMAKE_INSTALL_PREFIX", work / "module-stage", "PATH"),
            *[cmake_path_definition(key, tools[name], "FILEPATH") for key, name in (
                ("CMAKE_C_COMPILER", "cl.exe"), ("CMAKE_CXX_COMPILER", "cl.exe"),
                ("CMAKE_LINKER", "link.exe"), ("CMAKE_AR", "lib.exe"),
                ("CMAKE_RC_COMPILER", "rc.exe"), ("CMAKE_MT", "mt.exe"),
                ("CMAKE_MAKE_PROGRAM", "ninja.exe"))],
            "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL", "-DQT_BUILD_TESTS=OFF",
            "-DQT_BUILD_EXAMPLES=OFF", "-DQT_BUILD_TOOLS_BY_DEFAULT=OFF",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]


def module_configure_script(arguments):
    return ("$ErrorActionPreference = 'Stop'\n& " + " ".join(ps_quote(x) for x in arguments)
            + "\nexit $LASTEXITCODE\n").encode("utf-8")


def fixture_configure_arguments(repo, work, stock, tools):
    return [tools["cmake.exe"], "-S", Path(repo) / "tools/repros/qt612-popup-gc",
            "-B", Path(work) / "fixtures", "-G", "Ninja",
            "-C", Path(work) / "msvc-initial-cache.cmake", "-DCMAKE_BUILD_TYPE=Release",
            cmake_path_definition("CMAKE_PREFIX_PATH", stock, "PATH"),
            *[cmake_path_definition(key, tools[name], "FILEPATH") for key, name in (
                ("CMAKE_CXX_COMPILER", "cl.exe"), ("CMAKE_MAKE_PROGRAM", "ninja.exe"),
                ("CMAKE_LINKER", "link.exe"), ("CMAKE_AR", "lib.exe"),
                ("CMAKE_RC_COMPILER", "rc.exe"), ("CMAKE_MT", "mt.exe"))],
            "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]


def compiler_phase_plan(phase, arguments, cwd, context, lock, tool_identities, known_executables):
    """Bind one of four exact compiler invocations; a name or a receipt is not a capability."""
    phases = {"sdk:10-configure", "sdk:11-qml-build",
              "comparison:01-configure-fixtures", "comparison:02-build-fixtures"}
    require(phase in phases and set(context) == {"repo", "work", "stock", "tools"},
            "UnrecognizedCompilerPhase")
    repo, work, stock = (plain_path(Path(context[key])) for key in ("repo", "work", "stock"))
    tools = context["tools"]
    build = plain_path(work / ("build" if phase.startswith("sdk:") else "fixtures"), root=work)
    cache = plain_path(work / "msvc-initial-cache.cmake", root=work)
    require(cache.read_bytes() == MSVC_INITIAL_CACHE.encode("utf-8"), "CompilerInitialCacheChanged")
    inputs = {str(cache): file_identity(cache)}
    if phase == "sdk:10-configure":
        source = plain_path(work / "source", root=work)
        plain_path(work / "module-stage", root=work)
        script = plain_path(work / "configure-module.ps1", root=work)
        configure = module_configure_arguments(work, stock, tools)
        require(script.read_bytes() == module_configure_script(configure), "CompilerConfigureScriptChanged")
        wrapper = plain_path(stock / "bin/qt-configure-module.bat", root=stock)
        inputs.update({str(script): file_identity(script), str(wrapper): file_identity(wrapper)})
        expected = [tools["pwsh.exe"], "-NoLogo", "-NoProfile", "-NonInteractive", "-File", script]
        expected_cwd = build
    elif phase == "comparison:01-configure-fixtures":
        source = plain_path(repo / "tools/repros/qt612-popup-gc", root=repo)
        expected = fixture_configure_arguments(repo, work, stock, tools)
        expected_cwd = work
    else:
        source = (plain_path(work / "source", root=work) if phase.startswith("sdk:")
                  else plain_path(repo / "tools/repros/qt612-popup-gc", root=repo))
        targets = ["Qml", "BuiltinsOutput"] if phase.startswith("sdk:") else ["PopupGcFixture", "SweepSlotsProbe"]
        expected = [tools["cmake.exe"], "--build", build, "--target", *targets, "--parallel", "2"]
        expected_cwd = work
    args = [str(x) for x in arguments]
    require(args == [str(x) for x in expected] and plain_path(Path(cwd)) == expected_cwd,
            "CompilerPhaseInvocationMismatch")
    require((source / "CMakeLists.txt").is_file(), "CompilerSourceRootMissing")
    for name in ("cmake.exe", "pwsh.exe", "cl.exe", "link.exe", "lib.exe", "rc.exe", "mt.exe", "ninja.exe"):
        path = plain_path(Path(tools[name]))
        identity = {"path": str(path), **file_identity(path)}
        require(identity == tool_identities.get(name), "CompilerToolIdentityChanged:" + name)
        inputs[str(path)] = {k: identity[k] for k in ("bytes", "sha256")}
    pin = lock.get("compiler_retirement", {})
    require(pin.get("kind") == "one-owned-pinned-msvc-vctip" and pin.get("image") == "vctip.exe"
            and pin.get("maximum_survivors") == 1 and pin.get("grace_seconds") == 2
            and pin.get("proof_seconds") == 5 and 0 < pin.get("bytes", 0) <= 16 * 1024**2
            and SHA.fullmatch(pin.get("sha256", ""))
            and re.fullmatch(r"14\.[0-9]+\.[0-9]+", pin.get("msvc_tools_version", "")),
            "InvalidCompilerRetirementPin")
    cl = plain_path(Path(tools["cl.exe"]))
    require(tuple(x.casefold() for x in cl.parts[-6:]) == (
                "msvc", pin["msvc_tools_version"].casefold(), "bin", "hostx64", "x64", "cl.exe"),
            "CompilerRetirementToolsetMismatch")
    helper = plain_path(cl.parent / "vctip.exe")
    key = str(helper).replace("\\", "/").casefold()
    expected_helper = {"path": str(helper), "bytes": pin["bytes"], "sha256": pin["sha256"]}
    require(known_executables.get(key) == expected_helper,
            "CompilerHelperNotInPrelaunchInventory")
    require(file_identity(helper) == {k: pin[k] for k in ("bytes", "sha256")}, "CompilerHelperPinMismatch")
    return {"phase": phase, "name": phase.split(":", 1)[1], "arguments": args,
            "cwd": str(expected_cwd), "source": str(source), "build": str(build),
            "inputs": inputs, "helper": expected_helper, "policy": pin,
            "actual_process_module_sampling": False}


def compiler_retirement_prerequisites(record):
    first = record.get("root_first_signal") or {}
    return (record.get("atomic_job_membership") is True and record.get("process_signaled") is True
            and not record.get("errors") and record.get("timed_out") is False
            and record.get("forced_cleanup") is False and record.get("exit_code") == 0
            and first.get("exit_code") == 0 and first.get("before_any_termination") is True)


def _windows_image_path(value):
    if value.startswith("\\\\?\\"):
        value = value[4:]
    require(re.match(r"^[A-Za-z]:[\\/]", value) is not None
            and not any(x in value for x in "\0\r\n"), "NonLocalCompilerImagePath")
    return value


class _PinnedCompilerImage:
    """An exact prelaunch image, kept open without write/delete sharing until retirement."""
    def __init__(self, k, c, w, expected):
        self.k, self.c, self.w, self.expected, self.handle = k, c, w, expected, None
        class FileTime(c.Structure):
            _fields_ = [("low", w.DWORD), ("high", w.DWORD)]
        class FileInfo(c.Structure):
            _fields_ = [("attributes", w.DWORD), ("creation", FileTime), ("access", FileTime),
                        ("write", FileTime), ("volume", w.DWORD), ("size_high", w.DWORD),
                        ("size_low", w.DWORD), ("links", w.DWORD), ("id_high", w.DWORD), ("id_low", w.DWORD)]
        class FileId(c.Structure):
            _fields_ = [("volume", c.c_ulonglong), ("identifier", c.c_ubyte * 16)]
        self.FileInfo, self.FileId = FileInfo, FileId
        require((c.sizeof(FileTime), c.sizeof(FileInfo), c.sizeof(FileId)) == (8, 52, 24)
                and FileInfo.volume.offset == 28 and FileId.identifier.offset == 8,
                "CompilerImageFileAbiMismatch")
        for name, result, args in (
                ("CreateFileW", w.HANDLE, [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]),
                ("GetFileType", w.DWORD, [w.HANDLE]),
                ("GetFileInformationByHandle", w.BOOL, [w.HANDLE, c.POINTER(FileInfo)]),
                ("GetFileInformationByHandleEx", w.BOOL, [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]),
                ("GetFinalPathNameByHandleW", w.DWORD, [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]),
                ("CloseHandle", w.BOOL, [w.HANDLE]),
                ("SetFilePointerEx", w.BOOL, [w.HANDLE, c.c_longlong, c.POINTER(c.c_longlong), w.DWORD]),
                ("ReadFile", w.BOOL, [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p])):
            getattr(k, name).restype, getattr(k, name).argtypes = result, args
        try:
            self.handle = self.open(expected["path"])
            self.identity = self.read_identity(self.handle)
            require(self.identity["path_key"] == expected["path"].replace("\\", "/").casefold(),
                    "CompilerImageCanonicalPathMismatch")
            require({key: self.identity[key] for key in ("bytes", "sha256")}
                    == {key: expected[key] for key in ("bytes", "sha256")}, "CompilerImageLockedBytesMismatch")
        except BaseException:
            if self.handle:
                if not k.CloseHandle(self.handle):
                    raise RuntimeError("CompilerImageCloseAfterPinFailure:" + str(c.get_last_error()))
                self.handle = None
            raise

    def open(self, path):
        handle = self.k.CreateFileW(str(plain_path(Path(path))), 0x80000000, 1, None, 3, 0x00200000, None)
        require(bool(handle) and handle != self.c.c_void_p(-1).value,
                "CompilerImageReadLockFailed:" + str(self.c.get_last_error()))
        return handle

    def read_identity(self, handle):
        k, c, w = self.k, self.c, self.w
        info, identifier = self.FileInfo(), self.FileId()
        require(k.GetFileType(handle) == 1, "CompilerImageIsNotDiskFile")
        require(k.GetFileInformationByHandle(handle, c.byref(info))
                and k.GetFileInformationByHandleEx(handle, 18, c.byref(identifier), c.sizeof(identifier)),
                "CompilerImageFileIdentityUnavailable")
        require(not info.attributes & (0x10 | 0x400) and info.links > 0
                and identifier.volume != 0 and any(identifier.identifier), "CompilerImageFileIdentityInvalid")
        size = (info.size_high << 32) | info.size_low
        require(size == self.expected["bytes"], "CompilerImageLockedSizeMismatch")
        path = c.create_unicode_buffer(32768)
        length = k.GetFinalPathNameByHandleW(handle, path, len(path), 0)
        require(0 < length < len(path), "CompilerImageFinalPathUnavailable")
        canonical = plain_path(Path(_windows_image_path(path.value)))
        position = c.c_longlong()
        require(k.SetFilePointerEx(handle, 0, c.byref(position), 0) and position.value == 0,
                "CompilerImageSeekFailed")
        hashed, count, buffer = hashlib.sha256(), 0, c.create_string_buffer(65536)
        while count <= size:
            received = w.DWORD()
            wanted = min(len(buffer), size + 1 - count)
            require(k.ReadFile(handle, buffer, wanted, c.byref(received), None), "CompilerImageReadFailed")
            require(received.value <= wanted, "CompilerImageReadCountInvalid")
            if not received.value:
                break
            hashed.update(buffer.raw[:received.value])
            count += received.value
        require(count == size, "CompilerImageReadSizeMismatch")
        return {"path_key": str(canonical).replace("\\", "/").casefold(),
                "volume_serial": identifier.volume, "file_id_128": bytes(identifier.identifier).hex(),
                "attributes": info.attributes, "links": info.links, "bytes": count,
                "sha256": hashed.hexdigest(), "share_mode": "FILE_SHARE_READ only"}

    def validate_process_image(self, path):
        # Keep the prelaunch handle open while checking the live process's image path.
        canonical = plain_path(Path(_windows_image_path(path)))
        require(str(canonical).replace("\\", "/").casefold() == self.identity["path_key"],
                "CompilerProcessImagePathMismatch")
        require(self.read_identity(self.handle) == self.identity, "CompilerPinnedImageChanged")
        other = self.open(canonical)
        try:
            require(self.read_identity(other) == self.identity, "CompilerProcessImageIdentityMismatch")
        finally:
            require(self.k.CloseHandle(other), "CompilerImageAliasHandleCloseFailed")


_COMPILER_PHASE_FACTORY = object()


class _CompilerPhase:
    def __init__(self, token, plan, environment):
        require(token is _COMPILER_PHASE_FACTORY, "CompilerCapabilityFactoryRequired")
        self.plan = json.loads(json.dumps(plan))
        self.plan_id = canonical_digest(self.plan)
        self.environment_id = canonical_digest(environment)
        self.image, self.process, self.started, self.targeted, self.proved = None, None, False, False, False
        self.creation, self.root_creation, self.k, self.c, self.w = None, None, None, None, None
        self.proof = {"scope": "one exact owned MSVC telemetry image in a compiler phase only",
                      "method": None, "targeted_termination_called": False, "helper_signaled": False,
                      "helper_exit_code": None, "proved_within_original_deadline": False,
                      "accepted": False, "actual_process_module_sampling": False}

    def begin(self, k, c, w, arguments, cwd, name, environment):
        require(not self.started and canonical_digest(self.plan) == self.plan_id
                and canonical_digest(environment) == self.environment_id
                and self.plan["arguments"] == arguments and self.plan["cwd"] == str(cwd)
                and self.plan["name"] == name, "CompilerCapabilityBindingChanged")
        for path, expected in self.plan["inputs"].items():
            require(file_identity(Path(path)) == expected, "CompilerInputChangedBeforeLaunch:" + path)
        require(environment.get("VCTOOLSVERSION") == self.plan["policy"]["msvc_tools_version"],
                "CompilerEnvironmentToolsetChanged")
        self.k, self.c, self.w, self.started = k, c, w, True
        self.image = _PinnedCompilerImage(k, c, w, self.plan["helper"])

    def creation_time(self, handle):
        c, w = self.c, self.w
        class FileTime(c.Structure):
            _fields_ = [("low", w.DWORD), ("high", w.DWORD)]
        require(c.sizeof(FileTime) == 8, "CompilerProcessTimeAbiMismatch")
        values = [FileTime() for _ in range(4)]
        require(self.k.GetProcessTimes(handle, *[c.byref(x) for x in values]), "CompilerProcessTimesFailed")
        value = (values[0].high << 32) | values[0].low
        require(value > 0, "CompilerProcessCreationTimeMissing")
        return value

    def bind_root(self, handle):
        self.root_creation = self.creation_time(handle)

    def inspect_process(self, job, handle, observation=None):
        k, c, w = self.k, self.c, self.w
        observation = {} if observation is None else observation
        member = w.BOOL()
        require(k.IsProcessInJob(handle, job, c.byref(member)) and member.value,
                "CompilerHelperNotInOwnedJob")
        observation["owned_job_membership_confirmed"] = True
        creation = self.creation_time(handle)
        observation["creation_filetime"] = creation
        require(creation >= self.root_creation, "CompilerHelperPredatesOwnedCommand")
        state = k.WaitForSingleObject(handle, 0)
        require(state in (0, 258), "CompilerHelperWaitFailed")
        observation["state"] = "still-active" if state == 258 else "exited-before-inspection"
        size, buffer = w.DWORD(32768), c.create_unicode_buffer(32768)
        require(k.QueryFullProcessImageNameW(handle, 0, buffer, c.byref(size)), "CompilerHelperImageQueryFailed")
        path_hash = hashlib.sha256(buffer.value.replace("\\", "/").casefold().encode()).hexdigest()
        observation.update(executable_basename=Path(buffer.value).name, absolute_path_sha256=path_hash,
                           path_hash_encoding="forward-slash/casefold/UTF-8")
        self.image.validate_process_image(buffer.value)
        return creation, state, path_hash

    def capture(self, job, result):
        k, c, w = self.k, self.c, self.w
        class PidList(c.Structure):
            _fields_ = [("assigned", w.DWORD), ("count", w.DWORD), ("pids", c.c_size_t * 256)]
        require(c.sizeof(PidList) == 2056, "CompilerPidListAbiMismatch")
        values = PidList()
        result.update(utc=utc(), capacity=256, query_count=1, complete_pid_list=False,
                      processes=[], errors=[], command_line_or_environment_read=False,
                      actual_process_module_sampling=False, diagnostic_budget_seconds=1,
                      diagnostic_budget_scope="cooperative snapshot; separate from 5-second exit proof")
        deadline = time.monotonic() + 1
        require(k.QueryInformationJobObject(job, 3, c.byref(values), c.sizeof(values), None),
                "CompilerOwnedPidQueryFailed")
        result.update(assigned_count=values.assigned, listed_count=values.count)
        require(values.count <= 256 and values.assigned == values.count, "CompilerOwnedPidListIncomplete")
        result["complete_pid_list"] = True
        result["listed_pids"] = [int(x) for x in values.pids[:values.count]]
        require(values.count == 1, "CompilerRetirementRequiresExactlyOneSurvivor")
        pid = values.pids[0]
        item = {"pid": pid, "state": "not-inspected"}
        result["processes"].append(item)
        require(0 < pid <= 0xffffffff and self.process is None, "CompilerOwnedPidInvalid")
        self.process = k.OpenProcess(0x1000 | 0x100000 | 0x0001, False, pid)
        require(bool(self.process), "CompilerHelperOpenFailed:" + str(c.get_last_error()))
        item["same_process_handle_retained_for_termination"] = True
        creation, state, path_hash = self.inspect_process(job, self.process, item)
        self.creation = creation
        require(time.monotonic() < deadline, "CompilerHelperSnapshotBudgetExceeded")
        item.update(state="still-active" if state == 258 else "exited-before-inspection",
                    owned_job_membership_confirmed=True, creation_filetime=creation,
                    absolute_path_sha256=path_hash, path_hash_encoding="forward-slash/casefold/UTF-8",
                    matched_inventory_path=self.plan["helper"]["path"],
                    pinned_file_identity=self.image.identity,
                    same_process_handle_retained_for_termination=True)
        self.proof.update(pid=pid, creation_filetime=creation, file_identity=self.image.identity)
        result["completed"] = True

    def terminate(self, job, record, deadline):
        require(compiler_retirement_prerequisites(record) and self.process is not None,
                "CompilerRetirementPrerequisitesMissing")
        creation, state, path_hash = self.inspect_process(job, self.process)
        require(creation == self.creation and time.monotonic() < deadline,
                "CompilerHelperIdentityOrDeadlineChanged")
        self.proof.update(rechecked_creation_filetime=creation, rechecked_path_sha256=path_hash)
        if state == 0:
            self.proof["method"] = "identified-helper-exited-before-targeted-termination"
            return
        self.targeted = True
        record.update(forced_cleanup=True, termination_reason="controlled-pinned-compiler-helper",
                      termination_utc=utc())
        self.proof.update(method="TerminateProcess on retained verified process handle",
                          targeted_termination_called=True, requested_exit_code=125)
        result = bool(self.k.TerminateProcess(self.process, 125))
        self.proof["terminate_process_returned"] = result
        require(result, "CompilerHelperTerminationFailed:" + str(self.c.get_last_error()))

    def prove(self, record, deadline):
        require(self.process is not None and deadline is not None and time.monotonic() < deadline,
                "CompilerHelperExitProofExpired")
        state, code = self.k.WaitForSingleObject(self.process, 0), self.w.DWORD()
        self.proof.update(helper_wait_result=state, helper_signaled=state == 0)
        require(state == 0, "CompilerHelperActualExitUnconfirmed")
        queried = bool(self.k.GetExitCodeProcess(self.process, self.c.byref(code)))
        self.proof["helper_exit_code_query_succeeded"] = queried
        if queried:
            self.proof["helper_exit_code"] = code.value
        require(queried, "CompilerHelperActualExitUnconfirmed")
        creation = self.creation_time(self.process)
        self.proof["exit_creation_filetime"] = creation
        require(creation == self.creation, "CompilerHelperExitIdentityChanged")
        if self.targeted:
            require(code.value == 125, "CompilerHelperTerminationExitCodeChanged")
        require(record["process_signaled"] and record["owned_job_empty"]
                and record["exit_code"] == 0 and not record["errors"] and not record["timed_out"],
                "CompilerRootOrOwnedJobExitUnconfirmed")
        self.proof.update(helper_signaled=True, helper_exit_code=code.value,
                          proved_within_original_deadline=True, proof_utc=utc())
        self.proved = True

    def close(self, record):
        operations = []
        if self.process:
            handle, self.process = self.process, None
            operations.append(("CompilerHelperHandleCloseFailed", lambda: self.k.CloseHandle(handle)))
        if self.image and self.image.handle:
            image, self.image.handle = self.image.handle, None
            operations.append(("CompilerImageHandleCloseFailed", lambda: self.k.CloseHandle(image)))
        close_command_resources(operations, record)


def compiler_completion_allowed(record, capability):
    # No JSON receipt boolean can create the live proof held by this invocation.
    if command_completion_allowed(record, (0,)):
        return True
    first = record.get("root_first_signal") or {}
    return (type(capability) is _CompilerPhase and capability.proved and capability.targeted
            and record.get("atomic_job_membership") is True and record.get("process_signaled") is True
            and record.get("owned_job_empty") is True and not record.get("errors")
            and record.get("timed_out") is False and record.get("exit_code") == 0
            and record.get("forced_cleanup") is True
            and record.get("termination_reason") == "controlled-pinned-compiler-helper"
            and first.get("before_any_termination") is True and first.get("exit_code") == 0)


def run_compiler_logged(phase, arguments, cwd, evidence, timeout, *, context, lock,
                        tool_identities, known_executables, env):
    plan = compiler_phase_plan(phase, arguments, cwd, context, lock, tool_identities, known_executables)
    capability = _CompilerPhase(_COMPILER_PHASE_FACTORY, plan, env)
    write_json(Path(evidence) / (plan["name"] + ".compiler-plan.json"), plan)
    return _run_logged(arguments, cwd, evidence, plan["name"], timeout, env=env,
                       known_executables=known_executables, compiler=capability)


def owned_pid_snapshot(k, c, w, job, known_executables):
    """One bounded Job PID query; inspect only handles re-confirmed in this exact Job."""
    class PidList(c.Structure):
        _fields_ = [("assigned", w.DWORD), ("count", w.DWORD), ("pids", c.c_size_t * 256)]
    class FileTime(c.Structure):
        _fields_ = [("low", w.DWORD), ("high", w.DWORD)]
    require(c.sizeof(PidList) == 2056 and c.sizeof(FileTime) == 8, "OwnedPidSnapshotAbiMismatch")
    result = {"utc": utc(), "capacity": 256, "query_count": 1, "complete_pid_list": False,
              "processes": [], "errors": [], "command_line_or_environment_read": False,
              "actual_process_module_sampling": False}
    values = PidList()
    if not k.QueryInformationJobObject(job, 3, c.byref(values), c.sizeof(values), None):
        result["errors"].append("OwnedPidQueryFailed:" + str(c.get_last_error()))
        return result
    result.update(assigned_count=values.assigned, listed_count=values.count)
    if values.count > 256 or values.assigned != values.count:
        result["errors"].append("OwnedPidListIncompleteOrInvalid")
        return result
    result["complete_pid_list"] = True
    deadline, hashed_bytes = time.monotonic() + 1, 0
    for pid in values.pids[:values.count]:
        item = {"pid": pid, "state": "not-inspected"}
        result["processes"].append(item)
        if not 0 < pid <= 0xffffffff:
            item["state"] = "invalid-pid-list-entry"
            result["errors"].append("OwnedPidListEntryInvalid")
            continue
        if time.monotonic() >= deadline:
            item["state"] = "snapshot-time-budget-exhausted"
            continue
        handle = k.OpenProcess(0x1000 | 0x100000, False, pid)  # Query-limited + synchronize.
        if not handle:
            item.update(state="cannot-open; exit-not-proved", win32_error=c.get_last_error())
            continue
        try:
            member = w.BOOL()
            if not k.IsProcessInJob(handle, job, c.byref(member)):
                item.update(state="membership-unconfirmed", win32_error=c.get_last_error())
                continue
            if not member.value:
                item["state"] = "not-in-owned-job; no-further-inspection"
                continue
            item["owned_job_membership_confirmed"] = True
            state = k.WaitForSingleObject(handle, 0)
            item["state"] = "exited-before-inspection" if state == 0 else (
                "still-active" if state == 258 else "wait-failed")
            creation, exit_time, kernel, user = FileTime(), FileTime(), FileTime(), FileTime()
            if k.GetProcessTimes(handle, c.byref(creation), c.byref(exit_time),
                                 c.byref(kernel), c.byref(user)):
                item["creation_filetime"] = (creation.high << 32) | creation.low
            else:
                item["creation_time_error"] = c.get_last_error()
            size, buffer = w.DWORD(32768), c.create_unicode_buffer(32768)
            if not k.QueryFullProcessImageNameW(handle, 0, buffer, c.byref(size)):
                item["image_query_error"] = c.get_last_error()
                continue
            normalized = buffer.value.replace("\\", "/").casefold()
            item.update(executable_basename=Path(buffer.value).name,
                        absolute_path_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                        path_hash_encoding="forward-slash/casefold/UTF-8")
            known = known_executables.get(normalized)
            if known is not None:
                item["matched_inventory_path"] = known["path"]  # Already public in tool inventory.
                expected = {key: known[key] for key in ("bytes", "sha256")}
                item["inventory_identity"] = expected
                if (time.monotonic() < deadline and expected["bytes"] <= 16 * 1024**2
                        and hashed_bytes + expected["bytes"] <= 32 * 1024**2):
                    image_path = plain_path(Path(buffer.value))
                    with image_path.open("rb") as stream:
                        data = stream.read(expected["bytes"] + 1)
                    hashed_bytes += len(data)
                    if len(data) != expected["bytes"]:
                        item.update(observed_read_bytes=len(data), inventory_hash_matches=False,
                                    file_hash_status="size-mismatch; no-full-file-hash-claim")
                    else:
                        actual = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                        item.update(observed_file_identity=actual, inventory_hash_matches=actual == expected)
                    if not item["inventory_hash_matches"]:
                        result["errors"].append("OwnedProcessExecutableChanged:" + item["executable_basename"])
                else:
                    item["file_hash_status"] = "snapshot-time-or-byte-budget-exhausted"
        except Exception as error:
            item["inspection_error"] = type(error).__name__ + ":" + str(error)
        finally:
            if not k.CloseHandle(handle):
                result["errors"].append("OwnedPidHandleCloseFailed:" + str(c.get_last_error()))
    return result


def command_completion_allowed(record, accepted):
    first = record.get("root_first_signal") or {}
    return (record["atomic_job_membership"] and record["process_signaled"] and record["owned_job_empty"]
            and not record["errors"] and not record["timed_out"]
            and first.get("before_any_termination") is True
            and first.get("exit_code") == record["exit_code"]
            and record["exit_code"] in accepted
            and not (record["forced_cleanup"] and record["exit_code"] == 0))


def close_command_resources(operations, record):
    """A failed stream or handle close must not skip the remaining owned handles."""
    for label, close in operations:
        try:
            result = close()
            if result is not None and not result:
                record["errors"].append(label + ":ReturnedFalse")
        except Exception as error:
            record["errors"].append(label + ":" + type(error).__name__ + ":" + str(error))


def collect_command_output_evidence(paths, record):
    record["outputs"] = {}
    for path in paths:
        try:
            record["outputs"][path.name] = file_identity(path)
        except Exception as error:
            record["errors"].append("CommandOutputEvidenceFailed:" + path.name + ":"
                                    + type(error).__name__ + ":" + str(error))



# Fixed-target product comparison. This capability cannot retire compiler helpers
# or change generic/private completion rules. It only observes this Job.
_PRODUCT_FACTORY = object()
PRODUCT_HEAD = "d136505cb1ac8cfeb5b80c554daebbbb06ff1aa9"
PRODUCT_MERGE = "e76d264b9b5dfe1f1becdbef7dc8fceb3506a0ab"
PRODUCT_MANIFEST_PIN = {"bytes": 293662, "sha256": "c3f45626d9d07e87c8726794551f9bce6781e5894fcc3886dbe34a4cb08326be"}
PRODUCT_EXE_PIN = {"bytes": 41496576, "sha256": "cbf97a6b3e41b360d324187e26a4737cda18813e476fef779384fde6c9fc6711"}
PRODUCT_RUST_PIN = {"bytes": 14943232, "sha256": "c4dbee3124188ec265876e280ebd0a319ab36becc2bfbf8f501c50172c1751e4"}
PRODUCT_QML_PINS = {
    "stock": {"bytes": 5390136, "sha256": "2572e315c36d8cea89a5becb910ddccdcf5d34e5421eef1e033187a99b68f84b"},
    "patched": {"bytes": 5377536, "sha256": "66d291c47770c366627cfd68f3e050e30dbb6f1747639f32c6ea812803ad1cb3"},
}
PRODUCT_SMOKE_PIN = {"bytes": 15636, "sha256": "737a840a3816b6599b911240fb47940e609b48f7d3e27030626219c2104b7a97"}
PRODUCT_ASSERT_PIN = {"bytes": 715, "sha256": "6c1912a378711d723184cef60b4330e81931837fa0b11bc8714097a108d953cc"}


def product_manifest(path):
    require(file_identity(path) == PRODUCT_MANIFEST_PIN, "ProductOriginalManifestPinMismatch")
    rows = read_json(path, 1024 * 1024)
    require(type(rows) is list and len(rows) == 1516, "ProductOriginalManifestCount")
    result, folded = {}, set()
    for row in rows:
        require(type(row) is dict and set(row) == {"path", "bytes", "sha256"}, "ProductManifestSchema")
        name = row["path"]
        require(type(name) is str and name and "\\" not in name and ":" not in name
                and not any(ord(c) < 32 for c in name) and not PurePosixPath(name).is_absolute()
                and ".." not in PurePosixPath(name).parts and PurePosixPath(name).as_posix() == name
                and name.casefold() not in folded, "ProductManifestPath")
        require(type(row["bytes"]) is int and 0 <= row["bytes"] <= 128 * 1024**2
                and type(row["sha256"]) is str and SHA.fullmatch(row["sha256"]), "ProductManifestIdentity")
        folded.add(name.casefold())
        result[name] = {k: row[k] for k in ("bytes", "sha256")}
    require(sum(v["bytes"] for v in result.values()) == 210603842, "ProductOriginalManifestBytes")
    require(result.get("Swirl.exe") == PRODUCT_EXE_PIN and result.get("swirl_api.dll") == PRODUCT_RUST_PIN
            and result.get("Qt6Qml.dll") == PRODUCT_QML_PINS["stock"], "ProductOriginalBinaryPins")
    return result


def product_runtime_identity(runtime, manifest, variant):
    require(variant in PRODUCT_QML_PINS, "ProductVariantRejected")
    expected = product_manifest(manifest)
    expected["Qt6Qml.dll"] = PRODUCT_QML_PINS[variant]
    actual = inventory(runtime)
    require(actual == expected, "ProductRuntimeClosureMismatch")
    return actual


def product_case_plan(kind, variant, repository, work, evidence, powershell):
    require(kind in ("full-motion", "node-offscreen", "node-native")
            and variant in PRODUCT_QML_PINS, "ProductCaseRejected")
    repository, work, evidence = map(plain_path, (repository, work, evidence))
    require(repository == plain_path(Path(os.environ["GITHUB_WORKSPACE"]))
            and work.is_relative_to(plain_path(Path(os.environ["RUNNER_TEMP"])))
            and evidence == repository / "build-evidence/qt612-product-comparison",
            "ProductOwnedRootsRequired")
    require(subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"],
                                    text=True).strip() == PRODUCT_MERGE, "ProductTargetSourceMismatch")
    subprocess.run(["git", "-C", str(repository), "diff", "--quiet", "HEAD", "--"], check=True)
    unexpected = subprocess.check_output(["git", "-C", str(repository), "ls-files", "--others",
                                         "--exclude-standard", "--", "src", "core", "scripts", "tools", ".github"],
                                        text=True)
    require(not unexpected.strip(), "ProductUntrackedInputs")
    manifest = work / "inputs/runtime-before.json"
    runtime = work / "runtimes" / variant
    product_runtime_identity(runtime, manifest, variant)
    reference = repository / "build/swirl-quick/Release/Swirl.exe"
    require(file_identity(reference) == PRODUCT_EXE_PIN, "ProductCachedReferenceMismatch")
    require(file_identity(repository / "scripts/tests/Test-WindowsFullMotionSmoke.ps1") == PRODUCT_SMOKE_PIN
            and file_identity(repository / "scripts/Assert-BuildSource.ps1") == PRODUCT_ASSERT_PIN,
            "ProductOriginalDriverChanged")
    scratch = work / "processes" / (variant + "-" + kind)
    require(not scratch.exists(), "ProductFreshProcessRootRequired")
    scratch.mkdir(parents=True)
    output = evidence / variant / kind
    require(not output.exists(), "ProductFreshEvidenceRequired")
    environment = tool_environment()
    # The inherited host's proxy, private config, Qt choices and tokens are absent.
    for key in list(environment):
        if key.startswith(("QT_", "QML_", "QSG_", "SWIRL_")):
            environment.pop(key)
    environment.update(QT_FORCE_STDERR_LOGGING="1", QT_MESSAGE_PATTERN="[%{type}] %{message}")
    inputs = {str(reference): PRODUCT_EXE_PIN, str(manifest): PRODUCT_MANIFEST_PIN}
    if kind == "full-motion":
        shell = plain_path(Path(powershell))
        require(shell == plain_path(Path(os.environ["ProgramFiles"]) / "PowerShell/7/pwsh.exe"),
                "ProductSystemPowerShell7Required")
        script = repository / "scripts/tests/Test-WindowsFullMotionSmoke.ps1"
        arguments = [str(shell), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script),
                     "-RepositoryRoot", str(repository), "-RuntimeDirectory", str(runtime),
                     "-ReferenceExecutable", str(reference), "-OutputDirectory", str(output),
                     "-ScratchRoot", str(scratch), "-WorkflowSha", PRODUCT_MERGE,
                     "-PullRequestHeadSha", PRODUCT_HEAD, "-ExpectedFlavor", "qa"]
        inputs[str(shell)] = file_identity(shell)
        inputs[str(script)] = PRODUCT_SMOKE_PIN
        inputs[str(repository / "scripts/Assert-BuildSource.ps1")] = PRODUCT_ASSERT_PIN
        timeout, accepted, app = 240, (0, 1), None
    else:
        app = scratch / "app"
        shutil.copytree(runtime, app)
        product_runtime_identity(app, manifest, variant)
        profile = scratch / "profile"
        (profile / "tmp").mkdir(parents=True)
        output.mkdir(parents=True)
        arguments = [str(app / "Swirl.exe"), "--node-self-test"]
        environment.update(SWIRL_TEST_ROOT=str(profile), SWIRL_UI_QA_DIRECTORY=str(output),
                           TEMP=str(profile / "tmp"), TMP=str(profile / "tmp"), TMPDIR=str(profile / "tmp"),
                           QML_DISK_CACHE_PATH=str(profile / "qml-cache"),
                           QT_QPA_FONTDIR=str(app / "lib/fonts"))
        if kind == "node-offscreen":
            environment.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
        else:
            environment.update(QT_QPA_PLATFORM="windows", QSG_RHI_BACKEND="d3d11",
                               QT_SCALE_FACTOR="1.5", SWIRL_NODE_UI_REQUIRE_NATIVE="1")
        inputs[str(app / "Swirl.exe")] = PRODUCT_EXE_PIN
        inputs[str(app / "Qt6Qml.dll")] = PRODUCT_QML_PINS[variant]
        timeout, accepted = 180, (0, 2)
    return {"kind": kind, "variant": variant, "arguments": arguments, "cwd": str(repository),
            "name": kind, "timeout": timeout, "accepted": list(accepted), "inputs": inputs,
            "runtime": str(runtime), "manifest": str(manifest), "scratch": str(scratch),
            "app": str(app) if app else None, "output": str(output)}, environment


class _ProductPhase:
    def __init__(self, token, plan, environment):
        require(token is _PRODUCT_FACTORY, "LiveProductCapabilityRequired")
        self.plan = json.loads(json.dumps(plan))
        self.plan_id, self.environment_id = canonical_digest(plan), canonical_digest(environment)
        self.accepted = tuple(plan["accepted"])
        self.started, self.observations, self.handles, self.pins = False, {}, {}, []
        self.root_creation, self.k, self.c, self.w = None, None, None, None
        self.proof = {"scope": "Fixed d136 QA product in this owned Job only",
                      "target_source_sha": PRODUCT_MERGE, "target_pr_head_sha": PRODUCT_HEAD,
                      "case": plan["kind"], "variant": plan["variant"], "observations": [],
                      "module_query_attempts": 0, "owned_job_queries": 0, "transient_errors": [],
                      "actual_process_module_sampling": False, "memory_bytes_hashed": False,
                      "complete": False, "font_file_uploaded": False}

    def begin(self, k, c, w, arguments, cwd, name, environment):
        require(not self.started and canonical_digest(self.plan) == self.plan_id
                and canonical_digest(environment) == self.environment_id
                and self.plan["arguments"] == arguments and self.plan["cwd"] == str(cwd)
                and self.plan["name"] == name, "ProductCapabilityBindingChanged")
        for path, expected in self.plan["inputs"].items():
            require(file_identity(Path(path)) == expected, "ProductInputChangedBeforeLaunch:" + path)
        product_runtime_identity(Path(self.plan["runtime"]), Path(self.plan["manifest"]), self.plan["variant"])
        self.k, self.c, self.w, self.started = k, c, w, True
        class PidList(c.Structure):
            _fields_ = [("assigned", w.DWORD), ("count", w.DWORD), ("pids", c.c_size_t * 256)]
        class FileTime(c.Structure):
            _fields_ = [("low", w.DWORD), ("high", w.DWORD)]
        class ModuleInfo(c.Structure):
            _fields_ = [("base", c.c_void_p), ("size", w.DWORD), ("entry", c.c_void_p)]
        require(c.sizeof(c.c_void_p) == 8 and c.sizeof(PidList) == 2056
                and c.sizeof(FileTime) == 8 and c.sizeof(ModuleInfo) == 24
                and ModuleInfo.size.offset == 8 and ModuleInfo.entry.offset == 16,
                "ProductModuleObserverAbiMismatch")
        self.PidList, self.FileTime, self.ModuleInfo = PidList, FileTime, ModuleInfo
        self.psapi = c.WinDLL("psapi", use_last_error=True)
        for name, result, types in (
            ("EnumProcessModulesEx", w.BOOL, [w.HANDLE, c.POINTER(w.HMODULE), w.DWORD, c.POINTER(w.DWORD), w.DWORD]),
            ("GetModuleFileNameExW", w.DWORD, [w.HANDLE, w.HMODULE, w.LPWSTR, w.DWORD]),
            ("GetModuleInformation", w.BOOL, [w.HANDLE, w.HMODULE, c.POINTER(ModuleInfo), w.DWORD])):
            function = getattr(self.psapi, name)
            function.restype, function.argtypes = result, types

    def creation(self, handle):
        values = [self.FileTime() for _ in range(4)]
        require(self.k.GetProcessTimes(handle, *[self.c.byref(v) for v in values]), "ProductProcessTimesFailed")
        value = (values[0].high << 32) | values[0].low
        require(value > 0, "ProductProcessCreationMissing")
        return value

    def bind_root(self, handle):
        self.root_creation = self.creation(handle)
        self.proof["root_creation_filetime"] = str(self.root_creation)

    def image_path(self, handle):
        buffer, size = self.c.create_unicode_buffer(32768), self.w.DWORD(32768)
        require(self.k.QueryFullProcessImageNameW(handle, 0, buffer, self.c.byref(size)),
                "ProductProcessImageUnavailable")
        return plain_path(Path(_windows_image_path(buffer.value)))

    def same_job(self, job, handle):
        member = self.w.BOOL()
        require(self.k.IsProcessInJob(handle, job, self.c.byref(member)) and member.value,
                "ProductProcessOutsideOwnedJob")

    def app_role(self, image):
        scratch = plain_path(Path(self.plan["scratch"]))
        relative = image.relative_to(scratch).as_posix() if image.is_relative_to(scratch) else ""
        if self.plan["kind"] == "full-motion":
            match = re.fullmatch(r"swirl-full-motion-[0-9a-f]{32}/(rapid|ready)/app/Swirl\.exe", relative)
            require(match is not None, "ProductUnexpectedSmokeImagePath")
            return match[1]
        require(image == Path(self.plan["app"]) / "Swirl.exe", "ProductUnexpectedNodeImagePath")
        return self.plan["kind"]

    def note_transient(self, code, pid):
        if len(self.proof["transient_errors"]) < 16:
            self.proof["transient_errors"].append({"code": code, "pid": pid, "utc": utc()})

    def pin_file(self, expected):
        # Each pin owns ctypes function objects for its local FileInfo type.
        # Sharing the runner's WinDLL would overwrite earlier pins' argtypes.
        kernel = self.c.WinDLL("kernel32", use_last_error=True)
        pin = _PinnedCompilerImage(kernel, self.c, self.w, expected)
        self.pins.append(pin)
        return pin

    def inspect_modules(self, handle, item):
        c, w = self.c, self.w
        modules, needed = (w.HMODULE * 1024)(), w.DWORD()
        self.proof["module_query_attempts"] += 1
        if not self.psapi.EnumProcessModulesEx(handle, modules, c.sizeof(modules), c.byref(needed), 3):
            self.note_transient("EnumProcessModulesEx:" + str(c.get_last_error()), item["pid"])
            return
        require(0 < needed.value <= c.sizeof(modules) and needed.value % c.sizeof(w.HMODULE) == 0,
                "ProductModuleListIncomplete")
        found = []
        for module in modules[:needed.value // c.sizeof(w.HMODULE)]:
            path_buffer = c.create_unicode_buffer(32768)
            length = self.psapi.GetModuleFileNameExW(handle, module, path_buffer, len(path_buffer))
            if not length:
                self.note_transient("GetModuleFileNameExW:" + str(c.get_last_error()), item["pid"])
                return
            require(length < len(path_buffer), "ProductModulePathTruncated")
            if Path(path_buffer.value).name.casefold() == "qt6qml.dll":
                found.append((module, plain_path(Path(_windows_image_path(path_buffer.value)))))
        if not found:
            return
        require(len(found) == 1, "ProductAmbiguousQtQmlModule")
        module, path = found[0]
        require(path == Path(item["image_path"]).parent / "Qt6Qml.dll", "ProductQtQmlResolvedOutsideFreshApp")
        info = self.ModuleInfo()
        require(self.psapi.GetModuleInformation(handle, module, c.byref(info), c.sizeof(info))
                and info.base and 0 < info.size < 128 * 1024**2, "ProductMappedModuleInfoUnavailable")
        expected = {"path": str(path), **PRODUCT_QML_PINS[self.plan["variant"]]}
        pin = self.pin_file(expected)
        pin.validate_process_image(str(path))
        self.same_job(self.job, handle)
        require(self.creation(handle) == int(item["creation_filetime"]), "ProductPidIdentityChanged")
        item["qt_qml_module"] = {"path": str(path), "base_address": hex(info.base),
                                 "mapped_image_size": info.size, "entry_point": hex(info.entry or 0),
                                 "file": {**pin.identity, "volume_serial": str(pin.identity["volume_serial"])},
                                 "sampled_utc": utc(), "file_handle_held_until_actual_exit": True,
                                 "memory_bytes_hashed": False}
        item["module_proved"] = True
        self.proof["actual_process_module_sampling"] = True

    def poll(self, job):
        self.job = job
        c, w, k = self.c, self.w, self.k
        values = self.PidList()
        require(k.QueryInformationJobObject(job, 3, c.byref(values), c.sizeof(values), None),
                "ProductOwnedPidQueryFailed")
        self.proof["owned_job_queries"] += 1
        require(self.proof["owned_job_queries"] <= 3000 and values.count <= 256
                and values.assigned == values.count, "ProductOwnedPidListIncomplete")
        for pid in values.pids[:values.count]:
            require(0 < pid <= 0xffffffff, "ProductOwnedPidInvalid")
            if pid in self.handles:
                handle = self.handles[pid]
                item = self.observations[pid]
            else:
                handle = k.OpenProcess(0x400 | 0x10 | 0x100000, False, pid)
                if not handle:
                    self.note_transient("OwnedPidExitedBeforeOpen:" + str(c.get_last_error()), int(pid))
                    continue
                retain = False
                try:
                    self.same_job(job, handle)
                    if k.WaitForSingleObject(handle, 0) == 0:
                        continue
                    image = self.image_path(handle)
                    if image.name.casefold() != "swirl.exe":
                        continue
                    creation = self.creation(handle)
                    require(creation >= self.root_creation, "ProductChildPredatesOwnedRoot")
                    role = self.app_role(image)
                    require(role not in [x["role"] for x in self.observations.values()], "ProductDuplicateCaseImage")
                    pin = self.pin_file({"path": str(image), **PRODUCT_EXE_PIN})
                    pin.validate_process_image(str(image))
                    item = {"pid": int(pid), "creation_filetime": str(creation), "role": role,
                            "image_path": str(image), "image_file": {**pin.identity,
                                "volume_serial": str(pin.identity["volume_serial"])},
                            "owned_job_confirmed": True, "module_proved": False,
                            "first_seen_utc": utc(), "first_seen_monotonic": time.monotonic()}
                    self.handles[pid], self.observations[pid] = handle, item
                    self.proof["observations"].append(item)
                    retain = True
                finally:
                    if not retain:
                        require(k.CloseHandle(handle), "ProductUnretainedProcessHandleCloseFailed")
            if not item["module_proved"] and k.WaitForSingleObject(handle, 0) == 258:
                require(time.monotonic() - item["first_seen_monotonic"] <= 5,
                        "ProductQtQmlSamplingDeadlineExceeded")
                self.inspect_modules(handle, item)

    def finish(self, job, record):
        require(record["process_signaled"] and record["owned_job_empty"] and not record["forced_cleanup"]
                and not record["timed_out"], "ProductRootOrJobRetirementUnproved")
        expected = {"rapid", "ready"} if self.plan["kind"] == "full-motion" else {self.plan["kind"]}
        require({v["role"] for v in self.observations.values()} == expected, "ProductActualProcessCoverageIncomplete")
        for pid, handle in self.handles.items():
            item = self.observations[pid]
            # Membership was proved while live; the same retained handle and
            # creation are used for exit proof even after removal from Job accounting.
            require(self.creation(handle) == int(item["creation_filetime"]), "ProductExitCreationChanged")
            code = self.w.DWORD()
            require(self.k.WaitForSingleObject(handle, 0) == 0
                    and self.k.GetExitCodeProcess(handle, self.c.byref(code)), "ProductActualChildExitUnproved")
            item.update(process_signaled=True, actual_exit_code=code.value, exit_proof_utc=utc())
            require(item["module_proved"], "ProductQtQmlModuleUnproved")
        for pin in self.pins:
            pin.validate_process_image(pin.expected["path"])
        self.proof["complete"] = True

    def close(self, record):
        operations = [("ProductProcessHandleCloseFailed:" + str(pid),
                       lambda handle=handle: self.k.CloseHandle(handle)) for pid, handle in self.handles.items()]
        for pin in self.pins:
            if pin.handle:
                handle, pin.handle = pin.handle, None
                operations.append(("ProductFilePinCloseFailed", lambda handle=handle: self.k.CloseHandle(handle)))
        close_command_resources(operations, record)


def run_product_logged(kind, variant, repository, work, evidence, powershell):
    plan, environment = product_case_plan(kind, variant, repository, work, evidence, powershell)
    phase = _ProductPhase(_PRODUCT_FACTORY, plan, environment)
    command_evidence = Path(evidence) / variant / "commands"
    write_json(command_evidence / (kind + ".product-plan.json"), plan)
    return _run_logged(plan["arguments"], repository, command_evidence, kind, plan["timeout"],
                       env=environment, accepted=phase.accepted, product=phase)


def run_logged(arguments, cwd, evidence, name, timeout, *, env=None, accepted=(0,), known_executables=None):
    # The public generic entry point has no compiler-retirement option.
    return _run_logged(arguments, cwd, evidence, name, timeout, env=env, accepted=accepted,
                       known_executables=known_executables)


def _run_logged(arguments, cwd, evidence, name, timeout, *, env=None, accepted=(0,),
                known_executables=None, compiler=None, product=None):
    """Public build commands have their own kill-on-close Job, allowing compiler children.

    This does not reuse or weaken PrivateSubscriptionProcess's one-process/eight-second
    guard. Fixtures still run through that unchanged guard inside the comparison command.
    """
    require(os.name == "nt" and 0 < timeout <= 1200, "InvalidWindowsBuildCommand")
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", name), "InvalidCommandEvidenceName")
    require(compiler is None or (type(compiler) is _CompilerPhase and accepted == (0,)),
            "LiveCompilerCapabilityRequired")
    require(product is None or (type(product) is _ProductPhase and compiler is None
            and accepted == product.accepted), "LiveProductCapabilityRequired")
    import msvcrt
    from ctypes import wintypes as w
    c = ctypes
    k = c.WinDLL("kernel32", use_last_error=True)
    ptr = c.c_void_p
    class Basic(c.Structure):
        _fields_ = [("user", c.c_longlong), ("job", c.c_longlong), ("flags", w.DWORD),
                    ("minws", c.c_size_t), ("maxws", c.c_size_t), ("active", w.DWORD),
                    ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
    class Io(c.Structure):
        _fields_ = [(n, c.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]
    class Limits(c.Structure):
        _fields_ = [("basic", Basic), ("io", Io), ("pm", c.c_size_t), ("jm", c.c_size_t),
                    ("ppm", c.c_size_t), ("pjm", c.c_size_t)]
    class Accounting(c.Structure):
        _fields_ = [(n, c.c_longlong) for n in ("u", "k", "pu", "pk")] + [
            ("faults", w.DWORD), ("total", w.DWORD), ("active", w.DWORD), ("terminated", w.DWORD)]
    class Startup(c.Structure):
        _fields_ = [("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR),
                    ("title", w.LPWSTR)] + [(n, w.DWORD) for n in
                     ("x", "y", "xs", "ys", "xc", "yc", "fill", "flags")] + [
                    ("show", w.WORD), ("rs", w.WORD), ("rb", ptr),
                    ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE)]
    class StartupEx(c.Structure):
        _fields_ = [("startup", Startup), ("attributes", ptr)]
    class Information(c.Structure):
        _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]
    signatures = [
        ("CreateJobObjectW", w.HANDLE, [ptr, w.LPCWSTR]),
        ("SetInformationJobObject", w.BOOL, [w.HANDLE, c.c_int, ptr, w.DWORD]),
        ("QueryInformationJobObject", w.BOOL, [w.HANDLE, c.c_int, ptr, w.DWORD, ptr]),
        ("SetHandleInformation", w.BOOL, [w.HANDLE, w.DWORD, w.DWORD]),
        ("InitializeProcThreadAttributeList", w.BOOL, [ptr, w.DWORD, w.DWORD, c.POINTER(c.c_size_t)]),
        ("UpdateProcThreadAttribute", w.BOOL, [ptr, w.DWORD, c.c_size_t, ptr, c.c_size_t, ptr, ptr]),
        ("DeleteProcThreadAttributeList", None, [ptr]),
        ("CreateProcessW", w.BOOL, [w.LPCWSTR, w.LPWSTR, ptr, ptr, w.BOOL, w.DWORD,
                                  ptr, w.LPCWSTR, c.POINTER(Startup), c.POINTER(Information)]),
        ("IsProcessInJob", w.BOOL, [w.HANDLE, w.HANDLE, c.POINTER(w.BOOL)]),
        ("ResumeThread", w.DWORD, [w.HANDLE]),
        ("WaitForSingleObject", w.DWORD, [w.HANDLE, w.DWORD]),
        ("GetExitCodeProcess", w.BOOL, [w.HANDLE, c.POINTER(w.DWORD)]),
        ("TerminateJobObject", w.BOOL, [w.HANDLE, w.UINT]),
        ("TerminateProcess", w.BOOL, [w.HANDLE, w.UINT]),
        ("OpenProcess", w.HANDLE, [w.DWORD, w.BOOL, w.DWORD]),
        ("GetProcessTimes", w.BOOL, [w.HANDLE, ptr, ptr, ptr, ptr]),
        ("QueryFullProcessImageNameW", w.BOOL, [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]),
        ("CloseHandle", w.BOOL, [w.HANDLE]),
    ]
    for function, result, types in signatures:
        getattr(k, function).restype, getattr(k, function).argtypes = result, types
    require((c.sizeof(Startup), c.sizeof(StartupEx), c.sizeof(Information)) == (104, 112, 24),
            "WindowsCommandAbiMismatch")
    require((c.sizeof(Basic), c.sizeof(Limits), c.sizeof(Accounting)) == (64, 144, 48),
            "WindowsCommandJobAbiMismatch")
    args = [str(x) for x in arguments]
    require(Path(args[0]).is_absolute() and Path(args[0]).is_file(), "AbsoluteCommandRequired")
    require(not any("\0" in a for a in args), "NulCommandArgument")
    command = subprocess.list2cmdline(args)
    require(len(command.encode("utf-16-le")) // 2 < 32767, "CommandLineTooLong")
    environment = tool_environment() if env is None else env
    require(len({x.upper() for x in environment}) == len(environment)
            and all(k1 and "=" not in k1 and "\0" not in k1 and "\0" not in v
                    for k1, v in environment.items()), "InvalidCommandEnvironment")
    block = c.create_unicode_buffer("\0".join(key + "=" + environment[key]
                                    for key in sorted(environment, key=str.upper)) + "\0\0")
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    stdout_path, stderr_path = evidence / (name + ".stdout.log"), evidence / (name + ".stderr.log")
    record = {"schema": 1, "arguments": args, "cwd": str(cwd), "started_utc": utc(),
              "timeout_seconds": timeout, "atomic_job_membership": False, "timed_out": False,
              "process_signaled": False, "owned_job_empty": False, "exit_code": None, "errors": [],
              "root_first_signal": None, "forced_cleanup": False, "termination_reason": None,
              "retirement_grace_seconds": 2, "termination_proof_seconds": 5,
              "owned_pid_snapshot": None, "actual_process_module_sampling": False}
    if compiler is not None:
        record["compiler_phase"] = {"name": compiler.plan["phase"], "plan_content_id": compiler.plan_id,
                                    "environment_content_id": compiler.environment_id}
        record["compiler_controlled_retirement"] = compiler.proof
    if product is not None:
        record["product_phase"] = product.proof
    job, attrs, info = None, None, Information()
    streams, inherited = [], []
    started, terminated, retirement_deadline = time.monotonic(), False, None

    def start_termination_proof():
        nonlocal retirement_deadline
        if retirement_deadline is None:
            retirement_deadline = time.monotonic() + 5
            record.update(termination_proof_started_utc=utc(),
                          termination_proof_deadline_elapsed_seconds=round(retirement_deadline - started, 6))

    def observe_root(state, accounting, observed_by):
        record.update(process_signaled=state == 0, owned_job_empty=accounting.active == 0,
                      last_job_accounting={"active": accounting.active, "total": accounting.total,
                                           "terminated": accounting.terminated})
        if state == 0:
            code = w.DWORD()
            require(k.GetExitCodeProcess(info.process, c.byref(code)), "CommandExitCodeFailed")
            if record["root_first_signal"] is None:
                record["exit_code"] = code.value
                record["root_first_signal"] = {
                    "utc": utc(), "elapsed_seconds": round(time.monotonic() - started, 6),
                    "exit_code": code.value, "job_active_count": accounting.active,
                    "job_total_count": accounting.total, "job_terminated_count": accounting.terminated,
                    "before_any_termination": not terminated, "observed_by": observed_by}
                if not terminated and record["root_first_signal"]["elapsed_seconds"] > timeout:
                    record["timed_out"] = True
                    record["errors"].append("RootExitObservedAfterCommandDeadline")
            else:
                require(record["exit_code"] == code.value, "RootExitCodeChanged")

    def snapshot_once(for_compiler=False):
        if record["owned_pid_snapshot"] is None:
            record["owned_pid_snapshot"] = {"attempted_utc": utc(), "query_count_maximum": 1,
                                             "completed": False}
            if for_compiler:
                result = record["owned_pid_snapshot"]
                compiler.capture(job, result)
            else:
                result = owned_pid_snapshot(k, c, w, job, known_executables or {})
            record["owned_pid_snapshot"] = result
            record["errors"].extend(result["errors"])
    try:
        if product is not None:
            product.begin(k, c, w, args, cwd, name, environment)
        if compiler is not None:
            compiler.begin(k, c, w, args, cwd, name, environment)
            record["compiler_phase"]["prelaunch_image"] = compiler.image.identity
        job = k.CreateJobObjectW(None, None)
        require(bool(job), "CommandJobCreateFailed")
        limits = Limits()
        limits.basic.flags = 0x2000  # Kill on close, without breakaway or a compiler-child limit.
        require(k.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)),
                "CommandJobLimitsFailed")
        streams = [open(os.devnull, "rb"), stdout_path.open("xb"), stderr_path.open("xb")]
        inherited = [msvcrt.get_osfhandle(s.fileno()) for s in streams]
        for handle in inherited:
            require(k.SetHandleInformation(handle, 1, 1), "CommandStdioInheritanceFailed")
        handles, jobs = (w.HANDLE * 3)(*inherited), (w.HANDLE * 1)(job)
        size = c.c_size_t()
        c.set_last_error(0)
        require(not k.InitializeProcThreadAttributeList(None, 2, 0, c.byref(size))
                and c.get_last_error() == 122 and size.value > 0, "CommandAttributeSizeFailed")
        memory = (c.c_size_t * ((size.value + 7) // 8))()
        candidate = c.cast(memory, ptr)
        require(k.InitializeProcThreadAttributeList(candidate, 2, 0, c.byref(size)),
                "CommandAttributeInitFailed")
        attrs = candidate
        for attribute, values in ((0x00020002, handles), (0x0002000D, jobs)):
            require(k.UpdateProcThreadAttribute(attrs, 0, attribute, values, c.sizeof(values), None, None),
                    "CommandAttributeUpdateFailed")
        startup = StartupEx()
        startup.startup.cb, startup.startup.flags = c.sizeof(startup), 0x100
        startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = inherited
        startup.attributes = attrs
        mutable = c.create_unicode_buffer(command)
        require(k.CreateProcessW(args[0], mutable, None, None, True,
                                 0x4 | 0x08000000 | 0x00080000 | 0x400,
                                 block, str(cwd), c.byref(startup.startup), c.byref(info)),
                "AtomicCommandCreateFailed:" + str(c.get_last_error()))
        member = w.BOOL()
        require(k.IsProcessInJob(info.process, job, c.byref(member)) and member.value,
                "AtomicCommandMembershipUnconfirmed")
        record.update(pid=info.pid, atomic_job_membership=True)
        if compiler is not None:
            compiler.bind_root(info.process)
            record["compiler_phase"]["root_creation_filetime"] = compiler.root_creation
        if product is not None:
            product.bind_root(info.process)
        require(k.ResumeThread(info.thread) == 1, "CommandResumeFailed")
        require(k.CloseHandle(info.thread), "CommandThreadCloseFailed")
        info.thread = None
        deadline, grace_deadline = started + timeout, None
        while True:
            state, accounting = k.WaitForSingleObject(info.process, 100), Accounting()
            require(state in (0, 258), "CommandWaitFailed")
            require(k.QueryInformationJobObject(job, 1, c.byref(accounting), c.sizeof(accounting), None),
                    "CommandJobQueryFailed")
            observe_root(state, accounting, "command-loop")
            if product is not None:
                product.poll(job)
            now = time.monotonic()
            require(retirement_deadline is None or now < retirement_deadline,
                    "CommandRetirementUnconfirmed")
            excessive = sum(p.stat().st_size for p in (stdout_path, stderr_path)) > MAX_LOG_BYTES
            if state == 0 and grace_deadline is None:
                grace_deadline = now + 2
            if state == 0 and accounting.active == 0:
                if excessive:
                    record["errors"].append("OutputLimitExceeded")
                if compiler is not None and compiler.process is not None and retirement_deadline is not None:
                    compiler.prove(record, retirement_deadline)
                break
            if not terminated and (excessive or (state != 0 and now >= deadline)
                                   or (state == 0 and now >= grace_deadline)):
                if excessive:
                    reason = "output-limit"
                    record["errors"].append("OutputLimitExceeded")
                elif state != 0:
                    reason = "work-deadline-root-not-exited"
                    record["timed_out"] = True
                    record["errors"].append("CommandDeadlineExceeded")
                else:
                    reason = "root-exited-descendants-after-grace"
                qualified_phase = (compiler is not None and reason == "root-exited-descendants-after-grace"
                                   and compiler_retirement_prerequisites(record))
                snapshot_once(for_compiler=qualified_phase)
                # Root/child exit can race with the snapshot; observe both before termination.
                state = k.WaitForSingleObject(info.process, 0)
                require(state in (0, 258), "PreTerminationRootWaitFailed")
                require(k.QueryInformationJobObject(job, 1, c.byref(accounting), c.sizeof(accounting), None),
                        "PreTerminationJobQueryFailed")
                observe_root(state, accounting, "pre-termination")
                if state == 0 and accounting.active == 0:
                    record["owned_job_empty"] = True
                    continue
                if qualified_phase:
                    require(accounting.active == 1 and compiler_retirement_prerequisites(record),
                            "CompilerResidueChangedBeforeRetirement")
                    record["active_at_termination"] = accounting.active
                    start_termination_proof()
                    compiler.terminate(job, record, retirement_deadline)
                else:
                    record.update(forced_cleanup=True, termination_reason=reason,
                                  termination_utc=utc(), active_at_termination=accounting.active)
                    if state == 0 and record["exit_code"] == 0:
                        record["errors"].append("UnexpectedDescendantsAfterSuccessfulRoot")
                    start_termination_proof()
                    require(k.TerminateJobObject(job, 125), "CommandJobTerminationFailed")
                terminated = True
            require(retirement_deadline is None or time.monotonic() < retirement_deadline,
                    "CommandRetirementUnconfirmed")
            if state == 0:
                time.sleep(0.025)  # A signaled root handle otherwise spins while children retire.
    except BaseException as error:
        record["errors"].append(type(error).__name__ + ":" + str(error))
    finally:
        if info.process and not (record["process_signaled"] and record["owned_job_empty"]):
            if job and record["atomic_job_membership"] and record["owned_pid_snapshot"] is None:
                try:
                    snapshot_once()
                except Exception as error:
                    record["errors"].append("CleanupSnapshot:" + type(error).__name__ + ":" + str(error))
            record["forced_cleanup"] = True
            record["termination_reason"] = record["termination_reason"] or "exception-cleanup"
            terminated = True
            start_termination_proof()
            if not record["atomic_job_membership"] and not k.TerminateProcess(info.process, 125):
                record["errors"].append("UnconfirmedMembershipProcessTerminationFailed")
            if job and not k.TerminateJobObject(job, 125):
                record["errors"].append("CleanupJobTerminationFailed:" + str(c.get_last_error()))
            while job and time.monotonic() < retirement_deadline:
                accounting = Accounting()
                state = k.WaitForSingleObject(info.process, 100)
                if not k.QueryInformationJobObject(job, 1, c.byref(accounting), c.sizeof(accounting), None):
                    record["errors"].append("CleanupJobQueryFailed")
                    break
                try:
                    observe_root(state, accounting, "exception-cleanup")
                except Exception as error:
                    record["errors"].append("CleanupObservation:" + type(error).__name__ + ":" + str(error))
                if state == 0 and accounting.active == 0:
                    record.update(process_signaled=True, owned_job_empty=True)
                    break
                if state == 0:
                    time.sleep(0.025)
        if product is not None:
            try:
                product.finish(job, record)
            except Exception as error:
                record["errors"].append("ProductObservation:" + type(error).__name__ + ":" + str(error))
            finally:
                product.close(record)
                record["actual_process_module_sampling"] = product.proof["actual_process_module_sampling"]
        if attrs:
            k.DeleteProcThreadAttributeList(attrs)
        if compiler is not None:
            compiler.close(record)
        for handle in inherited:
            if not k.SetHandleInformation(handle, 1, 0):
                record["errors"].append("StdioInheritanceResetFailed")
        closes = [("CommandStreamCloseFailed:" + str(index), stream.close)
                  for index, stream in enumerate(streams)]
        closes.extend(("CommandHandleCloseFailed:" + name, lambda handle=handle: k.CloseHandle(handle))
                      for name, handle in (("thread", info.thread), ("process", info.process), ("job", job))
                      if handle)
        close_command_resources(closes, record)
        record.update(finished_utc=utc(), elapsed_seconds=round(time.monotonic() - started, 3))
        collect_command_output_evidence((stdout_path, stderr_path), record)
        if compiler is not None:
            allowed = compiler_completion_allowed(record, compiler)
            compiler.proof["accepted"] = bool(allowed and compiler.targeted and compiler.proved)
            record["compiler_phase"]["completion_accepted"] = allowed
        write_json(evidence / (name + ".json"), record)
    allowed = (command_completion_allowed(record, accepted) if compiler is None
               else compiler_completion_allowed(record, compiler))
    require(allowed, "CommandFailed:" + name)
    return record


def output_text(evidence, name):
    return (Path(evidence) / (name + ".stdout.log")).read_bytes().decode("utf-8", errors="replace").strip()


def parse_exports(text):
    require(len(re.findall(r"\bordinal\s+hint\s+RVA\s+name\b", text)) == 1, "AmbiguousExportTable")
    values = {}
    for line in text.splitlines():
        match = re.match(r"^\s+(\d+)\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]{8}\s+(\S+)", line)
        if not match:
            continue
        ordinal, name = int(match[1]), match[2]
        require(name not in values and name != "[NONAME]", "UnnamedOrDuplicateExport")
        values[name] = ordinal
    require(100 < len(values) <= 50000, "UnexpectedQmlExportCount")
    return values


def parse_dependents(text):
    require("Image has the following dependencies" in text, "MissingDependencyTable")
    names = re.findall(r"^\s+([A-Za-z0-9_.-]+\.dll)\s*$", text, re.MULTILINE | re.IGNORECASE)
    values = sorted({name.casefold() for name in names})
    require(values and len(values) <= 64 and "qt6core.dll" in values, "UnexpectedQmlDependencySet")
    return values


def byte_identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def source_header_stock_bytes(data):
    # The source checkout is independently pinned to exact Git blob bytes. This
    # one-way transform reconstructs the locked Windows archive, not arbitrary
    # input normalization: bare CR, mixed EOL and any other byte change fail.
    require(b"\r" not in data and b"\n" in data, "SourceHeaderMustBeCanonicalLf")
    return data.replace(b"\n", b"\r\n")


def expected_parser_bytes(stock_data, contract):
    require(byte_identity(stock_data) == contract["stock_raw"], "StockParserHeaderPinMismatch")
    require(stock_data.count(b"\r\n") == contract["stock_crlf_count"]
            and stock_data.count(b"\n") == contract["stock_lf_count"], "StockParserEolShapeMismatch")
    old_path = contract["stock_grammar_path"].encode("ascii")
    new_path = contract["build_grammar_path"].encode("ascii")
    expected_lines = [b'#line ' + str(n).encode("ascii") + b' "' + old_path + b'"\n'
                      for n in contract["line_numbers"]]
    require(re.findall(rb'(?m)^#line[^\n]*\n', stock_data) == expected_lines,
            "StockParserLineDirectivesMismatch")
    result = stock_data.replace(b"\r\n", b"\n")
    require(b"\r" not in result, "StockParserUnexpectedCarriageReturn")
    for old_line in expected_lines:
        require(result.count(old_line) == 1, "ParserLineDirectiveNotUnique")
        result = result.replace(old_line, old_line.replace(old_path, new_path))
    require(byte_identity(result) == contract["expected_built_lf"], "ExpectedParserHeaderPinMismatch")
    return result


def preserve_header_input(evidence, flavor, relative, data):
    target = evidence / "header-inputs" / flavor / relative
    plain_path(target, root=evidence, exists=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)


def verify_headers(source, build, stock, lock, evidence):
    result = []
    private = stock / "include/QtQml/6.12.0/QtQml/private"
    source_by_name = {}
    for path in (source / "src").rglob("*.h"):
        source_by_name.setdefault(path.name, []).append(path)
    generated = {
        "qtqml-config_p.h": build / "src/qml/qtqml-config_p.h",
        "qqmljsgrammar_p.h": build / "src/qml/qqmljsgrammar_p.h",
        "qqmljsparser_p.h": build / "src/qml/qqmljsparser_p.h",
        "qtqml-config.h": build / "src/qml/qtqml-config.h",
    }
    require(private.is_dir(), "StockQmlPrivateHeadersMissing")
    paths = list(private.glob("*.h"))
    # Public source headers have the same observed archive EOL contract. Other
    # generated public headers still require exact bytes at module installation.
    paths += [p for p in (stock / "include/QtQml").glob("*.h")
              if p.name in source_by_name or p.name == "qtqml-config.h"]
    for path in sorted(paths):
        relative = path.relative_to(stock).as_posix()
        data = path.read_bytes()
        preserve_header_input(evidence, "stock", relative, data)
        source_path = None
        expected_stock = None
        if path.name in generated:
            candidate = generated[path.name]
            other = candidate.read_bytes()
            preserve_header_input(evidence, "candidate", relative, other)
            expected = data
            method = "exact-generated"
            if path.name == "qqmljsparser_p.h":
                contract = lock["header_identity"]["parser"]
                require(relative == contract["path"], "UnexpectedParserHeaderPath")
                actual_grammar_path = os.path.relpath(source / "src/qml/parser/qqmljs.g",
                                                     build / "src/qml").replace("\\", "/")
                require(actual_grammar_path == contract["build_grammar_path"],
                        "UnexpectedParserGrammarLocation")
                expected = expected_parser_bytes(data, contract)
                method = "pinned-parser-CRLF-and-seven-exact-line-paths"
            preserve_header_input(evidence, "expected-candidate", relative, expected)
            okay = other == expected
        else:
            candidates = source_by_name.get(path.name, [])
            matches = [p for p in candidates if b"\r" not in p.read_bytes()
                       and source_header_stock_bytes(p.read_bytes()) == data]
            candidate = matches[0] if len(matches) == 1 else (candidates[0] if len(candidates) == 1 else None)
            okay = len(matches) == 1
            other = candidate.read_bytes() if candidate else None
            expected = other
            method = "canonical-source-LF-to-stock-CRLF"
            if candidate:
                source_path = candidate.relative_to(source).as_posix()
                preserve_header_input(evidence, "candidate", relative, other)
                expected_stock = source_header_stock_bytes(other)
                preserve_header_input(evidence, "expected-stock", relative, expected_stock)
        result.append({"path": relative, "stock": byte_identity(data), "matched": okay,
                       "candidate": str(candidate) if candidate else None, "method": method,
                       "source_path": source_path, "candidate_raw": byte_identity(other) if other is not None else None,
                       "expected_candidate": byte_identity(expected) if expected is not None else None,
                       "expected_stock": byte_identity(expected_stock) if expected_stock is not None else None})
    return result


def verify_header_contract(review, lock):
    contract = lock["header_identity"]
    require(all(row["matched"] for row in review), "QtQmlPrivateHeaderOrFeatureMismatch")
    mapping = [{k: row[k] for k in ("path", "source_path", "stock", "candidate_raw", "expected_stock")}
               for row in review if row["method"] == "canonical-source-LF-to-stock-CRLF"]
    require(len(review) == contract["header_review_count"] and len(mapping) == contract["source_headers"],
            "QmlHeaderCoverageChanged")
    mapping = sorted(mapping, key=lambda row: row["path"])
    require(canonical_digest(mapping) == contract["source_header_mapping_sha256"],
            "QmlSourceHeaderMappingPinMismatch")
    return {"headers": len(review), "source_headers": len(mapping),
            "source_header_mapping_sha256": canonical_digest(mapping),
            "generated_feature_and_grammar_headers": "exact original bytes",
            "parser": "exact expected bytes from pinned stock; no token or whitespace normalization"}


def permitted_override(path, before, after):
    if before == after:
        return True
    return bool(re.fullmatch(
        r"(?:bin/Qt6Qml\.(?:dll|pdb)|lib/Qt6Qml\.(?:lib|prl|pdb|debug)"
        r"|modules/Qml\.json|lib/cmake/Qt6Qml(?:Private)?/[^/]+"
        r"|mkspecs/modules/qt_lib_qml(?:_private)?\.pri|lib/pkgconfig/Qt6Qml\.pc)", path))


def verify_module_stage(stage, stock, header_review):
    staged = inventory(stage)
    require("bin/Qt6Qml.dll" in staged and "lib/Qt6Qml.lib" in staged,
            "WindowsQmlModuleOutputsMissing")
    changes, retained = [], []
    headers = {row["path"]: row for row in header_review}
    for relative in staged:
        original, changed = stock / relative, stage / relative
        old = original.read_bytes() if original.is_file() else None
        new = changed.read_bytes()
        require(old is not None or permitted_override(relative, None, new),
                "UnexpectedNewModuleFile:" + relative)
        if relative in headers:
            row = headers[relative]
            require(old is not None and row["matched"] and byte_identity(old) == row["stock"]
                    and byte_identity(new) == row["candidate_raw"], "ModuleHeaderChangedAfterReview:" + relative)
            if old != new:
                retained.append(relative)
        else:
            require(permitted_override(relative, old, new), "UnexpectedModuleMetadataOrHeaderChange:" + relative)
        if old != new:
            changes.append(relative)
    require("bin/Qt6Qml.dll" in changes, "QmlRuntimeWasNotRebuilt")
    return staged, changes, retained


def compose_derived_kit(stock, stage, derived, stock_before, staged, retained_headers):
    require(not derived.exists(), "DerivedKitMustBeFresh")
    require(len(set(retained_headers)) == len(retained_headers)
            and all(path.startswith("include/QtQml/") and path in stock_before and path in staged
                    for path in retained_headers), "InvalidRetainedHeaderSet")
    shutil.copytree(stock, derived, copy_function=shutil.copy2)
    for relative in staged:
        if relative in retained_headers or stock_before.get(relative) == staged[relative]:
            continue
        target = derived / relative
        plain_path(target, root=derived, exists=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stage / relative, target)
    derived_files = inventory(derived)
    expected_files = dict(stock_before)
    expected_files.update({path: item for path, item in staged.items() if path not in retained_headers})
    assert_same_tree(expected_files, derived_files)
    return derived_files


def cmake_quote(path):
    value = str(path).replace("\\", "/")
    require(not any(x in value for x in ('"', "\n", "\r", ";", "$", "[", "]")), "UnsafeCmakePath")
    return '"' + value + '"'


def cmake_path_definition(name, path, kind):
    require(re.fullmatch(r"[A-Z][A-Z0-9_]+", name) and kind in ("FILEPATH", "PATH"),
            "InvalidCmakePathDefinition")
    value = str(path).replace("\\", "/")
    require(value and not any(c in value for c in '\0\r\n";$[]'), "UnsafeCmakePathDefinition")
    return "-D" + name + ":" + kind + "=" + value


def ps_quote(value):
    require("\0" not in str(value) and "\r" not in str(value) and "\n" not in str(value),
            "UnsafePowerShellArgument")
    return "'" + str(value).replace("'", "''") + "'"


def tool_paths():
    names = ("git.exe", "pwsh.exe", "cmake.exe", "ninja.exe", "cl.exe", "link.exe", "lib.exe",
             "dumpbin.exe", "rc.exe", "mt.exe")
    result = {}
    for name in names:
        path = shutil.which(name)
        require(path is not None, "MissingTool:" + name)
        result[name] = str(plain_path(Path(path).absolute()))
    result["python.exe"] = str(plain_path(Path(sys.executable).absolute()))
    return result


def native_toolchain_files(tools):
    # Include compiler backends/resource tools plus all selected native header and
    # link-library search directories. Only hashes are published, never these files.
    vs = plain_path(Path(os.environ["VSINSTALLDIR"]))
    windows_kits = plain_path(Path(os.environ["WINDOWSSDKDIR"]).parent)
    selected = {Path(tools[name]).parent for name in ("cl.exe", "link.exe", "rc.exe", "mt.exe")}
    for variable in ("INCLUDE", "LIB"):
        directories = [p for p in os.environ.get(variable, "").split(os.pathsep) if p]
        require(directories, "NativeToolchainSearchPathMissing:" + variable)
        selected.update(Path(p) for p in directories)
    result = {}
    for directory in sorted(selected, key=str):
        directory = plain_path(directory)
        require(directory.is_relative_to(vs) or directory.is_relative_to(windows_kits),
                "NativeToolchainDirectoryOutsideSelectedInstall")
        result[str(directory)] = inventory(directory)
    require("c1xx.dll" in result[str(Path(tools["cl.exe"]).parent)]
            and "c2.dll" in result[str(Path(tools["cl.exe"]).parent)],
            "MsvcCompilerBackendsMissing")
    return result


def cache_values(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([^:#/][^:=]*):[^=]+=(.*)", line)
        if match:
            require(match[1] not in result, "DuplicateCmakeCacheKey")
            result[match[1]] = match[2]
    return result


def compiler_values(text):
    result = dict(re.findall(r'^set\((CMAKE_CXX_COMPILER(?:_ID|_VERSION)?) "([^"]*)"\)',
                             text, re.MULTILINE))
    architectures = re.findall(r'^set\(MSVC_CXX_ARCHITECTURE_ID "?([^"\s)]+)"?\)',
                               text, re.MULTILINE)
    require(len(architectures) == 1, "AmbiguousConfiguredMsvcArchitecture")
    result["MSVC_CXX_ARCHITECTURE_ID"] = architectures[0]
    return result


def version_tuple(value):
    require(re.fullmatch(r"\d+(?:\.\d+){1,3}", value), "UnparseableCompilerVersion")
    return tuple(map(int, value.split(".")))


def module_platform(metadata, expected_targets):
    require(metadata.get("schema_version") == 3 and metadata.get("name") == "Qml"
            and metadata.get("repository") == "qtdeclarative"
            and metadata.get("version") == "6.12.0", "UnexpectedQmlMetadata")
    platforms = metadata.get("platforms")
    require(isinstance(platforms, list) and len(platforms) == 1, "AmbiguousModulePlatform")
    platform = platforms[0]
    require(platform.get("name") == "Windows" and platform.get("compiler_id") == "MSVC"
            and platform.get("targets") == expected_targets,
            "UnexpectedModuleCompilerOrAbi")
    require(version_tuple(platform["compiler_version"])[0] == 19, "UnexpectedMsvcFamily")
    return platform


def verify_stock_qml_metadata(lock, path):
    expected = lock["stock"]["qml_module_json"]
    require(file_identity(path) == {k: expected[k] for k in ("bytes", "sha256")},
            "OfficialQmlMetadataFilePinMismatch")
    metadata = read_json(path, 65536)
    platform = module_platform(metadata, expected["targets"])
    require(platform["compiler_id"] == expected["compiler_id"]
            and platform["compiler_version"] == expected["compiler_version"],
            "OfficialQmlCompilerMetadataPinMismatch")
    return metadata


def verify_cmake_executable(cache, pinned):
    path = plain_path(Path(cache.get("CMAKE_COMMAND", "")))
    require(path == plain_path(Path(pinned["path"])), "ConfiguredCmakePathMismatch")
    actual = file_identity(path)
    require(actual == {k: pinned[k] for k in ("bytes", "sha256")}, "ConfiguredCmakeBytesChanged")
    return {"path": str(path), **actual,
            "cache_version": ".".join(cache.get("CMAKE_CACHE_" + part + "_VERSION", "?")
                                     for part in ("MAJOR", "MINOR", "PATCH"))}


def preserve_configuration_snapshot(build, evidence):
    candidates = [build / name for name in
                  ("CMakeCache.txt", "config.opt", "config.summary", "compile_commands.json",
                   "CMakeFiles/CMakeConfigureLog.yaml", "CMakeFiles/CMakeError.log",
                   "CMakeFiles/CMakeOutput.log")]
    for name in ("CMakeCCompiler.cmake", "CMakeCXXCompiler.cmake", "CMakeRCCompiler.cmake"):
        candidates.extend((build / "CMakeFiles").glob("*/" + name))
    destination = fresh_directory(evidence / "configuration-at-exit", root=evidence)
    result, total = {"files": {}, "absent_optional": []}, 0
    for path in candidates:
        relative = path.relative_to(build).as_posix()
        if not path.exists():
            result["absent_optional"].append(relative)
            continue
        plain_path(path, root=build)
        before = file_identity(path)
        total += before["bytes"]
        require(before["bytes"] <= 32 * 1024**2 and total <= 64 * 1024**2,
                "ConfigurationEvidenceSizeExceeded")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        require(file_identity(target) == before and file_identity(path) == before,
                "ConfigurationEvidenceChangedDuringCopy")
        result["files"][relative] = before
    return result


def verify_configuration(source, build, stock, tools, evidence, lock, pinned_cmake):
    cache = cache_values((build / "CMakeCache.txt").read_text(encoding="utf-8"))
    cmake = verify_cmake_executable(cache, pinned_cmake)
    expected = {"CMAKE_BUILD_TYPE": "Release", "CMAKE_GENERATOR": "Ninja",
                "CMAKE_MSVC_RUNTIME_LIBRARY": "MultiThreadedDLL",
                "CMAKE_POLICY_DEFAULT_CMP0141": "NEW",
                "CMAKE_MSVC_DEBUG_INFORMATION_FORMAT": MSVC_DEBUG_INFORMATION_FORMAT,
                "QT_BUILD_TESTS": "OFF", "QT_BUILD_EXAMPLES": "OFF",
                "QT_BUILD_TOOLS_BY_DEFAULT": "OFF"}
    require(all(cache.get(k) == v for k, v in expected.items()), "UnexpectedBuildConfiguration")
    for key, name in (("CMAKE_C_COMPILER", "cl.exe"), ("CMAKE_CXX_COMPILER", "cl.exe"),
                      ("CMAKE_LINKER", "link.exe"), ("CMAKE_AR", "lib.exe"),
                      ("CMAKE_RC_COMPILER", "rc.exe"), ("CMAKE_MT", "mt.exe")):
        require(Path(cache.get(key, "")).resolve() == Path(tools[name]).resolve(),
                "NativeBuildToolSelectionMismatch:" + key)
    qt_dirs = {k: v for k, v in cache.items() if re.fullmatch(r"Qt6.*_DIR", k)
               and not v.endswith("-NOTFOUND")}
    require({"Qt6_DIR", "Qt6Core_DIR", "Qt6CorePrivate_DIR", "Qt6BuildInternals_DIR"} <= set(qt_dirs),
            "RequiredBuildSdkSelectionMissing")
    for name, value in qt_dirs.items():
        plain_path(Path(value), root=stock)
    configurations = list((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    require(len(configurations) == 1, "AmbiguousConfiguredCompiler")
    text = configurations[0].read_text(encoding="utf-8")
    compiler = compiler_values(text)
    require(compiler.get("CMAKE_CXX_COMPILER_ID") == "MSVC"
            and compiler.get("MSVC_CXX_ARCHITECTURE_ID") == "x64"
            and Path(compiler.get("CMAKE_CXX_COMPILER", "")).resolve() == Path(tools["cl.exe"]).resolve(),
            "ConfiguredCompilerIdentityMismatch")
    stock_platform = module_platform(verify_stock_qml_metadata(lock, stock / "modules/Qml.json"),
                                     lock["stock"]["qml_module_json"]["targets"])
    actual_version = version_tuple(compiler["CMAKE_CXX_COMPILER_VERSION"])
    require(actual_version[0] == 19 and actual_version >= version_tuple(stock_platform["compiler_version"]),
            "ConfiguredMsvcPredatesStockLibrary")
    commands = read_json(build / "compile_commands.json")
    require(isinstance(commands, list) and commands, "CompileCommandsMissing")
    qv4 = [item for item in commands
           if Path(item["file"]).resolve() == (source / "src/qml/memory/qv4mm.cpp").resolve()]
    require(len(qv4) == 1 and "command" in qv4[0], "AmbiguousAllocatorCompileCommand")
    command = qv4[0]["command"]
    require(re.search(r"(?:^|\s)[/-]MD(?:\s|$)", command)
            and not re.search(r"(?:^|\s)[/-](?:MDd|MTd?)(?:\s|$)", command),
            "UnexpectedAllocatorRuntimeLibrary")
    require(re.search(r"(?:^|\s)[/-]DNDEBUG(?:\s|$)", command), "AllocatorIsNotRelease")
    result = {"compiler": compiler, "compiler_file": file_identity(configurations[0]), "cmake": cmake,
              "required_configuration": expected, "qt_directories": qt_dirs,
              "stock_qml_platform": stock_platform, "allocator_compile_command": qv4[0],
              "compile_command_count": len(commands),
              "toolchain_policy": "Exact executable hashes bound to this receipt; MSVC 19.x x64, "
                                  "no older than the pinned official library. No compiler-output cache."}
    shutil.copyfile(configurations[0], evidence / "CMakeCXXCompiler.cmake")
    write_json(evidence / "configuration-identity.json", result)
    return result


def verify_source_bytes(lock, name, data, expected_blob):
    if name == lock["patch"]["production_path"]:
        require(hashlib.sha256(data).hexdigest() == lock["patch"]["postimage_sha256"],
                "ArchivedPatchPostimageMismatch")
        return "pinned-production-postimage"
    contract = lock["source"]["checkout_eol_contract"]
    if name == contract["path"]:
        canonical = data.replace(b"\r\n", b"\n")
        require(expected_blob == contract["git_blob_sha1"]
                and len(data) == contract["checkout_bytes"]
                and hashlib.sha256(data).hexdigest() == contract["checkout_sha256"]
                and len(canonical) == contract["git_blob_bytes"]
                and hashlib.sha256(canonical).hexdigest() == contract["git_blob_sha256"],
                "UpstreamCrLfFixtureIdentityMismatch")
        return "pinned-upstream-crlf-checkout; original bytes preserved"
    actual = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    require(actual == expected_blob, "SourceCheckoutDiffersFromPinnedIndex:" + name)
    return "exact-git-blob"


def preserve_corresponding_source(source, entries, lock, evidence):
    """Archive the modified library's tracked source, including licenses and build files."""
    files, omitted, total = {}, [], 0
    output = evidence / "qtdeclarative-corresponding-source.zip"
    require(not output.exists(), "SourceArchiveMustBeFresh")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for raw in entries.split(b"\0"):
            if not raw:
                continue
            match = re.fullmatch(rb"([0-9]{6}) ([0-9a-f]{40}) 0\t(.+)", raw)
            require(match is not None, "UnrecognizedSourceIndexEntry")
            mode, blob, name = match[1].decode(), match[2].decode(), match[3].decode("utf-8")
            relative = PurePosixPath(name)
            require(not relative.is_absolute() and ".." not in relative.parts
                    and "\\" not in name and name not in files, "SourceArchivePathRejected")
            if mode == "160000":
                require(name == "tests/auto/qml/ecmascripttests/test262"
                        and blob == "a0efb7e1ab1cee24c387abe1897ff18fa116c17d",
                        "UnexpectedSourceGitlink")
                omitted.append({"path": name, "commit": blob,
                                "reason": "Unbuilt test suite; Qml/BuiltinsOutput do not use this gitlink."})
                continue
            require(mode in ("100644", "100755"), "UnsupportedTrackedSourceMode")
            path = plain_path(source / name, root=source)
            data = path.read_bytes()
            verified_by = verify_source_bytes(lock, name, data, blob)
            total += len(data)
            require(total <= 256 * 1024**2 and len(files) < 30000, "SourceSnapshotLimitExceeded")
            files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                           "git_blob_before_patch": blob, "mode": mode, "verification": verified_by}
            entry = zipfile.ZipInfo("qtdeclarative/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr, entry.compress_type = int(mode, 8) << 16, zipfile.ZIP_DEFLATED
            archive.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    require(len(files) == 23849 and len(omitted) == 1, "SourceSnapshotClosureChanged")
    require(files[lock["patch"]["production_path"]]["sha256"] == lock["patch"]["postimage_sha256"],
            "ArchivedPatchPostimageMismatch")
    require(any(n.startswith("LICENSES/") for n in files), "SourceLicensesMissing")
    contract = lock["source"]["checkout_eol_contract"]
    require(contract["attribute_rule"] in (source / contract["attribute_source"]).read_text().splitlines(),
            "UpstreamCrLfAttributeRuleMismatch")
    write_json(evidence / "source-snapshot-files.json", files)
    result = {"archive": file_identity(output), "tracked_regular_files": len(files),
              "tracked_bytes": total, "file_manifest_content_id": canonical_digest(files),
              "omitted_gitlinks": omitted, "source": lock["source"], "patch": lock["patch"],
              "scope": "Modified QtDeclarative library source and its build/license files. "
                       "The unbuilt test262 suite is explicitly omitted. The single upstream-forced CRLF "
                       "test data file retains its pinned checkout bytes; no general newline normalization."}
    write_json(evidence / "corresponding-source.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--evidence-directory", required=True, type=Path)
    parser.add_argument("--archive-cache", type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-pr-head-sha", required=True)
    parser.add_argument("--install-stock-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.install_stock_worker:
        return install_stock_worker(repo, args)
    report = {"schema": 1, "kind": "isolated-qt612-qml-diagnostic-sdk", "success": False,
              "started_utc": utc(), "errors": [], "stage": "admission",
              "source_sha": args.expected_source_sha, "pr_head_sha": args.expected_pr_head_sha,
              "product_workflow_modified": False, "actual_process_module_sampling": False,
              "real_provider_requests": 0}
    evidence, build = None, None
    try:
        inputs = admit(repo, args.expected_source_sha, args.expected_pr_head_sha)
        evidence = fresh_directory(args.evidence_directory.absolute(), root=repo)
        work = fresh_directory(args.work_root.absolute(), root=Path(os.environ["RUNNER_TEMP"]).absolute())
        # Keep native Qt/CMake paths short and shell-independent.
        require(len(str(work)) <= 100 and not any(x in str(work) for x in '&|<>^%!"();'),
                "UnsuitableDiagnosticBuildPath")
        report.update(source_inputs=inputs, work_root=str(work))
        for relative in SOURCE_INPUTS:
            destination = evidence / "reproduction" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / relative, destination)
        lock = read_json(repo / LOCK, 65536)
        require(lock["schema"] == 1 and lock["kind"] == "qt612-public-diagnostic-only"
                and lock["source"]["repository"] == "https://github.com/qt/qtdeclarative.git",
                "InvalidDiagnosticLock")
        tools = tool_paths()
        report["tools"] = {name: {"path": path, **file_identity(Path(path))} for name, path in tools.items()}
        toolchain_before = native_toolchain_files(tools)
        known_executables = executable_inventory(toolchain_before, report["tools"])
        write_json(evidence / "native-toolchain-files.json", toolchain_before)
        report["native_toolchain_content_id"] = canonical_digest(toolchain_before)
        report["tool_environment"] = {name: os.environ.get(name) for name in
                                      ("VCToolsVersion", "WindowsSDKVersion", "VSCMD_ARG_HOST_ARCH", "VSCMD_ARG_TGT_ARCH")}
        require(os.environ.get("VSCMD_ARG_TGT_ARCH", "").lower() == "x64", "MsvcX64EnvironmentRequired")
        commands = evidence / "commands"
        def run(name, arguments, cwd=work, seconds=120, env=None, accepted=(0,)):
            return run_logged(arguments, cwd, commands, name, seconds, env=env, accepted=accepted,
                              known_executables=known_executables)
        report["stage"] = "fresh-stock"
        private_cache = fresh_directory(work / "archives", root=work)
        cache_entries = []
        shared = plain_path(args.archive_cache.absolute(), exists=False) if args.archive_cache else None
        for entry in lock["stock"]["archives"]:
            require(re.fullmatch(r"[A-Za-z0-9_.-]+\.7z", entry["filename"])
                    and SHA.fullmatch(entry["sha256"]), "InvalidArchiveLockEntry")
            original = shared / entry["filename"] if shared else None
            item = {"filename": entry["filename"], "cache_status": "missing"}
            if original is not None and original.exists():
                plain_path(original, root=shared)
                item["cache_before"] = file_identity(original)
                if item["cache_before"]["sha256"] == entry["sha256"]:
                    copied = private_cache / entry["filename"]
                    shutil.copyfile(original, copied)
                    require(file_identity(copied) == item["cache_before"]
                            and file_identity(original) == item["cache_before"], "CachedArchiveChangedDuringCopy")
                    item["cache_status"] = "copied-verified"
                else:
                    item["cache_status"] = "rejected-digest; will-fetch-official-into-private-cache"
            cache_entries.append(item)
        report["archive_cache"] = cache_entries
        write_json(evidence / "archive-cache.json", cache_entries)
        stock_output = work / "stock"
        run("01-install-stock", [tools["python.exe"], repo / "tools/Build-Qt612QmlDiagnosticSdk.py",
             "--install-stock-worker", "--work-root", work,
             "--evidence-directory", evidence / "stock-install-pins", "--archive-cache", private_cache,
             "--expected-source-sha", args.expected_source_sha,
             "--expected-pr-head-sha", args.expected_pr_head_sha], seconds=900)
        sdk_receipt = read_json(stock_output / "sdk-install-result.json")
        check_receipt(lock, sdk_receipt)
        stock = plain_path(Path(sdk_receipt["kit_root"]), root=stock_output)
        stock_before = inventory(stock)
        write_json(evidence / "stock-sdk-receipt.json", sdk_receipt)
        write_json(evidence / "stock-files-before.json", stock_before)
        report.update(stock_root=str(stock), stock_content_id=canonical_digest(stock_before))
        report["stock_module_metadata"] = verify_stock_qml_metadata(lock, stock / "modules/Qml.json")
        shutil.copyfile(stock / "modules/Qml.json", evidence / "stock-Qml.json")
        report["stock_module_metadata_file"] = file_identity(evidence / "stock-Qml.json")
        report["stage"] = "pinned-source"
        source = fresh_directory(work / "source", root=work)
        git = tools["git.exe"]
        run("02-git-init", [git, "-C", source, "init"], seconds=20)
        for index, (key, value) in enumerate((("core.autocrlf", "false"), ("core.eol", "lf"),
                                            ("core.longpaths", "true"))):
            run("02-" + str(index) + "-git-local-config",
                [git, "-C", source, "config", "--local", key, value], seconds=20)
        run("03-git-fetch", [git, "-C", source, "fetch", "--depth=1", lock["source"]["repository"],
                            lock["source"]["commit"]], seconds=240)
        run("04-git-checkout", [git, "-C", source, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                               "checkout", "--detach", "FETCH_HEAD"], seconds=90)
        run("04a-source-config", [git, "-C", source, "config", "--local", "--list"], seconds=20)
        require({"core.autocrlf=false", "core.eol=lf", "core.longpaths=true"}
                <= set(output_text(commands, "04a-source-config").splitlines()), "SourceGitConfigurationMismatch")
        run("05-source-identity", [git, "-C", source, "show", "-s", "--format=%H%n%T", "HEAD"], seconds=20)
        require(output_text(commands, "05-source-identity").splitlines()
                == [lock["source"]["commit"], lock["source"]["tree"]], "QtSourceIdentityMismatch")
        original = source / lock["patch"]["production_path"]
        check_patch(lock, repo / PATCH, original)
        run("06-patch-check", [git, "-C", source, "apply", "--check", repo / PATCH], seconds=20)
        run("07-patch-apply", [git, "-C", source, "apply", repo / PATCH], seconds=20)
        require(digest(original) == lock["patch"]["postimage_sha256"], "PatchPostimageMismatch")
        run("08-patch-stat", [git, "-C", source, "diff", "--numstat"], seconds=20)
        require(output_text(commands, "08-patch-stat") == "15\t7\t" + lock["patch"]["production_path"],
                "UnexpectedQtSourceChanges")
        run("09-patch-diff", [git, "-C", source, "diff", "--binary"], seconds=20)
        run("09a-source-files", [git, "-C", source, "ls-files", "--stage", "-z"], seconds=30)
        run("09b-source-status", [git, "-C", source, "status", "--porcelain=v1", "--untracked-files=all"], seconds=30)
        run("09c-source-diff-paths", [git, "-C", source, "diff", "--name-only"], seconds=20)
        require(output_text(commands, "09b-source-status") == "M " + lock["patch"]["production_path"],
                "UnexpectedPatchedSourceStatus")
        require(output_text(commands, "09c-source-diff-paths") == lock["patch"]["production_path"],
                "UnexpectedPatchedSourcePaths")
        report["corresponding_source"] = preserve_corresponding_source(
            source, (commands / "09a-source-files.stdout.log").read_bytes(), lock, evidence)
        report["qt_source"] = lock["source"]
        report["qt_patch"] = lock["patch"]
        report["stage"] = "configure"
        build = fresh_directory(work / "build", root=work)
        module_stage = fresh_directory(work / "module-stage", root=work)
        configure = work / "configure-module.ps1"
        # Qt's .bat wrapper re-expands its arguments through cmd.exe. Keep the
        # generator expression's < and > out of that command line entirely.
        # CMP0141 applies before project(); the format propagates to try_compile.
        # /Z7 avoids compiler PDBs in debug probes, leaving Release unchanged.
        # https://cmake.org/cmake/help/v3.31/variable/CMAKE_MSVC_DEBUG_INFORMATION_FORMAT.html
        initial_cache = prepare_msvc_initial_cache(work, evidence)
        report["msvc_initial_cache"] = file_identity(initial_cache)
        configure_args = module_configure_arguments(work, stock, tools)
        require(Path(configure_args[0]).is_file(), "OfficialModuleConfigureWrapperMissing")
        with configure.open("xb") as stream:
            stream.write(module_configure_script(configure_args))
        with (evidence / configure.name).open("xb") as stream:
            stream.write(configure.read_bytes())
        require(file_identity(configure) == file_identity(evidence / configure.name),
                "ConfigureScriptEvidenceChanged")
        report["configure_script"] = file_identity(configure)
        env = tool_environment()
        env.update(PATH=str(stock / "bin") + os.pathsep + env["PATH"],
                   CMAKE_PREFIX_PATH=str(stock), QT_ROOT_DIR=str(stock))
        report["compiler_process_policy"] = {
            "invocation_environment": {"VCTIP_NO_TELEMETRY": env["VCTIP_NO_TELEMETRY"]},
            "debug_information_format": MSVC_DEBUG_INFORMATION_FORMAT,
            "telemetry_opt_out_effect_verified": False,
            "acceptance": "Natural successful compiler root plus actual empty owned Job; only the "
                          "locked, fully identified vctip may use recorded targeted retirement. "
                          "No telemetry opt-out guarantee or runtime/private exception.",
            "retirement_policy": lock["compiler_retirement"],
        }
        compile_context = {"repo": repo, "work": work, "stock": stock, "tools": tools}
        run_compiler_logged("sdk:10-configure",
            [tools["pwsh.exe"], "-NoLogo", "-NoProfile", "-NonInteractive", "-File", configure],
            build, commands, 180, context=compile_context, lock=lock, tool_identities=report["tools"],
            known_executables=known_executables, env=env)
        for name in ("CMakeCache.txt", "config.opt", "config.summary", "compile_commands.json"):
            candidate = build / name
            require(candidate.is_file(), "MissingConfigurationEvidence:" + name)
            shutil.copyfile(candidate, evidence / name)
        report["configuration"] = verify_configuration(
            source, build, stock, tools, evidence, lock, report["tools"]["cmake.exe"])
        run_compiler_logged("sdk:11-qml-build",
            [tools["cmake.exe"], "--build", build, "--target", "Qml", "BuiltinsOutput", "--parallel", "2"],
            work, commands, 1200, context=compile_context, lock=lock, tool_identities=report["tools"],
            known_executables=known_executables, env=env)
        report["stage"] = "headers-and-install-closure"
        shutil.copyfile(build / "build.ninja", evidence / "build.ninja")
        header_review = verify_headers(source, build, stock, lock, evidence)
        write_json(evidence / "header-alignment.json", header_review)
        report["header_contract"] = verify_header_contract(header_review, lock)
        install_script = build / "src/qml/cmake_install.cmake"
        text = install_script.read_text(encoding="utf-8")
        require(not re.search(r"(?m)^\s*include\s*\(", text), "ModuleInstallWouldRecurse")
        destinations = re.findall(r'file\(INSTALL DESTINATION "([^"]+)"', text)
        prefix = "$" + "{CMAKE_INSTALL_PREFIX}/"
        require(destinations and all(p.startswith(prefix) and ".." not in PurePosixPath(p).parts
                                     for p in destinations), "ModuleInstallDestinationEscapesStage")
        for name in ("qml/builtins.qmltypes", "qml/jsroot.qmltypes"):
            require((build / name).is_file(), "BuiltinsOutputIncomplete:" + name)
        shutil.copyfile(install_script, evidence / "qml-cmake-install.cmake")
        manifest_text = evidence / "module-install-files.txt"
        install_driver = work / "install-qml-only.cmake"
        install_driver.write_text(
            "set(CMAKE_INSTALL_PREFIX " + cmake_quote(module_stage) + ")\n"
            'set(CMAKE_INSTALL_CONFIG_NAME "Release")\nset(CMAKE_INSTALL_COMPONENT "")\n'
            "set(CMAKE_INSTALL_LOCAL_ONLY TRUE)\nset(CMAKE_INSTALL_DO_STRIP FALSE)\n"
            "include(" + cmake_quote(install_script) + ")\n"
            "file(WRITE " + cmake_quote(manifest_text) + ' "")\n'
            "foreach(_file IN LISTS CMAKE_INSTALL_MANIFEST_FILES)\n"
            "file(APPEND " + cmake_quote(manifest_text) + ' "' + "$" + '{_file}\\n")\nendforeach()\n',
            encoding="utf-8")
        shutil.copyfile(install_driver, evidence / "install-qml-only.cmake")
        run("12-install-qml-only", [tools["cmake.exe"], "-P", install_driver], seconds=120, env=env)
        staged, changes, retained_headers = verify_module_stage(module_stage, stock, header_review)
        write_json(evidence / "module-header-retention.json",
                   [row for row in header_review if row["path"] in retained_headers])
        for relative in staged:
            if relative.endswith((".cmake", ".pc", ".pri", ".prl")):
                data = (module_stage / relative).read_text(encoding="utf-8")
                for path in (source, build, module_stage):
                    require(str(path).replace("\\", "/") not in data.replace("\\", "/"),
                            "NonRelocatableModuleMetadata:" + relative)
        patched_platform = module_platform(read_json(module_stage / "modules/Qml.json", 65536),
                                           report["configuration"]["stock_qml_platform"]["targets"])
        require(patched_platform["compiler_version"]
                == report["configuration"]["compiler"]["CMAKE_CXX_COMPILER_VERSION"],
                "ModuleMetadataCompilerMismatch")
        report["patched_qml_platform"] = patched_platform
        recorded = [plain_path(Path(line), root=module_stage).relative_to(module_stage).as_posix()
                    for line in manifest_text.read_text(encoding="utf-8").splitlines() if line]
        require(set(recorded) == set(staged), "ModuleInstallManifestMismatch")
        write_json(evidence / "module-files.json", staged)
        report["module_install"] = {"files": len(staged), "approved_changes": changes,
                                    "retained_stock_headers": retained_headers,
                                    "duplicate_manifest_entries": len(recorded) - len(set(recorded))}
        report["stage"] = "exports-and-dependencies"
        for flavor, directory in (("stock", stock), ("patched", module_stage)):
            dll = directory / "bin/Qt6Qml.dll"
            run("13-" + flavor + "-exports", [tools["dumpbin.exe"], "/exports", dll], seconds=30)
            run("14-" + flavor + "-imports", [tools["dumpbin.exe"], "/imports", dll], seconds=30)
            run("15-" + flavor + "-dependents", [tools["dumpbin.exe"], "/dependents", dll], seconds=30)
            run("16-" + flavor + "-headers", [tools["dumpbin.exe"], "/headers", dll], seconds=30)
            require(re.search(r"(?mi)^\s*8664 machine \(x64\)\s*$",
                              output_text(commands, "16-" + flavor + "-headers")),
                    "QtQmlPeMachineMismatch:" + flavor)
        stock_exports = parse_exports(output_text(commands, "13-stock-exports"))
        patched_exports = parse_exports(output_text(commands, "13-patched-exports"))
        stock_deps = parse_dependents(output_text(commands, "15-stock-dependents"))
        patched_deps = parse_dependents(output_text(commands, "15-patched-dependents"))
        export_review = {"stock_count": len(stock_exports), "patched_count": len(patched_exports),
                         "names_and_ordinals_equal": stock_exports == patched_exports,
                         "stock_dependencies": stock_deps, "patched_dependencies": patched_deps,
                         "dependencies_equal": stock_deps == patched_deps,
                         "scope": "PE interface comparison plus identical source/feature headers; not a proof of all ABI behavior."}
        write_json(evidence / "pe-interface-review.json", export_review)
        require(export_review["names_and_ordinals_equal"] and export_review["dependencies_equal"],
                "QmlPeInterfaceDifferenceRequiresReview")
        require({p for p in patched_deps if p.startswith("qt")} <= {"qt6core.dll", "qt6network.dll"},
                "UnexpectedQtQmlDependency")
        for name in patched_deps:
            if name.startswith("qt"):
                require((stock / "bin" / name).is_file(), "UnresolvedQtQmlDependency:" + name)
        report["stage"] = "compose-complete-derived-kit"
        derived = work / "derived"
        derived_files = compose_derived_kit(stock, module_stage, derived, stock_before,
                                           staged, retained_headers)
        stock_after = inventory(stock)
        assert_same_tree(stock_before, stock_after)
        write_json(evidence / "derived-files.json", derived_files)
        write_json(evidence / "stock-files-after.json", stock_after)
        report.update(derived_root=str(derived), derived_content_id=canonical_digest(derived_files),
                      stock_unchanged=True, derived_delta=compare_tree(stock_before, derived_files))
        report["inherited_sdk_scope"] = (
            "Complete stock kit copy plus the inspected Qml Release install closure. "
            "Headers with proven source EOL/parser source-location differences retain their "
            "exact official stock bytes in the derived kit; raw build headers are preserved separately. "
            "Stock Debug binaries and original SDK SBOM files remain original; they do not "
            "attest the modified Release QtQml. This receipt/source/patch describe that derivation. "
            "No Rust Core or OpenSSL product pairing is changed or accepted by this fixture workflow.")
        # Public diagnostic binaries are paired with their corresponding source;
        # the full official SDK, host fonts and proprietary compiler files stay outside the artifact.
        preserved_module = evidence / "module-install-output"
        shutil.copytree(module_stage, preserved_module, copy_function=shutil.copyfile)
        assert_same_tree(staged, inventory(preserved_module))
        for flavor, directory in (("stock", stock), ("patched", derived)):
            run("17-" + flavor + "-qtpaths", [directory / "bin/qtpaths.exe", "--query", "QT_INSTALL_PREFIX"],
                seconds=20, env=env)
            observed = Path(output_text(commands, "17-" + flavor + "-qtpaths"))
            require(observed.resolve() == directory.resolve(), "QtPathsResolvedDifferentSdk:" + flavor)
        run("18-source-status-after-build", [git, "-C", source, "status", "--porcelain=v1",
                                            "--untracked-files=all"], seconds=30)
        require(output_text(commands, "18-source-status-after-build")
                == "M " + lock["patch"]["production_path"]
                and digest(original) == lock["patch"]["postimage_sha256"], "QtSourceChangedDuringBuild")
        require(source_identity(repo, args.expected_source_sha, args.expected_pr_head_sha) == inputs,
                "DiagnosticSourceChangedDuringBuild")
        for name, item in report["tools"].items():
            require(file_identity(Path(item["path"])) == {k: item[k] for k in ("bytes", "sha256")},
                    "BuildToolChanged:" + name)
        require(native_toolchain_files(tools) == toolchain_before, "NativeToolchainFilesChanged")
        report["derivation_id"] = canonical_digest({
            "lock": lock, "source_inputs": inputs["files"], "tools": report["tools"],
            "configuration": report["configuration"], "stock": report["stock_content_id"],
            "derived": report["derived_content_id"], "native_toolchain": report["native_toolchain_content_id"]})
        report["stage"] = "complete"
        report["success"] = True
    except BaseException as error:
        report["errors"].append(type(error).__name__ + ":" + str(error))
    finally:
        if evidence is not None:
            if build is not None:
                try:
                    report["configuration_snapshot"] = preserve_configuration_snapshot(build, evidence)
                except Exception as error:
                    report["success"] = False
                    report["errors"].append("ConfigurationEvidence:" + type(error).__name__ + ":" + str(error))
            report["finished_utc"] = utc()
            write_json(evidence / "receipt.json", report)
        else:
            report["finished_utc"] = utc()
        print(json.dumps({"success": report["success"], "stage": report["stage"], "errors": report["errors"]}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
