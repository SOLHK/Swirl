# SwirlVF restart, exact CFF2 verification and remaining delivery gates

**PARTIAL. No accepted SwirlVF.ttc exists. Do not install a diagnostic slice as
the complete font or treat this checkpoint as Windows font delivery.**

The recovery branch is `work/swirlvf-recovery-20261102`, with
[draft PR 51 targeting test](https://github.com/SOLHK/Swirl/pull/51). The primary
checkout at `Swirl/` was clean main. Interrupted work was found in the separate
`worktrees/swirlvf-delivery` checkout at ca8e6f2c. Twelve reviewed source files
were saved in independent local commit 62055319 and remote commit
`e8f765de592a10b3a1cdde614ce2fdd897e11e53`; their trees are byte-identical.
An active concurrent session then published 91c2b760. Ordinary merge
`d987eb624454c62da822b9f331ca2f75d3428708` preserves that history and the recovery
work. No reset, cleanup, force push or change to main/test was performed.

## Concrete repairs

1. The recovered symbolic HVF partition finds internal axis zero crossings,
   curve clamp boundaries and both roots of tangent projection equations.
   F2DOT14 neighbours bracket off-grid boundaries; subsequent refinement uses
   independent quarter/midpoint probes. This repairs the six measured line
   slices, not the unimplemented full three-axis source model.
2. `cff2_certificate.py` independently decodes actual saved ordinary CFF2
   CharStrings, including subroutine calls and their variation state. It compares
   every 16.16 coefficient and every F2DOT14 region identity with the supplied
   model. Equality proves ideal serialization identity for all simultaneous
   design coordinates, not just sampled corners. It does not prove that the
   supplied model equals the source. Metrics, native arithmetic, avar/user-axis
   mapping and layout remain separate. The fixture generator now requires this
   certificate for ordinary, compact and long CFF2 controls before exposing them.
   A fresh cache reads the saved SFNT tables; repairing a corrupt region only in
   memory cannot hide the on-disk mismatch. The caller's file remains open.
3. CFF2 holdout admission now treats omitted axes, explicit zero and negative
   zero as the same design point. A training point can no longer masquerade as
   an independent holdout because its dictionary uses different keys. Duplicate
   canonical training locations are also rejected.
4. Default CFF2 installation rejects factored/nested models known to lose outlines
   in the measured DirectWrite implementations. `experimental_nested=True`
   remains explicit in authored diagnostic generators; their failed native
   checks are retained. This is not a claim that nested blends violate the
   current specification: OpenType 1.9.1 permits repeated blending, whereas the
   earlier 1.9 CharString document prohibited nesting. Both the current
   [CFF2 specification](https://learn.microsoft.com/en-us/typography/opentype/spec/cff2#advanced-uses-of-blend)
   and actual native evidence must be considered. No threshold was increased.
5. The Windows Qt workflow now admits this specific recovery branch, preserving
   its public-runner, same-repository and dependency identity restrictions.

The nested-blend admission change is remote commit
`39d1186a51c3b4c4c76a0bff2197394fe4f1e3f4`. Later saved-SFNT reader hardening
and its final tests are bound by the current file hashes in the evidence.

## Actual source slices

The source remains read-only, 61,473,880 bytes, SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
A fresh run used 512 holdouts per slice, with fixed coordinates of the other two
axes from the retained private manifest. The limit remains 0.03125 source FUnit.

| GID | Source axis | Knots | Nine-node baseline maximum | Repaired holdout maximum |
| --- | --- | ---: | ---: | ---: |
| 1166 | WDTH | 49 | 0.606376 | 0.004985 |
| 1166 | wght | 80 | 5.639472 | 0.007066 |
| 1166 | HGHT | 27 | 2.397287 | 0.007705 |
| 19177 | WDTH | 11 | 0.245033 | 0.005775 |
| 19177 | wght | 181 | 2.790352 | 0.007143 |
| 19177 | HGHT | 28 | 1.142785 | 0.004194 |

All six saved slice TTCs also pass exact coefficient identity. They are small
experimental collections containing the selected source slice and authored
control glyphs. They are not full original GID/face coverage. The actual source
axis tag is uppercase `WDTH`, with its original custom scale; a registered
lowercase `wdth` percentage mapping has not been delivered or silently assumed.

Three-axis source reconstruction remains unaccepted. Previous independent
three-dimensional holds still fail; neither six slices nor exact serialization
of a supplied model resolves that. Default assembly continues to reject slice
models as complete design spaces. Original GIDs and Unicode mappings are not
deleted to manufacture a pass.

## Executed verification

Local environment: macOS 26.5.1 (25F80), ARM64; Python 3.12.16,
fontTools 4.61.1, NumPy 2.2.6. All private reports are under the separate
`private/recovery-20261102` directory, not public artifacts.

| Check | Result and limits |
| --- | --- |
| Full Python suite on final algorithm changes | 962 total: 955 passed, 0 failures/errors, 7 explicit skips |
| Audit suite | 6 passed, 0 failed |
| CFF2 focused suite | 27 passed; included in the full suite, not an additional total |
| Exact serialized coefficient regressions | 8 passed, including a three-axis hidden-region corruption missed by all 27 grid vertices; subroutine boundary and altered-support tests |
| Source line refit | 6 slices / 3,072 holdouts pass; no full-source three-axis acceptance |
| Saved source-slice coefficient identity | 6/6 pass; source fit and raw metrics are not granted by these certificates |
| Local native CoreText controls | 696 glyph observations, 0 geometry failures, max control error 0.001815559 FUnit |
| Same native experiment's raw metrics | FAIL: 224 CoreText and 48 HarfBuzz failed comparisons, 272 total; retained verbatim |
| Authored Windows input identity after the admission repair | All 19 generated controls byte-identical to actually measured CI inputs, including failing nested controls |
| Workflow validation | actionlint passes the changed font workflows |
| Strict production builder | Exit 2 at native metadata: exact external source physical faces cannot all be verified on this host; 0 native batches, no output |

Commands (run from the recovery worktree):

```sh
PY=/Users/mac16/Projects/Swirl-VF/private/venv/bin/python
"$PY" -m unittest discover -s tools/swirl_vf/tests -v
"$PY" -m unittest discover -s tools/swirl_vf/audit -p 'test_*.py' -v
"$PY" -m unittest discover -s tools/swirl_vf/tests -p 'test_cff2*.py' -v
actionlint .github/workflows/font-system-windows.yml .github/workflows/swirl-vf.yml
"$PY" tools/swirl_vf/platform/test_coretext_cff2.py --output NEW_PRIVATE_DIRECTORY
"$PY" tools/swirl_vf/platform/probe_piecewise_source.py \
  --source /Users/mac16/Projects/Swirl-VF/PingFangUI.ttc \
  --manifest /Users/mac16/Projects/Swirl-VF/private/dual-core-20261102/manifest.json \
  --private-output NEW_PRIVATE_DIRECTORY
"$PY" tools/swirl_vf/tools/build_swirlvf.py \
  /Users/mac16/Projects/Swirl-VF/PingFangUI.ttc \
  --expected-source-sha256 39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890 \
  --oracle /Users/mac16/Projects/Swirl-VF/private/recovery-20261102/native-cff2/coretext_extract \
  --output /Users/mac16/Projects/Swirl-VF/output/SwirlVF.ttc \
  --report NEW_PRIVATE_REPORT.json
```

Fresh output paths are required; prior reports and fonts must not be overwritten.
The strict native CFF2 command currently returns failure, as the table records.

## Native Windows evidence and integration

[Checkpoint native run 41456608240](https://github.com/SOLHK/Swirl/actions/runs/41456608240)
used head e8f765de and actual PR merge checkout
`18cca440d0e04233f4f2c4550d9aa2cf1ddcb6a7`. All three Windows jobs compiled and
executed DirectWrite: Server 2022, Server 2025 and Windows 11 ARM64. Ordinary,
compact and structural controls pass independent authored geometry; nested
controls fail, keeping all three jobs red. The Apple job retains its 849/850
failure and its separate CFF2 raw-metric failures; Python succeeds.

The downloaded Windows 11 artifact was hash-verified and inspected. Its 13
ordinary variants cover 4,650 observations, with zero geometry failures and
maximum error 0.007074260 FUnit. Each of the six nested variants has 124 failed
geometry observations. Compiler machine 0x8664 and native machine 0xAA64 prove
x64 emulation on ARM64. This is genuine Windows DirectWrite CI, not a Mac
simulation, and is not Windows 11 x64 hardware, installation or final-font proof.

[Windows Qt run 41459374057](https://github.com/SOLHK/Swirl/actions/runs/41459374057)
at aa3e37fb (merge checkout df783ca8fdd159130800a64c5f2e2194b75528e1)
passes all 3 registered CTests. The PR event skips the optional
complete-application build/smoke stages. The native matrix run
[41459374538](https://github.com/SOLHK/Swirl/actions/runs/41459374538) at that head
also executes the recovered origin-compensation experiments and exact CFF2
coefficient certificates. Its final result is FAILURE: Python passes, the Apple
job retains both strict failures, and each of the three Windows jobs retains
the nested-blend failure. All diagnostics still execute. These previous-head
results are not labelled as later-head check completion.

## Why there is no final font or test merge

- Full source three-axis fitting and complete 32-face / 1,507,264 face-GID model
  coverage are not accepted. This backend is still distinct from the historical
  TrueType production builder; it is not a completed CFF2 production pipeline.
- The local CoreText source-loading boundary blocks the exact-source native
  reconstruction session. The earlier successful resident-source macOS 27
  environment is separate evidence, not an available local replacement.
- Fractional raw advances and independent vertical X origins remain unresolved
  across engines. DirectWrite defines vertical X as half the current advance
  from the horizontal origin; GPOS placement can change ink location without
  making the raw APIs identical. Existing layout controls do not waive that
  retained gate. See the
  [DirectWrite metric definition](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_metrics).
- `wdth` percentage semantics, full target table/name/cmap/layout preservation,
  final-font platform rendering and Windows 11 x64 installation remain unverified.
- Applicable strict native checks are red. PR 51 remains draft targeting test;
  source is safely preserved remotely, but test has not been merged.

Expected output: `/Users/mac16/Projects/Swirl-VF/output/SwirlVF.ttc`.
Actual output: **absent**. Final-font SHA-256: **N/A**. No diagnostic file was
renamed to satisfy that filename. See
[aggregate, hash-bound evidence](evidence/SWIRL_VF_RESTART_20261102.json).
