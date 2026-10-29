#!/usr/bin/env python3
"""Install a verified Windows Qt SDK from the official split repository.

Requires aqtinstall==3.3.0 and py7zr>=1.1.4. Its updater relocates the official SDK after
extraction; its older repository discovery is deliberately not used.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import time

from defusedxml import ElementTree
import py7zr
import requests


ARCHITECTURES = {
    "win64_mingw": ("mingw", "mingw_64"),
    "win64_msvc2022_64": ("msvc2022_64", "msvc2022_64"),
}
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]+$")


def fetch(url):
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=(20, 90))
            response.raise_for_status()
            return response.content
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def official_hash(url):
    value = fetch(url + ".sha256").decode("ascii").split()[0].lower()
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError(f"Invalid SHA256 response for {url}")
    return value


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_archive(entry, cache):
    expected = official_hash(entry["url"])
    destination = cache / entry["filename"]
    if not destination.exists() or sha256(destination) != expected:
        temporary = destination.with_suffix(destination.suffix + ".part")
        for attempt in range(3):
            try:
                with requests.get(entry["url"], stream=True, timeout=(20, 120)) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as output:
                        for chunk in response.iter_content(1024 * 1024):
                            output.write(chunk)
                actual = sha256(temporary)
                if actual != expected:
                    raise ValueError(f"SHA256 mismatch for {entry['filename']}")
                temporary.replace(destination)
                break
            except (requests.RequestException, ValueError):
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)
    print(f"Verified {entry['filename']}", flush=True)
    return dict(entry, sha256=expected, local_path=str(destination))


def extract_archive(path, destination):
    with py7zr.SevenZipFile(path, "r") as archive:
        for member in archive.list():
            name = member.filename.replace("\\", "/")
            relative = PurePosixPath(name)
            if (relative.is_absolute() or ".." in relative.parts or ":" in name
                    or member.is_symlink or not (member.is_file or member.is_directory)):
                raise ValueError(f"Unsafe archive member: {name}")
            resolved = (destination / Path(*relative.parts)).resolve()
            if not resolved.is_relative_to(destination):
                raise ValueError(f"Archive member escapes installation: {name}")
        archive.extractall(destination)


def safe_install_path(path, output):
    if not path.is_relative_to(output):
        raise ValueError(f"Installation path is outside selected output: {path}")
    if not path.resolve().is_relative_to(output):
        raise ValueError(f"Installation path escapes selected output: {path}")
    current = path
    while current != output:
        if current.is_symlink() or current.is_junction():
            raise ValueError(f"Linked installation directory is not allowed: {current}")
        current = current.parent
    return path.resolve()


def verify_install(kit, version):
    required = ["bin/qmake.exe", "bin/Qt6Core.dll", "bin/Qt6Gui.dll", "bin/Qt6Quick.dll",
                "bin/qt.conf", "lib/cmake/Qt6/Qt6ConfigVersionImpl.cmake",
                "lib/cmake/Qt6GuiPrivate/Qt6GuiPrivateConfig.cmake",
                "lib/cmake/Qt6ShaderTools/Qt6ShaderToolsConfig.cmake"]
    fingerprints = {relative: sha256(kit / relative) for relative in required}
    version_text = (kit / required[5]).read_text(encoding="utf-8")
    if not re.search(r'set\(PACKAGE_VERSION\s+"?' + re.escape(version) + r'"?\)', version_text):
        raise ValueError("Installed CMake package version does not match requested Qt")
    process_environment = dict(os.environ)
    process_environment["PATH"] = str(kit / "bin") + os.pathsep + process_environment.get("PATH", "")
    qmake_version = subprocess.check_output([str(kit / "bin/qmake.exe"), "-query", "QT_VERSION"],
                                           env=process_environment, text=True, timeout=30).strip()
    if qmake_version != version:
        raise ValueError(f"Installed qmake reported {qmake_version}")
    return fingerprints


def main():
    if tuple(map(int, py7zr.__version__.split(".")[:3])) < (1, 1, 4):
        raise RuntimeError("py7zr 1.1.4 or newer is required for secure archive extraction")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--arch", required=True, choices=ARCHITECTURES)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--modules", nargs="*", default=[])
    parser.add_argument("--archive-cache", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"6\.\d+\.\d+", args.version):
        parser.error("Use an explicit stable Qt 6 version, such as 6.12.0")
    if tuple(map(int, args.version.split("."))) < (6, 12, 0):
        parser.error("Swirl's current SDK baseline is Qt 6.12 or newer")
    if any(not re.fullmatch(r"qt[a-z0-9]+", name) for name in args.modules):
        parser.error("Module names must be Qt package identifiers")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = (args.archive_cache or output / "archives").resolve()
    cache.mkdir(parents=True, exist_ok=True)
    extension, kit_directory = ARCHITECTURES[args.arch]
    compact_version = args.version.replace(".", "")
    folder = f"qt6_{compact_version}"
    repository = ("https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/"
                  f"{folder}/{folder}_{extension}/")
    metadata_url = repository + "Updates.xml"
    metadata = fetch(metadata_url)
    metadata_sha256 = official_hash(metadata_url)
    if hashlib.sha256(metadata).hexdigest() != metadata_sha256:
        raise ValueError("Official Qt metadata failed SHA256 verification")
    metadata_path = output / f"qt-{args.version}-{args.arch}-Updates.xml"
    metadata_path.write_bytes(metadata)
    root = ElementTree.fromstring(metadata)
    packages = {node.findtext("Name"): node for node in root.findall("PackageUpdate")}
    names = [f"qt.qt6.{compact_version}.{args.arch}"]
    names += [f"qt.qt6.{compact_version}.addons.{module}.{args.arch}"
              for module in dict.fromkeys(["qtshadertools", *args.modules])]
    kit = output / args.version / kit_directory
    safe_install_path(kit, output)
    result_path = output / "sdk-install-result.json"
    if result_path.exists():
        saved = json.loads(result_path.read_text(encoding="utf-8"))
        if (saved.get("version") == args.version and saved.get("arch") == args.arch
                and saved.get("kit_root") == str(kit)
                and saved.get("metadata_sha256") == metadata_sha256
                and saved.get("package_names") == names):
            try:
                current_files = verify_install(kit, args.version)
            except (OSError, ValueError, subprocess.CalledProcessError):
                current_files = None
            if current_files and current_files == saved.get("files"):
                print(f"Verified cached Qt {args.version} SDK", flush=True)
                print(f"QT_SDK_ROOT={kit}", flush=True)
                return
    entries = []
    package_evidence = []
    for name in names:
        if name not in packages:
            raise ValueError(f"Missing requested Qt package: {name}")
        package = packages[name]
        version = package.findtext("Version", "")
        if not version.startswith(args.version + "-") or not SAFE_SEGMENT.fullmatch(version):
            raise ValueError(f"Unexpected package version: {version}")
        package_evidence.append({"name": name, "version": version,
                                 "display_name": package.findtext("DisplayName"),
                                 "dependencies": package.findtext("Dependencies")})
        extraction_paths = {}
        allowed_paths = {f"@TargetDir@/{args.version}/{kit_directory}": kit,
                         f"@TargetDir@/{args.version}/{kit_directory}/bin": kit / "bin"}
        for operation in package.findall("Operations/Operation"):
            if operation.get("name") != "Extract":
                continue
            arguments = [item.text for item in operation.findall("Argument")]
            if len(arguments) != 2 or arguments[0] not in allowed_paths:
                raise ValueError(f"Unexpected archive installation path in {name}")
            if arguments[1] in extraction_paths:
                raise ValueError(f"Duplicate archive extraction in {name}")
            extraction_paths[arguments[1]] = str(allowed_paths[arguments[0]])
        for archive in package.findtext("DownloadableArchives", "").split(","):
            archive = archive.strip()
            if not archive.endswith(".7z") or not SAFE_SEGMENT.fullmatch(archive):
                raise ValueError(f"Invalid archive filename in {name}: {archive}")
            if archive not in extraction_paths:
                raise ValueError(f"Missing extraction mapping for {archive}")
            filename = version + archive
            entries.append({"package": name, "filename": filename,
                            "url": repository + name + "/" + filename,
                            "extract_to": extraction_paths[archive]})
    with ThreadPoolExecutor(max_workers=3) as pool:
        verified = list(pool.map(lambda entry: download_archive(entry, cache), entries))
    for entry in verified:
        print(f"Extracting {entry['filename']}", flush=True)
        destination = safe_install_path(Path(entry["extract_to"]), output)
        destination.mkdir(parents=True, exist_ok=True)
        extract_archive(Path(entry["local_path"]), destination)
    from aqt.archives import TargetConfig
    from aqt.updater import Updater
    Updater.update(TargetConfig(args.version, "desktop", args.arch, "windows"), output, None)
    files = verify_install(kit, args.version)
    result = {"version": args.version, "arch": args.arch, "kit_root": str(kit),
              "metadata_url": metadata_url, "metadata_sha256": metadata_sha256,
              "packages": package_evidence, "package_names": names, "archives": verified,
              "qmake_version": args.version, "files": files}
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"QT_SDK_ROOT={kit}", flush=True)


if __name__ == "__main__":
    main()
