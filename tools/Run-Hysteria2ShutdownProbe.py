"""Repeat the unchanged HTTPS contract with independent origin close receipts."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
from test_hysteria2_official import Hysteria2Official, HTTP


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    os.environ["HY2_EVIDENCE"] = str(output / "official-peer.json")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    with HTTP.tls_close_condition:
        HTTP.tls_close_receipts = []
        HTTP.tls_close_errors = []
    Hysteria2Official.records = []
    suite = unittest.TestSuite(
        Hysteria2Official("test_10_https_through_native_proxy") for _ in range(25)
    )
    with (output / "unittest.log").open("w", encoding="utf-8") as log:
        result = unittest.TextTestRunner(verbosity=2, stream=log).run(suite)
    records = Hysteria2Official.records
    complete = (len(records) == 200 and all(
        record["result"].get("ok") is True
        and record["client_exit"] == 0
        and record.get("independent_origin_tls_close") == [{"orderly_tls_close": True}]
        for record in records
    ))
    report = {
        "schema": 1, "source_sha": source, "repetitions": 25,
        "expected_requests": 200, "executed_requests": len(records),
        "executed_methods": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "all_origin_receipts_verified": complete,
        "client_sha256": hashlib.sha256(Path(os.environ["HY2_CLIENT"]).read_bytes()).hexdigest(),
        "server_sha256": hashlib.sha256(Path(os.environ["HY2_SERVER"]).read_bytes()).hexdigest(),
        "source_clean": not subprocess.check_output(["git", "status", "--porcelain"], text=True).strip(),
        "private_inputs": False,
    }
    report["network_contract_passed"] = (result.wasSuccessful() and result.testsRun == 25
                         and not result.skipped and not result.expectedFailures
                         and not result.unexpectedSuccesses and complete)
    expected_sha = os.environ.get("SWIRL_SOURCE_SHA", source)
    report["source_matches_expected"] = source == expected_sha
    report["success"] = (report["network_contract_passed"] and report["source_matches_expected"]
                         and (report["source_clean"] or os.environ.get("GITHUB_ACTIONS") != "true"))
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    raise SystemExit(run(parser.parse_args().output))
