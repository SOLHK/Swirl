# Swirl-VF font engineering tools — 2026-10-20

Independent code, original geometric fixtures, native probes and reconstruction
tools. This directory contains no Apple font, converted Apple font or extracted
Apple outlines. A locally supplied font requires appropriate use/modification
rights; availability of this code does not grant rights to redistribute fonts.

## Current status

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
glyph model or face. The latest rebuild at `ef564245` passed the old sample-41
WDTH location and retained the actual sample-44 wght counterexample: requested
323.3597412109375, reported 323.3596. No accepted `Swirl-VF.ttc` exists.

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
or a fresh original rebuild. Failure reports retain safe
axis values, binary64 hex, original/replay phase and completed-observation
counts. The separate boundary probe compares every predeclared numeric
candidate and cannot grant production acceptance. Neither this adapter nor a
successful diagnostic proves complete-font or continuous-space equivalence.

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
python tools/rebuild.py /private/PingFangUI.ttc \
  --oracle /private/build/coretext_extract \
  --output /private/output/Swirl-VF.ttc \
  --report /private/output/reconstruction.json
```

The current builder is **native-instance approximation**, not lossless format
translation. It retains original GIDs, face coverage, axis tags/ranges, and uses
standard glyf/gvar with explicit metric phantoms and equivalent HVAR/VVAR.
Its original total outline and metric budgets are 1 FUnit each, including
training/default rounding, independent holdouts and the 0.05-unit cubic allowance
when needed. Those are distinct from the source decoder's 1/32 FUnit gate;
neither budget was loosened in the geometry repair.

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
