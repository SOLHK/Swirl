# B1: UPEM and metric-source discriminator

Base: `e505326486202ad4c8e98bb8b66a17b4547c559f`.
Owned branch: `work/vf-metrics-b1`. No integration-branch update is authorized
for this experiment. The production extractor, rebuilder, axis mapping and
Windows tests are unchanged.

## Preregistered design

The two original fonts have UPEM 1000 and 1024. Every corresponding design
coordinate and stored integer is identical; only `head.unitsPerEm` and the
mandatory whole-font checksum differ. The witness has default top/bottom
phantoms 820/-180 and HGHT deltas +60/-90. Thus height is 1000 at default and
850 at the minimum. WDTH changes the advance from 1000 by +/-200, independently
of height. U+4E00 maps to GID 2. No Apple glyph data is in these fixtures.

Training HGHT values are -1, 0, 0.25, 0.375, 1. The independent, predeclared
native holdout values are -0.625, 0.125, 0.625. Each is crossed with WDTH -1, 0,
1. The axes use these values directly, with no avar table and no decimal4
readback adjustment. Their inputs are exactly representable dyadic values.

The 13 variants are gvar only, equivalent HVAR only, equivalent VVAR only,
equivalent HVAR+VVAR, hhea ascent+91, vhea ascent+91, OS/2 typo ascent+91,
OS/2 USE_TYPO_METRICS alone, the typo-ascent sentinel plus USE_TYPO_METRICS,
VORG Y=911, common phantom shifts +1 and +91, and a fixed-visible-outline
counterfactual with the same varying phantoms. The OS/2 combined case is
compared with the typo-ascent-only case; this isolates the selector bit with
different available metric sources. The VORG/glyf case tests actual behavior;
the OpenType VORG contract says glyf fonts must ignore it, so this is not a
proposed production representation. All table and field differences are saved.

This yields 26 fonts and 624 independent positions. Each font is observed in
two isolated processes with reversed request order, for 1,248 records and 624
full-payload, binary64-exact replay pairs. The complete manifest, including
predictions and holdout partition, is written and hashed before native work.

## Four native channels, plus an independent storage layer

1. `CTFontGetAdvancesForGlyphs`: both raw vector components and total. In the
   vertical call the advance is `CGSize.width`; do not accidentally use height.
2. `CTFontGetVerticalTranslationsForGlyphs`: the complete original vector,
   before the documented origin sign interpretation.
3. `CTFontCreatePathForGlyph`: complete path operations and both bounding
   rectangles of the original visible witness. This is not direct access to
   CoreText's hidden phantoms. The fixed-outline counterfactual distinguishes
   an outline-bounds fallback from a phantom-based advance.
4. A two-character actual vertical `CTFrame`/`CTRun`: positions, advances,
   base advances, base origins, frame/line/run geometry and actual font identity.

Each scalar retains its original JSON number and binary64 bits. An exact
rational calculation records `raw * UPEM / actual_point_size` once; neither
the raw result nor any production metric is rounded, compensated or replaced.
Each font is measured at its own UPEM point size and identity font matrix.
The raw stored metrics, gvar deltas, HVAR/VVAR coefficients and mathematical
design-space model are separate from native values. CGFont's integer advance
is explicitly a horizontal auxiliary, not a vertical API.

Both source instances and every layout run must match all original table
hashes, glyph counts, UPEM, exact axes and point size. Only the current fixture
URL is registered in the current process. Fallback, replacement, missing data,
nonfinite values, altered raw-number bits and nonidentical reverse replay all
fail the experiment. A partial native failure retains already measured values.

## Competing predictions frozen before native observations

For top T and bottom B, compare the continuous H=T-B, rounding H once,
rounding T/B separately, and two EM16.16 truncation candidates. The latter are
predictions from historical evidence, not declarations of Apple's internals.

At minimum height 850, UPEM1000 gives
`trunc(850*65536/1000)*1000/65536 = 849.9908447265625`;
a second integer truncation would produce 849. UPEM1024 represents the same
height exactly. Translating both phantoms by +91 leaves H unchanged but makes
the coordinate-first candidate produce 850 while the difference-first
candidate still produces 849 at UPEM1000. At HGHT 0.25, separate half-up
phantom rounding predicts 1037 versus 1038 for height-only rounding; at 0.375,
the predictions are 1057 versus 1056. Predictions keep their intermediate
integer codes and exact rational values.

No matching finite sample set proves a unique internal Apple algorithm.
Eliminated alternatives and prediction failures must remain in the report.

## Strict regression and original-font scope

The original 849/850 failure log is preserved verbatim alongside its provenance
and SHA-256. The existing strict synthetic test is run unchanged as a separate
gate; a successful diagnostic does not turn that failure green.

After the new diagnostic completes, a bounded original-font check uses the
unchanged production extractor and existing exact-replay launcher. It binds
the original font hash, verifies all 32 physical faces, and measures 15
predeclared locations / 60 GIDs across faces 0, 15 and 31. It directly invokes
the unchanged `with_phantoms` X representation gate with its 1e-5 threshold.
The source-table reference remains separately labeled and is not available
when ordered raw avar anchors are ambiguous. Private paths are not published;
only finite whitelisted metrics and identity hashes leave the process.

The native strict budget remains 1/32 FUnit. Source reference availability,
measured differences and X representation failures are counted separately.
No constant +1/-1, origin offset, substitution of source-table metrics, relaxed
tolerance, production mapping edit or font reconstruction is part of this
experiment. Original accepted faces remain 0/32 until a later actual rebuild
and its full gates complete. The new workflow's terminal state may be failure
because the unchanged strict gates intentionally retain real blockers.

## Results

At this preregistration checkpoint macOS execution has not yet occurred. See
the subsequent B1 handoff and archived native run summaries for actual results.
The fixture and numeric/protocol tests are offline checks only.
