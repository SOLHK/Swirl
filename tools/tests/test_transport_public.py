"""Manual public-target probes through a local, pinned official Xray peer.

This is deliberately not part of automatic CI. It uses no remote public proxy
node, private subscription, provider account, HTTP(S)_PROXY, or insecure TLS.
The transit peer is an isolated loopback Xray fixture; Swirl's native Rust
transport-client remains the client. Public target HTTPS uses the native
default root store and example.com SNI, never the fixture's private CA.

After building transport-client, set SWIRL_TRANSPORT_CLIENT,
SWIRL_XRAY_BINARY, SWIRL_XRAY_LEGACY_BINARY and SWIRL_TRANSPORT_EVIDENCE as for
the independent local suites, then run this file with --output <result.json>.
--direct-only can diagnose direct DNS/TCP/TLS/HTTP before a client is built.
Failure is recorded and returns nonzero; blocked preflight is never a pass.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import http.client
import json
from pathlib import Path
import platform
import socket
import ssl
import subprocess
import sys
import time
from types import SimpleNamespace


HOST = "example.com"
BODY_LIMIT = 1024 * 1024
# name -> official peer network, outer TLS, legacy peer, gRPC mode
TRANSPORTS = {
    "tcp": ("raw", False, False, None),
    "tcp_tls": ("raw", True, False, None),
    "websocket": ("ws", False, False, None),
    "wss": ("ws", True, False, None),
    "grpc": ("grpc", False, False, "tun"),
    "grpc_tls": ("grpc", True, False, "tun"),
    "grpc_multi": ("grpc", False, False, "tun_multi"),
    "grpc_multi_tls": ("grpc", True, False, "tun_multi"),
    "http2_tls": ("h2", True, True, None),
    "httpupgrade": ("httpupgrade", False, False, None),
    "httpupgrade_tls": ("httpupgrade", True, False, None),
    "xhttp_stream_one": ("xhttp", False, False, None),
    "xhttp_stream_one_tls": ("xhttp", True, False, None),
}


def direct_probe(scheme, seconds):
    """Runs in a bounded child process so even system DNS cannot hang the CLI."""
    port = 443 if scheme == "https" else 80
    result = {"target": f"{scheme}://{HOST}/", "ok": False,
              "environment_proxy_used": False, "certificate_verified": False}
    started = time.monotonic()
    phase = "dns_tcp"
    try:
        context = ssl.create_default_context()
        context.set_alpn_protocols(["http/1.1"])
        with socket.create_connection((HOST, port), timeout=seconds) as raw:
            result["peer_ip"] = raw.getpeername()[0]
            phase = "tls" if scheme == "https" else "http"
            stream = context.wrap_socket(raw, server_hostname=HOST) if scheme == "https" else raw
            with stream:
                stream.settimeout(seconds)
                if scheme == "https":
                    result.update(certificate_verified=True, sni=HOST,
                                  tls_version=stream.version(), alpn=stream.selected_alpn_protocol())
                phase = "http"
                stream.sendall(f"GET / HTTP/1.1\r\nHost: {HOST}:{port}\r\nConnection: close\r\n\r\n".encode())
                response = http.client.HTTPResponse(stream)
                response.begin()
                result["http_status"] = response.status
                raw_length = response.getheader("Content-Length")
                result["content_length"] = raw_length
                result["transfer_encoding"] = response.getheader("Transfer-Encoding")
                if response.status != 200:
                    raise ValueError("PublicHttpStatus")
                if raw_length is None or not raw_length.isdecimal() or result["transfer_encoding"]:
                    raise ValueError("PublicResponseFramingUnsupported")
                length = int(raw_length)
                if not 0 < length <= BODY_LIMIT:
                    raise ValueError("PublicResponseLengthLimit")
                body = response.read(length)
                if len(body) != length:
                    raise EOFError("PublicResponseTruncated")
                result.update(body_bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), ok=True)
                # Direct preflight only establishes a verified reference body.
                # Native transport closure is checked separately below.
    except (OSError, ValueError, EOFError, http.client.HTTPException) as error:
        result.update(error_type=type(error).__name__, error=str(error), failure_phase=phase)
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    return result


def bounded_direct_probe(scheme, seconds):
    started = time.monotonic()
    try:
        process = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                  "--direct-child", scheme, "--timeout", str(seconds)],
                                 capture_output=True, text=True, timeout=seconds + 1)
        result = json.loads(process.stdout)
        result["exit_code"] = process.returncode
        return result
    except (subprocess.TimeoutExpired, OSError, ValueError) as error:
        return {"target": f"{scheme}://{HOST}/", "ok": False,
                "error_type": type(error).__name__, "failure_phase": "direct_probe",
                "error": "DirectProbeTimeout" if isinstance(error, subprocess.TimeoutExpired)
                         else "DirectProbeProcessFailed",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}


def native_probe(fixture, peer, name, scheme, reference, seconds):
    port = 443 if scheme == "https" else 80
    target = SimpleNamespace(target_host=HOST, target_port=port, context=None)
    request = fixture.request(peer, target, path="/", timeout_ms=seconds * 1000)
    if scheme == "https":
        # Intentionally omit ca_der_base64: authenticate the public target
        # using the native root store, independently of outer fixture TLS.
        request["target_tls"] = {"server_name": HOST, "alpn": ["http/1.1"]}
    mode = TRANSPORTS[name][3]
    if mode:
        request["transport"]["config"]["mode"] = mode
    result = {"scope": "local_official_peer_to_public_target", "transport": name,
              "protocol": peer["protocol"], "target": f"{scheme}://{HOST}/",
              "server": peer["version"], "outer_tls": peer["tls"],
              "target_tls": scheme == "https", "remote_public_proxy_node_tested": False,
              "ok": False}
    try:
        process, report = fixture.run(request, timeout=seconds + 5)
        result.update(exit_code=process.returncode, native=report)
        try:
            fixture.assert_accepted(peer, target)
            result["independent_peer_accepted_target"] = True
        except AssertionError:
            result["independent_peer_accepted_target"] = False
        # The native HTTP client requires status 200, Content-Length and the
        # complete body before returning ok. Keep closure and content checks
        # independent so a partial success is never promoted to a full pass.
        response_ok = (process.returncode == 0 and report.get("ok") is True
                       and 0 < report.get("downloaded", 0) <= BODY_LIMIT
                       and isinstance(report.get("sha256"), str)
                       and len(report["sha256"]) == 64)
        result["public_response_received"] = response_ok
        result["public_certificate_verified"] = response_ok and scheme == "https"
        result["matches_direct_reference"] = (
            report.get("sha256") == reference.get("sha256")
            and report.get("downloaded") == reference.get("body_bytes")
        ) if reference.get("ok") else None
        result["ok"] = bool(response_ok and result["independent_peer_accepted_target"]
                            and report.get("close") == "clean"
                            and report.get("remaining_tasks") == 0
                            and result["matches_direct_reference"] is not False)
    except (OSError, AssertionError, subprocess.TimeoutExpired) as error:
        result.update(error_type=type(error).__name__, error=str(error))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transports", nargs="+", choices=list(TRANSPORTS), default=list(TRANSPORTS))
    parser.add_argument("--protocol", choices=("vless", "trojan"), default="vless")
    parser.add_argument("--schemes", nargs="+", choices=("http", "https"), default=["http", "https"])
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--direct-only", action="store_true")
    parser.add_argument("--attempt-native-on-preflight-failure", action="store_true",
                        help="record native failure evidence even if direct DNS/TCP/TLS failed")
    parser.add_argument("--direct-child", choices=("http", "https"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 30:
        parser.error("--timeout must be between 1 and 30 seconds")
    if args.direct_child:
        result = direct_probe(args.direct_child, args.timeout)
        print(json.dumps(result))
        return 0 if result["ok"] else 1
    if args.protocol == "trojan" and any(not TRANSPORTS[name][1] for name in args.transports):
        parser.error("Trojan requires an explicit selection of TLS transit transports")
    schemes = list(dict.fromkeys(args.schemes))
    transports = list(dict.fromkeys(args.transports))
    report = {"scope": "local_official_peer_to_public_target",
              "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "platform": platform.platform(), "automatic_ci": False,
              "command": sys.argv, "environment_proxy_used": False,
              "remote_public_proxy_node_tested": False,
              "requested_transports": transports, "protocol": args.protocol,
              "direct_preflight": [], "native_probes": [], "ok": False}
    reference = {scheme: bounded_direct_probe(scheme, args.timeout) for scheme in schemes}
    report["direct_preflight"] = list(reference.values())
    if args.direct_only:
        report["scope"] = "direct_public_target_preflight_only"
        report["ok"] = all(item["ok"] for item in reference.values())
    elif not any(item["ok"] for item in reference.values()) and not args.attempt_native_on_preflight_failure:
        report["blocked"] = "DirectPublicPreflightFailed"
        report["native_not_attempted"] = True
    else:
        # Import only after preflight so direct-only diagnosis requires no
        # fixture binaries, cryptography package or native build artifacts.
        from transport_peer import Fixture

        fixture = None
        try:
            fixture = Fixture("C6-public-target")
            report["fixture_evidence"] = str(fixture.evidence)
            for name in transports:
                network, tls, legacy, _ = TRANSPORTS[name]
                peer = fixture.peer(network, protocol=args.protocol, tls=tls, legacy=legacy)
                for scheme in schemes:
                    result = native_probe(fixture, peer, name, scheme, reference[scheme], args.timeout)
                    report["native_probes"].append(result)
                    print(json.dumps(result), flush=True)
                fixture.terminate(peer)
            report["ok"] = bool(report["native_probes"]) and all(item["ok"] for item in report["native_probes"])
        except (OSError, AssertionError, KeyError, subprocess.SubprocessError) as error:
            report.update(error_type=type(error).__name__, error=str(error))
        finally:
            if fixture is not None:
                try:
                    fixture.close()
                except (OSError, AssertionError, subprocess.SubprocessError) as error:
                    report.update(ok=False, cleanup_error=str(error))
    report["public_target_response_verified"] = any(
        item.get("public_response_received") and item.get("independent_peer_accepted_target")
        for item in report["native_probes"])
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
