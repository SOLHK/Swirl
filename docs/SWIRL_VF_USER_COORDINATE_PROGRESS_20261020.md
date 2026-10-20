# Swirl-VF user-coordinate and metric continuation

This phase starts at `b5a84bfacc48e6b2a8be8f0797f34639530766c9` on
`work/core-completion-20261017`; every push is non-forced and based on a fresh
remote head. UI, animations and Rust Core are outside the changes.

## Ninth implementation checkpoint: actual Windows placement and supported CoreText table access

Local verification: **319/319 Python tests, zero skips, in 14.102 seconds;
6/6 audit tests**. Existing acceptance thresholds and timeout values are unchanged.

The preceding source is `af8df45a9ca3f2ed0d2e623856cb3c8ef85f3974` (parent
`4927316c74f935099a5648cefacc13ae0d1f2772`). Its actual native results are now
available; a successful job is not a complete-font acceptance decision.

### Original first failing sample is now identified

Run [39371704891](https://github.com/SOLHK/Swirl/actions/runs/39371704891),
job 118461413491, verified the exact original SHA before and after extraction.
All **32 face identities and 91 initial batches / 5,824 observations** passed.
At face 0 / GID 0, training sample 1, user coordinates
`WDTH=1, wght=501, HGHT=500`, the native vertical X origin differs from
`horizontal_origin_x + advance_width/2` by **100 FUnits**. The original
`1e-5` representation guard is unchanged. This is a width-extreme representation
failure, not the fractional default-width rounding case. The public report
contains only the absolute error; its sign is not inferred. **Zero original
glyph models or faces completed, no final accepted transcript, no TTC.**
Safe artifact 12240689906 contains only `rebuild.json`; its verified ZIP SHA is
`f03e9564b29deda8fd78fb5943ab050e9329e6195a0dbc9ea62344f794b5c449`.

### Real DirectWrite layout results

Run [39371704981](https://github.com/SOLHK/Swirl/actions/runs/39371704981),
job 118460805932, actually compiled with MSVC 19.44.35229.0 / SDK 10.0.26100.0
and executed **4,608 layouts / 11,520 glyph observations** on Windows Server
2022 build 20348 (product type 3). Four independent processes completed all
identity, axis, summary and EOF checks. This is not a Windows 11 machine.

| Default vertical route | Fixed-origin error, 64 single-Han observations | Above 1/32 | Above 1 FUnit |
| --- | ---: | ---: | ---: |
| `vert` | 0.5 FUnit maximum | 1 | 0 |
| `vkrn` | 0.5 FUnit maximum | 1 | 0 |
| `vrt2` | 98 FUnits maximum; no default correction | 58 | 58 |

For each route, default horizontal records match **128/128**, disabled records
match **256/256**, GSUB/clusters and regional mapping checks each pass **768/768**,
and design metrics and layout advances each match **1,920/1,920**. These counts
refer only to the independently authored eight-glyph fixture.

DirectWrite's actual offset differs from the continuous GPOS value by up to
0.25 FUnit. The worst final case has continuous width 906.5, native width 907,
continuous placement 13.25 and actual placement 13, leaving -0.5 FUnit. The
actual callback geometry confirms this quantization; it is not JSON formatting.
Separately examining all 64 default mixed layouts per route gives the same
0.5 maximum Han residual for `vert` and `vkrn`. All 128 rotated space/Latin runs
(192 glyphs) and all baselines remain exactly unchanged. Explicit activation
can move rotated Latin along world Y, so unconditional application-level feature
activation is not accepted. Artifact 12241327627 ZIP SHA:
`94ac58f2dece1244fd590e15a008a59db1461b1afae818082820ba3ff9402e85`.

The same run's HarfBuzz job 118460806224 passed all 12 original tests, no skips,
using HarfBuzz 12.3.2 / uharfbuzz 0.53.3. Its **3,840 shapes / 15,360 glyph
observations** reproduce the earlier local limits: only `vert` is active by
default; final fixed-origin error is at most 0.25 FUnit, while individually
rounded odd deltas still reach 2 FUnits. Default `vkrn` therefore differs across
the two measured engines. No universal feature-routing contract is inferred.

### Fix the actual macOS compilation failure, then rerun the native experiment

CoreText job 118460806251 in the same run failed during Swift compilation:
the current macOS SDK marks `CTFontTableOptions.excludeSynthetic` unavailable.
It executed **zero GPOS layouts**. The probe now uses supported
`CTFontTableOptions(rawValue: 0)` at both table reads, retaining exact table
hashes and absent-table checks for the actual run font. All existing nine
CoreText analyzer/protocol tests remain. Linux source checks cannot establish
Swift SDK compatibility; the new xcode-27 job must compile and execute it.
The experiment's raster resolution remains 2.667 FUnits/pixel and can diagnose
large placement/direction errors, not certify a 1/32 or 1-FUnit limit.

Production reconstruction and its vertical-origin guard are unchanged in this
small compile repair. An encoded positional model must include the independent
native X origin in its existing metric error budget before the original
reconstruction can proceed. The 141 original quantization questions, old strict
849/850 API failure, complete original reconstruction and Windows 11/Qt
acceptance remain unresolved.

## Eighth implementation checkpoint: actual reconstruction progress and variable vertical layout

Local verification: **319/319 Python tests, zero skips, plus 6/6 audit tests**.
This includes actual optional HarfBuzz tests, not Windows/CoreText execution.
An earlier 310-test run had one launcher subprocess hit its unchanged 20-second
deadline. Its log is retained locally; the unchanged launcher then passed its
isolated test in 1.521 seconds and the full 319-test suite in 13.098 seconds.
No deadline, numerical budget or failure assertion was loosened.

The latest completed native checkpoint is
`4927316c74f935099a5648cefacc13ae0d1f2772`, parent
`ef564245f5de600757b7283437c7daf31a1e90e9`. Its new policy passed all 91 initial
original batches and reached the actual metric representation gate.

### Original reconstruction: the axis blocker was passed, the first glyph model is still blocked

Run [39370313776](https://github.com/SOLHK/Swirl/actions/runs/39370313776),
job 118456892468, used the exact original SHA on macOS 27.0.1 / xcode-27.
It verified **32/32 physical faces**, accepted **91/91 batches / 5,824 glyph
observations**, and then stopped in `with_phantoms` at **face 0 / GID 0**:
`native horizontal coordinate of vertical origin is not representable by standard vmtx`.
No axis mismatch or replay payload failure occurred. There are still **zero
completed original glyph models, zero completed faces and no original TTC**.
The final native transcript was not reached; completed batch counts do not
constitute a completed source session or resumable face checkpoint.

This run did not preserve the particular training/holdout record that failed.
The new source retains its actual user location, sample index/kind and finite
absolute X-origin representation error, without exposing raw metric values or
paths. The unchanged 1e-5 representation condition still rejects the discrepancy.
Three independent tests include a late GID failure after a prior completed GID,
a holdout failure despite a larger general metric budget, and the public-field
allowlist. The helper does not guess the missing value in the preceding run.

### Complete original synthetic TTC: actual native extraction, rebuilding and reread passed

Run [39370313682](https://github.com/SOLHK/Swirl/actions/runs/39370313682),
job 118456463254, completed the full CoreText -> v2 verifier -> explicit source
table metrics -> builder -> saved TTC -> independent CoreText reread chain:

- **2/2 faces, 3/3 GIDs per face**, all three original axis labels/ranges/flags.
- Each face: **27 training + 38 holdout positions**, zero adaptive additions,
  maximum sampled outline error **0.010986328125 FUnit**, metric error **zero**.
- Accepted terminal transcript: **260 batches / 390 glyph observations**;
  internally **520 native requests / 780 records**, zero errors, source unchanged.
- Each face's **3 glyphs, 21 default points including phantoms and 7 gvar
  tuples** checked after serialization; HVAR/VVAR exact coefficients checked;
  both TTC faces retained every verified standalone table byte except the
  permitted `head.checkSumAdjustment` field.
- A real **3,424-byte TTC** was generated, SHA-256
  `74168ffac87764d52b388d37b1868efb044bd119dd0757c0b6df4a0e21327485`.
  It contains only original authored test symbols and was removed privately;
  it is not the Apple-derived deliverable.
- Another **58-request / 174-record** native extraction of source and candidate
  found zero control-point, bounds and source-table-metric differences. These
  reread coordinates are not all claimed to be previously unsampled.

The separate 174-record analytic source gate and 6+6 static checks also passed.
Their counts are separate from reconstruction. The unchanged old raw API test
still fails at 849 versus 850 under 1/32, so the Apple job remains failure.
The candidate's retained raw CoreText height discrepancy is at most 0.3375 in
this sample; the source gvar-only fixture's is 1.3375. Table-derived metrics
are labelled and never relabelled as raw API observations. This full synthetic
success does not admit the unverified Apple avar/HVGL SourceTables policy.

### Independent GPOS mechanism and actual-layout gates

`experiment_vertical_gpos.py` creates eight independent geometric symbols with
three axes, coherent HVAR/gvar phantom advances, blank and region/vertical GSUB
cases. Adding GPOS leaves the original outline, metric, mapping and GSUB tables
byte-identical. A GDEF ItemVariationStore and SinglePos XPlacement express
current-width/2 minus the desired fixed X origin. Exact encoding rejects
fractional bases/deltas; explicitly labelled rounded counterexamples retain
their failures. No production origin is altered by this experiment.

Actual local HarfBuzz 12.3.2 / uharfbuzz 0.53.3 measurement completed **3,840
shaping calls / 15,360 glyph observations**. Of the three tested routes, `vert`
is active in default vertical shaping; `vrt2` and `vkrn` require explicit
activation in this harness. Default horizontal layout is unchanged, but explicit
activation can also move horizontal text. The native GPOS shift differs from
serialized values by at most **0.005798816681 FUnit**. HVAR width rounding leaves
up to **0.25 FUnit** final X residual in the even fixture: within the existing
1-FUnit rebuild budget, not a universal 1/32 exact-layout pass. A rounded
multi-region odd-delta counterexample reaches **2 FUnits**, rejecting that
particular independent-rounding scheme, not all possible standard encodings.

The new `directwrite_vertical_layout.cpp` and Python driver exercise actual
TextLayout4::Draw / TextRenderer1 callbacks in four independent custom font
collections. Actual file/table identity, no simulations/fallback, Float32 axis
inputs and real Face5 echoes, text coverage and terminal summaries are required.
The matrix requests **4,608 layouts / 11,520 glyph observations**, including
both writing directions, both regions, mixed text and single-character ink
bounds at 32 coordinates. Default/explicit/disabled routes remain separate.
The single-character fixed-origin result is not a mixed-text acceptance claim.
Fifteen local protocol/stub tests pass; Windows native execution is pending.
`probe_coretext_vertical_gpos.py` adds **2,016 actual layout requests** over six
isolated source/candidate processes at seven axis points. It retains raw API,
CTRun positions/base origins, actual CTFrameDraw/CTRunDraw and memory-raster
comparisons separately. Candidate-minus-current-source and
candidate-minus-source-default can distinguish a working correction from a
source that is already fixed and would be moved twice. Nine original local
analyzer/protocol tests pass; Swift compilation and native results are pending.
The new workflow runs actual HarfBuzz, xcode-27 CoreText and Windows Server
layout and publishes
only original synthetic observations and safe metadata. It cannot certify
Windows 11 installation, Qt/Swirl, DPI quality or an original converted font.

## Seventh implementation checkpoint: predeclare a stable replay before native observations

Local verification: **280/280 Python regressions and 6/6 audit tests pass**.
The Linux suite exercises protocol/serialization and explicit unavailable-native
behavior; it is not a replacement for the new macOS integration run.

The preceding source checkpoint is
`ef564245f5de600757b7283437c7daf31a1e90e9`, based on concurrent Core parent
`a3b89050e141557444519c8c17f2a263e6a013fc`. Its actual native boundary run
[39368769062](https://github.com/SOLHK/Swirl/actions/runs/39368769062) passed on
xcode-27 with the exact original source hash. The private records were compared
in memory; the public artifact contains only safe counts and axis observations.

Define `T(x) = trunc(binary64(x * 10000)) / 10000`. The probe declared requested,
divide1, multiply1, divide2 and multiply2 before starting either native process.
It completed 12,800 original records (four faces, ten cases, 32 selected GIDs,
five variants and two opposite-order processes) and 600 original synthetic
records (two faces, ten cases, three GIDs, five variants and two processes).
All eight within-process comparison chains and five cross-process chains had
zero typed-command, topology, raw metric or provenance differences. Each chain
had 1,280 original pairs and 60 synthetic pairs. These repeated comparisons
must not be counted as additional unique GIDs.

Recomputing each expression from each variant's own input gives:

| Source observations | Effective axis values | Exact T matches | Exact T(T) matches |
| --- | ---: | ---: | ---: |
| Original selected faces | 1,200 | 1,128 | 1,200 |
| Original synthetic fixtures | 600 | 600 | 564 |

There was no missing nondefault axis. Omitted defaults account for 400 original
and 200 synthetic values. All 600 native instances retained their actual echo
through every requested glyph read. The original sample-44 request
`wght=323.3597412109375` really reported `323.3596`, while its single-T candidate
was `323.3597`. The synthetic request `267.10205078125` reported `267.102`, but
replaying that first value reported `267.1019`. This is an observed API numeric
representation issue; it is not evidence for a universal design-coordinate
mapping. In particular, the two weights were not cross-requested in both font
formats, so the difference cannot be causally attributed to HVGL versus glyf.

For all 60 cases in both processes, the independently predeclared value
`C=T(T(original_request))` actually echoed C exactly, and its selected-GID
payloads exactly matched the original request. Adapter v2 therefore computes
the finite plan **before its first native request**. The original echo must
exactly equal the original value, T or T(T); one independent instance is then
created at the fixed C, whose actual echo must equal C exactly. Every GID's
complete typed path and every raw metric must match with zero tolerance before
any record from the batch is released. The emitted data and location remain
those of the original request. Negative/zero values stay exact-only; out-of-range
candidates fail without clamping. There is no third construction, recursive
truncation, epsilon increase, response-selected replay or per-point model choice.

The native source/table/axis identity, final transcript, source SHA, EOF, process
exit and per-face checkpoint bindings remain mandatory. Three new independent
regressions cover both first-echo expressions with the same predeclared replay,
a still-unstable replay and 1e-10 payload differences, and range-boundary
rejection before any native call. The adapter-specific suite passes **25/25**.
The new production policy needs a fresh original reconstruction run; the boundary
diagnostic alone cannot accept untested GIDs or continuous coordinates.

The preceding actual original rebuild
[39368768983](https://github.com/SOLHK/Swirl/actions/runs/39368768983) verified
32/32 source faces and stopped at face 0, GIDs 0-63, sample 44 / request 45.
It retained 44 completed batches / 2,816 accepted glyph observations, separately
from **zero completed glyph models, zero completed faces and no TTC**. Its exact
numeric failure is the original sample-44 observation above. The same commit's
[39368768995](https://github.com/SOLHK/Swirl/actions/runs/39368768995) passed
277 Python tests, six audit tests and Windows Server's original DirectWrite
fixtures. The unchanged strict raw CoreText 849/850 metric test still failed.

The 141 original HVAR quantization questions, all rejected global user/design
mapping models, real vertical-origin-X expression and all-GID reconstruction
remain unresolved. This change cannot establish Windows 11, Qt/Swirl or DPI
acceptance, and no original-derived output font is published.

## Sixth implementation checkpoint: preserve actual failure evidence and quantize residuals once

Local verification for this checkpoint: **277/277 Python tests and 6/6 audit
tests passed**. The final pre-publication HEAD advanced again to concurrent Core
commit `a3b89050e141557444519c8c17f2a263e6a013fc`; its changes are preserved.

The preceding font checkpoint is `24119489f7b85fe58dea53acf3a4a6f467a6e8fa`,
based on the preserved concurrent Core parent
`54908e2902c28ae20e2588fa5347df9b2b3d76e9`. Its real native outcomes are now
known; the adapter has not yet obtained a complete original-font pass.

- [39366215864](https://github.com/SOLHK/Swirl/actions/runs/39366215864): the
  opposite-first-writer gate completed all four chains at **704/704 exact
  payload matches**, 2,816 native glyph records total. The actual original
  reconstruction verified all 32 physical source identities and passed the
  former sample-41 WDTH guard location. It stopped at **face 0, GIDs 0-63,
  sample 44 / request 45**, with `native_readback_not_named_decimal4_candidate`.
  The requested location was WDTH=304.712646484375, wght=323.3597412109375,
  HGHT=728.240966796875. No glyph model or face was completed; no TTC exists.
- [39366215910](https://github.com/SOLHK/Swirl/actions/runs/39366215910):
  Python passed 254 tests plus 6 audit tests; Windows Server DirectWrite passed
  the original synthetic fixtures. The real two-face synthetic reconstruction
  used CoreText -> exact-axis adapter -> SourceTables -> builder, and stopped
  at the corresponding sample 44 with `native_readback_replay_not_exactly_stable`.
  Its requested wght was 267.10205078125. The unchanged raw CoreText test still
  reports 849 versus 850. The separate 174-record table/native-path comparison
  and two six-record static-instance comparisons passed.
- [39366216066](https://github.com/SOLHK/Swirl/actions/runs/39366216066):
  actual CTFrameDraw/CTRunDraw completed 378 single-character and 42 mixed-text
  observations over seven faces. Among 245 nonempty default/variation pairs,
  the fixed native X-origin model had maximum raster residual **0.186695 FUnit**;
  current-width/2 had maximum residual **100.008297 FUnits**. No fallback,
  missing/clipped ink or incomparable pair was detected. The instrument has
  2.667 FUnits per pixel and does not establish a 1/32 outline bound. It confirms
  that the fixed-X behavior affects actual drawing, not just the metric API.

The original and synthetic sample-44 failures did not preserve their inner
axis, reported number or original/replay phase. The numeric difference between
`trunc(x*10000)/10000` and `trunc(x*10000)*0.0001` is a concrete hypothesis, not
an observed native conclusion: at both requested weights those expressions
are one binary64 ULP apart, and the divided value can drift on a second
application. Production acceptance is **unchanged** in this checkpoint.

`verified_axis_oracle.py` now attaches safe finite requested/reported/candidate
numbers, binary64 hexadecimal forms, the exact axis and original/replay phase
to failures. `NativeOracle` and the builder retain these fields through the
private error protocol and a typed public-summary allowlist; outline data and
unreviewed strings cannot pass through that allowlist. Completed native batch
and glyph-observation counts are now reported separately from reconstructed
GIDs, faces and accepted final transcripts.

The new independent `probe_axis_readback_boundaries.py` declares all five
candidate instances before native processes start: requested, divide1,
multiply1, divide2 and multiply2. It compares every candidate's complete typed
path and raw metrics, and repeats construction in the opposite order. Both
sample-44 failures, the previous WDTH control, binary64 neighbors and decimal
neighbors are included: 12,800 original selected-GID records across faces
0/15/20/31 and 600 records from private original synthetic fixtures are planned.
The new native result must be read before selecting any production policy.
There is no recursive search, numeric tolerance or per-point best-model choice.

A separate original analytic counterexample proved that the builder rounded
masters and then residuals, causing an avoidable **1.40007142675 FUnit** training
error. It now fits the unrounded native master vectors and rounds each residual
against already encoded integer coefficients exactly once. The same authored
27-corner-plus-adaptive-peak model has maximum error **0.014142135624 FUnit**,
also after real TTF serialization and independent fontTools glyph-set rendering.
The default glyf coordinates and all gvar deltas remain integers. Four original
regressions include negative half-coordinate rounding and prove that fontTools'
in-place arithmetic cannot modify the original reference vectors. This is a
converter arithmetic repair, not evidence that Apple source GIDs have passed.

The original 141 HVAR quantization questions, unsupported global user/design
mapping, real vertical-origin-X expression and strict raw CoreText metric
failures remain explicit. No original-derived font, Windows 11 installation,
Qt/Swirl rendering or DPI acceptance is available. The five-minute public CI
attempt is still an early-failure experiment with private temporary data; it
must not be described as a full-build runtime or durable private checkpoint.

## Fifth implementation checkpoint: exact batch replay and accepted transcripts

Local full regression now passes **254/254 tests plus 6/6 audit tests**. New
native jobs have been wired but are not declared passing in this source
checkpoint. The remote advanced during publication to concurrent Core commit
`54908e2902c28ae20e2588fa5347df9b2b3d76e9`, following
`85f4cb916221fb64b9c07f0cd6fd85bbc7e94883` and our font checkpoint
`c31edaf04f3a6369e90da026b94aa6cf8176f356`. The five newly changed Core/CI
paths do not overlap this font work; publication was rebased without force.

`coretext_extract.swift` separates instance construction from acceptance. The
ordinary `makeInstance` path retains the exact original 1e-6 guard. Explicit
`--axis-observations` marks raw observations as unaccepted; neither the builder
nor SourceTables adapter can consume them directly. `verified_axis_oracle.py`
binds every original source table and every physical face/axis, including raw
fvar flags/hidden. It accepts a batch only after all its requested GIDs pass an
exact, finite, typed-command and raw-metric comparison against one separately
constructed reported-coordinate instance. Missing nondefault axes, an unknown
readback rule, a changing replay echo, any payload difference or late GID error
blocks the entire batch. Original requested/reported values and native payloads
are retained. There is no avar inference or replacement metric in this adapter.

The named positive decimal-four truncation candidate describes a falsifiable
readback hypothesis, not Apple's public contract. Binary64 multiplication and
truncation is not always idempotent; replay must actually echo the first value,
and is never recursively truncated until it matches. Twenty new adapter tests
include real subprocess/pipe consumption, independent source-metadata fixtures,
109 synthetic non-idempotent boundaries, malformed/missing records, late failure,
source mutation and hash-bound launcher dependencies.

The separate first-writer native gate compares two new processes with opposite
creation order. All 32 selected GIDs are forced through the first-created font
before creating the other font. Planned coverage is faces 20/31, 11 positions
per face, four comparison chains of 704 GID pairs each. Canonical values are
computed before either process starts. This does not claim that a system font
service cache was cleared. Fourteen original tests pass; native results remain
to be checked. The exact-source reconstruction job now depends on this gate and
uses the per-request verifier, with the unchanged outline/metric budgets.

The builder now verifies a complete final native summary, external request/GID
counts, source identity, EOF and successful process exit before TTC publication.
A reproduced recovery bug was also fixed: a face serialized before a failing
final summary could previously survive in a checkpoint and bypass that failure
on restart. Checkpoint recipe v2 requires a complete, independently finished
native session for each face before saving it. Restores require the accepted
transcript bound to the source, all-table identity, physical face and launcher.
A fresh zero-request session on a fully restored build cannot replace those
earlier face proofs. Twelve checkpoint regressions include this exact failure,
changed source/bytes/code/identity and valid partial recovery.

The synthetic native/table-metric reconstruction gate chains the verified axis
launcher with the existing standard-identity SourceTables adapter. Its original
raw 849/850 CoreText gate remains unchanged and separately reported. No source
table policy for Apple HVGL has been admitted. An independent actual CTFrameDraw
and CTRunDraw diagnosis is added for 378 single-character observations and 42
mixed-text frames over seven representative faces. All glyph paths and bitmaps
stay in memory; the 2.667-FUnit/pixel raster instrument distinguishes the large
placement signal and does not replace the unchanged 1/32 FUnit acceptance.

### Newly completed native evidence from the previous checkpoint

Run [39362516018](https://github.com/SOLHK/Swirl/actions/runs/39362516018),
source `c31edaf04f3a6369e90da026b94aa6cf8176f356`, actually completed all 32
faces and 2,692 user positions, 86,144 selected-GID comparisons per model:

| Mapping hypothesis | Failed comparisons | Measured point failures | Maximum measured point error |
| --- | ---: | ---: | ---: |
| raw-order float | 491 | 100 | 2.942359 FUnit |
| raw-order final F2DOT14 | 290 | 100 | 2.942506 FUnit |
| raw-order two F2DOT14 | 430 | 135 | 6.490196 FUnit |
| signed-zero raw-order two F2DOT14 | 150 | 65 | 0.453230 FUnit |

The other failures are strict segment-type correspondence failures; no model
passes the full sample. The best candidate's 65 measured failures occur on
faces 15-19 near the positive side of the weight default. All earlier models and
the 141 HVAR quantization questions remain. Requested/readback path comparison
had zero error, but only 44,928 comparisons constructed a distinct sibling;
the other 41,216 reused unchanged requests. These counts must not be conflated.

The same run's independent vertical-origin probe measured 6,912 values. All
retained the default native X exactly. Source default hmtx/2 differs on odd
widths by 0.5; current native width/2 differs in 3,956 observations, by up to
100 FUnits. Height=1000 and vertical Y=860 held for all measured values. Those
API findings motivate the actual drawing probe; they do not authorize changing
the source origins. No original-derived final font or Windows 11/Qt acceptance
has been produced by this checkpoint.

## Actual source and first native result

The uploaded 61,473,880-byte file matches SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
All 32 physical faces contain 47,102 GIDs. The original remains unchanged.

Executable diagnostic commit:
`0531127a0babcd8242b9d7f81db9f5c9c0202d3c`.
Native run: https://github.com/SOLHK/Swirl/actions/runs/39359357221
Apple job 118421592043 actually used xcode-27 / macOS 27.0.1. Python and Windows
synthetic jobs passed. The unchanged strict CoreText metric gate still fails at
849 versus 850. The new precision experiment completed successfully; this is a
diagnostic completion, not metric or font acceptance.

Each of three independently generated fixture expressions was measured at 58
requests x 3 GIDs x 4 point-size scales. Neither changing measurement size
(0.25, 1, 16, 64 times UPEM) nor using a verified single-glyph CTRun eliminates
the error in source font units. For each scale:

| Original fixture expression | Glyph observations | Outside 1/32 budget | Maximum height error |
| --- | ---: | ---: | ---: |
| gvar-only | 174 | 107 | 1.3375 FUnit |
| equivalent production HVAR/VVAR | 174 | 4 | 0.3375 FUnit |
| equivalent explicit bearing maps | 174 | 4 | 0.3375 FUnit |

Explicit bearing maps improve the maximum vertical-origin error to about
0.0039453 FUnit but do not cure integer vertical advances. These observations
exclude a simple output-size/JSON-format fix. Raw API measurements must remain
distinct from exact source-table metrics. No uniform +1 correction is valid.
The new `SourceMetrics` module evaluates hmtx/HVAR, vmtx/VVAR/VORG and gvar
phantoms at explicitly supplied design coordinates. It is an independent
reference; user-axis mapping must be verified before production use.

## New original-user geometry experiment

`probe_user_axis_geometry.py` pairs actual CoreText instances constructed from
the requested user values and their API readbacks. Separately it compares each
requested instance against the already repaired HVGL evaluator under global,
falsifiable mapping candidates. It retains all 32 physical faces, the earlier
structural GID selector, endpoints/defaults, fractional and joint axis samples,
and both sides of raw avar knots. The 1/32 FUnit geometry budget is unchanged.
No per-point best-model mixture can create a global pass. Original paths remain
process-private; only coordinates, counts, GIDs and discrepancies are published.
This new experiment has not yet been declared a native pass in this checkpoint.

## Recovery for full reconstruction

`rebuild.py --checkpoint-dir /private/checkpoints` now retains already fully
verified physical faces. The manifest binds the original and oracle hashes,
relevant converter-source hashes, runtime versions, error budgets and adaptive
limits. Resumption checks cached bytes and identity before skipping native work;
the original final TTC table verification is still required. Cached TTFs are
private data, never public Actions artifacts. Six new tests include an actual
three-face synthetic build failing on face two, then resuming successfully.

Failure records now identify stage, face, glyph or glyph range, user location,
sample number and available errors. A started face is not a completed face.

The current unchanged sampling scheme needs 130,001,520 native glyph
observations before adaptive work: faces 0-19 have 27+64 locations, faces 20-23
27+46, and faces 24-31 27+54. Five minutes cannot be treated as a full-build
acceptance timeout. Shared source tables and measured throughput need attention
after the source-coordinate and metric gates are understood.

## Boundaries

No accepted `Swirl-VF.ttc` has been generated. No original-derived candidate has
passed Windows 11 installation, Qt/Swirl or DPI tests. The previous design-space
1088/1088 result remains valid in its original scope and is not a full font.
The 141 HVAR quantization questions remain under explicit investigation.
No Apple font, Apple outline, derived font or credential is included here.

Primary references consulted: Apple CTFontCopyVariation and metric APIs;
OpenType otvaroverview normalization precision, avar, gvar, HVAR/VVAR/VORG;
fontTools VarStoreInstancer/VariationModel; Skia TypefaceMacTest at
709209322f9597b6712079a4386f4d1c7e9b5d44; HarfBuzz and Fontations raw avar
compatibility handling. These sources inform falsifiable hypotheses, not an
assumption that Apple's entire implementation matches one candidate.
# Fourth implementation checkpoint: native counterexamples and batched references

The exact-source user-coordinate run `39359956472` completed at
`ff3b59190ed1a6c6a628aba9e915aaf9eed18247`: 32 faces, 2,328 user positions
and 74,496 glyph checks per model. The raw/final-F2/two-F2 models retained
454/290/290 failures respectively; none passes the entire sample. Some are
strict L/Q correspondence failures rather than a measured large path error.
Requested versus readback-created native paths had zero discrepancy in the
40,704 comparisons that actually constructed a different readback instance;
the remaining 33,792 comparisons reused the unchanged request record. This did
not compare every raw metric or prove a universal coordinate mapping, and is
not complete-font acceptance.

At `4461798c9989d7230affc1d46560f6147b859e8c`, run `39361349404`
reproduced the original blocker at face 0, GIDs 0–63, sample 41, location
WDTH=600.5859375, wght=368.22259521484375, HGHT=975.7080078125.
All 32 source faces verified; zero glyphs/faces completed and no output font.
CFNumber direct reads, NSNumber and descriptor metadata agree on the stored
limited readback, so this is not merely a JSON display or NSNumber read issue.

Run `39361349387` actually passed the 174-record analytical native-path and
source-table-metric gate (native control-point error <=0.00660285213 FUnit),
plus two six-record static gates. Its full synthetic reconstruction remains
blocked by the same WDTH assertion; the raw API gate still fails at 849/850.
Python and Windows Server DirectWrite jobs passed, not Windows 11 acceptance.

The original native data also rejects current-width/2 as a universal Apple
vertical-origin-X interpretation (38,775/74,496 outside 1/32; max126.398987).
The standard SourceMetrics X convention is now explicitly labelled; the
HVGL adapter remains refused. A separate native origin probe tests predeclared
current/default/static-width hypotheses. No original metric was overwritten.

The portable reference computation is now batched across a whole face. Private
face-0 equivalence testing checked all 7,200 glyph/model positions: identical
source topology and maximum raw coordinate difference 0.0. Pure rendering CPU
was 96.3299s versus 2.3830s; parsing/native work is excluded from this ratio.
All per-face native observations remain independent. The revised diagnostic
preserves the old models, adds a separately falsifiable signed-zero hypothesis,
adds targeted counterexample coordinates and retains more failure context.

Local checkpoint regression: **202/202 Python tests pass**. Original 141 HVAR
quantization disagreements are retained, not relabelled as fixed.

# Third implementation checkpoint: transparent metric provenance

The xcode-27 run at `0531127a0babcd8242b9d7f81db9f5c9c0202d3c`
(`39359357221`) observed macOS 27.0.1. Increasing measurement size from
0.25 to 64 UPEM and using CTRun did not remove the retained raw CoreText
metric discrepancies. A new adapter uses explicit source-table coordinates
for exact metrics while retaining every raw API field and discrepancy.
Its CLI currently accepts only standard glyf fonts with verified identity
avar; it explicitly rejects an Apple/HVGL mapping guess or a diagnostic
axis-guard bypass. The old strict CoreText API gate remains unchanged.

The independent table-metric gate checks the original analytical fixture,
blank glyphs, fractional and static instances, then actually invokes the
complete reconstruction and independent serialized/native reread. It fails
if the existing production axis guard rejects a request. This is a separate
converter-data gate, not a claim that Apple's API metrics have passed.

The new quantization analysis retains all 141 original F2DOT14 discrepancies.
A normalized-16.16 truncation candidate explains those cases but introduces
36 different mismatches; no globally valid replacement is accepted. Native
construction diagnostics now read the same CFNumber through the C API and
inspect descriptor attributes to distinguish transport from stored values.

Local verification before this checkpoint: **180/180 Python tests and 6/6
audit tests pass**. Original 32-face reconstruction is still blocked before
the first completed face; no final font and no Windows 11/Qt acceptance.

