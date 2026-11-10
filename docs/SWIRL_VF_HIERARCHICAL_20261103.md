# Hierarchical CFF2 checkpoint — 2026-11-03

GIDs 1166 and 19177 do **not** yet pass over their complete three-axis cubes.
The acceptance limit remains 1/32 FUnit. This checkpoint resolves the ordinary
blend capacity of two difficult local boxes, without claiming complete glyphs.

The new hierarchical basis represents the same tensor interpolant before
16.16 quantization. Recursive local surpluses avoid the large cancelling
coefficients of the truncated-power ramp basis. Nonuniform F2DOT14 knots and
nonzero box anchors are supported. Vectorized rounding is bit-identical to
the previously tested local models, including support order; it avoids Python
objects for every zero tensor coefficient.

`hierarchical_cff2_compression` permits omission of nonzero coefficients only
with a uniform bound on the resulting encoded-model difference. On each grid
cell the difference is multi-affine. Every control is a convex combination of
its vertex differences, so the maximum vertex norm bounds the entire cell.
The implementation accumulates relative operands as exact integer 16.16 ticks
and uses outward interval arithmetic for synthesis, squared norms and square
roots. A rational-arithmetic regression checks nonuniform knots. Compression
clears source/serialized/native acceptance flags: this certificate does not
bound source-fitting error or native arithmetic. Resource and capacity limits
fail explicitly; no threshold is silently relaxed.

On macOS 26.5.1 ARM64, each source case has 1,024 new independent mathematical
holdouts, 1,024 actual saved/reopened CFF2 observations and 72 separate exact-axis
CoreText/libhvf comparisons. All pass, with no topology mismatch:

| GID | Normalized box, WDTH / wght / HGHT | Regions | Saved maximum | Native maximum |
| --- | --- | ---: | ---: | ---: |
| 1166 | [0,1] / [-.5,-.25] / [-1,-.5] | 339 | 0.012299366 | 0.007979110 |
| 19177 | [-.5,0] / [.25,.5] / [.25,.5] | 372 | 0.011591159 | 0.009607543 |

For GID 1166 the 65×33×9 grid has 1,951 nonzero regions before compression;
its 339-region result has a uniform compression bound of 0.007753880 FUnit.
GID 19177 uses a 65×33×5 grid and needs no lossy compression. These fonts use
an authored three-glyph template, not the original cmap, metrics or GIDs.
Local-model installation remains guarded. Their actual file hashes and native
oracle hashes are in the [receipt](evidence/SWIRL_VF_HIERARCHICAL_20261103.json).

The complete cube still needs a different partition. A 65×65×33 unencoded
grid gives maxima 0.813556888 / 0.456093641, with 155 / 389 failures out of 2,048
development positions. The GID 1166 maximum lies close to a Type-2 projection
boundary, with dominant weight/height contributions. Several GID 19177 maxima
lie near a shared internal weight-axis zero. These new failures are retained;
further uniform densification is not an accepted solution. The next experiment
uses a common source-boundary-aware box atlas for both glyphs, but native
selection, seams, total regions and glyph count must also fit the font format.

Local tests: 993 executed, 986 passed, seven platform skips, zero failures;
six parser audits pass. New compressed hierarchical authored fonts also pass
546 HarfBuzz 14.6.0 outline observations across two faces and three GIDs. The
fixture omits nonzero terms only after the same compression certificate. It is
included in both native matrices for subsequent CI validation. The local
CoreText matrix passes all 174 hierarchical outline observations (maximum
0.001940973 FUnit), while retaining 68 raw metric failures for that variant.
All seven variants retain the same metric failures, 476 total; the strict
combined gate is failed, not described as a complete native pass.

The preceding pushed commit `64edf480ada893b28e01be6473a46ee82996c9cf` has now
completed its Windows jobs. Its ramp fixture passes 372 outline observations
per environment, maximum 0.007074312 FUnit, on Server 2022 x64, Server 2025 x64,
and Windows 11 ARM64 running an **emulated x64 process**. This is not Windows
11 x64 physical-machine acceptance and does not certify source GIDs. Six nested
variants still fail per environment, and the overall jobs remain failed. Linux
passes all 987 tests and six audits. The Apple CI job was cancelled; the Qt job
was skipped by the branch filter. The new hierarchy's DirectWrite result is
pending. [Exact run](https://github.com/SOLHK/Swirl/actions/runs/41503468663).

Reproduce with the authorized private source and a fresh private output path:

```sh
python -m unittest discover -s tools/swirl_vf/tests -v
python -m unittest discover -s tools/swirl_vf/audit -p 'test_*.py' -v
python tools/swirl_vf/platform/probe_local_cff2_basis.py \
  --source "$PRIVATE_SOURCE" --manifest "$WIDE_BASIS_MANIFEST" \
  --private-output "$FRESH_PRIVATE_OUTPUT" \
  --coretext-binary "$CORETEXT_ORACLE" --hvf-binary "$HVF_ORACLE"
python tools/swirl_vf/platform/make_cff2_fixture.py \
  "$FRESH_AUTHORED_TTC" --hierarchical
```

The local recovery directory `private/three-axis-20261103` contains the input
manifest, source/native transcripts, models, failure positions, exact script
versions and aggregate hashes. `local-minimax/global_failures.py` reproduces
the new full-cube witnesses. No private fonts, outlines or coefficients are
committed. PR #52 remains draft; neither test nor main is merged. No final
SwirlVF.ttc or delivery checksum exists at this checkpoint.

## Serialization, regression and native CI follow-up

PR #51's exact ordinary-CFF2 decoder and its eight regressions are selectively
ported from `cc29a9e8caf29d7b668ccb9ec9c4be250d5abd1e`, byte-for-byte. The two
saved difficult-box TTCs pass complete coefficient/support identity, including
subroutines. Thus serialization preserves these supplied functions at all joint
coordinates. Their source-fit scope remains the declared boxes.

New full-cube sampled regressions cover GIDs 0, 2 and 12: 1,536 independent
saved/reopened observations and 216 actual CoreText/libhvf comparisons, all
pass. Saved maxima are 0.000796872, 0 and 0.012372212; native maxima are
0.009099353, 0 and 0.010697792. An initial all-empty template was rejected by
CoreText before identity verification. The harness now keeps a separate
authored `.notdef`; the measured blank GID remains genuinely empty. Startup
exceptions are retained as failed native records instead of escaping before
the case report is written. No native identity check is relaxed.

The frozen common-atlas experiment is also retained as a failure: 512 boxes,
35 fitted, 477 unresolved; the fitted subset already has 7,894 distinct regions.
A new 8,192-position independent plan gives 60 / 177 failed target observations,
maximum errors 0.126357692 / 0.120257162. All 27 cube-grid positions pass, which
again shows why corner-only validation is insufficient. An adaptive nonuniform
19,747-node octant grid also fails: maximum held error 0.866730818 and its
506-region compression bound is 0.126981944. No complete atlas font is installed.
Changing the greedy compression initialization to 16, 64 or 128 regions does
not improve the difficult-box result; the original 253-region seed is retained.
These experiments do not prove that every standard CFF2 representation fails.

At head `7a4337924f25bd2e57729a51c0e880cd6c4c846d`, actual CI now verifies the
new hierarchical fixture: each of Server 2022 x64, Server 2025 x64 and Windows
11 ARM64/x64-emulation passes 372 DirectWrite observations (max 0.007074312).
macOS 26.6.2 ARM64 passes 174 geometry observations (max 0.001940973), retaining
68 metric failures for this variant. Six nested variants still fail on Windows;
the overall workflow is failed. The decoded fixture bytes match the local
8,660-byte authored TTC exactly. [Run and artifacts](https://github.com/SOLHK/Swirl/actions/runs/41509979774).

The independent `cff2_qt_joint` target and a narrowly scoped Windows workflow
now request Qt **6.12.0**, exact font/table hashes and 546 three-axis source
comparisons. Both ordinary controls and empty outlines are compared through
actual `QRawFont::pathForGlyph`, with the unchanged 1/32 FUnit limit. Reference
commands come from the authored source, not the target. Native Qt execution is
pending at that checkpoint. The existing product workflow's
branch filters, UI, Rust runtime and delivery gates are untouched.

Validation before this follow-up: 1,002 Python tests, 995 passed, seven skipped,
zero failures, plus the newly added independent Qt-manifest test (one passed).
The [follow-up receipt](evidence/SWIRL_VF_HIERARCHICAL_FOLLOWUP_20261103.json)
binds these observations, the unchanged failure logs and private recovery
commands. The primary target glyphs and final-font delivery remain unaccepted.


## Qt native execution and empty-path representation

The retained delivery receipt identified the existing private Qt 6.12.0 SDK;
the earlier PATH-only lookup was insufficient to establish SDK absence. The
standalone C++23 probe builds locally and passes **546 / 546** macOS ARM64
observations, maximum **0.001156704 FUnit**, with actual Qt outlines, exact
font/table identity and application-font removal. Its QPA is offscreen; this
is geometry evidence, not physical display or final-font acceptance.

The first Windows Qt run builds successfully and reports 182 topology failures:
all are the authored blank GID 1, represented by a single `moveTo(0,0)` instead
of an empty element list. Every nonempty observation passes (364 / 364), max
0.001171961 FUnit. The failed archive and raw result are retained. The corrected
probe admits only this exact zero-ink representation, and only when the manifest
proves both an empty source command list and an empty saved CFF2 CharString.
The exact target font/table hashes bind that proof. It rejects displaced moves,
nonzero edges, curves, nonempty references and missing serialization proof;
positive and negative Qt-path controls execute in the native binary. Raw topology
mismatches remain reported separately. The coordinate limit is unchanged.

The corrected Windows run is pending. The [Qt receipt](evidence/SWIRL_VF_QT_JOINT_20261103.json)
records the actual local result and the failed Windows run separately. The
mathematical targets remain unresolved. A further local basis experiment that
extends endpoint ramps to shared global supports reduces the fitted atlas
subset from 7,894 to only 7,662 regions and creates one stack overflow; it is
not adopted as a solution and its private code/results are preserved.
# Absolute control quantization follow-up

The new `absolute_then_exact_relative` option preserves the independently
retained absolute source nodes. It transforms and quantizes absolute control
coefficients, then differences exact integer 16.16 ticks into CFF2 operands.
It rejects absolute inputs that do not exactly reproduce the supplied relative
observations. This fixes accumulated coefficient-rounding drift without forcing
endpoints closed, moving source controls or removing curves. The historical
relative encoding remains reproducible.

On the same new 1,024 holdouts for each target box, legacy/new errors are
0.009250226 / 0.009272331 for GID 1166 and 0.014872810 / 0.014910982 for GID 19177.
This is a closure-invariant fix, not an improved source fit. Nonzero closure
coefficient pairs decrease from 115 / 431 to zero. Region counts are 339 / 402;
the latter increases from 372. Integer coefficient identity survives actual
serialization and the existing bounded compression.

The new five-model run passes 3,584 independently selected saved/source checks
and 360 CoreText/libhvf checks. GIDs 1166/19177 remain restricted to the previous
declared local boxes; GIDs 0/2/12 have sampled full-cube scope. Exact serialized
coefficient certificates pass for every model. Python validation executes
1,007 tests: 1,000 pass, seven platform skips, no failures; six parser audits pass.

The Qt authored correction is now verified on Windows Server 2022 x64:
[run 41515917678](https://github.com/SOLHK/Swirl/actions/runs/41515917678),
head `87ee4b9d4fa65537d2b5fe68dc83f5ca29979f5c`, merge
`c50b1afc93bda8d6eb46fe35b7590e38c9a99695`. All 546 observations pass; maximum
0.001171960 FUnit. Of these, 182 retain the documented verified empty-origin
representation. The local authored Qt run also passes 546 observations.

Private source Qt diagnostics remain **FAIL**: GIDs 1166/19177/0/2/12 have
72/64/64/0/64 path-topology failures in 72 observations each. Qt adds tiny
implicit closing edges and suppresses tiny degenerate curves. Exact encoded
closure does not guarantee identical floating native path elements. No such
elements are discarded by the strict gate. Unmatched topology now reports a
null geometry error instead of a meaningless comparison between shifted
element indices. These failures are retained separately from CoreText passes.

Reproduce source fitting with `probe_local_cff2_basis.py` and a private manifest
whose cases specify `quantization: absolute_then_exact_relative`. The private
checkpoint `three-axis-20261103/absolute-basis-manifest.json` binds the source
hash, original boxes, training knots and new holdout seeds. `qt_cff2/joint.cpp`
accepts private manifests only with `--private-box`; default CI remains authored
controls. The [receipt](evidence/SWIRL_VF_ABSOLUTE_QUANTIZATION_20261103.json)
contains aggregate counts, font/code/input/log hashes and all failed Qt counts.
Raw outlines, coefficients and failure positions stay outside Git.

Full-cube source fitting, complete-font selection/capacity and final
`SwirlVF.ttc` remain unaccepted. This checkpoint does not merge test or main.
