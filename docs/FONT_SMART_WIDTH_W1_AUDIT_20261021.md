# W1 width fitting audit — 2026-10-21

This is the preserved initial W1 audit. Its unverified/SDK-unavailable status
describes that checkpoint, not the subsequent W1-B work. See
[W1-B validation](FONT_SMART_WIDTH_W1B_VALIDATION.md) for executed Qt tests,
actual Windows failures and fixes, QML coverage, costs and physical-test limits.

Base: `work/core-completion-20261017` at `50d2a8e8bac702abb2cdc0212f43953b8b78ffef`. W1 branch is isolated. This is a source audit, **not** a claim of native test success.

## Existing behavior

- `FontAxisPolicy` preserves designer axis defaults, respects exact manual values, and derives automatic weight and optical size from design font and logical DPI. It does not invent `wdth` for static fonts or mistake custom `WDTH` for OpenType `wdth`.
- `FontManager::fittedText` measures Qt font advances with actual variable-axis coordinates, retains a natural-width contract, and uses a bounded 256-entry width cache. The current solver samples five 2%-of-default steps down to 90% of default, requires measured reduction, and applies a four-pixel entry/release margin and two-pixel hold band.
- `SwirlText` opts in only for unwrapped, eliding `button`, `navigation`, and `pageTitle` roles directly parented by a Qt Quick Layout. The shared `SwirlFontBinding` uses coalesced updates, not animation ticks, and the natural preferred width prevents a simple feedback loop.
- This is **not** full UI coverage: labels with no elide, non-Layout labels, text inside custom button/combo/table delegates, and animated hero titles do not automatically get the fitting algorithm. Inputs, paragraphs, numeric counters, rich text, and custom `WDTH` are intentionally excluded.
- Existing tests `automaticWidthUsesRealAdvances` and `qmlLiveAutomaticFonts` cover generated width-varying fonts, invariant advances, manual mode, hysteresis, subpixel resize, and restoration. Private PingFang and physical Windows monitor checks are separate.

## Confirmed source-level gaps and W1 boundaries

1. The five-sample scan is finite and safe but cannot find an intermediate nonmonotonic optimum outside its sampled coordinates. Never assume axis-to-advance monotonicity.
2. A bound of 90% of the axis default is **not** a bound on actual measured glyph compression; the physical advance may change disproportionately. Add a real-advance readability floor before enabling wider fitting.
3. Width fitting currently depends on role, elide, wrap, and direct parent type. Expand only where geometry ownership and stability can be demonstrated; do not indiscriminately shrink text or override explicit caller layout constraints.
4. Qt shaping/advance measurement does not prove that every fallback run or overhanging glyph ink is inside a clipped control. Test complex scripts and physical output separately.
5. No native Qt SDK or Windows session is available in this local Linux runtime. Baseline Qt tests are **not run here**. GitHub Windows workflow currently triggers only for the integration branch, so W1 CI needs an explicit branch gate before CI results can be claimed.

## Independent implementation references

- Qt: `qtbase/src/gui/text/qfontmetrics.cpp`, `qtextlayout.cpp`; `qtdeclarative/src/quick/items/qquicktext.cpp`, `src/quick/util/qquickvaluetypes.cpp`.
- HarfBuzz: `src/hb-shape.cc`, `src/hb-ot-var.cc`.
- FreeType: `src/truetype/ttgxvar.c` and public multiple-master APIs.
- fontTools: `fontTools/ttLib/tables/_f_v_a_r.py`, `_a_v_a_r.py`, `H_V_A_R_.py`.
- Existing Swirl layout approach is retained; no upstream code copied, no new dependency.

## Baseline

At audit time: zero new W1 test runs; original Qt suite status on this branch is **unverified**. Existing coverage is recorded above rather than counted as newly passed. The W1 acceptance criteria require exact source SHA and CI XML results, then physical Windows 11 scaling, typography, and 240 Hz review. No private font may enter Git.
