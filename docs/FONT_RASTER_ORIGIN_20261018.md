# Preview raster origin correction — 2026-10-18

Follow-up: the44 unresolved cases below were diagnosed and repaired in [the native texture stage](FONT_NATIVE_TEXTURE_20261018.md). This document preserves the earlier checkpoint.

A stationary VariableFontPreview positioned on half a physical pixel was filtering its already-native raster a second time. At actual Windows 150% / 120Hz, the 9pt sample differed from direct native drawing at 6958 pixels, maximum channel delta128. Integer placement matched. This is a reproducible preview-compositing defect, not evidence of damaged font outlines.

The fix adds a render-only translation of at most about half a physical pixel for unscaled surfaces. It does not change layout x/y/width/height, line metrics, glyph spacing, font bytes or axes. HGHT/wght/wdth still use real QFont variable axes: this transform never implements or simulates an axis. Rotation, scale and additional transform effects retain their existing filtered rendering. Parent motion is observed after animation; unchanged offsets do not dirty frames. The original parent position is used rather than feeding floating-point transformed output back into alignment.

Nearest texture filtering was tested and rejected. A first reference using fractional logical drawing coordinates also introduced native glyph-rounding differences. Read-only comparison of original PNGs confirmed that the corrected 9/16/72pt results were exactly the original integer-position raster moved one physical pixel. The final check compares live Qt pixels with a separately drawn origin-zero native raster by integer pixel indexing; it neither resizes nor edits evidence images.

## Passed, bounded regression

Actual display 2560x1600, 150% / DPR1.5, 120Hz; FreeType / D3D11; original local TTC, SC family. No simulated scale override.

- 9/16/72pt at integer and half-pixel layout origins: 6/6 cases, maximum channel delta0, no missing glyph/fallback/nonfinite-outline point, no colour fringe, no out-of-bounds ink in these six samples.
- Parent translation alignment, existing0.9scale transform, geometry/font preservation and alignment after restoring scale: passed.
- Idle: 0 queued frames during120ms after settling; no alignment feedback loop.
- Existing painted-preview real-axis check passed. QtTest4/4 including setup/cleanup,3.106s.
- Swirl and SwirlFontTests builds passed. All-pages smoke passed12.99s before the final idle-stability guard; no broad matrix was rerun after that guard.

## Unresolved evidence — not a complete quality acceptance

One broader targeted run used9/16/72pt x18 true axis coordinates x2 placement phases =108 cases.64 passed and44 failed.36 cases had pipeline/reference differences;10 had ink outside the nominal line box (categories overlap). No missing glyphs, fallback, nonfinite outline points or colour fringes were detected. Windows clamped four large requested test-window geometries to the physical display; those captures must not be presented as complete large-layout checks.

These failures are retained in the local JSON/logs. They are not all established font interpolation defects. A next investigation should isolate fractional painted-surface dimensions, original glyph overhang and the test-window size limit, using one failing case at a time. No outline, spacing or line metric was changed to conceal them. The latest idle guard was not followed by another108-case run because the user requested quota conservation.

The user's updated acceptance prioritizes objective rendering/edge/interpolation adaptation. Subjective clarity improvement/blind review is user judgment and no longer blocks engineering. Historical10/12 Swirl acceptance is retained as an old-scope record; it is not increased by removing a gate. Stable240fps while changing axes remains unpassed based on the preceding direct-timing stage. Actual DPI switching/cross-screen checks and the wider size/family matrix remain unverified. No universal physical-display sharpness claim is made.

## Evidence and rollback

All fonts, raw images, private test outputs and isolated binaries remain under `D:\Codex\PingFangUI-Optimization`. See `screenshots\raster-quality-before`, `screenshots\raster-quality-focused-final`, `screenshots\raster-quality-regression-stable`, and matching logs under `reports`. The regression JSON records actual layout/render positions, real axes and per-case failures. Images are unprocessed QQuickWindow/application renders, not physical-panel or ToDesk proof.

Revert this commit to remove only the origin correction and its diagnostic test; the prior independent measurement stage remains available. The original font backup, running installed Swirl and system-font configuration require no rollback. Neither private fonts nor their rendered specimens are committed.
