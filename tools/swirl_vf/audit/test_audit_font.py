"""Focused regressions for loss of malformed source metadata during auditing."""
import importlib.util
from pathlib import Path
import struct
import unittest

MODULE_PATH = Path(__file__).parents[1] / "tools" / "audit_font.py"
spec = importlib.util.spec_from_file_location("audit_font", MODULE_PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def avar_bytes(pairs):
    return struct.pack(">5H", 1, 0, 0, 1, len(pairs)) + b"".join(
        struct.pack(">hh", a, b) for a, b in pairs)


class AuditRegressions(unittest.TestCase):
    def test_preserves_conflicting_duplicate_records(self):
        pairs = [(-16384, -16384), (-16384, -16000), (0, 0), (16384, 16384)]
        result = audit.raw_avar(avar_bytes(pairs), ["wght"])
        records = result["axes"][0]["records"]
        self.assertEqual([(r["from_f2dot14"], r["to_f2dot14"]) for r in records], pairs)
        self.assertFalse(result["standard_record_conformance_pass"])

    def test_order_violation_is_not_silently_sorted(self):
        pairs = [(-16384, -16384), (0, 0), (-40, 0), (16384, 16384)]
        result = audit.raw_avar(avar_bytes(pairs), ["wght"])
        self.assertEqual(result["axes"][0]["records"][2]["from_f2dot14"], -40)
        self.assertIn("from_coordinates_out_of_order", [r["kind"] for r in result["axes"][0]["violations"]])

    def test_standard_identity_map_passes(self):
        result = audit.raw_avar(avar_bytes([(-16384, -16384), (0, 0), (16384, 16384)]), ["HGHT"])
        self.assertTrue(result["standard_record_conformance_pass"])

    def test_truncated_map_fails(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            audit.raw_avar(avar_bytes([(-16384, -16384), (0, 0), (16384, 16384)])[:-1], ["wght"])

    def test_metric_long_advance_reuse_preserves_bearing(self):
        data = struct.pack(">Hhh", 900, -15, 23)
        self.assertEqual(audit.numeric_metrics(data, 2, 1), [(900, -15), (900, 23)])

    def test_hvgl_bad_index_fails_before_large_unpack(self):
        header = struct.pack("<HH5I", 3, 1, 0, 0xFFFFFFFF, 24, 10, 0)
        result = audit.inspect_hvgl(header, 0)
        self.assertIn("part_index_out_of_bounds", [r["kind"] for r in result["violations"]])


if __name__ == "__main__":
    unittest.main()
