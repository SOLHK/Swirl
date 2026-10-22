# Swirl-VF font-body continuation — 2026-10-19

This is an engineering checkpoint, **not an accepted font release**. No
Apple-derived `Swirl-VF.ttc` is generated or certified by this checkpoint.
The production reconstruction and strict native acceptance thresholds are not
changed. Only source code and numeric/aggregate diagnostics enter public CI.

## Environment correction

The previous handoff's missing-source-on-Mac condition is no longer current.
The `xcode-27` runner has the exact resident source SHA
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`,
61,473,880 bytes. It is macOS 27.0.1 arm64. The production source identity
checks have verified all 32 physical faces. No upload of the user's font to
public GitHub is necessary to perform these source-resident measurements.

## Actual native construction comparison

Commit `046e260b5aaafea91c8b83ec281036dbb4fd582e`, workflow run
[39275817385](https://github.com/SOLHK/Swirl/actions/runs/39275817385), job
118139731356 completed. Its downloaded summary artifact SHA is
`76bd42634456caccc75f2b52a45ad8d8a132a14fec7b7b120bda676888df2f8b`.
The source remained unchanged. Each method measured 32 faces, 864 axis
locations and six selected glyphs per location; this is not all-glyph coverage.

| Construction method | Axis checks within unchanged 1e-6 | Maximum axis echo error | Maximum outline point difference from original API | Maximum metric difference |
| --- | ---: | ---: | ---: | ---: |
| Original CTFont copy, diagnostic observation | 492/864 | 0.000172389 | 0 | 0 |
| Copied font descriptor | 492/864 | 0.000172389 | 0 | 0 |
| CGFont named-axis copy | 492/864 | 0.0004945 | 0.006972764 | 4.008422852 |
| CGFont copy followed by zero-tracking attribute | 492/864 | 0.0004945 | 0.006972764 | 0.008422852 |

All construction methods verified source identity; no path-topology mismatch
was seen at those points. Raw NSNumber binary64 values establish that the echo
error precedes JSON serialization. Alternative APIs do not solve the precision
gate, and are **not adopted as a replacement production extractor**. Successful
completion of this diagnostic is not a successful native-font acceptance.

## New geometry and mapping work

`calibrate_hvf_geometry.py` compares an explicit-Type-2 hypothesis with Apple
libhvf, in normalized **design coordinates**, keeping user-coordinate/avar and
metric acceptance separate. Its 32 selected visible roots cover all 13 distinct
Type-2 shapes, maximum hierarchy depth 12 and four rotation-bearing roots.
Each is requested at 27 extrema/default combinations and seven independent
fractional positions. This does not mean all Type-2-dependent glyphs are tested.
The original scalar production evaluator still rejects unsupported tangents.

`batch_geometry.py` evaluates many design coordinates together while retaining
source part, DFS occurrence, path and segment identity for every contour. It
retains fractional geometry, parallel factors, hierarchical translations and
rotations. It rejects unsupported tangent types, malformed locations and
excessive intermediate/output allocations. It has not been promoted to a
native-validated production converter or linked into `rebuild.py`.

`calibrate_avar_metrics.py` compares independent raw-record/normalization
hypotheses with the original HVAR and actual CoreText advances at 3,048 planned
requests. It never silently sorts/deletes the source's duplicate records or
relabels a best-fitting hypothesis as fact. Zero/default special cases and
source-default-versus-numeric-midpoint behavior are tested separately. A metric
match still needs a separate original-outline comparison before adoption.

Local verification on the retained historical source snapshot plus these new
modules: **50 Python parser/reconstruction/helper tests and 6 audit tests
passed**. This is not a claim to have rerun every newer remote test locally.
An initial new analytic-test expected value was wrong: both neighboring
controls translated by 5 units, so their convex combination translates by 5,
not 3.75. The expected point was corrected with that derivation; the original
failure log is retained and no tolerance was enlarged.

The geometry native run at commit `e228268dc779ed23cf674deb6fbfa249a6c8e60d`,
[39279585672](https://github.com/SOLHK/Swirl/actions/runs/39279585672), was still
queued at the last recorded check. No results are presumed from a queued job.

## Remaining production blockers

- Validate and implement complete Type-2/hierarchy semantics; do not simply
  relabel Type 2 as a corner on the strength of a hypothesis.
- Resolve original user-coordinate interpretation and native echo precision
  without hiding the existing strict failure.
- Preserve the source's vertical-origin behavior. Some source origins are not
  half the varied horizontal advance, so current vmtx-only reconstruction
  correctly refuses them. Dropping those origins is not an equivalent fix.
- Run complete all-face/all-glyph reconstruction, serialized standard-font
  checks, independent holdouts, shaping and actual Windows/Qt acceptance.

No font binary, original path data, or physical Windows 11 acceptance is
included. The concurrent Core subscription commit `292df3ba9763414947ec9b5dffa7886c45a00879`
is preserved; its changed files do not overlap these font-specific additions.
