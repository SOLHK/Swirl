"""Read-only CONNECT/TLS/HTTP probe; no account token or system setting changes.

This is an unauthenticated reachability check, NOT Codex WS/SSE acceptance.
Run: python Probe-CodexProxyPath.py --ports 7897 7898 --output probe.json
"""
import argparse
import concurrent.futures
import datetime
import json
import socket
import ssl
import time
from pathlib import Path


def header(sock):
    data = bytearray()
    while b"\r\n\r\n" not in data and len(data) < 16384:
        block = sock.recv(1)
        if not block:
            raise EOFError("EOF before response headers completed")
        data.extend(block)
    if b"\r\n\r\n" not in data:
        raise ValueError("response headers exceed diagnostic limit")
    return bytes(data).split(b"\r\n", 1)[0].decode("ascii", "replace")


def probe(port, host):
    start = time.monotonic()
    result = dict(proxy=f"127.0.0.1:{port}", host=host, stage="proxy TCP")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=8) as raw:
            result["stage"] = "HTTP CONNECT"
            raw.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode("ascii"))
            result["connectStatus"] = header(raw)
            if result["connectStatus"].split()[1] != "200":
                result["outcome"] = "proxy rejected CONNECT"
                return result
            result["stage"] = "TLS"
            context = ssl.create_default_context()
            context.set_alpn_protocols(["http/1.1"])
            with context.wrap_socket(raw, server_hostname=host) as tls:
                result["tls"] = tls.version()
                result["stage"] = "HTTP response"
                tls.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode("ascii"))
                result["httpStatus"] = header(tls)
                result["outcome"] = "HTTP response received; authentication and streaming untested"
    except Exception as error:
        result["outcome"] = "failed"
        result["errorType"] = type(error).__name__
        result["errorCode"] = getattr(error, "winerror", None) or getattr(error, "errno", None)
        result["error"] = str(error)[:240]
    finally:
        result["elapsedMs"] = round((time.monotonic() - start) * 1000)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ports", type=int, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if any(port < 1 or port > 65535 for port in args.ports):
        parser.error("ports must be between 1 and 65535")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(probe, port, host) for port in args.ports
                   for host in ("auth.openai.com", "api.openai.com", "chatgpt.com", "openai.com", "ws.chatgpt.com", "codex-cloud-backend.chatgpt.com")]
        results = [future.result() for future in futures]
    report = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  limitation="No authentication, WebSocket upgrade or SSE stream is tested. Proxy resolves targets; this does not inspect its DNS answer.",
                  results=results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
