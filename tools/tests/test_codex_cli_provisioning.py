"""Fail-closed tests for the downloaded native CLI fixture, without executing it."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('codex_provisioning',Path(__file__).parents[1]/'Install-CodexCli.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        raw=bytearray(128);raw[:2]=b'MZ';struct.pack_into('<I',raw,60,64);raw[64:70]=b'PE\x00\x00\x64\x86'
        self.binary=bytes(raw)
        self.expected={'name':'codex-x86_64-pc-windows-msvc.exe','size':len(raw),
                       'sha256':hashlib.sha256(raw).hexdigest()}
        self.destination=self.folder/'codex.exe'

    def archive(self,names=None,binary=None):
        path=self.folder/'fixture.tar.gz';raw=self.binary if binary is None else binary
        with tarfile.open(path,'w:gz') as package:
            for name in names or [self.expected['name']]:
                member=tarfile.TarInfo(name);member.size=len(raw)
                package.addfile(member,io.BytesIO(raw))
        return path

    def test_verified_native_fixture_is_copied_without_extracting_paths(self):
        receipt=p.extract_binary(self.archive(),self.expected,self.destination)
        self.assertEqual(self.destination.read_bytes(),self.binary)
        self.assertEqual(receipt['sha256'],self.expected['sha256'])
        self.assertEqual(receipt['pe_machine'],'0x8664')

    def test_changed_binary_bytes_are_rejected_before_publication(self):
        corrupt=self.binary[:-1]+b'X'
        with self.assertRaisesRegex(p.ProvisionError,'BinaryDigestMismatch'):
            p.extract_binary(self.archive(binary=corrupt),self.expected,self.destination)
        self.assertFalse(self.destination.exists());self.assertFalse(self.destination.with_suffix('.partial').exists())

    def test_traversal_and_duplicate_members_are_rejected(self):
        for names in (['../codex.exe'],[self.expected['name'],self.expected['name']]):
            with self.subTest(names=names),self.assertRaisesRegex(p.ProvisionError,'ArchiveMemberMismatch'):
                p.extract_binary(self.archive(names=names),self.expected,self.destination)
            self.assertFalse(self.destination.exists())

    def test_wrong_native_architecture_is_rejected_even_with_matching_digest(self):
        raw=self.binary[:68]+b'\x64\xaa'+self.binary[70:]
        expected={**self.expected,'sha256':hashlib.sha256(raw).hexdigest()}
        with self.assertRaisesRegex(p.ProvisionError,'WindowsX64Required'):
            p.extract_binary(self.archive(binary=raw),expected,self.destination)
        self.assertFalse(self.destination.exists())

    def test_existing_executable_is_not_overwritten(self):
        self.destination.write_bytes(b'existing')
        with self.assertRaisesRegex(p.ProvisionError,'FreshFixtureDestinationRequired'):
            p.extract_binary(self.archive(),self.expected,self.destination)
        self.assertEqual(self.destination.read_bytes(),b'existing')

    def test_existing_partial_file_is_not_removed(self):
        partial=self.destination.with_suffix('.partial');partial.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            p.extract_binary(self.archive(),self.expected,self.destination)
        self.assertEqual(partial.read_bytes(),b'existing');self.assertFalse(self.destination.exists())

    def test_floating_or_nonofficial_download_is_rejected(self):
        lock=p.read_lock(Path(__file__).parents[1]/'codex-cli-windows.lock.json')
        for url in ('https://github.com/openai/codex/releases/latest/download/codex.exe',
                    'https://example.invalid/codex.exe'):
            with self.subTest(url=url):
                lock['archive']['url']=url
                path=self.folder/'changed-lock.json';path.write_text(json.dumps(lock),encoding='utf-8')
                with self.assertRaisesRegex(p.ProvisionError,'PinnedAssetRequired'):p.read_lock(path)


if __name__=='__main__':unittest.main(verbosity=2)
