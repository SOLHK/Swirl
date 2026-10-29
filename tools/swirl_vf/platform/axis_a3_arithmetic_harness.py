"""Bind real constructor-entry bits without changing the frozen native oracle.

The existing reviewed production prefix, identity checks, constructor bodies,
glyph extraction and stdout protocol are preserved. The diagnostic run writes
only request identity and axis bits to its private stderr stream immediately
before invoking the selected, unchanged anchor constructor. This is an entry
observation, not a claim about CoreText's unobservable internal representation.
"""
from __future__ import annotations

import json
import re

import anchor_construction_harness as anchor
from probe_axis_a3_construction import diagnostic_failure as prior_diagnostic_failure
from probe_axis_anchor import bits, require


PREFIX = "SWIRL_A3_CONSTRUCTOR_ENTRY "
MODES = ("anchor_endpoint_original", "anchor_quarter_original")
_RUN = "\nfunc run() throws {"
_CALL = "            let (font, location, reported) = try anchorInstance(state, request.location, mode)"
_MARKER = "// SWIRL_A3_ARITHMETIC_ENTRY_AUDIT"
_HELPER = r'''
// SWIRL_A3_ARITHMETIC_ENTRY_AUDIT
func a3AuditConstructorEntry(_ request: Request, _ mode: String) throws {
    guard mode == "anchor_endpoint_original" || mode == "anchor_quarter_original",
          Set(request.location.keys) == Set(["WDTH", "wght", "HGHT"]),
          request.location.values.allSatisfy({ $0.isFinite }) else {
        throw OracleError.invalid("a3_invalid_constructor_entry_audit")
    }
    let payload: [String: Any] = [
        "request_id": request.request_id,
        "face_index": request.face_index,
        "mode": mode,
        "binary64_bits": request.location.mapValues { String($0.bitPattern, radix: 16) }
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    FileHandle.standardError.write(Data("SWIRL_A3_CONSTRUCTOR_ENTRY ".utf8))
    FileHandle.standardError.write(data)
    FileHandle.standardError.write(Data("\n".utf8))
}
'''


def make_harness(source):
    if _MARKER in source:
        raise ValueError("a3_arithmetic_refuses_nested_harness")
    generated = anchor.make_harness(source)
    prefix, run = generated.split(_RUN)
    require(run.count(_CALL) == 1, "a3_arithmetic_native_dispatch_changed")
    run = run.replace(_CALL, "            try a3AuditConstructorEntry(request, mode)\n" + _CALL, 1)
    return prefix + _HELPER + _RUN + run


def diagnostic_failure(error):
    result = prior_diagnostic_failure(error)
    match = re.fullmatch(
        r"(?:native request [0-9]+ face [0-9]+ failed|native oracle startup failed): ([A-Za-z0-9_]{1,160})",
        str(error))
    if match and match.group(1) == "a3_invalid_constructor_entry_audit":
        result["native_failure_code"] = match.group(1)
    return result


def check_entry_audit(text, expected, mode):
    """Check the entire stderr audit against already-issued native requests.

    Other runtime diagnostics are not copied to the public report. Every audit
    line must be valid, unique, in actual request order, and bit-exact; neither
    a missing line nor an extra audit line can be ignored.
    """
    require(mode in MODES and type(expected) is list and bool(expected),
            "a3_entry_audit_plan_invalid")
    rows = []
    for line in text.splitlines():
        if not line.startswith(PREFIX):
            continue
        try:
            row = json.loads(line[len(PREFIX):])
        except (ValueError, TypeError):
            raise ValueError("a3_entry_audit_json_invalid") from None
        require(type(row) is dict and set(row) == {"request_id", "face_index", "mode", "binary64_bits"},
                "a3_entry_audit_fields_invalid")
        raw = row["binary64_bits"]
        require(type(raw) is dict and set(raw) == {"WDTH", "wght", "HGHT"}
                and all(type(value) is str and re.fullmatch(r"[0-9a-f]{1,16}", value) for value in raw.values()),
                "a3_entry_audit_bits_invalid")
        rows.append({**row, "binary64_bits": {tag: value.zfill(16) for tag, value in raw.items()}})
    require(len(rows) == len(expected), "a3_entry_audit_count_mismatch")
    seen = set()
    for row, request in zip(rows, expected):
        require(type(row["request_id"]) is str and row["request_id"] == request["request_id"]
                and row["request_id"] not in seen and type(row["face_index"]) is int
                and row["face_index"] == request["face_index"] and row["mode"] == mode,
                "a3_entry_audit_request_identity_mismatch")
        require(row["binary64_bits"] == bits(request["location"]), "a3_entry_audit_input_bits_changed")
        seen.add(row["request_id"])
    return {row["request_id"]: row["binary64_bits"] for row in rows}
