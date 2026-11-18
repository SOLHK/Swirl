"""Rejected-axis evidence stays rejected; fabricated data tests only."""
from copy import deepcopy
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"platform"))
from b1_metric_followup import unadmitted_failure_evidence


def example():
    entry = {"sha256": "a"*64, "table_sha256": {"fvar": "b"*64}}
    row = {"id": "rejected", "status": "FAILED", "point_size": 1000.0,
           "requested_axes": {"HGHT": 0.828125, "WDTH": 0.0},
           "requested_defaults": {"HGHT": 0.828125, "WDTH": 0.0},
           "reported_axes": {"HGHT": 0.8281, "WDTH": 0.0},
           "error": "TEST_ONLY_FABRICATED_READBACK_NOT_NATIVE"}
    raw = {"source": deepcopy(entry), "status": "NATIVE_DIAGNOSTIC_FAILED",
           "observations": [{"id": "partial", "status": "COMPLETE"}, row],
           "completed_request_count": 1, "binary64_hex_by_json_path": {}}
    for field in ("requested_axes", "requested_defaults", "reported_axes"):
        for tag, value in row[field].items():
            raw["binary64_hex_by_json_path"][f"$.observations[1].{field}.{tag}"] = struct.pack(">d", value).hex()
    raw["binary64_hex_by_json_path"]["$.observations[1].point_size"] = struct.pack(">d", row["point_size"]).hex()
    return entry, raw


class FailureEvidenceTests(unittest.TestCase):
    def test_partial_rows_never_become_admitted_metrics(self):
        entry, raw = example()
        result = unadmitted_failure_evidence(raw, entry)
        self.assertEqual(result["partial_complete_rows_not_admitted"], 1)
        self.assertEqual(result["accepted_metric_records"], 0)
        self.assertFalse(result["native_instance_acceptance_claimed"])
        self.assertFalse(result["reverse_replay_complete"])
        self.assertEqual(result["failed_requests"][0]["requested_axes"]["HGHT"], 0.828125)
        self.assertEqual(result["failed_requests"][0]["reported_axes"]["HGHT"], 0.8281)
        self.assertEqual(result["metric_hypothesis_verdict"], "NOT_ESTABLISHED_BY_REJECTED_PROCESS")

    def test_decimal_alteration_and_missing_axis_bits_are_rejected(self):
        entry, raw = example()
        raw["observations"][1]["reported_axes"]["HGHT"] = 0.828125
        with self.assertRaisesRegex(ValueError, "failed_probe_binary64_mismatch"):
            unadmitted_failure_evidence(raw, entry)
        entry, raw = example()
        del raw["binary64_hex_by_json_path"]["$.observations[1].reported_axes.HGHT"]
        with self.assertRaisesRegex(ValueError, "failed_probe_axis_bits_missing"):
            unadmitted_failure_evidence(raw, entry)

    def test_wrong_source_cannot_supply_a_readback_failure(self):
        entry, raw = example()
        raw["source"]["sha256"] = "c"*64
        with self.assertRaisesRegex(ValueError, "failed_probe_source_identity_mismatch"):
            unadmitted_failure_evidence(raw, entry)

    def test_missing_bits_and_inconsistent_partial_counts_fail(self):
        entry, raw = example()
        raw["binary64_hex_by_json_path"] = {}
        with self.assertRaisesRegex(ValueError, "failed_probe_binary64_map_missing"):
            unadmitted_failure_evidence(raw, entry)
        entry, raw = example()
        raw["completed_request_count"] = 0
        with self.assertRaisesRegex(ValueError, "failed_probe_count_mismatch"):
            unadmitted_failure_evidence(raw, entry)


if __name__ == "__main__":
    unittest.main()
