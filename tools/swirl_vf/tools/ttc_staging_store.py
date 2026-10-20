"""Private, append-only GID batches for C1 reconstruction staging.

A receipt is the commit point: an fsynced, content-addressed payload must exist
before its immutable receipt is published. Unindexed payloads and temporary
files are never counted, repaired in-place, or promoted after a crash. The OS
writer lock is released even on process death. Restores rehash the actual bytes.
This storage layer establishes integrity, not native font equivalence.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from ttc_staging_contract import StagingError


FORMAT = "swirl-vf-c1-batches-v2"


def canonical_bytes(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise StagingError("serialization", "noncanonical_json") from error


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path, chunk_size=1024 * 1024):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            result.update(chunk)
    return result.hexdigest()


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _integer(value, minimum=0, maximum=2**63 - 1):
    return type(value) is int and minimum <= value <= maximum


def _safe_path(path):
    # This is a private build tree, never a location writable by hostile users.
    # Reject symlinks in every existing ancestor, not just the last component.
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise StagingError("serialization", "checkpoint_symlink")
    return path


def _regular(path):
    try:
        info = path.lstat()
    except FileNotFoundError as error:
        raise StagingError("serialization", "checkpoint_missing") from error
    if not stat.S_ISREG(info.st_mode):
        raise StagingError("serialization", "checkpoint_not_private_regular")
    return info


def _fsync_directory(directory):
    # Windows does not expose fsync(directory). File contents are still fsynced
    # before atomic link publication. Do not claim power-loss durability there.
    if os.name != "nt":
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_immutable(path, data):
    """Publish exact bytes without replacing any existing inode."""
    path = _safe_path(path)
    fd, temporary = tempfile.mkstemp(prefix=".uncommitted-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            _regular(path)
            if path.stat().st_size != len(data) or path.read_bytes() != data:
                raise StagingError("serialization", "immutable_checkpoint_conflict")
        finally:
            # A crash here may leave a second .uncommitted alias. Restores
            # validate immutable contents, so that alias cannot count twice
            # and does not invalidate a fully published receipt.
            if os.path.exists(temporary):
                os.unlink(temporary)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _writer_lock(directory):
    lock = _safe_path(directory / ".writer.lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock, flags, 0o600)
    acquired = False
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
            raise StagingError("serialization", "invalid_writer_lock")
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
            os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise StagingError("serialization", "checkpoint_writer_busy") from error
        acquired = True
        yield
    finally:
        if acquired:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _json_file(path, limit):
    info = _regular(path)
    if info.st_size > limit:
        raise StagingError("serialization", "checkpoint_size_limit", limit_bytes=limit,
                           observed_bytes=info.st_size)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise StagingError("serialization", "checkpoint_size_limit", limit_bytes=limit)
    try:
        def pairs(items):
            value = {}
            for key, item in items:
                if key in value:
                    raise ValueError("duplicate key")
                value[key] = item
            return value
        value = json.loads(data, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise StagingError("serialization", "invalid_checkpoint_json") from error
    if canonical_bytes(value) != data:
        raise StagingError("serialization", "noncanonical_checkpoint")
    return value, data


class BatchStore:
    """Fixed, gap-free batch plan bound to source, code, dependencies and recipe.

    `binding` is private build metadata (must include source_sha256 and
    builder_sha256); its complete canonical encoding is immutable. Existing
    records can never be overwritten by a changed recipe or a second writer.
    At most one batch payload is decoded at a time. Receipt metadata is small.
    """

    def __init__(self, directory, binding, face_glyph_counts, *, batch_size=64,
                 max_payload_bytes=64 * 1024 * 1024):
        if (type(binding) is not dict or not _sha(binding.get("source_sha256"))
                or not _sha(binding.get("builder_sha256"))
                or not _integer(batch_size, 1, 65535)
                or not _integer(max_payload_bytes, 1024, 512 * 1024 * 1024)
                or type(face_glyph_counts) not in (tuple, list)
                or not 1 <= len(face_glyph_counts) <= 65535
                or any(not _integer(n, 1, 65535) for n in face_glyph_counts)):
            raise StagingError("font_tables", "invalid_batch_recipe")
        self.directory = _safe_path(directory)
        self.counts = tuple(face_glyph_counts)
        self.batch_size = batch_size
        self.max_payload_bytes = max_payload_bytes
        self.recipe = {"format": FORMAT, "binding": json.loads(canonical_bytes(binding)), "face_glyph_counts": list(self.counts),
                       "batch_size": batch_size, "max_payload_bytes": max_payload_bytes,
                       "commit_policy": "immutable_receipt_after_payload_and_finished_session"}
        self.recipe_bytes = canonical_bytes(self.recipe)
        if len(self.recipe_bytes) > 4 * 1024 * 1024:
            raise StagingError("serialization", "checkpoint_recipe_size_limit")
        self.recipe_sha256 = digest_bytes(self.recipe_bytes)
        self._locked = False

    @contextmanager
    def writer(self):
        if self._locked:
            raise StagingError("serialization", "checkpoint_writer_reentrant")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        _safe_path(self.directory)
        with _writer_lock(self.directory):
            self._locked = True
            try:
                recipe_path = self.directory / "recipe.json"
                if recipe_path.exists():
                    _, data = _json_file(recipe_path, 4 * 1024 * 1024)
                    if data != self.recipe_bytes:
                        raise StagingError("serialization", "checkpoint_recipe_mismatch")
                else:
                    # A lock and orphan .uncommitted files can survive death
                    # before the initial recipe. No other content is accepted.
                    if any(p.name != ".writer.lock" and not p.name.startswith(".uncommitted-")
                           for p in self.directory.iterdir()):
                        raise StagingError("serialization", "checkpoint_recipe_missing")
                    atomic_immutable(recipe_path, self.recipe_bytes)
                for name in ("payloads", "receipts"):
                    path = _safe_path(self.directory / name)
                    path.mkdir(mode=0o700, exist_ok=True)
                yield self
            finally:
                self._locked = False

    def _require_writer(self):
        if not self._locked:
            raise StagingError("serialization", "checkpoint_writer_required")
        _safe_path(self.directory)
        _, actual = _json_file(self.directory / "recipe.json", 4 * 1024 * 1024)
        if actual != self.recipe_bytes:
            raise StagingError("serialization", "checkpoint_recipe_mismatch")

    def ranges(self, face_index=None):
        indices = range(len(self.counts)) if face_index is None else (face_index,)
        for face in indices:
            if not _integer(face, 0, len(self.counts) - 1):
                raise StagingError("font_tables", "invalid_face_index")
            for start in range(0, self.counts[face], self.batch_size):
                yield face, start, min(start + self.batch_size, self.counts[face])

    def _key(self, face, start, stop):
        if (not _integer(face, 0, len(self.counts) - 1)
                or not _integer(start, 0, self.counts[face] - 1)
                or start % self.batch_size or stop != min(start + self.batch_size, self.counts[face])
                or type(stop) is not int):
            raise StagingError("font_tables", "invalid_gid_batch")
        return f"face-{face:05d}-gids-{start:05d}-{stop:05d}.json"

    def _receipt(self, face, start, stop):
        return _safe_path(self.directory / "receipts" / self._key(face, start, stop))

    def _validate_evidence(self, evidence, face, start, stop):
        required = {"schema", "source_sha256", "recipe_sha256", "face_index", "gid_start", "gid_stop",
                    "session_finished", "source_unchanged", "request_count", "observation_count", "kind"}
        if (type(evidence) is not dict or set(evidence) != required
                or evidence.get("schema") != 1
                or type(evidence.get("schema")) is not int
                or evidence.get("source_sha256") != self.recipe["binding"]["source_sha256"]
                or evidence.get("recipe_sha256") != self.recipe_sha256
                or type(evidence.get("face_index")) is not int or evidence["face_index"] != face
                or type(evidence.get("gid_start")) is not int or evidence["gid_start"] != start
                or type(evidence.get("gid_stop")) is not int or evidence["gid_stop"] != stop
                or evidence.get("session_finished") is not True
                or evidence.get("source_unchanged") is not True
                or not _integer(evidence.get("request_count"), 1)
                or not _integer(evidence.get("observation_count"), stop - start)
                or evidence.get("kind") not in ("synthetic_analytic", "native_validated")):
            raise StagingError("platform_read", "incomplete_batch_session", face_index=face)
        # C1 does not yet have the accepted A3/B1 native input interface. Merely
        # supplying native_validated JSON must not admit original-font batches.
        if evidence["kind"] != "synthetic_analytic" or self.recipe["binding"].get("mode") != "synthetic":
            raise StagingError("input_axis", "production_adapter_unavailable")

    def restore(self, face, start, stop):
        self._require_writer()
        path = self._receipt(face, start, stop)
        if not path.exists() and not path.is_symlink():
            return None
        receipt, _ = _json_file(path, 16384)
        keys = {"schema", "recipe_sha256", "face_index", "gid_start", "gid_stop", "payload_sha256",
                "payload_bytes", "record_count", "evidence", "receipt_sha256"}
        if (type(receipt) is not dict or set(receipt) != keys
                or type(receipt["schema"]) is not int or receipt["schema"] != 1
                or receipt["recipe_sha256"] != self.recipe_sha256
                or type(receipt["face_index"]) is not int or receipt["face_index"] != face
                or type(receipt["gid_start"]) is not int or receipt["gid_start"] != start
                or type(receipt["gid_stop"]) is not int or receipt["gid_stop"] != stop
                or not _sha(receipt["payload_sha256"])
                or not _sha(receipt["receipt_sha256"])
                or not _integer(receipt["payload_bytes"], 1, self.max_payload_bytes)
                or type(receipt["record_count"]) is not int or receipt["record_count"] != stop - start):
            raise StagingError("serialization", "invalid_batch_receipt", face_index=face)
        checked = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        if digest_bytes(canonical_bytes(checked)) != receipt["receipt_sha256"]:
            raise StagingError("serialization", "checkpoint_receipt_hash_mismatch", face_index=face)
        self._validate_evidence(receipt["evidence"], face, start, stop)
        payload_path = _safe_path(self.directory / "payloads" / (receipt["payload_sha256"] + ".json"))
        payload, data = _json_file(payload_path, self.max_payload_bytes)
        if len(data) != receipt["payload_bytes"] or digest_bytes(data) != receipt["payload_sha256"]:
            raise StagingError("serialization", "checkpoint_payload_hash_mismatch", face_index=face)
        if (type(payload) is not dict or set(payload) != {"recipe_sha256", "face_index", "records"}
                or payload["recipe_sha256"] != self.recipe_sha256
                or type(payload["face_index"]) is not int or payload["face_index"] != face):
            raise StagingError("serialization", "invalid_batch_payload")
        self._validate_records(payload["records"], start, stop)
        return payload["records"], receipt["evidence"]

    @staticmethod
    def _validate_records(records, start, stop):
        if (type(records) is not list or len(records) != stop - start
                or any(type(row) is not dict or type(row.get("gid")) is not int
                       or row["gid"] != start + number for number, row in enumerate(records))):
            raise StagingError("font_tables", "batch_gid_coverage_mismatch")

    def commit(self, face, start, stop, records, evidence):
        self._require_writer()
        receipt_path = self._receipt(face, start, stop)
        self._validate_records(records, start, stop)
        self._validate_evidence(evidence, face, start, stop)
        data = canonical_bytes({"recipe_sha256": self.recipe_sha256, "face_index": face, "records": records})
        if len(data) > self.max_payload_bytes:
            raise StagingError("serialization", "checkpoint_size_limit",
                               observed_bytes=len(data), limit_bytes=self.max_payload_bytes)
        digest = digest_bytes(data)
        receipt = {"schema": 1, "recipe_sha256": self.recipe_sha256,
                   "face_index": face, "gid_start": start, "gid_stop": stop,
                   "payload_sha256": digest, "payload_bytes": len(data),
                   "record_count": stop - start, "evidence": evidence}
        receipt["receipt_sha256"] = digest_bytes(canonical_bytes(receipt))
        # Validate any old receipt before an idempotent replay. A corrupted
        # confirmed record cannot be replaced with newly computed data.
        if receipt_path.exists() or receipt_path.is_symlink():
            self.restore(face, start, stop)
            _, old = _json_file(receipt_path, 16384)
            if old != canonical_bytes(receipt):
                raise StagingError("serialization", "immutable_checkpoint_conflict", face_index=face)
            return False
        atomic_immutable(self.directory / "payloads" / (digest + ".json"), data)
        atomic_immutable(receipt_path, canonical_bytes(receipt))
        return True

    def progress(self):
        self._require_writer()
        complete_batches = complete_glyphs = complete_faces = 0
        for face, count in enumerate(self.counts):
            accepted = 0
            for _, start, stop in self.ranges(face):
                if self.restore(face, start, stop) is not None:
                    complete_batches += 1
                    accepted += stop - start
            complete_glyphs += accepted
            complete_faces += accepted == count
        return {"staged_batches": complete_batches, "staged_glyph_models": complete_glyphs,
                "staged_faces": complete_faces, "expected_faces": len(self.counts),
                "expected_glyph_models": sum(self.counts), "production_accepted": False,
                "count_scope": "verified private staging payloads; no original native acceptance"}
