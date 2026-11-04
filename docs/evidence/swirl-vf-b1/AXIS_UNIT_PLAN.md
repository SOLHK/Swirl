# Independent HGHT user-axis-unit control

This is a response to the exact readback rejection in
[attempt 1](FOLLOWUP_READBACK_FAILURE.md), not a change to a metric tolerance or
to A3 mapping. All 550 normalized design coordinates, phantom semantics and
post-stage-1 candidate predictions remain frozen and unchanged.

For each of the same 16 fonts, create a separate sibling file with only HGHT's
fvar min/default/max changed from `-1/0/1` to `-16384/0/16384`. The raw-patch
helper verifies all other table payloads byte-for-byte, allows only the
mandatory head checksum field to change, and verifies SFNT checksums. The
original files and input manifest are retained. There is no avar in these
synthetic fixtures.

Each request explicitly contains both `normalized_design_axes` and
`native_user_axes`; `normalized_HGHT = native_HGHT/16384` is stored as an exact
rational. WDTH units do not change. Thus the problematic normalized coordinate
53/64 becomes exactly 13568 in the native API request. Every prediction still
uses 53/64. The Swift guard still requires exact native user-axis readback and
all original font/table/size/matrix identity checks.

A follow-up-only copy of the Swift probe additionally saves requested and
reported axes before rejection, and includes both binary64 values in any axis
error. It preserves the original exact equality. The first-stage Swift file
remains byte-identical, SHA-256
`1c9a80a7a7e62104925818edf63634d20a666d2f4bb2025016a80780c135d597`.

The run first issues the problematic original-unit request in a separate
process to record its actual readback. This auxiliary process contributes no
accepted metric records. The main experiment then executes all 550 positions
in the new user units in independent forward and reverse processes (1,100 raw
records, 550 exact replay pairs if complete).

For the archived attempt-1 font, compare all 51 complete prefix rows against
the corresponding new-unit rows. Compare direct advance, vertical translation,
full witness path and layout data, including every binary64 bit pattern. Only
font_identity objects are excluded from cross-unit value comparison because
each side is independently checked against its own fvar/table identity. The
baseline remains failed/partial/no-reverse; the last failed request is explicitly
not compared and is not assigned invented values. The archive's known SHA-256
is checked before reading it.

The witness rectangle provides an additional coordinate check: its width gives
`WDTH=(width-600)/200`, its top gives `HGHT=(top-820)/60`, and its bottom gives
`HGHT=(-180-bottom)/90`. These use exact rational conversion from the raw API
points, with no intermediate rounding. Both height inferences must agree with
the intended normalized value. The phantom-only control has a fixed visible
height and is explicitly unable to identify HGHT through the outline.

The 14 new storage/unit tests cover all 550 requests and 242 VVAR coefficient
checks. The 12 exact-channel comparison tests cover partial-baseline provenance,
missing/duplicate IDs, omitted bits, signed zero, unit identity and witness
inference. Four additional tests ensure failed readback values remain unadmitted
and retain their bit evidence. These tests use synthetic records; they do not
replace CoreText execution.

The original VORG ablation now depends only on the Python gate and runs
independently of the synthetic readback control. Its unmodified original-font
representation failures still produce exit 1. No production extractor,
rebuilder, A3 mapping, D1 Windows code, metric threshold or measured value changes.
