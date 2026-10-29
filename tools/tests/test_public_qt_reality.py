"""Reject incomplete or misleading Windows Qt/public evidence without networking."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("public_qt_reality", ROOT / "tools/Verify-PublicQtReality.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def successful_report():
    checks = []
    for node, frontend, host, port, method in sorted(gate.expected_cases()):
        checks.append({"node": node, "frontend": frontend, "host": host, "port": port,
                       "method": method, "http_status": 200, "certificate_verified": port == 443,
                       "tls_version": "TLSv1.3" if port == 443 else "",
                       "proxy_host": "127.0.0.1", "proxy_port": 10800,
                       "stage": "complete", "closed": True,
                       "expected_body_verified": port == 80, "success": True})
    return {"schema": 1, **{name: True for name in gate.STATES}, "checks": checks}


class PublicQtEvidenceTests(unittest.TestCase):
    def test_complete_cross_product_and_only_authored_fields_are_retained(self):
        value = successful_report()
        value["untrusted_diagnostic"] = "synthetic-secret"
        value["checks"][0]["uuid"] = "synthetic-secret"
        safe = gate.validate_qt_report(value)
        self.assertEqual(len(safe["checks"]), 8)
        self.assertNotIn("synthetic-secret", str(safe))
        self.assertEqual({row["node"] for row in safe["checks"]}, {"A", "B"})
        self.assertEqual({row["frontend"] for row in safe["checks"]}, {"http-connect", "socks5"})

    def test_every_missing_product_state_and_truthy_non_boolean_is_rejected(self):
        for name in gate.STATES:
            for invalid in (None, False, 1, "true", []):
                value = successful_report()
                value[name] = invalid
                with self.subTest(state=name, invalid=invalid), self.assertRaises(gate.public.ProbeFailure):
                    gate.validate_qt_report(value)

    def test_missing_proxy_identity_or_close_cannot_pass(self):
        for field, invalid in (("proxy_host", "direct"), ("proxy_port", 0), ("proxy_port", True),
                               ("stage", "connect"), ("closed", False)):
            value = successful_report()
            value["checks"][0][field] = invalid
            with self.subTest(field=field), self.assertRaises(gate.public.ProbeFailure):
                gate.validate_qt_report(value)

    def test_partial_failed_case_is_preserved_without_untrusted_text(self):
        value = successful_report()
        value["checks"] = value["checks"][:1]
        value["checks"][0].update(success=False, stage="tls-handshake", socket_error=13,
                                   tls_error_count=1, elapsed_ms=419, closed=True,
                                   error_string="synthetic-secret", uuid="synthetic-secret")
        safe = gate.safe_qt_progress(value)
        self.assertEqual(len(safe["checks"]), 1)
        self.assertEqual(safe["checks"][0]["socket_error"], 13)
        self.assertEqual(safe["checks"][0]["stage"], "tls-handshake")
        self.assertFalse(safe["checks"][0]["success"])
        self.assertNotIn("synthetic-secret", str(safe))
        with self.assertRaises(gate.public.ProbeFailure):
            gate.validate_qt_report(safe)

    def test_bounded_tls_predicates_are_diagnostics_and_cannot_turn_failure_into_success(self):
        value = successful_report()
        row = next(row for row in value["checks"] if row["port"] == 443)
        row.update(success=False, stage="tls-handshake", tls_encrypted=True,
                   peer_certificate_present=True, handshake_error_count=0,
                   session_protocol=11, alpn_hex="", alpn_status=2,
                   active_backend="schannel", client_alpn_supported=True)
        safe = gate.safe_qt_progress(value)
        observed = next(row for row in safe["checks"] if row["port"] == 443)
        for field in ("tls_encrypted", "peer_certificate_present", "handshake_error_count",
                      "session_protocol", "alpn_hex", "alpn_status", "active_backend",
                      "client_alpn_supported"):
            self.assertEqual(observed[field], row[field])
        self.assertFalse(observed["success"])
        with self.assertRaises(gate.public.ProbeFailure):
            gate.validate_qt_report(safe)
        for field, invalid in (("tls_encrypted", 1), ("peer_certificate_present", "true"),
                               ("handshake_error_count", 257), ("session_protocol", 65),
                               ("alpn_hex", "secret"), ("alpn_hex", "aa" * 256),
                               ("alpn_status", 3), ("active_backend", "secret\nvalue"),
                               ("active_backend", "a" * 65), ("client_alpn_supported", 1)):
            modified = copy.deepcopy(value)
            next(item for item in modified["checks"] if item["port"] == 443)[field] = invalid
            observed = next(item for item in gate.safe_qt_progress(modified)["checks"] if item["port"] == 443)
            with self.subTest(field=field, invalid=invalid):
                self.assertNotIn(field, observed)

    def test_nonzero_child_and_timeout_keep_partial_progress(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                value = successful_report()
                value["checks"] = value["checks"][:1]
                value["checks"][0].update(success=False, stage="connect")
                child = root / "report.json"
                child.write_text(json.dumps(value), encoding="utf-8")
                log = root / "qt-raw.log"
                log.write_text("FAIL! public product request", encoding="utf-8")
                report = {}
                outcome = (subprocess.TimeoutExpired("qt-test", 180) if timeout else
                           subprocess.CompletedProcess(["qt-test"], 1, "", ""))
                with patch.object(gate.subprocess, "run", side_effect=outcome if timeout else None,
                                  return_value=None if timeout else outcome), self.assertRaises(
                                      subprocess.TimeoutExpired if timeout else gate.public.ProbeFailure):
                    gate.run_qt_test("qt-test", root / "fixture.json", child, log, root, report)
                self.assertEqual(len(report["checks"]), 1)
                self.assertFalse(report["checks"][0]["success"])
                self.assertEqual(report["qt_exit_code"], None if timeout else 1)
                self.assertTrue((root / "qt-product-progress.json").is_file())

    def test_missing_duplicate_extra_and_wrong_route_or_frontend_cannot_pass(self):
        variants = []
        missing = successful_report()
        missing["checks"].pop()
        variants.append(missing)
        duplicate = successful_report()
        duplicate["checks"][-1] = copy.deepcopy(duplicate["checks"][0])
        variants.append(duplicate)
        extra = successful_report()
        extra["checks"].append(copy.deepcopy(extra["checks"][0]))
        variants.append(extra)
        for field, invalid in (("node", "DIRECT"), ("frontend", "system-proxy"),
                               ("host", "unlisted.invalid"), ("port", 444),
                               ("method", "POST"), ("port", True), ("node", {})):
            value = successful_report()
            value["checks"][0][field] = invalid
            variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(gate.public.ProbeFailure):
                gate.validate_qt_report(value)

    def test_tls_without_certificate_or_tls13_and_http_without_body_fail(self):
        for port, edits in ((443, (("certificate_verified", False), ("certificate_verified", 1),
                                   ("tls_version", "TLSv1.2"), ("http_status", 400))),
                            (80, (("expected_body_verified", False), ("http_status", 302),
                                  ("http_status", "200"), ("success", False)))):
            for field, invalid in edits:
                value = successful_report()
                row = next(row for row in value["checks"] if row["port"] == port)
                row[field] = invalid
                with self.subTest(port=port, field=field), self.assertRaises(gate.public.ProbeFailure):
                    gate.validate_qt_report(value)

    def test_successful_child_cannot_replace_independent_authenticated_public_exit(self):
        self.assertEqual(len(gate.validate_qt_report(successful_report())["checks"]), 8)
        observed = {"vless_accepted_sessions": 4, "reality_authenticated_sessions": 4,
                    "client_finished_verified_sessions": 4, "vision_direct_upload_commands": 2,
                    "vision_direct_download_commands": 2, "vision_padding_events": 4,
                    "vision_unpadding_events": 4, "camouflage_application_bytes": 0}

        class Peer:
            identity = "A"
            connections = 2

            def observations(self):
                return dict(observed)

            def public_connections(self, target, address):
                return self.connections

        peer = Peer()
        destinations = [(target, "8.8.8.8") for target in gate.public.TARGETS]
        self.assertEqual(gate.verify_peer(peer, destinations)["node"], "A")
        for field, invalid in (("vless_accepted_sessions", 3), ("vless_accepted_sessions", 5),
                               ("reality_authenticated_sessions", 0), ("client_finished_verified_sessions", 0),
                               ("vision_direct_upload_commands", 1), ("vision_direct_download_commands", 1),
                               ("vision_padding_events", 0), ("vision_unpadding_events", 0),
                               ("camouflage_application_bytes", 1)):
            old = observed[field]
            observed[field] = invalid
            with self.subTest(field=field), patch.object(gate.time, "monotonic", side_effect=(0, 4)), \
                    self.assertRaises(gate.public.ProbeFailure):
                gate.verify_peer(peer, destinations)
            observed[field] = old
        peer.connections = 0
        with patch.object(gate.time, "monotonic", side_effect=(0, 4)), self.assertRaises(gate.public.ProbeFailure):
            gate.verify_peer(peer, destinations)

    def test_actual_xray_socket_log_must_match_pinned_remote_endpoint(self):
        target = gate.public.TARGETS[0]
        with tempfile.TemporaryDirectory() as folder:
            peer = object.__new__(gate.QtPublicPeer)
            peer.log_path = Path(folder) / "xray.log"
            peer.log_path.write_text(
                "connection opened to tcp:8.8.8.8:80, local endpoint 127.0.0.1:1, remote endpoint 8.8.8.8:80\n"
                "connection opened to tcp:8.8.8.8:80, local endpoint 127.0.0.1:2, remote endpoint 1.1.1.1:80\n"
                "connection opened to tcp:8.8.8.8:443, local endpoint 127.0.0.1:3, remote endpoint 8.8.8.8:443\n",
                encoding="utf-8")
            self.assertEqual(peer.public_connections(target, "8.8.8.8"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
