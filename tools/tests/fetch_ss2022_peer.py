"""Fetch only the pinned official ssserver executable, verifying the archive.

Usage: python tools/tests/fetch_ss2022_peer.py OUTPUT_DIRECTORY
sslocal and other proxy clients are neither extracted nor executed.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import platform
import tarfile
import urllib.request
import zipfile


def fetch(destination):
    lock = json.loads(Path(__file__).with_name("ss2022-peer-lock.json").read_text())
    asset = lock["assets"][f"{platform.system()}-{platform.machine()}"]
    url = f"{lock['repository']}/releases/download/{lock['release']}/{asset['name']}"
    request = urllib.request.Request(url, headers={"User-Agent": "Swirl-independent-interop"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != asset["sha256"]:
        raise ValueError("official server archive checksum or size mismatch")
    binary_name = "ssserver.exe" if platform.system() == "Windows" else "ssserver"
    if asset["name"].endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if PurePosixPath(name).name == binary_name]
            if len(names) != 1:
                raise ValueError("archive does not contain exactly one ssserver")
            binary = archive.read(names[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as archive:
            entries = [entry for entry in archive.getmembers()
                       if PurePosixPath(entry.name).name == binary_name and entry.isfile()]
            if len(entries) != 1:
                raise ValueError("archive does not contain exactly one ssserver")
            binary = archive.extractfile(entries[0]).read()
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / binary_name
    output.write_bytes(binary)
    output.chmod(0o755)
    (destination / "ss2022-server-provenance.json").write_text(json.dumps({
        "url": url, "release": lock["release"], "license": lock["license"],
        "archive_sha256": asset["sha256"], "server_sha256": hashlib.sha256(binary).hexdigest(),
        "purpose": lock["purpose"],
    }, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    fetch(parser.parse_args().destination)
