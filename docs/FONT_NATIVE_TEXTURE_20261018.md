# Native preview texture and glyph extents — 2026-10-18

At fractional display scales, QQuickPaintedItem rounded the surface dimensions and mapped that texture back to the logical item rectangle. An odd logical height at DPR1.5 introduced a second resampling pass. The preview also clipped legitimate ink outside the layout box. These are preview rendering defects; the original font bytes and all real OpenType axes remain unchanged.

VariableFontPreview now owns one current native raster and one scene graph texture. Its quad uses the image's physical dimensions divided by DPR. Glyph extents from each positioned QRawFont glyph, plus the existing layout/run rectangles and a small antialias margin, preserve overshoot without changing advances, wrapping, implicit line height or any other layout geometry. The existing render-origin pixel alignment remains. Scale/rotation animation retains filtering; HGHT is still a real QFont variable axis. No per-coordinate image/font cache is introduced. The rest of the UI keeps its existing native text path and confirmed axis bindings.

## Diagnosis and bounded validation

The prior108-case run had44 failures:36 raster differences and10 nominal-box overhangs, with2 overlapping. Four72pt cases also exceeded the physical display's available window height. All36 raster differences had odd logical heights at DPR1.5. Six selected cases still failed after introducing tiled captures, demonstrating that oversized windows alone did not explain them.

The test now uses a fixed1060x640 logical viewport and integer-physical-pixel tiles to cover large text. It compares every captured pixel against a padded, independently drawn same-engine/same-axis native reference. Natural overhang itself is diagnostic; lost or changed ink fails. No evidence image is resized, sharpened or postprocessed. The tolerance remains2 per channel and actual maximum differences are retained.

- Original44 failures:44/44 passed after the native-texture fix, maximum channel delta2. Previously passed64 cases were reused rather than rerun as another108-case matrix.
- Six final representative cases at actual150%:6/6 passed, maximum delta0. Final separate native Windows font-backend samples:6/6, delta0. The application's existing FreeType backend remains selected; no engines were stacked or changed globally.
- Missing requested10/11/12/13/14pt checks:89 new combinations passed at actual150%; the remaining default12pt sample was already covered in the five-family check.
- Supplemental simulated DPRs1/1.25/1.75/2:124 new point/axis combinations each, reusing existing default9/16pt results. Four high-DPR cases initially lost1–2 top-edge pixels in11/12pt wght100/wdth80/HGHT1000. Their run rectangles excluded glyph overshoot. Unioning positioned glyph extents fixed all four; targeted final comparisons had delta0.
- A single simulated100% scale-restore assertion was timing-sensitive (one failure, two passes in isolation). It now waits up to250ms for observable render alignment rather than assuming a frame completes within25ms. Three final isolated repetitions passed. This wait is outside performance measurements.
- Composite coverage index:7 requested sizes (9/10/11/12/13/14/16pt) x18 real axis coordinates =126 covered combinations at each of5 DPRs. This is an evidence union across staged tests and targeted repairs, not a fresh630-case run of the final commit. Only150% is actual Windows scale; other four values are application simulations, with no system change or live cross-screen transition.
- All5 TTC families rendered without fallback. Persistence tests include a separate restart process. UI32/32 checks passed, including real HGHT input, fractional numeric values, draft/confirmed separation, global input/dialog/page axis bindings, retained page instance and finite memory behavior.
- All-pages, motion and navigation CTests passed (3/3). Final change only expands raster ink bounds; unchanged page tests were not repeated.

## Performance and limits

The final1024-distinct-coordinate test peaked at265.39 MiB private bytes and ended at255.94 MiB; repeated identical coordinates reached a plateau. This is finite stress evidence, not a proof of unlimited runtime behavior.

At unchanged actual120Hz/150%, three direct timing rounds completed. Median queued-present interval was8.329–8.356ms static,8.345–8.405ms for HGHT slider input, and8.382–8.400ms for three-axis changes. Four-line rasterization medians were5.346–5.464ms and5.792–5.894ms respectively. The new textureUpdateCpuWallMs metric measures CPU texture preparation (about0.001ms median), not GPU upload completion. Raw sample flags now say textureUpdate. The initial invocation through the fonts preview route did not drive the slider and is retained as invalid measurement evidence; the existing settings/字体 entry route produced the valid measurements.

frameSwapped means queued presentation, not physical scanout. Stable240fps while changing axes remains NOT PASSED based on the earlier240Hz stage; it was not rerun and no animation was removed. No physical-panel sharpness conclusion is inferred from Qt captures or ToDesk. Subjective physical clarity remains for the user.

Supported native Windows interaction is unavailable in this environment (no node_repl/sky entry point; cua native window methods are absent). Actual system100/125/175/200% switching, cross-screen recovery and a real Swirl community-button-to-browser click therefore remain UNTESTED. No registry, system-font installation, display-scale workaround or external message was used. Actual baseline remains2560x1600,144DPI/150%,120Hz. The existing installed Swirl process was left running.

Historical10/12 font-function acceptance is preserved as a historical rubric, not recomputed from this coverage. Font progress is independent of the core10.83% record.

## Evidence and rollback

All original fonts, private captures, isolated builds and raw reports remain under `D:\Codex\PingFangUI-Optimization`, outside Git. No modified font is recommended: original, read-only backup and working copy still match SHA-256 `124bab748149ea99cd26727384c80f53c92b8abbb3299c66770668ca55ae438b`. The earlier hinting/gasp experiment has no established benefit and is not selected.

Local reports: `NATIVE_TEXTURE_FINAL_MANIFEST.json`, `NATIVE_TEXTURE_COVERAGE_INDEX.json`, `FONT_NATIVE_TEXTURE_FINAL_20261018.txt`; raw directories start `native-texture-`, and representative pre-fix captures are in `tiled-six-before`. Captures compare renderer versions with the same original font, not an original-versus-modified font. Window/tiling differences are recorded; images are unprocessed application renders, not physical screenshots. `scripts/Open-FontReview.ps1` opens the frozen isolated build when the user chooses to run it.

Revert this stage's commit to remove native-texture rendering and these diagnostics while retaining prior independent font functionality. Close only a manually opened isolated review window if present. Original fonts, original running app and system settings require no rollback. No proxy core, protocol or subscription code is changed.

Implementation references: [Qt painted-item implementation](https://github.com/qt/qtdeclarative/blob/6.10/src/quick/items/qquickpainteditem.cpp), [Qt painter node sizing](https://github.com/qt/qtdeclarative/blob/6.10/src/quick/scenegraph/util/qsgdefaultpainternode.cpp), [QGlyphRun bounds and positions](https://doc.qt.io/qt-6/qglyphrun.html#boundingRect), [QRawFont glyph bounds](https://doc.qt.io/qt-6/qrawfont.html#boundingRect). The implementation is independently written using public Qt APIs.
