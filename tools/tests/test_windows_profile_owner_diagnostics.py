"""Offline admission tests only: no Windows APIs, resource query or process launch."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ObserveWindowsProfileResidualOwners as diagnostic


def request_fixture():
    return {
        "schema": 1, "source_sha": "1" * 40,
        "new_account_created": True, "profile_removed": False,
        "path_verified": True, "token_path_verified": True,
        "cleanup_deadline_ms": 30000, "cleanup_elapsed_ms": 30001.25,
        "sid": "S-1-5-21-101-202-303-1001", "username": "swci_012345abcdef",
        "profile_path": r"C:\Users\swci_012345abcdef",
        "token_profile_path": r"C:\Users\swci_012345abcdef",
        "final_state": {"profile_path_exists": True, "profile_key_exists": False,
                        "user_hive_loaded": False, "user_classes_hive_loaded": False},
        "files": [{"relative_path": "AppData/Local/probe.dat", "kind": "file",
                   "attributes": 32, "bytes": 0, "hresult": None}],
    }


class OwnerDiagnosticAdmissionTests(unittest.TestCase):
    def test_child_environment_preserves_worker_entry_contract(self):
        required = {"OS": "Windows_NT", "GITHUB_ACTIONS": "true",
                    "RUNNER_ENVIRONMENT": "github-hosted", "SWIRL_DISPOSABLE_INSTALL_TEST": "1",
                    "GITHUB_SHA": "1" * 40}
        with mock.patch.dict(diagnostic.os.environ,
                             dict(required, UNRELATED_ENV_MARKER="must-not-be-forwarded"), clear=True):
            child = diagnostic.child_environment()
        self.assertEqual(child, required)
        self.assertNotIn("UNRELATED_ENV_MARKER", child)

    def rejected(self, value):
        with self.assertRaises(diagnostic.ObservationError):
            diagnostic.validate_request(value)

    def test_accepts_bounded_synthetic_metadata(self):
        value = request_fixture()
        self.assertIs(diagnostic.validate_request(value), value)
        value["files"] = [dict(value["files"][0], relative_path=f"AppData/Local/{i}.dat") for i in range(32)]
        self.assertIs(diagnostic.validate_request(value), value)
        value["files"].append(dict(value["files"][0], relative_path="AppData/Local/extra.dat"))
        self.rejected(value)

    def test_requires_strict_frozen_decision_types(self):
        for key, values in {
            "schema": (True, 1.0, "1", 2),
            "cleanup_deadline_ms": (True, 30000.0, "30000", 29999, 30001),
            "cleanup_elapsed_ms": (True, None, "30000", float("nan"), float("inf"), -float("inf"), 29999.99),
            "new_account_created": (False, 1, "true", None),
            "profile_removed": (True, 0, "false", None),
            "path_verified": (False, 1, "true", None),
            "token_path_verified": (False, 1, "true", None),
        }.items():
            for invalid in values:
                with self.subTest(key=key, value=repr(invalid)):
                    value = request_fixture()
                    value[key] = invalid
                    self.rejected(value)

    def test_requires_all_four_residual_state_facts(self):
        for key, valid in request_fixture()["final_state"].items():
            for invalid in (not valid, int(valid), None, str(valid)):
                with self.subTest(key=key, value=invalid):
                    value = request_fixture()
                    value["final_state"][key] = invalid
                    self.rejected(value)

    def test_requires_fresh_scope_and_source_identity(self):
        for key, invalid in (("sid", "S-1-5-18"), ("username", "runneradmin"),
                             ("source_sha", "1" * 64), ("source_sha", "1" * 39),
                             ("token_profile_path", r"C:\Users\another")):
            with self.subTest(key=key):
                value = request_fixture()
                value[key] = invalid
                self.rejected(value)

    def test_rejects_nonordinary_file_records(self):
        for key, invalid in (("kind", "directory"), ("kind", "reparse-point-not-followed"),
                             ("hresult", 5), ("attributes", 16), ("attributes", 1024),
                             ("attributes", True), ("attributes", -1), ("attributes", "32"),
                             ("bytes", -1), ("bytes", True), ("bytes", 1.5)):
            with self.subTest(key=key, value=invalid):
                value = request_fixture()
                value["files"][0][key] = invalid
                self.rejected(value)
        for entries in ([], None, [request_fixture()["files"][0]] * 2):
            value = request_fixture()
            value["files"] = entries
            self.rejected(value)

    def test_rejects_relative_path_escapes(self):
        for relative in ("", ".", "../other", "/absolute", "a//b", "a/./b", "a/../b", "a\\b",
                         "a:b", "a\0b", "a/ ", "a/b.", "NUL", "a/CON.txt", "a/LPT1.txt"):
            with self.subTest(path=relative):
                value = request_fixture()
                value["files"][0]["relative_path"] = relative
                self.rejected(value)

    def test_accepts_only_ordinary_local_absolute_paths(self):
        for path in ("C:\\", r"C:\Users\fresh", r"D:\a\Swirl\build-evidence\receipt.json"):
            self.assertEqual(diagnostic.local_path_text(path), path)
        for path in (r"C:relative", r"\rooted", r"\\server\share\file", r"\\?\C:\file",
                     r"\\.\C:\file", "file:///C:/file", r"C:\file:stream", r"C:\file::$DATA",
                     r"C:\a\..\b", r"C:\a\NUL.txt", r"C:\file.", "C:\\file ",
                     r"C:\a?b", r"C:\a*b", "C:\\a\0b", r"C:\a/b", r"C:\a\\b"):
            with self.subTest(path=path), self.assertRaises(diagnostic.ObservationError):
                diagnostic.local_path_text(path)

    def test_profile_binding_also_rejects_namespaces_and_ads(self):
        for path in (r"\\server\users\swci_012345abcdef", r"\\?\C:\Users\swci_012345abcdef",
                     r"C:\users:stream\swci_012345abcdef"):
            value = request_fixture()
            value["profile_path"] = value["token_profile_path"] = path
            self.rejected(value)

    def test_output_scope_handles_real_runner_drive_split(self):
        profile = request_fixture()["profile_path"]
        self.assertFalse(diagnostic.within_profile(r"D:\a\Swirl\build-evidence", profile))
        self.assertFalse(diagnostic.within_profile(profile + "_other", profile))
        self.assertTrue(diagnostic.within_profile(profile.lower(), profile))
        self.assertTrue(diagnostic.within_profile(profile + r"\AppData", profile))

    def test_cli_refuses_before_filesystem_or_native_actions(self):
        output = io.StringIO()
        with mock.patch.dict(diagnostic.os.environ, {}, clear=True), \
             mock.patch.object(diagnostic, "plain_path", side_effect=AssertionError("No filesystem access expected")) as filesystem, \
             contextlib.redirect_stdout(output):
            result = diagnostic.main(["--request", "PRIVATE_MARKER", "--request-sha256", "1" * 64,
                                      "--powershell", "PRIVATE_MARKER"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue()), {"error": "OwnerDiagnosticHostedWindowsPython312Required",
                                                        "target_process_actions": False})
        filesystem.assert_not_called()
        self.assertNotIn("PRIVATE_MARKER", output.getvalue())

    def test_cli_argument_error_does_not_echo_supplied_values(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = diagnostic.main(["--unrecognized", "PRIVATE_MARKER"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue())["error"], "OwnerDiagnosticArgumentsRejected")
        self.assertNotIn("PRIVATE_MARKER", output.getvalue())


if __name__ == "__main__":
    unittest.main()
