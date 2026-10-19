#!/usr/bin/env python3
"""Compare exact production binary64 JSON encoding with Darwin's legacy path.

Only self-authored numerical/Unicode records are used, never font data.
Extract the implementation from coretext_extract.swift instead of testing a
separate encoder. Keep both outputs and require exact bits after roundtrip.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import shutil
import struct
import subprocess
import tempfile


def bits(value):
    return struct.pack('>d', float(value)).hex()


def harness(source):
    text = source.read_text()
    start = text.index('private enum OracleJSON: Encodable {')
    end = text.index('\nfunc emit(', start)
    return '''import Foundation
import CoreFoundation
enum OracleError: Error { case invalid(String) }
''' + text[start:end] + '''
let input = FileHandle.standardInput.readDataToEndOfFile()
let values = try JSONDecoder().decode([Double].self, from: input)
let record: [String:Any] = ["numbers":values,
    "bits":values.map { String(format:"%016llx", $0.bitPattern) },
    "nested":[["boolean":true,"zero":Int(0),"one":Int(1),"nil":NSNull(),
               "unicode":"中国\\n引号\\\"", "large_unsigned":UInt64.max,
               "negative_integer":Int64.min]],
    "number_count":values.count]
FileHandle.standardOutput.write(try encodedJSON(record) + Data([10]))
FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject:record, options:[.sortedKeys]) + Data([10]))
for bad in [Double.nan, Double.infinity, -Double.infinity] {
    do { _ = try encodedJSON(["value":bad]); exit(5) }
    catch { /* required rejection */ }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('coretext_extract.swift'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    # Include the exact public axis-coordinate request that stopped run
    # 39263795788, boundary-representable numbers, and independent random data.
    values = [600.5859375, 368.22259521484375, 975.7080078125, 0., -0.,
              1., math.nextafter(1., 0.), math.nextafter(1., math.inf),
              129.9, 0.1, 1e-300, 1e300, float(2**53-1), -float(2**53-1)]
    rng = random.Random(20261019)
    values += [rng.randint(-16000, 16000)/16384*401+501 for _ in range(512)]
    values += [rng.uniform(-2000, 2000) for _ in range(512)]
    compiler = shutil.which('swiftc')
    if compiler is None:
        raise RuntimeError('swiftc unavailable: native JSON transport not tested')
    with tempfile.TemporaryDirectory(prefix='swirl-json-transport-') as tmp:
        swift, binary = Path(tmp)/'encoder.swift', Path(tmp)/'encoder'
        swift.write_text(harness(args.source))
        built = subprocess.run([compiler, str(swift), '-o', str(binary)], capture_output=True, text=True, timeout=90)
        if built.returncode:
            raise RuntimeError(built.stderr)
        run = subprocess.run([str(binary)], input=json.dumps(values, allow_nan=False), capture_output=True, text=True, timeout=15)
        if run.returncode:
            raise RuntimeError(f'encoder exited {run.returncode}: {run.stderr}')
        rows = [json.loads(line, parse_int=lambda s: -0.0 if s == '-0' else int(s)) for line in run.stdout.splitlines()]
    expected = [bits(v) for v in values]
    report = {'platform':platform.platform(), 'font_data_used':False,
              'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'number_count':len(values), 'required_error_bits':0,
              'nonfinite_values_rejected':True, 'encoders':{}}
    for label, row in zip(('production_JSONEncoder', 'legacy_JSONSerialization'), rows):
        errors = []
        for index, (value, encoded) in enumerate(zip(values, row['numbers'])):
            if bits(encoded) != expected[index]:
                errors.append({'index':index, 'input':value, 'returned':encoded,
                               'input_bits':expected[index], 'returned_bits':bits(encoded)})
        count_ok = len(row['numbers']) == len(values)
        input_bits_ok = row['bits'] == expected
        nested = row['nested'][0]
        types_ok = (type(nested['boolean']) is bool and type(nested['one']) is int
                    and type(nested['zero']) is int and nested['nil'] is None
                    and nested['large_unsigned'] == 2**64-1
                    and nested['negative_integer'] == -2**63
                    and nested['unicode'] == '中国\n引号"')
        report['encoders'][label] = {'roundtrip_mismatches':len(errors), 'first_mismatches':errors[:12],
                                    'input_decoded_bits_match':input_bits_ok, 'types_preserved':types_ok,
                                    'passed':not errors and count_ok and input_bits_ok and types_ok}
    if len(rows) != 2:
        raise AssertionError('native harness did not return both independent encoding paths')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report['encoders']['production_JSONEncoder']['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
