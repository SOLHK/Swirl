"""Run actual QA/Release entry refusals using synthetic paths, never live inputs.

An intentionally absent QPA plugin makes a regressed ordinary GUI entry fail
before it can construct a store or start networking. Mixed self-tests are the
existing TLS metadata and fixed loopback checks; --recover-tun has extra arguments, so even
the old dispatch must reject it without running recovery. PowerShell receives
a nonexistent executable. No negative control can start a real node or TUN.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
ERROR = b'{"errorCode":"AuthenticatedBillingAndWireGuardRequired","networkStarted":false}'
MARKER = "SWIRL_REFUSAL_PRIVATE_SENTINEL"
OPTIONS = ("--runtime-store", "--runtime-commands", "--runtime-state")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {str(path.relative_to(root)): {"sha256": sha256(path), "mtime_ns": path.stat().st_mtime_ns}
            if path.is_file() else {"directory": True}
            for path in sorted(root.rglob("*"))}


def run_case(name, command, private, environment, output):
    before = snapshot(private)
    started = time.monotonic()
    process = None
    row = {"name": name, "success": False, "timed_out": False, "exit_confirmed": False, "errors": []}
    stdout_path, stderr_path = output / (name + ".stdout.log"), output / (name + ".stderr.log")
    phase = "open-output"
    try:
        try:
            with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
                phase = "process-start"
                process = subprocess.Popen(command, cwd=private, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=stdout, stderr=stderr)
                phase = "process-wait"
                try:
                    row["exit_code"] = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    row["timed_out"] = True
                    phase = "timeout-kill"
                    process.kill()
                    phase = "timeout-exit-wait"
                    row["exit_code"] = process.wait(timeout=5)
                row["exit_confirmed"] = process.returncode is not None
            phase = "output-evidence"
            stdout, stderr = stdout_path.read_bytes(), stderr_path.read_bytes()
            row.update({"stdout_sha256": sha256(stdout_path), "stderr_sha256": sha256(stderr_path),
                        "stdout_empty": not stdout, "fixed_error": stderr.strip() == ERROR,
                        "argument_value_redacted": MARKER.encode() not in stdout + stderr,
                        "synthetic_tree_unchanged": snapshot(private) == before})
            row["success"] = (row["exit_code"] == 64 and not row["timed_out"] and row["exit_confirmed"]
                              and all(row[key] for key in ("stdout_empty", "fixed_error", "argument_value_redacted",
                                                         "synthetic_tree_unchanged")))
        except Exception as error:
            # Exception messages can contain arguments. Keep only fixed stage
            # names and exception types; no failed exit check supplies proof.
            row["errors"].append({"stage": phase, "type": type(error).__name__})
            row["success"] = row["exit_confirmed"] = False
        finally:
            try:
                phase = "cleanup-poll"
                if process is not None and process.poll() is None:
                    phase = "cleanup-kill"
                    process.kill()
                    phase = "cleanup-exit-wait"
                    process.wait(timeout=5)
            except Exception as error:
                row["errors"].append({"stage": phase, "type": type(error).__name__})
                row["success"] = row["exit_confirmed"] = False
    finally:
        # Record even an unconfirmed cleanup failure; never skip this receipt
        # because the final kill/wait raised. Raw child output stays on disk.
        row["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        (output / (name + ".json")).write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


def cases(paths, receipt):
    complete = [option + "=" + str(path) for option, path in zip(OPTIONS, paths)]
    for index, (option, path) in enumerate(zip(OPTIONS, paths)):
        for form, arguments in (("bare", [option]), ("empty", [option + "="]),
                                ("value", [option + "=" + str(path)]), ("separate", [option, str(path)])):
            yield f"option-{index + 1}-{form}", arguments
    yield "incomplete-pair", complete[:2]
    yield "complete", complete
    yield "duplicate-empty-last", complete + [OPTIONS[0] + "="]
    for label, dispatch in (("rust-self-test", ["--rust-core-self-test", str(receipt)]),
                            ("tls-self-test", ["--tls-runtime-self-test", str(receipt)]),
                            ("recover-tun", ["--recover-tun"])):
        yield label + "-before", dispatch + complete
        yield label + "-after", complete + dispatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--expected-source", required=True)
    parser.add_argument("--flavor", choices=("qa", "release"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--powershell", action="append", default=[], help="Explicit host path; repeat for 5.1 and 7")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": 1, "scope": "actual-legacy-runtime-entry-refusal", "success": False,
              "flavor": args.flavor, "platform": platform.platform(), "python": platform.python_version(),
              "identity_scope": {"flavor": "requested label, not observed build flavor",
                                 "source_sha": "checkout HEAD, not read from the executable",
                                 "executable_sha256": "actual tested executable bytes",
                                 "build_identity": "requires the same EXE SHA in this run's full-motion receipt with observed qml_cache flavor and/or package manifest"},
              "cases": [], "provider_requests": 0, "real_node_requests": 0,
              "qpa_platform": "swirl-refusal-must-precede-gui", "private_inputs": "synthetic-sentinels-only"}
    try:
        source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if source != args.expected_source:
            raise RuntimeError("CheckoutSourceMismatch")
        # Windows PowerShell 5.1 otherwise decodes this Chinese legacy source
        # as ANSI before executing its early refusal, possibly changing quotes.
        report["launcher_utf8_bom"] = (ROOT / "tools/Invoke-WindowsRustAcceptance.ps1").read_bytes().startswith(b"\xef\xbb\xbf")
        if not report["launcher_utf8_bom"]:
            raise RuntimeError("LegacyLauncherUtf8BomRequired")
        executable = args.executable.resolve(strict=True)
        report.update({"source_sha": source, "executable_sha256": sha256(executable),
                       "checkout_changes": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines(),
                       "input_sha256": {name: sha256(ROOT / name) for name in
                           ("src/Swirl.Quick/main.cpp", "tools/Invoke-WindowsRustAcceptance.ps1",
                            "tools/tests/test_runtime_acceptance_refusal.py")}})
        with tempfile.TemporaryDirectory(prefix="swirl-runtime-refusal-") as temporary:
            private = Path(temporary).resolve()
            paths = [private / (MARKER + f"-{index}.dat") for index in range(3)]
            for path in paths:
                path.write_bytes(b"Synthetic sentinel, not an encrypted node store.\n")
            environment = os.environ.copy()
            environment["QT_QPA_PLATFORM"] = report["qpa_platform"]
            environment["SWIRL_TEST_ROOT"] = str(private / "must-not-create-profile")
            for name, arguments in cases(paths, private / "must-not-create-self-test.json"):
                row = run_case(name, [str(executable), *arguments], private, environment, output)
                report["cases"].append(row)
                if not row["success"]:
                    raise RuntimeError("ExecutableRefusalFailed:" + name)
            for index, host in enumerate(args.powershell):
                host = Path(host).resolve(strict=True)
                command = [str(host), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-File", str(ROOT / "tools/Invoke-WindowsRustAcceptance.ps1")]
                supplied = ["-SwirlExe", str(private / (MARKER + "-absent.exe")), "-EncryptedStore", str(paths[0]),
                            "-WorkDirectory", str(private / (MARKER + "-must-not-create")), "-ExpectedSourceSha", MARKER]
                for label, values in (("no-arguments", []), ("partial", ["-EncryptedStore", str(paths[0])]),
                                      ("complete", supplied), ("switches", supplied + ["-ObserveRustOutbound", "-WriteProgress"])):
                    row = run_case(f"powershell-{index + 1}-{label}", command + values,
                                   private, environment, output)
                    row["host_sha256"] = sha256(host)
                    report["cases"].append(row)
                    if not row["success"]:
                        raise RuntimeError("PowerShellRefusalFailed")
        report["success"] = True
    except Exception as error:
        report["failure"] = str(error)
    finally:
        (output / "runtime-refusal.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success": report["success"], "cases": len(report["cases"]), "flavor": args.flavor,
                      "report": str(output / "runtime-refusal.json")}))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
