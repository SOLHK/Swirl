# SwirlVF root-cause continuation — 2026-11-02

**PARTIAL / BLOCKED. No generated or accepted SwirlVF.ttc exists.** This
continues [PR 49](https://github.com/SOLHK/Swirl/pull/49) from `7736c6c`, without
rewriting history. Tested engineering head:
`3c2ed586e15d6efee5e77d50e494715901f1a8d2`; tested PR merge tree:
`fd3e5a2eb6737da4bb62e049b7a0bfab2f459a8b`. Later evidence/CI metadata commits
do not retroactively change those identities. The
[aggregate evidence](evidence/SWIRL_VF_ROOT_CAUSE_20261102.json) records hashes,
counts, environments, native failures and CI identities. Raw outlines, copied
fonts and full logs remain private, outside Git.

The later strict product-entry execution is pinned separately to
`cfebb62ec56c7ba3677a927091ba48d7cd562f5b`, PR merge checkout
`09a83263d6de77411d1c3a9a40424c6d0a4f3167`. Its
[strict-build evidence](evidence/SWIRL_VF_STRICT_BUILD_20261102.json) records the
actual original-font attempt, compiler/tool hashes and completed CI results.

## System font reading and CoreText 103

Actual enumeration on macOS 26.5.1 found 631 PostScript names, 655 descriptors
and 48 PingFang descriptors. Resource URLs came from CoreText and a filesystem
scan, not a fixed PingFang pathname. Scan errors are recorded; discovery is not
claimed exhaustive through inaccessible directories. Every tested file was
readable and independently parsed with fontTools and HarfBuzz.

| Resource | Version | Bytes | Faces × GIDs | Format | Local native identity |
| --- | --- | ---: | --- | --- | --- |
| Supplied original | 22.0d5e2 | 61,473,880 | 32 × 47,102 | HVGL | 0/32 |
| System UI font | 21.4d1e1 | 61,080,840 | 32 × 47,098 | HVGL | 32/32 in system location |
| Supplemental font | 21.0d1e1 | 78,222,888 | 24 × 49,533 | static CFF | 24/24 |

Original SHA-256:
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
System UI SHA-256:
`13b201d63324db59de86956c11c46d1f0ad9ac0aeaa0b9d035c012a794062db7`.
Supplemental CFF SHA-256:
`9ff3ce9439fe285cdabb46f9ceb46b1ac58f1ca07e6f4a764e8286db621a0af9`.
These are different versions, not interchangeable references. The supplied
source and private backup remain mode 0400 and hash-identical after testing.

The system UI file exposes 268 URL descriptors and binds all 32 physical faces
by exact table identity. Its **byte-identical private copy** exposes zero URL
and data descriptors, no CGFont, and registration error 103. The CFF font loads
both in place and as a copy. The existing authored two-face standard variable
TTC also loads and registers. All registration is process-scoped, with cleanup.

An independent **macOS 27.0.1 (26A434)** environment was actually executed:
historical replay job
[125015443995](https://github.com/SOLHK/Swirl/actions/runs/39392843518/job/125015443995),
then current-code run
[41362777539](https://github.com/SOLHK/Swirl/actions/runs/41362777539).
Dynamic discovery found the **exact original SHA**, and CoreText verified
**32/32 faces**. Its identical private copy again returned **0/32 and 103** on
the same OS. The current source job remains failed because only **288/384**
strict axis requests pass; 96 exceed the unchanged 1e-6 readback condition.

A minimal authored control has one face, two glyphs and all three axes. Its
SFNT directory, table bounds, alignment, non-overlap and table/file checksums
pass. Names, cmap, metrics and fvar/avar bytes are unchanged between controls.
Standard glyf/loca/gvar and combined standard + HVGL versions load; HVGL-only
returns 103. These are format diagnostics, not converted or release fonts.

**Conclusion:** system font reading works. The local 0/32 failure is at source
loading, before conversion writes a candidate. Same-byte location controls
establish a location-dependent native HVGL loading boundary, rather than a
TTC-index, read-permission or conversion-serialization defect. Apple's private
routing/cache/policy implementation has not been proven. Correct independent
resident-source access restores the reference, but axis and metric failures
remain. Failure cannot be explained solely by not finding a system reference.

## The 849/850 precision failure

This is **vertical advance 849 versus expected 850**, not 849 passing tests
out of 850. The unchanged current gate fails at authored fixture face 0,
GID 2, `WDTH=1, wght=100, HGHT=1`, UPEM 1000. Fixture SHA-256:
`783625f70991f80584e88fdbef6f8db169c669081f38c22dc989fff46d28c3eb`.

Serialized gvar decoding gives top phantom Y 760 and bottom phantom Y -90,
hence advance 850. HarfBuzz returns 850; CoreText returns 849 through raw
vertical CGSize.width. All outline control points match exactly, the
quadratic extremum is correct, axis readback equals the request, avar is
identity, and all point deltas are explicit: **IUP is not involved**.
The value matches the existing frozen 16.16-floor-then-integer hypothesis;
this is not proof of Apple's internal arithmetic.

The failure is isolated to native metric evaluation of this gvar-phantom
encoding. [VVAR is optional for TrueType variable fonts](https://learn.microsoft.com/en-us/typography/opentype/spec/vvar),
so the baseline is not invalid merely because VVAR is absent. Equivalent
production HVAR/VVAR fixes integer endpoints but leaves fractional vertical
advance error **0.3375 FUnit**, above **1/32 = 0.03125**.

The current macOS 26.6.2 CI all-metric diagnosis has 106/174 gvar-only
observations outside budget and 6/174 for either metric-table variant. Those
diagnostic counts include blank-glyph origins beyond the original gate's
checks; they are not that gate's pass/fail count. No expected value, tolerance,
sample count, source metric or failed assertion changed. The complete precision
problem is **not fixed**. Existing nonempty-glyph model failures and integer
grid limitations in the earlier
[interpolation evidence](evidence/SWIRL_VF_INTERPOLATION_20261102.json) also remain.

An additional build-entry defect was found during continuation: the historical
`rebuild.py` CLI exposes only its 1-FUnit experiment defaults. The new
`build_swirlvf.py` entry delegates to the same engine with fixed **1/32** outline
and metric limits and a required source SHA. The cubic approximation parameter
now reaches the engine and checkpoint recipe; its 1/64 allowance is charged to
the total 1/32 outline bound. Historical experiments and expected values remain
unchanged. A real serialization regression shows the same 0.25-unit authored
error passing the historical budget and failing the strict entry without an
output file. Complete exact authored and cubic controls pass. This fixes budget
selection, not the remaining original-font representation failures.

The fixed entry was actually executed against the exact resident original on
macOS 27.0.1 / Xcode 27.1 / SDK 27.0 in
[run 41365043273](https://github.com/SOLHK/Swirl/actions/runs/41365043273).
Compilation succeeded. The existing verified-axis adapter admitted **all 91
initial batches / 5,824 observations** using exact per-GID native replay.
All 32 source identities matched. The converter exited 2 at **face 0 / GID 0**,
training sample 1: `WDTH=1, wght=501, HGHT=500`. Native vertical-origin X differs
from `horizontal_origin_x + advance_width/2` by **100 FUnits**. The existing
1e-5 representation guard and new total 1/32 budgets remain unchanged. No glyph
model or face completed and no output was written; source SHA stayed identical.

This independently reproduces the historical vertical-origin blocker after
correct source access, with the current strict builder. It is not caused by
CoreText 103 or a missing system reference. The existing vmtx/phantom encoder
cannot express that independent X origin. Historical variable GPOS experiments
also measured engine-dependent residuals above 1/32; they are not an accepted
replacement. Neither the native source metrics nor the gate was rewritten to
force this model through.

## Complete GID extraction and implemented changes

The new resumable driver completed **47,102 GIDs × 27 design locations =
1,271,754 native records**, across **1,242 chunks**, with zero failed chunks.
Every chunk validates the ordered GID interval, requested coordinates, axis
application, finite coordinates, closed paths, balanced component callbacks,
counters and terminal receipt. Empty measured glyphs are retained. Duplicate
or missing GIDs cannot pass by matching counts. The actual run stopped after
its first chunk and resumed with hash-verified reuse.

This covers **face 0 at the declared 27-point design grid**. All 32 faces share
the same HVGL byte range; that does not establish all-face user-coordinate or
metric equivalence. Continuous interpolation, metrics and complete model
serialization are not certified. Historical 228 experimental models are
preserved but are not production acceptance. Accepted production faces: **0/32**.
The private resumable corpus is `private/root-cause-20261102/full-gid-grid`
outside the repository, bound to source, native binary, code and output hashes.

| Changed path | Purpose |
| --- | --- |
| `tools/swirl_vf/platform/diagnose_font_sources.py` | Native discovery, independent parsing, exact-face identity and same-byte copy controls |
| `tools/swirl_vf/platform/diagnose_coretext_formats.py` | Minimal authored outline-format isolation and SFNT validation |
| `tools/swirl_vf/platform/hvf_transcript.py` | Reject incomplete, duplicate, reordered, malformed or nonfinite native evidence |
| `tools/swirl_vf/platform/run_hvf_oracle.py` | Replace count-only admission with complete transcript validation |
| `tools/swirl_vf/platform/hvf_coverage.py` | Locked, resumable all-GID batches and persistent receipts |
| `tools/swirl_vf/tools/build_swirlvf.py` | Fixed 1/32 product entry with mandatory source hash |
| `tools/swirl_vf/tools/rebuild.py` | Carry cubic allowance into the shared engine and checkpoint recipe |
| `tools/swirl_vf/platform/attempt_strict_rebuild.py` | Bounded actual strict reconstruction with private data and safe CI aggregates |
| `tools/swirl_vf/tests/test_strict_build.py` | Actual serialization, budget, source-hash and privacy regressions |
| `tools/swirl_vf/tests/test_font_source_diagnosis.py` | Source, copy, privacy and format regressions |
| `tools/swirl_vf/tests/test_hvf_transcript.py` | Coverage, failure, empty-glyph and callback regressions |
| `.github/workflows/swirl-vf.yml` | Add authored format diagnosis while preserving the strict failing gate |
| `.github/workflows/swirl-vf-source-diagnosis.yml` | Current-code exact-resident-source CI and version evidence |
| `.github/actionlint.yaml` | Declare the additional runner label verified by actual execution |

Rust, TUN, proxy, gateway, activities and QML behavior are untouched. No branch
was force-pushed and no unrelated history or implementation was overwritten.

## Acceptance and delivery status

| Requirement | Actual result |
| --- | --- |
| Local Python after strict entry fix | 914 tests, zero failures, seven platform skips; six audit tests pass |
| CI Python at cfebb62e | 914 tests, zero failures/skips; six audit tests pass |
| Changed workflows / whitespace | actionlint and `git diff --check` pass |
| macOS strict fixture | FAIL: 849 versus 850 at unchanged 1/32 |
| Exact-original independent macOS | 32/32 identities; 288/384 strict axes; overall gate FAIL |
| Exact-original strict reconstruction at cfebb62e | 91/91 native batches; exit 2 at face 0/GID 0 vertical-origin X, 100 FUnit representation error; no output |
| DirectWrite | Authored standard and production HVAR/VVAR fixtures PASS on Windows Server 2022 build 20348; all glyphs and 100–200% DPI captures |
| Qt 6.12 Windows CI | CTest 3/3; 62 passes, nine declared skips, zero gate errors; authored fonts only |
| Earlier full-app push | Run 41336471755 at 7736c6c completed full application compilation and isolated authored-font navigation smoke successfully |
| macOS Qt | Retained Qt 6.12 CTest 2/2, 61 passes, nine optional skips; software/offscreen scope |
| Final-font Windows 11 x64 / installation | NOT_RUN; no final font or accessible Windows 11 x64 machine established |
| Final-font Qt / native rendering | NOT_RUN |
| Font grant | Modification/conversion/cross-platform/public-distribution scope not verified: no separate grant document found in available project material |
| SwirlVF.ttc | Not generated; size and SHA-256: N/A |
| test merge / remote font SHA / post-merge CI | Not performed; gates remain failed or unrun |

GitHub's [regular-file policy](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
warns above 50 MiB and blocks above 100 MiB. The repository ignores `*.ttc`
and has no TTC LFS rule. With no candidate file there is no actual size on
which to base that decision. Font-data guards remain intact. No font binary,
authorization document, private log or credential was published; the owner's
oral authorization is not being requested again.

The intended product path remains `output/SwirlVF.ttc` in the private project
directory outside this checkout, currently absent.
Development branch: `work/swirlvf-delivery-20261102`; PR 49 remains draft.
`test` is unchanged. This report and the completed source-extraction corpus
are engineering progress, not a substitute for the missing formal font.

## Architecture continuation after c824c2ee

Status remains **PARTIAL / BLOCKED**, with no accepted `SwirlVF.ttc`.
The original input hash is unchanged. The current continuation implements a
fractional CFF2 geometry backend, an explicit CFF2 vertical-metric bridge and
additional native gates. The existing TrueType builder, source-identity checks,
axis validator, 1/32 precision assertions and failing legacy fixture remain.
The aggregate receipt is
[SWIRL_VF_CFF2_ARCHITECTURE_20261102.json](evidence/SWIRL_VF_CFF2_ARCHITECTURE_20261102.json).

The 100-unit origin mismatch has two distinct contracts. In the same horizontal
coordinate frame, DirectWrite defines the vertical origin X as half the current
horizontal advance. For a source gap `d = Xsource - Asource/2`, simultaneous
errors of at most epsilon in both raw quantities require
`abs(d) <= epsilon + epsilon/2`. A 100-unit gap exceeds that bound at epsilon
1/32. This is a limitation of equality through that raw API, not proof that a
complete OpenType layout cannot represent the desired visual position.
[DWRITE_GLYPH_METRICS](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_metrics)
documents the coordinate convention.

Real CoreText layout controls now include 2,016 calls, 1,008 paired layouts
and 1,764 glyph comparisons. Variable GPOS can compensate the independent
visual X origin in these authored TrueType controls. Raw metrics do not change.
A second experiment shifts points while holding the bearing fixed: the engine
normalizes away the shift. Shifting the bearing as well moves the horizontal
outline without changing the vertical origin. Neither result is an all-engine
acceptance or a repair to the original strict builder.

`cff2_geometry.py` retains fractional default points and residuals in CFF2
16.16 operands and elevates quadratic curves exactly to cubic curves. Models
must pass independent holdouts at the unchanged 1/32 limit, and assembly
requires every original GID. Failed models cannot be assembled. A second
encoder factors multi-axis regions into nested blends: an authored 729-master
function can be serialized without putting 728 delta operands onto a single
CFF2 stack. Factoring preserves the fitted function; it does not improve an
inaccurate fit. CFF2 explicitly permits repeated blending for higher-order
interpolation in its
[advanced blend rules](https://learn.microsoft.com/en-us/typography/opentype/spec/cff2#advanced-uses-of-blend).

The strict CoreText extractor now proves a zero-length CFF2 CharString by
parsing the table header, TopDICT reference, INDEX count and bounded monotonic
offsets. Nonempty programs and malformed inputs receive no empty-glyph
exemption. All 28 native Swift structural tests pass. The diagnostic harness
source fingerprint was updated only after reviewing this change; constructors,
axis checks, identity verification and glyph measurement code were verified
byte-identical to c824c2ee. No test tolerance or expected metric was changed.

Actual local measurements on macOS 26.5.1, fontTools 4.61.1 and HarfBuzz 14.6.0:

| Scope | Result |
| --- | --- |
| Python regression | 919 tests, zero failures, seven platform skips; six audits pass |
| Authored CFF2 flat and factored collections | Both load as two faces with three GIDs and all three original axis tags |
| CoreText geometry | 348 successful records, zero geometry failures; maximum cubic control error 0.00180813 FUnit |
| CoreText CFF2 VORG/VVAR Y origin | Maximum error 0.000527344 FUnit |
| CoreText CFF2 raw X origin with VORG | Uses default width in this control; error up to 70 FUnits against current half-advance |
| CoreText vertical advance | Fractional error 0.3375 FUnit remains; 8x and 14x physical-preserving controls still fail at 0.0875 and 0.0517858 |
| HarfBuzz raw metrics | Advance-width error 0.216594 and advance-height error 0.3375 FUnit remain in the unscaled controls |
| CFF2 strict native gate | FAIL: 68 raw metric failures per encoder; every failure retained |
| Real HVGL GID 0 | 125-point fit with 64 independent holdouts: maximum control error 0.0122735; finite geometry evidence only |
| Real HVGL GID 1166 / 19177 | 729-point fits still fail at 5.126612 / 1.894212 FUnits over the same 64 holdouts |

The two worst real-source holdouts were executed again through Apple's native
HVF library. Portable extraction matches native cubic-equivalent controls to
2.43e-13 and 3.42e-13 FUnit respectively, with the same topology. The remaining
large errors therefore arise in these interpolation models, not in those source
observations. Selected successful finite samples are not complete GID coverage
or a continuous-space proof.

VORG presence also changes CoreText behavior: removing VORG and supplying the
appropriate authored VVAR side-bearing maps restores the current half-advance
X origin and accurate Y origin. Fractional vertical advance still fails. This
experiment rules out treating a different table choice alone as a complete fix.

The workflow now executes the CFF2 strict native gate and loads/renders the
factored CFF2 control through real Windows DirectWrite. Those controls are
generated from repository-authored shapes and contain no original font data.
Windows CI is still distinct from Windows 11 hardware, installation and final
font acceptance. No new final-font Qt result exists. Production coverage stays
0/32 accepted faces. Grant documents remain unavailable for scope verification;
no font binary, native original outlines or private authorization material is
included in this continuation. Merge to `test` remains blocked.

## DirectWrite isolation and lossless CFF2 compaction

Actual [Windows native matrix run 41389700440](https://github.com/SOLHK/Swirl/actions/runs/41389700440)
at source commit `c46d10647eba3e0313389cc9a85b4972cf54dacc` used Windows Server
2022 build 20348. Seven ordinary CFF2 variants pass the existing DirectWrite
probe: flat TTC, standalone face, STAT, explicit FDSelect, private/default
vsindex choices and post format 3. The TTC cases retain two faces, three GIDs
and all three axes, with 62 actual native positions per face. The factored
variant fails: its probe outline disappears and axes produce no actual
geometry movement despite readable axis values. The same nested encoding
loads in CoreText and fontTools. This isolates a DirectWrite incompatibility
with this nested encoding, rather than a general CFF2 or TTC rejection; it
does not identify Microsoft's private implementation defect.

The new `compact()` encoder removes only all-zero **encoded** delta rows from
the existing fitted function. The 729-master authored model reduces from
728 regions to 40 nonzero regions, so ordinary blends fit the operand stack.
No nonzero coefficient, including one 16.16 quantum, is removed. Independent
serialized comparisons cover all 729 masters and 32 deterministic off-grid
points. Failure evidence survives compaction, and genuinely dense nonzero
models still fail the stack limit. Both the existing nested failure gate and
the strict raw-metric gate remain active. The new native compact gate is
pending CI when this source checkpoint is committed.

Local regression is now 921 tests with zero failures and seven platform skips;
all six audit tests pass. The three CoreText CFF2 encodings produce 522 native
glyph observations with zero geometry failures, maximum control error below
0.001816 FUnit. All three still fail 68 raw metric comparisons each at the
unchanged 1/32 threshold, so the strict native command correctly exits 1.

`platform/qt_cff2/` is a standalone Qt 6.12 probe exercised against the compact
authored font on macOS: both families, CFF2/GID identity, actual endpoint path
changes for all three axes, 60 QPainter images at DPR 1/1.25/1.5/1.75/2, and
two QML captures with verified font binding. These are software/offscreen
controls, not physical high-DPI, Chinese coverage or final Swirl acceptance.
Build with CMake and the Qt 6.12 SDK, then run `cff2_qt FONT OUTPUT_DIRECTORY`
with `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software`. The authored input
is generated by `platform/make_cff2_fixture.py OUTPUT --compact`.

No formal font has been generated. Full source-model fitting, strict raw
metric equality, Windows 11, final-font Qt and distribution-grant verification
remain unresolved. No test result above permits merging this PR into `test`.
