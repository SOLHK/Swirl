# P6 native rounding checkpoint (2026-10-21)

Branch: `work/vf-takeover-abc-20261021`; parent checkpoint
`9fff65027d6642f78f793150254c20e13e7ada2c`. PR #24 remains draft.

## First executable fix

`exact_rebase` reuses the existing bounded rebase engine and requires zero
error in the independent certificate of the serialized/reopened continuous
gvar/HVAR/VVAR models. It does not change the existing bounded selection,
1/32 limit, native gates, original data or production builder permission.

For the authored source UPEM1000, weight coefficient1, clipped weight span3/16,
the first exact legal integer multiplier is16 (UPEM16000). At GID2,
q=(63/16384,3/16,0), r=(63/16384,1,0), the old5x model error1/80 and
HarfBuzz advances18714/18726 become exact model error0 and advances18720/18720
at the unchanged physical output scale64000 (64 units/source FUnit).
This removes a coefficient-induced rounding mismatch for this case. It is
not a proof of native parity throughout the parameter domain or of original
Apple font conversion. User-coordinate quantization remains separate.

At source UPEM1144 this fixture needs16x but only14 integer multipliers are
legal: the new path explicitly refuses every approximate grid. This is a
restriction of this representation, not a universal OpenType impossibility.

Local targeted tests: `test_exact_rebase.py`2 PASS and unchanged
`test_bounded_rebase.py`7 PASS. Native Windows/CoreText trace and exact
rounding-bound evidence are the next checkpoint; NOT_RUN for this new path
at this checkpoint. All P5 strict native failures remain recorded.

Primary implementations reviewed before the fix:

- [HarfBuzz14.6 hmtx/HVAR](https://github.com/harfbuzz/harfbuzz/blob/14.6.0/src/hb-ot-hmtx-table.hh)
- [HarfBuzz14.6 font advance callbacks](https://github.com/harfbuzz/harfbuzz/blob/14.6.0/src/hb-ot-font.cc)
- [fontTools public instancer](https://github.com/fonttools/fonttools/tree/4.61.1/Lib/fontTools/varLib/instancer)
- [OpenType head UPEM range](https://learn.microsoft.com/en-us/typography/opentype/spec/head)

No upstream code is copied. Only authored control fonts are used. Original
first-face reconstruction remains blocked; no `Swirl-VF.ttc` is produced.
Windows11, Qt/Swirl and third-party application acceptance are NOT_RUN.

## Saved fix and native rounding diagnostics

First fix saved/pushed as `5dce5e0d0df357961ae28325348341d788f0d308`.
Its existing regression workflow passed; its unchanged P5 strict Windows gate
still failed as expected on the original5x controls. No failure was removed.

`native_rounding.py` independently models the pinned HarfBuzz14.6 metric path:
round the interpolated HVAR delta with `roundf` in font design units, add the
integer base, clamp, then apply the font's binary32-derived fixed16 output
multiplier and round to the requested integer output scale. It does not
emulate every VarStore floating operation or any proprietary engine internals.
The reference is checked against actual serialized self-authored fonts.

At the old5x GID2 witness, base1460 plus deltas2535/1024 and2599/1024 gives
integer design advances1462/1463. Their physical difference is1/5 source
FUnit. With scale64000/UPM5000 the fixed16 multiplier is838860 and outputs
18714/18726 differ by3/16 source FUnit. This is two-stage native rounding,
not a1/5 coefficient error. The actual decoded model difference is1/80.
HarfBuzz output units are caller-selected; scale64000 specifically makes
one output unit1/64 of a source FUnit. They are not intrinsically device pixels.
Actual floating HB outline callbacks differ by about1/80 here; integer
glyph extents and integer advances are separate API outputs.

### Remaining real nominal-coordinate counterexample

The16x coefficient fix has zero continuous coefficient error, but remains
strictly unaccepted. The fixed nominal request is:

```
WDTH=534.820556640625, wght=689.1845703125, HGHT=834.320068359375
source q F2 integers = [1141,1453,10955]
actual HB target post-avar r F2 integers = [1141,7749,10955]
```

The endpoint decode of target r shifts source weight q by−1/16 of one F2
integer (physical metric difference−1/262144 source FUnit). Actual serialized
HVAR deltas at UPEM16000 are417333333/4194304 and417333077/4194304, on opposite
sides of99.5; native rounding gives100/99. HB at scale64000 returns19088/19084,
an unchanged strict failure1/16>1/32. This tests real nominal inputs through
the compiled avar, separately from an additional direct-normalized-setter
counterexample retained in the tests. No global inverse mapping is claimed.

Conditional mathematical bound: for SAME-UPM nonnegative advances with no
overflow and a persistent gap of at least one integer design unit, the pinned
HB output gap is at least floor(multiplierFixed16/65536) output units. Exact
arithmetic over all16,369 legal integer UPEM values16..16384, including
noninteger source/target ratios, gives a minimum3/64 source FUnit at source
UPM1000 and output scale64000. This rules out merely hiding a retained
threshold mismatch by raising UPEM under that contract. It does NOT establish
that every font representation must retain a mismatch, or cover different-UPM
font pairs. Raising the reference's UPEM changes its native contract too;
same-UPM authored controls are not original-native conversion acceptance.

### Actual local macOS measurements

The new Swift probe uses public CoreText variation attributes, binds the
physical font and actual post-GSUB CTRun to table bytes, and keeps axis echo
failures separate. On local macOS26.3, source UPEM1000 physical normalization,
sizes12/48/1000/5000, each case has16 measurements and8 exact reverse replay
pairs. Against the matching authored one-face files:

| Case | Maximum advance difference | Maximum outline point distance |
| --- | ---: | ---: |
| old5x coefficient witness |0.0125|0.0125|
| exact16x coefficient witness |0|0|
| exact16x real nominal F2 witness |1/262144|0|

Baseline font metric differences are0. Horizontal text maps to GID2; authored
vertical GSUB deliberately maps to GID3 and is recorded separately. Native
post-avar coordinates are NOT_OBSERVED in CoreText; supplied mathematical
coordinates and decimal axis echoes do not establish its internal coordinates.
No tracking or application positioning correction is applied. All sources
remain unchanged. Device raster/pixel equivalence is NOT_RUN in this probe.

Local targeted regressions: rounding11, exact-rebase2, CoreText protocol4 PASS;
old bounded7 already passed after its source refactor. Non-Windows C++ stub
compiles with `-Wall -Wextra -Werror`; this does not compile the Windows body.
`make_rounding_controls.py` actually serializes and independently verifies
one-face TTCs via the existing C1 packer and runs HB at four output scales.

The new focused P6 workflow measures these same two requests on macOS and
Windows Server2022. It preserves the original5x failure, verifies the narrow
coefficient fix, then separately enforces the unchanged1/32 gate on the new
nominal witness. Actual Windows results will be appended after execution.
Only fixed authored aggregate reports are exported, never font binaries,
Apple data or arbitrary logs. Existing P5/original gates are unchanged.

Local private authored controls: `build/vf-takeover-private/p6/controls-stage3`.
Raw synthetic diagnostics: `build/vf-takeover-private/p6-coretext-public-*`.

Native/API references:

- [HarfBuzz14.6 scaling](https://github.com/harfbuzz/harfbuzz/blob/14.6.0/src/hb-font.hh)
- [DirectWrite design glyph metrics](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getdesignglyphmetrics)
- [DirectWrite glyph metric field units](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_metrics)
- [DirectWrite floating outline API](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getglyphrunoutline)
- [Apple advance API](https://developer.apple.com/documentation/coretext/ctfontgetadvancesforglyphs(_:_:_:_:_:))

Production remains closed: source-only replay cannot authorize target building;
original source-to-target user mapping and strict native parity remain
unaccepted. General original HVF extraction/model certification, unsupported
hinting/table semantics, MVAR reparameterization and full VORG/native behavior
still need their existing gates. Original first face is NOT_BUILT; original
32-face TTC, Windows11, real Qt/Swirl and third-party software are NOT_RUN.

## Actual native checkpoint e003a16

Saved/pushed `e003a164135dd8eb5a12b7e1f2b20a02a7f137ad`.
[P6 CI39578993915](https://github.com/SOLHK/Swirl/actions/runs/39578993915):
exact-reference PASS, CoreText PASS, Windows-native FAIL specifically at the
unchanged strict nominal-witness gate after successful compilation, all four
native diagnostics and the narrow coefficient-fix assertion.
[Existing CI39578993738](https://github.com/SOLHK/Swirl/actions/runs/39578993738)
also passed all three jobs; it was automatically triggered by source changes.

Actual Server2022/10.0.20348 results (self-authored GID2 only):

| Case | Integer advanceWidth pair | Single upright point difference at em=UPM | Strict |
| --- | --- | ---: | --- |
|5x old witness|1462/1463|0.2 source FUnit|FAIL|
|16x old witness|4680/4680|0|PASS|
|5x new nominal witness|1491/1491|0|PASS|
|16x new nominal witness|4772/4771|1/16 source FUnit|FAIL|

Every diagnostic checked14 integer metric fields,36 outline runs and240 point
pairs with zero topology failures. Six em sizes were used: fontUPM,1000,
1000.5,12,12.5,16.25 DIP, each with upright/sideways single-glyph, repeated
implicit-advance and repeated explicit-integer-advance runs. Old5x has2 metric
field failures and204 point-pair failures; new16x nominal has2 and124.
Repeated glyphs accumulate both outline and advance differences: maxima are
0.40006852042728636 and0.12500469501201922 respectively after physical
normalization. These are floating geometry results, not raster pixel errors.
At em=UPM the new nominal repeated horizontal translation is4772/4771 target
units; vertical translations agree. DWrite native post-avar coordinates and
its proprietary internal operation order remain NOT_OBSERVED. Actual integer
design results match the independent threshold calculation; that does not
prove DWrite implements HarfBuzz's source code or every tie rule.

P6 CoreText CI actually ran macOS15.7.9/build24G830, distinct from the local
macOS26.3 and the existing macOS27 original-source workflow. All four authored
cases completed; the important exact16 nominal advance error remains1/262144,
outline error0. Windows11 and original converted-font acceptance remain NOT_RUN.

## Alternative representation experiment: unchanged source grid

The new source-contract regression explicitly compares the unscaled authored
UPM1000 reference to the16x target: HB18688/18720, difference1/2 source FUnit.
Thus changing BOTH reference and target UPEM for coefficient isolation does
not establish preservation of the original reference's native API contract.
That failure is now executable and retained, as are all earlier failures.

`avar2_rounding_control.py` is a tightly restricted seven-glyph authored
compatibility fixture, not a converter or production option. It keeps UPEM1000
and raw glyf/gvar/HVAR/VVAR/hmtx/vmtx/cmap bytes unchanged. Existing compiled
staircase segment maps embed source integer q into r, then a post-segment
avar2 VarStore contracts weight by3/16 and rounds back to integer q. Because
the decode error bound is3/32 of ONE F2 integer (<1/2), this recovers every
integer q in[-3072,3072]. It avoids rounding fractional rebased coefficients.

Actual HB14.6 tests: all6,145 integer q recoveries, all32,769 nominal F2 weight
inputs and three mixed nominal cases pass. All seven GIDs' H/V advances and
extents agree at those three cases, and the native UPEM remains unchanged.
Local CoreText actually completes both principal cases with zero advance,
outline and baseline differences at all four sizes (16 records/8 exact reverse
pairs per case). Post-avar coordinates remain opaque there.

This does not prove between-grid binary64 input equivalence, full original
axes, original glyphs or Windows compatibility. The Microsoft published
[OpenType1.9.1 avar page](https://learn.microsoft.com/en-us/typography/opentype/spec/avar)
documents v1. The [HarfBuzz avar2 design](https://github.com/harfbuzz/boring-expansion-spec/blob/main/avar2.md)
and fontTools public builders inform this independent experiment. ISO OFF
[edition5 was published July2026](https://www.iso.org/standard/14496-22), but
its final avar2 text has not been inspected; no unsupported claim of universal
standard compliance is made. The dated [Google Fonts support matrix](https://googlefonts.github.io/how2avar2/docs/support/)
is a reason to test current native engines, not evidence of this candidate's
DirectWrite behavior. Windows/CI results for this new alternative are pending
at this checkpoint. COMPATIBILITY remains NOT_VERIFIED and production false.
