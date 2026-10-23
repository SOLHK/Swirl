#!/usr/bin/env python3
"""Run the retained native suites omitted by the first U1 workflow inventory.

This only schedules existing assertions. Qt-only SOCKS4/WS methods have an
explicit assignment to Run-U1QtFixtures.py; all other methods must execute.
The strict VMess and public menus retain their real nonzero outcomes. A failed
menu does not stop evidence collection for independent menus in the workflow.

Runner APIs: https://docs.python.org/3/library/unittest.html
Failure scheduling: https://docs.github.com/en/actions/reference/workflows-and-actions/expressions
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import importlib
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


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tools/tests"
sys.path.insert(0, str(TESTS))

SUITES = {
    "reality-peer": ("test_reality_peer", ("RealityPeerSelfChecks",), 16),
    "reality-tls": ("test_reality_tls", ("RealityTlsInterop",), 19),
    "reality-xray": ("test_reality_xray", ("RealityXrayInterop",), 14),
    "reality-fingerprint": ("test_reality_fingerprint", ("RealityFingerprintInterop",), 4),
    "vision-xray": ("test_vision_xray", ("VisionXrayInterop",), 4),
    "socks4": ("test_socks4", ("Socks4Integration",), 9),
    "websocket": ("test_websocket_transport", ("WebSocketPeerTests", "WebSocketTransportTests"), 10),
    "strict-vmess": ("test_vmess_xray", ("VmessXrayHalfCloseTests",), 2),
}
QT_ASSIGNMENTS = {
    "test_socks4.Socks4Integration.test_qt_imported_socks4_and_4a_data_path": "socks4ThroughIndependentPeer",
    "test_websocket_transport.WebSocketTransportTests.test_qt_vless_websocket_data_path": "webSocketThroughIndependentPeer",
}
NATIVE_PARTITIONS = {
    "socks4": tuple("test_socks4.Socks4Integration." + name for name in (
        "test_inbound_ipv4_and_4a_fragmented_with_coalesced_payload",
        "test_outbound_v4_local_dns_and_4a_remote_dns",
        "test_subscription_candidates_forward_through_independent_peer",
        "test_rejected_or_wrong_version_upstream_never_falls_back",
        "test_password_protected_inbound_rejects_socks4",
        "test_invalid_command_userid_domain_and_zero_port_are_rejected",
        "test_ipv6_destination_rejected_before_proxy_connection",
        "test_existing_socks4_session_survives_atomic_update",
        "test_invalid_configuration_rejected_without_activation",
    )),
    "websocket": (
        "test_websocket_transport.WebSocketPeerTests.test_control_only_and_empty_frames_return_to_the_forwarding_loop",
        *("test_websocket_transport.WebSocketTransportTests." + name for name in (
            "test_vless_ws_wss_trojan_wss_forward_actual_origin_and_mask_frames",
            "test_fragmented_binary_messages_and_interleaved_ping_are_not_payload",
            "test_control_only_pong_does_not_block_the_origin_response_tail",
            "test_coalesced_ping_burst_preserves_the_connection_and_all_pongs",
            "test_bad_upgrades_fail_without_sending_credentials_or_origin_traffic",
            "test_malformed_frames_never_release_invalid_payload",
            "test_wss_verifies_name_and_trust_before_http_upgrade",
            "test_configuration_generation_preserves_existing_ws_stream",
            "test_stop_cancels_owned_ws_driver_and_releases_network",
        )),
    ),
}
PUBLIC_OPTIONS = {
    "public-reality": (),
    "public-vision": ("--vision",),
    "public-chrome": ("--fingerprint", "chrome"),
    "public-chrome-vision": ("--vision", "--fingerprint", "chrome"),
    "public-direct": (),
}
PHASES = ("deterministic", "strict-vmess", *PUBLIC_OPTIONS)


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True, timeout=10).strip()


def configure(output):
    suffix = ".exe" if os.name == "nt" else ""
    binary = Path(os.environ["SWIRL_RUST_BIN_DIR"]).resolve(strict=True)
    peer = Path(os.environ["SWIRL_XRAY_PEER_DIR"]).resolve(strict=True)
    release = Path(os.environ["SWIRL_XRAY_RELEASE_DIR"]).resolve(strict=True)
    library = "swirl_api.dll" if os.name == "nt" else ("libswirl_api.dylib" if sys.platform == "darwin" else "libswirl_api.so")
    paths = {"library": binary / library, **{
        name: binary / (name + suffix) for name in ("swirl-api", "swirl-inspect", "swirl-diagnose")}, **{
        name: binary / "examples" / (name + suffix)
        for name in ("reality-client", "reality-hello", "vision-client", "transport-client")}, **{
        "source-" + name: peer / (name + suffix) for name in ("xray", "reality-peer", "utls-hello")},
        "release-xray": release / "current" / ("xray" + suffix)}
    env = {
        "SWIRL_RUST_HARNESS": paths["swirl-api"], "SWIRL_RUST_INSPECTOR": paths["swirl-inspect"],
        "SWIRL_RUST_DIAGNOSTIC": paths["swirl-diagnose"], "SWIRL_REALITY_CLIENT": paths["reality-client"],
        "SWIRL_REALITY_HELLO": paths["reality-hello"], "SWIRL_VISION_CLIENT": paths["vision-client"],
        "SWIRL_TRANSPORT_CLIENT": paths["transport-client"], "SWIRL_XRAY_BINARY": paths["release-xray"],
        "SWIRL_XRAY_EVIDENCE": output / "reality-xray",
        "SWIRL_FINGERPRINT_EVIDENCE": output / "reality-fingerprint",
        "SWIRL_VISION_EVIDENCE": output / "vision-xray",
        "SWIRL_TRANSPORT_EVIDENCE": output / "strict-vmess",
        "SWIRL_VMESS_EVIDENCE": output / "strict-vmess",
    }
    os.environ.update({key: str(value) for key, value in env.items()})
    return paths, peer, release


def validate_source_peer(manifest, lock, revision, hashes):
    require(manifest.get("status") == "success" and manifest.get("schema_version") == 1,
            "SourcePeerBuildFailed")
    require(manifest.get("swirl_source_commit") == revision, "SourcePeerWrongSwirlCommit")
    require(manifest.get("go_version") == lock["go_version"] and
            manifest.get("xray") == lock["xray"] and manifest.get("reality") == lock["reality"],
            "SourcePeerLockMismatch")
    for key, role in (("xray", "source-xray"), ("reality_peer", "source-reality-peer"), ("utls_hello", "source-utls-hello")):
        binary = manifest["binaries"][key]
        repeat = manifest["reproducible_rebuild"][key]
        require(binary["sha256"] == hashes[role] and repeat.get("matches") is True and
                repeat["first_sha256"] == repeat["repeated_sha256"] == binary["sha256"],
                "SourcePeerBinaryOrRepeatMismatch")


def library_identity(path, revision):
    library = ctypes.CDLL(str(path))
    entry = library.swirl_core_build_info
    entry.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
    entry.restype = ctypes.c_ssize_t
    buffer = (ctypes.c_uint8 * 4096)()
    size = int(entry(buffer, len(buffer)))
    require(0 < size <= len(buffer), "RustLibraryIdentityLength")
    result = json.loads(bytes(buffer[:size]).decode("utf-8"))
    require(result.get("source_sha") == revision and result.get("abi_version") == 1 and
            bool(result.get("build_id")) and bool(result.get("target")), "RustLibraryIdentityMismatch")
    return result


def identity(paths, peer, release):
    revision = git("rev-parse", "HEAD")
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None and
            os.environ.get("SWIRL_SOURCE_SHA") == revision and
            os.environ.get("GITHUB_SHA", revision) == revision, "SourceShaMismatch")
    require(not git("diff", "--name-only", "HEAD", "--"), "TrackedSourceDirty")
    files = [*sorted(TESTS.glob("*.py")), ROOT / "core/Cargo.lock", Path(__file__),
             ROOT / "tools/Build-XrayPeer.py", ROOT / "tools/Fetch-TransportPeers.py",
             ROOT / "tools/Verify-PublicRustCore.py", ROOT / "tools/Verify-PublicRealityRuntime.py",
             TESTS / "xray_peer/lock.json", TESTS / "xray_peer/main.go",
             TESTS / "xray_peer/utls_hello/main.go", TESTS / "transport-peer-lock.json"]
    git("ls-files", "--error-unmatch", "--", *(str(path.relative_to(ROOT)) for path in files))
    hashes = {name: sha256(path.resolve(strict=True)) for name, path in paths.items()}
    lock = json.loads((TESTS / "xray_peer/lock.json").read_text(encoding="utf-8"))
    manifest_path = peer / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_source_peer(manifest, lock, revision, hashes)
    require(manifest["lock_sha256"] == sha256(TESTS / "xray_peer/lock.json") and
            manifest["helper_source_sha256"] == sha256(TESTS / "xray_peer/main.go") and
            manifest["utls_helper_source_sha256"] == sha256(TESTS / "xray_peer/utls_hello/main.go"),
            "SourcePeerInputChanged")
    release_path = release / "manifest.json"
    downloaded = json.loads(release_path.read_text(encoding="utf-8"))
    release_lock = json.loads((TESTS / "transport-peer-lock.json").read_text(encoding="utf-8"))["peers"]["current"]
    platform_key = {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}[platform.system()]
    platform_key += "-arm64-v8a" if platform.machine().lower() in ("arm64", "aarch64") else "-64"
    current = downloaded["peers"]["current"]
    require(downloaded.get("schema") == 1 and downloaded.get("platform") == platform_key and
            all(current.get(key) == release_lock[key] for key in ("release", "commit", "sha256")) and
            current.get("archive_sha256") == release_lock["sha256"][platform_key] and
            current.get("binary_sha256") == hashes["release-xray"], "ReleasePeerIdentityMismatch")
    return {"source_sha": revision, "tracked_source_clean": True, "core_tree": git("rev-parse", "HEAD:core"),
            "binary_sha256": hashes, "binary_paths": {name: str(path) for name, path in paths.items()},
            "rust_library_export": library_identity(paths["library"], revision),
            "example_source_sha_embedded": False,
            "example_identity_basis": "clean pinned checkout, workflow fresh locked Cargo build, source and binary hashes",
            "source_peer_manifest_sha256": sha256(manifest_path), "release_peer_manifest_sha256": sha256(release_path),
            "source_files_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in files},
            "python": sys.version, "python_binary_sha256": sha256(Path(sys.executable).resolve()),
            "rustc": subprocess.check_output(["rustc", "-vV"], text=True, timeout=10),
            "platform": platform.platform(), "os": platform.system(),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def planned_suite(name):
    module_name, classes, expected = SUITES[name]
    module = importlib.import_module(module_name)
    loader = unittest.TestLoader()
    complete = list(flatten(unittest.TestSuite(loader.loadTestsFromTestCase(getattr(module, cls)) for cls in classes)))
    ids = {test.id() for test in complete}
    assigned = {key: value for key, value in QT_ASSIGNMENTS.items() if key.startswith(module_name + ".")}
    selected = set(NATIVE_PARTITIONS[name]) if name in NATIVE_PARTITIONS else ids
    require(not (selected & assigned.keys()) and ids == selected | assigned.keys(), "SuitePartitionDrift")
    require(len(selected) == expected and len(ids) == len(complete), "SuiteInventoryCountDrift")
    return unittest.TestSuite(test for test in complete if test.id() in selected), sorted(selected), assigned


def observe_tests(callback, expected_ids, module_name):
    """Observe the original unittest runners; never change their assertions/results."""
    observations = []
    original_run, original_start = unittest.TextTestRunner.run, unittest.TextTestResult.startTest
    def normalized(identifier):
        return module_name + identifier[len("__main__"):] if identifier.startswith("__main__.") else identifier
    def start(result, test):
        observations[-1]["executed_ids"].append(normalized(test.id()))
        return original_start(result, test)
    def run(runner, suite):
        row = {"planned_ids": sorted(normalized(test.id()) for test in flatten(suite)), "executed_ids": []}
        observations.append(row)
        require(row["planned_ids"] == expected_ids, "ExecutedMenuDiffersFromInventory")
        result = original_run(runner, suite)
        row.update(executed=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   skipped=len(result.skipped), expected_failures=len(result.expectedFailures),
                   unexpected_successes=len(result.unexpectedSuccesses), successful=result.wasSuccessful())
        return result
    outcome = 0
    with patch.object(unittest.TextTestRunner, "run", run), patch.object(unittest.TextTestResult, "startTest", start):
        try:
            callback()
        except SystemExit as result:
            outcome = 0 if result.code is None else result.code
    successful = (outcome == 0 and len(observations) == 1 and observations[0].get("successful") is True and
                  observations[0].get("executed") == len(expected_ids) and
                  sorted(observations[0]["executed_ids"]) == expected_ids and
                  not any(observations[0].get(key) for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes")))
    return {"success": successful, "original_exit_code": outcome, "expected": len(expected_ids),
            "expected_ids": expected_ids, "runs": observations}


def script(path, arguments):
    with patch.object(sys, "argv", [str(path), *map(str, arguments)]):
        runpy.run_path(str(path), run_name="__main__")


class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, text):
        for stream in self.streams:
            stream.write(text)
        self.flush()
        return len(text)
    def flush(self):
        for stream in self.streams:
            stream.flush()


def stage(output, name, callback):
    row = {"name": name, "success": False}
    started = time.monotonic()
    log_path = output / (name + ".log")
    with log_path.open("w", encoding="utf-8") as log:
        stream = Tee(sys.stdout, log)
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            try:
                row.update(callback())
            except Exception as error:
                row["failure_type"] = type(error).__name__
                print("Supplement stage failed:", name, type(error).__name__)
    row.update(elapsed_seconds=round(time.monotonic() - started, 3), log=log_path.name, log_sha256=sha256(log_path))
    write_json(output / (name + ".json"), row)
    return row


def run_suite(name):
    suite, ids, assigned = planned_suite(name)
    module = SUITES[name][0]
    if name in NATIVE_PARTITIONS:
        callback = lambda: unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        callback = lambda: script(TESTS / (module + ".py"), ["--strict-half-close"] if name == "strict-vmess" else [])
    row = observe_tests(callback, ids, module)
    row["assigned_to_windows_qt_workflow"] = assigned
    return row


def command(path, arguments):
    outcome = 0
    try:
        script(path, arguments)
    except SystemExit as result:
        outcome = 0 if result.code is None else result.code
    return {"success": outcome == 0, "original_exit_code": outcome,
            "command": [sys.executable, str(path.relative_to(ROOT)), *map(str, arguments)], "unittest_methods": None}


def public_menu(name, output, paths, peer, revision):
    require(platform.system() == "Linux", "HistoricalPublicNativeMenuRequiresLinux")
    receipt = output / (name + "-receipt.json")
    if name == "public-direct":
        path = ROOT / "tools/Verify-PublicRustCore.py"
        arguments = ["--harness", paths["swirl-api"], "--output", receipt]
    else:
        path = ROOT / "tools/Verify-PublicRealityRuntime.py"
        arguments = ["--harness", paths["swirl-api"], "--inspector", paths["swirl-inspect"],
                     "--xray-peer-dir", peer, "--output", receipt, *PUBLIC_OPTIONS[name]]
    row = command(path, arguments)
    document = json.loads(receipt.read_text(encoding="utf-8"))
    require(document.get("commit") == revision and document.get("tracked_worktree_clean") is True,
            "PublicReceiptSourceMismatch")
    row.update(receipt=receipt.name, receipt_sha256=sha256(receipt),
               checks=document.get("checks", []), success=row["success"] and document.get("success") is True)
    return row


def required_phases(system):
    return list(PHASES) if system == "Linux" else ["deterministic", "strict-vmess"]


def collect_summary(output, current_identity):
    rows = []
    for phase in required_phases(current_identity["os"]):
        path = output / (phase + "-result.json")
        row = {"phase": phase, "success": False}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            require(document.get("phase") == phase and document.get("identity") == current_identity,
                    "PhaseIdentityMismatch")
            row.update(success=document.get("success") is True, report=path.name, report_sha256=sha256(path),
                       stages=document.get("stages", []))
        except (OSError, ValueError, RuntimeError) as error:
            row["failure_type"] = type(error).__name__
        rows.append(row)
    return {"required_phases": required_phases(current_identity["os"]), "phases": rows,
            "success": bool(rows) and all(row["success"] for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=(*PHASES, "summary"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema": 1, "phase": args.phase, "success": False, "stages": [],
              "qt_product_acceptance": False, "private_provider_acceptance": False, "physical_windows_acceptance": False}
    try:
        paths, peer, release = configure(output)
        report["identity"] = identity(paths, peer, release)
        if args.phase == "summary":
            report.update(collect_summary(output, report["identity"]))
        else:
            def add(name, callback):
                report["stages"].append(stage(output, name, callback))
                write_json(output / (args.phase + "-result.json"), report)
            if args.phase == "deterministic":
                for name in ("reality", "vision"):
                    add(name + "-vectors", lambda name=name: command(TESTS / ("generate_" + name + "_vectors.py"), ["--check"]))
                for name in SUITES:
                    if name != "strict-vmess":
                        add(name, lambda name=name: run_suite(name))
            elif args.phase == "strict-vmess":
                add(args.phase, lambda: run_suite(args.phase))
            else:
                add(args.phase, lambda: public_menu(args.phase, output, paths, peer, report["identity"]["source_sha"]))
            require(identity(paths, peer, release) == report["identity"], "SourceOrBinaryChangedDuringTests")
            report["success"] = bool(report["stages"]) and all(row["success"] for row in report["stages"])
    except Exception as error:
        report["failure_type"] = type(error).__name__
        # Identity errors use fixed codes; never emit arbitrary fixture exception text here.
        if type(error) is RuntimeError and re.fullmatch(r"[A-Za-z]+", str(error)):
            report["failure_code"] = str(error)
    finally:
        write_json(output / (args.phase + "-result.json"), report)
    print(json.dumps({"phase": args.phase, "success": report["success"],
                      "report": str(output / (args.phase + "-result.json"))}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
