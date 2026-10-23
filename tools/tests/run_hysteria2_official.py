"""Require all original 17 official HY2 methods, with no skipped methods."""
import json
import os
from pathlib import Path
import sys
import unittest

from test_hysteria2_official import Hysteria2Official


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Hysteria2Official)
    if suite.countTestCases() != 17:
        raise RuntimeError("OriginalHysteria2MethodCountChanged")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {
        "expected_methods": 17,
        "executed_methods": result.testsRun,
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "skips": [test.id() for test, _ in result.skipped],
        "all_original_methods_passed": result.wasSuccessful()
            and result.testsRun == 17 and not result.skipped,
        "constrained_stack": os.environ.get("HY2_CONSTRAINED_STACK") == "1",
    }
    destination = os.environ.get("HY2_EVIDENCE")
    if destination:
        path = Path(destination)
        report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        report["suite"] = summary
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["all_original_methods_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
