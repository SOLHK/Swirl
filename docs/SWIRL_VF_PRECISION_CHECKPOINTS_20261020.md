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
control comparison passes. Native execution of this added comparison remains
pending; prior parametric evidence is not substituted for that execution.

Concurrent Core evidence/test commit
`f19b0ad51058580a8a0ed73008b22754e6f45ea0` was inspected and preserved by
fast-forward; none of its four files overlaps this font change.

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
