#!/usr/bin/env python3
"""Run the existing independent Windows Qt fixtures and require all nine slots.

Every subprocess is real. The observer only adds a second Qt XML output and
checks it; existing peer traffic assertions, credentials, deadlines and tests
remain unchanged. Missing fixtures, skips and failed public networking fail.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import runpy
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SLOTS = frozenset({
    "subscriptionProductChainAgainstIndependentPeer",
    "publicRealityProductChainAgainstIndependentPeer",
    "realityLifecycleProductChainAgainstIndependentPeer",
    "socks5UdpThroughIndependentPeer", "socks4ThroughIndependentPeer",
    "webSocketThroughIndependentPeer", "vlessThroughIndependentPeer",
    "shadowsocksThroughIndependentPeer", "loonShadowsocksThroughIndependentPeer",
})
LIFECYCLE_MODES = frozenset({"tls12", "http-control", "authentication-failure", "cancel", "reject"})
BASIC_TESTS = (
    "test_shadowsocks.ShadowsocksTests.test_qt_facade_http_obfs_with_udp_declared",
    "test_rust_core.RustCoreIntegration.test_vless_qt_data_path",
    "test_socks4.Socks4Integration.test_qt_imported_socks4_and_4a_data_path",
    "test_websocket_transport.WebSocketTransportTests.test_qt_vless_websocket_data_path",
    "test_socks5_udp.Socks5UdpIntegration.test_qt_imported_socks5_udp_data_path",
    "test_product_subscription_chain.ProductQtIntegration",
)


def fixture_slots(source: str) -> set[str]:
    functions = list(re.finditer(r"(?m)^\s*void\s+(\w+)\(\)\s*\{", source))
    return {match[1] for index, match in enumerate(functions)
            if "QSKIP(" in source[match.end():functions[index + 1].start()
                                  if index + 1 < len(functions) else len(source)]}


def verified_xml(path: Path, expected: list[str], qt_version: str, *, observation=None) -> dict:
    if not path.is_file() or not 0 < path.stat().st_size <= 16 * 1024 * 1024:
        raise AssertionError("Required Qt fixture XML missing or oversized")
    root = ET.parse(path).getroot()
    actual_version = root.findtext("./Environment/QtVersion")
    skipped = [item for item in root.iter() if item.get("type", "").lower() == "skip"]
    incidents = list(root.iter("Incident"))
    if observation is not None:
        # Record observed skips even when validation fails. A missing or invalid
        # document leaves the count unknown, never an invented zero.
        observation.update(qt_version=actual_version, skipped=len(skipped), xml_observed=True)
    if actual_version != qt_version:
        raise AssertionError(f"Fixture used Qt {actual_version}, expected {qt_version}")
    if skipped or not incidents or any(item.get("type") != "pass" for item in incidents):
        raise AssertionError("Qt fixture failed, skipped or omitted pass evidence")
    for name in expected:
        functions = [item for item in root.findall("TestFunction") if item.get("name") == name]
        if len(functions) != 1 or [item.get("type") for item in functions[0].findall("Incident")] != ["pass"]:
            raise AssertionError(f"Qt fixture slot was not executed exactly once: {name}")
    return {"slots": expected, "qt_version": actual_version, "skipped": 0, "success": True}


class Tee(io.StringIO):
    def __init__(self, output):
        super().__init__()
        self.output = output

    def write(self, text):
        self.output.write(text)
        self.output.flush()
        return super().write(text)


class QtObserver:
    def __init__(self, binary: Path, output: Path, qt_version: str):
        self.binary, self.output, self.qt_version = binary.resolve(), output, qt_version
        self.original_run = subprocess.run
        self.calls: list[dict] = []
        self.stage = "unassigned"

    def run(self, args, *positional, **kwargs):
        if not isinstance(args, (list, tuple)) or not args or Path(args[0]).resolve() != self.binary:
            return self.original_run(args, *positional, **kwargs)
        names = []
        for argument in args[1:]:
            if str(argument).startswith("-"):
                break
            names.append(str(argument))
        if not names or len(set(names)) != len(names) or not set(names) <= SLOTS:
            raise AssertionError("Unexpected Qt fixture invocation")
        folder = self.output / "qt-xml"
        folder.mkdir(exist_ok=True)
        path = folder / f"{len(self.calls) + 1:03d}-{self.stage}.xml"
        row = {"stage": self.stage, "slots": names, "xml": str(path.relative_to(self.output)),
               "success": False, "exit_code": None, "skipped": None, "xml_observed": False}
        self.calls.append(row)
        environment = kwargs.get("env", os.environ)
        if "realityLifecycleProductChainAgainstIndependentPeer" in names:
            fixture = Path(environment["SWIRL_QT_LIFECYCLE_FIXTURE"])
            if not 0 < fixture.stat().st_size <= 4 * 1024 * 1024:
                raise AssertionError("Lifecycle fixture size")
            mode = json.loads(fixture.read_text(encoding="utf-8"))["mode"]
            if mode not in LIFECYCLE_MODES:
                raise AssertionError("Unknown lifecycle mode")
            row["lifecycle_mode"] = mode
        started = time.monotonic()
        try:
            # Keep the original text/XML log arguments and all subprocess options.
            # QTest supports multiple explicit outputs, so the existing harness
            # still examines its own original report and observed peer traffic.
            result = self.original_run([*args, "-o", str(path) + ",xml"], *positional, **kwargs)
            row["exit_code"] = result.returncode
            row.update(verified_xml(path, names, self.qt_version, observation=row))
            if result.returncode:
                row["success"] = False
                raise AssertionError("Qt fixture subprocess failed")
            return result
        finally:
            row["elapsed_seconds"] = round(time.monotonic() - started, 3)


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qt-version", default="6.11.3")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema": 1, "success": False, "platform": platform.platform(),
              "required_slots": sorted(SLOTS), "required_slot_count": len(SLOTS),
              "stages": [], "qt_calls": [], "provider_credentials_used": False,
              "physical_windows_verified": False}
    observer = None
    try:
        if os.name != "nt":
            raise RuntimeError("Actual Windows Qt/DPAPI fixtures require Windows")
        source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        report["source_sha"] = source
        if source != os.environ.get("SWIRL_SOURCE_SHA") or source != os.environ.get("GITHUB_SHA"):
            raise RuntimeError("Fixture source SHA differs from the triggered commit")
        if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True):
            raise RuntimeError("Tracked source changed before Qt fixture regression")
        if fixture_slots((ROOT / "src/Swirl.Quick/tests/RustCoreTests.cpp").read_text(encoding="utf-8")) != SLOTS:
            raise RuntimeError("Qt conditional fixture inventory changed; update the explicit gate")
        binaries = {}
        for key in ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_QT_TESTS"):
            path = Path(os.environ[key]).resolve(strict=True)
            binaries[key] = {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        binary = Path(os.environ["SWIRL_RUST_QT_TESTS"])
        metadata = json.loads((binary.parent / "swirl-rust-build.json").read_text(encoding="utf-8-sig"))
        if metadata["source_sha"] != source or metadata["target"] != "x86_64-pc-windows-msvc" or metadata["abi_version"] != 1:
            raise RuntimeError("Qt fixture library is not the current paired Windows build")
        dll = binary.parent / "swirl_api.dll"
        report.update(binaries=binaries, rust=metadata, rust_dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest())
        observer = QtObserver(binary, output, args.qt_version)
        sys.path.insert(0, str(ROOT / "tools/tests"))
        os.environ["SWIRL_PRODUCT_EVIDENCE"] = str(output / "product-chain")

        def stage(name, callback):
            observer.stage = name
            started = time.monotonic()
            row = {"name": name, "success": False}
            report["stages"].append(row)
            log = Tee(sys.stdout)
            try:
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    callback(row)
                row["success"] = True
            except Exception as error:
                # Existing fixture harnesses redact their detailed logs. Do not
                # emit arbitrary exception payloads into this summary.
                row["failure_type"] = type(error).__name__
                print(f"Stage {name} failed: {type(error).__name__}", flush=True)
            finally:
                row["elapsed_seconds"] = round(time.monotonic() - started, 3)
                (output / (name + ".log")).write_text(log.getvalue(), encoding="utf-8")

        def basic(row):
            suite = unittest.defaultTestLoader.loadTestsFromNames(BASIC_TESTS)
            expected = suite.countTestCases()
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            row.update(expected=expected, executed=result.testsRun, skipped=len(result.skipped),
                       failures=len(result.failures), errors=len(result.errors))
            if expected != 6 or result.testsRun != expected or result.skipped or not result.wasSuccessful():
                raise AssertionError("Required Qt basic/subscription fixture failed or skipped")

        def script(path, arguments):
            def execute(row):
                with patch.object(sys, "argv", [str(path), *arguments]):
                    try:
                        runpy.run_path(str(path), run_name="__main__")
                    except SystemExit as outcome:
                        row["exit_code"] = outcome.code
                        if outcome.code not in (None, 0):
                            raise AssertionError("Existing fixture gate failed") from None
            return execute

        with patch.object(subprocess, "run", observer.run):
            stage("basic-and-subscription", basic)
            for name, options in (("reality", []), ("vision", ["--vision"]),
                                  ("chrome-vision-lifecycle", ["--vision", "--fingerprint", "chrome"])):
                os.environ["SWIRL_REALITY_RUNTIME_EVIDENCE"] = str(output / name)
                stage(name, script(ROOT / "tools/tests/test_reality_runtime.py", ["--qt", *options]))
            stage("public-reality-vision", script(ROOT / "tools/Verify-PublicQtReality.py", [
                "--qt-tests", str(binary), "--xray-peer-dir", os.environ["SWIRL_XRAY_PEER_DIR"],
                "--output", str(output / "public-reality-report.json")]))
        covered = {name for call in observer.calls if call["success"] for name in call["slots"]}
        modes = {call["lifecycle_mode"] for call in observer.calls if call["success"] and "lifecycle_mode" in call}
        report.update(executed_slots=sorted(covered), executed_slot_count=len(covered),
                      missing_slots=sorted(SLOTS - covered), lifecycle_modes=sorted(modes),
                      incomplete_xml_evidence=sum(not call["xml_observed"] for call in observer.calls),
                      skipped=(sum(call["skipped"] for call in observer.calls)
                               if observer.calls and all(call["xml_observed"] for call in observer.calls) else None))
        report["success"] = (covered == SLOTS and modes == LIFECYCLE_MODES and
                             all(row["success"] for row in report["stages"]) and
                             bool(observer.calls) and all(call["success"] for call in observer.calls))
    except Exception as error:
        report["failure_type"] = type(error).__name__
    finally:
        if observer:
            report["qt_calls"] = observer.calls
        write_json(output / "result.json", report)
    print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
