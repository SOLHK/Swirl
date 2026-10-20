# D2-1: Qt FreeType outline-state isolation checkpoint

Branch: `work/vf-windows-d1`. Started from verified remote HEAD
`4c0fcaf4a66fd34d3487754dd2f849a278da3a3e`, not an older executable tree.

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
