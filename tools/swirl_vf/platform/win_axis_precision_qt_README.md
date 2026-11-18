# D1 original synthetic Qt axis experiment

`win_axis_precision_qt.cpp` is an independent executable using Qt Core and Gui.
It never modifies `FontManager`, `FontAxisPolicy`, QML, system font settings, or
the Swirl application's saved preferences. The input must be the authored
single-face TrueType fixture generated for this experiment, with `wght`, `WDTH`,
and `HGHT` axes. No Apple font or Apple-derived outline is required.

The ordinary fixture is appropriate for the multi-size Qt raster matrix. The
separate high-gain fixture is intended for the DirectWrite normalization
experiment; its intentionally extreme dimensions are not a representative UI
font. The family, axis defaults, bounds, and physical font tables are read from
the input rather than inferred from a filename.

## Execution and evidence

Build with Qt 6.9 or newer, linking `Qt6::Core` and `Qt6::Gui`, and compile the
existing `src/Swirl.Quick/app/FontAxisPolicy.cpp` into the executable unchanged.
The D1 workflow pins Qt 6.10.3. Run on Windows with the native `windows` QPA plugin:

```powershell
$env:QT_QPA_PLATFORM = 'windows:fontengine=native'
.\win_axis_precision_qt.exe ordinary.ttf evidence\qt-native
.\win_axis_precision_qt.exe ordinary.ttf evidence\qt-native-reverse --reverse-order
```

`windows:fontengine=freetype` selects the alternative Qt FreeType backend, which
is relevant when the application explicitly requests it. Keep each backend and
invocation in its own output directory. `fontengine=directwrite` is **not** a
recognized selector in the inspected Qt version; using that string would leave
the default choice in effect and would not prove explicit backend selection.
The header records `requested_qpa` separately from the public platform name.
The executable does not query Qt's private font-engine class. Backend attribution
must retain that limitation and the recorded Qt build, requested selector, and
actual variable-axis observations.

For a fixture that has already been installed by the D1 Windows harness, launch
a new process with `--installed`. This mode requires the family to exist in the
system font database before any application-font registration. It never calls
`addApplicationFont` for the fixture. Installation and removal belong to the
harness, not this executable. Private mode rejects a family that is already
installed, so an installed font cannot silently satisfy the private-load test.

Each private run performs **936 observations**: 13 declared coordinate cases ×
3 point sizes (9, 12, 18) × 2 image-device logical DPIs (96, 144) × 4 device pixel
ratios (1, 1.25, 1.5, 2) × 3 passes. The second pass reverses coordinate order;
the third removes and registers the application font again. The independent
`--reverse-order` invocation reverses the first order too. The name avoids Qt's
reserved `--reverse` command-line option, which changes application layout
direction and is consumed by `QGuiApplication` before probe arguments are read.
Installed mode performs the
first two passes: **624 observations**. These numbers describe the planned
matrix; only the emitted successful summary establishes completion.

`qt-axis-precision.jsonl` contains a header, individual observations, pair
comparisons, load/reload controls, and exactly one summary. PNG files preserve
the first pass for every coordinate/size/DPI/DPR combination. The evidence keeps:

- The original binary64 requests `499.006199` and `499.006201` as separate cases
  `pair_lo` and `pair_hi`, plus their binary32 API values and bit patterns.
- The neighboring representable binary32 values, broad axis endpoints, a mixed
  fractional request, and the automatic 400/600 weight hierarchy as independent
  controls. The default, `automatic_600`, and manual mixed positions are obtained
  by calling the existing production `FontAxisPolicy::resolve` implementation.
- `QFont::variableAxisValue` results, explicitly labeled
  **`qfont_requested_axis_storage`**. This getter reports Qt's stored request;
  it is not a DirectWrite native-face axis readback.
- Actual `QRawFont` outline elements and advances for Latin, space, and two
  authored CJK-codepoint glyphs; `QFontMetricsF`; full mixed-text `QTextLayout`
  glyph identities, positions, outlines, and advances; and rendered pixel hashes.
- Exact comparison of the selected physical font tables against the source
  file in both `QRawFont::fromFont` and every actual text-layout run. Matching a
  family name alone cannot satisfy identity checks.
- Independent pair comparisons for actual outline, advance, metrics, text
  layout, and raster output. API storage equality does not substitute for any
  of these comparisons.
- Exact replay comparisons after reversed ordering and application-font
  reload. Every physical axis must independently change actual outlines **and**
  raster output between its minimum and maximum, preventing a static-font or
  ignored-axis implementation from passing merely because the pair is equal.
- A rejected missing-file load that preserves the default family and font
  database, plus a before/after input SHA-256 check.

All images are rendered through `QTextLayout` and `QPainter` to a `QImage` with
explicit logical DPI and DPR. Their dimensions account for actual glyph ink
bounds. This is a real Qt raster experiment; it is not a monitor-movement test,
ClearType visual-quality approval, Qt Quick scene-graph test, or Swirl UI test.
Timing includes measurement, serialization preparation and optional PNG output;
it is informational and is not a frame-time or font-cache-memory benchmark.

A successful run exits 0 with `PASS_QT_SYNTHETIC`. Failure exits nonzero and
retains its evidence. Non-Windows execution returns 77/`NOT_RUN`; offscreen and
non-Windows platform plugins cannot establish native Windows acceptance.
Original TTC, regional PingFang glyphs, and real Swirl UI acceptance remain
`NOT_RUN` even when every synthetic observation passes.

If a strict pair or replay comparison fails, the executable also starts a fresh
child process with the internal `--diagnose-path-state` option. The primary
failure, measurements, status and thresholds remain unchanged. The child writes
`path-state-diagnostic/qt-path-state-diagnostic.jsonl` and three PNGs. It examines
one identical request twice and then the other decimal spelling, recording
paths before/after advances, raw paths, font metrics, layout creation, actual
layout-run path extraction, rasterization and reacquisition of `QRawFont`.
These additional calls are explicitly instrumented diagnostics; they never run
before primary acceptance and are not warm-ups that can replace failed data.
The child ends with `DIAGNOSTIC_COMPLETED_NOT_ACCEPTANCE` rather than a pass
verdict for the font or original matrix.

The separate `--diagnose-subpixel-state` child holds one `const QRawFont`, one
authored `A` glyph, and exactly the same axis request for its entire lifetime.
It renders a `QGlyphRun` at horizontal offsets 0, 0.25, 0.5 and 0.75 pixels,
then replays those offsets without clearing caches. Its
`subpixel-state-diagnostic/qt-subpixel-state-diagnostic.jsonl` records the same
raw object's path immediately before and after each raster operation, then
after an advance query; every raster has a PNG and pixel hash. It reports
observed path changes and unchanged or changed advances without turning them
into an acceptance result. The replay deliberately retains any existing cache
state. No changes in this diagnostic are applied to primary measurements or
production font rendering.

## Measured stage 2 result: raster history changes FreeType path queries

[Windows CI run 39400461390](https://github.com/SOLHK/Swirl/actions/runs/39400461390)
tested source commit `47d6dfc06fa2fddddd1532c1d8370028a6b9da17` with Qt 6.10.3
on Windows Server 2022 build 20348 and Windows Server 2025 build 26100. These
are actual Windows measurements, but neither runner is Windows 11. On each OS,
all four Qt native invocations completed their full synthetic matrices; all
four Qt FreeType invocations failed the strict pair comparison after the first
13 observations. Private and installed loading reproduced the same behavior.
The primary FreeType failure remains a blocker; it is not reclassified as a
successful matrix by the following diagnostic.

The fixed `--reverse-order` option now changes the actual first observation
order. Its effect is directly visible in the original failed observations:

| First observation order | `pair_lo` A rightmost x | `pair_hi` A rightmost x |
| --- | ---: | ---: |
| Forward (`pair_lo` precedes `pair_hi`) | 6.421875 px | 6.4375 px |
| Reverse (`pair_hi` precedes `pair_lo`) | 6.4375 px | 6.421875 px |

Thus the smaller path coordinate follows which request is observed first,
rather than following the decimal value. Both API requests have binary32 bits
`0x43f980cb` (exact value `499.006195068359375`).

Each failed invocation started the separately instrumented path-state child.
All eight children (two OS versions, two load modes and two parent orders)
produced identical diagnostic observation records. With `wght=499.006199`,
`WDTH=HGHT=100`, 9 pt, logical DPI 96 and DPR 1, the same existing `QRawFont`
object produced the following A path coordinate:

| Checkpoint within one unchanged decimal request | A rightmost x |
| --- | ---: |
| Before and after raw advances | 6.421875 px |
| After raw paths, font metrics, layout creation and actual-run path extraction | 6.421875 px |
| Immediately after rasterization | 6.4375 px |
| After reacquiring a raw font | 6.4375 px |
| All checkpoints when repeating exactly `499.006199` | 6.4375 px |
| All checkpoints when subsequently requesting `499.006201` | 6.4375 px |

The change is exactly `1/64 px`. The A advance remains `7.625 px`; text metrics
and pixel output remain equal across the first request, identical-decimal
repeat and other-decimal request. The shared pixel SHA-256 is
`2e9e40bf767345167f349239150f93b16867d4201e6bd39526617f52f76378e1`.
This demonstrates render-history dependence of the path query without any
change in requested decimal or API axis value. It cannot establish additional
input precision or a successful preservation of Apple's source-side result.

Within each downloaded artifact, the independently reviewable evidence is
`d1-evidence/ordinary-qt-freetype-{private|installed}-{forward|reverse}/`
`path-state-diagnostic/qt-path-state-diagnostic.jsonl`. All four private files
have SHA-256 `d96cd5b8d3ec81bfc00fa0741c6c6e9e351149a88aaeadc4174c5d2213a5bd83`;
all four installed files have SHA-256
`fcfea5990d18997d7dc3d6f16c138f668224f912f4148c4b7383a0930f2678bf`.
The files differ only in the header's load mode; their three observation
records match exactly across all eight children.

The inspected Qt source below suggests a preceding raster's FreeType subpixel
translation as the mechanism: raster loading sets it, while the path loader's
face lock refreshes a changed matrix but does not independently clear the
translation. Stage 2 proves the after-raster state effect. The separately
implemented fixed-object subpixel-offset experiment is a further causal test;
its result must be read from its own future Windows evidence rather than
inferred from this stage 2 record.

## Inspected primary references

References were inspected before implementation. This probe is independently
written and does not copy Qt implementation code.

1. [Qt 6.10 QFont documentation](https://doc.qt.io/qt-6.10/qfont.html):
   `setVariableAxis(Tag, float)` and `variableAxisValue(Tag)` have binary32
   interfaces; Windows GDI does not support variable axes through this API.
2. [Qt 6.10.3 QFont implementation](https://github.com/qt/qtbase/blob/7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4/src/gui/text/qfont.cpp):
   `QFontPrivate::setVariableAxis` stores the supplied float and
   `QFont::variableAxisValue` returns that request-map value.
3. [Qt 6.10.3 DirectWrite font database](https://github.com/qt/qtbase/blob/7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4/src/gui/text/windows/qwindowsdirectwritefontdatabase.cpp):
   axis-map values are assigned to `DWRITE_FONT_AXIS_VALUE.value`, then passed
   to `IDWriteFontResource::CreateFontFace`. This path has no additional
   binary64 coordinate channel.
4. [Qt 6.10.3 Windows platform selection](https://github.com/qt/qtbase/blob/7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4/src/plugins/platforms/windows/qwindowsintegration.cpp):
   accepted font-engine selectors are `gdi`, `freetype`, and `native`. The
   default/native branch constructs `QWindowsDirectWriteFontDatabase` when
   built with `directwrite3`, unless GDI or `nodirectwrite` was requested.
5. [Qt 6.10.3 DirectWrite engine](https://github.com/qt/qtbase/blob/7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4/src/gui/text/windows/qwindowsfontenginedirectwrite.cpp):
   axis metadata comes from the DirectWrite font resource. Metadata is distinct
   from the instantiated glyph paths measured by this experiment.
6. [Qt 6.10.3 FreeType engine](https://github.com/qt/qtbase/blob/7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4/src/gui/text/freetype/qfontengine_ft.cpp):
   the float axis map is converted with `FT_Fixed(value * 65536)` and passed to
   `FT_Set_Var_Design_Coordinates`. Its `addGlyphsToPath` path locks the face at
   units-per-em size, loads glyphs with `FT_LOAD_NO_BITMAP` and manually scales
   their outlines. That implementation is separate from raster loading and
   should not be assumed to have identical state or precision.
7. [Qt 6.10.3 QRawFont path delegation](https://github.com/qt/qtbase/blob/7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4/src/gui/text/qrawfont.cpp#L254-L270):
   `pathForGlyph` delegates to the current engine's `addGlyphsToPath`.
   The FreeType engine's [raster loading](https://github.com/qt/qtbase/blob/7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4/src/gui/text/freetype/qfontengine_ft.cpp#L1779-L1824)
   sets a face transform including a subpixel translation. Its
   [path loading](https://github.com/qt/qtbase/blob/7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4/src/gui/text/freetype/qfontengine_ft.cpp#L2349-L2368)
   uses `lockFace(Unscaled)`, and
   [that lock](https://github.com/qt/qtbase/blob/7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4/src/gui/text/freetype/qfontengine_ft.cpp#L2917-L2937)
   refreshes the transform when its matrix changes. The subpixel experiment
   tests the possibility that a preceding raster translation remains visible
   to later paths; source inspection alone is not a measured result.
8. [FreeType transform documentation](https://freetype.org/freetype2/docs/reference/ft2-sizing_and_scaling.html#ft_set_transform):
   the face's matrix and translation are applied during subsequent glyph
   loads. A null translation pointer explicitly resets the translation.

Tag `v6.10.3` was resolved through the GitHub API to source commit
`7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4`.

## Relation to Swirl automatic adaptation

The inspected `FontAxisPolicy.cpp` preserves OpenType weight semantics, derives
`opsz` from logical point size, and retains physical defaults for unprofiled
custom axes. `WDTH` is case-sensitive and is not assumed to be percentage width.
The test calls this existing production policy directly; it does not duplicate
its implementation. Each invocation verifies **36 policy checks**:

- 24 automatic cases: weights 400/600 × logical DPI 96/144/192 × DPR
  1/1.25/1.5/2, with the expected weight and unchanged physical `WDTH`/`HGHT`
  defaults.
- 12 manual cases across the same DPI/DPR grid, retaining `WDTH=137.5` and
  `HGHT=172.5` in their physical custom units and rejecting a separate unsupported
  lowercase `wdth` key.

The resulting automatic default/600 and manual mixed coordinates also enter
the real outline/layout/raster matrix. The header declares the exact case IDs,
matrix dimensions, and expected record counts for independent evidence audit.

The inspected `FontManager.cpp` verifies source identity, keeps a working
fallback, and bounds its metadata/resolution/text-width caches. The experiment
provides native evidence for those underlying Qt capabilities without changing
shared production ownership. It does not certify a future original TTC profile,
regional face selection, or UI performance in advance of that candidate.
