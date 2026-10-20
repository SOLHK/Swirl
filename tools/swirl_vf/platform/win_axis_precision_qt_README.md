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
