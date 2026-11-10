"""Install a digest-pinned official Windows Codex CLI into a CI fixture directory.

No global installation, PATH changes, login, or user configuration access. The
download and extracted executable must both match independently published hashes.
Only this executable is copied out of the archive; tar paths are never extracted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tarfile
import tempfile
import urllib.request


class ProvisionError(Exception):
    pass


def file_sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_lock(path):
    lock = json.loads(Path(path).read_text(encoding='utf-8'))
    if lock.get('schema') != 1 or lock.get('repository') != 'openai/codex':
        raise ProvisionError('OfficialCodexLockRequired')
    version = lock.get('version', '')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ProvisionError('FixedReleaseRequired')
    tag = 'rust-v' + version
    prefix = 'https://github.com/openai/codex/releases/'
    if (lock.get('release_tag') != tag or lock.get('version_output') != 'codex-cli ' + version
            or lock.get('release_url') != prefix + 'tag/' + tag
            or lock.get('release_api_url') != 'https://api.github.com/repos/openai/codex/releases/tags/' + tag):
        raise ProvisionError('ReleaseIdentityMismatch')
    for field in ('tag_object_sha', 'source_commit'):
        if not re.fullmatch(r'[a-f0-9]{40}', lock.get(field, '')):
            raise ProvisionError('CommitIdentityRequired')
    for kind, name in (('archive', 'codex-x86_64-pc-windows-msvc.exe.tar.gz'),
                       ('binary', 'codex-x86_64-pc-windows-msvc.exe')):
        asset = lock[kind]
        if (asset.get('name') != name or not isinstance(asset.get('asset_id'), int)
                or not isinstance(asset.get('size'), int) or not 0 < asset['size'] < 1024 ** 3
                or not re.fullmatch(r'[a-f0-9]{64}', asset.get('sha256', ''))
                or asset.get('url') != prefix + 'download/' + tag + '/' + name):
            raise ProvisionError('PinnedAssetRequired')
    if lock['binary'].get('pe_machine') != '0x8664':
        raise ProvisionError('WindowsX64Required')
    return lock


def github_json(url):
    if not url.startswith('https://api.github.com/repos/openai/codex/'):
        raise ProvisionError('OfficialApiRequired')
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'Swirl-Codex-Fixture',
               'X-GitHub-Api-Version': '2022-11-28'}
    token = os.environ.get('GH_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ProvisionError('ReleaseMetadataBounds')
    return json.loads(raw)


def verify_release_metadata(lock):
    release = github_json(lock['release_api_url'])
    if (release.get('id') != lock['release_id'] or release.get('tag_name') != lock['release_tag']
            or release.get('draft') or release.get('prerelease')
            or release.get('html_url') != lock['release_url']):
        raise ProvisionError('OfficialReleaseMismatch')
    for kind in ('archive', 'binary'):
        expected = lock[kind]
        matches = [asset for asset in release.get('assets', []) if asset.get('id') == expected['asset_id']]
        if len(matches) != 1:
            raise ProvisionError('OfficialAssetMissing')
        actual = matches[0]
        if (actual.get('name') != expected['name'] or actual.get('size') != expected['size']
                or actual.get('digest') != 'sha256:' + expected['sha256']
                or actual.get('browser_download_url') != expected['url']):
            raise ProvisionError('OfficialAssetMismatch')
    ref = github_json('https://api.github.com/repos/openai/codex/git/ref/tags/' + lock['release_tag'])
    if ref.get('object') != {'sha': lock['tag_object_sha'], 'type': 'tag',
                            'url': 'https://api.github.com/repos/openai/codex/git/tags/' + lock['tag_object_sha']}:
        raise ProvisionError('OfficialTagMismatch')
    tag = github_json('https://api.github.com/repos/openai/codex/git/tags/' + lock['tag_object_sha'])
    if tag.get('object', {}).get('type') != 'commit' or tag['object'].get('sha') != lock['source_commit']:
        raise ProvisionError('OfficialCommitMismatch')
    return {'release_id': release['id'], 'release_tag': release['tag_name'],
            'published_at': release['published_at'], 'source_commit': tag['object']['sha'],
            'tag_signature_verified': tag.get('verification', {}).get('verified', False),
            'archive_asset_id': lock['archive']['asset_id'], 'binary_asset_id': lock['binary']['asset_id'],
            'official_asset_digests_match': True}


def download_archive(asset, destination):
    request = urllib.request.Request(asset['url'], headers={'User-Agent': 'Swirl-Codex-Fixture'})
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=120) as response, Path(destination).open('xb') as output:
        if not response.geturl().startswith('https://'):
            raise ProvisionError('HttpsDownloadRequired')
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > asset['size']:
                raise ProvisionError('DownloadSizeMismatch')
            digest.update(chunk)
            output.write(chunk)
    if size != asset['size'] or digest.hexdigest() != asset['sha256']:
        raise ProvisionError('DownloadDigestMismatch')
    return {'size': size, 'sha256': digest.hexdigest()}


def verify_pe_x64(path):
    with Path(path).open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise ProvisionError('NativePeRequired')
        offset = struct.unpack_from('<I', header, 60)[0]
        if offset < 64 or offset > 1024 * 1024:
            raise ProvisionError('NativePeRequired')
        stream.seek(offset)
        if stream.read(6) != b'PE\x00\x00\x64\x86':
            raise ProvisionError('WindowsX64Required')


def extract_binary(archive, expected, destination):
    destination = Path(destination)
    if destination.exists():
        raise ProvisionError('FreshFixtureDestinationRequired')
    temporary = destination.with_suffix('.partial')
    created = False
    try:
        with tarfile.open(archive, 'r:gz') as package:
            members = package.getmembers()
            if (len(members) != 1 or not members[0].isfile()
                    or members[0].name != expected['name'] or members[0].size != expected['size']):
                raise ProvisionError('ArchiveMemberMismatch')
            with package.extractfile(members[0]) as source, temporary.open('xb') as output:
                created = True
                shutil.copyfileobj(source, output, 1024 * 1024)
        if temporary.stat().st_size != expected['size'] or file_sha256(temporary) != expected['sha256']:
            raise ProvisionError('BinaryDigestMismatch')
        verify_pe_x64(temporary)
        temporary.replace(destination)
    finally:
        if created:
            temporary.unlink(missing_ok=True)
    return {'path': str(destination), 'size': destination.stat().st_size,
            'sha256': file_sha256(destination), 'pe_machine': '0x8664'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=Path(__file__).with_name('codex-cli-windows.lock.json'))
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    receipt = {'schema': 1, 'status': 'failed', 'source_sha': os.environ.get('GITHUB_SHA'),
               'run_id': os.environ.get('GITHUB_RUN_ID'), 'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
               'recorded_at': datetime.now(timezone.utc).isoformat()}
    try:
        lock = read_lock(args.lock)
        receipt['lock_sha256'] = file_sha256(args.lock)
        receipt['release_url'] = lock['release_url']
        receipt['release'] = verify_release_metadata(lock)
        destination = args.destination.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='codex-download-', dir=destination) as temporary:
            archive = Path(temporary) / lock['archive']['name']
            receipt['archive'] = download_archive(lock['archive'], archive)
            receipt['binary'] = extract_binary(archive, lock['binary'], destination / 'codex.exe')
        receipt['status'] = 'passed'
        print('Verified official Codex CLI ' + lock['version'] + ' executable SHA256 ' + receipt['binary']['sha256'])
        return 0
    except Exception as error:
        # Never print signed redirect URLs, tokens, or HTTP response bodies.
        receipt['error'] = str(error) if isinstance(error, ProvisionError) else type(error).__name__
        print('Codex CLI provisioning failed: ' + receipt['error'])
        return 1
    finally:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
