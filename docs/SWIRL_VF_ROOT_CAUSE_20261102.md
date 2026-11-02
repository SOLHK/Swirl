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
