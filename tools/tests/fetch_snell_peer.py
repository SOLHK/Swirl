"""Download the pinned official Linux-amd64 test server, never a product core."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import platform
import urllib.request
import zipfile


def fetch(destination):
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise RuntimeError("Pinned official Snell fixture requires Linux amd64")
    lock = json.loads(Path(__file__).with_name("snell-peer-lock.json").read_text())
    request = urllib.request.Request(lock["url"], headers={"User-Agent": "Swirl-independent-interop"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != lock["archive_sha256"]:
        raise ValueError("Official Snell archive checksum or size mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = [entry for entry in archive.infolist()
                   if PurePosixPath(entry.filename).name == "snell-server" and not entry.is_dir()]
        if len(entries) != 1 or entries[0].file_size > 16 * 1024 * 1024:
            raise ValueError("Official archive requires exactly one bounded server binary")
        binary = archive.read(entries[0])
    if hashlib.sha256(binary).hexdigest() != lock["server_sha256"]:
        raise ValueError("Official Snell executable checksum mismatch")
    destination.mkdir(parents=True, exist_ok=True)
    executable = destination / "snell-server"
    executable.write_bytes(binary)
    executable.chmod(0o755)
    (destination / "snell-server-provenance.json").write_text(json.dumps({
        **lock, "server_sha256": hashlib.sha256(binary).hexdigest(),
    }, indent=2) + "\n", encoding="utf-8")
    print(executable)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    fetch(parser.parse_args().destination)
