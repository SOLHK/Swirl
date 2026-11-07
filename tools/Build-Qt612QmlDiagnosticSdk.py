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
    # Invocation-local compiler opt-out, not a promise that no helper starts.
    # The unchanged owned-Job retirement check still decides acceptance.
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


def run_logged(arguments, cwd, evidence, name, timeout, *, env=None, accepted=(0,), known_executables=None):
    """Public build commands have their own kill-on-close Job, allowing compiler children.

    This does not reuse or weaken PrivateSubscriptionProcess's one-process/eight-second
    guard. Fixtures still run through that unchanged guard inside the comparison command.
    """
    require(os.name == "nt" and 0 < timeout <= 1200, "InvalidWindowsBuildCommand")
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", name), "InvalidCommandEvidenceName")
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

    def snapshot_once():
        if record["owned_pid_snapshot"] is None:
            record["owned_pid_snapshot"] = {"attempted_utc": utc(), "query_count_maximum": 1,
                                             "completed": False}
            result = owned_pid_snapshot(k, c, w, job, known_executables or {})
            record["owned_pid_snapshot"] = result
            record["errors"].extend(result["errors"])
    try:
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
            now = time.monotonic()
            require(retirement_deadline is None or now < retirement_deadline,
                    "CommandRetirementUnconfirmed")
            excessive = sum(p.stat().st_size for p in (stdout_path, stderr_path)) > MAX_LOG_BYTES
            if state == 0 and grace_deadline is None:
                grace_deadline = now + 2
            if state == 0 and accounting.active == 0:
                if excessive:
                    record["errors"].append("OutputLimitExceeded")
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
                snapshot_once()
                # Root/child exit can race with the snapshot; observe both before termination.
                state = k.WaitForSingleObject(info.process, 0)
                require(state in (0, 258), "PreTerminationRootWaitFailed")
                require(k.QueryInformationJobObject(job, 1, c.byref(accounting), c.sizeof(accounting), None),
                        "PreTerminationJobQueryFailed")
                observe_root(state, accounting, "pre-termination")
                if state == 0 and accounting.active == 0:
                    record["owned_job_empty"] = True
                    continue
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
        if attrs:
            k.DeleteProcThreadAttributeList(attrs)
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
        write_json(evidence / (name + ".json"), record)
    require(command_completion_allowed(record, accepted), "CommandFailed:" + name)
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


def normalized_parser(data):
    # Source-location strings only; line numbers, tokens and all other bytes remain exact.
    return re.sub(rb'(?m)^(#line [0-9]+ ")[^"\r\n]+(")\r?$', rb'\1<SOURCE_LOCATION>\2', data)


def verify_headers(source, build, stock):
    result = []
    private = stock / "include/QtQml/6.12.0/QtQml/private"
    source_by_name = {}
    for path in (source / "src").rglob("*.h"):
        source_by_name.setdefault(path.name, []).append(path)
    generated = {
        "qtqml-config_p.h": build / "src/qml/qtqml-config_p.h",
        "qqmljsgrammar_p.h": build / "src/qml/qqmljsgrammar_p.h",
        "qqmljsparser_p.h": build / "src/qml/qqmljsparser_p.h",
    }
    require(private.is_dir(), "StockQmlPrivateHeadersMissing")
    for path in sorted(private.glob("*.h")):
        data = path.read_bytes()
        if path.name in generated:
            candidate = generated[path.name]
            other = candidate.read_bytes()
            okay = (normalized_parser(data) == normalized_parser(other)
                    if path.name == "qqmljsparser_p.h" else data == other)
            method = "source-location-only-normalization" if path.name == "qqmljsparser_p.h" else "exact-generated"
        else:
            candidates = source_by_name.get(path.name, [])
            matches = [p for p in candidates if p.read_bytes() == data]
            okay, candidate, method = bool(matches), matches[0] if matches else None, "exact-source"
        result.append({"path": path.relative_to(stock).as_posix(), "stock": file_identity(path),
                       "matched": okay, "candidate": str(candidate) if candidate else None, "method": method})
    public = stock / "include/QtQml/qtqml-config.h"
    rebuilt = build / "src/qml/qtqml-config.h"
    result.append({"path": "include/QtQml/qtqml-config.h", "stock": file_identity(public),
                   "matched": public.read_bytes() == rebuilt.read_bytes(),
                   "candidate": str(rebuilt), "method": "exact-generated"})
    require(len(result) >= 250, "PrivateHeaderCoverageIncomplete")
    return result


def permitted_override(path, before, after):
    if before == after:
        return True
    if path == "include/QtQml/6.12.0/QtQml/private/qqmljsparser_p.h":
        return before is not None and normalized_parser(before) == normalized_parser(after)
    return bool(re.fullmatch(
        r"(?:bin/Qt6Qml\.(?:dll|pdb)|lib/Qt6Qml\.(?:lib|prl|pdb|debug)"
        r"|modules/Qml\.json|lib/cmake/Qt6Qml(?:Private)?/[^/]+"
        r"|mkspecs/modules/qt_lib_qml(?:_private)?\.pri|lib/pkgconfig/Qt6Qml\.pc)", path))


def verify_module_stage(stage, stock):
    staged = inventory(stage)
    require("bin/Qt6Qml.dll" in staged and "lib/Qt6Qml.lib" in staged,
            "WindowsQmlModuleOutputsMissing")
    changes = []
    for relative in staged:
        original, changed = stock / relative, stage / relative
        old = original.read_bytes() if original.is_file() else None
        new = changed.read_bytes()
        require(old is not None or permitted_override(relative, None, new),
                "UnexpectedNewModuleFile:" + relative)
        require(permitted_override(relative, old, new), "UnexpectedModuleMetadataOrHeaderChange:" + relative)
        if old != new:
            changes.append(relative)
    require("bin/Qt6Qml.dll" in changes, "QmlRuntimeWasNotRebuilt")
    return staged, changes


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
        initial_cache = work / "msvc-initial-cache.cmake"
        initial_cache.write_text(MSVC_INITIAL_CACHE, encoding="utf-8", newline="\n")
        shutil.copyfile(initial_cache, evidence / initial_cache.name)
        report["msvc_initial_cache"] = file_identity(initial_cache)
        configure_args = [
            stock / "bin/qt-configure-module.bat", source, "--", "-G", "Ninja",
            "-C", initial_cache,
            cmake_path_definition("CMAKE_PREFIX_PATH", stock, "PATH"),
            "-DCMAKE_BUILD_TYPE=Release", cmake_path_definition("CMAKE_INSTALL_PREFIX", module_stage, "PATH"),
            cmake_path_definition("CMAKE_C_COMPILER", tools["cl.exe"], "FILEPATH"),
            cmake_path_definition("CMAKE_CXX_COMPILER", tools["cl.exe"], "FILEPATH"),
            cmake_path_definition("CMAKE_LINKER", tools["link.exe"], "FILEPATH"),
            cmake_path_definition("CMAKE_AR", tools["lib.exe"], "FILEPATH"),
            cmake_path_definition("CMAKE_RC_COMPILER", tools["rc.exe"], "FILEPATH"),
            cmake_path_definition("CMAKE_MT", tools["mt.exe"], "FILEPATH"),
            cmake_path_definition("CMAKE_MAKE_PROGRAM", tools["ninja.exe"], "FILEPATH"),
            "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL",
            "-DQT_BUILD_TESTS=OFF", "-DQT_BUILD_EXAMPLES=OFF", "-DQT_BUILD_TOOLS_BY_DEFAULT=OFF",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ]
        require(Path(configure_args[0]).is_file(), "OfficialModuleConfigureWrapperMissing")
        configure.write_text("$ErrorActionPreference = 'Stop'\n& "
                             + " ".join(ps_quote(x) for x in configure_args)
                             + "\nexit $LASTEXITCODE\n", encoding="utf-8")
        env = tool_environment()
        env.update(PATH=str(stock / "bin") + os.pathsep + env["PATH"],
                   CMAKE_PREFIX_PATH=str(stock), QT_ROOT_DIR=str(stock))
        report["compiler_process_policy"] = {
            "invocation_environment": {"VCTIP_NO_TELEMETRY": env["VCTIP_NO_TELEMETRY"]},
            "debug_information_format": MSVC_DEBUG_INFORMATION_FORMAT,
            "telemetry_opt_out_effect_verified": False,
            "acceptance": "Unchanged native exit, no forced cleanup and empty owned Job required.",
        }
        run("10-configure", [tools["pwsh.exe"], "-NoLogo", "-NoProfile", "-NonInteractive",
                             "-File", configure], cwd=build, seconds=180, env=env)
        for name in ("CMakeCache.txt", "config.opt", "config.summary", "compile_commands.json"):
            candidate = build / name
            require(candidate.is_file(), "MissingConfigurationEvidence:" + name)
            shutil.copyfile(candidate, evidence / name)
        report["configuration"] = verify_configuration(
            source, build, stock, tools, evidence, lock, report["tools"]["cmake.exe"])
        run("11-qml-build", [tools["cmake.exe"], "--build", build, "--target", "Qml", "BuiltinsOutput",
                            "--parallel", "2"], seconds=1200, env=env)
        report["stage"] = "headers-and-install-closure"
        header_review = verify_headers(source, build, stock)
        write_json(evidence / "header-alignment.json", header_review)
        require(all(x["matched"] for x in header_review), "QtQmlPrivateHeaderOrFeatureMismatch")
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
        staged, changes = verify_module_stage(module_stage, stock)
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
        require(not derived.exists(), "DerivedKitMustBeFresh")
        shutil.copytree(stock, derived, copy_function=shutil.copy2)
        for relative in staged:
            if stock_before.get(relative) == staged[relative]:
                continue
            target = derived / relative
            plain_path(target, root=derived, exists=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(module_stage / relative, target)
        derived_files = inventory(derived)
        expected_files = dict(stock_before)
        expected_files.update(staged)
        assert_same_tree(expected_files, derived_files)
        stock_after = inventory(stock)
        assert_same_tree(stock_before, stock_after)
        write_json(evidence / "derived-files.json", derived_files)
        write_json(evidence / "stock-files-after.json", stock_after)
        report.update(derived_root=str(derived), derived_content_id=canonical_digest(derived_files),
                      stock_unchanged=True, derived_delta=compare_tree(stock_before, derived_files))
        report["inherited_sdk_scope"] = (
            "Complete stock kit copy plus the inspected Qml Release install closure. "
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
