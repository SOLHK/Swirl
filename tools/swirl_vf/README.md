# Swirl-VF font engineering tools — 2026-10-20

Independent code, original geometric fixtures, native probes and reconstruction
tools. This directory contains no Apple font, converted Apple font or extracted
Apple outlines. A locally supplied font requires appropriate use/modification
rights; availability of this code does not grant rights to redistribute fonts.

## Current status — 2026-11-02

Formal output is exactly **SwirlVF.ttc**. No accepted final font exists.
The [interruption recovery and CFF2 coefficient report](../../docs/SWIRL_VF_RESTART_20261102.md)
records the recovered piecewise source slices, exact serialization verification,
native nested-blend admission guard, actual Windows CI and remaining delivery
gates. Draft PR 51 preserves and merges the concurrently recovered PR 49 source;
neither slice success nor authored fixture success is full-font acceptance.
The [delivery checkpoint](../../docs/SWIRL_VF_DELIVERY_20261102.md) and
[branch recovery](../../docs/SWIRL_VF_RECOVERY_20261102.md) preserve P8's 228
experimental models and the already-merged C1/D1 tools; these are not complete
variable-face coverage. The [root-cause continuation](../../docs/SWIRL_VF_ROOT_CAUSE_20261102.md)
verifies all 32 exact-source CoreText identities in an independent macOS 27
resident-source environment. Local external-file loading still returns 103;
byte-identical copy controls isolate a location-dependent HVGL loading boundary.
The production HVF comparator passes 1088/1088 finite cases, while the strict
native vertical metric test still fails. Bounded new interpolation/default-grid
measurements explain why the existing expanded-simple representation cannot
meet the unchanged point-precision contract for selected real glyphs. Authored
Qt 6.12 integration passes on macOS; final-font and Windows 11 acceptance remain
NOT_RUN. See the linked exact-scope evidence and draft PR 49 before continuing.

## Historical source mapping checkpoint — 2026-10-20

The exact-source normalized-design geometry gate now passes: **1088/1088**, zero
failures, at the unchanged **1/32 FUnit** threshold. Native run 39306798698 used
source commit `5cbf5715d99c1046e80c1c3e45a4ec2ab8946f1f` on xcode-27. The previous
178 failures were repaired by ordered rigid-transform powers, rotation-centre
interpolation and native Type-0 factor evaluation. Scalar and batch evaluators
share that implementation. All 124 tangent, 28 hierarchy and 120 new transform
experiments also passed. Type-2 remains explicitly enabled; Types 3/4 fail.

This is a fixed sample, **not** all-GID, all-face user-coordinate, continuous-space
or Windows acceptance. CoreText actually verified all 32 physical source faces,
but the original `rebuild.py` run is still blocked before its first completed
glyph model or face. The latest rebuild at `af8df45a` accepted all 91 initial
batches / 5,824 glyph observations with exact replay, then stopped at face 0 /
GID 0 because the observed vertical X origin cannot be represented by vmtx alone.
Training sample 1 at `WDTH=1, wght=501, HGHT=500` has a 100-FUnit absolute
representation error, retained against the unchanged 1e-5 condition.
Zero original glyph models/faces are complete. No accepted `SwirlVF.ttc` exists.

The new HVAR diagnosis measured 3048 user locations / 12192 advances across 32
faces. Raw-order avar evaluation with zero-normalized coordinates preserved
matches these metric observations within the original 1/32 FUnit budget; its
rounding semantics and user-coordinate outline equivalence remain unaccepted.
The separate CoreText strict metric test still fails. Windows DirectWrite passes
only the original synthetic fixtures, not an Apple-derived candidate.

Continuation at `c31edaf04f3a6369e90da026b94aa6cf8176f356` measured 2,692
user-coordinate positions across all 32 faces, with 32 selected GIDs per point.
None of the four global avar/quantization models passes all 86,144 comparisons.
The independent 6,912-observation vertical-origin diagnosis also rejects
current-width/2 as a universal interpretation of Apple's API values. See the
[current continuation](../../docs/SWIRL_VF_USER_COORDINATE_PROGRESS_20261020.md).

The new `tools/verified_axis_oracle.py` accepts explicitly unverified native
observations only after checking original source/table identity and replaying
every requested GID at coordinates computed before any native observation.
With `T(x)=trunc(binary64(x*10000))/10000`, v2 admits only exact original/T/T(T)
first echoes and requires the actual independent replay at fixed `T(T(x))` to
echo that coordinate exactly. Exact finite equality is
required for typed path commands, bounds and all raw metrics; no tolerance is
increased and no coordinate/path/metric is replaced. The unchanged strict
extractor remains the default. Native boundary run `39368769062` completed
12,800 original selected-GID records and 600 original synthetic records with
zero path/raw-metric differences across all predeclared candidates and both
process orders. All 120 fixed second-step instances echoed exactly. This
supports the fixed v2 policy but does not replace its every-batch native checks
or every later original batch. Run `39370313776` now passed those first 91
batches before the separate origin gate. Failure reports retain safe
axis values, binary64 hex, original/replay phase and completed-observation
counts. The separate boundary probe compares every predeclared numeric
candidate and cannot grant production acceptance. Neither this adapter nor a
successful diagnostic proves complete-font or continuous-space equivalence.

Run `39370313682` did complete an original synthetic two-face, three-GID-per-face
TTC through real CoreText paths, v2 verification, explicit source-table metrics,
rebuilding, serialization and native reread. All three axes and exact metric
models were retained. The 3,424-byte original synthetic TTC was removed after
measurement. The old raw API 849/850 failure remains separately visible; this
does not grant original Apple-font or Windows acceptance. Independent variable
GPOS/actual TextLayout experiments address the confirmed fixed-origin blocker.
Run `39371704981` actually completed 4,608 Windows Server layouts / 11,520 glyph
observations: default `vert` and `vkrn` reduced the original synthetic maximum
drift from 98 to 0.5 FUnit, retaining default horizontal/mixed Latin runs and
mapping/metrics. HarfBuzz defaults differ (`vert` only); neither result proves
universal feature behavior or a 1/32 final-layout bound. The macOS job failed
before any layout because its SDK disallows `.excludeSynthetic`; the supported
table-option repair retains all identity checks and awaits native rerun.
No production origin is bypassed on the strength of a diagnostic result.

Read the current [detailed handoff](../../docs/SWIRL_VF_USER_AXIS_HANDOFF_20261020.md),
[geometry evidence](../../docs/SWIRL_VF_GEOMETRY_PASS_20261020.md), and
[algorithm repair](../../docs/SWIRL_VF_TRANSFORM_REPAIR_20261020.md) before continuing.

## Local tests and read-only audit

Use an isolated environment with Python 3.12+, `fonttools==4.61.1` and
`numpy==2.2.6` (CI pins these versions). From this directory:

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s audit -p 'test_*.py' -v
python tools/audit_font.py /private/PingFangUI.ttc --output /private/audit
python tools/inspect_hvf.py /private/PingFangUI.ttc --output /private/hvf-preflight.json
```

Parsing/finite-coordinate success is not native outline equality. Original raw
avar record order and duplicates must not be collapsed through a dictionary.

## Native source and reconstruction

The [Apple HVF probe](platform/HVF_ORACLE_README.md) uses the actual system
libhvf with normalized design coordinates. The [CoreText extractor](platform/CORETEXT_ORACLE.md)
requests original user coordinates, verifies physical face/table identity and
retains real outlines, origins and advances. Current exact-source runners use
`xcode-27` and require SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
Do not substitute a different installed PingFang release.

After resolving the source-oracle gates, run privately:

```sh
python tools/build_swirlvf.py /private/PingFangUI.ttc \
  --expected-source-sha256 39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890 \
  --oracle /private/build/coretext_extract \
  --output /private/output/SwirlVF.ttc \
  --report /private/output/reconstruction.json \
  --checkpoint-dir /private/build/verified-faces
```

The current builder is **native-instance approximation**, not lossless format
translation. It retains original GIDs, face coverage, axis tags/ranges, and uses
standard glyf/gvar with explicit metric phantoms and equivalent HVAR/VVAR.
The product entry point fixes both total outline and metric budgets at
**1/32 FUnit**. Cubic approximation consumes at most 1/64 of that same outline
budget; point/encoding error is added before checking the total. Source identity
is mandatory. Historical `rebuild.py` experiment defaults remain 1 FUnit with
a 0.05-unit cubic allowance, and must not be used for product acceptance.
Both entry points call the same reconstruction and serialization implementation.

The builder does not overwrite input or previous output. Missing data, topology
changes, unrepresentable metrics or remaining holdout error block publication.
Every serialized face's contours, phantoms and full variation coefficients and
all TTC-packed table bytes are checked. Even a sampled build pass still needs
independent source, Windows and application acceptance; `lossless_conversion`
stays false. No alternative-font fill, faux bold, dropped height axis or glyph
cropping is permitted.

Before publishing a candidate, the builder also requires the oracle's complete
final transcript: exact source identity, accepted request/GID counts, no native
errors, no trailing records, and exit code zero. Private face checkpoints must
have their own accepted native transcript before they can be restored.

## Windows and Swirl acceptance

See [DirectWrite](platform/DIRECTWRITE_README.md) for the C++/PowerShell probe.
It loads an explicitly supplied file, checks physical TTC faces and all three
axes, samples actual outlines/advances, and captures five software DPI scales.
It does not install a font or prove Apple equivalence, shaping, ClearType quality
or real Swirl UI performance. Windows Server synthetic CI and Windows 11 desktop
acceptance must remain separately identified.

Original source/candidate data, private glyph comparisons and Apple-font images
stay in an authorized private workspace, not this public repository or public
Actions artifacts. Swirl's existing 128 MiB font-file limit remains; if a complete
candidate exceeds it, evaluate size/memory and the application limit rather than
dropping glyphs or faces. Regions, cmap/UVS/GSUB, original horizontal/vertical
metrics, real shaping, five DPI levels and startup/layout/scroll performance all
remain part of final acceptance.

Primary references and licensing boundaries are recorded in
[technical comparison](research/TECHNICAL_COMPARISON.md) and
[licensing review](research/LICENSING_REVIEW.md). Those dated documents retain
historical observations; current tested state is in the detailed handoff above.

## Joint interpolation scaling checkpoint — 2026-11-03

The separate CFF2/avar2 joint compiler is a research representation, not the
completed full-font product builder described above. Its
[14-case corpus](../../docs/SWIRL_VF_CORPUS_20261103.md) has nine qualified
joint-q passes and five retained failures. Six additional unique GIDs pass
serialized CoreText/HarfBuzz/fontTools tests at 1/32 FUnit.

[Sparse streaming and exact instruction sharing](../../docs/SWIRL_VF_SCALING_20261103.md)
reduce compiler RSS and font size. The optional
[`--maximum-helpers 1239` dictionary](../../docs/SWIRL_VF_EXTENDED_DICTIONARY_20261103.md)
reduces the two anchor probes to 28,532,496 / 80,682,776 bytes with complete
native revalidation; the default bank remains 215. It adds an explicit drawing
cost, recorded with the storage benefit. The corpus tools retain failure costs,
source hashes, independent-sample counts and stage timings.

[Capacity and compatibility limits](../../docs/SWIRL_VF_SCALING_COMPATIBILITY_20261103.md)
include original physical-axis mapping, per-cell GID growth, shaping dependence
and actual failing DirectWrite controls. The Windows fractional glyf alternative
passes authored server controls but fails CoreText. These results do not
certify full-font or Windows 11 acceptance. PR #53 remains Draft.
