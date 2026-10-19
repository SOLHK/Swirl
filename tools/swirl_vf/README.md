# Swirl-VF font engineering tools — 2026-10-19

This directory contains independent code, synthetic tests and native probes. It
contains **no Apple font, converted Apple font or extracted Apple outlines**.
The font itself must be supplied locally by a user with the necessary rights.
Code availability does not confer a license to use or redistribute Apple fonts.

## Current, deliberately separate statuses

* The HVGL 3.1 / HVPM 1 binary reader implements bounds, layout, sparse matrices,
  depth-first structure and remapping validation. The uploaded source's entire
  70,047-part structure has been decoded and checked locally.
* `ExperimentalRenderer` is a research evaluator, **not an Apple oracle**. It
  refuses tangent blend types 2/3/4 rather than substituting another algorithm.
* `rebuild.py` implements native-instance reconstruction with standard
  `glyf/gvar`, complete original face/GID coverage, original axis tags/ranges,
  identity target `avar`, native metric phantom points, and independent
  holdouts plus adaptive refinement. This is explicitly an approximation, not
  a lossless format translation. It requires the CoreText extractor to run.
* Platform probes compile/run in their respective native environments. Public CI
  supplies only original geometric test fonts. Those tests do not certify the
  user's original PingFang or an Apple-derived candidate.
* No accepted Apple-derived `Swirl-VF.ttc` is included or claimed by this stage.

Native synthetic evidence at commits `501099d` and `7dfbdda` includes the Apple
HVF oracle (29/29 geometric locations) and DirectWrite (3 faces, 186 instances,
10 software-rendered DPI images). The CoreText extractor compiles and returns
all 174 requested synthetic glyph records, but its unchanged 1/32 FUnit
analytical regression fails (for example, vertical advance 849 versus 850).
`platform/diagnose_coretext_metrics.py` independently compares gvar-only,
equivalent HVAR/VVAR and static fonts without replacing that failing gate.
The original private PingFang has not been measured by either native oracle.

## Reproducible tools

Python 3.12+, `fonttools==4.61.1`, `numpy==2.2.6` (the source audit also records
the exact local runtime). Install in an isolated environment.

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s audit -p 'test_*.py' -v
python tools/audit_font.py /private/PingFangUI.ttc --output /private/audit
python tools/inspect_hvf.py /private/PingFangUI.ttc --output /private/hvf-preflight.json
```

On macOS, compile and validate the official HVF C oracle and the CoreText
user-coordinate oracle as documented in `platform/HVF_ORACLE_README.md` and
`platform/CORETEXT_ORACLE.md`. A current Apple SDK with `<hvf/Scaler.h>` and
`libhvf` is required for the first probe. The CoreText extractor verifies physical
font-table identity; it refuses to treat a system fallback as the supplied file.

After a private source run establishes the native oracle:

```sh
python tools/rebuild.py /private/PingFangUI.ttc \
  --oracle /private/build/coretext_extract \
  --output /private/output/Swirl-VF.ttc \
  --report /private/output/reconstruction.json
```

The final filename is fixed. An existing output is never overwritten. Missing
native data, differing topology, unrepresentable metrics, unresolved holdout
error or source mutation aborts the build and records `BLOCKED`. A successful
reconstruction still needs independent Apple comparison, Windows, Qt, visual
and performance acceptance; `lossless_conversion` stays false. Every saved
face is reopened and its decoded outline, topology, metric phantom points and
complete gvar coefficients must exactly match the native-checked model. TTC
packing must preserve every verified face's tables. Float-to-integer
quantization and cubic conversion are not hidden.

The default check thresholds are 1 source font unit for the total outline
error bound and for metrics. The cubic conversion allowance of 0.05 units,
when needed, is included in that outline budget. Training/default rounding
errors and independent holdouts are both checked. These are engineering
bounds, not a promise of pixel equality.
Every source glyph must be represented; there is no automatic dropping, outline
boolean merge, alternative-font fallback, pseudo-bold or stretch operation.

## Native Windows validation

`platform/run_directwrite_probe.ps1` builds and runs the DirectWrite probe on a
local supplied font. It enumerates physical TTC faces, compares source `fvar`
with DirectWrite, creates continuous arbitrary-axis instances and measures real
outlines/advances. It can render five DPI scales on light/dark backgrounds.
See `platform/DIRECTWRITE_README.md` for what this does and does not verify.
No system font is installed by these tests.

## Evidence boundaries and remaining work

Raw source `avar` data can contain duplicate input coordinates and records out
of order. A `fontTools` dictionary cannot represent those records faithfully.
The audit preserves the raw records, and the reconstruction asks CoreText at
original user coordinates rather than guessing which duplicate wins.

Native output, complete private per-glyph differences, Apple-font screenshots
and resulting font binaries belong in the user's private workspace. Do not
place them in this public source directory or public Actions artifacts.
Synthetic fixtures in CI are generated from original geometric formulas.

The remaining private acceptance includes original native extraction, all-face
reconstruction with its post-serialization gate, source-vs-target glyph bounds,
true sidebearings/vertical origins, shaping, AAT tracking equivalence where
needed, Windows 11 system installation and application loading, real Swirl UI
screenshots at 100/125/150/175/200%, and measured startup/layout/scroll baselines.
None is replaced by a Linux unit test or by a synthetic Windows pass.

Swirl currently retains its existing 128 MiB (134,217,728 byte) font-file limit.
The size of a complete reconstructed Apple font is unknown. A larger result
would be rejected by the application until the limit is reviewed against the
actual file and memory measurements; dropping glyphs or faces is not a remedy.

## Primary references

* [Apple HVGL 3.1](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html)
* [Apple HVPM 1](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvpm.html)
* [Apple HVF rendering API](https://developer.apple.com/documentation/hvf)
* [ACT-02/PingFangUI-VF](https://github.com/ACT-02/PingFangUI-VF): README and animation,
  not a published turnkey converter. Its removed height axis and altered
  outlines are not adopted here.
* [fontTools](https://github.com/fonttools/fonttools),
  [VariationModel](https://fonttools.readthedocs.io/en/latest/varLib/models.html),
  [cu2qu](https://fonttools.readthedocs.io/en/latest/cu2qu/index.html)
* [OpenType avar](https://learn.microsoft.com/en-us/typography/opentype/spec/avar)
* [DirectWrite arbitrary axis instances](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontresource-createfontface)
* [Qt QFont variable axes](https://doc.qt.io/qt-6/qfont.html#setVariableAxis)
* [Qt application font loading](https://doc.qt.io/qt-6/qfontdatabase.html#addApplicationFont)
* [Current published macOS 27 license](https://www.apple.com/legal/sla/docs/macOS27.pdf)

