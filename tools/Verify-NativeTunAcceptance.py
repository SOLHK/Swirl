#!/usr/bin/env python3
"""Validate collector provenance and compute scoped results without granting release approval.

Hashes detect accidental changes; they are not a signature or independent attestation.
No network traffic or operating-system configuration is changed by this verifier.
"""
import argparse
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path


class EvidenceError(ValueError):
    pass


DRIVER_HASHES = {
    "X64": "e5da8447dc2c320edc0fc52fa01885c103de8c118481f683643cacc3220dafce",
    "X86": "d694fa46ab4cfebcb2632d094c7aa97278eef2f8052438621766d863ae98a931",
    "Arm64": "f7ba89005544be9d85231a9e0d5f23b2d15b3311667e2dad0debd344918a3f80",
    "Arm": "daad267411ecdc70a0535e274d2c3e9da3d0084bdac7662cb8424dd4a031b4d9",
}


def require(value, message):
    if not value:
        raise EvidenceError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.utcoffset() is not None, "Timestamp must include a UTC offset")
    return parsed


def verify(directory, expected_source=None):
    root = Path(directory).resolve()
    plan = read_json(root / "plan.json")
    result = read_json(root / "result.json")
    require(isinstance(plan, dict) and isinstance(result, dict), "Evidence must contain JSON objects")
    require(type(plan.get("schema")) is int and plan["schema"] == 1 and
            type(result.get("schema")) is int and result["schema"] == 1, "Unsupported evidence schema")
    require(plan.get("physical_windows_11_acceptance") is False and
            result.get("physical_windows_11_acceptance") is False,
            "This collector cannot certify physical Windows 11 acceptance")
    source = plan.get("source_sha", "")
    require(re.fullmatch(r"[0-9a-f]{40}", source), "Missing exact source SHA")
    require(result.get("source_sha") == source, "Result source differs from frozen plan")
    if expected_source:
        require(source == expected_source, "Evidence belongs to another source")
    require(result.get("plan_sha256") == sha256(root / "plan.json"), "Frozen plan changed")
    require(type(plan.get("source_dirty")) is bool, "Working tree state was not recorded")
    command = result.get("command", {})
    require(isinstance(command, dict), "Command observation must be an object")
    require(re.fullmatch(r"[0-9a-f]{64}", plan.get("collector_sha256", "")) and
            command.get("collector_sha256") == plan["collector_sha256"], "Collector identity mismatch")
    require(timestamp(plan["created_utc"]) <= timestamp(result["started_utc"]) <=
            timestamp(result["finished_utc"]), "Plan was not frozen before the recorded run")
    mode = plan.get("mode")
    require(mode in ("Baseline", "Sample", "ScopedDriverSmoke") and result.get("mode") == mode,
            "Unknown or mismatched scenario")
    allowed = {"network-before.json", "network-after.json", "resource-samples.json", "scoped-driver.log"}
    artifacts = {}
    require(isinstance(result.get("artifacts"), list), "Artifact inventory must be an array")
    for artifact in result["artifacts"]:
        require(isinstance(artifact, dict), "Artifact observation must be an object")
        name = artifact.get("path")
        require(name in allowed and name not in artifacts, "Invalid or duplicate artifact path")
        path = root / name
        require(path.resolve().parent == root and not path.is_symlink(), "Artifact escaped evidence directory")
        require(artifact.get("sha256") == sha256(path), f"Artifact changed: {name}")
        artifacts[name] = path
    require({"network-before.json", "network-after.json"} <= artifacts.keys(), "Missing before/after inventory")
    coverage = {}
    snapshots = {}
    for name in ("network-before.json", "network-after.json"):
        snapshot = read_json(artifacts[name])
        require(isinstance(snapshot, dict), "Inventory must be an object")
        require(set(snapshot) == {"adapters", "routes", "dns", "firewall"}, "Incomplete inventory schema")
        require(all(isinstance(item, dict) and item.get("status") in ("observed", "unavailable") for item in snapshot.values()),
                "Inventory observation is missing status")
        for category, item in snapshot.items():
            if item["status"] == "unavailable":
                require(isinstance(item.get("error_type"), str) and item["error_type"], "Missing inventory failure type")
                continue
            data = item.get("data")
            require(isinstance(data, dict), "Observed inventory is missing data")
            counts = {"adapters": ("count", "hardware"),
                      "routes": ("count", "ipv4", "ipv6", "default_routes", "split_defaults"),
                      "dns": ("interfaces", "configured"),
                      "firewall": ("owned_active_rule_count", "enabled_outbound_blocks", "port53_filters")}[category]
            require(all(type(data.get(key)) is int and data[key] >= 0 for key in counts), "Missing inventory count")
            hashes = ("rules_fingerprint", "filters_fingerprint") if category == "firewall" else ("fingerprint",)
            require(all(re.fullmatch(r"[0-9a-f]{64}", data.get(key, "")) for key in hashes), "Missing inventory fingerprint")
            if category == "firewall":
                require(isinstance(data.get("service"), str) and isinstance(data.get("profiles"), list),
                        "Missing firewall enforcement observations")
        coverage[name] = {key: item["status"] for key, item in snapshot.items()}
        snapshots[name] = snapshot
    environment = plan["environment"]
    require(isinstance(environment, dict) and isinstance(environment.get("os"), dict) and
            isinstance(environment.get("machine"), dict), "Missing environment objects")
    require(type(environment["os"]["windows_11"]) is bool, "OS class is missing")
    require(environment["machine"]["class"] in ("Unknown", "Physical", "Virtual"), "Machine class is missing")
    output = {"schema": 1, "source_sha": source, "mode": mode, "source_dirty": plan["source_dirty"],
              "scope": "inventory", "inventory_coverage": coverage,
              "observed_schema_unchanged": {
                  name: (snapshots["network-before.json"][name].get("data") ==
                         snapshots["network-after.json"][name].get("data"))
                  if coverage["network-before.json"][name] == coverage["network-after.json"][name] == "observed"
                  else None for name in ("adapters", "routes", "dns", "firewall")},
              "physical_windows_11_acceptance": False, "release_approved": False}
    require(result.get("status") == "recorded" and type(command.get("exit_code")) is int and command["exit_code"] == 0,
            "Collector or scenario failed; preserve its failure evidence")
    if mode == "Sample":
        require("resource-samples.json" in artifacts, "Missing resource samples")
        observations = read_json(artifacts["resource-samples.json"])
        target = plan.get("observation_target")
        require(isinstance(target, dict) and type(target.get("process_id")) is int and
                target["process_id"] > 0, "Missing frozen process identity")
        require(target["process_id"] == command.get("process_id") == observations.get("process_id") and
                target.get("process_start_utc") == observations.get("process_start_utc"),
                "Resource observations belong to another process")
        require(timestamp(target["process_start_utc"]) <= timestamp(plan["created_utc"]),
                "Observed process did not exist when the plan was frozen")
        samples = observations["samples"]
        load = plan["load"]
        for key in ("duration_seconds", "interval_seconds", "max_rss_mib", "max_handles"):
            require(number(load.get(key)) and load[key] > 0, "Invalid pre-run resource threshold")
        require(len(samples) >= 2, "Resource run has insufficient samples")
        last_time = last_cpu = -1
        for sample in samples:
            for key in ("elapsed_seconds", "rss_bytes", "private_bytes", "handles", "cpu_seconds", "threads"):
                require(number(sample.get(key)) and sample[key] >= 0, "Invalid resource sample")
            require(sample["elapsed_seconds"] > last_time and sample["cpu_seconds"] >= last_cpu,
                    "Resource samples are not monotonic")
            if last_time >= 0:
                require(sample["elapsed_seconds"] - last_time <= load["interval_seconds"] * 2 + 1,
                        "Resource sampling missed its planned cadence")
            last_time, last_cpu = sample["elapsed_seconds"], sample["cpu_seconds"]
        require(samples[0]["elapsed_seconds"] <= load["interval_seconds"], "Resource sampling started late")
        require(samples[-1]["elapsed_seconds"] >= load["duration_seconds"], "Resource run ended before its planned duration")
        require((timestamp(result["finished_utc"]) - timestamp(result["started_utc"])).total_seconds() >=
                samples[-1]["elapsed_seconds"], "Sample duration exceeds recorded run duration")
        rss = max(item["rss_bytes"] for item in samples)
        handles = max(item["handles"] for item in samples)
        require(rss <= load["max_rss_mib"] * 1024 * 1024, "Planned RSS threshold exceeded")
        require(handles <= load["max_handles"], "Planned handle threshold exceeded")
        output.update(scope="resource_observation_only", samples=len(samples), max_rss_bytes=rss,
                      max_handles=handles, resource_thresholds_met=True,
                      workload_verified=False, sustained_network_acceptance=False)
    elif mode == "ScopedDriverSmoke":
        require("scoped-driver.log" in artifacts, "Missing original driver log")
        require(environment.get("elevated") is True, "Driver run was not elevated")
        require(plan.get("source_dirty") is False, "Driver acceptance requires clean identified source")
        require(re.fullmatch(r"[0-9a-f]{64}", command.get("executable_sha256", "")), "Missing smoke binary hash")
        require(command.get("arguments") == ["--disposable-network", "--wintun", "<explicit locally hashed Wintun DLL>"],
                "Driver invocation did not follow the scoped smoke contract")
        text = artifacts["scoped-driver.log"].read_text(encoding="utf-8-sig")
        summaries = []
        for line in text.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("evidence") == "Windows Wintun scoped loopback smoke":
                summaries.append(item)
        require(len(summaries) == 1, "Expected exactly one original final driver summary")
        smoke = summaries[0]
        require(smoke.get("source_sha") == source, "Smoke binary was compiled from another source")
        for key in ("ok", "dns_a", "dns_aaaa", "tcp_ipv4", "tcp_ipv6", "udp_ipv4", "udp_ipv6",
                    "tcp_reply_after_client_fin", "owned_network_state_restored", "adapter_removed", "default_routes_unchanged"):
            require(smoke.get(key) is True, f"Driver assertion missing: {key}")
        for key in ("physical_dns_modified", "firewall_modified", "windows_11_application_acceptance"):
            require(smoke.get(key) is False, "Scoped smoke was misclassified as physical capture")
        require(smoke.get("driver_version") == "0.14.1" and smoke.get("driver_sha256") ==
                (plan.get("driver") or {}).get("sha256"), "Driver identity differs from the frozen plan")
        require(smoke.get("driver_sha256") == DRIVER_HASHES.get(environment.get("architecture")),
                "Driver is not the pinned official binary for this architecture")
        for key in ("wintun_received_packets", "wintun_sent_packets"):
            require(type(smoke.get(key)) is int and smoke[key] > 0, "Driver did not transfer packets")
        require("PASS owned Wintun adapter removed" in text and
                "PASS default/split-default routes unchanged" in text, "Missing original cleanup markers")
        readbacks = []
        recoveries = []
        for line in text.splitlines():
            for marker, entries in (("Wintun smoke: exact network configuration verification ", readbacks),
                                    ("Wintun smoke: recovery report ", recoveries)):
                if marker in line:
                    entries.append(json.loads(line.split(marker, 1)[1]))
        require(len(readbacks) == 1 and readbacks[0].get("adapters_equal") is True and
                readbacks[0].get("all_routes_equal") is True, "Missing exact original network readback")
        for prefix in ("adapters", "routes"):
            require(type(readbacks[0].get(prefix + "_before")) is int and
                    readbacks[0][prefix + "_before"] > 0 and
                    readbacks[0][prefix + "_before"] == readbacks[0].get(prefix + "_after"),
                    "Original network resource count changed")
        require(len(recoveries) == 1 and recoveries[0].get("restored") == 6 and
                recoveries[0].get("conflicts") == [], "Owned six-resource recovery did not complete")
        output.update(scope="windows_scoped_loopback_driver", driver_assertions_met=True,
                      full_tunnel_acceptance=False, dns_leak_test=False, kill_switch_test=False)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expect-source")
    args = parser.parse_args()
    try:
        output = verify(args.directory, args.expect_source)
    except (EvidenceError, OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Invalid or failed acceptance evidence: {error}\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
