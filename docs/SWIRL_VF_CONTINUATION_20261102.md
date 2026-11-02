# SwirlVF continuation checkpoint — 2026-11-02

**Partial engineering checkpoint. No accepted SwirlVF.ttc exists.**
The recovered work through `91c2b760` is preserved. This continuation uses an
isolated worktree and [draft PR 52](https://github.com/SOLHK/Swirl/pull/52),
targeting `test`, because another session was active on PR 49's branch.
No existing branch was overwritten. `test` remains at
`63dde8812f85839aa6024cbba6c498c96cae022d` at this checkpoint.

## Native axis verification

The old DirectWrite geometry verifier could pass a transcript whose geometry
was correct even when its applied width value was replaced. It counted 62
positions without independently verifying their coordinates or names. The
verifier now requires the complete independently constructed plan, exact
submitted FLOAT readback, all physical fvar axes and GIDs, input SHA binding,
per-face receipts and a single successful terminal receipt. Synthetic axes
added by DirectWrite cannot substitute for the font's physical axes.

The C++ probe no longer accepts one-FLOAT-ULP readback changes under a
magnitude-based tolerance. The requested value was already converted to FLOAT;
the comparison does not mistakenly compare it with an unrepresentable Python
binary64 value. Six regressions cover these false-positive paths. The outline
limit remains **1/32 source font unit**.

## Mixed-axis geometry implementation and measurements

`adaptive_cff2_geometry.py` adds bounded tensor refinement across the complete
three-axis cube. It measures mixed-axis midpoint planes, chooses splits without
consulting independent holdouts, uses exact F2DOT14 knots and quantizes CFF2
coefficients once to 16.16. Absolute accumulated cubic control-point error is
checked after serialization coefficients are chosen. Lossless removal of
exactly zero regions is allowed; nonzero residuals are retained. Capacity and
accuracy failures remain explicit and cannot be assembled as accepted models.
This is sampled verification, not a proof for every continuous coordinate.

`probe_hvf_cff2_geometry.py` compares the existing portable evaluator, fitted
models and actual Apple libhvf on the exact supplied source. It checks all
three axes simultaneously at 27 grid positions plus 32 independent nonzero
F2DOT14 positions for GIDs 0, 2, 12, 1166 and 19177. Raw source transcripts
stay outside the repository. **295/295** portable/native geometry comparisons
pass; maximum error is approximately `4.69e-13`. This localizes the remaining
selected-glyph failures to the fitted CFF2 representation, not this portable
source evaluator or degree elevation.

| GID | Adaptive result, 507-node budget | Dense follow-up |
| --- | --- | --- |
| 0 | PASS sampled cube; 81 nodes, 44 nonzero regions | Not needed |
| 2 | Empty outline retained | Not needed |
| 12 | PASS sampled cube; 210 nodes, 57 nonzero regions | Not needed |
| 1166 | FAIL | 4,048 nodes, holdout error 0.856433, stack overflow |
| 19177 | FAIL | 4,032 nodes, holdout error 0.590699, stack overflow |

GIDs 0 and 12 also load as private geometry controls in CoreText: **182 native
observations, zero geometry failures**, maximum errors 0.003104 and 0.006616.
These controls place selected source outlines in an authored container; they
do **not** retain the complete source GID/cmap mapping or certify metrics.
They are neither distributable source fonts nor the requested delivery file.

A new fully authored nonlinear fixture contains a term that vanishes on
individual-axis sweeps but changes mixed-axis control points. The ordinary
CFF2 adaptive model is now required in both native platform matrices. The six
new regressions check independent holdouts, preserved topology/mapping,
serialization, control-point accumulation and failed-model admission.

## Executed validation

Local environment: macOS 26.5.1 ARM64, Python 3.12.16, fontTools 4.61.1,
NumPy 2.2.6, HarfBuzz 14.6.0. Commands from the repository root:

```sh
python -m unittest discover -s tools/swirl_vf/tests -v
python -m unittest discover -s tools/swirl_vf/audit -p 'test_*.py' -v
git diff --check
python tools/swirl_vf/platform/test_coretext_cff2.py --output "$PRIVATE_NEW_OUTPUT"
python tools/swirl_vf/platform/probe_hvf_cff2_geometry.py \
  --source "$PRIVATE_SOURCE" --source-sha256 "$EXPECTED_SOURCE_SHA256" \
  --binary "$PRIVATE_HVF_ORACLE" --private-output "$PRIVATE_NEW_OUTPUT" --adaptive
```

The source suite executed **965 tests: 958 passed, seven platform skips, zero
failures**; six audit tests passed. The authored CoreText gate executed five
variants, **870 glyph observations, zero geometry failures, 340 raw-metric
failures**. Each variant retains the same 68 raw-metric failures, including
fractional vertical advance and independent X origin. Its nonzero exit is
intentional evidence of an unresolved gate, not an accepted result.

New Windows execution of checkpoint `1344bd40` is recorded in
[run 41458445938](https://github.com/SOLHK/Swirl/actions/runs/41458445938),
PR merge checkout `a7a580bd711f6b9aa244151fb87f381bd7342821`.
The native C++ probe compiled and the 13 ordinary geometry controls passed on
Windows Server 2022, Server 2025 and Windows 11 ARM64 using an x64 process.
All six nested-blend controls still lost 124 nonempty outlines each. The strict
factored-blend steps remain failed on all three Windows platforms. Authored
variable-origin layout controls pass without changing raw metrics. The Apple
job on macOS 26.6.2 retains its 849/850 and raw-metric failures. The workflow
remains **failed**. This run predates the new adaptive native fixture; its
results cannot be attributed to that fixture or the original source font.

The [aggregate receipt](evidence/SWIRL_VF_CONTINUATION_20261102.json) records
counts, hashes, scope and failures without source geometry or coefficients.

## Outstanding delivery requirements

The original font has **32 faces × 47,102 GIDs**, with physical axes `WDTH`,
`wght`, `HGHT`. Uppercase custom `WDTH` is not the registered lowercase `wdth`;
final user-coordinate mapping and associated STAT/name changes are unfinished.
No glyph, Unicode mapping or axis was removed to obtain the results above.
Existing full-GID extraction evidence is preserved; full-font reconstruction,
all-face axis combinations, final table coherence and metrics are not accepted.

GID 1166/19177 interpolation, engine metric differences and the source's
independent vertical X origin remain blocking. Increasing the tensor budget
alone did not solve the measured failures. Required native gates remain red,
so PR 52 is draft and has not been merged into `test`. Final Windows 11 desktop
installation, application rendering and final-font CoreText acceptance have
not run. The intended private destination is `output/SwirlVF.ttc` outside this
checkout; no such final file or final SHA-256 is available.
