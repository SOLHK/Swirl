# Swirl-VF: native-calibrated transform and curve-factor repair

This phase starts from `91dc31e7ed8b5718ed0d7b3db3bddeffc87155ef`, preserving
all concurrent Core commits. No UI, Rust, source-font bytes or axis tags change.

## Reproducible evidence before the fix

Native run 39304868120 on xcode-27 retained all 124 tangent and 28 hierarchy
checks and reran the identical 1088 source observations: 910 passed, 178 failed.
Its new 72 independently authored transform/factor tests exposed 54 failures.
Artifact 12213506251 archive SHA256:
`42a9da2a2806e9966b3b7d9ba0414ef62bd201574a07fff15591563cb4b23217`.
The artifact contains source code and original synthetic geometry, no Apple
font or Apple outlines. The user's uploaded original still matches SHA256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.

## Inferred and independently measured rules

A composite transform row is an ordered product
`master * extreme_0**weight_0 * extreme_1**weight_1 * ...`.
Extremum order is the stored column order, not arbitrary summation or a
single exponential of summed motion parameters. For `(R(theta), t)`, a power
`w` rotates by `w*theta` and translates by
`sin(w*theta/2)/sin(theta/2) * R((w-1)*theta/2) * t`.
The implementation uses sinc to preserve the zero-angle limit `w*t` without
cancellation. Master rotation acts on subsequent translation contributions.
Deeper local transforms still act on inherited descendant translations.

Native Type-0 experiments also require the parallel factor to stay on the
closed segment [0,1]. The encoded source factor and user axes are NOT changed;
only its evaluation follows the observed native rule. Both renderer paths and
the tangent resolver now use that rule. Type 3/4 support is unchanged.

Local post-fix comparison with all 72 archived native tests passed in scalar
and batch modes, with and without Type-2 enabled (maximum about 1.71e-13
FUnit). This is recorded-output recomparison, not a new macOS execution.
The previous 104 local unit tests pass; eight new analytic tests pass. Native
CI retains all 72 inputs and adds 48 independent random mixed-axis/rotation
fixtures, plus the same 124/28 regressions and exact-source 1088 gate. No
sample or tolerance is relaxed; a fresh source result is still required.

## Boundaries

These corrections do not establish avar user-coordinate equivalence, CoreText
metric fidelity, full 32-face reconstruction, all-GID/continuous-space fidelity,
Windows 11/Qt rendering, installation, or a finished Swirl-VF.ttc. Read the
actual post-fix CI verdict before claiming any reduction in the 178 failures.

Primary reference: Apple HVGL 3.1 table layout and transform order:
https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html
Native integration reference (not an independent HVF decoder):
https://lists.gnu.org/archive/html/freetype-commit/2025-11/msg00038.html
