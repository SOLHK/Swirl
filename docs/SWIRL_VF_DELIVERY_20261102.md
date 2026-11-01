# SwirlVF delivery checkpoint — 2026-11-02

**PARTIAL / production BLOCKED. No accepted SwirlVF.ttc has been generated or
published. This checkpoint is engineering progress, not the requested font
delivery.**

## Preserved source and recovered work

The isolated branch `work/swirlvf-delivery-20261102` starts at remote test
`63dde8812f85839aa6024cbba6c498c96cae022d`. The original checkout and main are
unchanged. [Recovery audit](SWIRL_VF_RECOVERY_20261102.md) records the ten
branches, dependencies, conflicts and already-merged PRs. P8/C1/D1 source and
all old strict failures are retained. Private historical model/cache files are
not in this checkout; the historical 228 experimental models are **not** newly
recovered accepted models.

The original remains 61,473,880 bytes, SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
A byte-identical private backup outside the repository was verified and made
read-only. All audit, native and reconstruction commands open the original for
reading. Conversion output and authorization evidence remain private.

## Implemented changes

- Product discovery, metadata messages, production builder, smoke/test entry
  points and current usage instructions use exactly `SwirlVF.ttc`. The builder
  rejects the old name, wrong case and other extensions. The experimental TTC
  packer reserves both the new and historical production names, preserving its
  separation from production admission. Original-source filenames and historical
  documents remain intact.
- Reuse the two code/test files from `e6b44f83cd92e4b8082d54a84d4a98bef1cd5b28`:
  axis-readback diagnosis saves `BLOCKED_SOURCE_IDENTITY` when native source
  loading fails, with no fallback or instance requests. This repairs diagnostic
  reporting, **not** CoreText's loading behavior.
- The existing private Windows wrapper now exposes `--all-glyphs`, forwards
  `-AllGlyphs`, and rejects native summaries or per-face counts that do not
  confirm the requested complete coverage. Sampled runs explicitly remain
  `SAMPLED_GIDS`. No result grants final-font equivalence.
- Existing font CI now runs on this branch, test pushes and test-targeted font
  PRs. The authored Apple job uses the supported `macos-26` public runner;
  separate historical exact-original workflows retain their environment.
  CoreText's strict metric test remains mandatory and may fail. Windows Server
  authored controls remain explicitly separate from Windows 11. Public artifacts
  in the P8 workflow remain limited to its fixed summary allowlist.
- Update the existing standalone Windows font workflow from Qt 6.10.3 to
  6.12.0, including all SDK/ABI assertions, and activate it on the delivery
  branch and test. Preserve its authored-fixture, native raster, full-app push
  build and public-runner guards. This fixes an inactive, incompatible CI entry
  point without claiming a Windows 11 or final-font result.

## Actual local checks

Environment: macOS 26.5.1 (25F80), arm64; SDK 26.5; Apple clang 21.0.0;
Swift 6.3.3; CMake 4.4.5. The default Python was 3.9.6 and unsuitable.
An isolated Python 3.12.16 environment was installed with the existing pins
fontTools 4.61.1, NumPy 2.2.6 and uharfbuzz 0.56.3.

| Check | Actual result and scope |
| --- | --- |
| `audit_font.py` | Exit 0; 32 faces, 47,102 GIDs each, 1,507,264 face/GID slots; all-GID cmap and metric audit, source unchanged |
| Original cmap | Five unique cmap blobs, Unicode union 35,741; face 0 best cmap 34,555; no out-of-range mappings on face 0 |
| Original format | HVGL present, no glyf/loca/gvar; fvar/avar/HVAR/STAT/GSUB/VORG present; GPOS/VVAR absent on face 0 |
| Original audit findings | 32 head-checksum findings and 32 raw avar nonconformance findings retained; not silently repaired or declared corrupt |
| `inspect_hvf.py` | Exit 0; shared HVGL structural validation PASS, 70,047 parts / 47,102 GIDs; not all native outline verification |
| Axes | Original tags/ranges retained: WDTH 1/500/1000, wght 100/501/900, HGHT 1/500/1000; candidate runtime axes NOT_RUN |
| Exact-original CoreText | BLOCKED: 0 URL descriptors, 0 data descriptors, CGFont unavailable, 0/32 native identities, no successful glyph requests |
| Production normalized-design comparator | 1088/1088 PASS on unchanged 32-GID/34-location finite sample, max 1.7053025658242404e-12 source FUnits; not whole-font or user-axis proof |
| Native HVF | 128 bounded calls over 32 faces and four design positions, 2,560 glyph observations; finite source extraction only |
| Native authored strict metric test | FAIL: unchanged vertical advance discrepancy 849 vs 850; no tolerance changed |
| Production `rebuild.py` | Actually executed with exact source, compiled CoreText oracle and output name SwirlVF.ttc; exit 2 at native metadata identity; 0 batches, 0 completed faces, output absent |
| Portable regression suite | 896 tests, 0 failures/errors, 7 explicit skips: five Linux-library-only native API checks and two separate native-integration gates |
| Audit regressions | 6/6 PASS |
| Changed workflow validation | actionlint 1.7.12 PASS on swirl-vf.yml and swirl-vf-p8-windows-local.yml; historical source-rebuild workflow still uses legacy xcode-27 runner |
| Qt/Swirl authored integration | Qt 6.12.0 installed; standalone native font targets configure/build PASS, CTest 2/2 PASS, QTest 61 PASS / 0 FAIL / 9 optional skips; offscreen software scope, final font NOT_RUN |
| Windows 11 x64 / installation / physical DPI | NOT_RUN; no accessible Windows 11 machine established |

The original-format counts and table absence describe the source, not an output
font. Full private reports contain cmap/UVS, layout, metrics and raw table
findings; none are public artifacts. The embedded OS/2 fsType value is 4 and is
not proof of a separate modification or public redistribution grant.

[Qt evidence](evidence/SWIRL_VF_QT_20261102.json) binds 19 authored fixture hashes,
Qt 6.12.0/C++23 build commands, exact source hashes and every skip reason. Both
`SwirlVF.ttc` physical-face loading and actual mixed three-axis outline changes
pass using authored fixtures; final-font and Qt Windows acceptance remain open.

[Native evidence](evidence/SWIRL_VF_NATIVE_20261102.json) binds exact source and
code hashes, compiler versions, commands, exit codes and bounded counts. Private
raw observations are not included. The installed system font has a different
SHA-256 and was not used as a substitute.

## Unresolved delivery gates

1. No authorization document was found in the supplied project or accessible
   document locations. Its private local path was requested, without requesting
   renewed oral authorization. Modification, conversion, cross-platform use
   and public distribution scope therefore remain **UNVERIFIED**. Swirl's own
   license and commercial register do not grant rights to this third-party font.
2. Exact-original CoreText loading fails on this host. Historical evidence of
   different behavior at a system-reserved location is not an explanation or
   permission to modify that location. A supported independent environment or
   a verified native loading correction is still needed.
3. P8's historical 228 encoded face-0 models cover 0.484% of that face's GIDs;
   no nonempty model passed all frozen 129-position strict outline checks.
   Independent historical errors reach 8.521084573934047 source FUnits. This is
   above the unchanged 1/32 bound. A fresh bounded experiment reproduced these
   failures with the unchanged holdouts. Even 728 training nodes left errors
   above 1/32. Exhaustive legal-UPEM default-grid checks for GIDs 1166 and 19177
   found minimum control-point errors 0.0351376252 and 0.0390468960: the current
   expanded simple-glyf representation cannot satisfy that point/topology
   contract even at default. This is not a universal OpenType impossibility;
   fractional composite transforms or changed exact topology remain unimplemented
   and unverified. [Bounded evidence](evidence/SWIRL_VF_INTERPOLATION_20261102.json)
   contains only scalar results, training specifications and hashes. The remaining
   46,874 models, other faces,
   original user mapping, native metrics/origin, continuous interpolation and
   retained layout semantics are not accepted. A large sweep of the currently
   failing approximation is not a valid route to acceptance.
4. Windows 11, real final-font Qt loading, complete native equivalence and CI
   acceptance are required before any binary publication or test merge.

## Delivery identity

Expected private output: `/Users/mac16/Projects/Swirl-VF/output/SwirlVF.ttc`.
Actual output: **ABSENT**. Size/SHA-256/face count: **N/A**. Accepted complete
faces/GIDs: **0/32, 0/1,507,264**. No binary has entered Git or Git LFS, and no
remote font SHA match can be claimed. LFS selection awaits an accepted binary's
measured size and repository policy.

Development source is preserved in [draft PR 49](https://github.com/SOLHK/Swirl/pull/49)
targeting test, with no merge
until the above gates pass. No main update, release, force push or branch
protection change is authorized or performed.

The first connected-GitHub source commit is
`2a0f436821afd39585598c23b950fd0ed362b2e9`; its tree
`528943971e7b046c3b8a0ac7574ff21b2692152f` exactly matches the locally tested
commit tree. Command-line HTTPS push lacked credentials; the connected GitHub
API uploaded all 31 blobs with exact local blob-SHA verification, created the
same tree, then created the branch and draft PR. Local commit
`726da837eb97ca45ef2d02a96eddc01253a46ed5` remains preserved. The connected
worktree continues on `work/swirlvf-delivery-connected-20261102`, tracking the
public `work/swirlvf-delivery-20261102` branch. No forced update was used.

## First actual connected-GitHub checks

At source commit `2a0f436821afd39585598c23b950fd0ed362b2e9`,
[font run 41336018845](https://github.com/SOLHK/Swirl/actions/runs/41336018845)
completed Python and DirectWrite jobs successfully. Its Apple job failed the
unchanged strict check: `face0-point0`, GID 2, actual vertical advance 849 vs
expected 850.0 at tolerance 0.03125. The actual job log was retrieved and
checked; the independent diagnostic/table-metric steps completed, and the
conditional strict reconstruction step was skipped after the strict failure.
[All-GID P8 run 41336018875](https://github.com/SOLHK/Swirl/actions/runs/41336018875)
completed successfully with authored inputs only. The additional Windows Qt
workflow and the subsequent exact-head checks remain pending until observed;
these first-commit results cannot stand in for later SHA results.
