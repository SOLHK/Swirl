"""Exercise CMake's dependency/deployment graph with an isolated fake Cargo.

These tests do not claim DLL loading or proxy connectivity. Those are checked by
the native Qt/Rust integration suites. Here the fake build tool lets us force a
failed Cargo build and missing output without corrupting the real build cache.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix" and shutil.which("cmake") and shutil.which("ninja"),
                     "portable graph fixture requires CMake, Ninja and POSIX executable scripts")
class RustBuildChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="swirl-rust-build-graph-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.quick = self.root / "src/Swirl.Quick"
        (self.quick / "cmake").mkdir(parents=True)
        (self.quick / "packaging/rules").mkdir(parents=True)
        (self.quick / "packaging/rules/fixture.txt").write_text("fixture rules")
        for name in ("SwirlRustCore.cmake", "RequireRustLibrary.cmake"):
            shutil.copyfile(ROOT / "src/Swirl.Quick/cmake" / name, self.quick / "cmake" / name)
        self.core = self.root / "core"
        (self.core / "crates/swirl-api/src").mkdir(parents=True)
        (self.core / "vendor/example/src").mkdir(parents=True)
        for path in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml",
                     "crates/swirl-api/Cargo.toml", "crates/swirl-api/src/lib.rs",
                     "crates/swirl-api/build.rs", "vendor/example/Cargo.toml", "vendor/example/src/lib.rs"):
            (self.core / path).write_text("fixture\n")
        self.fake_cargo = self.root / "cargo-fixture"
        self.fake_cargo.write_text(textwrap.dedent("""\
            #!/usr/bin/env python3
            import json, os, pathlib, sys
            root = pathlib.Path(__file__).parent
            args = sys.argv[1:]
            target_dir = pathlib.Path(args[args.index('--target-dir') + 1])
            target = args[args.index('--target') + 1]
            with (root / 'calls.jsonl').open('a') as stream:
                stream.write(json.dumps({'build_id': os.environ['SWIRL_BUILD_ID'],
                                         'source_sha': os.environ['SWIRL_SOURCE_SHA'],
                                         'args': args}) + '\\n')
            if (root / 'fail-cargo').exists():
                sys.exit(33)
            if (root / 'no-output').exists():
                sys.exit(0)
            suffix = 'dylib' if 'apple' in target else 'so'
            output = target_dir / target / 'release' / ('libswirl_api.' + suffix)
            body = os.environ['SWIRL_BUILD_ID'].encode().ljust(2048, b'x')
            output.parent.mkdir(parents=True, exist_ok=True)
            if not output.exists() or output.read_bytes() != body:
                output.write_bytes(body)
            """))
        self.fake_cargo.chmod(0o755)
        self.fake_rustc = self.root / "rustc-fixture"
        self.fake_rustc.write_text("#!/bin/sh\nprintf 'host: x86_64-unknown-linux-gnu\\n'\n")
        self.fake_rustc.chmod(0o755)
        (self.quick / "main.cpp").write_text("int main() { return 0; }\n")
        (self.quick / "CMakeLists.txt").write_text(textwrap.dedent("""\
            cmake_minimum_required(VERSION 3.25)
            project(RustGraphFixture LANGUAGES CXX)
            include(cmake/SwirlRustCore.cmake)
            add_executable(Swirl main.cpp)
            swirl_pair_rust_core(Swirl)
            swirl_stage_rust_core(Swirl)
            """))
        self.build = self.root / "build"
        self.run_command("git", "init", "-q", str(self.root))
        self.run_command("git", "-C", str(self.root), "add", ".")
        self.run_command("git", "-C", str(self.root), "-c", "user.name=Build Fixture",
                         "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        self.run_command("cmake", "-S", str(self.quick), "-B", str(self.build), "-G", "Ninja",
                         "-DSWIRL_CARGO=" + str(self.fake_cargo),
                         "-DSWIRL_RUSTC=" + str(self.fake_rustc))

    def run_command(self, *args, expect_success=True):
        result = subprocess.run(args, cwd=self.root, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=60)
        if expect_success:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def build_product(self, expect_success=True):
        return self.run_command("cmake", "--build", str(self.build), "--target", "Swirl",
                                expect_success=expect_success)

    def identity(self):
        return json.loads((self.build / "swirl-rust-build.json").read_text())

    def calls(self):
        return [json.loads(line) for line in (self.root / "calls.jsonl").read_text().splitlines()]

    def test_production_inputs_refresh_identity_and_missing_deployment_is_restored(self):
        self.build_product()
        first = self.identity()
        self.assertEqual(len(first["build_id"]), 64)
        self.assertEqual(len(first["source_sha"]), 40)
        deployed = self.build / "libswirl_api.so"
        self.assertEqual(deployed.read_bytes()[:64].decode(), first["build_id"])
        # An unchanged EXE still runs Cargo incrementally and restores a missing
        # deployed DLL. A POST_BUILD-only copy would not run in this situation.
        exe_time = (self.build / "Swirl").stat().st_mtime_ns
        deployed.unlink()
        self.build_product()
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual((self.build / "Swirl").stat().st_mtime_ns, exe_time)
        self.assertEqual(deployed.read_bytes()[:64].decode(), first["build_id"])
        previous = first["build_id"]
        for name in ("crates/swirl-api/src/lib.rs", "crates/swirl-api/build.rs",
                     "vendor/example/src/lib.rs", "Cargo.lock", "rust-toolchain.toml"):
            with (self.core / name).open("a") as stream:
                stream.write("changed\n")
            self.build_product()
            current = self.identity()["build_id"]
            self.assertNotEqual(current, previous, name)
            self.assertEqual(deployed.read_bytes()[:64].decode(), current)
            previous = current

    def test_cargo_failure_cannot_report_a_successful_product_build(self):
        self.build_product()
        (self.root / "fail-cargo").touch()
        result = self.build_product(expect_success=False)
        self.assertIn("FAILED", result.stdout)

    def test_success_without_the_required_library_is_fatal(self):
        (self.root / "no-output").touch()
        result = self.build_product(expect_success=False)
        self.assertIn("Cargo did not produce the required Rust Core library", result.stdout)
        self.assertFalse((self.build / "libswirl_api.so").exists())


if __name__ == "__main__":
    unittest.main()
