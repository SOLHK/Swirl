"""Bounded-buffer, no-clobber TTC packing of already verified standalone faces.

This module changes no glyph IDs, axis values, layout data or model coefficients.
It copies complete SFNT tables and clears only head.checkSumAdjustment, which is
unused in a collection. It is an integrity layer, not native-font acceptance.

Primary design references (independent implementation, no copied upstream code):
https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/ttLib/ttCollection.py
https://learn.microsoft.com/en-us/typography/opentype/spec/otff
Unlike TTCollection.save's byte-keyed table cache, this writer retains only
table metadata and hashes. Hash matches always receive a full byte comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import struct
import tempfile

from ttc_staging_contract import StagingError


MAX_OFFSET = 0xFFFFFFFF
_SFNT = struct.Struct(">4sHHHH")
_ENTRY = struct.Struct(">4sIII")


def _require(ok, code, **context):
    if not ok:
        raise StagingError("serialization", code, **context)


def _checked_end(offset, size):
    _require(type(offset) is int and type(size) is int and offset >= 0 and size >= 0
             and offset <= MAX_OFFSET and size <= MAX_OFFSET - offset,
             "ttc_offset_overflow")
    return offset + size


def _stat_id(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


def _regular(path):
    try:
        value = path.lstat()
    except OSError as error:
        raise StagingError("platform_read", "source_read_failed") from error
    _require(stat.S_ISREG(value.st_mode), "source_not_regular")
    return value


def _chunks(stream, offset, length, chunk_size, *, head=False):
    """Read at most chunk_size bytes, with no hidden full-table buffer."""
    stream.seek(offset)
    done = 0
    while done < length:
        data = stream.read(min(chunk_size, length - done))
        _require(bool(data), "truncated_table")
        if head and done < 12 and done + len(data) > 8:
            lo, hi = max(8 - done, 0), min(12 - done, len(data))
            data = data[:lo] + b"\0" * (hi - lo) + data[hi:]
        done += len(data)
        yield data


def _fingerprint(stream, offset, length, chunk_size, *, head=False):
    digest, checksum, tail = hashlib.sha256(), 0, b""
    for data in _chunks(stream, offset, length, chunk_size, head=head):
        digest.update(data)
        data = tail + data
        boundary = len(data) & ~3
        checksum += sum(item[0] for item in struct.iter_unpack(">I", data[:boundary]))
        checksum &= MAX_OFFSET
        tail = data[boundary:]
    if tail:
        checksum = (checksum + int.from_bytes(tail.ljust(4, b"\0"), "big")) & MAX_OFFSET
    return digest.hexdigest(), checksum


def _file_hash(stream, size, chunk_size):
    digest = hashlib.sha256()
    for data in _chunks(stream, 0, size, chunk_size):
        digest.update(data)
    return digest.hexdigest()


@dataclass(frozen=True)
class _Table:
    tag: bytes
    checksum: int
    offset: int
    length: int
    digest: str


@dataclass(frozen=True)
class _Face:
    path: Path
    identity: tuple
    digest: str
    header: bytes
    tables: tuple


def _describe_face(path, chunk_size, expected):
    before = _regular(path)
    _checked_end(0, before.st_size)
    with path.open("rb") as stream:
        _require(_stat_id(os.fstat(stream.fileno())) == _stat_id(before),
                 "source_changed_before_open")
        header = stream.read(_SFNT.size)
        _require(len(header) == _SFNT.size, "truncated_sfnt_header")
        version, count, search, selector, shift = _SFNT.unpack(header)
        _require(version == b"\0\1\0\0", "unsupported_standalone_sfnt")
        _require(0 < count <= 4095, "invalid_sfnt_table_count")
        power = 1 << (count.bit_length() - 1)
        _require((search, selector, shift) == (power * 16, power.bit_length() - 1,
                                                count * 16 - power * 16),
                 "invalid_sfnt_search_fields")
        directory_end = _checked_end(_SFNT.size, count * _ENTRY.size)
        _require(directory_end <= before.st_size, "truncated_sfnt_directory")
        raw = []
        previous = None
        for _ in range(count):
            data = stream.read(_ENTRY.size)
            _require(len(data) == _ENTRY.size, "truncated_sfnt_directory")
            tag, checksum, offset, length = _ENTRY.unpack(data)
            _require(all(32 <= x <= 126 for x in tag) and tag.rstrip(b" ")
                     and b" " not in tag.rstrip(b" "), "invalid_table_tag")
            _require(previous is None or previous < tag, "duplicate_or_unsorted_table_tag")
            previous = tag
            _require(tag != b"DSIG", "signed_standalone_font_requires_explicit_resigning")
            end = _checked_end(offset, length)
            _require(offset % 4 == 0 and offset >= directory_end and end <= before.st_size,
                     "invalid_table_range", table=tag.decode("ascii"))
            raw.append((tag, checksum, offset, length))
        occupied = sorted((offset, offset + length) for _, _, offset, length in raw if length)
        _require(all(a[1] <= b[0] for a, b in zip(occupied, occupied[1:])),
                 "overlapping_standalone_tables")
        _require(any(tag == b"head" and length >= 54 for tag, _, _, length in raw),
                 "missing_or_truncated_head")
        tables = []
        for tag, checksum, offset, length in raw:
            digest, actual = _fingerprint(stream, offset, length, chunk_size, head=tag == b"head")
            _require(actual == checksum, "source_table_checksum_mismatch", table=tag.decode("ascii"))
            tables.append(_Table(tag, checksum, offset, length, digest))
        digest = _file_hash(stream, before.st_size, chunk_size)
        _require(expected is None or digest == expected, "source_sha256_mismatch")
        _require(_stat_id(os.fstat(stream.fileno())) == _stat_id(before)
                 and _stat_id(_regular(path)) == _stat_id(before), "source_changed_during_scan")
    return _Face(path, _stat_id(before), digest, header, tuple(tables))


def _same_bytes(source, table, target, offset, chunk_size):
    target.seek(offset)
    for data in _chunks(source, table.offset, table.length, chunk_size, head=table.tag == b"head"):
        if target.read(len(data)) != data:
            return False
    return True


def _source_unchanged(face, stream, chunk_size):
    _require(_stat_id(os.fstat(stream.fileno())) == face.identity
             and _stat_id(_regular(face.path)) == face.identity,
             "source_changed_during_pack")
    _require(_file_hash(stream, face.identity[2], chunk_size) == face.digest,
             "source_changed_during_pack")


def _fsync_directory(directory):
    if os.name != "nt":
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _verify_packed(candidate, faces, directories, placements, chunk_size):
    """Validate complete serialized directories and table bytes before publish."""
    with candidate.open("rb") as actual:
        expected_header = struct.pack(">4sII", b"ttcf", 0x00010000, len(faces))
        expected_header += struct.pack(f">{len(directories)}I", *directories)
        _require(actual.read(len(expected_header)) == expected_header, "ttc_header_changed")
        for face, directory, placement in zip(faces, directories, placements):
            actual.seek(directory)
            expected = face.header + b"".join(
                _ENTRY.pack(table.tag, table.checksum, offset, table.length)
                for table, offset in zip(face.tables, placement))
            _require(actual.read(len(expected)) == expected, "ttc_directory_changed")
            with face.path.open("rb") as source:
                for table, offset in zip(face.tables, placement):
                    _require(_same_bytes(source, table, actual, offset, chunk_size),
                             "ttc_table_bytes_changed", table=table.tag.decode("ascii"))
                    digest, checksum = _fingerprint(actual, offset, table.length, chunk_size)
                    _require((digest, checksum) == (table.digest, table.checksum),
                             "ttc_table_checksum_mismatch", table=table.tag.decode("ascii"))
                _source_unchanged(face, source, chunk_size)


def pack_collection(face_paths, destination, *, expected_sha256=None, chunk_size=1024 * 1024,
                    share_tables=True, validate=None):
    """Pack all supplied faces in order, atomically and without overwriting.

    ``expected_sha256`` binds paths to caller-verified standalone font bytes.
    If omitted, the writer snapshots them itself, without claiming validation.
    ``validate(candidate_path)`` runs before final byte revalidation/publication.
    Any failure removes the temporary candidate and leaves existing files alone.
    The call proves packaging integrity only; production_accepted is always false.
    File buffers are bounded by chunk_size; metadata scales with face/table count.
    """
    _require(type(chunk_size) is int and 1 <= chunk_size <= 16 * 1024 * 1024,
             "invalid_copy_chunk_size")
    _require(type(share_tables) is bool, "invalid_table_sharing_flag")
    paths = tuple(Path(path) for path in face_paths)
    _require(0 < len(paths) <= 65535, "invalid_collection_face_count")
    _require(validate is None or callable(validate), "invalid_collection_validator")
    destination = Path(destination)
    _require(destination.name.casefold() != "swirl-vf.ttc", "production_filename_reserved")
    _require(not destination.exists() and not destination.is_symlink(), "destination_exists")
    _require(all(destination.resolve() != path.resolve() for path in paths), "destination_source_alias")
    expected = [None] * len(paths) if expected_sha256 is None else list(expected_sha256)
    _require(len(expected) == len(paths), "source_hash_count_mismatch")
    _require(all(value is None or (type(value) is str and len(value) == 64
                    and all(c in "0123456789abcdef" for c in value)) for value in expected),
             "invalid_source_sha256")
    try:
        faces = [_describe_face(path, chunk_size, digest) for path, digest in zip(paths, expected)]
    except OSError as error:
        raise StagingError("platform_read", "source_read_failed") from error
    directories, cursor = [], _checked_end(12, len(faces) * 4)
    for face in faces:
        directories.append(cursor)
        cursor = _checked_end(cursor, _SFNT.size + len(face.tables) * _ENTRY.size)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".ttc-staging-", suffix=".tmp", dir=destination.parent)
    candidate, placements, dedup = Path(name), [], {}
    shared, written, published, completed = 0, 0, False, False
    try:
        with os.fdopen(fd, "w+b") as target:
            target.write(struct.pack(">4sII", b"ttcf", 0x00010000, len(faces)))
            target.write(struct.pack(f">{len(directories)}I", *directories))
            for face, directory in zip(faces, directories):
                placement = []
                with face.path.open("rb") as source:
                    _source_unchanged(face, source, chunk_size)
                    for table in face.tables:
                        key = (table.tag, table.length, table.digest, table.checksum)
                        offset = None
                        for previous in dedup.get(key, ()) if share_tables else ():
                            if _same_bytes(source, table, target, previous, chunk_size):
                                offset = previous
                                shared += 1
                                break
                        if offset is None:
                            offset = cursor
                            padded = (table.length + 3) & ~3
                            cursor = _checked_end(cursor, padded)
                            target.seek(offset)
                            for data in _chunks(source, table.offset, table.length,
                                                chunk_size, head=table.tag == b"head"):
                                target.write(data)
                            target.write(b"\0" * (padded - table.length))
                            dedup.setdefault(key, []).append(offset)
                            written += 1
                        placement.append(offset)
                    _source_unchanged(face, source, chunk_size)
                placements.append(tuple(placement))
                target.seek(directory)
                target.write(face.header)
                for table, offset in zip(face.tables, placement):
                    target.write(_ENTRY.pack(table.tag, table.checksum, offset, table.length))
            target.truncate(cursor)
            target.flush()
            os.fsync(target.fileno())
        if validate is not None:
            validate(candidate)
        _verify_packed(candidate, faces, directories, placements, chunk_size)
        _require(_regular(candidate).st_size == cursor, "ttc_size_changed")
        with candidate.open("rb") as stream:
            digest = _file_hash(stream, cursor, chunk_size)
        # Same-directory hard-link publication is atomic and never replaces an
        # existing target (including one created concurrently or a symlink).
        try:
            os.link(candidate, destination)
        except FileExistsError as error:
            raise StagingError("serialization", "destination_exists") from error
        published = True
        _fsync_directory(destination.parent)
        completed = True
        return {"status": "STAGED_COLLECTION", "production_accepted": False,
                "native_source_equivalence": False, "faces": len(faces),
                "source_sha256": [face.digest for face in faces],
                "sha256": digest, "byte_size": cursor,
                "tables_written": written, "table_references_shared": shared,
                "copy_chunk_bytes": chunk_size,
                "memory_policy": "bounded_byte_buffers_plus_face_table_metadata",
                "all_table_bytes_preserved_except_head_checksum_adjustment": True}
    except StagingError:
        raise
    except (OSError, ValueError, struct.error) as error:
        raise StagingError("serialization", "ttc_pack_io_failure") from error
    finally:
        # A durability error after creating our link must not leave an output
        # reported as failed. Never unlink a different concurrent replacement.
        if published and not completed:
            try:
                if destination.samefile(candidate):
                    destination.unlink()
            except FileNotFoundError:
                pass
        candidate.unlink(missing_ok=True)
