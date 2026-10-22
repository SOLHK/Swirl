"""Measure one fixed IPv4 HTTPS 204 target through a local HTTP proxy.

No proxy credentials, request body, response body or node configuration is read.
CONNECT includes the proxy's upstream dial; it cannot split a Shadowsocks TCP
connect from its encrypted handshake. The TCP figure is only loopback to the
local proxy. TLS verification remains enabled.
"""

import argparse
import ipaddress
import json
import socket
import ssl
import statistics
import time


def ms(start, end):
    return round((end - start) * 1000, 3)


def header(sock):
    data = bytearray()
    first = None
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise EOFError("peer closed before HTTP headers")
        if first is None:
            first = time.perf_counter()
        data.extend(chunk)
        if len(data) > 16384:
            raise ValueError("HTTP headers exceed 16 KiB")
    return bytes(data), first, time.perf_counter()


def connect(proxy_port, target_ip, target_host, context):
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.settimeout(12)
    start = time.perf_counter()
    try:
        raw.connect(("127.0.0.1", proxy_port))
        tcp = time.perf_counter()
        address = f"{target_ip}:443"
        raw.sendall(f"CONNECT {address} HTTP/1.1\r\nHost: {address}\r\n\r\n".encode("ascii"))
        response, _, proxy_done = header(raw)
        if not response.startswith(b"HTTP/1.1 200 ") and not response.startswith(b"HTTP/1.0 200 "):
            raise RuntimeError("proxy CONNECT did not return 200")
        secure = context.wrap_socket(raw, server_hostname=target_host)
        tls_done = time.perf_counter()
        if secure.selected_alpn_protocol() not in (None, "http/1.1"):
            raise RuntimeError("unexpected TLS application protocol")
        return secure, {"loopbackTcpMs": ms(start, tcp),
                        "proxyConnectMs": ms(tcp, proxy_done),
                        "verifiedTlsMs": ms(proxy_done, tls_done)}
    except Exception:
        raw.close()
        raise


def request(secure, host):
    start = time.perf_counter()
    secure.sendall((f"GET /generate_204 HTTP/1.1\r\nHost: {host}\r\n"
                    "Connection: keep-alive\r\nCache-Control: no-cache\r\n\r\n").encode("ascii"))
    response, first, complete = header(secure)
    if not response.startswith(b"HTTP/1.1 204 ") and not response.startswith(b"HTTP/1.0 204 "):
        raise RuntimeError("target did not return HTTP 204")
    if response.split(b"\r\n\r\n", 1)[1]:
        raise RuntimeError("unexpected body bytes after HTTP 204")
    return {"httpFirstByteMs": ms(start, first), "http204Ms": ms(start, complete)}


def summary(samples, key):
    ordered = sorted(sample[key] for sample in samples)
    return {"medianMs": round(statistics.median(ordered), 3),
            "p95NearestRankMs": ordered[(95 * len(ordered) + 99) // 100 - 1]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-port", type=int, required=True)
    parser.add_argument("--target-ipv4", required=True)
    parser.add_argument("--target-host", default="www.gstatic.com")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 1 <= args.proxy_port <= 65535 or not 10 <= args.samples <= 100:
        parser.error("proxy port or sample count out of range")
    target_ip = ipaddress.ip_address(args.target_ipv4)
    if target_ip.version != 4 or args.target_host != "www.gstatic.com":
        parser.error("this bounded probe accepts only www.gstatic.com over IPv4")
    report = {"scope": "fixed IPv4 HTTPS 204; local HTTP proxy; TLS verified",
              "proxyPort": args.proxy_port, "targetHost": args.target_host,
              "targetIpv4": str(target_ip), "samplesRequested": args.samples,
              "cold": [], "reusedConnection": [], "errors": []}
    context = ssl.create_default_context()
    context.set_alpn_protocols(["http/1.1"])
    for index in range(args.samples):
        try:
            secure, stages = connect(args.proxy_port, target_ip, args.target_host, context)
            with secure:
                response = request(secure, args.target_host)
            report["cold"].append({"sample": index + 1, **stages, **response,
                                   "totalMs": round(sum(stages.values()) + response["http204Ms"], 3)})
        except (OSError, RuntimeError, ValueError) as exc:
            report["errors"].append({"mode": "cold", "sample": index + 1,
                                     "type": type(exc).__name__})
    try:
        secure, stages = connect(args.proxy_port, target_ip, args.target_host, context)
        report["reusedConnectionSetup"] = stages
        with secure:
            for index in range(args.samples):
                report["reusedConnection"].append({"sample": index + 1,
                                                   **request(secure, args.target_host)})
    except (OSError, RuntimeError, ValueError) as exc:
        report["errors"].append({"mode": "reusedConnection", "sample": len(report["reusedConnection"]) + 1,
                                 "type": type(exc).__name__})
    if len(report["cold"]) == args.samples:
        report["coldSummary"] = summary(report["cold"], "totalMs")
    if len(report["reusedConnection"]) == args.samples:
        report["reusedSummary"] = summary(report["reusedConnection"], "http204Ms")
    report["pass"] = not report["errors"] and len(report["cold"]) == args.samples and len(report["reusedConnection"]) == args.samples
    with open(args.output, "x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({"pass": report["pass"], "proxyPort": args.proxy_port,
                      "coldSummary": report.get("coldSummary"),
                      "reusedSummary": report.get("reusedSummary"),
                      "errors": report["errors"]}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
