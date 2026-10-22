#!/usr/bin/env python3
"""The unchanged six official QUIC Core tests through the loaded Rust C ABI.

Requires SWIRL_NATIVE_LIBRARY plus the pinned HY2_SERVER/SWIRL_TUIC_SERVER.
SWIRL_QUIC_FFI_EVIDENCE selects an independent JSON receipt. This exercises the
exported dynamic-library functions; it does not launch Qt or test a public node.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

import test_quic_core as core_suite


ROOT = Path(__file__).resolve().parents[2]


class QuicFfiTests(core_suite.QuicCoreTests):
    evidence_env = "SWIRL_QUIC_FFI_EVIDENCE"

    @classmethod
    def setUpClass(cls):
        if not os.environ.get("SWIRL_NATIVE_LIBRARY"):
            raise RuntimeError("SWIRL_NATIVE_LIBRARY is required; no executable-host fallback")
        receipt = Path(os.environ.setdefault(cls.evidence_env, str(ROOT / "build/quic-ffi/results.json"))).resolve()
        if os.environ.get("SWIRL_QUIC_CORE_EVIDENCE") and receipt == Path(os.environ["SWIRL_QUIC_CORE_EVIDENCE"]).resolve():
            raise RuntimeError("C ABI evidence must not overwrite the original Core evidence")
        if receipt.exists():
            raise RuntimeError("Choose a new C ABI evidence path to preserve previous results")
        super().setUpClass()


class Output:
    def __init__(self, captured):
        self.captured = captured

    def write(self, value):
        self.captured.write(value)
        sys.stderr.write(value)

    def flush(self):
        sys.stderr.flush()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    destination = Path(os.environ.setdefault(QuicFfiTests.evidence_env,
                       str(ROOT / "build/quic-ffi/results.json"))).resolve()
    # Refuse collisions before running any test, including a failed setUpClass.
    if os.environ.get("SWIRL_QUIC_CORE_EVIDENCE") and destination == Path(os.environ["SWIRL_QUIC_CORE_EVIDENCE"]).resolve():
        raise RuntimeError("C ABI evidence must not overwrite the original Core evidence")
    if destination.exists():
        raise RuntimeError("Choose a new C ABI evidence path to preserve previous results")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QuicFfiTests)
    expected = suite.countTestCases()
    if expected != 6:
        raise RuntimeError("Reassess the official Core test count before changing this acceptance gate")
    captured = io.StringIO()
    began = time.monotonic()
    result = unittest.TextTestRunner(stream=Output(captured), verbosity=2).run(suite)
    duration = time.monotonic() - began
    destination.parent.mkdir(parents=True, exist_ok=True)
    receipt = json.loads(destination.read_text(encoding="utf-8")) if destination.exists() else {}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=5, check=True).stdout.strip()
    changed = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"],
                             cwd=ROOT, capture_output=True, text=True, timeout=5, check=True).stdout.splitlines()
    receipt.update({"evidence_level": "exported_c_abi_official_quic_loopback",
                    "tests_run": result.testsRun, "expected_tests": expected,
                    "failures": len(result.failures), "errors": len(result.errors),
                    "skipped": len(result.skipped), "duration_seconds": round(duration, 3),
                    "successful": result.wasSuccessful() and not result.skipped and result.testsRun == expected,
                    "source_commit": revision, "worktree_changes": changed,
                    "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in (
                        Path(__file__).resolve(), ROOT / "tools/tests/native_ffi_host.py",
                        ROOT / "tools/tests/test_quic_core.py", ROOT / "core/Cargo.lock",
                        ROOT / "core/crates/swirl-api/src/lib.rs")},
                    "public_network_tested": False, "qt_product_acceptance": False})
    destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    destination.with_suffix(".log").write_text(captured.getvalue(), encoding="utf-8")
    return 0 if receipt["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
