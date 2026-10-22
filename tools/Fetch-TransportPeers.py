"""Fetch hash-locked independent test servers; never used by the Swirl product."""
import argparse
import hashlib
import io
import json
import os
import platform
import subprocess
import urllib.request
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads((Path(__file__).parent / 'tests/transport-peer-lock.json').read_text())
    os_name = {'Linux': 'linux', 'Windows': 'windows', 'Darwin': 'macos'}[platform.system()]
    arch = 'arm64-v8a' if platform.machine().lower() in ('arm64', 'aarch64') else '64'
    platform_key = f'{os_name}-{arch}'
    manifest = {'schema': 1, 'platform': platform_key, 'peers': {}}
    for label, peer in lock['peers'].items():
        expected = peer['sha256'][platform_key]
        url = f"https://github.com/XTLS/Xray-core/releases/download/{peer['release']}/Xray-{platform_key}.zip"
        with urllib.request.urlopen(url, timeout=60) as response:
            archive = response.read(128 * 1024 * 1024 + 1)
        if len(archive) > 128 * 1024 * 1024 or hashlib.sha256(archive).hexdigest() != expected:
            raise RuntimeError('Pinned Xray archive digest mismatch')
        directory = args.output.resolve() / label
        directory.mkdir(parents=True, exist_ok=True)
        binary_name = 'xray.exe' if os_name == 'windows' else 'xray'
        # Extract only the selected executable. No archive-controlled path is used.
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            executable = z.read(binary_name)
        binary = directory / binary_name
        binary.write_bytes(executable)
        binary.chmod(0o755)
        result = subprocess.run([str(binary), 'version'], check=True, capture_output=True, text=True, timeout=10)
        if peer['release'][1:] not in result.stdout or peer['commit'][:7] not in result.stdout:
            raise RuntimeError('Pinned Xray executable identity mismatch')
        manifest['peers'][label] = {**peer, 'archive_sha256': expected,
            'binary_sha256': hashlib.sha256(executable).hexdigest(), 'version': result.stdout.strip()}
        variable = 'SWIRL_XRAY_BINARY' if label == 'current' else 'SWIRL_XRAY_LEGACY_BINARY'
        if os.environ.get('GITHUB_ENV'):
            with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as output:
                output.write(f'{variable}={binary}\n')
        print(f'{label}: {peer["release"]} {peer["commit"]} SHA256 verified')
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
