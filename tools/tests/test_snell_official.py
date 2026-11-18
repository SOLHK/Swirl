"""Snell v4 native TCP/UDP against the pinned, unmodified vendor server.

Only owned loopback endpoints are used. Missing tools fail rather than skip.
The vendor process is test infrastructure, never included in Swirl packages.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import time


def run():
    output = Path(os.environ["SWIRL_SNELL_EVIDENCE"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "summary.json").exists():
        raise RuntimeError("Use a fresh evidence directory to retain previous failures")
    (output / "summary.json").write_text(json.dumps({
        "success": False, "phase": "initializing",
        "scope": "owned loopback independent official server; no provider or host network changes",
    }, indent=2) + "\n", encoding="utf-8")
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise RuntimeError("Official Snell fixture requires Linux amd64")
    server = Path(os.environ["SWIRL_SNELL_SERVER"]).resolve(strict=True)
    client = Path(os.environ["SWIRL_SNELL_CLIENT"]).resolve(strict=True)
    lock = json.loads(Path(__file__).with_name("snell-peer-lock.json").read_text())
    provenance = json.loads(server.with_name("snell-server-provenance.json").read_text())
    server_hash = hashlib.sha256(server.read_bytes()).hexdigest()
    if (provenance["server_sha256"] != server_hash or server_hash != lock["server_sha256"]
            or any(provenance.get(key) != lock[key] for key in ("url", "archive_sha256", "version"))):
        raise ValueError("Official server provenance differs from the pinned fixture")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    configuration = output / "peer.conf"
    configuration.write_text(f"[snell-server]\nlisten = 127.0.0.1:{port}\n"
                             "psk = swirl-synthetic-peer-psk-2026\n", encoding="utf-8")
    report = {"success": False, "protocol": "Snell v4", "server_version": lock["version"],
              "server_sha256": server_hash, "archive_sha256": lock["archive_sha256"],
              "client_sha256": hashlib.sha256(client.read_bytes()).hexdigest(),
              "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "scope": "owned loopback independent official server; no provider or host network changes"}
    with (output / "server.log").open("wb") as log:
        process = subprocess.Popen([str(server), "-c", str(configuration)], stdout=log, stderr=log,
                                   stdin=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError("OfficialSnellServerExited")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("OfficialSnellStartupTimeout") from None
                    time.sleep(0.05)
            with (output / "client.stdout").open("wb") as stdout, (output / "client.stderr").open("wb") as stderr:
                result = subprocess.run([str(client), str(port)], stdout=stdout, stderr=stderr,
                                        stdin=subprocess.DEVNULL, timeout=20, check=False)
            report["client_exit"] = result.returncode
            if result.returncode:
                raise RuntimeError("NativeSnellInteroperabilityFailed")
            result = json.loads((output / "client.stdout").read_text())
            if result.get("success") is not True:
                raise RuntimeError("NativeSnellEvidenceMissing")
            report["observations"] = result
            report["success"] = True
        except BaseException as error:
            report["failure_class"] = type(error).__name__
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            report["server_retired"] = process.poll() is not None
            (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    run()
