#!/usr/bin/env python3
"""Pair a real staged Qt runtime with its pinned source, then bind the installer.

This tool never builds or executes source archives, DLLs, or the installer. The
only network requests are the five public, hash-pinned Qt source archives.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile


class SourceError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise SourceError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_identity(path):
    path = plain_path(path)
    require(path.is_file(), "RegularFileRequired")
    with path.open("rb") as stream:
        value = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"bytes": path.stat().st_size, "sha256": value}


def plain_path(value, *, exists=True):
    path = Path(value).absolute()
    for parent in [path, *path.parents]:
        if parent.exists() or parent.is_symlink():
            data = parent.lstat()
            require(not stat.S_ISLNK(data.st_mode)
                    and not getattr(data, "st_file_attributes", 0) & 0x400,
                    "ReparsePathRejected")
    require(not exists or path.exists(), "InputPathMissing")
    return path


def relative_name(value):
    require(isinstance(value, str) and value and "\\" not in value
            and not any(ord(ch) < 32 for ch in value), "ArchivePathRejected")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value
            and all(part not in ("", ".", "..") and ":" not in part
                    for part in path.parts), "ArchivePathRejected")
    return value


def read_json(path, limit=32 * 1024**2):
    path = plain_path(path)
    require(path.is_file() and path.stat().st_size <= limit, "JsonInputBoundExceeded")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_new(path, data):
    path = plain_path(path, exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def source_lock(path=None):
    path = Path(path) if path else Path(__file__).with_name("qt612-product-source.lock.json")
    lock = read_json(path)
    require(lock["schema"] == 1 and lock["qt_version"] == "6.12.0", "SourceLockSchemaMismatch")
    require(lock["runtime_modules"] == ["qtbase", "qtdeclarative", "qtsvg", "qttranslations"]
            and lock["build_only_modules"] == ["qtshadertools", "qttools"],
            "SourceLockModuleSetMismatch")
    require({x["module"] for x in lock["official_sources"]}
            == {"qtbase", "qtsvg", "qttranslations", "qtshadertools", "qttools"},
            "SourceLockArchiveSetMismatch")
    return path, lock


def classify_runtime(name, rules):
    relative_name(name)
    if name.startswith("licenses/"):
        return None
    if name in rules["root_dlls"]:
        return rules["root_dlls"][name]
    if name in rules["plugins"]:
        return rules["plugins"][name]
    if name.startswith("qml/"):
        require(any(name.startswith(prefix) for prefix in rules["qml_roots"]),
                "UnknownQtQmlModule")
        return "qtdeclarative"
    if name.startswith("translations/"):
        require(name in rules["generated_translations"], "UnknownQtTranslation")
        return "qttranslations"
    if name.lower().endswith(".dll"):
        require(name in rules["non_qt_root_dlls"], "UnknownRuntimeLibrary")
    require(not name.lower().startswith("qt6")
            and not name.startswith(("platforms/", "qmltooling/", "tls/", "imageformats/",
                                     "generic/", "networkinformation/", "iconengines/")),
            "UnknownQtRuntimeFile")
    return None


def sdk_name(name):
    if "/" not in name:
        return "bin/" + name
    if name.startswith(("qml/", "translations/")):
        return name
    return "plugins/" + name


def verify_runtime(root, lock, derived):
    root = plain_path(root)
    require(root.is_dir(), "RuntimeDirectoryRequired")
    files, excluded, seen = {}, [], set()
    paths = sorted(root.rglob("*"))
    require(len(paths) <= lock["limits"]["runtime_files"] * 2, "RuntimeEntryBoundExceeded")
    for path in paths:
        path = plain_path(path)
        if path.is_dir():
            continue
        require(path.is_file(), "RuntimeSpecialFileRejected")
        name = path.relative_to(root).as_posix()
        require(name.casefold() not in seen, "RuntimeCaseCollision")
        seen.add(name.casefold())
        module = classify_runtime(name, lock["runtime_rules"])
        if module is None:
            excluded.append(name)
            continue
        actual = file_identity(path)
        if module == "qttranslations":
            # windeployqt uses lconvert to merge component catalogs. Its output is
            # not the SDK's same-named, tiny dependency-index qt_<locale>.qm.
            require(actual["sha256"] == lock["runtime_rules"]["generated_translations"][name],
                    "GeneratedTranslationIdentityMismatch")
            origin = "pinned-windeployqt-lconvert-output"
        else:
            require(derived.get(sdk_name(name)) == actual, "RuntimeSdkIdentityMismatch")
            origin = "exact-derived-sdk-file"
        files[name] = {**actual, "module": module, "origin": origin}
    require(set(lock["runtime_rules"]["required_files"]) <= set(files), "RequiredQtRuntimeMissing")
    require({row["module"] for row in files.values()} == set(lock["runtime_modules"]),
            "RuntimeModuleClosureMismatch")
    return files, excluded


def verify_sdk(directory, lock):
    directory = plain_path(directory)
    for name, expected in lock["sdk_artifact"]["files"].items():
        relative_name(name)
        require(file_identity(directory / name) == expected, "PinnedSdkEvidenceMismatch")
    source = read_json(directory / "corresponding-source.json")
    require(source == lock["modified_declarative"], "ModifiedSourceReceiptMismatch")
    snapshot = read_json(directory / "source-snapshot-files.json")
    require(sha(canonical(snapshot)) == source["file_manifest_content_id"],
            "ModifiedSourceManifestMismatch")
    derived = read_json(directory / "derived-files.json")
    stock = read_json(directory / "stock-files-before.json")
    require(derived["bin/Qt6Qml.dll"] != stock["bin/Qt6Qml.dll"], "PatchedQtQmlMissing")
    return source, snapshot, derived


class HttpsRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        require(url.scheme == "https" and not url.username and not url.password,
                "SourceRedirectRejected")
        # No authentication or user headers are attached to public source fetches.
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def acquire_archive(item, cache, seconds):
    cache = plain_path(cache, exists=False)
    cache.mkdir(parents=True, exist_ok=True)
    name = relative_name(item["archive"])
    require("/" not in name, "ArchiveFilenameRejected")
    path = plain_path(cache / name, exists=False)
    expected = {"bytes": item["bytes"], "sha256": item["sha256"]}
    if path.exists():
        require(file_identity(path) == expected, "CachedSourceIdentityMismatch")
        return path
    require(item["url"] == "https://download.qt.io/archive/qt/6.12/6.12.0/submodules/" + name,
            "SourceUrlRejected")
    temporary = path.with_name(name + ".partial")
    start, total, digest = time.monotonic(), 0, hashlib.sha256()
    opener = urllib.request.build_opener(HttpsRedirects())
    with opener.open(item["url"], timeout=30) as response, temporary.open("xb") as stream:
        require(response.status == 200, "SourceHttpStatusRejected")
        while True:
            chunk = response.read(min(1024**2, item["bytes"] - total + 1))
            if not chunk:
                break
            total += len(chunk)
            require(total <= item["bytes"] and time.monotonic() - start <= seconds,
                    "SourceDownloadBoundExceeded")
            stream.write(chunk)
            digest.update(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    require({"bytes": total, "sha256": digest.hexdigest()} == expected,
            "DownloadedSourceIdentityMismatch")
    require(not path.exists(), "SourceCacheDestinationAppeared")
    # An atomic no-replace publication also rejects a concurrent cache writer.
    os.link(temporary, path)
    temporary.unlink()
    return path


def notice_member(name):
    parts = PurePosixPath(name).parts
    base = parts[-1].upper()
    return (parts[0] == "LICENSES"
            or len(parts) == 1 and base.startswith(("LICENSE", "COPYING", "NOTICE"))
            or name.startswith("src/3rdparty/")
            and (base.startswith(("LICENSE", "COPYING", "NOTICE"))
                 or base == "QT_ATTRIBUTION.JSON"))


def inspect_official_archive(path, item, limits):
    require(file_identity(path) == {"bytes": item["bytes"], "sha256": item["sha256"]},
            "OfficialSourceIdentityMismatch")
    root = item["module"] + "-everywhere-src-6.12.0"
    names, notices, total, tag, has_cmake = set(), {}, 0, None, False
    with tarfile.open(path, "r:xz") as archive:
        for member in archive:
            name = member.name.rstrip("/")
            relative_name(name)
            require(name == root or name.startswith(root + "/"), "OfficialSourceRootMismatch")
            require(name not in names, "ArchiveDuplicatePath")
            names.add(name)
            require(member.isdir() or member.isfile(), "ArchiveSpecialEntryRejected")
            total += member.size
            require(len(names) <= limits["archive_files"]
                    and total <= limits["archive_uncompressed_bytes"], "SourceArchiveBoundExceeded")
            if not member.isfile():
                continue
            relative = name[len(root) + 1:]
            has_cmake |= relative == "CMakeLists.txt"
            if relative == ".tag" or notice_member(relative):
                require(member.size <= 2 * 1024**2, "SourceNoticeBoundExceeded")
                data = archive.extractfile(member).read()
                require(len(data) == member.size, "SourceMemberTruncated")
                if relative == ".tag":
                    tag = data.decode("ascii").strip()
                else:
                    notices[relative] = data
    require(tag == item["commit"] and has_cmake and any(n.startswith("LICENSES/") for n in notices),
            "OfficialSourceProvenanceMismatch")
    return {"members": len(names), "uncompressed_bytes": total,
            "tag_commit": tag, "license_files": len(notices)}, notices


def inspect_modified_archive(path, source, snapshot, limits):
    require(file_identity(path) == source["archive"], "ModifiedSourceArchiveMismatch")
    names, notices, total = set(), {}, 0
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            require(member.orig_filename == member.filename, "ArchiveOriginalPathChanged")
            name = relative_name(member.filename)
            require(name.startswith("qtdeclarative/") and not member.is_dir()
                    and stat.S_IFMT(member.external_attr >> 16) == stat.S_IFREG,
                    "ModifiedSourceEntryRejected")
            relative = name[len("qtdeclarative/"):]
            require(relative not in names and relative in snapshot, "ModifiedSourcePathMismatch")
            names.add(relative)
            total += member.file_size
            require(len(names) <= limits["archive_files"]
                    and total <= limits["archive_uncompressed_bytes"], "SourceArchiveBoundExceeded")
            digest = hashlib.sha256()
            collected = bytearray() if notice_member(relative) else None
            with archive.open(member) as stream:
                for chunk in iter(lambda: stream.read(1024**2), b""):
                    digest.update(chunk)
                    if collected is not None:
                        require(len(collected) + len(chunk) <= 2 * 1024**2, "SourceNoticeBoundExceeded")
                        collected.extend(chunk)
            expected = snapshot[relative]
            require(member.file_size == expected["bytes"]
                    and digest.hexdigest() == expected["sha256"], "ModifiedSourceMemberMismatch")
            if collected is not None:
                notices[relative] = bytes(collected)
    require(names == set(snapshot) and len(names) == source["tracked_regular_files"]
            and total == source["tracked_bytes"] and any(n.startswith("LICENSES/") for n in notices),
            "ModifiedSourceClosureMismatch")
    return {"members": len(names), "uncompressed_bytes": total,
            "source_commit": source["source"]["commit"],
            "omitted_gitlinks": source["omitted_gitlinks"], "license_files": len(notices)}, notices


def zip_add(archive, name, data):
    relative_name(name)
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)


def verify_bundle_members(path, expected):
    seen = set()
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            name = relative_name(member.filename)
            require(member.orig_filename == name and name not in seen and name in expected,
                    "SourceBundleMemberSetMismatch")
            seen.add(name)
            with archive.open(member) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            require({"bytes": member.file_size, "sha256": actual} == expected[name],
                    "SourceBundleMemberIdentityMismatch")
    require(seen == set(expected), "SourceBundleMemberSetMismatch")


def prepare(args):
    lock_path, lock = source_lock()
    require(re.fullmatch(r"[0-9a-f]{40}", args.source_sha) is not None, "SourceShaRejected")
    runtime, sdk = plain_path(args.runtime_dir), plain_path(args.sdk_evidence)
    output = plain_path(args.output_dir, exists=False)
    require(not output.exists() and output != runtime and runtime not in output.parents,
            "SourceOutputMustBeFreshAndSeparate")
    notes_root = plain_path(runtime / "licenses/qt", exists=False)
    require(not notes_root.exists(), "InstallerQtNotesAlreadyExist")
    source, snapshot, derived = verify_sdk(sdk, lock)
    runtime_files, excluded = verify_runtime(runtime, lock, derived)
    source_paths, inspections, notices = {}, {}, {}
    for item in lock["official_sources"]:
        path = acquire_archive(item, args.cache_dir, lock["limits"]["download_seconds"])
        result, license_files = inspect_official_archive(path, item, lock["limits"])
        source_paths["sources/" + item["archive"]] = path
        inspections[item["module"]] = result
        notices.update({item["module"] + "/" + n: b for n, b in license_files.items()})
    modified = sdk / "qtdeclarative-corresponding-source.zip"
    result, license_files = inspect_modified_archive(modified, source, snapshot, lock["limits"])
    source_paths["sources/qtdeclarative-corresponding-source.zip"] = modified
    inspections["qtdeclarative"] = result
    notices.update({"qtdeclarative/" + n: b for n, b in license_files.items()})
    repository = Path(__file__).resolve().parents[1]
    recipe_paths = {
        "recipe/Prepare-Qt612ProductSource.py": Path(__file__),
        "recipe/qt612-product-source.lock.json": lock_path,
        "README.md": repository / "docs/qt/QT612_PRODUCT_SOURCE.md",
        "NOTICES.md": repository / "docs/qt/QT612_SOURCE_NOTICES.md",
    }
    for name in lock["sdk_artifact"]["files"]:
        if name != "qtdeclarative-corresponding-source.zip":
            recipe_paths["sdk-build-evidence/" + name] = sdk / name
    for path in recipe_paths.values():
        plain_path(path)
    manifest = {
        "schema": 1, "source_sha": args.source_sha, "qt_version": lock["qt_version"],
        "runtime_modules": lock["runtime_modules"], "build_only_modules": lock["build_only_modules"],
        "runtime_files": runtime_files, "runtime_content_id": sha(canonical(runtime_files)),
        "official_sources": lock["official_sources"], "source_inspections": inspections,
        "modified_declarative": source,
        "recipe_files": {name: file_identity(path) for name, path in recipe_paths.items()},
        "source_archives": {name: file_identity(path) for name, path in source_paths.items()},
        "notices": {"notices/" + name: {"bytes": len(data), "sha256": sha(data)}
                    for name, data in notices.items()},
        "exclusions": {"non_qt_runtime_paths": excluded,
                       "scope": "No claim about source or license closure of non-Qt dependencies. "
                                "This does not report runtime tests, whole-workflow acceptance or permanent hosting."},
    }
    output.mkdir(parents=True)
    filename = f"Swirl-Qt-6.12.0-{args.source_sha[:12]}-corresponding-source.zip"
    destination = output / filename
    manifest_data = json_bytes(manifest)
    with zipfile.ZipFile(destination, "x", allowZip64=True) as archive:
        zip_add(archive, "bundle-manifest.json", manifest_data)
        for name, path in sorted(source_paths.items()):
            # These original, already compressed containers retain their bytes.
            archive.write(path, name, compress_type=zipfile.ZIP_STORED)
        for name, path in sorted(recipe_paths.items()):
            zip_add(archive, name, path.read_bytes())
        for name, data in sorted(notices.items()):
            zip_add(archive, "notices/" + name, data)
    require(destination.stat().st_size < lock["limits"]["bundle_bytes"], "SourceBundleBoundExceeded")
    verify_bundle_members(destination, {
        "bundle-manifest.json": {"bytes": len(manifest_data), "sha256": sha(manifest_data)},
        **manifest["source_archives"], **manifest["recipe_files"], **manifest["notices"],
    })
    archive_identity = {"filename": filename, **file_identity(destination)}
    note = {"schema": 1, "source_sha": args.source_sha, "qt_version": lock["qt_version"],
            "archive": archive_identity, "runtime_content_id": manifest["runtime_content_id"],
            "runtime_modules": lock["runtime_modules"], "build_only_modules": lock["build_only_modules"],
            "qtdeclarative_source_commit": source["source"]["commit"],
            "patch_commit": source["patch"]["upstream_commit"],
            "delivery": "Provide this complete source archive together with the installer. "
                        "CI artifact retention is temporary and is not a long-term source offer."}
    installed_notes = {"SOURCE-BUNDLE.json": json_bytes(note),
                       "README.md": recipe_paths["README.md"].read_bytes(),
                       "NOTICES.md": recipe_paths["NOTICES.md"].read_bytes(), **notices}
    # Notes are installed only after every source archive and the completed ZIP
    # have passed validation. Existing product files are never overwritten.
    for name, data in sorted(installed_notes.items()):
        relative_name(name)
        write_new(notes_root / name, data)
    receipt = {"schema": 1, "status": "complete", "source_sha": args.source_sha,
               "qt_version": lock["qt_version"], "archive": archive_identity,
               "runtime_modules": lock["runtime_modules"],
               "build_only_modules": lock["build_only_modules"],
               "runtime_files": runtime_files, "runtime_content_id": manifest["runtime_content_id"],
               "source_inspections": inspections,
               "installer_notes": {"licenses/qt/" + n: {"bytes": len(b), "sha256": sha(b)}
                                   for n, b in installed_notes.items()},
               "patched_qml": {"commit": source["patch"]["upstream_commit"],
                               "source_commit": source["source"]["commit"],
                               "binary_sha256": runtime_files["Qt6Qml.dll"]["sha256"]},
               "sdk_artifact": {k: v for k, v in lock["sdk_artifact"].items() if k != "files"},
               "exclusions": manifest["exclusions"]}
    write_new(output / "qt-source-bundle.json", json_bytes(receipt))
    return receipt


def package_file_map(manifest):
    require(manifest.get("schema") == 1 and isinstance(manifest.get("files"), list),
            "PackageManifestSchemaMismatch")
    result, folded = {}, set()
    for row in manifest["files"]:
        require(isinstance(row, dict) and isinstance(row.get("sha256"), str),
                "PackageManifestEntryRejected")
        name = relative_name(row["path"])
        require(name.casefold() not in folded and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
                "PackageManifestEntryRejected")
        folded.add(name.casefold())
        result[name] = row["sha256"]
    return result


def verify_package(args):
    _, lock = source_lock()
    directory = plain_path(args.bundle_dir)
    receipt = read_json(directory / "qt-source-bundle.json")
    require(receipt.get("schema") == 1 and receipt.get("status") == "complete",
            "SourceBundleReceiptIncomplete")
    archive = receipt["archive"]
    require("/" not in relative_name(archive["filename"]), "SourceArchiveFilenameRejected")
    require(file_identity(directory / archive["filename"])
            == {k: archive[k] for k in ("bytes", "sha256")}, "SourceBundleIdentityMismatch")
    with zipfile.ZipFile(directory / archive["filename"]) as container:
        member = container.getinfo("bundle-manifest.json")
        require(member.file_size <= 32 * 1024**2, "BundleManifestBoundExceeded")
        bound = json.loads(container.read(member))
    require(bound.get("schema") == 1 and bound.get("source_sha") == receipt["source_sha"]
            and bound.get("runtime_files") == receipt["runtime_files"]
            and bound.get("runtime_content_id") == receipt["runtime_content_id"]
            == sha(canonical(receipt["runtime_files"])), "SourceBundleReceiptMismatch")
    package_path, delivery_path = plain_path(args.package_manifest), plain_path(args.delivery)
    require(package_path.stat().st_size <= 32 * 1024**2
            and delivery_path.stat().st_size <= 32 * 1024**2, "JsonInputBoundExceeded")
    package_bytes, delivery_bytes = package_path.read_bytes(), delivery_path.read_bytes()
    manifest = json.loads(package_bytes.decode("utf-8-sig"))
    delivery = json.loads(delivery_bytes.decode("utf-8-sig"))
    require(manifest.get("source_sha") == receipt["source_sha"]
            and delivery.get("source_sha") == receipt["source_sha"], "PackageSourceIdentityMismatch")
    require(delivery.get("qt") == lock["qt_version"]
            and re.fullmatch(r"[0-9a-f]{64}", delivery.get("installer_sha256", "")) is not None,
            "InstallerDeliveryIdentityMissing")
    require(delivery.get("qt_source_archive") == archive
            and delivery.get("qt_source_manifest_sha256")
            == file_identity(directory / "qt-source-bundle.json")["sha256"],
            "DeliverySourceBindingMismatch")
    packaged = package_file_map(manifest)
    qt_files = {n for n in packaged if classify_runtime(n, lock["runtime_rules"]) is not None}
    require(qt_files == set(receipt["runtime_files"]), "PackagedQtClosureChanged")
    for name, row in {**receipt["runtime_files"], **receipt["installer_notes"]}.items():
        require(packaged.get(name) == row["sha256"], "PackagedQtOrSourceNoticeChanged")
    # The delivery receipt, not this source tool, records the real installer.
    # Preserve its exact identity instead of inventing an EXE from a workflow URL.
    # Later installation tests update the workflow's delivery.json. Preserve
    # the packaging-time bytes here; their hash must remain independently
    # reproducible after those later results have been recorded.
    package_snapshot, delivery_snapshot = "package-manifest-snapshot.json", "delivery-packaging-snapshot.json"
    write_new(directory / package_snapshot, package_bytes)
    write_new(directory / delivery_snapshot, delivery_bytes)
    result = {"schema": 1, "status": "complete", "source_sha": receipt["source_sha"],
              "scope": "Initial installer/package/source binding; delivery_receipt is a packaging-time "
                       "snapshot; workflow final conclusion is not checked here.",
              "source_archive": archive,
              "package_manifest": {"filename": package_snapshot, "bytes": len(package_bytes),
                                   "sha256": sha(package_bytes)},
              "delivery_receipt": {"filename": delivery_snapshot, "bytes": len(delivery_bytes),
                                   "sha256": sha(delivery_bytes)}, "delivery": delivery,
              "stable_delivery_fields": {key: delivery[key] for key in
                                         ("source_sha", "installer_sha256", "qt_source_archive",
                                          "qt_source_manifest_sha256")},
              "runtime_content_id": receipt["runtime_content_id"],
              "qt_file_count": len(qt_files), "note_file_count": len(receipt["installer_notes"]),
              "installer_bytes_read_here": False,
              "whole_workflow_final_conclusion_checked_here": False}
    write_new(directory / "package-binding.json", json_bytes(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    before = sub.add_parser("prepare")
    for name in ("runtime-dir", "source-sha", "sdk-evidence", "cache-dir", "output-dir"):
        before.add_argument("--" + name, required=True)
    after = sub.add_parser("verify-package")
    for name in ("bundle-dir", "package-manifest", "delivery"):
        after.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(args) if args.operation == "prepare" else verify_package(args)
    except (SourceError, OSError, ValueError, KeyError, TypeError, AttributeError,
            tarfile.TarError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "failed", "code": str(error) if isinstance(error, SourceError)
                          else type(error).__name__}), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "source_sha": result["source_sha"],
                      "archive": result.get("archive", result.get("source_archive"))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
