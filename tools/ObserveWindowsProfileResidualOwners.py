"""Bounded, target-query-only observation after a failed disposable profile cleanup.

The original 30-second result is immutable input. This launcher never deletes a
profile or controls a reported resource owner. Its existing OwnedProcess may
terminate only the separate diagnostic worker at the eight-second work deadline.
OS-confirmed exit and Restart Manager session cleanup are reported separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import ntpath
import os
from pathlib import Path
import re
import stat
import struct
import sys
import threading
import time

MAX_FILES, MAX_OWNERS = 32, 64
MAX_REQUEST, MAX_REPORT, MAX_CAPTURE = 262144, 262144, 65536
WORK_SECONDS = 8.0


class ObservationError(Exception):
    """Fixed diagnostic codes only; never echo supplied paths or values."""


class Arguments(argparse.ArgumentParser):
    def error(self, _message):
        raise ObservationError("OwnerDiagnosticArgumentsRejected")


def validate_request(data):
    """Pure admission checks; filesystem and native APIs are checked separately."""
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data["schema"] != 1:
        raise ObservationError("OwnerDiagnosticRequestInvalid")
    if (data.get("new_account_created") is not True or data.get("profile_removed") is not False
            or data.get("path_verified") is not True or data.get("token_path_verified") is not True
            or type(data.get("cleanup_deadline_ms")) is not int or data["cleanup_deadline_ms"] != 30000
            or not isinstance(data.get("cleanup_elapsed_ms"), (int, float))
            or isinstance(data["cleanup_elapsed_ms"], bool) or not math.isfinite(data["cleanup_elapsed_ms"])
            or data["cleanup_elapsed_ms"] < 30000):
        raise ObservationError("OwnerDiagnosticFrozenFailureRequired")
    source, sid, username = (data.get(k) for k in ("source_sha", "sid", "username"))
    if (not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source)
            or not isinstance(sid, str) or not re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", sid)
            or not isinstance(username, str) or not re.fullmatch(r"swci_[0-9a-f]{12}", username)):
        raise ObservationError("OwnerDiagnosticIdentityInvalid")
    state = data.get("final_state")
    if (not isinstance(state, dict) or state.get("profile_path_exists") is not True
            or any(state.get(k) is not False for k in
                   ("profile_key_exists", "user_hive_loaded", "user_classes_hive_loaded"))):
        raise ObservationError("OwnerDiagnosticResidualStateRequired")
    profile, token_profile = data.get("profile_path"), data.get("token_profile_path")
    if (not isinstance(profile, str) or not isinstance(token_profile, str)
            or ntpath.normcase(ntpath.normpath(profile)) != ntpath.normcase(ntpath.normpath(token_profile))
            or ntpath.basename(profile.rstrip("\\/")).lower() != username):
        raise ObservationError("OwnerDiagnosticProfileBindingInvalid")
    local_path_text(profile)
    local_path_text(token_profile)
    files = data.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ObservationError("OwnerDiagnosticFileLimit")
    seen = set()
    for entry in files:
        if not isinstance(entry, dict) or entry.get("kind") != "file" or entry.get("hresult") is not None:
            raise ObservationError("OwnerDiagnosticRegularFilesRequired")
        relative, attributes, size = (entry.get(k) for k in ("relative_path", "attributes", "bytes"))
        if (not isinstance(relative, str) or not relative or len(relative) > 2048
                or any(c in relative for c in ("\\", ":", "\0"))
                or any(part in ("", ".", "..") or part.endswith((".", " "))
                       or re.match(r"(?i)^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part)
                       for part in relative.split("/"))
                or type(attributes) is not int or attributes < 0 or attributes & (0x10 | 0x400)
                or type(size) is not int or size < 0 or relative.casefold() in seen):
            raise ObservationError("OwnerDiagnosticFileRecordInvalid")
        seen.add(relative.casefold())
    return data


def local_path_text(path):
    """Only ordinary absolute local paths; reject ADS, devices and namespace escapes."""
    if (not isinstance(path, str) or not re.match(r"^[A-Za-z]:\\", path)
            or any(ord(c) < 32 or c in '/:<>"|?*' for c in path[2:])
            or any(part in ("", ".", "..") or part.endswith((".", " "))
                   or re.match(r"(?i)^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part)
                   for part in path[3:].rstrip("\\").split("\\") if path[3:].rstrip("\\"))):
        raise ObservationError("OwnerDiagnosticLocalPathRequired")
    return ntpath.normpath(path)


def plain_path(path, *, regular=False):
    path = Path(local_path_text(str(path)))
    for ancestor in reversed((path, *path.parents)):
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ObservationError("OwnerDiagnosticLinkedPathRejected")
    if regular and not stat.S_ISREG(path.lstat().st_mode):
        raise ObservationError("OwnerDiagnosticRegularFileRequired")
    return path


def within_profile(path, profile):
    path, profile = (ntpath.normcase(local_path_text(str(p))) for p in (path, profile))
    return ntpath.splitdrive(path)[0] == ntpath.splitdrive(profile)[0] and ntpath.commonpath((path, profile)) == profile


def read_limited(path, limit):
    path = plain_path(path, regular=True)
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ObservationError("OwnerDiagnosticInputTooLarge")
    return content


def hash_file(path):
    digest = hashlib.sha256()
    with plain_path(path, regular=True).open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path, data):
    path = plain_path(path)
    temporary = path.with_name(path.name + ".tmp")
    plain_path(temporary)
    with temporary.open("xb") as stream:
        stream.write((json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Capture:
    def __init__(self, stream):
        self.stream, self.kept, self.total = stream, bytearray(), 0
        self.digest, self.error = hashlib.sha256(), None
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        try:
            while block := self.stream.read(4096):
                self.total += len(block)
                self.digest.update(block)
                self.kept.extend(block[:max(0, MAX_CAPTURE - len(self.kept))])
        except Exception:
            self.error = "OwnerDiagnosticOutputReadFailed"

    def finish(self, path):
        self.thread.join(timeout=2)
        joined = not self.thread.is_alive()
        saved = False
        if joined:
            try:
                with plain_path(path).open("xb") as stream:
                    stream.write(self.kept)
                saved = True
            except Exception:
                self.error = self.error or "OwnerDiagnosticOutputSaveFailed"
        return {"joined": joined, "error": self.error, "bytes": self.total,
                "sha256": self.digest.hexdigest() if joined else None,
                "retained_bytes": len(self.kept) if joined else 0,
                "truncated": self.total > MAX_CAPTURE, "file_saved": saved}


def child_environment():
    # This is the launcher's own environment, never another process's environment.
    names = {"OS", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "TEMP", "TMP", "USERPROFILE",
             "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
             "GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "SWIRL_DISPOSABLE_INSTALL_TEST", "GITHUB_SHA"}
    return {key: value for key, value in os.environ.items() if key.upper() in names}


def observe(args):
    if (os.name != "nt" or sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.environ.get("SWIRL_DISPOSABLE_INSTALL_TEST") != "1"):
        raise ObservationError("OwnerDiagnosticHostedWindowsPython312Required")
    approved_python = os.environ.get("SWIRL_PROFILE_OWNER_PYTHON", "")
    if (not approved_python or ntpath.normcase(local_path_text(approved_python))
            != ntpath.normcase(local_path_text(sys.executable))):
        raise ObservationError("OwnerDiagnosticPythonIdentityMismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", args.request_sha256):
        raise ObservationError("OwnerDiagnosticRequestDigestRequired")
    request_path = plain_path(args.request, regular=True)
    raw = read_limited(request_path, MAX_REQUEST)
    if hashlib.sha256(raw).hexdigest() != args.request_sha256:
        raise ObservationError("OwnerDiagnosticRequestDigestMismatch")
    request = validate_request(json.loads(raw.decode("utf-8-sig")))
    if request["source_sha"] != os.environ.get("GITHUB_SHA"):
        raise ObservationError("OwnerDiagnosticSourceMismatch")
    profile = plain_path(request["profile_path"])
    if not profile.is_dir() or profile == Path(os.environ.get("USERPROFILE", "")):
        raise ObservationError("OwnerDiagnosticProfileScopeRejected")
    output = request_path.parent
    if within_profile(output, profile):
        raise ObservationError("OwnerDiagnosticOutputInsideProfile")
    powershell = plain_path(args.powershell, regular=True)
    if powershell.name.lower() != "pwsh.exe":
        raise ObservationError("OwnerDiagnosticPowerShell7Required")
    worker = plain_path(Path(__file__).parent.parent / "scripts/tests/Get-WindowsResidualProfileOwners.ps1", regular=True)
    worker_result = output / "owner-worker.json"
    report_path = output / "owner-diagnostics.json"
    for name in (worker_result, report_path, output / "owner-stdout.log", output / "owner-stderr.log"):
        plain_path(name)
        if name.exists():
            raise ObservationError("OwnerDiagnosticOutputAlreadyExists")
    from PrivateSubscriptionBudget import BudgetError
    from PrivateSubscriptionProcess import OwnedProcess
    report = {"schema": 1, "scope": "Post-failure resource-owner observation; never changes profile acceptance.",
              "source_sha": request["source_sha"], "frozen_request_sha256": args.request_sha256,
              "original_profile_removed": False, "original_cleanup_deadline_ms": 30000,
              "status": "starting", "success": False, "work_deadline_ms": 8000,
              "deadline_scope": "Cancellation trigger; OS exit confirmation is measured separately, not an exact eight-second retirement claim.",
              "python": {"path": str(plain_path(sys.executable, regular=True)), "version": sys.version,
                         "process_bits": 64, "sha256": hash_file(sys.executable)},
              "powershell": {"path": str(powershell), "sha256": hash_file(powershell)},
              "worker_script_sha256": hash_file(worker), "launcher_sha256": hash_file(__file__),
              "owned_process_source_sha256": hash_file(Path(__file__).with_name("PrivateSubscriptionProcess.py")),
              "child_pid": None, "exit_proof": None, "os_exit_confirmation_elapsed_ms": None,
              "owned_process_timed_out": False, "process_cleanup_error": None,
              "session_end_confirmed": False, "worker": None, "error": None, "receipt_error": None}
    save_json(report_path, report)
    child = None
    captures = []
    started = time.monotonic()
    try:
        child = OwnedProcess([str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(worker),
                              "-RequestPath", str(request_path), "-RequestSha256", args.request_sha256,
                              "-OutputPath", str(worker_result)],
                             deadline=started + WORK_SECONDS, environment=child_environment())
        report["child_pid"] = child.pid
        child.stdin.close()
        captures = [("stdout", Capture(child.stdout)), ("stderr", Capture(child.stderr))]
        proof = child.wait(timeout=max(0.001, started + WORK_SECONDS - time.monotonic()) + 2)
        report["exit_proof"] = proof.record()
        report["os_exit_confirmation_elapsed_ms"] = (time.monotonic() - started) * 1000
    except BudgetError as error:
        report["error"] = str(error)
    except Exception:
        report["error"] = "OwnerDiagnosticExecutionFailed"
    finally:
        if child is not None:
            if report["exit_proof"] is None:
                try:
                    proof = child.terminate_and_wait(timeout=2)
                    report["exit_proof"] = proof.record()
                    report["os_exit_confirmation_elapsed_ms"] = (time.monotonic() - started) * 1000
                except BudgetError as error:
                    report["process_cleanup_error"] = str(error)
                except Exception:
                    report["process_cleanup_error"] = "OwnerDiagnosticExitConfirmationFailed"
            report["owned_process_timed_out"] = child.timed_out
            report["watchdog_error"] = child.stop_error
            report["output"] = {name: capture.finish(output / ("owner-" + name + ".log")) for name, capture in captures}
            try:
                child.close()
            except BudgetError as error:
                report["process_cleanup_error"] = report["process_cleanup_error"] or str(error)
            except Exception:
                report["process_cleanup_error"] = report["process_cleanup_error"] or "OwnerDiagnosticHandleCleanupFailed"
        report["total_elapsed_ms"] = (time.monotonic() - started) * 1000
    try:
        if worker_result.exists():
            report["worker"] = json.loads(read_limited(worker_result, MAX_REPORT).decode("utf-8-sig"))
            report["worker_result_sha256"] = hash_file(worker_result)
        result = report["worker"]
        exited = (report["exit_proof"] is not None
                      and not report["owned_process_timed_out"] and report["process_cleanup_error"] is None
                      and report["error"] is None and len(captures) == 2
                      and all(x["joined"] and x["error"] is None and x["bytes"] == 0 for x in report["output"].values()))
        identified = (isinstance(result, dict) and result.get("schema") == 1
                      and result.get("source_sha") == request["source_sha"]
                      and result.get("request_sha256") == args.request_sha256
                      and result.get("worker_script_sha256") == report["worker_script_sha256"]
                      and result.get("powershell_major") == 7 and result.get("process_bits") == 64)
        report["session_end_confirmed"] = bool(exited and identified and result.get("session_end_confirmed") is True)
        report["success"] = bool(exited and report["exit_proof"]["exitCode"] == 0 and identified and result.get("observation_completed") is True
                                 and report["session_end_confirmed"])
        report["status"] = "observed" if report["success"] else "timeout" if report["owned_process_timed_out"] else "incomplete"
    except Exception:
        report["receipt_error"] = "OwnerDiagnosticWorkerReceiptInvalid"
        report["status"] = "incomplete"
    save_json(report_path, report)
    return 0 if report["success"] else 2


def main(argv=None):
    try:
        parser = Arguments(description=__doc__)
        parser.add_argument("--request", required=True)
        parser.add_argument("--request-sha256", required=True)
        parser.add_argument("--powershell", required=True)
        return observe(parser.parse_args(argv))
    except ObservationError as error:
        print(json.dumps({"error": str(error), "target_process_actions": False}))
        return 2
    except Exception:
        print('{"error":"OwnerDiagnosticAdmissionFailed","target_process_actions":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
