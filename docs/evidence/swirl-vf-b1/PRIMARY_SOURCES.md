# B1 primary references and limits

Reviewed on 2026-10-20 for the B1 metric-discrimination experiments.
These sources describe public contracts and open-source implementations. They
do **not** establish Apple's private CoreText metric algorithm or prove the
849/850 root cause. A measured synthetic result is not original-PingFang
acceptance. No source text or implementation has been copied into production.

## Public contracts and supported claims

| Primary source | What it supports | What it does not establish |
| --- | --- | --- |
| [Apple: CTFontGetAdvancesForGlyphs](https://developer.apple.com/documentation/coretext/ctfontgetadvancesforglyphs%28_%3A_%3A_%3A_%3A_%3A%29) | Glyph advances are scaled and transformed in font space; the API returns individual vectors and a summed advance. | An internal precision, rounding order, phantom algorithm, or equality to serialized integers. |
| [Apple: CTFontGetVerticalTranslationsForGlyphs](https://developer.apple.com/documentation/coretext/ctfontgetverticaltranslationsforglyphs%28_%3A_%3A_%3A_%3A%29) | Returns the horizontal-to-vertical-origin translation for glyphs. | That vertical X is necessarily half the current variable advance or that a layout offset repairs raw metrics. |
| [Apple: CTRunGetAdvances](https://developer.apple.com/documentation/coretext/ctrungetadvances%28_%3A_%3A_%3A%29) | Run advances are a distinct layout observation channel. | Independence from the CoreText metric implementation or freedom from font fallback. |
| [Apple: CGFont](https://developer.apple.com/documentation/CoreGraphics/CGFont?language=objc) | CGFontGetGlyphAdvances exposes advance widths; unitsPerEm gives glyph-space units per em. | A public vertical-advance equivalent: CGFontGetGlyphAdvances has no orientation argument. |
| [Microsoft: OpenType variations overview](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview) | Normalization has specified fixed-point conversion rules; subsequent interpolation precision and final-value rounding have implementation latitude. | Apple's exact implementation or raw metric equivalence of every standard representation. |
| [Microsoft: gvar](https://learn.microsoft.com/en-us/typography/opentype/spec/gvar) | gvar includes four metric phantom points in addition to outline points or components; HVAR/VVAR provide alternative metric access. | The precision or ordering of CoreText's phantom evaluation. |
| [Microsoft: vmtx](https://learn.microsoft.com/en-us/typography/opentype/spec/vmtx) | Stores advanceHeight and topSideBearing in design units; vertical Y is yMax plus topSideBearing; vertical X is not stored here; layout may use BASE. | An arbitrary per-glyph/per-instance X-origin representation in vmtx. |
| [Microsoft: HVAR](https://learn.microsoft.com/en-us/typography/opentype/spec/hvar) | Provides variations for horizontal advances and optional side bearings. | Storage of an independent vertical X origin. |
| [Microsoft: VVAR](https://learn.microsoft.com/en-us/typography/opentype/spec/vvar) | Provides vertical advance and optional bearing variations; vertical-origin mappings refer to Y and are not used for TrueType outlines. | A VOrgMap solution for glyf vertical X. |
| [Microsoft: VORG](https://learn.microsoft.com/en-us/typography/opentype/spec/vorg) | Stores Y origins for CFF/CFF2; it must be ignored for TrueType outlines. | A conforming glyf X-origin fix, even if an engine happens to respond to a diagnostic VORG addition. |
| [Apple: vhea](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6vhea.html) | Vertical typographic ascender/descender describe font-wide distances to the right/left of the vertical center baseline. | A per-glyph advance-height or phantom formula. |
| [Microsoft: hhea](https://learn.microsoft.com/en-us/typography/opentype/spec/hhea) | Defines horizontal font-wide header metrics and aggregate bounds. | That an hhea field is the cause of this particular vertical error. |
| [Microsoft: OS/2](https://learn.microsoft.com/en-us/typography/opentype/spec/os2) | Defines typographic and Windows font-wide metrics and line-metric selection flags. | That any one such field overrides glyph metrics in the measured CoreText path. |
| [fontTools: _g_l_y_f implementation](https://fonttools.readthedocs.io/en/latest/_modules/fontTools/ttLib/tables/_g_l_y_f.html) | _getPhantomPoints forms left/right from hmtx and top/bottom from vmtx plus glyf bounds; _setCoordinates rounds static metric writes with otRound. | Apple's behavior; a rounded static export is a different reference from the continuous variable model. |

## Predeclared discriminators, not corrections

For an original synthetic glyph, hold design coordinates and delta semantics
constant across UPEM 1000 and 1024: default height 1000 and minimum height 850.
Use each font's own UPEM as point size and record the actual font matrix. Changing
the UPEM here is an experiment; it is not a proposed modification of PingFang.

Let Q_U(x) = trunc(x / U * 65536) * U / 65536. For minimum top 760 and bottom -90,
Q_1000(850) is exactly 849.9908447265625. Q_1024(850) is exactly 850.
An additional common phantom translation of +91 gives top 851 and bottom 1.
Then Q_1000(top) - Q_1000(bottom) is 850.006103515625, while
Q_1000(top - bottom) remains 849.9908447265625. A subsequent integer truncation
therefore separates the two candidates (850 versus 849). These predictions were
computed with exact rational arithmetic before this B1 native experiment.
They neither change observed values nor prove CoreText uses either candidate.

Recommended distinct native channels are direct advance vectors/sums, origin
translation vectors, path coordinates of an original contour witness using the
same endpoint/delta semantics, and identity-verified run advances/positions.
A contour witness is not an observation of inaccessible internal phantom points.
Store raw binary64 values/bits, the serialized integers, and the arithmetic
basis for each derived design-unit value separately.

## Preserved historical failure

The adjacent legacy log is the complete decoded GitHub Actions job log obtained
through the GitHub connector, not a transcript reconstructed from summaries.
Its adjacent provenance file records the exact source SHA, run/job identity,
UTF-8 digest and one-based lines containing the 849/850 assertion and raw values.
Its synthetic-test failure remains a failure irrespective of later diagnostic,
source-table, or layout-only results.
