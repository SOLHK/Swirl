#!/usr/bin/env python3
"""Actual Xray JSON file -> Qt importer -> Rust ABI -> authenticated peers.

The Qt executable is mandatory: this test never replaces its importer or core
configuration with a Python conversion. Windows exercises the product DPAPI
store; other platforms explicitly report portable-import-runtime without
claiming persistence. Ordinary peers and origins reuse the established
independent subscription fixtures. REALITY uses the complete, pinned official
Xray reference executable, with the existing verified_build gates unchanged.

The default business client is Python's real socket/ssl client, launched by
the Qt test against its already running in-process Rust listener. It receives
only loopback origin URLs and the disposable origin CA, never node source or
credentials. Its TLS unwrap proves both alerts before raw TCP EOF. The optional
qt-network client diagnoses Qt TLS close behavior; it uses the same independent
origin shutdown gates and does not receive an exception for a missing alert.

Usage (all profiles require published native converters):
  SWIRL_XRAY_QT_TESTS=/path/to/SwirlXrayRuntimeTests python test_xray_qt_import.py
  ... python test_xray_qt_import.py --protocol vless-reality --evidence /path

REALITY also requires SWIRL_XRAY_PEER_DIR, SWIRL_RUST_HARNESS and
SWIRL_RUST_INSPECTOR as required by test_reality_runtime. VMess/Trojan require
SWIRL_XRAY_BINARY and SWIRL_XRAY_RELEASE_MANIFEST from Fetch-TransportPeers.py.
SWIRL_TRANSPORT_CLIENT must name the built transport-client example for the
shared server fixture; it is never invoked for this Qt product traffic.
All credentials and certificates are disposable local fixtures; evidence contains only allowlisted
booleans, counts, source identities and request paths, never configurations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from test_product_subscription_chain import BODY, USER, UUID, Origin, Relay
from test_reality_runtime import XrayRuntimePeer, verified_build
from test_rust_core import certificates, exact, header
from transport_peer import Fixture as TransportFixture, PASSWORD as PEER_PASSWORD, UUID as PEER_UUID


ROOT = Path(__file__).resolve().parents[2]
PROFILES = ("http", "socks5", "ss", "vless", "vless-reality", "vmess", "trojan")
CLIENTS = ("python-stdlib-ssl", "qt-network")
QT_SLOT = "nativeProductChain"
MAX_REPORT = 1024 * 1024
TRUE_FIELDS = (
    "file_preview", "parameters_preserved", "rust_core_started", "in_process",
    "stopped", "listener_closed",
)
BOOLEAN_FIELDS = (*TRUE_FIELDS, "persisted", "reloaded")


class EvidenceFailure(RuntimeError):
    """Only static, credential-free failure identifiers may enter evidence."""


def require(condition, code):
    if not condition:
        raise EvidenceFailure(code)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(128 * 1024):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_bounded(path):
    with Path(path).open("rb") as stream:
        content = stream.read(MAX_REPORT + 1)
    require(len(content) <= MAX_REPORT, "EvidenceResponseTooLarge")
    return content


def report_whitelist(report):
    """Do not persist additional keys even when a failing Qt test emits them."""
    safe = {}
    if type(report) is not dict:
        return safe
    if type(report.get("schema")) is int:
        safe["schema"] = report["schema"]
    for key in ("protocol", "selected_protocol"):
        if report.get(key) in PROFILES:
            safe[key] = report[key]
    if report.get("pipeline") in ("windows-dpapi", "portable-import-runtime"):
        safe["pipeline"] = report["pipeline"]
    if report.get("client") in CLIENTS:
        safe["client"] = report["client"]
    for key in BOOLEAN_FIELDS:
        if type(report.get(key)) is bool:
            safe[key] = report[key]
    for key in ("http", "https"):
        original = report.get(key)
        if type(original) is not dict:
            continue
        result = {}
        if type(original.get("status")) is int and 100 <= original["status"] <= 599:
            result["status"] = original["status"]
        for field in ("body_verified", "certificate_verified", "close_notify_sent", "close_notify_received",
                      "tls_shutdown_verified", "transport_closed"):
            if type(original.get(field)) is bool:
                result[field] = original[field]
        safe[key] = result
    runtime = report.get("runtime")
    if type(runtime) is dict:
        fields = ("accepted", "failed", "upload", "download")
        observed = {key: runtime[key] for key in fields
                    if type(runtime.get(key)) is int and runtime[key] >= 0}
        stages = ("", "dns", "tcp_connect", "tls_handshake", "http_obfs", "protocol_handshake",
                  "stream_io", "inbound", "reality_handshake", "websocket_upgrade",
                  "initial_write", "routing", "unknown")
        if runtime.get("last_error_stage") in stages:
            observed["last_error_stage"] = runtime["last_error_stage"]
        sessions = runtime.get("sessions")
        if type(sessions) is list and len(sessions) <= 128:
            observed["sessions"] = []
            for session in sessions:
                if type(session) is not dict:
                    continue
                item = {key: session[key] for key in ("port", "upload", "download")
                        if type(session.get(key)) is int and session[key] >= 0}
                if type(session.get("closed")) is bool:
                    item["closed"] = session["closed"]
                if session.get("state") in ("active", "closed", "failed"):
                    item["state"] = session["state"]
                observed["sessions"].append(item)
        safe["runtime"] = observed
    return safe


def validate_report(report, protocol, windows):
    require(report.get("schema") == 1, "QtReportSchemaInvalid")
    require(report.get("protocol") == protocol, "QtReportProfileMismatch")
    selected = "vless" if protocol == "vless-reality" else protocol
    require(report.get("selected_protocol") == selected, "SelectedProtocolMismatch")
    pipeline = "windows-dpapi" if windows else "portable-import-runtime"
    require(report.get("pipeline") == pipeline, "QtPipelineScopeMismatch")
    for field in TRUE_FIELDS:
        require(report.get(field) is True, "QtStageIncomplete:" + field)
    require(report.get("persisted") is windows, "QtPersistenceClaimMismatch")
    require(report.get("reloaded") is windows, "QtReloadClaimMismatch")
    for scheme in ("http", "https"):
        response = report.get(scheme, {})
        require(response.get("status") == 200, "OriginHttpStatusInvalid:" + scheme)
        require(response.get("body_verified") is True, "OriginBodyNotVerified:" + scheme)
    require(report["https"].get("certificate_verified") is True, "OriginCertificateNotVerified")
    require(report.get("client") in CLIENTS, "BusinessClientMissing")
    if report["client"] == "python-stdlib-ssl":
        require(report["https"].get("tls_shutdown_verified") is True, "ClientTlsShutdownNotVerified")
        for scheme in ("http", "https"):
            require(report[scheme].get("transport_closed") is True, "ClientTcpShutdownNotVerified")
    runtime = report.get("runtime", {})
    require(runtime.get("accepted") == 2 and runtime.get("failed") == 0
            and runtime.get("last_error_stage") == "", "RustSessionCountsInvalid")
    for field in ("upload", "download"):
        require(type(runtime.get(field)) is int and runtime[field] > 0, "RustBytesMissing")
    sessions = runtime.get("sessions")
    require(type(sessions) is list and len(sessions) == 2, "RustSessionsMissing")
    for session in sessions:
        require(type(session) is dict and session.get("closed") is True
                and session.get("state") == "closed", "RustSessionNotClosed")
        for field in ("port", "upload", "download"):
            require(type(session.get(field)) is int and session[field] > 0, "RustSessionBytesMissing")
        require(session["port"] <= 65535, "RustSessionPortInvalid")


def business_request(url, proxy_port, ca_pem, expected):
    """Real application traffic; no node configuration or proxy implementation."""
    address = urlsplit(url)
    host, port, path = address.hostname, address.port, address.path
    tls = address.scheme == "https"
    require(address.scheme in ("http", "https") and host == ("localhost" if tls else "127.0.0.1")
            and path == ("/xray-https" if tls else "/xray-http") and 0 < port <= 65535
            and address.username is None and address.password is None
            and not address.query and not address.fragment, "BusinessTargetInvalid")
    stream = socket.create_connection(("127.0.0.1", proxy_port), timeout=8)
    stream.settimeout(8)
    result = {"status": 0, "body_verified": False, "transport_closed": False}
    try:
        authority = f"{host}:{port}"
        stream.sendall(f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode("ascii"))
        require(header(stream).startswith(b"HTTP/1.1 200 "), "BusinessTunnelRejected")
        if tls:
            context = ssl.create_default_context(cadata=ca_pem)
            context.set_alpn_protocols(["http/1.1"])
            require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED,
                    "ClientTlsVerificationDisabled")
            stream = context.wrap_socket(stream, server_hostname=host, suppress_ragged_eofs=False)
            require(stream.getpeercert() and stream.selected_alpn_protocol() == "http/1.1",
                    "ClientTlsIdentityMissing")
            result["certificate_verified"] = True
        stream.sendall(f"GET {path} HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\n\r\n".encode("ascii"))
        response = header(stream)
        require(response.startswith(b"HTTP/1.1 200 OK\r\n"), "BusinessHttpStatusInvalid")
        lengths = []
        for field in response.split(b"\r\n")[1:-2]:
            key, separator, value = field.partition(b":")
            require(bool(separator), "BusinessHeaderInvalid")
            key, value = key.strip().lower(), value.strip()
            require(key != b"transfer-encoding" and
                    (key != b"content-encoding" or value == b"identity"), "BusinessEncodingInvalid")
            if key == b"content-length":
                require(value.isdigit() and len(value) <= 6, "BusinessContentLengthInvalid")
                lengths.append(int(value))
        wanted = expected + b":" + path.encode("ascii")
        require(lengths == [len(wanted)], "BusinessContentLengthMismatch")
        require(exact(stream, len(wanted)) == wanted, "BusinessBodyMismatch")
        result.update(status=200, body_verified=True)
        if tls:
            # SSL unwrap authenticates both close_notify alerts and keeps the
            # underlying socket available for a separate bidirectional EOF.
            stream = stream.unwrap()
            result["tls_shutdown_verified"] = True
        stream.shutdown(socket.SHUT_WR)
        require(stream.recv(1) == b"", "BusinessTcpEofMissing")
        result["transport_closed"] = True
        return result
    finally:
        stream.close()


def traffic_client(fixture_path, proxy_port):
    """Called by the actual Qt test while its Rust listener remains running."""
    try:
        require(0 < proxy_port <= 65535, "BusinessProxyPortInvalid")
        fixture = json.loads(read_bounded(fixture_path))
        require(type(fixture) is dict and set(fixture) ==
                {"schema", "http_url", "https_url", "ca_pem", "expected_body"}
                and fixture["schema"] == 1 and fixture["expected_body"] == "product-origin-ok",
                "BusinessFixtureInvalid")
        result = {"schema": 1, "client": "python-stdlib-ssl"}
        for scheme in ("http", "https"):
            result[scheme] = business_request(fixture[scheme + "_url"], proxy_port,
                                              fixture["ca_pem"], BODY)
        print(json.dumps(result), flush=True)
        return 0
    except EvidenceFailure as error:
        print(json.dumps({"schema": 1, "failure": str(error)}), flush=True)
    except Exception as error:
        print(json.dumps({"schema": 1, "failure": "BusinessClientException:" + type(error).__name__}), flush=True)
    return 1


def qt_outcome(content):
    root = ET.fromstring(content)
    functions = root.findall("TestFunction")
    selected = [item for item in functions if item.get("name") == QT_SLOT]
    passed = sum(item.get("type") == "pass" for item in root.iter("Incident"))
    failed = [item for item in root.iter("Incident") if item.get("type") != "pass"]
    skipped = list(root.iter("Skip"))
    result = {
        "executed_slot": len(selected) == 1,
        "passed_incidents": passed,
        "failed_incidents": len(failed),
        "skipped_incidents": len(skipped),
        "failure_locations": [
            {"file": Path(item.get("file", "")).name,
             "line": int(item.get("line", "0")) if item.get("line", "0").isdigit() else 0}
            for item in failed[:8]
        ],
    }
    result["slot_passed"] = len(selected) == 1 and any(
        item.get("type") == "pass" for item in selected[0].iter("Incident"))
    return result


def validate_qt_outcome(result):
    require(result["executed_slot"] and result["slot_passed"], "QtProductSlotNotExecuted")
    require(result["failed_incidents"] == 0, "QtAssertionFailed")
    require(result["skipped_incidents"] == 0, "QtProductSlotSkipped")


def verified_native_peer():
    """Bind unmodified official protocol servers to the committed release lock."""
    binary = Path(os.environ["SWIRL_XRAY_BINARY"]).resolve(strict=True)
    manifest = json.loads(Path(os.environ["SWIRL_XRAY_RELEASE_MANIFEST"]).read_text(encoding="utf-8"))
    expected = json.loads((ROOT / "tools/tests/transport-peer-lock.json").read_text(encoding="utf-8"))["peers"]["current"]
    host = {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}.get(platform.system())
    arch = "arm64-v8a" if platform.machine().lower() in ("arm64", "aarch64") else "64"
    platform_key = f"{host}-{arch}"
    require(manifest.get("schema") == 1 and manifest.get("platform") == platform_key,
            "OfficialReleaseManifestPlatformMismatch")
    observed = manifest.get("peers", {}).get("current", {})
    for key in ("release", "commit", "sha256"):
        require(observed.get(key) == expected[key], "OfficialReleaseLockMismatch")
    require(observed.get("archive_sha256") == expected["sha256"].get(platform_key)
            and bool(expected["sha256"].get(platform_key)), "OfficialArchiveHashMismatch")
    require(binary.is_file() and sha256(binary) == observed.get("binary_sha256"),
            "OfficialBinaryHashMismatch")
    return {key: observed[key] for key in ("release", "commit", "archive_sha256", "binary_sha256")}


class OfficialJsonPeer:
    """Reuse the official server fixture while supplying only source JSON to Qt."""

    def __init__(self, protocol):
        self.protocol = protocol
        self.fixture = TransportFixture("qt-json-" + protocol)
        try:
            self.peer = self.fixture.peer("raw", protocol=protocol, tls=protocol == "trojan")
            self.port = self.peer["port"]
        except BaseException:
            self.fixture.close()
            raise

    def document(self):
        server = {"address": "127.0.0.1", "port": self.port}
        stream = {"network": "tcp", "security": "none"}
        if self.protocol == "vmess":
            server["users"] = [{"id": PEER_UUID, "alterId": 0, "security": "auto"}]
            settings = {"vnext": [server]}
        else:
            server["password"] = PEER_PASSWORD
            settings = {"servers": [server]}
            stream = {"network": "tcp", "security": "tls", "tlsSettings": {
                "serverName": "localhost", "alpn": ["http/1.1"],
                "certificates": [{"usage": "verify", "certificate": self.fixture.ca_pem.splitlines()}]}}
        return json.dumps({"outbounds": [{"tag": "JSON official " + self.protocol,
            "protocol": self.protocol, "settings": settings, "streamSettings": stream}]}).encode("utf-8")

    def observations(self, ports):
        deadline = time.monotonic() + 3
        observed, content = [], ""
        while time.monotonic() < deadline:
            if self.peer["access"].is_file():
                content = self.peer["access"].read_text(encoding="utf-8")
                observed = [int(value) for value in re.findall(r"\baccepted\s+tcp:[^\s:]+:(\d+)\b", content)]
                if len(observed) >= 2:
                    break
            time.sleep(0.01)
        require(len(observed) == 2 and sorted(observed) == sorted(ports),
                "OfficialProtocolServerAcceptanceMissing")
        return {"protocol": self.protocol, "server_version": self.peer["version"],
                "accepted_requests": len(observed), "accepted_target_ports": observed,
                "access_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}

    def close(self):
        self.fixture.close()


def xray_document(protocol, peer):
    """Produce official input syntax only; conversion remains inside Qt/Rust."""
    if protocol == "vless-reality":
        return peer.document("xray").encode("utf-8")
    if protocol in ("vmess", "trojan"):
        return peer.document()
    server = {"address": "127.0.0.1", "port": peer.port}
    if protocol in ("http", "socks5"):
        server["users"] = [{"user": USER, "pass": peer.password}]
    elif protocol == "ss":
        server.update(method=peer.cipher, password=peer.password)
    elif protocol == "vless":
        server["users"] = [{"id": UUID, "encryption": "none"}]
    settings = {"vnext" if protocol == "vless" else "servers": [server]}
    name = {"ss": "shadowsocks", "socks5": "socks"}.get(protocol, protocol)
    return json.dumps({"outbounds": [{
        "tag": "JSON 节点 東京 🇸🇬", "protocol": name, "settings": settings,
        "streamSettings": {"network": "tcp", "security": "none"},
    }]}, ensure_ascii=False).encode("utf-8")


def origin_observations(http, https):
    def paths(origin):
        # The origins already enforce bounded request lines; keep only the two
        # exact expected paths in evidence, never arbitrary headers or bodies.
        values = [request.split(b" ")[1] for request in origin.requests]
        return [value.decode("ascii") if value in (b"/xray-http", b"/xray-https")
                else "unexpected-path" for value in values]

    return {
        "http_paths": paths(http), "https_paths": paths(https),
        "https_sni": [value if value == "localhost" else "unexpected-sni" for value in https.sni],
        "https_authenticated_closes": https.tls_closed,
        "http_request_bytes": sum(map(len, http.requests)),
        "https_plaintext_request_bytes": sum(map(len, https.requests)),
        "http_errors": len(http.errors), "https_errors": len(https.errors),
    }


def validate_origins(observed):
    require(observed["http_paths"] == ["/xray-http"], "IndependentHttpPathMismatch")
    require(observed["https_paths"] == ["/xray-https"], "IndependentHttpsPathMismatch")
    require(observed["https_sni"] == ["localhost"], "IndependentHttpsSniMismatch")
    require(observed["https_authenticated_closes"] == 1, "HttpsShutdownNotAuthenticated")
    require(observed["http_request_bytes"] > 0 and observed["https_plaintext_request_bytes"] > 0,
            "OriginRequestBytesMissing")
    require(not observed["http_errors"] and not observed["https_errors"], "IndependentOriginFailed")


def source_identity(executable):
    source = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, check=True, timeout=5).stdout.strip()
    if os.environ.get("GITHUB_SHA"):
        require(source == os.environ["GITHUB_SHA"], "CiSourceCommitMismatch")
    changes = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=no"],
                             cwd=ROOT, capture_output=True, text=True, check=True, timeout=5).stdout.splitlines()
    if os.environ.get("CI"):
        require(not changes, "CiTrackedSourceModified")
    diff = subprocess.run(["git", "diff", "--binary", "HEAD"], cwd=ROOT,
                          capture_output=True, check=True, timeout=5).stdout
    files = [Path(__file__).resolve(), ROOT / "src/Swirl.Quick/tests/XrayRuntimeTests.cpp",
             ROOT / "src/Swirl.Quick/tests/XrayImportTests.cpp",
             ROOT / "src/Swirl.Quick/engine/XrayJsonBridge.cpp",
             ROOT / "src/Swirl.Quick/engine/RustCoreEngine.cpp",
             ROOT / "core/crates/swirl-api/src/xray_import.rs"]
    library = executable.parent / ("swirl_api.dll" if os.name == "nt" else
                                  "libswirl_api.dylib" if sys.platform == "darwin" else "libswirl_api.so")
    require(library.is_file(), "ActualQtRustLibraryMissing")
    return {"git_sha": source, "tracked_worktree_changes": changes,
            "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
            "platform": sys.platform, "python": platform.python_version(),
            "openssl": ssl.OPENSSL_VERSION, "qt_binary_sha256": sha256(executable),
            "rust_library_sha256": sha256(library),
            "source_files": {str(path.relative_to(ROOT)): sha256(path) for path in files}}


def run_case(protocol, executable, evidence, xray=None, client="python-stdlib-ssl"):
    case = evidence / (protocol + "-" + str(time.time_ns()))
    case.mkdir()
    report = {"schema": 1, "protocol": protocol, "success": False,
              "provider_connection": False, "origin_scope": "controlled-loopback"}
    resources, peer, http, https = [], None, None, None
    with tempfile.TemporaryDirectory(prefix="Swirl Qt JSON 测试-") as temporary:
        folder = Path(temporary)
        try:
            context, _, ca = certificates(folder)
            http = Origin()
            resources.append(http)
            https = Origin(context=context)
            resources.append(https)
            ports = [http.port, https.port]
            if protocol == "vless-reality":
                peer = XrayRuntimePeer(xray, folder / "official-peer", case,
                                       "JSON-REALITY", ports, fingerprint="chrome")
                resources.append(peer)
                peer.start()
            elif protocol in ("vmess", "trojan"):
                peer = OfficialJsonPeer(protocol)
                resources.append(peer)
            else:
                peer = Relay(protocol, "JSON-QT", ports)
                resources.append(peer)
            document = xray_document(protocol, peer)
            configuration = folder / "配置-节点-東京.json"
            configuration.write_bytes(document)
            configuration_hash = sha256(configuration)
            fixture = {
                "schema": 1, "protocol": protocol, "configuration_path": str(configuration),
                "client": client,
                "http_url": f"http://127.0.0.1:{http.port}/xray-http",
                "https_url": f"https://localhost:{https.port}/xray-https",
                "ca_pem": ca, "expected_body": BODY.decode("ascii"),
            }
            fixture_path, output = folder / "fixture.json", folder / "qt-report.json"
            write_json(fixture_path, fixture)
            xml_path = folder / "qt.xml"
            env = {**os.environ, "SWIRL_XRAY_QT_FIXTURE": str(fixture_path),
                   "SWIRL_XRAY_QT_REPORT": str(output), "SWIRL_TEST_ROOT": str(folder / "state"),
                   "SWIRL_XRAY_PYTHON": sys.executable,
                   "QT_QPA_PLATFORM": "offscreen", "QT_FORCE_STDERR_LOGGING": "1"}
            # Qt diagnostics remain private temporary data. Publish structured
            # incident locations only; assertion text can contain credentials.
            # Qt 6.10's logger opens -o paths through narrow fopen_s on MSVC.
            # Capture its XML stdout with Python's Unicode-safe file handle;
            # configuration, fixture and encrypted-store paths stay Unicode.
            with (folder / "qt-private.log").open("wb") as log, xml_path.open("wb") as xml:
                result = subprocess.run([str(executable), QT_SLOT, "-o", "-,xml"],
                                        env=env, stdout=xml, stderr=log, timeout=90)
            report["qt_exit_code"] = result.returncode
            if output.is_file():
                report["qt"] = report_whitelist(json.loads(read_bounded(output)))
            require(xml_path.is_file(), "QtXmlReportMissing")
            require(xml_path.stat().st_size > 0, "QtXmlReportEmpty")
            report["qtest"] = qt_outcome(read_bounded(xml_path))
            require(result.returncode == 0, "QtProcessFailed")
            validate_qt_outcome(report["qtest"])
            require("qt" in report, "QtProductReportMissing")
            validate_report(report["qt"], protocol, os.name == "nt")
            require(report["qt"]["client"] == client, "BusinessClientMismatch")
            require(sorted(item["port"] for item in report["qt"]["runtime"]["sessions"]) == sorted(ports),
                    "RustTargetPortsMismatch")
            report["source_document_unchanged"] = sha256(configuration) == configuration_hash
            require(report["source_document_unchanged"], "OriginalJsonFileChanged")
            deadline = time.monotonic() + 3
            while https.tls_closed != 1 and not https.errors and time.monotonic() < deadline:
                time.sleep(0.01)
            report["origins"] = origin_observations(http, https)
            validate_origins(report["origins"])
            if protocol == "vless-reality":
                observed = peer.observations()
                report["peer"] = observed
                require(observed["reality_authenticated_sessions"] >= 2, "RealityAuthenticationMissing")
                require(observed["client_finished_verified_sessions"] >= 2, "RealityFinishedMissing")
                require(observed["vless_accepted_sessions"] == 2, "VlessSessionCountMismatch")
                require(sorted(observed["vless_target_ports"]) == sorted(ports), "XrayTargetMismatch")
                require(observed["camouflage_application_bytes"] == 0, "CamouflageApplicationLeak")
                require(observed["camouflage_record_size_failures"] == 0, "RealityRecordSizeFailure")
            elif protocol in ("vmess", "trojan"):
                report["peer"] = peer.observations(ports)
            else:
                with peer.lock:
                    events = [{key: item[key] for key in ("port", "upload", "download")}
                              for item in peer.connections]
                report["peer"] = {"protocol": protocol, "sessions": events,
                                  "authentication_denials": len(peer.denied), "errors": len(peer.errors)}
                require(len(events) == 2 and sorted(item["port"] for item in events) == sorted(ports),
                        "IndependentProxyPathMissing")
                require(all(item["upload"] > 0 and item["download"] > 0 for item in events),
                        "IndependentBidirectionalBytesMissing")
                require(not peer.denied and not peer.errors, "IndependentPeerAuthenticationFailed")
            report["success"] = True
        except EvidenceFailure as error:
            report["failure"] = str(error)
        except Exception as error:
            # Never copy arbitrary exception strings from Qt, TLS or fixtures.
            report["failure"] = "FixtureException:" + type(error).__name__
        finally:
            for resource in reversed(resources):
                try:
                    resource.close()
                except Exception as error:
                    report["success"] = False
                    report.setdefault("cleanup_errors", []).append(type(error).__name__)
            if http is not None and https is not None:
                report["origins"] = origin_observations(http, https)
            if peer is not None and protocol != "vless-reality":
                with socket.socket() as probe:
                    probe.settimeout(0.5)
                    report["peer_listener_closed"] = probe.connect_ex(("127.0.0.1", peer.port)) != 0
                if not report["peer_listener_closed"]:
                    report["success"] = False
                    report["failure"] = "IndependentPeerListenerRemainedOpen"
            write_json(case / "result.json", report)
    return {"protocol": protocol, "success": report["success"], "evidence": case.name,
            **({"failure": report["failure"]} if "failure" in report else {})}


class EvidenceGuardTests(unittest.TestCase):
    """Check that reduced or falsely promoted evidence cannot pass this gate."""

    def valid_report(self):
        return {"schema": 1, "protocol": "http", "selected_protocol": "http",
                "client": "python-stdlib-ssl",
                "pipeline": "portable-import-runtime", **dict.fromkeys(TRUE_FIELDS, True),
                "persisted": False, "reloaded": False,
                "http": {"status": 200, "body_verified": True, "transport_closed": True},
                "https": {"status": 200, "body_verified": True, "certificate_verified": True,
                          "tls_shutdown_verified": True, "transport_closed": True},
                "runtime": {"accepted": 2, "failed": 0, "last_error_stage": "", "upload": 200,
                            "download": 200, "sessions": [
                                {"port": port, "upload": 100, "download": 100, "closed": True,
                                 "state": "closed"} for port in (10001, 10002)]}}

    def test_each_missing_product_stage_fails(self):
        for field in TRUE_FIELDS:
            with self.subTest(field=field):
                report = self.valid_report()
                report[field] = False
                with self.assertRaises(EvidenceFailure):
                    validate_report(report, "http", False)

    def test_portable_evidence_cannot_claim_dpapi_or_wrong_protocol(self):
        for field, value in (("pipeline", "windows-dpapi"), ("persisted", True),
                             ("reloaded", True), ("selected_protocol", "vless")):
            with self.subTest(field=field):
                report = self.valid_report()
                report[field] = value
                with self.assertRaises(EvidenceFailure):
                    validate_report(report, "http", False)

    def test_tls_certificate_and_body_are_both_required(self):
        for field in ("body_verified", "certificate_verified", "tls_shutdown_verified", "transport_closed"):
            report = self.valid_report()
            report["https"][field] = False
            with self.assertRaises(EvidenceFailure):
                validate_report(report, "http", False)

    def test_skipped_or_unexecuted_slot_never_passes(self):
        valid = b'<TestCase><TestFunction name="nativeProductChain"><Incident type="pass"/></TestFunction></TestCase>'
        validate_qt_outcome(qt_outcome(valid))
        for invalid in (
            valid.replace(b'nativeProductChain', b'otherTest'),
            valid.replace(b'<Incident type="pass"/>', b'<Skip type="skipall"/><Incident type="pass"/>'),
            valid.replace(b'<Incident type="pass"/>', b'<Incident type="fail"/>'),
        ):
            with self.assertRaises(EvidenceFailure):
                validate_qt_outcome(qt_outcome(invalid))

    def test_untrusted_report_fields_are_not_published(self):
        report = self.valid_report()
        report.update(password="synthetic-secret", configuration={"token": "synthetic-secret"})
        report["https"]["body"] = "synthetic-secret"
        safe = report_whitelist(report)
        self.assertNotIn("synthetic-secret", json.dumps(safe))
        validate_report(safe, "http", False)

    def test_runtime_failure_or_active_sessions_cannot_pass(self):
        for key, value in (("accepted", 0), ("failed", 1), ("last_error_stage", "stream_io"),
                           ("upload", 0), ("download", 0), ("sessions", [])):
            with self.subTest(field=key):
                report = self.valid_report()
                report["runtime"][key] = value
                with self.assertRaises(EvidenceFailure):
                    validate_report(report, "http", False)
        report = self.valid_report()
        report["runtime"]["sessions"][0].update(closed=False, state="active")
        with self.assertRaises(EvidenceFailure):
            validate_report(report, "http", False)

    def test_http_success_does_not_replace_authenticated_tls_close(self):
        observed = {"http_paths": ["/xray-http"], "https_paths": ["/xray-https"],
                    "https_sni": ["localhost"], "https_authenticated_closes": 0,
                    "http_request_bytes": 200, "https_plaintext_request_bytes": 200,
                    "http_errors": 0, "https_errors": 0}
        with self.assertRaises(EvidenceFailure):
            validate_origins(observed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", action="append", choices=PROFILES)
    parser.add_argument("--client", choices=CLIENTS, default="python-stdlib-ssl",
                        help="actual business client; qt-network also diagnoses Qt TLS shutdown behavior")
    parser.add_argument("--traffic-client", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--client-fixture", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--proxy-port", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--evidence", type=Path,
                        default=Path(os.environ.get("SWIRL_XRAY_QT_EVIDENCE", ROOT / "build/xray-qt-import-evidence")))
    parser.add_argument("--self-test", action="store_true",
                        help="test evidence guards only; does not count as product/network acceptance")
    args = parser.parse_args()
    if args.traffic_client:
        return traffic_client(args.client_fixture, args.proxy_port)
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EvidenceGuardTests))
        return 0 if result.wasSuccessful() else 1
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    summary = {"schema": 1, "success": False, "provider_connection": False,
               "scope": "actual Qt importer and in-process Rust; DPAPI is Windows-only",
               "cases": []}
    try:
        require(bool(os.environ.get("SWIRL_XRAY_QT_TESTS")), "QtProductExecutableNotConfigured")
        executable = Path(os.environ["SWIRL_XRAY_QT_TESTS"]).resolve(strict=True)
        require(executable.is_file(), "QtProductExecutableMissing")
        summary["source"] = source_identity(executable)
        profiles = list(dict.fromkeys(args.protocol or PROFILES))
        xray = None
        if any(protocol in ("vmess", "trojan") for protocol in profiles):
            summary["official_native_peer"] = verified_native_peer()
        if "vless-reality" in profiles:
            reference = evidence / "official-peer-source"
            reference.mkdir(exist_ok=True)
            # This existing verifier retains its exact source/lock/hash/rebuild
            # gates. Our result.json supplies the actual Qt pipeline scope.
            xray = verified_build(reference, fingerprint="chrome")
        for protocol in profiles:
            outcome = run_case(protocol, executable, evidence, xray, args.client)
            summary["cases"].append(outcome)
            print(json.dumps(outcome), flush=True)
        summary["success"] = bool(summary["cases"]) and all(item["success"] for item in summary["cases"])
    except EvidenceFailure as error:
        summary["failure"] = str(error)
    except Exception as error:
        summary["failure"] = "SetupException:" + type(error).__name__
    write_json(evidence / "result.json", summary)
    if "failure" in summary:
        print(json.dumps({"success": False, "failure": summary["failure"]}), flush=True)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
