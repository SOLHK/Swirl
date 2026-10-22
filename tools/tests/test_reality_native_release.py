#!/usr/bin/env python3
"""Reuse production Core REALITY/Vision tests with a hash-pinned official release.

The older source-built oracle suite keeps its separate source/rebuild gate.
This entry point verifies the official release archive, or the provenance
manifest produced by Fetch-TransportPeers.py, before running the same Core
authentication, import, data, Direct, negative, and lifecycle assertions.
The reference executable is a server only. No Qt or public-node claim is made.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import platform
import ssl
import subprocess
import sys
import unittest
import zipfile

from test_reality_runtime import (
    EvidenceStream,
    RealityRuntimeInterop,
    VisionRuntimeInterop,
    write_json,
)
from test_reality_xray import executable, sha256


ROOT = Path(__file__).resolve().parents[2]
MAX_BINARY_BYTES = 128 * 1024 * 1024


def verified_release(evidence, fingerprint):
    required = ("SWIRL_XRAY_BINARY", "SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR")
    for name in required:
        if not os.environ.get(name):
            raise RuntimeError("Required native/release executable missing: " + name)
    binary = executable(Path(os.environ["SWIRL_XRAY_BINARY"]))
    lock_path = ROOT / "tools/tests/transport-peer-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    peer = lock["peers"]["current"]
    system = {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}[platform.system()]
    architecture = "arm64-v8a" if platform.machine().lower() in ("aarch64", "arm64") else "64"
    platform_key = f"{system}-{architecture}"
    expected_archive_sha256 = peer["sha256"][platform_key]
    binary_hash = sha256(binary)
    archive = os.environ.get("SWIRL_XRAY_RELEASE_ARCHIVE")
    manifest = os.environ.get("SWIRL_XRAY_RELEASE_MANIFEST")
    if bool(archive) == bool(manifest):
        raise RuntimeError("Provide exactly one verified release archive or fetch manifest")
    provenance = {"release": peer["release"], "commit": peer["commit"],
                  "platform": platform_key, "binary_sha256": binary_hash,
                  "archive_sha256": expected_archive_sha256, "lock_sha256": sha256(lock_path)}
    if archive:
        path = Path(archive).resolve(strict=True)
        if path.stat().st_size > MAX_BINARY_BYTES or sha256(path) != expected_archive_sha256:
            raise RuntimeError("Official Xray archive does not match the checked-in digest")
        with zipfile.ZipFile(path) as package:
            name = "xray.exe" if system == "windows" else "xray"
            entry = package.getinfo(name)
            if entry.file_size > MAX_BINARY_BYTES:
                raise RuntimeError("Official server executable exceeds the fixture size limit")
            import hashlib
            with package.open(entry) as source:
                archive_binary_hash = hashlib.file_digest(source, "sha256").hexdigest()
        if archive_binary_hash != binary_hash:
            raise RuntimeError("Xray executable differs from the pinned official archive")
        provenance["verification"] = "archive_digest_and_exact_binary_contents"
    else:
        path = Path(manifest).resolve(strict=True)
        document = json.loads(path.read_text(encoding="utf-8"))
        fetched = document["peers"]["current"]
        if (document.get("schema") != 1 or document.get("platform") != platform_key
                or any(fetched.get(key) != peer[key] for key in ("release", "commit", "sha256"))
                or fetched.get("archive_sha256") != expected_archive_sha256
                or fetched.get("binary_sha256") != binary_hash):
            raise RuntimeError("Xray fetch provenance differs from the pinned release or executable")
        provenance["verification"] = "Fetch-TransportPeers.py_manifest_and_binary_digest"
        provenance["manifest_sha256"] = sha256(path)
    version = subprocess.run([str(binary), "version"], capture_output=True, text=True,
                             check=True, timeout=10).stdout.strip()
    if f"Xray {peer['release'][1:]}" not in version or peer["commit"][:7] not in version:
        raise RuntimeError("Official Xray version differs from the locked release")
    provenance["version"] = version
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                              capture_output=True, check=True, timeout=5).stdout.strip()
    if os.environ.get("GITHUB_SHA", revision) != revision:
        raise RuntimeError("CI SHA does not match the checkout under test")
    changed = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                             cwd=ROOT, text=True, capture_output=True, check=True, timeout=5)
    binaries = {name: {"file": executable(Path(os.environ[name])).name,
                       "sha256": sha256(Path(os.environ[name]))} for name in required}
    write_json(evidence / "source-identity.json", {
        "git_sha": revision, "tracked_worktree_changes": changed.stdout.splitlines(),
        "binaries": binaries, "official_release": provenance,
        "test_sha256": sha256(Path(__file__)),
        "reused_test_sha256": sha256(ROOT / "tools/tests/test_reality_runtime.py"),
        "cargo_lock_sha256": sha256(ROOT / "core/Cargo.lock"),
        "python": sys.version, "openssl": ssl.OPENSSL_VERSION, "platform": sys.platform,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "scope": "production Rust Core JSON command host (Controller.dispatch; exported C ABI not exercised)",
        "public_network_tested": False, "qt_product_tested": False,
        "fingerprint": fingerprint,
        "client_hello_profile": "chrome_133" if fingerprint in ("chrome", "chrome_133") else "rustls",
    })
    return binary


class _OfficialReleaseSetup:
    @classmethod
    def setUpClass(cls):
        cls.evidence_root = Path(os.environ.get("SWIRL_REALITY_RUNTIME_EVIDENCE",
                                                ROOT / "build/reality-release-evidence")).resolve()
        cls.evidence_root.mkdir(parents=True, exist_ok=True)
        cls.xray = verified_release(cls.evidence_root, cls.fingerprint)


class RealityNativeReleaseInterop(_OfficialReleaseSetup, RealityRuntimeInterop):
    pass


class VisionNativeReleaseInterop(_OfficialReleaseSetup, VisionRuntimeInterop):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--fingerprint", choices=("rustls", "chrome", "chrome_133"), default="rustls")
    args = parser.parse_args()
    case = VisionNativeReleaseInterop if args.vision else RealityNativeReleaseInterop
    case.fingerprint = args.fingerprint
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(case)
    expected_count = suite.countTestCases()
    evidence = Path(os.environ.get("SWIRL_REALITY_RUNTIME_EVIDENCE",
                                   ROOT / "build/reality-release-evidence")).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    captured = io.StringIO()
    result = unittest.TextTestRunner(stream=EvidenceStream(sys.stderr, captured), verbosity=2).run(suite)
    (evidence / "tests.log").write_text(captured.getvalue(), encoding="utf-8")
    successful = result.wasSuccessful() and not result.skipped and result.testsRun == expected_count
    write_json(evidence / "test-summary.json", {
        "tests_run": result.testsRun, "expected_tests": expected_count,
        "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "successful": successful, "evidence_level": "independent_official_release_core_loopback",
        "protocol": "vless+reality+vision" if args.vision else "vless+reality",
        "fingerprint": args.fingerprint, "public_network_tested": False, "qt_product_tested": False,
    })
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
