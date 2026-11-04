# D2-1: Qt FreeType outline-state isolation checkpoint

Branch: `work/vf-windows-d1`. Started from verified remote HEAD
`4c0fcaf4a66fd34d3487754dd2f849a278da3a3e`, not an older executable tree.


**Latest verified result:** native source `7bf755d0c8e05f59f505becf5b188f60299cddfe`,
[run 39423555154](https://github.com/SOLHK/Swirl/actions/runs/39423555154).
D2 diagnostic validation passes on both Windows Server 2022 and 2025; the
unchanged D1 strict FreeType failures keep the overall CI red. The earlier
PENDING/NOT_RUN entries below are historical checkpoints, superseded for D2
by the final native verification section. No production repair is claimed.

## Scope and source finding

D1's original font, strict executable, DirectWrite and Qt native tests remain
unchanged. Its original FreeType failures remain failures. No production file,
other window's branch, font bytes, hinting default or backend selection changes.

Qt 6.10.3 source is pinned to `7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4`.
`QFontEngineFT::loadGlyph` sets the face translation on a cache miss, while
cache hits return without updating it. `lockFace(Unscaled)` only resets the
transform when the cached matrix differs. `addGlyphsToPath` then loads an
outline without clearing translation. Bundled FreeType applies that persistent
translation to the outline, but applies only the matrix to the advance.
This is a source-confirmed missing state normalization; causal native validation
of this particular failure is **PENDING** at this source checkpoint.

## Independent diagnostic, not a production workaround

The additional executable reuses unchanged D1 helpers and the ordinary fixture.
One fixed QRawFont/A glyph/axis tuple is held through each process. It reads the
actual QFontEngineFT, retained FT_Face, matrix, delta and glyph cache metadata.
The test-only guard clears only delta during the outline query and restores
matrix/delta before releasing the face lock. The unguarded failure must remain
reproducible immediately after restoration; all path comparisons are exact.

Only the three self-contained transform/version functions from the pinned
FreeType source are compiled under diagnostic names. No second rasterizer is
linked. Source Git blob identities, runtime FreeType version, actual backend and
Qt DLL hash are checked/recorded. Private Qt/FreeType ABI access is **not approved
for production**. A small upstream patch is generated as evidence, not applied.
Window 1 must review any dependency or production integration change.

The frozen matrix is 96/144/192 logical DPI, DPR 1/1.25/1.5/2, no/full hinting,
cache on/off diagnostic controls, independent unguarded/guarded processes, and
12 horizontal/vertical offsets including cached replay: 96 processes per OS.
Cache-off is a negative control, never the proposed fix. Complete paths,
advance, actual transform, cache entries, PNG and raw BGRA bytes are preserved.
Control/guard pixels and cache histories must be exactly equal.

## Validation at this checkpoint

15/15 portable fail-closed tests passed locally. These are mock/parser/patch
checks, not native evidence. Windows Server 2022/2025 D2 results are **NOT_RUN**
until the newly pushed workflow finishes and its raw outputs are inspected.
The original D1 runner still executes and fails strictly before D2 preparation;
D2 runs with `always()` and cannot turn those failures green.

Original TTC, Windows 11, Qt Quick production UI and performance: **NOT_RUN**.
This checkpoint does not claim a shipped Qt repair or a visible UI defect.

## Native configuration correction

First executable checkpoint: `f7e841816888aecdba19e51457b246a2b55f569f`.
CI: https://github.com/SOLHK/Swirl/actions/runs/39407995733 . Both Windows
SDKs reported bundled FreeType (`QT_FEATURE_system_freetype=OFF`), but the
external CMake consumer had not explicitly imported `Qt6GuiPrivate`. Qt 6.10
loads private module counterparts conditionally; their absence as an imported
target does not establish absent SDK headers. D2 now explicitly requires the
exact private package inside its opt-in block. The original D1 configuration
is unchanged. Source binding and unapplied patch generation succeeded; native
D2 compilation/execution was NOT_RUN in that attempt.

## Runtime identity correction and final native verification

The next source `205af02ce1db6c9ec525d8962b44e7681ee37ffe` successfully built and
executed all 96 D2 processes per OS in
[run 39408729626](https://github.com/SOLHK/Swirl/actions/runs/39408729626).
Its analyzer rejected every process with `Unverified physical runtime`:
it incorrectly required `2.14.3`, while both the pinned `freetype.h` macros and
runtime version readback are **2.14.2**. Attribution metadata is not a compiled
version or private-ABI identity oracle. Those original failed reports remain
unchanged; they are not relabeled as passes.

The identity correction was tested locally (37/37 unchanged D1 tests and 19/19
D2 tests), committed and pushed as `7bf755d0c8e05f59f505becf5b188f60299cddfe`.
Only `d2_state.py`, `d2_probe.cpp`, and `test_windows_d2_state.py` changed in
that executable commit. The guard, offsets, exact path comparisons, original
D1 executable and authored font bytes are unchanged.

Expected FreeType version now comes from canonical header bytes verified against
Git blob `e8a1b1e2f3ea9c39f6252497da36cfdd25a857d3` at the pinned Qt commit.
The prepared manifest, compiled header version and actual library readback must
agree. The executable embeds its build source SHA and upstream identity; the
analyzer rejects mismatches. The loaded `Qt6Gui.dll` is located through Windows
module APIs, matched to the selected SDK path, and independently hashed by the
parent Python process. Unknown or missing identities still fail closed.

Both systems used Qt 6.10.3 / FreeType 2.14.2 and the same Qt GUI DLL SHA-256:
`03ba47a2025036a04f5548bce242788ac21edf551e78d5b42e1b87beb799904f`.
This identifies the observed SDK; it is not a reproducible-build or binary
provenance certification of all upstream code.

| Native result | Server 2022, build 20348 | Server 2025, build 26100 |
| --- | --- | --- |
| Job | [118630286262](https://github.com/SOLHK/Swirl/actions/runs/39423555154/job/118630286262) | [118630285641](https://github.com/SOLHK/Swirl/actions/runs/39423555154/job/118630285641) |
| D2 build and diagnostic | PASS, 96 processes / 1152 observations | PASS, 96 processes / 1152 observations |
| Independent control/guard comparisons | 48 exact | 48 exact |
| Guarded queries different from cold path | **0 / 576** | **0 / 576** |
| Unguarded changes in control / guard processes | 42 / 42, retained | 42 / 42, retained |
| Original DirectWrite / Qt native | 8/8 and 4/4 processes PASS | 8/8 and 4/4 processes PASS |
| Original Qt FreeType strict tests | 4 failures retained | 4 failures retained |
| Overall workflow/job conclusion | **failure** | **failure** |

The overall failure is intentional evidence preservation, not a D2 identity or
isolation failure. Each D1 partial report was independently reproduced exactly:
12 validated processes, 3568 observations, six opposite-order comparisons,
three private/installed comparisons, and successful cleanup of both fonts.

### Causal transform intervention

At 9 pt, 96 logical DPI, DPR 1, PreferNoHinting, one fixed QRawFont/A glyph and
fixed axes were retained. Matrix values stayed `[65536,0,0,65536]`.

| Draw x-offset | Actual residual delta x (26.6 integer) | Original right x | Guarded right x |
| --- | ---: | ---: | ---: |
| 0 | 0 | 6.421875 | 6.421875 |
| 0.25 | 16 | 6.4375 | 6.421875 |
| 0.5 | 32 | 6.4375 | 6.421875 |
| 0.75 | 48 | 6.4375 | 6.421875 |
| Cached replay of 0 | 48 | 6.4375 | 6.421875 |

The guard clears only translation while querying the outline, then restores the
saved matrix/delta under the face lock. All 576 guarded paths per OS exactly
match the cold complete path, not merely its bounds. Every following unguarded
query reproduces the pre-guard path exactly. Actual and Qt-cached matrices,
delta, sampled glyph-cache entries and advances are unchanged by the guard.
The sample advance stays 7.625 px. With cache disabled only as a negative
control, replaying zero offset resets delta to `[0,0]` instead of retaining
`[48,0]`. This confirms the residual translation/cache mechanism for the fixture.

All 48 independent control/guard pairs per OS have byte-identical raster
sequences. All **2304 PNGs** across both OS versions were independently decoded
and matched to raw BGRA bytes and recorded SHA-256. All 1152 corresponding
cross-OS observations and rasters agree exactly. Archived source files were
also compared to the tested/pushed source checkpoint.

Actual contamination was observed only at DPR 1 with PreferNoHinting in this
fixture, across all three logical DPIs and both cache controls. Full hinting and
DPR 1.25/1.5/2 were exercised without an observed path change. These controls do
not establish absence of all other Qt rendering problems or a production UI bug.

### Durable handoff and stop condition

[Source-bound native evidence](evidence/SWIRL_VF_WINDOWS_D2_1_RUNTIME_20261020.json)
retains identities, counts, failure classifications, full sample paths/states
and artifact hashes. Full raw logs, PNGs and BGRA bytes are in the run artifacts:

- Server 2022 artifact `12265262358`, ZIP SHA-256 `047cc3943a78cc88ccc5b683b44fa3b850a55afc8b3eaec533d5c9fdda302ada`.
- Server 2025 artifact `12263714746`, ZIP SHA-256 `de5b9b5c377e2a4277e56e78609321787f23b460ebb4da63c84379dd4e20aa13`.

The [small upstream patch proposal](patches/SWIRL_VF_WINDOWS_D2_1_QT_6_10_3.patch)
is generated from the verified Qt source and remains **unapplied**. The native
experiment validates the scoped intervention in the diagnostic executable,
not a rebuilt/patched Qt DLL. Private ABI access is not approved for production.

D2-1 stops here with a confirmed cross-component defect and native-validated
diagnostic isolation. The next minimal task is Window 1 review of the patch and
approval of a separate patched-Qt validation build. No production integration,
D2-2, Windows 11, original TTC replacement, Qt Quick UI or performance acceptance
was started. All those production/desktop acceptance items remain NOT_RUN.
