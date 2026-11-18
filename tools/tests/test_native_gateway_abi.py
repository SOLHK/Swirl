"""Independent Gateway ABI boundaries; never changes the host network.

The source-identical library must be supplied in SWIRL_BUILT_LIBRARY. These
checks prove version negotiation and rejection, not Windows packet forwarding.
"""
import copy
import json
import unittest
import uuid

import test_native_lan_abi as lan


def gateway_config():
    return {
        "tun": {
            "driver_path": "C:\\Swirl\\wintun.dll",
            "adapter_guid": "70000000-0000-4000-8000-000000000001",
            "adapter_name": "Swirl Native TUN",
        },
        "lan": {
            "lan": {"index": 11, "guid": "70000000-0000-4000-8000-000000000002"},
            "subnet": "192.168.77.0/24", "gateway": "192.168.77.1",
            "allowed_sources": ["192.168.77.0/24"],
            "dedicated_lan_confirmed": True, "dhcp": False,
        },
    }


class NativeGatewayAbi(unittest.TestCase):
    setUpClass = classmethod(lan.NativeLanAbi.setUpClass.__func__)
    command_bytes = lan.NativeLanAbi.command_bytes

    def command(self, op, **fields):
        request = {"native_gateway_schema": 1, "request_id": str(uuid.uuid4()), "op": op}
        request.update(fields)
        result = self.command_bytes(json.dumps(request).encode())
        self.assertEqual(result["native_gateway_schema"], 1)
        if result["ok"]:
            self.assertEqual(result["request_id"], request["request_id"])
        return result

    def test_validation_is_pure_and_does_not_claim_acceptance(self):
        response = self.command("gateway_validate", config=gateway_config())
        self.assertIs(response["ok"], True, response)
        self.assertIs(response["validated"], True)
        self.assertIs(response["network_preflight_required"], True)
        self.assertEqual(response["dns_ipv4"], "198.18.0.2")
        capability = response["capabilities"]
        self.assertEqual(capability["schema"], 1)
        for name in ["ipv4_only", "prepare_activate", "controller_requires_helper",
                     "dhcp_socket_attestation"]:
            self.assertIs(capability[name], True)
        for name in ["ipv6_forwarding", "gui_activation_available",
                     "automatic_boot_recovery", "real_windows_11_acceptance"]:
            self.assertIs(capability[name], False)
        self.assertNotIn("handle", response)
        self.assertNotIn("state", response)

    def test_dll_cannot_modify_gateway_even_with_plausible_identity(self):
        identity = {"handle": "1", "engine_epoch": "1"}
        calls = [
            ("gateway_prepare", dict(identity, config=gateway_config())),
            ("gateway_activate", dict(identity, preparation_id="a" * 32)),
            ("gateway_stop", identity), ("gateway_recover", {}),
        ]
        for op, fields in calls:
            with self.subTest(op=op):
                response = self.command(op, **fields)
                self.assertIs(response["ok"], False)
                self.assertEqual(response["error"], "GatewayHelperRequired")

    def test_unconfirmed_public_or_unbounded_lan_is_rejected(self):
        baseline = gateway_config()
        bad = [
            ("dedicated_lan_confirmed", False), ("subnet", "0.0.0.0/0"),
            ("subnet", "8.8.8.0/24"), ("gateway", "192.168.77.0"),
            ("gateway", "192.168.77.255"), ("allowed_sources", []),
            ("allowed_sources", ["0.0.0.0/0"]),
        ]
        for key, value in bad:
            with self.subTest(key=key):
                config = copy.deepcopy(baseline)
                config["lan"][key] = value
                self.assertIs(self.command("gateway_validate", config=config)["ok"], False)
        for value in [0, 1000000]:
            config = copy.deepcopy(baseline)
            config["max_tcp_per_client"] = value
            self.assertIs(self.command("gateway_validate", config=config)["ok"], False)

    def test_schema_and_unknown_fields_cannot_smuggle_commands_or_secrets(self):
        response = self.command("gateway_validate", native_gateway_schema=2, config=gateway_config())
        self.assertIs(response["ok"], False)
        self.assertEqual(response["error"], "GatewayUnsupportedSchema")
        response = self.command("gateway_validate", config=gateway_config(), shell_command=lan.FIXTURE_SECRET)
        self.assertIs(response["ok"], False)
        self.assertEqual(response["error"], "GatewayCommandInvalid")
        response = self.command("gateway_validate", config=gateway_config(), request_id=lan.FIXTURE_SECRET)
        self.assertIs(response["ok"], False)
        self.assertNotIn(lan.FIXTURE_SECRET, json.dumps(response))


if __name__ == "__main__":
    unittest.main(verbosity=2)
