#!/usr/bin/env python3
"""Generate original standard glyf/gvar TTC geometry for native API tests."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from test_rebuild import write_fixture

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    write_fixture(args.output,faces=3)
