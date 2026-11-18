#!/usr/bin/env python3
"""Exercise the production Swift CFF2 empty-path proof with hostile inputs.

These are authored table fragments, not fonts. Only the actual native oracle
may decide whether a real font loads. A nonempty CharString never earns an
empty-path exemption, even if its only instruction is vsindex.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import shutil
import struct
import subprocess

SWIFT = r'''
do {
    let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    let table = TableSlice(offset: 0, length: data.count, digest: "authored-fragment")
    let empty = try cff2ProvesEmpty(table, Int(CommandLine.arguments[2])!,
                                   Int(CommandLine.arguments[3])!, Bytes(data: data))
    try emit(["result": empty ? "EMPTY_PROVED" : "NOT_PROVED"])
} catch {
    try? emit(["result": "REJECTED", "error": String(describing: error)])
}
'''


def table(strings=(b'', b'\x8b\x0f'), *, off_size=1):
    # Header + two-byte TopDICT + empty GlobalSubrINDEX = 11 bytes.
    prefix = b'\x02\x00\x05\x00\x02\x96\x11' + bytes(4)
    offsets = [1]
    for string in strings:
        offsets.append(offsets[-1] + len(string))
    return prefix + struct.pack('>IB', len(strings), off_size) + b''.join(
        offset.to_bytes(off_size, 'big') for offset in offsets) + b''.join(strings)


def cases():
    original = table()
    yield 'zero_length_charstring', original, 0, 2, 'EMPTY_PROVED'
    yield 'vsindex_only_is_not_a_proof', original, 1, 2, 'NOT_PROVED'
    yield 'nonempty_path', table((b'\x8b\x8b\x15', b'')), 0, 2, 'NOT_PROVED'
    for width in (2, 3, 4):
        yield f'offset_size_{width}', table(off_size=width), 0, 2, 'EMPTY_PROVED'
    yield 'maxp_count_mismatch', original, 0, 3, 'REJECTED'
    yield 'negative_gid', original, -1, 2, 'REJECTED'
    yield 'missing_gid', original, 2, 2, 'REJECTED'
    yield 'truncated_header', original[:4], 0, 2, 'REJECTED'
    yield 'truncated_topdict', original[:6], 0, 2, 'REJECTED'
    yield 'truncated_index', original[:17], 0, 2, 'REJECTED'
    yield 'truncated_program_data', original[:-1], 0, 2, 'REJECTED'
    for name, offset, value in (
        ('wrong_version', 0, 1), ('wrong_minor', 1, 1), ('short_header_size', 2, 4),
        ('offset_before_dict', 5, 139), ('offset_after_table', 5, 246),
        ('missing_charstrings_key', 6, 24), ('zero_offsize', 15, 0),
        ('oversized_offsize', 15, 5), ('non_one_first_offset', 16, 0),
        ('descending_offset', 17, 0), ('last_offset_after_data', 18, 255),
    ):
        data = bytearray(original); data[offset] = value
        yield name, bytes(data), 0, 2, 'REJECTED'
    # Replacing the DICT offset operand with a real number is never accepted.
    yield 'real_charstrings_offset', b'\x02\x00\x05\x00\x03\x1e\x1f\x11' + original[7:], 0, 2, 'REJECTED'
    yield 'unterminated_real', b'\x02\x00\x05\x00\x02\x1e\x12' + original[7:], 0, 2, 'REJECTED'
    yield 'truncated_long_number', b'\x02\x00\x05\x00\x02\x1d\x00' + original[7:], 0, 2, 'REJECTED'
    yield 'truncated_escape', b'\x02\x00\x05\x00\x02\x96\x0c' + original[7:], 0, 2, 'REJECTED'


def run(output):
    if platform.system() != 'Darwin' or not shutil.which('swiftc'):
        raise RuntimeError('CoreText CFF2 proof NOT_RUN: macOS and swiftc required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name('coretext_extract.swift').read_text()
    separator = '\nfunc run() throws {'
    if source.count(separator) != 1 or source.count('func cff2ProvesEmpty(') != 1:
        raise RuntimeError('review_changed_production_cff2_empty_proof')
    harness = output / 'proof.swift'; binary = output / 'proof'
    harness.write_text(source.split(separator)[0] + SWIFT)
    command = ['swiftc', '-O', str(harness), '-o', str(binary)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (output / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    compiled.check_returncode()
    rows = []
    for name, data, gid, count, expected in cases():
        path = output / f'{name}.bin'; path.write_bytes(data)
        command = [str(binary), str(path), str(gid), str(count)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        result.check_returncode()
        record = json.loads(result.stdout)
        rows.append(dict(case=name, expected=expected, actual=record,
                         passed=record.get('result') == expected))
    report = {'status': 'PASS' if all(r['passed'] for r in rows) else 'FAIL',
              'scope': 'production Swift structural proof; authored fragments, not font acceptance',
              'cases': rows}
    (output / 'result.json').write_text(json.dumps(report, indent=2))
    if report['status'] != 'PASS':
        raise AssertionError('CFF2 native empty-proof regression')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = run(args.output)
    print(f"PASS: {len(report['cases'])} production Swift CFF2 empty-proof cases")
