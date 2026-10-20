#!/usr/bin/env python3
"""Explicit public HTTP/HTTPS through Swirl's native REALITY Runtime.

The real Rust subscription inspector supplies the only proxy outbound to the
real Rust control executable. A complete, source-pinned official Xray server
authenticates that connection and contacts exactly the public targets below.
--vision preserves xtls-rprx-vision and requires official direct commands in
both directions for the TLS 1.3 HTTPS request. Nothing accepts private nodes,
changes certificate trust, follows redirects, or enables a DIRECT fallback.

This Linux public gate is separate from controlled protocol/Qt/DPAPI evidence
and private-provider acceptance. Temporary Xray credentials, configuration and
logs never enter its artifacts. Failed networking or cleanup remains failure.
Dirty or untracked sources may produce diagnostic check results, never a
successful source-identified gate result.

Endpoint and upstream sources reviewed:
https://learn.microsoft.com/en-us/windows-server/networking/ncsi/ncsi-frequently-asked-questions
https://www.rust-lang.org/
https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/infra/conf/freedom.go
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import ipaddress
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


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/tests"))
from test_reality_runtime import Control, SNI, XrayRuntimePeer, sha256, verified_build, write_json

_spec = importlib.util.spec_from_file_location("swirl_public_http", ROOT / "tools/Verify-PublicRustCore.py")
public_http = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(public_http)

TARGETS = (
    {"host": "www.msftconnecttest.com", "port": 80, "method": "GET", "path": "/connecttest.txt"},
    {"host": "www.rust-lang.org", "port": 443, "method": "HEAD", "path": "/"},
)
EXPECTED_HTTP_BODY = b"Microsoft Connect Test"
FLOW = "xtls-rprx-vision"


class ProbeFailure(Exception):
    """Every code is authored here; no untrusted peer text is reported."""


def require(condition, code):
    if not condition:
        raise ProbeFailure(code)


def failure(error, phase):
    result = {"phase": phase, "type": type(error).__name__}
    if isinstance(error, ProbeFailure):
        result["code"] = str(error)
    return result


def public_address(host):
    # Bound libc DNS with a disposable child process; no resolver thread can
    # survive timeout. Resolve only an authored endpoint, before proxy startup.
    require(any(target["host"] == host for target in TARGETS), "UnlistedPublicHost")
    query = ("import json,socket,sys;print(json.dumps(sorted({r[4][0] for r in "
             "socket.getaddrinfo(sys.argv[1],None,socket.AF_INET,socket.SOCK_STREAM)})))")
    result = subprocess.run([sys.executable, "-c", query, host], capture_output=True,
                            text=True, timeout=10)
    require(result.returncode == 0 and len(result.stdout) <= 4096, "PublicDnsFailed")
    addresses = json.loads(result.stdout)
    require(isinstance(addresses, list) and 0 < len(addresses) <= 16, "PublicDnsShape")
    parsed = [ipaddress.IPv4Address(value) for value in addresses]
    require(all(value.is_global for value in parsed), "PublicDnsReturnedNonpublicAddress")
    # A failed chosen address is not retried through another IP or proxy.
    return str(min(parsed))


class DeadlineControl(Control):
    """Retain the shared real process owner, with absolute command deadlines."""

    def __init__(self):
        super().__init__()
        self.usable = True

    def command(self, *, deadline=None, **command):
        require(self.usable, "NativeControlDesynchronized")
        deadline = time.monotonic() + 12 if deadline is None else deadline
        try:
            public_http.remaining(deadline, 12)
            encoded = json.dumps(command) + "\n"
            require(len(encoded.encode()) <= 4096, "NativeControlRequestLimit")
            self.process.stdin.write(encoded)
            self.process.stdin.flush()
            line = self.lines.get(timeout=public_http.remaining(deadline, 12))
            require(line is not None and len(line) <= 65536, "NativeControlReplyLimit")
            public_http.remaining(deadline, 12)
            response = json.loads(line)
            require(isinstance(response, dict), "NativeControlReplyShape")
            return response
        except Exception:
            # This ABI has no request IDs: never mistake a late timed-out reply
            # for an accounting or stop acknowledgment. Closing owns cleanup.
            self.usable = False
            raise


class PublicPeer(XrayRuntimePeer):
    def __init__(self, binary, folder, evidence, destinations, flow):
        self.destinations = destinations
        super().__init__(binary, folder, evidence, "public", (), flow)

    def outbound_routes(self):
        outbounds, rules = [], []
        for index, (target, address) in enumerate(self.destinations):
            tag, port = "public-origin-" + str(index), target["port"]
            outbounds.append({"tag": tag, "protocol": "freedom", "settings": {
                "redirect": f"{address}:{port}", "finalRules": [
                    {"action": "allow", "network": "tcp", "ip": [address + "/32"], "port": port}]}})
            rules.append({"type": "field", "network": "tcp", "domain": ["full:" + target["host"]],
                          "port": port, "outboundTag": tag})
        outbounds.append({"tag": "blocked", "protocol": "blackhole"})
        rules.append({"type": "field", "network": "tcp,udp", "outboundTag": "blocked"})
        return outbounds, rules

    def public_connections(self, target, address):
        log = self.log_path.read_text(encoding="utf-8", errors="replace")
        destination = re.escape(address + ":" + str(target["port"]))
        # The actual remote socket address must equal the chosen public IP.
        return len(re.findall(r"connection opened to tcp:" + destination +
                              r", local endpoint [^\r\n]+, remote endpoint " + destination +
                              r"(?:\r?\n|$)", log))


def imported_configuration(peer):
    document = peer.document("uri")
    parsed = subprocess.run([os.environ["SWIRL_RUST_INSPECTOR"], "--private-json"],
                            input=document, text=True, capture_output=True, timeout=10)
    require(parsed.returncode == 0 and len(parsed.stdout) <= 65536, "NativeImportFailed")
    value = json.loads(parsed.stdout)
    require(value["report"]["parsed"] is True and value["report"]["original_preserved"] is True,
            "SubscriptionSourceNotPreserved")
    expected = {"type": "vless", "host": "127.0.0.1", "port": peer.port, "uuid": peer.uuid,
                "tls": None, "websocket": None, "reality": {
                    "server_name": SNI, "public_key": peer.public_key,
                    "short_id": peer.short_id, "fingerprint": "rustls", "alpn": []}}
    if peer.flow:
        expected["flow"] = peer.flow
    require(value["tcpCandidates"] == [expected], "NativeCandidateParametersChanged")
    return {"schema": 1, "listen": "127.0.0.1:0", "selected": peer.identity,
            "nodes": [{"id": peer.identity, "outbound": value["tcpCandidates"][0]},
                      {"id": "reject", "outbound": {"type": "reject"}}],
            "rules": [{"matcher": {"type": "domain", "value": target["host"]},
                       "outbound": peer.identity} for target in TARGETS] + [
                           {"matcher": {"type": "match"}, "outbound": "reject"}],
            "limits": {"max_connections": 2, "handshake_timeout_ms": 15000}}


def receive_exact(stream, count, deadline):
    content = bytearray()
    while len(content) < count:
        stream.settimeout(public_http.remaining(deadline, 12))
        part = stream.recv(count - len(content))
        require(bool(part), "PublicBodyTruncated")
        content.extend(part)
    return bytes(content)


def origin_request(port, target, vision, result, deadline):
    authority = target["host"] + ":" + str(target["port"])
    stream = socket.create_connection(("127.0.0.1", port), timeout=public_http.remaining(deadline, 12))
    try:
        stream.settimeout(public_http.remaining(deadline, 12))
        stream.sendall(f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode())
        require(public_http.read_header(stream, deadline).startswith(b"HTTP/1.1 200 "),
                "NativeConnectRejected")
        result["native_connect_accepted"] = True
        encrypted = target["port"] == 443
        if encrypted:
            context = ssl.create_default_context()
            context.set_alpn_protocols(["http/1.1"])
            if vision:
                context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
            stream = context.wrap_socket(stream, server_hostname=target["host"], do_handshake_on_connect=False,
                                         suppress_ragged_eofs=False)
            stream.settimeout(public_http.remaining(deadline, 12))
            stream.do_handshake()
            require(stream.selected_alpn_protocol() == "http/1.1", "PublicAlpnMismatch")
            result.update(certificate_verified=True, tls_version=stream.version())
        stream.settimeout(public_http.remaining(deadline, 12))
        stream.sendall((f'{target["method"]} {target["path"]} HTTP/1.1\r\n'
                        f'Host: {target["host"]}\r\nConnection: close\r\n\r\n').encode())
        headers = public_http.read_header(stream, deadline)
        status = headers.split(b"\r\n", 1)[0].split()
        require(len(status) >= 2 and status[0] in (b"HTTP/1.0", b"HTTP/1.1") and
                len(status[1]) == 3 and status[1].isdigit(), "PublicHttpStatusMalformed")
        result["http_status"] = int(status[1])
        if encrypted:
            require(200 <= result["http_status"] < 400, "PublicHttpsStatusRejected")
            public_http.close_https(stream, deadline)
            result["authenticated_tls_close"] = True
        else:
            require(result["http_status"] == 200, "PublicHttpStatusRejected")
            lengths = [line.split(b":", 1)[1].strip() for line in headers.split(b"\r\n")
                       if line.lower().startswith(b"content-length:")]
            require(lengths == [str(len(EXPECTED_HTTP_BODY)).encode()] and
                    not any(line.lower().startswith(b"transfer-encoding:") for line in headers.split(b"\r\n")),
                    "PublicHttpBodyFraming")
            body = receive_exact(stream, len(EXPECTED_HTTP_BODY), deadline)
            require(body == EXPECTED_HTTP_BODY, "PublicHttpBodyMismatch")
            result.update(body_bytes=len(body), expected_body_verified=True)
            stream.shutdown(socket.SHUT_WR)
            stream.settimeout(public_http.remaining(deadline, 12))
            require(stream.recv(1) == b"", "PublicHttpClosure")
        result["orderly_origin_close"] = True
    finally:
        stream.close()


def probe(peer, target, address, vision):
    result = {**target, "success": False, "public_ipv4_only": True,
              "provider_connection": False, "direct_fallback": False}
    start, phase = time.monotonic(), "native-import"
    core, handle = None, None
    baseline, baseline_tcp = peer.observations(), peer.public_connections(target, address)
    try:
        config = imported_configuration(peer)
        result.update(subscription_original_preserved=True, native_candidate_parameters_preserved=True)
        phase, core = "native-start", DeadlineControl()
        response = core.command(op="start", config=config)
        require(response.get("ok") is True, "NativeStartRejected")
        handle, state = response["handle"], response["status"]
        require(state["engine"] == "swirl-rust" and state["selected"] == peer.identity,
                "NativeRuntimeIdentityMismatch")
        host, port = state["address"].rsplit(":", 1)
        require(host == "127.0.0.1" and 0 < int(port) < 65536, "NativeListenerMismatch")
        phase = "public-request"
        origin_request(int(port), target, vision, result, start + 45)
        phase = "official-peer-evidence"
        cutoff = time.monotonic() + 3
        while True:
            observed = peer.observations()
            delta = {key: observed[key] - baseline[key] for key in (
                "vless_accepted_sessions", "reality_authenticated_sessions", "client_finished_verified_sessions",
                "vision_padding_events", "vision_unpadding_events", "vision_direct_upload_commands",
                "vision_direct_download_commands")}
            opened = peer.public_connections(target, address) - baseline_tcp
            complete = (delta["vless_accepted_sessions"] == 1 and opened == 1 and
                        delta["reality_authenticated_sessions"] >= 1 and
                        delta["client_finished_verified_sessions"] >= 1)
            if vision:
                complete = complete and delta["vision_padding_events"] > 0 and delta["vision_unpadding_events"] > 0
                if target["port"] == 443:
                    complete = (complete and delta["vision_direct_upload_commands"] > 0 and
                                delta["vision_direct_download_commands"] > 0)
            if complete or time.monotonic() >= cutoff:
                break
            time.sleep(0.02)
        result["official_xray"] = {**delta, "public_tcp_connections": opened,
                                    "camouflage_application_bytes": observed["camouflage_application_bytes"]}
        require(delta["vless_accepted_sessions"] == 1 and opened == 1 and
                delta["reality_authenticated_sessions"] >= 1 and delta["client_finished_verified_sessions"] >= 1 and
                observed["camouflage_application_bytes"] == 0, "OfficialAuthenticatedPublicEvidenceMissing")
        if vision:
            require(delta["vision_padding_events"] > 0 and delta["vision_unpadding_events"] > 0,
                    "VisionFramingEvidenceMissing")
            if target["port"] == 443:
                require(result["tls_version"] == "TLSv1.3" and delta["vision_direct_upload_commands"] > 0 and
                        delta["vision_direct_download_commands"] > 0, "VisionDirectEvidenceMissing")
        result["success"] = True
    except Exception as error:
        result["failure"] = failure(error, phase)
    finally:
        if core is not None and handle is not None and core.usable:
            phase, snapshot = "native-accounting", {}
            try:
                state = public_http.settled_snapshot(lambda deadline, **command: core.command(deadline=deadline, **command),
                                                     handle, time.monotonic() + 8, snapshot)
                result["native"] = {key: state[key] for key in (
                    "accepted", "active", "failed", "upload", "download", "recorded_connections")}
                result["native"]["error_present"] = bool(state["last_error"] or state.get("last_error_stage"))
                require(public_http.native_traffic_error(state) is None, "NativeRelayAccountingFailed")
                require(core.command(op="stop", handle=handle).get("ok") is True, "NativeStopRejected")
            except Exception as error:
                result["success"] = False
                result["cleanup_failure"] = failure(error, phase)
        if core is not None:
            try:
                core.close()
                result["native_process_reaped"] = True
            except Exception as error:
                result["success"] = False
                result["cleanup_failure"] = failure(error, "native-process-cleanup")
        result["elapsed_ms"] = round((time.monotonic() - start) * 1000)
    return result


def source_is_clean():
    paths = ["core", "tools/tests", "tools/Verify-PublicRustCore.py", "tools/Verify-PublicRealityRuntime.py"]
    changed = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *paths], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", paths[-1]], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    require(changed.returncode in (0, 1) and tracked.returncode in (0, 1), "GitSourceIdentityFailed")
    return changed.returncode == tracked.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("harness", "inspector", "xray-peer-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--vision", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = output.parent / (output.stem + "-evidence")
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"schema": 1, "success": False, "platform": platform.system(),
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "checks": [],
              "protocol": "vless+reality" + ("+vision" if args.vision else ""),
              "flow": FLOW if args.vision else "", "verifier_sha256": sha256(Path(__file__)),
              "public_target_dns": "Explicit test-launcher system lookup; one public IPv4 pinned at Xray per origin",
              "scope": "Native Rust subscription import and Runtime through official Xray to explicit public origins; not Qt, provider or TUN acceptance"}
    phase, peer = "identity", None
    try:
        require(platform.system() == "Linux", "LinuxPublicGateRequired")
        os.environ["SWIRL_RUST_HARNESS"] = str(args.harness.resolve(strict=True))
        os.environ["SWIRL_RUST_INSPECTOR"] = str(args.inspector.resolve(strict=True))
        os.environ["SWIRL_XRAY_PEER_DIR"] = str(args.xray_peer_dir.resolve(strict=True))
        binary = verified_build(evidence)
        identity = json.loads((evidence / "source-identity.json").read_text(encoding="utf-8"))
        report.update(commit=identity["git_sha"], tracked_worktree_clean=source_is_clean())
        if not report["tracked_worktree_clean"]:
            report["source_identity_pending"] = "Verifier and relevant source must be committed without changes"
        phase = "explicit-public-dns"
        destinations = [(target, public_address(target["host"])) for target in TARGETS]
        with tempfile.TemporaryDirectory(prefix="swirl-public-reality-") as folder:
            try:
                phase = "official-peer-start"
                peer = PublicPeer(binary, Path(folder) / "peer", evidence, destinations, report["flow"])
                peer.start()
                report["checks"] = [probe(peer, target, address, args.vision) for target, address in destinations]
            finally:
                if peer is not None:
                    try:
                        peer.close()
                        report["official_peer_cleanup_passed"] = True
                    except Exception as error:
                        report["cleanup_failure"] = failure(error, "official-peer-cleanup")
        report["success"] = (report["tracked_worktree_clean"] and "cleanup_failure" not in report and
                             all(check["success"] for check in report["checks"]))
    except Exception as error:
        report["failure"] = failure(error, phase)
    write_json(output, report)
    print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
