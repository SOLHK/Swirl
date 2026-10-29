"""Download hash-pinned native-protocol test servers, never client runtimes.

Only the host platform's official Hysteria distribution and historical TUIC
reference server are fetched. Identity commands run only after SHA-256 matches.
The protocol fixtures are responsible for running each binary in server mode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import urllib.request


MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024


def host_platform() -> str:
    systems = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}
    architectures = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}
    system = systems.get(platform.system())
    architecture = architectures.get(platform.machine().lower())
    if system is None or architecture is None:
        raise RuntimeError("Native peer assets are not pinned for this host platform")
    return f"{system}-{architecture}"


def download_peer(label: str, peer: dict, platform_key: str, destination: Path) -> dict:
    asset = peer["assets"].get(platform_key)
    if asset is None:
        raise RuntimeError(f"No pinned {label} server asset for {platform_key}")
    if not re.fullmatch(r"[a-f0-9]{64}", asset["sha256"]):
        raise RuntimeError("Invalid pinned SHA-256")
    url = f'https://github.com/{peer["repository"]}/releases/download/{peer["release"]}/{asset["name"]}'
    suffix = ".exe" if platform_key.startswith("windows-") else ""
    directory = destination / label
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / (peer["binary"] + suffix)
    digest = hashlib.sha256()
    total = 0
    temporary = None
    try:
        # Stream to a sibling temporary file. Do not execute or publish a
        # partially downloaded or unverified executable.
        with tempfile.NamedTemporaryFile(prefix="download-", suffix=suffix, dir=directory, delete=False) as output:
            temporary = Path(output.name)
            request = urllib.request.Request(url, headers={"User-Agent": "Swirl-independent-protocol-peer-tests"})
            with urllib.request.urlopen(request, timeout=60) as response:
                while block := response.read(64 * 1024):
                    total += len(block)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError("Native peer download exceeds the bounded size limit")
                    digest.update(block)
                    output.write(block)
        actual = digest.hexdigest()
        if actual != asset["sha256"]:
            raise RuntimeError(f"Pinned {label} server SHA-256 mismatch")
        temporary.chmod(0o755)
        result = subprocess.run([str(temporary), *peer["version_args"]],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=10)
        identity = (result.stdout + result.stderr).strip()
        if len(identity) > 65536:
            raise RuntimeError("Native peer identity output exceeds its bound")
        if any(value not in identity for value in peer.get("version_contains", [])):
            raise RuntimeError(f"Pinned {label} server identity mismatch")
        if "version_exact" in peer and identity != peer["version_exact"]:
            raise RuntimeError(f"Pinned {label} server identity mismatch")
        temporary.replace(binary)
        temporary = None
        print(f'{label}: {peer["version"]}, SHA-256 and executable identity verified', flush=True)
        return {"repository": peer["repository"], "release": peer["release"],
            "commit": peer["commit"], "protocol": peer["protocol"], "asset": asset["name"],
            "url": url, "sha256": actual, "bytes": total, "version_output": identity,
            "binary": str(binary), "environment": peer["environment"],
            "role": "independent server test peer only"}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    if "\n" in str(destination) or "\r" in str(destination):
        raise RuntimeError("Peer output path cannot contain a newline")
    lock = json.loads((Path(__file__).parent / "tests/native-protocol-peer-lock.json").read_text(encoding="utf-8"))
    if lock.get("schema") != 1 or set(lock.get("peers", {})) != {"hysteria2", "tuic"}:
        raise RuntimeError("Unsupported native peer lock schema")
    platform_key = host_platform()
    manifest = {"schema": 1, "platform": platform_key, "client_runtime": False, "peers": {}}
    # Both locked peer identities are checked before exporting any CI paths.
    for label, peer in lock["peers"].items():
        manifest["peers"][label] = download_peer(label, peer, platform_key, destination)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as output:
            for peer in manifest["peers"].values():
                output.write(f'{peer["environment"]}={peer["binary"]}\n')


if __name__ == "__main__":
    main()
