"""Offline guards for the explicit Windows Qt lifecycle evidence contract."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reality_runtime as gate


def complete(mode):
    result = {"schema": 1, "mode": mode, "provider_connection": False,
              **dict.fromkeys(gate.QT_LIFECYCLE_STATES, True), "checks": []}
    phases = ("direct-control", "reject") if mode == "reject" else (mode,)
    hosts = (("denied.product.invalid", "unmatched.product.invalid") if mode == "reject" else
             ("tls.product.invalid" if mode == "tls12" else
              "stream.product.invalid" if mode == "cancel" else "a.product.invalid",))
    for frontend in ("http-connect", "socks5"):
        for phase in phases:
            for host in hosts:
                accepted = phase not in ("reject", "authentication-failure")
                row = {"frontend": frontend, "node": "A", "phase": phase, "target": host,
                       "target_port": 12345, "proxy_host": "127.0.0.1", "proxy_port": 10800,
                       "stage": "complete", "frontend_response_valid": True, "tunnel_accepted": accepted,
                       "expected_result_observed": True, "closed": True, "socket_error": -1,
                       "tls_error_count": 0, "elapsed_ms": 5,
                       "proxy_status": (200 if accepted else 502) if frontend == "http-connect" else (0 if accepted else 5)}
                if mode == "cancel":
                    row.update(echo_verified=True, cancelled_after_echo=True, echo_bytes=len(gate.QT_CANCEL_PAYLOAD))
                elif accepted:
                    row.update(http_status=200, expected_body_verified=True)
                if mode == "tls12":
                    row.update(certificate_verified=True, tls_version="TLSv1.2")
                result["checks"].append(row)
    return result


class QtLifecycleEvidenceTests(unittest.TestCase):
    def test_explicit_profile_selection_preserves_original_and_adds_exactly_four(self):
        for fingerprint, vision in (("rustls", False), ("rustls", True), ("chrome", False)):
            self.assertEqual(gate.qt_test_names(fingerprint, vision), (gate.QT_PRODUCT_TEST,))
        names = gate.qt_test_names("chrome", True)
        self.assertEqual(names, (gate.QT_PRODUCT_TEST, *gate.QT_LIFECYCLE_TESTS))
        self.assertEqual(len(set(names)), 5)
        for name in names:
            self.assertTrue(callable(getattr(gate.RealityQtInterop, name)))

    def test_all_complete_modes_are_accepted_with_authored_fields_only(self):
        for mode in gate.QT_LIFECYCLE_MODES:
            value = complete(mode)
            value["uuid"] = "synthetic-private-field"
            value["checks"][0]["error_string"] = "synthetic-private-field"
            with self.subTest(mode=mode):
                safe = gate.validate_qt_lifecycle_report(value, mode, 12345)
                self.assertNotIn("synthetic-private-field", json.dumps(safe))
                self.assertEqual(len(safe["checks"]), 8 if mode == "reject" else 2)

    def test_missing_product_state_or_truthy_non_boolean_fails(self):
        for state in gate.QT_LIFECYCLE_STATES:
            for bad in (None, False, 1, "true"):
                value = complete("tls12")
                value[state] = bad
                with self.subTest(state=state, value=bad), self.assertRaises(AssertionError):
                    gate.validate_qt_lifecycle_report(value, "tls12", 12345)

    def test_missing_duplicate_entrance_and_unproven_proxy_are_rejected(self):
        for mode in gate.QT_LIFECYCLE_MODES:
            value = complete(mode)
            broken = [value["checks"][:-1], [value["checks"][0]] * len(value["checks"])]
            for checks in broken:
                with self.subTest(mode=mode), self.assertRaises(AssertionError):
                    gate.validate_qt_lifecycle_report({**value, "checks": checks}, mode, 12345)
        for field, bad in (("proxy_host", "DIRECT"), ("proxy_port", True), ("target_port", 4),
                           ("closed", False), ("expected_result_observed", False), ("stage", "http-response"),
                           ("elapsed_ms", "secret"), ("frontend_response_valid", False)):
            value = complete("tls12")
            value["checks"][0][field] = bad
            with self.subTest(field=field), self.assertRaises(AssertionError):
                gate.validate_qt_lifecycle_report(value, "tls12", 12345)

    def test_certificate_tls12_and_actual_echo_are_mandatory(self):
        for mode, edits in (("tls12", (("certificate_verified", False), ("tls_version", "TLSv1.3"),
                                      ("tls_error_count", 1), ("http_status", 502))),
                            ("cancel", (("echo_verified", False), ("cancelled_after_echo", False),
                                        ("echo_bytes", 0)))):
            for field, bad in edits:
                value = complete(mode)
                value["checks"][0][field] = bad
                with self.subTest(mode=mode, field=field), self.assertRaises(AssertionError):
                    gate.validate_qt_lifecycle_report(value, mode, 12345)

    def test_reject_needs_direct_positive_control_and_exact_reject_reply(self):
        for index, field, bad in ((0, "http_status", 0), (0, "expected_body_verified", False),
                                  (2, "tunnel_accepted", True), (2, "proxy_status", 200)):
            value = complete("reject")
            value["checks"][index][field] = bad
            with self.subTest(index=index, field=field), self.assertRaises(AssertionError):
                gate.validate_qt_lifecycle_report(value, "reject", 12345)

    def test_invalid_uuid_may_fail_after_frontend_ack_but_never_after_http_success(self):
        value = complete("authentication-failure")
        for row in value["checks"]:
            row["tunnel_accepted"] = True
            row["proxy_status"] = 200 if row["frontend"] == "http-connect" else 0
        gate.validate_qt_lifecycle_report(value, "authentication-failure", 12345)
        value["checks"][0]["http_status"] = 200
        with self.assertRaises(AssertionError):
            gate.validate_qt_lifecycle_report(value, "authentication-failure", 12345)

    def test_failed_or_timed_out_child_preserves_partial_typed_evidence(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                value = complete("tls12")
                value["checks"] = value["checks"][:1]
                value["checks"][0].update(stage="tls-handshake", expected_result_observed=False,
                                          socket_error=13, error_string="synthetic-private-field")
                (root / "tls12-report.json").write_text(json.dumps(value), encoding="utf-8")
                case = gate.RealityQtInterop(gate.QT_PRODUCT_TEST)
                case.folder = SimpleNamespace(name=folder)
                case.case = root / "evidence"
                case.case.mkdir()
                case.https = SimpleNamespace(port=12345)
                case.ca_pem = "synthetic-ca"
                peer = SimpleNamespace(node=lambda: {"uuid": "synthetic-private-field"})
                outcome = subprocess.TimeoutExpired("qt", 100) if timeout else subprocess.CompletedProcess(["qt"], 1, "", "")
                with patch.dict(gate.os.environ, {"SWIRL_RUST_QT_TESTS": "fixture-qt"}), patch.object(
                        gate.subprocess, "run", side_effect=outcome if timeout else None,
                        return_value=None if timeout else outcome), self.assertRaises(
                            subprocess.TimeoutExpired if timeout else AssertionError):
                    case.lifecycle(peer, peer, "tls12")
                actual = json.loads((case.case / "tls12-qt.json").read_text())
                self.assertEqual(actual["checks"][0]["socket_error"], 13)
                self.assertEqual(actual["checks"][0]["stage"], "tls-handshake")
                self.assertNotIn("synthetic-private-field", json.dumps(actual))
                execution = json.loads((case.case / "tls12-execution.json").read_text())
                self.assertEqual(execution["timed_out"], timeout)
                self.assertEqual(execution["qt_exit_code"], None if timeout else 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
