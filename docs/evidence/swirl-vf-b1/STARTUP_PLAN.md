# Original startup diagnosis with an unchanged private-copy control

The no-VORG variant in native run 39403338270 produced zero accepted metric
records. Its public error does not identify the failing startup layer. This
new experiment changes the observation, not the metric test or its threshold.
It makes **zero glyph, outline, advance, translation or layout requests**.

Four independent processes inspect these conditions in order:

1. Original system-path TTC.
2. A byte-identical copy at a private temporary path.
3. The verified directory-only no-VORG copy at that same private path.
4. Original system-path TTC again.

Each source is independently SHA-256 and byte-size bound, and every raw source
table identity is recomputed in Python. The two private variants are written
sequentially to exactly one pathname; the original file is only read. Temporary
fonts are deleted before completion and never enter an uploaded artifact.
The unchanged private copy controls for relocation and its loading context;
equal file contents do not imply equal extended attributes or system trust.

The independent B1 Swift probe preserves the production startup API semantics:
unregistered URL descriptors followed by CTFontCreateWithFontDescriptor at
size 0 and the identity matrix. It does not edit or link the production Swift
entrypoint. Its best-match CTFont return is not treated as source identity.

Before judging success, the probe records descriptor nil/empty/type states,
all descriptor and font URL presence/match booleans, size/matrix binary64 bits,
all retained table lengths/hashes, and direct CTFontCopyTable(VORG) presence,
length and hash. Descriptor indices are never assumed to be raw face indices;
all 32 physical faces are compared, and ambiguous identities stay ambiguous.
There are no source path strings, font payloads or original glyph outlines in
the output. Fixed failure codes replace arbitrary native error text.

The Python consumer rechecks source identities, every recorded table
comparison, binding sets, counters and binary64 startup metadata. It saves the
native stdout byte-for-byte after validation. A/A reports must be exactly
equal. Missing descriptors cannot be reclassified as VORG API nil: direct
VORG observations exist only for an actual CTFont, with source identity
separately reported.

Interpretation is bounded:

- If the unchanged private copy also fails binding, VORG causality is unknown.
- If only the no-VORG private copy fails, removal is associated with startup
  binding failure under these controlled conditions, not proof of its internal
  reason.
- If a retained-table-bound no-VORG copy still exposes VORG, that visibility is
  recorded rather than assuming directory deletion made the API table absent.
- If source URLs, retained tables and VORG API nil all agree, that establishes
  only this startup observation; it supplies no glyph metric-equivalence pass.

This workflow can finish green for complete, accurate refusal diagnostics.
That is not a reclassification of the earlier red original metric gate.
Original acceptance is always false and reconstructed original faces remain 0.
