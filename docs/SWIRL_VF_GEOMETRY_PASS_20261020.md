# Swirl-VF: original sampled geometry gate now passes

Executable source: `5cbf5715d99c1046e80c1c3e45a4ec2ab8946f1f`.
Branch: `work/core-completion-20261017` only. Concurrent Core evidence commit
`c1c9af2cbb1d6c8eaefb2c61c9968046db74f481` remains in ancestry.

Native run: https://github.com/SOLHK/Swirl/actions/runs/39306798698
Job 118245849659 completed SUCCESS on xcode-27 / macOS 27.0.1.
Artifact 12214625609 archive SHA-256:
`04c2f22f6ae77dd882638b0a1a2aa98c6b152f8f155b1a84b508f29c1817aa73`.
Downloaded artifact source snapshot exactly matches all locally tested files.

## Exact results

- The unchanged original-source 32 GID x 34 location sample: **1088 passed,
  0 failed**, versus 910 passed / 178 failed before this repair.
- Maximum original control-point error: **1.7053025658242404e-12 FUnit**.
- Tolerance is still **0.03125 FUnit (1/32)**. Same selector, random seed,
  original bytes, GIDs and comparator; no samples removed or tolerance relaxed.
- Source SHA-256 before/after:
  `39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
- Original transform regressions: **120/120** pass (all 72 previous + 48 unseen),
  checked with scalar/batch paths and Type-2 enabled/disabled. Maximum error
  7.389644451905042e-13 FUnit.
- Previous tangent regressions: **124/124** pass. Maximum error
  2.2737367544323206e-13 FUnit.
- Previous hierarchy regressions: **28/28** pass.
- Local Python suite: **112/112** pass; source-audit regressions **6/6** pass.

## What changed

`transform_geometry.py` implements ordered master/extremum rigid-transform
powers, including rotation-centre interpolation and correct nested transforms.
`hvf.py` and `batch_geometry.py` share that implementation. Type-0 parallel
factors follow the independently measured closed-segment evaluation rule.
Original raw factors and user axes remain unmodified.
See `SWIRL_VF_TRANSFORM_REPAIR_20261020.md` for the actual formula and tests.

## Important remaining boundary

This is a **sampled normalized-design-space geometry pass**, not a finished font,
not all 47,102 GIDs at all positions, and not all 32 face/user-axis mappings.
It does not establish avar interpretation, CoreText metric accuracy, final
standard glyf/gvar construction, Windows 11 installation, or Qt/Swirl acceptance.
The separate CoreText strict metric gate remains unresolved. No accepted
Apple-derived `Swirl-VF.ttc` has been generated or distributed.

Next: run the real-source reconstruction entry point, preserve its exact first
blocker, resolve user-coordinate/metric semantics without loosening the old
gates, and expand original-source coverage before final TTC acceptance.
No Apple font, private outlines or credentials are included in this commit.
