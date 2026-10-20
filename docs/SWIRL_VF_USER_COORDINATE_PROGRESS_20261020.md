# Swirl-VF user-coordinate and metric continuation

This phase starts at `b5a84bfacc48e6b2a8be8f0797f34639530766c9` on
`work/core-completion-20261017`; every push is non-forced and based on a fresh
remote head. UI, animations and Rust Core are outside the changes.

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

