# Swirl-VF precision continuation: verified checkpoints

Branch: `work/core-completion-20261017` only. This continuation starts at
`056f7ea6dc7cf3a703da63e8522b89d33d1166f4`, not the older prompt baseline.
All concurrent Core changes remain in ancestry. No UI, animation or Core source
is changed. Original input was rechecked: 61,473,880 bytes, SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
The input and all Apple-derived private data remain outside this repository.

## A1: preserve the existing replay solution; close a strict-path omission hole

**Native verification complete for this bounded A1 fix.** Exact source:
`f72187f70d0af20fb197fb3e49389b53e8ce31a0`. Non-forced branch update was
followed by an independent remote HEAD read matching that full SHA.
[Actions 39379538186](https://github.com/SOLHK/Swirl/actions/runs/39379538186)
finished: Python **success**, Windows synthetic DirectWrite **success**, Apple
**failure** because the old strict 849/850 metric check still fails. Apple job
118485220527 compiled the actual production Swift helper and **22/22 validator
cases passed**, with `numeric_tolerance=1e-6`, `actual_font_test=false`, and
`PASS_PRODUCTION_SWIFT_VALIDATOR`. The real extractor exited zero before the
unchanged separate metric assertion rejected face 0 / GID 2 at 0.03125.
No queued/running job is counted as PASS. Artifact 12244867446 records the
native evidence; GitHub reports archive digest
`f47a0a483ad3c235102d59f48ed17a8b4e60c67292a5040333f9004a389ee636`.

The existing v2 verifier remains the production replay implementation. It
predeclares T/T(T) before native requests, checks an exactly stable replay echo,
compares every requested GID's complete raw paths and metrics with zero
tolerance, and returns the original observations only after the batch passes.
The earlier 91-batch / 5,824-observation original run remains a finite sampled
result, not complete user/design mapping or all-GID acceptance.

An independent counterexample exposed a different issue in the default Swift
strict path: a missing WDTH report at requested `500.0000005` was filled with
the default `500` and accepted by the existing `1e-6` numeric test. This
contradicted the explicit rule that only exact defaults may be omitted. This
is a validator counterexample; it is not claimed as an observed source-font
CoreText response. The v2 Python adapter already rejected this case.

`coretext_extract.swift` now separately requires the nondefault axis to be
present and retains the same `1e-6` numerical check and error code. It calls a
shared Swift helper, allowing original synthetic regression inputs to execute
the exact production validation code. The diagnostic GUARD contract is updated
with it, so observation-only helpers still remove the whole strict check rather
than accidentally adopting a partial acceptance rule.

`check_coretext_axis_guard.py`, invoked by the existing native test, compiles
the production helper verbatim and executes 22 independent cases: omitted and
explicit defaults; all three axes just above/below the default, including the
next binary64 value; explicit values inside/outside the unchanged tolerance;
exact nondefaults; the known `600.5859375 -> 600.5859` mismatch; and an absent
requested coordinate. Passing this logic test alone never claims that an actual
font instance or its metrics pass.

Baseline local regression: **320/320 Python tests, zero skips, 6/6 audits**,
using Python 3.12.14, fontTools 4.61.1, NumPy 2.2.6 and uharfbuzz 0.53.3.
After this fix: **324/324 Python tests, zero skips, 6/6 audits**; the full suite
completed in 12.780 seconds and `git diff --check` passed.
Linux has no CoreText/Swift runtime. The exact pushed source has now executed
the new Swift cases on xcode-27, as recorded above; local harness tests alone
were never counted as native success.

## A2 diagnostic checkpoint: retain the full metric-consistent interval

This checkpoint changes only diagnostic `calibrate_avar_metrics.py` and adds
`tests/test_axis_inference_intervals.py`; it does not change the production
mapper, any raw avar record, or any tolerance. The existing least-squares
best fit and `possible_interval` are retained for compatibility. A separate
`tolerance_consistent_interval` intersects the four affine inequalities with
the original branch domain. Rational arithmetic uses the exact supplied
binary64 values; only the displayed interval endpoints convert back to float.
Flat contradictions and empty intersections return null. A feasible interval
does not reclassify a failure under the old least-squares acceptance decision.

Local validation: **332/332 Python tests, zero skips, 6/6 audits**; full suite
11.346 seconds; `git diff --check` passed. Eight new independent analytical
cases cover positive/negative/mixed slopes, nonzero residual, clipped domains,
flat branches, contradictory constraints and a feasible singleton whose old
least-squares point still fails. Exact source commit
`a7efe8b983a6d1a7ad8e4ce33532d40326444d64` was pushed non-forcibly and the remote
HEAD matched. Native run [39380682143](https://github.com/SOLHK/Swirl/actions/runs/39380682143),
job 118488866332, completed **success** on xcode-27. The verified downloaded
artifact 12244799401 has ZIP SHA-256
`5bc02d3f638b983ff3f7df2c30a42351a9d8e1593388f8aa822c03f7a3267b65`.
All 32 faces / 3,048 native observations completed, exact source SHA matched,
and every pre-existing inference field is identical to the earlier archive.
The new best-branch intervals contain 7–23 F2DOT14 grid points.
This is diagnostic validation, not acceptance of a new mapping formula.

Same-source [39380682203](https://github.com/SOLHK/Swirl/actions/runs/39380682203)
also finished: Python and Windows synthetic DirectWrite **success**; Apple
**failure**, retaining the same raw 849/850 vertical-advance assertion at
0.03125. The actual failure log was read (job 118488867261).

The original archive's best fits are identifiable in the zero-residual sense,
but the 1/32 metric budget generally admits 7–23 neighboring F2DOT14 grid points
for these four GIDs. The previous point interval must not be read as proof of a
unique coordinate at that budget. The **141 simple-model disagreements remain
unresolved**; HVAR agreement still does not establish geometry equivalence.

The latest A1 cache experiment at `f72187f70d0af20fb197fb3e49389b53e8ce31a0`,
[39379538202](https://github.com/SOLHK/Swirl/actions/runs/39379538202),
again completed both independent construction orders, with 36 requests per
order and no request/readback or repeated-request geometry/metric difference.
For face 20 at default width/height, 300 to 300.01 changes native geometry and
horizontal metrics, while 400 to 400.01 changes neither, in both orders.
This is a concrete counterexample for the next threshold experiment, not a
font-specific exception to add to production. Safe cache artifact 12244931341
was downloaded and its ZIP SHA-256 checked:
`d2aee64e54ec4627aba32372a87d0d3cbb0c312fb71717817cfbf4173e62143f`.

The same run's rebuild job failed at the unchanged face 0 / GID 0 vertical
origin X guard (100 FUnit versus 1e-5), after 91 completed batches and 5,824
native observations. Zero GID models/faces completed; no original TTC exists.

Next: fresh native threshold samples around the two equal-slope intervals and
the discontinuous default, with original geometry plus HVAR, independent
process order, and fresh held-out coordinates. Do not repeat the already-run
cache experiment or choose per-point mapping exceptions.

## A2 next experiment: fresh thresholds with native geometry and HVAR

New files: `platform/axis_threshold_cases.py`, `platform/probe_axis_thresholds.py`,
`tests/test_axis_threshold_cases.py`, `tests/test_axis_threshold_probe.py` under
`tools/swirl_vf`, and `.github/workflows/swirl-vf-axis-thresholds.yml`. This is a
diagnostic executable, **not a production mapping repair**. Native execution has
completed; no formula, font or continuous-space pass is declared. Exact source `f51d262352a638d2256f5757171d6e3823a387a7` was pushed
non-forcibly and the independently queried remote HEAD matched. Native
[39381634460](https://github.com/SOLHK/Swirl/actions/runs/39381634460), job
118491837396, finished **success**: diagnostic completion only. The final job
log and safe artifact 12245849108 were read. Its verified ZIP SHA-256 is
`da3b7925a252b08023352ce22f8d059ddf576251e3af4b739762115c556f58a9`.
All 32 faces, 1,724 positions, 64 independent processes and 120,680 glyph
records completed with exact source identity, zero native errors, valid
summary/EOF and zero exit status. Source hash remained unchanged.

Same-source synthetic run
[39381634228](https://github.com/SOLHK/Swirl/actions/runs/39381634228) has finished:
Python and Windows DirectWrite **success**; Apple **failure** at the unchanged
849/850 assertion, tolerance 0.03125 (actual log job 118491836755 read).
The production Swift guard still passes its 22 cases. No new native metric pass
or accepted original font is implied. Compared with the starting remote HEAD,
the existing HVGL, batch geometry, transform, tangent and rebuild source files
are unchanged; all 15 changed paths remain within font tooling/documentation.

Concurrent work preserved: while the native threshold job was running, remote
HEAD advanced from `f51d262352a638d2256f5757171d6e3823a387a7` to
`b096ffac75eec057a901a792a4e81718263943bc` (subscription boundary/URI intent
repair and its independent Core handoff). The complete changed-path list was
inspected: no font-file overlap. Local synchronization is a fast-forward, and
this font handoff is based on that newer commit; no force push or Core rewrite.

The original fvar-only preflight creates **1,724 user positions**, 35 selected
GIDs (the established structural set plus the four HVAR controls), and plans
120,680 actual CoreText glyph records across opposite-order processes. All 32
faces, original tags/ranges/defaults, all 27 corners per face, default-side
16.16/F2DOT14 thresholds, binary64 nextafter neighbors, decimal readback bins
and the equal-slope 300/400 counterexample are retained. The 192 deterministic
random holdouts are absent from the old 3,048-position HVAR sample.

Each face uses two independent CoreText processes. Every process binds all 32
physical faces and all original table hashes and must finish with exact count,
zero-error summary, EOF and zero exit status. Opposite orders compare the whole
typed path/raw metric payload exactly; readback bits are recorded independently.
These processes do not claim to reset macOS's system-wide font-service cache.

Six global mapping hypotheses are precomputed before native observation, then
compared with the unchanged batched HVGL renderer and strict 1/32 comparator.
Two new candidates test normalized-16 truncation before avar from either the
original request or predeclared T(T(x)); neither is chosen per point. HVAR
inversion applies only at exact width/height nodes after checking raw identity
avar and neutral HVAR height regions. Rejected fits cannot create conditioned
design references. Best-fit residuals, full branch tolerance intervals and
neighbor-grid metric residuals are retained; these inferred per-observation
references are explicitly **not** a global mapping or unique tolerance solution.
Selected threshold cases also execute the existing Apple libhvf C oracle and
compare it independently with both CoreText and the portable implementation.

Local focused verification: **16/16 authored tests** pass, covering distinct
binary neighbors, source range preservation, complete face/table identities,
raw payload differences, rejected/clipped HVAR inversions and malformed/truncated
native HVF transcripts. Full regression: **348/348 Python tests, zero skips,
6/6 audits**, with `git diff --check` clean. The separate actual CoreText/libhvf results follow below.
Private original paths and raw advances remain in memory/temporary storage;
only coordinates, GIDs, aggregate discrepancies and identity evidence enter the
safe JSON checkpoint or public artifact. A failed run retains stage/face/request
context and remains FAILED. The existing 141 questions and 849/850 gate remain.

## A2 fresh native result: improved candidate, remaining counterexamples

Every opposite-order pair matches its complete raw typed path/metric payload:
**60,340/60,340**, zero readback differences. Direct Apple libhvf versus CoreText
passes **372/372**, maximum point difference **0**. The portable implementation
versus the same native libhvf cases also passes **372/372**, maximum
`3.410605131648481e-13` FUnit. These direct cases do not include the eight
remaining type failures below; they cannot be used to dismiss those failures.

All six global models remain unaccepted. Each made 60,340 strict geometry
comparisons and 1,724 four-GID horizontal-metric vector comparisons:

| Predeclared model | Geometry failures | Numeric / type failures | Exact metric vectors | Metric vectors over 1/32 |
|---|---:|---:|---:|---:|
| Raw-order float | 1396 | 390 / 1006 | 1026 | 30 |
| Raw-order final F2DOT14 | 938 | 390 / 548 | 1613 | 30 |
| Raw-order two F2DOT14 stages | 940 | 270 / 670 | 1609 | 30 |
| Signed-zero variant | 940 | 390 / 550 | 1609 | 30 |
| Request normalized-16 truncation | 628 | 240 / 388 | 1666 | 20 |
| Predeclared T(T(x)), normalized-16 truncation | 8 | 0 / 8 | 1694 | 0 |

The last candidate's largest comparable point error is
`0.006132067549600606` FUnit; maximum metric error is `0.0032958984375`.
It is a finite diagnostic candidate, not a production fix. Type-failure rows
have null point error and are not counted as zero-error results.
The 30 nonexact metric vectors comprise the existing 400.01 example on all
12 faces 20–31 and six fresh 400-threshold samples on each of faces 20, 24, 31.
All have inferred native weight grid -4915 versus candidate -4914.
The 192 unseen random positions are included in the overall comparison.

All eight remaining type failures are GID 19177:

| Face | WDTH | wght | HGHT |
|---:|---:|---:|---:|
| 0 | 500 | 837.5754436931355 | 500 |
| 1 | 422.3943344488167 | 810.2631054512518 | 344.1305449918785 |
| 8 | 500 | 831.1462518294346 | 500 |
| 15, 16, 17, 18, 19 | 1 | 100 | 1 |

At 1,596 eligible exact width/height nodes, the zero-residual HVAR best-fit grid
reference makes 55,860 geometry comparisons: 7 type failures, zero numeric
failures, maximum comparable error `2.3305801732931286e-12` FUnit. The mixed-axis
face-1 case is not eligible for that inversion. This reference is conditioned
on each observation and is **not** a user-to-design formula or proof of unique
coordinates within the metric budget. Neighbor grid references retain their
own failures in the safe artifact.

Offline falsification after the new run: a generic raw-interval rule using
pre-avar F2DOT14 rounding only when the chosen interval ends at (0, 0) fits all
3,048 old observations and removes these 30 fresh 400-threshold discrepancies.
It nevertheless fails two unseen weight holdouts: face 25 at
`482.20654224674365` (native -874, predicted -875) and face 30 at
`462.34568323838` (native -1851, predicted -1850). Their zero-residual HVAR and
recorded geometry independently distinguish the grids. This rejected rule is
not installed in production. Original avar order and duplicates remain intact.

Next smallest task: execute the existing native libhvf oracle on the eight
remaining GID-19177 cases and retain raw L/Q controls privately to distinguish
true curve changes from canonicalization sensitivity; keep the strict result
visible. In parallel, collect only discriminating 300/400 threshold neighbors
and the two fresh falsifiers. Do not smooth discontinuities, drop type failures,
or alter the original 1/32 threshold.

Concurrent commits `ac0069ec645b552835d15534b93d6d2ae0c69620` and
`5f16245a238411c8e57d097995fded50edc65522` were also inspected and fast-forwarded
before saving this evidence. Their Core / Qt / subscription files do not
overlap the font changes and remain preserved. No font production model,
original GID completion count, original TTC output, raw 849/850 status or
Windows 11 / Qt acceptance status changes at this diagnostic checkpoint.

## A2 narrow follow-up: preserve strict failures and inspect raw segments

New diagnostic files: `platform/probe_axis_counterexamples.py`,
`platform/diagnose_path_types.py`, `tests/test_axis_counterexamples.py`,
`tests/test_path_type_diagnostic.py`, and workflow
`.github/workflows/swirl-vf-axis-counterexamples.yml`. The existing
`probe_axis_thresholds.hvf_paths` delegates to a factored `hvf_events`; every
native header/event/counter/summary check remains in force before raw events
are exposed privately. No production renderer, mapping or strict comparator
is changed.

Preflight against original fvar ranges creates **324 user positions on 13
selected faces**, five GIDs and **3,240 planned actual CoreText records** in
two independent opposite-order processes. Both processes must verify all 32
physical source identities/table hashes. The eight GID-19177 cases, decimal
neighbors of six normalized-16 steps on both sides of 300/400, different-slope
300-left half-grid neighbors, two rejected-rule controls and **40 new random
holdouts** are predeclared before any observations. Direct Apple HVF checks
cover the type failures and selected narrow thresholds; per-observation HVAR
references remain separate from every global candidate.

Three stable platform controls also distinguish a concrete arithmetic hypothesis
before native execution: at weights 300.025, 400.025, 399.968 on faces 20/24/31,
canonical normalized-16 plus exact binary64 interpolation predicts grid
(-9829, -4914, -4916). Float32 interpolation with half ties toward positive
infinity predicts (-9828, -4913, -4916); half ties away from zero predicts
(-9829, -4914, -4917). The equal-slope .0062/.01 counterexample alone cannot
distinguish these arithmetic stages. No prediction is counted as observation.

The separate raw-path diagnostic preserves each original L/Q control privately
and reports the unchanged strict comparison beside analytical evidence. Only a
unique forward cyclic endpoint correspondence permits a continuous parametric
curve-difference bound. Exact rational arithmetic evaluates endpoints and
quadratic derivative roots, with outward rounding of the reported upper bound.
No sampled curve fit, reversed contour, merged segment or accepted mapping is
introduced. Public evidence contains only indices, types and scalar differences.

Local validation: **362/362 Python tests, zero skips, 6/6 audits**, full suite
13.744 seconds, clean `git diff --check`. Fourteen new tests include true
curvature, short chords, control-point overshoot, non-midpoint collinear
quadratics, ambiguous/reversed correspondence, exact between-sample extrema,
safe output and a three-way fixture whose strict type failure must remain
rejected even when the independent curve bound is tiny. This checkpoint is a
validated diagnostic implementation. Exact source
`619ec70181858815a23ba8c80adc63ab206dd2f3` was pushed and remote HEAD verified.
[39384574612](https://github.com/SOLHK/Swirl/actions/runs/39384574612), job
118501233885, completed **success** on xcode-27. Artifact 12247320036 was
read and its ZIP SHA-256 verified:
`cc5c37b0bed6e010ed41f66d8b190f9a568f95000d91c97338a7c2ac0c085426`.
This is diagnostic completion; no production mapping/font is accepted.

Both independent processes completed 324 requests / 1,620 records each, all
32 physical source identities and final summary/EOF/exit checks. All 1,620
opposite-order complete raw payload pairs are exactly equal, with no readback
differences. Source hash is unchanged. The six global candidates still retain
all eight strict type failures. The canonical normalized-16 candidate has
225/324 exactly matching metric vectors, none over 1/32; maximum metric error
is 0.006591796875 and maximum finite point error is 0.01110839843784106.

The new direct native comparison proves the scope of the eight type failures:
Apple HVF and CoreText are exactly equal at **all eight original failed cases**.
Both original commands of each mismatched segment are quadratic, but the old
canonicalizer classifies the portable one as L and the native one as Q. The
very short nonzero chord amplifies tiny control-point rounding into a projection
outside its dimensionless interval. This is not the short-chord branch. The
actual differing segment is path 7 / segment 3 on faces 0, 8 and 15–19; on
face 1 it is path 11 / segment 3. Exact rational continuous parametric bounds
for the entire corresponding glyph are at most `2.652692880171041e-13` FUnit.
The original eight strict failures are still reported; no tolerance or line
classification threshold has been changed to hide them.

Across all direct hypotheses there are 260 native HVF / CoreText comparisons,
zero strict failures and maximum point error 0.010740169102945174. That aggregate
includes intentionally wrong inferred/global coordinates and is not an exact
mapping claim. The eight type cases themselves are exactly equal. Portable /
HVF retains eight canonical type failures; its other comparable point errors
are at most `4.547473508864641e-13`.

The quantization investigation has a distinct new counterexample: on faces
20, 24 and 31, every tested weight from 399.9633 through 400.04 gives native
HVAR grid -4915, while 399.96 gives -4917. This is a finite set spanning several
ordinary quantization steps, **not proof of all values in a continuous interval**.
The predeclared three platform points give (-9829, -4915, -4915), contradicting
each full arithmetic prediction above. Real native HVF / CoreText geometry
at the accepted HVAR reference corroborates these observed grid values.
Do not turn this platform into a per-coordinate production exception. At
299.9817 another discrepancy remains (-9831 native versus -9830 canonical);
float32 normalization is a separate unverified mechanism worth distinguishing.

Same-source [39384574478](https://github.com/SOLHK/Swirl/actions/runs/39384574478)
finished with Python and Windows synthetic DirectWrite **success**, Apple
**failure**. Actual Apple job 118501233362 still reports raw 849 versus 850 at
0.03125, and the production Swift validator passes 22 cases. The separate
full 1,724-position rerun
[39384574416](https://github.com/SOLHK/Swirl/actions/runs/39384574416) is still
IN_PROGRESS at this evidence checkpoint; its final result must be retrieved.

Next minimal work: preserve the old canonical report and add a conservative
raw-Q/Q control-point comparison only where that report rejects segment types;
all six original quadratic coordinates must meet the unchanged 1/32 budget,
without rescuing existing numeric or topology failures. Separately locate the
400-platform boundaries and test constructor/base-instance dependence before
assigning any internal Apple mechanism. Concurrent Core commit
`1e45e4af4d490dbfc49c20a590258ab55587c6eb` was inspected and preserved by
fast-forward; it has no font-path overlap.

## Preserve quadratic controls at a canonical type-only rejection

`platform/diagnose_path_types.py` adds `compare_preserved_quadratics` without
editing any existing comparison function. `probe_axis_counterexamples.py`
reports its result alongside the unchanged canonical and parametric results
for the eight known cases. The two corresponding authored test modules are
updated. The source mapper, renderer, reconstruction code and original avar
records remain unchanged.

Each contour first executes the old comparator. Only its exact
`segment_types_differ` rejection can enter the new branch. Canonical same-type
segments keep the old fields/error calculation. A canonical L/Q mismatch must
have **original Q/Q commands on both sides**; all six original coordinates are
then compared under the unchanged 1/32 L-infinity control-point budget.
Restored differences use exact rational subtraction of input binary64 values
and round outward. Raw L/Q mismatches are never degree-elevated for acceptance.
Numeric failures, topology failures and the old forward-cycle policy remain.
The original rejected result and every restored segment index stay in the report.

Local regression: **374/374 Python tests, zero skips, 6/6 audits**, full suite
12.557 seconds, `git diff --check` clean. Twelve additional independent cases
cover exact/nextafter limits, true curvature, raw L/Q rejection, orientation,
cross-contour and same-contour numeric failures, and a binary64 subtraction
that would otherwise round a true over-budget difference down to exactly 1/32.
The diagnostic integration preserves the old failure even when the new raw-Q
control comparison passes. Exact source
`2518e7e4d87623b118c37a72f1cffb2538e82db9` was pushed non-forcibly and the
remote HEAD independently matched. Native
[39385586825](https://github.com/SOLHK/Swirl/actions/runs/39385586825), job
118504523929, completed **success**. All eight original type-only failures pass
the new original-Q control-point comparison, maximum
`3.410605131648481e-13` FUnit, without changing the 1/32 budget. Each has one
restored segment. Native HVF / CoreText needs no restored segment and is exact.
The old global-model, HVAR-conditioned, direct-strict and opposite-order fields
are identical to the prior 619ec701 artifact; all old failures remain visible.
Both processes completed 324 requests / 1,620 records, zero errors and valid
summary/EOF/exit, with full 32-face identity and unchanged source. Downloaded
artifact 12247188502 has verified ZIP SHA-256
`fb640bc42bbaf2acef879b1b22b7b0f204231d08611902c961046055f5227fe6`.
This validates the conservative comparison on these eight cases; it does not
accept a production mapper or a reconstructed font.

Same-source [39385586778](https://github.com/SOLHK/Swirl/actions/runs/39385586778)
finished: Python and Windows synthetic DirectWrite **success**, Apple
**failure**. Actual log 118504524101 was read: raw vertical advance 849 versus
850 at unchanged 0.03125; the 22-case production Swift guard still passes.

The full threshold rerun at source
`619ec70181858815a23ba8c80adc63ab206dd2f3`,
[39384574416](https://github.com/SOLHK/Swirl/actions/runs/39384574416), job
118501232869, has now completed **success**, superseding the running status
above. Downloaded artifact 12247761673 has verified ZIP SHA-256
`c2c9435be3460739b7c7e8c08e92a6bcf130db8c845bb85842f0e04905013044`.
Every top-level field equals the prior f51d262 report except `source_commit`,
including all 32 face reports, 1,724 positions, 120,680 records, all model
failures, native comparisons and process summaries. This proves repeatability
of the recorded finite diagnostic, not that its failed model is accepted.

Concurrent Core evidence/test commit
`f19b0ad51058580a8a0ed73008b22754e6f45ea0` was inspected and preserved by
fast-forward; none of its four files overlaps this font change.

## A2 next diagnostic: constructor and base-instance plateau boundaries

New files: `platform/plateau_construction_harness.py`,
`platform/probe_axis_plateau.py`, `tests/test_plateau_construction_harness.py`,
`tests/test_axis_plateau.py` under `tools/swirl_vf`, and
`.github/workflows/swirl-vf-axis-plateau.yml`. Local validation is
**386/386 Python tests, zero skips, 6/6 audits**, full suite 20.262 seconds;
`git diff --check` is clean. The 12 additional tests cover generated-source
contracts, refusal conditions, complete-payload comparison, mode restoration
and predefined source-range samples. They are not native Swift execution.

The new experiment selects seven representative faces, 287 fixed locations,
five GIDs and five constructor modes, each in separate forward/reverse
processes: **14,350 planned native records**. Modes are the unchanged production
constructor, existing descriptor and graphics alternatives, and production
copies from fully identity-verified bases seeded at wght 300 or 500. Alternative
paths do not preconstruct the production baseline. The full production Swift
prefix, strict guard, source SHA, 32-face table identity, extraction and native
termination contracts are retained. The harness is explicitly diagnostic and
must never be supplied to `rebuild.py` as an accepted oracle.

The report retains original and seeded base axis observations, full-payload
and raw-command equality, every scalar/vector metric difference, readback
differences, and conditional independent HVF checks. Only safe differences and
identity summaries are published. Samples cover the 400 plateau boundaries,
300 controls, original defaults and mixed WDTH/wght/HGHT. No font-specific
mapping rule or constructor is promoted. Exact source
`c6c5dd8c5eef829614cfce1950c616e501357537` was pushed non-forcibly and the remote
HEAD independently matched. Native
[39386727297](https://github.com/SOLHK/Swirl/actions/runs/39386727297), job
118508223685, completed **success**. Artifact 12248385248 was downloaded and
verified: ZIP SHA-256
`86986038391cc0dc62acccd2abaf036307678ef0fd720f9e8d99695d86934b78`.
All ten processes completed 287 requests / 1,435 records each, zero errors,
valid summary/EOF/exit, all 32 physical identities and unchanged source. All
7,175 forward/reverse pairs are exactly equal, including readback. The 70
selected conditional native HVF / CoreText geometry comparisons have **zero
error**, confirming the selected HVAR grid references independently.

All 32 original descriptor bases actually report `wght=400`, at 12 points.
Production and descriptor-copy observations are completely identical. The
finite 400-neighborhood platform now brackets as follows: 399.96 is outside,
399.9601 through 400.04 sampled points share the 400 output, and 400.0401 is
outside. On faces 20/24/31, q at these outside/inside/outside examples is
(-4917, -4915, -4913). This is not a claim about every point between samples.

**The platform depends on the construction base.** With a base explicitly
seeded at 300, the 400 platform disappears and the sampled 300.0062, 300.01 and
300.03 observations give q(300)=-9830 on faces 20/24/31; 300.04 gives -9828.
With the base seeded at 500, the ordinary 300.0062/300.01/300.03 value -9829
returns. Both seeded bases have the same UPEM size, so this difference cannot
be explained solely by changing the base size. At 400.04 both rebased modes
give -4913 instead of production's -4915. All these requests still report the
same user coordinates; API readback equality is not instance equality.

Relative to the production run, descriptor copy has zero payload or readback
differences. Graphics-copy-with-tracking has 150/1,435 payload differences and
700/1,435 readback differences; rebase_300 has 475 payload differences and
rebase_500 has 360, with zero readback differences for either rebase mode.
Maximum canonical point difference is 0.01110839843784106 FUnit; maximum
metric difference is 0.00686192512512207. These are maxima of numerical
comparisons; **each rebase mode also retains one canonical type rejection** at
face 10 / GID 19177 / WDTH=600.5859375, wght=400.04, HGHT=250. The safe report
records `segment_types_differ`; a small numeric maximum must not imply that
these rejected comparisons passed. Graphics-copy also produces a
300 platform and shifts the upper 400 boundary; it is not an equivalent fix.

The observation supports base-dependent near-coordinate reuse; it does not
prove an undocumented internal relative-tolerance constant or a global mapping
formula. No production construction change has been made. Next smallest task:
predeclare a far-axis anchor construction that avoids proximity to the target,
then compare actual native geometry/HVAR and complete readback replay across
independent initial bases, original defaults/extrema, mixed axes and fresh
held-out coordinates. Keep all raw avar records and all old strict failures.

Same-source [39386727229](https://github.com/SOLHK/Swirl/actions/runs/39386727229)
finished: Python and Windows synthetic DirectWrite **success**, Apple
**failure**. Actual job 118508223730 log was read: raw vertical 849 versus 850
at 0.03125 remains; the 22-case production Swift guard still passes. There is
still no accepted original GID model, completed original face or output TTC.

## A2 next diagnostic: predeclared far-axis anchors and independent references

The next source checkpoint adds `platform/anchor_construction_harness.py`,
`platform/axis_anchor_cases.py`, `platform/probe_axis_anchor.py`, their three
test modules and `.github/workflows/swirl-vf-axis-anchor.yml`. Production
Swift, production mapping and rebuild code remain unchanged. The generated
harness binds the reviewed production prefix and keeps it byte-for-byte.

Four experimental modes are separate from the unchanged production control:
far endpoints from original / wght-300 / wght-500 bases, and far quarter-points
from the original base. Each request independently plans all three anchor
coordinates using original ranges and the requested target, then makes exactly
two production-helper copies. Every axis is separated from its target by at
least half (endpoint) or a quarter (quarter-point) of its full raw range.
No prior request, observed coordinate, fitted HVAR result or retry chooses the
anchor or target. Anchor echoes must be exactly predeclared, and both copies
must preserve the production optical selection. All original and seeded bases
retain full table identity; the ordinary helper retains its own instance
identity, output UPEM, matrix and tracking checks.

The experiment has **736 fixed user positions**, seven representative faces,
five GIDs, five modes, both request orders, and original plus predeclared
T(T(x)) replay per request: **73,600 planned native glyph records**. Cases
include original defaults/extrema, endpoint neighbors, 300/400 boundaries,
anchor-choice midpoints, mixed axes and 84 new random holdouts with seed
20861020+face. All positions, replay declarations and both global model
predictions are fixed before the first native process starts. Readback and
complete-payload replay use the existing strict policy, with all failures
retained; diagnostic observations are never released to a builder.

The original double-normalize/16-bit-truncate candidate is compared separately
with a predeclared double-normalize, float32-result cast, then 16-bit-truncate
candidate. Both preserve original ordered avar records and duplicates. Every
model has its own legacy and preserved-Q geometry verdict, HVAR metric error,
and selected direct native HVF checks. HVAR-inferred coordinates remain
explicit conditional references, not global model outputs. Cross-base and
cross-anchor equality retains all payload fields, including origins and bounds.

Local final regression: **413/413 Python tests, zero skips, 6/6 audits**,
15.676 seconds; `git diff --check` clean. An earlier in-progress full-suite
snapshot caught an optical helper variable-name contract mismatch and duplicate
generator helpers appended after `run`; both are corrected without dropping
assertions, and the complete final frozen source passed. The new 27 independent
tests include failure preservation, exact replay, hidden payload changes,
raw-record ordering, anchor/range logic and generated-source rejection. Exact
native transport wrappers retain only a whitelist of public failure codes;
arbitrary native error text and private payload remain excluded.
Native compilation and execution were pending when this source checkpoint was
pushed; their subsequently retrieved final result follows below. No production
constructor change is accepted by the diagnostic alone.

Concurrent Core commit `8841244f17cfae92f0f025ad8ac00c5796a01fb0` was inspected
and preserved by fast-forward. Its Qt JSON-reload test and evidence changes
have no font-path overlap. No force push or overwrite was used.

## A2 far-axis anchor native result: finite construction independence

Exact source `aea46364186e0098cf432d0a3a7a1c0aa3c0d761` was pushed non-forcibly
and independently confirmed at remote HEAD. Native
[39388682680](https://github.com/SOLHK/Swirl/actions/runs/39388682680), job
118514656189, completed **success** on macOS 27.0.1 / xcode-27. Its final log
and artifact 12249245192 were retrieved; ZIP SHA-256 is
`32f90fd81218bfc6c09be23a4d08c27f04b7db1589e9f564bfcf61eaf8bd7a71`.
The report itself correctly says `COMPLETED_NATIVE_ANCHOR_DIAGNOSIS_NOT_ACCEPTANCE`.

All ten independent native processes completed 1,472 requests / 7,360 glyph
records, zero native errors, complete summary/EOF/exit and all 32 physical
identities. The source hash remained unchanged. The actual total is **73,600
records**. All **36,800 opposite-order pairs** match complete payload and
readback exactly. All **7,360 original/replay batch checks** pass the unchanged
production readback policy and exact complete-payload equality.

The four anchor modes give identical full payloads and readbacks at every one
of the 736 positions / 3,680 glyphs. This includes independent original/300/500
initial bases, endpoint versus quarter-point anchors and mixed/random cases.
Against the original one-copy production construction, each anchor changes
31 positions / 155 glyph payloads and raw paths, while all 3,680 user-coordinate
readbacks remain exactly equal. This independently confirms that matching an
API echo cannot establish matching geometry. It also bounds the new result:
the chosen construction removes the observed base-dependent behavior; it does
not prove that every possible public CoreText construction is equivalent.

The two predeclared global models distinguish the remaining arithmetic issue:

| Construction / candidate | Exact HVAR positions | Preserved-Q geometry | Maximum point error | Direct native HVF/CoreText |
| --- | ---: | ---: | ---: | ---: |
| Original production / double-normalized16 | 699/736 | 3680/3680 | 0.01110839843784106 | Not requested for global model |
| Original production / float32-normalized16 | 705/736 | 3680/3680 | 0.01110839843784106 | Not requested for global model |
| Each far-anchor / double-normalized16 | 730/736 | 3680/3680 | 0.005554199218977374 | 72/72 within budget; max 0.005370084551472587 |
| Each far-anchor / float32-normalized16 | **736/736** | **3680/3680** | **5.684341886080801e-13** | **72/72 exactly zero** |

Both models apply the predeclared C=T(T(x)) user coordinate. The second casts
only the result of double-precision normalization to float32, then truncates
to 16 normalized fractional bits, evaluates untouched raw ordered avar records
(including repeats and zero behavior), and finally rounds to F2DOT14. It does
not cast the input user coordinate or every arithmetic operation to float32.
The six remaining double-model HVAR disagreements are faces 20/24/31 at
wght=299.9817, with either default WDTH/HGHT or WDTH=600.5859375, HGHT=250.
The float32-result candidate removes all six and matches independent native
geometry, rather than merely fitting the previously archived HVAR observations.

Each anchor retains **two legacy `segment_types_differ` results**, face 10 /
GID 19177 at (WDTH=600.5859375,wght=400.01,HGHT=250), and face 15 / GID 19177
at (1,100,1). The already-native-validated preserved-Q comparison passes these
without relaxing 1/32, altering paths or concealing the old failures. The
original production control retains three legacy type rejections. Each mode
also has 435 eligible conditional HVAR grid inferences and 40 selected
conditional native HVF comparisons, all with zero geometry error. Conditional
results remain distinct from the global model; the native HVF cache contains
84 actual unique invocations and is never a CoreText instance cache.

**Production mapping and construction remain unchanged.** The next smallest
task is the same predeclared model/construction on all 32 faces, the old 3,048
locations, the existing structural GIDs and fresh held-out points, with exact
replay and independent native geometry. Do not call the finite 736-position
result continuous-space losslessness, or declare the historical 141 cases
fully resolved before the expanded real-source comparison.

## Same-source strict metric evidence rechecked, without rerunning old hypotheses

Same-source [39388682346](https://github.com/SOLHK/Swirl/actions/runs/39388682346)
finished with Python and Windows synthetic DirectWrite **success**, Apple
**failure**. Job 118514654842's actual log and final artifact 12248497276 were
read. ZIP SHA-256:
`418efaf1b82b0141fc8064d498c89f3bfa463f19a345161da9d142b24725b1bb`.
The artifact records macOS 27.0.1 build 26A434 / Xcode 27.0 build 27A266a;
commit.txt and all three bound extractor/metric-test/diagnostic source hashes
match this source. The 22 production Swift axis guards pass. Native extraction
exit 0 still accompanies **strict FAIL**: face 0 / GID 2 at all-min axes,
raw vertical CGSize.width **849 vs 850**, tolerance **0.03125**.

The current 144-observation three-path diagnostic has gvar-only **30/48** and
equivalent HVAR/VVAR with explicit bearing maps **4/48** outside budget; older
29/48 and 6/48 counts must not be reused for this run. The 1,044 equivalent
standard coefficients still have zero error. At integer height endpoints,
gvar-only 849/1149 becomes 850/1150 with the equivalent tables. At the internal
fractional positions, the ideal 1063.3375 becomes 1062 in gvar-only and 1063
with the equivalent tables: **0.3375 FUnit remains**. Face 1 / UPEM 1128 also
has gvar-only default height 999 versus 1000, so this is not solely nondefault
variation behavior. No OS or code cause is inferred merely from changed counts.

The four-size precision report has 2,088 observations and 2,784 measured CTRun
advances. Every normalized direct metric dictionary is exactly the same at
0.25/1/16/64 times UPEM, and every measured CTRun advance exactly matches its
direct counterpart. Per-size outside-budget counts remain 107/174 for
gvar-only and 4/174 for either table variant. Production HVAR/VVAR's origin Y
still differs by 0.335; explicit bearing maps reduce that to
0.00394531250003638, but neither removes the fractional height loss.

Static instances match all their own serialized advance widths/heights
exactly. Their **20/48** raw-origin failures consist of 16 blank glyphs and
four odd-width half origins (width 735, raw X 367 vs table half-width 367.5).
Static 1063 vs ideal 1063.3375 is a serialization loss, distinct from raw API
loss against a continuous variable-table model. SourceTables reconstruction
still explicitly retains the old strict FAIL; its 174 path/table checks and
two six-record static groups are not raw API acceptance. The existing local
16.16/phantom hypothesis has 42/42 matching predictions on 14 nondefault
GID-2 samples, but no independent UPEM-1024 or translated-phantom experiment
has yet isolated its mechanism. Do not repeat the old size/CTRun experiments.

## A2 next checkpoint: all 32 faces and the historical 141 as direct-native cases

The preceding verified native evidence was committed as
`0f03f7ff1e4b9ac9afe1907103b5cc13a824cc1c`, pushed non-forcibly, and independently
confirmed at remote HEAD before this next implementation began.

The fixed `closure_all_faces` profile reuses the same diagnostic transport,
constructor, predeclared models, strict replay and independent comparisons.
The default `anchors_736` profile retains its existing five modes and sampling.
No production Swift, mapping, HVGL algorithm or rebuild implementation changes.
New files are `axis_mapping_closure_cases.py`, `axis_mapping_closure_archive.py`,
their independent test modules, the compact safe
`tests/data/axis_mapping_archive_20261020.json`, and workflow
`swirl-vf-axis-mapping-closure.yml`; the shared driver/test and both handoffs
are updated.

The new profile contains **5,356 positions on all 32 faces**. It invokes the
existing `calibrate_avar_metrics.requests_for(fonts)` unchanged, retaining all
**3,048 old requests**, their order, IDs, binary64 coordinates and duplicates.
The 2,308 additional rows include 27 min/default/max combinations per face,
near-default values, anchor midpoints, 300/400 boundaries, mixed axes, the
original fractional WDTH blockage and **256 fresh three-axis holdouts** using
seed 20961020+face. New duplicate coordinates add provenance labels to the first
old occurrence; they never delete an archived observation.

Before any native launch, `prepare_archive` binds the complete old coordinates
to the downloaded actual native archive using per-face binary64-hex location
and location/q hashes. The 26,285-byte fixture stores only the actual 3,048
conditional HVAR grid integers, hashes, 141 historical failing indices and
provenance, with no advances or paths. Fixture SHA-256 is
`3eca463b6eb42df74565b6f25047a93f4dc9e6219d872a4ac070815f1c9b2bc1`;
the bound original safe JSON SHA-256 is
`1905e7a6beb77cd67424a14c567961698cda948889428090f9a0452396d4a91f`.
That JSON comes from source `a7efe8b983a6d1a7ad8e4ce33532d40326444d64`, run
39380682143, artifact 12244799401, whose ZIP hash is already recorded above.
Candidate predictions never substitute for historical measurements.

The direct Apple HVF subset is fixed before native execution: **all 141 old
disagreements**, plus each face's default, eight min/max corners, first fresh
triple, 299.9817 and 400.01 weight controls. This gives **525 positions**, each
with GIDs 5 and 19177. All 5,356 positions also retain the four HVAR glyphs and
GID 19177's portable/native-path comparison. The unchanged production control,
endpoint anchor and independent quarter-point anchor each run in both orders,
with original plus predeclared replay: **321,360 planned glyph records**.
Native HVF observations may be reused only for an identical verified
face/GID/design tuple; CoreText instances are never cached across requests.

Final audit separates original-production archive reproduction, actual changed
anchor q values, candidate/HVAR exactness, legacy and preserved-Q geometry,
actual direct-native coverage, replay and request-order results. Missing direct
native coverage for any historical-141 anchor case remains explicitly
unresolved. Every summary retains `mapping_accepted=false` and
`continuous_space_accepted=false`; valid numeric failures remain visible.

Local frozen regression: **432/432 Python tests, zero skips, 6/6 audits**,
15.464 seconds, `git diff --check` clean. Real private-source read-only planning
also verified 32 faces, all 3,048 archived rows/hashes, 141 fixed old indices,
5,356 total positions and 525 direct-reference positions. The candidate matches
the old inferred q on those 141 archived rows locally; this is **not a new
native result**. Enlarged native execution is pending at this source checkpoint.
Next task: retrieve its actual final results, verify source/termination and
every unresolved row, then save evidence before any production promotion.

## Production admission: reject diagnostic observations at every rebuild session

The all-face diagnostic source is pushed and independently remote-confirmed as
`b549ccdf0c28ec4d38ecc3893f2d149049882970`.
[39391013239](https://github.com/SOLHK/Swirl/actions/runs/39391013239), job
118522247190, is still **in progress**, not PASS. Its bounded old 736-position
profile repeat [39391012999](https://github.com/SOLHK/Swirl/actions/runs/39391012999),
job 118522246091, finished **success**. The actual log and downloaded artifact
12249194164 were checked; ZIP SHA-256:
`f478b8c1e299c372844104974de0beef503264bbe8427f6ecc80325652b9b51e`.
Every old summary field exactly equals the aea native result except source SHA;
the only added fields are `diagnostic_profile=anchors_736` and
`direct_native_reference_positions=36`. This verifies no measured regression
in the shared driver after adding the all-face profile.

The same-source companion run
[39391013019](https://github.com/SOLHK/Swirl/actions/runs/39391013019)
finished Python/Windows **success**, Apple **failure**. Actual Apple job
118522247042 logs retain 22/22 Swift guard checks and the strict raw vertical
advance failure, face 0 / GID 2 at all minima: **849 versus 850**, tolerance
0.03125. The SourceTables reconstruction result cannot override that failure.

A separate actual CLI counterexample, using only an original two-face/three-GID
temporary fixture and a real authored protocol child process, exposed that
`rebuild.run` accepted `axis_observations_only=false` together with
`diagnostic_readback_observation_only=true`. It issued the first sampling
request; only the fixture's deliberate error stopped reconstruction. This is
not evidence that an Apple font was reconstructed or that any diagnostic
instance was production-accepted in a native build.

`tools/rebuild.py` now checks the diagnostic marker in **every production
`open_session`**, immediately after metadata transport, before sampling or
checkpoint creation. Missing preserves the legacy strict protocol; an explicit
value must be the JSON boolean false. True, 0, 1, null and strings are rejected.
The shared `NativeOracle` remains available to diagnostic drivers. No numeric
tolerance, source mapping, Swift construction, v2 payload/replay policy or
metric field changes. In particular, the upstream `NOT_ACCEPTED` explanatory
string is not used as a false rejection of already verified v2 metadata.

Changed files: `tools/rebuild.py`, `tests/test_native_protocol.py`,
`tests/test_rebuild_checkpoints.py`, and both continuation handoffs.
The original CLI regression first failed on all ten diagnostic/malformed-marker
subcases before the fix. It now verifies ordinary and checkpointed entry,
exact rejection stage, zero requests, no output/checkpoint, and unchanged
source bytes; real original SFNT table identities are provided so unrelated
identity gates cannot substitute for this check. Legacy missing/false metadata
still reaches sampling, and direct diagnostic transport still works. A second
session test proves a verified first-face checkpoint is retained when the next
session's diagnostic metadata is rejected before any new sampling.

Frozen local regression: **436/436 tests, zero skips, 6/6 audits**, 37.462
seconds; `git diff --check` clean. Actual native CI for this new admission fix
is not yet run at this commit checkpoint. Next: obtain and save the all-face
closure's final source-bound native results, then consider the smallest
explicit production-construction bridge. Do not promote the diagnostic binary
or enter full reconstruction. Original completed faces remain **0/32**.

## A2/A3 boundary: freeze six input-resolution observations before promotion

Production admission source **`9f4d9882255bd36f804d0bd639966ad65677fc31`** was
non-forced pushed and independently confirmed as remote HEAD. Its
[39392843327](https://github.com/SOLHK/Swirl/actions/runs/39392843327) finished:
Python job 118528286230 **success** (436 tests, seven optional HarfBuzz skips;
the local frozen run had zero skips), Windows job 118528285590 **success**,
Apple job 118528285313 **failure**. Actual logs were read: the existing 22 Swift
guards pass, but raw face0/GID2 all-minimum vertical advance remains **849/850**
at 0.03125. This is not a new metric fix or a whole-job PASS.

The same-source real reconstruction
[39392843364](https://github.com/SOLHK/Swirl/actions/runs/39392843364) passed
its original construction preflight, then job 118529050437 actually ran the
builder and **failed**. Its safe final log confirms all32 identities, unchanged
source, 91 completed batches / 5,824 glyph observations, zero completed glyph
models and zero completed faces. The unchanged blocker is face0/GID0, WDTH=1,
wght=501, HGHT=500: vertical-origin X differs from the standard vmtx model by
**100 FUnit**. No TTC was generated; no new native transcript finalization is
claimed after this failure. The default strict probe 39392843518 also remains
failed at the known fractional WDTH readback; it is a separate unchanged path.

The 32-face b549 diagnostic
[39391013239](https://github.com/SOLHK/Swirl/actions/runs/39391013239) now has
actual final **success**, and all three mode logs report 5,356 positions with
zero failed replay batches. Artifact 12250517308 has GitHub ZIP SHA-256
`e29c2b663330845e16135ec35e760f7a4cf70a99814db0e4ff9e2ac30404f018`.
The complete native/archived-141 audit is not yet interpreted at this source
checkpoint. A workflow's diagnostic success is not production acceptance.

Before changing production construction, the independent numerical review
identified a deliberately small new falsification case on face15, with original
WDTH=HGHT=500. Requests **wght=499.006199 and 499.006201** are different binary64
values but both round to Fixed integer **32702870**, exactly
499.006195068359375. The already fixed source candidate instead predicts
C=499.0061/499.0062 and design q=0/65 in F2DOT14 integers. This is a **prediction,
not an observed native split**. Four controls are default499, each C, and the
common exact Fixed input. No new model is fitted to these six positions.

`platform/probe_axis_input_resolution.py` reuses the existing production-prefix
bound diagnostic constructors, both predeclared models, exact original/replay
policy, complete opposite-order payload checks and original strict raw-Q
comparator. It selects the existing structural set plus HVAR glyphs: **35 GIDs**,
13/13 Type2 shapes, maximum tested hierarchy depth12, four rotation-bearing roots.
All selected GIDs undergo portable/native comparison; **direct Apple HVF is
limited to GIDs5 and19177 at every point**, with explicitly separate conditional
HVAR references. Three constructs / two orders / original+replay plan **2,520
records**, six fully identity-checked native processes. The original source,
all payloads and native logs stay private. Only coordinates, counts, differences
and explicit failure verdicts are emitted.

New workflow `swirl-vf-axis-input-resolution.yml` runs xcode-27 and publishes
only the safe summary. Twelve independent original tests cover Fixed ties for
both signs, the six-point contract, independent rational cell bounds, distinct
locations with identical payloads, unknown-field differences without disclosure,
blank fractional origins, identity mismatch, and a true 0.5 control error which
remains failed in both legacy and raw-Q results. Frozen full regression:
**448/448, zero skips; 6/6 audits**, 50.261 seconds. No native execution of this
new probe is claimed at this checkpoint. Changed files are the new probe,
workflow/test and these two handoffs; existing mapping/constructors are unchanged.

The official [OpenType normalization specification](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview#coordinate-scales-and-normalization)
requires user input in16.16 with nearest conversion and ties to the higher
integer. This diagnostic tests that processing boundary. It does **not** assert
that every platform follows one precision path or that every standard-font
representation is impossible. Actual source behavior, exact replay and error
magnitudes must be measured first; a nonzero split alone is not a proof that
both sides cannot fit the1/32 budget. `standard_format_impossibility_proved`
remains false.

## Newly retrieved prior evidence (not new execution in this continuation)

- At exact source `056f7ea6dc7cf3a703da63e8522b89d33d1166f4`,
  [39374382394](https://github.com/SOLHK/Swirl/actions/runs/39374382394)
  completed all three actual-layout jobs successfully. The downloaded CoreText
  artifact 12243395032 has ZIP SHA-256
  `9a3cb17c0f0bb970a86eca90defc14e7318e0fc947018f7d2994c75431b7f9e1`.
  Its six fixture processes completed 2,016 layout calls, 1,764 paired glyph
  comparisons, zero native errors, zero GSUB/regional differences and zero
  source/candidate raw-metric differences. This confirms the earlier fixture
  registration repair's execution, not production origin equivalence.
- Same-source [39374382335](https://github.com/SOLHK/Swirl/actions/runs/39374382335)
  passed Python and Windows synthetic jobs; Apple job 118469106724 still
  failed the strict raw metric check: face 0, GID 2, height 849 versus 850 at
  tolerance 0.03125. The failure is retained and must not be hidden by the new
  axis-logic tests.
- The earlier 3,048-location HVAR evidence was downloaded and its archive hash
  rechecked as `0b6323fb51d03d13f70266facd9ced88f1b06107d96077e6070cb8e3579f09ba`.
  Existing code reproduces the 141 simple-model disagreements. The previous
  normalized-16 truncation candidate has 36 other disagreements; neither is a
  complete explanation or an accepted geometry mapping.

## Next smallest task and unchanged blockers

With the bounded A1 result recorded, continue A2 with the existing raw-order
avar diagnostics and independent native outlines/HVAR. Do not replace the 141
questions with a formula fitted only to archived advances. Preserve all raw
records and duplicates and the 1/32 geometry threshold.

The 849/850 raw metric failure, independent vertical X-origin representation,
all-face/all-GID reconstruction, Windows 11 and Qt/Swirl acceptance remain
unresolved. Original completed GID models: **0**; original faces: **0/32**;
accepted Apple-derived `Swirl-VF.ttc`: **not generated**. The earlier complete
two-face synthetic TTC must never be counted as the original deliverable.

Primary references reviewed for this continuation: Microsoft OpenType
[normalization](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview),
[avar](https://learn.microsoft.com/en-us/typography/opentype/spec/avar),
HarfBuzz's `src/hb-ot-var-avar-table.hh`, and FreeType's `src/truetype/ttgxvar.c`.
These are comparison references, not proof of Apple's undocumented behavior;
no upstream implementation is copied into the new validator regression.
