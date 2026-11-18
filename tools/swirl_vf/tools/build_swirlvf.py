#!/usr/bin/env python3
"""Build a private SwirlVF.ttc candidate at the fixed 1/32 FUnit contract.

This delegates to the existing reconstruction engine. Its historical 1 FUnit
experiment defaults are not product acceptance. A successful sampled build
still needs independent native macOS, Windows 11, Qt and distribution review.
"""
import argparse
from pathlib import Path
import re
import sys

import rebuild

PRECISION = 1 / 32
# Charge cubic approximation to the same total outline bound; reserve half of
# that bound for control-point/encoding discrepancy. No threshold is increased.
CUBIC_APPROXIMATION = PRECISION / 2


def run(source, executable, destination, report_path, *, expected_source_sha256,
        batch_size=64, checkpoint_dir=None):
    rebuild.check(type(expected_source_sha256) is str and
                  re.fullmatch(r'[0-9a-f]{64}', expected_source_sha256) is not None,
                  'a complete expected source SHA-256 is required')
    rebuild.check(rebuild.sha256(source) == expected_source_sha256,
                  'source SHA-256 differs from the specified original')
    rebuild.check(type(batch_size) is int and 1 <= batch_size <= 1024,
                  'batch size outside 1..1024')
    return rebuild.run(source, executable, destination, report_path,
                       batch_size=batch_size, outline_limit=PRECISION,
                       metric_limit=PRECISION, cubic_error=CUBIC_APPROXIMATION,
                       checkpoint_dir=checkpoint_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--oracle', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--checkpoint-dir', type=Path)
    args = parser.parse_args()
    try:
        run(args.source, args.oracle, args.output, args.report,
            expected_source_sha256=args.expected_source_sha256,
            batch_size=args.batch_size, checkpoint_dir=args.checkpoint_dir)
    except (rebuild.ReconstructionError, OSError, ValueError) as error:
        print(f'BLOCKED: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
