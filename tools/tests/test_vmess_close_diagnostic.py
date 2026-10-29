"""Receipt classification must never turn timer-driven teardown into success."""
import unittest

from diagnose_vmess_close import pattern_hash, strict_result


class VmessCloseReceiptTests(unittest.TestCase):
    def receipt(self):
        digest = pattern_hash(257)
        return {"downloaded": 257, "sha256": digest, "close": "clean",
                "post_eof_receipt_verified": True,
                "target_receipts_before_client_cleanup": [{
                    "received": 257, "sha256": digest, "upload_eof": True,
                    "failure": None}]}

    def test_complete_response_after_upload_eof_is_accepted(self):
        self.assertTrue(strict_result(self.receipt(), 257)["strict_target_half_close"])

    def test_echo_and_cleanup_eof_without_post_eof_receipt_are_rejected(self):
        result = self.receipt()
        result["post_eof_receipt_verified"] = False
        self.assertFalse(strict_result(result, 257)["strict_target_half_close"])
        self.assertTrue(result["bytes_match"])

    def test_receipt_cannot_cover_truncation_target_error_or_missing_eof(self):
        for field, value in (("received", 256), ("sha256", "0" * 64),
                             ("upload_eof", False), ("failure", "TimeoutError")):
            with self.subTest(field=field):
                result = self.receipt()
                result["target_receipts_before_client_cleanup"][0][field] = value
                self.assertFalse(strict_result(result, 257)["strict_target_half_close"])

    def test_late_receipt_does_not_cover_unclean_or_corrupt_download(self):
        for field, value in (("close", "unexpected_eof"), ("downloaded", 256),
                             ("sha256", "0" * 64)):
            with self.subTest(field=field):
                result = self.receipt()
                result[field] = value
                self.assertFalse(strict_result(result, 257)["strict_target_half_close"])


if __name__ == "__main__":
    unittest.main()
