# Swirl-VF: isolate shape and hierarchy disagreements

## Verified starting state

Branch: `work/core-completion-20261017`. This stage started from
`41555465b72fd59d42bc473f0d097c93e210c240`, preserving the newer Core changes.
The uploaded source is still 61,473,880 bytes, SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.

The previous statement that no native machine could access the identical source
is now obsolete. Run 39279585672, at `e228268dc779ed23cf674deb6fbfa249a6c8e60d`,
measured the same hash from the macOS 27.0.1 runner's resident font. Its archived
geometry report (artifact 12198841978) was downloaded and its archive SHA-256
verified as `743a0a1af8cbf15300a8c13411c8e5aa1212e74a13614d4fe10f94367c3d716d`.
No original outlines were published or transferred in that summary artifact.

That run completed a DIAGNOSIS, not a successful font conversion. Results:
32 selected GIDs x 34 design locations = 1,088 observations; 660 passed and 428
failed the unchanged 1/32 FUnit budget. There were 384 coordinate-budget failures
and 44 segment-type mismatches. Maximum reported point error was
223.93679441137425 FUnits. This is a sample, not a whole-font failure rate.
The explicit-Type-2 interpretation therefore cannot be promoted to production.

## New implementation and tests

`platform/probe_tangent_rules.py` creates 22 original geometric experiments:
incoming/outgoing controls, the tangent point, the next corner, both tangent
orientations, and paired tangent/corner controls. It logs full geometry only
because every coordinate is self-authored; it has no original-font input.
Its result remains DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE.

`platform/probe_hierarchy_rules.py` adds 28 original experiments with unequal
parallel factors, quarter-turn and non-right-angle rotation, fractional root
coordinates, internal extrapolation, nested rotation and descendant-row
translations. It compares exact quadratic controls, permits cyclic contour
starts, and retains the 1/32 FUnit limit. `--require-pass` fails the process on
any mismatch. Native and portable coordinates may be logged for these original
fixtures, never for Apple source outlines.

`tests/test_hierarchy_probe.py` verifies both encoders, independent single/nested
transform formulas, raw round-trip data, cyclic correspondence, deliberate
control-point damage and malformed-event rejection. Eight local tests passed.
The unchanged HVF parser/experimental renderer suite also passed its 15 tests.
These 23 local tests do not establish Apple or Windows acceptance. The local
runtime was Python 3.13.5, fontTools 4.63.0, NumPy 2.3.5; native CI retains its
pinned Python 3.12/fontTools 4.61.1/NumPy 2.2.6 dependencies.

The first new nested-transform test had an incorrect expected placement of a
descendant translation. It rotated that translation before the leaf transform,
whereas the current portable model adds it in the leaf parent's coordinate
system after rotation. The expected formula was corrected and the initial
failure retained in the delivery evidence. This is not a production bug fix,
a verified Apple behavior, or a relaxation of the native error budget.

## Why separate these tests

Not every failed original glyph contains Type 2. Failed GIDs 6 and 7 reference
an ordinary Type-0/1 shape through quarter-turn transforms; GID 104 also uses
Type-0/1 geometry with rotation and deeper transforms. This does not prove that
rotation is the cause. It means Type 2 alone cannot be assumed to explain all
failures. Independent synthetic hierarchy tests can discriminate that issue
without misusing another Apple face or changing original outlines.

The Apple-authored FreeType HVF integration was also checked against the callback
adapter. No speculative callback or production renderer modification was made
without a reproducer. Reference:
https://lists.gnu.org/archive/html/freetype-commit/2025-11/msg00038.html
Format reference:
https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html

## Native execution and handoff

The first new commit was `5cb42619785c66317552867d251784df2b0323b9`.
Its native run 39285093026 was still queued at the last check during this stage;
no native success is inferred. The extended workflow reruns both the local
regressions and the two native experiments, and uploads only original synthetic
JSON. The final delivery status records the exact later commit and run state.

Read the actual native results before modifying production HVF semantics. If
native hierarchy passes, investigate the original Type-2 and contour comparison
failures independently. If hierarchy fails, use the published synthetic inputs
and native events to isolate the transformation or interpolation convention.
Rerun the exact-source private geometry comparison after any genuine correction.
Do not interpret a diagnostic process exit of zero as geometry acceptance.

No accepted Apple-derived Swirl-VF.ttc has been generated in this stage. No
Windows installation or real Swirl font rendering is claimed. Original source
bytes remain unchanged; neither fonts nor private Apple outline dumps are
included in the public commit or delivery archive. UI and Rust Core are untouched.
