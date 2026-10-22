"""Independent, bounded-buffer validation of C1's unsigned TrueType TTC output.

This is a compact C1 serialization profile, not a generic font sanitizer or
native-equivalence gate. Parse on-disk directories independently of the writer;
verify every occupied byte and zero-filled gap/padding, including shared tables.
C1 writes TTC v1, unsigned glyf faces, and zero head.checkSumAdjustment.

Specification: https://learn.microsoft.com/en-us/typography/opentype/spec/otff
No source font, glyph identity or outline is included in the returned report.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import struct

from ttc_staging_contract import StagingError

MAX_OFFSET = 0xFFFFFFFF


def _require(condition, code):
    if not condition:
        raise StagingError('serialization', code)


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


def _binding(value):
    # Path and descriptor change-time semantics differ on Windows CPython.
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def _read(stream, offset, count):
    stream.seek(offset)
    data = stream.read(count)
    _require(len(data) == count, 'ttc_binary_truncated')
    return data


def _blocks(stream, offset, count, chunk_size):
    while count:
        size = min(count, chunk_size)
        yield _read(stream, offset, size)
        offset += size
        count -= size


def _zero_region(stream, offset, count, chunk_size):
    for block in _blocks(stream, offset, count, chunk_size):
        _require(not any(block), 'ttc_nonzero_padding')


def _checksum(stream, offset, length, chunk_size):
    result, tail = 0, b''
    for block in _blocks(stream, offset, length, chunk_size):
        data = tail + block
        end = len(data) & ~3
        result = (result + sum(value[0] for value in
                              struct.iter_unpack('>I', data[:end]))) & MAX_OFFSET
        tail = data[end:]
    if tail:
        result = (result + int.from_bytes(tail.ljust(4, b'\0'), 'big')) & MAX_OFFSET
    return result


def validate_ttc_binary(path, *, chunk_size=65536, max_table_records=131072):
    """Verify actual TTC bytes; reject malformed or unclaimed data.

    Table/hash buffers are bounded, metadata scales with the limited number of
    records. Equal table intervals may be shared only with equal tag/checksum/
    length. Partial overlap and directory aliasing are rejected. This does not
    decode glyf/gvar or replace the semantic face validator.
    """
    _require(type(chunk_size) is int and 1 <= chunk_size <= 16 * 1024 * 1024,
             'ttc_binary_invalid_chunk_size')
    _require(type(max_table_records) is int and 1 <= max_table_records <= 1048576,
             'ttc_binary_invalid_record_budget')
    path = Path(path)
    try:
        before = path.lstat()
        _require(stat.S_ISREG(before.st_mode), 'ttc_binary_not_regular')
        size = before.st_size
        _require(16 <= size <= MAX_OFFSET, 'ttc_binary_invalid_size')
        with path.open('rb') as stream:
            fd_before = os.fstat(stream.fileno())
            _require(stat.S_ISREG(fd_before.st_mode)
                     and _binding(before) == _binding(fd_before)
                     and _identity(path.lstat()) == _identity(before),
                     'ttc_binary_changed')
            magic, version, count = struct.unpack('>4sII', _read(stream, 0, 12))
            _require(magic == b'ttcf' and version == 0x00010000,
                     'ttc_binary_unsupported_header')
            _require(1 <= count <= 65535, 'ttc_binary_invalid_face_count')
            header_end = 12 + 4 * count
            _require(header_end <= size, 'ttc_binary_truncated')
            directories = struct.unpack('>' + str(count) + 'I',
                                        _read(stream, 12, 4 * count))
            _require(len(set(directories)) == count, 'ttc_binary_directory_alias')
            occupied = [(0, header_end)]
            tables = {}
            record_count = 0
            for directory in directories:
                _require(directory % 4 == 0 and header_end <= directory <= size - 12,
                         'ttc_binary_directory_range')
                sfnt, n, search, selector, shift = struct.unpack(
                    '>4sHHHH', _read(stream, directory, 12))
                _require(sfnt == b'\0\1\0\0' and 1 <= n <= 4095,
                         'ttc_binary_invalid_sfnt')
                power = 1 << (n.bit_length() - 1)
                _require((search, selector, shift) ==
                         (power * 16, power.bit_length() - 1, n * 16 - power * 16),
                         'ttc_binary_search_fields')
                record_count += n
                _require(record_count <= max_table_records, 'ttc_binary_record_budget')
                end = directory + 12 + 16 * n
                _require(end <= size, 'ttc_binary_directory_range')
                occupied.append((directory, end))
                previous, found_head = None, False
                for index in range(n):
                    tag, checksum, offset, length = struct.unpack(
                        '>4sIII', _read(stream, directory + 12 + 16 * index, 16))
                    _require(all(32 <= v <= 126 for v in tag) and tag.rstrip(b' ')
                             and b' ' not in tag.rstrip(b' '), 'ttc_binary_table_tag')
                    _require(previous is None or previous < tag, 'ttc_binary_table_order')
                    _require(tag != b'DSIG', 'ttc_binary_signed_input')
                    previous = tag
                    padded = (length + 3) & ~3
                    _require(offset % 4 == 0 and offset >= header_end
                             and offset <= size and padded <= size - offset,
                             'ttc_binary_table_range')
                    if tag == b'head':
                        found_head = True
                        _require(length >= 54, 'ttc_binary_head_missing_or_short')
                    key = (offset, length)
                    value = (tag, checksum)
                    if length and key in tables:
                        _require(tables[key] == value, 'ttc_binary_shared_table_conflict')
                    else:
                        # Empty tables occupy no bytes, but their zero checksum
                        # is still checked and does not create an overlap.
                        if not length:
                            _require(checksum == 0, 'ttc_binary_checksum')
                        else:
                            tables[key] = value
                _require(found_head, 'ttc_binary_head_missing_or_short')
            occupied.extend((offset, offset + ((length + 3) & ~3))
                            for offset, length in tables)
            occupied.sort()
            _require(all(a[1] <= b[0] for a, b in zip(occupied, occupied[1:])),
                     'ttc_binary_overlap')
            _require(occupied[-1][1] == size, 'ttc_binary_trailing_bytes')
            for a, b in zip(occupied, occupied[1:]):
                _zero_region(stream, a[1], b[0] - a[1], chunk_size)
            for (offset, length), (tag, checksum) in tables.items():
                if tag == b'head':
                    _require(_read(stream, offset + 8, 4) == b'\0' * 4,
                             'ttc_binary_head_adjustment')
                _require(_checksum(stream, offset, length, chunk_size) == checksum,
                         'ttc_binary_checksum')
                _zero_region(stream, offset + length, (-length) % 4, chunk_size)
            digest = hashlib.sha256()
            for block in _blocks(stream, 0, size, chunk_size):
                digest.update(block)
            _require(_identity(os.fstat(stream.fileno())) == _identity(fd_before)
                     and _identity(path.lstat()) == _identity(before),
                     'ttc_binary_changed')
        return {'status': 'BINARY_STRUCTURE_VERIFIED', 'faces': count,
                'table_references': record_count, 'unique_nonempty_tables': len(tables),
                'byte_size': size, 'sha256': digest.hexdigest(),
                'production_accepted': False, 'native_source_equivalence': False}
    except OSError as error:
        raise StagingError('platform_read', 'ttc_binary_read_failed') from error
