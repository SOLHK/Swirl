"""Isolated-outbound acceptance boundaries; no provider credentials or URLs."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import threading
import unittest
from unittest import mock


spec = importlib.util.spec_from_file_location(
    "native_probe", Path(__file__).resolve().parents[1] / "Verify-PublicRustCore.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def fixture():
    return {"type": "shadowsocks", "host": "127.0.0.1", "port": 1,
            "password": "synthetic-password", "cipher": "aes-128-gcm"}


class ProbeConfiguration(unittest.TestCase):
    def test_explicit_proxy_has_one_immutable_route_without_fallback(self):
        outbound = fixture()
        config = verifier.probe_configuration(outbound=outbound)
        outbound["type"] = "direct"
        self.assertEqual(config["selected"], "anonymous-node")
        self.assertEqual(config["nodes"], [{"id": "anonymous-node", "outbound": fixture()}])
        self.assertNotIn("rules", config)
        self.assertNotIn("selectors", config)
        self.assertNotIn("dns", config)

    def test_direct_reject_unknown_and_config_shaped_values_never_spawn(self):
        values = [{"type": "direct"}, {"type": "reject"}, {"type": "socks5"},
                  {"type": []}, {"nodes": []}, [], "synthetic"]
        for value in values:
            with self.subTest(value=value), mock.patch.object(verifier.subprocess, "Popen") as spawn:
                with self.assertRaises(ValueError):
                    verifier.probe("unused", "example.com", outbound=value)
                spawn.assert_not_called()

    def test_rules_groups_and_combined_dns_never_become_an_isolated_probe(self):
        for extra in ("rules", "selectors", "nodes", "selected", "dns"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                verifier.probe_configuration(outbound={**fixture(), extra: []})
        with self.assertRaises(ValueError):
            verifier.probe_configuration(encrypted_dns=True, outbound=fixture())

    def test_configuration_limit_accounts_for_json_escaping_and_envelope(self):
        with self.assertRaises(ValueError):
            verifier.probe_configuration(outbound={**fixture(), "password": "\x00" * 700})
        config = verifier.probe_configuration(outbound=fixture())
        self.assertLessEqual(len(json.dumps({"op": "start", "config": config}).encode()) + 1, 4096)

    def test_public_cli_configuration_and_authenticated_dns_remain_explicit(self):
        direct = verifier.probe_configuration()
        self.assertEqual(direct["selected"], "public-direct")
        self.assertEqual(direct["nodes"][0]["outbound"], {"type": "direct"})
        doh = verifier.probe_configuration(encrypted_dns=True)
        self.assertFalse(doh["dns"]["use_system_hosts"])
        self.assertEqual(doh["dns"]["tls_servers"][0]["tls"]["server_name"], "cloudflare-dns.com")

    @unittest.skipUnless(os.environ.get("SWIRL_RUST_HARNESS"), "Rust harness required")
    def test_rejecting_independent_ss_peer_is_a_failed_native_probe(self):
        reached = threading.Event()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(5)

            def reject():
                try:
                    with listener.accept()[0] as stream:
                        stream.settimeout(5)
                        if stream.recv(32):
                            reached.set()
                except OSError:
                    pass

            thread = threading.Thread(target=reject, daemon=True)
            thread.start()
            result = verifier.probe(os.environ["SWIRL_RUST_HARNESS"], "example.com",
                                    outbound={**fixture(), "port": listener.getsockname()[1]})
            thread.join(timeout=5)
        self.assertTrue(reached.is_set())
        self.assertFalse(result["success"])
        self.assertEqual(result["route"], "explicit-native-outbound")
        self.assertFalse(result.get("certificate_verified", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
