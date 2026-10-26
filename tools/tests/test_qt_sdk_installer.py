"""Offline filesystem boundary checks for the official Qt SDK installer.

All fixtures stay under an explicitly selected scratch directory. No SDK,
network, user configuration, or existing installation is modified.
"""

import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "Install-QtSdk.py"
SPEC = importlib.util.spec_from_file_location("qt_sdk_installer", SCRIPT)
sdk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sdk)
SCRATCH = None


class QtSdkInstallerBoundaries(unittest.TestCase):
    def setUp(self):
        if SCRATCH is None:
            raise RuntimeError("Run this test script with an explicit --scratch-root")
        self.temporary = tempfile.TemporaryDirectory(prefix="case-", dir=SCRATCH)
        self.root = Path(self.temporary.name).resolve()
        if not self.root.is_relative_to(SCRATCH):
            raise RuntimeError("Fixture escaped the selected scratch directory")
        self.output = self.root / "output"
        self.output.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def assert_member_rejected(self, name, *, symlink=False):
        member = SimpleNamespace(filename=name, is_symlink=symlink,
                                 is_file=not symlink, is_directory=False)
        archive = MagicMock()
        archive.__enter__.return_value = archive
        archive.list.return_value = [member]
        with patch.object(sdk.py7zr, "SevenZipFile", return_value=archive):
            with self.assertRaises(ValueError):
                sdk.extract_archive(self.root / "untrusted.7z", self.output)
        archive.extractall.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_archive_parent_paths_are_rejected_before_extraction(self):
        for name in ("../escape.txt", "..\\escape.txt", "bin/../../escape.txt"):
            with self.subTest(name=name):
                self.assert_member_rejected(name)

    def test_archive_absolute_paths_and_ads_are_rejected(self):
        for name in ("/escape.txt", "C:\\escape.txt", "\\\\host\\share\\escape", "bin/a.dll:stream"):
            with self.subTest(name=name):
                self.assert_member_rejected(name)

    def test_archive_symlink_is_rejected_before_extraction(self):
        self.assert_member_rejected("bin/redirect", symlink=True)

    def test_regular_archive_extracts_only_inside_the_selected_root(self):
        archive_path = self.root / "regular.7z"
        with sdk.py7zr.SevenZipFile(archive_path, "w") as archive:
            archive.writestr(b"verified fixture", "bin/fixture.txt")
        sdk.extract_archive(archive_path, self.output)
        self.assertEqual((self.output / "bin/fixture.txt").read_bytes(), b"verified fixture")
        self.assertFalse((self.root / "fixture.txt").exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_existing_junction_cannot_redirect_installation_or_archive_members(self):
        kit = self.output / "6.12.0/msvc2022_64"
        kit.mkdir(parents=True)
        outside = self.root / "outside-output"
        outside.mkdir()
        link = kit / "bin"
        shell = "pwsh.exe" if os.environ.get("PSModulePath") else "powershell.exe"
        command = "New-Item -ItemType Junction -Path $env:SDK_TEST_LINK -Target $env:SDK_TEST_TARGET | Out-Null"
        environment = dict(os.environ, SDK_TEST_LINK=str(link), SDK_TEST_TARGET=str(outside))
        subprocess.run([shell, "-NoProfile", "-Command", command], env=environment,
                       check=True, capture_output=True, text=True, timeout=30)
        try:
            self.assertTrue(link.is_junction())
            with self.assertRaises(ValueError):
                sdk.safe_install_path(link, self.output)
            member = SimpleNamespace(filename="bin/escape.txt", is_symlink=False,
                                     is_file=True, is_directory=False)
            archive = MagicMock()
            archive.__enter__.return_value = archive
            archive.list.return_value = [member]
            with patch.object(sdk.py7zr, "SevenZipFile", return_value=archive):
                with self.assertRaises(ValueError):
                    sdk.extract_archive(self.root / "untrusted.7z", kit)
            archive.extractall.assert_not_called()
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            # Remove the junction itself before TemporaryDirectory cleans up.
            # Both link and target were created inside this one fixture.
            if link.is_junction():
                link.rmdir()

    def run_metadata(self, data):
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", [str(SCRIPT), "--version", "6.12.0",
                "--arch", "win64_msvc2022_64", "--output", str(self.output), "--modules"]))
            stack.enter_context(patch.object(sdk, "fetch", return_value=data))
            stack.enter_context(patch.object(sdk, "official_hash", return_value=hashlib.sha256(data).hexdigest()))
            download = stack.enter_context(patch.object(sdk, "download_archive"))
            with self.assertRaises(ValueError):
                sdk.main()
            download.assert_not_called()

    def test_metadata_cannot_choose_an_extraction_root(self):
        for destination in ("@TargetDir@/../outside-output", "C:/outside-output",
                            "@TargetDir@/6.12.0/msvc2022_64/../../outside-output"):
            with self.subTest(destination=destination):
                data = f"""<Updates><PackageUpdate>
                  <Name>qt.qt6.6120.win64_msvc2022_64</Name><Version>6.12.0-0</Version>
                  <DownloadableArchives>qtbase.7z</DownloadableArchives><Operations>
                  <Operation name="Extract"><Argument>{destination}</Argument>
                  <Argument>qtbase.7z</Argument></Operation></Operations>
                  </PackageUpdate></Updates>""".encode()
                self.run_metadata(data)

    def test_xml_external_entity_is_rejected(self):
        sentinel = self.root / "private-fixture.txt"
        sentinel.write_text("not metadata", encoding="utf-8")
        data = ('<!DOCTYPE Updates [<!ENTITY x SYSTEM "' + sentinel.as_uri() + '">]>'
                '<Updates>&x;</Updates>').encode()
        with patch.object(sys, "argv", [str(SCRIPT), "--version", "6.12.0", "--arch",
            "win64_msvc2022_64", "--output", str(self.output), "--modules"]), \
             patch.object(sdk, "fetch", return_value=data), \
             patch.object(sdk, "official_hash", return_value=hashlib.sha256(data).hexdigest()), \
             patch.object(sdk, "download_archive") as download:
            from defusedxml.common import DefusedXmlException
            with self.assertRaises(DefusedXmlException):
                sdk.main()
            download.assert_not_called()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "not metadata")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-root", required=True, type=Path)
    arguments = parser.parse_args()
    SCRATCH = arguments.scratch_root.resolve()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
