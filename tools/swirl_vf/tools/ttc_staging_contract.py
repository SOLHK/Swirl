"""Small, public-safe error contract for the C1 private staging tools.

Staging is infrastructure, not a production font acceptance decision.  The six
categories describe the origin of a failure, not whether a stage may be skipped.
Exception strings and filesystem paths are deliberately never copied into a
public report.  Unknown context fields are discarded rather than serialized.
"""
from __future__ import annotations

import math
import re


CATEGORIES = frozenset({
    "input_axis", "metrics", "outline", "serialization", "platform_read",
    "font_tables",
})

_CODE = re.compile(r"[a-z][a-z0-9_]{0,95}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_NUMBER_FIELDS = frozenset({
    "face_index", "glyph_id", "gid", "gid_first", "gid_last", "face_count",
    "glyph_count", "batch_start", "batch_stop", "batch_index", "batch_size",
    "sample_number", "sample_count", "expected_count", "actual_count",
    "point_count", "tuple_count", "tuple_index", "axis_index", "region_index",
    "item_index", "lookup_index", "limit_bytes", "observed_bytes", "attempt",
    "table_offset", "table_length", "file_size", "byte_size", "offset", "length",
    "max_outline_error", "max_metric_error", "limit", "revision", "expected",
    "actual", "observed", "chunk_size", "chunks_written", "tables_checked",
    "faces_checked", "bytes_copied", "unindexed_count", "generation",
})
_HASH_FIELDS = frozenset({
    "source_sha256", "code_sha256", "expected_sha256", "actual_sha256",
    "recipe_sha256", "batch_sha256", "payload_sha256", "manifest_sha256",
})
_STAGES = frozenset({
    "preflight", "source_identity", "source_tables", "checkpoint", "restore",
    "batch", "batch_sampling", "batch_reconstruction", "batch_serialization",
    "face", "face_tables", "face_serialization", "collection", "packing",
    "serialization", "validation", "publication", "production", "native",
})


def safe_context(context):
    """Retain only bounded numeric identifiers, hashes, tags and fixed stages."""
    result = {}
    for key, value in context.items():
        if key in _NUMBER_FIELDS and type(value) in (int, float):
            try:
                valid = math.isfinite(value) and abs(value) <= 2 ** 64
            except OverflowError:
                valid = False
            if valid:
                result[key] = value
        elif key in _HASH_FIELDS and type(value) is str and _HASH.fullmatch(value):
            result[key] = value
        elif key in ("table", "tag", "axis") and type(value) is str:
            if len(value) == 4 and all(32 <= ord(c) <= 126 for c in value):
                result[key] = value
        elif key == "stage" and type(value) is str and value in _STAGES:
            result[key] = value
    return result


class StagingError(RuntimeError):
    """A typed failure whose message and ``to_dict`` are safe for public CI."""

    def __init__(self, category, code, **context):
        if type(category) is not str or category not in CATEGORIES:
            raise ValueError("unknown staging error category")
        if type(code) is not str or not _CODE.fullmatch(code):
            raise ValueError("invalid staging error code")
        self.category = category
        self.code = code
        self.context = safe_context(context)
        super().__init__(f"{category}:{code}")

    def to_dict(self):
        return {"category": self.category, "code": self.code,
                "context": dict(self.context)}

    as_dict = to_dict


def require(condition, category, code, **context):
    if not condition:
        raise StagingError(category, code, **context)
