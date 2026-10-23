#!/usr/bin/env python3
"""Measure UDP host prerequisites for independent protocol-server tests.

This is test-runner preparation, never a Swirl runtime dependency. By default
it only probes and reports; a failed prerequisite returns a nonzero exit code.
Only explicit --prepare-macos on Darwin may change a sysctl, for a disposable
CI runner. All protocol tests retain their original 65507-byte UDP payloads.
"""
from __future__ import annotations

import argparse
import datetime
import errno
import hashlib
import json
from pathlib import Path
import platform
import socket
import subprocess


UDP_MAX_PAYLOAD = 65_507
SIZES = (123, 4096, UDP_MAX_PAYLOAD)
SYSCTL = "/usr/sbin/sysctl"
SOURCES = [
    "https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/netinet/udp_usrreq.c",
    "https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/netinet6/udp6_usrreq.c",
    "https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/uipc_socket.c",
    "https://github.com/tuic-protocol/tuic/blob/a299ef02d9f4ab5a0edbf58b9998f41bf768b332/tuic-server/src/connection/udp_session.rs",
]


def sysctl_values():
    if platform.system() != "Darwin":
        return {}
    values = {}
    for name in ("net.inet.udp.maxdgram", "net.inet.udp.recvspace", "kern.ipc.maxsockbuf"):
        value = subprocess.run([SYSCTL, "-n", name], check=True,
                               capture_output=True, text=True, timeout=10)
        values[name] = int(value.stdout.strip())
    return values


def udp_probe(family, host, size):
    """Use fresh, unmodified sockets in both directions, outside any proxy."""
    result = {"address_family": "IPv6" if family == socket.AF_INET6 else "IPv4",
              "payload_bytes": size, "ok": False, "stage": "create-sockets"}
    payload = bytes((index * 31 + 17) % 251 for index in range(size))
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as sender, \
                socket.socket(family, socket.SOCK_DGRAM) as receiver:
            sender.settimeout(2)
            receiver.settimeout(2)
            sender.bind((host, 0))
            receiver.bind((host, 0))
            result["socket_defaults"] = {
                "sender_sndbuf": sender.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF),
                "sender_rcvbuf": sender.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF),
                "receiver_sndbuf": receiver.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF),
                "receiver_rcvbuf": receiver.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF),
            }
            result["stage"] = "send"
            if sender.sendto(payload, receiver.getsockname()) != size:
                raise RuntimeError("partial UDP send")
            result["stage"] = "receive"
            received, source = receiver.recvfrom(65_535)
            if received != payload:
                raise RuntimeError("UDP receive data mismatch")
            result["stage"] = "reply"
            if receiver.sendto(received, source) != size:
                raise RuntimeError("partial UDP reply")
            result["stage"] = "receive-reply"
            reply, _ = sender.recvfrom(65_535)
            if reply != payload:
                raise RuntimeError("UDP reply data mismatch")
            result.update(ok=True, stage="roundtrip-complete",
                          sha256=hashlib.sha256(reply).hexdigest())
    except OSError as error:
        result.update(error_type=type(error).__name__, errno=error.errno,
                      error=str(error), emsgsize=error.errno == errno.EMSGSIZE)
    except RuntimeError as error:
        result.update(error_type=type(error).__name__, error=str(error))
    return result


def snapshot():
    values = sysctl_values()
    probes = [udp_probe(family, host, size)
              for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1"))
              for size in SIZES]
    return {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "sysctl": values, "udp_roundtrips": probes,
            "ok": all(probe["ok"] for probe in probes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("out/native-interop/platform.json"))
    parser.add_argument("--prepare-macos", action="store_true",
                        help="allow raising Darwin UDP defaults on a disposable CI runner")
    args = parser.parse_args()
    report = {"platform": platform.platform(), "prepare_macos_requested": args.prepare_macos,
              "scope": "host UDP prerequisite; not proxy protocol interoperability",
              "sources": SOURCES, "system_setting_changed": False, "ok": False}
    try:
        report["before"] = before = snapshot()
        if not before["ok"] and platform.system() == "Darwin" and args.prepare_macos:
            failures = [probe for probe in before["udp_roundtrips"] if not probe["ok"]]
            needs_send = before["sysctl"]["net.inet.udp.maxdgram"] < UDP_MAX_PAYLOAD
            needs_receive = before["sysctl"]["net.inet.udp.recvspace"] < 65_535
            for probe in failures:
                known_send_limit = needs_send and probe.get("emsgsize")
                known_receive_limit = (needs_receive and probe.get("error_type") == "TimeoutError"
                                       and probe["stage"] in ("receive", "receive-reply"))
                if probe["payload_bytes"] != UDP_MAX_PAYLOAD or not (known_send_limit or known_receive_limit):
                    raise RuntimeError("UDP prerequisite failed outside Darwin's measured default socket-buffer limits")
            # The fixed official TUIC peer creates its destination sockets
            # with OS defaults and exposes no send-buffer configuration. Raise
            # only the new-socket default before any test peer is started.
            changes = []
            if needs_send:
                changes.append(("net.inet.udp.maxdgram", 65_535))
            # Current XNU defaults already exceed this. Older or customized
            # runners can need space for a complete payload plus its address.
            if needs_receive:
                changes.append(("net.inet.udp.recvspace", 131_072))
            report["preparation"] = []
            for setting, value in changes:
                completed = subprocess.run(["sudo", "-n", SYSCTL, "-w", f"{setting}={value}"],
                                           capture_output=True, text=True, timeout=10)
                report["preparation"].append({"setting": setting, "value": value,
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()})
                if completed.returncode != 0:
                    raise RuntimeError("explicit Darwin UDP default adjustment failed")
                report["system_setting_changed"] = True
            report["after"] = after = snapshot()
            if any(after["sysctl"][setting] != value for setting, value in changes):
                raise RuntimeError("Darwin UDP default did not match the requested value")
        else:
            report["after"] = after = before
        report["ok"] = after["ok"]
        if not report["ok"]:
            report["error"] = "host cannot complete the required unchanged UDP payloads"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "system_setting_changed": report["system_setting_changed"],
                      "evidence": str(args.output), "error": report.get("error")}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
