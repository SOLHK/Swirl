#!/usr/bin/env python3
"""Verify the locally built Qt 6.12.0 backports and their matching source bundle.

The older, separately pinned MSVC SDK workflow keeps its original admission
policy. This recipe binds this MinGW build to reviewed source, patches and DLLs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


HERE = Path(__file__).resolve().parent
LOCK = HERE / "qt612-backports.lock.json"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def verify(kit, runtime=None, source_bundle=None):
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["qt_version"] == "6.12.0" and lock["compiler"] == "GNU 15.1.0",
            "Unexpected Qt backport recipe")
    for patch in lock["patches"]:
        require(digest(HERE.parent / patch["path"]) == patch["sha256"], "Patch identity changed")
    kit = kit.resolve(strict=True)
    for name, expected in lock["kit_files"].items():
        require(digest(kit / name) == expected, "Qt kit identity changed: " + name)
    if runtime is None:
        return
    runtime = runtime.resolve(strict=True)
    require(source_bundle is not None and digest(source_bundle) == lock["source_bundle"]["sha256"],
            "Matching Qt corresponding-source archive is required")
    checked = {}
    for file in sorted(runtime.rglob("*")):
        if not file.is_file():
            continue
        name = file.relative_to(runtime).as_posix()
        if file.parent == runtime and file.name.startswith("Qt6") and file.suffix == ".dll":
            sdk_name = "bin/" + name
        elif name.startswith("qml/"):
            sdk_name = name
        elif name.split("/")[0] in {"platforms", "tls", "networkinformation", "imageformats", "iconengines", "generic"}:
            sdk_name = "plugins/" + name
        else:
            continue
        require(digest(file) == digest(kit / sdk_name), "Deployed Qt file differs: " + name)
        checked[name] = digest(file)
    require({"Qt6Core.dll", "Qt6Network.dll", "Qt6Qml.dll", "Qt6Quick.dll"} <= checked.keys(),
            "Required Qt modules are missing")
    # Copy original notices only from the verified corresponding-source bundle.
    licenses = runtime / "licenses" / "qt-backports"
    licenses.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(source_bundle) as archive:
        for module in ("qtbase", "qtdeclarative"):
            for name in archive.namelist():
                if name.startswith(module + "/LICENSES/") and not name.endswith("/"):
                    target = licenses / module / Path(name).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
    receipt = {"schema": 1, "qt_version": lock["qt_version"], "compiler": lock["compiler"],
               "lock_sha256": digest(LOCK), "source_bundle": lock["source_bundle"],
               "sources": lock["sources"], "patches": lock["patches"],
               "verified_runtime_files": checked}
    (runtime / "qt-backports.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(HERE / "QT612-BACKPORTS.md", licenses / "BUILD-AND-SOURCE.md")
    print(json.dumps({"qt_version": "6.12.0", "runtime_files_verified": len(checked),
                      "source_sha256": lock["source_bundle"]["sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--source-bundle", type=Path)
    args = parser.parse_args()
    verify(args.kit, args.runtime, args.source_bundle)
