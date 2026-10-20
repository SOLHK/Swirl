# D1 Windows axis precision checkpoint — 2026-10-20

Branch: `work/vf-windows-d1`. Verified integration parent:
`e505326486202ad4c8e98bb8b66a17b4547c559f`.

## Scope and independently authored experiment

The dedicated workflow `swirl-vf-windows-d1.yml` runs actual Windows Server
2022/2025 with Qt 6.10.3 and an installed MSVC toolchain. Its source and result identities are
recorded separately. Windows 11 desktop, original PingFang, original TTC
installation, regional typography, real Swirl UI and physical display clarity
remain **NOT_RUN**. No qualified original `Swirl-VF.ttc` exists in this task.

No changes are made to the Apple algorithm, Rust Core, QML, FontManager or
FontAxisPolicy. The experiment uses independently authored abstract geometry
and its own file names, workflow and tests.

### Predeclared input experiment

The distinct decimal requests `499.006199` and `499.006201` both become
binary32 `499.006195068359375`, bit pattern `0x43f980cb`; local binary32 ULP is
`0.000030517578125`. Their nearest 16.16 encoding is also the same, `32702870`.
These are numerical calculations, not native rendering evidence.

The DirectWrite axis field is `FLOAT`. Qt's public setter also accepts `float`.
The file representation of `fvar` bounds as 16.16 does not by itself prove
that the Windows runtime first rounds every user request to 16.16.

Two original synthetic fonts and 28 frozen requests separately test the
input collision, nearby binary32 values, broad axis controls and narrow avar
intervals. Below 128 the fixture contains distinct binary32 requests that
round to the same declared 16.16 value. The amplified fixture distinguishes
predeclared continuous, user16, normalized16 and normalized14 hypotheses;
the predictions are not substituted for measured Windows values.

### Independent native observables

DirectWrite records requested decimals, binary32 values/bits, native API
readback, complete outline operations with unrounded coordinate bits,
integer design metrics, natural fractional glyph placement and eight actual
alpha rasters per position. It compares complete payloads in reversed order,
not only API readback or hashes. Forward/reverse executable processes and
file/system-collection modes are separate. Actual installed resources must
match the source table bytes.

Qt records QFont requested-axis storage explicitly as request storage. It
independently measures QRawFont paths/advances, QTextLayout runs, font
metrics and QPainter pixels, at multiple point sizes, logical DPIs and DPRs.
Private-font remove/reload, missing-load handling, reversed requests and
actual-font table identity are checked. Both `windows:fontengine=native`
and `windows:fontengine=freetype` are requested. Qt 6.10.3 does not recognize
`fontengine=directwrite`; that spelling would not establish a backend.

### Validation completed before native execution

12/12 original-fixture Python tests passed locally with fontTools 4.61.1.
These include serialized table consistency, HVAR/phantom consistency,
deterministic font bytes and 18 saved static-instance checks. The Linux
DirectWrite placeholder was compiled and correctly returned 77/NOT_RUN;
it is not a Windows result. Native compile/run results must be appended
with the exact pushed source SHA and actual Actions run/job links.

## Stage 1: real Windows results and preserved failures

Source commit: [`562cbc998d03ad36c7e8b25fa7c614a3b17168ae`](https://github.com/SOLHK/Swirl/commit/562cbc998d03ad36c7e8b25fa7c614a3b17168ae).
Actions run: [`39399001699`](https://github.com/SOLHK/Swirl/actions/runs/39399001699),
final conclusion **failure**. This is not a fully passing D1 certification.

| Actual runtime | Native outcome | Unresolved first-run result |
| --- | --- | --- |
| Windows Server 2022 Datacenter, build 20348, dwrite.dll 10.0.20348.1 | All eight DirectWrite processes passed; 448 complete observations. Four Qt native processes passed their within-process gates. | All four Qt FreeType processes failed a strict outline equality check. Qt independent reverse order was not actually selected. |
| Windows Server 2025 Datacenter, build 26100, dwrite.dll 10.0.26100.1 | No native measurements executed. | The image provides Visual Studio 2026, while the initial script requested Visual Studio 2022. |

Server 2022 job: [`118548723590`](https://github.com/SOLHK/Swirl/actions/runs/39399001699/job/118548723590).
Server 2025 job: [`118548723271`](https://github.com/SOLHK/Swirl/actions/runs/39399001699/job/118548723271).
Server 2022 artifact ID: `12254410614`; ZIP SHA-256:
`9c84239a7b50044730b311c49a8a589880214e8b905754baa7aeaff8bfdfcdeb`.
The downloaded eight DirectWrite JSONL files were independently parsed and
validated against the frozen request manifest, including complete 28-by-2
case/pass matrices. Installation and cleanup both completed for both fixtures.

### Actual DirectWrite measurements

Each row below was observed in direct-file and installed-system-collection
modes, in independent forward and reverse processes. Advance is measured at
em size 1000; outline rightmost coordinates are in the same design-unit scale.

| Fixture / input | A design advance | A natural advance | A outline rightmost |
| --- | ---: | ---: | ---: |
| ordinary / 499.006199 | 636 | 636 | 536 |
| ordinary / 499.006201 | 636 | 636 | 536 |
| gain / 499.006199 | 19000 | 19000 | 18060 |
| gain / 499.006201 | 19000 | 19000 | 18060 |
| gain / adjacent binary32 below and above the pair | 19000 | 19000 | 18060 |
| gain / 100.00000762939453125 | 4000 | 4000 | 3060 |
| gain / 100.0000152587890625 | 4000 | 4000 | 3060 |
| gain / 498.9990234375 | 16000 | 16000 | 15060 |
| gain / 499.0142822265625 | 22000 | 22000 | 21060 |
| gain / 499.029541015625 | 28000 | 28000 | 27060 |

For the original precision pair, complete raw outline operations, design
metrics, natural placement and actual alpha-raster bytes were equal. This
conclusion is not inferred from equal axis readback. All three axis endpoint
controls changed real outlines and pixels; the horizontal weight/width
controls also changed advances. HGHT intentionally preserves advance.

For the gain fixture's 28 predeclared requests, the normalized16-before-avar
model has maximum advance and rightmost-outline residual **0**. The continuous
and user16-then-continuous models retain maximum residual about **204 FUnit**;
the normalized14-before-avar model retains **6000 FUnit**. This distinguishes
these particular hypotheses on this finite fixture. It does not expose or
prove the full proprietary Windows implementation. The ordinary fixture
retains a maximum **0.3603515625 FUnit** residual in the unrounded analytical
models; that residual is not silently relabeled a 1/32-FUnit pass.

Native readback is a separate observation: input `100.00000762939453125`
reads back as `100.0000152587890625`, the same value returned for the latter
input. This is compatible with user-coordinate 16.16 canonicalization for
this control. A zero residual in the normalized16 hypothesis does not rule
out a combined user16-then-normalized16 path; that combination was not a
distinct member of the four initially frozen models. Neither readback nor
the `fvar` storage format alone identifies the full rendering pipeline.

### Qt failure interpretation and next executable checkpoint

The first Qt native runs measured paths, advances, metrics, layout and pixels
at all 24 size/DPI/DPR scenarios. However, QGuiApplication consumes `--reverse`
as its own layout-direction argument: both independent headers reported
`reverse=false`. Only the within-process reversed replay was established.
The probe now uses `--reverse-order`, and the independent analyzer binds that
header to the process label so this cannot become an unnoticed false pass.

All four first-run FreeType logs stopped at the first 9-point, 96-DPI, DPR-1
pair check. Twenty path-coordinate fields changed by exactly **1/64 pixel**;
raw advances, QFontMetricsF, glyph IDs/positions, layout advance and painted
pixel hashes were equal. The layout comparison failed because it also
contains glyph outlines. Equal binary32 input cannot establish retained
decimal precision from this path discrepancy. The next checkpoint launches
a separate diagnostic child after failure to locate path state changes; the
primary cold observations, exact comparison and failed exit status remain.

The next checkpoint also discovers the actual VS 2022/2026 installation,
uploads raw native raster evidence, and compiles the unchanged production
`FontAxisPolicy.cpp` into the standalone Qt probe. Its 36 policy checks cover
automatic weights 400/600, 96/144/192 DPI, DPR 1/1.25/1.5/2 and explicit
case-sensitive WDTH/HGHT settings. They are not yet a real Swirl UI or original
TTC acceptance result. The local fixture/evidence regression suite is 31/31
at this checkpoint; new native outcomes must be appended after CI completes.

## Stage 2: both Windows runtimes executed; FreeType state isolated

Source commit: [`47d6dfc06fa2fddddd1532c1d8370028a6b9da17`](https://github.com/SOLHK/Swirl/commit/47d6dfc06fa2fddddd1532c1d8370028a6b9da17).
Actions run: [`39400461390`](https://github.com/SOLHK/Swirl/actions/runs/39400461390),
final conclusion **failure** because the strict FreeType path checks remain
failed. Both operating systems now configured, compiled and executed the full
16-process harness. No equality threshold or original acceptance gate changed.

| Runtime / job | Actual compiler | DirectWrite | Qt native | Qt FreeType |
| --- | --- | --- | --- | --- |
| Server 2022 build 20348 / [118553585274](https://github.com/SOLHK/Swirl/actions/runs/39400461390/job/118553585274) | VS 17 2022, instance 17.14.37710.0 | 8/8 processes, 448 observations | 4/4 processes, 3120 observations | 4 strict failures, each after 13 observations |
| Server 2025 build 26100 / [118553585584](https://github.com/SOLHK/Swirl/actions/runs/39400461390/job/118553585584) | VS 18 2026, MSVC 19.51.36260.0, v145, SDK 10.0.26100.0 | 8/8 processes, 448 observations | 4/4 processes, 3120 observations | 4 strict failures, each after 13 observations |

Both runtimes used Qt 6.10.3 and passed 31/31 Python checks. DirectWrite DLL
versions were respectively 10.0.20348.1 and 10.0.26100.1. Qt reverse headers now
actually report `reverse=true`. Every successful Qt process executed the 36
production-policy combinations; private processes also executed remove/reload
and missing-file fallback controls. Both fonts' installation cleanup passed
on both VMs. Windows 11 client and actual Swirl UI remain unexecuted.

Downloaded ZIP identities:

| Runtime | Artifact | SHA-256 |
| --- | --- | --- |
| Server 2022 | [12254492969](https://github.com/SOLHK/Swirl/actions/runs/39400461390/artifacts/12254492969) | `e01ba6a4b6a26fa88c9da81a87c9a4bb105b6e41da5c2c2ada7293694dbbcab4` |
| Server 2025 | [12254657939](https://github.com/SOLHK/Swirl/actions/runs/39400461390/artifacts/12254657939) | `365110cfb1a998aa1eb534454f5a527ac94cd1bf9ab8e16d227ee5029c6961e5` |

Independent cross-OS comparison found zero differences in all 448 DirectWrite
and 3120 Qt native corresponding observation payloads, including their raster
hashes. These counts compare the two OS datasets; they are not extra executions.
The saved native binary rasters and derived PGM images were independently
checked against the JSONL: 32 of each per OS. All 1300 primary Qt PNGs and 12
path-state diagnostic PNGs per OS were decoded back to BGRA bytes and matched
their recorded pixel hashes exactly.

### Fixed input changes its path after rasterization

All eight fresh FreeType diagnostic children (two OS versions, private and
installed loading, both parent orders) measured the same sequence. With one
existing QRawFont and unchanged `499.006199` request:

| Observation checkpoint | A rightmost x, pixels |
| --- | ---: |
| Before and after raw advance query | 6.421875 |
| After raw path, metrics and text-layout extraction | 6.421875 |
| Immediately after painting the text layout | 6.4375 |
| After reacquiring QRawFont | 6.4375 |
| Repeating the identical decimal 499.006199 | 6.4375 |
| Then requesting 499.006201, the same binary32 value | 6.4375 |

All three diagnostic requests retain A advance `7.625` pixels and identical
pixel SHA-256 `2e9e40bf767345167f349239150f93b16867d4201e6bd39526617f52f76378e1`.
The primary forward and reverse tests also swap which decimal receives the
first path value. This establishes render-history dependence without changing
the decimal or axis input. It cannot be used as evidence for extra precision.

The Qt 6.10.3 source supplies a plausible mechanism: FreeType raster loading
sets a subpixel translation with `FT_Set_Transform`; the subsequent unscaled
path extraction resets that transform only when its matrix differs, leaving
a same-matrix translation potentially active. This remains a source-backed
mechanism hypothesis until the focused offset diagnostic is executed; the
observed before/after path change itself is already established.

At the integration baseline, `FontRendering.h` explicitly requests
`windows:fontengine=freetype` before QGuiApplication. This makes the finding
relevant to Swirl's backend foundation, but the probe does not establish a
visible UI regression: its measured raster and advances did not change. It
also does not authorize silently switching the production backend, whose
existing comment documents a fractional-DPI rendering reason for FreeType.

Stage 3 adds a separate fixed-QRawFont/single-glyph fractional-offset
diagnostic, with no primary warm-up or relaxed equality. It also retains
individually source-bound valid subprocess evidence when the overall strict
analysis fails. Partial evidence must keep failed global status and exit 1.
The stage-3 local suite passed 37/37 tests. Against the actual stage-2 artifacts,
the partial collector retained exactly 12 complete processes / 3568 observations
per OS, rejected the four FreeType failures, and verified six opposite-order
and three private/installed comparisons. It also corrected its representation
check for an empty Qt path: a single MoveTo at the origin is empty according
to QPainterPath::isEmpty. No real path equality comparison was weakened.

## A3 target-input finding

For the current public DirectWrite FLOAT axis API and Qt float setter, the
mapping from these two requested decimals to API input is non-injective:
both have bit pattern `0x43f980cb`. A deterministic target using only those
unchanged public axis inputs cannot choose two different outputs based on
the discarded decimal distinction. The synthetic Windows results above
confirm actual collapse for this experiment; they do not certify PingFang.

The integration handoff reports a CoreText source advance difference of
`0.5474853515625 FUnit` for GID 5. Combining that source observation with the
input collision yields the conditional error lower bound
`0.27374267578125 FUnit`, or `8.759765625 * (1/32 FUnit)`, for at least one
request if a single deterministic target output must approximate both.
This is an A3 blocker for the unchanged-axis float pipeline, not a proof that
every possible coordinate remapping, discrete glyph representation or custom
renderer is impossible. No alternate precision-preserving target mechanism
has been validated in this D1 experiment. Source-side mechanism investigation
and any changed-coordinate contract remain separate work.

## Primary references reviewed before implementation

- [Microsoft axis value type](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/ns-dwrite_3-dwrite_font_axis_value)
- [Microsoft arbitrary-axis face creation](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontresource-createfontface)
- [Microsoft glyph placement](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritetextanalyzer-getglyphplacements)
- [Microsoft DWriteCore design and font selection examples](https://github.com/microsoft/WindowsAppSDK/blob/main/specs/dwritecore/DWriteCore.md)
- [Qt 6.10.3 DirectWrite font database](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/windows/qwindowsdirectwritefontdatabase.cpp)
- [Qt 6.10.3 QFont implementation](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/qfont.cpp)
- [Qt 6.10.3 Windows platform parameter parsing](https://github.com/qt/qtbase/blob/v6.10.3/src/plugins/platforms/windows/qwindowsintegration.cpp)

These references informed API use; the D1 experiment code and font geometry
are original. No proprietary font payload is committed or uploaded.
