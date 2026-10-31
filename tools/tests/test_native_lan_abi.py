"""Independent ctypes checks for the compiled Native LAN control ABI.

Requires SWIRL_BUILT_LIBRARY pointing at the source-identical DLL/shared library.
Only the existing loopback listener is started. LAN admission is validated but
never bypassed for test convenience; these tests do not claim LAN device or
Windows firewall acceptance. No network configuration or privileges are needed.
"""
import ctypes
import json
import os
from pathlib import Path
import socket
import unittest
import uuid


CAPACITY = 1024 * 1024
FIXTURE_SECRET = "NATIVE_LAN_SYNTHETIC_PASSWORD_123"


def lan_config():
    return {
        "listen_ip": "192.168.73.1",
        "http_port": 17890,
        "socks_port": 17891,
        "udp_port_start": 17900,
        "udp_port_end": 17915,
        "allowed_cidrs": ["192.168.73.0/24"],
        "auth": {"username": "synthetic-lan", "password": FIXTURE_SECRET},
        "max_connections": 64,
        "max_connections_per_client": 8,
        "auth_failures_per_minute": 5,
        "idle_timeout_secs": 300,
        "host_addresses": ["192.168.73.1"],
    }


class NativeLanAbi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(os.environ["SWIRL_BUILT_LIBRARY"]).resolve(strict=True)
        cls.library = ctypes.CDLL(str(path))
        cls.library.swirl_core_abi_version.argtypes = []
        cls.library.swirl_core_abi_version.restype = ctypes.c_uint32
        cls.library.swirl_core_build_info.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        cls.library.swirl_core_build_info.restype = ctypes.c_ssize_t
        cls.library.swirl_core_command.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t
        ]
        cls.library.swirl_core_command.restype = ctypes.c_ssize_t

    def command_bytes(self, raw):
        source = ctypes.create_string_buffer(raw)
        output = ctypes.create_string_buffer(CAPACITY)
        ctypes.memset(output, 0xA5, CAPACITY)
        count = self.library.swirl_core_command(source, len(raw), output, CAPACITY)
        self.assertGreater(count, 0)
        self.assertLess(count, CAPACITY)
        response = output.raw[:count]
        self.assertNotIn(FIXTURE_SECRET.encode(), response)
        self.assertEqual(output.raw[count:], b"\xa5" * (CAPACITY - count))
        return json.loads(response)

    def command(self, op, **fields):
        request = {"control_schema": 2, "request_id": str(uuid.uuid4()), "op": op}
        request.update(fields)
        result = self.command_bytes(json.dumps(request).encode())
        if result["ok"]:
            self.assertEqual(result["request_id"], request["request_id"])
        return result

    def test_capability_negotiation_preserves_abi(self):
        self.assertEqual(self.library.swirl_core_abi_version(), 1)
        output = ctypes.create_string_buffer(4096)
        count = self.library.swirl_core_build_info(output, len(output))
        self.assertGreater(count, 0)
        self.assertLess(count, len(output))
        info = json.loads(output.raw[:count])
        self.assertEqual(info["abi_version"], 1)
        self.assertEqual(info["control_schemas"], [1, 2])
        optional = info["capabilities"]["optional"]
        self.assertIs(optional["lan_proxy"], True)
        self.assertIs(type(optional["lan_proxy_control_schema"]), int)
        self.assertEqual(optional["lan_proxy_control_schema"], 1)
        self.assertIs(optional["lan_proxy_ipv6_listener"], False)
        self.assertIs(optional["gateway"], False)
        self.assertNotIn(FIXTURE_SECRET.encode(), output.raw[:count])

    def test_offline_validation_reports_only_validation(self):
        result = self.command("lan_validate", config=lan_config())
        self.assertIs(result["ok"], True, result)
        self.assertEqual(result["lan_control_schema"], 1)
        self.assertIs(result["validation"]["valid"], True)
        self.assertIs(result["validation"]["network_preflight_required"], True)
        self.assertNotIn("lan", result)
        self.assertNotIn("handle", result)
        self.assertNotIn("auth", result)

    def test_unsafe_bindings_allowlists_and_limits_fail_closed(self):
        bad_values = [
            ("listen_ip", "0.0.0.0"), ("listen_ip", "::"),
            ("listen_ip", "127.0.0.1"), ("listen_ip", "8.8.8.8"),
            ("listen_ip", "169.254.1.1"), ("listen_ip", "fd00::1"),
            ("allowed_cidrs", []), ("allowed_cidrs", ["0.0.0.0/0"]),
            ("allowed_cidrs", ["192.168.0.0/15"]),
            ("http_port", 0), ("socks_port", 65536),
            ("udp_port_end", 17899), ("max_connections", 0),
            ("max_connections_per_client", 1000000),
            ("auth_failures_per_minute", 0), ("idle_timeout_secs", 0),
            ("host_addresses", []),
            ("auth", {"username": "fixture", "password": "short"}),
            ("unknown", FIXTURE_SECRET),
        ]
        for field, value in bad_values:
            with self.subTest(field=field, value="invalid"):
                config = lan_config()
                config[field] = value
                result = self.command("lan_validate", config=config)
                self.assertIs(result["ok"], False)

    def test_malformed_duplicate_and_unknown_commands_do_not_echo_input(self):
        malformed = [
            b"{", b"[]", b"null", b"\xff",
            b'{"control_schema":2,"control_schema":1,"op":"lan_stop"}',
            json.dumps({"control_schema": 2, "op": "lan_unknown",
                        "password": FIXTURE_SECRET}).encode(),
            json.dumps({"control_schema": 2, "op": "lan_validate",
                        "request_id": FIXTURE_SECRET, "config": lan_config()}).encode(),
        ]
        for raw in malformed:
            self.assertIs(self.command_bytes(raw)["ok"], False)
        result = self.command("lan_validate", control_schema=3, config=lan_config())
        self.assertIs(result["ok"], False)
        self.assertEqual(result["code"], "UnsupportedControlSchema")

    def test_capacity_rejections_leave_output_untouched(self):
        raw = b" " * (CAPACITY + 1)
        source = ctypes.create_string_buffer(raw)
        output = ctypes.create_string_buffer(CAPACITY)
        ctypes.memset(output, 0xA5, CAPACITY)
        for length, capacity in [(len(raw), CAPACITY), (0, CAPACITY), (1, 16)]:
            count = self.library.swirl_core_command(source, length, output, capacity)
            self.assertEqual(count, -1)
            self.assertEqual(output.raw, b"\xa5" * CAPACITY)

    def test_lan_control_never_restarts_or_widens_primary_listener(self):
        node_id = str(uuid.uuid4())
        candidate = {
            "schema": 2, "listen": "127.0.0.1:0",
            "nodes": [{"id": node_id, "outbound": {
                "type": "socks5", "host": "127.0.0.1", "port": 9, "auth": None
            }}],
            "policy": {"schema": 2, "mode": "global", "default_policy": {
                "id": "policy:default", "target": {"kind": "node", "id": node_id}
            }},
        }
        started = self.command("start_v2", store_id=str(uuid.uuid4()),
                               saved_revision="1", candidate=candidate)
        self.assertIs(started["ok"], True, started)
        identity = {"handle": started["handle"], "engine_epoch": started["engine_epoch"]}
        try:
            host, port = started["address"].rsplit(":", 1)
            self.assertEqual(host, "127.0.0.1")
            for op in ["lan_start", "lan_stop", "lan_status"]:
                fields = dict(identity, engine_epoch="0")
                if op == "lan_start":
                    fields["config"] = lan_config()
                rejected = self.command(op, **fields)
                self.assertIs(rejected["ok"], False)
                self.assertEqual(rejected["code"], "EngineEpochMismatch")
            invalid_config = lan_config()
            invalid_config["listen_ip"] = "0.0.0.0"
            rejected = self.command("lan_start", config=invalid_config, **identity)
            self.assertIs(rejected["ok"], False)
            for op in ["lan_status", "lan_stop", "lan_status"]:
                status = self.command(op, **identity)
                self.assertIs(status["ok"], True, status)
                self.assertEqual(status["engine_epoch"], started["engine_epoch"])
                self.assertIs(status["lan"]["running"], False)
                self.assertEqual(status["lan"]["active_connections"], 0)
                self.assertNotIn("auth", status["lan"])
                with socket.create_connection((host, int(port)), timeout=3) as client:
                    self.assertEqual(client.getpeername(), (host, int(port)))
        finally:
            stopped = self.command_bytes(json.dumps({
                "op": "stop", "handle": int(started["handle"])
            }).encode())
            self.assertIs(stopped["ok"], True, stopped)
        stale = self.command("lan_stop", **identity)
        self.assertIs(stale["ok"], False)
        self.assertEqual(stale["code"], "UnknownV2Handle")


if __name__ == "__main__":
    unittest.main(verbosity=2)
