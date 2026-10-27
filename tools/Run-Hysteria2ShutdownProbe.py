"""Run the original HY2 context, then repeat its unchanged HTTPS contract."""
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
    names = unittest.defaultTestLoader.getTestCaseNames(Hysteria2Official)
    if len(names) != 17 or any(not name.startswith(f"test_{index:02d}_")
                               for index, name in enumerate(names, 1)):
        raise RuntimeError("The complete original 17-method menu is required")
    phases = {name: {"executed_methods": 0, "failures": 0, "errors": 0, "skipped": 0,
                     "expected_failures": 0, "unexpected_successes": 0}
              for name in ("full_menu", "repeated_https", "framework")}
    boundary = None

    def phase(test):
        return getattr(getattr(test, "test_case", test), "probe_phase", "framework")

    class ObservedResult(unittest.TextTestResult):
        def startTest(self, test):
            nonlocal boundary
            label = phase(test)
            if label == "repeated_https" and boundary is None:
                boundary = len(Hysteria2Official.records)
            phases[label]["executed_methods"] += 1
            self.stream.write(f"\nPHASE={label}\n")
            super().startTest(test)

        def addFailure(self, test, error):
            phases[phase(test)]["failures"] += 1
            super().addFailure(test, error)

        def addError(self, test, error):
            phases[phase(test)]["errors"] += 1
            super().addError(test, error)

        def addSubTest(self, test, subtest, error):
            if error is not None:
                kind = "failures" if issubclass(error[0], test.failureException) else "errors"
                phases[phase(test)][kind] += 1
            super().addSubTest(test, subtest, error)

        def addSkip(self, test, reason):
            phases[phase(test)]["skipped"] += 1
            super().addSkip(test, reason)

        def addExpectedFailure(self, test, error):
            phases[phase(test)]["expected_failures"] += 1
            super().addExpectedFailure(test, error)

        def addUnexpectedSuccess(self, test):
            phases[phase(test)]["unexpected_successes"] += 1
            super().addUnexpectedSuccess(test)

    tests = []
    for label, methods in (("full_menu", names),
                           ("repeated_https", ["test_10_https_through_native_proxy"] * 25)):
        for method in methods:
            test = Hysteria2Official(method)
            test.probe_phase = label
            tests.append(test)
    suite = unittest.TestSuite(tests)
    with (output / "unittest.log").open("w", encoding="utf-8") as log:
        result = unittest.TextTestRunner(verbosity=2, stream=log, resultclass=ObservedResult).run(suite)
    records = Hysteria2Official.records
    full_records = records[:boundary] if boundary is not None else records
    repeated_records = records[boundary:] if boundary is not None else []

    def receipts_complete(values, count):
        return len(values) == count and all(
        record["result"].get("ok") is True
        and record["client_exit"] == 0
        and record.get("independent_origin_tls_close") == [{"orderly_tls_close": True}]
        for record in values
        )

    full_https = [record for record in full_records
                  if record.get("case", "").startswith("verified-https-through-native-proxy-")]
    complete = receipts_complete(repeated_records, 200)
    full_receipts = receipts_complete(full_https, 8)
    for label, expected in (("full_menu", 17), ("repeated_https", 25), ("framework", 0)):
        stats = phases[label]
        stats["expected_methods"] = expected
        stats["passed"] = (stats["executed_methods"] == expected and all(
            stats[key] == 0 for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes")))
    phases["full_menu"].update(executed_requests=len(full_records),
                               original_method_order=names, tls_origin_receipts_verified=full_receipts)
    phases["repeated_https"].update(expected_requests=200, executed_requests=len(repeated_records),
                                    tls_origin_receipts_verified=complete)
    report = {
        "schema": 2, "source_sha": source, "repetitions": 25,
        "expected_requests": 200, "executed_requests": len(repeated_records),
        "total_requests": len(records), "expected_methods": 42,
        "executed_methods": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "all_origin_receipts_verified": complete and full_receipts, "phases": phases,
        "client_sha256": hashlib.sha256(Path(os.environ["HY2_CLIENT"]).read_bytes()).hexdigest(),
        "server_sha256": hashlib.sha256(Path(os.environ["HY2_SERVER"]).read_bytes()).hexdigest(),
        "source_clean": not subprocess.check_output(["git", "status", "--porcelain"], text=True).strip(),
        "private_inputs": False,
    }
    report["network_contract_passed"] = (result.wasSuccessful() and result.testsRun == 42
                         and not result.skipped and not result.expectedFailures
                         and not result.unexpectedSuccesses and complete and full_receipts
                         and all(stats["passed"] for stats in phases.values()))
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
