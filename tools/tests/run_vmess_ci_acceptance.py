"""Run the existing official-peer VMess suite for the current product commit.

The ordinary Rust workflow already exercises SS, Trojan and VLESS. VMess's
independent HTTP/HTTPS suite previously ran only on retired development
branches. Reuse that unchanged suite here and preserve exact source/binary
identity; this is controlled-peer evidence, not provider or Qt acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if source != os.environ.get("GITHUB_SHA", source):
        raise RuntimeError("VMess checkout differs from the workflow commit")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                               cwd=root, text=True).strip():
        raise RuntimeError("VMess acceptance requires unchanged tracked source")
    suffix = ".exe" if os.name == "nt" else ""
    binary = root / "core/target/release"
    peers = evidence.parent / (evidence.name + "-peers")
    commands = []
    receipt = {"source_sha": source, "success": False, "commands": commands,
               "scope": "Native Rust with pinned official Xray and independent HTTP/HTTPS origins",
               "provider_acceptance": False, "qt_acceptance": False,
               "target_half_close_acceptance": False}

    def run(name, command, environment=None):
        with (evidence / (name + ".log")).open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=root, env=environment,
                                    stdout=log, stderr=subprocess.STDOUT)
        commands.append({"name": name, "exit_code": result.returncode})
        if result.returncode:
            # Fixtures contain synthetic credentials only. Keep full output in
            # the artifact and show the final failure, not a stale pass.
            print((evidence / (name + ".log")).read_text(encoding="utf-8")[-12000:])
            raise RuntimeError(f"VMess {name} failed ({result.returncode})")

    try:
        run("build", ["cargo", "build", "--manifest-path", "core/Cargo.toml",
                      "--release", "--locked", "-p", "swirl-core", "--example",
                      "transport-runtime", "-p", "swirl-protocol", "--example",
                      "transport-client"])
        peer_environment = os.environ.copy()
        # Fetch only test peers, without changing later workflow steps' peers.
        peer_environment.pop("GITHUB_ENV", None)
        run("fetch", [sys.executable, "tools/Fetch-TransportPeers.py", "--output",
                      str(peers)], peer_environment)
        (evidence / "peer-manifest.json").write_bytes((peers / "manifest.json").read_bytes())
        environment = os.environ.copy()
        paths = {
            "SWIRL_TRANSPORT_CLIENT": binary / ("examples/transport-client" + suffix),
            "SWIRL_TRANSPORT_RUNTIME": binary / ("examples/transport-runtime" + suffix),
            "SWIRL_INSPECT_BINARY": binary / ("swirl-inspect" + suffix),
            "SWIRL_XRAY_BINARY": peers / "current" / ("xray" + suffix),
        }
        receipt["binaries"] = {key: hashlib.sha256(path.read_bytes()).hexdigest()
                               for key, path in paths.items()}
        environment.update({key: str(path) for key, path in paths.items()})
        environment.update(SWIRL_TRANSPORT_EVIDENCE=str(evidence / "sessions"),
                           SWIRL_VMESS_EVIDENCE=str(evidence), PYTHONUTF8="1")
        run("tests", [sys.executable, "tools/tests/test_vmess_xray.py"], environment)
        summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
        if (summary["suite"] != "data_and_completed_response_close"
                or summary["tests_run"] < 14 or summary["failures"] or summary["errors"]
                or summary["skipped"] or summary["exit_code"]):
            raise RuntimeError("The complete VMess suite did not execute successfully")
        if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                   cwd=root, text=True).strip():
            raise RuntimeError("Tracked source changed during VMess acceptance")
        receipt["tests_run"] = summary["tests_run"]
        receipt["success"] = True
        print(f"VMess: {summary['tests_run']} official-peer cases passed for {source}")
    finally:
        (evidence / "source.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
