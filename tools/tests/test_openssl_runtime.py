"""Offline security and cache checks for the pinned OpenSSL runtime builder.

Fixtures use only an explicit scratch directory. Synthetic PE files are never
loaded: runtime probes and downloads are mocked. No compiler or network runs.
"""

import argparse
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "Build-OpenSslRuntime.py"
PRODUCTION_LOCK = SCRIPT.with_name("openssl-runtime.lock.json")
SPEC = importlib.util.spec_from_file_location("openssl_runtime_builder", SCRIPT)
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)
REAL_PROBE = runtime.probe_runtime
SCRATCH = None


def pe_fixture(machine=0x8664, *, dll=True, magic=0x20B):
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<H", data, 132, machine)
    struct.pack_into("<H", data, 150, 0x2000 if dll else 0x0002)
    struct.pack_into("<H", data, 152, magic)
    return bytes(data)


class OpenSslRuntimeBoundaries(unittest.TestCase):
    def setUp(self):
        if SCRATCH is None:
            raise RuntimeError("Run this script with an explicit --scratch-root")
        self.temporary = tempfile.TemporaryDirectory(prefix="case-", dir=SCRATCH)
        self.root = Path(self.temporary.name).resolve()
        if not self.root.is_relative_to(SCRATCH):
            raise RuntimeError("Fixture escaped selected scratch root")
        self.payload = self.root / "runtime"
        self.payload.mkdir()
        self.license = b"Unmodified upstream-license fixture\n"
        self.lock = runtime.read_json(PRODUCTION_LOCK)
        self.lock["license_sha256"] = hashlib.sha256(self.license).hexdigest()
        self.lock_path = self.root / "fixture-lock.json"
        self.lock_path.write_text(json.dumps(self.lock), encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.object(runtime, "LOCK", self.lock_path).start()
        self.observed = {"version": "OpenSSL 3.5.9 fixture", "tls_context_created": True}
        self.probe = patch.object(runtime, "probe_runtime", return_value=self.observed).start()
        self.download = patch.object(runtime, "urlopen",
                                     side_effect=AssertionError("Unexpected network access")).start()
        self.junctions = []

    def tearDown(self):
        for link in reversed(self.junctions):
            if link.exists() and runtime.linked(link):
                link.rmdir()
        if not self.root.resolve().is_relative_to(SCRATCH):
            raise RuntimeError("Unexpected test cleanup path")
        self.temporary.cleanup()

    def receipt(self, target="mingw64"):
        tools = {"compiler", "make", "assembler", "perl"}
        if target == "mingw64":
            tools.add("shell")
        toolchain = {name: {"file": name + ".exe", "sha256": "a" * 64,
                            "version": "controlled tool fixture"} for name in tools}
        for name in runtime.FILES:
            file = self.payload / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(pe_fixture() if name.endswith(".dll") else
                             self.license if name.endswith("LICENSE.txt") else runtime.notice(self.lock))
        value = {"schema_version": 1, "status": "success", "version": self.lock["version"],
                 "target": target, "source": deepcopy(self.lock["source"]),
                 "signature_verified": False, "recipe_sha256": runtime.sha256(SCRIPT),
                 "lock_sha256": runtime.sha256(self.lock_path), "toolchain": toolchain,
                 "cache_key": runtime.runtime_cache_key(self.lock, target, toolchain),
                 "configure_options": [target, "shared", "no-tests"],
                 "runtime_probe": deepcopy(self.observed), "files": {}}
        self.refresh_files(value)
        self.save(value)
        return value

    def refresh_files(self, value):
        value["files"] = {name: {"sha256": runtime.sha256(self.payload / name),
                                 "size": (self.payload / name).stat().st_size}
                          for name in runtime.FILES}

    def save(self, value):
        (self.payload / "openssl-runtime.json").write_text(json.dumps(value), encoding="utf-8")

    def rejected(self, value):
        self.save(value)
        self.probe.reset_mock()
        with self.assertRaises((ValueError, OSError)):
            runtime.validate_runtime(self.payload, self.lock, "mingw64")
        self.probe.assert_not_called()

    def archive(self, members, name="source.tar.gz"):
        path = self.root / name
        with tarfile.open(path, "w:gz") as archive:
            for member, data in members:
                member.size = len(data) if member.isfile() else 0
                archive.addfile(member, io.BytesIO(data) if member.isfile() else None)
        return path

    def junction(self, link, target):
        environment = dict(os.environ, SSL_TEST_LINK=str(link), SSL_TEST_TARGET=str(target))
        subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        "New-Item -ItemType Junction -Path $env:SSL_TEST_LINK -Target $env:SSL_TEST_TARGET | Out-Null"],
                       env=environment, check=True, capture_output=True, text=True, timeout=30)
        self.junctions.append(link)
        self.assertTrue(runtime.linked(link))

    def test_production_lock_pins_supported_official_source_and_original_license(self):
        lock = runtime.read_json(PRODUCTION_LOCK)
        self.assertEqual(lock["version"], "3.5.9")
        self.assertEqual(lock["source"]["url"],
                         "https://github.com/openssl/openssl/releases/download/openssl-3.5.9/openssl-3.5.9.tar.gz")
        self.assertEqual(lock["source"]["sha256"],
                         "603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a")
        self.assertEqual(lock["license_sha256"],
                         "7d5450cb2d142651b8afa315b5f238efc805dad827d91ba367d8516bc9d49e7a")

    def test_complete_receipt_verifies_both_supported_targets_without_loading_dlls(self):
        for target in ("mingw64", "VC-WIN64A"):
            with self.subTest(target=target):
                value = self.receipt(target)
                self.assertEqual(runtime.validate_runtime(self.payload, self.lock, target,
                                                         value["cache_key"]), value)
        self.assertEqual(self.probe.call_count, 2)
        self.download.assert_not_called()

    def test_verify_only_cli_revalidates_without_build_tools_downloads_or_writes(self):
        value = self.receipt()
        before = {str(p.relative_to(self.payload)): runtime.sha256(p)
                  for p in self.payload.rglob("*") if p.is_file()}
        output = io.StringIO()
        with patch.object(sys, "argv", [str(SCRIPT), "--output", str(self.payload),
                         "--target", "mingw64", "--verify-only"]), \
             patch.object(runtime, "build") as build, patch.object(runtime, "tool") as tool, \
             patch.object(runtime, "download_source") as source, redirect_stdout(output):
            self.assertEqual(runtime.main(), 0)
            build.assert_not_called()
            tool.assert_not_called()
            source.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual((result["status"], result["version"], result["target"], result["cache_key"]),
                         ("success", "3.5.9", "mingw64", value["cache_key"]))
        self.probe.assert_called_once_with(self.payload)
        self.assertEqual(before, {str(p.relative_to(self.payload)): runtime.sha256(p)
                                  for p in self.payload.rglob("*") if p.is_file()})

    def test_source_recipe_lock_target_and_cache_identities_cannot_drift(self):
        original = self.receipt()
        changes = {"schema_version": 2, "status": "partial", "version": "3.0.16",
                   "target": "VC-WIN64A", "recipe_sha256": "0" * 64,
                   "lock_sha256": "0" * 64, "cache_key": "0" * 64,
                   "signature_verified": True, "configure_options": ["mingw64", "shared", "no-asm"],
                   "source": {**original["source"], "sha256": "0" * 64}}
        for name, replacement in changes.items():
            with self.subTest(field=name):
                value = deepcopy(original)
                value[name] = replacement
                self.rejected(value)
        value = deepcopy(original)
        value["unexpected"] = "not a receipt field"
        self.rejected(value)
        self.save(original)
        with self.assertRaises(ValueError):
            runtime.validate_runtime(self.payload, self.lock, "mingw64", "f" * 64)

    def test_toolchain_must_remain_portable_and_match_cached_inputs(self):
        original = self.receipt()
        for replacement in ({}, {"file": "C:/host/cl.exe", "sha256": "a" * 64, "version": "x"},
                            {"file": "cl.exe", "sha256": "not a digest", "version": "x"}):
            with self.subTest(record=replacement):
                value = deepcopy(original)
                value["toolchain"]["compiler"] = replacement
                value["cache_key"] = runtime.runtime_cache_key(self.lock, "mingw64", value["toolchain"])
                self.rejected(value)
        value = deepcopy(original)
        value["toolchain"]["compiler"]["version"] = "different compiler"
        self.rejected(value)

    def test_missing_runtime_files_fail_even_when_removed_from_receipt(self):
        for name in runtime.FILES:
            with self.subTest(file=name):
                value = self.receipt()
                (self.payload / name).unlink()
                value["files"].pop(name)
                self.rejected(value)

    def test_tampered_runtime_files_never_reach_the_probe(self):
        for name in runtime.FILES:
            with self.subTest(file=name):
                value = self.receipt()
                with (self.payload / name).open("ab") as output:
                    output.write(b"tampered")
                self.rejected(value)

    def test_receipt_cannot_add_path_traversal_ads_or_case_colliding_files(self):
        original = self.receipt()
        for path in ("../outside.dll", "C:/outside.dll", "bin/a.dll:stream",
                     "bin/LIBSSL-3-X64.DLL", "bin/./libssl-3-x64.dll"):
            with self.subTest(path=path):
                value = deepcopy(original)
                value["files"][path] = {"sha256": "a" * 64, "size": 1}
                self.rejected(value)

    def test_unlisted_files_are_rejected_only_in_deployable_root(self):
        original = self.receipt()
        sibling = self.payload.with_name(self.payload.name + "-build")
        sibling.mkdir()
        (sibling / "compiler.log").write_text("build evidence", encoding="utf-8")
        runtime.validate_runtime(self.payload, self.lock, "mingw64")
        for name in ("private.dpapi", "bin/ambient.dll", "licenses/unlisted.txt"):
            with self.subTest(path=name):
                file = self.payload / name
                file.write_bytes(b"must not be deployed")
                try:
                    self.rejected(original)
                finally:
                    file.unlink()

    def test_wrong_machine_non_dll_or_non_pe_cannot_be_rehashed_into_valid_receipt(self):
        samples = [pe_fixture(0x14C), pe_fixture(dll=False), pe_fixture(magic=0x10B), b"not a PE"]
        for data in samples:
            with self.subTest(header=data[:2]):
                value = self.receipt()
                (self.payload / runtime.FILES[0]).write_bytes(data)
                self.refresh_files(value)
                self.rejected(value)

    def test_pe_parser_rejects_truncated_or_redirected_headers(self):
        sample = self.root / "header.dll"
        valid = pe_fixture()
        self.assertEqual(runtime.pe_machine(self._write(sample, valid)), 0x8664)
        invalid_offset = bytearray(valid)
        struct.pack_into("<I", invalid_offset, 60, 0xFFFF)
        for data in (valid[:63], bytes(invalid_offset), valid[:128] + b"NOPE" + valid[132:]):
            with self.subTest(size=len(data)):
                with self.assertRaises(ValueError):
                    runtime.pe_machine(self._write(sample, data))

    @staticmethod
    def _write(path, data):
        path.write_bytes(data)
        return path

    def test_license_and_swirl_notice_must_match_their_independent_expectations(self):
        for name in ("licenses/LICENSE.txt", "licenses/NOTICE.txt"):
            with self.subTest(file=name):
                value = self.receipt()
                (self.payload / name).write_bytes(b"replacement license or notice")
                self.refresh_files(value)
                self.rejected(value)
        note = runtime.notice(self.lock)
        self.assertIn(b"written by Swirl, not an upstream NOTICE", note)
        self.assertIn(self.lock["source"]["sha256"].encode(), note)

    def test_cached_receipt_still_probes_actual_runtime_version_and_tls(self):
        for observed in ({"version": "OpenSSL 3.0.16 fixture", "tls_context_created": True},
                         {"version": "OpenSSL 3.5.9 fixture", "tls_context_created": False}):
            with self.subTest(observed=observed):
                value = self.receipt()
                value["runtime_probe"] = observed
                self.save(value)
                self.probe.return_value = observed
                with self.assertRaises(ValueError):
                    runtime.validate_runtime(self.payload, self.lock, "mingw64")
        self.probe.return_value = self.observed

    def test_duplicate_or_malformed_receipt_json_is_rejected_before_probe(self):
        self.receipt()
        path = self.payload / "openssl-runtime.json"
        for data in ('{"status":"success","status":"partial"}',
                     '{"files":{"duplicate":1,"duplicate":2}}', "not JSON"):
            with self.subTest(document=data):
                path.write_text(data, encoding="utf-8")
                self.probe.reset_mock()
                with self.assertRaises(ValueError):
                    runtime.read_json(path)
                with self.assertRaises(ValueError):
                    runtime.validate_runtime(self.payload, self.lock, "mingw64")
                self.probe.assert_not_called()
        path.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            runtime.validate_runtime(self.payload, self.lock, "mingw64")

    def test_runtime_probe_uses_fresh_isolated_child_and_no_ambient_ssl_environment(self):
        self.receipt()
        contamination = {"SystemRoot": str(self.root / "Windows"), "PATH": "untrusted ambient path",
                         "OPENSSL_CONF": "private.cnf", "OPENSSL_MODULES": "ambient providers",
                         "OPENSSL_ENGINES": "ambient engines", "OPENSSL_EXTRA": "not inherited",
                         "SSL_CERT_FILE": "private roots", "SSL_CERT_DIR": "private directory"}
        with patch.dict(os.environ, contamination), patch.object(runtime.subprocess, "run",
             return_value=SimpleNamespace(stdout=json.dumps(self.observed))) as child:
            self.assertEqual(REAL_PROBE(self.payload), self.observed)
        argv, = child.call_args.args
        env = child.call_args.kwargs["env"]
        self.assertEqual(argv[:4], [sys.executable, "-I", "-S", "-c"])
        self.assertEqual(argv[-1], str(self.payload / "bin"))
        self.assertIn('p/"libcrypto-3-x64.dll"', argv[4])
        self.assertIn('p/"libssl-3-x64.dll"', argv[4])
        self.assertIn("winmode=0x1100", argv[4])
        self.assertEqual(env["PATH"].split(os.pathsep),
                         [str(self.payload / "bin"), str(self.root / "Windows/System32")])
        self.assertEqual(env["OPENSSL_CONF"], "NUL")
        self.assertEqual(env["OPENSSL_MODULES"], str(self.payload / "bin"))
        self.assertNotIn("OPENSSL_EXTRA", env)
        self.assertNotIn("SSL_CERT_FILE", env)
        self.assertNotIn("SSL_CERT_DIR", env)
        self.assertTrue(child.call_args.kwargs["check"])

    def test_verified_download_and_cache_do_not_use_an_unchecked_archive(self):
        data = b"official-source fixture bytes"
        lock = deepcopy(self.lock)
        lock["source"]["sha256"] = hashlib.sha256(data).hexdigest()
        def response(*unused_args, **unused_kwargs):
            stream = io.BytesIO(data)
            stream.url = lock["source"]["url"]
            return stream
        self.download.side_effect = response
        folder = self.root / "download"
        path = runtime.download_source(lock, folder)
        self.assertEqual(path.read_bytes(), data)
        self.download.assert_called_once()
        self.download.reset_mock()
        self.download.side_effect = AssertionError("Cached archive should be verified locally")
        self.assertEqual(runtime.download_source(lock, folder), path)
        self.download.assert_not_called()
        path.write_bytes(b"tampered cache")
        with self.assertRaisesRegex(ValueError, "Cached source archive SHA256 mismatch"):
            runtime.download_source(lock, folder)
        self.download.assert_not_called()

    def test_wrong_download_hash_or_https_downgrade_never_promotes_an_archive(self):
        for label, url, content in (("wrong-hash", self.lock["source"]["url"], b"wrong bytes"),
                                    ("downgrade", "http://example.invalid/source", b"unused")):
            with self.subTest(case=label):
                def response(*unused_args, **unused_kwargs):
                    stream = io.BytesIO(content)
                    stream.url = url
                    return stream
                self.download.side_effect = response
                folder = self.root / label
                lock = deepcopy(self.lock)
                if label == "downgrade":
                    lock["source"]["sha256"] = hashlib.sha256(content).hexdigest()
                with self.assertRaises(ValueError):
                    runtime.download_source(lock, folder)
                self.assertFalse((folder / (self.lock["source"]["root_directory"] + ".tar.gz")).exists())
        lock = deepcopy(self.lock)
        lock["source"]["url"] = "http://example.invalid/source.tar.gz"
        self.download.reset_mock()
        with self.assertRaisesRegex(ValueError, "Source URL must be HTTPS"):
            runtime.download_source(lock, self.root / "insecure-url")
        self.download.assert_not_called()

    def test_regular_source_archive_stays_under_the_expected_root(self):
        root_name = self.lock["source"]["root_directory"]
        archive = self.archive([(tarfile.TarInfo(root_name + "/Configure"), b"source fixture")])
        output = self.root / "extract"
        source = runtime.extract_source(archive, output, root_name)
        self.assertEqual(source, output / root_name)
        self.assertEqual((source / "Configure").read_bytes(), b"source fixture")

    def test_archive_traversal_absolute_ads_reserved_and_foreign_roots_are_rejected(self):
        root_name = self.lock["source"]["root_directory"]
        sentinel = self.root / "sentinel.txt"
        sentinel.write_bytes(b"untouched")
        names = ("../sentinel.txt", root_name + "/../../sentinel.txt", "/absolute.txt",
                 "C:/absolute.txt", root_name + "\\..\\sentinel.txt", root_name + "/a:stream",
                 root_name + "/CON.txt", root_name + "/trailing. ", "other-root/Configure")
        for index, name in enumerate(names):
            with self.subTest(member=name):
                archive = self.archive([(tarfile.TarInfo(name), b"bad")], f"bad-{index}.tar.gz")
                with self.assertRaises(ValueError):
                    runtime.extract_source(archive, self.root / f"extract-{index}", root_name)
                self.assertEqual(sentinel.read_bytes(), b"untouched")

    def test_archive_links_special_files_and_case_duplicates_are_rejected(self):
        root_name = self.lock["source"]["root_directory"]
        for index, kind in enumerate((tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE)):
            with self.subTest(kind=kind):
                entry = tarfile.TarInfo(root_name + "/redirect")
                entry.type, entry.linkname = kind, "../outside"
                archive = self.archive([(entry, b"")], f"link-{index}.tar.gz")
                with self.assertRaises(ValueError):
                    runtime.extract_source(archive, self.root / f"links-{index}", root_name)
        archive = self.archive([(tarfile.TarInfo(root_name + "/file.txt"), b"first"),
                                (tarfile.TarInfo(root_name + "/FILE.txt"), b"second")], "duplicate.tar.gz")
        with self.assertRaises(ValueError):
            runtime.extract_source(archive, self.root / "duplicate", root_name)
        self.assertEqual((self.root / "duplicate" / root_name / "file.txt").read_bytes(), b"first")

    @unittest.skipUnless(os.name == "nt", "Windows reparse-point boundary")
    def test_linked_runtime_directory_never_reads_or_probes_outside_payload(self):
        value = self.receipt()
        outside = self.root / "outside-runtime"
        (self.payload / "bin").rename(outside)
        self.junction(self.payload / "bin", outside)
        self.rejected(value)

    @unittest.skipUnless(os.name == "nt", "Windows reparse-point boundary")
    def test_linked_build_output_is_rejected_before_tool_or_source_discovery(self):
        outside = self.root / "outside-output"
        outside.mkdir()
        link = self.root / "linked-output"
        self.junction(link, outside)
        with patch.object(runtime, "tool") as tool, patch.object(runtime, "download_source") as download:
            with self.assertRaises(ValueError):
                runtime.build(SimpleNamespace(output=link, target="mingw64", parallel=1))
            tool.assert_not_called()
            download.assert_not_called()
        self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows compiler-toolchain selection")
    def test_mingw_rejects_native_perl_msys_gcc_and_native_make_before_downloading(self):
        tools = self.root / "tools"
        tools.mkdir()
        for name in ("perl", "gcc", "make", "as", "sh"):
            (tools / (name + ".exe")).write_bytes(b"controlled build-tool identity")
        cases = (("MSWin32 v5.40.0", "x86_64-w64-mingw32", "GNU Make for msys", "MSYS/Cygwin Perl"),
                 ("msys v5.40.0", "x86_64-pc-msys", "GNU Make for msys", "x86_64-w64-mingw32 compiler"),
                 ("msys v5.40.0", "x86_64-w64-mingw32", "GNU Make for Windows", "matching POSIX GNU make"))
        for perl, machine, make, expected in cases:
            with self.subTest(perl=perl, machine=machine, make=make):
                def run(argv, **unused):
                    name = Path(argv[0]).stem
                    text = {"perl": perl, "gcc": machine if "-dumpmachine" in argv else "15.1.0",
                            "make": make, "sh": "GNU bash for msys", "as": "GNU assembler x86_64-w64-mingw32"}[name]
                    return SimpleNamespace(stdout=text, returncode=0)
                with patch.object(runtime, "tool", side_effect=lambda name, env_name=None: tools / (name + ".exe")), \
                     patch.object(runtime.subprocess, "run", side_effect=run) as command, \
                     patch.object(runtime, "download_source") as download, \
                     patch.dict(os.environ, {"CFLAGS": "ambient compiler flags", "CL": "ambient MSVC flags"}):
                    with self.assertRaisesRegex(RuntimeError, expected):
                        runtime.build(SimpleNamespace(output=self.payload, target="mingw64", parallel=1))
                    download.assert_not_called()
                    for call in command.call_args_list:
                        self.assertNotIn("CFLAGS", call.kwargs["env"])
                        self.assertNotIn("CL", call.kwargs["env"])
                        self.assertEqual(call.kwargs["env"]["LC_ALL"], "C")
                self.probe.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows compiler-toolchain selection")
    def test_mingw_accepts_consistent_msys_and_cygwin_tool_identities_before_source_download(self):
        tools = self.root / "posix-tools"
        tools.mkdir()
        for name in ("perl", "gcc", "make", "as", "sh"):
            (tools / (name + ".exe")).write_bytes(b"controlled build-tool identity")
        for platform in ("msys", "cygwin"):
            with self.subTest(platform=platform):
                def run(argv, **unused):
                    name = Path(argv[0]).stem
                    text = {"perl": platform + " v5.42.3",
                            "gcc": "x86_64-w64-mingw32" if "-dumpmachine" in argv else "15.1.0",
                            "make": "GNU Make 4.4.1\nBuilt for x86_64-pc-" + platform,
                            "sh": "GNU bash, version 5.3.20 (x86_64-pc-" + platform + ")",
                            "as": "GNU assembler x86_64-w64-mingw32"}[name]
                    return SimpleNamespace(stdout=text, returncode=0)
                with patch.object(runtime, "tool", side_effect=lambda name, env_name=None: tools / (name + ".exe")), \
                     patch.object(runtime.subprocess, "run", side_effect=run), \
                     patch.object(runtime, "download_source", side_effect=RuntimeError("controlled source boundary")) as download:
                    with self.assertRaisesRegex(RuntimeError, "controlled source boundary"):
                        runtime.build(SimpleNamespace(output=self.payload, target="mingw64", parallel=1))
                    download.assert_called_once()
                self.probe.assert_not_called()

    def test_invalid_target_or_parallel_count_never_starts_a_build(self):
        for extra in (("--target", "x86"), ("--parallel", "0"), ("--parallel", "65")):
            argv = [str(SCRIPT), "--output", str(self.payload), "--target", "mingw64", *extra]
            with self.subTest(arguments=extra), patch.object(sys, "argv", argv), \
                 patch.object(runtime, "build") as build, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    runtime.main()
                self.assertEqual(failure.exception.code, 2)
                build.assert_not_called()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-root", type=Path, required=True)
    args = parser.parse_args()
    SCRATCH = args.scratch_root.resolve()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    unittest.main(argv=[sys.argv[0]], verbosity=2)
