#!/usr/bin/env python3
"""Verify the Windows Qt/DPAPI product against independently observed public exits.

The existing pinned Xray server and public destination allowlist are reused.
The Qt process owns subscription import, encrypted persistence, node selection,
the in-process Rust engine and both proxy frontends. No Rust configuration is
injected, and the isolated Rust command host is not used for these requests.
Only synthetic credentials are generated; raw fixtures and Xray logs stay in a
temporary directory. This gate does not establish private-provider or physical
Windows 11 acceptance. Failed networking, missing evidence and skips fail.

Primary references (existing dependencies; no upstream code copied):
https://doc.qt.io/qt-6/qnetworkproxy.html
https://doc.qt.io/qt-6/qsslsocket.html
https://learn.microsoft.com/en-us/windows-server/networking/ncsi/ncsi-frequently-asked-questions
Xray MPL-2.0 source and exact revisions: tools/tests/xray_peer/lock.json.
Qt's existing LGPL/GPL licenses remain in the application's packaging files.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/tests"))
from test_reality_runtime import XrayRuntimePeer, redacted, remember_secret, sha256, verified_build, write_json

_spec = importlib.util.spec_from_file_location("swirl_public_reality", ROOT / "tools/Verify-PublicRealityRuntime.py")
public = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(public)

require = public.require
STATES = ("imported", "encrypted_store_reloaded", "parameters_preserved", "in_process_rust",
          "node_switch_verified", "selected_node_restored", "match_reject_verified",
          "stopped", "listener_released")
FRONTENDS = ("http-connect", "socks5")
CASE_FIELDS = ("node", "frontend", "host", "port", "method")
REQUEST_STAGES = ("connect", "tls-handshake", "http-write", "http-headers", "http-body", "close", "complete")


class QtPublicPeer(public.PublicPeer):
    def __init__(self, binary, folder, evidence, identity, destinations):
        self.destinations = destinations
        XrayRuntimePeer.__init__(self, binary, folder, evidence, identity, (), public.FLOW, "chrome")


def expected_cases():
    return {(node, frontend, target["host"], target["port"], target["method"])
            for node in ("A", "B") for frontend in FRONTENDS for target in public.TARGETS}


def safe_qt_progress(value):
    """Preserve partial failures without trusting arbitrary child diagnostics.

    This is diagnostic-only: it cannot satisfy validate_qt_report or the
    independent Xray gate. Unknown fields, addresses and strings are discarded.
    """
    if not isinstance(value, dict) or value.get("schema") != 1:
        return None
    safe = {"schema": 1, **{key: value.get(key) is True for key in STATES}, "checks": []}
    checks = value.get("checks")
    if not isinstance(checks, list):
        return safe
    for check in checks[:8]:
        if not isinstance(check, dict):
            continue
        key = tuple(check.get(name) for name in CASE_FIELDS)
        if (not all(type(item) in (str, int) for item in key) or key not in expected_cases()):
            continue
        row = dict(zip(CASE_FIELDS, key))
        for name, lower, upper in (("http_status", 0, 599), ("proxy_port", 1, 65535),
                                   ("socket_error", -1, 1000), ("tls_error_count", 0, 64),
                                   ("elapsed_ms", 0, 180000)):
            item = check.get(name)
            if type(item) is int and lower <= item <= upper:
                row[name] = item
        for name in ("certificate_verified", "expected_body_verified", "closed", "success"):
            row[name] = check.get(name) is True
        row["proxy_host"] = "127.0.0.1" if check.get("proxy_host") == "127.0.0.1" else "unreported"
        row["tls_version"] = "TLSv1.3" if check.get("tls_version") == "TLSv1.3" else ""
        row["stage"] = check.get("stage") if check.get("stage") in REQUEST_STAGES else "unreported"
        safe["checks"].append(row)
    return safe


def preserve_qt_progress(child_report, evidence, report):
    if not child_report.is_file() or child_report.stat().st_size > 65536:
        return
    try:
        value = json.loads(child_report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return
    safe = safe_qt_progress(value)
    if safe is not None:
        write_json(evidence / "qt-product-progress.json", safe)
        report.update(checks=safe["checks"], product_states={key: safe[key] for key in STATES})


def run_qt_test(executable, fixture, child_report, log, evidence, report):
    """Retain safe progress even when QTest fails or the process times out."""
    try:
        result = subprocess.run([executable, "publicRealityProductChainAgainstIndependentPeer",
                                 "-o", str(log) + ",txt"],
                                env={**os.environ, "SWIRL_PUBLIC_QT_FIXTURE": str(fixture),
                                     "SWIRL_PUBLIC_QT_REPORT": str(child_report)},
                                text=True, capture_output=True, timeout=180)
        report["qt_exit_code"] = result.returncode
    except subprocess.TimeoutExpired:
        report.update(qt_exit_code=None, qt_timeout=True)
        raise
    finally:
        safe_log = redacted(log.read_text(encoding="utf-8", errors="replace")) if log.exists() else ""
        (evidence / "qt.log").write_text(safe_log, encoding="utf-8")
        preserve_qt_progress(child_report, evidence, report)
    require(result.returncode == 0 and "SKIP" not in safe_log and "PASS" in safe_log,
            "QtProductTestFailedOrSkipped")


def validate_qt_report(value):
    """Fail closed on missing, duplicate or partial cross-product evidence.

    Return only authored fields. Unrecognized report keys or network messages
    never become public evidence, even if the child executable is faulty.
    """
    require(isinstance(value, dict) and value.get("schema") == 1, "QtReportShape")
    states = {key: value.get(key) is True for key in STATES}
    require(all(states.values()), "QtProductStateIncomplete")
    checks = value.get("checks")
    require(isinstance(checks, list) and len(checks) == 8, "QtPublicCaseCount")
    seen, safe = set(), []
    for check in checks:
        require(isinstance(check, dict), "QtPublicCaseShape")
        key = tuple(check.get(name) for name in CASE_FIELDS)
        require(all(isinstance(item, (str, int)) and not isinstance(item, bool) for item in key),
                "QtPublicCaseShape")
        require(key in expected_cases() and key not in seen, "QtPublicCaseIdentity")
        seen.add(key)
        status = check.get("http_status")
        require(type(status) is int and check.get("success") is True, "QtPublicRequestFailed")
        require(check.get("proxy_host") == "127.0.0.1" and type(check.get("proxy_port")) is int
                and 1 <= check["proxy_port"] <= 65535 and check.get("stage") == "complete"
                and check.get("closed") is True, "QtPublicProxyOrCloseEvidenceMissing")
        encrypted = check["port"] == 443
        if encrypted:
            require(200 <= status < 400 and check.get("certificate_verified") is True
                    and check.get("tls_version") == "TLSv1.3", "QtPublicTlsEvidenceMissing")
        else:
            require(status == 200 and check.get("expected_body_verified") is True,
                    "QtPublicBodyEvidenceMissing")
        safe.append({**dict(zip(CASE_FIELDS, key)),
                     "proxy_host": "127.0.0.1", "proxy_port": check["proxy_port"],
                     "stage": "complete", "closed": True,
                     "http_status": status, "certificate_verified": encrypted,
                     "tls_version": "TLSv1.3" if encrypted else "",
                     "expected_body_verified": not encrypted, "success": True})
    require(seen == expected_cases(), "QtPublicCaseIdentity")
    return {"schema": 1, **states, "checks": safe}


def verify_peer(peer, destinations):
    """Require separate authenticated public sockets for both frontends."""
    cutoff = time.monotonic() + 3
    while True:
        observed = peer.observations()
        opened = [{"host": target["host"], "port": target["port"],
                   "connections": peer.public_connections(target, address)}
                  for target, address in destinations]
        complete = (observed["vless_accepted_sessions"] == 4
                    and observed["reality_authenticated_sessions"] >= 4
                    and observed["client_finished_verified_sessions"] >= 4
                    and observed["vision_direct_upload_commands"] >= 2
                    and observed["vision_direct_download_commands"] >= 2
                    and all(item["connections"] == 2 for item in opened))
        if complete or time.monotonic() >= cutoff:
            break
        time.sleep(0.02)
    require(complete and observed["vision_padding_events"] > 0
            and observed["vision_unpadding_events"] > 0
            and observed["camouflage_application_bytes"] == 0, "QtOfficialPublicEvidenceMissing")
    keys = ("reality_authenticated_sessions", "client_finished_verified_sessions", "vless_accepted_sessions",
            "vision_padding_events", "vision_unpadding_events", "vision_direct_upload_commands",
            "vision_direct_download_commands", "camouflage_application_bytes")
    return {"node": peer.identity, **{key: observed[key] for key in keys}, "public_destinations": opened}


def fixture_for(peers):
    document = {"proxies": [peer.node() for peer in peers],
                "rules": ["DOMAIN," + target["host"] + ",A" for target in public.TARGETS]
                + ["MATCH,REJECT"]}
    targets = [dict(target) for target in public.TARGETS]
    targets[0]["expected_body"] = public.EXPECTED_HTTP_BODY.decode("ascii")
    return {"subscription": remember_secret(json.dumps(document)), "targets": targets, "vision": True}


def source_identity(evidence):
    identity = json.loads((evidence / "source-identity.json").read_text(encoding="utf-8"))
    require(identity["tracked_worktree_changes"] == [], "QtPublicSourceDirty")
    paths = ("tools/Verify-PublicQtReality.py", "src/Swirl.Quick/tests/RustCoreTests.cpp")
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", *paths], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    require(tracked.returncode == 0, "QtPublicSourceUntracked")
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("qt-tests", "xray-peer-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    evidence = output.parent / (output.stem + "-evidence")
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"schema": 1, "success": False, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "platform": platform.system(), "provider_connection": False, "physical_windows_verified": False,
              "fingerprint": "chrome", "client_hello_profile": "chrome_133", "flow": public.FLOW,
              "verifier_sha256": sha256(Path(__file__)), "checks": [],
              "scope": "Actual Windows Qt import/DPAPI/selection/in-process Rust through Xray to public HTTP/HTTPS",
              "routing_scope": "Global A/B selection for public requests; imported rule-mode MATCH rejection",
              "public_target_dns": "Explicit launcher lookup; one public IPv4 pinned at each Xray origin"}
    phase, peers = "identity", []
    try:
        require(platform.system() == "Windows", "WindowsQtDpapiRequired")
        os.environ["SWIRL_RUST_QT_TESTS"] = str(args.qt_tests.resolve(strict=True))
        os.environ["SWIRL_XRAY_PEER_DIR"] = str(args.xray_peer_dir.resolve(strict=True))
        binary = verified_build(evidence, qt=True, fingerprint="chrome")
        identity = source_identity(evidence)
        report.update(commit=identity["git_sha"], tracked_worktree_clean=True,
                      qt_test_sha256=identity["binaries"]["SWIRL_RUST_QT_TESTS"]["sha256"])
        phase = "explicit-public-dns"
        destinations = [(target, public.public_address(target["host"])) for target in public.TARGETS]
        with tempfile.TemporaryDirectory(prefix="swirl-public-qt-") as folder:
            temporary = Path(folder)
            try:
                phase = "official-peer-start"
                for name in ("A", "B"):
                    peer = QtPublicPeer(binary, temporary / name, evidence, name, destinations)
                    peers.append(peer)
                    peer.start()
                fixture, child_report, log = (temporary / name for name in ("fixture.json", "report.json", "qt.log"))
                write_json(fixture, fixture_for(peers))
                phase = "qt-product-public-requests"
                run_qt_test(os.environ["SWIRL_RUST_QT_TESTS"], fixture, child_report, log, evidence, report)
                require(child_report.is_file() and child_report.stat().st_size <= 65536, "QtProductReportMissing")
                qt = validate_qt_report(json.loads(child_report.read_text(encoding="utf-8")))
                write_json(evidence / "qt-product-report.json", qt)
                report.update(checks=qt["checks"], product_states={key: qt[key] for key in STATES})
                phase = "independent-public-exit-evidence"
                report["official_xray"] = [verify_peer(peer, destinations) for peer in peers]
            finally:
                cleanup = []
                for peer in peers:
                    try:
                        peer.close()
                        cleanup.append({"node": peer.identity, "success": True})
                    except Exception as error:
                        cleanup.append({"node": peer.identity, "success": False,
                                        "failure": public.failure(error, "official-peer-cleanup")})
                report["peer_cleanup"] = cleanup
        require(len(report.get("peer_cleanup", [])) == 2 and all(item["success"] for item in report["peer_cleanup"]),
                "QtPublicPeerCleanupFailed")
        report["success"] = True
    except Exception as error:
        report["failure"] = public.failure(error, phase)
    write_json(output, report)
    print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
