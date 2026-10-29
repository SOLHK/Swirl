"""Test private-outline-free triage and unchanged strict failure accounting."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from triage_source_projection import summarize, LIMIT

class TriageProjectionTests(unittest.TestCase):
    def test_failure_counts_and_order(self):
        report = {"by_glyph": {"7": {"passed": 1, "failed": 33, "max_error": 223.9},
                               "19177": {"passed": 21, "failed": 13, "max_error": 19.5},
                               "3": {"passed": 34, "failed": 0}}}
        result = summarize(report)
        self.assertEqual((result["sample_count"], result["failed_samples"]), (102, 46))
        self.assertEqual([r["gid"] for r in result["failed_gids"]], [7, 19177])
        self.assertEqual(result["error_budget_funits"], 1 / 32)
        self.assertEqual(result["status"], "ORIGINAL_GEOMETRY_NOT_ACCEPTED")

    def test_no_failure_not_complete_font(self):
        result = summarize({"by_glyph": {"1": {"passed": 34, "failed": 0}}})
        self.assertEqual(result["status"], "SAMPLED_GEOMETRY_PASS")
        self.assertNotIn("full_font_accepted", result)

    def test_invalid_or_missing_records_rejected(self):
        with self.assertRaises(ValueError):
            summarize({})
        with self.assertRaises(ValueError):
            summarize({"by_glyph": {"1": {"passed": -1, "failed": 2}}})

if __name__ == "__main__":
    unittest.main()
