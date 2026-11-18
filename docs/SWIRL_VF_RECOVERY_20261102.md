# SwirlVF recovery audit — 2026-11-02

This is a source-history recovery record, not font acceptance. The current
delivery filename is **SwirlVF.ttc**. Historical names in linked evidence remain
historical. No proprietary font, outline, model checkpoint, authorization
document or private log is included here.

## Audited baseline

After `git fetch --all --prune`, remote `test` was
`63dde8812f85839aa6024cbba6c498c96cae022d`. The isolated delivery worktree starts
from this SHA on `work/swirlvf-delivery-20261102`; the original checkout is
unchanged. This record describes that baseline even if the delivery branch
subsequently advances.

Git ancestry, commit lists, changed paths and non-checkout `git merge-tree
--write-tree` were inspected for every branch below. The merge checks are
textual compatibility checks only; no branch was merged by this audit.

| Remote branch under `origin/work/` | Exact head | Commits absent from test | Merge into baseline |
| --- | --- | ---: | --- |
| `vf-axis-a3` | `66594e9d32a33c1d216319e2dccd2f35c7e47a4a` | 8 | No textual conflicts |
| `vf-b1-public-containment-20261020` | `ba8039a1028808140453adcbe150438e2bb20385` | 7 | No textual conflicts |
| `vf-metrics-b1` | `7902cdb7b449a56939346263df54a692c22d8337` | 8 | No textual conflicts |
| `vf-rebuild-c1` | `c0fe6c47f1a4a0854fcbbde7c9f08b791b44123e` | 7 | Two add/add test conflicts |
| `vf-macos-native` | `e6b44f83cd92e4b8082d54a84d4a98bef1cd5b28` | 1 | No textual conflicts |
| `vf-macos-windows-d1-20261021` | `54e579f1b46ee75187069d40b9ec626b3cc980d5` | 0 | Already an ancestor |
| `vf-windows-d1` | `844544f92c8f2c0cc96dfb7af02e4fa8e6604b4f` | 10 | No textual conflicts |
| `vf-p8-gvar-pro` | `7ff8d17cb18c624b50895cda00216a2f3a86f844` | 4 | No textual conflicts |
| `vf-smart-width-w1` | `2be6c78cae93544af57e90cb4904a399959d6b7c` | 10 | Six QML content conflicts |
| `vf-takeover-abc-20261021` | `0d47f057b91912e3be4048cbd7a5548e505763da` | 0 | Already an ancestor |

No later font-converter commits were found across the fetched refs after the
P8 head's 2026-10-21 20:28:59 +08:00 timestamp. This statement concerns the
converter/tool paths, not subsequent unrelated product development.

## Existing PR integration and preserved results

Live GitHub PR metadata was read on 2026-11-02:

- [PR 23](https://github.com/SOLHK/Swirl/pull/23) is closed and merged, head
  `54e579f1b46ee75187069d40b9ec626b3cc980d5`.
- [PR 24](https://github.com/SOLHK/Swirl/pull/24) is closed and merged, head
  `0d47f057b91912e3be4048cbd7a5548e505763da`, recorded merge commit
  `95a6db7fcf6adf43fe39eeadfe68960498607efa`.
- [PR 27](https://github.com/SOLHK/Swirl/pull/27) integrated the lineages into
  `test`, merge commit `e19dc9f663ac326b6654953db212b97177a56966`.

The P8 converter, nominal support serialization repair, C1 verified-byte packer,
HVF geometry implementation, strict metrics and original failed comparisons
are already present in the audited baseline. Reapplying PR 23/24 would duplicate
history. The latest recorded tested P8 source is
`b0d26bf68c91d1f6cb7d692954c0950c37d0e09f` as identified by the existing P8
evidence; consult that evidence for exact source identity rather than treating
the later documentation head as newly tested code.

The [P8 handoff](SWIRL_VF_P8_BATCH_CONVERSION_20261021.md) records 228 encoded
real glyph models on face 0, of 47,102 GID slots: 223 have nonzero outline
variation, all 228 have metric/gvar variation, and 46,874 remain DEFAULT_ONLY.
That is partial experimental coverage, not a completed variable face. At all
125 training plus four holdout positions, only five empty-outline models pass
the strict outline bound; no nonempty model passes. All production acceptance
flags remain false. Prior Windows Server controls do not constitute Windows 11
acceptance. The old checkpoint files are not contained in Git; this audit
recovers source/evidence, not those private binary checkpoints.

## Narrow reuse recommendations

1. **CoreText source refusal reporting:** cherry-pick
   `e6b44f83cd92e4b8082d54a84d4a98bef1cd5b28` if continuing the axis-readback
   diagnostic. Its only code change is to `diagnose_axis_readback.py`, with five
   authored regressions and supporting public aggregate evidence/documentation.
   The generated Swift detects missing physical faces before requesting any
   instances, reports URL/data descriptor availability and CGFont construction,
   and emits `BLOCKED_SOURCE_IDENTITY` with zero axis observations. Python saves
   the blocked result bound to both extractor and generated-harness SHA and exits
   2. Successful-source diagnostics retain the unchanged 1e-6 axis condition.
   Production extraction/admission is untouched. The baseline's
   `macos_source_baseline.py` and `d2_axis_readback.py` already handle analogous
   refusal, so this repairs a remaining diagnostic path rather than enabling
   CoreText to load the font.

2. **A3:** the unique commits add arithmetic evidence, a prereadback cohort and
   authored HarfBuzz/FreeType normalized-coordinate transport. Their frozen
   ONCE_ALL hypothesis is already reused by baseline `target_axis_mapping.py`
   and `font_axis_mapping.py`, with acceptance flags false. These later P4/P8
   components do not supersede every independent A3 experiment, but no omitted
   A3 commit supplies a validated production mapping fix. Recover the diagnostic
   branch only when a corresponding experiment is needed; preserve
   `7cd579d6`'s archive-namespace repair with its dependencies. A broad merge is
   unnecessary for current candidate construction.

3. **B1:** both branches retain independent UPEM/unit/VORG experiments and
   unresolved native-origin failures. `vf-metrics-b1` adds the startup experiment
   `ac8e750bbcd174b5d1ba38214c646e5c55203ded`; the containment sibling adds
   `ba8039a1028808140453adcbe150438e2bb20385` to restrict public reports to
   aggregates. Baseline `d2_metric_upem.py` already extends the B1 frozen
   hypothesis across eight UPEMs, but does not reproduce the four-condition
   startup experiment. These are diagnostic assets, not a metric repair. Before
   broad integration, reconcile the siblings' public-output policy and inspect
   archived evidence; do not import raw diagnostic archives merely to recover
   their source.

4. **C1:** baseline versions of `ttc_staging_binary.py`,
   `ttc_staging_contract.py` and `ttc_staging_pack.py` are byte-identical to the
   branch. Production GDEF admission and confirmed-checkpoint recovery defects
   described by C1 were subsequently repaired in the already integrated D3
   lineage. Additional standalone staging store/engine/validator tools remain
   unique; they may help bounded recovery but do not prove bounded memory for
   full-face FontTools assembly. Resolve add/add differences in
   `test_ttc_staging_binary.py` and `test_ttc_staging_pack.py` by retaining both
   contracts if that infrastructure is integrated. Do not replace the current
   production entry point with its older fixture adapter.

5. **P8-G1:** `74d322b5`, `a713a0c1`, `c54b211a`, `7ff8d17c` form an isolated
   point-identity utility/test/documentation stack. It supports exact contour
   permutation, cyclic starts and reversed winding, rejects ambiguity, and
   excludes phantoms. Its ten tests were historically NOT_RUN. It does not
   align genuinely different shapes or fix gvar interpolation, so there is no
   demonstrated converter correction to cherry-pick on that premise.

6. **Windows D1 and W1:** D1's unique tools diagnose Qt 6.10.3 native/FreeType
   state with pinned runtime identities and a disposable patched-Qt experiment.
   They are distinct from the existing DirectWrite TTC tool and not a validated
   production Qt 6.12 patch. W1 touches product font fitting and old shared QML;
   its conflicts are `SwirlWindowTitleBar.qml`, `SwirlComboBox.qml`,
   `SwirlDialog.qml`, `SwirlFontBinding.qml`, `SwirlText.qml`, `GatewayPage.qml`.
   Preserve the current APEC V3 product tree and port only a separately
   reproduced, relevant defect rather than merging old UI files wholesale.

## Recovered source-load limitation

The B1 startup handoff records 268 CoreText descriptors and 32/32 bound physical
faces for the system-path exact source, but nil descriptors and zero bound
faces for a byte-identical private copy and for the same-path no-VORG variant.
The system source A/A replay remained byte-identical. This prevents attributing
the private-copy refusal to VORG removal or damaged font bytes. Path, metadata,
OS/SDK and system loading conditions were not isolated into a proven mechanism.
Do not substitute a different installed font or change source tables to claim
that the user's original was accepted.

## Acceptance boundary

This recovery audit generates no font and certifies no license, glyph, axis,
macOS/Windows/Qt equivalence or release. Current-source tests and native probes
must be run and recorded independently. Publication of SwirlVF.ttc remains
conditional on verified font rights, complete reconstruction and all requested
acceptance gates.
