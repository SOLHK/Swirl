#!/usr/bin/env python3
"""Adversarial evidence-contract tests; these are synthetic, not Windows acceptance."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("acceptance", ROOT / "tools/Verify-NativeTunAcceptance.py")
ACCEPTANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCEPTANCE)
SOURCE = "0123456789abcdef0123456789abcdef01234567"


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.plan = dict(schema=1, source_sha=SOURCE, source_dirty=False, mode="Baseline",
                         collector_sha256="1" * 64, created_utc="2026-11-01T00:00:00+00:00",
                         physical_windows_11_acceptance=False,
                         environment={"os": {"windows_11": True}, "machine": {"class": "Unknown"}, "elevated": False},
                         load=dict(duration_seconds=10, interval_seconds=5, max_rss_mib=512, max_handles=4096))
        self.result = dict(schema=1, source_sha=SOURCE, mode="Baseline", status="recorded",
                           started_utc="2026-11-01T00:00:01+00:00", finished_utc="2026-11-01T00:00:12+00:00",
                           physical_windows_11_acceptance=False,
                           command=dict(collector_sha256="1" * 64, exit_code=0), artifacts=[])
        snapshot = self.snapshot()
        self.write("network-before.json", snapshot)
        self.write("network-after.json", snapshot)

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding="utf-8")

    def snapshot(self):
        categories = {"adapters": ("count", "hardware"),
                      "routes": ("count", "ipv4", "ipv6", "default_routes", "split_defaults"),
                      "dns": ("interfaces", "configured"),
                      "firewall": ("owned_active_rule_count", "enabled_outbound_blocks", "port53_filters")}
        snapshot = {name: dict(status="observed", data={key: 0 for key in keys}) for name, keys in categories.items()}
        for name, item in snapshot.items():
            if name == "firewall":
                item["data"].update(service="Running", profiles=[], rules_fingerprint="0" * 64, filters_fingerprint="0" * 64)
            else:
                item["data"]["fingerprint"] = "0" * 64
        return snapshot

    def freeze(self):
        self.write("plan.json", self.plan)
        self.result["plan_sha256"] = ACCEPTANCE.sha256(self.root / "plan.json")
        self.result["artifacts"] = [dict(path=path.name, sha256=ACCEPTANCE.sha256(path))
                                    for path in sorted(self.root.iterdir()) if path.name not in ("plan.json", "result.json")]
        self.write("result.json", self.result)

    def verify(self):
        self.freeze()
        return ACCEPTANCE.verify(self.root, SOURCE)

    def sample(self):
        self.plan["mode"] = self.result["mode"] = "Sample"
        self.plan["observation_target"] = dict(process_id=1234, process_start_utc="2026-10-31T23:59:00+00:00")
        self.result["command"]["process_id"] = 1234
        samples = [dict(elapsed_seconds=elapsed, rss_bytes=1024 * 1024, private_bytes=2 * 1024 * 1024,
                        handles=30, threads=3, cpu_seconds=elapsed / 10) for elapsed in (0.01, 5, 10)]
        self.write_samples(samples)
        return samples

    def write_samples(self, samples, process_id=1234, process_start_utc="2026-10-31T23:59:00+00:00"):
        self.write("resource-samples.json", dict(samples=samples, process_id=process_id, process_start_utc=process_start_utc))

    def driver(self):
        self.plan["mode"] = self.result["mode"] = "ScopedDriverSmoke"
        self.plan["environment"].update(elevated=True, architecture="X64")
        self.plan["driver"] = dict(sha256=ACCEPTANCE.DRIVER_HASHES["X64"])
        self.result["command"].update(executable_sha256="2" * 64,
            arguments=["--disposable-network", "--wintun", "<explicit locally hashed Wintun DLL>"])
        smoke = {key: True for key in ("ok", "dns_a", "dns_aaaa", "tcp_ipv4", "tcp_ipv6", "udp_ipv4", "udp_ipv6",
                    "tcp_reply_after_client_fin", "owned_network_state_restored", "adapter_removed", "default_routes_unchanged")}
        smoke.update(evidence="Windows Wintun scoped loopback smoke", source_sha=SOURCE,
                     physical_dns_modified=False, firewall_modified=False, windows_11_application_acceptance=False,
                     driver_version="0.14.1", driver_sha256=ACCEPTANCE.DRIVER_HASHES["X64"],
                     wintun_received_packets=20, wintun_sent_packets=20)
        return smoke

    def write_driver(self, smoke, conflicts=None):
        lines = ["Wintun smoke: recovery report " + json.dumps(dict(restored=6, conflicts=conflicts or [])),
                 "Wintun smoke: exact network configuration verification " + json.dumps(dict(
                     adapters_equal=True, all_routes_equal=True, adapters_before=8, adapters_after=8,
                     routes_before=26, routes_after=26)),
                 "Wintun smoke: PASS owned Wintun adapter removed",
                 "Wintun smoke: PASS default/split-default routes unchanged", json.dumps(smoke)]
        (self.root / "scoped-driver.log").write_text("\n".join(lines), encoding="utf-8")

    def test_baseline_never_grants_physical_or_release_approval(self):
        actual = self.verify()
        self.assertFalse(actual["release_approved"])
        self.assertFalse(actual["physical_windows_11_acceptance"])
        self.assertEqual(actual["scope"], "inventory")

    def test_missing_firewall_visibility_is_retained(self):
        snapshot = self.snapshot()
        snapshot["firewall"] = dict(status="unavailable", error_type="CimException")
        self.write("network-before.json", snapshot)
        actual = self.verify()
        self.assertEqual(actual["inventory_coverage"]["network-before.json"]["firewall"], "unavailable")

    def test_an_asserted_physical_pass_is_rejected(self):
        self.result["physical_windows_11_acceptance"] = True
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "cannot certify"):
            self.verify()

    def test_boolean_is_not_a_schema_number(self):
        self.plan["schema"] = True
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "Unsupported evidence schema"):
            self.verify()

    def test_observation_without_inventory_data_is_not_a_valid_baseline(self):
        snapshot = self.snapshot()
        snapshot["routes"]["data"] = {}
        self.write("network-before.json", snapshot)
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "inventory count"):
            self.verify()

    def test_changed_frozen_thresholds_are_rejected(self):
        self.sample()
        self.freeze()
        self.plan["load"]["max_rss_mib"] *= 2
        self.write("plan.json", self.plan)
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "Frozen plan changed"):
            ACCEPTANCE.verify(self.root)

    def test_changed_original_log_is_rejected(self):
        self.sample()
        self.freeze()
        self.write("resource-samples.json", dict(samples=[]))
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "Artifact changed"):
            ACCEPTANCE.verify(self.root)

    def test_another_source_cannot_be_reused(self):
        self.freeze()
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "another source"):
            ACCEPTANCE.verify(self.root, "f" * 40)

    def test_path_traversal_cannot_supply_an_artifact(self):
        self.freeze()
        self.result["artifacts"].append(dict(path="../outside.json", sha256="0" * 64))
        self.write("result.json", self.result)
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "artifact path"):
            ACCEPTANCE.verify(self.root)

    def test_observed_resources_are_distinct_from_workload_acceptance(self):
        self.sample()
        actual = self.verify()
        self.assertTrue(actual["resource_thresholds_met"])
        self.assertFalse(actual["workload_verified"])
        self.assertFalse(actual["sustained_network_acceptance"])

    def test_short_run_cannot_pass_planned_duration(self):
        samples = self.sample()[:-1]
        self.write_samples(samples)
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "planned duration"):
            self.verify()

    def test_memory_peak_not_only_final_sample_is_checked(self):
        samples = self.sample()
        samples[1]["rss_bytes"] = 513 * 1024 * 1024
        self.write_samples(samples)
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "RSS threshold"):
            self.verify()

    def test_handle_peak_not_only_final_sample_is_checked(self):
        samples = self.sample()
        samples[1]["handles"] = 4097
        self.write_samples(samples)
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "handle threshold"):
            self.verify()

    def test_missing_final_driver_summary_is_not_success(self):
        self.driver()
        (self.root / "scoped-driver.log").write_text("Wintun smoke: PASS intermediate step\n", encoding="utf-8")
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "final driver summary"):
            self.verify()

    def test_complete_driver_evidence_retains_scoped_classification(self):
        self.write_driver(self.driver())
        actual = self.verify()
        self.assertTrue(actual["driver_assertions_met"])
        for key in ("full_tunnel_acceptance", "dns_leak_test", "kill_switch_test", "physical_windows_11_acceptance"):
            self.assertFalse(actual[key])

    def test_driver_source_mismatch_cannot_be_relabelled(self):
        smoke = self.driver()
        smoke["source_sha"] = "f" * 40
        self.write_driver(smoke)
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "another source"):
            self.verify()

    def test_recovery_conflict_cannot_be_hidden_by_success_summary(self):
        self.write_driver(self.driver(), conflicts=[0])
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "six-resource recovery"):
            self.verify()

    def test_removed_readback_cannot_be_hidden_by_success_summary(self):
        self.write_driver(self.driver())
        path = self.root / "scoped-driver.log"
        path.write_text("\n".join(line for line in path.read_text().splitlines() if "exact network" not in line))
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "exact original network readback"):
            self.verify()

    def test_relabelled_nonofficial_driver_is_rejected(self):
        smoke = self.driver()
        smoke["driver_sha256"] = self.plan["driver"]["sha256"] = "0" * 64
        self.write_driver(smoke)
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "pinned official"):
            self.verify()

    def test_failed_exit_code_is_not_success(self):
        self.result["command"]["exit_code"] = 1
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "scenario failed"):
            self.verify()

    def test_sampling_gaps_and_clock_reversal_are_rejected(self):
        original = self.sample()
        for elapsed in ((0.01, 12, 13), (0.01, 5, 4)):
            samples = copy.deepcopy(original)
            for item, value in zip(samples, elapsed):
                item["elapsed_seconds"] = value
            self.write_samples(samples)
            with self.assertRaises(ACCEPTANCE.EvidenceError):
                self.verify()

    def test_samples_from_another_process_are_rejected(self):
        samples = self.sample()
        self.write_samples(samples, process_id=5678)
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "another process"):
            self.verify()

    def test_reused_pid_with_another_start_time_is_rejected(self):
        samples = self.sample()
        self.write_samples(samples, process_start_utc="2026-10-31T23:58:00+00:00")
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "another process"):
            self.verify()

    def test_omitted_frozen_process_identity_is_rejected(self):
        self.sample()
        del self.plan["observation_target"]
        with self.assertRaisesRegex(ACCEPTANCE.EvidenceError, "frozen process identity"):
            self.verify()


if __name__ == "__main__":
    unittest.main(verbosity=2)
